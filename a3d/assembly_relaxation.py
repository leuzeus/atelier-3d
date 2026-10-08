"""Portable, bounded assembly proposals against immutable material rest data.

This is a geometric initializer, not a cloth engine. Explicit source seam pairs
are soft constraints, so they cannot close by silently resetting rest lengths.
Every selected triangle contributes material constraints, irrespective of body
role. Contacts, self intersections and final mesh admission remain downstream.
"""
from __future__ import annotations

import copy
import math

from .cloth_metrics import principal_stretches
from .core import StudioError, digest, sha


DEFAULTS = {
    'max_iterations': 120, 'rigid_iterations': 12,
    'max_displacement_cm': 20., 'metric_weight': 100., 'seam_weight': 1.,
    'position_weight': .001, 'seam_tolerance_cm': .05,
    'strain_tolerance': .02, 'stagnation_iterations': 8,
    'improvement_tolerance': 1e-9, 'ease_distribution': 'ZERO_EASE_ONLY',
}
_INTEGER_LIMITS = {'max_iterations': (1, 1000), 'rigid_iterations': (0, 100),
                   'stagnation_iterations': (1, 100)}
_FLOAT_LIMITS = {'max_displacement_cm': 100., 'metric_weight': 10000.,
                 'seam_weight': 1000., 'position_weight': 100.,
                 'seam_tolerance_cm': 5., 'strain_tolerance': .5,
                 'improvement_tolerance': .01}


def validate_options(options=None):
    if options is None:
        options = {}
    if not isinstance(options, dict) or set(options)-(set(DEFAULTS) | {'constraint_projection'}):
        raise StudioError('Unknown coupled rest metric relaxation option')
    if 'constraint_projection' in options and options['constraint_projection'] != 'ACTIVE_PRINCIPAL_CONE_V1':
        raise StudioError('Unsupported explicit coupled constraint projection')
    result = {**DEFAULTS, **options}
    for key, (low, high) in _INTEGER_LIMITS.items():
        if type(result[key]) is not int or not low <= result[key] <= high:
            raise StudioError('Coupled relaxation requires bounded integer option: '+key)
    for key, maximum in _FLOAT_LIMITS.items():
        value = result[key]
        if (type(value) not in (int, float) or not math.isfinite(value)
                or value > maximum or value < 0 or (value == 0 and key != 'position_weight')):
            raise StudioError('Coupled relaxation requires bounded finite option: '+key)
    if result['ease_distribution'] not in ('ZERO_EASE_ONLY', 'UNIFORM_NORMALIZED_SOURCE_ARC'):
        raise StudioError('Coupled relaxation requires an explicit supported ease distribution')
    return result


def _distance_step_limit(points, directions, original, maximum):
    """One common step preserves rigid translations and rotational equivariance."""
    result = 1.
    for point, direction, anchor in zip(points, directions, original, strict=True):
        delta = [x-y for x, y in zip(point, anchor)]
        a = math.fsum(x*x for x in direction)
        if a == 0:
            continue
        b = math.fsum(x*y for x, y in zip(delta, direction))
        c = math.fsum(x*x for x in delta)-maximum*maximum
        # The current candidate is in the closed trust region. Avoid any
        # coordinate-axis projection or per-panel scaling of material.
        root = max(0., (-b+math.sqrt(max(0., b*b-a*c)))/a)
        result = min(result, root)
    return result


def relax_assembly(states, initial, witnesses, budget, *, options=None, fixed_controls=None):
    """Return a measured best proposal; neither a seam nor a metric PASS.

    The source coupling caller validates source topology and correspondences.
    Stage one translates whole panels. Stage two minimizes a triangle-area
    weighted rest-edge energy and progressive seam energy with bounded,
    diagonally preconditioned descent and backtracking. No weld is performed.
    """
    settings = validate_options(options)
    projection_enabled = settings.get('constraint_projection') == 'ACTIVE_PRINCIPAL_CONE_V1'
    if projection_enabled:
        from .active_metric_constraints import (project_active_principal_direction, ConstraintProjectionRefused,
                                                MODE, MAX_SWEEPS, RESIDUAL_TOLERANCE)
        from . import active_metric_constraints
        projection_records = []; search_records = []
        observed_constraints = set(); observed_violation_count = 0
        search_phase = 'RIGID'; search_iteration = 0
    before = digest([initial, witnesses, {pid: {
        'uv': state['uv'], 'triangles': state['triangles']} for pid, state in states.items()}])
    keys = [(pid, i) for pid in sorted(states) for i in range(len(states[pid]['uv']))]
    lookup = {key: i for i, key in enumerate(keys)}
    if fixed_controls is None:
        fixed_controls = {}
    if (not isinstance(fixed_controls, dict) or not set(fixed_controls) <= set(states)
            or any(not isinstance(indices, list)
                or any(type(i) is not int or (pid, i) not in lookup for i in indices)
                or len(set(indices)) != len(indices)
                for pid, indices in fixed_controls.items())):
        raise StudioError('Coupled anatomical fixed controls require exact selected source cage identities')
    fixed = {lookup[pid, i] for pid, indices in fixed_controls.items() for i in indices}
    fixed_pieces = {pid for pid, indices in fixed_controls.items() if indices}
    original = [list(initial[pid][i]) for pid, i in keys]
    points = copy.deepcopy(original)
    edges = {}; areas = []; faces = []
    for pid, state in sorted(states.items()):
        for face in state['triangles']:
            budget.check()
            uv = [state['uv'][i] for i in face]
            a, b, c = uv
            area = abs((b[0]-a[0])*(c[1]-a[1])-(b[1]-a[1])*(c[0]-a[0]))/2
            if not math.isfinite(area) or area <= 0:
                raise StudioError('Coupled rest metric requires noncollapsed original UV triangles')
            areas.append(area)
            faces.append((uv, [lookup[pid, i] for i in face], pid))
            for a, b in zip(face, face[1:]+face[:1]):
                key = tuple(sorted((lookup[pid, a], lookup[pid, b])))
                length = math.dist(state['uv'][a], state['uv'][b])
                if not math.isfinite(length) or length <= 0:
                    raise StudioError('Coupled rest metric requires finite nonzero material edges')
                record = edges.setdefault(key, [length, 0.])
                if record[0] != length:
                    raise StudioError('Coupled rest metric has contradictory source edge lengths')
                record[1] += area/3
    total_area = math.fsum(areas)
    scale2 = total_area/len(states)
    material = [(a, b, length, area/(length*length*total_area))
                for (a, b), (length, area) in sorted(edges.items())]
    material_faces = []
    for (uv, indices, _), area in zip(faces, areas, strict=True):
        x1, y1 = [uv[1][k]-uv[0][k] for k in range(2)]
        x2, y2 = [uv[2][k]-uv[0][k] for k in range(2)]
        det = x1*y2-x2*y1
        gradients = [((y1-y2)/det, (x2-x1)/det), (y2/det, -x2/det), (-y1/det, x1/det)]
        material_faces.append((indices, gradients, area/total_area))
    pairs = []
    for row in witnesses:
        fractions = row['common_fractions']
        length = math.fsum(row['source_chain_lengths_cm'])/2
        for i, pair in enumerate(row['paired_cage_controls']):
            budget.check()
            left = fractions[i-1] if i else fractions[i]
            right = fractions[i+1] if i+1 < len(fractions) else fractions[i]
            weight = (right-left)*length/2
            a, b = [lookup[tuple(key)] for key in pair]
            if a != b:
                pairs.append((a, b, weight))
    seam_length = math.fsum(weight for _, _, weight in pairs)
    if not pairs or seam_length <= 0:
        raise StudioError('Coupled rest metric requires nontrivial declared sewing pairs')
    pairs = [(a, b, weight/(seam_length*scale2)) for a, b, weight in pairs]
    attachment_weight = settings['position_weight']/(len(points)*scale2)
    metric_envelopes = {pid: [1-settings['strain_tolerance'], 1+settings['strain_tolerance']]
                        for pid in states}
    for uv, indices, pid in faces:
        budget.check()
        stretches = principal_stretches(uv, [original[i] for i in indices])
        if stretches is None or any(not math.isfinite(value) for value in stretches):
            raise StudioError('Coupled rest metric requires measurable initial source principal stretches')
        metric_envelopes[pid][0] = min(metric_envelopes[pid][0], stretches[0])
        metric_envelopes[pid][1] = max(metric_envelopes[pid][1], stretches[1])

    def within_metric_envelopes(candidate, failure=None):
        # A mean energy alone can hide a badly sheared thin triangle. Keep
        # each piece within its original worst extrema or the declared target
        # tolerance. This does not replace final all-triangle mesh admission.
        for ordinal, (uv, indices, pid) in enumerate(faces):
            if ordinal % 128 == 0:
                budget.check()
            stretches = principal_stretches(uv, [candidate[i] for i in indices])
            low, high = metric_envelopes[pid]
            roundoff = 1e-10*max(1., high)
            if (stretches is None or any(not math.isfinite(value) for value in stretches)
                    or stretches[0] < low-roundoff or stretches[1] > high+roundoff):
                if failure is not None:
                    measurable = stretches is not None and all(math.isfinite(value) for value in stretches)
                    violated_sides = ([] if not measurable else
                        (['LOWER'] if stretches[0] < low-roundoff else [])
                        + (['UPPER'] if stretches[1] > high+roundoff else []))
                    failure.update(reason='CURRENT_NONLINEAR_METRIC_ENVELOPE', face_ordinal=ordinal,
                        piece=pid, principal_stretches=stretches if measurable else None,
                        bounds=[low, high], arithmetic_roundoff=roundoff, violated_sides=violated_sides)
                return False
        return True

    def targets_reached(candidate, measured):
        if (measured['max_seam_gap_cm'] > settings['seam_tolerance_cm']
                or measured['max_edge_strain'] > settings['strain_tolerance']):
            return False
        for ordinal, (uv, indices, _) in enumerate(faces):
            if ordinal % 128 == 0:
                budget.check()
            stretches = principal_stretches(uv, [candidate[i] for i in indices])
            if (stretches is None or any(not math.isfinite(value) for value in stretches)
                    or stretches[0] < 1-settings['strain_tolerance']
                    or stretches[1] > 1+settings['strain_tolerance']):
                return False
        return True

    def evaluate(candidate, seam_fraction=1., gradient=False):
        material_energy = seam_energy = position_energy = 0.
        edge_strain = max_gap = 0.
        grad = [[0., 0., 0.] for _ in candidate] if gradient else None
        diagonal = [0. for _ in candidate] if gradient else None

        def spring(a, b, rest, weight):
            nonlocal material_energy, seam_energy, edge_strain, max_gap
            delta = [candidate[a][k]-candidate[b][k] for k in range(3)]
            length = math.hypot(*delta)
            residual = length-rest
            if rest:
                material_energy += weight*residual*residual
                edge_strain = max(edge_strain, abs(residual/rest))
            else:
                seam_energy += weight*residual*residual
                max_gap = max(max_gap, length)
            if gradient:
                # At an exactly collapsed edge the objective is nondifferentiable.
                # Reuse its existing direction only; never invent a world axis.
                direction = delta
                divisor = length
                if length == 0 and rest:
                    direction = [original[a][k]-original[b][k] for k in range(3)]
                    divisor = math.hypot(*direction)
                factor = 2*weight*residual/divisor if divisor else 0.
                for k in range(3):
                    value = factor*direction[k]
                    grad[a][k] += value; grad[b][k] -= value
                diagonal[a] += 2*weight; diagonal[b] += 2*weight

        for ordinal, (a, b, rest, weight) in enumerate(material):
            if ordinal % 128 == 0:
                budget.check()
            # Small edge term gives collapsed edges a source-derived escape
            # direction; the principal triangle metric drives the solve.
            spring(a, b, rest, settings['metric_weight']*.001*weight)
        for ordinal, (indices, gradients, area_weight) in enumerate(material_faces):
            if ordinal % 128 == 0:
                budget.check()
            base = candidate[indices[0]]
            fu = [math.fsum((candidate[i][k]-base[k])*g[0]
                           for i, g in zip(indices, gradients, strict=True)) for k in range(3)]
            fv = [math.fsum((candidate[i][k]-base[k])*g[1]
                           for i, g in zip(indices, gradients, strict=True)) for k in range(3)]
            a = math.fsum(x*x for x in fu); b = math.fsum(x*y for x, y in zip(fu, fv))
            d = math.fsum(x*x for x in fv)
            weight = settings['metric_weight']*area_weight
            material_energy += weight*((a-1)**2+2*b*b+(d-1)**2)/4
            if gradient:
                du = [weight*((a-1)*x+b*y) for x, y in zip(fu, fv)]
                dv = [weight*(b*x+(d-1)*y) for x, y in zip(fu, fv)]
                for i, (u, v) in zip(indices, gradients, strict=True):
                    for k in range(3):
                        grad[i][k] += u*du[k]+v*dv[k]
                    diagonal[i] += weight*(1+3*(a+d))*(u*u+v*v)
        for a, b, weight in pairs:
            spring(a, b, 0., settings['seam_weight']*seam_fraction*weight)
        for i, (point, anchor) in enumerate(zip(candidate, original, strict=True)):
            delta = [x-y for x, y in zip(point, anchor)]
            position_energy += attachment_weight*math.fsum(x*x for x in delta)
            if gradient:
                for k in range(3):
                    grad[i][k] += 2*attachment_weight*delta[k]
                diagonal[i] += 2*attachment_weight
        energy = material_energy+seam_energy+position_energy
        if not math.isfinite(energy):
            raise StudioError('Coupled rest metric objective is not finite')
        return {'objective': energy, 'material_energy': material_energy,
            'seam_energy': seam_energy, 'position_energy': position_energy,
            'max_edge_strain': edge_strain, 'max_seam_gap_cm': max_gap}, grad, diagonal

    def search(directions, fraction):
        nonlocal observed_violation_count
        current, _, _ = evaluate(points, fraction)
        step = _distance_step_limit(points, directions, original, settings['max_displacement_cm'])
        if projection_enabled:
            observation = {'phase': search_phase, 'iteration': search_iteration, 'trials': []}
        for _ in range(14):
            budget.check()
            candidate = [[point[k]+step*direction[k] for k in range(3)]
                         for point, direction in zip(points, directions, strict=True)]
            measured, _, _ = evaluate(candidate, fraction)
            if projection_enabled:
                failure = {}; descending = measured['objective'] < current['objective']
                admissible = within_metric_envelopes(candidate, failure) if descending else False
                if failure:
                    # Only an actual finite nonlinear metric violation yields
                    # a side identity. No gradient or rejected point survives.
                    added = 0
                    for side in failure['violated_sides']:
                        identity = (failure['face_ordinal'], side)
                        observed_violation_count += 1
                        added += int(identity not in observed_constraints)
                        observed_constraints.add(identity)
                    failure['new_retained_constraints'] = added
                observation['trials'].append({'step': step, 'objective': measured['objective'],
                    'descending': descending, 'nonlinear_metric_check': ('PASS' if admissible else 'FAIL')
                        if descending else 'NOT_EXECUTED_NO_DESCENT', **({'failure': failure} if failure else {})})
                if descending and admissible:
                    observation['result'] = 'STEP_ACCEPTED'; search_records.append(observation)
                    return candidate, measured
            elif measured['objective'] < current['objective'] and within_metric_envelopes(candidate):
                return candidate, measured
            step *= .5
        if projection_enabled:
            observation['result'] = 'NO_ACCEPTABLE_STEP'; search_records.append(observation)
        return points, current

    initial_metrics, _, _ = evaluate(points)
    best = copy.deepcopy(points); best_metrics = initial_metrics; best_phase = 'ORIGINAL'
    phases = []; completed = 0; rigid_completed = 0

    def keep(phase):
        nonlocal best, best_metrics, best_phase
        measured, _, _ = evaluate(points)
        if measured['objective'] < best_metrics['objective']:
            best = copy.deepcopy(points); best_metrics = measured; best_phase = phase
        return measured

    # Equal rigid translations are applied to every vertex in each piece.
    # Unary seams have no rigid translation degree of freedom and wait for
    # material relaxation; their source boundary identities remain separate.
    for iteration in range(settings['rigid_iterations']):
        budget.check()
        if projection_enabled: search_iteration = iteration
        offsets = {pid: [0., 0., 0.] for pid in states}
        weights = {pid: 0. for pid in states}
        for a, b, weight in pairs:
            pa, pb = keys[a][0], keys[b][0]
            if pa == pb:
                continue
            for k in range(3):
                delta = (points[b][k]-points[a][k])*.5*weight
                offsets[pa][k] += delta; offsets[pb][k] -= delta
            weights[pa] += weight; weights[pb] += weight
        directions = [[value/weights[pid] if weights[pid] and pid not in fixed_pieces else 0.
                       for value in offsets[pid]]
                      for pid, _ in keys]
        proposal, _ = search(directions, 1.)
        rigid_completed += 1
        if proposal is points:
            break
        points = proposal
        keep('WHOLE_PIECE_RIGID_TRANSLATION')
    phases.append({'phase': 'WHOLE_PIECE_RIGID_TRANSLATION', 'iterations': rigid_completed,
                   'metrics': evaluate(points)[0], 'source_lengths_changed': False})
    satisfied = targets_reached(best, best_metrics)
    termination = 'PRINCIPAL_METRIC_AND_SEAM_TARGETS_REACHED' if satisfied else 'ITERATION_BUDGET_EXHAUSTED'
    stagnant = 0
    for iteration in range(0 if satisfied else settings['max_iterations']):
        budget.check()
        # Increase stitch strength during the first quarter of the declared
        # budget, keeping material strength unchanged throughout.
        ramp = min(1., (iteration+1)/max(1., settings['max_iterations']/4))
        current, grad, diagonal = evaluate(points, ramp, True)
        directions = [[-value/diagonal[i] if diagonal[i] and i not in fixed else 0. for value in row]
                      for i, row in enumerate(grad)]
        if projection_enabled:
            search_phase = 'MATERIAL'; search_iteration = iteration
            try:
                directions, observed = project_active_principal_direction(
                    points, directions, diagonal, faces, metric_envelopes, fixed, budget.check,
                    observed_constraints=observed_constraints)
            except ConstraintProjectionRefused as error:
                projection_records.append({'iteration': iteration, 'status': 'REFUSED', **error.diagnostic})
                termination = 'CONSTRAINT_PROJECTION_REFUSED'
                break
            # A linear cone projection is only a direction proposal. Its
            # descent and the nonlinear envelopes remain independent gates.
            try:
                derivative = math.fsum(g*d for gradient, direction in zip(grad, directions, strict=True)
                                       for g, d in zip(gradient, direction, strict=True))
            except (OverflowError, ValueError):
                derivative = None
            if derivative is None or not math.isfinite(derivative) or derivative >= 0:
                projection_records.append({'iteration': iteration, 'status': 'NO_DESCENT', **observed,
                    'gradient_dot_direction': derivative if derivative is not None and math.isfinite(derivative) else None})
                termination = 'CONSTRAINT_PROJECTION_NO_DESCENT'
                break
            projection_records.append({'iteration': iteration, 'status': 'PROJECTED', **observed,
                'gradient_dot_direction': derivative})
        proposal, measured = search(directions, ramp)
        completed += 1
        improvement = current['objective']-measured['objective']
        points = proposal
        actual = keep('COUPLED_MATERIAL_AND_STITCH_RELAXATION')
        if ramp == 1.:
            stagnant = stagnant+1 if improvement <= settings['improvement_tolerance'] else 0
            if targets_reached(points, actual):
                termination = 'PRINCIPAL_METRIC_AND_SEAM_TARGETS_REACHED'
                break
            if stagnant >= settings['stagnation_iterations']:
                termination = 'STAGNATION'
                break
    minimum = math.inf; maximum = 0.; unmeasurable = 0
    for uv, indices, _ in faces:
        budget.check()
        stretches = principal_stretches(uv, [best[i] for i in indices])
        if stretches is None or any(not math.isfinite(x) for x in stretches):
            unmeasurable += 1
        else:
            minimum = min(minimum, stretches[0]); maximum = max(maximum, stretches[1])
    measured_targets = (best_metrics['max_seam_gap_cm'] <= settings['seam_tolerance_cm']
        and not unmeasurable and minimum >= 1-settings['strain_tolerance']
        and maximum <= 1+settings['strain_tolerance'])
    final = {pid: [best[lookup[pid, i]] for i in range(len(state['uv']))]
             for pid, state in states.items()}
    if any(best[i] != original[i] for i in fixed):
        raise StudioError('Coupled rest metric moved an immutable anatomical support control')
    unchanged = digest([initial, witnesses, {pid: {
        'uv': state['uv'], 'triangles': state['triangles']} for pid, state in states.items()}])
    if before != unchanged:
        raise StudioError('Coupled rest metric mutated source material or input proposals')
    report = {'method': 'BOUNDED_PROGRESSIVE_REST_METRIC_AND_SOURCE_STITCHES', 'version': 2,
        'status': 'PROPOSAL_TARGETS_REACHED' if measured_targets else 'PROPOSAL_INCOMPLETE',
        'termination': termination, 'qualification': 'NONE', 'settings': settings,
        'kernel_code_sha256': sha(__file__), 'source_binding_sha256': before,
        'initial': initial_metrics, 'best': best_metrics, 'best_phase': best_phase,
        'iterations': completed, 'rigid_iterations': rigid_completed, 'phases': phases,
        'min_principal_stretch': None if minimum == math.inf else minimum,
        'max_principal_stretch': maximum, 'unmeasurable_triangles': unmeasurable,
        'max_displacement_cm': max(math.dist(a, b) for a, b in zip(best, original, strict=True)),
        'material_edge_count': len(material), 'source_pair_count': len(pairs),
        'material_trust_policy': 'PER_PIECE_PRINCIPAL_EXTREMA_NOT_WORSE_THAN_INPUT_OR_DECLARED_TARGET',
        'initial_material_trust_envelopes': metric_envelopes,
        'fixed_anatomical_controls': copy.deepcopy(fixed_controls),
        'anatomical_support_policy': 'EXACT_FIXED_SOURCE_CAGE_CONTROLS_NOT_PHYSICAL_CLOTH_PINS',
        'fixed_anatomical_control_count': len(fixed),
        'rest_policy': 'IMMUTABLE_SOURCE_UV_TRIANGLE_METRIC_AND_EDGE_LENGTHS',
        'material_objective': 'AREA_WEIGHTED_SOURCE_DEFORMATION_GRAM_RESIDUAL_WITH_SMALL_EDGE_REGULARIZER',
        'stitch_policy': 'SOFT_SOURCE_PAIRS_NO_WELD_NO_REST_RESET',
        'rotation_policy': 'INPUT_GUIDE_ORIENTATION_RETAINED_DURING_RIGID_TRANSLATION',
        'source_uv_scaled': False, 'contacts': 'NOT_ASSESSED', 'simulation': 'NOT_EXECUTED',
        'fitting': 'NOT_EXECUTED', 'whole_piece_admission': False}
    if projection_enabled:
        report['constraint_projection'] = {'mode': MODE,
            'kernel_code_sha256': sha(active_metric_constraints.__file__), 'max_sweeps': MAX_SWEEPS,
            'residual_tolerance': RESIDUAL_TOLERANCE, 'iterations': projection_records,
            'observed_constraint_policy': active_metric_constraints.OBSERVED_CONSTRAINT_POLICY,
            'observed_violation_count': observed_violation_count,
            'retained_observed_constraint_count': len(observed_constraints),
            'duplicate_observed_violation_count': observed_violation_count-len(observed_constraints),
            'retained_constraint_identities_sha256': digest(sorted(observed_constraints)),
            'retention_scope': 'CURRENT_SOLVE_ONLY_CONSERVATIVE_SIDE_IDENTITIES_CURRENT_GRADIENTS',
            'nonlinear_metric_admission': 'UNCHANGED', 'qualification': 'NONE'}
        report['line_search_diagnostics'] = search_records
    budget.check()
    return final, report
