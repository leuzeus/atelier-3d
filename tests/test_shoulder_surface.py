import copy
import unittest

from a3d.core import StudioError, digest
from a3d.shoulder_surface import measured_surface_shoulders, surface_anchors


def fixture():
    vertices = [[x,y,z] for z in (0.,100.) for y in (-10.,10.) for x in (-20.,20.)]
    faces = [[0,2,3,1],[4,5,7,6],[0,1,5,4],[2,6,7,3],[0,4,6,2],[1,3,7,5]]
    triangles = [t for a,b,c,d in faces for t in ([a,b,c],[a,c,d])]
    geometry = {'vertices_cm':vertices,'faces':faces,'source_sha256':'a'*64,'pose_sha256':digest(vertices)}
    profile = {'geometry_sha256':digest([vertices,faces]),'source_sha256':'a'*64,
               'pose_sha256':geometry['pose_sha256'], 'cache_key':'original-profile', 'stature_cm':100.,
               'frame':{'origin_cm':[0.,0.,0.],'right':[-1.,0.,0.], 'forward':[0.,-1.,0.],'up':[0.,0.,1.]},
               'landmarks':{f'shoulder.{side}':{'point_cm':[x,0.,95.]} for side,x in [('left',-10.),('right',10.)]}}
    return profile,geometry,triangles


class SurfaceShoulders(unittest.TestCase):
    def test_skin_exit_determinism_no_mutation_and_cache_binding(self):
        profile,geometry,triangles = fixture(); before = digest([profile,geometry,triangles])
        result = measured_surface_shoulders(profile,geometry,triangles)
        self.assertEqual(result, measured_surface_shoulders(profile,geometry,triangles))
        self.assertEqual(surface_anchors(result), {'left':[-10.,0.,100.], 'right':[10.,0.,100.]})
        self.assertEqual(result['landmarks']['shoulder.left']['point_cm'][2],95.)
        self.assertEqual(result['landmarks']['shoulder.surface.left']['distance_from_joint_cm'],5.)
        self.assertNotEqual(result['cache_key'],profile['cache_key'])
        self.assertEqual(before,digest([profile,geometry,triangles]))
        for key in ('geometry_sha256','pose_sha256','cache_key'):
            changed = copy.deepcopy(result); changed[key]='changed'
            with self.subTest(key=key), self.assertRaises(StudioError): surface_anchors(changed)
        changed = copy.deepcopy(result); changed['landmarks']['shoulder.surface.left']['point_cm'][2]=99.
        with self.assertRaises(StudioError): surface_anchors(changed)
        changed = copy.deepcopy(result); changed['frame']['origin_cm'][2] += 25.
        with self.assertRaises(StudioError): surface_anchors(changed)

    def test_refuses_old_body_pose_joint_only_or_external_joint(self):
        profile,geometry,triangles = fixture()
        with self.assertRaises(StudioError): surface_anchors(profile)
        for key in ('pose_sha256','source_sha256'):
            changed = dict(geometry); changed[key]='b'*64
            with self.subTest(key=key), self.assertRaises(StudioError):
                measured_surface_shoulders(profile,changed,triangles)
        for point in ([30.,0.,95.],[10.,0.,105.],[10.,0.,80.]):
            changed = copy.deepcopy(profile); changed['landmarks']['shoulder.left']['point_cm']=point
            with self.subTest(point=point), self.assertRaises(StudioError):
                measured_surface_shoulders(changed,geometry,triangles)

    def test_refuses_incomplete_cross_face_or_open_surface(self):
        profile,geometry,triangles = fixture()
        for invalid in (triangles[2:4], [[0,3,5]]+triangles, triangles+[triangles[0]],
                        [triangles[0][::-1]]+triangles[1:]):
            with self.subTest(triangles=invalid), self.assertRaises(StudioError):
                measured_surface_shoulders(profile,geometry,invalid)
        geometry['faces'] = geometry['faces'][1:]
        profile['geometry_sha256'] = digest([geometry['vertices_cm'],geometry['faces']])
        with self.assertRaises(StudioError): measured_surface_shoulders(profile,geometry,triangles[2:])
