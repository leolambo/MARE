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
    # 1: side waist-to-hip (near-straight — control points along the diagonal)
    wx, wy = sw[0], sw[1]
    hx, hy = xsh, hip_y
    lines.append(_cbez_line(sw, (wx + (hx-wx)*0.33, wy + (hy-wy)*0.33), (wx + (hx-wx)*0.67, wy + (hy-wy)*0.67), (xsh, hip_y)))
    # 2: side hip-to-knee (smooth taper, no outward bulge)
    mid_x = xsh + (xsk - xsh) * 0.3
    mid_y = hip_y + (knee_y - hip_y) * 0.3
    lines.append(_cbez_line((xsh, hip_y), (mid_x, mid_y), (xsk, knee_y-5), (xsk, knee_y)))
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
    # 1: side waist-to-hip (near-straight — control points along the diagonal)
    wx, wy = sw[0], sw[1]
    hx, hy = xsh, hip_y
    lines.append(_cbez_line(sw, (wx + (hx-wx)*0.33, wy + (hy-wy)*0.33), (wx + (hx-wx)*0.67, wy + (hy-wy)*0.67), (xsh, hip_y)))
    # 2: side hip-to-knee (smooth taper, no outward bulge)
    mid_x = xsh + (xsk - xsh) * 0.3
    mid_y = hip_y + (knee_y - hip_y) * 0.3
    lines.append(_cbez_line((xsh, hip_y), (mid_x, mid_y), (xsk, knee_y-5), (xsk, knee_y)))
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


# CLO3D Auto 3D Arrangement name mapping
# These must match CLO3D's internal arrangement point dictionary exactly.
# Wrong names → pieces placed incorrectly (e.g. waistband at neck).
CLO3D_ARRANGEMENT_NAMES = {
    "Front_Panel":  {"PointName": "Leg_Front_L", "fOffSetX": 0.05, "fOffSetY": 0.05, "fAngle": 0.0},
    "Back_Panel":   {"PointName": "Leg_Back_L",  "fOffSetX": 0.05, "fOffSetY": 0.05, "fAngle": 0.0},
    "Front_Left":   {"PointName": "Leg_Front_L", "fOffSetX": 0.05, "fOffSetY": 0.05, "fAngle": 0.0},
    "Front_Right":  {"PointName": "Leg_Front_R", "fOffSetX": 0.05, "fOffSetY": 0.05, "fAngle": 0.0},
    "Back_Left":    {"PointName": "Leg_Back_L",  "fOffSetX": 0.05, "fOffSetY": 0.05, "fAngle": 0.0},
    "Back_Right":   {"PointName": "Leg_Back_R",  "fOffSetX": 0.05, "fOffSetY": 0.05, "fAngle": 0.0},
    "Waistband":    {"PointName": "Pants_Waistband", "fOffSetX": 0.0, "fOffSetY": 0.0, "fAngle": 0.0},
}


def _build_pattern(name, lines, fabric_uuid, offset_x=0):
    """Build a complete CLO3D pattern entry."""
    pattern_id = _uid()

    # Apply x offset to all points
    if offset_x != 0:
        for line in lines:
            for pt in line["PointList"]:
                pt["Position"]["x"] += offset_x

    # Set correct arrangement point name for Auto 3D Arrangement
    arr = CLO3D_ARRANGEMENT_NAMES.get(name, {"PointName": "Arrangement Point", "fOffSetX": 0.0, "fOffSetY": 0.0, "fAngle": 0.0})

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
        "ArrangementPointDataMap": arr,
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


def _mirror_lines(lines):
    """Mirror panel geometry by negating X coordinates for opposite leg."""
    mirrored = json.loads(json.dumps(lines))  # deep copy
    for line in mirrored:
        for pt in line["PointList"]:
            pt["Position"]["x"] = -pt["Position"]["x"]
            pt["ID"] = _uid()
    return mirrored


def _side_seam_line_lengths_mm(m):
    """Compute the CLO3D arc lengths (mm) of the three side seam lines (1, 2, 3).

    Line 1 = side_top (waist→hip), Line 2 = side_hip_knee, Line 3 = side_knee_hem.
    Used to locate the in-seam pocket opening in CLO3D frac space.
    """
    lines = _build_front_lines(m)
    return [_clo_bezier_arc_length(lines[i]) for i in [1, 2, 3]]


def _clo_bezier_arc_length(line, samples=32):
    """Approximate arc length of a CLO3D line in mm via de Casteljau sampling."""
    pts = line["PointList"]
    if len(pts) == 2:
        # Straight line
        dx = pts[1]["Position"]["x"] - pts[0]["Position"]["x"]
        dy = pts[1]["Position"]["y"] - pts[0]["Position"]["y"]
        return math.hypot(dx, dy)
    # Cubic bezier
    p = [(pt["Position"]["x"], pt["Position"]["y"]) for pt in pts]
    total = 0.0
    prev = p[0]
    for i in range(1, samples + 1):
        t = i / samples
        mt = 1 - t
        x = mt**3*p[0][0] + 3*mt**2*t*p[1][0] + 3*mt*t**2*p[2][0] + t**3*p[3][0]
        y = mt**3*p[0][1] + 3*mt**2*t*p[1][1] + 3*mt*t**2*p[2][1] + t**3*p[3][1]
        total += math.hypot(x - prev[0], y - prev[1])
        prev = (x, y)
    return total


def _pocket_opening_fracs(m, construction, f_fracs):
    """Compute CLO3D perimeter fracs for the in-seam pocket opening on the front panel.

    The opening sits on the side seam. We locate it by measuring along the side seam
    from the waist in mm, then converting to perimeter fracs.

    Returns (frac_open_top, frac_open_bot) in CLO3D perimeter space, or None if
    no in-seam pocket is configured.
    """
    if construction.get("pocket_type") != "in_seam":
        return None

    drop_in   = float(construction.get("in_seam_drop",   1.5))
    length_in = float(construction.get("in_seam_length", 7.0))
    drop_mm   = drop_in   * INCH_TO_MM
    length_mm = length_in * INCH_TO_MM

    # Side seam lines: 1=waist→hip, 2=hip→knee, 3=knee→hem
    # Walk along these lines from waist to locate opening endpoints.
    lines = _build_front_lines(m)
    line1_mm = _clo_bezier_arc_length(lines[1])
    line2_mm = _clo_bezier_arc_length(lines[2])
    line3_mm = _clo_bezier_arc_length(lines[3])
    side_total_mm = line1_mm + line2_mm + line3_mm

    # Total perimeter of the front panel for converting to global fracs
    all_lengths = [_clo_bezier_arc_length(line) for line in lines]
    perim_mm = sum(all_lengths)
    cumulative = [0.0]
    for l in all_lengths:
        cumulative.append(cumulative[-1] + l)

    # Opening top: drop_mm along the side seam from waist end of line 1
    # Line 1 starts at waist (its start = f_fracs[1] boundary)
    # Opening top is at frac_of_line1 = drop_mm / line1_mm (clamped to line 1)
    top_along_side = drop_mm
    bot_along_side = drop_mm + length_mm

    def _side_dist_to_perim_frac(dist_along_side):
        """Convert distance along the side seam (from waist) to panel perimeter frac."""
        # Side seam lines start at line 1's start = cumulative[1] from panel start
        abs_dist = cumulative[1] + dist_along_side
        return abs_dist / perim_mm

    frac_top = _side_dist_to_perim_frac(top_along_side)
    frac_bot = _side_dist_to_perim_frac(bot_along_side)

    # Clamp to side seam range [f_fracs[1], f_fracs[4]]
    frac_top = max(f_fracs[1], min(f_fracs[4], frac_top))
    frac_bot = max(f_fracs[1], min(f_fracs[4], frac_bot))

    return (round(frac_top, 5), round(frac_bot, 5))


def _build_in_seam_pocket_pieces(fabric_uuid, offset_x=1600, m=None, construction=None):
    """Build CLO3D pocket bag + facing pattern pieces for in-seam pocket.

    Returns (facing_pat, facing_id, bag_pat, bag_id) or None if no pocket.
    The facing is attached to the front panel at the opening.
    The bag hangs behind, sewn to the facing.

    For CLO3D simulation these are flat rectangular pieces — the solver's
    kidney shape is the IRL cut shape. CLO sims with simpler rectangles.
    """
    if not construction or construction.get("pocket_type") != "in_seam":
        return None

    length_in = float(construction.get("in_seam_length",      7.0))
    depth_in  = float(construction.get("in_seam_depth",      10.5))
    width_in  = float(construction.get("in_seam_width",       7.5))
    facing_in = float(construction.get("in_seam_facing_width", 1.5))

    length_mm = length_in * INCH_TO_MM
    depth_mm  = depth_in  * INCH_TO_MM
    width_mm  = width_in  * INCH_TO_MM
    facing_mm = facing_in * INCH_TO_MM

    def _rect_clo(name, w, h, offset_x):
        """Build a simple rectangular CLO3D pattern (5 lines, closed)."""
        def _pt(x, y):
            return {"ID": _uid(), "PointType": "Straight",
                    "Position": {"x": x + offset_x, "y": y}, "GradingRuleID": 0}
        # Lines: bottom, right, top, left — 4 lines, 2 pts each
        lines = [
            {"ID": _uid(), "PointList": [_pt(0, 0),    _pt(w, 0)]},    # 0: bottom
            {"ID": _uid(), "PointList": [_pt(w, 0),    _pt(w, h)]},    # 1: right
            {"ID": _uid(), "PointList": [_pt(w, h),    _pt(0, h)]},    # 2: top
            {"ID": _uid(), "PointList": [_pt(0, h),    _pt(0, 0)]},    # 3: left (= opening side)
        ]
        # Share endpoints between consecutive lines
        for i in range(len(lines) - 1):
            lines[i+1]["PointList"][0]["ID"] = lines[i]["PointList"][-1]["ID"]
            lines[i+1]["PointList"][0]["Position"] = dict(lines[i]["PointList"][-1]["Position"])
        lines[0]["PointList"][0]["ID"] = lines[-1]["PointList"][-1]["ID"]
        lines[0]["PointList"][0]["Position"] = dict(lines[-1]["PointList"][-1]["Position"])

        arr = {"PointName": "Arrangement Point", "fOffSetX": 0.0, "fOffSetY": 0.0, "fAngle": 0.0}
        pat_id = _uid()
        return {
            "Name": name,
            "fGrainlineAngle": 0.0,
            "ID": pat_id,
            "IsHalfSymmetric": False,
            "strGrainlineOrientation": "One Way",
            "strSuperImposeSide": "None",
            "CurrentFabricUUID": fabric_uuid,
            "IsClosed": True,
            "InternalLineList": [],
            "ButtonHeadList": [], "ButtonHoleList": [], "NotchList": [], "AnnotationList": [],
            "ShapeInfo": {"IsSlashed": False, "LineList": lines},
            "ArrangementPointDataMap": arr,
        }, pat_id

    facing_pat, facing_id = _rect_clo("Pocket_Facing_L", facing_mm, length_mm, offset_x)
    bag_pat,    bag_id    = _rect_clo("Pocket_Bag_L",    width_mm,  depth_mm,  offset_x + facing_mm + 50)

    return facing_pat, facing_id, bag_pat, bag_id


def _pocket_fracs_for_rect(w, h):
    """Perimeter fracs for a rectangle: [0=bottom-start, 1=bottom-end/right-start,
    2=right-end/top-start, 3=top-end/left-start, 4=left-end=1.0]"""
    perim = 2 * (w + h)
    return [0.0, w/perim, (w+h)/perim, (2*w+h)/perim, 1.0]


def _build_per_leg_seams(front_id, back_id, f_fracs, b_fracs, f_line_count, b_line_count,
                          pocket_fracs=None):
    """Build per-leg seams (side, inseam, waist) — excludes center/crotch.

    If pocket_fracs is provided as (frac_top, frac_bot), the side seam is split
    into three segments: above opening, [opening gap — omitted], below opening.
    This leaves the pocket opening open in the side seam for CLO3D simulation.
    """
    pairs = [
        ("side_top", 1, 1),
        ("side_hip_knee", 2, 2),
        ("side_knee_hem", 3, 3),
        ("inseam_straight", 5, 5),
        ("inseam_curve", 6, 6),
        ("waist", 0, 0),
    ]

    seams = []

    for name, fi, bi in pairs:
        # Side seam segments get special treatment when pocket is present
        if pocket_fracs and name in ("side_top", "side_hip_knee", "side_knee_hem"):
            pocket_top, pocket_bot = pocket_fracs
            seg_start = f_fracs[fi]
            seg_end   = f_fracs[fi + 1]

            # Check if this segment overlaps the pocket opening
            overlap_start = max(seg_start, pocket_top)
            overlap_end   = min(seg_end,   pocket_bot)

            if overlap_end <= overlap_start:
                # No overlap — sew full segment normally
                seams.append(_make_seam(name, back_id, b_fracs[bi], b_fracs[bi+1],
                                         front_id, f_fracs[fi], f_fracs[fi+1]))
            else:
                # Segment overlaps pocket opening — split into sewn parts
                # Part A: from seg_start to pocket_top (above opening)
                if pocket_top > seg_start + 0.001:
                    seams.append(_make_seam(
                        name + "_above",
                        back_id,  _remap(pocket_top,  seg_start, seg_end, b_fracs[bi], b_fracs[bi+1]),
                                  _remap(seg_start,   seg_start, seg_end, b_fracs[bi], b_fracs[bi+1]),
                        front_id, f_fracs[fi], pocket_top,
                    ))
                # Gap: pocket_top → pocket_bot — no seam (this is the opening)
                # Part B: from pocket_bot to seg_end (below opening)
                if pocket_bot < seg_end - 0.001:
                    seams.append(_make_seam(
                        name + "_below",
                        back_id,  _remap(seg_end,     seg_start, seg_end, b_fracs[bi], b_fracs[bi+1]),
                                  _remap(pocket_bot,  seg_start, seg_end, b_fracs[bi], b_fracs[bi+1]),
                        front_id, pocket_bot, f_fracs[fi+1],
                    ))
        else:
            seams.append(_make_seam(name, back_id, b_fracs[bi], b_fracs[bi+1],
                                     front_id, f_fracs[fi], f_fracs[fi+1]))

    return seams


def _remap(val, src_lo, src_hi, dst_lo, dst_hi):
    """Linear remap val from [src_lo, src_hi] → [dst_lo, dst_hi]."""
    if abs(src_hi - src_lo) < 1e-9:
        return dst_lo
    t = (val - src_lo) / (src_hi - src_lo)
    return dst_lo + t * (dst_hi - dst_lo)


def _make_seam(name, first_id, first_start, first_end, second_id, second_start, second_end):
    return {
        "Name": name,
        "bIsTurned": False,
        "PairList": [{
            "First":  {"ShapeID": first_id,
                       "LengthParam": {"fStart": first_start, "fEnd": first_end},
                       "Direction": False},
            "Second": {"ShapeID": second_id,
                       "LengthParam": {"fStart": second_start, "fEnd": second_end},
                       "Direction": False},
        }],
        "FoldData": {"iAngle": 180, "iStrength": 5},
    }


def _build_cross_leg_seams(fl_id, fr_id, bl_id, br_id, f_fracs, b_fracs, f_line_count):
    """Build cross-leg seams: center front (FL↔FR), center back (BL↔BR), crotch."""
    seams = []

    # Center front: FL CF ↔ FR CF (lines 8 to end on front panel)
    cf_frac = {"fStart": f_fracs[f_line_count], "fEnd": f_fracs[8]}
    seams.append({
        "Name": "center_front",
        "bIsTurned": False,
        "PairList": [{"First": {"ShapeID": fl_id, "LengthParam": dict(cf_frac), "Direction": False},
                       "Second": {"ShapeID": fr_id, "LengthParam": dict(cf_frac), "Direction": False}}],
        "FoldData": {"iAngle": 180, "iStrength": 5},
    })

    # Center back: BL CB ↔ BR CB (line 8 on back panel)
    cb_frac = {"fStart": b_fracs[9], "fEnd": b_fracs[8]}
    seams.append({
        "Name": "center_back",
        "bIsTurned": False,
        "PairList": [{"First": {"ShapeID": bl_id, "LengthParam": dict(cb_frac), "Direction": False},
                       "Second": {"ShapeID": br_id, "LengthParam": dict(cb_frac), "Direction": False}}],
        "FoldData": {"iAngle": 180, "iStrength": 5},
    })

    # Crotch front: FL crotch ↔ FR crotch (line 7 on front)
    cf_crotch = {"fStart": f_fracs[8], "fEnd": f_fracs[7]}
    seams.append({
        "Name": "crotch_front",
        "bIsTurned": False,
        "PairList": [{"First": {"ShapeID": fl_id, "LengthParam": dict(cf_crotch), "Direction": False},
                       "Second": {"ShapeID": fr_id, "LengthParam": dict(cf_crotch), "Direction": False}}],
        "FoldData": {"iAngle": 180, "iStrength": 5},
    })

    # Crotch back: BL crotch ↔ BR crotch (line 7 on back)
    cb_crotch = {"fStart": b_fracs[8], "fEnd": b_fracs[7]}
    seams.append({
        "Name": "crotch_back",
        "bIsTurned": False,
        "PairList": [{"First": {"ShapeID": bl_id, "LengthParam": dict(cb_crotch), "Direction": False},
                       "Second": {"ShapeID": br_id, "LengthParam": dict(cb_crotch), "Direction": False}}],
        "FoldData": {"iAngle": 180, "iStrength": 5},
    })

    return seams


def _build_wb_piece(name, width_mm, height_mm, fabric_uuid, offset_x=0):
    """Build a rectangular waistband piece for CLO3D sim (not for IRL cutting).

    5 lines: bottom-left, bottom-right, right side, top, left side.
    Bottom is split at midpoint so each half can sew to a different leg panel
    without violating the no-edge-overlap rule.
    """
    def _pt(x, y):
        return {"ID": _uid(), "PointType": "Straight", "Position": {"x": x, "y": y}, "GradingRuleID": 0}
    mid = width_mm / 2.0
    lines = [
        {"PointList": [_pt(0, 0), _pt(mid, 0)]},                     # 0: bottom-left (sews to left leg)
        {"PointList": [_pt(mid, 0), _pt(width_mm, 0)]},              # 1: bottom-right (sews to right leg)
        {"PointList": [_pt(width_mm, 0), _pt(width_mm, height_mm)]}, # 2: right side
        {"PointList": [_pt(width_mm, height_mm), _pt(0, height_mm)]},# 3: top
        {"PointList": [_pt(0, height_mm), _pt(0, 0)]},               # 4: left side
    ]
    return _build_pattern(name, lines, fabric_uuid, offset_x=offset_x)


def generate_5panel_json(measurements: dict, output_path: str, b_drop: float = 1.9,
                          construction: dict | None = None) -> str:
    """
    Generate CLO3D JSON: FL, FR, BL, BR + 2 waistband pieces + optional pocket pieces.

    CLO3D-specific: 2 waistband pieces for simulation.
    IRL pattern uses single waistband — see pant_block.py/dxf_export.py.

    Right panels have mirrored geometry. Seams include per-leg (side, inseam),
    cross-leg (center front/back, crotch), waistband-to-leg + WB-to-WB,
    and pocket seams when pocket_type="in_seam" is in construction.

    Args:
        measurements: body measurements dict
        output_path:  output file path
        b_drop:       back crotch drop (auto-tuned by pant_block solver)
        construction: optional construction config dict. Supports:
                      pocket_type="in_seam" to add in-seam front pocket seams.
                      in_seam_drop, in_seam_length, in_seam_depth, in_seam_width,
                      in_seam_facing_width to tune pocket dimensions.
    """
    m = measurements
    c = construction or {}
    fabric_uuid = _uid()

    # Left leg (original geometry), Right leg (mirrored)
    fl_lines = _build_front_lines(m)
    bl_lines = _build_back_lines(m, b_drop=b_drop)
    fr_lines = _mirror_lines(_build_front_lines(m))
    br_lines = _mirror_lines(_build_back_lines(m, b_drop=b_drop))

    fl_pat, fl_id = _build_pattern("Front_Left", fl_lines, fabric_uuid, offset_x=0)
    fr_pat, fr_id = _build_pattern("Front_Right", fr_lines, fabric_uuid, offset_x=400)
    bl_pat, bl_id = _build_pattern("Back_Left", bl_lines, fabric_uuid, offset_x=800)
    br_pat, br_id = _build_pattern("Back_Right", br_lines, fabric_uuid, offset_x=1200)

    # Compute fracs from clean (unmutated) lines
    f_clean = _build_front_lines(m)
    b_clean = _build_back_lines(m, b_drop=b_drop)
    f_lengths = _compute_line_lengths_mm(f_clean)
    b_lengths = _compute_line_lengths_mm(b_clean)
    f_fracs = _get_fracs(f_lengths)
    b_fracs = _get_fracs(b_lengths)

    # 2 waistband pieces: front WB (width = 2x front waist) and back WB (width = 2x back waist)
    wb_h = 2.0 * 25.4  # 2" waistband height in mm
    f_waist_mm = f_lengths[0]
    b_waist_mm = b_lengths[0]
    fwb_w = f_waist_mm * 2  # front WB spans both front panels
    bwb_w = b_waist_mm * 2  # back WB spans both back panels

    fwb_pat, fwb_id = _build_wb_piece("WB_Front", fwb_w, wb_h, fabric_uuid, offset_x=0)
    bwb_pat, bwb_id = _build_wb_piece("WB_Back", bwb_w, wb_h, fabric_uuid, offset_x=600)

    # WB fracs (5 lines: bottom-L, bottom-R, right, top, left)
    def _wb_fracs(w, h):
        half_w = w / 2.0
        perim = 2 * (w + h)
        return [0.0, half_w/perim, w/perim, (w+h)/perim, (2*w+h)/perim, 1.0]
    fwb_fracs = _wb_fracs(fwb_w, wb_h)
    bwb_fracs = _wb_fracs(bwb_w, wb_h)

    # ── Pocket fracs (in-seam front pocket) ──────────────────────────────
    pocket_fracs = _pocket_opening_fracs(m, c, f_fracs)

    # ── Per-leg seams (side split at opening if pocket present) ──────────
    left_seams  = _build_per_leg_seams(fl_id, bl_id, f_fracs, b_fracs, len(f_clean), len(b_clean),
                                        pocket_fracs=pocket_fracs)
    right_seams = _build_per_leg_seams(fr_id, br_id, f_fracs, b_fracs, len(f_clean), len(b_clean),
                                        pocket_fracs=pocket_fracs)
    left_seams  = [s for s in left_seams  if s["Name"] != "waist"]
    right_seams = [s for s in right_seams if s["Name"] != "waist"]
    for s in left_seams:
        s["Name"] += "_L"
    for s in right_seams:
        s["Name"] += "_R"

    # Cross-leg seams (center front/back, crotch)
    cross_seams = _build_cross_leg_seams(fl_id, fr_id, bl_id, br_id, f_fracs, b_fracs, len(f_clean))

    # Waistband-to-leg seams
    # Waistband-to-leg seams.
    # Validated against Leo's corrected CLO3D export (2026-03-22 short inseam).
    #
    # WB piece lines: 0=bottom-left, 1=bottom-right, 2=right-side, 3=top, 4=left-side
    # Leg panel line 0 = waist edge.
    #
    # Front WB: bottom-RIGHT (line 1) → FL, bottom-LEFT (line 0) → FR
    # Back WB:  bottom-LEFT (line 0) → BL, bottom-RIGHT (line 1) → BR
    #
    # Reference: designs/wide-leg-twill-pants/analysis/clo3d-working-wb-seams-short.json
    wb_seams = []

    # wb_front_to_FL: FL is First, WB bottom-RIGHT (line 1). Both Dir=True.
    wb_seams.append({
        "Name": "wb_front_to_FL",
        "bIsTurned": False,
        "PairList": [{
            "First": {
                "ShapeID": fl_id,
                "LengthParam": {"fStart": f_fracs[0], "fEnd": f_fracs[1]},
                "Direction": True,
            },
            "Second": {
                "ShapeID": fwb_id,
                "LengthParam": {"fStart": fwb_fracs[1], "fEnd": fwb_fracs[2]},
                "Direction": True,
            },
        }],
        "FoldData": {"iAngle": 180, "iStrength": 5},
    })

    # wb_front_to_FR: WB is First, WB bottom-LEFT (line 0). WB Dir=True, FR Dir=False.
    wb_seams.append({
        "Name": "wb_front_to_FR",
        "bIsTurned": False,
        "PairList": [{
            "First": {
                "ShapeID": fwb_id,
                "LengthParam": {"fStart": fwb_fracs[0], "fEnd": fwb_fracs[1]},
                "Direction": True,
            },
            "Second": {
                "ShapeID": fr_id,
                "LengthParam": {"fStart": f_fracs[1], "fEnd": f_fracs[0]},
                "Direction": False,
            },
        }],
        "FoldData": {"iAngle": 180, "iStrength": 5},
    })

    # wb_back_to_BL: WB is First, WB bottom-LEFT (line 0). WB Dir=True, BL Dir=False.
    wb_seams.append({
        "Name": "wb_back_to_BL",
        "bIsTurned": False,
        "PairList": [{
            "First": {
                "ShapeID": bwb_id,
                "LengthParam": {"fStart": bwb_fracs[0], "fEnd": bwb_fracs[1]},
                "Direction": True,
            },
            "Second": {
                "ShapeID": bl_id,
                "LengthParam": {"fStart": b_fracs[1], "fEnd": b_fracs[0]},
                "Direction": False,
            },
        }],
        "FoldData": {"iAngle": 180, "iStrength": 5},
    })

    # wb_back_to_BR: BR is First, WB bottom-RIGHT (line 1). Both Dir=False.
    wb_seams.append({
        "Name": "wb_back_to_BR",
        "bIsTurned": False,
        "PairList": [{
            "First": {
                "ShapeID": br_id,
                "LengthParam": {"fStart": b_fracs[1], "fEnd": b_fracs[0]},
                "Direction": False,
            },
            "Second": {
                "ShapeID": bwb_id,
                "LengthParam": {"fStart": bwb_fracs[2], "fEnd": bwb_fracs[1]},
                "Direction": False,
            },
        }],
        "FoldData": {"iAngle": 180, "iStrength": 5},
    })

    # WB-to-WB side seams connecting front and back waistband pieces.
    # Right side: FWB right-side (line 2) ↔ BWB left-side (line 4)
    # FWB Dir=False, BWB Dir=True
    wb_seams.append({
        "Name": "wb_side_R",
        "bIsTurned": False,
        "PairList": [{
            "First": {
                "ShapeID": fwb_id,
                "LengthParam": {"fStart": fwb_fracs[3], "fEnd": fwb_fracs[2]},
                "Direction": False,
            },
            "Second": {
                "ShapeID": bwb_id,
                "LengthParam": {"fStart": bwb_fracs[4], "fEnd": bwb_fracs[5]},
                "Direction": True,
            },
        }],
        "FoldData": {"iAngle": 180, "iStrength": 5},
    })

    # Left side: FWB left-side (line 4) ↔ BWB right-side (line 2)
    # FWB Dir=True, BWB Dir=False
    wb_seams.append({
        "Name": "wb_side_L",
        "bIsTurned": False,
        "PairList": [{
            "First": {
                "ShapeID": fwb_id,
                "LengthParam": {"fStart": fwb_fracs[4], "fEnd": fwb_fracs[5]},
                "Direction": True,
            },
            "Second": {
                "ShapeID": bwb_id,
                "LengthParam": {"fStart": bwb_fracs[3], "fEnd": bwb_fracs[2]},
                "Direction": False,
            },
        }],
        "FoldData": {"iAngle": 180, "iStrength": 5},
    })

    # ── In-seam pocket pieces + seams ────────────────────────────────────
    pocket_seams = []
    pocket_patterns = []

    # Two sets of pocket pieces — one per leg (L and R)
    # Each facing sewn to one front panel only, no shared references.
    pocket_result_L = _build_in_seam_pocket_pieces(fabric_uuid, offset_x=1600, m=m, construction=c)
    pocket_result_R = _build_in_seam_pocket_pieces(fabric_uuid, offset_x=1900, m=m, construction=c)

    if pocket_result_L and pocket_result_R and pocket_fracs:
        facing_pat_L, facing_id_L, bag_pat_L, bag_id_L = pocket_result_L
        facing_pat_R, facing_id_R, bag_pat_R, bag_id_R = pocket_result_R

        # Rename R pieces
        facing_pat_R["Name"] = "Pocket_Facing_R"
        bag_pat_R["Name"]    = "Pocket_Bag_R"

        pocket_patterns = [facing_pat_L, bag_pat_L, facing_pat_R, bag_pat_R]

        length_in = float(c.get("in_seam_length",      7.0))
        depth_in  = float(c.get("in_seam_depth",      10.5))
        width_in  = float(c.get("in_seam_width",       7.5))
        facing_in = float(c.get("in_seam_facing_width", 1.5))

        length_mm = length_in * INCH_TO_MM
        depth_mm  = depth_in  * INCH_TO_MM
        width_mm  = width_in  * INCH_TO_MM
        facing_mm = facing_in * INCH_TO_MM

        facing_pf = _pocket_fracs_for_rect(facing_mm, length_mm)
        bag_pf    = _pocket_fracs_for_rect(width_mm,  depth_mm)
        frac_top, frac_bot = pocket_fracs

        # FL ↔ Facing_L (left edge of facing, line 3)
        pocket_seams.append(_make_seam(
            "pocket_FL_to_facing",
            fl_id,       frac_top,        frac_bot,
            facing_id_L, facing_pf[3],    facing_pf[4],
        ))

        # FR ↔ Facing_R (left edge of facing, line 3)
        pocket_seams.append(_make_seam(
            "pocket_FR_to_facing",
            fr_id,       frac_top,        frac_bot,
            facing_id_R, facing_pf[3],    facing_pf[4],
        ))

        # Facing_L top ↔ Bag_L top
        pocket_seams.append(_make_seam(
            "pocket_facing_to_bag_top_L",
            facing_id_L, facing_pf[1], facing_pf[2],
            bag_id_L,    bag_pf[1],    bag_pf[2],
        ))

        # Facing_L bottom ↔ Bag_L bottom
        pocket_seams.append(_make_seam(
            "pocket_facing_to_bag_bot_L",
            facing_id_L, facing_pf[0], facing_pf[1],
            bag_id_L,    bag_pf[0],    bag_pf[1],
        ))

        # Facing_R top ↔ Bag_R top
        pocket_seams.append(_make_seam(
            "pocket_facing_to_bag_top_R",
            facing_id_R, facing_pf[1], facing_pf[2],
            bag_id_R,    bag_pf[1],    bag_pf[2],
        ))

        # Facing_R bottom ↔ Bag_R bottom
        pocket_seams.append(_make_seam(
            "pocket_facing_to_bag_bot_R",
            facing_id_R, facing_pf[0], facing_pf[1],
            bag_id_R,    bag_pf[0],    bag_pf[1],
        ))

    all_seams = left_seams + right_seams + cross_seams + wb_seams + pocket_seams
    patterns = [fl_pat, fr_pat, bl_pat, br_pat, fwb_pat, bwb_pat] + pocket_patterns
    pat_ids = [p["ID"] for p in patterns]

    clo_data = {
        "FabricList": [{"FabricName": "FABRIC 1", "FabricType": "None", "FabricContent": "None",
                         "strBaseColorHexCode": "#FFFFFF", "FabricUUID": fabric_uuid}],
        "GradingRuleTableList": [],
        "Unit": "mm",
        "PatternList": patterns,
        "SymmetricDataList": [{"SymmetricPatternID": "None", "OriginPatternID": pid} for pid in pat_ids],
        "InstanceDataList": [{"OriginPatternID": pid, "InstancePatternIDArray": []} for pid in pat_ids],
        "SeamLinePairGroupList": all_seams,
    }

    out = Path(output_path)
    out.parent.mkdir(parents=True, exist_ok=True)
    with open(out, 'w') as f:
        json.dump(clo_data, f, indent=2)

    return str(out)


if __name__ == "__main__":
    m = {
        "waist": 30.0,
        "hip": 42.0,          # 21" flat × 2 (bag measurement)
        "front_rise": 10.75,  # waist seam to crotch (excludes 2" waistband)
        "inseam": 30.0,       # short
        "outseam": 40.0,
        "leg_opening": 23.5,
    }
    path = generate_5panel_json(m, "/tmp/clo_5panel_auto.json")
    print("Generated: " + path)

    with open(path) as f:
        data = json.load(f)
    print("Patterns: " + str(len(data["PatternList"])))
    print("Seams: " + str(len(data["SeamLinePairGroupList"])))
    for s in data["SeamLinePairGroupList"]:
        print("  " + s["Name"])
