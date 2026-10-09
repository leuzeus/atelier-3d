import copy
import json
import math
import unittest
from unittest.mock import patch

from a3d.core import StudioError, digest
from a3d.rigid_guide_alignment import (_complete_rows, _prepare_front_rigid_seeds,
    prepare_role_rigid_seeds, proper_rigid_fit, transform)
from a3d.source_seam_coupling import _Budget, _prepare_piece, couple_source_seams


def budget():
    return _Budget({}, lambda: 0.)


def point_rows(points=None, mapped=None):
    points = points or [[0., 0., 0.], [1., 0., 0.], [0., 2., 0.], [1., 2., .5]]
    mapped = mapped or (lambda p: [4.-p[1], -3.+p[0], 2.+p[2]])
    return [{'source_point_cm': p, 'target_point_cm': mapped(p), 'weight': index+1.}
            for index, p in enumerate(points)]


def fixture(extra=None):
    def rectangle(left, right):
        return {'vertices': [[left, 0.], [right, 0.], [right, 3.], [left, 3.]],
            'faces': [[0, 1, 2], [0, 2, 3]],
            'edges': {'a': [1, 2], 'b': [3, 0], 'top': [2, 3], 'bottom': [0, 1]}}
    pieces = {'mobile': rectangle(-2., 2.), 'a': rectangle(-6., -2.), 'b': rectangle(2., 6.)}
    seams = [dict(id='join-a', piece_a='a', edge_a='a', piece_b='mobile', edge_b='b',
                  kind='permanent', orientation='reverse'),
             dict(id='join-b', piece_a='b', edge_a='b', piece_b='mobile', edge_b='a',
                  kind='permanent', orientation='reverse')]
    semantics = {'mobile': {'role': 'inner_front'}, 'a': {'role': 'front'}, 'b': {'role': 'front'}}
    frames = {pid: {'source_ref': 'approved:'+pid, 'origin_cm': [0., 0., 0.],
        'u_axis': [1., 0., 0.], 'v_axis': [0., 0., 1.]} for pid in pieces}
    frames['mobile'].update(origin_cm=[10., 4., 8.], u_axis=[-1., 0., 0.])
    if extra == 'closure':
        seams.append(dict(id='not-a-sewn-join', piece_a='mobile', edge_a='top', piece_b='b', edge_b='top',
                          kind='closure', orientation='forward'))
    elif extra == 'collar':
        pieces['other'] = rectangle(-2., 2.)
        frames['other'] = {'source_ref': 'approved:other', 'origin_cm': [0., 6., 0.],
            'u_axis': [1., 0., 0.], 'v_axis': [0., 0., 1.]}
        semantics['other'] = {'role': 'collar'}
        seams.append(dict(id='remaining-neck-link', piece_a='mobile', edge_a='bottom', piece_b='other', edge_b='top',
                          kind='permanent', orientation='reverse'))
    data = {'component_id': 'fixture.alignment', 'units': 'cm', 'pieces': pieces, 'seams': seams}
    recipe = {'component_id': data['component_id'], 'seams': {row['id']:
        {'kind': row['kind'], 'ease_b_over_a': 0., 'tolerance_relative': 0.} for row in seams}}
    return data, frames, recipe, semantics


def prepared(extra=None):
    data, frames, recipe, semantics = fixture(extra)
    _, legacy = couple_source_seams(data, frames, recipe, subdivisions=3, clock=lambda: 0.)
    shared = budget()
    states = {pid: _prepare_piece(data['pieces'][pid], frame, pid, 3, shared) for pid, frame in frames.items()}
    return data, semantics, states, legacy['relations'], shared


def collar_fixture(*, joint=False, nonpermanent=False):
    data, frames, recipe, semantics = fixture('collar' if joint else None)
    if not joint:
        semantics['mobile']['role'] = 'collar'
        collar = 'mobile'
    else:
        collar = 'other'
        # Two independent torso partners and the already seeded inner front
        # share one congruent target collar. Source edge identities stay exact.
        frames[collar].update(origin_cm=[10., 6., 8.], u_axis=[-1., 0., 0.])
        for partner, source, edge, collar_edge in (('c', 'a', 'a', 'b'), ('d', 'b', 'b', 'a')):
            data['pieces'][partner] = copy.deepcopy(data['pieces'][source])
            frames[partner] = {'source_ref': 'approved:'+partner, 'origin_cm': [0., 0., -3.],
                'u_axis': [1., 0., 0.], 'v_axis': [0., 0., 1.]}
            semantics[partner] = {'role': 'front'}
            data['seams'].append(dict(id='collar-'+partner, piece_a=partner, edge_a=edge,
                piece_b=collar, edge_b=collar_edge, kind='permanent', orientation='reverse'))
    if nonpermanent:
        for sid, kind, partner, edge in (('declared-closure', 'closure', 'a', 'bottom'),
                                        ('declared-detachable', 'detachable', 'b', 'top')):
            data['seams'].append(dict(id=sid, piece_a=collar, edge_a=edge,
                piece_b=partner, edge_b=edge, kind=kind, orientation='forward'))
    recipe['seams'] = {seam['id']: {'kind': seam['kind'], 'ease_b_over_a': 0.,
        'tolerance_relative': 0.} for seam in data['seams']}
    return data, frames, recipe, semantics, collar


def prepared_collar(**kwargs):
    data, frames, recipe, semantics, collar = collar_fixture(**kwargs)
    _, legacy = couple_source_seams(data, frames, recipe, subdivisions=3, clock=lambda: 0.)
    shared = budget()
    states = {pid: _prepare_piece(data['pieces'][pid], frame, pid, 3, shared)
              for pid, frame in frames.items()}
    return data, semantics, states, legacy['relations'], shared, collar


class RigidGuideAlignment(unittest.TestCase):
    def test_exact_rigid_transform_preserves_distances_and_input(self):
        rows = point_rows(); before = copy.deepcopy(rows)
        fit = proper_rigid_fit(rows, budget())
        self.assertEqual(fit['status'], 'RIGID_SEED_PROPOSED')
        self.assertLess(fit['after']['max_gap_cm'], 1e-12)
        self.assertAlmostEqual(fit['rotation_determinant'], 1., places=12)
        self.assertLessEqual(fit['numerical']['horn']['rotations'], 64)
        for a in rows:
            for b in rows:
                self.assertAlmostEqual(math.dist(transform(fit, a['source_point_cm']), transform(fit, b['source_point_cm'])),
                    math.dist(a['source_point_cm'], b['source_point_cm']), places=12)
        self.assertEqual(rows, before)

    def test_correspondence_order_and_json_replay_are_deterministic(self):
        rows = point_rows()
        fit = proper_rigid_fit(rows, budget())
        self.assertEqual(fit, proper_rigid_fit(list(reversed(rows)), budget()))
        self.assertEqual(json.loads(json.dumps(fit, allow_nan=False)), fit)
        self.assertEqual(fit, proper_rigid_fit(json.loads(json.dumps(rows)), budget()))

    def test_rotation_and_translation_equivariance(self):
        rows = point_rows(); fit = proper_rigid_fit(rows, budget())
        world = lambda p: [100.+p[2], -70.+p[1], 20.-p[0]]
        moved = [{**row, 'source_point_cm': world(row['source_point_cm']), 'target_point_cm': world(row['target_point_cm'])} for row in rows]
        again = proper_rigid_fit(moved, budget())
        for row in rows:
            self.assertLess(math.dist(world(transform(fit, row['source_point_cm'])),
                transform(again, world(row['source_point_cm']))), 1e-12)

    def test_scale_required_retains_residual_without_scaling_source(self):
        rows = point_rows(mapped=lambda p: [1.2*x for x in p])
        fit = proper_rigid_fit(rows, budget())
        self.assertEqual(fit['qualification'], 'NONE')
        self.assertGreater(fit['after']['max_gap_cm'], .1)
        self.assertAlmostEqual(math.dist(transform(fit, rows[0]['source_point_cm']), transform(fit, rows[-1]['source_point_cm'])),
            math.dist(rows[0]['source_point_cm'], rows[-1]['source_point_cm']), places=12)

    def test_degenerate_near_collinear_and_reflection_ambiguous_refused(self):
        for points in ([[[float(i), 0., 0.] for i in range(4)],
                [[float(i), (i % 2)*1e-10, 0.] for i in range(4)], [[0., 0., 0.]]*4]):
            with self.subTest(points=points):
                self.assertEqual(proper_rigid_fit(point_rows(points), budget())['status'], 'RIGID_FRAME_AMBIGUOUS')
        points = [[1., 1., 1.], [-1., -1., 1.], [-1., 1., -1.], [1., -1., -1.]]
        rows = [{'source_point_cm': p, 'target_point_cm': [-p[0], p[1], p[2]], 'weight': 1.} for p in points]
        refused = proper_rigid_fit(rows, budget())
        self.assertEqual(refused['status'], 'RIGID_FRAME_AMBIGUOUS')
        self.assertIn('horn', refused['numerical'])

    def test_nonfinite_weights_and_points_refused(self):
        for key, value in (('weight', float('nan')), ('weight', -1.), ('weight', True),
                ('source_point_cm', [float('inf'), 0., 0.]), ('target_point_cm', [0., 0.])):
            rows = point_rows(); rows[0][key] = value
            self.assertEqual(proper_rigid_fit(rows, budget())['status'], 'RIGID_INVALID_CORRESPONDENCES')

    def test_shared_deadline_and_control_limit_remain_enforced(self):
        rows = point_rows(); original = copy.deepcopy(rows)
        ticks = iter([0., 0., 61.])
        with self.assertRaisesRegex(StudioError, 'time budget'):
            proper_rigid_fit(rows, _Budget({}, lambda: next(ticks)))
        self.assertEqual(rows, original)
        small = _Budget({'max_controls': 3}, lambda: 0.)
        self.assertEqual(proper_rigid_fit(rows, small)['status'], 'INCOMPLETE_CORRESPONDENCES')
        ticks = iter([2., 1.])
        with self.assertRaisesRegex(StudioError, 'clock reversed'):
            proper_rigid_fit(rows, _Budget({}, lambda: next(ticks)))

    def test_rotation_budget_exhaustion_refuses_without_retry_or_mutation(self):
        rows = point_rows(); original = copy.deepcopy(rows)
        with patch('a3d.rigid_guide_alignment._MAX_ROTATIONS', 1):
            result = proper_rigid_fit(rows, budget())
        self.assertEqual(result['status'], 'RIGID_NUMERIC_INCOMPLETE')
        self.assertEqual(result['numerical']['rotations'], 1)
        self.assertGreater(result['numerical']['normalized_off_diagonal_max'], result['numerical']['convergence_roundoff'])
        self.assertEqual(rows, original)

    def test_source_seed_applied_once_and_torso_fit_targets_immutable(self):
        data, semantics, states, witnesses, shared = prepared()
        original = digest([data, semantics, states['mobile']['original'], states['a']['original'], states['b']['original'], witnesses])
        positions, receipt = prepare_role_rigid_seeds(data, semantics, states, witnesses, shared, subdivisions=3)
        row = receipt['pieces']['mobile']
        self.assertTrue(row['applied'])
        self.assertLess(row['fit']['after']['max_gap_cm'], 1e-12)
        self.assertEqual(positions['a'], states['a']['original']); self.assertEqual(positions['b'], states['b']['original'])
        for index, source in enumerate(states['mobile']['original']):
            self.assertEqual(positions['mobile'][index], transform(row['fit'], source))
        self.assertEqual(original, digest([data, semantics, states['mobile']['original'], states['a']['original'], states['b']['original'], witnesses]))

    def test_missing_applicable_partner_or_link_or_partition_moves_nothing(self):
        for change in ('partner', 'link', 'partition'):
            data, semantics, states, witnesses, shared = prepared()
            if change == 'partner': del states['b']
            elif change == 'link': witnesses = witnesses[1:]
            else:
                witnesses[0]['common_fractions'].pop(1); witnesses[0]['paired_cage_controls'].pop(1)
            original = copy.deepcopy(states['mobile']['original'])
            positions, receipt = prepare_role_rigid_seeds(data, semantics, states, witnesses, shared, subdivisions=3)
            self.assertEqual(positions['mobile'], original)
            self.assertFalse(receipt['pieces']['mobile']['applied'])
            self.assertEqual(receipt['pieces']['mobile']['status'], 'INCOMPLETE_CORRESPONDENCES')

    def test_missing_role_is_explicit_and_keeps_positions(self):
        data, semantics, states, witnesses, shared = prepared(); del semantics['a']
        positions, receipt = prepare_role_rigid_seeds(data, semantics, states, witnesses, shared, subdivisions=3)
        self.assertEqual(positions, {pid: state['original'] for pid, state in states.items()})
        self.assertEqual(receipt['diagnostics'][0]['code'], 'RIGID_SEMANTICS_INCOMPLETE')

    def test_dispatcher_passes_explicit_semantics_and_preserves_partial_status(self):
        from a3d.garment_guide_policy import prepare_guide_policy, reconstruct_guide_policy
        from tests.test_garment_guide_policy import coupled_fixture
        compiled, profile, geometry, ref, data, parameters, recipes = coupled_fixture()
        policy = prepare_guide_policy(compiled, profile, geometry, ref, parameters, source_seam_recipes=recipes)
        guides, evidence = reconstruct_guide_policy(compiled, profile, geometry, ref, data, policy, source_seam_recipes=recipes)
        guide = guides['garment.test']
        self.assertEqual(guide['status'], 'PARTIAL_GUIDES')
        self.assertTrue(any(row['family'] == 'source_rigid_alignment' for row in guide['diagnostics']))
        self.assertEqual(guide['qualification'], 'NONE'); self.assertFalse(evidence['admissible_for_fit'])
        self.assertEqual(guide['source_seam_coupling']['rigid_alignment']['status'], 'ALIGNMENT_INCOMPLETE')

    def test_closure_excluded_and_remaining_collar_scope_is_partial(self):
        for extra in ('closure', 'collar'):
            data, frames, recipe, semantics = fixture(extra); original = copy.deepcopy([data, frames, recipe, semantics])
            _, report = couple_source_seams(data, frames, recipe, semantics=semantics, subdivisions=3, clock=lambda: 0.)
            row = report['rigid_alignment']['pieces']['mobile']
            self.assertTrue(row['applied']); self.assertFalse(row['whole_piece_admission'])
            if extra == 'closure':
                self.assertEqual(row['excluded_nonpermanent_relations'], [{'id': 'not-a-sewn-join', 'kind': 'closure'}])
                self.assertEqual(len(row['expected_relation_ids']), 2)
            else:
                self.assertEqual(row['status'], 'PARTIAL_RIGID_SEED_APPLIED')
                self.assertEqual(row['remaining_permanent_relation_ids'], ['remaining-neck-link'])
                # A single straight neckline has rank one. A collar seed must
                # explicitly refuse that ambiguity rather than invent rotation.
                self.assertEqual(report['rigid_alignment']['diagnostics'][0]['code'], 'RIGID_FRAME_AMBIGUOUS')
                self.assertFalse(report['rigid_alignment']['pieces']['other']['applied'])
            self.assertEqual([data, frames, recipe, semantics], original)

    def test_renamed_and_reordered_source_uses_roles_without_name_inference(self):
        data, frames, recipe, semantics = fixture()
        first, report = couple_source_seams(data, frames, recipe, semantics=semantics, subdivisions=3, clock=lambda: 0.)
        names = {'mobile': 'opaque-z', 'a': 'opaque-y', 'b': 'opaque-x'}
        renamed = copy.deepcopy(data)
        renamed['pieces'] = {names[pid]: value for pid, value in reversed(list(data['pieces'].items()))}
        seam_names = {'join-a': 'opaque-2', 'join-b': 'opaque-1'}
        for seam in renamed['seams']:
            seam['piece_a'] = names[seam['piece_a']]; seam['piece_b'] = names[seam['piece_b']]
            seam['id'] = seam_names[seam['id']]
        renamed['seams'].reverse()
        renamed_recipe = {**recipe, 'seams': {seam_names[sid]: row for sid, row in recipe['seams'].items()}}
        again, renamed_report = couple_source_seams(renamed, {names[p]: f for p, f in frames.items()}, renamed_recipe,
            semantics={names[p]: r for p, r in semantics.items()}, subdivisions=3, clock=lambda: 0.)
        for pid in first:
            self.assertEqual(first[pid]['target_cm'], again[names[pid]]['target_cm'])
        self.assertEqual(report['rigid_alignment']['pieces']['mobile']['fit'],
            renamed_report['rigid_alignment']['pieces']['opaque-z']['fit'])

    def test_shared_total_budget_does_not_charge_the_seed_again(self):
        data, frames, recipe, semantics = fixture()
        _, legacy = couple_source_seams(data, frames, recipe, subdivisions=3, clock=lambda: 0.)
        controls = sum(row['control_vertices'] for row in legacy['refinements'].values())
        triangles = sum(row['control_triangles'] for row in legacy['refinements'].values())
        _, report = couple_source_seams(data, frames, recipe, semantics=semantics, subdivisions=3,
            budgets={'max_controls': controls, 'max_triangles': triangles}, clock=lambda: 0.)
        self.assertTrue(report['rigid_alignment']['pieces']['mobile']['applied'])
        before = copy.deepcopy([data, frames, recipe, semantics])
        with self.assertRaisesRegex(StudioError, 'control or triangle budget'):
            couple_source_seams(data, frames, recipe, semantics=semantics, subdivisions=3,
                budgets={'max_controls': controls-1, 'max_triangles': triangles}, clock=lambda: 0.)
        self.assertEqual([data, frames, recipe, semantics], before)

    def test_original_and_postseed_displacement_are_separate_and_inputs_bound(self):
        data, frames, recipe, semantics = fixture()
        cages, report = couple_source_seams(data, frames, recipe, semantics=semantics, subdivisions=3, clock=lambda: 0.)
        self.assertGreater(report['max_target_correction_cm']['mobile'], 10.)
        self.assertLess(report['postseed_target_correction_cm']['mobile'], 1e-12)
        self.assertEqual(report['semantics_sha256'], digest(semantics))
        changed = copy.deepcopy(semantics); changed['mobile']['layer'] = 'other-declared-layer'
        recages, rereport = couple_source_seams(data, frames, recipe, semantics=changed, subdivisions=3, clock=lambda: 0.)
        self.assertNotEqual(report['source_binding_sha256'], rereport['source_binding_sha256'])
        self.assertNotEqual(cages['mobile']['source_ref'], recages['mobile']['source_ref'])

    def test_direct_calls_semantics_none_keep_historical_receipt_and_repeat_json(self):
        data, frames, recipe, semantics = fixture()
        legacy = couple_source_seams(data, frames, recipe, subdivisions=3, clock=lambda: 0.)
        self.assertEqual(legacy, couple_source_seams(data, frames, recipe, semantics=None, subdivisions=3, clock=lambda: 0.))
        self.assertNotIn('rigid_alignment', legacy[1]); self.assertNotIn('semantics_sha256', legacy[1])
        active = couple_source_seams(data, frames, recipe, semantics=semantics, subdivisions=3, clock=lambda: 0.)
        self.assertEqual(active, couple_source_seams(data, frames, recipe, semantics=semantics, subdivisions=3, clock=lambda: 0.))
        self.assertEqual(json.loads(json.dumps(active, allow_nan=False)), list(active))

    def test_collar_all_source_relations_transport_the_whole_piece(self):
        data, semantics, states, witnesses, shared, collar = prepared_collar()
        before = copy.deepcopy([data, semantics, witnesses, states[collar]['original'], states[collar]['uv'],
                                states[collar]['triangles'], states[collar]['segments']])
        positions, receipt = prepare_role_rigid_seeds(data, semantics, states, witnesses, shared, subdivisions=3)
        row = receipt['pieces'][collar]
        self.assertEqual(row['expected_relation_ids'], ['join-a', 'join-b'])
        self.assertEqual(set(row['relation_residuals']), {'join-a', 'join-b'})
        self.assertTrue(row['applied']); self.assertEqual(row['transformed_controls'], len(states[collar]['original']))
        self.assertEqual(row['status'], 'PARTIAL_RIGID_SEED_APPLIED')
        self.assertEqual(receipt['status'], 'PARTIAL_ROLE_SEEDS_PREPARED')
        self.assertEqual(row['proposal_scope'], 'PARTIAL_TEST_ONLY')
        self.assertFalse(row['whole_piece_admission']); self.assertEqual(row['qualification'], 'NONE')
        self.assertLess(row['fit']['after']['max_gap_cm'], 1e-12)
        for index, point in enumerate(states[collar]['original']):
            self.assertEqual(positions[collar][index], transform(row['fit'], point))
        for pid in ('a', 'b'):
            self.assertEqual(positions[pid], states[pid]['original'])
        self.assertEqual(before, [data, semantics, witnesses, states[collar]['original'], states[collar]['uv'],
                                  states[collar]['triangles'], states[collar]['segments']])

    def test_collar_uses_inner_front_proposed_positions_not_old_originals(self):
        data, semantics, states, witnesses, shared, collar = prepared_collar(joint=True)
        front_positions, historical = _prepare_front_rigid_seeds(data, semantics, states, witnesses, budget(), subdivisions=3)
        relations = sorted((row for row in data['seams'] if row['kind'] == 'permanent'
            and collar in (row['piece_a'], row['piece_b'])), key=lambda row: row['id'])
        view = {pid: {**state, 'original': front_positions[pid]} for pid, state in states.items()}
        expected = proper_rigid_fit(_complete_rows(collar, relations, view, witnesses, data, 3, budget()), budget())
        obsolete = proper_rigid_fit(_complete_rows(collar, relations, states, witnesses, data, 3, budget()), budget())
        original = copy.deepcopy(states['mobile']['original'])
        positions, receipt = prepare_role_rigid_seeds(data, semantics, states, witnesses, shared, subdivisions=3)
        row = receipt['pieces'][collar]
        self.assertEqual(row['fit'], expected); self.assertNotEqual(row['fit'], obsolete)
        self.assertLess(row['fit']['after']['max_gap_cm'], 1e-12)
        self.assertEqual(row['partner_controls_sha256']['mobile'], digest(front_positions['mobile']))
        self.assertEqual(receipt['pieces']['mobile'], historical['pieces']['mobile'])
        self.assertEqual(positions['mobile'], front_positions['mobile'])
        self.assertEqual(states['mobile']['original'], original)
        self.assertEqual(row['expected_relation_ids'], ['collar-c', 'collar-d', 'remaining-neck-link'])

    def test_collar_closure_detachable_are_explicitly_excluded(self):
        data, semantics, states, witnesses, shared, collar = prepared_collar(nonpermanent=True)
        positions, receipt = prepare_role_rigid_seeds(data, semantics, states, witnesses, shared, subdivisions=3)
        row = receipt['pieces'][collar]
        self.assertTrue(row['applied'])
        self.assertEqual(row['excluded_nonpermanent_relations'], [
            {'id': 'declared-closure', 'kind': 'closure'}, {'id': 'declared-detachable', 'kind': 'detachable'}])
        self.assertEqual(row['expected_relation_ids'], ['join-a', 'join-b'])
        self.assertNotEqual(positions[collar], states[collar]['original'])

    def test_collar_complete_witnesses_missing_duplicate_and_mutated_refuse(self):
        for change in ('missing', 'duplicate', 'partition', 'orientation', 'pair', 'shape', 'partner'):
            with self.subTest(change=change):
                data, semantics, states, witnesses, shared, collar = prepared_collar()
                if change == 'missing': witnesses.pop()
                elif change == 'duplicate': witnesses.append(copy.deepcopy(witnesses[0]))
                elif change == 'partition': witnesses[0]['common_fractions'].pop(1)
                elif change == 'orientation': witnesses[0]['source_relation']['orientation'] = 'forward'
                elif change == 'pair': witnesses[0]['paired_cage_controls'][1][1][1] += 1
                elif change == 'shape': del witnesses[0]['common_fractions']
                else: del states['b']
                original = copy.deepcopy(states[collar]['original'])
                positions, receipt = prepare_role_rigid_seeds(data, semantics, states, witnesses, shared, subdivisions=3)
                row = receipt['pieces'][collar]
                self.assertEqual(row['status'], 'INCOMPLETE_CORRESPONDENCES'); self.assertFalse(row['applied'])
                self.assertEqual(positions[collar], original)
                self.assertEqual(receipt['status'], 'ALIGNMENT_INCOMPLETE')

    def test_collar_only_nondeclared_or_no_permanent_partners_is_not_admitted(self):
        data, semantics, states, witnesses, shared, collar = prepared_collar()
        data['seams'] = [{**row, 'kind': 'closure'} for row in data['seams']]
        positions, receipt = prepare_role_rigid_seeds(data, semantics, states, witnesses, shared, subdivisions=3)
        self.assertEqual(receipt['pieces'][collar]['status'], 'INCOMPLETE_CORRESPONDENCES')
        self.assertEqual(positions[collar], states[collar]['original'])
        data, semantics, states, witnesses, shared, collar = prepared_collar()
        del states[collar]
        positions, receipt = prepare_role_rigid_seeds(data, semantics, states, witnesses, shared, subdivisions=3)
        self.assertEqual(receipt['unselected_collar_role_candidates'], [collar])
        self.assertEqual(receipt['status'], 'ALIGNMENT_INCOMPLETE')
        self.assertNotIn(collar, positions)

    def test_collar_joint_collar_partner_is_explicitly_unsupported(self):
        data, semantics, states, witnesses, shared, collar = prepared_collar()
        semantics['a']['role'] = 'collar'
        positions, receipt = prepare_role_rigid_seeds(data, semantics, states, witnesses, shared, subdivisions=3)
        self.assertEqual(receipt['pieces'][collar]['status'], 'COLLAR_JOINT_SEED_NOT_SUPPORTED')
        self.assertEqual(positions[collar], states[collar]['original'])

    def test_collar_proper_rotation_preserves_every_pair_and_source_orientation(self):
        data, semantics, states, witnesses, shared, collar = prepared_collar()
        positions, receipt = prepare_role_rigid_seeds(data, semantics, states, witnesses, shared, subdivisions=3)
        source = states[collar]['original']; moved = positions[collar]; fit = receipt['pieces'][collar]['fit']
        for i, a in enumerate(source):
            for j, b in enumerate(source):
                self.assertAlmostEqual(math.dist(a, b), math.dist(moved[i], moved[j]), places=12)
        self.assertAlmostEqual(fit['rotation_determinant'], 1., places=12)
        self.assertEqual(states[collar]['triangles'], _prepare_piece(data['pieces'][collar],
            collar_fixture()[1][collar], collar, 3, budget())['triangles'])

    def test_collar_uv_shift_marks_stops_direction_and_inputs_preserved(self):
        data, frames, recipe, semantics, collar = collar_fixture()
        _, initial = couple_source_seams(data, frames, recipe, semantics=semantics, subdivisions=3, clock=lambda: 0.)
        for piece in data['pieces'].values():
            piece['vertices'] = [[u+2., v+1.] for u, v in piece['vertices']]
            piece['declared_marks'] = [{'source_vertex_id': 0, 'role': 'notch'},
                {'source_vertex_id': 1, 'role': 'stop'}]
        for frame in frames.values(): frame['offset_uv_cm'] = [2., 1.]
        before = copy.deepcopy([data, frames, recipe, semantics])
        _, shifted = couple_source_seams(data, frames, recipe, semantics=semantics, subdivisions=3, clock=lambda: 0.)
        self.assertEqual(initial['rigid_alignment']['pieces'][collar]['fit'], shifted['rigid_alignment']['pieces'][collar]['fit'])
        self.assertEqual(before, [data, frames, recipe, semantics])
        self.assertTrue(all(row['source_relation']['orientation'] == 'reverse' for row in shifted['relations']))
        self.assertEqual(shifted['rigid_alignment']['pieces'][collar]['metric_after_coupling'], 'NOT_ASSESSED')
        self.assertEqual(shifted['rigid_alignment']['pieces'][collar]['interior_propagation'], 'NOT_ASSESSED')

    def test_collar_exact_total_caps_are_shared_with_preparation(self):
        data, frames, recipe, semantics, collar = collar_fixture(joint=True)
        _, legacy = couple_source_seams(data, frames, recipe, subdivisions=3, clock=lambda: 0.)
        controls = sum(row['control_vertices'] for row in legacy['refinements'].values())
        triangles = sum(row['control_triangles'] for row in legacy['refinements'].values())
        _, active = couple_source_seams(data, frames, recipe, semantics=semantics, subdivisions=3,
            budgets={'max_controls': controls, 'max_triangles': triangles}, clock=lambda: 0.)
        self.assertTrue(active['rigid_alignment']['pieces'][collar]['applied'])
        with self.assertRaisesRegex(StudioError, 'control or triangle budget'):
            couple_source_seams(data, frames, recipe, semantics=semantics, subdivisions=3,
                budgets={'max_controls': controls-1, 'max_triangles': triangles}, clock=lambda: 0.)

    def test_collar_deadline_expires_during_transport_and_after_last_hash(self):
        import a3d.rigid_guide_alignment as alignment
        for phase in ('transform', 'output_digest'):
            data, semantics, states, witnesses, shared, collar = prepared_collar()
            originals = copy.deepcopy([data, semantics, witnesses, states[collar]['original']])
            tick = [0.]; shared.clock = lambda: tick[0]
            actual_transform, actual_digest = alignment.transform, alignment.digest
            def expire_transform(fit, point):
                value = actual_transform(fit, point); tick[0] = 61.; return value
            def expire_digest(value):
                result = actual_digest(value)
                if isinstance(value, dict) and set(value) == set(states): tick[0] = 61.
                return result
            with patch('a3d.rigid_guide_alignment.'+('transform' if phase == 'transform' else 'digest'),
                       expire_transform if phase == 'transform' else expire_digest):
                with self.assertRaisesRegex(StudioError, 'time budget'):
                    prepare_role_rigid_seeds(data, semantics, states, witnesses, shared, subdivisions=3)
            self.assertEqual(originals, [data, semantics, witnesses, states[collar]['original']])

    def test_collar_combined_correspondence_cap_checked_before_rows_allocation(self):
        data, semantics, states, witnesses, shared, collar = prepared_collar()
        shared.limits['max_controls'] = len(states[collar]['original'])
        witness = witnesses[0]
        witness['paired_cage_controls'] *= len(states[collar]['original'])
        with patch('a3d.rigid_guide_alignment._complete_rows', side_effect=AssertionError('must not allocate')):
            positions, receipt = prepare_role_rigid_seeds(data, semantics, states, witnesses, shared, subdivisions=3)
        self.assertEqual(receipt['pieces'][collar]['status'], 'INCOMPLETE_CORRESPONDENCES')
        self.assertEqual(positions[collar], states[collar]['original'])

    def test_collar_no_improvement_keeps_best_original_without_retry(self):
        data, semantics, states, witnesses, shared, collar = prepared_collar()
        genuine = proper_rigid_fit(_complete_rows(collar, data['seams'], states, witnesses, data, 3, budget()), budget())
        genuine['after']['weighted_rms_gap_cm'] = genuine['before']['weighted_rms_gap_cm']+1.
        with patch('a3d.rigid_guide_alignment.proper_rigid_fit', return_value=genuine) as solve:
            positions, receipt = prepare_role_rigid_seeds(data, semantics, states, witnesses, shared, subdivisions=3)
        self.assertEqual(solve.call_count, 1)
        self.assertEqual(positions[collar], states[collar]['original'])
        self.assertEqual(receipt['pieces'][collar]['best_proposal'], 'ORIGINAL')
        self.assertEqual(receipt['pieces'][collar]['status'], 'PARTIAL_RIGID_SEED_UNCHANGED')

    def test_inner_front_path_is_exact_when_no_collar_is_selected(self):
        for extra in (None, 'closure'):
            data, semantics, states, witnesses, shared = prepared(extra)
            historical = _prepare_front_rigid_seeds(data, semantics, states, witnesses, budget(), subdivisions=3)
            current = prepare_role_rigid_seeds(data, semantics, states, witnesses, shared, subdivisions=3)
            self.assertEqual(json.dumps(historical, sort_keys=True, separators=(',', ':')),
                             json.dumps(current, sort_keys=True, separators=(',', ':')))

    def test_collar_table_order_and_source_side_do_not_infer_partner_coordinates(self):
        data, semantics, states, witnesses, shared, collar = prepared_collar()
        first, first_receipt = prepare_role_rigid_seeds(data, semantics, states, witnesses, shared, subdivisions=3)
        data['pieces'] = dict(reversed(list(data['pieces'].items())))
        data['seams'].reverse(); witnesses.reverse()
        states = dict(reversed(list(states.items())))
        again, receipt = prepare_role_rigid_seeds(data, semantics, states, witnesses, budget(), subdivisions=3)
        self.assertEqual(first, again)
        self.assertEqual(first_receipt['pieces'][collar], receipt['pieces'][collar])
        # Swap the explicit sides of each reverse relation and rebuild exact
        # source witnesses. A collar on side A still uses the declared partner.
        data, frames, recipe, semantics, collar = collar_fixture()
        for seam in data['seams']:
            seam['piece_a'], seam['piece_b'] = seam['piece_b'], seam['piece_a']
            seam['edge_a'], seam['edge_b'] = seam['edge_b'], seam['edge_a']
        _, report = couple_source_seams(data, frames, recipe, semantics=semantics, subdivisions=3, clock=lambda: 0.)
        self.assertLess(report['rigid_alignment']['pieces'][collar]['fit']['after']['max_gap_cm'], 1e-12)

    def test_collar_source_provenance_mutation_during_fit_refuses_return(self):
        import a3d.rigid_guide_alignment as alignment
        data, semantics, states, witnesses, shared, collar = prepared_collar()
        actual = alignment.proper_rigid_fit
        def changed(rows, shared_budget):
            fit = actual(rows, shared_budget)
            data['pieces'][collar]['declared_marks'] = [{'source_vertex_id': 0, 'role': 'changed'}]
            return fit
        with patch('a3d.rigid_guide_alignment.proper_rigid_fit', changed):
            with self.assertRaisesRegex(ValueError, 'Caller source'):
                prepare_role_rigid_seeds(data, semantics, states, witnesses, shared, subdivisions=3)

    def test_collar_incongruent_partners_leave_measured_residual_without_scale_or_admission(self):
        data, semantics, states, witnesses, shared, collar = prepared_collar()
        states['b']['original'] = [[x+5., y, z] for x, y, z in states['b']['original']]
        positions, receipt = prepare_role_rigid_seeds(data, semantics, states, witnesses, shared, subdivisions=3)
        row = receipt['pieces'][collar]
        self.assertGreater(row['fit']['after']['max_gap_cm'], 2.)
        self.assertEqual(row['residual_assessment'], 'MEASURED_ONLY_NO_ACCEPTANCE_BOUND')
        self.assertFalse(row['whole_piece_admission']); self.assertEqual(row['qualification'], 'NONE')
        for i, a in enumerate(states[collar]['original']):
            for j, b in enumerate(states[collar]['original']):
                self.assertAlmostEqual(math.dist(a, b), math.dist(positions[collar][i], positions[collar][j]), places=12)


if __name__ == '__main__':
    unittest.main()
