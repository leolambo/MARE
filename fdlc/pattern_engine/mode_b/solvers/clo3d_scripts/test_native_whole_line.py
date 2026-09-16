"""Synthetic exact observed GetPatternLineInfo schema, not host fixtures."""
import copy
import json
import struct
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


def verify(source, before, after, count, live):
    intended = native.whole_line_recipe.analyze(source, before)["groups"][:count]
    requests = native._planned_requests(intended, native.bind_geometry(before, live))
    return native.verify_fixed_result(source, before, after, count, live, requests=requests)


class NativeBindingTests(unittest.TestCase):
    def test_group2_binds_whole_section_with_native_reversal(self):
        source, target = fixture()
        first = source['SeamLinePairGroupList'][0]
        source['SeamLinePairGroupList'] = []
        for i, name in enumerate(('side_top_L', 'side_hip_knee_L', 'side_knee_hem_L')):
            group = copy.deepcopy(first); group['Name'] = name
            for side in group['PairList'][0].values():
                side['LengthParam'] = {'fStart': (i+1)/4, 'fEnd': (i+2)/4}
            source['SeamLinePairGroupList'].append(group)
        for document in (source, target):
            for name in ('Front_Right', 'Back_Right', 'WB_Front', 'WB_Back'):
                p = copy.deepcopy(document['PatternList'][0]); p['Name'] = p['ID'] = name
                document['PatternList'].append(p)
        live = capture(target)
        row = live['patterns'][0]; info = json.loads(row['pattern_line_info_json'])
        for line in info['lines']:
            line['start'], line['end'] = line['end'], line['start']
        row['pattern_line_info_json'] = json.dumps(info)
        self.assertEqual(native.bind_fixed(source, target, live, 2),
            dict(pattern_a=1, line_a=11, pattern_b=0, line_b=11,
                 direction_a=True, direction_b=False))
        sewn, _ = geo.correspond(source, target)
        for group in sewn['SeamLinePairGroupList']:
            for side in group['PairList'][0].values(): side['Direction'] = True
        verify(source, target, sewn, 3, live)
        for index in range(3):
            bad = copy.deepcopy(sewn)
            bad['SeamLinePairGroupList'][index]['PairList'][0]['First']['Direction'] = False
            with self.assertRaisesRegex(ValueError, 'native-result-pairing-or-direction'):
                verify(source, target, bad, 3, live)
        for invalid in (-1, 3, True):
            with self.assertRaisesRegex(ValueError, 'unsupported-native-group'):
                native.bind_fixed(source, target, live, invalid)

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
        with self.assertRaises(ValueError): native.bind_fixed(source, target, capture(target), 3)

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
        verify(source, target, sewn, 1, capture(target))
        sewn['SeamLinePairGroupList'][0]['PairList'][0]['First']['LineID'] = '2'
        with self.assertRaisesRegex(ValueError, 'native-result-whole-section'):
            verify(source, target, sewn, 1, capture(target))

    def test_native_length_model_not_analytic_perimeter(self):
        source, target = fixture()
        live = capture(target)
        sewn = copy.deepcopy(target)
        pair = {}
        for role, name in zip(('First', 'Second'), ('Back_Left', 'Front_Left')):
            row = next(r for r in live['patterns'] if json.loads(r['pattern_information_json'])['name'] == name)
            info = json.loads(row['pattern_line_info_json'])
            # Deliberately distinct native length model; reverse native endpoint
            # orientation and array order, retaining explicit nonordinal indices.
            for line in info['lines']:
                line['start'], line['end'] = line['end'], line['start']
                if line['lineIndex'] == 10: line['length'] += .01
            row['pattern_line_info_json'] = json.dumps(info)
            sizes = [next(l['length'] for l in info['lines'] if l['lineIndex'] == 10+i) for i in range(4)]
            fractions = geo.boundaries(sizes)
            pair[role] = {'ShapeID': name+'-export', 'LineID': '1', 'Direction': True,
                          'LengthParam': {'fStart': fractions[3], 'fEnd': fractions[4]}}
        sewn['SeamLinePairGroupList'] = [{'PairList': [pair]}]
        verify(source, target, sewn, 1, live)
        rounded = copy.deepcopy(sewn)
        for side in rounded['SeamLinePairGroupList'][0]['PairList'][0].values():
            for key, value in side['LengthParam'].items():
                side['LengthParam'][key] = round(struct.unpack('f', struct.pack('f', value))[0], 9)
        verify(source, target, rounded, 1, live)
        for kind in ('missing', 'stale', 'partial', 'local', 'line', 'direction', 'outside'):
            with self.subTest(kind=kind):
                bad, witness = copy.deepcopy(sewn), copy.deepcopy(live)
                side = bad['SeamLinePairGroupList'][0]['PairList'][0]['First']
                if kind == 'missing': witness = None
                if kind == 'stale': witness['patterns'][0]['outline_points'] = [1]
                if kind == 'partial': side['LengthParam']['fStart'] += .001
                if kind == 'local': side['LengthParam'] = {'fStart': 0, 'fEnd': 1}
                if kind == 'line': side['LineID'] = '2'
                if kind == 'direction': side['Direction'] = False
                if kind == 'outside': side['LengthParam']['fStart'] += (2**-23 + 5e-10) * 1.001
                with self.assertRaises(ValueError): verify(source, target, bad, 1, witness)

    def test_physical_caps_large_perimeter_and_tiny_section(self):
        for width, height in ((1000000., 1000000.), (1000., .01)):
            with self.subTest(width=width, height=height):
                source, target = fixture()
                for doc in (source, target):
                    for panel in doc['PatternList']:
                        for line in panel['ShapeInfo']['LineList']:
                            for point in line['PointList']:
                                point['Position']['x'] *= width/10
                                point['Position']['y'] *= height/10
                perimeter = 2*(width+height)
                for side in source['SeamLinePairGroupList'][0]['PairList'][0].values():
                    side['LengthParam'] = {'fStart': width/perimeter, 'fEnd': .5}
                sewn = copy.deepcopy(target)
                pair = {role: {'ShapeID': name+'-export', 'LineID': '1', 'Direction': True,
                    'LengthParam': {'fStart': 1-height/perimeter, 'fEnd': 1.}}
                    for role, name in zip(('First','Second'), ('Back_Left','Front_Left'))}
                sewn['SeamLinePairGroupList'] = [{'PairList': [pair]}]
                live = capture(target)
                verify(source, target, sewn, 1, live)
                bound = min(2**-23+5e-10, .001/perimeter, .001*height/perimeter)
                good = copy.deepcopy(sewn)
                good['SeamLinePairGroupList'][0]['PairList'][0]['First']['LengthParam']['fStart'] += bound*.99
                verify(source, target, good, 1, live)
                pair['First']['LengthParam']['fStart'] += bound*1.01
                with self.assertRaisesRegex(ValueError, 'native-result-whole-section'):
                    verify(source, target, sewn, 1, live)

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
