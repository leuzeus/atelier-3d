"""Generic measured-reference placement, including non-arm anatomy."""
import copy
import math
import unittest

from a3d.anatomical_placement import (STANDARD_REGIONS, path_frames, region_coverage,
    resolve_measured_path, sample_path, validate_anatomical_references)
from a3d.core import StudioError, digest


def fixture(*, closed=True, rotated=False, region='neck'):
    basis = {'right': [1., 0., 0.], 'forward': [0., 1., 0.], 'up': [0., 0., 1.], 'origin_cm': [0., 0., 0.]}
    if rotated:
        basis = {'right': [0., 1., 0.], 'forward': [0., 0., 1.], 'up': [1., 0., 0.], 'origin_cm': [20., -7., 53.]}
    local = [[-2., -1., 10.], [2., -1., 11.], [2., 1., 11.], [-2., 1., 10.]]
    world = [[basis['origin_cm'][k]+sum(p[j]*basis[axis][k] for j, axis in enumerate(('right', 'forward', 'up')))
              for k in range(3)] for p in local]
    geometry = {'vertices_cm': world, 'faces': [[0, 1, 2, 3], [3, 2, 1, 0]],
                'face_sets': [10, 20], 'source_sha256': 'a'*64, 'pose_sha256': 'b'*64}
    profile = {'status': 'PROFILE_MEASURED', 'segmentation': 'EXPLICIT_SOURCE', 'cache_key': 'c'*64,
               'source_sha256': 'a'*64, 'pose_sha256': 'b'*64, 'frame': basis,
               'geometry_sha256': digest([geometry['vertices_cm'], geometry['faces']])}
    vertices = [0, 1, 2, 3] if closed else [0, 1, 2]
    points = [world[i] for i in vertices]
    pairs = list(zip(vertices, vertices[1:]+([vertices[0]] if closed else [])))
    length = math.fsum(math.dist(world[a], world[b]) for a, b in pairs)
    row = {'id': 'measured', 'closed': closed, 'vertex_ids': vertices, 'edge_vertex_ids': [list(p) for p in pairs],
           'edge_source_face_ids': [[0, 1] if closed else [0] for _ in pairs]}
    if closed:
        row.update(curve_world_cm=points, length_cm=length, source_regions=[10, 20])
    else:
        row.update(polyline_world_cm=points, edge_arclength_cm=length, domain_region_ids=[10])
    report = {'version': 1, 'status': 'BODY_SOURCE_PATHS_MEASURED_FOR_REVIEW' if closed else 'BODY_SURFACE_OPEN_PATH_PROPOSALS_FOR_REVIEW',
              'frame': copy.deepcopy(basis), 'paths': [row],
              'identity': {key: profile[key] for key in ('geometry_sha256', 'source_sha256', 'pose_sha256')}}
    report['identity']['face_sets_sha256'] = digest(geometry['face_sets'])
    if closed:
        report['identity'].update(profile_sha256=digest(profile), profile_cache_key=profile['cache_key'])
    document = {'version': 1, 'profile_sha256': digest(profile), 'paths': {
        'chosen': {'report': report, 'report_sha256': digest(report), 'path_id': 'measured', 'region': region}},
        'pieces': {'sample': {'path_ref': 'chosen'}}}
    return profile, geometry, report, document, local


def rehash(document):
    for binding in document['paths'].values():
        binding['report_sha256'] = digest(binding['report'])


class AnatomicalPlacement(unittest.TestCase):
    def test_closed_source_path_retains_height_and_exact_geometry_in_rotated_frame(self):
        for rotated in (False, True):
            profile, geometry, report, doc, local = fixture(rotated=rotated)
            before = digest([profile, geometry, report, doc])
            result = validate_anatomical_references(profile, doc, geometry=geometry)
            path = result['paths']['chosen']
            self.assertEqual(path['points_body_cm'], local)
            self.assertEqual(path['points_world_cm'], geometry['vertices_cm'])
            self.assertEqual(path['geometry_validation'], 'EXACT_SOURCE_EDGES_VERIFIED')
            self.assertEqual(path['human_review'], 'CALLER_MUST_VERIFY')
            self.assertEqual(path['acceptance'], 'NOT_GRANTED')
            self.assertEqual(digest([profile, geometry, report, doc]), before)
            path['points_world_cm'][0][0] += 1
            result['pieces']['sample']['path_ref'] = 'different'
            self.assertEqual(digest([profile, geometry, report, doc]), before)

    def test_open_source_path_can_bind_leg_hand_digit_and_custom_regions(self):
        for region in ('upper_leg.left', 'lower_leg.right', 'hand.left', 'finger.thumb.right', 'toe.great.left', 'custom:tail.segment_2'):
            profile, geometry, report, doc, local = fixture(closed=False, rotated=True, region=region)
            result = validate_anatomical_references(profile, doc, geometry=geometry)
            path = result['paths']['chosen']
            self.assertFalse(path['closed'])
            self.assertEqual(path['points_body_cm'], local[:3])
            self.assertEqual(sample_path(path['points_body_cm'], [0., 1.], closed=False), [local[0], local[2]])
            rows = region_coverage(result, [{'region': region, 'primitive': 'path_frames'}])['regions']
            self.assertEqual(rows[0]['status'], 'MEASURED_REFERENCE_AVAILABLE')

    def test_curve_frames_are_equivariant_to_rigid_transform(self):
        local = [[0., 0., 0.], [4., 0., 1.], [4., 2., 2.]]
        transform = lambda p: [p[2]+11., p[0]-17., p[1]+3.]
        rotate = lambda p: [p[2], p[0], p[1]]
        original = path_frames(local, [.1, .65, .9], closed=False, reference_normal=[0., 0., 1.])
        changed = path_frames([transform(p) for p in local], [.1, .65, .9], closed=False, reference_normal=[1., 0., 0.])
        for a, b in zip(original, changed):
            for x, y in zip(transform(a['point_cm']), b['point_cm']): self.assertAlmostEqual(x, y)
            for key in ('tangent', 'normal', 'binormal'):
                for x, y in zip(rotate(a[key]), b[key]): self.assertAlmostEqual(x, y)
            self.assertAlmostEqual(sum(x*y for x, y in zip(b['normal'], b['tangent'])), 0.)
            self.assertAlmostEqual(math.hypot(*b['normal']), 1.)

    def test_arclength_sampling_closed_seam_and_outgoing_corner_are_explicit(self):
        points = [[0., 0., 0.], [4., 0., 0.], [4., 2., 0.], [0., 2., 0.]]
        self.assertEqual(sample_path(points, [0., 1., .5, 1/3], closed=True),
                         [[0., 0., 0.], [0., 0., 0.], [4., 2., 0.], [4., 0., 0.]])
        frames = path_frames(points, [0., 1., 1/3], closed=True, reference_normal=[0., 0., 3.])
        self.assertEqual(frames[0], frames[1])
        self.assertEqual(frames[2]['tangent'], [0., 1., 0.])

    def test_generic_kernel_does_not_mirror_left_right_or_invent_landmarks(self):
        profile, geometry, _, doc, _ = fixture(region='upper_arm.left')
        del profile['cache_key']
        with self.assertRaises(StudioError): validate_anatomical_references(profile, doc, geometry=geometry)
        profile, geometry, _, doc, _ = fixture(region='upper_arm.left')
        normalized = validate_anatomical_references(profile, doc, geometry=geometry)
        coverage = region_coverage(normalized, [
            {'region': 'upper_arm.left', 'primitive': 'sample_path'},
            {'region': 'upper_arm.right', 'primitive': 'sample_path'}])
        self.assertEqual([r['status'] for r in coverage['regions']], ['MEASURED_REFERENCE_AVAILABLE', 'MISSING_MEASURED_REFERENCE'])

    def test_numerical_reference_validation_without_geometry_is_explicitly_unverified(self):
        profile, _, report, _, _ = fixture()
        result = resolve_measured_path(profile, report, 'measured', expected_report_sha256=digest(report), region='neck')
        self.assertEqual(result['geometry_validation'], 'CALLER_MUST_VERIFY')
        self.assertEqual(result['vertex_ids'], [0, 1, 2, 3])
        self.assertEqual(result['native_provenance'], 'CALLER_MUST_VERIFY')
        self.assertNotIn('source_face_incidence', result)

    def test_verified_incidence_survives_normalization_without_aliasing_or_coordinate_change(self):
        for closed in (False, True):
            for rotated in (False, True):
                profile, geometry, report, doc, _ = fixture(closed=closed, rotated=rotated)
                before = digest([profile, geometry, report, doc])
                verified = validate_anatomical_references(profile, doc, geometry=geometry)['paths']['chosen']
                unverified = resolve_measured_path(profile, report, 'measured',
                    expected_report_sha256=digest(report), region='neck')
                self.assertEqual(verified['points_body_cm'], unverified['points_body_cm'])
                self.assertEqual(verified['points_world_cm'], unverified['points_world_cm'])
                support = verified['source_face_incidence']
                self.assertEqual(support['edge_source_face_ids'], report['paths'][0]['edge_source_face_ids'])
                self.assertEqual(support['edge_source_region_ids'],
                    [[geometry['face_sets'][i] for i in row] for row in support['edge_source_face_ids']])
                self.assertEqual(support['identity'], {key: report['identity'][key] for key in
                    ('source_sha256', 'pose_sha256', 'geometry_sha256', 'face_sets_sha256')})
                self.assertEqual(support['surface_correspondence'], 'NOT_SELECTED')
                self.assertEqual(support['native_provenance'], 'CALLER_MUST_VERIFY')
                support['edge_source_face_ids'][0][0] = 999
                support['identity']['pose_sha256'] = 'f'*64
                self.assertEqual(digest([profile, geometry, report, doc]), before)

    def test_unverified_geometry_never_publishes_claimed_incidence(self):
        profile, _, report, _, _ = fixture()
        report['paths'][0]['edge_source_face_ids'] = [[999]]
        result = resolve_measured_path(profile, report, 'measured',
            expected_report_sha256=digest(report), region='neck')
        self.assertNotIn('source_face_incidence', result)
        self.assertEqual(result['geometry_validation'], 'CALLER_MUST_VERIFY')

    def test_incidence_rejects_numeric_aliases_duplicates_and_invalid_face_rows(self):
        for face_ids in ([0., 1.], [False, True], [0, 0], [-1, 1], [0, 2], [], (0, 1), None):
            profile, geometry, report, doc, _ = fixture()
            report['paths'][0]['edge_source_face_ids'][0] = face_ids
            rehash(doc)
            with self.subTest(face_ids=face_ids), self.assertRaisesRegex(StudioError, 'integer face IDs'):
                validate_anatomical_references(profile, doc, geometry=geometry)

    def test_stale_source_pose_geometry_profile_or_frame_are_refused(self):
        for variant in ('source_sha256', 'pose_sha256', 'geometry_sha256', 'profile_sha256', 'profile_cache_key', 'frame'):
            profile, geometry, report, doc, _ = fixture()
            if variant == 'frame': report['frame']['origin_cm'][0] += 1
            else: report['identity'][variant] = 'f'*64
            rehash(doc)
            with self.subTest(variant=variant), self.assertRaises(StudioError):
                validate_anatomical_references(profile, doc, geometry=geometry)

    def test_rehashed_forged_path_coordinates_still_fail_against_geometry(self):
        profile, geometry, report, doc, _ = fixture()
        report['paths'][0]['curve_world_cm'] = copy.deepcopy(report['paths'][0]['curve_world_cm'])
        report['paths'][0]['curve_world_cm'][0][0] += .5
        points = report['paths'][0]['curve_world_cm']
        report['paths'][0]['length_cm'] = math.fsum(math.dist(a, b) for a, b in zip(points, points[1:]+points[:1]))
        rehash(doc)
        with self.assertRaisesRegex(StudioError, 'coordinates'): validate_anatomical_references(profile, doc, geometry=geometry)

    def test_rehashed_fake_edges_faces_or_region_labels_fail(self):
        for variant in ('edge', 'face', 'region', 'label_hash'):
            profile, geometry, report, doc, _ = fixture()
            row = report['paths'][0]
            if variant == 'edge': row['edge_vertex_ids'][0] = [0, 2]
            elif variant == 'face': row['edge_source_face_ids'][0] = [0]
            elif variant == 'region': row['source_regions'] = [10, 99]
            else: report['identity']['face_sets_sha256'] = 'f'*64
            rehash(doc)
            with self.subTest(variant=variant), self.assertRaises(StudioError):
                validate_anatomical_references(profile, doc, geometry=geometry)

    def test_missing_duplicate_unmeasured_or_stale_report_refuses(self):
        for variant in ('missing', 'duplicate', 'unmeasured', 'hash'):
            profile, geometry, report, doc, _ = fixture()
            if variant == 'missing': report['paths'] = []
            elif variant == 'duplicate': report['paths'].append(copy.deepcopy(report['paths'][0]))
            elif variant == 'unmeasured': report['status'] = 'GUESSED_PATH'
            else: doc['paths']['chosen']['report_sha256'] = 'f'*64
            if variant != 'hash': rehash(doc)
            with self.subTest(variant=variant), self.assertRaises(StudioError):
                validate_anatomical_references(profile, doc, geometry=geometry)

    def test_invalid_closed_length_and_topology_do_not_get_repaired(self):
        for variant in ('collapsed', 'length', 'topology', 'vertex_type'):
            profile, _, report, doc, _ = fixture()
            row = report['paths'][0]
            if variant == 'collapsed': row['curve_world_cm'][1] = row['curve_world_cm'][0][:]
            elif variant == 'length': row['length_cm'] += 1
            elif variant == 'topology': row['closed'] = False
            else: row['vertex_ids'][0] = []
            rehash(doc)
            with self.subTest(variant=variant), self.assertRaises(StudioError): validate_anatomical_references(profile, doc)

    def test_frame_refuses_scaled_sheared_left_handed_or_nonfinite(self):
        for variant in ('scale', 'shear', 'handedness', 'nonfinite'):
            profile, _, report, doc, _ = fixture()
            if variant == 'scale': profile['frame']['right'][0] = 2.
            elif variant == 'shear': profile['frame']['forward'][0] = .2
            elif variant == 'handedness': profile['frame']['right'][0] = -1.
            else: profile['frame']['up'][0] = math.inf
            if variant == 'nonfinite':
                with self.assertRaises(StudioError): resolve_measured_path(profile, report, 'measured', expected_report_sha256=digest(report), region='neck')
                continue
            doc['profile_sha256'] = digest(profile)
            with self.subTest(variant=variant), self.assertRaises(StudioError): validate_anatomical_references(profile, doc)

    def test_no_implicit_axis_for_parallel_reference_field(self):
        with self.assertRaises(StudioError):
            path_frames([[0., 0., 0.], [0., 0., 10.]], [.5], closed=False, reference_normal=[0., 0., 1.])

    def test_invalid_sample_requests_and_budget_refuse(self):
        points = [[0., 0., 0.], [1., 0., 0.]]
        for fractions in ([], [-.01], [1.01], [True], [math.nan], [0.]*8193):
            with self.subTest(fractions=str(fractions)[:20]), self.assertRaises(StudioError):
                sample_path(points, fractions, closed=False)
        with self.assertRaises(StudioError): sample_path(points, [.5], closed=True)
        with self.assertRaises(StudioError): sample_path([points[0], points[0]], [.5], closed=False)

    def test_body_wide_inventory_separates_missing_and_unsupported(self):
        profile, geometry, _, doc, _ = fixture(region='foot.right')
        result = validate_anatomical_references(profile, doc, geometry=geometry)
        report = region_coverage(result)
        self.assertEqual({r['region'] for r in report['regions']}, set(STANDARD_REGIONS))
        self.assertEqual(sum(r['status'] == 'MEASURED_REFERENCE_AVAILABLE' for r in report['regions']), 1)
        self.assertEqual(report['acceptance'], 'NOT_GRANTED')
        rows = region_coverage(result, [
            {'region': 'foot.right', 'primitive': 'unsupported_surface_solver'},
            {'region': 'unknown', 'primitive': 'sample_path'},
            {'region': 'foot.right', 'primitive': 'sample_path', 'reference_id': 'absent'}])['regions']
        self.assertEqual([r['status'] for r in rows], ['UNSUPPORTED_PRIMITIVE',
            'UNSUPPORTED_REGION_REQUIRES_EXPLICIT_CUSTOM_BINDING', 'MISSING_MEASURED_REFERENCE'])

    def test_optional_surface_triangles_preserve_indices_without_claiming_native_authentication(self):
        profile, geometry, _, doc, _ = fixture()
        doc['triangles'] = [[0, 1, 2], [0, 2, 3]]
        before = digest(doc)
        result = validate_anatomical_references(profile, doc, geometry=geometry)
        self.assertEqual(result['triangles'], doc['triangles'])
        self.assertEqual(result['triangles_sha256'], digest(doc['triangles']))
        self.assertEqual(result['triangulation_provenance'], 'SURFACE_CONSUMER_MUST_VERIFY_NATIVE_TRIANGULATION')
        result['triangles'][0][0] = 3
        self.assertEqual(digest(doc), before)
        with self.assertRaises(StudioError): validate_anatomical_references(profile, doc)
        for triangles in ([], [[0, 0, 1]], [[0, 1, 5]], [[0, 1, 2, 3]], [[0, 1, True]], [[0, 1, []]]):
            doc['triangles'] = triangles
            with self.subTest(triangles=triangles), self.assertRaises(StudioError):
                validate_anatomical_references(profile, doc, geometry=geometry)

    def test_surface_only_manifest_requires_exact_geometry_triangles_and_piece_policies(self):
        profile, geometry, _, doc, _ = fixture()
        doc['paths'] = {}
        doc['triangles'] = [[0, 1, 2], [0, 2, 3]]
        doc['pieces'] = {'panel': {'guide_kind': 'REGIONAL_SURFACE_ENVELOPE_V1'}}
        result = validate_anatomical_references(profile, doc, geometry=geometry)
        self.assertEqual(result['paths'], {})
        self.assertEqual(result['pieces'], doc['pieces'])
        self.assertTrue(all(row['status'] == 'MISSING_MEASURED_REFERENCE'
                            for row in region_coverage(result)['regions']))
        for missing in ('geometry', 'triangles', 'pieces'):
            candidate = copy.deepcopy(doc)
            if missing == 'triangles': candidate['triangles'] = []
            elif missing == 'pieces': candidate['pieces'] = {}
            with self.subTest(missing=missing), self.assertRaises(StudioError):
                validate_anatomical_references(profile, candidate, geometry=None if missing == 'geometry' else geometry)
        changed = copy.deepcopy(geometry)
        changed['vertices_cm'][0][0] += .1
        with self.assertRaises(StudioError): validate_anatomical_references(profile, doc, geometry=changed)
        profile['status'] = 'NEEDS_CLARIFICATION'
        doc['profile_sha256'] = digest(profile)
        with self.assertRaises(StudioError): validate_anatomical_references(profile, doc, geometry=geometry)


if __name__ == '__main__':
    unittest.main()
