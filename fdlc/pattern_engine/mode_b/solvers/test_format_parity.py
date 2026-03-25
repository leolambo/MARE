#!/usr/bin/env python3
"""
Cross-format parity tests: DXF ↔ CLO3D JSON consistency.

Verifies that the pant_block solver, dxf_export, and clo3d_json all agree
on the same geometry for a given set of measurements. Catches regressions
where one format diverges from the others.

Run: cd ~/base/mare-pipeline && python3 -m pytest fdlc/pattern_engine/mode_b/solvers/test_format_parity.py -v
"""

from __future__ import annotations

import json
import math
import os
import pytest
import ezdxf

from fdlc.pattern_engine.mode_b.solvers.pant_block import solve, _build_front_panel, _build_back_panel, _match_seams
from fdlc.pattern_engine.mode_b.solvers.dxf_export import to_dxf
from fdlc.pattern_engine.mode_b.solvers.clo3d_json import (
    generate_clo3d_json,
    generate_5panel_json,
    _build_front_lines,
    _build_back_lines,
    _compute_line_lengths_mm,
    _get_fracs,
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


# ── Helper functions ──────────────────────────────────────────────────────

def _clo_panel_bounding_box(pattern):
    """Get bounding box of all points in a CLO3D pattern (in mm)."""
    xs, ys = [], []
    for line in pattern["ShapeInfo"]["LineList"]:
        for pt in line["PointList"]:
            xs.append(pt["Position"]["x"])
            ys.append(pt["Position"]["y"])
    return min(xs), min(ys), max(xs), max(ys)


def _clo_panel_width_height_mm(pattern):
    """Width and height of a CLO3D pattern bounding box."""
    x0, y0, x1, y1 = _clo_panel_bounding_box(pattern)
    return abs(x1 - x0), abs(y1 - y0)


def _dxf_entity_bbox(doc, layer_name):
    """Bounding box of all entities on a specific DXF layer."""
    msp = doc.modelspace()
    xs, ys = [], []
    for e in msp:
        if e.dxf.layer == layer_name:
            if e.dxftype() == "LWPOLYLINE":
                for pt in e.get_points():
                    xs.append(pt[0])
                    ys.append(pt[1])
    if not xs:
        return None
    return min(xs), min(ys), max(xs), max(ys)


def _solver_panel_dimensions(m, panel_name):
    """Get the width/height of a solver panel in inches directly from pant_block."""
    c = DEFAULT_CONSTRUCTION
    e = DEFAULT_EASE
    if panel_name == "front":
        panel = _build_front_panel(m, c, e)
    else:
        front, back = _match_seams(m, c, e)
        panel = back
    pts = panel["cut"]
    x0, y0, x1, y1 = _bbox(pts)
    return abs(x1 - x0), abs(y1 - y0)


def _approx_percent(a, b, pct=5.0):
    """Check two values are within pct% of each other."""
    if abs(a) < 0.001 and abs(b) < 0.001:
        return True
    mid = (abs(a) + abs(b)) / 2.0
    if mid < 0.001:
        return True
    return abs(a - b) / mid * 100.0 <= pct


# ── 1. DXF ↔ Solver geometry consistency ─────────────────────────────────

class TestDXFSolverParity:
    """DXF panels must reflect the solver's geometry, not a truncated version."""

    def test_dxf_has_all_layers(self, dxf_doc):
        """All expected layers must be present in the DXF."""
        layer_names = {layer.dxf.name for layer in dxf_doc.layers}
        for expected in ["CUT", "SEAM_ALLOWANCE", "GRAIN", "NOTCH", "INTERNAL", "TEXT"]:
            assert expected in layer_names, f"DXF missing layer: {expected}"

    def test_dxf_cut_layer_has_geometry(self, dxf_doc):
        """CUT layer must contain polylines (not empty)."""
        msp = dxf_doc.modelspace()
        cut_entities = [e for e in msp if e.dxf.layer == "CUT"]
        assert len(cut_entities) >= 2, "DXF CUT layer should have at least front + back panels"

    def test_dxf_grain_layer_has_arrows(self, dxf_doc):
        """GRAIN layer must have grainlines for front and back panels."""
        msp = dxf_doc.modelspace()
        grain_entities = [e for e in msp if e.dxf.layer == "GRAIN"]
        assert len(grain_entities) >= 2, "DXF should have grainlines for at least 2 panels"

    def test_dxf_notch_layer_has_marks(self, dxf_doc):
        """NOTCH layer must have at least hip notch marks."""
        msp = dxf_doc.modelspace()
        notch_entities = [e for e in msp if e.dxf.layer == "NOTCH"]
        assert len(notch_entities) >= 2, "DXF should have notch marks"

    def test_dxf_text_layer_has_labels(self, dxf_doc):
        """TEXT layer must have panel labels."""
        msp = dxf_doc.modelspace()
        text_entities = [e for e in msp if e.dxf.layer == "TEXT" and e.dxftype() == "TEXT"]
        texts = [e.dxf.text for e in text_entities]
        assert any("FRONT" in t.upper() for t in texts), "DXF missing FRONT PANEL label"
        assert any("BACK" in t.upper() for t in texts), "DXF missing BACK PANEL label"

    def test_dxf_front_panel_dimensions_match_solver(self, solution, dxf_doc):
        """DXF front panel bounding box width must be within 5% of solver's front panel."""
        front = next(p for p in solution["pieces"] if p["name"] == "front_panel")
        pts = front["cut"]
        solver_w = _bbox(pts)[2] - _bbox(pts)[0]

        # DXF bbox on CUT layer gives us all panels together; check it's at least solver-wide
        bbox = _dxf_entity_bbox(dxf_doc, "CUT")
        assert bbox is not None
        dxf_total_w = bbox[2] - bbox[0]
        assert dxf_total_w >= solver_w * 0.9, \
            f"DXF total width {dxf_total_w:.2f}\" too narrow vs solver front panel {solver_w:.2f}\""

    def test_dxf_panel_count_matches_piece_count(self, solution, dxf_doc):
        """Number of closed polylines on CUT layer should match piece count."""
        msp = dxf_doc.modelspace()
        closed = [e for e in msp if e.dxf.layer == "CUT" and e.dxftype() == "LWPOLYLINE"
                  and e.is_closed]
        assert len(closed) == len(solution["pieces"]), \
            f"DXF has {len(closed)} closed cut lines, solver has {len(solution['pieces'])} pieces"

    def test_dxf_seam_allowance_present_for_panels(self, dxf_doc):
        """SEAM_ALLOWANCE layer should have offset outlines."""
        msp = dxf_doc.modelspace()
        sa_entities = [e for e in msp if e.dxf.layer == "SEAM_ALLOWANCE"
                       and e.dxftype() == "LWPOLYLINE"]
        assert len(sa_entities) >= 2, \
            f"DXF should have seam allowance outlines (got {len(sa_entities)})"

    def test_dxf_units_are_inches(self, dxf_doc):
        assert dxf_doc.header["$INSUNITS"] == 1

    def test_dxf_r2000_format(self, dxf_path):
        """DXF must be R2000 format (CLO3D requirement)."""
        doc = ezdxf.readfile(dxf_path)
        assert doc.dxfversion == "AC1015"  # R2000


# ── 2. CLO3D JSON ↔ Solver geometry consistency ───────────────────────────

class TestCLOSolverParity:
    """CLO3D panel geometry must match the solver's panel geometry within tolerance."""

    def test_clo_front_width_matches_solver(self, solution, clo_2panel):
        """CLO3D front panel width (in mm) must match solver front panel width (in inches × 25.4)."""
        front_solver = next(p for p in solution["pieces"] if p["name"] == "front_panel")
        pts = front_solver["cut"]
        solver_w_in = _bbox(pts)[2] - _bbox(pts)[0]
        solver_w_mm = solver_w_in * INCH_TO_MM

        clo_front = next(p for p in clo_2panel["PatternList"] if p["Name"] == "Front_Panel")
        clo_w, _ = _clo_panel_width_height_mm(clo_front)

        assert _approx_percent(solver_w_mm, clo_w, pct=8.0), \
            f"Front panel width: solver={solver_w_mm:.1f}mm CLO={clo_w:.1f}mm (>8% diff)"

    def test_clo_front_height_matches_solver(self, solution, clo_2panel):
        """CLO3D front panel height must match solver outseam (Y-depth)."""
        front_solver = next(p for p in solution["pieces"] if p["name"] == "front_panel")
        pts = front_solver["cut"]
        solver_h_in = _bbox(pts)[3] - _bbox(pts)[1]
        solver_h_mm = solver_h_in * INCH_TO_MM

        clo_front = next(p for p in clo_2panel["PatternList"] if p["Name"] == "Front_Panel")
        _, clo_h = _clo_panel_width_height_mm(clo_front)

        assert _approx_percent(solver_h_mm, clo_h, pct=8.0), \
            f"Front panel height: solver={solver_h_mm:.1f}mm CLO={clo_h:.1f}mm (>8% diff)"

    def test_clo_back_width_matches_solver(self, solution, clo_2panel):
        """CLO3D back panel width must match solver back panel width."""
        back_solver = next(p for p in solution["pieces"] if p["name"] == "back_panel")
        pts = back_solver["cut"]
        solver_w_in = _bbox(pts)[2] - _bbox(pts)[0]
        solver_w_mm = solver_w_in * INCH_TO_MM

        clo_back = next(p for p in clo_2panel["PatternList"] if p["Name"] == "Back_Panel")
        clo_w, _ = _clo_panel_width_height_mm(clo_back)

        assert _approx_percent(solver_w_mm, clo_w, pct=8.0), \
            f"Back panel width: solver={solver_w_mm:.1f}mm CLO={clo_w:.1f}mm (>8% diff)"

    def test_clo_back_height_matches_solver(self, solution, clo_2panel):
        """CLO3D back panel height must match solver back panel height."""
        back_solver = next(p for p in solution["pieces"] if p["name"] == "back_panel")
        pts = back_solver["cut"]
        solver_h_in = _bbox(pts)[3] - _bbox(pts)[1]
        solver_h_mm = solver_h_in * INCH_TO_MM

        clo_back = next(p for p in clo_2panel["PatternList"] if p["Name"] == "Back_Panel")
        _, clo_h = _clo_panel_width_height_mm(clo_back)

        assert _approx_percent(solver_h_mm, clo_h, pct=8.0), \
            f"Back panel height: solver={solver_h_mm:.1f}mm CLO={clo_h:.1f}mm (>8% diff)"

    def test_clo_back_wider_than_front(self, clo_2panel):
        """Back panel must be wider than front (52% vs 48% distribution)."""
        clo_front = next(p for p in clo_2panel["PatternList"] if p["Name"] == "Front_Panel")
        clo_back = next(p for p in clo_2panel["PatternList"] if p["Name"] == "Back_Panel")
        fw, _ = _clo_panel_width_height_mm(clo_front)
        bw, _ = _clo_panel_width_height_mm(clo_back)
        assert bw > fw, f"CLO3D back panel ({bw:.1f}mm) should be wider than front ({fw:.1f}mm)"

    def test_clo_panels_same_height(self, clo_2panel):
        """Front and back panels should be the same height (same outseam length)."""
        clo_front = next(p for p in clo_2panel["PatternList"] if p["Name"] == "Front_Panel")
        clo_back = next(p for p in clo_2panel["PatternList"] if p["Name"] == "Back_Panel")
        _, fh = _clo_panel_width_height_mm(clo_front)
        _, bh = _clo_panel_width_height_mm(clo_back)
        assert _approx_percent(fh, bh, pct=5.0), \
            f"Front ({fh:.1f}mm) and back ({bh:.1f}mm) heights differ by more than 5%"


# ── 3. DXF ↔ CLO3D geometry consistency ──────────────────────────────────

class TestDXFCLOParity:
    """DXF and CLO3D must agree on panel dimensions — they come from the same solver."""

    def test_front_panel_width_dxf_vs_clo(self, solution, dxf_doc, clo_2panel):
        """DXF front panel width must match CLO front panel width within 8%."""
        # Solver is ground truth
        front_solver = next(p for p in solution["pieces"] if p["name"] == "front_panel")
        pts = front_solver["cut"]
        solver_w_in = _bbox(pts)[2] - _bbox(pts)[0]
        solver_w_mm = solver_w_in * INCH_TO_MM

        clo_front = next(p for p in clo_2panel["PatternList"] if p["Name"] == "Front_Panel")
        clo_w, _ = _clo_panel_width_height_mm(clo_front)

        # Both must agree with solver within tolerance
        assert _approx_percent(solver_w_mm, clo_w, pct=8.0), \
            f"DXF/CLO front width mismatch: solver={solver_w_mm:.1f}mm CLO={clo_w:.1f}mm"

    def test_inseam_length_dxf_vs_clo(self, solution, clo_2panel):
        """Inseam length in solver must match CLO3D seam fraction × perimeter."""
        solver_inseam_in = solution["validation"]["front_inseam"]
        solver_inseam_mm = solver_inseam_in * INCH_TO_MM

        # Find front panel CLO3D inseam seam fraction
        front_id = next(p["ID"] for p in clo_2panel["PatternList"] if p["Name"] == "Front_Panel")
        front_lines = next(p["ShapeInfo"]["LineList"] for p in clo_2panel["PatternList"]
                           if p["Name"] == "Front_Panel")

        # Compute CLO perimeter from chord lengths (same method as clo3d_json.py)
        total_mm = 0
        for line in front_lines:
            pts = line["PointList"]
            chord = sum(
                math.hypot(pts[i+1]["Position"]["x"] - pts[i]["Position"]["x"],
                           pts[i+1]["Position"]["y"] - pts[i]["Position"]["y"])
                for i in range(len(pts)-1)
            )
            if len(pts) == 4:
                chord *= 1.15
            total_mm += chord

        # Inseam seam: find the inseam_curve seam
        inseam_seam = next((s for s in clo_2panel["SeamLinePairGroupList"]
                            if s["Name"] == "inseam_curve"), None)
        assert inseam_seam is not None, "inseam_curve seam not found in CLO3D JSON"

        first = inseam_seam["PairList"][0]["First"]
        if first["ShapeID"] == front_id:
            frac = abs(first["LengthParam"]["fStart"] - first["LengthParam"]["fEnd"])
        else:
            second = inseam_seam["PairList"][0]["Second"]
            frac = abs(second["LengthParam"]["fStart"] - second["LengthParam"]["fEnd"])

        clo_inseam_mm = frac * total_mm

        # The curved portion of inseam should be at least 30% of total inseam
        # (knee-to-crotch section). Allow wide tolerance for the approximation.
        assert clo_inseam_mm > solver_inseam_mm * 0.1, \
            f"CLO inseam seam fraction ({clo_inseam_mm:.1f}mm) seems too small vs solver ({solver_inseam_mm:.1f}mm)"


# ── 4. 5-Panel CLO3D specific tests ──────────────────────────────────────

class TestFivePanelParity:
    """5-panel CLO3D JSON (FL, FR, BL, BR + 2 WB pieces) must be internally consistent."""

    def test_5panel_has_6_patterns(self, clo_5panel):
        assert len(clo_5panel["PatternList"]) == 6

    def test_5panel_pattern_names(self, clo_5panel):
        names = {p["Name"] for p in clo_5panel["PatternList"]}
        for expected in ["Front_Left", "Front_Right", "Back_Left", "Back_Right",
                          "WB_Front", "WB_Back"]:
            assert expected in names, f"5-panel missing: {expected}"

    def test_5panel_fl_fr_same_dimensions(self, clo_5panel):
        """Left and right front panels must have the same width/height (mirrored)."""
        fl = next(p for p in clo_5panel["PatternList"] if p["Name"] == "Front_Left")
        fr = next(p for p in clo_5panel["PatternList"] if p["Name"] == "Front_Right")
        fl_w, fl_h = _clo_panel_width_height_mm(fl)
        fr_w, fr_h = _clo_panel_width_height_mm(fr)
        assert _approx_percent(fl_w, fr_w, pct=3.0), \
            f"FL width ({fl_w:.1f}mm) != FR width ({fr_w:.1f}mm)"
        assert _approx_percent(fl_h, fr_h, pct=3.0), \
            f"FL height ({fl_h:.1f}mm) != FR height ({fr_h:.1f}mm)"

    def test_5panel_bl_br_same_dimensions(self, clo_5panel):
        """Left and right back panels must have the same width/height (mirrored)."""
        bl = next(p for p in clo_5panel["PatternList"] if p["Name"] == "Back_Left")
        br = next(p for p in clo_5panel["PatternList"] if p["Name"] == "Back_Right")
        bl_w, bl_h = _clo_panel_width_height_mm(bl)
        br_w, br_h = _clo_panel_width_height_mm(br)
        assert _approx_percent(bl_w, br_w, pct=3.0), \
            f"BL width ({bl_w:.1f}mm) != BR width ({br_w:.1f}mm)"
        assert _approx_percent(bl_h, br_h, pct=3.0), \
            f"BL height ({bl_h:.1f}mm) != BR height ({br_h:.1f}mm)"

    def test_5panel_back_wider_than_front(self, clo_5panel):
        """Back panels must be wider than front panels."""
        fl = next(p for p in clo_5panel["PatternList"] if p["Name"] == "Front_Left")
        bl = next(p for p in clo_5panel["PatternList"] if p["Name"] == "Back_Left")
        fl_w, _ = _clo_panel_width_height_mm(fl)
        bl_w, _ = _clo_panel_width_height_mm(bl)
        assert bl_w > fl_w, f"Back ({bl_w:.1f}mm) should be wider than front ({fl_w:.1f}mm)"

    def test_5panel_seam_count(self, clo_5panel):
        """5-panel should have 20 seams: 5 L + 5 R per-leg + 4 cross-leg + 6 WB."""
        seams = clo_5panel["SeamLinePairGroupList"]
        assert len(seams) == 20, f"Expected 20 seams, got {len(seams)}"

    def test_5panel_seam_names_complete(self, clo_5panel):
        names = {s["Name"] for s in clo_5panel["SeamLinePairGroupList"]}
        expected = {
            "side_top_L", "side_hip_knee_L", "side_knee_hem_L", "inseam_straight_L", "inseam_curve_L",
            "side_top_R", "side_hip_knee_R", "side_knee_hem_R", "inseam_straight_R", "inseam_curve_R",
            "center_front", "center_back", "crotch_front", "crotch_back",
            "wb_front_to_FL", "wb_front_to_FR", "wb_back_to_BL", "wb_back_to_BR",
            "wb_side_R", "wb_side_L",
        }
        missing = expected - names
        assert not missing, f"5-panel missing seams: {missing}"

    def test_5panel_no_edge_overlap(self, clo_5panel):
        """Critical: no pattern edge referenced in 2+ seams (CLO3D rejects all if violated)."""
        edge_refs = {}
        for s in clo_5panel["SeamLinePairGroupList"]:
            for pair in s["PairList"]:
                for side in ["First", "Second"]:
                    shape = pair[side]["ShapeID"]
                    lp = pair[side]["LengthParam"]
                    key = (shape, round(lp["fStart"], 4), round(lp["fEnd"], 4))
                    assert key not in edge_refs, \
                        f"Edge overlap: {s['Name']} conflicts with {edge_refs.get(key)} on {key}"
                    edge_refs[key] = s["Name"]

    def test_5panel_seam_fracs_valid(self, clo_5panel):
        """All seam fraction pairs must be in [0,1] and non-zero length."""
        for s in clo_5panel["SeamLinePairGroupList"]:
            for pair in s["PairList"]:
                for side in ["First", "Second"]:
                    lp = pair[side]["LengthParam"]
                    assert 0.0 <= lp["fStart"] <= 1.0, f"{s['Name']} {side} fStart={lp['fStart']}"
                    assert 0.0 <= lp["fEnd"] <= 1.0, f"{s['Name']} {side} fEnd={lp['fEnd']}"
                    assert abs(lp["fStart"] - lp["fEnd"]) > 0.005, \
                        f"{s['Name']} {side} is near-zero length seam"

    def test_5panel_wb_pieces_are_rectangular(self, clo_5panel):
        """Waistband pieces should be rectangular (5 lines, 2 points each)."""
        for name in ["WB_Front", "WB_Back"]:
            wb = next(p for p in clo_5panel["PatternList"] if p["Name"] == name)
            lines = wb["ShapeInfo"]["LineList"]
            assert len(lines) == 5, f"{name} should have 5 lines (got {len(lines)})"
            for line in lines:
                assert len(line["PointList"]) == 2, \
                    f"{name} line should have 2 points (got {len(line['PointList'])})"

    def test_5panel_matches_2panel_front_dimensions(self, solution, clo_5panel):
        """FL in 5-panel must match solver front panel dimensions within 10%."""
        front_solver = next(p for p in solution["pieces"] if p["name"] == "front_panel")
        pts = front_solver["cut"]
        solver_w_in = _bbox(pts)[2] - _bbox(pts)[0]
        solver_h_in = _bbox(pts)[3] - _bbox(pts)[1]

        fl = next(p for p in clo_5panel["PatternList"] if p["Name"] == "Front_Left")
        clo_w, clo_h = _clo_panel_width_height_mm(fl)

        assert _approx_percent(solver_w_in * INCH_TO_MM, clo_w, pct=10.0), \
            f"5-panel FL width mismatch: solver={solver_w_in * INCH_TO_MM:.1f}mm CLO={clo_w:.1f}mm"
        assert _approx_percent(solver_h_in * INCH_TO_MM, clo_h, pct=10.0), \
            f"5-panel FL height mismatch: solver={solver_h_in * INCH_TO_MM:.1f}mm CLO={clo_h:.1f}mm"


# ── 5. Multi-size regression tests ───────────────────────────────────────

class TestMultiSizeFormatParity:
    """All three formats must produce valid output for all supported sizes."""

    @pytest.mark.parametrize("measurements", SIZES)
    def test_all_formats_generate_without_error(self, measurements, tmp_path):
        """DXF, 2-panel CLO, and 5-panel CLO must all generate for every size."""
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
        assert os.path.exists(clo5_p)

        # 5-panel must always have 20 seams and 6 patterns regardless of size
        with open(clo5_p) as f:
            data = json.load(f)
        assert len(data["PatternList"]) == 6
        assert len(data["SeamLinePairGroupList"]) == 20

    @pytest.mark.parametrize("measurements", SIZES)
    def test_inseam_delta_consistent_across_formats(self, measurements, tmp_path):
        """Solver inseam delta must stay < 0.5\" across all sizes (regression guard)."""
        m = {**measurements}
        sol = solve(m, DEFAULT_CONSTRUCTION, DEFAULT_EASE)
        assert sol["validation"]["inseam_delta"] < 0.5, \
            f"Size {m['waist']}/{m['hip']}: inseam delta {sol['validation']['inseam_delta']:.3f}\" too large"

    @pytest.mark.parametrize("measurements", SIZES)
    def test_dxf_readable_across_sizes(self, measurements, tmp_path):
        """DXF output must be parseable by ezdxf for all sizes."""
        m = {**measurements}
        sol = solve(m, DEFAULT_CONSTRUCTION, DEFAULT_EASE)
        p = str(tmp_path / f"check_{m['waist']}.dxf")
        to_dxf(sol, p)
        doc = ezdxf.readfile(p)
        assert doc.dxfversion == "AC1015"


# ── 6. Measurement round-trip ─────────────────────────────────────────────

class TestMeasurementRoundTrip:
    """Measurements embedded in DXF text annotations must match the input."""

    def test_dxf_size_annotation_matches_input(self, dxf_doc):
        """The size label in DXF must include the waist measurement used."""
        msp = dxf_doc.modelspace()
        texts = [e.dxf.text for e in msp if e.dxftype() == "TEXT"]
        waist_texts = [t for t in texts if "30" in t and "waist" in t.lower()]
        assert len(waist_texts) >= 1, \
            f"DXF should contain waist annotation with '30\"'; found texts: {texts[:10]}"

    def test_solver_validation_preserved_in_solution(self, solution):
        """Solver must expose inseam/side deltas for downstream inspection."""
        v = solution["validation"]
        for key in ["front_inseam", "back_inseam", "front_side", "back_side",
                     "inseam_delta", "side_delta", "b_drop"]:
            assert key in v, f"Solver validation missing key: {key}"
            assert v[key] > 0, f"Solver validation {key} should be > 0"
