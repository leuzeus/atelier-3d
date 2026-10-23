"""Exact clipping geometry and unchanged budget gates; no product fixture."""
import copy
from fractions import Fraction as F
import unittest
from unittest.mock import patch

from a3d import material_sample_carrier as uv
from a3d.core import StudioError


def points(*rows):
    return [tuple(F(value) for value in row) for row in rows]


def budget(**values):
    return uv._Budget(values, None, lambda: 0.)


def rectangle():
    return {'id': 'source', 'uv_cm': [[0, 0], [4, 0], [4, 2], [0, 2]],
        'vertex_ids': ['a', 'b', 'c', 'd'], 'face_ids': ['lower', 'upper'],
        'triangles': [[0, 1, 2], [0, 2, 3]]}


class MaterialExactClippingTests(unittest.TestCase):
    def test_strict_separation_on_either_axis_in_both_directions(self):
        base = points((0, 0), (1, 0), (0, 1))
        for delta in ((2, 0), (-2, 0), (0, 2), (0, -2)):
            shifted = [(p[0] + delta[0], p[1] + delta[1]) for p in base]
            for a, b in ((base, shifted), (shifted, base)):
                with self.subTest(delta=delta, reversed=a is shifted):
                    with patch.object(uv, '_cross', side_effect=AssertionError('unneeded clipping')):
                        self.assertEqual(uv._clip(a, b, budget()), [])

    def test_extremely_close_strict_gap_stays_exact(self):
        gap = F(1, 10**1000)
        left = points((0, 0), (1, 0), (1, 1))
        right = points((1 + gap, 0), (2, 0), (1 + gap, 1))
        self.assertEqual(float(1 + gap), 1.)  # IEEE would lose this separation.
        with patch.object(uv, '_cross', side_effect=AssertionError('float-like fallback')):
            self.assertEqual(uv._clip(left, right, budget()), [])

    def test_large_exact_translation_never_casts_to_float(self):
        origin = F(2**4000)
        left = points((origin, origin), (origin + 1, origin), (origin, origin + 1))
        right = points((origin + 3, origin), (origin + 4, origin), (origin + 3, origin + 1))
        with patch.object(uv, '_cross', side_effect=AssertionError('unneeded arithmetic')):
            self.assertEqual(uv._clip(left, right, budget()), [])

    def test_containment_preserves_exact_polygon(self):
        large = points((0, 0), (4, 0), (0, 4))
        small = points((0, 0), (1, 0), (0, 1))
        self.assertEqual(uv._clip(small, large, budget()), small)
        self.assertEqual(set(uv._clip(large, small, budget())), set(small))

    def test_rational_overlap_with_both_windings(self):
        a = points((0, 0), (2, 0), (0, 2))
        b = points((F(1, 3), 0), (F(4, 3), 0), (F(1, 3), 1))
        expected = set(b)
        for source in (a, list(reversed(a))):
            for target in (b, list(reversed(b))):
                result = uv._clip(source, target, budget())
                self.assertEqual(set(result), expected)
                self.assertEqual(uv._area(result), F(1, 2))

    def test_shared_edge_remains_a_line_with_both_windings(self):
        a = points((0, 0), (1, 0), (0, 1))
        b = points((0, 0), (1, 0), (0, -1))
        for source in (a, list(reversed(a))):
            for target in (b, list(reversed(b))):
                result = uv._clip(source, target, budget())
                self.assertEqual(set(result), {(F(0), F(0)), (F(1), F(0))})
                self.assertEqual(uv._area(result), 0)

    def test_tangent_vertex_uses_historical_clipping(self):
        a = points((0, 0), (1, 0), (0, 1))
        b = points((1, 0), (2, 0), (1, 1))
        with patch.object(uv, '_cross', wraps=uv._cross) as cross:
            self.assertEqual(uv._clip(a, b, budget()), [(F(1), F(0))])
        self.assertGreater(cross.call_count, 0)

    def test_equal_bounds_can_still_be_disjoint(self):
        a = points((0, 0), (1, 0), (0, 1))
        b = points((1, 1), (2, 1), (1, 2))
        with patch.object(uv, '_cross', wraps=uv._cross) as cross:
            self.assertEqual(uv._clip(a, b, budget()), [])
        self.assertGreater(cross.call_count, 0)

    def test_inputs_immutable_and_empty_polygon_supported(self):
        a = points((0, 0), (1, 0), (0, 1))
        b = points((2, 0), (3, 0), (2, 1))
        old = copy.deepcopy([a, b])
        self.assertEqual(uv._clip(a, b, budget()), [])
        self.assertEqual(old, [a, b])
        self.assertEqual(uv._clip([], b, budget()), [])

    def test_deadline_refused_before_bounds_arithmetic(self):
        b = budget()
        b.clock = lambda: 60.
        with patch.object(uv, '_cross', side_effect=AssertionError('deadline bypass')):
            with self.assertRaises(StudioError) as caught:
                uv._clip(points((0, 0), (1, 0), (0, 1)), points((2, 0), (3, 0), (2, 1)), b)
        self.assertEqual(caught.exception.reason, 'DEADLINE_EXHAUSTED')

    def test_deadline_rechecked_before_separated_return(self):
        b = budget()
        calls = [0]
        def clock():
            calls[0] += 1
            return 0. if calls[0] == 1 else 60.
        b.clock = clock
        with self.assertRaises(StudioError) as caught:
            uv._clip(points((0, 0), (1, 0), (0, 1)), points((2, 0), (3, 0), (2, 1)), b)
        self.assertEqual(caught.exception.reason, 'DEADLINE_EXHAUSTED')
        self.assertEqual(calls[0], 2)

    def test_deadline_rechecked_after_real_clipping(self):
        b = budget()
        value = [0.]
        b.clock = lambda: value[0]
        original = b.check
        def check(phase):
            if phase == 'exact clipping return':
                value[0] = 60.
            original(phase)
        b.check = check
        with self.assertRaises(StudioError) as caught:
            uv._clip(points((0, 0), (1, 0), (0, 1)), points((0, 0), (2, 0), (0, 2)), b)
        self.assertEqual(caught.exception.reason, 'DEADLINE_EXHAUSTED')

    def test_invalid_clock_cannot_take_separated_shortcut(self):
        b = budget()
        b.clock = lambda: float('nan')
        with self.assertRaises(StudioError) as caught:
            uv._clip(points((0, 0), (1, 0), (0, 1)), points((2, 0), (3, 0), (2, 1)), b)
        self.assertEqual(caught.exception.reason, 'INVALID_CLOCK')

    def test_computed_intersection_precision_limit_unchanged(self):
        da, db = 2**32 - 5, 2**32 - 17
        a = points((0, 0), (F(da - 1, da), F(-3*db + 1, db)), (0, -3))
        b = points((0, -2), (1, -1), (0, 1))  # Boxes overlap: real clipping required.
        with self.assertRaises(StudioError) as caught:
            uv._clip(a, b, budget(max_fraction_bits=64))
        self.assertEqual(caught.exception.reason, 'BUDGET_EXHAUSTED')
        self.assertIn('intersection precision', str(caught.exception))

    def test_public_input_precision_still_refuses_before_clipping(self):
        source = rectangle()
        source['uv_cm'][0][0] = '1/' + str(2**4096 + 1)
        with self.assertRaises(StudioError) as caught:
            uv.build_material_sample_carrier(source, rectangle(), [], clock=lambda: 0.)
        self.assertEqual(caught.exception.reason, 'BUDGET_EXHAUSTED')
        self.assertIn('rational precision', str(caught.exception))

    def test_public_pair_work_is_not_skipped_for_separated_pairs(self):
        result = uv.build_rectangular_material_carrier(rectangle(), ['a', 'b', 'c', 'd'],
            columns=3, rows=2, clock=lambda: 0.)
        ns, nc, nv = 2, 12, 4
        expected = ns*(ns-1)//2 + nc*(nc-1)//2 + ns*nc + nv*nc
        self.assertEqual(result['receipt']['work']['pair_checks'], expected)
        self.assertEqual(result['qualification'], 'NONE')

    def test_public_pair_budget_still_refuses_before_work(self):
        with self.assertRaises(StudioError) as caught:
            uv.build_rectangular_material_carrier(rectangle(), ['a', 'b', 'c', 'd'],
                columns=3, rows=2, budgets={'max_pair_checks': 138}, clock=lambda: 0.)
        self.assertEqual(caught.exception.reason, 'BUDGET_EXHAUSTED')


if __name__ == '__main__':
    unittest.main()
