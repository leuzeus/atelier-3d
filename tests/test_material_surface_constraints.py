import copy
import json
import unittest
from fractions import Fraction as F

from a3d.core import StudioError,digest
from a3d.material_surface_field import compile_material_surface_field
from a3d.material_surface_constraints import DISCRIMINANT,compile_material_surface_constraints
from tests.test_material_surface_field import square,coordinates,reference,HookClock,returned_nodes,returned_bytes


def fixture(orientation='forward',kind='permanent',right_fresh_z=0.,extra_kinds=False):
    sources={d:square(d)for d in['left','right']}
    samples=[{'id':'p0','source_face_id':'f0','source_barycentric_weights':['1','0','0']},
             {'id':'p1','source_face_id':'f0','source_barycentric_weights':['0','1','0']},
             {'id':'p2','source_face_id':'f0','source_barycentric_weights':['0','0','1']},
             {'id':'p3','source_face_id':'f1','source_barycentric_weights':['0','0','1']},
             {'id':'third','source_face_id':'f0','source_barycentric_weights':['2/3','1/3','0']},
             {'id':'near','source_face_id':'f0','source_barycentric_weights':[str(1-F(.49999975746439695)),str(F(.49999975746439695)),'0']},
             {'id':'half','source_face_id':'f0','source_barycentric_weights':['1/2','1/2','0']}]
    right_ids=['p1','p0']if orientation=='reverse'else['p0','p1']
    kinds=[('join',kind)]+([('close','closure'),('release','detachable')]if extra_kinds else[])
    global_relations=[]
    for name,k in kinds:
        global_relations.append({'id':name,'kind':k,'orientation':orientation,'owners':[
            {'domain_id':'left','edge_id':'bottom','source_sha256':digest(sources['left']),
             'samples':[{'sample_id':sid,'fraction':str(i)}for i,sid in enumerate(['p0','p1'])]},
            {'domain_id':'right','edge_id':'bottom','source_sha256':digest(sources['right']),
             'samples':[{'sample_id':sid,'fraction':str(i)}for i,sid in enumerate(right_ids)]}]})
    fields={}
    for domain,source in sources.items():
        local=[]
        for relation in global_relations:
            owners=[]
            for side,owner in enumerate(relation['owners']):
                declared={'source_id':owner['domain_id'],'edge_id':owner['edge_id'],'samples':copy.deepcopy(owner['samples'])}
                if owner['domain_id']!=domain:
                    declared['source_sha256']=owner['source_sha256'];declared['source_vertex_ids']=['v0','v1']
                    segment=['v1','v0']if side==1 and orientation=='reverse'else['v0','v1']
                    for i,entry in enumerate(declared['samples']):
                        entry['source_segment_vertex_ids']=segment;entry['source_segment_parameter']=str(i)
                owners.append(declared)
            local.append({'id':relation['id'],'kind':relation['kind'],'orientation':orientation,'owners':owners})
        fresh=reference()
        if domain=='right':
            for row in fresh['coordinates_cm']:row[2]=right_fresh_z
        fields[domain]=compile_material_surface_field(source,square('carrier-'+domain,True),fresh,
            coordinates(square()),samples=copy.deepcopy(samples),relations=local,clock=lambda:0.)
    return fields,global_relations


def stops_eight():
    return [{'id':d+'-original-'+str(i),'domain_id':d,'sample_id':'p'+str(i)}for d in['left','right']for i in range(4)]


def compile_constraints(fields=None,relations=None,physical_stops=None,numerical_targets=None,**kwargs):
    if fields is None:fields,default_relations=fixture();relations=default_relations if relations is None else relations
    return compile_material_surface_constraints(fields,[]if relations is None else relations,
        []if physical_stops is None else physical_stops,[]if numerical_targets is None else numerical_targets,
        clock=kwargs.pop('clock',lambda:0.),**kwargs)


class MaterialSurfaceConstraintsTests(unittest.TestCase):
    def refusal(self,reason,call,incomplete=False):
        with self.assertRaises(StudioError)as caught:call()
        self.assertEqual(caught.exception.reason,reason)
        self.assertEqual(caught.exception.status,'INCOMPLETE'if incomplete else'REFUSED')
        self.assertEqual(caught.exception.qualification,'NONE')

    def verify_certificate(self,result):
        columns=[(c['domain_id'],c['node_id'])for c in result['unknown_nodes']]
        lookup={key:i for i,key in enumerate(columns)};original={}
        for row in result['hard_rows']:
            vector=[F(0)]*len(columns)
            for c in row['coefficients']:vector[lookup[(c['domain_id'],c['node_id'])]]=F(c['weight'])
            original[tuple(row['row_id'])]=vector+list(map(F,row['rhs_exact_cm']))
        cert=result['certificate']
        for combination,claimed in zip(cert['row_combinations'],cert['rref_augmented_rows']):
            independently=[sum(F(term['coefficient'])*original[tuple(term['row_id'])][i]for term in combination)for i in range(len(columns)+3)]
            self.assertEqual(independently,list(map(F,claimed)))
        for proof in cert['contradictions']:
            independently=[sum(F(term['coefficient'])*original[tuple(term['row_id'])][i]for term in proof['original_row_combination'])for i in range(len(columns)+3)]
            self.assertEqual(independently[:len(columns)],[0]*len(columns))
            self.assertEqual(independently[len(columns):],list(map(F,proof['nonzero_rhs_exact_cm'])))
            self.assertTrue(any(independently[len(columns):]))

    def test_two_domains_exact_permanent_rows_and_rank_certificate(self):
        r=compile_constraints();self.assertEqual(r['discriminant'],DISCRIMINANT)
        self.assertEqual(len(r['hard_rows']),2);self.assertEqual(r['certificate']['rank_A'],2)
        self.assertEqual(r['certificate']['rank_augmented'],2)
        self.assertEqual(r['certificate']['status'],'COMPATIBLE_EXACT_LINEAR_MODEL')
        self.assertTrue(r['certificate']['provided_field_satisfies_hard']);self.verify_certificate(r)

    def test_reverse_orientation_uses_actual_right_sample_identity(self):
        fields,relations=fixture('reverse');r=compile_constraints(fields,relations)
        row=r['hard_rows'][0]
        self.assertEqual([b['sample_id']for b in row['sample_bindings']],['p0','p1'])
        self.assertEqual(row['coefficients'],[
            {'domain_id':'left','node_id':'v0','weight':'1'},
            {'domain_id':'right','node_id':'v1','weight':'-1'}])
        self.assertFalse(r['certificate']['provided_field_satisfies_hard'])
        self.assertEqual(r['certificate']['status'],'COMPATIBLE_EXACT_LINEAR_MODEL')

    def test_eight_distinct_original_stops_no_pin_with_redundant_seam_rows(self):
        r=compile_constraints(physical_stops=stops_eight())
        self.assertEqual(len(r['hard_rows']),10);self.assertEqual(r['certificate']['rank_A'],8)
        self.assertEqual(r['certificate']['rank_augmented'],8)
        self.assertEqual(r['physical_pins_added'],[])
        physical=[row for row in r['hard_rows']if row['role']=='physical_stop']
        self.assertEqual(len({tuple(row['row_id'])for row in physical}),8)
        self.assertTrue(all(row['rhs_origin']=='COMPLETE_FRESH_FIELD_AT_EXACT_MATERIAL_SUPPORT'for row in physical))
        self.verify_certificate(r)

    def test_hard_conflict_localized_without_pattern_impossibility(self):
        fields,relations=fixture(right_fresh_z=1.)
        r=compile_constraints(fields,relations,physical_stops=stops_eight())
        c=r['certificate'];self.assertEqual(c['status'],'INCOMPATIBLE_EXPLICIT_HARD_ROWS')
        self.assertEqual(c['rank_A'],8);self.assertEqual(c['rank_augmented'],9)
        self.assertTrue(c['contradictions']);self.assertFalse(c['pattern_impossibility'])
        self.verify_certificate(r)

    def test_matrices_and_certificate_identical_after_reorder(self):
        fields,relations=fixture(extra_kinds=True)
        targets=[{'id':'soft-b','domain_id':'right','sample_id':'third','target_cm':[1/3,0,0]},
                 {'id':'soft-a','domain_id':'left','sample_id':'half','target_cm':[.5,0,1]}]
        a=compile_constraints(fields,relations,stops_eight(),targets)
        b=compile_constraints(dict(reversed(list(fields.items()))),list(reversed(relations)),list(reversed(stops_eight())),list(reversed(targets)))
        for key in['hard_rows','numerical_target_observations','unknown_nodes','hard_system_sha256','certificate','relations']:
            self.assertEqual(a[key],b[key])

    def test_nonbinary_numerical_target_stays_soft_and_never_changes_rank(self):
        fields,relations=fixture();base=compile_constraints(fields,relations)
        r=compile_constraints(fields,relations,numerical_targets=[
            {'id':'third-ieee','domain_id':'left','sample_id':'third','target_cm':[1/3,0,0]},
            {'id':'large-soft-defect','domain_id':'right','sample_id':'half','target_cm':[100.,0,0]}])
        self.assertEqual(r['hard_system_sha256'],base['hard_system_sha256'])
        self.assertEqual(r['certificate'],base['certificate'])
        soft=r['numerical_target_observations'][0]
        self.assertEqual(soft['strength'],'SOFT_OBSERVATION')
        third=next(row for row in r['numerical_target_observations']if row['row_id']==['target','third-ieee'])
        self.assertEqual(F(third['provided_field_residual_exact_cm'][0]),F(1,3)-F(1/3))
        self.assertFalse(r['certificate']['numerical_targets_in_elimination'])

    def test_closure_and_detachable_are_preserved_without_hard_rows(self):
        for kind in['closure','detachable']:
            fields,relations=fixture(kind=kind);r=compile_constraints(fields,relations)
            self.assertEqual(r['hard_rows'],[]);self.assertEqual(r['relations'][0]['relation']['kind'],kind)
            self.assertEqual(r['relations'][0]['hard_rows_created'],0)
            self.assertEqual(r['certificate']['rank_A'],0)

    def test_closure_promotion_or_wrong_orientation_refused(self):
        fields,relations=fixture(kind='closure');relations[0]['kind']='permanent'
        self.refusal('RELATION_PROVENANCE',lambda:compile_constraints(fields,relations))
        fields,relations=fixture();relations[0]['orientation']='reverse'
        self.refusal('INVALID_RELATION',lambda:compile_constraints(fields,relations))

    def test_near_fraction_and_half_sample_stay_distinct_soft_rows(self):
        fields,relations=fixture();r=compile_constraints(fields,relations,numerical_targets=[
            {'id':sid,'domain_id':'left','sample_id':sid,'target_cm':[.5,0,0]}for sid in['near','half']])
        a,b=r['numerical_target_observations']
        self.assertNotEqual(a['sample_bindings'][0]['exact_uv_cm'],b['sample_bindings'][0]['exact_uv_cm'])
        self.assertEqual(len(r['numerical_target_observations']),2)

    def test_forged_flags_and_maps_do_not_bypass_revalidation(self):
        fields,relations=fixture()
        for c in fields.values():c['uv_qualification']='FORGED';c['qualification']='FORGED';c['material_reference_carrier_patches']=[]
        r=compile_constraints(fields,relations);self.assertEqual(r['qualification'],'NONE')
        fields['left']['inputs']['reference']['mesh']['uv_cm'][1][0]=2
        self.refusal('DOMAIN_COVERAGE',lambda:compile_constraints(fields,relations))

    def test_forged_source_hash_or_missing_declaration_refused(self):
        fields,relations=fixture();relations[0]['owners'][1]['source_sha256']='a'*64
        self.refusal('RELATION_PROVENANCE',lambda:compile_constraints(fields,relations))
        fields,relations=fixture();undeclared=copy.deepcopy(relations[0]);undeclared['id']='invented'
        self.refusal('UNDECLARED_RELATION',lambda:compile_constraints(fields,[undeclared]))

    def test_external_declared_identity_does_not_alias_other_sample(self):
        fields,relations=fixture()
        relations[0]['owners'][1]['samples'][0]['sample_id']='third'
        self.refusal('INVALID_RELATION',lambda:compile_constraints(fields,relations))

    def test_missing_domain_carrier_or_permanent_relation_refuses(self):
        fields,relations=fixture()
        self.refusal('MISSING_DOMAIN',lambda:compile_constraints({'left':fields['left']},relations))
        fields['left']['inputs']['carrier']=None
        self.refusal('INVALID_MESH',lambda:compile_constraints(fields,relations))
        fields,relations=fixture()
        self.refusal('MISSING_RELATION',lambda:compile_constraints(fields,[]))

    def test_duplicate_ids_and_unapproved_stop_rhs_refuse(self):
        fields,relations=fixture()
        self.refusal('IDENTITY_COLLISION',lambda:compile_constraints(fields,relations+relations))
        stops=stops_eight();stops[1]['id']=stops[0]['id']
        self.refusal('IDENTITY_COLLISION',lambda:compile_constraints(fields,relations,stops))
        stop={'id':'wrong','domain_id':'left','sample_id':'p0','target_cm':[1,2,3]}
        self.refusal('INVALID_CONTRACT',lambda:compile_constraints(fields,relations,[stop]))

    def test_absent_sample_and_domain_alias_refuse(self):
        fields,relations=fixture()
        self.refusal('INVALID_SAMPLE',lambda:compile_constraints(fields,relations,[{'id':'missing','domain_id':'left','sample_id':'absent'}]))
        self.refusal('DOMAIN_IDENTITY',lambda:compile_constraints({'alias':fields['left']},[]))

    def test_inputs_preserved_and_output_does_not_alias_fields(self):
        fields,relations=fixture();before=digest([fields,relations])
        r=compile_constraints(fields,relations);self.assertEqual(before,digest([fields,relations]))
        r['inputs']['fields']['left']['inputs']['source']['uv_cm'][0][0]=10
        self.assertEqual(before,digest([fields,relations]))

    def test_domain_revalidation_uses_one_shared_work_ledger(self):
        fields,relations=fixture();r=compile_constraints(fields,relations)
        self.assertEqual(r['domain_revalidation_count'],{'left':1,'right':1})
        self.assertEqual(r['receipt']['work']['source_vertices'],8)
        self.assertEqual(r['receipt']['work']['reference_vertices'],8)
        self.assertEqual(r['receipt']['work']['carrier_vertices'],16)
        self.refusal('BUDGET_EXHAUSTED',lambda:compile_constraints(fields,relations,budgets={'max_carrier_vertices':8}),True)

    def test_complete_output_caps_receipt_included(self):
        r=compile_constraints()
        self.assertEqual(r['receipt']['work']['output_nodes'],returned_nodes(r))
        self.assertEqual(r['receipt']['work']['output_bytes'],returned_bytes(r))
        cap=returned_nodes(r)
        r=compile_constraints(budgets={'max_output_nodes':cap});self.assertEqual(returned_nodes(r),cap)
        self.refusal('BUDGET_EXHAUSTED',lambda:compile_constraints(budgets={'max_output_nodes':cap-1}),True)

    def test_complete_utf8_byte_boundary_accepts_exact_and_refuses_one_below(self):
        fields,relations=fixture()
        targets=[{'id':'é漢🙂"\\\n','domain_id':'left','sample_id':'third','target_cm':[1/3,0,0]}]
        def call(cap=None):return compile_constraints(fields,relations,numerical_targets=targets,
            budgets=None if cap is None else{'max_output_bytes':cap})
        cap=returned_bytes(call())
        for _ in range(5):
            result=call(cap);actual=returned_bytes(result)
            if actual==cap:break
            cap=actual
        self.assertEqual(actual,cap);self.assertEqual(result['receipt']['work']['output_bytes'],cap)
        self.refusal('BUDGET_EXHAUSTED',lambda:call(cap-1),True)

    def test_augmented_rank_residual_copy_consumes_shared_matrix_cap(self):
        fields,relations=fixture();stops=stops_eight()
        # Ten rows, eight columns and three RHS values; the two redundant
        # residual rows copy three values each for augmented rank checking.
        cap=10*(8+3)+2*3
        result=compile_constraints(fields,relations,stops,budgets={'max_matrix_entries':cap})
        self.assertEqual(result['receipt']['work']['matrix_entries'],cap)
        self.refusal('BUDGET_EXHAUSTED',lambda:compile_constraints(fields,relations,stops,
            budgets={'max_matrix_entries':cap-1}),True)

    def test_constraints_geometry_precision_and_elimination_caps_refuse(self):
        fields,relations=fixture()
        for budget in[{'max_domains':1},{'max_hard_rows':1},{'max_unknown_nodes':1},
                       {'max_matrix_entries':1},{'max_elimination_operations':1},
                       {'max_certificate_terms':1},{'max_constraint_coefficients':1},
                       {'max_output_bytes':1},{'max_pair_checks':1},{'max_fraction_bits':1}]:
            with self.subTest(budget=budget):self.refusal('BUDGET_EXHAUSTED',lambda:compile_constraints(fields,relations,budgets=budget),True)

    def test_deadline_before_capture_during_revalidation_elimination_and_output(self):
        fields,relations=fixture()
        self.refusal('DEADLINE_EXHAUSTED',lambda:compile_constraints(fields,relations,deadline=0.),True)
        for phase in['constraint_budget_capture','constraint_domain_revalidation','constraint_relation',
                      'constraint_pivot_search','elimination_operations','output_serialization','output_return','output_terminal_deadline']:
            with self.subTest(phase=phase):
                clock=HookClock(phase=phase)
                self.refusal('DEADLINE_EXHAUSTED',lambda:compile_constraints(fields,relations,clock=clock,deadline=60.),True)
                self.assertTrue(clock.triggered)

    def test_reference_mutation_during_revalidation_elimination_or_return_refuses(self):
        for phase in['constraint_domain_revalidation','constraint_pivot_search','output_return']:
            fields,relations=fixture();clock=HookClock(phase=phase,action=lambda:fields['left']['inputs']['coordinates_cm'][0].__setitem__(2,1))
            self.refusal('REFERENCE_MUTATION',lambda:compile_constraints(fields,relations,clock=clock))
            self.assertTrue(clock.triggered)

    def test_optional_rank_certificate_is_explicitly_not_requested(self):
        r=compile_constraints(certify_hard=False)
        self.assertEqual(r['certificate']['status'],'NOT_REQUESTED')
        self.assertEqual(len(r['hard_rows']),2);self.assertNotIn('rank_A',r['certificate'])

    def test_linear_certificate_never_qualifies_metric_bars_or_fitting(self):
        r=compile_constraints(physical_stops=stops_eight())
        self.assertEqual(r['qualification'],'NONE');self.assertFalse(r['is_installable'])
        self.assertEqual(r['physical_pins_added'],[])
        for name in['metric','twelve_bars','traces','lengths','trajectory','contacts']:
            self.assertEqual(r[name],'NOT_ASSESSED')
        self.assertEqual(r['cloth'],'NOT_EXECUTED');self.assertEqual(r['fitting'],'NOT_QUALIFIED')


if __name__=='__main__':unittest.main()
