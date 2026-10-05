"""Small contract fixtures only; no Blender, Cloth or real garment proof."""
from contextlib import closing
import json
import sqlite3
from types import SimpleNamespace
from unittest.mock import patch

from a3d.core import ROOT, StudioError, atomic_json, digest, read_json, sha
from a3d.packages import build_package
from a3d.production_dossier import compile_project_dossier
from a3d.production_preparation import prepare_project_component_preparation
from a3d.garment_guide_policy import guide_generator_identity
from tests.test_core import Case
from tests.test_garment_guides import fixture as guide_fixture
from tests.test_garment_planner import example as planner_fixture
from tests.test_shoulder_surface import fixture as shoulder_fixture
from tests.support import PROVENANCE


class ProductionPreparation(Case):
    def save(self, name, value):
        atomic_json(self.root/name, value)
        return {'path': name, 'sha256': sha(self.root/name)}

    def fixture(self, register_native=True):
        data, semantics, profile = guide_fixture()
        _, geometry, _ = shoulder_fixture()
        data.update(component_id='garment.test', units='cm',
                    seams=[{'id': 'fixture-closure', 'kind': 'closure',
                            'piece_a': 'single-front', 'piece_b': 'collar',
                            'edge_a': 'attachment', 'edge_b': 'attachment', 'orientation': 'reverse'}],
                    material={'mass_kg': .3, 'tension_stiffness': 15, 'compression_stiffness': 15,
                              'shear_stiffness': 5, 'bending_stiffness': .5})
        for piece in data['pieces'].values():
            piece.update(faces=[[0, 1, 2], [0, 2, 3]], position_cm=[0., 0., 0.],
                         rotation_degrees=[0., 0., 0.])
        self.save('package-source/garment.json', data)
        polygons = ''.join('<polygon id="'+pid+'" points="'+
            ' '.join(str(p[0])+','+str(p[1]) for p in piece['vertices'])+'"/>'
            for pid, piece in data['pieces'].items())
        (self.root/'package-source/pattern.svg').write_text(
            '<svg xmlns="http://www.w3.org/2000/svg">'+polygons+'</svg>', encoding='utf-8')
        build_package(self.root/'package-source', self.root/'source.garmentpkg',
                      'test-fixture', 'garment.test', 'PATTERN_SEWN', PROVENANCE)
        package_ref = {'path': 'source.garmentpkg', 'sha256': sha(self.root/'source.garmentpkg')}
        body_ref = self.save('body.json', profile)
        geometry_ref = self.save('geometry.json', geometry)
        dossier = {'units': 'cm', 'components': {'garment.test': {'pipeline': 'PATTERN_SEWN',
            'pieces': [{'id': pid, 'grain_direction': [1, 0] if pid == 'collar' else [0, 1],
                        'seam_allowance_cm': 0, 'pattern': {'cut_quantity': 1,
                        'cut_outline_cm': piece['vertices'], 'folds': [], 'assembly_marks': []}}
                       for pid, piece in data['pieces'].items()]}}}
        dossier_ref = self.save('dossier.json', dossier)
        spec = {'version': 1, 'source_ref': dossier_ref, 'body_ref': body_ref,
            'packages': [{'component_id': 'garment.test', 'source_ref': package_ref}],
            'piece_semantics': {pid: {**row, 'layer': 'cloth'} for pid, row in semantics.items()},
            'measurement_paths': [], 'budgets': planner_fixture()['budgets'],
            'layers': {'version': 1, 'source_ref': dossier_ref, 'mode': 'ordered',
                'interaction': 'one_way_declared', 'nodes': [
                    {'id': 'body', 'kind': 'body', 'panels': [], 'colliders': ['body'], 'source_ref': body_ref},
                    {'id': 'cloth', 'kind': 'garment', 'panels': sorted(data['pieces']),
                     'colliders': [], 'source_ref': dossier_ref}], 'inside_to_outside': [['body', 'cloth']]}}
        self.save('production.json', spec)
        self.save('parameters.json', {'garment.test': {'upper_blend': 1., 'surface_sections': True,
                                                      'skin_section_heights_cm': []}})
        self.save('standard.json', read_json(ROOT/'templates/sewing-recipe.json'))
        project = SimpleNamespace(root=self.root, db=self.root/'project.sqlite3')
        with closing(sqlite3.connect(project.db)) as db, db:
            db.execute('CREATE TABLE events (id INTEGER PRIMARY KEY, kind TEXT, doc TEXT)')
            db.execute('CREATE TABLE runs (id TEXT PRIMARY KEY, doc TEXT)')
            if register_native:
                args = {'fixture': 'contract-only-not-real-Blender'}
                receipt = {'origin': 'NATIVE_DISPATCH', 'execution': 'RETURNED',
                    'operation': 'introduce_body_target', 'arguments': args, 'run_id': 'run.fixture',
                    'unit_id': 'unit.fixture', 'attempt_id': 'attempt.fixture', 'binding_sha256': 'a'*64,
                    'files': [body_ref, geometry_ref], 'result': {'profile_ref': body_ref,
                    'geometry_ref': geometry_ref, 'profile_cache_key': profile['cache_key']}}
                receipt_ref = self.save('native-receipt.json', receipt)
                event = {key: receipt[key] for key in ('run_id', 'unit_id', 'attempt_id', 'binding_sha256')}
                event['receipt'] = receipt_ref
                attempt = {'id': 'attempt.fixture', 'status': 'COMPLETED', 'receipt_event_id': 1,
                    'receipt': receipt_ref, 'operation': receipt['operation'], 'arguments': args,
                    'binding_sha256': receipt['binding_sha256']}
                run = {'units': [{'id': 'unit.fixture', 'status': 'COMPLETED', 'attempts': [attempt]}]}
                db.execute('INSERT INTO events VALUES (1, ?, ?)', ('run_native_receipt', json.dumps(event)))
                db.execute('INSERT INTO runs VALUES (?, ?)', ('run.fixture', json.dumps(run)))
        compiled = compile_project_dossier(project, 'dossier.json', 'production.json')
        return project, compiled

    def invoke(self, project, compiled, output='proposals/v1'):
        return prepare_project_component_preparation(project, compiled,
            'parameters.json', 'standard.json', output)

    def files(self):
        return {path.relative_to(self.root).as_posix(): sha(path)
                for path in self.root.rglob('*') if path.is_file()}

    def test_actual_producers_write_exact_reconstructable_inputs_without_native_mesh_or_qualification(self):
        project, compiled = self.fixture(); before = self.files(); identity = digest(compiled)
        result = self.invoke(project, compiled)
        self.assertEqual(result['status'], 'SOURCE_PREPARATION_TEMPLATES_READY')
        self.assertEqual(result['qualification'], 'NONE')
        self.assertEqual(result['placement'], 'NOT_QUALIFIED')
        self.assertEqual(result['planning_capability'],
                         {'coupled_multilayer': 'PROPOSAL_ONLY', 'native_path': 'NOT_QUALIFIED'})
        self.assertEqual(result['simulation'], 'NOT_EXECUTED')
        self.assertEqual(result['fitting'], 'NOT_EXECUTED')
        self.assertEqual(result['acceptance'], 'NOT_GRANTED')
        self.assertEqual(result['native_body_origin']['event_id'], 1)
        self.assertEqual(digest(compiled), identity)
        self.assertEqual(before, {name: sha(self.root/name) for name in before})
        self.assertEqual(set(result['artifacts']), {'guide_policy', 'guides', 'assembly_plan', 'templates', 'guide_report'})
        for ref in result['artifacts'].values():
            self.assertEqual(sha(self.root/ref['path']), ref['sha256'])
        templates = read_json(self.root/result['artifacts']['templates']['path'])
        self.assertEqual(set(templates['compiler_inputs']),
            {'assembly_plan_ref', 'guides_ref', 'production_spec_ref', 'standard_recipe_ref', 'dossier_ref'})
        self.assertEqual(templates['compiler_inputs'], result['compiler_inputs'])
        for ref in templates['compiler_inputs'].values():
            self.assertEqual(sha(self.root/ref['path']), ref['sha256'])
        self.assertEqual(templates['native_mesh_identity'], 'NOT_YET_DERIVED')
        self.assertNotIn('mapping_sha256', templates)
        self.assertEqual(len(templates['components']['garment.test']['recipe_template']['placements']), 5)

    def test_missing_arguments_paths_existing_directory_and_incomplete_compilation_refuse_before_generation(self):
        project, compiled = self.fixture()
        (self.root/'occupied').mkdir(); (self.root/'occupied/original.txt').write_text('preserve')
        variants = [(None, 'standard.json', 'new'), ('parameters.json', None, 'new'),
                    ('parameters.json', 'standard.json', None), ('../parameters.json', 'standard.json', 'new'),
                    ('parameters.json', 'standard.json', '../new'), ('parameters.json', 'standard.json', 'occupied')]
        before = self.files()
        with patch('a3d.production_preparation.prepare_project_guide_policy') as generate:
            for args in variants:
                with self.subTest(args=args), self.assertRaises(StudioError):
                    prepare_project_component_preparation(project, compiled, *args)
            incomplete = {**compiled, 'status': 'NEEDS_CLARIFICATION'}
            with self.assertRaisesRegex(StudioError, 'complete current source'):
                self.invoke(project, incomplete)
            generate.assert_not_called()
        self.assertEqual(self.files(), before)
        self.assertFalse((self.root/'proposals').exists())

    def test_files_without_canonical_native_origin_are_rejected_by_actual_validator(self):
        project, compiled = self.fixture(register_native=False); before = self.files()
        with self.assertRaisesRegex(StudioError, 'canonically registered native') as raised:
            self.invoke(project, compiled)
        self.assertEqual(raised.exception.preparation_phase, 'GUIDE_POLICY')
        self.assertEqual(raised.exception.diagnostic['qualification'], 'NONE')
        self.assertEqual(before, self.files())

    def test_changed_body_geometry_package_specification_or_receipt_is_not_rebound(self):
        for change in ('body.json', 'geometry.json', 'source.garmentpkg', 'production.json', 'native-receipt.json'):
            with self.subTest(change=change):
                project, compiled = self.fixture()
                original = (self.root/change).read_bytes()
                (self.root/change).write_bytes(original+b' ')
                before = self.files()
                with self.assertRaises(StudioError): self.invoke(project, compiled)
                self.assertEqual(before, self.files())
                (self.root/change).write_bytes(original)
                # This loop reuses fixture files; the immutable package must be new.
                (self.root/'source.garmentpkg').unlink()
                project.db.unlink()

    def test_existing_generator_refusal_keeps_message_phase_and_original_diagnostic(self):
        project, compiled = self.fixture(); before = self.files()
        error = StudioError('Source-seam budget exhausted at the declared 60 seconds')
        error.reason_category = 'source_seam_coupling'
        error.diagnostic = {'reason': 'SOURCE_SEAM_BUDGET', 'piece': 'collar'}
        with patch('a3d.production_preparation.reconstruct_guide_policy', side_effect=error):
            with self.assertRaises(StudioError) as raised: self.invoke(project, compiled)
        self.assertIs(raised.exception, error)
        self.assertEqual(str(error), 'Source-seam budget exhausted at the declared 60 seconds')
        self.assertEqual(error.preparation_phase, 'GUIDE_RECONSTRUCTION')
        self.assertEqual(error.diagnostic['piece'], 'collar')
        self.assertEqual(error.diagnostic['reason'], 'SOURCE_SEAM_BUDGET')
        self.assertEqual(error.diagnostic['fitting'], 'NOT_EXECUTED')
        self.assertEqual(before, self.files())

    def test_changed_parameters_recipe_or_code_during_generation_is_refused_before_outputs(self):
        from a3d.production_preparation import reconstruct_guide_policy as real_reconstruct
        for change in ('parameters.json', 'standard.json', 'code'):
            with self.subTest(change=change):
                project, compiled = self.fixture()
                original = (self.root/change).read_bytes() if change != 'code' else None
                def changed(*args, **kwargs):
                    result = real_reconstruct(*args, **kwargs)
                    if original is not None: (self.root/change).write_bytes(original+b' ')
                    return result
                current_code = {} if change == 'code' else guide_generator_identity()
                with patch('a3d.production_preparation.reconstruct_guide_policy', side_effect=changed),\
                        patch('a3d.production_preparation.guide_generator_identity', return_value=current_code):
                    with self.assertRaisesRegex(StudioError, 'changed') as raised: self.invoke(project, compiled)
                self.assertEqual(raised.exception.preparation_phase, 'SOURCE_RECHECK')
                self.assertFalse((self.root/'proposals').exists())
                if original is not None: (self.root/change).write_bytes(original)
                (self.root/'source.garmentpkg').unlink(); project.db.unlink()

    def test_partial_template_failure_preserves_artifacts_and_requires_fresh_output(self):
        project, compiled = self.fixture(); before = self.files()
        error = StudioError('Source guide stop is missing')
        with patch('a3d.production_preparation.prepare_component_templates', side_effect=error):
            with self.assertRaises(StudioError) as raised: self.invoke(project, compiled)
        self.assertIs(raised.exception, error)
        self.assertEqual(error.preparation_phase, 'COMPONENT_TEMPLATES')
        self.assertEqual(before, {name: sha(self.root/name) for name in before})
        self.assertEqual({p.name for p in (self.root/'proposals/v1').iterdir()},
                         {'guide-policy.json', 'guides.json', 'assembly-plan.json'})
        with self.assertRaisesRegex(StudioError, 'fresh directory'): self.invoke(project, compiled)

    def test_partial_guides_retain_actual_diagnostics_and_artifact_refs_on_refusal(self):
        project, compiled = self.fixture()
        with patch('a3d.garment_guides.specialised_volume_frames',
                   side_effect=StudioError('Declared fixture head landmarks are unavailable')):
            with self.assertRaisesRegex(StudioError, 'requires complete measured guides') as raised:
                self.invoke(project, compiled)
        error = raised.exception
        self.assertEqual(error.preparation_phase, 'COMPONENT_TEMPLATES')
        diagnostics = error.diagnostic['guide_diagnostics']['garment.test']
        self.assertEqual(diagnostics['status'], 'PARTIAL_GUIDES')
        self.assertEqual(diagnostics['diagnostics'][0]['message'],
                         'Declared fixture head landmarks are unavailable')
        self.assertTrue(diagnostics['pending_pieces'])
        self.assertEqual(set(error.diagnostic['partial_artifacts']),
                         {'guide_policy', 'guides', 'assembly_plan'})
        for ref in error.diagnostic['partial_artifacts'].values():
            self.assertEqual(sha(self.root/ref['path']), ref['sha256'])
        self.assertEqual(error.diagnostic['qualification'], 'NONE')
        self.assertFalse((self.root/'proposals/v1/component-templates.json').exists())

    def test_declared_source_seam_budgets_and_recipe_reach_existing_producer_unchanged(self):
        project, compiled = self.fixture()
        budgets = {'max_source_points': 20000, 'max_source_triangles': 20000,
                   'max_controls': 70000, 'max_triangles': 131072, 'max_seconds': 60.}
        parameters = read_json(self.root/'parameters.json')
        parameters['garment.test']['source_seam_coupling'] = {
            'pieces': ['single-front', 'collar'], 'subdivisions': 2, 'budgets': budgets,
            'recipe_ref': {'path': 'standard.json', 'sha256': sha(self.root/'standard.json')}}
        self.save('parameters.json', parameters); before = self.files()
        def refuse_at_existing_producer(*args, **kwargs):
            self.assertEqual(args[5]['components']['garment.test']['source_seam_coupling']['budgets'], budgets)
            self.assertEqual(kwargs['source_seam_recipes'], {'garment.test': read_json(self.root/'standard.json')})
            raise StudioError('Observed fixture producer stop; no coupled guide is qualified')
        with patch('a3d.production_preparation.reconstruct_guide_policy', side_effect=refuse_at_existing_producer):
            with self.assertRaisesRegex(StudioError, 'Observed fixture producer stop'):
                self.invoke(project, compiled)
        self.assertEqual(before, self.files())

    def test_actual_guide_policy_contract_rejects_over_budget_before_reconstruction(self):
        project, compiled = self.fixture(); parameters = read_json(self.root/'parameters.json')
        parameters['garment.test']['source_seam_coupling'] = {
            'pieces': ['single-front', 'collar'], 'subdivisions': 2,
            'budgets': {'max_source_points': 20000, 'max_source_triangles': 20000,
                        'max_controls': 70000, 'max_triangles': 131072, 'max_seconds': 121.},
            'recipe_ref': {'path': 'standard.json', 'sha256': sha(self.root/'standard.json')}}
        self.save('parameters.json', parameters); before = self.files()
        with patch('a3d.production_preparation.reconstruct_guide_policy') as reconstruct:
            with self.assertRaisesRegex(StudioError, 'outside bounds'):
                self.invoke(project, compiled)
            reconstruct.assert_not_called()
        self.assertEqual(before, self.files())


if __name__ == '__main__':
    import unittest
    unittest.main()
