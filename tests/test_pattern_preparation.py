import copy
import math
import unittest

from a3d.core import StudioError, digest
from a3d.pattern_preparation import (assess_preparation, audit_source,
    preparation_statistics, prepare_regular_boundaries, regular_interior_points)
from a3d.sewing import point_inside, edge_chain, sample_chain, prepare_boundaries
from tests.test_pattern_assembly import example
from tests.test_sewing import sources


def source_dossier(data):
    pieces = []
    for pid, piece in data['pieces'].items():
        x0, x1 = min(p[0] for p in piece['vertices']), max(p[0] for p in piece['vertices'])
        y0, y1 = min(p[1] for p in piece['vertices']), max(p[1] for p in piece['vertices'])
        pieces.append({'id': pid, 'grain_direction': [0, 1], 'seam_allowance_cm': 1,
            'pattern': {'cut_outline_cm': [[x0-1, y0-1], [x1+1, y0-1], [x1+1, y1+1], [x0-1, y1+1]],
                'assembly_marks': [{'id': 'notch-'+s['id'], 'seam_id': s['id'], 'symbol': 'notch',
                    'position': .7 if pid == s['piece_b'] and s['orientation'] == 'reverse' else .3}
                    for s in data['seams'] if pid in (s['piece_a'], s['piece_b'])]}})
    return {'units': 'cm', 'components': {data['component_id']: {'pieces': pieces}}}


class SourcePreparation(unittest.TestCase):
    def test_source_audit_preserves_patterns_and_reuses_sourced_notches(self):
        data, recipe = sources()
        dossier = source_dossier(data)
        before = digest([data, recipe, dossier])
        report = audit_source(data, recipe, dossier)
        self.assertEqual(report['status'], 'SOURCE_AUDITED', report['issues'])
        self.assertEqual(before, digest([data, recipe, dossier]))
        self.assertTrue(report['source_immutable'])
        self.assertEqual(report['qualification'], 'NONE')
        self.assertTrue(all(s['notches'] for s in report['seams']))
        self.assertTrue(all(s['stops_source'] == 'named_source_edge_endpoints' for s in report['seams']))

    def test_absent_metadata_is_clarification_and_does_not_invent_a_cut_defect(self):
        data, recipe = sources()
        report = audit_source(data, recipe)
        self.assertEqual(report['status'], 'NEEDS_CLARIFICATION')
        self.assertEqual({i['category'] for i in report['issues']}, {'missing_metadata'})
        self.assertTrue(all(p['grain_direction'] is None for p in report['panels'].values()))

    def test_bad_notch_orientation_is_identified_and_not_repaired(self):
        data, recipe = sources()
        dossier = source_dossier(data)
        target = next(p for p in dossier['components'][data['component_id']]['pieces'] if p['id'] == data['seams'][0]['piece_b'])
        target['pattern']['assembly_marks'][0]['position'] = .4
        before = digest(dossier)
        report = audit_source(data, recipe, dossier)
        self.assertIn('NOTCH_ORIENTATION_CONFLICT', [i['code'] for i in report['issues']])
        self.assertEqual(report['status'], 'NEEDS_CORRECTION')
        self.assertEqual(digest(dossier), before)

    def test_units_contour_and_declared_ease_are_separate_defects(self):
        data, recipe = sources()
        data['units'] = 'm'
        self.assertEqual(audit_source(data, recipe)['issues'][0]['code'], 'SOURCE_CONTRACT')
        data, recipe = sources()
        data['pieces']['front']['vertices'][1], data['pieces']['front']['vertices'][2] = data['pieces']['front']['vertices'][2], data['pieces']['front']['vertices'][1]
        report = audit_source(data, recipe)
        self.assertIn('INVALID_SOURCE_CONTOUR', [i['code'] for i in report['issues']])
        data, recipe = sources()
        recipe['seams'][data['seams'][0]['id']]['ease_b_over_a'] = .1
        report = audit_source(data, recipe)
        conflict = next(i for i in report['issues'] if i['code'] == 'SEAM_LENGTH_OR_EASE_CONFLICT')
        self.assertEqual(conflict['category'], 'cut_or_assembly_spec_conflict')


class RegularMeshing(unittest.TestCase):
    config = {'spacing_cm': 2., 'min_spacing_cm': .5, 'refinement_distance_cm': .5, 'max_vertices': 4000}

    def test_nested_lattice_is_deterministic_graded_and_inside_contour(self):
        boundary = {'polygon': [[0, 0], [20, 0], [20, 20], [0, 20]]}
        before = digest(boundary)
        points, report = regular_interior_points(boundary, self.config)
        again, repeated = regular_interior_points(boundary, self.config)
        self.assertEqual(points, again)
        self.assertEqual(report, repeated)
        self.assertTrue(all(point_inside(p, boundary['polygon']) for p in points))
        self.assertEqual(len(points), len(set(map(tuple, points))))
        self.assertGreater(len(report['levels']), 1)
        self.assertEqual(digest(boundary), before)
        self.assertEqual(report['triangulation'], 'requires_native_constrained_delaunay')

    def test_lattice_budgets_refuse_before_generating_unbounded_grids(self):
        boundary = {'polygon': [[0, 0], [2000, 0], [2000, 2000], [0, 2000]]}
        with self.assertRaisesRegex(StudioError, 'candidate count'):
            regular_interior_points(boundary, self.config)
        with self.assertRaisesRegex(StudioError, 'metric budget'):
            regular_interior_points(boundary, {**self.config, 'min_spacing_cm': 3.})

    def test_shared_arc_boundaries_reuse_ids_ease_and_source_immutability(self):
        data, recipe = sources()
        before = digest([data, recipe])
        boundaries, seams, report = prepare_regular_boundaries(data, recipe, self.config)
        self.assertEqual(digest([data, recipe]), before)
        self.assertEqual(report['sampling'], 'existing_common_source_arclength')
        self.assertEqual(set(seams), {s['id'] for s in data['seams']})
        for sid, seam in seams.items():
            self.assertEqual(len(seam['a']), len(seam['b']))
            self.assertEqual(len(seam['a']), len(seam['parameters']))
            self.assertEqual(seam['kind'], recipe['seams'][sid]['kind'])
        self.assertEqual(set(boundaries), set(data['pieces']))

    def test_unequal_source_counts_keep_exact_paired_notches_and_end_stops(self):
        data, recipe = sources()
        piece = data['pieces']['front']
        piece['vertices'].insert(2, [20, 20])
        piece['edges'] = {'right': [1, 2, 3], 'left': [0, 4], 'top': [4, 3]}
        # Legacy source faces are not used to triangulate the new simulation map.
        piece['faces'] = [[0, 1, 2], [0, 2, 3], [0, 3, 4]]
        dossier = source_dossier(data)
        before = digest([data, recipe, dossier])
        boundaries, seams, report = prepare_regular_boundaries(data, recipe, self.config, dossier)
        self.assertEqual(before, digest([data, recipe, dossier]))
        self.assertTrue(report['source_notches'])
        source = {s['id']: s for s in data['seams']}
        for notch in report['source_notches']:
            sid, side = notch['seam_id'], notch['side']
            seam = seams[sid]
            self.assertAlmostEqual(seam['parameters'][notch['common_sample']], .3)
            original = source[sid]
            pid = original['piece_'+side]
            _, chain, _ = edge_chain(data['pieces'][pid], original['edge_'+side])
            expected = sample_chain(chain, notch['source_local_parameter'])
            observed = boundaries[pid]['polygon'][notch['derived_boundary_vertex']]
            self.assertLess(math.dist(expected, observed), 1e-8)
        self.assertTrue(all(s['parameters'][0] == 0 and s['parameters'][-1] == 1 for s in seams.values()))

    def test_additional_arc_parameters_cannot_hide_wrong_topology_or_unknown_ids(self):
        data, recipe = sources()
        with self.assertRaisesRegex(StudioError, 'existing source seam IDs'):
            prepare_boundaries(data, recipe, {'missing': [.3]})
        with self.assertRaisesRegex(StudioError, 'normalized'):
            prepare_boundaries(data, recipe, {data['seams'][0]['id']: [1.01]})
        data['seams'] = [
            {'id': 'one', 'piece_a': 'front', 'edge_a': 'right', 'piece_b': 'back', 'edge_b': 'left', 'orientation': 'forward'},
            {'id': 'two', 'piece_a': 'front', 'edge_a': 'left', 'piece_b': 'back', 'edge_b': 'right', 'orientation': 'reverse'}]
        recipe['seams'] = {s['id']: {'kind': 'permanent', 'ease_b_over_a': 0, 'tolerance_relative': .01} for s in data['seams']}
        recipe['trial_pieces'] = ['front', 'back']
        with self.assertRaisesRegex(StudioError, 'Contradictory permanent seam orientation'):
            prepare_regular_boundaries(data, recipe, self.config)

    def test_forward_self_seam_keeps_one_notch_parameter_on_both_distinct_edges(self):
        data, recipe = sources()
        data['seams'] = [{'id': 'self', 'piece_a': 'front', 'edge_a': 'left',
                         'piece_b': 'front', 'edge_b': 'right', 'orientation': 'forward'}]
        recipe['seams'] = {'self': {'kind': 'permanent', 'ease_b_over_a': 0, 'tolerance_relative': .01}}
        recipe['trial_pieces'] = ['front', 'back']
        dossier = source_dossier(data)
        self.assertEqual(audit_source(data, recipe, dossier)['status'], 'SOURCE_AUDITED')
        boundaries, seams, report = prepare_regular_boundaries(data, recipe, self.config, dossier)
        self.assertEqual(len(report['source_notches']), 2)
        self.assertEqual({n['side'] for n in report['source_notches']}, {'a', 'b'})
        self.assertFalse(report['ambiguous_source_notches'])
        a, b = report['source_notches']
        self.assertEqual(a['common_parameter'], b['common_parameter'])
        self.assertNotEqual(a['derived_boundary_vertex'], b['derived_boundary_vertex'])


class PreparationStatistics(unittest.TestCase):
    def fixture(self):
        payload, assembly = example()
        from a3d.pattern_assembly import preform_coordinates
        payload['placed_cm'], _ = preform_coordinates(payload, assembly)
        recipe = {'mesh': assembly['quality'], 'mass': {'basis': 'areal_density_kg_m2', 'value': .3}, 'colliders': []}
        source_audit = {'status': 'SOURCE_AUDITED', 'source_sha256': payload['source_garment_sha256'], 'issues': []}
        return payload, recipe, source_audit

    def test_extruded_cylinder_has_bending_without_source_metric_stretch(self):
        # Each strip is rigidly folded about its vertical edge. The cylinder is
        # polygonal: unit chords equal the flat strip widths exactly.
        strips, turn = 8, math.pi/12
        radius = 1/(2*math.sin(turn/2))
        rest = [[float(i), v, 0.] for v in (0., 3.) for i in range(strips+1)]
        coords = [[radius*math.sin(i*turn), v, radius*math.cos(i*turn)]
                  for v in (0., 3.) for i in range(strips+1)]
        faces = []
        for i in range(strips):
            a, b, c, d = i, i+1, i+strips+1, i+strips+2
            faces.extend(([a, b, d], [a, d, c]))
        payload = {'rest_cm': rest, 'placed_cm': coords, 'faces': faces,
                   'panels': {'wrapped': {'indices': list(range(len(rest)))}}, 'seams': {},
                   'source_garment_sha256': 'metric-cylinder-fixture'}
        before = digest(payload)
        flat = preparation_statistics(payload, coords=rest)
        curved = preparation_statistics(payload)
        self.assertEqual(digest(payload), before)
        self.assertEqual(flat['bending']['placed_dihedral_degrees']['max'], 0.)
        bending = curved['bending']
        self.assertEqual(bending['metric'], 'GEOMETRIC_3D_DIHEDRAL_NOT_PHYSICAL')
        self.assertEqual(bending['placed_dihedral_degrees']['count'], 2*strips-1)
        self.assertAlmostEqual(bending['placed_dihedral_degrees']['max'], 15., places=10)
        self.assertGreater(bending['placed_dihedral_degrees']['p95'], 14.9)
        self.assertEqual(bending['source_dihedral_degrees']['max'], 0.)
        self.assertEqual(curved['per_piece']['wrapped']['bending']['placed_dihedral_degrees'],
                         bending['placed_dihedral_degrees'])
        for name in ('min_principal_stretch', 'max_principal_stretch'):
            self.assertAlmostEqual(curved['extrema'][name]['value'], 1., places=10)
        recipe = {'mesh': {'min_angle_degrees': 2., 'min_edge_cm': .01,
                          'min_stretch': .8, 'max_stretch': 1.25},
                  'mass': {'basis': 'total_kg', 'value': .3}, 'colliders': []}
        audit = {'source_sha256': payload['source_garment_sha256'], 'issues': []}
        admission = assess_preparation(payload, recipe, source_audit=audit)
        self.assertEqual(admission['status'], 'READY')
        self.assertFalse(admission['cloth_executed'])
        self.assertFalse(admission['accepted'])
        self.assertEqual(admission['statistics']['bending']['qualification'], 'NONE')

    def test_oriented_dihedral_keeps_folded_back_faces_and_excludes_panel_interfaces(self):
        payload = {'rest_cm': [[0., 0., 0.], [1., 0., 0.], [1., 1., 0.], [0., 1., 0.]],
                   'placed_cm': [[0., 0., 0.], [1., 0., 0.], [1., 1., 0.], [1., 0., 0.]],
                   'faces': [[0, 1, 2], [0, 2, 3]],
                   'panels': {'folded': {'indices': [0, 1, 2, 3]}}, 'seams': {}}
        report = preparation_statistics(payload)
        self.assertAlmostEqual(report['bending']['placed_dihedral_degrees']['max'], 180.)
        self.assertEqual(report['bending']['source_dihedral_degrees']['max'], 0.)
        self.assertEqual(report['bending']['excluded_edges']['open_boundary'], 4)
        payload['panels'] = {'one': {'indices': [0, 1, 2]}, 'two': {'indices': [0, 2, 3]}}
        report = preparation_statistics(payload)
        self.assertEqual(report['bending']['placed_dihedral_degrees']['count'], 0)
        self.assertEqual(report['bending']['excluded_edges']['panel_interface_or_ambiguous'], 1)
        self.assertTrue(all(p['bending']['placed_dihedral_degrees']['count'] == 0
                            for p in report['per_piece'].values()))

    def test_bending_excludes_degenerate_faces_and_does_not_repair_wrong_winding(self):
        payload, _, _ = self.fixture()
        payload['placed_cm'][0] = payload['placed_cm'][1][:]
        report = preparation_statistics(payload)
        self.assertGreater(report['invalid_face_count'], 0)
        self.assertGreater(report['bending']['excluded_edges']['degenerate_face'], 0)
        payload, recipe, audit = self.fixture()
        payload['faces'][1].reverse()
        report = assess_preparation(payload, recipe, source_audit=audit)
        self.assertEqual(report['status'], 'NEEDS_CORRECTION')
        self.assertIn('DERIVED_TOPOLOGY', {issue['code'] for issue in report['reasons']})
        self.assertGreater(report['statistics']['bending']['excluded_edges']['inconsistent_orientation'], 0)

    def test_source_face_metrics_mass_and_localized_extrema_are_conserved(self):
        payload, recipe, audit = self.fixture()
        before = digest(payload)
        result = preparation_statistics(payload, mass=recipe['mass'])
        self.assertEqual(digest(payload), before)
        self.assertAlmostEqual(result['source_area_cm2'], 8.)
        self.assertAlmostEqual(result['mass']['total_mass_kg'], .00024)
        self.assertAlmostEqual(sum(result['mass']['ideal_areal_vertex_mass_kg']), .00024)
        self.assertTrue(result['mass']['source_area_mass_conserved'])
        self.assertEqual(result['mass']['vertex_group_mass_semantics'], 'pin_weights_not_density')
        self.assertGreater(result['mass']['uniform_assignment_relative_local_density_error']['max'], 0)
        extreme = result['extrema']['max_principal_stretch']
        self.assertEqual(extreme['piece'], 'left')
        self.assertEqual(len(extreme['source_uv_cm']), 3)
        self.assertAlmostEqual(extreme['value'], 1.)
        self.assertEqual(result['source_rest_triangles_cm'][2], [[0, 0], [2, 0], [2, 2]])
        self.assertEqual(result['per_piece']['left']['source_dimensions_cm'], [2, 2])
        self.assertAlmostEqual(result['per_seam']['join']['worst_pair']['gap_cm'], .3)
        self.assertIn('source_uv_a_cm', result['per_seam']['join']['worst_pair'])
        self.assertTrue(result['topology']['vertex_manifold'])
        readiness = assess_preparation(payload, recipe, source_audit=audit)
        self.assertEqual(readiness['status'], 'READY')
        self.assertFalse(readiness['cloth_executed'])
        self.assertFalse(readiness['accepted'])

    def test_principal_strain_detects_shear_and_localizes_the_affected_face(self):
        payload, recipe, audit = self.fixture()
        for i in payload['panels']['left']['indices']:
            payload['placed_cm'][i][0] += .4*payload['placed_cm'][i][1]
        recipe['mesh']['max_stretch'] = 1.1
        report = assess_preparation(payload, recipe, source_audit=audit)
        self.assertEqual(report['status'], 'NEEDS_CORRECTION')
        issue = next(i for i in report['reasons'] if i['code'] == 'MAX_PRINCIPAL_STRETCH')
        self.assertEqual(issue['category'], 'placement')
        self.assertEqual(issue['observed']['piece'], 'left')
        self.assertGreater(issue['observed']['value'], 1.2)

    def test_missing_evidence_contact_and_invalid_geometry_are_distinct(self):
        payload, recipe, audit = self.fixture()
        recipe['colliders'] = [{'object': 'body'}]
        report = assess_preparation(payload, recipe, source_audit=audit)
        self.assertEqual(report['status'], 'NEEDS_CLARIFICATION')
        self.assertEqual(report['reasons'][0]['code'], 'COLLISION_EVIDENCE_MISSING')
        report = assess_preparation(payload, recipe, source_audit=audit,
            collision_report={'ok': False, 'penetration_cm': 7.8})
        self.assertEqual(report['status'], 'NEEDS_CORRECTION')
        self.assertEqual(report['reasons'][0]['code'], 'PLACEMENT_CONTACT')
        payload['placed_cm'][0] = payload['placed_cm'][1][:]
        stats = preparation_statistics(payload, mass=recipe['mass'])
        self.assertGreater(stats['invalid_face_count'], 0)
        self.assertEqual(stats['invalid_faces'][0]['piece'], 'left')

    def test_source_audit_binding_and_native_total_mass_basis(self):
        payload, recipe, audit = self.fixture()
        audit['source_sha256'] = 'different'
        report = assess_preparation(payload, recipe, source_audit=audit)
        self.assertEqual(report['status'], 'NEEDS_CORRECTION')
        self.assertIn('SOURCE_AUDIT_STALE', [i['code'] for i in report['reasons']])
        stats = preparation_statistics(payload, mass={'basis': 'total_kg', 'value': .2})
        self.assertAlmostEqual(stats['mass']['total_mass_kg'], .2)
        self.assertAlmostEqual(stats['mass']['areal_density_kg_m2'], 250.)

    def test_rotation_preserves_source_and_placement_metrics(self):
        payload, recipe, _ = self.fixture()
        before = preparation_statistics(payload, mass=recipe['mass'])
        coords = [[12+p[1], -6+p[2], 10+p[0]] for p in payload['placed_cm']]
        after = preparation_statistics(payload, coords=coords, mass=recipe['mass'])
        for key in ('min_principal_stretch', 'max_principal_stretch', 'max_placed_aspect_ratio'):
            self.assertAlmostEqual(before['extrema'][key]['value'], after['extrema'][key]['value'])
        self.assertEqual(before['source_rest_triangles_cm'], after['source_rest_triangles_cm'])

    def test_nonmanifold_derived_candidate_is_never_ready(self):
        payload, recipe, audit = self.fixture()
        payload['faces'].append(payload['faces'][0][:])
        report = assess_preparation(payload, recipe, source_audit=audit)
        self.assertEqual(report['status'], 'NEEDS_CORRECTION')
        self.assertIn('DERIVED_TOPOLOGY', [i['code'] for i in report['reasons']])
        self.assertEqual(report['statistics']['topology']['duplicate_face_count'], 1)

    def test_plan_cannot_relax_recipe_principal_strain_hidden_by_edge_ratios(self):
        payload, recipe, audit = self.fixture()
        c, s = math.cos(math.pi/8), math.sin(math.pi/8)
        a, b, d = 1.3*c*c+.85*s*s, (1.3-.85)*c*s, 1.3*s*s+.85*c*c
        for i in payload['panels']['left']['indices']:
            x, y, z = payload['placed_cm'][i]
            payload['placed_cm'][i] = [a*x+b*y, b*x+d*y, z]
        plan = {'quality': {**recipe['mesh'], 'max_stretch': 1.5, 'min_stretch': .5}}
        report = assess_preparation(payload, recipe, plan, source_audit=audit)
        self.assertLess(report['statistics']['extrema']['max_edge_stretch']['value'], 1.25)
        self.assertAlmostEqual(report['statistics']['extrema']['max_principal_stretch']['value'], 1.3)
        self.assertEqual(report['status'], 'NEEDS_CORRECTION')
        self.assertIn('MAX_PRINCIPAL_STRETCH', [i['code'] for i in report['reasons']])
        self.assertEqual(report['effective_quality_limits']['max_stretch'], 1.25)

    def test_requested_extreme_compression_and_stretch_are_localized_without_source_or_support_changes(self):
        payload, recipe, audit = self.fixture()
        payload['pins'] = {'1': .8, '2': .3, '7': .6}
        original = copy.deepcopy(payload)
        candidate = copy.deepcopy(payload)
        for i in candidate['panels']['left']['indices']:
            u, v = candidate['rest_cm'][i][:2]
            candidate['placed_cm'][i] = [.24*u, 2.86*v, 0.]
        report = assess_preparation(candidate, recipe, source_audit=audit)
        self.assertEqual(report['status'], 'NEEDS_CORRECTION')
        codes = {item['code'] for item in report['reasons']}
        self.assertTrue({'MIN_PRINCIPAL_STRETCH', 'MAX_PRINCIPAL_STRETCH'} <= codes)
        for metric, expected in (('min_principal_stretch', .24), ('max_principal_stretch', 2.86)):
            extreme = report['statistics']['extrema'][metric]
            self.assertAlmostEqual(extreme['value'], expected, places=12)
            self.assertEqual(extreme['piece'], 'left')
            self.assertIn(extreme['face'], (0, 1))
            self.assertEqual(extreme['source_uv_cm'], [original['rest_cm'][i][:2]
                for i in original['faces'][extreme['face']]])
        # World translation and an unrelated current-map index permutation must
        # not swap anatomical ownership, source UV metrics or support weights.
        translated = copy.deepcopy(candidate)
        translated['placed_cm'] = [[p[0]+22., p[1]-11., p[2]+9.] for p in candidate['placed_cm']]
        permutation = [7, 2, 5, 0, 4, 3, 1, 6]
        remap = {old: new for new, old in enumerate(permutation)}
        for key in ('rest_cm', 'placed_cm'):
            translated[key] = [translated[key][i] for i in permutation]
        translated['faces'] = [[remap[i] for i in face] for face in candidate['faces']]
        for panel in translated['panels'].values():
            panel['indices'] = [remap[i] for i in panel['indices']]
            panel['boundary'] = [remap[i] for i in panel['boundary']]
            panel['edges'] = {edge: [remap[i] for i in ids] for edge, ids in panel['edges'].items()}
        for seam in translated['seams'].values():
            seam['pairs'] = [[remap[a], remap[b]] for a, b in seam['pairs']]
        translated['pins'] = {str(remap[int(i)]): weight for i, weight in candidate['pins'].items()}
        transformed = assess_preparation(translated, recipe, source_audit=audit)
        self.assertEqual(transformed['status'], report['status'])
        for metric in ('min_principal_stretch', 'max_principal_stretch'):
            before = report['statistics']['extrema'][metric]
            after = transformed['statistics']['extrema'][metric]
            self.assertAlmostEqual(after['value'], before['value'], places=12)
            self.assertEqual(after['piece'], before['piece'])
            self.assertEqual(after['source_uv_cm'], before['source_uv_cm'])
        for source, current in zip(candidate['seams']['join']['pairs'], translated['seams']['join']['pairs']):
            self.assertEqual(current, [remap[i] for i in source])
        self.assertEqual({str(permutation[int(i)]): weight for i, weight in translated['pins'].items()}, original['pins'])
        self.assertEqual(candidate['rest_cm'], original['rest_cm'])
        self.assertEqual(candidate['pins'], original['pins'])
        self.assertEqual(payload, original)


if __name__ == '__main__':
    unittest.main()
