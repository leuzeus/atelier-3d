"""Unselected opening hypotheses on an exact source body interface.

The sagittal plane is declared by the body frame. Intersections use exact
rational arithmetic on its input floats, never a spatial-nearest search.
Neighbour pairs follow source cycle order. No geometry, grading, anatomical
review, closure, numeric ease or fitting decision is changed here.
"""
import copy
import html
import math
import time
from fractions import Fraction

from .core import StudioError, canonical, digest, ident


MAX_VERTICES = 250000
MAX_FACES = 250000
MAX_FACE_EDGES = 1500000
MAX_PATH_VERTICES = 10000


def validate_opening_options(options):
    keys = {'path_id', 'reference_plane', 'front_anchor', 'max_pairs', 'max_seconds', 'max_output_bytes'}
    if not isinstance(options, dict) or set(options) != keys:
        raise StudioError('Opening exploration requires its six explicit bounded options')
    ident(options['path_id'])
    if options['reference_plane'] != 'BODY_SAGITTAL' or options['front_anchor'] != 'UNIQUE_FRONTMOST_INTERSECTION':
        raise StudioError('Opening exploration requires the declared body sagittal plane and unique frontal intersection')
    if type(options['max_pairs']) is not int or not 1 <= options['max_pairs'] <= 32:
        raise StudioError('Opening exploration max_pairs must be an integer from 1 to 32')
    seconds = options['max_seconds']
    if type(seconds) not in (int, float) or not math.isfinite(seconds) or not 0 < seconds <= 60:
        raise StudioError('Opening exploration time budget must be finite, positive and at most 60 seconds')
    size = options['max_output_bytes']
    if type(size) is not int or not 1 <= size <= 32*1024*1024:
        raise StudioError('Opening exploration output byte budget is unsupported')
    return options


class _Budget:
    def __init__(self, options, callback):
        validate_opening_options(options)
        if callback is not None and not callable(callback):
            raise StudioError('Opening exploration parent budget check must be callable')
        self.options = options; self.callback = callback
        self.started = self.last = time.monotonic()
        if not math.isfinite(self.started):
            raise StudioError('Opening exploration initial clock is not finite')
        self.check()

    def check(self):
        if self.callback is not None: self.callback()
        now = time.monotonic()
        if not math.isfinite(now) or now < self.last or now-self.started > self.options['max_seconds']:
            raise StudioError('Opening exploration time budget exceeded or clock moved backwards')
        self.last = now

    def size(self, document):
        self.check()
        if len(canonical(document)) > self.options['max_output_bytes']:
            raise StudioError('Opening exploration output byte budget exceeded')
        self.check()


def _point(point):
    try:
        return isinstance(point, (list, tuple)) and len(point) == 3 and all(
            type(x) in (int, float) and math.isfinite(x) for x in point)
    except OverflowError:
        return False


def _dot(a, b):
    return math.fsum(x*y for x, y in zip(a, b))


def _frame(profile):
    frame = profile.get('frame', {})
    if set(frame) != {'origin_cm', 'right', 'forward', 'up'} or any(not _point(p) for p in frame.values()):
        raise StudioError('Opening exploration requires the exact finite declared body frame')
    axes = [frame[name] for name in ('right', 'forward', 'up')]
    if any(abs(_dot(a, b)-float(i == j)) > 1e-7 for i, a in enumerate(axes) for j, b in enumerate(axes)):
        raise StudioError('Opening exploration body frame is not orthonormal')
    return frame


def _exact_coordinate(point, frame, axis):
    return sum((Fraction(x)-Fraction(o))*Fraction(a)
               for x, o, a in zip(point, frame['origin_cm'], frame[axis]))


def _source_cycle(profile, geometry, path, options, budget):
    if not isinstance(profile, dict) or not isinstance(geometry, dict) or not isinstance(path, dict):
        raise StudioError('Opening exploration needs its exact source body and path documents')
    frame = _frame(profile)
    vertices, faces, labels = (geometry.get(k) for k in ('vertices_cm', 'faces', 'face_sets'))
    if (not isinstance(vertices, list) or not 3 <= len(vertices) <= MAX_VERTICES or
            not isinstance(faces, list) or not 2 <= len(faces) <= MAX_FACES or
            not isinstance(labels, list) or len(labels) != len(faces)):
        raise StudioError('Opening exploration geometry exceeds its structural limits or lacks source regions')
    for index, point in enumerate(vertices):
        if index % 256 == 0: budget.check()
        if not _point(point): raise StudioError('Opening exploration requires finite world-centimetre vertices')
    if (profile.get('geometry_sha256') != digest([vertices, faces]) or
            any(profile.get(k) != geometry.get(k) for k in ('source_sha256', 'pose_sha256'))):
        raise StudioError('Opening exploration profile belongs to another actual geometry, source or pose')
    for key in ('source_sha256', 'pose_sha256'):
        value = geometry.get(key)
        if not isinstance(value, str) or len(value) != 64 or any(c not in '0123456789abcdef' for c in value):
            raise StudioError('Opening exploration source and pose identities are invalid')
    ids = path.get('vertex_ids'); regions = path.get('source_regions')
    if (path.get('id') != options['path_id'] or path.get('closed') is not True or
            path.get('measurement_kind') != 'SOURCE_REGION_BOUNDARY_LENGTH' or
            not isinstance(ids, list) or not 3 <= len(ids) <= MAX_PATH_VERTICES or
            any(type(i) is not int or not 0 <= i < len(vertices) for i in ids) or len(set(ids)) != len(ids) or
            not isinstance(regions, list) or len(regions) != 2 or any(type(x) is not int for x in regions) or
            regions[0] == regions[1]):
        raise StudioError('Opening exploration needs one bounded exact closed source-region path')
    edges = list(zip(ids, ids[1:]+ids[:1])); keys = {tuple(sorted(edge)) for edge in edges}
    if path.get('edge_vertex_ids') != [list(edge) for edge in edges] or path.get('curve_world_cm') != [vertices[i] for i in ids]:
        raise StudioError('Opening exploration path points or edge provenance differ from its actual source vertices')
    if type(path.get('length_cm')) not in (int, float) or not math.isfinite(path['length_cm']):
        raise StudioError('Opening exploration source length is not finite')
    budget.size(path)
    incidence = {key: [] for key in keys}; count = 0
    for face_id, (face, label) in enumerate(zip(faces, labels)):
        budget.check()
        if (not isinstance(face, list) or len(face) < 3 or any(type(i) is not int or not 0 <= i < len(vertices) for i in face)
                or len(set(face)) != len(face) or type(label) is not int):
            raise StudioError('Opening exploration native face or region identity is invalid')
        count += len(face)
        if count > MAX_FACE_EDGES: raise StudioError('Opening exploration face-edge structural budget exceeded')
        for a, b in zip(face, face[1:]+face[:1]):
            key = tuple(sorted((a, b)))
            if key in incidence: incidence[key].append((face_id, label, a, b))
    source_faces = path.get('edge_source_face_ids')
    if not isinstance(source_faces, list) or len(source_faces) != len(edges):
        raise StudioError('Opening exploration source interface face witnesses are incomplete')
    for edge, witness in zip(edges, source_faces):
        budget.check(); owners = incidence[tuple(sorted(edge))]
        if (len(owners) != 2 or {item[1] for item in owners} != set(regions) or
                owners[0][2:] != tuple(reversed(owners[1][2:])) or
                witness != sorted(item[0] for item in owners) or math.dist(vertices[edge[0]], vertices[edge[1]]) == 0):
            raise StudioError('Opening exploration has an unreal, collapsed or nonmanifold source interface edge')
    total = math.fsum(math.dist(vertices[a], vertices[b]) for a, b in edges)
    if total != path['length_cm']: raise StudioError('Opening exploration length differs from its actual source-edge sum')
    # Canonicalize by source identity, not position, so a cyclic permutation or
    # reversed input order produces the same hypotheses and source selectors.
    start = ids.index(min(ids)); forward = ids[start:]+ids[:start]
    reverse = [forward[0]]+list(reversed(forward[1:]))
    ordered = forward if forward[1] < reverse[1] else reverse
    budget.check()
    return frame, vertices, ordered, total


def _intersections(frame, vertices, ids, budget):
    positions = [_exact_coordinate(vertices[i], frame, 'right') for i in ids]
    hits = []; n = len(ids)
    for index, value in enumerate(positions):
        budget.check(); following = (index+1)%n
        if value == 0:
            previous, after = positions[(index-1)%n], positions[following]
            if previous == 0 or after == 0:
                raise StudioError('Sagittal plane contains a source interface edge; frontal anchor is ambiguous')
            if previous*after >= 0:
                raise StudioError('Sagittal plane is tangent at a source vertex; frontal anchor is ambiguous')
            point = [Fraction(x) for x in vertices[ids[index]]]
            hits.append({'selector': {'kind': 'SOURCE_VERTEX', 'vertex_id': ids[index]},
                         'point': point, 'position': Fraction(index)})
        elif value*positions[following] < 0:
            t = value/(value-positions[following]); a, b = vertices[ids[index]], vertices[ids[following]]
            point = [Fraction(x)+t*(Fraction(y)-Fraction(x)) for x, y in zip(a, b)]
            hits.append({'selector': {'kind': 'SOURCE_EDGE_FRACTION', 'edge_vertex_ids': [ids[index], ids[following]],
                                     'fraction': float(t), 'fraction_exact': [t.numerator, t.denominator]},
                         'point': point, 'position': Fraction(index)+t})
    if len(hits) != 2: raise StudioError('Sagittal source interface needs exactly two unambiguous crossings')
    scores = [_exact_coordinate(hit['point'], frame, 'forward') for hit in hits]
    if scores[0] == scores[1]: raise StudioError('Source sagittal crossings tie for frontmost; no anchor is inferred')
    order = sorted(range(2), key=lambda i: scores[i], reverse=True)
    for hit in hits: hit['world_cm'] = [float(x) for x in hit['point']]
    return hits[order[0]], hits[order[1]]


def _arc(ids, start, steps, vertices, budget):
    ordered = []
    for offset in range(steps+1):
        if offset % 256 == 0: budget.check()
        ordered.append(ids[(start+offset)%len(ids)])
    return {'vertex_ids': ordered, 'length_cm': math.fsum(math.dist(vertices[a], vertices[b])
                                                        for a, b in zip(ordered, ordered[1:]))}


def prepare_opening_candidates(profile, geometry, path, options, *, budget_check=None):
    """Return unselected local-front source hypotheses, never a styling choice."""
    budget = _Budget(options, budget_check)
    try: before = digest([profile, geometry, path, options])
    except (ValueError, TypeError, RecursionError) as error:
        raise StudioError('Opening exploration inputs must be finite canonical documents') from error
    frame, vertices, ids, total = _source_cycle(profile, geometry, path, options, budget)
    front, rear = _intersections(frame, vertices, ids, budget); n = len(ids)
    position = front['position']; integer = position.numerator//position.denominator
    vertex_hit = position.denominator == 1
    before_index, after_index = (integer-1, integer+1) if vertex_hit else (integer, integer+1)
    candidates = []; stop_reason = 'PAIR_BUDGET_REACHED'
    for k in range(1, options['max_pairs']+1):
        budget.check(); start = (before_index-(k-1))%n; steps = (2*k if vertex_hit else 2*k-1)
        if steps >= n:
            stop_reason = 'SOURCE_CYCLE_CAPACITY_REACHED'; break
        if (rear['position']-start)%n <= steps:
            stop_reason = 'REAR_INTERSECTION_REACHED'; break
        end = (start+steps)%n
        omitted = _arc(ids, start, steps, vertices, budget)
        remaining = _arc(ids, end, n-steps, vertices, budget)
        candidates.append({'id': path['id']+'.opening-hypothesis.'+str(k), 'topological_pair_index': k,
            'endpoints': [{'selector': {'kind': 'SOURCE_VERTEX', 'vertex_id': ids[i]},
                           'world_cm': copy.deepcopy(vertices[ids[i]])} for i in (start, end)],
            'front_omitted_arc': omitted, 'remaining_arc': remaining,
            'source_closed_reference_length_cm': total,
            'length_partition_residual_cm': math.fsum([omitted['length_cm'], remaining['length_cm'], -total]),
            'selection': 'NONE', 'opening_review': 'REQUIRED', 'ease_cm': None,
            'garment_correspondence': 'NOT_PREPARED', 'acceptance': 'NONE'})
        budget.size(candidates)
    if not candidates: raise StudioError('No distinct front-side source endpoint pair exists before the rear crossing')
    result = {'version': 1, 'status': 'BODY_PATH_OPENING_HYPOTHESES_PROPOSED',
        'purpose': 'VISUAL_REVIEW_ONLY', 'source_path': copy.deepcopy(path),
        'identity': {'profile_sha256': digest(profile), 'geometry_sha256': digest([geometry['vertices_cm'], geometry['faces']]),
                     'source_sha256': geometry['source_sha256'], 'pose_sha256': geometry['pose_sha256']},
        'reference_plane': {'kind': 'BODY_SAGITTAL', 'origin_world_cm': copy.deepcopy(frame['origin_cm']),
                            'normal_world': copy.deepcopy(frame['right']),
                            'arithmetic': 'EXACT_RATIONAL_INTERSECTION_OF_INPUT_FLOATS'},
        'front_anchor': {'selector': front['selector'], 'world_cm': front['world_cm']},
        'rear_intersection': {'selector': rear['selector'], 'world_cm': rear['world_cm']},
        'canonical_source_vertex_ids': ids, 'candidates': candidates,
        'max_pairs': options['max_pairs'], 'produced_pairs': len(candidates), 'stop_reason': stop_reason,
        'endpoint_sampling': 'SOURCE_CYCLE_NEIGHBOURS_ONLY_NO_SPATIAL_NEAREST_SEARCH',
        'selection': 'NONE', 'ease_cm': None, 'acceptance': 'NONE', 'qualification': 'NONE',
        'body_reference_review_transferred': False, 'anatomical_homology': 'NOT_GRANTED_FOR_ENDPOINTS',
        'body_changed': False, 'grading': 'NOT_EXECUTED', 'fitting': 'NOT_EXECUTED', 'Blender': 'NOT_EXECUTED'}
    if digest([profile, geometry, path, options]) != before: raise StudioError('Opening exploration mutated source inputs')
    budget.size(result)
    return result


def render_opening_candidates(profile, geometry, report, options, *, budget_check=None):
    """Four exact-source projections per unselected hypothesis, in SVG memory."""
    budget = _Budget(options, budget_check)
    if not isinstance(report, dict) or 'source_path' not in report:
        raise StudioError('Opening renderer needs its exact source hypothesis report')
    expected = prepare_opening_candidates(profile, geometry, report['source_path'], options, budget_check=budget.check)
    if report != expected: raise StudioError('Opening renderer report differs from exact source reconstruction')
    frame = _frame(profile); vertices = geometry['vertices_cm']; ids = report['canonical_source_vertex_ids']
    local = {i: [_exact_coordinate(vertices[i], frame, name) for name in ('right', 'forward', 'up')] for i in ids}
    width = 1100; cell_height = 290; height = 80+cell_height*len(report['candidates']); pieces = []; used = 0
    report_bytes = len(canonical(report))
    def append(text):
        nonlocal used
        used += len(text.encode('utf-8'))
        if used+report_bytes > options['max_output_bytes']:
            raise StudioError('Opening renderer combined report/SVG byte budget exceeded')
        pieces.append(text)
    append(f'<svg xmlns="http://www.w3.org/2000/svg" width="{width}" height="{height}" viewBox="0 0 {width} {height}">')
    append('<rect width="100%" height="100%" fill="white"/><g font-family="sans-serif" font-size="12">')
    append('<text x="16" y="20">Hypothèses d’ouverture non sélectionnées — aucune aisance ou acceptation transférée.</text>')
    append('<text x="16" y="42">Zoom sur la boucle source exacte ; projections sans occlusion ; coordonnées SVG arrondies seulement pour affichage.</text>')
    views = [('Face', 1., 0.), ('Profil', 0., 1.), ('Dos', -1., 0.), ('Trois-quarts', 2**-.5, 2**-.5)]
    for row, candidate in enumerate(report['candidates']):
        budget.check(); y0 = 65+cell_height*row
        append(f'<text x="16" y="{y0+14}">'+html.escape(candidate['id'])+
               ' — arc omis '+repr(candidate['front_omitted_arc']['length_cm'])+' cm ; restant '+
               repr(candidate['remaining_arc']['length_cm'])+' cm</text>')
        for column, (name, a, b) in enumerate(views):
            budget.check(); points = {i: [a*float(local[i][0])+b*float(local[i][1]), float(local[i][2])] for i in ids}
            lo = [min(p[k] for p in points.values()) for k in (0, 1)]; hi = [max(p[k] for p in points.values()) for k in (0, 1)]
            x0 = 275*column; scale = min(225/max(hi[0]-lo[0], 1e-10), 180/max(hi[1]-lo[1], 1e-10))
            def pixels(index):
                x, y = points[index]
                return f'{x0+137.5+(x-(lo[0]+hi[0])/2)*scale:.3f},{y0+62+(hi[1]-y)*scale:.3f}'
            append(f'<text x="{x0+18}" y="{y0+40}">{name}</text>')
            for arc_name, colour in (('remaining_arc', '#176c43'), ('front_omitted_arc', '#c44b17')):
                append('<polyline points="'+' '.join(pixels(i) for i in candidate[arc_name]['vertex_ids'])+
                       '" fill="none" stroke="'+colour+'" stroke-width="2"/>')
            for endpoint in candidate['endpoints']:
                x, y = pixels(endpoint['selector']['vertex_id']).split(',')
                append(f'<circle cx="{x}" cy="{y}" r="4" fill="#1c45a3"/>')
    append('</g></svg>')
    svg = ''.join(pieces).encode('utf-8')
    budget.check()
    return svg
