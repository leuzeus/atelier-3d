import copy
import math
import unittest

from a3d.body_dimensions import variant_by_stature
from a3d.core import StudioError, digest
from tests.test_anatomy_profile import cylinder


def fixture(height=160.):
    points, faces = cylinder(radius=12., height=height)
    geometry = {'vertices_cm': [[x+5., y-7., z+11.] for x, y, z in points],
                'faces': faces, 'source_sha256': 'a'*64, 'pose_sha256': 'b'*64,
                'rig_landmarks': {'head.center': {'point_cm': [5., -7., 11.+height*.92],
                                                   'source_ref': 'evaluated-head'}}}
    options = {'up_axis': [0., 0., 1.], 'forward_axis': [0., 1., 0.],
               'origin_cm': [5., -7., 3.], 'torso_seed_xy_cm': [0., 0.],
               'section_count': 24, 'torso_faces': list(range(len(faces))),
               'segmentation_source_ref': 'actual-cylinder-faces'}
    return geometry, options


class BodyDimensions(unittest.TestCase):
    def test_exact_stature_source_floor_and_uniform_measured_girths(self):
        geometry, options = fixture(); before = digest([geometry, options])
        result = variant_by_stature(geometry, options, 180.)
        report = result['receipt']; output = result['geometry']
        self.assertAlmostEqual(result['profile']['stature_cm'], 180., places=10)
        self.assertAlmostEqual(report['uniform_factor'], 1.125)
        self.assertEqual(report['source_floor_cm'], report['measured_floor_cm'])
        self.assertEqual(min(point[2] for point in output['vertices_cm']), 11.)
        self.assertEqual(output['faces'], geometry['faces'])
        self.assertEqual(output['source_sha256'], geometry['source_sha256'])
        self.assertNotEqual(output['pose_sha256'], geometry['pose_sha256'])
        self.assertEqual(report['qualification'], 'HEIGHT_ONLY')
        self.assertEqual(report['girth_targets'], 'NOT_REQUESTED')
        self.assertIn('FITTING', report['prior_evidence_invalidated'])
        self.assertEqual(report['fitting'], 'NOT_EXECUTED')
        expected_girth = 32*2*12*math.sin(math.pi/32)*1.125
        self.assertAlmostEqual(report['measured_girths_cm']['chest'], expected_girth, places=3)
        self.assertAlmostEqual(output['rig_landmarks']['head.center']['point_cm'][2], 11.+180.*.92)
        self.assertEqual(digest([geometry, options]), before)
        output['vertices_cm'][0][0] = 900.
        output['faces'][0][0] = 9
        self.assertEqual(digest([geometry, options]), before)

    def test_rotated_declared_frame_measures_height_along_actual_up(self):
        geometry, options = fixture()
        # A 90 degree rotation about X makes world Y the height dimension.
        rotate = lambda p: [p[0], -p[2], p[1]]
        geometry['vertices_cm'] = [rotate(point) for point in geometry['vertices_cm']]
        geometry['rig_landmarks']['head.center']['point_cm'] = rotate(geometry['rig_landmarks']['head.center']['point_cm'])
        options.update(up_axis=[0., -1., 0.], forward_axis=[0., 0., 1.],
                       origin_cm=rotate(options['origin_cm']))
        result = variant_by_stature(geometry, options, 180.)
        vertices = result['geometry']['vertices_cm']
        self.assertAlmostEqual(max(p[1] for p in vertices)-min(p[1] for p in vertices), 180.)
        self.assertEqual(max(p[1] for p in vertices), -11.)
        self.assertAlmostEqual(result['profile']['stature_cm'], 180.)
        self.assertAlmostEqual(result['receipt']['measured_floor_cm'], 8.)

    def test_native_region_guide_structured_reference_stays_source_bound(self):
        geometry, options = fixture()
        reference = {'path': 'assets/mannequins/original-body.blend', 'sha256': 'a'*64}
        geometry['rig_landmarks']['head.center']['source_ref'] = reference
        result = variant_by_stature(geometry, options, 180.)
        transformed = result['geometry']['rig_landmarks']['head.center']
        self.assertEqual(result['receipt']['source_rig_landmark_references']['head.center'], reference)
        self.assertEqual(result['geometry']['dimension_derivation']['source_rig_landmark_references']['head.center'], reference)
        self.assertTrue(transformed['source_ref'].endswith(':'+digest(reference)))
        self.assertEqual(geometry['rig_landmarks']['head.center']['source_ref'], reference)
        for invalid in ({}, {'path': '../outside.blend', 'sha256': 'a'*64},
                        {'path': 'source.blend', 'sha256': 'bad'},
                        dict(reference, extra='unreviewed')):
            source = copy.deepcopy(geometry)
            source['rig_landmarks']['head.center']['source_ref'] = invalid
            with self.subTest(reference=invalid), self.assertRaises(StudioError):
                variant_by_stature(source, options, 180.)

    def test_deterministic_source_bound_cache_and_explicit_seed_transform(self):
        geometry, options = fixture(); options['torso_seed_xy_cm'] = [1., .5]
        first = variant_by_stature(geometry, options, 180.)
        self.assertEqual(first, variant_by_stature(geometry, options, 180.))
        self.assertEqual(first['options']['torso_seed_xy_cm'], [1.125, .5625])
        for changed in ('target', 'pose', 'source', 'geometry', 'frame'):
            source, config = copy.deepcopy(geometry), copy.deepcopy(options); target = 180.
            if changed == 'target': target = 181.
            if changed == 'pose': source['pose_sha256'] = 'c'*64
            if changed == 'source': source['source_sha256'] = 'd'*64
            if changed == 'geometry': source['vertices_cm'][0][0] += .01
            if changed == 'frame': config['origin_cm'][0] += .1
            with self.subTest(changed=changed):
                result = variant_by_stature(source, config, target)
                self.assertNotEqual(result['receipt']['cache_key'], first['receipt']['cache_key'])
                self.assertNotEqual(result['profile']['cache_key'], first['profile']['cache_key'])

    def test_bad_inputs_are_refused_without_mutation(self):
        failures = ('target_nan', 'target_bool', 'target_low', 'target_high', 'target_string',
                    'vertex_bool', 'vertex_nan', 'face_bool', 'face_range', 'face_duplicate', 'face_unhashable',
                    'hash', 'units', 'up_bool', 'up_zero', 'parallel_axes', 'origin_bool',
                    'rig_bool', 'rig_source', 'seed_bool')
        for failure in failures:
            geometry, options = fixture(); target = 180.
            if failure == 'target_nan': target = math.nan
            if failure == 'target_bool': target = True
            if failure == 'target_low': target = 29.9
            if failure == 'target_high': target = 400.1
            if failure == 'target_string': target = '180'
            if failure == 'vertex_bool': geometry['vertices_cm'][0][0] = True
            if failure == 'vertex_nan': geometry['vertices_cm'][0][0] = math.nan
            if failure == 'face_bool': geometry['faces'][0][0] = True
            if failure == 'face_range': geometry['faces'][0][0] = 100000
            if failure == 'face_duplicate': geometry['faces'][0][0] = geometry['faces'][0][1]
            if failure == 'face_unhashable': geometry['faces'][0][0] = []
            if failure == 'hash': geometry['source_sha256'] = 'invalid'
            if failure == 'units': geometry['vertices_cm'] = [[x/100 for x in p] for p in geometry['vertices_cm']]
            if failure == 'up_bool': options['up_axis'] = [False, False, True]
            if failure == 'up_zero': options['up_axis'] = [0., 0., 0.]
            if failure == 'parallel_axes': options['forward_axis'] = [0., 0., 1.]
            if failure == 'origin_bool': options['origin_cm'][0] = False
            if failure == 'rig_bool': geometry['rig_landmarks']['head.center']['point_cm'][0] = True
            if failure == 'rig_source': geometry['rig_landmarks']['head.center']['source_ref'] = ''
            if failure == 'seed_bool': options['torso_seed_xy_cm'][0] = True
            before = copy.deepcopy([geometry, options])
            with self.subTest(failure=failure), self.assertRaises(StudioError):
                variant_by_stature(geometry, options, target)
            # NaNs cannot compare by value; compare the representation for refusal immutability.
            self.assertEqual(repr([geometry, options]), repr(before))


if __name__ == '__main__':
    unittest.main()
