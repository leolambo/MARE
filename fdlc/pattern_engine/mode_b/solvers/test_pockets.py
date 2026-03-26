#!/usr/bin/env python3
"""Tests for pocket modules: in-seam front pocket and patch back pocket.

Run: cd ~/base/mare-pipeline && python3 -m pytest fdlc/pattern_engine/mode_b/solvers/test_pockets.py -v
"""

from __future__ import annotations

import math
import pytest

from fdlc.pattern_engine.mode_b.solvers.pant_block import solve, _build_front_panel, _build_back_panel, _match_seams
from fdlc.pattern_engine.mode_b.solvers.pattern_utils import DEFAULT_CONSTRUCTION, DEFAULT_EASE, _dist, _bbox, _polyline_length
from fdlc.pattern_engine.mode_b.pockets.in_seam import build as build_in_seam, DEFAULTS as IN_SEAM_DEFAULTS
from fdlc.pattern_engine.mode_b.pockets.patch import build as build_patch, DEFAULTS as PATCH_DEFAULTS

SAMPLE = {
    "waist": 30.0, "hip": 42.0, "front_rise": 10.75, "back_rise": 12.75,
    "inseam": 30.0, "outseam": 40.0, "thigh": 26.0, "leg_opening": 23.5, "fly_length": 10.0,
}


@pytest.fixture
def solution():
    return solve(SAMPLE, DEFAULT_CONSTRUCTION, DEFAULT_EASE)


@pytest.fixture
def front(solution):
    return next(p for p in solution["pieces"] if p["name"] == "front_panel")


@pytest.fixture
def back(solution):
    return next(p for p in solution["pieces"] if p["name"] == "back_panel")


@pytest.fixture
def front_raw():
    c = DEFAULT_CONSTRUCTION
    e = DEFAULT_EASE
    return _build_front_panel(SAMPLE, c, e)


@pytest.fixture
def back_raw():
    front, back = _match_seams(SAMPLE, DEFAULT_CONSTRUCTION, DEFAULT_EASE)
    return back


@pytest.fixture
def in_seam_result(front_raw):
    return build_in_seam(front_raw, SAMPLE, DEFAULT_CONSTRUCTION)


@pytest.fixture
def patch_result(back_raw):
    return build_patch(back_raw, SAMPLE, DEFAULT_CONSTRUCTION)


# ── In-seam pocket ────────────────────────────────────────────────────────

class TestInSeamStructure:
    """Result schema and piece structure."""

    def test_result_has_required_keys(self, in_seam_result):
        for key in ["opening_lines", "opening_notches", "pieces", "side_seam_split", "meta"]:
            assert key in in_seam_result, f"Missing key: {key}"

    def test_has_two_pieces(self, in_seam_result):
        assert len(in_seam_result["pieces"]) == 2

    def test_piece_names(self, in_seam_result):
        names = {p["name"] for p in in_seam_result["pieces"]}
        assert "front_pocket_facing" in names
        assert "front_pocket_bag" in names

    def test_pieces_have_count_2(self, in_seam_result):
        for p in in_seam_result["pieces"]:
            assert p["count"] == 2, f"{p['name']} should have count=2 (left+right)"

    def test_pieces_are_mirrored(self, in_seam_result):
        for p in in_seam_result["pieces"]:
            assert p["mirror"] is True

    def test_pieces_have_cut(self, in_seam_result):
        for p in in_seam_result["pieces"]:
            assert len(p["cut"]) >= 4, f"{p['name']} cut outline too short"

    def test_meta_pocket_type(self, in_seam_result):
        assert in_seam_result["meta"]["pocket_type"] == "in_seam"


class TestInSeamGeometry:
    """Opening geometry and placement."""

    def test_has_opening_line(self, in_seam_result):
        assert len(in_seam_result["opening_lines"]) == 1
        line = in_seam_result["opening_lines"][0]
        assert len(line) == 2, "Opening line should have exactly 2 endpoints"

    def test_opening_length_matches_config(self, in_seam_result):
        line = in_seam_result["opening_lines"][0]
        length = _dist(line[0], line[1])
        expected = IN_SEAM_DEFAULTS["length"]
        assert abs(length - expected) < 0.5, \
            f"Opening length {length:.2f}\" expected ~{expected}\""

    def test_opening_notches_at_endpoints(self, in_seam_result):
        notches = in_seam_result["opening_notches"]
        assert len(notches) == 2

        line = in_seam_result["opening_lines"][0]
        top_pt, _ = notches[0]
        bot_pt, _ = notches[1]
        assert _dist(top_pt, line[0]) < 0.5, "Top notch should be at opening top"
        assert _dist(bot_pt, line[1]) < 0.5, "Bot notch should be at opening bottom"

    def test_opening_on_side_seam(self, in_seam_result, front_raw):
        """Opening endpoints must be on or near the front panel side seam."""
        line = in_seam_result["opening_lines"][0]
        pts = front_raw["cut"]
        xs = [p[0] for p in pts]
        max_x = max(xs)

        for pt in line:
            assert pt[0] > max_x * 0.5, \
                f"Opening point {pt} not near side seam (max_x={max_x:.2f}\")"

    def test_opening_drop_from_waist(self, in_seam_result, front_raw):
        """Top of opening should be ~1.5\" below waist."""
        pts = front_raw["cut"]
        waist_y = min(p[1] for p in pts)
        top_pt = in_seam_result["opening_lines"][0][0]
        drop = top_pt[1] - waist_y
        expected = IN_SEAM_DEFAULTS["drop"]
        assert abs(drop - expected) < 0.5, \
            f"Opening drop {drop:.2f}\" expected ~{expected}\""

    def test_side_seam_split_fracs_valid(self, in_seam_result):
        """Perimeter fractions must be in [0, 1] and top < bot."""
        frac_top, frac_bot = in_seam_result["side_seam_split"]
        assert 0.0 <= frac_top < frac_bot <= 1.0, \
            f"Invalid split fracs: top={frac_top} bot={frac_bot}"

    def test_side_seam_split_span_reasonable(self, in_seam_result):
        """Opening fraction span should be > 0.01 (not degenerate)."""
        frac_top, frac_bot = in_seam_result["side_seam_split"]
        assert (frac_bot - frac_top) > 0.01, "Split span too small — degenerate opening"


class TestInSeamBagShape:
    """Bag piece geometry: must be a closed valid shape large enough to function."""

    def test_bag_is_closed(self, in_seam_result):
        bag = next(p for p in in_seam_result["pieces"] if p["name"] == "front_pocket_bag")
        pts = bag["cut"]
        assert _dist(pts[0], pts[-1]) < 0.1, "Bag outline not closed"

    def test_bag_depth(self, in_seam_result):
        """Bag must be at least `depth` inches tall."""
        bag = next(p for p in in_seam_result["pieces"] if p["name"] == "front_pocket_bag")
        _, y0, _, y1 = _bbox(bag["cut"])
        h = y1 - y0
        assert h >= IN_SEAM_DEFAULTS["depth"] * 0.8, \
            f"Bag height {h:.2f}\" too shallow (expected ~{IN_SEAM_DEFAULTS['depth']}\")"

    def test_bag_width(self, in_seam_result):
        bag = next(p for p in in_seam_result["pieces"] if p["name"] == "front_pocket_bag")
        x0, _, x1, _ = _bbox(bag["cut"])
        w = x1 - x0
        assert w >= IN_SEAM_DEFAULTS["width"] * 0.8, \
            f"Bag width {w:.2f}\" too narrow"

    def test_facing_narrower_than_bag(self, in_seam_result):
        facing = next(p for p in in_seam_result["pieces"] if p["name"] == "front_pocket_facing")
        bag = next(p for p in in_seam_result["pieces"] if p["name"] == "front_pocket_bag")
        fx0, _, fx1, _ = _bbox(facing["cut"])
        bx0, _, bx1, _ = _bbox(bag["cut"])
        assert (fx1 - fx0) < (bx1 - bx0), "Facing should be narrower than bag"

    def test_facing_same_height_as_opening(self, in_seam_result):
        """Facing height must match opening length (it lines the opening)."""
        facing = next(p for p in in_seam_result["pieces"] if p["name"] == "front_pocket_facing")
        _, y0, _, y1 = _bbox(facing["cut"])
        h = y1 - y0
        expected = IN_SEAM_DEFAULTS["length"]
        assert abs(h - expected) < 0.5, \
            f"Facing height {h:.2f}\" should match opening length {expected}\""


class TestInSeamSolverIntegration:
    """In-seam pocket wired into solve() correctly."""

    def test_front_panel_has_opening_line(self, solution):
        front = next(p for p in solution["pieces"] if p["name"] == "front_panel")
        assert len(front["internal_lines"]) >= 1, "Front panel missing pocket opening line"

    def test_front_panel_has_pocket_notches(self, solution):
        front = next(p for p in solution["pieces"] if p["name"] == "front_panel")
        pocket_notches = [n for n in front["notches"] if "pocket" in n[1]]
        assert len(pocket_notches) == 2, "Front panel should have 2 pocket opening notches"

    def test_facing_and_bag_in_pieces(self, solution):
        names = [p["name"] for p in solution["pieces"]]
        assert "front_pocket_facing" in names
        assert "front_pocket_bag" in names

    def test_no_old_slash_stub(self, solution):
        """Old slash stub (diagonal line from waist) should not exist."""
        front = next(p for p in solution["pieces"] if p["name"] == "front_panel")
        for line in front["internal_lines"]:
            if len(line) == 2:
                p0, p1 = line[0], line[1]
                # Old stub went diagonally from near waist-side seam downward-inward
                # It was ~6.5" long and angled ~30 degrees
                # In-seam opening is vertical (on side seam) — angle should be < 30 degrees from vertical
                dx = abs(p1[0] - p0[0])
                dy = abs(p1[1] - p0[1])
                if dy > 0.1:
                    angle_from_vertical = math.degrees(math.atan2(dx, dy))
                    assert angle_from_vertical < 30, \
                        f"Opening line too diagonal ({angle_from_vertical:.0f}°) — possible slash stub"

    def test_pocket_result_in_solution(self, solution):
        assert solution["pockets"]["front"] is not None
        assert solution["pockets"]["back"] is not None


# ── Patch pocket ──────────────────────────────────────────────────────────

class TestPatchStructure:
    """Result schema and piece structure."""

    def test_result_has_required_keys(self, patch_result):
        for key in ["opening_lines", "opening_notches", "pieces", "placement", "meta"]:
            assert key in patch_result, f"Missing key: {key}"

    def test_has_one_piece(self, patch_result):
        assert len(patch_result["pieces"]) == 1

    def test_piece_name(self, patch_result):
        assert patch_result["pieces"][0]["name"] == "back_pocket_patch"

    def test_piece_count_2(self, patch_result):
        assert patch_result["pieces"][0]["count"] == 2

    def test_meta_pocket_type(self, patch_result):
        assert patch_result["meta"]["pocket_type"] == "patch"

    def test_has_sewing_note(self, patch_result):
        piece = patch_result["pieces"][0]
        assert "sewing_note" in piece["meta"]
        assert len(piece["meta"]["sewing_note"]) > 10


class TestPatchGeometry:
    """Patch outline, placement, and dimensions."""

    def test_patch_has_placement_outline(self, patch_result):
        """Should have one placement line drawn on the back panel."""
        assert len(patch_result["opening_lines"]) == 1
        outline = patch_result["opening_lines"][0]
        assert len(outline) >= 4

    def test_patch_has_corner_notches(self, patch_result):
        notches = patch_result["opening_notches"]
        assert len(notches) == 2
        labels = [n[1] for n in notches]
        assert "patch_top_left" in labels
        assert "patch_top_right" in labels

    def test_patch_notches_at_top_corners(self, patch_result):
        """Notches should be at the top-left and top-right of the placement outline."""
        notches = patch_result["opening_notches"]
        xs = [n[0][0] for n in notches]
        # Two distinct X positions (left and right corners)
        assert abs(xs[0] - xs[1]) > 1.0, "Notches not at opposite corners"

    def test_placement_center_on_panel(self, patch_result, back_raw):
        """Placement center X must be within the back panel's X range."""
        pts = back_raw["cut"]
        xs = [p[0] for p in pts]
        center_x = patch_result["placement"]["center_x"]
        assert min(xs) < center_x < max(xs), \
            f"Patch center_x {center_x:.2f}\" outside panel range [{min(xs):.2f}, {max(xs):.2f}]"

    def test_placement_below_waist(self, patch_result, back_raw):
        """Patch must be below the waist (drop > 0)."""
        pts = back_raw["cut"]
        waist_y = min(p[1] for p in pts)
        top_y = patch_result["placement"]["top_y"]
        assert top_y > waist_y, "Patch top must be below waist"

    def test_placement_drop_from_waist(self, patch_result, back_raw):
        """Patch top should be ~3.5\" below waist seam."""
        pts = back_raw["cut"]
        waist_y = min(p[1] for p in pts)
        top_y = patch_result["placement"]["top_y"]
        drop = top_y - waist_y
        expected = PATCH_DEFAULTS["drop"]
        assert abs(drop - expected) < 0.5, f"Patch drop {drop:.2f}\" expected ~{expected}\""

    def test_patch_above_hip(self, patch_result, back_raw):
        """Patch top should be above hip level (~8.5\" down)."""
        pts = back_raw["cut"]
        waist_y = min(p[1] for p in pts)
        top_y = patch_result["placement"]["top_y"]
        drop = top_y - waist_y
        assert drop < 8.5, f"Patch drop {drop:.2f}\" — patch is at or below hip"


class TestPatchPieceShape:
    """Patch piece cut outline geometry."""

    def test_patch_is_closed(self, patch_result):
        piece = patch_result["pieces"][0]
        pts = piece["cut"]
        assert _dist(pts[0], pts[-1]) < 0.1, "Patch outline not closed"

    def test_patch_width(self, patch_result):
        piece = patch_result["pieces"][0]
        x0, _, x1, _ = _bbox(piece["cut"])
        w = x1 - x0
        assert abs(w - PATCH_DEFAULTS["width"]) < 0.5, \
            f"Patch width {w:.2f}\" expected ~{PATCH_DEFAULTS['width']}\""

    def test_patch_height(self, patch_result):
        piece = patch_result["pieces"][0]
        _, y0, _, y1 = _bbox(piece["cut"])
        # Height includes hem fold allowance at top (1") + pocket depth
        h = y1 - y0
        assert h >= PATCH_DEFAULTS["height"], \
            f"Patch height {h:.2f}\" should be >= {PATCH_DEFAULTS['height']}\""

    def test_patch_has_topstitch_internal_line(self, patch_result):
        piece = patch_result["pieces"][0]
        assert len(piece["internal_lines"]) >= 1, "Patch should have topstitch line"

    def test_patch_topstitch_smaller_than_outline(self, patch_result):
        """Topstitch inset line must fit inside the outer cut line."""
        piece = patch_result["pieces"][0]
        if not piece["internal_lines"]:
            pytest.skip("No topstitch line generated")
        x0, y0, x1, y1 = _bbox(piece["cut"])
        tx0, ty0, tx1, ty1 = _bbox(piece["internal_lines"][0])
        assert tx0 > x0 and ty0 > y0 and tx1 < x1 and ty1 < y1, \
            "Topstitch line not inset from cut line"

    def test_patch_has_grainline(self, patch_result):
        piece = patch_result["pieces"][0]
        assert len(piece["grainline"]) == 2


class TestPatchSolverIntegration:
    """Patch pocket wired into solve() correctly."""

    def test_back_panel_has_placement_outline(self, solution):
        back = next(p for p in solution["pieces"] if p["name"] == "back_panel")
        assert len(back["internal_lines"]) >= 1, "Back panel missing patch placement outline"

    def test_back_panel_has_placement_notches(self, solution):
        back = next(p for p in solution["pieces"] if p["name"] == "back_panel")
        patch_notches = [n for n in back["notches"] if "patch" in n[1]]
        assert len(patch_notches) == 2

    def test_patch_piece_in_solution(self, solution):
        names = [p["name"] for p in solution["pieces"]]
        assert "back_pocket_patch" in names

    def test_no_old_rect_stubs(self, solution):
        """Old placeholder pieces should not exist."""
        names = [p["name"] for p in solution["pieces"]]
        assert "back_pocket_welt" not in names, "Old welt stub still present"
        assert "back_pocket_bag" not in names, "Old back bag stub still present"
        assert "front_pocket_bag" not in names or \
               next(p for p in solution["pieces"] if p["name"] == "front_pocket_bag")["meta"].get("pocket_type") == "in_seam", \
               "Old generic rect bag still present"


# ── Piece count and DXF integration ──────────────────────────────────────

class TestPieceCount:
    """Solver piece list with pocket modules."""

    EXPECTED = [
        "front_panel", "back_panel", "waistband", "fly_shield",
        "fly_extension", "belt_loop_strip",
        "front_pocket_facing", "front_pocket_bag", "back_pocket_patch",
    ]

    def test_all_expected_pieces_present(self, solution):
        names = [p["name"] for p in solution["pieces"]]
        for expected in self.EXPECTED:
            assert expected in names, f"Missing piece: {expected}"

    def test_piece_count(self, solution):
        assert len(solution["pieces"]) == 9

    def test_dxf_generates_without_error(self, solution, tmp_path):
        from fdlc.pattern_engine.mode_b.solvers.dxf_export import to_dxf
        import os
        out = str(tmp_path / "pockets.dxf")
        to_dxf(solution, out)
        assert os.path.exists(out)
        assert os.path.getsize(out) > 1000

    def test_dxf_has_correct_piece_count(self, solution, tmp_path):
        from fdlc.pattern_engine.mode_b.solvers.dxf_export import to_dxf
        import ezdxf
        out = str(tmp_path / "pockets_count.dxf")
        to_dxf(solution, out)
        doc = ezdxf.readfile(out)
        msp = doc.modelspace()
        closed = [e for e in msp if e.dxf.layer == "CUT" and e.dxftype() == "LWPOLYLINE" and e.is_closed]
        assert len(closed) == len(solution["pieces"])


# ── Config overrides ──────────────────────────────────────────────────────

class TestPocketConfigOverrides:
    """Pocket dimensions should respond to construction config overrides."""

    def test_in_seam_length_override(self):
        front, _ = _match_seams(SAMPLE, DEFAULT_CONSTRUCTION, DEFAULT_EASE)
        c = {**DEFAULT_CONSTRUCTION, "in_seam_length": 8.0}
        result = build_in_seam(front, SAMPLE, c)
        line = result["opening_lines"][0]
        length = _dist(line[0], line[1])
        assert abs(length - 8.0) < 0.5, f"Override length {length:.2f}\" expected ~8.0\""

    def test_patch_width_override(self):
        _, back = _match_seams(SAMPLE, DEFAULT_CONSTRUCTION, DEFAULT_EASE)
        c = {**DEFAULT_CONSTRUCTION, "patch_width": 7.0}
        result = build_patch(back, SAMPLE, c)
        piece = result["pieces"][0]
        x0, _, x1, _ = _bbox(piece["cut"])
        assert abs((x1 - x0) - 7.0) < 0.5, f"Override width {x1-x0:.2f}\" expected ~7.0\""

    def test_no_front_pocket(self):
        c = {**DEFAULT_CONSTRUCTION, "pocket_type": None}
        sol = solve(SAMPLE, c, DEFAULT_EASE)
        names = [p["name"] for p in sol["pieces"]]
        assert "front_pocket_facing" not in names
        assert "front_pocket_bag" not in names
        assert sol["pockets"]["front"] is None

    def test_no_back_pocket(self):
        c = {**DEFAULT_CONSTRUCTION, "back_pocket_type": None}
        sol = solve(SAMPLE, c, DEFAULT_EASE)
        names = [p["name"] for p in sol["pieces"]]
        assert "back_pocket_patch" not in names
        assert sol["pockets"]["back"] is None
