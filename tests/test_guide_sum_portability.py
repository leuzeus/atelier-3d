"""Guide coordinates and geometric predicates must have explicit float sums."""
import copy
import math
import unittest
from unittest.mock import patch

from a3d import contact_geometry, pattern_assembly, preform_volume
from a3d.core import digest
from tests.test_anatomy_sum_portability import compensated_sum, legacy_sum
from tests import test_preform_volume as volume_fixtures


class GuideSumPortability(unittest.TestCase):
    def test_half_ellipse_normalization_preserves_exact_points_when_builtin_sum_changes(self):
        parameters = {'half_perimeter': 61.125, 'aspect': 1.37,
                      'center_xy': [2.125, -3.75], 'z': 83.0625}
        before = digest(parameters)
        # These are the actual 256 unscaled segments used by the old
        # normalizer. Its builtin float sum demonstrably changed the scale.
        base = [[parameters['aspect']*math.sin(math.pi*i/256),
                 -math.cos(math.pi*i/256)] for i in range(257)]
        lengths = [preform_volume.length(a, b) for a, b in zip(base, base[1:])]
        old_totals = [accumulate(lengths) for accumulate in (legacy_sum, compensated_sum)]
        self.assertNotEqual(*old_totals)
        old_scales = [parameters['half_perimeter']/total for total in old_totals]
        old_curves = [[[parameters['center_xy'][0]+scale*x,
                        parameters['center_xy'][1]+scale*y, parameters['z']]
                       for x, y in base] for scale in old_scales]
        self.assertNotEqual(old_curves[0], old_curves[1])
        self.assertNotEqual(digest(old_curves[0]), digest(old_curves[1]))

        for side in (-1, 1):
            with self.subTest(side=side):
                curves = []
                for accumulate in (legacy_sum, compensated_sum):
                    with patch.object(preform_volume, 'sum', side_effect=accumulate, create=True):
                        curves.append(preform_volume.half_ellipse(**parameters, side=side))
                self.assertEqual(curves[0], curves[1])
                self.assertEqual(digest(curves[0]), digest(curves[1]))
                curve = curves[0]
                self.assertEqual(len(curve), 257)
                self.assertTrue(all(point[2] == parameters['z'] for point in curve))
                self.assertEqual(curve[0][0], parameters['center_xy'][0])
                self.assertGreater(side*(curve[128][0]-parameters['center_xy'][0]), 0.)
                # Independent measurement of emitted, translated 3D points;
                # this bound concerns floating arithmetic in the test only.
                measured = math.fsum(math.dist(a, b) for a, b in zip(curve, curve[1:]))
                self.assertLessEqual(abs(measured-parameters['half_perimeter']),
                                     32*math.ulp(parameters['half_perimeter']))
        self.assertEqual(before, digest(parameters))

    def test_real_source_volume_producer_keeps_identity_and_does_not_mutate_patterns(self):
        data, groups, body = volume_fixtures.source_fixture()
        body['aspect_ratio'] = 1.37
        body['center_xy_cm'] = [2.125, -3.75]
        before = digest([data, groups, body])
        results = []
        for accumulate in (legacy_sum, compensated_sum):
            with patch.object(preform_volume, 'sum', side_effect=accumulate, create=True):
                results.append(preform_volume.volume_frames(data, groups, body))
        self.assertEqual(results[0], results[1])
        self.assertEqual(digest(results[0]), digest(results[1]))
        self.assertEqual(before, digest([data, groups, body]))
        panels, report = results[0]
        self.assertEqual(set(panels), set(data['pieces']))
        self.assertEqual(report['status'], 'UNQUALIFIED_PLACEMENT_HYPOTHESIS')
        self.assertFalse(report['source_uv_scaled'])
        self.assertFalse(report['body_changed'])
        for section in report['sections']:
            self.assertEqual(section['raw_source']['half_girth_cm'], 10.)
            curve = next(row['curve_cm'] for row in panels['front']['arc_sections']
                         if row['v_cm'] == section['v_cm'])
            measured = math.fsum(math.dist(a, b) for a, b in zip(curve, curve[1:]))
            self.assertLessEqual(abs(measured-12.), 32*math.ulp(12.))

        changed = copy.deepcopy(data)
        for point in changed['pieces']['front']['vertices']:
            if point[0] == 4.:
                point[0] = 4.25
        changed_before = digest(changed)
        changed_panels, changed_report = preform_volume.volume_frames(changed, groups, body)
        self.assertNotEqual(digest(panels), digest(changed_panels))
        self.assertTrue(all(row['raw_source']['half_girth_cm'] == 10.25
                            for row in changed_report['sections']))
        self.assertEqual(changed_before, digest(changed))
        self.assertEqual(before, digest([data, groups, body]))

    def test_contact_dot_retains_small_residual_after_large_cancellation(self):
        a, b = [1e16, 1., -1e16], [1., 1., 1.]
        before = digest([a, b])
        products = [x*y for x, y in zip(a, b)]
        self.assertEqual(legacy_sum(products), 0.)
        self.assertEqual(compensated_sum(products), 1.)
        for accumulate in (legacy_sum, compensated_sum):
            with self.subTest(accumulation=accumulate.__name__), \
                    patch.object(contact_geometry, 'sum', side_effect=accumulate, create=True):
                self.assertEqual(contact_geometry.dot(a, b), 1.)
                self.assertEqual(contact_geometry.dot(b, a), 1.)
        self.assertEqual(before, digest([a, b]))

    def test_compiled_cage_retains_cancellation_residual_with_existing_barycentric_weights(self):
        frame = {'uv_cm': [[0., 0.], [3., 0.], [0., 3.]],
                 'target_cm': [[1e16, 0., 0.], [1., 3., 0.], [-1e16, 0., 3.]],
                 'triangles': [[0, 1, 2]]}
        source_uv = [1., 1.]
        before = digest([frame, source_uv])
        results = []
        for accumulate in (legacy_sum, compensated_sum):
            with patch.object(pattern_assembly, 'sum', side_effect=accumulate, create=True):
                compiled = pattern_assembly._compile_cage(frame, 'arithmetic-fixture')
                results.append(pattern_assembly._cage_point(frame, compiled, source_uv,
                                                            'arithmetic-fixture'))
        self.assertEqual(results[0], results[1])
        self.assertEqual(digest(results[0]), digest(results[1]))
        point, binding = results[0]
        # The mathematical barycentre has thirds. Keep the existing binary
        # weights exactly, including the first weight's rounding difference.
        # The two large products consequently differ by exactly 1.5;
        # their compensated residual plus the small product is 11/6.
        weights = [1.-1./3.-1./3., 1./3., 1./3.]
        self.assertEqual(binding, {'cage_triangle': 0, 'barycentric_weights': weights})
        products = [weight*frame['target_cm'][i][0] for i, weight in enumerate(weights)]
        self.assertEqual(products[0]+products[2], 1.5)
        self.assertEqual(legacy_sum(products), 2.)
        self.assertEqual(compensated_sum(products), 11./6.)
        self.assertEqual(point, [11./6., 1., 1.])
        self.assertEqual(before, digest([frame, source_uv]))


if __name__ == '__main__':
    unittest.main()
