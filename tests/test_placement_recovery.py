"""Bounded offline recovery diagnostics cannot qualify a production candidate."""
import copy
import unittest

from a3d.core import StudioError, digest
from a3d.placement_recovery import diagnose_placement_recovery


def fixture():
    points = [[0., 0., 0.], [2., 0., 0.], [0., 2., 0.],
              [3., 0., 0.], [5., 0., 0.], [3., 2., 0.],
              [6., 0., 0.], [8., 0., 0.], [6., 2., 0.]]
    quality = dict(min_angle_degrees=15., min_edge_cm=.001, min_stretch=.9, max_stretch=1.1)
    seams = {'join': dict(piece_a='alpha', piece_b='beta', kind='permanent', pairs=[[1, 3]]),
             'open': dict(piece_a='beta', piece_b='gamma', kind='detachable', pairs=[[4, 6]])}
    source = dict(component_id='fixture.asset', pieces={p: {} for p in ('alpha', 'beta', 'gamma')},
                  seams=[dict(id=sid, **{k: seam[k] for k in ('piece_a', 'piece_b', 'kind')}) for sid, seam in seams.items()])
    recipe = dict(component_id='fixture.asset', mesh=copy.deepcopy(quality), placements={}, seams={}, pins={})
    specification = dict(quality=copy.deepcopy(quality), protected_indices=[1])
    preparation = dict(placement_correction=copy.deepcopy(specification), regular_mesh=dict(target_min_angle_degrees=15.))
    mesh = dict(component_id='fixture.asset', rest_cm=copy.deepcopy(points), placed_cm=copy.deepcopy(points),
                faces=[[0, 1, 2], [3, 4, 5], [6, 7, 8]],
                panels={p: dict(indices=list(range(i*3, i*3+3)), edges={'anchor': [i*3, i*3+1]})
                        for i, p in enumerate(('alpha', 'beta', 'gamma'))},
                seams=seams, pins={}, recipe_mesh_sha256=digest(recipe), source_garment_sha256=digest(source))
    correction = dict(coordinates_cm=copy.deepcopy(points), candidate_sha256=digest(points),
                      source_sha256='a'*64, effective_specification=copy.deepcopy(specification),
                      declared_specification_sha256=digest(specification),
                      measurement=dict(candidate_sha256=digest(points), hard_valid=False, score=.5,
                                       contacts=[], score_vertex_deficits_cm={'1': .5}))
    return dict(mesh=mesh, correction=correction, recipe=recipe, source=source, preparation=preparation)


def diagnose(values, **kwargs):
    return diagnose_placement_recovery(**values, expected_digests={k: digest(v) for k, v in values.items()},
        budgets=kwargs.pop('budgets', dict(max_vertices=100, max_faces=100, max_seam_pairs=100,
                                         max_contacts=100, max_seconds=10.)), **kwargs)


class PlacementRecoveryPreflight(unittest.TestCase):
    def test_exact_historical_defects_preserve_inputs_and_do_not_admit(self):
        values = fixture(); before = copy.deepcopy(values)
        result = diagnose(values)
        self.assertEqual(values, before)
        self.assertFalse(result['admitted']); self.assertEqual(result['qualification'], 'NONE')
        self.assertEqual(result['next_actions'], ['PREPARE_ADMISSIBLE_GUIDE_ANCHORS'])
        self.assertEqual(result['protected_anchors']['deficits'], [dict(vertex=1, piece='alpha', search_deficit_cm=.5)])
        self.assertIn('NOT_PENETRATION_DEPTH', result['search_deficit_scope'])

    def test_only_actual_permanent_pairs_union(self):
        result = diagnose(fixture())
        self.assertEqual([v['vertices'] for v in result['permanent_vertex_cohorts']], [[1, 3]])
        self.assertEqual(result['permanent_vertex_cohorts'][0]['protected_vertices'], [1])

    def test_clear_case_is_only_permission_to_prepare_bounded_search(self):
        values = fixture(); values['correction']['measurement']['score_vertex_deficits_cm'] = {}
        values['correction']['measurement']['hard_valid'] = True
        result = diagnose(values)
        self.assertEqual(result['next_actions'], ['RUN_BOUNDED_RECOVERY'])
        self.assertFalse(result['admitted']); self.assertEqual(result['status'], 'DIAGNOSTIC_ONLY')

    def test_sliver_and_protected_support_both_require_repairs(self):
        values = fixture(); values['mesh']['rest_cm'][2] = [1., .01, 0.]
        result = diagnose(values)
        self.assertEqual(result['next_actions'], ['REMESH_DERIVED_REST', 'PREPARE_ADMISSIBLE_GUIDE_ANCHORS'])
        self.assertEqual(result['source_rest']['worst_face']['piece'], 'alpha')
        self.assertEqual(result['source_rest']['angle_threshold_degrees'], 15.)
        self.assertLess(result['source_rest']['worst_face']['min_angle_degrees'], 1.)
        self.assertFalse(result['admitted'])

    def test_changed_whole_mesh_identity_is_refused(self):
        values = fixture(); expected = {k: digest(v) for k, v in values.items()}
        values['mesh']['rest_cm'][0][0] += .01
        with self.assertRaisesRegex(StudioError, 'changed mesh input identity'):
            diagnose_placement_recovery(**values, expected_digests=expected,
                budgets=dict(max_vertices=100, max_faces=100, max_seam_pairs=100, max_contacts=100, max_seconds=10.))

    def test_stale_candidate_or_measurement_is_refused(self):
        for field in ('candidate_sha256',):
            values = fixture(); values['correction'][field] = '0'*64
            with self.assertRaisesRegex(StudioError, 'stale candidate'):
                diagnose(values)
        values = fixture(); values['correction']['measurement']['candidate_sha256'] = '0'*64
        with self.assertRaisesRegex(StudioError, 'stale candidate'):
            diagnose(values)

    def test_changed_source_and_recipe_are_refused(self):
        for category in ('source', 'recipe'):
            values = fixture(); values[category]['extra'] = 'changed'
            # Recipe identity excludes non-mesh metadata; change its actual mesh policy.
            if category == 'recipe': values['recipe']['mesh']['min_angle_degrees'] = 16.
            with self.assertRaises(StudioError): diagnose(values)

    def test_invalid_and_nonfinite_indices_coordinates_are_refused(self):
        changes = [lambda v: v['mesh']['faces'][0].__setitem__(0, -1),
                   lambda v: v['mesh']['faces'][0].__setitem__(0, True),
                   lambda v: v['mesh']['rest_cm'][0].__setitem__(0, float('inf')),
                   lambda v: v['mesh']['panels']['alpha']['indices'].append(3),
                   lambda v: v['mesh']['seams']['join']['pairs'][0].__setitem__(1, 6)]
        for change in changes:
            values = fixture(); expected = {k: digest(v) for k, v in values.items()}; change(values)
            with self.assertRaises(StudioError):
                diagnose_placement_recovery(**values, expected_digests=expected,
                    budgets=dict(max_vertices=100, max_faces=100, max_seam_pairs=100, max_contacts=100, max_seconds=10.))

    def test_explicit_count_and_time_budgets_are_enforced(self):
        for key, limit in (('max_vertices', 2), ('max_faces', 2), ('max_seam_pairs', 1)):
            budget = dict(max_vertices=100, max_faces=100, max_seam_pairs=100, max_contacts=100, max_seconds=10.)
            budget[key] = limit
            with self.assertRaisesRegex(StudioError, 'budget'): diagnose(fixture(), budgets=budget)
        ticks = iter((0., 20.))
        with self.assertRaisesRegex(StudioError, 'time budget'): diagnose(fixture(), clock=lambda: next(ticks))

    def test_declared_angle_threshold_cannot_be_lowered(self):
        values = fixture(); values['correction']['effective_specification']['quality']['min_angle_degrees'] = 2.
        with self.assertRaisesRegex(StudioError, 'lowered'): diagnose(values)

    def test_omitted_protected_anchor_cannot_start_recovery(self):
        values = fixture(); values['correction']['effective_specification']['protected_indices'] = []
        with self.assertRaisesRegex(StudioError, 'protected support omitted'): diagnose(values)

    def test_malformed_nested_indices_and_source_triangles_are_refused(self):
        values = fixture(); values['mesh']['faces'][0][0] = []
        expected = {k: digest(v) for k, v in values.items()}
        with self.assertRaisesRegex(StudioError, 'invalid triangle indices'):
            diagnose_placement_recovery(**values, expected_digests=expected,
                budgets=dict(max_vertices=100, max_faces=100, max_seam_pairs=100, max_contacts=100, max_seconds=10.))
        values = fixture(); values['mesh']['source_rest_triangles_cm'] = [[['bad'], [0, 1], [1, 0]]] * 3
        with self.assertRaisesRegex(StudioError, 'invalid source rest triangle'): diagnose(values)

    def test_unknown_relation_and_missing_shapes_are_refused(self):
        values = fixture(); del values['source']['seams'][0]['kind']
        with self.assertRaisesRegex(StudioError, 'relation changed'): diagnose(values)
        values = fixture(); del values['correction']['measurement']
        with self.assertRaisesRegex(StudioError, 'measurement required'): diagnose(values)

    def test_nonfinite_unknown_metadata_cannot_get_an_identity(self):
        values = fixture(); expected = {k: digest(v) for k, v in values.items()}
        values['source']['unknown'] = float('nan')
        with self.assertRaisesRegex(StudioError, 'nonfinite or non-JSON'):
            diagnose_placement_recovery(**values, expected_digests=expected,
                budgets=dict(max_vertices=100, max_faces=100, max_seam_pairs=100, max_contacts=100, max_seconds=10.))


if __name__ == '__main__':
    unittest.main()
