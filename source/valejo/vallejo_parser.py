#!/usr/bin/env python3
"""
Shared Vallejo parsing logic — used by each palette's __main__.py.
"""
from pathlib import Path
import json
import csv
from PIL import Image
import numpy as np
import easyocr
import cv2
import re


def rgb_to_hex(r, g, b):
    return "#{:02x}{:02x}{:02x}".format(int(r), int(g), int(b))


def find_color_swatches(image_array, min_swatch_size=20, max_swatch_size=200):
    """Detect color swatches using K-means clustering with size filtering."""
    swatches = []
    h, w, _ = image_array.shape

    scale = max(1, min(w // 400, h // 400))
    small = cv2.resize(
        image_array,
        (max(1, w // scale), max(1, h // scale)),
        interpolation=cv2.INTER_AREA,
    )

    Z = small.reshape((-1, 3)).astype(np.float32)
    K = min(15, max(3, len(np.unique(Z.reshape(-1, 3), axis=0))))
    criteria = (cv2.TERM_CRITERIA_EPS + cv2.TERM_CRITERIA_MAX_ITER, 10, 1.0)
    attempts = 4
    _, labels, centers = cv2.kmeans(
        Z, K, None, criteria, attempts, cv2.KMEANS_PP_CENTERS
    )
    centers = centers.astype(np.uint8)
    labels = labels.flatten().reshape(small.shape[0], small.shape[1])

    for i in range(K):
        mask = (labels == i).astype(np.uint8) * 255
        mask_big = cv2.resize(mask, (w, h), interpolation=cv2.INTER_NEAREST)
        contours, _ = cv2.findContours(
            mask_big, cv2.RETR_EXTERNAL, cv2.CHAIN_APPROX_SIMPLE
        )
        for cnt in contours:
            x, y, ww, hh = cv2.boundingRect(cnt)
            area = ww * hh

            if (
                ww >= min_swatch_size
                and hh >= min_swatch_size
                and ww <= max_swatch_size
                and hh <= max_swatch_size
                and area > (min_swatch_size * min_swatch_size)
            ):
                region = image_array[y : y + hh, x : x + ww]
                avg_color = region.reshape(-1, 3).mean(axis=0)
                hex_color = rgb_to_hex(*avg_color)

                r, g, b = avg_color
                brightness = (r + g + b) / 3
                is_white = r > 220 and g > 220 and b > 220
                is_black = r < 30 and g < 30 and b < 30
                is_gray = (
                    abs(r - g) < 10
                    and abs(g - b) < 10
                    and abs(r - b) < 10
                    and brightness > 100
                    and brightness < 200
                )

                if not (is_white or is_black or is_gray):
                    swatches.append(
                        {
                            "x": int(x),
                            "y": int(y),
                            "width": int(ww),
                            "height": int(hh),
                            "hex": hex_color,
                            "rgb": [int(c) for c in avg_color],
                        }
                    )

    seen = set()
    unique = []
    for s in swatches:
        key = (s["x"], s["y"], s["width"], s["height"])
        if key in seen:
            continue
        seen.add(key)
        unique.append(s)
    return unique


def process_image(image_path, reader):
    """Process a single image with OCR."""
    print(f"Processing: {image_path.name}")

    with Image.open(image_path) as image:
        image_array = np.array(image.convert("RGB"))

    h, w = image_array.shape[:2]

    swatches = find_color_swatches(image_array)
    print(f"  Found {len(swatches)} swatches")

    ocr_result = reader.readtext(str(image_path))
    text_entries = []

    for detection in ocr_result:
        (bbox, text, confidence) = detection
        bbox_array = np.array(bbox)
        x_min, x_max = bbox_array[:, 0].min(), bbox_array[:, 0].max()
        y_min, y_max = bbox_array[:, 1].min(), bbox_array[:, 1].max()

        text_entries.append(
            {
                "text": text.strip(),
                "confidence": float(confidence),
                "bbox": {
                    "x": float(x_min),
                    "y": float(y_min),
                    "width": float(x_max - x_min),
                    "height": float(y_max - y_min),
                },
            }
        )

    print(f"  Found {len(text_entries)} text entries")

    return {
        "filename": image_path.name,
        "width": w,
        "height": h,
        "text_entries": text_entries,
        "swatches": swatches,
    }


def extract_vallejo_codes_and_names(text_entries):
    """
    Extract Vallejo color codes and names from OCR text.

    Vallejo codes are typically in formats like:
    - 70.950 (Model Color)
    - 71.001 (Model Air)
    - 69.001 (Game Color)
    """
    colors = []

    sorted_entries = sorted(
        text_entries, key=lambda e: (e["bbox"]["y"], e["bbox"]["x"])
    )

    rows = []
    current_row = []
    last_y = None
    y_threshold = 30

    for entry in sorted_entries:
        y = entry["bbox"]["y"]
        if last_y is None or abs(y - last_y) <= y_threshold:
            current_row.append(entry)
            if last_y is not None:
                last_y = (last_y + y) / 2
            else:
                last_y = y
        else:
            if current_row:
                rows.append(current_row)
            current_row = [entry]
            last_y = y

    if current_row:
        rows.append(current_row)

    for row in rows:
        row_sorted = sorted(row, key=lambda e: e["bbox"]["x"])
        full_text = " ".join(e["text"] for e in row_sorted)

        code_pattern = r"(\d{2}[\.\s\-]?\d{3})"
        matches = list(re.finditer(code_pattern, full_text))

        for idx, match in enumerate(matches):
            raw_code = match.group(1)
            code = re.sub(r"[\s\-]", ".", raw_code)

            if not re.match(r"^\d{2}\.\d{3}$", code):
                continue

            code_end = match.end()

            if idx + 1 < len(matches):
                next_code_start = matches[idx + 1].start()
                name_text = full_text[code_end:next_code_start]
            else:
                name_text = full_text[code_end:]

            name_text = name_text.strip()
            name = name_text[:80] if name_text else "Unknown"
            name = re.sub(r"\s*\d+\s*$", "", name)
            name = re.sub(r"\s*[\[\]]\s*$", "", name)
            name = name.strip()

            if not name or len(name) < 2:
                name = "Unknown"

            colors.append({"code": code, "name": name})

    return colors


def match_colors_with_swatches(colors, swatches, text_entries):
    """Assign hex colors to extracted color codes by matching to nearest swatch."""
    for color in colors:
        best_swatch = None
        best_distance = float("inf")

        code_entry = None
        for entry in text_entries:
            if color["code"] in entry["text"]:
                code_entry = entry
                break

        if not code_entry:
            color["hex"] = "#cccccc"
            continue

        cx = code_entry["bbox"]["x"] + code_entry["bbox"]["width"] / 2
        cy = code_entry["bbox"]["y"] + code_entry["bbox"]["height"] / 2

        for swatch in swatches:
            sx = swatch["x"] + swatch["width"] / 2
            sy = swatch["y"] + swatch["height"] / 2

            dx = sx - cx
            dy = abs(sy - cy)

            if dx > 0:
                distance = dy * 2 + abs(dx) * 3
            else:
                distance = dy + abs(dx)

            if distance < best_distance:
                best_distance = distance
                best_swatch = swatch

        if best_swatch and best_distance < 1000:
            color["hex"] = best_swatch["hex"]
        else:
            color["hex"] = "#cccccc"


def parse_vallejo_images(folder_path, output_json, brand_label, brand_id):
    """Parse all Vallejo images in folder_path and write JSON + CSV to output_json."""
    folder = Path(folder_path)
    output_json = Path(output_json)

    if not folder.exists():
        print(f"Vallejo folder not found: {folder}")
        return []

    image_files = sorted(folder.glob("*.png"))
    if not image_files:
        print(f"No PNG files found in {folder}")
        return []

    print(f"Found {len(image_files)} image files")
    print("Loading OCR reader...")
    reader = easyocr.Reader(["en"], gpu=False)

    all_colors = []

    for image_path in image_files:
        try:
            result = process_image(image_path, reader)
            colors = extract_vallejo_codes_and_names(result["text_entries"])
            match_colors_with_swatches(
                colors, result["swatches"], result["text_entries"]
            )
            all_colors.extend(colors)
        except Exception as err:
            print(f"  Error: {err}")

    colors_list = sorted(all_colors, key=lambda c: c["code"])
    print(f"\nExtracted {len(colors_list)} colors")

    pack = {
        "brand": brand_label,
        "brand_id": brand_id,
        "source": str(output_json),
        "count": len(colors_list),
        "colors": colors_list,
    }

    output_json.parent.mkdir(parents=True, exist_ok=True)
    output_json.write_text(
        json.dumps(pack, indent=2, ensure_ascii=False), encoding="utf-8"
    )
    print(f"✓ Wrote {len(colors_list)} colors to {output_json}")

    csv_path = output_json.with_suffix(".csv")
    with csv_path.open("w", newline="", encoding="utf-8") as fh:
        writer = csv.DictWriter(fh, fieldnames=["code", "name", "hex"])
        writer.writeheader()
        for color in colors_list:
            writer.writerow(
                {
                    "code": color.get("code", ""),
                    "name": color.get("name", ""),
                    "hex": color.get("hex", ""),
                }
            )
    print(f"✓ Wrote CSV to {csv_path}")

    return colors_list
