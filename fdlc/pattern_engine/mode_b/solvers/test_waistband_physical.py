"""Physical simulation bands must match the generated rounded-mm waist curves."""
import contextlib
import io
import json
import math
from pathlib import Path
import tempfile
import unittest

import clo3d_json as generator

MEASUREMENTS = dict(waist=30., hip=44., front_rise=12.75,
                    inseam=31.5, outseam=43.5, leg_opening=23.5)


def independent_length(line):
    """Composite midpoint integration, independent of adaptive Simpson code."""
    p = [tuple(v['Position'][k] for k in ('x', 'y')) for v in line['PointList']]
    if len(p) == 2:
        return math.dist(*p)
    n = 20000
    return math.fsum(math.hypot(*(3*((1-t)**2*(p[1][k]-p[0][k]) +
        2*(1-t)*t*(p[2][k]-p[1][k]) + t*t*(p[3][k]-p[2][k]))
        for k in (0, 1))) for t in ((i+.5)/n for i in range(n))) / n


def generate(measurements=MEASUREMENTS):
    with tempfile.TemporaryDirectory() as tmp, contextlib.redirect_stdout(io.StringIO()):
        p = Path(tmp)/'panels.json'
        generator.generate_5panel_json(measurements, str(p))
        return json.loads(p.read_text())


class PhysicalWaistbandTests(unittest.TestCase):
    def test_physical_integrator_independent_analytic_curve(self):
        # Cubic representation of (t, t^2), with known exact integral.
        line = {'PointList': [{'Position': dict(x=x, y=y)} for x, y in
                             [(0.,0.), (1/3,0.), (2/3,1/3), (1.,1.)]]}
        expected = math.sqrt(5)/2 + math.asinh(2)/4
        self.assertAlmostEqual(generator._physical_cubic_length_mm(line), expected, delta=1e-10)
        line['PointList'].reverse()
        self.assertAlmostEqual(generator._physical_cubic_length_mm(line), expected, delta=1e-10)
        for p in line['PointList']:
            p['Position']['x'] = 100 + p['Position']['x'] * 100
            p['Position']['y'] = -500 + p['Position']['y'] * 100
        self.assertAlmostEqual(generator._physical_cubic_length_mm(line), 100*expected, delta=1e-8)

    def test_other_four_panels_and_legacy_leg_seams_byte_unchanged(self):
        import hashlib
        import random
        # Captured from fbc7bf1 with deterministic IDs, not regenerated expectations.
        expected = ['05866ee3009c2459516a203b702020442743114b5dfeb237a247e2ae98702e0f',
                    '90dcdfbc500179be0ac1cdf549795f8bed1777f3a641ff89360c57fa935b55dc',
                    'c0974795399240c82abb9d2b3e2cf1f39bd36183c2487ce7e146237fe7d12d0c',
                    '70fb1efcc29992b8de8678674b688b2b5842ce9194b58fcd487ebfa747be2591']
        state = random.getstate()
        try:
            random.seed(123)
            document = generate()
        finally:
            random.setstate(state)
        digest = lambda value: hashlib.sha256(json.dumps(value, sort_keys=True,
                                          separators=(',', ':')).encode()).hexdigest()
        self.assertEqual([digest(p) for p in document['PatternList'][:4]], expected)
        # Python 3.12+ sum changes last-bit fraction rounding. Geometry above
        # stays byte-exact; seam fractions retain twelve decimal places here.
        def stable(value):
            if isinstance(value, float):
                return round(value, 12)
            if isinstance(value, list):
                return [stable(v) for v in value]
            if isinstance(value, dict):
                return {k: stable(v) for k, v in value.items()}
            return value
        self.assertEqual(digest(stable(document['SeamLinePairGroupList'][:14])),
                         'a789ce61e971150e3685f3e6ac4c5de849940a210eec6e184c013730f958e40f')

    def test_rectangular_midpoint_bands_match_multiple_generated_sizes(self):
        for waist, hip, rise in [(24.,36.,10.), (30.,44.,12.75), (42.,52.,15.)]:
            with self.subTest(waist=waist):
                panels = {p['Name']: p for p in generate(dict(MEASUREMENTS,
                          waist=waist, hip=hip, front_rise=rise))['PatternList']}
                for band, leg in [('WB_Front','Front_Left'), ('WB_Back','Back_Left')]:
                    lines = panels[band]['ShapeInfo']['LineList']
                    self.assertEqual(len(lines), 5)
                    self.assertTrue(all(len(line['PointList']) == 2 for line in lines))
                    pts = [[tuple(p['Position'][k] for k in ('x','y'))
                            for p in line['PointList']] for line in lines]
                    self.assertTrue(all(pts[i][-1] == pts[(i+1)%5][0] for i in range(5)))
                    lengths = [independent_length(line) for line in lines]
                    self.assertAlmostEqual(lengths[0], lengths[1], delta=1e-10)
                    self.assertAlmostEqual(lengths[2], 50.8, delta=1e-10)
                    self.assertAlmostEqual(lengths[4], 50.8, delta=1e-10)
                    self.assertAlmostEqual(lengths[3], 2*lengths[0], delta=1e-10)
                    self.assertTrue(all(a[0]==b[0] or a[1]==b[1] for a,b in pts))
                    self.assertAlmostEqual(lengths[0], independent_length(
                        panels[leg]['ShapeInfo']['LineList'][0]), delta=1e-3)

    def test_each_attachment_matches_actual_waist_without_artificial_ease(self):
        panels = {p['Name']: p['ShapeInfo']['LineList'] for p in generate()['PatternList']}
        for band, leg, half in [('WB_Front','Front_Left',1), ('WB_Front','Front_Right',0),
                                ('WB_Back','Back_Left',0), ('WB_Back','Back_Right',1)]:
            with self.subTest(band=band, leg=leg):
                self.assertAlmostEqual(independent_length(panels[band][half]),
                                       independent_length(panels[leg][0]), delta=1e-3)


if __name__ == '__main__':
    unittest.main()
