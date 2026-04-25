#!/usr/bin/env python3
"""
Master pipeline to parse all color charts and prepare data for frontend.
Supports running all parsers or individual ones via CLI arguments.

Usage:
  python3 scripts/run_pipeline.py                    # Run all
  python3 scripts/run_pipeline.py mr_color           # Run Mr. Color only
    python3 scripts/run_pipeline.py ammo               # Run Ammo by Mig only
  python3 scripts/run_pipeline.py ammo-atom          # Run Ammo-Atom only
    python3 scripts/run_pipeline.py hobby_color             # Run Aqueous Hobby color only
    python3 scripts/run_pipeline.py tamiya             # Run Tamiya only
  python3 scripts/run_pipeline.py ak                 # Run AK Interactive only
"""

import json
import sys
import argparse
import time
from pathlib import Path
import importlib.util
from collections import Counter
from rich.console import Console
from rich.table import Table
from rich.panel import Panel

# Rich console for colored output
console = Console()

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
parse_mr_color = load_module(
    "parse_mr_color", SCRIPT_DIR / "source/mr_color/__main__.py"
)
parse_mr_color_images = parse_mr_color.process_mr_color_images

parse_ammo = load_module(
    "parse_ammo", SCRIPT_DIR / "source/ammo/acrylic_paint/__main__.py"
)
parse_ammo_images = parse_ammo.parse_ammo_images

parse_ammo_atom = load_module(
    "parse_ammo_atom", SCRIPT_DIR / "source/ammo/ammo-atom/__main__.py"
)
parse_ammo_atom_images = parse_ammo_atom.parse_ammo_atom_images

parse_ammo_figures = load_module(
    "parse_ammo_figures", SCRIPT_DIR / "source/ammo/figures/__main__.py"
)
parse_ammo_figures_colors = parse_ammo_figures.parse_ammo_figures

parse_hobby_color = load_module(
    "parse_hobby_color", SCRIPT_DIR / "source/mr_hobby/hobby-color/__main__.py"
)
parse_hobby_color_images = parse_hobby_color.parse_gunze_images

parse_tamiya = load_module("parse_tamiya", SCRIPT_DIR / "source/tamiya/__main__.py")
parse_tamiya_images = parse_tamiya.parse_tamiya_images

parse_ak = load_module("parse_ak", SCRIPT_DIR / "source/ak/__main__.py")
parse_ak_images = parse_ak.parse_ak_images

parse_rlm = load_module("parse_rlm", SCRIPT_DIR / "source/rlm/__main__.py")
parse_rlm_images = parse_rlm.parse_rlm_images

parse_humbrol = load_module("parse_humbrol", SCRIPT_DIR / "source/humbrol/__main__.py")
parse_humbrol_images = parse_humbrol.parse_humbrol_images

parse_vallejo_model_color = load_module(
    "parse_vallejo_model_color", SCRIPT_DIR / "source/valejo/model_color/__main__.py"
)
parse_vallejo_model_color_images = (
    parse_vallejo_model_color.parse_vallejo_model_color_images
)

parse_vallejo_model_air = load_module(
    "parse_vallejo_model_air", SCRIPT_DIR / "source/valejo/model_air/__main__.py"
)
parse_vallejo_model_air_images = parse_vallejo_model_air.parse_vallejo_model_air_images

parse_vallejo_game_color = load_module(
    "parse_vallejo_game_color", SCRIPT_DIR / "source/valejo/game_color/__main__.py"
)
parse_vallejo_game_color_images = (
    parse_vallejo_game_color.parse_vallejo_game_color_images
)

parse_vallejo_game_air = load_module(
    "parse_vallejo_game_air", SCRIPT_DIR / "source/valejo/game_air/__main__.py"
)
parse_vallejo_game_air_images = parse_vallejo_game_air.parse_vallejo_game_air_images

parse_vallejo_mecha_color = load_module(
    "parse_vallejo_mecha_color", SCRIPT_DIR / "source/valejo/mecha_color/__main__.py"
)
parse_vallejo_mecha_color_images = (
    parse_vallejo_mecha_color.parse_vallejo_mecha_color_images
)

parse_hataka = load_module("parse_hataka", SCRIPT_DIR / "source/hataka/__main__.py")
parse_hataka_images = parse_hataka.parse_hataka_images

parse_federal_standard = load_module(
    "parse_federal_standard", SCRIPT_DIR / "source/federal_standard/__main__.py"
)
parse_federal_standard_colors = parse_federal_standard.FederalStandardScraper

parse_ral = load_module("parse_ral", SCRIPT_DIR / "source/ral/__main__.py")
parse_ral_colors = parse_ral.RALScraper


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


def _run_federal_standard(output_path: Path):
    """Wrapper for Federal Standard scraper to match parser interface."""
    scraper = parse_federal_standard_colors()
    scraper.run(output_path)
    return scraper.colors


def _run_ral(output_path: Path):
    """Wrapper for RAL scraper to match parser interface."""
    scraper = parse_ral_colors()
    scraper.run(output_path)
    return scraper.colors


def get_parser_stats(brand_id):
    """Get statistics for a parsed brand."""
    output_file = f"data/pack_{brand_id}.json"
    if not Path(output_file).exists():
        return None

    try:
        with open(output_file, "r") as f:
            data = json.load(f)

        colors = data.get("colors", [])
        codes = [color.get("code") for color in colors]
        unique_codes = set(codes)
        code_counts = Counter(codes)
        duplicates = {code: count for code, count in code_counts.items() if count > 1}

        return {
            "total": len(colors),
            "unique": len(unique_codes),
            "duplicates": len(duplicates),
            "duplicate_details": duplicates,
        }
    except Exception:
        return None


def display_parser_stats(stats_data, timings=None):
    """Display parser statistics in a formatted table using rich."""
    if not stats_data:
        return

    if timings is None:
        timings = {}

    table = Table(title="📊 Parser Statistics Summary")
    table.add_column("Brand", style="cyan", no_wrap=True)
    table.add_column("Total Items", justify="right", style="green")
    table.add_column("Unique", justify="right", style="blue")
    table.add_column("Duplicates", justify="right", style="yellow")
    table.add_column("Time (s)", justify="right", style="magenta")

    total_items = 0
    total_unique = 0
    total_duplicates = 0
    total_time = sum(timings.values())

    for brand_id, stats in sorted(stats_data.items()):
        if stats:
            t = timings.get(brand_id)
            time_str = f"{t:.1f}" if t is not None else "-"
            table.add_row(
                brand_id,
                str(stats["total"]),
                str(stats["unique"]),
                str(stats["duplicates"]),
                time_str,
            )
            total_items += stats["total"]
            total_unique += stats["unique"]
            total_duplicates += stats["duplicates"]

    # Add totals row
    total_time_str = f"{total_time:.1f}" if timings else "-"
    table.add_row(
        "[bold]TOTAL[/bold]",
        f"[bold green]{total_items}[/bold green]",
        f"[bold blue]{total_unique}[/bold blue]",
        f"[bold yellow]{total_duplicates}[/bold yellow]",
        f"[bold magenta]{total_time_str}[/bold magenta]",
    )

    console.print(table)

    # Show duplicate details if any
    duplicates_found = {
        bid: stats["duplicate_details"]
        for bid, stats in stats_data.items()
        if stats and stats["duplicate_details"]
    }

    if duplicates_found:
        console.print("\n[yellow]⚠️  Duplicate codes detected:[/yellow]")
        for brand_id, duplicates in sorted(duplicates_found.items()):
            if duplicates:
                dup_str = ", ".join(
                    [
                        f"{code}×{count}"
                        for code, count in sorted(
                            duplicates.items(), key=lambda x: -x[1]
                        )[:3]
                    ]
                )
                if len(duplicates) > 3:
                    dup_str += f", +{len(duplicates)-3} more"
                console.print(f"  • [yellow]{brand_id}[/yellow]: {dup_str}")


def run_parser(brand_id, parser_func, source_dir, output_file, brand_name):
    """Run a single parser and format results. Returns (success, elapsed_seconds)."""
    console.print(f"[cyan]\n{brand_id.upper()}[/cyan]: {brand_name}...")
    t_start = time.monotonic()
    try:
        colors = parser_func(Path(source_dir), Path(output_file))
        if colors:
            # Format for frontend
            formatted = format_colors(colors, brand_name, brand_id)

            # Save results
            Path(output_file).parent.mkdir(parents=True, exist_ok=True)
            with open(output_file, "w", encoding="utf-8") as f:
                json.dump(formatted, f, indent=2, ensure_ascii=False)

            elapsed = time.monotonic() - t_start
            console.print(
                f"   [green]✅ {len(colors)} colors extracted[/green] [dim]({elapsed:.1f}s)[/dim]"
            )
            return True, elapsed
        else:
            elapsed = time.monotonic() - t_start
            console.print("   [yellow]⚠️  No colors extracted[/yellow]")
            return False, elapsed
    except Exception as err:
        elapsed = time.monotonic() - t_start
        console.print(f"   [red]❌ Error: {err}[/red]")
        import traceback

        traceback.print_exc()
        return False, elapsed


def run_all_parsers():
    """Run all parser scripts and organize results."""
    results_dir = Path("data/")
    results_dir.mkdir(parents=True, exist_ok=True)

    console.print("\n[cyan]🎨 Color Chart Parsing Pipeline[/cyan]")
    console.print("[cyan]" + "=" * 50 + "[/cyan]")

    # Define all parsers
    parsers = [
        (
            "federal_standard",
            lambda p, o: _run_federal_standard(Path(o)),
            "source/federal_standard",
            "data/pack_federal_standard.json",
            "Federal Standard",
        ),
        (
            "ral",
            lambda p, o: _run_ral(Path(o)),
            "source/ral",
            "data/pack_ral.json",
            "RAL",
        ),
        (
            "ammo",
            parse_ammo_images,
            "source/ammo/acrylic_paint",
            "data/pack_ammo.json",
            "Ammo by Mig",
        ),
        (
            "ammo_atom",
            parse_ammo_atom_images,
            "source/ammo/ammo-atom",
            "data/pack_ammo_atom.json",
            "Ammo by Mig Atom",
        ),
        (
            "ammo_figures",
            parse_ammo_figures_colors,
            "source/ammo/figures",
            "data/pack_ammo_figures.json",
            "Ammo by Mig Figures",
        ),
        (
            "mr_color",
            parse_mr_color_images,
            "source/mr_color",
            "data/pack_mr_color.json",
            "Mr. Color",
        ),
        (
            "hobby_color",
            parse_hobby_color_images,
            "source/mr_hobby/hobby-color",
            "data/pack_hobby_color.json",
            "Aqueous Hobby color",
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
        (
            "rlm",
            parse_rlm_images,
            "source/rlm",
            "data/pack_rlm.json",
            "RLM",
        ),
        (
            "humbrol",
            parse_humbrol_images,
            "source/humbrol",
            "data/pack_humbrol.json",
            "Humbrol",
        ),
        (
            "vallejo_model_color",
            parse_vallejo_model_color_images,
            "source/valejo/model_color",
            "data/pack_vallejo_model_color.json",
            "Vallejo Model Color",
        ),
        (
            "vallejo_model_air",
            parse_vallejo_model_air_images,
            "source/valejo/model_air",
            "data/pack_vallejo_model_air.json",
            "Vallejo Model Air",
        ),
        (
            "vallejo_game_color",
            parse_vallejo_game_color_images,
            "source/valejo/game_color",
            "data/pack_vallejo_game_color.json",
            "Vallejo Game Color",
        ),
        (
            "vallejo_game_air",
            parse_vallejo_game_air_images,
            "source/valejo/game_air",
            "data/pack_vallejo_game_air.json",
            "Vallejo Game Air",
        ),
        (
            "vallejo_mecha_color",
            parse_vallejo_mecha_color_images,
            "source/valejo/mecha_color",
            "data/pack_vallejo_mecha_color.json",
            "Vallejo Mecha Color",
        ),
        (
            "hataka",
            parse_hataka_images,
            "source/hataka",
            "data/pack_hataka.json",
            "Hataka",
        ),
    ]

    # Run selected or all parsers
    success_count = 0
    timings = {}
    pipeline_start = time.monotonic()
    for brand_id, parser_func, source_dir, output_file, brand_name in parsers:
        success, elapsed = run_parser(
            brand_id, parser_func, source_dir, output_file, brand_name
        )
        timings[brand_id] = elapsed
        if success:
            success_count += 1

    total_elapsed = time.monotonic() - pipeline_start
    console.print("\n[cyan]" + "=" * 50 + "[/cyan]")
    total = len(parsers)
    console.print(
        f"[green]✅ Pipeline complete! ({success_count}/{total} parsers succeeded)[/green]"
    )
    console.print(f"[blue]⏱  Total time: {total_elapsed:.1f}s[/blue]")
    console.print("[blue]📁 Results saved to data/[/blue]\n")

    # Collect and display stats
    stats_data = {}
    for brand_id, _, _, _, _ in parsers:
        stats_data[brand_id] = get_parser_stats(brand_id)

    display_parser_stats(stats_data, timings)


def run_single_parser(brand):
    """Run a single parser by brand name."""
    parsers = {
        "mr_color": (
            "mr_color",
            parse_mr_color_images,
            "source/mr_color",
            "data/pack_mr_color.json",
            "Mr. Color",
        ),
        "mr-color": (
            "mr_color",
            parse_mr_color_images,
            "source/mr_color",
            "data/pack_mr_color.json",
            "Mr. Color",
        ),
        "ammo": (
            "ammo",
            parse_ammo_images,
            "source/ammo/acrylic_paint",
            "data/pack_ammo.json",
            "Ammo by Mig",
        ),
        "ammo-by-mig": (
            "ammo",
            parse_ammo_images,
            "source/ammo/acrylic_paint",
            "data/pack_ammo.json",
            "Ammo by Mig",
        ),
        "ammo-atom": (
            "ammo_atom",
            parse_ammo_atom_images,
            "source/ammo/ammo-atom",
            "data/pack_ammo_atom.json",
            "Ammo by Mig Atom",
        ),
        "ammo_atom": (
            "ammo_atom",
            parse_ammo_atom_images,
            "source/ammo/ammo-atom",
            "data/pack_ammo_atom.json",
            "Ammo by Mig Atom",
        ),
        "ammo_figures": (
            "ammo_figures",
            parse_ammo_figures_colors,
            "source/ammo/figures",
            "data/pack_ammo_figures.json",
            "Ammo by Mig Figures",
        ),
        "ammo-figures": (
            "ammo_figures",
            parse_ammo_figures_colors,
            "source/ammo/figures",
            "data/pack_ammo_figures.json",
            "Ammo by Mig Figures",
        ),
        "hobby_color": (
            "hobby_color",
            parse_hobby_color_images,
            "source/mr_hobby/hobby-color",
            "data/pack_hobby_color.json",
            "Aqueous Hobby color",
        ),
        "hobby-color": (
            "hobby_color",
            parse_hobby_color_images,
            "source/mr_hobby/hobby-color",
            "data/pack_hobby_color.json",
            "Aqueous Hobby color",
        ),
        "aqueous_hobby_color": (
            "hobby_color",
            parse_hobby_color_images,
            "source/mr_hobby/hobby-color",
            "data/pack_hobby_color.json",
            "Aqueous Hobby color",
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
        "rlm": (
            "rlm",
            parse_rlm_images,
            "source/rlm",
            "data/pack_rlm.json",
            "RLM",
        ),
        "humbrol": (
            "humbrol",
            parse_humbrol_images,
            "source/humbrol",
            "data/pack_humbrol.json",
            "Humbrol",
        ),
        "vallejo_model_color": (
            "vallejo_model_color",
            parse_vallejo_model_color_images,
            "source/valejo/model_color",
            "data/pack_vallejo_model_color.json",
            "Vallejo Model Color",
        ),
        "vallejo_model_air": (
            "vallejo_model_air",
            parse_vallejo_model_air_images,
            "source/valejo/model_air",
            "data/pack_vallejo_model_air.json",
            "Vallejo Model Air",
        ),
        "vallejo_game_color": (
            "vallejo_game_color",
            parse_vallejo_game_color_images,
            "source/valejo/game_color",
            "data/pack_vallejo_game_color.json",
            "Vallejo Game Color",
        ),
        "vallejo_game_air": (
            "vallejo_game_air",
            parse_vallejo_game_air_images,
            "source/valejo/game_air",
            "data/pack_vallejo_game_air.json",
            "Vallejo Game Air",
        ),
        "vallejo_mecha_color": (
            "vallejo_mecha_color",
            parse_vallejo_mecha_color_images,
            "source/valejo/mecha_color",
            "data/pack_vallejo_mecha_color.json",
            "Vallejo Mecha Color",
        ),
        # Legacy alias
        "vallejo": (
            "vallejo_model_color",
            parse_vallejo_model_color_images,
            "source/valejo/model_color",
            "data/pack_vallejo_model_color.json",
            "Vallejo Model Color",
        ),
        "hataka": (
            "hataka",
            parse_hataka_images,
            "source/hataka",
            "data/pack_hataka.json",
            "Hataka",
        ),
        "federal_standard": (
            "federal_standard",
            lambda p, o: _run_federal_standard(Path(o)),
            "source/federal_standard",
            "data/pack_federal_standard.json",
            "Federal Standard",
        ),
        "federal-standard": (
            "federal_standard",
            lambda p, o: _run_federal_standard(Path(o)),
            "source/federal_standard",
            "data/pack_federal_standard.json",
            "Federal Standard",
        ),
        "ral": (
            "ral",
            lambda p, o: _run_ral(Path(o)),
            "source/ral",
            "data/pack_ral.json",
            "RAL",
        ),
        "ral-classic": (
            "ral",
            lambda p, o: _run_ral(Path(o)),
            "source/ral",
            "data/pack_ral.json",
            "RAL",
        ),
    }

    if brand not in parsers:
        console.print(f"[red]❌ Unknown brand: {brand}[/red]")
        available = [p for p in parsers.keys() if "_" in p or "-" in p]
        available = set(available)
        console.print(f"Available: {', '.join(available)}")
        sys.exit(1)

    console.print("\n[cyan]🎨 Color Chart Parsing Pipeline[/cyan]")
    console.print("[cyan]" + "=" * 50 + "[/cyan]")

    brand_id, parser_func, source_dir, output_file, brand_name = parsers[brand]
    success, elapsed = run_parser(
        brand_id, parser_func, source_dir, output_file, brand_name
    )
    if success:
        console.print(f"\n[cyan]" + "=" * 50 + "[/cyan]")
        console.print(f"[green]✅ Pipeline complete for {brand}[/green]")
        console.print(f"[blue]⏱  Time: {elapsed:.1f}s[/blue]\n")

        # Display stats for this brand
        stats = get_parser_stats(brand_id)
        if stats:
            stats_data = {brand_id: stats}
            display_parser_stats(stats_data, {brand_id: elapsed})
    else:
        console.print(f"\n[red]❌ Pipeline failed for {brand}[/red]")
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
            "(mr_color, ammo, ammo-atom, gunze, tamiya, ak, rlm, humbrol, vallejo) - omit to run all"
        ),
    )

    args = parser.parse_args()

    if args.brand:
        run_single_parser(args.brand)
    else:
        run_all_parsers()
