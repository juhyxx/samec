#!/usr/bin/env python3
"""
Parse images in source/hobby-color -> extract OCR, detect swatches and produce rows JSON/CSV.
"""
from pathlib import Path
import json
from PIL import Image
import numpy as np
import easyocr
import cv2
from statistics import mean
import csv
import re

GUNZE_FOLDER = Path("source/hobby-color")
OUT_JSON = Path("data/gunze_rows.json")
OUT_CSV = Path("data/gunze_rows.csv")

# Fraction of image width to sample for left-column color swatch (configurable).
TABLE_LEFT_POS = 846

GUNZE_EQUIVALENT_COLUMNS = [
    {
        "key": "gunze",
        "brand": "Gunze / Mr. Color",
        "aliases": ["GUNZE"],
        "fallback_ratio": 0.54,
    },
    {
        "key": "tamiya",
        "brand": "Tamiya",
        "aliases": ["TAMIYA"],
        "fallback_ratio": 0.63,
    },
    {
        "key": "humbrol",
        "brand": "Humbrol",
        "aliases": ["HUMBROL"],
        "fallback_ratio": 0.73,
    },
    {
        "key": "revell",
        "brand": "Revell",
        "aliases": ["REVELL"],
        "fallback_ratio": 0.82,
    },
    {
        "key": "testors",
        "brand": "Testors",
        "aliases": ["TESTORS"],
        "fallback_ratio": 0.91,
    },
]


def rgb_to_hex(arr):
    return "#{:02x}{:02x}{:02x}".format(int(arr[0]), int(arr[1]), int(arr[2]))


def find_swatches(image_array, min_swatch_size=8):
    h, w, _ = image_array.shape
    # detect blue-border pixels and create a mask to ignore them
    blue_mask = np.zeros((h, w), dtype=bool)
    # blue criteria tuned for the catalogue frame
    rchan = image_array[:, :, 0].astype(int)
    gchan = image_array[:, :, 1].astype(int)
    bchan = image_array[:, :, 2].astype(int)
    blue_mask = (bchan > 90) & (bchan > rchan + 40) & (bchan > gchan + 40)
    # create a copy with blue pixels replaced by white to avoid clustering them
    proc = image_array.copy()
    proc[blue_mask] = [255, 255, 255]
    # Apply Gaussian blur to smooth noise and help detect swatches
    proc = cv2.GaussianBlur(proc, (5, 5), 0)
    small = cv2.resize(
        proc, (max(1, w // 4), max(1, h // 4)), interpolation=cv2.INTER_AREA
    )
    Z = small.reshape((-1, 3)).astype(np.float32)
    K = 8
    criteria = (cv2.TERM_CRITERIA_EPS + cv2.TERM_CRITERIA_MAX_ITER, 10, 1.0)
    _, labels, centers = cv2.kmeans(Z, K, None, criteria, 3, cv2.KMEANS_PP_CENTERS)
    centers = centers.astype(np.uint8)
    labels = labels.flatten().reshape(small.shape[0], small.shape[1])
    swatches = []
    for i in range(K):
        mask = (labels == i).astype("uint8") * 255
        mask_big = cv2.resize(mask, (w, h), interpolation=cv2.INTER_NEAREST)
        contours, _ = cv2.findContours(
            mask_big, cv2.RETR_EXTERNAL, cv2.CHAIN_APPROX_SIMPLE
        )
        for cnt in contours:
            x, y, ww, hh = cv2.boundingRect(cnt)
            if (
                ww >= min_swatch_size
                and hh >= min_swatch_size
                and ww * hh > min_swatch_size * min_swatch_size
            ):
                # reject regions that overlap the blue border by more than 20%
                area = ww * hh
                mask_region = blue_mask[y : y + hh, x : x + ww]
                blue_overlap = mask_region.sum()
                if blue_overlap / area > 0.2:
                    continue
                region = image_array[y : y + hh, x : x + ww]
                avg = region.reshape(-1, 3).mean(axis=0)
                swatches.append(
                    {
                        "x": int(x),
                        "y": int(y),
                        "width": int(ww),
                        "height": int(hh),
                        "rgb": [int(avg[0]), int(avg[1]), int(avg[2])],
                        "hex": rgb_to_hex(avg),
                    }
                )
    # dedupe
    uniq = []
    seen = set()
    for s in swatches:
        key = (s["x"], s["y"], s["width"], s["height"])
        if key in seen:
            continue
        seen.add(key)
        uniq.append(s)
    return uniq


def extract_ocr(img_path, reader):
    res = reader.readtext(str(img_path))
    out = []
    for bbox, text, conf in res:
        x_coords = [p[0] for p in bbox]
        y_coords = [p[1] for p in bbox]
        out.append(
            {
                "text": text.strip(),
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


def center_x(entry):
    bbox = entry["bbox"]
    return bbox["x"] + bbox["width"] / 2


def detect_gunze_column_centers(text_entries, image_width, image_height=1200):
    # Adaptive: top 15% of image height, minimum 190 px
    y_threshold = max(190, int(image_height * 0.15))
    header_entries = [e for e in text_entries if e["bbox"]["y"] <= y_threshold]
    centers = {}
    # Track the bottom edge of UNAMBIGUOUS column headers (not "GUNZE" which also
    # appears in title text like "GUNZE SANGYO..." and "GUNZE 10 ml ACRYLIC PAINTS").
    header_y_bottom = 0

    for column in GUNZE_EQUIVALENT_COLUMNS:
        # Prefer exact alias matches to avoid false positives from title text
        # (e.g. "GUNZE" should not match "GUNZE 10 ml ACRYLIC PAINTS")
        exact_matches = []
        partial_matches = []
        for entry in header_entries:
            text = entry["text"].strip().upper()
            for alias in column["aliases"]:
                if text == alias:
                    exact_matches.append(entry)
                    break
                elif alias in text:
                    partial_matches.append(entry)
                    break

        matched_entries = exact_matches if exact_matches else partial_matches
        if matched_entries:
            centers[column["key"]] = mean(center_x(e) for e in matched_entries)
            # Only use unambiguous columns (not "gunze") to set the header boundary,
            # because "GUNZE" also appears in brand-title text which sits higher.
            if column["key"] != "gunze":
                for e in matched_entries:
                    header_y_bottom = max(header_y_bottom, e["bbox"]["y_end"])
        else:
            centers[column["key"]] = image_width * column["fallback_ratio"]

    return centers, header_y_bottom


def normalize_gunze_equivalent_code(brand, text):
    if not text:
        return None

    code = text.strip().upper()
    code = code.replace(" ", "")
    code = code.replace("_", "")

    if code in {"-", "--"}:
        return None

    if brand == "Tamiya":
        # Cleanup for Tamiya
        code_clean = (
            code.replace("I", "1").replace("O", "0")
            if any(ch.isdigit() for ch in code)
            else code
        )
        code_clean = re.sub(r"^[^A-Z0-9]+|[^A-Z0-9/.-]+$", "", code_clean)
        code_clean = re.sub(r"\s*/\s*", "/", code_clean)
        match = re.match(r"^(XF|X)-?(\d+)$", code_clean)
        if match:
            return f"{match.group(1)}{match.group(2)}"

    if brand == "Gunze / Mr. Color":
        # Pre-correct common OCR misreads (O→0, I→1) before pattern matching,
        # so e.g. "H1O0" is found as "H100" instead of being truncated to "H10".
        code_pre = code.replace("I", "1").replace("O", "0")
        # Try: find ALL codes that start with H/C/S/M, then pick the longest (most complete) one
        code_matches = list(re.finditer(r"[HCSM]\d+[GO]?", code_pre))
        if code_matches:
            # Pick the last (rightmost) match, as it's likely the actual code
            code_pattern = code_matches[-1].group(0)
        else:
            code_pattern = code_pre

        # Now do the cleanup on the extracted pattern only
        code_clean = (
            code_pattern.replace("I", "1")
            if any(ch.isdigit() for ch in code_pattern)
            else code_pattern
        )
        code_clean = (
            code_clean.replace("O", "0")
            if any(ch.isdigit() for ch in code_clean)
            else code_clean
        )
        code_clean = re.sub(r"^[^A-Z0-9]+|[^A-Z0-9/.-]+$", "", code_clean)
        code_clean = re.sub(r"\s*/\s*", "/", code_clean)

        # Try direct match first
        match = re.match(r"^([HCSM])[- ]?(\d{1,4})$", code_clean)
        if match:
            return f"{match.group(1)}{match.group(2)}"

        # OCR misreads '9' as 'g' and '0' as 'o' - fix these
        code_fixed = code_clean.replace("G", "9").replace("O", "0")
        match = re.match(r"^([HCSM])[- ]?(\d{1,4})$", code_fixed)
        if match:
            return f"{match.group(1)}{match.group(2)}"

    return code or None


def build_gunze_equivalents(cluster, column_centers):
    column_brand_map = {
        column["key"]: column["brand"] for column in GUNZE_EQUIVALENT_COLUMNS
    }
    ordered_columns = sorted(column_centers.items(), key=lambda item: item[1])
    equivalents = []
    seen_pairs = set()
    code = None

    for key, center in ordered_columns:
        matches = [
            entry
            for entry in cluster
            if abs(center_x(entry) - center) <= 120 and entry["text"].strip()
        ]
        if not matches:
            continue

        matches = sorted(matches, key=lambda entry: entry["bbox"]["x"])
        raw_text = " ".join(entry["text"].strip() for entry in matches).strip()
        normalized = normalize_gunze_equivalent_code(column_brand_map[key], raw_text)
        if not normalized:
            continue

        if key == "gunze":
            code = normalized
            continue

        pair = (column_brand_map[key], normalized)
        if pair in seen_pairs:
            continue
        seen_pairs.add(pair)
        equivalents.append({"brand": column_brand_map[key], "code": normalized})

    return code, equivalents


def detect_column_boundaries(text_entries, gap_threshold=40):
    if not text_entries:
        return []
    xs = sorted(
        [e["bbox"]["x"] for e in text_entries]
        + [e["bbox"]["x_end"] for e in text_entries]
    )
    xs = sorted(list(set(xs)))
    boundaries = []
    for i in range(len(xs) - 1):
        if xs[i + 1] - xs[i] > gap_threshold:
            boundaries.append((xs[i] + xs[i + 1]) / 2)
    return boundaries


def assign_to_columns(text_entries, column_boundaries):
    if not column_boundaries:
        return {0: text_entries}
    columns = {i: [] for i in range(len(column_boundaries) + 1)}
    for e in text_entries:
        cx = (e["bbox"]["x"] + e["bbox"]["x_end"]) / 2
        col = 0
        for bound in column_boundaries:
            if cx > bound:
                col += 1
        if col in columns:
            columns[col].append(e)
    return {k: v for k, v in columns.items() if v}


def cluster_rows(text_entries, y_tol=18):
    entries = sorted(text_entries, key=lambda e: e["bbox"]["y"])
    rows = []
    cur = []
    last = None
    for e in entries:
        y = e["bbox"]["y"]
        if last is None or abs(y - last) <= y_tol:
            cur.append(e)
            last = mean([it["bbox"]["y"] for it in cur])
        else:
            rows.append(cur)
            cur = [e]
            last = e["bbox"]["y"]
    if cur:
        rows.append(cur)
    return rows


def match_swatches(swatches, row_y, header_x=None):
    best = None
    best_score = None
    for s in swatches:
        cx = s["x"] + s["width"] / 2
        cy = s["y"] + s["height"] / 2
        dy = abs(cy - row_y)
        dx = abs(cx - (header_x if header_x is not None else cx))
        score = dy + 0.5 * dx
        if dy <= 80 and (best_score is None or score < best_score):
            best_score = score
            best = s
    return best


def parse_image(img_path, reader):
    with Image.open(img_path) as im:
        if im.mode != "RGB":
            im = im.convert("RGB")
        arr = np.array(im)
    text_entries = extract_ocr(img_path, reader)
    swatches = find_swatches(arr)
    valid_entries = [e for e in text_entries if len(e["text"].strip()) > 0]
    column_centers, header_y_bottom = detect_gunze_column_centers(
        valid_entries, arr.shape[1], arr.shape[0]
    )
    # detect columns first for better structure
    col_bounds = detect_column_boundaries(valid_entries, gap_threshold=40)
    col_groups = assign_to_columns(valid_entries, col_bounds)
    clusters = cluster_rows(valid_entries)
    rows = []
    # attempt to guess headers by topmost texts
    top = sorted(text_entries, key=lambda e: e["bbox"]["y"])[:8]
    header_xs = {
        t["text"].strip().upper(): (t["bbox"]["x"] + t["bbox"]["width"] / 2)
        for t in top
    }
    sample_header_x = (
        header_xs.get("SAMPLE")
        or header_xs.get("COLOR SAMPLE")
        or list(header_xs.values())[2]
        if len(header_xs) >= 3
        else None
    )
    # Use detected column-header bottom as cutoff; fall back to a small fixed value
    # when no column headers exist (pages 2+ have no header row).
    header_cutoff = (header_y_bottom + 5) if header_y_bottom > 0 else 40
    for cluster in clusters:
        row_y = mean([e["bbox"]["y"] for e in cluster])
        if row_y <= header_cutoff:
            continue

        # assemble text by nearest column
        texts = [(c["text"], c["bbox"]) for c in cluster]
        # pick probable reference as left-most short token
        cluster_sorted = sorted(cluster, key=lambda e: e["bbox"]["x"])
        name_tokens = [
            entry["text"].strip()
            for entry in cluster_sorted
            if entry["text"].strip() and center_x(entry) < column_centers["gunze"] - 120
        ]
        display_name = " ".join(name_tokens).strip()
        display_name = re.sub(r"^[\(I\[]+", "", display_name).strip()

        code, equivalents = build_gunze_equivalents(cluster_sorted, column_centers)
        if not code:
            continue

        # Extract RLM / FS equivalents from display name.
        # Examples: "RLM-02 Grau", "RLM02", "FS 34092 Olive Drab", "FS34092"
        if display_name:
            mrlm = re.search(r"\bRLM[-\s]?(\d{2,3})\b", display_name.upper())
            if mrlm:
                equivalents.append(
                    {"brand": "RLM", "code": f"RLM-{mrlm.group(1).zfill(3)}"}
                )
            mfs = re.search(r"\bFS[-\s]?(\d{5})\b", display_name.upper())
            if mfs:
                equivalents.append(
                    {"brand": "Federal Standard", "code": f"FS {mfs.group(1)}"}
                )

        # Always sample a pixel at sample_header_x (or TABLE_LEFT_POS) — no K-means needed.
        h, w, _ = arr.shape
        sx = int(TABLE_LEFT_POS)
        sy = int(max(2, min(h - 3, int(row_y))))
        xs = [min(w - 1, max(0, sx + dx)) for dx in (-2, -1, 0, 1, 2)]
        ys = [min(h - 1, max(0, sy + dy)) for dy in (-2, -1, 0, 1, 2)]
        samples = [arr[y, x] for y in ys for x in xs]
        non_blue = [
            p
            for p in samples
            if not (
                int(p[2]) > 80
                and int(p[2]) > int(p[0]) + 30
                and int(p[2]) > int(p[1]) + 30
            )
        ]
        if non_blue:
            avg = np.mean(np.array(non_blue, dtype=np.float32), axis=0)
            hexv = rgb_to_hex(avg)
        else:
            px = arr[sy, sx]
            hexv = rgb_to_hex(px)
        conf = mean([e.get("confidence", 0) for e in cluster])
        rows.append(
            {
                "image": img_path.name,
                "raw_reference": " ".join(
                    entry["text"].strip()
                    for entry in cluster_sorted
                    if entry["text"].strip()
                ),
                "reference": code,
                "name": display_name,
                "equivalents": equivalents,
                "hex": hexv,
                "confidence": conf,
            }
        )
    return {
        "filename": img_path.name,
        "text_entries": text_entries,
        "swatches": swatches,
        "rows": rows,
    }


def parse_gunze_images(folder_path, output_json):
    folder = Path(folder_path)
    output_json = Path(output_json)
    data_dir = output_json.parent

    if not folder.exists():
        print("No gunze folder:", folder)
        return
    files = sorted(folder.glob("*.png"))
    if not files:
        print("No PNGs in", folder)
        return

    rows_json = data_dir / "gunze_rows.json"
    rows_csv = data_dir / "gunze_rows.csv"

    reader = easyocr.Reader(["en"], gpu=False)
    all_rows = []
    for f in files:
        print("Processing", f.name)
        res = parse_image(f, reader)
        for r in res["rows"]:
            all_rows.append(r)
    rows_json.parent.mkdir(parents=True, exist_ok=True)
    rows_json.write_text(json.dumps(all_rows, indent=2, ensure_ascii=False))
    with rows_csv.open("w", newline="") as fh:
        w = csv.writer(fh)
        w.writerow(
            [
                "image",
                "raw_reference",
                "reference",
                "name",
                "equivalents",
                "hex",
                "confidence",
            ]
        )
        for r in all_rows:
            eq = "; ".join(
                [f"{e['brand']}:{e['code']}" for e in r.get("equivalents", [])]
            )
            w.writerow(
                [
                    r.get("image"),
                    r.get("raw_reference"),
                    r.get("reference"),
                    r.get("name"),
                    eq,
                    r.get("hex"),
                    r.get("confidence"),
                ]
            )
    print("Wrote", rows_json, "and", rows_csv)

    # --- Resolve gray-like Gunze entries (previously in resolve_gunze_fs.py) ---
    FS_TO_HEX = {
        "11136": "#cc0000",
        "13538": "#ffff00",
        "15044": "#1f45a3",
        "15050": "#000066",
        "16081": "#5a5a5a",
        "26440": "#888888",
        "34087": "#7cb342",
        "34092": "#556b2f",
        "34097": "#4a7023",
        "34102": "#6b8e23",
        "35237": "#556b7d",
        "36081": "#696969",
        "36231": "#c89860",
        "36495": "#c0c0c0",
    }

    BS_TO_HEX = {
        "C627": "#808080",
        "C636": "#4682b4",
        "C637": "#6b6b6b",
        "C638": "#575757",
        "C640": "#2f4f4f",
        "C641": "#2f4f4f",
        "18B21": "#8b7355",
        "10B21": "#a0826d",
    }

    GRAY_LIKE = {
        "#808080",
        "#7e7e7e",
        "#6f6f6f",
        "#6a6a6a",
        "#5f5f5f",
        "#4c4c4c",
        "#c9c9c9",
        "#9b9b9b",
        "#909090",
        "#535353",
        "#464646",
        "#929292",
        "#656565",
        "#595959",
        "#4b4b4b",
        "#a8a8a8",
        "#b0b0b0",
        "#a2a2a2",
        "#a1a1a1",
        "#4a4a4a",
        "#939393",
        "#6e6e6e",
        "#6d6d6d",
        "#ababab",
        "#797979",
    }

    updated = 0
    for r in all_rows:
        hex_val = r.get("hex", "")
        if hex_val not in GRAY_LIKE:
            continue

        raw_ref = r.get("raw_reference", "")

        fs_match = re.search(r"FS[\s-]?(\d{5})", raw_ref)
        if fs_match and fs_match.group(1) in FS_TO_HEX:
            r["hex"] = FS_TO_HEX[fs_match.group(1)]
            updated += 1
            continue

        for bs_key in BS_TO_HEX:
            if bs_key in raw_ref:
                r["hex"] = BS_TO_HEX[bs_key]
                updated += 1
                break

    if updated:
        rows_json.write_text(json.dumps(all_rows, indent=2, ensure_ascii=False))
        print(f"Resolved {updated} gray-like Gunze entries and updated {rows_json}")

    # --- Prepare frontend pack ---
    colors = []

    def _normalize_code_token(tok: str) -> str:
        if not tok:
            return tok
        t = tok.strip()
        if re.search(r"\d", t) or len(t) <= 4:
            t = (
                t.replace("I", "1")
                .replace("l", "1")
                .replace("O", "0")
                .replace("o", "0")
            )
        t = re.sub(r"^[^A-Za-z0-9]+|[^A-Za-z0-9]+$", "", t)
        t = re.sub(r"[\s\._]+", "-", t)
        m = re.match(r"^([A-Za-z]{1,3}-?\d{1,4})", t)
        if m:
            return m.group(1)
        return t

    def _is_code_like(tok: str) -> bool:
        if not tok:
            return False
        t = _normalize_code_token(tok)
        if re.match(r"^[A-Za-z]{1,3}-?\d{1,4}$", t):
            return True
        if re.match(r"^\d{1,3}[\.]?\d{1,3}$", t):
            return True
        return False

    for r in all_rows:
        code = _normalize_code_token((r.get("reference") or "").strip()).upper()
        display_name = (r.get("name") or "").strip()

        if not code or not str(code).upper().startswith("H"):
            continue
        if not display_name or len(display_name.strip()) < 2:
            continue

        hexv = r.get("hex") or None
        if hexv and not str(hexv).startswith("#"):
            hexv = "#" + str(hexv)

        colors.append(
            {
                "code": code,
                "name": display_name,
                "hex": hexv,
                "equivalents": r.get("equivalents", []),
                "confidence": r.get("confidence"),
            }
        )

    pack = {
        "brand": "Gunze Sangyo",
        "brand_id": "gunze",
        "source": str(output_json),
        "count": len(colors),
        "colors": colors,
    }
    output_json.parent.mkdir(parents=True, exist_ok=True)
    output_json.write_text(json.dumps(pack, indent=2, ensure_ascii=False))
    print("Wrote", output_json)

    csv_path = output_json.parent / "pack_gunze.csv"
    with csv_path.open("w", newline="") as fh:
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
    print("Wrote", csv_path)

    return colors


def main():
    parse_gunze_images(GUNZE_FOLDER, Path("data/pack_gunze.json"))


if __name__ == "__main__":
    main()
