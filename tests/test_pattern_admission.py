import copy
from types import SimpleNamespace
from unittest.mock import patch

from a3d.core import ROOT, StudioError, atomic_json, digest, read_json, sha
from a3d.guard import admit_operation, code_for, parse_code
from tests.support import ready_project
from tests.test_core import Case
from tests.test_pattern_assembly import example


class PatternAdmission(Case):
    def prepare(self):
        project = ready_project(self.root, True)
        _, plan = example()
        plan['component_id'] = 'garment.coat'
        atomic_json(self.root / 'plan.json', plan)
        atomic_json(self.root / 'recipe.json', read_json(ROOT / 'templates/sewing-recipe.json'))
        args = {'component_id':'garment.coat','recipe_path':'recipe.json',
                'plan_path':'plan.json','stage':'preposition'}
        return project, args

    def test_native_code_and_stage_contract(self):
        project, args = self.prepare()
        admit_operation(project,'transition_pattern_assembly',args)
        code = code_for(str(project.root),'transition_pattern_assembly',args)
        self.assertEqual(parse_code(code)['arguments'],args)
        with self.assertRaisesRegex(StudioError,'Unknown pattern assembly stage'):
            admit_operation(project,'transition_pattern_assembly',{**args,'stage':'approve'})
        with self.assertRaises(StudioError):
            admit_operation(project,'transition_pattern_assembly',{**args,'force':True})

    def test_nominal_path_rejects_preparation_stack_without_touching_project(self):
        project, args = self.prepare()
        recipe = read_json(self.root/'recipe.json')
        recipe['experimental_prefit'] = {'enabled':True,'iterations':10,'max_displacement_cm':1,
            'seam_weight':1,'edge_weight':1,'anchor_weight':1}
        atomic_json(self.root/'recipe.json',recipe)
        state = digest(project.state())
        with self.assertRaises(StudioError):
            admit_operation(project,'transition_pattern_assembly',args)
        self.assertEqual(digest(project.state()),state)

    def test_new_stage_cannot_bypass_pending_recovery(self):
        project, args = self.prepare()
        with project.transaction() as db:
            state = project.state(db)
            state['pending_blender_operation'] = {'operation':'transition_pattern_assembly','status':'failed'}
            project.save(db,state,'test_pending',{})
        with self.assertRaisesRegex(StudioError,'recover|checkpoint|pending'):
            admit_operation(project,'transition_pattern_assembly',args)

    def test_reprise_binds_geometry_plan_map_and_recipe(self):
        from blender.pattern_assembly import current_receipt
        project = SimpleNamespace(root=self.root)
        payload = {'component_id':'coat','package_sha256':'source'}
        recipe = {'fixture':1}
        atomic_json(self.root/'mesh.json',{'immutable':True})
        map_ref = {'path':'mesh.json','sha256':sha(self.root/'mesh.json')}
        plan_ref = {'path':'plan.json','sha256':'plan'}
        record = {'component_id':'coat','package_sha256':'source','recipe_sha256':digest(recipe),
            'plan':plan_ref,'derived_mesh':map_ref,'mesh_sha256':'mesh','accepted':False}
        atomic_json(self.root/'receipt.json',record)
        obj = {'a3d_pattern_assembly_receipt':'receipt.json',
               'a3d_pattern_assembly_receipt_sha256':sha(self.root/'receipt.json'),
               'a3d_sewing_mesh_sha256':map_ref['sha256']}
        with patch('blender.pattern_assembly.mesh_digest',return_value='mesh'):
            current_receipt(project,obj,payload,recipe,plan_ref)
            for key in ('plan','recipe','payload'):
                values = {'plan':plan_ref,'recipe':recipe,'payload':payload}
                values[key] = {**values[key],'changed':True}
                if key=='payload':values[key]['package_sha256']='stale'
                with self.subTest(key=key),self.assertRaises(StudioError):
                    current_receipt(project,obj,values['payload'],values['recipe'],values['plan'])
            atomic_json(self.root/'mesh.json',{'immutable':False})
            with self.assertRaises(StudioError):
                current_receipt(project,obj,payload,recipe,plan_ref)
