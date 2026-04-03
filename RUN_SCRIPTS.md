# 🎨 How to Run Color Parsing Scripts

## Quick Start (One Command)

Run all parsers at once:

```bash
cd /Users/miroslavjuhos/projects/colors
/Users/miroslavjuhos/projects/colors/.venv/bin/python scripts/run_pipeline.py
```

This will parse all available producer catalogs and output JSON to `data/results/`.

---

## Individual Parsers

### 1️⃣ Mr. Hobby Parser
Extracts colors from Mr. Hobby chart images.

```bash
cd /Users/miroslavjuhos/projects/colors
/Users/miroslavjuhos/projects/colors/.venv/bin/python source/mr_hobby/parse_mr_hobby.py
```

**Input:** `source/mr_hobby/*.png`  
**Output:** `data/results/pack_mr_hobby.json`  
**Features:** Color numbers in black boxes (C prefix), color names from corners

---

### 2️⃣ Ammo-Atom Parser
Extracts colors from Ammo-Atom (Ammo by Mig Atom) chart images.

```bash
cd /Users/miroslavjuhos/projects/colors
/Users/miroslavjuhos/projects/colors/.venv/bin/python source/ammo-atom/parse_ammo_atom.py
```

**Input:** `source/ammo-atom/*.png`  
**Output:** `data/results/pack_ammo_atom.json`  
**Features:** Table-based OCR, ATOM- codes, column detection

---

### 3️⃣ AK Interactive Parser
Extracts colors from AK Interactive chart images.

```bash
cd /Users/miroslavjuhos/projects/colors
/Users/miroslavjuhos/projects/colors/.venv/bin/python source/ak/parse_ak.py
```

**Input:** `source/ak/*.png`  
**Output:** `data/results/pack_ak.json`  
**Features:** Swatch clustering, AK code detection, row grouping

---

### 4️⃣ Gunze Sangyo Parser
Extracts colors from Gunze Sangyo (Mr. Color) chart images.

```bash
cd /Users/miroslavjuhos/projects/colors
/Users/miroslavjuhos/projects/colors/.venv/bin/python source/gunze/parse_gunze.py
```

**Input:** `source/gunze/*.png`  
**Output:** `data/results/pack_gunze.json` (already populated)  
**Features:** K-means swatch clustering, blue border filtering, OCR text extraction

---

### 5️⃣ Ammo by Mig Parser (Legacy)
Extracts colors from Ammo by Mig chart images.

```bash
cd /Users/miroslavjuhos/projects/colors
/Users/miroslavjuhos/projects/colors/.venv/bin/python source/ammo/parse_ammo_ocr.py
```

**Input:** `source/ammo/*.png`  
**Output:** Intermediate JSON files (processed separately)  
**Features:** Table OCR, row clustering, column assignment

---

## Python Environment Setup

### First Time Only: Create Virtual Environment

```bash
cd /Users/miroslavjuhos/projects/colors
python3 -m venv .venv
```

### Install Dependencies

```bash
/Users/miroslavjuhos/projects/colors/.venv/bin/pip install -r requirements.txt
```

Or install manually:

```bash
/Users/miroslavjuhos/projects/colors/.venv/bin/pip install pillow easyocr opencv-python numpy
```

---

## Expected Output

When you run the pipeline, you should see:

```
🎨 Color Chart Parsing Pipeline
==================================================

1️⃣  Parsing Mr. Hobby...
Processing 01.png...
  Found 75 colors
Processing 02.png...
  Found 27 colors
Wrote 102 colors to data/results/pack_mr_hobby.json
   ✅ 102 colors extracted

2️⃣  Parsing Ammo-Atom...
Processing 01.png...
  Found 10 headers: [...]
  ...
   ✅ 182 colors extracted

3️⃣  Parsing AK Interactive...
Processing Screenshot ...
  ...
   ✅ 33 colors extracted

==================================================
✅ Pipeline complete!
📁 Results saved to data/results/
```

---

## Verify Results

Check output files:

```bash
ls -lh /Users/miroslavjuhos/projects/colors/data/results/pack_*.json
```

View color counts:

```bash
for f in /Users/miroslavjuhos/projects/colors/data/results/pack_*.json; do
  echo "$(basename $f): $(jq '.count' $f) colors"
done
```

View sample colors:

```bash
jq '.colors[0:3]' /Users/miroslavjuhos/projects/colors/data/results/pack_mr_hobby.json
jq '.colors[0:3]' /Users/miroslavjuhos/projects/colors/data/results/pack_ammo_atom.json
jq '.colors[0:3]' /Users/miroslavjuhos/projects/colors/data/results/pack_ak.json
```

---

## Troubleshooting

### Missing Dependencies

If you get `ModuleNotFoundError`:

```bash
/Users/miroslavjuhos/projects/colors/.venv/bin/pip install pillow easyocr opencv-python numpy
```

### Python Path Issues

Use the full venv path:

```bash
/Users/miroslavjuhos/projects/colors/.venv/bin/python scripts/run_pipeline.py
```

### Slow OCR Processing

First run is slow because models download. Subsequent runs are faster (models cached).

### USB/Device Issues on macOS

Ignore warnings about MPS/GPU pinned memory—they don't affect functionality.

---

## File Organization

```
source/
├── mr_hobby/parse_mr_hobby.py       ← Run for Mr. Hobby colors
├── ammo-atom/parse_ammo_atom.py     ← Run for Ammo-Atom colors
├── ak/parse_ak.py                   ← Run for AK colors
├── gunze/parse_gunze.py             ← Run for Gunze colors
├── ammo/parse_ammo_ocr.py           ← Run for Ammo colors (legacy)
└── common/                           ← Shared utilities

data/
├── results/                          ← Output JSON files
│   ├── pack_mr_hobby.json
│   ├── pack_ammo_atom.json
│   ├── pack_ak.json
│   ├── pack_gunze.json
│   └── pack_ammo.json
└── temp/                             ← Intermediate files (CSVs, raw OCR)

scripts/
└── run_pipeline.py                   ← Master script (runs all parsers)
```

---

## View Results in Browser

After running parsers, open the frontend:

```bash
open /Users/miroslavjuhos/projects/colors/index.html
```

Select a brand from the dropdown to view colors with in-stack toggle.

---

## Summary

| Task | Command |
|------|---------|
| **Run all parsers** | `/Users/miroslavjuhos/projects/colors/.venv/bin/python scripts/run_pipeline.py` |
| **Mr. Hobby only** | `/Users/miroslavjuhos/projects/colors/.venv/bin/python source/mr_hobby/parse_mr_hobby.py` |
| **Ammo-Atom only** | `/Users/miroslavjuhos/projects/colors/.venv/bin/python source/ammo-atom/parse_ammo_atom.py` |
| **AK only** | `/Users/miroslavjuhos/projects/colors/.venv/bin/python source/ak/parse_ak.py` |
| **Gunze only** | `/Users/miroslavjuhos/projects/colors/.venv/bin/python source/gunze/parse_gunze.py` |
| **Check results** | `ls -lh data/results/pack_*.json` |
| **View in browser** | `open index.html` |
