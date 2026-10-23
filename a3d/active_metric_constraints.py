"""Bounded active principal constraints for an explicitly selected guide solver.

Linearized feasibility never admits a step: the caller retains its nonlinear
material envelopes, fixed controls, displacement cap and descent check.
"""
from __future__ import annotations

import math

from .cloth_metrics import principal_stretches
from .core import StudioError, sha


MODE = 'ACTIVE_PRINCIPAL_CONE_V1'
MAX_SWEEPS = 256
RESIDUAL_TOLERANCE = 1e-12
MAX_CONTROLS = 70000
MAX_FACES = 131072
WITNESS_LIMIT = 32
OBSERVED_CONSTRAINT_POLICY = 'RETAIN_NONLINEAR_VIOLATIONS_V1'


class ConstraintProjectionRefused(StudioError):
    """A bounded numerical refusal; global deadline errors are not this type."""
    def __init__(self, reason, **details):
        self.diagnostic = {'reason': reason, **details, 'qualification': 'NONE'}
        super().__init__('Active principal constraint projection refused: '+reason)


def _finite(value):
    return type(value) in (int, float) and math.isfinite(value)


def _vector(value, size):
    return isinstance(value, (list, tuple)) and len(value) == size and all(_finite(x) for x in value)


def _sum(values):
    # Catch arithmetic here, where no deadline callback is evaluated. Global
    # budget exceptions must never become an ordinary projection refusal.
    try:
        return math.fsum(values)
    except ConstraintProjectionRefused:
        raise
    except (OverflowError, ValueError) as error:
        raise ConstraintProjectionRefused('UNREPRESENTABLE_PROJECTION_ARITHMETIC') from error


def _dot(a, b):
    return _sum(x*y for x, y in zip(a, b))


def _principal_gradients(uv, points):
    """Gradients of simple positive singular values, with no world-axis choice."""
    x1, y1 = (uv[1][k]-uv[0][k] for k in (0, 1))
    x2, y2 = (uv[2][k]-uv[0][k] for k in (0, 1))
    det = x1*y2-x2*y1
    if not math.isfinite(det) or abs(det) < 1e-12:
        raise ConstraintProjectionRefused('UNREPRESENTABLE_SOURCE_DIFFERENTIAL')
    gradients = [((y1-y2)/det, (x2-x1)/det), (y2/det, -x2/det), (-y1/det, x1/det)]
    fu = [_sum((p[k]-points[0][k])*g[0] for p, g in zip(points, gradients)) for k in range(3)]
    fv = [_sum((p[k]-points[0][k])*g[1] for p, g in zip(points, gradients)) for k in range(3)]
    a, b, d = _dot(fu, fu), _dot(fu, fv), _dot(fv, fv)
    gap = math.hypot(a-d, 2*b); scale = max(abs(a), abs(b), abs(d))
    if not all(math.isfinite(v) for v in (a, b, d, gap)) or scale == 0:
        raise ConstraintProjectionRefused('COLLAPSED_ACTIVE_TARGET_DIFFERENTIAL')
    if gap <= 128*math.ulp(scale):
        raise ConstraintProjectionRefused('REPEATED_ACTIVE_SINGULAR_VALUE')
    angle = .5*math.atan2(2*b, a-d)
    vectors = [(-math.sin(angle), math.cos(angle)), (math.cos(angle), math.sin(angle))]
    values = []; rows = []
    for vector in vectors:
        image = [vector[0]*x+vector[1]*y for x, y in zip(fu, fv)]
        sigma = math.hypot(*image)
        if not math.isfinite(sigma) or sigma <= 128*math.ulp(math.sqrt(scale)):
            raise ConstraintProjectionRefused('ZERO_ACTIVE_SINGULAR_VALUE')
        left = [value/sigma for value in image]
        rows.append([[_dot(g, vector)*value for value in left] for g in gradients])
        values.append(sigma)
    return values, rows


def _validate_direction(direction, diagonal, fixed, check_time):
    if (not isinstance(direction, (list, tuple)) or not 1 <= len(direction) <= MAX_CONTROLS
            or not isinstance(diagonal, (list, tuple)) or len(diagonal) != len(direction)
            or not isinstance(fixed, (set, frozenset, list, tuple))
            or any(type(i) is not int or not 0 <= i < len(direction) for i in fixed)
            or len(set(fixed)) != len(fixed)):
        raise ConstraintProjectionRefused('INVALID_DIRECTION_LAYOUT')
    for index, (row, weight) in enumerate(zip(direction, diagonal)):
        if index % 128 == 0: check_time()
        if not _vector(row, 3) or not _finite(weight) or weight <= 0:
            raise ConstraintProjectionRefused('NONFINITE_DIRECTION_OR_NONPOSITIVE_WEIGHT')


def _project_halfspaces(direction, diagonal, rows, fixed, check_time):
    """Weighted Hildreth projection with fixed, versioned numerical budgets."""
    _validate_direction(direction, diagonal, fixed, check_time)
    if not isinstance(rows, (list, tuple)) or len(rows) > 2*MAX_FACES:
        raise ConstraintProjectionRefused('INVALID_CONSTRAINT_LAYOUT')
    denominators = []
    inverse = [0. if i in fixed else 1./value for i, value in enumerate(diagonal)]
    if any(not math.isfinite(value) for value in inverse):
        raise ConstraintProjectionRefused('UNREPRESENTABLE_INVERSE_WEIGHT')
    for index, support in enumerate(rows):
        if index % 128 == 0: check_time()
        if (not isinstance(support, (list, tuple)) or not 1 <= len(support) <= 3
                or any(not isinstance(pair, (list, tuple)) or len(pair) != 2
                    or type(pair[0]) is not int or not 0 <= pair[0] < len(direction)
                    or pair[0] in fixed or not _vector(pair[1], 3) for pair in support)
                or len({i for i, _ in support}) != len(support)):
            raise ConstraintProjectionRefused('INVALID_FREE_CONSTRAINT_SUPPORT')
        q = _sum(inverse[i]*_dot(row, row) for i, row in support)
        if not math.isfinite(q) or q <= 0:
            raise ConstraintProjectionRefused('DEGENERATE_FREE_CONSTRAINT')
        denominators.append(q)
    result = [[0., 0., 0.] if i in fixed else list(row) for i, row in enumerate(direction)]
    multipliers = [0.]*len(rows)

    def residuals():
        violation = complementarity = 0.
        for index, (support, multiplier) in enumerate(zip(rows, multipliers)):
            if index % 128 == 0: check_time()
            value = _sum(_dot(row, result[i]) for i, row in support)
            if not math.isfinite(value):
                raise ConstraintProjectionRefused('NONFINITE_PROJECTION_RESIDUAL')
            violation = max(violation, value)
            if multiplier > 0: complementarity = max(complementarity, abs(value))
        return violation, complementarity

    initial_residual = residuals()[0]
    for sweep in range(MAX_SWEEPS):
        check_time()
        for index, (support, q) in enumerate(zip(rows, denominators)):
            if index % 128 == 0: check_time()
            value = _sum(_dot(row, result[i]) for i, row in support)
            if not math.isfinite(value):
                raise ConstraintProjectionRefused('NONFINITE_PROJECTION_RESIDUAL')
            multiplier = max(0., multipliers[index]+value/q)
            if not math.isfinite(multiplier):
                raise ConstraintProjectionRefused('NONFINITE_PROJECTION_MULTIPLIER')
            delta = multiplier-multipliers[index]; multipliers[index] = multiplier
            for i, row in support:
                for k in range(3): result[i][k] -= delta*inverse[i]*row[k]
                if not _vector(result[i], 3):
                    raise ConstraintProjectionRefused('NONFINITE_PROJECTED_DIRECTION')
        violation, complementarity = residuals()
        if max(violation, complementarity) <= RESIDUAL_TOLERANCE:
            return result, {'sweeps': sweep+1, 'constraints': len(rows),
                'maximum_initial_normalized_residual': initial_residual,
                'maximum_final_normalized_residual': violation,
                'maximum_dual_complementarity_residual': complementarity}
    raise ConstraintProjectionRefused('PROJECTION_ITERATION_BUDGET_EXHAUSTED',
        max_sweeps=MAX_SWEEPS, maximum_normalized_residual=violation,
        maximum_dual_complementarity_residual=complementarity)


def project_active_principal_direction(points, direction, diagonal, faces, metric_envelopes,
                                       fixed, check_time, *, observed_constraints=()):
    """Return a finite candidate direction and observations, never an admission."""
    if not callable(check_time):
        raise ConstraintProjectionRefused('MISSING_DEADLINE_CALLBACK')
    check_time()
    _validate_direction(direction, diagonal, fixed, check_time)
    if (not isinstance(points, (list, tuple)) or len(points) != len(direction)
            or not isinstance(faces, (list, tuple)) or not 1 <= len(faces) <= MAX_FACES
            or not isinstance(metric_envelopes, dict) or not metric_envelopes):
        raise ConstraintProjectionRefused('INVALID_ACTIVE_METRIC_LAYOUT')
    for index, point in enumerate(points):
        if index % 128 == 0: check_time()
        if not _vector(point, 3): raise ConstraintProjectionRefused('NONFINITE_CURRENT_POINT')
    for pid, bounds in metric_envelopes.items():
        check_time()
        if not isinstance(pid, str) or not pid or not _vector(bounds, 2) or not 0 <= bounds[0] <= bounds[1]:
            raise ConstraintProjectionRefused('INVALID_METRIC_ENVELOPE')
    if (not isinstance(observed_constraints, (list, tuple, set, frozenset))
            or len(observed_constraints) > 2*len(faces)):
        raise ConstraintProjectionRefused('INVALID_OBSERVED_CONSTRAINT_LAYOUT')
    retained = set()
    for ordinal, item in enumerate(observed_constraints):
        if ordinal % 128 == 0: check_time()
        if (not isinstance(item, (list, tuple)) or len(item) != 2
                or type(item[0]) is not int or not 0 <= item[0] < len(faces)
                or type(item[1]) is not str or item[1] not in ('LOWER', 'UPPER')):
            raise ConstraintProjectionRefused('INVALID_OBSERVED_CONSTRAINT_IDENTITY')
        retained.add(tuple(item))
    rows = []; witnesses = []; active_count = 0; fixed_count = 0
    roundoff_count = retained_additional_count = retained_overlap_count = 0
    try:
        for ordinal, face in enumerate(faces):
            if ordinal % 128 == 0: check_time()
            if not isinstance(face, (list, tuple)) or len(face) != 3:
                raise ConstraintProjectionRefused('INVALID_SOURCE_FACE_LAYOUT')
            uv, indices, pid = face
            if (not isinstance(uv, (list, tuple)) or len(uv) != 3 or any(not _vector(p, 2) for p in uv)
                    or not isinstance(indices, (list, tuple)) or len(indices) != 3
                    or any(type(i) is not int or not 0 <= i < len(points) for i in indices)
                    or len(set(indices)) != 3 or not isinstance(pid, str) or pid not in metric_envelopes):
                raise ConstraintProjectionRefused('INVALID_SOURCE_FACE_OR_OWNER')
            xyz = [points[i] for i in indices]; measured = principal_stretches(uv, xyz)
            if measured is None or not all(_finite(x) for x in measured):
                raise ConstraintProjectionRefused('UNMEASURABLE_CURRENT_TRIANGLE', face_ordinal=ordinal)
            low, high = metric_envelopes[pid]; roundoff = 1e-10*max(1., high)
            if measured[0] < low-roundoff or measured[1] > high+roundoff:
                raise ConstraintProjectionRefused('CURRENT_POINT_OUTSIDE_UNCHANGED_ENVELOPE', face_ordinal=ordinal)
            active = []
            for singular, sign, bound, kind, at_roundoff in (
                    (0, -1., low, 'LOWER', measured[0] <= low+roundoff),
                    (1, 1., high, 'UPPER', measured[1] >= high-roundoff)):
                observed = (ordinal, kind) in retained
                roundoff_count += int(at_roundoff)
                retained_additional_count += int(observed and not at_roundoff)
                retained_overlap_count += int(observed and at_roundoff)
                if at_roundoff or observed:
                    origins = (['METRIC_ENVELOPE_ROUNDOFF'] if at_roundoff else [])
                    if observed: origins.append('OBSERVED_NONLINEAR_VIOLATION')
                    active.append((singular, sign, bound, origins))
            if not active: continue
            active_count += len(active)
            # A completely fixed face has no direction. Its current geometry
            # was measured above; no singular derivative is needed at all.
            if all(i in fixed for i in indices):
                fixed_count += len(active); continue
            sigma, gradients = _principal_gradients(uv, xyz)
            if max(abs(a-b) for a, b in zip(sigma, measured)) > 1e-9*max(1., high):
                raise ConstraintProjectionRefused('ANALYTICAL_AND_CANONICAL_METRICS_DISAGREE', face_ordinal=ordinal)
            # Retain only the side identity from earlier rejected steps. Every
            # derivative below is rebuilt at the current coordinates.
            for singular, sign, bound, origins in active:
                support = [(i, [sign*x for x in gradient]) for i, gradient in zip(indices, gradients[singular]) if i not in fixed]
                norm = math.sqrt(_sum(_dot(row, row) for _, row in support))
                if not math.isfinite(norm) or norm == 0:
                    raise ConstraintProjectionRefused('UNREPRESENTABLE_ACTIVE_CONSTRAINT', face_ordinal=ordinal)
                rows.append([(i, [x/norm for x in row]) for i, row in support])
                if len(witnesses) < WITNESS_LIMIT:
                    witnesses.append({'face_ordinal': ordinal, 'piece': pid,
                        'kind': 'LOWER' if singular == 0 else 'UPPER', 'sigma': measured[singular],
                        'bound': bound, 'origins': origins})
        projected, report = _project_halfspaces(direction, diagonal, rows, fixed, check_time)
    except (OverflowError, ZeroDivisionError) as error:
        raise ConstraintProjectionRefused('UNREPRESENTABLE_PROJECTION_ARITHMETIC') from error
    report.update(method=MODE, kernel_code_sha256=sha(__file__), active_constraint_count=active_count,
        fixed_only_constraint_count=fixed_count, witnesses=witnesses,
        roundoff_active_constraint_count=roundoff_count,
        retained_observed_constraint_count=len(retained),
        retained_additional_constraint_count=retained_additional_count,
        retained_overlap_constraint_count=retained_overlap_count,
        duplicate_observed_constraint_count=len(observed_constraints)-len(retained),
        observed_constraint_policy=OBSERVED_CONSTRAINT_POLICY,
        witnesses_truncated=len(rows)>len(witnesses), max_sweeps=MAX_SWEEPS,
        residual_tolerance=RESIDUAL_TOLERANCE,
        activity_policy='EXISTING_METRIC_ENVELOPE_ROUNDOFF_UNION_OBSERVED_VIOLATIONS',
        repeated_or_zero_active_singular_values='CONSERVATIVE_REFUSAL_UNLESS_FACE_FULLY_FIXED',
        fixed_controls_policy='REMOVED_BEFORE_PROJECTION', nonlinear_admission='REQUIRED_UNCHANGED', qualification='NONE')
    return projected, report
