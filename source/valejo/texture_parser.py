from pathlib import Path
import json, csv
from PIL import Image
import numpy as np
import cv2

def render_pdf_pages(pdf_path: Path, out_dir: Path, dpi: int = 300):
    try:
        import fitz
    except Exception:
        return []
    if not pdf_path.exists():
        return []
    out_dir.mkdir(parents=True, exist_ok=True)
    doc = fitz.open(str(pdf_path))
    panels = []
    for i, page in enumerate(doc, start=1):
        mat = fitz.Matrix(dpi / 72.0, dpi / 72.0)
        pix = page.get_pixmap(matrix=mat, alpha=False)
        outp = out_dir / f"panel_{i:02d}.png"
        pix.save(str(outp))
        panels.append(outp)
    return panels


def collect_panels(tmp_dir: Path, folder_path: Path | None = None):
    tmp = Path(tmp_dir)
    panels = []
    if tmp.exists():
        panels = sorted(tmp.glob("panel_*.png"))
        if not panels:
            panels = sorted(tmp.glob("*.png"))
    if not panels and folder_path:
        p = Path(folder_path)
        panels = sorted(p.glob("panel_*.png"))
        if not panels:
            panels = sorted(p.glob("*.png"))
    if not panels:
        p = Path.cwd() / "source/valejo"
        panels = sorted(p.glob("panel_*.png"))
    return panels


def get_cells_from_image(img: np.ndarray, grid_cols: int = 9):
    gray = cv2.cvtColor(img, cv2.COLOR_RGB2GRAY)
    thresh = cv2.adaptiveThreshold(
        gray, 255, cv2.ADAPTIVE_THRESH_GAUSSIAN_C, cv2.THRESH_BINARY_INV, 15, 3
    )
    contours, _ = cv2.findContours(thresh, cv2.RETR_EXTERNAL, cv2.CHAIN_APPROX_SIMPLE)
    MIN_W, MIN_H = 100, 100
    filtered_contours = []
    for cnt in contours:
        approx = cv2.approxPolyDP(cnt, 0.02 * cv2.arcLength(cnt, True), True)
        if len(approx) == 4 and cv2.isContourConvex(approx):
            x, y, w, h = cv2.boundingRect(approx)
            if w >= MIN_W and h >= MIN_H:
                filtered_contours.append(approx)
    rectangles = []
    for cnt in filtered_contours:
        x, y, w, h = cv2.boundingRect(cnt)
        rectangles.append((x, y, w, h))
    def snap(v, step=5):
        return round(v / step) * step
    rectangles = map(lambda r: (snap(r[0]), snap(r[1]), snap(r[2]), snap(r[3])), rectangles)
    rectangles = sorted(rectangles, key=lambda r: (r[1], r[0]))
    grid = (set(), set(), set(), set())
    for i, (x, y, w, h) in enumerate(rectangles):
        grid[0].add(x)
        grid[1].add(y)
        grid[2].add(w)
        grid[3].add(h)
    grid = (sorted(grid[0]), sorted(grid[1]), sorted(grid[2]), sorted(grid[3]))
    cells = []
    if len(grid[1]) < 2 or len(grid[0]) < 1 or len(grid[2]) < 1:
        img_h, img_w = img.shape[0], img.shape[1]
        cols = grid_cols
        est_cell_w = max(1, img_w // max(1, cols))
        est_rows = max(1, round(img_h / est_cell_w))
        cell_w = img_w // cols
        cell_h = img_h // est_rows
        for cx in range(cols):
            x = cx * cell_w
            for ry in range(est_rows):
                y = ry * cell_h
                cells.append((x, y, cell_w, cell_h))
        return cells
    h = grid[1][1] - grid[1][0]
    for x in grid[0]:
        for y in grid[1]:
            cells.append((x, y, grid[2][0], h - 3))
    return cells


def parse_cell_generic(cell, img: np.ndarray, reader, color_offset=(10, 10), ocr_conf=0.4):
    x, y, w, h = cell
    ox, oy = color_offset
    sx = min(img.shape[1] - 1, x + ox)
    sy = min(img.shape[0] - 1, y + oy)
    roi_color = img[sy - 1 : sy + 2, sx - 1 : sx + 2]
    if roi_color.size == 0:
        mean_color = np.array([204, 204, 204])
    else:
        mean_color = roi_color.mean(axis=(0, 1))
    roi = img[y : y + h, x : x + w]
    result = reader.readtext(roi)
    result = [r[1] for r in result if r[2] > ocr_conf]
    code = result[0] if len(result) > 0 else None
    name = " ".join(result[1:]) if len(result) > 1 else None
    hexcol = "#{:02x}{:02x}{:02x}".format(int(mean_color[0]), int(mean_color[1]), int(mean_color[2]))
    return {"code": code, "name": name, "color": hexcol}


def parse_all_panels(config: dict, folder_path: Path | None = None, output_json: Path | None = None):
    tmp_dir = Path(config.get("tmp_dir"))
    pdf_path = Path(config.get("pdf_path"))
    # render PDF pages into tmp_dir
    try:
        render_pdf_pages(pdf_path, tmp_dir, dpi=config.get("render_dpi", 300))
    except Exception:
        pass
    panels = collect_panels(tmp_dir, folder_path)
    if not panels:
        return []
    import easyocr
    reader = easyocr.Reader(["en"], gpu=False)
    trans_map = str.maketrans({"O": "0", "o": "0", "I": "1", "l": "1", "i": "1", "S": "5", "s": "5"})
    results = []
    for panel_path in panels:
        try:
            with Image.open(panel_path) as im:
                img = np.array(im.convert("RGB"))
        except Exception:
            continue
        cells = get_cells_from_image(img, grid_cols=config.get("grid_cols", 9))
        for ci, cell in enumerate(cells):
            parsed = parse_cell_generic(cell, img, reader)
            code_raw = parsed.get("code")
            name = parsed.get("name")
            hexcol = parsed.get("color")
            code_norm = ""
            if code_raw:
                t = str(code_raw).translate(trans_map)
                digits = "".join(ch for ch in t if ch.isdigit())
                if len(digits) >= 3:
                    digits = digits[-3:]
                    code_norm = f"{config.get('code_prefix')}.{digits}"
            entry = {"panel": panel_path.name, "cell_index": ci, "code": code_norm, "name": name or "", "hex": hexcol or "#cccccc"}
            results.append(entry)
    # write outputs
    outp = Path(output_json) if output_json else Path(config.get("output_json"))
    outp.parent.mkdir(parents=True, exist_ok=True)
    with outp.open("w", encoding="utf-8") as fh:
        json.dump(results, fh, ensure_ascii=False, indent=2)
    csvp = Path(config.get("output_csv"))
    try:
        csvp.parent.mkdir(parents=True, exist_ok=True)
        with csvp.open("w", encoding="utf-8", newline="") as cf:
            writer = csv.writer(cf)
            writer.writerow(["panel", "cell_index", "code", "name", "hex"])
            for r in results:
                writer.writerow([r.get("panel", ""), r.get("cell_index", ""), r.get("code", ""), r.get("name", ""), r.get("hex", "")])
    except Exception:
        pass
    return results
