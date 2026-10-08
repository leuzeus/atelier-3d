import copy
import math
import unittest
from unittest.mock import patch

from a3d.anatomical_placement import validate_anatomical_references
from a3d.core import StudioError, digest
from a3d.garment_guides import (anatomical_band_frame, limb_volume_frames, _world,
    garment_volume_frames, permanent_component_pieces)
from a3d.pattern_assembly import _compile_cage, _cage_point
from a3d.regional_surface_guides import apply_regional_surface_envelopes, _hits
from a3d.contact_geometry import TriangleBVH
from a3d.shoulder_surface import measured_surface_shoulders
from tests.test_anatomical_placement import fixture as path_fixture
from tests.test_garment_guides import limb_fixture
from tests.test_shoulder_surface import fixture as box_fixture
from tests.test_source_seam_coupling import recipe


def band_fixture(rotated=False, axis='u'):
    profile, geometry, report, doc, local = path_fixture(rotated=rotated)
    width = report['paths'][0]['length_cm']
    vertices = [[0., 0.], [width, 0.], [width, 7.], [0., 7.]]
    if axis == 'v':
        vertices = [[v, u] for u, v in vertices]
    piece = {'vertices': vertices, 'faces': [[0, 1, 2], [0, 2, 3]],
             'edges': {'base': [0, 1], 'top': [2, 3]}}
    policy = {'guide_kind': 'PATH_BAND_V1', 'path_ref': 'chosen', 'material_axis': axis,
        'source_anchor_edge': 'base', 'source_anchor_fraction': 0., 'path_anchor_fraction': 0.,
        'longitudinal_direction_body': [0., 0., 1.], 'max_path_expansion_ratio': 1.2}
    doc['pieces'] = {'band': policy}
    return piece, policy, profile, validate_anatomical_references(profile, doc, geometry=geometry)


class MeasuredBandAndLimb(unittest.TestCase):
    def test_dispatcher_explicit_band_owns_belt_role_without_legacy_collision(self):
        piece, policy, _, _ = band_fixture()
        profile, geometry, report, document, _ = path_fixture()
        document['pieces'] = {'band': policy}
        data = {'pieces': {'band': piece}, 'seams': []}
        semantics = {'band': {'role': 'belt', 'side': 'center', 'longitudinal_uv_axis': 'u'}}
        result = garment_volume_frames(data, semantics, profile, anatomical_references=document,
                                       anatomical_geometry={'geometry': geometry})
        self.assertEqual(result['status'], 'GARMENT_GUIDES_PREPARED')
        self.assertEqual(list(result['panels']), ['band'])
        self.assertEqual([row['family'] for row in result['families']], ['specialised'])
        self.assertEqual(result['qualification'], 'NONE')
        regions = {row['region']: row['status'] for row in result['anatomical_region_coverage']['regions']}
        self.assertEqual(regions['neck'], 'MEASURED_REFERENCE_AVAILABLE')
        self.assertEqual(regions['foot.left'], 'MISSING_MEASURED_REFERENCE')

    def test_band_follows_measured_vertical_curve_and_preserves_seven_cm_height(self):
        piece, policy, profile, refs = band_fixture()
        before = digest([piece, policy, profile, refs])
        frame, report = anatomical_band_frame(piece, policy, profile, refs, 'band')
        bottom = {round(u, 9): p for (u, v), p in zip(frame['uv_cm'], frame['target_cm']) if v == 0.}
        top = {round(u, 9): p for (u, v), p in zip(frame['uv_cm'], frame['target_cm']) if v == 7.}
        self.assertGreater(max(p[2] for p in bottom.values())-min(p[2] for p in bottom.values()), .9)
        for u in set(bottom) & set(top):
            self.assertAlmostEqual(math.dist(bottom[u], top[u]), 7., places=10)
        self.assertEqual(bottom[0.], refs['paths']['chosen']['points_world_cm'][0])
        self.assertEqual(report['auxiliary_path_expansion_ratio'], 1.)
        self.assertEqual(report['qualification'], 'NONE')
        self.assertEqual(digest([piece, policy, profile, refs]), before)

    def test_band_material_axis_and_rotated_body_are_covariant(self):
        expected, _ = anatomical_band_frame(*band_fixture(), 'band')
        actual, _ = anatomical_band_frame(*band_fixture(rotated=True), 'band')
        for p, q in zip(expected['target_cm'], actual['target_cm']):
            self.assertLess(math.dist(q, [20+p[2], -7+p[0], 53+p[1]]), 1e-9)
        transposed, _ = anatomical_band_frame(*band_fixture(axis='v'), 'band')
        original = {(round(u, 9), round(v, 9)): p for (u, v), p in zip(expected['uv_cm'], expected['target_cm'])}
        for (v, u), point in zip(transposed['uv_cm'], transposed['target_cm']):
            self.assertLess(math.dist(point, original[round(u, 9), round(v, 9)]), 1e-9)

    def test_undersized_band_refuses_without_stretching_pattern_or_shrinking_body(self):
        piece, policy, profile, refs = band_fixture()
        for point in piece['vertices']:
            point[0] *= .75
        before = digest([piece, policy, profile, refs])
        with self.assertRaisesRegex(StudioError, 'circumference'):
            anatomical_band_frame(piece, policy, profile, refs, 'band')
        self.assertEqual(digest([piece, policy, profile, refs]), before)

    def test_limb_attachment_corrects_axis_skin_difference_rigidly(self):
        data, semantics, profile = limb_fixture()
        original = limb_volume_frames(data, semantics, profile)['panels']['limb']
        # A measured attachment is intentionally separate from the rig centre.
        refs = {'paths': {'skin': {'points_body_cm': [[10., 0., 25.], [10., 2., 25.]],
            'closed': False, 'path_sha256': 'e'*64, 'region': 'upper_arm.right'}}, 'pieces': {'limb': {
            'guide_kind': 'LIMB_ATTACHMENT_V1', 'attachment_path_ref': 'skin', 'path_fraction': .5,
            'source_anchor_edge': 'proximal', 'source_anchor_fraction': .5,
            'axis_landmarks': ['shoulder.right', 'wrist.right'],
            'transverse_direction_body': [0., 1., 0.], 'attachment_offset_body': [0., 0., .3]}}}
        before = digest([data, semantics, profile, refs])
        result = limb_volume_frames(data, semantics, profile, anatomical_references=refs)
        changed = result['panels']['limb']
        anchor = [5., 12.]
        old = _cage_point(original, _compile_cage(original, 'limb'), anchor, 'limb')[0]
        new = _cage_point(changed, _compile_cage(changed, 'limb'), anchor, 'limb')[0]
        self.assertGreater(math.dist(old, [10., 1., 25.3]), 5.)
        self.assertLess(math.dist(new, [10., 1., 25.3]), 1e-9)
        shift = [b-a for a, b in zip(original['target_cm'][0], changed['target_cm'][0])]
        for p, q in zip(original['target_cm'], changed['target_cm']):
            self.assertLess(math.dist(q, [a+b for a, b in zip(p, shift)]), 1e-9)
        self.assertEqual(digest([data, semantics, profile, refs]), before)
        self.assertFalse(result['evidence'][0]['anatomical_attachment']['material_metric_changed_by_attachment'])

    def test_generic_limb_can_use_leg_landmarks_without_shoulders(self):
        data, semantics, profile = limb_fixture()
        profile['landmarks'] = {'hip.right': {'point_cm': [10., 0., 20.]},
                                'ankle.right': {'point_cm': [10., 0., 0.]}}
        semantics['limb']['role'] = 'trouser_panel'
        policy = {'guide_kind': 'LIMB_ATTACHMENT_V1', 'attachment_path_ref': 'skin', 'path_fraction': 0.,
            'source_anchor_edge': 'proximal', 'source_anchor_fraction': .5,
            'axis_landmarks': ['hip.right', 'ankle.right'], 'transverse_direction_body': [0., 1., 0.],
            'attachment_offset_body': [0., 0., 0.]}
        refs = {'paths': {'skin': {'points_body_cm': [[10., 0., 20.], [10., 2., 20.]],
            'closed': False, 'path_sha256': 'e'*64, 'region': 'upper_leg.right'}}, 'pieces': {'limb': policy}}
        result = limb_volume_frames(data, semantics, profile, anatomical_references=refs)
        self.assertEqual(result['pending_pieces'], [])
        self.assertEqual(result['evidence'][0]['anatomical_attachment']['axis_landmarks'], ['hip.right', 'ankle.right'])

    def test_limb_rejects_wrong_side_reference_or_axis_and_accepts_explicit_custom_region(self):
        data, semantics, profile = limb_fixture()
        policy = {'guide_kind': 'LIMB_ATTACHMENT_V1', 'attachment_path_ref': 'skin', 'path_fraction': 0.,
            'source_anchor_edge': 'proximal', 'source_anchor_fraction': .5,
            'axis_landmarks': ['shoulder.right', 'wrist.right'], 'transverse_direction_body': [0., 1., 0.],
            'attachment_offset_body': [0., 0., 0.]}
        refs = {'paths': {'skin': {'points_body_cm': [[10., 0., 20.], [10., 2., 20.]],
            'closed': False, 'path_sha256': 'e'*64, 'region': 'upper_arm.left'}}, 'pieces': {'limb': policy}}
        with self.assertRaisesRegex(StudioError, 'region side'):
            limb_volume_frames(data, semantics, profile, anatomical_references=refs)
        refs['paths']['skin']['region'] = 'upper_arm.right'
        policy['axis_landmarks'][1] = 'wrist.left'
        with self.assertRaisesRegex(StudioError, 'landmark side'):
            limb_volume_frames(data, semantics, profile, anatomical_references=refs)
        policy['axis_landmarks'][1] = 'wrist.right'
        refs['paths']['skin']['region'] = 'custom:measured-attachment'
        self.assertEqual(limb_volume_frames(data, semantics, profile, anatomical_references=refs)['pending_pieces'], [])

    def test_single_band_unary_seam_is_allowed_and_anatomical_attachment_stays_fixed(self):
        piece, policy, _, _ = band_fixture()
        piece['edges'].update(left=[0, 3], right=[1, 2])
        profile, geometry, _, document, _ = path_fixture()
        document['pieces'] = {'band': policy}
        data = {'component_id': 'example.band', 'units': 'cm', 'pieces': {'band': piece},
            'seams': [{'id': 'self', 'kind': 'permanent', 'piece_a': 'band', 'piece_b': 'band',
                       'edge_a': 'left', 'edge_b': 'right', 'orientation': 'forward'}]}
        semantics = {'band': {'role': 'collar', 'side': 'center', 'longitudinal_uv_axis': 'u'}}
        coupling = {'strategy': 'COUPLED_REST_METRIC_V2', 'pieces': ['band'], 'subdivisions': 2, 'budgets': None,
                    'relaxation': {'max_iterations': 2, 'rigid_iterations': 0}}
        result = garment_volume_frames(data, semantics, profile, anatomical_references=document,
            anatomical_geometry={'geometry': geometry}, source_seam_coupling=coupling, seam_recipe=recipe(data))
        self.assertEqual(result['anatomical_attachment_constraints']['violations'], 0)
        self.assertTrue(result['source_seam_coupling']['anatomical_attachments'])
        self.assertEqual(result['source_seam_coupling']['permanent_relation_coverage'], 'COMPLETE_SELECTED_COMPONENT')

        def damaged(*args, **kwargs):
            frames = copy.deepcopy(args[1])
            for point in frames['band']['target_cm']:
                point[0] += 1.
            return frames, {'strategy': 'COUPLED_REST_METRIC_V2', 'status': 'PROPOSAL_TARGETS_REACHED'}
        with patch('a3d.source_seam_coupling.couple_source_seams', side_effect=damaged):
            result = garment_volume_frames(data, semantics, profile, anatomical_references=document,
                anatomical_geometry={'geometry': geometry}, source_seam_coupling=coupling, seam_recipe=recipe(data))
        self.assertEqual(result['status'], 'PARTIAL_GUIDES')
        self.assertGreater(result['anatomical_attachment_constraints']['violations'], 0)
        self.assertIn('FINAL_ANATOMICAL_ATTACHMENT_DRIFT', [row['code'] for row in result['diagnostics']])


def envelope_fixture():
    profile, geometry, triangles = box_fixture()
    profile.update(status='PROFILE_MEASURED', segmentation='EXPLICIT_SOURCE')
    geometry['face_sets'] = [1, 2, 3, 4, 5, 6]
    profile = measured_surface_shoulders(profile, geometry, triangles)
    data = {'pieces': {'patch': {'vertices': [[0., 0.], [5., 0.], [5., 5.], [0., 5.]],
                                'faces': [[0, 1, 2], [0, 2, 3]], 'edges': {}}}}
    frames = {'patch': {'source_ref': 'fixture:source', 'uv_cm': data['pieces']['patch']['vertices'],
        'target_cm': [[-5., 0., 40.], [5., 0., 40.], [5., 0., 50.], [-5., 0., 50.]],
        'triangles': [[0, 1, 2], [0, 2, 3]]}}
    policy = {'method': 'REGIONAL_SURFACE_ENVELOPE_V1', 'source_region_ids': [4],
              'direction_body': [0., -1., 0.], 'reserve_cm': .5, 'max_displacement_cm': 20.}
    return data, frames, profile, {'geometry': geometry, 'triangles': triangles}, {'patch': policy}


class RegionalSurfaceEnvelopes(unittest.TestCase):
    def test_full_chain_detects_seam_solver_erasing_body_reserve(self):
        data, frames, profile, body, policies = envelope_fixture()
        data.update(component_id='example.patch', units='cm', seams=[])
        doc = {'version': 1, 'profile_sha256': digest(profile), 'paths': {}, 'triangles': body['triangles'],
               'pieces': {'patch': {'surface_envelope': policies['patch']}}}
        semantics = {'patch': {'role': 'sleeve', 'side': 'right', 'longitudinal_uv_axis': 'v'}}
        def seed(*args, **kwargs):
            return {'panels': copy.deepcopy(frames)}
        def damaged(*args, **kwargs):
            changed = copy.deepcopy(args[1])
            for point in changed['patch']['target_cm']:
                point[1] -= 2.
            return changed, {'strategy': 'COUPLED_REST_METRIC_V2', 'status': 'PROPOSAL_TARGETS_REACHED'}
        coupling = {'strategy': 'COUPLED_REST_METRIC_V2', 'pieces': ['patch'], 'subdivisions': 2, 'budgets': None}
        with patch('a3d.garment_guides.limb_volume_frames', side_effect=seed), patch(
                'a3d.source_seam_coupling.couple_source_seams', side_effect=damaged):
            result = garment_volume_frames(data, semantics, profile, anatomical_references=doc,
                anatomical_geometry=body, source_seam_coupling=coupling)
        self.assertEqual(result['status'], 'PARTIAL_GUIDES')
        self.assertAlmostEqual(result['post_coupling_surface_reserve']['pieces'][0]['max_displacement_cm'], 2.)
        self.assertIn('FINAL_REGIONAL_SURFACE_RESERVE_NOT_PRESERVED', [row['code'] for row in result['diagnostics']])
        self.assertTrue(all(p[1] == 8.5 for p in result['panels']['patch']['target_cm']))

    def test_actual_upper_surface_penetration_is_removed_without_source_change(self):
        args = envelope_fixture(); before = digest(args)
        result, report = apply_regional_surface_envelopes(*args)
        for point in result['patch']['target_cm']:
            self.assertAlmostEqual(point[1], 10.5)
        self.assertEqual(report['pieces'][0]['moved_controls'], 4)
        self.assertEqual(report['pieces'][0]['unresolved_controls'], 0)
        self.assertEqual(report['qualification'], 'NONE')
        self.assertEqual(result['patch']['uv_cm'], args[1]['patch']['uv_cm'])
        self.assertEqual(result['patch']['triangles'], args[1]['patch']['triangles'])
        self.assertEqual(digest(args), before)
        repeated, repeated_report = apply_regional_surface_envelopes(*args)
        self.assertEqual(result, repeated)
        self.assertEqual(report, repeated_report)

    def test_generic_face_region_selection_applies_to_any_body_direction(self):
        args = list(envelope_fixture())
        args[4]['patch'].update(source_region_ids=[2], direction_body=[0., 0., 1.], max_displacement_cm=70.)
        result, report = apply_regional_surface_envelopes(*args)
        self.assertTrue(all(abs(p[2]-100.5) < 1e-9 for p in result['patch']['target_cm']))
        self.assertEqual(report['pieces'][0]['covered_controls'], 4)

    def test_scope_missing_region_and_budget_remain_explicit_partial(self):
        for update, expected in [({'source_region_ids': [6]}, 'SURFACE_COVERAGE_MISSING'),
                                 ({'max_ray_tests': 1}, 'BUDGET_NOT_EVALUATED'),
                                 ({'max_displacement_cm': 5.}, 'SURFACE_COVERAGE_MISSING')]:
            args = list(envelope_fixture()); args[4]['patch'].update(update)
            result, report = apply_regional_surface_envelopes(*args)
            self.assertEqual(report['status'], 'PARTIAL_SURFACE_ENVELOPES')
            self.assertEqual(report['pieces'][0]['unresolved_samples'][0]['reason'], expected)
            self.assertEqual(report['qualification'], 'NONE')
        args = list(envelope_fixture()); args[4]['patch']['source_v_range_cm'] = [3., 5.]
        result, report = apply_regional_surface_envelopes(*args)
        self.assertEqual(result['patch']['target_cm'][:2], args[1]['patch']['target_cm'][:2])
        self.assertEqual(report['pieces'][0]['outside_declared_scope_controls'], 2)

    def test_changed_body_or_native_triangle_binding_is_refused(self):
        args = list(envelope_fixture()); args[3]['geometry']['vertices_cm'][0][0] += 1
        with self.assertRaisesRegex(StudioError, 'geometry'):
            apply_regional_surface_envelopes(*args)
        args = list(envelope_fixture()); args[3]['triangles'] = args[3]['triangles'][1:]
        with self.assertRaisesRegex(StudioError, 'triangulation'):
            apply_regional_surface_envelopes(*args)

    def test_distinct_exterior_sheets_are_not_silently_selected(self):
        triangles = [[[0., 0., z], [1., 0., z], [0., 1., z]] for z in (1., 3.)]
        hits = _hits([.2, .2, 0.], [0., 0., 1.], triangles, TriangleBVH(triangles), 10., lambda **_: None)
        self.assertEqual([row[0] for row in hits], [1., 3.])


class PermanentSourceScope(unittest.TestCase):
    def test_complete_permanent_graph_includes_sleeve_and_cuff_but_not_detachable(self):
        data = {'pieces': {name: {} for name in ('torso', 'sleeve', 'cuff', 'hood', 'zip')},
                'seams': [{'piece_a': a, 'piece_b': b, 'kind': kind} for a, b, kind in (
                    ('torso', 'sleeve', 'permanent'), ('sleeve', 'cuff', 'permanent'),
                    ('sleeve', 'sleeve', 'permanent'), ('torso', 'hood', 'detachable'),
                    ('torso', 'zip', 'closure'))]}
        self.assertEqual(permanent_component_pieces(data, ['torso']), ['cuff', 'sleeve', 'torso'])
        data['seams'].reverse()
        self.assertEqual(permanent_component_pieces(data, ['cuff']), ['cuff', 'sleeve', 'torso'])

    def test_missing_component_guides_remain_localized_partial_instead_of_skipped_seams(self):
        profile = path_fixture()[0]
        data = {'pieces': {'unmapped-a': {}, 'unmapped-b': {}},
                'seams': [{'id': 'join', 'piece_a': 'unmapped-a', 'piece_b': 'unmapped-b', 'kind': 'permanent'}]}
        semantics = {pid: {'role': 'undeclared_family'} for pid in data['pieces']}
        report = garment_volume_frames(data, semantics, profile, source_seam_coupling={
            'pieces': ['unmapped-a'], 'piece_scope': 'PERMANENT_COMPONENT', 'strategy': 'COUPLED_REST_METRIC_V2'})
        self.assertEqual(report['status'], 'PARTIAL_GUIDES')
        self.assertEqual(report['pending_pieces'], ['unmapped-a', 'unmapped-b'])
        self.assertEqual(report['source_seam_coupling']['status'], 'NOT_EXECUTED_MISSING_COMPONENT_GUIDES')


if __name__ == '__main__':
    unittest.main()
