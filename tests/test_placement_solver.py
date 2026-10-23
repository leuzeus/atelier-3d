import copy
import unittest

from a3d.core import StudioError, digest
from a3d.placement_solver import solve_placement, constrained_relaxation_candidate


def fixture():
    points = [[0., 0., 0.], [2., 0., 0.], [2., 2., 0.], [0., 2., 0.]]
    payload = {'rest_cm': points, 'faces': [[0, 1, 2], [0, 2, 3]],
               'panels': {'source-panel': {'indices': [0, 1, 2, 3]}}, 'pins': {}, 'seams': {}}
    placed = [[x, y, -.8] for x, y, z in points]
    spec = {'version': 1, 'kernels': ['rigid', 'relaxation'],
        'quality': {'min_angle_degrees': 10., 'min_edge_cm': .1, 'min_stretch': .9, 'max_stretch': 1.1},
        'budgets': {'max_iterations': 10, 'max_seconds': 10., 'max_proposals_per_iteration': 5,
                   'max_displacement_cm': 2., 'max_step_cm': .2, 'stagnation_iterations': 2,
                   'min_improvement': .00001, 'target_score': .000001}}

    def evaluate(source, candidate):
        score = max(max(0., .1-p[2]) for p in candidate)
        return {'score': score, 'hard_valid': score <= .000001,
                'candidate_sha256': digest(candidate),
                'contacts': [{'vertex': i, 'normal': [0., 0., 1.], 'signed_offset_cm': p[2],
                              'clearance_cm': .1} for i, p in enumerate(candidate)]}
    return payload, placed, spec, evaluate


class PlacementSolver(unittest.TestCase):
    def test_explicit_measured_stop_reference_allows_shifted_numerical_stop_with_no_fitting_claim(self):
        payload,original,spec,evaluate=fixture();entry=[[x,y,z+1.]for x,y,z in original]
        spec['protected_indices']=[0];stop_reference=copy.deepcopy(entry)
        before=digest([payload,original,entry,spec,stop_reference])
        result=solve_placement(payload,entry,evaluate,spec,clock=lambda:0.,
            displacement_reference=original,protected_stop_reference=stop_reference)
        self.assertEqual(result['status'],'GEOMETRIC_GATES_PASSED')
        self.assertEqual(result['coordinates_cm'][0],entry[0])
        self.assertEqual(result['protected_stop_reference_sha256'],digest(stop_reference))
        self.assertEqual(result['displacement_reference_sha256'],digest(original))
        self.assertEqual(result['numerical_fixed_indices'],[0])
        self.assertEqual(result['physical_fixed_indices'],[])
        self.assertEqual(result['relocated_numerical_stop_indices'],[0])
        self.assertEqual(result['max_displacement_cm'],1.)
        self.assertEqual(result['qualification'],'NONE');self.assertEqual(result['simulation'],'NOT_EXECUTED')
        self.assertEqual(result['fitting'],'NOT_EXECUTED')
        self.assertEqual(result['final_assessment'],'REQUIRED_BEFORE_NATIVE_ADMISSION')
        self.assertEqual(before,digest([payload,original,entry,spec,stop_reference]))

    def test_proposals_keep_shifted_numerical_stop_exact_and_retain_existing_metric_gates(self):
        payload,original,spec,_=fixture();entry=copy.deepcopy(payload['rest_cm'])
        spec['protected_indices']=[0]
        def measure(source,candidate):
            deficit=max(0.,.2-candidate[1][2])
            return {'score':deficit,'hard_valid':deficit<=1e-8,'candidate_sha256':digest(candidate),
                    'contacts':[{'vertex':1,'normal':[0.,0.,1.],
                                 'signed_offset_cm':candidate[1][2],'clearance_cm':.2}]}
        result=solve_placement(payload,entry,measure,spec,clock=lambda:0.,
            displacement_reference=original,protected_stop_reference=entry)
        self.assertEqual(result['status'],'GEOMETRIC_GATES_PASSED')
        self.assertEqual(result['coordinates_cm'][0],entry[0])
        self.assertGreater(result['coordinates_cm'][1][2],entry[1][2])
        self.assertTrue(any(row['kernel']=='relaxation' and row['kept'] for row in result['history']))
        self.assertLessEqual(result['max_displacement_cm'],2.)
        self.assertEqual(result['protected_indices'],[0])

    def test_explicit_stop_reference_keeps_total_original_displacement_budget(self):
        import math
        payload,_,spec,_=fixture();entry=copy.deepcopy(payload['rest_cm'])
        original=[[x,y,z-1.8]for x,y,z in entry];spec['protected_indices']=[0]
        def measure(source,candidate):
            deficit=max(0.,.5-candidate[1][2])
            return {'score':deficit,'hard_valid':deficit<=1e-8,
                    'contacts':[{'vertex':1,'normal':[0.,0.,1.],
                                 'signed_offset_cm':candidate[1][2],'clearance_cm':.5}]}
        result=solve_placement(payload,entry,measure,spec,clock=lambda:0.,
            displacement_reference=original,protected_stop_reference=entry)
        self.assertEqual(result['status'],'NEEDS_CORRECTION')
        self.assertTrue(any(row['reason']=='DISPLACEMENT_BUDGET'for row in result['history']))
        self.assertLessEqual(result['max_displacement_cm'],2.)
        self.assertLessEqual(max(math.dist(a,b)for a,b in zip(original,result['coordinates_cm'])),2.)
        self.assertEqual(result['coordinates_cm'][0],entry[0])
        self.assertEqual(result['displacement_reference_sha256'],digest(original))

    def test_default_shifted_protected_stop_policy_and_receipt_shape_are_unchanged(self):
        payload,original,spec,evaluate=fixture();spec['protected_indices']=[0]
        entry=[[x,y,z+.1]for x,y,z in original]
        for options in ({},{'protected_stop_reference':None}):
            with self.subTest(options=options),self.assertRaisesRegex(StudioError,'protected original source-guide support'):
                solve_placement(payload,entry,evaluate,spec,displacement_reference=original,**options)
        baseline=solve_placement(payload,original,evaluate,spec,clock=lambda:0.)
        explicit_none=solve_placement(payload,original,evaluate,spec,clock=lambda:0.,protected_stop_reference=None)
        self.assertEqual(baseline,explicit_none)
        for key in ('protected_stop_reference_sha256','numerical_fixed_indices','physical_fixed_indices',
                    'relocated_numerical_stop_indices','protected_stop_reference_policy'):
            self.assertNotIn(key,baseline)

    def test_physical_pins_cannot_move_even_with_measured_stop_reference(self):
        for index in (0,1):
            payload,original,spec,evaluate=fixture();spec['protected_indices']=[0]
            payload['pins']={str(index):.2};entry=[[x,y,z+.1]for x,y,z in original]
            before=digest([payload,original,spec,entry])
            with self.subTest(pin=index),self.assertRaisesRegex(StudioError,'protected original source-guide support'):
                solve_placement(payload,entry,evaluate,spec,displacement_reference=original,protected_stop_reference=entry)
            self.assertEqual(before,digest([payload,original,spec,entry]))

    def test_missing_stale_or_malformed_measured_stop_reference_refuses_before_evaluation(self):
        for kind in ('stale','missing-row','bad-dimension','nan','bool','no-original','no-indices'):
            payload,original,spec,evaluate=fixture();entry=[[x,y,z+.1]for x,y,z in original]
            spec['protected_indices']=[0];reference=copy.deepcopy(entry);calls=[]
            options={'displacement_reference':original,'protected_stop_reference':reference}
            if kind=='stale':reference[0][2]+=.01
            if kind=='missing-row':reference.pop()
            if kind=='bad-dimension':reference[0].pop()
            if kind=='nan':reference[1][2]=float('nan')
            if kind=='bool':reference[1][2]=False
            if kind=='no-original':options.pop('displacement_reference')
            if kind=='no-indices':spec.pop('protected_indices')
            with self.subTest(kind=kind),self.assertRaises(StudioError):
                solve_placement(payload,entry,lambda *args:calls.append(args),spec,**options)
            self.assertEqual(calls,[])

    def test_external_mutation_of_measured_stop_reference_is_detected(self):
        payload,original,spec,evaluate=fixture();entry=[[x,y,z+1.]for x,y,z in original]
        spec['protected_indices']=[0];reference=copy.deepcopy(entry)
        def mutate(source,candidate):
            reference[1][0]+=.01
            return evaluate(source,candidate)
        with self.assertRaisesRegex(StudioError,'source changed'):
            solve_placement(payload,entry,mutate,spec,clock=lambda:0.,
                displacement_reference=original,protected_stop_reference=reference)

    def test_late_clock_mutation_of_stop_reference_is_detected_before_return(self):
        payload,original,spec,evaluate=fixture();entry=[[x,y,z+1.]for x,y,z in original]
        spec['protected_indices']=[0];reference=copy.deepcopy(entry);calls=0
        def clock():
            nonlocal calls
            calls+=1
            if calls==2:reference[1][0]+=.01
            return 0.
        with self.assertRaisesRegex(StudioError,'source changed before returning'):
            solve_placement(payload,entry,evaluate,spec,clock=clock,
                displacement_reference=original,protected_stop_reference=reference)

    def test_rigid_stagnation_enters_relaxation_even_with_one_proposal_slot(self):
        payload,points,spec,_=fixture();points=copy.deepcopy(payload['rest_cm']);payload['pins']={'0':1.}
        spec['budgets']['max_proposals_per_iteration']=1
        def evaluate(source,candidate):
            deficit=max(0.,.1-candidate[1][2])
            return {'score':deficit,'hard_valid':deficit<=1e-8,'contacts':[{'vertex':1,'normal':[0.,0.,1.],
                'signed_offset_cm':candidate[1][2],'clearance_cm':.1}]}
        result=solve_placement(payload,points,evaluate,spec)
        self.assertEqual(result['status'],'GEOMETRIC_GATES_PASSED')
        self.assertEqual(result['terminal_kernel_phase'],'relaxation')
        self.assertEqual(result['coordinates_cm'][0],points[0])
        self.assertTrue(any(row['kernel']=='relaxation' and row['kept'] for row in result['history']))

    def test_contact_failures_can_improve_before_final_gates_pass_without_mutating_source(self):
        payload, points, spec, evaluate = fixture(); before = digest([payload, points, spec])
        result = solve_placement(payload, points, evaluate, spec)
        kept = [record for record in result['history'] if record['kept']]
        self.assertFalse(kept[0]['measurement']['hard_valid'])
        self.assertEqual(result['stop_reason'], 'FINAL_GATES_PASSED')
        self.assertEqual(result['status'], 'GEOMETRIC_GATES_PASSED')
        self.assertTrue(result['measurement']['hard_valid'])
        self.assertEqual(result['qualification'], 'NONE')
        self.assertEqual(result['simulation'], 'NOT_EXECUTED')
        self.assertEqual(digest([payload, points, spec]), before)

    def test_final_failure_never_becomes_ready_even_at_target_score(self):
        payload, points, spec, evaluate = fixture()
        def reject(source, candidate):
            report = evaluate(source, candidate); report['hard_valid'] = False
            return report
        result = solve_placement(payload, points, reject, spec)
        self.assertEqual(result['measurement']['score'], 0.)
        self.assertEqual(result['status'], 'NEEDS_CORRECTION')
        self.assertEqual(result['stop_reason'], 'STAGNATION')

    def test_pins_and_explicit_supports_remain_fixed_during_relaxation(self):
        payload, points, spec, evaluate = fixture()
        payload['pins']['0'] = .25; spec['protected_indices'] = [1]
        spec['kernels'] = ['relaxation']
        result = solve_placement(payload, points, evaluate, spec)
        self.assertEqual(result['coordinates_cm'][0], points[0])
        self.assertEqual(result['coordinates_cm'][1], points[1])
        self.assertEqual(result['protected_indices'], [0, 1])
        self.assertEqual(result['status'], 'NEEDS_CORRECTION')

    def test_metric_violation_rolls_back_candidate_and_displacement_limits_hold(self):
        payload, points, spec, evaluate = fixture()
        spec['kernels'] = ['relaxation']; payload['pins'] = {'0': 1., '1': 1., '2': 1.}
        spec['quality']['min_stretch'] = .999; spec['quality']['max_stretch'] = 1.001
        result = solve_placement(payload, points, evaluate, spec)
        self.assertTrue(any(row['reason'] == 'SOURCE_METRIC_OR_TRAJECTORY_GATE' for row in result['history']))
        self.assertEqual(result['coordinates_cm'], points)
        payload, points, spec, evaluate = fixture(); spec['budgets']['max_displacement_cm'] = .1
        result = solve_placement(payload, points, evaluate, spec)
        self.assertEqual(result['status'], 'NEEDS_CORRECTION')
        self.assertTrue(any(row['reason'] == 'DISPLACEMENT_BUDGET' for row in result['history']))

    def test_stale_nonfinite_and_mutating_evaluations_are_refused(self):
        for failure in ('stale', 'nan', 'mutate', 'normal'):
            payload, points, spec, evaluate = fixture()
            def bad(source, candidate):
                report = evaluate(source, candidate)
                if failure == 'stale': report['candidate_sha256'] = 'old'
                if failure == 'nan': report['score'] = float('nan')
                if failure == 'mutate': source['pins']['0'] = 1.
                if failure == 'normal': report['contacts'][0]['normal'] = [0., 0., 5.]
                return report
            with self.subTest(failure=failure), self.assertRaises(StudioError):
                solve_placement(payload, points, bad, spec)

    def test_time_budget_preserves_last_measured_geometry(self):
        payload, points, spec, evaluate = fixture()
        ticks = iter([0., 20., 20.])
        result = solve_placement(payload, points, evaluate, spec, clock=lambda: next(ticks))
        self.assertEqual(result['stop_reason'], 'TIME_BUDGET')
        self.assertEqual(result['coordinates_cm'], points)

    def test_prior_metric_correction_does_not_create_a_second_displacement_allowance(self):
        payload,points,spec,evaluate=fixture()
        reference=[[x,y,z-.8] for x,y,z in points]
        spec['budgets']['max_displacement_cm']=1.
        result=solve_placement(payload,points,evaluate,spec,displacement_reference=reference)
        self.assertEqual(result['status'],'NEEDS_CORRECTION')
        self.assertTrue(any(row['reason']=='DISPLACEMENT_BUDGET' for row in result['history']))
        self.assertLessEqual(result['max_displacement_cm'],1.)
        self.assertEqual(result['displacement_reference_sha256'],digest(reference))
        reference=[[x,y,z-2.] for x,y,z in points]
        with self.assertRaisesRegex(StudioError,'already exceeds'):
            solve_placement(payload,points,evaluate,spec,displacement_reference=reference)


if __name__ == '__main__':
    unittest.main()
