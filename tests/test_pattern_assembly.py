import copy
import math
import unittest

from a3d.core import StudioError, digest
from a3d.pattern_assembly import (bounded_close, consolidate, continuous_quality,
    map_digest, migrate_legacy_receipt, preform_coordinates, support_weights, validate_plan,
    verify_permanent_continuity)


def example():
    # Two square islands. The seam follows opposite oriented boundary directions.
    rest = [[0, 0, 0], [2, 0, 0], [2, 2, 0], [0, 2, 0],
            [0, 0, 1000], [2, 0, 1000], [2, 2, 1000], [0, 2, 1000]]
    panels = {}
    for pid, start in (('left', 0), ('right', 4)):
        panels[pid] = {'indices': list(range(start, start+4)),
            'boundary': list(range(start, start+4)), 'edges': {
                'bottom': [start, start+1], 'right': [start+1, start+2],
                'top': [start+2, start+3], 'left': [start+3, start]}}
    payload = {'version': 1, 'component_id': 'coupon', 'source_garment_sha256': 'source',
        'rest_cm': rest, 'placed_cm': copy.deepcopy(rest), 'panels': panels,
        'faces': [[0, 1, 2], [0, 2, 3], [4, 5, 6], [4, 6, 7]], 'pins': {},
        'seams': {'join': {'kind': 'permanent', 'piece_a': 'left', 'piece_b': 'right',
            'parameters': [0, 1], 'pairs': [[1, 4], [2, 7]]}}}
    frames = {pid: {'source_ref': 'fixture:'+pid, 'origin_cm': [x, 0., 0.],
                   'u_axis': [1., 0., 0.], 'v_axis': [0., 1., 0.]}
              for pid, x in (('left', 0.), ('right', 2.3))}
    plan = {'version': 1, 'component_id': 'coupon', 'source_refs': ['fixture:immutable'],
        'mapping_sha256': map_digest(payload), 'preform': {'panels': frames},
        'assembly': {'max_initial_gap_cm': .8, 'max_displacement_cm': .8,
            'max_step_cm': .03, 'iterations': 100, 'neighborhood_rings': 3,
            'closure_support_release': 1.}, 'consolidation': {'weld_gap_cm': .01},
        'quality': {'min_angle_degrees': 10., 'min_edge_cm': .05, 'min_stretch': .8, 'max_stretch': 1.25},
        'supports': {'temporary': [], 'drape': [], 'functional': []},
        'collision': {'required': False, 'clearance_cm': 0., 'source_ref': 'fixture:free'}}
    return payload, plan


def arc_example():
    payload, plan = example()
    # One polyline cross-section extruded orthogonally is developable. Sections
    # are source geometric data; no fitted body or source cut is invented here.
    curve = [[4*math.sin(i*.025), 0., 4*(1-math.cos(i*.025))] for i in range(61)]
    for pid, offset in (('left', 0.), ('right', 2.3)):
        plan['preform']['panels'][pid] = {'source_ref': 'fixture:measured-extruded-arc',
            'arc_sections': [{'v_cm': v, 'arc_offset_cm': offset,
                'curve_cm': [[p[0], v, p[2]] for p in curve]} for v in (0., 2.)]}
    return payload, plan


class PatternAssembly(unittest.TestCase):
    def consolidated_fixture(self):
        source,plan=example();coords,_=preform_coordinates(source,plan)
        coords,_=bounded_close(source,coords,plan)
        continuous,report=consolidate(source,coords,plan)
        return source,plan,continuous,report

    def test_consolidation_proof_verifies_source_permanent_pairs_after_zero_springs(self):
        from blender.sewing import simulation_pairs
        source,plan,continuous,report=self.consolidated_fixture()
        before=digest(continuous);proof=verify_permanent_continuity(continuous,plan['consolidation']['weld_gap_cm'])
        self.assertEqual(simulation_pairs(continuous),[])
        self.assertEqual(proof['status'],'CONTINUITY_VERIFIED')
        self.assertEqual(proof['source_permanent_pair_count'],2)
        self.assertGreater(proof['explicit_unions'],0)
        self.assertEqual(proof,report['permanent_continuity'])
        self.assertTrue(proof['current_physics_validation_required'])
        self.assertEqual(proof['qualification'],'GEOMETRY_ONLY')
        self.assertEqual(digest(continuous),before)
        self.assertEqual(source['seams']['join']['kind'],'permanent')

    def test_continuity_refuses_flags_missing_proof_stale_mapping_cohorts_and_weld_budget(self):
        _,plan,continuous,_=self.consolidated_fixture()
        for change in ('missing','checksum','faces','cohorts','mapping','rest','seam_kind','source_pairs'):
            candidate=copy.deepcopy(continuous)
            if change=='missing':candidate.pop('permanent_consolidation')
            elif change=='checksum':candidate['permanent_consolidation']['observed_pair_gap_cm']=0.
            elif change=='faces':candidate['faces'][0][0]=candidate['faces'][0][1]
            elif change=='cohorts':candidate['source_vertex_cohorts']['0'].append(999)
            elif change=='mapping':candidate['source_vertex_map']['0']=1
            elif change=='rest':candidate['rest_cm'][0][0]+=1.
            elif change=='seam_kind':candidate['seams']['join']['kind']='closure';candidate['seams']['fake']=copy.deepcopy(continuous['seams']['join'])
            else:
                proof=candidate['permanent_consolidation'];proof['source']['seams']['join']['pairs']=[]
                proof['source_mapping_sha256']=map_digest(proof['source']);candidate['source_mapping_sha256']=proof['source_mapping_sha256']
                proof['proof_sha256']=digest({k:v for k,v in proof.items() if k!='proof_sha256'})
            with self.subTest(change=change),self.assertRaises(StudioError):
                verify_permanent_continuity(candidate,plan['consolidation']['weld_gap_cm'])
        with self.assertRaisesRegex(StudioError,'weld budget'):
            verify_permanent_continuity(continuous,plan['consolidation']['weld_gap_cm']/2)

    def test_continuity_reconstructs_edges_and_openings_even_after_resigning_map(self):
        _,plan,continuous,_=self.consolidated_fixture()
        candidate=copy.deepcopy(continuous);candidate['panels']['left']['edges']['right'].reverse()
        proof=candidate['permanent_consolidation'];proof['result_mapping_sha256']=map_digest(candidate)
        proof['proof_sha256']=digest({k:v for k,v in proof.items() if k!='proof_sha256'})
        with self.assertRaisesRegex(StudioError,'source panel boundaries'):
            verify_permanent_continuity(candidate,plan['consolidation']['weld_gap_cm'])
        candidate=copy.deepcopy(continuous)
        candidate['seams']['new-detachable']={**copy.deepcopy(candidate['seams']['join']),'kind':'detachable'}
        proof=candidate['permanent_consolidation'];proof['result_mapping_sha256']=map_digest(candidate)
        proof['proof_sha256']=digest({k:v for k,v in proof.items() if k!='proof_sha256'})
        with self.assertRaisesRegex(StudioError,'source sewing pairs'):
            verify_permanent_continuity(candidate,plan['consolidation']['weld_gap_cm'])

    def test_native_bend_plan_accepts_zero_angle_but_requires_native_backend(self):
        payload, plan = example()
        plan['preform']['panels']['left']['native_bend'] = {
            'angle_degrees': 0., 'deform_axis': 'Z', 'origin_cm': [0., 0., 0.]}
        original = copy.deepcopy((payload, plan))
        self.assertEqual(validate_plan(payload, plan)['status'], 'PLAN_VALIDATED')
        with self.assertRaisesRegex(StudioError, 'requires the Blender preform backend'):
            preform_coordinates(payload, plan)
        self.assertEqual((payload, plan), original)

    def test_native_bend_callback_preserves_vertex_binding_and_existing_gates(self):
        payload, plan = example()
        reference, _ = preform_coordinates(payload, plan)
        for frame in plan['preform']['panels'].values():
            frame['native_bend'] = {'angle_degrees': 0., 'deform_axis': 'Z',
                'origin_cm': [0., 0., 0.], 'rotation_degrees': [90., 0., 0.]}
        original = copy.deepcopy((payload, plan))
        calls = []
        def evaluator(source, pid, frame):
            calls.append(pid)
            # This stub only exercises dispatch and gates; it is no Bend proof.
            return ({index: reference[index] for index in source['panels'][pid]['indices']},
                    {'backend': 'UNIT_TEST_IDENTITY_NOT_NATIVE_PROOF'})
        coords, report = preform_coordinates(payload, plan, native_evaluator=evaluator)
        self.assertEqual(coords, reference)
        self.assertEqual(calls, list(payload['panels']))
        self.assertEqual(set(report['native_backends']), set(payload['panels']))
        self.assertEqual(report['qualification'], 'NONE')
        for binding in report['correspondence']:
            ids = payload['panels'][binding['piece']]['indices']
            self.assertEqual(ids[binding['native_local_vertex']], binding['derived_vertex'])
            self.assertEqual(binding['source_uv_cm'], payload['rest_cm'][binding['derived_vertex']][:2])
        self.assertEqual((payload, plan), original)
        for failure in ('strain', 'gap'):
            def invalid(source, pid, frame):
                values, backend = evaluator(source, pid, frame)
                if failure == 'strain':
                    values = {index: [point[0], point[1]*2, point[2]] for index, point in values.items()}
                elif pid == 'right':
                    values = {index: [point[0]+4, point[1], point[2]] for index, point in values.items()}
                return values, backend
            with self.subTest(failure=failure), self.assertRaises(StudioError) as caught:
                preform_coordinates(payload, plan, native_evaluator=invalid)
            self.assertEqual(len(caught.exception.preform_coordinates_cm), len(payload['rest_cm']))
            self.assertEqual(set(caught.exception.preform_native_backends), set(payload['panels']))

    def test_native_bend_refuses_invalid_parameters_or_incomplete_backend_mapping(self):
        for problem in ('axis', 'angle_nan', 'origin_inf', 'rotation_nan', 'origin_size', 'extra', 'scale', 'mixed_variant'):
            payload, plan = example()
            frame = plan['preform']['panels']['left']
            bend = frame['native_bend'] = {'angle_degrees': 90., 'deform_axis': 'Z', 'origin_cm': [0., 0., 0.]}
            if problem == 'axis': bend['deform_axis'] = 'XY'
            elif problem == 'angle_nan': bend['angle_degrees'] = math.nan
            elif problem == 'origin_inf': bend['origin_cm'][1] = math.inf
            elif problem == 'rotation_nan': bend['rotation_degrees'] = [0., math.nan, 0.]
            elif problem == 'origin_size': bend['origin_cm'] = [0., 0.]
            elif problem == 'extra': bend['scale'] = 2.
            elif problem == 'scale': frame['u_axis'] = [2., 0., 0.]
            elif problem == 'mixed_variant':
                frame.update(arc_sections=[{'v_cm': v, 'arc_offset_cm': 0., 'curve_cm': [[0., v, 0.], [3., v, 0.]]}
                                           for v in (0., 2.)])
            with self.subTest(problem=problem), self.assertRaises(StudioError):
                validate_plan(payload, plan)
        payload, plan = example()
        frame = plan['preform']['panels']['left']
        frame['native_bend'] = {'angle_degrees': 0., 'deform_axis': 'Z', 'origin_cm': [0., 0., 0.]}
        for failure in ('missing', 'wrong_index', 'nonfinite', 'provenance'):
            def broken(source, pid, source_frame):
                values = {index: source['rest_cm'][index][:] for index in source['panels'][pid]['indices']}
                if failure == 'missing': del values[0]
                elif failure == 'wrong_index': values[10] = values.pop(0)
                elif failure == 'nonfinite': values[0][0] = math.inf
                return values, {} if failure == 'provenance' else {'backend': 'UNIT_TEST_STUB'}
            with self.subTest(failure=failure), self.assertRaises(StudioError):
                preform_coordinates(payload, plan, native_evaluator=broken)

    def test_metric_arc_extrusion_bends_source_and_quantifies_mesh_chord_approximation(self):
        from a3d.pattern_preparation import preparation_statistics
        payload, plan = arc_example()
        original = copy.deepcopy(payload)
        coords, report = preform_coordinates(payload, plan)
        self.assertGreater(max(p[2] for p in coords), 1.)
        self.assertLess(math.dist(coords[0], coords[1]), 2.)
        self.assertAlmostEqual(math.dist(coords[0], coords[3]), 2.)
        stats = preparation_statistics(payload, coords=coords)
        self.assertGreater(stats['extrema']['min_principal_stretch']['value'], .989)
        self.assertLess(stats['extrema']['min_principal_stretch']['value'], .991)
        self.assertAlmostEqual(stats['extrema']['max_principal_stretch']['value'], 1.)
        # Arc distance between u=0 and u=2 remains exactly two source cm. The
        # coarser derived edge is a chord, whose measured compression is retained.
        section = plan['preform']['panels']['left']['arc_sections'][0]
        cumulative = report['section_parameterizations']['left'][0]['cumulative_length_cm']
        path = [coords[0]]+[p for p, s in zip(section['curve_cm'], cumulative) if 0 < s < 2]+[coords[1]]
        self.assertAlmostEqual(sum(math.dist(a, b) for a, b in zip(path, path[1:])), 2.)
        binding = report['correspondence'][1]
        self.assertEqual(binding['source_uv_cm'], [2, 0])
        self.assertEqual(binding['arc_section_indices'], [0, 1])
        self.assertEqual(binding['arc_section_weights'], [1, 0])
        self.assertEqual(binding['arc_samples'][0]['arc_coordinate_cm'], 2.)
        self.assertAlmostEqual(sum(binding['arc_samples'][0]['segment_weights']), 1.)
        self.assertEqual(payload, original)

    def test_metric_sections_rebind_after_remeshing_and_translate_without_metric_change(self):
        payload, plan = arc_example()
        coords, _ = preform_coordinates(payload, plan)
        remeshed = copy.deepcopy(payload)
        for pid, index, old_faces in (('left', 8, [[0, 1, 2], [0, 2, 3]]),
                                       ('right', 9, [[4, 5, 6], [4, 6, 7]])):
            remeshed['rest_cm'].append([1., 1., 0. if pid == 'left' else 1000.])
            remeshed['placed_cm'].append([1., 1., 0.])
            remeshed['panels'][pid]['indices'].append(index)
            for old in old_faces:
                remeshed['faces'].remove(old)
            boundary = payload['panels'][pid]['boundary']
            remeshed['faces'].extend([[a, b, index] for a, b in zip(boundary, boundary[1:]+boundary[:1])])
        rebound = copy.deepcopy(plan)
        rebound['mapping_sha256'] = map_digest(remeshed)
        refined, refined_report = preform_coordinates(remeshed, rebound)
        self.assertEqual(refined[:8], coords)
        center = next(c for c in refined_report['correspondence'] if c['derived_vertex'] == 8)
        self.assertEqual(center['arc_section_weights'], [.5, .5])
        self.assertAlmostEqual(refined[8][1], 1.)
        translated_plan = copy.deepcopy(rebound)
        shift = [11., -7., 3.]
        for frame in translated_plan['preform']['panels'].values():
            for section in frame['arc_sections']:
                section['curve_cm'] = [[p[k]+shift[k] for k in range(3)] for p in section['curve_cm']]
        translated, _ = preform_coordinates(remeshed, translated_plan)
        for before, after in zip(refined, translated):
            self.assertLess(math.dist([before[k]+shift[k] for k in range(3)], after), 1e-12)

    def test_arc_section_interpolation_uses_actual_lengths_and_optional_reverse_u(self):
        payload, plan = example()
        for pid, offset in (('left', 5.), ('right', 2.7)):
            plan['preform']['panels'][pid] = {'source_ref': 'fixture:arc-reversed', 'u_direction': -1,
                'arc_sections': [{'v_cm': v, 'arc_offset_cm': offset,
                    'curve_cm': [[-8., v, 0.], [-7., v, 0.], [8., v, 0.]]} for v in (0., 2.)]}
        coords, report = preform_coordinates(payload, plan)
        self.assertAlmostEqual(coords[0][0], -3.)
        self.assertAlmostEqual(coords[1][0], -5.)
        self.assertEqual(report['correspondence'][0]['arc_samples'][0]['segment'], 1)
        self.assertAlmostEqual(report['correspondence'][0]['arc_samples'][0]['segment_weights'][1], 4/15)

    def test_arc_sections_refuse_invalid_domains_and_malformed_geometry_without_clamping(self):
        for case in ('v_order', 'zero_segment', 'nonfinite', 'below_arc', 'beyond_arc', 'outside_v', 'direction', 'mixed_variant'):
            payload, plan = arc_example()
            frame = plan['preform']['panels']['left']
            if case == 'v_order':
                frame['arc_sections'][1]['v_cm'] = 0.
            elif case == 'zero_segment':
                frame['arc_sections'][0]['curve_cm'][1] = frame['arc_sections'][0]['curve_cm'][0][:]
            elif case == 'nonfinite':
                frame['arc_sections'][0]['curve_cm'][1][0] = math.nan
            elif case == 'below_arc':
                frame['arc_sections'][0]['arc_offset_cm'] = -.000001
            elif case == 'beyond_arc':
                frame['arc_sections'][0]['arc_offset_cm'] = 100.
            elif case == 'outside_v':
                frame['arc_sections'][0]['v_cm'] = .000001
            elif case == 'direction':
                frame['u_direction'] = 0
            elif case == 'mixed_variant':
                frame['origin_cm'] = [0, 0, 0]
            with self.subTest(case=case), self.assertRaises(StudioError):
                preform_coordinates(payload, plan)

    def test_complete_pure_chain_preserves_sources_and_separate_rest_islands(self):
        payload, plan = example()
        original = copy.deepcopy(payload)
        placed, preparation = preform_coordinates(payload, plan)
        self.assertGreater(preparation['initial_gap_cm'], plan['consolidation']['weld_gap_cm'])
        closed, closure = bounded_close(payload, placed, plan)
        self.assertEqual(closure['status'], 'GEOMETRY_READY')
        self.assertGreater(closure['accepted_steps'], 1)
        self.assertLessEqual(max(s['max_step_cm'] for s in closure['history']), .03+1e-10)
        continuous, report = consolidate(payload, closed, plan)
        self.assertEqual(report['status'], 'GEOMETRY_CONSOLIDATED')
        self.assertEqual(report['qualification'], 'NONE')
        self.assertEqual(continuous['rest_mode'], 'assembled_3d')
        self.assertEqual(continuous['rest_cm'], continuous['placed_cm'])
        self.assertEqual(len(continuous['rest_cm']), 6)
        self.assertEqual(continuous['source_rest_triangles_cm'][2], [[0, 0], [2, 0], [2, 2]])
        self.assertEqual(payload, original)
        quality = continuous_quality(continuous, continuous['placed_cm'], plan['quality'])
        self.assertAlmostEqual(quality['rest_area_cm2'], 8.)
        self.assertLess(quality['max_stretch'], 1.01)

    def test_rigid_placement_invariance_and_deterministic_small_perturbations(self):
        payload, plan = example()
        reference, _ = preform_coordinates(payload, plan)
        closed, report = bounded_close(payload, reference, plan)
        angle = .03490658503988659
        def rotate(p):
            return [p[0]*math.cos(angle)-p[1]*math.sin(angle),
                    p[0]*math.sin(angle)+p[1]*math.cos(angle), p[2]]
        changed = copy.deepcopy(plan)
        for frame in changed['preform']['panels'].values():
            frame['origin_cm'] = [a+b for a, b in zip(rotate(frame['origin_cm']), [17., -31., 8.])]
            frame['u_axis'], frame['v_axis'] = rotate(frame['u_axis']), rotate(frame['v_axis'])
        transformed, _ = preform_coordinates(payload, changed)
        final, transformed_report = bounded_close(payload, transformed, changed)
        self.assertEqual(transformed_report['status'], report['status'])
        for actual, point in zip(final, closed):
            for a, b in zip(actual, [a+b for a, b in zip(rotate(point), [17., -31., 8.])]):
                self.assertAlmostEqual(a, b, places=9)
        for delta in (-.2, .1, .2):
            shifted = copy.deepcopy(plan)
            shifted['preform']['panels']['right']['origin_cm'][0] += delta
            preform, _ = preform_coordinates(payload, shifted)
            result, status = bounded_close(payload, preform, shifted)
            self.assertEqual(status['status'], 'GEOMETRY_READY')
            consolidate(payload, result, shifted)

    def test_cage_preserves_curvature_and_explicit_barycentric_mapping(self):
        payload, plan = example()
        baseline, _ = preform_coordinates(payload, plan)
        for pid, panel in payload['panels'].items():
            ids = panel['indices']
            target = [[p[0], p[1], .04*p[1]] for p in [baseline[i] for i in ids]]
            plan['preform']['panels'][pid] = {'source_ref': 'fixture:curved-master',
                'uv_cm': [payload['rest_cm'][i][:2] for i in ids], 'target_cm': target,
                'triangles': [[0, 1, 2], [0, 2, 3]]}
        coords, report = preform_coordinates(payload, plan)
        self.assertAlmostEqual(coords[2][2], .08)
        self.assertIn('barycentric_weights', report['correspondence'][0])
        self.assertEqual(len(report['correspondence']), len(payload['rest_cm']))
        result, closure = bounded_close(payload, coords, plan)
        self.assertEqual(closure['status'], 'GEOMETRY_READY')
        consolidate(payload, result, plan)

    def test_cage_holes_and_conflicting_correspondence_are_refused(self):
        payload, plan = example()
        plan['preform']['panels']['left'] = {'source_ref': 'fixture:cage',
            'uv_cm': [[0, 0], [1, 0], [0, 1]], 'target_cm': [[0, 0, 0], [1, 0, 0], [0, 1, 0]],
            'triangles': [[0, 1, 2]]}
        with self.assertRaisesRegex(StudioError, 'outside'):
            preform_coordinates(payload, plan)
        cage = plan['preform']['panels']['left']
        cage['uv_cm'] = [[0, 0], [4, 0], [0, 4]] * 2
        cage['target_cm'] = [[0, 0, 0], [4, 0, 0], [0, 4, 0], [0, 0, 1], [4, 0, 1], [0, 4, 1]]
        cage['triangles'] = [[0, 1, 2], [3, 4, 5]]
        with self.assertRaisesRegex(StudioError, 'Ambiguous'):
            preform_coordinates(payload, plan)

    def test_topological_orientation_is_checked_independently_of_world_tangents(self):
        payload, plan = example()
        payload['seams']['join']['pairs'] = [[1, 7], [2, 4]]
        plan['mapping_sha256'] = map_digest(payload)
        with self.assertRaisesRegex(StudioError, 'topological'):
            validate_plan(payload, plan)

    def test_support_roles_release_and_fixed_conflict(self):
        payload, plan = example()
        for pid, edge in (('left', 'right'), ('right', 'left')):
            plan['supports']['temporary'].append({'id': pid, 'piece': pid,
                'edge': edge, 'source_ref': 'fixture:temporary', 'weight': 1.})
        weights, _ = support_weights(payload, plan, 'assembly', .5)
        self.assertEqual(set(weights.values()), {.5})
        self.assertFalse(support_weights(payload, plan, 'relax')[0])
        coords, _ = preform_coordinates(payload, plan)
        plan['assembly']['closure_support_release'] = 0.
        unchanged, report = bounded_close(payload, coords, plan)
        self.assertEqual(report['reason_category'], 'support_conflict')
        self.assertEqual(unchanged, coords)
        plan['assembly']['closure_support_release'] = 1.
        self.assertEqual(bounded_close(payload, coords, plan)[1]['status'], 'GEOMETRY_READY')

    def test_drape_supports_persist_through_mount_and_temporary_release(self):
        payload, plan = example()
        plan['supports']['drape'] = [{'id': 'neck', 'piece': 'left', 'edge': 'top',
                                     'source_ref': 'fixture:neck', 'weight': .7}]
        for stage in ('assembly', 'mount', 'closure', 'relax', 'drape'):
            weights, report = support_weights(payload, plan, stage, release=1.)
            self.assertEqual(weights, {'2': .7, '3': .7})
            self.assertFalse(report['temporary_supports_active'])

    def test_consolidation_uses_fixed_anchor_and_reports_full_source_cohorts(self):
        payload, plan = example()
        plan['supports']['functional'] = [{'id': 'anchor', 'piece': 'left', 'edge': 'right',
            'source_ref': 'fixture:fixed-functional', 'weight': 1.}]
        plan['preform']['panels']['right']['origin_cm'][0] = 2.005
        coords, _ = preform_coordinates(payload, plan)
        source = copy.deepcopy(coords)
        continuous, report = consolidate(payload, coords, plan)
        for old in (1, 2):
            new = continuous['source_vertex_map'][str(old)]
            self.assertEqual(continuous['placed_cm'][new], source[old])
            self.assertEqual(len(continuous['source_vertex_cohorts'][str(new)]), 2)
        self.assertEqual(len(continuous['source_vertex_indices']), len(continuous['rest_cm']))
        self.assertEqual(len(report['fixed_support_anchors']), 2)
        self.assertEqual(coords, source)
        plan['supports']['functional'].append({'id': 'other', 'piece': 'right', 'edge': 'left',
            'source_ref': 'fixture:contradiction', 'weight': 1.})
        with self.assertRaisesRegex(StudioError, 'contradictory fixed cohort'):
            consolidate(payload, coords, plan)

    def test_current_triangulation_reindexing_uses_id_arc_map_not_old_indices(self):
        payload, plan = example()
        points, _ = preform_coordinates(payload, plan)
        final, _ = bounded_close(payload, points, plan)
        changed = copy.deepcopy(payload)
        permutation = [7, 2, 5, 0, 4, 3, 1, 6]
        remap = {old: new for new, old in enumerate(permutation)}
        changed['rest_cm'] = [payload['rest_cm'][i] for i in permutation]
        changed['placed_cm'] = [payload['placed_cm'][i] for i in permutation]
        changed['faces'] = [[remap[i] for i in f] for f in payload['faces']]
        for panel in changed['panels'].values():
            panel['indices'] = [remap[i] for i in panel['indices']]
            panel['boundary'] = [remap[i] for i in panel['boundary']]
            panel['edges'] = {name: [remap[i] for i in ids] for name, ids in panel['edges'].items()}
        for seam in changed['seams'].values():
            seam['pairs'] = [[remap[a], remap[b]] for a, b in seam['pairs']]
        with self.assertRaisesRegex(StudioError, 'mapping changed'):
            validate_plan(changed, plan)
        plan['mapping_sha256'] = map_digest(changed)
        placed, _ = preform_coordinates(changed, plan)
        result, report = bounded_close(changed, placed, plan)
        self.assertEqual(report['status'], 'GEOMETRY_READY')
        for old, point in enumerate(final):
            self.assertLess(math.dist(result[remap[old]], point), 1e-10)

    def test_required_collision_and_deep_contact_cannot_become_tolerance_success(self):
        payload, plan = example()
        coords, _ = preform_coordinates(payload, plan)
        plan['collision']['required'] = True
        self.assertEqual(bounded_close(payload, coords, plan)[1]['reason_category'], 'placement')
        result, report = bounded_close(payload, coords, plan,
            collision_check=lambda _: {'ok': False, 'penetration_cm': 7.8})
        self.assertEqual(result, coords)
        self.assertEqual(report['collision']['penetration_cm'], 7.8)
        self.assertEqual(report['status'], 'REFUSED')

    def test_closure_rejects_forbidden_collision_path_without_changing_input(self):
        payload, plan = example()
        coords, _ = preform_coordinates(payload, plan)
        before = copy.deepcopy(coords)
        result, report = bounded_close(payload, coords, plan,
            collision_check=lambda p: p[1][0] <= 2.000000001)
        self.assertEqual(report['status'], 'REFUSED')
        self.assertLessEqual(result[1][0], 2.000000001)
        self.assertEqual(coords, before)

    def test_distance_budget_and_stale_mapping_are_refused(self):
        payload, plan = example()
        coords, _ = preform_coordinates(payload, plan)
        with self.assertRaisesRegex(StudioError, 'tolerance'):
            consolidate(payload, coords, plan)
        changed = copy.deepcopy(payload)
        changed['rest_cm'][0][0] = .01
        with self.assertRaisesRegex(StudioError, 'mapping changed'):
            validate_plan(changed, plan)
        for i in payload['panels']['right']['indices']:
            coords[i][0] += 4.
        self.assertEqual(bounded_close(payload, coords, plan)[1]['reason'], 'initial_gap_exceeds_assembly_budget')

    def test_geometry_refusal_does_not_assert_cut_or_physics_failure(self):
        payload, plan = example()
        coords, _ = preform_coordinates(payload, plan)
        coords[0] = list(coords[1])
        result, report = bounded_close(payload, coords, plan)
        self.assertEqual(report['reason_category'], 'geometry_safety')
        self.assertEqual(report['qualification'], 'NONE')
        self.assertEqual(result, coords)

    def test_closure_detachable_seams_never_supply_weld_partners(self):
        payload, plan = example()
        payload['seams']['opening'] = {'kind': 'closure', 'piece_a': 'left', 'piece_b': 'right',
            'parameters': [0, 1], 'pairs': [[0, 5], [3, 6]]}
        plan['mapping_sha256'] = map_digest(payload)
        coords, _ = preform_coordinates(payload, plan)
        closed, _ = bounded_close(payload, coords, plan)
        continuous, report = consolidate(payload, closed, plan)
        self.assertEqual(report['explicit_unions'], 2)
        self.assertIn('opening', report['preserved_links'])
        self.assertTrue(all(a != b for a, b in continuous['seams']['opening']['pairs']))

    def test_transitive_cohort_diameter_refused_even_when_each_pair_near(self):
        # Three sectors meeting along two edges: the endpoint cohort is larger
        # than either pairwise gap. The guards run before any welded mutation.
        payload, plan = example()
        third = [[2.016, 0, 0], [2.016, -2, 0], [4.016, -2, 0], [4.016, 0, 0]]
        payload['rest_cm'].extend([[0, 0, 2000], [0, -2, 2000], [2, -2, 2000], [2, 0, 2000]])
        payload['faces'].extend([[8, 9, 10], [8, 10, 11]])
        payload['panels']['third'] = {'indices': [8, 9, 10, 11], 'boundary': [8, 9, 10, 11], 'edges': {'top': [11, 8]}}
        payload['seams']['third'] = {'kind': 'permanent', 'piece_a': 'right', 'piece_b': 'third',
            'parameters': [0, 1], 'pairs': [[4, 8], [5, 11]]}
        plan['preform']['panels']['third'] = {'source_ref': 'fixture:third', 'origin_cm': [2.016, 0, 0],
                                            'u_axis': [1, 0, 0], 'v_axis': [0, 1, 0]}
        plan['preform']['panels']['right']['origin_cm'] = [2.008, 0, 0]
        plan['mapping_sha256'] = map_digest(payload)
        coords, _ = preform_coordinates(payload, plan)
        self.assertAlmostEqual(coords[8][0], third[0][0])
        with self.assertRaisesRegex(StudioError, 'transitive cohort diameter'):
            consolidate(payload, coords, plan)

    def test_bowtie_vertex_is_rejected(self):
        from a3d.pattern_assembly import _vertex_manifold
        with self.assertRaisesRegex(StudioError, 'bowtie'):
            _vertex_manifold([[0, 1, 2], [0, 3, 4]])
        _vertex_manifold([[0, 1, 2], [0, 2, 3]])

    def test_receipt_migration_preserves_history_without_promoting_pass(self):
        receipt = {'version': 1, 'simulation': 'PASS', 'qualification': 'FREE_ASSEMBLY_ONLY',
                   'nested': {'value': 3}}
        before = digest(receipt)
        migrated = migrate_legacy_receipt(receipt)
        self.assertEqual(migrated['source_receipt_sha256'], before)
        self.assertEqual(migrated['qualification'], 'NONE')
        self.assertEqual(migrated['historical_result'], 'PASS')
        migrated['legacy_receipt']['nested']['value'] = 8
        self.assertEqual(digest(receipt), before)


if __name__ == '__main__':
    unittest.main()
