"""Offline seam injection; run on Mac, not inside CLO.

Usage: python3 02_inject_seams.py panels.json clo-export.json NEW-sewn.json
The output must not already exist. Input artifacts are never overwritten.
"""

import importlib.util
import json
import sys
from pathlib import Path

# Resolve the sibling by exact path, including importlib-based callers; no CLO imports.
_spec = importlib.util.spec_from_file_location(
    "mare_artifact_verifier", Path(__file__).with_name("verify_artifacts.py")
)
assert _spec is not None and _spec.loader is not None
_verifier = importlib.util.module_from_spec(_spec)
_spec.loader.exec_module(_verifier)


def inject_seams(panels_path: str, export_path: str, output_path: str) -> str:
    """Copy the export with geometry-resolved IDs and corrected seam fractions."""
    with open(panels_path) as stream:
        source = _verifier.parse(stream.read())
    with open(export_path) as stream:
        target = _verifier.parse(stream.read())
    result = _verifier.remap_seams(source, target)
    payload = json.dumps(result, indent=2, allow_nan=False)
    with open(output_path, "x") as stream:
        stream.write(payload)
    print(
        "Sewn artifact written; seam groups: "
        + str(len(result["SeamLinePairGroupList"]))
    )
    return output_path


if __name__ == "__main__":
    if len(sys.argv) != 4:
        print(__doc__, file=sys.stderr)
        raise SystemExit(1)
    try:
        inject_seams(*sys.argv[1:])
    except (ValueError, OSError):
        print(
            "Injection rejected: invalid inputs or unavailable new output.",
            file=sys.stderr,
        )
        raise SystemExit(1)
