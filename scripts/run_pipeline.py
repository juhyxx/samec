#!/usr/bin/env python3
"""
Master pipeline to parse all color charts and prepare data for frontend.
Supports running all parsers or individual ones via CLI arguments.

Usage:
  python3 scripts/run_pipeline.py                    # Run all
  python3 scripts/run_pipeline.py mr_hobby           # Run Mr. Hobby only
    python3 scripts/run_pipeline.py ammo               # Run Ammo by Mig only
  python3 scripts/run_pipeline.py ammo-atom          # Run Ammo-Atom only
    python3 scripts/run_pipeline.py gunze              # Run Gunze Sangyo only
    python3 scripts/run_pipeline.py tamiya             # Run Tamiya only
  python3 scripts/run_pipeline.py ak                 # Run AK Interactive only
"""

import json
import sys
import argparse
from pathlib import Path
import importlib.util

# Add source to path
SCRIPT_DIR = Path(__file__).parent.parent
sys.path.insert(0, str(SCRIPT_DIR))


def load_module(module_name, file_path):
    """Load a module from a file path."""
    spec = importlib.util.spec_from_file_location(module_name, str(file_path))
    if spec is None or spec.loader is None:
        raise ImportError(f"Unable to load module {module_name} from {file_path}")

    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    return module


# Import modules - handle hyphenated folder names
parse_mr_hobby = load_module(
    "parse_mr_hobby", SCRIPT_DIR / "source/mr_hobby/__main__.py"
)
parse_mr_hobby_images = parse_mr_hobby.parse_mr_hobby_images

parse_ammo = load_module("parse_ammo", SCRIPT_DIR / "source/ammo/__main__.py")
parse_ammo_images = parse_ammo.parse_ammo_images

parse_ammo_atom = load_module(
    "parse_ammo_atom", SCRIPT_DIR / "source/ammo-atom/__main__.py"
)
parse_ammo_atom_images = parse_ammo_atom.parse_ammo_atom_images

parse_gunze = load_module("parse_gunze", SCRIPT_DIR / "source/gunze/__main__.py")
parse_gunze_images = parse_gunze.parse_gunze_images

parse_tamiya = load_module("parse_tamiya", SCRIPT_DIR / "source/tamiya/__main__.py")
parse_tamiya_images = parse_tamiya.parse_tamiya_images

parse_ak = load_module("parse_ak", SCRIPT_DIR / "source/ak/__main__.py")
parse_ak_images = parse_ak.parse_ak_images


def load_equivalents(equivalents_file):
    """Load equivalents mapping from JSON file."""
    with open(equivalents_file, encoding="utf-8") as f:
        return json.load(f)


def merge_equivalents(colors, equivalents_map, brand_id):
    """Merge equivalents from mapping into colors."""
    brand_equivs = equivalents_map.get(brand_id, {})

    for color in colors:
        code = color.get("code")
        if code and code in brand_equivs:
            color["equivalents"] = brand_equivs[code]

    return colors


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
        "source": f"data/pack_{brand_id}.json",
        "count": len(formatted),
        "colors": formatted,
    }


def run_parser(brand_id, parser_func, source_dir, output_file, brand_name):
    """Run a single parser and format results."""
    print(f"\n{brand_id.upper()}: {brand_name}...")
    try:
        colors = parser_func(Path(source_dir), Path(output_file))
        if colors:
            # Load equivalents
            equiv_file = Path("data/equivalents.json")
            equivalents = {}
            if equiv_file.exists():
                with open(equiv_file, encoding="utf-8") as f:
                    equivalents = json.load(f)

            # Merge equivalents into colors
            colors = merge_equivalents(colors, equivalents, brand_id)

            # Format for frontend
            formatted = format_colors(colors, brand_name, brand_id)

            # Save results
            Path(output_file).parent.mkdir(parents=True, exist_ok=True)
            with open(output_file, "w", encoding="utf-8") as f:
                json.dump(formatted, f, indent=2, ensure_ascii=False)

            print(f"   ✅ {len(colors)} colors extracted")
            return True
        else:
            print("   ⚠️  No colors extracted")
            return False
    except Exception as err:
        print(f"   ❌ Error: {err}")
        import traceback

        traceback.print_exc()
        return False


def run_all_parsers():
    """Run all parser scripts and organize results."""
    results_dir = Path("data/")
    results_dir.mkdir(parents=True, exist_ok=True)

    print("🎨 Color Chart Parsing Pipeline")
    print("=" * 50)

    # Define all parsers
    parsers = [
        (
            "mr_hobby",
            parse_mr_hobby_images,
            "source/mr_hobby",
            "data/pack_mr_hobby.json",
            "Mr. Hobby",
        ),
        (
            "ammo",
            parse_ammo_images,
            "source/ammo",
            "data/pack_ammo.json",
            "Ammo by Mig",
        ),
        (
            "ammo_atom",
            parse_ammo_atom_images,
            "source/ammo-atom",
            "data/pack_ammo_atom.json",
            "Ammo by Mig Atom",
        ),
        (
            "gunze",
            parse_gunze_images,
            "source/gunze",
            "data/pack_gunze.json",
            "Gunze Sangyo",
        ),
        (
            "tamiya",
            parse_tamiya_images,
            "source/tamiya",
            "data/pack_tamiya.json",
            "Tamiya",
        ),
        (
            "ak",
            parse_ak_images,
            "source/ak",
            "data/pack_ak.json",
            "AK Interactive",
        ),
    ]

    # Run selected or all parsers
    success_count = 0
    for brand_id, parser_func, source_dir, output_file, brand_name in parsers:
        if run_parser(brand_id, parser_func, source_dir, output_file, brand_name):
            success_count += 1

    print("\n" + "=" * 50)
    total = len(parsers)
    print(f"✅ Pipeline complete! ({success_count}/{total} parsers succeeded)")
    print("📁 Results saved to data/")


def run_single_parser(brand):
    """Run a single parser by brand name."""
    parsers = {
        "mr_hobby": (
            "mr_hobby",
            parse_mr_hobby_images,
            "source/mr_hobby",
            "data/pack_mr_hobby.json",
            "Mr. Hobby",
        ),
        "mr-hobby": (
            "mr_hobby",
            parse_mr_hobby_images,
            "source/mr_hobby",
            "data/pack_mr_hobby.json",
            "Mr. Hobby",
        ),
        "ammo": (
            "ammo",
            parse_ammo_images,
            "source/ammo",
            "data/pack_ammo.json",
            "Ammo by Mig",
        ),
        "ammo-by-mig": (
            "ammo",
            parse_ammo_images,
            "source/ammo",
            "data/pack_ammo.json",
            "Ammo by Mig",
        ),
        "ammo-atom": (
            "ammo_atom",
            parse_ammo_atom_images,
            "source/ammo-atom",
            "data/pack_ammo_atom.json",
            "Ammo by Mig Atom",
        ),
        "ammo_atom": (
            "ammo_atom",
            parse_ammo_atom_images,
            "source/ammo-atom",
            "data/pack_ammo_atom.json",
            "Ammo by Mig Atom",
        ),
        "gunze": (
            "gunze",
            parse_gunze_images,
            "source/gunze",
            "data/pack_gunze.json",
            "Gunze Sangyo",
        ),
        "gunze_sangyo": (
            "gunze",
            parse_gunze_images,
            "source/gunze",
            "data/pack_gunze.json",
            "Gunze Sangyo",
        ),
        "tamiya": (
            "tamiya",
            parse_tamiya_images,
            "source/tamiya",
            "data/pack_tamiya.json",
            "Tamiya",
        ),
        "ak": (
            "ak",
            parse_ak_images,
            "source/ak",
            "data/pack_ak.json",
            "AK Interactive",
        ),
        "ak_interactive": (
            "ak",
            parse_ak_images,
            "source/ak",
            "data/pack_ak.json",
            "AK Interactive",
        ),
    }

    if brand not in parsers:
        print(f"❌ Unknown brand: {brand}")
        available = [p for p in parsers.keys() if "_" in p or "-" in p]
        available = set(available)
        print(f"Available: {', '.join(available)}")
        sys.exit(1)

    print("\n🎨 Color Chart Parsing Pipeline")
    print("=" * 50)

    brand_id, parser_func, source_dir, output_file, brand_name = parsers[brand]
    if run_parser(brand_id, parser_func, source_dir, output_file, brand_name):
        print(f"\n✅ Pipeline complete for {brand}")
    else:
        print(f"\n❌ Pipeline failed for {brand}")
        sys.exit(1)


if __name__ == "__main__":
    parser = argparse.ArgumentParser(
        description="Parse color charts for scale modelling paints"
    )
    parser.add_argument(
        "brand",
        nargs="?",
        default=None,
        help=(
            "Brand to parse "
            "(mr_hobby, ammo, ammo-atom, gunze, tamiya, ak) - omit to run all"
        ),
    )

    args = parser.parse_args()

    if args.brand:
        run_single_parser(args.brand)
    else:
        run_all_parsers()
