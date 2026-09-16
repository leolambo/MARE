"""Synthetic native output contract; not independent host reversal evidence."""
import copy
import json
import unittest
import native_whole_line as n
from test_native_recipe import fixture
from test_native_whole_line import capture

def output_fixture(sdk=True, native_reverse=False, export_reverse=False):
    import math
    source, before = fixture()
    live = capture(before)
    if native_reverse:
        for row in live['patterns']:
            info = json.loads(row['pattern_line_info_json'])
            for line in info['lines']:
                line['start'], line['end'] = line['end'], line['start']
            row['pattern_line_info_json'] = json.dumps(info)
    after = copy.deepcopy(before)
    if export_reverse:
        for panel in after['PatternList']:
            panel['ShapeInfo']['LineList'].reverse()
            for line in panel['ShapeInfo']['LineList']: line['PointList'].reverse()
    request, pair = {}, {}
    # Explicit synthetic SDK request: section0 of two distinct native patterns.
    for suffix, role, pattern in zip(('a','b'), ('First','Second'), (0,1)):
        request.update({'pattern_'+suffix:pattern, 'line_'+suffix:10, 'direction_'+suffix:sdk})
        panel = after['PatternList'][pattern]
        sizes = [n.geo.arc_length(s) for s in n.geo.points(panel)]
        index = len(sizes)-1 if export_reverse else 0
        bounds = [math.fsum(sizes[:i])/math.fsum(sizes) for i in (index,index+1)]
        # Independent coordinate-frame truth table, no production helper.
        forward = bool((int(sdk)+int(native_reverse)+int(export_reverse)) % 2)
        if not forward: bounds.reverse()
        pair[role] = {'ShapeID':panel['ID'], 'LineID':panel['ShapeInfo']['LineList'][index]['ID'],
                     'Direction':forward, 'LengthParam':dict(zip(('fStart','fEnd'),bounds))}
    after['SeamLinePairGroupList'] = [{'PairList':[pair]}]
    return source, before, after, live, [request]


class OutputContractTests(unittest.TestCase):
    def test_sdk_native_and_export_reversal_truth_table(self):
        import itertools
        for sdk, nr, er in itertools.product((False, True), repeat=3):
            with self.subTest(sdk=sdk, native_reverse=nr, export_reverse=er):
                _, before, after, live, requests = output_fixture(sdk,nr,er)
                n.verify_native_output(before,after,live,requests)
                for kind in ('order', 'raw', 'both', 'line', 'coverage', 'ambiguous'):
                    with self.subTest(corruption=kind):
                        bad=copy.deepcopy(after)
                        side=bad['SeamLinePairGroupList'][0]['PairList'][0]['First']
                        if kind in ('order','both'):
                            p=side['LengthParam']; p['fStart'],p['fEnd']=p['fEnd'],p['fStart']
                        if kind in ('raw','both'): side['Direction'] = not side['Direction']
                        if kind=='line': side['LineID']='unknown'
                        if kind=='coverage': side['LengthParam']['fStart'] += .001
                        if kind=='ambiguous':
                            panel=bad['PatternList'][0]
                            panel['ShapeInfo']['LineList'][1]['ID']=side['LineID']
                        with self.assertRaises(ValueError): n.verify_native_output(before,bad,live,requests)

    def test_request_schema_policy_and_geometry_fail_closed(self):
        source,before,after,live,requests=output_fixture()
        for kind in ('missing','integer-direction','bool-index','extra','wrong-line','wrong-pattern'):
            with self.subTest(kind=kind):
                bad=copy.deepcopy(requests)
                if kind=='missing': bad=None
                if kind=='integer-direction': bad[0]['direction_a']=1
                if kind=='bool-index': bad[0]['pattern_a']=False
                if kind=='extra': bad[0]['ignored']=0
                if kind=='wrong-line': bad[0]['line_a']=999
                if kind=='wrong-pattern': bad[0]['pattern_a']=99
                with self.assertRaises(ValueError): n.verify_native_output(before,after,live,bad)
        with self.assertRaisesRegex(ValueError,'native-result-request-policy'):
            n.verify_recipe_result(source,before,after,1,live,requests=requests)
        ambiguous=copy.deepcopy(live)
        info=json.loads(ambiguous['patterns'][0]['pattern_line_info_json'])
        info['lines'][1]['lineIndex']=info['lines'][0]['lineIndex']
        ambiguous['patterns'][0]['pattern_line_info_json']=json.dumps(info)
        with self.assertRaises(ValueError): n.verify_native_output(before,after,ambiguous,requests)

    def test_exact_request_is_required(self):
        source,before=fixture(); live=capture(before)
        after=copy.deepcopy(before)
        with self.assertRaisesRegex(ValueError,'native-result-requests'):
            n.verify_recipe_result(source,before,after,1,live)


if __name__ == '__main__': unittest.main()
