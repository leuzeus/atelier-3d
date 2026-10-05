"""Guard and receipt tests only; live Blender execution has separate fixtures."""
import copy
from types import SimpleNamespace
from unittest.mock import patch

from a3d.core import StudioError,atomic_json,digest,sha
from a3d.guard import admit_operation
from blender.pattern_assembly import nearest_signed_distance_cm
from blender.pattern_preparation import prepared_receipt,_material_assessment,_placement_displacement,migrate_preparation_recipe
from tests.test_core import Case
from tests.support import ready_project


class PreparedReceiptContracts(Case):
    def setUp(self):
        super().setUp()
        self.project=SimpleNamespace(root=self.root)
        self.recipe={'component_id':'coat'}
        self.payload={'component_id':'coat','package_sha256':'package'}
        for name in ('spec','plan','map','dossier'):
            atomic_json(self.root/(name+'.json'),{'fixture':name})
        atomic_json(self.root/'recipe.json',self.recipe)
        self.ref=lambda name:{'path':name+'.json','sha256':sha(self.root/(name+'.json'))}
        self.plan=self.ref('plan')
        self.record={'readiness':'READY','simulation':'NOT_EXECUTED','accepted':False,
            'validation_contract':{'version':2},
            'component_id':'coat','package_sha256':'package','recipe_sha256':digest(self.recipe),
            'assembly_plan':self.plan,'derived_mesh':self.ref('map'),'mesh_sha256':'prepared-world-geometry',
            'preparation_spec':self.ref('spec'),'recipe':self.ref('recipe'),'construction_dossier':self.ref('dossier')}
        self.obj={'a3d_pattern_preparation_receipt':'receipt.json','a3d_sewing_mesh_sha256':sha(self.root/'map.json')}

    def invoke(self,record=None,geometry='prepared-world-geometry'):
        atomic_json(self.root/'receipt.json',record or self.record)
        self.obj['a3d_pattern_preparation_receipt_sha256']=sha(self.root/'receipt.json')
        with patch('blender.pattern_preparation.mesh_digest',return_value=geometry):
            return prepared_receipt(self.project,self.obj,self.payload,self.recipe,self.plan)

    def test_exact_ready_receipt_admits_same_geometry_without_running_placement(self):
        with patch('a3d.pattern_assembly.preform_coordinates',side_effect=AssertionError('must not replay placement')):
            record,ref=self.invoke()
        self.assertEqual(record['mesh_sha256'],'prepared-world-geometry')
        self.assertEqual(ref['sha256'],self.obj['a3d_pattern_preparation_receipt_sha256'])

    def test_incomplete_preparation_and_false_cloth_pass_do_not_admit(self):
        for field,value in (('readiness','NEEDS_CORRECTION'),('readiness','NEEDS_CLARIFICATION'),('simulation','PASS'),('accepted',True)):
            record=copy.deepcopy(self.record);record[field]=value
            with self.subTest(field=field,value=value),self.assertRaisesRegex(StudioError,'READY preparation'):
                self.invoke(record)

    def test_old_ready_cannot_transfer_new_metric_and_contact_qualification(self):
        record=copy.deepcopy(self.record);record.pop('validation_contract')
        with self.assertRaisesRegex(StudioError,'Legacy READY'):self.invoke(record)

    def test_changed_mesh_plan_recipe_and_dossier_invalidate_readiness(self):
        with self.assertRaisesRegex(StudioError,'Prepared geometry'):self.invoke(geometry='moved')
        record=copy.deepcopy(self.record);record['recipe_sha256']='changed'
        with self.assertRaisesRegex(StudioError,'Prepared geometry'):self.invoke(record)
        atomic_json(self.root/'dossier.json',{'changed':True})
        with self.assertRaisesRegex(StudioError,'referenced artifact changed'):self.invoke()

    def test_migrated_recipe_archive_is_part_of_resumption_provenance(self):
        legacy={**self.recipe,'fitting_tacks':[]};atomic_json(self.root/'legacy.json',legacy)
        self.record['recipe_migration']={'archived_source_recipe':self.ref('legacy'),
            'source_recipe_sha256':digest(legacy),'prepared_recipe_sha256':digest(self.recipe)}
        self.invoke()
        atomic_json(self.root/'legacy.json',{'changed':True})
        with self.assertRaisesRegex(StudioError,'referenced artifact changed'):self.invoke()

    def test_new_meshing_profile_cannot_reuse_historical_ready_or_incomplete_observation(self):
        from tests.test_meshing_profile import profile
        from a3d.meshing_profile import profile_binding
        p=profile(['panel']);atomic_json(self.root/'spec.json',{'meshing_profile':p})
        self.record['preparation_spec']=self.ref('spec')
        with self.assertRaisesRegex(StudioError,'synchronized meshing'):self.invoke()
        work={'component_id':'coat','qualification':'NONE','admission':'NONE','last_checkpoint':1.,'absolute_deadline':2.}
        self.payload.update(meshing_profile=profile_binding(p),meshing_work=work)
        self.record['meshing_observation']={'status':'COMPLETED_MESH_BUILD_ONLY','profile':profile_binding(p),'work':copy.deepcopy(work)}
        self.invoke()
        self.record['meshing_observation']['status']='REFUSED_OR_INCOMPLETE_MESH_BUILD'
        with self.assertRaisesRegex(StudioError,'synchronized meshing'):self.invoke()
        self.record['meshing_observation']['status']='COMPLETED_MESH_BUILD_ONLY'
        self.payload['meshing_work']['last_checkpoint']=2.
        with self.assertRaisesRegex(StudioError,'synchronized meshing'):self.invoke()


class PreparationAdmission(Case):
    def test_new_operation_is_guarded_without_requiring_existing_blender_geometry(self):
        project=ready_project(self.root/'project',True)
        from a3d.core import ROOT,read_json
        recipe=read_json(ROOT/'templates/sewing-recipe.json')
        atomic_json(project.root/'recipe.json',recipe)
        spec={'version':1,'component_id':'garment.coat','source_ref':'synthetic-test-source',
            'regular_mesh':{'spacing_cm':2.,'min_spacing_cm':1.,'refinement_distance_cm':3.,'max_vertices':10000}}
        atomic_json(project.root/'prep.json',spec)
        args={'component_id':'garment.coat','recipe_path':'recipe.json','preparation_path':'prep.json'}
        admit_operation(project,'prepare_pattern_assembly',args)
        with self.assertRaisesRegex(StudioError,'Unexpected/missing'):
            admit_operation(project,'prepare_pattern_assembly',{**args,'accept':True})
        spec['component_id']='wrong';atomic_json(project.root/'prep.json',spec)
        with self.assertRaisesRegex(StudioError,'component mismatch'):
            admit_operation(project,'prepare_pattern_assembly',args)

    def test_legacy_migration_requires_explicit_spec_and_sourced_plan(self):
        from a3d.core import ROOT,read_json,contract
        project=ready_project(self.root/'migration',True)
        recipe=read_json(ROOT/'templates/sewing-recipe.json')
        recipe['fitting_pose']={'path':'retired-pose.json','sha256':'a'*64}
        atomic_json(project.root/'recipe.json',recipe)
        spec={'version':1,'component_id':'garment.coat','source_ref':'fixture',
            'regular_mesh':{'spacing_cm':2.,'min_spacing_cm':1.,'refinement_distance_cm':3.,'max_vertices':10000}}
        atomic_json(project.root/'prep.json',spec)
        args={'component_id':'garment.coat','recipe_path':'recipe.json','preparation_path':'prep.json'}
        with self.assertRaisesRegex(StudioError,'migrate legacy'):
            admit_operation(project,'prepare_pattern_assembly',args)
        spec['migration']={'retire_legacy_preparations':True}
        atomic_json(project.root/'prep.json',spec)
        with self.assertRaisesRegex(StudioError,'sourced assembly plan'):admit_operation(project,'prepare_pattern_assembly',args)
        plan=read_json(ROOT/'templates/pattern-assembly.json');plan['component_id']='garment.coat'
        atomic_json(project.root/'plan.json',plan)
        spec['assembly_plan']={'path':'plan.json','sha256':sha(project.root/'plan.json')}
        atomic_json(project.root/'prep.json',spec)
        admit_operation(project,'prepare_pattern_assembly',args)
        with self.assertRaisesRegex(StudioError,'migrate legacy'):
            admit_operation(project,'transition_pattern_assembly',{'component_id':'garment.coat',
                'recipe_path':'recipe.json','plan_path':'plan.json','stage':'preposition'})
        spec['migration']['change_cut']=True
        with self.assertRaises(StudioError):contract('pattern-preparation',spec)

    def test_recipe_migration_preserves_all_other_fields_without_mutating_source(self):
        raw={'component_id':'garment.coat','placements':{'original':[1,2,3]},'mesh':{'source':'exact'},
            'seams':{'seam':'permanent'},'pins':[1],'mass':{'basis':'total_kg','value':.3},
            'phases':{'mount':'unchanged'},'limits':{'original':True},'fitting_plan':{'path':'fit.json','sha256':'b'*64},
            'panel_mount':{'legacy_config':[1,2,3]},'fitting_pose':{'path':'retired.json','sha256':'c'*64}}
        witness=copy.deepcopy(raw)
        with self.assertRaisesRegex(StudioError,'explicit'):migrate_preparation_recipe(raw,{})
        spec={'migration':{'retire_legacy_preparations':True}}
        with self.assertRaisesRegex(StudioError,'sourced assembly plan'):migrate_preparation_recipe(raw,spec)
        spec['assembly_plan']={'path':'plan.json','sha256':'a'*64}
        recipe,report=migrate_preparation_recipe(raw,spec)
        self.assertEqual(raw,witness)
        self.assertEqual(recipe,{k:v for k,v in raw.items() if k not in ('panel_mount','fitting_pose')})
        self.assertEqual(report['retired_fields'],{k:raw[k] for k in ('panel_mount','fitting_pose')})
        self.assertEqual(report['source_recipe_sha256'],digest(witness))
        self.assertEqual(report['prepared_recipe_sha256'],digest(recipe))
        self.assertFalse(report['physics_validation_transferred'])


class NativeMassAndSurfaceDistance(Case):
    def test_rigid_preform_translation_cannot_hide_source_placement_budget(self):
        source=[[0,0,0],[10,0,0],[0,10,0]]
        payload={'rest_cm':source,'panels':{'source-panel':{'indices':[0,1,2]}}}
        report=_placement_displacement(payload,source,[[x+100000,y,z] for x,y,z in source],2.)
        self.assertFalse(report['within_budget'])
        self.assertEqual(report['max_cm'],100000.)
        self.assertEqual(report['pieces'],['source-panel'])
        self.assertEqual(report['source_uv_cm'],[0,0])
        self.assertTrue(_placement_displacement(payload,source,[[x+.15,y,z] for x,y,z in source],2.)['within_budget'])

    def test_external_point_coplanar_with_face_has_real_edge_clearance(self):
        # Exterior cube corner from the five-panel fixture, in Blender metres.
        measured=nearest_signed_distance_cm([-.12,-.03,0],[-.09,-.018,0],[0,0,-1])
        self.assertAlmostEqual(measured,(3**2+1.2**2)**.5)
        self.assertGreater(measured,.4)

    def test_deep_interior_sample_remains_negative(self):
        self.assertAlmostEqual(nearest_signed_distance_cm([0,0,-.0781148],[0,0,0],[0,0,1]),-7.81148)

    def test_surface_mass_is_total_scalar_and_never_implemented_with_pins(self):
        payload={'rest_cm':[[0,0,0],[10,0,0],[0,10,0]],'faces':[[0,1,2]]}
        profile={'sewing_force_per_kg':10.,'tension_stiffness':1.,'compression_stiffness':1.,'shear_stiffness':1.,'bending_stiffness':1.}
        recipe={'mass':{'basis':'areal_density_kg_m2','value':.3},'phases':{'mount':profile}}
        spec={'material_profiles':[{'id':'main','source_ref':'hypothesis','pieces':['panel'],'areal_density_kg_m2':.3}]}
        report=_material_assessment({'pieces':{'panel':{}}},recipe,spec,payload)
        self.assertFalse(report['pin_group_is_mass_distribution'])
        self.assertFalse(report['limitations'])
        self.assertAlmostEqual(report['configured_assignment']['mount']['total_mass_kg'],.0015)
        spec['mass_policy']='require_exact_surface_density'
        self.assertTrue(_material_assessment({'pieces':{'panel':{}}},recipe,spec,payload)['limitations'])

    def test_cloth_profile_binding_uses_each_phase_piece_assignment_and_keeps_visual_separate(self):
        base={'sewing_force_per_kg':10.,'tension_stiffness':1.,'compression_stiffness':1.,'shear_stiffness':1.,'bending_stiffness':1.}
        recipe={'phases':{'local':copy.deepcopy(base),'full':copy.deepcopy(base)}}
        spec={'material_profiles':[{'id':'main','source_ref':'source','pieces':['panel'],
            'areal_density_kg_m2':.3,'category':'main','cloth_profile':'phase_base','visual_material_ref':'neutral-gray'}]}
        report=_material_assessment({'pieces':{'panel':{}}},recipe,spec,None)
        self.assertFalse(report['limitations'])
        self.assertEqual(report['profile_bindings'][0]['visual_material_assignment'],'REFERENCE_ONLY_NOT_APPLIED_TO_SIMULATION')
        regional={'profiles':[{'id':'cloth'},{'id':'lining'}],'default_profile':'cloth','assignments':[],'reinforcements':[]}
        for phase in recipe['phases'].values():phase['regional_stiffness']=copy.deepcopy(regional)
        spec['material_profiles'][0]['cloth_profile']='cloth'
        self.assertFalse(_material_assessment({'pieces':{'panel':{}}},recipe,spec,None)['limitations'])
        recipe['phases']['full']['regional_stiffness']['assignments']=[{'piece':'panel','profile':'lining'}]
        report=_material_assessment({'pieces':{'panel':{}}},recipe,spec,None)
        self.assertTrue(any('phase full' in message for message in report['limitations']))
        spec['material_profiles'][0]['cloth_profile']='nonexistent'
        self.assertTrue(any('absent Cloth profile' in message for message in _material_assessment({'pieces':{'panel':{}}},recipe,spec,None)['limitations']))
