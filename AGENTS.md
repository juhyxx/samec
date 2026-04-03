# Scale Model Color Manager — Project Guidelines

## Project Overview

A application for scale modellers to manage their paint collection.
Users can catalogue paints from multiple brands, track which ones they have in stock ("in stack"),
search and filter colors, view a visual swatch, and discover equivalent/cross-reference colors from other brands.

**Target user**: scale modellers (plastic kits, miniatures, military models).
**Supported brands**: AK Interactive, Mr. Color (Gunze Sangyo),  Ammo by Mig.

---

## Tech Stack

| Layer | Technology |
|---|---|
| Renderer |  React 18  |
| Styling | Tailwind CSS v3 |
| Linting | ESLint + Prettier |

App has to work as client only. So the build should create json files, and data will available for readonly.


---

## Seed Data Format

Each brand catalog:
```json
[
  { "code": "XF-1", "name": "Flat Black", "hex": "1a1a1a" },
  { "code": "XF-2", "name": "Flat White", "hex": "f5f5f5" }
]
```

Equivalence pairs:

```json
[
  { "brand_a": "tamiya",  "code_a": "XF-1",  "brand_b": "vallejo", "code_b": "70.950" },
  { "brand_a": "tamiya",  "code_a": "XF-1",  "brand_b": "citadel", "code_b": "Abaddon Black" }
]
```


---

## Features

### List View
- Default home screen
- Shows colors by selected producer as a long table
- Color swatch (filled square rendered from `hex`), code, name, brand label
- Quick in-stack toggle button on each card
- color in stack will be saved to browser store

