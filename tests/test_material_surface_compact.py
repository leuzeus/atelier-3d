"""Small exact storage fixtures only; no real collar/compiler or native run."""
import ast
import copy
from fractions import Fraction as F
import hashlib
import json
import math
from pathlib import Path
import sys
import unittest
from unittest.mock import patch

from a3d import material_sample_carrier as uv
from a3d import material_surface_field as field
from a3d import material_surface_compact as compact
from a3d.core import StudioError
from tests.test_material_surface_field import (
    square, coordinates, reference, sample, relation, HookClock,
    returned_nodes, returned_bytes,
)


def data_fixture(reverse=False, break_height=2., with_owners=False):
    source=square('material',reverse=reverse)
    carrier=square('carrier',True,reverse)
    data={'source':source,'carrier':carrier,'reference':reference(break_height,reverse),
          'coordinates_cm':coordinates(carrier),'samples':[sample()],
          'marks':[],'relations':[],'targets':[],
          'previous_coordinates_cm':coordinates(carrier),'limits':None}
    if with_owners:
        data['samples'].extend([sample('start','0'),sample('end','1')])
        data['relations']=[relation('closure','zip')]
        data['marks']=[{'id':'first','relation_id':'zip','fraction':'0','symbol':'notch',
                       'owners':[{'owner_index':0,'sample_id':'start'}]}]
        data['targets']=[{'id':'hard-name-only','sample_id':'mid','target_cm':[.5,0.,0.],
                         'role':'physical_stop'}]
    return data


def capture_on_ledger(originals,budget):
    budget.check('fixture_before_capture')
    copied=field._snapshot(originals,budget)
    before=field._hash(copied,budget,'fixture_snapshot')
    if field._hash(originals,budget,'fixture_original')!=before:
        field._refuse('REFERENCE_MUTATION','fixture inputs changed during capture')
    return copied,before


def packed(data=None,provenance=None,budgets=None,clock=lambda:0.,deadline=None):
    data=data_fixture()if data is None else data
    originals=[data,provenance,budgets,deadline]
    captured,before,budget=field._capture(originals,budgets,deadline,clock)
    state=field._compile(captured[0],budget)
    result=compact.pack_material_surface_state(state,originals=originals,before=before,
        budget=budget,input_hashes=field._hashes(state,budget),provenance=captured[1])
    return result,budget,originals,state


def consume(result,budget,budgets=None,expand=False):
    originals=[result,budgets,budget.declared_deadline]
    captured,before=capture_on_ledger(originals,budget)
    fn=compact.expand_material_surface_compact_geometry if expand else compact.validate_material_surface_compact
    return fn(captured[0],originals=originals,before=before,budget=budget)


def rehash_content(result):
    result['receipt']['content_sha256']=uv._digest({k:v for k,v in result.items()if k!='receipt'})


class MaterialSurfaceCompactTests(unittest.TestCase):
    def refusal(self,reason,fn,incomplete=False):
        with self.assertRaises(StudioError)as caught:fn()
        self.assertEqual(caught.exception.reason,reason)
        self.assertEqual(caught.exception.qualification,'NONE')
        self.assertEqual(caught.exception.status,'INCOMPLETE'if incomplete else'REFUSED')

    def assert_sizes(self,result):
        self.assertEqual(result['receipt']['output']['nodes'],returned_nodes(result))
        self.assertEqual(result['receipt']['output']['bytes'],returned_bytes(result))

    def test_full_inputs_fresh_breaks_targets_and_owners_preserved(self):
        data=data_fixture(with_owners=True);before=copy.deepcopy(data)
        out,budget,_,_=packed(data)
        self.assertEqual(out['inputs'],data);self.assertEqual(data,before)
        self.assertEqual(len(out['inputs']['reference']['mesh']['uv_cm']),5)
        self.assertEqual(len(out['inputs']['reference']['mesh']['triangles']),4)
        self.assertEqual(out['inputs']['reference']['coordinates_cm'][-1][2],2.)
        self.assertEqual(out['relations'],data['relations']);self.assertEqual(out['assembly_marks'],data['marks'])
        self.assertEqual(out['target_observations'][0]['role'],'physical_stop')
        self.assertEqual(out['external_source_references'][0]['geometry_checked'],False)
        self.assertEqual(out['physical_pins_added'],[]);self.assert_sizes(out)

    def test_explicit_parents_reconstruct_face_ids_vertices_weights_and_area_exactly(self):
        out,budget,_,state=packed();geometry=out['geometry']
        expanded=consume(out,budget,expand=True)
        old=field._base(state)
        for key in ('source_carrier_intersections','reference_carrier_intersections',
                    'material_reference_carrier_patches'):
            expected=field._encode(old[key],field._Budget(None,None,lambda:0.))
            self.assertEqual(expanded[key],expected)
        for row,verbose in zip(geometry['source_reference_carrier'],expanded['material_reference_carrier_patches']):
            sp,rp=geometry['source_carrier'][row[0]],geometry['reference_carrier'][row[1]]
            self.assertEqual(sp[0],verbose['source_face_id']);self.assertEqual(rp[0],verbose['reference_face_id'])
            self.assertEqual(sp[1],rp[1]);self.assertEqual(sp[1],verbose['carrier_face_id'])
            self.assertEqual(row[2],verbose['uv_polygon_cm']);self.assertEqual(row[3],verbose['area_cm2'])
            for key in ('source_barycentric_weights','reference_barycentric_weights','carrier_barycentric_weights'):
                self.assertTrue(all(sum(map(F,weights))==1 for weights in verbose[key]))
        self.assertEqual(expanded['v1_consumer_compatible'],False)
        self.assertNotEqual(expanded['discriminant'],field.DISCRIMINANT);self.assert_sizes(expanded)

    def test_compact_geometry_node_count_reduces_storage_only(self):
        out,_,_,state=packed()
        old=field._encode(field._base(state),field._Budget(None,None,lambda:0.))
        legacy=sum(returned_nodes(old[k])for k in ('source_carrier_intersections',
            'reference_carrier_intersections','material_reference_carrier_patches'))
        self.assertLess(returned_nodes(out['geometry']),legacy)
        self.assertEqual(out['discriminant'],compact.DISCRIMINANT)
        self.assertEqual(out['qualification'],'NONE');self.assertFalse(out['is_installable'])
        self.assertEqual(out['fitting'],'NOT_QUALIFIED');self.assertEqual(out['contacts'],'NOT_ASSESSED')

    def test_near_half_samples_and_same_uv_distinct_ids_are_not_merged(self):
        data=data_fixture();near=F(math.nextafter(.5,0.))
        data['samples'].extend([sample('near',str(near)),sample('same-uv-another-id')])
        out,budget,_,_=packed(data);consume(out,budget)
        records={r['id']:r for r in out['samples']}
        self.assertNotEqual(records['mid']['exact_uv_cm'],records['near']['exact_uv_cm'])
        self.assertEqual(records['mid']['exact_uv_cm'],records['same-uv-another-id']['exact_uv_cm'])
        self.assertEqual(len(records),3);self.assertFalse(out['receipt']['identities_merged'])

    def test_opaque_registry_is_captured_verbatim_and_never_applied_or_admitted(self):
        provenance={'body_sha256':'a'*64,'recipe_id':'fixture','registry':[
            {'id':'declared-hard','strength':'HARD','sample_id':'mid'},
            {'id':'declared-soft','strength':'SOFT','sample_id':'mid'}]}
        before=copy.deepcopy(provenance);out,budget,_,_=packed(provenance=provenance)
        checked=consume(out,budget)
        self.assertEqual(out['provenance'],before);self.assertEqual(checked['provenance'],before)
        self.assertEqual(out['provenance_scope'],'NON_ADMITTED_NOT_APPLIED_TO_COMPUTATION')
        self.assertEqual(out['physical_pins_added'],[]);self.assertEqual(out['target_observations'],[])
        self.assertFalse(out['receipt']['constraints_3d_qualified'])
        self.assertEqual(out['receipt']['input_hashes']['provenance'],uv._digest(before))

    def test_absent_provenance_remains_none(self):
        out,_,_,_=packed();self.assertIsNone(out['provenance'])

    def test_provenance_not_in_original_capture_refuses(self):
        data=data_fixture();originals=[data,None,None,None]
        copied,before,budget=field._capture(originals,None,None,lambda:0.)
        state=field._compile(copied[0],budget)
        self.refusal('INVALID_CAPTURE',lambda:compact.pack_material_surface_state(state,
            originals=originals,before=before,budget=budget,provenance={'unscoped':True}))

    def test_compact_code_has_own_identity_not_v1_compiler_identity(self):
        out,_,_,_=packed();receipt=out['receipt']
        actual=hashlib.sha256(Path(compact.__file__).read_bytes()).hexdigest()
        self.assertEqual(receipt['input_hashes']['compact_code'],actual)
        self.assertEqual(receipt['code_sha256']['compact'],actual)
        self.assertNotEqual(actual,receipt['input_hashes']['compiler_code'])

    def test_validation_recompiles_and_two_outputs_have_cumulative_cost_without_refund(self):
        out,budget,_,_=packed();first=copy.deepcopy(budget.counts)
        checked=consume(out,budget);self.assert_sizes(out);self.assert_sizes(checked)
        self.assertEqual(checked['receipt']['work']['output_nodes'],
                         out['receipt']['output']['nodes']+checked['receipt']['output']['nodes'])
        self.assertEqual(checked['receipt']['work']['output_bytes'],
                         out['receipt']['output']['bytes']+checked['receipt']['output']['bytes'])
        self.assertGreater(budget.counts['pair_checks'],first['pair_checks'])
        self.assertGreater(budget.counts['fraction_operations'],first['fraction_operations'])
        self.assertGreater(budget.counts['input_nodes'],first['input_nodes'])
        self.assertEqual(checked['status'],'VALIDATED_STORAGE_TEST_ONLY')
        self.assertEqual(checked['receipt']['work'],budget.counts)

    def test_second_output_node_cap_exhaustion_keeps_prior_cost_and_inputs(self):
        out,budget,_,_=packed();checked=consume(out,budget)
        cap=budget.counts['output_nodes']-1;budgets={'max_output_nodes':cap}
        out,budget,_,_=packed(budgets=budgets);before=copy.deepcopy(out);used=dict(budget.counts)
        self.refusal('BUDGET_EXHAUSTED',lambda:consume(out,budget,budgets),True)
        self.assertEqual(out,before);self.assertEqual(budget.counts['output_nodes'],cap)
        self.assertEqual(budget.counts['output_bytes'],used['output_bytes'])
        self.assertGreater(budget.counts['pair_checks'],used['pair_checks'])

    def test_second_output_byte_cap_exact_and_minus_one(self):
        cap=field._HARD['max_output_bytes']
        for _ in range(5):
            budgets={'max_output_bytes':cap};out,budget,_,_=packed(budgets=budgets)
            checked=consume(out,budget,budgets);measured=budget.counts['output_bytes']
            if measured==cap:break
            cap=measured
        self.assertEqual(measured,cap);self.assert_sizes(checked)
        budgets={'max_output_bytes':cap-1};out,budget,_,_=packed(budgets=budgets)
        before=copy.deepcopy(out);used=dict(budget.counts)
        self.refusal('BUDGET_EXHAUSTED',lambda:consume(out,budget,budgets),True)
        self.assertEqual(out,before);self.assertEqual(budget.counts['output_bytes'],used['output_bytes'])
        self.assertGreater(budget.counts['output_nodes'],used['output_nodes'])

    def test_first_output_nodes_exact_and_minus_one(self):
        out,_,_,_=packed();nodes=returned_nodes(out)
        exact,_,_,_=packed(budgets={'max_output_nodes':nodes});self.assert_sizes(exact)
        self.refusal('BUDGET_EXHAUSTED',lambda:packed(budgets={'max_output_nodes':nodes-1}),True)

    def test_first_output_utf8_bytes_exact_and_minus_one(self):
        provenance={'message':'épaule 🧵 « exacte »','escaped':'"\\\n'}
        cap=field._HARD['max_output_bytes']
        for _ in range(5):
            out,_,_,_=packed(provenance=provenance,budgets={'max_output_bytes':cap})
            measured=returned_bytes(out)
            if measured==cap:break
            cap=measured
        self.assertEqual(measured,cap);self.assert_sizes(out)
        self.refusal('BUDGET_EXHAUSTED',lambda:packed(provenance=provenance,
            budgets={'max_output_bytes':cap-1}),True)

    def test_pair_cap_consumed_before_validation_is_not_reset(self):
        out,budget,_,_=packed();first=budget.counts['pair_checks'];consume(out,budget)
        total=budget.counts['pair_checks'];self.assertGreater(total,first)
        budgets={'max_pair_checks':total-1};out,budget,_,_=packed(budgets=budgets)
        before=copy.deepcopy(out)
        self.refusal('BUDGET_EXHAUSTED',lambda:consume(out,budget,budgets),True)
        self.assertEqual(out,before);self.assertGreaterEqual(budget.counts['pair_checks'],first)

    def test_fraction_cap_consumed_before_validation_is_not_reset(self):
        out,budget,_,_=packed();first=budget.counts['fraction_operations'];consume(out,budget)
        total=budget.counts['fraction_operations'];budgets={'max_fraction_operations':total-1}
        out,budget,_,_=packed(budgets=budgets);before=copy.deepcopy(out)
        self.refusal('BUDGET_EXHAUSTED',lambda:consume(out,budget,budgets),True)
        self.assertEqual(out,before);self.assertGreater(budget.counts['fraction_operations'],first)

    def test_no_cap_raise_fake_budget_or_hidden_clock(self):
        self.refusal('INVALID_BUDGET',lambda:packed(budgets={'max_output_nodes':500001}))
        self.refusal('INVALID_BUDGET',lambda:compact.pack_material_surface_state({},
            originals=[],before='0'*64,budget=object()))
        tree=ast.parse(Path(compact.__file__).read_text(encoding='utf-8'))
        imports=[a.name for n in ast.walk(tree)if isinstance(n,ast.Import)for a in n.names]
        self.assertFalse(any(x.startswith(('time','bpy','mathutils','sqlite3','importlib'))for x in imports))
        self.assertFalse(any(isinstance(n,ast.ClassDef)for n in tree.body))

    def test_closed_geometry_parent_indices_polygon_area_and_extra_fields_refuse(self):
        for change in ('missing','parent','bool_parent','area','uv','extra','row_extra'):
            out,budget,_,_=packed();row=out['geometry']['source_reference_carrier'][0]
            if change=='missing':out['geometry']['source_reference_carrier'].pop()
            elif change=='parent':row[0]=999
            elif change=='bool_parent':row[0]=False
            elif change=='area':row[3]='1/7'
            elif change=='uv':row[2][0][0]=str(F(math.nextafter(.5,0.)))
            elif change=='extra':out['geometry']['unapproved_weights']=[]
            else:row.append({'source_barycentric_weights':['1','0','0']})
            rehash_content(out)
            with self.subTest(change=change):self.refusal('COMPACT_GEOMETRY_MISMATCH',lambda:consume(out,budget))

    def test_noncanonical_rational_strings_never_alias_canonical_values(self):
        for token in ('2/4','-0','0/1',.5):
            out,budget,_,_=packed();out['geometry']['source_reference_carrier'][0][3]=token
            rehash_content(out)
            with self.subTest(token=token):self.refusal('COMPACT_GEOMETRY_MISMATCH',lambda:consume(out,budget))

    def test_flags_pins_and_missing_full_reference_cannot_qualify(self):
        for change in ('flag','pin','mesh','unknown'):
            out,budget,_,_=packed()
            if change=='flag':out['qualification']='PASS'
            elif change=='pin':out['physical_pins_added']=['mid']
            elif change=='mesh':out['inputs']['reference']['mesh']['triangles'].pop()
            else:out['new_gate']='READY'
            rehash_content(out)
            with self.subTest(change=change),self.assertRaises(StudioError):consume(out,budget)

    def test_mutated_input_or_provenance_with_rehashed_payload_invalidates_identity(self):
        for change in ('current','previous','limits','provenance'):
            out,budget,_,_=packed(provenance={'pose':'source-pose'})
            if change=='current':out['inputs']['coordinates_cm'][0][2]=.1
            elif change=='previous':out['inputs']['previous_coordinates_cm'][0][2]=.1
            elif change=='limits':out['inputs']['limits']={'max_displacement_cm':7.}
            else:out['provenance']['pose']='another-pose'
            rehash_content(out)
            with self.subTest(change=change),self.assertRaises(StudioError)as caught:consume(out,budget)
            self.assertIn(caught.exception.reason,('REFERENCE_MUTATION','COMPACT_GEOMETRY_MISMATCH'))

    def test_code_content_output_size_and_receipt_claim_mutations_refuse(self):
        for change in ('code','content','nodes','bytes','work','claim'):
            out,budget,_,_=packed();receipt=out['receipt']
            if change=='code':receipt['input_hashes']['compact_code']='0'*64
            elif change=='content':receipt['content_sha256']='0'*64
            elif change=='nodes':receipt['output']['nodes']-=1
            elif change=='bytes':receipt['output']['bytes']-=1
            elif change=='work':receipt['work']['output_bytes']=0
            else:receipt['constraints_3d_qualified']=True
            with self.subTest(change=change),self.assertRaises(StudioError):consume(out,budget)

    def test_v1_consumers_and_validator_reject_the_other_discriminant(self):
        out,_,_,_=packed()
        with self.assertRaises(StudioError):field.observe_material_surface_field(out,clock=lambda:0.)
        old=field.compile_material_surface_field(square(),square('carrier',True),reference(),
            coordinates(square('carrier',True)),clock=lambda:0.)
        budget=field._Budget(None,None,lambda:0.)
        self.refusal('INVALID_CONTRACT',lambda:consume(old,budget))

    def test_two_consistent_windings_preserve_positive_exact_coverage(self):
        for reverse in (False,True):
            out,budget,_,_=packed(data_fixture(reverse));consume(out,budget)
            area=sum(F(r[3])for r in out['geometry']['source_reference_carrier'])
            self.assertEqual(area,1)

    def test_deadline_at_capture_serialization_last_hash_boundary_and_return_refuses(self):
        for phase in ('before_budget_capture','compact_before_input_access',
                      'compact_binary_parent','compact_complete_serialization',
                      'compact_output_after_preservation','compact_output_terminal_deadline'):
            clock=HookClock(phase=phase)
            with self.subTest(phase=phase):self.refusal('DEADLINE_EXHAUSTED',lambda:packed(clock=clock),True)

    def test_second_output_expiry_preserves_first_output_and_consumed_work(self):
        clock=HookClock();out,budget,_,_=packed(clock=clock);before=copy.deepcopy(out)
        prior=dict(budget.counts);clock.phase='compact_output_terminal_deadline'
        self.refusal('DEADLINE_EXHAUSTED',lambda:consume(out,budget),True)
        self.assertEqual(out,before);self.assertGreater(budget.counts['output_nodes'],prior['output_nodes'])
        self.assertGreater(budget.counts['output_bytes'],prior['output_bytes'])
        self.assertEqual(budget.start,0.);self.assertEqual(budget.deadline,60.)

    def test_mutation_during_output_preservation_is_detected(self):
        data=data_fixture();clock=HookClock(phase='compact_output_return',
            action=lambda:data['samples'][0].update(id='mutated'))
        self.refusal('REFERENCE_MUTATION',lambda:packed(data,clock=clock))

    def test_complete_outputs_have_no_alias_to_original_data_or_provenance(self):
        data=data_fixture();provenance={'opaque':['retained']};original=copy.deepcopy([data,provenance])
        out,_,_,_=packed(data,provenance);out['inputs']['source']['uv_cm'][0][0]=100
        out['provenance']['opaque'][0]='changed';out['geometry']['source_carrier'][0][2][0][0]='100'
        self.assertEqual([data,provenance],original)

    def test_expiry_during_last_preservation_hash_refuses_all_three_interfaces(self):
        for operation in ('pack','validate','expand'):
            value=[0.];clock=lambda:value[0];data=data_fixture();before_data=copy.deepcopy(data)
            original=compact._preservation_digest;calls=[0]
            if operation!='pack':out,budget,_,_=packed(data,clock=clock);before_out=copy.deepcopy(out)
            def slow_last_hash(reference):
                result=original(reference);calls[0]+=1
                if calls[0]==2:value[0]=60.
                return result
            with self.subTest(operation=operation),patch.object(compact,'_preservation_digest',slow_last_hash):
                self.refusal('DEADLINE_EXHAUSTED',lambda:(packed(data,clock=clock)if operation=='pack'
                    else consume(out,budget,expand=operation=='expand')),True)
            self.assertEqual(calls[0],2);self.assertEqual(data,before_data)
            if operation!='pack':self.assertEqual(out,before_out)

    def test_expiry_during_final_code_hash_keeps_charged_complete_output(self):
        value=[0.];calls=[0]
        def clock():
            frame=sys._getframe(1)
            if frame.f_code.co_name=='now':frame=frame.f_back
            if frame and frame.f_code.co_name=='check'and frame.f_locals.get('phase')=='compact_code_after_hash':
                calls[0]+=1
                if calls[0]==4:value[0]=60.
            return value[0]
        data=data_fixture();originals=[data,None,None,None]
        copied,before,budget=field._capture(originals,None,None,clock)
        state=field._compile(copied[0],budget);before_data=copy.deepcopy(data)
        self.refusal('DEADLINE_EXHAUSTED',lambda:compact.pack_material_surface_state(state,
            originals=originals,before=before,budget=budget),True)
        self.assertGreater(budget.counts['output_nodes'],0);self.assertGreater(budget.counts['output_bytes'],0)
        self.assertEqual(data,before_data)

    def test_invalid_capture_identity_or_declared_caps_refuses(self):
        data=data_fixture();originals=[data,None,None,None]
        copied,before,budget=field._capture(originals,None,None,lambda:0.)
        state=field._compile(copied[0],budget)
        self.refusal('REFERENCE_MUTATION',lambda:compact.pack_material_surface_state(state,
            originals=originals,before='0'*64,budget=budget))
        budget.limits['max_output_nodes']=500001
        self.refusal('INVALID_BUDGET',lambda:compact.pack_material_surface_state(state,
            originals=originals,before=before,budget=budget))

    def test_expansion_is_another_charged_output_and_can_exhaust_caps(self):
        out,budget,_,_=packed();first=dict(budget.counts);expanded=consume(out,budget,expand=True)
        self.assert_sizes(expanded)
        self.assertEqual(budget.counts['output_nodes'],first['output_nodes']+returned_nodes(expanded))
        self.assertEqual(budget.counts['output_bytes'],first['output_bytes']+returned_bytes(expanded))
        cap=budget.counts['output_nodes']-1;budgets={'max_output_nodes':cap}
        out,budget,_,_=packed(budgets=budgets)
        self.refusal('BUDGET_EXHAUSTED',lambda:consume(out,budget,budgets,expand=True),True)


if __name__=='__main__':unittest.main()
