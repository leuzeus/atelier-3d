import copy
import math
import unittest
from unittest.mock import patch

from a3d.core import StudioError, digest
from a3d.contact_geometry import cross, dot
from a3d.guide_metric_solver import recover_guide_metric
from tests.test_guide_metric_solver import fixture, seamed_fixture


def surface_document(source, entry, piece_ids, requirements=None, *, trust=10.):
    """Independent supplied triangle patches; no native body origin is claimed."""
    indices = sorted(i for pid in piece_ids for i in source['panels'][pid]['indices'])
    requirements = requirements or {}
    vertices = []; faces = []; rows = []
    for index in indices:
        normal, required = requirements.get(index, ([0., 0., 1.], -1.))
        length = math.sqrt(dot(normal, normal)); normal = [x/length for x in normal]
        point = [entry[index][k]+required*normal[k] for k in range(3)]
        ref = [1., 0., 0.] if abs(normal[0]) < .8 else [0., 1., 0.]
        first = cross(ref, normal); size = math.sqrt(dot(first, first)); first = [x/size for x in first]
        second = cross(normal, first)
        triangle = [[point[k]-20*first[k]-20*second[k] for k in range(3)],
                    [point[k]+20*first[k]-20*second[k] for k in range(3)],
                    [point[k]+40*second[k] for k in range(3)]]
        tid = len(faces); start = len(vertices); vertices.extend(triangle); faces.append([start, start+1, start+2])
        rows.append({'id': 'sample.'+str(index), 'material_index': index,
                     'point_cm': point, 'normal_world': normal, 'clearance_cm': 0.,
                     'trust_radius_cm': trust, 'triangle_id': tid, 'barycentric': [1/3]*3, 'section_id': 'sampled'})
    body = {'vertices_cm': vertices, 'faces': faces, 'source_sha256': '1'*64, 'pose_sha256': '2'*64}
    identity = {'source_payload_sha256': digest(source), 'entry_coordinates_sha256': digest(entry),
                'body_geometry_sha256': digest([vertices, faces]), 'body_triangles_sha256': digest(faces),
                'body_source_sha256': body['source_sha256'], 'body_pose_sha256': body['pose_sha256']}
    body_identity = {k: v for k, v in identity.items() if k.startswith('body_')}
    return {'version': 1, 'identity': identity, 'body_geometry': body, 'body_triangles': copy.deepcopy(faces),
            'sections': {'sampled': {'status': 'MEASURED', 'body_identity_sha256': digest(body_identity),
                                     'triangle_ids': list(range(len(faces)))}},
            'material_indices': indices, 'rows': rows, 'weight': 10000., 'search_margin_cm': .01}


class ConstrainedGuideRecovery(unittest.TestCase):
    def solve(self, source, entry, quality, document, **options):
        return recover_guide_metric(source, entry, quality, ['panel'], [{'piece': 'panel', 'edge': 'anchor'}],
                                    surface_constraints=document, clock=lambda: 0., max_iterations=60, **options)

    def test_sufficient_material_bad_pose_recovers_metric_and_local_planes(self):
        source, _, quality = fixture(); entry = copy.deepcopy(source['rest_cm'])
        document = surface_document(source, entry, ['panel'], {1: ([0., 0., 1.], .2), 2: ([0., 0., 1.], .2)})
        before = digest([source, entry, quality, document]); result = self.solve(source, entry, quality, document)
        self.assertEqual(result['status'], 'SOURCE_METRIC_RECOVERED')
        self.assertTrue(result['initial_metric_valid']); self.assertTrue(result['combined_constraints_valid'])
        self.assertFalse(result['surface_constraints']['initial']['satisfied'])
        self.assertTrue(result['surface_constraints']['final']['satisfied'])
        self.assertGreaterEqual(result['coordinates_cm'][1][2], .2)
        self.assertEqual(result['coordinates_cm'][0], entry[0]); self.assertEqual(result['coordinates_cm'][3], entry[3])
        self.assertEqual(result['qualification'], 'NONE'); self.assertEqual(result['contacts'], 'NOT_ASSESSED')
        self.assertEqual(result['surface_constraints']['continuous_body_clearance'], 'NOT_QUALIFIED')
        self.assertEqual(before, digest([source, entry, quality, document]))

    def test_small_material_does_not_resize_or_gain_plane_metric_admission(self):
        source, _, quality = fixture(); entry = copy.deepcopy(source['rest_cm'])
        document = surface_document(source, entry, ['panel'], {1: ([1., 0., 0.], 2.), 2: ([1., 0., 0.], 2.)})
        before = digest(source); result = self.solve(source, entry, quality, document)
        self.assertEqual(result['status'], 'NEEDS_CORRECTION')
        self.assertFalse(result['combined_constraints_valid']); self.assertEqual(before, digest(source))
        self.assertFalse(result['surface_constraints']['final']['satisfied'] and
                         quality['min_stretch'] <= result['metric']['min_principal_stretch'] and
                         result['metric']['max_principal_stretch'] <= quality['max_stretch'])

    def test_same_material_circumference_distinct_local_shape_changes_recovered_guide(self):
        source, _, quality = fixture(); entry = copy.deepcopy(source['rest_cm']); source_sha = digest(source)
        results = []
        for height in (.12, .3):
            doc = surface_document(source, entry, ['panel'], {1: ([0., 0., 1.], height), 2: ([0., 0., 1.], height)})
            results.append(self.solve(source, entry, quality, doc))
        self.assertTrue(all(r['status'] == 'SOURCE_METRIC_RECOVERED' for r in results))
        self.assertNotEqual(results[0]['candidate_sha256'], results[1]['candidate_sha256'])
        self.assertEqual(source_sha, digest(source))

    def test_inclined_shoulder_normal_moves_only_free_material(self):
        source, _, quality = fixture(); entry = copy.deepcopy(source['rest_cm'])
        doc = surface_document(source, entry, ['panel'], {1: ([1., 0., 1.], .12), 2: ([1., 0., 1.], .12)})
        result = self.solve(source, entry, quality, doc)
        self.assertEqual(result['status'], 'SOURCE_METRIC_RECOVERED')
        self.assertGreater(result['coordinates_cm'][1][0], entry[1][0]); self.assertGreater(result['coordinates_cm'][1][2], 0.)
        self.assertEqual(result['coordinates_cm'][0], entry[0])

    def test_three_panels_preserve_transitive_cohort_and_source_parameters(self):
        source, entry, quality, edges = seamed_fixture(three=True)
        doc = surface_document(source, entry, ['a', 'b', 'c']); before = digest(source)
        result = recover_guide_metric(source, entry, quality, ['a', 'b', 'c'], edges,
            surface_constraints=doc, seam_ids=['ab', 'bc'], max_initial_seam_gap_cm=0.,
            anchor_scope='permanent_component', clock=lambda: 0., max_iterations=100)
        self.assertEqual(result['status'], 'SOURCE_METRIC_RECOVERED')
        for seam in source['seams'].values():
            for a, b in seam['pairs']:self.assertEqual(result['coordinates_cm'][a], result['coordinates_cm'][b])
        self.assertEqual(result['coordinates_cm'][2], result['coordinates_cm'][9])
        self.assertEqual(result['seam_coupling']['final_max_cohort_gap_cm'], 0.)
        self.assertEqual(before, digest(source))

    def test_fixed_anchor_incompatible_with_plane_stops_before_optimization(self):
        source, entry, quality = fixture(); doc = surface_document(source, entry, ['panel'], {0: ([0., 0., 1.], .2)})
        result = self.solve(source, entry, quality, doc)
        self.assertEqual(result['status'], 'NEEDS_CORRECTION')
        self.assertEqual(result['stop_reason'], 'INCOMPATIBLE_FIXED_SURFACE_CONSTRAINT')
        self.assertEqual(result['iterations'], 0); self.assertEqual(result['coordinates_cm'][0], entry[0])

    def test_missing_stale_nonfinite_and_contradictory_surface_provenance_refuses(self):
        source, entry, quality = fixture()
        for kind in ('coverage', 'row', 'identity', 'pose', 'section', 'normal', 'point', 'nonfinite', 'bool', 'winding'):
            doc = surface_document(source, entry, ['panel'])
            if kind == 'coverage':doc['material_indices'].pop()
            if kind == 'row':doc['rows'].pop()
            if kind == 'identity':doc['identity']['entry_coordinates_sha256'] = '3'*64
            if kind == 'pose':doc['body_geometry']['pose_sha256'] = '3'*64
            if kind == 'section':doc['sections']['sampled']['status'] = 'NOT_QUALIFIED'
            if kind == 'normal':doc['rows'][0]['normal_world'] = [0., 0., -1.]
            if kind == 'point':doc['rows'][0]['point_cm'][2] += .01
            if kind == 'nonfinite':doc['rows'][0]['clearance_cm'] = float('nan')
            if kind == 'bool':doc['rows'][0]['material_index'] = True
            if kind == 'winding':doc['body_triangles'][0].reverse()
            with self.subTest(kind=kind), self.assertRaises(StudioError):self.solve(source, entry, quality, doc)

    def test_entry_outside_trust_domain_refuses_and_tight_trust_never_gains_success(self):
        source, _, quality = fixture(); entry = copy.deepcopy(source['rest_cm'])
        doc = surface_document(source, entry, ['panel'], trust=.1)
        with self.assertRaisesRegex(StudioError, 'trust patch'):self.solve(source, entry, quality, doc)
        doc = surface_document(source, entry, ['panel'], {1: ([0., 0., 1.], .2), 2: ([0., 0., 1.], .2)})
        for row in doc['rows']:row['trust_radius_cm'] = .2 if row['material_index'] in (1, 2) else 1.1
        result = self.solve(source, entry, quality, doc)
        self.assertTrue(result['surface_constraints']['final']['trust_domain_valid'])
        if result['status'] == 'SOURCE_METRIC_RECOVERED':self.assertTrue(result['surface_constraints']['final']['satisfied'])

    def test_inactive_panel_preserved_and_optional_none_is_exact_legacy(self):
        source, entry, quality = fixture(); source['rest_cm'] += [[10., 0., 0.], [12., 0., 0.], [12., 2., 0.], [10., 2., 0.]]
        source['faces'] += [[4, 5, 6], [4, 6, 7]]; source['panels']['other'] = {'indices': [4, 5, 6, 7], 'edges': {'anchor': [4, 7]}}
        entry += [[x, y, 5.] for x, y, _ in source['rest_cm'][4:]]
        args = (source, entry, quality, ['panel'], [{'piece': 'panel', 'edge': 'anchor'}])
        legacy = recover_guide_metric(*args, clock=lambda: 0.)
        self.assertEqual(legacy, recover_guide_metric(*args, clock=lambda: 0., surface_constraints=None))
        self.assertNotIn('surface_constraints', legacy)
        doc = surface_document(source, entry, ['panel']); result = self.solve(source, entry, quality, doc)
        self.assertEqual(result['coordinates_cm'][4:], entry[4:])

    def test_metric_only_pass_with_tight_step_is_rejected_not_reported_recovered(self):
        source, _, quality = fixture(); entry = copy.deepcopy(source['rest_cm'])
        doc = surface_document(source, entry, ['panel'], {1: ([0., 0., 1.], .2), 2: ([0., 0., 1.], .2)})
        result = self.solve(source, entry, quality, doc, max_step_cm=.001)
        self.assertEqual(result['status'], 'NEEDS_CORRECTION')
        self.assertEqual(result['coordinates_cm'], entry); self.assertTrue(result['initial_metric_valid'])
        self.assertFalse(result['combined_constraints_valid'])

    def test_constraint_mutation_during_optimization_detected(self):
        source, entry, quality = fixture(); doc = surface_document(source, entry, ['panel'])
        from a3d import guide_metric_solver
        pcg = guide_metric_solver._pcg
        def mutate(*args, **kwargs):
            doc['rows'][0]['trust_radius_cm'] += .01
            return pcg(*args, **kwargs)
        with patch.object(guide_metric_solver, '_pcg', side_effect=mutate), self.assertRaisesRegex(StudioError, 'immutable input'):
            self.solve(source, entry, quality, doc)

    def test_explicit_opposite_planes_on_one_index_refuse_contradiction(self):
        source, entry, quality = fixture()
        doc = surface_document(source, entry, ['panel'], {1: ([0., 0., 1.], .2)})
        opposite = surface_document(source, entry, ['panel'], {1: ([0., 0., -1.], .2)})
        vertices = doc['body_geometry']['vertices_cm']; start = len(vertices)
        vertices.extend(opposite['body_geometry']['vertices_cm'][3:6])
        tid = len(doc['body_triangles']); triangle = [start, start+1, start+2]
        doc['body_geometry']['faces'].append(triangle); doc['body_triangles'].append(triangle[:])
        row = opposite['rows'][1]; row.update(id='opposite', triangle_id=tid); doc['rows'].append(row)
        doc['identity']['body_geometry_sha256'] = digest([vertices, doc['body_geometry']['faces']])
        doc['identity']['body_triangles_sha256'] = digest(doc['body_triangles'])
        body_identity = {k: v for k, v in doc['identity'].items() if k.startswith('body_')}
        doc['sections']['sampled']['body_identity_sha256'] = digest(body_identity)
        doc['sections']['sampled']['triangle_ids'].append(tid)
        with self.assertRaisesRegex(StudioError, 'contradictory opposite planes'):self.solve(source, entry, quality, doc)

    def test_trust_radius_blocks_required_material_relocation(self):
        source, entry, quality = fixture()
        doc = surface_document(source, entry, ['panel'], {i: ([0., 0., 1.], 0.) for i in range(4)}, trust=.1)
        result = self.solve(source, entry, quality, doc)
        self.assertEqual(result['status'], 'NEEDS_CORRECTION')
        self.assertTrue(result['surface_constraints']['final']['trust_domain_valid'])
        self.assertTrue(all(math.dist(point, row['point_cm']) <= .1
                            for point, row in zip(result['coordinates_cm'], doc['rows'])))

    def test_budget_exhaustion_cannot_admit_even_already_valid_metric(self):
        source, _, quality = fixture(); entry = copy.deepcopy(source['rest_cm'])
        doc = surface_document(source, entry, ['panel'])
        clock_state = [0.]
        def advancing_clock():
            clock_state[0] += .001
            return clock_state[0]
        with self.assertRaisesRegex(StudioError, 'deadline exhausted'):
            recover_guide_metric(source, entry, quality, ['panel'], [{'piece': 'panel', 'edge': 'anchor'}],
                                 surface_constraints=doc, clock=advancing_clock, max_seconds=.002)

    def test_deadline_during_pcg_preserves_best_candidate_and_local_snapshot(self):
        from a3d import guide_metric_solver
        source, entry, quality = fixture(); doc = surface_document(source, entry, ['panel'])
        state = [0.]; pcg = guide_metric_solver._pcg
        def expire(*args, **kwargs):
            state[0] = 2.
            return pcg(*args, **kwargs)
        with patch.object(guide_metric_solver, '_pcg', side_effect=expire):
            result = recover_guide_metric(source, entry, quality, ['panel'], [{'piece': 'panel', 'edge': 'anchor'}],
                                         surface_constraints=doc, clock=lambda: state[0], max_seconds=1.)
        self.assertEqual(result['status'], 'NEEDS_CORRECTION'); self.assertEqual(result['stop_reason'], 'TIME_BUDGET')
        self.assertEqual(result['coordinates_cm'], entry); self.assertFalse(result['combined_constraints_valid'])
        self.assertEqual(result['surface_constraints']['final']['coordinate_sha256'], result['candidate_sha256'])
        self.assertEqual(result['shared_deadline']['expired_phase'], 'pcg')

    def test_deadline_during_final_metric_validation_returns_bound_snapshot_no_readmission(self):
        import inspect
        from a3d import guide_metric_solver
        source, _, quality = fixture(); entry = copy.deepcopy(source['rest_cm'])
        doc = surface_document(source, entry, ['panel']); state = [0.]
        validator = guide_metric_solver.validate_metrics
        def expire_final(*args, **kwargs):
            try:return validator(*args, **kwargs)
            finally:
                functions = [frame.function for frame in inspect.stack()]
                if 'recover_guide_metric' in functions and '_metric_admitted' not in functions:state[0] = 2.
        with patch.object(guide_metric_solver, 'validate_metrics', side_effect=expire_final):
            result = recover_guide_metric(source, entry, quality, ['panel'], [{'piece': 'panel', 'edge': 'anchor'}],
                                         surface_constraints=doc, clock=lambda: state[0], max_seconds=1.)
        self.assertEqual(result['status'], 'NEEDS_CORRECTION'); self.assertEqual(result['stop_reason'], 'TIME_BUDGET')
        self.assertFalse(result['combined_constraints_valid']); self.assertTrue(result['surface_constraints']['final']['satisfied'])
        self.assertEqual(result['surface_constraints']['final']['coordinate_sha256'], result['candidate_sha256'])
        self.assertEqual(result['coordinates_cm'], entry)

    def test_surface_caps_refuse_before_full_input_digest_and_metric_work(self):
        from a3d import constrained_guide_recovery as local
        source, entry, quality = fixture()
        for kind in ('vertices', 'rows', 'face-edges', 'section-references', 'extra-body-metadata', 'long-id'):
            doc = surface_document(source, entry, ['panel'])
            if kind == 'vertices':doc['body_geometry']['vertices_cm'] = [[0., 0., 0.]]*(local.MAX_BODY_VERTICES+1)
            if kind == 'rows':doc['rows'] = [doc['rows'][0]]*(local.MAX_ROWS+1)
            if kind == 'face-edges':doc['body_geometry']['faces'] = [[0]*(local.MAX_BODY_FACE_EDGES+1)]
            if kind == 'section-references':
                section = copy.deepcopy(doc['sections']['sampled']); section['triangle_ids'] = [0]*local.MAX_BODY_TRIANGLES
                doc['sections'] = {str(i): section for i in range(4)}
            if kind == 'extra-body-metadata':doc['body_geometry']['unbounded'] = {'data': 'extra'}
            if kind == 'long-id':doc['rows'][0]['id'] = 'x'*129
            with self.subTest(kind=kind), patch('a3d.guide_metric_solver.digest', side_effect=AssertionError('premature hash')), \
                    patch('a3d.guide_metric_solver.evaluate_metrics', side_effect=AssertionError('premature metric')), \
                    self.assertRaises(StudioError):self.solve(source, entry, quality, doc)

    def test_terminal_immutable_hash_expiry_retains_coupled_best_without_admission(self):
        from a3d import guide_metric_solver
        source, _, quality, edges = seamed_fixture(); entry = copy.deepcopy(source['rest_cm'])
        doc = surface_document(source, entry, ['a', 'b']); state = [0.]; hashes = [0]
        original_digest = guide_metric_solver.digest
        def expire_last_hash(value):
            hashed = original_digest(value)
            if isinstance(value, list) and value and value[0] is source and value[-1] is doc:
                hashes[0] += 1
                if hashes[0] == 3:state[0] = 2.
            return hashed
        with patch.object(guide_metric_solver, 'digest', side_effect=expire_last_hash):
            result = recover_guide_metric(source, entry, quality, ['a', 'b'], edges,
                surface_constraints=doc, seam_ids=['ab'], max_initial_seam_gap_cm=0.,
                anchor_scope='permanent_component', clock=lambda: state[0], max_seconds=1.)
        self.assertEqual(hashes[0], 3)
        self.assertEqual(result['status'], 'NEEDS_CORRECTION'); self.assertEqual(result['stop_reason'], 'TIME_BUDGET')
        self.assertFalse(result['combined_constraints_valid']); self.assertTrue(result['initial_metric_valid'])
        self.assertTrue(result['surface_constraints']['final']['satisfied'])
        self.assertEqual(result['surface_constraints']['final']['coordinate_sha256'], result['candidate_sha256'])
        self.assertEqual(result['coordinates_cm'], entry); self.assertEqual(result['seam_coupling']['final_max_cohort_gap_cm'], 0.)
        self.assertEqual(result['elapsed_seconds'], 2.); self.assertEqual(result['shared_deadline']['finished'], 2.)
        self.assertTrue(result['shared_deadline']['expired'])
        self.assertEqual(result['shared_deadline']['expired_phase'], 'terminal_input_validation')


if __name__ == '__main__':
    unittest.main()
