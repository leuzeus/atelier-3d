"""Path-knot material partition is explicit, bounded and source conforming."""
import copy
import math
import time
import unittest

from a3d.cloth_metrics import principal_stretches
from a3d.anatomical_placement import sample_path
from a3d.core import StudioError, digest
from a3d.garment_guides import anatomical_band_frame, _path_knot_partition, _world
from a3d.pattern_assembly import _cage_point, _compile_cage
from a3d.source_seam_coupling import _Budget
from tests.test_anatomical_garment_guides import band_fixture


def area(points):
    a, b, c = points
    return abs((b[0]-a[0])*(c[1]-a[1])-(b[1]-a[1])*(c[0]-a[0]))/2


def partition_fixture(**kwargs):
    piece, policy, profile, refs = band_fixture(**kwargs)
    policy.update(transverse_field='BODY_DIRECTION_CONSTANT_V1', cage_sampling='PATH_KNOT_PARTITION_V1',
                  path_anchor_fraction=.173)
    return piece, policy, profile, refs


class AnatomicalBandPartition(unittest.TestCase):
    def test_declared_partition_preserves_source_area_vertices_faces_boundary_and_cuts(self):
        for axis in ('u', 'v'):
            for sign in (-1, 1):
                with self.subTest(axis=axis, sign=sign):
                    piece, policy, profile, refs = partition_fixture(axis=axis)
                    policy['path_direction'] = sign; before = digest([piece, policy, profile, refs])
                    cage, report = anatomical_band_frame(piece, policy, profile, refs, 'sample')
                    partition = report['path_knot_partition']; along = 0 if axis == 'u' else 1
                    self.assertTrue(set(map(tuple, piece['vertices'])) <= set(map(tuple, cage['uv_cm'])))
                    measured = 0.; edges = {}
                    for triangle, source_id in zip(cage['triangles'], partition['triangle_source_face_indices']):
                        uv = [cage['uv_cm'][i] for i in triangle]; measured += area(uv)
                        self.assertGreater(area(uv), 5e-11)
                        for cut in partition['path_knot_cuts_cm']:
                            self.assertFalse(min(p[along] for p in uv) < cut < max(p[along] for p in uv))
                        self.assertIn(source_id, range(len(piece['faces'])))
                        for a, b in zip(triangle, triangle[1:]+triangle[:1]):
                            key = tuple(sorted((a, b))); edges[key] = edges.get(key, 0)+1
                    self.assertAlmostEqual(measured, sum(area([piece['vertices'][i] for i in t]) for t in piece['faces']), places=10)
                    boundary_length = sum(math.dist(cage['uv_cm'][a], cage['uv_cm'][b]) for (a, b), count in edges.items() if count == 1)
                    source_length = sum(math.dist(a, b) for a, b in zip(piece['vertices'], piece['vertices'][1:]+piece['vertices'][:1]))
                    self.assertAlmostEqual(boundary_length, source_length, places=10)
                    self.assertEqual(set(edges.values()), {1, 2})
                    self.assertEqual(digest([piece, policy, profile, refs]), before)

    def test_constant_band_partition_reproduces_piecewise_affine_map_without_straddling_knots(self):
        piece, policy, profile, refs = partition_fixture()
        cage, report = anatomical_band_frame(piece, policy, profile, refs, 'sample')
        rows = [principal_stretches([cage['uv_cm'][i] for i in t], [cage['target_cm'][i] for i in t])
                for t in cage['triangles']]
        # Exact constant extrusion of the sloped fixture has a bounded shear;
        # this is not the production material gate or a fitting acceptance.
        self.assertGreater(min(r[0] for r in rows), .8)
        self.assertLess(max(r[1] for r in rows), 1.2)
        lookup = {tuple(uv): target for uv, target in zip(cage['uv_cm'], cage['target_cm'])}
        width = max(p[0] for p in piece['vertices'])
        for v in (0., 7.): self.assertLess(math.dist(lookup[(0., v)], lookup[(width, v)]), 1e-12)
        for u in report['path_knot_partition']['path_knot_cuts_cm']:
            self.assertAlmostEqual(math.dist(lookup[(u, 0.)], lookup[(u, 7.)]), 7., places=10)

    def test_partition_is_deterministic_and_covariant_in_rotated_frame(self):
        args = partition_fixture(); first = anatomical_band_frame(*args, 'sample')
        self.assertEqual(first, anatomical_band_frame(*args, 'sample'))
        rotated, report = anatomical_band_frame(*partition_fixture(rotated=True), 'sample')
        self.assertEqual(rotated['uv_cm'], first[0]['uv_cm'])
        self.assertEqual(rotated['triangles'], first[0]['triangles'])
        for a, b in zip(first[0]['target_cm'], rotated['target_cm']):
            self.assertLess(math.dist(b, [20+a[2], -7+a[0], 53+a[1]]), 1e-10)
        reordered = copy.deepcopy(args); reordered[0]['faces'].reverse()
        changed, _ = anatomical_band_frame(*reordered, 'sample')
        self.assertEqual(first[0], changed)

    def test_every_triangle_interior_matches_analytical_map_in_all_frames_and_axes(self):
        for axis in ('u', 'v'):
            for sign in (-1, 1):
                for rotated in (False, True):
                    with self.subTest(axis=axis, sign=sign, rotated=rotated):
                        piece, policy, profile, refs = partition_fixture(axis=axis, rotated=rotated)
                        policy['path_direction'] = sign
                        before = digest([piece, policy, profile, refs])
                        cage, report = anatomical_band_frame(piece, policy, profile, refs, 'sample')
                        compiled = _compile_cage(cage, 'sample')
                        center = report['auxiliary_path_expansion_center_body_cm']
                        scale = report['auxiliary_path_expansion_ratio']
                        path = refs['paths'][policy['path_ref']]['points_body_cm']
                        expanded = [[center[k]+scale*(point[k]-center[k]) for k in range(3)] for point in path]
                        normal = policy['longitudinal_direction_body']
                        normal = [x/math.hypot(*normal) for x in normal]
                        along = 0 if axis == 'u' else 1; across = 1-along
                        anchor = report['source_anchor_uv_cm']
                        width = report['source_circumference_cm']
                        for triangle in cage['triangles']:
                            for weights in ((1/3, 1/3, 1/3), (.2, .3, .5), (.1, .7, .2)):
                                uv = [math.fsum(weight*cage['uv_cm'][index][k]
                                                for weight, index in zip(weights, triangle)) for k in range(2)]
                                fraction = (policy['path_anchor_fraction']+sign*(uv[along]-anchor[along])/width) % 1.
                                base = sample_path(expanded, [fraction], closed=True)[0]
                                expected = _world(profile, [base[k]+(uv[across]-anchor[across])*normal[k]
                                                            for k in range(3)])
                                actual = _cage_point(cage, compiled, uv, 'sample')[0]
                                self.assertLess(math.dist(actual, expected), 1e-10,
                                                msg=f'Interior mismatch in source cage triangle {triangle}, UV {uv}')
                        self.assertEqual(digest([piece, policy, profile, refs]), before)

    def test_default_cage_is_historical_and_explicit_partition_requires_constant_field(self):
        piece, policy, profile, refs = band_fixture()
        initial, report = anatomical_band_frame(piece, policy, profile, refs, 'sample')
        explicit, report2 = anatomical_band_frame(piece, dict(policy, cage_sampling='SOURCE_TRIANGLE_GRID_V1'), profile, refs, 'sample')
        self.assertEqual(initial, explicit)
        self.assertEqual(report2.pop('cage_sampling'), 'SOURCE_TRIANGLE_GRID_V1')
        self.assertEqual(report, report2)
        for field in (None, 'SEGMENT_ORTHOGONAL_V1'):
            bad = dict(policy, cage_sampling='PATH_KNOT_PARTITION_V1')
            if field is not None: bad['transverse_field'] = field
            with self.assertRaisesRegex(StudioError, 'requires BODY_DIRECTION_CONSTANT'):
                anatomical_band_frame(piece, bad, profile, refs, 'sample')
        for mode in (None, True, 1, [], {}, 'auto'):
            with self.assertRaisesRegex(StudioError, 'cage sampling'):
                anatomical_band_frame(piece, dict(policy, cage_sampling=mode), profile, refs, 'sample')

    def test_unrepresentable_sliver_and_exhausted_budget_are_refused(self):
        piece, _, _, _ = band_fixture(); original = copy.deepcopy(piece)
        evaluate = lambda point: list(point)+[0.]
        with self.assertRaisesRegex(StudioError, 'Collapsed|collapsed'):
            _path_knot_partition(piece, 0, [1e-12], 'sample', evaluate,
                                 _Budget(None, time.monotonic), 'test:source')
        with self.assertRaisesRegex(StudioError, 'budget'):
            _path_knot_partition(piece, 0, [1.], 'sample', evaluate,
                                 _Budget({'max_controls': 3}, time.monotonic), 'test:source')
        self.assertEqual(piece, original)


if __name__ == '__main__': unittest.main()
