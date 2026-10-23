"""Small numerical checks for the exploratory QR metric solver."""
import copy
import json
from pathlib import Path
import unittest
from unittest.mock import patch
import numpy as np

from solve_piece_metric import solve
import solve_piece_metric as kernel


def fixture():
    uv = [[float(u), float(v)] for v in range(4) for u in range(5)]
    triangles = []
    for v in range(3):
        for u in range(4):
            a = v*5+u
            triangles.extend(([a, a+1, a+6], [a, a+6, a+5]))
    cage = {'source_ref': 'synthetic-source', 'uv_cm': uv, 'triangles': triangles,
            'target_cm': [[u+.4*v, 0., v] for u, v in uv]}
    settings = {'max_seconds': 5., 'max_iterations': 1000, 'observation_stride': 1,
                'strain_tolerance': .02, 'projection_strain_tolerance': 0.,
                'position_penalty': 1e-6, 'max_displacement_cm': 20.}
    return cage, list(range(5)), settings


class MetricSolver(unittest.TestCase):
    def test_shear_corrected_with_exact_fixed_edge_and_immutable_source(self):
        cage, fixed, settings = fixture(); before = copy.deepcopy(cage)
        candidate, result = solve(cage, fixed, settings)
        self.assertEqual(cage, before)
        self.assertEqual(result['status'], 'SINGLE_PIECE_METRIC_TARGETS_REACHED')
        self.assertEqual(result['best']['outside_triangles'], 0)
        self.assertEqual(candidate['uv_cm'], cage['uv_cm'])
        self.assertEqual(candidate['triangles'], cage['triangles'])
        self.assertTrue(all(candidate['target_cm'][i] == cage['target_cm'][i] for i in fixed))

    def test_rigid_world_transform_keeps_metric_and_transforms_candidate_equivariantly(self):
        cage, fixed, settings = fixture()
        transform = lambda p: [p[2]+20., p[0]-7., p[1]+53.]
        changed = copy.deepcopy(cage); changed['target_cm'] = [transform(p) for p in cage['target_cm']]
        first, _ = solve(cage, fixed, settings); second, _ = solve(changed, fixed, settings)
        self.assertLess(np.linalg.norm(np.asarray(second['target_cm'])-np.asarray([transform(p) for p in first['target_cm']]), axis=1).max(), 1e-8)

    def test_impossible_fixed_chord_cannot_be_reported_as_metric_success(self):
        cage, _, settings = fixture(); fixed = [0, 4]
        cage['target_cm'][4] = [4.2, 0., 0.]
        candidate, result = solve(cage, fixed, settings)
        self.assertNotEqual(result['status'], 'SINGLE_PIECE_METRIC_TARGETS_REACHED')
        self.assertGreater(result['best']['outside_triangles'], 0)
        self.assertTrue(all(candidate['target_cm'][i] == cage['target_cm'][i] for i in fixed))

    def test_dense_dimension_budgets_refuse_before_factorization(self):
        cage, fixed, settings = fixture()
        for limits in ({'max_dense_free_controls': 10}, {'max_dense_estimated_bytes': 100}):
            with self.subTest(limits=limits), patch('solve_piece_metric.qr') as factor:
                with self.assertRaisesRegex(ValueError, 'DENSE_DIMENSION_BUDGET'):
                    solve(cage, fixed, {**settings, **limits})
                factor.assert_not_called()
        large = copy.deepcopy(cage)
        large['uv_cm'] *= 60; large['target_cm'] *= 60
        with patch('solve_piece_metric.qr') as factor:
            with self.assertRaisesRegex(ValueError, 'DENSE_DIMENSION_BUDGET'):
                solve(large, fixed, settings)
            factor.assert_not_called()

    def test_deadline_after_factorization_step_and_measurement_cannot_report_success(self):
        for stage in ('qr', 'solve_triangular', 'metric'):
            cage, fixed, settings = fixture(); settings['max_seconds'] = 1.
            cage['target_cm'] = [[u, 0., v] for u, v in cage['uv_cm']]
            now = [0.]; original = getattr(kernel, stage); calls = [0]
            def delayed(*args, **kwargs):
                answer = original(*args, **kwargs); calls[0] += 1
                if stage != 'metric' or calls[0] == 2: now[0] = 2.
                return answer
            with self.subTest(stage=stage), patch('solve_piece_metric.time.monotonic', side_effect=lambda: now[0]), patch('solve_piece_metric.'+stage, side_effect=delayed):
                if stage == 'qr':
                    with self.assertRaisesRegex(TimeoutError, 'TIME_BUDGET'):
                        solve(cage, fixed, settings)
                else:
                    _, report = solve(cage, fixed, settings)
                    self.assertTrue(report['status'].startswith('TIME_BUDGET_EXHAUSTED'))

    def test_deadline_during_observation_save_cannot_report_success(self):
        cage, fixed, settings = fixture(); settings['max_seconds'] = 1.
        cage['target_cm'] = [[u, 0., v] for u, v in cage['uv_cm']]
        now = [0.]
        class SlowOutput:
            def __truediv__(self, name): return self
            def write_text(self, *args, **kwargs): now[0] = 2.
        with patch('solve_piece_metric.time.monotonic', side_effect=lambda: now[0]):
            _, report = solve(cage, fixed, settings, SlowOutput())
        self.assertTrue(report['status'].startswith('TIME_BUDGET_EXHAUSTED'))


if __name__ == '__main__':
    suite = unittest.defaultTestLoader.loadTestsFromTestCase(MetricSolver)
    result = unittest.TextTestRunner(verbosity=2).run(suite)
    Path('synthetic-test-report.json').write_text(json.dumps({'tests': result.testsRun,
        'failures': len(result.failures), 'errors': len(result.errors), 'passed': result.wasSuccessful(),
        'scope': 'PORTABLE_SYNTHETIC_SOLVER_CHECKS_ONLY', 'qualification': 'NONE'}, indent=2), encoding='utf-8')
    raise SystemExit(0 if result.wasSuccessful() else 1)
