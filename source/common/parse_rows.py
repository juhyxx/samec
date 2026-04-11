#!/usr/bin/env python3
"""Parse `data/ammo_catalog.json` into structured rows with code, name, equivalents, and hex."""
import json
from pathlib import Path
from statistics import mean
import csv
import re
import os


IN_FILE = Path("data/ammo_catalog.json")
OUT_JSON = Path("data/ammo_rows.json")
OUT_CSV = Path("data/ammo_rows.csv")


HEADERS_EXPECTED = [
    "REFERENCE",
    "COLOR NAME",
    "RAL/RLMFS",
    "HOBBY COLOR",
    "MR.COLOR",
    "TAMIYA",
    "MODEL COLOR",
    "MODEL AIR",
]

# For table-like image layouts (k, ammo, ammo-atom, gunze) we can pick
# a single pixel/swatch at a fixed left position per row instead of
# searching nearest-to-header. Set to a fraction (0.0-1.0) to use image
# relative coordinate, or to a pixel value (>1) to use absolute coords.
TABLE_LEFT_POS = 0.06
TABLE_BRANDS = ["k", "ammo", "ammo-atom", "gunze"]


def center(entry):
    b = entry["bbox"]
    return (b["x"] + b["width"] / 2, b["y"] + b["height"] / 2)


def cluster_rows(text_entries, y_tol=18):
    # sort by y
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
    headers = {}
    for e in text_entries:
        t = e["text"].strip().upper()
        if t in HEADERS_EXPECTED:
            cx, cy = center(e)
            headers[t] = cx
    # Sort headers by x position
    ordered = dict(sorted(headers.items(), key=lambda kv: kv[1]))
    return ordered


def assign_columns(row_entries, headers_map):
    # headers_map: name->x_center
    cols = {k: None for k in headers_map.keys()}
    for e in row_entries:
        cx, cy = center(e)
        # find nearest header by x distance
        best = None
        best_dist = None
        for h, hx in headers_map.items():
            dist = abs(cx - hx)
            if best is None or dist < best_dist:
                best = h
                best_dist = dist
        if best is not None:
            # prefer highest confidence if multiple
            if cols[best] is None:
                cols[best] = e["text"].strip()
            else:
                # keep longer / higher confidence
                if len(e["text"].strip()) > len(cols[best]):
                    cols[best] = e["text"].strip()
    return cols


def normalize_code(code):
    """Remove dashes from brand codes like H-44 → H44, C-51 → C51."""
    if not code:
        return code
    # Remove dashes from codes, but preserve slashes for variants like H-47/H-460
    return code.replace("-", "")


def split_concatenated_codes(code_string):
    """Split concatenated brand codes like 'FS35352RLM 65' into separate codes.

    Handles patterns:
    - FS35352RLM 65 → ['FS 35352', 'RLM 65']
    - FS34095RAL 6020RLM 82 → ['FS 34095', 'RAL 6020', 'RLM 82']
    - FS 26373BS 627 → ['FS 26373', 'BS 627']
    - C3/C79/C114 → ['C3', 'C79', 'C114'] (slashed codes)

    Returns a list of code strings.
    """
    if not code_string:
        return []

    code_string = code_string.strip()

    # Handle slashed codes (e.g., C3/C79/C114 for Vallejo variants)
    if "/" in code_string:
        return [c.strip() for c in code_string.split("/") if c.strip()]

    # Find all brand code patterns
    codes = []
    text = code_string.upper()

    # Patterns: FS, RAL, RLM, BS, etc. followed by optional space/dash and digits
    pattern = r"(FS|RAL|RLM|BS|HI|MR|XF)\s*[-\s]?(\d+)"

    for match in re.finditer(pattern, text):
        brand = match.group(1)
        code = match.group(2)

        # Format appropriately
        if brand == "RLM":
            codes.append(f"RLM {code}")
        elif brand == "RAL":
            codes.append(f"RAL {code}")
        elif brand == "FS":
            codes.append(f"FS {code}")
        elif brand == "BS":
            codes.append(f"BS {code}")
        else:
            codes.append(f"{brand}{code}")

    # If no patterns matched, return the original string
    if not codes:
        codes = [code_string]

    return codes


def parse_definition_equivalents(definition):
    """Parse a concatenated definition string like 'FS34082-RAL 6003-RLM 03' into
    separate equivalent entries for FS, RAL and RLM brands.

    Returns a list of {brand, code} dicts (empty if nothing matched).
    """
    if not definition:
        return []
    equivs = []
    seen = set()
    text = definition.upper()
    for m in re.finditer(r"FS[-\s]?(\d{5})", text):
        code = f"FS {m.group(1)}"
        if code not in seen:
            seen.add(code)
            equivs.append({"brand": "Federal Standard", "code": code})
    for m in re.finditer(r"RAL[-\s]?(\d{4})", text):
        code = f"RAL {m.group(1)}"
        if code not in seen:
            seen.add(code)
            equivs.append({"brand": "RAL", "code": code})
    for m in re.finditer(r"RLM[-\s]?(\d{2,3})", text):
        code = f"RLM-{m.group(1).zfill(2)}"
        if code not in seen:
            seen.add(code)
            equivs.append({"brand": "RLM", "code": code})
    return equivs


def normalize_reference(ref):
    if not ref:
        return None
    s = ref.strip().upper()
    # remove dots and spaces
    s = s.replace(".", "").replace(" ", "")
    # remove leading 'A' if present before MIG/AMIG
    if s.startswith("AMIG"):
        s = "MIG" + s[4:]
    if s.startswith("A M I G"):
        s = s.replace("A M I G", "MIG")

    # try to extract trailing numeric part
    import re

    m = re.search(r"([0-9OQIlgGBSZ]+)$", s)
    if m:
        num = m.group(1)
        trans = str.maketrans(
            {
                "O": "0",
                "Q": "0",
                "I": "1",
                "L": "1",
                "G": "9",
                "g": "9",
                "B": "8",
                "S": "5",
                "Z": "2",
                "o": "0",
                "l": "1",
            }
        )
        num2 = num.translate(trans)
        num2 = re.sub(r"\D", "", num2)
        if not num2:
            return s
        num2 = num2.zfill(4)
        return f"MIG-{num2}"

    digits = re.findall(r"\d+", s)
    if digits:
        num2 = digits[-1].zfill(4)
        return f"MIG-{num2}"

    return s


def parse_catalog():
    if not IN_FILE.exists():
        print("Input catalog not found:", IN_FILE)
        return
    catalog = json.loads(IN_FILE.read_text())
    rows_out = []

    for img in catalog.get("images", []):
        text_entries = img.get("text_entries", [])
        matches = img.get("matches", [])

        headers_map = detect_headers(text_entries)
        # fallback: if headers missing, estimate by top row words
        if not headers_map:
            # try first 10 entries as headers
            top = sorted(text_entries, key=lambda e: e["bbox"]["y"])[:10]
            headers_map = {t["text"].strip().upper(): center(t)[0] for t in top}

        # cluster text entries into rows
        non_header = [
            e for e in text_entries if e["text"].strip().upper() not in headers_map
        ]
        clusters = cluster_rows(non_header)

        # Build row dicts
        for cluster in clusters:
            cols = assign_columns(cluster, headers_map)
            raw_reference = cols.get("REFERENCE") or cols.get("REF") or None
            reference = normalize_reference(raw_reference) if raw_reference else None
            name = cols.get("COLOR NAME") or cols.get("COLOR") or None
            definition = cols.get("RAL/RLMFS") or cols.get("RAL") or None
            # compute average confidence for cluster
            try:
                confidence = mean([e.get("confidence", 0) for e in cluster])
            except Exception:
                confidence = None
            equivalents = []
            for key in (
                "HOBBY COLOR",
                "MR.COLOR",
                "TAMIYA",
                "MODEL COLOR",
                "MODEL AIR",
            ):
                v = cols.get(key)
                if v:
                    # Split any concatenated codes (e.g., "FS35352RLM 65" → ["FS 35352", "RLM 65"])
                    split_codes = split_concatenated_codes(v)

                    for code_str in split_codes:
                        code_str = code_str.strip()
                        if not code_str:
                            continue

                        # Determine if this is a standard brand code (FS, RAL, RLM, BS) or a variant code
                        code_upper = code_str.upper()
                        brand_to_use = key  # default to the column name

                        # Check if code matches a known brand pattern
                        if code_upper.startswith("FS ") or code_upper.startswith("FS"):
                            brand_to_use = "Federal Standard"
                            code_str = normalize_code(code_str)
                        elif code_upper.startswith("RAL"):
                            brand_to_use = "RAL"
                            code_str = normalize_code(code_str)
                        elif code_upper.startswith("RLM"):
                            brand_to_use = "RLM"
                            code_str = normalize_code(code_str)
                        elif code_upper.startswith("BS"):
                            brand_to_use = "British Standard"
                            code_str = normalize_code(code_str)
                        else:
                            code_str = normalize_code(code_str)

                        equivalents.append({"brand": brand_to_use, "code": code_str})

            # Parse FS/RAL/RLM codes out of the definition column
            equivalents.extend(parse_definition_equivalents(definition))

            # If the visible color name contains an RLM code (e.g. "RLM-02"),
            # add it as an equivalent. This is useful for Gunze/table rows.
            if name:
                mrlm = re.search(r"RLM[-\s]?(\d{3})", name.upper())
                if mrlm:
                    rl = mrlm.group(1)
                    equivalents.append({"brand": "RLM", "code": f"RLM-{rl}"})

            # find swatch corresponding to the sample column (third column)
            cy = mean([e["bbox"]["y"] for e in cluster])
            hex_color = None
            # Prefer swatch nearest to the 'RAL/RLMFS' header x position (third column)
            header_x = headers_map.get("RAL/RLMFS") or headers_map.get("RAL")

            # detect if this image is a table-like layout (brand or filename hints)
            fname = img.get("filename", "").lower() if img.get("filename") else ""
            source = img.get("source", "").lower() if img.get("source") else ""
            brand_id = img.get("brand_id", "").lower() if img.get("brand_id") else ""
            is_table = any(
                b in fname or b in source or b == brand_id for b in TABLE_BRANDS
            )

            best = None
            best_score = None

            # compute desired left x coordinate if using table-left strategy
            left_x = None
            if is_table and matches:
                # TABLE_LEFT_POS <=1 -> fraction of image width; else absolute px
                img_w = img.get("width")
                if 0 < TABLE_LEFT_POS <= 1.0 and img_w:
                    left_x = TABLE_LEFT_POS * img_w
                else:
                    left_x = TABLE_LEFT_POS

            for m in matches:
                sw = m.get("swatch")
                if not sw:
                    continue
                sw_cx = sw["x"] + sw["width"] / 2
                sw_cy = sw["y"] + sw["height"] / 2
                dy = abs(sw_cy - cy)

                if left_x is not None:
                    # prefer swatches that cover the left_x (inside bbox)
                    if sw["x"] <= left_x <= sw["x"] + sw["width"]:
                        score = (
                            dy  # purely vertical proximity when horizontally matched
                        )
                    else:
                        dx = abs((sw["x"] + sw["width"] / 2) - left_x)
                        score = dy + dx * 0.8
                else:
                    dx = abs(sw_cx - (header_x if header_x is not None else sw_cx))
                    # score favors vertical proximity and somewhat horizontal proximity to header
                    score = dy + dx * 0.5

                if dy <= 80 and (best_score is None or score < best_score):
                    best_score = score
                    best = sw
            if best is not None:
                hex_color = best.get("hex")

            row = {
                "image": img.get("filename"),
                "raw_reference": raw_reference,
                "reference": reference,
                "name": name,
                "definition": definition,
                "equivalents": equivalents,
                "hex": hex_color,
                "confidence": confidence,
            }
            # Only include rows that look like a color row (has reference or hex or name)
            if reference or name or hex_color:
                rows_out.append(row)

    # write outputs
    OUT_JSON.parent.mkdir(parents=True, exist_ok=True)
    OUT_JSON.write_text(json.dumps(rows_out, indent=2, ensure_ascii=False))

    # write CSV
    with OUT_CSV.open("w", newline="") as f:
        writer = csv.writer(f)
        writer.writerow(
            [
                "image",
                "raw_reference",
                "reference",
                "name",
                "definition",
                "equivalents",
                "hex",
                "confidence",
            ]
        )
        for r in rows_out:
            eq = "; ".join([f"{e['brand']}:{e['code']}" for e in r["equivalents"]])
            writer.writerow(
                [
                    r.get("image"),
                    r.get("raw_reference"),
                    r.get("reference"),
                    r.get("name"),
                    r.get("definition"),
                    eq,
                    r.get("hex"),
                    r.get("confidence"),
                ]
            )

    print(f"Wrote {len(rows_out)} rows to {OUT_JSON} and {OUT_CSV}")


if __name__ == "__main__":
    parse_catalog()
