import copy
import unittest
from unittest.mock import patch

from a3d.core import StudioError, digest
from a3d.constrained_guide_recovery import LocalSurfaceConstraints
from a3d.local_surface_constraint_producer import produce_local_surface_constraints


def fixture(points=None, duplicate=False, opposite=False):
    points = points or [[1., 1., .1], [2., 1., .1], [1., 2., .1]]
    if len(points) < 3:
        points = copy.deepcopy(points)+[[2., 1., .1], [1., 2., .1]][:3-len(points)]
    payload = {'rest_cm': copy.deepcopy(points), 'faces': [[0, 1, 2]],
               'panels': {'active': {'indices': list(range(len(points)))}}}
    vertices = [[0., 0., 0.], [10., 0., 0.], [0., 10., 0.]]
    faces = [[0, 1, 2]]
    if duplicate:
        vertices += copy.deepcopy(vertices)
        faces.append([3, 5, 4] if opposite else [3, 4, 5])
    body = {'vertices_cm': vertices, 'faces': faces, 'source_sha256': '1'*64, 'pose_sha256': '2'*64}
    triangles = copy.deepcopy(faces)
    identity = {'source_payload_sha256': digest(payload), 'entry_coordinates_sha256': digest(points),
                'body_geometry_sha256': digest([vertices, faces]), 'body_triangles_sha256': digest(triangles),
                'body_source_sha256': body['source_sha256'], 'body_pose_sha256': body['pose_sha256']}
    domains = {'surface': {'status': 'MEASURED', 'body_identity_sha256': digest(
        {k: v for k, v in identity.items() if k.startswith('body_')}), 'triangle_ids': list(range(len(triangles)))}}
    spec = {'version': 1, 'identity': identity, 'selected_piece_ids': ['active'],
            'clearance_cm': .3, 'trust_radius_cm': 20., 'weight': 10000., 'search_margin_cm': .01,
            'budgets': {'max_selected_vertices': 32000, 'max_queries': 32000,
                       'max_triangle_evaluations': 1000000, 'max_output_rows': 32000, 'max_seconds': 20.}}
    return payload, points, body, triangles, domains, spec


class LocalSurfaceProducerTests(unittest.TestCase):
    def produce(self, data, **options):
        return produce_local_surface_constraints(*data, clock=options.pop('clock', lambda: 0.), **options)

    def test_unique_interior_full_document_consumed_without_input_mutation(self):
        data = fixture(); before = digest(data)
        result = self.produce(data)
        self.assertEqual(result['status'], 'LOCAL_CONSTRAINT_DOCUMENT_PREPARED')
        self.assertTrue(result['coverage_complete']); self.assertEqual(before, digest(data))
        source, entry, *_ = data
        groups = {i: [i] for i in range(len(entry))}
        consumer = LocalSurfaceConstraints(result['consumer_document'], source, entry,
            set(groups), groups, set(), lambda: None)
        self.assertTrue(consumer.observe(entry)['trust_domain_valid'])
        self.assertFalse(consumer.observe(entry)['satisfied'])
        self.assertEqual(result['qualification'], 'NONE')

    def test_closed_edge_nearest_does_not_imply_valid_plane_projection(self):
        data = fixture([[-1., 1., .2]])
        result = self.produce(data); row = result['diagnostics'][0]
        self.assertEqual(row['point_cm'], [0., 1., 0.])
        self.assertAlmostEqual(row['unsigned_closed_triangle_distance_cm'], 1.04**.5)
        self.assertAlmostEqual(row['signed_plane_offset_cm'], .2)
        self.assertFalse(row['entry_patch_valid'])
        self.assertEqual(result['status'], 'NEEDS_REPRESENTATION')
        self.assertIsNone(result['consumer_document'])

    def test_all_ties_refused_including_duplicate_coplanar_and_opposed_normals(self):
        for opposite in (False, True):
            with self.subTest(opposite=opposite):
                result = self.produce(fixture(duplicate=True, opposite=opposite))
                self.assertEqual(result['status'], 'NEEDS_REPRESENTATION')
                self.assertIsNone(result['consumer_document'])
                for row in result['diagnostics']:
                    self.assertEqual(row['nearest_tie_ids'], [0, 1])
                    self.assertTrue(row['nearest_triangle_ambiguous'])

    def test_signed_offset_is_only_oriented_plane_not_global_inside(self):
        data = fixture([[1., 1., -.2]])
        result = self.produce(data)
        self.assertAlmostEqual(result['diagnostics'][0]['signed_plane_offset_cm'], -.2)
        self.assertEqual(result['global_inside_outside'], 'NOT_ASSESSED')
        self.assertEqual(result['signed_offset_scope'], 'ORIENTED_LOCAL_TRIANGLE_PLANE_ONLY')

    def test_missing_domains_never_invent_measurement(self):
        for domains in (None, {}):
            data = list(fixture()); data[4] = domains
            result = self.produce(data)
            self.assertEqual(result['status'], 'NEEDS_MEASURED_DOMAINS')
            self.assertIsNone(result['consumer_document'])
            self.assertTrue(all(not row['measured_domain_ids'] for row in result['diagnostics']))

    def test_supplied_domains_missing_triangle_do_not_create_partial_document(self):
        data = list(fixture(duplicate=True))
        # Separate second triangle spatially so nearest is unique but uncovered.
        data[2]['vertices_cm'][3:] = [[20., 0., 0.], [30., 0., 0.], [20., 10., 0.]]
        data[1][0] = [21., 1., .1]
        data[4]['surface']['triangle_ids'] = [0]
        self.reidentify(data)
        result = self.produce(data)
        self.assertEqual(result['status'], 'NEEDS_MEASURED_DOMAINS')
        self.assertIsNone(result['consumer_document'])

    @staticmethod
    def reidentify(data):
        payload, points, body, triangles, domains, spec = data
        spec['identity'].update(source_payload_sha256=digest(payload), entry_coordinates_sha256=digest(points),
            body_geometry_sha256=digest([body['vertices_cm'], body['faces']]), body_triangles_sha256=digest(triangles))
        if domains:
            for section in domains.values():
                section['body_identity_sha256'] = digest({k: v for k, v in spec['identity'].items() if k.startswith('body_')})

    def test_bad_owner_winding_stale_nonfinite_and_domain_status_refused(self):
        for kind in ('owner', 'winding', 'source', 'nonfinite', 'domain'):
            data = list(fixture())
            if kind == 'owner': data[2]['faces'].append([0, 1, 2])
            if kind == 'winding': data[3][0].reverse()
            if kind == 'source': data[5]['identity']['source_payload_sha256'] = 'a'*64
            if kind == 'nonfinite': data[1][0][0] = float('nan')
            if kind == 'domain': data[4]['surface']['status'] = 'NOT_QUALIFIED'
            with self.subTest(kind=kind), self.assertRaises(StudioError): self.produce(data)

    def test_query_triangle_output_and_vertex_budgets_preserve_partial_scope(self):
        for key in ('max_queries', 'max_triangle_evaluations', 'max_output_rows', 'max_selected_vertices'):
            data = list(fixture()); data[5]['budgets'][key] = 1
            result = self.produce(data)
            self.assertEqual(result['status'], 'BUDGET_EXHAUSTED')
            self.assertIsNone(result['consumer_document']); self.assertFalse(result['coverage_complete'])
            self.assertEqual(result['selected_material_indices'], [0, 1, 2])
            if key in ('max_output_rows', 'max_selected_vertices'):
                self.assertEqual(result['work']['triangle_evaluations'], 0)

    def test_time_deadline_and_bad_clocks(self):
        data = fixture(); values = iter([0., 20.])
        result = self.produce(data, clock=lambda: next(values))
        self.assertEqual(result['status'], 'BUDGET_EXHAUSTED')
        self.assertEqual(result['reasons'], ['TIME_BUDGET'])
        for invalid in (float('nan'), -1.):
            values = iter([0., invalid])
            with self.assertRaises(StudioError): self.produce(data, clock=lambda: next(values))

    def test_inactive_piece_coordinates_and_body_hash_preserved(self):
        data = list(fixture()); data[1].append([1000., 1000., 1000.]); data[0]['rest_cm'].append([1000., 1000., 1000.])
        data[0]['panels']['inactive'] = {'indices': [3]}; self.reidentify(data)
        before = digest(data)
        result = self.produce(data)
        self.assertEqual(result['selected_material_indices'], [0, 1, 2]); self.assertEqual(before, digest(data))
        self.assertEqual(set(result['consumer_document']['body_geometry']),
                         {'vertices_cm', 'faces', 'source_sha256', 'pose_sha256'})

    def test_diagnostic_all_indices_can_exceed_consumer_cap_without_publication(self):
        points = [[1., 1., .1] for _ in range(4097)]
        result = self.produce(fixture(points))
        self.assertEqual(len(result['diagnostics']), 4097); self.assertTrue(result['coverage_complete'])
        self.assertEqual(result['status'], 'NEEDS_REPRESENTATION')
        self.assertIn('CONSUMER_V1_ROW_CAP_EXCEEDED', result['reasons'])
        self.assertIsNone(result['consumer_document'])

    def test_far_distance_is_not_a_sizing_or_bad_placement_verdict(self):
        result = self.produce(fixture([[1., 1., 21.]]))
        self.assertEqual(result['status'], 'NEEDS_REPRESENTATION')
        self.assertEqual(result['dimensional_classification'], 'NOT_ASSESSED')
        self.assertIn('ENTRY_OUTSIDE_TRUST_BALL', result['reasons'])

    def test_whole_json_invalid_tree_refuses_before_any_digest(self):
        for kind in ('face', 'rest', 'node', 'bytes', 'depth', 'cycle', 'number', 'string', 'integer', 'key', 'object'):
            data = list(fixture())
            limits = {'MAX_JSON_NODES': 4000000}
            if kind == 'face': data[0]['faces'] = [['not an index']]
            if kind == 'rest': data[0]['rest_cm'][0] = ['not a number', 1, 2]
            if kind == 'node': data[0]['metadata'] = list(range(10000)); limits['MAX_JSON_NODES'] = 1000
            if kind == 'bytes': data[0]['metadata'] = ['a'*1000 for _ in range(10)]; limits['MAX_JSON_BYTES'] = 10000
            if kind == 'depth':
                value = 0
                for _ in range(40): value = [value]
                data[0]['metadata'] = value
            if kind == 'cycle':
                value = []; value.append(value); data[0]['metadata'] = value
            if kind == 'number': data[0]['metadata'] = float('inf')
            if kind == 'string': data[0]['metadata'] = 'a'*65537
            if kind == 'integer': data[0]['metadata'] = 1 << 65
            if kind == 'key': data[0]['metadata'] = {1: 'not a JSON key'}
            if kind == 'object': data[0]['metadata'] = object()
            with self.subTest(kind=kind), patch('a3d.local_surface_constraint_producer.digest',
                    side_effect=AssertionError('premature digest')), patch.multiple(
                    'a3d.local_surface_constraint_producer', **limits), self.assertRaises(StudioError):
                self.produce(data)

    def test_legitimate_bounded_extra_metadata_remains_supported(self):
        data = list(fixture()); data[0]['metadata'] = {'label': 'Épaule', 'opaque': list(range(10000))}
        self.reidentify(data)
        result = self.produce(data)
        self.assertEqual(result['status'], 'LOCAL_CONSTRAINT_DOCUMENT_PREPARED')
        self.assertGreater(result['work']['json_nodes'], 10000)

    def test_exact_skinny_triangle_barycentric_document_consumes(self):
        data = list(fixture())
        triangle = [[-9.830973170998192, -12.676086344783116, 0.],
                    [-8.248090929069772, -.9293047333645852, 0.],
                    [-8.570471550079867, -3.2778789416974075, 0.]]
        data[2]['vertices_cm'] = triangle
        data[1][:] = [[-8.851907850052335, -5.392768900123273, .1] for _ in range(3)]
        self.reidentify(data)
        result = self.produce(data)
        self.assertEqual(result['status'], 'LOCAL_CONSTRAINT_DOCUMENT_PREPARED')
        source, entry, *_ = data; groups = {i: [i] for i in range(len(entry))}
        LocalSurfaceConstraints(result['consumer_document'], source, entry, set(groups), groups, set(), lambda: None)
        for row in result['diagnostics']:
            self.assertLessEqual(row['barycentric_reconstruction_gap_cm'], 1e-9)

    def test_source_panel_coverage_and_stored_binding_refuse_before_digest(self):
        for kind in ('coverage', 'owner', 'stored_uv', 'stored_ids', 'source_map'):
            data = list(fixture())
            if kind == 'coverage': data[0]['panels']['active']['indices'].pop()
            if kind == 'owner': data[0]['source_face_pieces'] = ['missing']
            if kind == 'stored_uv': data[0]['source_rest_triangles_cm'] = [[[0, 0], [1, 0], ['bad', 1]]]
            if kind == 'stored_ids': data[0]['source_face_vertex_ids'] = [[0, 2, 1]]
            if kind == 'source_map': data[0]['source_vertex_map'] = {'bad': 0}
            with self.subTest(kind=kind), patch('a3d.local_surface_constraint_producer.digest',
                    side_effect=AssertionError('premature digest')), self.assertRaises(StudioError):
                self.produce(data)


if __name__ == '__main__':
    unittest.main()
