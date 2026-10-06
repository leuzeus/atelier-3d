import copy
import math
import random
import unittest

from a3d.core import StudioError
from a3d.interior_grid_queries import InteriorGridQueries
from a3d.sewing import point_inside, segment_distance


def oracle_distance(p, polygon):
    return min(segment_distance(p, a, b) for a, b in zip(polygon, polygon[1:] + polygon[:1]))


def subdivide(polygon, count):
    return [[a[axis] + (b[axis]-a[axis])*k/count for axis in range(2)]
            for a, b in zip(polygon, polygon[1:] + polygon[:1]) for k in range(count)]


class InteriorGridQueryTests(unittest.TestCase):
    def verify_points(self, polygon, points):
        before = copy.deepcopy(polygon)
        queries = InteriorGridQueries(polygon)
        for p in points:
            self.assertEqual(queries.contains(p), point_inside(p, polygon), (p, polygon))
            actual, expected = queries.distance(p), oracle_distance(p, polygon)
            self.assertEqual(actual.hex(), expected.hex(), (p, polygon, actual, expected))
        self.assertEqual(polygon, before)
        self.assertEqual(queries.report()['qualification'], 'NONE')
        return queries

    def test_concave_negative_polygon_all_rows_and_boundary_vertices(self):
        polygon = [[-10., -7.], [8., -7.], [8., 9.], [3., 9.],
                   [3., -1.], [-2., -1.], [-2., 9.], [-10., 9.]]
        points = [[x*.5, y*.5] for y in range(-16, 21) for x in range(-23, 20)]
        self.verify_points(polygon, points + polygon)

    def test_repeated_subdivision_preserves_actual_source_oracle(self):
        polygon = subdivide([[-8., -3.], [9., -3.], [9., 2.], [1., 2.],
                             [1., 8.], [-8., 8.]], 35)
        points = [[x*.7, y*.6] for y in range(-7, 17) for x in range(-15, 17)]
        queries = self.verify_points(polygon, points)
        self.assertLess(queries.report()['counters']['segment_distance_evaluations'],
                        len(points)*len(polygon))
        self.assertEqual(queries.report()['counters']['compiled_rows'], 24)

    def test_strict_winding_at_intersections_nextafter_thresholds(self):
        polygon = [[0., 0.], [5., 0.], [2., 5.], [-3., 2.]]
        points = []
        for y in (0., 1., 2., 5., math.nextafter(2., math.inf), math.nextafter(2., -math.inf)):
            for a, b in zip(polygon, polygon[1:] + polygon[:1]):
                if (a[1] > y) != (b[1] > y):
                    x = (b[0]-a[0])*(y-a[1])/(b[1]-a[1])+a[0]
                    points.extend([[math.nextafter(x, -math.inf), y], [x, y],
                                   [math.nextafter(x, math.inf), y]])
        self.verify_points(polygon, points)

    def test_distance_thresholds_are_identical_binary64(self):
        polygon = subdivide([[0., 0.], [100., 0.], [100., 100.], [0., 100.]], 25)
        for scale in (.00001, .7, 1., 7.3):
            threshold = .38*scale
            points = [[30., math.nextafter(threshold, -math.inf)], [30., threshold],
                      [30., math.nextafter(threshold, math.inf)]]
            q = self.verify_points(polygon, points)
            for p in points:
                self.assertEqual(q.distance(p) < threshold, oracle_distance(p, polygon) < threshold)

    def test_random_concave_and_multiscale_coordinates(self):
        rng = random.Random(80231)
        for scale in (1e-12, 1e-6, 1., 1e8, 1e100):
            polygon = [[scale*radius*math.cos(k*math.pi/16),
                        scale*radius*math.sin(k*math.pi/16)]
                       for k in range(32) for radius in [1. if k % 2 else 2.]]
            points = [[rng.uniform(-3, 3)*scale, rng.uniform(-3, 3)*scale] for _ in range(150)]
            self.verify_points(polygon, points)

    def test_projection_cancellation_boxes_enclose_reconstructed_endpoint(self):
        # fl(a+(b-a)) need not equal b: a usual source-endpoint box is unsafe.
        polygon = [[1e16, 0.], [1., 2.], [-20., 3.], [-20., -5.]]
        self.assertNotEqual(polygon[0][0] + (polygon[1][0]-polygon[0][0]), polygon[1][0])
        points = [[0., 2.], [1., 2.], [.5, 2.], [-10., 1.], [1e16, 0.]]
        self.verify_points(polygon, points)

    def test_overflow_unbounded_projection_uses_original_scan(self):
        polygon = [[-1e308, 0.], [1e308, 0.], [1e308, 1.], [-1e308, 1.]]
        queries = self.verify_points(polygon, [[0., .5], [0., 2.], [1e308, .5]])
        self.assertEqual(queries.report()['distance_index'], 'FULL_SCAN')
        self.assertEqual(queries.report()['counters']['fallback_queries'], 3)

    def test_degenerate_repeated_vertices_keep_oracle_behavior(self):
        polygon = [[0., 0.], [0., 0.], [2., 0.], [2., 2.], [0., 2.], [0., 0.]]
        self.verify_points(polygon, [[0., 0.], [1., 0.], [1., 1.], [3., 3.]])

    def test_integer_source_and_equal_float_rows_keep_source_arithmetic(self):
        offset = 2**54
        polygon = [[offset, offset], [offset+21, offset], [offset+21, offset+23],
                   [offset+9, offset+23], [offset+9, offset+10], [offset, offset+10]]
        points = [[offset+x, offset+y] for y in range(-2, 27) for x in range(-2, 26)]
        points += [[offset+3, offset+4], [float(offset+3), float(offset+4)],
                   [offset+3, offset+4]]
        self.verify_points(polygon, points)

    def test_source_snapshot_and_report_are_not_mutable_aliases(self):
        polygon = [[0., 0.], [4., 0.], [4., 4.], [0., 4.]]
        queries = InteriorGridQueries(polygon)
        polygon[1][0] = 100.
        self.assertEqual(queries.distance([5., 1.]), 1.)
        report = queries.report()
        report['counters']['distance_queries'] = 10000
        self.assertEqual(queries.report()['counters']['distance_queries'], 1)

    def test_budget_and_deadline_callbacks_propagate_before_further_work(self):
        charged, checks = [], []
        def check():
            checks.append(True)
        queries = InteriorGridQueries(subdivide([[0., 0.], [9., 0.], [9., 9.], [0., 9.]], 60),
                                      check=check, reserve=charged.append)
        queries.contains([2., 2.]); queries.distance([2., 2.])
        self.assertEqual(sum(charged), queries.report()['counters']['work_steps'])
        self.assertEqual(len(checks), len(charged))
        def stopped():
            raise RuntimeError('deadline')
        queries._check = stopped
        before = queries.report()['counters'].copy()
        with self.assertRaisesRegex(RuntimeError, 'deadline'):
            queries.contains([3., 3.])
        self.assertEqual(queries.report()['counters']['row_segment_tests'], before['row_segment_tests'])
        with self.assertRaisesRegex(RuntimeError, 'deadline'):
            queries.distance([3., 3.])
        with self.assertRaisesRegex(RuntimeError, 'deadline'):
            InteriorGridQueries([[0., 0.], [1., 0.], [0., 1.]], check=stopped)

    def test_failed_row_compile_does_not_publish_partial_cache(self):
        queries = InteriorGridQueries(subdivide([[0., 0.], [9., 0.], [9., 9.], [0., 9.]], 60))
        calls = 0
        def reserve(n):
            nonlocal calls
            calls += 1
            if calls == 3:
                raise RuntimeError('work budget')
        queries._reserve = reserve
        with self.assertRaisesRegex(RuntimeError, 'work budget'):
            queries.contains([2., 2.])
        self.assertEqual(queries.report()['cached_rows'], 0)
        queries._reserve = None
        self.assertTrue(queries.contains([2., 2.]))

    def test_invalid_geometry_and_queries_fail_closed(self):
        for polygon in ([], [[0., 0.]], [[0., 0.], [1., 0.], [0., math.nan]],
                        [[0., 0.], [1., 0.], [0., math.inf]],
                        [[0., 0.], [1., 0.], [False, 1.]]):
            with self.assertRaises(StudioError):
                InteriorGridQueries(polygon)
        queries = InteriorGridQueries([[0., 0.], [1., 0.], [0., 1.]])
        for p in ([0., math.nan], [math.inf, 0.], [1.], [1., 2., 3.], [False, 0.]):
            with self.assertRaises(StudioError):queries.contains(p)
            with self.assertRaises(StudioError):queries.distance(p)

    def test_finite_integer_coordinates_with_overflowed_norm_use_oracle(self):
        size=10**200
        polygon=[[0,0],[size,0],[size,size],[0,size]]
        queries=InteriorGridQueries(polygon)
        self.assertEqual(queries.report()['distance_index'],'FULL_SCAN')
        for point in ([1,1],[size-1,1],[size//2,size//2]):
            expected=min(segment_distance(point,a,b) for a,b in
                zip(polygon,polygon[1:]+polygon[:1]))
            self.assertEqual(queries.distance(point).hex(),expected.hex())


if __name__ == '__main__':
    unittest.main()
