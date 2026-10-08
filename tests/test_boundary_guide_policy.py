"""Public, reproducible current-boundary diagnostics with native source inputs."""
import copy
from types import SimpleNamespace
from unittest.mock import patch

from a3d.core import StudioError, atomic_json, digest, sha
from a3d.garment_guide_policy import (prepare_guide_policy, reconstruct_guide_policy,
    verify_guide_policy, prepare_project_guide_policy, verify_project_guides, CODE_SOURCES)
from a3d.garment_guides import garment_volume_frames
from a3d.shoulder_surface import measured_surface_shoulders
from a3d.source_boundary_bindings import inspect_current_source_boundaries
from tests.test_core import Case
from tests.test_garment_guide_policy import fixture as public_fixture
from tests.test_shoulder_surface import fixture as body_fixture
from tests.test_source_boundary_bindings import fixture as binding_fixture


def fixture():
    data, frames, recipe, _, _, document, policy = binding_fixture()
    base, geometry, triangles = body_fixture()
    geometry['face_sets'] = [11, 10, 11, 11, 11, 11]
    profile = measured_surface_shoulders(base, geometry, triangles)
    profile.update(status='PROFILE_MEASURED', segmentation='EXPLICIT_SOURCE')
    # Remeasure after these profile fields are authored, retaining provenance.
    base.update(status='PROFILE_MEASURED', segmentation='EXPLICIT_SOURCE')
    profile = measured_surface_shoulders(base, geometry, triangles)
    vertices = [4, 5, 7, 6]
    edges = list(zip(vertices, vertices[1:]+vertices[:1]))
    incidences = [[fid for fid, face in enumerate(geometry['faces']) if any(
        {a, b} == {x, y} for x, y in zip(face, face[1:]+face[:1]))] for a, b in edges]
    report = {'version': 1, 'status': 'BODY_SOURCE_PATHS_MEASURED_FOR_REVIEW',
        'frame': copy.deepcopy(profile['frame']), 'paths': [{'id': 'measured', 'closed': True,
            'vertex_ids': vertices, 'edge_vertex_ids': list(map(list, edges)), 'edge_source_face_ids': incidences,
            'curve_world_cm': [geometry['vertices_cm'][i] for i in vertices],
            'length_cm': 120., 'source_regions': [10, 11]}],
        'identity': {key: profile[key] for key in ('geometry_sha256', 'source_sha256', 'pose_sha256')}}
    report['identity'].update(profile_sha256=digest(profile), profile_cache_key=profile['cache_key'],
                              face_sets_sha256=digest(geometry['face_sets']))
    document.update(profile_sha256=digest(profile), triangles=triangles)
    document['paths']['chosen'].update(report=report, report_sha256=digest(report))
    for pid, piece in data['pieces'].items():
        for uv in piece['vertices']: uv[0] *= 120./14.
        for uv in frames[pid]['uv_cm']: uv[0] *= 120./14.
        frames[pid]['target_cm'] = [[-7.8+u*.1, -4., 100.1+v] for u, v in frames[pid]['uv_cm']]
    document['pieces']['alpha']['longitudinal_direction_body'] = [0., 0., 1.]
    policy['continuation'] = {'method': 'SEEDED_SURFACE_PATH_LIFT_V2', 'min_cosine': .05, 'max_events': 200000}
    return data, frames, recipe, profile, geometry, document, policy


def policy_fixture():
    data, frames, recipe, profile, geometry, document, inspection = fixture()
    compiled, _, _, ref, _, _ = public_fixture()
    component = data['component_id']
    compiled['components'][0]['id'] = component
    document['pieces']['beta'] = copy.deepcopy(document['pieces']['alpha'])
    semantics = {pid: {'role': 'panel', 'side': 'center', 'layer': 'cloth', 'longitudinal_uv_axis': 'u'} for pid in data['pieces']}
    compiled['textiles'] = {pid: {'component_id': component, 'source_geometry': piece,
        'semantics': semantics[pid]} for pid, piece in data['pieces'].items()}
    parameters = {component: {'upper_blend': 1., 'surface_sections': False, 'skin_section_heights_cm': [],
        'anatomical_references_ref': {'path': 'references.json', 'sha256': '1'*64},
        'source_boundary_bindings': {**inspection, 'recipe_ref': {'path': 'recipe.json', 'sha256': '2'*64}}}}
    return compiled, profile, geometry, ref, {component: data}, parameters, {component: recipe}, {component: document}


class BoundaryGuidePolicy(Case):
    def test_current_queries_trace_real_native_surface_without_mutation_or_timing_evidence(self):
        args = fixture(); before = digest(args)
        first = inspect_current_source_boundaries(*args)
        second = inspect_current_source_boundaries(*args)
        self.assertEqual(first, second)
        self.assertEqual(digest(args), before)
        observed = first['current_surface_observations']
        self.assertEqual(len(observed['observations']), 3)
        self.assertEqual(observed['refused_paths'], 0)
        self.assertEqual(observed['reserve_pending'], 3)
        for row in observed['observations']:
            self.assertAlmostEqual(row['selected_plane_reserve']['additional_directional_correction_cm'], .2)
            self.assertNotIn('elapsed_seconds', row['continuation'])
        self.assertFalse(first['candidate_adjusted'])
        self.assertEqual(first['new_fixed_anatomical_constraints'], 0)
        self.assertEqual(observed['whole_body_segment_contact_admission'], 'NOT_GRANTED')
        changed = copy.deepcopy(args)
        for point in changed[1]['beta']['target_cm']: point[2] += .4
        after = inspect_current_source_boundaries(*changed)
        self.assertNotEqual(after['binding_set_sha256'], first['binding_set_sha256'])
        self.assertEqual(after['current_surface_observations']['reserve_pending'], 0)

    def test_terminal_triangle_edge_does_not_admit_an_uncertified_normal_cone(self):
        args = fixture()
        for point in args[1]['beta']['target_cm']: point[0] -= .2
        result = inspect_current_source_boundaries(*args)
        first = result['current_surface_observations']['observations'][0]
        self.assertEqual(first['continuation']['status'], 'LOCAL_PATH_LIFT_REACHED')
        self.assertEqual(first['selected_plane_reserve']['status'], 'NOT_VERIFIABLE_ENDPOINT_NORMAL_CONE')

    def test_declared_displacement_budget_precedes_small_reserve_residual_tolerance(self):
        args = fixture()
        args[-2]['pieces']['beta']['surface_envelope'].update(
            direction_body=[1., 0., .01], reserve_cm=1e-10, max_displacement_cm=1e-10)
        args[-1]['continuation']['min_cosine'] = .005
        for point in args[1]['beta']['target_cm']: point[2] -= .1
        result = inspect_current_source_boundaries(*args)
        self.assertEqual(result['status'], 'PARTIAL_BOUNDARY_CONTINUATION')
        self.assertEqual(result['current_surface_observations']['reserve_pending'], 3)
        for row in result['current_surface_observations']['observations']:
            measured = row['selected_plane_reserve']
            self.assertLess(measured['additional_directional_correction_cm'], 1e-7)
            self.assertFalse(measured['within_declared_displacement_budget'])
            self.assertEqual(measured['status'], 'DECLARED_DISPLACEMENT_BUDGET_EXCEEDED')

    def test_finite_grazing_input_keeps_unrepresentable_correction_out_of_canonical_report(self):
        args = fixture()
        args[-2]['pieces']['beta']['surface_envelope']['direction_body'] = [1., 0., 1e-309]
        args[-1]['continuation']['min_cosine'] = 1e-310
        for point in args[1]['beta']['target_cm']: point[2] -= .1
        before = digest(args)
        result = inspect_current_source_boundaries(*args)
        self.assertEqual(result['status'], 'PARTIAL_BOUNDARY_CONTINUATION')
        self.assertEqual(result['current_surface_observations']['reserve_pending'], 3)
        self.assertEqual(digest(args), before)
        self.assertEqual(len(digest(result)), 64)
        for row in result['current_surface_observations']['observations']:
            measured = row['selected_plane_reserve']
            self.assertEqual(row['continuation']['status'], 'LOCAL_PATH_LIFT_REACHED')
            self.assertEqual(measured['status'], 'DIRECTIONAL_CORRECTION_NOT_REPRESENTABLE')
            self.assertNotIn('additional_directional_correction_cm', measured)
            self.assertFalse(measured['within_declared_displacement_budget'])

    def test_common_budget_exhaustion_or_changed_native_surface_refuses_complete_public_report(self):
        args = fixture(); args[-1]['continuation']['max_events'] = 1
        with self.assertRaisesRegex(StudioError, 'budget'):
            inspect_current_source_boundaries(*args)
        args = fixture(); ticks = iter(range(1000000))
        with self.assertRaisesRegex(StudioError, 'budget'):
            inspect_current_source_boundaries(*args, clock=lambda: float(next(ticks)))
        args = fixture(); args[-2]['triangles'][0].reverse()
        with self.assertRaisesRegex(StudioError, 'triangulation'):
            inspect_current_source_boundaries(*args)
        args = fixture(); args[-1]['query_target_kind'] = 'HOMOLOGOUS_DRIVER_BOUNDARY_TARGET'
        with self.assertRaisesRegex(StudioError, 'current partner'):
            inspect_current_source_boundaries(*args)

    def test_public_preparation_and_exact_replay_preserve_missing_domain_and_solver_supports(self):
        c, p, g, ref, data, params, recipes, references = policy_fixture()
        before = digest([c, p, g, ref, data, params, recipes, references])
        policy = prepare_guide_policy(c, p, g, ref, params, source_seam_recipes=recipes, anatomical_references=references)
        guides, evidence = reconstruct_guide_policy(c, p, g, ref, data, policy, source_seam_recipes=recipes, anatomical_references=references)
        result = guides['arbitrary.component']; binding = result['source_boundary_bindings']
        self.assertEqual(result['status'], 'PARTIAL_GUIDES')
        self.assertTrue(binding['unresolved_anatomical_inputs'])
        self.assertTrue(all(row['sewing_support_status'] == 'BOTH_CURRENT_CAGE_SUPPORTS_PREPARED' for row in binding['bindings']))
        self.assertEqual(binding['identities']['frames_sha256'], digest(result['panels']))
        self.assertEqual(binding['current_surface_observations']['frames_sha256'], digest(result['panels']))
        self.assertEqual(verify_guide_policy(c, p, g, ref, data, policy, guides,
            source_seam_recipes=recipes, anatomical_references=references)['comparison'], 'FULL_UNROUNDED_GUIDE_REPORT_IDENTICAL')
        self.assertFalse(evidence['admissible_for_fit'])
        self.assertEqual(before, digest([c, p, g, ref, data, params, recipes, references]))
        self.assertIn('source_boundary_bindings', CODE_SOURCES)
        self.assertIn('surface_path_continuation', CODE_SOURCES)

    def test_absent_option_preserves_exact_dispatcher_output_and_does_not_trace(self):
        c, p, g, ref, data, params, recipes, refs = policy_fixture(); cid = 'arbitrary.component'
        params[cid].pop('source_boundary_bindings')
        policy = prepare_guide_policy(c, p, g, ref, params, anatomical_references=refs)
        with patch('a3d.source_boundary_bindings.inspect_current_source_boundaries') as inspect:
            guides, _ = reconstruct_guide_policy(c, p, g, ref, data, policy, anatomical_references=refs)
            inspect.assert_not_called()
        semantics = {pid: row['semantics'] for pid, row in c['textiles'].items()}
        expected = garment_volume_frames(data[cid], semantics, p, surface_sections=False,
            anatomical_references=refs[cid], anatomical_geometry={'geometry': g, 'triangles': refs[cid]['triangles']})
        self.assertEqual(guides[cid], expected)
        self.assertNotIn('source_boundary_bindings', expected)

    def test_policy_refuses_undeclared_anatomy_old_targets_conflicting_recipes_and_code_drift(self):
        args = policy_fixture(); c, p, g, ref, data, params, recipes, refs = args; cid = 'arbitrary.component'
        for change in ('no-anatomy', 'driver-target', 'bad-method', 'recipe-conflict', 'budget', 'zero-cosine', 'unit-cosine'):
            values = copy.deepcopy(params)
            if change == 'no-anatomy': values[cid].pop('anatomical_references_ref')
            elif change == 'driver-target': values[cid]['source_boundary_bindings']['query_target_kind'] = 'HOMOLOGOUS_DRIVER_BOUNDARY_TARGET'
            elif change == 'bad-method': values[cid]['source_boundary_bindings']['continuation']['method'] = 'SEEDED_SURFACE_PATH_LIFT_V1'
            elif change == 'budget': values[cid]['source_boundary_bindings']['budgets']['max_seconds'] = 121
            elif change == 'zero-cosine': values[cid]['source_boundary_bindings']['continuation']['min_cosine'] = 0
            elif change == 'unit-cosine': values[cid]['source_boundary_bindings']['continuation']['min_cosine'] = 1
            else: values[cid]['source_seam_coupling'] = {'recipe_ref': {'path': 'other.json', 'sha256': '3'*64}}
            with self.subTest(change=change), self.assertRaises(StudioError):
                prepare_guide_policy(c, p, g, ref, values, source_seam_recipes=recipes, anatomical_references=refs)
        policy = prepare_guide_policy(c, p, g, ref, params, source_seam_recipes=recipes, anatomical_references=refs)
        policy['generator_code_sha256']['source_boundary_bindings'] = 'f'*64
        with self.assertRaisesRegex(StudioError, 'code is stale'):
            reconstruct_guide_policy(c, p, g, ref, data, policy, source_seam_recipes=recipes, anatomical_references=refs)

    def test_project_loader_authenticates_recipe_reports_and_native_triangles_for_optional_inspection(self):
        c, p, g, ref, data, params, recipes, refs = policy_fixture(); cid = 'arbitrary.component'
        def store(name, value):
            atomic_json(self.root/name, value)
            return {'path': name, 'sha256': sha(self.root/name)}
        spec = copy.deepcopy(refs[cid]); spec['triangles_ref'] = store('triangles.json', spec.pop('triangles'))
        for name, row in list(spec['paths'].items()):
            spec['paths'][name] = {'report_ref': store('native-path.json', row['report']),
                                  'path_id': row['path_id'], 'region': row['region']}
        params[cid]['anatomical_references_ref'] = store('references.json', spec)
        params[cid]['source_boundary_bindings']['recipe_ref'] = store('recipe.json', recipes[cid])
        project = SimpleNamespace(root=self.root)
        with patch('a3d.garment_guide_policy._project_inputs', return_value=(p, g, ref, data, {'native': True})):
            policy, _ = prepare_project_guide_policy(project, c, params)
            guides, _ = reconstruct_guide_policy(c, p, g, ref, data, policy, source_seam_recipes=recipes, anatomical_references=refs)
            store('policy.json', policy)
            verify_project_guides(project, c, guides, 'policy.json')
            for name in ('recipe.json', 'native-path.json', 'triangles.json'):
                original = (self.root/name).read_bytes()
                (self.root/name).write_bytes(original+b' ')
                with self.subTest(name=name), self.assertRaisesRegex(StudioError, 'artifact changed'):
                    verify_project_guides(project, c, guides, 'policy.json')
                (self.root/name).write_bytes(original)
