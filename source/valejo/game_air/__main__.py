from pathlib import Path

import cv2

_HERE = Path(__file__).resolve().parent
_ROOT = _HERE.parents[2]
from rich import print
import cv2
from PIL import Image
import easyocr
import numpy as np
import os

CONFIG = {
    "pdf_path": str(_HERE / "GameAir.pdf"),
    "render_dpi": 300,
    "tmp_dir": str(_ROOT / ".tmp" / "vallejo_game_air"),
    "composite_page_index": 1,
    "composite_cols": 4,
    "composite_rows": 1,
    "panels_to_skip": [0],
    "color_panels": [1, 2, 3],
    "equiv_panels": [4, 5],
    "grid_cols": 9,
    "code_prefix": "71",
    "row_cluster_threshold": 80,
    "swatch_inset": 0.08,
    "output_json": str(_ROOT / "data" / "pack_vallejo_game_air.json"),
    "output_csv": str(_ROOT / "data" / "pack_vallejo_game_air.csv"),
    "brand_label": "Vallejo Game Air",
    "brand_id": "vallejo_game_air",
    "debug": False,
    "debug_show_cells": True,
    "debug_show_swatch": True,
    "debug_show_code_area": True,
    "debug_show_name_area": True,
    "debug_panel": None,
    "debug_output_dir": str(_ROOT / ".tmp" / "vallejo_game_air" / "debug"),
}


def rgb_to_hex(arr):
    return "#{:02x}{:02x}{:02x}".format(int(arr[0]), int(arr[1]), int(arr[2]))


def parse_vallejo_game_air_images(
    folder_path: Path | None = None, output_json: Path | None = None
):
    """Pipeline entrypoint using the in-file per-image parser.

    - If `folder_path` contains `panel_01.png`, it will be used; otherwise the repo
      `source/valejo/game_air/panel_01.png` is used.
    - If `output_json` is provided the resulting list will be written there.
    Returns: list of color dicts (may be empty).
    """
    # collect panel images (support multiple panels)
    panels: list[Path] = []
    print(folder_path)
    tmp_dir = Path(CONFIG.get("tmp_dir"))
    # if folder_path:
    #     p = Path(folder_path)
    #     panels = sorted(p.glob("panel_*.png"))
    #     if not panels:
    #         panels = sorted(p.glob("*.png"))
    # else:
    # Prefer pre-rendered panels in the configured tmp dir
    if tmp_dir.exists():
        panels = sorted(tmp_dir.glob("panel_*.png"))
        if not panels:
            panels = sorted(tmp_dir.glob("*.png"))

    reader = easyocr.Reader(["en"], gpu=False)

    results: list[dict] = []

    panels = [panels[3]]

    for panel_path in panels:
        print(f"Processing panel: {panel_path}")
        try:
            with Image.open(panel_path) as im:
                img = np.array(im.convert("RGB"))
        except Exception as e:
            print(f"Failed to open {panel_path}: {e}")
            continue

        cells = get_grid(img, panel_path.stem)
        for ci, cell in enumerate(cells):
            parsed = parse_cell(cell, img, reader)
            if parsed is None:
                continue
            code_raw = parsed.get("code").strip() if parsed.get("code") else None
            if code_raw is None:
                continue
            code_norm = code_raw

            entry = {
                "panel": panel_path.name,
                "cell_index": ci,
                "code": code_norm or "",
                "name": parsed.get("name") or "",
                "hex": parsed.get("color") or "#cccccc",
            }
            results.append(entry)

    # Always write pack JSON for frontend compatibility. Prefer explicit output_json,
    # otherwise use the configured path.
    import json, csv

    outp = Path(output_json) if output_json else Path(CONFIG.get("output_json"))
    outp.parent.mkdir(parents=True, exist_ok=True)
    with outp.open("w", encoding="utf-8") as fh:
        json.dump(results, fh, ensure_ascii=False, indent=2)

    # also write a simple CSV for convenience
    csvp = Path(CONFIG.get("output_csv"))
    try:
        csvp.parent.mkdir(parents=True, exist_ok=True)
        with csvp.open("w", encoding="utf-8", newline="") as cf:
            writer = csv.writer(cf)
            writer.writerow(["panel", "cell_index", "code", "name", "hex"])
            for r in results:
                writer.writerow(
                    [
                        r.get("panel", ""),
                        r.get("cell_index", ""),
                        r.get("code", ""),
                        r.get("name", ""),
                        r.get("hex", ""),
                    ]
                )
    except Exception:
        # non-fatal; continue
        pass

    return results


def parse_cell(cell, img, reader):
    x, y, w, h = cell

    # clip coordinates to image bounds to avoid empty ROIs
    h_img, w_img = img.shape[:2]
    x = max(0, int(x))
    y = max(0, int(y))
    w = int(w)
    h = int(h)
    x2 = min(w_img, x + max(1, w))
    y2 = min(h_img, y + max(1, h))

    if x >= x2 or y >= y2:
        # invalid cell, return placeholder values
        parsed = {"code": None, "name": None, "color": "#cccccc"}
        print("Invalid cell bounds, skipping OCR", cell)
        return parsed

    # safe color ROI (ensure we don't go out of bounds)
    roi_color = img[y + 10 : min(y + 13, y2), x + 10 : min(x + 13, x2)]
    if roi_color.size == 0:
        mean_color = np.array([204, 204, 204])
    else:
        mean_color = roi_color.mean(axis=(0, 1))

    # OCR text from cell (safe ROI)
    roi = img[y:y2, x - 5 : x2 - 30]

    try:
        result = reader.readtext(roi)
        result = [r[1] for r in result if r[2] > 0.4]
    except Exception as e:
        print(f"OCR failed for cell {cell}: {e}")
        result = []

    parsed = {
        "code": result[0] if len(result) > 0 else None,
        "name": result[1] if len(result) > 1 else None,
        "color": rgb_to_hex(mean_color),
    }
    if parsed["code"] is None:
        return None
    print("code:", parsed["code"], "name:", parsed["name"], "color:", parsed["color"])
    return parsed


def get_grid(img, panel_name=""):

    top_padding = 180

    os.makedirs(CONFIG["debug_output_dir"], exist_ok=True)
    gray = cv2.cvtColor(img, cv2.COLOR_BGR2GRAY)
    clahe = cv2.createCLAHE(2.0, (8, 8))
    gray = clahe.apply(gray)

    edges = cv2.Canny(gray, 10, 80)

    edges[0:top_padding, :] = 0

    kernel_h = cv2.getStructuringElement(cv2.MORPH_RECT, (10, 1))
    horiz = cv2.morphologyEx(edges, cv2.MORPH_OPEN, kernel_h)

    horiz = cv2.erode(edges, kernel_h)
    horiz = cv2.dilate(horiz, kernel_h)

    kernel_v = cv2.getStructuringElement(cv2.MORPH_RECT, (1, 80))
    vert = cv2.morphologyEx(edges, cv2.MORPH_OPEN, kernel_v, iterations=1)
    kernel = cv2.getStructuringElement(cv2.MORPH_RECT, (5, 5))

    cv2.imwrite(
        CONFIG["tmp_dir"] + f"/debug/{panel_name}_debug_horiz.png", horiz.copy()
    )
    cv2.imwrite(CONFIG["tmp_dir"] + f"/debug/{panel_name}_debug_vert.png", vert.copy())

    grid = cv2.bitwise_or(horiz, vert)
    # grid = cv2.morphologyEx(grid, cv2.MORPH_CLOSE, kernel, iterations=2)

    cv2.imwrite(CONFIG["tmp_dir"] + f"/debug/{panel_name}_debug_grid.png", grid.copy())

    col_sum = np.sum(vert, axis=0)
    row_sum = np.sum(horiz, axis=1)

    col_sum = np.where(col_sum >= 10_000, col_sum, 0)
    row_sum = np.where(row_sum >= 100_150, row_sum, 0)

    def find_lines(proj, threshold):
        lines = []
        active = False
        start = 0

        for i, v in enumerate(proj):
            if v > threshold and not active:
                active = True
                start = i
            elif v <= threshold and active:
                active = False
                lines.append((start + i) // 2)

        return lines

    xs = find_lines(col_sum, threshold=1000)
    ys = find_lines(row_sum, threshold=1000)

    ys.append(len(row_sum) - 250)

    out = img.copy()

    # svislé čáry (x pozice)
    for x in xs:
        cv2.line(out, (x, 0), (x, out.shape[0]), (0, 0, 255), 2)

    # vodorovné čáry (y pozice)
    for y in ys:
        cv2.line(out, (0, y), (out.shape[1], y), (255, 0, 0), 2)

    cv2.imwrite(CONFIG["tmp_dir"] + f"/debug/{panel_name}_debug_lines_out.png", out)

    ys = ys[0::2]  # vynech sude

    rectangles = []

    for i in range(len(xs) - 1):
        for j in range(len(ys) - 1):
            x1, x2 = xs[i], xs[i + 1]
            y1, y2 = ys[j], ys[j + 1]

            w = x2 - x1
            h = y2 - y1

            if w > 100 and h > 140:  # filtr velikosti
                rectangles.append((x1, y1, w, h))

    out = img.copy()
    for x, y, w, h in rectangles:
        cv2.rectangle(out, (x, y), (x + w, y + h), (0, 0, 255), 2)

    cv2.imwrite(CONFIG["tmp_dir"] + f"/debug/{panel_name}_debug_grid_out.png", out)

    return rectangles
