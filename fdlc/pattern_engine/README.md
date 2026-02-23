# pattern_engine/ — Stage 4: Pattern Generation

Converts design geometry into AAMA/ASTM DXF files for CLO3D import.
Two modes — choose based on the design type.

## Mode Selection

| Mode | Use When | Input |
|------|----------|-------|
| **Mode A — Illustrator Bridge** | Organic/sculptural curves where geometry must be drawn (rib cutouts, collar structure, puffer cutouts) | SVG from potrace or Illustrator |
| **Mode B — Parametric** | Geometric/measurement-driven shapes (rectangular grids, standard blocks, panels with known proportions) | Core measurements + ratio extraction from tech pack |

**When in doubt:** If you can describe the panel shape with numbers and ratios, use Mode B. If the curve IS the design and can't be parameterized, use Mode A.

## DXF Output Spec (CLO3D compatible)
- Format: AAMA/ASTM DXF, R12 POLYLINE
- Layer 14: base/editable pattern pieces
- Layer 87: cut lines (dense)
- Layer 1: text/labels
- Pieces in named BLOCKs (one per pattern piece)
- Export settings in CLO3D: DXF-ASTM, Graded Nest, Inch, 100%, Optimize Curve Points

## Subdirectories
- `mode_a/` — Illustrator Bridge pipeline
- `mode_b/` — Parametric generator + solver library
