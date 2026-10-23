"""Source sewing parameter proof; no native execution or product qualification."""
import copy
import json
import math
import struct
import unittest

from a3d.core import ROOT, StudioError, digest, read_json
from a3d.sewing import chain_lengths, edge_chain, prepare_boundaries, sample_chain
from a3d.source_uv_witnesses import source_boundary_seam_witnesses


def f32(point):
    return [struct.unpack('f', struct.pack('f', value))[0] for value in point]


def fixture(orientation='forward'):
    # This declared rectangle puts a real sewing sample across a binary32
    # midpoint from the reconstruction using only its eight-decimal key.
    width = 37.01308077488563
    parameter = .09861497599213345
    piece = {'vertices': [[0., 0.], [width, 0.], [width, 10.], [0., 10.]],
             'edges': {'join': [1, 2]}}
    peer = copy.deepcopy(piece)
    if orientation == 'reverse':
        peer['edges']['join'].reverse()
    uv = sample_chain(edge_chain(piece, 'join')[1], parameter)
    points = [piece['vertices'][0], piece['vertices'][1], uv,
              piece['vertices'][2], piece['vertices'][3]]
    stops = chain_lengths(piece['vertices'] + piece['vertices'][:1])
    keys = [0., round(stops[1], 8), round(stops[1] + uv[1], 8),
            round(stops[2], 8), round(stops[3], 8)]
    native = {'component_id': 'coat', 'rest_cm': [f32(p) + [0.] for p in points * 2],
              'panels': {}, 'seams': {'join': {'piece_a': 'front', 'piece_b': 'back',
                  'kind': 'permanent', 'parameters': [0., parameter, 1.],
                  'pairs': [[1, 6], [2, 7], [3, 8]]}}}
    for name, offset, source in (('front', 0, piece), ('back', 5, peer)):
        edge = [offset + index for index in (1, 2, 3)]
        if name == 'back' and orientation == 'reverse':
            edge.reverse()
        native['panels'][name] = {'indices': list(range(offset, offset + 5)),
            'boundary': list(range(offset, offset + 5)), 'boundary_source_arclength_cm': list(keys),
            'source_contour_sha256': digest(source['vertices']), 'edges': {'join': edge}}
    links = [{'id': 'coat::join', 'source_link_id': 'join', 'component_id': 'coat',
              'piece_a': 'front', 'piece_b': 'back', 'edge_a': 'join', 'edge_b': 'join',
              'kind': 'permanent', 'orientation': orientation,
              'source_ref': {'path': 'packages/coat.garmentpkg', 'sha256': 'a' * 64}}]
    return piece, peer, native, links


def official_preparation_fixture(orientation):
    """Use the actual source sampler, without Blender or a canonical DB fake."""
    parameter = .9499999910593033
    piece = {'vertices': [[0., 0.], [37., 0.], [37., 10.], [0., 10.]],
             'faces': [[0, 1, 2], [0, 2, 3]], 'edges': {'join': [1, 2]}}
    data = {'component_id': 'garment.coat', 'units': 'cm',
            'pieces': {'front': copy.deepcopy(piece), 'back': copy.deepcopy(piece)},
            'seams': [{'id': 'join', 'piece_a': 'front', 'edge_a': 'join',
                      'piece_b': 'back', 'edge_b': 'join', 'orientation': orientation}]}
    recipe = read_json(ROOT / 'templates/sewing-recipe.json')
    recipe['seams'] = {'join': {'kind': 'permanent', 'ease_b_over_a': 0., 'tolerance_relative': .02}}
    recipe['placements'] = {pid: copy.deepcopy(recipe['placements'][pid]) for pid in data['pieces']}
    recipe['trial_pieces'] = ['front', 'back']
    recipe['pins'] = []
    before = digest([data, recipe])
    samples, seams, _ = prepare_boundaries(data, recipe, {'join': [parameter]})
    if before != digest([data, recipe]):
        raise AssertionError('Official source boundary preparation mutated its inputs')
    native = {'component_id': 'garment.coat', 'panels': {}, 'rest_cm': [], 'seams': {}}
    offsets = {}
    for pid, row in samples.items():
        offset = len(native['rest_cm'])
        offsets[pid] = offset
        native['rest_cm'].extend(f32(uv) + [0.] for uv in row['polygon'])
        indices = list(range(offset, len(native['rest_cm'])))
        native['panels'][pid] = {'indices': indices, 'boundary': list(indices),
            'boundary_source_arclength_cm': row['keys'], 'source_contour_sha256': row['source_sha256'],
            'edges': {name: [offset + index for index in ids] for name, ids in row['edges'].items()}}
    for sid, row in seams.items():
        native['seams'][sid] = {name: copy.deepcopy(row[name])
                               for name in ('piece_a', 'piece_b', 'kind', 'parameters')}
        native['seams'][sid]['pairs'] = [[a + offsets[row['piece_a']], b + offsets[row['piece_b']]]
                                        for a, b in zip(row['a'], row['b'])]
    links = [{**data['seams'][0], 'id': 'garment.coat::join', 'source_link_id': 'join',
              'component_id': 'garment.coat', 'kind': 'permanent'}]
    return data, recipe, native, links, parameter


class SourceUVWitnesses(unittest.TestCase):
    def test_midpoint_witness_recovers_original_uv_when_central_key_roundtrip_is_different(self):
        piece, _, native, links = fixture()
        before = digest([piece, native, links])
        keys = native['panels']['front']['boundary_source_arclength_cm']
        contour = piece['vertices'] + piece['vertices'][:1]
        central = sample_chain(contour, keys[2] / chain_lengths(contour)[-1])
        self.assertNotEqual(f32(central), native['rest_cm'][2][:2])
        result = source_boundary_seam_witnesses(piece, 'front', 'coat', native, links)
        self.assertEqual(set(result), {1, 2, 3})
        self.assertEqual(f32(result[2]['source_uv_cm']), native['rest_cm'][2][:2])
        self.assertEqual(result[2]['source_uv_cm'], sample_chain(
            edge_chain(piece, 'join')[1], native['seams']['join']['parameters'][1]))
        proof = result[2]['evidence']
        self.assertEqual(round(proof['source_perimeter_position_cm'], 8), keys[2])
        self.assertLessEqual(abs(proof['source_perimeter_position_cm'] - keys[2]), .5e-8)
        self.assertEqual(proof['binary32_round_trip'], 'EXACT')
        self.assertEqual(proof['witnesses'][0]['source_segment_vertex_ids'], [1, 2])
        self.assertEqual(proof['qualification'], 'NONE')
        self.assertFalse(proof['admissible_for_fit'])
        self.assertEqual(digest([piece, native, links]), before)
        self.assertEqual(json.loads(json.dumps(result[2])), result[2])

    def test_reverse_side_uses_oriented_named_edge_parameter_and_native_pair_order(self):
        piece, peer, native, links = fixture('reverse')
        front = source_boundary_seam_witnesses(piece, 'front', 'coat', native, links)
        back = source_boundary_seam_witnesses(peer, 'back', 'coat', native, links)
        witness = back[7]['evidence']['witnesses'][0]
        self.assertEqual(witness['local_parameter'], 1. - native['seams']['join']['parameters'][1])
        self.assertEqual(witness['side'], 'b')
        self.assertEqual(witness['source_segment_vertex_ids'], [1, 2])
        self.assertEqual(witness['sampler'], 'REVERSED_NAMED_EDGE')
        self.assertEqual(witness['sampler_parameter'], witness['common_parameter'])
        self.assertEqual(f32(front[2]['source_uv_cm']), f32(back[7]['source_uv_cm']))

    def test_official_preparation_forward_and_reverse_witness_all_actual_source_samples(self):
        for orientation in ('forward', 'reverse'):
            with self.subTest(orientation=orientation):
                data, recipe, native, links, parameter = official_preparation_fixture(orientation)
                before = digest([data, recipe, native, links])
                pair_index = native['seams']['join']['parameters'].index(parameter)
                for pid, column in (('front', 0), ('back', 1)):
                    result = source_boundary_seam_witnesses(
                        data['pieces'][pid], pid, 'garment.coat', native, links)
                    self.assertEqual(set(result), {pair[column] for pair in native['seams']['join']['pairs']})
                    for vertex, row in result.items():
                        self.assertEqual(f32(row['source_uv_cm']), native['rest_cm'][vertex][:2])
                        self.assertEqual(row['evidence']['qualification'], 'NONE')
                        self.assertFalse(row['evidence']['admissible_for_fit'])
                if orientation == 'reverse':
                    vertex = native['seams']['join']['pairs'][pair_index][1]
                    points = edge_chain(data['pieces']['back'], 'join')[1]
                    wrong_order = sample_chain(points, 1. - parameter)
                    actual_order = sample_chain(list(reversed(points)), parameter)
                    self.assertNotEqual(f32(wrong_order), native['rest_cm'][vertex][:2])
                    self.assertEqual(f32(actual_order), native['rest_cm'][vertex][:2])
                    self.assertEqual(result[vertex]['source_uv_cm'], actual_order)
                    self.assertEqual(native['rest_cm'][vertex][1], .5000001192092896)
                    self.assertEqual(f32(wrong_order)[1], .5000000596046448)
                self.assertEqual(digest([data, recipe, native, links]), before)

    def test_missing_observed_seams_returns_empty_without_inventing_witnesses(self):
        piece, _, native, links = fixture()
        native['seams'] = {}
        self.assertEqual(source_boundary_seam_witnesses(piece, 'front', 'coat', native, links), {})
        native.pop('seams')
        native.pop('component_id')
        self.assertEqual(source_boundary_seam_witnesses(piece, 'front', 'coat', native, links), {})
        for invalid in (None, [], True):
            native['seams'] = invalid
            with self.subTest(invalid=invalid), self.assertRaises(StudioError):
                source_boundary_seam_witnesses(piece, 'front', 'coat', native, links)

    def test_present_seam_without_its_matching_source_link_is_refused(self):
        piece, _, native, links = fixture()
        for alteration in ('missing', 'component', 'source_link_id', 'piece', 'kind', 'orientation', 'edge'):
            changed = copy.deepcopy(links)
            if alteration == 'missing':
                changed.clear()
            elif alteration == 'component':
                changed[0]['component_id'] = 'other'
            elif alteration == 'source_link_id':
                changed[0]['source_link_id'] = 'other'
            elif alteration == 'piece':
                changed[0]['piece_a'] = 'other'
            elif alteration == 'kind':
                changed[0]['kind'] = 'closure'
            elif alteration == 'orientation':
                changed[0]['orientation'] = 'reverse'
            else:
                changed[0]['edge_a'] = 'other'
            with self.subTest(alteration=alteration), self.assertRaises(StudioError):
                source_boundary_seam_witnesses(piece, 'front', 'coat', native, changed)
        with self.assertRaises(StudioError):
            source_boundary_seam_witnesses(piece, 'front', 'coat', native, links * 2)
        for alteration in ('wrong_piece_a', 'wrong_both_pieces', 'empty_relation'):
            changed = copy.deepcopy(native)
            if alteration == 'empty_relation':
                changed['seams']['join'] = {}
            else:
                changed['seams']['join']['piece_a'] = 'other'
                if alteration == 'wrong_both_pieces':
                    changed['seams']['join']['piece_b'] = 'different'
            with self.subTest(alteration=alteration), self.assertRaises(StudioError):
                source_boundary_seam_witnesses(piece, 'front', 'coat', changed, links)

    def test_parameters_are_finite_unique_sorted_and_cover_both_endpoints(self):
        piece, _, native, links = fixture()
        for values in ([0., 0., 1.], [0., .7, .3, 1.], [.01, .2, 1.], [0., .2, .99],
                       [0., math.nan, 1.], [0., math.inf, 1.], [0., True, 1.], [0., .2, 1.1]):
            changed = copy.deepcopy(native)
            changed['seams']['join']['parameters'] = values
            with self.subTest(values=values), self.assertRaises(StudioError):
                source_boundary_seam_witnesses(piece, 'front', 'coat', changed, links)
        changed = copy.deepcopy(native)
        changed['seams']['join']['parameters'][1] += .001
        with self.assertRaises(StudioError):
            source_boundary_seam_witnesses(piece, 'front', 'coat', changed, links)

    def test_native_pairs_require_exact_edge_membership_order_and_full_parameter_coverage(self):
        piece, _, native, links = fixture()
        for alteration in ('short', 'index', 'foreign', 'interior', 'order', 'peer', 'edge_extra', 'bool'):
            changed = copy.deepcopy(native)
            seam = changed['seams']['join']
            if alteration == 'short':
                seam['pairs'].pop()
            elif alteration == 'index':
                seam['pairs'][1][0] = len(changed['rest_cm'])
            elif alteration == 'foreign':
                seam['pairs'][1][0] = 7
            elif alteration == 'interior':
                seam['pairs'][1][0] = 0
            elif alteration == 'order':
                seam['pairs'][0], seam['pairs'][1] = seam['pairs'][1], seam['pairs'][0]
            elif alteration == 'peer':
                changed['panels']['back']['boundary'].remove(7)
            elif alteration == 'bool':
                seam['pairs'][1][0] = True
            else:
                changed['panels']['front']['edges']['join'].append(4)
            with self.subTest(alteration=alteration), self.assertRaises(StudioError):
                source_boundary_seam_witnesses(piece, 'front', 'coat', changed, links)

    def test_contour_keys_indices_and_actual_binary32_data_cannot_be_substituted(self):
        piece, _, native, links = fixture()
        for alteration in ('sha', 'key', 'duplicate_key', 'keys_short', 'boundary_index',
                           'boundary_duplicate', 'unowned', 'uv', 'not_f32', 'component'):
            changed = copy.deepcopy(native)
            panel = changed['panels']['front']
            if alteration == 'sha':
                panel['source_contour_sha256'] = 'f' * 64
            elif alteration == 'key':
                panel['boundary_source_arclength_cm'][2] += 1e-8
            elif alteration == 'duplicate_key':
                panel['boundary_source_arclength_cm'][2] = panel['boundary_source_arclength_cm'][1]
            elif alteration == 'keys_short':
                panel['boundary_source_arclength_cm'].pop()
            elif alteration == 'boundary_index':
                panel['boundary'][2] = 7
            elif alteration == 'boundary_duplicate':
                panel['boundary'][2] = panel['boundary'][1]
            elif alteration == 'unowned':
                panel['indices'].remove(2)
            elif alteration == 'uv':
                changed['rest_cm'][2][1] = f32([changed['rest_cm'][2][1] + 1e-5])[0]
            elif alteration == 'not_f32':
                changed['rest_cm'][2][1] += 1e-10
            else:
                changed['component_id'] = 'other'
            with self.subTest(alteration=alteration), self.assertRaises(StudioError):
                source_boundary_seam_witnesses(piece, 'front', 'coat', changed, links)

    def test_source_edge_must_follow_original_polygon_semantics(self):
        piece, _, native, links = fixture()
        for ids in ([1, 3], [1, True], [1, 2, 1, 2], [1], [1, 9]):
            changed = copy.deepcopy(piece)
            changed['edges']['join'] = ids
            with self.subTest(ids=ids), self.assertRaises(StudioError):
                source_boundary_seam_witnesses(changed, 'front', 'coat', native, links)

    def test_same_boundary_point_accepts_consistent_witnesses_and_refuses_conflicting_source_uv(self):
        piece, _, native, links = fixture()
        other_link = {**copy.deepcopy(links[0]), 'source_link_id': 'second', 'id': 'coat::second'}
        links.append(other_link)
        native['seams']['second'] = copy.deepcopy(native['seams']['join'])
        witnesses = source_boundary_seam_witnesses(piece, 'front', 'coat', native, links)
        self.assertEqual(len(witnesses[2]['evidence']['witnesses']), 2)
        native['seams']['second']['parameters'][1] -= 1e-12
        # Both variants still have the same native f32 and rounded perimeter key;
        # they nevertheless cannot give different exact source UV to one vertex.
        with self.assertRaisesRegex(StudioError, 'Multiple source sewing witnesses disagree'):
            source_boundary_seam_witnesses(piece, 'front', 'coat', native, links)

    def test_malformed_contracts_raise_local_errors_without_fallback(self):
        piece, _, native, links = fixture()
        for alteration in ('mixed_seam_id', 'rest', 'panels', 'edges', 'source_point', 'nan_source'):
            changed_piece, changed_native = copy.deepcopy(piece), copy.deepcopy(native)
            if alteration == 'mixed_seam_id':
                changed_native['seams'][1] = copy.deepcopy(native['seams']['join'])
            elif alteration == 'rest':
                changed_native['rest_cm'][2] = None
            elif alteration == 'panels':
                changed_native['panels'] = None
            elif alteration == 'edges':
                changed_native['panels']['front']['edges']['join'] = None
            elif alteration == 'source_point':
                changed_piece['vertices'][1] = 'invalid'
            else:
                changed_piece['vertices'][1][0] = math.nan
            with self.subTest(alteration=alteration), self.assertRaises(StudioError):
                source_boundary_seam_witnesses(changed_piece, 'front', 'coat', changed_native, links)


if __name__ == '__main__':
    unittest.main()
