import copy
import math
import unittest

from a3d.core import StudioError, digest
from a3d.garment_guides import _source_limb_mesh
from a3d.source_seam_coupling import couple_source_seams
from tests.test_source_seam_coupling import plain, recipe


def fixture():
    def panel(height):
        return {'vertices': [[0., 0.], [4., 0.], [4., height], [0., height]],
            'faces': [[0, 1, 2], [0, 2, 3]],
            'edges': {'lower': [0, 1], 'upper': [3, 2], 'left': [0, 3], 'right': [1, 2]}}
    data = {'component_id': 'example.any-region', 'units': 'cm',
        'pieces': {'part-a': panel(7.), 'part-b': panel(10.)}, 'seams': [{
            'id': 'join', 'piece_a': 'part-a', 'edge_a': 'lower',
            'piece_b': 'part-b', 'edge_b': 'upper', 'orientation': 'forward', 'kind': 'permanent'}]}
    frames = {'part-a': plain('part-a', 0.), 'part-b': plain('part-b', 3.5)}
    frames['part-b']['origin_cm'][2] = -12.
    return data, frames, recipe(data)


def run(data, frames, declared, **options):
    return couple_source_seams(data, frames, declared, subdivisions=2,
        strategy='COUPLED_REST_METRIC_V2', relaxation=options)


def fibre(cage):
    ids = [cage['uv_cm'].index(point) for point in ([0., 0.], [0., 7.])]
    return math.dist(*(cage['target_cm'][index] for index in ids))


class CoupledAssembly(unittest.TestCase):
    def test_rigid_assembly_fixes_boundary_only_stretch_without_resetting_material(self):
        data, frames, declared = fixture(); before = digest([data, frames, declared])
        old, old_report = couple_source_seams(data, frames, declared, subdivisions=2)
        fixed, report = run(data, frames, declared)
        self.assertGreater(fibre(old['part-a']), 8.)
        self.assertAlmostEqual(fibre(fixed['part-a']), 7., delta=.001)
        self.assertLess(report['relaxation']['best']['max_seam_gap_cm'], .002)
        self.assertLess(report['relaxation']['max_principal_stretch'], 1.001)
        self.assertGreater(report['relaxation']['min_principal_stretch'], .999)
        self.assertEqual(report['status'], 'PROPOSAL_TARGETS_REACHED')
        self.assertEqual(report['qualification'], 'NONE')
        self.assertEqual(report['contact_assessment'], 'REQUIRED')
        self.assertEqual(report['permanent_relation_coverage'], 'COMPLETE_SELECTED_COMPONENT')
        self.assertEqual(digest([data, frames, declared]), before)
        for pid in fixed:
            self.assertEqual(fixed[pid]['uv_cm'], old[pid]['uv_cm'])
            self.assertEqual(fixed[pid]['triangles'], old[pid]['triangles'])

    def test_material_relaxation_reduces_existing_strain_not_only_seam_gap(self):
        data, frames, declared = fixture()
        for pid, piece in data['pieces'].items():
            uv, triangles = _source_limb_mesh(piece, 2)
            frame = frames[pid]
            frames[pid] = {'source_ref': frame['source_ref'], 'uv_cm': uv, 'triangles': triangles,
                'target_cm': [[u, frame['origin_cm'][1], frame['origin_cm'][2]+v*1.25] for u, v in uv]}
        _, report = run(data, frames, declared, max_iterations=300)
        solve = report['relaxation']
        self.assertLess(solve['best']['material_energy'], solve['initial']['material_energy']*.1)
        self.assertLess(solve['best']['max_edge_strain'], .06)
        self.assertLess(solve['best']['objective'], solve['initial']['objective'])
        self.assertFalse(report['whole_piece_admission'])

    def test_rotation_and_translation_equivariance_for_arbitrary_piece_names(self):
        data, frames, declared = fixture()
        # Proper non-axis-aligned rotation about z followed by a translation.
        angle = .731; c, s = math.cos(angle), math.sin(angle)
        def rotate(p):
            return [c*p[0]-s*p[1], s*p[0]+c*p[1], p[2]]
        def move(p):
            return [x+t for x, t in zip(rotate(p), [13., -7., 5.])]
        transformed = copy.deepcopy(frames)
        for frame in transformed.values():
            frame['origin_cm'] = move(frame['origin_cm'])
            frame['u_axis'] = rotate(frame['u_axis']); frame['v_axis'] = rotate(frame['v_axis'])
        before, a = run(data, frames, declared, max_iterations=40)
        after, b = run(data, transformed, declared, max_iterations=40)
        for pid in before:
            for first, second in zip(before[pid]['target_cm'], after[pid]['target_cm'], strict=True):
                self.assertLess(math.dist(move(first), second), 1e-8)
        self.assertAlmostEqual(a['relaxation']['best']['objective'], b['relaxation']['best']['objective'], places=11)

    def test_small_displacement_budget_preserves_best_incomplete_candidate(self):
        data, frames, declared = fixture(); before = digest([data, frames, declared])
        _, report = run(data, frames, declared, max_displacement_cm=.1, max_iterations=20)
        solve = report['relaxation']
        self.assertEqual(report['status'], 'PROPOSAL_INCOMPLETE')
        self.assertLessEqual(solve['max_displacement_cm'], .1000000001)
        self.assertGreater(solve['best']['max_seam_gap_cm'], 3.)
        self.assertLessEqual(solve['best']['objective'], solve['initial']['objective'])
        self.assertEqual(digest([data, frames, declared]), before)

    def test_iteration_budget_is_incomplete_not_qualification(self):
        data, frames, declared = fixture()
        _, report = run(data, frames, declared, rigid_iterations=0, max_iterations=1)
        solve = report['relaxation']
        self.assertEqual(solve['termination'], 'ITERATION_BUDGET_EXHAUSTED')
        self.assertEqual(solve['iterations'], 1)
        self.assertEqual(report['status'], 'PROPOSAL_INCOMPLETE')
        self.assertEqual(solve['qualification'], 'NONE')

    def test_nonzero_ease_requires_declared_uniform_distribution_and_keeps_rest_lengths(self):
        data, frames, declared = fixture()
        data['pieces']['part-b']['vertices'][1][0] = 4.2
        data['pieces']['part-b']['vertices'][2][0] = 4.2
        declared['seams']['join']['ease_b_over_a'] = .05
        with self.assertRaisesRegex(StudioError, 'easing'):
            run(data, frames, declared)
        before = digest([data, frames, declared])
        _, report = run(data, frames, declared, ease_distribution='UNIFORM_NORMALIZED_SOURCE_ARC')
        self.assertEqual(report['relations'][0]['source_chain_lengths_cm'], [4., 4.2])
        self.assertEqual(report['relations'][0]['declared_ease_b_over_a'], .05)
        self.assertFalse(report['source_uv_scaled'])
        self.assertEqual(digest([data, frames, declared]), before)

    def test_external_permanent_relations_are_explicitly_incomplete(self):
        data, frames, declared = fixture()
        data['pieces']['sleeve'] = copy.deepcopy(data['pieces']['part-a'])
        data['seams'].append({'id': 'armhole', 'piece_a': 'part-a', 'edge_a': 'right',
            'piece_b': 'sleeve', 'edge_b': 'left', 'orientation': 'forward', 'kind': 'permanent'})
        _, report = run(data, frames, recipe(data))
        self.assertEqual(report['status'], 'PROPOSAL_INCOMPLETE_SOURCE_PARTNERS')
        self.assertEqual(report['unsupported_or_missing_partners'], [
            {'id': 'armhole', 'missing_piece_ids': ['sleeve']}])
        frames['sleeve'] = plain('sleeve', 5.)
        _, complete = run(data, frames, recipe(data))
        self.assertEqual(complete['permanent_relation_coverage'], 'COMPLETE_SELECTED_COMPONENT')
        self.assertEqual({row['source_seam_id'] for row in complete['relations']}, {'armhole', 'join'})

    def test_detachable_and_closure_links_never_become_stitch_constraints(self):
        for kind in ('detachable', 'closure'):
            data, frames, declared = fixture()
            data['seams'].append({'id': 'optional', 'piece_a': 'part-a', 'edge_a': 'upper',
                'piece_b': 'part-b', 'edge_b': 'lower', 'orientation': 'forward', 'kind': kind})
            _, report = run(data, frames, recipe(data))
            self.assertEqual(report['excluded_nonpermanent_relations'], [{'id': 'optional', 'kind': kind}])
            self.assertEqual([row['source_seam_id'] for row in report['relations']], ['join'])

    def test_unary_seam_keeps_original_material_and_cannot_claim_closed_flat_band(self):
        data, frames, declared = fixture()
        data['pieces'] = {'part-a': data['pieces']['part-a']}; frames = {'part-a': frames['part-a']}
        data['seams'] = [{'id': 'band', 'piece_a': 'part-a', 'edge_a': 'right',
            'piece_b': 'part-a', 'edge_b': 'left', 'orientation': 'forward', 'kind': 'permanent'}]
        _, report = run(data, frames, recipe(data), max_iterations=20)
        self.assertEqual(report['status'], 'PROPOSAL_INCOMPLETE')
        self.assertEqual(report['relaxation']['qualification'], 'NONE')
        self.assertGreater(report['relaxation']['best']['max_seam_gap_cm'], 0.)
        self.assertFalse(report['source_uv_scaled'])

    def test_unary_precurved_tube_meets_numerical_targets_without_body_role(self):
        data, frames, declared = fixture()
        piece = data['pieces']['part-a']; data['pieces'] = {'arbitrary-tube': piece}
        data['seams'] = [{'id': 'tube-side', 'piece_a': 'arbitrary-tube', 'edge_a': 'right',
            'piece_b': 'arbitrary-tube', 'edge_b': 'left', 'orientation': 'forward', 'kind': 'permanent'}]
        uv, faces = _source_limb_mesh(piece, 8)
        radius = 4/(2*math.pi)
        frames = {'arbitrary-tube': {'source_ref': 'body-region-agnostic-cylinder', 'uv_cm': uv,
            'triangles': faces, 'target_cm': [[radius*math.sin(u/radius), radius*math.cos(u/radius), v]
                                            for u, v in uv]}}
        before = digest([data, frames])
        _, report = couple_source_seams(data, frames, recipe(data), subdivisions=8,
            strategy='COUPLED_REST_METRIC_V2', relaxation={'strain_tolerance': .03, 'max_iterations': 4})
        self.assertEqual(report['status'], 'PROPOSAL_TARGETS_REACHED')
        self.assertEqual(report['permanent_relation_coverage'], 'COMPLETE_SELECTED_COMPONENT')
        self.assertFalse(report['whole_piece_admission'])
        self.assertEqual(digest([data, frames]), before)

    def test_observations_name_actual_solver_stage(self):
        data, frames, declared = fixture()
        _, report = couple_source_seams(data, frames, declared, subdivisions=2,
            strategy='COUPLED_REST_METRIC_V2', observe_guide_stages=True)
        observed = report['guide_stage_metrics']
        self.assertEqual(observed['stage_order'][-1], 'coupled_rest_metric_proposal')
        self.assertIn('coupled_rest_metric_proposal', observed['per_piece']['part-a']['stages'])
        self.assertNotIn('seam_cohort_mean', observed['per_piece']['part-a']['stages'])

    def test_invalid_options_and_deadline_leave_inputs_unchanged(self):
        for option in ({'max_iterations': True}, {'max_displacement_cm': math.nan},
                       {'unknown': 1}, {'metric_weight': 0}, {'ease_distribution': 'invented'}):
            data, frames, declared = fixture(); before = copy.deepcopy([data, frames, declared])
            with self.subTest(option=option), self.assertRaises(StudioError):
                run(data, frames, declared, **option)
            self.assertEqual([data, frames, declared], before)
        tick = iter([0., 0., 10.])
        data, frames, declared = fixture(); before = copy.deepcopy([data, frames, declared])
        with self.assertRaises(StudioError):
            couple_source_seams(data, frames, declared, subdivisions=2,
                strategy='COUPLED_REST_METRIC_V2', clock=lambda: next(tick), budgets={'max_seconds': 1.})
        self.assertEqual([data, frames, declared], before)

    def test_numerical_anchor_ids_are_explicit_bound_for_subsequent_native_recovery(self):
        data, frames, declared = fixture()
        anchor = [{'piece': 'part-a', 'edge': 'upper'}]
        cages, report = couple_source_seams(data, frames, declared, subdivisions=2,
            strategy='COUPLED_REST_METRIC_V2', numerical_anchor_edges=anchor)
        other, changed = couple_source_seams(data, frames, declared, subdivisions=2,
            strategy='COUPLED_REST_METRIC_V2', numerical_anchor_edges=[{'piece': 'part-b', 'edge': 'lower'}])
        self.assertNotEqual(report['source_binding_sha256'], changed['source_binding_sha256'])
        self.assertEqual(cages['part-a']['target_cm'], other['part-a']['target_cm'])
        self.assertEqual(report['numerical_anchor_edges'], anchor)
        self.assertIn('NOT_FIXED_DURING_GUIDE_GENERATION', report['numerical_anchor_scope'])
        with self.assertRaisesRegex(StudioError, 'COUPLED_REST_METRIC_V2'):
            couple_source_seams(data, frames, declared, numerical_anchor_edges=anchor)
        for invalid in ([{'piece': 'missing', 'edge': 'upper'}], anchor+anchor,
                        [{'piece': 'part-a', 'edge': 'invented'}]):
            with self.assertRaises(StudioError):
                couple_source_seams(data, frames, declared, strategy='COUPLED_REST_METRIC_V2',
                    numerical_anchor_edges=invalid)

    def test_multilink_assembly_never_hides_new_shear_in_mean_energy(self):
        from tests.test_source_seam_coupling import six_piece_fixture
        data, frames, declared = six_piece_fixture()
        _, report = couple_source_seams(data, frames, declared, subdivisions=3,
            strategy='COUPLED_REST_METRIC_V2', relaxation={'max_iterations': 40})
        solved = report['relaxation']
        self.assertGreaterEqual(solved['min_principal_stretch'], .98-1e-8)
        # One original arc guide is very slightly longer than its source UV.
        upper = max(row[1] for row in solved['initial_material_trust_envelopes'].values())
        self.assertLessEqual(solved['max_principal_stretch'], upper+1e-8)
        self.assertLess(solved['best']['max_seam_gap_cm'], solved['initial']['max_seam_gap_cm'])
        self.assertEqual(report['qualification'], 'NONE')

    def test_measured_anatomical_control_stays_fixed_while_partner_is_assembled(self):
        data, frames, declared = fixture()
        attachment = {'piece': 'part-a', 'source_uv_cm': [0., 0.], 'target_world_cm': [0., 0., 0.],
            'tolerance_cm': 0., 'source_ref': 'measured.body.surface-landmark'}
        before = digest([data, frames, declared, attachment])
        cages, report = couple_source_seams(data, frames, declared, subdivisions=2,
            strategy='COUPLED_REST_METRIC_V2', anatomical_attachments=[attachment])
        index = cages['part-a']['uv_cm'].index([0., 0.])
        self.assertEqual(cages['part-a']['target_cm'][index], [0., 0., 0.])
        self.assertEqual(report['anatomical_attachments'][0]['binding_policy'], 'EXACT_SOURCE_CONTROL')
        self.assertEqual(report['anatomical_attachments'][0]['final_residual_cm'], 0.)
        self.assertLess(report['relaxation']['best']['max_seam_gap_cm'], .05)
        self.assertEqual(digest([data, frames, declared, attachment]), before)
        self.assertEqual(report['source_seam_recipe'], declared)
        self.assertEqual(report['seam_recipe_sha256'], digest(declared))

    def test_anatomical_barycentric_attachment_preserves_support_controls(self):
        data, frames, declared = fixture()
        attachment = {'piece': 'part-a', 'source_uv_cm': [.63, .87], 'target_world_cm': [.63, 0., .87],
            'tolerance_cm': 1e-9, 'source_ref': 'measured.body.path'}
        _, report = couple_source_seams(data, frames, declared, subdivisions=2,
            strategy='COUPLED_REST_METRIC_V2', anatomical_attachments=[attachment])
        result = report['anatomical_attachments'][0]
        self.assertEqual(result['binding_policy'], 'CONSERVATIVE_FIXED_BARYCENTRIC_SUPPORT_CONTROLS')
        self.assertEqual(len(result['fixed_cage_control_indices']), 3)
        self.assertEqual(result['max_fixed_control_displacement_cm'], 0.)
        self.assertLessEqual(result['final_residual_cm'], 1e-9)

    def test_incompatible_anatomical_supports_remain_fixed_and_not_admitted(self):
        data, frames, declared = fixture()
        attachments = [
            {'piece': 'part-a', 'source_uv_cm': [0., 0.], 'target_world_cm': [0., 0., 0.],
                'tolerance_cm': 0., 'source_ref': 'measured.shoulder'},
            {'piece': 'part-b', 'source_uv_cm': [0., 10.], 'target_world_cm': [0., 3.5, -2.],
                'tolerance_cm': 0., 'source_ref': 'measured.partner'}]
        _, report = couple_source_seams(data, frames, declared, subdivisions=2,
            strategy='COUPLED_REST_METRIC_V2', anatomical_attachments=attachments,
            relaxation={'max_iterations': 10})
        self.assertEqual(report['status'], 'PROPOSAL_INCOMPLETE')
        self.assertGreaterEqual(report['relaxation']['best']['max_seam_gap_cm'], math.hypot(3.5, 2.))
        self.assertTrue(all(row['max_fixed_control_displacement_cm'] == 0. for row in report['anatomical_attachments']))

    def test_invalid_or_stale_anatomical_target_refuses_without_mutation(self):
        data, frames, declared = fixture()
        attachment = {'piece': 'part-a', 'source_uv_cm': [0., 0.], 'target_world_cm': [0., 1., 0.],
            'tolerance_cm': .001, 'source_ref': 'different.pose'}
        before = copy.deepcopy([data, frames, declared, attachment])
        with self.assertRaisesRegex(StudioError, 'does not satisfy'):
            couple_source_seams(data, frames, declared, strategy='COUPLED_REST_METRIC_V2',
                anatomical_attachments=[attachment])
        self.assertEqual([data, frames, declared, attachment], before)


if __name__ == '__main__':
    unittest.main()
