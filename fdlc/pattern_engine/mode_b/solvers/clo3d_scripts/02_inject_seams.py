#!/usr/bin/env python3
"""
Seam injection script — run on Mac, NOT in CLO3D.

Reads the generated panels JSON and CLO3D's export JSON,
remaps pattern IDs, injects seams, writes the sewn JSON.

Usage:
    python3 02_inject_seams.py <panels.json> <export.json> <sewn_output.json>

Or import and call inject_seams() directly.
"""

import json
import sys


def inject_seams(panels_path: str, export_path: str, output_path: str) -> str:
    """Inject seams from panels JSON into CLO3D export, remapping pattern IDs.

    Args:
        panels_path: path to our generated JSON (has seams with our IDs)
        export_path: path to CLO3D's export JSON (has real IDs)
        output_path: path to write the sewn JSON

    Returns:
        output file path
    """
    with open(panels_path) as f:
        our_data = json.load(f)
    with open(export_path) as f:
        clo_data = json.load(f)

    # Build ID remap: our ID → CLO3D's ID, matched by pattern name
    our_name_to_id = {p["Name"]: p["ID"] for p in our_data["PatternList"]}
    clo_name_to_id = {
        p["Name"]: (p.get("ShapeID") or p.get("ID"))
        for p in clo_data["PatternList"]
    }

    id_remap = {}
    for name in our_name_to_id:
        if name in clo_name_to_id:
            id_remap[our_name_to_id[name]] = clo_name_to_id[name]

    # Deep-replace all ShapeID references in seams
    seams = our_data["SeamLinePairGroupList"]
    seams_json = json.dumps(seams)
    for old_id, new_id in id_remap.items():
        seams_json = seams_json.replace('"' + old_id + '"', '"' + new_id + '"')
    seams = json.loads(seams_json)

    # Inject into CLO3D export (preserves CLO3D's arrangement data)
    clo_data["SeamLinePairGroupList"] = seams

    with open(output_path, "w") as f:
        json.dump(clo_data, f, indent=2)

    print(f"Sewn: {output_path}, Seams: {len(seams)}")
    return output_path


if __name__ == "__main__":
    if len(sys.argv) != 4:
        print("Usage: python3 02_inject_seams.py <panels.json> <export.json> <sewn_output.json>")
        sys.exit(1)
    inject_seams(sys.argv[1], sys.argv[2], sys.argv[3])
