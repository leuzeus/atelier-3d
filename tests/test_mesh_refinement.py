import copy
import math
import unittest
from a3d.core import StudioError
from a3d.cloth_metrics import triangle_metrics
from a3d.mesh_refinement import improve_interior


class InteriorRefinement(unittest.TestCase):
    def test_improves_angles_without_touching_contour_or_topology(self):
        vertices=[[0.,0.],[2.,0.],[2.,2.],[0.,2.],[.2,.2]]
        faces=[[0,1,4],[1,2,4],[2,3,4],[3,0,4]]
        before=copy.deepcopy((vertices,faces))
        result,report=improve_interior(vertices,faces,{0,1,2,3},target_angle=25.,min_edge=.1,max_displacement=.8)
        self.assertEqual((vertices,faces),before)
        self.assertEqual(result[:4],vertices[:4])
        self.assertGreater(report['min_angle_after_degrees'],report['min_angle_before_degrees'])
        self.assertLessEqual(report['maximum_displacement_cm'],.8)

    def test_fixed_or_budget_exhausted_is_explicit_and_does_not_move_source(self):
        vertices=[[0.,0.],[2.,0.],[.01,.1]];faces=[[0,1,2]]
        result,report=improve_interior(vertices,faces,{0,1,2},target_angle=15.,min_edge=.1,max_displacement=.5)
        self.assertEqual(result,vertices)
        self.assertFalse(report['target_reached'])
        self.assertEqual(report['accepted_vertex_moves'],0)

    def test_contour_is_automatically_fixed_and_triangle_quality_does_not_spread_defects(self):
        vertices=[[0.,0.],[2.,0.],[2.,2.],[0.,2.],[.2,.2]]
        faces=[[0,1,4],[1,2,4],[2,3,4],[3,0,4]]
        result,report=improve_interior(vertices,faces,set(),target_angle=25.,min_edge=.1,max_displacement=.8)
        self.assertEqual(result[:4],vertices[:4])
        self.assertEqual(report['boundary_vertex_count'],4)
        before=[triangle_metrics([vertices[i] for i in face]) for face in faces]
        after=[triangle_metrics([result[i] for i in face]) for face in faces]
        self.assertAlmostEqual(sum(row['area_cm2'] for row in before),sum(row['area_cm2'] for row in after))
        for a,b in zip(before,after):
            self.assertGreaterEqual(b['min_angle_degrees']+1e-7,min(25.,a['min_angle_degrees']))
        repeated,repeated_report=improve_interior(vertices,faces,set(),target_angle=25.,min_edge=.1,max_displacement=.8)
        self.assertEqual(repeated,result)
        self.assertEqual(repeated_report,report)

    def test_clockwise_source_winding_is_preserved_and_does_not_change_solution(self):
        vertices=[[0.,0.],[2.,0.],[2.,2.],[0.,2.],[.2,.2]]
        faces=[[0,1,4],[1,2,4],[2,3,4],[3,0,4]]
        settings={'target_angle':25.,'min_edge':.1,'max_displacement':.8}
        reference,_=improve_interior(vertices,faces,set(),**settings)
        clockwise=[list(reversed(face)) for face in faces]
        result,report=improve_interior(vertices,clockwise,set(),**settings)
        self.assertTrue(all(math.dist(a,b)<1e-12 for a,b in zip(reference,result)))
        for face in clockwise:
            a,b,c=[result[i] for i in face]
            self.assertLess((b[0]-a[0])*(c[1]-a[1])-(b[1]-a[1])*(c[0]-a[0]),0.)
        self.assertTrue(report['target_reached'])

    def test_angle_success_cannot_hide_short_edges_or_inadequate_motion_budget(self):
        vertices=[[0.,0.],[.01,0.],[0.,.01]];faces=[[0,1,2]]
        result,report=improve_interior(vertices,faces,set(),target_angle=15.,min_edge=.1,max_displacement=.5)
        self.assertFalse(report['target_reached'])
        self.assertEqual(report['remaining_bad_faces'],[0])
        self.assertEqual(result,vertices)

    def test_malformed_geometry_and_nonfinite_budgets_are_refused(self):
        vertices=[[0.,0.],[1.,0.],[0.,1.]];faces=[[0,1,2]]
        for problem in ('empty','nan_vertex','3d','negative_budget','nan_budget','bad_anchor','collapsed','flipped_neighbor'):
            points=copy.deepcopy(vertices);triangles=copy.deepcopy(faces);fixed=set()
            settings={'target_angle':15.,'min_edge':.01,'max_displacement':.5}
            if problem=='empty':triangles=[]
            elif problem=='nan_vertex':points[0][0]=math.nan
            elif problem=='3d':points[0].append(0.)
            elif problem=='negative_budget':settings['max_displacement']=-1.
            elif problem=='nan_budget':settings['max_displacement']=math.inf
            elif problem=='bad_anchor':fixed.add(10)
            elif problem=='collapsed':points[2]=[2.,0.]
            elif problem=='flipped_neighbor':points.append([1.,1.]);triangles.append([0,1,3])
            with self.subTest(problem=problem),self.assertRaises(StudioError):
                improve_interior(points,triangles,fixed,**settings)
