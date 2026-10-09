"""Bounded nearest closed-triangle diagnostics and optional V1 local patches.

The caller authenticates native origin. Hashes here establish exact supplied
artifact consistency only. Signed offsets are oriented *triangle-plane* offsets,
never inside/outside or global body clearance. Ties (including coplanar duplicates)
are refused, rather than choosing a surface that makes a candidate admissible.
"""
import copy
import heapq
import math
import time

from .core import StudioError, digest
from .contact_geometry import TriangleBVH, bounds_distance_sq, closest_point_triangle, cross, dot, sub
from .constrained_guide_recovery import MAX_ROWS, MAX_TRUST_RADIUS_CM


# Bounds include metadata, keys and repeated serialized aliases, not merely
# geometry's outer lists. Bytes are a conservative canonical-JSON upper bound.
MAX_JSON_NODES = 4000000
MAX_JSON_BYTES = 128*1024*1024
MAX_JSON_DEPTH = 32
MAX_JSON_STRING_CHARACTERS = 65536
MAX_JSON_INTEGER_BITS = 64


class _Budget(Exception):
    pass


def _require(value, message):
    if not value:
        raise StudioError('Local surface producer: '+message)


def _number(value):
    return type(value) in (int, float) and math.isfinite(value)


def _vector(value):
    return isinstance(value, (list, tuple)) and len(value) == 3 and all(_number(v) for v in value)


def _hash(value):
    return isinstance(value, str) and len(value) == 64 and all(c in '0123456789abcdef' for c in value)


def _tie_tolerance(value):
    # Float64 comparison tolerance, in squared cm: 64 ULP of max(1, d^2).
    # This classifies numerical ambiguity, not physical reserve or uncertainty.
    return 64*math.ulp(max(1., value))


def _bounded_json(values, check):
    """Bound the ENTIRE supplied JSON tree before any canonical digest.

    Metadata is allowed under the same cumulative bounds. Cycles are refused;
    a shared acyclic subtree is counted on every occurrence, as JSON writes it.
    """
    nodes = 0; size = 0; ancestors = set()

    def visit(value, depth):
        nonlocal nodes, size
        check(); nodes += 1
        _require(nodes <= MAX_JSON_NODES and depth <= MAX_JSON_DEPTH, 'whole JSON node/depth cap exceeded')
        kind = type(value)
        if kind in (dict, list):
            _require(id(value) not in ancestors, 'cyclic JSON input')
            # Cheap length bound before iteration, independent of child types.
            _require(len(value) <= MAX_JSON_NODES-nodes, 'whole JSON node cap exceeded')
            size += 2+len(value)*2
            _require(size <= MAX_JSON_BYTES, 'whole JSON byte cap exceeded')
            ancestors.add(id(value))
            if kind is dict:
                for key, child in value.items():
                    _require(type(key) is str, 'JSON object keys must be strings')
                    visit(key, depth+1); visit(child, depth+1)
            else:
                for child in value:
                    visit(child, depth+1)
            ancestors.remove(id(value))
        elif kind is str:
            _require(len(value) <= MAX_JSON_STRING_CHARACTERS, 'JSON string cap exceeded')
            # Canonical JSON quotes/control escapes cost at most six bytes per
            # Unicode scalar. Refuse lone surrogates before UTF-8 serialization.
            for character in value:
                check(); _require(not 0xD800 <= ord(character) <= 0xDFFF, 'JSON strings must contain Unicode scalars')
            size += 2+6*len(value)
        elif kind is int:
            _require(value.bit_length() <= MAX_JSON_INTEGER_BITS, 'JSON integer magnitude cap exceeded')
            size += 22
        elif kind is float:
            _require(math.isfinite(value), 'finite JSON numbers required'); size += 32
        elif kind is bool or value is None:
            size += 5
        else:
            _require(False, 'only finite ordinary JSON types supported')
        _require(size <= MAX_JSON_BYTES, 'whole JSON byte cap exceeded')

    for value in values:
        visit(value, 0)
    check()
    return {'json_nodes': nodes, 'json_bytes_upper_bound': size}


def _material_source(payload, check):
    """Validate actual material topology/ownership and optional stored bindings."""
    rest, faces, panels = payload['rest_cm'], payload['faces'], payload['panels']
    _require(0 < len(faces) <= 200000 and 0 < len(panels) <= 128, 'complete bounded material topology required')
    for point in rest:
        check(); _require(_vector(point), 'actual finite three-dimensional REST coordinates required')
    memberships = {}
    for piece, panel in panels.items():
        check()
        _require(isinstance(piece, str) and 0 < len(piece) <= 128 and isinstance(panel, dict), 'actual material panels required')
        indices = panel.get('indices')
        _require(isinstance(indices, list) and 0 < len(indices) <= len(rest) and
                 all(type(i) is int and 0 <= i < len(rest) for i in indices) and len(set(indices)) == len(indices),
                 'actual unique panel index coverage required')
        for index in indices:
            check(); memberships.setdefault(index, set()).add(piece)
        edges = panel.get('edges', {})
        _require(isinstance(edges, dict), 'material edge mapping required')
        for name, edge in edges.items():
            check()
            _require(isinstance(name, str) and bool(name) and isinstance(edge, list) and 2 <= len(edge) <= len(indices)
                     and all(type(i) is int and i in memberships and piece in memberships[i] for i in edge)
                     and len(set(edge)) == len(edge), 'actual named panel edges required')
    _require(len(memberships) == len(rest), 'panels must cover all material REST vertices')
    stored = payload.get('source_rest_triangles_cm'); owners = payload.get('source_face_pieces')
    source_ids = payload.get('source_face_vertex_ids'); mapping = payload.get('source_vertex_map', {})
    _require(isinstance(mapping, dict) and all(type(k) is str and len(k) <= 20 and k.isdigit() and str(int(k)) == k
             and type(v) is int and 0 <= v < len(rest) for k, v in mapping.items()), 'actual source vertex mapping required')
    for key, value in (('source_rest_triangles_cm', stored), ('source_face_pieces', owners), ('source_face_vertex_ids', source_ids)):
        _require(value is None or isinstance(value, list) and len(value) == len(faces), 'complete source binding required: '+key)
    _require(payload.get('rest_mode') != 'assembled_3d' or stored is not None, 'assembled REST needs immutable source UV')
    for fid, face in enumerate(faces):
        check()
        _require(isinstance(face, list) and len(face) == 3 and
                 all(type(i) is int and 0 <= i < len(rest) for i in face) and len(set(face)) == 3,
                 'actual indexed material triangles required')
        common = set.intersection(*(memberships[i] for i in face))
        owner = owners[fid] if owners is not None else next(iter(common)) if len(common) == 1 else None
        _require(isinstance(owner, str) and owner in common, 'unambiguous source face ownership required')
        if stored is not None:
            uv = stored[fid]
            _require(isinstance(uv, list) and len(uv) == 3 and all(isinstance(p, list) and len(p) in (2, 3)
                     and all(_number(v) for v in p) for p in uv), 'actual finite source triangle coordinates required')
        if source_ids is not None:
            ids = source_ids[fid]
            _require(isinstance(ids, list) and len(ids) == 3 and all(type(i) is int and i >= 0 for i in ids)
                     and len(set(ids)) == 3, 'actual source triangle vertex IDs required')
            expected = [mapping.get(str(i), i) for i in ids]
            _require(face in [expected[k:]+expected[:k] for k in range(3)], 'source winding or vertex binding changed')
    check()


def _barycentric(point, triangle):
    a = sub(triangle[1], triangle[0]); b = sub(triangle[2], triangle[0]); p = sub(point, triangle[0])
    normal = cross(a, b); axis = max(range(3), key=lambda k: abs(normal[k]))
    first, second = [k for k in range(3) if k != axis]
    determinant = a[first]*b[second]-a[second]*b[first]
    _require(determinant != 0 and math.isfinite(determinant), 'degenerate triangle barycentric frame')
    u = (p[first]*b[second]-p[second]*b[first])/determinant
    v = (a[first]*p[second]-a[second]*p[first])/determinant
    # Only clamp binary rounding on the already computed closed-triangle point.
    values = [max(0., min(1., x)) for x in (1-u-v, u, v)]
    total = math.fsum(values)
    values = [x/total for x in values]
    reconstructed = [math.fsum(values[j]*triangle[j][k] for j in range(3)) for k in range(3)]
    return values, math.dist(point, reconstructed)


def produce_local_surface_constraints(payload, entry_coordinates, body_geometry, body_triangles,
                                      measured_domains, specification, *, clock=time.monotonic):
    """Return every selected-index diagnostic; emit no partial consumer document.

    ``measured_domains`` uses the consumer's exact sections schema. Missing
    domains still allow geometric diagnostics but never become MEASURED here.
    Diagnostic budgets can exceed the consumer's fixed 4096-row V1 cap.
    Unsupported entries return NEEDS_REPRESENTATION; no resizing inference.
    """
    start = clock(); previous = start
    _require(_number(start), 'finite monotonic clock required')
    _require(isinstance(specification, dict) and set(specification) == {
        'version', 'identity', 'selected_piece_ids', 'clearance_cm', 'trust_radius_cm',
        'weight', 'search_margin_cm', 'budgets'} and specification['version'] == 1
        and type(specification['version']) is int, 'explicit V1 specification required')
    budgets = specification['budgets']
    caps = {'max_selected_vertices': 32000, 'max_queries': 32000,
            'max_triangle_evaluations': 10000000, 'max_output_rows': 32000}
    _require(isinstance(budgets, dict) and set(budgets) == set(caps)|{'max_seconds'}, 'explicit budgets required')
    for key, maximum in caps.items():
        _require(type(budgets[key]) is int and 0 < budgets[key] <= maximum, 'unsupported '+key)
    _require(_number(budgets['max_seconds']) and 0 < budgets['max_seconds'] <= 300., 'bounded time required')
    deadline = start+budgets['max_seconds']
    _require(math.isfinite(deadline), 'finite deadline required')
    counters = {'queries': 0, 'triangle_evaluations': 0}
    rows = []; selected = []; identity = None

    def check():
        nonlocal previous
        now = clock()
        _require(_number(now) and now >= previous, 'finite monotonic clock required')
        previous = now
        if now >= deadline:
            raise _Budget('TIME_BUDGET')

    def result(status, reasons):
        return {'version': 1, 'status': status, 'reasons': reasons,
                'identity': identity, 'selected_material_indices': selected,
                'diagnostics': rows, 'coverage_complete': len(rows) == len(selected) and bool(selected),
                'consumer_document': None, 'work': dict(counters), 'elapsed_seconds': previous-start,
                'signed_offset_scope': 'ORIENTED_LOCAL_TRIANGLE_PLANE_ONLY',
                'global_inside_outside': 'NOT_ASSESSED', 'continuous_body_clearance': 'NOT_QUALIFIED',
                'dimensional_classification': 'NOT_ASSESSED', 'qualification': 'NONE',
                'tie_tolerance': '64 ULP of max(1, squared distance in cm); all ties refused'}

    try:
        check()
        counters.update(_bounded_json((payload, entry_coordinates, body_geometry,
                                       body_triangles, measured_domains, specification), check))
        _require(isinstance(payload, dict) and isinstance(payload.get('panels'), dict)
                 and isinstance(payload.get('rest_cm'), list) and 0 < len(payload['rest_cm']) <= 100000
                 and isinstance(payload.get('faces'), list) and len(payload['faces']) <= 200000,
                 'bounded material source required')
        _material_source(payload, check)
        _require(isinstance(entry_coordinates, list) and len(entry_coordinates) == len(payload['rest_cm']),
                 'complete exact entry coordinates required')
        for point in entry_coordinates:
            check(); _require(_vector(point), 'finite entry coordinates required')
        pieces = specification['selected_piece_ids']
        _require(isinstance(pieces, list) and 0 < len(pieces) <= 128 and
                 all(isinstance(p, str) and 0 < len(p) <= 128 and p in payload['panels'] for p in pieces)
                 and len(set(pieces)) == len(pieces), 'exact selected piece IDs required')
        active = set()
        for piece in pieces:
            indices = payload['panels'][piece].get('indices')
            _require(isinstance(indices, list) and len(indices) <= 100000 and len(set(indices)) == len(indices),
                     'bounded unique source indices required')
            for index in indices:
                check(); _require(type(index) is int and 0 <= index < len(entry_coordinates), 'actual source index required')
                active.add(index)
        selected = sorted(active)
        if not selected or len(selected) > budgets['max_selected_vertices']:
            return result('BUDGET_EXHAUSTED', ['SELECTED_VERTEX_BUDGET'])
        # Output must cover all selected entries: fail before searching, never truncate.
        if len(selected) > budgets['max_output_rows']:
            return result('BUDGET_EXHAUSTED', ['OUTPUT_ROW_BUDGET'])
        body = body_geometry
        _require(isinstance(body, dict) and set(body) == {'vertices_cm', 'faces', 'source_sha256', 'pose_sha256'}
                 and _hash(body['source_sha256']) and _hash(body['pose_sha256']), 'exact four-field body geometry required')
        vertices, faces, triangles = body['vertices_cm'], body['faces'], body_triangles
        _require(isinstance(vertices, list) and 0 < len(vertices) <= 100000 and
                 isinstance(faces, list) and 0 < len(faces) <= 200000 and
                 isinstance(triangles, list) and 0 < len(triangles) <= 200000, 'bounded body geometry required')
        for point in vertices:
            check(); _require(_vector(point), 'finite body coordinates required')
        memberships = {}; edge_count = 0
        for fid, face in enumerate(faces):
            check()
            _require(isinstance(face, list) and 3 <= len(face) <= 600000, 'bounded source face required')
            edge_count += len(face)
            _require(edge_count <= 600000, 'body face-edge cap exceeded')
            _require(all(type(i) is int and 0 <= i < len(vertices) for i in face) and len(set(face)) == len(face),
                     'actual unique source face indices required')
            for i in face:
                check(); memberships.setdefault(i, set()).add(fid)
        owners = []; by_face = {}; native_triangles = []; normals = []
        for triangle in triangles:
            check()
            _require(isinstance(triangle, list) and len(triangle) == 3 and
                     all(type(i) is int and 0 <= i < len(vertices) for i in triangle) and len(set(triangle)) == 3,
                     'actual triangle indices required')
            candidates = set.intersection(*(memberships.get(i, set()) for i in triangle))
            _require(len(candidates) == 1, 'triangle needs exactly one source face owner')
            owner = next(iter(candidates)); owners.append(owner); by_face.setdefault(owner, []).append(triangle)
            coords = [vertices[i] for i in triangle]; normal = cross(sub(coords[1], coords[0]), sub(coords[2], coords[0]))
            size = math.sqrt(dot(normal, normal))
            _require(math.isfinite(size) and size > 1e-12, 'nondegenerate finite oriented triangle required')
            native_triangles.append(coords); normals.append([x/size for x in normal])
        for fid, face in enumerate(faces):
            check(); parts = by_face.get(fid, []); counts = {}
            _require(len(parts) == len(face)-2, 'native triangles must cover every source face')
            for triangle in parts:
                for edge in zip(triangle, triangle[1:]+triangle[:1]):
                    check(); counts[edge] = counts.get(edge, 0)+1
            boundary = set(zip(face, face[1:]+face[:1]))
            _require(all(counts.get(e) == 1 and not counts.get(e[::-1]) for e in boundary) and
                     all(e in boundary or n == 1 and counts.get(e[::-1]) == 1 for e, n in counts.items()),
                     'native triangulation contradicts source boundary or winding')
        identity = {'source_payload_sha256': digest(payload), 'entry_coordinates_sha256': digest(entry_coordinates),
                    'body_geometry_sha256': digest([vertices, faces]), 'body_triangles_sha256': digest(triangles),
                    'body_source_sha256': body['source_sha256'], 'body_pose_sha256': body['pose_sha256']}
        check()
        _require(specification['identity'] == identity, 'stale source, entry, body, pose or triangles')
        for key, maximum, positive in (('clearance_cm', MAX_TRUST_RADIUS_CM, False),
                                       ('trust_radius_cm', MAX_TRUST_RADIUS_CM, True),
                                       ('weight', 1e6, True), ('search_margin_cm', .1, True)):
            value = specification[key]
            _require(_number(value) and (value > 0 if positive else value >= 0) and value <= maximum,
                     'unsupported '+key)
        sections = measured_domains
        triangle_sections = {}
        if sections is not None and sections != {}:
            _require(isinstance(sections, dict) and len(sections) <= MAX_ROWS, 'bounded measured domains required')
            body_identity = digest({k: v for k, v in identity.items() if k.startswith('body_')})
            references = 0
            for key, section in sections.items():
                check()
                _require(isinstance(key, str) and 0 < len(key) <= 128 and isinstance(section, dict)
                         and set(section) == {'status', 'body_identity_sha256', 'triangle_ids'}
                         and section['status'] == 'MEASURED' and section['body_identity_sha256'] == body_identity
                         and isinstance(section['triangle_ids'], list) and 0 < len(section['triangle_ids']) <= 200000,
                         'missing, unmeasured or stale measured domain')
                ids = section['triangle_ids']; references += len(ids)
                _require(references <= 600000 and all(type(i) is int and 0 <= i < len(triangles) for i in ids)
                         and len(set(ids)) == len(ids), 'exact bounded domain triangle coverage required')
                for tid in ids:
                    check(); triangle_sections.setdefault(tid, []).append(key)
        else:
            _require(sections is None or sections == {}, 'measured domains must be supplied explicitly')
        check(); bvh = TriangleBVH(native_triangles); check()
        reasons = set()
        for index in selected:
            check()
            if counters['queries'] >= budgets['max_queries']:
                raise _Budget('QUERY_BUDGET')
            counters['queries'] += 1
            point = entry_coordinates[index]; box = (tuple(point), tuple(point))
            queue = [(bounds_distance_sq(box, bvh.root[0]), 0, bvh.root)]; sequence = 0
            best = math.inf; nearest = []
            while queue:
                check(); lower, _, node = heapq.heappop(queue)
                if math.isfinite(best) and lower > best+_tie_tolerance(best):
                    continue
                if node[1] is None:
                    for child in (node[2], node[3]):
                        sequence += 1
                        heapq.heappush(queue, (bounds_distance_sq(box, child[0]), sequence, child))
                    continue
                for tid in node[1]:
                    check()
                    if math.isfinite(best) and bounds_distance_sq(box, bvh.bounds[tid]) > best+_tie_tolerance(best):
                        continue
                    if counters['triangle_evaluations'] >= budgets['max_triangle_evaluations']:
                        raise _Budget('TRIANGLE_EVALUATION_BUDGET')
                    counters['triangle_evaluations'] += 1
                    closest = closest_point_triangle(point, native_triangles[tid])
                    distance = dot(sub(point, closest), sub(point, closest))
                    _require(math.isfinite(distance), 'nonfinite nearest distance')
                    if distance < best:
                        best = distance
                        nearest = [(t, q, d) for t, q, d in nearest if d <= best+_tie_tolerance(best)]
                    if distance <= best+_tie_tolerance(best):
                        nearest.append((tid, closest, distance))
            nearest = sorted((item for item in nearest if item[2] <= best+_tie_tolerance(best)), key=lambda x: x[0])
            _require(bool(nearest), 'nearest query has no body triangle')
            # Witness chosen solely for diagnostics; ambiguity never publishes a row.
            tid, closest, distance = nearest[0]; normal = normals[tid]; triangle = native_triangles[tid]
            signed = dot(sub(point, closest), normal)
            projection = [point[k]-signed*normal[k] for k in range(3)]
            patch_gap = math.dist(projection, closest_point_triangle(projection, triangle))
            trust_distance = math.sqrt(distance)
            patch_valid = patch_gap <= 1e-9
            trust_valid = trust_distance <= specification['trust_radius_cm']
            ambiguity = len(nearest) != 1
            sections_for_triangle = sorted(triangle_sections.get(tid, []))
            barycentric, barycentric_gap = _barycentric(closest, triangle)
            flags = []
            if ambiguity: flags.append('AMBIGUOUS_NEAREST_TRIANGLE')
            if not patch_valid: flags.append('ENTRY_PROJECTION_OUTSIDE_TRIANGLE_PATCH')
            if not trust_valid: flags.append('ENTRY_OUTSIDE_TRUST_BALL')
            if not sections_for_triangle: flags.append('MISSING_MEASURED_DOMAIN')
            if barycentric_gap > 1e-9: flags.append('UNREPRESENTABLE_SURFACE_POINT_BARYCENTRIC')
            rows.append({'material_index': index, 'entry_point_cm': list(point), 'triangle_id': tid,
                         'body_face_id': owners[tid], 'triangle_vertex_indices': list(triangles[tid]),
                         'point_cm': list(closest), 'barycentric': barycentric,
                         'barycentric_reconstruction_gap_cm': barycentric_gap,
                         'normal_world': list(normal), 'unsigned_closed_triangle_distance_cm': trust_distance,
                         'signed_plane_offset_cm': signed, 'plane_projection_cm': projection,
                         'projection_patch_gap_cm': patch_gap, 'entry_patch_valid': patch_valid,
                         'entry_trust_valid': trust_valid, 'measured_domain_ids': sections_for_triangle,
                         'nearest_triangle_ambiguous': ambiguity, 'nearest_tie_count': len(nearest),
                         'nearest_tie_ids': [t for t, _, _ in nearest[:16]],
                         'tie_ids_truncated': len(nearest) > 16, 'flags': flags})
            reasons.update(flags)
        check()
        if len(selected) > MAX_ROWS:
            reasons.add('CONSUMER_V1_ROW_CAP_EXCEEDED')
        representation = reasons-{'MISSING_MEASURED_DOMAIN'}
        if representation:
            return result('NEEDS_REPRESENTATION', sorted(reasons))
        if not sections or 'MISSING_MEASURED_DOMAIN' in reasons:
            return result('NEEDS_MEASURED_DOMAINS', sorted(reasons or {'MISSING_MEASURED_DOMAIN'}))
        document = {'version': 1, 'identity': copy.deepcopy(identity), 'body_geometry': copy.deepcopy(body),
                    'body_triangles': copy.deepcopy(triangles), 'sections': copy.deepcopy(sections),
                    'material_indices': list(selected), 'rows': [], 'weight': specification['weight'],
                    'search_margin_cm': specification['search_margin_cm']}
        for row in rows:
            check()
            document['rows'].append({'id': 'material.'+str(row['material_index']),
                **{key: copy.deepcopy(row[key]) for key in ('material_index', 'point_cm', 'normal_world', 'triangle_id', 'barycentric')},
                'clearance_cm': specification['clearance_cm'], 'trust_radius_cm': specification['trust_radius_cm'],
                'section_id': row['measured_domain_ids'][0]})
        check()
        output = result('LOCAL_CONSTRAINT_DOCUMENT_PREPARED', [])
        output['consumer_document'] = document
        return output
    except _Budget as error:
        return result('BUDGET_EXHAUSTED', [str(error)])
