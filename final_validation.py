#!/usr/bin/env python3
"""Final validation that all work is complete."""
import sys
import json
import csv

print("=" * 70)
print("FINAL VALIDATION")
print("=" * 70)

all_pass = True

# Test 1: Check parse_ak.py imports
try:
    sys.path.insert(0, "source/ak")
    import parse as ak_parse

    funcs = [
        "rgb_to_hex",
        "extract_ocr_with_bbox",
        "cluster_rows",
        "find_color_swatches",
        "normalize_ak_code",
        "extract_color_data_from_rows",
        "parse_ak_images",
    ]
    for f in funcs:
        assert hasattr(ak_parse, f), f"Missing: {f}"
    print("✓ parse_ak.py: All functions present")
except Exception as e:
    print(f"✗ parse_ak.py: {e}")
    all_pass = False

# Test 2: Verify JSON output
try:
    with open("data/results/pack_ak.json") as f:
        pack = json.load(f)
        assert pack["count"] == 240, f"Count mismatch: {pack['count']}"
        assert all("code" in c for c in pack["colors"]), "Missing code"
        assert all("name" in c for c in pack["colors"]), "Missing name"
        assert all("type" in c for c in pack["colors"]), "Missing type"
        assert all("hex" in c for c in pack["colors"]), "Missing hex"
    print(f"✓ pack_ak.json: 240 colors with all fields")
except Exception as e:
    print(f"✗ pack_ak.json: {e}")
    all_pass = False

# Test 3: Verify CSV output
try:
    with open("data/results/pack_ak.csv") as f:
        reader = csv.DictReader(f)
        rows = list(reader)
        assert len(rows) == 240, f"Row count: {len(rows)}"
        assert "type" in reader.fieldnames, "Missing type field"
    print(f"✓ pack_ak.csv: 240 rows with type field")
except Exception as e:
    print(f"✗ pack_ak.csv: {e}")
    all_pass = False

# Test 4: Check all parsers exist
try:
    from pathlib import Path

    parsers = list(Path("source").glob("*/parse.py"))
    assert len(parsers) == 5, f"Parser count: {len(parsers)}"
    print(f"✓ All parsers: 5 parse.py files found")
except Exception as e:
    print(f"✗ Parsers: {e}")
    all_pass = False

# Test 5: Check run_pipeline.py
try:
    import py_compile

    py_compile.compile("scripts/run_pipeline.py", doraise=True)
    print(f"✓ run_pipeline.py: Syntax OK")
except Exception as e:
    print(f"✗ run_pipeline.py: {e}")
    all_pass = False

print()
if all_pass:
    print("=" * 70)
    print("✅ ALL VALIDATION TESTS PASSED")
    print("=" * 70)
    sys.exit(0)
else:
    print("❌ SOME TESTS FAILED")
    sys.exit(1)
