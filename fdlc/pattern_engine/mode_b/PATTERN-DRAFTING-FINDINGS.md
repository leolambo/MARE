# Pattern Drafting Findings

Key learnings from building the trouser block solver (v1–v21, March 2026).
Apply these to ALL future garment block solvers.

## Coordinate System
- **Y goes DOWN** (waist at y=0, hem at y=40+)
- **X=0 = center front/back + inseam axis** — the left edge of the panel
- **Positive X = side seam direction** (outward)
- **Negative X = crotch extension direction** (inward)
- **Grainline** at x = hem_width / 2 (crease line = midpoint of leg tube)

## Critical Rules

### 1. Seam Lengths MUST Match
Front and back inseam must be equal (Δ < 0.5"). Same for side seam.
Build a solver loop: generate → measure → adjust → repeat until deltas converge.
The `b_drop` parameter (how far below crotch line the crotch tip sits) is the primary tuning knob for inseam matching.

### 2. Shared Crotch Line
Use the SAME Y position for both front and back crotch depth. The body crotch line doesn't change — what changes is:
- How far BELOW that line each crotch tip extends (back drops further)
- How far LEFT the crotch extension reaches (back extends more)
The `back_rise - front_rise` difference is absorbed by the CB seam length and crotch curve depth, NOT by moving the crotch line.

### 3. Measurement Interpretation — Don't Halve Twice
`leg_opening` in body measurements is typically the FLAT half-circumference (pants folded flat).
Each panel gets ~48% (front) or ~52% (back) of this value directly.
**DO NOT** halve it again inside the panel function. Halving twice = half the actual hem width = extreme taper.
This was the single biggest bug in early versions.

### 4. Bezier Curve Continuity at Segment Joints
When two bezier segments meet, the tangent at the junction must be continuous (G1 continuity).
If you chain `cb_seam → crotch_curve → inseam_curve`, each segment's end tangent must match the next segment's start tangent.
**Better approach:** merge adjacent curves into ONE longer cubic bezier when possible (e.g., back CB seam + crotch curve = single cbez from waist to crotch tip).

### 5. Cubic > Quadratic for Anatomical Curves
Quadratic beziers (3 points) create too-simple curves — they always produce symmetric arcs.
Cubic beziers (4 points) allow asymmetric J-curves, S-curves, and proper anatomical shaping.
Use `cbez(p0, p1, p2, p3)` everywhere garment curves exist.

### 6. Waistline Shaping
- **Front:** concave curve — CF dips ~0.5–0.75" below the waist line, side rises ~0.3–0.5" above
- **Back:** CB raised ~1.5" above waist line and shifted ~2" to the left for CB seam angle
- **Control points** for concave curves must be ABOVE (more negative Y) both endpoints

### 7. Back Panel Differences
- CB seam: angled (slants outward/left at top, 1.5–2" offset from vertical)
- Crotch extension: ~1.5" deeper than front
- Hip width: ~1" wider per side than front
- Waist: slightly narrower than front (dart intake)
- Crotch tip drops further below crotch line (1.6–2.0" vs 1.0" for front)

### 8. Side Seam Curve Character
- Waist to hip: smooth convex curve outward (most of the curvature is in the top 8–10")
- Hip to knee: gradual inward taper (or nearly straight for wide-leg)
- Knee to hem: nearly straight (slight inward for tapered, straight for wide-leg)

### 9. Visual Verification Loop
**Always** generate PNG before DXF. Use vision model to check:
1. Side seam curve (smooth, no spikes/diamonds)
2. Crotch J-curve (extending correct direction, smooth)
3. Waistline shape (concave front, angled back)
4. Front vs back proportions (back wider)
5. No angular corners at segment junctions

### 10. DXF Export Rules (CLO3D)
- R2000 format
- INSUNITS=1 (inches)
- Flat modelspace geometry only (no BLOCK/INSERT)
- Panels laid out side-by-side with spacing
- Separate layers: CUT, SEAM_ALLOWANCE, GRAIN, NOTCH, INTERNAL, TEXT

## Solver Architecture
```
measurements + construction + ease
  → build_front_panel()  → points + metadata
  → build_back_panel()   → points + metadata
  → seam_match_solver()  → adjust b_drop until Δinseam < 0.5"
  → auxiliary_pieces()   → waistband, fly, pockets
  → validate()           → seam deltas, proportions
  → to_dxf() / to_png()  → export
```

## Applicable to Other Blocks
| Block | Key Shared Principles |
|-------|----------------------|
| Skirt | Same waist shaping, hip curve, grainline rules |
| Bodice | Similar CF/CB seam logic, dart intake, side seam matching |
| Sleeve | Seam matching (sleeve cap must match armscye), bezier smoothness |
| Jacket | All of the above + ease handling |
| Shorts | Same as trouser block with shorter inseam |

## Parameter Ranges (Size 30 Waist Reference)
| Parameter | Front | Back | Notes |
|-----------|-------|------|-------|
| Waist width | 8.0" | 7.0" | Quarter waist + ease |
| Hip width | 13.5" | 11.1–14.5" | Quarter hip + ease |
| Hem width | 11.28" | 12.22" | 48/52 split of leg_opening |
| Crotch extension | 3.25" | 4.75" | hip/16 + back offset |
| Crotch tip drop | 1.0" | 1.6–1.9" | Below shared crotch line |
| CB waist offset | 0 | -2.0" x, -1.5" y | Diagonal for glute room |
| Waist concavity | 0.75" dip | 0.3" dip | At CF/CB relative to side |
