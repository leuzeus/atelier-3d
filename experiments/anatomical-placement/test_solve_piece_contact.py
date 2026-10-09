import copy
import json
from pathlib import Path
from types import SimpleNamespace
import unittest
from unittest.mock import patch
import numpy as np
from solve_piece_contact import Budget, MetricFactor, ScalarProjection, barycentric, orientation_report, scalar_rows


def settings():
    return {'max_seconds': 5., 'position_penalty': 1e-6}


class ScalarContactTests(unittest.TestCase):
    def test_scalar_projection_does_not_snap_tangent_or_move_fixed_controls(self):
        cage = {'uv_cm': [[0., 0.], [1., 0.], [0., 1.]], 'triangles': [[0, 1, 2]],
                'target_cm': [[0., 0., 0.], [1., 0., 0.], [0., 1., 0.]]}
        original = copy.deepcopy(cage); budget = Budget(settings()); factor = MetricFactor(cage, [0, 1], settings(), budget)
        rows = np.zeros((1, 3, 3)); rows[0, 2, 2] = 1
        solver = ScalarProjection(factor, rows, np.array([.3]), budget)
        result, residual = solver.project(np.asarray(cage['target_cm']), 5)
        self.assertEqual(cage, original)
        self.assertTrue(np.array_equal(result[:2], np.asarray(cage['target_cm'])[:2]))
        self.assertTrue(np.array_equal(result[2, :2], [0., 1.]))
        self.assertAlmostEqual(result[2, 2], .3, places=12); self.assertLess(residual, 1e-12)

    def test_contradictory_halfspaces_remain_measured_unsatisfied(self):
        cage = {'uv_cm': [[0., 0.], [1., 0.], [0., 1.]], 'triangles': [[0, 1, 2]],
                'target_cm': [[0., 0., 0.], [1., 0., 0.], [0., 1., 0.]]}
        budget = Budget(settings()); factor = MetricFactor(cage, [0, 1], settings(), budget)
        rows = np.zeros((2, 3, 3)); rows[0, 2, 2] = 1; rows[1, 2, 2] = -1
        solver = ScalarProjection(factor, rows, np.array([.3, .3]), budget)
        _, residual = solver.project(np.asarray(cage['target_cm']), 30)
        self.assertGreaterEqual(residual, .3)

    def test_contact_support_is_barycentric_and_all_shared_feature_planes_retained(self):
        cage = {'triangles': [[0, 1, 2]]}; xyz = np.array([[0., 0., .1], [1., 0., .1], [0., 1., .1]])
        body = SimpleNamespace(triangles=np.array([[[0., 0., 0.], [1., 0., 0.], [0., 1., 0.]]]*2),
            normals=np.array([[0., 0., 1.], [0., 0., 1.]]))
        contact = {'cage_triangle': 0, 'body_triangle': 0, 'body_source_face': 0, 'kind': 'SEPARATED',
                   'distance_cm': .1, 'point_a_cm': [.5, 0., .1], 'point_b_cm': [.5, 0., 0.]}
        audit = {'unrepresentable_pairs': [], 'contacts': [contact, {**contact, 'body_triangle': 1}]}
        rows, bound, records = scalar_rows(cage, xyz, audit, body, [], .3, 10)
        self.assertEqual(len(rows), 2); self.assertEqual(len(records), 2)
        self.assertTrue(np.allclose(rows[:, :, 2], [[.5, .5, 0.], [.5, .5, 0.]]))
        self.assertTrue(np.allclose(bound, .3))
        with self.assertRaisesRegex(ValueError, 'FIXED_SUPPORT_CONFLICT'):
            scalar_rows(cage, xyz, audit, body, [0, 1], .3, 10)

    def test_barycentric_refuses_outside_witness_without_clipping(self):
        tri = [[0., 0., 0.], [1., 0., 0.], [0., 1., 0.]]
        self.assertTrue(np.allclose(barycentric([.2, .3, 0.], tri), [.5, .2, .3]))
        with self.assertRaisesRegex(ValueError, 'OUTSIDE_RECORDED'):
            barycentric([2., 2., 0.], tri)

    def test_activation_band_retains_near_plane_without_changing_physical_bound(self):
        cage = {'triangles': [[0, 1, 2]]}; xyz = np.array([[0., 0., .32], [1., 0., .32], [0., 1., .32]])
        body = SimpleNamespace(triangles=np.array([[[0., 0., 0.], [1., 0., 0.], [0., 1., 0.]]]), normals=np.array([[0., 0., 1.]]))
        contact = {'cage_triangle': 0, 'body_triangle': 0, 'body_source_face': 0, 'kind': 'SEPARATED',
            'distance_cm': .32, 'point_a_cm': [.2, .3, .32], 'point_b_cm': [.2, .3, 0.]}
        audit = {'unrepresentable_pairs': [], 'contacts': [contact]}; reserve = .3000000026077032
        rows, bound, records = scalar_rows(cage, xyz, audit, body, [], reserve, 10, reserve+.05)
        self.assertEqual(len(rows), 1); self.assertEqual(bound.tolist(), [reserve])
        self.assertEqual(records[0]['physical_reserve_cm'], reserve)
        self.assertEqual(records[0]['activation_distance_cm'], reserve+.05)
        self.assertGreater(float(np.einsum('mij,ij->m', rows, xyz)[0]), bound[0])

    def test_native_orientation_requires_closed_consistent_positive_volume_without_flipping(self):
        vertices = np.array([[0., 0., 0.], [1., 0., 0.], [0., 1., 0.], [0., 0., 1.]])
        triangles = np.array([[0, 2, 1], [0, 1, 3], [0, 3, 2], [1, 2, 3]])
        _, report = orientation_report(vertices, triangles)
        self.assertAlmostEqual(report['positive_signed_volume_cm3'], 1/6)
        self.assertEqual(report['normal_flips'], 0)
        for changed in (triangles[:-1], triangles[:, ::-1]):
            with self.assertRaises(ValueError): orientation_report(vertices, changed)

    def test_computation_margin_changes_only_scalar_rhs_and_refuses_fixed_conflict(self):
        cage = {'triangles': [[0, 1, 2]]}; xyz = np.array([[0., 0., .3005], [1., 0., .3005], [0., 1., .3005]])
        body = SimpleNamespace(triangles=np.array([[[0., 0., 0.], [1., 0., 0.], [0., 1., 0.]]]), normals=np.array([[0., 0., 1.]]))
        contact = {'cage_triangle': 0, 'body_triangle': 0, 'body_source_face': 0, 'kind': 'SEPARATED',
            'distance_cm': .3005, 'point_a_cm': [0., 0., .3005], 'point_b_cm': [0., 0., 0.]}
        audit = {'unrepresentable_pairs': [], 'contacts': [contact]}; reserve = .3000000026077032
        original = xyz.copy()
        rows, old_bound, _ = scalar_rows(cage, xyz, audit, body, [], reserve, 10, reserve+.05, 0.)
        changed_rows, bound, records = scalar_rows(cage, xyz, audit, body, [], reserve, 10, reserve+.05, .001)
        self.assertTrue(np.array_equal(rows, changed_rows)); self.assertTrue(np.array_equal(xyz, original))
        self.assertEqual(bound.tolist(), [reserve+.001]); self.assertEqual(old_bound.tolist(), [reserve])
        self.assertEqual(records[0]['physical_reserve_cm'], reserve); self.assertEqual(records[0]['computation_margin_cm'], .001)
        scalar_rows(cage, xyz, audit, body, [0], reserve, 10, reserve+.05, 0.)
        with self.assertRaisesRegex(ValueError, 'FIXED_SUPPORT_CONFLICT'):
            scalar_rows(cage, xyz, audit, body, [0], reserve, 10, reserve+.05, .001)

    def test_scalar_solver_checks_shared_deadline(self):
        cage = {'uv_cm': [[0., 0.], [1., 0.], [0., 1.]], 'triangles': [[0, 1, 2]],
                'target_cm': [[0., 0., 0.], [1., 0., 0.], [0., 1., 0.]]}
        budget = Budget(settings()); factor = MetricFactor(cage, [0, 1], settings(), budget)
        rows = np.zeros((1, 3, 3)); rows[0, 2, 2] = 1
        solver = ScalarProjection(factor, rows, np.array([.3]), budget)
        with patch.object(budget, 'check', side_effect=TimeoutError('COMMON_TIME_BUDGET')):
            with self.assertRaises(TimeoutError): solver.project(np.asarray(cage['target_cm']), 1)


if __name__ == '__main__':
    result = unittest.TextTestRunner(verbosity=2).run(unittest.defaultTestLoader.loadTestsFromTestCase(ScalarContactTests))
    Path('scalar-contact-test-report.json').write_text(json.dumps({'tests': result.testsRun, 'failures': len(result.failures),
        'errors': len(result.errors), 'passed': result.wasSuccessful(), 'scope': 'SYNTHETIC_SCALAR_CONTACTS_ONLY',
        'qualification': 'NONE'}, indent=2), encoding='utf-8')
    raise SystemExit(0 if result.wasSuccessful() else 1)
