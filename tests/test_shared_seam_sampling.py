import copy
import math
import unittest

from a3d.core import StudioError, digest
from a3d.sewing import (active_sewing_pairs, permanent_support_groups,
                       prepare_boundaries, seam_report)
from a3d.shared_seam_sampling import shared_parameters
from tests.test_sewing import sources


def shared_source(reverse=False, reverse_edge=False):
    _, recipe = sources()
    pieces = {
        'upper': {'vertices': [[0, 0], [3, 0], [7, 0], [10, 0], [10, 3], [0, 3]],
                  'edges': {'whole': [0, 1, 2, 3], 'attachment': [2, 1] if reverse_edge else [1, 2]}},
        'hood': {'vertices': [[0, 0], [10, 0], [10, 3], [0, 3]], 'edges': {'whole': [0, 1]}},
        'lower': {'vertices': [[0, 0], [4, 0], [4, 3], [0, 3]], 'edges': {'attachment': [0, 1]}},
    }
    data = {'component_id': recipe['component_id'], 'pieces': pieces, 'seams': [
        {'id': 'hood-base', 'piece_a': 'upper', 'edge_a': 'whole',
         'piece_b': 'hood', 'edge_b': 'whole', 'orientation': 'reverse', 'kind': 'permanent'},
        {'id': 'attachment', 'piece_a': 'upper', 'edge_a': 'attachment',
         'piece_b': 'lower', 'edge_b': 'attachment',
         'orientation': 'reverse' if reverse else 'forward', 'kind': 'detachable'}]}
    recipe['seams'] = {s['id']: {'kind': s['kind'], 'ease_b_over_a': 0, 'tolerance_relative': .005}
                       for s in data['seams']}
    placement = next(iter(recipe['placements'].values()))
    recipe['placements'] = {pid: copy.deepcopy(placement) for pid in pieces}
    recipe['trial_pieces'] = ['upper', 'hood']
    recipe['pins'] = []
    recipe['mesh']['spacing_cm'] = 3
    return data, recipe


class SharedSeamSampling(unittest.TestCase):
    def assert_complete_runs(self, data, boundaries, seams):
        for source in data['seams']:
            sampled = seams[source['id']]
            self.assertEqual(len(sampled['a']), len(sampled['b']))
            self.assertEqual(sampled['kind'], source['kind'])
            for side in ('a', 'b'):
                ids = sampled[side]
                edge_ids = boundaries[source['piece_'+side]]['edges'][source['edge_'+side]]
                expected = list(reversed(edge_ids)) if side == 'b' and source['orientation'] == 'reverse' else edge_ids
                self.assertEqual(ids, expected, (source['id'], side))
                self.assertEqual(len(ids), len(set(ids)), (source['id'], side, 'duplicate vertices'))

    def test_partial_arc_samples_propagate_both_ways_and_respect_orientation(self):
        for reverse in (False, True):
            for reverse_edge in (False, True):
                with self.subTest(reverse=reverse, reverse_edge=reverse_edge):
                    data, recipe = shared_source(reverse, reverse_edge)
                    original = digest([data, recipe])
                    boundaries, seams, _ = prepare_boundaries(data, recipe,
                        {'hood-base': [.4], 'attachment': [.3]})
                    self.assertEqual(digest([data, recipe]), original)
                    self.assert_complete_runs(data, boundaries, seams)
                    x = 7-4*.3 if reverse_edge else 3+4*.3
                    self.assertTrue(any(abs(p[0]-x) < 1e-12 and p[1] == 0
                                        for p in boundaries['upper']['polygon']))
                    self.assertTrue(any(abs(p[0]-(10-x)) < 1e-12 and p[1] == 0
                                        for p in boundaries['hood']['polygon']))

    def test_declaration_order_does_not_change_sampling(self):
        data, recipe = shared_source(True, True)
        before = prepare_boundaries(data, recipe, {'attachment': [.37]})
        data['seams'].reverse()
        data['pieces'] = dict(reversed(list(data['pieces'].items())))
        after = prepare_boundaries(data, recipe, {'attachment': [.37]})
        self.assertEqual(before[0], after[0])
        self.assertEqual(before[1], after[1])

    def test_curved_source_with_noninteger_arc_lengths_keeps_complete_runs(self):
        data, recipe = shared_source(True)
        upper = data['pieces']['upper']
        upper['vertices'][1] = [3, -2]
        upper['vertices'][2] = [7, -1]
        data['pieces']['hood']['vertices'] = copy.deepcopy(upper['vertices'])
        data['pieces']['hood']['edges']['whole'] = [0, 1, 2, 3]
        width = math.dist(upper['vertices'][1], upper['vertices'][2])
        data['pieces']['lower']['vertices'] = [[0, 0], [width, 0], [width, 3], [0, 3]]
        boundaries, seams, _ = prepare_boundaries(data, recipe, {'attachment': [.31]})
        self.assert_complete_runs(data, boundaries, seams)

    def test_samples_reach_a_second_permanent_partner_through_detachable_link(self):
        data, recipe = shared_source(True, True)
        data['pieces']['lining'] = copy.deepcopy(data['pieces']['lower'])
        recipe['placements']['lining'] = copy.deepcopy(recipe['placements']['lower'])
        data['seams'].append({'id': 'lining-base', 'piece_a': 'lower', 'edge_a': 'attachment',
            'piece_b': 'lining', 'edge_b': 'attachment', 'orientation': 'reverse', 'kind': 'permanent'})
        recipe['seams']['lining-base'] = copy.deepcopy(recipe['seams']['hood-base'])
        boundaries, seams, _ = prepare_boundaries(data, recipe, {'lining-base': [.9]})
        self.assert_complete_runs(data, boundaries, seams)
        self.assertTrue(any(abs(t-.1) < 1e-12 for t in seams['attachment']['parameters']))
        self.assertTrue(any(abs(t-.66) < 1e-12 for t in seams['hood-base']['parameters']))
        original = (boundaries, seams)
        data['seams'] = data['seams'][1:] + data['seams'][:1]
        self.assertEqual(prepare_boundaries(data, recipe, {'lining-base': [.9]})[:2], original)

    def test_only_one_permanent_plus_one_detachable_owner_is_allowed(self):
        for first, second in (('permanent', 'permanent'), ('detachable', 'detachable'),
                              ('permanent', 'closure'), ('closure', 'detachable')):
            with self.subTest(first=first, second=second):
                data, recipe = shared_source()
                for source, kind in zip(data['seams'], (first, second)):
                    source['kind'] = recipe['seams'][source['id']]['kind'] = kind
                with self.assertRaisesRegex(StudioError, 'multiple seams'):
                    seam_report(data, recipe)
        data, recipe = shared_source()
        extra = {**data['seams'][1], 'id': 'another-attachment'}
        data['seams'].append(extra)
        recipe['seams'][extra['id']] = copy.deepcopy(recipe['seams']['attachment'])
        with self.assertRaisesRegex(StudioError, 'multiple seams'):
            seam_report(data, recipe)

    def test_allowing_overlap_does_not_retype_source_or_add_active_sewing(self):
        data, recipe = shared_source()
        _, seams, _ = prepare_boundaries(data, recipe)
        payload = {'seams': {sid: {'kind': seam['kind'], 'pairs': [[i, i+100] for i in range(len(seam['a']))]}
                             for sid, seam in seams.items()}}
        payload['seams']['attachment']['pairs'] = [[1000, 2000]]
        self.assertEqual(active_sewing_pairs(payload), payload['seams']['hood-base']['pairs'])
        self.assertFalse(any(1000 in group or 2000 in group for group in permanent_support_groups(payload)))
        recipe['seams']['attachment']['kind'] = 'permanent'
        with self.assertRaises(StudioError):
            seam_report(data, recipe)

    def test_nonidentity_cycle_is_rejected_without_sampling_iteration(self):
        # Two seams overlap once in the same direction and once in opposite
        # directions: there is no globally consistent affine correspondence.
        pieces = {'a': {'vertices': [[0, 0], [4, 0]]}, 'b': {'vertices': [[0, 0], [4, 0]]}}
        chains = {'first': (('a', [0, 1]), ('b', [0, 1])),
                  'second': (('a', [0, 1]), ('b', [1, 0]))}
        with self.assertRaisesRegex(StudioError, 'inconsistent cyclic'):
            shared_parameters(pieces, chains, {'first': [0., .2, 1.], 'second': [0., 1.]})


if __name__ == '__main__':
    unittest.main()
