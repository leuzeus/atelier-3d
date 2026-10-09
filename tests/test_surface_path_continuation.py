import copy
import json
from pathlib import Path
import unittest

from a3d.surface_path_continuation import Surface, Refused, trace_surface_paths, MAX_VERTEX_SEED_FACES
from a3d.core import StudioError


VERTICES = [[0., 0., 0.], [2., 0., 0.], [2., 2., 0.], [0., 2., 0.]]
TRIANGLES = [[0, 1, 2], [0, 2, 3]]


def planar(vertices=None, triangles=None, owners=None, regions=None, **kwargs):
    vertices = copy.deepcopy(VERTICES if vertices is None else vertices)
    triangles = copy.deepcopy(TRIANGLES if triangles is None else triangles)
    owners = list(range(len(triangles))) if owners is None else owners
    regions = [0]*len(triangles) if regions is None else regions
    return Surface(vertices, triangles, owners, regions, [0], [0., 0., 1.], **kwargs)


class ContinuationTests(unittest.TestCase):
    def batch(self, **kwargs):
        policy = {'method': 'SEEDED_SURFACE_PATH_LIFT_V1', 'source_region_ids': [0],
                  'direction_world': [0., 0., 1.], 'min_cosine': 1e-9,
                  'max_seconds': 120., 'max_events': 100000}
        query = {'request_id': 'source.boundary.0', 'seed_edge_vertex_ids': [0, 1],
                 'seed_fraction': .5, 'seed_face_ids': [0], 'target_world_cm': [.5, 1.5, .3]}
        return trace_surface_paths(VERTICES, TRIANGLES, [0, 1], [0, 0],
            kwargs.pop('policy', policy), kwargs.pop('queries', [query]), **kwargs)

    def test_walk_crosses_shared_diagonal_and_preserves_source(self):
        surface = planar()
        before = copy.deepcopy([surface.vertices, surface.triangles])
        r = surface.trace([0, 1], .5, [0], [.5, 1.5, .3])
        self.assertEqual(r['status'], 'LOCAL_PATH_LIFT_REACHED')
        self.assertEqual(r['selected_source_face'], 1)
        self.assertEqual(r['point_world_cm'], [.5, 1.5, 0.])
        self.assertEqual(len(r['traversed']), 2)
        self.assertEqual([surface.vertices, surface.triangles], before)

    def test_seed_branch_is_not_nearest_sheet(self):
        vertices = VERTICES + [[x, y, z+1.] for x, y, z in VERTICES]
        triangles = TRIANGLES + [[i+4 for i in row] for row in TRIANGLES]
        r = planar(vertices, triangles).trace([0, 1], .5, [0], [.5, 1.5, .9])
        self.assertEqual(r['status'], 'LOCAL_PATH_LIFT_REACHED')
        self.assertEqual(r['point_world_cm'][2], 0.)
        self.assertAlmostEqual(r['signed_ray_distance_cm'], -.9)
        self.assertFalse(r['nearest_selection'])

    def test_declared_region_boundary_refuses(self):
        r = planar(regions=[0, 1]).trace([0, 1], .5, [0], [.5, 1.5, .3])
        self.assertEqual(r['status'], 'CONTINUATION_REFUSED')
        self.assertEqual(r['reason'], 'DECLARED_REGION_BOUNDARY_OR_PATH_OUTSIDE_DOMAIN')

    def test_fold_cannot_be_crossed(self):
        vertices = VERTICES[:3]+[[2., 1., 1.]]
        r = planar(vertices).trace([0, 1], .5, [0], [.5, 1.5, .3])
        self.assertEqual(r['status'], 'CONTINUATION_REFUSED')
        self.assertEqual(r['reason'], 'FOLD_OR_GRAZING_AT_EXIT')

    def test_grazing_seed_refuses(self):
        s = Surface(VERTICES, TRIANGLES, [0, 1], [0, 0], [0], [1., 0., 0.])
        r = s.trace([0, 1], .5, [0], [.5, 1.5, .3])
        self.assertEqual(r['status'], 'CONTINUATION_REFUSED')
        self.assertEqual(r['reason'], 'SEED_HAS_NO_UNIQUE_TRANSVERSE_OUTGOING_PATCH')

    def test_ambiguous_seed_outgoing_faces_refuse(self):
        vertices = [[0., 0., 0.], [2., 0., 0.], [0., 2., 0.], [0., 2., 1.]]
        r = planar(vertices, [[0, 1, 2], [0, 1, 3]]).trace([0, 1], .5, [0, 1], [.9, .5, .3])
        self.assertEqual(r['status'], 'CONTINUATION_REFUSED')
        self.assertEqual(len(r['diagnostic']['outgoing']), 2)

    def test_coplanar_subdivision_preserves_lift_including_vertex_event(self):
        target = [1., 1.75, .3]
        old = planar().trace([0, 1], .5, [0], target)
        vertices = VERTICES + [[1., 1., 0.]]
        triangles = [[0, 1, 4], [1, 2, 4], [2, 3, 4], [3, 0, 4]]
        new = planar(vertices, triangles).trace([0, 1], .5, [0], target)
        self.assertEqual(new['status'], 'LOCAL_PATH_LIFT_REACHED')
        self.assertEqual(old['point_world_cm'], new['point_world_cm'])
        self.assertEqual(old['signed_ray_distance_cm'], new['signed_ray_distance_cm'])
        self.assertEqual(old['minimum_traversed_cosine'], new['minimum_traversed_cosine'])

    def test_coplanar_centroid_subdivision_preserves_lift(self):
        vertices = copy.deepcopy(VERTICES); triangles = []; owners = []
        for fid, tri in enumerate(TRIANGLES):
            mid = len(vertices)
            vertices.append([sum(vertices[i][k] for i in tri)/3 for k in range(3)])
            for a, b in zip(tri, tri[1:]+tri[:1]):
                triangles.append([a, b, mid]); owners.append(fid)
        target = [.5, 1.5, .3]
        old = planar().trace([0, 1], .5, [0], target)
        new = planar(vertices, triangles, owners, [0, 0]).trace([0, 1], .5, [0], target)
        self.assertEqual(new['status'], 'LOCAL_PATH_LIFT_REACHED')
        self.assertEqual(old['point_world_cm'], new['point_world_cm'])
        self.assertEqual(old['selected_source_face'], new['selected_source_face'])

    def test_unproven_seed_face_is_refused(self):
        r = planar().trace([0, 1], .5, [1], [.5, 1.5, .3])
        self.assertEqual(r['reason'], 'SEED_FACE_INCIDENCES_DIFFER_FROM_DECLARED_DOMAIN')

    def test_work_budget_is_explicit_refusal(self):
        with self.assertRaises(Refused) as raised:
            planar(max_events=2)
        self.assertEqual(raised.exception.reason, 'WORK_BUDGET_EXHAUSTED')

    def test_batch_scope_hashes_and_no_admission(self):
        result = self.batch()
        self.assertEqual(result['status'], 'LOCAL_PATHS_REACHED')
        self.assertEqual(result['native_provenance'], 'CALLER_MUST_VERIFY')
        self.assertEqual(result['reserve_admission'], 'NOT_GRANTED')
        self.assertEqual(result['contact_admission'], 'NOT_GRANTED')
        self.assertFalse(result['candidate_adjusted'])
        self.assertEqual(result['unprocessed_queries'], 0)
        query = {'request_id': 'source.boundary.0', 'seed_edge_vertex_ids': [0, 1],
                 'seed_fraction': .5, 'seed_face_ids': [0], 'target_world_cm': [.5, 1.5, .4]}
        changed = self.batch(queries=[query])
        self.assertNotEqual(result['identities']['queries_sha256'], changed['identities']['queries_sha256'])
        self.assertEqual(result['rows'][0]['point_world_cm'], changed['rows'][0]['point_world_cm'])
        self.assertNotEqual(result['rows'][0]['signed_ray_distance_cm'], changed['rows'][0]['signed_ray_distance_cm'])

    def test_input_mutation_after_surface_creation_cannot_mix_geometry(self):
        vertices = copy.deepcopy(VERTICES); triangles = copy.deepcopy(TRIANGLES)
        s = Surface(vertices, triangles, [0, 1], [0, 0], [0], [0., 0., 1.])
        vertices[2][2] = 100.; triangles[1].reverse()
        result = s.trace([0, 1], .5, [0], [.5, 1.5, .3])
        self.assertEqual(result['point_world_cm'], [.5, 1.5, 0.])

    def test_returned_normal_cannot_corrupt_next_query(self):
        s = planar()
        first = s.trace([0, 1], .5, [0], [.5, 1.5, .3])
        first['normal_world'][:] = [7., 8., 9.]
        second = s.trace([0, 1], .5, [0], [.5, 1.5, .3])
        self.assertEqual(second['normal_world'], [0., 0., 1.])
        self.assertEqual(second['cosine'], 1.)

    def test_subnormal_direction_preserves_unit_geometry(self):
        # Plane perpendicular to (1,1,0), with outward winding.
        vertices = [[0., 0., 0.], [1., -1., 0.], [1., -1., -2.], [0., 0., -2.]]
        results = []
        for direction in ([1., 1., 0.], [5e-324, 5e-324, 0.]):
            s = Surface(vertices, TRIANGLES, [0, 1], [0, 0], [0], direction)
            r = s.trace([0, 1], .5, [0], [.5, .1, -1.5])
            self.assertEqual(r['status'], 'LOCAL_PATH_LIFT_REACHED')
            self.assertLessEqual(r['cosine'], 1.+1e-15)
            self.assertLess(r['ray_reconstruction_residual_cm'], 1e-15)
            results.append(r)
        for key in ('point_world_cm', 'signed_ray_distance_cm', 'cosine'):
            self.assertEqual(results[0][key], results[1][key])

    def test_tiny_nondegenerate_triangle_has_stable_normal(self):
        factor = 1e-170
        vertices = [[x*factor, y*factor, z*factor] for x, y, z in VERTICES]
        result = planar(vertices).trace([0, 1], .5, [0], [.5*factor, 1.5*factor, .3])
        self.assertEqual(result['status'], 'LOCAL_PATH_LIFT_REACHED')
        self.assertEqual(result['normal_world'], [0., 0., 1.])
        self.assertEqual(result['cosine'], 1.)

    def test_endpoint_at_shared_edge_leaves_normal_cone_unqualified(self):
        r = planar().trace([0, 1], .5, [0], [.5, .5, .3])
        self.assertEqual(r['status'], 'LOCAL_PATH_LIFT_REACHED')
        self.assertEqual(r['endpoint_normal_status'], 'ENDPOINT_NORMAL_CONE_NOT_CERTIFIED')

    def test_seed_at_vertex_and_zero_projected_path_refuse(self):
        for fraction, target, reason in [
            (0., [.5, 1.5, .3], 'SEED_ENDPOINT_NOT_SUPPORTED_BY_EDGE_SEED_V1'),
            (.5, [1., 0., .3], 'ZERO_PROJECTED_PATH_NEEDS_SEED_NORMAL_CONE')]:
            with self.subTest(reason=reason):
                self.assertEqual(planar().trace([0, 1], fraction, [0], target)['reason'], reason)

    def test_hidden_disconnected_native_vertex_star_refuses(self):
        vertices = VERTICES + [[1., 1., 0.], [1., 1., 1.], [2., 1., 1.]]
        triangles = [[0, 1, 4], [1, 2, 4], [2, 3, 4], [3, 0, 4], [4, 5, 6]]
        r = planar(vertices, triangles, regions=[0, 0, 0, 0, 1]).trace([0, 1], .5, [0], [1., 1.75, .3])
        self.assertEqual(r['reason'], 'NONMANIFOLD_OR_DISCONNECTED_NATIVE_VERTEX_STAR')

    def test_invalid_shapes_duplicate_geometry_and_numerics(self):
        cases = [dict(vertices=None), dict(triangles=[[0, 1, 2], [2, 1, 0]]),
                 dict(owners=[False, 1]), dict(face_regions=[False, 0]),
                 dict(allowed_regions=[False]), dict(direction=[0., 0., float('inf')]),
                 dict(min_cosine=True), dict(max_seconds=True), dict(max_events=True),
                 dict(vertices=[[float('nan'), 0., 0.]]), dict(vertices=[[1e300, 0., 0.]])]
        base = dict(vertices=VERTICES, triangles=TRIANGLES, owners=[0, 1], face_regions=[0, 0],
                    allowed_regions=[0], direction=[0., 0., 1.])
        for patch in cases:
            with self.subTest(patch=patch), self.assertRaises(ValueError):
                Surface(**(base | patch))

    def test_shared_time_budget_retains_partial_rows(self):
        class Clock:
            value = 0.
            def __call__(self):
                self.value += .125
                return self.value
        policy = {'method': 'SEEDED_SURFACE_PATH_LIFT_V1', 'source_region_ids': [0],
                  'direction_world': [0., 0., 1.], 'min_cosine': 1e-9,
                  'max_seconds': 1.5, 'max_events': 100000}
        result = self.batch(policy=policy, clock=Clock())
        self.assertEqual(result['status'], 'CONTINUATION_INCOMPLETE')
        self.assertEqual(result['rows'][0]['reason'], 'TIME_BUDGET_EXHAUSTED')

    def test_deadline_expired_after_last_query_is_not_batch_success(self):
        class Clock:
            value = 0.
            def __call__(self):
                self.value += .125
                return self.value
        # Sweep around final arithmetic/serialization boundaries. Success may
        # only carry a measured elapsed time within the declared allowance.
        for deadline in (2.375, 2.5, 2.625, 2.75, 2.875, 3.):
            policy = {'method': 'SEEDED_SURFACE_PATH_LIFT_V1', 'source_region_ids': [0],
                      'direction_world': [0., 0., 1.], 'min_cosine': 1e-9,
                      'max_seconds': deadline, 'max_events': 100000}
            with self.subTest(deadline=deadline):
                result = self.batch(policy=policy, clock=Clock())
                if result['status'] == 'LOCAL_PATHS_REACHED':
                    self.assertLessEqual(result['elapsed_seconds'], deadline)
                elif result.get('elapsed_seconds', 0) > deadline:
                    self.assertEqual(result['reason'], 'TIME_BUDGET_EXHAUSTED')

    def test_invalid_batch_and_duplicate_ids_are_errors(self):
        for queries in [[], [None], [{'request_id': 'x'}]]:
            with self.subTest(queries=queries), self.assertRaises(StudioError):
                self.batch(queries=queries)
        query = {'request_id': 'same', 'seed_edge_vertex_ids': [0, 1],
                 'seed_fraction': .5, 'seed_face_ids': [0], 'target_world_cm': [.5, 1.5, .3]}
        with self.assertRaises(StudioError):
            self.batch(queries=[query, query])

    def test_entire_batch_budget_exhausted_before_queries_is_incomplete(self):
        policy = {'method': 'SEEDED_SURFACE_PATH_LIFT_V1', 'source_region_ids': [0],
                  'direction_world': [0., 0., 1.], 'min_cosine': 1e-9,
                  'max_seconds': 120., 'max_events': 1}
        result = self.batch(policy=policy)
        self.assertEqual(result['status'], 'CONTINUATION_INCOMPLETE')
        self.assertEqual(result['rows'], [])
        self.assertEqual(result['unprocessed_queries'], 1)


class VertexSeedTests(unittest.TestCase):
    vertices = VERTICES + [[1., 1., 0.]]
    triangles = [[0, 1, 4], [1, 2, 4], [2, 3, 4], [3, 0, 4]]

    def surface(self, **kwargs):
        return planar(self.vertices, self.triangles, **kwargs)

    def query(self, **changes):
        return {'request_id': 'exact.vertex', 'seed_edge_vertex_ids': [4, 0],
                'seed_fraction': 0., 'seed_face_ids': [0, 1, 2, 3],
                'target_world_cm': [1.2, 1.6, .3]} | changes

    def batch(self, queries=None, **changes):
        policy = {'method': 'SEEDED_SURFACE_PATH_LIFT_V2', 'source_region_ids': [0],
                  'direction_world': [0., 0., 1.], 'min_cosine': 1e-9,
                  'max_seconds': 120., 'max_events': 100000} | changes
        return trace_surface_paths(self.vertices, self.triangles, [0, 1, 2, 3], [0]*4,
                                   policy, queries if queries is not None else [self.query()])

    def test_exact_vertex_uses_complete_star_and_unique_outgoing_triangle(self):
        result = self.batch()
        self.assertEqual(result['status'], 'LOCAL_PATHS_REACHED')
        row = result['rows'][0]
        self.assertEqual(row['selected_source_face'], 2)
        self.assertEqual(row['point_world_cm'], [1.2, 1.6, 0.])
        incidence = row['seed_incidence']
        self.assertEqual(incidence['vertex_id'], 4)
        self.assertEqual(incidence['native_star_triangles'], [0, 1, 2, 3])
        self.assertEqual(incidence['all_authorized_incident_source_faces'], [0, 1, 2, 3])
        self.assertFalse(row['nearest_selection'])
        self.assertEqual(result['contact_admission'], 'NOT_GRANTED')

    def test_reversed_edge_endpoint_identifies_same_vertex(self):
        a = self.batch()['rows'][0]
        b = self.batch([self.query(seed_edge_vertex_ids=[0, 4], seed_fraction=1.)])['rows'][0]
        for field in ('point_world_cm', 'selected_source_face', 'normal_world', 'signed_ray_distance_cm'):
            self.assertEqual(a[field], b[field])
        self.assertEqual(b['seed_incidence']['vertex_id'], 4)

    def test_boundary_vertex_fan_is_supported(self):
        r = planar().trace([0, 1], 0, [0, 1], [.5, 1.5, .3], allow_vertex_seed=True)
        self.assertEqual(r['status'], 'LOCAL_PATH_LIFT_REACHED')
        self.assertEqual(r['point_world_cm'], [.5, 1.5, 0.])

    def test_edge_incidence_subset_cannot_claim_vertex_incidence(self):
        r = self.batch([self.query(seed_face_ids=[0, 3])])['rows'][0]
        self.assertEqual(r['reason'], 'SEED_FACE_INCIDENCES_DIFFER_FROM_DECLARED_DOMAIN')
        self.assertEqual(r['diagnostic']['actual_faces'], [0, 1, 2, 3])

    def test_vertex_hidden_native_nonmanifold_star_is_not_filtered_away(self):
        vertices = self.vertices + [[1., 1., 1.], [2., 1., 1.]]
        triangles = self.triangles + [[4, 5, 6]]
        r = planar(vertices, triangles, regions=[0, 0, 0, 0, 1]).trace(
            [4, 0], 0, [0, 1, 2, 3], [1.2, 1.6, .3], allow_vertex_seed=True)
        self.assertEqual(r['reason'], 'NONMANIFOLD_OR_DISCONNECTED_NATIVE_VERTEX_STAR')

    def test_vertex_nonmanifold_incident_edge_is_refused(self):
        vertices = self.vertices + [[1., 0., 1.]]
        triangles = self.triangles + [[4, 1, 5]]
        r = planar(vertices, triangles, regions=[0, 0, 0, 0, 1]).trace(
            [4, 0], 0, [0, 1, 2, 3], [1.2, 1.6, .3], allow_vertex_seed=True)
        self.assertEqual(r['reason'], 'NONMANIFOLD_VERTEX_STAR')

    def test_authorized_vertex_domain_must_be_connected(self):
        r = self.surface(regions=[0, 1, 0, 1]).trace(
            [4, 0], 0, [0, 2], [1.2, 1.6, .3], allow_vertex_seed=True)
        self.assertEqual(r['reason'], 'NONMANIFOLD_OR_DISCONNECTED_VERTEX_STAR')

    def test_entire_authorized_seed_fan_must_be_transverse(self):
        triangles = copy.deepcopy(self.triangles)
        triangles[0].reverse()
        r = planar(self.vertices, triangles).trace(
            [4, 0], 0, [0, 1, 2, 3], [1.2, 1.6, .3], allow_vertex_seed=True)
        self.assertEqual(r['reason'], 'FOLD_OR_GRAZING_IN_SEED_VERTEX_STAR')

    def test_path_on_two_outgoing_patches_stays_ambiguous(self):
        r = self.batch([self.query(target_world_cm=[1.5, 1.5, .3])])['rows'][0]
        self.assertEqual(r['reason'], 'SEED_HAS_NO_UNIQUE_TRANSVERSE_OUTGOING_PATCH')
        self.assertEqual(len(r['diagnostic']['outgoing']), 2)

    def test_zero_projected_vertex_path_and_missing_edge_are_refused(self):
        r = self.batch([self.query(target_world_cm=[1., 1., .3])])['rows'][0]
        self.assertEqual(r['reason'], 'ZERO_PROJECTED_PATH_NEEDS_SEED_NORMAL_CONE')
        r = self.surface().trace([1, 3], 0, [0, 1], [.5, 1.5, .3], allow_vertex_seed=True)
        self.assertEqual(r['reason'], 'MISSING_OR_NONMANIFOLD_SEED_EDGE')

    def test_v1_still_refuses_endpoints_and_v2_preserves_interior_behavior(self):
        r = planar().trace([0, 1], 0., [0], [.5, 1.5, .3])
        self.assertEqual(r['reason'], 'SEED_ENDPOINT_NOT_SUPPORTED_BY_EDGE_SEED_V1')
        rows = [planar().trace([0, 1], .5, [0], [.5, 1.5, .3], allow_vertex_seed=option)
                for option in (False, True)]
        for row in rows:
            row.pop('elapsed_seconds')
        self.assertEqual(*rows)
        self.assertEqual(self.batch([self.query(seed_face_ids=[0, 3])],
            method='SEEDED_SURFACE_PATH_LIFT_V1')['rows'][0]['reason'],
            'SEED_ENDPOINT_NOT_SUPPORTED_BY_EDGE_SEED_V1')

    def test_vertex_strict_arguments_and_face_count_bound(self):
        for changes in ({'seed_fraction': False}, {'seed_fraction': float('nan')},
                        {'seed_face_ids': [False, 1]}, {'seed_face_ids': list(range(MAX_VERTEX_SEED_FACES+1))},
                        {'seed_edge_vertex_ids': [False, 0]}):
            with self.subTest(changes=changes), self.assertRaises(StudioError):
                self.batch([self.query(**changes)])
        r = self.batch([self.query(seed_face_ids=[0, 1, 2, 2])])['rows'][0]
        self.assertEqual(r['reason'], 'INVALID_SEED_OR_TARGET')
        r = self.surface().trace([4, 0], 0, [0, 1, 2, 3], [1.2, 1.6, .3], allow_vertex_seed=1)
        self.assertEqual(r['reason'], 'INVALID_VERTEX_SEED_POLICY')

    def test_budget_exhaustion_inside_native_vertex_star_retains_refusal(self):
        r = self.surface(max_events=12).trace(
            [4, 0], 0, [0, 1, 2, 3], [1.2, 1.6, .3], allow_vertex_seed=True)
        self.assertEqual(r['reason'], 'WORK_BUDGET_EXHAUSTED')
        self.assertNotIn('point_world_cm', r)

    def test_vertex_batch_budget_is_cumulative(self):
        probe = self.surface()
        probe.trace([4, 0], 0, [0, 1, 2, 3], [1.2, 1.6, .3], allow_vertex_seed=True)
        result = self.batch([self.query(request_id=str(i)) for i in range(3)], max_events=probe.events)
        self.assertEqual(result['rows'][0]['status'], 'LOCAL_PATH_LIFT_REACHED')
        self.assertEqual(result['rows'][1]['reason'], 'WORK_BUDGET_EXHAUSTED')
        self.assertEqual(result['unprocessed_queries'], 1)

    def test_fraction_near_vertex_remains_exact_edge_interior(self):
        for fraction in (5e-324, 1.-2.**-53):
            with self.subTest(fraction=fraction):
                r = self.batch([self.query(seed_fraction=fraction, seed_face_ids=[0, 3])])['rows'][0]
                self.assertEqual(r['status'], 'LOCAL_PATH_LIFT_REACHED')
                self.assertNotIn('vertex_id', r['seed_incidence'])
                self.assertEqual(r['seed_incidence']['edge_fraction'], fraction)

    def test_time_budget_interrupts_vertex_star(self):
        class Clock:
            value = 0.
            def __call__(self):
                self.value += .125
                return self.value
        r = self.surface(max_seconds=1.5, clock=Clock()).trace(
            [4, 0], 0, [0, 1, 2, 3], [1.2, 1.6, .3], allow_vertex_seed=True)
        self.assertEqual(r['reason'], 'TIME_BUDGET_EXHAUSTED')
        self.assertNotIn('point_world_cm', r)

    def test_rotated_frame_and_vertex_subdivision_preserve_surface_point(self):
        target = [1.2, 1.6, .3]
        original = self.surface().trace([4, 0], 0, [0, 1, 2, 3], target, allow_vertex_seed=True)
        transform = lambda p: [p[2]+3., p[0]+5., p[1]+7.]
        rotated = Surface([transform(p) for p in self.vertices], self.triangles,
            [0, 1, 2, 3], [0]*4, [0], [1., 0., 0.]).trace(
                [4, 0], 0, [0, 1, 2, 3], transform(target), allow_vertex_seed=True)
        for a, b in zip(rotated['point_world_cm'], transform(original['point_world_cm'])):
            self.assertAlmostEqual(a, b)
        vertices = copy.deepcopy(self.vertices); triangles = []; owners = []
        for owner, tri in enumerate(self.triangles):
            mid = len(vertices)
            vertices.append([sum(vertices[i][k] for i in tri)/3 for k in range(3)])
            for a, b in zip(tri, tri[1:]+tri[:1]):
                triangles.append([a, b, mid]); owners.append(owner)
        refined = planar(vertices, triangles, owners, [0]*4).trace(
            [4, 0], 0, [0, 1, 2, 3], target, allow_vertex_seed=True)
        self.assertEqual(refined['selected_source_face'], original['selected_source_face'])
        self.assertEqual(refined['point_world_cm'], original['point_world_cm'])


if __name__ == '__main__':
    unittest.main()
