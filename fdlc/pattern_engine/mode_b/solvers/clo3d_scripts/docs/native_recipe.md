# Bounded whole-section recipe (offline contract3)

`native_recipe.py` adds a small source-anatomy policy, not a second geometry mapper.
`native_whole_line.bind_recipe` resolves each internal execution position through
existing source/export correspondence and the same-run native geometry bijection.
`verify_recipe_result` reuses the fixed result kernel and its authenticated native
length budget. Fixed group0/adjacent1/group2 interfaces remain unchanged.

The bridge exposes **one** new handle-only operation, `pipeline_sew_advance`.
After the three verified fixed stages it selects the next position from exact
private directory membership, authenticates every predecessor and reverifies the
latest **complete** pairing set. The execution sequence is source groups0–9,
11–19: 19 calls total, excluding center_front. No caller stage, indices, directions,
path or batch length is accepted. No uncertain stage is retried.

## Endpoint policy, derived from construction

Source ordinals below refer only to `_build_front_lines`, `_build_back_lines`,
`_mirror_lines`, `_build_wb_piece` and `generate_5panel_json` in the pinned generator.
They are never native ordinals. Source geometry must have the expected panel and
group sets, mirrored full sections, closed adjacency, anatomical vertical order,
and rectangular two-half waistband topology. Existing correspondence additionally
checks full exported curves, both source coverage boundaries and disjoint occupancy.

| Source groups | Sections / anatomical endpoint pairs | Source traversal A/B |
|---|---|---|
| 0,5 side_top L/R | Back1/Front1: waist↔waist, hip↔hip | forward/forward |
| 1,6 side_hip_knee L/R | Back2/Front2: hip↔hip, knee↔knee | forward/forward |
| 2,7 side_knee_hem L/R | Back3/Front3: knee↔knee, hem↔hem | forward/forward |
| 3,8 inseam_straight L/R | Back5/Front5: hem↔hem, knee↔knee | forward/forward |
| 4,9 inseam_curve L/R | Back6/Front6: knee↔knee, crotch tip↔tip | forward/forward |
| 11 center_back | BL8/BR8: rise-base↔base, CB waist↔waist | forward/forward |
| 12 crotch_front | FL7/FR7: inseam tip↔tip, CF base↔base | forward/forward |
| 13 crotch_back | BL7/BR7: inseam tip↔tip, CB base↔base | forward/forward |
| 14 wb_front_to_FL | FL0/FWB1: center waist↔midpoint, side waist↔right end | forward/forward |
| 15 wb_front_to_FR | FWB0/FR0: left end↔side waist, midpoint↔center waist | forward/backward |
| 16 wb_back_to_BL | BWB0/BL0: left end↔side waist, midpoint↔center waist | forward/backward |
| 17 wb_back_to_BR | BR0/BWB1: center waist↔midpoint, side waist↔right end | forward/forward |
| 18 wb_side_R | FWB2/BWB4: bottom↔bottom, top↔top | forward/backward |
| 19 wb_side_L | FWB4/BWB2: top↔top, bottom↔bottom | forward/backward |

Right pieces are reflected in X **without reversing section traversal**. Waistband
half assignment follows the generator's corrected connectivity (FWB1→FL, FWB0→FR,
BWB0→BL, BWB1→BR). A panel waist runs center→side; the first waistband half runs
side→center and the second center→side. Thus blindly copying the first seams'
forward/forward policy would twist two waist attachments and both waistband ends.
The new flags are `source_forward XOR export_reversal XOR native_reversal`, not
legacy JSON Direction or descending fraction values. These anatomical endpoint
policies are reviewable construction interpretations, not independent host-authored
orientation or drape acceptance for the new families.

## Length/easing limitations

Do not equalize or trim lengths. Whole sections are retained unchanged, including
unequal front/back side/inseam lengths. The current generator sizes waistband halves
from its **legacy control-polygon ×1.15 proxy**, not physical curve arc length.
Retained size30 geometry shows waistband/front-waist excess ≈38.318231 mm and
waistband/back-waist excess ≈26.419192 mm per half. These are real recipe discrepancies,
not native fraction errors. The runner preserves that mismatch; it does **not** assert
that this amount or distribution of ease was intentional or acceptable in a garment.
No source easing parameter is supported; unexpected sewing fields, turned seams,
or changed fold parameters fail closed. A six-argument call and endpoint verification
do not prove fold strength, sewing tension, or physical easing distribution.

## Center-front: geometry candidates, no dispatch

Source group10 spans FL8–11 and FR8–11. For each left section the analyzer reflects
its full geometry, finds one unique right geometric match, checks equal physical
length, and requires a bijection. This is not ordinal-only pairing. In the retained
benchmark the four straight sections have corresponding junctions and zero total
length discrepancy, so **geometric candidates** exist for four whole-line pairs.

They remain excluded: replacing one source sewing group by four native groups can
alter grouping-dependent properties and local ease distribution; no host-authored
multi-section control or acceptance establishes that semantic equivalence. The
report sets `split_authorized=False`. A future approved split would require 23
native groups for the full 20-group source graph, explicit source-to-native coverage,
all intermediate endpoint correspondences, unchanged easing intent, and grouping
semantics review. Nineteen verified whole pairs are not twenty-group completion.

## Evidence meaning

Success means exact intended whole-section pairing graph, orientation and coverage
in a sealed export under the narrow observed native-length representation. Complete
cubic geometry and all prior pairings remain checked; same-count topology drift is
rejected before the next intent. It does not mean saved project persistence, JSON
replay, avatar arrangement, simulation, fit or physical drape.
