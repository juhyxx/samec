#!/usr/bin/env python3
"""
Quick checker for parser data statistics.

Usage:
    python scripts/check_parser_stats.py          # Check all parsers
    python scripts/check_parser_stats.py ak       # Check specific parser
"""

import json
import sys
from pathlib import Path
from collections import Counter
from rich.console import Console
from rich.table import Table

console = Console()


def check_parser(brand_key):
    """Check statistics for a single parser."""
    data_dir = Path(__file__).parent.parent / "data"

    parsers = {
        "ak": "pack_ak.json",
        "ammo": "pack_ammo.json",
        "ammo_atom": "pack_ammo_atom.json",
        "hobby_color": "pack_hobby_color.json",
        "humbrol": "pack_humbrol.json",
        "mr_hobby": "pack_mr_hobby.json",
        "ral": "pack_ral.json",
        "rlm": "pack_rlm.json",
        "tamiya": "pack_tamiya.json",
        "vallejo": "pack_vallejo.json",
        "federal_standard": "pack_federal_standard.json",
    }

    if brand_key not in parsers:
        console.print(f"[red]Unknown parser: {brand_key}[/red]")
        console.print(f"[yellow]Available: {', '.join(parsers.keys())}[/yellow]")
        return False

    file_path = data_dir / parsers[brand_key]
    if not file_path.exists():
        console.print(f"[red]Data file not found: {file_path}[/red]")
        return False

    with open(file_path, "r") as f:
        data = json.load(f)

    colors = data.get("colors", [])
    codes = [color.get("code") for color in colors]
    unique_codes = set(codes)
    code_counts = Counter(codes)
    duplicates = {code: count for code, count in code_counts.items() if count > 1}

    console.print(f"\n[cyan]{brand_key.upper()} Parser Statistics[/cyan]")
    console.print("[cyan]" + "-" * 50 + "[/cyan]")
    console.print(f"[green]Total items parsed:    {len(colors):>6}[/green]")
    console.print(f"[blue]Unique items (by code):{len(unique_codes):>6}[/blue]")
    console.print(f"[yellow]Duplicate codes:       {len(duplicates):>6}[/yellow]")

    if duplicates:
        console.print(f"\n[yellow]Duplicate codes:[/yellow]")
        for code, count in sorted(duplicates.items(), key=lambda x: -x[1]):
            console.print(f"  [yellow]•[/yellow] {code}: appears {count} times")

    return True


def check_all_parsers():
    """Check all parsers and display summary."""
    data_dir = Path(__file__).parent.parent / "data"

    parsers = {
        "ak": "pack_ak.json",
        "ammo": "pack_ammo.json",
        "ammo_atom": "pack_ammo_atom.json",
        "hobby_color": "pack_hobby_color.json",
        "humbrol": "pack_humbrol.json",
        "mr_hobby": "pack_mr_hobby.json",
        "ral": "pack_ral.json",
        "rlm": "pack_rlm.json",
        "tamiya": "pack_tamiya.json",
        "vallejo": "pack_vallejo.json",
        "federal_standard": "pack_federal_standard.json",
    }

    summary = {}
    total_items = 0
    total_unique = 0
    total_duplicates = 0

    for brand_key, filename in sorted(parsers.items()):
        file_path = data_dir / filename
        if not file_path.exists():
            continue

        with open(file_path, "r") as f:
            data = json.load(f)

        colors = data.get("colors", [])
        codes = [color.get("code") for color in colors]
        unique_codes = set(codes)
        code_counts = Counter(codes)
        duplicates = sum(1 for count in code_counts.values() if count > 1)

        summary[brand_key] = {
            "total": len(colors),
            "unique": len(unique_codes),
            "duplicates": duplicates,
        }

        total_items += len(colors)
        total_unique += len(unique_codes)
        total_duplicates += duplicates

    # Create and display summary table
    table = Table(title="📊 Parser Summary - All Brands")
    table.add_column("Brand", style="cyan", no_wrap=True)
    table.add_column("Total Items", justify="right", style="green")
    table.add_column("Unique", justify="right", style="blue")
    table.add_column("Duplicates", justify="right", style="yellow")

    for brand, stats in sorted(summary.items()):
        table.add_row(
            brand,
            str(stats["total"]),
            str(stats["unique"]),
            str(stats["duplicates"]),
        )

    # Add totals row
    table.add_row(
        "[bold]TOTAL[/bold]",
        f"[bold green]{total_items}[/bold green]",
        f"[bold blue]{total_unique}[/bold blue]",
        f"[bold yellow]{total_duplicates}[/bold yellow]",
    )

    console.print(table)


if __name__ == "__main__":
    if len(sys.argv) > 1:
        check_parser(sys.argv[1])
    else:
        check_all_parsers()
