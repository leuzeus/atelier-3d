"""A tube can follow a declared local segment without a fabricated skin anchor."""
import copy
import math
import unittest
from unittest.mock import patch

from a3d.core import StudioError, digest, sha
from a3d.cloth_metrics import principal_stretches
from a3d.garment_guides import limb_volume_frames, garment_volume_frames, anatomical_attachment_controls
from a3d.limb_axis_binding import resolve_segment_axis, segment_center
from a3d.garment_guide_policy import prepare_guide_policy, reconstruct_guide_policy, verify_guide_policy
from tests.test_garment_guides import limb_fixture


def fixture(side='right'):
    data, semantics, profile = limb_fixture(role='cuff', side=side)
    profile['landmarks']['joint_a'] = {'point_cm': [15., 3., 20.]}
    profile['landmarks']['joint_b'] = {'point_cm': [10., 0., 0.]}
    policy = {'guide_kind': 'LIMB_SEGMENT_AXIS_V1', 'anatomical_region': 'lower_arm.'+side,
              'axis_landmarks': ['joint_a', 'joint_b'], 'transverse_direction_body': [0., 1., 0.],
              'source_end_edges': {'proximal': 'proximal', 'distal': 'distal'},
              'source_anchor_end': 'distal'}
    return data, semantics, profile, {'paths': {}, 'pieces': {'limb': policy}}


class LimbSegmentAxis(unittest.TestCase):
    def test_explicit_axis_preserves_lengths_and_does_not_add_skin_attachment(self):
        for side in ('left', 'right'):
            data, semantics, profile, refs = fixture(side)
            old = limb_volume_frames(data, semantics, profile, limb_parameterization='SOURCE_SEWN_DOMAIN_V1')
            before = digest([data, semantics, profile, refs])
            result = limb_volume_frames(data, semantics, profile, anatomical_references=refs,
                                        limb_parameterization='SOURCE_SEWN_DOMAIN_V1')
            cage = result['panels']['limb']; previous = old['panels']['limb']
            self.assertEqual(previous['uv_cm'], cage['uv_cm'])
            self.assertEqual(previous['triangles'], cage['triangles'])
            for triangle in cage['triangles']:
                source = [cage['uv_cm'][i] for i in triangle]
                actual = principal_stretches(source, [cage['target_cm'][i] for i in triangle])
                expected = principal_stretches(source, [previous['target_cm'][i] for i in triangle])
                self.assertLess(max(abs(a-b) for a, b in zip(actual, expected)), 1e-11)
            self.assertEqual(anatomical_attachment_controls(data, result['panels'], refs), [])
            evidence = result['evidence'][0]['source_segment_axis']
            self.assertEqual(evidence['anchor_body_cm'], [10., 0., 0.])
            self.assertEqual(evidence['source_axial_scale'], 1.)
            self.assertGreater(evidence['opposite_landmark_residual_cm'], 0.)
            self.assertFalse(evidence['anatomical_attachment_added'])
            self.assertEqual(before, digest([data, semantics, profile, refs]))
            self.assertEqual(result['qualification'], 'NONE')

    def test_both_anchor_ends_and_source_v_directions_keep_opposite_residual(self):
        for anchor in ('proximal', 'distal'):
            for reverse in (False, True):
                data, _, profile, refs = fixture()
                piece = data['pieces']['limb']; policy = refs['pieces']['limb']
                policy['source_anchor_end'] = anchor
                if reverse:
                    for p in piece['vertices']:
                        p[1] = -p[1]
                binding = resolve_segment_axis(piece, profile, policy)
                e = binding['evidence']
                expected = profile['landmarks'][policy['axis_landmarks'][0 if anchor == 'proximal' else 1]]['point_cm']
                self.assertEqual(segment_center(binding, e['source_end_v_cm'][anchor]), expected)
                other = 'distal' if anchor == 'proximal' else 'proximal'
                self.assertAlmostEqual(math.dist(expected, segment_center(binding, e['source_end_v_cm'][other])),
                                       e['source_axial_length_cm'])

    def test_arbitrary_panel_rotated_body_frame_and_historical_default(self):
        data, semantics, profile, refs = fixture()
        legacy = limb_volume_frames(data, semantics, profile)
        self.assertEqual(legacy, limb_volume_frames(data, semantics, profile, anatomical_references={'paths': {}, 'pieces': {}}))
        semantics['limb']['role'] = 'panel'
        refs['pieces']['limb']['anatomical_region'] = 'custom:measured-segment'
        result = limb_volume_frames(data, semantics, profile, anatomical_references=refs)
        turned = copy.deepcopy(profile)
        turned['frame'] = {'origin_cm': [20., -7., 53.], 'right': [0., 1., 0.],
                           'forward': [0., 0., 1.], 'up': [1., 0., 0.]}
        rotated = limb_volume_frames(data, semantics, turned, anatomical_references=refs)
        for p, q in zip(result['panels']['limb']['target_cm'], rotated['panels']['limb']['target_cm']):
            self.assertLess(math.dist(q, [20.+p[2], -7.+p[0], 53.+p[1]]), 1e-10)

    def test_invalid_segment_and_source_end_policies_are_refused(self):
        changes = [lambda p: p.update(source_anchor_end='middle'),
                   lambda p: p.update(axis_landmarks=['joint_a', 'joint_a']),
                   lambda p: p.update(axis_landmarks=['joint_a', 'absent']),
                   lambda p: p.update(transverse_direction_body=[-5., -3., -20.]),
                   lambda p: p.update(transverse_direction_body=[True, 0., 0.]),
                   lambda p: p.update(anatomical_region='unknown'),
                   lambda p: p.update(anatomical_region='lower_arm.left'),
                   lambda p: p.update(source_end_edges={'proximal': 'front', 'distal': 'distal'}),
                   lambda p: p.update(source_end_edges={'proximal': 'distal', 'distal': 'distal'}),
                   lambda p: p.update(attachment_path_ref='fabricated')]
        for change in changes:
            data, semantics, profile, refs = fixture()
            change(refs['pieces']['limb'])
            with self.subTest(change=change), self.assertRaises(StudioError):
                limb_volume_frames(data, semantics, profile, anatomical_references=refs)
        data, semantics, profile, refs = fixture()
        profile['landmarks']['joint_a']['point_cm'] = profile['landmarks']['joint_b']['point_cm'][:]
        with self.assertRaises(StudioError):
            limb_volume_frames(data, semantics, profile, anatomical_references=refs)
        data, semantics, profile, refs = fixture()
        refs['pieces']['limb']['axis_landmarks'] = ['elbow.left', 'joint_b']
        profile['landmarks']['elbow.left'] = {'point_cm': [15., 3., 20.]}
        with self.assertRaisesRegex(StudioError, 'side'):
            limb_volume_frames(data, semantics, profile, anatomical_references=refs)

    def test_direction_magnitude_is_not_a_placement_scale_and_bad_arithmetic_is_refused(self):
        data, semantics, profile, refs = fixture()
        first = limb_volume_frames(data, semantics, profile, anatomical_references=refs)['panels']['limb']
        refs['pieces']['limb']['transverse_direction_body'] = [0., 1e300, 0.]
        second = limb_volume_frames(data, semantics, profile, anatomical_references=refs)['panels']['limb']
        self.assertEqual(first['target_cm'], second['target_cm'])
        profile['landmarks']['joint_a']['point_cm'] = [1e308, 0., 0.]
        profile['landmarks']['joint_b']['point_cm'] = [-1e308, 0., 0.]
        with self.assertRaises(StudioError):
            limb_volume_frames(data, semantics, profile, anatomical_references=refs)

    def test_public_reconstruction_and_invalidation_of_binding_inputs(self):
        from tests.test_anatomical_placement import fixture as body_fixture
        from tests.test_garment_guide_policy import fixture as policy_fixture
        compiled, _, _, ref, _, parameters = policy_fixture()
        profile, geometry, _, document, _ = body_fixture()
        data, semantics, limb_profile, refs = fixture()
        semantics['limb']['role'] = 'panel'
        profile.setdefault('landmarks', {}).update(limb_profile['landmarks'])
        document.update(profile_sha256=digest(profile), pieces=refs['pieces'], paths={},
                        triangles=[[0, 1, 2], [0, 2, 3], [3, 2, 1], [3, 1, 0]])
        references = {'garment.test': document}
        data['component_id'] = 'garment.test'
        compiled['textiles'] = {'limb': {'component_id': 'garment.test', 'source_geometry': data['pieces']['limb'],
                                        'semantics': semantics['limb']}}
        parameters['garment.test'].update(upper_blend=0., surface_sections=False,
            limb_parameterization='SOURCE_SEWN_DOMAIN_V1',
            anatomical_references_ref={'path': 'references.json', 'sha256': 'a'*64})
        inputs = (compiled, profile, geometry, ref)
        policy = prepare_guide_policy(*inputs, parameters, anatomical_references=references)
        guides, _ = reconstruct_guide_policy(*inputs, {'garment.test': data}, policy, anatomical_references=references)
        self.assertIn('limb', guides['garment.test']['panels'])
        self.assertEqual(guides['garment.test']['status'], 'GARMENT_GUIDES_PREPARED')
        self.assertEqual(guides['garment.test'].get('anatomical_attachment_constraints', {}).get('controls', []), [])
        result = verify_guide_policy(*inputs, {'garment.test': data}, policy, guides, anatomical_references=references)
        self.assertEqual(result['comparison'], 'FULL_UNROUNDED_GUIDE_REPORT_IDENTICAL')
        with patch('a3d.garment_guide_policy.sha', side_effect=lambda path:
                   'f'*64 if path.name == 'limb_axis_binding.py' else sha(path)):
            with self.assertRaisesRegex(StudioError, 'generator code is stale'):
                reconstruct_guide_policy(*inputs, {'garment.test': data}, policy, anatomical_references=references)
        changed = copy.deepcopy(references)
        changed['garment.test']['pieces']['limb']['source_anchor_end'] = 'proximal'
        with self.assertRaises(StudioError):
            reconstruct_guide_policy(*inputs, {'garment.test': data}, policy, anatomical_references=changed)


if __name__ == '__main__':
    unittest.main()
