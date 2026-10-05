"""Pure geometry for the resumable PATTERN_SEWN assembly path, in centimetres.

The source boundary map is the authority for seam IDs and shared arc samples.
An assembly result is never a Cloth, fitting, behaviour, or artistic approval.
"""
import copy
import math
from bisect import bisect_right

from .core import StudioError, contract, digest
from .sewing import permanent_support_groups, weld_permanent
from .cloth_metrics import validate_metrics, validate_linear_motion, face_sources, legacy_metric_evidence


def _refuse(message, category='geometry_safety'):
    error = StudioError(message)
    error.reason_category = category
    raise error


def map_digest(payload):
    """Bind a plan to the current versioned derivation, not historic indices."""
    fields = {k: payload.get(k) for k in (
        'version', 'component_id', 'source_garment_sha256', 'rest_cm',
        'faces', 'panels', 'seams')}
    for key in ('trial_mode', 'single_panel_source'):
        if key in payload:
            fields[key] = payload[key]
    return digest(fields)


def _single_panel_noop(payload):
    """Accept only the explicit complete one-panel source, never a trial subset."""
    if payload.get('trial_mode') != 'single_panel':
        return False
    source = payload.get('single_panel_source')
    panels = sorted(payload['panels'])
    kinds = {sid: seam.get('kind') for sid, seam in payload['seams'].items()}
    if (not isinstance(source, dict) or len(panels) != 1
            or source.get('component_id') != payload['component_id']
            or not payload.get('source_garment_sha256')
            or source.get('source_garment_sha256') != payload['source_garment_sha256']
            or source.get('piece_ids') != panels or source.get('trial_pieces') != panels
            or source.get('seam_kinds') != kinds
            or any(kind not in ('closure', 'detachable') for kind in kinds.values())):
        _refuse('Single-panel no-op requires complete and consistent source provenance')
    return True


def _vec(a, b):
    return [a[k] - b[k] for k in range(3)]


def _dot(a, b):
    return sum(x * y for x, y in zip(a, b))


def _normal(points):
    a, b = _vec(points[1], points[0]), _vec(points[2], points[0])
    return [a[1]*b[2]-a[2]*b[1], a[2]*b[0]-a[0]*b[2], a[0]*b[1]-a[1]*b[0]]


def _coordinates(payload, coords):
    if len(coords) != len(payload['rest_cm']) or any(
            len(p) != 3 or any(not math.isfinite(v) for v in p) for p in coords):
        _refuse('Nonfinite or mismatched assembly coordinates')


def _pairs(payload):
    return [tuple(p) for seam in payload['seams'].values()
            if seam['kind'] == 'permanent' for p in seam['pairs']]


def _gap(coords, pairs):
    return max((math.dist(coords[a], coords[b]) for a, b in pairs), default=0.)


def _edges(faces):
    result = {}
    for face in faces:
        for a, b in zip(face, face[1:] + face[:1]):
            result.setdefault(tuple(sorted((a, b))), []).append((a, b))
    return result


def _topology(payload):
    """Use oriented triangle boundaries, never the absolute 3D tangent angle."""
    edges = _edges(payload['faces'])
    size = len(payload['rest_cm'])
    for sid, seam in payload['seams'].items():
        if seam.get('kind') not in ('permanent', 'closure', 'detachable'):
            _refuse('Unknown seam kind: ' + sid)
        ts, pairs = seam.get('parameters', []), seam['pairs']
        if len(ts) != len(pairs) or len(ts) < 2 or any(
                not math.isfinite(t) or not 0 <= t <= 1 for t in ts) or any(
                b <= a for a, b in zip(ts, ts[1:])):
            _refuse('Missing or invalid common source arc parameters: ' + sid)
        if abs(ts[0]) > 1e-8 or abs(ts[-1]-1) > 1e-8:
            _refuse('Seam must retain the complete common source arc domain: ' + sid)
        for pair in pairs:
            if len(pair) != 2 or any(type(i) is not int or not 0 <= i < size for i in pair):
                _refuse('Invalid current-map seam pair: ' + sid)
            for side, i in zip(('a', 'b'), pair):
                if i not in payload['panels'][seam['piece_'+side]]['indices']:
                    _refuse('Seam partner does not belong to its source panel: ' + sid)
        if seam['kind'] != 'permanent':
            continue
        for (a, b), (c, d) in zip(pairs, pairs[1:]):
            left, right = edges.get(tuple(sorted((a, c))), []), edges.get(tuple(sorted((b, d))), [])
            if len(left) != 1 or len(right) != 1:
                _refuse('Permanent seam does not follow two current boundary runs: ' + sid)
            if (left[0] == (a, c)) == (right[0] == (b, d)):
                _refuse('Contradictory topological seam orientation: ' + sid)


def _compile_arc_sections(frame, pid):
    """Compile actual polyline arc lengths once, outside derived-vertex loops."""
    compiled = []
    for index, section in enumerate(frame['arc_sections']):
        if index and section['v_cm'] <= frame['arc_sections'][index-1]['v_cm']:
            _refuse('Preform arc section v coordinates must be strictly increasing: ' + pid, 'placement')
        cumulative = [0.]
        for a, b in zip(section['curve_cm'], section['curve_cm'][1:]):
            length = math.dist(a, b)
            if not math.isfinite(length) or length <= 1e-12:
                _refuse('Preform arc section contains a collapsed or nonfinite segment: ' + pid, 'placement')
            cumulative.append(cumulative[-1]+length)
        if not math.isfinite(cumulative[-1]):
            _refuse('Preform arc section length is not finite: ' + pid, 'placement')
        compiled.append({'v_cm': section['v_cm'], 'arc_offset_cm': section['arc_offset_cm'],
                         'cumulative_length_cm': cumulative, 'total_length_cm': cumulative[-1]})
    return compiled


def _arc_point(curve, cumulative, s, pid):
    """Strict source arc evaluation. No clamping, wrapping or extrapolation."""
    if not math.isfinite(s) or not 0 <= s <= cumulative[-1]:
        _refuse('Source UV arc coordinate is outside its declared preform section: ' + pid, 'placement')
    segment = min(len(curve)-2, bisect_right(cumulative, s)-1)
    alpha = (s-cumulative[segment])/(cumulative[segment+1]-cumulative[segment])
    point = [curve[segment][k]+alpha*(curve[segment+1][k]-curve[segment][k]) for k in range(3)]
    return point, {'segment': segment, 'segment_vertices': [segment, segment+1],
                   'segment_weights': [1-alpha, alpha], 'arc_coordinate_cm': s}


def _section_point(frame, compiled, uv, pid):
    v = uv[1]
    positions = [section['v_cm'] for section in compiled]
    if not math.isfinite(v) or not positions[0] <= v <= positions[-1]:
        _refuse('Source UV v coordinate is outside its declared preform sections: ' + pid, 'placement')
    lower = min(len(compiled)-2, bisect_right(positions, v)-1)
    upper = lower+1
    blend = (v-positions[lower])/(positions[upper]-positions[lower])
    points, bindings = [], []
    for index in (lower, upper):
        s = compiled[index]['arc_offset_cm']+frame.get('u_direction', 1)*uv[0]
        point, binding = _arc_point(frame['arc_sections'][index]['curve_cm'],
                                    compiled[index]['cumulative_length_cm'], s, pid)
        points.append(point)
        bindings.append({'section': index, **binding})
    return ([points[0][k]*(1-blend)+points[1][k]*blend for k in range(3)],
            {'arc_section_indices': [lower, upper], 'arc_section_weights': [1-blend, blend],
             'arc_samples': bindings, 'u_direction': frame.get('u_direction', 1)})


def _compile_cage(frame, pid, check_time=None):
    """Validate the existing explicit cage once for placement and measurement."""
    uv = frame.get('uv_cm'); target = frame.get('target_cm'); triangles = frame.get('triangles')
    if (not isinstance(uv, list) or not isinstance(target, list) or len(uv) != len(target)
            or len(uv) < 3 or not isinstance(triangles, list) or not triangles):
        _refuse('Preform cage UV and target counts differ or are missing: ' + pid, 'placement')
    for points, size in ((uv, 2), (target, 3)):
        if any(not isinstance(p, (list, tuple)) or len(p) != size
               or any(type(v) not in (int, float) or not math.isfinite(v) for v in p) for p in points):
            _refuse('Preform cage requires finite source UV and world targets: ' + pid, 'placement')
    compiled = []; faces = set()
    for triangle_id, triangle in enumerate(triangles):
        if check_time is not None:
            check_time()
        if (not isinstance(triangle, (list, tuple)) or len(triangle) != 3
                or any(type(i) is not int or not 0 <= i < len(uv) for i in triangle)
                or len(set(triangle)) != 3):
            _refuse('Invalid preform cage triangle: ' + pid, 'placement')
        key = tuple(sorted(triangle))
        if key in faces:
            _refuse('Duplicate preform cage triangle: ' + pid, 'placement')
        faces.add(key)
        a, b, c = [uv[i] for i in triangle]
        denominator = (b[0]-a[0])*(c[1]-a[1])-(b[1]-a[1])*(c[0]-a[0])
        if abs(denominator) < 1e-10:
            _refuse('Collapsed source-UV preform cage triangle: ' + pid, 'placement')
        compiled.append((triangle_id, triangle, a, b, c, denominator))
    return compiled


def _cage_point(frame, compiled, uv, pid, check_time=None):
    """The same barycentric correspondence is used in both consumers."""
    if len(uv) != 2 or any(type(v) not in (int, float) or not math.isfinite(v) for v in uv):
        _refuse('Cage evaluation needs finite source material UV: ' + pid, 'placement')
    candidates = []
    for triangle_id, triangle, a, b, c, denominator in compiled:
        if check_time is not None:
            check_time()
        beta = ((uv[0]-a[0])*(c[1]-a[1])-(uv[1]-a[1])*(c[0]-a[0]))/denominator
        gamma = ((b[0]-a[0])*(uv[1]-a[1])-(b[1]-a[1])*(uv[0]-a[0]))/denominator
        bary = [1-beta-gamma, beta, gamma]
        if min(bary) >= -1e-8 and max(bary) <= 1+1e-8:
            target = [math.fsum(w*frame['target_cm'][j][k] for w, j in zip(bary, triangle)) for k in range(3)]
            candidates.append((triangle_id, bary, target))
    if not candidates:
        _refuse('Derived source UV is outside its explicit preform cage: ' + pid, 'placement')
    if any(math.dist(candidates[0][2], c[2]) > 1e-6 for c in candidates[1:]):
        _refuse('Ambiguous overlapping preform cage correspondence: ' + pid, 'placement')
    triangle_id, bary, target = candidates[0]
    return target, {'cage_triangle': triangle_id, 'barycentric_weights': bary}


def validate_plan(payload, plan):
    contract('pattern-assembly', plan)
    if payload.get('rest_mode') == 'assembled_3d':
        _refuse('A preform plan requires its original derived source map')
    if plan['component_id'] != payload['component_id']:
        _refuse('Assembly plan component mismatch')
    if plan['mapping_sha256'] != map_digest(payload):
        _refuse('Assembly plan source mapping changed; remap from source IDs and arc parameters')
    if set(plan['preform']['panels']) != set(payload['panels']):
        _refuse('Preform must declare a sourced frame for every derived panel')
    owned = [i for panel in payload['panels'].values() for i in panel['indices']]
    if sorted(owned) != list(range(len(payload['rest_cm']))):
        _refuse('Original derived panels must partition the current mesh')
    section_parameterizations = {}
    for pid, frame in plan['preform']['panels'].items():
        if 'arc_sections' in frame:
            section_parameterizations[pid] = _compile_arc_sections(frame, pid)
            continue
        if 'uv_cm' in frame:
            section_parameterizations[pid] = _compile_cage(frame, pid)
            continue
        u, v = frame['u_axis'], frame['v_axis']
        if abs(_dot(u, u)-1) > 1e-7 or abs(_dot(v, v)-1) > 1e-7 or abs(_dot(u, v)) > 1e-7:
            _refuse('Preform frame must be orthonormal without scale: ' + pid, 'placement')
    if plan['quality']['min_stretch'] >= plan['quality']['max_stretch']:
        _refuse('Assembly strain limits are reversed')
    if plan['assembly']['max_initial_gap_cm'] < plan['consolidation']['weld_gap_cm']:
        _refuse('Initial assembly budget must contain the final geometric tolerance')
    cloth = plan.get('cloth', {})
    steps = cloth.get('mount_release_steps', [0., .5, 1.])
    if steps[0] != 0 or steps[-1] != 1 or any(b <= a for a, b in zip(steps, steps[1:])):
        _refuse('Temporary supports need a monotonic release schedule from zero to one', 'support_conflict')
    _topology(payload)
    _, supports = support_weights(payload, plan, 'assembly')
    return {'status': 'PLAN_VALIDATED', 'mapping_sha256': map_digest(payload),
            'source_garment_sha256': payload.get('source_garment_sha256'),
            'seam_orientation': 'source_arc_and_oriented_mesh_boundary',
            'section_parameterizations': section_parameterizations,
            'supports': supports, 'qualification': 'NONE'}


def preform_coordinates(payload, plan, native_evaluator=None):
    """Evaluate source-bound placement, then apply the same geometric gates.

    A native evaluator is called once per Bend panel with (payload, piece_id,
    frame), returning ({global_vertex_index: world_cm}, backend_record). There
    is deliberately no Python approximation or silent rigid fallback for Bend.
    """
    validation = validate_plan(payload, plan)
    coords = [None] * len(payload['rest_cm'])
    correspondence = []
    native_backends = {}
    for pid, panel in payload['panels'].items():
        frame = plan['preform']['panels'][pid]
        uv0 = frame.get('offset_uv_cm', [0., 0.])
        native_coords = None
        if 'native_bend' in frame:
            if not callable(native_evaluator):
                _refuse('Native Bend requires the Blender preform backend: ' + pid, 'placement')
            native_coords, backend = native_evaluator(payload, pid, frame)
            if (not isinstance(native_coords, dict) or set(native_coords) != set(panel['indices'])
                    or any(type(index) is not int for index in native_coords)):
                _refuse('Native Bend returned an incomplete source vertex correspondence: ' + pid, 'placement')
            if any(not isinstance(point, (list, tuple)) or len(point) != 3
                   or any(type(value) not in (int, float) or not math.isfinite(value) for value in point)
                   for point in native_coords.values()):
                _refuse('Native Bend returned nonfinite or invalid coordinates: ' + pid, 'placement')
            if not isinstance(backend, dict) or not isinstance(backend.get('backend'), str) or not backend['backend']:
                _refuse('Native Bend returned no backend provenance: ' + pid, 'placement')
            native_backends[pid] = backend
        for local_index, index in enumerate(panel['indices']):
            uv = payload['rest_cm'][index][:2]
            if native_coords is not None:
                coords[index] = list(native_coords[index])
                binding = {'native_backend': native_backends[pid]['backend'],
                           'native_local_vertex': local_index, 'frame_source_ref': frame['source_ref']}
            elif 'arc_sections' in frame:
                coords[index], binding = _section_point(frame, validation['section_parameterizations'][pid], uv, pid)
            elif 'uv_cm' in frame:
                coords[index], binding = _cage_point(frame, validation['section_parameterizations'][pid], uv, pid)
            else:
                coords[index] = [frame['origin_cm'][k] + (uv[0]-uv0[0])*frame['u_axis'][k]
                                 + (uv[1]-uv0[1])*frame['v_axis'][k] for k in range(3)]
                binding = {'frame_source_ref': frame['source_ref']}
            correspondence.append({'piece': pid, 'derived_vertex': index,
                'source_uv_cm': list(uv), 'target_cm': list(coords[index]),
                'preform_source_ref': frame['source_ref'], **binding})
    try:
        quality = continuous_quality(payload, coords, plan['quality'])
        gap = _gap(coords, _pairs(payload))
        if gap > plan['assembly']['max_initial_gap_cm']:
            _refuse('Prepositioned seam exceeds the initial assembly budget', 'placement')
    except StudioError as error:
        error.preform_coordinates_cm=coords
        error.preform_correspondence=correspondence
        error.preform_native_backends=native_backends
        raise
    return coords, {'status': 'PREPOSITIONED', 'mapping_sha256': map_digest(payload),
        'correspondence_version': 1, 'correspondence': correspondence,
        'section_parameterizations': validation['section_parameterizations'],
        'native_backends': native_backends,
        'quality': quality, 'initial_gap_cm': gap, 'qualification': 'NONE'}


def support_weights(payload, plan, stage, release=0.0):
    if stage not in ('assembly', 'mount', 'closure', 'close', 'relax', 'drape'):
        _refuse('Unknown support stage')
    if not math.isfinite(release) or not 0 <= release <= 1:
        _refuse('Support release must be between zero and one', 'support_conflict')
    ids, weights, memberships = set(), {}, {}
    factors = {'temporary': 1-release if stage in ('assembly', 'mount', 'closure', 'close') else 0.,
               'drape': 1., 'functional': 1.}
    declarations = []
    for role, entries in plan['supports'].items():
        for item in entries:
            if item['id'] in ids:
                _refuse('Support identifiers must be unique', 'support_conflict')
            ids.add(item['id'])
            panel = payload['panels'].get(item['piece'])
            if panel is None or ('edge' in item and item['edge'] not in panel['edges']):
                _refuse('Support must reference a current named source panel/edge', 'support_conflict')
            selected = panel['edges'][item['edge']] if 'edge' in item else panel['indices']
            weight = item['weight'] * factors[role]
            for index in selected:
                if weight > 0:
                    key = str(index)
                    weights[key] = max(weights.get(key, 0.), weight)
                    memberships.setdefault(key, []).append({'id': item['id'], 'role': role, 'weight': weight})
            declarations.append({'id': item['id'], 'role': role, 'effective_weight': weight,
                                 'source_ref': item['source_ref']})
    return weights, {'stage': stage, 'release': release, 'declarations': declarations,
        'overlapping_supports': {i: v for i, v in memberships.items() if len(v) > 1},
        'temporary_supports_active': factors['temporary'] > 0 and bool(plan['supports']['temporary']),
        'combination': 'maximum_declared_weight', 'qualification': 'NONE'}


def continuous_quality(payload, coords, limits):
    """Retain separate 2D rest triangles even when seam vertices are shared."""
    result = validate_metrics(payload, coords, limits)
    result['rest_metric_domain'] = 'immutable_source_uv_per_face'
    result['simulation_rest_mode'] = payload.get('rest_mode', 'source_2d_flat')
    return result


def _collision(coords, callback, required):
    if callback is None:
        return {'ok': not required, 'reason': 'collision_check_unavailable' if required else 'declared_free_assembly'}
    value = callback(coords)
    if isinstance(value, bool):
        return {'ok': value}
    if not isinstance(value, dict) or type(value.get('ok')) is not bool:
        _refuse('Collision callback must return bool or a report with boolean ok')
    return value


def bounded_close(payload, coords, plan, collision_check=None):
    """One bounded native operation may run this deterministic local solver.

    Each accepted step is capped, line searched, and checked against source
    lengths, support mobility, face orientation, quality, and collision reserve.
    Failure returns the last admissible coordinates and an explicit refusal.
    """
    validate_plan(payload, plan)
    _coordinates(payload, coords)
    start = copy.deepcopy(coords)
    current = copy.deepcopy(coords)
    limits, budget = plan['quality'], plan['assembly']
    pairs = _pairs(payload)
    single_panel = _single_panel_noop(payload)
    tolerance = plan['consolidation']['weld_gap_cm']
    weights, supports = support_weights(payload, plan, 'closure', budget['closure_support_release'])
    report = {'status': 'REFUSED', 'qualification': 'NONE', 'initial_gap_cm': _gap(current, pairs),
              'support_transition': supports, 'accepted_steps': 0, 'history': []}
    def refused(reason, category, **extra):
        report.update(reason=reason, reason_category=category, final_gap_cm=_gap(current, pairs), **extra)
        return current, report
    if report['initial_gap_cm'] > budget['max_initial_gap_cm']:
        return refused('initial_gap_exceeds_assembly_budget', 'placement')
    initial_collision = _collision(current, collision_check, plan['collision']['required'])
    if not initial_collision['ok']:
        return refused('initial_collision_or_missing_collision_evidence', 'placement', collision=initial_collision)
    try:
        continuous_quality(payload, current, limits)
    except StudioError as error:
        return refused('initial_geometry_rejected', 'geometry_safety', detail=str(error),
                       quality=getattr(error, 'quality_metrics', None))
    for group in permanent_support_groups(payload):
        fixed = [i for i in group if weights.get(str(i), 0.) >= 1.]
        if any(math.dist(current[a], current[b]) > tolerance for a in fixed for b in fixed):
            return refused('contradictory_fixed_seam_supports', 'support_conflict', fixed_vertices=fixed)
    if not pairs:
        if single_panel:
            report.update(status='GEOMETRY_READY', operation='SINGLE_PANEL_NO_OP',
                final_gap_cm=0., max_displacement_cm=0., explicit_unions=0,
                sewing_executed=False, welding_executed=False, closure_behavior='NOT_QUALIFIED',
                source_mapping_sha256=map_digest(payload),
                preserved_links=list(payload['seams']),
                quality=continuous_quality(payload, current, limits))
            return current, report
        return refused('no_declared_permanent_seams', 'free_assembly')
    adjacency = [set() for _ in current]
    edge_list = list(_edges(payload['faces']))
    for a, b in edge_list:
        adjacency[a].add(b)
        adjacency[b].add(a)
    last_rejection = None
    for iteration in range(budget['iterations']):
        gap = _gap(current, pairs)
        # Leave numerical clearance for consolidation and floating point IO.
        if gap <= tolerance * .95:
            report.update(status='GEOMETRY_READY', final_gap_cm=gap,
                max_displacement_cm=max(math.dist(a, b) for a, b in zip(start, current)),
                quality=continuous_quality(payload, current, limits))
            return current, report
        force, counts = [[0., 0., 0.] for _ in current], [0] * len(current)
        for a, b in pairs:
            delta = _vec(current[b], current[a])
            for i, sign in ((a, 1), (b, -1)):
                counts[i] += 1
                for k in range(3):
                    force[i][k] += sign * delta[k] * .5
        influenced = {i for i, count in enumerate(counts) if count}
        for i in influenced:
            force[i] = [v / counts[i] for v in force[i]]
        # Extend partner motion through mesh neighbours, never across undeclared
        # proximity or separate layers. Source edge springs resist deformation.
        for _ in range(budget['neighborhood_rings']):
            frontier = {j for i in influenced for j in adjacency[i]} - influenced
            for j in frontier:
                neighbors = adjacency[j] & influenced
                force[j] = [sum(force[i][k] for i in neighbors)/len(neighbors) for k in range(3)]
            influenced.update(frontier)
        for a, b in edge_list:
            delta = _vec(current[b], current[a])
            length = math.sqrt(_dot(delta, delta))
            rest = math.dist(payload['rest_cm'][a], payload['rest_cm'][b])
            if length > 1e-12:
                spring = .05 * (length-rest)/length
                for k in range(3):
                    force[a][k] += spring * delta[k]
                    force[b][k] -= spring * delta[k]
        for i, vector in enumerate(force):
            mobility = 1-weights.get(str(i), 0.)
            length = math.sqrt(_dot(vector, vector))
            scale = mobility * min(1., budget['max_step_cm']/max(length, 1e-12))
            force[i] = [v * scale for v in vector]
        before_energy = sum(math.dist(current[a], current[b])**2 for a, b in pairs)
        accepted = False
        for line in range(16):
            scale = 2. ** -line
            trial = [[p[k]+scale*force[i][k] for k in range(3)] for i, p in enumerate(current)]
            energy = sum(math.dist(trial[a], trial[b])**2 for a, b in pairs)
            if energy >= before_energy - 1e-14:
                last_rejection = 'no_descent'
                continue
            if max(math.dist(a, b) for a, b in zip(start, trial)) > budget['max_displacement_cm']:
                last_rejection = 'displacement_budget'
                continue
            try:
                trial_quality = continuous_quality(payload, trial, limits)
                motion_quality = validate_linear_motion(payload, current, trial)
            except StudioError:
                last_rejection = 'source_metric_or_mesh_quality'
                continue
            collision = _collision(trial, collision_check, plan['collision']['required'])
            if not collision['ok']:
                last_rejection = 'collision_reserve'
                continue
            current = trial
            report['accepted_steps'] += 1
            report['history'].append({'iteration': iteration+1, 'step_scale': scale,
                'gap_cm': _gap(current, pairs), 'max_step_cm': max(math.sqrt(_dot(v, v))*scale for v in force),
                'metric_version': trial_quality['metric_version'], 'validator_version': trial_quality['validator_version'],
                'min_principal_stretch': trial_quality['min_principal_stretch'],
                'max_principal_stretch': trial_quality['max_principal_stretch'],
                'linear_motion_min_area_cm2': motion_quality['minimum_area_cm2']})
            accepted = True
            break
        if not accepted:
            return refused('no_admissible_closure_step', 'free_assembly', limiting_constraint=last_rejection)
    if _gap(current, pairs) <= tolerance:
        report.update(status='GEOMETRY_READY', final_gap_cm=_gap(current, pairs),
                      quality=continuous_quality(payload, current, limits))
        return current, report
    return refused('bounded_closure_did_not_converge', 'free_assembly', limiting_constraint=last_rejection)


def _vertex_manifold(faces):
    links = {}
    for face in faces:
        for i, vertex in enumerate(face):
            a, b = face[(i+1) % 3], face[(i+2) % 3]
            graph = links.setdefault(vertex, {})
            graph.setdefault(a, set()).add(b)
            graph.setdefault(b, set()).add(a)
    for vertex, graph in links.items():
        seen, pending = set(), [next(iter(graph))]
        while pending:
            point = pending.pop()
            if point not in seen:
                seen.add(point)
                pending.extend(graph[point]-seen)
        ends = sum(len(v) == 1 for v in graph.values())
        if len(seen) != len(graph) or any(len(v) > 2 for v in graph.values()) or ends not in (0, 2):
            _refuse('Consolidation would create a nonmanifold bowtie vertex: ' + str(vertex))


def consolidate(payload, coords, plan):
    validate_plan(payload, plan)
    _coordinates(payload, coords)
    tolerance = plan['consolidation']['weld_gap_cm']
    continuous_quality(payload, coords, plan['quality'])
    for group in permanent_support_groups(payload):
        diameter = max(math.dist(coords[a], coords[b]) for a in group for b in group)
        if diameter > tolerance:
            _refuse('Permanent transitive cohort diameter exceeds verified weld tolerance')
    single_panel = _single_panel_noop(payload)
    if single_panel:
        # The cloth is already one continuous panel. No source endpoints are
        # joined and nonpermanent links remain descriptions, not fastenings.
        vertices, faces = copy.deepcopy(coords), copy.deepcopy(payload['faces'])
        mapping, count = {i: i for i in range(len(coords))}, 0
        if len({tuple(sorted(face)) for face in faces}) != len(faces):
            _refuse('Single-panel consolidation would retain duplicate faces')
    else:
        vertices, faces, mapping, count = weld_permanent(coords, payload['faces'], payload['seams'], tolerance)
    # A geometric union may use a fixed declared support as its representative,
    # but cannot move that support to the average of a nearby cohort.
    supports, _ = support_weights(payload, plan, 'closure', plan['assembly']['closure_support_release'])
    groups = {}
    for old, new in mapping.items():
        groups.setdefault(new, []).append(old)
    support_anchors = []
    for new, old_ids in groups.items():
        fixed = [i for i in old_ids if supports.get(str(i), 0.) >= 1.]
        if not fixed:
            continue
        if any(math.dist(coords[fixed[0]], coords[i]) > 1e-6 for i in fixed[1:]):
            _refuse('Consolidation has contradictory fixed cohort supports', 'support_conflict')
        vertices[new] = list(coords[fixed[0]])
        support_anchors.append({'vertex': new, 'fixed_source_vertices': fixed})
    for sid, seam in payload['seams'].items():
        if seam['kind'] != 'permanent' and any(a != b and mapping[a] == mapping[b] for a, b in seam['pairs']):
            _refuse('Consolidation would collapse a declared opening or detachable link: ' + sid)
    union_motion = validate_linear_motion(payload, coords, [vertices[mapping[i]] for i in range(len(coords))])
    _vertex_manifold(faces)
    sources = face_sources(payload)
    result = copy.deepcopy(payload)
    result.update(version=2, rest_mode='assembled_3d', rest_cm=copy.deepcopy(vertices),
        placed_cm=copy.deepcopy(vertices), faces=faces,
        source_rest_triangles_cm=sources['source_rest_triangles_cm'],
        source_face_pieces=sources['source_face_pieces'],
        source_face_vertex_ids=sources['source_face_vertex_ids'],
        source_vertex_map={str(i): j for i, j in mapping.items()},
        source_mapping_sha256=map_digest(payload),
        regional_source={k: copy.deepcopy(payload.get(k)) for k in ('rest_cm', 'panels', 'source_garment_sha256')})
    source_ids = payload.get('source_vertex_indices', list(range(len(coords))))
    result['source_vertex_cohorts'] = {str(new): [source_ids[i] for i in old_ids] for new, old_ids in groups.items()}
    result['source_vertex_indices'] = [min(result['source_vertex_cohorts'][str(i)]) for i in range(len(vertices))]
    result['source_vertex_index_semantics'] = 'representative_only_see_source_vertex_cohorts'
    for panel in (() if single_panel else result['panels'].values()):
        panel['indices'] = sorted({mapping[i] for i in panel['indices']})
        panel['boundary'] = [mapping[i] for i in panel['boundary']]
        panel['edges'] = {name: [mapping[i] for i in ids] for name, ids in panel['edges'].items()}
    for seam in (() if single_panel else result['seams'].values()):
        seam['pairs'] = [[mapping[a], mapping[b]] for a, b in seam['pairs']]
        if seam['kind'] == 'permanent':
            seam['consolidated'] = True
    pins = {}
    for i, weight in payload.get('pins', {}).items():
        j = str(mapping[int(i)])
        pins[j] = max(pins.get(j, 0.), weight)
    result['pins'] = pins
    result['quality'] = continuous_quality(result, vertices, plan['quality'])
    result['full_rest_area_cm2'] = result['quality']['rest_area_cm2']
    result.pop('fitting_tacks', None)
    report = {'status': 'GEOMETRY_CONSOLIDATED', 'qualification': 'NONE',
        'source_mapping_sha256': map_digest(payload), 'result_mapping_sha256': map_digest(result),
        'explicit_unions': count, 'vertices_before': len(coords), 'vertices_after': len(vertices),
        'fixed_support_anchors': support_anchors,
        'linear_union_motion': union_motion,
        'verified_weld_gap_cm': tolerance, 'observed_pair_gap_cm': _gap(coords, _pairs(payload)),
        'source_rest_mode': 'immutable_source_uv_per_face', 'simulation_rest_mode': 'assembled_3d',
        'quality': result['quality'], 'preserved_links': [sid for sid, s in payload['seams'].items() if s['kind'] != 'permanent'],
        'requires': ['continuous_cloth_relaxation', 'body_fitting', 'behaviour_qualification', 'artistic_review']}
    if any(seam['kind']=='permanent' for seam in payload['seams'].values()):
        source={key:copy.deepcopy(payload[key]) for key in ('version','component_id','source_garment_sha256',
            'rest_cm','faces','panels','seams')}
        for key in ('trial_mode','single_panel_source','source_vertex_indices','source_rest_triangles_cm',
                    'source_face_pieces','source_face_vertex_ids'):
            if key in payload:source[key]=copy.deepcopy(payload[key])
        proof={'version':1,'scope':'EXPLICIT_SOURCE_PERMANENT_UNIONS','source':source,
            'source_mapping_sha256':map_digest(payload),'result_mapping_sha256':map_digest(result),
            'coordinates_before_cm':copy.deepcopy(coords),'plan_sha256':digest(plan),
            'verified_weld_gap_cm':tolerance,'observed_pair_gap_cm':_gap(coords,_pairs(payload)),
            'explicit_unions':count,'qualification':'GEOMETRY_ONLY'}
        proof['proof_sha256']=digest(proof)
        result['permanent_consolidation']=proof
        report['permanent_continuity']=verify_permanent_continuity(result,tolerance)
    if single_panel:
        report.update(operation='SINGLE_PANEL_NO_OP', sewing_executed=False,
            welding_executed=False, closure_behavior='NOT_QUALIFIED', verified_weld_gap_cm=None)
    return result, report


def verify_permanent_continuity(payload,weld_limit_cm):
    """Reconstruct explicit source unions; a consolidated flag is insufficient.

    This is geometry evidence. It does not transfer the earlier Cloth result
    or waive the current frame, contact, metric and movement checks.
    """
    permanent={sid:seam for sid,seam in payload['seams'].items() if seam['kind']=='permanent'}
    if not permanent:return None
    proof=payload.get('permanent_consolidation')
    if payload.get('rest_mode')!='assembled_3d' or not isinstance(proof,dict):
        _refuse('Permanent continuity requires its exact source consolidation proof')
    if (proof.get('version')!=1 or proof.get('scope')!='EXPLICIT_SOURCE_PERMANENT_UNIONS'
            or proof.get('qualification')!='GEOMETRY_ONLY'
            or proof.get('proof_sha256')!=digest({k:v for k,v in proof.items() if k!='proof_sha256'})):
        _refuse('Permanent consolidation proof changed or has an unsupported scope')
    source=proof['source'];coords=proof['coordinates_before_cm'];tolerance=proof['verified_weld_gap_cm']
    if (not math.isfinite(tolerance) or tolerance<0 or tolerance>weld_limit_cm+1e-8
            or source['component_id']!=payload['component_id']
            or source['source_garment_sha256']!=payload['source_garment_sha256']
            or map_digest(source)!=proof['source_mapping_sha256']
            or payload.get('source_mapping_sha256')!=proof['source_mapping_sha256']
            or map_digest(payload)!=proof['result_mapping_sha256']):
        _refuse('Permanent consolidation source, current map or weld budget changed')
    _coordinates(source,coords)
    source_permanent={sid:seam for sid,seam in source['seams'].items() if seam['kind']=='permanent'}
    if set(source['seams'])!=set(payload['seams']) or set(source_permanent)!=set(permanent) or not _pairs(source):
        _refuse('Permanent continuity lost actual source sewing pairs')
    for group in permanent_support_groups(source):
        if max(math.dist(coords[a],coords[b]) for a in group for b in group)>tolerance:
            _refuse('Permanent source cohort exceeds its verified weld tolerance')
    vertices,faces,mapping,count=weld_permanent(coords,source['faces'],source['seams'],tolerance)
    if (payload['faces']!=faces or len(payload['rest_cm'])!=len(vertices)
            or payload.get('source_vertex_map')!={str(old):new for old,new in mapping.items()}
            or proof['explicit_unions']!=count
            or proof['observed_pair_gap_cm']!=_gap(coords,_pairs(source))):
        _refuse('Permanent continuity does not match the reconstructed explicit source unions')
    source_ids=source.get('source_vertex_indices',list(range(len(coords))))
    cohorts={str(new):[] for new in range(len(vertices))}
    for old,new in mapping.items():cohorts[str(new)].append(source_ids[old])
    if payload.get('source_vertex_cohorts')!=cohorts:
        _refuse('Permanent continuity source vertex cohorts changed')
    for old,new in mapping.items():
        if math.dist(coords[old],payload['rest_cm'][new])>tolerance+1e-8:
            _refuse('Consolidated rest vertex lies outside its explicit source cohort tolerance')
    panels=copy.deepcopy(source['panels'])
    for panel in panels.values():
        panel['indices']=sorted({mapping[index] for index in panel['indices']})
        panel['boundary']=[mapping[index] for index in panel['boundary']]
        panel['edges']={name:[mapping[index] for index in ids] for name,ids in panel['edges'].items()}
    if payload['panels']!=panels:
        _refuse('Permanent continuity source panel boundaries or support edges changed')
    for sid,seam in source['seams'].items():
        current=payload['seams'].get(sid)
        expected=copy.deepcopy(seam);expected['pairs']=[[mapping[a],mapping[b]] for a,b in seam['pairs']]
        if seam['kind']=='permanent':expected['consolidated']=True
        if current!=expected:
            _refuse('Permanent continuity source seam mapping or relation kind changed: '+sid)
        if seam['kind']=='permanent' and any(a!=b for a,b in current['pairs']):
            _refuse('A permanent source pair is still open after consolidation: '+sid)
        if seam['kind']!='permanent' and any(a!=b and mapping[a]==mapping[b] for a,b in seam['pairs']):
            _refuse('A source opening or detachable relation was consolidated: '+sid)
    source_metrics=face_sources(source);current_metrics=face_sources(payload)
    keys=('source_rest_triangles_cm','source_face_pieces','source_face_vertex_ids')
    if source_metrics['binding_issues'] or current_metrics['binding_issues'] or any(source_metrics[k]!=current_metrics[k] for k in keys):
        _refuse('Permanent continuity lost exact source face material coordinates')
    _vertex_manifold(payload['faces'])
    return {'status':'CONTINUITY_VERIFIED','scope':'EXPLICIT_PERMANENT_SOURCE_PAIRS_AND_SHARED_CURRENT_VERTICES',
        'proof_sha256':proof['proof_sha256'],'source_mapping_sha256':proof['source_mapping_sha256'],
        'result_mapping_sha256':proof['result_mapping_sha256'],'source_permanent_pair_count':len(_pairs(source)),
        'explicit_unions':count,'verified_weld_gap_cm':tolerance,'observed_before_weld_gap_cm':proof['observed_pair_gap_cm'],
        'measured_current_gap_cm':_gap(payload['placed_cm'],_pairs(payload)),
        'qualification':'GEOMETRY_ONLY','current_physics_validation_required':True}


def migrate_legacy_receipt(receipt):
    """Wrap immutable historic evidence; never promote it to a new qualification."""
    return {'version': 1, 'migration': 'legacy_sewing_to_pattern_assembly',
        'status': 'MIGRATED_EVIDENCE_ONLY', 'source_receipt_sha256': digest(receipt),
        'legacy_receipt': copy.deepcopy(receipt), 'qualification': 'NONE',
        'metric_evidence': legacy_metric_evidence(receipt),
        'requires': ['source_mapping_rebind', 'explicit_support_roles', 'native_stage_replay'],
        'historical_result': receipt.get('simulation', receipt.get('status', 'unknown'))}
