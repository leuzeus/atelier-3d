"""Pure fixture measurements qualify the kernel contract, never a real body."""
import copy
import math
import unittest

from a3d.anchor_reserve import DOMAIN, solve_anchor_reserve
from a3d.core import StudioError, digest


def fixture(names=('first', 'partner', 'external', 'detachable')):
    points = [[float(x), float(y), 0.] for n in range(4)
              for x, y in ((n * 4, 0), (n * 4 + 1, 0), (n * 4, 1))]
    payload = {'rest_cm': copy.deepcopy(points),
               'uv_cm': [[p[0], p[1]] for p in points],
               'faces': [[3 * n, 3 * n + 1, 3 * n + 2] for n in range(4)],
               'panels': {pid: {'indices': [3*n, 3*n+1, 3*n+2]} for n, pid in enumerate(names)},
               'seams': {'first-link': {'kind': 'permanent', 'piece_a': names[0], 'piece_b': names[1], 'pairs': [[1, 3]]},
                         'transitive-link': {'kind': 'permanent', 'piece_a': names[1], 'piece_b': names[2], 'pairs': [[4, 6]]},
                         'free-link': {'kind': 'detachable', 'piece_a': names[0], 'piece_b': names[3], 'pairs': [[2, 9]]}},
               'pins': {}}
    spec = {'version': 1, 'enabled': True, 'domain': DOMAIN,
            'budgets': {'max_displacement_cm': 3., 'max_step_cm': .5,
                        'max_iterations': 12, 'max_seconds': 10.,
                        'stagnation_iterations': 3, 'min_improvement_cm': 1e-9}}
    context = {'body_sha256': 'body-fixture', 'pose_sha256': 'pose-fixture',
               'controls_sha256': 'controls-fixture'}
    return payload, points, spec, context


def evaluator(context, stops=(0,), moving=tuple(range(9)), axis=(0., 0., 1.), target=1.5):
    def measure(payload, points):
        return {'status': 'MEASURED', 'context_identity': copy.deepcopy(context),
                'source_sha256': digest(payload), 'candidate_sha256': digest(points),
                'method': 'FULL_BODY_COLLISION', 'sign_status': 'UNAMBIGUOUS',
                'moving_indices': sorted(moving),
                'protected_contacts': [{'vertex': i, 'signed_offset_cm': sum(x*y for x, y in zip(axis, points[i])),
                                         'clearance_cm': target} for i in stops]}
    return measure


class Clock:
    def __init__(self): self.value = 0.
    def __call__(self): return self.value


class AnchorReserve(unittest.TestCase):
    def run_kernel(self, payload=None, points=None, spec=None, context=None, evaluate=None, **options):
        source, entry, declared, identity = fixture()
        payload = source if payload is None else payload
        points = entry if points is None else points
        spec = declared if spec is None else spec
        context = identity if context is None else context
        stops = options.pop('protected_indices', [0])
        up = options.pop('body_frame_up', [0., 0., 1.])
        precondition = options.pop('rest_precondition') if 'rest_precondition' in options else {
            'status': 'PASSED', 'source_sha256': digest(payload), 'candidate_sha256': digest(points)}
        return solve_anchor_reserve(payload, points, evaluate or evaluator(context, stops=stops), spec,
            body_frame_up=up, context_identity=context,
            displacement_reference=options.pop('displacement_reference', copy.deepcopy(points)),
            rest_precondition=precondition,
            protected_indices=stops, clock=options.pop('clock', lambda: 0.), **options)

    def test_transitive_permanent_component_includes_external_partner_and_preserves_gaps(self):
        payload, points, spec, context = fixture()
        original = digest([payload, points, spec, context])
        result = self.run_kernel(payload, points, spec, context)
        self.assertEqual(result['status'], 'ANCHORS_ADMISSIBLE_ONLY')
        self.assertEqual(result['moving_indices'], list(range(9)))
        self.assertEqual(result['coordinates_cm'][9:], points[9:])
        for seam in payload['seams'].values():
            if seam['kind'] == 'permanent':
                for a, b in seam['pairs']:
                    self.assertAlmostEqual(math.dist(points[a], points[b]),
                                           math.dist(result['coordinates_cm'][a], result['coordinates_cm'][b]), places=13)
        for face in payload['faces']:
            for a, b in zip(face, face[1:] + face[:1]):
                self.assertEqual(math.dist(points[a], points[b]),
                                 math.dist(result['coordinates_cm'][a], result['coordinates_cm'][b]))
        self.assertEqual(digest([payload, points, spec, context]), original)
        self.assertEqual(result['source_sha256'], digest(payload))
        self.assertEqual(result['qualification'], 'NONE')
        self.assertEqual(result['simulation'], 'NOT_EXECUTED')
        self.assertEqual(result['fitting'], 'NOT_EXECUTED')
        self.assertEqual(result['final_assessment'], 'FULL_NATIVE_GATES_REQUIRED')
        self.assertEqual(result['native_origin'], 'NOT_ESTABLISHED')

    def test_renamed_and_reordered_panel_and_seam_maps_are_geometry_equivalent(self):
        first = self.run_kernel()
        payload, points, spec, context = fixture(('zebra', 'auxiliary', 'remote', 'optional'))
        payload['panels'] = dict(reversed(list(payload['panels'].items())))
        payload['seams'] = dict(reversed(list(payload['seams'].items())))
        for panel in payload['panels'].values(): panel['indices'].reverse()
        result = self.run_kernel(payload, points, spec, context)
        self.assertEqual(first['coordinates_cm'], result['coordinates_cm'])
        self.assertEqual(first['moving_indices'], result['moving_indices'])
        self.assertEqual(result['groups'], [['auxiliary', 'remote', 'zebra']])

    def test_rotated_body_frame_up_is_normalized_without_world_z_assumption(self):
        payload, points, spec, context = fixture()
        points = [[p[2], p[1], -p[0]] for p in points]
        payload['rest_cm'] = copy.deepcopy(points)
        result = self.run_kernel(payload, points, spec, context,
            body_frame_up=[4., 0., 0.], evaluate=evaluator(context, axis=(1., 0., 0.)))
        self.assertEqual(result['body_frame_up'], [1., 0., 0.])
        self.assertEqual(result['translation_scalar_cm'], 1.5)
        for i in range(9):
            self.assertEqual(result['coordinates_cm'][i], [points[i][0]+1.5, points[i][1], points[i][2]])

    def test_detachable_component_moves_only_when_it_owns_an_explicit_stop(self):
        _, _, _, context = fixture()
        result = self.run_kernel(protected_indices=[9, 0],
                                 evaluate=evaluator(context, stops=(0, 9), moving=range(12)))
        self.assertEqual(result['moving_indices'], list(range(12)))
        self.assertEqual(len(result['groups']), 2)
        self.assertEqual(result['coordinates_cm'][9][2], 1.5)

    def test_closure_does_not_become_a_permanent_join(self):
        payload, points, spec, context = fixture()
        payload['seams']['transitive-link']['kind'] = 'closure'
        result = self.run_kernel(payload, points, spec, context,
                                 evaluate=evaluator(context, moving=range(6)))
        self.assertEqual(result['moving_indices'], list(range(6)))
        self.assertEqual(result['coordinates_cm'][6:], points[6:])

    def test_pin_or_support_in_transitive_component_refuses_before_measurement(self):
        for kind in ('pin', 'support'):
            payload, points, spec, context = fixture()
            options = {'support_indices': [8]} if kind == 'support' else {}
            if kind == 'pin': payload['pins'] = {'8': .2}
            calls = []
            result = self.run_kernel(payload, points, spec, context,
                                     evaluate=lambda *args: calls.append(args), **options)
            self.assertEqual(result['status'], 'REFUSED')
            self.assertEqual(result['stop_reason'], 'FIXED_SUPPORT_IN_SELECTED_COMPONENT')
            self.assertEqual(result['coordinates_cm'], points)
            self.assertEqual(calls, [])

    def test_unselected_fixed_pin_is_preserved_without_preventing_reserve(self):
        payload, points, spec, context = fixture(); payload['pins'] = {'9': 1.}
        result = self.run_kernel(payload, points, spec, context)
        self.assertEqual(result['status'], 'ANCHORS_ADMISSIBLE_ONLY')
        self.assertEqual(result['coordinates_cm'][9], points[9])

    def test_failed_stale_or_missing_rest_precondition_never_calls_contacts(self):
        for precondition in (None, {'status': 'FAILED'}, {'status': 'PASSED', 'source_sha256': 'old'}):
            calls = []
            result = self.run_kernel(rest_precondition=precondition, evaluate=lambda *args: calls.append(args))
            self.assertEqual(result['status'], 'REFUSED')
            self.assertEqual(result['stop_reason'], 'REST_PRECONDITION_REQUIRED')
            self.assertEqual(result['spent_budget']['measurement_calls'], 0)
            self.assertEqual(calls, [])

    def test_unknown_sign_scope_and_stale_identities_never_admit(self):
        _, _, _, context = fixture()
        alterations = [('status', 'AMBIGUOUS'), ('status', 'UNAVAILABLE'), ('sign_status', 'AMBIGUOUS'),
                       ('method', 'NEAREST_TRIANGLE_PROXY'), ('context_identity', {'body_sha256': 'changed'}),
                       ('source_sha256', 'old'), ('candidate_sha256', 'old'), ('moving_indices', [0])]
        for key, value in alterations:
            def bad(payload, points):
                report = evaluator(context)(payload, points); report[key] = value; return report
            with self.subTest(key=key, value=value):
                result = self.run_kernel(evaluate=bad)
                self.assertEqual(result['status'], 'NEEDS_MEASUREMENT')
                self.assertEqual(result['translation_scalar_cm'], 0.)

    def test_missing_duplicate_and_nonfinite_stop_measurements_never_admit(self):
        _, _, _, context = fixture()
        for mode in ('missing', 'duplicate', 'nan', 'negative-clearance', 'bool-index', 'wrong-stop'):
            def bad(payload, points):
                report = evaluator(context, stops=(0, 1))(payload, points)
                if mode == 'missing': report['protected_contacts'].pop()
                if mode == 'duplicate': report['protected_contacts'][1]['vertex'] = 0
                if mode == 'nan': report['protected_contacts'][0]['signed_offset_cm'] = float('nan')
                if mode == 'negative-clearance': report['protected_contacts'][0]['clearance_cm'] = -.1
                if mode == 'bool-index': report['protected_contacts'][0]['vertex'] = False
                if mode == 'wrong-stop': report['protected_contacts'][0]['vertex'] = 2
                return report
            with self.subTest(mode=mode):
                self.assertEqual(self.run_kernel(evaluate=bad, protected_indices=[0, 1])['status'], 'NEEDS_MEASUREMENT')

    def test_bad_callbacks_are_contained_and_do_not_mutate_kernel_inputs(self):
        original = fixture()[0]
        for mode in ('exception', 'mutate-source', 'mutate-coordinates', 'not-dict'):
            def bad(payload, points):
                if mode == 'exception': raise RuntimeError('measurement unavailable')
                if mode == 'mutate-source': payload['pins']['0'] = 1.
                if mode == 'mutate-coordinates': points[0][2] = 99.
                if mode == 'not-dict': return []
                return evaluator(fixture()[3])(payload, points)
            with self.subTest(mode=mode):
                result = self.run_kernel(payload=original, evaluate=bad)
                self.assertEqual(result['status'], 'NEEDS_MEASUREMENT')
                self.assertEqual(result['coordinates_cm'][0][2], 0.)
                self.assertEqual(original, fixture()[0])

    def test_impossible_target_preserves_best_bounded_witness(self):
        payload, points, spec, context = fixture()
        result = self.run_kernel(payload, points, spec, context,
                                 evaluate=evaluator(context, target=10.))
        self.assertEqual(result['status'], 'NEEDS_CORRECTION')
        self.assertEqual(result['stop_reason'], 'DISPLACEMENT_BUDGET')
        self.assertEqual(result['translation_scalar_cm'], 3.)
        self.assertEqual(result['after_measurement']['protected_contacts'][0]['signed_offset_cm'], 3.)
        self.assertEqual(result['maximum_cumulative_displacement_cm'], 3.)

    def test_original_reference_prevents_an_additional_displacement_allowance(self):
        payload, points, spec, context = fixture()
        reference = [[p[0], p[1], p[2]-.9] for p in points]
        spec['budgets']['max_displacement_cm'] = 1.
        spec['budgets']['max_step_cm'] = .05
        result = self.run_kernel(payload, points, spec, context, displacement_reference=reference)
        self.assertEqual(result['status'], 'NEEDS_CORRECTION')
        self.assertEqual(result['stop_reason'], 'CUMULATIVE_DISPLACEMENT_BUDGET')
        self.assertLessEqual(result['maximum_cumulative_displacement_cm'], 1.)
        self.assertAlmostEqual(result['translation_scalar_cm'], .1)
        self.assertEqual(result['displacement_reference_sha256'], digest(reference))
        self.assertEqual(result['initial_displacement_from_reference_cm'], .9)

    def test_entry_already_outside_original_budget_refuses_without_contacts(self):
        payload, points, spec, context = fixture()
        reference = [[p[0], p[1], -4.] for p in points]; calls = []
        result = self.run_kernel(payload, points, spec, context,
            displacement_reference=reference, evaluate=lambda *args: calls.append(args))
        self.assertEqual(result['stop_reason'], 'INITIAL_CUMULATIVE_DISPLACEMENT_BUDGET')
        self.assertEqual(calls, [])

    def test_nonmonotone_progress_stagnates_and_keeps_the_best_measurement(self):
        _, _, _, context = fixture()
        def measured(payload, points):
            report = evaluator(context)(payload, points)
            offset = .1 if points[0][2] >= .5 else 0.
            report['protected_contacts'][0]['signed_offset_cm'] = offset
            return report
        result = self.run_kernel(evaluate=measured)
        self.assertEqual(result['stop_reason'], 'STAGNATION')
        self.assertEqual(result['translation_scalar_cm'], .5)
        self.assertEqual(result['spent_budget']['iterations'], 4)

    def test_measurement_turning_unknown_keeps_previous_exact_witness(self):
        _, _, _, context = fixture()
        def measure(payload, points):
            report = evaluator(context)(payload, points)
            if points[0][2] >= 1.: report['sign_status'] = 'AMBIGUOUS'
            return report
        result = self.run_kernel(evaluate=measure)
        self.assertEqual(result['status'], 'NEEDS_MEASUREMENT')
        self.assertEqual(result['translation_scalar_cm'], .5)
        self.assertEqual(result['after_measurement']['candidate_sha256'], result['candidate_sha256'])

    def test_changing_clearance_without_changing_context_is_refused(self):
        _, _, _, context = fixture()
        def measure(payload, points):
            report = evaluator(context)(payload, points)
            if points[0][2] >= .5: report['protected_contacts'][0]['clearance_cm'] = 0.
            return report
        result = self.run_kernel(evaluate=measure)
        self.assertEqual(result['status'], 'NEEDS_MEASUREMENT')
        self.assertEqual(result['stop_reason'], 'CHANGED_CLEARANCE_CONTROL')
        self.assertEqual(result['translation_scalar_cm'], 0.)

    def test_nonmonotone_clock_is_refused_and_never_admits(self):
        ticks = iter([1., 0.])
        with self.assertRaisesRegex(StudioError, 'monotone'):
            self.run_kernel(clock=lambda: next(ticks))

    def test_elapsed_measurement_budget_cannot_grant_late_admissibility(self):
        _, _, _, context = fixture(); clock = Clock()
        def measure(payload, points):
            report = evaluator(context, target=.5)(payload, points)
            if points[0][2] >= .5: clock.value = 11.
            return report
        result = self.run_kernel(evaluate=measure, clock=clock)
        self.assertEqual(result['status'], 'NEEDS_MEASUREMENT')
        self.assertEqual(result['stop_reason'], 'TIME_BUDGET')
        self.assertEqual(result['translation_scalar_cm'], 0.)
        self.assertEqual(result['spent_budget']['measurement_calls'], 2)

    def test_iteration_budget_is_separate_from_initial_measurement(self):
        payload, points, spec, context = fixture(); spec['budgets']['max_iterations'] = 1
        result = self.run_kernel(payload, points, spec, context)
        self.assertEqual(result['stop_reason'], 'ITERATION_BUDGET')
        self.assertEqual(result['spent_budget']['iterations'], 1)
        self.assertEqual(result['spent_budget']['measurement_calls'], 2)

    def test_initial_success_is_only_anchor_success_and_never_ready(self):
        _, _, _, context = fixture()
        result = self.run_kernel(evaluate=evaluator(context, target=0.))
        self.assertEqual(result['status'], 'ANCHORS_ADMISSIBLE_ONLY')
        self.assertEqual(result['stop_reason'], 'INITIAL_ANCHORS_ADMISSIBLE')
        self.assertEqual(result['spent_budget']['iterations'], 0)
        self.assertEqual(result['qualification'], 'NONE')

    def test_invalid_axis_supports_stops_and_budgets_refuse(self):
        for axis in ([0., 0., 0.], [float('nan'), 0., 1.], [0., False, 1.], [0., 1.]):
            with self.subTest(axis=axis), self.assertRaises(StudioError):
                self.run_kernel(body_frame_up=axis)
        for indices in ([0, 0], [True], [12], []):
            with self.subTest(indices=indices), self.assertRaises(StudioError):
                self.run_kernel(protected_indices=indices)
        for key, value in (('max_iterations', True), ('max_step_cm', 0.),
                           ('max_seconds', float('inf')), ('stagnation_iterations', 0)):
            payload, points, spec, context = fixture(); spec['budgets'][key] = value
            with self.subTest(key=key), self.assertRaises(StudioError):
                self.run_kernel(payload, points, spec, context)

    def test_malformed_mesh_source_ownership_faces_and_seams_refuse(self):
        for mode in ('rest', 'uv', 'duplicate-owner', 'missing-owner', 'bad-face', 'mixed-face', 'bad-pair', 'bad-kind'):
            payload, points, spec, context = fixture()
            if mode == 'rest': payload['rest_cm'].pop()
            if mode == 'uv': payload['uv_cm'][0] = [float('nan'), 0.]
            if mode == 'duplicate-owner': payload['panels']['partner']['indices'].append(0)
            if mode == 'missing-owner': payload['panels']['first']['indices'].pop()
            if mode == 'bad-face': payload['faces'][0] = [0, 0, 1]
            if mode == 'mixed-face': payload['faces'][0] = [0, 1, 3]
            if mode == 'bad-pair': payload['seams']['first-link']['pairs'] = [[1, 6]]
            if mode == 'bad-kind': payload['seams']['first-link']['kind'] = 'implicit-weld'
            with self.subTest(mode=mode), self.assertRaises(StudioError):
                self.run_kernel(payload, points, spec, context, rest_precondition=None)

    def test_explicit_opt_in_and_original_reference_are_required(self):
        payload, points, spec, context = fixture(); spec['enabled'] = False
        with self.assertRaises(StudioError): self.run_kernel(payload, points, spec, context)
        spec['enabled'] = True; spec['version'] = True
        with self.assertRaises(StudioError): self.run_kernel(payload, points, spec, context)
        with self.assertRaises(StudioError): self.run_kernel(displacement_reference=None)
        with self.assertRaises(StudioError): self.run_kernel(context={})


if __name__ == '__main__':
    unittest.main()
