import copy
import json
import unittest
from a3d.native_transport import compact_preparation_reply


class NativeTransport(unittest.TestCase):
    def test_full_frame_and_mesh_arrays_stay_in_the_exact_receipt(self):
        result = {'operation': 'transition_pattern_assembly', 'stage': 'mount', 'simulation': 'PASS',
                  'qualification': 'ASSEMBLY_PHYSICS_ONLY', 'accepted': False,
                  'receipt': {'path': 'evidence/full.json', 'sha256': 'a'*64},
                  'candidate_cm': [[1., 2., 3.]]*10000,
                  'cloth_runs': [{'simulation': 'PASS', 'frames': [{'frame': i, 'faces': [1, 2, 3]*100} for i in range(1000)],
                                  'executed': {'settings': {'use_sewing_springs': True}},
                                  'final_gap_cm': .1, 'execution_control': {'stop_reason': 'MEASURED_CONVERGENCE'}}]}
        original = copy.deepcopy(result); reply = compact_preparation_reply(result)
        self.assertEqual(result, original)
        self.assertLess(len(json.dumps(reply)), 1200)
        self.assertEqual(reply['cloth_runs'][0]['evaluated_frames'], 1000)
        self.assertTrue(reply['cloth_runs'][0]['sewing_springs'])
        self.assertEqual(reply['transport']['full_evidence'], result['receipt'])
        self.assertFalse(reply['accepted'])
        self.assertEqual(reply['qualification'], 'ASSEMBLY_PHYSICS_ONLY')

    def test_reply_without_a_persisted_receipt_is_not_trimmed(self):
        value = {'status': 'NEEDS_CORRECTION', 'diagnostic': 'useful failure evidence'}
        self.assertEqual(compact_preparation_reply(value), value)
