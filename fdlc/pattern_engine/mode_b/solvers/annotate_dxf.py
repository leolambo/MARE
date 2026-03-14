#!/usr/bin/env python3
"""DXF annotation helpers for Mode B pant block solver."""

from __future__ import annotations

import math

from .pattern_utils import (
    LAYER_GRAIN,
    LAYER_NOTCH,
    LAYER_SA,
    LAYER_TEXT,
    Point,
    _TEXT_ALIGN,
    _dist,
)


def _vnorm(v: Point) -> Point:
    """Normalize a 2D vector."""
    length = math.hypot(v[0], v[1])
    if length < 1e-9:
        return (0.0, 0.0)
    return (v[0] / length, v[1] / length)


def _vperp(v: Point) -> Point:
    """Perpendicular (90deg CCW) of a 2D vector."""
    return (-v[1], v[0])


def _vmid(a: Point, b: Point) -> Point:
    return ((a[0]+b[0])/2, (a[1]+b[1])/2)


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

    n = len(pts)
    indices = []
    i = start_idx
    while i != end_idx:
        indices.append(i)
        i = (i + 1) % n
    indices.append(end_idx)

    total = sum(_dist(pts[indices[j]], pts[indices[j+1]]) for j in range(len(indices)-1))
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
    """Draw notch mark(s) perpendicular to the seam at the given point."""
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
    tx = point[0] + perp[0] * offset_dist
    ty = point[1] + perp[1] * offset_dist
    msp.add_text(
        str(number),
        dxfattribs={"layer": LAYER_TEXT, "height": 0.2},
    ).set_placement((tx, ty), align=_TEXT_ALIGN)
    msp.add_circle((tx, ty), 0.2, dxfattribs={"layer": LAYER_TEXT})


def _annotate_main_panel(msp, piece: dict, translated_cut: list, dy: float, measurements: dict, is_front: bool = True):
    """Add industry-standard annotations to a main panel (front or back)."""
    pts = translated_cut[:-1] if translated_cut and _dist(translated_cut[0], translated_cut[-1]) < 0.01 else translated_cut
    n = len(pts)

    hem_y_val = max(p[1] for p in pts)
    waist_y_val = min(p[1] for p in pts)

    hem_pts = [(i, p) for i, p in enumerate(pts) if abs(p[1] - hem_y_val) < 0.5]
    if len(hem_pts) >= 2:
        hem_pts.sort(key=lambda x: x[1][0])
        inseam_hem_idx = hem_pts[0][0]
        side_hem_idx = hem_pts[-1][0]
    else:
        inseam_hem_idx = side_hem_idx = 0

    waist_pts = [(i, p) for i, p in enumerate(pts) if abs(p[1] - waist_y_val) < 2.0]
    if len(waist_pts) >= 2:
        waist_pts.sort(key=lambda x: x[1][0])
        cf_waist_idx = waist_pts[0][0]
        side_waist_idx = waist_pts[-1][0]
    else:
        cf_waist_idx = side_waist_idx = 0

    crotch_idx = min(range(n), key=lambda i: pts[i][0])

    mid, tan = _seam_midpoint(pts, inseam_hem_idx, crotch_idx)
    _add_seam_number(msp, mid, tan, 1, offset_dist=-0.7)

    mid, tan = _seam_midpoint(pts, side_waist_idx, side_hem_idx)
    _add_seam_number(msp, mid, tan, 2, offset_dist=0.7)

    mid, tan = _seam_midpoint(pts, cf_waist_idx, crotch_idx)
    _add_seam_number(msp, mid, tan, 3, offset_dist=-0.7)

    mid, tan = _seam_midpoint(pts, cf_waist_idx, side_waist_idx)
    _add_seam_number(msp, mid, tan, 4, offset_dist=-0.5)

    hip_y_translated = 8.5 + dy
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
    _add_notch_mark(msp, pts[best_hip_idx], hip_tan, count=(1 if is_front else 2))

    cf_pt = pts[cf_waist_idx]
    if cf_waist_idx + 1 < n:
        cf_tan = _vnorm((pts[cf_waist_idx+1][0] - cf_pt[0], pts[cf_waist_idx+1][1] - cf_pt[1]))
    else:
        cf_tan = (0, 1)
    _add_notch_mark(msp, cf_pt, cf_tan, count=1)

    lx, ly = piece["label_pos"]
    name_text = "FRONT PANEL" if is_front else "BACK PANEL"
    count = piece.get("count", 1)
    mirror = piece.get("mirror", False)
    cut_text = f"Cut {count} (mirror)" if mirror else f"Cut {count}"
    size_text = f"Size: {measurements.get('waist', '?')}\" waist"

    spacing = 0.35
    for i, text in enumerate([name_text, cut_text, size_text]):
        msp.add_text(
            text,
            dxfattribs={"layer": LAYER_TEXT, "height": 0.2},
        ).set_placement((lx, ly + i * spacing), align=_TEXT_ALIGN)

    sa = piece.get("seam_allowance", 0.625)
    msp.add_text(
        f'SA {sa}"',
        dxfattribs={"layer": LAYER_SA, "height": 0.15},
    ).set_placement((lx + 3.0, ly - 1.0), align=_TEXT_ALIGN)


__all__ = [
    "_vnorm",
    "_vperp",
    "_vmid",
    "_nearest_index",
    "_seam_midpoint",
    "_add_notch_mark",
    "_add_grain_arrowhead",
    "_add_seam_number",
    "_annotate_main_panel",
]
