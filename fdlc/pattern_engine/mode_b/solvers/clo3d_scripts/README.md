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

## Offline artifact verification (no CLO or MCP access)

Keep `seam_correspondence.py` and `verify_artifacts.py` beside `02_inject_seams.py`.
See [offline geometry API and limitations](docs/seam_correspondence.md).
All three use only Python's
standard library; the injector's positional arguments and callable interface are
unchanged. The output must now be **new**: existing files, input aliases, and
symlinks are refused by exclusive creation. Choose a versioned output rather than
overwriting. Inputs and CLO export arrangement/metadata are preserved.

From this directory:

```bash
# Any explicitly supplied subset is useful; missing stages remain unknown.
python3 verify_artifacts.py --panels /path/panels.json
python3 verify_artifacts.py --panels /path/panels.json \
  --clo-export /path/clo-export.json --sewn /path/sewn.json
# Historical file with no proven stage: run each variant separately.
python3 verify_artifacts.py --artifact /path/retained-reference.json
```

Stdout is a JSON manifest with byte SHA-256 fingerprints, counts, static error
codes and check status. No paths, names, IDs, geometry or raw parse errors are
printed. Fingerprints permit correlation and are **not anonymization**. Redirection
is optional and performed by your shell, not by the read-only verifier.

Exit status: **0** all implemented offline checks passed with all three stages and
nonempty, geometry-resolvable boundary seams; **1** invalid/unreadable artifact or stage
mismatch; **2** incomplete/unknown (also argparse usage errors). An incomplete
report can have no errors. `checks.roundtrip=passed` means only structural
agreement of the supplied stage files, not host provenance or successful import.

### Checks and intentional limits

- Pattern names and string IDs must be nonempty and unique; ID/ShapeID aliases
  must agree if both exist. Names match exactly, with no trimming or case folding.
  All present stages must have identical name sets, establishing a total bijection.
- Remapping resolves `PairList[].First/Second.ShapeID` and recomputes LengthParam
  from matched exported section arc lengths (LineID inputs become LengthParam).
  First/Second order, Direction and seam names/metadata remain unchanged.
  Source-to-sewn seams and
  export-to-sewn non-seam content are compared with type-sensitive canonical JSON.
  List order is significant; whitespace/object-key order is not.
- Supported units are mm. Supported seam sides are exactly ShapeID, Direction
  plus either LineID or LengthParam `{fStart,fEnd}`. Direction must be a JSON
  boolean; fractions must be finite numbers in [0,1], not booleans. Descending
  fractions use the explicit forward/wrap contract in the geometry API document;
  no alternate legacy traversal is guessed. Duplicate JSON keys and all nonfinite numbers fail.
  Unknown seam group/pair/side structure is rejected rather than silently remapped.
  Optional group `Name` must be a string (empty labels remain supported),
  `bIsTurned` must be a JSON boolean, and present `FoldData` must be exactly
  `{iAngle, iStrength}` with integer values, excluding booleans. This is the
  generator/retained-reference structure; missing/extra keys, nested references,
  nulls and other types fail closed. Omitted metadata remains supported. Fold
  settings are type-checked, not certified for CLO physical ranges or semantics.
- A LineID references an outline line within its pattern. Reuse of that **whole
  physical line** is a conflict regardless of Direction or group. Present outline
  IDs must be unique per panel. Generator waistband lines can omit IDs; these
  cannot satisfy LineID references. Shared endpoint IDs are intentionally not
  globally rejected. Point types, coordinates, closed boundaries and section
  correspondence are validated; missing PointList geometry fails closed.
- LengthParam and LineID references across seam sides share physical interval
  overlap checks. Shared endpoints are allowed. A side cannot contain both
  reference encodings. Source fraction endpoints must uniquely snap to generator
  boundary sections; interior endpoints and all subdivisions are unsupported.
  See the geometry API document for tolerance scope and reversal/wrap limitations.
- No proof of CLO geometry equivalence across generation/export, correct seam
  orientation, fabric physics, arrangement, simulation, saved-project persistence,
  asset closure, or matching live project is supplied. Unique names are a mapping
  convention, not independently authenticated identity. No host API is called.
- Use explicit trusted local files. Parsing is in memory, not a hostile-input
  sandbox; fingerprints identify bytes read, not atomic provenance against a
  concurrent writer. Injection is no-clobber, not transactional against disk I/O
  failure: a failed new output write can leave a partial new file.

Regression tests and recorded evidence: `test_artifact_verifier.py` and
[`docs/evidence/offline-artifacts/REPORT.md`](../../../../../docs/evidence/offline-artifacts/REPORT.md).

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
