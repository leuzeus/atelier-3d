"""Exact portable UV carriers. No production caller or 3D solver uses this API."""
import hashlib
import json
import math
import re
import time
from fractions import Fraction

from .core import StudioError


DISCRIMINANT = 'MATERIAL_SAMPLE_CARRIER_V1'
_DEFAULTS = {
    'max_source_vertices': 4000, 'max_source_triangles': 8000,
    'max_carrier_vertices': 4000, 'max_carrier_triangles': 8000,
    'max_samples': 10000, 'max_mark_owners': 20000,
    'max_relation_owners': 20000, 'max_pair_checks': 250000,
    'max_intersection_patches': 50000, 'max_input_nodes': 200000,
    'max_input_bytes': 8388608,
    'max_fraction_bits': 4096, 'max_seconds': 60.,
}
_HARD = {**_DEFAULTS, 'max_pair_checks': 2000000,
         'max_intersection_patches': 100000, 'max_input_nodes': 500000}


def _refuse(reason, detail):
    error = StudioError('Material sample carrier: ' + detail)
    error.reason = reason
    error.qualification = 'NONE'
    raise error


def _digest(value):
    try:
        return hashlib.sha256(json.dumps(value, sort_keys=True, ensure_ascii=False,
            allow_nan=False, separators=(',', ':')).encode('utf-8')).hexdigest()
    except (TypeError, ValueError, OverflowError, RecursionError):
        _refuse('INVALID_REFERENCE', 'references must contain bounded finite JSON data')


def _precheck(value, budgets):
    """Bound native JSON before serialization or any caller clock callback."""
    nodes = 0; size = 0
    node_limit = budgets.get('max_input_nodes', _DEFAULTS['max_input_nodes']) if type(budgets) is dict else _DEFAULTS['max_input_nodes']
    byte_limit = budgets.get('max_input_bytes', _DEFAULTS['max_input_bytes']) if type(budgets) is dict else _DEFAULTS['max_input_bytes']
    if type(node_limit) is not int or not 0 < node_limit <= _HARD['max_input_nodes'] or type(byte_limit) is not int or not 0 < byte_limit <= _HARD['max_input_bytes']:
        _refuse('INVALID_BUDGET', 'invalid input size budget')
    def visit(item, depth):
        nonlocal nodes, size
        nodes += 1; size += 8
        if nodes > node_limit or size > byte_limit:
            _refuse('BUDGET_EXHAUSTED', 'input representation budget exhausted')
        if depth > 32:
            _refuse('INVALID_REFERENCE', 'reference nesting is too deep')
        if type(item) is dict:
            for key, child in item.items():
                if type(key) is not str or len(key) > 128:
                    _refuse('INVALID_REFERENCE', 'invalid native reference key')
                size += 6*len(key)+3; visit(child, depth+1)
        elif type(item) is list:
            for child in item:
                visit(child, depth+1)
        elif type(item) is str and len(item) <= 2048:
            size += 6*len(item)+2
        elif type(item) is int and item.bit_length() <= 4096:
            size += len(str(item))
        elif type(item) is float and math.isfinite(item):
            size += len(repr(item))
        elif item is not None and type(item) is not bool:
            _refuse('INVALID_REFERENCE', 'only bounded finite native JSON references are accepted')
        if size > byte_limit:
            _refuse('BUDGET_EXHAUSTED', 'input representation budget exhausted')
    visit(value, 0)


class _Budget:
    def __init__(self, values, deadline, clock):
        if values is None:
            values = {}
        if type(values) is not dict or set(values) - set(_DEFAULTS):
            _refuse('INVALID_BUDGET', 'unknown or non-object budget')
        self.limits = {**_DEFAULTS, **values}
        for key, value in self.limits.items():
            valid_type = type(value) in (int, float) if key == 'max_seconds' else type(value) is int
            if not valid_type or not 0 < value <= _HARD[key] or not math.isfinite(value):
                _refuse('INVALID_BUDGET', 'invalid bounded value for ' + key)
        if not callable(clock):
            _refuse('INVALID_CLOCK', 'a monotone clock is required')
        if deadline is not None and (type(deadline) not in (int, float) or not math.isfinite(deadline)):
            _refuse('INVALID_DEADLINE', 'deadline must be an absolute finite time')
        self.clock = clock
        self.last = self.start = self.now()
        self.deadline = min(self.start + self.limits['max_seconds'], deadline) if deadline is not None else self.start + self.limits['max_seconds']
        self.counts = {}
        self.check('start')

    def now(self):
        try:
            value = self.clock()
        except Exception:
            _refuse('INVALID_CLOCK', 'clock failed while reading the deadline')
        if type(value) not in (int, float) or not math.isfinite(value):
            _refuse('INVALID_CLOCK', 'clock returned a nonfinite time')
        if hasattr(self, 'last') and value < self.last:
            _refuse('INVALID_CLOCK', 'clock moved backwards')
        self.last = value
        return value

    def check(self, phase):
        if self.now() >= self.deadline:
            _refuse('DEADLINE_EXHAUSTED', 'deadline exhausted during ' + phase)

    def take(self, key, count=1):
        self.check(key)
        used = self.counts.get(key, 0) + count
        if used > self.limits['max_' + key]:
            _refuse('BUDGET_EXHAUSTED', key + ' budget exhausted')
        self.counts[key] = used

    def available(self, key, count):
        if self.counts.get(key, 0) + count > self.limits['max_' + key]:
            _refuse('BUDGET_EXHAUSTED', key + ' work cannot fit the declared budget')


def _snapshot(value, budget, depth=0):
    budget.take('input_nodes')
    if depth > 32:
        _refuse('INVALID_REFERENCE', 'reference nesting is too deep')
    if type(value) is dict:
        if any(type(k) is not str or len(k) > 128 for k in value):
            _refuse('INVALID_REFERENCE', 'invalid reference key')
        return {k: _snapshot(v, budget, depth + 1) for k, v in value.items()}
    if type(value) is list:
        return [_snapshot(v, budget, depth + 1) for v in value]
    if value is None or type(value) is bool:
        return value
    if type(value) is str and len(value) <= 2048:
        return value
    if type(value) is int and value.bit_length() <= 4096:
        return value
    if type(value) is float and math.isfinite(value):
        return value
    _refuse('INVALID_REFERENCE', 'only bounded finite native JSON values are accepted')


def _fields(value, required, optional=()):
    if type(value) is not dict or set(value) - set(required) - set(optional) or set(required) - set(value):
        _refuse('INVALID_CONTRACT', 'missing or unknown explicit contract fields')


def _identity(value):
    if type(value) is not str or not value or len(value) > 128:
        _refuse('INVALID_IDENTITY', 'an explicit nonempty bounded identity is required')
    return value


def _number(value, budget):
    if type(value) in (int, float):
        if type(value) is float and not math.isfinite(value):
            _refuse('INVALID_NUMBER', 'nonfinite material number')
        result = Fraction(value)
    elif type(value) is str and re.fullmatch(r'-?(0|[1-9][0-9]*)(/[1-9][0-9]*)?', value):
        if len(value) > 2048:
            _refuse('INVALID_NUMBER', 'rational token is too large')
        result = Fraction(value)
        if str(result) != value:
            _refuse('INVALID_NUMBER', 'rational token must be canonical')
    else:
        _refuse('INVALID_NUMBER', 'numbers must be finite native numbers or canonical rational strings')
    if max(result.numerator.bit_length(), result.denominator.bit_length()) > budget.limits['max_fraction_bits']:
        _refuse('BUDGET_EXHAUSTED', 'rational precision budget exhausted')
    return result


def _cross(a, b, c):
    return (b[0]-a[0])*(c[1]-a[1]) - (b[1]-a[1])*(c[0]-a[0])


def _area(poly):
    return abs(sum(a[0]*b[1]-a[1]*b[0] for a, b in zip(poly, poly[1:]+poly[:1]))) / 2


def _bary(point, triangle):
    a, b, c = triangle
    determinant = _cross(a, b, c)
    return (_cross(point, b, c)/determinant,
            _cross(a, point, c)/determinant, _cross(a, b, point)/determinant)


def _clip(poly, triangle, budget):
    budget.check('exact clipping bounds')
    if poly:
        # Strict separation of exact coordinate intervals proves an empty
        # intersection without constructing any intermediate rational point.
        # Equality must still use clipping so tangent edges/vertices survive.
        for axis in range(2):
            if (max(p[axis] for p in poly) < min(p[axis] for p in triangle) or
                    max(p[axis] for p in triangle) < min(p[axis] for p in poly)):
                budget.check('exact clipping separated return')
                return []
    if _cross(*triangle) < 0:
        triangle = list(reversed(triangle))
    for a, b in zip(triangle, triangle[1:]+triangle[:1]):
        budget.check('exact clipping')
        if not poly:
            break
        next_poly = []
        for p, q in zip(poly, poly[1:]+poly[:1]):
            cp, cq = _cross(a, b, p), _cross(a, b, q)
            if cp >= 0:
                next_poly.append(p)
            if (cp < 0 <= cq) or (cq < 0 <= cp):
                ratio = cp/(cp-cq)
                next_poly.append(tuple(p[k]+ratio*(q[k]-p[k]) for k in range(2)))
        poly = []
        for p in next_poly:
            for number in p:
                if max(number.numerator.bit_length(), number.denominator.bit_length()) > budget.limits['max_fraction_bits']:
                    _refuse('BUDGET_EXHAUSTED', 'intersection precision budget exhausted')
            if not poly or p != poly[-1]:
                poly.append(p)
        if len(poly) > 1 and poly[-1] == poly[0]:
            poly.pop()
    budget.check('exact clipping return')
    return poly


def _encode(value, budget=None):
    if budget is not None:
        budget.check('exact receipt encoding')
    if isinstance(value, Fraction):
        if budget is not None and max(value.numerator.bit_length(), value.denominator.bit_length()) > budget.limits['max_fraction_bits']:
            _refuse('BUDGET_EXHAUSTED', 'output rational precision budget exhausted')
        return str(value)
    if type(value) in (tuple, list):
        return [_encode(v, budget) for v in value]
    if type(value) is dict:
        return {k: _encode(v, budget) for k, v in value.items()}
    return value


def _mesh(raw, label, budget):
    _fields(raw, ('id', 'uv_cm', 'triangles', 'vertex_ids', 'face_ids'), ('edges',))
    _identity(raw['id'])
    for key in ('uv_cm', 'triangles', 'vertex_ids', 'face_ids'):
        if type(raw[key]) is not list:
            _refuse('INVALID_MESH', 'mesh arrays must be explicit lists')
    budget.take(label + '_vertices', len(raw['uv_cm']))
    budget.take(label + '_triangles', len(raw['triangles']))
    if not raw['triangles'] or len(raw['uv_cm']) < 3 or len(raw['vertex_ids']) != len(raw['uv_cm']) or len(raw['face_ids']) != len(raw['triangles']):
        _refuse('INVALID_MESH', 'mesh identities and array counts differ')
    vertex_ids = [_identity(v) for v in raw['vertex_ids']]
    face_ids = [_identity(v) for v in raw['face_ids']]
    if len(set(vertex_ids)) != len(vertex_ids) or len(set(face_ids)) != len(face_ids):
        _refuse('IDENTITY_COLLISION', 'mesh identities collide within their namespace')
    points = []
    for p in raw['uv_cm']:
        budget.check('mesh coordinates')
        if type(p) is not list or len(p) != 2:
            _refuse('INVALID_MESH', 'UV points must have two coordinates')
        points.append(tuple(_number(v, budget) for v in p))
    if len(set(points)) != len(points):
        _refuse('AMBIGUOUS_MESH', 'distinct mesh vertices have exactly coincident UVs')
    faces = raw['triangles']
    seen = set(); edges = {}; orientation = None; used = set()
    for face_id, f in enumerate(faces):
        budget.check('mesh topology')
        if type(f) is not list or len(f) != 3 or any(type(i) is not int or not 0 <= i < len(points) for i in f) or len(set(f)) != 3:
            _refuse('INVALID_MESH', 'triangles require three distinct actual vertex indices')
        key = tuple(sorted(f))
        if key in seen:
            _refuse('OVERLAP', 'duplicate material triangle')
        seen.add(key); used.update(f)
        determinant = _cross(*(points[i] for i in f))
        if determinant == 0:
            _refuse('DEGENERATE_MESH', 'zero area triangle')
        sign = 1 if determinant > 0 else -1
        if orientation is not None and orientation != sign:
            _refuse('WINDING', 'inconsistent mesh winding')
        orientation = sign
        for a, b in zip(f, f[1:]+f[:1]):
            edges.setdefault(tuple(sorted((a, b))), []).append((face_id, a, b))
    if used != set(range(len(points))):
        _refuse('INVALID_MESH', 'unused mesh vertices are not a carrier identity')
    adjacency = {i: set() for i in range(len(faces))}
    for uses in edges.values():
        budget.check('edge manifold')
        if len(uses) > 2 or (len(uses) == 2 and uses[0][1:] != tuple(reversed(uses[1][1:]))):
            _refuse('NONMANIFOLD', 'edge ownership or direction is invalid')
        if len(uses) == 2:
            adjacency[uses[0][0]].add(uses[1][0]); adjacency[uses[1][0]].add(uses[0][0])
    reached = set(); pending = [0]
    while pending:
        budget.check('connected domain')
        i = pending.pop()
        if i not in reached:
            reached.add(i); pending.extend(adjacency[i]-reached)
    boundary = {edge for edge, uses in edges.items() if len(uses) == 1}
    degrees = {}
    for a, b in boundary:
        degrees[a] = degrees.get(a, 0)+1; degrees[b] = degrees.get(b, 0)+1
    if len(reached) != len(faces) or len(points)-len(edges)+len(faces) != 1 or not degrees or any(n != 2 for n in degrees.values()):
        _refuse('NONMANIFOLD', 'this local contract requires one complete manifold material disk')
    triangles = [[points[i] for i in f] for f in faces]
    for i, a in enumerate(triangles):
        for j in range(i+1, len(triangles)):
            budget.take('pair_checks')
            intersection = _clip(a, triangles[j], budget)
            if intersection and _area(intersection):
                _refuse('OVERLAP', 'triangles overlap in positive area')
            shared = set(faces[i]) & set(faces[j])
            if intersection and (not shared or any(not _on_segment(p, points[min(shared)], points[max(shared)]) for p in intersection)):
                _refuse('AMBIGUOUS_MESH', 'nonconforming triangle contact')
    edge_names = raw.get('edges', {})
    if type(edge_names) is not dict:
        _refuse('INVALID_MESH', 'named boundaries must be explicit')
    lookup = {v: i for i, v in enumerate(vertex_ids)}
    for name, chain in edge_names.items():
        budget.check('named boundaries')
        _identity(name)
        if type(chain) is not list or len(chain) < 2 or any(type(v) is not str or v not in lookup for v in chain) or len(set(chain)) != len(chain):
            _refuse('INVALID_BOUNDARY', 'named boundary has missing or repeated identities')
        for a, b in zip(chain, chain[1:]):
            budget.check('named boundary segments')
            if tuple(sorted((lookup[a], lookup[b]))) not in boundary:
                _refuse('INVALID_BOUNDARY', 'named edge does not follow actual material boundary')
    return {'raw': raw, 'points': points, 'faces': faces, 'triangles': triangles,
            'orientation': orientation, 'vertex_lookup': lookup,
            'face_lookup': {v: i for i, v in enumerate(face_ids)}}


def _on_segment(p, a, b):
    return _cross(a, b, p) == 0 and all(min(a[k], b[k]) <= p[k] <= max(a[k], b[k]) for k in range(2))


def _support(point, mesh, budget):
    rows = []
    for index, triangle in enumerate(mesh['triangles']):
        budget.take('pair_checks')
        weights = _bary(point, triangle)
        if min(weights) >= 0:
            row = tuple(sorted((mesh['raw']['vertex_ids'][v], w) for v, w in zip(mesh['faces'][index], weights) if w))
            rows.append((index, weights, row))
    if not rows:
        _refuse('OUTSIDE_DOMAIN', 'sample lies outside the supplied carrier')
    if any(row != rows[0][2] for _, _, row in rows[1:]):
        _refuse('AMBIGUOUS_SUPPORT', 'candidate carrier faces give different interpolation rows')
    rows.sort(key=lambda row: mesh['raw']['face_ids'][row[0]])
    index, weights, sparse = rows[0]
    return {'carrier_face_id': mesh['raw']['face_ids'][index],
            'carrier_vertex_ids': [mesh['raw']['vertex_ids'][i] for i in mesh['faces'][index]],
            'barycentric_weights': weights, 'sparse_vertex_weights': dict(sparse),
            'equivalent_carrier_face_ids': sorted(mesh['raw']['face_ids'][i] for i, _, _ in rows)}


def _fraction(value, budget):
    result = _number(value, budget)
    if not 0 <= result <= 1:
        _refuse('INVALID_PARAMETER', 'material fraction is outside [0, 1]')
    return result


def _walk(point, mesh, edge, budget, reverse=False):
    chain = mesh['raw'].get('edges', {}).get(edge)
    if chain is None:
        _refuse('INVALID_BOUNDARY', 'relation names an absent local edge')
    chain = list(reversed(chain)) if reverse else chain
    rows = []
    for ordinal, (a, b) in enumerate(zip(chain, chain[1:])):
        budget.check('source boundary support')
        p, q = mesh['points'][mesh['vertex_lookup'][a]], mesh['points'][mesh['vertex_lookup'][b]]
        if _on_segment(point, p, q):
            axis = 0 if p[0] != q[0] else 1
            rows.append(Fraction(ordinal)+(point[axis]-p[axis])/(q[axis]-p[axis]))
    if not rows or any(row != rows[0] for row in rows[1:]):
        _refuse('INVALID_BOUNDARY', 'sample has no unambiguous declared edge support')
    return rows[0], len(chain)-1


def _relations(raw, marks, samples, mesh, budget):
    if type(raw) is not list or type(marks) is not list:
        _refuse('INVALID_CONTRACT', 'relations and marks must be explicit arrays')
    relation_map = {}; occupied = set(); external = []
    for relation in raw:
        budget.check('relations')
        _fields(relation, ('id', 'kind', 'orientation', 'owners'))
        identity = _identity(relation['id'])
        if identity in relation_map:
            _refuse('IDENTITY_COLLISION', 'relation identities collide')
        relation_map[identity] = relation
        if relation['kind'] not in ('permanent', 'closure', 'detachable') or relation['orientation'] not in ('forward', 'reverse') or type(relation['owners']) is not list or len(relation['owners']) != 2:
            _refuse('INVALID_RELATION', 'two explicit owners, kind and orientation are required')
        partitions = []
        for side, owner in enumerate(relation['owners']):
            _fields(owner, ('source_id', 'edge_id', 'samples'), ('source_sha256', 'source_vertex_ids'))
            _identity(owner['source_id']); _identity(owner['edge_id'])
            if type(owner['samples']) is not list or len(owner['samples']) < 2:
                _refuse('INVALID_RELATION', 'each owner requires its explicit endpoint partition')
            budget.take('relation_owners', len(owner['samples']))
            local = owner['source_id'] == mesh['raw']['id']
            if local and ('source_sha256' in owner or 'source_vertex_ids' in owner):
                _refuse('INVALID_RELATION', 'local owner uses the actual source, not an external alias')
            if not local:
                if type(owner.get('source_sha256')) is not str or not re.fullmatch('[0-9a-f]{64}', owner['source_sha256']) or type(owner.get('source_vertex_ids')) is not list or len(owner['source_vertex_ids']) < 2:
                    _refuse('INVALID_EXTERNAL_REFERENCE', 'external owner needs source hash and explicit source vertex chain')
                ids = [_identity(v) for v in owner['source_vertex_ids']]
                if len(set(ids)) != len(ids):
                    _refuse('IDENTITY_COLLISION', 'external source vertex identities collide')
                external.append({'relation_id': identity, 'owner_index': side,
                    'source_id': owner['source_id'], 'source_sha256': owner['source_sha256'],
                    'status': 'BOUNDED_SOURCE_REFERENCE_ONLY', 'geometry_checked': False, 'equality_3d_checked': False})
                traversal = list(reversed(ids)) if side == 1 and relation['orientation'] == 'reverse' else ids
            fractions = []; used = set(); positions = []
            for entry in owner['samples']:
                budget.check('relation sample support')
                _fields(entry, ('sample_id', 'fraction'), () if local else ('source_segment_vertex_ids', 'source_segment_parameter'))
                sid = _identity(entry['sample_id'])
                if sid in used:
                    _refuse('IDENTITY_COLLISION', 'owner repeats a material sample identity')
                used.add(sid); fractions.append(_fraction(entry['fraction'], budget))
                if local:
                    if sid not in samples:
                        _refuse('INVALID_RELATION', 'local relation names an absent sample')
                    positions.append(_walk(samples[sid]['point'], mesh, owner['edge_id'], budget, side == 1 and relation['orientation'] == 'reverse'))
                else:
                    segment = entry.get('source_segment_vertex_ids')
                    segments = [traversal[i:i+2] for i in range(len(traversal)-1)]
                    if type(segment) is not list or len(segment) != 2 or segment not in segments:
                        _refuse('INVALID_EXTERNAL_REFERENCE', 'external segment must follow its declared chain')
                    positions.append((Fraction(segments.index(segment)) + _fraction(entry.get('source_segment_parameter'), budget), len(traversal)-1))
            if fractions[0] != 0 or fractions[-1] != 1 or any(a >= b for a, b in zip(fractions, fractions[1:])):
                _refuse('INVALID_PARAMETER', 'owner fractions must be strictly increasing from 0 to 1')
            if positions[0][0] != 0 or positions[-1][0] != positions[-1][1] or any(a[0] >= b[0] for a, b in zip(positions, positions[1:])):
                _refuse('INVALID_RELATION', 'sample order contradicts the explicit named boundary orientation')
            if local:
                if relation['kind'] == 'permanent':
                    chain = mesh['raw']['edges'][owner['edge_id']]
                    edges = {tuple(sorted((a, b))) for a, b in zip(chain, chain[1:])}
                    if occupied & edges:
                        _refuse('AMBIGUOUS_RELATION', 'local boundary assigned to multiple permanent relations')
                    occupied.update(edges)
            partitions.append(fractions)
        if partitions[0] != partitions[1]:
            _refuse('INVALID_RELATION', 'paired fractions differ; this builder invents no partition')
    mark_ids = set()
    for mark in marks:
        budget.check('assembly marks')
        _fields(mark, ('id', 'relation_id', 'fraction', 'symbol', 'owners'))
        _identity(mark['relation_id'])
        identity = _identity(mark['id'])
        if identity in mark_ids:
            _refuse('IDENTITY_COLLISION', 'mark identities collide')
        mark_ids.add(identity)
        if mark['relation_id'] not in relation_map or mark['symbol'] not in ('notch', 'double-notch') or type(mark['owners']) is not list or not mark['owners']:
            _refuse('INVALID_MARK', 'mark needs an actual relation, symbol and owners')
        _fraction(mark['fraction'], budget)
        budget.take('mark_owners', len(mark['owners']))
        used = set()
        for owner in mark['owners']:
            budget.check('assembly mark support')
            _fields(owner, ('owner_index', 'sample_id'))
            side = owner['owner_index']; sid = _identity(owner['sample_id'])
            if type(side) is not int or side not in (0, 1) or side in used:
                _refuse('INVALID_MARK', 'mark owner is repeated or invalid')
            used.add(side)
            relation_owner = relation_map[mark['relation_id']]['owners'][side]
            if relation_owner['source_id'] != mesh['raw']['id'] or sid not in samples:
                _refuse('INVALID_MARK', 'this local mark contract requires a supplied local material sample')
            _walk(samples[sid]['point'], mesh, relation_owner['edge_id'], budget)
    return external


def _build(source, carrier, samples, marks, relations, budget):
    if type(samples) is not list:
        _refuse('INVALID_CONTRACT', 'material samples must be an explicit array')
    budget.take('samples', len(samples))
    for raw in (source, carrier):
        if type(raw) is not dict or type(raw.get('triangles')) is not list:
            _refuse('INVALID_MESH', 'source and carrier must have explicit triangles')
    ns, nc = len(source['triangles']), len(carrier['triangles'])
    vertices = len(source.get('uv_cm', [])) if type(source.get('uv_cm')) is list else 0
    budget.available('pair_checks', ns*(ns-1)//2 + nc*(nc-1)//2 + ns*nc + (vertices+len(samples))*nc)
    sm = _mesh(source, 'source', budget); cm = _mesh(carrier, 'carrier', budget)
    if sm['orientation'] != cm['orientation']:
        _refuse('WINDING', 'carrier winding differs from the source')
    source_area = [Fraction(0) for _ in sm['faces']]
    carrier_area = [Fraction(0) for _ in cm['faces']]
    patches = []
    for i, a in enumerate(sm['triangles']):
        for j, b in enumerate(cm['triangles']):
            budget.take('pair_checks'); poly = _clip(a, b, budget)
            if len(poly) < 3 or not _area(poly):
                continue
            budget.take('intersection_patches'); ar = _area(poly)
            source_area[i] += ar; carrier_area[j] += ar
            patches.append({'source_face_id': source['face_ids'][i], 'carrier_face_id': carrier['face_ids'][j],
                'uv_polygon_cm': poly, 'area_cm2': ar,
                'source_vertex_ids': [source['vertex_ids'][v] for v in sm['faces'][i]],
                'carrier_vertex_ids': [carrier['vertex_ids'][v] for v in cm['faces'][j]],
                'source_barycentric_weights': [_bary(p, a) for p in poly],
                'carrier_barycentric_weights': [_bary(p, b) for p in poly]})
    if any(a != _area(t) for a, t in zip(source_area, sm['triangles'])) or any(a != _area(t) for a, t in zip(carrier_area, cm['triangles'])):
        _refuse('DOMAIN_COVERAGE', 'source and carrier do not cover exactly the same material domain once')
    original_vertices = [{'source_vertex_id': identity, 'uv_cm': point,
        'support': _support(point, cm, budget)} for identity, point in zip(source['vertex_ids'], sm['points'])]
    sample_map = {}; sample_records = []
    for sample in samples:
        budget.check('material samples')
        _fields(sample, ('id', 'source_face_id', 'source_barycentric_weights'), ('source_vertex_id', 'metadata'))
        identity = _identity(sample['id'])
        if identity in sample_map:
            _refuse('IDENTITY_COLLISION', 'material sample identities collide')
        if type(sample['source_face_id']) is not str or sample['source_face_id'] not in sm['face_lookup'] or type(sample['source_barycentric_weights']) is not list or len(sample['source_barycentric_weights']) != 3:
            _refuse('INVALID_SOURCE_SUPPORT', 'sample needs an explicit actual source triangle and three weights')
        weights = tuple(_fraction(v, budget) for v in sample['source_barycentric_weights'])
        if sum(weights) != 1:
            _refuse('INVALID_SOURCE_SUPPORT', 'source barycentric weights must sum exactly to one')
        i = sm['face_lookup'][sample['source_face_id']]
        triangle = sm['triangles'][i]
        point = tuple(sum(w*p[k] for w, p in zip(weights, triangle)) for k in range(2))
        if 'source_vertex_id' in sample:
            vertex = sample['source_vertex_id']
            if type(vertex) is not str or vertex not in sm['vertex_lookup'] or sm['points'][sm['vertex_lookup'][vertex]] != point:
                _refuse('INVALID_SOURCE_SUPPORT', 'sample vertex identity disagrees with its exact UV')
        sample_map[identity] = {'point': point}
        sample_records.append({'id': identity, 'source_identity': sample,
            'exact_uv_cm': point, 'carrier_support': _support(point, cm, budget)})
    external = _relations(relations, marks, sample_map, sm, budget)
    budget.check('final exact qualification')
    return {'discriminant': DISCRIMINANT, 'version': 1, 'purpose': 'TEST_ONLY', 'qualification': 'NONE',
        'uv_qualification': 'EXACT_DOMAIN_COVERAGE_AND_SAMPLE_SUPPORT',
        'source': source, 'carrier': carrier, 'source_vertex_bindings': original_vertices,
        'samples': sample_records, 'assembly_marks': marks, 'relations': relations,
        'source_carrier_intersections': sorted(patches, key=lambda p: (p['source_face_id'], p['carrier_face_id'])),
        'external_source_references': external,
        'normalized_arc_measurement': 'DECLARED_FRACTIONS_ONLY_NOT_MEASURED',
        'field_3d_representability': 'NOT_QUALIFIED_SOURCE_BREAKS_MAY_CROSS_CARRIER_FACES',
        'constraints_3d': 'NOT_QUALIFIED', 'physical_mesh': False, 'is_installable': False}


def build_material_sample_carrier(source, carrier, samples, *, marks=None, relations=None,
        budgets=None, deadline=None, clock=time.monotonic):
    """Validate a supplied local carrier without modifying source or admitting 3D.

    Numeric floats are interpreted as their exact binary64 rational values.
    A sample is defined by an existing source face and exact barycentric row.
    Source corners automatically retain explicit carrier bindings. No nearest
    search, spatial weld, coordinate rounding or relation inference occurs.
    """
    marks = [] if marks is None else marks
    relations = [] if relations is None else relations
    originals = [source, carrier, samples, marks, relations, budgets, deadline]
    _precheck(originals, budgets)
    before = _digest(originals)
    budget = _Budget(budgets, deadline, clock)
    snapshots = _snapshot([source, carrier, samples, marks, relations], budget)
    if _digest(originals) != before:
        _refuse('REFERENCE_MUTATION', 'an input reference changed while snapshotting')
    result = _build(*snapshots, budget)
    budget.check('reference preservation')
    if _digest(originals) != before:
        _refuse('REFERENCE_MUTATION', 'an input reference changed during construction')
    encoded = _encode(result, budget)
    encoded['receipt'] = {'purpose': 'TEST_ONLY', 'qualification': 'NONE',
        'input_sha256': before, 'source_sha256': _digest(source), 'carrier_sha256': _digest(carrier),
        'content_sha256': _digest(encoded), 'budgets': budget.limits, 'work': budget.counts,
        'elapsed_seconds': budget.now()-budget.start, 'deadline': budget.deadline,
        'inputs_preserved': True, 'source_uv_rounded': False, 'identities_merged': False,
        'equality_3d_checked': False, 'source_material_3d_qualified': False}
    budget.check('return')
    if _digest(originals) != before:
        _refuse('REFERENCE_MUTATION', 'an input reference changed before return')
    return encoded


def build_rectangular_material_carrier(source, corner_vertex_ids, *, columns, rows,
        budgets=None, deadline=None, clock=time.monotonic):
    """Generate a TEST_ONLY grid only after exact rectangle and domain proofs."""
    originals = [source, corner_vertex_ids, columns, rows, budgets, deadline]
    _precheck(originals, budgets)
    before = _digest(originals)
    budget = _Budget(budgets, deadline, clock)
    source, corners = _snapshot([source, corner_vertex_ids], budget)
    if _digest(originals) != before:
        _refuse('REFERENCE_MUTATION', 'an input reference changed while snapshotting')
    if type(corners) is not list or len(corners) != 4 or any(type(v) is not str for v in corners) or len(set(corners)) != 4 or type(columns) is not int or type(rows) is not int or min(columns, rows) < 1:
        _refuse('INVALID_RECTANGLE', 'four ordered actual corners and positive integer subdivisions are required')
    if type(source) is not dict or type(source.get('vertex_ids')) is not list or type(source.get('uv_cm')) is not list:
        _refuse('INVALID_RECTANGLE', 'explicit source identities and UVs are required')
    identities = [_identity(v) for v in source['vertex_ids']]
    if len(set(identities)) != len(identities) or len(source['uv_cm']) != len(identities):
        _refuse('IDENTITY_COLLISION', 'source rectangle identities collide or counts differ')
    _identity(source.get('id'))
    if any(type(p) is not list or len(p) != 2 for p in source['uv_cm']):
        _refuse('INVALID_RECTANGLE', 'source rectangle needs explicit two-dimensional UVs')
    lookup = {v: i for i, v in enumerate(identities)}
    if any(c not in lookup for c in corners):
        _refuse('INVALID_RECTANGLE', 'rectangle corners must be actual source vertex identities')
    points = [tuple(_number(v, budget) for v in source['uv_cm'][lookup[c]]) for c in corners]
    a, b, c, d = points
    u = tuple(b[k]-a[k] for k in range(2)); v = tuple(d[k]-a[k] for k in range(2))
    if sum(u[k]*v[k] for k in range(2)) != 0 or c != tuple(a[k]+u[k]+v[k] for k in range(2)) or _cross(a, b, d) == 0:
        _refuse('INVALID_RECTANGLE', 'supplied corners are not an exact nondegenerate rectangle')
    budget.available('carrier_vertices', (columns+1)*(rows+1))
    budget.available('carrier_triangles', 2*columns*rows)
    uv = []; vertices = []; faces = []
    for row in range(rows+1):
        for col in range(columns+1):
            budget.check('rectangle generation')
            uv.append([str(a[k]+Fraction(col, columns)*u[k]+Fraction(row, rows)*v[k]) for k in range(2)])
            vertices.append('grid:' + str(col) + ':' + str(row))
    for row in range(rows):
        for col in range(columns):
            budget.check('rectangle generation')
            i = row*(columns+1)+col
            faces.extend([[i, i+1, i+columns+2], [i, i+columns+2, i+columns+1]])
    carrier = {'id': 'rectangular-test:' + _digest(source)[:32], 'uv_cm': uv,
        'triangles': faces, 'vertex_ids': vertices, 'face_ids': ['grid-face:' + str(i) for i in range(len(faces))]}
    result = _build(source, carrier, [], [], [], budget)
    result['rectangle_parameters'] = {'corner_vertex_ids': corners, 'columns': columns, 'rows': rows,
        'rectangle_verified_exactly': True, 'source_domain_verified_exactly': True}
    encoded = _encode(result, budget)
    budget.check('rectangle reference preservation')
    if _digest(originals) != before:
        _refuse('REFERENCE_MUTATION', 'an input reference changed during rectangle construction')
    encoded['receipt'] = {'purpose': 'TEST_ONLY', 'qualification': 'NONE', 'input_sha256': before,
        'content_sha256': _digest(encoded), 'budgets': budget.limits, 'work': budget.counts,
        'elapsed_seconds': budget.now()-budget.start, 'deadline': budget.deadline,
        'inputs_preserved': True, 'equality_3d_checked': False, 'source_material_3d_qualified': False}
    budget.check('rectangle return')
    if _digest(originals) != before:
        _refuse('REFERENCE_MUTATION', 'an input reference changed before rectangle return')
    return encoded
