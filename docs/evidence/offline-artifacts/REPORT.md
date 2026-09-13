# Offline artifact verifier evidence

Implementation issue: `mare-pipeline-mg3`. No CLO, MCP, plugin, service, SDK bridge,
or active project changes. Implementation is pending independent parent review;
no commit or push performed by the implementation subagent.

## Executed evidence

From `/Users/al/base/mare-pipeline`:

```bash
uv run --with pytest --with ezdxf python -m pytest \
  fdlc/pattern_engine/mode_b/solvers/test_clo3d_json.py \
  fdlc/pattern_engine/mode_b/solvers/test_pocket_clo3d.py \
  fdlc/pattern_engine/mode_b/solvers/clo3d_scripts/test_artifact_verifier.py -q
# 102 passed: original 61 plus 41 verifier/injector cases

uv run --with pytest --with ezdxf python -m pytest fdlc/pattern_engine/mode_b/solvers -q
# 269 passed, 1188 ezdxf DeprecationWarnings (closed -> close)
```

Original targeted baseline: 61 passed. TDD exposed the original string-replacement
bug (seam Name `a` became `c` and colliding remaps cascaded). Subsequent red/green
slices covered malformed/schema drift, duplicate names/IDs, strict directions and
fractions, missing references, physical whole-line reuse, unknown LengthParam
semantics, type-sensitive preservation and no-clobber outputs. Generator smoke
coverage exposed waistband outline entries with no IDs; those are accepted only
when no LineID resolution is required, preserving the existing six-panel route.

A separate stdlib-only CLI run on a tiny **synthetic** complete whole-LineID fixture
returned exit 0. Its manifest is `synthetic-complete-manifest.json`. The fixture is
reproducible via `fixture()` / `files()` in the test module; temporary source files
were discarded. It is not CLO import or integration proof. The actual six-panel
generator with synthetic export IDs also passed structural roundtrip tests (20
seam groups), while correctly remaining incomplete for physical edges.

## Real retained references: separate unstaged variants

Root: `/Users/al/base/creative/MAREv2/designs/wide-leg-twill-pants/analysis`.
Ran `python3 fdlc/pattern_engine/mode_b/solvers/clo3d_scripts/verify_artifacts.py
--artifact <root>/<filename>` separately for:

| File | Result | Manifest |
|---|---|---|
| `clo3d-working-wb-seams.json` | exit 2, incomplete, no structural errors | `clo3d-working-wb-seams-manifest.json` |
| `clo3d-working-wb-seams-short.json` | exit 2, incomplete, no structural errors | `clo3d-working-wb-seams-short-manifest.json` |

Each has 6 patterns, 20 seam groups and 40 seam sides. Before/after SHA-256 reads
matched for both original files. Both have physical-edge and roundtrip status
unknown, and all three proven stages missing. They were **not** treated as
successive stages or as a fabricated historical complete bundle. Manifests retain
fingerprints but no raw geometry, names, IDs or source paths.

## Independent review schema blocker fix

The review found that group key allowlisting did not validate metadata values.
`bIsTurned="not a boolean"` and `FoldData={"ShapeID":"missing"}` were accepted
and copied by `remap_seams`. Validation now checks all supported present group
metadata before either input can be remapped or an injection output opened:

- `Name`: string, without imposing identity/nonempty semantics on a seam label.
- `bIsTurned`: strict boolean (not integer 0/1 or truthy containers).
- `FoldData`: exactly `iAngle` and `iStrength`, both integers excluding booleans;
  unsupported nested references, extra/missing keys and other types are rejected.
- All three fields remain optional; supported metadata is copied unchanged.

Schema selection was grounded in `clo3d_json.py` seam builders and read-only
inspection of both retained variants above: each variant has 20 string-named
seam groups with `bIsTurned=false` and `FoldData={"iAngle":180,"iStrength":5}`.
No unsupported nested FoldData schema was inferred. Physical fold ranges and
CLO semantics are not asserted by these type checks.

TDD commands from the repository root (each red slice preceded its production
change):

```bash
uv run --with pytest --with ezdxf python -m pytest fdlc/pattern_engine/mode_b/solvers/clo3d_scripts/test_artifact_verifier.py -q -k group_turned
# RED: 6 failed (incomplete rather than invalid); GREEN: 6 passed
uv run --with pytest --with ezdxf python -m pytest fdlc/pattern_engine/mode_b/solvers/clo3d_scripts/test_artifact_verifier.py -q -k group_name --tb=no
# RED: 6 failed; same command without --tb=no GREEN: 6 passed
uv run --with pytest --with ezdxf python -m pytest fdlc/pattern_engine/mode_b/solvers/clo3d_scripts/test_artifact_verifier.py -q -k 'group_fold or supported_group' --tb=short
# RED: 32 failed (incomplete rather than invalid), 4 compatibility cases passed
uv run --with pytest --with ezdxf python -m pytest fdlc/pattern_engine/mode_b/solvers/clo3d_scripts/test_artifact_verifier.py -q
# GREEN: 89 passed, including all fold cases and generator compatibility
uv run --with pytest --with ezdxf python -m pytest -q
# FULL REPOSITORY: 317 passed, 1188 pre-existing ezdxf DeprecationWarnings
uv run --with ruff ruff check fdlc/pattern_engine/mode_b/solvers/clo3d_scripts/verify_artifacts.py fdlc/pattern_engine/mode_b/solvers/clo3d_scripts/test_artifact_verifier.py
# All checks passed!
git diff --check
# Passed
```

The new adversarial tests exercise verifier errors and injector refusal before
output creation, including invalid FoldData in both source and export. Fold and
boolean rejection cases also verify input bytes remain unchanged. Compatibility
cases preserve omitted metadata, empty/exact string labels, both boolean values,
and the observed historical fold structure. Existing generator smoke coverage
continues to pass.

Both retained CLI checks were rerun with `python3 .../verify_artifacts.py
--artifact <root>/<filename>` after the fix: exit 2, no structural errors, reports
identical to their stored manifests. SHA-256 before/after reads matched for each
original, and the manifests required no changes. No original fixture, CLO, MCP,
service or Beads state was changed. Issue `mare-pipeline-mg3` remains in progress
for parent review; no commit or push was performed.

## Limitations / review handoff

The historical complete bundle remains missing. There is no new CLO host proof.
LengthParam wrap, direction and physical edge correspondence are intentionally
unknown. Whole-LineID reuse is checked, not arbitrary interval encodings. See the
scripts README for the exact accepted schema and all assurance limitations.

One test invocation omitted `--with ezdxf` and failed package import; rerunning in
the declared uv environment succeeded. No system pip installation was used.
Static ruff checks and diff whitespace checks were run on changed code; independent
review is the parent's remaining gate before commit/push and issue closure.
