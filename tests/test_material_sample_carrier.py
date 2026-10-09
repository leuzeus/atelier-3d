import copy
import json
import inspect
import math
import unittest
from fractions import Fraction as F

from a3d.core import StudioError, digest
from a3d.material_sample_carrier import (
    DISCRIMINANT, build_material_sample_carrier, build_rectangular_material_carrier,
)
from a3d.guide_cage_sampling import validated_cage_state
from a3d.source_seam_coupling import _Budget


def rectangle(identity='material', opposite=False):
    return {'id':identity,'uv_cm':[[0,0],[4,0],[4,2],[0,2]],
        'vertex_ids':['v0','v1','v2','v3'],'face_ids':['f0','f1'],
        'triangles':[[0,1,3],[1,2,3]] if opposite else [[0,1,2],[0,2,3]],
        'edges':{'bottom':['v0','v1'],'right':['v1','v2'],'top':['v2','v3'],'left':['v3','v0']}}


def sample(identity='sample', x='1/2'):
    x=F(x)
    return {'id':identity,'source_face_id':'f0',
        'source_barycentric_weights':[str(1-x),str(x),'0']}


def external_relation(entries=None, kind='permanent', identity='seam'):
    entries=entries or [('start','0'),('end','1')]
    return {'id':identity,'kind':kind,'orientation':'forward','owners':[
        {'source_id':'material','edge_id':'bottom','samples':[
            {'sample_id':sid,'fraction':fraction} for sid,fraction in entries]},
        {'source_id':'other-panel','edge_id':'other-bottom','source_sha256':'a'*64,
            'source_vertex_ids':['e0','e1'],'samples':[
                {'sample_id':'external:'+sid,'fraction':fraction,
                 'source_segment_vertex_ids':['e0','e1'],'source_segment_parameter':fraction}
                for sid,fraction in entries]}]}


def build(source=None, carrier=None, samples=None, **options):
    return build_material_sample_carrier(source or rectangle(), carrier or rectangle('carrier',True),
        [] if samples is None else samples, clock=options.pop('clock',lambda:0.), **options)


class MaterialSampleCarrierTests(unittest.TestCase):
    def assertRefusal(self,reason,call):
        with self.assertRaises(StudioError) as caught:
            call()
        self.assertEqual(caught.exception.reason,reason)
        self.assertEqual(caught.exception.qualification,'NONE')

    def test_cross_source_faces_have_explicit_exact_intersection_maps(self):
        result=build(samples=[sample()])
        self.assertEqual(result['discriminant'],DISCRIMINANT)
        self.assertEqual(result['qualification'],'NONE')
        self.assertEqual(result['uv_qualification'],'EXACT_DOMAIN_COVERAGE_AND_SAMPLE_SUPPORT')
        patches=result['source_carrier_intersections']
        self.assertEqual(len(patches),4)
        self.assertEqual(sum(F(p['area_cm2']) for p in patches),8)
        self.assertEqual({p['source_face_id'] for p in patches},{'f0','f1'})
        for p in patches:
            self.assertEqual(sum(F(w) for w in p['source_barycentric_weights'][0]),1)
            self.assertEqual(sum(F(w) for w in p['carrier_barycentric_weights'][0]),1)
        self.assertFalse(result['physical_mesh'])
        self.assertFalse(result['is_installable'])
        self.assertEqual(result['constraints_3d'],'NOT_QUALIFIED')

    def test_legacy_source_conforming_validator_still_refuses_crossing_carrier(self):
        source,carrier=rectangle(),rectangle('carrier',True)
        self.assertEqual(build(source,carrier)['qualification'],'NONE')
        piece={'vertices':source['uv_cm'],'faces':source['triangles']}
        frame={'uv_cm':carrier['uv_cm'],'target_cm':[p+[0.] for p in carrier['uv_cm']],
            'triangles':carrier['triangles']}
        with self.assertRaisesRegex(StudioError,'not supported by one original source material face'):
            validated_cage_state(piece,frame,'material',8,_Budget({},lambda:0.),lambda uv:uv+[0.])

    def test_source_corner_identities_have_bindings_without_invented_samples(self):
        result=build()
        self.assertEqual(result['samples'],[])
        self.assertEqual({r['source_vertex_id'] for r in result['source_vertex_bindings']},{'v0','v1','v2','v3'})
        self.assertTrue(all(sum(F(w) for w in r['support']['sparse_vertex_weights'].values())==1 for r in result['source_vertex_bindings']))

    def test_near_fractions_and_coincident_distinct_identities_are_not_merged(self):
        values=[sample('a','1/2'),sample('b','500000001/1000000000'),sample('c','1/2')]
        result=build(samples=values)
        self.assertEqual([r['id'] for r in result['samples']],['a','b','c'])
        self.assertNotEqual(result['samples'][0]['exact_uv_cm'],result['samples'][1]['exact_uv_cm'])
        self.assertEqual(result['samples'][0]['exact_uv_cm'],result['samples'][2]['exact_uv_cm'])
        self.assertFalse(result['receipt']['identities_merged'])

    def test_midpoint_mark_can_be_distinct_from_a_near_partition(self):
        values=[sample('start','0'),sample('near','499999999/1000000000'),sample('mid','1/2'),sample('end','1')]
        relation=external_relation([('start','0'),('near','499999999/1000000000'),('end','1')])
        mark={'id':'seam-mid','relation_id':'seam','fraction':'1/2','symbol':'double-notch',
            'owners':[{'owner_index':0,'sample_id':'mid'}]}
        result=build(samples=values,relations=[relation],marks=[mark])
        self.assertEqual(result['assembly_marks'],[mark])
        self.assertEqual(result['relations'],[relation])
        self.assertFalse(result['external_source_references'][0]['geometry_checked'])
        self.assertEqual(result['normalized_arc_measurement'],'DECLARED_FRACTIONS_ONLY_NOT_MEASURED')

    def test_exact_shared_edge_supports_are_equivalent_sparse_rows(self):
        value={'id':'center','source_face_id':'f0','source_barycentric_weights':['1/2','0','1/2']}
        result=build(samples=[value])
        support=result['samples'][0]['carrier_support']
        self.assertEqual(support['equivalent_carrier_face_ids'],['f0','f1'])
        self.assertEqual(support['sparse_vertex_weights'],{'v1':'1/2','v3':'1/2'})

    def test_missing_source_coverage_is_refused(self):
        carrier={'id':'c','uv_cm':[[0,0],[4,0],[4,2]],'vertex_ids':['a','b','c'],
            'face_ids':['one'],'triangles':[[0,1,2]]}
        self.assertRefusal('DOMAIN_COVERAGE',lambda:build(carrier=carrier))

    def test_outside_carrier_extension_is_refused(self):
        carrier=rectangle('carrier');carrier['uv_cm'][1][0]=5;carrier['uv_cm'][2][0]=5
        self.assertRefusal('DOMAIN_COVERAGE',lambda:build(carrier=carrier))

    def test_source_gap_even_with_equal_total_area_is_refused(self):
        source=rectangle();source['uv_cm'][2]=[3,2]
        carrier=rectangle('carrier');carrier['uv_cm'][3]=[1,2]
        self.assertRefusal('DOMAIN_COVERAGE',lambda:build(source,carrier))

    def test_positive_area_overlap_is_refused(self):
        carrier={'id':'c','uv_cm':[[0,0],[4,0],[4,2],[3,1]],'vertex_ids':['a','b','c','d'],
            'face_ids':['one','two'],'triangles':[[0,1,2],[0,1,3]]}
        self.assertRefusal('NONMANIFOLD',lambda:build(carrier=carrier))

    def test_geometric_overlap_of_topologically_valid_disk_is_refused(self):
        source={'id':'self-crossing','uv_cm':[[0,0],[2,0],[0,2],[-2,0],[0,-2],[2,1]],
            'vertex_ids':['a','b','c','d','e','f'],'face_ids':['one','two','three','four'],
            'triangles':[[0,1,2],[0,2,3],[0,3,4],[0,4,5]]}
        self.assertRefusal('OVERLAP',lambda:build(source=source))
        source['uv_cm'][-1]=[1,0]
        self.assertRefusal('AMBIGUOUS_MESH',lambda:build(source=source))

    def test_duplicate_and_degenerate_triangles_are_refused(self):
        carrier=rectangle('c');carrier['triangles'][1]=[0,1,2]
        self.assertRefusal('OVERLAP',lambda:build(carrier=carrier))
        carrier=rectangle('c');carrier['uv_cm'][2]=[2,0]
        self.assertRefusal('DEGENERATE_MESH',lambda:build(carrier=carrier))

    def test_winding_changes_and_inconsistent_winding_are_refused(self):
        carrier=rectangle('c');carrier['triangles']=[list(reversed(f)) for f in carrier['triangles']]
        self.assertRefusal('WINDING',lambda:build(carrier=carrier))
        carrier=rectangle('c');carrier['triangles'][1].reverse()
        self.assertRefusal('WINDING',lambda:build(carrier=carrier))

    def test_disconnected_or_holey_material_is_not_implicitly_supported(self):
        source={'id':'s','uv_cm':[[0,0],[1,0],[0,1],[2,0],[3,0],[2,1]],
            'vertex_ids':['a','b','c','d','e','f'],'face_ids':['one','two'],
            'triangles':[[0,1,2],[3,4,5]]}
        self.assertRefusal('NONMANIFOLD',lambda:build(source=source))

    def test_coincident_mesh_vertices_are_refused_without_welding(self):
        carrier=rectangle('c');carrier['uv_cm'][3]=carrier['uv_cm'][0]
        self.assertRefusal('AMBIGUOUS_MESH',lambda:build(carrier=carrier))

    def test_material_sample_collision_and_wrong_source_support_are_refused(self):
        self.assertRefusal('IDENTITY_COLLISION',lambda:build(samples=[sample(),sample()]))
        bad=sample();bad['source_barycentric_weights']=['1/2','1/3','0']
        self.assertRefusal('INVALID_SOURCE_SUPPORT',lambda:build(samples=[bad]))
        bad=sample();bad['source_face_id']='fiction'
        self.assertRefusal('INVALID_SOURCE_SUPPORT',lambda:build(samples=[bad]))
        bad=sample();bad['source_vertex_id']='v0'
        self.assertRefusal('INVALID_SOURCE_SUPPORT',lambda:build(samples=[bad]))

    def test_out_of_source_weights_and_noncanonical_rationals_are_refused(self):
        bad=sample();bad['source_barycentric_weights']=['-1/2','3/2','0']
        self.assertRefusal('INVALID_PARAMETER',lambda:build(samples=[bad]))
        bad=sample();bad['source_barycentric_weights']=['2/4','1/2','0']
        self.assertRefusal('INVALID_NUMBER',lambda:build(samples=[bad]))

    def test_reflections_rotation_scale_and_translation_preserve_binding_rows(self):
        base=build(samples=[sample()])
        source,carrier=rectangle(),rectangle('carrier',True)
        transform=lambda p:[7+3*p[0]-4*p[1],11+4*p[0]+3*p[1]]
        source['uv_cm']=[transform(p) for p in source['uv_cm']]
        carrier['uv_cm']=[transform(p) for p in carrier['uv_cm']]
        changed=build(source,carrier,[sample()])
        self.assertEqual(base['samples'][0]['carrier_support'],changed['samples'][0]['carrier_support'])
        self.assertEqual(sum(F(p['area_cm2']) for p in changed['source_carrier_intersections']),200)
        for mesh in (source,carrier):
            mesh['uv_cm']=[[-p[0],p[1]] for p in mesh['uv_cm']]
        reflected=build(source,carrier,[sample()])
        self.assertEqual(changed['samples'][0]['carrier_support'],reflected['samples'][0]['carrier_support'])

    def test_face_and_vertex_permutations_preserve_explicit_identified_maps(self):
        source,carrier=rectangle(),rectangle('carrier',True)
        initial=build(source,carrier,[sample()])
        def permute(mesh):
            order=[2,0,3,1];inverse={old:new for new,old in enumerate(order)}
            mesh['uv_cm']=[mesh['uv_cm'][i] for i in order]
            mesh['vertex_ids']=[mesh['vertex_ids'][i] for i in order]
            mesh['triangles']=[[inverse[i] for i in f] for f in reversed(mesh['triangles'])]
            mesh['face_ids'].reverse()
        permute(source);permute(carrier)
        changed=build(source,carrier,[sample()])
        self.assertEqual(initial['samples'],changed['samples'])
        self.assertEqual(initial['source_carrier_intersections'],changed['source_carrier_intersections'])

    def test_exact_binary64_coordinates_are_not_decimal_rounded(self):
        source=rectangle();carrier=rectangle('carrier',True)
        for mesh in (source,carrier):
            mesh['uv_cm']=[[p[0]*0.1,p[1]*0.1] for p in mesh['uv_cm']]
        result=build(source,carrier,[sample()])
        point=result['samples'][0]['exact_uv_cm'][0]
        self.assertEqual(F(point),F(0.4)/2)
        self.assertNotEqual(F(point),F('1/5'))
        self.assertEqual(result['source'],source)

    def test_local_relations_use_actual_named_edges_order_and_matching_partitions(self):
        values=[sample('start','0'),sample('end','1')]
        relation=external_relation();relation['owners'][0]['edge_id']='fiction'
        self.assertRefusal('INVALID_BOUNDARY',lambda:build(samples=values,relations=[relation]))
        relation=external_relation();relation['owners'][0]['samples'].reverse()
        self.assertRefusal('INVALID_PARAMETER',lambda:build(samples=values,relations=[relation]))
        relation=external_relation();relation['owners'][1]['samples'].insert(1,{
            'sample_id':'extra','fraction':'1/2','source_segment_vertex_ids':['e0','e1'],'source_segment_parameter':'1/2'})
        self.assertRefusal('INVALID_RELATION',lambda:build(samples=values,relations=[relation]))

    def test_overlapping_permanent_relations_are_refused_and_closure_stays_closure(self):
        values=[sample('start','0'),sample('end','1')]
        self.assertRefusal('AMBIGUOUS_RELATION',lambda:build(samples=values,relations=[external_relation(),external_relation(identity='other')]))
        result=build(samples=values,relations=[external_relation(kind='closure')])
        self.assertEqual(result['relations'][0]['kind'],'closure')
        self.assertFalse(result['receipt']['equality_3d_checked'])

    def test_external_references_need_hash_chain_and_bounded_parameters(self):
        values=[sample('start','0'),sample('end','1')]
        relation=external_relation();relation['owners'][1]['source_sha256']='bad'
        self.assertRefusal('INVALID_EXTERNAL_REFERENCE',lambda:build(samples=values,relations=[relation]))
        relation=external_relation();relation['owners'][1]['samples'][0]['source_segment_parameter']='-1'
        self.assertRefusal('INVALID_PARAMETER',lambda:build(samples=values,relations=[relation]))
        relation=external_relation();relation['owners'][1]['samples'][0]['source_segment_vertex_ids']=['e1','e0']
        self.assertRefusal('INVALID_EXTERNAL_REFERENCE',lambda:build(samples=values,relations=[relation]))

    def test_reverse_external_traversal_and_endpoints_are_explicit(self):
        values=[sample('start','0'),sample('end','1')]
        relation=external_relation();relation['orientation']='reverse'
        for entry in relation['owners'][1]['samples']:
            entry['source_segment_vertex_ids']=['e1','e0']
        result=build(samples=values,relations=[relation])
        self.assertEqual(result['relations'],[relation])
        relation['owners'][1]['samples'][0]['source_segment_parameter']='1/2'
        self.assertRefusal('INVALID_RELATION',lambda:build(samples=values,relations=[relation]))

    def test_input_serialization_and_precision_work_are_bounded(self):
        self.assertRefusal('BUDGET_EXHAUSTED',lambda:build(budgets={'max_input_bytes':100}))
        value=sample();value['source_barycentric_weights']=['1/65536','65535/65536','0']
        self.assertRefusal('BUDGET_EXHAUSTED',lambda:build(samples=[value],budgets={'max_fraction_bits':8}))

    def test_deadline_expired_at_entry_or_during_clipping_never_qualifies(self):
        self.assertRefusal('DEADLINE_EXHAUSTED',lambda:build(deadline=0))
        class Clock:
            def __init__(self):self.calls=0
            def __call__(self):
                self.calls+=1
                return 0. if self.calls<90 else 1.
        self.assertRefusal('DEADLINE_EXHAUSTED',lambda:build(clock=Clock(),deadline=1.))

    def test_deadline_inside_exact_clipping_and_support_is_observed(self):
        for target in ('_clip','_support'):
            def clock():
                frame=inspect.currentframe().f_back
                while frame is not None:
                    if frame.f_code.co_name==target:
                        return 1.
                    frame=frame.f_back
                return 0.
            self.assertRefusal('DEADLINE_EXHAUSTED',lambda:build(clock=clock,deadline=1.))

    def test_deadline_during_sample_mapping_and_before_return_is_refused(self):
        source=rectangle();carrier=rectangle('carrier',True)
        for phase in ('sample','return'):
            calls=[]
            def clock():
                calls.append(0)
                return 0.
            build(source,carrier,[sample()],clock=clock)
            threshold=len(calls)-1 if phase=='return' else len(calls)-12
            count=[0]
            def expires():
                count[0]+=1
                return 0. if count[0]<threshold else 1.
            self.assertRefusal('DEADLINE_EXHAUSTED',lambda:build(source,carrier,[sample()],clock=expires,deadline=1.))

    def test_clock_nonfinite_or_backward_is_refused(self):
        self.assertRefusal('INVALID_CLOCK',lambda:build(clock=lambda:math.nan))
        calls=iter([2.,1.])
        self.assertRefusal('INVALID_CLOCK',lambda:build(clock=lambda:next(calls)))

    def test_inputs_are_preserved_and_result_has_no_mutable_alias(self):
        source,carrier,values=rectangle(),rectangle('carrier',True),[sample()]
        before=digest([source,carrier,values])
        result=build(source,carrier,values)
        self.assertEqual(digest([source,carrier,values]),before)
        result['source']['uv_cm'][0][0]=999
        result['samples'][0]['source_identity']['id']='changed'
        self.assertEqual(digest([source,carrier,values]),before)

    def test_mutated_reference_is_refused(self):
        source=rectangle();calls=[0]
        def clock():
            calls[0]+=1
            if calls[0]==5:source['uv_cm'][0][0]=1
            return 0.
        self.assertRefusal('REFERENCE_MUTATION',lambda:build(source=source,clock=clock))

    def test_budgets_exhaust_before_excessive_work(self):
        self.assertRefusal('BUDGET_EXHAUSTED',lambda:build(budgets={'max_pair_checks':2}))
        self.assertRefusal('BUDGET_EXHAUSTED',lambda:build(budgets={'max_intersection_patches':1}))
        self.assertRefusal('BUDGET_EXHAUSTED',lambda:build(budgets={'max_source_vertices':3}))
        self.assertRefusal('BUDGET_EXHAUSTED',lambda:build(budgets={'max_input_nodes':3}))
        self.assertRefusal('BUDGET_EXHAUSTED',lambda:build(samples=[sample('a'),sample('b')],budgets={'max_samples':1}))

    def test_invalid_budget_number_or_hostile_container_is_refused(self):
        self.assertRefusal('INVALID_BUDGET',lambda:build(budgets={'max_seconds':61}))
        self.assertRefusal('INVALID_BUDGET',lambda:build(budgets={'max_pair_checks':True}))
        self.assertRefusal('INVALID_BUDGET',lambda:build(budgets={'unknown':1}))
        source=rectangle();source['uv_cm'][0][0]=math.inf
        self.assertRefusal('INVALID_REFERENCE',lambda:build(source=source))
        source=rectangle();source['uv_cm'][0][0]=True
        self.assertRefusal('INVALID_NUMBER',lambda:build(source=source))
        class Hostile(dict):pass
        self.assertRefusal('INVALID_REFERENCE',lambda:build(source=Hostile(rectangle())))

    def test_mesh_and_mark_identity_collisions_are_refused(self):
        source=rectangle();source['vertex_ids'][1]='v0'
        self.assertRefusal('IDENTITY_COLLISION',lambda:build(source=source))
        values=[sample('start','0'),sample('end','1'),sample('mid')]
        mark={'id':'m','relation_id':'seam','fraction':'1/2','symbol':'notch','owners':[{'owner_index':0,'sample_id':'mid'}]}
        self.assertRefusal('IDENTITY_COLLISION',lambda:build(samples=values,relations=[external_relation()],marks=[mark,mark]))

    def test_one_mark_cannot_alias_two_samples_on_the_same_owner(self):
        values=[sample('start','0'),sample('end','1'),sample('mid'),sample('other-mid')]
        mark={'id':'m','relation_id':'seam','fraction':'1/2','symbol':'notch',
            'owners':[{'owner_index':0,'sample_id':'mid'},{'owner_index':0,'sample_id':'other-mid'}]}
        self.assertRefusal('INVALID_MARK',lambda:build(samples=values,relations=[external_relation()],marks=[mark]))

    def test_rectangle_grid_is_deterministic_and_exactly_covered(self):
        source=rectangle();before=digest(source)
        a=build_rectangular_material_carrier(source,['v0','v1','v2','v3'],columns=4,rows=2,clock=lambda:0.)
        b=build_rectangular_material_carrier(source,['v0','v1','v2','v3'],columns=4,rows=2,clock=lambda:0.)
        self.assertEqual(a,b)
        self.assertEqual(len(a['carrier']['uv_cm']),15)
        self.assertEqual(len(a['carrier']['triangles']),16)
        self.assertEqual(digest(source),before)
        self.assertEqual(a['qualification'],'NONE')

    def test_rotated_exact_rectangle_is_supported_without_bounding_box_guess(self):
        source=rectangle();source['uv_cm']=[[3*p[0]-4*p[1],4*p[0]+3*p[1]] for p in source['uv_cm']]
        result=build_rectangular_material_carrier(source,['v0','v1','v2','v3'],columns=2,rows=2,clock=lambda:0.)
        self.assertTrue(result['rectangle_parameters']['rectangle_verified_exactly'])
        self.assertEqual(sum(F(p['area_cm2']) for p in result['source_carrier_intersections']),200)

    def test_rectangle_domain_mismatch_and_trapezoid_are_refused(self):
        source=rectangle();source['uv_cm'][2]=[3,2]
        self.assertRefusal('INVALID_RECTANGLE',lambda:build_rectangular_material_carrier(source,['v0','v1','v2','v3'],columns=2,rows=2,clock=lambda:0.))
        source={'id':'not-full-rectangle','uv_cm':[[0,0],[4,0],[4,2],[0,2],[2,1]],
            'vertex_ids':['v0','v1','v2','v3','middle'],'face_ids':['a','b','c'],
            'triangles':[[0,1,4],[1,2,4],[2,3,4]]}
        self.assertRefusal('DOMAIN_COVERAGE',lambda:build_rectangular_material_carrier(source,['v0','v1','v2','v3'],columns=2,rows=2,clock=lambda:0.))

    def test_rectangle_generated_counts_and_shared_deadline_are_bounded(self):
        self.assertRefusal('BUDGET_EXHAUSTED',lambda:build_rectangular_material_carrier(rectangle(),['v0','v1','v2','v3'],columns=1000,rows=1000,clock=lambda:0.))
        self.assertRefusal('DEADLINE_EXHAUSTED',lambda:build_rectangular_material_carrier(rectangle(),['v0','v1','v2','v3'],columns=2,rows=2,deadline=0,clock=lambda:0.))


if __name__=='__main__':
    unittest.main()
