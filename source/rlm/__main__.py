#!/usr/bin/env python3
"""
Parse RLM color chart images.

Layout: regular grid of color swatches (7 per row).
Each swatch cell contains:
  - Top area: the color swatch itself
  - Below swatch: "RLM XX" code in bold
  - Below code: color name (German)

Strategy:
  1. OCR to find all "RLM XX" code entries
  2. For each code, find the name text just below it
  3. Sample pixel above the code text (within the swatch area) for the hex color
"""

from pathlib import Path
import json
import re
import csv
from statistics import mean

from PIL import Image
import numpy as np
import easyocr


RLM_FOLDER = Path("source/rlm")
OUT_JSON = Path("data/pack_rlm.json")
OUT_CSV = Path("data/pack_rlm.csv")

# Approximate cell width; dynamically computed but useful as a default
CELL_WIDTH_ESTIMATE = 200


def rgb_to_hex(arr):
    return "#{:02x}{:02x}{:02x}".format(int(arr[0]), int(arr[1]), int(arr[2]))


def extract_ocr(img_path, reader):
    res = reader.readtext(str(img_path))
    out = []
    for bbox, text, conf in res:
        text = text.strip()
        if not text:
            continue
        xs = [p[0] for p in bbox]
        ys = [p[1] for p in bbox]
        out.append(
            {
                "text": text,
                "confidence": float(conf),
                "bbox": {
                    "x": int(min(xs)),
                    "y": int(min(ys)),
                    "x_end": int(max(xs)),
                    "y_end": int(max(ys)),
                    "width": int(max(xs) - min(xs)),
                    "height": int(max(ys) - min(ys)),
                },
            }
        )
    return out


def normalize_rlm_code(text):
    """Parse 'RLM 02', 'RLM02', 'RLM 02-1', 'RLM02-1' → 'RLM-02', 'RLM-02-1'."""
    t = text.strip().upper().replace(" ", "")
    m = re.match(r"RLM[-]?(\d{2,3})(?:[-](\d))?$", t)
    if m:
        base = m.group(1)
        suffix = m.group(2)
        return f"RLM-{base}-{suffix}" if suffix else f"RLM-{base}"
    return None


def parse_rlm_image(img_path, reader):
    """Parse a single RLM chart image and return a list of color dicts."""
    with Image.open(img_path) as im:
        if im.mode != "RGB":
            im = im.convert("RGB")
        arr = np.array(im)
    h, w = arr.shape[:2]

    text_entries = extract_ocr(img_path, reader)

    # Find all RLM code entries
    code_entries = []
    for e in text_entries:
        code = normalize_rlm_code(e["text"])
        if code:
            code_entries.append({"code": code, "entry": e})

    if not code_entries:
        return []

    # Estimate cell width from x-spacing between codes in the same row
    # Group codes by approximate row (y within 40px)
    rows: dict[int, list] = {}
    for ce in code_entries:
        ey = ce["entry"]["bbox"]["y"]
        key = None
        for ky in list(rows.keys()):
            if abs(ey - ky) < 40:
                key = ky
                break
        if key is None:
            key = ey
        rows.setdefault(key, []).append(ce)

    x_gaps = []
    for row_entries in rows.values():
        if len(row_entries) < 2:
            continue
        row_sorted = sorted(row_entries, key=lambda e: e["entry"]["bbox"]["x"])
        for i in range(1, len(row_sorted)):
            gap = (
                row_sorted[i]["entry"]["bbox"]["x"]
                - row_sorted[i - 1]["entry"]["bbox"]["x"]
            )
            if 50 < gap < 600:
                x_gaps.append(gap)
    cell_w = int(mean(x_gaps)) if x_gaps else CELL_WIDTH_ESTIMATE

    results = []
    seen = set()

    for ce in code_entries:
        code = ce["code"]
        if code in seen:
            continue
        seen.add(code)

        e = ce["entry"]
        ex = e["bbox"]["x"]
        ey = e["bbox"]["y"]
        ey_end = e["bbox"]["y_end"]
        code_height = e["bbox"]["height"] or 16

        # ── Sample swatch color ──────────────────────────────────────
        # The swatch is ABOVE the code text.  Sample a region ~half a cell
        # height above, centred horizontally on the code entry.
        swatch_cx = int(ex + e["bbox"]["width"] / 2)
        swatch_cy = max(0, int(ey - cell_w * 0.35))

        margin = max(6, cell_w // 8)
        r1 = max(0, swatch_cy - margin)
        r2 = min(h, swatch_cy + margin)
        c1 = max(0, swatch_cx - margin)
        c2 = min(w, swatch_cx + margin)
        region = arr[r1:r2, c1:c2]
        if region.size > 0:
            avg = region.reshape(-1, 3).mean(axis=0)
            # Reject near-white (background) and retry lower
            lum = float(avg.mean())
            if lum > 240:
                r1b = max(0, ey - int(cell_w * 0.5))
                r2b = max(0, ey - 4)
                region2 = arr[r1b:r2b, c1:c2]
                if region2.size > 0:
                    avg2 = region2.reshape(-1, 3).mean(axis=0)
                    if float(avg2.mean()) < lum:
                        avg = avg2
            hex_color = rgb_to_hex(avg)
        else:
            hex_color = "#cccccc"

        # ── Find name text just below the code ───────────────────────
        name_candidates = []
        for te in text_entries:
            tx = te["bbox"]["x"]
            ty = te["bbox"]["y"]
            t = te["text"].strip()
            # Must be below the code entry
            if ty <= ey_end or ty > ey_end + code_height * 4:
                continue
            # Must be in the same horizontal column
            if abs(tx - ex) > cell_w * 0.55:
                continue
            # Skip if it's another RLM code
            if normalize_rlm_code(t):
                continue
            if len(t) < 2:
                continue
            name_candidates.append(
                {"text": t, "dy": ty - ey_end, "conf": te["confidence"]}
            )

        if name_candidates:
            name_candidates.sort(key=lambda c: (c["dy"], -c["conf"]))
            name = name_candidates[0]["text"]
        else:
            name = ""

        results.append({"code": code, "name": name, "hex": hex_color})

    return results


def parse_rlm_images(folder_path, output_json):
    folder = Path(folder_path)
    output_json = Path(output_json)

    if not folder.exists():
        print(f"RLM folder not found: {folder}")
        return []

    files = sorted(folder.glob("*.png"))
    if not files:
        print(f"No PNGs in {folder}")
        return []

    reader = easyocr.Reader(["en"], gpu=False)
    all_colors = []
    seen_codes: set[str] = set()

    for f in files:
        print(f"Processing {f.name}...")
        rows = parse_rlm_image(f, reader)
        for r in rows:
            if r["code"] not in seen_codes:
                seen_codes.add(r["code"])
                all_colors.append(r)
        print(f"  {len(rows)} colors found")

    pack = {
        "brand": "RLM",
        "brand_id": "rlm",
        "source": str(output_json),
        "count": len(all_colors),
        "colors": [
            {
                "code": c["code"],
                "name": c.get("name", ""),
                "hex": c["hex"],
                "equivalents": [],
                "confidence": None,
            }
            for c in all_colors
        ],
    }

    output_json.parent.mkdir(parents=True, exist_ok=True)
    output_json.write_text(json.dumps(pack, indent=2, ensure_ascii=False))
    print(f"Wrote {len(all_colors)} RLM colors to {output_json}")

    csv_path = output_json.parent / "pack_rlm.csv"
    with csv_path.open("w", newline="") as fh:
        w = csv.DictWriter(fh, fieldnames=["code", "name", "hex"])
        w.writeheader()
        for c in all_colors:
            w.writerow({"code": c["code"], "name": c.get("name", ""), "hex": c["hex"]})
    print(f"Wrote CSV to {csv_path}")

    return all_colors


if __name__ == "__main__":
    parse_rlm_images(RLM_FOLDER, OUT_JSON)
