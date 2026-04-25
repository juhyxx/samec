#!/usr/bin/env python3
"""
Vallejo orchestrator — runs all palette parsers.
Run individual palettes via their own __main__.py, or run this to process all.
"""
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent))
from vallejo_parser import parse_vallejo_images as _run_palette

PALETTES = [
    (
        "source/valejo/model_color",
        "data/pack_vallejo_model_color.json",
        "Vallejo Model Color",
        "vallejo_model_color",
    ),
    (
        "source/valejo/model_air",
        "data/pack_vallejo_model_air.json",
        "Vallejo Model Air",
        "vallejo_model_air",
    ),
    (
        "source/valejo/game_color",
        "data/pack_vallejo_game_color.json",
        "Vallejo Game Color",
        "vallejo_game_color",
    ),
    (
        "source/valejo/game_air",
        "data/pack_vallejo_game_air.json",
        "Vallejo Game Air",
        "vallejo_game_air",
    ),
    (
        "source/valejo/mecha_color",
        "data/pack_vallejo_mecha_color.json",
        "Vallejo Mecha Color",
        "vallejo_mecha_color",
    ),
]


def parse_vallejo_images(folder_path=None, output_json=None):
    """Entry point used by run_pipeline.py — runs all palettes."""
    for folder, out, label, brand_id in PALETTES:
        print(f"\n=== {label} ===")
        _run_palette(folder, out, label, brand_id)


if __name__ == "__main__":
    print("Starting Vallejo full parsing pipeline...")
    parse_vallejo_images()
