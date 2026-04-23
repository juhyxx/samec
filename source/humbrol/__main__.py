#!/usr/bin/env python3
"""
Humbrol PDF color parser.

Process:
  1. Render source/humbrol/humbrol.pdf to .tmp/humbrol/ at 300 DPI (skipped if
     files already exist).
  2. Skip page 1 (cover).
  3. Pages 2-7: color swatch grid -> extract code, name, finish via OCR;
     hex color taken directly from PDF vector fills (exact, no rendering artefacts).
  4. Pages 8-12: cross-reference table -> extract code, finish, hex (HEX Code
     column) and cross-brand equivalents via OCR.
  5. Merge by Humbrol code: swatch-page data wins for name/finish;
     hex from equivalents table (column value) overrides swatch vector fill when
     available.
"""

from pathlib import Path
from statistics import mean
import json
import re
import csv

import pymupdf  # PyMuPDF >=1.24
from PIL import Image
import numpy as np
import cv2
import easyocr


# ── Paths ────────────────────────────────────────────────────────────────────
PDF_PATH = Path("source/humbrol/humbrol.pdf")
TMP_DIR = Path(".tmp/humbrol")
OUT_JSON = Path("data/pack_humbrol.json")
OUT_CSV = Path("data/pack_humbrol.csv")

# ── Page layout constants ─────────────────────────────────────────────────────
DPI = 300
SCALE = DPI / 72.0  # PDF points -> pixel scale factor

# Swatch rectangle dimensions in PDF points (approximate, used for detection)
SWATCH_W_MIN, SWATCH_W_MAX = 80.0, 100.0
SWATCH_H_MIN, SWATCH_H_MAX = 24.0, 35.0

# ── Finish labels ─────────────────────────────────────────────────────────────
_FINISH_WORDS = {"matt", "gloss", "satin", "metallic", "metalcote", "metal"}

# ── Equivalents patterns ──────────────────────────────────────────────────────
_EQUIVALENT_PATTERNS = [
    (
        re.compile(r"^(LP|XF|X)(\d{1,3})$"),
        "Tamiya",
        lambda m: f"{m.group(1)}{m.group(2)}",
    ),
    (re.compile(r"^H(\d{1,3})$"), "Gunze Sangyo", lambda m: f"H{m.group(1)}"),
    (re.compile(r"^C(\d{1,3})$"), "Mr. Color", lambda m: f"C{m.group(1)}"),
    (re.compile(r"^AK(\d{4,5})$"), "AK Interactive", lambda m: f"AK{m.group(1)}"),
    (re.compile(r"^7\d\.\d{3}$"), "Vallejo", lambda m: m.group(0)),
    (
        re.compile(r"^(\d{4})$"),
        "RAL",
        lambda m: f"RAL {m.group(1)}" if 1000 <= int(m.group(1)) <= 9999 else None,
    ),
    (re.compile(r"^RLM[-]?(\d{2,3})$"), "RLM", lambda m: f"RLM-{m.group(1)}"),
    (re.compile(r"^(\d{5})$"), "Federal Standard", lambda m: f"FS {m.group(1)}"),
    (re.compile(r"^BS(\d{3,4})$"), "British Standard", lambda m: f"BS{m.group(1)}"),
]

_HEX_RE = re.compile(r"^[0-9A-Fa-f]{6}$")


# ── Helpers ──────────────────────────────────────────────────────────────────


def _fill_to_hex(fill_rgb):
    r, g, b = fill_rgb[0], fill_rgb[1], fill_rgb[2]
    return "#{:02x}{:02x}{:02x}".format(int(r * 255), int(g * 255), int(b * 255))


def _clean_hex(text):
    t = text.strip().upper().lstrip("#")
    t = t.replace("O", "0").replace("I", "1").replace("L", "1").replace("S", "5")
    return f"#{t}" if _HEX_RE.match(t) else None


def _try_match_equivalent(text):
    t_clean = text.strip().upper().replace("-", "").replace(" ", "")
    t_orig = text.strip().upper()
    for pattern, brand, formatter in _EQUIVALENT_PATTERNS:
        for candidate in (t_clean, t_orig):
            m = pattern.match(candidate)
            if m:
                code = formatter(m)
                if code:
                    return {"brand": brand, "code": code}
    return None


def _cluster_rows(entries, y_tol=18):
    if not entries:
        return []
    sorted_e = sorted(entries, key=lambda e: e["bbox"]["y"])
    rows, cur, last_y = [], [], None
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


def _ocr_image_array(image_array, reader):
    results = reader.readtext(image_array, detail=1)
    out = []
    for bbox, text, conf in results:
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


# ── Step 1: PDF rendering ─────────────────────────────────────────────────────


def render_pdf_pages(pdf_path=PDF_PATH, out_dir=TMP_DIR, dpi=DPI, force=False):
    """Render every PDF page to PNG in out_dir. Skips existing files."""
    out_dir.mkdir(parents=True, exist_ok=True)
    doc = pymupdf.open(str(pdf_path))
    mat = pymupdf.Matrix(dpi / 72, dpi / 72)
    paths = []
    for i, page in enumerate(doc):
        dest = out_dir / f"page_{i + 1:02d}.png"
        if not dest.exists() or force:
            pix = page.get_pixmap(matrix=mat)
            pix.save(str(dest))
            print(f"  rendered page {i + 1} -> {dest.name}")
        paths.append(dest)
    return paths


# ── Step 2: Parse swatch pages ────────────────────────────────────────────────


def _find_swatches_on_page(page):
    """Return swatch rects with fill hex, sorted top-to-bottom left-to-right."""
    swatches = []
    for d in page.get_drawings():
        fill = d.get("fill")
        rect = d.get("rect")
        if not fill or not rect:
            continue
        w = rect.x1 - rect.x0
        h = rect.y1 - rect.y0
        if not (
            SWATCH_W_MIN <= w <= SWATCH_W_MAX and SWATCH_H_MIN <= h <= SWATCH_H_MAX
        ):
            continue
        r, g, b = fill[0], fill[1], fill[2]
        if r > 0.95 and g > 0.95 and b > 0.95:  # skip near-white
            continue
        swatches.append(
            {"x": rect.x0, "y": rect.y0, "w": w, "h": h, "hex": _fill_to_hex(fill)}
        )
    return sorted(swatches, key=lambda s: (round(s["y"], 1), s["x"]))


# ── Fixed parsing regions within the 3× upscaled full cell image ─────────────
# Coordinates were calibrated from rendered 300-DPI cells (upscaled 3×).
# Swatch colour is read from PDF vector data; pixel sample is a fallback.
_CELL_SWATCH_SAMPLE = (500, 200, 10, 10)  # (x, y, w, h) — centre of swatch
_CELL_NAME_REGION = (0, 418, 1116, 120)  # (x, y, w, h) — colour name text
_CELL_CODE_REGION = (0, 531, 360, 110)  # (x, y, w, h) — code + finish


def _crop_region(img, x, y, w, h):
    """Safe crop: clamps to image bounds."""
    ih, iw = img.shape[:2]
    x1, y1 = min(x + w, iw), min(y + h, ih)
    return img[max(0, y) : y1, max(0, x) : x1]


def _parse_cell_text(cell_img_rgb, reader):
    """
    Return (code, name, finish) from a 3× upscaled full-cell image.

    Parsing areas (calibrated pixel regions in the 3× upscaled cell):
      • Name  : _CELL_NAME_REGION
      • Code  : _CELL_CODE_REGION  (also contains finish word)
    """
    # ── Name ─────────────────────────────────────────────────────────────────
    nx, ny, nw, nh = _CELL_NAME_REGION
    name_region = _crop_region(cell_img_rgb, nx, ny, nw, nh)
    name = None
    if name_region.size:
        name_entries = _ocr_image_array(name_region, reader)
        name_parts = [
            e["text"].strip()
            for e in name_entries
            if not re.match(r"^(DB|AA|AD)\d+$", e["text"].strip(), re.IGNORECASE)
        ]
        name = " ".join(name_parts).strip() or None

    # ── Code + finish ─────────────────────────────────────────────────────────
    cx, cy, cw, ch = _CELL_CODE_REGION
    code_region = _crop_region(cell_img_rgb, cx, cy, cw, ch)
    code = None
    finish = None
    if code_region.size:
        code_entries = _ocr_image_array(code_region, reader)
        for e in sorted(code_entries, key=lambda e: e["bbox"]["x"]):
            t = e["text"].strip()
            if finish is None and t.lower() in _FINISH_WORDS:
                finish = t.capitalize()
            elif code is None and re.match(r"^\d{1,4}$", t):
                code = t

    return code, name, finish


def parse_swatch_pages(doc, page_indices, rendered_paths, reader):
    """Parse color swatch pages; returns list of {code, name, finish, hex}."""
    results = []

    for page_idx in page_indices:
        page = doc[page_idx]
        swatches = _find_swatches_on_page(page)
        if not swatches:
            continue

        print(f"  Page {page_idx + 1}: {len(swatches)} swatches")

        # Compute median row spacing
        y_positions = sorted(set(round(s["y"], 1) for s in swatches))
        if len(y_positions) > 1:
            gaps = [
                y_positions[i + 1] - y_positions[i] for i in range(len(y_positions) - 1)
            ]
            row_spacing = sorted(gaps)[len(gaps) // 2]
        else:
            row_spacing = 66.3

        with Image.open(rendered_paths[page_idx]) as im:
            img_rgb = np.array(im.convert("RGB"))

        for sw in swatches:
            # Crop full cell: from swatch top downward by row_spacing
            px0 = max(0, int(sw["x"] * SCALE))
            py0 = max(0, int(sw["y"] * SCALE))
            px1 = min(img_rgb.shape[1], int((sw["x"] + sw["w"]) * SCALE))
            py1 = min(img_rgb.shape[0], int((sw["y"] + row_spacing) * SCALE))

            cell_crop = img_rgb[py0:py1, px0:px1]
            if cell_crop.size == 0:
                continue

            # Upscale 3× so calibrated pixel regions apply
            ch_orig, cw_orig = cell_crop.shape[:2]
            cell_3x = cv2.resize(
                cell_crop, (cw_orig * 3, ch_orig * 3), interpolation=cv2.INTER_CUBIC
            )

            code, name, finish = _parse_cell_text(cell_3x, reader)
            results.append(
                {
                    "code": code,
                    "name": name or "",
                    "finish": finish or "",
                    "hex": sw["hex"],
                }
            )

    coded = sum(1 for r in results if r["code"])
    print(f"  -> {coded} / {len(results)} cells have a code")
    return results


# ── Step 3: Parse equivalents table pages ────────────────────────────────────


def parse_equivalents_pages(rendered_paths, page_indices, reader):
    """Parse cross-reference table pages; returns list of {code, finish, hex, equivalents}."""
    all_entries = []

    for page_idx in page_indices:
        print(f"  Page {page_idx + 1}: OCR equivalents table...")

        with Image.open(rendered_paths[page_idx]) as im:
            img_rgb = np.array(im.convert("RGB"))
            img_w = im.width

        entries = _ocr_image_array(img_rgb, reader)
        if not entries:
            continue

        min_y = min(e["bbox"]["y"] for e in entries)
        header_cutoff = min_y + 200

        rows = _cluster_rows(entries, y_tol=20)

        for row in rows:
            row_y = mean(e["bbox"]["y"] for e in row)
            if row_y <= header_cutoff:
                continue

            sorted_row = sorted(row, key=lambda e: e["bbox"]["x"])

            # Humbrol code: leftmost 1-3 digit number (1–250, no leading zeros)
            humbrol_code = None
            for e in sorted_row[:6]:
                t = re.sub(r"[()\[\]]", "", e["text"].strip())
                m = re.match(r"^(\d{1,3})$", t)
                if m:
                    val = int(m.group(1))
                    raw = m.group(1)
                    # Reject: zero or leading-zero strings (e.g. "06")
                    if val == 0 or (len(raw) > 1 and raw[0] == "0"):
                        continue
                    humbrol_code = raw
                    break
            if not humbrol_code:
                continue

            # Hex: rightmost 6-char hex token
            hex_color = None
            for e in reversed(sorted_row):
                h = _clean_hex(e["text"])
                if h:
                    hex_color = h
                    break

            # Finish
            finish = ""
            for e in sorted_row[:5]:
                if e["text"].strip().lower() in _FINISH_WORDS:
                    finish = e["text"].strip().capitalize()
                    break

            # Equivalents
            equivalents = []
            seen: set[tuple] = set()
            equiv_x_start = img_w * 0.08
            for e in sorted_row:
                if e["bbox"]["x"] < equiv_x_start:
                    continue
                if _clean_hex(e["text"]):
                    continue
                eq = _try_match_equivalent(e["text"])
                if not eq:
                    continue
                key = (eq["brand"], eq["code"])
                if key not in seen:
                    seen.add(key)
                    equivalents.append(eq)

            all_entries.append(
                {
                    "code": humbrol_code,
                    "finish": finish,
                    "hex": hex_color or "#cccccc",
                    "equivalents": equivalents,
                }
            )

    return all_entries


# ── Step 4: Merge ─────────────────────────────────────────────────────────────


def merge_results(swatch_entries, equiv_entries):
    """Merge swatch data (name, hex) with equivalents table (hex, equivalents)."""
    equiv_by_code: dict[str, dict] = {}
    for e in equiv_entries:
        c = e.get("code")
        if c and c not in equiv_by_code:
            equiv_by_code[c] = e

    merged = {}

    for sw in swatch_entries:
        code = sw.get("code")
        if not code:
            continue
        entry = {
            "code": code,
            "name": sw.get("name", ""),
            "finish": sw.get("finish", ""),
            "hex": sw.get("hex", "#cccccc"),
            "equivalents": [],
        }
        if code in equiv_by_code:
            eq = equiv_by_code[code]
            if eq.get("hex") and eq["hex"] != "#cccccc":
                entry["hex"] = eq["hex"]
            if not entry["finish"] and eq.get("finish"):
                entry["finish"] = eq["finish"]
            entry["equivalents"] = eq.get("equivalents", [])
        merged[code] = entry

    # Include codes only found in equivalents table
    for code, eq in equiv_by_code.items():
        if code not in merged:
            merged[code] = {
                "code": code,
                "name": "",
                "finish": eq.get("finish", ""),
                "hex": eq.get("hex", "#cccccc"),
                "equivalents": eq.get("equivalents", []),
            }

    return sorted(merged.values(), key=lambda c: int(c["code"]))


# ── Step 5: Export ────────────────────────────────────────────────────────────


def export_pack(colors, out_json=OUT_JSON, out_csv=OUT_CSV):
    out_json.parent.mkdir(parents=True, exist_ok=True)
    pack = {
        "brand": "Humbrol",
        "brand_id": "humbrol",
        "source": str(out_json),
        "count": len(colors),
        "colors": [
            {
                "code": c["code"],
                "name": c.get("name", ""),
                "hex": c["hex"],
                "equivalents": c.get("equivalents", []),
                "confidence": None,
            }
            for c in colors
        ],
    }
    out_json.write_text(json.dumps(pack, indent=2, ensure_ascii=False))
    print(f"Wrote {len(colors)} colors to {out_json}")

    with out_csv.open("w", newline="") as fh:
        w = csv.DictWriter(fh, fieldnames=["code", "name", "finish", "hex"])
        w.writeheader()
        for c in colors:
            w.writerow(
                {
                    "code": c["code"],
                    "name": c.get("name", ""),
                    "finish": c.get("finish", ""),
                    "hex": c["hex"],
                }
            )
    print(f"Wrote CSV to {out_csv}")


# ── Main entry point ──────────────────────────────────────────────────────────


def parse_humbrol_images(folder_path, output_json):
    """Pipeline entry point called by run_pipeline.py."""
    folder = Path(folder_path)
    pdf_path = folder / "humbrol.pdf"
    output_json = Path(output_json)

    if not pdf_path.exists():
        print(f"[humbrol] PDF not found: {pdf_path}")
        return []

    print(f"\nHumbrol parser — PDF: {pdf_path}")
    print("=" * 60)

    # Render
    print("Rendering PDF pages (skipping already-rendered)...")
    rendered = render_pdf_pages(pdf_path, TMP_DIR, DPI)

    doc = pymupdf.open(str(pdf_path))

    # Detect page types automatically
    swatch_page_indices = []
    equiv_page_indices = []
    for i in range(1, len(doc)):  # skip page 0 (cover)
        page = doc[i]
        sw_count = sum(
            1
            for d in page.get_drawings()
            if d.get("fill")
            and SWATCH_W_MIN <= (d["rect"].x1 - d["rect"].x0) <= SWATCH_W_MAX
            and SWATCH_H_MIN <= (d["rect"].y1 - d["rect"].y0) <= SWATCH_H_MAX
        )
        (swatch_page_indices if sw_count > 0 else equiv_page_indices).append(i)

    print(f"Swatch pages : {[i+1 for i in swatch_page_indices]}")
    print(f"Equiv. pages : {[i+1 for i in equiv_page_indices]}")

    reader = easyocr.Reader(["en"], gpu=False)

    print("\nParsing swatch pages...")
    swatch_colors = parse_swatch_pages(doc, swatch_page_indices, rendered, reader)

    print("\nParsing equivalents table pages...")
    equiv_colors = parse_equivalents_pages(rendered, equiv_page_indices, reader)

    print("\nMerging results...")
    colors = merge_results(swatch_colors, equiv_colors)
    print(f"  -> {len(colors)} unique Humbrol colors")

    out_json_path = Path(output_json)
    export_pack(colors, out_json_path, out_json_path.parent / "pack_humbrol.csv")

    return colors


def render_cell_sample(pdf_path=PDF_PATH, out_dir=TMP_DIR, cell_index=0):
    """
    Render the first (or nth) swatch cell from the first swatch page and save
    a debug PNG with all parsing regions highlighted:
      - SWATCH  : cyan  — pixel sample point (inflated to 20×20 for visibility)
      - NAME    : green — name OCR region
      - CODE    : red   — code + finish OCR region

    Output: <out_dir>/cell_sample_debug.png
    """
    rendered = render_pdf_pages(pdf_path, out_dir, DPI)
    doc = pymupdf.open(str(pdf_path))

    # Find first swatch page
    swatch_page_idx = None
    for i in range(1, len(doc)):
        page = doc[i]
        sw_count = sum(
            1
            for d in page.get_drawings()
            if d.get("fill")
            and SWATCH_W_MIN <= (d["rect"].x1 - d["rect"].x0) <= SWATCH_W_MAX
            and SWATCH_H_MIN <= (d["rect"].y1 - d["rect"].y0) <= SWATCH_H_MAX
        )
        if sw_count > 0:
            swatch_page_idx = i
            break

    if swatch_page_idx is None:
        print("No swatch page found.")
        return

    page = doc[swatch_page_idx]
    swatches = _find_swatches_on_page(page)
    if not swatches:
        print("No swatches found on page.")
        return

    sw = swatches[cell_index % len(swatches)]

    # Compute row spacing
    y_positions = sorted(set(round(s["y"], 1) for s in swatches))
    if len(y_positions) > 1:
        gaps = [
            y_positions[i + 1] - y_positions[i] for i in range(len(y_positions) - 1)
        ]
        row_spacing = sorted(gaps)[len(gaps) // 2]
    else:
        row_spacing = 66.3

    with Image.open(rendered[swatch_page_idx]) as im:
        img_rgb = np.array(im.convert("RGB"))

    px0 = max(0, int(sw["x"] * SCALE))
    py0 = max(0, int(sw["y"] * SCALE))
    px1 = min(img_rgb.shape[1], int((sw["x"] + sw["w"]) * SCALE))
    py1 = min(img_rgb.shape[0], int((sw["y"] + row_spacing) * SCALE))

    cell_crop = img_rgb[py0:py1, px0:px1]
    ch_orig, cw_orig = cell_crop.shape[:2]
    cell_3x = cv2.resize(
        cell_crop, (cw_orig * 3, ch_orig * 3), interpolation=cv2.INTER_CUBIC
    )

    # Draw regions on a BGR copy
    debug = cv2.cvtColor(cell_3x, cv2.COLOR_RGB2BGR)

    def draw_region(img, x, y, w, h, color, label):
        cv2.rectangle(img, (x, y), (x + w, y + h), color, 2)
        cv2.putText(
            img,
            label,
            (x + 4, max(y - 6, 12)),
            cv2.FONT_HERSHEY_SIMPLEX,
            0.55,
            color,
            1,
            cv2.LINE_AA,
        )

    # Swatch sample point (inflate for visibility)
    sx, sy, sw_w, sw_h = _CELL_SWATCH_SAMPLE
    draw_region(debug, sx - 10, sy - 10, 20, 20, (255, 200, 0), "SWATCH")

    # Name region
    draw_region(debug, *_CELL_NAME_REGION, (0, 200, 0), "NAME")

    # Code region
    draw_region(debug, *_CELL_CODE_REGION, (0, 0, 220), "CODE")

    out_path = out_dir / "cell_sample_debug.png"
    cv2.imwrite(str(out_path), debug)
    print(f"Saved debug cell image → {out_path}")
    print(f"  Cell #{cell_index}: hex={sw['hex']}  page {swatch_page_idx + 1}")
    print(f"  Cell size (3×): {cell_3x.shape[1]}×{cell_3x.shape[0]} px")


if __name__ == "__main__":
    import sys

    if "--cell-sample" in sys.argv or "--watch" in sys.argv:
        idx = 0
        watch = "--watch" in sys.argv
        flag = "--cell-sample" if "--cell-sample" in sys.argv else "--watch"
        try:
            idx = int(sys.argv[sys.argv.index(flag) + 1])
        except (IndexError, ValueError):
            pass

        render_cell_sample(cell_index=idx)

        if watch:
            import time as _time
            import subprocess

            src = Path(__file__)
            last_mtime = src.stat().st_mtime
            print(f"\nWatching {src.name} for changes — press Ctrl+C to stop...")
            try:
                while True:
                    _time.sleep(0.5)
                    mtime = src.stat().st_mtime
                    if mtime != last_mtime:
                        last_mtime = mtime
                        print(
                            f"\n[{_time.strftime('%H:%M:%S')}] File changed — re-rendering..."
                        )
                        subprocess.run(
                            [sys.executable, str(src), "--cell-sample", str(idx)],
                            check=False,
                        )
            except KeyboardInterrupt:
                print("\nWatch stopped.")
    else:
        parse_humbrol_images(PDF_PATH.parent, OUT_JSON)
