import unittest
from a3d.core import StudioError
from a3d.simulation_control import ConvergenceMonitor


def monitor(clock=lambda: 0.):
    return ConvergenceMonitor({'max_seconds': 5., 'min_frames': 4, 'window_frames': 2,
                               'velocity_tolerance_cm_s': .1}, 24., 10, .2, clock=clock)


class SimulationControl(unittest.TestCase):
    def test_only_consecutive_measured_stability_and_closed_seams_can_converge(self):
        control = monitor()
        self.assertFalse(control.observe(1, [[0., 0., 0.]], .1, True))
        self.assertFalse(control.observe(2, [[0., 0., 1.]], .1, True))
        self.assertFalse(control.observe(3, [[0., 0., 1.]], .1, True))
        self.assertTrue(control.observe(4, [[0., 0., 1.]], .1, True))
        control.require_convergence()
        self.assertEqual(control.report()['stop_reason'], 'MEASURED_CONVERGENCE')

    def test_failed_contacts_or_open_seams_reset_the_stability_window(self):
        control = monitor()
        for frame in range(1, 11):
            converged = control.observe(frame, [[0., 0., 0.]], .3 if frame%2 else .1, frame%2 == 1)
            self.assertFalse(converged)
        self.assertEqual(control.report()['stop_reason'], 'FRAME_BUDGET')
        with self.assertRaises(StudioError) as raised: control.require_convergence()
        self.assertEqual(raised.exception.simulation_outcome, 'INCOMPLETE')

    def test_timeout_is_incomplete_and_never_a_success(self):
        ticks = iter([0., 10.]); control = monitor(clock=lambda: next(ticks))
        with self.assertRaises(StudioError) as raised: control.before_frame()
        self.assertEqual(raised.exception.simulation_outcome, 'INCOMPLETE')

    def test_missing_frames_and_changed_topology_are_refused(self):
        control = monitor()
        with self.assertRaises(StudioError): control.observe(2, [[0., 0., 0.]], 0., True)
        control.observe(1, [[0., 0., 0.]], 0., True)
        with self.assertRaises(StudioError): control.observe(2, [[0., 0., 0.], [1., 0., 0.]], 0., True)
