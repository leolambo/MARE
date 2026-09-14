# Offline seam correspondence API

This module performs no CLO, bridge, deployment, arrangement, simulation, back-flip,
or staging operations. All geometry examples in tests are synthetic, not host evidence.

## Entry points

- `verify_artifacts.remap_seams(source, target, *, with_report=False)` is the
  schema-validating API for parsed documents. It validates both inputs and the
  output, returns a deep-copied sewn export, and optionally returns `(export, report)`.
  `InvalidArtifact` contains only a static category. Use `verify_artifacts.parse`
  for JSON decoding with duplicate-key rejection.
- `seam_correspondence.correspond(source, target)` is the reusable geometry core:
  it returns `(export, report)` without file access. Its precondition is the
  verifier's artifact/seam schema validation. It independently checks panel
  bijection, point geometry, correspondence, endpoint recovery and source coverage.
  It raises `CorrespondenceError`, a separate `ValueError` subclass; the verifier
  translates that class at its boundary, avoiding circular imports.
- `check_intervals(data, legacy=False)` checks geometry and physical interval
  reuse in a schema-validated document. `legacy=True` recovers generator recipe
  occupancy after strict boundary snapping, including mixed LineID/fraction inputs.
  Otherwise it retains the existing actual-length forward/wrap check; that check
  is not established CLO semantics. An unstaged artifact uses this target mode.
- The injector retains its three positional paths and callable signature. It
  serializes before exclusively creating the output (`open(..., 'x')`). Existing
  outputs, input aliases and symlinks cannot be overwritten. Inputs are immutable;
  export fields other than `SeamLinePairGroupList` remain unchanged.

## Geometry and source intent

Panels map by exact unique names, with unique string IDs and agreeing ID/ShapeID
aliases. No trimming, case folding, scale fitting, registration or reflection is
performed. Units must be `mm`.

A closed `ShapeInfo.LineList` consists of straight two-point sections with types
`[0,0]` or cubic Bezier sections with types `[0,3,3,0]`. The generator's exact legacy
spellings `[Straight,Straight]` and `[Straight,Bezier Curve,Bezier Curve,Straight]`
are also supported. Mixed or unknown type sequences fail closed. Position x/y
must be finite numbers, not booleans. Additional point/export metadata is preserved.
Consecutive section endpoints, including closure, must agree within `1e-8 mm`.
Zero-length/near-degenerate sections are rejected.

Source fractions are interpreted using the existing generator's **control-polygon
length sum multiplied by 1.15 for cubics**, and Euclidean length for straights.
This is not an approximation of actual cubic arc length used for the output.
Each intended endpoint must snap to exactly one cumulative source section boundary
within an absolute, dimensionless fraction tolerance of `1e-9`. No nearest-point
fallback, interior interpolation, or enlarged geometry tolerance is used for
endpoint snapping. Nonboundary and nonunique endpoints are rejected. The fraction
budget is not a universal millimetre error bound; its physical size depends on
perimeter. LineID inputs resolve the entire source outline section and become
corrected LengthParam outputs, so exported line IDs need not remain stable.

Export fractions use adaptive Simpson integration of cubic speed, with an absolute
per-section error estimate budget of `1e-10 mm`, split recursively to depth 24.
Nonconvergence is rejected rather than returning an unconverged estimate. Straight
lengths are Euclidean. Independent analytic cubic/parabola tests exercise this path.

## Matching and tolerance scope

Every source section must have exactly one complete matching exported section,
including all cubic controls. Duplicates and multiple candidates are rejected even
when list order happens to agree. The matching is a total section bijection.

- A panel with the same section count, arity, direct order and orientation may use
  Euclidean point discrepancy up to `0.001 mm`.
- Cyclic reorder and complete contour reversal use the independent synthetic
  numerical tolerance `1e-8 mm`, not the observed conversion tolerance. Reversal
  reverses all cubic controls as well as endpoints. A tolerance-only reversed or
  reordered candidate is rejected.
- Arbitrary noncontiguous ordering, mixed section orientation, changed section
  counts, and **all straight/cubic subdivision or merging are unsupported**.
  Section-count changes have an explicit unsupported category; there is no
  partial-chain or endpoint-only matching.

The supplied observations motivating only the first case are: 6 unique same-name
panels; Unit mm; bbox scale 1:1; 52 sections with the same count, arity, orientation
and direct order; no reorder/subdivision observed; maximum serialized coordinate
discrepancy `0.000100499 mm`, mean `0.000019026 mm`. These were supplied observations,
not recomputed from private artifacts, and do not establish support for any other
conversion topology. Report discrepancy statistics are computed from the actual
supplied documents, never filled with those observation constants.

## Source recipe recovery versus target representation

Known legacy generator recipes use section index boundaries, including descending
ones: `_build_per_leg_seams` constructs a single section with boundaries `bi+1`
and `bi`, and known waistband pairs also descend. After strict, unique snapping,
source occupancy is `range(min(start_index, end_index), max(start_index, end_index))`.
Indices `(2,1)` therefore consume exactly section 1, not the wrapping remainder.
This recovers generator construction intent only; it does not infer CLO LengthParam
traversal. Mixed LineID/fraction inputs use the same source section space.
Shared endpoints are allowed; positive source occupancy overlap is rejected
independently of Direction, group or First/Second. Existing rejection of identical
endpoints and `[1,0]` remains; `[0,1]` remains the explicit full perimeter.

First/Second ordering and every Direction boolean are preserved exactly.
Direction=True is **not** an instruction to swap endpoints. For a geometrically
reversed export contour, the corrected interval bounds reverse to retain the
same physical section coverage; this is driven only by geometry. No back-panel
flips or new Direction values are inferred.

Occupancy recovery does not sort or swap the emitted endpoints. The mapper's
existing endpoint representation, First/Second ordering and Direction handling
are unchanged, including descending output on a direct export clone.

The target validator is deliberately unchanged: ascending fractions use an
ordinary interval and descending fractions are checked as forward wraparound.
This is an implementation assumption, **not documented or observed CLO LengthParam
semantics**. Thus source recovery and geometry correspondence can pass while
`remap_seams` still rejects the corrected result during target validation. Such a
rejection is not evidence that the source recipe overlaps or that CLO would reject
it. Establish target semantics independently before changing that validator.
Nonboundary source endpoints (including partial sections) remain unsupported.

## Reports and verification limits

Reports contain only digests, statuses, counts, tolerance values, discrepancy
statistics, categories and coverage. No raw names, IDs, coordinates, paths or
exception traces are emitted by the CLI. Coverage counts matched boundary sections
and occupied source sections; it does not certify paired seam lengths, easing,
orientation inside CLO, self-intersection, fabric, physical simulation or live
project provenance. The core report has no file digest because it performs no I/O;
the verifier adds byte SHA-256 digests (correlatable fingerprints, not anonymization).

`checks.correspondence` contains independent panels-to-export and panels-to-sewn
reports where those stages are supplied. A full `passed` offline report requires
all stages, nonempty seams, interval clearance, corrected seam equality and exact
type-sensitive non-seam export preservation. Missing stages remain incomplete.
