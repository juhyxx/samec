#!/usr/bin/env python3
"""Parse `data/ammo_catalog.json` into structured rows with code, name, equivalents, and hex."""
import json
from pathlib import Path
from statistics import mean
import csv


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
                    equivalents.append({"brand": key, "code": normalize_code(v)})

            # find swatch corresponding to the sample column (third column)
            cy = mean([e["bbox"]["y"] for e in cluster])
            hex_color = None
            # Prefer swatch nearest to the 'RAL/RLMFS' header x position (third column)
            header_x = headers_map.get("RAL/RLMFS") or headers_map.get("RAL")
            best = None
            best_score = None
            for m in matches:
                sw = m.get("swatch")
                sw_cx = sw["x"] + sw["width"] / 2
                sw_cy = sw["y"] + sw["height"] / 2
                dy = abs(sw_cy - cy)
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
