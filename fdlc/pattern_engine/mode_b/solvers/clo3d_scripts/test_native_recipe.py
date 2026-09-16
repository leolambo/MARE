"""Generated, synthetic observations only; no host authority."""
import contextlib
import copy
import io
import json
from pathlib import Path
import sys
import tempfile
import unittest
sys.path.insert(0, str(Path(__file__).resolve().parent.parent))
import clo3d_json
import native_whole_line as native
import seam_correspondence as geo
from test_native_whole_line import capture


def fixture():
    with tempfile.TemporaryDirectory() as tmp, contextlib.redirect_stdout(io.StringIO()):
        path = Path(tmp)/'panels.json'
        clo3d_json.generate_5panel_json({'waist':30., 'hip':44., 'front_rise':12.75,
            'inseam':31.5, 'outseam':43.5, 'leg_opening':23.5}, str(path))
        source = json.loads(path.read_text())
    target = copy.deepcopy(source)
    target['SeamLinePairGroupList'] = []
    for p in target['PatternList']:
        for i, line in enumerate(p['ShapeInfo']['LineList']): line['ID'] = p['Name']+str(i)
    return source, target


def verify(source, before, after, count, live):
    intended = [native.recipe_plan(source, before)[i] for i in native.WHOLE_GROUPS[:count]]
    requests = native._planned_requests(intended, native.bind_geometry(before, live))
    return native.verify_recipe_result(source, before, after, count, live, requests=requests)


class RecipeTests(unittest.TestCase):
    def test_all_twenty_classified_and_nineteen_bounded(self):
        self.assertTrue(hasattr(native, 'recipe_plan'), 'recipe plan missing')
        source, target = fixture()
        plan = native.recipe_plan(source, target)
        self.assertEqual(len(plan), 20)
        self.assertEqual([p['index'] for p in plan if p['supported']], list(range(10))+list(range(11,20)))
        self.assertEqual(plan[10]['status'], 'center-front-grouping-unresolved')
        self.assertEqual(len(plan[10]['constituent_candidates']), 4)
        # Waist landmarks, not JSON booleans: center-to-side versus side-to-center.
        self.assertEqual([p['forward'] for p in plan[15]['sides']], [True, False])
        self.assertEqual([p['forward'] for p in plan[16]['sides']], [True, False])
        self.assertEqual([p['forward'] for p in plan[18]['sides']], [True, False])
        self.assertEqual([p['forward'] for p in plan[19]['sides']], [True, False])

    def test_rejects_easing_or_changed_fold_contract(self):
        for field,value in (('EaseRatio',1.1),('bIsTurned',True),('FoldData',{'iAngle':90,'iStrength':5})):
            with self.subTest(field=field):
                source,target=fixture()
                source['SeamLinePairGroupList'][3][field]=value
                with self.assertRaisesRegex(ValueError,'native-recipe-sewing-semantics'):
                    native.recipe_plan(source,target)

    def test_adversarial_source_grouping_mirror_overlap_and_endpoints(self):
        for kind in ('group-count','group-order','duplicate','mirror','endpoint','center-front','waistband'):
            with self.subTest(kind=kind):
                source,target=fixture()
                if kind=='group-count': source['SeamLinePairGroupList'].pop()
                if kind=='group-order': source['SeamLinePairGroupList'].reverse()
                if kind=='duplicate': source['SeamLinePairGroupList'][4]=copy.deepcopy(source['SeamLinePairGroupList'][3])
                if kind=='mirror':
                    source['PatternList'][1]['ShapeInfo']['LineList'][6]['PointList'][1]['Position']['x']+=1
                    target=copy.deepcopy(source); target['SeamLinePairGroupList']=[]
                if kind=='endpoint': source['SeamLinePairGroupList'][4]['PairList'][0]['First']['LengthParam']['fStart']+=.001
                if kind=='center-front': source['SeamLinePairGroupList'][10]['PairList'][0]['Second']['LengthParam']['fEnd']+=.001
                if kind=='waistband':
                    source['PatternList'][4]['ShapeInfo']['LineList'][0]['PointList'][-1]['Position']['x']+=1
                    target=copy.deepcopy(source); target['SeamLinePairGroupList']=[]
                with self.assertRaises(ValueError): native.recipe_plan(source,target)

    def test_unequal_lengths_are_not_trimmed_or_split(self):
        source,target=fixture(); plan=native.recipe_plan(source,target)
        self.assertGreater(abs(plan[4]['length_delta_mm']),1)
        self.assertEqual(plan[4]['sides'][0]['source_sections'],[6])
        self.assertEqual(plan[4]['sides'][1]['source_sections'],[6])
        self.assertEqual(plan[10]['length_delta_mm'],0)
        self.assertFalse(plan[10]['split_authorized'])

    def test_export_reversal_and_native_reversal_compose(self):
        source,target=fixture()
        for panel in target['PatternList']:
            lines=panel['ShapeInfo']['LineList']; lines.reverse()
            for line in lines: line['PointList'].reverse()
        live=capture(target)
        # FR attachment: source WB forward, FR backward; export reversed both.
        ref=native.bind_recipe(source,target,live,14)
        self.assertEqual((ref['direction_a'],ref['direction_b']),(False,True))
        for row in live['patterns']:
            info=json.loads(row['pattern_line_info_json'])
            for line in info['lines']: line['start'],line['end']=line['end'],line['start']
            row['pattern_line_info_json']=json.dumps(info)
        ref=native.bind_recipe(source,target,live,14)
        self.assertEqual((ref['direction_a'],ref['direction_b']),(True,False))

    def test_all_bindings_and_complete_pairing_verifier(self):
        self.assertTrue(hasattr(native, 'bind_recipe'), 'bounded recipe binder missing')
        self.assertTrue(hasattr(native, 'verify_recipe_result'), 'bounded recipe verifier missing')
        source, target = fixture(); live = capture(target)
        plan = native.recipe_plan(source,target)
        sewn = copy.deepcopy(target)
        for stage,index in enumerate(native.WHOLE_GROUPS):
            ref = native.bind_recipe(source,target,live,stage)
            sides = plan[index]['sides']; pair={}
            for role, side, suffix in zip(('First','Second'), sides, ('a','b')):
                panel = next(p for p in target['PatternList'] if p['Name']==side['panel'])
                section=side['target_sections'][0]
                fractions=geo.boundaries([geo.arc_length(s) for s in geo.points(panel)])
                self.assertEqual(ref['direction_'+suffix], side['forward'])
                pair[role]={'ShapeID':panel['ID'],'LineID':panel['ShapeInfo']['LineList'][section]['ID'],
                    'Direction':side['forward'], 'LengthParam':dict(zip(('fStart','fEnd'),
                        fractions[section:section+2] if side['forward'] else fractions[section:section+2][::-1]))}
            sewn['SeamLinePairGroupList'].append({'PairList':[pair]})
            verify(source,target,sewn,stage+1,live)
        for kind in ('direction','duplicate','count','partial'):
            with self.subTest(kind=kind):
                bad=copy.deepcopy(sewn)
                if kind=='direction': bad['SeamLinePairGroupList'][14]['PairList'][0]['Second']['Direction'] ^= True
                if kind=='duplicate': bad['SeamLinePairGroupList'][5]=copy.deepcopy(bad['SeamLinePairGroupList'][0])
                if kind=='count': bad['SeamLinePairGroupList'].pop()
                if kind=='partial': bad['SeamLinePairGroupList'][17]['PairList'][0]['First']['LengthParam']['fStart']+=.001
                with self.assertRaises(ValueError): verify(source,target,bad,19,live)
        for bad in (-1,23,True):
            with self.assertRaises(ValueError): native.bind_recipe(source,target,live,bad)
        # Host array order and endpoints are not source traversal.
        for row in live['patterns']:
            info=json.loads(row['pattern_line_info_json'])
            for line in info['lines']: line['start'],line['end']=line['end'],line['start']
            row['pattern_line_info_json']=json.dumps(info)
        self.assertEqual(native.bind_recipe(source,target,live,14)['direction_b'], True)

if __name__ == '__main__': unittest.main()
