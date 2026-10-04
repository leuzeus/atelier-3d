import copy
import math
import unittest

from a3d.core import StudioError, digest
from a3d.garment_guides import specialised_volume_frames, garment_volume_frames, limb_volume_frames
from a3d.pattern_assembly import _compile_cage, _cage_point
from a3d.sewing import edge_chain, sample_chain
from a3d.preform_volume import sample_curve
from a3d.shoulder_surface import measured_surface_shoulders
from a3d.head_surface import measured_head_surface
from a3d.torso_sections import apply_measured_sections
from tests.test_shoulder_surface import fixture as shoulder_fixture


def fixture():
    profile, geometry, triangles = shoulder_fixture()
    profile.update(status='PROFILE_MEASURED', segmentation='EXPLICIT_SOURCE')
    for landmark, height in (('neck', 98.),):
        curve = [[-5., -4., height], [5., -4., height], [5., 4., height], [-5., 4., height]]
        profile['landmarks'][landmark] = {'point_cm': [0., 0., height],
            'section': {'status': 'MEASURED', 'curve_cm': curve, 'height_cm': height,
                        'bounds_xy_cm': [[-5., -4.], [5., 4.]], 'girth_cm': 36.}}
    profile['landmarks']['head.center'] = {'point_cm': [0., 0., 99.], 'source_ref': 'fixture:head-joint'}
    profile = measured_head_surface(profile, geometry, list(range(len(geometry['faces']))), 'fixture:head-segmentation')
    profile = measured_surface_shoulders(profile, geometry, triangles)
    data = {'pieces': {pid: {'vertices': [[-4., 2.], [4., 2.], [4., 12.], [-4., 12.]],
                             'edges': {'attachment': [0, 1], 'free': [2, 3]}}
                      for pid in ('single-front', 'collar', 'hood-left', 'hood-right', 'yoke')}}
    semantics = {pid: {'role': role, 'side': side, 'longitudinal_uv_axis': 'u' if role == 'collar' else 'v',
                      'guide_edges': {'anchor': 'attachment'}} for pid, role, side in
                 [('single-front', 'inner_front', 'center'), ('collar', 'collar', 'center'),
                  ('hood-left', 'hood', 'left'), ('hood-right', 'hood', 'right'), ('yoke', 'yoke', 'center')]}
    return data, semantics, profile


def limb_fixture(role='sleeve', side='right'):
    points = [[0., 0.], [4., 0.], [10., 0.], [11., 6.], [12., 12.], [-2., 12.], [-1., 6.]]
    piece = {'vertices': points, 'faces': [[6, 0, 1], [6, 1, 2], [6, 2, 3], [6, 3, 4], [6, 4, 5]],
             'edges': {'front': [5, 6, 0], 'back': [2, 3, 4], 'distal': [0, 1, 2], 'proximal': [4, 5]}}
    if side == 'left':
        piece['vertices'] = [[-u, v] for u, v in points]
    data = {'pieces': {'limb': piece}, 'seams': [{'id': 'actual-underarm', 'piece_a': 'limb', 'piece_b': 'limb',
            'edge_a': 'front', 'edge_b': 'back', 'orientation': 'reverse', 'kind': 'permanent'}]}
    semantic = {'role': role, 'side': side, 'longitudinal_uv_axis': 'v'}
    if role == 'cuff':
        semantic['guide_edges'] = {'distal': 'distal', 'proximal': 'proximal'}
    sign = 1 if side == 'right' else -1
    profile = {'status': 'PROFILE_MEASURED', 'segmentation': 'EXPLICIT_SOURCE', 'cache_key': 'fixture-cache',
        'frame': {'origin_cm': [0., 0., 0.], 'right': [1., 0., 0.], 'forward': [0., 1., 0.], 'up': [0., 0., 1.]},
        'landmarks': {'shoulder.'+side: {'point_cm': [sign*10., 0., 20.]},
                      'wrist.'+side: {'point_cm': [sign*10., 0., 0.]}}}
    return data, {'limb': semantic}, profile


class GarmentGuides(unittest.TestCase):
    def test_tapered_unary_source_seam_has_exact_shared_cage_boundary_without_input_change(self):
        data, semantics, profile = limb_fixture(); before = digest([data, semantics, profile])
        report = limb_volume_frames(data, semantics, profile); frame = report['panels']['limb']
        compiled = _compile_cage(frame, 'limb'); piece = data['pieces']['limb']
        for fraction in (0., .16134918981837518, .31, .5, .8385456355596534, 1.):
            a = sample_chain(edge_chain(piece, 'front')[1], fraction)
            b = sample_chain(edge_chain(piece, 'back')[1], 1-fraction)
            self.assertLess(math.dist(_cage_point(frame, compiled, a, 'limb')[0],
                                      _cage_point(frame, compiled, b, 'limb')[0]), 1e-8)
        self.assertEqual(report['evidence'][0]['source_circumference_domain_cm'], [10., 14.])
        self.assertEqual(report['evidence'][0]['cage_refinement']['control_triangles'], 5*8**2)
        self.assertEqual(report['evidence'][0]['anatomical_homology'], 'REVIEW_REQUIRED')
        self.assertEqual(report['qualification'], 'NONE'); self.assertEqual(report['fitting'], 'NOT_EXECUTED')
        self.assertEqual(digest([data, semantics, profile]), before)

    def test_oblique_body_plane_crosses_exact_normalized_source_partners(self):
        from a3d.garment_measurements import intersect_guide_material_plane, _trace
        from a3d.semantic_placement import limb_volume_frames as bbox_limb_frames
        data, semantics, profile = limb_fixture(); frame = limb_volume_frames(data, semantics, profile)['panels']['limb']
        triangles = [[frame['uv_cm'][i] for i in face] for face in frame['triangles']]
        section = {'center_cm': [10., 0., 14.], 'plane': {'normal_world': [.15, 0., math.sqrt(1-.15**2)]}}
        legacy = intersect_guide_material_plane(data['pieces']['limb'],
            bbox_limb_frames(data, semantics, profile)['panels']['limb'], triangles, section, ['front', 'back'])
        self.assertGreater(abs(legacy['from']['fraction']+legacy['to']['fraction']-1.), .02)
        self.assertGreater(math.dist(legacy['guide_world_polyline_cm'][0], legacy['guide_world_polyline_cm'][-1]), 1.)
        curve = intersect_guide_material_plane(data['pieces']['limb'], frame, triangles, section, ['front', 'back'])
        self.assertAlmostEqual(curve['from']['fraction']+curve['to']['fraction'], 1., places=8)
        self.assertLess(math.dist(curve['guide_world_polyline_cm'][0], curve['guide_world_polyline_cm'][-1]), 1e-8)
        segment = {'piece': 'limb', 'from': curve['from'], 'to': curve['to'], 'source_uv_polyline_cm': curve['source_uv_polyline_cm']}
        traced = _trace({'links': data['seams']}, [segment])
        self.assertEqual(traced['path_kind'], 'closed_girth'); self.assertEqual(traced['joins'], ['actual-underarm'])

    def test_cuff_uses_real_distal_stop_and_measured_frame_rotation(self):
        data, semantics, profile = limb_fixture('cuff')
        frame = limb_volume_frames(data, semantics, profile)['panels']['limb']; compiled = _compile_cage(frame, 'limb')
        a = _cage_point(frame, compiled, [0., 0.], 'limb')[0]
        b = _cage_point(frame, compiled, [-2., 12.], 'limb')[0]
        self.assertEqual(a[2], 0.); self.assertEqual(b[2], 12.)
        original = copy.deepcopy(profile)
        profile['frame'].update(origin_cm=[3., 4., 5.], right=[0., 1., 0.], forward=[-1., 0., 0.])
        rotated = limb_volume_frames(data, semantics, profile)['panels']['limb']
        for point, target in zip(frame['target_cm'], rotated['target_cm']):
            self.assertLess(math.dist(target, [3.-point[1], 4.+point[0], 5.+point[2]]), 1e-9)
        self.assertNotEqual(digest(profile), digest(original))

    def test_source_mirrors_and_input_order_preserve_correspondence(self):
        data, semantics, profile = limb_fixture(); right = limb_volume_frames(data, semantics, profile)
        mirrored, mirror_semantics, mirror_profile = limb_fixture(side='left')
        left = limb_volume_frames(mirrored, mirror_semantics, mirror_profile)
        for r, l in zip(right['panels']['limb']['target_cm'], left['panels']['limb']['target_cm']):
            self.assertLess(math.dist(l, [-r[0], r[1], r[2]]), 1e-9)
        data['pieces'] = dict(reversed(list(data['pieces'].items())))
        self.assertEqual(right, limb_volume_frames(data, semantics, profile))

    def test_missing_sewing_easing_oblique_pairs_or_invalid_source_triangles_refuse(self):
        for change in ('missing', 'duplicate', 'orientation', 'easing', 'pairing', 'faces', 'winding', 'nonfinite', 'bool'):
            data, semantics, profile = limb_fixture()
            if change == 'missing': data['seams'] = []
            elif change == 'duplicate': data['seams'] += copy.deepcopy(data['seams'])
            elif change == 'orientation': data['seams'][0]['orientation'] = 'forward'
            elif change == 'easing': data['pieces']['limb']['vertices'][3][0] += .5
            elif change == 'pairing': data['seams'][0]['edge_a'] = 'proximal'
            elif change == 'faces': data['pieces']['limb']['faces'].pop()
            elif change == 'winding': data['pieces']['limb']['faces'][0].reverse()
            elif change == 'nonfinite': data['pieces']['limb']['vertices'][0][0] = float('nan')
            else: data['pieces']['limb']['vertices'][0][0] = True
            with self.subTest(change=change), self.assertRaises((StudioError, ValueError)):
                limb_volume_frames(data, semantics, profile)
        for resolution in (True, 1, 17, 4.5):
            with self.subTest(resolution=resolution), self.assertRaises(StudioError):
                limb_volume_frames(*limb_fixture(), cage_subdivisions=resolution)

    def test_dispatcher_keeps_a_limb_without_original_sewing_data_pending(self):
        data, semantics, profile = limb_fixture(); data['seams'] = []
        report = garment_volume_frames(data, semantics, profile)
        self.assertEqual(report['pending_pieces'], ['limb']); self.assertEqual(report['qualification'], 'NONE')
        self.assertEqual(report['diagnostics'][0]['family'], 'limb')

    def test_unmatched_source_sewing_partitions_require_a_synchronized_guide(self):
        from a3d.garment_guides import _paired_limb_boundary
        # An extra real source corner on only one side may change the cage's
        # piecewise-linear boundary interpolation. It cannot be ignored even
        # when its endpoint arclengths and V coordinates still match.
        data = {'pieces': {'limb': {'vertices': [[0., 0.], [10., 0.], [10., 12.], [0., 12.], [0., 6.]],
            'edges': {'front': [3, 4, 0], 'back': [1, 2]}}},
            'seams': [{'id': 'source-only', 'kind': 'permanent', 'piece_a': 'limb', 'piece_b': 'limb',
                       'edge_a': 'front', 'edge_b': 'back', 'orientation': 'reverse'}]}
        before = digest(data)
        with self.assertRaisesRegex(StudioError, 'corner partitions'):
            _paired_limb_boundary(data, 'limb')
        self.assertEqual(digest(data), before)

    def test_actual_open_front_shift_preserves_source_seam_correspondence_without_uv_scaling(self):
        section={'status':'MEASURED','height_cm':5.,'bounds_xy_cm':[[-3.,-3.],[3.,3.]],
            'curve_cm':[[-3.,-3.,5.],[3.,-3.,5.],[3.,3.,5.],[-3.,3.,5.]]}
        profile={'sections':[section]}
        panels={'front':{'arc_sections':[{'v_cm':5.,'arc_offset_cm':0.,'curve_cm':[[0.,0.,5.],[10.,0.,5.]]}]},
                'back':{'arc_sections':[{'v_cm':5.,'arc_offset_cm':10.,'curve_cm':[[0.,0.,5.],[10.,0.,5.]]}]}}
        report={'body_frame':{'hem_z_cm':0.},'sections':[{'v_cm':5.,'applied_guide':{'half_girth_cm':10.}}]}
        group={'front':'front','back':'back','side_sign':1,
            'source_open_front':{'free_edge_v_domain_cm':[2.,8.],'inner_front_piece':'central-source'}}
        result,evidence=apply_measured_sections(panels,report,group,profile)
        front=result['front']['arc_sections'][0];back=result['back']['arc_sections'][0]
        self.assertAlmostEqual(front['arc_offset_cm'],2.)
        self.assertAlmostEqual(back['arc_offset_cm'],12.)
        self.assertEqual(sample_curve(front['curve_cm'],front['arc_offset_cm']+4.),
                         sample_curve(back['curve_cm'],back['arc_offset_cm']-6.))
        self.assertFalse(evidence['measured_sections'][0]['source_uv_scaled'])
        group['source_open_front']['free_edge_v_domain_cm']=[6.,8.]
        with self.assertRaises(StudioError) as error:apply_measured_sections(panels,report,group,profile)
        self.assertEqual(error.exception.guide_diagnostic['reason'],'SOURCE_GUIDE_CAPACITY_DEFICIT')

    def test_upper_torso_uses_actual_height_and_does_not_extend_chest_to_shoulders(self):
        sections = [{'status':'MEASURED','height_cm':height,'girth_cm':8*radius,
            'bounds_xy_cm':[[-radius,-radius],[radius,radius]],
            'curve_cm':[[-radius,-radius,height],[radius,-radius,height],[radius,radius,height],[-radius,radius,height]]}
            for height,radius in ((0.,3.),(10.,1.))]
        profile = {'sections':sections,'landmarks':{'chest':{'section':sections[0]}}}
        group = {'front':'front','back':'back','side_sign':1}
        rows = [{'v_cm':v,'curve_cm':[[0.,0.,v],[5.,0.,v]],'arc_offset_cm':0.} for v in (-5.,10.)]
        panels = {pid:{'arc_sections':copy.deepcopy(rows)} for pid in ('front','back')}
        report = {'body_frame':{'hem_z_cm':0.},'sections':[{'v_cm':v,'applied_guide':{'half_girth_cm':4.1}} for v in (-5.,10.)]}
        source_lower = copy.deepcopy(panels['front']['arc_sections'][0])
        result, observed = apply_measured_sections(panels,report,group,profile)
        self.assertEqual(result['front']['arc_sections'][0],source_lower)
        self.assertEqual(observed['measured_sections'][0]['surface_guide'],'SOURCE_AUXILIARY_BELOW_MEASURED_TORSO')
        self.assertEqual(observed['measured_sections'][1]['measured_section_heights_cm'],[10.,10.])
        self.assertAlmostEqual(observed['measured_sections'][1]['surface_half_girth_cm'],4.)
        self.assertFalse(observed['measured_sections'][1]['body_surface_extrapolated'])
        report['sections'] = [{'v_cm':20.,'applied_guide':{'half_girth_cm':4.1}}]
        with self.assertRaises(StudioError) as error: apply_measured_sections(panels,report,group,profile)
        self.assertEqual(error.exception.guide_diagnostic['reason'],'BODY_SECTION_HEIGHT_UNAVAILABLE')

    def test_complete_special_guides_preserve_metric_coverage_and_measured_identity(self):
        data, semantics, profile = fixture(); before = digest([data, semantics, profile])
        report = specialised_volume_frames(data, semantics, profile)
        self.assertEqual(set(report['panels']), set(data['pieces']))
        self.assertEqual(report['pending_pieces'], [])
        self.assertEqual(report['qualification'], 'NONE')
        self.assertEqual(digest([data, semantics, profile]), before)
        for pid, frame in report['panels'].items():
            first, last = frame['arc_sections']
            for source_u in (-3., 0., 3.):
                distance = source_u+first['arc_offset_cm']
                self.assertAlmostEqual(math.dist(sample_curve(first['curve_cm'], distance),
                                                 sample_curve(last['curve_cm'], distance)), 10.)
            perimeter = sum(math.dist(a, b) for a, b in zip(first['curve_cm'], first['curve_cm'][1:]))
            self.assertAlmostEqual(perimeter, 8.)
        self.assertEqual(len([g for g in report['guides'] if g['role'] == 'inner_front']), 1)

    def test_input_permutation_does_not_change_guides_and_body_change_invalidates_identity(self):
        data, semantics, profile = fixture(); expected = specialised_volume_frames(data, semantics, profile)
        data['pieces'] = dict(reversed(list(data['pieces'].items())))
        self.assertEqual(specialised_volume_frames(data, semantics, profile), expected)
        changed = copy.deepcopy(profile); changed['cache_key'] = 'stale'
        with self.assertRaises(StudioError): specialised_volume_frames(data, semantics, changed)

    def test_missing_source_anchor_axis_or_skin_section_refused_without_fabrication(self):
        for failure in ('anchor', 'edge', 'axis', 'skin', 'center'):
            data, semantics, profile = fixture()
            if failure == 'anchor': del semantics['collar']['guide_edges']['anchor']
            if failure == 'edge': semantics['collar']['guide_edges']['anchor'] = 'invented'
            if failure == 'axis': semantics['collar']['longitudinal_uv_axis'] = 'v'
            if failure == 'skin': del profile['surface_sections']['head']
            if failure == 'center': semantics['single-front']['side'] = 'left'
            with self.subTest(failure=failure), self.assertRaises(StudioError):
                specialised_volume_frames(data, semantics, profile)

    def test_dispatcher_keeps_unsupported_or_missing_skin_piece_pending(self):
        data, semantics, profile = fixture(); semantics['single-front']['role'] = 'reinforcement'
        report = garment_volume_frames(data, semantics, profile)
        self.assertEqual(report['status'], 'PARTIAL_GUIDES')
        self.assertEqual(report['pending_pieces'], ['single-front'])
        self.assertNotIn('single-front', report['panels'])
        del profile['surface_sections']['head']
        report = garment_volume_frames(data, semantics, profile)
        self.assertTrue(report['diagnostics'])
        self.assertNotEqual(report['status'], 'GARMENT_GUIDES_PREPARED')


if __name__ == '__main__':
    unittest.main()
