"""Portable open-path proposals; no anatomy, body or fitting acceptance."""
import copy
import json
import math
import unittest
from unittest.mock import patch

from a3d.body_surface_paths import _Budget, _shortest, propose_body_surface_paths
from a3d.core import StudioError, digest


FRAME = {'origin_cm': [0., 0., 0.], 'right': [-1., 0., 0.],
         'forward': [0., -1., 0.], 'up': [0., 0., 1.]}


def reports(geometry, rings, frame=FRAME):
    identity = {'geometry_sha256': digest([geometry['vertices_cm'], geometry['faces']]),
        'face_sets_sha256': digest(geometry['face_sets']),
        'source_sha256': geometry['source_sha256'], 'pose_sha256': geometry['pose_sha256']}
    paths = []
    for pid, ids, face_ids, regions in rings:
        paths.append({'id': pid, 'closed': True, 'vertex_ids': list(ids),
            'edge_vertex_ids': [list(pair) for pair in zip(ids, ids[1:]+ids[:1])],
            'edge_source_face_ids': [face_ids for _ in ids], 'source_regions': regions,
            'curve_world_cm': [list(geometry['vertices_cm'][i]) for i in ids]})
    return {'source': {'identity': identity, 'frame': copy.deepcopy(frame), 'paths': paths}}


def vertex(index):
    return {'kind': 'source_vertex', 'vertex_id': index}


def fixture(second=False):
    geometry = {'vertices_cm': [[0., 0., 1.], [1., 0., .2], [1., 1., 0.], [0., 1., .3]],
        'faces': [[0, 1, 2, 3], [3, 2, 1, 0]], 'face_sets': [1, 2],
        'source_sha256': 'a'*64, 'pose_sha256': 'b'*64}
    rings = [('ring', [0, 1, 2, 3], [0, 1], [1, 2])]
    if second:
        geometry['vertices_cm'] += [[x+10., y, z+.2] for x, y, z in geometry['vertices_cm']]
        geometry['faces'] += [[4, 5, 6, 7], [7, 6, 5, 4]]
        geometry['face_sets'] += [3, 4]
        rings.append(('other', [4, 5, 6, 7], [2, 3], [3, 4]))
    spec = {'version': 1, 'frame': copy.deepcopy(FRAME), 'budgets': {},
        'paths': [{'id': 'proposal', 'domain_region_ids': [1], 'start': vertex(0), 'end': vertex(2)}]}
    return geometry, reports(geometry, rings), spec, rings


class BodySurfacePaths(unittest.TestCase):
    def test_tilted_surface_polyline_length_differs_from_chord_without_new_diagonals(self):
        geometry, paths, spec, _ = fixture(); before = digest([geometry, paths, spec])
        report = propose_body_surface_paths(geometry, paths, spec, clock=lambda: 0.)
        row = report['paths'][0]
        self.assertEqual(row['vertex_ids'], [0, 3, 2])
        self.assertEqual(row['edge_source_face_ids'], [[0], [0]])
        self.assertGreater(row['edge_arclength_cm'], row['endpoint_chord_cm'])
        self.assertAlmostEqual(row['edge_arclength_cm'], math.sqrt(1+.7**2)+math.sqrt(1+.3**2))
        self.assertEqual(row['vertical_drop_cm'], 1.)
        self.assertEqual(row['polyline_world_cm'], [geometry['vertices_cm'][i] for i in (0, 3, 2)])
        self.assertFalse(row['closed']); self.assertIsNone(row['mesh_approximation_error_cm'])
        self.assertEqual(row['smooth_geodesic_error_bound'], 'NOT_ESTABLISHED')
        self.assertEqual(row['qualification'], 'NONE')
        self.assertEqual(row['tailoring_homology'], 'REVIEW_REQUIRED')
        self.assertFalse(report['body_girths_replaced'])
        self.assertEqual(digest([geometry, paths, spec]), before)
        json.dumps(report, allow_nan=False)

    def test_boundary_frame_extreme_and_source_centroid_direction_are_data_driven(self):
        geometry, paths, spec, _ = fixture(second=True)
        spec['paths'][0]['start'] = {'kind': 'boundary_toward_path_centroid',
            'report_id': 'source', 'path_id': 'ring', 'toward_report_id': 'source', 'toward_path_id': 'other'}
        spec['paths'][0]['end'] = {'kind': 'boundary_extreme', 'report_id': 'source', 'path_id': 'ring',
                                  'axis': 'up', 'extreme': 'max'}
        row = propose_body_surface_paths(geometry, paths, spec, clock=lambda: 0.)['paths'][0]
        self.assertEqual(row['vertex_ids'], [1, 0])
        self.assertEqual(row['endpoint_sources']['start']['vertex_id'], 1)
        self.assertEqual(row['endpoint_sources']['end']['vertex_id'], 0)
        self.assertGreater(row['endpoint_sources']['start']['endpoint_score_gap_cm'], 0.)
        self.assertIn('direction_target_path_sha256', row['endpoint_sources']['start'])

    def test_rotating_world_coordinates_and_explicit_body_frame_preserves_path_and_drop(self):
        geometry, paths, spec, rings = fixture()
        spec['paths'][0]['start'] = {'kind': 'boundary_extreme', 'report_id': 'source', 'path_id': 'ring', 'axis': 'up', 'extreme': 'max'}
        baseline = propose_body_surface_paths(geometry, paths, spec, clock=lambda: 0.)['paths'][0]
        rotate = lambda point: [point[2], -point[0], point[1]]
        world = lambda point: [a+b for a, b in zip(rotate(point), [7., 10., -4.])]
        geometry['vertices_cm'] = [world(point) for point in geometry['vertices_cm']]
        frame = {key: world(value) if key == 'origin_cm' else rotate(value) for key, value in FRAME.items()}
        spec['frame'] = frame; paths = reports(geometry, rings, frame)
        rotated = propose_body_surface_paths(geometry, paths, spec, clock=lambda: 0.)['paths'][0]
        self.assertEqual(rotated['vertex_ids'], baseline['vertex_ids'])
        self.assertAlmostEqual(rotated['edge_arclength_cm'], baseline['edge_arclength_cm'])
        self.assertAlmostEqual(rotated['vertical_drop_cm'], baseline['vertical_drop_cm'])

    def test_disconnected_or_excluded_domains_never_bridge_or_invent_source_endpoints(self):
        for regions in ([1], [1, 3], [99]):
            geometry, paths, spec, _ = fixture(second=True)
            spec['paths'][0].update(domain_region_ids=regions, end=vertex(4))
            with self.subTest(regions=regions), self.assertRaises(StudioError):
                propose_body_surface_paths(geometry, paths, spec, clock=lambda: 0.)
        geometry, paths, spec, _ = fixture()
        spec['paths'][0]['end'] = {'kind': 'world_point', 'point_world_cm': [3., 4., 5.]}
        with self.assertRaises(StudioError):
            propose_body_surface_paths(geometry, paths, spec, clock=lambda: 0.)

    def test_endpoint_ties_route_ties_and_priority_queue_ties_have_distinct_outcomes(self):
        geometry, _, spec, rings = fixture()
        geometry['vertices_cm'] = [[0., 0., 0.], [1., 0., 0.], [1., 1., 0.], [0., 1., 0.]]
        paths = reports(geometry, rings)
        with self.assertRaisesRegex(StudioError, 'shortest.*tied'):
            propose_body_surface_paths(geometry, paths, spec, clock=lambda: 0.)
        spec['paths'][0]['end'] = vertex(1)
        result = propose_body_surface_paths(geometry, paths, spec, clock=lambda: 0.)
        self.assertEqual(result['paths'][0]['vertex_ids'], [0, 1])
        spec['paths'][0]['start'] = {'kind': 'boundary_extreme', 'report_id': 'source', 'path_id': 'ring', 'axis': 'up', 'extreme': 'max'}
        with self.assertRaisesRegex(StudioError, 'endpoint.*tied'):
            propose_body_surface_paths(geometry, paths, spec, clock=lambda: 0.)

    def test_three_improvements_keep_true_minimum_and_close_second_route_and_propagate_refusal(self):
        unit = math.ulp(100.)
        def graph(last_costs, downstream=False):
            edges = [(0, 1, 1.), (0, 2, 2.), (0, 3, 3.),
                     (1, 4, last_costs[0]), (2, 4, last_costs[1]), (3, 4, last_costs[2])]
            if downstream:
                edges.append((4, 5, 1.))
            result = {}
            for a, b, weight in edges:
                result.setdefault(a, {})[b] = weight
                result.setdefault(b, {})[a] = weight
            return result
        for downstream in (False, True):
            tied = graph([99., 98.-30*unit, 97.-40*unit], downstream)
            end = 5 if downstream else 4
            with self.subTest(downstream=downstream), self.assertRaisesRegex(StudioError, 'tied.*alternatives'):
                _shortest(tied, 0, end, _Budget({}, lambda: 0.))
            # The true best route is permitted when every competitor is
            # separated by much more than the binary64 roundoff policy.
            unique = graph([99., 98.-60*unit, 97.-120*unit], downstream)
            expected = [0, 3, 4, 5] if downstream else [0, 3, 4]
            self.assertEqual(_shortest(unique, 0, end, _Budget({}, lambda: 0.)), expected)

    def test_source_path_branching_missing_ids_and_stale_identity_are_refused(self):
        for variant in ('branch', 'edge', 'face', 'curve', 'identity', 'frame', 'absent', 'zero_centroid',
                        'boolean_curve', 'boolean_face_id', 'boolean_report_frame'):
            geometry, paths, spec, _ = fixture()
            if variant == 'branch': paths['source']['paths'][0]['vertex_ids'].append(1)
            elif variant == 'edge': paths['source']['paths'][0]['edge_vertex_ids'][0].reverse()
            elif variant == 'face': paths['source']['paths'][0]['edge_source_face_ids'][0] = [0]
            elif variant == 'curve': paths['source']['paths'][0]['curve_world_cm'][0][0] += .1
            elif variant == 'identity': paths['source']['identity']['geometry_sha256'] = 'f'*64
            elif variant == 'frame': spec['frame']['up'][0] = .1
            elif variant == 'absent': spec['paths'][0]['start'] = {'kind': 'boundary_extreme', 'report_id': 'source', 'path_id': 'missing', 'axis': 'up', 'extreme': 'max'}
            elif variant == 'boolean_curve': paths['source']['paths'][0]['curve_world_cm'][0][2] = True
            elif variant == 'boolean_face_id': paths['source']['paths'][0]['edge_source_face_ids'][0][1] = True
            elif variant == 'boolean_report_frame': paths['source']['frame']['up'][2] = True
            else: spec['paths'][0]['start'] = {'kind': 'boundary_toward_path_centroid', 'report_id': 'source', 'path_id': 'ring', 'toward_report_id': 'source', 'toward_path_id': 'ring'}
            before = copy.deepcopy([geometry, paths, spec])
            with self.subTest(variant=variant), self.assertRaises(StudioError):
                propose_body_surface_paths(geometry, paths, spec, clock=lambda: 0.)
            self.assertEqual([geometry, paths, spec], before)

    def test_nonfinite_boolean_collapsed_edges_and_invalid_indices_are_domain_errors(self):
        for variant in ('nonfinite', 'bool', 'zero', 'face', 'vertex', 'region', 'unknown_budget'):
            geometry, paths, spec, rings = fixture()
            if variant == 'nonfinite': geometry['vertices_cm'][0][0] = math.inf
            elif variant == 'bool': geometry['vertices_cm'][0][0] = True
            elif variant == 'zero':
                geometry['vertices_cm'][1] = list(geometry['vertices_cm'][0]); paths = reports(geometry, rings)
            elif variant == 'face': geometry['faces'][0][0] = []
            elif variant == 'vertex': spec['paths'][0]['end'] = vertex(True)
            elif variant == 'region': spec['paths'][0]['domain_region_ids'] = [True]
            else: spec['budgets'] = {'unknown': 4}
            with self.subTest(variant=variant), self.assertRaises(StudioError):
                propose_body_surface_paths(geometry, paths, spec, clock=lambda: 0.)

    def test_every_declared_geometry_path_and_shared_visited_budget_is_enforced(self):
        for key, limit in (('max_vertices', 3), ('max_faces', 1), ('max_edges', 7), ('max_visited', 1),
                           ('max_paths', 1), ('max_seconds', True), ('max_edges', 1500001)):
            geometry, paths, spec, _ = fixture(); spec['budgets'][key] = limit
            if key == 'max_paths': spec['paths'].append({**copy.deepcopy(spec['paths'][0]), 'id': 'second'})
            with self.subTest(key=key), self.assertRaisesRegex(StudioError, 'budget'):
                propose_body_surface_paths(geometry, paths, spec, clock=lambda: 0.)
        geometry, paths, spec, _ = fixture()
        spec['paths'].append({**copy.deepcopy(spec['paths'][0]), 'id': 'second'})
        spec['budgets']['max_visited'] = 7
        with self.assertRaisesRegex(StudioError, 'visited'):
            propose_body_surface_paths(geometry, paths, spec, clock=lambda: 0.)

    def test_time_deadline_clock_reversal_and_final_evidence_hash_are_bounded(self):
        for ticks in ((0., 31.), (1., 0.), (0., math.nan)):
            geometry, paths, spec, _ = fixture(); values = iter(ticks)
            with self.subTest(ticks=ticks), self.assertRaises(StudioError):
                propose_body_surface_paths(geometry, paths, spec, clock=lambda: next(values))
        geometry, paths, spec, _ = fixture(); current = [0.]
        def expire(_):
            current[0] = 31.; return 'a'*64
        with patch('a3d.body_surface_paths.sha', side_effect=expire), self.assertRaisesRegex(StudioError, 'time budget'):
            propose_body_surface_paths(geometry, paths, spec, clock=lambda: current[0])

    def test_repeated_reports_are_deterministic_and_finite_with_no_native_acceptance(self):
        geometry, paths, spec, _ = fixture()
        first = propose_body_surface_paths(geometry, paths, spec, clock=lambda: 0.)
        self.assertEqual(first, propose_body_surface_paths(geometry, paths, spec, clock=lambda: 0.))
        self.assertEqual(first, json.loads(json.dumps(first, allow_nan=False)))
        self.assertEqual(first['native_body_origin'], 'SOURCE_REPORT_PROVENANCE_NOT_REVALIDATED_BY_PORTABLE_KERNEL')
        self.assertEqual(first['acceptance'], 'NOT_GRANTED')


if __name__ == '__main__':
    unittest.main()
