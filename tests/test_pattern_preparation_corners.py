"""Regular boundary preparation preserves the approved source polygon exactly."""
import unittest
from unittest.mock import patch

from a3d.core import StudioError, digest
from a3d.pattern_preparation import (prepare_regular_boundaries, regular_chain_parameters,
                                     regular_shared_parameters)
from a3d.sewing import (chain_lengths, edge_chain, mesh_quality,
                        prepare_boundaries, resample_parameters, sample_chain, segment_distance)
from tests.test_pattern_preparation import source_dossier
from tests.test_sewing import sources


CONFIG = {'spacing_cm': 2., 'min_spacing_cm': 1., 'refinement_distance_cm': 1., 'max_vertices': 4000}


def shallow_source():
    data, recipe = sources()
    piece = data['pieces']['front']
    piece['vertices'].insert(2, [19.99, 20.006905])
    piece['edges'] = {'right': [1, 2, 3], 'left': [0, 4], 'top': [4, 3]}
    piece['faces'] = [[0, 1, 2], [0, 2, 3], [0, 3, 4]]
    source = next(seam for seam in data['seams'] if seam['piece_a'] == 'front' and seam['edge_a'] == 'right')
    _, a, _ = edge_chain(piece, source['edge_a'])
    _, b, _ = edge_chain(data['pieces'][source['piece_b']], source['edge_b'])
    recipe['seams'][source['id']]['ease_b_over_a'] = chain_lengths(b)[-1] / chain_lengths(a)[-1] - 1.
    return data, recipe, source


class SourceCorners(unittest.TestCase):
    def test_shallow_source_corner_previously_below_error_is_required_and_paired(self):
        data, recipe, source = shallow_source()
        piece = data['pieces']['front']
        _, points, _ = edge_chain(piece, 'right')
        parameter = chain_lengths(points)[1] / chain_lengths(points)[-1]
        legacy = resample_parameters([points], CONFIG['min_spacing_cm'], recipe['mesh']['max_boundary_error_cm'])
        self.assertNotIn(parameter, legacy)
        self.assertLess(segment_distance(points[1], points[0], points[2]), recipe['mesh']['max_boundary_error_cm'])
        before = digest([data, recipe])
        boundaries, seams, report = prepare_regular_boundaries(data, recipe, CONFIG)
        row = seams[source['id']]
        self.assertIn(parameter, row['parameters'])
        index = row['parameters'].index(parameter)
        self.assertEqual(boundaries['front']['polygon'][row['a'][index]], piece['vertices'][2])
        self.assertEqual(len(row['a']), len(row['b']))
        partner = data['pieces'][source['piece_b']]
        _, partner_points, _ = edge_chain(partner, source['edge_b'])
        if source['orientation'] == 'reverse':
            partner_points.reverse()
        self.assertEqual(boundaries[source['piece_b']]['polygon'][row['b'][index]], sample_chain(partner_points, parameter))
        policy = report['boundary_sampling_policy']
        self.assertEqual(policy['source_corner_policy'], 'PRESERVE_EVERY_EXACT_SOURCE_TURN_BEFORE_PRUNING')
        self.assertIn(parameter, policy['source_corner_parameters'][source['id']])
        self.assertIn({'source_vertex': 2, 'derived_boundary_vertex': row['a'][index],
                       'source_perimeter_key_cm': boundaries['front']['keys'][row['a'][index]]},
                      report['source_corner_bindings']['front'])
        self.assertEqual(digest([data, recipe]), before)

    def test_both_oriented_partner_corner_fractions_are_unioned_despite_different_subdivisions(self):
        pieces = {
            'a': {'vertices': [[0., 0.], [10., 0.], [9.99, 4.03], [10., 10.], [0., 10.]]},
            'b': {'vertices': [[0., 0.], [12., 0.], [11.99, 6.17], [12., 10.], [0., 10.]]}}
        chains = {'join': (('a', [1, 2, 3]), ('b', [3, 2, 1]))}
        sampled = {'join': [0., .5, 1.]}
        before = digest([pieces, chains, sampled])
        selected, report = regular_shared_parameters(pieces, chains, sampled, {'join': [0., 1.]}, 2., .05)
        expected = set()
        for pid, ids in chains['join']:
            points = [pieces[pid]['vertices'][index] for index in ids]
            expected.add(chain_lengths(points)[1] / chain_lengths(points)[-1])
        self.assertEqual(len(expected), 2)
        self.assertTrue(expected <= set(selected['join']))
        self.assertTrue(expected <= set(report['protected_parameters']['join']))
        self.assertEqual(set(report['source_corner_parameters']['join']), expected)
        self.assertEqual(digest([pieces, chains, sampled]), before)

    def test_source_corner_propagates_transitively_through_shared_original_vertex_ids(self):
        pieces = {
            'a': {'vertices': [[0., 0.], [10., 0.], [9.99, 4.03], [10., 10.], [0., 10.]]},
            'b': {'vertices': [[0., 0.], [12., 0.], [12., 10.], [0., 10.]]},
            'c': {'vertices': [[0., 0.], [8., 0.], [8., 10.], [0., 10.]]}}
        chains = {'ab': (('a', [1, 2, 3]), ('b', [1, 2])),
                  'bc': (('b', [2, 1]), ('c', [1, 2]))}
        points = [pieces['a']['vertices'][index] for index in (1, 2, 3)]
        parameter = chain_lengths(points)[1] / chain_lengths(points)[-1]
        selected, report = regular_shared_parameters(pieces, chains,
            {'ab': [0., .5, 1.], 'bc': [0., .5, 1.]}, {'ab': [0., 1.], 'bc': [0., 1.]}, 2., .05)
        self.assertIn(parameter, selected['ab'])
        self.assertIn(1. - parameter, selected['bc'])
        self.assertIn(1. - parameter, report['protected_parameters']['bc'])

    def test_unsewn_run_protects_shallow_corners_even_when_sampler_omits_them(self):
        points = [[0., 0.], [4.03, .01], [10., 0.]]
        before = digest(points)
        parameter = chain_lengths(points)[1] / chain_lengths(points)[-1]
        legacy = resample_parameters([points], 1., .05)
        self.assertNotIn(parameter, legacy)
        selected = regular_chain_parameters(points, legacy, 1., .05)
        self.assertIn(parameter, selected)
        self.assertEqual(sample_chain(points, parameter), points[1])
        self.assertEqual(digest(points), before)

    def test_public_regular_preparation_protects_source_corner_on_unsewn_named_run(self):
        data, recipe = sources()
        piece = data['pieces']['front']
        # Its bottom boundary has no permanent relation. Endpoints remain
        # corners of the polygon and this new point is a shallow source turn.
        piece['vertices'].insert(1, [8.03, .01])
        piece['edges'] = {'right': [2, 3], 'left': [0, 4], 'top': [4, 3]}
        piece['faces'] = [[0, 1, 2], [0, 2, 3], [0, 3, 4]]
        before = digest([data, recipe])
        boundaries, _, _ = prepare_regular_boundaries(data, recipe, CONFIG)
        self.assertIn(piece['vertices'][1], boundaries['front']['polygon'])
        self.assertEqual(digest([data, recipe]), before)

    def test_exact_collinear_subdivisions_do_not_force_dense_simulation_samples(self):
        points = [[0., index / 100] for index in range(1001)]
        sampled = resample_parameters([points], 2., .05)
        selected = regular_chain_parameters(points, sampled, 2., .05)
        self.assertEqual(selected, sampled)
        self.assertLess(len(selected), 10)

    def test_no_angle_threshold_discards_arbitrarily_shallow_real_source_turn(self):
        for height in (1e-6, 1e-12, 1e-20):
            points = [[0., 0.], [4.03, height], [10., 0.]]
            parameter = chain_lengths(points)[1] / chain_lengths(points)[-1]
            with self.subTest(height=height):
                self.assertIn(parameter, regular_chain_parameters(points, [0., .5, 1.], 2., .05))

    def test_exact_source_stop_returns_authored_uv_without_interpolation_noise(self):
        points = [[.1, .1], [.3, 0.], [.1, 27.]]
        lengths = chain_lengths(points)
        parameter = lengths[1] / lengths[-1]
        # The former interpolation generated y=1.3877787807814457e-17 here,
        # whose native binary32 is nonzero although the source UV is zero.
        self.assertEqual(sample_chain(points, parameter), points[1])
        near = sample_chain(points, parameter + 1e-6)
        self.assertNotEqual(near, points[1])
        self.assertEqual(sample_chain(points, 0.), points[0])
        self.assertEqual(sample_chain(points, 1.), points[-1])

    def test_close_required_corners_and_notches_survive_density_pressure_then_quality_refuses(self):
        points = [[10., 0.], [10., 5.], [9.99999, 5.0001], [10., 10.]]
        pieces = {'a': {'vertices': [[0., 0.]] + points + [[0., 10.]]},
                  'b': {'vertices': [[0., 0.], [12., 0.], [12., 10.], [0., 10.]]}}
        chains = {'join': (('a', [1, 2, 3, 4]), ('b', [1, 2]))}
        lengths = chain_lengths(points)
        corners = [lengths[index] / lengths[-1] for index in (1, 2)]
        notch = .50003
        selected, report = regular_shared_parameters(pieces, chains,
            {'join': [0., .5, 1.]}, {'join': [0., notch, 1.]}, 2., .05)
        self.assertTrue(set(corners + [notch]) <= set(selected['join']))
        self.assertTrue(report['close_required_parameters_preserved'])
        # The immutable short boundary edge remains a metric failure; no point
        # is removed to make the downstream quality check claim success.
        rest = [points[1] + [0.], points[2] + [0.], [0., 0., 0.]]
        with self.assertRaises(StudioError) as caught:
            mesh_quality(rest, rest, [[0, 1, 2]],
                {'min_angle_degrees': 0., 'min_edge_cm': .01, 'min_stretch': .8, 'max_stretch': 1.25})
        self.assertIn('short_edge', caught.exception.quality_violations)

    def test_budget_exhaustion_refuses_instead_of_removing_mandatory_source_corners(self):
        data, recipe, _ = shallow_source()
        before = digest([data, recipe])
        with self.assertRaisesRegex(StudioError, 'vertex budget'):
            prepare_regular_boundaries(data, recipe, {**CONFIG, 'max_vertices': 20})
        self.assertEqual(digest([data, recipe]), before)

    def test_existing_named_stops_and_material_notches_are_kept_alongside_new_corners(self):
        data, recipe, source = shallow_source()
        dossier = source_dossier(data)
        before = digest([data, recipe, dossier])
        boundaries, seams, report = prepare_regular_boundaries(data, recipe, CONFIG, dossier)
        row = seams[source['id']]
        self.assertIn(.3, row['parameters'])
        self.assertEqual(row['parameters'][0], 0.)
        self.assertEqual(row['parameters'][-1], 1.)
        self.assertTrue(report['source_notches'])
        self.assertIn(data['pieces']['front']['vertices'][2], boundaries['front']['polygon'])
        self.assertEqual(digest([data, recipe, dossier]), before)

    def test_postcheck_refuses_lost_or_altered_corner_instead_of_repairing_it(self):
        data, recipe, _ = shallow_source()
        before = digest([data, recipe])
        for alteration in ('omitted', 'coordinate'):
            def corrupt(*args, **kwargs):
                boundaries, seams, reports = prepare_boundaries(*args, **kwargs)
                polygon = boundaries['front']['polygon']
                index = polygon.index(data['pieces']['front']['vertices'][2])
                if alteration == 'omitted':
                    boundaries['front']['keys'][index] += .001
                else:
                    polygon[index] = [polygon[index][0] + 1e-12, polygon[index][1]]
                return boundaries, seams, reports
            with self.subTest(alteration=alteration), patch('a3d.pattern_preparation.prepare_boundaries', corrupt):
                with self.assertRaises(StudioError):
                    prepare_regular_boundaries(data, recipe, CONFIG)
            self.assertEqual(digest([data, recipe]), before)


if __name__ == '__main__':
    unittest.main()
