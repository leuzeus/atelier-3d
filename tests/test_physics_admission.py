import copy
import unittest
from unittest.mock import patch

from a3d.core import StudioError, atomic_json, digest, sha
from a3d.physics_admission import require_recipe_fit_intent
from tests.test_sewing import sources
from tests.test_core import Case
from tests.support import ready_project


class PhysicsAdmission(unittest.TestCase):
    def body_recipe(self):
        _, recipe = sources()
        recipe['colliders'] = [{'object': 'measured.body', 'role': 'mannequin',
                               'dimensions_cm': [10., 10., 180.], 'geometry_sha256': 'd'*64,
                               'outer_thickness_cm': .3, 'inner_thickness_cm': .3, 'tolerance_cm': .001}]
        return recipe

    def test_body_physics_without_classification_is_refused_before_native_lookup(self):
        recipe = self.body_recipe()
        with patch('a3d.native_evidence.checked_reference') as lookup:
            with self.assertRaisesRegex(StudioError, 'reviewed fit_context'):
                require_recipe_fit_intent(None, recipe)
            lookup.assert_not_called()
        recipe['physics_purpose'] = 'GARMENT_CANDIDATE'
        with self.assertRaises(StudioError): require_recipe_fit_intent(None, recipe)

    def test_collider_free_assembly_and_explicit_body_test_have_limited_scope(self):
        _, recipe = sources()
        recipe['colliders'] = []
        before = digest(recipe)
        result = require_recipe_fit_intent(None, recipe)
        self.assertEqual(result['admission'], 'SOURCE_ASSEMBLY_WITHOUT_BODY')
        self.assertFalse(result['accepted'])
        self.assertEqual(digest(recipe), before)
        recipe = self.body_recipe(); recipe['physics_purpose'] = 'TEST_ONLY'
        result = require_recipe_fit_intent(None, recipe)
        self.assertEqual(result['fitting'], 'NOT_QUALIFIED')
        self.assertEqual(result['product_acceptance'], 'NOT_GRANTED')

    def test_production_context_checks_exact_refs_and_owned_paths(self):
        from types import SimpleNamespace
        recipe = self.body_recipe(); recipe['physics_purpose'] = 'GARMENT_CANDIDATE'
        package = {'path': 'package.garmentpkg', 'sha256': 'e'*64}
        project = SimpleNamespace(root='portable.unit.only',
            state=lambda: {'components': {recipe['component_id']: {'package': package}}})
        recipe['fit_context'] = {'compiled_dossier_ref': {'path': 'compiled.json', 'sha256': 'a'*64},
                                 'fit_profile_ref': {'path': 'fit.json', 'sha256': 'b'*64}}
        report = {'checks': [{'component_id': recipe['component_id']}]}
        specification = {'body_ref': {'path': 'body.json', 'sha256': 'c'*64}}
        compiled = {'components': [{'id': recipe['component_id'], 'pipeline': 'PATTERN_SEWN',
                                    'package_source_ref': copy.deepcopy(package)}]}
        with patch('a3d.native_evidence.checked_reference') as checked, \
                patch('a3d.garment_fit.require_fit_intent', return_value=report), \
                patch('a3d.physics_admission.inside', side_effect=lambda root,path:path), \
                patch('a3d.physics_admission.read_json', side_effect=lambda path:compiled if path=='compiled.json' else specification):
            result = require_recipe_fit_intent(project, recipe)
            self.assertEqual(checked.call_count, 3)
            self.assertEqual(result['body_ref'], specification['body_ref'])
            self.assertEqual(result['admission'], 'EXPLORATORY_PHYSICS_ONLY')
            report['checks'][0]['component_id'] = 'another.component'
            with self.assertRaisesRegex(StudioError, 'no measured path'):
                require_recipe_fit_intent(project, recipe)
            report['checks'][0]['component_id'] = recipe['component_id']
            package['sha256'] = 'f'*64
            with self.assertRaisesRegex(StudioError, 'executing canonical source package'):
                require_recipe_fit_intent(project, recipe)
        with patch('a3d.native_evidence.checked_reference', side_effect=StudioError('Source changed')):
            with self.assertRaisesRegex(StudioError, 'Source changed'):
                require_recipe_fit_intent(None, recipe)

    def test_test_scope_cannot_carry_production_intent_and_duplicate_bodies_refuse(self):
        recipe = self.body_recipe(); recipe['physics_purpose'] = 'TEST_ONLY'
        recipe['fit_context'] = {'compiled_dossier_ref': {'path': 'compiled.json', 'sha256': 'a'*64},
                                 'fit_profile_ref': {'path': 'fit.json', 'sha256': 'b'*64}}
        with self.assertRaisesRegex(StudioError, 'cannot carry'): require_recipe_fit_intent(None, recipe)
        recipe['physics_purpose'] = 'GARMENT_CANDIDATE'
        recipe['colliders'].append(copy.deepcopy(recipe['colliders'][0]))
        with self.assertRaisesRegex(StudioError, 'one exact'): require_recipe_fit_intent(None, recipe)

    def test_measured_body_relabeling_cannot_skip_the_native_boundary(self):
        from blender.physics_admission import require_native_recipe_fit_intent
        from types import SimpleNamespace
        recipe = self.body_recipe(); recipe['physics_purpose'] = 'GARMENT_CANDIDATE'
        recipe['colliders'][0]['role'] = 'support'
        with self.assertRaises(StudioError): require_recipe_fit_intent(None, recipe)
        body = SimpleNamespace(name='measured.body', get=lambda key:'actual.cache' if key=='a3d_profile_cache_key' else None)
        with patch('blender.physics_admission.require_recipe_fit_intent') as admission:
            with self.assertRaisesRegex(StudioError, 'cannot be relabeled'):
                require_native_recipe_fit_intent(None, recipe, [body])
            admission.assert_not_called()


class PhysicsEntryAdmission(Case):
    def test_missing_ease_refuses_public_physics_before_canonical_mutation(self):
        from a3d.guard import admit_operation
        from a3d.lifecycle import simulation_plan
        project = ready_project(self.root, True)
        recipe = PhysicsAdmission().body_recipe()
        atomic_json(project.root/'recipe.json', recipe)
        args = {'component_id':recipe['component_id'], 'recipe_path':'recipe.json'}
        plan = {'component_id':recipe['component_id'], 'type':'cloth', 'frame_start':1,
                'frame_end':recipe['phases']['mount']['frames'], 'quality':recipe['phases']['mount']['quality'],
                'collision_components':[], 'baked':False, 'max_frames':2400,
                'sewing_recipe':'recipe.json', 'phase':'mount'}
        atomic_json(project.root/'simulation.json', plan)
        before, database = project.state(), sha(project.db)
        with self.assertRaisesRegex(StudioError, 'reviewed fit_context'):
            admit_operation(project, 'simulate_sewn', dict(args, phase='mount', scope='local'))
        with self.assertRaisesRegex(StudioError, 'reviewed fit_context'):
            admit_operation(project, 'freeze_sewn', args)
        with self.assertRaisesRegex(StudioError, 'reviewed fit_context'):
            simulation_plan(project, before, 'simulation.json', [recipe['component_id']])
        self.assertEqual(project.state(), before)
        self.assertEqual(sha(project.db), database)

    def test_test_only_trial_cannot_freeze_through_public_operation(self):
        from a3d.guard import admit_operation
        project = ready_project(self.root, True)
        recipe = PhysicsAdmission().body_recipe(); recipe['physics_purpose'] = 'TEST_ONLY'
        atomic_json(project.root/'recipe.json', recipe)
        before = sha(project.db)
        admit_operation(project, 'simulate_sewn', {'component_id':recipe['component_id'],
                        'recipe_path':'recipe.json', 'phase':'mount', 'scope':'local'})
        with self.assertRaisesRegex(StudioError, 'TEST_ONLY'):
            admit_operation(project, 'freeze_sewn', {'component_id':recipe['component_id'], 'recipe_path':'recipe.json'})
        self.assertEqual(sha(project.db), before)


if __name__ == '__main__': unittest.main()
