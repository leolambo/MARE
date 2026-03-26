#!/usr/bin/env python3
"""Shared geometry/constants utilities for Mode B pant block solver."""

from __future__ import annotations

import math
from typing import List, Tuple

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
    "pocket_type": "in_seam",       # front pocket: "in_seam" | "slash" (future)
    "back_pocket_type": "patch",    # back pocket:  "patch"   | "welt"  (future)
    "fly_type": "standard_zip",
    "dart_count_back": 0,
    # in_seam pocket overrides
    "in_seam_drop": 1.5,
    "in_seam_length": 7.0,
    "in_seam_depth": 10.5,
    "in_seam_width": 7.5,
    "in_seam_facing_width": 1.5,
    # patch pocket overrides
    "patch_width": 6.0,
    "patch_height": 6.5,
    "patch_corner_r": 0.75,
    "patch_drop": 3.5,
    "patch_topstitch": 0.25,
}

DEFAULT_EASE = {"waist": 1.0, "hip": 2.0, "thigh": 2.0}


def _qbez(p0: Point, p1: Point, p2: Point, steps: int = 32) -> List[Point]:
    """Quadratic bezier."""
    return [((1-t)**2*p0[0]+2*(1-t)*t*p1[0]+t**2*p2[0],
             (1-t)**2*p0[1]+2*(1-t)*t*p1[1]+t**2*p2[1])
            for t in [i/steps for i in range(steps+1)]]


def _cbez(p0: Point, p1: Point, p2: Point, p3: Point, steps: int = 40) -> List[Point]:
    """Cubic bezier for anatomical curves."""
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
    xs = [p[0] for p in pts]
    ys = [p[1] for p in pts]
    return min(xs), min(ys), max(xs), max(ys)


def _closed_offset(poly: List[Point], offset: float) -> List[Point]:
    pts = list(poly)
    if pts[0] != pts[-1]:
        pts = pts + [pts[0]]
    result = list(offset_vertices_2d(pts, offset=offset, closed=True))
    return [(float(x), float(y)) for x, y in result]


def _rect_piece(name: str, width: float, height: float, *, count: int = 1, mirror: bool = False, fold: bool = False) -> dict:
    cut = [(0, 0), (width, 0), (width, height), (0, height), (0, 0)]
    return {
        "name": name,
        "count": count,
        "mirror": mirror,
        "cut": cut,
        "grainline": [(width/2, 0.5), (width/2, max(0.5, height-0.5))],
        "internal_lines": [],
        "notches": [],
        "label_pos": (width/2, height/2),
        "meta": {"cut_on_fold": fold},
    }


def _translate(pts: list, dx: float, dy: float) -> list:
    return [(x+dx, y+dy) for x, y in pts]


__all__ = [
    "Point",
    "LAYER_CUT",
    "LAYER_SA",
    "LAYER_GRAIN",
    "LAYER_NOTCH",
    "LAYER_INTERNAL",
    "LAYER_TEXT",
    "DEFAULT_CONSTRUCTION",
    "DEFAULT_EASE",
    "_TEXT_ALIGN",
    "_qbez",
    "_cbez",
    "_dist",
    "_polyline_length",
    "_bbox",
    "_closed_offset",
    "_rect_piece",
    "_translate",
]
