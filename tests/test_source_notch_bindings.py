"""Source marks are material references, not mandatory cloth particles."""
import copy
import json
import math
import unittest

from a3d.core import StudioError, digest
from a3d.pattern_preparation import _bind_source_notch, prepare_regular_boundaries
from a3d.sewing import chain_lengths, edge_chain, prepare_boundaries, sample_chain
from tests.test_material_notch_sides import fixture as sided_fixture
from tests.test_pattern_preparation import source_dossier
from tests.test_pattern_preparation_corners import CONFIG, shallow_source
from tests.test_sewing import sources


def unary_corner_source():
    data, recipe = sources()
    panel = data['pieces']['front']
    panel['vertices'] = [[0., 0.], [8.25, 0.], [8.38, 4.7499995],
                         [8.51, 9.5], [.26, 9.5], [.13, 4.7499995]]
    panel['faces'] = [[0, index, index + 1] for index in range(1, 5)]
    panel['edges'] = {'left': [0, 5, 4], 'right': [3, 2, 1], 'top': [4, 3]}
    data['seams'] = [{'id': 'unary', 'piece_a': 'front', 'edge_a': 'left',
                      'piece_b': 'front', 'edge_b': 'right',
                      'orientation': 'reverse', 'kind': 'permanent'}]
    recipe['seams'] = {'unary': {'kind': 'permanent', 'ease_b_over_a': 0.,
                                'tolerance_relative': .01}}
    dossier = source_dossier(data)
    mark = next(piece for piece in dossier['components'][data['component_id']]['pieces']
                if piece['id'] == 'front')['pattern']['assembly_marks'][0]
    mark['position'] = .5
    return data, recipe, dossier, mark


class SourceNotchBindings(unittest.TestCase):
    def test_neighbouring_float_samples_cannot_overwrite_true_source_corner(self):
        data, recipe, source = shallow_source()
        _, points, _ = edge_chain(data['pieces']['front'], source['edge_a'])
        parameter = chain_lengths(points)[1] / chain_lengths(points)[-1]
        before = digest([data, recipe])
        for direction in (-math.inf, math.inf):
            neighbour = math.nextafter(parameter, direction)
            with self.subTest(direction=direction):
                boundaries, seams, _ = prepare_boundaries(data, recipe,
                    {source['id']: [parameter, neighbour]}, regular_boundary_spacing_cm=1.)
                boundary, seam = boundaries['front'], seams[source['id']]
                index = boundary['polygon'].index(data['pieces']['front']['vertices'][2])
                self.assertIn(index, seam['a'])
                provenance = boundary['sample_provenance'][index]
                self.assertEqual(provenance['kind'], 'SOURCE_VERTEX')
                self.assertEqual(provenance['source_vertex'], 2)
                self.assertEqual(provenance['derived_boundary_vertex'], index)
                self.assertEqual(provenance['index_space'], 'PIECE_BOUNDARY_LOCAL')
                self.assertEqual(len(seam['a']), len(seam['b']))
        self.assertEqual(digest([data, recipe]), before)

    def test_distinct_authored_vertices_at_same_storage_key_refuse(self):
        data, recipe = sources()
        panel = data['pieces']['front']
        width = 20.000000004
        panel['vertices'] = [[0., 0.], [width, 0.], [width, 40.],
                             [0., 40.], [0., 1.01e-8]]
        panel['faces'] = [[0, 1, 4], [1, 2, 3], [1, 3, 4]]
        panel['edges'] = {'left': [0, 4, 3], 'right': [1, 2], 'top': [3, 2],
                          'source-stop': [4, 3]}
        before = digest([data, recipe])
        with self.assertRaisesRegex(StudioError, 'Distinct source vertices exceed boundary key precision'):
            prepare_regular_boundaries(data, recipe, CONFIG)
        self.assertEqual(digest([data, recipe]), before)

    def test_near_corner_midpoint_is_interpolated_without_creating_micro_edges(self):
        data, recipe, dossier, mark = unary_corner_source()
        before = digest([data, recipe, dossier])
        plain, plain_seams, _ = prepare_regular_boundaries(data, recipe, CONFIG)
        boundaries, seams, report = prepare_regular_boundaries(data, recipe, CONFIG, dossier)
        self.assertEqual(boundaries, plain)
        self.assertEqual(seams, plain_seams)
        seam = seams['unary']
        self.assertNotIn(.5, seam['parameters'])
        boundary = boundaries['front']
        for source_vertex in (2, 5):
            self.assertIn(data['pieces']['front']['vertices'][source_vertex], boundary['polygon'])
        self.assertGreater(min(math.dist(a, b) for a, b in zip(
            boundary['polygon'], boundary['polygon'][1:] + boundary['polygon'][:1])), .001)
        self.assertEqual(len(report['source_notches']), 2)
        for row in report['source_notches']:
            self.assertEqual(row['source_mark'], mark)
            self.assertEqual(row['symbol'], mark['symbol'])
            self.assertEqual(row['source_local_parameter'], .5)
            self.assertEqual(row['binding']['kind'], 'BOUNDARY_SEGMENT')
            self.assertNotIn('derived_boundary_vertex', row)
            _, points, _ = edge_chain(data['pieces']['front'], data['seams'][0]['edge_' + row['side']])
            self.assertEqual(row['source_uv_cm'], sample_chain(points, .5))
        self.assertEqual(digest([data, recipe, dossier]), before)

    def test_exact_authored_corner_mark_uses_existing_vertex_on_both_unary_sides(self):
        data, recipe, dossier, mark = unary_corner_source()
        positions = {}
        for side in ('a', 'b'):
            _, points, _ = edge_chain(data['pieces']['front'], data['seams'][0]['edge_' + side])
            positions[side] = chain_lengths(points)[1] / chain_lengths(points)[-1]
        mark['seam_side_positions'] = positions
        before = digest([data, recipe, dossier])
        boundaries, _, report = prepare_regular_boundaries(data, recipe, CONFIG, dossier)
        for row in report['source_notches']:
            vertex = 5 if row['side'] == 'a' else 2
            self.assertEqual(row['source_vertex'], vertex)
            self.assertEqual(row['source_uv_cm'], data['pieces']['front']['vertices'][vertex])
            self.assertEqual(row['source_local_parameter'], positions[row['side']])
            self.assertEqual(row['binding']['kind'], 'BOUNDARY_VERTEX')
            index = row['binding']['boundary_vertex']
            self.assertEqual(boundaries['front']['polygon'][index], row['source_uv_cm'])
            self.assertEqual(row['derived_boundary_vertex'], index)
            self.assertEqual(row['numeric_reconstruction_residual_cm'], 0.)
        self.assertEqual(digest([data, recipe, dossier]), before)

    def test_straight_cyclic_source_origin_survives_without_notch_particle(self):
        data, recipe, dossier, mark = unary_corner_source()
        panel = data['pieces']['front']
        panel['vertices'] = [[0., 5.0000005], [0., 10.], [8., 10.],
                             [8., 5.0000005], [8., 0.], [0., 0.]]
        panel['faces'] = [[0, index, index + 1] for index in range(1, 5)]
        panel['edges'] = {'left': [5, 0, 1], 'right': [4, 3, 2], 'top': [1, 2]}
        data['seams'][0]['orientation'] = 'forward'
        before = digest([data, recipe, dossier])
        boundaries, seams, report = prepare_regular_boundaries(data, recipe, CONFIG, dossier)
        self.assertIn(panel['vertices'][0], boundaries['front']['polygon'])
        self.assertNotIn(.5, seams['unary']['parameters'])
        origin = boundaries['front']['polygon'].index(panel['vertices'][0])
        self.assertEqual(boundaries['front']['sample_provenance'][origin]['source_vertex'], 0)
        self.assertTrue(all(row['binding']['kind'] == 'BOUNDARY_SEGMENT'
                            for row in report['source_notches']))
        self.assertEqual(digest([data, recipe, dossier]), before)

    def test_json_rederivation_refuses_forged_weights_uv_or_source_identity(self):
        data, recipe, dossier, _ = sided_fixture()
        boundaries, seams, report = prepare_regular_boundaries(data, recipe, CONFIG, dossier)
        row = json.loads(json.dumps(report['source_notches'][0]))
        expected = _bind_source_notch(data, boundaries, seams, row)
        self.assertEqual(expected, {key: row[key] for key in expected})
        for mutation in ('weights', 'uv', 'identity', 'owner', 'symbol'):
            changed = copy.deepcopy(row)
            if mutation == 'weights':
                changed['binding']['weights'][0] += .1
            elif mutation == 'uv':
                changed['source_uv_cm'][0] += .1
            elif mutation == 'identity':
                changed['source_chain'][0] += 1
            elif mutation == 'owner':
                changed['piece'] = 'back'
            else:
                changed['symbol'] = 'different-symbol'
            with self.subTest(mutation=mutation), self.assertRaises(StudioError):
                _bind_source_notch(data, boundaries, seams, changed)
        duplicated = copy.deepcopy(dossier)
        info = next(piece for piece in duplicated['components'][data['component_id']]['pieces']
                    if piece['id'] == 'front')
        info['pattern']['assembly_marks'].append(copy.deepcopy(info['pattern']['assembly_marks'][0]))
        with self.assertRaisesRegex(StudioError, 'identities must be unique'):
            prepare_regular_boundaries(data, recipe, CONFIG, duplicated)

    def test_segment_json_cannot_claim_obsolete_physical_vertex_fields(self):
        data, recipe, dossier, _ = sided_fixture()
        boundaries, seams, report = prepare_regular_boundaries(data, recipe, CONFIG, dossier)
        row = next(item for item in report['source_notches']
                   if item['binding']['kind'] == 'BOUNDARY_SEGMENT')
        for key in ('common_sample', 'derived_boundary_vertex'):
            changed = json.loads(json.dumps(row))
            changed[key] = 999999
            with self.subTest(key=key), self.assertRaisesRegex(StudioError, 'cannot claim a physical'):
                _bind_source_notch(data, boundaries, seams, changed)


if __name__ == '__main__':
    unittest.main()
