#!/usr/bin/env python3
"""
Generate a Mermaid graph visualizing color equivalency relationships
across all brands.

Usage:
    uv run python scripts/visualize_equivalents.py
    uv run python scripts/visualize_equivalents.py --brand hataka
    uv run python scripts/visualize_equivalents.py --brand hataka --limit 30
    uv run python scripts/visualize_equivalents.py --from-equivalents

Output:
    data/equivalents_graph.mmd  (or --output <path>)
"""
from __future__ import annotations

import argparse
import json
import re
from pathlib import Path

DATA_DIR = Path("data")

PACK_FILES = [
    DATA_DIR / "pack_ak.json",
    DATA_DIR / "pack_ammo.json",
    DATA_DIR / "pack_ammo_atom.json",
    DATA_DIR / "pack_federal_standard.json",
    DATA_DIR / "pack_gunze.json",
    DATA_DIR / "pack_hataka.json",
    DATA_DIR / "pack_hobby_color.json",
    DATA_DIR / "pack_humbrol.json",
    DATA_DIR / "pack_mr_color.json",
    DATA_DIR / "pack_ral.json",
    DATA_DIR / "pack_rlm.json",
    DATA_DIR / "pack_tamiya.json",
    DATA_DIR / "pack_vallejo.json",
]

# Brand colors for styling nodes (hex without #)
BRAND_STYLE: dict[str, tuple[str, str]] = {
    # brand_id -> (fill, text-color)
    "ak": ("d32f2f", "ffffff"),
    "ammo": ("e65100", "ffffff"),
    "ammo_atom": ("f9a825", "000000"),
    "federal_standard": ("1565c0", "ffffff"),
    "gunze": ("6a1b9a", "ffffff"),
    "hataka": ("e31e24", "ffffff"),
    "hobby_color": ("4527a0", "ffffff"),
    "humbrol": ("00695c", "ffffff"),
    "mr_color": ("283593", "ffffff"),
    "ral": ("558b2f", "ffffff"),
    "rlm": ("4e342e", "ffffff"),
    "tamiya": ("ad1457", "ffffff"),
    "vallejo": ("00838f", "ffffff"),
}


def _node_id(brand_id: str, code: str) -> str:
    """Return a safe Mermaid node identifier."""
    safe = re.sub(r"[^a-zA-Z0-9]", "_", f"{brand_id}__{code}")
    return safe


def _node_label(brand_id: str, code: str) -> str:
    return f"{brand_id}\\n{code}"


def _style_class(brand_id: str) -> str:
    return f"cls_{re.sub(r'[^a-zA-Z0-9]', '_', brand_id)}"


def load_pack(path: Path) -> dict:
    if not path.exists():
        return {}
    return json.loads(path.read_text(encoding="utf-8"))


def build_edges_from_packs(
    filter_brand: str | None = None,
    limit: int | None = None,
) -> tuple[set, list[tuple]]:
    """
    Walk every pack file; for each color that has equivalents emit
    (source_brand, source_code, target_brand, target_code) edges.
    """
    nodes: set[tuple[str, str]] = set()  # (brand_id, code)
    edges: list[tuple[str, str, str, str]] = []
    seen_edges: set[frozenset] = set()

    for pack_path in PACK_FILES:
        pack = load_pack(pack_path)
        if not pack:
            continue

        brand_id: str = pack.get("brand_id", pack_path.stem.replace("pack_", ""))
        colors: list[dict] = pack.get("colors", [])

        if filter_brand and brand_id != filter_brand:
            # Still include colors that are *targets* from this brand — handled below
            continue

        for color in colors:
            code = color.get("code")
            if not code:
                continue
            equivalents = color.get("equivalents") or []
            if not equivalents:
                continue

            src = (brand_id, code)
            nodes.add(src)
            for eq in equivalents:
                tgt_brand = eq.get("brand_id") or _brand_name_to_id(eq.get("brand", ""))
                tgt_code = eq.get("code")
                if not tgt_brand or not tgt_code:
                    continue
                tgt = (tgt_brand, tgt_code)
                nodes.add(tgt)
                edge_key = frozenset([src, tgt])
                if edge_key not in seen_edges:
                    seen_edges.add(edge_key)
                    edges.append((brand_id, code, tgt_brand, tgt_code))

            if limit and len(edges) >= limit:
                return nodes, edges

    return nodes, edges


def build_edges_from_equivalents_json(
    filter_brand: str | None = None,
    limit: int | None = None,
) -> tuple[set, list[tuple]]:
    """
    Use data/equivalents.json which has the merged cross-brand mapping.
    Structure: { brand_id: { code: [ {brand, code}, ... ] } }
    """
    eq_path = DATA_DIR / "equivalents.json"
    if not eq_path.exists():
        print(f"⚠️  {eq_path} not found — run generate_equivalents.py first")
        return set(), []

    data: dict = json.loads(eq_path.read_text(encoding="utf-8"))

    nodes: set[tuple[str, str]] = set()
    edges: list[tuple[str, str, str, str]] = []
    seen_edges: set[frozenset] = set()

    for brand_id, color_map in data.items():
        if filter_brand and brand_id != filter_brand:
            continue
        for code, eq_list in color_map.items():
            src = (brand_id, code)
            nodes.add(src)
            for eq in eq_list:
                tgt_brand = eq.get("brand", "")
                tgt_code = eq.get("code", "")
                if not tgt_brand or not tgt_code:
                    continue
                tgt = (tgt_brand, tgt_code)
                nodes.add(tgt)
                edge_key = frozenset([src, tgt])
                if edge_key not in seen_edges:
                    seen_edges.add(edge_key)
                    edges.append((brand_id, code, tgt_brand, tgt_code))
            if limit and len(edges) >= limit:
                return nodes, edges

    return nodes, edges


# ------------------------------------------------------------------
# Brand name → brand_id normalisation (for inline equivalents that
# store the human-readable brand name rather than the id)
# ------------------------------------------------------------------
_BRAND_NAME_MAP = {
    "ak interactive": "ak",
    "ak": "ak",
    "ammo by mig": "ammo",
    "ammo": "ammo",
    "ammo by mig atom": "ammo_atom",
    "ammo atom": "ammo_atom",
    "ammo_atom": "ammo_atom",
    "federal standard": "federal_standard",
    "gunze sangyo": "gunze",
    "gunze / mr. hobby": "gunze",
    "gunze": "gunze",
    "hataka": "hataka",
    "hobby color": "hobby_color",
    "humbrol": "humbrol",
    "mr. hobby": "mr_color",
    "mr hobby": "mr_color",
    "ral": "ral",
    "rlm": "rlm",
    "tamiya": "tamiya",
    "testors": "testors",
    "vallejo": "vallejo",
    "vallejo air": "vallejo",
    "xtracolor": "xtracolor",
    "bs": "bs",
    "ana": "ana",
}


def _brand_name_to_id(name: str) -> str:
    return _BRAND_NAME_MAP.get(
        name.lower().strip(), re.sub(r"[^a-z0-9]", "_", name.lower().strip())
    )


def render_mermaid(
    nodes: set[tuple[str, str]],
    edges: list[tuple[str, str, str, str]],
) -> str:
    max_edges = max(len(edges) + 100, 500)
    lines: list[str] = [
        f'%%{{init: {{"maxEdges": {max_edges}}} }}%%',
        "graph LR",
    ]

    # Collect which brand_ids are actually used
    used_brands: set[str] = {n[0] for n in nodes}

    # Emit classDef for each used brand
    for brand_id in sorted(used_brands):
        fill, color = BRAND_STYLE.get(brand_id, ("cccccc", "000000"))
        cls = _style_class(brand_id)
        lines.append(
            f"    classDef {cls} fill:#{fill},color:#{color},stroke:#333,stroke-width:1px"
        )

    lines.append("")

    # Emit node definitions with labels
    for brand_id, code in sorted(nodes):
        nid = _node_id(brand_id, code)
        label = _node_label(brand_id, code)
        cls = _style_class(brand_id)
        lines.append(f'    {nid}["{label}"]:::{cls}')

    lines.append("")

    # Emit edges
    for src_brand, src_code, tgt_brand, tgt_code in edges:
        src_nid = _node_id(src_brand, src_code)
        tgt_nid = _node_id(tgt_brand, tgt_code)
        lines.append(f"    {src_nid} --- {tgt_nid}")

    return "\n".join(lines) + "\n"


def main() -> None:
    parser = argparse.ArgumentParser(
        description="Generate a Mermaid equivalency graph from color pack data."
    )
    parser.add_argument(
        "--brand",
        metavar="BRAND_ID",
        help="Only show equivalents originating from this brand (e.g. hataka)",
    )
    parser.add_argument(
        "--limit",
        type=int,
        default=None,
        metavar="N",
        help="Cap the number of edges (useful for large datasets)",
    )
    parser.add_argument(
        "--from-equivalents",
        action="store_true",
        help="Source data from data/equivalents.json instead of individual pack files",
    )
    parser.add_argument(
        "--output",
        default=str(DATA_DIR / "equivalents_graph.mmd"),
        metavar="FILE",
        help="Output .mmd file path (default: data/equivalents_graph.mmd)",
    )
    args = parser.parse_args()

    if args.from_equivalents:
        nodes, edges = build_edges_from_equivalents_json(
            filter_brand=args.brand, limit=args.limit
        )
    else:
        nodes, edges = build_edges_from_packs(filter_brand=args.brand, limit=args.limit)

    if not edges:
        print("No edges found — check your --brand name or run the pipeline first.")
        return

    mmd = render_mermaid(nodes, edges)

    out = Path(args.output)
    out.parent.mkdir(parents=True, exist_ok=True)
    out.write_text(mmd, encoding="utf-8")

    print(f"✅ Wrote {len(nodes)} nodes, {len(edges)} edges → {out}")
    print()
    print("Render options:")
    print("  • Paste into https://mermaid.live/")
    print("  • VS Code: install 'Markdown Preview Mermaid Support' extension")
    print(
        "  • CLI:     npx -p @mermaid-js/mermaid-cli mmdc -i data/equivalents_graph.mmd -o data/equivalents_graph.svg"
    )


if __name__ == "__main__":
    main()
