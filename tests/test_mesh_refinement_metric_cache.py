"""Cache correctness and real arithmetic savings; no native fitting claims."""
import math
import unittest
from unittest import mock

from a3d.cloth_metrics import triangle_metrics
from a3d.mesh_refinement import improve_interior


class CommittedMetricCache(unittest.TestCase):
    def test_unchanged_faces_are_measured_at_entry_and_terminal_audit(self):
        points=[[float(x),float(y)] for y in range(5) for x in range(5)]
        faces=[]
        for y in range(4):
            for x in range(4):
                a=y*5+x
                faces.extend([[a,a+1,a+6],[a,a+6,a+5]])
        checks=[]
        with mock.patch('a3d.mesh_refinement.triangle_metrics',wraps=triangle_metrics) as measure:
            result,report=improve_interior(points,faces,(),target_angle=15.,
                min_edge=.1,max_displacement=.5,check=checks.append)
        self.assertEqual(result,points)
        self.assertEqual(measure.call_count,2*len(faces))
        self.assertGreater(checks.count('interior_refinement:metric_face'),len(faces))
        self.assertTrue(report['target_reached'])

    def test_accepted_moves_invalidate_metrics_and_trials_never_poison_cache(self):
        points=[[0.,0.],[2.,0.],[2.,2.],[0.,2.],[.2,.2]]
        faces=[[0,1,4],[1,2,4],[2,3,4],[3,0,4]]
        result,report=improve_interior(points,faces,(),target_angle=25.,
            min_edge=.1,max_displacement=.8)
        self.assertGreater(report['accepted_vertex_moves'],0)
        rows=[triangle_metrics([result[i] for i in face]) for face in faces]
        self.assertEqual(report['min_angle_after_degrees'],min(r['min_angle_degrees'] for r in rows))
        self.assertEqual(report['min_edge_after_cm'],min(min(r['edges_cm']) for r in rows))
        self.assertEqual(report['remaining_bad_faces'],[i for i,r in enumerate(rows)
            if r['min_angle_degrees']<25.-1e-7 or min(r['edges_cm'])<.1])
        self.assertEqual(result[:4],points[:4])
        self.assertLessEqual(math.dist(result[4],points[4]),.8)


if __name__=='__main__':unittest.main()
