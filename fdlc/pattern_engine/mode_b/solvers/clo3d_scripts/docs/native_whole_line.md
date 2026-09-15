# Fixed native whole-section result profile

`native_whole_line.verify_fixed_result` requires caller-authenticated, same-run
native `pattern_geometry`. There is no analytic fallback for absent witnesses.
The bridge brackets its same-project initial export with identical complete
geometry/topology/identity reads, signs the native reference, and requires unchanged
post-sewing geometry. Adjacent verification authenticates the predecessor files,
witness hashes and readback before using its lengths. This pure pipeline function
cannot independently establish freshness or authenticate a caller's dict.

Every before/after contour still passes full straight/cubic correspondence. Both
exports bind uniquely to native lines by endpoints and bounded length agreement.
Reported native lengths are then placed in **exported contour order** via that
bijection, never native array order or `lineIndex` ordinals. Cumulative fractions
use `math.fsum`. Unique LineIDs, exact intended recipe pairing, counts, effective
endpoint direction and all completed fixed groups remain mandatory.

## Bounded third stage

The internal binder accepts only groups 0, 1 and 2: `side_top_L`,
`side_hip_knee_L`, `side_knee_hem_L`. Group2 is whole source section 3 on
Back_Left and Front_Left, boundary order [3,4]: knee pairs with knee and hem
with hem. Native flags are `not (export_reversed XOR native_reversed)`;
they are not copied from recipe Direction. A reversed observed native line
therefore reverses its flag. Result count 3 verifies all three unique intended
pairings with the same authenticated native-length model and direction policy.
No later group or arbitrary caller indices are accepted.

The canonical 20-group recipe was fully classified with `whole_line_recipe.analyze`:
19 groups are one whole section per side; only group10 `center_front` spans
multiple whole sections (8,9,10,11 on each Front panel). No partial section occurs
under the source recipe boundary model. This is coverage eligibility, not blanket
native support. A future programmatic route should keep a fixed recipe-owned plan,
prove endpoint orientation per seam family and disjoint occupancy, and resolve
center_front segment correspondence before splitting it. Do not add one public API
per remaining group or silently pair multi-section ordinals. Group2 native host
acceptance, physical orientation, persistence and simulation remain separate gates.

## Numerical acceptance budget

For perimeter P and selected section length L, each endpoint must be within

```
min(2**-23 + 5e-10, 0.001 / P, 0.001 * L / P)
```

of the native-length cumulative boundary. Fractions must also be finite and in
[0, 1]; exactly one forward/backward whole-section interpretation must fit.
The unit-scale budget allows two half-ULPs for binary32-scale fraction arithmetic
and half a nine-decimal-place serialization step. This is a conservative **fixed
observed-profile acceptance policy**, not a vendor guarantee about accumulation,
rounding or decimal formatting. Each endpoint is additionally capped at 0.001 mm
and 0.1% of its selected section; combined endpoint truncation can be at most twice
those endpoint budgets. Tiny sections and large perimeters therefore get stricter
acceptance, not a global scalar-tolerance increase. Unresolvable or differently
serialized valid outputs can fail closed. Generic LengthParam semantics remain
unknown; 0..1 is not accepted as a line-local substitute for a nonfull-perimeter
section.

## Evidence and provenance

A retained authorized native group0 call returned true, incremented topology 0→1
and completed its export. The old analytic 1e-6 fraction comparison rejected one
endpoint at 1.296e-6 residual; same-run reported native lengths explain the untouched
output to at most 1.20e-8. Offline replay with manifest hash, witness bracket,
postread geometry and reference checks passes this profile. That replay neither
creates a verification marker for the consumed attempt nor authorizes continuing it.
Fresh live acceptance remains a separate parent-owned gate.

The historical two-group orientation fixture is **retained generated data**, not
independent host-authored physical sewing proof. Its exact analytic boundaries
cannot expose the native-versus-analytic length-model difference. Synthetic tests
cover native reordering/reversal, binary32/decimal fractions, missing/stale geometry,
just-outside-budget partials, physical caps, wrong LineID and direction. Native
endpoint/length matching does not prove hidden cubic internals; complete export
curve equality and same-run available-state checks remain separate requirements.
