import copy
import json
import math
import unittest

from a3d.core import StudioError, digest
from a3d.cloth_metrics import principal_stretches
from a3d.garment_guides import _source_limb_mesh
from a3d.guide_cage_sampling import section_cage_state
from a3d.pattern_assembly import _compile_arc_sections, _section_point, _compile_cage, _cage_point
from a3d.source_seam_coupling import _Budget, _evaluator, _prepare_piece
from a3d.torso_sections import source_bound_torso_cages


def concave_sleeve_source():
    # Exact material coordinates from the approved source-row-grading-v3
    # sleeve. This regression fixture has two concave underarm transitions;
    # anatomical targets and project state are deliberately outside this test.
    vertices = [[3.5, 0], [18, 0], [32.5, 0], [34.25, 12.800328],
        [40.71995117084247, 21.496071279843697], [36, 25.600655],
        [35.168403, 25.785596], [34.180556, 26.296903], [33.046875, 27.069303],
        [31.777778, 28.037523], [30.383681, 29.136289], [28.875, 30.300328],
        [27.262153, 31.464367], [25.555556, 32.563133], [23.765625, 33.531352],
        [21.902778, 34.303752], [19.977431, 34.815059], [18.0, 35.0],
        [16.022569, 34.815059], [14.097222, 34.303752], [12.234375, 33.531352],
        [10.444444, 32.563133], [8.737847, 31.464367], [7.125, 30.300328],
        [5.616319, 29.136289], [4.222222, 28.037523], [2.953125, 27.069303],
        [1.819444, 26.296903], [0.831597, 25.785596], [0.0, 25.600655],
        [-4.719951170842471, 21.496071279843697], [1.75, 12.800328]]
    faces = [[31, 0, 1], [31, 1, 2], [31, 2, 3], [3, 4, 31], [4, 5, 31]]
    faces += [[31, i, i+1] for i in range(5, 28)]
    faces += [[29, 30, 28], [30, 31, 28]]
    return {'vertices': vertices, 'faces': faces, 'edges': {}}


def fixture():
    piece = {'vertices':[[0., 0.], [4., 0.], [4., 12.], [0., 12.]],
        'faces':[[0, 1, 2], [0, 2, 3]], 'edges':{'side':[1, 2], 'left':[3, 0]}}
    frame = {'source_ref':'measured-polyline-fixture', 'u_direction':1,
        'arc_sections':[{'v_cm':v, 'arc_offset_cm':0.,
            'curve_cm':[[0., 0., v], [1., 0., v], [1., 3., v]]} for v in (0., 6., 12.)]}
    return piece, frame


def build(piece, frame, *, n=8, budgets=None, clock=lambda:0.):
    budget = _Budget(budgets, clock)
    state = section_cage_state(piece, frame, 'back', n, budget, _evaluator(frame, 'back', budget))
    return {'source_ref':frame['source_ref'], 'uv_cm':state['uv'],
        'target_cm':state['original'], 'triangles':state['triangles']}, state


class GuideCageSampling(unittest.TestCase):
    def test_concave_source_refinement_has_exact_barycentric_rounding_and_boundary(self):
        from fractions import Fraction
        from a3d.guide_cage_sampling import validated_cage_state, _rounded_source_segment
        from a3d.source_seam_coupling import _refinement_keys
        piece = concave_sleeve_source(); before = digest(piece); n = 8
        uv, faces = _source_limb_mesh(piece, n)
        keys = _refinement_keys(piece, n, _Budget({}, lambda: 0.))
        for key, index in keys.items():
            expected = [float(sum(Fraction(piece['vertices'][i][k])*weight
                                  for i, weight in key)/n) for k in (0, 1)]
            self.assertEqual(uv[index], expected)
        cage = {'source_ref': 'concave-source-regression', 'uv_cm': uv,
                'target_cm': [[*point, 0.] for point in uv], 'triangles': faces}
        state = validated_cage_state(piece, cage, 'sleeve-left', n,
                                     _Budget({}, lambda: 0.), lambda point: [*point, 0.])
        self.assertEqual(state['uv'], uv)
        self.assertEqual(state['triangles'], faces)
        self.assertEqual(len(state['segments']), len(piece['vertices']))
        for (a, b), controls in state['segments'].items():
            self.assertEqual(len(controls), n+1)
            self.assertTrue(all(_rounded_source_segment(uv[index], piece['vertices'][a],
                                                       piece['vertices'][b]) for _, index in controls))
        self.assertEqual(digest(piece), before)
        reordered = copy.deepcopy(piece); reordered['faces'].reverse()
        self.assertEqual(_source_limb_mesh(reordered, n), (uv, faces))
        self.assertEqual(_source_limb_mesh(json.loads(json.dumps(piece)), n), (uv, faces))

    def test_old_weighted_rounding_is_still_refused_on_concave_source_boundary(self):
        from a3d.guide_cage_sampling import validated_cage_state
        from a3d.source_seam_coupling import _refinement_keys
        piece = concave_sleeve_source(); n = 8; uv, faces = _source_limb_mesh(piece, n)
        key = ((6, 3), (7, 5)); index = _refinement_keys(piece, n, _Budget({}, lambda: 0.))[key]
        previous = [math.fsum(piece['vertices'][i][k]*weight for i, weight in key)/n for k in (0, 1)]
        self.assertNotEqual(uv[index], previous)
        uv[index] = previous
        cage = {'source_ref': 'historical-rounded-control', 'uv_cm': uv,
                'target_cm': [[*point, 0.] for point in uv], 'triangles': faces}
        with self.assertRaisesRegex(StudioError, 'original source segment once'):
            validated_cage_state(piece, cage, 'sleeve-left', n,
                                 _Budget({}, lambda: 0.), lambda point: [*point, 0.])

    def test_tapered_oblique_source_with_nonbinary_subdivision_retains_exact_corners(self):
        from a3d.guide_cage_sampling import validated_cage_state, _rounded_source_segment
        piece = {'vertices': [[35.168403, 25.785596], [35.168503, 25.785696],
                              [34.180556, 26.296903]], 'faces': [[0, 1, 2]], 'edges': {}}
        before = digest(piece)
        for n in (3, 8, 11):
            with self.subTest(subdivisions=n):
                uv, faces = _source_limb_mesh(piece, n)
                cage = {'source_ref': 'tapered-source', 'uv_cm': uv,
                        'target_cm': [[*point, 0.] for point in uv], 'triangles': faces}
                state = validated_cage_state(piece, cage, 'taper', n,
                                             _Budget({}, lambda: 0.), lambda point: [*point, 0.])
                for point in piece['vertices']:
                    self.assertIn(point, uv)
                for (a, b), controls in state['segments'].items():
                    self.assertEqual(len(controls), n+1)
                    self.assertTrue(all(_rounded_source_segment(uv[i], piece['vertices'][a],
                                                               piece['vertices'][b]) for _, i in controls))
        self.assertEqual(digest(piece), before)

    def test_v_partition_reduces_causal_sampling_defect_and_preserves_raw_metric(self):
        piece, frame = fixture()
        frame['arc_sections'][1]['v_cm'] = 5.1
        frame['arc_sections'][1]['curve_cm'] = [[p[0], p[1]+2., 5.1] for p in frame['arc_sections'][1]['curve_cm']]
        before = digest([piece, frame]); cage, state = build(piece, frame)
        witness = [[.7, 4.9], [.9, 4.9], [.8, 5.3]]
        raw = [_section_point(frame, _compile_arc_sections(frame, 'back'), uv, 'back')[0] for uv in witness]
        actual = [_cage_point(cage, _compile_cage(cage, 'back'), uv, 'back')[0] for uv in witness]
        old_uv, old_faces = _source_limb_mesh(piece, 8)
        old = {'source_ref':'old', 'uv_cm':old_uv, 'triangles':old_faces,
            'target_cm':[_section_point(frame, _compile_arc_sections(frame, 'back'), uv, 'back')[0] for uv in old_uv]}
        previous = [_cage_point(old, _compile_cage(old, 'back'), uv, 'back')[0] for uv in witness]
        self.assertLess(max(math.dist(a, b) for a, b in zip(actual, raw)), 1e-12)
        self.assertGreater(max(math.dist(a, b) for a, b in zip(previous, raw)), .01)
        self.assertTrue(all(abs(a-b) < 1e-12 for a, b in zip(principal_stretches(witness, actual), principal_stretches(witness, raw))))
        self.assertEqual(digest([piece, frame]), before)
        self.assertEqual(set(state['triangle_source_faces']), {0, 1})

    def test_received_cage_is_preserved_instead_of_uniform_resampling(self):
        piece, frame = fixture(); cage, _ = build(piece, frame); before = digest(cage)
        state = _prepare_piece(piece, cage, 'back', 8, _Budget({}, lambda:0.))
        self.assertEqual(state['uv'], cage['uv_cm'])
        self.assertEqual(state['triangles'], cage['triangles'])
        self.assertEqual(state['original'], cage['target_cm'])
        self.assertEqual(digest(cage), before)
        self.assertNotEqual(state['uv'], _source_limb_mesh(piece, 8)[0])

    def test_source_corners_boundary_controls_sections_and_json_are_retained(self):
        piece, frame = fixture(); cage, state = build(piece, frame)
        for point in piece['vertices']:
            self.assertIn(point, cage['uv_cm'])
        for edge, controls in state['segments'].items():
            for step in range(9):
                self.assertTrue(any(abs(t-step/8) <= 32*math.ulp(1.) for t, _ in controls))
        self.assertTrue(any(uv[1] == 6. for uv in cage['uv_cm']))
        restored = json.loads(json.dumps([piece, frame]))
        self.assertEqual(build(*restored)[0], cage)
        reordered = copy.deepcopy(piece); reordered['faces'].reverse()
        self.assertEqual(build(reordered, frame)[0], cage)

    def test_targets_at_v_cuts_are_sourced_even_when_u_interpolation_is_not_exact(self):
        piece, frame = fixture()
        frame['arc_sections'][1]['curve_cm'] = [[0., 0., 6.], [2., 0., 6.], [2., 2., 6.]]
        cage, state = build(piece, frame)
        self.assertTrue(any(uv[1] == 6. for uv in cage['uv_cm']))
        for uv, target in zip(cage['uv_cm'], cage['target_cm']):
            self.assertEqual(target, _section_point(frame, _compile_arc_sections(frame, 'back'), uv, 'back')[0])
        self.assertTrue(all(len(uses) in (1, 2) for uses in state['owners'].values()))

    def test_affine_rotated_targets_do_not_change_uv_partition(self):
        piece, frame = fixture(); original, _ = build(piece, frame)
        moved = copy.deepcopy(frame)
        transform = lambda p:[3.-p[1], 7.+p[2], 12.+p[0]]
        for row in moved['arc_sections']:
            row['curve_cm'] = [transform(p) for p in row['curve_cm']]
        cage, _ = build(piece, moved)
        self.assertEqual(cage['uv_cm'], original['uv_cm'])
        self.assertEqual(cage['triangles'], original['triangles'])
        self.assertTrue(all(math.dist(transform(a), b) < 1e-12 for a, b in zip(original['target_cm'], cage['target_cm'])))

    def test_reverse_u_is_an_actual_arc_parameter(self):
        piece, frame = fixture(); expected, _ = build(piece, frame)
        piece['vertices'] = [[-p[0], p[1]] for p in piece['vertices']]
        frame['u_direction'] = -1
        cage, _ = build(piece, frame)
        mirrored = {(-p[0], p[1]):target for p, target in zip(expected['uv_cm'], expected['target_cm'])}
        self.assertEqual({tuple(p):target for p, target in zip(cage['uv_cm'], cage['target_cm'])}, mirrored)

    def test_arc_offset_is_applied_by_the_existing_evaluator(self):
        piece, frame = fixture(); expected, _ = build(piece, frame)
        for row in frame['arc_sections']:
            row['arc_offset_cm'] = .5
            row['curve_cm'].insert(0, [-.5, 0., row['v_cm']])
        cage, _ = build(piece, frame)
        self.assertEqual(cage, {**expected, 'source_ref':frame['source_ref']})

    def test_invalid_received_cages_are_not_trusted_by_source_reference(self):
        piece, frame = fixture(); valid, _ = build(piece, frame)
        for variant in ('hole', 'winding', 'nonfinite', 'corner', 'foreign', 'unused', 'duplicate', 'overlap'):
            cage = copy.deepcopy(valid); cage['source_ref'] += ';source-conforming:true'
            if variant == 'hole':
                cage['triangles'].pop()
            elif variant == 'winding':
                cage['triangles'][0].reverse()
            elif variant == 'nonfinite':
                cage['target_cm'][0][0] = math.nan
            elif variant == 'corner':
                i = cage['uv_cm'].index(piece['vertices'][0]); cage['uv_cm'][i][0] += .001
            elif variant == 'foreign':
                cage['uv_cm'][0][0] -= 10.
            elif variant == 'unused':
                cage['uv_cm'].append([2., 2.]); cage['target_cm'].append([0., 0., 0.])
            elif variant == 'duplicate':
                cage['uv_cm'][1] = list(cage['uv_cm'][0])
            else:
                cage['triangles'].append(list(cage['triangles'][0]))
            with self.subTest(variant=variant), self.assertRaises(StudioError):
                _prepare_piece(piece, cage, 'back', 8, _Budget({}, lambda:0.))

    def test_crossing_source_face_provenance_is_refused(self):
        piece, _ = fixture()
        cage = {'source_ref':'alternative-valid-domain', 'uv_cm':copy.deepcopy(piece['vertices']),
            'target_cm':[[p[0], 0., p[1]] for p in piece['vertices']], 'triangles':[[0, 1, 3], [1, 2, 3]]}
        with self.assertRaisesRegex(StudioError, 'one original source material face'):
            _prepare_piece(piece, cage, 'back', 8, _Budget({}, lambda:0.))

    def test_bowtie_vertex_is_refused_even_with_valid_source_corners_and_support(self):
        piece, _ = fixture(); uv = copy.deepcopy(piece['vertices'])+[[2., 6.]]
        cage = {'source_ref':'bowtie', 'uv_cm':uv, 'target_cm':[[p[0], 0., p[1]] for p in uv],
            'triangles':[[0, 1, 4], [4, 2, 3]]}
        with self.assertRaisesRegex(StudioError, 'bowtie'):
            _prepare_piece(piece, cage, 'back', 8, _Budget({}, lambda:0.))

    def test_exact_source_rounding_bins_preserve_oblique_border_and_refuse_a_shift(self):
        from a3d.guide_cage_sampling import _rounded_source_segment
        from fractions import Fraction
        a = [0., 131.]; b = [-1.252148, 131.014062]
        point = [float(Fraction(x)+Fraction(3, 8)*(Fraction(y)-Fraction(x))) for x, y in zip(a, b)]
        self.assertTrue(_rounded_source_segment(point, a, b))
        point[1] += .000001
        self.assertFalse(_rounded_source_segment(point, a, b))
        # Adjacent odd/even bins touch, but round-to-even cannot round one
        # exact coordinate to two different received values simultaneously.
        self.assertFalse(_rounded_source_segment([1., math.nextafter(1., math.inf)], [0., 0.], [2., 2.]))
        self.assertTrue(_rounded_source_segment([1., 1.], [0., 0.], [2., 2.]))

    def test_control_triangle_and_time_budgets_refuse_without_mutation(self):
        piece, frame = fixture(); before = digest([piece, frame])
        for values in ({'max_controls':3}, {'max_triangles':1}):
            with self.subTest(values=values), self.assertRaisesRegex(StudioError, 'budget'):
                build(piece, frame, budgets=values)
        clock = iter((0., 61.))
        with self.assertRaisesRegex(StudioError, 'time budget'):
            build(piece, frame, clock=lambda:next(clock))
        self.assertEqual(digest([piece, frame]), before)

    def test_exact_control_and_triangle_budget_does_not_double_charge_seed(self):
        piece, frame = fixture(); cage, _ = build(piece, frame)
        admitted, _ = build(piece, frame, budgets={'max_controls':len(cage['uv_cm']),
                                                  'max_triangles':len(cage['triangles'])})
        self.assertEqual(admitted, cage)

    def test_received_cage_checks_deadline_between_boundary_candidates(self):
        from unittest.mock import patch
        from a3d.guide_cage_sampling import _rounded_source_segment
        piece, frame = fixture(); cage, _ = build(piece, frame); before = digest(cage)
        clock = {'value':0., 'calls':0}
        def boundary(point, a, b):
            clock['calls'] += 1; clock['value'] = 61.
            return _rounded_source_segment(point, a, b)
        budget = _Budget({}, lambda:clock['value'])
        with patch('a3d.guide_cage_sampling._rounded_source_segment', side_effect=boundary):
            with self.assertRaisesRegex(StudioError, 'time budget'):
                _prepare_piece(piece, cage, 'back', 8, budget)
        self.assertLessEqual(clock['calls'], 2)
        self.assertEqual(digest(cage), before)

    def test_unrepresentable_exact_v_rows_are_refused_without_approximation(self):
        piece, frame = fixture()
        row = copy.deepcopy(frame['arc_sections'][1]); row['v_cm'] = math.nextafter(6., math.inf)
        row['curve_cm'] = [[p[0], p[1], row['v_cm']] for p in row['curve_cm']]
        frame['arc_sections'].insert(2, row)
        with self.assertRaisesRegex(StudioError, 'Collapsed source-UV') as caught:
            build(piece, frame)
        diagnostic = caught.exception.guide_diagnostic
        self.assertEqual(diagnostic['reason'], 'SECTION_PARTITION_NOT_REPRESENTABLE')
        self.assertLess(abs(diagnostic['determinant_cm2']), 1e-10)
        self.assertFalse(diagnostic['cuts_merged'])
        self.assertEqual(diagnostic['qualification'], 'NONE')

    def test_declared_source_budget_is_checked_in_first_torso_consumer(self):
        from tests.test_torso_cages import fixture as torso_fixture
        data, frames = torso_fixture()
        with self.assertRaisesRegex(StudioError, 'original source budget'):
            source_bound_torso_cages(data, frames, budgets={'max_source_points':3})


if __name__ == '__main__':
    unittest.main()
