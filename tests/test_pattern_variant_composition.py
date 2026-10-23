"""Synthetic inputs only: no private MAIN source or authorization fixtures."""
import copy
import math
import unittest

from a3d.core import StudioError, canonical
from a3d.pattern_variant_composition import compose_pattern_variant_dossier, verify_pattern_variant_scope


def fixture():
    piece = {'vertices': [[0., 0.], [4., 0.], [4., 6.], [0., 6.]],
             'faces': [[0, 1, 2], [0, 2, 3]],
             'edges': {'front': [3, 0], 'back': [1, 2], 'top': [2, 3], 'bottom': [0, 1]},
             'position_cm': [0., 0., 0.], 'rotation_degrees': [0., 0., 0.]}
    ids = ['front', 'sleeve-left', 'back', 'sleeve-right', 'cuff-left']
    garment = {'component_id': 'garment.test', 'units': 'cm', 'pieces': {pid: copy.deepcopy(piece) for pid in ids},
        'seams': [{'id': pid+'-underarm', 'piece_a': pid, 'edge_a': 'front', 'piece_b': pid,
                   'edge_b': 'back', 'kind': 'permanent', 'orientation': 'reverse'} for pid in ids],
        'material': {'mass_kg': .2, 'tension_stiffness': 20., 'compression_stiffness': 20.,
                     'shear_stiffness': 10., 'bending_stiffness': .3}}
    rows = [{'id': pid, 'label': pid, 'material': 'declared-wool', 'dimensions_cm': [4., 6.],
        'pattern': {'cut_outline_cm': copy.deepcopy(piece['vertices']), 'cut_quantity': 1,
                    'assembly_marks': [{'id': 'mid', 'seam_id': pid+'-underarm', 'position': .5, 'symbol': 'notch'},
                                       {'id': 'quarter', 'seam_id': pid+'-underarm', 'position': .25, 'symbol': 'notch'}],
                    'folds': []}} for pid in ids]
    dossier = {'schema_version': 1, 'asset_id': 'synthetic.pattern-review', 'units': 'cm',
        'title': 'Explicit synthetic source', 'body_measurements': {'source_ref': 'synthetic:unchanged-body'},
        'components': {'garment.test': {'pipeline': 'PATTERN_SEWN', 'assembly_notes': ['unchanged'], 'pieces': rows},
                       'prop.test': {'pipeline': 'MULTIVIEW_PART', 'assembly_notes': ['separate'],
                                     'pieces': [{'id': 'buckle', 'dimensions_cm': [1., 1., 1.]}]}}}
    variant = copy.deepcopy(garment); candidate = copy.deepcopy(dossier)
    for pid in ('sleeve-left', 'sleeve-right'):
        variant['pieces'][pid]['vertices'][1][0] = 5.
        row = next(row for row in candidate['components']['garment.test']['pieces'] if row['id'] == pid)
        row['pattern']['cut_outline_cm'] = copy.deepcopy(variant['pieces'][pid]['vertices'])
        row['dimensions_cm'][0] = 5.
        row['pattern']['assembly_marks'].reverse()
    return garment, variant, dossier, candidate


SCOPE = ['sleeve-left', 'sleeve-right']


class PatternVariantComposition(unittest.TestCase):
    def test_only_explicit_sleeves_change_and_inputs_outputs_do_not_alias(self):
        original, variant, dossier, candidate = fixture()
        before = canonical([original, variant, dossier, candidate])
        verification = verify_pattern_variant_scope(original, variant, SCOPE)
        result = compose_pattern_variant_dossier(dossier, candidate, SCOPE)
        self.assertEqual(verification['changed_piece_ids'], SCOPE)
        self.assertEqual(result['dossier'], candidate)
        self.assertEqual(before, canonical([original, variant, dossier, candidate]))
        result['dossier']['components']['garment.test']['pieces'][1]['pattern']['assembly_marks'][0]['position'] = .8
        self.assertEqual(before, canonical([original, variant, dossier, candidate]))
        self.assertEqual(result['status'], 'COMPOSED_INPUTS_ONLY')
        for field in ('construction', 'fitting', 'permission', 'human_review'):
            self.assertEqual(result[field], 'NOT_GRANTED')
        self.assertEqual(result['qualification'], 'NONE')

    def test_outside_scope_package_change_refused_even_one_ulp(self):
        for change in ('coordinate', 'placement', 'topology'):
            original, variant, _, _ = fixture()
            if change == 'coordinate': variant['pieces']['front']['vertices'][1][0] = math.nextafter(4., math.inf)
            elif change == 'placement': variant['pieces']['front']['position_cm'][0] = .01
            else: variant['pieces']['front']['faces'].reverse()
            with self.subTest(change=change), self.assertRaisesRegex(StudioError, 'outside reviewed scope'):
                verify_pattern_variant_scope(original, variant, SCOPE)

    def test_package_globals_material_and_seam_order_remain_exact(self):
        for change in ('component', 'material', 'seam-kind', 'seam-order', 'units'):
            original, variant, _, _ = fixture()
            if change == 'component': variant['component_id'] = 'garment.other'
            elif change == 'material': variant['material']['mass_kg'] = math.nextafter(.2, math.inf)
            elif change == 'seam-kind': variant['seams'][0]['kind'] = 'detachable'
            elif change == 'seam-order': variant['seams'].reverse()
            else: variant['units'] = 'm'
            with self.subTest(change=change), self.assertRaises(StudioError):
                verify_pattern_variant_scope(original, variant, SCOPE)

    def test_package_piece_and_edge_ids_cannot_be_added_removed_or_renamed(self):
        for change in ('missing', 'added', 'renamed', 'edge'):
            original, variant, _, _ = fixture()
            if change == 'missing': variant['pieces'].pop('cuff-left')
            elif change == 'added': variant['pieces']['extra'] = copy.deepcopy(variant['pieces']['front'])
            elif change == 'renamed': variant['pieces']['sleeve-other'] = variant['pieces'].pop('sleeve-left')
            else: variant['pieces']['sleeve-left']['edges']['unused'] = [0, 1]
            with self.subTest(change=change), self.assertRaises(StudioError):
                verify_pattern_variant_scope(original, variant, SCOPE)

    def test_duplicate_package_seams_and_missing_seam_source_rejected(self):
        for side in ('approved', 'variant'):
            original, variant, _, _ = fixture()
            data = original if side == 'approved' else variant
            data['seams'].append(copy.deepcopy(data['seams'][0]))
            with self.subTest(side=side), self.assertRaisesRegex(StudioError, 'duplicate seam IDs'):
                verify_pattern_variant_scope(original, variant, SCOPE)
        original, variant, _, _ = fixture(); variant['seams'][0]['edge_a'] = 'missing'
        with self.assertRaisesRegex(StudioError, 'absent piece or named edge'):
            verify_pattern_variant_scope(original, variant, SCOPE)

    def test_invalid_scope_refused_by_both_helpers(self):
        for scope in ([], (), None, 'sleeve-left', {'sleeve-left'}, [True], [''], ['  '], ['missing'], SCOPE+SCOPE):
            original, variant, dossier, candidate = fixture()
            with self.subTest(scope=scope), self.assertRaises(StudioError):
                verify_pattern_variant_scope(original, variant, scope)
            with self.subTest(scope=scope), self.assertRaises(StudioError):
                compose_pattern_variant_dossier(dossier, candidate, scope)

    def test_one_ulp_unreviewed_notch_is_preserved_and_reported_without_epsilon(self):
        _, _, dossier, candidate = fixture()
        row = candidate['components']['garment.test']['pieces'][2]
        row['pattern']['assembly_marks'][0]['position'] = math.nextafter(.5, 1.)
        result = compose_pattern_variant_dossier(dossier, candidate, SCOPE)
        actual = result['dossier']['components']['garment.test']['pieces'][2]
        self.assertEqual(canonical(actual), canonical(dossier['components']['garment.test']['pieces'][2]))
        excluded = result['excluded_unreviewed_differences']
        self.assertEqual(len(excluded), 1); self.assertEqual(excluded[0]['piece_id'], 'back')
        diff = excluded[0]['differences'][0]
        self.assertEqual(diff['path'], '/pattern/assembly_marks/0/position')
        self.assertEqual(diff['approved_value'], .5)
        self.assertEqual(diff['variant_value'], math.nextafter(.5, 1.))

    def test_original_row_component_and_unreviewed_mark_order_retained(self):
        _, _, dossier, candidate = fixture()
        rows = candidate['components']['garment.test']['pieces']; rows.reverse()
        next(row for row in rows if row['id'] == 'back')['pattern']['assembly_marks'].reverse()
        candidate['components'] = dict(reversed(list(candidate['components'].items())))
        result = compose_pattern_variant_dossier(dossier, candidate, SCOPE)
        composed = result['dossier']['components']['garment.test']['pieces']
        self.assertEqual([row['id'] for row in composed], [row['id'] for row in dossier['components']['garment.test']['pieces']])
        self.assertEqual(list(result['dossier']['components']), list(dossier['components']))
        self.assertEqual(composed[2]['pattern']['assembly_marks'], dossier['components']['garment.test']['pieces'][2]['pattern']['assembly_marks'])
        self.assertEqual(composed[1]['pattern']['assembly_marks'], next(row for row in rows if row['id']=='sleeve-left')['pattern']['assembly_marks'])
        self.assertEqual(len(result['excluded_variant_order_changes']), 1)
        self.assertEqual(result['excluded_unreviewed_differences'][0]['piece_id'], 'back')

    def test_dossier_global_component_and_owner_changes_refused(self):
        for change in ('global', 'component-global', 'component-id', 'owner'):
            _, _, dossier, candidate = fixture()
            if change == 'global': candidate['body_measurements']['source_ref'] = 'other:body'
            elif change == 'component-global': candidate['components']['garment.test']['assembly_notes'].append('new')
            elif change == 'component-id': candidate['components']['prop.changed'] = candidate['components'].pop('prop.test')
            else: candidate['components']['prop.test']['pieces'].append(candidate['components']['garment.test']['pieces'].pop(1))
            with self.subTest(change=change), self.assertRaises(StudioError):
                compose_pattern_variant_dossier(dossier, candidate, SCOPE)

    def test_missing_extra_or_duplicate_dossier_pieces_refused(self):
        for change in ('missing', 'extra', 'duplicate', 'cross-component'):
            _, _, dossier, candidate = fixture()
            rows = candidate['components']['garment.test']['pieces']
            if change == 'missing': rows.pop()
            elif change == 'extra': rows.append(dict(copy.deepcopy(rows[0]), id='extra'))
            elif change == 'duplicate': rows.append(copy.deepcopy(rows[0]))
            else: candidate['components']['prop.test']['pieces'].append(copy.deepcopy(rows[0]))
            with self.subTest(change=change), self.assertRaises(StudioError):
                compose_pattern_variant_dossier(dossier, candidate, SCOPE)

    def test_duplicate_marks_and_folds_refused_including_excluded_rows(self):
        for side in ('approved', 'variant'):
            for field in ('assembly_marks', 'folds'):
                _, _, dossier, candidate = fixture()
                target = dossier if side == 'approved' else candidate
                pattern = target['components']['garment.test']['pieces'][0]['pattern']
                if field == 'folds': pattern[field] = [{'id': 'fold', 'points_cm': [[0.,0.],[0.,1.]]}]
                pattern[field].append(copy.deepcopy(pattern[field][0]))
                with self.subTest(side=side, field=field), self.assertRaisesRegex(StudioError, 'duplicate'):
                    compose_pattern_variant_dossier(dossier, candidate, SCOPE)

    def test_same_mark_id_on_distinct_seams_is_legal_and_row_order_is_exact(self):
        original, variant, dossier, candidate = fixture()
        for pid in ('front', 'sleeve-left'):
            seam = {'id': pid+'-cap', 'piece_a': pid, 'edge_a': 'top', 'piece_b': pid,
                    'edge_b': 'bottom', 'orientation': 'reverse', 'kind': 'permanent'}
            original['seams'].append(copy.deepcopy(seam)); variant['seams'].append(copy.deepcopy(seam))
            source = next(row for row in dossier['components']['garment.test']['pieces'] if row['id']==pid)
            other = next(row for row in candidate['components']['garment.test']['pieces'] if row['id']==pid)
            marks = [{'id': 'midpoint', 'seam_id': pid+'-underarm', 'position': .5, 'symbol': 'notch'},
                     {'id': 'midpoint', 'seam_id': pid+'-cap', 'position': .25, 'symbol': 'notch'}]
            source['pattern']['assembly_marks'] = copy.deepcopy(marks)
            other['pattern']['assembly_marks'] = copy.deepcopy(list(reversed(marks)))
        before = canonical([original, variant, dossier, candidate])
        verify_pattern_variant_scope(original, variant, SCOPE)
        result = compose_pattern_variant_dossier(dossier, candidate, SCOPE)
        rows = result['dossier']['components']['garment.test']['pieces']
        self.assertEqual(rows[0]['pattern']['assembly_marks'], dossier['components']['garment.test']['pieces'][0]['pattern']['assembly_marks'])
        self.assertEqual(rows[1]['pattern']['assembly_marks'], candidate['components']['garment.test']['pieces'][1]['pattern']['assembly_marks'])
        self.assertEqual([row['piece_id'] for row in result['excluded_unreviewed_differences']], ['front'])
        self.assertEqual(canonical([original, variant, dossier, candidate]), before)

    def test_repeated_mark_seam_id_pair_is_refused_even_when_other_values_differ(self):
        for side in ('approved', 'variant'):
            _, _, dossier, candidate = fixture()
            target = dossier if side == 'approved' else candidate
            marks = target['components']['garment.test']['pieces'][0]['pattern']['assembly_marks']
            repeated = copy.deepcopy(marks[0]); repeated['position'] = .75; repeated['symbol'] = 'double-notch'
            marks.append(repeated)
            before = canonical([dossier, candidate])
            with self.subTest(side=side), self.assertRaisesRegex(StudioError, 'duplicate assembly_marks'):
                compose_pattern_variant_dossier(dossier, candidate, SCOPE)
            self.assertEqual(canonical([dossier, candidate]), before)

    def test_assembly_mark_requires_a_real_nonempty_seam_id(self):
        for seam_id in (None, '', '  ', True, 1, []):
            _, _, dossier, candidate = fixture()
            candidate['components']['garment.test']['pieces'][0]['pattern']['assembly_marks'][0]['seam_id'] = seam_id
            with self.subTest(seam_id=seam_id), self.assertRaisesRegex(StudioError, 'nonempty string ID'):
                compose_pattern_variant_dossier(dossier, candidate, SCOPE)

    def test_excluded_addition_removal_and_changed_list_reported_exactly(self):
        _, _, dossier, candidate = fixture()
        row = candidate['components']['garment.test']['pieces'][0]
        row.pop('label'); row['new_note'] = 'excluded'; row['pattern']['folds'].append({'id': 'one', 'points_cm': [[0.,0.],[0.,1.]]})
        result = compose_pattern_variant_dossier(dossier, candidate, SCOPE)
        self.assertEqual(result['dossier']['components']['garment.test']['pieces'][0], dossier['components']['garment.test']['pieces'][0])
        diffs = {row['path']: row for row in result['excluded_unreviewed_differences'][0]['differences']}
        self.assertFalse(diffs['/label']['variant_present'])
        self.assertFalse(diffs['/new_note']['approved_present'])
        self.assertEqual(diffs['/pattern/folds']['approved_value'], [])

    def test_nonfinite_and_malformed_rows_refused_without_mutation(self):
        for value in (math.nan, math.inf, -math.inf):
            original, variant, dossier, candidate = fixture()
            variant['pieces']['sleeve-left']['vertices'][0][0] = value
            with self.subTest(value=value), self.assertRaises(StudioError):
                verify_pattern_variant_scope(original, variant, SCOPE)
            candidate['components']['garment.test']['pieces'][0]['dimensions_cm'][0] = value
            with self.subTest(value=value), self.assertRaises(StudioError):
                compose_pattern_variant_dossier(dossier, candidate, SCOPE)
        for value in (None, [], {'components': []}, {'components': {'one': {'pieces': [None]}}}):
            _, _, dossier, _ = fixture()
            with self.subTest(value=value), self.assertRaises(StudioError):
                compose_pattern_variant_dossier(dossier, value, SCOPE)

    def test_json_type_and_signed_zero_changes_are_exact(self):
        _, _, dossier, candidate = fixture()
        candidate['components']['garment.test']['pieces'][0]['dimensions_cm'][0] = 4
        candidate['components']['garment.test']['pieces'][0]['pattern']['cut_outline_cm'][0][0] = -0.0
        result = compose_pattern_variant_dossier(dossier, candidate, SCOPE)
        self.assertEqual(len(result['excluded_unreviewed_differences'][0]['differences']), 2)
        self.assertEqual(canonical(result['dossier']['components']['garment.test']['pieces'][0]),
                         canonical(dossier['components']['garment.test']['pieces'][0]))

    def test_non_json_values_and_keys_cannot_collapse_during_comparison(self):
        for value in ({1: 'coerced-key'}, (1., 2.), {1., 2.}, object()):
            _, _, dossier, candidate = fixture()
            dossier['extra'] = value; candidate['extra'] = value
            with self.subTest(kind=type(value).__name__), self.assertRaisesRegex(StudioError, 'finite JSON values'):
                compose_pattern_variant_dossier(dossier, candidate, SCOPE)
        _, _, dossier, candidate = fixture()
        dossier['cycle'] = dossier
        with self.assertRaisesRegex(StudioError, 'finite JSON values'):
            compose_pattern_variant_dossier(dossier, candidate, SCOPE)


if __name__ == '__main__':
    unittest.main()
