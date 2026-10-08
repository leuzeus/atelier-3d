"""Opt-in active metric directions preserve the existing nonlinear gates."""
import copy
import math
import time
import unittest
from unittest import mock

from a3d import active_metric_constraints as active
from a3d.assembly_relaxation import relax_assembly, validate_options
from a3d.cloth_metrics import principal_stretches
from a3d.core import StudioError, digest
from a3d.source_seam_coupling import _Budget


def check(): pass


def triangle():
    uv = [[0., 0.], [1., 0.], [0., 1.]]
    points = [[0., 0., 0.], [1.2, 0., 0.], [0., 1., 0.]]
    direction = [[0., 0., 0.], [.3, 0., 0.], [0., -.1, 0.]]
    return points, direction, [1., 1., 1.], [(uv, [0, 1, 2], 'arbitrary')], {'arbitrary': [.8, 1.2]}, {0}


def solve_fixture():
    states = {pid: {'uv': [[0., 0.], [1., 0.], [0., 1.]], 'triangles': [[0, 1, 2]]} for pid in ('a', 'b')}
    points = {'a': [[0., 0., 0.], [1.2, 0., 0.], [0., 1., 0.]],
              'b': [[3., 0., 0.], [4.2, 0., 0.], [3., 1., 0.]]}
    witnesses = [{'common_fractions': [0., 1.], 'source_chain_lengths_cm': [1., 1.],
        'paired_cage_controls': [[['a', 0], ['b', 0]], [['a', 1], ['b', 1]]]}]
    return states, points, witnesses


def solve(options=None, fixed=None):
    states, points, witnesses = solve_fixture()
    return relax_assembly(states, points, witnesses, _Budget(None, time.monotonic),
        options={'max_iterations': 4, 'rigid_iterations': 2, **(options or {})},
        fixed_controls={'a': [0]} if fixed is None else fixed)


class ActivePrincipalDirection(unittest.TestCase):
    def test_simple_active_bound_rotation_descent_and_immutable_input(self):
        args = triangle(); before = copy.deepcopy(args)
        projected, report = active.project_active_principal_direction(*args, check)
        self.assertEqual(args, before)
        self.assertEqual(projected, [[0., 0., 0.], [0., 0., 0.], [0., -.1, 0.]])
        derivative = -sum(active._dot(a, b) for a, b in zip(args[1], projected))
        self.assertLess(derivative, 0.)
        moved = [[p[k]+.5*d[k] for k in range(3)] for p, d in zip(args[0], projected)]
        low, high = principal_stretches(args[3][0][0], moved)
        self.assertGreaterEqual(low, .8); self.assertLessEqual(high, 1.2)
        rotate = lambda p: [p[2], p[0], p[1]]
        turned = copy.deepcopy(args)
        turned[0][:] = [[a+b for a, b in zip(rotate(p), [11., -3., 7.])] for p in args[0]]
        turned[1][:] = [rotate(p) for p in args[1]]
        result, _ = active.project_active_principal_direction(*turned, check)
        for a, b in zip(result, map(rotate, projected)): self.assertLess(math.dist(a, b), 1e-12)
        self.assertEqual(report['qualification'], 'NONE')
        self.assertEqual(report['nonlinear_admission'], 'REQUIRED_UNCHANGED')
        again, repeated = active.project_active_principal_direction(*args, check)
        self.assertEqual(again, projected); self.assertEqual(repeated, report)

    def test_analytical_gradients_match_finite_differences(self):
        uv = [[0., 0.], [2., .3], [.1, 1.7]]
        points = [[.2, .5, .1], [2.4, .8, .3], [.4, 1.9, .7]]
        _, gradients = active._principal_gradients(uv, points)
        for singular in (0, 1):
            for index in range(3):
                for axis in range(3):
                    plus = copy.deepcopy(points); minus = copy.deepcopy(points); h = 1e-6
                    plus[index][axis] += h; minus[index][axis] -= h
                    observed = (principal_stretches(uv, plus)[singular]-principal_stretches(uv, minus)[singular])/(2*h)
                    self.assertAlmostEqual(observed, gradients[singular][index][axis], places=8)

    def test_multiple_shared_constraints_and_fixed_elimination(self):
        rows = [[(0, [1., 0., 0.]), (1, [-1., 0., 0.])], [(1, [1., 0., 0.])]]
        d, _ = active._project_halfspaces([[2., 0., 0.], [1., 0., 0.]], [1., 1.], rows, set(), check)
        self.assertLessEqual(d[0][0]-d[1][0], 1e-12); self.assertLessEqual(d[1][0], 1e-12)
        d, _ = active._project_halfspaces([[0., 0., 0.], [-1., 0., 0.]], [1., 1.],
                                         [[(1, [-1., 0., 0.])]], {0}, check)
        self.assertEqual(d, [[0., 0., 0.], [0., 0., 0.]])

    def test_repeated_and_zero_active_singularities_refuse_without_axis_guess(self):
        args = triangle()
        for points in ([[0., 0., 0.], [1.2, 0., 0.], [0., 1.2, 0.]],
                       [[0., 0., 0.], [1.2, 0., 0.], [2.4, 0., 0.]]):
            with self.subTest(points=points), self.assertRaises(active.ConstraintProjectionRefused):
                active.project_active_principal_direction(points, args[1], args[2], args[3],
                    {'arbitrary': [0., 3.] if points[-1][0] else [.8, 1.2]}, set(), check)
        # An isotropic face entirely fixed is measurable and has no direction.
        with mock.patch.object(active, '_principal_gradients', side_effect=AssertionError('No derivative needed')):
            d, report = active.project_active_principal_direction(
                [[0., 0., 0.], [1.2, 0., 0.], [0., 1.2, 0.]], args[1], args[2], args[3],
                {'arbitrary': [.8, 1.2]}, {0, 1, 2}, check)
        self.assertEqual(d, [[0., 0., 0.]]*3); self.assertEqual(report['fixed_only_constraint_count'], 1)

    def test_tangent_direction_does_not_bypass_nonlinear_metric_check(self):
        args = triangle(); args[0][2][1] = .9
        args[1][:] = [[0., 0., 0.], [0., 0., 1.], [0., 0., 0.]]
        direction, _ = active.project_active_principal_direction(*args, check)
        self.assertEqual(direction, args[1])
        for step in (1., .5, .01):
            moved = [[p[k]+step*d[k] for k in range(3)] for p, d in zip(args[0], direction)]
            self.assertGreater(principal_stretches(args[3][0][0], moved)[1], 1.2+1.2e-10)

    def test_malformed_nonfinite_and_unsafe_supports_refused(self):
        for value in (math.nan, math.inf, True, 'number'):
            args = list(copy.deepcopy(triangle())); args[1][1][0] = value
            with self.subTest(value=value), self.assertRaises(active.ConstraintProjectionRefused):
                active.project_active_principal_direction(*args, check)
        for mutate in (lambda a: a[0].pop(), lambda a: a[2].__setitem__(0, 0.),
                       lambda a: a.__setitem__(5, {True}), lambda a: a[3].__setitem__(0, ([], [0, 1, 2], 'arbitrary')),
                       lambda a: a[3].__setitem__(0, (a[3][0][0], [0, 0, 2], 'arbitrary')),
                       lambda a: a[4].__setitem__('arbitrary', [math.nan, 1.2])):
            args = list(copy.deepcopy(triangle())); mutate(args)
            with self.assertRaises(active.ConstraintProjectionRefused): active.project_active_principal_direction(*args, check)
        for support in ([(0, [math.nan, 0., 0.])], [(True, [1., 0., 0.])],
                        [(0, [1., 0., 0.]), (0, [1., 0., 0.])], [(4, [1., 0., 0.])]):
            with self.assertRaises(active.ConstraintProjectionRefused):
                active._project_halfspaces([[1., 0., 0.]], [1.], [support], set(), check)
        with self.assertRaises(active.ConstraintProjectionRefused):
            active._project_halfspaces([[math.nan, 0., 0.]], [1.], [], set(), check)
        with self.assertRaises(active.ConstraintProjectionRefused):
            active._project_halfspaces([[1e308, -1e308, 0.]], [1.],
                [[(0, [1e308, 1e308, 0.])]], set(), check)

    def test_projection_iteration_budget_refuses_and_deadline_is_not_swallowed(self):
        rows = [[(0, [1., 0., 0.]), (1, [-1., 0., 0.])], [(1, [1., 0., 0.])]]
        with mock.patch.object(active, 'MAX_SWEEPS', 1), self.assertRaisesRegex(active.ConstraintProjectionRefused, 'ITERATION_BUDGET'):
            active._project_halfspaces([[2., 0., 0.], [1., 0., 0.]], [1., 1.], rows, set(), check)
        error = StudioError('global deadline'); calls = []
        def deadline():
            calls.append(1)
            if len(calls) == 4: raise error
        with self.assertRaises(StudioError) as raised:
            active.project_active_principal_direction(*triangle(), deadline)
        self.assertIs(raised.exception, error)
        self.assertNotIsInstance(raised.exception, active.ConstraintProjectionRefused)
        # A long denominator/residual pass must call its deadline by blocks.
        calls.clear()
        with self.assertRaises(StudioError) as raised:
            active._project_halfspaces([[1., 0., 0.]], [1.], [[(0, [1., 0., 0.])]]*600, set(), deadline)
        self.assertIs(raised.exception, error)


class ActivePrincipalIntegration(unittest.TestCase):
    def test_omitted_option_preserves_exact_historical_coordinates_and_report(self):
        targets, report = solve()
        self.assertEqual(digest(targets), '66bda5401e20d58370d07c5ed1a74c6ca66f35b6eea38a1a6f810f841e96b2bd')
        report.pop('kernel_code_sha256')
        self.assertEqual(digest(report), '6a7bcdf9432c99821ea74f8ff542e7c6e1ee9a69192aba191fb59b486b841fb4')
        self.assertNotIn('constraint_projection', report['settings'])
        self.assertNotIn('line_search_diagnostics', report)

    def test_explicit_mode_records_actual_checks_and_preserves_best_and_fixed_control(self):
        states, points, witnesses = solve_fixture(); before = copy.deepcopy([states, points, witnesses])
        targets, report = relax_assembly(states, points, witnesses, _Budget(None, time.monotonic),
            options={'max_iterations': 4, 'rigid_iterations': 2, 'constraint_projection': active.MODE}, fixed_controls={'a': [0]})
        self.assertEqual([states, points, witnesses], before)
        self.assertEqual(targets['a'][0], points['a'][0])
        self.assertLess(report['best']['objective'], report['initial']['objective'])
        self.assertEqual(report['constraint_projection']['mode'], active.MODE)
        self.assertTrue(report['constraint_projection']['kernel_code_sha256'])
        self.assertTrue(report['line_search_diagnostics'])
        self.assertTrue(all(row['gradient_dot_direction'] < 0 for row in report['constraint_projection']['iterations']))
        self.assertEqual(report['qualification'], 'NONE'); self.assertFalse(report['whole_piece_admission'])

    def test_specific_refusal_preserves_measured_candidate_but_global_deadline_propagates(self):
        with mock.patch.object(active, 'project_active_principal_direction', side_effect=active.ConstraintProjectionRefused('REPEATED_ACTIVE_SINGULAR_VALUE')):
            targets, report = solve({'constraint_projection': active.MODE})
        self.assertEqual(report['termination'], 'CONSTRAINT_PROJECTION_REFUSED')
        self.assertEqual(report['iterations'], 0)
        self.assertLessEqual(report['best']['objective'], report['initial']['objective'])
        self.assertEqual(report['constraint_projection']['iterations'][0]['reason'], 'REPEATED_ACTIVE_SINGULAR_VALUE')
        self.assertEqual(report['qualification'], 'NONE')
        with mock.patch.object(active, 'project_active_principal_direction', side_effect=StudioError('global deadline')):
            with self.assertRaisesRegex(StudioError, 'global deadline'): solve({'constraint_projection': active.MODE})

    def test_nonfinite_or_zero_direction_never_enters_search_as_descent(self):
        for value in (0., math.inf):
            def invalid(points, *args): return [[value]*3 for _ in points], {'qualification': 'NONE'}
            with mock.patch.object(active, 'project_active_principal_direction', side_effect=invalid):
                _, report = solve({'constraint_projection': active.MODE})
            self.assertEqual(report['termination'], 'CONSTRAINT_PROJECTION_NO_DESCENT')
            self.assertEqual(report['iterations'], 0)

    def test_projection_mode_is_explicit_and_versioned(self):
        self.assertNotIn('constraint_projection', validate_options())
        self.assertEqual(validate_options({'constraint_projection': active.MODE})['constraint_projection'], active.MODE)
        for value in (None, True, 'NONE', 'UNCONSTRAINED_GRADIENT_V1', 'ACTIVE_PRINCIPAL_CONE_V2', {}):
            with self.subTest(value=value), self.assertRaises(StudioError):
                validate_options({'constraint_projection': value})


if __name__ == '__main__': unittest.main()
