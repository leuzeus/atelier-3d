"""Bounded piecewise-linear lifting of explicit paths from source edge seeds.

No nearest selection, displacement, source editing or garment admission. The
domain is the supplied existing source-region union. Only this supplied path
is certified by the local walk; no interior atlas is inferred. This portable
kernel does not authenticate native provenance or derive garment bindings.
No automatic guide correction consumes its diagnostics.
"""
from collections import defaultdict
from fractions import Fraction as F
import math
from pathlib import Path
import time

from .core import StudioError, digest, sha


MAX_COORDINATE_CM = 1000000
MAX_QUERIES = 4096
MAX_WORK_EVENTS = 2000000


def _number(x):
    return type(x) in (int, float) and -MAX_COORDINATE_CM <= x <= MAX_COORDINATE_CM


class Refused(Exception):
    def __init__(self, reason, **data):
        self.reason = reason
        self.data = data
        super().__init__(reason)


def cross(a, b):
    return [a[1]*b[2]-a[2]*b[1], a[2]*b[0]-a[0]*b[2], a[0]*b[1]-a[1]*b[0]]


def sub(a, b):
    return [x-y for x, y in zip(a, b)]


def finite_vector(p):
    return isinstance(p, (list, tuple)) and len(p) == 3 and all(
        _number(x) for x in p)


class Surface:
    def __init__(self, vertices, triangles, owners, face_regions, allowed_regions,
                 direction, *, min_cosine=1e-9, max_seconds=120, max_events=100000,
                 clock=time.monotonic):
        self.clock = clock
        self.started = clock()
        self.max_seconds = max_seconds
        self.max_events = max_events
        self.events = 0
        if (type(max_seconds) not in (int, float) or not 0 < max_seconds <= 120
                or type(max_events) is not int or not 0 < max_events <= MAX_WORK_EVENTS):
            raise ValueError('Explicit bounded diagnostic budgets required')
        if not finite_vector(direction) or math.hypot(*direction) == 0:
            raise ValueError('Finite nonzero declared query direction required')
        if type(min_cosine) not in (int, float) or not 0 < min_cosine < 1:
            raise ValueError('Explicit positive transversality predicate required')
        if (not isinstance(vertices, list) or not 1 <= len(vertices) <= 100000
                or not isinstance(triangles, list) or not 1 <= len(triangles) <= 200000
                or not isinstance(owners, list) or len(triangles) != len(owners)
                or not isinstance(face_regions, list) or not 1 <= len(face_regions) <= 200000
                or any(type(label) is not int or not -2147483648 <= label <= 2147483647 for label in face_regions)):
            raise ValueError('Bounded exact native indexed geometry required')
        if (not isinstance(allowed_regions, list) or not 1 <= len(allowed_regions) <= 128
                or any(type(label) is not int for label in allowed_regions)
                or len(set(allowed_regions)) != len(allowed_regions)
                or not set(allowed_regions) <= set(face_regions)):
            raise ValueError('Explicit distinct existing regions required')
        # Store detached geometry. Reuse cannot accidentally combine a cached
        # projection with coordinates mutated by the caller between queries.
        self.vertices = []
        self.triangles = []
        self.owners = list(owners)
        self.regions = list(face_regions)
        self.allowed = set(allowed_regions)
        direction_scale = max(map(abs, direction))
        scaled_direction = [x/direction_scale for x in direction]
        size = math.hypot(*scaled_direction)
        self.direction = [x/size for x in scaled_direction]
        self.min_cosine = min_cosine
        self.axis = max(range(3), key=lambda k: abs(direction[k]))
        self.planar_axes = [k for k in range(3) if k != self.axis]
        self.rdirection = list(map(F, direction))
        self.rvertices = []
        self.projected = []
        for v in vertices:
            self.tick()
            if not finite_vector(v):
                raise ValueError('Finite body vertices required')
            rv = list(map(F, v))
            self.vertices.append(list(v))
            self.rvertices.append(rv)
            self.projected.append(self.project(rv))
        self.edge_triangles = defaultdict(list)
        self.vertex_triangles = defaultdict(set)
        self.by_owner = defaultdict(list)
        self.normals = {}
        self.cosines = {}
        self.domain_triangles = set()
        seen = set()
        for tid, tri in enumerate(triangles):
            self.tick()
            if (not isinstance(tri, list) or len(tri) != 3
                    or any(type(i) is not int or not 0 <= i < len(vertices) for i in tri) or len(set(tri)) != 3):
                raise ValueError('Actual native triangle required')
            key = tuple(sorted(tri))
            if key in seen:
                raise ValueError('Duplicated source triangle is not a unique surface')
            seen.add(key)
            self.triangles.append(list(tri))
            owner = owners[tid]
            if type(owner) is not int or not 0 <= owner < len(face_regions):
                raise ValueError('Exact source face owner required')
            self.by_owner[owner].append(tid)
            for a, b in zip(tri, tri[1:]+tri[:1]):
                self.edge_triangles[tuple(sorted((a, b)))].append(tid)
            for i in tri:
                self.vertex_triangles[i].add(tid)
            a, b, c = [self.rvertices[i] for i in tri]
            rational_normal = cross(sub(b, a), sub(c, a))
            scale = max(map(abs, rational_normal))
            if scale == 0:
                raise ValueError('Nondegenerate native surface required')
            # Ratio-first conversion keeps very small valid triangles from
            # underflowing when normals are used for transversality.
            normal = [float(x/scale) for x in rational_normal]
            length = math.hypot(*normal)
            self.normals[tid] = [x/length for x in normal]
            self.cosines[tid] = math.fsum(a*b for a, b in zip(self.normals[tid], self.direction))
            if face_regions[owner] in self.allowed:
                self.domain_triangles.add(tid)

    def tick(self):
        self.events += 1
        if self.events > self.max_events:
            raise Refused('WORK_BUDGET_EXHAUSTED')
        if self.clock()-self.started > self.max_seconds:
            raise Refused('TIME_BUDGET_EXHAUSTED')

    def project(self, p):
        # Affine quotient by the declared direction. Rational predicates avoid
        # tolerance-based merging at shared edges and subdivision vertices.
        k = self.axis
        return tuple(p[i]*self.rdirection[k]-p[k]*self.rdirection[i] for i in self.planar_axes)

    def barycentric(self, tid, q):
        a, b, c = [self.projected[i] for i in self.triangles[tid]]
        determinant = (b[0]-a[0])*(c[1]-a[1])-(b[1]-a[1])*(c[0]-a[0])
        if determinant == 0:
            raise Refused('TANGENT_PROJECTED_TRIANGLE', triangle=tid)
        u = ((q[0]-a[0])*(c[1]-a[1])-(q[1]-a[1])*(c[0]-a[0]))/determinant
        v = ((b[0]-a[0])*(q[1]-a[1])-(b[1]-a[1])*(q[0]-a[0]))/determinant
        return (1-u-v, u, v)

    def trace(self, seed_edge, seed_fraction, seed_faces, target):
        start = self.clock()
        traversed = []
        result = {'scope': 'DECLARED_SINGLE_PROJECTED_PATH_LIFT_ONLY', 'qualification': 'NONE',
                  'source_regions': sorted(self.allowed), 'source_mutated': False,
                  'nearest_selection': False, 'candidate_adjusted': False,
                  'global_projection_injectivity': 'NOT_CERTIFIED',
                  'min_cosine_predicate': self.min_cosine}
        try:
            self.tick()
            if (not isinstance(seed_edge, (list, tuple)) or len(seed_edge) != 2 or any(
                    type(i) is not int or not 0 <= i < len(self.vertices) for i in seed_edge)
                    or len(set(seed_edge)) != 2):
                raise Refused('INVALID_NATIVE_SEED_EDGE')
            if type(seed_fraction) not in (int, float) or not 0 < seed_fraction < 1:
                raise Refused('SEED_ENDPOINT_NOT_SUPPORTED_BY_EDGE_SEED_V1')
            if (not finite_vector(target) or not isinstance(seed_faces, (list, tuple))
                    or not 1 <= len(seed_faces) <= 2 or any(
                    type(f) is not int or not 0 <= f < len(self.regions) for f in seed_faces)
                    or len(set(seed_faces)) != len(seed_faces)):
                raise Refused('INVALID_SEED_OR_TARGET')
            fraction = F(seed_fraction)
            edge = tuple(sorted(seed_edge))
            incident = self.edge_triangles[edge]
            if not incident or len(incident) > 2:
                raise Refused('MISSING_OR_NONMANIFOLD_SEED_EDGE')
            actual_faces = sorted({self.owners[t] for t in incident if t in self.domain_triangles})
            if sorted(seed_faces) != actual_faces:
                raise Refused('SEED_FACE_INCIDENCES_DIFFER_FROM_DECLARED_DOMAIN', actual_faces=actual_faces)
            q0 = tuple(a+fraction*(b-a) for a, b in zip(self.projected[seed_edge[0]], self.projected[seed_edge[1]]))
            q1 = self.project(list(map(F, target)))
            seed_xyz = [a+fraction*(b-a) for a, b in zip(self.rvertices[seed_edge[0]], self.rvertices[seed_edge[1]])]
            result.update(seed_point_world_cm=list(map(float, seed_xyz)), target_world_cm=list(target),
                          path={'kind': 'STRAIGHT_SEGMENT_IN_DECLARED_DIRECTION_QUOTIENT',
                                'dropped_axis': self.axis,
                                'projected_seed': list(map(float, q0)), 'projected_target': list(map(float, q1))})
            if q0 == q1:
                raise Refused('ZERO_PROJECTED_PATH_NEEDS_SEED_NORMAL_CONE')
            cache = {}

            def interval(tid):
                self.tick()
                if tid in cache:
                    return cache[tid]
                if self.cosines[tid] <= self.min_cosine:
                    cache[tid] = None
                    return None
                left = self.barycentric(tid, q0)
                right = self.barycentric(tid, q1)
                slopes = tuple(b-a for a, b in zip(left, right))
                low, high = F(0), F(1)
                for a, slope in zip(left, slopes):
                    if slope == 0:
                        if a < 0:
                            cache[tid] = None
                            return None
                    elif slope > 0:
                        low = max(low, -a/slope)
                    else:
                        high = min(high, -a/slope)
                answer = (low, high, left, slopes) if low <= high else None
                cache[tid] = answer
                return answer

            candidates = [t for t in incident if t in self.domain_triangles and self.owners[t] in seed_faces]
            outgoing = [t for t in candidates if interval(t) is not None and interval(t)[0] == 0 and interval(t)[1] > 0]
            result['seed_incidence'] = {
                'ordered_edge_vertex_ids': list(seed_edge), 'edge_fraction': seed_fraction,
                'all_native_incident_source_faces': sorted({self.owners[t] for t in incident}),
                'all_authorized_incident_source_faces': actual_faces,
                'candidates': [{'triangle': t, 'source_face': self.owners[t],
                    'cosine': self.cosines[t], 'outgoing': t in outgoing,
                    'projected_path_interval': ([float(interval(t)[0]), float(interval(t)[1])]
                        if interval(t) is not None else None)} for t in candidates],
                'initial_choice_rule': 'ONE_ALLOWED_TRANSVERSE_INCIDENT_TRIANGLE_CONTAINS_POSITIVE_PATH_INTERVAL'}
            if len(outgoing) != 1:
                raise Refused('SEED_HAS_NO_UNIQUE_TRANSVERSE_OUTGOING_PATCH', outgoing=outgoing,
                              seed_cosines=[self.cosines[t] for t in candidates])
            current = outgoing[0]
            parameter = F(0)
            visited = set()
            terminal = None
            while True:
                self.tick()
                identity = current, parameter
                if identity in visited:
                    raise Refused('NONADVANCING_CONTINUATION')
                visited.add(identity)
                low, high, weights, slopes = interval(current)
                if not low <= parameter < high:
                    raise Refused('DISCONTINUOUS_PATCH_INTERVAL')
                traversed.append({'triangle': current, 'source_face': self.owners[current],
                                  'parameter_interval': [float(parameter), float(high)],
                                  'cosine': self.cosines[current]})
                if high == 1:
                    terminal = current
                    break
                at = tuple(a+high*b for a, b in zip(weights, slopes))
                zeros = [i for i, value in enumerate(at) if value == 0]
                tri = self.triangles[current]
                if len(zeros) == 1:
                    shared = tuple(sorted(tri[i] for i in range(3) if i not in zeros))
                    neighbours = self.edge_triangles[shared]
                    if len(neighbours) > 2:
                        raise Refused('NONMANIFOLD_CROSSED_EDGE')
                    local = set(neighbours)-{current}
                elif len(zeros) == 2:
                    vertex = tri[next(i for i in range(3) if i not in zeros)]
                    # Inspect the complete native star before limiting to the
                    # declared region. A hidden third incident face must not
                    # turn a nonmanifold native vertex into an admitted fan.
                    native_star = self.vertex_triangles[vertex]
                    native_adjacency = {t: set() for t in native_star}
                    for t in native_star:
                        self.tick()
                        for other in self.triangles[t]:
                            if other == vertex:
                                continue
                            edge_faces = self.edge_triangles[tuple(sorted((vertex, other)))]
                            if len(edge_faces) > 2:
                                raise Refused('NONMANIFOLD_VERTEX_STAR')
                            native_adjacency[t].update(set(edge_faces)&native_star-{t})
                    native_reached = {current}
                    native_pending = [current]
                    while native_pending:
                        self.tick()
                        t = native_pending.pop()
                        for other in native_adjacency[t]-native_reached:
                            native_reached.add(other); native_pending.append(other)
                    if native_reached != native_star or any(len(v) > 2 for v in native_adjacency.values()):
                        raise Refused('NONMANIFOLD_OR_DISCONNECTED_NATIVE_VERTEX_STAR')
                    local = native_star & self.domain_triangles
                    adjacency = {t: native_adjacency[t]&local for t in local}
                    reached = {current}
                    pending = [current]
                    while pending:
                        self.tick()
                        t = pending.pop()
                        for other in adjacency[t]-reached:
                            reached.add(other); pending.append(other)
                    if reached != local or any(len(v) > 2 for v in adjacency.values()):
                        raise Refused('NONMANIFOLD_OR_DISCONNECTED_VERTEX_STAR')
                    if any(self.cosines[t] <= self.min_cosine for t in local):
                        raise Refused('FOLD_OR_GRAZING_IN_CROSSED_VERTEX_STAR')
                    local -= {current}
                else:
                    raise Refused('UNREPRESENTABLE_EXIT_EVENT')
                allowed = local & self.domain_triangles
                outgoing = [t for t in allowed if interval(t) is not None and interval(t)[0] <= high < interval(t)[1]]
                if len(outgoing) != 1:
                    reason = ('AMBIGUOUS_OUTGOING_BRANCH' if len(outgoing) > 1 else
                              'FOLD_OR_GRAZING_AT_EXIT' if any(self.cosines[t] <= self.min_cosine for t in allowed) else
                              'DECLARED_REGION_BOUNDARY_OR_PATH_OUTSIDE_DOMAIN')
                    raise Refused(reason, parameter=float(high), outgoing=outgoing,
                                  local_source_faces=sorted({self.owners[t] for t in local}))
                current = outgoing[0]
                parameter = high
            weights = self.barycentric(terminal, q1)
            point = [sum(weights[j]*self.rvertices[i][k] for j, i in enumerate(self.triangles[terminal])) for k in range(3)]
            zeros = [j for j, value in enumerate(weights) if value == 0]
            if zeros:
                # An endpoint on a triangulation boundary is a surface point,
                # not a licence to select one of several normals. Report the
                # exact same point but leave its complete normal cone pending.
                normal_status = 'ENDPOINT_NORMAL_CONE_NOT_CERTIFIED'
            else:
                normal_status = 'INTERIOR_TRIANGLE_NORMAL'
            xyz = list(map(float, point))
            signed = math.fsum((xyz[k]-target[k])*self.direction[k] for k in range(3))
            residual = math.dist(xyz, [target[k]+signed*self.direction[k] for k in range(3)])
            result.update(status='LOCAL_PATH_LIFT_REACHED', selected_triangle=terminal,
                          selected_source_face=self.owners[terminal], point_world_cm=xyz,
                          barycentric=list(map(float, weights)), signed_ray_distance_cm=signed,
                          ray_reconstruction_residual_cm=residual,
                          normal_world=list(self.normals[terminal]), cosine=self.cosines[terminal],
                          endpoint_normal_status=normal_status,
                          minimum_traversed_cosine=min(row['cosine'] for row in traversed))
        except Refused as error:
            result.update(status='CONTINUATION_REFUSED', reason=error.reason, diagnostic=error.data)
        finished = self.clock()
        if finished-self.started > self.max_seconds and result.get('status') == 'LOCAL_PATH_LIFT_REACHED':
            terminal_fields = ('selected_triangle', 'selected_source_face', 'point_world_cm', 'barycentric',
                'signed_ray_distance_cm', 'ray_reconstruction_residual_cm', 'normal_world', 'cosine',
                'endpoint_normal_status', 'minimum_traversed_cosine')
            result['provisional_endpoint'] = {key: result.pop(key) for key in terminal_fields}
            result.update(status='CONTINUATION_REFUSED', reason='TIME_BUDGET_EXHAUSTED', diagnostic={})
        result.update(traversed=traversed, elapsed_seconds=finished-start,
                      work_events_cumulative=self.events)
        return result


def trace_surface_paths(vertices, triangles, owners, face_regions, policy, queries, *, clock=time.monotonic):
    """Replay a bounded batch on one declared domain with exact input hashes.

    All source-edge seeds and targets are explicit input. Native origin and
    source-seam derivation remain the caller's responsibility. A reached path
    only identifies a local surface point; reserve, segment/face contacts,
    interior coverage and fitting are not admitted by this function.
    """
    required = {'method', 'source_region_ids', 'direction_world', 'min_cosine', 'max_seconds', 'max_events'}
    query_fields = {'request_id', 'seed_edge_vertex_ids', 'seed_fraction', 'seed_face_ids', 'target_world_cm'}
    if (not isinstance(policy, dict) or set(policy) != required
            or policy['method'] != 'SEEDED_SURFACE_PATH_LIFT_V1'
            or not isinstance(queries, list) or not 1 <= len(queries) <= MAX_QUERIES):
        raise StudioError('Surface continuation requires its exact bounded policy and query list')
    identifiers = set()
    for query in queries:
        if (not isinstance(query, dict) or set(query) != query_fields
                or not isinstance(query['request_id'], str) or not 1 <= len(query['request_id']) <= 160
                or query['request_id'] in identifiers):
            raise StudioError('Surface continuation requires distinct bounded exact query identities')
        identifiers.add(query['request_id'])
        if (not isinstance(query['seed_edge_vertex_ids'], list) or len(query['seed_edge_vertex_ids']) != 2
                or any(type(i) is not int or not 0 <= i < 100000 for i in query['seed_edge_vertex_ids'])
                or type(query['seed_fraction']) not in (int, float) or not 0 <= query['seed_fraction'] <= 1
                or not isinstance(query['seed_face_ids'], list) or not 1 <= len(query['seed_face_ids']) <= 2
                or any(type(i) is not int or not 0 <= i < 200000 for i in query['seed_face_ids'])
                or not finite_vector(query['target_world_cm'])):
            raise StudioError('Surface continuation requires bounded numeric query values')
    # Build/validate before hashing arrays or copying metadata. Geometry work
    # and every query share one deadline and one cumulative event allowance.
    try:
        surface = Surface(vertices, triangles, owners, face_regions, policy['source_region_ids'],
            policy['direction_world'], min_cosine=policy['min_cosine'], max_seconds=policy['max_seconds'],
            max_events=policy['max_events'], clock=clock)
    except Refused as error:
        return {'version': 1, 'status': 'CONTINUATION_INCOMPLETE', 'reason': error.reason,
                'rows': [], 'unprocessed_queries': len(queries), 'qualification': 'NONE',
                'native_provenance': 'CALLER_MUST_VERIFY', 'source_mutated': False}
    except (ValueError, OverflowError, TypeError) as error:
        raise StudioError('Surface continuation: '+str(error)) from error
    identities = {'vertices_sha256': digest(surface.vertices), 'triangles_sha256': digest(surface.triangles),
        'owners_sha256': digest(surface.owners), 'face_regions_sha256': digest(surface.regions),
        'policy_sha256': digest(policy), 'queries_sha256': digest(queries),
        'kernel_sha256': sha(Path(__file__))}
    rows = []
    for query in queries:
        row = surface.trace(query['seed_edge_vertex_ids'], query['seed_fraction'], query['seed_face_ids'],
                            query['target_world_cm'])
        row['request_id'] = query['request_id']
        rows.append(row)
        if row.get('reason') in ('TIME_BUDGET_EXHAUSTED', 'WORK_BUDGET_EXHAUSTED'):
            break
    elapsed = clock()-surface.started
    expired = elapsed > policy['max_seconds']
    return {'version': 1, 'method': policy['method'], 'identities': identities,
        'status': 'LOCAL_PATHS_REACHED' if not expired and len(rows) == len(queries) and all(
            row['status'] == 'LOCAL_PATH_LIFT_REACHED' for row in rows) else 'CONTINUATION_INCOMPLETE',
        **({'reason': 'TIME_BUDGET_EXHAUSTED'} if expired else {}),
        'rows': rows, 'unprocessed_queries': len(queries)-len(rows),
        'elapsed_seconds': elapsed, 'work_events': surface.events,
        'native_provenance': 'CALLER_MUST_VERIFY', 'source_mutated': False,
        'candidate_adjusted': False, 'reserve_admission': 'NOT_GRANTED',
        'contact_admission': 'NOT_GRANTED', 'fitting': 'NOT_EXECUTED', 'qualification': 'NONE'}
