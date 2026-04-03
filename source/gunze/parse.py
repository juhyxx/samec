#!/usr/bin/env python3
"""
Parse images in source/gunze -> extract OCR, detect swatches and produce rows JSON/CSV.
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

GUNZE_FOLDER = Path("source/gunze")
OUT_JSON = Path("data/gunze_rows.json")
OUT_CSV = Path("data/gunze_rows.csv")


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
    for cluster in clusters:
        # assemble text by nearest column
        texts = [(c["text"], c["bbox"]) for c in cluster]
        # pick probable reference as left-most short token
        ref = None
        name = None
        cluster_sorted = sorted(cluster, key=lambda e: e["bbox"]["x"])
        if cluster_sorted:
            ref = cluster_sorted[0]["text"]
            # take more tokens for multi-word names (up to 4 tokens after the code)
            name = " ".join([e["text"] for e in cluster_sorted[1:5]])
        cy = mean([e["bbox"]["y"] for e in cluster])
        sw = match_swatches(swatches, cy, header_x=sample_header_x)
        hexv = sw["hex"] if sw else None
        # If no swatch was detected, try sampling a small region inside the sample column
        if not hexv:
            h, w, _ = arr.shape
            try:
                # Determine a sample x by taking midpoint between left-most and right-most text in the cluster
                if len(cluster_sorted) >= 2:
                    left = cluster_sorted[0]["bbox"]
                    right = cluster_sorted[-1]["bbox"]
                    sx = int((left["x_end"] + right["x"]) / 2)
                elif sample_header_x is not None:
                    sx = int(sample_header_x)
                else:
                    sx = int(min(w - 1, max(5, w // 3)))
                sy = int(max(2, min(h - 3, int(cy))))
                # sample a small 5x5 region and ignore blue-frame pixels (edges)
                xs = [min(w - 1, max(0, sx + dx)) for dx in (-2, -1, 0, 1, 2)]
                ys = [min(h - 1, max(0, sy + dy)) for dy in (-2, -1, 0, 1, 2)]
                samples = [arr[y, x] for y in ys for x in xs]

                def _is_blue_edge(p):
                    r, g, b = int(p[0]), int(p[1]), int(p[2])
                    # blue edge criteria: strong blue channel and significantly higher than R/G
                    return (b > 80) and (b > r + 30) and (b > g + 30)

                non_blue = [p for p in samples if not _is_blue_edge(p)]
                if non_blue:
                    avg = np.mean(np.array(non_blue, dtype=np.float32), axis=0)
                    hexv = rgb_to_hex(avg)
                else:
                    # fallback: take center pixel if all sampled pixels are blue edges
                    px = arr[sy, sx]
                    hexv = rgb_to_hex(px)
            except Exception:
                hexv = None
        conf = mean([e.get("confidence", 0) for e in cluster])
        rows.append(
            {
                "image": img_path.name,
                "raw_reference": ref,
                "reference": ref,
                "name": name,
                "equivalents": [],
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


def main():
    if not GUNZE_FOLDER.exists():
        print("No gunze folder:", GUNZE_FOLDER)
        return
    files = sorted(GUNZE_FOLDER.glob("*.png"))
    if not files:
        print("No PNGs in", GUNZE_FOLDER)
        return
    reader = easyocr.Reader(["en"], gpu=False)
    all_rows = []
    for f in files:
        print("Processing", f.name)
        res = parse_image(f, reader)
        for r in res["rows"]:
            all_rows.append(r)
    OUT_JSON.parent.mkdir(parents=True, exist_ok=True)
    OUT_JSON.write_text(json.dumps(all_rows, indent=2, ensure_ascii=False))
    with OUT_CSV.open("w", newline="") as fh:
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
    print("Wrote", OUT_JSON, "and", OUT_CSV)

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
        OUT_JSON.write_text(json.dumps(all_rows, indent=2, ensure_ascii=False))
        print(f"Resolved {updated} gray-like Gunze entries and updated {OUT_JSON}")

    # --- Prepare frontend pack (previously in prepare_frontend.py) ---
    PACK_OUT = Path("data/pack_gunze.json")
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
        raw_name = (r.get("raw_reference") or r.get("reference") or "").strip()
        code_field = (r.get("name") or "").strip()
        code = None
        display_name = raw_name

        if code_field and _is_code_like(code_field):
            code = _normalize_code_token(code_field).upper()
            display_name = raw_name or code
        else:
            tokens = raw_name.split()
            for i in range(1, min(4, len(tokens) + 1)):
                cand = tokens[-i]
                if _is_code_like(cand):
                    code = _normalize_code_token(cand).upper()
                    display_name = " ".join(tokens[:-i]).strip() or raw_name
                    break
            if not code:
                if code_field:
                    code = _normalize_code_token(code_field).upper()
                else:
                    code = raw_name

        if display_name:
            display_name = re.sub(r"^\s*[Il](?=[A-Z])", "", display_name)
            display_name = re.sub(r"^[^A-Za-z0-9]+", "", display_name)
            display_name = re.sub(r"[^A-Za-z0-9\s-]+$", "", display_name).strip()
            toks = display_name.split()
            while toks and _is_code_like(toks[-1]):
                toks.pop()
            display_name = " ".join(toks).strip()

        if not display_name:
            rn = raw_name
            rn = re.sub(r"[^A-Za-z0-9\s\-]+$", "", rn).strip()
            parts = rn.split()
            if parts and _is_code_like(parts[-1]):
                parts = parts[:-1]
            display_name = " ".join(parts).strip() or raw_name

        if display_name and re.match(r"^I(?=[A-Z])", display_name):
            toks = raw_name.split()
            toks = [t for t in toks if not re.match(r"^I(?=[A-Z])", t)]
            display_name = " ".join(toks).strip()

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
        "source": str(OUT_JSON),
        "count": len(colors),
        "colors": colors,
    }
    PACK_OUT.parent.mkdir(parents=True, exist_ok=True)
    PACK_OUT.write_text(json.dumps(pack, indent=2, ensure_ascii=False))
    print("Wrote", PACK_OUT)


if __name__ == "__main__":
    main()
