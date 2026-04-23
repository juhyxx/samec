#!/usr/bin/env python3
"""
Cell detection for Mr. Color Mr. Color chart images.
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


# ── Region definitions (relative to cell top-left) ─────────────────────────
# Adjust these to tune where OCR reads the code number.
CODE_STD = (20, 12, 44, 44)  # (x, y, w, h) standard position (files 01/02)
CODE_ALT = (20, 10, 53, 44)  # (x, y, w, h) alt-box cells in file 03
# ─────────────────────────────────────────────────────────────────────────────

# Characters commonly misread as other characters inside the code black square.
# Only include mappings where the letter is visually unambiguous in this context
# (white digits on black background). Avoid S→5, G→6, E→3 etc. which can
# corrupt digits that appear already correct at later positions.
_OCR_CHAR_MAP = {
    "b": "3",  # '3' misread as 'b' — confirmed by 'b26'→'326' fix
    "B": "3",  # same, uppercase variant
    "J": "3",  # '3' misread as 'J' — confirmed by 'J60'→'360'
    "j": "3",
    "I": "1",  # '1' misread as 'I' — confirmed by 'I07'→'107', 'IOO'→'100'
    "l": "1",
    "L": "1",
    "O": "0",  # '0' misread as 'O' — confirmed by 'IOO'→'100'
    "o": "0",
    "D": "0",
    "Z": "2",
    "z": "2",
}

# Corrections applied ONLY to file 03 (ALT path).
# C114→C14 is intentionally absent — C114 is a real code in file 03.
_ALT_CORRECTIONS = {
    "C764": "C364",  # '3' misread as '7'
    "C621": "C521",  # '5' misread as '6',
    "C14": "C114",
}


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


def normalize_code(code):
    """Normalize Mr. Color color codes, fixing known OCR errors."""
    if not code:
        return code

    # Known OCR error corrections (STD region only — do NOT apply to ALT/file 03)
    # C1261 is actually C126 (OCR misread the trailing "1")
    corrections = {
        "C1261": "C126",
    }

    return corrections.get(code, code)


def extract_cell_code(image_array, cell, reader, allow_alt=True):
    """Extract code number from the black square in the cell.

    Standard position: [21, 12] with size 44x44
    For codes >= 340: position shifts to [30, 12] with size 44x44

    allow_alt: if False, skip the ALT region entirely (use for images that
               only contain low codes, e.g. the first chart page).
    """
    cell_x = cell["x"]
    cell_y = cell["y"]

    def extract_from_region(image_array, code_x, code_y, code_w, code_h):
        """Extract code from a specific region with preprocessing."""
        # Crop the code region
        code_region = image_array[code_y : code_y + code_h, code_x : code_x + code_w]

        # Upscale the region for better OCR (white text on black - no color ops needed)
        upscaled = cv2.resize(
            code_region, None, fx=2, fy=2, interpolation=cv2.INTER_CUBIC
        )

        candidates = []
        results = reader.readtext(upscaled, detail=1)

        # Debug: show raw OCR results
        print(".", end="")

        # Sort results left-to-right by bbox x so concatenation is in reading order
        results_sorted = sorted(results, key=lambda r: min(pt[0] for pt in r[0]))

        # Collect digit sequences sorted left-to-right
        all_segment_digits = []
        for bbox, text, confidence in results_sorted:
            text = text.strip().upper()
            # Apply known OCR char→digit substitutions (b→3, J→3, I→1, etc.)
            # This recovers leading digits misread as similar-looking letters, e.g. 'b26'→'326'
            text = "".join(_OCR_CHAR_MAP.get(c, c) for c in text)
            digits = re.findall(r"\d+", text)
            if digits:
                all_segment_digits.append(("".join(digits), confidence))

            # Per-segment candidates
            for d in digits:
                try:
                    number = int(d)
                    if 1 <= number <= 999:
                        # Range 1-999: values above 700 are likely misreads (e.g. 764→364)
                        # and will be corrected by normalize_code_alt later.
                        candidates.append((f"C{number}", confidence))
                    elif number > 999 and len(d) >= 4:
                        # 4-digit read: spurious leading digit from box border — strip it.
                        # e.g. '9351'→351, '1363'→363, '1601'→601
                        stripped = int(d[1:])
                        if 1 <= stripped <= 999:
                            candidates.append((f"C{stripped}", confidence * 0.9))
                except ValueError:
                    pass

            # C-prefixed matches within a segment
            for c_match in re.finditer(r"C[^a-z]*?(\d{1,3})\b", text):
                try:
                    number = int(c_match.group(1))
                    if 1 <= number <= 999:
                        candidates.append((f"C{number}", confidence))
                except ValueError:
                    pass

        # Also try concatenating ALL digit segments left-to-right (handles "3"+"60" → "360")
        if len(all_segment_digits) > 1:
            concat = "".join(d for d, _ in all_segment_digits)
            # Use max confidence: concatenated form should not be penalised vs sub-segments
            max_conf = max(c for _, c in all_segment_digits)
            try:
                number = int(concat)
                if 1 <= number <= 999:
                    candidates.append((f"C{number}", max_conf))
            except ValueError:
                pass

        # Return best candidate: prefer higher confidence, then more digits
        if candidates:
            unique_candidates = list({c[0]: c[1] for c in candidates}.items())
            unique_candidates.sort(key=lambda x: (-x[1], -len(x[0])))
            return unique_candidates[0][0], unique_candidates[0][1]
        return None, 0.0

    # File 03 contains only cells with the ALT box layout — use ALT region directly.
    # Use a separate correction dict — must NOT include C114→C14 (C114 is a real code in file 03).
    if allow_alt:
        ax, ay, aw, ah = CODE_ALT
        alt_x = cell_x + ax
        code, _ = extract_from_region(image_array, alt_x, cell_y + ay, aw, ah)
        if code:
            code = _ALT_CORRECTIONS.get(code, code)
        return code, (ax, ay, aw, ah)

    # Files 01/02: use standard region only.
    sx, sy, sw, sh = CODE_STD
    code_x, code_y, code_w, code_h = cell_x + sx, cell_y + sy, sw, sh
    code, _ = extract_from_region(image_array, code_x, code_y, code_w, code_h)
    used_x, used_w = code_x, code_w

    # Normalize code (fix known OCR errors)
    if code:
        code = normalize_code(code)

    # Return code and the region used (relative to cell)
    return code, (used_x - cell_x, code_y - cell_y, used_w, code_h)


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

    # Use OCR to extract text from enhanced region
    results = reader.readtext(upscaled, detail=1)

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
        # Standard code region - WHITE
        sx, sy, sw, sh = CODE_STD
        cv2.rectangle(crop, (sx, sy), (sx + sw, sy + sh), (255, 255, 255), 1)
        cv2.putText(
            crop,
            "STD",
            (sx, sy - 2),
            cv2.FONT_HERSHEY_SIMPLEX,
            0.35,
            (255, 255, 255),
            1,
        )

        # Alternate code region - YELLOW
        ax, ay, aw, ah = CODE_ALT
        cv2.rectangle(crop, (ax, ay), (ax + aw, ay + ah), (255, 255, 0), 1)
        cv2.putText(
            crop, "ALT", (ax, ay - 2), cv2.FONT_HERSHEY_SIMPLEX, 0.35, (255, 255, 0), 1
        )

        # Actual region used - CYAN (thick)
        if idx < len(color_data):
            cx, cy, cw_, ch_ = color_data[idx].get("_code_region", (21, 12, 44, 44))
        else:
            cx, cy, cw_, ch_ = 21, 12, 44, 44
        cv2.rectangle(crop, (cx, cy), (cx + cw_, cy + ch_), (0, 255, 255), 2)
        cv2.putText(
            crop,
            "USED",
            (cx + 2, cy + ch_ + 10),
            cv2.FONT_HERSHEY_SIMPLEX,
            0.35,
            (0, 255, 255),
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
    json_file = output_path / "pack_mr_color.json"
    formatted_json = {
        "brand": "Mr. Color",
        "brand_id": "mr_color",
        "source": "data/pack_mr_color.json",
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
    csv_file = output_path / "pack_mr_color.csv"
    with csv_file.open("w", newline="") as fh:
        writer = csv.DictWriter(fh, fieldnames=["code", "name", "hex"])
        writer.writeheader()
        for c in colors:
            writer.writerow({"code": c["code"], "name": c["name"], "hex": c["hex"]})
    print(f"✓ Exported {len(colors)} colors to {csv_file}")


def deduplicate_codes(colors):
    """Remove duplicate codes by keeping only the first occurrence of each code.

    This handles OCR errors where codes like C160, C260, C360 are misread as C60,
    creating duplicates. By keeping first occurrence and removing subsequent ones,
    we maintain data integrity while eliminating duplicates.

    Returns the deduplicated list and a report of removed items.
    """
    seen_codes = set()
    deduplicated = []
    removed_count = {}

    for color in colors:
        code = color.get("code")
        if code:
            if code not in seen_codes:
                deduplicated.append(color)
                seen_codes.add(code)
            else:
                # Track which codes had duplicates removed
                removed_count[code] = removed_count.get(code, 0) + 1

    # Report on deduplication
    if removed_count:
        total_removed = sum(removed_count.values())
        print(f"\n⚠️ Removed {total_removed} total duplicate entries:")
        for code in sorted(removed_count.keys()):
            count = removed_count[code]
            print(f"  • {code}: removed {count} duplicate(s), keeping first occurrence")

    return deduplicated


def process_mr_color_images(folder_path, output_folder_or_file):
    """Process all Mr. Color images: detect cells, extract codes, and export previews and pack files.

    Returns a list of color dictionaries with code, name, and hex.
    """
    folder = Path(folder_path)
    output_path = Path(output_folder_or_file)

    preview_folder = Path(".tmp") / "mr_color_previews"

    print(f"\nProcessing Mr. Color images from: {folder}")
    print(f"Exporting previews to: {preview_folder}")
    print(f"{'='*70}\n")

    # Initialize OCR reader
    reader = easyocr.Reader(["en"], gpu=False)

    total_cells = 0
    all_colors = []  # Collect all colors for pack file

    image_files = sorted(folder.glob("*.png"))
    for img_path in image_files:
        print(f"Processing {img_path.name}...")

        # Load image
        with Image.open(img_path) as im:
            img_rgb = np.array(im.convert("RGB"))

        # Detect cells
        cells = find_grid_cells(img_rgb)
        print(f"  ✓ Detected {len(cells)} cells\n")

        # ALT code region is only valid in the third image file (file 03),
        # which contains only colors with the alternative box layout.
        cell_colors = []
        for idx, cell in enumerate(cells):
            allow_alt = img_path == image_files[2]
            code, code_region = extract_cell_code(
                img_rgb, cell, reader, allow_alt=allow_alt
            )
            hex_color, rgb = extract_cell_color(img_rgb, cell)
            name = extract_cell_name(img_rgb, cell, reader, code)
            code_str = code if code else "N/A"
            # print(
            #     f"  {idx:<5} {code_str:<8} {hex_color:<10} {name:<30} {cell['x']:<6} {cell['y']:<6}"
            # )

            # Collect color data for pack file and preview naming
            if code:
                color_dict = {
                    "code": code,
                    "name": name,
                    "hex": hex_color,
                    "equivalents": extract_equivalents_from_name(name),
                    "_code_region": code_region,
                }
                # File 03 ALT corrections are manually verified — replace any earlier
                # entry with the same code so the corrected version takes precedence.
                if allow_alt and code in _ALT_CORRECTIONS.values():
                    all_colors = [c for c in all_colors if c["code"] != code]
                all_colors.append(color_dict)
                cell_colors.append(color_dict)
            else:
                cell_colors.append(
                    {
                        "code": "N/A",
                        "name": name,
                        "hex": hex_color,
                        "_code_region": code_region,
                    }
                )
        print()

        # Export previews
        num_exported = export_cell_previews(
            img_rgb, cells, cell_colors, preview_folder, img_path.stem
        )
        print(f"  ✓ Exported {num_exported} preview files\n")

        total_cells += len(cells)

    # Deduplicate codes before export
    # all_colors = deduplicate_codes(all_colors)

    # Export pack files (JSON and CSV) to data folder
    print(f"\n{'='*70}")
    export_pack_files(all_colors, output_path.parent)
    print(f"{'='*70}\n")

    print(f"TOTAL: {total_cells} cells detected and previewed")
    print()

    # Return colors for pipeline processing
    return all_colors


if __name__ == "__main__":
    source_folder = Path("source/mr_color")
    output_folder = Path("data/mr_color_previews")
    colors = process_mr_color_images(source_folder, output_folder)
