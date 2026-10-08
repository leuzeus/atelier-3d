"""Pure open mesh-edge path proposals from exact source vertex identities.

An edge-graph shortest path is not a smooth surface geodesic and does not
establish tailoring homology. No body measurement, source or gate is written.
"""
import copy
import heapq
import math
import time

from .contact_geometry import dot, norm, sub
from .core import StudioError, digest, sha


_DEFAULT = {'max_vertices': 20000, 'max_faces': 20000, 'max_edges': 200000,
            'max_visited': 50000, 'max_seconds': 30., 'max_paths': 16}
_HARD = {'max_vertices': 250000, 'max_faces': 250000, 'max_edges': 1500000,
         'max_visited': 1000000, 'max_seconds': 60., 'max_paths': 32}


def _finite(value):
    return type(value) in (int, float) and math.isfinite(value)


def _point(value):
    return isinstance(value, (list, tuple)) and len(value) == 3 and all(_finite(x) for x in value)


def _hash(value):
    return isinstance(value, str) and len(value) == 64 and all(x in '0123456789abcdef' for x in value)


def _close(a, b):
    return abs(a-b) <= 32*math.ulp(max(1., abs(a), abs(b)))


class _Budget:
    def __init__(self, limits, clock):
        if not isinstance(limits, dict) or set(limits)-set(_DEFAULT):
            raise StudioError('Body surface paths require explicit recognized budgets')
        self.limits = {**_DEFAULT, **limits}
        for key, maximum in _HARD.items():
            value = self.limits[key]
            if not (_finite(value) if key == 'max_seconds' else type(value) is int) or not 0 < value <= maximum:
                raise StudioError('Invalid finite body surface path budget: '+key)
        self.clock = clock; self.started = self.last = self._time(); self.visited = 0

    def _time(self):
        value = self.clock()
        if not _finite(value):
            raise StudioError('Body surface path clock must be finite')
        return value

    def check(self):
        now = self._time()
        if now < self.last or now-self.started > self.limits['max_seconds']:
            raise StudioError('Body surface path time budget exhausted or clock reversed')
        self.last = now


def _basis(value):
    if (not isinstance(value, dict) or set(value) != {'origin_cm', 'right', 'forward', 'up'}
            or any(not _point(point) for point in value.values())):
        raise StudioError('Body surface paths require the exact finite explicit body frame')
    axes = [value[key] for key in ('right', 'forward', 'up')]
    if any(abs(dot(a, b)-float(i == j)) > 1e-7 for i, a in enumerate(axes) for j, b in enumerate(axes)):
        raise StudioError('Body surface path frame must be orthonormal')
    return value


def _mesh(geometry, budget):
    if not isinstance(geometry, dict):
        raise StudioError('Body surface paths need exact source geometry')
    vertices, faces, regions = (geometry.get(key) for key in ('vertices_cm', 'faces', 'face_sets'))
    if (not isinstance(vertices, list) or not 3 <= len(vertices) <= budget.limits['max_vertices']
            or not isinstance(faces, list) or not 1 <= len(faces) <= budget.limits['max_faces']
            or not isinstance(regions, list) or len(regions) != len(faces)
            or any(not _hash(geometry.get(key)) for key in ('source_sha256', 'pose_sha256'))):
        raise StudioError('Body surface geometry counts, regions or source identities are invalid or over budget')
    for point in vertices:
        budget.check()
        if not _point(point):
            raise StudioError('Body surface vertices must be finite world centimetres')
    edges = {}; occurrences = 0
    for index, (face, region) in enumerate(zip(faces, regions, strict=True)):
        budget.check()
        if (not isinstance(face, list) or len(face) < 3 or type(region) is not int
                or any(type(i) is not int or not 0 <= i < len(vertices) for i in face)
                or len(set(face)) != len(face)):
            raise StudioError('Body surface face or region identity is invalid')
        occurrences += len(face)
        if occurrences > budget.limits['max_edges']:
            raise StudioError('Body surface path face-edge incidence budget exhausted')
        for a, b in zip(face, face[1:]+face[:1]):
            edges.setdefault(tuple(sorted((a, b))), []).append(index)
    return vertices, faces, regions, edges, occurrences


def _reports(reports, geometry, basis, edges, budget):
    if (not isinstance(reports, dict) or not 1 <= len(reports) <= budget.limits['max_paths']
            or any(not isinstance(key, str) or not 1 <= len(key) <= 200 for key in reports)):
        raise StudioError('Body surface paths require bounded explicit source path reports')
    identity = {'geometry_sha256': digest([geometry['vertices_cm'], geometry['faces']]),
        'face_sets_sha256': digest(geometry['face_sets']),
        'source_sha256': geometry['source_sha256'], 'pose_sha256': geometry['pose_sha256']}
    rows = {}; path_count = 0
    for report_id, report in sorted(reports.items()):
        budget.check()
        if (not isinstance(report_id, str) or not report_id or len(report_id) > 200
                or not isinstance(report, dict) or report.get('frame') != basis
                or not isinstance(report.get('identity'), dict)
                or any(report.get('identity', {}).get(key) != value for key, value in identity.items())
                or not isinstance(report.get('paths'), list)):
            raise StudioError('Body surface source path report geometry, pose, regions or frame differs')
        _basis(report['frame'])
        for row in report['paths']:
            budget.check(); path_count += 1
            if path_count > budget.limits['max_paths']:
                raise StudioError('Body surface source boundary path budget exhausted')
            if (not isinstance(row, dict) or not isinstance(row.get('id'), str) or not row['id']
                    or len(row['id']) > 200 or (report_id, row['id']) in rows or row.get('closed') is not True
                    or not isinstance(row.get('vertex_ids'), list) or not 3 <= len(row['vertex_ids']) <= budget.limits['max_vertices']):
                raise StudioError('Body surface selectors require a unique complete closed source boundary')
            ids = row['vertex_ids']; n = len(geometry['vertices_cm'])
            if (any(type(i) is not int or not 0 <= i < n for i in ids) or len(set(ids)) != len(ids)
                    or row.get('edge_vertex_ids') != [list(pair) for pair in zip(ids, ids[1:]+ids[:1])]
                    or not isinstance(row.get('curve_world_cm'), list)
                    or row.get('curve_world_cm') != [geometry['vertices_cm'][i] for i in ids]
                    or not isinstance(row.get('edge_source_face_ids'), list)
                    or len(row['edge_source_face_ids']) != len(ids)
                    or not isinstance(row.get('source_regions'), list) or len(row['source_regions']) != 2
                    or any(type(i) is not int for i in row['source_regions']) or len(set(row['source_regions'])) != 2):
                raise StudioError('Body surface source boundary is branched, incomplete or has changed source vertices')
            for pair, face_ids in zip(row['edge_vertex_ids'], row['edge_source_face_ids'], strict=True):
                budget.check(); actual = edges.get(tuple(sorted(pair)))
                if (any(type(i) is not int for i in pair)
                        or not isinstance(face_ids, list) or any(type(i) is not int for i in face_ids)
                        or actual is None or len(actual) != 2 or face_ids != sorted(actual)
                        or {geometry['face_sets'][i] for i in actual} != set(row['source_regions'])
                        or math.dist(*(geometry['vertices_cm'][i] for i in pair)) == 0):
                    raise StudioError('Body surface source boundary edge provenance is missing, ambiguous or collapsed')
            for point in row['curve_world_cm']:
                budget.check()
                if not _point(point):
                    raise StudioError('Body surface source boundary coordinates must be finite and nonboolean')
            rows[report_id, row['id']] = row
    budget.check()
    return rows, identity


def _selector(selector, rows, vertices, basis, budget):
    if not isinstance(selector, dict):
        raise StudioError('Body surface endpoint selector must be explicit source data')
    if set(selector) == {'kind', 'vertex_id'} and selector['kind'] == 'source_vertex':
        index = selector['vertex_id']
        if type(index) is not int or not 0 <= index < len(vertices):
            raise StudioError('Body surface endpoint source vertex ID is invalid')
        return index, {'selector': copy.deepcopy(selector), 'vertex_id': index,
                       'method': 'EXPLICIT_SOURCE_VERTEX_ID_PROPOSAL_DATA'}
    shared = {'kind', 'report_id', 'path_id'}
    if not shared <= set(selector):
        raise StudioError('Body surface endpoint requires an exact source boundary selector')
    if not all(isinstance(selector.get(key), str) for key in ('report_id', 'path_id')):
        raise StudioError('Body surface source boundary selector identity is invalid')
    source = rows.get((selector['report_id'], selector['path_id']))
    if source is None:
        raise StudioError('Body surface endpoint source boundary is absent')
    ids = source['vertex_ids']
    center = [math.fsum(vertices[i][k]/len(ids) for i in ids) for k in range(3)]
    details = {'source_path_sha256': digest(source), 'source_vertex_centroid_world_cm': center}
    if (set(selector) == shared|{'axis', 'extreme'} and selector['kind'] == 'boundary_extreme'
            and selector['axis'] in ('right', 'forward', 'up') and selector['extreme'] in ('min', 'max')):
        direction = basis[selector['axis']]
        sign = 1 if selector['extreme'] == 'max' else -1
        method = 'UNIQUE_SOURCE_BOUNDARY_BODY_FRAME_EXTREME'
    elif (set(selector) == shared|{'toward_report_id', 'toward_path_id'}
            and selector['kind'] == 'boundary_toward_path_centroid'
            and all(isinstance(selector[key], str) for key in ('toward_report_id', 'toward_path_id'))):
        target = rows.get((selector['toward_report_id'], selector['toward_path_id']))
        if target is None:
            raise StudioError('Body surface endpoint direction target boundary is absent')
        target_ids = target['vertex_ids']
        toward = [math.fsum(vertices[i][k]/len(target_ids) for i in target_ids) for k in range(3)]
        delta = sub(toward, center); size = norm(delta)
        if not math.isfinite(size) or size == 0:
            raise StudioError('Body surface boundary centroid direction is zero or nonfinite')
        direction = [x/size for x in delta]; sign = 1
        details.update(direction_target_path_sha256=digest(target),
                       direction_target_centroid_world_cm=toward, direction_world=direction)
        method = 'UNIQUE_SOURCE_BOUNDARY_EXTREME_TOWARD_SOURCE_PATH_VERTEX_CENTROID'
    else:
        raise StudioError('Unsupported body surface source endpoint selector')
    scores = []
    for index in sorted(ids):
        budget.check(); score = sign*dot(sub(vertices[index], center), direction)
        if not math.isfinite(score):
            raise StudioError('Body surface endpoint score is not finite')
        scores.append((score, index))
    scores.sort(key=lambda row: (-row[0], row[1]))
    if _close(scores[0][0], scores[1][0]):
        raise StudioError('Body surface endpoint extreme is tied or numerically ambiguous')
    index = scores[0][1]
    details.update(selector=copy.deepcopy(selector), vertex_id=index, method=method,
                   best_score_cm=scores[0][0], second_score_cm=scores[1][0],
                   endpoint_score_gap_cm=scores[0][0]-scores[1][0])
    return index, details


def _shortest(graph, start, end, budget):
    distances = {start: 0.}; previous = {}; incoming = {}; queue = [(0., start)]
    while queue:
        budget.check(); distance, current = heapq.heappop(queue)
        if distance != distances[current]:
            continue
        budget.visited += 1
        if budget.visited > budget.limits['max_visited']:
            raise StudioError('Body surface path shared visited-vertex budget exhausted')
        for neighbor, length in sorted(graph[current].items()):
            budget.check(); candidate = distance+length
            if not math.isfinite(candidate) or candidate <= distance:
                raise StudioError('Body surface path cost is nonfinite or numerically unresolved')
            # Retain each predecessor's latest exact minimum candidate. A
            # near-tied improvement must still replace the minimum; otherwise
            # a third improvement can erase the closest competing route.
            # At most two directed records per source graph edge are stored.
            incoming.setdefault(neighbor, {})[current] = candidate
            old = distances.get(neighbor)
            if old is None or candidate < old:
                distances[neighbor] = candidate; previous[neighbor] = current
                heapq.heappush(queue, (candidate, neighbor))
    if end not in distances:
        raise StudioError('Body surface endpoints are disconnected in the explicit source region domain')
    ordered = [end]
    while ordered[-1] != start:
        budget.check()
        current = ordered[-1]; predecessor = previous[current]
        if any(other != predecessor and _close(cost, distances[current])
               for other, cost in incoming[current].items()):
            raise StudioError('Body surface shortest edge path has tied or numerically ambiguous alternatives')
        ordered.append(predecessor)
    return list(reversed(ordered))


def propose_body_surface_paths(geometry, source_path_reports, specification, *, clock=time.monotonic):
    """Return bounded OPEN proposals on original polygon boundary edges only.

    Selectors use exact vertex IDs, unique source-ring frame extrema, or a
    direction derived from two source-ring vertex centroids. Shortest-path
    and endpoint ties are refused using a binary64 roundoff policy; no
    anatomical tolerance, interpolated endpoint or mesh diagonal is inserted.
    Native-origin verification remains owned by the approved source reports.
    """
    if (not isinstance(specification, dict) or set(specification) != {'version', 'frame', 'paths', 'budgets'}
            or type(specification['version']) is not int or specification['version'] != 1):
        raise StudioError('Body surface paths require an explicit version 1 specification')
    budget = _Budget(specification['budgets'], clock)
    basis = _basis(specification['frame'])
    requests = specification['paths']
    if not isinstance(requests, list) or not 1 <= len(requests) <= budget.limits['max_paths']:
        raise StudioError('Body surface proposal path budget exhausted or paths absent')
    vertices, faces, regions, edges, occurrences = _mesh(geometry, budget)
    rows, identity = _reports(source_path_reports, geometry, basis, edges, budget)
    try:
        before = digest([geometry, source_path_reports, specification])
    except (TypeError, ValueError, OverflowError, RecursionError) as error:
        raise StudioError('Body surface paths need finite canonical source evidence') from error
    budget.check(); results = []; ids = set()
    for request in requests:
        budget.check()
        if (not isinstance(request, dict) or set(request) != {'id', 'domain_region_ids', 'start', 'end'}
                or not isinstance(request['id'], str) or not 1 <= len(request['id']) <= 200
                or request['id'] in ids or not isinstance(request['domain_region_ids'], list)
                or not 1 <= len(request['domain_region_ids']) <= 256
                or any(type(i) is not int for i in request['domain_region_ids'])
                or len(set(request['domain_region_ids'])) != len(request['domain_region_ids'])
                or not set(request['domain_region_ids']) <= set(regions)):
            raise StudioError('Body surface proposal needs a unique ID and existing explicit source domain regions')
        ids.add(request['id']); domain = set(request['domain_region_ids']); graph = {}; owners = {}
        for edge, face_ids in sorted(edges.items()):
            budget.check(); selected = [i for i in face_ids if regions[i] in domain]
            if not selected:
                continue
            if len(face_ids) > 2:
                raise StudioError('Body surface domain edge has ambiguous nonmanifold provenance')
            a, b = edge; length = math.dist(vertices[a], vertices[b])
            if not math.isfinite(length) or length <= 0:
                raise StudioError('Body surface domain contains a zero or nonfinite source edge')
            graph.setdefault(a, {})[b] = length; graph.setdefault(b, {})[a] = length; owners[edge] = selected
        start, start_source = _selector(request['start'], rows, vertices, basis, budget)
        end, end_source = _selector(request['end'], rows, vertices, basis, budget)
        if start == end or start not in graph or end not in graph:
            raise StudioError('Body surface endpoints must be distinct actual vertices in the declared domain')
        ordered = _shortest(graph, start, end, budget)
        pairs = list(zip(ordered, ordered[1:])); points = [list(vertices[i]) for i in ordered]
        length = math.fsum(graph[a][b] for a, b in pairs); chord = math.dist(points[0], points[-1])
        heights = [dot(sub(point, basis['origin_cm']), basis['up']) for point in points]
        drop = heights[0]-heights[-1]
        if not all(math.isfinite(x) for x in [length, chord, drop, *heights]):
            raise StudioError('Body surface path measurements are not finite')
        results.append({'id': request['id'], 'domain_region_ids': sorted(domain), 'closed': False,
            'method': 'DIJKSTRA_ORIGINAL_MESH_EDGE_GRAPH', 'vertex_ids': ordered,
            'edge_vertex_ids': [list(pair) for pair in pairs],
            'edge_source_face_ids': [owners[tuple(sorted(pair))] for pair in pairs],
            'polyline_world_cm': points, 'edge_arclength_cm': length, 'endpoint_chord_cm': chord,
            'vertical_drop_cm': drop, 'body_frame_height_range_cm': [min(heights), max(heights)],
            'vertical_drop_definition': 'START_HEIGHT_MINUS_END_HEIGHT_IN_EXPLICIT_BODY_UP_FRAME',
            'endpoint_sources': {'start': start_source, 'end': end_source},
            'domain_face_count': sum(region in domain for region in regions),
            'domain_vertex_count': len(graph), 'domain_edge_count': len(owners),
            'mesh_approximation_error_cm': None, 'smooth_geodesic_error_bound': 'NOT_ESTABLISHED',
            'qualification': 'NONE', 'tailoring_homology': 'REVIEW_REQUIRED', 'anatomical_gate': 'NOT_GRANTED'})
    if digest([geometry, source_path_reports, specification]) != before:
        raise StudioError('Body surface path proposals changed immutable source inputs')
    budget.check()
    result = {'version': 1, 'status': 'BODY_SURFACE_OPEN_PATH_PROPOSALS_FOR_REVIEW',
        'identity': identity, 'geometry_document_sha256': digest(geometry),
        'source_path_report_sha256': {key: digest(value) for key, value in sorted(source_path_reports.items())},
        'specification_sha256': digest(specification), 'measurement_code_sha256': sha(__file__),
        'frame': copy.deepcopy(basis), 'paths': results, 'budgets': copy.deepcopy(budget.limits),
        'work_counts': {'face_edge_incidences': occurrences, 'visited_vertices_all_paths': budget.visited},
        'edge_budget_scope': 'ALL_SOURCE_POLYGON_FACE_EDGE_INCIDENCES',
        'tie_policy': 'REFUSE_ENDPOINT_OR_ROUTE_ALTERNATIVES_WITHIN_BINARY64_32_ULP_AT_SCORE_COST_SCALE',
        'discretization_scope': 'ACTUAL_SOURCE_MESH_EDGE_POLYLINE_NO_DIAGONALS_OR_SURFACE_SMOOTHING',
        'native_body_origin': 'SOURCE_REPORT_PROVENANCE_NOT_REVALIDATED_BY_PORTABLE_KERNEL',
        'source_mutated': False, 'body_profile_changed': False, 'body_girths_replaced': False,
        'qualification': 'NONE', 'tailoring_homology': 'REVIEW_REQUIRED',
        'fitting': 'NOT_EXECUTED', 'Blender': 'NOT_EXECUTED', 'acceptance': 'NOT_GRANTED'}
    budget.check()
    return result
