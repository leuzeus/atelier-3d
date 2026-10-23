"""File-bound generic placement inputs and production V2 recovery coverage."""
import copy
from types import SimpleNamespace

from a3d.anatomical_guide_inputs import project_anatomical_references
from a3d.anatomical_placement import validate_anatomical_references
from a3d.core import StudioError, atomic_json, contract, digest, sha
from a3d.garment_guide_policy import prepare_guide_policy, reconstruct_guide_policy, verify_guide_policy
from a3d.textile_executor import _source_metric_recovery
from tests.test_anatomical_placement import fixture
from tests.test_core import Case
from tests.test_garment_guide_policy import coupled_fixture
from tests.test_metric_recovery_inputs import compiler_fixture, preparation
from tests.test_placement_solver import fixture as placement_fixture


class AnatomicalGuideInputs(Case):
    def test_generic_panel_uses_public_policy_reconstruction_without_anatomical_role_alias(self):
        from tests.test_anatomical_garment_guides import band_fixture
        c, _, _, ref, _, _ = coupled_fixture()[:6]
        profile, geometry, _, document, _ = fixture()
        piece, policy_input, _, _ = band_fixture()
        data = {'component_id': 'garment.test', 'units': 'cm', 'pieces': {'band': piece}, 'seams': []}
        semantics = {'role': 'panel', 'side': 'center', 'layer': 'cloth', 'longitudinal_uv_axis': 'u'}
        c['textiles'] = {'band': {'component_id': 'garment.test', 'source_geometry': piece, 'semantics': semantics}}
        document['pieces'] = {'band': policy_input}
        parameters = {'garment.test': {'upper_blend': 1., 'surface_sections': False, 'skin_section_heights_cm': [],
            'anatomical_references_ref': {'path': 'references.json', 'sha256': '1'*64}}}
        references = {'garment.test': document}
        policy = prepare_guide_policy(c, profile, geometry, ref, parameters, anatomical_references=references)
        guides, _ = reconstruct_guide_policy(c, profile, geometry, ref, {'garment.test': data}, policy,
                                             anatomical_references=references)
        verification = verify_guide_policy(c, profile, geometry, ref, {'garment.test': data}, policy, guides,
                                           anatomical_references=references)
        self.assertEqual(guides['garment.test']['status'], 'GARMENT_GUIDES_PREPARED')
        self.assertEqual(verification['comparison'], 'FULL_UNROUNDED_GUIDE_REPORT_IDENTICAL')
        from tests.test_garment_planner import example
        from a3d.garment_planner import plan_assembly
        specification = example()
        for row in specification['pieces']:
            row['role'] = 'panel'
        self.assertEqual(plan_assembly(specification)['qualification'], 'NONE')

    def files(self):
        profile, geometry, report, document, _ = fixture()
        report_path = self.root/'path-report.json'; atomic_json(report_path, report)
        specification = copy.deepcopy(document)
        specification['paths']['chosen'] = {'path_id': 'measured', 'region': 'neck',
            'report_ref': {'path': report_path.name, 'sha256': sha(report_path)}}
        spec_path = self.root/'references.json'; atomic_json(spec_path, specification)
        rows = {'garment.any': {'anatomical_references_ref': {'path': spec_path.name, 'sha256': sha(spec_path)}}}
        return profile, geometry, document, rows, report_path, spec_path

    def test_exact_files_reconstruct_same_pure_reference_and_keep_review_separate(self):
        profile, geometry, expected, rows, _, _ = self.files()
        result = project_anatomical_references(SimpleNamespace(root=self.root), rows)
        self.assertEqual(result['garment.any'], expected)
        normalized = validate_anatomical_references(profile, result['garment.any'], geometry=geometry)
        self.assertEqual(normalized['paths']['chosen']['geometry_validation'], 'EXACT_SOURCE_EDGES_VERIFIED')
        self.assertEqual(normalized['anatomical_gate'], 'NOT_GRANTED')

    def test_changed_report_or_specification_is_refused_before_consuming_coordinates(self):
        for choice in (4, 5):
            inputs = self.files(); rows = inputs[3]
            inputs[choice].write_text('{}', encoding='utf-8')
            with self.assertRaisesRegex(StudioError, 'changed'):
                project_anatomical_references(SimpleNamespace(root=self.root), rows)

    def test_path_escape_and_raw_coordinate_override_are_refused(self):
        _, _, _, rows, _, spec_path = self.files()
        rows['garment.any']['anatomical_references_ref']['path'] = '../outside.json'
        with self.assertRaises(StudioError):
            project_anatomical_references(SimpleNamespace(root=self.root), rows)
        _, _, document, rows, _, spec_path = self.files()
        atomic_json(spec_path, document)  # Inlined reports are not the public transport.
        rows['garment.any']['anatomical_references_ref']['sha256'] = sha(spec_path)
        with self.assertRaisesRegex(StudioError, 'report reference'):
            project_anatomical_references(SimpleNamespace(root=self.root), rows)

    def test_v2_policy_cannot_be_relabelled_legacy_or_ignore_relaxation_inputs(self):
        c, p, g, ref, data, params, recipes = coupled_fixture()
        coupling = params['garment.test']['source_seam_coupling']
        coupling.update(strategy='COUPLED_REST_METRIC_V2', piece_scope='PERMANENT_COMPONENT',
            numerical_anchor_edges=[{'piece': 'single-front', 'edge': 'attachment'}],
            relaxation={'max_iterations': 2})
        policy = prepare_guide_policy(c, p, g, ref, params, source_seam_recipes=recipes)
        self.assertEqual(policy['version'], 2)
        contract('garment-guide-policy', policy)
        bad = copy.deepcopy(policy); bad.update(version=1, generator='GARMENT_VOLUME_FRAMES_V1')
        with self.assertRaisesRegex(StudioError, 'version'):
            reconstruct_guide_policy(c, p, g, ref, data, bad, source_seam_recipes=recipes)


def modern_recovery_fixture():
    inputs = list(compiler_fixture())
    data, semantics, guide, _, _ = inputs
    coupling = guide['source_seam_coupling']
    coupling.update(method='SOURCE_PERMANENT_NORMALIZED_PARTITION_COUPLED_REST_METRIC',
        refinements={pid: {} for pid in data['pieces']}, cage_sha256=digest(guide['panels']),
        relations=[{'source_seam_id': row['id'], 'source_relation': copy.deepcopy(row)} for row in data['seams']],
        permanent_relation_coverage='COMPLETE_SELECTED_COMPONENT',
        numerical_anchor_edges=[{'piece': 'a', 'edge': 'left'}],
        relaxation={'settings': {'seam_tolerance_cm': .05}, 'best': {'max_seam_gap_cm': .03}})
    for row in semantics.values():
        row['role'] = 'custom-foot-cover'
        row.pop('guide_edges', None)
    return inputs


class GenericMetricRecovery(Case):
    def test_v2_covers_all_connected_pieces_and_explicit_anchors_without_torso_roles(self):
        inputs = modern_recovery_fixture(); before = digest(inputs)
        result = _source_metric_recovery(*inputs)
        self.assertEqual(result['piece_ids'], ['a', 'b', 'c'])
        self.assertEqual(result['seam_ids'], ['ab', 'bc'])
        self.assertEqual(result['protected_edges'], [{'piece': 'a', 'edge': 'left'}])
        self.assertAlmostEqual(result['max_initial_seam_gap_cm'], .052)
        _, _, specification, _ = placement_fixture()
        contract('pattern-preparation', preparation(result, specification))
        self.assertEqual(digest(inputs), before)

    def test_omitted_permanent_partner_cannot_pass_as_complete_recovery(self):
        inputs = modern_recovery_fixture(); coupling = inputs[2]['source_seam_coupling']
        coupling['refinements'].pop('c')
        coupling['relations'].pop()
        coupling['cage_sha256'] = digest({pid: inputs[2]['panels'][pid] for pid in ('a', 'b')})
        with self.assertRaisesRegex(StudioError, 'all permanent source partners'):
            _source_metric_recovery(*inputs)

    def test_unreached_gap_or_missing_anchor_does_not_become_native_recovery(self):
        for mutate in (
            lambda row: row.update(numerical_anchor_edges=[]),
            lambda row: row['relaxation']['best'].update(max_seam_gap_cm=.051),
            lambda row: row['relaxation']['settings'].update(seam_tolerance_cm=float('nan')),
        ):
            inputs = modern_recovery_fixture(); mutate(inputs[2]['source_seam_coupling'])
            with self.assertRaises(StudioError):
                _source_metric_recovery(*inputs)
