"""Bind measured anatomical landmarks to immutable native source triangles.

Bindings protect numerical placement controls, never physical Cloth pins.
The only extra distance allowance models binary32 native coordinate storage:
8 unit-roundoffs per coordinate, propagated through the barycentric sum and
Euclidean norm. A guard exceeding 0.01 cm is refused, never enlarged silently.
"""
import copy
import math

from .cloth_metrics import face_sources
from .core import StudioError, digest


_MAX_ATTACHMENTS = 4096
_MAX_FACE_TESTS = 20000000
_FLOAT32_UNIT_ROUNDOFF = 2.**-24
_MAX_FLOAT32_GUARD_CM = .01


def _vector(value, size):
    return isinstance(value, (list, tuple)) and len(value) == size and all(
        type(x) in (int, float) and math.isfinite(x) for x in value)


def _coordinates(points, count):
    if not isinstance(points, (list, tuple)) or len(points) != count or not all(_vector(p, 3) for p in points):
        raise StudioError('Anatomical placement requires complete finite native coordinates')


def _point(points, indices, weights):
    return [math.fsum(weight*points[i][k] for i, weight in zip(indices, weights, strict=True)) for k in range(3)]


def bind_anatomical_attachments(payload, coordinates, declarations):
    """Resolve exact source UV ownership before any placement mutation."""
    if (not isinstance(declarations, list) or len(declarations) > _MAX_ATTACHMENTS
            or any(not isinstance(row, dict) or set(row) != {
                'piece', 'source_uv_cm', 'target_world_cm', 'tolerance_cm', 'source_ref'}
                or not isinstance(row.get('piece'), str) or row['piece'] not in payload.get('panels', {})
                or not _vector(row.get('source_uv_cm'), 2) or not _vector(row.get('target_world_cm'), 3)
                or type(row.get('tolerance_cm')) not in (int, float) or not math.isfinite(row['tolerance_cm'])
                or not 0 <= row['tolerance_cm'] <= 1.
                or not isinstance(row.get('source_ref'), str) or not row['source_ref'] for row in declarations)):
        raise StudioError('Native anatomical attachments require complete explicit source UV and measured target declarations')
    _coordinates(coordinates, len(payload['rest_cm']))
    source = face_sources(payload)
    if source['binding_issues']:
        raise StudioError('Native anatomical attachments require unchanged source face identities')
    pieces = {}
    for index, (uv, pid) in enumerate(zip(source['source_rest_triangles_cm'], source['source_face_pieces'], strict=True)):
        pieces.setdefault(pid, []).append((index, uv))
    if sum(len(pieces.get(row['piece'], [])) for row in declarations) > _MAX_FACE_TESTS:
        raise StudioError('Native anatomical source correspondence coverage exceeds its fixed bounded work budget')
    records = []; protected = set()
    for declaration in declarations:
        pid = declaration['piece']; point = declaration['source_uv_cm']; found = []
        for face_index, uv in pieces.get(pid, []):
            a, b, c = uv
            det = (b[0]-a[0])*(c[1]-a[1])-(b[1]-a[1])*(c[0]-a[0])
            if not math.isfinite(det) or abs(det) < 1e-12:
                raise StudioError('Native anatomical attachment cannot use degenerate original material triangles')
            beta = ((point[0]-a[0])*(c[1]-a[1])-(point[1]-a[1])*(c[0]-a[0]))/det
            gamma = ((b[0]-a[0])*(point[1]-a[1])-(b[1]-a[1])*(point[0]-a[0]))/det
            weights = [1-beta-gamma, beta, gamma]
            if min(weights) < -1e-10 or max(weights) > 1+1e-10:
                continue
            indices = list(payload['faces'][face_index])
            placed = _point(coordinates, indices, weights)
            scale = max(1., *(abs(x) for i in indices for x in coordinates[i]),
                        *(abs(x) for x in declaration['target_world_cm']))
            guard = 8*_FLOAT32_UNIT_ROUNDOFF*scale*math.sqrt(3)*math.fsum(abs(w) for w in weights)
            if not math.isfinite(guard) or guard > _MAX_FLOAT32_GUARD_CM:
                raise StudioError('Native anatomical binary32 uncertainty exceeds 0.01 cm; recenter or qualify coordinates')
            found.append({'face_index': face_index, 'source_uv_triangle_cm': copy.deepcopy(uv),
                'source_face_vertex_ids': source['source_face_vertex_ids'][face_index],
                'native_vertex_indices': indices, 'barycentric_weights': weights,
                'initial_point_cm': placed, 'native_float32_guard_cm': guard})
        if not found:
            raise StudioError('Anatomical source UV has no covering triangle in its exact source piece: '+pid)
        reference = found[0]
        # Shared source edges legitimately have several supporting triangles.
        # All must represent the same 3D material point, and all participating
        # controls remain protected. Overlapping inconsistent islands refuse.
        if any(math.dist(row['initial_point_cm'], reference['initial_point_cm']) >
               row['native_float32_guard_cm']+reference['native_float32_guard_cm'] for row in found[1:]):
            raise StudioError('Native anatomical source UV has ambiguous overlapping source support: '+pid)
        support = set()
        for row in found:
            support.update(i for i, weight in zip(row['native_vertex_indices'], row['barycentric_weights'], strict=True) if weight != 0)
        protected.update(support)
        residual = math.dist(reference['initial_point_cm'], declaration['target_world_cm'])
        if residual > declaration['tolerance_cm']+reference['native_float32_guard_cm']:
            raise StudioError('Native initial placement does not satisfy the measured anatomical attachment: '+pid)
        records.append({**copy.deepcopy(declaration), 'supports': found,
            'protected_indices': sorted(support), 'initial_residual_cm': residual,
            'native_float32_guard_cm': reference['native_float32_guard_cm']})
    result = {'version': 1, 'method': 'IMMUTABLE_SOURCE_TRIANGLE_ANATOMICAL_ATTACHMENTS',
        'coordinate_count': len(coordinates), 'source_declarations_sha256': digest(declarations),
        'source_binding_sha256': digest(source), 'native_topology_sha256': digest(payload['faces']),
        'entry_coordinates_sha256': digest(coordinates), 'protected_indices': sorted(protected),
        'protected_entry_coordinates_cm': {str(i): list(coordinates[i]) for i in sorted(protected)},
        'attachments': records,
        'binary32_guard_policy': '8_UNIT_ROUNDOFFS_COORDINATE_SCALE_BARYCENTRIC_L1_EUCLIDEAN_NORM_MAX_0.01_CM',
        'physical_pin_created': False, 'qualification': 'NONE'}
    result['binding_sha256'] = digest(result)
    return result


def observe_anatomical_attachments(binding, coordinates):
    """Evaluate targets and support drift against the original binding only."""
    _coordinates(coordinates, binding['coordinate_count'])
    reports = []; valid = True
    for row in binding['attachments']:
        residuals = [math.dist(_point(coordinates, support['native_vertex_indices'], support['barycentric_weights']),
            row['target_world_cm']) for support in row['supports']]
        errors = [residual <= row['tolerance_cm']+support['native_float32_guard_cm']
                  for residual, support in zip(residuals, row['supports'], strict=True)]
        drift = max((math.dist(coordinates[i], binding['protected_entry_coordinates_cm'][str(i)])
                     for i in row['protected_indices']), default=0.)
        preserved = all(errors) and drift <= row['native_float32_guard_cm']
        valid = valid and preserved
        reports.append({'piece': row['piece'], 'source_uv_cm': row['source_uv_cm'], 'source_ref': row['source_ref'],
            'target_world_cm': row['target_world_cm'], 'max_residual_cm': max(residuals),
            'declared_tolerance_cm': row['tolerance_cm'], 'native_float32_guard_cm': row['native_float32_guard_cm'],
            'max_support_displacement_cm': drift, 'preserved': preserved})
    return {'status': 'ANATOMICAL_ATTACHMENTS_PRESERVED' if valid else 'ANATOMICAL_ATTACHMENTS_CHANGED',
        'preserved': valid, 'attachments': reports, 'binding_sha256': binding['binding_sha256'],
        'candidate_sha256': digest(coordinates), 'physical_pin_created': False, 'qualification': 'NONE'}
