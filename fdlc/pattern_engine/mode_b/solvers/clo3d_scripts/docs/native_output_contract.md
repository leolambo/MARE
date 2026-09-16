# Native coupled-field output contract

This is an **SDK-request/output check for the observed native export profile**.
It does not establish physical endpoint correspondence, drape, fit, persistence,
or universal CLO JSON `Direction` semantics. The generic generated-JSON
correspondence solver and its historical fixtures are unchanged.

## Request to output

The exact SDK 2026.1.224 `PatternAPIInterface.h:1314–1316` documents each
`AddSeamlinePairGroup` boolean as true=forward, false=backward. The recipe binder
transforms its anatomical traversal into a native boolean:

```
sdk_direction = source_forward XOR source_to_before_export_reversed
                               XOR before_export_to_native_reversed
export_forward = sdk_direction XOR after_export_to_native_reversed
```

In the native-only profile, **both** of these must match `export_forward`:

* interval order (ascending whole section for true; descending for false);
* raw `Direction` boolean.

They are coupled output fields, not two independent reversal operators. Checking
`interval_forward == Direction` as the endpoint direction cancelled a real
backward request and incorrectly accepted some doubly-wrong output records.
Both single-field corruption and flipping both fields now fail. Orientation is
transformed by geometry bijections, not ShapeID equality or array ordinals.

`verify_fixed_result` / `verify_recipe_result` require keyword `requests`, an
ordered list of the exact SDK request dictionaries. They enforce strict types,
exact fields and equality to the bounded recipe's native bindings before checking
output. `verify_native_output` is a pure, lower-level native-output check; it does
not enforce anatomical policy and is not a public bridge command. It also requires
explicit requests and cannot authenticate arbitrary dictionaries itself.

The bridge authenticates every predecessor manifest, reconstructs each reference
from the recipe and retained full geometry/topology, and requires byte-for-byte
equality to its retained SDK reference before passing those request arguments.
The current reference is checked unchanged after native output, and the exact
in-memory submitted binding is passed to verification. Existing private-file,
clean-pin, same-run export bracket, identity/geometry/topology, native signature,
SDK result, counts, durable intent/one-shot and no-retry checks remain mandatory.
No retrospective marker is created for historical failed or diagnostic attempts.

## Evidence and limits

Retained production stages 0–14 and the fixed WB_Front/Front_Right true/true
control pass read-only replay against their own authenticated references and
same-run native lengths. The true/false attachment has descending Front_Right
interval `0.077108786 -> 0`, raw false; the true/true control has ascending
`0 -> 0.077108786`, raw true. WB_Front remains ascending/raw true. Both target
native reversal flags are false, with matching native lines, full geometry
bijections and identical target native line-info bytes.

The contrast is **not a perfectly isolated causal experiment**: prior seam counts
were 14 versus 0, with different contracts and disposable projects. It supports
this narrow output contract, not a universal schema interpretation. Synthetic
truth-table tests exercise native and export reversals explicitly; they are
coordinate-transform regressions, not additional host reversal observations.
A fresh same-baseline true/false control could strengthen evidence, but is not
required to correct the cancellation in this scoped output check. Fresh full-run
acceptance and physical garment inspection are separate parent-owned milestones.

Historical generated JSON can encode traversal with ascending/opposite-Direction
or descending/opposite-Direction alternatives. Native-only tests no longer treat
these as native observations; the generic generated-JSON verifier is not weakened
or rewritten to adopt this profile.

## Unchanged numerical and geometry gates

Full straight/cubic before/after correspondence; uniquely mapped native endpoint
and length evidence; unique LineIDs; exact counts/pairing; no unknown/ambiguous
representations. Native-length cumulative fractions use `math.fsum` and each
endpoint tolerance remains:

```
min(2**-23 + 5e-10, 0.001 / perimeter_mm,
    0.001 * section_length_mm / perimeter_mm)
```

No analytic fallback, global tolerance increase, partial-section acceptance or
center-front splitting. Wrong line, coverage, ambiguity and malformed/missing
requests fail closed. Offline replay hashes retained artifacts before and after;
no CLO reads, sewing, deployment, restart, checkpoint read or project save occurs.
