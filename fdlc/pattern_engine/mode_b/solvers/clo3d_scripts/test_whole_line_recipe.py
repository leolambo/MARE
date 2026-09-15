"""Offline recipe coverage, never native index authority or host evidence."""
import copy
import unittest
import seam_correspondence as geometry
import whole_line_recipe as recipe


def fixture():
    corners = [(0, 0), (10, 0), (10, 10), (0, 10), (0, 0)]
    patterns = []
    for name in ('Back_Left', 'Front_Left'):
        patterns.append({'Name': name, 'ID': name, 'ShapeInfo': {'LineList': [
            {'ID': str(i), 'PointList': [{'PointType': 0, 'Position': {'x': x, 'y': y}}
                                       for x, y in corners[i:i+2]]}
            for i in range(4)]}})
    source = {'Unit': 'mm', 'PatternList': patterns, 'SeamLinePairGroupList': [
        {'Name': 'section', 'PairList': [{key: {'ShapeID': name, 'Direction': False,
            'LengthParam': {'fStart': .25, 'fEnd': .5}}
            for key, name in [('First', 'Back_Left'), ('Second', 'Front_Left')]}]}]}
    target = copy.deepcopy(source)
    target['SeamLinePairGroupList'] = []
    for p in target['PatternList']:
        p['ID'] += '-export'
        p['ShapeInfo']['LineList'] = p['ShapeInfo']['LineList'][2:] + p['ShapeInfo']['LineList'][:2]
    target['PatternList'].reverse()
    return source, target


class WholeLineRecipeTests(unittest.TestCase):
    def test_perimeter_fraction_is_whole_section_not_native_ordinal(self):
        self.assertIsNotNone(recipe, 'whole-line recipe analysis is missing')
        source, target = fixture()
        before = copy.deepcopy((source, target))
        report = recipe.analyze(source, target)
        side = report['groups'][0]['sides'][0]
        self.assertEqual(side['coverage'], 'whole-target-section')
        self.assertEqual(side['source_sections'], [1])
        self.assertEqual(side['target_sections'], [3])
        self.assertEqual(report['native_index_binding'], 'unproven')
        self.assertNotIn('pattern_index', side)
        self.assertNotIn('line_index', side)
        self.assertEqual((source, target), before)

    def test_line_id_does_not_override_conflicting_boundary_coverage(self):
        source, target = fixture()
        for side in source['SeamLinePairGroupList'][0]['PairList'][0].values():
            side['LineID'] = '2'
        with self.assertRaisesRegex(geometry.CorrespondenceError, 'line-id-coverage-mismatch'):
            recipe.analyze(source, target)

    def test_nonboundary_fraction_is_not_whole_line(self):
        source, target = fixture()
        for side in source['SeamLinePairGroupList'][0]['PairList'][0].values():
            side['LineID'] = '1'
            side['LengthParam']['fEnd'] = .4
        with self.assertRaisesRegex(geometry.CorrespondenceError, 'nonboundary-endpoint'):
            recipe.analyze(source, target)

    def test_multiple_sections_are_not_one_native_line(self):
        source, target = fixture()
        for side in source['SeamLinePairGroupList'][0]['PairList'][0].values():
            side['LengthParam'] = {'fStart': .75, 'fEnd': .25}
        report = recipe.analyze(source, target)
        for side in report['groups'][0]['sides']:
            self.assertEqual(side['coverage'], 'multiple-target-sections')
            self.assertEqual(side['source_sections'], [1, 2])


if __name__ == '__main__':
    unittest.main()
