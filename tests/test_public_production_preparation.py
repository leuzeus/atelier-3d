"""Public compile compatibility and explicit initial preparation admission."""
import itertools
import unittest
from unittest.mock import patch

from a3d.core import StudioError
from a3d.tools import TOOLS, compile_dossier


class PublicProductionPreparationTests(unittest.TestCase):
    def test_compile_only_does_not_prepare_or_grant_fit(self):
        compiled = {'status': 'READY_TO_PLAN'}
        with patch('a3d.tools.Project') as project, patch(
                'a3d.production_dossier.compile_project_dossier', return_value=compiled) as compiler:
            result = compile_dossier('project', 'dossier.json', 'specification.json')
        compiler.assert_called_once_with(project.return_value, 'dossier.json', 'specification.json')
        self.assertEqual(result['compilation'], compiled)
        self.assertNotIn('component_preparation', result)
        self.assertEqual(result['fit_preflight']['status'], 'FIT_METADATA_REQUIRED')
        self.assertEqual(result['qualification'], 'NONE')
        self.assertEqual(result['fitting'], 'NOT_EXECUTED')

    def test_all_partial_preparation_trios_refused_before_project_open(self):
        keys = ('preparation_parameters_path', 'standard_recipe_path', 'preparation_output_dir')
        for count in (1, 2):
            for chosen in itertools.combinations(keys, count):
                with self.subTest(chosen=chosen), patch('a3d.tools.Project') as project:
                    with self.assertRaisesRegex(StudioError, 'requires explicit parameters'):
                        compile_dossier('project', 'dossier.json', 'specification.json',
                                        **{key: key + '.json' for key in chosen})
                    project.assert_not_called()

    def test_initial_preparation_and_existing_guide_measurements_cannot_mix(self):
        for key in ('measurement_guides_path', 'measurement_mesh_refs', 'measurement_guide_policy_path'):
            with self.subTest(key=key), patch('a3d.tools.Project') as project:
                with self.assertRaisesRegex(StudioError, 'cannot be mixed'):
                    compile_dossier('project', 'dossier.json', 'specification.json',
                                    preparation_parameters_path='parameters.json', standard_recipe_path='recipe.json',
                                    preparation_output_dir='new-preparation', **{key: {} if key.endswith('refs') else 'guides.json'})
                project.assert_not_called()

    def test_public_descriptor_declares_optional_preparation_side_effects(self):
        descriptor = TOOLS['studio_compile_production_dossier']['descriptor']
        self.assertFalse(descriptor['annotations']['readOnlyHint'])
        self.assertFalse(descriptor['annotations']['destructiveHint'])
        schema = descriptor['inputSchema']
        self.assertEqual(schema['required'], ['project_root', 'dossier_path', 'specification_path'])
        self.assertFalse(schema['additionalProperties'])
        for key in ('preparation_parameters_path', 'standard_recipe_path', 'preparation_output_dir'):
            self.assertEqual(schema['properties'][key], {'type': 'string', 'minLength': 1})

    def test_preparation_uses_exact_compilation_and_declared_inputs(self):
        compiled = {'status': 'READY_TO_PLAN'}
        preparation = {'status': 'PREPARATION_TEMPLATES_PREPARED', 'qualification': 'NONE'}
        with patch('a3d.tools.Project') as project, patch(
                'a3d.production_dossier.compile_project_dossier', return_value=compiled), patch(
                'a3d.production_preparation.prepare_project_component_preparation', return_value=preparation) as prepare:
            result = compile_dossier('project', 'dossier.json', 'specification.json',
                                    preparation_parameters_path='parameters.json', standard_recipe_path='recipe.json',
                                    preparation_output_dir='new-preparation')
        prepare.assert_called_once_with(project.return_value, compiled, 'parameters.json', 'recipe.json', 'new-preparation')
        self.assertEqual(result['component_preparation'], preparation)
        self.assertEqual(result['status'], 'READY_TO_PLAN')
        self.assertEqual(result['fit_preflight']['acceptance'], 'NOT_GRANTED')

    def test_generator_refusal_keeps_original_message(self):
        with patch('a3d.tools.Project'), patch(
                'a3d.production_dossier.compile_project_dossier', return_value={'status': 'READY_TO_PLAN'}), patch(
                'a3d.production_preparation.prepare_project_component_preparation', side_effect=StudioError('Measured col budget exhausted')):
            with self.assertRaisesRegex(StudioError, '^Measured col budget exhausted$'):
                compile_dossier('project', 'dossier.json', 'specification.json',
                                preparation_parameters_path='parameters.json', standard_recipe_path='recipe.json',
                                preparation_output_dir='new-preparation')

    def test_mcp_preserves_original_refusal_and_reports_known_preparation_phase(self):
        from a3d.server import Server
        error = StudioError('Source-seam budget exhausted')
        error.preparation_phase = 'GUIDE_RECONSTRUCTION'
        error.diagnostic = {'reason': 'SOURCE_SEAM_BUDGET', 'qualification': 'NONE',
                            'fitting': 'NOT_EXECUTED', 'acceptance': 'NOT_GRANTED'}
        server = Server()
        server.handle({'jsonrpc': '2.0', 'id': 1, 'method': 'initialize'})
        server.handle({'jsonrpc': '2.0', 'method': 'notifications/initialized'})
        with patch('a3d.server.call', side_effect=error):
            response = server.handle({'jsonrpc': '2.0', 'id': 2, 'method': 'tools/call',
                'params': {'name': 'studio_compile_production_dossier', 'arguments': {}}})
        result = response['result']
        self.assertTrue(result['isError'])
        self.assertEqual(result['content'], [{'type': 'text', 'text': str(error)}])
        self.assertEqual(result['structuredContent'], {'error': str(error),
            'preparation_phase': error.preparation_phase, 'diagnostic': error.diagnostic})


if __name__ == '__main__':
    unittest.main()
