#!/usr/bin/env python3
"""ASTM/AAMA DXF export for CLO3D.

Generates DXF with:
- ASTM D6673 numbered layers (1=boundary, 7=grain, 14=sew lines, etc.)
- BLOCK structure (one block per piece)
- Adaptive point simplification (tight on curves, loose on straights)
- Sew line edges on layer 14 for seam identification

CLO3D import settings:
- ✅ Swap Cutting Line and Sewing Line
- ✅ Import Draw Curve Points
- ✅ Optimize All Curve Points
- ✅ Import Pattern Annotation
- ✅ Include Notches (Ratio)
"""

from __future__ import annotations

import math
from pathlib import Path
from typing import List, Tuple

import ezdxf

from .pattern_utils import Point, _bbox, _dist

# ASTM layer numbers
L_BOUNDARY = "1"
L_NOTCH = "4"
L_MIRROR = "6"
L_GRAIN = "7"
L_INTERNAL = "8"
L_SEW = "14"
L_ANNOT = "15"

# Simplification tolerances
CURVE_TOLERANCE = 0.04   # tight — preserves curve shape
STRAIGHT_TOLERANCE = 0.2  # loose — minimal points on straight edges


def _setup_astm_layers(doc) -> None:
    for name, color in [
        (L_BOUNDARY, 7), (L_NOTCH, 1), (L_MIRROR, 6), (L_GRAIN, 3),
        (L_INTERNAL, 8), (L_SEW, 2), (L_ANNOT, 2),
    ]:
        if name not in doc.layers:
            doc.layers.add(name=name, color=color)


def _simplify_rdp(pts: List[Point], tolerance: float) -> List[Point]:
    """Ramer-Douglas-Peucker simplification."""
    if len(pts) <= 2:
        return pts
    s, e = pts[0], pts[-1]
    dx, dy = e[0] - s[0], e[1] - s[1]
    ll = math.hypot(dx, dy)
    md, mi = 0.0, 0
    for i in range(1, len(pts) - 1):
        if ll > 0.001:
            d = abs(dy * pts[i][0] - dx * pts[i][1] + e[0] * s[1] - e[1] * s[0]) / ll
        else:
            d = _dist(pts[i], s)
        if d > md:
            md = d
            mi = i
    if md > tolerance:
        left = _simplify_rdp(pts[:mi + 1], tolerance)
        right = _simplify_rdp(pts[mi:], tolerance)
        return left[:-1] + right
    return [pts[0], pts[-1]]


def _adaptive_simplify(pts: List[Point]) -> List[Point]:
    """Split outline at key transition points, simplify each segment
    with tight tolerance on curves and loose on straights."""
    n = len(pts)
    hy = max(p[1] for p in pts)
    wy = min(p[1] for p in pts)

    hp = sorted([(i, p) for i, p in enumerate(pts) if abs(p[1] - hy) < 0.5], key=lambda x: x[1][0])
    wp = sorted([(i, p) for i, p in enumerate(pts) if abs(p[1] - wy) < 2.0], key=lambda x: x[1][0])
    ci = min(range(n), key=lambda i: pts[i][0])

    if len(hp) < 2 or len(wp) < 2:
        return _simplify_rdp(pts, CURVE_TOLERANCE)

    keys = sorted(set([wp[0][0], wp[-1][0], hp[-1][0], hp[0][0], ci]))

    result: List[Point] = []
    for i in range(len(keys)):
        s = keys[i]
        e = keys[(i + 1) % len(keys)]
        seg: List[Point] = []
        j = s
        while True:
            seg.append(pts[j])
            if j == e:
                break
            j = (j + 1) % n
            if len(seg) > n:
                break

        is_straight = (
            len(seg) < 5
            or (max(p[0] for p in seg) - min(p[0] for p in seg) < 1.0)
            or (max(p[1] for p in seg) - min(p[1] for p in seg) < 1.0)
        )
        tol = STRAIGHT_TOLERANCE if is_straight else CURVE_TOLERANCE
        simp = _simplify_rdp(seg, tol)

        if result and result[-1] == simp[0]:
            result.extend(simp[1:])
        else:
            result.extend(simp)

    return result


def _seam_keys(pts: List[Point]) -> dict:
    """Identify key transition point indices for seam edges."""
    n = len(pts)
    hy = max(p[1] for p in pts)
    wy = min(p[1] for p in pts)
    hp = sorted([(i, p) for i, p in enumerate(pts) if abs(p[1] - hy) < 0.5], key=lambda x: x[1][0])
    wp = sorted([(i, p) for i, p in enumerate(pts) if abs(p[1] - wy) < 2.0], key=lambda x: x[1][0])
    ci = min(range(n), key=lambda i: pts[i][0])
    return {
        "in_hem": hp[0][0],
        "side_hem": hp[-1][0],
        "cf_waist": wp[0][0],
        "side_waist": wp[-1][0],
        "crotch": ci,
    }


def to_astm_dxf(solution: dict, output_path: str) -> str:
    """Export CLO3D-optimized ASTM DXF with adaptive simplification."""
    doc = ezdxf.new("R2000")
    doc.header["$INSUNITS"] = 1
    _setup_astm_layers(doc)
    msp = doc.modelspace()

    cx = 0.0
    cy = 0.0
    rh = 0.0

    for idx, piece in enumerate(solution["pieces"]):
        cut = piece["cut"]
        x0, y0, x1, y1 = _bbox(cut)
        w = x1 - x0
        h = y1 - y0
        orig = cut[:-1] if cut and _dist(cut[0], cut[-1]) < 0.01 else cut

        bn = f"P{idx}_{piece['name'].upper()}"
        block = doc.blocks.new(name=bn)

        # Simplify main panels adaptively, others with tight tolerance
        if piece["name"] in ("front_panel", "back_panel"):
            simp = _adaptive_simplify(orig)
        else:
            simp = _simplify_rdp(orig, CURVE_TOLERANCE)

        # Layer 1: piece boundary
        block.add_lwpolyline(simp, dxfattribs={"layer": L_BOUNDARY, "closed": True})

        # Layer 14: sew lines (main panels only)
        if piece["name"] in ("front_panel", "back_panel"):
            sk = _seam_keys(simp)
            for s, e in [
                (sk["in_hem"], sk["crotch"]),
                (sk["side_waist"], sk["side_hem"]),
                (sk["cf_waist"], sk["crotch"]),
                (sk["cf_waist"], sk["side_waist"]),
            ]:
                block.add_lwpolyline([simp[s], simp[e]], dxfattribs={"layer": L_SEW})

        # Layer 7: grain line
        grain = piece.get("grainline")
        if grain and len(grain) >= 2:
            block.add_lwpolyline(grain, dxfattribs={"layer": L_GRAIN})

        # Layer 8: internal lines
        for line in piece.get("internal_lines", []):
            if len(line) >= 2:
                block.add_lwpolyline(line, dxfattribs={"layer": L_INTERNAL})

        # Layer 4: notches
        for (nx, ny), _ in piece.get("notches", []):
            block.add_point((nx, ny), dxfattribs={"layer": L_NOTCH})

        # Layer 6: mirror/fold line
        if piece.get("meta", {}).get("cut_on_fold"):
            ys = [p[1] for p in simp]
            mx = min(p[0] for p in simp)
            block.add_lwpolyline([(mx, min(ys)), (mx, max(ys))], dxfattribs={"layer": L_MIRROR})

        # Layer 15: annotation text
        acx, acy = (x0 + x1) / 2, (y0 + y1) / 2
        block.add_text(
            piece["name"].replace("_", " ").upper(),
            dxfattribs={"layer": L_ANNOT, "height": 0.25},
        ).set_placement((acx, acy))
        cnt = piece.get("count", 1)
        mir = "MIRROR" if piece.get("mirror") else ""
        block.add_text(
            f"CUT {cnt} {mir}".strip(),
            dxfattribs={"layer": L_ANNOT, "height": 0.18},
        ).set_placement((acx, acy + 0.4))

        # Insert block into modelspace
        msp.add_blockref(bn, (cx - x0, cy - y0), dxfattribs={"layer": L_BOUNDARY})

        cx += w + 3.0
        rh = max(rh, h)
        if cx > 70:
            cx = 0
            cy += rh + 2.0
            rh = 0

    out = Path(output_path)
    out.parent.mkdir(parents=True, exist_ok=True)
    doc.saveas(str(out))
    return str(out)
