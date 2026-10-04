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


def seamed_fixture(three=False):
    source={'rest_cm':[[0.,0.,0.],[2.,0.,0.],[2.,2.,0.],[0.,2.,0.],
                       [2.,0.,0.],[4.,0.,0.],[4.,2.,0.],[2.,2.,0.],[3.,1.,0.]],
        'faces':[[0,1,2],[0,2,3],[4,5,8],[5,6,8],[6,7,8],[7,4,8]],
        'panels':{'a':{'indices':[0,1,2,3],'edges':{'anchor':[0,3],'join':[1,2],'top':[3,2]}},
                  'b':{'indices':[4,5,6,7,8],'edges':{'anchor':[5,6],'join':[4,7],'top':[7,6]}}},
        'seams':{'ab':{'piece_a':'a','piece_b':'b','edge_a':'join','edge_b':'join','kind':'permanent',
                       'orientation':'forward','parameters':[0.,1.],'pairs':[[1,4],[2,7]]}},'pins':{}}
    guide=[[0.,0.,0.],[1.,0.,0.],[1.,2.,0.],[0.,2.,0.],
           [1.,0.,0.],[4.,0.,0.],[4.,2.,0.],[1.,2.,0.],[2.4,1.2,0.]]
    edges=[{'piece':'a','edge':'anchor'},{'piece':'b','edge':'anchor'}]
    if three:
        source['rest_cm'] += [[2.,2.,0.],[4.,2.,0.],[4.,4.,0.],[2.,4.,0.]]
        source['faces'] += [[9,10,11],[9,11,12]]
        source['panels']['c']={'indices':[9,10,11,12],'edges':{'join':[9,10],'anchor':[12,11]}}
        source['seams']['bc']={'piece_a':'b','piece_b':'c','edge_a':'top','edge_b':'join','kind':'permanent',
                               'orientation':'forward','parameters':[0.,1.],'pairs':[[7,9],[6,10]]}
        guide += [[1.,2.,0.],[4.,2.,0.],[4.,4.,0.],[2.,4.,0.]]
        edges.append({'piece':'c','edge':'anchor'})
    quality={'min_angle_degrees':15.,'min_edge_cm':.01,'min_stretch':.9,'max_stretch':1.1}
    return source,guide,quality,edges


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

    def test_joint_quotient_reduces_distortion_and_keeps_permanent_seams_exact_without_weld(self):
        import math
        source,guide,quality,edges=seamed_fixture();before=digest([source,guide,quality,edges])
        independent=recover_guide_metric(source,guide,quality,['a','b'],edges,max_iterations=30)
        result=recover_guide_metric(source,guide,quality,['a','b'],edges,seam_ids=['ab'],
            max_initial_seam_gap_cm=0.,max_iterations=30)
        self.assertEqual(result['status'],'SOURCE_METRIC_RECOVERED')
        for first,last in source['seams']['ab']['pairs']:
            self.assertEqual(result['coordinates_cm'][first],result['coordinates_cm'][last])
        self.assertGreater(max(math.dist(independent['coordinates_cm'][a],independent['coordinates_cm'][b])
                               for a,b in source['seams']['ab']['pairs']),1e-4)
        self.assertNotEqual(result['coordinates_cm'][8],guide[8])
        self.assertGreaterEqual(result['metric']['min_principal_stretch'],.9)
        self.assertLessEqual(result['metric']['max_principal_stretch'],1.1)
        coupling=result['seam_coupling']
        self.assertLess(coupling['quotient_unknown_count'],coupling['free_vertex_count'])
        self.assertEqual(coupling['final_max_cohort_gap_cm'],0.)
        self.assertFalse(coupling['weld_performed']);self.assertFalse(coupling['topology_modified'])
        self.assertFalse(coupling['source_uv_modified'])
        self.assertEqual(result['qualification'],'NONE');self.assertEqual(result['contacts'],'NOT_ASSESSED')
        self.assertEqual(digest([source,guide,quality,edges]),before)

    def test_transitive_three_piece_corner_uses_one_unknown_and_diffuses_to_interiors(self):
        source,guide,quality,edges=seamed_fixture(three=True)
        result=recover_guide_metric(source,guide,quality,['a','b','c'],edges,
            seam_ids=['ab','bc'],max_initial_seam_gap_cm=0.,max_iterations=50)
        self.assertEqual(result['status'],'SOURCE_METRIC_RECOVERED')
        self.assertEqual(result['coordinates_cm'][2],result['coordinates_cm'][7])
        self.assertEqual(result['coordinates_cm'][2],result['coordinates_cm'][9])
        self.assertIn([2,7,9],[row['indices']for row in result['seam_coupling']['cohorts']])
        self.assertNotEqual(result['coordinates_cm'][8],guide[8])
        for index in (0,3,5,6,11,12):self.assertEqual(result['coordinates_cm'][index],guide[index])

    def test_initial_semantic_gap_alignment_is_declared_bounded_and_measured(self):
        source,guide,quality,edges=seamed_fixture();guide[4][2]=.001;guide[7][2]=.001
        result=recover_guide_metric(source,guide,quality,['a','b'],edges,seam_ids=['ab'],
            max_initial_seam_gap_cm=.001,max_iterations=30)
        self.assertEqual(result['coordinates_cm'][1],result['coordinates_cm'][4])
        self.assertEqual(result['coordinates_cm'][2],result['coordinates_cm'][7])
        self.assertAlmostEqual(result['seam_coupling']['initial_max_cohort_gap_cm'],.001)
        self.assertAlmostEqual(result['seam_coupling']['initial_alignment_displacement_cm'],.0005)
        with self.assertRaisesRegex(StudioError,'seam gap budget'):
            recover_guide_metric(source,guide,quality,['a','b'],edges,seam_ids=['ab'],max_initial_seam_gap_cm=.0009)
        with self.assertRaisesRegex(StudioError,'displacement budget'):
            recover_guide_metric(source,guide,quality,['a','b'],edges,seam_ids=['ab'],
                max_initial_seam_gap_cm=.001,max_displacement_cm=.0001)

    def test_transitive_initial_cohort_checks_diameter_and_not_only_each_seam_pair(self):
        source,guide,quality,edges=seamed_fixture(three=True)
        guide[7][2]=.0009;guide[9][2]=.0018
        with self.assertRaisesRegex(StudioError,'seam gap budget'):
            recover_guide_metric(source,guide,quality,['a','b','c'],edges,
                seam_ids=['ab','bc'],max_initial_seam_gap_cm=.001)

    def test_initial_alignment_that_collapses_a_source_face_refuses_without_mutating_inputs(self):
        source,guide,quality,edges=seamed_fixture()
        # Both copies are initially nondegenerate. Their allowed semantic mean
        # would put A's entire join on its fixed opposite boundary.
        guide[4][0]=-1.;guide[7][0]=-1.
        before=digest([source,guide,quality,edges])
        with self.assertRaisesRegex(StudioError,'linear geometry motion collapses a face'):
            recover_guide_metric(source,guide,quality,['a','b'],edges,seam_ids=['ab'],
                max_initial_seam_gap_cm=2.)
        self.assertEqual(digest([source,guide,quality,edges]),before)

    def test_fixed_cohort_preserves_exact_stop_and_refuses_two_incompatible_pins(self):
        source,guide,quality,edges=seamed_fixture();source['pins']={'2':1.}
        guide[7][2]=.0001
        result=recover_guide_metric(source,guide,quality,['a','b'],edges,seam_ids=['ab'],
            max_initial_seam_gap_cm=.001,max_iterations=5)
        self.assertEqual(result['coordinates_cm'][2],guide[2])
        self.assertEqual(result['coordinates_cm'][7],guide[2])
        self.assertIn(7,result['seam_coupling']['fixed_cohort_indices'])
        source['pins']['7']=1.
        with self.assertRaisesRegex(StudioError,'incompatible exact fixed'):
            recover_guide_metric(source,guide,quality,['a','b'],edges,seam_ids=['ab'],max_initial_seam_gap_cm=.001)

    def test_unselected_piece_is_immutable_and_a_seam_crossing_it_is_refused(self):
        source,guide,quality,edges=seamed_fixture(three=True)
        result=recover_guide_metric(source,guide,quality,['a','b'],edges[:2],seam_ids=['ab'],
            max_initial_seam_gap_cm=0.,max_iterations=30)
        self.assertEqual(result['coordinates_cm'][9:],guide[9:])
        with self.assertRaisesRegex(StudioError,'unselected piece'):
            recover_guide_metric(source,guide,quality,['a','b'],edges[:2],seam_ids=['ab','bc'],max_initial_seam_gap_cm=0.)
        source['panels']['c']['indices'].append(2)
        with self.assertRaisesRegex(StudioError,'unselected piece'):
            recover_guide_metric(source,guide,quality,['a','b'],edges[:2],seam_ids=['ab'],max_initial_seam_gap_cm=0.)

    def test_seams_require_real_unique_owned_boundary_pairs_and_permanent_kind(self):
        source,guide,quality,edges=seamed_fixture()
        for alteration in ('missing','closure','detachable','owner','interior','index','edge','params','reverse','ambiguous'):
            changed=copy.deepcopy(source);ids=['ab'];seam=changed['seams']['ab']
            if alteration=='missing':ids=['unknown']
            elif alteration in('closure','detachable'):seam['kind']=alteration
            elif alteration=='owner':seam['piece_a']='missing'
            elif alteration=='interior':seam['pairs'][0][1]=8;seam['edge_b']='invented';changed['panels']['b']['edges']['invented']=[8,7]
            elif alteration=='index':seam['pairs'][0][0]=True
            elif alteration=='edge':seam['edge_b']='anchor'
            elif alteration=='params':seam['parameters']=[0.,.9]
            elif alteration=='reverse':seam['orientation']='reverse'
            else:
                seam.pop('edge_b');changed['panels']['b']['edges']['alias']=[4,7]
            with self.subTest(alteration=alteration),self.assertRaises(StudioError):
                recover_guide_metric(changed,guide,quality,['a','b'],edges,seam_ids=ids,max_initial_seam_gap_cm=0.)

    def test_unique_native_boundary_binding_can_supply_edge_names_without_inventing_associations(self):
        source,guide,quality,edges=seamed_fixture()
        source['seams']['ab'].pop('edge_a');source['seams']['ab'].pop('edge_b');source['seams']['ab'].pop('orientation')
        result=recover_guide_metric(source,guide,quality,['a','b'],edges,seam_ids=['ab'],max_initial_seam_gap_cm=0.)
        relation=result['seam_coupling']['relations'][0]
        self.assertEqual(relation['edge_a'],'join');self.assertEqual(relation['edge_b'],'join')

    def test_missing_piece_stop_or_invalid_declared_coupling_budgets_refuse(self):
        source,guide,quality,edges=seamed_fixture()
        for ids,gap in ((['ab'],None),(['ab'],float('nan')),(['ab'],float('inf')),(['ab'],True),
                        (['ab'],-.01),(['ab','ab'],0.),('ab',0.),([True],0.)):
            with self.subTest(ids=ids,gap=gap),self.assertRaises(StudioError):
                recover_guide_metric(source,guide,quality,['a','b'],edges,seam_ids=ids,max_initial_seam_gap_cm=gap)
        with self.assertRaisesRegex(StudioError,'Each recovered source piece'):
            recover_guide_metric(source,guide,quality,['a','b'],edges[:1],seam_ids=['ab'],max_initial_seam_gap_cm=0.)

    def test_coupled_stagnation_and_time_or_iteration_budgets_do_not_grant_contact_or_fit(self):
        source,guide,quality,edges=seamed_fixture()
        result=recover_guide_metric(source,guide,quality,['a','b'],edges,seam_ids=['ab'],
            max_initial_seam_gap_cm=0.,max_iterations=1,max_displacement_cm=.001)
        self.assertEqual(result['status'],'NEEDS_CORRECTION')
        self.assertEqual(result['stop_reason'],'ITERATION_BUDGET')
        self.assertLessEqual(result['max_displacement_cm'],.001)
        self.assertEqual(result['coordinates_cm'][1],result['coordinates_cm'][4])
        self.assertEqual(result['qualification'],'NONE');self.assertEqual(result['fitting'],'NOT_EXECUTED')
        ticks=iter([0.,0.,2.])
        with self.assertRaisesRegex(StudioError,'time budget'):
            recover_guide_metric(source,guide,quality,['a','b'],edges,seam_ids=['ab'],
                max_initial_seam_gap_cm=0.,max_seconds=1.,clock=lambda:next(ticks))

    def test_coupled_world_translation_preserves_result_and_exact_semantic_equality(self):
        import math
        source,guide,quality,edges=seamed_fixture();kwargs={'seam_ids':['ab'],'max_initial_seam_gap_cm':0.,'max_iterations':30}
        result=recover_guide_metric(source,guide,quality,['a','b'],edges,**kwargs)
        offset=[1e6,-2e6,3e6];translated=[[p[k]+offset[k]for k in range(3)]for p in guide]
        moved=recover_guide_metric(source,translated,quality,['a','b'],edges,**kwargs)
        self.assertEqual(moved['status'],result['status'])
        restored=[[p[k]-offset[k]for k in range(3)]for p in moved['coordinates_cm']]
        self.assertLess(max(math.dist(a,b)for a,b in zip(restored,result['coordinates_cm'])),1e-8)
        self.assertEqual(moved['coordinates_cm'][1],moved['coordinates_cm'][4])
        self.assertEqual(moved['coordinates_cm'][2],moved['coordinates_cm'][7])

    def test_fixed_stops_preserve_coordinate_representation_exactly_during_quotient_iterations(self):
        source,guide,quality,edges=seamed_fixture();source['pins']={'2':1.}
        guide[2][2]=-0.;guide[7][2]=-0.
        result=recover_guide_metric(source,guide,quality,['a','b'],edges,seam_ids=['ab'],
            max_initial_seam_gap_cm=0.,max_iterations=5)
        self.assertEqual(digest(result['coordinates_cm'][2]),digest(guide[2]))
        self.assertEqual(digest(result['coordinates_cm'][7]),digest(guide[2]))

    def test_impossible_fixed_source_chord_refuses_before_optimization_with_measured_diagnostic(self):
        source,_,quality=fixture();guide=[[x,y*1.2,z]for x,y,z in source['rest_cm']]
        result=recover_guide_metric(source,guide,quality,['panel'],[{'piece':'panel','edge':'anchor'}])
        self.assertEqual(result['status'],'NEEDS_CORRECTION')
        self.assertEqual(result['stop_reason'],'FIXED_SOURCE_STOP_BOUND_EXCEEDS_METRIC')
        self.assertEqual(result['iterations'],0);self.assertEqual(result['history'],[])
        self.assertEqual(result['coordinates_cm'],guide)
        bounds=result['fixed_stop_bounds'];self.assertEqual(bounds['status'],'IMPOSSIBLE_FIXED_STOPS')
        row=bounds['records'][0]
        self.assertEqual(row['source_uv_path_length_cm'],2.)
        self.assertEqual(row['fixed_stop_indices'],[0,3])
        self.assertEqual(row['fixed_stop_coordinates_cm'],[guide[0],guide[3]])
        self.assertAlmostEqual(row['minimum_required_stretch'],1.2)
        self.assertEqual(row['maximum_declared_stretch'],1.1)
        self.assertEqual(bounds['qualification'],'NONE')

    def test_fixed_stop_source_length_uses_the_full_uv_polyline_and_not_its_source_chord(self):
        source={'rest_cm':[[0.,0.,0.],[1.,1.,0.],[2.,0.,0.],[0.,-2.,0.]],
            'faces':[[0,3,1],[1,3,2]],'panels':{'panel':{'indices':[0,1,2,3],
            'edges':{'anchor':[0,1,2]}}},'pins':{},'seams':{}}
        guide=copy.deepcopy(source['rest_cm']);guide[2][0]=2.5
        quality={'min_angle_degrees':1.,'min_edge_cm':.01,'min_stretch':.9,'max_stretch':1.1}
        result=recover_guide_metric(source,guide,quality,['panel'],[{'piece':'panel','edge':'anchor'}],max_iterations=1)
        bound=result['fixed_stop_bounds']['records'][0]
        self.assertAlmostEqual(bound['source_uv_path_length_cm'],2*2**.5)
        self.assertAlmostEqual(bound['minimum_required_stretch'],2.5/(2*2**.5))
        self.assertFalse(bound['impossible_with_fixed_stops'])

    def test_fixed_stop_preflight_obeys_time_budget_without_mutating_source(self):
        source,guide,quality=fixture();before=digest([source,guide,quality])
        ticks=iter([0.,2.])
        with self.assertRaisesRegex(StudioError,'preflight time budget'):
            recover_guide_metric(source,guide,quality,['panel'],[{'piece':'panel','edge':'anchor'}],
                max_seconds=1.,clock=lambda:next(ticks))
        self.assertEqual(digest([source,guide,quality]),before)

    def test_fixed_stop_margin_is_explicit_bounded_and_does_not_relax_final_metrics(self):
        source,_,quality=fixture();guide=[[x,y*1.100000001,z]for x,y,z in source['rest_cm']]
        result=recover_guide_metric(source,guide,quality,['panel'],[{'piece':'panel','edge':'anchor'}],
            fixed_stop_stretch_margin=1e-8,max_iterations=1)
        self.assertEqual(result['fixed_stop_bounds']['status'],'NO_IMPOSSIBILITY_DETECTED')
        self.assertEqual(result['status'],'NEEDS_CORRECTION')
        self.assertGreater(result['metric']['max_principal_stretch'],quality['max_stretch'])
        self.assertEqual(result['policy']['quality'],quality)
        for margin in (float('nan'),float('inf'),True,-.01,.1):
            with self.subTest(margin=margin),self.assertRaises(StudioError):
                recover_guide_metric(source,guide,quality,['panel'],[{'piece':'panel','edge':'anchor'}],fixed_stop_stretch_margin=margin)


if __name__=='__main__':unittest.main()
