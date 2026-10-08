"""Portable sampled triangle-plane constraints for source-metric recovery.

Input identities establish consistency of supplied artifacts, not native origin
or human approval. A local triangle plane is never a signed body distance. The
trust ball AND the projected triangle patch bound every supported coordinate.
No source, topology, pins, cuts or production gate is changed here.
"""
import copy
import math

from .core import StudioError, digest
from .contact_geometry import closest_point_triangle, cross, dot, sub


MAX_ROWS = 4096
MAX_BODY_VERTICES = 100000
MAX_BODY_FACES = 200000
MAX_BODY_TRIANGLES = 200000
MAX_BODY_FACE_EDGES = 600000
MAX_SECTION_TRIANGLE_REFERENCES = 600000
MAX_TRUST_RADIUS_CM = 20.


def _number(value):
    return type(value) in (int, float) and math.isfinite(value)


def _vector(value):
    return isinstance(value, (list, tuple)) and len(value) == 3 and all(_number(x) for x in value)


def _hash(value):
    return isinstance(value, str) and len(value) == 64 and all(x in '0123456789abcdef' for x in value)


def _require(condition, message):
    if not condition:
        raise StudioError('Local surface constraints: '+message)


def preflight_surface_constraints(document, check):
    """Bound ALL nested serialized input before any digest or metric work."""
    check()
    fields = {'version', 'identity', 'body_geometry', 'body_triangles', 'sections',
              'material_indices', 'rows', 'weight', 'search_margin_cm'}
    _require(isinstance(document, dict) and set(document) == fields and
             type(document['version']) is int and document['version'] == 1,
             'explicit version 1 document required')
    identity = document['identity']
    identity_fields = {'source_payload_sha256', 'entry_coordinates_sha256', 'body_geometry_sha256',
                       'body_triangles_sha256', 'body_source_sha256', 'body_pose_sha256'}
    _require(isinstance(identity, dict) and set(identity) == identity_fields and
             all(_hash(value) for value in identity.values()), 'bounded exact identities required')
    body = document['body_geometry']
    _require(isinstance(body, dict) and set(body) == {'vertices_cm', 'faces', 'source_sha256', 'pose_sha256'}
             and _hash(body['source_sha256']) and _hash(body['pose_sha256']), 'bounded body geometry required')
    vertices, faces, triangles = body['vertices_cm'], body['faces'], document['body_triangles']
    _require(isinstance(vertices, list) and 0 < len(vertices) <= MAX_BODY_VERTICES and
             isinstance(faces, list) and 0 < len(faces) <= MAX_BODY_FACES and
             isinstance(triangles, list) and 0 < len(triangles) <= MAX_BODY_TRIANGLES,
             'body geometry exceeds fixed work caps or is missing')
    coverage, rows, sections = document['material_indices'], document['rows'], document['sections']
    _require(isinstance(coverage, list) and 0 < len(coverage) <= MAX_ROWS and
             isinstance(rows, list) and 0 < len(rows) <= MAX_ROWS and
             isinstance(sections, dict) and 0 < len(sections) <= MAX_ROWS,
             'material coverage, rows or sections exceed fixed work caps')
    for point in vertices:
        check(); _require(_vector(point), 'finite body coordinates required')
    total_edges = 0
    for face in faces:
        check()
        _require(isinstance(face, list) and 3 <= len(face) <= MAX_BODY_FACE_EDGES,
                 'bounded source face required')
        total_edges += len(face)
        _require(total_edges <= MAX_BODY_FACE_EDGES, 'body face-edge work cap exceeded')
        for index in face:
            check(); _require(type(index) is int and 0 <= index < len(vertices), 'actual source face indices required')
    for triangle in triangles:
        check(); _require(isinstance(triangle, list) and len(triangle) == 3 and
                          all(type(i) is int and 0 <= i < len(vertices) for i in triangle), 'actual triangle indices required')
    references = 0
    for key, section in sections.items():
        check()
        _require(isinstance(key, str) and 0 < len(key) <= 128 and isinstance(section, dict) and
                 set(section) == {'status', 'body_identity_sha256', 'triangle_ids'} and
                 section['status'] == 'MEASURED' and _hash(section['body_identity_sha256']) and
                 isinstance(section['triangle_ids'], list), 'bounded measured section provenance required')
        references += len(section['triangle_ids'])
        _require(references <= MAX_SECTION_TRIANGLE_REFERENCES, 'total section-triangle reference cap exceeded')
        for index in section['triangle_ids']:
            check(); _require(type(index) is int and 0 <= index < len(triangles), 'actual section triangle indices required')
    for index in coverage:
        check(); _require(type(index) is int and index >= 0, 'material indices must be exact integers')
    row_fields = {'id', 'material_index', 'point_cm', 'normal_world', 'clearance_cm',
                  'trust_radius_cm', 'triangle_id', 'barycentric', 'section_id'}
    for row in rows:
        check()
        _require(isinstance(row, dict) and set(row) == row_fields and
                 isinstance(row['id'], str) and 0 < len(row['id']) <= 128 and
                 isinstance(row['section_id'], str) and 0 < len(row['section_id']) <= 128 and
                 type(row['material_index']) is int and type(row['triangle_id']) is int and
                 _vector(row['point_cm']) and _vector(row['normal_world']) and
                 isinstance(row['barycentric'], list) and len(row['barycentric']) == 3 and
                 all(_number(x) for x in row['barycentric']) and
                 _number(row['clearance_cm']) and _number(row['trust_radius_cm']),
                 'complete finite bounded local rows required')
    _require(_number(document['weight']) and 0 < document['weight'] <= 1e6 and
             _number(document['search_margin_cm']) and 0 < document['search_margin_cm'] <= .1,
             'bounded positive weight and search margin required')
    check()


class LocalSurfaceConstraints:
    """Compile only explicit material indices, after semantic seam grouping."""

    def __init__(self, document, payload, initial, active, groups, fixed_roots, check):
        self.check = check
        preflight_surface_constraints(document, check)
        fields = {'version', 'identity', 'body_geometry', 'body_triangles', 'sections',
                  'material_indices', 'rows', 'weight', 'search_margin_cm'}
        _require(isinstance(document, dict) and set(document) == fields and
                 type(document['version']) is int and document['version'] == 1,
                 'explicit version 1 document required')
        try:
            self.input_sha = digest(document)
        except (TypeError, ValueError, OverflowError) as error:
            raise StudioError('Local surface constraints: finite structured input required') from error
        self.check()
        body = document['body_geometry']; triangles = document['body_triangles']
        _require(isinstance(body, dict), 'exact body geometry required')
        vertices, faces = body.get('vertices_cm'), body.get('faces')
        _require(isinstance(vertices, list) and 0 < len(vertices) <= MAX_BODY_VERTICES and
                 isinstance(faces, list) and 0 < len(faces) <= MAX_BODY_FACES and
                 isinstance(triangles, list) and 0 < len(triangles) <= MAX_BODY_TRIANGLES,
                 'body geometry exceeds fixed work caps or is missing')
        for point in vertices:
            self.check(); _require(_vector(point), 'finite body coordinates required')
        memberships = {}; face_edges = 0
        for fid, face in enumerate(faces):
            self.check()
            _require(isinstance(face, list) and len(face) >= 3
                     and all(type(i) is int and 0 <= i < len(vertices) for i in face) and len(set(face)) == len(face),
                     'actual source face identities required')
            face_edges += len(face)
            _require(face_edges <= MAX_BODY_FACE_EDGES, 'body face-edge work cap exceeded')
            for i in face:
                memberships.setdefault(i, set()).add(fid)
        triangle_owners = []; by_face = {}
        for triangle in triangles:
            self.check()
            _require(isinstance(triangle, list) and len(triangle) == 3
                     and all(type(i) is int and 0 <= i < len(vertices) for i in triangle) and len(set(triangle)) == 3,
                     'actual body triangle identities required')
            owners = set.intersection(*(memberships.get(i, set()) for i in triangle))
            _require(len(owners) == 1, 'body triangle needs one exact source face')
            owner = next(iter(owners)); triangle_owners.append(owner)
            by_face.setdefault(owner, []).append(triangle)
        for fid, face in enumerate(faces):
            self.check(); parts = by_face.get(fid, []); counts = {}
            _require(len(parts) == len(face)-2, 'triangles must cover each source face exactly')
            for triangle in parts:
                for edge in zip(triangle, triangle[1:]+triangle[:1]):
                    counts[edge] = counts.get(edge, 0)+1
            boundary = set(zip(face, face[1:]+face[:1]))
            _require(all(counts.get(e) == 1 and not counts.get(e[::-1]) for e in boundary) and
                     all(e in boundary or count == 1 and counts.get(e[::-1]) == 1 for e, count in counts.items()),
                     'triangulation contradicts source face boundary or winding')
        identity = document['identity']
        expected = {'source_payload_sha256': digest(payload), 'entry_coordinates_sha256': digest(initial),
                    'body_geometry_sha256': digest([vertices, faces]),
                    'body_triangles_sha256': digest(triangles),
                    'body_source_sha256': body.get('source_sha256'), 'body_pose_sha256': body.get('pose_sha256')}
        _require(isinstance(identity, dict) and set(identity) == set(expected) and
                 all(_hash(value) for value in expected.values()) and identity == expected,
                 'stale source, entry, body, pose or triangle identity')
        self.identity = copy.deepcopy(identity)
        body_identity = {k: v for k, v in identity.items() if k.startswith('body_')}
        sections = document['sections']
        _require(isinstance(sections, dict) and 0 < len(sections) <= MAX_ROWS,
                 'measured section provenance required')
        for key, section in sections.items():
            self.check()
            _require(isinstance(key, str) and key and isinstance(section, dict) and
                     set(section) == {'status', 'body_identity_sha256', 'triangle_ids'} and
                     section['status'] == 'MEASURED' and section['body_identity_sha256'] == digest(body_identity) and
                     isinstance(section['triangle_ids'], list) and 0 < len(section['triangle_ids']) <= MAX_BODY_TRIANGLES and
                     all(type(i) is int and 0 <= i < len(triangles) for i in section['triangle_ids']) and
                     len(set(section['triangle_ids'])) == len(section['triangle_ids']),
                     'missing, unmeasured or stale section coverage')
        coverage = document['material_indices']; rows = document['rows']
        _require(isinstance(coverage, list) and len(coverage) <= MAX_ROWS and
                 all(type(i) is int for i in coverage) and len(set(coverage)) == len(coverage) and
                 set(coverage) == active and isinstance(rows, list) and 0 < len(rows) <= MAX_ROWS,
                 'explicit complete active material-index coverage required')
        self.weight = document['weight']; self.margin = document['search_margin_cm']
        _require(_number(self.weight) and 0 < self.weight <= 1e6 and
                 _number(self.margin) and 0 < self.margin <= .1,
                 'bounded positive weight and search margin required')
        roots = {i: root for root, indices in groups.items() for i in indices}
        row_fields = {'id', 'material_index', 'point_cm', 'normal_world', 'clearance_cm',
                      'trust_radius_cm', 'triangle_id', 'barycentric', 'section_id'}
        self.rows = []; ids = set(); covered = set()
        for row in rows:
            self.check()
            _require(isinstance(row, dict) and set(row) == row_fields and isinstance(row['id'], str) and
                     row['id'] and row['id'] not in ids, 'unique complete local constraint rows required')
            index = row['material_index']; tid = row['triangle_id']; weights = row['barycentric']
            _require(type(index) is int and index in active and type(tid) is int and 0 <= tid < len(triangles),
                     'constraint must name an active material index and actual triangle')
            _require(isinstance(weights, list) and len(weights) == 3 and all(_number(x) and 0 <= x <= 1 for x in weights)
                     and abs(math.fsum(weights)-1.) <= 1e-12 and _vector(row['point_cm']) and _vector(row['normal_world']),
                     'finite surface point, unit normal and barycentric provenance required')
            _require(isinstance(row['section_id'], str), 'section ID must be explicit')
            section = sections.get(row['section_id'])
            _require(section is not None and tid in section['triangle_ids'], 'triangle lacks measured section coverage')
            triangle = [vertices[i] for i in triangles[tid]]
            point = [math.fsum(weights[j]*triangle[j][k] for j in range(3)) for k in range(3)]
            normal = cross(sub(triangle[1], triangle[0]), sub(triangle[2], triangle[0]))
            size = math.sqrt(dot(normal, normal))
            _require(size > 1e-12, 'surface triangle is degenerate')
            normal = [x/size for x in normal]
            _require(math.dist(point, row['point_cm']) <= 1e-9 and math.dist(normal, row['normal_world']) <= 1e-10,
                     'point or normal contradicts actual oriented triangle')
            _require(_number(row['clearance_cm']) and 0 <= row['clearance_cm'] <= MAX_TRUST_RADIUS_CM and
                     _number(row['trust_radius_cm']) and 0 < row['trust_radius_cm'] <= MAX_TRUST_RADIUS_CM,
                     'finite bounded clearance and trust radius required')
            compiled = copy.deepcopy(row)
            compiled.update(representative=roots[index], triangle_cm=triangle, body_face_id=triangle_owners[tid])
            self.rows.append(compiled); ids.add(row['id']); covered.add(index)
        _require(covered == active, 'missing material-index surface coverage')
        # Opposed coincident-cohort planes can establish an impossible slab.
        by_root = {}
        for row in self.rows:
            self.check()
            for other in by_root.setdefault(row['representative'], []):
                self.check()
                if row['normal_world'] == [-x for x in other['normal_world']]:
                    lower = dot(row['normal_world'], row['point_cm'])+row['clearance_cm']
                    upper = dot(row['normal_world'], other['point_cm'])-other['clearance_cm']
                    _require(lower <= upper, 'contradictory opposite planes on a semantic cohort')
            by_root[row['representative']].append(row)
        self.fixed_roots = set(fixed_roots)
        first = self.observe(initial)
        _require(first['trust_domain_valid'], 'entry lies outside its measured local trust patch')

    def observe(self, coordinates):
        rows = []; energy = 0.; trusted = True; satisfied = True; fixed_violation = False
        for row in self.rows:
            self.check()
            point = coordinates[row['material_index']]
            offset = dot(sub(point, row['point_cm']), row['normal_world'])
            projection = [point[k]-offset*row['normal_world'][k] for k in range(3)]
            in_domain = (math.dist(point, row['point_cm']) <= row['trust_radius_cm'] and
                         math.dist(projection, closest_point_triangle(projection, row['triangle_cm'])) <= 1e-9)
            deficit = max(0., row['clearance_cm']-offset)
            search_deficit = max(0., row['clearance_cm']+self.margin-offset)
            _require(math.isfinite(offset) and math.isfinite(search_deficit), 'nonfinite local plane observation')
            trusted &= in_domain; satisfied &= deficit == 0.
            fixed_violation |= row['representative'] in self.fixed_roots and deficit > 0.
            energy += self.weight*search_deficit**2/2
            rows.append({'id': row['id'], 'material_index': row['material_index'],
                         'representative': row['representative'], 'signed_plane_offset_cm': offset,
                         'deficit_cm': deficit, 'trust_domain_valid': in_domain})
        _require(math.isfinite(energy), 'nonfinite constraint energy')
        return {'coordinate_sha256': digest(coordinates),
                'satisfied': bool(trusted and satisfied), 'trust_domain_valid': bool(trusted),
                'fixed_violation': bool(fixed_violation), 'max_deficit_cm': max(r['deficit_cm'] for r in rows),
                'energy': energy, 'rows': rows}

    def add_proximal_terms(self, coordinates, lookup, matrix, rhs, origin):
        for row in self.rows:
            self.check()
            root = row['representative']
            if root not in lookup:
                continue
            point = coordinates[root]
            offset = dot(sub(point, row['point_cm']), row['normal_world'])
            deficit = max(0., row['clearance_cm']+self.margin-offset)
            if not deficit:
                continue
            target = [point[k]+deficit*row['normal_world'][k] for k in range(3)]
            index = lookup[root]
            matrix[index][root] = matrix[index].get(root, 0.)+self.weight
            for k in range(3):
                rhs[k][index] += self.weight*(target[k]-origin[k])

    def report(self, initial, final):
        return {'version': 1, 'status': 'LOCAL_SAMPLE_CONSTRAINTS_SATISFIED' if final['satisfied'] else 'NEEDS_CORRECTION',
                'constraints_sha256': self.input_sha, 'identity': self.identity,
                'scope': 'EXPLICIT_MATERIAL_SAMPLES_LOCAL_ORIENTED_TRIANGLE_PLANES_ONLY',
                'coverage': 'ALL_SELECTED_MATERIAL_VERTICES_SAMPLED', 'continuous_body_clearance': 'NOT_QUALIFIED',
                'native_body_origin': 'NOT_AUTHENTICATED_BY_PORTABLE_KERNEL',
                'initial': initial, 'final': final, 'weight': self.weight, 'search_margin_cm': self.margin,
                'source_mutated': False, 'qualification': 'NONE', 'contacts': 'NOT_ASSESSED',
                'fitting': 'NOT_EXECUTED', 'simulation': 'NOT_EXECUTED'}
