"""
Shared Vallejo PDF catalog parser.

All palette-specific __main__.py modules define a CONFIG dict and call run(cfg).
"""

import json
import csv
import re
from pathlib import Path

import fitz  # pymupdf
import numpy as np
import cv2
from PIL import Image, ImageDraw

# ── PDF rendering ──────────────────────────────────────────────────────────────


def render_pdf_pages(pdf_path, dpi, tmp_dir, force=False):
    """Render each PDF page to PNG (cached). Returns list of Paths."""
    tmp = Path(tmp_dir)
    tmp.mkdir(parents=True, exist_ok=True)
    doc = fitz.open(pdf_path)
    scale = dpi / 72.0
    mat = fitz.Matrix(scale, scale)
    rendered = []
    for i, page in enumerate(doc):
        out_path = tmp / f"page_{i:02d}.png"
        if out_path.exists() and not force:
            print(f"  [cache] {out_path.name}")
        else:
            print(f"  Rendering page {i} at {dpi} DPI → {out_path.name}")
            pix = page.get_pixmap(matrix=mat, alpha=False)
            pix.save(str(out_path))
        rendered.append(out_path)
    doc.close()
    return rendered


# ── Panel splitting ─────────────────────────────────────────────────────────────


def split_into_panels(page_path, cols, rows):
    """Split a rendered page into (cols × rows) equal sub-panels."""
    img = Image.open(page_path).convert("RGB")
    w, h = img.size
    panel_w = w // cols
    panel_h = h // rows
    panels = []
    for row in range(rows):
        for col in range(cols):
            x1, y1 = col * panel_w, row * panel_h
            panels.append(img.crop((x1, y1, x1 + panel_w, y1 + panel_h)))
    return panels


# ── Color extraction ────────────────────────────────────────────────────────────


def rgb_to_hex(r, g, b):
    return "#{:02x}{:02x}{:02x}".format(int(r), int(g), int(b))


def find_row_boundaries(gray_arr, min_gap_height=14):
    """Detect significant horizontal white bands that separate color rows.

    Returns list of (gap_start, gap_end) tuples for bands whose height
    >= min_gap_height.  Gaps smaller than this threshold are assumed to be
    inter-line spacing *within* a cell and are ignored.
    """
    row_mean = gray_arr.mean(axis=1)
    white = row_mean > 240
    h = gray_arr.shape[0]
    bands = []
    in_band = False
    start = 0
    for y in range(h):
        if white[y]:
            if not in_band:
                start = y
                in_band = True
        else:
            if in_band:
                bands.append((start, y - 1))
                in_band = False
    if in_band:
        bands.append((start, h - 1))
    return [(s, e) for s, e in bands if e - s >= min_gap_height]


def find_color_rows(gray_arr, min_gap_height=14, min_content_height=50):
    """Return list of (row_y1, row_y2) for each color row in a panel.

    Uses find_row_boundaries to find separating white bands, then returns
    the content segments between them.
    """
    gaps = find_row_boundaries(gray_arr, min_gap_height)
    h = gray_arr.shape[0]
    rows = []
    prev_end = 0
    for gap_start, gap_end in gaps:
        content_h = gap_start - prev_end
        if content_h >= min_content_height:
            rows.append((prev_end, gap_start))
        prev_end = gap_end + 1
    if h - prev_end >= min_content_height:
        rows.append((prev_end, h))
    return rows


def extract_colors_from_panel(panel_img, reader, config, panel_idx):
    arr = np.array(panel_img)
    h, w = arr.shape[:2]
    prefix = config["code_prefix"]
    grid_cols = config["grid_cols"]
    cell_w = w // grid_cols
    inset = config["swatch_inset"]

    # ── Step 1: detect row boundaries via horizontal white bands ──────────────
    gray = cv2.cvtColor(arr, cv2.COLOR_RGB2GRAY)
    min_gap = config.get("row_gap_height", 14)
    color_rows = find_color_rows(gray, min_gap_height=min_gap)
    print(f"  Panel {panel_idx}: OCR ({w}x{h}), {len(color_rows)} rows detected…", flush=True)

    # ── Step 2: single OCR pass on the full panel ─────────────────────────────
    ocr_results = reader.readtext(arr)
    code_re = re.compile(rf"\b{prefix}[.\s]?(\d{{3}})\b")

    code_entries = []
    all_text = []
    for bbox, text, conf in ocr_results:
        pts = np.array(bbox)
        x1, y1 = int(pts[:, 0].min()), int(pts[:, 1].min())
        x2, y2 = int(pts[:, 0].max()), int(pts[:, 1].max())
        all_text.append({"bbox": (x1, y1, x2, y2), "text": text.strip(), "conf": conf})
        m = code_re.search(text.strip())
        if m:
            code_entries.append(
                {
                    "code": f"{prefix}.{m.group(1)}",
                    "bbox": (x1, y1, x2, y2),
                    "conf": conf,
                }
            )

    if not code_entries:
        print(f"  No codes found in panel {panel_idx}")
        return []

    print(f"  Found {len(code_entries)} codes")

    # ── Step 3: build OCR-based row clusters ──────────────────────────────────
    # Cluster code entries into rows by Y proximity (always needed for fallback
    # and for estimating row height when white bands are not available).
    threshold = config["row_cluster_threshold"]
    sorted_entries = sorted(code_entries, key=lambda c: c["bbox"][1])
    ocr_rows = []
    current_row = [sorted_entries[0]]
    for entry in sorted_entries[1:]:
        if abs(entry["bbox"][1] - current_row[-1]["bbox"][1]) < threshold:
            current_row.append(entry)
        else:
            ocr_rows.append(sorted(current_row, key=lambda c: c["bbox"][0]))
            current_row = [entry]
    ocr_rows.append(sorted(current_row, key=lambda c: c["bbox"][0]))

    # Build a lookup: code → (row_idx, row_entries) for Y-bound estimation
    code_to_ocr_row = {}
    for row_idx, row_entries in enumerate(ocr_rows):
        for e in row_entries:
            code_to_ocr_row[e["code"]] = row_idx

    # Decide whether to use white-band rows or OCR-cluster rows.
    # If white-band detection found fewer rows than OCR clustering, fall back.
    use_band_rows = len(color_rows) >= len(ocr_rows) * 0.7

    # Pre-compute OCR-cluster row bounds using midpoints between adjacent rows.
    # Row centre Y = median of code bbox Y centres in that row.
    ocr_row_centres = []
    for row_entries in ocr_rows:
        ys = [(e["bbox"][1] + e["bbox"][3]) // 2 for e in row_entries]
        ocr_row_centres.append(int(np.median(ys)))

    # Estimate a typical row height from the median gap between row centres.
    if len(ocr_row_centres) > 1:
        gaps = [ocr_row_centres[i+1] - ocr_row_centres[i] for i in range(len(ocr_row_centres)-1)]
        median_row_h = int(np.median(gaps))
    else:
        median_row_h = h

    ocr_row_bounds = []
    for i, centre_y in enumerate(ocr_row_centres):
        if i == 0:
            top = max(0, centre_y - median_row_h // 2)
        else:
            top = (ocr_row_centres[i-1] + centre_y) // 2
        if i == len(ocr_row_centres) - 1:
            bot = min(h, centre_y + median_row_h // 2)
        else:
            bot = (centre_y + ocr_row_centres[i+1]) // 2
        ocr_row_bounds.append((top, bot))

    def row_bounds_for_entry(entry, ocr_row_idx):
        """Return (y1, y2) cell bounds for this code entry."""
        cx1, cy1, cx2, cy2 = entry["bbox"]
        code_cy = (cy1 + cy2) // 2

        if use_band_rows:
            # Try to find which white-band row contains this code
            for ry1, ry2 in color_rows:
                if ry1 <= code_cy <= ry2:
                    return ry1, ry2
            # Fallback: nearest band row
            best = min(color_rows, key=lambda r: abs((r[0] + r[1]) // 2 - code_cy), default=None)
            if best:
                return best

        # OCR-cluster fallback: use pre-computed midpoint bounds
        return ocr_row_bounds[ocr_row_idx]

    # ── Step 4: assign each code to its grid cell ─────────────────────────────
    colors = []
    for entry in code_entries:
        cx1, cy1, cx2, cy2 = entry["bbox"]
        code_cx = (cx1 + cx2) // 2

        # Determine column from x position
        col_idx = min(int(code_cx / cell_w), grid_cols - 1)
        cell_x1 = col_idx * cell_w
        cell_x2 = cell_x1 + cell_w

        ocr_row_idx = code_to_ocr_row.get(entry["code"], 0)
        row_y1, row_y2 = row_bounds_for_entry(entry, ocr_row_idx)

        # ── Swatch: top portion of the row, above the code text ───────────────
        sw_y1 = row_y1
        sw_y2 = cy1 - 4
        si_y1 = max(sw_y1, int(sw_y1 + (sw_y2 - sw_y1) * inset))
        si_y2 = max(si_y1 + 1, int(sw_y2 - (sw_y2 - sw_y1) * inset))
        si_x1 = int(cell_x1 + cell_w * inset)
        si_x2 = int(cell_x2 - cell_w * inset)

        if si_y1 < si_y2 and si_x1 < si_x2:
            region = arr[si_y1:si_y2, si_x1:si_x2]
            avg = region.reshape(-1, 3).mean(axis=0)
            hex_color = rgb_to_hex(*avg)
        else:
            hex_color = "#cccccc"

        # ── Name: first non-code text line below the code bbox ────────────────
        name_y1 = cy2
        name_y2 = row_y2
        name_lines = []
        for t in all_text:
            tx1, ty1, tx2, ty2 = t["bbox"]
            in_col = (tx1 >= cell_x1 - 10) and (tx2 <= cell_x2 + 10)
            in_row = (ty1 >= name_y1 - 5) and (ty1 <= name_y2)
            if in_col and in_row and not code_re.search(t["text"]) and t["text"]:
                name_lines.append((ty1, t["text"]))

        name_lines.sort(key=lambda x: x[0])
        name_en = name_lines[0][1] if name_lines else ""

        colors.append(
            {
                "code": entry["code"],
                "name": name_en,
                "hex": hex_color,
                "_cell_bbox": (cell_x1, row_y1, cell_x2, row_y2),
                "_swatch_bbox": (si_x1, si_y1, si_x2, si_y2),
                "_code_bbox": (cx1, cy1, cx2, cy2),
                "_name_bbox": (cell_x1, name_y1, cell_x2, name_y2),
            }
        )

    return colors


# ── Debug visualization ─────────────────────────────────────────────────────────

_DEBUG_COLORS = {
    "cell": (255, 80, 80),
    "swatch": (0, 200, 0),
    "code": (30, 30, 255),
    "name": (220, 120, 0),
}


def save_debug_panel(panel_img, colors, config, out_path):
    img = panel_img.copy()
    draw = ImageDraw.Draw(img)
    for c in colors:
        if config.get("debug_show_cells") and "_cell_bbox" in c:
            draw.rectangle(
                list(c["_cell_bbox"]), outline=_DEBUG_COLORS["cell"], width=2
            )
        if config.get("debug_show_swatch") and "_swatch_bbox" in c:
            draw.rectangle(
                list(c["_swatch_bbox"]), outline=_DEBUG_COLORS["swatch"], width=3
            )
        if config.get("debug_show_code_area") and "_code_bbox" in c:
            draw.rectangle(
                list(c["_code_bbox"]), outline=_DEBUG_COLORS["code"], width=2
            )
        if config.get("debug_show_name_area") and "_name_bbox" in c:
            draw.rectangle(
                list(c["_name_bbox"]), outline=_DEBUG_COLORS["name"], width=1
            )
    Path(out_path).parent.mkdir(parents=True, exist_ok=True)
    img.save(str(out_path))
    print(f"  Debug image → {out_path}")


def save_cell_debug_images(panel_img, colors, out_dir):
    """Save one cropped image per color cell with swatch/code/name areas overlaid."""
    out = Path(out_dir)
    out.mkdir(parents=True, exist_ok=True)
    arr = np.array(panel_img)
    ph, pw = arr.shape[:2]

    for c in colors:
        if "_cell_bbox" not in c:
            continue
        bx1, by1, bx2, by2 = c["_cell_bbox"]
        # clamp to panel bounds
        bx1, by1 = max(0, bx1), max(0, by1)
        bx2, by2 = min(pw, bx2), min(ph, by2)
        if bx2 <= bx1 or by2 <= by1:
            continue

        cell_img = panel_img.crop((bx1, by1, bx2, by2)).copy()
        draw = ImageDraw.Draw(cell_img)

        def rel(box):
            """Translate panel-absolute bbox to cell-relative coords."""
            return (box[0] - bx1, box[1] - by1, box[2] - bx1, box[3] - by1)

        cw = bx2 - bx1
        ch = by2 - by1
        zones = [
            ("swatch", "_swatch_bbox", _DEBUG_COLORS["swatch"], 3),
            ("code", "_code_bbox", _DEBUG_COLORS["code"], 2),
            ("name", "_name_bbox", _DEBUG_COLORS["name"], 2),
        ]
        for label, key, color, width in zones:
            if key not in c:
                continue
            rx1, ry1, rx2, ry2 = rel(c[key])
            # clamp to cell bounds and ensure valid rect
            rx1 = max(0, min(rx1, cw))
            rx2 = max(0, min(rx2, cw))
            ry1 = max(0, min(ry1, ch))
            ry2 = max(0, min(ry2, ch))
            if rx2 <= rx1 or ry2 <= ry1:
                continue
            draw.rectangle([rx1, ry1, rx2, ry2], outline=color, width=width)
            # small label in top-left corner of the zone
            lx = max(rx1 + 2, 0)
            ly = max(ry1 + 1, 0)
            draw.text((lx + 1, ly + 1), label, fill=(0, 0, 0))
            draw.text((lx, ly), label, fill=color)

        # safe filename from code (e.g. "70.001" → "70_001")
        safe = c["code"].replace(".", "_").replace("/", "-")
        cell_img.save(str(out / f"{safe}.png"))

    print(f"  Cell debug images → {out}  ({len(colors)} files)")


# ── Equivalence table parsing ───────────────────────────────────────────────────


def extract_equiv_from_panel(panel_img, reader, config, panel_idx):
    arr = np.array(panel_img)
    print(f"  Panel {panel_idx}: OCR equivalence table…", flush=True)
    ocr_results = reader.readtext(arr)
    prefix = config["code_prefix"]
    code_re = re.compile(rf"\b{prefix}[.\s]?(\d{{3}})\b")

    rows = {}
    for bbox, text, conf in ocr_results:
        pts = np.array(bbox)
        x1, y1 = int(pts[:, 0].min()), int(pts[:, 1].min())
        m = code_re.search(text.strip())
        if m:
            code = f"{prefix}.{m.group(1)}"
            if code not in rows:
                rows[code] = {"code": code, "y1": y1, "entries": []}

    code_ys = {code: info["y1"] for code, info in rows.items()}
    for bbox, text, conf in ocr_results:
        pts = np.array(bbox)
        x1, y1 = int(pts[:, 0].min()), int(pts[:, 1].min())
        t = text.strip()
        if not t:
            continue
        best_code, best_dist = None, 999999
        for code, cy in code_ys.items():
            d = abs(y1 - cy)
            if d < best_dist and d < 60:
                best_dist, best_code = d, code
        if best_code and not code_re.search(t):
            rows[best_code]["entries"].append({"x1": x1, "text": t})

    result = []
    for code, info in sorted(rows.items()):
        entries_sorted = sorted(info["entries"], key=lambda e: e["x1"])
        result.append({"code": code, "equiv_raw": [e["text"] for e in entries_sorted]})
    return result


# ── Main pipeline ───────────────────────────────────────────────────────────────


def run(cfg):
    import easyocr
    import sys

    pdf_path = cfg["pdf_path"]
    if not Path(pdf_path).exists():
        print(f"ERROR: PDF not found: {pdf_path}")
        sys.exit(1)

    force = cfg.get("force_render", False)
    print(f"Rendering PDF: {pdf_path}")
    rendered_pages = render_pdf_pages(
        pdf_path, cfg["render_dpi"], cfg["tmp_dir"], force
    )

    comp_idx = cfg["composite_page_index"]
    cols = cfg["composite_cols"]
    rows_n = cfg.get("composite_rows", 1)
    print(f"\nSplitting page {comp_idx} into {cols}×{rows_n} panels…")
    panels = split_into_panels(rendered_pages[comp_idx], cols, rows_n)
    print(f"  {len(panels)} panels, each {panels[0].size[0]}×{panels[0].size[1]} px")

    tmp = Path(cfg["tmp_dir"])
    for i, panel in enumerate(panels):
        panel.save(str(tmp / f"panel_{i:02d}.png"))

    print("\nLoading OCR reader…")
    reader = easyocr.Reader(["en"], gpu=False)

    all_colors = []
    all_equivs = []
    debug_target = cfg.get("debug_panel")

    for panel_idx, panel_img in enumerate(panels):
        if panel_idx in cfg.get("panels_to_skip", []):
            print(f"\nPanel {panel_idx}: skipped")
            continue

        if panel_idx in cfg.get("color_panels", []):
            print(f"\nPanel {panel_idx}: color extraction")
            colors = extract_colors_from_panel(panel_img, reader, cfg, panel_idx)
            print(f"  → {len(colors)} colors")
            all_colors.extend(colors)
            cells_dir = (
                Path(cfg["debug_output_dir"]) / f"cells_panel_{panel_idx:02d}"
            )
            save_cell_debug_images(panel_img, colors, cells_dir)
            if cfg.get("debug") and (debug_target is None or debug_target == panel_idx):
                out = Path(cfg["debug_output_dir"]) / f"debug_panel_{panel_idx:02d}.png"
                save_debug_panel(panel_img, colors, cfg, out)

        elif panel_idx in cfg.get("equiv_panels", []):
            print(f"\nPanel {panel_idx}: equivalence table")
            equivs = extract_equiv_from_panel(panel_img, reader, cfg, panel_idx)
            print(f"  → {len(equivs)} rows")
            all_equivs.extend(equivs)
            if cfg.get("debug") and (debug_target is None or debug_target == panel_idx):
                out = Path(cfg["debug_output_dir"]) / f"debug_panel_{panel_idx:02d}.png"
                Path(cfg["debug_output_dir"]).mkdir(parents=True, exist_ok=True)
                panel_img.save(str(out))
                print(f"  Debug image → {out}")

    seen = set()
    unique = []
    for c in sorted(all_colors, key=lambda x: x["code"]):
        if c["code"] not in seen:
            seen.add(c["code"])
            unique.append({"code": c["code"], "name": c["name"], "hex": c["hex"]})

    print(f"\n{'─'*50}")
    print(f"Colors extracted : {len(unique)}")
    print(f"Equiv rows parsed: {len(all_equivs)}")

    out_json = Path(cfg["output_json"])
    out_json.parent.mkdir(parents=True, exist_ok=True)
    pack = {
        "brand": cfg["brand_label"],
        "brand_id": cfg["brand_id"],
        "source": str(out_json),
        "count": len(unique),
        "colors": unique,
    }
    out_json.write_text(
        json.dumps(pack, indent=2, ensure_ascii=False), encoding="utf-8"
    )
    print(f"✓ JSON → {out_json}")

    out_csv = Path(cfg["output_csv"])
    with out_csv.open("w", newline="", encoding="utf-8") as fh:
        writer = csv.DictWriter(fh, fieldnames=["code", "name", "hex"])
        writer.writeheader()
        writer.writerows(unique)
    print(f"✓ CSV  → {out_csv}")

    return unique
