"""Mandatory attachment material controls survive sampling and native transport.

The triangulation double below is an exact deterministic convex fan. It tests
the native adapter and restoration contract, not Blender CDT qualification.
"""
import copy
import math
import unittest
from unittest.mock import patch

from a3d.core import StudioError, digest
from a3d.pattern_preparation import prepare_regular_boundaries
from a3d.pattern_assembly import _compile_cage, _cage_point
from a3d.placement_attachments import bind_anatomical_attachments, observe_anatomical_attachments
from a3d.sewing import prepare_boundaries, mandatory_boundary_bindings
from blender.sewing import build_mesh, subset_mesh
from tests.test_boundary_gradation import envelope, binary32
from tests.test_sewing import sources


def fixture(reverse=False):
    _, recipe = sources()
    piece = {'vertices': [[0., 0.], [4., 0.], [4., 4.], [0., 4.]],
        'faces': [[0, 1, 2], [0, 2, 3]],
        'edges': {'bottom': [0, 1], 'right': [1, 2], 'top': [2, 3], 'left': [3, 0]}}
    data = {'component_id': 'garment.coat', 'units': 'cm', 'pieces': {
        'left': copy.deepcopy(piece), 'right': copy.deepcopy(piece)}, 'seams': [{
        'id': 'join', 'piece_a': 'left', 'piece_b': 'right', 'edge_a': 'bottom', 'edge_b': 'bottom',
        'orientation': 'reverse' if reverse else 'forward', 'kind': 'permanent'}]}
    placement = recipe['placements']['front']
    recipe.update(component_id=data['component_id'], seams={'join': {
        'kind': 'permanent', 'ease_b_over_a': 0., 'tolerance_relative': .01}},
        placements={pid: copy.deepcopy(placement) for pid in data['pieces']},
        trial_pieces=list(data['pieces']), pins=[], colliders=[], no_collision_reason='Portable fixture')
    recipe['mesh'].update(spacing_cm=2., max_vertices=1000, min_edge_cm=.001,
        max_boundary_error_cm=.01, quality_refinement={
            'max_passes': 8, 'max_added_vertices': 4000, 'target_min_angle_degrees': 15.})
    regular = {'spacing_cm': 2., 'min_spacing_cm': 2., 'refinement_distance_cm': 1.,
               'max_vertices': 1000, 'target_min_angle_degrees': 15.}
    return data, recipe, regular


def constraints(*points):
    return [{'piece': 'left', 'source_uv_cm': list(point), 'target_world_cm': [point[0], point[1], .2],
             'tolerance_cm': 1e-7, 'source_ref': 'fixture:accepted-body-path'} for point in points]


def fan(boundary, recipe, regular=None):
    polygon = copy.deepcopy(boundary['polygon'])
    center = [sum(p[k] for p in polygon)/len(polygon) for k in range(2)]
    vertices = polygon+[center]; n = len(polygon)
    faces = [[i, (i+1) % n, n] for i in range(n)]
    if boundary['flip']:
        faces = [face[::-1] for face in faces]
    boundary['preparation_refinement'] = {'method': 'PORTABLE_EXACT_FAN_FIXTURE_ONLY'}
    return vertices, faces, {i: i for i in range(n)}


class MandatoryAnatomicalMeshControls(unittest.TestCase):
    def test_mid_edge_missing_from_baseline_is_inserted_and_propagated_to_seam_partner(self):
        for reverse in (False, True):
            data, recipe, regular = fixture(reverse)
            original = digest([data, recipe, regular])
            old, _, _ = prepare_regular_boundaries(data, recipe, regular)
            self.assertNotIn([1., 0.], old['left']['polygon'])
            parts, seams, report = prepare_regular_boundaries(data, recipe, regular,
                                                            anatomical_attachments=constraints([1., 0.]))
            self.assertIn([1., 0.], parts['left']['polygon'])
            expected = [3., 0.] if reverse else [1., 0.]
            self.assertIn(expected, parts['right']['polygon'])
            seam = seams['join']; index = seam['parameters'].index(.25)
            self.assertEqual(parts['left']['polygon'][seam['a'][index]], [1., 0.])
            self.assertEqual(parts['right']['polygon'][seam['b'][index]], expected)
            self.assertEqual(len(report['mandatory_anatomical_boundary_bindings']), 1)
            self.assertEqual(digest([data, recipe, regular]), original)

    def test_unsewn_edge_mandatory_uv_survives_regular_pruning_and_graded_resampling(self):
        data, recipe, regular = fixture()
        required = constraints([1., 0.], [1., 4.])
        before = digest([data, recipe, regular, required])
        parts, seams, report = prepare_regular_boundaries(data, recipe, regular,
            anatomical_attachments=required, meshing_envelope=envelope(data), transport_2d=binary32)
        self.assertIn([1., 0.], parts['left']['polygon'])
        self.assertIn([1., 4.], parts['left']['polygon'])
        self.assertEqual(parts['left']['mandatory_source_uv_cm'], [[1., 0.], [1., 4.]])
        self.assertEqual(report['source_boundary_gradation']['qualification'], 'NONE')
        self.assertTrue(all(row['numeric_source_residual_cm'] == 0. for row in report['mandatory_anatomical_boundary_bindings']))
        # The independently exposed grader must also retain the metadata.
        from a3d.boundary_gradation import grade_shared_boundaries
        again, _, _ = grade_shared_boundaries(data, recipe, regular, parts, seams,
                                             transport_2d=binary32, envelope=envelope(data))
        self.assertEqual(again['left']['mandatory_source_uv_cm'], [[1., 0.], [1., 4.]])
        self.assertIn([1., 4.], again['left']['polygon'])
        self.assertEqual(digest([data, recipe, regular, required]), before)

    def test_interior_point_and_boundary_key_alias_are_explicit_refusals(self):
        data, recipe, regular = fixture()
        with self.assertRaisesRegex(StudioError, 'interior insertion is unsupported'):
            prepare_regular_boundaries(data, recipe, regular, anatomical_attachments=constraints([1., 1.]))
        with self.assertRaises(StudioError):
            prepare_regular_boundaries(data, recipe, regular,
                anatomical_attachments=constraints([1., 0.], [1.000000001, 0.]))
        with self.assertRaises(StudioError):
            prepare_regular_boundaries(data, recipe, regular,
                anatomical_attachments=constraints([math.nan, 0.]))

    def test_native_mesh_adapter_keeps_material_control_and_curved_target_vertex(self):
        data, recipe, regular = fixture()
        required = constraints([1., 0.])
        # Preserve quality checks: the mock fan has angles exceeding 15 degrees.
        with patch('blender.sewing.triangulate', side_effect=fan), patch(
                'blender.sewing.placed_point', side_effect=lambda uv, _: [uv[0], uv[1], 0.]):
            previous = build_mesh(data, recipe, regular)
            payload = build_mesh(data, recipe, regular, anatomical_attachments=required)
        binding = payload['mandatory_anatomical_boundary_bindings'][0]
        index = binding['native_vertex']
        self.assertEqual(payload['rest_cm'][index][:2], [1., 0.])
        # Evaluate every native UV with the same real five-control guide.
        # Without the mandatory control, even exact guide vertex samples leave
        # the material anchor reconstructed on the wrong native chord.
        uv = [[0., 0.], [1., 0.], [4., 0.], [4., 4.], [0., 4.]]
        guide = {'uv_cm': uv, 'target_cm': [[u, v, .2 if i == 1 else -.8]
                 for i, (u, v) in enumerate(uv)],
                 'triangles': [[0, 1, 4], [1, 3, 4], [1, 2, 3]]}
        compiled = _compile_cage(guide, 'left')
        def place(mesh):
            return [_cage_point(guide, compiled, point[:2], 'left')[0] for point in mesh['rest_cm']]
        with self.assertRaisesRegex(StudioError, 'initial placement does not satisfy'):
            bind_anatomical_attachments(previous, place(previous), required)
        placed = place(payload)
        self.assertEqual(placed[index][2], .2)
        bound = bind_anatomical_attachments(payload, placed, required)
        observed = observe_anatomical_attachments(bound, placed)
        self.assertTrue(observed['preserved'])
        self.assertEqual(observed['status'], 'ANATOMICAL_ATTACHMENTS_PRESERVED')
        self.assertEqual(payload['anatomical_attachments_sha256'], digest(required))
        subset = subset_mesh(payload, ['left'])
        self.assertEqual(subset['rest_cm'][subset['mandatory_anatomical_boundary_bindings'][0]['native_vertex']][:2], [1., 0.])

    def test_deadline_expires_during_inverse_validation_before_sampling(self):
        data, recipe, regular = fixture()
        required = constraints(*[[i/32., 0.] for i in range(128)])
        before = digest([data, recipe, regular, required])
        calls = [0]
        env = envelope(data, clock=lambda: calls[0], max_seconds=12.)
        actual_distance = math.dist
        def measured_distance(a, b):
            calls[0] += 1
            return actual_distance(a, b)
        with patch('a3d.sewing.math.dist', side_effect=measured_distance), \
                self.assertRaises(StudioError) as raised:
            prepare_regular_boundaries(data, recipe, regular, anatomical_attachments=required,
                                       meshing_envelope=env, transport_2d=binary32)
        self.assertEqual(raised.exception.reason, 'DEADLINE_EXHAUSTED')
        self.assertGreater(env._counts['work_steps'], 0)
        self.assertEqual(env._counts['sampling_calls'], 0)
        self.assertEqual(digest([data, recipe, regular, required]), before)

    def test_inverse_validation_debits_work_and_honors_stop_before_sampling(self):
        data, recipe, regular = fixture()
        required = constraints(*[[i/32., 0.] for i in range(128)])
        for reason in ('BUDGET_EXHAUSTED', 'STOP_REQUESTED'):
            with self.subTest(reason=reason):
                env = envelope(data, {'work_steps': 350} if reason == 'BUDGET_EXHAUSTED' else {})
                if reason == 'STOP_REQUESTED':
                    env.stop_requested = lambda: env._counts['work_steps'] >= 350
                with self.assertRaises(StudioError) as raised:
                    prepare_regular_boundaries(data, recipe, regular, anatomical_attachments=required,
                                               meshing_envelope=env, transport_2d=binary32)
                self.assertEqual(raised.exception.reason, reason)
                self.assertGreater(env._counts['work_steps'], 0)
                self.assertEqual(env._counts['sampling_calls'], 0)

    def test_native_triangulator_cannot_move_mandatory_source_control_silently(self):
        data, recipe, regular = fixture()
        def moved(*args):
            vertices, faces, mapping = fan(*args)
            vertices[vertices.index([1., 0.])][0] += .01
            return vertices, faces, mapping
        with patch('blender.sewing.triangulate', side_effect=moved), patch(
                'blender.sewing.placed_point', side_effect=lambda uv, _: [uv[0], uv[1], 0.]):
            with self.assertRaisesRegex(StudioError, 'moved a mandatory'):
                build_mesh(data, recipe, regular, anatomical_attachments=constraints([1., 0.]))


if __name__ == '__main__':
    unittest.main()
