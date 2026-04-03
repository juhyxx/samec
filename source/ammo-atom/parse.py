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
                cx, cy = center(e)
                headers[h] = cx
                break

    # Sort by x position
    ordered = dict(sorted(headers.items(), key=lambda kv: kv[1]))
    return ordered


def assign_columns(row_entries, headers_map):
    """Assign row entries to columns based on headers."""
    cols = {k: None for k in headers_map.keys()}

    for e in row_entries:
        cx, cy = center(e)
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


def parse_ammo_atom_images(folder_path, output_json):
    """Parse all Ammo-Atom images."""
    folder = Path(folder_path)

    reader = easyocr.Reader(["en"], gpu=False)
    all_colors = []

    for img_path in sorted(folder.glob("*.png")):
        print(f"Processing {img_path.name}...")

        # Extract OCR
        text_entries = extract_ocr_with_bbox(img_path, reader)

        # Detect headers and rows
        headers = detect_headers(text_entries)
        rows = cluster_rows(text_entries)

        print(f"  Found {len(headers)} headers: {list(headers.keys())}")

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
                all_colors.append(
                    {
                        "code": atom_code,
                        "name": color_name,
                        "hex": "#000000",  # Placeholder, could extract from image if needed
                    }
                )

        print(
            f"  Found {len([c for c in all_colors if 'ATOM' in c['code']])} colors so far"
        )

    # Deduplicate
    seen = set()
    unique_colors = []
    for c in all_colors:
        key = c["code"]
        if key not in seen:
            seen.add(key)
            unique_colors.append(c)

    # Write results
    output_json.parent.mkdir(parents=True, exist_ok=True)
    output_json.write_text(json.dumps(unique_colors, indent=2, ensure_ascii=False))
    print(f"Wrote {len(unique_colors)} unique colors to {output_json}")

    # Generate CSV
    csv_path = output_json.parent / "pack_ammo_atom.csv"
    with csv_path.open("w", newline="") as fh:
        writer = csv.DictWriter(fh, fieldnames=["code", "name", "hex"])
        writer.writeheader()
        for c in unique_colors:
            writer.writerow(
                {
                    "code": c.get("code", ""),
                    "name": c.get("name", ""),
                    "hex": c.get("hex", ""),
                }
            )
    print(f"Wrote CSV to {csv_path}")
    return unique_colors


if __name__ == "__main__":
    source_folder = Path("source/ammo-atom")
    output = Path("data/results/pack_ammo_atom.json")

    colors = parse_ammo_atom_images(source_folder, output)
