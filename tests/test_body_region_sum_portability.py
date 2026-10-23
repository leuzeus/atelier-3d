"""Sensitive measured contours, portable only; no anatomical or fitting admission."""
import copy
import math
import unittest

from a3d.body_region_sections import _hand, _ordered_perimeter_sum, _section
from a3d.core import digest


def prism(count):
    polygon = [[(6.+(i%3)*.17)*math.cos(2*math.pi*i/count),
                (6.+(i%3)*.17)*math.sin(2*math.pi*i/count)] for i in range(count)]
    vertices = [[x,y,z] for z in (-1.,1.) for x,y in polygon]
    faces = [[i,(i+1)%count,(i+1)%count+count,i+count] for i in range(count)]
    triangles = [triangle for a,b,c,d in faces for triangle in ([a,b,c],[a,c,d])]
    return vertices, faces, triangles


class BodyRegionSumPortability(unittest.TestCase):
    def test_compensation_sensitive_positive_distances_keep_historical_order(self):
        lengths = [1e16,1.,1.,1.]
        self.assertEqual(_ordered_perimeter_sum(iter(lengths)), 1e16)
        self.assertNotEqual(_ordered_perimeter_sum(iter(lengths)), math.fsum(lengths))

    def test_true_section_preserves_sensitive_historical_girth_exactly(self):
        vertices, _, triangles = prism(8)
        before = digest([vertices,triangles])
        row = _section(vertices,triangles,list(range(len(triangles))),[0.,0.,0.],
                       [0.,0.,1.],[1.,0.,0.],[0.,1.,0.],1e-6)
        self.assertTrue(row['ok']); self.assertEqual(row['status'], 'MEASURED')
        self.assertEqual(row['girth_cm'], float.fromhex('0x1.2d7ae60ba7344p+5'))
        curve = row['curve_cm']
        lengths = [math.dist(a,b) for a,b in zip(curve,curve[1:]+curve[:1])]
        self.assertNotEqual(row['girth_cm'], math.fsum(lengths))
        self.assertEqual(len(curve),16)
        self.assertEqual(before,digest([vertices,triangles]))

    def test_whole_hand_hull_preserves_sensitive_historical_perimeter_exactly(self):
        vertices, faces, _ = prism(7)
        wrist = {'point_cm':[0.,0.,-1.], 'source_ref':'synthetic:wrist'}
        geometry = {'vertices_cm':vertices,'faces':faces,'face_sets':[1]*len(faces),
                    'rig_landmarks':{'wrist.left':copy.deepcopy(wrist),
                        'hand.left':{'point_cm':[-0.028355096616817312,0.008450159481368655,0.],
                                     'source_ref':'synthetic:hand'}}}
        profile = {'frame':{'origin_cm':[0.,0.,0.],'right':[1.,0.,0.],
                           'forward':[0.,1.,0.],'up':[0.,0.,1.]},
                   'landmarks':{'wrist.left':copy.deepcopy(wrist)}}
        original = copy.deepcopy(geometry)
        adapter = {'source_ref':'synthetic:adapter',
            'source_geometry_sha256':digest([vertices,faces,geometry['face_sets']]),
            'region_to_bone':{'1':'hand.left'},'centers':{'hand.left':[1]}}
        ref = {'path':'synthetic-hand.json','sha256':'a'*64}
        spec = {'hand_source':{'adapter_sha256':digest(adapter),
            'source_geometry_sha256':digest(original),'adapter_ref':ref},
            'budgets':{'max_projection_vertices':100}}
        declaration = {'id':'hand.left','side':'left','plane_reference_axis':'forward','source_ref':ref}
        before = digest([profile,geometry,spec,adapter,original])
        row = _hand(profile,geometry,declaration,spec,adapter,original,1e-6)
        self.assertEqual(row['status'],'CONSERVATIVE_SKIN_PROJECTION_MEASURED')
        self.assertEqual(row['hull_perimeter_cm'],float.fromhex('0x1.2bbe9b4b1c2c3p+5'))
        hull = row['hull_plane_cm']
        self.assertNotEqual(row['hull_perimeter_cm'], math.fsum(
            math.dist(a,b) for a,b in zip(hull,hull[1:]+hull[:1])))
        self.assertEqual(before,digest([profile,geometry,spec,adapter,original]))
        self.assertEqual(row['physical_hand_passage'],'NOT_QUALIFIED')


if __name__ == '__main__': unittest.main()
