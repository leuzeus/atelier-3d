"""Public input failures and metric behaviour of the sourced volume guide."""
import copy
import math
import unittest

from a3d.core import StudioError, digest
from a3d.pattern_assembly import preform_coordinates
from a3d.pattern_preparation import preparation_statistics
from a3d.preform_volume import half_ellipse, sample_curve, volume_frames
from tests.test_pattern_assembly import example


def source_fixture():
    def rectangle(width):
        return {'vertices': [[0., 0.], [width, 0.], [width, 10.], [0., 10.]],
                'edges': {'center': [0, 3], 'hem': [0, 1], 'side': [1, 2],
                          'front': [0, 3], 'back': [1, 2]}}
    data = {'pieces': {'front': rectangle(4.), 'center': rectangle(1.),
                       'side': rectangle(2.), 'back': rectangle(4.)}}
    group = {'front': 'front', 'center': 'center', 'side': 'side', 'back': 'back',
        'pieces': ['front', 'center', 'side', 'back'], 'side_sign': 1,
        'front_neck_cm': 2., 'back_neck_cm': 2., 'uv_origin_cm': [0., 0.]}
    body = {'source_ref': 'fixture:explicit-geometric-frame', 'aspect_ratio': 1.,
        'center_xy_cm': [0., 0.], 'hem_z_cm': 17., 'neck_center_cm': [0., 0., 27.],
        'shoulders_cm': {'1': [4., 0., 27.], '-1': [-4., 0., 27.]}}
    return data, [group], body


class VolumeCurveDomain(unittest.TestCase):
    def test_actual_arc_length_is_independent_of_nonuniform_segment_counts(self):
        curve = [[0., 0., 0.], [.1, 0., 0.], [1., 0., 0.], [1., 3., 0.]]
        self.assertEqual(sample_curve(curve, 0.), [0., 0., 0.])
        self.assertEqual(sample_curve(curve, 2.), [1., 1., 0.])
        self.assertEqual(sample_curve(curve, 4.), [1., 3., 0.])

    def test_outside_arc_has_no_silent_endpoint_extrapolation(self):
        curve = [[0., 0., 0.], [1., 0., 0.]]
        for s in (-5e-10, 1.+5e-10, math.nan, math.inf):
            with self.subTest(s=s), self.assertRaises(StudioError):
                sample_curve(curve, s)

    def test_collapsed_nonfinite_or_invalid_polylines_have_explicit_refusals(self):
        for curve in ([], [[0., 0., 0.]],
                [[0., 0., 0.], [0., 0., 0.], [1., 0., 0.]],
                [[0., 0., 0.], [math.nan, 0., 0.]],
                [[0., 0.], [1., 0.]]):
            with self.subTest(curve=curve), self.assertRaises(StudioError):
                sample_curve(curve, 0.)


class SourceVolumeConvention(unittest.TestCase):
    def test_unstated_uv_origin_and_translated_source_are_refused(self):
        data, groups, body = source_fixture()
        missing = copy.deepcopy(groups)
        del missing[0]['uv_origin_cm']
        with self.assertRaises(StudioError):
            volume_frames(data, missing, body)
        translated = copy.deepcopy(data)
        for piece in translated['pieces'].values():
            for point in piece['vertices']:
                point[0] += 10.
        before = digest(translated)
        with self.assertRaises(StudioError):
            volume_frames(translated, groups, body)
        self.assertEqual(digest(translated), before)

    def test_raw_source_girth_is_preserved_separately_from_smoothed_guide(self):
        data, groups, body = source_fixture()
        data['pieces']['front'] = {'vertices': [[0., 0.], [4., 0.], [8., 5.], [4., 10.], [0., 10.]],
            'edges': {'hem': [0, 1], 'center': [0, 4], 'side': [1, 2, 3]}}
        before = digest([data, groups, body])
        panels, report = volume_frames(data, groups, body, guide_smoothing_cm=40.)
        self.assertEqual(digest([data, groups, body]), before)
        self.assertEqual(report['status'], 'UNQUALIFIED_PLACEMENT_HYPOTHESIS')
        self.assertFalse(report['source_uv_scaled'])
        self.assertFalse(report['body_changed'])
        rows = report['sections']
        for row in rows:
            v = row['source_v_cm']
            expected = 10.+.8*min(v, 10.-v)
            self.assertAlmostEqual(row['raw_source']['half_girth_cm'], expected)
            self.assertIn('side_arc_offset_cm', row['raw_source'])
            self.assertIn('side_arc_offset_cm', row['applied_guide'])
            curve = next(s['curve_cm'] for s in panels['front']['arc_sections'] if s['v_cm'] == row['v_cm'])
            emitted_length = sum(math.dist(a, b) for a, b in zip(curve, curve[1:]))
            self.assertAlmostEqual(emitted_length-2., row['applied_guide']['half_girth_cm'], places=8)
        self.assertTrue(any(abs(r['raw_source']['half_girth_cm']-r['applied_guide']['half_girth_cm']) > 1e-6 for r in rows))


class VolumeMetricChecks(unittest.TestCase):
    def test_extruded_guide_preserves_arc_metric_but_longitudinal_stretch_is_refused(self):
        payload, plan = example()
        # Two congruent sections extruded 2 cm along the normal axis preserve
        # the continuous metric. Triangles retain their measured chord error.
        for pid, offset in (('left', 0.), ('right', 2.3)):
            plan['preform']['panels'][pid] = {'source_ref': 'fixture:metric-guide',
                'arc_sections': [{'v_cm': v, 'arc_offset_cm': offset,
                    'curve_cm': half_ellipse(20., 1.3, [0., 0.], v, 1)} for v in (0., 2.)]}
        source_before = digest(payload)
        coords, _ = preform_coordinates(payload, plan)
        statistics = preparation_statistics(payload, coords=coords)
        self.assertGreater(statistics['extrema']['min_principal_stretch']['value'], .99)
        self.assertAlmostEqual(statistics['extrema']['max_principal_stretch']['value'], 1.)
        stretched = copy.deepcopy(plan)
        for frame in stretched['preform']['panels'].values():
            for p in frame['arc_sections'][1]['curve_cm']:
                p[2] = 2.8
        with self.assertRaises(StudioError) as caught:
            preform_coordinates(payload, stretched)
        rejected = preparation_statistics(payload, coords=caught.exception.preform_coordinates_cm)
        self.assertAlmostEqual(rejected['extrema']['max_principal_stretch']['value'], 1.4)
        self.assertEqual(digest(payload), source_before)


if __name__ == '__main__':
    unittest.main()
