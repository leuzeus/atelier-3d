"""Exact source ease survives the real guide-to-native-template boundary."""
import copy
import unittest

from a3d.core import ROOT, StudioError, digest, read_json
from a3d.garment_planner import plan_assembly
from a3d.source_seam_coupling import couple_source_seams
from a3d.textile_executor import prepare_component_templates
from tests.test_assembly_relaxation import fixture
from tests.test_garment_planner import example


def inputs(ease=.05):
    data, frames, declared = fixture()
    for point in data['pieces']['part-b']['vertices']:
        point[0] *= 1+ease
    declared['seams']['join'].update(ease_b_over_a=ease, tolerance_relative=.003)
    data['material'] = {'mass_kg': .3, 'tension_stiffness': 15, 'compression_stiffness': 15,
                        'shear_stiffness': 5, 'bending_stiffness': .5}
    for piece in data['pieces'].values():
        piece.update(position_cm=[0., 0., 0.], rotation_degrees=[0., 0., 0.])
    cages, report = couple_source_seams(data, frames, declared, subdivisions=2,
        strategy='COUPLED_REST_METRIC_V2',
        relaxation={'ease_distribution': 'UNIFORM_NORMALIZED_SOURCE_ARC', 'strain_tolerance': .04,
                    'seam_weight': 1000., 'max_iterations': 400},
        numerical_anchor_edges=[{'piece': 'part-a', 'edge': 'upper'}])
    ref = {'path': 'source.garmentpkg', 'sha256': digest(data)}
    semantics = {pid: {'role': 'panel', 'side': 'center', 'layer': 'cloth'} for pid in data['pieces']}
    specification = {'version': 1, 'source_ref': ref, 'body_ref': ref,
        'pieces': [{**semantics[pid], 'id': pid, 'component_id': data['component_id'],
                    'edges': sorted(piece['edges']), 'source_ref': ref} for pid, piece in data['pieces'].items()],
        'links': [{**{k: s[k] for k in ('id', 'kind', 'piece_a', 'piece_b', 'edge_a', 'edge_b')},
                   'source_ref': ref} for s in data['seams']],
        'budgets': example()['budgets'],
        'layers': {'version': 1, 'source_ref': ref, 'mode': 'single', 'interaction': 'one_way_declared',
            'nodes': [{'id': 'cloth', 'kind': 'garment', 'panels': sorted(data['pieces']),
                       'colliders': [], 'source_ref': ref}], 'inside_to_outside': []}}
    guide = {'status': 'GARMENT_GUIDES_PREPARED', 'panels': cages, 'source_seam_coupling': report,
        'source_sha256': digest(data), 'semantics_sha256': digest(semantics),
        'profile_sha256': 'a'*64, 'profile_cache_key': 'b'*64}
    return [plan_assembly(specification), {data['component_id']: {'source_ref': ref, 'data': data}},
        {data['component_id']: guide}, read_json(ROOT/'templates/sewing-recipe.json'), {'units': 'cm'}, ref]


class ExactSeamPreparation(unittest.TestCase):
    def test_all_final_attachments_reach_native_template_with_or_without_coupling(self):
        from a3d.garment_guides import anatomical_attachment_residuals
        from a3d.pattern_assembly import _cage_point, _compile_cage
        for coupled in (False, True):
            arguments = inputs(ease=0.)
            guide = arguments[2]['example.any-region']
            controls = []
            for pid, uv in [('part-a', [0., 7.]), ('part-b', [0., 0.])]:
                cage = guide['panels'][pid]
                target = _cage_point(cage, _compile_cage(cage, pid), uv, pid)[0]
                controls.append({'piece': pid, 'source_uv_cm': uv, 'target_world_cm': target,
                    'tolerance_cm': 1e-7, 'source_ref': 'synthetic:measured-attachment'})
            guide['anatomical_attachment_constraints'] = anatomical_attachment_residuals(guide['panels'], controls)
            if coupled:
                # One constraint also appears in the coupled subset. Both
                # final guide controls must survive, without duplicating it.
                guide['source_seam_coupling']['anatomical_attachments'] = controls[:1]
            else:
                guide.pop('source_seam_coupling')
            result = prepare_component_templates(*arguments)
            declarations = result['components']['example.any-region']['preparation_template']['anatomical_attachments']
            self.assertEqual({digest(row) for row in declarations}, {digest(row) for row in controls})
            self.assertEqual(len(declarations), 2)

    def test_five_percent_ease_and_custom_tolerance_survive_native_template_preparation(self):
        arguments = inputs(); before = digest(arguments)
        result = prepare_component_templates(*arguments)
        component = result['components']['example.any-region']
        self.assertEqual(component['recipe_template']['seams']['join'],
            {'kind': 'permanent', 'ease_b_over_a': .05, 'tolerance_relative': .003})
        self.assertEqual(component['recipe_provenance']['seam_ease'], 'EXACT_SOURCE_RECIPE_BOUND_TO_GUIDES')
        self.assertEqual(result['simulation'], 'NOT_EXECUTED')
        self.assertEqual(digest(arguments), before)

    def test_missing_or_changed_source_sewing_recipe_refuses_instead_of_default_zero_ease(self):
        base = inputs()
        for change in ('missing', 'changed'):
            arguments = copy.deepcopy(base)
            coupling = arguments[2]['example.any-region']['source_seam_coupling']
            if change == 'missing':
                coupling.pop('source_seam_recipe', None)
            else:
                coupling['source_seam_recipe']['seams']['join']['ease_b_over_a'] = 0.
            with self.assertRaisesRegex(StudioError, 'exact source sewing recipe'):
                prepare_component_templates(*arguments)
