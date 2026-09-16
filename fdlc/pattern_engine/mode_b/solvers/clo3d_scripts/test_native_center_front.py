"""Synthetic fixed CF graph equivalence, not physical CLO acceptance."""
import copy
import unittest
import native_recipe as recipe
import native_whole_line as native
import seam_correspondence as geo
from test_native_recipe import fixture
from test_native_whole_line import capture

class CenterFrontTests(unittest.TestCase):
    def test_native_cf_lengths_must_agree_without_new_easing(self):
        import json
        source,target = fixture(); live = capture(target)
        row = next(r for r in live['patterns'] if json.loads(r['pattern_line_info_json'])['patternName']=='Front_Right')
        info = json.loads(row['pattern_line_info_json'])
        # Within normal endpoint/length binding tolerance, but not CF no-ease.
        line = next(s for s in info['lines'] if abs(s['start']['y'] + 323.85)<1e-6 and abs(s['end']['y'] + 247.65)<1e-6)
        line['length'] += .01
        row['pattern_line_info_json'] = json.dumps(info)
        with self.assertRaisesRegex(ValueError, 'native-center-front-length-equality'):
            native.bind_recipe(source,target,live,19)

    def test_cf_geometry_adversaries_fail_closed(self):
        for kind in ('gap','overlap','curve-control','coverage-gap','duplicate'):
            with self.subTest(kind=kind):
                source,target = fixture()
                panels = geo.panel_index(target)
                if kind in ('gap','overlap'):
                    panels['Front_Right']['ShapeInfo']['LineList'][9]['PointList'][0]['Position']['y'] += .01 if kind=='gap' else -.01
                elif kind=='curve-control':
                    # Same endpoints but different full curve is not equivalent.
                    line = panels['Front_Right']['ShapeInfo']['LineList'][9]
                    control = copy.deepcopy(line['PointList'][0]); control['Position']['x'] += .01
                    line['PointList'].insert(1,control)
                elif kind=='coverage-gap':
                    source['SeamLinePairGroupList'][10]['PairList'][0]['Second']['LengthParam']['fStart'] -= .01
                else:
                    panels['Front_Right']['ShapeInfo']['LineList'][9] = copy.deepcopy(panels['Front_Right']['ShapeInfo']['LineList'][8])
                with self.assertRaises(ValueError): recipe.execution_plan(source,target)

    def test_cf_geometry_maps_reversed_rotated_targets_and_native_indices(self):
        import json
        source,target = fixture()
        for panel in target['PatternList']:
            lines=panel['ShapeInfo']['LineList']; lines.reverse()
            for line in lines: line['PointList'].reverse()
        live = capture(target)
        expected = native.bind_geometry(target,live)
        plan = recipe.execution_plan(source,target)
        for i in range(19,23):
            binding = native.bind_recipe(source,target,live,i)
            for suffix,side in zip(('a','b'),plan[i]['sides']):
                section=side['target_sections'][0]
                self.assertEqual(binding['line_'+suffix],expected[side['panel']]['sections'][section][0])
                self.assertFalse(binding['direction_'+suffix])
        for row in live['patterns']:
            info=json.loads(row['pattern_line_info_json'])
            for line in info['lines']:
                line['lineIndex'] += 300
                line['start'],line['end']=line['end'],line['start']
            row['pattern_line_info_json']=json.dumps(info)
        for i in range(19,23):
            binding=native.bind_recipe(source,target,live,i)
            self.assertTrue(binding['direction_a']); self.assertTrue(binding['direction_b'])
            self.assertGreaterEqual(binding['line_a'],300)

    def test_complete_twenty_semantic_groups_in_twenty_three_native_stages(self):
        source, target = fixture()
        self.assertTrue(hasattr(recipe, 'execution_plan'), 'fixed constituent execution plan missing')
        plan = recipe.execution_plan(source, target)
        self.assertEqual(len(plan), 23)
        self.assertEqual([p['index'] for p in plan[:19]], list(recipe.WHOLE_GROUPS))
        self.assertEqual([p['index'] for p in plan[19:]], [10]*4)
        self.assertEqual({p['index'] for p in plan}, set(range(20)))
        for suffix in (0,1):
            self.assertEqual([p['sides'][suffix]['source_sections'] for p in plan[19:]], [[8],[9],[10],[11]])
        live = capture(target)
        requests = [native.bind_recipe(source,target,live,i) for i in range(23)]
        sewn = copy.deepcopy(target)
        for i, stage in enumerate(plan):
            pair = {}
            for role, side in zip(('First','Second'), stage['sides']):
                panel = geo.panel_index(target)[side['panel']]
                section = side['target_sections'][0]
                fractions = geo.boundaries([geo.arc_length(s) for s in geo.points(panel)])
                values = fractions[section:section+2]
                if not side['forward']: values = values[::-1]
                pair[role] = dict(ShapeID=panel['ID'],LineID=panel['ShapeInfo']['LineList'][section]['ID'],
                    Direction=side['forward'],LengthParam=dict(zip(('fStart','fEnd'), values)))
            sewn['SeamLinePairGroupList'].append({'PairList':[pair]})
            native.verify_recipe_result(source,target,sewn,i+1,live,requests=requests[:i+1])
        for i in range(19,23):
            bad = copy.deepcopy(sewn)
            bad['SeamLinePairGroupList'][i] = copy.deepcopy(bad['SeamLinePairGroupList'][19 if i!=19 else 20])
            with self.assertRaises(ValueError):
                native.verify_recipe_result(source,target,bad,23,live,requests=requests)

if __name__ == '__main__': unittest.main()
