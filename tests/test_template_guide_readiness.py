"""Complete proposal DTOs stay distinct from native placement readiness.

Small source-coupling fixtures only; no native body, garment or Cloth evidence.
"""
import copy
import unittest

from a3d.core import ROOT, StudioError, digest, read_json
from a3d.garment_planner import plan_assembly
from a3d.source_seam_coupling import couple_source_seams
from a3d.textile_executor import _template_guide_assessment, prepare_component_templates
from tests.test_garment_planner import example as planner_example
from tests.test_rigid_guide_alignment import collar_fixture


def fixture():
    data, frames, coupling_recipe, semantics, collar = collar_fixture(joint=True)
    data['material'] = {'mass_kg': .3, 'tension_stiffness': 15, 'compression_stiffness': 15,
                        'shear_stiffness': 5, 'bending_stiffness': .5}
    for piece in data['pieces'].values():
        piece.update(position_cm=[0., 0., 0.], rotation_degrees=[0., 0., 0.])
    for pid, row in semantics.items():
        row.update(side='center', layer='cloth', longitudinal_uv_axis='v',
                   guide_edges={'shoulder': 'top'} if row['role'] == 'front' else {'anchor': 'bottom'})
    # This is the actual bounded source-seam producer, including its complete
    # collar report and genuine PARTIAL_TEST_ONLY remaining-scope warning.
    cages, coupling = couple_source_seams(data, frames, coupling_recipe,
        semantics=semantics, subdivisions=3, clock=lambda: 0.)
    ref = {'path': 'synthetic/source.garmentpkg', 'sha256': digest(data)}
    dossier_ref = {'path': 'synthetic/dossier.json', 'sha256': digest('contract-only dossier')}
    profile = {'test_fixture': 'identity only; no native anatomy or garment acceptance'}
    body_ref = {'path': 'synthetic/body.json', 'sha256': digest(profile)}
    spec = {'version': 1, 'source_ref': dossier_ref, 'body_ref': body_ref,
        'pieces': [{**row, 'id': pid, 'component_id': data['component_id'],
                    'edges': sorted(data['pieces'][pid]['edges']), 'source_ref': ref}
                   for pid, row in semantics.items()],
        'links': [{**{key: row[key] for key in ('id', 'kind', 'piece_a', 'edge_a', 'piece_b', 'edge_b')},
                   'source_ref': ref} for row in data['seams']],
        'budgets': planner_example()['budgets'],
        'layers': {'version': 1, 'source_ref': dossier_ref, 'mode': 'ordered',
            'interaction': 'one_way_declared', 'nodes': [
                {'id': 'body', 'kind': 'body', 'panels': [], 'colliders': ['body'], 'source_ref': body_ref},
                {'id': 'cloth', 'kind': 'garment', 'panels': sorted(data['pieces']),
                 'colliders': [], 'source_ref': ref}], 'inside_to_outside': [['body', 'cloth']]}}
    assembly = plan_assembly(spec, capabilities=['coupled_multilayer'])
    guide = {'version': 1, 'status': 'PARTIAL_GUIDES', 'panels': cages, 'pending_pieces': [],
        'diagnostics': [{'family': 'source_rigid_alignment', 'code': 'PARTIAL_SOURCE_RELATION_ALIGNMENT',
            'message': 'Rigid seeds cover front attachments only; other permanent relations still require correction'}],
        'source_seam_coupling': coupling, 'source_sha256': digest(data),
        'semantics_sha256': digest(semantics), 'profile_cache_key': digest(profile),
        'profile_sha256': digest(profile), 'qualification': 'NONE', 'simulation': 'NOT_EXECUTED',
        'fitting': 'NOT_EXECUTED', 'source_mutated': False, 'source_uv_scaled': False}
    dossier = {'units': 'cm', 'components': {data['component_id']: {'pipeline': 'PATTERN_SEWN',
        'pieces': [{'id': pid, 'grain_direction': [0, 1], 'seam_allowance_cm': 0,
            'pattern': {'cut_quantity': 1, 'cut_outline_cm': copy.deepcopy(piece['vertices']),
                        'folds': [], 'assembly_marks': []}} for pid, piece in data['pieces'].items()]}}}
    sources = {data['component_id']: {'source_ref': ref, 'data': data}}
    standard = read_json(ROOT/'templates/sewing-recipe.json')
    return data, assembly, sources, guide, standard, dossier, dossier_ref, collar


def produce(case, guide=None):
    data, assembly, sources, original, standard, dossier, dossier_ref, _ = case
    return prepare_component_templates(assembly, sources, {data['component_id']: guide or original},
                                       standard, dossier, dossier_ref)


class TemplateGuideReadiness(unittest.TestCase):
    def test_actual_collar_source_report_prepares_dto_but_preserves_needed_placement_correction(self):
        case = fixture(); data, assembly, sources, guide, standard, dossier, dossier_ref, collar = case
        before = digest(case)
        alignment = guide['source_seam_coupling']['rigid_alignment']
        self.assertEqual(alignment['status'], 'PARTIAL_ROLE_SEEDS_PREPARED')
        self.assertEqual(alignment['diagnostics'], [])
        self.assertEqual(alignment['pieces'][collar]['proposal_scope'], 'PARTIAL_TEST_ONLY')
        self.assertFalse(alignment['pieces'][collar]['whole_piece_admission'])
        result = produce(case); component = result['components'][data['component_id']]
        self.assertEqual(result['status'], 'SOURCE_PREPARATION_TEMPLATES_READY')
        assessment = component['guide_assessment']
        self.assertEqual(assessment['status'], 'NEEDS_CORRECTION')
        self.assertEqual(assessment['source_guide_status'], 'PARTIAL_GUIDES')
        self.assertEqual(assessment['proposal_scope'], 'PARTIAL_TEST_ONLY')
        self.assertFalse(assessment['whole_piece_admission'])
        self.assertEqual(assessment['diagnostics'], guide['diagnostics'])
        forwarded = [row for row in result['diagnostics'] if row['category'] == 'guide_placement']
        self.assertEqual(forwarded, [{'component_id': data['component_id'], 'category': 'guide_placement',
            'assessment': 'NEEDS_CORRECTION', 'guide_assessment': assessment}])
        for report in (result, component, assessment):
            self.assertEqual(report['qualification'], 'NONE')
            self.assertEqual(report['simulation'], 'NOT_EXECUTED')
        self.assertEqual(assessment['fitting'], 'NOT_EXECUTED')
        self.assertEqual(result['native_mesh_identity'], 'NOT_YET_DERIVED')
        self.assertEqual(before, digest(case))
        self.assertEqual(guide['status'], 'PARTIAL_GUIDES')
        self.assertEqual(component['recipe_template']['limits'], standard['limits'])
        self.assertEqual(component['recipe_template']['mesh'], standard['mesh'])
        self.assertEqual(component['preparation_template']['placement_correction']['budgets']['max_displacement_cm'],
                         assembly['groups'][0]['budgets']['max_displacement_cm'])
        # Changing DTO completeness alone does not change any physical recipe,
        # staging/correction budget, source audit or source mesh requirement.
        complete = copy.deepcopy(guide); complete['status'] = 'GARMENT_GUIDES_PREPARED'; complete['diagnostics'] = []
        baseline = produce(case, complete)['components'][data['component_id']]
        for key in ('recipe_template', 'plan_fields', 'preparation_template', 'source_audit',
                    'native_bindings_required', 'recipe_provenance'):
            self.assertEqual(component[key], baseline[key])

    def test_source_inventory_missing_or_extra_is_refused_for_both_statuses(self):
        case = fixture()
        for status in ('PARTIAL_GUIDES', 'GARMENT_GUIDES_PREPARED'):
            for change in ('missing', 'extra'):
                guide = copy.deepcopy(case[3]); guide['status'] = status
                if change == 'missing': guide['panels'].pop('a')
                else: guide['panels']['unexpected-source-piece'] = copy.deepcopy(guide['panels']['a'])
                with self.subTest(status=status, change=change), self.assertRaises(StudioError):
                    produce(case, guide)

    def test_pending_source_piece_is_refused_even_when_panels_are_present(self):
        case = fixture(); guide = copy.deepcopy(case[3]); guide['pending_pieces'] = ['a']
        with self.assertRaisesRegex(StudioError, 'complete measured guides'): produce(case, guide)

    def test_unrelated_mixed_empty_or_malformed_diagnostics_are_refused(self):
        case = fixture()
        unrelated = {'family': 'torso', 'code': 'GUIDE_INPUT_OR_CAPABILITY_MISSING', 'message': 'missing landmark'}
        warning = case[3]['diagnostics'][0]
        for diagnostics in ([unrelated], [warning, unrelated], [], [None],
                            [{**warning, 'code': 'INCOMPLETE_CORRESPONDENCES'}],
                            [{**warning, 'family': 'other'}]):
            guide = copy.deepcopy(case[3]); guide['diagnostics'] = diagnostics
            with self.subTest(diagnostics=diagnostics), self.assertRaises(StudioError): produce(case, guide)

    def test_incomplete_or_internally_refused_rigid_alignment_is_refused(self):
        case = fixture()
        for change in ('status', 'internal-error', 'missing-diagnostics', 'missing-alignment', 'not-object'):
            guide = copy.deepcopy(case[3]); alignment = guide['source_seam_coupling']['rigid_alignment']
            if change == 'status': alignment['status'] = 'ALIGNMENT_INCOMPLETE'
            elif change == 'internal-error': alignment['diagnostics'] = [{'code': 'INCOMPLETE_CORRESPONDENCES'}]
            elif change == 'missing-diagnostics': alignment.pop('diagnostics')
            elif change == 'missing-alignment': guide['source_seam_coupling'].pop('rigid_alignment')
            else: guide['source_seam_coupling']['rigid_alignment'] = None
            with self.subTest(change=change), self.assertRaises(StudioError): produce(case, guide)

    def test_whole_piece_admission_or_other_proposal_scope_is_refused(self):
        case = fixture()
        for change in ('admitted', 'truthy', 'missing-admission', 'scope', 'missing-scope'):
            guide = copy.deepcopy(case[3]); alignment = guide['source_seam_coupling']['rigid_alignment']
            if change == 'admitted': alignment['whole_piece_admission'] = True
            elif change == 'truthy': alignment['whole_piece_admission'] = 'false'
            elif change == 'missing-admission': alignment.pop('whole_piece_admission')
            elif change == 'scope': alignment['proposal_scope'] = 'QUALIFIED_PRODUCTION'
            else: alignment.pop('proposal_scope')
            with self.subTest(change=change), self.assertRaises(StudioError): produce(case, guide)

    def test_changed_source_or_semantics_identity_keeps_existing_producer_refusal(self):
        case = fixture()
        for key in ('source_sha256', 'semantics_sha256'):
            guide = copy.deepcopy(case[3]); guide[key] = 'f'*64
            with self.subTest(key=key), self.assertRaisesRegex(StudioError, 'another source geometry or semantic'):
                produce(case, guide)

    def test_fully_prepared_input_keeps_existing_assessment_none(self):
        case = fixture(); guide = copy.deepcopy(case[3]); guide['status'] = 'GARMENT_GUIDES_PREPARED'
        guide['diagnostics'] = []
        self.assertIsNone(_template_guide_assessment(case[0], guide))
        component = produce(case, guide)['components'][case[0]['component_id']]
        self.assertNotIn('guide_assessment', component)


if __name__ == '__main__':
    unittest.main()
