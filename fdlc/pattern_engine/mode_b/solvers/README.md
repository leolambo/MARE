# solvers/ — Geometry Primitive Library

Reusable building blocks for the parametric generator.
Each solver takes measurements + ratios and returns exact panel dimensions.
Designs compose from multiple primitives.

## Available Solvers

| Solver | Shape | First Use | Status |
|--------|-------|-----------|--------|
| `rect_panel_grid.py` | Rounded rectangle grid (N cols × M rows) | Star grid denim pants | 🔲 TODO |
| `curved_panel.py` | Arc-based panel (puffer belly, sleeve crown) | Kimimaro puffer | 🔲 TODO |
| `tapered_panel.py` | Trapezoid panel (raglan, tapered pieces) | — | 🔲 TODO |
| `waistband.py` | Straight or curved waistband | Star grid pants | 🔲 TODO |
| `sleeve_block.py` | Basic sleeve (bicep → wrist, ease) | — | 🔲 TODO |

## Solver Interface (convention)
Each solver returns a dict of computed dimensions + the ezdxf draw function:
```python
from solvers.rect_panel_grid import solve, draw

dims = solve(
    leg_width=120,      # mm
    inseam=762,
    cols=3, rows=4,
    gap_ratio=0.12,
    corner_ratio=0.18,
    seam_allowance=12.7  # 0.5 inch in mm
)
# dims = { panel_width, panel_height, gap, corner_radius, ... }

draw(msp, x=0, y=0, **dims)  # writes to ezdxf modelspace
```

## Adding a New Solver
When a new design needs geometry that doesn't fit existing primitives:
1. Create `solvers/<shape_name>.py`
2. Implement `solve(**inputs) → dict` and `draw(msp, x, y, **dims)`
3. Add to this README table
4. Commit to mare-pipeline
