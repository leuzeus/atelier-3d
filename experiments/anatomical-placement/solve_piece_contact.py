"""Exploratory metric QR + scalar native-face contacts, never admission.

The caller authenticates an existing full triangle contact receipt. Every local
plane keeps its own source triangle; no nearest-sheet selection, pseudonormal,
global inside sign, fixed-point movement or external seam closure is used.
"""
import os
os.environ.setdefault('OPENBLAS_NUM_THREADS', '1')
os.environ.setdefault('OMP_NUM_THREADS', '1')
import argparse
import collections
import copy
import hashlib
import json
import math
from pathlib import Path
import sys
import time
import numpy as np
from scipy.linalg import qr, solve_triangular
from solve_piece_metric import metric


def sha(path): return hashlib.sha256(Path(path).read_bytes()).hexdigest()
def require(value, message):
    if not value: raise ValueError(message)


class Budget:
    def __init__(self, settings):
        self.start = time.monotonic(); self.settings = settings; self.counts = collections.Counter()
        require(0 < settings['max_seconds'] <= 120, 'BOUNDED_TIME_REQUIRED')
    def check(self):
        if self.elapsed >= self.settings['max_seconds']: raise TimeoutError('COMMON_TIME_BUDGET_EXHAUSTED')
    @property
    def elapsed(self): return time.monotonic()-self.start
    def take(self, key, amount=1):
        self.check(); self.counts[key] += amount
        if self.counts[key] > self.settings['max_'+key]: raise TimeoutError(key.upper()+'_BUDGET_EXHAUSTED')


def barycentric(point, triangle):
    """No clipping or snapping: refuse an unrepresentable actual witness."""
    t = np.asarray(triangle); p = np.asarray(point); edges = (t[1:]-t[0]).T
    weights, _, rank, s = np.linalg.lstsq(edges, p-t[0], rcond=None)
    require(rank == 2 and s[-1] > 0, 'UNREPRESENTABLE_WITNESS_TRIANGLE')
    condition = s[0]/s[-1]
    guard = 512*np.finfo(float).eps*max(1., condition)
    require(guard <= 1e-5, 'UNRESOLVED_WITNESS_BARYCENTRIC_CONDITIONING')
    result = np.r_[1-weights.sum(), weights]
    require(float(result.min()) >= -guard and float(result.max()) <= 1+guard,
            'WITNESS_OUTSIDE_RECORDED_TRIANGLE')
    require(np.linalg.norm(result@t-p) <= guard*max(1., np.linalg.norm(t, axis=1).max()),
            'WITNESS_RECONSTRUCTION_MISMATCH')
    return result


def orientation_report(vertices, indices):
    """Native local winding only; closed + oriented is not self-intersection proof."""
    vertices = np.asarray(vertices); indices = np.asarray(indices)
    edges = collections.defaultdict(list)
    for fid, face in enumerate(indices):
        for a, b in zip(face, np.roll(face, -1)): edges[tuple(sorted((int(a), int(b))))].append((int(a), int(b), fid))
    bad = [key for key, rows in edges.items() if len(rows) != 2 or rows[0][:2] != rows[1][1::-1]]
    require(not bad, 'BODY_NATIVE_TRIANGLES_NOT_CLOSED_AND_CONSISTENTLY_ORIENTED')
    # Record signed volume, do not reverse any normals from this scalar.
    t = vertices[indices]; center = vertices.mean(axis=0); tc = t-center
    volume = float(np.einsum('ij,ij->i', tc[:, 0], np.cross(tc[:, 1], tc[:, 2])).sum()/6)
    require(math.isfinite(volume) and volume > 0, 'POSITIVE_NATIVE_ORIENTATION_NOT_VERIFIED')
    cross = np.cross(t[:, 1]-t[:, 0], t[:, 2]-t[:, 0]); size = np.linalg.norm(cross, axis=1)
    require(np.all(size > 0) and np.isfinite(size).all(), 'BODY_TRIANGLE_DEGENERATE')
    return cross/size[:, None], {'closed_consistent_winding': True, 'positive_signed_volume_cm3': volume,
        'normal_scope': 'ORIENTED_NATIVE_FACE_PLANE_ONLY', 'self_intersections': 'NOT_VERIFIED',
        'global_inside_outside': 'NOT_ASSESSED', 'normal_flips': 0}


class Body:
    def __init__(self, geometry, indices, kernel, budget):
        self.kernel = kernel; self.budget = budget; self.vertices = np.asarray(geometry['vertices_cm'])
        self.indices = np.asarray(indices); self.triangles = self.vertices[self.indices]
        self.normals, self.orientation = orientation_report(self.vertices, self.indices)
        self.tree = kernel.TriangleBVH(self.triangles.tolist()); membership = collections.defaultdict(set)
        for fid, face in enumerate(geometry['faces']):
            for i in face: membership[i].add(fid)
        self.owners = []
        for tri in self.indices:
            common = set.intersection(*(membership[int(i)] for i in tri))
            require(len(common) == 1, 'BODY_OWNER_AMBIGUOUS'); self.owners.append(next(iter(common)))
        self.regions = geometry['face_sets']; budget.check()

    def audit(self, cage, xyz, reserve):
        k = self.kernel; rows = []; failed = []; fs = cage['triangles']; work = collections.Counter()
        for fid, face in enumerate(fs):
            self.budget.check(); tri = xyz[face].tolist(); box = k.triangle_bounds(tri); pending = [self.tree.root]
            while pending:
                self.budget.take('bvh_nodes'); node = pending.pop()
                if k.bounds_distance_sq(box, node[0]) > reserve*reserve: continue
                if node[1] is None: pending.extend((node[2], node[3])); continue
                for bid in node[1]:
                    if k.bounds_distance_sq(box, self.tree.bounds[bid]) > reserve*reserve: continue
                    bt = self.triangles[bid].tolist()
                    if k.separated_projection(tri, bt, reserve): continue
                    self.budget.take('exact_triangle_tests'); work['exact_triangle_tests'] += 1
                    try: observed = k.triangle_contact(tri, bt)
                    except Exception as error:
                        failed.append({'cage_triangle': fid, 'body_triangle': bid, 'reason': str(error)}); continue
                    if observed['distance_cm'] <= reserve:
                        self.budget.take('contact_rows')
                        rows.append({'cage_triangle': fid, 'body_triangle': bid, 'body_source_face': self.owners[bid],
                            'body_region_id': self.regions[self.owners[bid]], **observed})
        self.budget.check()
        return {'coverage_complete': True, 'completed_triangles': len(fs), 'contacts': rows,
                'unrepresentable_pairs': failed, 'work': dict(work)}


def contact_summary(audit, reserve):
    return {'coverage_complete': audit['coverage_complete'], 'completed_triangles': audit['completed_triangles'],
        'intersections': sum(row['kind'] != 'SEPARATED' for row in audit['contacts']),
        'below_reserve_pairs': sum(row['distance_cm'] < reserve for row in audit['contacts']),
        'sum_squared_unsigned_deficit_cm2': sum(max(0., reserve-row['distance_cm'])**2 for row in audit['contacts']),
        'unrepresentable_pairs': len(audit['unrepresentable_pairs'])}


def scalar_rows(cage, xyz, audit, body, fixed, reserve, max_rows, activation_distance=None, computation_margin=0.):
    require(not audit['unrepresentable_pairs'], 'UNREPRESENTABLE_CONTACTS_NOT_DISCARDED')
    require(len(audit['contacts']) <= max_rows, 'ACTIVE_SCALAR_DIMENSION_BUDGET')
    n = len(xyz); rows = []; bounds = []; records = []; fixed_set = set(fixed)
    activation_distance = reserve if activation_distance is None else activation_distance
    require(math.isfinite(activation_distance) and reserve <= activation_distance <= reserve+1., 'EXPLICIT_ACTIVATION_BAND_REQUIRED')
    require(type(computation_margin) in (int, float) and math.isfinite(computation_margin) and 0 <= computation_margin <= .1,
            'BOUNDED_EXPLICIT_COMPUTATION_MARGIN_REQUIRED')
    required_offset = reserve+computation_margin
    for contact in audit['contacts']:
        if contact['distance_cm'] >= activation_distance: continue
        face = cage['triangles'][contact['cage_triangle']]; bid = contact['body_triangle']
        weights = barycentric(contact['point_a_cm'], xyz[face]); q = np.asarray(contact['point_b_cm'])
        body_weights = barycentric(q, body.triangles[bid]); normal = body.normals[bid]
        # Keep every recorded body triangle separately, including shared-feature
        # planes. Their intersection is a conservative local proposal; no mean
        # normal or one-sided branch selection is introduced.
        row = np.zeros((n, 3)); row[face] = weights[:, None]*normal
        bound = float(normal@q+required_offset); offset = float(np.sum(row*xyz)-normal@q)
        record = {'cage_triangle': contact['cage_triangle'], 'body_triangle': bid,
            'body_source_face': contact['body_source_face'], 'source_controls': face,
            'source_barycentric': weights.tolist(), 'body_barycentric': body_weights.tolist(),
            'body_point_cm': q.tolist(), 'normal': normal.tolist(), 'bound_cm': bound,
            'current_oriented_offset_cm': offset, 'original_contact_kind': contact['kind'],
            'activation_distance_cm': activation_distance, 'physical_reserve_cm': reserve,
            'computation_margin_cm': computation_margin, 'required_local_offset_cm': required_offset,
            'normal_scope': 'EACH_RECORDED_ORIENTED_NATIVE_FACE_PLANE',
            'shared_feature_policy': 'PRESERVE_ALL_RECORDED_PLANES_NO_PSEUDONORMAL'}
        if all(i in fixed_set or abs(weights[j]) == 0 for j, i in enumerate(face)) and offset < required_offset:
            raise ValueError('FIXED_SUPPORT_CONFLICT:'+json.dumps(record))
        rows.append(row); bounds.append(bound); records.append(record)
    return np.asarray(rows).reshape((-1, n, 3)), np.asarray(bounds), records


class MetricFactor:
    def __init__(self, cage, fixed, settings, budget):
        self.initial = np.asarray(cage['target_cm']); uv = np.asarray(cage['uv_cm']); faces = np.asarray(cage['triangles'])
        self.fixed = np.asarray(fixed); self.free = np.asarray([i for i in range(len(uv)) if i not in set(fixed)])
        n = len(uv); nf = len(self.free); rows = len(faces)*2
        estimate = 8*(rows*n+5*(rows+nf)*nf+3*nf*nf+12*n)
        require(nf <= 1024 and estimate <= 128*1024*1024, 'DENSE_METRIC_BUDGET')
        inv = np.linalg.inv(uv[faces[:, 1:]]-uv[faces[:, 0, None]])
        coeff = np.stack((-inv.sum(axis=2), inv[:, :, 0], inv[:, :, 1]), axis=2)
        self.operator = np.zeros((rows, n))
        for k in range(3): self.operator[np.arange(rows), np.repeat(faces[:, k], 2)] = coeff[:, :, k].reshape(-1)
        self.center = self.initial[self.fixed].mean(axis=0); self.local_initial = self.initial-self.center
        self.reg = math.sqrt(settings['position_penalty']); self.fixed_effect = self.operator[:, self.fixed]@self.local_initial[self.fixed]
        system = np.vstack((self.operator[:, self.free], self.reg*np.eye(nf)))
        self.scale = np.linalg.norm(system, axis=0); self.q, self.r = qr(system/self.scale, mode='economic')
        budget.check()
    def step(self, world):
        x = world-self.center; deformation = (self.operator@x).reshape((-1, 2, 3))
        u, _, vt = np.linalg.svd(deformation, full_matrices=False)
        projected = (u@vt).reshape((-1, 3))
        rhs = np.vstack((projected-self.fixed_effect, self.reg*self.local_initial[self.free]))
        value = solve_triangular(self.r, self.q.T@rhs, lower=False, check_finite=False)/self.scale[:, None]
        result = world.copy(); result[self.free] = value+self.center; result[self.fixed] = self.initial[self.fixed]
        return result
    def inverse(self, rhs):
        first = solve_triangular(self.r.T, rhs/self.scale[:, None], lower=True, check_finite=False)
        return solve_triangular(self.r, first, lower=False, check_finite=False)/self.scale[:, None]


class ScalarProjection:
    def __init__(self, factor, rows, bounds, budget):
        self.factor = factor; self.rows = rows; self.bounds = bounds; self.budget = budget
        m = len(rows); nf = len(factor.free)
        require(m <= 1200 and 8*(6*m*nf+3*m*m) <= 128*1024*1024, 'DENSE_CONTACT_BUDGET')
        free_rows = rows[:, factor.free, :]
        rhs = free_rows.transpose(1, 2, 0).reshape((nf, -1))
        response = factor.inverse(rhs).reshape((nf, 3, m)).transpose((2, 0, 1))
        self.response = response; flat = free_rows.reshape((m, -1))
        self.gram = flat@response.reshape((m, -1)).T
        self.gram = (self.gram+self.gram.T)/2
        require(np.isfinite(self.gram).all() and np.all(np.diag(self.gram) > 0), 'SCALAR_COMPLIANCE_NOT_REPRESENTABLE')
        self.multipliers = np.zeros(m); budget.check()
    def project(self, xyz, sweeps):
        needed = self.bounds-np.einsum('mij,ij->m', self.rows, xyz)
        # Hildreth dual coordinate descent for the simultaneous scalar
        # halfspaces in the QR metric. Not an isotropic point projection.
        lam = self.multipliers.copy(); residual = needed-self.gram@lam
        for _ in range(sweeps):
            self.budget.check()
            for j in range(len(lam)):
                delta = max(0., lam[j]+residual[j]/self.gram[j, j])-lam[j]
                if delta:
                    lam[j] += delta; residual -= delta*self.gram[:, j]
        result = xyz.copy(); result[self.factor.free] += np.einsum('m,mij->ij', lam, self.response)
        result[self.factor.fixed] = self.factor.initial[self.factor.fixed]
        require(np.isfinite(result).all() and np.isfinite(lam).all(), 'NONFINITE_SCALAR_CONTACT_PROPOSAL')
        self.multipliers = lam
        remaining = self.bounds-np.einsum('mij,ij->m', self.rows, result)
        return result, float(max(0., remaining.max(initial=0.)))


def main():
    parser = argparse.ArgumentParser(); parser.add_argument('--request', required=True)
    reqpath = Path(parser.parse_args().request); request = json.loads(reqpath.read_text(encoding='utf-8'))
    settings = request['settings']; budget = Budget(settings); out = Path(request['output_directory']); out.mkdir(exist_ok=False)
    artifacts = {}
    def read(ref):
        p = Path(ref['path']); require(sha(p) == ref['sha256'], 'INPUT_SHA_MISMATCH:'+str(p)); artifacts[str(p)] = ref['sha256']
        answer = json.loads(p.read_text(encoding='utf-8')); budget.check(); return answer
    audit_request = read(request['contact_request_ref']); audit_receipt = read(request['contact_report_ref'])
    require(audit_receipt['request_sha256'] == request['contact_request_ref']['sha256'], 'RECEIPT_REQUEST_MISMATCH')
    initial = read(request['initial_cages_ref'])[request['piece_id']]; prep = read(request['preparation_ref'])
    cage = read(audit_request['candidates'][request['contact_candidate_key']])[request['piece_id']]
    geometry = read(audit_request['body_geometry_ref']); raw = read(audit_request['body_triangles_ref'])
    indices = raw if isinstance(raw, list) else raw['triangles']; fixed = prep['fixed_controls'][request['piece_id']]
    require(cage['uv_cm'] == initial['uv_cm'] and cage['triangles'] == initial['triangles'], 'SOURCE_CHANGED')
    require(cage.get('source_ref') == initial.get('source_ref'), 'SOURCE_REF_CHANGED')
    for row in prep['attachments']:
        if row['piece'] == request['piece_id']:
            require(len(row['fixed_controls']) == 1, 'VERTEX_FIXED_SUPPORT_REQUIRED'); i = row['fixed_controls'][0]
            require(cage['target_cm'][i] == row['target_world_cm'] and cage['uv_cm'][i] == row['source_uv_cm'], 'FIXED_TARGET_MISMATCH')
    require(sorted(set(i for row in prep['attachments'] if row['piece'] == request['piece_id'] for i in row['fixed_controls'])) == sorted(fixed), 'FIXED_INVENTORY_MISMATCH')
    sys.path.insert(0, audit_request['source_root']); import a3d.contact_geometry as kernel
    require(sha(kernel.__file__) == audit_receipt['source_code_sha256'], 'CONTACT_KERNEL_CHANGED')
    artifacts[kernel.__file__] = sha(kernel.__file__)
    for path, value in audit_receipt['artifacts'].items(): require(sha(path) == value, 'CONTACT_AUDIT_INPUT_STALE:'+path)
    current_audit = copy.deepcopy(audit_receipt['candidate_reports'][request['contact_candidate_key']])
    current_audit['completed_triangles'] = current_audit['pieces'][request['piece_id']]['completed_triangles']
    require(current_audit['coverage_complete'] and current_audit['completed_triangles'] == len(cage['triangles']), 'INITIAL_CONTACT_COVERAGE_INCOMPLETE')
    reserve = settings.get('physical_reserve_cm', audit_request['clearance_cm'])
    require(type(reserve) in (int, float) and math.isfinite(reserve) and 0 < reserve <= 20., 'EXPLICIT_PHYSICAL_RESERVE_REQUIRED')
    activation = settings.get('contact_activation_distance_cm', reserve)
    require(reserve <= activation <= reserve+1., 'EXPLICIT_ACTIVATION_BAND_REQUIRED')
    computation_margin = settings.get('contact_computation_margin_cm', 0.)
    if 'physical_reserve_ref' in request:
        document = read(request['physical_reserve_ref'])
        value = document
        for key in request['physical_reserve_json_path']: value = value[key]
        require(value == reserve, 'PHYSICAL_RESERVE_SOURCE_MISMATCH')
    initial_xyz = np.asarray(initial['target_cm']); x = np.asarray(cage['target_cm']); best = x.copy(); start_metric = metric(cage, x)
    best_audit = current_audit; accepted = []; trials = []; status = 'OUTER_ITERATION_BUDGET_EXHAUSTED'; body = None
    def rank(values, summary):
        # No priority can turn a failing metric into an admitted result. This
        # merit is merely a recorded exploratory line-search objective.
        metric_penalty = 100*values['max_metric_excess']**2
        return metric_penalty+summary['sum_squared_unsigned_deficit_cm2']
    best_metric = start_metric; best_summary = contact_summary(current_audit, reserve); score = rank(best_metric, best_summary)
    (out/'input-cage.json').write_text(json.dumps(cage, separators=(',', ':'), allow_nan=False), encoding='utf-8')
    (out/'initial-contact-audit.json').write_text(json.dumps(current_audit, separators=(',', ':'), allow_nan=False), encoding='utf-8')
    try:
        body = Body(geometry, indices, kernel, budget); factor = MetricFactor(cage, fixed, settings, budget)
        # Authenticate the old receipt, then explicitly rebind the larger
        # numerical activation band on these exact current positions. Its
        # distance does not replace the physical reserve in any metric.
        if activation != audit_request['clearance_cm']:
            current_audit = body.audit(cage, x, activation)
            best_audit = current_audit; best_summary = contact_summary(current_audit, reserve)
            score = rank(best_metric, best_summary)
            (out/'initial-activation-audit.json').write_text(json.dumps(current_audit, separators=(',', ':'), allow_nan=False), encoding='utf-8')
        for outer in range(settings['max_outer_iterations']):
            budget.check(); rows, bounds, bindings = scalar_rows(cage, x, current_audit, body, fixed, reserve, settings['max_active_rows'], activation, computation_margin)
            (out/f'contact-bindings-{outer:02}.json').write_text(json.dumps(bindings, separators=(',', ':'), allow_nan=False), encoding='utf-8')
            # The disappearance of active contacts does not settle metric
            # recovery. Continue the same bounded QR block, then rebind actual
            # body contacts after movement; no old plane is held as proof.
            projection = ScalarProjection(factor, rows, bounds, budget) if len(rows) else None
            proposal = x.copy(); local_residual = None
            for inner in range(settings['metric_iterations_per_outer']):
                budget.check(); proposal = factor.step(proposal)
                if projection is not None:
                    proposal, local_residual = projection.project(proposal, settings['scalar_sweeps_per_metric_step'])
                movement = float(np.linalg.norm(proposal-initial_xyz, axis=1).max())
                if movement > settings['max_displacement_cm']:
                    proposal = initial_xyz+(proposal-initial_xyz)*(settings['max_displacement_cm']/movement)
                    proposal[fixed] = initial_xyz[fixed]
                budget.check()
            # Both current exact triangle contacts and actual final metric are
            # recomputed after each trial. No stale scalar plane is a gate.
            retained = False
            for alpha in settings['line_search_steps']:
                budget.check(); trial = x+alpha*(proposal-x); trial[fixed] = initial_xyz[fixed]
                values = metric(cage, trial); audit = body.audit(cage, trial, activation)
                summary = contact_summary(audit, reserve); trial_score = rank(values, summary)
                record = {'outer': outer, 'alpha': alpha, 'elapsed_seconds': budget.elapsed, 'metric': values,
                    'contacts': summary, 'merit': trial_score, 'fixed_plane_max_residual_cm': local_residual,
                    'active_rows': len(rows), 'retained': False,
                    'max_displacement_cm': float(np.linalg.norm(trial-initial_xyz, axis=1).max())}
                budget.check()
                trialcage = copy.deepcopy(cage); trialcage['target_cm'] = trial.tolist()
                stem = f'trial-{outer:02}-{str(alpha).replace(".", "_")}'
                (out/(stem+'-cage.json')).write_text(json.dumps(trialcage, separators=(',', ':'), allow_nan=False), encoding='utf-8')
                (out/(stem+'-contacts.json')).write_text(json.dumps(audit, separators=(',', ':'), allow_nan=False), encoding='utf-8')
                budget.check()
                if trial_score < score and not summary['unrepresentable_pairs']:
                    x = trial; best = trial.copy(); current_audit = audit; best_audit = audit
                    best_metric = values; best_summary = summary; score = trial_score
                    retained = True; record['retained'] = True; accepted.append(copy.deepcopy(record))
                trials.append(record)
                (out/'latest-observation.json').write_text(json.dumps(record, indent=2, allow_nan=False), encoding='utf-8')
                budget.check()
                if retained: break
            if not retained: status = 'LINE_SEARCH_STAGNATION'; break
            if best_metric['outside_triangles'] == 0 and best_summary['below_reserve_pairs'] == 0 and best_summary['intersections'] == 0:
                status = 'LOCAL_METRIC_AND_UNSIGNED_CONTACT_TARGETS_REACHED_NOT_ADMITTED'; break
    except (TimeoutError, ValueError) as error:
        status = str(error)
    candidate = copy.deepcopy(cage); candidate['target_cm'] = best.tolist()
    require(candidate['uv_cm'] == initial['uv_cm'] and candidate['triangles'] == initial['triangles'], 'SOURCE_MUTATION')
    require(all(candidate['target_cm'][i] == initial['target_cm'][i] for i in fixed), 'FIXED_MUTATION')
    (out/'candidate-cage.json').write_text(json.dumps(candidate, separators=(',', ':'), allow_nan=False), encoding='utf-8')
    (out/'candidate-contacts.json').write_text(json.dumps(best_audit, separators=(',', ':'), allow_nan=False), encoding='utf-8')
    report = {'status': status, 'qualification': 'NONE', 'admitted': False, 'initial_metric': start_metric,
        'initial_contacts': contact_summary(audit_receipt['candidate_reports'][request['contact_candidate_key']] | {'completed_triangles': len(cage['triangles'])}, reserve),
        'best_metric': best_metric, 'best_contacts': best_summary, 'accepted': accepted, 'trials': trials,
        'elapsed_seconds': budget.elapsed, 'settings': settings, 'work': dict(budget.counts), 'fixed_targets_exact': True,
        'source_uv_and_triangles_unchanged': True, 'max_displacement_from_source_placement_cm': float(np.linalg.norm(best-initial_xyz, axis=1).max()),
        'orientation': body.orientation if body is not None else None, 'external_seams': 'NOT_CLOSED',
        'global_inside_outside': 'NOT_ASSESSED', 'self_contacts': 'NOT_ASSESSED', 'cloth_and_fitting': 'NOT_EXECUTED',
        'request_sha256': sha(reqpath), 'helper_sha256': sha(__file__), 'metric_helper_sha256': sha(Path(__file__).with_name('solve_piece_metric.py')),
        'candidate_sha256': sha(out/'candidate-cage.json'), 'artifacts': artifacts,
        'inputs_unchanged': all(sha(p) == digest for p, digest in artifacts.items())}
    if budget.elapsed >= settings['max_seconds']: report['status'] = 'COMMON_TIME_BUDGET_EXHAUSTED_AFTER_OUTPUT_SAVE'
    (out/'report.json').write_text(json.dumps(report, indent=2, allow_nan=False), encoding='utf-8')
    if budget.elapsed >= settings['max_seconds'] and 'TARGETS_REACHED' in report['status']:
        report['status'] = 'COMMON_TIME_BUDGET_EXHAUSTED_AFTER_REPORT_SAVE'
        (out/'report.json').write_text(json.dumps(report, indent=2, allow_nan=False), encoding='utf-8')
    print(json.dumps({k: report[k] for k in ('status', 'best_metric', 'best_contacts', 'elapsed_seconds', 'fixed_targets_exact')}))


if __name__ == '__main__': main()
