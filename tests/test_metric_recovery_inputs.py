"""Portable compiler/adapter contracts; no real garment or contacts admitted."""
import copy
import unittest
from unittest.mock import patch

from a3d.core import StudioError,contract,digest
from a3d.textile_executor import _source_metric_recovery
from blender.placement_correction import correct_preparation
from tests.test_guide_metric_solver import seamed_fixture
from tests.test_placement_solver import fixture as placement_fixture


def compiler_fixture():
    pieces={pid:{'edges':{'left':[0,3],'right':[1,2]}}for pid in ('a','b','c')}
    ab={'id':'ab','kind':'permanent','piece_a':'a','piece_b':'b','edge_a':'right','edge_b':'left','orientation':'forward'}
    bc={**ab,'id':'bc','piece_a':'b','piece_b':'c'}
    data={'component_id':'source.coat','pieces':pieces,'seams':[ab,bc]}
    panels={pid:{'source_ref':'fixture:'+pid,'origin_cm':[0.,0.,0.],
        'u_axis':[1.,0.,0.],'v_axis':[0.,1.,0.]}for pid in pieces}
    guide={'panels':panels,'source_seam_coupling':{
        'method':'SOURCE_PERMANENT_NORMALIZED_PARTITION_UNION_CAGE',
        'component_id':data['component_id'],'source_sha256':digest(data),
        'refinements':{'a':{},'b':{}},'cage_sha256':digest({pid:panels[pid]for pid in ('a','b')}),
        'relations':[{'source_seam_id':'ab','source_relation':copy.deepcopy(ab)}]}}
    semantics={'a':{'role':'front','guide_edges':{'shoulder':'left'}},
        'b':{'role':'inner_front','guide_edges':{'anchor':'left','anchor_end':'right'}},
        'c':{'role':'sleeve'}}
    preform={'panels':{'a':{'native_float32_guard_cm':.0002},'b':{'native_float32_guard_cm':.0003},
                       'c':{'native_float32_guard_cm':.001}}}
    budgets={'max_iterations':300,'max_seconds':100.,'max_displacement_cm':8.}
    return data,semantics,guide,preform,budgets


def preparation(recovery,spec):
    return {'version':1,'component_id':'coupon','source_ref':'fixture:source',
        'regular_mesh':{'spacing_cm':1.,'min_spacing_cm':.2,'refinement_distance_cm':1.,
                        'max_vertices':100,'target_min_angle_degrees':15.},
        'placement_correction':spec,'metric_recovery':recovery}


class MetricRecoveryInputs(unittest.TestCase):
    def test_explicit_cohort_covers_specialised_piece_and_only_internal_source_seams(self):
        inputs=compiler_fixture();before=digest(inputs)
        result=_source_metric_recovery(*inputs)
        self.assertEqual(result['piece_ids'],['a','b'])
        self.assertEqual(result['seam_ids'],['ab'])
        self.assertEqual(result['protected_edges'],[{'piece':'a','edge':'left'}])
        self.assertEqual(result['anchor_scope'],'permanent_component')
        self.assertEqual(result['max_initial_seam_gap_cm'],.0006)
        self.assertEqual(result['budgets']['max_displacement_cm'],8.)
        self.assertEqual(digest(inputs),before)
        _,_,spec,_=placement_fixture()
        contract('pattern-preparation',preparation(result,spec))

    def test_legacy_uncoupled_guide_keeps_only_declared_torso_stops(self):
        inputs=compiler_fixture();inputs[2].pop('source_seam_coupling')
        result=_source_metric_recovery(*inputs)
        self.assertEqual(result['piece_ids'],['a'])
        self.assertNotIn('seam_ids',result)
        self.assertNotIn('max_initial_seam_gap_cm',result)
        self.assertNotIn('anchor_scope',result)

    def test_changed_source_cage_relation_or_coverage_cannot_declare_recovery(self):
        variants=[]
        for mutate in (
            lambda x:x[2]['source_seam_coupling'].update(source_sha256='0'*64),
            lambda x:x[2]['panels']['b'].update(origin_cm=[1.,0.,0.]),
            lambda x:x[2]['source_seam_coupling']['relations'].clear(),
            lambda x:x[2]['source_seam_coupling']['relations'][0]['source_relation'].update(orientation='reverse'),
            lambda x:x[2]['source_seam_coupling']['relations'].append(copy.deepcopy(x[2]['source_seam_coupling']['relations'][0])),
            lambda x:x[2]['source_seam_coupling']['refinements'].update(missing={}),
            lambda x:x[1]['b']['guide_edges'].update(anchor='invented'),
            lambda x:x[3]['panels']['b'].update(native_float32_guard_cm=float('nan')),
        ):
            inputs=compiler_fixture();mutate(inputs);variants.append(inputs)
        for inputs in variants:
            with self.subTest(variant=len(str(inputs))):
                with self.assertRaises(StudioError):_source_metric_recovery(*inputs)

    def test_contract_requires_seam_ids_and_explicit_alignment_bound_together(self):
        recovery=_source_metric_recovery(*compiler_fixture());_,_,spec,_=placement_fixture()
        for field in ('seam_ids','max_initial_seam_gap_cm'):
            changed=copy.deepcopy(recovery);changed.pop(field)
            with self.assertRaises(StudioError):contract('pattern-preparation',preparation(changed,spec))
        for value in (float('nan'),True,-.01,2.01):
            changed=copy.deepcopy(recovery);changed['max_initial_seam_gap_cm']=value
            with self.assertRaises(StudioError):contract('pattern-preparation',preparation(changed,spec))

    def test_component_scope_without_seams_or_torso_numerical_anchor_is_refused(self):
        recovery=_source_metric_recovery(*compiler_fixture());_,_,spec,_=placement_fixture()
        recovery.pop('seam_ids');recovery.pop('max_initial_seam_gap_cm')
        with self.assertRaises(StudioError):contract('pattern-preparation',preparation(recovery,spec))
        inputs=compiler_fixture()
        inputs[1]['a']={'role':'collar','guide_edges':{'anchor':'left'}}
        with self.assertRaisesRegex(StudioError,'no specialised pin is inferred'):_source_metric_recovery(*inputs)

    def test_native_adapter_transports_declared_seams_to_real_portable_solver(self):
        payload,points,quality,edges=seamed_fixture()
        payload.update(placed_cm=points,component_id='coupon',package_sha256='a'*64)
        _,_,spec,_=placement_fixture();spec['quality']=copy.deepcopy(quality)
        recovery={'version':1,'piece_ids':['a','b'],'protected_edges':edges[:1],'strain_weight':100.,
            'seam_ids':['ab'],'max_initial_seam_gap_cm':0.,
            'anchor_scope':'permanent_component',
            'budgets':{'max_iterations':30,'max_seconds':10.,'max_displacement_cm':2.,'max_step_cm':.5,
                      'cg_iterations':80,'cg_tolerance':1e-5,'stagnation_iterations':3}}
        policy=preparation(recovery,spec)
        plan={'quality':quality,'assembly':{'max_displacement_cm':2.,'max_step_cm':.2,'iterations':10},
              'collision':{'clearance_cm':.1},'consolidation':{'weld_gap_cm':.05}}
        before=digest([payload,plan,policy])
        def measured(source,coordinates,*args):
            return {'candidate_sha256':digest(coordinates),'hard_valid':True,'score':0.,'contacts':[]}
        with patch('blender.cloth_contacts.build_contact_context',return_value={'bodies':[]}),\
                patch('blender.placement_correction.native_measurement',side_effect=measured):
            result=correct_preparation(payload,{'mesh':quality},plan,policy,[])
        self.assertEqual(result['metric_recovery']['seam_coupling']['seam_ids'],['ab'])
        self.assertEqual(result['metric_recovery']['seam_coupling']['final_max_cohort_gap_cm'],0.)
        for a,b in payload['seams']['ab']['pairs']:
            self.assertEqual(result['coordinates_cm'][a],result['coordinates_cm'][b])
        self.assertEqual(result['qualification'],'NONE')
        self.assertEqual(digest([payload,plan,policy]),before)
