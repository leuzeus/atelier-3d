import copy
import unittest

from a3d.core import StudioError
from a3d.motion_profiles import (motion_evidence_binding, sample_times, standard_motion_profile,
                                 validate_motion_profile, verify_sample_coverage)


def specification():
    return {'evaluated_geometry_sha256': 'a'*64, 'cache_key': 'b'*64,
            'bones': [{'name': bone+'.'+side} for bone in ('upper_arm', 'forearm', 'thigh', 'shin')
                      for side in ('left', 'right')]}


class MotionProfiles(unittest.TestCase):
    def test_clips_cover_start_finish_and_intermediate_pose_without_early_stop(self):
        rig = specification()
        for clip in ('walk', 'elbow_flexion', 'arm_raise'):
            profile = standard_motion_profile(clip, rig, 'explicit inspection test clip', frame_end=5)
            times = sample_times(profile)
            self.assertEqual(times, [1., 1.5, 2., 2.5, 3., 3.5, 4., 4.5, 5.])
            self.assertEqual(validate_motion_profile(profile, rig), profile)
            self.assertEqual(profile['axis_convention'], 'DERIVED_BONE_LOCAL_XYZ_REQUIRES_REVIEW')
            for track in profile['tracks']:
                self.assertEqual(track['keys'][0]['frame'], 1)
                self.assertEqual(track['keys'][-1]['frame'], 5)

    def test_missing_or_stale_rig_and_ambiguous_channels_are_refused(self):
        rig = specification(); profile = standard_motion_profile('walk', rig, 'explicit test')
        for change in ('geometry', 'rig', 'missing_bone', 'duplicate', 'coverage', 'order', 'finite'):
            bad = copy.deepcopy(profile)
            if change == 'geometry': bad['body_geometry_sha256'] = 'c'*64
            if change == 'rig': bad['rig_specification_sha256'] = 'd'*64
            if change == 'missing_bone': bad['tracks'][0]['bone'] = 'invented.bone'
            if change == 'duplicate': bad['tracks'].append(copy.deepcopy(bad['tracks'][0]))
            if change == 'coverage': bad['tracks'][0]['keys'][-1]['frame'] -= 1
            if change == 'order': bad['tracks'][0]['keys'].reverse()
            if change == 'finite': bad['tracks'][0]['keys'][0]['radians'] = float('nan')
            with self.subTest(change=change), self.assertRaises(StudioError): validate_motion_profile(bad, rig)

    def test_sampling_budget_and_topology_correspondence_are_qualified_separately(self):
        profile = standard_motion_profile('arm_raise', specification(), 'explicit test', frame_end=3)
        samples = [{'time': time, 'topology_sha256': 'd'*64, 'vertices_cm': [[time, 0., 0.], [time, 1., 0.]]}
                   for time in sample_times(profile)]
        complete = verify_sample_coverage(profile, samples)
        self.assertEqual(complete['status'], 'CLIP_SAMPLES_COMPLETE')
        self.assertEqual(complete['continuous_collision_qualification'], 'NOT_GRANTED')
        self.assertEqual(complete['fitting'], 'NOT_EXECUTED')
        tight = dict(profile, max_increment_cm=.1)
        self.assertEqual(verify_sample_coverage(tight, samples)['status'], 'TEMPORAL_RESOLUTION_INSUFFICIENT')
        # Removing the midpoint would miss a moving obstacle's transit even if
        # endpoint geometry was unchanged. Missing evidence is refused.
        with self.assertRaises(StudioError): verify_sample_coverage(profile, samples[::2])
        bad = copy.deepcopy(samples); bad[2]['topology_sha256'] = 'e'*64
        with self.assertRaises(StudioError): verify_sample_coverage(profile, bad)
        bad = copy.deepcopy(samples); bad[2]['vertices_cm'].append([0., 0., 0.])
        with self.assertRaises(StudioError): verify_sample_coverage(profile, bad)

    def test_action_weights_topology_and_recipe_changes_invalidate_evidence(self):
        rig = specification(); profile = standard_motion_profile('elbow_flexion', rig, 'explicit test')
        original = motion_evidence_binding(profile, rig, 'c'*64, 'd'*64, 'e'*64)
        for change in ('action', 'weights', 'topology', 'profile'):
            data = copy.deepcopy(profile); action, weights, topology = 'c'*64, 'd'*64, 'e'*64
            if change == 'action': action = 'f'*64
            if change == 'weights': weights = 'f'*64
            if change == 'topology': topology = 'f'*64
            if change == 'profile': data['tracks'][0]['keys'][1]['radians'] -= .1
            with self.subTest(change=change):
                self.assertNotEqual(motion_evidence_binding(data, rig, action, weights, topology), original)


if __name__ == '__main__':
    unittest.main()
