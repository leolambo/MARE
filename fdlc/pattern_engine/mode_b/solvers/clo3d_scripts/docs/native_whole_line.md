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
endpoint direction and both adjacent groups remain mandatory.

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
