#!/usr/bin/env python3
"""
Cross-format parity tests: DXF ↔ CLO3D JSON consistency.

Verifies that the pant_block solver, dxf_export, and clo3d_json all agree
on the same geometry for a given set of measurements. Catches regressions
where one format diverges from the others.

Comparison strategy:
  - Solver is ground truth (pant_block.py)
  - Keypoint measurements (waist width, hip width, hem width, rise depth) are
    extracted from each format and compared against the solver's known values
  - Perimeter lengths are compared between solver polylines and CLO3D line chains
  - Structural checks (piece count, seam count, edge overlaps) are binary pass/fail
  - No bbox-only comparisons — every dimensional check is tied to a specific garment
    measurement

Run: cd ~/base/mare-pipeline && python3 -m pytest fdlc/pattern_engine/mode_b/solvers/test_format_parity.py -v
"""

from __future__ import annotations

import json
import math
import os
import pytest
import ezdxf

from fdlc.pattern_engine.mode_b.solvers.pant_block import (
    solve, _build_front_panel, _build_back_panel, _match_seams,
)
from fdlc.pattern_engine.mode_b.solvers.dxf_export import to_dxf
from fdlc.pattern_engine.mode_b.solvers.clo3d_json import (
    generate_clo3d_json,
    generate_5panel_json,
    _build_front_lines,
    _build_back_lines,
    _compute_line_lengths_mm,
    _get_fracs,
    _mirror_lines,
    INCH_TO_MM,
)
from fdlc.pattern_engine.mode_b.solvers.pattern_utils import (
    DEFAULT_CONSTRUCTION,
    DEFAULT_EASE,
    _polyline_length,
    _bbox,
    _dist,
)

# ── Shared fixtures ───────────────────────────────────────────────────────

SAMPLE = {
    "waist": 30.0,
    "hip": 42.0,
    "front_rise": 10.75,
    "back_rise": 12.75,
    "inseam": 30.0,
    "outseam": 40.0,
    "thigh": 26.0,
    "leg_opening": 23.5,
    "fly_length": 10.0,
}

SIZES = [
    {"waist": 28.0, "hip": 38.0, "front_rise": 10.0, "inseam": 30.0,
     "outseam": 40.0, "thigh": 24.0, "leg_opening": 20.0, "fly_length": 9.5},
    {"waist": 32.0, "hip": 44.0, "front_rise": 11.5, "inseam": 31.0,
     "outseam": 41.5, "thigh": 28.0, "leg_opening": 24.0, "fly_length": 10.5},
    {"waist": 36.0, "hip": 50.0, "front_rise": 12.0, "inseam": 31.5,
     "outseam": 42.0, "thigh": 32.0, "leg_opening": 26.0, "fly_length": 11.0},
]


@pytest.fixture
def solution():
    return solve(SAMPLE, DEFAULT_CONSTRUCTION, DEFAULT_EASE)


@pytest.fixture
def front_panel(solution):
    return next(p for p in solution["pieces"] if p["name"] == "front_panel")


@pytest.fixture
def back_panel(solution):
    return next(p for p in solution["pieces"] if p["name"] == "back_panel")


@pytest.fixture
def dxf_path(solution, tmp_path):
    p = str(tmp_path / "pant.dxf")
    to_dxf(solution, p)
    return p


@pytest.fixture
def dxf_doc(dxf_path):
    return ezdxf.readfile(dxf_path)


@pytest.fixture
def clo_2panel_path(tmp_path):
    p = str(tmp_path / "clo_2panel.json")
    generate_clo3d_json(SAMPLE, p)
    return p


@pytest.fixture
def clo_2panel(clo_2panel_path):
    with open(clo_2panel_path) as f:
        return json.load(f)


@pytest.fixture
def clo_5panel_path(tmp_path):
    p = str(tmp_path / "clo_5panel.json")
    generate_5panel_json(SAMPLE, p)
    return p


@pytest.fixture
def clo_5panel(clo_5panel_path):
    with open(clo_5panel_path) as f:
        return json.load(f)


# ── Geometry extraction helpers ───────────────────────────────────────────

def _clo_all_points_mm(pattern):
    """Extract all (x, y) points from a CLO3D pattern in mm."""
    pts = []
    for line in pattern["ShapeInfo"]["LineList"]:
        for pt in line["PointList"]:
            pts.append((pt["Position"]["x"], pt["Position"]["y"]))
    return pts


def _clo_line_chord_mm(line):
    """Chord length of a single CLO3D line in mm."""
    pts = line["PointList"]
    total = 0
    for i in range(len(pts) - 1):
        dx = pts[i + 1]["Position"]["x"] - pts[i]["Position"]["x"]
        dy = pts[i + 1]["Position"]["y"] - pts[i]["Position"]["y"]
        total += math.hypot(dx, dy)
    return total


def _clo_bezier_arc_length_mm(line, samples=32):
    """Approximate arc length of a CLO3D bezier line via de Casteljau sampling."""
    pts = line["PointList"]
    if len(pts) != 4:
        return _clo_line_chord_mm(line)

    p0 = (pts[0]["Position"]["x"], pts[0]["Position"]["y"])
    p1 = (pts[1]["Position"]["x"], pts[1]["Position"]["y"])
    p2 = (pts[2]["Position"]["x"], pts[2]["Position"]["y"])
    p3 = (pts[3]["Position"]["x"], pts[3]["Position"]["y"])

    total = 0.0
    prev = p0
    for i in range(1, samples + 1):
        t = i / samples
        t2 = t * t
        t3 = t2 * t
        mt = 1 - t
        mt2 = mt * mt
        mt3 = mt2 * mt
        x = mt3 * p0[0] + 3 * mt2 * t * p1[0] + 3 * mt * t2 * p2[0] + t3 * p3[0]
        y = mt3 * p0[1] + 3 * mt2 * t * p1[1] + 3 * mt * t2 * p2[1] + t3 * p3[1]
        total += math.hypot(x - prev[0], y - prev[1])
        prev = (x, y)
    return total


def _clo_perimeter_mm(pattern):
    """Total perimeter of a CLO3D pattern using proper arc length for beziers."""
    total = 0
    for line in pattern["ShapeInfo"]["LineList"]:
        total += _clo_bezier_arc_length_mm(line)
    return total


def _clo_line_lengths_mm(pattern):
    """List of individual line arc lengths in mm."""
    return [_clo_bezier_arc_length_mm(line) for line in pattern["ShapeInfo"]["LineList"]]


def _clo_keypoints_mm(pattern):
    """Extract garment keypoints from a CLO3D panel.

    All X measurements are offset-invariant: we measure relative to the panel's
    own geometry, not absolute layout position. Mirrored panels (negated X) are
    handled by using width/span rather than absolute X.

    Returns dict with:
      waist_width: horizontal span at the topmost Y
      hem_width: horizontal span at the bottommost Y
      rise_depth: vertical distance from waist to crotch tip
      total_height: vertical span (waist to hem)
      crotch_extension: how far the crotch extends past the inseam line (narrowest X region)
      panel_width: total horizontal span
    """
    pts = _clo_all_points_mm(pattern)
    xs = [p[0] for p in pts]
    ys = [p[1] for p in pts]

    # CLO3D is Y-up, so max Y = waist (top), min Y = hem (bottom)
    max_y = max(ys)  # waist
    min_y = min(ys)  # hem

    # Waist width: span at top Y (within 2mm tolerance)
    waist_pts = [p[0] for p in pts if abs(p[1] - max_y) < 2.0]
    waist_width = max(waist_pts) - min(waist_pts) if waist_pts else 0

    # Hem width: span at bottom Y (within 2mm tolerance)
    hem_pts = [p[0] for p in pts if abs(p[1] - min_y) < 2.0]
    hem_width = max(hem_pts) - min(hem_pts) if hem_pts else 0

    # Total panel width (offset-invariant)
    panel_width = max(xs) - min(xs)

    # Crotch extension: how far the panel extends beyond the hem/inseam edge.
    # The inseam edge is at the narrower (hem) X region. Crotch extends past it.
    # Use hem min-X as reference, crotch tip is the point furthest past it.
    # For mirrored panels, use hem max-X instead (crotch goes right).
    hem_min_x = min(hem_pts) if hem_pts else min(xs)
    hem_max_x = max(hem_pts) if hem_pts else max(xs)

    # Crotch tip: point with the most extreme X beyond the hem edge
    # Check both directions (original panels: crotch goes left/min-X; mirrored: goes right/max-X)
    ext_left = hem_min_x - min(xs)  # how far left of hem the panel extends
    ext_right = max(xs) - hem_max_x  # how far right of hem

    crotch_extension = max(ext_left, ext_right)

    # Rise depth: vertical distance from waist to the point at the crotch extension tip
    # Find the point at the extreme X
    if ext_left >= ext_right:
        crotch_pt = next(p for p in pts if p[0] == min(xs))
    else:
        crotch_pt = next(p for p in pts if p[0] == max(xs))
    rise_depth = max_y - crotch_pt[1]

    return {
        "waist_width": waist_width,
        "hem_width": hem_width,
        "rise_depth": rise_depth,
        "total_height": max_y - min_y,
        "crotch_extension": crotch_extension,
        "panel_width": panel_width,
    }


def _solver_keypoints_in(panel):
    """Extract garment keypoints from a solver panel in inches.

    Same measurements as _clo_keypoints_mm but in inches.
    """
    pts = panel["cut"]
    xs = [p[0] for p in pts]
    ys = [p[1] for p in pts]

    # Solver is Y-down, so min Y = waist (top), max Y = hem (bottom)
    min_y = min(ys)  # waist
    max_y = max(ys)  # hem

    # Waist width at top
    waist_pts = [p[0] for p in pts if abs(p[1] - min_y) < 0.1]
    waist_width = max(waist_pts) - min(waist_pts) if len(waist_pts) >= 2 else 0

    # Hem width at bottom
    hem_pts = [p[0] for p in pts if abs(p[1] - max_y) < 0.1]
    hem_width = max(hem_pts) - min(hem_pts) if len(hem_pts) >= 2 else 0

    # Crotch = leftmost point (most negative X)
    min_x = min(xs)
    crotch_pt = next(p for p in pts if p[0] == min_x)
    rise_depth = crotch_pt[1] - min_y  # Y-down: crotch is below waist

    return {
        "waist_width": waist_width,
        "hem_width": hem_width,
        "rise_depth": rise_depth,
        "total_height": max_y - min_y,
        "crotch_extension": abs(min_x),
    }


def _dxf_closed_polylines(doc, layer):
    """Extract all closed polylines on a layer as lists of (x,y) tuples."""
    msp = doc.modelspace()
    polys = []
    for e in msp:
        if e.dxf.layer == layer and e.dxftype() == "LWPOLYLINE" and e.is_closed:
            polys.append([(pt[0], pt[1]) for pt in e.get_points()])
    return polys


def _dxf_panel_keypoints_in(poly):
    """Extract garment keypoints from a DXF polyline in inches."""
    xs = [p[0] for p in poly]
    ys = [p[1] for p in poly]

    min_y = min(ys)  # DXF Y-up: min = bottom (hem), max = top (waist)... depends on export
    max_y = max(ys)

    # The DXF is exported in solver space (Y-down: waist at low Y, hem at high Y)
    # After dxf_export.py applies offset, Y still increases downward
    # So min_y = waist, max_y = hem
    waist_y = min_y
    hem_y = max_y

    waist_pts = [p[0] for p in poly if abs(p[1] - waist_y) < 0.2]
    waist_width = max(waist_pts) - min(waist_pts) if len(waist_pts) >= 2 else 0

    hem_pts = [p[0] for p in poly if abs(p[1] - hem_y) < 0.2]
    hem_width = max(hem_pts) - min(hem_pts) if len(hem_pts) >= 2 else 0

    min_x = min(xs)
    crotch_pt = next(p for p in poly if p[0] == min_x)
    rise_depth = crotch_pt[1] - waist_y

    return {
        "waist_width": waist_width,
        "hem_width": hem_width,
        "rise_depth": rise_depth,
        "total_height": max_y - min_y,
        "crotch_extension": abs(min_x - min(p[0] for p in poly if abs(p[1] - waist_y) < 0.2)) if waist_pts else 0,
    }


def _poly_perimeter(pts):
    """Perimeter of a closed polyline."""
    total = 0
    for i in range(len(pts)):
        total += _dist(pts[i], pts[(i + 1) % len(pts)])
    return total


# ── 1. Solver ↔ CLO3D keypoint comparisons ───────────────────────────────

class TestSolverCLOKeypoints:
    """Compare specific garment measurements between solver and CLO3D panels."""

    def test_front_hem_width(self, front_panel, clo_2panel):
        """Front hem width (inches) must match CLO3D front hem width (mm / 25.4)."""
        solver = _solver_keypoints_in(front_panel)
        clo_front = next(p for p in clo_2panel["PatternList"] if p["Name"] == "Front_Panel")
        clo = _clo_keypoints_mm(clo_front)

        solver_mm = solver["hem_width"] * INCH_TO_MM
        assert abs(solver_mm - clo["hem_width"]) < 5.0, \
            f"Front hem width: solver={solver_mm:.1f}mm CLO={clo['hem_width']:.1f}mm (Δ{abs(solver_mm - clo['hem_width']):.1f}mm)"

    def test_back_hem_width(self, back_panel, clo_2panel):
        """Back hem width must match between solver and CLO3D."""
        solver = _solver_keypoints_in(back_panel)
        clo_back = next(p for p in clo_2panel["PatternList"] if p["Name"] == "Back_Panel")
        clo = _clo_keypoints_mm(clo_back)

        solver_mm = solver["hem_width"] * INCH_TO_MM
        assert abs(solver_mm - clo["hem_width"]) < 5.0, \
            f"Back hem width: solver={solver_mm:.1f}mm CLO={clo['hem_width']:.1f}mm"

    def test_front_total_height(self, front_panel, clo_2panel):
        """Front panel total height (waist to hem) must match."""
        solver = _solver_keypoints_in(front_panel)
        clo_front = next(p for p in clo_2panel["PatternList"] if p["Name"] == "Front_Panel")
        clo = _clo_keypoints_mm(clo_front)

        solver_mm = solver["total_height"] * INCH_TO_MM
        assert abs(solver_mm - clo["total_height"]) < 10.0, \
            f"Front height: solver={solver_mm:.1f}mm CLO={clo['total_height']:.1f}mm"

    def test_back_total_height(self, back_panel, clo_2panel):
        """Back panel total height must match."""
        solver = _solver_keypoints_in(back_panel)
        clo_back = next(p for p in clo_2panel["PatternList"] if p["Name"] == "Back_Panel")
        clo = _clo_keypoints_mm(clo_back)

        solver_mm = solver["total_height"] * INCH_TO_MM
        assert abs(solver_mm - clo["total_height"]) < 10.0, \
            f"Back height: solver={solver_mm:.1f}mm CLO={clo['total_height']:.1f}mm"

    def test_front_crotch_extension(self, front_panel, clo_2panel):
        """Crotch extension depth must match — critical for fit."""
        solver = _solver_keypoints_in(front_panel)
        clo_front = next(p for p in clo_2panel["PatternList"] if p["Name"] == "Front_Panel")
        clo = _clo_keypoints_mm(clo_front)

        solver_mm = solver["crotch_extension"] * INCH_TO_MM
        assert abs(solver_mm - clo["crotch_extension"]) < 8.0, \
            f"Front crotch ext: solver={solver_mm:.1f}mm CLO={clo['crotch_extension']:.1f}mm"

    def test_back_crotch_extension(self, back_panel, clo_2panel):
        """Back crotch extension must be deeper than front and match CLO3D."""
        solver = _solver_keypoints_in(back_panel)
        clo_back = next(p for p in clo_2panel["PatternList"] if p["Name"] == "Back_Panel")
        clo = _clo_keypoints_mm(clo_back)

        solver_mm = solver["crotch_extension"] * INCH_TO_MM
        assert abs(solver_mm - clo["crotch_extension"]) < 8.0, \
            f"Back crotch ext: solver={solver_mm:.1f}mm CLO={clo['crotch_extension']:.1f}mm"

    def test_back_crotch_deeper_than_front(self, front_panel, back_panel):
        """Back crotch extension must be deeper (52% + 1.5\" offset from solver)."""
        f_ext = _solver_keypoints_in(front_panel)["crotch_extension"]
        b_ext = _solver_keypoints_in(back_panel)["crotch_extension"]
        assert b_ext > f_ext, \
            f"Back crotch ({b_ext:.2f}\") must be deeper than front ({f_ext:.2f}\")"

    def test_back_hem_wider_than_front(self, front_panel, back_panel, clo_2panel):
        """Back gets 52% of leg opening, front gets 48% — in both solver and CLO."""
        f_hem = _solver_keypoints_in(front_panel)["hem_width"]
        b_hem = _solver_keypoints_in(back_panel)["hem_width"]
        assert b_hem > f_hem, "Solver: back hem must be wider than front"

        clo_front = next(p for p in clo_2panel["PatternList"] if p["Name"] == "Front_Panel")
        clo_back = next(p for p in clo_2panel["PatternList"] if p["Name"] == "Back_Panel")
        cf = _clo_keypoints_mm(clo_front)["hem_width"]
        cb = _clo_keypoints_mm(clo_back)["hem_width"]
        assert cb > cf, f"CLO: back hem ({cb:.1f}mm) must be wider than front ({cf:.1f}mm)"


# ── 2. Perimeter length comparisons ──────────────────────────────────────

class TestPerimeterParity:
    """Perimeter lengths must be consistent between solver polylines and CLO3D bezier chains."""

    def test_front_perimeter(self, front_panel, clo_2panel):
        """Solver front perimeter (polyline sum) vs CLO3D (bezier arc length)."""
        solver_perim_in = _poly_perimeter(front_panel["cut"])
        solver_perim_mm = solver_perim_in * INCH_TO_MM

        clo_front = next(p for p in clo_2panel["PatternList"] if p["Name"] == "Front_Panel")
        clo_perim_mm = _clo_perimeter_mm(clo_front)

        # Within 5%: solver has dense polyline (many points), CLO has exact beziers
        # Difference comes from polyline approximation of curves
        pct_diff = abs(solver_perim_mm - clo_perim_mm) / solver_perim_mm * 100
        assert pct_diff < 5.0, \
            f"Front perimeter: solver={solver_perim_mm:.1f}mm CLO={clo_perim_mm:.1f}mm ({pct_diff:.1f}% diff)"

    def test_back_perimeter(self, back_panel, clo_2panel):
        """Solver back perimeter vs CLO3D back perimeter."""
        solver_perim_in = _poly_perimeter(back_panel["cut"])
        solver_perim_mm = solver_perim_in * INCH_TO_MM

        clo_back = next(p for p in clo_2panel["PatternList"] if p["Name"] == "Back_Panel")
        clo_perim_mm = _clo_perimeter_mm(clo_back)

        pct_diff = abs(solver_perim_mm - clo_perim_mm) / solver_perim_mm * 100
        assert pct_diff < 5.0, \
            f"Back perimeter: solver={solver_perim_mm:.1f}mm CLO={clo_perim_mm:.1f}mm ({pct_diff:.1f}% diff)"

    def test_front_back_perimeter_ratio(self, front_panel, back_panel):
        """Back perimeter should be > front (deeper crotch, wider hip).
        Ratio should be ~1.02-1.15 for most pant styles."""
        f_perim = _poly_perimeter(front_panel["cut"])
        b_perim = _poly_perimeter(back_panel["cut"])
        ratio = b_perim / f_perim
        assert 1.0 < ratio < 1.2, \
            f"Back/front perimeter ratio {ratio:.3f} out of range [1.0, 1.2]"


# ── 3. Seam length parity (solver inseam vs CLO3D seam fraction) ─────────

class TestSeamLengthParity:
    """Individual seam lengths derived from CLO3D fractions must match solver lengths."""

    def test_inseam_total_length(self, solution, clo_2panel):
        """Total inseam (straight + curve) from CLO3D fractions must match solver."""
        solver_inseam_mm = solution["validation"]["front_inseam"] * INCH_TO_MM

        front_id = next(p["ID"] for p in clo_2panel["PatternList"] if p["Name"] == "Front_Panel")
        clo_front = next(p for p in clo_2panel["PatternList"] if p["Name"] == "Front_Panel")
        clo_perim = _clo_perimeter_mm(clo_front)

        # Sum both inseam seam fractions on the front panel
        inseam_names = ["inseam_straight", "inseam_curve"]
        total_frac = 0
        for s in clo_2panel["SeamLinePairGroupList"]:
            if s["Name"] in inseam_names:
                for pair in s["PairList"]:
                    for side in ["First", "Second"]:
                        if pair[side]["ShapeID"] == front_id:
                            lp = pair[side]["LengthParam"]
                            total_frac += abs(lp["fStart"] - lp["fEnd"])

        clo_inseam_mm = total_frac * clo_perim

        pct_diff = abs(solver_inseam_mm - clo_inseam_mm) / solver_inseam_mm * 100
        assert pct_diff < 10.0, \
            f"Inseam length: solver={solver_inseam_mm:.1f}mm CLO={clo_inseam_mm:.1f}mm ({pct_diff:.1f}%)"

    def test_side_seam_total_length(self, solution, clo_2panel):
        """Total side seam (top + hip-knee + knee-hem) from CLO3D must match solver."""
        solver_side_mm = solution["validation"]["front_side"] * INCH_TO_MM

        front_id = next(p["ID"] for p in clo_2panel["PatternList"] if p["Name"] == "Front_Panel")
        clo_front = next(p for p in clo_2panel["PatternList"] if p["Name"] == "Front_Panel")
        clo_perim = _clo_perimeter_mm(clo_front)

        side_names = ["side_top", "side_hip_knee", "side_knee_hem"]
        total_frac = 0
        for s in clo_2panel["SeamLinePairGroupList"]:
            if s["Name"] in side_names:
                for pair in s["PairList"]:
                    for side in ["First", "Second"]:
                        if pair[side]["ShapeID"] == front_id:
                            lp = pair[side]["LengthParam"]
                            total_frac += abs(lp["fStart"] - lp["fEnd"])

        clo_side_mm = total_frac * clo_perim

        pct_diff = abs(solver_side_mm - clo_side_mm) / solver_side_mm * 100
        assert pct_diff < 10.0, \
            f"Side seam length: solver={solver_side_mm:.1f}mm CLO={clo_side_mm:.1f}mm ({pct_diff:.1f}%)"

    def test_seam_pair_length_balance(self, clo_2panel):
        """For each paired seam, First and Second sides should have similar lengths.
        Large mismatch means seam will pucker in CLO3D simulation."""
        front_pat = next(p for p in clo_2panel["PatternList"] if p["Name"] == "Front_Panel")
        back_pat = next(p for p in clo_2panel["PatternList"] if p["Name"] == "Back_Panel")
        front_perim = _clo_perimeter_mm(front_pat)
        back_perim = _clo_perimeter_mm(back_pat)

        perim_map = {front_pat["ID"]: front_perim, back_pat["ID"]: back_perim}

        for s in clo_2panel["SeamLinePairGroupList"]:
            for pair in s["PairList"]:
                first = pair["First"]
                second = pair["Second"]
                f_len = abs(first["LengthParam"]["fStart"] - first["LengthParam"]["fEnd"]) * perim_map.get(first["ShapeID"], 1)
                s_len = abs(second["LengthParam"]["fStart"] - second["LengthParam"]["fEnd"]) * perim_map.get(second["ShapeID"], 1)

                if f_len < 1.0 or s_len < 1.0:
                    continue  # skip tiny seams

                ratio = max(f_len, s_len) / min(f_len, s_len)
                assert ratio < 1.5, \
                    f"Seam '{s['Name']}' sides unbalanced: {f_len:.1f}mm vs {s_len:.1f}mm (ratio {ratio:.2f})"


# ── 4. DXF ↔ Solver structural checks ────────────────────────────────────

class TestDXFSolverStructure:
    """DXF must faithfully represent the solver's output."""

    def test_dxf_has_all_layers(self, dxf_doc):
        layer_names = {layer.dxf.name for layer in dxf_doc.layers}
        for expected in ["CUT", "SEAM_ALLOWANCE", "GRAIN", "NOTCH", "INTERNAL", "TEXT"]:
            assert expected in layer_names, f"DXF missing layer: {expected}"

    def test_dxf_panel_count_matches_solver(self, solution, dxf_doc):
        """Number of closed CUT polylines must match solver piece count."""
        msp = dxf_doc.modelspace()
        closed = [e for e in msp if e.dxf.layer == "CUT" and e.dxftype() == "LWPOLYLINE"
                  and e.is_closed]
        assert len(closed) == len(solution["pieces"]), \
            f"DXF: {len(closed)} closed cut lines, solver: {len(solution['pieces'])} pieces"

    def test_dxf_seam_allowance_count(self, dxf_doc):
        """SEAM_ALLOWANCE layer should have offset outlines for panels with valid offsets."""
        msp = dxf_doc.modelspace()
        sa = [e for e in msp if e.dxf.layer == "SEAM_ALLOWANCE" and e.dxftype() == "LWPOLYLINE"]
        assert len(sa) >= 2, f"Expected at least 2 SA outlines, got {len(sa)}"

    def test_dxf_has_front_and_back_labels(self, dxf_doc):
        msp = dxf_doc.modelspace()
        texts = [e.dxf.text.upper() for e in msp if e.dxftype() == "TEXT"]
        assert any("FRONT" in t for t in texts), "Missing FRONT PANEL label"
        assert any("BACK" in t for t in texts), "Missing BACK PANEL label"

    def test_dxf_units_r2000(self, dxf_doc):
        assert dxf_doc.header["$INSUNITS"] == 1  # inches
        assert dxf_doc.dxfversion == "AC1015"    # R2000

    def test_dxf_front_perimeter_matches_solver(self, solution, dxf_doc):
        """DXF front panel perimeter must match solver within 2%.
        DXF is a polyline rendition of the solver's polyline — should be near-exact."""
        front = next(p for p in solution["pieces"] if p["name"] == "front_panel")
        solver_perim = _poly_perimeter(front["cut"])

        # Find the DXF panel that's closest to the solver's front dimensions
        polys = _dxf_closed_polylines(dxf_doc, "CUT")
        # Front panel: largest perimeter (main panels are biggest)
        # Sort by perimeter, pick the two biggest (front and back)
        polys.sort(key=lambda p: _poly_perimeter(p), reverse=True)
        assert len(polys) >= 2, "Need at least 2 panels in DXF"

        # One of the two biggest should match the solver front perimeter
        dxf_perims = [_poly_perimeter(p) for p in polys[:2]]
        best_match = min(dxf_perims, key=lambda dp: abs(dp - solver_perim))
        pct_diff = abs(best_match - solver_perim) / solver_perim * 100
        assert pct_diff < 2.0, \
            f"DXF front perimeter: solver={solver_perim:.2f}\" DXF={best_match:.2f}\" ({pct_diff:.1f}%)"

    def test_dxf_notch_marks_present(self, dxf_doc):
        msp = dxf_doc.modelspace()
        notches = [e for e in msp if e.dxf.layer == "NOTCH"]
        assert len(notches) >= 2, "DXF should have hip/knee notch marks"

    def test_dxf_grainlines_present(self, dxf_doc):
        msp = dxf_doc.modelspace()
        grains = [e for e in msp if e.dxf.layer == "GRAIN"]
        assert len(grains) >= 2, "DXF should have grainlines"

    def test_dxf_size_annotation(self, dxf_doc):
        """DXF must contain the waist measurement from input."""
        msp = dxf_doc.modelspace()
        texts = [e.dxf.text for e in msp if e.dxftype() == "TEXT"]
        waist_texts = [t for t in texts if "30" in t and "waist" in t.lower()]
        assert len(waist_texts) >= 1, "DXF missing waist size annotation"


# ── 5. 5-Panel CLO3D consistency ─────────────────────────────────────────

class TestFivePanelParity:
    """5-panel CLO3D JSON (FL, FR, BL, BR + 2 WB) must be internally consistent."""

    def test_5panel_has_6_patterns(self, clo_5panel):
        assert len(clo_5panel["PatternList"]) == 6

    def test_5panel_pattern_names(self, clo_5panel):
        names = {p["Name"] for p in clo_5panel["PatternList"]}
        for expected in ["Front_Left", "Front_Right", "Back_Left", "Back_Right",
                         "WB_Front", "WB_Back"]:
            assert expected in names, f"Missing: {expected}"

    def test_fl_fr_mirrored_keypoints(self, clo_5panel):
        """FL and FR must have identical keypoint measurements (they're mirrored)."""
        fl = next(p for p in clo_5panel["PatternList"] if p["Name"] == "Front_Left")
        fr = next(p for p in clo_5panel["PatternList"] if p["Name"] == "Front_Right")
        fl_k = _clo_keypoints_mm(fl)
        fr_k = _clo_keypoints_mm(fr)

        for key in ["hem_width", "total_height", "crotch_extension"]:
            assert abs(fl_k[key] - fr_k[key]) < 2.0, \
                f"FL/FR {key}: {fl_k[key]:.1f}mm vs {fr_k[key]:.1f}mm"

    def test_bl_br_mirrored_keypoints(self, clo_5panel):
        """BL and BR must have identical keypoint measurements (mirrored)."""
        bl = next(p for p in clo_5panel["PatternList"] if p["Name"] == "Back_Left")
        br = next(p for p in clo_5panel["PatternList"] if p["Name"] == "Back_Right")
        bl_k = _clo_keypoints_mm(bl)
        br_k = _clo_keypoints_mm(br)

        for key in ["hem_width", "total_height", "crotch_extension"]:
            assert abs(bl_k[key] - br_k[key]) < 2.0, \
                f"BL/BR {key}: {bl_k[key]:.1f}mm vs {br_k[key]:.1f}mm"

    def test_fl_fr_same_perimeter(self, clo_5panel):
        """Mirrored panels must have same perimeter length."""
        fl = next(p for p in clo_5panel["PatternList"] if p["Name"] == "Front_Left")
        fr = next(p for p in clo_5panel["PatternList"] if p["Name"] == "Front_Right")
        fl_p = _clo_perimeter_mm(fl)
        fr_p = _clo_perimeter_mm(fr)
        assert abs(fl_p - fr_p) < 2.0, f"FL perimeter {fl_p:.1f}mm vs FR {fr_p:.1f}mm"

    def test_bl_br_same_perimeter(self, clo_5panel):
        bl = next(p for p in clo_5panel["PatternList"] if p["Name"] == "Back_Left")
        br = next(p for p in clo_5panel["PatternList"] if p["Name"] == "Back_Right")
        bl_p = _clo_perimeter_mm(bl)
        br_p = _clo_perimeter_mm(br)
        assert abs(bl_p - br_p) < 2.0, f"BL perimeter {bl_p:.1f}mm vs BR {br_p:.1f}mm"

    def test_5panel_back_wider_hem(self, clo_5panel):
        fl = next(p for p in clo_5panel["PatternList"] if p["Name"] == "Front_Left")
        bl = next(p for p in clo_5panel["PatternList"] if p["Name"] == "Back_Left")
        assert _clo_keypoints_mm(bl)["hem_width"] > _clo_keypoints_mm(fl)["hem_width"]

    def test_5panel_seam_count(self, clo_5panel):
        """5 L + 5 R per-leg + 4 cross-leg + 6 WB = 20 seams."""
        assert len(clo_5panel["SeamLinePairGroupList"]) == 20

    def test_5panel_seam_names_complete(self, clo_5panel):
        names = {s["Name"] for s in clo_5panel["SeamLinePairGroupList"]}
        expected = {
            "side_top_L", "side_hip_knee_L", "side_knee_hem_L", "inseam_straight_L", "inseam_curve_L",
            "side_top_R", "side_hip_knee_R", "side_knee_hem_R", "inseam_straight_R", "inseam_curve_R",
            "center_front", "center_back", "crotch_front", "crotch_back",
            "wb_front_to_FL", "wb_front_to_FR", "wb_back_to_BL", "wb_back_to_BR",
            "wb_side_R", "wb_side_L",
        }
        assert not (expected - names), f"Missing seams: {expected - names}"

    def test_5panel_no_edge_overlap(self, clo_5panel):
        """No pattern edge referenced in 2+ seams (CLO3D rejects all if violated)."""
        edge_refs = {}
        for s in clo_5panel["SeamLinePairGroupList"]:
            for pair in s["PairList"]:
                for side in ["First", "Second"]:
                    shape = pair[side]["ShapeID"]
                    lp = pair[side]["LengthParam"]
                    key = (shape, round(lp["fStart"], 4), round(lp["fEnd"], 4))
                    assert key not in edge_refs, \
                        f"Edge overlap: {s['Name']} conflicts with {edge_refs.get(key)}"
                    edge_refs[key] = s["Name"]

    def test_5panel_seam_fracs_valid(self, clo_5panel):
        for s in clo_5panel["SeamLinePairGroupList"]:
            for pair in s["PairList"]:
                for side in ["First", "Second"]:
                    lp = pair[side]["LengthParam"]
                    assert 0.0 <= lp["fStart"] <= 1.0
                    assert 0.0 <= lp["fEnd"] <= 1.0
                    assert abs(lp["fStart"] - lp["fEnd"]) > 0.005, \
                        f"{s['Name']} {side} near-zero seam"

    def test_5panel_wb_rectangular(self, clo_5panel):
        for name in ["WB_Front", "WB_Back"]:
            wb = next(p for p in clo_5panel["PatternList"] if p["Name"] == name)
            lines = wb["ShapeInfo"]["LineList"]
            assert len(lines) == 5, f"{name}: expected 5 lines, got {len(lines)}"
            for line in lines:
                assert len(line["PointList"]) == 2

    def test_5panel_fl_matches_solver_front(self, front_panel, clo_5panel):
        """FL keypoints must match solver front panel."""
        solver = _solver_keypoints_in(front_panel)
        fl = next(p for p in clo_5panel["PatternList"] if p["Name"] == "Front_Left")
        clo = _clo_keypoints_mm(fl)

        assert abs(solver["hem_width"] * INCH_TO_MM - clo["hem_width"]) < 5.0
        assert abs(solver["total_height"] * INCH_TO_MM - clo["total_height"]) < 10.0
        assert abs(solver["crotch_extension"] * INCH_TO_MM - clo["crotch_extension"]) < 8.0


# ── 6. Multi-size regression ─────────────────────────────────────────────

class TestMultiSizeFormatParity:
    """All formats must produce valid, consistent output across sizes."""

    @pytest.mark.parametrize("measurements", SIZES)
    def test_all_formats_generate(self, measurements, tmp_path):
        m = {**measurements}
        sol = solve(m, DEFAULT_CONSTRUCTION, DEFAULT_EASE)

        dxf_p = str(tmp_path / f"pant_{m['waist']}.dxf")
        to_dxf(sol, dxf_p)
        assert os.path.exists(dxf_p) and os.path.getsize(dxf_p) > 1000

        clo2_p = str(tmp_path / f"clo2_{m['waist']}.json")
        generate_clo3d_json(m, clo2_p)
        assert os.path.exists(clo2_p)

        clo5_p = str(tmp_path / f"clo5_{m['waist']}.json")
        generate_5panel_json(m, clo5_p)
        with open(clo5_p) as f:
            data = json.load(f)
        assert len(data["PatternList"]) == 6
        assert len(data["SeamLinePairGroupList"]) == 20

    @pytest.mark.parametrize("measurements", SIZES)
    def test_inseam_delta_under_half_inch(self, measurements):
        m = {**measurements}
        sol = solve(m, DEFAULT_CONSTRUCTION, DEFAULT_EASE)
        assert sol["validation"]["inseam_delta"] < 0.5, \
            f"Size {m['waist']}: inseam delta {sol['validation']['inseam_delta']:.3f}\""

    @pytest.mark.parametrize("measurements", SIZES)
    def test_perimeter_parity_across_sizes(self, measurements, tmp_path):
        """Solver vs CLO3D perimeter must stay within 5% for every size."""
        m = {**measurements}
        sol = solve(m, DEFAULT_CONSTRUCTION, DEFAULT_EASE)
        front = next(p for p in sol["pieces"] if p["name"] == "front_panel")
        solver_perim_mm = _poly_perimeter(front["cut"]) * INCH_TO_MM

        clo2_p = str(tmp_path / f"perim_{m['waist']}.json")
        generate_clo3d_json(m, clo2_p)
        with open(clo2_p) as f:
            data = json.load(f)
        clo_front = next(p for p in data["PatternList"] if p["Name"] == "Front_Panel")
        clo_perim = _clo_perimeter_mm(clo_front)

        pct_diff = abs(solver_perim_mm - clo_perim) / solver_perim_mm * 100
        assert pct_diff < 5.0, \
            f"Size {m['waist']}: perimeter solver={solver_perim_mm:.0f}mm CLO={clo_perim:.0f}mm ({pct_diff:.1f}%)"

    @pytest.mark.parametrize("measurements", SIZES)
    def test_dxf_readable(self, measurements, tmp_path):
        m = {**measurements}
        sol = solve(m, DEFAULT_CONSTRUCTION, DEFAULT_EASE)
        p = str(tmp_path / f"check_{m['waist']}.dxf")
        to_dxf(sol, p)
        doc = ezdxf.readfile(p)
        assert doc.dxfversion == "AC1015"


# ── 7. Measurement round-trip ─────────────────────────────────────────────

class TestMeasurementRoundTrip:
    """Input measurements must be recoverable from output artifacts."""

    def test_solver_validation_complete(self, solution):
        v = solution["validation"]
        for key in ["front_inseam", "back_inseam", "front_side", "back_side",
                     "inseam_delta", "side_delta", "b_drop"]:
            assert key in v and v[key] > 0, f"Validation missing/zero: {key}"

    def test_hem_width_traces_to_input(self, front_panel, back_panel):
        """Sum of front + back hem widths should equal input leg_opening."""
        f_hem = _solver_keypoints_in(front_panel)["hem_width"]
        b_hem = _solver_keypoints_in(back_panel)["hem_width"]
        expected = SAMPLE["leg_opening"]
        actual = f_hem + b_hem
        assert abs(actual - expected) < 1.0, \
            f"Hem widths {f_hem:.2f}\" + {b_hem:.2f}\" = {actual:.2f}\", expected ~{expected}\""

    def test_outseam_traces_to_input(self, front_panel):
        """Front panel total height should approximate the outseam measurement."""
        height = _solver_keypoints_in(front_panel)["total_height"]
        expected = SAMPLE["outseam"]
        assert abs(height - expected) < 2.0, \
            f"Panel height {height:.2f}\" vs outseam input {expected}\""

    def test_dxf_waist_annotation(self, dxf_doc):
        msp = dxf_doc.modelspace()
        texts = [e.dxf.text for e in msp if e.dxftype() == "TEXT"]
        assert any("30" in t and "waist" in t.lower() for t in texts), \
            "DXF missing waist size annotation"
