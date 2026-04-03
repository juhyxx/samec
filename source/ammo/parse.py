#!/usr/bin/env python3
"""
Combined OCR + parse for Ammo by Mig color charts.
Runs OCR on PNGs in `source/ammo` then extracts recognized color codes.
Writes parsed results to `data/ammo_by_mig_parsed.json`.
"""
from pathlib import Path
import json
import re
from PIL import Image
import easyocr

SRC = Path("source/ammo")
#!/usr/bin/env python3
"""
Full Ammo parsing pipeline merged from `source/common/extract_catalog.py`.

Produces `data/ammo_catalog.json` containing OCR results, detected swatches,
and matched swatch→text associations for each source image.
"""
import json
from pathlib import Path
from PIL import Image
import numpy as np
import easyocr
from collections import defaultdict
import re
import cv2
import csv


AMMO_FOLDER = Path("source/ammo")
OUT_FOLDER = Path("data")
OUT_FILE = OUT_FOLDER / "ammo_catalog.json"


def rgb_to_hex(r, g, b):
    return "#{:02x}{:02x}{:02x}".format(int(r), int(g), int(b))


def hex_to_rgb(hex_str):
    h = hex_str.lstrip("#")
    return tuple(int(h[i : i + 2], 16) for i in (0, 2, 4))


def find_color_swatches(image_array, min_swatch_size=15):
    swatches = []
    h, w, _ = image_array.shape

    scale = max(1, min(w // 400, h // 400))
    small = cv2.resize(
        image_array,
        (max(1, w // scale), max(1, h // scale)),
        interpolation=cv2.INTER_AREA,
    )

    Z = small.reshape((-1, 3)).astype(np.float32)
    K = min(8, max(2, len(np.unique(Z.reshape(-1, 3), axis=0))))
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
            if (
                ww >= min_swatch_size
                and hh >= min_swatch_size
                and ww * hh > (min_swatch_size * min_swatch_size)
            ):
                region = image_array[y : y + hh, x : x + ww]
                avg_color = region.reshape(2, 3).mean(axis=0)
                hex_color = rgb_to_hex(*avg_color)
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


def extract_ocr_text(image_path, reader):
    result = reader.readtext(str(image_path))
    entries = []
    for bbox, text, conf in result:
        x_coords = [p[0] for p in bbox]
        y_coords = [p[1] for p in bbox]
        x_min, x_max = min(x_coords), max(x_coords)
        y_min, y_max = min(y_coords), max(y_coords)
        entries.append(
            {
                "text": text,
                "confidence": float(conf),
                "bbox": {
                    "x": int(x_min),
                    "y": int(y_min),
                    "x_end": int(x_max),
                    "y_end": int(y_max),
                    "width": int(x_max - x_min),
                    "height": int(y_max - y_min),
                },
            }
        )
    return entries


def match_swatches_to_text(swatches, text_entries):
    results = []
    for swatch in swatches:
        nearby_texts = []
        swatch_cx = swatch["x"] + swatch["width"] / 2
        swatch_cy = swatch["y"] + swatch["height"] / 2
        for text_entry in text_entries:
            text_cx = text_entry["bbox"]["x"] + text_entry["bbox"]["width"] / 2
            text_cy = text_entry["bbox"]["y"] + text_entry["bbox"]["height"] / 2
            distance = ((swatch_cx - text_cx) ** 2 + (swatch_cy - text_cy) ** 2) ** 0.5
            if distance < 150:
                nearby_texts.append(
                    {
                        "text": text_entry["text"],
                        "confidence": text_entry["confidence"],
                        "distance": distance,
                    }
                )
        nearby_texts.sort(key=lambda x: (x["distance"], -x["confidence"]))
        results.append({"swatch": swatch, "nearby_text": nearby_texts})
    return results


def process_image(image_path, reader):
    print(f"Processing: {image_path.name}")
    img = Image.open(image_path)
    if img.mode != "RGB":
        img = img.convert("RGB")
    img_array = np.array(img)
    text_entries = extract_ocr_text(image_path, reader)
    print(f"  Found {len(text_entries)} text entries")
    swatches = find_color_swatches(img_array)
    print(f"  Found {len(swatches)} potential color swatches")
    matches = match_swatches_to_text(swatches, text_entries)
    return {
        "filename": image_path.name,
        "width": img.width,
        "height": img.height,
        "text_entries": text_entries,
        "swatches": swatches,
        "matches": matches,
    }


def main():
    if not AMMO_FOLDER.exists():
        print(f"Ammo folder not found: {AMMO_FOLDER}")
        return
    image_files = sorted(AMMO_FOLDER.glob("*.png"))
    if not image_files:
        print("No PNG files found")
        return
    print(f"Found {len(image_files)} image files")
    print("Loading OCR reader...")
    reader = easyocr.Reader(["en"], gpu=False)
    all_results = []
    for image_path in image_files:
        try:
            result = process_image(image_path, reader)
            all_results.append(result)
        except Exception as e:
            print(f"  Error: {e}")
    output = {
        "source": str(AMMO_FOLDER),
        "files_processed": len(all_results),
        "images": all_results,
    }
    OUT_FOLDER.mkdir(parents=True, exist_ok=True)
    OUT_FILE.write_text(json.dumps(output, indent=2))
    print(f"\n✓ Processed {len(all_results)} files")
    print(f"✓ Saved to: {OUT_FILE}")

    # Generate CSV for data checking
    csv_path = OUT_FOLDER / "ammo_catalog.csv"
    with csv_path.open("w", newline="") as fh:
        writer = csv.DictWriter(fh, fieldnames=["filename", "text", "confidence"])
        writer.writeheader()
        for img in all_results:
            for entry in img.get("text_entries", []):
                writer.writerow(
                    {
                        "filename": img["filename"],
                        "text": entry["text"],
                        "confidence": entry["confidence"],
                    }
                )
    print(f"✓ CSV saved to: {csv_path}")


if __name__ == "__main__":
    main()
