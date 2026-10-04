"""Admission contracts only; mocked calls never qualify native Cloth or visuals."""
import base64
import copy
from types import SimpleNamespace
from unittest.mock import patch

from a3d.core import ROOT,StudioError,atomic_json,digest,sha,read_json
from blender.pattern_assembly import freeze_continuous,validate_envelope_review
from tests.test_core import Case


class GeometryBoundaryReached(RuntimeError):
    pass


class RefusedPreformSupportContracts(Case):
    def test_initial_metric_refusal_does_not_hide_declared_source_supports(self):
        from blender.pattern_preparation import preform_supports
        payload={'panels':{'a':{'indices':[0,1],'edges':{'top':[0,1]}}},
            'seams':{'join':{'kind':'permanent','pairs':[[0,1]]}},'source_pins':{'0':.25}}
        plan={'supports':{'temporary':[{'id':'shoulder','piece':'a','edge':'top','weight':1.,'source_ref':'actual:source-edge'}],
            'drape':[],'functional':[]},'consolidation':{'weld_gap_cm':.15}}
        before=digest([payload,plan]);weights,observations=preform_supports(payload,plan,[[0.,0.,0.],[1.,0.,0.]])
        self.assertEqual(weights,{'0':1.,'1':1.})
        self.assertEqual(observations['contradictory_fixed_cohorts'],[[0,1]])
        self.assertEqual(observations['source_pin_transition']['0'],{'source_weight':.25,'prepared_weight':1.})
        self.assertEqual(digest([payload,plan]),before)


class ContactOutcomeContracts(Case):
    def test_indeterminate_sign_is_not_reported_as_an_observed_physical_failure(self):
        from blender.sewing import contact_refusal
        report={'reason':'INTERPOLATED_CONTACT','contact':{'point_samples':{'ambiguous_sign_count':1},'contact_count':0}}
        error=contact_refusal(report)
        self.assertEqual((error.reason_category,error.simulation_outcome),('contact_sign_uncertainty','INCOMPLETE'))
        report['contact']['contact_count']=1
        self.assertEqual(contact_refusal(report).simulation_outcome,'FAIL')

    def test_bounded_sampling_and_invalid_context_are_incomplete(self):
        from blender.sewing import contact_refusal
        for reason in ('SWEPT_RAY_BUDGET','COLLIDER_VOLUME_ORIENTATION'):
            with self.subTest(reason=reason):self.assertEqual(contact_refusal({'reason':reason}).simulation_outcome,'INCOMPLETE')


class ContinuousFreezeContracts(Case):
    def setUp(self):
        super().setUp()
        self.project=SimpleNamespace(root=self.root)
        self.payload={'component_id':'coat','package_sha256':'package'}
        self.recipe=read_json(ROOT/'templates/sewing-recipe.json');self.recipe['component_id']='coat'
        atomic_json(self.root/'plan.json',{'synthetic':True})
        atomic_json(self.root/'map.json',{'synthetic':True})
        self.record={'component_id':'coat','package_sha256':'package','recipe_sha256':digest(self.recipe),
            'plan':{'path':'plan.json','sha256':sha(self.root/'plan.json')},
            'derived_mesh':{'path':'map.json','sha256':sha(self.root/'map.json')},
            'mesh_sha256':'mesh','accepted':False,'stage':'drape','simulation':'PASS',
            'qualification':'FITTING_PHYSICS_ONLY','fitting':{'fit_binding':'fit'},
            'dressing':{'status':'READY','required':True,'full_coverage':True},
            'cloth_runs':[{'simulation':'PASS','executed':{'settings':{'use_sewing_springs':False}},
                           'validation_contract':{'version':2},
                           'support_transition':{'temporary_supports_active':False}}]}
        self.obj={'a3d_pattern_assembly_receipt':'receipt.json','a3d_sewing_mesh_sha256':sha(self.root/'map.json')}
        self.fit={'fit_status':'CAPACITY_SUFFICIENT','fit_binding':'fit','donning':{'missing':[]}}

    def invoke(self,record=None,fit=None):
        atomic_json(self.root/'receipt.json',record or self.record)
        self.obj['a3d_pattern_assembly_receipt_sha256']=sha(self.root/'receipt.json')
        with patch.dict('sys.modules',{'bpy':SimpleNamespace()}), \
                patch('blender.pattern_assembly.mesh_digest',return_value='mesh'), \
                patch('blender.fitting.recipe_fit',return_value=fit or self.fit), \
                patch('blender.pattern_assembly.object_mesh',side_effect=GeometryBoundaryReached('admitted to native geometry')):
            return freeze_continuous(self.project,{},self.obj,self.payload,self.recipe)

    def test_exact_qualified_receipt_reaches_geometry_without_claiming_native_execution(self):
        with self.assertRaisesRegex(GeometryBoundaryReached,'admitted to native geometry'):
            self.invoke()

    def test_test_only_cannot_freeze_via_internal_entrypoint(self):
        self.recipe['physics_purpose']='TEST_ONLY'
        with patch('blender.pattern_assembly.object_mesh') as geometry:
            with self.assertRaisesRegex(StudioError,'TEST_ONLY'):
                self.invoke()
            geometry.assert_not_called()

    def test_assembly_consolidation_relaxation_and_unqualified_drape_do_not_freeze(self):
        for stage in ('mount','close','consolidate','relax'):
            record=copy.deepcopy(self.record);record['stage']=stage
            with self.subTest(stage=stage),self.assertRaisesRegex(StudioError,'exact qualified drape'):
                self.invoke(record)
        record=copy.deepcopy(self.record);record['qualification']='DRAPE_PHYSICS_ONLY_FITTING_NOT_QUALIFIED'
        with self.assertRaisesRegex(StudioError,'exact qualified drape'):self.invoke(record)

    def test_changed_mesh_map_recipe_and_plan_are_not_qualified_by_old_drape(self):
        for field,value in (('mesh_sha256','other'),('recipe_sha256','other')):
            record=copy.deepcopy(self.record);record[field]=value
            with self.subTest(field=field),self.assertRaisesRegex(StudioError,'binding is stale'):
                self.invoke(record)
        atomic_json(self.root/'map.json',{'changed':True})
        with self.assertRaisesRegex(StudioError,'referenced artifact changed'):self.invoke()

    def test_temporary_pins_and_sewing_springs_cannot_reach_freeze(self):
        for temporary,springs in ((True,False),(False,True)):
            record=copy.deepcopy(self.record)
            record['cloth_runs'][0]['executed']['settings']['use_sewing_springs']=springs
            record['cloth_runs'][0]['support_transition']['temporary_supports_active']=temporary
            with self.subTest(temporary=temporary,springs=springs),self.assertRaisesRegex(StudioError,'without sewing springs'):
                self.invoke(record)
        record=copy.deepcopy(self.record);record['cloth_runs']=[]
        with self.assertRaisesRegex(StudioError,'without sewing springs'):self.invoke(record)

    def test_legacy_physics_pass_does_not_claim_new_metric_and_motion_coverage(self):
        record=copy.deepcopy(self.record)
        del record['cloth_runs'][0]['validation_contract']
        with self.assertRaisesRegex(StudioError,'Legacy drape evidence'):
            self.invoke(record)

    def test_unassessed_dressing_cannot_become_qualified_fitting(self):
        record=copy.deepcopy(self.record);record.pop('dressing')
        with self.assertRaisesRegex(StudioError,'source-bound dressing'):self.invoke(record)
        for field in ('required','full_coverage'):
            record=copy.deepcopy(self.record);record['dressing'][field]=False
            with self.subTest(field=field),self.assertRaisesRegex(StudioError,'source-bound dressing'):self.invoke(record)

    def test_changed_or_deficient_fitting_remains_blocked_after_physics_pass(self):
        for change in ({'fit_binding':'stale'},{'fit_status':'INCOMPATIBLE'},
                       {'donning':{'missing':['validated body landmarks']}}):
            fit={**copy.deepcopy(self.fit),**change}
            with self.subTest(change=change),self.assertRaisesRegex(StudioError,'missing, changed or unqualified'):
                self.invoke(fit=fit)


class EnvelopeReviewContracts(Case):
    def setUp(self):
        super().setUp()
        self.project=SimpleNamespace(root=self.root)
        self.proxy={'a3d_body_geometry_sha256':'target-body'}
        # A fixed one-pixel synthetic image tests reference integrity, not review.
        image=base64.b64decode('iVBORw0KGgoAAAANSUhEUgAAAAEAAAABCAQAAAC1HAwCAAAAC0lEQVR42mP8/x8AAusB9Y9Z4S8AAAAASUVORK5CYII=')
        views={}
        for view in ('front','side','back','threequarter'):
            path=self.root/(view+'.png');path.write_bytes(image)
            views[view]={'path':path.name,'sha256':sha(path)}
        self.record={'visual_validation':'REVIEWED','collision_use':'SUITABLE',
            'source_ref':'synthetic-contract-fixture-not-a-consumer-review','geometry_sha256':'envelope',
            'target_geometry_sha256':'target-body','views':views}

    def invoke(self,record=None):
        atomic_json(self.root/'review.json',record or self.record)
        ref={'path':'review.json','sha256':sha(self.root/'review.json')}
        with patch('blender.pattern_assembly.require_envelope_review',return_value=[self.proxy]), \
                patch('blender.pattern_assembly.mesh_digest',return_value='envelope'):
            result=validate_envelope_review(self.project,{'collision':{'envelope_review':ref}},{},[])
        self.assertEqual(result,ref)

    def test_complete_immutable_synthetic_review_contract_is_admitted(self):
        self.invoke()

    def test_view_names_without_image_evidence_are_refused(self):
        record=copy.deepcopy(self.record);record['views']=list(record['views'])
        with self.assertRaisesRegex(StudioError,'immutable image references'):self.invoke(record)

    def test_unsuitable_collision_review_and_wrong_target_are_refused(self):
        record=copy.deepcopy(self.record);record['collision_use']='NOT_SUITABLE'
        with self.assertRaisesRegex(StudioError,'suitability'):self.invoke(record)
        record=copy.deepcopy(self.record);record['target_geometry_sha256']='another-pose'
        with self.assertRaisesRegex(StudioError,'exact target body'):self.invoke(record)

    def test_changed_image_or_wrong_envelope_invalidates_review(self):
        record=copy.deepcopy(self.record);record['geometry_sha256']='another-envelope'
        with self.assertRaisesRegex(StudioError,'another geometry'):self.invoke(record)
        (self.root/'front.png').write_bytes(b'changed')
        with self.assertRaisesRegex(StudioError,'referenced artifact changed'):self.invoke()

    def test_nonimage_file_does_not_supply_visual_evidence(self):
        path=self.root/'front.png';path.write_bytes(b'not a picture'*5)
        record=copy.deepcopy(self.record);record['views']['front']['sha256']=sha(path)
        with self.assertRaisesRegex(StudioError,'actual PNG/JPEG/WebP'):self.invoke(record)


class ContinuousSourceCoordinates(Case):
    def fixture(self):
        return {'rest_mode':'assembled_3d','rest_cm':[[0,0,0],[1.1,0,0],[0,1,0],[0,-1,0],[-1,0,0]],
            'faces':[[0,1,2],[0,3,4]],'pins':{},'seams':{},
            'panels':{'left':{'indices':[0,1,2],'edges':{}},'right':{'indices':[0,3,4],'edges':{}}},
            'regional_source':{'rest_cm':[[0,0,0],[1,0,0],[0,1,0],[100,200,1000],[101,200,1000],[100,201,1000]],
                'panels':{'left':{'indices':[0,1,2]},'right':{'indices':[3,4,5]}}},
            'source_vertex_map':{'0':0,'1':1,'2':2,'3':0,'4':3,'5':4},
            'source_vertex_cohorts':{'0':[0,3],'1':[1],'2':[2],'3':[4],'4':[5]},
            'source_vertex_indices':[0,1,2,4,5],
            'source_rest_triangles_cm':[[[0,0],[1,0],[0,1]],[[100,200],[101,200],[100,201]]]}

    def test_shared_seam_vertex_has_two_uv_origins_without_invented_mean(self):
        from a3d.sewing_diagnostics import source_coordinates
        payload=self.fixture();record=source_coordinates(payload,0)
        self.assertIsNone(record['rest_uv_cm'])
        self.assertEqual([row['source_uv_cm'] for row in record['source_uv_samples']],[[0,0],[100,200]])
        self.assertEqual(source_coordinates(payload,0,'right')['rest_uv_cm'],[100,200])
        self.assertEqual(record['simulation_rest_domain'],'assembled_3d')

    def test_failure_stretch_uses_source_2d_face_metric_not_assembled_rest(self):
        from a3d.sewing_diagnostics import failure_geometry
        payload=self.fixture();coords=copy.deepcopy(payload['rest_cm'])
        recipe={'mesh':{'min_stretch':.95,'max_stretch':1.05,'min_edge_cm':.001,'min_angle_degrees':1},
                'limits':{'max_seam_gap_cm':.15}}
        report=failure_geometry(payload,coords,coords,recipe)
        edge=next(row for row in report['outlier_edges'] if row['indices']==[0,1])
        self.assertAlmostEqual(edge['ratio'],1.1)
        self.assertEqual(edge['rest_metric_domain'],'immutable_source_uv_per_face')
        self.assertEqual(report['rest_coordinate_domain'],'assembled_3d')

    def test_continuous_subset_keeps_uv_bindings_after_current_vertex_renumbering(self):
        from blender.sewing import subset_mesh
        from a3d.cloth_metrics import face_sources
        payload=self.fixture();payload['placed_cm']=copy.deepcopy(payload['rest_cm'])
        payload['source_face_pieces']=['left','right'];payload['source_face_vertex_ids']=[[0,1,2],[3,4,5]]
        for panel in payload['panels'].values():panel['boundary']=list(panel['indices'])
        sub=subset_mesh(payload,['right'])
        self.assertEqual(sub['faces'],[[0,1,2]])
        self.assertEqual(sub['source_vertex_map'],{'0':0,'3':0,'4':1,'5':2})
        self.assertEqual(sub['source_vertex_cohorts'],{'0':[0,3],'1':[4],'2':[5]})
        self.assertEqual(face_sources(sub)['binding_issues'],[])
        self.assertEqual(face_sources(sub)['source_rest_triangles_cm'],[[[100,200],[101,200],[100,201]]])
