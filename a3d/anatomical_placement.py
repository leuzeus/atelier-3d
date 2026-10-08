"""Explicit, source-bound anatomical references and generic curve placement.

The body frame, measured paths and the caller's region selections are inputs.
No rig joint is substituted for a skin reference and no anatomical direction is
guessed. These portable checks establish numerical identity, not human review,
native provenance, collision clearance, material admission or garment fitting.
"""
import copy
import math

from .core import StudioError, digest


STANDARD_REGIONS = (
    'head', 'neck', 'torso', 'pelvis',
    *(part+'.'+side for side in ('left', 'right') for part in
      ('upper_arm', 'lower_arm', 'hand', 'upper_leg', 'lower_leg', 'foot')),
    *(part+'.'+digit+'.'+side for side in ('left', 'right') for part, digits in
      (('finger', ('thumb', 'index', 'middle', 'ring', 'little')),
       ('toe', ('great', 'second', 'third', 'fourth', 'little'))) for digit in digits),
)
MAX_PATH_POINTS = 8192
MAX_REFERENCES = 128
MAX_REQUESTS = 512


def _finite(value):
    return type(value) in (int, float) and math.isfinite(value)


def _point(value):
    return isinstance(value, (list, tuple)) and len(value) == 3 and all(map(_finite, value))


def _hash(value):
    return isinstance(value, str) and len(value) == 64 and all(c in '0123456789abcdef' for c in value)


def _name(value):
    return isinstance(value, str) and 0 < len(value) <= 160 and value.strip() == value


def _region(value):
    return value in STANDARD_REGIONS if isinstance(value, str) and not value.startswith('custom:') else (
        _name(value) and value.startswith('custom:') and bool(value[7:].strip()))


def _dot(a, b):
    return math.fsum(x*y for x, y in zip(a, b))


def _cross(a, b):
    return [a[1]*b[2]-a[2]*b[1], a[2]*b[0]-a[0]*b[2], a[0]*b[1]-a[1]*b[0]]


def _unit(value):
    if not _point(value):
        raise StudioError('Anatomical placement requires a finite explicit three-dimensional direction')
    length = math.hypot(*value)
    if not math.isfinite(length) or length <= 1e-10:
        raise StudioError('Anatomical placement direction is collapsed or nonfinite')
    return [x/length for x in value]


def _basis(value):
    if not isinstance(value, dict) or any(not _point(value.get(k)) for k in ('right', 'forward', 'up', 'origin_cm')):
        raise StudioError('Anatomical placement needs the complete finite body frame')
    axes = [value[k] for k in ('right', 'forward', 'up')]
    if (any(abs(_dot(axis, axis)-1) > 1e-7 for axis in axes) or
            any(abs(_dot(axes[a], axes[b])) > 1e-7 for a, b in ((0, 1), (0, 2), (1, 2))) or
            math.dist(_cross(axes[0], axes[1]), axes[2]) > 1e-7):
        raise StudioError('Anatomical body frame must be right-handed and orthonormal')
    return axes


def _profile(profile):
    if (not isinstance(profile, dict) or profile.get('status') != 'PROFILE_MEASURED' or
            profile.get('segmentation') != 'EXPLICIT_SOURCE' or not _hash(profile.get('cache_key')) or
            any(not _hash(profile.get(k)) for k in ('source_sha256', 'pose_sha256', 'geometry_sha256'))):
        raise StudioError('Anatomical placement requires the exact measured segmented body profile')
    return _basis(profile.get('frame'))


def _path(points, closed):
    if (type(closed) is not bool or not isinstance(points, (list, tuple)) or
            not (3 if closed else 2) <= len(points) <= MAX_PATH_POINTS or any(not _point(p) for p in points)):
        raise StudioError('Anatomical path needs bounded finite vertices and explicit open/closed topology')
    segments = list(zip(points, list(points[1:])+([points[0]] if closed else [])))
    lengths = [math.dist(a, b) for a, b in segments]
    if any(not math.isfinite(x) or x <= 1e-10 for x in lengths):
        raise StudioError('Anatomical path has collapsed or nonfinite segments; do not repeat its closing vertex')
    total = math.fsum(lengths)
    if not math.isfinite(total):
        raise StudioError('Anatomical path length is nonfinite')
    return segments, lengths, total


def _samples(points, fractions, closed):
    segments, lengths, total = _path(points, closed)
    if (not isinstance(fractions, (list, tuple)) or not 1 <= len(fractions) <= MAX_PATH_POINTS or
            any(not _finite(f) or not 0 <= f <= 1 for f in fractions)):
        raise StudioError('Anatomical path samples require bounded explicit fractions in [0, 1]')
    cumulative = [0.]
    for length in lengths:
        cumulative.append(cumulative[-1]+length)
    import bisect
    result = []
    for fraction in fractions:
        distance = (0. if closed and fraction == 1 else fraction)*total
        index = min(bisect.bisect_right(cumulative, distance)-1, len(segments)-1)
        a, b = segments[index]
        t = min(1., max(0., (distance-cumulative[index])/lengths[index]))
        point = [(1-t)*x+t*y for x, y in zip(a, b)]
        tangent = [(y-x)/lengths[index] for x, y in zip(a, b)]
        result.append((point, tangent, distance))
    return result


def _geometry_snapshot(profile, geometry):
    """Index a caller-supplied exact mesh once for all selected report paths."""
    if geometry is None:
        return None
    if not isinstance(geometry, dict) or not isinstance(profile, dict):
        raise StudioError('Anatomical references require an explicit evaluated geometry document')
    vertices = geometry.get('vertices_cm'); faces = geometry.get('faces'); labels = geometry.get('face_sets')
    if (not isinstance(vertices, list) or not 3 <= len(vertices) <= 500000 or any(not _point(p) for p in vertices) or
            not isinstance(faces, list) or not 1 <= len(faces) <= 500000 or
            not isinstance(labels, list) or len(labels) != len(faces) or any(type(v) is not int or v < 0 for v in labels) or
            any(geometry.get(key) != profile.get(key) for key in ('source_sha256', 'pose_sha256')) or
            digest([vertices, faces]) != profile.get('geometry_sha256')):
        raise StudioError('Anatomical reference geometry, pose, source or region labels are missing/stale')
    owners = {}; count = 0
    for face_id, face in enumerate(faces):
        if (not isinstance(face, list) or len(face) < 3 or
                any(type(i) is not int or not 0 <= i < len(vertices) for i in face) or len(set(face)) != len(face)):
            raise StudioError('Anatomical reference geometry has invalid source polygon faces')
        count += len(face)
        if count > 2000000:
            raise StudioError('Anatomical reference geometry edge incidence budget exceeded')
        for a, b in zip(face, face[1:]+face[:1]):
            owners.setdefault(tuple(sorted((a, b))), []).append(face_id)
    return {'vertices': vertices, 'labels': labels, 'owners': owners, 'face_sets_sha256': digest(labels)}


def sample_path(points, fractions, *, closed):
    """Sample actual piecewise-linear arclength; never extrapolate or rescale.

    A closed fraction 1 is its existing first point. An open fraction 1 is its
    final point. Inputs remain immutable and fractions need not be sorted.
    """
    return [point for point, _, _ in _samples(points, fractions, closed)]


def path_frames(points, fractions, *, closed, reference_normal,
                transverse_field='SEGMENT_ORTHOGONAL_V1'):
    """Orient fibres from a declared reference field, not an inferred body up.

    The explicit direction is projected normal to each sampled tangent. At an
    exact corner the outgoing segment wins (the last segment at an open end).
    A parallel direction is unsupported and refused, rather than choosing a
    fallback axis. This is not a smooth/parallel-transport or offset-surface
    construction; curves with sharp corners still need metric/contact checks.
    BODY_DIRECTION_CONSTANT_V1 instead retains the declared unit direction at
    every sample. It is continuous across path corners but is not generally
    orthogonal to the tangent, so shear must still be measured. The returned
    binormal is their cross product; a parallel field is explicitly refused.
    """
    if transverse_field not in ('SEGMENT_ORTHOGONAL_V1', 'BODY_DIRECTION_CONSTANT_V1'):
        raise StudioError('Anatomical path needs a supported explicit transverse field')
    normal_ref = _unit(reference_normal)
    output = []
    for point, tangent, distance in _samples(points, fractions, closed):
        if transverse_field == 'BODY_DIRECTION_CONSTANT_V1':
            normal = list(normal_ref)
            if math.hypot(*_cross(tangent, normal)) <= 1e-10:
                raise StudioError('Constant anatomical transverse field is parallel to the path tangent')
        else:
            projection = _dot(normal_ref, tangent)
            normal = _unit([normal_ref[i]-projection*tangent[i] for i in range(3)])
        output.append({'point_cm': point, 'tangent': tangent, 'normal': normal,
                       'binormal': _cross(tangent, normal), 'arclength_cm': distance})
    return output


def resolve_measured_path(profile, report, path_id, *, expected_report_sha256, region, geometry=None):
    """Bind one existing source-edge path to the exact measured body's frame.

    Accepts the existing closed ``body_source_paths`` and open
    ``body_surface_paths`` reports. The report hash must be supplied by the
    caller's reference manifest. File/native receipt and human-review checks
    belong to that caller; the kernel does not manufacture such approval.
    """
    return _resolve_measured_path(profile, report, path_id, expected_report_sha256=expected_report_sha256,
        region=region, geometry_snapshot=_geometry_snapshot(profile, geometry))


def _resolve_measured_path(profile, report, path_id, *, expected_report_sha256, region, geometry_snapshot):
    axes = _profile(profile)
    if (not isinstance(report, dict) or not _hash(expected_report_sha256) or
            digest(report) != expected_report_sha256 or not _name(path_id) or not _region(region)):
        raise StudioError('Anatomical path binding has missing/stale report identity or unsupported region')
    expected_status = {'BODY_SOURCE_PATHS_MEASURED_FOR_REVIEW': True,
                       'BODY_SURFACE_OPEN_PATH_PROPOSALS_FOR_REVIEW': False}
    if report.get('status') not in expected_status:
        raise StudioError('Anatomical binding requires an existing measured source-path report')
    identity = report.get('identity')
    if (not isinstance(identity, dict) or report.get('frame') != profile['frame'] or
            any(identity.get(k) != profile[k] for k in ('source_sha256', 'pose_sha256', 'geometry_sha256')) or
            ('profile_sha256' in identity and identity['profile_sha256'] != digest(profile)) or
            ('profile_cache_key' in identity and identity['profile_cache_key'] != profile['cache_key'])):
        raise StudioError('Anatomical path report source, pose, geometry, profile or body frame is stale')
    rows = report.get('paths')
    if not isinstance(rows, list) or not 1 <= len(rows) <= MAX_REFERENCES or any(not isinstance(row, dict) for row in rows):
        raise StudioError('Anatomical path report requires bounded explicit rows')
    selected = [row for row in rows if row.get('id') == path_id]
    if len(selected) != 1:
        raise StudioError('Anatomical path must have one unambiguous measured report row: '+path_id)
    row = selected[0]; closed = row.get('closed')
    if type(closed) is not bool or closed != expected_status[report['status']]:
        raise StudioError('Anatomical path topology differs from its measured report kind')
    points = row.get('curve_world_cm' if closed else 'polyline_world_cm')
    _, _, length = _path(points, closed)
    vertex_ids = row.get('vertex_ids'); regions = row.get('source_regions' if closed else 'domain_region_ids')
    if (not isinstance(vertex_ids, list) or len(vertex_ids) != len(points) or
            any(type(i) is not int or i < 0 for i in vertex_ids) or len(set(vertex_ids)) != len(vertex_ids) or
            not isinstance(regions, list) or not regions or any(type(i) is not int or i < 0 for i in regions) or
            len(set(regions)) != len(regions)):
        raise StudioError('Anatomical path needs distinct actual source vertices and explicit source regions')
    pairs = list(zip(vertex_ids, vertex_ids[1:]+([vertex_ids[0]] if closed else [])))
    if row.get('edge_vertex_ids') != [list(pair) for pair in pairs]:
        raise StudioError('Anatomical path must preserve measured source-edge order')
    if geometry_snapshot is not None:
        mesh = geometry_snapshot; vertices = mesh['vertices']; labels = mesh['labels']
        if (identity.get('face_sets_sha256') != mesh['face_sets_sha256'] or
                any(i >= len(vertices) for i in vertex_ids) or points != [vertices[i] for i in vertex_ids]):
            raise StudioError('Anatomical path coordinates or source regions differ from the exact evaluated mesh')
        source_faces = row.get('edge_source_face_ids')
        if not isinstance(source_faces, list) or len(source_faces) != len(pairs):
            raise StudioError('Anatomical path needs exact source face incidence provenance')
        for pair, claimed_faces in zip(pairs, source_faces):
            actual = mesh['owners'].get(tuple(sorted(pair)), [])
            selected_faces = [i for i in actual if labels[i] in regions]
            if (not actual or len(actual) > 2 or claimed_faces != selected_faces or
                    not selected_faces or (closed and (len(actual) != 2 or {labels[i] for i in actual} != set(regions)))):
                raise StudioError('Anatomical path source-edge/region incidence differs from exact evaluated geometry')
    measured = row.get('length_cm' if closed else 'edge_arclength_cm')
    if not _finite(measured) or abs(measured-length) > max(1e-8, length*1e-10):
        raise StudioError('Anatomical path length differs from its source-edge polyline')
    origin = profile['frame']['origin_cm']
    local = [[_dot([p[i]-origin[i] for i in range(3)], axis) for axis in axes] for p in points]
    return {'path_id': path_id, 'region': region, 'source_region_ids': sorted(regions),
            'points_body_cm': local, 'points_world_cm': copy.deepcopy(points), 'closed': closed,
            'length_cm': length, 'report_sha256': expected_report_sha256, 'path_sha256': digest(row),
            'profile_sha256': digest(profile), 'reference_kind': 'SOURCE_MESH_EDGE_PATH',
            'vertex_ids': copy.deepcopy(vertex_ids), 'edge_vertex_ids': [list(pair) for pair in pairs],
            'anatomical_homology': 'EXPLICIT_SELECTION_NOT_QUALIFIED',
            'geometry_validation': 'EXACT_SOURCE_EDGES_VERIFIED' if geometry_snapshot is not None else 'CALLER_MUST_VERIFY',
            'native_provenance': 'CALLER_MUST_VERIFY', 'human_review': 'CALLER_MUST_VERIFY',
            'fitting': 'NOT_EXECUTED', 'acceptance': 'NOT_GRANTED'}


def validate_anatomical_references(profile, document, *, geometry=None):
    """Normalize a hash-bound manifest; family-specific piece rules stay data.

    ``paths[id]`` contains report, report_sha256, path_id and region.
    ``pieces[id]`` is copied for the family guide dispatcher to validate. This
    API does not interpret a role label as proof of anatomical correspondence.
    """
    _profile(profile)
    if (not isinstance(document, dict) or type(document.get('version')) is not int or document['version'] != 1 or
            document.get('profile_sha256') != digest(profile) or
            not isinstance(document.get('paths'), dict) or len(document['paths']) > MAX_REFERENCES or
            not isinstance(document.get('pieces'), dict) or len(document['pieces']) > MAX_REQUESTS):
        raise StudioError('Anatomical references require a bounded manifest bound to the exact profile')
    if not document['paths'] and (geometry is None or not document['pieces'] or
                                  not isinstance(document.get('triangles'), list) or not document['triangles']):
        raise StudioError('Surface-only anatomical references require exact geometry, triangles and nonempty piece policies')
    snapshot = _geometry_snapshot(profile, geometry); output = {}
    for ref_id, binding in sorted(document['paths'].items()):
        if not _name(ref_id) or not isinstance(binding, dict):
            raise StudioError('Anatomical reference IDs and bindings must be explicit')
        output[ref_id] = _resolve_measured_path(profile, binding.get('report'), binding.get('path_id'),
            expected_report_sha256=binding.get('report_sha256'), region=binding.get('region'), geometry_snapshot=snapshot)
    if any(not _name(pid) or not isinstance(rule, dict) for pid, rule in document['pieces'].items()):
        raise StudioError('Anatomical piece bindings must have explicit IDs and policy objects')
    result = {'version': 1, 'profile_sha256': digest(profile), 'paths': output,
              'pieces': copy.deepcopy(document['pieces']), 'manifest_sha256': digest(document),
              'source_mutated': False, 'anatomical_gate': 'NOT_GRANTED', 'fitting': 'NOT_EXECUTED'}
    if 'triangles' in document:
        triangles = document['triangles']
        if (snapshot is None or not isinstance(triangles, list) or not 1 <= len(triangles) <= 1000000 or
                any(not isinstance(face, list) or len(face) != 3 or
                    any(type(i) is not int or not 0 <= i < len(snapshot['vertices']) for i in face) or
                    len(set(face)) != 3 for face in triangles)):
            raise StudioError('Anatomical triangle references need exact geometry and bounded distinct source vertex indices')
        result['triangles'] = copy.deepcopy(triangles)
        result['triangles_sha256'] = digest(triangles)
        result['triangulation_provenance'] = 'SURFACE_CONSUMER_MUST_VERIFY_NATIVE_TRIANGULATION'
    return result


def region_coverage(references, requests=None):
    """Report actual inputs for every body region, never universal fit support.

    Pass normalized references from ``validate_anatomical_references`` and
    optional rows ``{region, primitive, reference_id?}``. Supported primitives
    are the reusable measured-path sampling and explicit curve-frame kernels.
    Unknown named regions require the explicit ``custom:`` prefix and a bound
    source path. A catalog entry alone does not supply a missing measurement.
    """
    paths = references.get('paths') if isinstance(references, dict) else None
    if not isinstance(paths, dict) or len(paths) > MAX_REFERENCES:
        raise StudioError('Anatomical coverage needs normalized path references')
    if requests is None:
        regions = sorted(set(STANDARD_REGIONS) | {p.get('region') for p in paths.values() if isinstance(p, dict) and _region(p.get('region'))})
        requests = [{'region': region, 'primitive': 'path_frames'} for region in regions]
    if not isinstance(requests, list) or len(requests) > MAX_REQUESTS or any(not isinstance(r, dict) for r in requests):
        raise StudioError('Anatomical coverage needs bounded explicit requests')
    output = []
    for request in requests:
        region = request.get('region'); primitive = request.get('primitive'); reference = request.get('reference_id')
        matches = sorted(key for key, row in paths.items() if isinstance(row, dict) and row.get('region') == region and
                         (reference is None or reference == key))
        if not _region(region):
            state = 'UNSUPPORTED_REGION_REQUIRES_EXPLICIT_CUSTOM_BINDING'
        elif primitive not in ('sample_path', 'path_frames'):
            state = 'UNSUPPORTED_PRIMITIVE'
        elif not matches:
            state = 'MISSING_MEASURED_REFERENCE'
        else:
            state = 'MEASURED_REFERENCE_AVAILABLE'
        output.append({'region': region, 'primitive': primitive, 'reference_ids': matches, 'status': state})
    return {'version': 1, 'regions': output, 'qualification': 'REFERENCE_COVERAGE_ONLY',
            'guide_geometry': 'NOT_EVALUATED', 'contacts': 'NOT_EVALUATED', 'fitting': 'NOT_EXECUTED',
            'acceptance': 'NOT_GRANTED'}
