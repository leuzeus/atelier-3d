import copy
import unittest

from a3d.core import StudioError,digest
from a3d.guide_metric_solver import recover_guide_metric


def fixture():
    source={'rest_cm':[[0.,0.,0.],[2.,0.,0.],[2.,2.,0.],[0.,2.,0.]],
        'faces':[[0,1,2],[0,2,3]],'panels':{'panel':{'indices':[0,1,2,3],
            'edges':{'anchor':[0,3],'opposite':[1,2]}}},'seams':{},'pins':{}}
    guide=[[x*.5,y,z] for x,y,z in source['rest_cm']]
    quality={'min_angle_degrees':15.,'min_edge_cm':.01,'min_stretch':.9,'max_stretch':1.1}
    return source,guide,quality


class GuideMetricRecovery(unittest.TestCase):
    def test_compressed_coupon_recovers_source_metric_with_fixed_stops_and_no_acceptance(self):
        source,guide,quality=fixture();before=digest([source,guide,quality])
        result=recover_guide_metric(source,guide,quality,['panel'],[{'piece':'panel','edge':'anchor'}],
            max_iterations=20,max_seconds=10.,max_step_cm=.5)
        self.assertEqual(result['status'],'SOURCE_METRIC_RECOVERED')
        self.assertGreaterEqual(result['metric']['min_principal_stretch'],.9)
        self.assertLessEqual(result['metric']['max_principal_stretch'],1.1)
        self.assertEqual(result['coordinates_cm'][0],guide[0]);self.assertEqual(result['coordinates_cm'][3],guide[3])
        self.assertEqual(digest([source,guide,quality]),before)
        self.assertEqual(result['qualification'],'NONE');self.assertEqual(result['simulation'],'NOT_EXECUTED')
        self.assertEqual(result['contacts'],'NOT_ASSESSED')
        self.assertTrue(all(system['relative_residual']<1e-4
            for step in result['history'] for system in step['linear_systems']))

    def test_impossible_fixed_corners_and_tight_budget_never_gain_admission(self):
        source,guide,quality=fixture()
        result=recover_guide_metric(source,guide,quality,['panel'],
            [{'piece':'panel','edge':'anchor'},{'piece':'panel','edge':'opposite'}],max_iterations=8)
        self.assertEqual(result['status'],'NEEDS_CORRECTION');self.assertEqual(result['stop_reason'],'STAGNATION')
        self.assertEqual(result['coordinates_cm'],guide)
        result=recover_guide_metric(source,guide,quality,['panel'],[{'piece':'panel','edge':'anchor'}],
            max_iterations=5,max_displacement_cm=.01)
        self.assertEqual(result['status'],'NEEDS_CORRECTION');self.assertLessEqual(result['max_displacement_cm'],.01)

    def test_pin_and_unselected_piece_coordinates_remain_exact(self):
        source,guide,quality=fixture();source['rest_cm'] += [[10.,0.,0.],[12.,0.,0.],[12.,2.,0.],[10.,2.,0.]]
        source['faces'] += [[4,5,6],[4,6,7]];source['panels']['other']={'indices':[4,5,6,7],'edges':{'anchor':[4,7]}}
        guide += [[x,y,z+7.] for x,y,z in source['rest_cm'][4:]];source['pins']={'0':1.}
        before=digest(source);result=recover_guide_metric(source,guide,quality,['panel'],[{'piece':'panel','edge':'anchor'}])
        self.assertEqual(result['coordinates_cm'][0],guide[0]);self.assertEqual(result['coordinates_cm'][4:],guide[4:])
        self.assertEqual(digest(source),before)
        result=recover_guide_metric(source,guide,quality,['panel'],[{'piece':'panel','edge':'anchor'}],protected_indices=[1])
        self.assertEqual(result['coordinates_cm'][1],guide[1])
        with self.assertRaisesRegex(StudioError,'vertex indices'):
            recover_guide_metric(source,guide,quality,['panel'],[{'piece':'panel','edge':'anchor'}],protected_indices=[True])

    def test_unknown_stops_missing_constraints_and_invalid_budgets_refuse(self):
        source,guide,quality=fixture()
        for pieces,edges,kwargs in ((['unknown'],[],{}),(['panel'],[],{}),
            (['panel'],[{'piece':'panel','edge':'invented'}],{}),
            (['panel'],[{'piece':'panel','edge':'anchor'}],{'max_seconds':float('nan')})):
            with self.assertRaises(StudioError):recover_guide_metric(source,guide,quality,pieces,edges,**kwargs)

    def test_world_translation_does_not_change_the_numerical_metric_target(self):
        import math
        source,guide,quality=fixture();edges=[{'piece':'panel','edge':'anchor'}]
        reference=recover_guide_metric(source,guide,quality,['panel'],edges,max_iterations=20)
        offset=[1e6,-2e6,3e6];shifted=[[p[k]+offset[k] for k in range(3)] for p in guide]
        translated=recover_guide_metric(source,shifted,quality,['panel'],edges,max_iterations=20)
        self.assertEqual(translated['status'],reference['status'])
        restored=[[p[k]-offset[k] for k in range(3)] for p in translated['coordinates_cm']]
        self.assertLess(max(math.dist(a,b) for a,b in zip(reference['coordinates_cm'],restored)),1e-8)


if __name__=='__main__':unittest.main()
