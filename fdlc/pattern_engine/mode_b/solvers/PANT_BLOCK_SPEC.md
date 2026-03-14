# Pant Block Solver — Technical Spec

**Purpose:** Generate production-grade trouser pattern pieces from flat measurements, for use in the reference clone pipeline (Mode 2).

**First target:** Pool House New York wide-leg twill pants, size 30.

**Output:** DXF (AAMA/ASTM R2000, INSUNITS=1 inches) importable into CLO3D.

---

## Input Schema

```json
{
  "garment_type": "wide_leg_pants",
  "unit": "inches",
  "measurements": {
    "waist": 30.0,
    "hip": 52.0,
    "front_rise": 12.75,
    "back_rise": null,
    "inseam": 28.5,
    "outseam": 40.5,
    "thigh": 28.0,
    "knee": null,
    "leg_opening": 23.5,
    "fly_length": 10.0
  },
  "construction": {
    "seam_allowance": 0.625,
    "hem_allowance": 1.5,
    "waistband_width": 1.75,
    "pocket_type": "slash",
    "pocket_angle_deg": 30,
    "back_pocket_type": "single_welt",
    "fly_type": "standard_zip",
    "dart_count_back": 0
  },
  "ease": {
    "waist": 1.0,
    "hip": 2.0,
    "thigh": 2.0
  }
}
```

**Notes on inputs:**
- All circumference measurements are FULL (not flat). The solver halves them internally.
- `back_rise` can be null — derive as `front_rise + 2.0` (standard offset for men's relaxed fit).
- `knee` can be null — derive as midpoint between crotch and hem, with width interpolated from thigh to leg_opening.
- Measurements come from `size-chart.json` (verified from brand) or vision model extraction. Size chart takes priority.

---

## Output: Pattern Pieces

### 1. Front Panel (x2, mirror)
- **Construction:** Rectangle base from waist to hem, with crotch curve extension at inseam.
- **Key points:** Waist, hip, crotch (deepest point), knee, hem.
- **Crotch curve (front):** Shallow curve — `hip/8` extension from center front at crotch depth. Use quadratic bezier or 3-point arc. Front crotch is less deep than back.
- **Side seam:** Straight from hem to knee, slight outward curve through hip to waist.
- **Inseam:** Straight from hem to knee, slight inward curve to crotch point.
- **Waist:** Width = `(waist + waist_ease) / 4 + 1.0"` (front gets slightly more than quarter).
- **Hem:** Width = `leg_opening / 4 + 0.5"` (adjusted for wide-leg — front/back nearly equal).
- **Grainline:** Vertical, centered between inseam and side seam at crotch depth.
- **Slash pocket cutout:** Diagonal line from ~1" below waist at side seam, angling toward center at `pocket_angle_deg`. Creates the pocket opening edge on the front panel.

### 2. Back Panel (x2, mirror)
- **Same construction as front with key differences:**
- **Crotch curve (back):** Deeper — `hip/8 + 1.5"` extension. More pronounced curve. Back crotch is always wider and deeper than front.
- **Waist:** Width = `(waist + waist_ease) / 4 - 1.0"` (back gets less; center back rises ~1" above front waist for seat room).
- **Back rise:** Longer than front by ~2" — center back seam extends higher.
- **Welt pocket position:** Horizontal rectangle at approximately hip level, centered on panel. Mark with construction lines only (not cut lines).

### 3. Waistband (x1, cut on fold)
- **Rectangle:** Length = `waist + waist_ease + seam_allowance*2`. Height = `waistband_width * 2` (folds in half).
- **Notches:** Mark center front, center back, side seams, fly position.

### 4. Fly Shield (x1)
- **Shape:** J-shaped piece following the fly curve.
- **Dimensions:** Width ~2.5", length = `fly_length`. Curved at bottom matching the J-stitch line.

### 5. Fly Extension (x1)
- **Shape:** Narrow strip that underlaps the zipper.
- **Dimensions:** Width ~1.5", length = `fly_length`.

### 6. Front Pocket Bag (x2)
- **Shape:** Curved top edge matching the slash pocket opening, rectangular body.
- **Dimensions:** ~6" wide x 10-11" deep. Top edge curves to match pocket opening angle.

### 7. Back Pocket Welt (x2)
- **Shape:** Rectangle.
- **Dimensions:** Width ~5.5", height ~1.5" (folds to ~0.75" visible welt).

### 8. Back Pocket Bag (x2)
- **Shape:** Rectangle.
- **Dimensions:** ~6" wide x 7" deep.

### 9. Belt Loop Strip (x1)
- **Shape:** Long rectangle, cut into 5 loops.
- **Dimensions:** Width ~1.5" (folds to ~0.5"), total length = `5 * 3.5"` (each loop ~3.5" long).

---

## Crotch Curve Algorithm

The crotch curve is the hardest part. Standard approach:

### Front crotch:
1. From center front at crotch depth, extend horizontally by `crotch_extension_front = hip_half / 8`
2. The curve connects the center front at waist-to-hip point to the crotch point
3. Use a 3-point bezier: start (center front at crotch depth), control (0.6 * extension, 0.4 * rise below crotch depth), end (full extension point)
4. Front curve is relatively shallow — almost a quarter circle

### Back crotch:
1. From center back at crotch depth, extend horizontally by `crotch_extension_back = hip_half / 8 + 1.5"`
2. Back curve is deeper and more aggressive
3. Use a 3-point bezier: start (center back at crotch depth), control (0.5 * extension, 0.6 * rise below crotch depth), end (full extension point)
4. Center back waist point rises ~1" above the front waist line

### Validation:
- Front inseam length must equal back inseam length (within 0.25")
- Front side seam must equal back side seam (within 0.25")
- Total crotch curve length (front + back) should approximate: `front_rise + back_rise`

---

## DXF Output Requirements

Follow the same conventions as `rect_panel_grid.py`:
- **Format:** R2000 (`AC1015`)
- **Units:** `$INSUNITS = 1` (inches)
- **Geometry:** Flat modelspace only (no BLOCK/INSERT)
- **Layers:**
  - `CUT` — cut lines (solid)
  - `SEAM_ALLOWANCE` — seam allowance offset lines (dashed)
  - `GRAIN` — grainlines
  - `NOTCH` — notch marks
  - `INTERNAL` — construction lines (darts, pocket placement, fold lines)
  - `TEXT` — piece labels
- **Each piece** gets a text label with piece name + size
- **Seam allowance** is added as an offset around each piece (default 5/8" = 0.625")
- **Hem allowance** is separate (default 1.5")

---

## File Structure

```
mare-pipeline/fdlc/pattern_engine/mode_b/solvers/
├── rect_panel_grid.py      # existing — grid panels
├── pant_block.py            # NEW — trouser block solver
├── __init__.py              # update to export pant_block
└── PANT_BLOCK_SPEC.md       # this file
```

`pant_block.py` should expose:
```python
def solve(measurements: dict, construction: dict, ease: dict) -> dict:
    """Returns dict with pieces list, each piece having points, curves, metadata."""
    ...

def to_dxf(solution: dict, output_path: str) -> str:
    """Writes DXF file, returns path."""
    ...
```

---

## Integration

The `parametric_gen.py` script should be updated to:
1. Detect `garment_type == "wide_leg_pants"` (or any pants type)
2. Route to `pant_block.solve()` instead of `rect_panel_grid.solve()`
3. Maintain the same CLI interface: `python parametric_gen.py <design_dir> [--draft]`

---

## Test Case: Pool House Wide Leg Twill Size 30

```json
{
  "waist": 30.0, "hip": 52.0,
  "front_rise": 12.75, "back_rise": 14.75,
  "inseam": 28.5, "outseam": 40.5,
  "thigh": 28.0, "leg_opening": 23.5,
  "fly_length": 10.0
}
```

Expected output: DXF with 9 distinct pattern pieces, importable into CLO3D without errors.

---

## References

- Standard trouser block drafting: theshapesoffabric.com/2020/08/16/learn-how-to-draft-the-basic-pants-pattern/
- MARE pattern engine architecture: `~/base/creative/MAREv2/designs/wide-leg-twill-pants/../../pattern-engine/architecture.md`
- Existing solver pattern: `rect_panel_grid.py` in this directory
- DXF conventions: R2000 format, ezdxf library, flat modelspace geometry
- CLO3D import tested: INSUNITS=1 (inches), no BLOCK/INSERT
