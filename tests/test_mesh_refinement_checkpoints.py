import copy
import unittest
from a3d.mesh_refinement import improve_interior
from a3d.core import StudioError


class CooperativeRefinementTests(unittest.TestCase):
    def inputs(self):
        points=[[0.,0.],[3.,0.],[3.,2.],[0.,2.],[.1,.7]]
        faces=[[0,1,4],[1,2,4],[2,3,4],[3,0,4]]
        return points,faces,[0,1,2,3]

    def run_case(self,check=None):
        points,faces,boundary=self.inputs()
        return improve_interior(points,faces,boundary,target_angle=15,min_edge=.001,
                                max_displacement=.5,displacement_reference=points,check=check)

    def test_default_and_cooperative_outputs_are_exactly_equal(self):
        calls=[]
        expected=self.run_case()
        actual=self.run_case(calls.append)
        self.assertEqual(actual,expected)
        for phase in ('before_capture','after_capture','topology_face','metric_face','pass','vertex','target','trial',
                      'permanent_reference_validation','after_final_report'):
            self.assertIn('interior_refinement:'+phase,calls)

    def test_stop_inside_trial_preserves_caller_data(self):
        points,faces,boundary=self.inputs();before=copy.deepcopy([points,faces,boundary])
        def check(phase):
            if phase=='interior_refinement:metric_face' and seen[0]:raise StudioError('controlled stop')
            if phase=='interior_refinement:trial':seen[0]=True
        seen=[False]
        with self.assertRaisesRegex(StudioError,'controlled stop'):
            improve_interior(points,faces,boundary,target_angle=15,min_edge=.001,max_displacement=.5,
                             displacement_reference=points,check=check)
        self.assertEqual([points,faces,boundary],before)

    def test_final_checkpoint_is_required_after_digest_and_report(self):
        def check(phase):
            if phase=='interior_refinement:after_final_report':raise StudioError('expired after final report')
        with self.assertRaisesRegex(StudioError,'expired after final report'):self.run_case(check)

    def test_invalid_callback_refuses(self):
        with self.assertRaisesRegex(StudioError,'callable'):self.run_case(False)

if __name__=='__main__':unittest.main()
