#!/usr/bin/env python3
"""
Convert simple color data (code, name, hex) to the full frontend format with brand and metadata.
"""

import json
from pathlib import Path


def format_for_frontend(colors, brand_name, brand_id, source_file=None):
    """
    Format colors for frontend consumption.

    Args:
        colors: List of {code, name, hex, equivalents?, confidence?}
        brand_name: Display name (e.g., "Mr. Color")
        brand_id: Short ID for data (e.g., "mr_color")
        source_file: Optional source file reference

    Returns:
        Dict with brand metadata and colors array
    """
    # Ensure hex values have # prefix
    formatted_colors = []
    for color in colors:
        hex_val = color.get("hex", "")
        if hex_val and not hex_val.startswith("#"):
            hex_val = f"#{hex_val}"

        formatted_colors.append(
            {
                "code": color.get("code", ""),
                "name": color.get("name", "Unnamed"),
                "hex": hex_val,
                "equivalents": color.get("equivalents", []),
                "confidence": color.get("confidence"),
            }
        )

    return {
        "brand": brand_name,
        "brand_id": brand_id,
        "source": source_file or f"data/pack_{brand_id}.json",
        "count": len(formatted_colors),
        "colors": formatted_colors,
    }


def process_mr_color(raw_colors_file, output_file):
    """Process Mr. Color colors."""
    with open(raw_colors_file) as f:
        colors = json.load(f)

    formatted = format_for_frontend(colors, brand_name="Mr. Color", brand_id="mr_color")

    output_file.parent.mkdir(parents=True, exist_ok=True)
    with open(output_file, "w") as f:
        json.dump(formatted, f, indent=2, ensure_ascii=False)

    print(f"Wrote {len(colors)} Mr. Color colors to {output_file}")


def process_ammo_atom(raw_colors_file, output_file):
    """Process Ammo-Atom colors."""
    with open(raw_colors_file) as f:
        colors = json.load(f)

    formatted = format_for_frontend(
        colors, brand_name="Ammo by Mig Atom", brand_id="ammo_atom"
    )

    output_file.parent.mkdir(parents=True, exist_ok=True)
    with open(output_file, "w") as f:
        json.dump(formatted, f, indent=2, ensure_ascii=False)

    print(f"Wrote {len(colors)} Ammo-Atom colors to {output_file}")


def process_ak(raw_colors_file, output_file):
    """Process AK Interactive colors."""
    with open(raw_colors_file) as f:
        colors = json.load(f)

    formatted = format_for_frontend(colors, brand_name="AK Interactive", brand_id="ak")

    output_file.parent.mkdir(parents=True, exist_ok=True)
    with open(output_file, "w") as f:
        json.dump(formatted, f, indent=2, ensure_ascii=False)

    print(f"Wrote {len(colors)} AK colors to {output_file}")


if __name__ == "__main__":
    # Define paths
    results_dir = Path("data/")

    # Process each brand
    # Mr. Color
    mr_color_raw = results_dir / "pack_mr_color.json"
    if mr_color_raw.exists():
        process_mr_color(mr_color_raw, results_dir / "pack_mr_color.json")

    # Ammo-Atom
    atom_raw = results_dir / "pack_ammo_atom.json"
    if atom_raw.exists():
        process_ammo_atom(atom_raw, results_dir / "pack_ammo_atom.json")

    # AK
    ak_raw = results_dir / "pack_ak.json"
    if ak_raw.exists():
        process_ak(ak_raw, results_dir / "pack_ak.json")
