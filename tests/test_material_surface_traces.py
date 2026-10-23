import copy
import inspect
import json
import math
import sys
import unittest
from fractions import Fraction as F
from unittest.mock import patch

from a3d.core import StudioError, digest
from a3d import material_sample_carrier as uv
from a3d import material_surface_field as field
from a3d import material_surface_traces as traces


def context():
    return {'source_package_sha256': None, 'body_sha256': None, 'pose_sha256': None,
            'recipe_sha256': None, 'generator_sha256': None, 'metadata': {'fixture': 'portable'}}


def mesh(identity='material', reverse=False, opposite=False):
    faces = [[0,1,3],[1,2,3]] if opposite else [[0,1,2],[0,2,3]]
    if reverse: faces = [list(reversed(row)) for row in faces]
    return {'id': identity, 'uv_cm': [[0,0],[2,0],[2,2],[0,2]],
            'vertex_ids': ['v0','v1','v2','v3'], 'face_ids': ['f0','f1'],
            'triangles': faces, 'edges': {'bottom': ['v0','v1'], 'bent': ['v0','v1','v2']}}


def fixture(break_height=2., reverse=False, fresh_break=0., previous=True, domain='material', opposite=False):
    source = mesh(domain, reverse=reverse)
    carrier = mesh('carrier', reverse=reverse, opposite=opposite)
    fresh_mesh = mesh('reference', reverse=reverse)
    current = [[0,0,0],[2,0,0],[2,2,0],[0,2,break_height]]
    fresh = [[0,0,0],[2,0,0],[2,2,0],[0,2,fresh_break]]
    samples = [{'id':'third','source_face_id':'f0','source_barycentric_weights':['2/3','1/3','0']}]
    c = field.compile_material_surface_field(source,carrier,
        {'mesh':fresh_mesh,'coordinates_cm':fresh},current,
        previous_coordinates_cm=fresh if previous else None,samples=samples,clock=lambda:0.)
    path = {'id':'cross','domain_id':domain,'source_sha256':digest(source),
            'vertices':[{'id':'start','uv_cm':[0,1]}, {'id':'end','uv_cm':[2,1]}]}
    bar = {'id':'bar','trace_id':'cross','start_vertex_id':'start','end_vertex_id':'end','source_length_cm':2.}
    return {domain:c}, [path], [bar]


def observe(fields=None, paths=None, bars=None, **kwargs):
    if fields is None: fields,paths,bars=fixture()
    return traces.observe_material_surface_traces(fields,paths,bars,
        context=kwargs.pop('context',context()),clock=kwargs.pop('clock',lambda:0.),**kwargs)


def nodes(value):
    if type(value) is dict:return 1+sum(nodes(v) for v in value.values())
    if type(value) is list:return 1+sum(nodes(v) for v in value)
    return 1


def byte_count(value):
    return len(json.dumps(value,ensure_ascii=False,separators=(',',':'),allow_nan=False).encode('utf8'))


class PhaseClock:
    def __init__(self,phase,action=None):self.phase=phase;self.action=action;self.triggered=False;self.time=0.
    def __call__(self):
        frame=sys._getframe(1);hit=False
        while frame:
            hit |= frame.f_code.co_name=='check' and frame.f_locals.get('phase')==self.phase
            frame=frame.f_back
        if hit and not self.triggered:
            self.triggered=True
            if self.action:self.action()
            else:self.time=60.
        return self.time


class MaterialSurfaceTraceTests(unittest.TestCase):
    def refusal(self,reason,call,incomplete=False):
        with self.assertRaises(StudioError) as caught:call()
        self.assertEqual(caught.exception.reason,reason)
        self.assertEqual(caught.exception.status,'INCOMPLETE' if incomplete else 'REFUSED')
        self.assertEqual(caught.exception.qualification,'NONE')
        return caught.exception

    def test_hidden_affine_break_sqrt_two_plus_one_not_endpoint_sqrt_five(self):
        r=observe();t=r['traces'][0];s=t['segments'][0]
        self.assertEqual([F(e['t']) for e in s['events']],[0,F(1,2),1])
        self.assertEqual([F(p['lengths']['candidate']['squared_norm_exact_cm2']) for p in s['chunks']],[2,1])
        self.assertEqual(F(t['endpoint_chords']['candidate']['squared_norm_exact_cm2']),5)
        measured=t['continuous_lengths']['candidate']
        self.assertLessEqual(measured['lower_cm'],math.sqrt(2)+1)
        self.assertGreaterEqual(measured['upper_cm'],math.sqrt(2)+1)
        self.assertGreater(measured['lower_cm'],t['endpoint_chords']['candidate']['upper_cm'])
        self.assertEqual(t['length_observation']['status'],'MEASURED_NO_ACCEPTANCE_BOUND')
        self.assertEqual(r['bars'][0]['length_observation']['status'],'MEASURED_NO_ACCEPTANCE_BOUND')
        self.assertEqual(r['hard_rows_added'],[]);self.assertEqual(r['physical_pins_added'],[])
        self.assertEqual(r['qualification'],'NONE');self.assertEqual(r['fitting'],'NOT_QUALIFIED')

    def test_global_affine_and_three_fields_separate(self):
        f,p,b=fixture(break_height=0.,fresh_break=2.)
        r=observe(f,p,b);t=r['traces'][0]
        self.assertLessEqual(t['continuous_lengths']['candidate']['lower_cm'],2.)
        self.assertGreaterEqual(t['continuous_lengths']['candidate']['upper_cm'],2.)
        self.assertGreater(t['continuous_lengths']['fresh_reference']['lower_cm'],2.)
        self.assertEqual(t['continuous_lengths']['previous'],t['continuous_lengths']['fresh_reference'])
        f,p,b=fixture(previous=False);t=observe(f,p,b)['traces'][0]
        self.assertNotIn('previous',t['continuous_lengths']);self.assertIsNone(t['vertices'][0]['previous'])

    def test_reference_break_not_at_carrier_nodes_is_preserved(self):
        f,p,b=fixture(break_height=0.)
        compiled=f['material'];src=compiled['inputs']['source'];car=compiled['inputs']['carrier']
        ref=mesh('reference');ref['uv_cm'].append([1,1]);ref['vertex_ids'].append('center')
        ref['triangles']=[[0,1,4],[1,2,4],[2,3,4],[3,0,4]];ref['face_ids']=['r0','r1','r2','r3']
        f['material']=field.compile_material_surface_field(src,car,
            {'mesh':ref,'coordinates_cm':[[0,0,0],[2,0,0],[2,2,0],[0,2,0],[1,1,2]]},
            compiled['inputs']['coordinates_cm'],clock=lambda:0.)
        t=observe(f,p,b)['traces'][0]
        self.assertEqual(t['segments'][0]['events'][1]['fresh_reference']['coordinates_exact_cm'],['1','1','2'])
        self.assertGreater(t['continuous_lengths']['fresh_reference']['lower_cm'],4.)

    def test_shared_edge_not_double_length_and_both_windings(self):
        for reverse in [False,True]:
            f,p,b=fixture(break_height=0.,reverse=reverse)
            p[0]['vertices']=[{'id':'start','uv_cm':[0,0]},{'id':'end','uv_cm':[2,2]}]
            s=observe(f,p,b)['traces'][0]['segments'][0]
            self.assertEqual(len(s['chunks']),1)
            self.assertEqual(s['chunks'][0]['covering_face_ids']['carrier'],['f0','f1'])
            self.assertEqual(F(s['chunks'][0]['lengths']['candidate']['squared_norm_exact_cm2']),8)

    def test_tangent_at_vertex_keeps_event_not_extra_positive_interval(self):
        f,p,b=fixture(break_height=0.)
        p[0]['vertices']=[{'id':'start','uv_cm':[0,0]},{'id':'end','uv_cm':[2,0]}]
        s=observe(f,p,b)['traces'][0]['segments'][0]
        self.assertEqual(len(s['chunks']),1);self.assertEqual(len(s['events']),2)

    def test_outside_domain_between_valid_endpoints_concave_domain(self):
        source={'id':'material','uv_cm':[[0,0],[2,0],[2,1],[1,1],[1,2],[0,2]],
                'vertex_ids':['v'+str(i) for i in range(6)],'face_ids':['f'+str(i) for i in range(4)],
                'triangles':[[0,1,3],[1,2,3],[0,3,5],[3,4,5]]}
        coords=[uv+[0] for uv in source['uv_cm']]
        c=field.compile_material_surface_field(source,copy.deepcopy(source),
            {'mesh':copy.deepcopy(source),'coordinates_cm':coords},coords,clock=lambda:0.)
        path={'id':'cross','domain_id':'material','source_sha256':digest(source),
              'vertices':[{'id':'start','uv_cm':[2,1]},{'id':'end','uv_cm':[1,2]}]}
        e=self.refusal('TRACE_DOMAIN_COVERAGE',lambda:observe({'material':c},[path],[]))
        self.assertGreater(e.work['pair_checks'],0)

    def test_near_half_fractions_and_source_identities_remain_distinct(self):
        f,p,b=fixture();near=F(.49999975746439695)
        p[0]['vertices']=[{'id':'start','uv_cm':[0,1],'fraction':'0'},
            {'id':'near','uv_cm':[str(2*near),'1'],'fraction':.49999975746439695},
            {'id':'half','uv_cm':['1','1'],'fraction':'1/2'},
            {'id':'end','uv_cm':[2,1],'fraction':'1'}]
        t=observe(f,p,b)['traces'][0]
        self.assertEqual([v['id'] for v in t['vertices']],['start','near','half','end'])
        self.assertNotEqual(t['vertices'][1]['exact_uv_cm'],t['vertices'][2]['exact_uv_cm'])
        self.assertNotEqual(t['vertices'][1]['declared_fraction_exact'],t['vertices'][2]['declared_fraction_exact'])
        self.assertGreater(F(t['segments'][1]['chunks'][0]['lengths']['candidate']['squared_norm_exact_cm2']),0)

    def test_ieee_third_target_soft_residual_and_no_hard_equality(self):
        f,p,b=fixture(break_height=0.)
        p[0]['vertices']=[{'id':'start','sample_id':'third','target_cm':[2/3,0,0]},
                          {'id':'end','source_vertex_id':'v1'}]
        r=observe(f,p,b);soft=r['traces'][0]['vertices'][0]['target_observation']
        self.assertEqual(soft['strength'],'SOFT_OBSERVATION')
        self.assertEqual(F(soft['residual_exact_cm'][0]),F(2,3)-F(2/3))
        self.assertEqual(r['hard_rows_added'],[])

    def test_distinct_samples_at_identical_uv_are_not_merged(self):
        f,p,b=fixture(break_height=0.)
        p[0]['vertices'].insert(1,{'id':'other-start','uv_cm':[0,1],'fraction':'1/2'})
        t=observe(f,p,b)['traces'][0]
        self.assertEqual([v['id'] for v in t['vertices']],['start','other-start','end'])
        self.assertEqual(F(t['segments'][0]['chunks'][0]['lengths']['candidate']['squared_norm_exact_cm2']),0)
        self.assertEqual([e['path_vertex_ids'] for e in t['segments'][0]['events']],[['start'],['other-start']])

    def test_exact_band_within_outside_overlap_and_wrong_quantity(self):
        f,p,b=fixture();p[0]['length_band']={'quantity':'candidate_continuous_trace_length','lower_cm':2.,'upper_cm':3.}
        self.assertEqual(observe(f,p,b)['traces'][0]['length_observation']['status'],'WITHIN_DECLARED_BAND')
        p[0]['length_band']['upper_cm']=2.2
        self.assertEqual(observe(f,p,b)['traces'][0]['length_observation']['status'],'OUTSIDE_DECLARED_BAND')
        f,p,b=fixture(break_height=0.)
        p[0]['length_band']={'quantity':'candidate_continuous_trace_length','lower_cm':2.,'upper_cm':2.}
        self.assertEqual(observe(f,p,b)['traces'][0]['length_observation']['status'],'INDETERMINATE_BOUND_OVERLAP')
        p[0]['length_band']['quantity']='historical_polyline_length'
        self.refusal('INVALID_LENGTH_BAND',lambda:observe(f,p,b))

    def test_historical_bounds_are_never_continuous_allowance(self):
        f,p,b=fixture();p[0]['historical_observation']={'summed_IEEE_bound_cm':100.,'satisfied_IEEE':True}
        t=observe(f,p,b)['traces'][0]
        self.assertEqual(t['length_observation']['status'],'MEASURED_NO_ACCEPTANCE_BOUND')
        self.assertFalse(t['historical_bounds_applied_to_continuous_length'])

    def test_explicit_partner_missing_transport_not_assessed_or_refused(self):
        f,p,b=fixture();partner=copy.deepcopy(p[0]);partner['id']='partner';p.append(partner)
        p[0]['partner_trace_id']='partner'
        r=observe(f,p,b)
        self.assertEqual(r['traces'][0]['partner_observation'],'NOT_ASSESSED_NO_CONTINUOUS_TRANSPORT')
        p[0]['require_continuous_partner']=True
        self.refusal('MISSING_TRANSPORT',lambda:observe(f,p,b))
        p[0].pop('require_continuous_partner');p[0]['partner_trace_id']='absent'
        self.refusal('MISSING_PARTNER',lambda:observe(f,p,b))

    def test_boundary_orientation_and_skipped_bent_source_corner(self):
        f,p,b=fixture(break_height=0.)
        p[0]['vertices']=[{'id':'start','source_vertex_id':'v1'},{'id':'end','source_vertex_id':'v0'}]
        p[0]['edge_id']='bottom';p[0]['orientation']='reverse'
        self.assertEqual(observe(f,p,b)['traces'][0]['coverage'],'COMPLETE_EXACT_PROVIDED_UV_PATH')
        p[0]['orientation']='forward';self.refusal('INVALID_BOUNDARY',lambda:observe(f,p,b))
        p[0]['edge_id']='bent';p[0]['vertices']=[{'id':'start','source_vertex_id':'v0'},{'id':'end','source_vertex_id':'v2'}]
        self.refusal('MISSING_SOURCE_CORNER',lambda:observe(f,p,b))

    def test_revalidation_once_per_domain_shared_cost_and_domain_cap(self):
        f,p,b=fixture();right,rp,rb=fixture(domain='right')
        rp[0]['id']='right-trace';f.update(right);p+=rp
        calls=[];real=field._from_compiled
        def recording(compiled,budget):calls.append(compiled['inputs']['source']['id']);return real(compiled,budget)
        with patch.object(field,'_from_compiled',recording):r=observe(f,p,b)
        self.assertEqual(calls,['material','right'])
        self.assertEqual(r['receipt']['work']['source_vertices'],8)
        self.assertEqual(r['receipt']['work']['carrier_vertices'],16)
        self.assertEqual(r['domain_revalidation_count'],{'material':1,'right':1})
        e=self.refusal('BUDGET_EXHAUSTED',lambda:observe(f,p,b,budgets={'max_source_vertices':7}),True)
        self.assertEqual(e.work['source_vertices'],4)
        self.refusal('BUDGET_EXHAUSTED',lambda:observe(f,p,b,budgets={'max_domains':1}),True)

    def test_all_counted_work_caps_at_exact_and_one_less(self):
        f,p,b=fixture();base=observe(f,p,b)
        for key in ['queries','pair_checks','intersection_patches','patch_vertex_checks','fraction_operations']:
            cap=base['receipt']['work'][key]
            r=observe(f,p,b,budgets={'max_'+key:cap})
            self.assertEqual(r['receipt']['work'][key],cap)
            self.refusal('BUDGET_EXHAUSTED',lambda key=key,cap=cap:observe(f,p,b,budgets={'max_'+key:cap-1}),True)

    def test_output_entire_receipt_nodes_and_compact_unicode_bytes(self):
        f,p,b=fixture();c=context();c['metadata']['fixture']='épreuve'
        r=observe(f,p,b,context=c)
        self.assertEqual(nodes(r),r['receipt']['work']['output_nodes'])
        self.assertEqual(byte_count(r),r['receipt']['work']['output_bytes'])
        cap=nodes(r);self.assertEqual(nodes(observe(f,p,b,context=c,budgets={'max_output_nodes':cap})),cap)
        self.refusal('BUDGET_EXHAUSTED',lambda:observe(f,p,b,context=c,budgets={'max_output_nodes':cap-1}),True)
        # cap representation affects byte count, settle its digit length first.
        cap=byte_count(r)
        for _ in range(3):
            try:r=observe(f,p,b,context=c,budgets={'max_output_bytes':cap})
            except StudioError:cap+=16;continue
            size=byte_count(r)
            if size==cap:break
            cap=size
        r=observe(f,p,b,context=c,budgets={'max_output_bytes':cap})
        self.assertEqual(byte_count(r),cap)
        self.refusal('BUDGET_EXHAUSTED',lambda:observe(f,p,b,context=c,budgets={'max_output_bytes':cap-1}),True)

    def test_deadlines_before_capture_clipping_sqrt_and_final_hash(self):
        f,p,b=fixture()
        self.refusal('DEADLINE_EXHAUSTED',lambda:observe(f,p,b,deadline=0.),True)
        for phase in ['trace_clipping','trace_sqrt_after','output_serialization','output_terminal_deadline']:
            clock=PhaseClock(phase)
            e=self.refusal('DEADLINE_EXHAUSTED',lambda:observe(f,p,b,clock=clock),True)
            self.assertTrue(clock.triggered)
            if phase!='trace_clipping':self.assertGreater(e.work['queries'],0)

    def test_work_in_final_preservation_digest_expiring_deadline_refuses(self):
        f,p,b=fixture();now=[0.];real=uv._digest;triggered=[]
        def slow_digest(value):
            frame=inspect.currentframe().f_back
            if frame.f_code.co_name=='_finish' and 'budget' in frame.f_locals:
                budget=frame.f_locals['budget']
                if budget.phase=='output_deadline_after_preservation':now[0]=60.;triggered.append(True)
            return real(value)
        with patch.object(uv,'_digest',slow_digest):
            self.refusal('DEADLINE_EXHAUSTED',lambda:observe(f,p,b,clock=lambda:now[0]),True)
        self.assertTrue(triggered)

    def test_mutation_and_no_input_or_output_alias(self):
        f,p,b=fixture();c=context();before=copy.deepcopy([f,p,b,c])
        r=observe(f,p,b,context=c)
        self.assertEqual([f,p,b,c],before)
        r['traces'][0]['declaration']['vertices'][0]['uv_cm'][0]=99
        r['context']['metadata']['fixture']='changed';self.assertEqual([f,p,b,c],before)
        clock=PhaseClock('trace_clipping',lambda:p[0]['vertices'][0]['uv_cm'].__setitem__(0,99))
        self.refusal('REFERENCE_MUTATION',lambda:observe(f,p,b,context=c,clock=clock))

    def test_changed_fields_refuse_and_paths_context_bindings_invalidate(self):
        f,p,b=fixture();base=observe(f,p,b)
        changed=copy.deepcopy(f);changed['material']['inputs']['coordinates_cm'][0][0]+=.1
        self.refusal('REFERENCE_MUTATION',lambda:observe(changed,p,b))
        p[0]['vertices'][0]['uv_cm'][1]='1/2'
        r=observe(f,p,b);self.assertNotEqual(base['receipt']['input_hashes']['paths'],r['receipt']['input_hashes']['paths'])
        c=context();c['pose_sha256']='a'*64
        r=observe(f,p,b,context=c);self.assertNotEqual(base['receipt']['input_hashes']['context'],r['receipt']['input_hashes']['context'])
        bad=copy.deepcopy(p);bad[0]['source_sha256']='0'*64
        self.refusal('SOURCE_IDENTITY',lambda:observe(f,bad,b))
        self.refusal('DOMAIN_IDENTITY',lambda:observe({'alias':f['material']},p,b))

    def test_order_independent_payload_and_bar_bindings(self):
        f,p,b=fixture();other=copy.deepcopy(p[0]);other['id']='another';p.append(other)
        bar=copy.deepcopy(b[0]);bar['id']='another-bar';bar['trace_id']='another';b.append(bar)
        a=observe(f,p,b);z=observe(f,list(reversed(p)),list(reversed(b)))
        self.assertEqual(a['traces'],z['traces']);self.assertEqual(a['bars'],z['bars'])
        b[0]['end_vertex_id']='missing';self.refusal('INVALID_BAR',lambda:observe(f,p,b))

    def test_hostile_numbers_identity_and_undeclared_context(self):
        f,p,b=fixture()
        for value in [True,float('nan'),'1/02']:
            bad=copy.deepcopy(p);bad[0]['vertices'][0]['uv_cm'][0]=value
            self.refusal('INVALID_REFERENCE' if type(value)is float else 'INVALID_NUMBER',lambda:observe(f,bad,b))
        bad=copy.deepcopy(p);bad[0]['vertices'][1]['id']='start'
        self.refusal('IDENTITY_COLLISION',lambda:observe(f,bad,b))
        bad=copy.deepcopy(p);bad[0]['vertices'][0]['fraction']=1.1
        self.refusal('INVALID_PARAMETER',lambda:observe(f,bad,b))
        c=context();c['body_sha256']='not-a-hash'
        self.refusal('INVALID_CONTEXT',lambda:observe(f,p,b,context=c))
        self.assertEqual(len(observe(f,p,b)['undeclared_context_identities']),5)

    def test_norm_bracket_rational_square_proof_large_tiny_and_zero(self):
        budget=traces.constraints._Budget(None,None,lambda:0.)
        for vector in [[F(0)]*3,[F(1),F(1),F(0)],[F(10)**200,F(0),F(0)],
                       [F(1,10**200),F(0),F(0)],[F(1,3),F(2,3),F(0)]]:
            measured=traces._norm([F(0)]*3,vector,budget)
            q=sum(x*x for x in vector)
            self.assertLessEqual(measured['lower_exact_cm']**2,q)
            self.assertGreaterEqual(measured['upper_exact_cm']**2,q)
            self.assertTrue(math.isfinite(measured['lower_cm']) and math.isfinite(measured['upper_cm']))


if __name__=='__main__':unittest.main()
