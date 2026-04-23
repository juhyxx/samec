#!/usr/bin/env python3
"""
Generate color equivalents by matching hex values across brands.
Compares colors from all packs and creates cross-references.
"""

import json
from pathlib import Path
from collections import defaultdict
import colorsys


def hex_to_rgb(hex_color):
    """Convert hex color to RGB tuple."""
    hex_color = hex_color.lstrip("#")
    if len(hex_color) != 6:
        return None
    try:
        return tuple(int(hex_color[i : i + 2], 16) for i in (0, 2, 4))
    except ValueError:
        return None


def color_distance(rgb1, rgb2):
    """Calculate Euclidean distance between two RGB colors."""
    if rgb1 is None or rgb2 is None:
        return float("inf")
    return sum((a - b) ** 2 for a, b in zip(rgb1, rgb2)) ** 0.5


def find_closest_match(hex_color, candidates, max_distance=50):
    """Find closest matching color from candidates.

    Args:
        hex_color: Hex color to match
        candidates: List of (brand_id, code, hex) tuples
        max_distance: Maximum RGB distance to consider a match

    Returns:
        List of (brand_id, code) tuples for matching colors
    """
    rgb = hex_to_rgb(hex_color)
    if rgb is None:
        return []

    distances = []
    for brand_id, code, candidate_hex in candidates:
        cand_rgb = hex_to_rgb(candidate_hex)
        if cand_rgb is None:
            continue
        dist = color_distance(rgb, cand_rgb)
        if dist <= max_distance:
            distances.append((dist, brand_id, code))

    # Sort by distance and return top matches
    distances.sort(key=lambda x: x[0])
    return [(brand, code) for _, brand, code in distances[:3]]  # Return top 3 matches


def load_all_packs():
    """Load all color packs from data directory."""
    packs = {}
    data_dir = Path("data")

    for pack_file in sorted(data_dir.glob("pack_*.json")):
        try:
            with open(pack_file, encoding="utf-8") as f:
                data = json.load(f)
                brand_id = data.get("brand_id", pack_file.stem.replace("pack_", ""))
                packs[brand_id] = data.get("colors", [])
        except Exception as e:
            print(f"Warning: Could not load {pack_file}: {e}")

    return packs


def generate_equivalents(packs, max_distance=50):
    """Generate equivalents mapping by matching hex colors.

    Args:
        packs: Dict of brand_id -> colors list
        max_distance: Maximum RGB distance for a match

    Returns:
        Dict with brand_id -> code -> equivalents[] mapping
    """
    equivalents = defaultdict(lambda: defaultdict(list))

    # Build candidate list: (brand_id, code, hex)
    candidates = []
    for brand_id, colors in packs.items():
        for color in colors:
            hex_val = color.get("hex", "")
            if hex_val:
                candidates.append((brand_id, color.get("code"), hex_val))

    # Reference systems — these have no manufacturer-stated equivalents.
    # They appear only as *targets* in paint brands' equivalents, never as sources.
    REFERENCE_ONLY_BRANDS = {'federal_standard', 'ral', 'rlm'}

    # For each color in each pack, find matches in other brands
    for source_brand_id, colors in packs.items():
        if source_brand_id in REFERENCE_ONLY_BRANDS:
            continue  # FS/RAL/RLM don't have direct equivalents from a manufacturer

        for color in colors:
            code = color.get("code")
            hex_val = color.get("hex", "")

            if not hex_val or not code:
                continue

            # Find candidates from OTHER brands only
            other_candidates = [
                (bid, c, h) for bid, c, h in candidates if bid != source_brand_id
            ]

            # Find matches
            matches = find_closest_match(hex_val, other_candidates, max_distance)

            if matches:
                equivalents[source_brand_id][code] = [
                    {"brand": brand, "code": match_code}
                    for brand, match_code in matches
                ]

    return dict(equivalents)


def main():
    """Main entry point."""
    print("🎨 Generating color equivalents...")

    # Load all packs
    packs = load_all_packs()
    print(f"✅ Loaded {len(packs)} color packs")

    # Generate equivalents
    print("📊 Matching colors across brands...")
    equivalents = generate_equivalents(packs, max_distance=50)

    # Save equivalents
    output_file = Path("data/equivalents.json")
    with open(output_file, "w", encoding="utf-8") as f:
        json.dump(equivalents, f, indent=2, ensure_ascii=False)

    print(f"✅ Saved equivalents to {output_file}")

    # Print statistics
    total_equiv = sum(len(codes) for codes in equivalents.values())
    print(f"\n📈 Statistics:")
    print(f"   • Total brands with equivalents: {len(equivalents)}")
    print(f"   • Total color equivalences generated: {total_equiv}")

    # Show mr_color stats if available
    if "mr_color" in equivalents:
        mr_color_equivs = len(equivalents["mr_color"])
        mr_color_with_equivs = sum(
            1 for codes in equivalents["mr_color"].values() if codes
        )
        print(f"\n   Mr. Color:")
        print(f"     • Colors with equivalents: {mr_color_with_equivs}")
        print(
            f"     • Total equivalences: {sum(len(e) for e in equivalents['mr_color'].values())}"
        )

        # Show Federal Standard matches for Mr. Color
        if "federal_standard" in equivalents.get("mr_color", {}):
            print(
                f"     • Federal Standard matches: {len(equivalents['mr_color']['federal_standard'])}"
            )


if __name__ == "__main__":
    main()
