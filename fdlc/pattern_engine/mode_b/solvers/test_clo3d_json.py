#!/usr/bin/env python3
"""Tests for CLO3D JSON generator.
Run: cd ~/base/mare-pipeline && python3 -m pytest fdlc/pattern_engine/mode_b/solvers/test_clo3d_json.py -v
"""

import json
import math
import os
import pytest
from fdlc.pattern_engine.mode_b.solvers.clo3d_json import (
    generate_clo3d_json, _uid, _ic, _build_front_lines, _build_back_lines,
    _compute_line_lengths_mm, _get_fracs, _ensure_shared_points,
    _cbez_line, _straight_line, _build_seams,
)

SAMPLE = {
    "waist": 30.0, "hip": 52.0, "front_rise": 12.75,
    "inseam": 28.5, "outseam": 40.5, "leg_opening": 23.5,
}


@pytest.fixture
def output_path(tmp_path):
    return str(tmp_path / "test_clo.json")


@pytest.fixture
def generated(output_path):
    generate_clo3d_json(SAMPLE, output_path)
    with open(output_path) as f:
        return json.load(f)


# ── JSON Structure ────────────────────────────────────────────────────────

class TestJSONStructure:
    def test_generates_file(self, output_path):
        generate_clo3d_json(SAMPLE, output_path)
        assert os.path.exists(output_path)
        assert os.path.getsize(output_path) > 1000

    def test_valid_json(self, generated):
        assert isinstance(generated, dict)

    def test_top_level_keys(self, generated):
        required = ["FabricList", "Unit", "PatternList", "SeamLinePairGroupList",
                     "SymmetricDataList", "InstanceDataList"]
        for key in required:
            assert key in generated, "Missing key: " + key

    def test_unit_is_mm(self, generated):
        assert generated["Unit"] == "mm"

    def test_has_fabric(self, generated):
        assert len(generated["FabricList"]) >= 1
        assert "FabricUUID" in generated["FabricList"][0]


# ── Patterns ──────────────────────────────────────────────────────────────

class TestPatterns:
    def test_pattern_count(self, generated):
        assert len(generated["PatternList"]) == 2

    def test_pattern_names(self, generated):
        names = [p["Name"] for p in generated["PatternList"]]
        assert "Front_Panel" in names
        assert "Back_Panel" in names

    def test_patterns_have_unique_ids(self, generated):
        ids = [p["ID"] for p in generated["PatternList"]]
        assert len(ids) == len(set(ids))

    def test_patterns_are_closed(self, generated):
        for p in generated["PatternList"]:
            assert p["IsClosed"] is True

    def test_patterns_have_lines(self, generated):
        for p in generated["PatternList"]:
            lines = p["ShapeInfo"]["LineList"]
            assert len(lines) >= 9

    def test_front_has_12_lines(self, generated):
        front = next(p for p in generated["PatternList"] if p["Name"] == "Front_Panel")
        assert len(front["ShapeInfo"]["LineList"]) == 12

    def test_back_has_9_lines(self, generated):
        back = next(p for p in generated["PatternList"] if p["Name"] == "Back_Panel")
        assert len(back["ShapeInfo"]["LineList"]) == 9

    def test_fabric_uuid_matches(self, generated):
        fab_uuid = generated["FabricList"][0]["FabricUUID"]
        for p in generated["PatternList"]:
            assert p["CurrentFabricUUID"] == fab_uuid


# ── Line Geometry ─────────────────────────────────────────────────────────

class TestLineGeometry:
    def test_shared_points_between_lines(self, generated):
        """Consecutive lines must share endpoint/startpoint IDs."""
        for p in generated["PatternList"]:
            lines = p["ShapeInfo"]["LineList"]
            for i in range(len(lines) - 1):
                last_id = lines[i]["PointList"][-1]["ID"]
                first_id = lines[i + 1]["PointList"][0]["ID"]
                assert last_id == first_id, \
                    p["Name"] + " line " + str(i) + " end != line " + str(i+1) + " start"

    def test_closing_point_matches(self, generated):
        """First point of first line must match last point of last line (closed polygon)."""
        for p in generated["PatternList"]:
            lines = p["ShapeInfo"]["LineList"]
            first_id = lines[0]["PointList"][0]["ID"]
            last_id = lines[-1]["PointList"][-1]["ID"]
            assert first_id == last_id, p["Name"] + " not closed"

    def test_bezier_lines_have_4_points(self, generated):
        for p in generated["PatternList"]:
            for line in p["ShapeInfo"]["LineList"]:
                pts = line["PointList"]
                types = [pt["PointType"] for pt in pts]
                if "Bezier Curve" in types:
                    assert len(pts) == 4, "Bezier line should have 4 points"

    def test_straight_lines_have_2_points(self, generated):
        for p in generated["PatternList"]:
            for line in p["ShapeInfo"]["LineList"]:
                pts = line["PointList"]
                types = [pt["PointType"] for pt in pts]
                if "Bezier Curve" not in types:
                    assert len(pts) == 2, "Straight line should have 2 points"

    def test_point_types_valid(self, generated):
        valid = {"Straight", "Bezier Curve"}
        for p in generated["PatternList"]:
            for line in p["ShapeInfo"]["LineList"]:
                for pt in line["PointList"]:
                    assert pt["PointType"] in valid


# ── Seams ─────────────────────────────────────────────────────────────────

class TestSeams:
    def test_seam_count(self, generated):
        """Should have 8 seam groups for 2-panel version."""
        assert len(generated["SeamLinePairGroupList"]) == 8

    def test_seam_names(self, generated):
        names = [s["Name"] for s in generated["SeamLinePairGroupList"]]
        expected = ["side_top", "side_hip_knee", "side_knee_hem",
                     "inseam_straight", "inseam_curve", "crotch",
                     "waist", "center_seam"]
        for e in expected:
            assert e in names, "Missing seam: " + e

    def test_seam_references_valid_patterns(self, generated):
        pattern_ids = {p["ID"] for p in generated["PatternList"]}
        for s in generated["SeamLinePairGroupList"]:
            for pair in s["PairList"]:
                assert pair["First"]["ShapeID"] in pattern_ids, \
                    s["Name"] + " First references unknown pattern"
                assert pair["Second"]["ShapeID"] in pattern_ids, \
                    s["Name"] + " Second references unknown pattern"

    def test_seam_fractions_in_range(self, generated):
        for s in generated["SeamLinePairGroupList"]:
            for pair in s["PairList"]:
                for side in ["First", "Second"]:
                    lp = pair[side]["LengthParam"]
                    assert 0.0 <= lp["fStart"] <= 1.0, \
                        s["Name"] + " " + side + " fStart out of range"
                    assert 0.0 <= lp["fEnd"] <= 1.0, \
                        s["Name"] + " " + side + " fEnd out of range"

    def test_seam_fractions_not_zero_length(self, generated):
        for s in generated["SeamLinePairGroupList"]:
            for pair in s["PairList"]:
                for side in ["First", "Second"]:
                    lp = pair[side]["LengthParam"]
                    assert abs(lp["fStart"] - lp["fEnd"]) > 0.01, \
                        s["Name"] + " " + side + " is zero-length seam"

    def test_no_edge_overlap(self, generated):
        """No pattern edge should be referenced in two different seam groups.
        This causes CLO3D to reject all seams."""
        edge_refs = {}
        for s in generated["SeamLinePairGroupList"]:
            for pair in s["PairList"]:
                for side in ["First", "Second"]:
                    shape = pair[side]["ShapeID"]
                    lp = pair[side]["LengthParam"]
                    key = (shape, round(lp["fStart"], 4), round(lp["fEnd"], 4))
                    if key in edge_refs:
                        pytest.fail(
                            s["Name"] + " overlaps with " + edge_refs[key] +
                            " on edge " + str(key)
                        )
                    edge_refs[key] = s["Name"]

    def test_seam_has_fold_data(self, generated):
        for s in generated["SeamLinePairGroupList"]:
            assert "FoldData" in s
            assert s["FoldData"]["iAngle"] == 180


# ── Coordinate System ─────────────────────────────────────────────────────

class TestCoordinates:
    def test_inch_to_clo_conversion(self):
        x, y = _ic(1.0, 1.0)
        assert x == pytest.approx(25.4, abs=0.1)
        assert y == pytest.approx(-25.4, abs=0.1)

    def test_y_is_flipped(self):
        """CLO3D uses Y-up, our solver uses Y-down."""
        x, y = _ic(0, 10.0)
        assert y < 0  # positive inches Y-down → negative mm Y-up


# ── Multi-Size ────────────────────────────────────────────────────────────

class TestMultiSize:
    def test_different_sizes_generate(self, tmp_path):
        for waist, hip in [(28, 48), (32, 54), (36, 58)]:
            m = dict(SAMPLE)
            m["waist"] = waist
            m["hip"] = hip
            path = str(tmp_path / ("test_" + str(waist) + ".json"))
            generate_clo3d_json(m, path)
            with open(path) as f:
                data = json.load(f)
            assert len(data["PatternList"]) == 2
            assert len(data["SeamLinePairGroupList"]) == 8

    def test_different_silhouettes(self, tmp_path):
        for lo in [14.0, 18.0, 23.5, 28.0]:
            m = dict(SAMPLE)
            m["leg_opening"] = lo
            path = str(tmp_path / ("test_lo" + str(int(lo)) + ".json"))
            generate_clo3d_json(m, path)
            with open(path) as f:
                data = json.load(f)
            assert len(data["PatternList"]) == 2
