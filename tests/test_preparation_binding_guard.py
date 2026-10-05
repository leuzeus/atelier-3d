"""Real preparation admission on small canonical-shaped contract fixtures.

Only the cutting-board reader is replaced in admission tests. No Blender or
real garment scene is executed, and fixture receipts grant no product proof.
"""
import copy
from unittest.mock import Mock, patch

from a3d.core import ROOT, StudioError, atomic_json, digest, read_json, sha
from a3d.guard import admit_operation, code_for, parse_code
from a3d.production_preparation import prepare_project_component_preparation
from a3d.runs import _unit_runtime
from tests.test_core import Case
from tests import test_production_preparation as preparation_fixtures


class PreparationBindingGuard(Case):
    # Reuse fixture builders without inheriting their unrelated test methods.
    save = preparation_fixtures.ProductionPreparation.save
    fixture = preparation_fixtures.ProductionPreparation.fixture
    files = preparation_fixtures.ProductionPreparation.files

    def setUp(self):
        super().setUp()
        self.project, compilation = self.fixture()
        self.prepared = prepare_project_component_preparation(self.project, compilation,
            'parameters.json', 'standard.json', 'portable-proposals/v1')
        package_ref = next(row['package_source_ref'] for row in compilation['components']
                           if row['id'] == 'garment.test')
        self.state = {'stage': 'RECONSTRUCTING', 'pending_blender_operation': None,
                      'components': {'garment.test': {'stage': 'PACKAGED',
                          'route': {'selected': 'PATTERN_SEWN'}, 'package': package_ref}}}
        self.project.state = lambda: copy.deepcopy(self.state)
        self.project.ready = Mock(return_value=(self.state, self.state['components']['garment.test']))
        self.arguments = {'templates_path': self.prepared['artifacts']['templates']['path'],
            'body_object': 'body', 'body_geometry_ref': self.prepared['geometry_ref'],
            'output_directory': 'native-bindings/v1',
            'policy_path': self.prepared['artifacts']['guide_policy']['path']}

    def admit(self, arguments=None):
        with patch('a3d.guard.require_board') as board:
            result = admit_operation(self.project, 'bind_component_preparations',
                                     self.arguments if arguments is None else arguments)
        return result, board

    def test_real_inputs_admit_read_only_and_prepare_exact_controlled_code_without_execution(self):
        before = self.files()
        result, board = self.admit()
        self.assertIsNone(result)
        board.assert_called_once_with(self.project, self.state)
        self.project.ready.assert_called_once_with('garment.test')
        code = code_for(str(self.root), 'bind_component_preparations', self.arguments)
        self.assertEqual(parse_code(code), {'project_root': str(self.root),
            'operation': 'bind_component_preparations', 'arguments': self.arguments})
        self.assertIn(repr(str(ROOT/'blender/bootstrap.py')), code)
        self.assertIn("['dispatch_current']", code)
        with self.assertRaisesRegex(StudioError, 'Raw Blender code is not admitted'):
            parse_code(code+'\n# altered operation\n')
        self.assertEqual(before, self.files())
        self.assertFalse((self.root/'native-bindings').exists())

    def test_missing_or_unexpected_arguments_refuse_before_board_and_leave_sources_unchanged(self):
        variants = [{key: value for key, value in self.arguments.items() if key != missing}
                    for missing in self.arguments]
        variants.append({**self.arguments, 'accept': True})
        before = self.files()
        for arguments in variants:
            with self.subTest(keys=sorted(arguments)), patch('a3d.guard.require_board') as board:
                with self.assertRaisesRegex(StudioError, 'Unexpected/missing'):
                    admit_operation(self.project, 'bind_component_preparations', arguments)
                board.assert_not_called()
        self.project.ready.assert_not_called()
        self.assertEqual(before, self.files())

    def test_wrong_stage_or_pending_operation_refuses_without_output_or_component_admission(self):
        before = self.files()
        for state in ({**self.state, 'stage': 'COMPLETE'},
                      {**self.state, 'pending_blender_operation': {'id': 'interrupted-fixture'}}):
            self.project.state = lambda: copy.deepcopy(state)
            with self.subTest(state=state), self.assertRaises(StudioError): self.admit()
        self.project.ready.assert_not_called()
        self.assertEqual(before, self.files())
        self.assertFalse((self.root/'native-bindings').exists())

    def test_output_must_be_new_inside_project_and_existing_witness_is_preserved(self):
        (self.root/'occupied').mkdir()
        (self.root/'occupied/original.txt').write_text('must remain unchanged', encoding='utf-8')
        before = self.files()
        for directory in ('occupied', '../outside', 'C:/outside', ''):
            with self.subTest(directory=directory), self.assertRaises(StudioError):
                self.admit({**self.arguments, 'output_directory': directory})
        self.project.ready.assert_not_called()
        self.assertEqual(before, self.files())

    def test_changed_compiler_input_bytes_refuse_before_ready_without_mutating_remaining_inputs(self):
        templates = read_json(self.root/self.arguments['templates_path'])
        for name, ref in templates['compiler_inputs'].items():
            original = (self.root/ref['path']).read_bytes()
            (self.root/ref['path']).write_bytes(original+b' ')
            before = self.files()
            with self.subTest(name=name), self.assertRaisesRegex(StudioError, 'input changed'):
                self.admit()
            self.assertEqual(before, self.files())
            (self.root/ref['path']).write_bytes(original)
        self.project.ready.assert_not_called()

    def test_changed_package_or_measured_profile_is_rejected_by_actual_source_recompilation(self):
        for path in ('source.garmentpkg', 'body.json'):
            original = (self.root/path).read_bytes()
            (self.root/path).write_bytes(original+b' ')
            before = self.files()
            with self.subTest(path=path), self.assertRaisesRegex(StudioError, 'Production source hash changed'):
                self.admit()
            self.assertEqual(before, self.files())
            (self.root/path).write_bytes(original)
        self.project.ready.assert_not_called()

    def test_geometry_changed_bytes_bad_hash_or_other_valid_reference_cannot_replace_native_geometry(self):
        ref = self.arguments['body_geometry_ref']; original = (self.root/ref['path']).read_bytes()
        (self.root/ref['path']).write_bytes(original+b' ')
        before = self.files()
        with self.assertRaisesRegex(StudioError, 'input changed'): self.admit()
        self.assertEqual(before, self.files()); (self.root/ref['path']).write_bytes(original)
        alternate = self.save('other-geometry.json', read_json(self.root/ref['path']))
        for value in ({**ref, 'sha256': 'f'*64}, alternate, {'path': ref['path']},
                      {'path': '../geometry.json', 'sha256': ref['sha256']}):
            before = self.files()
            with self.subTest(value=value), self.assertRaises(StudioError):
                self.admit({**self.arguments, 'body_geometry_ref': value})
            self.assertEqual(before, self.files())
        self.project.ready.assert_not_called()

    def test_policy_bound_to_wrong_compilation_profile_or_geometry_is_refused_read_only(self):
        path = self.root/self.arguments['policy_path']; original = path.read_bytes()
        for key in ('compiled_sha256', 'body_ref', 'geometry_ref'):
            policy = read_json(path)
            if key == 'compiled_sha256': policy[key] = 'f'*64
            else: policy[key] = {**policy[key], 'sha256': 'f'*64}
            atomic_json(path, policy); before = self.files()
            with self.subTest(key=key), self.assertRaisesRegex(StudioError, 'another current source or native body'):
                self.admit()
            self.assertEqual(before, self.files()); path.write_bytes(original)
        self.project.ready.assert_not_called()

    def test_changed_template_digest_body_or_inventory_cannot_self_admit(self):
        path = self.root/self.arguments['templates_path']; original = path.read_bytes()
        for change in ('digest', 'body', 'missing-component', 'extra-component', 'compiler-inputs'):
            templates = read_json(path)
            if change == 'digest': templates['prepared_sha256'] = 'f'*64
            elif change == 'body': templates['body_ref']['sha256'] = 'f'*64
            elif change == 'missing-component': templates['components'].pop('garment.test')
            elif change == 'extra-component': templates['components']['unknown.component'] = {}
            else: templates['compiler_inputs'].pop('standard_recipe_ref')
            if change != 'digest':
                templates['prepared_sha256'] = digest({k:v for k,v in templates.items() if k!='prepared_sha256'})
            atomic_json(path, templates); before = self.files()
            with self.subTest(change=change), self.assertRaises(StudioError): self.admit()
            self.assertEqual(before, self.files()); path.write_bytes(original)
        self.project.ready.assert_not_called()

    def test_body_object_must_be_explicit_and_optional_envelope_review_hash_is_verified(self):
        for name in ('', None, 42, 'other-measured-body'):
            before = self.files()
            with self.subTest(name=name), self.assertRaises(StudioError):
                self.admit({**self.arguments, 'body_object': name})
            self.assertEqual(before, self.files())
        envelope = self.save('envelope-review.json', {'scope': 'SYNTHETIC_INPUT_IDENTITY_ONLY_NO_PHYSICAL_ACCEPTANCE'})
        before = self.files()
        self.admit({**self.arguments, 'envelope_review': envelope})
        self.assertEqual(before, self.files())
        with self.assertRaisesRegex(StudioError, 'envelope review changed'):
            self.admit({**self.arguments, 'envelope_review': {**envelope, 'sha256': 'f'*64}})
        self.assertEqual(before, self.files())

    def test_canonical_package_binding_and_template_source_must_match_current_approved_component(self):
        before = self.files()
        component = copy.deepcopy(self.state['components']['garment.test'])
        component['package']['sha256'] = 'f'*64
        self.project.ready.return_value = (self.state, component)
        with self.assertRaisesRegex(StudioError, 'canonical approved component'): self.admit()
        self.assertEqual(before, self.files())
        self.project.ready.return_value = (self.state, self.state['components']['garment.test'])
        path = self.root/self.arguments['templates_path']; original = path.read_bytes()
        template = read_json(path); template['components']['garment.test']['source_ref']['sha256'] = 'f'*64
        template['prepared_sha256'] = digest({k:v for k,v in template.items() if k!='prepared_sha256'})
        atomic_json(path, template); before = self.files()
        with self.assertRaisesRegex(StudioError, 'canonical approved component'): self.admit()
        self.assertEqual(before, self.files()); path.write_bytes(original)

    def recovery_fixture(self):
        # This synthetic boundary validates guard references only. It is not
        # produced native geometry, and cannot qualify a physical run.
        run_ref = self.save('native-bindings/v1/run.json',
            {'scope': 'GUARD_REFERENCE_FIXTURE_ONLY', 'simulation': 'NOT_EXECUTED'})
        result = {'version': 1, 'status': 'NATIVE_PREPARATION_INPUTS_BOUND',
            'templates': {'path': self.arguments['templates_path'],
                          'sha256': sha(self.root/self.arguments['templates_path'])},
            'body_ref': self.prepared['body_ref'], 'body_geometry_ref': self.prepared['geometry_ref'],
            'collider': {'object': self.arguments['body_object']},
            'guide_reconstruction': {'policy_ref': {'path': self.arguments['policy_path'],
                                                    'sha256': sha(self.root/self.arguments['policy_path'])}},
            'run_specification': run_ref, 'qualification': 'NONE', 'simulation': 'NOT_EXECUTED'}
        self.save('native-bindings/v1/binding.json', result)
        return result

    def test_complete_binding_boundary_can_be_replayed_before_journal_without_new_mutation(self):
        self.recovery_fixture(); before = self.files()
        result, _ = self.admit()
        self.assertIsNone(result)
        self.project.ready.assert_called_once_with('garment.test')
        self.assertEqual(before, self.files())

    def test_completed_boundary_changed_identities_or_run_cannot_be_replayed(self):
        previous = self.recovery_fixture()
        binding = self.root/'native-bindings/v1/binding.json'
        run_file = self.root/previous['run_specification']['path']; run_bytes = run_file.read_bytes()
        for change in ('status', 'templates', 'body', 'geometry', 'collider', 'policy', 'run', 'missing-run'):
            value = copy.deepcopy(previous)
            if change == 'status': value['status'] = 'INCOMPLETE'
            elif change == 'templates': value['templates']['sha256'] = 'f'*64
            elif change == 'body': value['body_ref']['sha256'] = 'f'*64
            elif change == 'geometry': value['body_geometry_ref']['sha256'] = 'f'*64
            elif change == 'collider': value['collider']['object'] = 'another-body'
            elif change == 'policy': value['guide_reconstruction']['policy_ref']['sha256'] = 'f'*64
            elif change == 'run': run_file.write_bytes(run_bytes+b' ')
            else: value.pop('run_specification')
            atomic_json(binding, value); before = self.files()
            with self.subTest(change=change), self.assertRaises(StudioError): self.admit()
            self.assertEqual(before, self.files()); run_file.write_bytes(run_bytes)
        self.project.ready.assert_not_called()

    def test_runtime_identity_binds_existing_handler_generator_and_imported_source_kernels(self):
        before = self.files()
        inventory = _unit_runtime({'operation': 'bind_component_preparations'})
        for path in ('blender/textile_executor.py', 'a3d/production_preparation.py',
                     'a3d/garment_guide_policy.py', 'a3d/textile_executor.py',
                     'a3d/garment_guides.py', 'a3d/source_seam_coupling.py',
                     'a3d/rigid_guide_alignment.py'):
            self.assertEqual(inventory[path], sha(ROOT/path))
        self.assertEqual(before, self.files())

    def test_dispatcher_routes_same_arguments_to_existing_binder_without_blender_execution(self):
        from blender.operations import _perform
        # This isolated routing test replaces the handler and constructor, not
        # any validation. The admission tests above use their real producers.
        before = self.files(); marker = {'routing_test_only': True}
        with patch('blender.operations.Project', return_value=self.project) as constructor,\
                patch('blender.textile_executor.bind_component_preparations', return_value=marker) as handler:
            self.assertIs(_perform(str(self.root), 'bind_component_preparations', self.arguments), marker)
            constructor.assert_called_once_with(str(self.root))
            handler.assert_called_once_with(self.project, **self.arguments)
        self.assertEqual(before, self.files())


if __name__ == '__main__':
    import unittest
    unittest.main()
