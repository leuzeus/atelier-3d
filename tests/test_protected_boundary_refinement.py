"""Portable regression for restored global CDT proposals; no native proof."""
import copy
import math
import sys
import types
import unittest
from unittest import mock

from a3d.cloth_metrics import triangle_metrics
from a3d.sewing import distance, point_inside
from blender.sewing import triangulate
from tests.test_native_mesh_conditioning import Vector2, fixture, mocked_conditioner, native_result


class ProtectedBoundaryRefinement(unittest.TestCase):
    @staticmethod
    def unchanged(vertices, *_args, **_settings):
        return copy.deepcopy(vertices), {'algorithm': 'TEST_STUB_NO_SMOOTHING', 'target_reached': False}

    def run_mocked(self, polygon, apex, *, passes=1, added=4000, min_edge=.001, existing=()):
        boundary, recipe, regular = fixture(max_passes=passes, max_added=added)
        boundary.update(polygon=copy.deepcopy(polygon), source=copy.deepcopy(polygon))
        recipe['mesh']['min_edge_cm'] = min_edge
        initial = [Vector2(p) for p in polygon] + [Vector2(apex)]
        faces = [[i, (i + 1) % len(polygon), len(polygon)] for i in range(len(polygon))]
        snapshots = []
        def cdt(points, *_args):
            snapshots.append([list(p) for p in points])
            return initial, [], faces, [[i] for i in range(len(initial))], [], []
        module = types.ModuleType('mathutils'); module.Vector = Vector2
        geometry = types.ModuleType('mathutils.geometry'); geometry.delaunay_2d_cdt = cdt
        with mock.patch.dict(sys.modules, {'mathutils': module, 'mathutils.geometry': geometry}), \
                mock.patch('a3d.pattern_preparation.regular_interior_points', return_value=([apex, *existing], {})), \
                mock.patch('a3d.mesh_refinement.improve_interior', side_effect=self.unchanged):
            result = triangulate(boundary, recipe, regular)
        return result, boundary['preparation_refinement'], snapshots

    def test_circumcenter_outside_incident_face_remains_valid_global_cdt_proposal(self):
        polygon = [[0., 0.], [.01, 0.], [1., 0.], [1., 1.], [0., 1.]]
        apex = [.025, .05]
        result, report, snapshots = self.run_mocked(polygon, apex)
        transported = snapshots[1][len(polygon) + 1]
        # Analytical center of the first triangle, transported to binary32.
        expected = list(Vector2([.005, .02875]))
        self.assertEqual(transported, expected)
        self.assertTrue(point_inside(transported, polygon))
        self.assertFalse(point_inside(transported, [polygon[0], polygon[1], apex]))
        self.assertEqual([result[0][result[2][i]] for i in range(len(polygon))], polygon)
        self.assertEqual(report['status'], 'NEEDS_CORRECTION')
        self.assertEqual(report['refusal'], 'PASS_BUDGET_EXHAUSTED')
        self.assertEqual(report['target_min_angle_degrees'], 15.)

    def test_small_equilateral_triangle_does_not_qualify_incident_subdivision(self):
        # Measured source53 face2607: the local small triangle can be excellent
        # while the other triangles become worse. This is a pure geometry fact,
        # not a prediction of global CDT topology or a new source repair.
        triangle = [[23.842698501622912, 116.8255726412122],
                    [23.75521469116211, 116.81970977783203],
                    [23.844444, 116.814815]]
        a, b = triangle[2], triangle[0]
        c = triangle[1]
        d = [b[k] - a[k] for k in range(2)]; mid = [(a[k] + b[k]) / 2 for k in range(2)]
        normal = [-d[1], d[0]]
        if sum(normal[k] * (c[k] - mid[k]) for k in range(2)) < 0: normal = [-v for v in normal]
        local = [mid[k] + normal[k] * math.sqrt(3) / 2 for k in range(2)]
        self.assertTrue(point_inside(local, triangle))
        self.assertGreater(triangle_metrics([a, b, local])['min_angle_degrees'], 59.999999)
        induced = [triangle_metrics([triangle[i], triangle[(i + 1) % 3], local])['min_angle_degrees'] for i in range(3)]
        self.assertLess(min(induced), triangle_metrics(triangle)['min_angle_degrees'])
        self.assertLess(min(induced), 15.)

    def test_offset_float32_transport_preserves_distinct_exact_source_stops(self):
        polygon = [[10.0000000001, 100.], [10.010898330661834, 100.], [11., 100.],
                   [11., 101.], [10.0000000001, 101.]]
        apex = [10.025, 100.05]
        before = copy.deepcopy((polygon, apex))
        result, report, snapshots = self.run_mocked(polygon, apex)
        first_inserted = snapshots[1][len(polygon) + 1]
        self.assertTrue(point_inside(first_inserted, polygon))
        self.assertFalse(point_inside(first_inserted, [polygon[0], polygon[1], apex]))
        self.assertNotEqual(result[2][0], result[2][1])
        self.assertEqual([result[0][result[2][i]] for i in range(len(polygon))], polygon)
        self.assertEqual((polygon, apex), before)
        self.assertEqual(self.run_mocked(polygon, apex), (result, report, snapshots))

    def test_dense_existing_point_rejects_global_proposal_without_snapping(self):
        polygon = [[0., 0.], [.01, 0.], [1., 0.], [1., 1.], [0., 1.]]
        apex = [.025, .05]
        blocked = [.005, .02875]
        result, report, snapshots = self.run_mocked(polygon, apex, existing=[blocked])
        appended = snapshots[1][len(polygon) + 2:]
        self.assertTrue(appended)
        self.assertNotIn(list(Vector2(blocked)), appended)
        self.assertTrue(all(distance(value, Vector2(blocked)) >= .001 for value in appended))
        self.assertEqual([result[0][result[2][i]] for i in range(len(polygon))], polygon)
        self.assertEqual(report['status'], 'NEEDS_CORRECTION')

    def test_no_admissible_point_stalls_with_original_spacing_and_final_gate(self):
        polygon = [[0., 0.], [1., 0.], [1., 1.], [0., 1.]]
        result, report, snapshots = self.run_mocked(polygon, [.2, .2], min_edge=.9)
        self.assertEqual(len(snapshots), 1)
        self.assertEqual(report['refusal'], 'REFINEMENT_STALLED')
        self.assertEqual(report['status'], 'NEEDS_CORRECTION')
        self.assertEqual(report['added_vertices'], 0)
        self.assertEqual(report['target_min_angle_degrees'], 15.)
        self.assertEqual([result[0][result[2][i]] for i in range(4)], polygon)

    def test_true_acute_source_corner_stays_refused_with_exact_coordinates(self):
        polygon = [[0., 0.], [1., 0.], [1., .05]]
        result, report, snapshots = self.run_mocked(polygon, [.95, .015], passes=0)
        self.assertEqual(report['status'], 'NEEDS_CORRECTION')
        self.assertEqual(report['refusal'], 'PASS_BUDGET_EXHAUSTED')
        self.assertLess(report['min_angle_degrees'], 15.)
        self.assertEqual(len(snapshots), 1)
        self.assertEqual([result[0][result[2][i]] for i in range(3)], polygon)

    def test_added_vertex_budget_remains_refused_before_second_cdt(self):
        polygon = [[0., 0.], [1., 0.], [1., 1.], [0., 1.]]
        _, report, snapshots = self.run_mocked(polygon, [.2, .2], added=0)
        self.assertEqual(report['refusal'], 'VERTEX_BUDGET_EXHAUSTED')
        self.assertEqual(report['added_vertices'], 0)
        self.assertEqual(len(snapshots), 1)

    def test_degraded_conditioned_global_candidate_rolls_back_to_exact_best(self):
        boundary, recipe, regular = fixture()
        polygon = copy.deepcopy(boundary['polygon'])
        outputs = [native_result(polygon, [.2, .2]), native_result(polygon, [.05, .05])]
        smoother, _ = mocked_conditioner([None, [.15, .15]])
        module = types.ModuleType('mathutils'); module.Vector = Vector2
        geometry = types.ModuleType('mathutils.geometry'); geometry.delaunay_2d_cdt = mock.Mock(side_effect=outputs)
        with mock.patch.dict(sys.modules, {'mathutils': module, 'mathutils.geometry': geometry}), \
                mock.patch('a3d.pattern_preparation.regular_interior_points', return_value=([[.2, .2]], {})), \
                mock.patch('a3d.mesh_refinement.improve_interior', side_effect=smoother):
            coordinates, _, mapping = triangulate(boundary, recipe, regular)
        report = boundary['preparation_refinement']
        self.assertEqual(coordinates[4], list(Vector2([.2, .2])))
        self.assertEqual([coordinates[mapping[i]] for i in range(4)], polygon)
        self.assertEqual(report['refusal'], 'NON_MONOTONIC_REFINEMENT_ROLLED_BACK')
        self.assertEqual(report['passes'], 0)
        self.assertEqual(report['conditioning_history'][-1]['decision'], 'ROLLED_BACK_AFTER_CONDITIONING')
        self.assertEqual(report['status'], 'NEEDS_CORRECTION')


if __name__ == '__main__': unittest.main()
