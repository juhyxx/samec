#!/usr/bin/env python3
"""
Ammo Figures (AMMO.F-XXX) palette parser.

Single-image JPG with two mirrored table columns:
  REFERENCE | COLOR NAME | COLOR swatch

Outputs:
  data/pack_ammo_figures.json
  data/pack_ammo_figures.csv
"""

import csv
import json
import re
import sys
from pathlib import Path

import numpy as np
from PIL import Image

_HERE = Path(__file__).resolve().parent
_ROOT = _HERE.parents[2]  # source/ammo/figures/__main__.py → root

IMAGE_PATH = _HERE / "figures.jpg"
OUTPUT_JSON = _ROOT / "data" / "pack_ammo_figures.json"
OUTPUT_CSV = _ROOT / "data" / "pack_ammo_figures.csv"

# The image is 926 px wide, two groups split at the midpoint.
# Within each half the swatch band is the rightmost ~80 px.
IMG_HALF_X = 463  # horizontal midpoint separating left / right table
SWATCH_INSET = 18  # px from the right edge of each half to sample swatch
SWATCH_WIDTH = 45  # width of swatch sample strip

CODE_RE = re.compile(r"AMMO\.?F[-.]?(\d{3})", re.IGNORECASE)


def rgb_to_hex(r, g, b):
    return "#{:02x}{:02x}{:02x}".format(int(r), int(g), int(b))


def sample_swatch(arr, row_y1, row_y2, half):
    """Average pixels in the swatch band for a given row band and half (0=left, 1=right)."""
    h, w = arr.shape[:2]
    if half == 0:
        sx2 = IMG_HALF_X - SWATCH_INSET
        sx1 = max(0, sx2 - SWATCH_WIDTH)
    else:
        sx2 = w - SWATCH_INSET
        sx1 = max(IMG_HALF_X, sx2 - SWATCH_WIDTH)

    y1 = max(0, row_y1 + 2)
    y2 = min(h, row_y2 - 2)
    if y2 <= y1 or sx2 <= sx1:
        return "#cccccc"
    region = arr[y1:y2, sx1:sx2]
    avg = region.reshape(-1, 3).mean(axis=0)
    return rgb_to_hex(*avg)


def parse_ammo_figures(image_path=None, output_json=None, output_csv=None):
    import easyocr

    # Accept either a folder path (pipeline convention) or direct image path
    if image_path is None:
        img_path = IMAGE_PATH
    else:
        p = Path(image_path)
        img_path = (p / "figures.jpg") if p.is_dir() else p
    out_json = Path(output_json) if output_json else OUTPUT_JSON
    out_csv = Path(output_csv) if output_csv else OUTPUT_CSV

    if not img_path.exists():
        print(f"ERROR: image not found: {img_path}")
        sys.exit(1)

    img = Image.open(img_path).convert("RGB")
    arr = np.array(img)
    img_h, img_w = arr.shape[:2]

    print(f"Image: {img_path.name}  ({img_w}×{img_h})")
    print("Loading OCR reader…")
    reader = easyocr.Reader(["en"], gpu=False)

    print("Running OCR…")
    ocr = reader.readtext(arr)

    # ── collect all text with bboxes ──────────────────────────────────────────
    texts = []
    for bbox, text, conf in ocr:
        pts = np.array(bbox)
        x1 = int(pts[:, 0].min())
        y1 = int(pts[:, 1].min())
        x2 = int(pts[:, 0].max())
        y2 = int(pts[:, 1].max())
        texts.append(
            {"text": text.strip(), "conf": conf, "x1": x1, "y1": y1, "x2": x2, "y2": y2}
        )

    # ── find code entries ─────────────────────────────────────────────────────
    code_entries = []
    for t in texts:
        m = CODE_RE.search(t["text"])
        if m:
            num = int(m.group(1))
            half = 0 if t["x1"] < IMG_HALF_X else 1
            code_entries.append(
                {
                    "code": f"AMMO.F-{num:03d}",
                    "num": num,
                    "half": half,
                    "x1": t["x1"],
                    "x2": t["x2"],
                    "y1": t["y1"],
                    "y2": t["y2"],
                    "cy": (t["y1"] + t["y2"]) // 2,
                }
            )

    if not code_entries:
        print("ERROR: no AMMO.F codes found in image")
        sys.exit(1)

    code_entries.sort(key=lambda e: (e["half"], e["cy"]))
    print(f"Found {len(code_entries)} codes")

    # ── for each code, find the closest name text in the same half ────────────
    # Name text lives to the right of the code but left of the swatch strip.
    name_texts = [t for t in texts if not CODE_RE.search(t["text"]) and t["text"]]

    # ── build row bands: each code spans from its y1 to the next code's y1 ───
    colors = []
    # Group entries by half to compute row bands independently
    for half_id in (0, 1):
        half_codes = [e for e in code_entries if e["half"] == half_id]
        for i, entry in enumerate(half_codes):
            # row band: from this code's y1 to next code's y1 (or img bottom)
            row_y1 = entry["y1"]
            row_y2 = half_codes[i + 1]["y1"] if i + 1 < len(half_codes) else img_h

            # swatch x bounds for this half
            if half_id == 0:
                name_x_min = entry["x2"] + 2
                name_x_max = IMG_HALF_X - SWATCH_WIDTH - SWATCH_INSET - 2
            else:
                name_x_min = IMG_HALF_X + entry["x2"] - entry["x1"] + 2
                name_x_max = img_w - SWATCH_WIDTH - SWATCH_INSET - 2

            # find name tokens in this row band and x range
            name_tokens = []
            for t in name_texts:
                in_half = (
                    (t["x1"] < IMG_HALF_X) if half_id == 0 else (t["x1"] >= IMG_HALF_X)
                )
                in_row = (t["y1"] >= row_y1 - 4) and (t["y2"] <= row_y2 + 4)
                in_x = (t["x1"] >= name_x_min) and (t["x2"] <= name_x_max + 60)
                if in_half and in_row and in_x:
                    name_tokens.append((t["x1"], t["text"]))

            name_tokens.sort(key=lambda x: x[0])
            name = " ".join(tok for _, tok in name_tokens)

            hex_color = sample_swatch(arr, row_y1, row_y2, half_id)

            colors.append(
                {
                    "code": entry["code"],
                    "name": name,
                    "hex": hex_color,
                }
            )

    colors.sort(key=lambda c: int(c["code"].split("-")[1]))

    print(f"Colors extracted: {len(colors)}")

    # ── write JSON ────────────────────────────────────────────────────────────
    pack = {
        "brand": "Ammo by Mig Figures",
        "brand_id": "ammo_figures",
        "source": str(img_path),
        "count": len(colors),
        "colors": colors,
    }
    out_json.parent.mkdir(parents=True, exist_ok=True)
    out_json.write_text(
        json.dumps(pack, indent=2, ensure_ascii=False), encoding="utf-8"
    )
    print(f"✓ JSON → {out_json}")

    with out_csv.open("w", newline="", encoding="utf-8") as fh:
        writer = csv.DictWriter(fh, fieldnames=["code", "name", "hex"])
        writer.writeheader()
        writer.writerows(colors)
    print(f"✓ CSV  → {out_csv}")

    return colors


if __name__ == "__main__":
    print("Starting Ammo Figures parser…")
    parse_ammo_figures()
