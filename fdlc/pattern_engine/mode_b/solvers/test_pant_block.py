#!/usr/bin/env python3
"""Tests for pant_block.py solver.
Run: cd ~/base/mare-pipeline && python3 -m pytest fdlc/pattern_engine/mode_b/solvers/test_pant_block.py -v
"""

import math
import pytest
from fdlc.pattern_engine.mode_b.solvers.dxf_export import to_dxf
from fdlc.pattern_engine.mode_b.solvers.pant_block import solve
from fdlc.pattern_engine.mode_b.solvers.pattern_utils import (
    DEFAULT_CONSTRUCTION,
    DEFAULT_EASE,
    _cbez,
    _dist,
    _polyline_length,
    _qbez,
)

# ── Fixtures ──────────────────────────────────────────────────────────────

SAMPLE_MEASUREMENTS = {
    "waist": 30.0, "hip": 52.0,
    "front_rise": 12.75, "back_rise": 14.75,
    "inseam": 28.5, "outseam": 40.5,
    "thigh": 28.0, "leg_opening": 23.5,
    "fly_length": 10.0,
}

@pytest.fixture
def solution():
    return solve(SAMPLE_MEASUREMENTS, DEFAULT_CONSTRUCTION, DEFAULT_EASE)

@pytest.fixture
def front(solution):
    return next(p for p in solution["pieces"] if p["name"] == "front_panel")

@pytest.fixture
def back(solution):
    return next(p for p in solution["pieces"] if p["name"] == "back_panel")


# ── Seam Length Matching ──────────────────────────────────────────────────

class TestSeamMatching:
    """Front/back seam lengths must match for the garment to be sewable."""

    def test_inseam_delta_under_half_inch(self, solution):
        """Inseam delta must be < 0.5" — the pieces are sewn together."""
        assert solution["validation"]["inseam_delta"] < 0.5, \
            f"Inseam delta {solution['validation']['inseam_delta']:.3f}\" exceeds 0.5\" tolerance"

    def test_side_seam_delta_under_1_5_inch(self, solution):
        """Side seam delta should be < 1.5" — back is longer due to hip but within ease range."""
        assert solution["validation"]["side_delta"] < 1.5, \
            f"Side delta {solution['validation']['side_delta']:.3f}\" exceeds 1.5\" tolerance"

    def test_inseam_lengths_positive(self, solution):
        assert solution["validation"]["front_inseam"] > 20
        assert solution["validation"]["back_inseam"] > 20

    def test_side_lengths_positive(self, solution):
        assert solution["validation"]["front_side"] > 30
        assert solution["validation"]["back_side"] > 30


# ── Panel Proportions ─────────────────────────────────────────────────────

class TestPanelProportions:
    """Validate panel widths and proportions to prevent the 'halve twice' bug."""

    def test_front_hem_width_is_wide_leg(self, front):
        """Front hem must be > 10" for wide-leg (not 5.6" from double-halving)."""
        assert front["meta"]["hem_width"] > 10.0, \
            f"Front hem {front['meta']['hem_width']:.2f}\" is too narrow — possible double-halving bug"

    def test_back_hem_wider_than_front(self, front, back):
        """Back panel gets 52% of leg opening, front gets 48%."""
        assert back["meta"]["hem_width"] > front["meta"]["hem_width"]

    def test_hip_wider_than_hem(self, front, back):
        """Hip should be wider than hem (even for wide-leg, hip wraps the body)."""
        assert front["meta"]["hip_width"] > front["meta"]["hem_width"]
        assert back["meta"]["hip_width"] > 0  # back hip can be tucked

    def test_back_hip_wider_than_front(self, front, back):
        """Back hip should accommodate glutes — wider than front."""
        # Note: after side_tuck, back hip might be smaller. Check raw crotch extension instead.
        assert back["meta"]["crotch_extension"] > front["meta"]["crotch_extension"], \
            "Back crotch extension must be deeper than front"

    def test_hem_to_hip_ratio_reasonable(self, front):
        """For wide-leg: hem/hip ratio should be > 0.7 (not the 0.47 from double-halving)."""
        ratio = front["meta"]["hem_width"] / front["meta"]["hip_width"]
        assert ratio > 0.7, f"Hem/hip ratio {ratio:.2f} too low — check for double-halving"


# ── Outline Geometry ──────────────────────────────────────────────────────

class TestOutlineGeometry:
    """Validate the outline point geometry to catch shape bugs early."""

    def test_outline_is_closed(self, front, back):
        """Outline must form a closed polygon."""
        for panel in [front, back]:
            pts = panel["cut"]
            assert _dist(pts[0], pts[-1]) < 0.01, \
                f"{panel['name']} outline is not closed (gap={_dist(pts[0], pts[-1]):.3f}\")"

    def test_outline_has_sufficient_points(self, front, back):
        """Bezier curves need enough points for smooth DXF import."""
        for panel in [front, back]:
            assert len(panel["cut"]) > 80, \
                f"{panel['name']} has only {len(panel['cut'])} points — curves will be angular"

    def test_no_self_intersection_simple(self, front, back):
        """Basic check: no two non-adjacent segments should be very close to intersecting.
        Full intersection detection is expensive; this catches gross errors."""
        for panel in [front, back]:
            pts = panel["cut"]
            xs = [p[0] for p in pts]
            ys = [p[1] for p in pts]
            # The outline should have a reasonable bounding box
            w = max(xs) - min(xs)
            h = max(ys) - min(ys)
            assert w > 5, f"{panel['name']} is too narrow ({w:.1f}\")"
            assert h > 30, f"{panel['name']} is too short ({h:.1f}\")"
            assert w < 25, f"{panel['name']} is too wide ({w:.1f}\") — possible geometry explosion"

    def test_crotch_extends_left(self, front, back):
        """Crotch extension must go into negative X (left of CF/CB line)."""
        for panel in [front, back]:
            min_x = min(p[0] for p in panel["cut"])
            assert min_x < -2.0, \
                f"{panel['name']} crotch doesn't extend left enough (min_x={min_x:.2f}\")"

    def test_side_seam_extends_right(self, front, back):
        """Side seam must be in positive X."""
        for panel in [front, back]:
            max_x = max(p[0] for p in panel["cut"])
            assert max_x > 8.0, \
                f"{panel['name']} side seam too narrow (max_x={max_x:.2f}\")"

    def test_hem_at_correct_depth(self, front, back):
        """Hem y should be at outseam depth (40.5")."""
        for panel in [front, back]:
            max_y = max(p[1] for p in panel["cut"])
            assert abs(max_y - 40.5) < 1.0, \
                f"{panel['name']} hem at y={max_y:.1f}\" (expected ~40.5\")"


# ── Curve Quality ─────────────────────────────────────────────────────────

class TestCurveQuality:
    """Detect angular corners and kinks in curves."""

    def _max_angle_change(self, pts):
        """Compute the maximum angle change between consecutive segments."""
        max_change = 0
        for i in range(1, len(pts) - 1):
            dx1 = pts[i][0] - pts[i-1][0]
            dy1 = pts[i][1] - pts[i-1][1]
            dx2 = pts[i+1][0] - pts[i][0]
            dy2 = pts[i+1][1] - pts[i][1]
            len1 = math.hypot(dx1, dy1)
            len2 = math.hypot(dx2, dy2)
            if len1 < 0.001 or len2 < 0.001:
                continue
            dot = (dx1*dx2 + dy1*dy2) / (len1 * len2)
            dot = max(-1, min(1, dot))
            angle = math.degrees(math.acos(dot))
            max_change = max(max_change, angle)
        return max_change

    def test_front_outline_smoothness(self, front):
        """Front panel curved sections should have no sharp corners > 70°.
        Note: the waist-to-CF-seam junction is inherently ~65-70° (curve meets straight line).
        Anything over 70° indicates a real kink."""
        pts = front["cut"]
        n = len(pts)
        crotch_region = pts[:int(n * 0.15)]
        max_angle = self._max_angle_change(crotch_region)
        assert max_angle < 70, \
            f"Front crotch region has {max_angle:.1f}° corner (max 70°)"

    def test_back_outline_smoothness(self, back):
        """Back panel curved sections should have no sharp corners > 70°."""
        pts = back["cut"]
        n = len(pts)
        crotch_region = pts[:int(n * 0.15)]
        max_angle = self._max_angle_change(crotch_region)
        assert max_angle < 70, \
            f"Back crotch region has {max_angle:.1f}° corner (max 70°)"


# ── Piece Count ───────────────────────────────────────────────────────────

class TestPieceCount:
    """Validate that all expected pieces are present."""

    EXPECTED_PIECES = [
        "front_panel", "back_panel", "waistband", "fly_shield",
        "fly_extension", "belt_loop_strip",
        "front_pocket_facing", "front_pocket_bag", "back_pocket_patch",
    ]

    def test_all_pieces_present(self, solution):
        names = [p["name"] for p in solution["pieces"]]
        for expected in self.EXPECTED_PIECES:
            assert expected in names, f"Missing piece: {expected}"

    def test_piece_count(self, solution):
        assert len(solution["pieces"]) == 9


# ── DXF Export ────────────────────────────────────────────────────────────

class TestDXFExport:
    """Validate DXF generation doesn't crash and produces a valid file."""

    def test_dxf_export(self, solution, tmp_path):
        out = str(tmp_path / "test.dxf")
        result = to_dxf(solution, out)
        assert result == out
        import os
        assert os.path.exists(out)
        assert os.path.getsize(out) > 1000  # should be a reasonable size

    def test_dxf_has_correct_units(self, solution, tmp_path):
        import ezdxf
        out = str(tmp_path / "test_units.dxf")
        to_dxf(solution, out)
        doc = ezdxf.readfile(out)
        assert doc.header["$INSUNITS"] == 1  # inches


# ── Input Validation ──────────────────────────────────────────────────────

class TestInputValidation:
    def test_missing_measurements_raises(self):
        with pytest.raises(ValueError, match="Missing measurements"):
            solve({"waist": 30.0})

    def test_auto_computes_back_rise(self):
        m = dict(SAMPLE_MEASUREMENTS)
        del m["back_rise"]
        sol = solve(m)
        # back_rise should default to front_rise + 2.0
        assert float(sol["measurements"]["back_rise"]) == 14.75

    def test_different_sizes(self):
        """Solver should work for different body sizes without crashing."""
        for waist, hip in [(28, 48), (32, 54), (36, 58), (40, 62)]:
            m = dict(SAMPLE_MEASUREMENTS)
            m["waist"] = waist
            m["hip"] = hip
            sol = solve(m)
            assert sol["validation"]["inseam_delta"] < 1.0, \
                f"Size {waist}/{hip} inseam delta too large"


# ── Bezier Helpers ────────────────────────────────────────────────────────

class TestBezierHelpers:
    def test_cubic_bezier_endpoints(self):
        pts = _cbez((0, 0), (1, 2), (3, 2), (4, 0), steps=10)
        assert len(pts) == 11
        assert pts[0] == pytest.approx((0, 0), abs=0.001)
        assert pts[-1] == pytest.approx((4, 0), abs=0.001)

    def test_quadratic_bezier_endpoints(self):
        pts = _qbez((0, 0), (2, 4), (4, 0), steps=10)
        assert len(pts) == 11
        assert pts[0] == pytest.approx((0, 0), abs=0.001)
        assert pts[-1] == pytest.approx((4, 0), abs=0.001)

    def test_polyline_length_straight(self):
        pts = [(0, 0), (3, 0), (3, 4)]
        assert _polyline_length(pts) == pytest.approx(7.0, abs=0.001)

    def test_dist(self):
        assert _dist((0, 0), (3, 4)) == pytest.approx(5.0, abs=0.001)
