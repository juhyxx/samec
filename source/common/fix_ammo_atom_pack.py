#!/usr/bin/env python3
"""
Fix and enrich Ammo Atom pack:
- Remove header placeholder entries
- Fill hex values from RAL where available (using data/ral_to_hex.json)
- Compute equivalents by comparing hex values to other packs

Writes updated pack to data/pack_ammo_atom.json and data/results/pack_ammo_atom.json
"""
from pathlib import Path
import json
import re
from math import sqrt

ROOT = Path(__file__).resolve().parents[2]
DATA = ROOT / "data"
RESULTS = DATA / "results"


def hex_distance(h1, h2):
    try:
        a = h1.lstrip("#")
        b = h2.lstrip("#")
        r1, g1, b1 = int(a[0:2], 16), int(a[2:4], 16), int(a[4:6], 16)
        r2, g2, b2 = int(b[0:2], 16), int(b[2:4], 16), int(b[4:6], 16)
        return sqrt((r1 - r2) ** 2 + (g1 - g2) ** 2 + (b1 - b2) ** 2)
    except Exception:
        return float("inf")


# Load files
pack_path = RESULTS / "pack_ammo_atom.json"
pack = json.loads(pack_path.read_text())
ral_map = json.loads((DATA / "ral_to_hex.json").read_text())

# Load other packs to build equivalence candidates
other_packs = []
for p in ["pack_ammo.json", "pack_gunze.json", "pack_ak.json", "pack_mr_hobby.json"]:
    fp = DATA / p
    if not fp.exists():
        continue
    other = json.loads(fp.read_text())
    other_packs.append(other)

candidates = []
for pack_other in other_packs:
    brand = pack_other.get("brand", "other")
    for c in pack_other.get("colors", []):
        hexv = c.get("hex")
        code = c.get("code")
        if hexv and hexv != "#cccccc":
            candidates.append((brand, code, hexv))

# Clean and enrich Atom colors
new_colors = []
for c in pack.get("colors", []):
    code = c.get("code")
    name = c.get("name", "").strip()
    if not code:
        continue
    # skip header placeholder
    if code.upper() == "ATOM" and (name.upper() == "COLOR NAME" or name == ""):
        continue

    # try extract RAL from name
    hexv = c.get("hex")
    if hexv in (None, "", "#cccccc"):
        m = re.search(r"RAL\s*0?([0-9]{3,4})", name.upper())
        if m:
            ral = m.group(1)
            if ral in ral_map:
                hexv = ral_map[ral]

    # keep original or fallback to nullish placeholder
    if not hexv:
        hexv = "#cccccc"

    # compute equivalents: nearest matches from candidates
    equivalents = []
    if hexv and hexv != "#cccccc":
        sims = []
        for brand, code2, hex2 in candidates:
            d = hex_distance(hexv, hex2)
            sims.append((d, brand, code2, hex2))
        sims.sort(key=lambda x: x[0])
        for d, brand, code2, hex2 in sims[:3]:
            if d <= 50:
                equivalents.append({"brand": brand, "code": code2, "distance": d})

    new_colors.append(
        {
            "code": code,
            "name": name if name else "Unnamed",
            "hex": hexv,
            "equivalents": equivalents,
            "confidence": c.get("confidence"),
        }
    )

# Build final structure
out = {
    "brand": pack.get("brand", "Ammo by Mig Atom"),
    "brand_id": pack.get("brand_id", "ammo_atom"),
    "source": str(pack_path),
    "count": len(new_colors),
    "colors": new_colors,
}

# Write updated files
dst1 = DATA / "pack_ammo_atom.json"
dst2 = RESULTS / "pack_ammo_atom.json"
for dst in [dst1, dst2]:
    dst.write_text(json.dumps(out, indent=2, ensure_ascii=False))

print(f"Wrote {len(new_colors)} Atom colors to:")
print(f"  {dst1}")
print(f"  {dst2}")
