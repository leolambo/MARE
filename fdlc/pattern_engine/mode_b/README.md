# mode_b/ — Parametric Generator

Core measurements + proportional ratios → computed dimensions → AAMA DXF → CLO3D.

## When to use
Designs where geometry is measurement-driven and describable with math:
- Star grid denim pants (3×4 rounded rectangle panel grid)
- Puffer panels (arc-based curves with known depth ratios)
- Standard trouser/jacket blocks
- Any design where you can say "X panels wide, Y% gap, Z% corner radius"

## Pipeline
```
tech pack image (optional)
    ↓
Gemini 2.5 Flash vision — extract ratio structure as JSON
  { panels_per_row: 3, rows: 4, gap_ratio: 0.12, corner_ratio: 0.18 }
    ↓
Core measurements from pattern_intake.py
  { waist: 32, hip: 40, inseam: 30, rise: 11, ease: 4 }
    ↓
Solver (solvers/) — constraint system → exact mm dimensions
  panel_width = leg_width / (cols * (1 + gap_ratio))
  panel_height = inseam / (rows * (1 + gap_ratio))
  corner_radius = panel_width * corner_ratio
    ↓
ezdxf — generate DXF from computed dimensions
    ↓
CLO3D simulate → validate → --recalculate if needed
```

## Recalculation Loop
After CLO3D simulation reveals fit issues:
```bash
python3 fdlc/pattern_intake.py --recalculate <design-name>
```
Adjusts one or more ratios, re-runs solver, outputs updated DXF. No re-measuring.

## Solver Library
See `solvers/` for available geometry primitives. Each design composes from these.
New designs that don't fit existing primitives get a new solver added to the library.

## Status
🔲 Not yet built. Spec complete, math validated on star-grid pants.

## Scripts
- `parametric_gen.py` — TODO
- `solvers/rect_panel_grid.py` — TODO (star-grid, first to build)
