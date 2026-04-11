#!/usr/bin/env python3
"""
Parse Humbrol color cross-reference chart images.

Each image is a table with columns (left to right):
  Humbrol number | Finish | Acrylic | Enamel | Aerosol |
  Revell | Tamiya | Vallejo | AK | Federal Standard |
  Aqueous Color | Mr. Hobby Color | RLM | AMMO MiG | MRP |
  RAL | British Standard | Army Painter | Reaper Master | HEX Code

The HEX Code column (rightmost) contains the raw 6-char hex value without '#'.
The Humbrol number is in the leftmost column (1–maximum 3 digits, bold in a
colored circle – OCR reads it as a plain number).

Strategy:
  1. OCR the image
  2. Cluster OCR entries into rows by Y-coordinate
  3. For each row find:
     a. Humbrol number   → leftmost 1–3 digit plain number
     b. Hex color        → any 6-char hex-like string (last column)
     c. Equivalents      → recognised code patterns in the remaining cells
"""

from pathlib import Path
import json
import re
import csv
from statistics import mean

from PIL import Image
import numpy as np
import easyocr


HUMBROL_FOLDER = Path("source/humbrol")
OUT_JSON = Path("data/pack_humbrol.json")
OUT_CSV = Path("data/pack_humbrol.csv")

# Equivalents we can recognise purely by code format
_EQUIVALENT_PATTERNS = [
    # Tamiya X / XF / LP codes
    (
        re.compile(r"^(LP|XF|X)(\d{1,3})$"),
        "Tamiya",
        lambda m: f"{m.group(1)}{m.group(2)}",
    ),
    # Gunze Aqueous H-codes  (H1 … H999)
    (re.compile(r"^H(\d{1,3})$"), "Gunze Sangyo", lambda m: f"H{m.group(1)}"),
    # Mr. Color C-codes
    (re.compile(r"^C(\d{1,3})$"), "Mr. Hobby", lambda m: f"C{m.group(1)}"),
    # AK codes (AK1234)
    (re.compile(r"^AK(\d{4,5})$"), "AK Interactive", lambda m: f"AK{m.group(1)}"),
    # Vallejo 4-5 digit codes (70.xxx / 71.xxx etc)  stored as-is
    (re.compile(r"^7\d\.\d{3}$"), "Vallejo", lambda m: m.group(0)),
    # RAL 4-digit codes
    (
        re.compile(r"^(\d{4})$"),
        "RAL",
        lambda m: f"RAL {m.group(1)}" if 1000 <= int(m.group(1)) <= 9999 else None,
    ),
    # RLM codes
    (re.compile(r"^RLM[-]?(\d{2,3})$"), "RLM", lambda m: f"RLM-{m.group(1)}"),
    # Federal Standard 5-digit
    (re.compile(r"^(\d{5})$"), "Federal Standard", lambda m: f"FS {m.group(1)}"),
    # AMS / British Standard like "BS640"
    (re.compile(r"^BS(\d{3,4})$"), "British Standard", lambda m: f"BS{m.group(1)}"),
    # Revell 1–2 digit numeric — only reliable after Humbrol number is found
    # (handled separately to avoid false positives)
]

_HEX_RE = re.compile(r"^[0-9A-Fa-f]{6}$")


def rgb_to_hex(arr):
    return "#{:02x}{:02x}{:02x}".format(int(arr[0]), int(arr[1]), int(arr[2]))


def extract_ocr(img_path, reader):
    res = reader.readtext(str(img_path))
    out = []
    for bbox, text, conf in res:
        text = text.strip()
        if not text:
            continue
        xs = [p[0] for p in bbox]
        ys = [p[1] for p in bbox]
        out.append(
            {
                "text": text,
                "confidence": float(conf),
                "bbox": {
                    "x": int(min(xs)),
                    "y": int(min(ys)),
                    "x_end": int(max(xs)),
                    "y_end": int(max(ys)),
                    "width": int(max(xs) - min(xs)),
                    "height": int(max(ys) - min(ys)),
                },
            }
        )
    return out


def cluster_rows(entries, y_tol=18):
    if not entries:
        return []
    sorted_e = sorted(entries, key=lambda e: e["bbox"]["y"])
    rows = []
    cur = []
    last_y = None
    for e in sorted_e:
        y = e["bbox"]["y"]
        if last_y is None or abs(y - last_y) <= y_tol:
            cur.append(e)
            last_y = mean(it["bbox"]["y"] for it in cur)
        else:
            rows.append(cur)
            cur = [e]
            last_y = y
    if cur:
        rows.append(cur)
    return rows


def clean_hex(text):
    """Try to recover a 6-char hex string from OCR output (O→0, I→1 etc.)."""
    t = text.strip().upper()
    # Remove any leading # that OCR might have retained
    t = t.lstrip("#")
    t = t.replace("O", "0").replace("I", "1").replace("L", "1").replace("S", "5")
    if _HEX_RE.match(t):
        return f"#{t}"
    return None


def try_match_equivalent(text):
    """Return a {brand, code} dict if text matches a known equivalent pattern."""
    t = text.strip().upper().replace("-", "").replace(" ", "")
    # Also try with the original dashes intact for RLM
    t_orig = text.strip().upper()

    for pattern, brand, formatter in _EQUIVALENT_PATTERNS:
        m = pattern.match(t)
        if m:
            code = formatter(m)
            if code:
                return {"brand": brand, "code": code}
        # Try with original text (for dotted Vallejo codes)
        m2 = pattern.match(t_orig)
        if m2:
            code = formatter(m2)
            if code:
                return {"brand": brand, "code": code}
    return None


def parse_humbrol_image(img_path, reader, img_width):
    """Parse a single Humbrol chart image."""
    text_entries = extract_ocr(img_path, reader)
    if not text_entries:
        return []

    # Detect approximate header row y (topmost entries, typically y < 120)
    min_y = min(e["bbox"]["y"] for e in text_entries)
    header_cutoff = min_y + 120

    rows = cluster_rows(text_entries)
    results = []

    for row in rows:
        row_y = mean(e["bbox"]["y"] for e in row)
        if row_y <= header_cutoff:
            continue  # skip header rows

        sorted_row = sorted(row, key=lambda e: e["bbox"]["x"])

        # ── Find Humbrol number ───────────────────────────────────────────
        humbrol_num = None
        humbrol_x = None
        for e in sorted_row[:8]:  # check only leftmost entries
            t = e["text"].strip()
            # Strip parentheses OCR sometimes adds around the circled number
            t_clean = re.sub(r"[()\\[\\]]", "", t)
            m = re.match(r"^(\d{1,3})$", t_clean)
            if m:
                humbrol_num = m.group(1)
                humbrol_x = e["bbox"]["x"]
                break

        if not humbrol_num:
            continue

        # ── Find hex color (rightmost HEX-like token) ────────────────────
        hex_color = None
        for e in reversed(sorted_row):
            h = clean_hex(e["text"])
            if h:
                hex_color = h
                break

        if not hex_color:
            hex_color = "#cccccc"

        # ── Extract equivalents ───────────────────────────────────────────
        equivalents = []
        seen_pairs: set[tuple] = set()

        # Find the leftmost x boundary beyond the Humbrol number + finish icon
        # (roughly: beyond the first ~8% of image width)
        equiv_x_start = humbrol_x + img_width * 0.06

        for e in sorted_row:
            if e["bbox"]["x"] < equiv_x_start:
                continue
            t = e["text"].strip()
            # Skip hex color we already collected
            if clean_hex(t):
                continue
            eq = try_match_equivalent(t)
            if not eq:
                continue
            key = (eq["brand"], eq["code"])
            if key not in seen_pairs:
                seen_pairs.add(key)
                equivalents.append(eq)

        results.append(
            {
                "code": humbrol_num,
                "name": "",  # Humbrol names are not in these cross-reference charts
                "hex": hex_color,
                "equivalents": equivalents,
            }
        )

    return results


def parse_humbrol_images(folder_path, output_json):
    folder = Path(folder_path)
    output_json = Path(output_json)

    if not folder.exists():
        print(f"Humbrol folder not found: {folder}")
        return []

    files = sorted(folder.glob("*.png"))
    if not files:
        print(f"No PNGs in {folder}")
        return []

    reader = easyocr.Reader(["en"], gpu=False)
    all_colors = []
    seen_codes: set[str] = set()

    for f in files:
        print(f"Processing {f.name}...")
        with Image.open(f) as im:
            img_w = im.width

        rows = parse_humbrol_image(f, reader, img_w)

        for r in rows:
            code = r["code"]
            if code not in seen_codes:
                seen_codes.add(code)
                all_colors.append(r)

        print(f"  {len(rows)} rows parsed")

    pack = {
        "brand": "Humbrol",
        "brand_id": "humbrol",
        "source": str(output_json),
        "count": len(all_colors),
        "colors": [
            {
                "code": c["code"],
                "name": c.get("name", ""),
                "hex": c["hex"],
                "equivalents": c.get("equivalents", []),
                "confidence": None,
            }
            for c in all_colors
        ],
    }

    output_json.parent.mkdir(parents=True, exist_ok=True)
    output_json.write_text(json.dumps(pack, indent=2, ensure_ascii=False))
    print(f"Wrote {len(all_colors)} Humbrol colors to {output_json}")

    csv_path = output_json.parent / "pack_humbrol.csv"
    with csv_path.open("w", newline="") as fh:
        w = csv.DictWriter(fh, fieldnames=["code", "name", "hex", "equivalents"])
        w.writeheader()
        for c in all_colors:
            w.writerow(
                {
                    "code": c["code"],
                    "name": c.get("name", ""),
                    "hex": c["hex"],
                    "equivalents": "; ".join(
                        f"{e['brand']}:{e['code']}" for e in c.get("equivalents", [])
                    ),
                }
            )
    print(f"Wrote CSV to {csv_path}")

    return all_colors


if __name__ == "__main__":
    parse_humbrol_images(HUMBROL_FOLDER, OUT_JSON)
