# Color Parsing Pipeline Documentation

## Project Structure

### `/source/` — Parsing Scripts
Organized by brand/producer:

- **`source/ammo/`** — Ammo by Mig parsers
  - `ocr_ammo.py` — Legacy OCR extractor
  - `parse_ammo_ocr.py` — Legacy parser
  
- **`source/ammo-atom/`** — Ammo by Mig Atom (new)
  - `parse_ammo_atom.py` — Table-based OCR parser
  - Images: `01.png`, `02.png`, `03.png`
  
- **`source/ak/`** — AK Interactive (new)
  - `parse_ak.py` — Grid detection + OCR parser
  - Images: Screenshots from catalog
  
- **`source/gunze/`** — Gunze Sangyo
  - `parse_gunze.py` — Grid detection, swatch extraction, OCR
  - Images: `01.png`, `02.png`, `03.png`
  
- **`source/mr_hobby/`** — Mr. Hobby (new)
  - `parse_mr_hobby.py` — Grid-based swatch + OCR parser
  - Features: Extracts color number (with "C" prefix), name, hex
  - Images: `01.png`, `02.png`
  
- **`source/common/`** — Shared utilities
  - `parse_rows.py` — OCR → row clustering
  - `extract_catalog.py` — Data extraction
  - `resolve_definitions.py` — Equivalence resolution
  - `create_equivalents.py` — Cross-brand linking
  - `format_frontend.py` — Format output for UI
  
### `/data/` — Data Organization

```
data/
├── results/             ✅ Final output for frontend
│   ├── pack_ammo.json
│   ├── pack_ammo_atom.json    (new)
│   ├── pack_ak.json            (new)
│   ├── pack_gunze.json
│   └── pack_mr_hobby.json      (new)
│
├── temp/                🔧 Intermediate parsing outputs
│   ├── ammo_rows.json     (OCR extracted rows)
│   ├── ammo_rows.csv
│   ├── gunze_rows.json    (OCR + swatch data)
│   ├── gunze_rows.csv
│   └── [other intermediate files]
│
└── [symlinks]           🔗 Convenience links
    ├── pack_ammo.json → results/pack_ammo.json
    ├── pack_ammo_atom.json → results/pack_ammo_atom.json (new)
    ├── pack_ak.json → results/pack_ak.json (new)
    ├── pack_gunze.json → results/pack_gunze.json
    └── pack_mr_hobby.json → results/pack_mr_hobby.json (new)
```

## Parser Output Format

### Raw Parser Output
Simple JSON with color data:
```json
[
  {"code": "C1", "name": "White", "hex": "#f5f5f5"},
  {"code": "C2", "name": "Black", "hex": "#1a1a1a"}
]
```

### Frontend Format (`pack_*.json`)
Full metadata for UI:
```json
{
  "brand": "Mr. Hobby",
  "brand_id": "mr_hobby",
  "source": "data/results/pack_mr_hobby.json",
  "count": 171,
  "colors": [
    {
      "code": "C1",
      "name": "White",
      "hex": "#f5f5f5",
      "equivalents": [],
      "confidence": null
    }
  ]
}
```

## Running the Pipeline

### Option 1: Master Pipeline Script
```bash
python3 scripts/run_pipeline.py
```
Runs all parsers sequentially and formats output.

### Option 2: Individual Parsers
```bash
# Mr. Hobby
python3 source/mr_hobby/parse_mr_hobby.py

# Ammo-Atom
python3 source/ammo-atom/parse_ammo_atom.py

# AK Interactive
python3 source/ak/parse_ak.py

# Gunze Sangyo
python3 source/gunze/parse_gunze.py
```

## Parsing Methods by Producer

| Producer | Method | Notes |
|----------|--------|-------|
| Mr. Hobby | Grid + OCR | Color number in black box (C prefix added), name at bottom left |
| Ammo-Atom | Table OCR | Similar to Ammo, ATOM- prefixed codes |
| AK Interactive | Grid detection | AK codes with color swatches |
| Gunze Sangyo | Swatch clustering + OCR | K-means color detection, blue border filtering |
| Ammo by Mig | Table OCR | Row clustering, column assignment |

## Frontend Integration

### Supported Brands (index.html)
- Ammo by Mig
- Ammo by Mig Atom ✨ (new)
- Gunze Sangyo
- AK Interactive ✨ (new)
- Mr. Hobby ✨ (new)

### Brand ID Mapping (script.js)
- `ammo_by_mig` → `pack_ammo_by_mig.json`
- `ammo_atom` → `pack_ammo_atom.json` (new)
- `ak_interactive` → `pack_ak.json` (new)
- `gunze` → `pack_gunze.json`
- `mr_hobby` → `pack_mr_hobby.json` (new)

## Key Features of New Parsers

### Mr. Hobby Parser (`parse_mr_hobby.py`)
- ✅ Grid cell detection using k-means clustering
- ✅ OCR number extraction with "C" prefix addition
- ✅ Color name extraction from bottom corners
- ✅ Color swatch analysis for hex extraction
- ✅ Handles multiple image pages

### Ammo-Atom Parser (`parse_ammo_atom.py`)
- ✅ Table structure detection
- ✅ Header-based column assignment
- ✅ ATOM- code normalization
- ✅ Deduplication
- ✅ Reuses Ammo layout logic

### AK Interactive Parser (`parse_ak.py`)
- ✅ Row-based OCR clustering
- ✅ AK code detection (AKXXXX pattern)
- ✅ Swatch color extraction
- ✅ Row grouping for color assignment
- ✅ Hex color generation from swatches

## Dependencies

All parsers require:
- `easyocr` — OCR text extraction
- `pillow` — Image processing
- `opencv-python` — Computer vision (swatch detection, k-means)
- `numpy` — Array operations

Install:
```bash
pip install easyocr pillow opencv-python numpy
```

## Future Improvements

- [ ] Add color equivalence linking between brands
- [ ] Improve hex color extraction accuracy
- [ ] Add batch optimization to parser pipeline
- [ ] Cache OCR results to speed up re-runs
- [ ] Support additional producers (Vallejo, Citadel, etc.)
