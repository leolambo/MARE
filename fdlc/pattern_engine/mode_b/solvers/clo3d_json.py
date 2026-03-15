"""
CLO3D JSON Generator — measurements → complete CLO3D JSON with patterns + seams.

Usage:
    from clo3d_json import generate_clo3d_json
    generate_clo3d_json(measurements, "/path/to/output.json")

Then in CLO3D:
    import pattern_api
    pattern_api.ImportPatternJSON("/path/to/output.json")

One import = panels + sewing. Zero manual steps.
"""

from __future__ import annotations

import json
import math
import uuid
from pathlib import Path
from typing import List, Tuple

INCH_TO_MM = 25.4


def _uid():
    """Generate a short unique ID like CLO3D uses."""
    import random
    import string
    chars = string.ascii_letters + string.digits
    return ''.join(random.choices(chars, k=6))


def _ic(x_in, y_in):
    """Convert inches (Y-down) to CLO3D mm (Y-up)."""
    return (round(x_in * INCH_TO_MM, 2), round(-y_in * INCH_TO_MM, 2))


def _build_line(points_inch, point_types):
    """
    Build a CLO3D LineList entry.
    points_inch: list of (x, y) in inches
    point_types: list of "Straight" or "Bezier Curve" for each point
    """
    pts = []
    for (x, y), ptype in zip(points_inch, point_types):
        mx, my = _ic(x, y)
        pts.append({
            "ID": _uid(),
            "PointType": ptype,
            "Position": {"x": mx, "y": my},
            "GradingRuleID": 0,
        })
    return {"ID": _uid(), "PointList": pts}


def _cbez_line(p0, p1, p2, p3):
    """Cubic bezier as one CLO3D line (4 points: straight, curve, curve, straight)."""
    return _build_line(
        [p0, p1, p2, p3],
        ["Straight", "Bezier Curve", "Bezier Curve", "Straight"]
    )


def _straight_line(p0, p1):
    """Straight segment as one CLO3D line (2 points)."""
    return _build_line([p0, p1], ["Straight", "Straight"])


def _ensure_shared_points(lines):
    """Ensure consecutive lines share their endpoint/startpoint IDs."""
    for i in range(len(lines) - 1):
        # Last point of line i should have same ID as first point of line i+1
        lines[i+1]["PointList"][0]["ID"] = lines[i]["PointList"][-1]["ID"]
        lines[i+1]["PointList"][0]["Position"] = dict(lines[i]["PointList"][-1]["Position"])
    # Close: first point of line 0 should match last point of last line
    lines[0]["PointList"][0]["ID"] = lines[-1]["PointList"][-1]["ID"]
    lines[0]["PointList"][0]["Position"] = dict(lines[-1]["PointList"][-1]["Position"])
    return lines


def _build_front_lines(m):
    """Build front panel as list of CLO3D lines."""
    hip_y = 8.5
    CY = m["front_rise"]
    hem_y = m["outseam"]
    knee_y = hem_y - m["inseam"] * 0.52
    wh = m["waist"] / 2.0
    hh = m["hip"] / 2.0
    fw = wh * 0.48 + 1.0
    fhip = hh * 0.48 + 0.5
    fhem = m["leg_opening"] * 0.48
    fcx = hh * 0.125
    xsh = fhip
    xsk = fhem + 0.3
    ct = (-fcx, CY + 1.0)
    cfw = (0, 0.75)
    sw = (fw, -0.5)

    lines = []
    # 0: waist curve
    lines.append(_cbez_line(cfw, (fw*0.3, -0.8), (fw*0.65, -0.7), sw))
    # 1: side waist-to-hip
    lines.append(_cbez_line(sw, (xsh*0.7, hip_y*0.3), (xsh, hip_y*0.7), (xsh, hip_y)))
    # 2: side hip-to-knee
    lines.append(_cbez_line((xsh, hip_y), (xsh, hip_y+3), (xsk, knee_y-5), (xsk, knee_y)))
    # 3: side knee-to-hem
    lines.append(_straight_line((xsk, knee_y), (fhem, hem_y)))
    # 4: hem across
    lines.append(_straight_line((fhem, hem_y), (0, hem_y)))
    # 5: inseam hem-to-knee
    lines.append(_straight_line((0, hem_y), (0, knee_y)))
    # 6: inseam knee-to-crotch
    lines.append(_cbez_line((0, knee_y), (0.1, knee_y-6), (-fcx*0.5, ct[1]+3), ct))
    # 7: crotch curve
    lines.append(_cbez_line(ct, (-fcx, CY+0.1), (-fcx*0.5, CY), (0, CY)))
    # 8-11: CF seam (straight segments)
    steps = 4
    prev_y = CY
    for i in range(steps):
        t = (steps - 1 - i) / steps
        next_y = CY * t + cfw[1] * (1 - t)
        lines.append(_straight_line((0, prev_y), (0, next_y)))
        prev_y = next_y

    return _ensure_shared_points(lines)


def _build_back_lines(m, b_drop=1.9):
    """Build back panel as list of CLO3D lines."""
    hip_y = 8.5
    CY = m["front_rise"]
    hem_y = m["outseam"]
    knee_y = hem_y - m["inseam"] * 0.52
    wh = m["waist"] / 2.0
    hh = m["hip"] / 2.0
    bw = wh * 0.52 - 1.0
    bhip = hh * 0.52 + 1.5 - 3.4
    bhem = m["leg_opening"] * 0.52
    bcx = hh * 0.125 + 1.5
    xsh = bhip
    xsk = bhem + 0.3
    ct = (-bcx, CY + b_drop)
    cfw = (-2.0, -1.5)
    sw = (bw - 2.0, -0.3)

    lines = []
    # 0: waist curve
    lines.append(_cbez_line(cfw, (cfw[0]+bw*0.3, -1.2), (cfw[0]+bw*0.7, -0.6), sw))
    # 1: side waist-to-hip
    lines.append(_cbez_line(sw, (xsh*0.7, hip_y*0.3), (xsh, hip_y*0.7), (xsh, hip_y)))
    # 2: side hip-to-knee
    lines.append(_cbez_line((xsh, hip_y), (xsh, hip_y+3), (xsk, knee_y-5), (xsk, knee_y)))
    # 3: side knee-to-hem
    lines.append(_straight_line((xsk, knee_y), (bhem, hem_y)))
    # 4: hem across
    lines.append(_straight_line((bhem, hem_y), (0, hem_y)))
    # 5: inseam hem-to-knee
    lines.append(_straight_line((0, hem_y), (0, knee_y)))
    # 6: inseam knee-to-crotch
    lines.append(_cbez_line((0, knee_y), (0.1, knee_y-6), (-bcx*0.3, ct[1]+3), ct))
    # 7: crotch J-curve
    lines.append(_cbez_line(ct, (-bcx*0.5, CY+0.3), (-bcx*0.2, CY), (0, CY)))
    # 8: CB seam
    lines.append(_cbez_line((0, CY), (-0.5, CY*0.6), (-1.5, CY*0.3), cfw))

    return _ensure_shared_points(lines)


def _compute_line_lengths_mm(lines):
    """Approximate each line's length in mm for seam fraction calculation."""
    lengths = []
    for line in lines:
        pts = line["PointList"]
        # Simple chord-length approximation (good enough for fractions)
        total = 0
        for i in range(len(pts) - 1):
            dx = pts[i+1]["Position"]["x"] - pts[i]["Position"]["x"]
            dy = pts[i+1]["Position"]["y"] - pts[i]["Position"]["y"]
            total += math.hypot(dx, dy)
        # For bezier curves, actual arc is ~1.1-1.3x chord. Use 1.15 for 4-point curves.
        if len(pts) == 4:
            total *= 1.15
        lengths.append(total)
    return lengths


def _get_fracs(lengths):
    """Cumulative fractions [0, ..., 1.0] for each line boundary."""
    total = sum(lengths)
    fracs = [0.0]
    c = 0.0
    for l in lengths:
        c += l
        fracs.append(min(c / total, 1.0))  # clamp to avoid float rounding > 1.0
    return fracs


def _build_pattern(name, lines, fabric_uuid, offset_x=0):
    """Build a complete CLO3D pattern entry."""
    pattern_id = _uid()

    # Apply x offset to all points
    if offset_x != 0:
        for line in lines:
            for pt in line["PointList"]:
                pt["Position"]["x"] += offset_x

    return {
        "Name": name,
        "fGrainlineAngle": 0.0,
        "ID": pattern_id,
        "IsHalfSymmetric": False,
        "strGrainlineOrientation": "One Way",
        "strSuperImposeSide": "None",
        "CurrentFabricUUID": fabric_uuid,
        "IsClosed": True,
        "InternalLineList": [],
        "ButtonHeadList": [],
        "ButtonHoleList": [],
        "NotchList": [],
        "AnnotationList": [],
        "ShapeInfo": {
            "IsSlashed": False,
            "LineList": lines,
        },
        "ArrangementPointDataMap": {
            "PointName": "Arrangement Point",
            "fOffSetX": 0.0,
            "fOffSetY": 0.0,
            "fAngle": 0.0,
        },
    }, pattern_id


def _build_seams(front_id, back_id, f_fracs, b_fracs, f_line_count, b_line_count):
    """Build all seam pair groups."""
    # Matching seams by line index
    pairs = [
        ("side_top", 1, 1),
        ("side_hip_knee", 2, 2),
        ("side_knee_hem", 3, 3),
        ("inseam_straight", 5, 5),
        ("inseam_curve", 6, 6),
        ("crotch", 7, 7),
        ("waist", 0, 0),
    ]

    seams = []
    for name, fi, bi in pairs:
        seam = {
            "Name": name,
            "bIsTurned": False,
            "PairList": [{
                "First": {
                    "ShapeID": back_id,
                    "LengthParam": {"fStart": b_fracs[bi+1], "fEnd": b_fracs[bi]},
                    "Direction": False,
                },
                "Second": {
                    "ShapeID": front_id,
                    "LengthParam": {"fStart": f_fracs[fi+1], "fEnd": f_fracs[fi]},
                    "Direction": False,
                },
            }],
            "FoldData": {"iAngle": 180, "iStrength": 5},
        }
        seams.append(seam)

    # Center seam: front CF (lines 8 to f_line_count-1) ↔ back CB (line 8)
    seam = {
        "Name": "center_seam",
        "bIsTurned": False,
        "PairList": [{
            "First": {
                "ShapeID": back_id,
                "LengthParam": {"fStart": b_fracs[9], "fEnd": b_fracs[8]},
                "Direction": False,
            },
            "Second": {
                "ShapeID": front_id,
                "LengthParam": {"fStart": f_fracs[f_line_count], "fEnd": f_fracs[8]},
                "Direction": False,
            },
        }],
        "FoldData": {"iAngle": 180, "iStrength": 5},
    }
    seams.append(seam)

    return seams


def generate_clo3d_json(measurements: dict, output_path: str, b_drop: float = 1.9) -> str:
    """
    Generate a complete CLO3D-importable JSON from measurements.
    
    One import in CLO3D = patterns + sewing, zero manual steps.
    
    Args:
        measurements: dict with waist, hip, front_rise, inseam, outseam, leg_opening
        output_path: where to write the JSON file
        b_drop: back crotch drop (auto-tuned by pant_block solver)
    
    Returns:
        output file path
    """
    m = measurements
    fabric_uuid = _uid()

    # Build lines for each panel
    f_lines = _build_front_lines(m)
    b_lines = _build_back_lines(m, b_drop=b_drop)

    # Build patterns (back offset 500mm right)
    front_pattern, front_id = _build_pattern("Front_Panel", f_lines, fabric_uuid, offset_x=0)
    back_pattern, back_id = _build_pattern("Back_Panel", b_lines, fabric_uuid, offset_x=500)

    # Compute line lengths and fractions for seam mapping
    f_lengths = _compute_line_lengths_mm(f_lines)
    b_lengths = _compute_line_lengths_mm(b_lines)
    f_fracs = _get_fracs(f_lengths)
    b_fracs = _get_fracs(b_lengths)

    # Build seams
    seams = _build_seams(front_id, back_id, f_fracs, b_fracs, len(f_lines), len(b_lines))

    # Assemble full JSON
    clo_data = {
        "FabricList": [{
            "FabricName": "FABRIC 1",
            "FabricType": "None",
            "FabricContent": "None",
            "strBaseColorHexCode": "#FFFFFF",
            "FabricUUID": fabric_uuid,
        }],
        "GradingRuleTableList": [],
        "Unit": "mm",
        "PatternList": [front_pattern, back_pattern],
        "SymmetricDataList": [
            {"SymmetricPatternID": "None", "OriginPatternID": front_id},
            {"SymmetricPatternID": "None", "OriginPatternID": back_id},
        ],
        "InstanceDataList": [
            {"OriginPatternID": front_id, "InstancePatternIDArray": []},
            {"OriginPatternID": back_id, "InstancePatternIDArray": []},
        ],
        "SeamLinePairGroupList": seams,
    }

    out = Path(output_path)
    out.parent.mkdir(parents=True, exist_ok=True)
    with open(out, 'w') as f:
        json.dump(clo_data, f, indent=2)

    return str(out)


if __name__ == "__main__":
    m = {
        "waist": 30.0,
        "hip": 52.0,
        "front_rise": 12.75,
        "inseam": 28.5,
        "outseam": 40.5,
        "leg_opening": 23.5,
    }
    path = generate_clo3d_json(m, "/tmp/clo_auto.json")
    print("Generated: " + path)

    # Stats
    with open(path) as f:
        data = json.load(f)
    print("Patterns: " + str(len(data["PatternList"])))
    print("Seams: " + str(len(data["SeamLinePairGroupList"])))
    for s in data["SeamLinePairGroupList"]:
        print("  " + s["Name"])
