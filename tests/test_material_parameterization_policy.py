"""Public selection, replay and invalidation of source-material torso guides."""
import copy
import unittest
from unittest.mock import patch

from a3d.core import StudioError, digest, sha
from a3d.garment_guide_policy import prepare_guide_policy, reconstruct_guide_policy, verify_guide_policy
from a3d.garment_guides import garment_volume_frames
from tests.test_garment_guide_policy import fixture


class MaterialParameterizationPolicy(unittest.TestCase):
    def test_explicit_legacy_selection_keeps_identical_guides_and_v1_policy(self):
        compiled, profile, geometry, ref, data, params = fixture()
        original = digest([compiled, profile, geometry, ref, data, params])
        historical = prepare_guide_policy(compiled, profile, geometry, ref, params)
        guides, _ = reconstruct_guide_policy(compiled, profile, geometry, ref, data, historical)
        self.assertNotIn('section_parameterization', historical['components']['garment.test'])
        self.assertEqual(original, digest([compiled, profile, geometry, ref, data, params]))
        params['garment.test']['section_parameterization'] = 'POLYLINE_ARCLENGTH_V1'
        declared = prepare_guide_policy(compiled, profile, geometry, ref, params)
        self.assertEqual(declared['version'], 1)
        self.assertEqual(reconstruct_guide_policy(compiled, profile, geometry, ref, data, declared)[0], guides)

    def test_unknown_or_inapplicable_mode_refuses_before_reconstruction(self):
        compiled, profile, geometry, ref, data, params = fixture()
        for values in (
                {'section_parameterization': 'GUESSED_U'},
                {'section_parameterization': None},
                {'section_parameterization': 'SOURCE_MATERIAL_U_V1', 'upper_blend': 0.},
                {'section_parameterization': 'SOURCE_MATERIAL_U_V1', 'upper_blend': float('nan')},
                {'section_parameterization': 'SOURCE_MATERIAL_U_V1', 'upper_blend': True},
                {'section_parameterization': 'SOURCE_MATERIAL_U_V1', 'surface_sections': False}):
            selected = copy.deepcopy(params)
            selected['garment.test'].update(values)
            with self.subTest(values=values), self.assertRaises(StudioError):
                prepare_guide_policy(compiled, profile, geometry, ref, selected)

    def test_source_mode_requires_v2_and_is_not_silently_ignored_on_other_roles(self):
        compiled, profile, geometry, ref, data, params = fixture()
        params['garment.test']['section_parameterization'] = 'SOURCE_MATERIAL_U_V1'
        policy = prepare_guide_policy(compiled, profile, geometry, ref, params)
        self.assertEqual(policy['version'], 2)
        self.assertEqual(policy['generator'], 'GARMENT_VOLUME_FRAMES_V2')
        with self.assertRaisesRegex(StudioError, 'actual torso guide family'):
            reconstruct_guide_policy(compiled, profile, geometry, ref, data, policy)
        policy.update(version=1, generator='GARMENT_VOLUME_FRAMES_V1')
        with self.assertRaisesRegex(StudioError, 'generator version'):
            reconstruct_guide_policy(compiled, profile, geometry, ref, data, policy)

    def test_material_sampler_code_change_invalidates_exact_policy(self):
        compiled, profile, geometry, ref, data, params = fixture()
        policy = prepare_guide_policy(compiled, profile, geometry, ref, params)
        guides, _ = reconstruct_guide_policy(compiled, profile, geometry, ref, data, policy)
        self.assertIn('material_section_sampling', policy['generator_code_sha256'])
        with patch('a3d.garment_guide_policy.sha', side_effect=lambda path:
                   'f'*64 if path.name == 'material_section_sampling.py' else sha(path)):
            with self.assertRaisesRegex(StudioError, 'generator code is stale'):
                verify_guide_policy(compiled, profile, geometry, ref, data, policy, guides)

    def test_dispatcher_refuses_unknown_parameterization_even_without_torso(self):
        compiled, profile, _, _, data, _ = fixture()
        semantics = {pid: row['semantics'] for pid, row in compiled['textiles'].items()}
        with self.assertRaisesRegex(StudioError, 'Unsupported torso section parameterization'):
            garment_volume_frames(data['garment.test'], semantics, profile, section_parameterization='UNKNOWN')

    def test_public_policy_replays_actual_source_material_torso_without_admission(self):
        from tests.test_torso_material_parameterization import paired_fixture
        source, semantics, profile, geometry = paired_fixture(with_geometry=True)
        compiled, _, _, ref, _, params = fixture()
        source['component_id'] = 'garment.test'
        data = {'garment.test': source}
        compiled['textiles'] = {pid: {'component_id': 'garment.test', 'source_geometry': copy.deepcopy(piece),
                                     'semantics': copy.deepcopy(semantics[pid])}
                                for pid, piece in source['pieces'].items()}
        params['garment.test']['section_parameterization'] = 'SOURCE_MATERIAL_U_V1'
        original = digest([compiled, profile, geometry, ref, data, params])
        policy = prepare_guide_policy(compiled, profile, geometry, ref, params)
        guides, evidence = reconstruct_guide_policy(compiled, profile, geometry, ref, data, policy)
        self.assertEqual(set(guides['garment.test']['panels']), set(source['pieces']))
        torso = next(row['report'] for row in guides['garment.test']['families'] if row['family'] == 'torso')
        self.assertEqual(torso['source_boundary_cage']['section_parameterization'], 'SOURCE_MATERIAL_U_V1')
        verified = verify_guide_policy(compiled, profile, geometry, ref, data, policy, guides)
        self.assertEqual(verified['comparison'], 'FULL_UNROUNDED_GUIDE_REPORT_IDENTICAL')
        self.assertEqual(evidence['qualification'], 'NONE')
        self.assertFalse(evidence['admissible_for_fit'])
        self.assertEqual(original, digest([compiled, profile, geometry, ref, data, params]))
        old_mode = copy.deepcopy(policy)
        old_mode['components']['garment.test']['section_parameterization'] = 'POLYLINE_ARCLENGTH_V1'
        with self.assertRaisesRegex(StudioError, 'generator version'):
            verify_guide_policy(compiled, profile, geometry, ref, data, old_mode, guides)


if __name__ == '__main__':
    unittest.main()
