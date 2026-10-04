import copy
import math
import unittest

from a3d.core import StudioError, digest
from a3d.garment_guides import specialised_volume_frames, garment_volume_frames
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


class GarmentGuides(unittest.TestCase):
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
