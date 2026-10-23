"""Bounded single-piece metric feasibility; fixed controls/UV/topology unchanged.

Exploratory local/global polar projection with a column-scaled QR solve. This
does not qualify developability, contacts, sewing, material physics or fitting.
"""
import os
os.environ.setdefault('OPENBLAS_NUM_THREADS', '1')
os.environ.setdefault('OMP_NUM_THREADS', '1')
import argparse
import copy
import hashlib
import heapq
import json
import math
from pathlib import Path
import time
import zipfile

import numpy as np
from scipy.linalg import qr, solve_triangular


def sha(path):
    return hashlib.sha256(Path(path).read_bytes()).hexdigest()


def metric(cage, targets=None, tolerance=.02):
    uv = np.asarray(cage['uv_cm'], dtype=float)
    xyz = np.asarray(cage['target_cm'] if targets is None else targets, dtype=float)
    faces = np.asarray(cage['triangles'], dtype=int)
    delta = uv[faces[:, 1:]]-uv[faces[:, 0, None]]
    deformation = np.linalg.solve(delta, xyz[faces[:, 1:]]-xyz[faces[:, 0, None]])
    singular = np.linalg.svd(deformation, compute_uv=False)
    bad = (singular[:, 1] < 1-tolerance) | (singular[:, 0] > 1+tolerance)
    area = np.abs(np.linalg.det(delta))/2
    return {'principal_min': float(singular[:, 1].min()), 'principal_max': float(singular[:, 0].max()),
        'max_metric_excess': float(max(0., 1-tolerance-singular[:, 1].min(), singular[:, 0].max()-(1+tolerance))),
        'outside_triangles': int(bad.sum()), 'outside_source_area_fraction': float(area[bad].sum()/area.sum()),
        'source_area_cm2': float(area.sum())}


def solve(cage, fixed_indices, settings, output=None):
    started = time.monotonic(); clock = lambda: time.monotonic()-started
    seconds = settings['max_seconds']; tolerance = settings['strain_tolerance']
    if not 0 < seconds <= 120 or not 0 < tolerance <= .02:
        raise ValueError('Explicit bounded experiment required')
    uv = np.asarray(cage['uv_cm'], dtype=float); initial = np.asarray(cage['target_cm'], dtype=float)
    faces = np.asarray(cage['triangles'], dtype=int); fixed = np.asarray(sorted(set(fixed_indices)), dtype=int)
    if not len(fixed) or len(fixed) != len(fixed_indices): raise ValueError('Explicit distinct fixed controls required')
    free = np.asarray([i for i in range(len(uv)) if i not in set(fixed)], dtype=int)
    control_limit = settings.get('max_dense_free_controls', 1024)
    byte_limit = settings.get('max_dense_estimated_bytes', 128*1024*1024)
    if type(control_limit) is not int or not 1 <= control_limit <= 2048 or type(byte_limit) is not int or not 1 <= byte_limit <= 512*1024*1024:
        raise ValueError('Bounded dense matrix budget required')
    # Include the operator, augmented system, QR copies/workspace and RHS.
    # This is a conservative dimension budget, not a measured RSS guarantee.
    rows = len(faces)*2; columns = len(free)
    dense_bytes = 8*(rows*len(uv)+5*(rows+columns)*columns+3*columns*columns+12*len(uv))
    if columns > control_limit or dense_bytes > byte_limit:
        raise ValueError('DENSE_DIMENSION_BUDGET_EXHAUSTED_BEFORE_MATRIX_ALLOCATION')
    delta = uv[faces[:, 1:]]-uv[faces[:, 0, None]]; inverse = np.linalg.inv(delta)
    coefficients = np.stack((-inverse.sum(axis=2), inverse[:, :, 0], inverse[:, :, 1]), axis=2)
    operator = np.zeros((len(faces)*2, len(uv)))
    for k in range(3):
        operator[np.arange(len(faces)*2), np.repeat(faces[:, k], 2)] = coefficients[:, :, k].reshape(-1)
    center = initial[fixed].mean(axis=0); local_initial = initial-center
    regularization = math.sqrt(settings['position_penalty'])
    system = np.vstack((operator[:, free], regularization*np.eye(len(free))))
    scale = np.linalg.norm(system, axis=0)
    system /= scale
    factor_started = clock(); q, r = qr(system, mode='economic', check_finite=True)
    factor_seconds = clock()-factor_started
    if clock() >= seconds:
        raise TimeoutError('TIME_BUDGET_EXHAUSTED_AFTER_FACTORIZATION')
    fixed_effect = operator[:, fixed]@local_initial[fixed]
    x = local_initial.copy(); best = initial.copy(); best_metrics = metric(cage, best, tolerance)
    best_score = (best_metrics['max_metric_excess'], best_metrics['outside_source_area_fraction'])
    best_iteration = 0; observations = []; status = 'ITERATION_BUDGET_EXHAUSTED'
    if not np.allclose((operator@local_initial).reshape((-1, 2, 3)),
            np.linalg.solve(delta, initial[faces[:, 1:]]-initial[faces[:, 0, None]]), atol=1e-6, rtol=1e-6):
        raise ValueError('Gradient operator differs from source metric evaluator')
    for iteration in range(1, settings['max_iterations']+1):
        if clock() >= seconds:
            status = 'TIME_BUDGET_EXHAUSTED'; break
        deformation = (operator@x).reshape((-1, 2, 3))
        u, singular, vt = np.linalg.svd(deformation, full_matrices=False)
        target_singular = np.clip(singular, 1-settings['projection_strain_tolerance'], 1+settings['projection_strain_tolerance'])
        projected = np.einsum('fij,fj,fjk->fik', u, target_singular, vt).reshape((-1, 3))
        rhs = np.vstack((projected-fixed_effect, regularization*local_initial[free]))
        free_next = solve_triangular(r, q.T@rhs, lower=False, check_finite=False)/scale[:, None]
        candidate = x.copy(); candidate[free] = free_next; candidate[fixed] = local_initial[fixed]
        displacement = np.linalg.norm(candidate-local_initial, axis=1).max()
        if displacement > settings['max_displacement_cm']:
            candidate = local_initial+(candidate-local_initial)*(settings['max_displacement_cm']/displacement)
            candidate[fixed] = local_initial[fixed]
        x = candidate
        if clock() >= seconds:
            status = 'TIME_BUDGET_EXHAUSTED_AFTER_STEP'; break
        if iteration == 1 or iteration % settings['observation_stride'] == 0 or iteration == settings['max_iterations']:
            world = x+center; world[fixed] = initial[fixed]
            values = metric(cage, world, tolerance)
            record = {'iteration': iteration, 'elapsed_seconds': clock(), **values,
                'max_displacement_cm': float(np.linalg.norm(world-initial, axis=1).max()),
                'fixed_targets_exact': bool(np.array_equal(world[fixed], initial[fixed]))}
            observations.append(record)
            if clock() >= seconds:
                record['retained'] = False
                status = 'TIME_BUDGET_EXHAUSTED_AFTER_MEASUREMENT'; break
            score = (values['max_metric_excess'], values['outside_source_area_fraction'])
            if score < best_score:
                best = world.copy(); best_score = score; best_metrics = values; best_iteration = iteration
            if output is not None:
                (output/'latest-observation.json').write_text(json.dumps(record, indent=2), encoding='utf-8')
            if clock() >= seconds:
                status = 'TIME_BUDGET_EXHAUSTED_AFTER_OBSERVATION_WRITE'; break
            if values['outside_triangles'] == 0:
                status = 'SINGLE_PIECE_METRIC_TARGETS_REACHED'; break
    result = copy.deepcopy(cage); result['target_cm'] = best.tolist()
    if result['uv_cm'] != cage['uv_cm'] or result['triangles'] != cage['triangles']:
        raise ValueError('Exploratory solver changed immutable material mesh')
    if any(result['target_cm'][int(i)] != cage['target_cm'][int(i)] for i in fixed):
        raise ValueError('Fixed anatomical target changed')
    elapsed = clock()
    if elapsed >= seconds:
        status = 'TIME_BUDGET_EXHAUSTED'
    return result, {'status': status, 'best_iteration': best_iteration, 'best': best_metrics,
        'observations': observations, 'factor_seconds': factor_seconds, 'elapsed_seconds': elapsed,
        'free_controls': len(free), 'fixed_controls': fixed.tolist(), 'settings': settings,
        'dense_dimension_budget': {'free_controls_limit': control_limit, 'estimated_bytes_limit': byte_limit,
            'estimated_bytes': dense_bytes, 'scope': 'CONSERVATIVE_DIMENSION_ESTIMATE_NOT_RSS'},
        'qr_diagonal_ratio': float(np.abs(np.diag(r)).max()/np.abs(np.diag(r)).min()),
        'fixed_targets_exact': True, 'source_uv_and_triangles_unchanged': True,
        'contacts': 'NOT_ASSESSED', 'external_seams': 'NOT_SOLVED', 'developability': 'NOT_CERTIFIED', 'qualification': 'NONE'}


def main():
    parser = argparse.ArgumentParser(); parser.add_argument('--request', required=True)
    request_path = Path(parser.parse_args().request); request = json.loads(request_path.read_text(encoding='utf-8'))
    out = Path(request['output_directory']); out.mkdir(exist_ok=False)
    def read(ref):
        if sha(ref['path']) != ref['sha256']: raise ValueError('Input SHA mismatch')
        return json.loads(Path(ref['path']).read_text(encoding='utf-8'))
    frames = read(request['cages_ref']); preparation = read(request['preparation_ref'])
    pid = request['piece_id']; cage = frames[pid]; fixed = preparation['fixed_controls'][pid]
    # Verify that the fixed variables are the actual recorded anatomical targets.
    attachment_rows = [row for row in preparation['attachments'] if row['piece'] == pid]
    if sorted({i for row in attachment_rows for i in row['fixed_controls']}) != sorted(fixed):
        raise ValueError('Fixed set differs from authenticated attachment supports')
    for row in attachment_rows:
        if len(row['fixed_controls']) != 1: raise ValueError('This experiment requires explicit vertex attachments')
        i = row['fixed_controls'][0]
        if cage['uv_cm'][i] != row['source_uv_cm'] or cage['target_cm'][i] != row['target_world_cm']:
            raise ValueError('Current fixed control differs from recorded anatomy')
    uv = np.asarray(cage['uv_cm']); xyz = np.asarray(cage['target_cm']); fs = np.asarray(cage['triangles'])
    delta = uv[fs[:, 1:]]-uv[fs[:, 0, None]]; areas = np.abs(np.linalg.det(delta))/2
    condition = np.linalg.cond(delta); singular = np.linalg.svd(np.linalg.solve(delta, xyz[fs[:, 1:]]-xyz[fs[:, 0, None]]), compute_uv=False)
    edges = {tuple(sorted((int(a), int(b)))) for face in fs for a, b in zip(face, np.roll(face, -1))}
    pairs = []; adjacency = [[] for _ in uv]
    for a, b in edges:
        length = math.dist(uv[a], uv[b]); adjacency[a].append((b, length)); adjacency[b].append((a, length))
    for rank, a in enumerate(fixed):
        # A chord in source UV can cross a hole or concave exterior. A path
        # through the actual material cage edges is always the valid necessary
        # upper bound; it is not claimed to be the shortest surface geodesic.
        distances = {a: 0.}; pending = [(0., a)]
        while pending:
            distance, index = heapq.heappop(pending)
            if distance != distances[index]: continue
            for neighbour, edge_length in adjacency[index]:
                total = distance+edge_length
                if total < distances.get(neighbour, math.inf):
                    distances[neighbour] = total; heapq.heappush(pending, (total, neighbour))
        for b in fixed[rank+1:]:
            length = distances.get(b); chord = math.dist(xyz[a], xyz[b])
            pairs.append({'controls': [a, b], 'source_cage_edge_path_cm': length,
                'source_straight_distance_cm': math.dist(uv[a], uv[b]), 'target_chord_cm': chord,
                'ratio': chord/length if length else None, 'source_mesh_edge': tuple(sorted((a, b))) in edges,
                'bound_scope': 'EXISTING_MATERIAL_EDGE_PATH_NECESSARY_ONLY',
                'upper_metric_necessary_bound_violated': length is not None and chord > (1+request['settings']['strain_tolerance'])*length})
    report = {'scope': 'ONE_EXACT_PIECE_FIXED_ANATOMICAL_ATTACHMENTS', 'piece_id': pid,
        'inputs': {k: request[k] for k in ('cages_ref', 'preparation_ref')},
        'initial': metric(cage), 'fixed_anchors': attachment_rows, 'anchor_pairs': pairs,
        'anchor_pair_incompatibilities': sum(row['upper_metric_necessary_bound_violated'] for row in pairs),
        'smallest_source_triangles': [{'face': int(i), 'source_area_cm2': float(areas[i]),
            'condition_number': float(condition[i]), 'uv_cm': uv[fs[i]].tolist(), 'control_indices': fs[i].tolist(),
            'principal': singular[i][::-1].tolist()} for i in np.argsort(areas)[:12]],
        'helper_sha256': sha(__file__), 'request_sha256': sha(request_path), 'qualification': 'NONE'}
    (out/'audit.json').write_text(json.dumps(report, indent=2, allow_nan=False), encoding='utf-8')
    solve_started = time.monotonic()
    try:
        candidate, result = solve(cage, fixed, request['settings'], out)
    except TimeoutError as error:
        candidate = copy.deepcopy(cage)
        result = {'status': str(error), 'best_iteration': 0, 'best': metric(cage),
            'factor_seconds': None, 'elapsed_seconds': time.monotonic()-solve_started,
            'settings': request['settings'], 'fixed_targets_exact': True, 'qualification': 'NONE'}
    (out/'candidate-cage.json').write_text(json.dumps(candidate, separators=(',', ':'), allow_nan=False), encoding='utf-8')
    after_save = time.monotonic()-solve_started
    if after_save >= request['settings']['max_seconds']:
        result['status'] = 'TIME_BUDGET_EXHAUSTED_AFTER_CANDIDATE_SAVE'
    result['elapsed_with_candidate_save_seconds'] = after_save
    result.update(inputs=report['inputs'], helper_sha256=sha(__file__), request_sha256=sha(request_path),
        candidate_sha256=sha(out/'candidate-cage.json'), audit_sha256=sha(out/'audit.json'), piece_id=pid,
        inputs_unchanged=all(sha(request[k]['path']) == request[k]['sha256'] for k in ('cages_ref', 'preparation_ref')))
    if time.monotonic()-solve_started >= request['settings']['max_seconds']:
        result['status'] = 'TIME_BUDGET_EXHAUSTED_AFTER_OUTPUT_VERIFICATION'
    (out/'report.json').write_text(json.dumps(result, indent=2, allow_nan=False), encoding='utf-8')
    if time.monotonic()-solve_started >= request['settings']['max_seconds'] and result['status'] == 'SINGLE_PIECE_METRIC_TARGETS_REACHED':
        result['status'] = 'TIME_BUDGET_EXHAUSTED_AFTER_REPORT_SAVE'
        (out/'report.json').write_text(json.dumps(result, indent=2, allow_nan=False), encoding='utf-8')
    print(json.dumps({k: result[k] for k in ('status', 'best_iteration', 'best', 'factor_seconds', 'elapsed_seconds', 'fixed_targets_exact')}))


if __name__ == '__main__': main()
