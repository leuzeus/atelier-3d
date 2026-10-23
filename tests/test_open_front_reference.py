"""Pure native-UV central-front references, with no production gate transfer."""
import copy
import unittest
import xml.etree.ElementTree as ET
from unittest.mock import patch

from a3d.core import StudioError, digest
from a3d.open_front_reference import prepare_open_front_reference, render_open_front_reference
from a3d.sewing import chain_lengths


def fixture(rotated=False):
    cid = 'textile.arbitrary'; pid = 'center.alpha'
    def piece(points, faces, edges):
        return {'vertices': points, 'faces': faces, 'edges': edges,
                'position_cm': [0., 0., 0.], 'rotation_degrees': [0., 0., 0.]}
    central = piece([[-2., 0.], [2., 0.], [2., 8.], [2., 10.], [-2., 10.], [-2., 8.]],
                    [[0, 1, 2], [0, 2, 5], [5, 2, 3], [5, 3, 4]],
                    {'join.alpha': [2, 3], 'join.beta': [5, 4],
                     'free.alpha': [1, 2], 'free.beta': [5, 0], 'cap': [3, 4], 'hem': [0, 1]})
    partner = piece([[0., 0.], [2., 0.], [2., 2.], [0., 2.]], [[0, 1, 2], [0, 2, 3]],
                    {'join': [0, 1], 'opening': [1, 2], 'hem': [2, 3], 'outer': [3, 0]})
    data = {'component_id': cid, 'units': 'cm', 'pieces': {pid: central,
        'wing.omega': copy.deepcopy(partner), 'wing.beta': copy.deepcopy(partner)},
        'seams': [{'id': 'attach.'+side, 'piece_a': pid, 'edge_a': edge,
                   'piece_b': other, 'edge_b': 'join', 'orientation': 'forward', 'kind': 'permanent'}
                  for side, edge, other in (('left', 'join.alpha', 'wing.omega'),
                                           ('right', 'join.beta', 'wing.beta'))],
        'material': {'mass_kg': .1, 'tension_stiffness': 1., 'compression_stiffness': 1.,
                     'shear_stiffness': 1., 'bending_stiffness': 1.}}
    frame = {'origin_cm': [7., 11., 13.], 'right': [0., 1., 0.] if rotated else [1., 0., 0.],
             'forward': [-1., 0., 0.] if rotated else [0., 1., 0.], 'up': [0., 0., 1.]}
    body = {'status': 'PROFILE_MEASURED', 'segmentation': 'EXPLICIT_SOURCE', 'cache_key': 'b'*64,
        'geometry_sha256': 'd'*64, 'pose_sha256': 'e'*64, 'frame': frame,
        'landmarks': {name: {'girth_cm': 22., 'section': {'status': 'MEASURED', 'height_cm': height,
            'girth_cm': 22., 'curve_cm': [[-4., -2., height], [4., -2., height], [4., 3., height],
                                      [-4., 3., height], [-4., -2., height]]}}
            for name, height in (('torso.top', 6.), ('torso.middle', 4.), ('torso.bottom', 2.))}}
    def world(point):
        return [frame['origin_cm'][k]+sum(point[j]*frame[axis][k]
                for j, axis in enumerate(('right', 'forward', 'up'))) for k in range(3)]
    ref = {'path': 'approved.garmentpkg', 'sha256': 'c'*64}
    semantics = {pid: {'role': 'inner_front', 'side': 'center', 'layer': 'lining', 'longitudinal_uv_axis': 'v'},
        'wing.omega': {'role': 'front', 'side': 'left', 'layer': 'shell'},
        'wing.beta': {'role': 'front', 'side': 'right', 'layer': 'shell'}}
    textiles = {p: {'component_id': cid, 'source_geometry': copy.deepcopy(v),
                    'semantics': semantics[p], 'package_source_ref': copy.deepcopy(ref)}
                for p, v in data['pieces'].items()}
    links = [{**s, 'source_link_id': s['id'], 'component_id': cid, 'id': cid+'::'+s['id']}
             for s in data['seams']]
    compiled = {'status': 'READY_TO_PLAN', 'assembly_spec': {'body_ref': {'path': 'body.json', 'sha256': 'f'*64},
        'layers': {'inside_to_outside': [['body', 'lining'], ['lining', 'shell']]}},
        'textiles': textiles, 'links': links, 'components': [{'id': cid, 'pipeline': 'PATTERN_SEWN'}]}
    compiled['compiled_sha256'] = digest(compiled)
    panels = {p: {'uv_cm': copy.deepcopy(v['vertices']),
        'target_cm': [world([uv[0], 1., uv[1]]) for uv in v['vertices']],
        'triangles': copy.deepcopy(v['faces']), 'source_ref': copy.deepcopy(ref)} for p, v in data['pieces'].items()}
    guides = {cid: {'panels': panels, 'source_sha256': digest(data), 'profile_sha256': digest(body),
        'profile_cache_key': body['cache_key'], 'semantics_sha256': digest(semantics)}}
    native = {'component_id': cid, 'source_garment_sha256': digest(data), 'package_sha256': ref['sha256'],
              'panels': {}, 'rest_cm': [], 'faces': [], 'seams': {}}
    for p, v in data['pieces'].items():
        offset = len(native['rest_cm']); native['rest_cm'].extend(uv+[0.] for uv in v['vertices'])
        native['faces'].extend([[offset+i for i in face] for face in v['faces']])
        indices = list(range(offset, offset+len(v['vertices'])))
        native['panels'][p] = {'indices': indices, 'boundary': list(indices),
            'source_contour_sha256': digest(v['vertices']), 'boundary_source_arclength_cm':
                [round(s, 8) for s in chain_lengths(v['vertices']+[v['vertices'][0]])[:-1]],
            'edges': {name: [offset+i for i in chain] for name, chain in v['edges'].items()}}
    for s in data['seams']:
        native['seams'][s['id']] = {k: s[k] for k in ('piece_a', 'piece_b', 'kind')}
        a = native['panels'][s['piece_a']]['edges'][s['edge_a']]
        b = native['panels'][s['piece_b']]['edges'][s['edge_b']]
        native['seams'][s['id']].update({'parameters': [0., 1.], 'pairs': [list(pair) for pair in zip(a, b)]})
    options = {'budgets': {'max_input_bytes': 2000000, 'max_vertices': 20000, 'max_faces': 50000,
        'max_boundary_edges': 10000, 'max_curve_points': 20000, 'max_output_bytes': 1000000, 'max_seconds': 10.},
        'provenance': {'native_receipt_event': 76, 'reviewed': True}}
    return [compiled, body, guides, {cid: data}, {cid: native}, list(body['landmarks'])], options


def refresh(inputs):
    compiled, body, guides, source_data, source_meshes, _ = inputs
    for cid, data in source_data.items():
        guides[cid]['source_sha256'] = digest(data)
        source_meshes[cid]['source_garment_sha256'] = digest(data)
        for pid in data['pieces']:
            compiled['textiles'][pid]['source_geometry'] = copy.deepcopy(data['pieces'][pid])
        guides[cid]['profile_sha256'] = digest(body)
        guides[cid]['semantics_sha256'] = digest({p: row['semantics'] for p, row in compiled['textiles'].items()
                                                if row['component_id'] == cid})
    compiled['compiled_sha256'] = digest({k: v for k, v in compiled.items() if k != 'compiled_sha256'})


class OpenFrontReference(unittest.TestCase):
    def test_native_source_uv_three_sections_arbitrary_ids_preserve_sources_and_no_target(self):
        inputs, options = fixture(); before = digest([inputs, options])
        report = prepare_open_front_reference(*inputs, **options)
        self.assertEqual(report['status'], 'CENTRAL_FRONT_REFERENCE_MEASURED')
        self.assertEqual([r['body_landmark'] for r in report['sections']], inputs[-1])
        self.assertEqual(report['reference_piece']['piece_id'], 'center.alpha')
        self.assertEqual(report['reference_piece']['free_boundaries']['left']['edge'], 'free.alpha')
        self.assertEqual(report['reference_piece']['attachments']['right']['source_link_id'], 'attach.right')
        for row in report['sections']:
            self.assertAlmostEqual(row['material_width_cm'], 4.)
            self.assertAlmostEqual(row['guide_world_length_cm'], 4.)
            self.assertAlmostEqual(row['projected_right_span_cm'], 4.)
            for endpoint in row['endpoints'].values():
                self.assertAlmostEqual(endpoint['signed_recess_from_section_front_cm'], 2.)
            self.assertEqual(row['physical_layer_recess'], 'NOT_MEASURED')
            self.assertEqual(row['source_span']['guide_plane_material_curve']['qualification'], 'NONE')
        self.assertEqual(report['visibility'], {'status': 'UNSELECTED', 'left_margin_cm': None, 'right_margin_cm': None})
        self.assertFalse(report['admissible_for_fit']); self.assertFalse(report['target_adopted'])
        self.assertFalse(report['variant_adopted']); self.assertFalse(report['current_outer_opening_is_target'])
        self.assertTrue(report['input_immutability_verified'])
        self.assertEqual(report['report_sha256'], digest({k: v for k, v in report.items() if k != 'report_sha256'}))
        self.assertEqual(report['integrity_scope'], 'CANONICAL_REPORT_CONTENT_ONLY_NOT_PROVENANCE_AUTHENTICATION')
        self.assertEqual(digest([inputs, options]), before)

    def test_kernel_and_renderer_never_read_files_or_schemas(self):
        inputs, options = fixture()
        with patch('builtins.open', side_effect=AssertionError('unexpected file read')), \
                patch('pathlib.Path.open', side_effect=AssertionError('unexpected file read')), \
                patch('a3d.core.read_json', side_effect=AssertionError('unexpected schema read')):
            result = prepare_open_front_reference(*inputs, **options)
            self.assertEqual(result['status'], 'CENTRAL_FRONT_REFERENCE_MEASURED')
            ET.fromstring(render_open_front_reference(inputs[1], result, max_output_bytes=100000))

    def test_pure_free_atoms_match_existing_source_boundary_graph_exactly(self):
        from a3d.dressing_derivation import source_boundary_graph, source_boundary_graph_from_validated
        inputs, _ = fixture(); data = inputs[3]['textile.arbitrary']
        self.assertEqual(source_boundary_graph_from_validated(data, max_edges=10000), source_boundary_graph(data))

    def test_nonmanifold_or_double_permanent_consumption_refused(self):
        from a3d.dressing_derivation import source_boundary_graph_from_validated
        for change in ('nonmanifold', 'duplicate-permanent'):
            inputs, _ = fixture(); data = inputs[3]['textile.arbitrary']
            if change == 'nonmanifold':
                data['pieces']['center.alpha']['faces'].extend([copy.deepcopy(data['pieces']['center.alpha']['faces'][0])]*2)
            else: data['seams'].append({**data['seams'][0], 'id': 'another-attachment'})
            with self.subTest(change=change), self.assertRaises(StudioError):
                source_boundary_graph_from_validated(data, max_edges=10000)

    def test_rotated_frame_has_identical_material_and_signed_recess(self):
        reports = [prepare_open_front_reference(*args, **opts) for args, opts in (fixture(), fixture(True))]
        for original, rotated in zip(reports[0]['sections'], reports[1]['sections']):
            for key in ('material_width_cm', 'projected_right_span_cm', 'endpoint_distance_cm'):
                self.assertAlmostEqual(original[key], rotated[key])
            for side in ('left', 'right'):
                self.assertEqual(original['endpoints'][side]['body_frame_cm'], rotated['endpoints'][side]['body_frame_cm'])
                self.assertNotEqual(original['endpoints'][side]['guide_world_cm'], rotated['endpoints'][side]['guide_world_cm'])

    def test_spatial_projection_is_not_material_width_or_body_girth_deficit(self):
        inputs, options = fixture(); cage = inputs[2]['textile.arbitrary']['panels']['center.alpha']
        for point in cage['target_cm']:
            point[0] = inputs[1]['frame']['origin_cm'][0]+.5*(point[0]-inputs[1]['frame']['origin_cm'][0])
        result = prepare_open_front_reference(*inputs, **options)
        for row in result['sections']:
            self.assertAlmostEqual(row['material_width_cm'], 4.)
            self.assertAlmostEqual(row['projected_right_span_cm'], 2.)
            self.assertNotIn('ease_cm', row)

    def test_missing_or_multiple_declared_central_piece_requires_mapping(self):
        for role in ('front', 'inner_front'):
            inputs, options = fixture()
            if role == 'front': inputs[0]['textiles']['center.alpha']['semantics']['role'] = role
            else: inputs[0]['textiles']['wing.beta']['semantics'].update(role=role, side='center')
            refresh(inputs); result = prepare_open_front_reference(*inputs, **options)
            self.assertEqual(result['status'], 'NEEDS_MAPPING'); self.assertFalse(result['sections'])
            self.assertEqual(result['diagnostics'][0]['code'], 'UNIQUE_DECLARED_CENTRAL_FRONT_REQUIRED')

    def test_detachable_or_missing_partner_side_does_not_become_permanent_reference(self):
        for change in ('detachable', 'unknown-side'):
            inputs, options = fixture()
            if change == 'detachable':
                inputs[3]['textile.arbitrary']['seams'][0]['kind'] = 'detachable'
                inputs[0]['links'][0]['kind'] = 'detachable'
                inputs[4]['textile.arbitrary']['seams']['attach.left']['kind'] = 'detachable'
            else: inputs[0]['textiles']['wing.omega']['semantics']['side'] = 'center'
            refresh(inputs); result = prepare_open_front_reference(*inputs, **options)
            self.assertEqual(result['status'], 'NEEDS_MAPPING')
            self.assertEqual(result['diagnostics'][0]['code'], 'CENTRAL_FRONT_ATTACHMENT_MAPPING_REQUIRED')

    def test_free_border_alias_or_multiple_longitudinal_candidates_is_ambiguous(self):
        for change in ('alias', 'competing-border'):
            inputs, options = fixture(); piece = inputs[3]['textile.arbitrary']['pieces']['center.alpha']
            if change == 'alias': piece['edges']['another-name'] = [1, 2]
            else:
                # A sloped free cap incident to the same attachment is not chosen by name.
                piece['vertices'][4][1] = 9.
            refresh(inputs); result = prepare_open_front_reference(*inputs, **options)
            self.assertEqual(result['status'], 'NEEDS_MAPPING')
            self.assertEqual(result['diagnostics'][0]['code'], 'CENTRAL_FRONT_FREE_BOUNDARY_MAPPING_REQUIRED')

    def test_missing_body_section_preserves_other_exact_sections_without_completion(self):
        inputs, options = fixture(); del inputs[1]['landmarks']['torso.middle']; refresh(inputs)
        result = prepare_open_front_reference(*inputs, **options)
        self.assertEqual(result['status'], 'NEEDS_DATA'); self.assertEqual(len(result['sections']), 2)
        self.assertEqual(result['diagnostics'][0]['body_landmark'], 'torso.middle')

    def test_stale_package_source_body_semantics_compilation_or_native_seam_is_refused(self):
        for change in ('source', 'package', 'body', 'semantics', 'compiled', 'native-seam'):
            inputs, options = fixture()
            if change == 'source': inputs[3]['textile.arbitrary']['pieces']['center.alpha']['vertices'][0][0] -= .001
            elif change == 'package': inputs[4]['textile.arbitrary']['package_sha256'] = '9'*64
            elif change == 'body': inputs[1]['cache_key'] = '9'*64
            elif change == 'semantics': inputs[2]['textile.arbitrary']['semantics_sha256'] = '9'*64
            elif change == 'compiled': inputs[0]['textiles']['center.alpha']['semantics']['layer'] = 'unapproved'
            else: del inputs[4]['textile.arbitrary']['seams']['attach.left']
            with self.subTest(change=change), self.assertRaises(StudioError):
                prepare_open_front_reference(*inputs, **options)

    def test_native_uv_mutation_is_local_diagnostic_never_completed(self):
        inputs, options = fixture(); inputs[4]['textile.arbitrary']['rest_cm'][0][0] += .001
        report = prepare_open_front_reference(*inputs, **options)
        self.assertEqual(report['status'], 'NEEDS_DATA'); self.assertFalse(report['sections'])
        self.assertEqual(report['diagnostics'][0]['code'], 'CENTRAL_FRONT_SECTION_NOT_MEASURED')
        self.assertFalse(report['admissible_for_fit'])

    def test_explicit_input_geometry_boundary_curve_and_output_budgets(self):
        for key in ('max_input_bytes', 'max_vertices', 'max_faces', 'max_boundary_edges', 'max_curve_points', 'max_output_bytes'):
            inputs, options = fixture(); options['budgets'][key] = 1
            report = prepare_open_front_reference(*inputs, **options)
            with self.subTest(key=key):
                self.assertEqual(report['status'], 'INCOMPLETE')
                self.assertFalse(report['sections']); self.assertFalse(report['admissible_for_fit'])
                self.assertFalse(report['input_immutability_verified'])

    def test_deadline_checked_after_existing_curve_primitive_and_no_cross_call_cache(self):
        from a3d.open_front_reference import _source_guide_curve
        inputs, options = fixture(); elapsed = [0.]
        def delayed(*args):
            value = _source_guide_curve(*args); elapsed[0] = 11.; return value
        with patch('a3d.open_front_reference._source_guide_curve', side_effect=delayed) as method:
            result = prepare_open_front_reference(*inputs, **options, clock=lambda: elapsed[0])
        self.assertEqual(method.call_count, 1); self.assertEqual(result['status'], 'INCOMPLETE')
        self.assertEqual(result['diagnostics'][0]['code'], 'OPEN_FRONT_TIME_BUDGET')
        self.assertEqual(prepare_open_front_reference(*inputs, **options)['status'], 'CENTRAL_FRONT_REFERENCE_MEASURED')

    def test_mutation_during_curve_measurement_refused(self):
        from a3d.open_front_reference import _source_guide_curve
        inputs, options = fixture()
        def mutated(*args):
            value = _source_guide_curve(*args); inputs[1]['landmarks']['torso.middle']['girth_cm'] += .1; return value
        with patch('a3d.open_front_reference._source_guide_curve', side_effect=mutated), self.assertRaisesRegex(StudioError, 'mutated'):
            prepare_open_front_reference(*inputs, **options)

    def test_invalid_nonfinite_clock_budget_names_or_anatomical_sections_refused(self):
        for change in ('clock', 'budget', 'names', 'nan', 'incomplete-budget'):
            inputs, options = fixture(); extra = {}
            if change == 'clock': extra['clock'] = lambda: float('nan')
            elif change == 'budget': options['budgets']['max_seconds'] = 61.
            elif change == 'names': inputs[-1] = ['same']*3
            elif change == 'nan': inputs[1]['frame']['origin_cm'][0] = float('nan')
            else: del options['budgets']['max_faces']
            with self.subTest(change=change), self.assertRaises(StudioError):
                prepare_open_front_reference(*inputs, **options, **extra)
        inputs, options = fixture()
        times = iter([1., .9])
        with self.assertRaisesRegex(StudioError, 'monotonic'):
            prepare_open_front_reference(*inputs, **options, clock=lambda: next(times))

    def test_current_outer_proposals_retained_as_identity_never_as_aesthetic_target(self):
        inputs, options = fixture(); current = [{'path_kind': 'open_material_span', 'source_material_length_cm': 1.,
                                                'open_front_overlap': 'NOT_MEASURED'}]
        result = prepare_open_front_reference(*inputs, **options, source_path_proposals=current)
        self.assertEqual(result['identity']['source_path_proposals_sha256'], digest(current))
        self.assertEqual([r['material_width_cm'] for r in result['sections']], [4., 4., 4.])
        self.assertFalse(result['current_outer_opening_is_target'])

    def test_svg_actual_curves_utf8_xml_escape_output_budget_and_profile_binding(self):
        inputs, options = fixture()
        # Legitimate source labels are prepared before measurement, never edited
        # into sealed measured data to exercise display escaping.
        original = inputs[-1][0]; label = 'poitrine <source> é'
        inputs[1]['landmarks'][label] = inputs[1]['landmarks'].pop(original)
        inputs[-1][0] = label; refresh(inputs)
        report = prepare_open_front_reference(*inputs, **options)
        before = digest([inputs[1], report]); svg = render_open_front_reference(inputs[1], report, max_output_bytes=100000)
        self.assertTrue(svg.startswith('<svg')); ET.fromstring(svg)
        self.assertIn('poitrine &lt;source&gt; é', svg); self.assertIn('UNSELECTED', svg)
        self.assertIn('Retrait signé', svg); self.assertIn('UV source', svg)
        self.assertEqual(digest([inputs[1], report]), before)
        with self.assertRaisesRegex(StudioError, 'byte budget'):
            render_open_front_reference(inputs[1], report, max_output_bytes=1)
        other = copy.deepcopy(inputs[1]); other['pose_sha256'] = 'a'*64
        with self.assertRaises(StudioError): render_open_front_reference(other, report, max_output_bytes=100000)

    def test_renderer_refuses_tampered_measurements_curves_endpoints_attachments_or_missing_hash(self):
        inputs, options = fixture(); original = prepare_open_front_reference(*inputs, **options)
        for change in ('material-width', 'body-curve', 'guide-curve', 'endpoint', 'source-uv',
                       'outline', 'attachment', 'provenance', 'missing-hash', 'wrong-hash'):
            report = copy.deepcopy(original); row = report['sections'][0]
            if change == 'material-width': row['material_width_cm'] = 999.
            elif change == 'body-curve': row['body_section_curve_cm'][0][0] = 999.
            elif change == 'guide-curve': row['guide_body_frame_polyline_cm'][0][0] = 999.
            elif change == 'endpoint': row['endpoints']['left']['signed_recess_from_section_front_cm'] = 999.
            elif change == 'source-uv': row['source_segment']['source_uv_polyline_cm'][0][0] = 999.
            elif change == 'outline': report['reference_piece']['source_uv_outline_cm'][0][0] = 999.
            elif change == 'attachment': report['reference_piece']['attachments']['left']['source_material_length_cm'] = 999.
            elif change == 'provenance': report['identity']['provenance']['reviewed'] = False
            elif change == 'missing-hash': del report['report_sha256']
            else: report['report_sha256'] = 'a'*64
            snapshot = digest(report)
            with self.subTest(change=change), self.assertRaisesRegex(StudioError, 'report integrity'):
                render_open_front_reference(inputs[1], report, max_output_bytes=100000)
            self.assertEqual(digest(report), snapshot)
        self.assertEqual(original['report_sha256'], digest({k: v for k, v in original.items() if k != 'report_sha256'}))

    def test_svg_closes_verified_cyclic_body_sections_without_changing_report(self):
        inputs, options = fixture()
        for landmark in inputs[1]['landmarks'].values():
            section = landmark['section']; section['curve_cm'].pop()
            section.update(confidence='MEASURED_SECTION', loop_count=1, excluded_loops=0)
        refresh(inputs); report = prepare_open_front_reference(*inputs, **options)
        before = digest([inputs[1], report]); seal = report['report_sha256']
        tree = ET.fromstring(render_open_front_reference(inputs[1], report, max_output_bytes=100000))
        ns = {'s': 'http://www.w3.org/2000/svg'}
        outlines = [node for node in tree.findall('.//s:polyline', ns) if node.attrib['stroke'] == '#64748b'][:3]
        self.assertEqual(len(outlines), 3)
        for node in outlines:
            points = [[float(value) for value in p.split(',')] for p in node.attrib['points'].split()]
            self.assertEqual(points[0], points[-1]); self.assertEqual(len(points), 5)
        self.assertEqual(report['report_sha256'], seal); self.assertEqual(digest([inputs[1], report]), before)

    def test_svg_does_not_close_unverified_open_body_polyline(self):
        inputs, options = fixture()
        for landmark in inputs[1]['landmarks'].values():
            landmark['section']['curve_cm'].pop()
        refresh(inputs); report = prepare_open_front_reference(*inputs, **options)
        tree = ET.fromstring(render_open_front_reference(inputs[1], report, max_output_bytes=100000))
        ns = {'s': 'http://www.w3.org/2000/svg'}
        outlines = [node for node in tree.findall('.//s:polyline', ns) if node.attrib['stroke'] == '#64748b'][:3]
        for node in outlines:
            points = node.attrib['points'].split(); self.assertEqual(len(points), 4)
            self.assertNotEqual(points[0], points[-1])


if __name__ == '__main__':
    unittest.main()
