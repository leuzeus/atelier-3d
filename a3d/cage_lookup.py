"""Conservative candidate lookup for the existing source-UV cage narrow phase.

No UV-box tolerance or geometric approximation is used. Interval operations
enclose the SAME floating operations as ``pattern_assembly._cage_point``. A
candidate superset retains compiled order and all potentially overlapping cells.
The immutable local snapshot is never shared through a global cache.
"""
from dataclasses import dataclass
import copy
import math
from types import MappingProxyType

from .core import digest

_LOWER = -1e-8
_UPPER = 1 + 1e-8


def _exact_float(value):
    """Only exact finite coefficient representations may enter the hierarchy."""
    if type(value) not in (int, float):
        raise ValueError('Unproved coefficient type')
    converted = float(value)
    if not math.isfinite(converted) or converted != value:
        raise ValueError('Coefficient has no exact finite floating representation')
    return converted


def _freeze(value):
    if isinstance(value, dict):
        return MappingProxyType({key: _freeze(item) for key, item in value.items()})
    if isinstance(value, (list, tuple)):
        return tuple(_freeze(item) for item in value)
    return copy.deepcopy(value)


def _enclose(values):
    """One outward rounding around each endpoint operation; uncertainty aborts."""
    if any(type(value) is not float or not math.isfinite(value) for value in values):
        raise ArithmeticError('Unbounded floating interval')
    result = (math.nextafter(min(values), -math.inf), math.nextafter(max(values), math.inf))
    if not all(math.isfinite(value) for value in result):
        raise ArithmeticError('Unbounded outward rounding')
    return result


def _sub(a, b):
    return _enclose((a[0] - b[1], a[1] - b[0]))


def _mul(a, b):
    return _enclose(tuple(x * y for x in a for y in b))


def _div(a, b):
    if b[0] <= 0 <= b[1]:
        raise ArithmeticError('Denominator interval contains zero')
    return _enclose(tuple(x / y for x in a for y in b))


def _impossible(bounds, uv, lower, upper):
    ax, ay, bx, by, cx, cy, denominator = bounds
    dx = _sub((uv[0], uv[0]), ax)
    dy = _sub((uv[1], uv[1]), ay)
    beta = _div(_sub(_mul(dx, cy), _mul(dy, cx)), denominator)
    gamma = _div(_sub(_mul(bx, dy), _mul(by, dx)), denominator)
    # Preserve the original left-associative expression 1-beta-gamma.
    alpha = _sub(_sub((1., 1.), beta), gamma)
    return any(lo > upper or hi < lower for lo, hi in (alpha, beta, gamma))


@dataclass(frozen=True, slots=True)
class _Node:
    bounds: tuple
    indices: tuple = ()
    children: tuple = ()


@dataclass(frozen=True, slots=True)
class CageCandidates:
    entries: tuple
    visited_nodes: int
    retained_cells: int
    full_scan_fallback: bool


@dataclass(frozen=True, slots=True, init=False)
class CageLookup:
    """Input-bound immutable cage snapshot and optional interval hierarchy.

    ``frame`` and ``compiled`` are frozen copies for the unchanged narrow phase.
    Later mutations of caller inputs cannot change this snapshot. ``matches``
    is an explicit provenance check when a consumer wants to reuse the instance.
    Coefficients admit integers only when their computed values have exact finite
    float representations. Integer query points still use the full scan because
    their original arithmetic could retain integer intermediates.
    Explicit predicate bounds may widen the current narrow phase's bounds but
    cannot silently narrow them; such an unsupported configuration uses all cells.
    """
    frame: object
    compiled: tuple
    source_fingerprint: object
    _root: object
    _supports_intervals: bool
    bary_min: object
    bary_max: object

    def __init__(self, frame, compiled, check_time=None, *, leaf_size=16,
                 bary_min=_LOWER, bary_max=_UPPER):
        if type(leaf_size) is not int or leaf_size < 1:
            raise ValueError('Cage lookup leaf size must be a positive integer')
        if check_time is not None:
            check_time()
        object.__setattr__(self, 'frame', _freeze(frame))
        rows = tuple(_freeze(row) for row in compiled)
        object.__setattr__(self, 'compiled', rows)
        try:
            fingerprint = digest([frame, compiled])
        except (TypeError, ValueError, OverflowError):
            fingerprint = None
        object.__setattr__(self, 'source_fingerprint', fingerprint)
        object.__setattr__(self, 'bary_min', bary_min)
        object.__setattr__(self, 'bary_max', bary_max)
        coefficients = []
        supported = (bool(rows) and fingerprint is not None
            and type(bary_min) is float and type(bary_max) is float
            and math.isfinite(bary_min) and math.isfinite(bary_max)
            and bary_min <= _LOWER and bary_max >= _UPPER)
        for row in rows:
            if check_time is not None:
                check_time()
            try:
                _, _, a, b, c, denominator = row
                values = (a[0], a[1], b[0], b[1], c[0], c[1], denominator)
                if any(type(value) not in (int, float) or
                       (type(value) is float and not math.isfinite(value)) for value in values) or denominator == 0:
                    supported = False
                    break
                # Subtract in ORIGINAL types first. For example, integer b-a can
                # equal 1 exactly even when converting b before subtraction would
                # lose that value. The narrow phase keeps the original row.
                raw = (a[0], a[1], b[0]-a[0], b[1]-a[1], c[0]-a[0], c[1]-a[1], denominator)
                coefficient = tuple(_exact_float(value) for value in raw)
                coefficients.append(coefficient)
            except (TypeError, ValueError, IndexError, OverflowError):
                supported = False
                break

        def build(indices):
            if check_time is not None:
                check_time()
            bounds = tuple((min(coefficients[i][column] for i in indices),
                            max(coefficients[i][column] for i in indices)) for column in range(7))
            if len(indices) <= leaf_size:
                return _Node(bounds, tuple(indices))
            # Spatial ordering affects efficiency only, never the proof predicate.
            axis = 0 if bounds[0][1]-bounds[0][0] >= bounds[1][1]-bounds[1][0] else 1
            ordered = sorted(indices, key=lambda index: (coefficients[index][axis], index))
            middle = len(ordered)//2
            return _Node(bounds, children=(build(ordered[:middle]), build(ordered[middle:])))

        root = None
        if supported:
            # Separate signs so a node denominator never spans zero.
            groups = [tuple(i for i, values in enumerate(coefficients) if (values[-1] < 0) == negative)
                      for negative in (False, True)]
            root = tuple(build(indices) for indices in groups if indices)
        object.__setattr__(self, '_root', root)
        object.__setattr__(self, '_supports_intervals', supported)
        if check_time is not None:
            check_time()

    def matches(self, frame, compiled):
        try:
            return self.source_fingerprint is not None and digest([frame, compiled]) == self.source_fingerprint
        except (TypeError, ValueError, OverflowError):
            return False

    def query(self, uv, check_time=None):
        if check_time is not None:
            check_time()
        full = lambda visits: CageCandidates(self.compiled, visits, len(self.compiled), True)
        if (not self._supports_intervals or not isinstance(uv, (list, tuple)) or len(uv) != 2
                or any(type(value) is not float or not math.isfinite(value) for value in uv)):
            return full(0)
        selected = []
        stack = list(reversed(self._root))
        visits = 0
        try:
            while stack:
                if check_time is not None:
                    check_time()
                node = stack.pop()
                visits += 1
                if _impossible(node.bounds, uv, self.bary_min, self.bary_max):
                    continue
                if node.children:
                    stack.extend(reversed(node.children))
                else:
                    selected.extend(node.indices)
        except (ArithmeticError, OverflowError, ZeroDivisionError):
            return full(visits)
        entries = tuple(self.compiled[index] for index in sorted(selected))
        if check_time is not None:
            check_time()
        return CageCandidates(entries, visits, len(entries), False)

    def candidates(self, uv, check_time=None):
        return self.query(uv, check_time).entries
