"""Current sewing supports and verified native seeds, never fitting proof."""
import copy
import math
import unittest
from unittest.mock import patch

from a3d.core import StudioError, digest
from a3d.garment_guides import _source_limb_mesh
from a3d.source_boundary_bindings import prepare_source_boundary_bindings, METHOD
from tests.test_anatomical_placement import fixture as anatomy_fixture, rehash


def fixture(*, reverse=False, driver_side='a', ease=0., domain=True, rotated=False):
    profile, geometry, _, document, _ = anatomy_fixture(rotated=rotated, region='custom:measured-junction')
    width = 14.; partner_width = width*(1+ease)
    driver = {'vertices': [[0., 0.], [width, 0.], [width, 2.], [0., 2.]],
        'faces': [[0, 1, 2], [0, 2, 3]], 'edges': {'selected': [0, 1]}}
    partner = {'vertices': [[0., 0.], [partner_width*.3, 0.], [partner_width, 0.],
                            [partner_width, 3.], [0., 3.]],
        'faces': [[4, 0, 1], [4, 1, 2], [4, 2, 3]],
        'edges': {'selected': [2, 1, 0] if reverse else [0, 1, 2]}}
    seam = {'id': 'authored-relation', 'piece_a': 'alpha', 'edge_a': 'selected',
        'piece_b': 'beta', 'edge_b': 'selected', 'orientation': 'reverse' if reverse else 'forward', 'kind': 'permanent'}
    declared_ease = ease
    if driver_side == 'b':
        seam['piece_a'], seam['piece_b'] = seam['piece_b'], seam['piece_a']
        declared_ease = 1/(1+ease)-1
    data = {'component_id': 'arbitrary.component', 'units': 'cm',
        'pieces': {'alpha': driver, 'beta': partner}, 'seams': [seam]}
    frames = {}
    for index, (pid, piece) in enumerate(data['pieces'].items()):
        uv, triangles = _source_limb_mesh(piece, 1)
        local = [[p[0], float(index)*4, p[1]+10.] for p in uv]
        basis = profile['frame']
        world = [[basis['origin_cm'][k]+sum(p[j]*basis[axis][k] for j, axis in enumerate(('right','forward','up'))) for k in range(3)] for p in local]
        frames[pid] = {'source_ref': 'source-bound:candidate:'+pid, 'uv_cm': uv, 'triangles': triangles, 'target_cm': world}
    recipe = {'component_id': data['component_id'], 'seams': {'authored-relation':
        {'kind': 'permanent', 'ease_b_over_a': declared_ease, 'tolerance_relative': .02}}}
    document['pieces'] = {'alpha': {'guide_kind': 'PATH_BAND_V1', 'path_ref': 'chosen',
        'material_axis': 'u', 'source_anchor_edge': 'selected', 'source_anchor_fraction': 0.,
        'path_anchor_fraction': .125, 'path_direction': 1, 'max_path_expansion_ratio': 1.5}}
    if domain:
        document['pieces']['beta'] = {'surface_envelope': {'method': 'REGIONAL_SURFACE_ENVELOPE_V1',
            'source_region_ids': [10], 'direction_body': [0., 0., 1.], 'reserve_cm': .3, 'max_displacement_cm': 20.}}
    policy = {'version': 1, 'method': METHOD, 'driver_piece': 'alpha',
        'source_seam_ids': ['authored-relation'], 'ease_distribution': 'UNIFORM_NORMALIZED_SOURCE_ARC',
        'query_target_kind': 'CURRENT_PARTNER_BOUNDARY_TARGET', 'budgets': {'max_seconds': 15.}}
    return data, frames, recipe, profile, geometry, document, policy


def evaluate(frames, link):
    support = link['support']; frame = frames[link['piece']]
    return [math.fsum(w*frame['target_cm'][i][k] for i, w in zip(support['control_indices'], support['weights'])) for k in range(3)]


class SourceBoundaryBindings(unittest.TestCase):
    def test_joint_supports_keep_source_orientation_ease_and_current_candidate(self):
        for reverse in (False, True):
            for side in ('a', 'b'):
                args = fixture(reverse=reverse, driver_side=side, ease=.1)
                before = digest(args)
                result = prepare_source_boundary_bindings(*args)
                self.assertEqual(result['status'], 'SOURCE_BOUNDARY_BINDINGS_PREPARED')
                self.assertEqual(len(result['bindings']), 3)
                for row in result['bindings']:
                    a, b = row['driver'], row['partner']
                    for link in (a, b):
                        self.assertEqual(evaluate(args[1], link), link['support']['evaluated_world_cm'])
                        self.assertTrue(link['source_segment_owners'])
                    self.assertAlmostEqual(b['source_uv_cm'][0], a['source_uv_cm'][0]*1.1)
                    self.assertEqual(row['anatomical_query']['target_world_cm'], b['support']['evaluated_world_cm'])
                    self.assertFalse(row['fixed_anatomical_constraint_added'])
                self.assertEqual(digest(args), before)
                self.assertEqual(result['new_fixed_anatomical_constraints'], 0)

    def test_missing_domain_preserves_solver_supports_and_new_target_requires_new_identity(self):
        args = fixture(domain=False)
        first = prepare_source_boundary_bindings(*args)
        self.assertEqual(first['status'], 'PARTIAL_ANATOMICAL_INPUTS')
        self.assertTrue(all(row['anatomical_query'] is None for row in first['bindings']))
        self.assertTrue(all(row['sewing_support_status'] == 'BOTH_CURRENT_CAGE_SUPPORTS_PREPARED' for row in first['bindings']))
        changed = copy.deepcopy(args)
        for p in changed[1]['beta']['target_cm']: p[2] += .25
        second = prepare_source_boundary_bindings(*changed)
        self.assertNotEqual(first['binding_set_sha256'], second['binding_set_sha256'])
        self.assertNotEqual(first['identities']['frames_sha256'], second['identities']['frames_sha256'])
        self.assertEqual([r['body_seed'] for r in first['bindings']], [r['body_seed'] for r in second['bindings']])
        for a, b in zip(first['bindings'], second['bindings']):
            self.assertEqual(a['partner']['support']['weights'], b['partner']['support']['weights'])
            self.assertAlmostEqual(b['partner']['support']['evaluated_world_cm'][2]-a['partner']['support']['evaluated_world_cm'][2], .25)

    def test_explicit_query_target_and_reversed_body_path_are_independent(self):
        args = fixture()
        current = prepare_source_boundary_bindings(*args)
        args[-1]['query_target_kind'] = 'HOMOLOGOUS_DRIVER_BOUNDARY_TARGET'
        proposed = prepare_source_boundary_bindings(*args)
        for a, b in zip(current['bindings'], proposed['bindings']):
            self.assertEqual(a['body_seed'], b['body_seed'])
            self.assertEqual(b['anatomical_query']['target_world_cm'], b['driver']['support']['evaluated_world_cm'])
            self.assertNotEqual(a['anatomical_query']['target_world_cm'], b['anatomical_query']['target_world_cm'])
        args[-2]['pieces']['alpha']['path_direction'] = -1
        reverse = prepare_source_boundary_bindings(*args)
        self.assertNotEqual(proposed['bindings'][1]['body_seed']['path_fraction'], reverse['bindings'][1]['body_seed']['path_fraction'])

    def test_vertex_seed_keeps_full_domain_star_and_does_not_pick_outgoing_face(self):
        args = fixture()
        args[-2]['pieces']['alpha']['path_anchor_fraction'] = 0.
        args[-2]['pieces']['beta']['surface_envelope']['source_region_ids'] = [10, 20]
        result = prepare_source_boundary_bindings(*args)
        vertex_rows = [r for r in result['bindings'] if r['body_seed']['kind'] == 'NATIVE_VERTEX']
        self.assertEqual(len(vertex_rows), 2)
        for row in vertex_rows:
            self.assertEqual(row['body_seed']['edge_fraction'], 0.)
            self.assertEqual(row['anatomical_query']['seed_face_ids'], [0, 1])
            self.assertNotIn('selected_source_face', row['body_seed'])

    def test_rotated_body_frame_rotates_current_targets_and_declared_direction(self):
        original = prepare_source_boundary_bindings(*fixture())
        changed = prepare_source_boundary_bindings(*fixture(rotated=True))
        for a, b in zip(original['bindings'], changed['bindings']):
            p = a['anatomical_query']['target_world_cm']; q = b['anatomical_query']['target_world_cm']
            self.assertLess(math.dist(q, [20.+p[2], -7.+p[0], 53.+p[1]]), 1e-10)
            self.assertEqual(b['domain']['direction_world'], [1., 0., 0.])
            self.assertEqual(a['body_seed']['edge_vertex_ids'], b['body_seed']['edge_vertex_ids'])

    def test_bad_report_native_incidence_phase_seam_and_cage_are_refused(self):
        def bad_face(args):
            args[-2]['paths']['chosen']['report']['paths'][0]['edge_source_face_ids'][0] = [0]
            rehash(args[-2])
        changes = [bad_face,
            lambda a: a[-2]['pieces']['alpha'].update(path_direction=True),
            lambda a: a[-2]['pieces']['alpha'].update(path_anchor_fraction=float('nan')),
            lambda a: a[-1].update(source_seam_ids=['missing']),
            lambda a: a[-1].update(ease_distribution='INVENTED'),
            lambda a: a[-2]['pieces']['beta']['surface_envelope'].update(source_region_ids=[999]),
            lambda a: a[1]['alpha']['uv_cm'][0].__setitem__(0, .1),
            lambda a: a[1]['alpha'].update(source_ref=''),
            lambda a: a[4]['face_sets'].__setitem__(0, 30)]
        for change in changes:
            args = fixture(); change(args)
            with self.subTest(change=change), self.assertRaises(StudioError):
                prepare_source_boundary_bindings(*args)

    def test_shared_time_and_size_budgets_refuse_before_returning_solver_rows(self):
        args = fixture()
        args[-1]['budgets']['max_controls'] = 3
        with self.assertRaisesRegex(StudioError, 'budget'):
            prepare_source_boundary_bindings(*args)
        args = fixture(); ticks = iter(range(100000))
        with self.assertRaisesRegex(StudioError, 'time budget'):
            prepare_source_boundary_bindings(*args, clock=lambda: float(next(ticks)))
        args = fixture(); now = [0.]
        def late_hash(_):
            now[0] = 16.
            return 'e'*64
        with patch('a3d.source_boundary_bindings.sha', side_effect=late_hash):
            with self.assertRaisesRegex(StudioError, 'time budget'):
                prepare_source_boundary_bindings(*args, clock=lambda: now[0])

    def test_material_range_does_not_discard_an_unresolved_source_constraint(self):
        args = fixture()
        args[-2]['pieces']['beta']['surface_envelope']['source_v_range_cm'] = [1., 2.]
        result = prepare_source_boundary_bindings(*args)
        self.assertEqual(len(result['bindings']), 3)
        self.assertTrue(all(r['anatomical_query'] is None for r in result['bindings']))
        self.assertTrue(all(r['anatomical_query_status'] == 'PARTNER_MATERIAL_POINT_OUTSIDE_DECLARED_REGIONAL_RANGE' for r in result['bindings']))


if __name__ == '__main__': unittest.main()
