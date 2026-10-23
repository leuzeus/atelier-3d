import copy
from fractions import Fraction as F
import hashlib
import inspect
import json
from pathlib import Path
import unittest

from a3d import material_reference_partition as m
from a3d.core import StudioError
from a3d.material_sample_carrier import _digest


def square(pid='square',clockwise=False):
    faces=[[0,1,2],[0,2,3]]
    if clockwise:faces=[list(reversed(f))for f in faces]
    return {'id':pid,'uv_cm':[[0,0],[1,0],[1,1],[0,1]],'triangles':faces,
        'vertex_ids':['v0','v1','v2','v3'],'face_ids':['f0','f1'],
        'edges':{'bottom':['v0','v1']}}


def binding(sources):
    return {'candidate_id':'new-candidate','run_id':'new-run','predecessor_candidate_id':'old-candidate',
        'predecessor_run_id':'old-run','source_sha256':_digest(sources),
        'recipe_sha256':'a'*64,'body_sha256':'b'*64,
        'code_sha256':hashlib.sha256(Path(m.__file__).read_bytes()).hexdigest()}


def sections(pid='square'):
    return [{'id':'section-low','domain_id':pid,'v_cm':'1/3'},
            {'id':'section-high','domain_id':pid,'v_cm':'2/3'}]


def build(sources=None,ss=None,n=2,samples=None,**kw):
    sources=[square()]if sources is None else sources
    ss=sections()if ss is None else ss
    kw.setdefault('clock',lambda:0.)
    return m.prepare_material_reference_partition(sources,ss,n,binding(sources),material_samples=samples,**kw)


def sample(identity='point',role='notch',support=None,pid='square'):
    return {'id':identity,'domain_id':pid,'role':role,
        'support':{'kind':'source_segment','vertex_ids':['v0','v1'],'fraction':'1/2'}if support is None else support}


def area(result):
    out=F(0);nodes=result['global_nodes']
    for f in result['global_triangles']:
        a,b,c=[[F(x)for x in nodes[i]['uv_cm']]for i in f['nodes']]
        out+=((b[0]-a[0])*(c[1]-a[1])-(b[1]-a[1])*(c[0]-a[0]))/2
    return out


def value_nodes(v):
    return 1+sum(map(value_nodes,v.values()))if type(v)is dict else 1+sum(map(value_nodes,v))if type(v)is list else 1


class PhaseClock:
    def __init__(self,phase,mutate=None):self.phase=phase;self.value=0.;self.mutate=mutate;self.hit=False
    def __call__(self):
        f=inspect.currentframe().f_back
        for _ in range(5):
            if f is None:break
            if f.f_locals.get('phase')==self.phase:
                self.hit=True
                if self.mutate is None:self.value=1.
                else:self.mutate();self.mutate=lambda:None
            f=f.f_back
        return self.value


class MaterialReferencePartitionTests(unittest.TestCase):
    def refused(self,fn,reason=None):
        with self.assertRaises(StudioError)as cm:fn()
        self.assertEqual(cm.exception.qualification,'NONE')
        if reason:self.assertEqual(cm.exception.reason,reason)
        self.assertIn(cm.exception.status,('INCOMPLETE','REFUSED'))
        return cm.exception

    def test_integer_n8_clipping_area_support_and_full_certificate(self):
        r=build(n=8);self.assertEqual(area(r),1)
        self.assertEqual(len(r['seed_parents']),128)
        self.assertTrue(all(len(p['child_cell_ids'])>=1 for p in r['seed_parents']))
        self.assertEqual(r['fresh_reference'],'NOT_CREATED');self.assertEqual(r['pins'],[])
        self.assertEqual(r['generated_seams'],[]);self.assertFalse(r['is_installable'])
        for p in r['global_nodes']:
            self.assertEqual(sum(F(w)for _,w in p['source_weights']),1)
            self.assertTrue(all(F(w)>=0 for _,w in p['source_weights']))
        v=m.verify_material_reference_partition(r,clock=lambda:0.)
        self.assertEqual(v['status'],'CERTIFICATE_VERIFIED_TEST_ONLY')
        self.assertEqual(v['global_triangles'],r['global_triangles'])

    def test_n8_clipped_boundary_is_exact_once_and_no_unused_seed(self):
        r=build(n=8);edges={};used=set()
        for tri in r['global_triangles']:
            f=tri['nodes'];used.update(f)
            for a,c in zip(f,f[1:]+f[:1]):edges.setdefault(tuple(sorted((a,c))),[]).append((a,c))
        self.assertEqual(used,set(range(len(r['global_nodes']))))
        self.assertEqual(len(used)-len(edges)+len(r['global_triangles']),1)
        spans={('x',F(0)):[],('x',F(1)):[],('y',F(0)):[],('y',F(1)):[]}
        for edge,owners in edges.items():
            self.assertIn(len(owners),(1,2))
            if len(owners)==2:self.assertEqual(owners[0],tuple(reversed(owners[1])));continue
            a,c=[[F(x)for x in r['global_nodes'][i]['uv_cm']]for i in edge]
            if a[0]==c[0]and a[0]in(0,1):key=('x',a[0]);interval=sorted((a[1],c[1]))
            else:self.assertEqual(a[1],c[1]);self.assertIn(a[1],(0,1));key=('y',a[1]);interval=sorted((a[0],c[0]))
            spans[key].append(interval)
        for intervals in spans.values():
            end=F(0)
            for lo,hi in sorted(intervals):self.assertEqual(lo,end);end=hi
            self.assertEqual(end,1)

    def test_exact_source_fractions_are_not_ieee_roundtrip(self):
        s=square();s['uv_cm'][2]=[.7,.9];s['uv_cm'][3]=[0,.9]
        r=build([s],[],n=8)
        orig=[tuple(map(F,p))for p in s['uv_cm']]
        for p in r['global_nodes']:
            expected=[sum(F(w)*orig[int(v[1:])][k]for v,w in p['source_weights'])for k in (0,1)]
            self.assertEqual(list(map(F,p['uv_cm'])),expected)

    def test_reorder_vertex_face_section_input_geometry_stable(self):
        s=square();r=build([s]);t=copy.deepcopy(s)
        order=[3,1,0,2];inv={old:new for new,old in enumerate(order)}
        t['uv_cm']=[s['uv_cm'][i]for i in order];t['vertex_ids']=[s['vertex_ids'][i]for i in order]
        t['face_ids']=list(reversed(s['face_ids']))
        t['triangles']=[[inv[i]for i in f[1:]+f[:1]]for f in reversed(s['triangles'])]
        rr=build([t],list(reversed(sections())))
        for k in ('source_tables','global_nodes','global_triangles','seed_parents','section_cells','work_views'):
            self.assertEqual(r[k],rr[k],k)

    def test_two_windings_keep_orientation(self):
        for clockwise in (False,True):
            r=build([square(clockwise=clockwise)])
            self.assertEqual(area(r),-1 if clockwise else 1)
            self.assertEqual(m.verify_material_reference_partition(r,clock=lambda:0.)['qualification'],'NONE')

    def test_rotated_scaled_source_material_support(self):
        s=square();s['uv_cm']=[[2-y*3,4+x*3]for x,y in s['uv_cm']]
        r=build([s],[{'id':'rotated-section','domain_id':'square','v_cm':'11/2'}],n=8)
        self.assertEqual(area(r),9)
        self.assertEqual(m.verify_material_reference_partition(r,clock=lambda:0.)['metric'],'NOT_ASSESSED')

    def test_close_fractions_notches_stay_samples_no_node_weld(self):
        a=sample('near',support={'kind':'source_segment','vertex_ids':['v0','v1'],'fraction':.49999975746439695})
        c=sample('half')
        r=build(samples=[a,c])
        self.assertNotEqual(r['material_samples'][0]['exact_uv_cm'],r['material_samples'][1]['exact_uv_cm'])
        self.assertTrue(all(s['reference_node_index']is None for s in r['material_samples']))
        self.assertEqual(len(r['global_nodes']),len(build()['global_nodes']))

    def test_equal_uv_distinct_sample_and_notch_identities(self):
        r=build(samples=[sample('notch'),sample('material',role='material_sample')])
        self.assertEqual(len(r['material_samples']),2)
        self.assertEqual(r['material_samples'][0]['exact_uv_cm'],r['material_samples'][1]['exact_uv_cm'])
        self.assertNotEqual(r['material_samples'][0]['id'],r['material_samples'][1]['id'])

    def test_explicit_segment_reference_nodes_split_both_owners(self):
        p=sample(role='reference_node',support={'kind':'source_segment','vertex_ids':['v0','v2'],'fraction':'1/3'})
        r=build(ss=[],samples=[p]);self.assertEqual(area(r),1)
        self.assertEqual(len(r['insertion_steps']),1)
        self.assertEqual(len(r['insertion_steps'][0]['parent_triangles']),2)
        self.assertTrue(any(not t['active']for t in r['triangle_archive']))
        self.assertIsNotNone(r['material_samples'][0]['reference_node_index'])
        m.verify_material_reference_partition(r,clock=lambda:0.)

    def test_explicit_interior_face_insertion_and_vertex_identity(self):
        p=sample('inside',role='reference_node',support={'kind':'source_face','face_id':'f0',
            'weights':[['v0','1/3'],['v1','1/3'],['v2','1/3']]})
        q=sample('original',support={'kind':'source_vertex','vertex_id':'v2'})
        r=build(ss=[],samples=[p,q]);self.assertEqual(area(r),1)
        self.assertEqual(len(r['insertion_steps'][0]['parent_triangles']),1)
        m.verify_material_reference_partition(r,clock=lambda:0.)

    def test_close_reference_node_insertions_no_proximity(self):
        a=sample('near',role='reference_node',support={'kind':'source_segment','vertex_ids':['v0','v1'],'fraction':.49999975746439695})
        c=sample('half',role='reference_node')
        r=build(ss=[],samples=[a,c]);self.assertEqual(area(r),1)
        self.assertNotEqual(*[s['reference_node_index']for s in r['material_samples']])

    def test_closure_detachable_never_become_seams(self):
        for kind in ('closure','detachable','permanent'):
            p=sample();p['relation_ref']={'id':'relation','kind':kind,'orientation':'reverse'}
            r=build(samples=[p]);self.assertEqual(r['generated_seams'],[])
            self.assertEqual(r['material_samples'][0]['definition']['relation_ref'],p['relation_ref'])

    def test_invalid_material_supports(self):
        bad=[{'kind':'rounded_uv','uv_cm':[.5,0]},
            {'kind':'source_segment','vertex_ids':['v1','v3'],'fraction':'1/2'},
            {'kind':'source_segment','vertex_ids':['v0','v1'],'fraction':'3/2'},
            {'kind':'source_vertex','vertex_id':'unknown'},
            {'kind':'source_face','face_id':'f0','weights':[['v0','1/3'],['v1','1/3']]},
            {'kind':'source_face','face_id':'f0','weights':[['v0','2'],['v1','-1']]},
            {'kind':'source_face','face_id':'f0','weights':[['v0','1/2'],['v0','1/2']]},
            {'kind':'source_face','face_id':'missing','weights':[['v0','1']]}]
        for support in bad:
            with self.subTest(support=support):self.refused(lambda:build(samples=[sample(support=support)]),'INVALID_SUPPORT')

    def test_source_exhaustive_refuses_overlap_gap_winding(self):
        for change in ('duplicate','hole','flip','overlap'):
            s=square()
            if change=='duplicate':s['triangles'][1]=s['triangles'][0]
            elif change=='hole':s['triangles'].pop();s['face_ids'].pop()
            elif change=='flip':s['triangles'][1].reverse()
            else:s['uv_cm'][3]=[F(1,2).__str__(),F(1,4).__str__()]
            with self.subTest(change=change):self.refused(lambda:build([s]))

    def test_topological_disk_flags_do_not_admit_overlapping_double_fan(self):
        s={'id':'double-fan','uv_cm':[[0,0],[1,0],[0,1],[-1,0],[0,-1],[2,0],[0,2],[-2,0],[0,-2]],
            'triangles':[[0,i,1 if i==8 else i+1]for i in range(1,9)],
            'vertex_ids':['v'+str(i)for i in range(9)],'face_ids':['f'+str(i)for i in range(8)]}
        e=self.refused(lambda:build([s],[]))
        self.assertIn(e.reason,('OVERLAP','AMBIGUOUS_SOURCE'))

    def test_source_precision_and_finiteness(self):
        for x in (float('nan'),float('inf'),'1/'+str(2**256)):
            s=square();s['uv_cm'][0][0]=x
            bb=binding([square()])
            with self.subTest(x=x):self.refused(lambda:m.prepare_material_reference_partition([s],[],2,bb,budgets={'max_fraction_bits':64},clock=lambda:0.))

    def test_hostile_native_shapes_refused_without_unhandled_exception(self):
        sources=[lambda s:s['triangles'][0].__setitem__(0,[]),lambda s:s['edges'].__setitem__('bottom',[[],{}])]
        for edit in sources:
            s=square();edit(s);self.refused(lambda:build([s]))
        supports=[{'kind':'source_vertex','vertex_id':[]},
            {'kind':'source_segment','vertex_ids':[[],{}],'fraction':'1/2'},
            {'kind':'source_face','face_id':[],'weights':[]},
            {'kind':'source_face','face_id':'f0','weights':[[[],'1']]}]
        for support in supports:self.refused(lambda:build(samples=[sample(support=support)]),'INVALID_SUPPORT')
        self.refused(lambda:build(ss=[{'id':'section','domain_id':[],'v_cm':'1/2'}]),'INVALID_IDENTITY')

    def test_duplicate_source_section_sample_and_invalid_section(self):
        self.refused(lambda:build([square(),square()]),'IDENTITY_COLLISION')
        self.refused(lambda:build(ss=[sections()[0],sections()[0]]),'INVALID_SECTION')
        self.refused(lambda:build(samples=[sample(),sample()]),'IDENTITY_COLLISION')
        self.refused(lambda:build(ss=[{'id':'outside','domain_id':'square','v_cm':2}]),'INVALID_SECTION')

    def test_certificate_refuses_corrupt_parent_weights_face_gap_overlap_flags(self):
        base=build()
        edits=[lambda r:r['global_nodes'][1]['source_weights'].__setitem__(0,['v0','2']),
            lambda r:r['seed_parents'][0].__setitem__('source_face_id','unknown'),
            lambda r:r['section_cells'][0].__setitem__('parent_seed_id','missing'),
            lambda r:r['global_triangles'].pop(),lambda r:r['global_triangles'].append(r['global_triangles'][0]),
            lambda r:r.__setitem__('qualification','PASS'),lambda r:r.__setitem__('euler_valid',True),
            lambda r:r['input_payload']['sources'][0]['uv_cm'][0].__setitem__(0,'1/100')]
        for change in edits:
            r=copy.deepcopy(base);change(r)
            self.refused(lambda:m.verify_material_reference_partition(r,clock=lambda:0.))

    def test_binding_source_code_and_old_run_refused(self):
        s=[square()]
        for key,value in [('source_sha256','0'*64),('code_sha256','0'*64),('run_id','old-run'),('candidate_id','old-candidate')]:
            bb=binding(s);bb[key]=value
            self.refused(lambda:m.prepare_material_reference_partition(s,sections(),2,bb,clock=lambda:0.))

    def test_immutable_inputs_and_receipt_hashes(self):
        s=[square()];ss=sections();p=[sample()];before=copy.deepcopy([s,ss,p]);r=build(s,ss,samples=p)
        self.assertEqual(before,[s,ss,p]);self.assertTrue(r['receipt']['inputs_preserved'])
        self.assertEqual(r['receipt']['work']['output_nodes'],value_nodes(r))
        self.assertEqual(r['receipt']['work']['output_bytes'],len(json.dumps(r,ensure_ascii=False,allow_nan=False,separators=(',',':')).encode('utf-8')))

    def test_mutation_during_clipping_is_refused(self):
        s=[square()];c=PhaseClock('rational_section_clipping',lambda:s[0]['uv_cm'][0].__setitem__(0,.1))
        self.refused(lambda:build(s,clock=c),'REFERENCE_MUTATION');self.assertTrue(c.hit)

    def test_deadline_before_capture_during_phases_and_after_last_hash(self):
        for phase in ('before_capture','source_exhaustive_clipping','rational_section_clipping','constructive_ear','code_after_hash','output_serialization','output_terminal_deadline'):
            c=PhaseClock(phase)
            with self.subTest(phase=phase):self.refused(lambda:build(clock=c,deadline=1),'DEADLINE_EXHAUSTED');self.assertTrue(c.hit)
        c=PhaseClock('output_terminal_deadline');r=build()
        self.refused(lambda:m.verify_material_reference_partition(r,clock=c,deadline=1),'DEADLINE_EXHAUSTED')
        self.refused(lambda:build(clock=lambda:1.,deadline=1.),'DEADLINE_EXHAUSTED')

    def test_caps_source_controls_triangles_samples_sections_input(self):
        for cap,value in [('max_source_points',3),('max_source_triangles',1),('max_controls',3),('max_triangles',1),('max_sections',1),('max_input_nodes',1),('max_input_bytes',100),('max_fraction_operations',1)]:
            with self.subTest(cap=cap):self.refused(lambda:build(budgets={cap:value}),'BUDGET_EXHAUSTED')
        self.refused(lambda:build(samples=[sample('a'),sample('b')],budgets={'max_samples':1}),'BUDGET_EXHAUSTED')

    def test_global_domains_share_controls_and_pairs_no_budget_reset(self):
        a=square('a');c=square('c');one=build([a],[],n=2)
        cap=one['receipt']['work']['controls']
        self.refused(lambda:build([a,c],[],n=2,budgets={'max_controls':cap}),'BUDGET_EXHAUSTED')
        self.refused(lambda:build([a,c],[],n=2,budgets={'max_pair_checks':1}),'BUDGET_EXHAUSTED')

    def test_exhaustive_source_pair_preflight_even_under_source_size_cap(self):
        s=square();s['triangles']=[[0,1,2]]*5;s['face_ids']=['f'+str(i)for i in range(5)]
        self.refused(lambda:build([s],[],budgets={'max_pair_checks':9}),'BUDGET_EXHAUSTED')

    def test_rational_operation_default_hard_exact_boundary_not_real_campaign(self):
        for maximum in (300000,5000000):
            b=m._Budget({'max_fraction_operations':maximum},None,lambda:0.)
            b.take('fraction_operations',maximum)
            self.assertEqual(b.counts['fraction_operations'],maximum)
            self.refused(lambda:b.q(F(1)),'BUDGET_EXHAUSTED')
            self.assertEqual(b.counts['fraction_operations'],maximum)
        self.refused(lambda:build(budgets={'max_fraction_operations':5000001}),'INVALID_BUDGET')

    def test_complete_output_node_and_byte_caps_include_receipt(self):
        r=build();nodes=r['receipt']['work']['output_nodes']
        self.assertEqual(build(budgets={'max_output_nodes':nodes})['receipt']['work']['output_nodes'],nodes)
        self.refused(lambda:build(budgets={'max_output_nodes':nodes-1}),'BUDGET_EXHAUSTED')
        size=r['receipt']['work']['output_bytes']
        for _ in range(4):
            rr=build(budgets={'max_output_bytes':size});nextsize=rr['receipt']['work']['output_bytes']
            if size==nextsize:break
            size=nextsize
        self.assertEqual(size,nextsize)
        self.refused(lambda:build(budgets={'max_output_bytes':size-1}),'BUDGET_EXHAUSTED')

    def test_verifier_complete_output_and_shared_work_accounting(self):
        compiled=build();r=m.verify_material_reference_partition(compiled,clock=lambda:0.)
        self.assertEqual(r['receipt']['work']['output_nodes'],value_nodes(r))
        self.assertEqual(r['receipt']['work']['output_bytes'],len(json.dumps(r,ensure_ascii=False,allow_nan=False,separators=(',',':')).encode('utf-8')))
        self.assertGreater(r['receipt']['work']['input_nodes'],compiled['receipt']['work']['input_nodes'])
        cap=r['receipt']['work']['output_nodes']
        m.verify_material_reference_partition(compiled,clock=lambda:0.,budgets={'max_output_nodes':cap})
        self.refused(lambda:m.verify_material_reference_partition(compiled,clock=lambda:0.,budgets={'max_output_nodes':cap-1}),'BUDGET_EXHAUSTED')
        for phase in ('source_exhaustive_clipping','rational_section_clipping','output_serialization'):
            c=PhaseClock(phase)
            self.refused(lambda:m.verify_material_reference_partition(compiled,clock=c,deadline=1.),'DEADLINE_EXHAUSTED')
            self.assertTrue(c.hit)

    def test_unknown_budgets_nonmonotone_clock_and_no_old_reference_input(self):
        self.refused(lambda:build(budgets={'max_reference_vertices':4000}),'INVALID_BUDGET')
        self.refused(lambda:build(budgets={'max_seconds':60.00001}),'INVALID_BUDGET')
        seq=iter([0.,-1.]);self.refused(lambda:build(clock=lambda:next(seq)),'INVALID_CLOCK')
        r=build();r['input_payload']['S_fresh']=[[0,0,0]]
        self.refused(lambda:m.verify_material_reference_partition(r,clock=lambda:0.),'INVALID_CONTRACT')


if __name__=='__main__':unittest.main()
