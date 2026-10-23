import copy
import math
import unittest

from a3d.core import StudioError, digest
from a3d.shoulder_guides import material_plane


class MaterialShoulderFrame(unittest.TestCase):
    def test_preserves_source_distances_for_sloped_and_mirrored_shoulders(self):
        for sign in (-1, 1):
            piece = {'vertices': [[sign*3., 12.], [sign*11., 10.]],
                     'edges': {'approved-shoulder': [0, 1]}}
            before = digest(piece)
            point, report = material_plane(piece, 'approved-shoulder', sign,
                                           [4., 1., 15.], [12., 0., 10.], [0., -5., 8.])
            samples = [(3., 12.), (11., 10.), (5., 9.), (9., 14.)]
            for a in samples:
                for b in samples:
                    self.assertAlmostEqual(math.dist(point(*a), point(*b)), math.dist(a, b), places=10)
            self.assertEqual(point(3., 12.), [4., 1., 15.])
            self.assertEqual(digest(piece), before)
            self.assertAlmostEqual(report['source_shoulder_length_cm'], math.sqrt(68.))

    def test_refuses_curved_collapsed_and_unusable_anatomical_frames(self):
        for points, ridge, joint, chest in [
            ([[0., 0.], [0., 0.]], [0.,0.,0.], [1.,0.,0.], [0.,1.,0.]),
            ([[0., 0.], [1., 1.], [2., 0.]], [0.,0.,0.], [1.,0.,0.], [0.,1.,0.]),
            ([[0., 0.], [2., 0.]], [0.,0.,0.], [0.,0.,0.], [0.,1.,0.]),
            ([[0., 0.], [2., 0.]], [0.,0.,0.], [1.,0.,0.], [2.,0.,0.]),
        ]:
            piece = {'vertices': points, 'edges': {'shoulder': list(range(len(points)))}}
            with self.subTest(points=points), self.assertRaises(StudioError):
                material_plane(piece, 'shoulder', 1, ridge, joint, chest)


if __name__ == '__main__':
    unittest.main()
