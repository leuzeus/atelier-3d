import copy
import unittest
from a3d.core import StudioError, digest
from a3d.semantic_placement import torso_volume_frames, limb_volume_frames, belt_volume_frames
from a3d.preform_volume import sample_curve
from tests.test_preform_volume import source_fixture


def fixture():
    data, _, _ = source_fixture()
    semantics = {pid: {'role': 'front' if pid == 'center' else pid, 'side': 'right', 'layer': 'outer'} for pid in data['pieces']}
    semantics['center']['subrole'] = 'opening_strip'
    profile = {'status': 'PROFILE_MEASURED', 'segmentation': 'EXPLICIT_SOURCE', 'cache_key': 'a'*64,
               'frame': {'origin_cm': [3., 4., 5.], 'right': [1., 0., 0.], 'forward': [0., -1., 0.], 'up': [0., 0., 1.]},
               'landmarks': {'chest': {'girth_cm': 100., 'section': {'bounds_xy_cm': [[-20., -10.], [20., 10.]]}},
                             'neck': {'point_cm': [0., 0., 140.]},
                             'shoulder.right': {'point_cm': [20., 0., 140.]},
                             'shoulder.left': {'point_cm': [-20., 0., 140.]}}}
    return data, semantics, profile


class SemanticPlacement(unittest.TestCase):
    def test_open_belt_guide_preserves_material_length_height_and_closure_type(self):
        import math
        _,_,profile=fixture()
        profile['landmarks']['waist']={'point_cm':[0.,0.,80.],'girth_cm':70.,
            'section':{'bounds_xy_cm':[[-15.,-10.],[15.,10.]]}}
        data={'pieces':{'belt':{'vertices':[[4.,2.],[100.,2.],[100.,8.],[4.,8.]]}},
              'seams':[{'id':'ends','kind':'closure'}]}
        semantics={'belt':{'role':'belt','longitudinal_uv_axis':'u'}}
        before=digest([data,semantics,profile]);result=belt_volume_frames(data,semantics,profile)
        sections=result['panels']['belt']['arc_sections']
        compiled_length=sum(math.dist(a,b) for a,b in zip(sections[0]['curve_cm'],sections[0]['curve_cm'][1:]))
        self.assertAlmostEqual(compiled_length,96.5)
        self.assertGreater(math.dist(sample_curve(sections[0]['curve_cm'],0.),
                                     sample_curve(sections[0]['curve_cm'],96.)),.4)
        for material in (0.,20.,60.,96.):
            self.assertAlmostEqual(math.dist(sample_curve(sections[0]['curve_cm'],material),
                                            sample_curve(sections[1]['curve_cm'],material)),6.)
        self.assertEqual(result['evidence'][0]['closure'],'NOT_EXECUTED')
        self.assertEqual(digest([data,semantics,profile]),before)
        semantics['belt']['longitudinal_uv_axis']='v'
        with self.assertRaises(StudioError):belt_volume_frames(data,semantics,profile)

    def test_real_front_back_cut_preserves_mirrors_and_never_fabricates_panels(self):
        data,_,profile=fixture()
        data={'pieces':{pid:data['pieces'][pid] for pid in ('front','back')}}
        for point in data['pieces']['back']['vertices']:point[0]*=-1
        semantics={pid:{'role':pid,'side':'left','layer':'outer'} for pid in data['pieces']}
        before=digest([data,semantics,profile])
        result=torso_volume_frames(data,semantics,profile)
        self.assertEqual(set(result['panels']),{'front','back'})
        self.assertEqual(result['groups'][0]['guide']['fabricated_source_panels'],[])
        self.assertEqual(result['groups'][0]['guide']['sections'][0]['raw_source']['half_girth_cm'],8.)
        front=result['panels']['front'];back=result['panels']['back']
        for a,b in zip(front['arc_sections'],back['arc_sections']):
            left=sample_curve(a['curve_cm'],a['arc_offset_cm']+front['u_direction']*4.)
            right=sample_curve(b['curve_cm'],b['arc_offset_cm']+back['u_direction']*(-4.))
            self.assertEqual(left,right)
        self.assertEqual(digest([data,semantics,profile]),before)
        self.assertEqual(result['simulation'],'NOT_EXECUTED')

    def test_paired_taper_does_not_smooth_partners_into_overlapping_interiors(self):
        data,_,profile=fixture()
        data={'pieces':{pid:data['pieces'][pid] for pid in ('front','back')}}
        for piece in data['pieces'].values():piece['vertices'][2][0]=6.
        semantics={pid:{'role':pid,'side':'right','layer':'outer'} for pid in data['pieces']}
        result=torso_volume_frames(data,semantics,profile)
        front=result['panels']['front'];back=result['panels']['back']
        for a,b in zip(front['arc_sections'],back['arc_sections']):
            source_width=4.+a['v_cm']*.2
            self.assertGreaterEqual(b['arc_offset_cm']-source_width,source_width)
        for a,b in zip(back['arc_sections'],back['arc_sections'][1:]):
            self.assertLessEqual(abs(b['arc_offset_cm']-a['arc_offset_cm']),.45*(b['v_cm']-a['v_cm'])+1e-8)
        self.assertEqual(result['groups'][0]['guide']['guide_smoothing']['mode'],'SOURCE_COVERING_SMOOTHED_GIRTH')

    def test_paired_cut_does_not_fill_a_real_front_opening_or_accept_shifted_back_center(self):
        data,_,profile=fixture()
        data={'pieces':{pid:data['pieces'][pid] for pid in ('front','back')}}
        for point in data['pieces']['front']['vertices']:
            if point[0]==0.:point[0]=1.
        semantics={pid:{'role':pid,'side':'right','layer':'outer'} for pid in data['pieces']}
        result=torso_volume_frames(data,semantics,profile)
        section=result['panels']['front']['arc_sections'][0]
        self.assertNotEqual(sample_curve(section['curve_cm'],1.),sample_curve(section['curve_cm'],0.))
        for point in data['pieces']['back']['vertices']:point[0]+=1.
        with self.assertRaises(StudioError):torso_volume_frames(data,semantics,profile)

    def test_uses_measured_profile_and_preserves_named_source_metric(self):
        data, semantics, profile = fixture(); before = digest([data, semantics, profile])
        result = torso_volume_frames(data, semantics, profile)
        self.assertEqual(result['status'], 'TORSO_GUIDES_PREPARED')
        self.assertEqual(set(result['panels']), set(data['pieces']))
        self.assertEqual(result['panels']['front']['arc_sections'][0]['curve_cm'][0][2], 135.)
        self.assertEqual(result['qualification'], 'NONE')
        self.assertEqual(digest([data, semantics, profile]), before)
        self.assertFalse(result['source_uv_scaled'])

    def test_missing_source_roles_profile_or_coverage_are_refused(self):
        for failure in ('role', 'profile', 'coverage', 'origin'):
            data, semantics, profile = fixture()
            if failure == 'role': semantics['side']['role'] = 'sleeve'
            if failure == 'profile': profile['segmentation'] = 'CENTRAL_CLOSED_LOOP_ONLY'
            if failure == 'coverage': del semantics['center']
            if failure == 'origin': data['pieces']['back']['vertices'][0][0] = 3.
            with self.subTest(failure=failure), self.assertRaises(StudioError):
                torso_volume_frames(data, semantics, profile)

    def test_other_roles_remain_explicitly_pending_without_fake_completion(self):
        data, semantics, profile = fixture()
        data['pieces']['sleeve'] = copy.deepcopy(data['pieces']['front'])
        semantics['sleeve'] = {'role': 'sleeve', 'side': 'right', 'layer': 'outer'}
        result = torso_volume_frames(data, semantics, profile)
        self.assertEqual(result['status'], 'PARTIAL_GUIDES')
        self.assertEqual(result['pending_pieces'], ['sleeve'])
        self.assertNotIn('sleeve', result['panels'])

    def test_limb_guides_preserve_source_arc_and_longitudinal_metric(self):
        data, _, profile = fixture()
        data = {'pieces': {'sleeve': data['pieces']['front']}}
        semantics = {'sleeve': {'role': 'sleeve', 'side': 'right', 'longitudinal_uv_axis': 'v'}}
        profile['landmarks']['wrist.right'] = {'point_cm': [40., 0., 85.]}
        before = digest([data, semantics, profile])
        result = limb_volume_frames(data, semantics, profile)
        sections = result['panels']['sleeve']['arc_sections']
        import math
        self.assertAlmostEqual(sum(math.dist(a, b) for a, b in zip(sections[0]['curve_cm'], sections[0]['curve_cm'][1:])), 4.)
        for u in (0., 1., 2., 3., 4.):
            self.assertAlmostEqual(math.dist(sample_curve(sections[0]['curve_cm'], u),
                                            sample_curve(sections[1]['curve_cm'], u)), 10.)
        self.assertEqual(digest([data, semantics, profile]), before)
        self.assertEqual(result['qualification'], 'NONE')
        del semantics['sleeve']['longitudinal_uv_axis']
        with self.assertRaises(StudioError): limb_volume_frames(data, semantics, profile)
