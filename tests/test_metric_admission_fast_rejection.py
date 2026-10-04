"""Definite principal failures save work without relaxing complete admission."""
import copy
import struct
import unittest
from unittest.mock import patch

from a3d.cloth_metrics import evaluate_metrics,face_sources,validate_metrics
from a3d.core import StudioError,digest
from a3d.guide_metric_solver import _definite_principal_violation,_metric_admitted,recover_guide_metric
from tests.test_guide_metric_solver import fixture,seamed_fixture


def triangle(scale=1.):
    return {'rest_cm':[[0.,0.,0.],[scale,0.,0.],[0.,scale,0.]],'faces':[[0,1,2]],
            'panels':{'coupon':{'indices':[0,1,2],'edges':{'anchor':[0,2]}}},'seams':{},'pins':{}}


LIMITS={'min_angle_degrees':5.,'min_edge_cm':.01,'min_stretch':.9,'max_stretch':1.05}


def old_admitted(payload,coordinates,quality):
    try:validate_metrics(payload,coordinates,quality,include_faces=False,include_bending=False)
    except StudioError:return False
    return True


class MetricAdmissionFastRejection(unittest.TestCase):
    def assert_complete_fallback(self,payload,coordinates,limits,expected):
        binding=face_sources(payload)
        self.assertFalse(_definite_principal_violation(payload,coordinates,limits,binding))
        with patch('a3d.guide_metric_solver.validate_metrics',wraps=validate_metrics)as complete:
            self.assertEqual(_metric_admitted(payload,coordinates,limits,binding),expected)
        complete.assert_called_once_with(payload,coordinates,limits,include_faces=False,include_bending=False)
        self.assertEqual(old_admitted(payload,coordinates,limits),expected)

    def test_shear_hidden_from_edges_is_definite_principal_rejection_without_full_scan(self):
        payload=triangle();coordinates=[[0.,0.,0.],[1.,0.,0.],[.2,1.,0.]]
        before=digest([payload,coordinates,LIMITS]);binding=face_sources(payload)
        measured=evaluate_metrics(payload,coordinates,include_faces=False,include_bending=False)
        self.assertGreaterEqual(measured['min_stretch'],LIMITS['min_stretch'])
        self.assertLessEqual(measured['max_stretch'],LIMITS['max_stretch'])
        self.assertGreater(measured['max_principal_stretch'],LIMITS['max_stretch'])
        with patch('a3d.guide_metric_solver.validate_metrics',side_effect=AssertionError('Definite failure already known')):
            self.assertFalse(_metric_admitted(payload,coordinates,LIMITS,binding))
        self.assertFalse(old_admitted(payload,coordinates,LIMITS))
        self.assertEqual(digest([payload,coordinates,LIMITS]),before)

    def test_compression_is_rejected_with_existing_lower_limit(self):
        payload=triangle();coordinates=[[x*.8,y,z]for x,y,z in payload['rest_cm']]
        with patch('a3d.guide_metric_solver.validate_metrics',side_effect=AssertionError('Definite compression')):
            self.assertFalse(_metric_admitted(payload,coordinates,LIMITS,face_sources(payload)))
        self.assertFalse(old_admitted(payload,coordinates,LIMITS))

    def test_source_and_placed_angle_failure_still_requires_full_validator(self):
        payload=triangle();payload['rest_cm'][2]=[0.,.02,0.]
        self.assert_complete_fallback(payload,copy.deepcopy(payload['rest_cm']),LIMITS,False)

    def test_short_placed_edge_with_unit_principal_metric_still_requires_full_validator(self):
        payload=triangle(.005)
        self.assert_complete_fallback(payload,copy.deepcopy(payload['rest_cm']),LIMITS,False)

    def test_source_and_placed_area_failure_still_requires_full_validator(self):
        payload=triangle(1e-5);limits={**LIMITS,'min_edge_cm':1e-6}
        self.assert_complete_fallback(payload,copy.deepcopy(payload['rest_cm']),limits,False)

    def test_oriented_topology_failure_still_requires_full_validator(self):
        payload=triangle();payload['rest_cm'].append([1.,-1.,0.]);payload['faces'].append([0,1,3])
        payload['panels']['coupon']['indices'].append(3)
        self.assert_complete_fallback(payload,copy.deepcopy(payload['rest_cm']),LIMITS,False)

    def test_nonfinite_or_mismatched_positions_never_gain_a_witness_or_admission(self):
        payload=triangle()
        for value in (float('nan'),float('inf'),-float('inf')):
            coordinates=copy.deepcopy(payload['rest_cm']);coordinates[2][1]=value
            with self.subTest(value=value):self.assert_complete_fallback(payload,coordinates,LIMITS,False)
        self.assert_complete_fallback(payload,payload['rest_cm'][:2],LIMITS,False)
        coordinates=copy.deepcopy(payload['rest_cm']);coordinates[1]=[1.,0.]
        self.assert_complete_fallback(payload,coordinates,LIMITS,False)

    def test_missing_or_nonfinite_principal_observation_defers_to_full_validation(self):
        payload=triangle();coordinates=copy.deepcopy(payload['rest_cm'])
        for observation in (None,[float('nan'),1.],[1.,float('inf')]):
            with self.subTest(observation=observation),patch('a3d.guide_metric_solver.principal_stretches',return_value=observation):
                self.assert_complete_fallback(payload,coordinates,LIMITS,True)
        payload['rest_cm'][2]=[2.,0.,0.]
        self.assert_complete_fallback(payload,copy.deepcopy(payload['rest_cm']),LIMITS,False)

    def test_valid_neutral_rotated_and_translated_candidates_invoke_full_validator(self):
        payload=triangle()
        for coordinates in (copy.deepcopy(payload['rest_cm']),
                [[3+z,7+x,9+y]for x,y,z in payload['rest_cm']],
                [[3+x,7-y,9-z]for x,y,z in payload['rest_cm']]):
            with self.subTest(coordinates=coordinates):
                self.assert_complete_fallback(payload,coordinates,LIMITS,True)

    def test_exact_principal_limit_equality_does_not_trigger_fast_rejection(self):
        payload=triangle();coordinates=copy.deepcopy(payload['rest_cm'])
        limits={**LIMITS,'min_stretch':1.,'max_stretch':1.}
        self.assert_complete_fallback(payload,coordinates,limits,True)

    def test_ambiguous_binding_defers_to_complete_canonical_source_check(self):
        payload=triangle();coordinates=[[0.,0.,0.],[1.,0.,0.],[.2,1.,0.]]
        binding=face_sources(payload);binding['binding_issues'].append({'code':'SOURCE_FACE_WINDING_OR_BINDING_CHANGED'})
        self.assertFalse(_definite_principal_violation(payload,coordinates,LIMITS,binding))
        with patch('a3d.guide_metric_solver.validate_metrics',wraps=validate_metrics)as complete:
            self.assertFalse(_metric_admitted(payload,coordinates,LIMITS,binding))
        complete.assert_called_once()

    def test_explicit_per_face_uv_and_cyclic_source_binding_use_shared_correspondence(self):
        payload=triangle();payload.update({key:value for key,value in face_sources(payload).items()if key.startswith('source_')})
        coordinates=[[0.,0.,0.],[1.,0.,0.],[.2,1.,0.]]
        payload['rest_mode']='assembled_3d';payload['rest_cm']=copy.deepcopy(coordinates)
        payload['faces'][0]=[1,2,0]
        binding=face_sources(payload);before=digest([payload,coordinates,binding,LIMITS])
        self.assertTrue(_definite_principal_violation(payload,coordinates,LIMITS,binding))
        self.assertFalse(_metric_admitted(payload,coordinates,LIMITS,binding))
        self.assertFalse(old_admitted(payload,coordinates,LIMITS))
        self.assertEqual(digest([payload,coordinates,binding,LIMITS]),before)

    def test_all_faces_and_nonselected_panels_remain_in_boolean_check(self):
        payload=triangle();payload['rest_cm']+=[[10.,0.,0.],[11.,0.,0.],[10.,1.,0.]]
        payload['faces'].append([3,4,5]);payload['panels']['other']={'indices':[3,4,5]}
        coordinates=copy.deepcopy(payload['rest_cm']);coordinates[5][0]+=.2
        with patch('a3d.guide_metric_solver.validate_metrics',side_effect=AssertionError('Other panel failure known')):
            self.assertFalse(_metric_admitted(payload,coordinates,LIMITS,face_sources(payload)))
        self.assertFalse(old_admitted(payload,coordinates,LIMITS))

    def test_double_and_native_float32_representations_match_complete_boolean(self):
        payload=triangle()
        def f32(value):return struct.unpack('<f',struct.pack('<f',value))[0]
        for shear in (0.,.03,.2,-.2):
            original=[[1e3+x+shear*y,-2e3+y,3e3+z]for x,y,z in payload['rest_cm']]
            for coordinates in (original,[[f32(value)for value in point]for point in original]):
                with self.subTest(shear=shear,float32=coordinates is not original):
                    before=digest([payload,coordinates,LIMITS]);binding=face_sources(payload)
                    self.assertEqual(_metric_admitted(payload,coordinates,LIMITS,binding),old_admitted(payload,coordinates,LIMITS))
                    self.assertEqual(digest([payload,coordinates,LIMITS]),before)

    def test_no_faces_cannot_admit_and_recovery_keeps_explicit_refusal(self):
        payload=triangle();payload['faces']=[];coordinates=copy.deepcopy(payload['rest_cm'])
        self.assert_complete_fallback(payload,coordinates,LIMITS,False)
        with self.assertRaisesRegex(StudioError,'actual source triangles'):
            recover_guide_metric(payload,coordinates,LIMITS,['coupon'],[{'piece':'coupon','edge':'anchor'}])

    def test_definite_failures_do_not_skip_complete_final_validation_or_relax_output(self):
        payload,coordinates,limits=fixture();edges=[{'piece':'panel','edge':'anchor'},{'piece':'panel','edge':'opposite'}]
        before=digest([payload,coordinates,limits])
        with patch('a3d.guide_metric_solver.validate_metrics',wraps=validate_metrics)as complete:
            result=recover_guide_metric(payload,coordinates,limits,['panel'],edges,max_iterations=1)
        complete.assert_called_once_with(payload,result['coordinates_cm'],limits,include_faces=False,include_bending=False)
        self.assertEqual(result['status'],'NEEDS_CORRECTION')
        self.assertEqual(result['stop_reason'],'ITERATION_BUDGET')
        self.assertEqual(result['metric'],evaluate_metrics(payload,result['coordinates_cm'],include_faces=False,include_bending=False))
        self.assertEqual(result['policy']['quality'],limits)
        self.assertEqual(result['qualification'],'NONE');self.assertEqual(result['fitting'],'NOT_EXECUTED')
        self.assertEqual(digest([payload,coordinates,limits]),before)

    def test_immutable_source_early_exit_still_runs_complete_final_validation(self):
        payload=triangle();payload['rest_cm'][2]=[0.,.02,0.];coordinates=copy.deepcopy(payload['rest_cm'])
        with patch('a3d.guide_metric_solver.validate_metrics',wraps=validate_metrics)as complete:
            result=recover_guide_metric(payload,coordinates,LIMITS,['coupon'],[{'piece':'coupon','edge':'anchor'}])
        self.assertEqual(complete.call_count,2)
        self.assertEqual(result['stop_reason'],'IMMUTABLE_SOURCE_MESH_QUALITY')
        self.assertEqual(result['status'],'NEEDS_CORRECTION');self.assertEqual(result['iterations'],0)

    def test_recovery_geometry_and_energy_match_previous_complete_boolean_path(self):
        for coupled in (False,True):
            if coupled:
                payload,coordinates,limits,edges=seamed_fixture()
                pieces=['a','b'];kwargs={'seam_ids':['ab'],'max_initial_seam_gap_cm':0.}
            else:
                payload,coordinates,limits=fixture();edges=[{'piece':'panel','edge':'anchor'}];pieces=['panel'];kwargs={}
            kwargs.update(max_iterations=30,max_seconds=10.)
            before=digest([payload,coordinates,limits,edges,kwargs])
            optimized=recover_guide_metric(payload,coordinates,limits,pieces,edges,**kwargs)
            with patch('a3d.guide_metric_solver._metric_admitted',side_effect=lambda p,c,q,b:old_admitted(p,c,q)):
                previous=recover_guide_metric(payload,coordinates,limits,pieces,edges,**kwargs)
            with self.subTest(coupled=coupled):
                for key in ('coordinates_cm','candidate_sha256','history','energy','status','stop_reason','metric','policy'):
                    self.assertEqual(optimized[key],previous[key])
                self.assertEqual(digest([payload,coordinates,limits,edges,kwargs]),before)


if __name__=='__main__':unittest.main()
