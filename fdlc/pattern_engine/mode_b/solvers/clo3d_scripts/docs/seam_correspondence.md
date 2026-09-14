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
  reuse in a schema-validated document. `legacy=True` uses source generator length
  weights when resolving LineID references mixed with fractions. Otherwise it uses
  actual arc lengths. An unstaged artifact is interpreted in actual-length space.
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

## Interval and Direction contract

LengthParam uses a **forward perimeter interval**: start < end is ordinary;
start > end crosses the perimeter origin. Shared endpoints are allowed; any
positive interval intersection on the same panel is rejected, independently of
Direction, group or First/Second. Mixed LineID/fraction references are checked in
one perimeter space. `[0,1]` is an explicit full perimeter; identical endpoints
and `[1,0]` are rejected as empty/ambiguous.

First/Second ordering and every Direction boolean are preserved exactly.
Direction=True is **not** an instruction to swap endpoints. For a geometrically
reversed export contour, the corrected interval bounds reverse to retain the
same physical section coverage; this is driven only by geometry. No back-panel
flips or new Direction values are inferred.

This explicit forward/wrap contract does **not** guess that a descending legacy
range meant a reverse traversal of the short non-wrapping interval. The current
synthetic five-panel generator example is rejected for physical overlap under
this contract rather than being treated as a successful import. Any partial
waistband section endpoints would separately be unsupported by endpoint snapping.
If another traversal convention is required, it needs an explicit, independently
validated schema/intent contract before extending this layer.

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
