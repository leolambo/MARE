"""Independent offline geometry examples, not observations of CLO."""
import copy
import importlib.util
from pathlib import Path
import pytest

HERE = Path(__file__).parent

def api():
    spec = importlib.util.spec_from_file_location('seam_geometry_test', HERE / 'seam_correspondence.py')
    assert spec is not None and spec.loader is not None
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    return module

def line(points, ident='edge'):
    types = [0, 0] if len(points) == 2 else [0, 3, 3, 0]
    return {'ID': ident, 'PointList': [
        {'PointType': t, 'Position': {'x': x, 'y': y}}
        for (x, y), t in zip(points, types)]}

def document():
    corners = [(0, 0), (10, 0), (10, 10), (0, 10), (0, 0)]
    return {'Unit': 'mm', 'PatternList': [
        {'Name': name, 'ID': ident, 'ShapeInfo': {'LineList': [
            line(corners[i:i+2], str(i)) for i in range(4)]}}
        for name, ident in [('waistband', 'a'), ('front', 'b')]],
        'SeamLinePairGroupList': [{'PairList': [{
            side: {'ShapeID': ident, 'LengthParam': {'fStart': 0, 'fEnd': .25}, 'Direction': True}
            for side, ident in [('First', 'a'), ('Second', 'b')]}]}]}

def export_of(source):
    target = copy.deepcopy(source)
    target['SeamLinePairGroupList'] = []
    for p in target['PatternList']:
        p['ID'] += '-export'
    target['Arrangement'] = {'unchanged': True}
    return target

def test_direct_straight_preserves_order_direction_and_export():
    source = document()
    target = export_of(source)
    before = copy.deepcopy((source, target))
    result, report = api().correspond(source, target)
    pair = result['SeamLinePairGroupList'][0]['PairList'][0]
    assert list(pair) == ['First', 'Second']
    assert pair['First'] == {'ShapeID': 'a-export', 'LengthParam': {'fStart': 0, 'fEnd': .25}, 'Direction': True}
    assert pair['Second']['ShapeID'] == 'b-export'
    assert {k: v for k, v in result.items() if k != 'SeamLinePairGroupList'} == {k: v for k, v in target.items() if k != 'SeamLinePairGroupList'}
    assert (source, target) == before
    assert report['status'] == 'passed'

def test_line_id_resolves_geometry_when_export_line_ids_change():
    source = document()
    for side in source['SeamLinePairGroupList'][0]['PairList'][0].values():
        del side['LengthParam']
        side['LineID'] = '0'
    target = export_of(source)
    for p in target['PatternList']:
        for edge in p['ShapeInfo']['LineList']:
            edge['ID'] += '-new'
    result, _ = api().correspond(source, target)
    side = result['SeamLinePairGroupList'][0]['PairList'][0]['First']
    assert 'LineID' not in side
    assert side['LengthParam'] == {'fStart': 0, 'fEnd': .25}

def test_cubic_uses_arc_length_not_generator_control_polygon_factor():
    source = document()
    for p in source['PatternList']:
        p['ShapeInfo']['LineList'][0] = line([(0, 0), (0, -10), (10, -10), (10, 0)], '0')
    # This cubic has speed 30*(2*t*t-2*t+1); exact integral = 20.
    for side in source['SeamLinePairGroupList'][0]['PairList'][0].values():
        side['LengthParam']['fEnd'] = (30 * 1.15) / (30 * 1.15 + 30)
    result, _ = api().correspond(source, export_of(source))
    assert result['SeamLinePairGroupList'][0]['PairList'][0]['First']['LengthParam']['fEnd'] == pytest.approx(20 / 50, abs=1e-10)

@pytest.mark.parametrize('fault', ['missing', 'type', 'bool', 'open', 'degenerate'])
def test_boundary_geometry_schema_fails_closed(fault):
    source = document()
    edge = source['PatternList'][0]['ShapeInfo']['LineList'][0]
    if fault == 'missing':
        del edge['PointList']
    if fault == 'type':
        edge['PointList'][0]['PointType'] = 3
    if fault == 'bool':
        edge['PointList'][0]['Position']['x'] = True
    if fault == 'open':
        edge['PointList'][0]['Position']['x'] = 2
    if fault == 'degenerate':
        edge['PointList'][1] = copy.deepcopy(edge['PointList'][0])
    with pytest.raises(ValueError, match='geometry-schema|open-boundary|degenerate-section'):
        api().correspond(source, export_of(source))

def test_unmatched_geometry_rejects_instead_of_copying_fractions():
    source = document()
    target = export_of(source)
    for edge in target['PatternList'][0]['ShapeInfo']['LineList']:
        for p in edge['PointList']:
            p['Position']['x'] += 100
    with pytest.raises(ValueError, match='unmatched-geometry'):
        api().correspond(source, target)

@pytest.mark.parametrize('reverse', [False, True])
def test_cyclic_reorder_and_reverse_map_physical_edge_not_direction(reverse):
    source = document()
    target = export_of(source)
    for p in target['PatternList']:
        lines = p['ShapeInfo']['LineList']
        if reverse:
            lines.reverse()
            for edge in lines:
                edge['PointList'].reverse()
        else:
            lines[:] = lines[1:] + lines[:1]
    result, _ = api().correspond(source, target)
    side = result['SeamLinePairGroupList'][0]['PairList'][0]['First']
    assert side['LengthParam'] == {'fStart': .75, 'fEnd': 1}
    assert side['Direction'] is True

def test_duplicate_geometry_is_ambiguous_even_in_direct_order():
    source = document()
    for p in source['PatternList']:
        p['ShapeInfo']['LineList'] *= 2
    with pytest.raises(ValueError, match='ambiguous-geometry'):
        api().correspond(source, export_of(source))

def test_nonboundary_source_fraction_rejected():
    source = document()
    source['SeamLinePairGroupList'][0]['PairList'][0]['First']['LengthParam']['fEnd'] = .125
    with pytest.raises(ValueError, match='nonboundary-endpoint'):
        api().correspond(source, export_of(source))

@pytest.mark.parametrize('endpoints', [(0, 0), (.25, .25), (1, 0)])
def test_empty_or_ambiguous_full_cycle_rejected(endpoints):
    source = document()
    source['SeamLinePairGroupList'][0]['PairList'][0]['First']['LengthParam'] = dict(zip(('fStart', 'fEnd'), endpoints))
    with pytest.raises(ValueError, match='empty-or-ambiguous-interval'):
        api().correspond(source, export_of(source))

def test_explicit_full_perimeter_survives_cyclic_reorder():
    source = document()
    for side in source['SeamLinePairGroupList'][0]['PairList'][0].values():
        side['LengthParam'] = {'fStart': 0, 'fEnd': 1}
    target = export_of(source)
    for p in target['PatternList']:
        edges = p['ShapeInfo']['LineList']
        edges[:] = edges[1:] + edges[:1]
    result, _ = api().correspond(source, target)
    assert result['SeamLinePairGroupList'][0]['PairList'][0]['First']['LengthParam'] == {'fStart': 0, 'fEnd': 1}

def test_private_report_carries_counts_tolerances_discrepancy_and_coverage():
    import json
    source = document()
    target = export_of(source)
    for p in target['PatternList']:
        for edge in p['ShapeInfo']['LineList']:
            for pt in edge['PointList']:
                pt['Position']['x'] += .0001
    _, report = api().correspond(source, target)
    assert report['counts'] == {'panels': 2, 'sections': 8, 'seam_sides': 2}
    assert report['coverage'] == {'matched_sections': 8, 'sewn_sections': 2}
    assert report['categories'] == {'direct': 2, 'reordered': 0, 'reversed': 0}
    assert report['tolerances']['direct_mm'] == .001
    assert report['tolerances']['numerical_mm'] == 1e-8
    assert report['discrepancy_mm']['max'] == pytest.approx(.0001)
    assert report['discrepancy_mm']['mean'] == pytest.approx(.0001)
    assert all(secret not in json.dumps(report) for secret in ('waistband', 'front', 'a-export', 'Position'))

@pytest.mark.parametrize('cubic', [False, True])
def test_subdivided_section_is_explicitly_unsupported(cubic):
    source = document()
    if cubic:
        source['PatternList'][0]['ShapeInfo']['LineList'][0] = line([(0, 0), (0, -10), (10, -10), (10, 0)], '0')
    target = export_of(source)
    split = [line([(0, 0), (5, 0)], 'split-a'), line([(5, 0), (10, 0)], 'split-b')]
    if cubic:
        split = [line([(0, 0), (0, -5), (2.5, -7.5), (5, -7.5)], 'split-a'),
                 line([(5, -7.5), (7.5, -7.5), (10, -5), (10, 0)], 'split-b')]
    target['PatternList'][0]['ShapeInfo']['LineList'][0:1] = split
    with pytest.raises(ValueError, match='unsupported-subdivision-or-section-count'):
        api().correspond(source, target)

@pytest.mark.parametrize('reverse', [False, True])
def test_non_direct_topology_never_uses_observed_serialization_tolerance(reverse):
    source = document()
    target = export_of(source)
    for pattern in target['PatternList']:
        edges = pattern['ShapeInfo']['LineList']
        if reverse:
            edges.reverse()
            for edge in edges:
                edge['PointList'].reverse()
        else:
            edges[:] = edges[1:] + edges[:1]
        for edge in edges:
            for pt in edge['PointList']:
                pt['Position']['x'] += .0001
    with pytest.raises(ValueError, match='unmatched-geometry'):
        api().correspond(source, target)

def test_adaptive_cubic_length_against_independent_parabola_integral():
    import math
    # Degree elevation of (x,y)=(10*t,10*t*t), analytic integral of speed.
    cubic = [(0, 0), (10/3, 0), (20/3, 10/3), (10, 10)]
    expected = 5*math.sqrt(5) + 2.5*math.asinh(2)
    assert api().arc_length(cubic) == pytest.approx(expected, abs=1e-10)

@pytest.mark.parametrize('fault', ['duplicate-name', 'duplicate-id', 'ambiguous-id', 'name-set-mismatch', 'unsupported-unit'])
def test_reusable_geometry_entrypoint_protects_panel_mapping(fault):
    source = document()
    target = export_of(source)
    if fault == 'duplicate-name':
        target['PatternList'][1]['Name'] = target['PatternList'][0]['Name']
    if fault == 'duplicate-id':
        target['PatternList'][1]['ID'] = target['PatternList'][0]['ID']
    if fault == 'ambiguous-id':
        target['PatternList'][0]['ShapeID'] = 'other'
    if fault == 'name-set-mismatch':
        target['PatternList'].pop()
    if fault == 'unsupported-unit':
        target['Unit'] = 'inch'
    with pytest.raises(ValueError, match=fault):
        api().correspond(source, target)

def test_snap_tolerance_is_unique_and_strict():
    module = api()
    assert module.snap(.25 + 5e-10, [0, .25, .5, 1]) == 1
    with pytest.raises(ValueError, match='nonboundary-endpoint'):
        module.snap(.25 + 2e-9, [0, .25, .5, 1])
    with pytest.raises(ValueError, match='ambiguous-endpoint'):
        module.snap(.25, [0, .25, .25 + 5e-10, 1])

def test_reverse_cubic_preserves_actual_section_and_direction_false():
    source = document()
    for p in source['PatternList']:
        p['ShapeInfo']['LineList'][0] = line([(0, 0), (0, -10), (10, -10), (10, 0)], '0')
    for side in source['SeamLinePairGroupList'][0]['PairList'][0].values():
        side['LengthParam'] = {'fStart': 0, 'fEnd': 34.5/64.5}
        side['Direction'] = False
    target = export_of(source)
    for p in target['PatternList']:
        p['ShapeInfo']['LineList'].reverse()
        for edge in p['ShapeInfo']['LineList']:
            edge['PointList'].reverse()
    result, report = api().correspond(source, target)
    side = result['SeamLinePairGroupList'][0]['PairList'][0]['First']
    assert side['Direction'] is False
    assert side['LengthParam'] == pytest.approx({'fStart': .6, 'fEnd': 1}, abs=1e-10)
    assert report['categories']['reversed'] == 2

@pytest.mark.parametrize('overlap', [False, True])
def test_wraparound_physical_coverage_allows_shared_endpoints_only(overlap):
    source = document()
    pair = source['SeamLinePairGroupList'][0]['PairList'][0]
    for side in pair.values():
        side['LengthParam'] = {'fStart': .75, 'fEnd': .25}
    extra = copy.deepcopy(pair)
    for side in extra.values():
        side['Direction'] = False
        side['LengthParam'] = {'fStart': 0 if overlap else .25, 'fEnd': .5}
    source['SeamLinePairGroupList'][0]['PairList'].append(extra)
    if overlap:
        with pytest.raises(ValueError, match='physical-interval-overlap'):
            api().correspond(source, export_of(source))
    else:
        result, _ = api().correspond(source, export_of(source))
        assert result['SeamLinePairGroupList'][0]['PairList'][0]['First']['LengthParam'] == {'fStart': .75, 'fEnd': .25}
