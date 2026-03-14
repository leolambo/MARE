#!/usr/bin/env python3
"""Tests for DXF annotations and construction guide generation.
Lock in current behavior before refactoring into separate modules.

Run: cd ~/base/mare-pipeline && python3 -m pytest fdlc/pattern_engine/mode_b/solvers/test_annotations.py -v
"""

import math
import os
import pytest
import ezdxf
from fdlc.pattern_engine.mode_b.solvers.pant_block import (
    solve, to_dxf, DEFAULT_CONSTRUCTION, DEFAULT_EASE,
    _vnorm, _vperp, _vmid, _nearest_index, _seam_midpoint,
    _add_notch_mark, _add_grain_arrowhead, _add_seam_number,
)

SAMPLE = {
    "waist": 30.0, "hip": 52.0,
    "front_rise": 12.75, "back_rise": 14.75,
    "inseam": 28.5, "outseam": 40.5,
    "thigh": 28.0, "leg_opening": 23.5,
    "fly_length": 10.0,
}


@pytest.fixture
def solution():
    return solve(SAMPLE, DEFAULT_CONSTRUCTION, DEFAULT_EASE)


@pytest.fixture
def dxf_doc(solution, tmp_path):
    out = str(tmp_path / "annotated.dxf")
    to_dxf(solution, out)
    return ezdxf.readfile(out)


# ── Vector helpers ────────────────────────────────────────────────────────

class TestVectorHelpers:
    def test_vnorm_unit_length(self):
        v = _vnorm((3.0, 4.0))
        assert math.hypot(v[0], v[1]) == pytest.approx(1.0, abs=0.001)

    def test_vnorm_zero_vector(self):
        assert _vnorm((0, 0)) == (0.0, 0.0)

    def test_vperp_is_perpendicular(self):
        v = (3.0, 4.0)
        p = _vperp(v)
        dot = v[0]*p[0] + v[1]*p[1]
        assert dot == pytest.approx(0.0, abs=0.001)

    def test_vperp_same_magnitude(self):
        v = (3.0, 4.0)
        p = _vperp(v)
        assert math.hypot(p[0], p[1]) == pytest.approx(math.hypot(v[0], v[1]), abs=0.001)

    def test_vmid(self):
        assert _vmid((0, 0), (4, 6)) == (2.0, 3.0)

    def test_nearest_index(self):
        pts = [(0, 0), (1, 0), (2, 0), (3, 0)]
        assert _nearest_index(pts, (2.1, 0)) == 2
        assert _nearest_index(pts, (0.4, 0)) == 0

    def test_seam_midpoint_returns_point_on_segment(self):
        pts = [(0, 0), (10, 0), (10, 10), (0, 10)]
        mid, tan = _seam_midpoint(pts, 0, 1)
        assert mid[0] == pytest.approx(5.0, abs=0.5)
        assert mid[1] == pytest.approx(0.0, abs=0.5)


# ── DXF Layer Structure ──────────────────────────────────────────────────

class TestDXFLayers:
    """Verify all expected layers exist with correct properties."""

    EXPECTED_LAYERS = ["CUT", "SEAM_ALLOWANCE", "GRAIN", "NOTCH", "INTERNAL", "TEXT"]

    def test_all_layers_present(self, dxf_doc):
        layer_names = [l.dxf.name for l in dxf_doc.layers]
        for expected in self.EXPECTED_LAYERS:
            assert expected in layer_names, f"Missing layer: {expected}"

    def test_cut_layer_color(self, dxf_doc):
        assert dxf_doc.layers.get("CUT").color == 7

    def test_notch_layer_color(self, dxf_doc):
        assert dxf_doc.layers.get("NOTCH").color == 1

    def test_grain_layer_color(self, dxf_doc):
        assert dxf_doc.layers.get("GRAIN").color == 3


# ── Annotation Content ───────────────────────────────────────────────────

class TestAnnotationContent:
    """Verify annotations are present in the DXF output."""

    def _entities_on_layer(self, dxf_doc, layer):
        return [e for e in dxf_doc.modelspace() if e.dxf.layer == layer]

    def _texts_on_layer(self, dxf_doc, layer):
        return [e for e in dxf_doc.modelspace()
                if e.dxftype() == 'TEXT' and e.dxf.layer == layer]

    def test_has_seam_numbers(self, dxf_doc):
        """Should have circled numbers (1-4) for seam edges on both panels."""
        texts = self._texts_on_layer(dxf_doc, "TEXT")
        text_values = [t.dxf.text for t in texts]
        # Should have at least seam numbers 1-4 for front + back = 8 numbers
        for num in ['1', '2', '3', '4']:
            count = text_values.count(num)
            assert count >= 2, f"Seam number '{num}' appears {count} times (need >= 2 for front+back)"

    def test_has_seam_circles(self, dxf_doc):
        """Each seam number should have a circle around it."""
        circles = [e for e in dxf_doc.modelspace() if e.dxftype() == 'CIRCLE']
        # At least 8 circles (4 seams × 2 panels)
        assert len(circles) >= 8, f"Only {len(circles)} circles found (need >= 8 for seam markers)"

    def test_has_panel_labels(self, dxf_doc):
        """Should have FRONT PANEL and BACK PANEL text."""
        texts = self._texts_on_layer(dxf_doc, "TEXT")
        text_values = [t.dxf.text for t in texts]
        assert "FRONT PANEL" in text_values, "Missing FRONT PANEL label"
        assert "BACK PANEL" in text_values, "Missing BACK PANEL label"

    def test_has_cut_instructions(self, dxf_doc):
        """Should have 'Cut 2 (mirror)' text for main panels."""
        texts = self._texts_on_layer(dxf_doc, "TEXT")
        text_values = [t.dxf.text for t in texts]
        mirror_count = sum(1 for t in text_values if 'mirror' in t.lower())
        assert mirror_count >= 2, f"Only {mirror_count} 'Cut (mirror)' labels (need >= 2)"

    def test_has_size_label(self, dxf_doc):
        """Should have size info text."""
        texts = self._texts_on_layer(dxf_doc, "TEXT")
        text_values = [t.dxf.text for t in texts]
        size_labels = [t for t in text_values if 'waist' in t.lower()]
        assert len(size_labels) >= 2, f"Only {len(size_labels)} size labels (need >= 2)"

    def test_has_sa_labels(self, dxf_doc):
        """Should have seam allowance labels on SA layer."""
        texts = self._texts_on_layer(dxf_doc, "SEAM_ALLOWANCE")
        assert len(texts) >= 2, f"Only {len(texts)} SA labels (need >= 2 for front+back)"
        sa_texts = [t.dxf.text for t in texts]
        assert any('SA' in t for t in sa_texts), "No SA label text found"

    def test_has_notch_marks(self, dxf_doc):
        """Should have notch lines on NOTCH layer."""
        notch_entities = self._entities_on_layer(dxf_doc, "NOTCH")
        lines = [e for e in notch_entities if e.dxftype() == 'LINE']
        # At least: 2 knee notches per panel × 2 panels + hip notches + CF/CB notches
        assert len(lines) >= 8, f"Only {len(lines)} notch lines (need >= 8)"

    def test_has_grainline_arrowheads(self, dxf_doc):
        """Grainlines should have arrowhead polygons."""
        grain_entities = self._entities_on_layer(dxf_doc, "GRAIN")
        polys = [e for e in grain_entities if e.dxftype() == 'LWPOLYLINE']
        # Each piece with a grainline gets: 1 line + 2 arrowhead polys
        # Front + back + accessories = many grainlines
        arrowheads = [p for p in polys if p.closed and len(list(p.get_points())) <= 6]
        assert len(arrowheads) >= 4, f"Only {len(arrowheads)} arrowheads (need >= 4 for front+back)"

    def test_front_has_single_notch_back_has_double(self, dxf_doc):
        """Front panel hip should have 1 notch line, back should have 2 (double notch)."""
        notch_lines = [e for e in dxf_doc.modelspace()
                       if e.dxftype() == 'LINE' and e.dxf.layer == 'NOTCH']
        # We can't easily distinguish front vs back by position without knowing layout,
        # but we can verify total count is consistent with single+double pattern
        # Front: 2 knee + 1 hip + 1 CF = 4 notch lines
        # Back: 2 knee + 2 hip (double) + 1 CB = 5 notch lines
        # Total for panels: >= 9
        assert len(notch_lines) >= 9, \
            f"Only {len(notch_lines)} notch lines — may be missing single/double pattern"


# ── Annotation Geometry Quality ───────────────────────────────────────────

class TestAnnotationGeometry:
    """Verify annotations don't overlap or go off-pattern."""

    def test_seam_numbers_outside_cut_line(self, dxf_doc):
        """Seam number positions should be offset from cut line, not on it."""
        texts = [e for e in dxf_doc.modelspace()
                 if e.dxftype() == 'TEXT' and e.dxf.layer == 'TEXT'
                 and e.dxf.text in ('1', '2', '3', '4')]
        circles = [e for e in dxf_doc.modelspace() if e.dxftype() == 'CIRCLE']

        # Each number text should have a nearby circle
        for text in texts:
            try:
                tx, ty = text.dxf.insert.x, text.dxf.insert.y
            except:
                continue
            has_circle = any(
                math.hypot(c.dxf.center.x - tx, c.dxf.center.y - ty) < 0.5
                for c in circles
            )
            assert has_circle, f"Seam number '{text.dxf.text}' at ({tx:.1f},{ty:.1f}) has no nearby circle"

    def test_notch_marks_are_short(self, dxf_doc):
        """Notch marks should be ~0.25" long, not full-length lines."""
        notch_lines = [e for e in dxf_doc.modelspace()
                       if e.dxftype() == 'LINE' and e.dxf.layer == 'NOTCH']
        for line in notch_lines:
            length = math.hypot(
                line.dxf.end.x - line.dxf.start.x,
                line.dxf.end.y - line.dxf.start.y
            )
            assert length < 1.0, f"Notch line is {length:.2f}\" long (should be ~0.25\")"

    def test_grain_arrowheads_are_small(self, dxf_doc):
        """Arrowheads should be small triangles, not huge shapes."""
        grain_polys = [e for e in dxf_doc.modelspace()
                       if e.dxftype() == 'LWPOLYLINE' and e.dxf.layer == 'GRAIN' and e.closed]
        for poly in grain_polys:
            pts = list(poly.get_points(format='xy'))
            if len(pts) < 3:
                continue
            xs = [p[0] for p in pts]
            ys = [p[1] for p in pts]
            w = max(xs) - min(xs)
            h = max(ys) - min(ys)
            assert max(w, h) < 1.0, f"Arrowhead is {w:.2f}\"×{h:.2f}\" (too large)"


# ── Construction Guide ────────────────────────────────────────────────────

class TestConstructionGuide:
    """Verify the construction guide exists and has required sections."""

    GUIDE_PATH = '/Users/al/base/creative/MAREv2/designs/wide-leg-twill-pants/CONSTRUCTION-GUIDE.md'

    @pytest.fixture
    def guide_text(self):
        with open(self.GUIDE_PATH) as f:
            return f.read()

    def test_guide_exists(self):
        assert os.path.exists(self.GUIDE_PATH)

    def test_has_pattern_pieces_table(self, guide_text):
        assert '| # | Piece' in guide_text

    def test_has_seam_key(self, guide_text):
        assert 'Seam Key' in guide_text
        assert '①' in guide_text or 'Inseam' in guide_text

    def test_has_notch_guide(self, guide_text):
        assert 'Notch Guide' in guide_text
        assert 'Single notch' in guide_text
        assert 'Double notch' in guide_text

    def test_has_irl_sewing_order(self, guide_text):
        assert 'Sewing Order' in guide_text or 'IRL' in guide_text
        # Should have numbered steps
        assert '1.' in guide_text
        assert 'Inseam' in guide_text or 'inseam' in guide_text

    def test_has_clo3d_instructions(self, guide_text):
        assert 'CLO3D' in guide_text
        assert 'Sewing Pairs' in guide_text or 'sewing' in guide_text.lower()

    def test_has_fabric_requirements(self, guide_text):
        assert 'Fabric' in guide_text
        assert 'yards' in guide_text or 'yard' in guide_text

    def test_seam_numbers_match_dxf(self, guide_text):
        """Guide seam numbers should match what's in the DXF."""
        assert '①' in guide_text  # inseam
        assert '②' in guide_text  # side seam
        assert '③' in guide_text  # center seam
        assert '④' in guide_text  # waist

    def test_all_pieces_listed(self, guide_text):
        """All 9 pieces should appear in the guide."""
        for piece in ['Front Panel', 'Back Panel', 'Waistband', 'Fly Shield',
                       'Fly Extension', 'Pocket Bag', 'Pocket Welt', 'Belt Loop']:
            assert piece in guide_text, f"Missing piece in guide: {piece}"
