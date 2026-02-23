# mode_a/ — Illustrator Bridge

SVG closed paths → seam allowance → AAMA DXF → CLO3D.

## When to use
Designs where the curve IS the design — organic shapes that can't be parameterized:
- Kimimaro puffer (organic panel cutouts)
- Multi-strap snap collar (structural standing collar curves)
- Bone vest (anatomical rib cutouts)
- Any panel with a hand-designed curve

## Pipeline
```
SVG (closed paths, one per pattern piece)
    ↓
svgelements — parse paths into piece list
    ↓
shapely + pyclipr — add seam allowance, validate closed paths
    ↓
ezdxf — output AAMA/ASTM DXF (Layer 14/87, named BLOCKs, R12 POLYLINE)
    ↓
CLO3D import
```

## SVG Sources (all valid inputs)
1. **potrace from AI-generated B&W flat** ← preferred (no Illustrator needed)
   ```bash
   potrace silhouette.png -s -o silhouette.svg
   ```
2. **Illustrator export** — File → Export → SVG, "Outline" text, preserve paths
3. **Hand-drawn clean line art** → potrace

## Status
🔲 Not yet built. Spec complete. No blockers.

## Scripts
- `illustrator_bridge.py` — TODO
