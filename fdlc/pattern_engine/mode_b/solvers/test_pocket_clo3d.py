#!/usr/bin/env python3
"""Tests for CLO3D pocket seam integration.

Validates that in-seam pocket pieces and seams are correctly generated in
generate_5panel_json when construction config includes pocket_type="in_seam".

Run: cd ~/base/mare-pipeline && python3 -m pytest fdlc/pattern_engine/mode_b/solvers/test_pocket_clo3d.py -v
"""

from __future__ import annotations

import json
import math
import os
import pytest

from fdlc.pattern_engine.mode_b.solvers.clo3d_json import (
    generate_5panel_json, _pocket_opening_fracs, _build_front_lines,
    _get_fracs, _compute_line_lengths_mm, INCH_TO_MM,
)
from fdlc.pattern_engine.mode_b.solvers.pattern_utils import DEFAULT_CONSTRUCTION

SAMPLE = {
    "waist": 30.0, "hip": 42.0, "front_rise": 10.75,
    "inseam": 30.0, "outseam": 40.0, "leg_opening": 23.5,
}


@pytest.fixture
def clo_with_pockets(tmp_path):
    path = str(tmp_path / "clo_pockets.json")
    generate_5panel_json(SAMPLE, path, construction=DEFAULT_CONSTRUCTION)
    with open(path) as f:
        return json.load(f)


@pytest.fixture
def clo_without_pockets(tmp_path):
    path = str(tmp_path / "clo_no_pockets.json")
    c = {**DEFAULT_CONSTRUCTION, "pocket_type": None}
    generate_5panel_json(SAMPLE, path, construction=c)
    with open(path) as f:
        return json.load(f)


@pytest.fixture
def clo_legacy(tmp_path):
    """No construction arg — legacy behavior (no pockets)."""
    path = str(tmp_path / "clo_legacy.json")
    generate_5panel_json(SAMPLE, path)
    with open(path) as f:
        return json.load(f)


# ── Pattern pieces ────────────────────────────────────────────────────────

class TestPocketPatterns:
    def test_has_10_patterns(self, clo_with_pockets):
        assert len(clo_with_pockets["PatternList"]) == 10

    def test_pocket_pattern_names(self, clo_with_pockets):
        names = {p["Name"] for p in clo_with_pockets["PatternList"]}
        assert "Pocket_Facing_L" in names
        assert "Pocket_Bag_L" in names
        assert "Pocket_Facing_R" in names
        assert "Pocket_Bag_R" in names

    def test_pocket_pieces_are_closed(self, clo_with_pockets):
        for p in clo_with_pockets["PatternList"]:
            if "Pocket" in p["Name"]:
                assert p["IsClosed"] is True

    def test_pocket_pieces_have_4_lines(self, clo_with_pockets):
        """Pocket rectangles: 4 lines (bottom, right, top, left)."""
        for p in clo_with_pockets["PatternList"]:
            if "Pocket" in p["Name"]:
                assert len(p["ShapeInfo"]["LineList"]) == 4, \
                    f"{p['Name']} has {len(p['ShapeInfo']['LineList'])} lines (expected 4)"

    def test_pocket_pieces_all_straight(self, clo_with_pockets):
        for p in clo_with_pockets["PatternList"]:
            if "Pocket" in p["Name"]:
                for line in p["ShapeInfo"]["LineList"]:
                    for pt in line["PointList"]:
                        assert pt["PointType"] == "Straight"

    def test_pocket_pieces_unique_ids(self, clo_with_pockets):
        ids = [p["ID"] for p in clo_with_pockets["PatternList"]]
        assert len(ids) == len(set(ids))

    def test_lr_facing_different_ids(self, clo_with_pockets):
        fl = next(p for p in clo_with_pockets["PatternList"] if p["Name"] == "Pocket_Facing_L")
        fr = next(p for p in clo_with_pockets["PatternList"] if p["Name"] == "Pocket_Facing_R")
        assert fl["ID"] != fr["ID"]

    def test_lr_bag_different_ids(self, clo_with_pockets):
        bl = next(p for p in clo_with_pockets["PatternList"] if p["Name"] == "Pocket_Bag_L")
        br = next(p for p in clo_with_pockets["PatternList"] if p["Name"] == "Pocket_Bag_R")
        assert bl["ID"] != br["ID"]


# ── Seam structure ────────────────────────────────────────────────────────

class TestPocketSeams:
    def test_seam_count_with_pockets(self, clo_with_pockets):
        """28 seams: 20 base (split side adds extra) + 2 FL/FR-to-facing + 4 facing-to-bag."""
        seams = clo_with_pockets["SeamLinePairGroupList"]
        assert len(seams) == 28, f"Expected 28 seams, got {len(seams)}"

    def test_pocket_seam_names(self, clo_with_pockets):
        names = {s["Name"] for s in clo_with_pockets["SeamLinePairGroupList"]}
        expected = {
            "pocket_FL_to_facing",
            "pocket_FR_to_facing",
            "pocket_facing_to_bag_top_L",
            "pocket_facing_to_bag_bot_L",
            "pocket_facing_to_bag_top_R",
            "pocket_facing_to_bag_bot_R",
        }
        assert expected.issubset(names), f"Missing pocket seams: {expected - names}"

    def test_all_seam_fracs_valid(self, clo_with_pockets):
        for s in clo_with_pockets["SeamLinePairGroupList"]:
            for pair in s["PairList"]:
                for side in ["First", "Second"]:
                    lp = pair[side]["LengthParam"]
                    assert 0.0 <= lp["fStart"] <= 1.0, f"{s['Name']} {side} fStart={lp['fStart']}"
                    assert 0.0 <= lp["fEnd"] <= 1.0, f"{s['Name']} {side} fEnd={lp['fEnd']}"

    def test_no_zero_length_seams(self, clo_with_pockets):
        for s in clo_with_pockets["SeamLinePairGroupList"]:
            for pair in s["PairList"]:
                for side in ["First", "Second"]:
                    lp = pair[side]["LengthParam"]
                    assert abs(lp["fStart"] - lp["fEnd"]) > 0.001, \
                        f"{s['Name']} {side} is zero-length"

    def test_seam_references_valid_patterns(self, clo_with_pockets):
        pat_ids = {p["ID"] for p in clo_with_pockets["PatternList"]}
        for s in clo_with_pockets["SeamLinePairGroupList"]:
            for pair in s["PairList"]:
                assert pair["First"]["ShapeID"] in pat_ids, f"{s['Name']} First refs unknown pattern"
                assert pair["Second"]["ShapeID"] in pat_ids, f"{s['Name']} Second refs unknown pattern"


# ── Edge overlap — the critical CLO3D constraint ─────────────────────────

class TestNoEdgeOverlap:
    def test_no_edge_overlap_with_pockets(self, clo_with_pockets):
        """If any edge is referenced in 2+ seams, CLO3D rejects ALL seams."""
        edge_refs = {}
        for s in clo_with_pockets["SeamLinePairGroupList"]:
            for pair in s["PairList"]:
                for side in ["First", "Second"]:
                    shape = pair[side]["ShapeID"]
                    lp = pair[side]["LengthParam"]
                    key = (shape, round(lp["fStart"], 4), round(lp["fEnd"], 4))
                    assert key not in edge_refs, \
                        f"OVERLAP: {s['Name']} vs {edge_refs.get(key)} on {key}"
                    edge_refs[key] = s["Name"]


# ── Side seam splitting ──────────────────────────────────────────────────

class TestSideSeamSplit:
    def test_side_top_split_into_above_below(self, clo_with_pockets):
        """With in-seam pocket, side_top should split into above + below (no full side_top)."""
        names = [s["Name"] for s in clo_with_pockets["SeamLinePairGroupList"]]
        assert "side_top_above_L" in names
        assert "side_top_below_L" in names
        assert "side_top_above_R" in names
        assert "side_top_below_R" in names
        # Full side_top_L/R should not exist
        assert "side_top_L" not in names
        assert "side_top_R" not in names

    def test_hip_and_knee_seams_unchanged(self, clo_with_pockets):
        """Pocket is in the waist→hip region; hip→knee and knee→hem should be untouched."""
        names = [s["Name"] for s in clo_with_pockets["SeamLinePairGroupList"]]
        assert "side_hip_knee_L" in names
        assert "side_knee_hem_L" in names

    def test_above_frac_ends_at_pocket_top(self, clo_with_pockets):
        """above segment should end where pocket opening starts."""
        f_lines = _build_front_lines(SAMPLE)
        f_lengths = _compute_line_lengths_mm(f_lines)
        f_fracs = _get_fracs(f_lengths)
        pocket_fracs = _pocket_opening_fracs(SAMPLE, DEFAULT_CONSTRUCTION, f_fracs)
        assert pocket_fracs is not None
        frac_top, _ = pocket_fracs

        # Find side_top_above_L
        above = next(s for s in clo_with_pockets["SeamLinePairGroupList"]
                     if s["Name"] == "side_top_above_L")
        # The front panel (Second) fEnd should be at frac_top
        front_id = next(p["ID"] for p in clo_with_pockets["PatternList"]
                       if p["Name"] == "Front_Left")
        for pair in above["PairList"]:
            for side_key in ["First", "Second"]:
                if pair[side_key]["ShapeID"] == front_id:
                    actual_end = pair[side_key]["LengthParam"]["fEnd"]
                    assert abs(actual_end - frac_top) < 0.001, \
                        f"above should end at {frac_top}, got {actual_end}"


# ── Backward compatibility ───────────────────────────────────────────────

class TestLegacyBackcompat:
    def test_no_construction_arg_gives_20_seams(self, clo_legacy):
        """Calling without construction= should produce original 20-seam output."""
        assert len(clo_legacy["PatternList"]) == 6
        assert len(clo_legacy["SeamLinePairGroupList"]) == 20

    def test_no_construction_has_no_pocket_pieces(self, clo_legacy):
        names = {p["Name"] for p in clo_legacy["PatternList"]}
        assert not any("Pocket" in n for n in names)

    def test_pocket_type_none_gives_20_seams(self, clo_without_pockets):
        assert len(clo_without_pockets["PatternList"]) == 6
        assert len(clo_without_pockets["SeamLinePairGroupList"]) == 20

    def test_pocket_type_none_has_unsplit_side(self, clo_without_pockets):
        names = [s["Name"] for s in clo_without_pockets["SeamLinePairGroupList"]]
        assert "side_top_L" in names
        assert "side_top_above_L" not in names


# ── Pocket opening fracs ─────────────────────────────────────────────────

class TestPocketOpeningFracs:
    def test_returns_tuple(self):
        f_lines = _build_front_lines(SAMPLE)
        f_fracs = _get_fracs(_compute_line_lengths_mm(f_lines))
        result = _pocket_opening_fracs(SAMPLE, DEFAULT_CONSTRUCTION, f_fracs)
        assert result is not None
        assert len(result) == 2

    def test_fracs_ordered(self):
        f_lines = _build_front_lines(SAMPLE)
        f_fracs = _get_fracs(_compute_line_lengths_mm(f_lines))
        top, bot = _pocket_opening_fracs(SAMPLE, DEFAULT_CONSTRUCTION, f_fracs)
        assert top < bot

    def test_fracs_within_side_seam(self):
        """Opening fracs must be within the side seam range (lines 1-3)."""
        f_lines = _build_front_lines(SAMPLE)
        f_fracs = _get_fracs(_compute_line_lengths_mm(f_lines))
        top, bot = _pocket_opening_fracs(SAMPLE, DEFAULT_CONSTRUCTION, f_fracs)
        assert top >= f_fracs[1], f"Pocket top {top} before side seam start {f_fracs[1]}"
        assert bot <= f_fracs[4], f"Pocket bot {bot} past side seam end {f_fracs[4]}"

    def test_returns_none_without_pocket(self):
        f_lines = _build_front_lines(SAMPLE)
        f_fracs = _get_fracs(_compute_line_lengths_mm(f_lines))
        assert _pocket_opening_fracs(SAMPLE, {"pocket_type": None}, f_fracs) is None

    def test_longer_opening_gives_wider_span(self):
        f_lines = _build_front_lines(SAMPLE)
        f_fracs = _get_fracs(_compute_line_lengths_mm(f_lines))
        c_short = {**DEFAULT_CONSTRUCTION, "in_seam_length": 5.0}
        c_long  = {**DEFAULT_CONSTRUCTION, "in_seam_length": 9.0}
        t_s, b_s = _pocket_opening_fracs(SAMPLE, c_short, f_fracs)
        t_l, b_l = _pocket_opening_fracs(SAMPLE, c_long,  f_fracs)
        assert (b_l - t_l) > (b_s - t_s), "Longer opening should span more"


# ── Multi-size ────────────────────────────────────────────────────────────

class TestPocketMultiSize:
    SIZES = [
        {"waist": 28, "hip": 38, "front_rise": 10.0, "inseam": 30, "outseam": 40, "leg_opening": 20},
        {"waist": 32, "hip": 44, "front_rise": 11.5, "inseam": 31, "outseam": 41.5, "leg_opening": 24},
        {"waist": 36, "hip": 50, "front_rise": 12.0, "inseam": 31.5, "outseam": 42, "leg_opening": 26},
    ]

    @pytest.mark.parametrize("m", SIZES)
    def test_generates_without_error(self, m, tmp_path):
        path = str(tmp_path / f"pocket_{m['waist']}.json")
        generate_5panel_json(m, path, construction=DEFAULT_CONSTRUCTION)
        with open(path) as f:
            d = json.load(f)
        assert len(d["PatternList"]) == 10
        assert len(d["SeamLinePairGroupList"]) == 28

    @pytest.mark.parametrize("m", SIZES)
    def test_no_edge_overlap_across_sizes(self, m, tmp_path):
        path = str(tmp_path / f"overlap_{m['waist']}.json")
        generate_5panel_json(m, path, construction=DEFAULT_CONSTRUCTION)
        with open(path) as f:
            d = json.load(f)
        refs = {}
        for s in d["SeamLinePairGroupList"]:
            for pair in s["PairList"]:
                for side in ["First", "Second"]:
                    lp = pair[side]["LengthParam"]
                    key = (pair[side]["ShapeID"], round(lp["fStart"], 4), round(lp["fEnd"], 4))
                    assert key not in refs, f"Size {m['waist']}: overlap {s['Name']} vs {refs.get(key)}"
                    refs[key] = s["Name"]
