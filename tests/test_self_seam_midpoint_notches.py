import copy
import unittest

from a3d.core import StudioError, digest
from a3d.pattern_preparation import audit_source, prepare_regular_boundaries
from tests.test_pattern_preparation import source_dossier
from tests.test_sewing import sources


def fixture(position=.5):
    data, recipe = sources()
    # Reverse this named edge, preserving its geometric segment. The reverse
    # pairing then has consistent permanent winding on the single front panel.
    data['pieces']['front']['edges']['right-reversed'] = [2, 1]
    data['seams'] = [{'id': 'self', 'piece_a': 'front', 'edge_a': 'left',
                     'piece_b': 'front', 'edge_b': 'right-reversed', 'orientation': 'reverse'}]
    recipe['seams'] = {'self': {'kind': 'permanent', 'ease_b_over_a': 0, 'tolerance_relative': .01}}
    recipe['trial_pieces'] = ['front', 'back']
    dossier = source_dossier(data)
    info = next(p for p in dossier['components'][data['component_id']]['pieces'] if p['id'] == 'front')
    info['pattern']['assembly_marks'][0]['position'] = position
    return data, recipe, dossier, info


class SelfSeamMidpointNotches(unittest.TestCase):
    config = {'spacing_cm': 2., 'min_spacing_cm': .5, 'refinement_distance_cm': .5, 'max_vertices': 4000}

    def test_board_compatible_midpoint_is_paired_on_distinct_edges_without_source_edits(self):
        data, recipe, dossier, _ = fixture()
        before = digest([data, recipe, dossier])
        audit = audit_source(data, recipe, dossier)
        self.assertEqual(audit['status'], 'SOURCE_AUDITED', audit['issues'])
        boundaries, seams, report = prepare_regular_boundaries(data, recipe, self.config, dossier)
        marks = report['source_notches']
        self.assertEqual(len(marks), 2)
        self.assertEqual({m['side'] for m in marks}, {'a', 'b'})
        self.assertEqual({m['common_parameter'] for m in marks}, {.5})
        self.assertEqual(len({m['derived_boundary_vertex'] for m in marks}), 2)
        self.assertFalse(report['ambiguous_source_notches'])
        self.assertEqual(before, digest([data, recipe, dossier]))
        for mark in marks:
            expected = [0, 20] if mark['side'] == 'a' else [20, 20]
            actual = boundaries['front']['polygon'][mark['derived_boundary_vertex']]
            self.assertEqual(actual, expected)

    def test_off_center_reverse_self_notch_stays_ambiguous(self):
        # Near-midpoints must not introduce two almost coincident samples or
        # silently snap the approved source mark to a new position.
        for position in (.3, .50000000001, .500000001):
            with self.subTest(position=position):
                data, recipe, dossier, _ = fixture(position)
                audit = audit_source(data, recipe, dossier)
                self.assertIn('SELF_SEAM_NOTCH_SIDE_UNSPECIFIED', [i['code'] for i in audit['issues']])
                _, _, report = prepare_regular_boundaries(data, recipe, self.config, dossier)
                self.assertTrue(report['ambiguous_source_notches'])
                self.assertFalse(report['source_notches'])

    def test_missing_duplicate_and_invalid_marks_are_not_accepted(self):
        for variant in ('missing', 'duplicate', 'symbol', 'nonfinite'):
            with self.subTest(variant=variant):
                data, recipe, dossier, info = fixture()
                marks = info['pattern']['assembly_marks']
                if variant == 'missing':
                    marks.clear()
                elif variant == 'duplicate':
                    marks.append(copy.deepcopy(marks[0]))
                elif variant == 'symbol':
                    marks[0]['symbol'] = 'unsupported'
                else:
                    marks[0]['position'] = float('inf')
                    # Nonfinite JSON cannot receive a source identity at all.
                    with self.assertRaises(ValueError):
                        audit_source(data, recipe, dossier)
                    with self.assertRaisesRegex(StudioError, 'finite normalized'):
                        prepare_regular_boundaries(data, recipe, self.config, dossier)
                    continue
                audit = audit_source(data, recipe, dossier)
                self.assertNotEqual(audit['status'], 'SOURCE_AUDITED')
                self.assertTrue(audit['issues'])


if __name__ == '__main__':
    unittest.main()
