#!/usr/bin/env python3
"""Parse the fixed-layout Tamiya XF paint chip chart."""

from pathlib import Path
import csv
import json

import numpy as np
from PIL import Image


TAMIYA_FOLDER = Path("source/tamiya")
IMAGE_NAME = "tamiya-xf-paint-chips-7011.jpg"

BASE_WIDTH = 1200
BASE_HEIGHT = 808
GRID_X_START = 76
GRID_Y_START = 39
GRID_X_STEP = 121
GRID_Y_STEP = 110
SAMPLE_SIZE = 16
SAMPLE_OFFSET_X = -20
SAMPLE_OFFSET_Y = 0

TAMIYA_ROWS = [
    [
        ("XF1", "Flat Black"),
        ("XF2", "Flat White"),
        ("XF3", "Flat Yellow"),
        ("XF4", "Yellow Green"),
        ("XF5", "Flat Green"),
        ("XF6", "Copper"),
        ("XF7", "Flat Red"),
        ("XF8", "Flat Blue"),
        ("XF9", "Hull Red"),
        ("XF10", "Flat Brown"),
    ],
    [
        ("XF11", "J.N. Green"),
        ("XF12", "J.N. Gray"),
        ("XF13", "J.A. Green"),
        ("XF14", "J.A. Gray"),
        ("XF15", "Flat Flesh"),
        ("XF16", "Flat Aluminum"),
        ("XF17", "Sea Blue"),
        ("XF18", "Medium Blue"),
        ("XF19", "Sky Gray"),
        ("XF20", "Medium Gray"),
    ],
    [
        ("XF21", "Sky"),
        ("XF22", "RLM Gray"),
        ("XF23", "Light Blue"),
        ("XF24", "Dark Gray"),
        ("XF25", "Light Sea Gray"),
        ("XF26", "Deep Green"),
        ("XF27", "Black Green"),
        ("XF28", "Dark Copper"),
        ("XF49", "Khaki"),
        ("XF50", "Field Blue"),
    ],
    [
        ("XF51", "Khaki Drab"),
        ("XF52", "Flat Earth"),
        ("XF53", "Neutral Gray"),
        ("XF54", "Dark Sea Gray"),
        ("XF55", "Deck Tan"),
        ("XF56", "Metallic Gray"),
        ("XF57", "Buff"),
        ("XF58", "Olive Green"),
        ("XF59", "Desert Yellow"),
        ("XF60", "Dark Yellow"),
    ],
    [
        ("XF61", "Dark Green"),
        ("XF62", "Olive Drab"),
        ("XF63", "German Gray"),
        ("XF64", "Red Brown"),
        ("XF65", "Field Gray"),
        ("XF66", "Light Gray"),
        ("XF67", "NATO Green"),
        ("XF68", "NATO Brown"),
        ("XF69", "NATO Black"),
        ("XF70", "Dark Green 2"),
    ],
    [
        ("XF71", "Cockpit Green (IJN)"),
        ("XF72", "Brown (JGSDF)"),
        ("XF73", "Dark Green (JGSDF)"),
        ("XF74", "Olive Drab (JGSDF)"),
        ("XF75", "IJN Gray"),
        ("XF76", "Gray Green"),
        ("XF77", "IJN Gray (Sasebo Arsenal)"),
        ("XF78", "Deck Tan Wooden"),
        ("XF79", "Deck Brown Linoleum"),
        ("XF80", "Navy Gray (British)"),
    ],
    [
        ("XF81", "Dark Green"),
        ("XF82", "Ocean Gray"),
        ("XF83", "Medium Sea Gray"),
        ("XF84", "Dark Iron"),
        ("XF85", "Rubber Black"),
        ("XF86", "Flat Clear"),
        ("XF87", "IJN Gray (Maizuru Arsenal)"),
        ("XF88", "Light Green"),
        ("XF89", "Green"),
        ("XF90", "Purple"),
    ],
]


def rgb_to_hex(values):
    return "#{:02x}{:02x}{:02x}".format(
        int(values[0]),
        int(values[1]),
        int(values[2]),
    )


def sample_chip_color(image_array, row_index, col_index):
    scale_x = image_array.shape[1] / BASE_WIDTH
    scale_y = image_array.shape[0] / BASE_HEIGHT

    center_x = int(
        round((GRID_X_START + col_index * GRID_X_STEP + SAMPLE_OFFSET_X) * scale_x)
    )
    center_y = int(
        round((GRID_Y_START + row_index * GRID_Y_STEP + SAMPLE_OFFSET_Y) * scale_y)
    )

    half_size_x = max(6, int(round((SAMPLE_SIZE / 2) * scale_x)))
    half_size_y = max(6, int(round((SAMPLE_SIZE / 2) * scale_y)))

    left = max(0, center_x - half_size_x)
    right = min(image_array.shape[1], center_x + half_size_x)
    top = max(0, center_y - half_size_y)
    bottom = min(image_array.shape[0], center_y + half_size_y)

    region = image_array[top:bottom, left:right]
    avg_color = region.reshape(-1, 3).mean(axis=0)
    return rgb_to_hex(avg_color)


def parse_tamiya_images(folder_path, output_json):
    folder = Path(folder_path)
    output_json = Path(output_json)
    image_path = folder / IMAGE_NAME

    if not image_path.exists():
        print(f"Tamiya chart not found: {image_path}")
        return []

    with Image.open(image_path) as image:
        image_array = np.array(image.convert("RGB"))

    colors = []
    for row_index, row in enumerate(TAMIYA_ROWS):
        for col_index, (code, name) in enumerate(row):
            colors.append(
                {
                    "code": code,
                    "name": name,
                    "hex": sample_chip_color(
                        image_array,
                        row_index,
                        col_index,
                    ),
                    "equivalents": [],
                    "confidence": None,
                }
            )

    pack = {
        "brand": "Tamiya",
        "brand_id": "tamiya",
        "source": str(output_json),
        "count": len(colors),
        "colors": colors,
    }

    output_json.parent.mkdir(parents=True, exist_ok=True)
    output_json.write_text(
        json.dumps(pack, indent=2, ensure_ascii=False),
        encoding="utf-8",
    )
    print(f"Wrote {len(colors)} colors to {output_json}")

    csv_path = output_json.parent / "pack_tamiya.csv"
    with csv_path.open("w", newline="", encoding="utf-8") as file_handle:
        writer = csv.DictWriter(
            file_handle,
            fieldnames=["code", "name", "hex"],
        )
        writer.writeheader()
        for color in colors:
            writer.writerow(
                {
                    "code": color["code"],
                    "name": color["name"],
                    "hex": color["hex"],
                }
            )
    print(f"Wrote CSV to {csv_path}")

    return colors


def main():
    parse_tamiya_images(TAMIYA_FOLDER, Path("data/pack_tamiya.json"))


if __name__ == "__main__":
    main()
