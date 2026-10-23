"""Public, source-bound selection of the sewn-domain limb guide."""
import copy
import unittest
from unittest.mock import patch

from a3d.core import StudioError, digest, sha
from a3d.garment_guide_policy import prepare_guide_policy, reconstruct_guide_policy, verify_guide_policy
from tests.test_garment_guide_policy import fixture as policy_fixture
from tests.test_garment_guides import limb_fixture


def fixture():
    compiled, profile, geometry, geometry_ref, _, params = policy_fixture()
    data, semantics, limb_profile = limb_fixture()
    data['component_id'] = 'garment.test'
    profile['landmarks'].update(limb_profile['landmarks'])
    compiled['textiles'] = {pid: {'component_id': 'garment.test',
        'source_geometry': copy.deepcopy(piece), 'semantics': semantics[pid]}
        for pid, piece in data['pieces'].items()}
    params['garment.test'].update(upper_blend=0., surface_sections=False,
                                limb_parameterization='SOURCE_SEWN_DOMAIN_V1')
    return compiled, profile, geometry, geometry_ref, {'garment.test': data}, params


class LimbGuidePolicy(unittest.TestCase):
    def test_public_roundtrip_preserves_sources_and_does_not_admit_fitting(self):
        compiled, profile, geometry, ref, data, params = fixture()
        before = digest([compiled, profile, geometry, ref, data, params])
        policy = prepare_guide_policy(compiled, profile, geometry, ref, params)
        self.assertEqual(policy['version'], 2)
        guides, evidence = reconstruct_guide_policy(compiled, profile, geometry, ref, data, policy)
        self.assertIn('limb', guides['garment.test']['panels'])
        self.assertEqual(guides['garment.test']['qualification'], 'NONE')
        self.assertFalse(evidence['admissible_for_fit'])
        observed = verify_guide_policy(compiled, profile, geometry, ref, data, policy, guides)
        self.assertEqual(observed['comparison'], 'FULL_UNROUNDED_GUIDE_REPORT_IDENTICAL')
        self.assertEqual(before, digest([compiled, profile, geometry, ref, data, params]))

    def test_invalid_modes_refused_before_generation(self):
        compiled, profile, geometry, ref, _, params = fixture()
        for value in ('UNKNOWN', None, True, {'mode': 'SOURCE_SEWN_DOMAIN_V1'}):
            changed = copy.deepcopy(params)
            changed['garment.test']['limb_parameterization'] = value
            with self.subTest(value=value), self.assertRaises(StudioError):
                prepare_guide_policy(compiled, profile, geometry, ref, changed)

    def test_sampling_kernel_change_invalidates_policy(self):
        compiled, profile, geometry, ref, data, params = fixture()
        policy = prepare_guide_policy(compiled, profile, geometry, ref, params)
        self.assertIn('limb_surface_sampling', policy['generator_code_sha256'])
        with patch('a3d.garment_guide_policy.sha', side_effect=lambda path:
                   'f'*64 if path.name == 'limb_surface_sampling.py' else sha(path)):
            with self.assertRaisesRegex(StudioError, 'generator code is stale'):
                reconstruct_guide_policy(compiled, profile, geometry, ref, data, policy)

    def test_historical_mode_preserves_report_and_coordinates(self):
        compiled, profile, geometry, ref, data, params = fixture()
        del params['garment.test']['limb_parameterization']
        old_policy = prepare_guide_policy(compiled, profile, geometry, ref, params)
        old, _ = reconstruct_guide_policy(compiled, profile, geometry, ref, data, old_policy)
        params['garment.test']['limb_parameterization'] = 'SOURCE_ROW_CIRCUMFERENCE_V1'
        explicit = prepare_guide_policy(compiled, profile, geometry, ref, params)
        guides, _ = reconstruct_guide_policy(compiled, profile, geometry, ref, data, explicit)
        self.assertEqual(old_policy['version'], 1)
        self.assertEqual(explicit['version'], 1)
        self.assertEqual(old, guides)

    def test_modern_mode_cannot_claim_historical_generator(self):
        compiled, profile, geometry, ref, data, params = fixture()
        policy = prepare_guide_policy(compiled, profile, geometry, ref, params)
        policy.update(version=1, generator='GARMENT_VOLUME_FRAMES_V1')
        with self.assertRaisesRegex(StudioError, 'version does not match'):
            reconstruct_guide_policy(compiled, profile, geometry, ref, data, policy)


if __name__ == '__main__':
    unittest.main()
