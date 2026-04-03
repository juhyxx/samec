#!/usr/bin/env python3
"""
Parse Mr. Hobby color chart images.
Grid layout with:
- Number in black box (add "C" prefix)
- Color sample
- Color name in bottom left
"""

from pathlib import Path
import json
from PIL import Image
import numpy as np
import easyocr
import cv2
import re
import csv


def rgb_to_hex(arr):
    """Convert RGB array to hex color."""
    return "#{:02x}{:02x}{:02x}".format(int(arr[0]), int(arr[1]), int(arr[2]))


def find_color_grid_cells(image_array, cell_min_size=30):
    """Detect grid cells and extract color from each."""
    h, w, _ = image_array.shape

    # Use k-means clustering to identify distinct regions
    proc = cv2.cvtColor(image_array, cv2.COLOR_RGB2LAB)
    proc = cv2.GaussianBlur(proc, (7, 7), 0)

    Z = proc.reshape((-1, 3)).astype(np.float32)
    K = 16  # number of clusters for grid detection
    criteria = (cv2.TERM_CRITERIA_EPS + cv2.TERM_CRITERIA_MAX_ITER, 10, 1.0)
    _, labels, centers = cv2.kmeans(Z, K, None, criteria, 3, cv2.KMEANS_PP_CENTERS)

    labels = labels.reshape(h, w).astype(np.uint8)

    cells = []
    for i in range(K):
        mask = (labels == i).astype("uint8") * 255
        contours, _ = cv2.findContours(mask, cv2.RETR_EXTERNAL, cv2.CHAIN_APPROX_SIMPLE)

        for cnt in contours:
            x, y, ww, hh = cv2.boundingRect(cnt)

            if ww >= cell_min_size and hh >= cell_min_size:
                # Extract the color from the center of the cell
                cy_center = y + hh // 2
                cx_center = x + ww // 2

                # Get a small region around center
                sy, ey = max(0, y + hh // 3), min(h, y + 2 * hh // 3)
                sx, ex = max(0, x + ww // 3), min(w, x + 2 * ww // 3)

                region = image_array[sy:ey, sx:ex]
                if region.size > 0:
                    avg_color = region.reshape(-1, 3).mean(axis=0)
                    cells.append(
                        {
                            "x": int(x),
                            "y": int(y),
                            "width": int(ww),
                            "height": int(hh),
                            "rgb": [
                                int(avg_color[0]),
                                int(avg_color[1]),
                                int(avg_color[2]),
                            ],
                            "hex": rgb_to_hex(avg_color),
                        }
                    )

    return cells


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

    return out


def match_numbers_to_cells(text_entries, cells):
    """Match OCR-detected numbers with grid cells."""
    matches = []

    for text_entry in text_entries:
        # Look for numbers (color codes)
        num_match = re.match(r"^(\d{1,3})$", text_entry["text"].strip())
        if not num_match:
            continue

        number = num_match.group(1)
        text_y = text_entry["bbox"]["y"]
        text_x = text_entry["bbox"]["x"]

        # Find nearest cell (cell above/containing this text)
        best_cell = None
        best_dist = None

        for cell in cells:
            # Cell is above text, with similar x center
            cell_cx = cell["x"] + cell["width"] // 2
            text_cx = text_x + text_entry["bbox"]["width"] // 2

            x_dist = abs(cell_cx - text_cx)
            y_dist = abs((cell["y"] + cell["height"]) - text_y)

            dist = x_dist + y_dist * 0.5

            if best_dist is None or dist < best_dist:
                if y_dist < 50:  # text should be near cell bottom
                    best_dist = dist
                    best_cell = cell

        if best_cell:
            matches.append(
                {
                    "code": f"C{number}",
                    "hex": best_cell["hex"],
                    "rgb": best_cell["rgb"],
                    "cell": best_cell,
                    "text_entry": text_entry,
                }
            )

    return matches


def extract_color_names(text_entries, cells, matches):
    """Extract color names near color codes."""
    result = []

    for match in matches:
        # Find text entries near this cell (below or to the right)
        cell = match["cell"]
        code = match["code"]
        hex_color = match["hex"]

        # Look for name text below the cell
        name_texts = []
        for text_entry in text_entries:
            t = text_entry["text"].strip()
            # Skip if it's a number
            if re.match(r"^(\d+)$", t):
                continue

            text_y = text_entry["bbox"]["y"]
            text_x = text_entry["bbox"]["x"]
            cell_bottom = cell["y"] + cell["height"]
            cell_cx = cell["x"] + cell["width"] // 2

            # Text should be below cell
            if text_y > cell_bottom - 10 and text_y < cell_bottom + 40:
                x_dist = abs(text_x - cell_cx)
                if x_dist < 60:
                    name_texts.append(
                        {
                            "text": t,
                            "confidence": text_entry["confidence"],
                            "x_dist": x_dist,
                        }
                    )

        # Use closest/highest confidence text as name
        if name_texts:
            name_texts.sort(key=lambda x: (-x["confidence"], x["x_dist"]))
            name = name_texts[0]["text"]
        else:
            name = "Unnamed"
        # If OCR picked very short uppercase abbreviations (e.g. 'G', 'ME', 'SG'),
        # treat them as missing names because they look like layout artifacts.
        if re.fullmatch(r"[A-Z]{1,3}", name):
            name = "Unnamed"
        result.append({"code": code, "name": name, "hex": hex_color})

    return result


def parse_mr_hobby_images(folder_path, output_json):
    """Parse all Mr. Hobby images in folder."""
    folder = Path(folder_path)

    reader = easyocr.Reader(["en"], gpu=False)
    all_colors = []

    for img_path in sorted(folder.glob("*.png")):
        print(f"Processing {img_path.name}...")

        with Image.open(img_path) as im:
            img_rgb = np.array(im.convert("RGB"))

        # Extract text and cells
        text_entries = extract_ocr(img_path, reader)
        cells = find_color_grid_cells(img_rgb)

        # Match numbers to cells
        matches = match_numbers_to_cells(text_entries, cells)

        # Extract names
        colors = extract_color_names(text_entries, cells, matches)

        all_colors.extend(colors)
        print(f"  Found {len(colors)} colors")

    # Format for frontend
    formatted = {
        "brand": "Mr. Hobby",
        "brand_id": "mr_hobby",
        "source": "data/results/pack_mr_hobby.json",
        "count": len(all_colors),
        "colors": [
            {
                "code": c.get("code", ""),
                "name": c.get("name", "Unnamed"),
                "hex": c.get("hex", "#cccccc"),
                "equivalents": [],
                "confidence": None,
            }
            for c in all_colors
        ],
    }

    # Write results
    output_json.parent.mkdir(parents=True, exist_ok=True)
    output_json.write_text(json.dumps(formatted, indent=2, ensure_ascii=False))
    print(f"Wrote {len(all_colors)} colors to {output_json}")

    # Generate CSV
    csv_path = output_json.parent / "pack_mr_hobby.csv"
    with csv_path.open("w", newline="") as fh:
        writer = csv.DictWriter(fh, fieldnames=["code", "name", "hex"])
        writer.writeheader()
        for c in all_colors:
            writer.writerow(
                {
                    "code": c.get("code", ""),
                    "name": c.get("name", ""),
                    "hex": c.get("hex", ""),
                }
            )
    print(f"Wrote CSV to {csv_path}")
    return all_colors


if __name__ == "__main__":
    source_folder = Path("source/mr_hobby")
    output = Path("data/results/pack_mr_hobby.json")

    colors = parse_mr_hobby_images(source_folder, output)
