"""Measured contact proposals and constrained relaxation on disposable copies.

The rigid kernel reuses placement_correction. A separate relaxation kernel
updates coordinates while retaining source UV, topology, panel ownership,
pins, supports and the consumer's existing metric thresholds. Exploratory
contact failures may improve; final hard gates alone control readiness.
Callbacks must bound their own work and return current candidate evidence.
"""
import copy
import math
import time

from .cloth_metrics import validate_metrics, validate_linear_motion
from .core import StudioError, contract, digest
from .placement_correction import rigid_candidate


def _vector(point):
    return isinstance(point, (tuple, list)) and len(point) == 3 and all(type(x) in (float, int) and math.isfinite(x) for x in point)


def _ownership(payload, count):
    owners = {}
    for pid, panel in payload['panels'].items():
        for index in panel['indices']:
            if type(index) is not int or not 0 <= index < count or index in owners:
                raise StudioError('Placement solver requires one actual source owner per coordinate')
            owners[index] = pid
    if set(owners) != set(range(count)):
        raise StudioError('Placement solver source mapping does not cover every coordinate')
    return owners


def _contacts(report, count):
    rows = report.get('contacts', [])
    if not isinstance(rows, list):
        raise StudioError('Measured contacts must be a finite list')
    result = []
    for row in rows:
        if (not isinstance(row, dict) or type(row.get('vertex')) is not int or not 0 <= row['vertex'] < count
                or not _vector(row.get('normal'))
                or any(type(row.get(k)) not in (float, int) or not math.isfinite(row[k])
                       for k in ('signed_offset_cm', 'clearance_cm'))
                or row['clearance_cm'] < 0):
            raise StudioError('Contact proposal requires current vertex, unit normal, signed offset and clearance')
        norm = math.sqrt(sum(x*x for x in row['normal']))
        if abs(norm-1) > 1e-6:
            raise StudioError('Measured collider normals must be unit vectors')
        deficit = max(0., row['clearance_cm']-row['signed_offset_cm'])
        if deficit:
            result.append((row['vertex'], [deficit*v for v in row['normal']]))
    return sorted(result, key=lambda row: (row[0], tuple(row[1])))


def _bounded(vector, maximum):
    length = math.sqrt(sum(v*v for v in vector))
    factor = min(1., maximum/length) if length else 0.
    return [factor*v for v in vector]


def measured_rigid_proposals(payload, coordinates, report, max_step_cm, protected=()):
    """Translations derive from measured normal deficits and actual seam pairs."""
    owners = _ownership(payload, len(coordinates)); fixed = set(protected)
    moves = {}; samples = {}
    for index, vector in _contacts(report, len(coordinates)):
        pid = owners[index]
        samples.setdefault(pid, []).append(vector)
    for pid, values in sorted(samples.items()):
        if fixed.intersection(payload['panels'][pid]['indices']):
            continue
        average = [sum(v[i] for v in values)/len(values) for i in range(3)]
        moves[pid] = _bounded(average, max_step_cm)
    identity = [[1., 0., 0.], [0., 1., 0.], [0., 0., 1.]]

    def motion(pid, vector):
        return {'panels': [pid], 'rotation': copy.deepcopy(identity),
                'origin_cm': [0., 0., 0.], 'translation_cm': vector}
    if moves:
        # Atomic correction permits both sides to improve together, without
        # requiring either intermediate panel to satisfy final contact gates.
        yield {'motions': [motion(pid, vector) for pid, vector in sorted(moves.items())]}
        if len(moves) > 1:
            for pid, vector in sorted(moves.items()):
                yield motion(pid, vector)
    for sid, seam in sorted(payload.get('seams', {}).items()):
        if seam.get('kind') != 'permanent':
            continue
        a, b = seam['piece_a'], seam['piece_b']
        if a == b or not seam.get('pairs'):
            continue
        if any(owners.get(x) != a or owners.get(y) != b for x, y in seam['pairs']):
            raise StudioError('Placement seam pairs lost their source panel ownership')
        average = [sum(coordinates[y][i]-coordinates[x][i] for x, y in seam['pairs'])/len(seam['pairs'])
                   for i in range(3)]
        movable_a = not fixed.intersection(payload['panels'][a]['indices'])
        movable_b = not fixed.intersection(payload['panels'][b]['indices'])
        factor = .5 if movable_a and movable_b else 1.
        vector = _bounded([factor*x for x in average], max_step_cm)
        motions = []
        if movable_a: motions.append(motion(a, vector))
        if movable_b: motions.append(motion(b, [-x for x in vector]))
        if motions and any(abs(v) > 1e-12 for v in vector):
            yield {'motions': motions}


def constrained_relaxation_candidate(payload, coordinates, report, max_step_cm, protected=(), fraction=1.):
    """Contact normal corrections spread over the same panel's first ring.

    This computes only a trial. Admission requires source-UV metric and linear
    trajectory checks in solve_placement; no source rest, topology or pin moves.
    """
    owners = _ownership(payload, len(coordinates)); fixed = set(protected)
    if not 0 < fraction <= 1:
        raise StudioError('Relaxation backtracking fraction must be bounded')
    adjacency = {i: set() for i in range(len(coordinates))}
    for face in payload['faces']:
        if len(face) != 3 or any(index not in owners for index in face):
            raise StudioError('Relaxation requires the actual indexed triangle topology')
        for a, b in zip(face, face[1:]+face[:1]):
            if owners[a] == owners[b]:
                adjacency[a].add(b); adjacency[b].add(a)
    corrections = {}
    for index, vector in _contacts(report, len(coordinates)):
        if index in fixed:
            continue
        for affected in {index, *adjacency[index]}-fixed:
            corrections.setdefault(affected, []).append(vector)
    trial = copy.deepcopy(coordinates)
    for index, values in sorted(corrections.items()):
        average = [sum(v[i] for v in values)/len(values) for i in range(3)]
        vector = _bounded(average, max_step_cm*fraction)
        trial[index] = [trial[index][i]+vector[i] for i in range(3)]
    return trial


def solve_placement(payload, coordinates, evaluate, specification, clock=time.monotonic, *,
                    displacement_reference=None, protected_stop_reference=None):
    """Automatically propose bounded repairs; preserve all final gate decisions.

    Evaluator returns ``score`` (finite >= 0), ``hard_valid`` (unchanged final
    gates), and optional contacts for proposal generation. An optional
    candidate_sha256 must match points. Candidate readiness requires both the
    declared target_score and the existing final hard gates. No Cloth/fitting
    execution or acceptance follows from this pure geometric result.

    Optional ``protected_stop_reference`` freezes numerical protected_indices
    at an already measured phase entry. It requires explicit ORIGINAL
    displacement_reference, full finite mapping and exact current-entry stop
    coordinates. Physical pins always remain at the ORIGINAL guide coordinates.
    The original displacement budget still includes every earlier correction.
    The caller authenticates any preceding body/anchor measurement; this option
    establishes no native origin or contact acceptance. None preserves the
    historical policy and receipt shape, including shifted-support refusal.
    """
    contract('placement-correction', specification)
    count = len(payload['rest_cm'])
    if count != len(coordinates) or not count or any(not _vector(p) for p in coordinates):
        raise StudioError('Solver requires finite coordinates with exact immutable source mapping')
    _ownership(payload, count)
    numerical_fixed = set(specification.get('protected_indices', []))
    protected = set(numerical_fixed); physical_fixed = set()
    for index, weight in payload.get('pins', {}).items():
        if type(weight) not in (int, float) or not math.isfinite(weight) or not 0 <= weight <= 1:
            raise StudioError('Solver pin weights must remain finite and bounded')
        if (not isinstance(index, str) or not index.isdigit() or
                str(index) != str(int(index)) or not 0 <= int(index) < count):
            raise StudioError('Solver pins reference a missing actual coordinate')
        if weight > 0:
            protected.add(int(index)); physical_fixed.add(int(index))
    if any(type(i) is not int or not 0 <= i < count for i in protected):
        raise StudioError('Protected supports reference a missing actual coordinate')
    reference=copy.deepcopy(coordinates if displacement_reference is None else displacement_reference)
    if len(reference)!=count or any(not _vector(p) for p in reference):
        raise StudioError('Displacement reference must cover the exact original source-guide coordinates')
    if max(math.dist(a,b) for a,b in zip(reference,coordinates))>specification['budgets']['max_displacement_cm']:
        raise StudioError('Initial candidate already exceeds the shared displacement budget from its original source guide')
    relocated_stop_policy = protected_stop_reference is not None
    stop_reference = None
    if relocated_stop_policy:
        if displacement_reference is None:
            raise StudioError('A protected stop reference requires an explicit original-guide displacement reference')
        if not numerical_fixed:
            raise StudioError('A protected stop reference requires explicit numerical protected indices')
        if (not isinstance(protected_stop_reference,(list,tuple)) or len(protected_stop_reference)!=count
                or any(not _vector(point) for point in protected_stop_reference)):
            raise StudioError('Protected stop reference must contain one finite 3D coordinate per source vertex')
        stop_reference=copy.deepcopy(protected_stop_reference)
        if any(digest(coordinates[i])!=digest(stop_reference[i]) for i in numerical_fixed):
            raise StudioError('A protected numerical stop does not match its measured stage-entry reference')
    original_fixed = physical_fixed if relocated_stop_policy else protected
    if any(coordinates[i]!=reference[i] for i in original_fixed):
        raise StudioError('An earlier correction changed a protected original source-guide support')
    def immutable_inputs():
        values=[payload, coordinates, specification, displacement_reference]
        return values+[protected_stop_reference] if relocated_stop_policy else values
    original = digest(immutable_inputs())
    source_identity = digest(payload); initial = copy.deepcopy(coordinates)
    limits = specification['quality']; budgets = specification['budgets']
    start = clock(); history = []; seen = {digest(initial)}

    def measurement(points):
        source, trial = copy.deepcopy(payload), copy.deepcopy(points)
        identity = digest([source, trial]); report = evaluate(source, trial)
        if digest([source, trial]) != identity:
            raise StudioError('Placement evaluator mutated an immutable source or candidate')
        if (not isinstance(report, dict) or type(report.get('hard_valid')) is not bool or
                type(report.get('score')) not in (int, float) or not math.isfinite(report['score']) or report['score'] < 0):
            raise StudioError('Placement evaluator must return current finite score and unchanged final gates')
        if 'candidate_sha256' in report and report['candidate_sha256'] != digest(points):
            raise StudioError('Placement evaluator returned stale candidate evidence')
        _contacts(report, count)
        return copy.deepcopy(report)

    # Existing source-metric gates are prerequisite rails. A distorted input
    # guide must be repaired at its source-guide stage, before contact search.
    validate_metrics(payload, initial, limits, include_faces=False, include_bending=False)
    best = initial; best_report = measurement(best); stop = 'ITERATION_BUDGET'; stagnant = 0; iterations = 0
    kernel_phase='rigid' if 'rigid' in specification['kernels'] else 'relaxation'
    for iteration in range(1, budgets['max_iterations']+1):
        if best_report['hard_valid'] and best_report['score'] <= budgets['target_score']:
            stop = 'FINAL_GATES_PASSED'; break
        if clock()-start >= budgets['max_seconds']:
            stop = 'TIME_BUDGET'; break
        iterations = iteration; improved = False; proposed = 0
        # Evaluate each iteration against one fixed best snapshot. Mutating the
        # baseline halfway through a proposal batch would stale its contacts.
        baseline, report = copy.deepcopy(best), copy.deepcopy(best_report)
        trials = []
        if kernel_phase=='rigid':
            for proposal in measured_rigid_proposals(payload, baseline, report, budgets['max_step_cm'], protected):
                trials.append(('rigid', rigid_candidate(payload, baseline, proposal), proposal))
                if len(trials) >= budgets['max_proposals_per_iteration']:
                    break
        if kernel_phase=='relaxation':
            for fraction in (1., .5, .25, .125):
                trials.append(('relaxation', constrained_relaxation_candidate(payload, baseline, report,
                    budgets['max_step_cm'], protected, fraction), {'fraction': fraction}))
                if len(trials) >= budgets['max_proposals_per_iteration']:
                    break
        for kernel, trial, proposal in trials:
            if clock()-start >= budgets['max_seconds']:
                stop = 'TIME_BUDGET'; break
            proposed += 1; identity = digest(trial)
            movement = max(math.dist(a, b) for a, b in zip(reference, trial))
            record = {'iteration': iteration, 'kernel': kernel, 'proposal': proposal,
                      'candidate_sha256': identity, 'displacement_cm': movement, 'kept': False}
            if identity in seen:
                record['reason'] = 'REPEATED_CANDIDATE'
            elif movement > budgets['max_displacement_cm']:
                record['reason'] = 'DISPLACEMENT_BUDGET'
            elif any(trial[i] != initial[i] for i in protected):
                record['reason'] = 'PROTECTED_SUPPORT'
            else:
                seen.add(identity)
                try:
                    validate_linear_motion(payload, baseline, trial)
                    metrics = validate_metrics(payload, trial, limits, include_faces=False, include_bending=False)
                except StudioError as error:
                    record.update(reason='SOURCE_METRIC_OR_TRAJECTORY_GATE', violations=getattr(error, 'quality_violations', [str(error)]))
                else:
                    trial_report = measurement(trial)
                    # Once final gates pass, no exploratory failure can replace
                    # that admissible geometry merely by reducing its score.
                    keep = (not best_report['hard_valid'] or trial_report['hard_valid']) and (
                        best_report['score']-trial_report['score'] > budgets['min_improvement'] or
                        trial_report['hard_valid'] and not best_report['hard_valid'] and trial_report['score'] <= best_report['score'])
                    record.update(reason='MEASURED_IMPROVEMENT' if keep else 'NO_ADMISSIBLE_IMPROVEMENT',
                                  measurement=trial_report, metric_extrema=metrics['extrema'], kept=keep)
                    if keep:
                        best, best_report, improved = trial, trial_report, True
            history.append(record)
        if best_report['hard_valid'] and best_report['score'] <= budgets['target_score']:
            stop = 'FINAL_GATES_PASSED'; break
        if stop == 'TIME_BUDGET': break
        if not improved and kernel_phase=='rigid' and 'relaxation' in specification['kernels']:
            # A saturated rigid proposal budget must not starve relaxation.
            # Enter its separate constrained phase only after rigid stagnation.
            kernel_phase='relaxation';stagnant=0
            continue
        stagnant = 0 if improved else stagnant+1
        if not proposed or stagnant >= budgets['stagnation_iterations']:
            stop = 'STAGNATION'; break
    if digest(immutable_inputs()) != original:
        raise StudioError('Solver source changed during execution')
    result = {'version': 1, 'status': 'GEOMETRIC_GATES_PASSED' if stop == 'FINAL_GATES_PASSED' else 'NEEDS_CORRECTION',
            'stop_reason': stop, 'coordinates_cm': best, 'measurement': best_report, 'history': history,
            'iterations': iterations, 'elapsed_seconds': clock()-start,'terminal_kernel_phase':kernel_phase,
            'source_sha256': source_identity, 'candidate_sha256': digest(best),
            'displacement_reference_sha256':digest(reference),
            'max_displacement_cm':max(math.dist(a,b) for a,b in zip(reference,best)),
            'specification_sha256': digest(specification), 'protected_indices': sorted(protected),
            'source_mutated': False, 'source_uv_scaled': False, 'qualification': 'NONE',
            'simulation': 'NOT_EXECUTED', 'fitting': 'NOT_EXECUTED',
            'final_assessment': 'REQUIRED_BEFORE_NATIVE_ADMISSION'}
    if relocated_stop_policy:
        result.update(protected_stop_reference_sha256=digest(stop_reference),
            protected_stop_reference_policy='FREEZE_MEASURED_STAGE_ENTRY_NUMERICAL_STOPS',
            numerical_fixed_indices=sorted(numerical_fixed), physical_fixed_indices=sorted(physical_fixed),
            relocated_numerical_stop_indices=sorted(i for i in numerical_fixed
                if digest(coordinates[i])!=digest(reference[i])))
        if digest(immutable_inputs()) != original:
            raise StudioError('Solver source changed before returning measured stop references')
    return result
