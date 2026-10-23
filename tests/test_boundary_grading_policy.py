import copy
import unittest

from a3d.core import StudioError, digest
from a3d.boundary_grading_policy import material_row_reference, prepare_local_row_policy
from tests.test_garment_measurements import collar_cycle_fixture
from tests.test_pattern_ease_variant import fixture as variant_fixture


class BoundaryPolicy(unittest.TestCase):
    def inputs(self):
        compiled, _, _, _ = collar_cycle_fixture()
        ref = material_row_reference(compiled, 'textile.unusual', 'band.named', 'stop.a', 'stop.b', 0.)
        _, _, _, old, _, _ = variant_fixture()
        return compiled, ref, {'path': 'new-intent.json', 'sha256': 'd' * 64}, {
            'band.named': [], 'insert.named': ['free'], 'neck.named': ['free', 'side.a', 'side.b']
        }, {'minimum': .5, 'initial': 1., 'maximum': 1.5}, old['constraints'], old['budgets']

    def test_source_controls_generic_ids_closure_retained_and_inputs_immutable(self):
        args = self.inputs(); before = digest(args)
        policy = prepare_local_row_policy(*args)
        self.assertEqual(digest(args), before)
        self.assertEqual(policy['nominal_paths'][0]['path_kind'], 'open_material_span')
        self.assertEqual(policy['nominal_paths'][0]['joins'], [])
        self.assertEqual(policy['nominal_paths'][0]['engaged_links'], [])
        self.assertEqual({p for f in policy['families'] for p in f['pieces']}, set(args[3]))

    def test_all_protected_partners_refused_no_admission(self):
        args = list(self.inputs())
        args[3]['insert.named'] = ['free', 'anchor.a', 'anchor.b']
        args[3]['neck.named'] = ['real-neck', 'free', 'side.a', 'side.b']
        with self.assertRaisesRegex(StudioError, 'All attached row partners'):
            prepare_local_row_policy(*args)

    def test_real_unchanged_edges_force_zero_weights(self):
        args = self.inputs(); policy = prepare_local_row_policy(*args)
        for family in policy['families']:
            pid = family['pieces'][0]; weights = family['weights_by_piece'][pid]
            for name in args[3][pid]:
                for index in args[0]['textiles'][pid]['source_geometry']['edges'][name]:
                    self.assertEqual(weights[index], 0.)

    def test_stale_source_reference_refused(self):
        args = list(self.inputs()); args[1] = copy.deepcopy(args[1]); args[1]['source_material_length_cm'] += 1
        with self.assertRaisesRegex(StudioError, 'reference changed'):
            prepare_local_row_policy(*args)

    def test_unattached_upper_row_refused(self):
        compiled = self.inputs()[0]
        with self.assertRaisesRegex(StudioError, 'permanent source endpoint cycle'):
            material_row_reference(compiled, 'textile.unusual', 'band.named', 'stop.a', 'stop.b', 7.)

    def test_extra_or_missing_participant_protection_refused(self):
        for missing in (True, False):
            args = list(self.inputs()); args[3] = copy.deepcopy(args[3])
            if missing:
                del args[3]['insert.named']
            else:
                args[3]['phantom'] = []
            with self.assertRaisesRegex(StudioError, 'every participant'):
                prepare_local_row_policy(*args)

    def test_nonfinite_bounds_refused(self):
        args = list(self.inputs()); args[4] = dict(args[4], initial=float('nan'))
        with self.assertRaisesRegex(StudioError, 'finite'):
            prepare_local_row_policy(*args)

    def test_arc_taper_combines_real_connected_edges_and_preserves_protections(self):
        args = self.inputs()
        policy = prepare_local_row_policy(*args, weight_profile='SOURCE_ARC_QUADRATIC_TAPER')
        insert = next(f for f in policy['families'] if f['pieces'] == ['insert.named'])
        self.assertEqual(insert['weights_by_piece']['insert.named'], [0., 1., 0.])
        for family in policy['families']:
            self.assertTrue(all(0 <= w <= 1 for weights in family['weights_by_piece'].values() for w in weights))

    def test_weight_profile_is_explicit_and_unknown_method_refused(self):
        with self.assertRaisesRegex(StudioError, 'supported source weight profile'):
            prepare_local_row_policy(*self.inputs(), weight_profile='AI_COORDINATE_ADJUSTMENT')

    def test_frozen_reference_intervals_translate_without_changing_their_material_length(self):
        args = list(self.inputs())
        # Activate the middle source span, freeze the insert as a reference.
        args[3]['insert.named'] = ['free', 'anchor.a', 'anchor.b']
        args[3]['neck.named'] = ['free']
        policy = prepare_local_row_policy(*args)
        frozen = next(f for f in policy['families'] if f['pieces'] == ['insert.named'])
        self.assertEqual(frozen['scale_x'], {'minimum': 1., 'initial': 1., 'maximum': 1.})
        band = next(f for f in policy['families'] if f['pieces'] == ['band.named'])
        vertices = args[0]['textiles']['band.named']['source_geometry']['vertices']
        weights = band['weights_by_piece']['band.named']
        target = [p[0] + .5 * w * p[0] for p, w in zip(vertices, weights)]
        self.assertEqual(target[1] - target[0], 2.)
        self.assertEqual(target[4] - target[3], 2.)
        self.assertEqual(target[4] - target[0], 16.)


if __name__ == '__main__':
    unittest.main()
