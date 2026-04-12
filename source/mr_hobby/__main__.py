#!/usr/bin/env python3
"""
Cell detection for Mr. Hobby Mr. Color chart images.
Detects grid layout and exports preview files for each cell.
"""

from pathlib import Path
from PIL import Image
import numpy as np
import cv2
import easyocr
import re
import json
import csv


def find_grid_cells(image_array, cell_width=231, cell_height=162, tolerance=20):
    """Detect rectangular cells with fixed size (231 x 162).

    Uses contour detection to find boxes matching the target dimensions.
    Returns a list of {x, y, width, height} dicts sorted row-first.
    """
    h, w = image_array.shape[:2]
    gray = cv2.cvtColor(image_array, cv2.COLOR_RGB2GRAY)

    # Detect edges
    edges = cv2.Canny(gray, 50, 150)

    # Dilate edges to connect broken lines
    kernel = cv2.getStructuringElement(cv2.MORPH_RECT, (5, 5))
    dilated = cv2.dilate(edges, kernel, iterations=2)

    # Find contours
    contours, _ = cv2.findContours(dilated, cv2.RETR_TREE, cv2.CHAIN_APPROX_SIMPLE)

    cells = []

    for contour in contours:
        # Approximate contour to polygon
        epsilon = 0.02 * cv2.arcLength(contour, True)
        approx = cv2.approxPolyDP(contour, epsilon, True)

        # Check if it's a rectangle (4 vertices)
        if len(approx) == 4:
            x, y, cw, ch = cv2.boundingRect(approx)

            # Check if size matches target (with tolerance)
            width_match = abs(cw - cell_width) <= tolerance
            height_match = abs(ch - cell_height) <= tolerance

            if width_match and height_match:
                cells.append(
                    {
                        "x": int(x),
                        "y": int(y),
                        "width": int(cw),
                        "height": int(ch),
                    }
                )

    return sorted(cells, key=lambda c: (c["y"], c["x"]))


def extract_cell_code(image_array, cell, reader):
    """Extract code number from the black square in the cell [21, 12] with size 44x44."""
    cell_x = cell["x"]
    cell_y = cell["y"]

    # Code square position and size within the cell
    code_x = cell_x + 21
    code_y = cell_y + 12
    code_w = 44
    code_h = 44

    # Crop the code region
    code_region = image_array[code_y : code_y + code_h, code_x : code_x + code_w]

    # Use OCR to extract text
    results = reader.readtext(code_region, detail=1)

    code = None
    for bbox, text, confidence in results:
        # Clean and parse the text
        text = text.strip()
        # Try to extract just the number part
        match = re.search(r"\d+", text)
        if match:
            number = match.group()
            code = f"C{number}"
            break

    return code


def extract_cell_color(image_array, cell):
    """Extract color from the color swatch at position [150, 50] in the cell."""
    cell_x = cell["x"]
    cell_y = cell["y"]

    # Swatch position within the cell
    swatch_x = cell_x + 150
    swatch_y = cell_y + 50

    # Read pixel at that position (R, G, B)
    pixel = image_array[swatch_y, swatch_x]
    rgb = pixel[:3]  # Get only RGB, ignore alpha if present

    # Convert to hex
    hex_color = "#{:02x}{:02x}{:02x}".format(int(rgb[0]), int(rgb[1]), int(rgb[2]))

    return hex_color, rgb


def extract_cell_name(image_array, cell, reader, code=None):
    """Extract color name from the text area at position [10, 112] size 135x51.

    Uses image upscaling (super-resolution) and preprocessing to improve OCR
    accuracy on condensed fonts. May span two rows.

    For code 351, the name box is shifted 10px to the right.
    """
    cell_x = cell["x"]
    cell_y = cell["y"]

    # Name area position and size within the cell
    # For code 351, move 10px to the right
    name_x_offset = 20 if code == "C351" else 10
    name_x = cell_x + name_x_offset
    name_y = cell_y + 112
    name_w = 135  # 15 pixels wider
    name_h = 51

    # Crop the name region
    name_region = image_array[name_y : name_y + name_h, name_x : name_x + name_w]

    # Upscale the image 3x to improve OCR accuracy on condensed fonts
    upscaled = cv2.resize(name_region, None, fx=3, fy=3, interpolation=cv2.INTER_CUBIC)

    # Convert to grayscale for preprocessing
    gray = cv2.cvtColor(upscaled, cv2.COLOR_RGB2GRAY)

    # Apply contrast enhancement (CLAHE - Contrast Limited Adaptive Histogram Equalization)
    clahe = cv2.createCLAHE(clipLimit=2.0, tileGridSize=(8, 8))
    enhanced = clahe.apply(gray)

    # Convert back to RGB for OCR
    enhanced_rgb = cv2.cvtColor(enhanced, cv2.COLOR_GRAY2RGB)

    # Use OCR to extract text from enhanced region
    results = reader.readtext(enhanced_rgb, detail=1)

    # Collect all text found in the region
    name_parts = []
    for bbox, text, confidence in results:
        text = text.strip()
        if text:
            name_parts.append(text)

    # Join all parts (may span two rows)
    name = " ".join(name_parts) if name_parts else "Unnamed"

    return name


def export_cell_previews(image_array, cells, color_data, output_folder, image_name):
    """Export preview images for each detected cell with parsing regions highlighted.

    Highlights:
    - Code region (red): [21, 12] size 44x44
    - Color swatch (blue): [150, 50] - small region around the pixel
    - Name region (green): [10, 112] size 135x51 ([20, 112] for code C351)

    Args:
        image_array: The image as numpy array
        cells: List of detected cell dictionaries
        color_data: List of color dicts with 'code' and 'name' keys
        output_folder: Path to save preview images
        image_name: Stem of the original image filename
    """
    output_path = Path(output_folder)
    output_path.mkdir(parents=True, exist_ok=True)

    for idx, cell in enumerate(cells):
        x = cell["x"]
        y = cell["y"]
        w = cell["width"]
        h = cell["height"]

        # Crop the cell from the image
        crop = image_array[y : y + h, x : x + w].copy()

        # Draw parsing regions on the crop
        # Code region [21, 12] size 44x44 - RED
        code_x, code_y = 21, 12
        code_w, code_h = 44, 44
        cv2.rectangle(
            crop, (code_x, code_y), (code_x + code_w, code_y + code_h), (0, 0, 255), 2
        )  # Red
        cv2.putText(
            crop,
            "CODE",
            (code_x + 5, code_y - 5),
            cv2.FONT_HERSHEY_SIMPLEX,
            0.4,
            (0, 0, 255),
            1,
        )

        # Color swatch [150, 50] - BLUE (show as small square around pixel)
        swatch_x, swatch_y = 150, 50
        swatch_size = 15
        cv2.rectangle(
            crop,
            (swatch_x - swatch_size, swatch_y - swatch_size),
            (swatch_x + swatch_size, swatch_y + swatch_size),
            (255, 0, 0),
            2,
        )  # Blue
        cv2.putText(
            crop,
            "COLOR",
            (swatch_x - 20, swatch_y - swatch_size - 5),
            cv2.FONT_HERSHEY_SIMPLEX,
            0.4,
            (255, 0, 0),
            1,
        )

        # Name region [10, 112] size 135x51 - GREEN (20, 112 for code 351)
        if idx < len(color_data) and color_data[idx].get("code") == "C351":
            name_x, name_y = 20, 112  # 10px right for C351
        else:
            name_x, name_y = 10, 112
        name_w, name_h = 135, 51  # 15 pixels wider
        cv2.rectangle(
            crop, (name_x, name_y), (name_x + name_w, name_y + name_h), (0, 255, 0), 2
        )  # Green
        cv2.putText(
            crop,
            "NAME",
            (name_x + 5, name_y - 5),
            cv2.FONT_HERSHEY_SIMPLEX,
            0.4,
            (0, 255, 0),
            1,
        )

        # Convert to PIL and save with color code only
        crop_img = Image.fromarray(crop)

        # Create filename from color code only
        if idx < len(color_data):
            color_info = color_data[idx]
            code = color_info.get("code", f"C{idx}").replace("/", "_").replace(" ", "_")
            filename = output_path / f"{code}.png"
        else:
            filename = output_path / f"{image_name}_cell_{idx:04d}.png"

        crop_img.save(filename)

    return len(cells)


def extract_equivalents_from_name(name):
    """Extract standard codes from color name (FS, RAL, RLM, BS)."""
    if not name:
        return []
    equivs = []
    text = name.upper()

    # FS codes (Federal Standard)
    for m in re.finditer(r"FS[-\s]?(\d{5})", text):
        code = f"FS {m.group(1)}"
        equivs.append({"brand": "Federal Standard", "code": code})

    # RAL codes
    for m in re.finditer(r"RAL[-\s]?(\d{4})", text):
        code = f"RAL {m.group(1)}"
        equivs.append({"brand": "RAL", "code": code})

    # RLM codes
    for m in re.finditer(r"RLM[-\s]?(\d{2,3})", text):
        code = f"RLM {m.group(1)}"
        equivs.append({"brand": "RLM", "code": code})

    # BS codes (British Standard)
    for m in re.finditer(r"BS[-\s]?(\d{3}C?(?:/\d{3})?)", text):
        code = f"BS {m.group(1)}"
        equivs.append({"brand": "British Standard", "code": code})

    return equivs


def export_pack_files(colors, output_folder="data"):
    """Export colors to JSON and CSV pack files."""
    output_path = Path(output_folder)
    output_path.mkdir(parents=True, exist_ok=True)

    # Extract equivalents from color names (FS, RAL, RLM codes)
    # Export JSON
    json_file = output_path / "pack_mr_hobby.json"
    formatted_json = {
        "brand": "Mr. Hobby",
        "brand_id": "mr_hobby",
        "source": "data/pack_mr_hobby.json",
        "count": len(colors),
        "colors": [
            {
                "code": c["code"],
                "name": c["name"],
                "hex": c["hex"],
                "equivalents": c.get("equivalents", []),
                "confidence": None,
            }
            for c in colors
        ],
    }
    json_file.write_text(json.dumps(formatted_json, indent=2, ensure_ascii=False))
    print(f"✓ Exported {len(colors)} colors to {json_file}")

    # Export CSV
    csv_file = output_path / "pack_mr_hobby.csv"
    with csv_file.open("w", newline="") as fh:
        writer = csv.DictWriter(fh, fieldnames=["code", "name", "hex"])
        writer.writeheader()
        for c in colors:
            writer.writerow({"code": c["code"], "name": c["name"], "hex": c["hex"]})
    print(f"✓ Exported {len(colors)} colors to {csv_file}")


def process_mr_hobby_images(folder_path, output_folder_or_file):
    """Process all Mr. Hobby images: detect cells, extract codes, and export previews and pack files.

    Returns a list of color dictionaries with code, name, and hex.
    """
    folder = Path(folder_path)
    output_path = Path(output_folder_or_file)

    # If output is a .json file, use its parent directory for previews
    if output_path.suffix == ".json":
        preview_folder = output_path.parent
    else:
        preview_folder = output_path

    print(f"\nProcessing Mr. Hobby images from: {folder}")
    print(f"Exporting previews to: {preview_folder}")
    print(f"{'='*70}\n")

    # Initialize OCR reader
    reader = easyocr.Reader(["en"], gpu=False)

    total_cells = 0
    all_colors = []  # Collect all colors for pack file

    for img_path in sorted(folder.glob("*.png")):
        print(f"Processing {img_path.name}...")

        # Load image
        with Image.open(img_path) as im:
            img_rgb = np.array(im.convert("RGB"))

        # Detect cells
        cells = find_grid_cells(img_rgb)
        print(f"  ✓ Detected {len(cells)} cells\n")

        # Extract all color data first (for preview naming)
        cell_colors = []
        for idx, cell in enumerate(cells):
            code = extract_cell_code(img_rgb, cell, reader)
            hex_color, rgb = extract_cell_color(img_rgb, cell)
            name = extract_cell_name(img_rgb, cell, reader, code)
            code_str = code if code else "N/A"
            print(
                f"  {idx:<5} {code_str:<8} {hex_color:<10} {name:<30} {cell['x']:<6} {cell['y']:<6}"
            )

            # Collect color data for pack file and preview naming
            if code:
                color_dict = {
                    "code": code,
                    "name": name,
                    "hex": hex_color,
                    "equivalents": extract_equivalents_from_name(name),
                }
                all_colors.append(color_dict)
                cell_colors.append(color_dict)
            else:
                cell_colors.append(
                    {
                        "code": "N/A",
                        "name": name,
                        "hex": hex_color,
                    }
                )
        print()

        # Export previews
        num_exported = export_cell_previews(
            img_rgb, cells, cell_colors, preview_folder, img_path.stem
        )
        print(f"  ✓ Exported {num_exported} preview files\n")

        total_cells += len(cells)

    # Export pack files (JSON and CSV) to data folder
    print(f"\n{'='*70}")
    export_pack_files(all_colors, output_path.parent)
    print(f"{'='*70}\n")

    print(f"TOTAL: {total_cells} cells detected and previewed")
    print()

    # Return colors for pipeline processing
    return all_colors


if __name__ == "__main__":
    source_folder = Path("source/mr_hobby")
    output_folder = Path("data/mr_hobby_previews")
    colors = process_mr_hobby_images(source_folder, output_folder)
