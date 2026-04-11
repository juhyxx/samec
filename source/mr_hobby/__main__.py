#!/usr/bin/env python3
"""
Parse Mr. Hobby Mr. Color chart images.
Grid layout: each cell has a number (top-left), color swatch, and name at
the bottom-left inside the cell.
"""

from pathlib import Path
import json
from PIL import Image
import numpy as np
import easyocr
import cv2
import re
import csv
from statistics import mean


def rgb_to_hex(arr):
    """Convert RGB array to hex color."""
    return "#{:02x}{:02x}{:02x}".format(int(arr[0]), int(arr[1]), int(arr[2]))


def find_grid_cells(image_array, min_size=40):
    """Detect rectangular cells in a bordered grid using line projection.

    Returns a list of {x, y, width, height, hex, rgb} dicts sorted row-first.
    """
    h, w = image_array.shape[:2]
    gray = cv2.cvtColor(image_array, cv2.COLOR_RGB2GRAY)

    # Detect dark border-like edges via Canny
    edges = cv2.Canny(gray, 60, 150)

    # ── Horizontal lines ──────────────────────────────────────────────
    kernel_h = cv2.getStructuringElement(cv2.MORPH_RECT, (max(1, w // 12), 1))
    h_lines = cv2.morphologyEx(edges, cv2.MORPH_CLOSE, kernel_h)
    h_proj = np.sum(h_lines, axis=1).astype(float)

    threshold_h = h_proj.max() * 0.25
    row_ys = []
    in_line = False
    group = []
    for idx, val in enumerate(h_proj):
        if val >= threshold_h:
            in_line = True
            group.append(idx)
        elif in_line:
            row_ys.append(int(np.mean(group)))
            group = []
            in_line = False
    if group:
        row_ys.append(int(np.mean(group)))

    # ── Vertical lines ────────────────────────────────────────────────
    kernel_v = cv2.getStructuringElement(cv2.MORPH_RECT, (1, max(1, h // 12)))
    v_lines = cv2.morphologyEx(edges, cv2.MORPH_CLOSE, kernel_v)
    v_proj = np.sum(v_lines, axis=0).astype(float)

    threshold_v = v_proj.max() * 0.25
    col_xs = []
    in_line = False
    group = []
    for idx, val in enumerate(v_proj):
        if val >= threshold_v:
            in_line = True
            group.append(idx)
        elif in_line:
            col_xs.append(int(np.mean(group)))
            group = []
            in_line = False
    if group:
        col_xs.append(int(np.mean(group)))

    # ── Build cells from grid ─────────────────────────────────────────
    cells = []
    for i in range(len(row_ys) - 1):
        for j in range(len(col_xs) - 1):
            x1, y1 = col_xs[j], row_ys[i]
            x2, y2 = col_xs[j + 1], row_ys[i + 1]
            cw, ch = x2 - x1, y2 - y1
            if cw < min_size or ch < min_size:
                continue

            # Sample color from the upper 55% of the cell (swatch area),
            # excluding the very top (number box) and outer edges.
            sy, ey = y1 + int(ch * 0.20), y1 + int(ch * 0.60)
            sx, ex = x1 + int(cw * 0.10), x1 + int(cw * 0.90)
            sy, ey = max(0, sy), min(h, ey)
            sx, ex = max(0, sx), min(w, ex)
            region = image_array[sy:ey, sx:ex]
            if region.size == 0:
                continue
            avg = region.reshape(-1, 3).mean(axis=0)

            cells.append(
                {
                    "x": int(x1),
                    "y": int(y1),
                    "width": int(cw),
                    "height": int(ch),
                    "rgb": [int(avg[0]), int(avg[1]), int(avg[2])],
                    "hex": rgb_to_hex(avg),
                }
            )

    return sorted(cells, key=lambda c: (c["y"], c["x"]))


def extract_ocr(img_path, reader):
    """Extract text from image using OCR."""
    res = reader.readtext(str(img_path))
    out = []
    for bbox, text, conf in res:
        text = text.strip()
        if not text:
            continue
        x_coords = [p[0] for p in bbox]
        y_coords = [p[1] for p in bbox]
        out.append(
            {
                "text": text,
                "confidence": float(conf),
                "bbox": {
                    "x": int(min(x_coords)),
                    "y": int(min(y_coords)),
                    "x_end": int(max(x_coords)),
                    "y_end": int(max(y_coords)),
                    "width": int(max(x_coords) - min(x_coords)),
                    "height": int(max(y_coords) - min(y_coords)),
                },
            }
        )
    print(out)
    return out


# Finish-type abbreviations that appear inside cells but are NOT color names
_FINISH_TOKENS = {
    "G",
    "SG",
    "M",
    "ME",
    "MG",
    "PA",
    "P",
    "A",
    "T",
    "S",
    "C",
    "N",
    "J",
    "M75%",
    "UK",
    "US",
    "J-II",
    "G-II",
}


def match_numbers_to_cells(text_entries, cells):
    """Match OCR-detected Mr. Hobby codes with grid cells."""
    matches = []
    seen_codes = set()

    for cell in cells:
        cx, cy = cell["x"], cell["y"]
        cw, ch = cell["width"], cell["height"]

        # Look for a number in the top-left 40% × 40% of the cell
        top_entries = [
            e
            for e in text_entries
            if cx <= e["bbox"]["x"] <= cx + cw * 0.50
            and cy <= e["bbox"]["y"] <= cy + ch * 0.40
        ]

        best_code = None
        for e in sorted(top_entries, key=lambda e: e["bbox"]["y"]):
            t = e["text"].strip()
            # Plain digits: 1–999
            m = re.match(r"^\[?(\d{1,3})\]?$", t)
            if m:
                best_code = f"C{m.group(1)}"
                break
            # Lowercase c-prefix  like "c301" or bracketed "c 301"
            m = re.match(r"^\[?[cC]\s?(\d{1,3})\]?$", t)
            if m:
                best_code = f"C{m.group(1)}"
                break

        if best_code and best_code not in seen_codes:
            seen_codes.add(best_code)
            matches.append(
                {
                    "code": best_code,
                    "hex": cell["hex"],
                    "rgb": cell["rgb"],
                    "cell": cell,
                }
            )

    return matches


def extract_color_names(text_entries, matches):
    """Extract color names from the bottom portion of each cell."""
    result = []

    for match in matches:
        cell = match["cell"]
        code = match["code"]
        cx, cy = cell["x"], cell["y"]
        cw, ch = cell["width"], cell["height"]

        # Name is in the bottom 40% of the cell (below the swatch)
        name_y_min = cy + ch * 0.58
        name_y_max = cy + ch * 0.95
        # Horizontally within the left 85% of the cell
        name_x_max = cx + cw * 0.85

        name_candidates = []
        for e in text_entries:
            tx = e["bbox"]["x"]
            ty = e["bbox"]["y"]
            t = e["text"].strip()

            if not (name_y_min <= ty <= name_y_max and cx <= tx <= name_x_max):
                continue
            # Skip numbers
            if re.match(r"^[cC]?\d+$", t):
                continue
            # Skip finish/short abbreviation tokens
            if t.upper() in _FINISH_TOKENS or len(t) <= 2:
                continue
            # Skip cross-reference patterns like "P H44", "A H44", "N44"
            if re.match(r"^[ACJNPTS][- ]?[HCSM]?\d", t.upper()):
                continue

            name_candidates.append({"text": t, "y": ty, "conf": e["confidence"]})

        if name_candidates:
            # Take the topmost entry (closest to top of bottom zone = first name line)
            name_candidates.sort(key=lambda x: (x["y"], -x["conf"]))
            name = name_candidates[0]["text"]
        else:
            name = "Unnamed"

        result.append({"code": code, "name": name, "hex": match["hex"]})

    return result


def normalize_color_name(name):
    if name and re.fullmatch(r"[A-Z]{1,3}", name):
        return "Unnamed"
    return name or "Unnamed"


def finalize_colors(colors):
    return [
        {
            "code": color.get("code", ""),
            "name": normalize_color_name(color.get("name", "")),
            "hex": color.get("hex", "#cccccc"),
        }
        for color in colors
    ]


def parse_mr_hobby_images(folder_path, output_json):
    """Parse all Mr. Hobby images in folder."""
    folder = Path(folder_path)

    reader = easyocr.Reader(["en"], gpu=False)
    all_colors = []

    for img_path in sorted(folder.glob("*.png")):
        print(f"\n{'='*70}")
        print(f"Processing {img_path.name}...")
        print(f"{'='*70}")

        with Image.open(img_path) as im:
            img_rgb = np.array(im.convert("RGB"))

        cells = find_grid_cells(img_rgb)
        print(f"✓ Detected {len(cells)} grid cells")

        text_entries = extract_ocr(img_path, reader)
        print(f"✓ OCR: {len(text_entries)} text entries")

        matches = match_numbers_to_cells(text_entries, cells)
        print(f"✓ Matched {len(matches)} codes to cells")

        colors = extract_color_names(text_entries, matches)

        # Print detailed color detection results
        print(f"\n{'Cell #':<8} {'Code':<8} {'Hex Color':<12} {'Color Name':<30}")
        print(f"{'-'*8} {'-'*8} {'-'*12} {'-'*30}")
        for idx, color in enumerate(colors, 1):
            code = color.get("code", "")
            hex_color = color.get("hex", "#cccccc")
            name = color.get("name", "Unnamed")
            print(f"{idx:<8} {code:<8} {hex_color:<12} {name:<30}")

        all_colors.extend(colors)
        print(f"\n✓ Extracted {len(colors)} colors from {img_path.name}")

    all_colors = finalize_colors(all_colors)

    # Print final summary
    print(f"\n{'='*70}")
    print(f"FINAL SUMMARY: {len(all_colors)} total colors parsed")
    print(f"{'='*70}\n")
    print(f"{'#':<6} {'Code':<8} {'Hex Color':<12} {'Color Name':<30}")
    print(f"{'-'*6} {'-'*8} {'-'*12} {'-'*30}")
    for idx, c in enumerate(all_colors, 1):
        code = c.get("code", "")
        name = c.get("name", "")
        hex_color = c.get("hex", "#cccccc")
        print(f"{idx:<6} {code:<8} {hex_color:<12} {name:<30}")
    print()

    formatted = {
        "brand": "Mr. Hobby",
        "brand_id": "mr_hobby",
        "source": "data/pack_mr_hobby.json",
        "count": len(all_colors),
        "colors": [
            {
                "code": c.get("code", ""),
                "name": normalize_color_name(c.get("name", "")),
                "hex": c.get("hex", "#cccccc"),
                "equivalents": [],
                "confidence": None,
            }
            for c in all_colors
        ],
    }

    output_json = Path(output_json)
    output_json.parent.mkdir(parents=True, exist_ok=True)
    output_json.write_text(json.dumps(formatted, indent=2, ensure_ascii=False))
    print(f"Wrote {len(all_colors)} colors to {output_json}")

    csv_path = output_json.parent / "pack_mr_hobby.csv"
    with csv_path.open("w", newline="") as fh:
        writer = csv.DictWriter(fh, fieldnames=["code", "name", "hex"])
        writer.writeheader()
        for c in all_colors:
            writer.writerow(
                {
                    "code": c.get("code", ""),
                    "name": normalize_color_name(c.get("name", "")),
                    "hex": c.get("hex", ""),
                }
            )
    print(f"Wrote CSV to {csv_path}")
    return all_colors


if __name__ == "__main__":
    source_folder = Path("source/mr_hobby")
    output = Path("data/pack_mr_hobby.json")
    parse_mr_hobby_images(source_folder, output)
