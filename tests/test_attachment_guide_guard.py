import copy
import unittest
from unittest.mock import patch

from a3d.core import StudioError, digest
from a3d.attachment_guide_guard import (inspect_fixed_attachment_reserve,
    validate_attachment_guard_policy, METHOD)
from a3d.garment_guide_policy import prepare_guide_policy, reconstruct_guide_policy, verify_guide_policy
from a3d.garment_guides import garment_volume_frames
from tests.test_boundary_guide_policy import policy_fixture


def fixture():
    c, p, g, ref, data, params, recipes, docs = policy_fixture()
    cid = next(iter(data))
    native_digest = digest({'vertices_m': [[round(x/100., 7) for x in point]
        for point in g['vertices_cm']], 'faces': g['faces']})
    recipes[cid]['colliders'] = [{'object': 'Native.Body', 'geometry_sha256': native_digest,
                                'outer_thickness_cm': .3}]
    options = {'method': METHOD, 'collider_object': 'Native.Body', 'budgets': {'max_seconds': 30.}}
    params[cid]['attachment_clearance'] = {**options,
        'recipe_ref': copy.deepcopy(params[cid]['source_boundary_bindings']['recipe_ref'])}
    return c, p, g, ref, data, params, recipes, docs


class AttachmentGuideGuard(unittest.TestCase):
    def test_recipe_native_digest_encoding_matches_blender_and_is_distinct_from_profile(self):
        from blender.sewing import mesh_digest
        c, p, g, ref, data, params, recipes, docs = fixture(); cid = next(iter(data))
        vertices_m = [[x/100. for x in point] for point in g['vertices_cm']]
        with patch('blender.sewing.object_mesh', return_value=(vertices_m, g['faces'])):
            self.assertEqual(mesh_digest(object(), True), recipes[cid]['colliders'][0]['geometry_sha256'])
        self.assertNotEqual(p['geometry_sha256'], recipes[cid]['colliders'][0]['geometry_sha256'])

    def test_fixed_target_conflict_is_necessary_and_verified_targets_are_not_fit(self):
        c, p, g, ref, data, params, recipes, docs = fixture(); cid = next(iter(data))
        geometry = {'geometry': g, 'triangles': docs[cid]['triangles']}
        controls = [{'piece': 'alpha', 'source_ref': 'source-edge:selected', 'source_uv_cm': [0., 0.],
                     'target_world_cm': list(g['vertices_cm'][0])}]
        options = {k: v for k, v in params[cid]['attachment_clearance'].items() if k != 'recipe_ref'}
        args = (data[cid], controls, p, geometry, recipes[cid], options); before = digest(args)
        report = inspect_fixed_attachment_reserve(*args)
        self.assertEqual(report['status'], 'FIXED_TARGET_CLEARANCE_CONFLICTS')
        self.assertEqual(report['clearance']['conflict_count'], 1)
        self.assertTrue(report['clearance']['checks'][0]['certificate']['necessary_conflict_proved'])
        self.assertFalse(report['candidate_adjusted']); self.assertFalse(report['admissible_for_fit'])
        self.assertEqual(before, digest(args))
        controls[0]['target_world_cm'][2] = max(v[2] for v in g['vertices_cm'])+1.
        report = inspect_fixed_attachment_reserve(*args)
        self.assertEqual(report['status'], 'ALL_TARGET_CLEARANCES_VERIFIED')
        self.assertEqual(report['panel_contacts'], 'NOT_ASSESSED')
        self.assertEqual(report['global_inside_outside'], 'NOT_ASSESSED')
        self.assertEqual(report, inspect_fixed_attachment_reserve(*args))

    def test_dispatcher_blocks_coupling_before_mutation_and_keeps_source_targets(self):
        c, p, g, ref, data, params, recipes, docs = fixture(); cid = next(iter(data))
        options = {k: v for k, v in params[cid]['attachment_clearance'].items() if k != 'recipe_ref'}
        semantics = {pid: row['semantics'] for pid, row in c['textiles'].items()}
        coupling = {'strategy': 'COUPLED_REST_METRIC_V2', 'pieces': sorted(data[cid]['pieces']),
                    'subdivisions': 2, 'budgets': {'max_seconds': 30.}}
        before = digest([data, docs, g, p, recipes])
        with patch('a3d.source_seam_coupling.couple_source_seams') as solve:
            result = garment_volume_frames(data[cid], semantics, p, surface_sections=False,
                anatomical_references=docs[cid], anatomical_geometry={'geometry': g, 'triangles': docs[cid]['triangles']},
                seam_recipe=recipes[cid], attachment_clearance=options, source_seam_coupling=coupling)
            solve.assert_not_called()
        self.assertEqual(result['status'], 'PARTIAL_GUIDES')
        self.assertEqual(result['source_seam_coupling']['status'], 'NOT_EXECUTED_FIXED_ATTACHMENT_CLEARANCE_CONFLICT')
        self.assertEqual(result['anatomical_attachment_constraints']['violations'], 0)
        self.assertEqual(result['qualification'], 'NONE')
        self.assertEqual(before, digest([data, docs, g, p, recipes]))

    def test_public_guard_only_policy_replays_without_timing_fields(self):
        c, p, g, ref, data, params, recipes, docs = fixture(); cid = next(iter(data))
        params[cid].pop('source_boundary_bindings')
        policy = prepare_guide_policy(c, p, g, ref, params, source_seam_recipes=recipes, anatomical_references=docs)
        guides, evidence = reconstruct_guide_policy(c, p, g, ref, data, policy,
            source_seam_recipes=recipes, anatomical_references=docs)
        self.assertEqual(guides[cid]['attachment_clearance']['status'], 'FIXED_TARGET_CLEARANCE_CONFLICTS')
        self.assertNotIn('elapsed_seconds', guides[cid]['attachment_clearance']['clearance'])
        self.assertEqual(verify_guide_policy(c, p, g, ref, data, policy, guides,
            source_seam_recipes=recipes, anatomical_references=docs)['comparison'], 'FULL_UNROUNDED_GUIDE_REPORT_IDENTICAL')
        self.assertFalse(evidence['admissible_for_fit'])

    def test_absent_option_performs_no_new_body_check(self):
        c, p, g, ref, data, params, recipes, docs = fixture(); cid = next(iter(data))
        params[cid].pop('attachment_clearance'); params[cid].pop('source_boundary_bindings')
        policy = prepare_guide_policy(c, p, g, ref, params, anatomical_references=docs)
        with patch('a3d.attachment_guide_guard.inspect_fixed_attachment_reserve') as inspect:
            guides, _ = reconstruct_guide_policy(c, p, g, ref, data, policy, anatomical_references=docs)
            inspect.assert_not_called()
        self.assertNotIn('attachment_clearance', guides[cid])

    def test_changed_body_recipe_triangulation_or_missing_fixed_targets_refuse(self):
        c, p, g, ref, data, params, recipes, docs = fixture(); cid = next(iter(data))
        options = {k: v for k, v in params[cid]['attachment_clearance'].items() if k != 'recipe_ref'}
        controls = [{'piece': 'alpha', 'source_ref': 'source-edge:selected', 'source_uv_cm': [0., 0.],
                     'target_world_cm': list(g['vertices_cm'][0])}]
        args = [data[cid], controls, p, {'geometry': g, 'triangles': docs[cid]['triangles']}, recipes[cid], options]
        def change(values, kind):
            if kind == 'body': values[3]['geometry']['vertices_cm'][0][0] += .1
            elif kind == 'triangles': values[3]['triangles'][0].reverse()
            elif kind == 'collider': values[4]['colliders'][0]['geometry_sha256'] = 'f'*64
            elif kind == 'duplicate': values[4]['colliders'] *= 2
            elif kind == 'component': values[4]['component_id'] = 'another'
            else: values[1].clear()
        for kind in ('body', 'triangles', 'collider', 'duplicate', 'component', 'no-targets'):
            values = copy.deepcopy(args); change(values, kind)
            with self.subTest(kind=kind), self.assertRaises(StudioError):
                inspect_fixed_attachment_reserve(*values)
        ticks = iter(range(1000000)); values = copy.deepcopy(args); values[-1]['budgets']['max_seconds'] = .5
        with self.assertRaisesRegex(StudioError, 'budget'):
            inspect_fixed_attachment_reserve(*values, clock=lambda: float(next(ticks)))

    def test_policy_recipe_conflict_missing_anatomy_and_unbounded_inputs_refuse(self):
        for kind in ('recipe-conflict', 'missing-anatomy', 'bad-budget'):
            c, p, g, ref, data, params, recipes, docs = fixture(); cid = next(iter(data))
            if kind == 'recipe-conflict': params[cid]['attachment_clearance']['recipe_ref']['sha256'] = 'c'*64
            elif kind == 'missing-anatomy': params[cid].pop('anatomical_references_ref')
            else: params[cid]['attachment_clearance']['budgets']['max_seconds'] = 61.
            with self.subTest(kind=kind), self.assertRaises(StudioError):
                prepare_guide_policy(c, p, g, ref, params, source_seam_recipes=recipes, anatomical_references=docs)
        for value in (True, float('nan'), float('inf'), 10**1000, -1):
            with self.subTest(value=str(value)[:12]), self.assertRaises(StudioError):
                validate_attachment_guard_policy({'method': METHOD, 'collider_object': 'body',
                                                   'budgets': {'max_seconds': value}})
