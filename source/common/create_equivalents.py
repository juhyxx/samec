#!/usr/bin/env python3
"""
Create Gunze ↔ Ammo equivalents mapping based on color hex similarity.

Updates:
1. pack_gunze.json with Ammo equivalents (in-place in colors array)
2. ammo_rows.json with Gunze equivalents
"""
import json
from pathlib import Path
from math import sqrt


def hex_distance(hex1, hex2):
    """Calculate RGB Euclidean distance between two hex colors."""
    try:
        # Handle optional '#' prefix
        h1 = hex1.lstrip("#")
        h2 = hex2.lstrip("#")
        r1, g1, b1 = int(h1[0:2], 16), int(h1[2:4], 16), int(h1[4:6], 16)
        r2, g2, b2 = int(h2[0:2], 16), int(h2[2:4], 16), int(h2[4:6], 16)
        return sqrt((r1 - r2) ** 2 + (g1 - g2) ** 2 + (b1 - b2) ** 2)
    except:
        return float("inf")


def find_similar_colors(hex_color, all_colors, max_distance=50):
    """Find colors within distance threshold. Returns list of (code, hex, distance) tuples."""
    similar = []
    for code, hex_val in all_colors:
        dist = hex_distance(hex_color, hex_val)
        if 0 < dist <= max_distance:  # Exclude exact matches (distance=0)
            similar.append((code, hex_val, dist))
    similar.sort(key=lambda x: x[2])
    return similar


# Load data files
ammo_rows = json.loads(Path("data/ammo_rows.json").read_text())
pack_gunze = json.loads(Path("data/pack_gunze.json").read_text())

# Build color lists
ammo_colors = [(r["reference"], r["hex"]) for r in ammo_rows if r.get("hex")]
gunze_colors = [(c["code"], c["hex"]) for c in pack_gunze["colors"] if c.get("hex")]

print(f"Ammo colors: {len(ammo_colors)}")
print(f"Gunze colors: {len(gunze_colors)}")

# Find mappings: Gunze→Ammo and Ammo→Gunze
gunze_to_ammo = {}
ammo_to_gunze = {}

for gunze_code, gunze_hex in gunze_colors:
    similar_ammo = find_similar_colors(gunze_hex, ammo_colors, max_distance=50)
    if similar_ammo:
        gunze_to_ammo[gunze_code] = similar_ammo[:2]  # Keep top 2

for ammo_code, ammo_hex in ammo_colors:
    similar_gunze = find_similar_colors(ammo_hex, gunze_colors, max_distance=50)
    if similar_gunze:
        ammo_to_gunze[ammo_code] = similar_gunze[:2]

print(f"\nGunze→Ammo matches: {len(gunze_to_ammo)}")
print(f"Ammo→Gunze matches: {len(ammo_to_gunze)}")

# Update pack_gunze.json: add Ammo equivalents to each Gunze color
updated_gunze_count = 0
for color in pack_gunze["colors"]:
    code = color["code"]
    if code in gunze_to_ammo:
        color["equivalents"] = [
            {"brand": "Ammo by Mig", "code": ammo_code}
            for ammo_code, _, dist in gunze_to_ammo[code][:2]
        ]
        updated_gunze_count += 1

# Update ammo_rows.json: add Gunze equivalents to each Ammo row
updated_ammo_count = 0
for row in ammo_rows:
    code = row["reference"]
    if code in ammo_to_gunze:
        gunze_equivs = [
            {"brand": "Gunze Sangyo", "code": gunze_code}
            for gunze_code, _, dist in ammo_to_gunze[code][:2]
        ]
        if "equivalents" not in row:
            row["equivalents"] = []
        row["equivalents"].extend(gunze_equivs)
        updated_ammo_count += 1

print(f"\nUpdated {updated_gunze_count} Gunze entries")
print(f"Updated {updated_ammo_count} Ammo entries")

# Save files
Path("data/pack_gunze.json").write_text(
    json.dumps(pack_gunze, indent=2, ensure_ascii=False)
)
Path("data/ammo_rows.json").write_text(
    json.dumps(ammo_rows, indent=2, ensure_ascii=False)
)

print("\nSaved pack_gunze.json and ammo_rows.json")

# Print samples
print("\nSample Gunze→Ammo mappings (first 5):")
for i, (gunze_code, matches) in enumerate(list(gunze_to_ammo.items())[:5]):
    ammo_code = matches[0][0]
    dist = matches[0][2]
    print(f"  {gunze_code:5s} → {ammo_code:10s} (distance: {dist:.1f})")

print("\nSample Ammo→Gunze mappings (first 5):")
for i, (ammo_code, matches) in enumerate(list(ammo_to_gunze.items())[:5]):
    gunze_code = matches[0][0]
    dist = matches[0][2]
    print(f"  {ammo_code:10s} → {gunze_code:5s} (distance: {dist:.1f})")
