"""Private proper-rigid seeds from complete approved source correspondences.

The numerical roundoff policy is not a garment tolerance. A seed, including a
zero-residual seed, never admits placement, coverage, contacts or fitting.
"""
from __future__ import annotations

import math

from .core import digest, sha


_EPS = math.ulp(1.)
_MAX_ROTATIONS = 64


class _Refusal(ValueError):
    def __init__(self, code, message, measurement=None):
        super().__init__(message)
        self.code = code
        self.measurement = measurement or {}


def _vector(point):
    return (isinstance(point, (list, tuple)) and len(point) == 3
            and all(type(x) in (int, float) and math.isfinite(x) for x in point))


def _dot(a, b):
    return math.fsum(x*y for x, y in zip(a, b))


def _jacobi(matrix, budget):
    """Normalize one symmetric Horn 4x4 system and bound its uncertainty."""
    budget.check()
    n = len(matrix)
    scale = max(abs(value) for row in matrix for value in row)
    if not math.isfinite(scale) or scale == 0:
        raise _Refusal('RIGID_FRAME_AMBIGUOUS', 'Zero or nonfinite normalized covariance')
    a = [[value/scale for value in row] for row in matrix]
    vectors = [[float(i == j) for j in range(n)] for i in range(n)]
    # IEEE roundoff after a fixed-size normalized update, not a distance gate.
    convergence_roundoff = 16*n*n*_EPS
    rotations = 0
    for _ in range(_MAX_ROTATIONS):
        budget.check()
        i, j = max(((i, j) for i in range(n) for j in range(i+1, n)),
                   key=lambda pair: abs(a[pair[0]][pair[1]]))
        if abs(a[i][j]) <= convergence_roundoff:
            break
        tau = (a[j][j]-a[i][i])/(2*a[i][j])
        tangent = math.copysign(1., tau)/(abs(tau)+math.hypot(1., tau))
        cosine = 1/math.hypot(1., tangent); sine = tangent*cosine
        off = a[i][j]
        a[i][i] -= tangent*off; a[j][j] += tangent*off
        a[i][j] = a[j][i] = 0.
        for k in range(n):
            if k not in (i, j):
                ki, kj = a[k][i], a[k][j]
                a[k][i] = a[i][k] = cosine*ki-sine*kj
                a[k][j] = a[j][k] = sine*ki+cosine*kj
            vi, vj = vectors[k][i], vectors[k][j]
            vectors[k][i] = cosine*vi-sine*vj
            vectors[k][j] = sine*vi+cosine*vj
        rotations += 1
    budget.check()
    offdiag = max(abs(a[i][j]) for i in range(n) for j in range(i+1, n))
    # Gershgorin radius plus a conservative accumulated update roundoff bound.
    radius = max(math.fsum(abs(a[i][j]) for j in range(n) if i != j) for i in range(n))
    roundoff = 128*n*n*(rotations+1)*_EPS
    error = (radius+roundoff)*scale
    order = sorted(range(n), key=lambda index: (-a[index][index], index))
    report = {'max_rotations': _MAX_ROTATIONS, 'rotations': rotations,
        'normalized_matrix_scale': scale, 'normalized_off_diagonal_max': offdiag,
        'convergence_roundoff': convergence_roundoff,
        'eigenvalue_uncertainty_bound': error,
        'eigenvalues': [a[index][index]*scale for index in order],
        'converged': offdiag <= convergence_roundoff}
    if not report['converged']:
        raise _Refusal('RIGID_NUMERIC_INCOMPLETE', 'Jacobi rotation budget exhausted', report)
    return [list(vectors[k][index] for k in range(n)) for index in order], report


def transform(fit, point):
    delta = [point[k]-fit['source_centroid_cm'][k] for k in range(3)]
    return [fit['target_centroid_cm'][i]+_dot(row, delta)
            for i, row in enumerate(fit['rotation'])]


def _rank(points, weights, budget):
    """Conservative rank of a normalized positive-semidefinite 3x3 Gram.

    Principal minors certify rank >=2; no additional iterative solve consumes
    a separate rotation budget. Indeterminate roundoff intervals are refused.
    """
    budget.check()
    gram = [[math.fsum(weight*point[i]*point[j] for point, weight in zip(points, weights))
             for j in range(3)] for i in range(3)]
    scale = max(abs(value) for row in gram for value in row)
    roundoff = 32*_EPS*scale
    minors = []
    for i in range(3):
        for j in range(i+1, 3):
            product, square = gram[i][i]*gram[j][j], gram[i][j]*gram[i][j]
            minors.append({'value': product-square,
                'uncertainty': 8*_EPS*(abs(product)+abs(square))+8*scale*roundoff})
    terms = [gram[0][0]*gram[1][1]*gram[2][2], gram[0][1]*gram[1][2]*gram[2][0],
        gram[0][2]*gram[1][0]*gram[2][1], -gram[0][2]*gram[1][1]*gram[2][0],
        -gram[0][1]*gram[1][0]*gram[2][2], -gram[0][0]*gram[1][2]*gram[2][1]]
    determinant = math.fsum(terms)
    determinant_error = 16*_EPS*math.fsum(abs(value) for value in terms)+16*scale*scale*roundoff
    rank = 3 if determinant > determinant_error else 2 if any(
        row['value'] > row['uncertainty'] for row in minors) else 1 if scale else 0
    budget.check()
    return {'rank': rank, 'policy': 'LOWER_BOUND_FROM_IEEE_PRINCIPAL_MINOR_INTERVALS',
        'normalized_gram_scale': scale, 'gram_entry_roundoff_bound': roundoff,
        'principal_two_minors': minors, 'determinant': determinant,
        'determinant_uncertainty': determinant_error}


def _summary(rows, fit=None, check=None):
    maximum_weight = max(row['weight'] for row in rows)
    weights = [row['weight']/maximum_weight for row in rows]
    total = math.fsum(weights)
    gaps = []
    for row in rows:
        if check is not None:
            check()
        gaps.append(math.dist(row['source_point_cm'] if fit is None else transform(fit, row['source_point_cm']),
                              row['target_point_cm']))
    if not all(math.isfinite(gap) for gap in gaps):
        raise _Refusal('RIGID_NONFINITE_ARITHMETIC', 'Unrepresentable residual')
    maximum = max(gaps)
    # Scaling avoids overflowing squares of otherwise finite world gaps.
    rms = (maximum*math.sqrt(math.fsum(weight*(gap/maximum)**2 for weight, gap in zip(weights, gaps))/total)
           if maximum else 0.)
    return {'controls': len(rows), 'max_gap_cm': maximum, 'weighted_rms_gap_cm': rms}


def proper_rigid_fit(rows, budget):
    """Return a proposed seed or explicit refusal; never retry or mutate rows."""
    try:
        if not isinstance(rows, list) or len(rows) < 3 or len(rows) > budget.limits['max_controls']:
            raise _Refusal('INCOMPLETE_CORRESPONDENCES', 'Fit needs bounded complete point correspondences')
        for row in rows:
            budget.check()
            if (not isinstance(row, dict) or not _vector(row.get('source_point_cm'))
                    or not _vector(row.get('target_point_cm'))
                    or type(row.get('weight')) not in (int, float)
                    or not math.isfinite(row['weight']) or row['weight'] <= 0):
                raise _Refusal('RIGID_INVALID_CORRESPONDENCES', 'Nonfinite point or nonpositive weight')
        max_weight = max(row['weight'] for row in rows)
        weights = [row['weight']/max_weight for row in rows]
        total = math.fsum(weights); weights = [weight/total for weight in weights]
        if any(weight == 0 for weight in weights):
            raise _Refusal('RIGID_NUMERIC_INCOMPLETE', 'A positive correspondence weight underflowed')
        p = [math.fsum(weight*row['source_point_cm'][k] for row, weight in zip(rows, weights)) for k in range(3)]
        q = [math.fsum(weight*row['target_point_cm'][k] for row, weight in zip(rows, weights)) for k in range(3)]
        left = []; right = []
        for row in rows:
            budget.check()
            left.append([row['source_point_cm'][k]-p[k] for k in range(3)])
            right.append([row['target_point_cm'][k]-q[k] for k in range(3)])
        ps = max(abs(x) for point in left for x in point)
        qs = max(abs(x) for point in right for x in point)
        if not math.isfinite(ps) or not math.isfinite(qs):
            raise _Refusal('RIGID_NONFINITE_ARITHMETIC', 'Unrepresentable centered coordinates')
        if ps == 0 or qs == 0:
            raise _Refusal('RIGID_FRAME_AMBIGUOUS', 'Coincident source or target points', {'rank': 0})
        left = [[x/ps for x in point] for point in left]
        right = [[x/qs for x in point] for point in right]
        numerical = {'method': 'NORMALIZED_SYMMETRIC_HORN_JACOBI_IEEE_ROUNDOFF',
            'source_spread_cm': ps, 'target_spread_cm': qs, 'product_tolerance_changed': False}
        for label, points in (('source_rank', left), ('target_rank', right)):
            numerical[label] = _rank(points, weights, budget)
            if numerical[label]['rank'] < 2:
                raise _Refusal('RIGID_FRAME_AMBIGUOUS', 'Correspondence rank is below two', numerical)
        h = [[math.fsum(weight*a[i]*b[j] for a, b, weight in zip(left, right, weights))
              for j in range(3)] for i in range(3)]
        xx, xy, xz = h[0]; yx, yy, yz = h[1]; zx, zy, zz = h[2]
        horn = [[xx+yy+zz, yz-zy, zx-xz, xy-yx],
                [yz-zy, xx-yy-zz, xy+yx, zx+xz],
                [zx-xz, xy+yx, -xx+yy-zz, yz+zy],
                [xy-yx, zx+xz, yz+zy, -xx-yy+zz]]
        vectors, observed = _jacobi(horn, budget)
        gap = observed['eigenvalues'][0]-observed['eigenvalues'][1]
        numerical['horn'] = {**observed, 'largest_eigenvalue_gap': gap}
        if gap <= 2*observed['eigenvalue_uncertainty_bound']:
            raise _Refusal('RIGID_FRAME_AMBIGUOUS', 'Overlapping leading eigenvalue intervals', numerical)
        size = math.hypot(*vectors[0]); w, x, y, z = [v/size for v in vectors[0]]
        r = [[1-2*(y*y+z*z), 2*(x*y-z*w), 2*(x*z+y*w)],
             [2*(x*y+z*w), 1-2*(x*x+z*z), 2*(y*z-x*w)],
             [2*(x*z-y*w), 2*(y*z+x*w), 1-2*(x*x+y*y)]]
        determinant = (r[0][0]*(r[1][1]*r[2][2]-r[1][2]*r[2][1])
            - r[0][1]*(r[1][0]*r[2][2]-r[1][2]*r[2][0])
            + r[0][2]*(r[1][0]*r[2][1]-r[1][1]*r[2][0]))
        orthogonal = max(abs(_dot(r[i], r[j])-float(i == j)) for i in range(3) for j in range(3))
        rotation_roundoff = 128*_EPS*(observed['rotations']+1)
        if (not all(_vector(row) for row in r) or abs(determinant-1.) > rotation_roundoff
                or orthogonal > rotation_roundoff):
            raise _Refusal('RIGID_NUMERIC_INCOMPLETE', 'Proper rotation numerical invariant failed', numerical)
        fit = {'status': 'RIGID_SEED_PROPOSED', 'qualification': 'NONE', 'rotation': r,
            'source_centroid_cm': p, 'target_centroid_cm': q, 'rotation_determinant': determinant,
            'rotation_orthogonality_max_residual': orthogonal, 'rotation_roundoff_bound': rotation_roundoff,
            'numerical': numerical, 'before': _summary(rows, check=budget.check)}
        fit['after'] = _summary(rows, fit, check=budget.check)
        budget.check()
        return fit
    except _Refusal as error:
        return {'status': error.code, 'qualification': 'NONE', 'message': str(error), 'numerical': error.measurement}
    except (OverflowError, ZeroDivisionError) as error:
        return {'status': 'RIGID_NONFINITE_ARITHMETIC', 'qualification': 'NONE', 'message': str(error)}


def _complete_rows(pid, relations, states, witnesses, data, subdivisions, budget):
    # Reuse exact source-chain identities after the caller's union insertions.
    # No cage is rebuilt, no point is added and no proximity is searched.
    from .source_seam_coupling import _chain, _near_parameter, _partition_union
    indexed = {}
    for witness in witnesses:
        budget.check()
        indexed.setdefault(witness['source_seam_id'], []).append(witness)
    rows = []
    for seam in relations:
        budget.check()
        found = indexed.get(seam['id'], [])
        if len(found) != 1 or found[0]['source_relation'] != seam:
            raise _Refusal('INCOMPLETE_CORRESPONDENCES', 'Missing, duplicate or mismatched approved source relation')
        witness = found[0]
        chains = [_chain(data['pieces'][seam['piece_'+side]], seam['edge_'+side],
            side == 'b' and seam['orientation'] == 'reverse', states[seam['piece_'+side]],
            seam['piece_'+side], subdivisions) for side in ('a', 'b')]
        budget.check()
        expected = _partition_union(*chains)
        fractions = witness['common_fractions']; pairs = witness['paired_cage_controls']
        if len(fractions) != len(pairs) or len(fractions) != len(expected):
            raise _Refusal('INCOMPLETE_CORRESPONDENCES', 'A required complete source partition is missing')
        source_side = 0 if seam['piece_a'] == pid else 1
        for index, entry in enumerate(expected):
            budget.check()
            fraction = fractions[index]; pair = pairs[index]
            if (type(fraction) not in (int, float) or not math.isfinite(fraction)
                    or not _near_parameter(fraction, entry['fraction'])
                    or not isinstance(pair, (list, tuple)) or len(pair) != 2
                    or any(not isinstance(value, (list, tuple)) or len(value) != 2
                           or type(value[1]) is not int for value in pair)):
                raise _Refusal('INCOMPLETE_CORRESPONDENCES', 'Source partition identity mismatch')
            provenance = {row['side']: row for row in entry['provenance']}
            for side, (partner, control) in enumerate(pair):
                if (side not in provenance or partner != seam['piece_'+('a' if side == 0 else 'b')]
                        or control != provenance[side]['index']):
                    raise _Refusal('INCOMPLETE_CORRESPONDENCES', 'Paired source control identity mismatch')
            a = fractions[index-1] if index else fraction
            b = fractions[index+1] if index+1 < len(fractions) else fraction
            source, target = pair[source_side], pair[1-source_side]
            rows.append({'source_point_cm': states[source[0]]['original'][source[1]],
                'target_point_cm': states[target[0]]['original'][target[1]],
                'weight': (b-a)/2*chains[source_side]['total'], 'source_seam_id': seam['id']})
    return rows


def prepare_role_rigid_seeds(data, semantics, states, witnesses, budget, *, subdivisions):
    """Align front attachments only; diagnose remaining piece scope explicitly."""
    budget.check()
    original = {pid: state['original'] for pid, state in states.items()}
    positions = dict(original)
    receipt = {'version': 1, 'method': 'ROLE_SOURCE_PERMANENT_PROPER_RIGID_SEED',
        'qualification': 'NONE', 'coverage_scope': 'FRONT_ATTACHMENTS_ONLY',
        'whole_piece_admission': False, 'pieces': {}, 'diagnostics': [],
        'kernel_code_sha256': sha(__file__), 'source_sha256': digest(data),
        'semantics_sha256': digest(semantics), 'input_controls_sha256': digest(original),
        'immutable_torso_fit_targets': True, 'source_uv_scaled': False, 'body_changed': False}
    if (not isinstance(semantics, dict) or set(semantics) != set(data['pieces'])
            or any(not isinstance(row, dict) or not isinstance(row.get('role'), str)
                   or not row['role'] for row in semantics.values())):
        receipt['diagnostics'].append({'code': 'RIGID_SEMANTICS_INCOMPLETE',
            'message': 'Explicit roles must cover the complete approved source inventory'})
        receipt['status'] = 'ALIGNMENT_INCOMPLETE'
        return positions, receipt
    candidates = sorted(pid for pid in states if semantics[pid]['role'] == 'inner_front')
    receipt['unselected_role_candidates'] = sorted(pid for pid in semantics
        if semantics[pid]['role'] == 'inner_front' and pid not in states)
    for pid in candidates:
        budget.check()
        attached = [seam for seam in data['seams'] if pid in (seam['piece_a'], seam['piece_b'])]
        permanent = [seam for seam in attached if seam['kind'] == 'permanent']
        applicable = sorted((seam for seam in permanent if semantics[
            seam['piece_b'] if seam['piece_a'] == pid else seam['piece_a']]['role'] == 'front'), key=lambda s: s['id'])
        applicable_ids = {seam['id'] for seam in applicable}
        row = {'role': 'inner_front', 'coverage_scope': 'FRONT_ATTACHMENTS_ONLY',
            'expected_relation_ids': sorted(applicable_ids),
            'remaining_permanent_relation_ids': sorted(seam['id'] for seam in permanent if seam['id'] not in applicable_ids),
            'excluded_nonpermanent_relations': [{'id': seam['id'], 'kind': seam['kind']}
                for seam in sorted(attached, key=lambda s: s['id']) if seam['kind'] != 'permanent'],
            'whole_piece_admission': False, 'applied': False}
        receipt['pieces'][pid] = row
        try:
            if not applicable or any(seam['piece_a'] not in states or seam['piece_b'] not in states for seam in applicable):
                raise _Refusal('INCOMPLETE_CORRESPONDENCES', 'Every approved applicable front partner must be prepared')
            rows = _complete_rows(pid, applicable, states, witnesses, data, subdivisions, budget)
            fit = proper_rigid_fit(rows, budget); row['fit'] = fit
            if fit['status'] != 'RIGID_SEED_PROPOSED':
                raise _Refusal(fit['status'], fit.get('message', 'No determinate rigid seed'), fit.get('numerical'))
            moved = []
            for point in original[pid]:
                budget.check()
                value = transform(fit, point)
                if not _vector(value):
                    raise _Refusal('RIGID_NONFINITE_ARITHMETIC', 'Transported original guide is not finite')
                moved.append(value)
            per_relation = {}
            for seam in applicable:
                budget.check()
                selected = [value for value in rows if value['source_seam_id'] == seam['id']]
                per_relation[seam['id']] = {'before': _summary(selected, check=budget.check),
                    'after': _summary(selected, fit, check=budget.check)}
            row.update(status='PARTIAL_RIGID_SEED_APPLIED' if row['remaining_permanent_relation_ids'] else 'RIGID_SEED_APPLIED',
                applied=True, relation_residuals=per_relation,
                max_rigid_seed_displacement_cm=max(math.dist(a, b) for a, b in zip(original[pid], moved)))
            positions[pid] = moved
        except _Refusal as error:
            row.update(status=error.code, message=str(error))
            receipt['diagnostics'].append({'piece': pid, 'code': error.code, 'message': str(error)})
    for pid in sorted(states):
        budget.check()
        if semantics[pid]['role'] == 'collar':
            receipt['diagnostics'].append({'piece': pid, 'code': 'COLLAR_ALIGNMENT_NOT_IMPLEMENTED',
                'message': 'Global rigid collation is insufficient; derived neckline guides need separate measured correction',
                'source_permanent_relation_ids': sorted(seam['id'] for seam in data['seams']
                    if seam['kind'] == 'permanent' and pid in (seam['piece_a'], seam['piece_b']))})
    receipt['status'] = ('ALIGNMENT_INCOMPLETE' if receipt['diagnostics'] else
        'PARTIAL_ROLE_SEEDS_PREPARED' if any(row['remaining_permanent_relation_ids'] for row in receipt['pieces'].values())
        else 'ROLE_SEEDS_PREPARED')
    receipt['output_controls_sha256'] = digest(positions)
    budget.check()
    return positions, receipt
