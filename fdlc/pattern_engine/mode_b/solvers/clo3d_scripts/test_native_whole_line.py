"""Synthetic exact observed GetPatternLineInfo schema, not host fixtures."""
import copy
import json
import unittest
import seam_correspondence as geo
from test_whole_line_recipe import fixture
try:
    import native_whole_line as native
except ImportError:
    native = None


def capture(target):
    rows = []
    for index, p in enumerate(target['PatternList']):
        lines = []
        for j, section in enumerate(geo.points(p)):
            lines.append({'lineIndex': 10 + j, 'start': dict(zip(('x','y'), section[0])),
                          'end': dict(zip(('x','y'), section[-1])), 'length': geo.arc_length(section)})
        rows.append({'index': index, 'outline_points': [],
                     'pattern_information_json': json.dumps({'name': p['Name'], 'id': index, 'uuid': 'synthetic'}),
                     'pattern_line_info_json': json.dumps({'patternIndex': index, 'patternName': p['Name'],
                         'status': 'success', 'lineCount': len(lines), 'lines': lines[::-1]})})
    return {'ok': True, 'pattern_count': len(rows), 'patterns': rows}


class NativeBindingTests(unittest.TestCase):
    def test_native_line_indices_are_geometry_matched_not_ordinals(self):
        self.assertIsNotNone(native, 'native binder missing')
        source, target = fixture()
        mapping = native.bind_geometry(target, capture(target))
        self.assertEqual(mapping['Back_Left']['sections'][3], (13, False))
        self.assertEqual(mapping['Back_Left']['pattern_index'], 1)

    def test_fixed_group_binds_recipe_forward_endpoints(self):
        self.assertTrue(hasattr(native, 'bind_fixed'), 'fixed native binding missing')
        source, target = fixture()
        source['SeamLinePairGroupList'][0]['Name'] = 'side_top_L'
        for document in (source, target):
            for name in ('Front_Right', 'Back_Right', 'WB_Front', 'WB_Back'):
                p = copy.deepcopy(document['PatternList'][0]); p['Name'] = p['ID'] = name
                document['PatternList'].append(p)
        result = native.bind_fixed(source, target, capture(target), 0)
        self.assertEqual(result, {'pattern_a': 1, 'line_a': 13, 'pattern_b': 0,
                                 'line_b': 13, 'direction_a': True, 'direction_b': True})
        with self.assertRaises(ValueError): native.bind_fixed(source, target, capture(target), 2)

    def test_export_pairing_requires_intended_edges_not_just_counts(self):
        self.assertTrue(hasattr(native, 'verify_fixed_result'), 'result verifier missing')
        source, target = fixture()
        source['SeamLinePairGroupList'][0]['Name'] = 'side_top_L'
        sewn = copy.deepcopy(target)
        sewn['SeamLinePairGroupList'] = [{'PairList': [{
            'First': {'ShapeID': 'Back_Left-export', 'LineID': '1', 'Direction': True,
                      'LengthParam': {'fStart': .75, 'fEnd': 1.0}},
            'Second': {'ShapeID': 'Front_Left-export', 'LineID': '1', 'Direction': True,
                       'LengthParam': {'fStart': .75, 'fEnd': 1.0}}}]}]
        native.verify_fixed_result(source, target, sewn, 1)
        sewn['SeamLinePairGroupList'][0]['PairList'][0]['First']['LineID'] = '2'
        with self.assertRaises(ValueError): native.verify_fixed_result(source, target, sewn, 1)

    def test_reversed_native_line_sets_endpoint_direction(self):
        _, target = fixture(); live = capture(target)
        row = live['patterns'][0]; info = json.loads(row['pattern_line_info_json'])
        for line in info['lines']:
            line['start'], line['end'] = line['end'], line['start']
        row['pattern_line_info_json'] = json.dumps(info)
        self.assertTrue(native.bind_geometry(target, live)['Front_Left']['sections'][0][1])

    def test_rejects_transform_length_drift_and_ambiguous_indices(self):
        _, target = fixture()
        for kind in ('frame', 'length', 'index', 'nan'):
            with self.subTest(kind=kind):
                live = capture(target); row = live['patterns'][0]
                info = json.loads(row['pattern_line_info_json'])
                if kind == 'frame': info['lines'][0]['start']['x'] += 100
                if kind == 'length': info['lines'][0]['length'] += 1
                if kind == 'index': info['lines'][0]['lineIndex'] = info['lines'][1]['lineIndex']
                if kind == 'nan': info['lines'][0]['length'] = float('nan')
                row['pattern_line_info_json'] = json.dumps(info)
                with self.assertRaises(ValueError): native.bind_geometry(target, live)

if __name__ == '__main__': unittest.main()
