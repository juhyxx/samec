#!/usr/bin/env python3
"""
Merge equivalents from equivalents.json into existing color pack files.
"""

import json
from pathlib import Path


def merge_equivalents_into_packs():
    """Load equivalents and merge them into existing pack files."""
    equiv_file = Path("data/equivalents.json")

    if not equiv_file.exists():
        print("❌ equivalents.json not found!")
        return
    # Reference systems have no manufacturer-stated equivalents — skip them entirely.
    REFERENCE_ONLY_BRANDS = {'federal_standard', 'ral', 'rlm'}
    # Load equivalents
    with open(equiv_file, encoding="utf-8") as f:
        equivalents_data = json.load(f)

    print(f"✅ Loaded equivalents from {equiv_file}")

    # Process each pack file
    data_dir = Path("data")
    merged_count = 0

    for pack_file in sorted(data_dir.glob("pack_*.json")):
        brand_id = pack_file.stem.replace("pack_", "")

        # Skip reference-only systems — they never have direct equivalents
        if brand_id in REFERENCE_ONLY_BRANDS:
            continue

        # Check if this brand has equivalents
        if brand_id not in equivalents_data:
            continue

        try:
            # Load pack
            with open(pack_file, encoding="utf-8") as f:
                pack_data = json.load(f)

            # Get equivalents for this brand
            brand_equivs = equivalents_data[brand_id]

            # Merge equivalents into colors
            updated = 0
            for color in pack_data.get("colors", []):
                code = color.get("code")
                if code and code in brand_equivs:
                    color["equivalents"] = brand_equivs[code]
                    updated += 1

            # Save updated pack
            with open(pack_file, "w", encoding="utf-8") as f:
                json.dump(pack_data, f, indent=2, ensure_ascii=False)

            if updated > 0:
                print(f"  ✅ {brand_id}: {updated} colors updated with equivalents")
                merged_count += updated

        except Exception as e:
            print(f"  ❌ Error processing {pack_file}: {e}")

    print(f"\n✅ Total colors merged: {merged_count}")


if __name__ == "__main__":
    merge_equivalents_into_packs()
