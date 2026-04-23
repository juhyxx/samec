#!/usr/bin/env python3
"""
Parse Hataka ColorSpace colour chart (2019 edition).

Two-page PDF:
  Page 1 – CROSS-REFERENCE TABLE  (FS, ANA, RAL, BS, RLM, Humbrol, Mr.Hobby,
                                    Tamiya, Testors, Vallejo Air, Xtracolor)
  Page 2 – Colour swatches with HTK codes and names

Workflow:
  1. Extract PDF pages to .tmp/ at 300 DPI.
  2. Parse page-1 cross-reference tables via pdfplumber.
  3. Parse page-2 swatches: character positions → swatch bbox → average colour,
     names extracted from the text directly below each code.
  4. Merge and emit data/pack_hataka.json + data/pack_hataka.csv.
"""

from __future__ import annotations

import csv
import json
import re
from pathlib import Path
from typing import Any

import numpy as np
import pdfplumber
from pdf2image import convert_from_path
from PIL import Image

# ---------------------------------------------------------------------------
# Paths
# ---------------------------------------------------------------------------
HATAKA_FOLDER = Path("source/hataka")
PDF_NAME = "Hataka Hobby colour chart & x-ref table 2019_light.pdf"
TMP_FOLDER = Path(".tmp")
OUT_JSON = Path("data/pack_hataka.json")
OUT_CSV = Path("data/pack_hataka.csv")

# ---------------------------------------------------------------------------
# PDF → image scaling constants (300 DPI)
# ---------------------------------------------------------------------------
PDF_DPI = 300
# Actual page dimensions in PDF points (measured from pdfplumber):
PDF_W_PT = 1964.41
PDF_H_PT = 595.276

# ---------------------------------------------------------------------------
# Cross-reference column metadata
# Index matches the table column order.
# ---------------------------------------------------------------------------
XREF_COLUMNS = [
    None,  # 0 → Product ID (our key)
    {"brand": "Federal Standard", "prefix": "FS "},  # 1 → FS
    {"brand": "ANA", "prefix": ""},  # 2 → ANA
    {"brand": "RAL", "prefix": "RAL "},  # 3 → RAL
    {"brand": "British Standard", "prefix": ""},  # 4 → BS
    {"brand": "RLM", "prefix": "RLM-"},  # 5 → RLM
    {"brand": "Humbrol", "prefix": ""},  # 6 → Humbrol
    {"brand": "Gunze Sangyo", "prefix": ""},  # 7 → Mr.Hobby Aqueous
    {"brand": "Tamiya", "prefix": ""},  # 8 → Tamiya
    {"brand": "Testors", "prefix": ""},  # 9 → Testors (Model Master)
    {"brand": "Vallejo", "prefix": ""},  # 10 → Vallejo Air
    {"brand": "Xtracolor", "prefix": ""},  # 11 → Xtracolor
]

# Indices of the cross-reference tables within page 1 (0-indexed).
# Found by inspecting pdfplumber.find_tables(); tables 3/4/6 are layout boxes.
XREF_TABLE_INDICES = [5, 0, 1, 2]  # ordered left→right, top→bottom


# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------


def rgb_to_hex(r: float, g: float, b: float) -> str:
    return "#{:02x}{:02x}{:02x}".format(int(r), int(g), int(b))


def normalise_code(raw: str) -> str:
    """Strip whitespace/dash variants; keep the HTK-_NNN shape."""
    return raw.strip()


def _clean_cell(value: str | None) -> list[str]:
    """Split a pdfplumber cell (possibly multi-line) into non-empty tokens."""
    if not value:
        return []
    parts = [p.strip() for p in value.split("\n")]
    return [p for p in parts if p and p != "-"]


def _make_equivalent(brand_meta: dict, raw_code: str) -> dict | None:
    """
    Build an equivalents entry for a given column's raw code string.
    Returns None if the code looks empty or placeholder ('-').
    """
    code = raw_code.strip()
    if not code or code == "-":
        return None

    prefix = brand_meta["prefix"]
    brand = brand_meta["brand"]

    # Strip leading brand prefix if already present in the cell text
    if brand == "Federal Standard":
        # Cells contain e.g. "FS15042"; normalise to "FS 15042"
        m = re.match(r"^FS\s*(\d+)$", code, re.IGNORECASE)
        if m:
            return {"brand": brand, "code": f"FS {m.group(1)}"}
        return None

    if brand == "ANA":
        # Cells contain e.g. "ANA 606" or "ANA606"
        m = re.match(r"^ANA\s*(\d+)$", code, re.IGNORECASE)
        if m:
            return {"brand": brand, "code": f"ANA {m.group(1)}"}
        return None

    if brand == "RAL":
        # Cells contain plain 4-digit number like "7009"
        m = re.match(r"^(\d{4})$", code)
        if m:
            return {"brand": brand, "code": f"RAL {m.group(1)}"}
        # Or already "RAL XXXX"
        m = re.match(r"^RAL\s*(\d{4})$", code, re.IGNORECASE)
        if m:
            return {"brand": brand, "code": f"RAL {m.group(1)}"}
        return None

    if brand == "British Standard":
        # Cells contain e.g. "BS381C:356" or plain numbers
        if code:
            return {"brand": brand, "code": code}
        return None

    if brand == "RLM":
        # Cells contain e.g. "RLM 01", "RLM 75" or plain "01"
        m = re.match(r"^RLM\s*(\d+)$", code, re.IGNORECASE)
        if m:
            return {"brand": brand, "code": f"RLM-{m.group(1)}"}
        m = re.match(r"^(\d+)$", code)
        if m:
            return {"brand": brand, "code": f"RLM-{m.group(1)}"}
        return None

    if brand == "Humbrol":
        # Plain numbers like "181", "29", "144"
        m = re.match(r"^(\d+)$", code)
        if m:
            return {"brand": brand, "code": m.group(1)}
        return None

    if brand == "Gunze Sangyo":
        # H-codes like "H55", "H421"
        m = re.match(r"^H(\d+)$", code)
        if m:
            return {"brand": brand, "code": f"H{m.group(1)}"}
        # Also handles slash variants like "H315/\nH325" (already split by caller)
        return None

    if brand == "Tamiya":
        # XF codes, X codes (1-2 digit), LP codes
        m = re.match(r"^(XF|X|LP)(\d{1,3})$", code)
        if m:
            return {"brand": brand, "code": f"{m.group(1)}{m.group(2)}"}
        return None

    if brand == "Testors":
        # 4-digit model master codes like "1740"
        m = re.match(r"^(\d{4})$", code)
        if m:
            return {"brand": brand, "code": m.group(1)}
        return None

    if brand == "Vallejo":
        # "71.277", "71.264" etc.
        m = re.match(r"^(\d{2}\.\d{3})$", code)
        if m:
            return {"brand": brand, "code": m.group(1)}
        return None

    if brand == "Xtracolor":
        # X + 3 digits like "X121"
        m = re.match(r"^X(\d+)$", code)
        if m:
            return {"brand": brand, "code": f"X{m.group(1)}"}
        return None

    # Generic fallback
    if prefix and not code.startswith(prefix):
        return {"brand": brand, "code": f"{prefix}{code}"}
    return {"brand": brand, "code": code}


# ---------------------------------------------------------------------------
# Page 1 – cross-reference table parsing
# ---------------------------------------------------------------------------


def parse_xref_tables(pdf_path: Path) -> dict[str, list[dict]]:
    """
    Return a mapping of HTK code → list of equivalents dicts.
    Each equivalent dict: {"brand": str, "code": str}
    """
    equivalents: dict[str, list[dict]] = {}

    with pdfplumber.open(str(pdf_path)) as pdf:
        page = pdf.pages[0]
        tables = page.find_tables()

        for tbl_idx in XREF_TABLE_INDICES:
            if tbl_idx >= len(tables):
                continue
            rows = tables[tbl_idx].extract()
            if not rows:
                continue

            # Skip header row(s) – rows whose first cell is "Product ID"
            data_rows = [r for r in rows if r and r[0] != "Product ID"]

            for row in data_rows:
                if not row or not row[0]:
                    continue

                # Multiple codes can be packed into a single cell (newline-sep)
                codes = _clean_cell(row[0])
                if not codes:
                    continue

                # For each column, split by newline to get per-code values
                col_values: list[list[str]] = []
                for col_i, cell in enumerate(row):
                    if col_i == 0:
                        col_values.append(codes)
                    else:
                        col_values.append(_clean_cell(cell))

                for code_idx, htk_code in enumerate(codes):
                    htk_code = normalise_code(htk_code)
                    if not htk_code:
                        continue

                    equivs: list[dict] = []
                    for col_i in range(1, len(XREF_COLUMNS)):
                        meta = XREF_COLUMNS[col_i]
                        if meta is None:
                            continue
                        col_vals = col_values[col_i] if col_i < len(col_values) else []
                        # Pick the value for this code_idx (or the last available)
                        raw = (
                            col_vals[code_idx]
                            if code_idx < len(col_vals)
                            else (col_vals[-1] if col_vals else "")
                        )
                        if not raw or raw == "-":
                            continue
                        # Cells can contain slash-separated alternatives
                        sub_codes = [
                            s.strip() for s in re.split(r"[/\\]", raw) if s.strip()
                        ]
                        for sc in sub_codes:
                            entry = _make_equivalent(meta, sc)
                            if entry:
                                equivs.append(entry)

                    if htk_code not in equivalents:
                        equivalents[htk_code] = equivs
                    else:
                        # Merge without duplicates
                        existing_set = {
                            (e["brand"], e["code"]) for e in equivalents[htk_code]
                        }
                        for e in equivs:
                            if (e["brand"], e["code"]) not in existing_set:
                                equivalents[htk_code].append(e)
                                existing_set.add((e["brand"], e["code"]))

    return equivalents


# ---------------------------------------------------------------------------
# Page 2 – swatch colour + name parsing
# ---------------------------------------------------------------------------

_HTK_CODE_RE = re.compile(r"HTK-_\d{3,}", re.IGNORECASE)
_BOLD_FONT_FRAGMENT = "Canaro-Bold"
_INLINE_EQUIV_PATTERN = re.compile(
    r"(?:FS\d+|ANA\s*\d+|RLM\s*\d+|RAL\s*\d+|BS\s*\S+|"
    r"(?:XF|X|LP)\d+|H\d+|7[01]\.\d{3}|X\d{3,}|\d{4,5})"
)


def _chars_to_tokens(chars: list[dict]) -> list[dict]:
    """
    Merge adjacent chars (same y-line, same font) into token strings.
    Returns list of {text, x0, x1, top, bottom, bold}.
    """
    if not chars:
        return []

    tokens: list[dict] = []
    cur_chars: list[dict] = []

    def flush():
        if not cur_chars:
            return
        text = "".join(c["text"] for c in cur_chars)
        tokens.append(
            {
                "text": text,
                "x0": cur_chars[0]["x0"],
                "x1": cur_chars[-1]["x1"],
                "top": min(c["top"] for c in cur_chars),
                "bottom": max(c["bottom"] for c in cur_chars),
                "bold": _BOLD_FONT_FRAGMENT in (cur_chars[0].get("fontname") or ""),
            }
        )
        cur_chars.clear()

    for c in chars:
        if not c.get("text", "").strip():
            # Space character – acts as word separator; flush if same context
            if cur_chars:
                last = cur_chars[-1]
                if abs(c["top"] - last["top"]) < 1.0 and (
                    _BOLD_FONT_FRAGMENT in (c.get("fontname") or "")
                ) == (_BOLD_FONT_FRAGMENT in (last.get("fontname") or "")):
                    flush()
            continue

        if not cur_chars:
            cur_chars.append(c)
            continue

        last = cur_chars[-1]
        same_line = abs(c["top"] - last["top"]) < 1.0
        same_font_boldness = (_BOLD_FONT_FRAGMENT in (c.get("fontname") or "")) == (
            _BOLD_FONT_FRAGMENT in (last.get("fontname") or "")
        )
        gap = c["x0"] - last["x1"]

        # Merge if: moving rightward (prevents wrap-around), small gap
        if same_line and same_font_boldness and c["x0"] > last["x0"] and gap < 5.0:
            cur_chars.append(c)
        else:
            flush()
            cur_chars.append(c)

    flush()
    return tokens


def _parse_inline_equivalents(text_after_code: str) -> list[dict]:
    """
    Parse equivalents embedded on the same line as the HTK code on page 2:
    e.g. "FS15042, ANA 623" → [{"brand": "Federal Standard", "code": "FS 15042"}, ...]
    These are used as a supplementary source; the cross-reference table
    is the primary source.
    """
    equivs: list[dict] = []
    for m in _INLINE_EQUIV_PATTERN.finditer(text_after_code):
        raw = m.group(0).strip().rstrip(",")
        if re.match(r"^FS\s*(\d+)$", raw, re.I):
            num = re.sub(r"^FS\s*", "", raw, flags=re.I)
            equivs.append({"brand": "Federal Standard", "code": f"FS {num}"})
        elif re.match(r"^ANA\s*(\d+)$", raw, re.I):
            num = re.sub(r"^ANA\s*", "", raw, flags=re.I)
            equivs.append({"brand": "ANA", "code": f"ANA {num}"})
        elif re.match(r"^RLM\s*(\d+)$", raw, re.I):
            num = re.sub(r"^RLM\s*", "", raw, flags=re.I)
            equivs.append({"brand": "RLM", "code": f"RLM-{num}"})
        elif re.match(r"^RAL\s*(\d+)$", raw, re.I):
            num = re.sub(r"^RAL\s*", "", raw, flags=re.I)
            equivs.append({"brand": "RAL", "code": f"RAL {num}"})
        elif re.match(r"^BS\s*\S+$", raw, re.I):
            equivs.append({"brand": "British Standard", "code": raw})
    return equivs


def _sample_swatch_color(
    img_arr: np.ndarray,
    x0_pdf: float,
    x1_pdf: float,
    y0_pdf: float,
    y1_pdf: float,
    scale_x: float,
    scale_y: float,
) -> str:
    """Sample the average colour of a swatch region and return hex."""
    img_h, img_w = img_arr.shape[:2]

    ix0 = max(0, int(x0_pdf * scale_x) + 2)
    ix1 = min(img_w, int(x1_pdf * scale_x) - 2)
    iy0 = max(0, int(y0_pdf * scale_y) + 2)
    iy1 = min(img_h, int(y1_pdf * scale_y) - 2)

    if ix1 <= ix0 or iy1 <= iy0:
        return "#000000"

    region = img_arr[iy0:iy1, ix0:ix1]
    avg = region.reshape(-1, 3).mean(axis=0)
    return rgb_to_hex(*avg)


def parse_swatch_page(
    pdf_path: Path,
    img_page2: Image.Image,
) -> dict[str, dict[str, Any]]:
    """
    Parse page 2 of the PDF.

    Returns mapping: htk_code → {"hex": str, "name": str, "inline_equivs": list}
    """
    img_arr = np.array(img_page2.convert("RGB"))
    img_h, img_w = img_arr.shape[:2]
    scale_x = img_w / PDF_W_PT
    scale_y = img_h / PDF_H_PT

    with pdfplumber.open(str(pdf_path)) as pdf:
        page = pdf.pages[1]
        chars = page.chars

    if not chars:
        return {}

    # Sort chars by (top, x0) for orderly processing
    chars = sorted(chars, key=lambda c: (round(c["top"], 1), c["x0"]))
    tokens = _chars_to_tokens(chars)

    # Cluster tokens into rows by y-position
    row_map: dict[float, list[dict]] = {}
    for tok in tokens:
        y_key = round(tok["top"], 0)
        row_map.setdefault(y_key, []).append(tok)

    # Identify rows that carry HTK codes (bold font, contain HTK pattern)
    code_rows: list[float] = sorted(
        y
        for y, toks in row_map.items()
        if any(tok["bold"] and _HTK_CODE_RE.search(tok["text"]) for tok in toks)
    )

    result: dict[str, dict[str, Any]] = {}

    for row_i, code_y in enumerate(code_rows):
        code_toks = row_map[code_y]

        # Determine the y-range for the swatch (above the code text)
        if row_i == 0:
            swatch_y0 = 1.0
        else:
            prev_name_y = code_rows[row_i - 1] + 7.0  # approx. bottom of name row
            swatch_y0 = prev_name_y + 1.0

        swatch_y1 = code_y - 2.0  # a small gap between swatch and code text

        # Find the name row (first non-bold row just below this code row)
        name_y_candidates = [y for y in row_map if y > code_y and y < code_y + 12.0]
        name_y = max(name_y_candidates) if name_y_candidates else None

        # Build a list of (x_code, code_str, inline_equiv_text, width_of_swatch)
        # within this row. Group contiguous bold tokens.
        htk_entries: list[tuple[float, str]] = []
        for tok in code_toks:
            if tok["bold"] and _HTK_CODE_RE.search(tok["text"]):
                htk_entries.append((tok["x0"], tok["text"].strip()))

        # Sort by x so we can determine widths
        htk_entries.sort()

        # Determine swatch x-ranges
        for j, (x_code, code_str) in enumerate(htk_entries):
            # Right boundary: start of next code in same row (or +65 PDF units)
            if j + 1 < len(htk_entries):
                x_right = htk_entries[j + 1][0] - 0.5
            else:
                x_right = x_code + 65.0  # approx swatch width

            # Sample swatch colour
            hex_color = _sample_swatch_color(
                img_arr, x_code, x_right, swatch_y0, swatch_y1, scale_x, scale_y
            )

            # Extract name for this code position
            name = ""
            if name_y is not None:
                name_toks = [
                    t
                    for t in row_map[name_y]
                    if t["x0"] >= x_code - 2.0 and t["x0"] < x_right
                ]
                name = " ".join(
                    t["text"] for t in sorted(name_toks, key=lambda t: t["x0"])
                )

            # Extract inline equivalents (non-bold text on same code row)
            inline_text = " ".join(
                t["text"]
                for t in code_toks
                if not t["bold"] and t["x0"] >= x_code - 1.0 and t["x0"] < x_right + 5.0
            )
            inline_equivs = _parse_inline_equivalents(inline_text)

            result[code_str] = {
                "hex": hex_color,
                "name": name.strip(),
                "inline_equivs": inline_equivs,
            }

    return result


# ---------------------------------------------------------------------------
# Main entry point
# ---------------------------------------------------------------------------


def parse_hataka_images(
    source_dir: Path = HATAKA_FOLDER,
    output_file: Path = OUT_JSON,
) -> list[dict]:
    """
    Full pipeline. Returns list of colour dicts (standard format).
    """
    pdf_path = source_dir / PDF_NAME
    if not pdf_path.exists():
        raise FileNotFoundError(f"PDF not found: {pdf_path}")

    # ------------------------------------------------------------------
    # Step 1 – Extract PDF pages to .tmp/ at 300 DPI
    # ------------------------------------------------------------------
    TMP_FOLDER.mkdir(exist_ok=True)
    page_paths = [
        TMP_FOLDER / "hataka_page_1.png",
        TMP_FOLDER / "hataka_page_2.png",
    ]
    if not all(p.exists() for p in page_paths):
        print(f"  Extracting PDF at {PDF_DPI} DPI → {TMP_FOLDER}/")
        pages = convert_from_path(str(pdf_path), dpi=PDF_DPI)
        for i, page_img in enumerate(pages):
            page_img.save(str(TMP_FOLDER / f"hataka_page_{i + 1}.png"))
    else:
        print(f"  Using cached page images in {TMP_FOLDER}/")

    img_page2 = Image.open(str(page_paths[1]))

    # ------------------------------------------------------------------
    # Step 2 – Parse cross-reference table (page 1)
    # ------------------------------------------------------------------
    print("  Parsing cross-reference table …")
    xref = parse_xref_tables(pdf_path)
    print(f"    {len(xref)} codes with equivalents")

    # ------------------------------------------------------------------
    # Step 3 – Parse swatch page (page 2)
    # ------------------------------------------------------------------
    print("  Parsing colour swatches …")
    swatches = parse_swatch_page(pdf_path, img_page2)
    print(f"    {len(swatches)} swatches detected")

    # ------------------------------------------------------------------
    # Step 4 – Merge
    # ------------------------------------------------------------------
    all_codes = sorted(
        set(xref.keys()) | set(swatches.keys()),
        key=lambda c: int(re.search(r"\d+", c).group()) if re.search(r"\d+", c) else 0,
    )

    colors: list[dict] = []
    for code in all_codes:
        swatch = swatches.get(code, {})
        equiv_from_xref = xref.get(code, [])
        equiv_inline = swatch.get("inline_equivs", [])

        # Merge equivalents: xref is primary, inline fills gaps
        combined_equivs = list(equiv_from_xref)
        existing_keys = {(e["brand"], e["code"]) for e in combined_equivs}
        for e in equiv_inline:
            if (e["brand"], e["code"]) not in existing_keys:
                combined_equivs.append(e)
                existing_keys.add((e["brand"], e["code"]))

        colors.append(
            {
                "code": code,
                "name": swatch.get("name", ""),
                "hex": swatch.get("hex", ""),
                "equivalents": combined_equivs,
            }
        )

    # ------------------------------------------------------------------
    # Step 5 – Write CSV
    # ------------------------------------------------------------------
    out_path = Path(output_file)
    out_path.parent.mkdir(parents=True, exist_ok=True)

    csv_path = out_path.with_suffix(".csv")
    with open(csv_path, "w", newline="", encoding="utf-8") as f:
        writer = csv.DictWriter(f, fieldnames=["code", "name", "hex", "equivalents"])
        writer.writeheader()
        for c in colors:
            writer.writerow(
                {
                    "code": c["code"],
                    "name": c["name"],
                    "hex": c["hex"],
                    "equivalents": json.dumps(c["equivalents"], ensure_ascii=False),
                }
            )

    return colors


if __name__ == "__main__":
    colors = parse_hataka_images()
    print(f"\nHataka: {len(colors)} colours parsed")
    for c in colors[:5]:
        print(f"  {c['code']:12s}  {c['hex']}  {c['name']}")
