#!/usr/bin/env python3
"""Trouser block solver for Mode B parametric generation.
v21 — validated via visual verification loop (see PATTERN-DRAFTING-FINDINGS.md)."""

from __future__ import annotations

import json
import math
from pathlib import Path
from typing import Any, Dict, List, Tuple

import ezdxf
from ezdxf.math import offset_vertices_2d

try:
    from ezdxf.enums import TextEntityAlignment as _TEA
    _TEXT_ALIGN = _TEA.MIDDLE_CENTER
except ImportError:
    _TEXT_ALIGN = "MIDDLE_CENTER"

Point = Tuple[float, float]

LAYER_CUT = "CUT"
LAYER_SA = "SEAM_ALLOWANCE"
LAYER_GRAIN = "GRAIN"
LAYER_NOTCH = "NOTCH"
LAYER_INTERNAL = "INTERNAL"
LAYER_TEXT = "TEXT"

DEFAULT_CONSTRUCTION = {
    "seam_allowance": 0.625,
    "hem_allowance": 1.5,
    "waistband_width": 1.75,
    "pocket_type": "slash",
    "pocket_angle_deg": 30,
    "back_pocket_type": "single_welt",
    "fly_type": "standard_zip",
    "dart_count_back": 0,
}

DEFAULT_EASE = {"waist": 1.0, "hip": 2.0, "thigh": 2.0}


# ---------------------------------------------------------------------------
# Bezier helpers
# ---------------------------------------------------------------------------

def _qbez(p0: Point, p1: Point, p2: Point, steps: int = 32) -> List[Point]:
    """Quadratic bezier."""
    return [((1-t)**2*p0[0]+2*(1-t)*t*p1[0]+t**2*p2[0],
             (1-t)**2*p0[1]+2*(1-t)*t*p1[1]+t**2*p2[1])
            for t in [i/steps for i in range(steps+1)]]


def _cbez(p0: Point, p1: Point, p2: Point, p3: Point, steps: int = 40) -> List[Point]:
    """Cubic bezier — preferred for anatomical curves (G1 continuity)."""
    return [((1-t)**3*p0[0]+3*(1-t)**2*t*p1[0]+3*(1-t)*t**2*p2[0]+t**3*p3[0],
             (1-t)**3*p0[1]+3*(1-t)**2*t*p1[1]+3*(1-t)*t**2*p2[1]+t**3*p3[1])
            for t in [i/steps for i in range(steps+1)]]


def _dist(a: Point, b: Point) -> float:
    return math.hypot(b[0]-a[0], b[1]-a[1])


def _polyline_length(points) -> float:
    pts = list(points)
    return sum(_dist(pts[i], pts[i+1]) for i in range(len(pts)-1))


def _bbox(points) -> tuple:
    pts = list(points)
    xs = [p[0] for p in pts]; ys = [p[1] for p in pts]
    return min(xs), min(ys), max(xs), max(ys)


def _closed_offset(poly: List[Point], offset: float) -> List[Point]:
    pts = list(poly)
    if pts[0] != pts[-1]:
        pts = pts + [pts[0]]
    result = list(offset_vertices_2d(pts, offset=offset, closed=True))
    return [(float(x), float(y)) for x, y in result]


# ---------------------------------------------------------------------------
# Panel builders
# ---------------------------------------------------------------------------

def _build_front_panel(m: dict, c: dict, e: dict) -> dict:
    """Build front trouser panel using validated v21 geometry."""
    hip_y = 8.5
    CROTCH_Y = float(m["front_rise"])
    hem_y = float(m["outseam"])
    knee_y = hem_y - float(m["inseam"]) * 0.52
    
    waist_half = float(m["waist"]) / 2.0
    hip_half = float(m["hip"]) / 2.0
    
    # Panel widths — leg_opening is FLAT half-circumference (DO NOT halve again!)
    f_waist = waist_half * 0.48 + 1.0         # ~8.0"
    f_hip = hip_half * 0.48 + 0.5             # ~13.5"
    f_hem = float(m["leg_opening"]) * 0.48    # ~11.3" for wide-leg
    f_cext = hip_half * 0.125                 # ~3.25"
    
    # Key x positions
    x_sh = f_hip        # side hip (widest)
    x_sk = f_hem + 0.3  # side knee
    x_se = f_hem         # side hem
    
    # Crotch tip: drops 1.0" below crotch line
    ct = (-f_cext, CROTCH_Y + 1.0)
    
    # WAISTLINE: concave — CF dips, side rises
    cf_w = (0, 0.75)
    sw = (f_waist, -0.5)
    wc = _cbez(cf_w, (f_waist*0.3, -0.8), (f_waist*0.65, -0.7), sw, 16)
    
    # CF SEAM: straight vertical x=0 from waist to crotch
    cf_seam = [(0, cf_w[1] + i*(CROTCH_Y-cf_w[1])/10) for i in range(11)]
    
    # CROTCH J-CURVE: smooth cubic from (0, CROTCH_Y) to crotch tip
    cc = _cbez((0, CROTCH_Y), (-f_cext*0.5, CROTCH_Y), (-f_cext, CROTCH_Y+0.1), ct, 32)
    
    # INSEAM: smooth cubic from crotch tip to (0, knee_y)
    ic = _cbez(ct, (-f_cext*0.5, ct[1]+3), (0.1, knee_y-6), (0, knee_y), 32)
    
    # SIDE SEAM: smooth cubic curves
    st = _cbez(sw, (x_sh*0.7, hip_y*0.3), (x_sh, hip_y*0.7), (x_sh, hip_y), 24)
    sm = _cbez((x_sh, hip_y), (x_sh, hip_y+3), (x_sk, knee_y-5), (x_sk, knee_y), 24)
    
    # Measure seam lengths
    inseam_len = _polyline_length(ic) + abs(hem_y - knee_y)
    side_len = _polyline_length(st) + _polyline_length(sm) + math.hypot(x_sk-x_se, knee_y-hem_y)
    
    # Assemble outline
    outline = list(wc)
    outline += st[1:]
    outline += sm[1:]
    outline += [(x_se, hem_y), (0, hem_y), (0, knee_y)]
    outline += list(reversed(ic))[1:]
    outline += list(reversed(cc))[1:]
    outline += list(reversed(cf_seam))[1:]
    outline += [wc[0]]
    
    # Internal lines (pocket)
    pocket_drop = 1.0
    pocket_len = 6.5
    pocket_angle = math.radians(c.get("pocket_angle_deg", 30))
    pocket_a = (f_waist, -0.5 + pocket_drop)
    pocket_b = (f_waist - math.cos(pocket_angle)*pocket_len,
                -0.5 + pocket_drop + math.sin(pocket_angle)*pocket_len)
    
    x0, y0, x1, y1 = _bbox(outline)
    grain_x = f_hem / 2.0
    
    return {
        "name": "front_panel",
        "count": 2,
        "mirror": True,
        "cut": outline,
        "grainline": [(grain_x, hip_y), (grain_x, hem_y - 2.0)],
        "internal_lines": [[pocket_a, pocket_b]],
        "notches": [((x_sk, knee_y), "knee"), ((0, knee_y), "knee")],
        "label_pos": ((x0+x1)/2, (y0+y1)/2),
        "meta": {
            "crotch_extension": f_cext,
            "inseam_length": inseam_len,
            "side_length": side_len,
            "hem_width": f_hem,
            "hip_width": f_hip,
        },
    }


def _build_back_panel(m: dict, c: dict, e: dict, b_drop: float = 1.9) -> dict:
    """Build back trouser panel using validated v21 geometry."""
    hip_y = 8.5
    CROTCH_Y = float(m["front_rise"])  # SHARED crotch line!
    hem_y = float(m["outseam"])
    knee_y = hem_y - float(m["inseam"]) * 0.52
    
    waist_half = float(m["waist"]) / 2.0
    hip_half = float(m["hip"]) / 2.0
    
    b_waist = waist_half * 0.52 - 1.0
    b_hip = hip_half * 0.52 + 1.5 - 3.4  # after side_tuck
    b_hem = float(m["leg_opening"]) * 0.52
    b_cext = hip_half * 0.125 + 1.5
    
    x_sh = b_hip
    x_sk = b_hem + 0.3
    x_se = b_hem
    
    # Crotch tip: drops b_drop below SHARED crotch line
    ct = (-b_cext, CROTCH_Y + b_drop)
    
    # WAISTLINE: CB raised and shifted left
    cf_w = (-2.0, -1.5)
    sw = (b_waist - 2.0, -0.3)
    wc = _cbez(cf_w, (cf_w[0]+b_waist*0.3, -1.2), (cf_w[0]+b_waist*0.7, -0.6), sw, 16)
    
    # CB SEAM + CROTCH: ONE continuous cubic (no kink at junction)
    cb_to_crotch = _cbez(cf_w, (-1.0, CROTCH_Y*0.5), (-1.0, CROTCH_Y), ct, 48)
    
    # INSEAM
    ic = _cbez(ct, (-b_cext*0.3, ct[1]+3), (0.1, knee_y-6), (0, knee_y), 32)
    
    # SIDE SEAM
    st = _cbez(sw, (x_sh*0.7, hip_y*0.3), (x_sh, hip_y*0.7), (x_sh, hip_y), 24)
    sm = _cbez((x_sh, hip_y), (x_sh, hip_y+3), (x_sk, knee_y-5), (x_sk, knee_y), 24)
    
    inseam_len = _polyline_length(ic) + abs(hem_y - knee_y)
    side_len = _polyline_length(st) + _polyline_length(sm) + math.hypot(x_sk-x_se, knee_y-hem_y)
    
    outline = list(wc)
    outline += st[1:]
    outline += sm[1:]
    outline += [(x_se, hem_y), (0, hem_y), (0, knee_y)]
    outline += list(reversed(ic))[1:]
    outline += list(reversed(cb_to_crotch))[1:]
    outline += [wc[0]]
    
    x0, y0, x1, y1 = _bbox(outline)
    grain_x = b_hem / 2.0
    
    # Back pocket welt
    pocket_y = hip_y + 2.25
    pocket_w = 5.5
    pocket_x = b_hip * 0.5
    welt = [(pocket_x - pocket_w/2, pocket_y), (pocket_x + pocket_w/2, pocket_y)]
    
    return {
        "name": "back_panel",
        "count": 2,
        "mirror": True,
        "cut": outline,
        "grainline": [(grain_x, hip_y), (grain_x, hem_y - 2.0)],
        "internal_lines": [welt],
        "notches": [((x_sk, knee_y), "knee"), ((0, knee_y), "knee")],
        "label_pos": ((x0+x1)/2, (y0+y1)/2),
        "meta": {
            "crotch_extension": b_cext,
            "inseam_length": inseam_len,
            "side_length": side_len,
            "hem_width": b_hem,
            "hip_width": b_hip,
            "b_drop": b_drop,
        },
    }


def _match_seams(m: dict, c: dict, e: dict) -> tuple:
    """Build front, then adjust back b_drop until inseams match."""
    front = _build_front_panel(m, c, e)
    target_inseam = front["meta"]["inseam_length"]
    
    best_drop = 1.9
    best_err = 999
    for d10 in range(5, 45):
        d = d10 * 0.1
        back = _build_back_panel(m, c, e, b_drop=d)
        err = abs(back["meta"]["inseam_length"] - target_inseam)
        if err < best_err:
            best_err = err
            best_drop = d
    
    back = _build_back_panel(m, c, e, b_drop=best_drop)
    return front, back


def _rect_piece(name: str, width: float, height: float, *, count: int = 1, mirror: bool = False, fold: bool = False) -> dict:
    cut = [(0, 0), (width, 0), (width, height), (0, height), (0, 0)]
    return {
        "name": name, "count": count, "mirror": mirror,
        "cut": cut,
        "grainline": [(width/2, 0.5), (width/2, max(0.5, height-0.5))],
        "internal_lines": [], "notches": [],
        "label_pos": (width/2, height/2),
        "meta": {"cut_on_fold": fold},
    }


def solve(measurements: dict, construction: dict | None = None, ease: dict | None = None) -> dict:
    """Main solver entry point."""
    c = {**DEFAULT_CONSTRUCTION, **(construction or {})}
    e = {**DEFAULT_EASE, **(ease or {})}
    m = dict(measurements)
    
    required = ["waist", "hip", "front_rise", "inseam", "outseam", "thigh", "leg_opening", "fly_length"]
    missing = [k for k in required if m.get(k) in (None, "")]
    if missing:
        raise ValueError(f"Missing measurements: {', '.join(missing)}")
    
    m["back_rise"] = float(m.get("back_rise") or (float(m["front_rise"]) + 2.0))
    if m.get("knee") in (None, ""):
        m["knee"] = (float(m["thigh"]) + float(m["leg_opening"])) / 2.0
    
    front, back = _match_seams(m, c, e)
    
    # Auxiliary pieces
    wb_len = float(m["waist"]) + e["waist"] + c["seam_allowance"] * 2.0
    wb_h = c["waistband_width"] * 2.0
    waistband = _rect_piece("waistband", wb_len/2, wb_h, count=1, fold=True)
    
    fly_len = float(m["fly_length"])
    fly_shield = {
        "name": "fly_shield", "count": 1, "mirror": False,
        "cut": [(0,0), (2.5,0)] + _qbez((2.5,0), (1.7,fly_len*0.65), (0.5,fly_len), 20) + [(0,fly_len), (0,0)],
        "grainline": [(1.25, 0.5), (1.25, fly_len-0.5)],
        "internal_lines": [], "notches": [],
        "label_pos": (1.25, fly_len*0.45),
        "meta": {},
    }
    fly_ext = _rect_piece("fly_extension", 1.5, fly_len)
    pocket_bag = _rect_piece("front_pocket_bag", 6.0, 10.5, count=2, mirror=True)
    back_welt = _rect_piece("back_pocket_welt", 5.5, 1.5, count=2, mirror=True)
    back_bag = _rect_piece("back_pocket_bag", 6.0, 7.0, count=2, mirror=True)
    belt_loop = _rect_piece("belt_loop_strip", 17.5, 1.5)
    
    pieces = [front, back, waistband, fly_shield, fly_ext, pocket_bag, back_welt, back_bag, belt_loop]
    
    for piece in pieces:
        piece["seam_allowance"] = c["seam_allowance"]
        piece["hem_allowance"] = c["hem_allowance"] if "panel" in piece["name"] else 0.0
        try:
            piece["seam_outline"] = _closed_offset(piece["cut"], c["seam_allowance"])
        except Exception:
            piece["seam_outline"] = []
    
    return {
        "garment_type": "wide_leg_pants",
        "unit": "inches",
        "measurements": m,
        "construction": c,
        "ease": e,
        "pieces": pieces,
        "validation": {
            "front_inseam": round(front["meta"]["inseam_length"], 3),
            "back_inseam": round(back["meta"]["inseam_length"], 3),
            "front_side": round(front["meta"]["side_length"], 3),
            "back_side": round(back["meta"]["side_length"], 3),
            "inseam_delta": round(abs(front["meta"]["inseam_length"] - back["meta"]["inseam_length"]), 3),
            "side_delta": round(abs(front["meta"]["side_length"] - back["meta"]["side_length"]), 3),
            "b_drop": back["meta"]["b_drop"],
        },
    }


# ---------------------------------------------------------------------------
# DXF annotation helpers
# ---------------------------------------------------------------------------

def _vnorm(v: Point) -> Point:
    """Normalize a 2D vector."""
    length = math.hypot(v[0], v[1])
    if length < 1e-9:
        return (0.0, 0.0)
    return (v[0] / length, v[1] / length)


def _vperp(v: Point) -> Point:
    """Perpendicular (90° CCW) of a 2D vector."""
    return (-v[1], v[0])


def _vmid(a: Point, b: Point) -> Point:
    return ((a[0]+b[0])/2, (a[1]+b[1])/2)


def _translate(pts: list, dx: float, dy: float) -> list:
    return [(x+dx, y+dy) for x, y in pts]


def _nearest_index(pts: list, target: Point) -> int:
    """Find the index of the closest point in pts to target."""
    best_i = 0
    best_d = _dist(pts[0], target)
    for i, p in enumerate(pts[1:], 1):
        d = _dist(p, target)
        if d < best_d:
            best_d = d
            best_i = i
    return best_i


def _seam_midpoint(pts: list, start_idx: int, end_idx: int) -> tuple:
    """Find midpoint along a polyline segment and its tangent direction."""
    if start_idx == end_idx:
        return pts[start_idx], (1, 0)
    # Collect points in order
    n = len(pts)
    indices = []
    i = start_idx
    while i != end_idx:
        indices.append(i)
        i = (i + 1) % n
    indices.append(end_idx)
    
    # Total length
    total = sum(_dist(pts[indices[j]], pts[indices[j+1]]) for j in range(len(indices)-1))
    # Walk to midpoint
    half = total / 2.0
    accum = 0.0
    for j in range(len(indices)-1):
        seg = _dist(pts[indices[j]], pts[indices[j+1]])
        if accum + seg >= half:
            t = (half - accum) / seg if seg > 0 else 0
            mx = pts[indices[j]][0] + t * (pts[indices[j+1]][0] - pts[indices[j]][0])
            my = pts[indices[j]][1] + t * (pts[indices[j+1]][1] - pts[indices[j]][1])
            dx = pts[indices[j+1]][0] - pts[indices[j]][0]
            dy = pts[indices[j+1]][1] - pts[indices[j]][1]
            return (mx, my), _vnorm((dx, dy))
        accum += seg
    return pts[indices[-1]], (1, 0)


def _add_notch_mark(msp, point: Point, tangent: Point, count: int = 1):
    """Draw notch mark(s) perpendicular to the seam at the given point.
    count=1 for single notch (front), count=2 for double (back)."""
    perp = _vperp(_vnorm(tangent))
    notch_len = 0.25
    if count == 1:
        a = (point[0] - perp[0]*notch_len/2, point[1] - perp[1]*notch_len/2)
        b = (point[0] + perp[0]*notch_len/2, point[1] + perp[1]*notch_len/2)
        msp.add_line(a, b, dxfattribs={"layer": LAYER_NOTCH})
    else:
        for offset in [-0.15, 0.15]:
            px = point[0] + tangent[0]*offset
            py = point[1] + tangent[1]*offset
            a = (px - perp[0]*notch_len/2, py - perp[1]*notch_len/2)
            b = (px + perp[0]*notch_len/2, py + perp[1]*notch_len/2)
            msp.add_line(a, b, dxfattribs={"layer": LAYER_NOTCH})


def _add_grain_arrowhead(msp, tip: Point, direction: Point):
    """Draw a small triangle arrowhead at the tip of the grainline."""
    d = _vnorm(direction)
    p = _vperp(d)
    size = 0.15
    p1 = (tip[0] + d[0]*size*2, tip[1] + d[1]*size*2)
    p2 = (tip[0] + p[0]*size, tip[1] + p[1]*size)
    p3 = (tip[0] - p[0]*size, tip[1] - p[1]*size)
    msp.add_lwpolyline([tip, p2, p1, p3, tip], dxfattribs={"layer": LAYER_GRAIN, "closed": True})


def _add_seam_number(msp, point: Point, tangent: Point, number: int, offset_dist: float = 0.5):
    """Place a circled seam number outside the cut line."""
    perp = _vperp(_vnorm(tangent))
    # Offset outward from the cut line
    tx = point[0] + perp[0] * offset_dist
    ty = point[1] + perp[1] * offset_dist
    # Number text
    msp.add_text(
        str(number),
        dxfattribs={"layer": LAYER_TEXT, "height": 0.2}
    ).set_placement((tx, ty), align=_TEXT_ALIGN)
    # Circle around the number
    msp.add_circle((tx, ty), 0.2, dxfattribs={"layer": LAYER_TEXT})


def _annotate_main_panel(msp, piece: dict, translated_cut: list, dx: float, dy: float,
                          measurements: dict, is_front: bool = True):
    """Add industry-standard annotations to a main panel (front or back)."""
    tc = translated_cut
    # Remove closing point for indexing
    pts = tc[:-1] if tc and _dist(tc[0], tc[-1]) < 0.01 else tc
    n = len(pts)
    
    # --- SEAM EDGE IDENTIFICATION ---
    # The outline order (from build functions):
    # waist_curve → side_top → side_mid → side_hem → hem_across → inseam_up → 
    # inseam_curve(rev) → crotch_curve(rev) → [cb_seam(rev)] → close
    #
    # We identify seams by y-position of key points:
    hem_y_val = max(p[1] for p in pts)
    waist_y_val = min(p[1] for p in pts)
    
    # Find hem corners (two points at max y)
    hem_pts = [(i, p) for i, p in enumerate(pts) if abs(p[1] - hem_y_val) < 0.5]
    if len(hem_pts) >= 2:
        hem_pts.sort(key=lambda x: x[1][0])
        inseam_hem_idx = hem_pts[0][0]
        side_hem_idx = hem_pts[-1][0]
    else:
        inseam_hem_idx = side_hem_idx = 0
    
    # Find waist corners (near min y, leftmost and rightmost)
    waist_pts = [(i, p) for i, p in enumerate(pts) if abs(p[1] - waist_y_val) < 2.0]
    if len(waist_pts) >= 2:
        waist_pts.sort(key=lambda x: x[1][0])
        cf_waist_idx = waist_pts[0][0]
        side_waist_idx = waist_pts[-1][0]
    else:
        cf_waist_idx = side_waist_idx = 0
    
    # Find crotch point (leftmost x)
    crotch_idx = min(range(n), key=lambda i: pts[i][0])
    
    # --- SEAM NUMBERS ---
    # 1 = inseam (hem to crotch on left side)
    mid, tan = _seam_midpoint(pts, inseam_hem_idx, crotch_idx)
    _add_seam_number(msp, mid, tan, 1, offset_dist=-0.7)
    
    # 2 = side seam (waist to hem on right side)
    mid, tan = _seam_midpoint(pts, side_waist_idx, side_hem_idx)
    _add_seam_number(msp, mid, tan, 2, offset_dist=0.7)
    
    # 3 = center/crotch seam (waist to crotch on left side)
    mid, tan = _seam_midpoint(pts, cf_waist_idx, crotch_idx)
    _add_seam_number(msp, mid, tan, 3, offset_dist=-0.7)
    
    # 4 = waist (top edge)
    mid, tan = _seam_midpoint(pts, cf_waist_idx, side_waist_idx)
    _add_seam_number(msp, mid, tan, 4, offset_dist=-0.5)
    
    # --- NOTCH MARKS ---
    # Hip-level notch on side seam
    hip_y_translated = 8.5 + dy
    # Find closest point on side seam (right side, between waist and hem)
    side_region = []
    i = side_waist_idx
    while i != side_hem_idx:
        side_region.append(i)
        i = (i + 1) % n
    side_region.append(side_hem_idx)
    
    best_hip_idx = min(side_region, key=lambda i: abs(pts[i][1] - hip_y_translated))
    hip_tan = _vnorm((
        pts[(best_hip_idx+1) % n][0] - pts[(best_hip_idx-1) % n][0],
        pts[(best_hip_idx+1) % n][1] - pts[(best_hip_idx-1) % n][1],
    ))
    notch_count = 1 if is_front else 2
    _add_notch_mark(msp, pts[best_hip_idx], hip_tan, count=notch_count)
    
    # CF/CB waist notch
    cf_pt = pts[cf_waist_idx]
    if cf_waist_idx + 1 < n:
        cf_tan = _vnorm((pts[cf_waist_idx+1][0] - cf_pt[0], pts[cf_waist_idx+1][1] - cf_pt[1]))
    else:
        cf_tan = (0, 1)
    _add_notch_mark(msp, cf_pt, cf_tan, count=1)
    
    # --- PATTERN INFO TEXT ---
    lx, ly = piece["label_pos"]
    lx += dx; ly += dy
    name_text = "FRONT PANEL" if is_front else "BACK PANEL"
    count = piece.get("count", 1)
    mirror = piece.get("mirror", False)
    cut_text = f"Cut {count} (mirror)" if mirror else f"Cut {count}"
    size_text = f"Size: {measurements.get('waist', '?')}\" waist"
    
    spacing = 0.35
    for i, text in enumerate([name_text, cut_text, size_text]):
        msp.add_text(
            text,
            dxfattribs={"layer": LAYER_TEXT, "height": 0.2}
        ).set_placement((lx, ly + i * spacing), align=_TEXT_ALIGN)
    
    # --- SA LABEL ---
    sa = piece.get("seam_allowance", 0.625)
    sa_text = f'SA {sa}"'
    # Place near top-right corner
    msp.add_text(
        sa_text,
        dxfattribs={"layer": LAYER_SA, "height": 0.15}
    ).set_placement((lx + 3.0, ly - 1.0), align=_TEXT_ALIGN)


# ---------------------------------------------------------------------------
# DXF export
# ---------------------------------------------------------------------------

def _add_layers(doc) -> None:
    for name, color, lt in [
        (LAYER_CUT, 7, "CONTINUOUS"), (LAYER_SA, 8, "DASHED"),
        (LAYER_GRAIN, 3, "CENTER"), (LAYER_NOTCH, 1, "CONTINUOUS"),
        (LAYER_INTERNAL, 6, "DOTTED"), (LAYER_TEXT, 2, "CONTINUOUS"),
    ]:
        if name not in doc.layers:
            doc.layers.add(name=name, color=color, linetype=lt)


def _draw_poly(msp, points, layer, closed=False):
    pts = points[:-1] if closed and points and points[0] == points[-1] else points
    msp.add_lwpolyline(pts, dxfattribs={"layer": layer, **({"closed": True} if closed else {})})


def to_dxf(solution: dict, output_path: str) -> str:
    doc = ezdxf.new("R2000")
    doc.header["$INSUNITS"] = 1
    _add_layers(doc)
    msp = doc.modelspace()
    
    cx = 0.0; cy = 0.0; row_h = 0.0
    
    for piece in solution["pieces"]:
        cut = piece["cut"]
        x0, y0, x1, y1 = _bbox(cut)
        w = x1-x0; h = y1-y0
        dx, dy = -x0 + cx, -y0 + cy
        
        tc = [(x+dx, y+dy) for x, y in cut]
        ts = [(x+dx, y+dy) for x, y in piece.get("seam_outline", [])]
        
        _draw_poly(msp, tc, LAYER_CUT, closed=True)
        if ts:
            _draw_poly(msp, ts, LAYER_SA, closed=True)
        
        for line in piece.get("internal_lines", []):
            _draw_poly(msp, [(x+dx, y+dy) for x, y in line], LAYER_INTERNAL)
        
        # Grainline with arrowheads
        grain = piece.get("grainline")
        if grain:
            tg = _translate(grain, dx, dy)
            _draw_poly(msp, tg, LAYER_GRAIN)
            if len(tg) >= 2:
                # Arrowhead at start (pointing up)
                d_start = (tg[0][0]-tg[1][0], tg[0][1]-tg[1][1])
                _add_grain_arrowhead(msp, tg[0], d_start)
                # Arrowhead at end (pointing down)
                d_end = (tg[-1][0]-tg[-2][0], tg[-1][1]-tg[-2][1])
                _add_grain_arrowhead(msp, tg[-1], d_end)
        
        # Notch marks with proper perpendicular orientation
        closed_pts = tc[:-1] if tc and _dist(tc[0], tc[-1]) < 0.01 else tc
        for (nx, ny), label in piece.get("notches", []):
            p = (nx+dx, ny+dy)
            idx = _nearest_index(closed_pts, p)
            n_pts = len(closed_pts)
            tan = _vnorm((
                closed_pts[(idx+1) % n_pts][0] - closed_pts[(idx-1) % n_pts][0],
                closed_pts[(idx+1) % n_pts][1] - closed_pts[(idx-1) % n_pts][1],
            ))
            _add_notch_mark(msp, p, tan, count=1)
        
        # Annotations for main panels
        if piece["name"] in ("front_panel", "back_panel"):
            is_front = piece["name"] == "front_panel"
            _annotate_main_panel(msp, piece, tc, dx, dy,
                                  solution.get("measurements", {}), is_front=is_front)
        else:
            lx, ly = piece["label_pos"]
            msp.add_text(
                piece["name"].replace("_", " ").title(),
                dxfattribs={"layer": LAYER_TEXT, "height": 0.25}
            ).set_placement((lx+dx, ly+dy), align=_TEXT_ALIGN)
        
        cx += w + 3.0
        row_h = max(row_h, h)
        if cx > 70:
            cx = 0; cy += row_h + 2.0; row_h = 0
    
    out = Path(output_path)
    out.parent.mkdir(parents=True, exist_ok=True)
    doc.saveas(str(out))
    return str(out)


if __name__ == "__main__":
    sample = {
        "waist": 30.0, "hip": 52.0,
        "front_rise": 12.75, "back_rise": 14.75,
        "inseam": 28.5, "outseam": 40.5,
        "thigh": 28.0, "leg_opening": 23.5,
        "fly_length": 10.0,
    }
    sol = solve(sample, DEFAULT_CONSTRUCTION, DEFAULT_EASE)
    print(json.dumps(sol["validation"], indent=2))
