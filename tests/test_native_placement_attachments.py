import copy
import math
import struct
import tempfile
import unittest
from contextlib import ExitStack
from pathlib import Path
from types import SimpleNamespace
from unittest.mock import patch

from a3d.core import StudioError, contract, digest
from a3d.placement_attachments import bind_anatomical_attachments, observe_anatomical_attachments
from blender.placement_correction import correct_preparation
from tests.test_placement_solver import fixture


def declaration(piece='source-panel', uv=None, target=None):
    return {'piece': piece, 'source_uv_cm': uv or [0., 0.],
        'target_world_cm': target or [0., 0., -.8], 'tolerance_cm': 0., 'source_ref': 'measured.body.path'}


def native_inputs():
    payload, points, spec, _ = fixture()
    payload.update(placed_cm=points, package_sha256='a'*64, component_id='coupon')
    plan = {'quality': copy.deepcopy(spec['quality']),
        'assembly': {'max_displacement_cm': 2., 'max_step_cm': .2, 'iterations': 10},
        'collision': {'clearance_cm': .1}, 'consolidation': {'weld_gap_cm': .05}}
    preparation = {'version': 1, 'component_id': 'coupon', 'source_ref': 'fixture',
        'regular_mesh': {'spacing_cm': 1., 'min_spacing_cm': .2, 'refinement_distance_cm': 1.,
                         'max_vertices': 20, 'target_min_angle_degrees': 10},
        'placement_correction': spec, 'anatomical_attachments': [declaration()]}
    return payload, {'mesh': copy.deepcopy(spec['quality'])}, plan, preparation


class NativeAnatomicalAttachments(unittest.TestCase):
    def test_source_binding_is_generic_for_every_piece_name_and_barycentric_support(self):
        for pid in ('head-cover', 'left-elbow', 'ankle', 'arbitrary-source-81'):
            payload, points, _, _ = fixture()
            payload['panels'] = {pid: payload['panels'].pop('source-panel')}
            declarations = [declaration(pid, [.4, .2], [.4, .2, -.8])]
            before = digest([payload, points, declarations])
            binding = bind_anatomical_attachments(payload, points, declarations)
            self.assertEqual(binding['protected_indices'], [0, 1, 2])
            report = observe_anatomical_attachments(binding, points)
            self.assertTrue(report['preserved']); self.assertFalse(report['physical_pin_created'])
            self.assertEqual(digest([payload, points, declarations]), before)

    def test_shared_source_edge_uses_every_support_without_proximity_weld(self):
        payload, points, _, _ = fixture()
        binding = bind_anatomical_attachments(payload, points, [declaration(uv=[1., 1.], target=[1., 1., -.8])])
        self.assertEqual(len(binding['attachments'][0]['supports']), 2)
        self.assertEqual(binding['protected_indices'], [0, 2])
        changed = copy.deepcopy(points); changed[0][0] += .1; changed[2][0] -= .1
        observed = observe_anatomical_attachments(binding, changed)
        self.assertLess(observed['attachments'][0]['max_residual_cm'], 1e-10)
        self.assertFalse(observed['preserved'], 'Equal opposite support motion must not rebase a measured attachment')

    def test_binding_rotates_and_translates_with_measured_target(self):
        payload, points, _, _ = fixture(); angle = .64; c, s = math.cos(angle), math.sin(angle)
        def move(p): return [p[0]+12., c*p[1]-s*p[2]-9., s*p[1]+c*p[2]+17.]
        decl = declaration(uv=[.8, .6], target=[.8, .6, -.8])
        a = bind_anatomical_attachments(payload, points, [decl])
        moved = [move(p) for p in points]; decl['target_world_cm'] = move(decl['target_world_cm'])
        b = bind_anatomical_attachments(payload, moved, [decl])
        self.assertEqual(a['protected_indices'], b['protected_indices'])
        self.assertTrue(observe_anatomical_attachments(b, moved)['preserved'])

    def test_binary32_storage_is_measured_separately_and_larger_errors_refuse(self):
        payload, points, _, _ = fixture()
        points = [[x+31.127381, y, z+180.321765] for x, y, z in points]
        decl = declaration(target=list(points[0]))
        native = [[struct.unpack('f', struct.pack('f', x/100))[0]*100 for x in p] for p in points]
        binding = bind_anatomical_attachments(payload, native, [decl])
        observed = observe_anatomical_attachments(binding, native)
        self.assertTrue(observed['preserved'])
        row = observed['attachments'][0]
        self.assertGreater(row['native_float32_guard_cm'], 0.)
        self.assertLess(row['native_float32_guard_cm'], .001)
        native[0][0] += .01
        self.assertFalse(observe_anatomical_attachments(binding, native)['preserved'])
        with self.assertRaises(StudioError): bind_anatomical_attachments(payload, native, [decl])

    def test_missing_wrong_or_ambiguous_source_binding_is_refused(self):
        payload, points, _, _ = fixture()
        for row in (declaration('wrong-piece'), declaration(uv=[30., 30.]),
                    declaration(target=[0., 0., 5.]), {**declaration(), 'tolerance_cm': True}):
            with self.subTest(row=row), self.assertRaises(StudioError):
                bind_anatomical_attachments(payload, points, [row])
        bound = copy.deepcopy(payload)
        bound['source_face_vertex_ids'] = copy.deepcopy(bound['faces'])
        bound['faces'][0].reverse()
        with self.assertRaisesRegex(StudioError, 'identities'):
            bind_anatomical_attachments(bound, points, [declaration()])
        huge = [[x+1e8, y, z] for x, y, z in points]
        with self.assertRaisesRegex(StudioError, 'binary32'):
            bind_anatomical_attachments(payload, huge, [declaration(target=list(huge[0]))])

    def test_invalid_native_entry_stops_before_contact_context_and_any_solver(self):
        payload, recipe, plan, preparation = native_inputs()
        preparation['anatomical_attachments'][0]['target_world_cm'][2] += 2.
        before = digest([payload, recipe, plan, preparation])
        with patch('blender.cloth_contacts.build_contact_context') as context, \
                patch('blender.placement_correction.solve_placement') as solve, self.assertRaises(StudioError):
            correct_preparation(payload, recipe, plan, preparation, [])
        context.assert_not_called(); solve.assert_not_called()
        self.assertEqual(digest([payload, recipe, plan, preparation]), before)

    def test_contact_solver_receives_protected_indices_without_physical_pins(self):
        payload, recipe, plan, preparation = native_inputs()
        seen = []
        def solve(source, coords, evaluator, specification, **kwargs):
            seen.append(specification['protected_indices'])
            self.assertEqual(source['pins'], {})
            return {'status': 'NEEDS_CORRECTION', 'coordinates_cm': copy.deepcopy(coords),
                    'candidate_sha256': digest(coords), 'qualification': 'NONE'}
        with patch('blender.cloth_contacts.build_contact_context', return_value={'bodies': []}), \
                patch('blender.placement_correction.solve_placement', side_effect=solve):
            result = correct_preparation(payload, recipe, plan, preparation, [])
        self.assertEqual(seen, [[0]])
        self.assertTrue(result['anatomical_attachments']['final']['preserved'])
        self.assertTrue(result['candidate_not_automatically_admitted'])

    def test_buggy_contact_solver_cannot_report_success_after_anatomical_drift(self):
        payload, recipe, plan, preparation = native_inputs()
        changed = copy.deepcopy(payload['placed_cm']); changed[0][2] += .2
        with patch('blender.cloth_contacts.build_contact_context', return_value={'bodies': []}), \
                patch('blender.placement_correction.solve_placement', return_value={
                    'status': 'GEOMETRIC_GATES_PASSED', 'coordinates_cm': changed}):
            result = correct_preparation(payload, recipe, plan, preparation, [])
        self.assertEqual(result['status'], 'NEEDS_CORRECTION')
        self.assertEqual(result['stop_reason'], 'ANATOMICAL_ATTACHMENT_CHANGED_CONTACT_SOLVER')
        self.assertEqual(result['coordinates_cm'], payload['placed_cm'])
        self.assertEqual(result['rejected_stage_result']['coordinates_cm'], changed)
        self.assertTrue(result['anatomical_attachments']['final']['preserved'])

    def test_actual_contact_search_cannot_move_protected_body_point_to_improve_score(self):
        payload, recipe, plan, preparation = native_inputs()
        _, _, _, evaluate = fixture()
        with patch('blender.cloth_contacts.build_contact_context', return_value={'bodies': []}), \
                patch('blender.placement_correction.native_measurement',
                      side_effect=lambda source, coords, *args: evaluate(source, coords)):
            result = correct_preparation(payload, recipe, plan, preparation, [])
        self.assertEqual(result['status'], 'NEEDS_CORRECTION')
        self.assertEqual(result['coordinates_cm'][0], payload['placed_cm'][0])
        self.assertTrue(result['anatomical_attachments']['final']['preserved'])

    def test_actual_metric_recovery_cannot_resize_the_anatomical_anchor(self):
        payload, recipe, plan, preparation = self.anchor_inputs()
        preparation.pop('anchor_reserve_correction')
        preparation['anatomical_attachments'] = [declaration('panel', [2., 0.], list(payload['placed_cm'][1]))]
        with patch('blender.cloth_contacts.build_contact_context', return_value={'bodies': []}), \
                patch('blender.placement_correction.native_measurement',
                      return_value={'hard_valid': False, 'score': 1.}), \
                patch('blender.placement_correction.solve_placement') as contact:
            result = correct_preparation(payload, recipe, plan, preparation, [])
        contact.assert_not_called()
        self.assertEqual(result['status'], 'NEEDS_CORRECTION')
        self.assertEqual(result['coordinates_cm'][1], payload['placed_cm'][1])
        self.assertTrue(result['anatomical_attachments']['final']['preserved'])

    def anchor_inputs(self):
        from tests.test_native_placement_correction import NativeCorrectionAdapter
        payload, points, quality, plan, preparation, recipe = NativeCorrectionAdapter().anchor_inputs()
        preparation['anatomical_attachments'] = [declaration('panel', target=list(points[0]))]
        return payload, recipe, plan, preparation

    def test_anchor_reserve_does_not_rebase_measured_anatomical_targets(self):
        payload, recipe, plan, preparation = self.anchor_inputs()
        shifted = [[x, y, z+.25] for x, y, z in payload['placed_cm']]
        with patch('blender.cloth_contacts.build_contact_context', return_value={'bodies': []}), \
                patch('blender.anchor_reserve.propose_anchor_reserve', return_value={
                    'status': 'ANCHORS_ADMISSIBLE_ONLY', 'coordinates_cm': shifted}), \
                patch('blender.placement_correction.recover_guide_metric') as metric, \
                patch('blender.placement_correction.solve_placement') as contact:
            result = correct_preparation(payload, recipe, plan, preparation, [])
        metric.assert_not_called(); contact.assert_not_called()
        self.assertEqual(result['status'], 'NEEDS_CORRECTION')
        self.assertEqual(result['stop_reason'], 'ANATOMICAL_ATTACHMENT_CHANGED_ANCHOR_RESERVE')
        self.assertEqual(result['coordinates_cm'], payload['placed_cm'])

    def test_metric_recovery_receives_protection_and_drift_cannot_continue(self):
        payload, recipe, plan, preparation = self.anchor_inputs()
        preparation.pop('anchor_reserve_correction')
        changed = copy.deepcopy(payload['placed_cm']); changed[0][2] += .2
        calls = []
        def recover(*args, **kwargs):
            calls.append(kwargs['protected_indices'])
            return {'status': 'SOURCE_METRIC_RECOVERED', 'coordinates_cm': changed}
        with patch('blender.cloth_contacts.build_contact_context', return_value={'bodies': []}), \
                patch('blender.placement_correction.recover_guide_metric', side_effect=recover), \
                patch('blender.placement_correction.solve_placement') as contact:
            result = correct_preparation(payload, recipe, plan, preparation, [])
        self.assertEqual(calls, [[0]]); contact.assert_not_called()
        self.assertEqual(result['status'], 'NEEDS_CORRECTION')
        self.assertEqual(result['stop_reason'], 'ANATOMICAL_ATTACHMENT_CHANGED_METRIC_RECOVERY')
        self.assertEqual(result['coordinates_cm'], payload['placed_cm'])

    def test_preparation_contract_declares_only_source_attachments_not_physical_pins(self):
        _, _, _, preparation = native_inputs()
        contract('pattern-preparation', preparation)
        preparation['anatomical_attachments'][0]['physical_pin'] = True
        with self.assertRaises(StudioError): contract('pattern-preparation', preparation)


class NativePreparationAttachmentEntry(unittest.TestCase):
    """Exercise the actual entry control flow; Blender/file services are doubles."""
    def invoke(self, target_delta=0., correction=False, final_delta=0.):
        from a3d.core import ROOT
        from blender.pattern_preparation import prepare_pattern_assembly
        payload, recipe, _, spec = native_inputs()
        if not correction:
            spec.pop('placement_correction')
        spec['assembly_plan'] = {'path': 'plan.json', 'sha256': 'a'*64}
        spec['anatomical_attachments'][0]['target_world_cm'][2] += target_delta
        recipe.update(component_id='coupon', colliders=[], mass={}, limits={'weld_gap_cm': .05})
        plan = {'component_id': 'coupon', 'mapping_sha256': 'old', 'layers': {},
            'assembly': {'max_displacement_cm': 100.}, 'quality': recipe['mesh']}
        writes = []; mesh_arguments = []; correction_calls = []
        class Object(dict):
            name = 'test-candidate'
        obj = Object()
        base = ROOT/'work/test-runs'; base.mkdir(parents=True, exist_ok=True)
        with tempfile.TemporaryDirectory(dir=base) as directory, ExitStack() as stack:
            root = Path(directory)
            component = {'route': {'selected': 'PATTERN_SEWN'}, 'stage': 'PACKAGED',
                         'package': {'path': 'package.garmentpkg', 'sha256': 'a'*64}}
            project = SimpleNamespace(root=root, data=root/'.a3d',
                ready=lambda component_id: (None, component),
                state=lambda: {'pending_blender_operation': {'checkpoint': {'path': 'checkpoint.blend', 'sha256': 'a'*64}}})
            saved = {'spec.json': spec, 'recipe.json': recipe, 'plan.json': plan,
                     'garment.json': {'component_id': 'coupon'}, 'dossier.json': {}}
            bpy = SimpleNamespace(data=SimpleNamespace(objects=[], is_dirty=False),
                ops=SimpleNamespace(wm=SimpleNamespace(save_as_mainfile=lambda **kwargs: None)))
            stack.enter_context(patch.dict('sys.modules', {'bpy': bpy}))
            def make_mesh(*args, **kwargs):
                mesh_arguments.append(copy.deepcopy(kwargs)); return copy.deepcopy(payload)
            def correct(source, *args, **kwargs):
                correction_calls.append(1)
                moved = copy.deepcopy(source['placed_cm']); moved[0][2] += final_delta
                return {'status': 'GEOMETRIC_GATES_PASSED', 'coordinates_cm': moved}
            def collide(*args, **kwargs):
                def guard(coords):
                    if not correction and final_delta:
                        coords[0][2] += final_delta
                    return {'ok': True}
                return guard
            values = {
                'blender.operations.working': (project, {'working': str(root/'working.blend')}),
                'a3d.packages.extract_package': {},
                'a3d.planning.require_board': {'dossier_path': 'dossier.json', 'dependencies': {'dossier.json': 'a'*64}},
                'a3d.pattern_preparation.audit_source': {'status': 'SOURCE_AUDITED'},
                'a3d.pattern_preparation.preparation_statistics': {},
                'a3d.pattern_preparation.assess_preparation': {'status': 'READY'},
                'a3d.dressing.layer_collision_selection': {'status': 'LAYER_COLLIDERS_SELECTED', 'colliders': []},
                'blender.pattern_preparation.preform_supports': ({}, {'contradictory_fixed_cohorts': []}),
                'blender.pattern_preparation.context_colliders': ([], [], []),
                'blender.pattern_preparation.validate_envelope_review': {},
                'blender.pattern_preparation.simulation_quality': {},
                'blender.pattern_preparation._material_assessment': {'limitations': []},
                'blender.pattern_preparation.make_object': obj,
                'blender.pattern_preparation.mesh_recipe_digest': 'mesh-recipe',
                'blender.pattern_preparation.mesh_digest': 'mesh',
                'blender.pattern_assembly.dressing_measurement': {'status': 'ASSESSED'},
                'blender.piece_inventory.remember_candidate': None,
                'blender.piece_inventory.collect': {'summary': 'fixture inventory'},
                'blender.piece_inventory.save_report': None,
                'blender.preparation_review.render_preparation': {'views': {}},
                'blender.preparation_review.save_preparation_master': None,
            }
            for name, value in values.items():
                stack.enter_context(patch(name, return_value=value))
            effects = {
                'blender.pattern_preparation.contract': lambda name, value: value,
                'blender.pattern_preparation.inside': lambda parent, path: parent/path,
                'blender.pattern_preparation.read_json': lambda path: copy.deepcopy(saved[Path(path).name]),
                'blender.pattern_preparation.sha': lambda path: 'a'*64,
                'blender.pattern_preparation.verified_reference': lambda project, ref: project.root/ref['path'],
                'blender.pattern_preparation.reference': lambda project, path: {'path': Path(path).relative_to(project.root).as_posix(), 'sha256': 'a'*64},
                'blender.pattern_preparation.atomic_json': lambda path, value: writes.append((Path(path).name, copy.deepcopy(value))),
                'blender.pattern_preparation.build_mesh': make_mesh,
                'a3d.dressing.rebind_layer_execution': lambda supplied, mapped: supplied,
                'blender.preform.preform_coordinates': lambda source, plan: (copy.deepcopy(source['placed_cm']), {'status': 'PREPOSITIONED'}),
                'blender.pattern_preparation.collision_guard': collide,
                'blender.placement_correction.correct_preparation': correct,
            }
            for name, effect in effects.items():
                stack.enter_context(patch(name, side_effect=effect))
            result = prepare_pattern_assembly(str(root), 'coupon', 'recipe.json', 'spec.json')
        return result, writes, mesh_arguments, correction_calls

    def test_wrong_attachment_without_optional_correction_never_reaches_ready(self):
        result, writes, mesh_calls, corrections = self.invoke(target_delta=1.)
        self.assertEqual(result['readiness'], 'NEEDS_CORRECTION')
        self.assertEqual(result['anatomical_attachments']['status'], 'NEEDS_CORRECTION')
        self.assertEqual(result['anatomical_attachments']['stage'], 'ENTRY')
        self.assertIsNone(result['next_operation']); self.assertEqual(corrections, [])
        self.assertIn('anatomical_attachments', mesh_calls[0])
        receipt = next(value for name, value in writes if name == 'receipt.json')
        self.assertEqual(receipt['anatomical_attachments']['status'], 'NEEDS_CORRECTION')
        self.assertTrue(any(row['category'] == 'anatomical_attachments' for row in receipt['problems']))

    def test_correct_attachment_without_optional_correction_gets_current_final_evidence(self):
        result, _, _, corrections = self.invoke()
        self.assertEqual(result['readiness'], 'READY')
        self.assertEqual(corrections, [])
        observation = result['anatomical_attachments']
        self.assertEqual(observation['status'], 'ANATOMICAL_ATTACHMENTS_PRESERVED')
        self.assertTrue(observation['entry']['preserved']); self.assertTrue(observation['final']['preserved'])
        self.assertEqual(observation['final']['candidate_sha256'], observation['entry']['candidate_sha256'])

    def test_wrong_attachment_prevents_optional_correction_from_rebasing_it(self):
        result, _, _, corrections = self.invoke(target_delta=1., correction=True)
        self.assertEqual(corrections, [])
        self.assertEqual(result['readiness'], 'NEEDS_CORRECTION')

    def test_final_entry_guard_is_independent_of_optional_solver_success(self):
        result, _, _, corrections = self.invoke(correction=True, final_delta=.25)
        self.assertEqual(corrections, [1])
        self.assertEqual(result['readiness'], 'NEEDS_CORRECTION')
        self.assertFalse(result['anatomical_attachments']['final']['preserved'])

    def test_final_entry_guard_also_runs_when_solver_is_absent(self):
        result, _, _, corrections = self.invoke(final_delta=.25)
        self.assertEqual(corrections, [])
        self.assertEqual(result['readiness'], 'NEEDS_CORRECTION')
        self.assertFalse(result['anatomical_attachments']['final']['preserved'])

    def test_cached_ready_requires_current_anatomical_evidence_and_target(self):
        from tests.test_pattern_preparation_native import PreparedReceiptContracts
        from a3d.core import atomic_json
        case = PreparedReceiptContracts(); case.setUp()
        try:
            source, points, _, _ = fixture()
            case.payload.update(source, placed_cm=points)
            declarations = [declaration()]
            atomic_json(case.root/'spec.json', {'anatomical_attachments': declarations})
            case.record['preparation_spec'] = case.ref('spec')
            with self.assertRaisesRegex(StudioError, 'anatomical attachment evidence'):
                case.invoke()
            binding = bind_anatomical_attachments(case.payload, points, declarations)
            observed = observe_anatomical_attachments(binding, points)
            case.record['anatomical_attachments'] = {
                'status': observed['status'], 'source_declarations_sha256': digest(declarations), 'final': observed}
            case.invoke()
            case.record['anatomical_attachments']['final']['candidate_sha256'] = 'stale'
            with self.assertRaisesRegex(StudioError, 'anatomical attachment evidence'):
                case.invoke()
            case.record['anatomical_attachments']['final']['candidate_sha256'] = digest(points)
            case.payload['placed_cm'][0][2] += .2
            with self.assertRaisesRegex(StudioError, 'measured anatomical attachment'):
                case.invoke()
        finally:
            case.tearDown()


if __name__ == '__main__':
    unittest.main()
