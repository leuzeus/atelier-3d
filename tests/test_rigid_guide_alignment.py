import copy
import json
import math
import unittest
from unittest.mock import patch

from a3d.core import StudioError, digest
from a3d.rigid_guide_alignment import prepare_role_rigid_seeds, proper_rigid_fit, transform
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
                self.assertEqual(report['rigid_alignment']['diagnostics'][0]['code'], 'COLLAR_ALIGNMENT_NOT_IMPLEMENTED')
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


if __name__ == '__main__':
    unittest.main()
