from pathlib import Path

import cv2
from shapely import snap

_HERE = Path(__file__).resolve().parent
_ROOT = _HERE.parents[2]
from rich import print
import cv2
from PIL import Image
import easyocr
import numpy as np

CONFIG = {
    "pdf_path": str(_HERE / "ModelAir.pdf"),
    "render_dpi": 300,
    "tmp_dir": str(_ROOT / ".tmp" / "vallejo_model_air"),
    "composite_page_index": 1,
    "composite_cols": 6,
    "composite_rows": 1,
    "panels_to_skip": [0],
    "color_panels": [1, 2, 3],
    "equiv_panels": [4, 5],
    "grid_cols": 9,
    "code_prefix": "71",
    "row_cluster_threshold": 80,
    "swatch_inset": 0.08,
    "output_json": str(_ROOT / "data" / "pack_vallejo_model_air.json"),
    "output_csv": str(_ROOT / "data" / "pack_vallejo_model_air.csv"),
    "brand_label": "Vallejo Model Air",
    "brand_id": "vallejo_model_air",
    "debug": False,
    "debug_show_cells": True,
    "debug_show_swatch": True,
    "debug_show_code_area": True,
    "debug_show_name_area": True,
    "debug_panel": None,
    "debug_output_dir": str(_ROOT / ".tmp" / "vallejo_model_air" / "debug"),
}


def rgb_to_hex(arr):
    return "#{:02x}{:02x}{:02x}".format(int(arr[0]), int(arr[1]), int(arr[2]))


def parse_vallejo_model_air_images(
    folder_path: Path | None = None, output_json: Path | None = None
):
    """Pipeline entrypoint using the in-file per-image parser.

    - If `folder_path` contains `panel_01.png`, it will be used; otherwise the repo
      `source/valejo/model_air/panel_01.png` is used.
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
    trans_map = str.maketrans(
        {"O": "0", "o": "0", "I": "1", "l": "1", "i": "1", "S": "5", "s": "5"}
    )
    results: list[dict] = []

    print(panels)

    panels = panels[1:3]

    for panel_path in panels:
        print(f"Processing panel: {panel_path}")
        try:
            with Image.open(panel_path) as im:
                img = np.array(im.convert("RGB"))
        except Exception as e:
            print(f"Failed to open {panel_path}: {e}")
            continue

        cells = get_cells_from_image(img)
        for ci, cell in enumerate(cells):
            parsed = parse_cell(cell, img, reader)
            code_raw = parsed.get("code")
            name = parsed.get("name")
            hexcol = parsed.get("color")

            code_norm = None
            if code_raw:
                t = str(code_raw).translate(trans_map)
                digits = "".join(ch for ch in t if ch.isdigit())
                if len(digits) >= 3:
                    digits = digits[-3:]
                    code_norm = f"{CONFIG.get('code_prefix')}.{digits}"

            entry = {
                "panel": panel_path.name,
                "cell_index": ci,
                "code": code_norm or "",
                "name": name or "",
                "hex": hexcol or "#cccccc",
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

    roi_color = img[y + 10 : y + 13, x + 10 : x + 13]
    mean_color = roi_color.mean(axis=(0, 1))

    # ocr text from cell
    roi = img[y : y + h, x : x + w]

    result = reader.readtext(roi)
    result = [r[1] for r in result if r[2] > 0.4]

    parsed = {
        "code": result[0] if len(result) > 0 else None,
        "name": " ".join(result[1:]) if len(result) > 1 else None,
        "color": rgb_to_hex(mean_color),
    }
    print("code:", parsed["code"], "name:", parsed["name"], "color:", parsed["color"])
    return parsed


def get_cells_from_image(img):

    gray = cv2.cvtColor(img, cv2.COLOR_RGB2GRAY)
    # adjusted = cv2.convertScaleAbs(gray, alpha=1.5, beta=1)
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

    rectangles = map(
        lambda r: (snap(r[0]), snap(r[1]), snap(r[2]), snap(r[3])), rectangles
    )
    rectangles = sorted(rectangles, key=lambda r: (r[1], r[0]))

    grid = (set(), set(), set(), set())

    for i, (x, y, w, h) in enumerate(rectangles):
        grid[0].add(x)
        grid[1].add(y)
        grid[2].add(w)
        grid[3].add(h)

    grid = (sorted(grid[0]), sorted(grid[1]), sorted(grid[2]), sorted(grid[3]))

    cells = []
    try:
        h = grid[1][1] - grid[1][0]

        for x in grid[0]:
            for y in grid[1]:
                cells.append((x, y, grid[2][0], h - 3))
    except Exception as e:
        print("Error constructing cells from grid:", e)

    return cells

    #  out = img.copy()
    # for x, y, w, h in cells:
    #     cv2.rectangle(out, (x, y), (x + w, y + h), (0, 0, 255), 2)
    # cv2.imshow("image", out)
    # cv2.waitKey(0)
