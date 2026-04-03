#!/usr/bin/env python3
"""
Fix short/abbreviated names in Mr Hobby pack files by replacing
short all-caps tokens (e.g. 'G', 'ME', 'SG') with 'Unnamed'.
Writes updated JSON back to data/pack_mr_hobby.json and data/results/pack_mr_hobby.json
"""
from pathlib import Path
import json
import re

ROOT = Path(__file__).resolve().parents[2]
DATA = ROOT / "data"
RESULTS = DATA / "results"


def fix_pack(fp):
    j = json.loads(fp.read_text())
    changed = 0
    for c in j.get("colors", []):
        name = c.get("name", "")
        if name and re.fullmatch(r"[A-Z]{1,3}", name):
            c["name"] = "Unnamed"
            changed += 1
    fp.write_text(json.dumps(j, indent=2, ensure_ascii=False))
    return changed


for path in [DATA / "pack_mr_hobby.json", RESULTS / "pack_mr_hobby.json"]:
    if path.exists():
        n = fix_pack(path)
        print(f"Updated {n} names in {path}")
    else:
        print(f"File not found: {path}")
