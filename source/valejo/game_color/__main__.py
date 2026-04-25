import argparse, sys
from pathlib import Path

_HERE = Path(__file__).resolve().parent
_ROOT = _HERE.parents[2]
sys.path.insert(0, str(_ROOT / "source" / "valejo"))
from _pdf_parser import run

CONFIG = {
    "pdf_path": str(_HERE / "GameColor.pdf"),
    "render_dpi": 300,
    "tmp_dir": str(_ROOT / ".tmp" / "vallejo_game_color"),
    "composite_page_index": 0,
    "composite_cols": 6,
    "composite_rows": 1,
    "panels_to_skip": [2, 3],
    "color_panels": [0, 1, 4, 5],
    "equiv_panels": [],
    "grid_cols": 10,
    "code_prefix": "72",
    "row_cluster_threshold": 80,
    "swatch_inset": 0.08,
    "output_json": str(_ROOT / "data" / "pack_vallejo_game_color.json"),
    "output_csv": str(_ROOT / "data" / "pack_vallejo_game_color.csv"),
    "brand_label": "Vallejo Game Color",
    "brand_id": "vallejo_game_color",
    "debug": False,
    "debug_show_cells": True,
    "debug_show_swatch": True,
    "debug_show_code_area": True,
    "debug_show_name_area": True,
    "debug_panel": None,
    "debug_output_dir": str(_ROOT / ".tmp" / "vallejo_game_color" / "debug"),
}


def parse_vallejo_game_color_images(folder_path=None, output_json=None):
    try:
        from source.valejo.texture_parser import parse_all_panels
    except Exception:
        from .texture_parser import parse_all_panels

    cfg = dict(CONFIG)
    return parse_all_panels(cfg, folder_path=Path(folder_path) if folder_path else None, output_json=Path(output_json) if output_json else None)


if __name__ == "__main__":
    ap = argparse.ArgumentParser(description="Vallejo Game Color PDF parser")
    ap.add_argument("--debug", action="store_true")
    ap.add_argument("--debug-panel", type=int, default=None)
    ap.add_argument("--dpi", type=int, default=None)
    ap.add_argument("--force-render", action="store_true")
    args = ap.parse_args()
    cfg2 = dict(CONFIG)
    if args.debug:
        cfg2["debug"] = True
    if args.debug_panel is not None:
        cfg2["debug_panel"] = args.debug_panel
    if args.dpi:
        cfg2["render_dpi"] = args.dpi
    if args.force_render:
        cfg2["force_render"] = True
    run(cfg2)
