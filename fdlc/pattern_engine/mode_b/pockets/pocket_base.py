"""Shared utilities for pocket modules."""

from __future__ import annotations
import math
from typing import List, Tuple

from ..solvers.pattern_utils import (
    Point, _dist, _polyline_length, _bbox, _cbez, _qbez, _rect_piece,
)


def _nearest_point_on_poly(pts: List[Point], target: Point) -> Tuple[int, float]:
    """Find index of closest vertex in pts to target. Returns (index, distance)."""
    best_i, best_d = 0, float("inf")
    for i, p in enumerate(pts):
        d = _dist(p, target)
        if d < best_d:
            best_d = d
            best_i = i
    return best_i, best_d


def _walk_perimeter_fraction(pts: List[Point], start_idx: int, end_idx: int) -> float:
    """Fraction of total perimeter between start_idx and end_idx (walking forward)."""
    n = len(pts)
    total = sum(_dist(pts[i], pts[(i + 1) % n]) for i in range(n))
    if total < 1e-9:
        return 0.0
    segment = 0.0
    i = start_idx
    while i != end_idx:
        j = (i + 1) % n
        segment += _dist(pts[i], pts[j])
        i = j
    return segment / total


def _point_at_fraction(pts: List[Point], frac: float) -> Point:
    """Interpolate a point at fraction along a closed polyline."""
    n = len(pts)
    total = sum(_dist(pts[i], pts[(i + 1) % n]) for i in range(n))
    target = frac * total
    acc = 0.0
    for i in range(n):
        j = (i + 1) % n
        seg = _dist(pts[i], pts[j])
        if acc + seg >= target:
            t = (target - acc) / seg if seg > 0 else 0
            return (
                pts[i][0] + t * (pts[j][0] - pts[i][0]),
                pts[i][1] + t * (pts[j][1] - pts[i][1]),
            )
        acc += seg
    return pts[-1]


def _side_seam_points(panel: dict) -> Tuple[Point, Point]:
    """Return (waist_end, hem_end) of the side seam on a panel.

    Side seam = rightmost region of the panel outline.
    Waist end = rightmost point near top (min y), hem end = rightmost near bottom (max y).
    """
    pts = panel["cut"]
    xs = [p[0] for p in pts]
    ys = [p[1] for p in pts]
    max_x = max(xs)
    min_y = min(ys)
    max_y = max(ys)

    # Waist-side end of side seam: highest X near waist Y
    waist_candidates = [p for p in pts if abs(p[1] - min_y) < 1.5]
    waist_end = max(waist_candidates, key=lambda p: p[0]) if waist_candidates else (max_x, min_y)

    # Hem-side end of side seam: highest X near hem Y
    hem_candidates = [p for p in pts if abs(p[1] - max_y) < 1.5]
    hem_end = max(hem_candidates, key=lambda p: p[0]) if hem_candidates else (max_x, max_y)

    return waist_end, hem_end


def _side_seam_segment(panel: dict, opening_drop: float, opening_len: float) -> Tuple[Point, Point]:
    """Return (top, bottom) endpoints of the pocket opening on the side seam.

    opening_drop: inches from waist down to top of opening
    opening_len: inches of opening length
    """
    waist_end, hem_end = _side_seam_points(panel)
    # Side seam runs from waist_end to hem_end; parameterize by Y
    total_h = hem_end[1] - waist_end[1]
    if total_h < 0.001:
        return waist_end, hem_end

    t_top = opening_drop / total_h
    t_bot = (opening_drop + opening_len) / total_h
    t_top = min(max(t_top, 0.0), 1.0)
    t_bot = min(max(t_bot, 0.0), 1.0)

    def _lerp(a, b, t):
        return (a[0] + t * (b[0] - a[0]), a[1] + t * (b[1] - a[1]))

    return _lerp(waist_end, hem_end, t_top), _lerp(waist_end, hem_end, t_bot)


__all__ = [
    "_nearest_point_on_poly",
    "_walk_perimeter_fraction",
    "_point_at_fraction",
    "_side_seam_points",
    "_side_seam_segment",
]
