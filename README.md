# Scale Model Color Manager

A web-based tool for scale modelers to manage and organize paint colors from multiple brands, track equivalent colors across manufacturers, and build personal color collections.

## Purpose

Scale modelers often work with paints from different manufacturers (Ammo by Mig, Vallejo, Tamiya, Mr. Color, etc.). This app helps you:

- **Browse color catalogs** from 10+ paint manufacturers in one place
- **Track your paint collection** ("My Stack") with persistent local storage
- **Find manufacturer-provided color equivalents** across different brands — colors that manufacturers have explicitly marked as equivalent
- **Compare swatches visually** with actual hex color values
- **Save and load** paint stacks for different projects

**Important: This uses manufacturer equivalents, not RGB matching.** The app relies on official equivalency data published by paint manufacturers themselves. This means you get accurate, manufacturer-certified color matches—not approximate RGB color searches. This is more reliable for scale modeling where specific paint formulations matter.

Supported paint brands:
- Ammo by Mig
- ATOM (Ammo)
- AK Interactive
- Aqueous Hobby color (Gunze)
- Mr. Color
- Vallejo
- Tamiya
- Humbrol
- RLM

## How to Use

### Getting Started

1. Open `index.html` in your web browser
2. You'll see a grid of color cards with brand tabs at the top

### Browsing Colors

- **Select a brand**: Click on the brand tabs at the top (Ammo, Vallejo, Tamiya, etc.) to switch between paint manufacturer catalogs
- **View color details**: Each card shows:
  - Color swatch (left side)
  - Color code/name
  - Manufacturer label
  - Add/Remove button

### Building Your Color Stack

1. Click the **"Add"** button on any color card to add it to your stack
2. The button changes to **"✓ Remove"** and the card highlights in yellow
3. Click **"My Stack"** tab to view all colors you've collected
4. Your stack automatically saves to your browser's local storage

### Understanding Color Equivalents

This is a **key feature** of the app: it uses **manufacturer-provided equivalents**, not RGB or color space calculations.

When you add a Vallejo color to your stack, the app can show you if other manufacturers (Tamiya, Ammo, Mr. Color, etc.) have officially declared their colors as equivalent. These equivalencies come from official manufacturer catalogs and matching charts—they're not computed based on similar RGB values.

**Why this matters:**
- **Accuracy**: Paint formulations vary by manufacturer. A visually similar color might perform differently
- **Manufacturer certified**: You get official matches that manufacturers have tested and approved
- **No approximations**: You won't see "close" colors, only official equivalents
- **Reliable for modeling**: Critical when you need exact paint substitutes for a specific project

**How equivalents work:**
- Manufacturers publish color equivalency charts (e.g., "Vallejo 70.820 = Tamiya XF-27")
- These are extracted from official catalogs and stored in the app's database
- When you view a color, equivalent colors from other brands are displayed
- This is accurate manufacturer data, not algorithmically-generated matches

### Managing Your Stack

In the "My Stack" tab, you can:
- See all colors you've added with their codes, names, and brands
- Remove colors by clicking the **×** button
- **Save to file**: Export your stack as a JSON file for backup or sharing
- **Load from file**: Import a previously saved stack

### Features

- **Color swatches**: Real hex color values for accurate visual reference
- **Manufacturer-certified equivalents**: Cross-brand color matches from official manufacturer catalogs (not RGB-based searching)
- **Dark mode**: Automatically switches based on your system preferences
- **Persistent storage**: Your stack is saved locally and persists between sessions

## Technical Details

### Data Files

- `data/pack_*brand*.json` — Color catalogs for each brand
- `data/*.csv` — Source data files

### Code Structure

- `index.html` — Main page with HTML templates
- `script.js` — Client-side logic (tabs, color management, storage)
- `style/` — Tailwind CSS styling

### Templates

The app uses CSS `<template>` elements for dynamic content:
- Color cards
- Brand tabs
- Stack items

### Storage

- Colors are stored in browser's `localStorage`
- Each brand's colors are stored separately in JSON format
- Stack data can be exported to JSON file format

## Browser Requirements

- Modern browser with ES6+ support
- Local storage enabled
- JavaScript enabled

## Keyboard Shortcuts

- Tab navigation works with keyboard
- Click buttons to add/remove colors from stack
