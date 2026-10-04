"""Bounded, measured rigid corrections on disposable panel coordinates.

The caller supplies a read-only metric/contact evaluator and proposed rigid
motions. No pattern metric, construction link, body or threshold is editable.
This pure loop never writes a scene or qualifies Cloth/fitting.
"""
import copy
import math
import time

from .core import StudioError, digest


def _finite_vector(value):
    return (isinstance(value, (list, tuple)) and len(value) == 3
            and all(type(x) in (int, float) and math.isfinite(x) for x in value))


def rigid_candidate(payload, coordinates, proposal):
    if set(proposal)=={'motions'}:
        motions=proposal['motions']
        if not isinstance(motions,list) or not 1<=len(motions)<=len(payload['panels']):
            raise StudioError('Compound correction requires bounded actual panel motions')
        touched=set();result=copy.deepcopy(coordinates)
        for motion in motions:
            if not isinstance(motion,dict) or set(motion)!={'panels','rotation','origin_cm','translation_cm'}:
                raise StudioError('Compound correction permits only non-nested rigid motions')
            if touched.intersection(motion['panels']):
                raise StudioError('Compound correction cannot move a panel twice')
            result=rigid_candidate(payload,result,motion);touched.update(motion['panels'])
        return result
    if set(proposal) != {'panels', 'rotation', 'origin_cm', 'translation_cm'}:
        raise StudioError('Placement correction permits only declared rigid panel motions')
    panels = proposal['panels']; rotation = proposal['rotation']
    if not panels or len(set(panels)) != len(panels) or any(pid not in payload['panels'] for pid in panels):
        raise StudioError('Correction must identify unique actual source panels')
    if (len(rotation) != 3 or any(not _finite_vector(row) for row in rotation)
            or not _finite_vector(proposal['origin_cm']) or not _finite_vector(proposal['translation_cm'])):
        raise StudioError('Rigid correction needs finite rotation, origin and translation')
    for a in range(3):
        for b in range(3):
            if abs(sum(rotation[a][i]*rotation[b][i] for i in range(3))-(1. if a == b else 0.)) > 1e-8:
                raise StudioError('Placement correction cannot scale or shear source geometry')
    determinant = (rotation[0][0]*(rotation[1][1]*rotation[2][2]-rotation[1][2]*rotation[2][1])
                   -rotation[0][1]*(rotation[1][0]*rotation[2][2]-rotation[1][2]*rotation[2][0])
                   +rotation[0][2]*(rotation[1][0]*rotation[2][1]-rotation[1][1]*rotation[2][0]))
    if abs(determinant-1.) > 1e-8:
        raise StudioError('Placement correction cannot reflect the approved panel orientation')
    result = copy.deepcopy(coordinates); owners = {}
    for pid, panel in payload['panels'].items():
        for index in panel['indices']:
            if index in owners or type(index) is not int or not 0 <= index < len(result):
                raise StudioError('Rigid correction needs distinct actual derived panel indices')
            owners[index] = pid
    if set(owners) != set(range(len(result))):
        raise StudioError('Every corrected coordinate needs source panel ownership')
    origin, translation = proposal['origin_cm'], proposal['translation_cm']
    for pid in panels:
        for index in payload['panels'][pid]['indices']:
            point = [result[index][i]-origin[i] for i in range(3)]
            result[index] = [origin[i]+translation[i]+sum(rotation[i][j]*point[j] for j in range(3)) for i in range(3)]
    return result


def correct_placement(payload, coordinates, evaluate, propose, budgets, clock=time.monotonic):
    """Callbacks work on copies; invalid trials never replace the best candidate.

    Evaluator: {score: nonnegative scalar, hard_valid: bool, ...measured evidence}.
    Proposer: iterable of rigid motions, derived from those measurements. Scores
    and hard gates must be declared by the consumer before starting this loop.
    Time is checked between evaluations; an evaluator must bound its own work.
    """
    expected = {'max_iterations', 'max_proposals_per_iteration', 'max_seconds',
                'max_displacement_cm', 'stagnation_iterations', 'target_score', 'min_improvement'}
    if set(budgets) != expected:
        raise StudioError('Correction requires explicit iteration, time, movement and stagnation budgets')
    for key, maximum in [('max_iterations', 1000), ('max_proposals_per_iteration', 100), ('stagnation_iterations', 100)]:
        if type(budgets[key]) is not int or not 1 <= budgets[key] <= maximum:
            raise StudioError('Correction budget outside supported bounds: '+key)
    for key in ('max_seconds', 'max_displacement_cm', 'target_score', 'min_improvement'):
        if type(budgets[key]) not in (int, float) or not math.isfinite(budgets[key]) or budgets[key] < 0:
            raise StudioError('Correction budget must be finite and nonnegative: '+key)
    if not 0 < budgets['max_seconds'] <= 3600:
        raise StudioError('Correction time budget must be positive and bounded')
    if len(coordinates) != len(payload['rest_cm']) or any(not _finite_vector(p) for p in coordinates):
        raise StudioError('Correction requires finite coordinates with exact immutable source mapping')
    source_identity = digest(payload); initial = copy.deepcopy(coordinates)
    start = clock(); history = []; seen = {digest(initial)}; stagnant = 0

    def measurement(points):
        source, trial = copy.deepcopy(payload), copy.deepcopy(points)
        before = digest([source, trial]); report = evaluate(source, trial)
        if digest([source, trial]) != before:
            raise StudioError('Correction evaluator mutated its source or candidate')
        if (not isinstance(report, dict) or type(report.get('hard_valid')) is not bool
                or type(report.get('score')) not in (int, float)
                or not math.isfinite(report['score']) or report['score'] < 0):
            raise StudioError('Correction evaluator must return finite measured score and hard-gate status')
        return copy.deepcopy(report)

    best = initial; best_report = measurement(best); stop = 'ITERATION_BUDGET'; iterations = 0
    for iteration in range(1, budgets['max_iterations']+1):
        if best_report['hard_valid'] and best_report['score'] <= budgets['target_score']:
            stop = 'TARGET_REACHED'; break
        if clock()-start >= budgets['max_seconds']:
            stop = 'TIME_BUDGET'; break
        iterations = iteration; improved = False
        proposal_source, proposal_points, proposal_report = copy.deepcopy(payload), copy.deepcopy(best), copy.deepcopy(best_report)
        before = digest([proposal_source, proposal_points, proposal_report])
        proposals = iter(propose(proposal_source, proposal_points, proposal_report))
        for number in range(budgets['max_proposals_per_iteration']):
            if clock()-start >= budgets['max_seconds']:
                stop = 'TIME_BUDGET'; break
            try: proposal = next(proposals)
            except StopIteration: break
            if digest([proposal_source, proposal_points, proposal_report]) != before:
                raise StudioError('Correction proposer mutated its source or candidate')
            trial = rigid_candidate(payload, best, proposal); identity = digest(trial)
            record = {'iteration': iteration, 'proposal': copy.deepcopy(proposal), 'candidate_sha256': identity}
            movement = max(math.dist(a, b) for a, b in zip(initial, trial))
            if movement > budgets['max_displacement_cm']:
                record.update(kept=False, reason='DISPLACEMENT_BUDGET', displacement_cm=movement)
            elif identity in seen:
                record.update(kept=False, reason='REPEATED_CANDIDATE')
            else:
                seen.add(identity); report = measurement(trial)
                keep = report['hard_valid'] and (not best_report['hard_valid']
                        or best_report['score']-report['score'] > budgets['min_improvement'])
                record.update(kept=keep, reason='IMPROVEMENT' if keep else 'HARD_GATE_OR_NO_IMPROVEMENT',
                              measurement=report, displacement_cm=movement)
                if keep: best, best_report, improved = trial, report, True
            history.append(record)
        if digest([proposal_source, proposal_points, proposal_report]) != before:
            raise StudioError('Correction proposer mutated its source or candidate')
        if best_report['hard_valid'] and best_report['score'] <= budgets['target_score']:
            stop = 'TARGET_REACHED'; break
        if stop == 'TIME_BUDGET': break
        stagnant = 0 if improved else stagnant+1
        if stagnant >= budgets['stagnation_iterations']:
            stop = 'STAGNATION'; break
    if digest(payload) != source_identity:
        raise StudioError('Correction source changed during execution')
    return {'status': 'GEOMETRIC_TARGET_REACHED' if stop == 'TARGET_REACHED' else 'NEEDS_CORRECTION',
            'stop_reason': stop, 'coordinates_cm': best, 'measurement': best_report,
            'history': history, 'iterations': iterations, 'elapsed_seconds': clock()-start,
            'budgets': copy.deepcopy(budgets), 'source_sha256': source_identity,
            'source_mutated': False, 'qualification': 'NONE', 'simulation': 'NOT_EXECUTED',
            'fitting': 'NOT_EXECUTED'}
