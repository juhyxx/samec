#!/usr/bin/env python3
"""
Master pipeline to parse all color charts and prepare data for frontend.
Runs parsers for all producers and formats output.
"""

import json
import sys
from pathlib import Path
import subprocess
import importlib.util

# Add source to path
SCRIPT_DIR = Path(__file__).parent.parent
sys.path.insert(0, str(SCRIPT_DIR))

# Import modules - handle hyphenated folder names
mr_hobby_spec = importlib.util.spec_from_file_location(
    "parse_mr_hobby", str(SCRIPT_DIR / "source/mr_hobby/parse.py")
)
parse_mr_hobby = importlib.util.module_from_spec(mr_hobby_spec)
mr_hobby_spec.loader.exec_module(parse_mr_hobby)
parse_mr_hobby_images = parse_mr_hobby.parse_mr_hobby_images

ammo_atom_spec = importlib.util.spec_from_file_location(
    "parse_ammo_atom", str(SCRIPT_DIR / "source/ammo-atom/parse.py")
)
parse_ammo_atom = importlib.util.module_from_spec(ammo_atom_spec)
ammo_atom_spec.loader.exec_module(parse_ammo_atom)
parse_ammo_atom_images = parse_ammo_atom.parse_ammo_atom_images

ak_spec = importlib.util.spec_from_file_location(
    "parse_ak", str(SCRIPT_DIR / "source/ak/parse.py")
)
parse_ak = importlib.util.module_from_spec(ak_spec)
ak_spec.loader.exec_module(parse_ak)
parse_ak_images = parse_ak.parse_ak_images

from source.common.format_frontend import format_for_frontend


def format_colors(colors, brand_name, brand_id):
    """Format raw colors into frontend format."""
    # Ensure hex values have # prefix
    formatted = []
    for color in colors:
        hex_val = color.get("hex", "")
        if hex_val and not hex_val.startswith("#"):
            hex_val = f"#{hex_val}"

        formatted.append(
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
        "source": f"data/results/pack_{brand_id}.json",
        "count": len(formatted),
        "colors": formatted,
    }


def run_all_parsers():
    """Run all parser scripts and organize results."""
    results_dir = Path("data/results")
    results_dir.mkdir(parents=True, exist_ok=True)

    print("🎨 Color Chart Parsing Pipeline")
    print("=" * 50)

    # Parse Mr. Hobby
    print("\n1️⃣  Parsing Mr. Hobby...")
    try:
        mr_hobby_colors = parse_mr_hobby_images(
            Path("source/mr_hobby"), Path("data/results/pack_mr_hobby.json")
        )
        if mr_hobby_colors:
            formatted = format_colors(mr_hobby_colors, "Mr. Hobby", "mr_hobby")
            with open(Path("data/results/pack_mr_hobby.json"), "w") as f:
                json.dump(formatted, f, indent=2, ensure_ascii=False)
            print(f"   ✅ {len(mr_hobby_colors)} colors extracted")
    except Exception as e:
        print(f"   ⚠️  Error: {e}")

    # Parse Ammo-Atom
    print("\n2️⃣  Parsing Ammo-Atom...")
    try:
        atom_colors = parse_ammo_atom_images(
            Path("source/ammo-atom"), Path("data/results/pack_ammo_atom.json")
        )
        if atom_colors:
            formatted = format_colors(atom_colors, "Ammo by Mig Atom", "ammo_atom")
            with open(Path("data/results/pack_ammo_atom.json"), "w") as f:
                json.dump(formatted, f, indent=2, ensure_ascii=False)
            print(f"   ✅ {len(atom_colors)} colors extracted")
    except Exception as e:
        print(f"   ⚠️  Error: {e}")

    # Parse AK Interactive
    print("\n3️⃣  Parsing AK Interactive...")
    try:
        ak_colors = parse_ak_images(
            Path("source/ak"), Path("data/results/pack_ak.json")
        )
        if ak_colors:
            formatted = format_colors(ak_colors, "AK Interactive", "ak_interactive")
            with open(Path("data/results/pack_ak.json"), "w") as f:
                json.dump(formatted, f, indent=2, ensure_ascii=False)
            print(f"   ✅ {len(ak_colors)} colors extracted")
    except Exception as e:
        print(f"   ⚠️  Error: {e}")

    print("\n" + "=" * 50)
    print("✅ Pipeline complete!")
    print(f"📁 Results saved to data/results/")


if __name__ == "__main__":
    run_all_parsers()
