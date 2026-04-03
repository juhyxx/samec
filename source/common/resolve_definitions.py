#!/usr/bin/env python3
"""Resolve color definitions (RAL/FS) to hex using a mapping file.

Writes data/ammo_rows_resolved.json and logs missing codes to data/missing_ral_codes.txt
"""
import json
import re
from pathlib import Path

IN = Path("data/ammo_rows.json")
OUT = Path("data/ammo_rows_resolved.json")
MAPPING = Path("data/ral_to_hex.json")
MISSING = Path("data/missing_ral_codes.txt")

# load
if not IN.exists():
    print("Input not found:", IN)
    raise SystemExit(1)
rows = json.loads(IN.read_text())
map_data = {}
if MAPPING.exists():
    try:
        map_data = json.loads(MAPPING.read_text())
    except Exception as e:
        print("Failed to load mapping:", e)

# helper
ral_re = re.compile(r"RAL\s*-?\s*(\d{4}|\d{3})", re.IGNORECASE)
fs_re = re.compile(r"FS\s*-?\s*(\d{3,5})", re.IGNORECASE)

missing = set()
updated = []
for r in rows:
    resolved = None
    src = None
    definition = r.get("definition")
    if definition:
        m = ral_re.search(definition)
        if m:
            code = m.group(1).zfill(3)
            src = f"RAL {code}"
            hexv = map_data.get(code)
            if hexv:
                resolved = hexv
            else:
                missing.add(code)
        else:
            m2 = fs_re.search(definition)
            if m2:
                # keep FS as fallback key
                code = m2.group(1)
                src = f"FS {code}"
                # no FS mapping by default
                missing.add(f"FS {code}")

    # prefer resolved hex if available, else keep existing
    r["resolved_hex"] = resolved or None
    r["resolved_from"] = src
    updated.append(r)

OUT.write_text(json.dumps(updated, indent=2, ensure_ascii=False))
if missing:
    MISSING.write_text("\n".join(sorted(missing)))
    print(f"Resolved with mapping; missing {len(missing)} codes written to {MISSING}")
else:
    if MAPPING.exists():
        print("Resolved all definitions using mapping")
    else:
        print("No mapping file found; no resolutions applied")
