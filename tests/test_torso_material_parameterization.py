import copy
import math
import unittest
from unittest.mock import patch

from a3d.core import StudioError, digest
from a3d.semantic_placement import torso_volume_frames
from a3d.shoulder_surface import measured_surface_shoulders
from a3d.torso_sections import source_bound_torso_cages
from tests.test_torso_cages import fixture as cage_fixture


def paired_fixture(with_geometry=False, rotated=False):
    """Synthetic paired cut and measured closed box; no production evidence."""
    front = {'vertices':[[.5,0.],[4.,0.],[4.,6.],[5.,10.],[1.,12.],[.5,11.]],
        'faces':[[0,1,2],[0,2,3],[0,3,4],[0,4,5]],
        'edges':{'hem':[0,1], 'side':[1,2], 'armhole':[2,3], 'shoulder':[3,4],
                 'neckline':[4,5], 'free':[5,0]}}
    back = {'vertices':[[0.,0.],[-4.,0.],[-4.,6.],[-5.,10.],[-1.,12.],[0.,12.]],
        'faces':[[0,1,2],[0,2,3],[0,3,4],[0,4,5]],
        'edges':{'hem':[0,1], 'side':[1,2], 'armhole':[2,3], 'shoulder':[3,4],
                 'neckline':[4,5], 'center':[5,0]}}
    data = {'pieces':{'front':front, 'back':back}, 'seams':[{'id':'actual-side',
        'piece_a':'front', 'piece_b':'back', 'edge_a':'side', 'edge_b':'side',
        'orientation':'forward', 'kind':'permanent'}]}
    semantics = {pid:{'role':pid, 'side':'right', 'layer':'outer'} for pid in data['pieces']}
    vertices = [[x,y,z] for z in (0.,20.) for y in (-1.,1.) for x in (-2.,2.)]
    faces = [[0,2,3,1],[4,5,7,6],[0,1,5,4],[2,6,7,3],[0,4,6,2],[1,3,7,5]]
    triangles = [t for a,b,c,d in faces for t in ([a,b,c],[a,c,d])]
    geometry = {'vertices_cm':vertices, 'faces':faces, 'source_sha256':'a'*64, 'pose_sha256':digest(vertices)}
    if rotated:
        vertices = [[p[2]+7.,p[1]-3.,-p[0]+2.] for p in vertices]
        geometry.update(vertices_cm=vertices,pose_sha256=digest(vertices))
    sections = [{'status':'MEASURED', 'height_cm':z, 'bounds_xy_cm':[[-2.,-1.],[2.,1.]],
        'curve_cm':[[-2.,-1.,z],[2.,-1.,z],[2.,1.,z],[-2.,1.,z]], 'girth_cm':12.}
        for z in (7.6,12.6,18.)]
    profile = {'geometry_sha256':digest([vertices,faces]), 'source_sha256':'a'*64,
        'pose_sha256':geometry['pose_sha256'], 'cache_key':'synthetic-original', 'stature_cm':20.,
        'status':'PROFILE_MEASURED', 'segmentation':'EXPLICIT_SOURCE', 'sections':sections,
        'frame':{'origin_cm':[0.,0.,0.], 'right':[1.,0.,0.], 'forward':[0.,-1.,0.], 'up':[0.,0.,1.]},
        'landmarks':{'neck':{'point_cm':[0.,0.,19.6]},
            'chest':{'point_cm':[0.,0.,12.6], 'girth_cm':12., 'section':sections[1]},
            **{f'shoulder.{side}':{'point_cm':[x,0.,19.2]} for side,x in [('left',-1.),('right',1.)]}}}
    if rotated:
        profile['frame']={'origin_cm':[7.,-3.,2.], 'right':[0.,0.,-1.], 'forward':[0.,-1.,0.], 'up':[1.,0.,0.]}
    result = (data, semantics, measured_surface_shoulders(profile,geometry,triangles))
    return result+(geometry,) if with_geometry else result


def material_cage_fixture():
    data, old = cage_fixture()
    frames = {pid:{'source_ref':frame['source_ref'], 'sampling_contract':'SOURCE_MATERIAL_U_V1',
        'material_sections':[{'v_cm':row['v_cm'], 'material_u_cm':[0.,frame['u_direction']*15.],
                             'curve_cm':row['curve_cm']} for row in frame['arc_sections']]}
        for pid,frame in old.items()}
    return data, frames


class TorsoMaterialParameterization(unittest.TestCase):
    def test_default_torso_cage_retains_historical_result_exactly(self):
        data, frames = cage_fixture()
        self.assertEqual(source_bound_torso_cages(data,frames), source_bound_torso_cages(
            data,frames,section_parameterization='POLYLINE_ARCLENGTH_V1'))

    def test_private_material_contract_requires_explicit_selection_and_preserves_source(self):
        data, frames = material_cage_fixture(); before = digest([data,frames])
        with self.assertRaises(StudioError):
            source_bound_torso_cages(data,frames)
        cages, report = source_bound_torso_cages(data,frames,section_parameterization='SOURCE_MATERIAL_U_V1')
        self.assertEqual(digest([data,frames]),before)
        self.assertEqual(report['source_seed_subdivisions'],1)
        self.assertEqual(report['section_parameterization'],'SOURCE_MATERIAL_U_V1')
        self.assertEqual(report['relations'][0]['max_common_control_gap_cm'],0.)
        self.assertEqual(report['qualification'],'NONE')
        self.assertEqual(report['contact_assessment'],'REQUIRED')
        self.assertEqual(report['simulation'],'NOT_EXECUTED')
        for pid, cage in cages.items():
            self.assertEqual(set(cage),{'source_ref','uv_cm','target_cm','triangles'})
            self.assertGreater(report['final_cage_metrics'][pid]['principal_range'][1],1.)
            self.assertLess(report['historical_arclength_comparison'][pid]['maximum_shift_cm'],1e-12)
            self.assertEqual(report['material_sampling'][pid]['stage'],'INITIAL_SOURCE_MATERIAL_PARTITION')

    def test_real_producer_transports_parameters_without_changing_curve_vertices(self):
        data, semantics, profile = paired_fixture(); before = digest([data,semantics,profile])
        def raw_cages(source, frames, **kwargs):
            return copy.deepcopy(frames), {'qualification':'NONE'}
        with patch('a3d.torso_sections.source_bound_torso_cages', side_effect=raw_cages):
            old = torso_volume_frames(data,semantics,profile,upper_blend=1.,surface_sections=True)
            new = torso_volume_frames(data,semantics,profile,upper_blend=1.,surface_sections=True,
                                      section_parameterization='SOURCE_MATERIAL_U_V1')
        for pid in data['pieces']:
            frame = new['panels'][pid]
            self.assertEqual(set(frame),{'source_ref','sampling_contract','material_sections'})
            for prior, row in zip(old['panels'][pid]['arc_sections'],frame['material_sections']):
                self.assertEqual(prior['v_cm'],row['v_cm'])
                self.assertEqual(prior['curve_cm'],row['curve_cm'])
                sign = 1 if pid=='front' else -1
                self.assertEqual(row['material_u_cm'][:129],[sign*5.*i/128 for i in range(129)])
                self.assertEqual(len(row['material_u_cm']),len(row['curve_cm']))
                curve = row['curve_cm']; params=row['material_u_cm']
                expected = params[-2]+(params[-2]-params[-3])*math.dist(curve[-2],curve[-1])/math.dist(curve[-3],curve[-2])
                self.assertEqual(params[-1],expected)
        self.assertEqual(digest([data,semantics,profile]),before)
        self.assertNotIn('section_parameterization',old['groups'][0]['guide'])

    def test_end_to_end_paired_opt_in_is_deterministic_with_current_metrics_and_no_admission(self):
        data, semantics, profile = paired_fixture(); before=digest([data,semantics,profile])
        kwargs = dict(upper_blend=1.,surface_sections=True,section_parameterization='SOURCE_MATERIAL_U_V1')
        result = torso_volume_frames(data,semantics,profile,**kwargs)
        self.assertEqual(result,torso_volume_frames(data,semantics,profile,**kwargs))
        self.assertEqual(digest([data,semantics,profile]),before)
        self.assertEqual(result['qualification'],'NONE')
        report=result['source_boundary_cage']
        self.assertEqual(set(report['final_cage_metrics']),set(data['pieces']))
        self.assertTrue(any(row['maximum_shift_cm'] > .1 for row in report['historical_arclength_comparison'].values()))
        self.assertLessEqual(report['controls'],report['budgets']['max_controls'])
        self.assertLessEqual(report['triangles'],report['budgets']['max_triangles'])

    def test_opt_in_rejects_missing_producer_prerequisites_and_unknown_modes(self):
        data, semantics, profile = paired_fixture()
        for kwargs in ({'upper_blend':0.,'surface_sections':True},
                       {'upper_blend':1.,'surface_sections':False}):
            with self.subTest(kwargs=kwargs),self.assertRaisesRegex(StudioError,'source|sourced'):
                torso_volume_frames(data,semantics,profile,section_parameterization='SOURCE_MATERIAL_U_V1',**kwargs)
        with self.assertRaisesRegex(StudioError,'parameterization'):
            torso_volume_frames(data,semantics,profile,section_parameterization='unknown')

    def test_insufficient_historical_arc_domain_is_a_comparison_gap_not_material_admission(self):
        data,frames=material_cage_fixture()
        for frame in frames.values():
            for row in frame['material_sections']:
                row['curve_cm']=[[.25*x for x in point] for point in row['curve_cm']]
        before=digest([data,frames])
        cages,report=source_bound_torso_cages(data,frames,section_parameterization='SOURCE_MATERIAL_U_V1')
        self.assertEqual(set(cages),set(data['pieces']))
        self.assertEqual(digest([data,frames]),before)
        self.assertTrue(all(row['status']=='NOT_COMPARABLE' for row in report['historical_arclength_comparison'].values()))
        self.assertTrue(all(row['reason']=='HISTORICAL_ARC_DOMAIN_DOES_NOT_COVER_SOURCE_CONTROLS'
                            for row in report['historical_arclength_comparison'].values()))
        self.assertTrue(all(row['principal_range'][0] < .5 for row in report['final_cage_metrics'].values()))
        self.assertEqual(report['qualification'],'NONE')
        self.assertEqual(report['metric_assessment'],'REQUIRED')

    def test_private_source_parameters_survive_world_rotation_without_scaling(self):
        def raw_cages(source,frames,**kwargs):
            return copy.deepcopy(frames), {'qualification':'NONE'}
        kwargs=dict(upper_blend=1.,surface_sections=True,section_parameterization='SOURCE_MATERIAL_U_V1')
        with patch('a3d.torso_sections.source_bound_torso_cages',side_effect=raw_cages):
            original=torso_volume_frames(*paired_fixture(),**kwargs)
            rotated=torso_volume_frames(*paired_fixture(rotated=True),**kwargs)
        for pid, frame in original['panels'].items():
            for first, second in zip(frame['material_sections'],rotated['panels'][pid]['material_sections']):
                self.assertEqual(first['material_u_cm'],second['material_u_cm'])
                for point, actual in zip(first['curve_cm'],second['curve_cm']):
                    expected=[point[2]+7.,point[1]-3.,-point[0]+2.]
                    self.assertLess(math.dist(expected,actual),1e-12)


if __name__ == '__main__':
    unittest.main()
