"""Source material orientation must not inherit arbitrary body-edge cycle order."""
import copy
import math
import unittest

from a3d.anatomical_placement import path_frames
from a3d.core import StudioError, digest
from a3d.garment_guides import anatomical_band_frame
from tests.test_anatomical_garment_guides import band_fixture


class AnatomicalBandDirection(unittest.TestCase):
    def test_default_and_positive_direction_reproduce_existing_targets(self):
        piece, policy, profile, references = band_fixture()
        policy['path_anchor_fraction'] = .23
        old, report = anatomical_band_frame(piece, policy, profile, references, 'band')
        explicit = dict(policy, path_direction=1)
        current, current_report = anatomical_band_frame(piece, explicit, profile, references, 'band')
        self.assertEqual(old, current)
        self.assertEqual(report, current_report)
        self.assertEqual(report['path_direction'], 1)

    def test_negative_direction_follows_reverse_arclength_without_changing_anchor_or_source(self):
        piece, policy, profile, references = band_fixture()
        policy.update(path_anchor_fraction=.23, path_direction=-1)
        before = digest([piece, policy, profile, references])
        cage, report = anatomical_band_frame(piece, policy, profile, references, 'band')
        points = references['paths']['chosen']['points_body_cm']
        width = max(v[0] for v in piece['vertices'])
        expected = path_frames(points, [(.23-u/width) % 1 for u, v in cage['uv_cm']],
                               closed=True, reference_normal=[0., 0., 1.])
        for (u, v), actual, frame in zip(cage['uv_cm'], cage['target_cm'], expected):
            target = [frame['point_cm'][k]+v*frame['normal'][k] for k in range(3)]
            self.assertLess(math.dist(actual, target), 1e-9)
        positive, _ = anatomical_band_frame(piece, dict(policy, path_direction=1), profile, references, 'band')
        anchor_indices = [i for i, (u, v) in enumerate(cage['uv_cm']) if u == 0 and v == 0]
        self.assertTrue(anchor_indices)
        for index in anchor_indices:
            self.assertEqual(cage['target_cm'][index], positive['target_cm'][index])
        self.assertNotEqual(cage['target_cm'], positive['target_cm'])
        self.assertEqual(report['path_direction'], -1)
        self.assertEqual(digest([piece, policy, profile, references]), before)

    def test_reversed_direction_is_covariant_in_rotated_body_and_material_v(self):
        piece, policy, profile, references = band_fixture()
        policy.update(path_anchor_fraction=.37, path_direction=-1)
        base, _ = anatomical_band_frame(piece, policy, profile, references, 'band')
        for rotated, axis in ((True, 'u'), (False, 'v')):
            part, other_policy, other_profile, other_refs = band_fixture(rotated=rotated, axis=axis)
            other_policy.update(path_anchor_fraction=.37, path_direction=-1)
            cage, _ = anatomical_band_frame(part, other_policy, other_profile, other_refs, 'band')
            expected = {(round(u, 9), round(v, 9)): point
                        for (u, v), point in zip(base['uv_cm'], base['target_cm'])}
            for uv, actual in zip(cage['uv_cm'], cage['target_cm']):
                u, v = uv if axis == 'u' else reversed(uv)
                p = expected[round(u, 9), round(v, 9)]
                target = [20+p[2], -7+p[0], 53+p[1]] if rotated else p
                self.assertLess(math.dist(actual, target), 1e-9)

    def test_invalid_direction_is_refused_without_mutating_inputs(self):
        for bad in (True, False, 0, 2, -2, 1., -1., float('nan'), float('inf'), None, 'reverse'):
            with self.subTest(direction=bad):
                piece, policy, profile, references = band_fixture()
                policy['path_direction'] = bad
                original = copy.deepcopy([piece, profile, references])
                with self.assertRaisesRegex(StudioError, 'direction'):
                    anatomical_band_frame(piece, policy, profile, references, 'band')
                self.assertEqual([piece, profile, references], original)


if __name__ == '__main__':
    unittest.main()
