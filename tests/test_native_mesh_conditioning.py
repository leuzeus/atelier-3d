"""Portable candidate-sequencing regressions; these mocks are not native CDT proof."""
import copy
import math
import struct
import sys
import types
import unittest
from unittest import mock

from a3d.core import StudioError, digest
from a3d.cloth_metrics import triangle_metrics
from a3d.mesh_refinement import improve_interior
from a3d.sewing import signed_area
from blender.sewing import triangulate


class Vector2:
    """Only the float32 vector operations used by this native wrapper."""
    def __init__(self, values):
        self.values = [struct.unpack('f', struct.pack('f', v))[0] for v in values]
    @property
    def x(self): return self.values[0]
    @property
    def y(self): return self.values[1]
    @property
    def length_squared(self): return self.x * self.x + self.y * self.y
    def __len__(self): return len(self.values)
    def __getitem__(self, index): return self.values[index]
    def __iter__(self): return iter(self.values)
    def __add__(self, other): return Vector2([a + b for a, b in zip(self, other)])
    def __sub__(self, other): return Vector2([a - b for a, b in zip(self, other)])
    def __mul__(self, factor): return Vector2([v * factor for v in self])
    def __truediv__(self, factor): return Vector2([v / factor for v in self])
    def __neg__(self): return Vector2([-v for v in self])
    def __eq__(self, other): return list(self) == list(other)
    def dot(self, other): return sum(a * b for a, b in zip(self, other))


def fixture(*, max_passes=8, max_added=4000):
    polygon = [[0., 0.], [1., 0.], [1., 1.], [0., 1.]]
    boundary = {'polygon': copy.deepcopy(polygon), 'source': copy.deepcopy(polygon), 'flip': False}
    recipe = {'mesh': {'spacing_cm': 1., 'max_vertices': 100, 'min_angle_degrees': 2.,
                      'min_edge_cm': .001,
                      'quality_refinement': {'target_min_angle_degrees': 15.,
                                             'max_passes': max_passes, 'max_added_vertices': max_added}}}
    regular = {'spacing_cm': 2., 'min_spacing_cm': 1., 'refinement_distance_cm': 4.,
               'max_vertices': 100, 'target_min_angle_degrees': 15.}
    return boundary, recipe, regular


def native_result(polygon, apex, origins=None):
    points = [Vector2(p) for p in polygon] + [Vector2(apex)]
    faces = [[0, 1, 4], [1, 2, 4], [2, 3, 4], [3, 0, 4]]
    return points, [], faces, origins or [[0], [1], [2], [3], [4]], [], []


def mocked_conditioner(apices):
    calls = []
    def condition(vertices, faces, anchors, **settings):
        result = copy.deepcopy(vertices)
        target = apices[len(calls)]
        if target is not None: result[4] = target
        calls.append({'vertices': copy.deepcopy(vertices), 'faces': copy.deepcopy(faces),
                      'anchors': set(anchors), 'settings': settings})
        assert all(result[i] == vertices[i] for i in anchors)
        assert max(math.dist(a, b) for a, b in zip(vertices, result)) <= settings['max_displacement']
        angles = [triangle_metrics([result[i] for i in f])['min_angle_degrees'] for f in faces]
        return result, {'algorithm': 'TEST_STUB_SEQUENCE_ONLY', 'target_reached': min(angles) >= settings['target_angle'],
                        'min_angle_after_degrees': min(angles)}
    return condition, calls


class NativeMeshConditioningSequence(unittest.TestCase):
    def environment(self, outputs):
        module = types.ModuleType('mathutils'); module.Vector = Vector2
        geometry = types.ModuleType('mathutils.geometry')
        geometry.delaunay_2d_cdt = mock.Mock(side_effect=outputs)
        return mock.patch.dict(sys.modules, {'mathutils': module, 'mathutils.geometry': geometry}), geometry.delaunay_2d_cdt

    def run_regular(self, boundary, recipe, regular, outputs, conditioner):
        environment, cdt = self.environment(outputs)
        with environment, mock.patch('a3d.pattern_preparation.regular_interior_points', return_value=([[.2, .2]], {})), \
                mock.patch('a3d.mesh_refinement.improve_interior', side_effect=conditioner):
            result = triangulate(boundary, recipe, regular)
        return result, cdt

    def test_raw_worse_cdt_candidate_is_conditioned_before_comparison(self):
        boundary, recipe, regular = fixture()
        original = copy.deepcopy((boundary['polygon'], boundary['source'], recipe, regular))
        smoother, calls = mocked_conditioner([None, [.35, .35]])
        result, cdt = self.run_regular(boundary, recipe, regular,
            [native_result(boundary['polygon'], [.2, .2]), native_result(boundary['polygon'], [.05, .05])], smoother)
        coordinates, faces, mapping = result
        report = boundary['preparation_refinement']
        history = report['conditioning_history']
        self.assertEqual(cdt.call_count, 2)
        self.assertEqual(len(calls), 2)
        self.assertLess(history[1]['raw_cdt_min_angle_degrees'], history[0]['raw_cdt_min_angle_degrees'])
        self.assertGreater(history[1]['conditioned_min_angle_degrees'], history[0]['conditioned_min_angle_degrees'])
        self.assertEqual(report['status'], 'TARGET_REACHED')
        self.assertIsNone(report['rejected_candidate'])
        self.assertGreaterEqual(min(triangle_metrics([coordinates[i] for i in f])['min_angle_degrees'] for f in faces), 15.)
        self.assertEqual([coordinates[mapping[i]] for i in range(4)], boundary['polygon'])
        self.assertEqual((boundary['polygon'], boundary['source'], recipe, regular), original)
        self.assertEqual(calls[1]['settings']['max_displacement'], .5)

    def test_conditioned_worse_candidate_rolls_back_exactly_with_failure_evidence(self):
        boundary, recipe, regular = fixture()
        smoother, calls = mocked_conditioner([None, [.15, .15]])
        result, _ = self.run_regular(boundary, recipe, regular,
            [native_result(boundary['polygon'], [.2, .2]), native_result(boundary['polygon'], [.05, .05])], smoother)
        report = boundary['preparation_refinement']
        self.assertEqual(len(calls), 2)
        self.assertEqual(result[0][4], list(Vector2([.2, .2])))
        self.assertEqual(report['status'], 'NEEDS_CORRECTION')
        self.assertEqual(report['refusal'], 'NON_MONOTONIC_REFINEMENT_ROLLED_BACK')
        self.assertEqual(report['conditioning_history'][-1]['decision'], 'ROLLED_BACK_AFTER_CONDITIONING')
        self.assertGreater(report['rejected_candidate']['conditioned_min_angle_degrees'],
                           report['rejected_candidate']['raw_cdt_min_angle_degrees'])
        self.assertEqual(report['passes'], 0)

    def test_cdt_and_added_vertex_budgets_are_not_extended(self):
        for max_passes, max_added, refusal in [(0, 4000, 'PASS_BUDGET_EXHAUSTED'),
                                               (8, 0, 'VERTEX_BUDGET_EXHAUSTED')]:
            boundary, recipe, regular = fixture(max_passes=max_passes, max_added=max_added)
            smoother, calls = mocked_conditioner([None])
            _, cdt = self.run_regular(boundary, recipe, regular,
                [native_result(boundary['polygon'], [.2, .2])], smoother)
            with self.subTest(refusal=refusal):
                self.assertEqual(cdt.call_count, 1)
                self.assertEqual(len(calls), 1)
                self.assertEqual(boundary['preparation_refinement']['refusal'], refusal)
                self.assertEqual(boundary['preparation_refinement']['added_vertices'], 0)

    def test_real_portable_smoothing_preserves_area_winding_and_source_anchors(self):
        boundary, recipe, regular = fixture()
        original = digest([boundary, recipe, regular])
        (coordinates, faces, mapping), _ = self.run_regular(boundary, recipe, regular,
            [native_result(boundary['polygon'], [.2, .2])], improve_interior)
        self.assertEqual(boundary['preparation_refinement']['status'], 'TARGET_REACHED')
        self.assertEqual([coordinates[mapping[i]] for i in range(4)], boundary['polygon'])
        self.assertAlmostEqual(sum(signed_area([coordinates[i] for i in f]) for f in faces), 1., places=12)
        self.assertTrue(all(signed_area([coordinates[i] for i in f]) > 0 for f in faces))
        self.assertLessEqual(math.dist(coordinates[4], list(Vector2([.2, .2]))), .5)
        self.assertEqual(digest([{k: v for k, v in boundary.items() if k != 'preparation_refinement'}, recipe, regular]), original)

    def test_exact_returned_source_quality_cannot_be_granted_by_smoothing_claim(self):
        boundary, recipe, regular = fixture()
        boundary['polygon'] = [[0., 0.], [.0001, 0.], [0., .0001]]
        boundary['source'] = copy.deepcopy(boundary['polygon'])
        points = [Vector2(p) for p in boundary['polygon']]
        output = (points, [], [[0, 1, 2]], [[0], [1], [2]], [], [])
        def claim(vertices, *_args, **_settings):
            return vertices, {'target_reached': True, 'algorithm': 'FALSE_CLAIM_TEST'}
        (_, _, mapping), _ = self.run_regular(boundary, recipe, regular, [output], claim)
        report = boundary['preparation_refinement']
        self.assertEqual(report['status'], 'NEEDS_CORRECTION')
        self.assertLess(report['min_edge_cm'], .001)
        self.assertTrue(report['interior_smoothing']['target_reached'])
        self.assertEqual(set(mapping), {0, 1, 2})

    def test_source_restoration_remains_exact_and_legacy_does_not_invoke_smoothing(self):
        boundary, recipe, _ = fixture()
        boundary['polygon'] = [[.1, .1], [1.1, .1], [1.1, 1.1], [.1, 1.1]]
        boundary['source'] = copy.deepcopy(boundary['polygon'])
        recipe['mesh'].pop('quality_refinement')
        output = ([Vector2(p) for p in boundary['polygon']], [], [[0, 1, 2], [0, 2, 3]], [[0], [1], [2], [3]], [], [])
        environment, _ = self.environment([output])
        with environment, mock.patch('a3d.mesh_refinement.improve_interior') as smoother:
            coordinates, _, mapping = triangulate(boundary, recipe)
        smoother.assert_not_called()
        self.assertEqual([coordinates[mapping[i]] for i in range(4)], boundary['polygon'])
        self.assertNotIn('preparation_refinement', boundary)

    def test_boundary_collapse_and_restoration_inversion_still_refuse(self):
        for issue in ('collapsed_anchor', 'restoration_inverts'):
            boundary, recipe, regular = fixture()
            output = native_result(boundary['polygon'], [.2, .2])
            if issue == 'collapsed_anchor': output = (*output[:3], [[0, 1], [2], [3], [], []], *output[4:])
            else:
                boundary['polygon'] = [[.00005, .00005], [.00006, 0.], [0., .00006]]
                boundary['source'] = copy.deepcopy(boundary['polygon'])
                output = ([Vector2([0., 0.]), Vector2([.00006, 0.]), Vector2([0., .00006])],
                          [], [[0, 1, 2]], [[0], [1], [2]], [], [])
            def unchanged(vertices, *_args, **_settings): return vertices, {'target_reached': False}
            with self.subTest(issue=issue), self.assertRaises(StudioError):
                self.run_regular(boundary, recipe, regular, [output], unchanged)


if __name__ == '__main__': unittest.main()
