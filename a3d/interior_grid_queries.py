"""Exact source-contour queries for repeated rows of an interior seed lattice.

Only query work is indexed: source vertices, winding arithmetic and the final
``sewing.segment_distance`` evaluation are unchanged. This is not admission.
Callbacks ``check()`` and ``reserve(work_steps)`` may raise to stop bounded work.
"""
import bisect
import heapq
import math

from .core import StudioError
from .sewing import segment_distance


def _point(value):
    if (not isinstance(value, (list, tuple)) or len(value) != 2 or
            any(isinstance(v, bool) or not isinstance(v, (int, float)) or
                not math.isfinite(v) for v in value)):
        raise StudioError('Interior grid queries require finite 2D coordinates')
    return tuple(value)


class InteriorGridQueries:
    """One-row winding cache plus conservative nearest-segment hierarchy.

    The nearest hierarchy uses L-infinity lower bounds, avoiding a replacement
    distance formula. Its boxes enclose *computed* segment projections, including
    cancellation in ``a + (b-a)``. Arithmetic that cannot be bounded safely uses
    the original full scan. The cache retains only the most recently queried y.
    """
    def __init__(self, polygon, *, check=None, reserve=None):
        self._check = check
        self._reserve = reserve
        self._counts = {'contains_queries': 0, 'distance_queries': 0,
                        'compiled_rows': 0, 'row_segment_tests': 0,
                        'segment_distance_evaluations': 0, 'box_tests': 0,
                        'fallback_queries': 0, 'work_steps': 0}
        self._work(1)
        if not isinstance(polygon, (list, tuple)) or len(polygon) < 3:
            raise StudioError('Interior grid queries require at least three source vertices')
        captured = []
        for offset in range(0, len(polygon), 128):
            chunk = polygon[offset:offset + 128]
            self._work(len(chunk))
            captured.extend(_point(p) for p in chunk)
        self._polygon = tuple(captured)
        self._segments = tuple(zip(self._polygon, self._polygon[1:] + self._polygon[:1]))
        self._row_y = None
        self._crossings = ()
        boxes = []
        safe = True
        for offset in range(0, len(self._segments), 128):
            chunk = self._segments[offset:offset + 128]
            self._work(len(chunk))
            for a, b in chunk:
                try:
                    d = [b[i] - a[i] for i in range(2)]
                    n = sum(v*v for v in d)
                    start = [a[i] + 0.0*d[i] for i in range(2)]
                    end = [a[i] + 1.0*d[i] for i in range(2)]
                    finite = all(math.isfinite(v) for v in (*d, n, *start, *end))
                except (OverflowError,ValueError):
                    finite = False
                if not finite:
                    # Exact integer norms can exceed binary64 while the
                    # unchanged distance oracle still has a finite result.
                    safe = False
                    boxes.append((0.,0.,0.,0.))
                    continue
                # t is clamped to [0, 1]. Floating multiplication and addition
                # are monotone, so these endpoints enclose every computed q.
                # math.dist converts integer coordinates to binary64 too.
                # Only boxes use that conversion; source/query arithmetic stays
                # unchanged, including winding with integer subtraction.
                boxes.append((min(float(a[0]), start[0], end[0]), min(float(a[1]), start[1], end[1]),
                              max(float(a[0]), start[0], end[0]), max(float(a[1]), start[1], end[1])))
        self._boxes = tuple(boxes)
        self._tree = self._build(tuple(range(len(boxes)))) if safe else None

    def _work(self, count):
        if self._check is not None:
            self._check()
        if self._reserve is not None:
            self._reserve(count)
        self._counts['work_steps'] += count

    def _build(self, indices):
        self._work(len(indices))
        box = (min(self._boxes[i][0] for i in indices),
               min(self._boxes[i][1] for i in indices),
               max(self._boxes[i][2] for i in indices),
               max(self._boxes[i][3] for i in indices))
        if len(indices) <= 8:
            return box, indices, None, None
        # Difference may overflow without invalidating the boxes. Ordering by
        # low then high avoids center overflow and is deterministic.
        axis = int(box[3] - box[1] > box[2] - box[0])
        ordered = tuple(sorted(indices, key=lambda i: (self._boxes[i][axis],
                                                       self._boxes[i][axis + 2], i)))
        middle = len(ordered)//2
        return box, None, self._build(ordered[:middle]), self._build(ordered[middle:])

    def contains(self, point):
        p = _point(point)
        self._counts['contains_queries'] += 1
        self._work(1)
        row_key = (type(p[1]), p[1])
        if self._row_y != row_key:
            crossings = []
            for offset in range(0, len(self._segments), 128):
                chunk = self._segments[offset:offset + 128]
                self._work(len(chunk))
                self._counts['row_segment_tests'] += len(chunk)
                for a, b in chunk:
                    if (a[1] > p[1]) != (b[1] > p[1]):
                        # Same binary64 expression and strict comparison as
                        # sewing.point_inside, including source row vertices.
                        crossing = (b[0]-a[0])*(p[1]-a[1])/(b[1]-a[1])+a[0]
                        # x < NaN is always false, just as in the full scan.
                        if not math.isnan(crossing):
                            crossings.append(crossing)
            crossings.sort()
            self._crossings = tuple(crossings)
            self._row_y = row_key
            self._counts['compiled_rows'] += 1
        return bool((len(self._crossings) - bisect.bisect_right(self._crossings, p[0])) % 2)

    def _lower_bound(self, point, box):
        self._counts['box_tests'] += 1
        gaps = []
        for axis in range(2):
            if point[axis] < box[axis]:
                gap = box[axis] - point[axis]
            elif point[axis] > box[axis + 2]:
                gap = point[axis] - box[axis + 2]
            else:
                gap = 0.0
            # Round outward so a rounded subtraction never overstates the
            # minimum component distance used by math.dist in the oracle.
            gaps.append(max(0.0, math.nextafter(gap, -math.inf)))
        return max(gaps)

    def _evaluate(self, point, indices, best):
        self._work(len(indices))
        for i in indices:
            a, b = self._segments[i]
            result = segment_distance(point, a, b)
            self._counts['segment_distance_evaluations'] += 1
            best = min(best, result)
        return best

    def distance(self, point):
        p = _point(point)
        self._counts['distance_queries'] += 1
        self._work(1)
        if self._tree is None:
            self._counts['fallback_queries'] += 1
            best = math.inf
            for offset in range(0, len(self._segments), 128):
                best = self._evaluate(p, range(offset, min(offset + 128, len(self._segments))), best)
            return best
        best = math.inf
        serial = 0
        pending = [(self._lower_bound(p, self._tree[0]), serial, self._tree)]
        while pending:
            self._work(1)
            bound, _, node = heapq.heappop(pending)
            if bound > best:
                continue
            _, indices, left, right = node
            if indices is not None:
                best = self._evaluate(p, indices, best)
            else:
                for child in (left, right):
                    lower = self._lower_bound(p, child[0])
                    if lower <= best:
                        serial += 1
                        heapq.heappush(pending, (lower, serial, child))
        return best

    def report(self):
        return {'version': 1, 'algorithm': 'source_row_winding_projection_bbox_linf',
                'source_segments': len(self._segments),
                'distance_index': 'CONSERVATIVE_HIERARCHY' if self._tree else 'FULL_SCAN',
                'cached_rows': int(self._row_y is not None),
                'counters': dict(self._counts), 'qualification': 'NONE'}
