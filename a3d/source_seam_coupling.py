"""Source-parameter coupling of one component's existing guide proposals.

This module prepares auxiliary cages, in cm. It never edits a pattern, executes
physics, admits front coverage or infers anatomical homology. Seam length
admission uses the supplied source recipe and the existing ``seam_report``.
"""
from __future__ import annotations

import bisect
import copy
import json
import math
import time
from fractions import Fraction

from .core import StudioError, canonical, digest
from .pattern_assembly import _cage_point, _compile_arc_sections, _compile_cage, _section_point
from .sewing import chain_lengths, edge_chain, seam_report


_DEFAULTS = {'max_source_points': 20000, 'max_source_triangles': 20000,
    'max_controls': 70000, 'max_triangles': 131072, 'max_seconds': 60.}
_HARD = {'max_source_points': 80000, 'max_source_triangles': 32768,
    'max_controls': 70000, 'max_triangles': 131072, 'max_seconds': 120.}


def _finite(value):
    return type(value) in (int, float) and math.isfinite(value)


def _vector(value, size):
    return isinstance(value, (list, tuple)) and len(value) == size and all(_finite(x) for x in value)


def _near_parameter(a, b):
    # Only arithmetic round-off in a dimensionless source parameter. This is
    # never a distance search, a geometric weld or a source corner tolerance.
    return abs(a-b) <= 32*math.ulp(1.)


class _Budget:
    def __init__(self, values, clock):
        if values is None:
            values = {}
        if not isinstance(values, dict) or set(values)-set(_DEFAULTS):
            raise StudioError('Unknown source seam coupling budget')
        self.limits = {**_DEFAULTS, **values}
        for key, maximum in _HARD.items():
            value = self.limits[key]
            valid = _finite(value) if key == 'max_seconds' else type(value) is int
            if not valid or not 0 < value <= maximum:
                raise StudioError('Source seam coupling requires finite bounded budgets: '+key)
        self.clock = clock
        self.started = self._time()
        self.last_time = self.started
        self.controls = self.triangles = 0

    def _time(self):
        value = self.clock()
        if not _finite(value):
            raise StudioError('Source seam coupling clock is not finite')
        return value

    def check(self):
        value = self._time()
        if value < self.last_time or value-self.started > self.limits['max_seconds']:
            raise StudioError('Source seam coupling time budget exhausted or clock reversed')
        self.last_time = value

    def reserve(self, controls, triangles):
        self.check()
        if (self.controls+controls > self.limits['max_controls']
                or self.triangles+triangles > self.limits['max_triangles']):
            raise StudioError('Source seam coupling control or triangle budget exhausted')
        self.controls += controls
        self.triangles += triangles


def _source(data, frames, recipe, budget):
    from .garment_guides import _source_limb_mesh
    if (not isinstance(data, dict) or not isinstance(data.get('component_id'), str)
            or not data['component_id'] or data.get('units') != 'cm'
            or not isinstance(data.get('pieces'), dict) or not 1 <= len(data['pieces']) <= 16
            or not isinstance(frames, dict) or not frames or not set(frames) <= set(data['pieces'])):
        raise StudioError('Source seam coupling requires one explicit cm component and its source pieces')
    if (not isinstance(recipe, dict) or recipe.get('component_id') != data['component_id']
            or not isinstance(recipe.get('seams'), dict)):
        raise StudioError('Source seam coupling requires the matching explicit source seam recipe')
    points = faces = 0
    for pid, piece in data['pieces'].items():
        budget.check()
        if (not isinstance(pid, str) or not pid or not isinstance(piece, dict)
                or not isinstance(piece.get('vertices'), list) or not 3 <= len(piece['vertices']) <= 5000
                or not all(_vector(v, 2) for v in piece['vertices'])
                or not isinstance(piece.get('faces'), list) or not piece['faces']
                or not isinstance(piece.get('edges'), dict)):
            raise StudioError('Source seam coupling requires finite original source triangles: '+str(pid))
        points += len(piece['vertices']); faces += len(piece['faces'])
        if (points > budget.limits['max_source_points'] or faces > budget.limits['max_source_triangles']
                or len(piece['edges']) > 256):
            raise StudioError('Source seam coupling original point, triangle or boundary budget exhausted')
        for face in piece['faces']:
            budget.check()
            if (not isinstance(face, (list, tuple)) or len(face) != 3
                    or any(type(i) is not int or not 0 <= i < len(piece['vertices']) for i in face)
                    or len(set(face)) != 3):
                raise StudioError('Invalid original source triangle: '+pid)
            a, b, c = [piece['vertices'][i] for i in face]
            if not math.isfinite((b[0]-a[0])*(c[1]-a[1])-(b[1]-a[1])*(c[0]-a[0])):
                raise StudioError('Source material triangle arithmetic is not finite: '+pid)
        for name, indices in piece['edges'].items():
            if (not isinstance(name, str) or not name or not isinstance(indices, list)
                    or len(indices) < 2
                    or any(type(i) is not int or not 0 <= i < len(piece['vertices']) for i in indices)
                    or len(indices) != len(set(indices))):
                raise StudioError('Source boundary indices are invalid: '+pid)
            if not math.isfinite(chain_lengths(edge_chain(piece, name)[1])[-1]):
                raise StudioError('Source boundary length arithmetic is not finite: '+pid)
        try:
            polygon_area = math.fsum(a[0]*b[1]-b[0]*a[1] for a, b in
                                    zip(piece['vertices'], piece['vertices'][1:]+piece['vertices'][:1]))/2
        except (OverflowError, ValueError) as error:
            raise StudioError('Source material area arithmetic is not finite: '+pid) from error
        if not math.isfinite(polygon_area):
            raise StudioError('Source material area arithmetic is not finite: '+pid)
        _source_limb_mesh(piece, 1)
        budget.check()
    seams = data.get('seams')
    if not isinstance(seams, list) or not 1 <= len(seams) <= 128:
        raise StudioError('Source seam coupling requires bounded explicit source relations')
    ids = []
    for seam in seams:
        budget.check()
        if (not isinstance(seam, dict) or not isinstance(seam.get('id'), str) or not seam['id']
                or seam.get('orientation') not in ('forward', 'reverse')
                or seam.get('kind') not in ('permanent', 'detachable', 'closure')
                or any(not isinstance(seam.get('piece_'+side), str)
                       or seam['piece_'+side] not in data['pieces'] for side in ('a', 'b'))):
            raise StudioError('Invalid explicit source sewing relation')
        ids.append(seam['id'])
        declared = recipe['seams'].get(seam['id'])
        if (not isinstance(declared, dict) or declared.get('kind') != seam['kind']
                or not _finite(declared.get('ease_b_over_a')) or declared['ease_b_over_a'] <= -1
                or not _finite(declared.get('tolerance_relative'))
                or not 0 <= declared['tolerance_relative'] <= 1):
            raise StudioError('Source sewing recipe must declare finite kinds, ease and tolerance')
        for side in ('a', 'b'):
            if seam.get('edge_'+side) not in data['pieces'][seam['piece_'+side]]['edges']:
                raise StudioError('Source sewing relation names a missing boundary')
    if len(set(ids)) != len(ids) or set(ids) != set(recipe['seams']):
        raise StudioError('Source sewing IDs must be unique and exactly covered by the recipe')
    # Existing ownership, topological orientation and length admission. The
    # caller cannot replace its length contract with a larger hidden epsilon.
    reports, _ = seam_report(data, recipe)
    budget.check()
    return {row['id']: row for row in reports}


def _evaluator(frame, pid, budget):
    if (not isinstance(frame, dict) or not isinstance(frame.get('source_ref'), str)
            or not frame['source_ref']):
        raise StudioError('Source seam coupling needs an explicit existing guide reference: '+pid)
    keys = set(frame)
    if keys == {'source_ref', 'uv_cm', 'target_cm', 'triangles'}:
        if (not isinstance(frame['uv_cm'], list) or len(frame['uv_cm']) > budget.limits['max_controls']
                or not isinstance(frame['triangles'], list)
                or len(frame['triangles']) > budget.limits['max_triangles']):
            raise StudioError('Input guide cage exceeds the declared source coupling budget')
        compiled = _compile_cage(frame, pid, check_time=budget.check)
        return lambda uv: _cage_point(frame, compiled, uv, pid, check_time=budget.check)[0]
    if keys == {'source_ref', 'arc_sections', 'u_direction'}:
        sections = frame['arc_sections']
        if (type(frame['u_direction']) is not int or frame['u_direction'] not in (-1, 1)
                or not isinstance(sections, list) or not 2 <= len(sections) <= 128):
            raise StudioError('Input arc guide must have bounded sections and explicit source direction')
        total = 0
        for section in sections:
            budget.check()
            if (not isinstance(section, dict) or set(section) != {'v_cm', 'arc_offset_cm', 'curve_cm'}
                    or not _finite(section['v_cm']) or not _finite(section['arc_offset_cm'])
                    or not isinstance(section['curve_cm'], list) or not 2 <= len(section['curve_cm']) <= 4096
                    or not all(_vector(v, 3) for v in section['curve_cm'])):
                raise StudioError('Input arc guide requires finite actual source curves')
            total += len(section['curve_cm'])
            if total > budget.limits['max_controls']:
                raise StudioError('Input arc guide exceeds the declared control budget')
        compiled = _compile_arc_sections(frame, pid)
        return lambda uv: _section_point(frame, compiled, uv, pid)[0]
    plain = {'source_ref', 'origin_cm', 'u_axis', 'v_axis'}
    if plain <= keys <= plain | {'offset_uv_cm'}:
        if (not all(_vector(frame[key], 3) for key in ('origin_cm', 'u_axis', 'v_axis'))
                or not _vector(frame.get('offset_uv_cm', [0., 0.]), 2)):
            raise StudioError('Input plain guide needs finite source axes and origin')
        u, v = frame['u_axis'], frame['v_axis']
        if (abs(math.fsum(x*x for x in u)-1) > 1e-7 or abs(math.fsum(x*x for x in v)-1) > 1e-7
                or abs(math.fsum(x*y for x, y in zip(u, v))) > 1e-7):
            raise StudioError('Input plain guide axes must be orthonormal without material scale')
        offset = frame.get('offset_uv_cm', [0., 0.])
        return lambda uv: [frame['origin_cm'][k]+(uv[0]-offset[0])*u[k]+(uv[1]-offset[1])*v[k] for k in range(3)]
    raise StudioError('Unsupported native bend, hybrid or incomplete source guide frame: '+pid)


def _refinement_keys(piece, n, budget):
    # Same integer barycentric identity as _source_limb_mesh. Reconstructing
    # this identity avoids finding an index by UV or world-coordinate proximity.
    keys = set()
    for face in sorted(piece['faces'], key=lambda face: tuple(sorted(face))):
        budget.check()
        for i in range(n+1):
            for j in range(n+1-i):
                weights = (n-i-j, i, j)
                keys.add(tuple(sorted((index, weight) for index, weight in zip(face, weights) if weight)))
    return {key: index for index, key in enumerate(sorted(keys))}


def _triangle_edges(face):
    return [tuple(sorted((a, b))) for a, b in zip(face, face[1:]+face[:1])]


def _prepare_piece(piece, frame, pid, n, budget):
    from .garment_guides import _source_limb_mesh
    if isinstance(frame, dict) and set(frame) == {'source_ref', 'uv_cm', 'target_cm', 'triangles'}:
        from .guide_cage_sampling import validated_cage_state
        evaluate = _evaluator(frame, pid, budget)
        return validated_cage_state(piece, frame, pid, n, budget, evaluate)
    budget.reserve(len(piece['vertices']), len(piece['faces'])*n*n)
    uv, triangles = _source_limb_mesh(piece, n)
    budget.reserve(len(uv)-len(piece['vertices']), 0)
    evaluate = _evaluator(frame, pid, budget)
    # Preserve the exact original proposal when it already uses this source
    # refinement. New boundary points still use the checked shared evaluator.
    if frame.get('uv_cm') == uv and frame.get('triangles') == triangles:
        targets = copy.deepcopy(frame['target_cm'])
    else:
        targets = []
        for point in uv:
            budget.check()
            targets.append(evaluate(point))
    if not all(_vector(point, 3) for point in targets):
        raise StudioError('Source guide produced a nonfinite target: '+pid)
    keys = _refinement_keys(piece, n, budget)
    if len(keys) != len(uv):
        raise StudioError('Source integer refinement identities are inconsistent')
    segments = {}
    for a in range(len(piece['vertices'])):
        b = (a+1) % len(piece['vertices']); lo, hi = sorted((a, b)); controls = []
        for step in range(n+1):
            key = tuple((index, weight) for index, weight in ((lo, n-step), (hi, step)) if weight)
            if key not in keys:
                raise StudioError('Original source boundary is absent from its actual triangle refinement')
            controls.append((step/n, keys[key]))
        segments[lo, hi] = controls
    owners = {}
    for index, triangle in enumerate(triangles):
        for edge in _triangle_edges(triangle):
            owners.setdefault(edge, set()).add(index)
    source_faces = [index for index, face in sorted(enumerate(piece['faces']), key=lambda row: tuple(sorted(row[1])))]
    return {'uv': uv, 'triangles': triangles, 'original': targets, 'evaluate': evaluate,
        'keys': keys, 'segments': segments, 'owners': owners,
        'triangle_source_faces': [face for face in source_faces for _ in range(n*n)], 'inserted': []}


def _chain(piece, name, reverse, state, pid, n):
    indices, points, _ = edge_chain(piece, name)
    if reverse:
        indices, points = list(reversed(indices)), list(reversed(points))
    cumulative = chain_lengths(points); total = cumulative[-1]
    if not math.isfinite(total) or total <= 0:
        raise StudioError('Source sewing chain length is not finite')
    controls = []
    for ordinal, (a, b) in enumerate(zip(indices, indices[1:])):
        lo, hi = sorted((a, b))
        ordered = state['segments'][lo, hi] if a == lo else list(reversed(state['segments'][lo, hi]))
        for t, index in ordered[:-1]:
            local = t if a == lo else 1-t
            fraction = (cumulative[ordinal]+local*(cumulative[ordinal+1]-cumulative[ordinal]))/total
            controls.append({'fraction': fraction, 'index': index, 'piece': pid, 'edge': name,
                'source_segment_vertex_ids': [a, b], 'source_segment_parameter': local,
                'source_corner_vertex_id': a if local == 0 else None})
    controls.append({'fraction': 1., 'index': state['keys'][((indices[-1], n),)],
        'piece': pid, 'edge': name, 'source_segment_vertex_ids': indices[-2:],
        'source_segment_parameter': 1., 'source_corner_vertex_id': indices[-1]})
    if any(_near_parameter(a['fraction'], b['fraction']) for a, b in zip(controls, controls[1:])):
        raise StudioError('Indistinguishable source boundary control parameters; no proximity merge is allowed')
    return {'indices': indices, 'cumulative': cumulative, 'total': total, 'controls': controls,
        'corner_fractions': [value/total for value in cumulative], 'piece': pid, 'edge': name}


def _partition_union(a, b):
    groups = []
    rows = [(row['fraction'], side, row) for side, chain in enumerate((a, b)) for row in chain['controls']]
    for fraction, side, row in sorted(rows, key=lambda item: (item[0], item[1])):
        if groups and _near_parameter(fraction, groups[-1]['fraction']):
            if any(record['side'] == side for record in groups[-1]['provenance']):
                raise StudioError('Ambiguous distinct original source controls at one normalized parameter')
            groups[-1]['provenance'].append({'side': side, **row})
        else:
            groups.append({'fraction': fraction, 'provenance': [{'side': side, **row}]})
    return groups


def _insert(piece, state, edge, t, pid, budget):
    controls = state['segments'][edge]
    position = bisect.bisect_left([value for value, _ in controls], t)
    for neighbour in (position-1, position):
        if 0 <= neighbour < len(controls) and _near_parameter(t, controls[neighbour][0]):
            return controls[neighbour][1]
    if not 0 < position < len(controls):
        raise StudioError('Source seam parameter lies outside its declared original material segment')
    _, a = controls[position-1]; _, b = controls[position]
    owner = state['owners'].get(tuple(sorted((a, b))), set())
    if len(owner) != 1:
        raise StudioError('Source boundary insertion requires exactly one actual supporting triangle')
    face_id = next(iter(owner)); triangle = state['triangles'][face_id]
    source_face_id = state['triangle_source_faces'][face_id]
    budget.reserve(1, 1)
    lo, hi = edge
    # Preserve constant source axes exactly; weighted sums of two equal
    # endpoints can round beyond a strictly declared arc-section boundary.
    uv = [float(Fraction(piece['vertices'][lo][k])+Fraction(t)*
                (Fraction(piece['vertices'][hi][k])-Fraction(piece['vertices'][lo][k]))) for k in (0, 1)]
    target = state['evaluate'](uv)
    if not _vector(target, 3):
        raise StudioError('Inserted source boundary target is not finite')
    new = len(state['uv'])
    oriented = next((triangle[i:]+triangle[:i] for i in range(3)
                     if {triangle[i], triangle[(i+1) % 3]} == {a, b}), None)
    if oriented is None:
        raise StudioError('Source boundary triangle ownership is inconsistent')
    x, y, z = oriented
    for face in ([x, new, z], [new, y, z]):
        points = [(uv if index == new else state['uv'][index]) for index in face]
        p, q, r = points
        determinant = (q[0]-p[0])*(r[1]-p[1])-(q[1]-p[1])*(r[0]-p[0])
        if not math.isfinite(determinant) or abs(determinant) < 1e-10:
            raise StudioError('Source boundary partition cannot be represented by noncollapsed cage triangles')
    for edge_key in _triangle_edges(triangle):
        state['owners'][edge_key].remove(face_id)
    state['uv'].append(uv); state['original'].append(target)
    state['triangles'][face_id] = [x, new, z]
    appended = len(state['triangles']); state['triangles'].append([new, y, z])
    state['triangle_source_faces'].append(source_face_id)
    for index in (face_id, appended):
        for edge_key in _triangle_edges(state['triangles'][index]):
            state['owners'].setdefault(edge_key, set()).add(index)
    controls.insert(position, (t, new))
    state['inserted'].append({'cage_control_index': new, 'source_segment_vertex_ids': list(edge),
        'source_segment_parameter': t, 'source_face_index': source_face_id})
    return new


def _at_fraction(piece, state, chain, fraction, budget, n):
    corners = chain['corner_fractions']
    for ordinal, corner in enumerate(corners):
        if _near_parameter(fraction, corner):
            vertex = chain['indices'][ordinal]
            index = state['keys'][((vertex, n),)]
            interval = min(ordinal, len(corners)-2)
            ids = chain['indices'][interval:interval+2]
            return index, {'piece': chain['piece'], 'edge': chain['edge'],
                'normalized_arc_fraction': fraction, 'source_segment_vertex_ids': ids,
                'source_segment_parameter': 0. if ordinal < len(corners)-1 else 1.,
                'source_corner_vertex_id': vertex, 'cage_control_index': index}
    interval = bisect.bisect_right(corners, fraction)-1
    if not 0 <= interval < len(corners)-1:
        raise StudioError('Common seam parameter lies outside its original source boundary')
    a, b = chain['indices'][interval:interval+2]
    local = (fraction-corners[interval])/(corners[interval+1]-corners[interval])
    edge = tuple(sorted((a, b))); t = local if a == edge[0] else 1-local
    index = _insert(piece, state, edge, t, chain['piece'], budget)
    return index, {'piece': chain['piece'], 'edge': chain['edge'], 'normalized_arc_fraction': fraction,
        'source_segment_vertex_ids': [a, b], 'source_segment_parameter': local,
        'source_corner_vertex_id': None, 'cage_control_index': index}


def couple_source_seams(data, frames, seam_recipe, *, subdivisions=8, budgets=None, clock=time.monotonic, semantics=None,
                        observe_guide_stages=False, strategy='LEGACY_COHORT_MEAN_V1', relaxation=None,
                        numerical_anchor_edges=None, anatomical_attachments=None):
    """Return ``(cages, report)`` without changing any supplied source input.

    Permanent source boundaries in ``frames`` are paired over the union of
    their normalized original corner/refinement partitions. Opposite chains
    are reversed by the source relation, without an assumption about UV axes.
    Every added control subdivides its actual boundary-supporting triangle.
    Legacy common targets are the unweighted mean of original proposals in
    each transitive source cohort. COUPLED_REST_METRIC_V2 instead prepares a
    bounded progressive assembly against immutable material rest lengths.
    Source recipe tolerances admit the input lengths;
    final metric, contact, anatomical and physical gates remain required.
    Optional guide stage observations describe interpolation only, against
    unchanged source UV; they never admit a regular mesh, Cloth or fitting.
    """
    if type(observe_guide_stages) is not bool:
        raise StudioError('Guide stage observation option must be explicitly boolean')
    if strategy not in ('LEGACY_COHORT_MEAN_V1', 'COUPLED_REST_METRIC_V2'):
        raise StudioError('Unsupported versioned source seam coupling strategy')
    if strategy == 'LEGACY_COHORT_MEAN_V1' and (relaxation is not None or numerical_anchor_edges is not None
                                              or anatomical_attachments is not None):
        raise StudioError('Relaxation parameters and numerical anchors require COUPLED_REST_METRIC_V2')
    if strategy == 'COUPLED_REST_METRIC_V2':
        from .assembly_relaxation import validate_options
        relaxation = validate_options(relaxation)
    if type(subdivisions) is not int or not 2 <= subdivisions <= 16:
        raise StudioError('Source seam coupling subdivisions must be an integer in 2..16')
    budget = _Budget(budgets, clock)
    try:
        before = digest([data, frames, seam_recipe] if semantics is None else [data, frames, seam_recipe, semantics])
    except (TypeError, ValueError, OverflowError) as error:
        raise StudioError('Source seam coupling requires finite JSON source inputs') from error
    admitted = _source(data, frames, seam_recipe, budget)
    if strategy == 'COUPLED_REST_METRIC_V2':
        if numerical_anchor_edges is None:
            numerical_anchor_edges = []
        if (not isinstance(numerical_anchor_edges, list) or len(numerical_anchor_edges) > 256
                or any(not isinstance(row, dict) or set(row) != {'piece', 'edge'}
                    or not isinstance(row.get('piece'), str) or row['piece'] not in frames
                    or not isinstance(row.get('edge'), str)
                    or row['edge'] not in data['pieces'][row['piece']]['edges'] for row in numerical_anchor_edges)):
            raise StudioError('Coupled numerical anchors must name existing selected source piece edges')
        keys = [(row['piece'], row['edge']) for row in numerical_anchor_edges]
        if len(set(keys)) != len(keys):
            raise StudioError('Coupled numerical anchors must be unique source edge identities')
        if anatomical_attachments is None:
            anatomical_attachments = []
        if (not isinstance(anatomical_attachments, list) or len(anatomical_attachments) > 4096
                or any(not isinstance(row, dict) or set(row) != {
                    'piece', 'source_uv_cm', 'target_world_cm', 'tolerance_cm', 'source_ref'}
                    or not isinstance(row.get('piece'), str) or row['piece'] not in frames
                    or not _vector(row.get('source_uv_cm'), 2)
                    or not _vector(row.get('target_world_cm'), 3)
                    or not _finite(row.get('tolerance_cm')) or not 0 <= row['tolerance_cm'] <= 1.
                    or not isinstance(row.get('source_ref'), str) or not row['source_ref']
                    for row in anatomical_attachments)):
            raise StudioError('Coupled anatomical attachments require bounded explicit source UV and measured target points')
    relations = sorted((s for s in data['seams'] if s['kind'] == 'permanent'
        and s['piece_a'] in frames and s['piece_b'] in frames), key=lambda s: s['id'])
    if not relations:
        raise StudioError('Source seam coupling has no permanent relation between its supplied pieces')
    if (any(seam_recipe['seams'][s['id']]['ease_b_over_a'] != 0 for s in relations)
            and (strategy == 'LEGACY_COHORT_MEAN_V1'
                 or relaxation['ease_distribution'] != 'UNIFORM_NORMALIZED_SOURCE_ARC')):
        raise StudioError('Source seam coupling V1 cannot infer a nonzero source easing distribution')
    matched = {s['piece_'+side] for s in relations for side in ('a', 'b')}
    if matched != set(frames):
        raise StudioError('Source seam coupling has a guide without a permanent source partner')
    states = {pid: _prepare_piece(data['pieces'][pid], frame, pid, subdivisions, budget)
              for pid, frame in sorted(frames.items())}
    # The subdivision value is passed through each chain; no mutable module
    # state is used, so simultaneous independent preparations remain isolated.
    parents = {}; witnesses = []

    def root(key):
        parents.setdefault(key, key)
        trail = []
        while parents[key] != key:
            trail.append(key); key = parents[key]
        for value in trail:
            parents[value] = key
        return key

    def unite(a, b):
        a, b = root(a), root(b)
        parents[max(a, b)] = min(a, b)

    for seam in relations:
        budget.check()
        chains = [_chain(data['pieces'][seam['piece_'+side]], seam['edge_'+side],
                   side == 'b' and seam['orientation'] == 'reverse', states[seam['piece_'+side]],
                   seam['piece_'+side], subdivisions) for side in ('a', 'b')]
        union = _partition_union(*chains); pairs = []; parameters = []
        for entry in union:
            budget.check()
            pair = []; provenance = []
            for chain in chains:
                pid = chain['piece']
                index, source = _at_fraction(data['pieces'][pid], states[pid], chain, entry['fraction'], budget, subdivisions)
                pair.append([pid, index]); provenance.append(source)
            unite(tuple(pair[0]), tuple(pair[1])); pairs.append(pair)
            parameters.append({'common_fraction': entry['fraction'], 'partners': provenance,
                'original_control_provenance': copy.deepcopy(entry['provenance'])})
        contract = admitted[seam['id']]
        witnesses.append({'source_seam_id': seam['id'], 'source_relation': copy.deepcopy(seam),
            'source_chain_lengths_cm': [chain['total'] for chain in chains],
            'source_length_delta_cm': chains[1]['total']-chains[0]['total'],
            'declared_tolerance_relative': seam_recipe['seams'][seam['id']]['tolerance_relative'],
            'relative_length_residual': contract['residual'],
            'source_corner_partitions': [chain['corner_fractions'] for chain in chains],
            'common_fractions': [entry['fraction'] for entry in union], 'paired_cage_controls': pairs,
            'source_parameters': parameters,
            'max_initial_guide_gap_cm': max(math.dist(states[a[0]]['original'][a[1]], states[b[0]]['original'][b[1]]) for a, b in pairs)})
    original_proposals = {pid: state['original'] for pid, state in states.items()}
    aligned_proposals = original_proposals
    alignment_report = None
    if semantics is not None and strategy == 'LEGACY_COHORT_MEAN_V1':
        from .rigid_guide_alignment import prepare_role_rigid_seeds
        aligned_proposals, alignment_report = prepare_role_rigid_seeds(
            data, semantics, states, witnesses, budget, subdivisions=subdivisions)
    cohorts = {}
    for key in sorted(parents):
        cohorts.setdefault(root(key), []).append(key)
    targets = {pid: copy.deepcopy(points) for pid, points in aligned_proposals.items()}
    for cohort in (cohorts.values() if strategy == 'LEGACY_COHORT_MEAN_V1' else ()):
        budget.check()
        try:
            common = [math.fsum(aligned_proposals[pid][index][k] for pid, index in cohort)/len(cohort) for k in range(3)]
        except OverflowError:
            # A finite mean can exist even when summing finite large inputs
            # overflows. Division before summation keeps this case bounded.
            common = [math.fsum(aligned_proposals[pid][index][k]/len(cohort) for pid, index in cohort) for k in range(3)]
        if not _vector(common, 3):
            raise StudioError('Source cohort mean cannot be represented by finite world coordinates')
        for pid, index in cohort:
            targets[pid][index] = list(common)
    relaxation_report = None
    if strategy == 'COUPLED_REST_METRIC_V2':
        from .assembly_relaxation import relax_assembly
        fixed_controls = {}; attachment_bindings = []; prepared = {}
        for attachment in anatomical_attachments:
            budget.check()
            pid = attachment['piece']; state = states[pid]
            if pid not in prepared:
                cage = {'source_ref': frames[pid]['source_ref'], 'uv_cm': state['uv'],
                    'target_cm': original_proposals[pid], 'triangles': state['triangles']}
                prepared[pid] = cage, _compile_cage(cage, pid, check_time=budget.check)
            cage, compiled = prepared[pid]
            sampled, binding = _cage_point(cage, compiled, attachment['source_uv_cm'], pid, check_time=budget.check)
            gap = math.dist(sampled, attachment['target_world_cm'])
            if gap > attachment['tolerance_cm']:
                raise StudioError('Initial source guide does not satisfy the measured anatomical attachment: '+pid)
            exact = [i for i, uv in enumerate(state['uv']) if list(uv) == list(attachment['source_uv_cm'])]
            if len(exact) > 1:
                raise StudioError('Anatomical attachment has ambiguous exact source cage controls: '+pid)
            support = exact or [i for i, weight in zip(state['triangles'][binding['cage_triangle']],
                binding['barycentric_weights'], strict=True) if weight != 0]
            fixed_controls.setdefault(pid, set()).update(support)
            attachment_bindings.append({**copy.deepcopy(attachment), **binding,
                'initial_point_cm': sampled, 'initial_residual_cm': gap,
                'fixed_cage_control_indices': support,
                'binding_policy': 'EXACT_SOURCE_CONTROL' if exact else 'CONSERVATIVE_FIXED_BARYCENTRIC_SUPPORT_CONTROLS'})
        fixed_controls = {pid: sorted(indices) for pid, indices in sorted(fixed_controls.items())}
        targets, relaxation_report = relax_assembly(
            states, original_proposals, witnesses, budget, options=relaxation, fixed_controls=fixed_controls)
        for binding in attachment_bindings:
            budget.check()
            pid = binding['piece']
            face = states[pid]['triangles'][binding['cage_triangle']]
            point = [math.fsum(weight*targets[pid][i][k] for i, weight in
                zip(face, binding['barycentric_weights'], strict=True)) for k in range(3)]
            residual = math.dist(point, binding['target_world_cm'])
            if residual > binding['tolerance_cm']:
                raise StudioError('Coupled proposal changed an immutable anatomical attachment: '+pid)
            binding.update(final_point_cm=point, final_residual_cm=residual,
                max_fixed_control_displacement_cm=max(math.dist(targets[pid][i], original_proposals[pid][i])
                    for i in binding['fixed_cage_control_indices']))
        binding_inputs = [data, frames, seam_recipe, subdivisions, semantics,
            strategy, relaxation, numerical_anchor_edges, anatomical_attachments, relaxation_report['kernel_code_sha256']]
        if 'constraint_projection' in relaxation_report:
            projection = relaxation_report['constraint_projection']
            binding_inputs.append({key: projection[key] for key in
                ('mode', 'kernel_code_sha256', 'max_sweeps', 'residual_tolerance',
                 'observed_constraint_policy')})
        source_binding = digest(binding_inputs)
    else:
        source_binding = digest([data, frames, seam_recipe, subdivisions] if semantics is None else
            [data, frames, seam_recipe, subdivisions, semantics, alignment_report['kernel_code_sha256']])
    cages = {}; refinements = {}; displacements = {}
    for pid, state in states.items():
        budget.check()
        cages[pid] = {'source_ref': frames[pid]['source_ref']+'; source-seam-coupling:'+source_binding,
            'uv_cm': state['uv'], 'target_cm': targets[pid], 'triangles': state['triangles']}
        _compile_cage(cages[pid], pid, check_time=budget.check)
        source = data['pieces'][pid]
        area = lambda points, faces: math.fsum(abs((points[b][0]-points[a][0])*(points[c][1]-points[a][1])
            -(points[b][1]-points[a][1])*(points[c][0]-points[a][0]))/2 for a, b, c in faces)
        source_area = area(source['vertices'], source['faces']); output_area = area(state['uv'], state['triangles'])
        if not math.isfinite(output_area) or abs(output_area-source_area) > max(1e-7, source_area*1e-10):
            raise StudioError('Source seam coupling changed the original material triangle area')
        refinements[pid] = {'source_faces': len(source['faces']), 'source_uv_area_cm2': source_area,
            'cage_uv_area_cm2': output_area, 'uv_area_error_cm2': output_area-source_area,
            'control_vertices': len(state['uv']), 'control_triangles': len(state['triangles']),
            'inserted_boundary_controls': state['inserted'],
            'triangle_source_face_indices': state['triangle_source_faces']}
        displacements[pid] = max(math.dist(a, b) for a, b in zip(state['original'], targets[pid]))
    for witness in witnesses:
        if alignment_report is not None:
            witness['max_aligned_proposal_gap_cm'] = max(math.dist(
                aligned_proposals[a[0]][a[1]], aligned_proposals[b[0]][b[1]])
                for a, b in witness['paired_cage_controls'])
        witness['max_common_control_gap_cm'] = max(math.dist(targets[a[0]][a[1]], targets[b[0]][b[1]])
            for a, b in witness['paired_cage_controls'])
    if digest([data, frames, seam_recipe] if semantics is None else [data, frames, seam_recipe, semantics]) != before:
        raise StudioError('Source seam coupling mutated immutable source, recipe or guide inputs')
    budget.check()
    report = {'method': 'SOURCE_PERMANENT_NORMALIZED_PARTITION_UNION_CAGE', 'version': 1,
        'component_id': data['component_id'], 'source_sha256': digest(data), 'input_guide_sha256': digest(frames),
        'seam_recipe_sha256': digest(seam_recipe), 'cage_sha256': digest(cages), 'subdivisions': subdivisions,
        'budgets': copy.deepcopy(budget.limits), 'relations': witnesses, 'refinements': refinements,
        'max_target_correction_cm': displacements,
        'unprocessed_external_relations': sorted(s['id'] for s in data['seams'] if s['kind'] == 'permanent'
            and ((s['piece_a'] in frames) != (s['piece_b'] in frames))),
        'target_policy': 'UNWEIGHTED_ORIGINAL_PROPOSAL_MEAN_PER_TRANSITIVE_SOURCE_COHORT',
        'boundary_correspondence': 'COMPLETE_PIECEWISE_LINEAR_CAGE_NORMALIZED_SOURCE_ARC_DOMAIN',
        'input_frame_sampling': 'ORIGINAL_SOURCE_TRIANGLE_REFINEMENT_CONTROL_SAMPLES',
        'parameter_roundoff_policy': 'NORMALIZED_BINARY64_ARITHMETIC_32_ULP_AT_UNIT_SCALE_NO_PROXIMITY',
        'length_admission': 'EXISTING_EXPLICIT_SOURCE_RECIPE_SEAM_REPORT',
        'material_refinement': 'EXISTING_TRIANGLES_AND_SOURCE_BOUNDARY_TRIANGLE_SUBDIVISION_ONLY',
        'source_mutated': False, 'source_uv_scaled': False, 'body_changed': False,
        'front_coverage': 'NOT_REVIEWED', 'qualification': 'NONE', 'anatomical_homology': 'NOT_QUALIFIED',
        'metric_assessment': 'REQUIRED', 'contact_assessment': 'REQUIRED',
        'simulation': 'NOT_EXECUTED', 'fitting': 'NOT_EXECUTED'}
    if alignment_report is not None:
        postseed_displacements = {}
        for pid, points in aligned_proposals.items():
            budget.check()
            postseed_displacements[pid] = max(math.dist(a, b) for a, b in zip(points, targets[pid]))
        report.update(semantics_sha256=digest(semantics), source_binding_sha256=source_binding,
            rigid_alignment=alignment_report,
            postseed_target_correction_cm=postseed_displacements,
            target_policy='UNWEIGHTED_ROLE_RIGID_SEEDED_PROPOSAL_MEAN_PER_TRANSITIVE_SOURCE_COHORT',
            displacement_policy='MAX_TARGET_CORRECTION_FROM_ORIGINAL_GUIDE_SEPARATE_POSTSEED_CORRECTION')
    if relaxation_report is not None:
        external = report['unprocessed_external_relations']
        selected = set(frames)
        report.update(version=2, method='SOURCE_PERMANENT_NORMALIZED_PARTITION_COUPLED_REST_METRIC',
            strategy=strategy, relaxation=relaxation_report,
            source_binding_sha256=source_binding,
            target_policy='BOUNDED_RIGID_FIRST_PROGRESSIVE_SOURCE_STITCH_AND_REST_METRIC_RELAXATION',
            status='PROPOSAL_INCOMPLETE_SOURCE_PARTNERS' if external else relaxation_report['status'],
            permanent_relation_coverage='INCOMPLETE' if external else 'COMPLETE_SELECTED_COMPONENT',
            excluded_nonpermanent_relations=[{'id': s['id'], 'kind': s['kind']}
                for s in sorted(data['seams'], key=lambda s: s['id']) if s['kind'] != 'permanent'
                and (s['piece_a'] in selected or s['piece_b'] in selected)],
            unsupported_or_missing_partners=[{'id': s['id'], 'missing_piece_ids': sorted(
                {s['piece_a'], s['piece_b']}-selected)} for s in sorted(data['seams'], key=lambda s: s['id'])
                if s['id'] in external],
            ease_distribution=relaxation['ease_distribution'],
            numerical_anchor_edges=copy.deepcopy(numerical_anchor_edges),
            numerical_anchor_scope='SUBSEQUENT_NATIVE_METRIC_RECOVERY_ONLY_NOT_FIXED_DURING_GUIDE_GENERATION',
            source_seam_recipe=copy.deepcopy(seam_recipe),
            anatomical_attachments=attachment_bindings,
            anatomical_attachment_sha256=digest(anatomical_attachments),
            anatomical_attachment_scope='MEASURED_GUIDE_ATTACHMENT_PRESERVED_DURING_COUPLING_NOT_PHYSICAL_PIN',
            whole_piece_admission=False, source_rest_metric='IMMUTABLE_ORIGINAL_UV')
        for row in witnesses:
            row['declared_ease_b_over_a'] = seam_recipe['seams'][row['source_seam_id']]['ease_b_over_a']
            row['ease_distribution'] = relaxation['ease_distribution']
            row['max_proposed_control_gap_cm'] = row.pop('max_common_control_gap_cm')
    if observe_guide_stages:
        from .guide_stage_metrics import observe_guide_stages as observe
        report['guide_stage_metrics'] = observe(states, {
            'original_guide': original_proposals, 'role_rigid_seed': aligned_proposals,
            'seam_cohort_mean': targets}, budget, provenance={
                'source_sha256': report['source_sha256'], 'input_guide_sha256': report['input_guide_sha256'],
                'seam_recipe_sha256': report['seam_recipe_sha256'], 'source_binding_sha256': source_binding,
                'source_refs': {pid: frame['source_ref'] for pid, frame in sorted(frames.items())},
                'rigid_seed_applied': alignment_report is not None,
                'rigid_alignment_kernel_code_sha256': (alignment_report['kernel_code_sha256']
                    if alignment_report is not None else None)})
        if relaxation_report is not None:
            observed = report['guide_stage_metrics']
            observed['stage_order'][-1] = 'coupled_rest_metric_proposal'
            for row in observed['per_piece'].values():
                row['stages']['coupled_rest_metric_proposal'] = row['stages'].pop('seam_cohort_mean')
    try:
        report = json.loads(canonical(report))
    except (TypeError, ValueError, OverflowError) as error:
        raise StudioError('Source seam coupling diagnostics are not finite JSON evidence') from error
    budget.check()
    return cages, report
