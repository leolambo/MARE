# CLO3D Scripts

Scripts for the CLO3D 3D simulation workflow. CLO3D ignores seams from freshly generated JSON, so a round-trip is required.

## Workflow

1. Generate panels JSON on Mac:
   ```python
   from fdlc.pattern_engine.mode_b.solvers.clo3d_json import generate_5panel_json
   generate_5panel_json(measurements, "/tmp/clo_DESIGN_panels.json")
   ```

2. **File → New** in CLO3D, paste `01_import_export.py` → tells AL to inject seams

3. Run `02_inject_seams.py` on Mac:
   ```bash
   python3 02_inject_seams.py /tmp/clo_DESIGN_panels.json /tmp/clo_DESIGN_export.json /tmp/clo_DESIGN_sewn.json
   ```

4. **File → New** in CLO3D, paste `03_import_sewn.py` → imports with seams, flips back panels

5. Manually arrange panels around avatar in 3D window

6. Set fabric (optional: paste `04_set_fabric.py`, then manually set Physical Properties: Woven, 300 g/m²)

7. Simulate via spacebar

## Script Editor Rules

- All API calls require `import pattern_api` — functions are NOT bare globals
- `fabric_api` is a separate import
- `NewProject()` does NOT exist — File → New is manual
- `pattern_api.Simulate()` may not exist in all versions — use spacebar
- Replace `DESIGN` in file paths with your actual design name

## Flip Rules

- Flip all panels with "Back" in the name: Back_Left, Back_Right, WB_Back
- Flip horizontal: `FlipPatternPiece(i, True, False)`
- Never hardcode indices — iterate by name with `GetPatternPieceName(i)`

## Panel Layout (6 panels)

| Panel | Type | Notes |
|-------|------|-------|
| Front_Left | Leg | Original geometry |
| Front_Right | Leg | Mirrored (negated X) |
| Back_Left | Leg | Original geometry, flip after import |
| Back_Right | Leg | Mirrored, flip after import |
| WB_Front | Waistband (CLO3D only) | Bottom split: right-half→FL, left-half→FR |
| WB_Back | Waistband (CLO3D only) | Bottom split: left-half→BL, right-half→BR. Flip after import |

IRL production uses a single waistband piece — see `pant_block.py`.

## Seam Architecture (20 seams)

**Per-leg (10):** side_top, side_hip_knee, side_knee_hem, inseam_straight, inseam_curve × L/R

**Cross-leg (4):** center_front (FL↔FR), center_back (BL↔BR), crotch_front, crotch_back

**Waistband (6):** wb_front_to_FL, wb_front_to_FR, wb_back_to_BL, wb_back_to_BR, wb_side_R, wb_side_L
