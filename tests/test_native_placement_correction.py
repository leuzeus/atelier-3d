import copy
from types import SimpleNamespace
import unittest
from unittest.mock import patch

from a3d.core import digest
from a3d.cloth_metrics import validate_metrics
from blender.placement_correction import correct_preparation,effective_quality,native_measurement
from a3d.placement_solver import solve_placement
from tests.test_placement_solver import fixture


class NativeCorrectionAdapter(unittest.TestCase):
    def anchor_inputs(self):
        from tests.test_guide_metric_solver import fixture as metric_fixture
        payload,points,quality=metric_fixture();payload.update(placed_cm=points,component_id='coupon',package_sha256='a'*64)
        _,_,spec,_=fixture();spec['quality']=copy.deepcopy(quality)
        plan={'quality':quality,'assembly':{'max_displacement_cm':2.,'max_step_cm':.2,'iterations':10},
              'collision':{'clearance_cm':.1},'consolidation':{'weld_gap_cm':.05}}
        preparation={'version':1,'component_id':'coupon','source_ref':'fixture:source',
            'regular_mesh':{'spacing_cm':1.,'min_spacing_cm':.2,'refinement_distance_cm':1.,'max_vertices':20,'target_min_angle_degrees':15.},
            'placement_correction':spec,'metric_recovery':{'version':1,'piece_ids':['panel'],
                'protected_edges':[{'piece':'panel','edge':'anchor'}],'strain_weight':100.,
                'budgets':{'max_iterations':20,'max_seconds':10.,'max_displacement_cm':2.,'max_step_cm':.5,
                    'cg_iterations':80,'cg_tolerance':1e-5,'stagnation_iterations':3}},
            'anchor_reserve_correction':{'version':1,'mode':'PERMANENT_COMPONENT_BODY_AXIS_TRANSLATION_V1',
                'body_ref':{'path':'body.json','sha256':'a'*64},'direction':'BODY_FRAME_UP',
                'reserve_source':'PLAN_COLLISION_CLEARANCE',
                'budgets':{'max_iterations':10,'max_seconds':10.,'max_displacement_cm':2.,'max_step_cm':.2}}}
        return payload,points,quality,plan,preparation,{'mesh':quality}

    def test_inadmissible_anchors_prevent_metric_freeze_and_contact_solver(self):
        payload,points,quality,plan,prep,recipe=self.anchor_inputs()
        before=digest([payload,recipe,plan,prep])
        with patch('blender.cloth_contacts.build_contact_context',return_value={'bodies':[]}),\
                patch('blender.anchor_reserve.propose_anchor_reserve',return_value={
                    'status':'NEEDS_MEASUREMENT','stop_reason':'AMBIGUOUS_SIGN','coordinates_cm':points}),\
                patch('blender.placement_correction.recover_guide_metric') as metric,\
                patch('blender.placement_correction.solve_placement') as contact:
            result=correct_preparation(payload,recipe,plan,prep,[],anchor_body={'source':'fixture'})
        metric.assert_not_called();contact.assert_not_called()
        self.assertEqual(result['status'],'NEEDS_CORRECTION');self.assertEqual(result['qualification'],'NONE')
        self.assertEqual(result['contact_search'],'NOT_STARTED_INADMISSIBLE_ANCHORS')
        self.assertEqual(digest([payload,recipe,plan,prep]),before)

    def test_anchor_entry_is_frozen_after_shift_with_original_displacement_reference(self):
        payload,points,quality,plan,prep,recipe=self.anchor_inputs()
        shifted=[[p[0],p[1],p[2]+.25] for p in points]
        original_recovery=__import__('a3d.guide_metric_solver',fromlist=['recover_guide_metric']).recover_guide_metric
        calls=[]
        def recover(source,entry,*args,**kwargs):
            calls.append((copy.deepcopy(entry),copy.deepcopy(kwargs)))
            return original_recovery(source,entry,*args,**kwargs)
        def measure(source,coords,context,limits,assembly):
            validate_metrics(source,coords,limits,include_faces=False,include_bending=False)
            return {'candidate_sha256':digest(coords),'hard_valid':True,'score':0.,'contacts':[]}
        with patch('blender.cloth_contacts.build_contact_context',return_value={'bodies':[]}),\
                patch('blender.anchor_reserve.propose_anchor_reserve',return_value={
                    'status':'ANCHORS_ADMISSIBLE_ONLY','coordinates_cm':shifted}),\
                patch('blender.placement_correction.recover_guide_metric',side_effect=recover),\
                patch('blender.placement_correction.native_measurement',side_effect=measure):
            result=correct_preparation(payload,recipe,plan,prep,[],anchor_body={'source':'fixture'})
        self.assertEqual(calls[0][0],shifted);self.assertEqual(calls[0][1]['displacement_reference'],points)
        self.assertEqual(calls[0][1]['protected_stop_reference'],shifted)
        self.assertEqual(result['displacement_reference_sha256'],digest(points))
        self.assertEqual(result['metric_recovery']['displacement_reference_sha256'],digest(points))
        self.assertEqual(result['coordinates_cm'][0],shifted[0])
        self.assertEqual(result['coordinates_cm'][3],shifted[3])
        self.assertLessEqual(result['metric_recovery']['max_displacement_cm'],2.)

    def test_opt_in_metric_recovery_preserves_sources_and_runs_contact_search_only_after_strict_success(self):
        from tests.test_guide_metric_solver import fixture as metric_fixture
        payload,points,quality=metric_fixture();payload.update(placed_cm=points,component_id='coupon',package_sha256='a'*64)
        _,_,spec,_=fixture();spec['quality']=copy.deepcopy(quality)
        plan={'quality':quality,'assembly':{'max_displacement_cm':2.,'max_step_cm':.2,'iterations':10},
            'collision':{'clearance_cm':.1},'consolidation':{'weld_gap_cm':.05}}
        preparation={'version':1,'component_id':'coupon','source_ref':'fixture:source',
            'regular_mesh':{'spacing_cm':1.,'min_spacing_cm':.2,'refinement_distance_cm':1.,'max_vertices':20,'target_min_angle_degrees':15.},
            'placement_correction':spec,'metric_recovery':{'version':1,'piece_ids':['panel'],
                'protected_edges':[{'piece':'panel','edge':'anchor'}],'strain_weight':100.,
                'budgets':{'max_iterations':20,'max_seconds':10.,'max_displacement_cm':2.,'max_step_cm':.5,
                    'cg_iterations':80,'cg_tolerance':1e-5,'stagnation_iterations':3}}}
        before=digest([payload,plan,preparation]);recipe={'mesh':quality}
        def measure(source,coords,context,limits,assembly):
            validate_metrics(source,coords,limits,include_faces=False,include_bending=False)
            return {'candidate_sha256':digest(coords),'hard_valid':True,'score':0.,'contacts':[]}
        with patch('blender.cloth_contacts.build_contact_context',return_value={'bodies':[]}),\
                patch('blender.placement_correction.native_measurement',side_effect=measure):
            result=correct_preparation(payload,recipe,plan,preparation,[])
        self.assertEqual(result['status'],'GEOMETRIC_GATES_PASSED')
        self.assertEqual(result['metric_recovery']['status'],'SOURCE_METRIC_RECOVERED')
        self.assertEqual(result['metric_recovery']['shared_displacement_reference_sha256'],digest(points))
        self.assertEqual(result['displacement_reference_sha256'],digest(points))
        self.assertEqual(result['coordinates_cm'][0],points[0]);self.assertEqual(result['coordinates_cm'][3],points[3])
        self.assertEqual(digest([payload,plan,preparation]),before)
        refused=copy.deepcopy(preparation);refused['metric_recovery']['protected_edges'].append({'piece':'panel','edge':'opposite'})
        with patch('blender.cloth_contacts.build_contact_context',return_value={'bodies':[]}),\
                patch('blender.placement_correction.native_measurement',return_value={'hard_valid':False,'score':1.}),\
                patch('blender.placement_correction.solve_placement') as contact_search:
            result=correct_preparation(payload,recipe,plan,refused,[])
        contact_search.assert_not_called();self.assertEqual(result['status'],'NEEDS_CORRECTION')
        self.assertEqual(result['coordinates_cm'],points)
        self.assertEqual(result['contact_search'],'NOT_STARTED_INVALID_SOURCE_METRIC')
        self.assertEqual(result['qualification'],'NONE')

    def test_new_precise_contact_witnesses_do_not_block_continuous_penetration_repair(self):
        payload,_,spec,_=fixture();points=[[x,y,.8] for x,y,_ in payload['rest_cm']]
        spec['budgets'].update(max_iterations=50,max_step_cm=.05,min_improvement=1e-8,target_score=1e-8)
        class Vector(list):
            def normalized(self):return self
        tree=SimpleNamespace(find_nearest=lambda point:(Vector([point[0],point[1],.01]),Vector([0.,0.,1.]),0,0.))
        context={'bodies':[{'name':'body','tree':tree,'snapshot':{},'closed':True,
            'triangles':[[[0.,0.,1.],[2.,0.,1.],[2.,2.,1.]]]}],'clearance_cm':.1}
        plan={'assembly':{'max_initial_gap_cm':.5}}
        def contacts(ctx,candidate):
            z=candidate[0][2];rows=[]
            if abs(z-1.)<.1:
                # Duplicate triangle witnesses occur when the broadphase
                # first reaches the clearance band around the same surface.
                rows=[{'collider':'body','collider_triangle':0,'point_b_cm':[0.,0.,1.],
                    'vertices':[0,1,2,3]} for _ in range(4)]
            return {'ok':z>=1.1-1e-10,'contacts':rows,'contact_count':len(rows),'self_contact':{'contact_count':0}}
        def signed(candidate,*args,**kwargs):
            return {'ambiguous_sign_count':0,'minimum_signed_offset_cm':candidate[0][2]-1.}
        with patch.dict('sys.modules',{'mathutils':SimpleNamespace(Vector=Vector)}),\
                patch('blender.cloth_contacts.check_contacts',side_effect=contacts),\
                patch('blender.pattern_assembly.collision_check',side_effect=signed):
            result=solve_placement(payload,points,lambda source,candidate:native_measurement(
                source,candidate,context,spec['quality'],plan),spec)
        self.assertEqual(result['status'],'GEOMETRIC_GATES_PASSED')
        scores=[row['measurement']['score'] for row in result['history'] if row['kept']]
        self.assertTrue(all(a>b for a,b in zip(scores,scores[1:])))
        self.assertGreaterEqual(result['coordinates_cm'][0][2],1.1-1e-10)
        self.assertEqual(result['measurement']['static_contact']['ok'],True)

    def test_opt_in_is_required_and_effective_gates_only_tighten(self):
        payload,points,spec,_=fixture();payload['placed_cm']=points
        self.assertIsNone(correct_preparation(payload,{}, {}, {},[]))
        recipe={'mesh':{'min_angle_degrees':2,'min_edge_cm':.01,'min_stretch':.9,'max_stretch':1.1}}
        plan={'quality':{'min_angle_degrees':10,'min_edge_cm':.001,'min_stretch':.8,'max_stretch':1.25}}
        preparation={'regular_mesh':{'target_min_angle_degrees':15}}
        spec['quality']={'min_angle_degrees':0,'min_edge_cm':0,'min_stretch':.1,'max_stretch':3}
        limits=effective_quality(recipe,plan,preparation,spec)
        self.assertEqual(limits,{'min_angle_degrees':15,'min_edge_cm':.01,'min_stretch':.9,'max_stretch':1.1})

    def test_adapter_uses_current_contact_evaluator_and_retains_actual_candidate_identity(self):
        payload,points,spec,evaluate=fixture();payload['placed_cm']=points;payload['package_sha256']='a'*64
        recipe={'mesh':copy.deepcopy(spec['quality'])}
        plan={'quality':copy.deepcopy(spec['quality']),'assembly':{'max_displacement_cm':2,'max_step_cm':.2,'iterations':10},
            'collision':{'clearance_cm':.1},'consolidation':{'weld_gap_cm':.05}}
        preparation={'regular_mesh':{'target_min_angle_degrees':10},'placement_correction':spec}
        inputs=[payload,recipe,plan,preparation];before=digest(inputs)
        with patch('blender.cloth_contacts.build_contact_context',return_value={'bodies':[]}) as context,\
                patch('blender.placement_correction.native_measurement',side_effect=lambda source,coords,*args:evaluate(source,coords)) as measured:
            result=correct_preparation(payload,recipe,plan,preparation,[])
        self.assertEqual(result['status'],'GEOMETRIC_GATES_PASSED')
        self.assertEqual(result['origin'],'NATIVE_MEASURED_CONTACT_CORRECTION')
        self.assertEqual(result['candidate_sha256'],digest(result['coordinates_cm']))
        self.assertTrue(result['candidate_not_automatically_admitted'])
        self.assertEqual(result['simulation'],'NOT_EXECUTED');self.assertEqual(result['qualification'],'NONE')
        self.assertGreater(measured.call_count,1);context.assert_called_once()
        self.assertEqual(digest(inputs),before)


if __name__=='__main__':unittest.main()
