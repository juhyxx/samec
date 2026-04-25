"""
Vallejo Model Air – texture-aware cell parser
==============================================
The catalog page has a textured background that confuses standard white-band
row detection.  This script takes a two-phase approach:

  Phase 1 – HIGH CONTRAST
    • Convert the rendered page to grayscale and apply CLAHE (Contrast Limited
      Adaptive Histogram Equalization) so grid lines stand out clearly against
      the texture.
    • Use column-wise and row-wise intensity profiles on the enhanced image to
      locate the exact starting offset and pitch of the grid.

  Phase 2 – CELL EXTRACTION
    • With the grid origin known, step through cells of the expected size
      (approx 182 × 215 px) across 9 columns.
    • Sample the swatch area from the *original* (unenhanced) image so colours
      are not distorted.
    • Run OCR on each cell to extract paint code and name.

Usage
-----
  python scripts/parse_model_air_texture.py [options]

Options
-------
  --pdf PATH          Path to ModelAir.pdf (default: source/valejo/model_air/ModelAir.pdf)
  --dpi INT           Render DPI (default: 300)
  --page INT          Zero-based page index to parse (default: 1)
  --cols INT          Number of grid columns (default: 9)
  --cell-w INT        Expected cell width in pixels at the chosen DPI (default: 182)
  --cell-h INT        Expected cell height in pixels at the chosen DPI (default: 215)
  --swatch-frac FLOAT Fraction of cell height used as the colour swatch (default: 0.55)
  --inset FLOAT       Inset factor applied to swatch region edges (default: 0.08)
  --debug             Save annotated debug images
  --debug-dir PATH    Directory for debug output (default: .tmp/model_air_texture/debug)
  --output-json PATH  Output JSON file (default: data/pack_vallejo_model_air.json)
  --output-csv PATH   Output CSV file (default: data/pack_vallejo_model_air.csv)
  --force-render      Re-render even if cached PNGs exist
"""

import argparse
import csv
import json
import sys
from pathlib import Path

import cv2
import fitz  # pymupdf
import easyocr
import numpy as np
from PIL import Image, ImageDraw

# ---------------------------------------------------------------------------
# Paths relative to repository root
# ---------------------------------------------------------------------------
_SCRIPT_DIR = Path(__file__).resolve().parent
_ROOT = _SCRIPT_DIR.parent

DEFAULT_PDF = str(_ROOT / "source" / "valejo" / "model_air" / "ModelAir.pdf")
DEFAULT_TMP = str(_ROOT / ".tmp" / "model_air_texture")
DEFAULT_DEBUG = str(_ROOT / ".tmp" / "model_air_texture" / "debug")
DEFAULT_JSON = str(_ROOT / "data" / "pack_vallejo_model_air.json")
DEFAULT_CSV = str(_ROOT / "data" / "pack_vallejo_model_air.csv")

CODE_PREFIX = "71"
CODE_RE_PATTERN = r"\b71[.\s]?(\d{3})\b"

# ---------------------------------------------------------------------------
# Phase 0 – PDF rendering
# ---------------------------------------------------------------------------


def render_page(
    pdf_path: str, page_idx: int, dpi: int, tmp_dir: str, force: bool
) -> Path:
    """Render a single PDF page to PNG (cached). Returns the PNG path."""
    tmp = Path(tmp_dir)
    tmp.mkdir(parents=True, exist_ok=True)
    out = tmp / f"page_{page_idx:02d}.png"
    if out.exists() and not force:
        print(f"  [cache] {out.name}")
        return out
    doc = fitz.open(pdf_path)
    page = doc[page_idx]
    scale = dpi / 72.0
    mat = fitz.Matrix(scale, scale)
    pix = page.get_pixmap(matrix=mat, alpha=False)
    pix.save(str(out))
    doc.close()
    print(f"  Rendered page {page_idx} at {dpi} DPI → {out.name}")
    return out


# ---------------------------------------------------------------------------
# Phase 1 – High-contrast preprocessing & grid detection
# ---------------------------------------------------------------------------


def high_contrast(gray: np.ndarray) -> np.ndarray:
    """Apply CLAHE to bring out grid structure over a textured background."""
    clahe = cv2.createCLAHE(clipLimit=3.0, tileGridSize=(16, 16))
    enhanced = clahe.apply(gray)
    # Additional global contrast stretch to push lines closer to white/black
    enhanced = cv2.normalize(enhanced, None, 0, 255, cv2.NORM_MINMAX)
    return enhanced


def find_grid_origin(
    enhanced: np.ndarray, cell_w: int, cell_h: int, cols: int
) -> tuple[int, int]:
    """
    Locate the top-left corner of the colour grid using column and row
    intensity profiles computed on the high-contrast image.

    Strategy:
      • Invert so *dark* grid lines become peaks.
      • Compute the mean of each column (row) across the full height (width).
      • Look for a regularly-spaced set of `cols` peaks consistent with
        `cell_w` spacing, accepting the best-scoring starting offset.

    Returns (origin_x, origin_y).
    """
    inv = cv2.bitwise_not(enhanced)

    # --- Column profile → horizontal origin -----------------------------------
    col_profile = inv.mean(axis=0).astype(float)  # shape (width,)
    ox = _find_periodic_origin(col_profile, cell_w, cols)

    # --- Row profile → vertical origin ----------------------------------------
    # We don't know how many rows there are; estimate from image height.
    estimated_rows = max(1, enhanced.shape[0] // cell_h)
    row_profile = inv.mean(axis=1).astype(float)  # shape (height,)
    oy = _find_periodic_origin(row_profile, cell_h, estimated_rows)

    return ox, oy


def _find_periodic_origin(profile: np.ndarray, period: int, count: int) -> int:
    """
    Slide through possible starting offsets (0 … period-1) and return the one
    that maximises the summed profile value at positions:
        start, start+period, start+2*period, …  (count peaks)

    This finds the offset where grid lines (inverted = peaks) best align with
    the expected spacing.
    """
    best_score = -1.0
    best_offset = 0
    for offset in range(period):
        positions = [
            offset + i * period
            for i in range(count)
            if offset + i * period < len(profile)
        ]
        if not positions:
            continue
        score = float(np.mean(profile[positions]))
        if score > best_score:
            best_score = score
            best_offset = offset
    return best_offset


# ---------------------------------------------------------------------------
# Phase 2 – Cell extraction & colour sampling
# ---------------------------------------------------------------------------


def rgb_to_hex(r: float, g: float, b: float) -> str:
    return "#{:02x}{:02x}{:02x}".format(int(r), int(g), int(b))


def extract_cells(
    orig_img: Image.Image,
    enhanced: np.ndarray,
    origin_x: int,
    origin_y: int,
    cell_w: int,
    cell_h: int,
    cols: int,
    swatch_frac: float,
    inset: float,
) -> list[dict]:
    """
    Step through the grid and build a list of cell dicts with bounding boxes
    and the sampled colour hex.  OCR is NOT run here; it is done in a second
    pass to keep concerns separate.
    """
    arr_orig = np.array(orig_img)
    img_h, img_w = arr_orig.shape[:2]

    cells = []
    row_idx = 0
    y = origin_y
    while y + cell_h <= img_h:
        for col_idx in range(cols):
            x = origin_x + col_idx * cell_w
            if x + cell_w > img_w:
                break

            # Full cell bounds
            cx1, cy1, cx2, cy2 = x, y, x + cell_w, y + cell_h

            # Swatch area: top `swatch_frac` of the cell, inset on all sides
            sw_h = int(cell_h * swatch_frac)
            si_x1 = int(cx1 + cell_w * inset)
            si_x2 = int(cx2 - cell_w * inset)
            si_y1 = int(cy1 + cell_h * inset)
            si_y2 = cy1 + sw_h - int(sw_h * inset)

            if si_x2 > si_x1 and si_y2 > si_y1:
                region = arr_orig[si_y1:si_y2, si_x1:si_x2]
                avg = region.reshape(-1, 3).mean(axis=0)
                hex_color = rgb_to_hex(*avg)
            else:
                hex_color = "#cccccc"

            cells.append(
                {
                    "row": row_idx,
                    "col": col_idx,
                    "hex": hex_color,
                    "_cell_bbox": (cx1, cy1, cx2, cy2),
                    "_swatch_bbox": (si_x1, si_y1, si_x2, si_y2),
                    # OCR fields filled in later
                    "code": "",
                    "name": "",
                }
            )

        row_idx += 1
        y += cell_h

    return cells


# ---------------------------------------------------------------------------
# Phase 2b – OCR pass
# ---------------------------------------------------------------------------


def run_ocr_on_cells(
    orig_img: Image.Image,
    cells: list[dict],
    reader: easyocr.Reader,
) -> list[dict]:
    """
    Run OCR on each individual cell crop and populate `code` and `name`.
    Working on small crops is faster and more accurate than one giant pass.
    """
    import re

    code_re = re.compile(CODE_RE_PATTERN)
    arr = np.array(orig_img)

    for cell in cells:
        cx1, cy1, cx2, cy2 = cell["_cell_bbox"]
        crop = arr[cy1:cy2, cx1:cx2]
        results = reader.readtext(crop)

        codes_found = []
        other_lines = []

        for bbox, text, conf in results:
            t = text.strip()
            if not t:
                continue
            m = code_re.search(t)
            if m:
                pts = np.array(bbox)
                y_centre = int(pts[:, 1].mean())
                codes_found.append(
                    {"code": f"{CODE_PREFIX}.{m.group(1)}", "y": y_centre, "conf": conf}
                )
            else:
                pts = np.array(bbox)
                y_top = int(pts[:, 1].min())
                other_lines.append({"text": t, "y": y_top})

        if codes_found:
            # Use the highest-confidence code
            best = max(codes_found, key=lambda c: c["conf"])
            cell["code"] = best["code"]
            code_y = best["y"]
            # Name: first text line *below* the code (larger y)
            below = [l for l in other_lines if l["y"] > code_y - 5]
            below.sort(key=lambda l: l["y"])
            cell["name"] = below[0]["text"] if below else ""

    return cells


# ---------------------------------------------------------------------------
# Debug output
# ---------------------------------------------------------------------------

_COLORS = {
    "cell": (255, 80, 80),
    "swatch": (0, 200, 0),
    "code": (30, 30, 255),
}


def save_debug_image(orig_img: Image.Image, cells: list[dict], path: str) -> None:
    img = orig_img.copy()
    draw = ImageDraw.Draw(img)
    for c in cells:
        draw.rectangle(list(c["_cell_bbox"]), outline=_COLORS["cell"], width=2)
        draw.rectangle(list(c["_swatch_bbox"]), outline=_COLORS["swatch"], width=3)
        if c.get("code"):
            draw.text(
                (c["_cell_bbox"][0] + 4, c["_cell_bbox"][1] + 4),
                c["code"],
                fill=_COLORS["code"],
            )
    Path(path).parent.mkdir(parents=True, exist_ok=True)
    img.save(path)
    print(f"  Debug image → {path}")


def save_high_contrast_image(enhanced: np.ndarray, path: str) -> None:
    Path(path).parent.mkdir(parents=True, exist_ok=True)
    cv2.imwrite(path, enhanced)
    print(f"  High-contrast image → {path}")


# ---------------------------------------------------------------------------
# Main
# ---------------------------------------------------------------------------


def main() -> None:
    ap = argparse.ArgumentParser(description="Vallejo Model Air texture-aware parser")
    ap.add_argument("--pdf", default=DEFAULT_PDF)
    ap.add_argument("--dpi", type=int, default=300)
    ap.add_argument("--page", type=int, default=1, help="Zero-based page index")
    ap.add_argument("--cols", type=int, default=9, help="Number of grid columns")
    ap.add_argument("--cell-w", type=int, default=182, help="Expected cell width (px)")
    ap.add_argument("--cell-h", type=int, default=215, help="Expected cell height (px)")
    ap.add_argument(
        "--swatch-frac",
        type=float,
        default=0.55,
        help="Fraction of cell height for swatch",
    )
    ap.add_argument("--inset", type=float, default=0.08, help="Edge inset fraction")
    ap.add_argument("--debug", action="store_true")
    ap.add_argument("--debug-dir", default=DEFAULT_DEBUG)
    ap.add_argument("--output-json", default=DEFAULT_JSON)
    ap.add_argument("--output-csv", default=DEFAULT_CSV)
    ap.add_argument("--force-render", action="store_true")
    ap.add_argument("--tmp-dir", default=DEFAULT_TMP)
    args = ap.parse_args()

    pdf = args.pdf
    if not Path(pdf).exists():
        print(f"ERROR: PDF not found: {pdf}")
        sys.exit(1)

    # ── Render ─────────────────────────────────────────────────────────────────
    print(f"\n[1/4] Rendering PDF page {args.page} at {args.dpi} DPI…")
    page_png = render_page(pdf, args.page, args.dpi, args.tmp_dir, args.force_render)
    orig_img = Image.open(page_png).convert("RGB")
    arr_orig = np.array(orig_img)

    # ── Phase 1: High contrast → grid detection ────────────────────────────────
    print("\n[2/4] Detecting grid via high-contrast preprocessing…")
    gray = cv2.cvtColor(arr_orig, cv2.COLOR_RGB2GRAY)
    enhanced = high_contrast(gray)

    if args.debug:
        save_high_contrast_image(enhanced, str(Path(args.debug_dir) / "enhanced.png"))

    origin_x, origin_y = find_grid_origin(enhanced, args.cell_w, args.cell_h, args.cols)
    print(f"  Grid origin detected at x={origin_x}, y={origin_y}")
    print(f"  Cell size: {args.cell_w} × {args.cell_h} px,  {args.cols} columns")

    # ── Phase 2: Cell extraction + colour sampling ─────────────────────────────
    print("\n[3/4] Extracting cells and sampling colours…")
    cells = extract_cells(
        orig_img,
        enhanced,
        origin_x,
        origin_y,
        args.cell_w,
        args.cell_h,
        args.cols,
        args.swatch_frac,
        args.inset,
    )
    print(
        f"  {len(cells)} cells found across {cells[-1]['row'] + 1 if cells else 0} rows"
    )

    # ── OCR ────────────────────────────────────────────────────────────────────
    print("\n  Loading OCR reader…")
    reader = easyocr.Reader(["en"], gpu=False)
    cells = run_ocr_on_cells(orig_img, cells, reader)
    named = sum(1 for c in cells if c["code"])
    print(f"  OCR complete: {named} / {len(cells)} cells have a paint code")

    if args.debug:
        save_debug_image(
            orig_img, cells, str(Path(args.debug_dir) / "cells_annotated.png")
        )

    # ── Write output ────────────────────────────────────────────────────────────
    print("\n[4/4] Writing output…")
    colors = [
        {"code": c["code"], "name": c["name"], "hex": c["hex"]}
        for c in cells
        if c["code"]
    ]
    # Deduplicate by code (keep first occurrence)
    seen: set[str] = set()
    unique: list[dict] = []
    for clr in sorted(colors, key=lambda x: x["code"]):
        if clr["code"] not in seen:
            seen.add(clr["code"])
            unique.append(clr)

    out_json = Path(args.output_json)
    out_json.parent.mkdir(parents=True, exist_ok=True)
    pack = {
        "brand": "Vallejo Model Air",
        "brand_id": "vallejo_model_air",
        "source": str(out_json),
        "count": len(unique),
        "colors": unique,
    }
    out_json.write_text(
        json.dumps(pack, indent=2, ensure_ascii=False), encoding="utf-8"
    )
    print(f"  ✓ JSON → {out_json}  ({len(unique)} colours)")

    out_csv = Path(args.output_csv)
    with out_csv.open("w", newline="", encoding="utf-8") as fh:
        writer = csv.DictWriter(fh, fieldnames=["code", "name", "hex"])
        writer.writeheader()
        writer.writerows(unique)
    print(f"  ✓ CSV  → {out_csv}")


if __name__ == "__main__":
    main()
