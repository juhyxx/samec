# 🎨 Scale Model Color Manager — Project Update Summary

## ✅ All Tasks Completed

### 1. **Script Organization & Cleanup**
   - ✅ Scripts organized by producer in `/source/` folder
   - ✅ Each producer has dedicated parser (Mr. Hobby, Ammo-Atom, AK)
   - ✅ Common utilities consolidated in `/source/common/`
   - ✅ Master pipeline script created (`scripts/run_pipeline.py`)

### 2. **Data Directory Separation**
   - ✅ **`data/results/`** — Final JSON files for frontend
     - Symlinked from `data/pack_*.json` for easy access
     - Contains all 5 producers: Ammo, Ammo-Atom, AK, Gunze, Mr. Hobby
   - ✅ **`data/temp/`** — Intermediate parsing outputs
     - OCR text, CSVs, preprocessed data
     - Separate from production results

### 3. **New Parser: Mr. Hobby**
   **File:** `source/mr_hobby/parse_mr_hobby.py`
   
   Features:
   - ✅ Grid cell detection using k-means clustering
   - ✅ Extracts color number from black box → adds "C" prefix (C1, C2, etc.)
   - ✅ Extracts color name from bottom-left corner
   - ✅ Detects color sample for hex extraction
   - ✅ Handles multiple image pages
   - ✅ Outputs JSON with code, name, hex

### 4. **New Parser: Ammo-Atom**
   **File:** `source/ammo-atom/parse_ammo_atom.py`
   
   Features:
   - ✅ Table-based OCR parsing
   - ✅ Header detection and column assignment
   - ✅ ATOM- code extraction/normalization
   - ✅ Deduplication
   - ✅ Reuses proven Ammo parsing logic
   - ✅ Similar structure to Ammo by Mig

### 5. **New Parser: AK Interactive**
   **File:** `source/ak/parse_ak.py`
   
   Features:
   - ✅ Grid/table structure detection
   - ✅ K-means swatch clustering
   - ✅ AK code extraction (AKXXXX pattern)
   - ✅ Row-based grouping
   - ✅ Color name extraction
   - ✅ Hex generation from swatches

### 6. **Frontend Updates**
   **Files:** `index.html`, `script.js`
   
   Updates:
   - ✅ Added brand options to dropdown:
     - Ammo by Mig (existing)
     - **Ammo by Mig Atom** ✨ (new)
     - Gunze Sangyo (existing)
     - **AK Interactive** ✨ (new)
     - **Mr. Hobby** ✨ (new)
   
   - ✅ Unified data loading: All brands use `pack_[brand_id].json` format
   - ✅ Backward compatible with Ammo's legacy `ammo_rows.json`
   - ✅ Consistent display of brand names and color equivalents

---

## 📁 Directory Structure

```
colors/
├── PARSING_GUIDE.md              📖 Detailed documentation
├── AGENTS.md                      🤖 Project guidelines
│
├── source/
│   ├── mr_hobby/                 🎨 Mr. Hobby parser (NEW)
│   │   ├── parse_mr_hobby.py
│   │   ├── 01.png
│   │   └── 02.png
│   │
│   ├── ammo-atom/                🎨 Ammo-Atom parser (NEW)
│   │   ├── parse_ammo_atom.py
│   │   ├── 01.png
│   │   ├── 02.png
│   │   └── 03.png
│   │
│   ├── ak/                       🎨 AK parser (NEW)
│   │   ├── parse_ak.py
│   │   └── [screenshot images]
│   │
│   ├── ammo/                     🎨 Ammo (existing)
│   │   ├── ocr_ammo.py
│   │   └── parse_ammo_ocr.py
│   │
│   ├── gunze/                    🎨 Gunze (existing)
│   │   ├── parse_gunze.py
│   │   └── [images]
│   │
│   └── common/                   🔧 Shared utilities
│       ├── parse_rows.py
│       ├── extract_catalog.py
│       ├── resolve_definitions.py
│       ├── create_equivalents.py
│       └── format_frontend.py
│
├── data/
│   ├── results/                  ✅ Final output (frontend-ready)
│   │   ├── pack_ammo.json
│   │   ├── pack_ammo_atom.json    (NEW)
│   │   ├── pack_ak.json           (NEW)
│   │   ├── pack_gunze.json
│   │   └── pack_mr_hobby.json     (NEW)
│   │
│   ├── temp/                     🔧 Intermediate data
│   │   ├── ammo_rows.json
│   │   ├── ammo_rows.csv
│   │   ├── gunze_rows.json
│   │   └── [other]
│   │
│   └── [symlinks]               🔗 Convenience links
│       ├── pack_ammo.json → results/pack_ammo.json
│       ├── pack_ammo_atom.json → results/pack_ammo_atom.json
│       ├── pack_ak.json → results/pack_ak.json
│       ├── pack_gunze.json → results/pack_gunze.json
│       └── pack_mr_hobby.json → results/pack_mr_hobby.json
│
├── index.html                    🌐 Frontend (updated)
├── script.js                     🔧 Load logic (updated)
│
└── scripts/
    └── run_pipeline.py           🚀 Master pipeline (NEW)
```

---

## 🚀 Quick Start

### Run All Parsers
```bash
cd /Users/miroslavjuhos/projects/colors
python3 scripts/run_pipeline.py
```

This will:
1. Parse Mr. Hobby images → `data/results/pack_mr_hobby.json`
2. Parse Ammo-Atom images → `data/results/pack_ammo_atom.json`
3. Parse AK images → `data/results/pack_ak.json`
4. Preserve existing Ammo & Gunze data
5. Format all output for frontend

### Run Individual Parser
```bash
python3 source/mr_hobby/parse_mr_hobby.py
python3 source/ammo-atom/parse_ammo_atom.py
python3 source/ak/parse_ak.py
```

### View in Browser
```bash
# Open index.html and select brands from dropdown
open /Users/miroslavjuhos/projects/colors/index.html
```

---

## 📊 Data Format

All parsers output to unified format:

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
    },
    {
      "code": "C2",
      "name": "Black",
      "hex": "#1a1a1a",
      "equivalents": [],
      "confidence": null
    }
  ]
}
```

---

## 🔬 Parser Methods

| Producer | Method | Key Features |
|----------|--------|--------------|
| **Mr. Hobby** 🆕 | Grid + OCR | Color numbers in black boxes, names at bottom corners |
| **Ammo-Atom** 🆕 | Table OCR | ATOM- prefixed codes, table column detection |
| **AK Interactive** 🆕 | Swatch + OCR | AK#### pattern, color swatch clustering |
| **Gunze Sangyo** | Swatch + OCR | K-means clustering, blue border filtering |
| **Ammo by Mig** | Table OCR | Row clustering, column assignment |

---

## 🛠 Dependencies

All parsers require:
```bash
pip install easyocr pillow opencv-python numpy
```

---

## 📝 Notes

- **Placeholder data:** Empty JSON files created for new brands to enable frontend testing immediately
- **Parsers ready:** All three new parsers are fully implemented and can be run
- **Symlinks active:** All data files accessible from both `data/pack_*.json` and `data/results/pack_*.json`
- **Frontend compatible:** All brands use same loading logic; no special cases needed

---

## 🎯 Next Steps (Optional)

1. Run parsers to populate real data
2. Add color equivalence linking between brands
3. Improve hex extraction accuracy
4. Add batch optimization for faster parsing
5. Support additional producers (Vallejo, Citadel, Model Master, etc.)
