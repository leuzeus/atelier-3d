"""An open material cap is not a full circumference above its sewn domain."""
import copy
import math
import time
import unittest
from unittest.mock import patch

from a3d.core import StudioError, digest
from a3d.cloth_metrics import principal_stretches
from a3d.garment_guides import (limb_volume_frames, garment_volume_frames,
    validate_limb_parameterization, _paired_limb_boundary, _source_span, _world)
from a3d.limb_surface_sampling import compile_sewn_domain, sewn_domain_interval
from a3d.pattern_assembly import _compile_cage, _cage_point
from a3d.source_seam_coupling import _Budget
from tests.test_garment_guides import limb_fixture


MODE = 'SOURCE_SEWN_DOMAIN_V1'


def open_cap(side='right'):
    data, semantics, profile = limb_fixture(side=side)
    piece = data['pieces']['limb']; sign = 1 if side == 'right' else -1
    piece['vertices'] = [[sign*u, v] for u, v in
        ((0., 0.), (12., 0.), (12., 8.), (8., 12.), (6., 14.), (4., 12.), (0., 8.))]
    piece['faces'] = [[0, i, i+1] for i in range(1, 6)]
    piece['edges'] = {'front': [6, 0], 'back': [1, 2], 'proximal': [3, 4, 5], 'distal': [0, 1]}
    return data, semantics, profile


def extension_metrics(frame, stop=8.):
    values = []
    for face in frame['triangles']:
        source = [frame['uv_cm'][i] for i in face]
        if min(p[1] for p in source) >= stop:
            values.append(principal_stretches(source, [frame['target_cm'][i] for i in face]))
    return [min(row[0] for row in values), max(row[1] for row in values)]


class SewnLimbDomain(unittest.TestCase):
    def test_default_and_explicit_historical_reports_are_byte_equivalent(self):
        identities = {
            'sleeve': ('a402cac4075cca3229668fadfbe31b521ea450ebd3780f30d1d7811433a9c3b6',
                       '54ee055377187030bd50b872783a7d864cbcdde0e25dc33de6b2164033be4d9d'),
            'cuff': ('1b04074a5eca060f6248424aae0648949f61f4c915b5d1bab4d3d5dc08d40cbe',
                     'feb7e82fe2ff6f2e927ff9762c7fc62f2d217aa1a34c7e70754d247e5df2b518')}
        for role, (direct_hash, dispatched_hash) in identities.items():
            args = limb_fixture(role=role)
            for function, expected in ((limb_volume_frames, direct_hash), (garment_volume_frames, dispatched_hash)):
                with self.subTest(role=role, function=function.__name__):
                    result = function(*args)
                    self.assertEqual(digest(result), expected)
                    self.assertEqual(result, function(*args, limb_parameterization='SOURCE_ROW_CIRCUMFERENCE_V1'))

    def test_open_cap_preserves_material_source_and_reduces_false_compression_on_both_sides(self):
        for side in ('left', 'right'):
            args = open_cap(side); before = digest(args)
            original = limb_volume_frames(*args)['panels']['limb']
            result = limb_volume_frames(*args, limb_parameterization=MODE)
            frame = result['panels']['limb']; evidence = result['evidence'][0]
            low, high = extension_metrics(frame); old_low, old_high = extension_metrics(original)
            self.assertGreater(low, .98); self.assertLess(high, 1.02)
            self.assertLess(old_low, .5); self.assertGreater(old_high, 1.5)
            self.assertEqual(before, digest(args))
            self.assertEqual(result, limb_volume_frames(*args, limb_parameterization=MODE))
            domain = evidence['source_sewn_domain']; sampling = evidence['cage_refinement']
            self.assertEqual(domain['sewn_v_domain_cm'], [0., 8.])
            self.assertEqual(domain['source_v_domain_cm'], [0., 14.])
            self.assertEqual(sampling['source_faces_covered'], len(args[0]['pieces']['limb']['faces']))
            self.assertEqual(sampling['source_boundary_validation'], 'EXISTING_SOURCE_VALIDATOR_PASS')
            self.assertTrue(sampling['exact_rational_partition_area_preserved'])
            self.assertEqual(sampling['material_admission'], 'NOT_GRANTED')
            self.assertEqual(result['qualification'], 'NONE')
            for corner in args[0]['pieces']['limb']['vertices']:
                self.assertIn(corner, frame['uv_cm'])
            for face in frame['triangles']:
                values = [frame['uv_cm'][i][1] for i in face]
                for cut in sampling['cuts_cm']:
                    self.assertFalse(min(values) < cut < max(values))

    def test_new_map_keeps_sewn_rows_and_cuff_center_law(self):
        for role in ('sleeve', 'cuff'):
            data, semantics, profile = limb_fixture(role=role)
            result = limb_volume_frames(data, semantics, profile, limb_parameterization=MODE)
            frame = result['panels']['limb']; piece = data['pieces']['limb']
            for (u, v), actual in zip(frame['uv_cm'], frame['target_cm']):
                low, high = _source_span(piece, v); width = high-low
                angle = 0. if abs(u-low) <= 1e-9 or abs(u-high) <= 1e-9 else 2*math.pi*(u-low)/width
                center_z = 20.-(12.-v) if role == 'sleeve' else v
                expected = _world(profile, [10.+width/(2*math.pi)*math.sin(angle),
                                            -width/(2*math.pi)*math.cos(angle), center_z])
                self.assertLess(math.dist(expected, actual), 1e-12)
            compiled = _compile_cage(frame, 'limb')
            for row in result['evidence'][0]['source_sewing_pairs']:
                points = [_cage_point(frame, compiled, p, 'limb')[0] for p in row['source_uv_pair_cm']]
                self.assertLess(math.dist(*points), 1e-10)
            self.assertIsNone(result['evidence'][0]['cage_refinement']['principal_ranges_by_domain']['OPEN_EXTENSION'])

    def test_custom_member_axis_rotated_body_and_recomputed_anatomical_anchor(self):
        data, semantics, profile = open_cap()
        semantics['limb']['role'] = 'panel'
        profile['landmarks'] = {'joint_a': {'point_cm': [3., 5., 22.]}, 'joint_b': {'point_cm': [3., 5., 0.]}}
        refs = {'paths': {'skin': {'points_body_cm': [[4., 7., 23.], [4., 9., 23.]],
            'closed': False, 'path_sha256': 'a'*64, 'region': 'custom:measured-member-root'}},
            'pieces': {'limb': {'guide_kind': 'LIMB_ATTACHMENT_V1', 'attachment_path_ref': 'skin',
                'path_fraction': .5, 'source_anchor_edge': 'proximal', 'source_anchor_fraction': .5,
                'axis_landmarks': ['joint_a', 'joint_b'], 'transverse_direction_body': [0., 1., 0.],
                'attachment_offset_body': [0., 0., .3]}}}
        before = digest([data, semantics, profile, refs])
        original = limb_volume_frames(data, semantics, profile, anatomical_references=refs)
        result = limb_volume_frames(data, semantics, profile, anatomical_references=refs, limb_parameterization=MODE)
        evidence = result['evidence'][0]['anatomical_attachment']
        self.assertTrue(evidence['placement_recomputed_on_new_cage'])
        self.assertLess(evidence['actual_anchor_residual_cm'], 1e-10)
        self.assertEqual(evidence['target_attachment_world_cm'], [4., 8., 23.3])
        self.assertGreater(math.dist(evidence['translation_world_cm'],
            original['evidence'][0]['anatomical_attachment']['translation_world_cm']), 1.)
        self.assertEqual(before, digest([data, semantics, profile, refs]))
        rotated = copy.deepcopy(profile)
        rotated['frame'] = {'origin_cm': [20., -7., 53.], 'right': [0., 1., 0.],
                            'forward': [0., 0., 1.], 'up': [1., 0., 0.]}
        turned = limb_volume_frames(data, semantics, rotated, anatomical_references=refs, limb_parameterization=MODE)
        self.assertEqual(result['panels']['limb']['uv_cm'], turned['panels']['limb']['uv_cm'])
        for p, q in zip(result['panels']['limb']['target_cm'], turned['panels']['limb']['target_cm']):
            self.assertLess(math.dist(q, [20.+p[2], -7.+p[0], 53.+p[1]]), 1e-9)

    def test_invalid_ambiguous_nonmonotone_or_unsupported_domains_are_refused(self):
        data, semantics, profile = open_cap()
        piece = data['pieces']['limb']; _, pairs, _ = _paired_limb_boundary(data, 'limb')
        for change in (lambda p: p[0].__setitem__('source_v_cm', math.nan),
                       lambda p: p.append(copy.deepcopy(p[0])),
                       lambda p: p[0]['source_uv_pair_cm'][0].__setitem__(1, 100.)):
            bad = copy.deepcopy(pairs); change(bad)
            with self.assertRaises(StudioError):
                compile_sewn_domain(piece, bad, 'limb', _Budget(None, time.monotonic))
        outside = copy.deepcopy(data); outside['pieces']['limb']['vertices'][3][0] = 13.
        with self.assertRaisesRegex(StudioError, 'terminal sewn U interval'):
            limb_volume_frames(outside, semantics, profile, limb_parameterization=MODE)
        ambiguous = copy.deepcopy(data); ambiguous['seams'].append(copy.deepcopy(ambiguous['seams'][0]))
        with self.assertRaisesRegex(StudioError, 'one explicit unary'):
            limb_volume_frames(ambiguous, semantics, profile, limb_parameterization=MODE)
        budget = _Budget(None, time.monotonic); domain = compile_sewn_domain(piece, pairs, 'limb', budget)
        for query in ([math.nan, 9.], [6., 15.], [20., 9.], [0., 13.]):
            with self.assertRaises(StudioError): sewn_domain_interval(piece, domain, query, 'limb', budget)

    def test_shared_budgets_refuse_without_partial_admission_or_source_change(self):
        data, semantics, profile = open_cap(); single = limb_volume_frames(data, semantics, profile, limb_parameterization=MODE)
        data['pieces']['other'] = copy.deepcopy(data['pieces']['limb']); semantics['other'] = copy.deepcopy(semantics['limb'])
        seam = copy.deepcopy(data['seams'][0]); seam.update(id='second-source-seam', piece_a='other', piece_b='other')
        data['seams'].append(seam); before = digest([data, semantics, profile])
        for limits in ({'max_controls': single['source_cage_budget']['controls']+1},
                       {'max_triangles': single['source_cage_budget']['triangles']+1},
                       {'max_source_points': 8}, {'max_source_triangles': 6}):
            with self.subTest(limits=limits), self.assertRaisesRegex(StudioError, 'budget'):
                limb_volume_frames(data, semantics, profile, limb_parameterization=MODE, source_cage_budgets=limits)
        with patch('time.monotonic', side_effect=[0., 0., 2.]):
            with self.assertRaisesRegex(StudioError, 'time budget'):
                limb_volume_frames(data, semantics, profile, limb_parameterization=MODE,
                                   source_cage_budgets={'max_seconds': 1.})
        self.assertEqual(before, digest([data, semantics, profile]))

    def test_dispatcher_and_validator_require_explicit_supported_family(self):
        for value in (None, True, 1, {}, 'SOURCE_SEWN_DOMAIN_V2'):
            with self.subTest(value=value), self.assertRaises(StudioError): validate_limb_parameterization(value)
        data, semantics, profile = open_cap()
        for value in (None, True, 1, 17):
            with self.assertRaises(StudioError):
                limb_volume_frames(data, semantics, profile, limb_parameterization=MODE, cage_subdivisions=value)
        result = garment_volume_frames(data, semantics, profile, limb_parameterization=MODE)
        self.assertEqual(result['status'], 'GARMENT_GUIDES_PREPARED')
        self.assertEqual(result['families'][0]['report']['limb_parameterization'], MODE)
        semantics['limb']['role'] = 'panel'
        with self.assertRaisesRegex(StudioError, 'actual limb guide family'):
            garment_volume_frames(data, semantics, profile, limb_parameterization=MODE)


if __name__ == '__main__': unittest.main()
