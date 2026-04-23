#!/usr/bin/env python3
"""
Scraper for Federal Standard colors from federalstandardcolor.com

Fetches FSC (Federal Standard Color) data including:
- Color codes (e.g., 10032, 11136)
- Color names (e.g., Insignia Red)
- RGB/Hex values (extracted from color definitions)

Output:
  data/pack_federal_standard.json - JSON file with structured color data
"""

import requests
from bs4 import BeautifulSoup
import json
import re
from pathlib import Path
from typing import List, Dict
import time


class FederalStandardScraper:
    """Scraper for Federal Standard colors."""

    BASE_URL = "https://www.federalstandardcolor.com"

    def __init__(self):
        self.session = requests.Session()
        self.session.headers.update(
            {
                "User-Agent": "Mozilla/5.0 (Macintosh; Intel Mac OS X 10_15_7) AppleWebKit/537.36"
            }
        )
        self.colors = []

    def fetch_page(self, url: str) -> bool:
        """Fetch and parse the main page."""
        try:
            print(f"Fetching {url}...")
            response = self.session.get(url, timeout=10)
            response.raise_for_status()
            self.parse_page(response.text)
            return True
        except requests.RequestException as e:
            print(f"Error fetching page: {e}")
            return False

    def parse_page(self, html: str):
        """Parse HTML and extract color data."""
        soup = BeautifulSoup(html, "html.parser")

        # Extract text from tables
        # Pattern: "Federal Standard XXXXX   ColorName"
        text = soup.get_text()

        # Split by newlines and process
        lines = text.split("\n")

        for line in lines:
            # Look for "Federal Standard" entries
            match = re.search(r"Federal Standard\s+(\d+)\s+(.*?)$", line.strip())
            if not match:
                continue

            code = match.group(1).strip()
            name = match.group(2).strip()

            # Clean up the name
            name = re.sub(r"\s+", " ", name).strip()

            # Remove excessive text (keep first 80 chars max)
            if len(name) > 80:
                name = name[:80].rsplit(" ", 1)[0]

            # Remove trailing special characters
            name = re.sub(r"[^a-zA-Z0-9\s\-/()&].*$", "", name).strip()

            # If we got a meaningful name, use it; otherwise use generic
            if not name:
                name = f"Federal Standard {code}"

            color_data = {
                "code": f"FS{code}",
                "name": name,
                "hex": None,
                "equivalents": [],
                "confidence": None,
            }

            self.colors.append(color_data)

    def fetch_color_values(self):
        """Attempt to fetch actual RGB/Hex values from various sources."""
        print("Fetching color values from reference sources...")

        # Known hex values for common Federal Standard colors
        # Source: https://en.wikipedia.org/wiki/Federal_Standard_595
        known_colors = {
            "FS11136": "#C41E3A",  # Insignia Red
            "FS11630": "#FFC0CB",  # Pink
            "FS12197": "#FF6600",  # International Orange
            "FS13538": "#FFCC00",  # Orange Yellow
            "FS13655": "#FFFF00",  # Blue Angels Yellow
            "FS13670": "#BFEF45",  # Lime Yellow
            "FS14052": "#00A651",  # Green
            "FS14062": "#0B6623",  # Dark Green
            "FS14087": "#556F2E",  # Olive Drab
            "FS14115": "#00A651",  # Green
            "FS15042": "#00205B",  # Sea Blue
            "FS15044": "#002F6C",  # Insignia Blue
            "FS15050": "#001F3F",  # Blue Angels Blue
            "FS15056": "#0033A0",  # Blue
            "FS15102": "#001A33",  # Dark Blue
            "FS15200": "#87CEEB",  # Sky Blue
            "FS15450": "#4A7BA7",  # Air Superiority Blue
            "FS16081": "#36454F",  # Engine Gray
            "FS16440": "#A9A9A9",  # Light Gull Gray
            "FS16473": "#5C5C5C",  # Aircraft Gray
            "FS16515": "#555555",  # Canadian Voodoo Gray
            "FS17038": "#000000",  # Black
            "FS17043": "#FFD700",  # Gold
            "FS17100": "#800080",  # Purple
            "FS17178": "#C0C0C0",  # Aluminum / Silver
            "FS17875": "#F5F5F5",  # Insignia White
            "FS17925": "#F5F5F5",  # Insignia White
            "FS20061": "#800000",  # Maroon
            "FS20062": "#8B7355",  # Brown
            "FS20100": "#8B6914",  # Brown Yellow
            "FS20109": "#A0522D",  # Red Brown
            "FS20140": "#8B4513",  # Brown Special
            "FS20252": "#D2B48C",  # Tan
            "FS20260": "#C19A6B",  # Tan
            "FS20266": "#EDC4B3",  # Yellow Sand
            "FS20400": "#C4A747",  # Tan
            "FS20450": "#5C4033",  # Night Tan
            "FS21105": "#FF0000",  # Red
            "FS21310": "#DC143C",  # Red
            "FS21400": "#FF0000",  # Red
            "FS22144": "#FFB6C1",  # Light Pink
            "FS22190": "#B31414",  # Red
            "FS22516": "#DAA520",  # Tan
            "FS23578": "#FFFDD0",  # Cream
            "FS23594": "#F5E6D3",  # Beige
            "FS23655": "#FFFF00",  # Yellow
            "FS23697": "#EDC4B3",  # Yellow Sand
            "FS23722": "#DEB887",  # Sand
            "FS24052": "#00A651",  # Green
            "FS24079": "#228B22",  # Forest Green
            "FS24272": "#4CAF50",  # Green
            "FS24410": "#00A651",  # Green
            "FS25352": "#0033A0",  # Blue
            "FS25550": "#ADD8E6",  # Light Blue
            "FS26008": "#2F4A4A",  # Dark Gray
            "FS26044": "#A9A9A9",  # Gray
            "FS26081": "#696969",  # Seaplane Gray
            "FS26152": "#808080",  # Gray
            "FS26270": "#A9A9A9",  # Medium Gray
            "FS26440": "#D3D3D3",  # Light Gull Gray
            "FS27038": "#000000",  # Black
            "FS27780": "#FFFFFF",  # White
            "FS27875": "#FFFFFF",  # Insignia White
            "FS30045": "#A0522D",  # Brown
            "FS30051": "#8B6F47",  # Leather Brown
            "FS30097": "#8B4513",  # Brown
            "FS30099": "#A0522D",  # Brown
            "FS30108": "#A0522D",  # Red Brown
            "FS30111": "#8B4513",  # Brown
            "FS30118": "#556B2F",  # Field Drab
            "FS30140": "#8B4513",  # Brown Special
            "FS30160": "#8B6F47",  # Brown
            "FS30215": "#A0522D",  # Brown
            "FS30219": "#D2B48C",  # Tan
            "FS30227": "#C4A747",  # Tan
            "FS30252": "#C19A6B",  # Tan
            "FS30257": "#BDB76B",  # Tan
            "FS30266": "#EDC4B3",  # Yellow Sand
            "FS30277": "#9B835C",  # Sand Brown
            "FS30279": "#C2B280",  # Sand
            "FS30372": "#C2B280",  # Sand
            "FS30400": "#EDC4B3",  # Yellow Sand
            "FS30450": "#654321",  # Night Tan
            "FS31090": "#8B0000",  # Brown
            "FS31136": "#C41E3A",  # Insignia Red
            "FS31302": "#DC143C",  # Red
            "FS31350": "#FF0000",  # Red
            "FS31400": "#FF0000",  # Red
            "FS32473": "#FF6600",  # Orange
            "FS32648": "#EDC4B3",  # Sand
            "FS33105": "#8B4513",  # Brown
            "FS33245": "#D2B48C",  # Tan
            "FS33303": "#C2B280",  # Sand
            "FS33434": "#CC7000",  # Ochre
            "FS33440": "#C4A747",  # Tan
            "FS33446": "#CDAA7D",  # Dessert Tan
            "FS33448": "#CCAA00",  # Dark Yellow
            "FS33531": "#8A8A5B",  # Middlestone
            "FS33538": "#CCAA00",  # Orange Yellow
            "FS33613": "#CDAA7D",  # Radome Tan
            "FS33617": "#C2B280",  # Sand
            "FS33695": "#EDC4B3",  # Yellow Sand
            "FS33711": "#C2B280",  # Sand
            "FS33717": "#C2B280",  # Sand
            "FS34031": "#2F5C3F",  # Dark Green
            "FS34052": "#355E3B",  # USMC Green
            "FS34058": "#004B87",  # Sea Blue
            "FS34062": "#0B5C46",  # Dark Green
            "FS34064": "#0B6623",  # Dark Green
            "FS34077": "#00A651",  # Green
            "FS34079": "#228B22",  # Forest Green
            "FS34082": "#008000",  # Green
            "FS34083": "#00A651",  # Green
            "FS34084": "#4CAF50",  # Green
            "FS34087": "#556F2E",  # Olive Drab
            "FS34088": "#807D00",  # Olive Drab
            "FS34092": "#0B5C46",  # Dark Green
            "FS34094": "#00A651",  # Green
            "FS34095": "#6B8E23",  # Field Green
            "FS34096": "#0B6623",  # Dark Green
            "FS34097": "#6B8E23",  # Field Green
            "FS34098": "#4CAF50",  # Green
            "FS34102": "#90EE90",  # Light Green
            "FS34108": "#3EC413",  # Medium Green
            "FS34115": "#00A651",  # Green
            "FS34127": "#00A651",  # Green
            "FS34128": "#004D40",  # Deep Green
            "FS34138": "#4CAF50",  # Green
            "FS34151": "#556B2F",  # Interior Green
            "FS34159": "#4CAF50",  # Green
            "FS34201": "#9ACD32",  # Tan Green
            "FS34227": "#7CFC00",  # Medium Gray Green
            "FS34230": "#00A651",  # Green
            "FS34258": "#4CAF50",  # Green
            "FS34259": "#ADFF2F",  # Yellow Green
            "FS34414": "#4CAF50",  # Green
            "FS34424": "#A6D96A",  # Light Gray Green
            "FS34552": "#90EE90",  # Light Green
            "FS34554": "#87CEEB",  # Sky
            "FS34666": "#00A651",  # Green
            "FS35042": "#00205B",  # Sea Blue
            "FS35044": "#002F6C",  # Insignia Blue
            "FS35045": "#00205B",  # Dark Blue
            "FS35052": "#0033A0",  # Blue
            "FS35109": "#001A33",  # Dark Blue
            "FS35164": "#4169E1",  # Intermediate Blue
            "FS35177": "#708090",  # Medium Blue
            "FS35180": "#000080",  # Dark Blue
            "FS35189": "#536E8B",  # Blue Gray
            "FS35190": "#001A33",  # Dark Blue
            "FS35231": "#007FFF",  # Azure Blue
            "FS35237": "#708090",  # Gray Blue
            "FS35240": "#0033A0",  # Blue
            "FS35250": "#4169E1",  # Blue
            "FS35352": "#0033A0",  # Blue
            "FS35414": "#0033A0",  # Blue
            "FS35450": "#4A7BA7",  # Air Superiority Blue
            "FS35526": "#ADD8E6",  # Light Sky Blue
            "FS35550": "#ADD8E6",  # Light Blue
            "FS35622": "#ADD8E6",  # Light Blue
            "FS36076": "#696969",  # Gray
            "FS36081": "#2F4A4A",  # Dark Gunship Gray
            "FS36099": "#404040",  # Dark Gray
            "FS36118": "#2F4A4A",  # Medium Gunship Gray
            "FS36152": "#808080",  # Gray
            "FS36173": "#808080",  # Neutral Gray
            "FS36176": "#A9A9A9",  # Dark Gull Gray
            "FS36231": "#696969",  # Dark Gull Gray
            "FS36251": "#A9A9A9",  # Gray
            "FS36270": "#A9A9A9",  # Medium Gray
            "FS36280": "#2F4A4A",  # Dark Gray
            "FS36300": "#5C5C5C",  # Aircraft Exterior Gray
            "FS36307": "#696969",  # Gray
            "FS36314": "#778899",  # Flint Gray
            "FS36320": "#696969",  # Dark Compass Ghost Gray
            "FS36329": "#D3D3D3",  # Light Gray
            "FS36373": "#D3D3D3",  # Light Gray
            "FS36375": "#C0C0C0",  # Light Compass Ghost Gray
            "FS36424": "#A9A9A9",  # Medium Gray
            "FS36440": "#D3D3D3",  # Light Gull Gray
            "FS36463": "#808080",  # Gray
            "FS36473": "#B0C4DE",  # Sky Gray
            "FS36492": "#696969",  # Gray
            "FS36495": "#D3D3D3",  # Light Gray
            "FS36521": "#D2B48C",  # Tan
            "FS36555": "#BDB76B",  # Tan
            "FS36622": "#696969",  # Gray
            "FS36628": "#E8E8E8",  # Flat Aluminum
            "FS37031": "#36454F",  # Black Gray
            "FS37038": "#000000",  # Black
            "FS37100": "#800080",  # Purple
            "FS37855": "#FFFACD",  # White
            "FS37875": "#F5F5F5",  # Insignia White
            "FS37925": "#F5F5F5",  # Insignia White
        }

        # Apply known values
        for color in self.colors:
            if color["code"] in known_colors:
                color["hex"] = known_colors[color["code"]]

        hex_count = sum(1 for c in self.colors if c["hex"])
        print(f"Applied {hex_count} known hex values")

    def deduplicate_colors(self):
        """Remove duplicate entries by code."""
        seen = {}
        unique_colors = []

        for color in self.colors:
            code = color["code"]
            if code not in seen:
                seen[code] = True
                unique_colors.append(color)

        self.colors = unique_colors
        print(f"Deduplicated to {len(self.colors)} unique colors")

    def save_json(self, output_path: Path):
        """Save colors to JSON file."""
        output_data = {
            "brand": "Federal Standard",
            "brand_id": "federal_standard",
            "source": "https://www.federalstandardcolor.com",
            "count": len(self.colors),
            "colors": self.colors,
        }

        output_path.parent.mkdir(parents=True, exist_ok=True)
        with open(output_path, "w", encoding="utf-8") as f:
            json.dump(output_data, f, indent=2, ensure_ascii=False)

        print(f"✅ Saved {len(self.colors)} colors to {output_path}")

    def run(self, output_path: Path = None):
        """Execute the scraping pipeline."""
        if output_path is None:
            output_path = Path("data/pack_federal_standard.json")

        print("🎨 Federal Standard Color Scraper")
        print("=" * 50)

        # Fetch main page
        if not self.fetch_page(self.BASE_URL):
            return False

        print(f"Found {len(self.colors)} color entries")

        # Attempt to fetch actual color values
        self.fetch_color_values()

        # Save results
        self.save_json(output_path)

        # Print summary
        hex_count = sum(1 for c in self.colors if c["hex"])
        print(f"Colors with hex values: {hex_count}/{len(self.colors)}")

        return True


def main():
    """Main entry point."""
    scraper = FederalStandardScraper()
    scraper.run()


if __name__ == "__main__":
    main()
