"""Portable proposal and sequencing tests; no native CDT qualification."""
import copy
import math
import sys
import types
import unittest
from unittest import mock

from a3d.cloth_metrics import triangle_metrics
from a3d.sewing import distance, point_inside, segment_distance
from blender.sewing import _incident_refinement_candidates, triangulate
from tests.test_native_mesh_conditioning import Vector2, fixture


class ProtectedBoundaryRefinement(unittest.TestCase):
    # Read-only source53 material witness face2607. These numbers are test
    # observations, not garment placement coordinates or a pattern correction.
    witness = [[23.842698501622912, 116.8255726412122],
               [23.75521469116211, 116.81970977783203],
               [23.844444, 116.814815]]

    def test_protected_local_apex_is_not_replaced_by_outside_face_circumcenter(self):
        original = copy.deepcopy(self.witness)
        report = _incident_refinement_candidates(self.witness, [(2, 0)])
        self.assertEqual(report['short_edge'], (2, 0))
        self.assertTrue(report['protected_short_edge'])
        self.assertEqual(report['candidates'][0]['kind'], 'LOCAL_EDGE_APEX')
        self.assertNotIn('INCIDENT_CIRCUMCENTER', [c['kind'] for c in report['candidates']])
        value = report['candidates'][0]['point']
        self.assertTrue(point_inside(value, self.witness))
        self.assertAlmostEqual(value[0], 23.834254860236886, places=11)
        self.assertAlmostEqual(value[1], 116.81868217466929, places=11)
        a, b = [self.witness[i] for i in report['short_edge']]
        self.assertGreaterEqual(triangle_metrics([a, b, value])['min_angle_degrees'], 59.999999)
        self.assertGreater(segment_distance(value, a, b), max(.001, distance(a, b) * .2))
        self.assertEqual(self.witness, original)

    def test_inside_circumcenter_remains_first_for_unprotected_edge(self):
        triangle = [[0., 0.], [1., 0.], [.3, .7]]
        report = _incident_refinement_candidates(triangle)
        self.assertFalse(report['protected_short_edge'])
        self.assertEqual(report['candidates'][0]['kind'], 'INCIDENT_CIRCUMCENTER')
        self.assertTrue(all(point_inside(c['point'], triangle) for c in report['candidates']))
        self.assertAlmostEqual(report['candidates'][0]['point'][0], .5)
        self.assertAlmostEqual(report['candidates'][0]['point'][1], .2)

    def test_clockwise_and_translation_keep_incident_domain(self):
        triangles = [self.witness, list(reversed(self.witness))]
        for triangle in triangles:
            short = min(((0, 1), (1, 2), (2, 0)), key=lambda ij: distance(triangle[ij[0]], triangle[ij[1]]))
            report = _incident_refinement_candidates(triangle, [short])
            value = report['candidates'][0]['point']
            with self.subTest(triangle=triangle):
                self.assertEqual(report['candidates'][0]['kind'], 'LOCAL_EDGE_APEX')
                self.assertTrue(point_inside(value, triangle))
                self.assertAlmostEqual(value[0], 23.834254860236886, places=11)
                self.assertAlmostEqual(value[1], 116.81868217466929, places=11)
        moved = [[p[0] - 20., p[1] - 110.] for p in self.witness]
        result = _incident_refinement_candidates(moved, [(2, 0)])
        for k, (x, y) in enumerate(zip(result['candidates'][0]['point'], _incident_refinement_candidates(self.witness, [(2, 0)])['candidates'][0]['point'])):
            self.assertAlmostEqual(x, y - (20., 110.)[k], places=11)

    def test_offset_float32_proposal_keeps_existing_separation_floor(self):
        report = _incident_refinement_candidates(self.witness, [(2, 0)])
        native_value = list(Vector2(report['candidates'][0]['point']))
        a, b = [self.witness[i] for i in report['short_edge']]
        self.assertTrue(point_inside(native_value, self.witness))
        self.assertGreater(segment_distance(native_value, a, b), max(.001, distance(a, b) * .2))
        self.assertGreater(triangle_metrics([a, b, native_value])['min_angle_degrees'], 59.)
        self.assertGreaterEqual(min(triangle_metrics([a, b, native_value])['edges_cm']), .001)

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

    def test_native_transport_prioritizes_local_point_and_restores_all_exact_corners(self):
        polygon = [[10.0000000001, 100.], [10.010898330661834, 100.], [11., 100.],
                   [11., 101.], [10.0000000001, 101.]]
        apex = [10.025, 100.05]
        before = copy.deepcopy((polygon, apex))
        result, report, snapshots = self.run_mocked(polygon, apex)
        targets = _incident_refinement_candidates([polygon[0], polygon[1], list(Vector2(apex))], [(0, 1)])
        self.assertEqual(snapshots[1][len(polygon) + 1], list(Vector2(targets['candidates'][0]['point'])))
        self.assertEqual(report['status'], 'NEEDS_CORRECTION')
        self.assertEqual(report['refusal'], 'PASS_BUDGET_EXHAUSTED')
        self.assertEqual(report['passes'], 1)
        self.assertEqual([result[0][result[2][i]] for i in range(len(polygon))], polygon)
        self.assertEqual((polygon, apex), before)
        repeated = self.run_mocked(polygon, apex)
        self.assertEqual(repeated, (result, report, snapshots))

    def test_no_admissible_point_stalls_without_weakening_spacing_or_quality(self):
        polygon = [[0., 0.], [1., 0.], [1., 1.], [0., 1.]]
        result, report, snapshots = self.run_mocked(polygon, [.2, .2], min_edge=.9)
        self.assertEqual(len(snapshots), 1)
        self.assertEqual(report['refusal'], 'REFINEMENT_STALLED')
        self.assertEqual(report['status'], 'NEEDS_CORRECTION')
        self.assertEqual(report['added_vertices'], 0)
        self.assertEqual(report['target_min_angle_degrees'], 15.)
        self.assertEqual([result[0][result[2][i]] for i in range(4)], polygon)

    def test_dense_existing_point_rejects_local_proposal_without_snapping(self):
        polygon = [[10.0000000001, 100.], [10.010898330661834, 100.], [11., 100.],
                   [11., 101.], [10.0000000001, 101.]]
        apex = [10.025, 100.05]
        targets = _incident_refinement_candidates([polygon[0], polygon[1], list(Vector2(apex))], [(0, 1)])
        local = targets['candidates'][0]['point']
        dense = [local[0] + .0005, local[1]]
        result, report, snapshots = self.run_mocked(polygon, apex, existing=[dense])
        separation = max(.001, targets['short_edge_cm'] * .2)
        appended = snapshots[1][len(polygon) + 2:]
        self.assertTrue(appended)
        self.assertNotIn(list(Vector2(local)), appended)
        self.assertTrue(all(distance(value, Vector2(dense)) >= separation for value in appended))
        self.assertEqual([result[0][result[2][i]] for i in range(len(polygon))], polygon)
        self.assertEqual(report['status'], 'NEEDS_CORRECTION')

    def test_float32_point_outside_incident_face_is_skipped_after_conversion(self):
        triangle = [[10., 100.000006], [10.01, 100.000006], [10.005, 100.0086663]]
        targets = _incident_refinement_candidates(triangle, [(0, 1), (1, 2), (2, 0)])
        local, center = [c['point'] for c in targets['candidates'][:2]]
        self.assertTrue(point_inside(local, triangle))
        self.assertFalse(point_inside(Vector2(local), triangle))
        self.assertTrue(point_inside(Vector2(center), triangle))
        boundary, recipe, regular = fixture(max_passes=1)
        boundary.update(polygon=copy.deepcopy(triangle), source=copy.deepcopy(triangle))
        regular['target_min_angle_degrees'] = 60.  # Stress proposal transport only.
        snapshots = []
        def cdt(points, *_args):
            snapshots.append([list(p) for p in points])
            return [Vector2(p) for p in triangle], [], [[0, 1, 2]], [[0], [1], [2]], [], []
        module = types.ModuleType('mathutils'); module.Vector = Vector2
        geometry = types.ModuleType('mathutils.geometry'); geometry.delaunay_2d_cdt = cdt
        with mock.patch.dict(sys.modules, {'mathutils': module, 'mathutils.geometry': geometry}), \
                mock.patch('a3d.pattern_preparation.regular_interior_points', return_value=([], {})), \
                mock.patch('a3d.mesh_refinement.improve_interior', side_effect=self.unchanged):
            coordinates, _, mapping = triangulate(boundary, recipe, regular)
        self.assertEqual(snapshots[1][-1], list(Vector2(center)))
        self.assertNotIn(list(Vector2(local)), snapshots[1][len(triangle):])
        self.assertEqual([coordinates[mapping[i]] for i in range(3)], triangle)
        self.assertEqual(boundary['preparation_refinement']['status'], 'NEEDS_CORRECTION')

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


if __name__ == '__main__': unittest.main()
