import copy
import unittest
from unittest.mock import patch
from a3d.core import StudioError,contract
from a3d.meshing_profile import create_envelope,verify_inventory,verify_envelope,profile_binding,prepare_profile
from a3d.pattern_preparation import prepare_regular_boundaries
from tests.test_boundary_gradation import fixture,binary32


def profile(ids):
    return {'version':1,'mode':'SYNCHRONIZED_GRADED_V1','piece_ids':list(ids),
        'budgets':{'max_seconds':90.,'max_capture_nodes':500000,'max_capture_bytes':8388608,
        'max_output_nodes':500000,'max_output_bytes':8388608,'max_work_steps':100000000,
        'max_sampling_calls':20,'max_sampling_point_slots':20000,'max_fraction_requests':4000}}


class MeshingProfileTests(unittest.TestCase):
    def inputs(self):
        data,recipe,regular,*_=fixture()
        return data,recipe,regular,profile(data['pieces'])

    def test_profile_prepared_by_code_is_inventory_deterministic_and_preserves_budgets(self):
        data,recipe,regular,p=self.inputs();before=copy.deepcopy((data,recipe,regular,p))
        a=prepare_profile(data,recipe,regular,p['budgets'])
        other={**data,'pieces':dict(reversed(list(data['pieces'].items())))}
        self.assertEqual(a,prepare_profile(other,recipe,regular,p['budgets']))
        self.assertEqual(before,(data,recipe,regular,p))
        a['budgets']['max_seconds']=1.
        self.assertEqual(p['budgets']['max_seconds'],90.)

    def test_explicit_global_and_per_piece_limits_share_one_origin(self):
        data,recipe,regular,p=self.inputs()
        e=create_envelope(p,data['component_id'],recipe,regular,clock=lambda:12.,started_at=5.)
        self.assertEqual(e.start,5.);self.assertEqual(e.deadline,95.)
        self.assertEqual(e.limits['attempted_insertions'],4000)
        self.assertEqual(e.limits['native_cdt_calls'],18)
        self.assertEqual(e.owner_limits['native_cdt_calls'],9)
        self.assertEqual(e.limits['native_point_slots'],18000)
        self.assertEqual(e.snapshot()['qualification'],'NONE')

    def test_schema_refuses_partial_unknown_duplicate_and_excessive_profile(self):
        data,recipe,regular,p=self.inputs()
        spec={'version':1,'component_id':data['component_id'],'source_ref':'fixture',
              'regular_mesh':regular,'meshing_profile':p}
        contract('pattern-preparation',spec)
        for mutate in (lambda q:q.update(mode='boundary_only'),lambda q:q.update(extra=True),
                       lambda q:q['piece_ids'].append(q['piece_ids'][0]),
                       lambda q:q['budgets'].update(max_seconds=90.000001),
                       lambda q:q['budgets'].pop('max_work_steps')):
            bad=copy.deepcopy(p);mutate(bad)
            with self.assertRaises(StudioError):create_envelope(bad,data['component_id'],recipe,regular,clock=lambda:0.)

    def test_domain_refusals_do_not_change_legacy_recipe_or_configuration(self):
        data,recipe,regular,p=self.inputs();before=copy.deepcopy((recipe,regular))
        for change in ('passes','maximum','fine','component'):
            r=copy.deepcopy(recipe);m=copy.deepcopy(regular)
            if change=='passes':r['mesh']['quality_refinement']['max_passes']=9
            elif change=='maximum':r['mesh']['max_vertices']=m['max_vertices']=30001
            elif change=='fine':m['min_spacing_cm']=1.01
            else:r['component_id']='other'
            with self.assertRaises(StudioError)as caught:create_envelope(p,data['component_id'],r,m,clock=lambda:0.)
            self.assertEqual(caught.exception.reason,'MESHING_PROFILE_REFUSED')
        self.assertEqual(before,(recipe,regular))

    def test_exact_whole_source_inventory_required(self):
        data,recipe,regular,p=self.inputs();e=create_envelope(p,data['component_id'],recipe,regular,clock=lambda:0.)
        verify_inventory(p,data,e)
        for changed in ({**data,'component_id':'other'},{**data,'pieces':{'left':data['pieces']['left']}}):
            with self.assertRaises(StudioError):verify_inventory(p,changed,e)
        self.assertTrue(all(v==0 for v in e.snapshot()['work'].values()))

    def test_supplied_envelope_cannot_expand_declared_limits(self):
        data,recipe,regular,p=self.inputs();e=create_envelope(p,data['component_id'],recipe,regular,clock=lambda:0.)
        verify_envelope(p,data['component_id'],recipe,regular,e)
        changed=copy.deepcopy(p);changed['budgets']['max_work_steps']-=1
        with self.assertRaises(StudioError)as caught:verify_envelope(changed,data['component_id'],recipe,regular,e)
        self.assertEqual(caught.exception.reason,'MESHING_PROFILE_REFUSED')

    def test_mesh_caller_forwards_one_envelope_and_reserves_future_piece_vertices(self):
        from blender.sewing import build_mesh
        from tests.test_bounded_pattern_meshing import SuppliedNativeFixtures,Backend
        data,recipe,regular,p=self.inputs();parts,seams,sampling=prepare_regular_boundaries(data,recipe,regular)
        before=copy.deepcopy((data,recipe,regular,p));e=create_envelope(p,data['component_id'],recipe,regular,clock=lambda:0.)
        calls=[]
        def bounded(boundary,r,m,*,envelope):
            calls.append((boundary['piece_id'],m['max_vertices'],envelope))
            polygon=boundary['polygon'];boundary['preparation_refinement']={'status':'FIXTURE_NOT_NATIVE'}
            return copy.deepcopy(polygon),[[0,i,i+1]for i in range(1,len(polygon)-1)],dict(enumerate(range(len(polygon))))
        with SuppliedNativeFixtures(Backend()),patch('a3d.pattern_preparation.prepare_regular_boundaries',return_value=(copy.deepcopy(parts),copy.deepcopy(seams),sampling))as prepare,patch('blender.bounded_pattern_meshing.triangulate',side_effect=bounded),patch('blender.sewing.placed_point',side_effect=lambda v,p:[*v,0.]),patch('blender.sewing.mesh_quality',return_value={'rest_area_cm2':1.}):
            payload=build_mesh(data,recipe,regular,meshing_profile=p,meshing_envelope=e)
        self.assertEqual(before,(data,recipe,regular,p));self.assertEqual(len(calls),2)
        self.assertTrue(all(item[2]is e for item in calls))
        self.assertEqual(calls[0][1],regular['max_vertices']-len(parts['right']['polygon']))
        self.assertEqual(calls[1][1],regular['max_vertices']-len(parts['left']['polygon']))
        self.assertIs(prepare.call_args.kwargs['meshing_envelope'],e)
        self.assertEqual(payload['meshing_profile'],profile_binding(p))
        self.assertEqual(payload['meshing_work']['qualification'],'NONE')
        self.assertEqual(payload['meshing_work']['start'],0.)

    def test_boundary_activation_charges_baseline_and_rebinds_source(self):
        data,recipe,regular,p=self.inputs();before=copy.deepcopy((data,recipe,regular))
        e=create_envelope(p,data['component_id'],recipe,regular,clock=lambda:0.)
        parts,seams,report=prepare_regular_boundaries(data,recipe,regular,
            meshing_envelope=e,transport_2d=binary32)
        self.assertEqual(before,(data,recipe,regular))
        self.assertEqual(set(parts),set(data['pieces']));self.assertEqual(set(seams),{'join'})
        self.assertIn('source_boundary_gradation',report)
        self.assertGreater(e.snapshot()['work']['sampling_calls'],1)
        self.assertGreater(e.snapshot()['work']['attempted_insertions'],0)
        self.assertEqual(report['source_notch_policy'],'MATERIAL_REFERENCE_WITHOUT_REQUIRED_PHYSICAL_VERTEX')
        self.assertEqual(profile_binding(p)['qualification'],'NONE')

    def test_native_refusal_becomes_structured_without_resetting_attempted_work(self):
        from blender.sewing import build_mesh
        from blender.bounded_pattern_meshing import ConditionedPointRefusal
        from tests.test_bounded_pattern_meshing import SuppliedNativeFixtures,Backend
        data,recipe,regular,p=self.inputs();parts,seams,sampling=prepare_regular_boundaries(data,recipe,regular)
        e=create_envelope(p,data['component_id'],recipe,regular,clock=lambda:0.)
        cause=ConditionedPointRefusal('AMBIGUOUS_INPUT_IDENTITY',output_id=2)
        partial={'qualification':'NONE','best_safe_candidate':'LAST_CHECKPOINT_ONLY'}
        cause.bounded_meshing_partial=partial
        def refused(*args,envelope,**kwargs):
            envelope.reserve('native_cdt_calls',1,owner='left')
            raise cause
        with SuppliedNativeFixtures(Backend()),patch('a3d.pattern_preparation.prepare_regular_boundaries',return_value=(parts,seams,sampling)),patch('blender.bounded_pattern_meshing.triangulate',side_effect=refused):
            with self.assertRaises(StudioError)as caught:
                build_mesh(data,recipe,regular,meshing_profile=p,meshing_envelope=e)
        self.assertEqual(caught.exception.reason,'AMBIGUOUS_INPUT_IDENTITY')
        self.assertEqual(caught.exception.status,'REFUSED')
        self.assertEqual(caught.exception.diagnostic,{'output_id':2})
        self.assertIs(caught.exception.bounded_meshing_partial,partial)
        self.assertIs(caught.exception.__cause__,cause)
        self.assertEqual(e.snapshot()['work']['native_cdt_calls'],1)

    def test_no_profile_keeps_source_preparation_exact_and_inactive(self):
        data,recipe,regular,p=self.inputs()
        old=prepare_regular_boundaries(data,recipe,regular)
        with patch('a3d.boundary_gradation.grade_shared_boundaries',side_effect=AssertionError('inactive')):
            same=prepare_regular_boundaries(data,recipe,regular,meshing_envelope=None,transport_2d=None)
        self.assertEqual(old,same)
        self.assertNotIn('source_boundary_gradation',same[2])
        with self.assertRaises(StudioError):prepare_regular_boundaries(data,recipe,regular,transport_2d=binary32)

    def test_boundary_deadline_is_checked_before_capture(self):
        data,recipe,regular,p=self.inputs();now=[0.]
        e=create_envelope(p,data['component_id'],recipe,regular,clock=lambda:now[0]);now[0]=90.
        with patch('a3d.pattern_preparation.prepare_boundaries',side_effect=AssertionError('must not allocate')):
            with self.assertRaises(StudioError)as caught:
                prepare_regular_boundaries(data,recipe,regular,meshing_envelope=e,transport_2d=binary32)
        self.assertEqual(caught.exception.reason,'DEADLINE_EXHAUSTED')
        self.assertEqual(e._counts['sampling_calls'],0)

if __name__=='__main__':unittest.main()
