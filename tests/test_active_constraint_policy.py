"""The public guide policy binds optional active constraints and their code."""
import copy
import unittest
from unittest.mock import patch

from a3d.core import StudioError, digest, sha
from a3d.garment_guide_policy import prepare_guide_policy, reconstruct_guide_policy, verify_guide_policy
from tests.test_garment_guide_policy import coupled_fixture


def fixture():
    compiled, profile, geometry, ref, data, params, recipes = coupled_fixture()
    params['garment.test']['source_seam_coupling'].update(strategy='COUPLED_REST_METRIC_V2',
        relaxation={'max_iterations': 2, 'rigid_iterations': 0,
                    'constraint_projection': 'ACTIVE_PRINCIPAL_CONE_V1'})
    return compiled, profile, geometry, ref, data, params, recipes


class ActiveConstraintPolicy(unittest.TestCase):
    def test_public_roundtrip_preserves_exact_selection_sources_and_unqualified_result(self):
        compiled, profile, geometry, ref, data, params, recipes = fixture()
        before = digest([compiled, profile, geometry, ref, data, params, recipes])
        policy = prepare_guide_policy(compiled, profile, geometry, ref, params, source_seam_recipes=recipes)
        self.assertEqual(policy['version'], 2)
        guides, evidence = reconstruct_guide_policy(compiled, profile, geometry, ref, data, policy,
                                                    source_seam_recipes=recipes)
        relaxation = guides['garment.test']['source_seam_coupling']['relaxation']
        self.assertEqual(relaxation['settings']['constraint_projection'], 'ACTIVE_PRINCIPAL_CONE_V1')
        self.assertEqual(relaxation['qualification'], 'NONE')
        self.assertFalse(relaxation['whole_piece_admission'])
        self.assertEqual(relaxation['constraint_projection']['observed_constraint_policy'],
                         'RETAIN_NONLINEAR_VIOLATIONS_V1')
        verified = verify_guide_policy(compiled, profile, geometry, ref, data, policy, guides,
                                        source_seam_recipes=recipes)
        self.assertEqual(verified['comparison'], 'FULL_UNROUNDED_GUIDE_REPORT_IDENTICAL')
        self.assertFalse(evidence['admissible_for_fit'])
        self.assertEqual(before, digest([compiled, profile, geometry, ref, data, params, recipes]))
        old = copy.deepcopy(policy)
        del old['components']['garment.test']['source_seam_coupling']['relaxation']['constraint_projection']
        with self.assertRaisesRegex(StudioError, 'differ from reconstruction'):
            verify_guide_policy(compiled, profile, geometry, ref, data, old, guides, source_seam_recipes=recipes)

    def test_unsupported_mode_and_user_numeric_projection_tolerance_are_rejected(self):
        compiled, profile, geometry, ref, _, params, recipes = fixture()
        for change in ({'constraint_projection': 'UNKNOWN'}, {'projection_tolerance': 1.},
                       {'constraint_projection': None}, {'constraint_projection': {'mode': 'ACTIVE_PRINCIPAL_CONE_V1'}}):
            selected = copy.deepcopy(params)
            selected['garment.test']['source_seam_coupling']['relaxation'].update(change)
            with self.subTest(change=change), self.assertRaises(StudioError):
                prepare_guide_policy(compiled, profile, geometry, ref, selected, source_seam_recipes=recipes)

    def test_active_constraint_kernel_is_included_in_exact_replay_identity(self):
        compiled, profile, geometry, ref, data, params, recipes = fixture()
        policy = prepare_guide_policy(compiled, profile, geometry, ref, params, source_seam_recipes=recipes)
        self.assertIn('active_metric_constraints', policy['generator_code_sha256'])
        with patch('a3d.garment_guide_policy.sha', side_effect=lambda path:
                   'f'*64 if path.name == 'active_metric_constraints.py' else sha(path)):
            with self.assertRaisesRegex(StudioError, 'generator code is stale'):
                reconstruct_guide_policy(compiled, profile, geometry, ref, data, policy, source_seam_recipes=recipes)

    def test_cage_binding_changes_with_projection_kernel_even_when_targets_do_not(self):
        from tests.test_assembly_relaxation import fixture as assembly_fixture, run
        data, frames, recipe = assembly_fixture()
        options = {'constraint_projection': 'ACTIVE_PRINCIPAL_CONE_V1', 'max_iterations': 2}
        before, report = run(data, frames, recipe, **options)
        with patch('a3d.assembly_relaxation.sha', side_effect=lambda path:
                   'f'*64 if str(path).replace('\\', '/').endswith('/active_metric_constraints.py') else sha(path)):
            after, changed = run(data, frames, recipe, **options)
        self.assertNotEqual(report['source_binding_sha256'], changed['source_binding_sha256'])
        self.assertEqual(report['relaxation']['kernel_code_sha256'], changed['relaxation']['kernel_code_sha256'])
        for pid in before:
            self.assertEqual(before[pid]['target_cm'], after[pid]['target_cm'])
            self.assertNotEqual(before[pid]['source_ref'], after[pid]['source_ref'])

    def test_cage_binding_includes_observed_constraint_policy_even_without_motion(self):
        from tests.test_assembly_relaxation import fixture as assembly_fixture, run
        data, frames, recipe = assembly_fixture()
        options = {'constraint_projection': 'ACTIVE_PRINCIPAL_CONE_V1', 'max_iterations': 2}
        before, report = run(data, frames, recipe, **options)
        with patch('a3d.active_metric_constraints.OBSERVED_CONSTRAINT_POLICY',
                   'DIFFERENT_OBSERVED_CONSTRAINT_POLICY'):
            after, changed = run(data, frames, recipe, **options)
        self.assertNotEqual(report['source_binding_sha256'], changed['source_binding_sha256'])
        for pid in before:
            self.assertEqual(before[pid]['target_cm'], after[pid]['target_cm'])
            self.assertNotEqual(before[pid]['source_ref'], after[pid]['source_ref'])


if __name__ == '__main__':
    unittest.main()
