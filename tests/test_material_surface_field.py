import copy
import json
import math
import sys
import unittest
from fractions import Fraction as F

from a3d.core import StudioError, digest
from a3d.material_surface_field import (
    DISCRIMINANT, compile_material_surface_field, evaluate_material_field,
    observe_material_surface_field, validate_material_surface_field,
)


def square(identity='material',opposite=False,reverse=False):
    faces=[[0,1,3],[1,2,3]]if opposite else[[0,1,2],[0,2,3]]
    if reverse:faces=[list(reversed(f))for f in faces]
    return {'id':identity,'uv_cm':[[0,0],[1,0],[1,1],[0,1]],
            'vertex_ids':['v0','v1','v2','v3'],'face_ids':['f0','f1'],
            'triangles':faces,'edges':{'bottom':['v0','v1']}}


def coordinates(mesh,scale=1.,shift=0.):
    return [[float(F(p[0]))*scale+shift,float(F(p[1])),0.]for p in mesh['uv_cm']]


def reference(break_height=None,reverse=False):
    mesh=square('reference',reverse=reverse)
    if break_height is None:return {'mesh':mesh,'coordinates_cm':coordinates(mesh)}
    mesh['uv_cm'].append(['1/2','1/2']);mesh['vertex_ids'].append('center')
    mesh['triangles']=[[0,1,4],[1,2,4],[2,3,4],[3,0,4]]
    if reverse:mesh['triangles']=[list(reversed(f))for f in mesh['triangles']]
    mesh['face_ids']=['r0','r1','r2','r3']
    positions=coordinates(mesh);positions[-1][2]=break_height
    return {'mesh':mesh,'coordinates_cm':positions}


def sample(identity='mid',fraction='1/2'):
    f=F(fraction)
    return {'id':identity,'source_face_id':'f0','source_barycentric_weights':[str(1-f),str(f),'0']}


def relation(kind,identity):
    return {'id':identity,'kind':kind,'orientation':'reverse','owners':[
        {'source_id':'material','edge_id':'bottom','samples':[
            {'sample_id':'start','fraction':'0'},{'sample_id':'end','fraction':'1'}]},
        {'source_id':'external','edge_id':'other-bottom','source_sha256':'a'*64,
         'source_vertex_ids':['a','b'],'samples':[
             {'sample_id':'other-start','fraction':'0','source_segment_vertex_ids':['b','a'],'source_segment_parameter':'0'},
             {'sample_id':'other-end','fraction':'1','source_segment_vertex_ids':['b','a'],'source_segment_parameter':'1'}]}]}


def compile_field(**options):
    source=options.pop('source',square());carrier=options.pop('carrier',square('carrier',True))
    fresh=options.pop('reference',reference())
    current=options.pop('coordinates_cm',coordinates(carrier))
    return compile_material_surface_field(source,carrier,fresh,current,
        clock=options.pop('clock',lambda:0.),**options)


def returned_nodes(value):
    if type(value)is dict:return 1+sum(returned_nodes(v)for v in value.values())
    if type(value)is list:return 1+sum(returned_nodes(v)for v in value)
    return 1


def returned_bytes(value):
    return len(json.dumps(value,separators=(',',':'),ensure_ascii=False,allow_nan=False).encode('utf8'))


def reviewer_fixture(**options):
    # The exact independent V1 witness, with globally named IDs and no edges.
    meshes=[]
    for identity,opposite in[('source',False),('carrier',True),('reference',False)]:
        mesh=square(identity,opposite);mesh.pop('edges')
        mesh['vertex_ids']=[identity+':v'+str(i)for i in range(4)]
        mesh['face_ids']=[identity+':f'+str(i)for i in range(2)]
        meshes.append(mesh)
    source,carrier,fresh=meshes
    return compile_field(source=source,carrier=carrier,
        reference={'mesh':fresh,'coordinates_cm':coordinates(fresh)},**options)


class HookClock:
    def __init__(self,phase=None,function=None,action=None):
        self.phase=phase;self.function=function;self.action=action;self.triggered=False;self.value=0.
    def __call__(self):
        frame=sys._getframe(1);hit=False
        while frame:
            hit|=(self.phase is not None and frame.f_code.co_name=='check'and frame.f_locals.get('phase')==self.phase)
            hit|=(self.function is not None and frame.f_code.co_name==self.function)
            frame=frame.f_back
        if hit and not self.triggered:
            self.triggered=True
            if self.action:self.action()
            else:self.value=60.
        return self.value


class MaterialSurfaceFieldTests(unittest.TestCase):
    def refusal(self,reason,call,incomplete=False):
        with self.assertRaises(StudioError)as caught:call()
        self.assertEqual(caught.exception.reason,reason)
        self.assertEqual(caught.exception.qualification,'NONE')
        self.assertEqual(caught.exception.status,'INCOMPLETE'if incomplete else'REFUSED')

    def observed(self,compiled,**options):
        return observe_material_surface_field(compiled,clock=options.pop('clock',lambda:0.),**options)['observations']

    def test_opposite_diagonals_have_exact_triple_maps(self):
        c=compile_field(reference=reference(2.))
        self.assertEqual(c['discriminant'],DISCRIMINANT)
        patches=c['material_reference_carrier_patches']
        self.assertEqual(len(patches),4)
        self.assertEqual([F(p['area_cm2'])for p in patches],[F(1,4)]*4)
        self.assertEqual(sum(F(p['area_cm2'])for p in patches),1)
        for p in patches:
            for key in['source_barycentric_weights','reference_barycentric_weights','carrier_barycentric_weights']:
                self.assertTrue(all(sum(map(F,row))==1 for row in p[key]))
        self.assertEqual({p['reference_face_id']for p in patches},{'r0','r1','r2','r3'})

    def test_fresh_reference_break_is_evaluated_without_coarsening(self):
        c=compile_field(reference=reference(3.))
        r=evaluate_material_field(c,[{'id':'at-break','uv_cm':['1/2','1/2']}],clock=lambda:0.)['evaluations'][0]
        self.assertEqual(r['fresh_reference_evaluation']['coordinates_exact_cm'],['1/2','1/2','3'])
        self.assertEqual(r['coordinates_exact_cm'],['1/2','1/2','0'])
        self.assertIn('center',r['reference_support']['sparse_vertex_weights'])

    def test_patch_corner_detects_maximum_missed_by_samples_and_carrier_vertices(self):
        c=compile_field(reference=reference(9.),samples=[sample('corner','0')])
        observed=self.observed(c)
        self.assertEqual(F(observed['max_displacement_squared_exact_cm2']),81)
        self.assertIn('ORIGINAL_REFERENCE_DISPLACEMENT',observed['violations'])
        self.assertEqual(evaluate_material_field(c,clock=lambda:0.)['evaluations'][0]['fresh_reference_evaluation']['coordinates_cm'],[0.,0.,0.])

    def test_rotation_preserves_exact_gram(self):
        mesh=square('carrier',True);points=[[-p[1],p[0],0]for p in mesh['uv_cm']]
        r=self.observed(compile_field(carrier=mesh,coordinates_cm=points))
        self.assertEqual(r['local_field_checks'],'PASS_TEST_ONLY')
        self.assertTrue(all(f['gram_exact']==[['1','0'],['0','1']]for f in r['carrier_face_metrics']))

    def test_declared_binary64_stretch_boundaries_inclusive(self):
        for scale in[.9,1.1]:
            with self.subTest(scale=scale):
                r=self.observed(compile_field(coordinates_cm=coordinates(square(),scale)))
                self.assertNotIn('FIELD_METRIC_BOUNDS',r['violations'])
                self.assertEqual(F(r['limits_rational']['min_stretch']),F(.9))
                self.assertEqual(F(r['limits_rational']['max_stretch']),F(1.1))

    def test_one_ulp_outside_stretch_bounds_refused_without_epsilon(self):
        for scale in[math.nextafter(.9,0.),math.nextafter(1.1,math.inf)]:
            with self.subTest(scale=scale):
                r=self.observed(compile_field(coordinates_cm=coordinates(square(),scale)))
                self.assertIn('FIELD_METRIC_BOUNDS',r['violations']);self.assertFalse(r['epsilon_allowance'])

    def test_collapsed_field_is_metric_failure(self):
        r=self.observed(compile_field(coordinates_cm=[[0,0,0]]*4))
        self.assertIn('FIELD_METRIC_BOUNDS',r['violations'])
        self.assertEqual(r['constraints_3d'],'NOT_QUALIFIED')

    def test_displacement_8cm_and_next_ulp(self):
        for shift,pass_ in[(8.,True),(math.nextafter(8.,math.inf),False)]:
            points=[[float(p[0]),float(p[1]),shift]for p in square()['uv_cm']]
            r=self.observed(compile_field(coordinates_cm=points))
            self.assertEqual('ORIGINAL_REFERENCE_DISPLACEMENT'not in r['violations'],pass_)

    def test_half_cm_step_limit_and_next_ulp(self):
        for amount,pass_ in[(.5,True),(math.nextafter(.5,math.inf),False)]:
            points=[[float(p[0]),float(p[1]),amount]for p in square()['uv_cm']]
            r=self.observed(compile_field(coordinates_cm=points,previous_coordinates_cm=coordinates(square())))
            self.assertEqual('PREVIOUS_FIELD_STEP'not in r['violations'],pass_)
            self.assertTrue(r['step_assessed'])

    def test_step_uses_previous_but_reference_budget_not_reset(self):
        current=[[p[0],p[1],8.5]for p in square()['uv_cm']]
        previous=[[p[0],p[1],8.]for p in square()['uv_cm']]
        r=self.observed(compile_field(coordinates_cm=current,previous_coordinates_cm=previous))
        self.assertEqual(F(r['max_step_squared_exact_cm2']),F(1,4))
        self.assertNotIn('PREVIOUS_FIELD_STEP',r['violations'])
        self.assertIn('ORIGINAL_REFERENCE_DISPLACEMENT',r['violations'])

    def test_no_previous_field_does_not_claim_a_step_proof(self):
        r=self.observed(compile_field());self.assertFalse(r['step_assessed'])
        self.assertIsNone(r['max_step_squared_exact_cm2'])

    def test_near_source_point_and_half_notch_distinct(self):
        near=.49999975746439695
        samples=[sample('near',str(F(near))),sample('notch','1/2'),sample('same-position-other-id','1/2')]
        c=compile_field(samples=samples)
        r=evaluate_material_field(c,clock=lambda:0.)['evaluations']
        self.assertEqual([x['id']for x in r],['near','notch','same-position-other-id'])
        self.assertNotEqual(r[0]['exact_uv_cm'],r[1]['exact_uv_cm'])
        self.assertEqual(r[1]['exact_uv_cm'],r[2]['exact_uv_cm'])
        self.assertFalse(c['receipt']['identities_merged'])

    def test_rational_evaluation_conversion_error_is_recorded(self):
        c=compile_field(samples=[sample('third','1/3')])
        r=evaluate_material_field(c,clock=lambda:0.)['evaluations'][0]
        self.assertEqual(r['coordinates_exact_cm'][0],'1/3')
        self.assertEqual(F(r['binary64_conversion_component_errors_cm'][0]),F(float(F(1,3)))-F(1,3))
        self.assertNotEqual(F(r['binary64_conversion_max_absolute_error_cm']),0)

    def test_existing_source_vertex_and_explicit_uv_queries(self):
        r=evaluate_material_field(compile_field(),[
            {'id':'vertex','source_vertex_id':'v2'},{'id':'uv','uv_cm':['1/4','3/4']}],clock=lambda:0.)['evaluations']
        self.assertEqual(r[0]['coordinates_exact_cm'],['1','1','0'])
        self.assertEqual(r[1]['coordinates_exact_cm'],['1/4','3/4','0'])

    def test_outside_and_ambiguous_or_unknown_queries_refuse(self):
        c=compile_field()
        for raw,reason in[({'id':'out','uv_cm':[2,2]},'OUTSIDE_DOMAIN'),
                           ({'id':'unknown','sample_id':'missing'},'INVALID_QUERY'),
                           ({'id':'bad','sample_id':[]},'INVALID_QUERY'),
                           ({'id':'two','source_vertex_id':'v0','uv_cm':[0,0]},'INVALID_QUERY')]:
            with self.subTest(raw=raw):self.refusal(reason,lambda:evaluate_material_field(c,[raw],clock=lambda:0.))

    def test_duplicate_query_and_sample_ids_refuse(self):
        self.refusal('IDENTITY_COLLISION',lambda:compile_field(samples=[sample(),sample()]))
        self.refusal('IDENTITY_COLLISION',lambda:evaluate_material_field(compile_field(),[
            {'id':'same','uv_cm':[0,0]},{'id':'same','uv_cm':[1,1]}],clock=lambda:0.))

    def test_physical_stop_residual_not_hidden_by_numerical_target(self):
        targets=[{'id':'stop','sample_id':'mid','target_cm':[.5,0,1],'role':'physical_stop'},
                 {'id':'numeric','sample_id':'mid','target_cm':[.5,0,2],'role':'numerical_target'}]
        r=self.observed(compile_field(samples=[sample()],targets=targets))
        self.assertIn('PROVIDED_PHYSICAL_STOP_RESIDUAL',r['violations'])
        self.assertEqual(r['target_observations'][0]['residual_exact_cm'],['0','0','-1'])
        self.assertEqual(r['target_observations'][1]['residual_exact_cm'],['0','0','-2'])
        self.assertEqual(r['constraints_3d'],'NOT_QUALIFIED')

    def test_two_stops_exact_no_inferred_pins_or_constraint_qualification(self):
        c=compile_field(samples=[sample('start','0'),sample('end','1')],targets=[
            {'id':'left','sample_id':'start','target_cm':[0,0,0],'role':'physical_stop'},
            {'id':'right','sample_id':'end','target_cm':[1,0,0],'role':'physical_stop'}])
        self.assertEqual(c['physical_pins_added'],[])
        self.assertTrue(all(r['exact_target_satisfied']for r in c['target_observations']))
        self.assertEqual(self.observed(c)['constraints_3d'],'NOT_QUALIFIED')

    def test_closure_detachable_and_orientation_preserved(self):
        relations=[relation('closure','closure'),relation('detachable','detachable')]
        c=compile_field(samples=[sample('start','0'),sample('end','1')],relations=relations)
        self.assertEqual(c['relations'],relations);self.assertEqual(c['physical_pins_added'],[])
        self.assertTrue(all(not r['geometry_checked']for r in c['external_source_references']))

    def test_both_consistent_windings_work_and_mixed_winding_refuses(self):
        for reverse in[False,True]:
            c=compile_field(source=square(reverse=reverse),carrier=square('c',True,reverse),reference=reference(reverse=reverse))
            self.assertEqual(self.observed(c)['local_field_checks'],'PASS_TEST_ONLY')
        self.refusal('WINDING',lambda:compile_field(carrier=square('c',True,True)))

    def test_reference_domain_shift_or_missing_coverage_refuses_exactly(self):
        for kind in['ulp-shift','missing-face']:
            fresh=reference()
            if kind=='ulp-shift':fresh['mesh']['uv_cm'][1][0]=math.nextafter(1.,math.inf)
            else:fresh['mesh']['triangles'].pop();fresh['mesh']['face_ids'].pop()
            self.refusal('DOMAIN_COVERAGE'if kind=='ulp-shift'else'INVALID_MESH',lambda:compile_field(reference=fresh))

    def test_no_cached_qualification_can_bypass_revalidation(self):
        c=compile_field();c['uv_qualification']='FORGED_PASS';c['qualification']='FORGED_ACCEPTANCE'
        c['material_reference_carrier_patches']=[]
        r=validate_material_surface_field(c,clock=lambda:0.)
        self.assertEqual(r['qualification'],'NONE');self.assertNotEqual(r['status'],'READY')
        self.assertGreater(len(r['observations']['patch_corner_observations']),0)
        c['inputs']['reference']['mesh']['uv_cm'][1][0]=2
        self.refusal('DOMAIN_COVERAGE',lambda:validate_material_surface_field(c,clock=lambda:0.))

    def test_pending_or_unidentified_compilation_refuses(self):
        c=compile_field();c['status']='PENDING'
        self.refusal('INVALID_CONTRACT',lambda:evaluate_material_field(c,clock=lambda:0.))
        self.refusal('INVALID_CONTRACT',lambda:evaluate_material_field({'discriminant':'OLD_CAGE'},clock=lambda:0.))

    def test_mutated_compiled_coordinate_or_limits_identity_refuses(self):
        for key in['coordinate','limit']:
            c=compile_field()
            if key=='coordinate':c['inputs']['coordinates_cm'][0][2]=1
            else:c['inputs']['limits']={'max_displacement_cm':1.}
            self.refusal('REFERENCE_MUTATION',lambda:self.observed(c))

    def test_inputs_are_unchanged_and_outputs_have_no_aliases(self):
        source,carrier,fresh=square(),square('c',True),reference(2.)
        inputs=[source,carrier,fresh];before=digest(inputs)
        c=compile_field(source=source,carrier=carrier,reference=fresh)
        self.assertEqual(digest(inputs),before)
        c['inputs']['source']['uv_cm'][0][0]=3
        self.assertEqual(digest(inputs),before)

    def test_hostile_non_native_nonfinite_and_wrong_positions_refuse(self):
        class Hostile(dict):pass
        self.refusal('INVALID_REFERENCE',lambda:compile_field(source=Hostile(square())))
        self.refusal('INVALID_REFERENCE',lambda:compile_field(coordinates_cm=[[0,0,math.nan]]*4))
        self.refusal('INVALID_COORDINATES',lambda:compile_field(coordinates_cm=[[0,0,0]]*3))
        self.refusal('INVALID_COORDINATES',lambda:compile_field(coordinates_cm=[[2**53+1,0,0]]*4))
        self.refusal('INVALID_COORDINATES',lambda:compile_field(coordinates_cm=[['1/3',0,0]]*4))

    def test_mutation_during_clipping_refuses(self):
        source=square()
        clock=HookClock(function='_clip',action=lambda:source['uv_cm'][0].__setitem__(0,2))
        self.refusal('REFERENCE_MUTATION',lambda:compile_field(source=source,clock=clock))
        self.assertTrue(clock.triggered)

    def test_mutation_during_metrics_and_final_callback_refuses(self):
        for phase in['metric_gram','return']:
            c=compile_field();clock=HookClock(phase=phase,action=lambda:c['inputs']['coordinates_cm'][0].__setitem__(2,1))
            self.refusal('REFERENCE_MUTATION',lambda:self.observed(c,clock=clock))
            self.assertTrue(clock.triggered)

    def test_expired_entry_and_during_capture_clipping_metrics_and_return(self):
        self.refusal('DEADLINE_EXHAUSTED',lambda:compile_field(deadline=0.,clock=lambda:0.),True)
        for phase in['before_budget_capture','budget_capture','input_nodes','exact clipping','final_return','return','final_deadline_after_preservation']:
            clock=HookClock(phase=phase)
            self.refusal('DEADLINE_EXHAUSTED',lambda:compile_field(clock=clock,deadline=60.),True)
            self.assertTrue(clock.triggered)
        c=compile_field();clock=HookClock(phase='metric_gram')
        self.refusal('DEADLINE_EXHAUSTED',lambda:self.observed(c,clock=clock,deadline=60.),True)
        self.assertTrue(clock.triggered)

    def test_caller_deadline_and_phase_limit_share_one_clock(self):
        c=compile_field(clock=lambda:10.,deadline=15.,budgets={'max_seconds':60.})
        self.assertEqual(c['receipt']['clock_start_before_capture'],10.)
        self.assertEqual(c['receipt']['absolute_deadline'],15.)
        self.assertEqual(c['receipt']['caller_absolute_deadline'],15.)
        self.refusal('INVALID_BUDGET',lambda:compile_field(budgets={'max_seconds':61.}))

    def test_resource_caps_refuse_without_qualification(self):
        for caps in[{'max_input_nodes':1},{'max_input_bytes':128},{'max_pair_checks':1},
                     {'max_refinement_patches':1},{'max_fraction_bits':1},{'max_reference_vertices':3},
                     {'max_fraction_operations':1},{'max_output_nodes':1},{'max_output_bytes':128}]:
            with self.subTest(caps=caps):self.refusal('BUDGET_EXHAUSTED',lambda:compile_field(budgets=caps),True)
        c=compile_field()
        for caps in[{'max_metric_faces':1},{'max_patch_vertex_checks':1}]:
            self.refusal('BUDGET_EXHAUSTED',lambda:self.observed(c,budgets=caps),True)
        self.refusal('BUDGET_EXHAUSTED',lambda:evaluate_material_field(c,[
            {'id':'a','uv_cm':[0,0]},{'id':'b','uv_cm':[1,1]}],clock=lambda:0.,budgets={'max_queries':1}),True)

    def test_limits_cannot_be_relaxed_and_invalid_budget_clock_refuse(self):
        for limits in[{'max_displacement_cm':8.1},{'max_step_cm':.51},
                       {'min_stretch':.89},{'max_stretch':1.11}]:
            self.refusal('INVALID_LIMITS',lambda:compile_field(limits=limits))
        for budgets in[{'unknown':1},{'max_input_nodes':True},{'max_input_nodes':2**10000}]:
            self.refusal('INVALID_BUDGET',lambda:compile_field(budgets=budgets))
        self.refusal('INVALID_CLOCK',lambda:compile_field(clock=lambda:math.nan))
        self.refusal('INVALID_DEADLINE',lambda:compile_field(deadline=math.inf))

    def test_local_validation_never_claims_constraint_motion_or_product_pass(self):
        c=compile_field(samples=[sample()],targets=[{'id':'numeric','sample_id':'mid','target_cm':[0,0,0],'role':'numerical_target'}])
        r=validate_material_surface_field(c,clock=lambda:0.)
        self.assertEqual(r['qualification'],'NONE');self.assertFalse(r['physical_mesh']);self.assertFalse(r['is_installable'])
        self.assertEqual(r['observations']['local_field_checks'],'PASS_TEST_ONLY')
        self.assertEqual(r['observations']['constraints_3d'],'NOT_QUALIFIED')
        self.assertEqual(r['observations']['trajectory'],'NOT_ASSESSED')

    def output_operations(self):
        c=compile_field(samples=[sample()],targets=[
            {'id':'stop','sample_id':'mid','target_cm':[.5,0,1.],'role':'physical_stop'}])
        return {
            'compile':lambda **kwargs:compile_field(**kwargs),
            'evaluate':lambda **kwargs:evaluate_material_field(c,[],clock=kwargs.pop('clock',lambda:0.),**kwargs),
            'observe-failed-local-checks':lambda **kwargs:observe_material_surface_field(c,clock=kwargs.pop('clock',lambda:0.),**kwargs),
            'validate-failed-local-checks':lambda **kwargs:validate_material_surface_field(c,clock=kwargs.pop('clock',lambda:0.),**kwargs),
        }

    def test_complete_output_counters_include_receipt_exactly_once(self):
        for name,call in self.output_operations().items():
            with self.subTest(operation=name):
                r=call();work=r['receipt']['work']
                self.assertEqual(work['output_nodes'],returned_nodes(r))
                self.assertEqual(work['output_bytes'],returned_bytes(r))
                self.assertLessEqual(work['output_nodes'],r['receipt']['budgets']['max_output_nodes'])
                self.assertLessEqual(work['output_bytes'],r['receipt']['budgets']['max_output_bytes'])
                self.assertEqual(r['qualification'],'NONE')
                self.assertEqual(r['receipt']['content_sha256'],digest({k:v for k,v in r.items()if k!='receipt'}))

    def test_reviewer_840_node_cap_no_longer_returns_906_nodes(self):
        r=reviewer_fixture()
        self.assertEqual(returned_nodes({k:v for k,v in r.items()if k!='receipt'}),840)
        self.assertGreater(returned_nodes(r),840)
        self.refusal('BUDGET_EXHAUSTED',lambda:reviewer_fixture(budgets={'max_output_nodes':840}),True)

    def test_reviewer_empty_evaluation_1211_byte_cap_refuses_complete_return(self):
        c=reviewer_fixture();r=evaluate_material_field(c,[],clock=lambda:0.)
        self.assertEqual(returned_bytes({k:v for k,v in r.items()if k!='receipt'}),243)
        self.assertGreater(returned_bytes(r),1211)
        self.refusal('BUDGET_EXHAUSTED',lambda:evaluate_material_field(c,[],clock=lambda:0.,budgets={'max_output_bytes':1211}),True)

    def test_exact_complete_node_cap_accepts_and_one_below_refuses_all_operations(self):
        for name,call in self.output_operations().items():
            with self.subTest(operation=name):
                cap=returned_nodes(call())
                r=call(budgets={'max_output_nodes':cap})
                self.assertEqual(returned_nodes(r),cap)
                self.assertEqual(r['receipt']['work']['output_nodes'],cap)
                self.refusal('BUDGET_EXHAUSTED',lambda:call(budgets={'max_output_nodes':cap-1}),True)

    def test_exact_complete_byte_cap_accepts_and_one_below_refuses_all_operations(self):
        for name,call in self.output_operations().items():
            with self.subTest(operation=name):
                cap=returned_bytes(call())
                # The cap itself occurs in the returned receipt. The independent
                # JSON oracle adjusts its decimal digit count to find equality.
                for _ in range(5):
                    r=call(budgets={'max_output_bytes':cap});actual=returned_bytes(r)
                    if actual==cap:break
                    cap=actual
                self.assertEqual(actual,cap)
                self.assertEqual(r['receipt']['work']['output_bytes'],cap)
                self.refusal('BUDGET_EXHAUSTED',lambda:call(budgets={'max_output_bytes':cap-1}),True)

    def test_utf8_and_json_escaping_count_actual_return_bytes(self):
        c=compile_field(samples=[sample('é漢🙂"\\\n','1/3')])
        r=evaluate_material_field(c,clock=lambda:0.)
        self.assertEqual(r['receipt']['work']['output_nodes'],returned_nodes(r))
        self.assertEqual(r['receipt']['work']['output_bytes'],returned_bytes(r))
        self.assertGreater(len(json.dumps(r,ensure_ascii=True).encode('utf8')),returned_bytes(r))

    def test_deadline_during_receipt_encoding_and_complete_serialization_refuses(self):
        class ReceiptClock:
            triggered=False
            def __call__(self):
                frame=sys._getframe(1)
                while frame:
                    if(frame.f_code.co_name=='_encode'and type(frame.f_locals.get('value'))is dict and
                        'content_sha256'in frame.f_locals['value']):self.triggered=True
                    frame=frame.f_back
                return 60. if self.triggered else 0.
        clock=ReceiptClock()
        self.refusal('DEADLINE_EXHAUSTED',lambda:compile_field(clock=clock,deadline=60.),True)
        self.assertTrue(clock.triggered)
        for name,call in self.output_operations().items():
            for phase in['output_serialization','output_serialization_after',
                          'output_preservation_before_hash','output_preservation_after_hash',
                          'output_return','output_deadline_after_preservation']:
                with self.subTest(operation=name,phase=phase):
                    clock=HookClock(phase=phase)
                    self.refusal('DEADLINE_EXHAUSTED',lambda:call(clock=clock,deadline=60.),True)
                    self.assertTrue(clock.triggered)

    def test_input_mutation_during_complete_output_accounting_refuses(self):
        for phase in['output_serialization','output_return','output_deadline_after_preservation']:
            with self.subTest(phase=phase):
                c=compile_field();clock=HookClock(phase=phase,action=lambda:c['inputs']['coordinates_cm'][0].__setitem__(2,1))
                self.refusal('REFERENCE_MUTATION',lambda:observe_material_surface_field(c,clock=clock))
                self.assertTrue(clock.triggered)

    def test_simultaneous_output_caps_and_failed_measurements_remain_unqualified(self):
        c=compile_field(coordinates_cm=[[0.,0.,0.]]*4)
        r=observe_material_surface_field(c,clock=lambda:0.)
        self.assertIn('FIELD_METRIC_BOUNDS',r['observations']['violations'])
        cap_nodes=returned_nodes(r);cap_bytes=returned_bytes(r)
        r=observe_material_surface_field(c,clock=lambda:0.,budgets={'max_output_nodes':cap_nodes,'max_output_bytes':cap_bytes})
        self.assertEqual(r['receipt']['work']['output_nodes'],returned_nodes(r))
        self.assertEqual(r['receipt']['work']['output_bytes'],returned_bytes(r))
        self.assertEqual(r['qualification'],'NONE');self.assertNotEqual(r['status'],'READY')

    def test_last_input_fingerprint_time_expiry_refuses_all_interfaces(self):
        from a3d import material_surface_field as field
        for name,call in self.output_operations().items():
            with self.subTest(operation=name):
                timing={'now':0.,'consumed':False}
                original_digest=field.uv._digest
                def slow_final_digest(value):
                    result=original_digest(value)
                    caller=sys._getframe(1)
                    if(caller.f_code.co_name=='_finish'and
                        caller.f_locals['budget'].phase=='output_deadline_after_preservation'):
                        timing.update(now=60.,consumed=True)
                    return result
                # The clock only reads time. The digest consumes time without
                # changing inputs; the last work must precede the last check.
                try:
                    field.uv._digest=slow_final_digest
                    self.refusal('DEADLINE_EXHAUSTED',
                        lambda:call(clock=lambda:timing['now'],deadline=60.),True)
                finally:field.uv._digest=original_digest
                self.assertTrue(timing['consumed'])


if __name__=='__main__':unittest.main()
