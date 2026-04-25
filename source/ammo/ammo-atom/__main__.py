#!/usr/bin/env python3
"""
Parse Ammo-Atom color chart images (table format, similar to Ammo by Mig).
Uses OCR to extract structured table data.
"""

from pathlib import Path
import json
from PIL import Image
import easyocr
import re
import csv
from statistics import mean
from collections import Counter
from math import sqrt


ROOT = Path(__file__).resolve().parents[2]
DATA_DIR = ROOT / "data"

# Fraction of image width to sample for left-column color swatch (configurable).
TABLE_LEFT_POS = 826


def extract_ocr_with_bbox(img_path, reader):
    """Extract text with bounding boxes."""
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


def center(entry):
    """Get center coordinates of a text entry."""
    b = entry["bbox"]
    return (b["x"] + b["width"] / 2, b["y"] + b["height"] / 2)


def cluster_rows(text_entries, y_tol=18):
    """Group text entries into rows by y-coordinate."""
    if not text_entries:
        return []

    entries = sorted(text_entries, key=lambda e: e["bbox"]["y"])
    rows = []
    current = []
    last_y = None

    for e in entries:
        y = e["bbox"]["y"]
        if last_y is None or abs(y - last_y) <= y_tol:
            current.append(e)
            last_y = mean([it["bbox"]["y"] for it in current])
        else:
            rows.append(current)
            current = [e]
            last_y = e["bbox"]["y"]

    if current:
        rows.append(current)

    return rows


def detect_headers(text_entries):
    """Detect table headers."""
    headers_expected = [
        "ATOM",
        "COLOR NAME",
        "NOMBRE DEL COLOR",
        "RAL",
        "AMMO",
        "HOBBY COLOR",
        "MR.COLOR",
        "TAMIYA",
        "MODEL COLOR",
        "MODEL AIR",
    ]

    headers = {}
    for e in text_entries:
        t = e["text"].strip().upper()
        for h in headers_expected:
            if h in t or t in h:
                cx, _ = center(e)
                headers[h] = cx
                break

    # Sort by x position
    ordered = dict(sorted(headers.items(), key=lambda kv: kv[1]))
    return ordered


def assign_columns(row_entries, headers_map):
    """Assign row entries to columns based on headers."""
    cols = {k: None for k in headers_map.keys()}

    for e in row_entries:
        cx, _ = center(e)
        # Find nearest header
        best = None
        best_dist = None

        for h, hx in headers_map.items():
            dist = abs(cx - hx)
            if best is None or dist < best_dist:
                best = h
                best_dist = dist

        if best is not None:
            if cols[best] is None:
                cols[best] = e["text"].strip()
            else:
                # Prefer longer/higher confidence
                if len(e["text"].strip()) > len(cols[best]):
                    cols[best] = e["text"].strip()

    return cols


def normalize_atom_code(text):
    """Normalize ATOM code (e.g., 'ATOM-20001' -> 'ATOM-20001')."""
    if not text:
        return None
    s = text.strip().upper()
    # Match patterns like ATOM-20001 or ATOM 20001 or ATOM20001
    m = re.search(r"ATOM[-\s]?(\d{4,5})", s)
    if m:
        return f"ATOM-{m.group(1)}"
    return None


def normalize_atom_equiv_code(code):
    """Normalize an equivalent code: strip dashes/spaces/dots, uppercase, O→0, I→1 when digits present.

    Special post-fixes:
    - AM1GddDD -> MIG-ddDD  (AMIG OCR corruption; normalises to ammo pack format)
    - AMM0Fnn  -> AMMOFnn   (AMMO filter codes; O->0 corruption)
    """
    if not code:
        return None
    s = code.strip().upper().replace("-", "").replace(" ", "").replace(".", "")
    if any(ch.isdigit() for ch in s):
        s = s.replace("I", "1").replace("O", "0").replace("L", "1")
    if s in {"-", "--", ""}:
        return None
    # AMIG codes: AM1G0050 (all OCR variants collapse here) → MIG-0050
    m = re.match(r"^AM1G(\d{4})$", s)
    if m:
        return f"MIG-{m.group(1)}"
    # AMMO filter codes: AMM0F515 → AMMOF515
    m = re.match(r"^AMM0F(\d{3,4})$", s)
    if m:
        return f"AMMOF{m.group(1)}"
    return s


def build_atom_equivalents(brand, raw_code):
    """Build one or more equivalents from raw OCR text, splitting on '/'."""
    if not raw_code or raw_code.strip() in {"-", "--"}:
        return []
    results = []
    seen = set()
    for part in raw_code.split("/"):
        code = normalize_atom_equiv_code(part)
        if not code:
            continue
        # Infer sub-brand from code prefix for H/C codes
        effective_brand = brand
        if re.match(r"^H\d", code):
            effective_brand = "Gunze Sangyo"
        elif re.match(r"^C\d", code):
            effective_brand = "Mr. Color"
        key = (effective_brand, code)
        if key not in seen:
            seen.add(key)
            results.append({"brand": effective_brand, "code": code})
    return results


def extract_rlm_from_name(color_name):
    """Extract RLM codes from color name (e.g., 'OLIVGRiN (RLM 71)' or 'SANDGELB RLM 79').

    Handles patterns like:
    - RLM XX (with optional hyphen: RLM-XX)
    - (RLM XX)
    Returns list of equivalents with brand='RLM'.
    """
    if not color_name:
        return []

    results = []
    seen = set()

    # Match patterns: RLM XX, RLM-XX, (RLM XX), (RLM-XX), etc.
    # Case insensitive
    pattern = r"\(?RLM[\s-]?(\d{2}(?:-\d)?)\)?"
    matches = re.findall(pattern, color_name, re.IGNORECASE)

    for match in matches:
        # Normalize to RLM-XX or RLM-XX-X format
        code = f"RLM-{match}"
        if code not in seen:
            seen.add(code)
            results.append({"brand": "RLM", "code": code})

    return results


def extract_table_colors_grid(img_path, left_x=TABLE_LEFT_POS):
    """Sample pixels at left_x_frac (fraction of image width) for every row.

    Returns {y: hex_color} without brightness filtering so that near-white
    and near-black colors are captured correctly.
    """
    img = Image.open(img_path)
    if img.mode != "RGB":
        img = img.convert("RGB")

    lx = int(left_x)
    colors_by_y = {}
    for y in range(80, img.height - 20, 2):
        r, g, b = img.getpixel((lx, y))
        colors_by_y[y] = f"#{r:02x}{g:02x}{b:02x}"
    return colors_by_y


def hex_distance(hex_a, hex_b):
    """Compute Euclidean distance between two hex colors."""
    try:
        left = hex_a.lstrip("#")
        right = hex_b.lstrip("#")
        r1, g1, b1 = int(left[0:2], 16), int(left[2:4], 16), int(left[4:6], 16)
        r2, g2, b2 = (
            int(right[0:2], 16),
            int(right[2:4], 16),
            int(right[4:6], 16),
        )
        return sqrt((r1 - r2) ** 2 + (g1 - g2) ** 2 + (b1 - b2) ** 2)
    except ValueError:
        return float("inf")


def load_ral_map():
    """Load RAL-to-hex mapping when available."""
    ral_path = DATA_DIR / "ral_to_hex.json"
    if not ral_path.exists():
        return {}
    return json.loads(ral_path.read_text(encoding="utf-8"))


def load_equivalent_candidates():
    """Load candidate colors from other brand packs for nearest matching."""
    candidates = []

    for file_name in [
        "pack_ammo.json",
        "pack_gunze.json",
        "pack_ak.json",
        "pack_mr_color.json",
    ]:
        pack_path = DATA_DIR / file_name
        if not pack_path.exists():
            continue

        pack = json.loads(pack_path.read_text(encoding="utf-8"))
        brand = pack.get("brand", "other")
        for color in pack.get("colors", []):
            hex_value = color.get("hex")
            code = color.get("code")
            if code and hex_value and hex_value != "#cccccc":
                candidates.append((brand, code, hex_value))

    return candidates


def parse_ammo_atom_images(folder_path, output_json):
    """Parse all Ammo-Atom images."""
    folder = Path(folder_path)

    reader = easyocr.Reader(["en"], gpu=False)
    all_colors = []

    # Collect colors from grid extraction across all images
    colors_grid = {}

    for img_path in sorted(folder.glob("*.png")):
        print(f"Processing {img_path.name}...")

        # Extract OCR
        text_entries = extract_ocr_with_bbox(img_path, reader)

        # Detect headers and rows
        headers = detect_headers(text_entries)
        rows = cluster_rows(text_entries)

        print(f"  Found {len(headers)} headers: {list(headers.keys())}")

        # Extract colors from grid
        img_colors = extract_table_colors_grid(img_path)
        colors_grid.update(img_colors)

        for row_entries in rows:
            cols = assign_columns(row_entries, headers)

            atom_code = normalize_atom_code(cols.get("ATOM"))
            if not atom_code:
                continue

            color_name = (
                cols.get("COLOR NAME", "").strip()
                or cols.get("NOMBRE DEL COLOR", "").strip()
            )

            if atom_code and color_name:
                # Find the y position of this row to match with grid colors
                row_y = int(mean([e["bbox"]["y"] for e in row_entries]))

                # Find the closest y from grid extraction
                hex_color = "#ffffff"  # Default fallback
                if colors_grid:
                    closest_y = min(
                        colors_grid.keys(),
                        key=lambda y, row_y=row_y: abs(y - row_y),
                    )
                    if abs(closest_y - row_y) < 30:  # Within 30 pixels
                        hex_color = colors_grid[closest_y]

                # Extract equivalents from table columns
                equivalents = []
                for equiv_key, brand_name in [
                    ("AMMO", "Ammo by Mig"),
                    ("HOBBY COLOR", "Gunze Sangyo"),
                    ("MR.COLOR", "Mr. Color"),
                    ("TAMIYA", "Tamiya"),
                    ("MODEL COLOR", "Vallejo Model Color"),
                    ("MODEL AIR", "Vallejo Model Air"),
                ]:
                    val = cols.get(equiv_key)
                    if val and val.strip() and val.strip() not in {"-", "--"}:
                        equivalents.extend(
                            build_atom_equivalents(brand_name, val.strip())
                        )

                # Extract RLM codes from color name
                equivalents.extend(extract_rlm_from_name(color_name))

                all_colors.append(
                    {
                        "code": atom_code,
                        "name": color_name,
                        "hex": hex_color,
                        "equivalents": equivalents,
                    }
                )

        print(
            f"  Found {len(
                [c for c in all_colors if 'ATOM' in c['code']]
            )} colors so far"
        )

    # Build output in standard format
    output_data = {
        "brand": "Ammo by Mig Atom",
        "brand_id": "ammo_atom",
        "source": str(output_json),
        "count": len(all_colors),
        "colors": all_colors,
    }

    # Write results
    output_json.parent.mkdir(parents=True, exist_ok=True)
    output_json.write_text(json.dumps(output_data, indent=2, ensure_ascii=False))
    print(f"Wrote {len(all_colors)} colors to {output_json}")

    # Generate CSV
    csv_path = output_json.parent / "pack_ammo_atom.csv"
    with csv_path.open("w", newline="") as fh:
        writer = csv.DictWriter(
            fh,
            fieldnames=["code", "name", "hex", "equivalents", "confidence"],
        )
        writer.writeheader()
        for c in all_colors:
            writer.writerow(
                {
                    "code": c.get("code", ""),
                    "name": c.get("name", ""),
                    "hex": c.get("hex", ""),
                    "equivalents": "; ".join(
                        f"{item.get('brand')}:{item.get('code')}"
                        for item in c.get("equivalents", [])
                    ),
                    "confidence": c.get("confidence", ""),
                }
            )
    print(f"Wrote CSV to {csv_path}")
    return all_colors


if __name__ == "__main__":
    source_folder = Path("source/ammo-atom")
    output = Path("data/pack_ammo_atom.json")

    parsed_colors = parse_ammo_atom_images(source_folder, output)
