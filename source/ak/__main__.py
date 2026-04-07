#!/usr/bin/env python3
"""
Parse AK Interactive color chart images.

Overview:
  AK Interactive provides color reference charts as PNG table images.
  Each image contains rows with: [swatch] [code] [color name]

  This parser:
  1. Extracts OCR text from images (codes like "AK1301", color names)
  2. Detects color swatches using K-means clustering
  3. Groups OCR entries into rows by Y-coordinate proximity
  4. Matches each row's text entries to find code + name
  5. Maps rows to color swatches by Y-position
  6. Outputs JSON pack format with hex colors

Key Tolerances:
  - y_tol=20: Row clustering tolerance (entries within 20px vertically = same row)
  - min_swatch_size=15: Minimum dimensions to treat as a color swatch
  - K=12: Number of k-means clusters for color extraction
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

DEBUG = False  # Set to False to suppress row/swatch counts

# Fraction of image width to sample for left-column color swatch (configurable).
TABLE_LEFT_POS = 589

AK_EQUIVALENT_COLUMNS = [
    {
        "key": "tamiya",
        "brand": "Tamiya",
        "aliases": ["TAMIYA"],
        "fallback_ratio": 0.385,
    },
    {
        "key": "humbrol",
        "brand": "Humbrol",
        "aliases": ["HUMBROL"],
        "fallback_ratio": 0.442,
    },
    {
        "key": "vallejo",
        "brand": "Vallejo",
        "aliases": ["VALLEJO"],
        "fallback_ratio": 0.504,
    },
    {
        "key": "gunze",
        "brand": "Gunze / Mr. Hobby",
        "aliases": ["GUNZE", "HOBBY"],
        "fallback_ratio": 0.556,
    },
    {
        "key": "testor",
        "brand": "Testor",
        "aliases": ["TESTOR"],
        "fallback_ratio": 0.611,
    },
    {
        "key": "lifecolor",
        "brand": "Lifecolor",
        "aliases": ["LIFECOLOR"],
        "fallback_ratio": 0.668,
    },
    {
        "key": "ral",
        "brand": "RAL",
        "aliases": ["RAL"],
        "fallback_ratio": 0.732,
    },
    {
        "key": "fs",
        "brand": "FS",
        "aliases": ["FS"],
        "fallback_ratio": 0.791,
    },
    {
        "key": "hataka",
        "brand": "Hataka",
        "aliases": ["HATAKA"],
        "fallback_ratio": 0.843,
    },
    {
        "key": "real_colors",
        "brand": "Real Colors",
        "aliases": ["REAL", "COLORS"],
        "fallback_ratio": 0.897,
    },
    {
        "key": "ak_old_reference",
        "brand": "AK Old Reference",
        "aliases": ["AK OLD", "REFERENCE"],
        "fallback_ratio": 0.955,
    },
]


def rgb_to_hex(arr):
    """Convert RGB array to hex color string.

    Args:
        arr: [R, G, B] values (0-255)
    Returns:
        Hex color string like "#ff00aa"
    """
    return "#{:02x}{:02x}{:02x}".format(int(arr[0]), int(arr[1]), int(arr[2]))


def extract_ocr_with_bbox(img_path, reader):
    """Extract text with bounding boxes from image using EasyOCR.

    This step identifies all text in the image and records its position.
    Each text entry stores: text, confidence score, and bbox (x, y, x_end, y_end).

    Args:
        img_path: Path to PNG image
        reader: EasyOCR reader instance

    Returns:
        List of {text, confidence, bbox} dicts
        bbox = {x, y, x_end, y_end, width, height}
    """
    res = reader.readtext(str(img_path))
    out = []

    for bbox, text, conf in res:
        text = text.strip()
        if not text:
            continue

        # Extract corner coordinates from OCR bbox polygon (usually 4 corners)
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
    if DEBUG:
        print(f"    OCR extracted {len(out)} text entries")
    return out


def center(entry):
    """Get center coordinates of a text entry."""
    b = entry["bbox"]
    return (b["x"] + b["width"] / 2, b["y"] + b["height"] / 2)


def detect_ak_column_centers(text_entries, image_width):
    """Detect header column centers for the AK equivalents table."""
    header_entries = [e for e in text_entries if e["bbox"]["y"] <= 120]
    centers = {}

    for column in AK_EQUIVALENT_COLUMNS:
        matches = []
        for entry in header_entries:
            text = entry["text"].strip().upper()
            if any(alias in text for alias in column["aliases"]):
                matches.append(center(entry)[0])

        if matches:
            centers[column["key"]] = mean(matches)
        else:
            centers[column["key"]] = image_width * column["fallback_ratio"]

    return centers


def find_ak_equivalent_column(entry_x, column_centers):
    """Assign an OCR entry to the nearest AK equivalents column."""
    if not column_centers:
        return None

    nearest_key = None
    nearest_distance = None
    sorted_columns = sorted(column_centers.items(), key=lambda item: item[1])

    for key, center_x in sorted_columns:
        distance = abs(entry_x - center_x)
        if nearest_distance is None or distance < nearest_distance:
            nearest_key = key
            nearest_distance = distance

    if nearest_distance is not None and nearest_distance <= 90:
        return nearest_key
    return None


def normalize_equivalent_code(brand, text):
    """Normalize OCR tokens for equivalent-code display and lookup."""
    if not text:
        return None

    code = text.strip().upper()
    code = code.replace(" ", "")
    code = code.replace("_", "")
    code = code.replace("O", "0") if any(ch.isdigit() for ch in code) else code
    code = code.replace("I", "1") if any(ch.isdigit() for ch in code) else code
    code = code.replace("L", "1") if any(ch.isdigit() for ch in code) else code
    code = re.sub(r"^[^A-Z0-9]+|[^A-Z0-9/.-]+$", "", code)
    code = re.sub(r"\s*/\s*", "/", code)

    if brand == "Tamiya":
        match = re.match(r"^(XF|X|LP)-?(\d+)$", code)
        if match:
            return f"{match.group(1)}{match.group(2)}"
    if brand == "Gunze / Mr. Hobby":
        match = re.match(r"^([HCSM])[- ]?(\d{1,4})$", code)
        if match:
            return f"{match.group(1)}{match.group(2)}"
    if brand in {"Humbrol", "Vallejo", "Hataka", "Real Colors", "RAL", "FS"}:
        return code
    if brand == "Lifecolor":
        match = re.match(r"^(UA)-?(\d+)$", code)
        if match:
            return f"{match.group(1)}{match.group(2)}"
    if brand == "AK Old Reference":
        match = re.search(r"AK\d+", code)
        if match:
            return match.group(0)

    return code or None


def build_equivalent(brand, text):
    """Convert raw OCR cell text into a normalized equivalent entry."""
    code = normalize_equivalent_code(brand, text)
    if not code or code in {"-", "--"}:
        return None
    return {"brand": brand, "code": code}


def cluster_rows(text_entries, y_tol=20):
    """Group text entries into rows by Y-coordinate proximity.

    Purpose:
      Table rows often have OCR text at slightly different Y values.
      This function groups entries that are vertically close (within y_tol pixels).

    Algorithm:
      1. Sort all entries by Y-coordinate
      2. Initialize: current_row = []
      3. For each entry:
         - If Y distance to last_y <= y_tol: add to current_row
         - Else: save current_row and start new row
      4. Return list of rows (each row is list of entries)

    Args:
        text_entries: List of OCR text entries with bbox info
        y_tol: Vertical distance threshold (pixels) to consider entries same row
               y_tol=12: very tight (needs near-perfect alignment)
               y_tol=20: moderate (captures chars of different heights)
               y_tol=30+: loose (may merge separate table rows)

    Returns:
        List of rows, where each row is [entry1, entry2, ...] sorted left-to-right
    """
    if not text_entries:
        return []

    # Sort by Y position (top to bottom)
    entries = sorted(text_entries, key=lambda e: e["bbox"]["y"])
    rows = []
    current = []
    last_y = None

    for e in entries:
        y = e["bbox"]["y"]
        # If within tolerance, add to current row
        if last_y is None or abs(y - last_y) <= y_tol:
            current.append(e)
            # Update last_y as mean of all entries in current row (centers converge)
            last_y = mean([it["bbox"]["y"] for it in current])
        else:
            # Too far below: save current row and start new one
            if current:
                rows.append(current)
            current = [e]
            last_y = e["bbox"]["y"]

    if current:
        rows.append(current)

    if DEBUG:
        print(f"    Row clustering (y_tol={y_tol}): {len(rows)} rows detected")
    return rows


def find_color_swatches(image_array, min_swatch_size=15):
    """Detect color swatches in image using K-means clustering.

    Purpose:
      Swatches are small colored rectangles. We use K-means to group pixels
      into distinct color clusters, then detect connected regions of each color.

    Algorithm:
      1. Reshape image into Nx3 array (all pixels as RGB vectors)
      2. K-means clustering: k=12 clusters to find dominant colors
      3. Create label map: each pixel gets cluster ID
      4. For each cluster, find contours (connected regions)
      5. Each contour is a potential swatch if size >= min_swatch_size px²
      6. Extract average color from swatch region

    Args:
        image_array: Image as numpy array (H, W, 3) RGB
        min_swatch_size: Min width and height to treat as swatch (default 15px)

    Returns:
        List of swatches: [{x, y, width, height, rgb, hex, cluster}, ...]
    """
    h, w, _ = image_array.shape

    # K-means clustering to group pixels by color
    Z = image_array.reshape((-1, 3)).astype(np.float32)
    K = 12  # Number of color clusters
    criteria = (cv2.TERM_CRITERIA_EPS + cv2.TERM_CRITERIA_MAX_ITER, 10, 1.0)
    _, labels, centers = cv2.kmeans(Z, K, None, criteria, 3, cv2.KMEANS_PP_CENTERS)

    centers = centers.astype(np.uint8)
    labels = labels.flatten().reshape(h, w)  # Reshape back to image dimensions

    swatches = []
    # For each cluster color, find contours (solid regions)
    for i in range(K):
        mask = (labels == i).astype("uint8") * 255
        contours, _ = cv2.findContours(mask, cv2.RETR_EXTERNAL, cv2.CHAIN_APPROX_SIMPLE)

        for cnt in contours:
            x, y, ww, hh = cv2.boundingRect(cnt)

            # Filter by minimum size (avoid noise)
            if ww >= min_swatch_size and hh >= min_swatch_size:
                # Extract average color from swatch region
                region = image_array[y : y + hh, x : x + ww]
                avg_color = region.reshape(-1, 3).mean(axis=0)

                swatches.append(
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
                        "cluster": i,
                    }
                )
    print(swatches)
    if DEBUG:
        print(f"    Swatch detection: {len(swatches)} swatches found")
    return swatches


def normalize_ak_code(text):
    """Extract AK code from text, handling common OCR errors.

    AK codes have format: AK#### (4 digits, e.g., AK1301, AK3073)
    OCR sometimes produces 5+ digits due to digit doubling (e.g., AK11366 for AK1336).

    OCR Error Handling:
      - I → 1 (OCR often confuses letter I with digit 1)
      - l → 1 (lowercase L looks like 1)
      - O → 0 (letter O confused with digit 0)
      - o → 0 (lowercase O)
      - Allow spacing: "AK 1301", "AK-1301" → "AK1301"
      - Keep all extracted digits (deduplication handles near-duplicates)

    Args:
        text: Raw OCR text (may contain errors, possibly 5+ digits)

    Returns:
        Code like "AK1301" or "AK11366" (if 5 digits due to OCR), or None
    """
    if not text:
        return None

    s = text.strip().upper()

    # Replace likely OCR errors
    s_cleaned = (
        s.replace("I", "1")  # Capital I -> 1
        .replace("l", "1")  # Lowercase L -> 1
        .replace("O", "0")  # Capital O -> 0
        .replace("o", "0")  # Lowercase O -> 0
    )

    # Match "AK [optional space/dash] followed by digits"
    # Keep ALL digits (even if 5+, to preserve uniqueness for deduplication)
    match = re.search(r"AK[\s\-]?(\d+)", s_cleaned)
    if match:
        digits = match.group(1)
        # Require at least 4 digits
        if len(digits) >= 4:
            return f"AK{digits}"  # Keep all digits

    return None


def extract_color_data_from_rows(text_entries, image_array, image_width):
    """Extract color codes, names, and hex values from OCR rows and swatches.

    Workflow for each row:
      1. Cluster OCR text entries into rows (vertically aligned entries)
      2. Sort row entries left-to-right (column order)
      3. Find LEFTMOST AK code in row (the primary code, not cross-references)
      4. Find color name (usually after code)
      5. Find matching swatch by Y-position (swatch Y closest to row Y)
      6. Extract hex color from swatch
      7. Return {code, name, hex}

    Row Structure (from AK reference chart):
      [SWATCH] [AK1301] [Type] [Color Name] [Cross-refs...] [AK OLD REF...]
      We only want the leftmost AK#### code (primary), not cross-refs on the right.

    Args:
        text_entries: List of OCR text entries with bbox
        swatches: List of detected color swatches

    Returns:
        List of {code, name, hex} dicts (deduplicated, primary codes only)
    """
    colors = []
    rows = cluster_rows(text_entries)
    column_centers = detect_ak_column_centers(text_entries, image_width)
    column_brand_map = {
        column["key"]: column["brand"] for column in AK_EQUIVALENT_COLUMNS
    }

    if DEBUG:
        print(f"    Extracting colors from {len(rows)} rows...")

    # Track seen codes in THIS image to avoid duplicates from repeated columns
    seen_codes_in_image = set()

    for row_idx, row_entries in enumerate(rows):
        # Sort entries left-to-right (by X) to determine column order
        sorted_entries = sorted(row_entries, key=lambda e: e["bbox"]["x"])

        # DEBUG: Show first few rows to understand structure
        if DEBUG and row_idx < 3:
            row_texts = [
                e["text"][:20] for e in sorted_entries[:5]
            ]  # First 5 entries, truncated
            print(f"      Row {row_idx}: {row_texts}")

        # Step 1: Find LEFTMOST AK code (the primary code, not cross-references from other columns)
        # Cross-reference codes appear in the rightmost columns of the chart
        # We only want the first/leftmost code to avoid extracting old AK references
        ak_code = None
        code_idx = None
        code_x = None  # Track X position of found code

        for idx, entry in enumerate(sorted_entries):
            code = normalize_ak_code(entry["text"])
            if code:
                # Take the FIRST (leftmost) code found in this row
                # (This is the primary reference, not cross-refs from other brands)
                if ak_code is None:  # Only set if we haven't found one yet
                    ak_code = code
                    code_idx = idx
                    code_x = entry["bbox"]["x"]
                    if DEBUG and row_idx < 5:
                        print(f"        → Found code {ak_code} at position {idx}")
                else:
                    # Skip additional codes in the same row (they're cross-references)
                    pass

        if not ak_code:
            # No valid AK code in this row—skip it
            if DEBUG and row_idx < 5:
                print(f"        ✗ No AK code found")
            continue

        # DEDUPLICATION: Skip if we already extracted this code from this image
        if ak_code in seen_codes_in_image:
            continue
        seen_codes_in_image.add(ak_code)

        # Step 2: Extract TYPE (column 2, usually right after code: AFV, FIG, AIR, etc.)
        # This should be a short label
        color_type = None
        if code_idx is not None and code_idx + 1 < len(sorted_entries):
            next_entry = sorted_entries[code_idx + 1]
            text = next_entry["text"].strip().upper()
            # Type is usually short (2-5 chars) and all caps
            if text and len(text) <= 5 and text.isalpha():
                color_type = text

        # Step 3: Extract COLOR NAME (column 3, after type)
        # The color name is a longer text description
        color_name = None
        search_start_idx = code_idx + 2 if color_type else code_idx + 1
        if search_start_idx < len(sorted_entries):
            # Try entries after type
            for entry in sorted_entries[search_start_idx:]:
                text = entry["text"].strip()
                entry_x = entry["bbox"]["x"]
                # Only consider entries within ~1000px of code (same logical column area)
                # This avoids reading from cross-reference columns far to the right
                if entry_x - code_x > 1000:
                    break  # We've moved too far right, stop looking

                # Skip empty, single-char, or other AK codes
                if text and len(text) > 1 and not normalize_ak_code(text):
                    color_name = text
                    break

        if not color_name:
            color_name = "Unnamed"
        if not color_type:
            color_type = "Unknown"

        equivalents = []
        seen_equivalent_pairs = set()
        for entry in sorted_entries:
            entry_text = entry["text"].strip()
            if not entry_text:
                continue

            entry_x = center(entry)[0]
            if code_x is not None and entry_x <= code_x + 520:
                continue

            column_key = find_ak_equivalent_column(entry_x, column_centers)
            if not column_key:
                continue

            equivalent = build_equivalent(column_brand_map[column_key], entry_text)
            if not equivalent:
                continue

            pair = (equivalent["brand"], equivalent["code"])
            if pair in seen_equivalent_pairs:
                continue
            seen_equivalent_pairs.add(pair)
            equivalents.append(equivalent)

        # Step 4: Sample pixel at TABLE_LEFT_POS for this row (no K-means needed).
        row_y = mean([e["bbox"]["y"] for e in row_entries])
        h, w = image_array.shape[:2]
        lx = int(TABLE_LEFT_POS)
        sy = int(max(2, min(h - 3, row_y)))
        region = image_array[
            max(0, sy - 2) : min(h, sy + 3),
            max(0, lx - 2) : min(w, lx + 3),
        ]
        if region.size:
            avg = region.reshape(-1, 3).mean(axis=0)
            hex_color = rgb_to_hex(avg)
        else:
            hex_color = "#cccccc"

        # Store color with type as metadata
        colors.append(
            {
                "code": ak_code,
                "name": color_name.strip(),
                "type": color_type,  # Store column 2 (type) as extra data
                "hex": hex_color,
                "equivalents": equivalents,
            }
        )

        if DEBUG and len(colors) % 20 == 0:
            print(f"      Extracted {len(colors)} colors so far...")

    if DEBUG:
        print(f"    Total: {len(colors)} colors extracted (primary codes only)")
    return colors


def parse_ak_images(folder_path, output_json):
    """Parse all AK Interactive PNG images and generate color pack JSON.

    Pipeline:
      1. Load all PNG images from folder
      2. For each image:
         a. Extract OCR (codes, color names)
         b. Detect color swatches
         c. Match rows to swatches
      3. Deduplicate colors by code
      4. Output pack JSON + CSV

    Args:
        folder_path: Path to folder with PNG images
        output_json: Path to save output JSON pack

    Returns:
        List of unique color dicts
    """
    folder = Path(folder_path)

    reader = easyocr.Reader(["en"], gpu=False)
    all_colors = []

    # Process each PNG
    image_files = sorted(folder.glob("*.png"))
    print(f"Found {len(image_files)} PNG files in {folder}")

    for img_idx, img_path in enumerate(image_files, 1):
        print(f"\n[{img_idx}/{len(image_files)}] Processing {img_path.name}...")

        # Load image
        with Image.open(img_path) as im:
            img_rgb = np.array(im.convert("RGB"))
            print(f"  Image size: {img_rgb.shape}")

        # Extract text and swatches
        text_entries = extract_ocr_with_bbox(img_path, reader)

        # Extract color data from rows using direct pixel sampling
        colors = extract_color_data_from_rows(text_entries, img_rgb, img_rgb.shape[1])
        all_colors.extend(colors)

        print(f"  → {len(colors)} new colors (total: {len(all_colors)})")

    # Deduplicate by AK code (keep first occurrence)
    seen = set()
    unique_colors = []
    duplicates = 0
    for c in all_colors:
        key = c["code"]
        if key not in seen:
            seen.add(key)
            unique_colors.append(c)
        else:
            duplicates += 1

    print(
        f"\nDeduplication: {len(all_colors)} → {len(unique_colors)} unique ({duplicates} removed)"
    )

    # Build pack format
    pack = {
        "brand": "AK Interactive",
        "brand_id": "ak",
        "source": str(output_json),
        "count": len(unique_colors),
        "colors": [
            {
                "code": c.get("code", ""),
                "name": c.get("name", "Unnamed"),
                "type": c.get(
                    "type", "Unknown"
                ),  # Include color type (AFV, FIG, AIR, etc.)
                "hex": c.get("hex", "#cccccc"),
                "equivalents": c.get("equivalents", []),
                "confidence": None,
            }
            for c in unique_colors
        ],
    }

    # Write JSON result
    output_json.parent.mkdir(parents=True, exist_ok=True)
    output_json.write_text(json.dumps(pack, indent=2, ensure_ascii=False))
    print(f"\n✓ Wrote {len(unique_colors)} colors to {output_json}")

    # Generate CSV for data checking
    csv_path = output_json.parent / "pack_ak.csv"
    with csv_path.open("w", newline="") as fh:
        writer = csv.DictWriter(
            fh, fieldnames=["code", "name", "type", "hex", "equivalents", "confidence"]
        )
        writer.writeheader()
        for c in pack["colors"]:
            writer.writerow(
                {
                    "code": c.get("code", ""),
                    "name": c.get("name", ""),
                    "type": c.get("type", ""),
                    "hex": c.get("hex", ""),
                    "equivalents": "; ".join(
                        [
                            f"{e.get('brand')}:{e.get('code')}"
                            for e in c.get("equivalents", [])
                        ]
                    ),
                    "confidence": c.get("confidence", ""),
                }
            )
    print(f"✓ Wrote CSV to {csv_path}")
    return unique_colors


if __name__ == "__main__":
    source_folder = Path("source/ak")
    output = Path("data/pack_ak.json")

    colors = parse_ak_images(source_folder, output)
