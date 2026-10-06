"""Opt-in, pure rigid reserve for protected material stops before freezing them.

V1 searches ONE positive scalar translation along the caller's BODY_FRAME_UP,
common to the union of whole permanent-connected panel components containing
the stops. It is not a warp, optimal placement search, seam welding, admission,
simulation or fitting. Detachable/closure relationships do not imply ownership.

The native caller must authenticate body/frame/source/pose identities, execute
the unchanged rest-quality precondition (including its existing angle limit),
and measure ALL protected stops against the ENTIRE actual evaluated body
surface. FULL_BODY_COLLISION describes the body-query domain, not a per-step
cloth-triangle admission gate. An isolated nearest triangle or skin proxy is
not an implementation of that callback. This kernel cannot establish native
provenance from callback labels.
Full triangle, layer, metric and contact gates are still required afterwards.
Coordinates and all distances are centimetres; the original displacement
reference is REQUIRED and never reset after an earlier correction.
"""
import copy
import math
import time

from .core import StudioError, digest


DOMAIN = 'WHOLE_PERMANENT_COMPONENT_UNION_BODY_FRAME_UP'


def _number(value, *, nonnegative=False):
    return (type(value) in (int, float) and math.isfinite(value)
            and (not nonnegative or value >= 0))


def _points(value, count=None, dimension=3):
    return (isinstance(value, (list, tuple)) and len(value) > 0
            and (count is None or len(value) == count)
            and all(isinstance(p, (list, tuple)) and len(p) == dimension
                    and all(_number(x) for x in p) for p in value))


def _indices(value, count, label, *, nonempty=False):
    if (not isinstance(value, (list, tuple)) or (nonempty and not value)
            or any(type(i) is not int or not 0 <= i < count for i in value)
            or len(set(value)) != len(value)):
        raise StudioError('Invalid or duplicate ' + label)
    return set(value)


def _structure(payload, points):
    if not isinstance(payload, dict) or not _points(points):
        raise StudioError('Anchor reserve requires a finite mapped mesh')
    count = len(points)
    if not _points(payload.get('rest_cm'), count):
        raise StudioError('Anchor reserve rest coordinates must cover the same mesh')
    if 'uv_cm' in payload and not _points(payload['uv_cm'], count, 2):
        raise StudioError('Anchor reserve UV mapping is malformed')
    panels = payload.get('panels')
    if not isinstance(panels, dict) or not panels:
        raise StudioError('Anchor reserve needs explicit source panel ownership')
    owners = {}; neighbours = {pid: set() for pid in panels}
    for pid, panel in panels.items():
        if not isinstance(pid, str) or not pid or not isinstance(panel, dict):
            raise StudioError('Anchor reserve source panel identity is invalid')
        indices = _indices(panel.get('indices'), count, 'panel indices', nonempty=True)
        for index in indices:
            if index in owners:
                raise StudioError('Anchor reserve requires unique unmerged source ownership')
            owners[index] = pid
    if set(owners) != set(range(count)):
        raise StudioError('Anchor reserve source ownership is incomplete')
    faces = payload.get('faces')
    if not isinstance(faces, list) or not faces:
        raise StudioError('Anchor reserve requires actual source triangles')
    seen = set(); used = set()
    for face in faces:
        vertices = _indices(face, count, 'triangle indices', nonempty=True)
        if len(vertices) != 3 or len({owners[i] for i in face}) != 1:
            raise StudioError('Anchor reserve needs unmixed source panel triangles')
        key = tuple(sorted(vertices))
        if key in seen:
            raise StudioError('Anchor reserve source triangle is duplicated')
        seen.add(key); used.update(vertices)
    if used != set(range(count)):
        raise StudioError('Anchor reserve has source vertices outside material faces')
    seams = payload.get('seams', {})
    if not isinstance(seams, dict):
        raise StudioError('Anchor reserve seams must be explicitly mapped')
    for sid, seam in seams.items():
        if (not isinstance(sid, str) or not sid or not isinstance(seam, dict)
                or seam.get('kind') not in ('permanent', 'detachable', 'closure')
                or not isinstance(seam.get('piece_a'), str) or not isinstance(seam.get('piece_b'), str)
                or seam.get('piece_a') not in panels or seam.get('piece_b') not in panels
                or not isinstance(seam.get('pairs'), list) or not seam['pairs']):
            raise StudioError('Anchor reserve seam identity or relationships are malformed')
        pairs_seen = set()
        for pair in seam['pairs']:
            if (not isinstance(pair, (list, tuple)) or len(pair) != 2
                    or any(type(i) is not int or not 0 <= i < count for i in pair)
                    or pair[0] == pair[1] or tuple(pair) in pairs_seen
                    or owners[pair[0]] != seam['piece_a'] or owners[pair[1]] != seam['piece_b']):
                raise StudioError('Anchor reserve seam pair lost source ownership')
            pairs_seen.add(tuple(pair))
        if seam['kind'] == 'permanent':
            neighbours[seam['piece_a']].add(seam['piece_b'])
            neighbours[seam['piece_b']].add(seam['piece_a'])
    return owners, neighbours


def _groups(owners, neighbours, stops):
    groups = []; visited = set()
    for pid in sorted({owners[i] for i in stops}):
        if pid in visited:
            continue
        pending = [pid]; group = set()
        while pending:
            current = pending.pop()
            if current in group:
                continue
            group.add(current); pending.extend(sorted(neighbours[current] - group))
        visited.update(group); groups.append(sorted(group))
    return sorted(groups)


class _Unmeasured(ValueError):
    pass


def _measurement(evaluate, payload, points, context, stops, moving, clearances=None):
    source = copy.deepcopy(payload); trial = copy.deepcopy(points)
    identity = digest([source, trial])
    try:
        report = evaluate(source, trial)
    except Exception as error:
        raise _Unmeasured('CALLBACK_UNAVAILABLE:' + type(error).__name__) from error
    if digest([source, trial]) != identity:
        raise _Unmeasured('CALLBACK_MUTATED_INPUT')
    if not isinstance(report, dict):
        raise _Unmeasured('MALFORMED_MEASUREMENT')
    if report.get('status') != 'MEASURED':
        raise _Unmeasured('MEASUREMENT_' + str(report.get('status', 'UNAVAILABLE')))
    if (report.get('context_identity') != context
            or report.get('source_sha256') != digest(payload)
            or report.get('candidate_sha256') != digest(points)):
        raise _Unmeasured('STALE_MEASUREMENT_IDENTITY')
    if (report.get('method') != 'FULL_BODY_COLLISION'
            or report.get('sign_status') != 'UNAMBIGUOUS'
            or report.get('moving_indices') != sorted(moving)):
        raise _Unmeasured('UNSUPPORTED_OR_AMBIGUOUS_MEASUREMENT')
    rows = report.get('protected_contacts')
    if not isinstance(rows, list) or len(rows) != len(stops):
        raise _Unmeasured('INCOMPLETE_PROTECTED_MEASUREMENT')
    seen = set(); deficits = []
    for row in rows:
        if (not isinstance(row, dict) or type(row.get('vertex')) is not int
                or row['vertex'] not in stops or row['vertex'] in seen
                or not _number(row.get('signed_offset_cm'))
                or not _number(row.get('clearance_cm'), nonnegative=True)):
            raise _Unmeasured('MALFORMED_PROTECTED_MEASUREMENT')
        seen.add(row['vertex'])
        if clearances is not None and row['clearance_cm'] != clearances[row['vertex']]:
            raise _Unmeasured('CHANGED_CLEARANCE_CONTROL')
        deficits.append(max(0., row['clearance_cm'] - row['signed_offset_cm']))
    if any(not math.isfinite(deficit) for deficit in deficits):
        raise _Unmeasured('NONFINITE_CLEARANCE_DEFICIT')
    score = max(deficits)
    return copy.deepcopy(report), score, score == 0.


def solve_anchor_reserve(payload, coordinates, evaluate, specification, *,
                        body_frame_up, context_identity, displacement_reference,
                        rest_precondition, protected_indices, support_indices=(),
                        clock=time.monotonic):
    """Search a bounded reserve, without claiming garment or native admission.

    Required specification: version=1, enabled=True, domain=DOMAIN, budgets
    (max_displacement_cm, max_step_cm, max_iterations, max_seconds). Optional
    budgets: stagnation_iterations=3, min_improvement_cm=1e-9. Iterations count
    proposed positive translations; the initial measurement is separate. The
    injected callback must enforce its own per-call deadline: Python cannot
    preempt an external measurement. Late results are rejected and cannot
    replace the last in-budget witness or grant admissibility. The clearance
    control for each stop must remain identical throughout the search.

    rest_precondition: status=PASSED, exact source_sha256/candidate_sha256.
    Other precondition statuses refuse without invoking collision measurement.
    Fixed pins and explicit supports in any selected component refuse the
    domain before any proposal; unselected fixed components remain untouched.
    Unknown/malformed/stale callback evidence never permits admissibility.
    """
    owners, neighbours = _structure(payload, coordinates)
    count = len(coordinates)
    stops = _indices(protected_indices, count, 'protected stop indices', nonempty=True)
    supports = _indices(support_indices, count, 'support indices')
    if not _points([body_frame_up]):
        raise StudioError('BODY_FRAME_UP must be finite and nonzero')
    norm = math.hypot(*body_frame_up)
    if not math.isfinite(norm) or norm == 0:
        raise StudioError('BODY_FRAME_UP must be finite and nonzero')
    axis = [x / norm for x in body_frame_up]
    if not isinstance(context_identity, dict) or not context_identity:
        raise StudioError('Anchor reserve requires an exact measurement context')
    if not _points(displacement_reference, count):
        raise StudioError('Original displacement reference is required for every source vertex')
    if (not isinstance(specification, dict) or type(specification.get('version')) is not int
            or specification['version'] != 1
            or specification.get('enabled') is not True or specification.get('domain') != DOMAIN):
        raise StudioError('Anchor reserve requires explicit opt-in to its narrow domain')
    budgets = specification.get('budgets')
    if not isinstance(budgets, dict):
        raise StudioError('Anchor reserve requires declared work budgets')
    for key in ('max_displacement_cm', 'max_step_cm', 'max_seconds'):
        if not _number(budgets.get(key)) or budgets[key] <= 0:
            raise StudioError('Anchor reserve budget must be finite and positive: ' + key)
    iterations_max = budgets.get('max_iterations')
    stagnant_max = budgets.get('stagnation_iterations', 3)
    improvement = budgets.get('min_improvement_cm', 1e-9)
    if (type(iterations_max) is not int or iterations_max < 1
            or type(stagnant_max) is not int or stagnant_max < 1
            or not _number(improvement, nonnegative=True)):
        raise StudioError('Anchor reserve iteration/stagnation budgets are invalid')
    pins = payload.get('pins', {})
    if not isinstance(pins, dict):
        raise StudioError('Anchor reserve pins must be indexed weights')
    for key, weight in pins.items():
        if (not isinstance(key, str) or not key.isascii() or not key.isdigit() or str(int(key)) != key
                or not 0 <= int(key) < count or not _number(weight)
                or not 0 <= weight <= 1):
            raise StudioError('Anchor reserve pin declaration is malformed')
        if weight > 0:
            supports.add(int(key))
    groups = _groups(owners, neighbours, stops)
    moving_panels = {pid for group in groups for pid in group}
    moving = {i for i, owner in owners.items() if owner in moving_panels}
    initial = copy.deepcopy(coordinates); reference = copy.deepcopy(displacement_reference)
    input_identity = digest([payload, coordinates, specification, body_frame_up,
                             context_identity, displacement_reference, rest_precondition,
                             protected_indices, support_indices])
    source_identity = digest(payload); context = copy.deepcopy(context_identity)
    start = clock(); last_time = start
    if not _number(start):
        raise StudioError('Anchor reserve clock must be finite and monotone')

    def elapsed():
        nonlocal last_time
        value = clock()
        if not _number(value) or value < last_time:
            raise StudioError('Anchor reserve clock must be finite and monotone')
        last_time = value
        return value - start

    best = initial; before = after = None; best_score = None
    best_admissible = False; best_scalar = 0.; history = []; iterations = calls = stagnant = 0
    clearances = None
    initial_displacement = max(math.dist(a, b) for a, b in zip(reference, initial))
    if not math.isfinite(initial_displacement):
        raise StudioError('Anchor reserve displacement must be representable and finite')
    reason = 'ITERATION_BUDGET'; status = 'NEEDS_CORRECTION'

    def result():
        spent = elapsed()
        if digest([payload, coordinates, specification, body_frame_up, context_identity,
                   displacement_reference, rest_precondition, protected_indices, support_indices]) != input_identity:
            raise StudioError('Anchor reserve input changed during execution')
        return {'version': 1, 'domain': DOMAIN, 'status': status, 'stop_reason': reason,
                'coordinates_cm': copy.deepcopy(best), 'before_measurement': before,
                'after_measurement': after, 'history': history, 'groups': groups,
                'protected_indices': sorted(stops), 'moving_indices': sorted(moving),
                'support_indices': sorted(supports), 'body_frame_up': axis,
                'translation_scalar_cm': best_scalar, 'source_sha256': source_identity,
                'initial_candidate_sha256': digest(initial), 'candidate_sha256': digest(best),
                'displacement_reference_sha256': digest(reference),
                'measurement_context_sha256': digest(context),
                'specification_sha256': digest(specification),
                'initial_displacement_from_reference_cm': initial_displacement,
                'maximum_cumulative_displacement_cm': max(math.dist(a, b) for a, b in zip(reference, best)),
                'spent_budget': {'iterations': iterations, 'measurement_calls': calls,
                                 'elapsed_seconds': spent},
                'budgets': copy.deepcopy(budgets), 'source_mutated': False,
                'source_uv_scaled': False, 'source_rest_changed': False,
                'metric_policy': 'PRESERVE_RIGID_COMPONENT_METRIC',
                'permanent_gap_policy': 'PRESERVE_RELATIVE_POSITIONS',
                'qualification': 'NONE', 'simulation': 'NOT_EXECUTED', 'fitting': 'NOT_EXECUTED',
                'final_assessment': 'FULL_NATIVE_GATES_REQUIRED', 'native_origin': 'NOT_ESTABLISHED'}

    if (not isinstance(rest_precondition, dict) or rest_precondition.get('status') != 'PASSED'
            or rest_precondition.get('source_sha256') != source_identity
            or rest_precondition.get('candidate_sha256') != digest(initial)):
        status = 'REFUSED'; reason = 'REST_PRECONDITION_REQUIRED'; return result()
    if moving & supports:
        status = 'REFUSED'; reason = 'FIXED_SUPPORT_IN_SELECTED_COMPONENT'; return result()
    if initial_displacement > budgets['max_displacement_cm']:
        status = 'REFUSED'; reason = 'INITIAL_CUMULATIVE_DISPLACEMENT_BUDGET'; return result()

    def measure(points):
        nonlocal calls
        if elapsed() >= budgets['max_seconds']:
            raise _Unmeasured('TIME_BUDGET')
        calls += 1
        measured = _measurement(evaluate, payload, points, context, stops, moving, clearances)
        if elapsed() >= budgets['max_seconds']:
            raise _Unmeasured('TIME_BUDGET')
        return measured

    try:
        before, best_score, best_admissible = measure(initial)
        after = copy.deepcopy(before)
        clearances = {row['vertex']: row['clearance_cm'] for row in before['protected_contacts']}
    except _Unmeasured as error:
        status = 'NEEDS_MEASUREMENT'; reason = str(error); return result()
    if best_admissible:
        status = 'ANCHORS_ADMISSIBLE_ONLY'; reason = 'INITIAL_ANCHORS_ADMISSIBLE'; return result()
    for iteration in range(1, iterations_max + 1):
        if elapsed() >= budgets['max_seconds']:
            reason = 'TIME_BUDGET'; break
        iterations = iteration
        scalar = min(iteration * budgets['max_step_cm'], budgets['max_displacement_cm'])
        trial = copy.deepcopy(initial)
        for index in sorted(moving):
            trial[index] = [initial[index][k] + scalar * axis[k] for k in range(3)]
        if not _points(trial):
            reason = 'NONFINITE_PROPOSAL'; break
        movement = max(math.dist(a, b) for a, b in zip(reference, trial))
        if not math.isfinite(movement):
            reason = 'NONFINITE_PROPOSAL'; break
        record = {'iteration': iteration, 'translation_scalar_cm': scalar,
                  'candidate_sha256': digest(trial), 'maximum_cumulative_displacement_cm': movement,
                  'kept': False}
        if movement > budgets['max_displacement_cm']:
            record['reason'] = 'CUMULATIVE_DISPLACEMENT_BUDGET'
            history.append(record); reason = record['reason']; break
        try:
            report, score, admissible = measure(trial)
        except _Unmeasured as error:
            record['reason'] = str(error); history.append(record)
            reason = str(error); status = 'NEEDS_MEASUREMENT'; break
        kept = score < best_score - improvement or admissible
        record.update(reason='MEASURED_IMPROVEMENT' if kept else 'NO_MEASURED_IMPROVEMENT',
                      measurement=report, score_cm=score, kept=kept)
        history.append(record)
        if kept:
            best, after, best_score, best_scalar = trial, report, score, scalar
        stagnant = 0 if kept else stagnant + 1
        if admissible:
            status = 'ANCHORS_ADMISSIBLE_ONLY'; reason = 'MEASURED_ANCHORS_ADMISSIBLE'; break
        if scalar == budgets['max_displacement_cm']:
            reason = 'DISPLACEMENT_BUDGET'; break
        if stagnant >= stagnant_max:
            reason = 'STAGNATION'; break
    return result()
