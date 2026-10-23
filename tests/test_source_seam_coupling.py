import copy
import json
import math
import unittest
from unittest.mock import patch

from a3d.core import StudioError, digest
from a3d.garment_guides import _source_limb_mesh
from a3d.pattern_assembly import _cage_point, _compile_cage
from a3d.sewing import edge_chain, mesh_quality, sample_chain
from a3d.source_seam_coupling import couple_source_seams


def recipe(data, tolerance=.02):
    return {'component_id': data['component_id'], 'seams': {s['id']:
        {'kind': s['kind'], 'ease_b_over_a': 0., 'tolerance_relative': tolerance} for s in data['seams']}}


def plain(pid, y):
    return {'source_ref': 'approved-guide:'+pid, 'origin_cm': [0., y, 0.],
        'u_axis': [1., 0., 0.], 'v_axis': [0., 0., 1.]}


def two_piece_fixture():
    from tests.test_torso_cages import fixture
    data, frames = fixture()
    data.update(component_id='fixture.coat', units='cm')
    # Same actual straight material edge, but different original corner
    # parameters. This was refused by the older torso-only helper.
    data['pieces']['back']['vertices'][2] = [-4.5, 3.]
    return data, frames, recipe(data)


def six_piece_fixture():
    pieces = {}
    for index, pid in enumerate(('front-left', 'front-right', 'back-left', 'back-right')):
        pieces[pid] = {'vertices': [[0., 0.], [4., 0.], [4., 10.], [2., 12.], [0., 12.]],
            'faces': [[0, 1, 2], [0, 2, 3], [0, 3, 4]],
            'edges': {'side': [1, 2], 'shoulder': [2, 3], 'neckline': [3, 4],
                      'inner-attachment': [4, 0], 'center-back': [4, 0]}}
    pieces['inner-front'] = {'vertices': [[0., 0.], [8., 0.], [8., 12.], [4., 12.], [0., 12.]],
        'faces': [[0, 1, 2], [0, 2, 3], [0, 3, 4]],
        'edges': {'attach-left': [4, 0], 'attach-right': [1, 2], 'neck-left': [2, 3], 'neck-right': [3, 4]}}
    x = [0., 4., 6., 8., 10., 12., 16.]
    pieces['collar'] = {'vertices': [[value, 0.] for value in x]+[[16., 2.], [0., 2.]],
        'faces': [[8, i, i+1] for i in range(6)]+[[8, 6, 7]],
        'edges': {name: [i, i+1] for i, name in enumerate(
            ('inner-left', 'front-left', 'back-left', 'back-right', 'front-right', 'inner-right'))}}
    seams = []

    def join(sid, a, ea, b, eb, orientation='reverse'):
        seams.append({'id': sid, 'piece_a': a, 'edge_a': ea, 'piece_b': b,
            'edge_b': eb, 'orientation': orientation, 'kind': 'permanent'})

    for side in ('left', 'right'):
        join('side-'+side, 'front-'+side, 'side', 'back-'+side, 'side')
        join('shoulder-'+side, 'front-'+side, 'shoulder', 'back-'+side, 'shoulder')
        join('inner-attach-'+side, 'front-'+side, 'inner-attachment', 'inner-front', 'attach-'+side)
    join('center-back', 'back-left', 'center-back', 'back-right', 'center-back')
    for family in ('inner', 'front', 'back'):
        for side in ('left', 'right'):
            partner = 'inner-front' if family == 'inner' else family+'-'+side
            edge = 'neck-'+side if family == 'inner' else 'neckline'
            join('collar-'+family+'-'+side, 'collar', family+'-'+side, partner, edge, 'forward')
    data = {'component_id': 'fixture.coat', 'units': 'cm', 'pieces': pieces, 'seams': seams}
    frames = {pid: plain(pid, float(index)*3.) for index, pid in enumerate(pieces)}
    # A valid existing source cage, an arc adapter and plain frames coexist.
    uv, faces = _source_limb_mesh(pieces['back-left'], 3)
    frames['back-left'] = {'source_ref': frames['back-left']['source_ref'], 'uv_cm': uv,
        'target_cm': [[p[0], 6., p[1]] for p in uv], 'triangles': faces}
    frames['inner-front'] = {'source_ref': 'approved-inner-plane', 'u_direction': 1,
        'arc_sections': [{'v_cm': v, 'arc_offset_cm': 0., 'curve_cm': [[0., 12., v], [8., 12., v]]}
                         for v in (0., 12.)]}
    return data, frames, recipe(data)


def area(points, triangles):
    return math.fsum(abs((points[b][0]-points[a][0])*(points[c][1]-points[a][1])
        -(points[b][1]-points[a][1])*(points[c][0]-points[a][0]))/2 for a, b, c in triangles)


class SourceSeamCoupling(unittest.TestCase):
    def test_partition_union_accepts_original_mismatched_corners_and_preserves_material(self):
        data, frames, declared = two_piece_fixture(); before = digest([data, frames, declared])
        cages, report = couple_source_seams(data, frames, declared, subdivisions=3)
        row = report['relations'][0]
        self.assertNotEqual(*row['source_corner_partitions'])
        self.assertTrue(any(report['refinements'][pid]['inserted_boundary_controls'] for pid in cages))
        compiled = {pid: _compile_cage(frame, pid) for pid, frame in cages.items()}
        for t in (0., .013, .16134918981837518, .251, .499, .842076250287768, 1.):
            uv = [sample_chain(edge_chain(data['pieces'][pid], 'side')[1], fraction)
                  for pid, fraction in (('front', t), ('back', 1-t))]
            positions = [_cage_point(cages[pid], compiled[pid], point, pid)[0]
                         for pid, point in zip(('front', 'back'), uv)]
            self.assertLess(math.dist(*positions), 1e-10)
        for pid, frame in cages.items():
            self.assertAlmostEqual(area(frame['uv_cm'], frame['triangles']),
                                   area(data['pieces'][pid]['vertices'], data['pieces'][pid]['faces']), places=11)
            self.assertEqual(set(frame), {'source_ref', 'uv_cm', 'target_cm', 'triangles'})
        self.assertEqual(digest([data, frames, declared]), before)

    def test_six_guides_couple_four_inner_and_collar_links_with_different_uv_v(self):
        data, frames, declared = six_piece_fixture()
        # Split one original collar corner at a distinct source parameter,
        # retaining its actual boundary and source triangles.
        collar = data['pieces']['collar']
        collar['vertices'].insert(1, [1.2, 0.])
        collar['faces'] = [[9, i, i+1] for i in range(7)]+[[9, 7, 8]]
        for name, ids in collar['edges'].items():
            collar['edges'][name] = [i+1 if i >= 1 else i for i in ids]
        collar['edges']['inner-left'] = [0, 1, 2]
        cages, report = couple_source_seams(data, frames, declared, subdivisions=3)
        self.assertEqual(len(report['relations']), 13)
        compiled = {pid: _compile_cage(frame, pid) for pid, frame in cages.items()}
        for row in report['relations']:
            seam = row['source_relation']
            for t in (0., .019, .317, .501, .913, 1.):
                positions = []
                for side in ('a', 'b'):
                    pid = seam['piece_'+side]; fraction = 1-t if side == 'b' and seam['orientation'] == 'reverse' else t
                    uv = sample_chain(edge_chain(data['pieces'][pid], seam['edge_'+side])[1], fraction)
                    positions.append(_cage_point(cages[pid], compiled[pid], uv, pid)[0])
                self.assertLess(math.dist(*positions), 1e-9, seam['id'])
        specific = {row['source_seam_id']: row for row in report['relations']}
        self.assertEqual({sid for sid in specific if sid.startswith(('inner-attach', 'collar-inner'))},
                         {'inner-attach-left', 'inner-attach-right', 'collar-inner-left', 'collar-inner-right'})
        left = specific['collar-inner-left']
        self.assertNotEqual(*left['source_corner_partitions'])
        self.assertTrue(any(cages[a[0]]['uv_cm'][a[1]][1] != cages[b[0]]['uv_cm'][b[1]][1]
                            for a, b in left['paired_cage_controls']))
        self.assertTrue(all(row['max_common_control_gap_cm'] == 0. for row in specific.values()))

    def test_original_proposal_mean_is_transitive_at_shared_source_corner(self):
        data, frames, declared = six_piece_fixture(); cages, report = couple_source_seams(data, frames, declared, subdivisions=3)
        # Both source back neck/shoulder corners and the collar chain's common
        # endpoint belong to one cohort. Count each source identity once.
        keys = set()
        adjacency = {}
        for row in report['relations']:
            for a, b in row['paired_cage_controls']:
                a, b = tuple(a), tuple(b); keys.update((a, b))
                adjacency.setdefault(a, set()).add(b); adjacency.setdefault(b, set()).add(a)
        seed = ('back-left', cages['back-left']['uv_cm'].index([2., 12.]))
        cohort = {seed}; remaining = [seed]
        while remaining:
            for neighbour in adjacency.get(remaining.pop(), ()):
                if neighbour not in cohort:
                    cohort.add(neighbour); remaining.append(neighbour)
        self.assertGreaterEqual(len(cohort), 3)
        old = {}
        from a3d.source_seam_coupling import _Budget, _evaluator
        budget = _Budget(None, __import__('time').monotonic)
        for pid, index in cohort:
            old[pid, index] = _evaluator(frames[pid], pid, budget)(cages[pid]['uv_cm'][index])
        expected = [math.fsum(point[k] for point in old.values())/len(old) for k in range(3)]
        for pid, index in cohort:
            self.assertLess(math.dist(cages[pid]['target_cm'][index], expected), 1e-12)
        reordered = copy.deepcopy(data); reordered['seams'].reverse()
        again, _ = couple_source_seams(reordered, frames, declared, subdivisions=3)
        self.assertEqual([again[p]['target_cm'] for p in sorted(again)], [cages[p]['target_cm'] for p in sorted(cages)])

    def test_binary64_roundoff_is_not_a_geometric_merge_and_report_is_json_native(self):
        data, frames, declared = six_piece_fixture(); before = digest([data, frames, declared])
        cages, report = couple_source_seams(data, frames, declared, subdivisions=3)
        value = {'frames': cages, 'report': report}
        self.assertEqual(json.loads(json.dumps(value, allow_nan=False)), value)
        restored = json.loads(json.dumps([data, frames, declared], allow_nan=False))
        self.assertEqual(couple_source_seams(*restored, subdivisions=3), (cages, report))
        self.assertIn('NO_PROXIMITY', report['parameter_roundoff_policy'])
        self.assertEqual(digest([data, frames, declared]), before)

    def test_accepted_tuple_coordinates_and_metadata_still_produce_native_json(self):
        data, frames, declared = two_piece_fixture()
        data['seams'][0]['source_metadata'] = {'source_ids': ('original-a', 'original-b')}
        for piece in data['pieces'].values():
            piece['vertices'] = [tuple(p) for p in piece['vertices']]
            piece['faces'] = [tuple(face) for face in piece['faces']]
        before = copy.deepcopy([data, frames, declared])
        cages, report = couple_source_seams(data, frames, declared, subdivisions=3)
        self.assertEqual(json.loads(json.dumps([cages, report])), [cages, report])
        self.assertEqual([data, frames, declared], before)

    def test_unary_source_seam_uses_original_distinct_boundary_identities(self):
        piece = {'vertices': [[0., 0.], [4., 0.], [4., 12.], [0., 12.]],
            'faces': [[0, 1, 2], [0, 2, 3]], 'edges': {'a': [1, 2], 'b': [3, 0]}}
        data = {'component_id': 'source.band', 'units': 'cm', 'pieces': {'band': piece}, 'seams': [
            {'id': 'self-closure', 'piece_a': 'band', 'edge_a': 'a', 'piece_b': 'band', 'edge_b': 'b',
             'kind': 'permanent', 'orientation': 'reverse'}]}
        cages, report = couple_source_seams(data, {'band': plain('band', 0.)}, recipe(data), subdivisions=3)
        pairs = report['relations'][0]['paired_cage_controls']
        self.assertTrue(all(a[0] == b[0] == 'band' and a[1] != b[1] for a, b in pairs))
        self.assertTrue(all(cages['band']['target_cm'][a[1]] == cages['band']['target_cm'][b[1]] for a, b in pairs))
        self.assertEqual(report['qualification'], 'NONE')

    def test_declared_recipe_admits_source_rounding_and_rejects_real_undeclared_length_difference(self):
        data, frames, declared = two_piece_fixture()
        # Original source arclengths differ by about 3e-7 cm, as for MAIN's
        # rounded collar edges. Existing recipe admission remains explicit.
        data['pieces']['back']['vertices'][3][0] -= 3.3e-6
        _, report = couple_source_seams(data, frames, declared, subdivisions=3)
        row = report['relations'][0]
        self.assertGreater(abs(row['source_length_delta_cm']), 1e-7)
        self.assertLess(row['relative_length_residual'], declared['seams']['actual-side']['tolerance_relative'])
        data['pieces']['back']['vertices'][3][0] -= 2.
        with self.assertRaisesRegex(StudioError, 'length mismatch'):
            couple_source_seams(data, frames, declared, subdivisions=3)

    def test_nonzero_ease_is_not_inferred_even_when_source_recipe_would_admit_it(self):
        data, frames, declared = two_piece_fixture()
        declared['seams']['actual-side']['ease_b_over_a'] = .001
        with self.assertRaisesRegex(StudioError, 'nonzero.*easing'):
            couple_source_seams(data, frames, declared)

    def test_boundary_ownership_and_topological_contradiction_are_refused(self):
        data, frames, declared = six_piece_fixture()
        data['seams'][0]['orientation'] = 'forward'
        with self.assertRaisesRegex(StudioError, 'Contradictory'):
            couple_source_seams(data, frames, declared)
        data, frames, declared = two_piece_fixture()
        second = copy.deepcopy(data['seams'][0]); second['id'] = 'duplicate-owner'
        data['seams'].append(second); declared = recipe(data)
        with self.assertRaisesRegex(StudioError, 'multiple seams'):
            couple_source_seams(data, frames, declared)

    def test_source_identity_is_retained_at_reverse_chain_corners(self):
        data, frames, declared = two_piece_fixture(); cages, report = couple_source_seams(data, frames, declared, subdivisions=3)
        row = report['relations'][0]
        # Partner b's reversed source boundary starts at its opposite actual
        # corner. Provenance retains original IDs rather than guessing indices.
        initial, final = row['source_parameters'][0], row['source_parameters'][-1]
        self.assertEqual(initial['partners'][1]['source_corner_vertex_id'], 1)
        self.assertEqual(final['partners'][1]['source_corner_vertex_id'], 3)
        for boundary in row['source_parameters']:
            for partner in boundary['partners']:
                pid = partner['piece']; a, b = partner['source_segment_vertex_ids']; t = partner['source_segment_parameter']
                expected = [data['pieces'][pid]['vertices'][a][k]*(1-t)+data['pieces'][pid]['vertices'][b][k]*t for k in (0, 1)]
                self.assertLess(math.dist(expected, cages[pid]['uv_cm'][partner['cage_control_index']]), 1e-12)

    def test_plain_offset_adapter_uses_declared_axes_and_refuses_native_bend(self):
        data, _, declared = two_piece_fixture()
        frames = {pid: plain(pid, float(i)*2.) for i, pid in enumerate(data['pieces'])}
        for frame in frames.values():
            frame['offset_uv_cm'] = [2., 1.]
        cages, report = couple_source_seams(data, frames, declared, subdivisions=3)
        touched = {tuple(key) for row in report['relations'] for pair in row['paired_cage_controls'] for key in pair}
        for pid, frame in cages.items():
            for index, uv in enumerate(frame['uv_cm']):
                if (pid, index) not in touched:
                    self.assertEqual(frame['target_cm'][index], [uv[0]-2., frames[pid]['origin_cm'][1], uv[1]-1.])
        frames['front']['native_bend'] = {'curvature': 1.}
        with self.assertRaisesRegex(StudioError, 'Unsupported native bend'):
            couple_source_seams(data, frames, declared)

    def test_external_source_relations_are_reported_without_coupling(self):
        data, frames, _ = two_piece_fixture()
        data['pieces']['arm'] = {'vertices': [[0., 0.], [5., 0.], [0., 3.]],
            'faces': [[0, 1, 2]], 'edges': {'cap': [0, 1]}}
        data['seams'].append({'id': 'external-cap', 'piece_a': 'front', 'edge_a': 'shoulder',
            'piece_b': 'arm', 'edge_b': 'cap', 'kind': 'permanent', 'orientation': 'reverse'})
        cages, report = couple_source_seams(data, frames, recipe(data), subdivisions=3)
        self.assertEqual(set(cages), {'front', 'back'})
        self.assertEqual(report['unprocessed_external_relations'], ['external-cap'])
        self.assertEqual(len(report['relations']), 1)

    def test_metric_and_contact_gates_remain_required_and_stretch_still_rejects(self):
        data, frames, declared = two_piece_fixture(); cages, report = couple_source_seams(data, frames, declared, subdivisions=3)
        frame = cages['front']
        with self.assertRaisesRegex(StudioError, 'distorted'):
            mesh_quality([point+[0.] for point in frame['uv_cm']], frame['target_cm'], frame['triangles'],
                         {'min_angle_degrees': 0., 'min_edge_cm': .00001, 'min_stretch': .999999, 'max_stretch': 1.000001})
        self.assertEqual(report['qualification'], 'NONE')
        self.assertEqual(report['metric_assessment'], 'REQUIRED')
        self.assertEqual(report['contact_assessment'], 'REQUIRED')
        self.assertEqual(report['anatomical_homology'], 'NOT_QUALIFIED')
        self.assertEqual(report['front_coverage'], 'NOT_REVIEWED')
        self.assertEqual(report['fitting'], 'NOT_EXECUTED')

    def test_invalid_inputs_are_domain_errors_and_never_change_sources(self):
        for variant in ('nan', 'bool', 'face', 'winding', 'edge', 'missing', 'units', 'recipe', 'hybrid', 'axis', 'arc'):
            data, frames, declared = two_piece_fixture()
            if variant == 'nan': data['pieces']['front']['vertices'][0][0] = math.nan
            elif variant == 'bool': data['pieces']['front']['vertices'][0][0] = True
            elif variant == 'face': data['pieces']['front']['faces'][0][0] = []
            elif variant == 'winding': data['pieces']['front']['faces'][0].reverse()
            elif variant == 'edge': data['pieces']['front']['edges']['side'] = [1, 3]
            elif variant == 'missing': data['seams'][0]['edge_a'] = 'unknown'
            elif variant == 'units': data['units'] = 'm'
            elif variant == 'recipe': declared['seams']['actual-side']['tolerance_relative'] = True
            elif variant == 'hybrid': frames['front']['uv_cm'] = [[0., 0.]]
            elif variant == 'axis': frames['front'] = plain('front', 0.); frames['front']['u_axis'][0] = 2.
            else: frames['front']['arc_sections'][0]['curve_cm'][0][0] = True
            before = copy.deepcopy([data, frames, declared])
            with self.subTest(variant=variant), self.assertRaises(StudioError):
                couple_source_seams(data, frames, declared, subdivisions=3)
            if variant != 'nan': self.assertEqual([data, frames, declared], before)

    def test_all_budgets_are_enforced_with_finite_nonboolean_values(self):
        for key, value in (('max_source_points', 3), ('max_source_triangles', 1), ('max_controls', 5),
                           ('max_triangles', 4), ('max_seconds', math.nan), ('max_seconds', True),
                           ('max_controls', True), ('max_triangles', 131073), ('unknown', 1)):
            data, frames, declared = two_piece_fixture(); before = digest([data, frames, declared])
            with self.subTest(key=key, value=value), self.assertRaises(StudioError):
                couple_source_seams(data, frames, declared, budgets={key: value})
            self.assertEqual(digest([data, frames, declared]), before)
        ticks = iter((0., .2))
        with self.assertRaisesRegex(StudioError, 'time budget'):
            couple_source_seams(*two_piece_fixture(), budgets={'max_seconds': .1}, clock=lambda: next(ticks))
        with self.assertRaises(StudioError):
            couple_source_seams(*two_piece_fixture(), subdivisions=True)

    def test_final_report_serialization_is_inside_time_and_monotonic_clock_budget(self):
        from a3d.core import canonical
        for final_time in (2., -1.):
            data, frames, declared = two_piece_fixture(); before = digest([data, frames, declared])
            current = [0.]

            def final_serialization(value):
                result = canonical(value)
                current[0] = final_time
                return result

            with self.subTest(final_time=final_time), patch('a3d.source_seam_coupling.canonical', final_serialization):
                with self.assertRaisesRegex(StudioError, 'time budget.*clock reversed'):
                    couple_source_seams(data, frames, declared, subdivisions=3,
                                        budgets={'max_seconds': 1.}, clock=lambda: current[0])
            self.assertEqual(digest([data, frames, declared]), before)


if __name__ == '__main__':
    unittest.main()
