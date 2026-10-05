"""Small fresh compiler-state fixtures, never a real collar or native trial."""
import ast
import copy
from fractions import Fraction as F
import hashlib
import math
from pathlib import Path
import unittest
from unittest.mock import patch

from a3d import material_surface_field as field
from a3d import material_surface_compact as storage
from a3d import material_surface_metrics as metrics
from a3d.core import StudioError
from tests.test_material_surface_compact import data_fixture
from tests.test_material_surface_field import HookClock,returned_nodes,returned_bytes


def fresh(data=None,provenance=None,caps=None,clock=lambda:0.,deadline=None):
    data=data_fixture() if data is None else data
    originals=[data,provenance,caps,deadline]
    captured,before,budget=field._capture(originals,caps,deadline,clock)
    state=field._compile(captured[0],budget)
    return state,originals,before,budget,captured[1]


def observe(context,**kwargs):
    state,originals,before,budget,provenance=context
    return metrics.observe_material_surface_metrics(state,originals=originals,before=before,
        budget=budget,provenance=provenance,**kwargs)


class MaterialSurfaceMetricsTests(unittest.TestCase):
    def refusal(self,reason,call,incomplete=False):
        with self.assertRaises(StudioError)as caught:call()
        self.assertEqual(caught.exception.reason,reason)
        self.assertEqual(caught.exception.qualification,'NONE')
        self.assertEqual(caught.exception.status,'INCOMPLETE'if incomplete else'REFUSED')

    def sizes(self,result):
        self.assertEqual(result['receipt']['output']['nodes'],returned_nodes(result))
        self.assertEqual(result['receipt']['output']['bytes'],returned_bytes(result))

    def test_exact_legacy_metric_section_on_rotations_windings_shear_and_collapse(self):
        for reverse in(False,True):
            for kind in('identity','rotation','shear','collapse'):
                data=data_fixture(reverse)
                if kind=='rotation':data['coordinates_cm']=[[-p[1],p[0],0.]for p in data['coordinates_cm']]
                elif kind=='shear':data['coordinates_cm']=[[p[0]+.5*p[1],p[1],0.]for p in data['coordinates_cm']]
                elif kind=='collapse':data['coordinates_cm']=[[0.,0.,0.]for _ in data['coordinates_cm']]
                context=fresh(data);state=context[0]
                legacy=field._observe(state,field._Budget(None,None,lambda:0.))['carrier_face_metrics']
                expected=field._encode(legacy,field._Budget(None,None,lambda:0.))
                result=observe(context)
                with self.subTest(reverse=reverse,kind=kind):
                    self.assertEqual(result['carrier_face_metrics'],expected)
                    self.assertEqual(result['metric_checks']['all_bounds_met'],kind in('identity','rotation'))
                    self.sizes(result)

    def test_binary64_bounds_inclusive_and_one_ulp_outside_no_epsilon(self):
        for scale,met in((.9,True),(1.1,True),(math.nextafter(.9,0.),False),
                          (math.nextafter(1.1,math.inf),False)):
            data=data_fixture();data['coordinates_cm']=[[p[0]*scale,p[1],p[2]]for p in data['coordinates_cm']]
            result=observe(fresh(data))
            with self.subTest(scale=scale):
                self.assertEqual(result['metric_checks']['all_bounds_met'],met)
                self.assertEqual(result['metric_checks']['evaluated_faces'],2)
                self.assertEqual(result['metric_checks']['passed_faces'],2 if met else 0)
                self.assertEqual(result['metric_checks']['violated_faces'],0 if met else 2)
                self.assertEqual(result['metric_checks']['violating_face_ids'],[]if met else['f0','f1'])
                self.assertEqual(F(result['lower_gram_bound_squared_exact']),F(.9)**2)
                self.assertEqual(F(result['upper_gram_bound_squared_exact']),F(1.1)**2)
                self.assertFalse(result['epsilon_allowance'])

    def test_no_displacement_step_stop_contact_domain_or_fitting_admission(self):
        data=data_fixture(with_owners=True)
        data['coordinates_cm']=[[p[0]+100.,p[1],p[2]]for p in data['coordinates_cm']]
        data['previous_coordinates_cm']=[[0.,0.,0.]for _ in data['coordinates_cm']]
        result=observe(fresh(data,{'declared_strength':'HARD'}))
        self.assertTrue(result['metric_checks']['all_bounds_met'])
        for key in('displacement','step','physical_stops','contacts'):
            self.assertEqual(result[key],'NOT_ASSESSED')
        self.assertEqual(result['qualification'],'NONE')
        self.assertEqual(result['constraints_3d'],'NOT_QUALIFIED')
        self.assertEqual(result['fitting'],'NOT_QUALIFIED')
        self.assertIn('NOT_REVALIDATED',result['domain_validation'])
        self.assertFalse(result['physical_mesh']);self.assertFalse(result['is_installable'])
        self.assertNotIn('inputs',result);self.assertNotIn('READY',str(result))

    def test_fresh_compile_same_budget_no_hidden_capture_compile_or_clock(self):
        context=fresh();budget=context[3];used=dict(budget.counts)
        with (patch.object(field,'_capture',side_effect=AssertionError('new capture')),
              patch.object(field,'_compile',side_effect=AssertionError('new compile'))):
            result=observe(context,input_hashes=field._hashes(context[0],budget))
        self.assertEqual(budget.counts['metric_faces'],2)
        self.assertEqual(budget.counts['pair_checks'],used['pair_checks'])
        self.assertEqual(budget.counts['input_nodes'],used['input_nodes'])
        self.assertEqual(budget.counts.get('patch_vertex_checks',0),used.get('patch_vertex_checks',0))
        self.assertEqual(result['receipt']['work'],budget.counts)
        tree=ast.parse(Path(metrics.__file__).read_text(encoding='utf-8'))
        forbidden={'_Budget','_capture','_compile','_observe','_interpolate'}
        self.assertFalse(any(isinstance(n,ast.Call)and isinstance(n.func,ast.Attribute)
            and n.func.attr in forbidden for n in ast.walk(tree)))
        self.assertFalse(any(isinstance(n,ast.Import)and any(a.name in('time','bpy','sqlite3')for a in n.names)
            for n in ast.walk(tree)))

    def test_raw_metric_kernel_reuses_exact_helpers_and_debits_13_q_per_face(self):
        context=fresh();budget=context[3];before=dict(budget.counts)
        rows,_,_=metrics._face_metrics(context[0],budget)
        self.assertEqual(len(rows),2)
        self.assertEqual(budget.counts['metric_faces']-before.get('metric_faces',0),2)
        self.assertEqual(budget.counts['fraction_operations']-before['fraction_operations'],26)

    def test_actual_metrics_identity_and_checkpoint_scope(self):
        result=observe(fresh());actual=hashlib.sha256(Path(metrics.__file__).read_bytes()).hexdigest()
        self.assertEqual(result['metrics_code_sha256'],actual)
        self.assertEqual(result['receipt']['input_hashes']['metrics_code'],actual)
        self.assertEqual(result['metric_inputs_sha256'],result['receipt']['input_hashes']['metric_inputs'])
        self.assertEqual(set(result['receipt']['code_sha256']),{'compact','field','uv'})
        self.assertIn('BEFORE_METRICS_RETURN_GUARDS',result['receipt_scope'])

    def test_originals_provenance_and_output_have_no_mutable_alias(self):
        context=fresh(provenance={'opaque':['retained']});before=copy.deepcopy(context[1])
        result=observe(context)
        self.assertEqual(context[1],before)
        result['carrier_face_metrics'][0]['carrier_face_id']='changed'
        result['metric_checks']['violating_face_ids'].append('not-real')
        self.assertEqual(context[1],before)

    def test_cumulative_output_two_observations_and_packing_no_reset(self):
        context=fresh();first=observe(context);second=observe(context);budget=context[3]
        self.assertEqual(budget.counts['metric_faces'],4)
        self.assertEqual(budget.counts['output_nodes'],returned_nodes(first)+returned_nodes(second))
        self.assertEqual(budget.counts['output_bytes'],returned_bytes(first)+returned_bytes(second))
        self.assertEqual(second['receipt']['work'],budget.counts)
        self.sizes(first);self.sizes(second)

    def test_metric_face_cap_partial_work_retained(self):
        context=fresh(caps={'max_metric_faces':1});used=dict(context[3].counts)
        self.refusal('BUDGET_EXHAUSTED',lambda:observe(context),True)
        self.assertEqual(context[3].counts['metric_faces'],1)
        self.assertGreater(context[3].counts['fraction_operations'],used['fraction_operations'])

    def test_fraction_and_output_caps_refuse_without_refund(self):
        baseline=fresh();result=observe(baseline)
        for caps in({'max_fraction_operations':baseline[3].counts['fraction_operations']-1},
                     {'max_output_nodes':returned_nodes(result)-1},
                     {'max_output_bytes':1}):
            context=fresh(caps=caps);before=dict(context[3].counts)
            with self.subTest(caps=caps):
                self.refusal('BUDGET_EXHAUSTED',lambda:observe(context),True)
                self.assertTrue(all(context[3].counts[k]>=v for k,v in before.items()))

    def test_fake_budget_and_relaxed_cap_refuse(self):
        context=fresh()
        self.refusal('INVALID_BUDGET',lambda:metrics.observe_material_surface_metrics(context[0],
            originals=context[1],before=context[2],budget=object()))
        context[3].limits['max_fraction_operations']=300001
        self.refusal('INVALID_BUDGET',lambda:observe(context))

    def test_original_or_provenance_outside_capture_and_caller_hash_refuse(self):
        context=fresh();context[1][0]['coordinates_cm'][0][0]=2.
        self.refusal('REFERENCE_MUTATION',lambda:observe(context))
        context=fresh();self.refusal('INVALID_CAPTURE',lambda:metrics.observe_material_surface_metrics(
            context[0],originals=context[1],before=context[2],budget=context[3],provenance={'not-captured':True}))
        context=fresh();hashes=field._hashes(context[0],context[3]);hashes['candidate']='0'*64
        self.refusal('REFERENCE_MUTATION',lambda:observe(context,input_hashes=hashes))

    def test_state_flag_or_persisted_object_is_not_a_compile_contract(self):
        context=fresh()
        for fake in({'validated':True}, {'discriminant':storage.DISCRIMINANT,'status':'COMPILED_TEST_ONLY'}):
            with self.subTest(fake=fake):self.refusal('INVALID_CONTRACT',lambda:metrics.observe_material_surface_metrics(
                fake,originals=context[1],before=context[2],budget=context[3]))

    def test_deadline_in_kernel_finalizer_and_last_metrics_return(self):
        for phase in('metrics_gram','compact_complete_serialization_after',
                      'metrics_final_used_inputs_after_hash','metrics_return_terminal_deadline'):
            clock=HookClock();context=fresh(clock=clock);clock.phase=phase
            with self.subTest(phase=phase):self.refusal('DEADLINE_EXHAUSTED',lambda:observe(context),True)

    def test_used_internal_state_mutation_before_return_guards_refuses(self):
        clock=HookClock();context=fresh(clock=clock)
        clock.phase='compact_complete_serialization_after'
        clock.action=lambda:context[0]['current'].__setitem__(0,(F(1),F(0),F(0)))
        self.refusal('REFERENCE_MUTATION',lambda:observe(context))
        self.assertGreater(context[3].counts['output_bytes'],0)

    def test_original_mutation_at_compact_terminal_caught_by_metrics_guards(self):
        clock=HookClock();context=fresh(clock=clock)
        clock.phase='compact_output_terminal_deadline'
        clock.action=lambda:context[1][0]['coordinates_cm'][0].__setitem__(0,2.)
        self.refusal('REFERENCE_MUTATION',lambda:observe(context))

    def test_metrics_actual_file_mutation_after_finalizer_refuses(self):
        context=fresh();original=Path.read_bytes;count=[0]
        def changing(path):
            raw=original(path)
            if path.resolve()==Path(metrics.__file__).resolve():
                count[0]+=1
                if count[0]==2:return raw+b'\n# simulated changed bytes\n'
            return raw
        with patch.object(Path,'read_bytes',changing):
            self.refusal('CODE_MUTATION',lambda:observe(context))
        self.assertEqual(count[0],2)

    def test_no_new_interval_when_shared_caller_deadline_expires(self):
        value=[2.];context=fresh(clock=lambda:value[0],deadline=3.)
        self.assertEqual(context[3].deadline,3.);value[0]=3.
        self.refusal('DEADLINE_EXHAUSTED',lambda:observe(context),True)
        self.assertEqual(context[3].start,2.)


if __name__=='__main__':unittest.main()
