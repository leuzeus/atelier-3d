import copy
from types import SimpleNamespace
from unittest.mock import Mock,patch

from a3d.core import StudioError,atomic_json,digest
from blender.textile_executor import bind_component_preparations,require_native_textile_program_admission
from tests.test_core import Case


class NativeTextileBinding(Case):
    def test_group_admission_checks_the_actual_body_before_any_native_copy(self):
        project=SimpleNamespace(root=self.root)
        body_ref={'path':'body.json','sha256':'a'*64}
        admission={'purpose':'GARMENT_CANDIDATE','body_ref':body_ref,'production_qualification':'NOT_GRANTED'}
        spec={'purpose':'GARMENT_CANDIDATE'}
        body=SimpleNamespace(name='reviewed-body')
        objects=SimpleNamespace(get=lambda name:body if name==body.name else None)
        bpy=SimpleNamespace(data=SimpleNamespace(objects=objects),context=SimpleNamespace(scene=SimpleNamespace(objects=objects)))
        actual={'object':body.name,'visible':True,'collision_enabled':True,'geometry_sha256':'b'*64,
            'dimensions_cm':[30.,20.,180.],'outer_thickness_cm':.3,'inner_thickness_cm':.3}
        snapshot={key:actual[key] for key in ('object','geometry_sha256','dimensions_cm','outer_thickness_cm','inner_thickness_cm')}
        compiled={'groups':[{'group':{'body_colliders':[body.name]},'recipe':{'colliders':[{**snapshot,'role':'mannequin'}]}}]}
        for change in ('none','missing','multiple','policy','disabled','stale-body'):
            source=copy.deepcopy(compiled);observed=copy.deepcopy(actual)
            if change=='missing':source['groups'][0]['group']['body_colliders']=[]
            elif change=='multiple':source['groups'][0]['group']['body_colliders'].append('other-body')
            elif change=='policy':observed['outer_thickness_cm']=.6
            elif change=='disabled':observed['collision_enabled']=False
            native=Mock(side_effect=StudioError('NATIVE_BODY_STALE')) if change=='stale-body' else Mock(return_value={'live_body_checked':True})
            with self.subTest(change=change),patch.dict('sys.modules',{'bpy':bpy}),\
                    patch('blender.textile_executor.require_textile_program_admission',return_value=copy.deepcopy(admission)),\
                    patch('blender.physics_admission.require_native_fit_body',native),\
                    patch('blender.sewing.collider_info',return_value=observed):
                if change=='none':
                    result=require_native_textile_program_admission(project,spec,source)
                    self.assertTrue(result['native_body']['live_body_checked'])
                    native.assert_called_once_with(project,body_ref,body)
                else:
                    with self.assertRaises(StudioError):require_native_textile_program_admission(project,spec,source)
                    if change in ('missing','multiple'):native.assert_not_called()

    def fixture(self):
        inputs={key:{'path':key+'.json','sha256':'a'*64} for key in
            ('dossier_ref','production_spec_ref','assembly_plan_ref','guides_ref','standard_recipe_ref')}
        profile_ref={'path':'profile.json','sha256':'b'*64};geometry_ref={'path':'geometry.json','sha256':'c'*64}
        geometry={'vertices_cm':[[0.,0.,0.],[1.,0.,0.],[0.,1.,0.]],'faces':[[0,1,2]],'face_sets':[1],
            'source_sha256':'d'*64,'pose_sha256':'e'*64}
        profile={key:geometry[key] for key in ('source_sha256','pose_sha256')}
        profile.update(geometry_sha256=digest([geometry['vertices_cm'],geometry['faces']]),cache_key='f'*64)
        assembly={'source':'approved deterministic plan'}
        templates={'status':'SOURCE_PREPARATION_TEMPLATES_READY','compiler_inputs':inputs,'body_ref':profile_ref,
            'components':{'source.panel':{'plan_fields':{'quality':{'max_stretch':1.1}}}}}
        templates['prepared_sha256']=digest(templates)
        records={row['path']:{} for row in inputs.values()}
        records.update({inputs['assembly_plan_ref']['path']:assembly,inputs['production_spec_ref']['path']:{'packages':[]},
            profile_ref['path']:profile,geometry_ref['path']:geometry})
        bpy=SimpleNamespace(data=SimpleNamespace(objects=SimpleNamespace(get=Mock())))
        return templates,records,assembly,geometry_ref,bpy

    def invoke(self,templates,records,assembly,geometry_ref,bpy,reconstructed,project=None):
        atomic_json(self.root/'templates.json',templates)
        with patch.dict('sys.modules',{'bpy':bpy}),\
                patch('blender.textile_executor.verified',side_effect=lambda project,ref:copy.deepcopy(records[ref['path']])),\
                patch('a3d.production_dossier.compile_project_dossier',return_value={'assembly_spec':{}}),\
                patch('a3d.garment_planner.plan_assembly',return_value=assembly),\
                patch('a3d.textile_executor.prepare_component_templates',return_value=reconstructed):
            return bind_component_preparations(project or SimpleNamespace(root=self.root),'templates.json','body',geometry_ref,'bound')

    def test_verified_binding_creates_fresh_output_and_preserves_interrupted_boundary(self):
        templates,records,assembly,geometry_ref,bpy=self.fixture()
        profile=records[templates['body_ref']['path']];geometry=records[geometry_ref['path']]
        obj=SimpleNamespace(type='MESH',get=lambda key:profile['cache_key'])
        bpy.data.objects.get.return_value=obj;bpy.context=SimpleNamespace(evaluated_depsgraph_get=lambda:None)
        project=SimpleNamespace(root=self.root,state=Mock(side_effect=StudioError('STATE_READ_SENTINEL')))
        actual={key:geometry[key] for key in ('vertices_cm','faces','face_sets')}
        with patch('blender.body_target.evaluated_mesh',return_value=(actual,None)),\
                patch('blender.sewing.collider_info',return_value={'visible':True,'collision_enabled':True,'scale':[1.,1.,1.]}):
            with self.assertRaisesRegex(StudioError,'STATE_READ_SENTINEL'):
                self.invoke(templates,records,assembly,geometry_ref,bpy,copy.deepcopy(templates),project)
            self.assertTrue((self.root/'bound').is_dir())
            with self.assertRaisesRegex(StudioError,'preserve it and choose a fresh'):
                self.invoke(templates,records,assembly,geometry_ref,bpy,copy.deepcopy(templates),project)
        project.state.assert_called_once()

    def test_new_geometry_reference_cannot_reuse_old_body_profile_or_cache(self):
        templates,records,assembly,geometry_ref,bpy=self.fixture()
        records[geometry_ref['path']]['vertices_cm'][0][2]=1.
        with self.assertRaisesRegex(StudioError,'geometry or pose differs'):
            self.invoke(templates,records,assembly,geometry_ref,bpy,copy.deepcopy(templates))
        bpy.data.objects.get.assert_not_called()

    def test_self_signed_policy_change_is_rejected_by_source_reconstruction(self):
        templates,records,assembly,geometry_ref,bpy=self.fixture();trusted=copy.deepcopy(templates)
        templates['components']['source.panel']['plan_fields']['quality']['max_stretch']=2.
        templates['prepared_sha256']=digest({k:v for k,v in templates.items() if k!='prepared_sha256'})
        with self.assertRaisesRegex(StudioError,'differs from reconstruction'):
            self.invoke(templates,records,assembly,geometry_ref,bpy,trusted)
        bpy.data.objects.get.assert_not_called()
