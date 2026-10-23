"""Guide observations describe bounded interpolation; they admit no garment."""
import copy
import json
import math
import unittest
from unittest.mock import patch

from a3d import cloth_metrics
from a3d.core import StudioError, digest
from a3d.guide_stage_metrics import STAGES, observe_guide_stages
from a3d.source_seam_coupling import _Budget, couple_source_seams
from tests.test_source_seam_coupling import two_piece_fixture


def fixture():
    states = {'textile': {'uv': [[0., 0.], [2., 0.], [0., 1.]],
        'triangles': [[0, 1, 2]], 'triangle_source_faces': [4]}}
    points = [[u, v, 0.] for u, v in states['textile']['uv']]
    coordinates = {stage: {'textile': copy.deepcopy(points)} for stage in STAGES}
    return states, coordinates


def observe(states, coordinates, **kwargs):
    return observe_guide_stages(states, coordinates, _Budget(None, lambda: 0.),
                                provenance={'source_ref': 'immutable-fixture'}, **kwargs)


class GuideStageMetrics(unittest.TestCase):
    def test_rigid_rotation_translation_and_normal_reversal_preserve_source_metric(self):
        states, coordinates = fixture()
        coordinates['role_rigid_seed']['textile'] = [[3., 7.+u, 9.+v] for u, v in states['textile']['uv']]
        coordinates['seam_cohort_mean']['textile'] = [[3.+u, 7.-v, 9.] for u, v in states['textile']['uv']]
        before = digest([states, coordinates])
        with patch.object(cloth_metrics, 'principal_stretches', wraps=cloth_metrics.principal_stretches) as kernel:
            report = observe(states, coordinates)
        self.assertEqual(kernel.call_count, 3)
        for stage in STAGES:
            row = report['per_piece']['textile']['stages'][stage]
            self.assertEqual(row['extrema']['min_principal_stretch']['value'], 1.)
            self.assertEqual(row['extrema']['max_principal_stretch']['value'], 1.)
            self.assertEqual(row['extrema']['max_principal_engineering_strain']['value'], 0.)
            self.assertEqual(row['degenerate_triangle_count'], 0)
            self.assertEqual(row['degenerate_triangle_witnesses'], [])
            self.assertEqual(row['evaluated_triangle_count'], 1)
            self.assertEqual(row['extrema']['max_principal_stretch']['source_face_index'], 4)
        self.assertEqual(digest([states, coordinates]), before)
        self.assertEqual(report['scope'], 'GUIDE_CAGE_INTERPOLATION_DIAGNOSTIC_ONLY')
        self.assertEqual(report['qualification'], 'NONE')
        self.assertEqual(report['regular_mesh_assessment'], 'NOT_EXECUTED')
        self.assertEqual(report['fitting'], 'NOT_EXECUTED')

    def test_seam_mean_deformation_is_visible_and_opt_in_leaves_cages_and_prior_report_unchanged(self):
        data, frames, recipe = two_piece_fixture()
        before = digest([data, frames, recipe])
        old_cages, old_report = couple_source_seams(data, frames, recipe, subdivisions=3)
        cages, report = couple_source_seams(data, frames, recipe, subdivisions=3, observe_guide_stages=True)
        self.assertEqual(cages, old_cages)
        diagnostics = report.pop('guide_stage_metrics')
        self.assertEqual(report, old_report)
        self.assertEqual(digest([data, frames, recipe]), before)
        self.assertFalse(diagnostics['provenance']['rigid_seed_applied'])
        deformed = False
        for pid, row in diagnostics['per_piece'].items():
            original = row['stages']['original_guide']
            seeded = row['stages']['role_rigid_seed']
            self.assertEqual(original, seeded)
            final = row['stages']['seam_cohort_mean']
            for record in final['extrema'].values():
                self.assertEqual(record['source_uv_cm'], [cages[pid]['uv_cm'][i] for i in record['cage_control_indices']])
                self.assertEqual(record['source_face_index'], report['refinements'][pid]['triangle_source_face_indices'][record['cage_triangle_index']])
            deformed |= abs(final['extrema']['max_principal_stretch']['value']-original['extrema']['max_principal_stretch']['value']) > 1e-5
            self.assertEqual(final['coordinate_sha256'], digest(cages[pid]['target_cm']))
        self.assertTrue(deformed)
        with self.assertRaisesRegex(StudioError, 'explicitly boolean'):
            couple_source_seams(data, frames, recipe, observe_guide_stages=1)

    def test_three_stages_compare_material_uv_even_when_seed_moves_a_stretched_guide(self):
        states, coordinates = fixture()
        coordinates['original_guide']['textile'] = [[2*u, v, 0.] for u, v in states['textile']['uv']]
        coordinates['role_rigid_seed']['textile'] = [[5., 3.+2*u, 7.+v] for u, v in states['textile']['uv']]
        coordinates['seam_cohort_mean']['textile'][1][0] = 3.
        report = observe(states, coordinates)['per_piece']['textile']['stages']
        self.assertEqual(report['original_guide']['extrema']['max_principal_stretch']['value'], 2.)
        self.assertEqual(report['role_rigid_seed']['extrema']['max_principal_stretch']['value'], 2.)
        self.assertEqual(report['seam_cohort_mean']['extrema']['max_principal_stretch']['value'], 1.5)

    def test_actual_role_seed_is_observed_without_changing_coupling_and_retains_provenance(self):
        from tests.test_rigid_guide_alignment import fixture as rigid_fixture
        data, frames, recipe, semantics = rigid_fixture()
        before = digest([data, frames, recipe, semantics])
        expected_cages, expected_report = couple_source_seams(data, frames, recipe, semantics=semantics,
                                                            subdivisions=3, clock=lambda: 0.)
        cages, report = couple_source_seams(data, frames, recipe, semantics=semantics,
            subdivisions=3, clock=lambda: 0., observe_guide_stages=True)
        metrics = report.pop('guide_stage_metrics')
        self.assertEqual((cages, report), (expected_cages, expected_report))
        self.assertEqual(digest([data, frames, recipe, semantics]), before)
        self.assertTrue(metrics['provenance']['rigid_seed_applied'])
        self.assertEqual(metrics['provenance']['rigid_alignment_kernel_code_sha256'],
                         report['rigid_alignment']['kernel_code_sha256'])
        stages = metrics['per_piece']['mobile']['stages']
        self.assertNotEqual(stages['original_guide']['coordinate_sha256'], stages['role_rigid_seed']['coordinate_sha256'])
        for stage in STAGES:
            self.assertEqual(stages[stage]['principal_measurement_count'], 18)
            self.assertAlmostEqual(stages[stage]['extrema']['min_principal_stretch']['value'], 1., places=12)
            self.assertAlmostEqual(stages[stage]['extrema']['max_principal_stretch']['value'], 1., places=12)

    def test_reports_are_deterministic_with_piece_order_and_do_not_mutate_uv_or_topology(self):
        states, coordinates = fixture()
        states['lining'] = copy.deepcopy(states['textile'])
        for stage in STAGES:
            coordinates[stage]['lining'] = copy.deepcopy(coordinates[stage]['textile'])
        before = digest([states, coordinates])
        first = observe(states, coordinates)
        second = observe(dict(reversed(list(states.items()))),
            {stage: dict(reversed(list(coordinates[stage].items()))) for stage in reversed(STAGES)})
        self.assertEqual(first, second)
        self.assertEqual(list(first['per_piece']), ['lining', 'textile'])
        self.assertEqual(digest([states, coordinates]), before)
        json.dumps(first, allow_nan=False)

    def test_singular_source_and_collapsed_target_are_finite_diagnostics_without_admission(self):
        states, coordinates = fixture()
        states['textile']['uv'][2] = [1., 0.]
        report = observe(states, coordinates)
        for stage in STAGES:
            row = report['per_piece']['textile']['stages'][stage]
            record = row['degenerate_triangle_witnesses'][0]
            self.assertTrue(record['source_degenerate'])
            self.assertEqual(record['principal_measurement'], 'SOURCE_SINGULAR')
            self.assertIsNone(record['principal_stretch'])
            self.assertNotIn('max_principal_stretch', row['extrema'])
            self.assertEqual(row['degenerate_triangle_count'], 1)
            self.assertEqual(row['principal_measurement_count'], 0)
            self.assertEqual(row['source_singular_triangle_count'], 1)
            self.assertEqual(row['degenerate_triangle_witnesses'][0]['cage_triangle_index'], 0)
        json.dumps(report, allow_nan=False)
        states, coordinates = fixture()
        coordinates['seam_cohort_mean']['textile'][2] = [1., 0., 0.]
        row = observe(states, coordinates)['per_piece']['textile']['stages']['seam_cohort_mean']
        self.assertTrue(row['degenerate_triangle_witnesses'][0]['placed_degenerate'])
        self.assertEqual(row['extrema']['min_principal_stretch']['value'], 0.)
        self.assertEqual(row['qualification'], 'NONE')

    def test_source_cage_sliver_angle_never_becomes_a_physical_mesh_gate(self):
        states, coordinates = fixture()
        states['textile']['uv'][2] = [1., .0001]
        for stage in STAGES:
            coordinates[stage]['textile'] = [[u, v, 0.] for u, v in states['textile']['uv']]
        report = observe(states, coordinates)
        self.assertLess(report['per_piece']['textile']['stages']['original_guide']['extrema']['min_source_angle_degrees']['value'], .01)
        self.assertEqual(report['source_angle_scope'], 'CAGE_CONDITIONING_NOT_PHYSICAL_REST_MESH_ADMISSION')
        self.assertEqual(report['qualification'], 'NONE')

    def test_every_triangle_is_measured_but_degenerate_output_witnesses_are_bounded_to_32(self):
        states, coordinates = fixture()
        states['textile']['uv'][2] = [1., 0.]
        states['textile']['triangles'] *= 50
        states['textile']['triangle_source_faces'] *= 50
        before = digest([states, coordinates])
        with patch.object(cloth_metrics, 'principal_stretches', wraps=cloth_metrics.principal_stretches) as kernel:
            report = observe(states, coordinates)
        self.assertEqual(kernel.call_count, 150)
        self.assertEqual(report['degenerate_witness_limit_per_piece_stage'], 32)
        for row in report['per_piece']['textile']['stages'].values():
            self.assertEqual(row['evaluated_triangle_count'], 50)
            self.assertEqual(row['degenerate_triangle_count'], 50)
            self.assertEqual(row['source_singular_triangle_count'], 50)
            self.assertEqual(len(row['degenerate_triangle_witnesses']), 32)
            self.assertEqual([w['cage_triangle_index'] for w in row['degenerate_triangle_witnesses']], list(range(32)))
            self.assertTrue(row['degenerate_witnesses_truncated'])
            self.assertNotIn('triangle_metrics', row)
            self.assertNotIn('degenerate_cage_triangle_indices', row)
            self.assertEqual(row['extrema']['min_source_angle_degrees']['cage_triangle_index'], 0)
        self.assertEqual(report, observe(states, coordinates))
        self.assertEqual(digest([states, coordinates]), before)

    def test_incomplete_invalid_and_nonfinite_arithmetic_are_domain_refusals(self):
        for variant in ('stage', 'piece', 'control', 'uv', 'source_face', 'triangle', 'boolean', 'overflow'):
            states, coordinates = fixture()
            if variant == 'stage': del coordinates['role_rigid_seed']
            elif variant == 'piece': coordinates['seam_cohort_mean'] = {}
            elif variant == 'control': coordinates['seam_cohort_mean']['textile'].pop()
            elif variant == 'uv': states['textile']['uv'][0][0] = math.inf
            elif variant == 'source_face': states['textile']['triangle_source_faces'] = []
            elif variant == 'triangle': states['textile']['triangles'][0][0] = []
            elif variant == 'boolean': coordinates['original_guide']['textile'][0][0] = True
            else: coordinates['seam_cohort_mean']['textile'][1][0] = 1e308
            before = copy.deepcopy([states, coordinates])
            with self.subTest(variant=variant), self.assertRaises(StudioError):
                observe(states, coordinates)
            self.assertEqual([states, coordinates], before)

    def test_existing_control_triangle_and_monotonic_deadline_budgets_bound_observations(self):
        states, coordinates = fixture()
        for limits in ({'max_controls': 2}, {'max_triangles': 1}):
            bound_states, bound_coordinates = copy.deepcopy(states), copy.deepcopy(coordinates)
            if 'max_triangles' in limits:
                bound_states['textile']['triangles'] *= 2
                bound_states['textile']['triangle_source_faces'] *= 2
            with self.subTest(limits=limits), self.assertRaisesRegex(StudioError, 'budget'):
                observe_guide_stages(bound_states, bound_coordinates, _Budget(limits, lambda: 0.), provenance={})
        current = [0.]
        budget = _Budget({'max_seconds': 1.}, lambda: current[0])
        with patch('a3d.guide_stage_metrics.cloth_metrics.principal_stretches', side_effect=lambda *args: (current.__setitem__(0, 2.) or [1., 1.])):
            with self.assertRaisesRegex(StudioError, 'time budget'):
                observe_guide_stages(states, coordinates, budget, provenance={})
        self.assertEqual((budget.controls, budget.triangles), (0, 0))
        ticks = iter((1., 0.))
        with self.assertRaisesRegex(StudioError, 'clock reversed'):
            observe_guide_stages(states, coordinates, _Budget(None, lambda: next(ticks)), provenance={})


if __name__ == '__main__':
    unittest.main()
