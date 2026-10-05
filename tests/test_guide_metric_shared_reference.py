"""Differentiating guards for a prior numeric injection and shared deadline."""
import copy
import inspect
import math
import unittest
from unittest.mock import patch

from a3d.core import StudioError,digest
from a3d import guide_metric_solver as solver
from tests.test_guide_metric_solver import fixture,seamed_fixture


class Clock:
    def __init__(self,value=0.):self.value=value
    def __call__(self):return self.value


class SharedGuideReference(unittest.TestCase):
    def run_coupon(self,source,entry,quality,**options):
        return solver.recover_guide_metric(source,entry,quality,['panel'],
            [{'piece':'panel','edge':'anchor'}],clock=options.pop('clock',lambda:0.),**options)

    def test_prior_displacement_spends_the_same_total_budget(self):
        source,entry,quality=fixture();reference=copy.deepcopy(entry)
        reference[1][0]=reference[2][0]=.1
        inputs=digest([source,entry,reference,quality])
        result=self.run_coupon(source,entry,quality,displacement_reference=reference,
            max_displacement_cm=1.,max_iterations=6,stagnation_iterations=2)
        self.assertEqual(result['status'],'NEEDS_CORRECTION')
        self.assertAlmostEqual(result['initial_displacement_from_reference_cm'],.9)
        self.assertLessEqual(result['max_displacement_cm'],1.)
        self.assertLessEqual(max(math.dist(a,b)for a,b in zip(reference,result['coordinates_cm'])),1.)
        self.assertTrue(all(row['max_displacement_cm']<=1. for row in result['history']))
        self.assertEqual(inputs,digest([source,entry,reference,quality]))

    def test_entry_beyond_original_budget_refuses_before_metrics(self):
        source,entry,quality=fixture();reference=copy.deepcopy(entry);reference[1][0]-=1.
        with patch.object(solver,'evaluate_metrics',side_effect=AssertionError('Entry must refuse first')):
            with self.assertRaisesRegex(StudioError,'Initial guide candidate exceeds the shared'):
                self.run_coupon(source,entry,quality,displacement_reference=reference,max_displacement_cm=.5)

    def test_numerical_target_can_differ_from_reference_without_becoming_a_pin(self):
        source,_,quality=fixture();reference=copy.deepcopy(source['rest_cm']);entry=copy.deepcopy(reference)
        entry[1][0]+=.05;original=digest([source,entry,reference])
        result=self.run_coupon(source,entry,quality,displacement_reference=reference,protected_indices=[1])
        self.assertEqual(result['status'],'SOURCE_METRIC_RECOVERED')
        self.assertEqual(result['coordinates_cm'][1],entry[1]);self.assertEqual(source['pins'],{})
        self.assertEqual(result['physical_fixed_indices'],[0,3])
        self.assertEqual(result['initial_candidate_sha256'],digest(entry))
        self.assertEqual(result['displacement_reference_sha256'],digest(reference))
        self.assertNotEqual(result['initial_candidate_sha256'],result['displacement_reference_sha256'])
        self.assertEqual(original,digest([source,entry,reference]))

    def test_physical_pin_and_named_source_stops_cannot_be_injected(self):
        for kind,index in [('pin',1),('stop',0)]:
            with self.subTest(kind=kind):
                source,_,quality=fixture();reference=copy.deepcopy(source['rest_cm']);entry=copy.deepcopy(reference)
                if kind=='pin':source['pins']={'1':.2}
                entry[index][2]=.01;before=digest([source,entry,reference])
                with self.assertRaisesRegex(StudioError,'physical pin or protected source stop'):
                    self.run_coupon(source,entry,quality,displacement_reference=reference,protected_indices=[index])
                self.assertEqual(before,digest([source,entry,reference]))

    def test_alignment_is_bounded_against_each_original_owner_reference(self):
        source,entry,quality,edges=seamed_fixture();reference=copy.deepcopy(entry)
        for i in (1,2):reference[i][0]=0.
        for i in (4,7):reference[i][0]=2.;entry[i][0]=3.
        before=digest([source,entry,reference])
        with self.assertRaisesRegex(StudioError,'alignment exceeds the shared original-guide'):
            solver.recover_guide_metric(source,entry,quality,['a','b'],edges,clock=lambda:0.,
                seam_ids=['ab'],max_initial_seam_gap_cm=2.,max_displacement_cm=1.,max_step_cm=2.,
                displacement_reference=reference)
        self.assertEqual(before,digest([source,entry,reference]))

    def test_alignment_actual_step_cannot_exceed_limit(self):
        source,entry,quality,edges=seamed_fixture();reference=copy.deepcopy(entry)
        for i in (4,7):entry[i][0]+=.2
        with self.assertRaisesRegex(StudioError,'alignment exceeds the measured step'):
            solver.recover_guide_metric(source,entry,quality,['a','b'],edges,clock=lambda:0.,
                seam_ids=['ab'],max_initial_seam_gap_cm=.3,max_step_cm=.05,
                displacement_reference=reference)

    def test_aligned_numerical_target_remains_fixed_for_the_whole_cohort(self):
        source,entry,quality,edges=seamed_fixture();reference=copy.deepcopy(entry)
        for i in (1,4):entry[i][0]+=.05
        result=solver.recover_guide_metric(source,entry,quality,['a','b'],edges,clock=lambda:0.,
            seam_ids=['ab'],max_initial_seam_gap_cm=0.,protected_indices=[1],
            displacement_reference=reference,max_iterations=2)
        self.assertEqual(result['coordinates_cm'][1],entry[1])
        self.assertEqual(result['coordinates_cm'][4],entry[1])
        self.assertIn(4,result['seam_coupling']['fixed_cohort_indices'])
        self.assertEqual(result['seam_coupling']['final_max_cohort_gap_cm'],0.)

    def test_real_rounded_steps_are_remeasured_without_epsilon(self):
        source,entry,quality=fixture()
        # A large exact world offset makes 0.05 algebraic clipping round to a
        # larger representable displacement; backtracking must retain <=0.05.
        for p in source['rest_cm']:p[0]+=1e12
        entry=[[1e12+(x-1e12)*.5,y,z]for x,y,z in source['rest_cm']]
        reference=copy.deepcopy(entry)
        self.assertGreater((1e12+.05)-1e12,.05)
        result=self.run_coupon(source,entry,quality,displacement_reference=reference,
            max_step_cm=.05,max_iterations=2)
        accepted=[row for row in result['history']if row['accepted']]
        self.assertTrue(accepted)
        self.assertTrue(all(row['actual_step_cm']<=.05 for row in accepted))
        self.assertEqual(max(math.dist(a,b)for a,b in zip(reference,result['coordinates_cm'])),result['max_displacement_cm'])

    def test_absolute_deadline_and_local_time_limit_use_the_stricter_bound(self):
        source,_,quality=fixture();entry=copy.deepcopy(source['rest_cm'])
        for declared,expected in [(650.,600.),(550.,550.)]:
            with self.subTest(deadline=declared):
                result=self.run_coupon(source,entry,quality,deadline=declared,clock=Clock(500.),max_seconds=100.)
                self.assertEqual(result['shared_deadline']['effective_absolute'],expected)
                self.assertEqual(result['status'],'SOURCE_METRIC_RECOVERED')

    def test_expired_deadline_refuses_before_any_metric_work(self):
        source,entry,quality=fixture()
        with patch.object(solver,'evaluate_metrics',side_effect=AssertionError('Expired entry must not evaluate')):
            with self.assertRaisesRegex(StudioError,'shared deadline exhausted during entry'):
                self.run_coupon(source,entry,quality,deadline=1.,clock=Clock(1.))

    def test_deadline_expiring_during_initial_metric_is_not_admitted(self):
        source,entry,quality=fixture();clock=Clock();original=solver.evaluate_metrics
        def expires(*args,**kwargs):
            result=original(*args,**kwargs);clock.value=2.;return result
        with patch.object(solver,'evaluate_metrics',side_effect=expires):
            with self.assertRaisesRegex(StudioError,'during initial_metric'):
                self.run_coupon(source,entry,quality,deadline=1.,clock=clock)

    def test_deadline_expiring_in_residual_preflight_is_not_admitted(self):
        source,entry,quality=fixture();clock=Clock();original=solver._dot
        def expires(*args):
            if inspect.currentframe().f_back.f_code.co_name=='residual':clock.value=2.
            return original(*args)
        with patch.object(solver,'_dot',new=expires):
            with self.assertRaisesRegex(StudioError,'during residual'):
                self.run_coupon(source,entry,quality,deadline=1.,clock=clock)

    def test_deadline_in_matrix_assembly_restores_entry_best(self):
        source,entry,quality=fixture();clock=Clock();original=solver._dot
        def expires(*args):
            # _dot is called by residual and by assembly. Expire only assembly.
            frame=inspect.currentframe().f_back
            if frame.f_code.co_name=='recover_guide_metric' and 'iteration' in frame.f_locals:clock.value=2.
            return original(*args)
        with patch.object(solver,'_dot',new=expires):
            result=self.run_coupon(source,entry,quality,deadline=1.,clock=clock)
        self.assertEqual(result['status'],'NEEDS_CORRECTION');self.assertEqual(result['stop_reason'],'TIME_BUDGET')
        self.assertEqual(result['coordinates_cm'],entry);self.assertEqual(result['history'],[])
        self.assertEqual(result['shared_deadline']['expired_phase'],'matrix_assembly')

    def test_deadline_in_pcg_keeps_prior_best_and_never_grants_admission(self):
        source,entry,quality=fixture();clock=Clock();original=solver._pcg
        def expires(*args,**kwargs):
            result=original(*args,**kwargs);clock.value=2.;return result
        with patch.object(solver,'_pcg',side_effect=expires):
            result=self.run_coupon(source,entry,quality,deadline=1.,clock=clock)
        self.assertEqual(result['coordinates_cm'],entry);self.assertEqual(result['status'],'NEEDS_CORRECTION')
        self.assertEqual(result['stop_reason'],'TIME_BUDGET');self.assertEqual(result['shared_deadline']['expired_phase'],'pcg')

    def test_deadline_after_an_improvement_returns_the_previous_best(self):
        source,entry,quality=fixture();clock=Clock();original=solver._pcg;calls=0
        original_motion=solver.validate_linear_motion;validated=[]
        def observed_motion(payload,before,after):
            result=original_motion(payload,before,after);validated.append(copy.deepcopy(after));return result
        def expires(*args,**kwargs):
            nonlocal calls
            calls+=1;result=original(*args,**kwargs)
            if calls==5:clock.value=2.
            return result
        with patch.object(solver,'_pcg',side_effect=expires),patch.object(solver,'validate_linear_motion',new=observed_motion):
            result=self.run_coupon(source,entry,quality,deadline=1.,clock=clock,max_step_cm=.2)
        self.assertEqual(result['status'],'NEEDS_CORRECTION');self.assertEqual(result['stop_reason'],'TIME_BUDGET')
        self.assertEqual(len(result['history']),1);self.assertTrue(result['history'][0]['accepted'])
        self.assertNotEqual(result['coordinates_cm'],entry)
        self.assertEqual(result['coordinates_cm'],validated[-1])
        self.assertEqual(result['history'][0]['max_displacement_cm'],result['max_displacement_cm'])

    def test_failed_later_proposals_keep_the_exact_previous_best(self):
        source,entry,quality=fixture();reference=copy.deepcopy(entry);validated=[]
        original=solver.validate_linear_motion
        def observed(payload,before,after):
            result=original(payload,before,after);validated.append(copy.deepcopy(after));return result
        with patch.object(solver,'validate_linear_motion',new=observed):
            result=self.run_coupon(source,entry,quality,displacement_reference=reference,
                max_displacement_cm=.11,max_step_cm=.2,max_iterations=2)
        self.assertEqual(result['status'],'NEEDS_CORRECTION')
        self.assertTrue(result['history'][0]['accepted']);self.assertFalse(result['history'][1]['accepted'])
        self.assertEqual(len(validated),1);self.assertEqual(result['coordinates_cm'],validated[0])
        self.assertLessEqual(result['max_displacement_cm'],.11)

    def test_deadline_in_semantic_cohort_preflight_refuses_without_source_mutation(self):
        source,entry,quality,edges=seamed_fixture();reference=copy.deepcopy(entry);clock=Clock()
        original=solver._semantic_cohorts;before=digest([source,entry,reference])
        def expires(*args,**kwargs):
            clock.value=2.;return original(*args,**kwargs)
        with patch.object(solver,'_semantic_cohorts',side_effect=expires):
            with self.assertRaisesRegex(StudioError,'time budget exhausted before alignment'):
                solver.recover_guide_metric(source,entry,quality,['a','b'],edges,clock=clock,
                    seam_ids=['ab'],max_initial_seam_gap_cm=0.,displacement_reference=reference,deadline=1.)
        self.assertEqual(before,digest([source,entry,reference]))

    def test_deadline_in_fixed_stop_preflight_refuses(self):
        source,entry,quality=fixture();clock=Clock();original=solver._fixed_stop_bounds
        def expires(*args,**kwargs):
            clock.value=2.;return original(*args,**kwargs)
        with patch.object(solver,'_fixed_stop_bounds',side_effect=expires):
            with self.assertRaisesRegex(StudioError,'preflight time budget exhausted'):
                self.run_coupon(source,entry,quality,deadline=1.,clock=clock)

    def test_final_validator_overrun_does_not_promote_a_valid_candidate(self):
        source,_,quality=fixture();entry=copy.deepcopy(source['rest_cm']);clock=Clock()
        original=solver.validate_metrics;calls=0
        def expires(*args,**kwargs):
            nonlocal calls
            calls+=1;result=original(*args,**kwargs)
            if calls==3:clock.value=2.
            return result
        with patch.object(solver,'validate_metrics',side_effect=expires):
            result=self.run_coupon(source,entry,quality,deadline=1.,clock=clock)
        self.assertEqual(calls,3);self.assertEqual(result['coordinates_cm'],entry)
        self.assertEqual(result['status'],'NEEDS_CORRECTION');self.assertEqual(result['stop_reason'],'TIME_BUDGET')
        self.assertEqual(result['shared_deadline']['expired_phase'],'final_validation')

    def test_reference_size_finiteness_and_hostile_types_refuse(self):
        source,entry,quality=fixture()
        class Hostile:
            def __iter__(self):raise AssertionError('Do not iterate an untrusted reference object')
        cases=[[],entry[:-1],{},Hostile(),[[False,0.,0.]]*4,[[math.nan,0.,0.]]*4,
               [[math.inf,0.,0.]]*4,[[0.,0.]]*4]
        for reference in cases:
            with self.subTest(type=type(reference).__name__):
                with self.assertRaises(StudioError):self.run_coupon(source,entry,quality,displacement_reference=reference)

    def test_nonfinite_and_backwards_shared_clocks_refuse(self):
        source,entry,quality=fixture()
        for clock in [lambda:math.nan,lambda:True,iter([2.,1.]).__next__]:
            with self.subTest(clock=clock):
                with self.assertRaisesRegex(StudioError,'finite and monotonic'):
                    self.run_coupon(source,entry,quality,deadline=10.,clock=clock)

    def test_invalid_absolute_deadlines_refuse(self):
        source,entry,quality=fixture()
        for deadline in [True,math.nan,math.inf,'later']:
            with self.subTest(deadline=deadline):
                with self.assertRaisesRegex(StudioError,'finite absolute monotonic'):
                    self.run_coupon(source,entry,quality,deadline=deadline)

    def test_callback_mutation_of_original_reference_is_detected(self):
        source,entry,quality=fixture();reference=copy.deepcopy(entry);calls=0
        def hostile_clock():
            nonlocal calls
            calls+=1
            if calls==2:reference[1][0]+=.01
            return 0.
        with self.assertRaisesRegex(StudioError,'immutable input'):
            self.run_coupon(source,entry,quality,displacement_reference=reference,clock=hostile_clock)


if __name__=='__main__':unittest.main()
