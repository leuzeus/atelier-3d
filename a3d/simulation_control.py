"""Bounded observation of actual evaluated Cloth frames; never a physics solver."""
import math
import time
from .core import StudioError


class ConvergenceMonitor:
    def __init__(self, control, fps, max_frames, seam_tolerance_cm, clock=time.monotonic):
        required = {'max_seconds', 'min_frames', 'window_frames', 'velocity_tolerance_cm_s'}
        if set(control) != required:
            raise StudioError('Cloth convergence needs explicit time, minimum frame, window and velocity budgets')
        for name in ('max_seconds', 'velocity_tolerance_cm_s'):
            if type(control[name]) not in (int, float) or not math.isfinite(control[name]) or control[name] < 0:
                raise StudioError('Cloth convergence budget must be finite and nonnegative')
        if not 0 < control['max_seconds'] <= 3600:
            raise StudioError('Cloth convergence time budget must stay within zero to 3600 seconds')
        if any(type(control[name]) is not int or not 2 <= control[name] <= max_frames for name in ('min_frames', 'window_frames')):
            raise StudioError('Cloth convergence window and minimum must fit the declared frame budget')
        if not math.isfinite(fps) or fps <= 0 or not math.isfinite(seam_tolerance_cm) or seam_tolerance_cm < 0:
            raise StudioError('Cloth convergence requires positive frame rate and nonnegative seam tolerance')
        self.control = dict(control); self.fps = fps; self.max_frames = max_frames
        self.seam_tolerance = seam_tolerance_cm; self.clock = clock; self.start = clock()
        self.previous = None; self.last_frame = 0; self.stable = 0; self.maximum_velocity = None
        self.stop_reason = None

    def before_frame(self):
        if self.clock()-self.start >= self.control['max_seconds']:
            self.stop_reason = 'TIME_BUDGET'
            error = StudioError('Cloth time budget exhausted before measured convergence')
            error.simulation_outcome = 'INCOMPLETE'
            error.reason_category = 'simulation_budget'
            raise error

    def observe(self, frame, coordinates, seam_gap_cm, gates_valid):
        self.before_frame()
        if type(frame) is not int or frame != self.last_frame+1 or frame > self.max_frames:
            raise StudioError('Cloth convergence requires each consecutive actual evaluated frame')
        if (not coordinates or any(len(p) != 3 or any(type(x) not in (int, float) or not math.isfinite(x) for x in p) for p in coordinates)
                or type(gates_valid) is not bool or not math.isfinite(seam_gap_cm) or seam_gap_cm < 0):
            raise StudioError('Cloth convergence requires finite coordinates, gaps and actual hard-gate status')
        if self.previous is not None:
            if len(coordinates) != len(self.previous):
                raise StudioError('Cloth convergence observed a topology change')
            self.maximum_velocity = max(math.dist(a, b)*self.fps for a, b in zip(self.previous, coordinates))
            self.stable = self.stable+1 if (gates_valid and seam_gap_cm <= self.seam_tolerance
                and self.maximum_velocity <= self.control['velocity_tolerance_cm_s']) else 0
        self.previous = [list(p) for p in coordinates]; self.last_frame = frame
        converged = frame >= self.control['min_frames'] and self.stable >= self.control['window_frames']
        if converged: self.stop_reason = 'MEASURED_CONVERGENCE'
        elif frame == self.max_frames: self.stop_reason = 'FRAME_BUDGET'
        return converged

    def report(self):
        return {'mode': 'MEASURED_FRAME_VELOCITY_AND_SEAM_GAP', 'control': self.control,
                'stop_reason': self.stop_reason, 'evaluated_frames': self.last_frame,
                'stable_intervals': self.stable, 'maximum_velocity_cm_s': self.maximum_velocity,
                'elapsed_seconds': self.clock()-self.start, 'max_frames': self.max_frames,
                'seam_tolerance_cm': self.seam_tolerance, 'qualification': 'OBSERVATION_ONLY'}

    def require_convergence(self):
        if self.stop_reason != 'MEASURED_CONVERGENCE':
            error = StudioError('Cloth frame budget exhausted without measured convergence')
            error.simulation_outcome = 'INCOMPLETE'
            error.reason_category = 'simulation_budget'
            raise error
