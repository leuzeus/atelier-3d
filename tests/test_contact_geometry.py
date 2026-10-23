import math
import random
import unittest

from a3d.core import StudioError
from a3d.contact_geometry import triangle_contact,TriangleBVH,bounds_distance_sq,separated_projection


class ContactGeometry(unittest.TestCase):
    def test_coplanar_containment_and_disjoint_triangles(self):
        a=[[0,0,0],[4,0,0],[0,4,0]]
        b=[[.2,.2,0],[.8,.2,0],[.2,.8,0]]
        self.assertEqual(triangle_contact(a,b)['kind'],'COPLANAR_OVERLAP')
        c=[[5,0,0],[6,0,0],[5,1,0]]
        contact=triangle_contact(a,c)
        self.assertEqual(contact['kind'],'SEPARATED')
        self.assertAlmostEqual(contact['distance_cm'],1.)

    def test_transverse_intersection_is_not_a_distance_only_near_miss(self):
        a=[[-2,-2,0],[2,-2,0],[0,2,0]]
        b=[[0,-1,-1],[0,1,-1],[0,0,1]]
        contact=triangle_contact(a,b)
        self.assertEqual(contact['kind'],'TRANSVERSE_INTERSECTION')
        self.assertLess(contact['distance_cm'],1e-12)

    def test_separated_layers_have_face_distance_and_translation_invariance(self):
        a=[[0,0,0],[4,0,0],[0,4,0]]
        b=[[.2,.2,.125],[.8,.2,.125],[.2,.8,.125]]
        contact=triangle_contact(a,b)
        self.assertAlmostEqual(contact['distance_cm'],.125)
        self.assertEqual(contact['kind'],'SEPARATED')
        delta=[101.7,-223.1,97.4]
        translated=triangle_contact([[p[k]+delta[k] for k in range(3)] for p in a],
                                    [[p[k]+delta[k] for k in range(3)] for p in b])
        self.assertAlmostEqual(translated['distance_cm'],.125)

    def test_tangent_shared_point_does_not_become_transverse_crossing(self):
        a=[[0,0,0],[1,0,0],[0,1,0]]
        b=[[0,0,0],[0,-1,1],[-1,0,1]]
        self.assertEqual(triangle_contact(a,b)['kind'],'TOUCHING')

    def test_degenerate_and_nonfinite_geometry_refuses(self):
        regular=[[0,0,0],[1,0,0],[0,1,0]]
        for bad in ([[0,0,0],[1,0,0],[2,0,0]],[[0,0,0],[math.nan,0,0],[0,1,0]]):
            with self.assertRaises(StudioError):triangle_contact(regular,bad)

    def test_aabb_bvh_coplanar_distance_pairs_equal_brute_force_after_shuffle(self):
        rng=random.Random(7023)
        triangles=[]
        for _ in range(55):
            x,y=rng.randrange(10),rng.randrange(10)
            triangles.append([[x,y,0],[x+1.2,y,0],[x,y+1.2,0]])
        rng.shuffle(triangles)
        tree=TriangleBVH(triangles)
        actual=list(tree.pairs(tree,.15,same=True))
        expected={(i,j) for i in range(len(triangles)) for j in range(i+1,len(triangles))
                  if bounds_distance_sq(tree.bounds[i],tree.bounds[j])<=.15**2}
        self.assertEqual(len(actual),len(set(actual)))
        self.assertEqual(set(actual),expected)

    def test_separating_projection_never_discards_contacts_in_seeded_variants(self):
        rng=random.Random(981)
        for _ in range(80):
            a=[[rng.uniform(-2,2) for _ in range(3)] for _ in range(3)]
            b=[[rng.uniform(-2,2) for _ in range(3)] for _ in range(3)]
            distance=triangle_contact(a,b)['distance_cm']
            for margin in (0.,.1,.5):
                if separated_projection(a,b,margin):self.assertGreater(distance,margin-1e-9)

    def test_closed_volume_winding_is_checked_per_connected_component(self):
        from blender.cloth_contacts import _closed_orientation
        coords=[[0.,0.,0.],[1.,0.,0.],[0.,1.,0.],[0.,0.,1.]]
        faces=[[0,2,1],[0,1,3],[0,3,2],[1,2,3]]
        def check(points,triangles):
            uses={}
            for index,face in enumerate(triangles):
                for a,b in zip(face,face[1:]+face[:1]):
                    uses.setdefault(tuple(sorted((a,b))),[]).append((a,b,index))
            return _closed_orientation(points,triangles,uses)
        self.assertEqual(check(coords,faces),(True,[]))
        flipped=[list(reversed(faces[0]))]+faces[1:]
        self.assertEqual(check(coords,flipped)[1][0]['reason'],'INCONSISTENT_CLOSED_WINDING')
        # The positive volume of the larger first shell must not hide a second
        # inward shell; the body is preserved and its context is refused.
        both=[[v*3 for v in p] for p in coords]+[[p[0]+5,p[1],p[2]] for p in coords]
        mixed=faces+[[i+4 for i in reversed(face)] for face in faces]
        issues=check(both,mixed)[1]
        self.assertEqual(len(issues),1)
        self.assertEqual(issues[0]['reason'],'NONPOSITIVE_ORIENTED_VOLUME')
        self.assertEqual(issues[0]['first_triangle'],4)


if __name__=='__main__':unittest.main()
