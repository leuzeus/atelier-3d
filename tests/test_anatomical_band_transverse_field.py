"""Explicit continuous transverse fields retain measured path and material fibres."""
import copy
import math
import unittest

from a3d.anatomical_placement import path_frames
from a3d.core import StudioError, digest
from a3d.garment_guides import anatomical_band_frame
from tests.test_anatomical_garment_guides import band_fixture


class AnatomicalBandTransverseField(unittest.TestCase):
    def test_historical_frames_and_band_targets_are_exactly_preserved(self):
        points = [[0., 0., 0.], [1., 0., .5], [1., 1., 0.], [0., 1., 0.]]
        args = dict(closed=True, reference_normal=[0., 0., 1.])
        old = path_frames(points, [0., .1, .5, 1.], **args)
        self.assertEqual(old, path_frames(points, [0., .1, .5, 1.],
                         transverse_field='SEGMENT_ORTHOGONAL_V1', **args))
        piece, policy, profile, refs = band_fixture()
        cage, report = anatomical_band_frame(piece, policy, profile, refs, 'sample')
        current, explicit = anatomical_band_frame(piece, dict(policy, transverse_field='SEGMENT_ORTHOGONAL_V1'),
                                                  profile, refs, 'sample')
        self.assertEqual(cage, current)
        self.assertNotIn('transverse_field', report)
        self.assertEqual(explicit.pop('transverse_field'), 'SEGMENT_ORTHOGONAL_V1')
        self.assertEqual(report, explicit)

    def test_constant_field_is_continuous_at_every_corner_including_closed_seam(self):
        points = [[0., 0., 0.], [1., 0., .5], [1., 1., 0.], [0., 1., 0.]]
        original = copy.deepcopy(points)
        lengths = [math.dist(a, b) for a, b in zip(points, points[1:]+points[:1])]
        total = math.fsum(lengths); cumulative = 0.
        for length in lengths:
            fraction = cumulative/total
            samples = [(fraction-1e-8) % 1, (fraction+1e-8) % 1]
            rows = path_frames(points, samples, closed=True, reference_normal=[0., 0., 4.],
                               transverse_field='BODY_DIRECTION_CONSTANT_V1')
            targets = [[r['point_cm'][k]+7*r['normal'][k] for k in range(3)] for r in rows]
            self.assertLessEqual(math.dist(*targets), 2e-8*total+1e-12)
            for row, target in zip(rows, targets):
                self.assertAlmostEqual(math.dist(row['point_cm'], target), 7., places=12)
                self.assertEqual(row['normal'], [0., 0., 1.])
            cumulative += length
        endpoints = path_frames(points, [0., 1.], closed=True, reference_normal=[0., 0., 1.],
                                transverse_field='BODY_DIRECTION_CONSTANT_V1')
        self.assertEqual(endpoints[0], endpoints[1])
        self.assertEqual(points, original)

    def test_band_preserves_base_fibres_rotation_direction_and_material_axis(self):
        for sign in (1, -1):
            for rotated in (False, True):
                for axis in ('u', 'v'):
                    with self.subTest(sign=sign, rotated=rotated, axis=axis):
                        piece, policy, profile, refs = band_fixture(rotated=rotated, axis=axis)
                        policy.update(path_direction=sign, path_anchor_fraction=.17)
                        original, _ = anatomical_band_frame(piece, policy, profile, refs, 'sample')
                        policy['transverse_field'] = 'BODY_DIRECTION_CONSTANT_V1'
                        before = digest([piece, policy, profile, refs])
                        cage, report = anatomical_band_frame(piece, policy, profile, refs, 'sample')
                        self.assertEqual(cage['uv_cm'], original['uv_cm'])
                        self.assertEqual(cage['triangles'], original['triangles'])
                        along = 0 if axis == 'u' else 1; across = 1-along
                        basis = profile['frame']; expected = [basis['up'][k] for k in range(3)]
                        for uv, target, old in zip(cage['uv_cm'], cage['target_cm'], original['target_cm']):
                            if uv[across] == 0.: self.assertEqual(target, old)
                        pairs = {}
                        for uv, target in zip(cage['uv_cm'], cage['target_cm']):
                            pairs.setdefault(round(uv[along], 12), []).append((uv[across], target))
                        for rows in pairs.values():
                            rows.sort(); low, high = rows[0], rows[-1]
                            for k in range(3):
                                self.assertAlmostEqual(high[1][k]-low[1][k],
                                                       (high[0]-low[0])*expected[k], places=10)
                        self.assertEqual(report['transverse_field'], 'BODY_DIRECTION_CONSTANT_V1')
                        self.assertEqual(digest([piece, policy, profile, refs]), before)

    def test_unknown_field_or_parallel_direction_is_refused_without_mutation(self):
        for mode in (None, True, 1, [], {}, 'auto', 'constant'):
            piece, policy, profile, refs = band_fixture()
            original = copy.deepcopy([piece, profile, refs]); policy['transverse_field'] = mode
            with self.subTest(mode=mode), self.assertRaisesRegex(StudioError, 'transverse field'):
                anatomical_band_frame(piece, policy, profile, refs, 'sample')
            self.assertEqual([piece, profile, refs], original)
        with self.assertRaisesRegex(StudioError, 'parallel'):
            path_frames([[0., 0., 0.], [0., 0., 1.]], [.5], closed=False,
                        reference_normal=[0., 0., 1.], transverse_field='BODY_DIRECTION_CONSTANT_V1')
        for direction in ([0., 0., 0.], [0., 0., math.inf], [True, 0., 1.]):
            with self.assertRaises(StudioError):
                path_frames([[0., 0., 0.], [1., 0., 0.]], [.5], closed=False,
                            reference_normal=direction, transverse_field='BODY_DIRECTION_CONSTANT_V1')


if __name__ == '__main__': unittest.main()
