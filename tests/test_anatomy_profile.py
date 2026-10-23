import copy
import math
import unittest

from a3d.anatomy_profile import profile_mesh, surface_section
from a3d.core import StudioError, digest


def cylinder(cx=0., radius=15., height=180.):
    vertices = [[cx+radius*math.cos(i*math.tau/32), radius*math.sin(i*math.tau/32), z]
                for z in (0., height) for i in range(32)]
    faces = [[i, (i+1)%32, (i+1)%32+32, i+32] for i in range(32)]
    faces += [list(reversed(range(32))), list(range(32, 64))]
    return vertices, faces


def fixture():
    vertices, faces = cylinder()
    geometry = {'vertices_cm': vertices, 'faces': faces, 'source_sha256': 'a'*64, 'pose_sha256': 'b'*64}
    return geometry, {'up_axis': [0, 0, 1], 'forward_axis': [0, 1, 0], 'section_count': 24}


class AnatomyProfile(unittest.TestCase):
    def test_closed_section_measures_surface_without_source_change(self):
        geometry, options = fixture(); before = digest([geometry, options])
        section = surface_section(geometry['vertices_cm'], geometry['faces'], 90., [0., 0.])
        self.assertEqual(section['status'], 'MEASURED')
        self.assertAlmostEqual(section['girth_cm'], 32*2*15*math.sin(math.pi/32), places=4)
        report = profile_mesh(geometry, options)
        self.assertEqual(report['status'], 'NEEDS_CLARIFICATION')
        self.assertEqual(report['stature_cm'], 180.)
        self.assertIn('waist', report['landmarks'])
        self.assertIn('shoulder.left', report['missing_landmarks'])
        self.assertEqual(report['sex_classification'], 'NOT_PERFORMED')
        self.assertEqual(digest([geometry, options]), before)

    def test_disconnected_limbs_are_excluded_without_bloating_torso_girth(self):
        geometry, _ = fixture(); limb, faces = cylinder(40., 5.)
        n = len(geometry['vertices_cm']); geometry['vertices_cm'] += limb
        geometry['faces'] += [[i+n for i in face] for face in faces]
        section = surface_section(geometry['vertices_cm'], geometry['faces'], 90., [0., 0.])
        self.assertEqual(section['excluded_loops'], 1)
        self.assertLess(section['girth_cm'], 100.)

    def test_open_or_ambiguous_surface_is_not_closed_by_a_hull(self):
        geometry, _ = fixture()
        section = surface_section(geometry['vertices_cm'], geometry['faces'][1:], 90., [0., 0.])
        self.assertEqual(section['status'], 'NOT_QUALIFIED')
        duplicate, faces = cylinder(radius=10.)
        n = len(geometry['vertices_cm']); geometry['vertices_cm'] += duplicate
        geometry['faces'] += [[i+n for i in face] for face in faces]
        self.assertEqual(surface_section(geometry['vertices_cm'], geometry['faces'], 90., [0., 0.])['status'], 'NOT_QUALIFIED')

    def test_pose_options_geometry_and_rig_changes_invalidate_cache(self):
        geometry, options = fixture(); original = profile_mesh(geometry, options)['cache_key']
        for change in ['pose', 'geometry', 'options', 'rig']:
            data, config = copy.deepcopy(geometry), copy.deepcopy(options)
            if change == 'pose': data['pose_sha256'] = 'c'*64
            if change == 'geometry': data['vertices_cm'][0][0] += .01
            if change == 'options': config['section_count'] = 25
            if change == 'rig': data['rig_landmarks'] = {'head.center': {'point_cm': [0., 0., 165.], 'source_ref': 'rig guide'}}
            with self.subTest(change=change):
                self.assertNotEqual(profile_mesh(data, config)['cache_key'], original)

    def test_rig_guides_do_not_replace_mesh_measurements_or_qualify_fitting(self):
        geometry, options = fixture()
        points = {'shoulder.left': [-10., 0., 140.], 'shoulder.right': [10., 0., 140.],
                  'elbow.left': [-12., 0., 110.], 'elbow.right': [12., 0., 110.],
                  'wrist.left': [-14., 0., 85.], 'wrist.right': [14., 0., 85.],
                  'head.center': [0., 0., 165.]}
        geometry['rig_landmarks'] = {name: {'point_cm': point, 'source_ref': 'explicit evaluated rig'}
                                    for name, point in points.items()}
        self.assertEqual(profile_mesh(geometry, options)['status'], 'NEEDS_CLARIFICATION')
        options.update(torso_faces=list(range(len(geometry['faces']))), segmentation_source_ref='synthetic cylinder')
        report = profile_mesh(geometry, options)
        self.assertEqual(report['status'], 'PROFILE_MEASURED')
        self.assertEqual(report['fitting'], 'NOT_EXECUTED')
        self.assertEqual(report['anatomical_review'], 'REQUIRED_BEFORE_FITTING')
        self.assertIn('girth_cm', report['landmarks']['chest'])

    def test_collapsed_outside_and_nonfinite_guides_are_refused(self):
        for failure in ('collapsed', 'outside', 'nonfinite'):
            geometry, options = fixture()
            point = [0., 0., 140.] if failure == 'collapsed' else [1000., 0., 140.]
            if failure == 'nonfinite': point[0] = math.nan
            geometry['rig_landmarks'] = {name: {'point_cm': point, 'source_ref': 'invalid rig'}
                                        for name in ('shoulder.left', 'elbow.left')}
            with self.subTest(failure=failure), self.assertRaises(StudioError):
                profile_mesh(geometry, options)

    def test_wrong_units_invalid_axes_bad_segmentation_and_nonfinite_are_refused(self):
        for failure in ['units', 'axes', 'segmentation', 'nonfinite', 'sampling']:
            geometry, options = fixture()
            if failure == 'units': geometry['vertices_cm'] = [[x/100 for x in p] for p in geometry['vertices_cm']]
            if failure == 'axes': options['forward_axis'] = [0., 0., 1.]
            if failure == 'segmentation': options['torso_faces'] = [-1]
            if failure == 'nonfinite': geometry['vertices_cm'][0][0] = math.nan
            if failure == 'sampling': options['section_count'] = 10000
            with self.subTest(failure=failure), self.assertRaises(StudioError):
                profile_mesh(geometry, options)
