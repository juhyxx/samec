#!/usr/bin/env python3
"""
Full Ammo parsing pipeline.

Produces `data/ammo_catalog.json` containing OCR results, detected swatches,
and matched swatch→text associations for each source image.
"""
from pathlib import Path
import importlib.util
import json
from PIL import Image
import numpy as np
import easyocr
import csv
import cv2


AMMO_FOLDER = Path("source/ammo")
OUT_FOLDER = Path("data")
OUT_FILE = OUT_FOLDER / "ammo_catalog.json"

# Fraction of image width to sample for left-column color swatch (configurable).
TABLE_LEFT_POS = 884


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
                avg_color = region.reshape(-1, 3).mean(axis=0)
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


def _sample_left_column(image_array, left_x=TABLE_LEFT_POS, step=4):
    """Replace K-means with direct left-column pixel sampling for table images.

    Scans every `step` rows at `left_x_frac * image_width` and returns one
    lightweight swatch per band. Near-white colours are preserved correctly.
    """
    h, w, _ = image_array.shape
    lx = int(left_x)
    swatches = []
    for y in range(0, h - step + 1, step):
        region = image_array[y : y + step, max(0, lx - 2) : min(w, lx + 3)]
        if region.size == 0:
            continue
        avg = region.reshape(-1, 3).mean(axis=0)
        swatches.append(
            {
                "x": lx,
                "y": y,
                "width": 5,
                "height": step,
                "hex": rgb_to_hex(int(avg[0]), int(avg[1]), int(avg[2])),
                "rgb": [int(avg[0]), int(avg[1]), int(avg[2])],
            }
        )
    return swatches


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
    swatches = _sample_left_column(img_array)
    print(f"  Sampled {len(swatches)} left-column pixels")
    # Format as matches directly — parse_rows.py only uses m.get("swatch")
    matches = [{"swatch": s} for s in swatches]
    return {
        "filename": image_path.name,
        "width": img.width,
        "height": img.height,
        "text_entries": text_entries,
        "swatches": swatches,
        "matches": matches,
    }


def load_rows_parser():
    """Load the legacy Ammo row parser from source/common."""
    parser_file = Path(__file__).resolve().parent.parent / "common/parse_rows.py"
    spec = importlib.util.spec_from_file_location("ammo_parse_rows", parser_file)
    if spec is None or spec.loader is None:
        raise ImportError(f"Unable to load rows parser from {parser_file}")

    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    return module


def write_catalog(all_results, folder_path, catalog_file):
    """Persist the OCR catalog and CSV used by the legacy row parser."""
    output = {
        "source": str(folder_path),
        "files_processed": len(all_results),
        "images": all_results,
    }
    catalog_file.parent.mkdir(parents=True, exist_ok=True)
    catalog_file.write_text(json.dumps(output, indent=2), encoding="utf-8")
    print(f"\n✓ Processed {len(all_results)} files")
    print(f"✓ Saved to: {catalog_file}")

    csv_path = catalog_file.with_suffix(".csv")
    with csv_path.open("w", newline="", encoding="utf-8") as fh:
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


def build_colors_from_rows(rows):
    """Convert parsed Ammo rows into the shared color list shape."""
    colors = []
    seen_codes = set()

    for row in rows:
        code = row.get("reference")
        if not code or code in seen_codes:
            continue

        seen_codes.add(code)
        hex_color = row.get("resolved_hex") or row.get("hex") or "#cccccc"
        if hex_color and not hex_color.startswith("#"):
            hex_color = f"#{hex_color}"

        colors.append(
            {
                "code": code,
                "name": row.get("name") or "Unnamed",
                "hex": hex_color,
                "equivalents": row.get("equivalents", []),
                "confidence": row.get("confidence"),
            }
        )

    return colors


def parse_ammo_images(folder_path, output_json):
    """Run the legacy Ammo OCR + row parser flow and return frontend colors."""
    folder = Path(folder_path)
    output_json = Path(output_json)

    if not folder.exists():
        print(f"Ammo folder not found: {folder}")
        return []

    image_files = sorted(folder.glob("*.png"))
    if not image_files:
        print("No PNG files found")
        return []

    print(f"Found {len(image_files)} image files")
    print("Loading OCR reader...")
    reader = easyocr.Reader(["en"], gpu=False)
    all_results = []

    for image_path in image_files:
        try:
            all_results.append(process_image(image_path, reader))
        except Exception as err:
            print(f"  Error: {err}")

    if not all_results:
        return []

    if output_json.parent.name == "results":
        data_dir = output_json.parent.parent
    else:
        data_dir = Path("data")
    catalog_file = data_dir / "ammo_catalog.json"
    rows_file = data_dir / "ammo_rows.json"
    rows_csv_file = data_dir / "ammo_rows.csv"

    write_catalog(all_results, folder, catalog_file)

    rows_parser = load_rows_parser()
    rows_parser.IN_FILE = catalog_file
    rows_parser.OUT_JSON = rows_file
    rows_parser.OUT_CSV = rows_csv_file
    rows_parser.parse_catalog()

    rows = json.loads(rows_file.read_text(encoding="utf-8"))
    colors = build_colors_from_rows(rows)

    output_json.parent.mkdir(parents=True, exist_ok=True)
    output_json.write_text(
        json.dumps(colors, indent=2, ensure_ascii=False),
        encoding="utf-8",
    )
    print(f"✓ Wrote {len(colors)} colors to {output_json}")

    csv_path = output_json.parent / "pack_ammo.csv"
    with csv_path.open("w", newline="", encoding="utf-8") as fh:
        writer = csv.DictWriter(
            fh,
            fieldnames=["code", "name", "hex", "equivalents", "confidence"],
        )
        writer.writeheader()
        for color in colors:
            writer.writerow(
                {
                    "code": color.get("code", ""),
                    "name": color.get("name", ""),
                    "hex": color.get("hex", ""),
                    "equivalents": "; ".join(
                        f"{item.get('brand')}:{item.get('code')}"
                        for item in color.get("equivalents", [])
                    ),
                    "confidence": color.get("confidence", ""),
                }
            )
    print(f"✓ Wrote CSV to {csv_path}")

    return colors


def main():
    parse_ammo_images(AMMO_FOLDER, OUT_FOLDER / "pack_ammo.json")


if __name__ == "__main__":
    print("Starting Ammo parsing pipeline...")
    main()
