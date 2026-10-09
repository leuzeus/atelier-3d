"""Pure-Python clearance checks and variants along a declared attachment ray.

Distances concern the supplied closed triangle sets, not a signed body volume.
The caller authenticates/selects the path and body and separately adopts variants.
This module never edits geometry, chooses anatomical references, or admits fitting.
"""
from __future__ import annotations

import copy
from fractions import Fraction
import math
from pathlib import Path
import time

from .core import StudioError, digest, sha


METHOD = 'DECLARED_OFFSET_RAY_EXACT_CLEARANCE_V1'
DEFAULT_BUDGETS = {'max_seconds': 10., 'max_triangle_visits': 2000000,
                   'max_candidates': 128, 'max_body_vertices': 200000, 'max_body_triangles': 200000}
_MAXIMUM_BUDGETS = {'max_seconds': 60., 'max_triangle_visits': 10000000,
                    'max_candidates': 1024, 'max_body_vertices': 200000, 'max_body_triangles': 200000}


class AttachmentClearanceRefused(StudioError):
    """A detailed bounded refusal; an external budget exception is not wrapped."""
    def __init__(self, reason, **details):
        self.diagnostic = {'reason': reason, 'qualification': 'NONE', **details}
        super().__init__('Attachment clearance refused: '+reason)


def _number(value, name, *, positive=False):
    try:
        valid = type(value) in (int, float) and math.isfinite(value)
        result = float(value) if valid else math.nan
    except (OverflowError, TypeError, ValueError):
        valid, result = False, math.nan
    if not valid or not math.isfinite(result) or (result <= 0 if positive else result < 0):
        raise AttachmentClearanceRefused('INVALID_FINITE_NUMBER', field=name)
    if type(value) is int and int(result) != value:
        raise AttachmentClearanceRefused('INTEGER_NOT_EXACT_BINARY64', field=name)
    return result


def _vector(value, name):
    if not isinstance(value, (list, tuple)) or len(value) != 3:
        raise AttachmentClearanceRefused('INVALID_VECTOR3', field=name)
    result = []
    for v in value:
        try:
            valid = type(v) in (int, float) and math.isfinite(v)
            x = float(v) if valid else math.nan
        except (OverflowError, TypeError, ValueError):
            x = math.nan
        if not math.isfinite(x):
            raise AttachmentClearanceRefused('INVALID_FINITE_VECTOR3', field=name)
        if type(v) is int and int(x) != v:
            raise AttachmentClearanceRefused('INTEGER_NOT_EXACT_BINARY64', field=name)
        result.append(x)
    return result


def _fraction_record(value):
    try:
        approximation = float(value)
    except OverflowError:
        approximation = None
    return {'numerator': str(value.numerator), 'denominator': str(value.denominator),
            'approximate': approximation if approximation is None or math.isfinite(approximation) else None}


def _rational_vector(value):
    return [Fraction(x) for x in value]


def _sub(a, b):
    return [x-y for x, y in zip(a, b)]


def _dot(a, b):
    return sum(x*y for x, y in zip(a, b))


def _segment_witness(point, triangle, first, second):
    a, b = triangle[first], triangle[second]
    edge = _sub(b, a); denominator = _dot(edge, edge)
    t = Fraction(0) if not denominator else max(Fraction(0), min(Fraction(1), _dot(_sub(point, a), edge)/denominator))
    q = [x+t*y for x, y in zip(a, edge)]
    weights = [Fraction(0)]*3; weights[first] = 1-t; weights[second] = t
    return _dot(_sub(point, q), _sub(point, q)), weights


def _closed_triangle_distance(point, triangle):
    """Exact binary-rational distance, including edges and degenerate triangles."""
    a, b, c = triangle
    ab, ac, ap = _sub(b, a), _sub(c, a), _sub(point, a)
    aa, cc, mixed = _dot(ab, ab), _dot(ac, ac), _dot(ab, ac)
    determinant = aa*cc-mixed*mixed
    witnesses = [_segment_witness(point, triangle, i, j) for i, j in ((0, 1), (1, 2), (2, 0))]
    if determinant > 0:
        u = (cc*_dot(ap, ab)-mixed*_dot(ap, ac))/determinant
        v = (aa*_dot(ap, ac)-mixed*_dot(ap, ab))/determinant
        if u >= 0 and v >= 0 and u+v <= 1:
            q = [a[i]+u*ab[i]+v*ac[i] for i in range(3)]
            witnesses.append((_dot(_sub(point, q), _sub(point, q)), [1-u-v, u, v]))
    return min(witnesses, key=lambda row: (row[0], row[1]))


class _Budget:
    def __init__(self, options, clock, check_time):
        if options is not None and (not isinstance(options, dict) or set(options)-set(DEFAULT_BUDGETS)):
            raise AttachmentClearanceRefused('INVALID_BUDGET_FIELDS')
        self.options = {**DEFAULT_BUDGETS, **(options or {})}
        for key, value in self.options.items():
            if key != 'max_seconds' and type(value) is not int:
                raise AttachmentClearanceRefused('INVALID_INTEGER_BUDGET', field=key)
            if _number(value, key, positive=True) > _MAXIMUM_BUDGETS[key]:
                raise AttachmentClearanceRefused('BUDGET_LIMIT_EXCEEDED', field=key)
        if not callable(clock) or check_time is not None and not callable(check_time):
            raise AttachmentClearanceRefused('INVALID_BUDGET_CALLBACK')
        self.clock, self.check_time = clock, check_time
        self.start = self._read_clock(); self.last_time = self.start
        self.work = {'prepared_vertices': 0, 'prepared_triangles': 0, 'triangle_visits': 0,
                     'exact_aabb_exclusions': 0, 'exact_closed_triangle_tests': 0, 'candidates': 0}
        self.context = {}

    def _read_clock(self):
        value = self.clock()
        try:
            valid = type(value) in (int, float) and math.isfinite(value)
        except (OverflowError, TypeError, ValueError):
            valid = False
        if not valid:
            raise AttachmentClearanceRefused('INVALID_CLOCK_VALUE')
        return value

    def check(self):
        if self.check_time is not None:
            self.check_time()  # A caller's interruption/deadline propagates unchanged.
        current = self._read_clock()
        if current < self.last_time:
            raise AttachmentClearanceRefused('NONMONOTONIC_CLOCK')
        self.last_time = current
        if current-self.start >= self.options['max_seconds']:
            self.refuse('TIME_BUDGET')

    def take(self, key):
        if self.work[key] >= self.options['max_'+key]:
            self.refuse(key.upper()+'_BUDGET')
        self.work[key] += 1

    def refuse(self, reason, **details):
        raise AttachmentClearanceRefused(reason, work=copy.deepcopy(self.work),
                                        budgets=dict(self.options), **self.context, **details)


class _Body:
    def __init__(self, vertices, triangles, budget):
        if (not isinstance(vertices, (list, tuple)) or not vertices or
                not isinstance(triangles, (list, tuple)) or not triangles):
            budget.refuse('NONEMPTY_BODY_REQUIRED')
        if len(vertices) > budget.options['max_body_vertices'] or len(triangles) > budget.options['max_body_triangles']:
            budget.refuse('BODY_SIZE_BUDGET', vertices=len(vertices), triangles=len(triangles))
        self.vertices = []
        for index, row in enumerate(vertices):
            if index % 32 == 0: budget.check()
            self.vertices.append(_rational_vector(_vector(row, 'body_vertex')))
            budget.work['prepared_vertices'] += 1
        self.triangles, self.boxes = [], []
        for index, row in enumerate(triangles):
            if index % 32 == 0: budget.check()
            if (not isinstance(row, (list, tuple)) or len(row) != 3 or
                    any(type(i) is not int or not 0 <= i < len(vertices) for i in row)):
                budget.refuse('INVALID_BODY_TRIANGLE', triangle_index=index)
            points = [self.vertices[i] for i in row]
            self.triangles.append(tuple(row))
            self.boxes.append(tuple((min(p[k] for p in points), max(p[k] for p in points)) for k in range(3)))
            budget.work['prepared_triangles'] += 1
        budget.check()

    def certify(self, point, radius, budget):
        p, threshold2 = _rational_vector(point), radius*radius
        skipped, tested = 0, 0
        for index, (indices, bounds) in enumerate(zip(self.triangles, self.boxes)):
            if index % 32 == 0: budget.check()
            budget.take('triangle_visits')
            # Exact lower bound: every point of the closed triangle lies in its AABB.
            lower2 = sum(max(lo-p[k], Fraction(0), p[k]-hi)**2 for k, (lo, hi) in enumerate(bounds))
            if lower2 >= threshold2:
                skipped += 1; budget.work['exact_aabb_exclusions'] += 1
                continue
            points = [self.vertices[i] for i in indices]
            distance2, weights = _closed_triangle_distance(p, points)
            tested += 1; budget.work['exact_closed_triangle_tests'] += 1
            if distance2 < threshold2:
                witness = [sum(weights[j]*points[j][axis] for j in range(3)) for axis in range(3)]
                budget.check()
                return {'clearance_satisfied': False, 'necessary_conflict_proved': True,
                        'coverage_complete': index+1 == len(self.triangles), 'body_triangles': len(self.triangles),
                        'visited_triangles': index+1, 'exact_aabb_exclusions': skipped, 'exact_closed_triangle_tests': tested,
                        'threshold_cm': _fraction_record(radius), 'threshold_squared_cm2': _fraction_record(threshold2),
                        'witness': {'body_triangle': index, 'body_vertex_indices': list(indices),
                                    'distance_squared_cm2': _fraction_record(distance2),
                                    'barycentric': [_fraction_record(x) for x in weights],
                                    'point_world_cm_exact': [_fraction_record(x) for x in witness]}}
        budget.check()
        return {'clearance_satisfied': True, 'necessary_conflict_proved': False, 'coverage_complete': True,
                'body_triangles': len(self.triangles), 'visited_triangles': len(self.triangles),
                'exact_aabb_exclusions': skipped, 'exact_closed_triangle_tests': tested,
                'threshold_cm': _fraction_record(radius), 'threshold_squared_cm2': _fraction_record(threshold2),
                'witness': None}


def _context(vertices, triangles, inputs, provenance, budget):
    if provenance is not None and not isinstance(provenance, dict):
        budget.refuse('INVALID_PROVENANCE')
    try:
        provenance_identity = digest(provenance or {})
        identity = digest({'vertices_cm': vertices, 'triangles': triangles, **inputs})
        geometry_identity = digest([vertices, triangles])
    except (ValueError, TypeError, OverflowError, RecursionError) as error:
        budget.refuse('INVALID_JSON_IDENTITY', detail=str(error))
    budget.check()
    return {'method': METHOD, 'inputs_sha256': identity, 'body_geometry_sha256': geometry_identity,
            'kernel_code_sha256': sha(Path(__file__)), 'provenance': copy.deepcopy(provenance or {}),
            'provenance_sha256': provenance_identity, 'qualification': 'NONE',
            'signed_inside_outside': 'NOT_ASSESSED', 'mesh_closed_or_manifold': 'NOT_ASSESSED',
            'distance_scope': 'ALL_SUPPLIED_CLOSED_TRIANGLE_SETS',
            'canonical_mutation': False, 'source_selection': 'CALLER',
            'safety_margin_is_design_ease': False, 'physical_fitting': 'NOT_EXECUTED'}


def _radius(clearance, margin):
    clearance = _number(clearance, 'clearance_cm', positive=True)
    margin = _number(margin, 'safety_margin_cm')
    radius = Fraction(clearance)+Fraction(margin)
    try:
        finite = math.isfinite(float(radius))
    except OverflowError:
        finite = False
    if not finite:
        raise AttachmentClearanceRefused('UNREPRESENTABLE_CLEARANCE_SUM')
    return clearance, margin, radius


def _finish(report, budget):
    budget.check()
    report.update(budgets=dict(budget.options), work=dict(budget.work), elapsed_seconds=budget.last_time-budget.start)
    return report


def check_attachment_clearance(vertices_cm, triangles, target_world_cm, *, clearance_cm,
                               safety_margin_cm=0., budgets=None, provenance=None,
                               clock=time.monotonic, check_time=None):
    """Prove reserve or provide one exact necessary-conflict witness for a fixed target."""
    budget = _Budget(budgets, clock, check_time); budget.check()
    point = _vector(target_world_cm, 'target_world_cm')
    clearance, margin, radius = _radius(clearance_cm, safety_margin_cm)
    body = _Body(vertices_cm, triangles, budget)
    report = _context(vertices_cm, triangles, {'target_world_cm': point, 'clearance_cm': clearance,
                      'safety_margin_cm': margin}, provenance, budget)
    budget.context = {'inputs_sha256': report['inputs_sha256']}
    budget.take('candidates')
    certificate = body.certify(point, radius, budget)
    report.update(status='CLEARANCE_VERIFIED' if certificate['clearance_satisfied'] else 'FIXED_TARGET_CLEARANCE_CONFLICT',
                  target_world_cm=point, clearance_cm=clearance, safety_margin_cm=margin, certificate=certificate)
    return _finish(report, budget)


def check_attachment_clearances(vertices_cm, triangles, targets_world_cm, *, clearance_cm,
                                safety_margin_cm=0., budgets=None, provenance=None,
                                clock=time.monotonic, check_time=None):
    """Check ordered fixed targets with one body conversion and one shared budget."""
    budget = _Budget(budgets, clock, check_time); budget.check()
    if not isinstance(targets_world_cm, (list, tuple)) or not targets_world_cm:
        budget.refuse('NONEMPTY_TARGETS_REQUIRED')
    if len(targets_world_cm) > budget.options['max_candidates']:
        budget.refuse('TARGET_COUNT_BUDGET', targets=len(targets_world_cm))
    points = [_vector(p, 'target_world_cm') for p in targets_world_cm]
    clearance, margin, radius = _radius(clearance_cm, safety_margin_cm)
    body = _Body(vertices_cm, triangles, budget)
    report = _context(vertices_cm, triangles, {'targets_world_cm': points, 'clearance_cm': clearance,
                      'safety_margin_cm': margin}, provenance, budget)
    budget.context = {'inputs_sha256': report['inputs_sha256'], 'total_targets': len(points),
                      'checked_count': 0, 'conflict_count': 0, 'verified_count': 0, 'completed_checks': []}
    checks = []
    for index, point in enumerate(points):
        budget.check(); budget.take('candidates')
        certificate = body.certify(point, radius, budget)
        verified = certificate['clearance_satisfied']
        checks.append({'index': index, 'target_world_cm': point,
                       'status': 'CLEARANCE_VERIFIED' if verified else 'FIXED_TARGET_CLEARANCE_CONFLICT',
                       'certificate': certificate})
        budget.context['checked_count'] += 1
        budget.context['verified_count' if verified else 'conflict_count'] += 1
        budget.context['completed_checks'] = checks
    report.update(status='FIXED_TARGET_CLEARANCE_CONFLICTS' if budget.context['conflict_count'] else 'ALL_TARGET_CLEARANCES_VERIFIED',
                  total_targets=len(points), checked_count=len(checks), checks=checks,
                  verified_count=budget.context['verified_count'], conflict_count=budget.context['conflict_count'],
                  clearance_cm=clearance, safety_margin_cm=margin)
    return _finish(report, budget)


def propose_attachment_clearance(vertices_cm, triangles, path_anchor_world_cm, offset_world_cm, *,
                                 clearance_cm, safety_margin_cm, max_added_displacement_cm,
                                 search_step_cm, budgets=None, provenance=None,
                                 clock=time.monotonic, check_time=None):
    """Check the original target, then search only the declared offset ray.

    A finite deterministic grid does not prove impossibility or minimality. Each
    stored binary64 target is certified; callers must recheck transformed outputs.
    """
    budget = _Budget(budgets, clock, check_time); budget.check()
    anchor = _vector(path_anchor_world_cm, 'path_anchor_world_cm')
    offset = _vector(offset_world_cm, 'offset_world_cm')
    length = math.hypot(*offset)
    if not math.isfinite(length) or length == 0:
        budget.refuse('NONZERO_REPRESENTABLE_OFFSET_REQUIRED')
    clearance, margin, radius = _radius(clearance_cm, safety_margin_cm)
    maximum = _number(max_added_displacement_cm, 'max_added_displacement_cm')
    step = _number(search_step_cm, 'search_step_cm', positive=True)
    exact_anchor, exact_offset = _rational_vector(anchor), _rational_vector(offset)
    def point_at(multiplier):
        exact = [a+multiplier*b for a, b in zip(exact_anchor, exact_offset)]
        try:
            point = [float(x) for x in exact]
        except OverflowError:
            budget.refuse('UNREPRESENTABLE_RAY_TARGET')
        if not all(math.isfinite(x) for x in point):
            budget.refuse('UNREPRESENTABLE_RAY_TARGET')
        return point, exact
    original, _ = point_at(Fraction(1))
    body = _Body(vertices_cm, triangles, budget)
    report = _context(vertices_cm, triangles, {'path_anchor_world_cm': anchor, 'offset_world_cm': offset,
                      'clearance_cm': clearance, 'safety_margin_cm': margin,
                      'max_added_displacement_cm': maximum, 'search_step_cm': step}, provenance, budget)
    report.update(path_anchor_world_cm=anchor, offset_world_cm=offset, original_target_world_cm=original,
                  clearance_cm=clearance, safety_margin_cm=margin, minimality='NOT_CLAIMED',
                  clearance_monotonicity='NOT_ASSUMED', adoption='REQUIRED_SEPARATELY',
                  transformed_outputs='RECHECK_ACTUAL_ROUNDED_TARGET_BEFORE_BINDING')
    budget.context = {'inputs_sha256': report['inputs_sha256']}
    budget.take('candidates')
    initial = body.certify(original, radius, budget)
    report['initial_check'] = initial
    budget.context['initial_check'] = initial
    if initial['clearance_satisfied']:
        report.update(status='UNCHANGED_TARGET_CLEARANCE_VERIFIED', target_world_cm=original,
                      offset_multiplier=_fraction_record(Fraction(1)), added_displacement_cm=0., certificate=initial)
        return _finish(report, budget)
    exact_max, exact_step = Fraction(maximum), Fraction(step)
    trials = []
    # No eagerly allocated list, even for an extremely small declared step.
    index, previous_nominal = 1, Fraction(0)
    while previous_nominal < exact_max:
        budget.check(); budget.take('candidates')
        nominal = min(index*exact_step, exact_max)
        multiplier = Fraction(1)+nominal/Fraction(length)
        point, exact_point = point_at(multiplier)
        displacement = _sub(_rational_vector(point), _rational_vector(original))
        displacement2 = _dot(displacement, displacement)
        row = {'grid_index': index, 'nominal_added_displacement_cm': float(nominal),
               'target_world_cm': point, 'offset_multiplier': _fraction_record(multiplier)}
        if displacement2 > exact_max*exact_max:
            row['status'] = 'ROUNDED_DISPLACEMENT_CAP_REFUSED'
        else:
            certificate = body.certify(point, radius, budget)
            row['status'] = 'CLEARANCE_VERIFIED' if certificate['clearance_satisfied'] else 'CLEARANCE_REFUSED'
            row['certificate'] = certificate
            if certificate['clearance_satisfied']:
                rounding = _sub(_rational_vector(point), exact_point)
                report.update(status='CLEARANCE_VARIANT_PROPOSED', target_world_cm=point,
                              exact_ray_target_world_cm=[_fraction_record(x) for x in exact_point],
                              offset_multiplier=_fraction_record(multiplier),
                              added_displacement_squared_cm2=_fraction_record(displacement2),
                              added_displacement_cm=math.dist(point, original),
                              representation_error_squared_cm2=_fraction_record(_dot(rounding, rounding)),
                              certificate=certificate, trials=[*trials, row])
                return _finish(report, budget)
        trials.append(row)
        budget.context['last_examined_candidate'] = row
        previous_nominal = nominal; index += 1
    budget.refuse('NO_CANDIDATE_ON_DECLARED_RAY_GRID', finite_grid_exhausted=True,
                  geometric_impossibility_proved=False, trials=trials)
