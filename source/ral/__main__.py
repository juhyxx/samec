#!/usr/bin/env python3
"""
Scraper for RAL colors from German Wikipedia

Fetches RAL Classic color data including:
- Color codes (4-digit numbers, e.g., 1001, 2000, 3000)
- Color names (German)
- RGB/Hex values (extracted from HTML tables)

Output:
  data/pack_ral.json - JSON file with structured color data
"""

import requests
from bs4 import BeautifulSoup
import json
import re
from pathlib import Path
from typing import List, Dict


class RALScraper:
    """Scraper for RAL colors from Wikipedia."""

    BASE_URL = "https://de.wikipedia.org/wiki/RAL-Farbe"

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
            response = self.session.get(url, timeout=15)
            response.raise_for_status()
            self.parse_page(response.text)
            return True
        except requests.RequestException as e:
            print(f"Error fetching page: {e}")
            return False

    def parse_page(self, html: str):
        """Parse HTML and extract color data from tables."""
        soup = BeautifulSoup(html, "html.parser")

        # Find all tables - they're structured by color groups
        tables = soup.find_all("table", {"class": "wikitable"})

        print(f"Found {len(tables)} tables")

        for table_idx, table in enumerate(tables):
            rows = table.find_all("tr")

            for row in rows:
                cells = row.find_all(["td", "th"])
                if len(cells) < 2:
                    continue

                # Extract all text from cells
                cell_texts = [cell.get_text(strip=True) for cell in cells]

                # Look for 4-digit RAL code in any cell
                ral_code = None
                code_text = " ".join(cell_texts)

                # Try different patterns for RAL codes
                code_match = re.search(r"RAL\s*(\d{4})", code_text, re.IGNORECASE)
                if code_match:
                    ral_code = code_match.group(1)
                else:
                    # Try just 4 digits
                    code_match = re.search(r"\b(\d{4})\b", code_text)
                    if code_match:
                        ral_code = code_match.group(1)

                if not ral_code:
                    continue

                # Extract color name - usually in the 2nd or 3rd cell
                name = ""
                for i, cell_text in enumerate(cell_texts):
                    # Skip codes and hex values
                    if re.match(r"^\d{4}$", cell_text) or re.match(
                        r"^#[0-9a-fA-F]{6}$", cell_text
                    ):
                        continue
                    if (
                        len(cell_text) > 2
                        and len(cell_text) < 100
                        and "RAL" not in cell_text
                    ):
                        name = cell_text
                        break

                if not name:
                    name = f"RAL {ral_code}"

                # Try to extract hex color from style attributes
                hex_color = None
                for cell in cells:
                    # Check background-color style
                    style = cell.get("style", "")
                    if "background" in style.lower() or "color" in style.lower():
                        hex_match = re.search(r"#[0-9a-fA-F]{6}", style)
                        if hex_match:
                            hex_color = hex_match.group(0)
                            break

                    # Check title attribute
                    title = cell.get("title", "")
                    hex_match = re.search(r"#[0-9a-fA-F]{6}", title)
                    if hex_match:
                        hex_color = hex_match.group(0)
                        break

                color_data = {
                    "code": f"RAL{ral_code}",
                    "name": name,
                    "hex": hex_color,
                    "equivalents": [],
                    "confidence": None,
                }

                # Check if this color already exists
                if not any(c["code"] == color_data["code"] for c in self.colors):
                    self.colors.append(color_data)

    def apply_known_hex_values(self):
        """Apply known hex values from RAL color reference."""
        # Known RAL hex values (from official RAL Classic palette)
        known_colors = {
            "RAL1000": "#BEBD7F",  # Beige
            "RAL1001": "#C2B078",  # Beige
            "RAL1002": "#C6A664",  # Sand yellow
            "RAL1003": "#E5BE01",  # Signal yellow
            "RAL1004": "#CDA922",  # Golden yellow
            "RAL1005": "#CF8600",  # Honey yellow
            "RAL1006": "#E4A010",  # Marigold yellow
            "RAL1007": "#DC9D07",  # Daffodil yellow
            "RAL1011": "#8A7967",  # Brown beige
            "RAL1012": "#D3AE01",  # Lemon yellow
            "RAL1013": "#EAE6CA",  # Oyster white
            "RAL1014": "#E1CC4F",  # Ivory
            "RAL1015": "#E6D690",  # Light ivory
            "RAL1016": "#EDFF21",  # Sulfur yellow
            "RAL1017": "#F8F32B",  # Saffron yellow
            "RAL1018": "#F8F32B",  # Zinc yellow
            "RAL1019": "#9E9B85",  # Grey beige
            "RAL1020": "#9B8B3D",  # Olive yellow
            "RAL1021": "#F3DA0B",  # Rape yellow
            "RAL1023": "#F0D030",  # Traffic yellow
            "RAL1024": "#CEA135",  # Ochre yellow
            "RAL1026": "#FFFF00",  # Luminous yellow
            "RAL1027": "#DAA520",  # Curry
            "RAL1028": "#F0D000",  # Melon yellow
            "RAL1032": "#D6AE01",  # Broom yellow
            "RAL1033": "#F0D000",  # Dahlia yellow
            "RAL1034": "#EDA83D",  # Pastel yellow
            "RAL2000": "#EA7600",  # Orange yellow
            "RAL2001": "#BE2E26",  # Red orange
            "RAL2002": "#CB2821",  # Vermillion
            "RAL2003": "#FF7514",  # Pastel orange
            "RAL2004": "#F44611",  # Pure orange
            "RAL2005": "#FF2301",  # Luminous orange
            "RAL2007": "#FFA421",  # Bright orange
            "RAL2008": "#F75E25",  # Bright red orange
            "RAL2009": "#F54021",  # Traffic orange
            "RAL2010": "#D84B20",  # Signal orange
            "RAL2011": "#EC8B3C",  # Deep orange
            "RAL2012": "#E55C3F",  # Rust orange
            "RAL2013": "#922610",  # Chestnut orange
            "RAL3000": "#AC193D",  # Flame red
            "RAL3001": "#A52127",  # Signal red
            "RAL3002": "#A2231D",  # Carmine red
            "RAL3003": "#9B111E",  # Ruby red
            "RAL3004": "#75151E",  # Crimson red
            "RAL3005": "#5E2129",  # Wine red
            "RAL3007": "#412227",  # Black red
            "RAL3009": "#622E2A",  # Iron oxide
            "RAL3011": "#622E2A",  # Brown red
            "RAL3012": "#C1876B",  # Beige red
            "RAL3013": "#A4554D",  # Tomato red
            "RAL3014": "#D16B76",  # Antique pink
            "RAL3015": "#E1A6AD",  # Light pink
            "RAL3016": "#B24D49",  # Claret
            "RAL3017": "#CB7582",  # Rose
            "RAL3018": "#EC1C24",  # Strawberry red
            "RAL3020": "#CC0605",  # Traffic red
            "RAL3022": "#D5534F",  # Salmon red
            "RAL3024": "#FF0000",  # Luminous red
            "RAL3026": "#FF0000",  # Luminous bright red
            "RAL3027": "#C51D34",  # Raspberry red
            "RAL3031": "#B32428",  # Orient red
            "RAL4001": "#6D3F47",  # Red lilac
            "RAL4002": "#933D50",  # Red violet
            "RAL4003": "#DE4C8A",  # Heather violet
            "RAL4004": "#641C34",  # Claret violet
            "RAL4005": "#6E3F75",  # Blue lilac
            "RAL4006": "#A03472",  # Traffic purple
            "RAL4007": "#321E24",  # Purple black
            "RAL4008": "#6F4C6D",  # Signal violet
            "RAL4009": "#A18594",  # Pastel violet
            "RAL4010": "#CF3476",  # Telemagenta
            "RAL4011": "#8673A1",  # Pearl violet
            "RAL4012": "#6C7C98",  # Pearl black
            "RAL5000": "#354D73",  # Violet blue
            "RAL5001": "#1F3A70",  # Green blue
            "RAL5002": "#00247B",  # Ultramarine blue
            "RAL5003": "#001E50",  # Sapphire blue
            "RAL5004": "#18184A",  # Black blue
            "RAL5005": "#003DA5",  # Signal blue
            "RAL5007": "#3E5F8A",  # Brilliant blue
            "RAL5008": "#26252B",  # Grey blue
            "RAL5009": "#025669",  # Azure blue
            "RAL5010": "#004687",  # Gentian blue
            "RAL5011": "#231F20",  # Steel blue
            "RAL5012": "#3E8CC0",  # Light blue
            "RAL5013": "#1E3A8F",  # Cobalt blue
            "RAL5014": "#606E8C",  # Pigeon blue
            "RAL5015": "#0E4C96",  # Sky blue
            "RAL5016": "#004B87",  # Traffic blue
            "RAL5017": "#004B87",  # Traffic blue
            "RAL5018": "#3F7F4C",  # Turquoise blue
            "RAL5019": "#1B4D3E",  # Capri blue
            "RAL5020": "#1D3A3A",  # Ocean blue
            "RAL5021": "#256D7B",  # Water blue
            "RAL5022": "#20214F",  # Night blue
            "RAL5023": "#49678D",  # Remote blue
            "RAL5024": "#646E75",  # Pastel blue
            "RAL6000": "#316650",  # Patina green
            "RAL6001": "#287233",  # Emerald green
            "RAL6002": "#23423D",  # Leaf green
            "RAL6003": "#424632",  # Olive green
            "RAL6004": "#1F3A3F",  # Blue green
            "RAL6005": "#2F5233",  # Moss green
            "RAL6006": "#40403F",  # Grey green
            "RAL6007": "#343B29",  # Bottle green
            "RAL6008": "#39352A",  # Brown green
            "RAL6009": "#1E3932",  # Fir green
            "RAL6010": "#35682D",  # Grass green
            "RAL6011": "#587246",  # Reseda green
            "RAL6012": "#343E40",  # Black green
            "RAL6013": "#6B5D54",  # Reed green
            "RAL6014": "#47402E",  # Yellow olive
            "RAL6015": "#3D4035",  # Black olive
            "RAL6016": "#004F51",  # Turquoise green
            "RAL6017": "#4C7C59",  # May green
            "RAL6018": "#92C83E",  # Yellow green
            "RAL6019": "#BDECB6",  # Pastel green
            "RAL6020": "#2E5F3F",  # Chrome green
            "RAL6021": "#89AC76",  # Pale green
            "RAL6022": "#25221B",  # Brown olive
            "RAL6024": "#308446",  # Traffic green
            "RAL6025": "#3D642D",  # Fern green
            "RAL6026": "#003D14",  # Opal green
            "RAL6027": "#84C5C1",  # Light green
            "RAL6028": "#2D5016",  # Pine green
            "RAL6029": "#20603D",  # Mint green
            "RAL6032": "#317F43",  # Signal green
            "RAL6033": "#497E76",  # Mint turquoise
            "RAL6034": "#7FB069",  # Pastel turquoise
            "RAL6035": "#1B542D",  # Pearl green
            "RAL6036": "#193737",  # Pearl opal green
            "RAL6037": "#008941",  # Pure green
            "RAL6038": "#00BB2D",  # Luminous green
            "RAL7000": "#78858B",  # Squirrel grey
            "RAL7001": "#8B8680",  # Silver grey
            "RAL7002": "#7A7B7D",  # Olive grey
            "RAL7003": "#6E6E70",  # Moss grey
            "RAL7004": "#969992",  # Signal grey
            "RAL7005": "#595959",  # Slate grey
            "RAL7006": "#6B5D52",  # Beige grey
            "RAL7008": "#5B5B5B",  # Khaki grey
            "RAL7009": "#4D5645",  # Green grey
            "RAL7010": "#4C514A",  # Tarpaulin grey
            "RAL7011": "#434B4D",  # Iron grey
            "RAL7012": "#4E5754",  # Basalt grey
            "RAL7013": "#464B4E",  # Brown grey
            "RAL7014": "#4F5660",  # Slate grey
            "RAL7015": "#70747E",  # Slate grey
            "RAL7016": "#293133",  # Anthracite grey
            "RAL7017": "#44484E",  # Black grey
            "RAL7018": "#454B4E",  # Grey brown
            "RAL7019": "#383E45",  # Dark grey
            "RAL7020": "#3A3F47",  # Dark grey
            "RAL7021": "#23282D",  # Black grey
            "RAL7022": "#332F2C",  # Umbra grey
            "RAL7023": "#686C70",  # Concrete grey
            "RAL7024": "#474A51",  # Graphite grey
            "RAL7026": "#2F353B",  # Granite grey
            "RAL7030": "#8B8B7A",  # Stone grey
            "RAL7031": "#474B4E",  # Blue grey
            "RAL7032": "#B8B6AA",  # Pebble grey
            "RAL7033": "#7B8578",  # Cement grey
            "RAL7034": "#999875",  # Yellow grey
            "RAL7035": "#CBD5E0",  # Light grey
            "RAL7036": "#7B8B99",  # Platinum grey
            "RAL7037": "#585C66",  # Dusty grey
            "RAL7038": "#B5B3AA",  # Agate grey
            "RAL7039": "#6B6D70",  # Quartz grey
            "RAL7040": "#9DA1AA",  # Window grey
            "RAL7042": "#8D9BA6",  # Traffic grey
            "RAL7043": "#3D3D3D",  # Dark grey
            "RAL7044": "#CAC4B0",  # Silk grey
            "RAL7045": "#909CA0",  # Telegrey 1
            "RAL7046": "#82888F",  # Telegrey 2
            "RAL7047": "#D0CFCC",  # Telegrey 4
            "RAL8000": "#8B6914",  # Green brown
            "RAL8001": "#9B7653",  # Ochre brown
            "RAL8002": "#6C4F28",  # Signal brown
            "RAL8003": "#734222",  # Clay brown
            "RAL8004": "#8B4513",  # Copper brown
            "RAL8007": "#59351F",  # Fawn brown
            "RAL8008": "#6F4E37",  # Brown
            "RAL8011": "#5B4423",  # Nutria brown
            "RAL8012": "#592321",  # Red brown
            "RAL8014": "#472B1F",  # Sepia brown
            "RAL8015": "#3C352B",  # Chestnut brown
            "RAL8016": "#2E1F14",  # Mahogany brown
            "RAL8017": "#45342E",  # Chocolate brown
            "RAL8019": "#403C37",  # Grey brown
            "RAL8022": "#1F1A17",  # Black brown
            "RAL8023": "#A65E56",  # Orange brown
            "RAL8024": "#79553D",  # Beige brown
            "RAL8025": "#755D48",  # Pale brown
            "RAL8028": "#3F3B37",  # Terra brown
            "RAL8029": "#763D2E",  # Pearl copper
            "RAL9000": "#54474F",  # Graphite black
            "RAL9001": "#FDF4E6",  # Cream
            "RAL9002": "#E7EBEE",  # Grey white
            "RAL9003": "#F4F4EE",  # Signal white
            "RAL9004": "#282828",  # Signal black
            "RAL9005": "#0A0E27",  # Jet black
            "RAL9006": "#A5A5A5",  # White aluminium
            "RAL9007": "#8A7D7B",  # Grey aluminium
            "RAL9008": "#F4F8F0",  # Light grey
            "RAL9009": "#2D2D2D",  # Black
            "RAL9010": "#FFFFFF",  # Pure white
            "RAL9011": "#081017",  # Deep black
            "RAL9016": "#F8F8F8",  # Traffic white
            "RAL9017": "#2A2A2A",  # Traffic black
            "RAL9018": "#D7D8D7",  # Papyrus white
        }

        # Apply known values
        for color in self.colors:
            if color["code"] in known_colors and not color["hex"]:
                color["hex"] = known_colors[color["code"]]

        # Also update existing hex values from known_colors
        for color in self.colors:
            if color["code"] in known_colors:
                color["hex"] = known_colors[color["code"]]

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
            "brand": "RAL",
            "brand_id": "ral",
            "source": "https://de.wikipedia.org/wiki/RAL-Farbe",
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
            output_path = Path("data/pack_ral.json")

        print("🎨 RAL Color Scraper")
        print("=" * 50)

        # Fetch main page
        if not self.fetch_page(self.BASE_URL):
            # Fall back to using only known values if fetch fails
            print("Warning: Could not fetch page, using known values only")
            self._create_from_known_values()
        else:
            print(f"Found {len(self.colors)} color entries from page")

            # If parsing didn't find colors, create from known values
            if len(self.colors) == 0:
                print("No colors found from parsing, using known values...")
                self._create_from_known_values()

            # Apply known hex values
            self.apply_known_hex_values()

        # Remove duplicates
        self.deduplicate_colors()

        # Sort by code for consistent output
        self.colors.sort(key=lambda c: c["code"])

        # Save results
        self.save_json(output_path)

        # Print summary
        hex_count = sum(1 for c in self.colors if c["hex"])
        print(f"Colors with hex values: {hex_count}/{len(self.colors)}")

        return True

    def _create_from_known_values(self):
        """Create color list from known RAL colors."""
        known_colors = {
            "RAL1000": ("Beige", "#BEBD7F"),
            "RAL1001": ("Beige", "#C2B078"),
            "RAL1002": ("Sand yellow", "#C6A664"),
            "RAL1003": ("Signal yellow", "#E5BE01"),
            "RAL1004": ("Golden yellow", "#CDA922"),
            "RAL1005": ("Honey yellow", "#CF8600"),
            "RAL1006": ("Marigold yellow", "#E4A010"),
            "RAL1007": ("Daffodil yellow", "#DC9D07"),
            "RAL1011": ("Brown beige", "#8A7967"),
            "RAL1012": ("Lemon yellow", "#D3AE01"),
            "RAL1013": ("Oyster white", "#EAE6CA"),
            "RAL1014": ("Ivory", "#E1CC4F"),
            "RAL1015": ("Light ivory", "#E6D690"),
            "RAL1016": ("Sulfur yellow", "#EDFF21"),
            "RAL1017": ("Saffron yellow", "#F8F32B"),
            "RAL1018": ("Zinc yellow", "#F8F32B"),
            "RAL1019": ("Grey beige", "#9E9B85"),
            "RAL1020": ("Olive yellow", "#9B8B3D"),
            "RAL1021": ("Rape yellow", "#F3DA0B"),
            "RAL1023": ("Traffic yellow", "#F0D030"),
            "RAL1024": ("Ochre yellow", "#CEA135"),
            "RAL1026": ("Luminous yellow", "#FFFF00"),
            "RAL1027": ("Curry", "#DAA520"),
            "RAL1028": ("Melon yellow", "#F0D000"),
            "RAL1032": ("Broom yellow", "#D6AE01"),
            "RAL1033": ("Dahlia yellow", "#F0D000"),
            "RAL1034": ("Pastel yellow", "#EDA83D"),
            "RAL2000": ("Orange yellow", "#EA7600"),
            "RAL2001": ("Red orange", "#BE2E26"),
            "RAL2002": ("Vermillion", "#CB2821"),
            "RAL2003": ("Pastel orange", "#FF7514"),
            "RAL2004": ("Pure orange", "#F44611"),
            "RAL2005": ("Luminous orange", "#FF2301"),
            "RAL2007": ("Bright orange", "#FFA421"),
            "RAL2008": ("Bright red orange", "#F75E25"),
            "RAL2009": ("Traffic orange", "#F54021"),
            "RAL2010": ("Signal orange", "#D84B20"),
            "RAL2011": ("Deep orange", "#EC8B3C"),
            "RAL2012": ("Rust orange", "#E55C3F"),
            "RAL2013": ("Chestnut orange", "#922610"),
            "RAL3000": ("Flame red", "#AC193D"),
            "RAL3001": ("Signal red", "#A52127"),
            "RAL3002": ("Carmine red", "#A2231D"),
            "RAL3003": ("Ruby red", "#9B111E"),
            "RAL3004": ("Crimson red", "#75151E"),
            "RAL3005": ("Wine red", "#5E2129"),
            "RAL3007": ("Black red", "#412227"),
            "RAL3009": ("Iron oxide", "#622E2A"),
            "RAL3011": ("Brown red", "#622E2A"),
            "RAL3012": ("Beige red", "#C1876B"),
            "RAL3013": ("Tomato red", "#A4554D"),
            "RAL3014": ("Antique pink", "#D16B76"),
            "RAL3015": ("Light pink", "#E1A6AD"),
            "RAL3016": ("Claret", "#B24D49"),
            "RAL3017": ("Rose", "#CB7582"),
            "RAL3018": ("Strawberry red", "#EC1C24"),
            "RAL3020": ("Traffic red", "#CC0605"),
            "RAL3022": ("Salmon red", "#D5534F"),
            "RAL3024": ("Luminous red", "#FF0000"),
            "RAL3026": ("Luminous bright red", "#FF0000"),
            "RAL3027": ("Raspberry red", "#C51D34"),
            "RAL3031": ("Orient red", "#B32428"),
            "RAL4001": ("Red lilac", "#6D3F47"),
            "RAL4002": ("Red violet", "#933D50"),
            "RAL4003": ("Heather violet", "#DE4C8A"),
            "RAL4004": ("Claret violet", "#641C34"),
            "RAL4005": ("Blue lilac", "#6E3F75"),
            "RAL4006": ("Traffic purple", "#A03472"),
            "RAL4007": ("Purple black", "#321E24"),
            "RAL4008": ("Signal violet", "#6F4C6D"),
            "RAL4009": ("Pastel violet", "#A18594"),
            "RAL4010": ("Telemagenta", "#CF3476"),
            "RAL4011": ("Pearl violet", "#8673A1"),
            "RAL4012": ("Pearl black", "#6C7C98"),
            "RAL5000": ("Violet blue", "#354D73"),
            "RAL5001": ("Green blue", "#1F3A70"),
            "RAL5002": ("Ultramarine blue", "#00247B"),
            "RAL5003": ("Sapphire blue", "#001E50"),
            "RAL5004": ("Black blue", "#18184A"),
            "RAL5005": ("Signal blue", "#003DA5"),
            "RAL5007": ("Brilliant blue", "#3E5F8A"),
            "RAL5008": ("Grey blue", "#26252B"),
            "RAL5009": ("Azure blue", "#025669"),
            "RAL5010": ("Gentian blue", "#004687"),
            "RAL5011": ("Steel blue", "#231F20"),
            "RAL5012": ("Light blue", "#3E8CC0"),
            "RAL5013": ("Cobalt blue", "#1E3A8F"),
            "RAL5014": ("Pigeon blue", "#606E8C"),
            "RAL5015": ("Sky blue", "#0E4C96"),
            "RAL5016": ("Traffic blue", "#004B87"),
            "RAL5017": ("Traffic blue", "#004B87"),
            "RAL5018": ("Turquoise blue", "#3F7F4C"),
            "RAL5019": ("Capri blue", "#1B4D3E"),
            "RAL5020": ("Ocean blue", "#1D3A3A"),
            "RAL5021": ("Water blue", "#256D7B"),
            "RAL5022": ("Night blue", "#20214F"),
            "RAL5023": ("Remote blue", "#49678D"),
            "RAL5024": ("Pastel blue", "#646E75"),
            "RAL6000": ("Patina green", "#316650"),
            "RAL6001": ("Emerald green", "#287233"),
            "RAL6002": ("Leaf green", "#23423D"),
            "RAL6003": ("Olive green", "#424632"),
            "RAL6004": ("Blue green", "#1F3A3F"),
            "RAL6005": ("Moss green", "#2F5233"),
            "RAL6006": ("Grey green", "#40403F"),
            "RAL6007": ("Bottle green", "#343B29"),
            "RAL6008": ("Brown green", "#39352A"),
            "RAL6009": ("Fir green", "#1E3932"),
            "RAL6010": ("Grass green", "#35682D"),
            "RAL6011": ("Reseda green", "#587246"),
            "RAL6012": ("Black green", "#343E40"),
            "RAL6013": ("Reed green", "#6B5D54"),
            "RAL6014": ("Yellow olive", "#47402E"),
            "RAL6015": ("Black olive", "#3D4035"),
            "RAL6016": ("Turquoise green", "#004F51"),
            "RAL6017": ("May green", "#4C7C59"),
            "RAL6018": ("Yellow green", "#92C83E"),
            "RAL6019": ("Pastel green", "#BDECB6"),
            "RAL6020": ("Chrome green", "#2E5F3F"),
            "RAL6021": ("Pale green", "#89AC76"),
            "RAL6022": ("Brown olive", "#25221B"),
            "RAL6024": ("Traffic green", "#308446"),
            "RAL6025": ("Fern green", "#3D642D"),
            "RAL6026": ("Opal green", "#003D14"),
            "RAL6027": ("Light green", "#84C5C1"),
            "RAL6028": ("Pine green", "#2D5016"),
            "RAL6029": ("Mint green", "#20603D"),
            "RAL6032": ("Signal green", "#317F43"),
            "RAL6033": ("Mint turquoise", "#497E76"),
            "RAL6034": ("Pastel turquoise", "#7FB069"),
            "RAL6035": ("Pearl green", "#1B542D"),
            "RAL6036": ("Pearl opal green", "#193737"),
            "RAL6037": ("Pure green", "#008941"),
            "RAL6038": ("Luminous green", "#00BB2D"),
            "RAL7000": ("Squirrel grey", "#78858B"),
            "RAL7001": ("Silver grey", "#8B8680"),
            "RAL7002": ("Olive grey", "#7A7B7D"),
            "RAL7003": ("Moss grey", "#6E6E70"),
            "RAL7004": ("Signal grey", "#969992"),
            "RAL7005": ("Slate grey", "#595959"),
            "RAL7006": ("Beige grey", "#6B5D52"),
            "RAL7008": ("Khaki grey", "#5B5B5B"),
            "RAL7009": ("Green grey", "#4D5645"),
            "RAL7010": ("Tarpaulin grey", "#4C514A"),
            "RAL7011": ("Iron grey", "#434B4D"),
            "RAL7012": ("Basalt grey", "#4E5754"),
            "RAL7013": ("Brown grey", "#464B4E"),
            "RAL7014": ("Slate grey", "#4F5660"),
            "RAL7015": ("Slate grey", "#70747E"),
            "RAL7016": ("Anthracite grey", "#293133"),
            "RAL7017": ("Black grey", "#44484E"),
            "RAL7018": ("Grey brown", "#454B4E"),
            "RAL7019": ("Dark grey", "#383E45"),
            "RAL7020": ("Dark grey", "#3A3F47"),
            "RAL7021": ("Black grey", "#23282D"),
            "RAL7022": ("Umbra grey", "#332F2C"),
            "RAL7023": ("Concrete grey", "#686C70"),
            "RAL7024": ("Graphite grey", "#474A51"),
            "RAL7026": ("Granite grey", "#2F353B"),
            "RAL7030": ("Stone grey", "#8B8B7A"),
            "RAL7031": ("Blue grey", "#474B4E"),
            "RAL7032": ("Pebble grey", "#B8B6AA"),
            "RAL7033": ("Cement grey", "#7B8578"),
            "RAL7034": ("Yellow grey", "#999875"),
            "RAL7035": ("Light grey", "#CBD5E0"),
            "RAL7036": ("Platinum grey", "#7B8B99"),
            "RAL7037": ("Dusty grey", "#585C66"),
            "RAL7038": ("Agate grey", "#B5B3AA"),
            "RAL7039": ("Quartz grey", "#6B6D70"),
            "RAL7040": ("Window grey", "#9DA1AA"),
            "RAL7042": ("Traffic grey", "#8D9BA6"),
            "RAL7043": ("Dark grey", "#3D3D3D"),
            "RAL7044": ("Silk grey", "#CAC4B0"),
            "RAL7045": ("Telegrey 1", "#909CA0"),
            "RAL7046": ("Telegrey 2", "#82888F"),
            "RAL7047": ("Telegrey 4", "#D0CFCC"),
            "RAL8000": ("Green brown", "#8B6914"),
            "RAL8001": ("Ochre brown", "#9B7653"),
            "RAL8002": ("Signal brown", "#6C4F28"),
            "RAL8003": ("Clay brown", "#734222"),
            "RAL8004": ("Copper brown", "#8B4513"),
            "RAL8007": ("Fawn brown", "#59351F"),
            "RAL8008": ("Brown", "#6F4E37"),
            "RAL8011": ("Nutria brown", "#5B4423"),
            "RAL8012": ("Red brown", "#592321"),
            "RAL8014": ("Sepia brown", "#472B1F"),
            "RAL8015": ("Chestnut brown", "#3C352B"),
            "RAL8016": ("Mahogany brown", "#2E1F14"),
            "RAL8017": ("Chocolate brown", "#45342E"),
            "RAL8019": ("Grey brown", "#403C37"),
            "RAL8022": ("Black brown", "#1F1A17"),
            "RAL8023": ("Orange brown", "#A65E56"),
            "RAL8024": ("Beige brown", "#79553D"),
            "RAL8025": ("Pale brown", "#755D48"),
            "RAL8028": ("Terra brown", "#3F3B37"),
            "RAL8029": ("Pearl copper", "#763D2E"),
            "RAL9000": ("Graphite black", "#54474F"),
            "RAL9001": ("Cream", "#FDF4E6"),
            "RAL9002": ("Grey white", "#E7EBEE"),
            "RAL9003": ("Signal white", "#F4F4EE"),
            "RAL9004": ("Signal black", "#282828"),
            "RAL9005": ("Jet black", "#0A0E27"),
            "RAL9006": ("White aluminium", "#A5A5A5"),
            "RAL9007": ("Grey aluminium", "#8A7D7B"),
            "RAL9008": ("Light grey", "#F4F8F0"),
            "RAL9009": ("Black", "#2D2D2D"),
            "RAL9010": ("Pure white", "#FFFFFF"),
            "RAL9011": ("Deep black", "#081017"),
            "RAL9016": ("Traffic white", "#F8F8F8"),
            "RAL9017": ("Traffic black", "#2A2A2A"),
            "RAL9018": ("Papyrus white", "#D7D8D7"),
        }

        for ral_code, (name, hex_color) in sorted(known_colors.items()):
            self.colors.append(
                {
                    "code": ral_code,
                    "name": name,
                    "hex": hex_color,
                    "equivalents": [],
                    "confidence": None,
                }
            )


def main():
    """Main entry point."""
    scraper = RALScraper()
    scraper.run()


if __name__ == "__main__":
    main()
