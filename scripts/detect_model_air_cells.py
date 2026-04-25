"""
Vallejo Model Air – cell and colour-box detector
=================================================
Goal: detect the grid of paint cells on a rendered catalog page.
NO colour extraction.  NO OCR.

Each cell has:
  ┌──────────────────┐
  │   colour box     │  ← filled rectangle (~top 55 % of cell)
  │                  │
  ├──────────────────┤
  │  code + name     │  ← text area (not processed here)
  └──────────────────┘

Known layout (at 300 DPI):
  • Cell size     : ~182 × 215 px
  • Gap between   :   5 px
  • Grid columns  :   9

Approach
--------
1. Render the requested PDF page at the given DPI.
2. Apply CLAHE on the grayscale version to suppress the textured background
   and make cell borders visible.
3. Run Canny edge detection on the enhanced image.
4. Find contours; filter by the expected colour-box aspect ratio and area.
5. Snap the detected box centres onto a regular grid (periodicity = cell+gap).
6. Save debug images:
     debug/enhanced.png          – CLAHE output
     debug/edges.png             – Canny edges
     debug/detected_boxes.png    – raw detected contours before snapping
     debug/grid_snapped.png      – final snapped grid overlay on original page

Usage
-----
    python scripts/detect_model_air_cells.py [options]

Options
-------
  --pdf PATH          Source PDF  (default: source/valejo/model_air/ModelAir.pdf)
  --dpi INT           Render DPI  (default: 300)
  --page INT          Zero-based page index to analyse  (default: 1)
  --cols INT          Expected grid columns  (default: 9)
  --cell-w INT        Expected cell width in px at the chosen DPI  (default: 182)
  --cell-h INT        Expected cell height in px  (default: 215)
  --gap INT           Gap between cells in px  (default: 5)
  --box-frac FLOAT    Fraction of cell height occupied by the colour box  (default: 0.58)
  --canny-lo INT      Canny low threshold   (default: 30)
  --canny-hi INT      Canny high threshold  (default: 90)
  --debug-dir PATH    Where to write debug images  (default: .tmp/detect_model_air)
  --tmp-dir PATH      Where to cache rendered PNG pages  (default: .tmp/detect_model_air)
  --force-render      Re-render even if cached PNGs exist
  --panel INT         If given, work only on this zero-based panel column instead
                      of the full page (splits the page into `--cols` vertical strips).
"""

import argparse
import sys
from pathlib import Path

import cv2
import fitz  # pymupdf
import numpy as np
from PIL import Image, ImageDraw, ImageFont

_ROOT = Path(__file__).resolve().parent.parent

DEFAULT_PDF = str(_ROOT / "source" / "valejo" / "model_air" / "ModelAir.pdf")
DEFAULT_TMP = str(_ROOT / ".tmp" / "detect_model_air")
DEFAULT_DEBUG_DIR = str(_ROOT / ".tmp" / "detect_model_air" / "debug")


# ─────────────────────────────────────────────────────────────────────────────
# Step 1 – PDF rendering
# ─────────────────────────────────────────────────────────────────────────────


def render_page(
    pdf_path: str, page_idx: int, dpi: int, tmp_dir: str, force: bool
) -> Path:
    """Render one PDF page to PNG (cached).  Returns the PNG path."""
    tmp = Path(tmp_dir)
    tmp.mkdir(parents=True, exist_ok=True)
    out = tmp / f"page_{page_idx:02d}_dpi{dpi}.png"
    if out.exists() and not force:
        print(f"  [cache] {out.name}")
        return out
    doc = fitz.open(pdf_path)
    page = doc[page_idx]
    scale = dpi / 72.0
    pix = page.get_pixmap(matrix=fitz.Matrix(scale, scale), alpha=False)
    pix.save(str(out))
    doc.close()
    print(
        f"  Rendered page {page_idx} @ {dpi} DPI → {out.name}  ({pix.width}×{pix.height} px)"
    )
    return out


# ─────────────────────────────────────────────────────────────────────────────
# Step 2 – High-contrast preprocessing
# ─────────────────────────────────────────────────────────────────────────────


def apply_high_contrast(gray: np.ndarray) -> np.ndarray:
    """
    CLAHE + normalisation.

    CLAHE (Contrast Limited Adaptive Histogram Equalisation) locally boosts
    contrast.  The tileGridSize should be slightly larger than one cell so
    each tile captures at least one cell boundary.
    """
    clahe = cv2.createCLAHE(clipLimit=3.0, tileGridSize=(24, 24))
    enhanced = clahe.apply(gray)
    # Global stretch so the full 0-255 range is used
    enhanced = cv2.normalize(enhanced, None, 0, 255, cv2.NORM_MINMAX)
    return enhanced


# ─────────────────────────────────────────────────────────────────────────────
# Step 3 – Edge detection
# ─────────────────────────────────────────────────────────────────────────────


def detect_edges(enhanced: np.ndarray, lo: int, hi: int) -> np.ndarray:
    """
    Apply a slight Gaussian blur first so the texture doesn't produce too many
    spurious edges, then run Canny.
    """
    blurred = cv2.GaussianBlur(enhanced, (3, 3), 0)
    edges = cv2.Canny(blurred, lo, hi)
    # Close small gaps in cell borders with a small dilation
    kernel = cv2.getStructuringElement(cv2.MORPH_RECT, (3, 3))
    edges = cv2.dilate(edges, kernel, iterations=1)
    return edges


# ─────────────────────────────────────────────────────────────────────────────
# Step 4 – Contour-based colour-box detection
# ─────────────────────────────────────────────────────────────────────────────


def find_color_boxes(
    edges: np.ndarray,
    cell_w: int,
    cell_h: int,
    box_frac: float,
    tolerance: float = 0.30,
) -> list[tuple[int, int, int, int]]:
    """
    Find rectangular contours whose dimensions match the expected colour box.

    Expected colour box size:
        width  ≈ cell_w              (full cell width)
        height ≈ cell_h * box_frac   (top portion of cell)

    tolerance: allowed relative deviation from the expected size (±30 %).

    Returns a list of (x, y, w, h) tuples for each detected box.
    """
    exp_w = cell_w
    exp_h = int(cell_h * box_frac)
    min_w = int(exp_w * (1 - tolerance))
    max_w = int(exp_w * (1 + tolerance))
    min_h = int(exp_h * (1 - tolerance))
    max_h = int(exp_h * (1 + tolerance))

    contours, _ = cv2.findContours(edges, cv2.RETR_LIST, cv2.CHAIN_APPROX_SIMPLE)

    boxes = []
    for cnt in contours:
        # Approximate to a polygon
        peri = cv2.arcLength(cnt, True)
        approx = cv2.approxPolyDP(cnt, 0.04 * peri, True)
        if len(approx) != 4:
            continue
        x, y, w, h = cv2.boundingRect(approx)
        if min_w <= w <= max_w and min_h <= h <= max_h:
            boxes.append((x, y, w, h))

    # Remove near-duplicates (keep one per cluster)
    boxes = _deduplicate(boxes, threshold=15)
    return boxes


def _deduplicate(
    boxes: list[tuple[int, int, int, int]], threshold: int
) -> list[tuple[int, int, int, int]]:
    """Remove boxes whose centre is within `threshold` px of an already-kept box."""
    kept = []
    for b in sorted(boxes, key=lambda b: (b[1], b[0])):
        cx, cy = b[0] + b[2] // 2, b[1] + b[3] // 2
        too_close = False
        for k in kept:
            kx, ky = k[0] + k[2] // 2, k[1] + k[3] // 2
            if abs(cx - kx) < threshold and abs(cy - ky) < threshold:
                too_close = True
                break
        if not too_close:
            kept.append(b)
    return kept


# ─────────────────────────────────────────────────────────────────────────────
# Step 5 – Grid snapping
# ─────────────────────────────────────────────────────────────────────────────


def snap_to_grid(
    boxes: list[tuple[int, int, int, int]],
    cell_w: int,
    cell_h: int,
    gap: int,
    cols: int,
    img_h: int,
) -> list[dict]:
    """
    Given raw detected box positions, infer a regular grid and snap each
    detection to the nearest grid position.

    Returns a list of dicts:
        {
            "grid_col":  int,       # 0-based column index
            "grid_row":  int,       # 0-based row index
            "cell_x":    int,       # top-left x of the full cell
            "cell_y":    int,       # top-left y of the full cell
            "box_x":     int,       # top-left x of the colour box
            "box_y":     int,       # top-left y of the colour box
            "box_w":     int,       # detected box width
            "box_h":     int,       # detected box height
            "snapped":   bool,      # True if this came from a detection
        }
    """
    if not boxes:
        return []

    pitch_x = cell_w + gap
    pitch_y = cell_h + gap

    # Estimate grid origin from cluster of box x/y positions
    xs = [b[0] for b in boxes]
    ys = [b[1] for b in boxes]
    origin_x = _estimate_origin(xs, pitch_x)
    origin_y = _estimate_origin(ys, pitch_y)

    print(f"  Grid origin estimate: x={origin_x}, y={origin_y}")
    print(
        f"  Cell pitch: {pitch_x} × {pitch_y} px  (cell {cell_w}×{cell_h} + {gap}px gap)"
    )

    # Build a set of detected positions keyed by (col, row)
    detected: dict[tuple[int, int], tuple[int, int, int, int]] = {}
    for bx, by, bw, bh in boxes:
        col = round((bx - origin_x) / pitch_x)
        row = round((by - origin_y) / pitch_y)
        if 0 <= col < cols and row >= 0:
            detected[(col, row)] = (bx, by, bw, bh)

    # Determine how many rows fit in the image
    max_row = max((r for _, r in detected), default=0)
    # Also check if more rows might exist but weren't detected
    rows_by_height = max(1, (img_h - origin_y) // pitch_y)
    total_rows = max(max_row + 1, rows_by_height)

    results = []
    for row in range(total_rows):
        for col in range(cols):
            cell_x = origin_x + col * pitch_x
            cell_y = origin_y + row * pitch_y
            snapped = (col, row) in detected
            if snapped:
                bx, by, bw, bh = detected[(col, row)]
            else:
                bx, by = cell_x, cell_y
                bw, bh = cell_w, int(cell_h * 0.58)

            results.append(
                {
                    "grid_col": col,
                    "grid_row": row,
                    "cell_x": cell_x,
                    "cell_y": cell_y,
                    "box_x": bx,
                    "box_y": by,
                    "box_w": bw,
                    "box_h": bh,
                    "snapped": snapped,
                }
            )

    return results


def _estimate_origin(positions: list[int], pitch: int) -> int:
    """
    Find the offset (0…pitch-1) that best aligns with the observed positions
    using a modular histogram (similar to a Hough-style vote).
    """
    votes: dict[int, int] = {}
    for p in positions:
        key = p % pitch
        votes[key] = votes.get(key, 0) + 1
    if not votes:
        return 0
    best = max(votes, key=lambda k: votes[k])
    return best


# ─────────────────────────────────────────────────────────────────────────────
# Debug visualisation
# ─────────────────────────────────────────────────────────────────────────────

_COL_BOX_DETECTED = (0, 220, 0)  # green  – detected colour box
_COL_BOX_INFERRED = (255, 160, 0)  # orange – grid position inferred (no detection)
_COL_CELL_BORDER = (200, 50, 50)  # red    – full cell rectangle
_COL_LABEL = (255, 255, 255)


def save_debug_image(
    orig_arr: np.ndarray,
    grid: list[dict],
    cell_h: int,
    out_path: str,
    title: str = "",
) -> None:
    """Draw cell outlines and colour-box outlines on the original image."""
    vis = orig_arr.copy()

    for g in grid:
        cx, cy = g["cell_x"], g["cell_y"]
        bx, by, bw, bh = g["box_x"], g["box_y"], g["box_w"], g["box_h"]
        col_idx, row_idx = g["grid_col"], g["grid_row"]

        # Full cell rectangle
        cv2.rectangle(
            vis,
            (cx, cy),
            (cx + bw, cy + cell_h),  # use detected box width
            _COL_CELL_BORDER,
            1,
        )

        # Colour box rectangle
        box_color = _COL_BOX_DETECTED if g["snapped"] else _COL_BOX_INFERRED
        cv2.rectangle(vis, (bx, by), (bx + bw, by + bh), box_color, 2)

        # Small grid-position label
        label = f"{col_idx},{row_idx}"
        cv2.putText(
            vis,
            label,
            (bx + 4, by + 16),
            cv2.FONT_HERSHEY_SIMPLEX,
            0.35,
            _COL_LABEL,
            1,
            cv2.LINE_AA,
        )

    Path(out_path).parent.mkdir(parents=True, exist_ok=True)
    cv2.imwrite(out_path, cv2.cvtColor(vis, cv2.COLOR_RGB2BGR))
    print(f"  Debug image → {out_path}")


def save_cv_image(arr: np.ndarray, out_path: str) -> None:
    Path(out_path).parent.mkdir(parents=True, exist_ok=True)
    cv2.imwrite(out_path, arr)
    print(f"  Saved → {out_path}")


# ─────────────────────────────────────────────────────────────────────────────
# Main
# ─────────────────────────────────────────────────────────────────────────────


def main() -> None:
    ap = argparse.ArgumentParser(
        description="Detect colour-box cells in a Vallejo Model Air catalog page."
    )
    ap.add_argument("--pdf", default=DEFAULT_PDF)
    ap.add_argument("--dpi", type=int, default=300)
    ap.add_argument("--page", type=int, default=1, help="Zero-based page index")
    ap.add_argument("--cols", type=int, default=9, help="Grid columns")
    ap.add_argument("--cell-w", type=int, default=182, help="Cell width (px)")
    ap.add_argument("--cell-h", type=int, default=215, help="Cell height (px)")
    ap.add_argument("--gap", type=int, default=5, help="Gap between cells (px)")
    ap.add_argument(
        "--box-frac",
        type=float,
        default=0.58,
        help="Fraction of cell height for colour box",
    )
    ap.add_argument("--canny-lo", type=int, default=30, help="Canny low threshold")
    ap.add_argument("--canny-hi", type=int, default=90, help="Canny high threshold")
    ap.add_argument(
        "--panel",
        type=int,
        default=None,
        help="If set, crop to this zero-based vertical panel (divides page into --cols strips)",
    )
    ap.add_argument("--debug-dir", default=DEFAULT_DEBUG_DIR)
    ap.add_argument("--tmp-dir", default=DEFAULT_TMP)
    ap.add_argument("--force-render", action="store_true")
    args = ap.parse_args()

    if not Path(args.pdf).exists():
        print(f"ERROR: PDF not found: {args.pdf}")
        sys.exit(1)

    # ── 1. Render ──────────────────────────────────────────────────────────────
    print(f"\n[1/4] Rendering PDF page {args.page} @ {args.dpi} DPI…")
    page_png = render_page(
        args.pdf, args.page, args.dpi, args.tmp_dir, args.force_render
    )

    orig_arr = cv2.cvtColor(cv2.imread(str(page_png)), cv2.COLOR_BGR2RGB)
    img_h, img_w = orig_arr.shape[:2]
    print(f"  Image size: {img_w} × {img_h} px")

    # Optionally restrict to one vertical panel
    if args.panel is not None:
        panel_w = img_w // args.cols
        x_start = args.panel * panel_w
        orig_arr = orig_arr[:, x_start : x_start + panel_w]
        img_h, img_w = orig_arr.shape[:2]
        print(f"  Cropped to panel {args.panel}: {img_w} × {img_h} px")

    # ── 2. High contrast ───────────────────────────────────────────────────────
    print("\n[2/4] Applying CLAHE high-contrast preprocessing…")
    gray = cv2.cvtColor(orig_arr, cv2.COLOR_RGB2GRAY)
    enhanced = apply_high_contrast(gray)
    save_cv_image(enhanced, str(Path(args.debug_dir) / "enhanced.png"))

    # ── 3. Edge detection ──────────────────────────────────────────────────────
    print("\n[3/4] Running edge detection…")
    edges = detect_edges(enhanced, args.canny_lo, args.canny_hi)
    save_cv_image(edges, str(Path(args.debug_dir) / "edges.png"))

    # ── 4. Contour detection → colour boxes ────────────────────────────────────
    print("\n[4/4] Detecting colour boxes via contour filtering…")
    raw_boxes = find_color_boxes(edges, args.cell_w, args.cell_h, args.box_frac)
    print(f"  Raw detections: {len(raw_boxes)} colour-box candidates")

    # Save raw detections (before grid snapping)
    raw_vis = orig_arr.copy()
    for bx, by, bw, bh in raw_boxes:
        cv2.rectangle(raw_vis, (bx, by), (bx + bw, by + bh), (0, 220, 0), 2)
    save_cv_image(
        cv2.cvtColor(raw_vis, cv2.COLOR_RGB2BGR),
        str(Path(args.debug_dir) / "detected_boxes.png"),
    )

    # ── 5. Grid snapping ───────────────────────────────────────────────────────
    grid = snap_to_grid(raw_boxes, args.cell_w, args.cell_h, args.gap, args.cols, img_h)
    snapped = sum(1 for g in grid if g["snapped"])
    total = len(grid)
    print(
        f"  Grid positions: {total}  ({snapped} detected, {total - snapped} inferred)"
    )

    save_debug_image(
        orig_arr,
        grid,
        args.cell_h,
        str(Path(args.debug_dir) / "grid_snapped.png"),
    )

    # ── Summary ────────────────────────────────────────────────────────────────
    print("\n── Summary ──────────────────────────────────────────────────────")
    print(f"  Page          : {args.page}  ({img_w}×{img_h} px)")
    print(f"  Cell size     : {args.cell_w} × {args.cell_h} px  (gap {args.gap} px)")
    print(f"  Columns       : {args.cols}")
    rows = grid[-1]["grid_row"] + 1 if grid else 0
    print(f"  Rows detected : {rows}")
    print(f"  Colour boxes  : {snapped} / {total} confirmed by contour detection")
    print(f"  Debug images  : {args.debug_dir}/")


if __name__ == "__main__":
    main()
