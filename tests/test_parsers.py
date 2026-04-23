#!/usr/bin/env python3
"""
Tests for color parsers.

Validates parsed data by checking:
- Total item count
- Unique item count (by code)
- Data structure and required fields
"""

import json
import unittest
from pathlib import Path
from collections import Counter


class TestParserData(unittest.TestCase):
    """Test suite for validating parsed color data."""

    DATA_DIR = Path(__file__).parent.parent / "data"

    # Define all parser brands and their corresponding data files
    PARSERS = {
        "ak": {"file": "pack_ak.json", "brand": "AK Interactive"},
        "ammo": {"file": "pack_ammo.json", "brand": "Ammo by Mig"},
        "ammo_atom": {"file": "pack_ammo_atom.json", "brand": "Ammo by Mig Atom"},
        "hobby_color": {
            "file": "pack_hobby_color.json",
            "brand": "Aqueous Hobby color",
        },
        "humbrol": {"file": "pack_humbrol.json", "brand": "Humbrol"},
        "mr_color": {"file": "pack_mr_color.json", "brand": "Mr. Color"},
        "ral": {"file": "pack_ral.json", "brand": "RAL"},
        "rlm": {"file": "pack_rlm.json", "brand": "RLM"},
        "tamiya": {"file": "pack_tamiya.json", "brand": "Tamiya"},
        "vallejo": {"file": "pack_vallejo.json", "brand": "Vallejo"},
        "federal_standard": {
            "file": "pack_federal_standard.json",
            "brand": "Federal Standard",
        },
    }

    def _load_parser_data(self, brand_key):
        """Load JSON data for a parser."""
        file_path = self.DATA_DIR / self.PARSERS[brand_key]["file"]
        if not file_path.exists():
            self.skipTest(f"Data file not found: {file_path}")
        with open(file_path, "r") as f:
            return json.load(f)

    def _count_items(self, data):
        """Count total items parsed."""
        return len(data.get("colors", []))

    def _count_unique_items(self, data):
        """Count unique items by code."""
        codes = [color.get("code") for color in data.get("colors", [])]
        return len(set(codes))

    def _find_duplicate_codes(self, data):
        """Find all duplicate codes."""
        codes = [color.get("code") for color in data.get("colors", [])]
        code_counts = Counter(codes)
        return {code: count for code, count in code_counts.items() if count > 1}

    def test_ak_parser(self):
        """Test AK Interactive parser."""
        self._test_parser_data("ak")

    def test_ammo_parser(self):
        """Test Ammo parser."""
        self._test_parser_data("ammo")

    def test_ammo_atom_parser(self):
        """Test Ammo-Atom parser."""
        self._test_parser_data("ammo_atom")

    def test_hobby_color_parser(self):
        """Test Aqueous Hobby color parser."""
        self._test_parser_data("hobby_color")

    def test_humbrol_parser(self):
        """Test Humbrol parser."""
        self._test_parser_data("humbrol")

    def test_mr_color_parser(self):
        """Test Mr. Color parser."""
        self._test_parser_data("mr_color")

    def test_rlm_parser(self):
        """Test RLM parser."""
        self._test_parser_data("rlm")

    def test_tamiya_parser(self):
        """Test Tamiya parser."""
        self._test_parser_data("tamiya")

    def test_vallejo_parser(self):
        """Test Vallejo parser."""
        self._test_parser_data("vallejo")

    def test_federal_standard_parser(self):
        """Test Federal Standard parser."""
        self._test_parser_data("federal_standard")

    def test_ral_parser(self):
        """Test RAL parser."""
        self._test_parser_data("ral")

    def _test_parser_data(self, brand_key):
        """Generic test for parser data."""
        data = self._load_parser_data(brand_key)

        # Test data structure
        self.assertIn("colors", data, f"{brand_key}: Missing 'colors' field")
        self.assertIn("brand", data, f"{brand_key}: Missing 'brand' field")
        self.assertIn("count", data, f"{brand_key}: Missing 'count' field")

        # Count items
        total_count = self._count_items(data)
        unique_count = self._count_unique_items(data)
        duplicates = self._find_duplicate_codes(data)

        # Verify count field matches actual count
        self.assertEqual(
            total_count,
            data["count"],
            f"{brand_key}: Count mismatch. Expected {data['count']}, got {total_count}",
        )

        # Verify all items have required fields
        for i, color in enumerate(data["colors"]):
            self.assertIn(
                "code",
                color,
                f"{brand_key}: Color at index {i} missing 'code' field",
            )
            self.assertIn(
                "name",
                color,
                f"{brand_key}: Color at index {i} missing 'name' field",
            )
            self.assertIn(
                "hex",
                color,
                f"{brand_key}: Color at index {i} missing 'hex' field",
            )

        # Print summary
        print(f"\n{brand_key.upper()} Parser Summary:")
        print(f"  Total items parsed: {total_count}")
        print(f"  Unique items (by code): {unique_count}")
        if duplicates:
            print(f"  Duplicate codes found: {len(duplicates)}")
            for code, count in sorted(duplicates.items())[:5]:
                print(f"    - {code}: {count} times")
            if len(duplicates) > 5:
                print(f"    ... and {len(duplicates) - 5} more")


class TestParserComparison(unittest.TestCase):
    """Compare parsing results across all parsers."""

    DATA_DIR = Path(__file__).parent.parent / "data"
    PARSERS = {
        "ak": "pack_ak.json",
        "ammo": "pack_ammo.json",
        "ammo_atom": "pack_ammo_atom.json",
        "hobby_color": "pack_hobby_color.json",
        "humbrol": "pack_humbrol.json",
        "mr_color": "pack_mr_color.json",
        "ral": "pack_ral.json",
        "rlm": "pack_rlm.json",
        "tamiya": "pack_tamiya.json",
        "vallejo": "pack_vallejo.json",
        "federal_standard": "pack_federal_standard.json",
    }

    def test_all_parsers_summary(self):
        """Generate summary statistics for all parsers."""
        summary = {}

        for brand_key, filename in self.PARSERS.items():
            file_path = self.DATA_DIR / filename
            if not file_path.exists():
                continue

            with open(file_path, "r") as f:
                data = json.load(f)

            colors = data.get("colors", [])
            codes = [color.get("code") for color in colors]
            unique_codes = set(codes)
            duplicates = [code for code in unique_codes if codes.count(code) > 1]

            summary[brand_key] = {
                "total": len(colors),
                "unique": len(unique_codes),
                "duplicates": len(duplicates),
            }

        # Print summary table
        print("\n" + "=" * 70)
        print("PARSER SUMMARY - All Brands")
        print("=" * 70)
        print(f"{'Brand':<20} {'Total Items':<15} {'Unique':<15} {'Duplicates':<15}")
        print("-" * 70)

        total_all = 0
        unique_all = 0
        duplicates_all = 0

        for brand, stats in sorted(summary.items()):
            total = stats["total"]
            unique = stats["unique"]
            dups = stats["duplicates"]
            print(f"{brand:<20} {total:<15} {unique:<15} {dups:<15}")
            total_all += total
            unique_all += unique
            duplicates_all += dups

        print("-" * 70)
        print(f"{'TOTAL':<20} {total_all:<15} {unique_all:<15} {duplicates_all:<15}")
        print("=" * 70)

        # Assertions to ensure test passes
        self.assertGreater(len(summary), 0, "No parser data found")
        for brand, stats in summary.items():
            self.assertGreaterEqual(stats["total"], 0, f"{brand}: Invalid total count")
            self.assertGreaterEqual(
                stats["unique"], 0, f"{brand}: Invalid unique count"
            )
            self.assertLessEqual(
                stats["unique"],
                stats["total"],
                f"{brand}: Unique count cannot exceed total",
            )


if __name__ == "__main__":
    unittest.main()
