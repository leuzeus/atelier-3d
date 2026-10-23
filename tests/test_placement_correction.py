import copy
import math
import unittest
from a3d.core import StudioError, digest
from a3d.placement_correction import correct_placement, rigid_candidate
from tests.test_pattern_assembly import example


def motion(dx):
    return {'panels': ['right'], 'rotation': [[1., 0., 0.], [0., 1., 0.], [0., 0., 1.]],
            'origin_cm': [0., 0., 0.], 'translation_cm': [dx, 0., 0.]}


def fixture():
    payload, _ = example()
    coordinates = copy.deepcopy(payload['rest_cm'])
    for point in coordinates[4:]: point[0] += 4.; point[2] = 0.
    budget = {'max_iterations': 10, 'max_proposals_per_iteration': 3, 'max_seconds': 10.,
              'max_displacement_cm': 3., 'stagnation_iterations': 2, 'target_score': .001,
              'min_improvement': .0001}
    def measure(source, points):
        gaps = [math.dist(points[a], points[b]) for a, b in source['seams']['join']['pairs']]
        return {'score': max(gaps), 'hard_valid': True, 'seam_gaps_cm': gaps}
    return payload, coordinates, budget, measure


class PlacementCorrection(unittest.TestCase):
    def test_two_invalid_panels_can_only_be_repaired_by_one_atomic_measured_candidate(self):
        payload,coords,budget,_=fixture();before=digest([payload,coords])
        left={**motion(1.),'panels':['left']};right=motion(-1.)
        def evaluate(source,points):
            valid=points[0][0]==coords[0][0]+1. and points[4][0]==coords[4][0]-1.
            return {'hard_valid':valid,'score':0. if valid else 1.}
        result=correct_placement(payload,coords,evaluate,
            lambda *args:[left,right,{'motions':[left,right]}],budget)
        self.assertEqual(result['stop_reason'],'TARGET_REACHED')
        self.assertEqual([row['kept'] for row in result['history']],[False,False,True])
        self.assertEqual(digest([payload,coords]),before)
        with self.assertRaises(StudioError):rigid_candidate(payload,coords,{'motions':[left,left]})
        with self.assertRaises(StudioError):rigid_candidate(payload,coords,{'motions':[{'motions':[left]}]})

    def test_keeps_measured_improvement_and_preserves_approved_source(self):
        payload, coords, budget, measure = fixture(); before = digest([payload, coords, budget])
        result = correct_placement(payload, coords, measure, lambda *args: [motion(-.5)], budget)
        self.assertEqual(result['stop_reason'], 'TARGET_REACHED')
        self.assertEqual(result['measurement']['score'], 0.)
        self.assertEqual(result['simulation'], 'NOT_EXECUTED')
        self.assertEqual(digest([payload, coords, budget]), before)
        self.assertEqual(result['coordinates_cm'][:4], coords[:4])

    def test_worse_hard_failure_repeated_and_over_budget_trials_are_undone(self):
        payload, coords, budget, measure = fixture()
        def proposals(*args): return [motion(1.), motion(0.), motion(-10.)]
        result = correct_placement(payload, coords, measure, proposals, budget)
        self.assertEqual(result['stop_reason'], 'STAGNATION')
        self.assertEqual(result['coordinates_cm'], coords)
        self.assertEqual({row['reason'] for row in result['history']},
                         {'HARD_GATE_OR_NO_IMPROVEMENT', 'REPEATED_CANDIDATE', 'DISPLACEMENT_BUDGET'})
        def hard_gate(source, points): return dict(measure(source, points), hard_valid=points[4][0] >= 4.)
        result = correct_placement(payload, coords, hard_gate, lambda *args: [motion(-.5)], budget)
        self.assertEqual(result['coordinates_cm'], coords)

    def test_scale_shear_reflection_and_source_edit_proposals_are_refused(self):
        payload, coords, _, _ = fixture()
        for failure in ('scale', 'shear', 'reflect', 'source'):
            proposal = motion(0.)
            if failure == 'scale': proposal['rotation'][0][0] = 2.
            if failure == 'shear': proposal['rotation'][0][1] = .1
            if failure == 'reflect': proposal['rotation'][0][0] = -1.
            if failure == 'source': proposal['rest_cm'] = []
            with self.subTest(failure=failure), self.assertRaises(StudioError): rigid_candidate(payload, coords, proposal)

    def test_callbacks_cannot_mutate_sources_or_return_nonfinite_proof(self):
        for failure in ('evaluate', 'propose', 'nan'):
            payload, coords, budget, measure = fixture()
            def evaluator(source, points):
                if failure == 'evaluate': source['pins']['0'] = 1.
                return {'score': math.nan if failure == 'nan' else 2., 'hard_valid': True}
            def proposer(source, points, report):
                if failure == 'propose': source['seams'].clear()
                return [motion(-.5)]
            with self.subTest(failure=failure), self.assertRaises(StudioError):
                correct_placement(payload, coords, evaluator, proposer, budget)

    def test_time_and_iteration_budgets_preserve_best_measured_candidate(self):
        payload, coords, budget, measure = fixture(); budget['max_iterations'] = 1
        result = correct_placement(payload, coords, measure, lambda *args: [motion(-.5)], budget)
        self.assertEqual(result['stop_reason'], 'ITERATION_BUDGET')
        self.assertEqual(result['measurement']['score'], 1.5)
        ticks = iter([0., 0., 20., 20.])
        result = correct_placement(payload, coords, measure, lambda *args: [], budget, clock=lambda: next(ticks))
        self.assertEqual(result['stop_reason'], 'TIME_BUDGET')
        self.assertEqual(result['coordinates_cm'], coords)
