"""Read-only, measured dressing admission on evaluated collider cages.

The caller owns checkpoints and activation. This module changes no object,
source pattern, support or collider and performs no projection/correction.
"""
import math

from a3d.core import StudioError, digest, inside, sha
from a3d.dressing import (migrate_legacy_layers, source_references,
                         validate_dressing, select_colliders)


def _sub(a, b):
    return [x-y for x, y in zip(a, b)]


def _dot(a, b):
    return sum(x*y for x, y in zip(a, b))


def _cross(a, b):
    return [a[1]*b[2]-a[2]*b[1], a[2]*b[0]-a[0]*b[2], a[0]*b[1]-a[1]*b[0]]


def _unit(a):
    length = math.sqrt(_dot(a, a))
    if length <= 1e-12:
        raise StudioError('Degenerate dressing axis or normal')
    return [x/length for x in a]


def _basis(axis):
    normal = _unit(axis)
    seed = min(([1., 0., 0.], [0., 1., 0.], [0., 0., 1.]), key=lambda v: abs(_dot(v, normal)))
    u = _unit(_cross(seed, normal))
    return normal, u, _cross(normal, u)


def _project(point, origin, u, v):
    delta = _sub(point, origin)
    return [_dot(delta, u), _dot(delta, v)]


def _point_segment(point, a, b):
    edge = _sub(b, a)
    length = _dot(edge, edge)
    t = max(0., min(1., _dot(_sub(point, a), edge)/length)) if length else 0.
    return math.dist(point, [x+t*y for x, y in zip(a, edge)])


def _inside(point, polygon):
    inside_value = False
    for a, b in zip(polygon, polygon[1:]+polygon[:1]):
        if (a[1] > point[1]) != (b[1] > point[1]):
            if point[0] < a[0]+(point[1]-a[1])*(b[0]-a[0])/(b[1]-a[1]):
                inside_value = not inside_value
    return inside_value


def _crosses(a, b, c, d):
    def orient(p, q, r):
        return (q[0]-p[0])*(r[1]-p[1])-(q[1]-p[1])*(r[0]-p[0])
    return orient(a, b, c)*orient(a, b, d) < -1e-16 and orient(c, d, a)*orient(c, d, b) < -1e-16


def _segment_distance(a, b, c, d):
    if _crosses(a, b, c, d):
        return 0.
    return min(_point_segment(a, c, d), _point_segment(b, c, d),
               _point_segment(c, a, b), _point_segment(d, a, b))


def _section_edges_touch(a, b, c, d, epsilon):
    if any(max(a[k], b[k])+epsilon < min(c[k], d[k]) or
           max(c[k], d[k])+epsilon < min(a[k], b[k]) for k in (0, 1)):
        return False
    return _segment_distance(a, b, c, d) <= epsilon


def capture_collider(obj):
    """Capture evaluated triangles in world centimetres, without modifiers edits."""
    import bpy
    evaluated = obj.evaluated_get(bpy.context.evaluated_depsgraph_get())
    mesh = evaluated.to_mesh()
    if mesh is None:
        raise StudioError('Dressing collider has no evaluated mesh: '+obj.name)
    try:
        mesh.calc_loop_triangles()
        result = {'object': obj.name,
                  'vertices_cm': [[float(x)*100 for x in evaluated.matrix_world @ vertex.co] for vertex in mesh.vertices],
                  'faces': [list(face.vertices) for face in mesh.loop_triangles],
                  'geometry': 'EVALUATED_NATIVE_TRIANGLE_CAGE'}
        result['sha256'] = digest(result)
        return result
    finally:
        evaluated.to_mesh_clear()


def _select_axis_section(segments, origin_cm, axis, epsilon):
    """Partition the complete section before selecting by the sourced axis only.

    The garment opening is deliberately unavailable here: choosing the loop
    which fits the garment would conceal a placement or source-axis defect.
    Every excluded component remains inspectable in ``loops``.
    """
    def key(point):
        return tuple(round(value/epsilon) for value in point)

    adjacency, points = {}, {}
    for index, segment in enumerate(segments):
        for point in segment:
            node = key(point)
            points.setdefault(node, point)
            adjacency.setdefault(node, []).append(index)
    report = {'ok': False, 'segments_cm': segments,
              'triangle_intersection_count': len(segments),
              'coverage': 'ACTUAL_EVALUATED_TRIANGLE_PLANE_INTERSECTION',
              'selection': 'UNIQUE_CLOSED_LOOP_CONTAINING_SOURCED_AXIS',
              'axis_origin_cm': list(origin_cm), 'loops': [], 'excluded_loops': []}
    if not segments or any(len(edges) != 2 for edges in adjacency.values()):
        return dict(report, reason='SECTION_NOT_CLOSED_OR_EMPTY')

    _, u, v = _basis(axis)
    remaining = set(range(len(segments)))
    polygons, components = [], []
    while remaining:
        first = min(remaining)
        start = key(segments[first][0])
        node, edge = start, first
        nodes, indices = [], []
        while True:
            if edge not in remaining:
                return dict(report, reason='SECTION_LOOP_TRAVERSAL_AMBIGUOUS')
            remaining.remove(edge)
            nodes.append(node)
            indices.append(edge)
            a, b = (key(point) for point in segments[edge])
            node = b if node == a else a
            if node == start:
                break
            edge = next(index for index in adjacency[node] if index != edge)
        loop_points = [points[node] for node in nodes]
        polygon = [_project(point, origin_cm, u, v) for point in loop_points]
        axis_distance = min(_point_segment([0., 0.], a, b)
                            for a, b in zip(polygon, polygon[1:]+polygon[:1]))
        loop = {'index': len(polygons), 'points_cm': loop_points,
                'source_segment_indices': indices, 'segment_count': len(indices),
                'contains_sourced_axis': _inside([0., 0.], polygon),
                'minimum_axis_boundary_distance_cm': axis_distance}
        report['loops'].append(loop)
        polygons.append(polygon)
        components.append(indices)

    # Touching/crossing components cannot be treated as independent body parts.
    # The same numerical band as triangle joining is used, never physical reserve.
    for index, polygon in enumerate(polygons):
        area2 = sum(a[0]*b[1]-b[0]*a[1] for a, b in zip(polygon, polygon[1:]+polygon[:1]))
        if len(polygon) < 3 or abs(area2) <= epsilon*epsilon:
            return dict(report, reason='DEGENERATE_SECTION_LOOP', ambiguous_loops=[index])
        edges = list(zip(polygon, polygon[1:]+polygon[:1]))
        for i, (a, b) in enumerate(edges):
            for j in range(i+1, len(edges)):
                if j == i+1 or (i == 0 and j == len(edges)-1):
                    continue
                if _section_edges_touch(a, b, *edges[j], epsilon):
                    return dict(report, reason='SELF_INTERSECTING_SECTION_LOOP', ambiguous_loops=[index])
        for other in range(index):
            other_edges = zip(polygons[other], polygons[other][1:]+polygons[other][:1])
            for c, d in other_edges:
                if any(_section_edges_touch(a, b, c, d, epsilon) for a, b in edges):
                    return dict(report, reason='SECTION_LOOPS_TOUCH_OR_INTERSECT', ambiguous_loops=[other, index])

    touching = [loop['index'] for loop in report['loops']
                if loop['minimum_axis_boundary_distance_cm'] <= epsilon]
    if touching:
        return dict(report, reason='SOURCED_AXIS_TOUCHES_SECTION', ambiguous_loops=touching)
    containing = [loop['index'] for loop in report['loops'] if loop['contains_sourced_axis']]
    if len(containing) != 1:
        return dict(report, reason=('SOURCED_AXIS_OUTSIDE_SECTION_LOOPS' if not containing
                                    else 'SOURCED_AXIS_IN_MULTIPLE_SECTION_LOOPS'),
                    containing_loops=containing)
    selected = containing[0]
    report.update(ok=True, selected_loop=selected,
                  segments_cm=[segments[index] for index in components[selected]],
                  selected_segment_count=len(components[selected]),
                  excluded_loops=[{'index': loop['index'], 'reason': 'DOES_NOT_CONTAIN_SOURCED_AXIS'}
                                  for loop in report['loops'] if loop['index'] != selected])
    return report


def section_segments(geometry, origin_cm, axis):
    """Actual triangle/plane intersection, requiring a closed collider cage.

    The numerical band resolves duplicate triangle intersections only. It is
    not a clearance or penetration allowance. Ambiguous sections are refused.
    """
    vertices, faces = geometry['vertices_cm'], geometry['faces']
    edges = {}
    for face in faces:
        for a, b in zip(face, face[1:]+face[:1]):
            key = tuple(sorted((a, b)))
            edges[key] = edges.get(key, 0)+1
    if not faces or any(count != 2 for count in edges.values()):
        return {'ok': False, 'reason': 'REGION_COLLIDER_NOT_CLOSED', 'segments_cm': []}
    normal = _unit(axis)
    epsilon = 1e-6  # cm; numeric joining only, far below admissible physical reserves.
    segments, seen = [], {}
    for face_index, face in enumerate(faces):
        points = [vertices[i] for i in face]
        signed = [_dot(_sub(point, origin_cm), normal) for point in points]
        if all(abs(value) <= epsilon for value in signed):
            return {'ok': False, 'reason': 'COPLANAR_SECTION_AMBIGUOUS', 'face': face_index, 'segments_cm': []}
        hits = []
        for i, j in ((0, 1), (1, 2), (2, 0)):
            if abs(signed[i]) <= epsilon:
                hits.append(points[i])
            if signed[i]*signed[j] < 0 and abs(signed[i]) > epsilon and abs(signed[j]) > epsilon:
                t = signed[i]/(signed[i]-signed[j])
                hits.append([points[i][k]+t*(points[j][k]-points[i][k]) for k in range(3)])
        unique = []
        for point in hits:
            if not any(math.dist(point, other) <= epsilon for other in unique):
                unique.append(point)
        if len(unique) == 2 and math.dist(*unique) > epsilon:
            key = tuple(sorted(tuple(round(value/epsilon) for value in point) for point in unique))
            if key not in seen:
                seen[key] = face
                segments.append(unique)
            elif len(set(seen[key]).intersection(face)) < 2:
                # Duplicate intersections from a shared source edge are normal;
                # coincident disconnected shells do not identify a unique part.
                return {'ok': False, 'reason': 'SECTION_COINCIDENT_INTERSECTIONS_AMBIGUOUS',
                        'face': face_index, 'segments_cm': segments}
        elif len(unique) > 2:
            return {'ok': False, 'reason': 'SECTION_INTERSECTION_AMBIGUOUS', 'face': face_index, 'segments_cm': []}
    return _select_axis_section(segments, origin_cm, axis, epsilon)


def loop_from_opening(payload, coords_cm, opening, plan):
    """A measured loop plus explicit virtual seam bridges, never a union."""
    chain, bridges = [], []
    partners = {}
    for seam_id, seam in payload['seams'].items():
        if seam['kind'] == 'permanent':
            for a, b in seam['pairs']:
                partners[tuple(sorted((a, b)))] = seam_id
    def bridge(a, b):
        if a == b:
            return
        seam = partners.get(tuple(sorted((a, b))))
        if seam is None:
            raise StudioError('Opening loop has undeclared/open/closure/detachable partners')
        gap = math.dist(coords_cm[a], coords_cm[b])
        if gap > plan['assembly']['max_initial_gap_cm']:
            raise StudioError('Opening virtual bridge exceeds initial assembly gap budget')
        bridges.append({'seam': seam, 'vertices': [a, b], 'gap_cm': gap,
                        'kind': 'VIRTUAL_DIRECT_PERMANENT_BRIDGE_NO_UNION'})
    for edge in opening['edges']:
        indices = list(payload['panels'][edge['piece']]['edges'][edge['edge']])
        if edge.get('reverse'):
            indices.reverse()
        if len(indices) < 2:
            raise StudioError('Opening named edge has fewer than two samples')
        if chain:
            bridge(chain[-1], indices[0])
        chain.extend(indices if not chain or chain[-1] != indices[0] else indices[1:])
    bridge(chain[-1], chain[0])
    if chain[-1] == chain[0]:
        chain.pop()
    if len(set(chain)) < 3:
        raise StudioError('Opening loop has fewer than three distinct vertices')
    return {'indices': chain, 'points_cm': [coords_cm[i] for i in chain],
            'bridged_permanent_seams': bridges, 'geometry_changed': False}


def audit_opening(payload, coords_cm, opening, region, geometry, plan):
    """Does the sourced opening actually contain its evaluated body section?"""
    axis = _sub(region['axis_end_cm'], region['axis_start_cm'])
    normal, u, v = _basis(axis)
    origin = [a+opening['section_parameter']*b for a, b in zip(region['axis_start_cm'], axis)]
    section = section_segments(geometry, origin, axis)
    report = {'id': opening['id'], 'region': region['id'], 'body_section': section,
              'ok': False, 'qualification': 'NONE'}
    if not section['ok']:
        report['reason'] = section['reason']
        return report
    try:
        loop = loop_from_opening(payload, coords_cm, opening, plan)
    except StudioError as error:
        report.update(reason='OPENING_LOOP_UNRESOLVED', detail=str(error))
        return report
    polygon = [_project(point, origin, u, v) for point in loop['points_cm']]
    report.update(loop=loop, max_plane_offset_cm=max(abs(_dot(_sub(point, origin), normal)) for point in loop['points_cm']))
    if report['max_plane_offset_cm'] > opening['plane_tolerance_cm']:
        report['reason'] = 'OPENING_NOT_AT_SOURCED_BODY_SECTION'
        return report
    boundary = list(zip(polygon, polygon[1:]+polygon[:1]))
    if any(_crosses(a, b, c, d) for i, (a, b) in enumerate(boundary)
           for j, (c, d) in enumerate(boundary) if j > i+1 and not (i == 0 and j == len(boundary)-1)):
        report['reason'] = 'OPENING_PROJECTED_LOOP_SELF_INTERSECTION'
        return report
    segments = [[_project(point, origin, u, v) for point in segment] for segment in section['segments_cm']]
    distances = [_segment_distance(a, b, c, d) for a, b in segments for c, d in boundary]
    clearance = min(distances)
    contained = all(_inside(point, polygon) for segment in segments for point in segment)
    report.update(minimum_passage_clearance_cm=clearance, required_clearance_cm=plan['collision']['clearance_cm'],
                  section_inside_opening=contained)
    report['ok'] = contained and clearance >= plan['collision']['clearance_cm'] and clearance > 1e-8
    report['reason'] = None if report['ok'] else 'BODY_SECTION_DOES_NOT_PASS_OPENING_WITH_RESERVE'
    return report


def _exterior_report(payload, coords, assignment, region):
    axis = _sub(region['axis_end_cm'], region['axis_start_cm'])
    unit = _unit(axis)
    owned = set(payload['panels'][assignment['piece']]['indices'])
    failed, minimum, count = [], None, 0
    for face_index, face in enumerate(payload['faces']):
        if not set(face) <= owned:
            continue
        points = [coords[i] for i in face]
        center = [sum(point[k] for point in points)/3 for k in range(3)]
        delta = _sub(center, region['axis_start_cm'])
        radial = [delta[k]-_dot(delta, unit)*unit[k] for k in range(3)]
        normal = _cross(_sub(points[1], points[0]), _sub(points[2], points[0]))
        norm = math.sqrt(_dot(normal, normal)*_dot(radial, radial))
        cosine = assignment['outward_normal_sign']*_dot(normal, radial)/norm if norm > 1e-14 else None
        if cosine is None or cosine <= 0.:
            failed.append(face_index)
        if cosine is not None:
            minimum = cosine if minimum is None else min(minimum, cosine)
        count += 1
    return {'piece': assignment['piece'], 'region': assignment['region'], 'ok': count > 0 and not failed,
            'faces_measured': count, 'minimum_outward_radial_cosine': minimum,
            'failed_face_count': len(failed), 'failed_faces': failed[:32],
            'metric': 'ORIENTED_FACE_NORMAL_VERSUS_SOURCED_REGION_AXIS_NOT_COLLISION_PROOF'}


def layer_order_report(payload, coords_cm, plan, geometries):
    """Measure inner→outer order of garment surfaces, separately from contact.

    Open cloth has no global inside volume. Its sourced outward side is used
    at nearest triangle samples. Tangential/contradictory sides are refused,
    never silently classified as being above the inner layer.
    """
    from mathutils import Vector
    from mathutils.bvhtree import BVHTree
    layers = plan['layers']
    nodes = {node['id']: node for node in layers['nodes']}
    assignments = {item['piece']: item for item in plan.get('dressing', {}).get('assignments', [])}
    relations, missing = [], []
    parents = {key: set() for key in nodes}
    for inner, outer in layers['inside_to_outside']:
        parents[outer].add(inner)
    for _ in nodes:
        for outer in parents:
            parents[outer].update(set().union(*(parents[p] for p in list(parents[outer]))))
    def surface(node):
        vertices, faces, signs = [], [], []
        owned = {pid: set(payload['panels'][pid]['indices']) for pid in node['panels']}
        for face in payload['faces']:
            pieces = [pid for pid, indices in owned.items() if set(face) <= indices]
            if len(pieces) != 1:
                continue
            sign = assignments.get(pieces[0], {}).get('outward_normal_sign', node.get('outward_normal_sign'))
            offset = len(vertices)
            vertices.extend(coords_cm[i] for i in face)
            faces.append([offset, offset+1, offset+2])
            signs.append(sign)
        for name in node['colliders']:
            geometry = geometries[name]
            offset = len(vertices)
            vertices.extend(geometry['vertices_cm'])
            faces.extend([[index+offset for index in face] for face in geometry['faces']])
            signs.extend([node.get('outward_normal_sign')]*len(geometry['faces']))
        return vertices, faces, signs
    for outer, ancestors in parents.items():
        if nodes[outer]['kind'] != 'garment':
            continue
        for inner in sorted(ancestors):
            if nodes[inner]['kind'] != 'garment':
                continue  # Body signed volume/reserve is measured by contact_check.
            iv, faces, signs = surface(nodes[inner])
            ov, outer_faces, _ = surface(nodes[outer])
            if not faces or not outer_faces or any(sign is None for sign in signs):
                missing.append({'inner': inner, 'outer': outer, 'reason': 'LAYER_SURFACE_OR_SOURCED_OUTWARD_SIDE_MISSING'})
                continue
            tree = BVHTree.FromPolygons([Vector(point) for point in iv], faces, all_triangles=True)
            samples = list(ov)+[[sum(ov[i][k] for i in face)/3 for k in range(3)] for face in outer_faces]
            failed, minimum = [], None
            for sample, point in enumerate(samples):
                hit, normal, face_index, distance = tree.find_nearest(Vector(point))
                if hit is None:
                    failed.append({'sample': sample, 'reason': 'LAYER_NEAREST_SURFACE_UNAVAILABLE'})
                    continue
                signed = (Vector(point)-hit).dot(normal)*signs[face_index]
                minimum = signed if minimum is None else min(minimum, signed)
                if signed <= 0. or signed < plan['collision']['clearance_cm']:
                    failed.append({'sample': sample, 'inner_face': face_index,
                                   'signed_normal_clearance_cm': signed, 'distance_cm': distance})
            relations.append({'inner': inner, 'outer': outer, 'ok': not failed,
                              'minimum_signed_normal_clearance_cm': minimum,
                              'failed_count': len(failed), 'failed_samples': failed[:32]})
    return {'ok': not missing and all(row['ok'] for row in relations), 'relations': relations,
            'missing': missing, 'interaction': 'one_way_declared',
            'coverage': 'ORIENTED_NEAREST_LAYER_TRIANGLE_VERTEX_AND_CENTROID_SAMPLES_NOT_CONTINUOUS_PROOF',
            'qualification': 'NONE'}


def audit_dressing(payload, coords_cm, plan, *, colliders, project=None,
                   source_resolver=None, contact_check=None, motion_check=None,
                   collider_roles=None, source_coords_cm=None):
    """Native audit with optional shared static/motion collision callbacks.

    source_resolver(ref) must return a readable path; its bytes are hashed here.
    contact_check(coords) and motion_check(previous, current, i, j) return an
    actual geometric report with ok, not a declaration from the assembly plan.
    """
    if len(coords_cm) != len(payload['rest_cm']) or any(len(p) != 3 or not all(math.isfinite(x) for x in p) for p in coords_cm):
        raise StudioError('Dressing coordinates must match the current finite mesh')
    names = [obj.name for obj in colliders]
    if len(names) != len(set(names)):
        raise StudioError('Duplicate dressing collider identities')
    structural = validate_dressing(payload, plan, names)
    report = {'version': 1, 'status': structural['status'], 'contract': structural,
              'qualification': 'NONE', 'simulation': 'NOT_EXECUTED', 'geometry_changed': False,
              'required': structural['required'], 'full_coverage': structural['full_coverage'],
              'plan_sha256': digest(plan), 'coordinates_sha256': digest(coords_cm),
              'openings': [], 'regions': [], 'exterior': [], 'motion': [], 'problems': []}
    for ref in source_references(plan):
        if source_resolver is not None:
            path = source_resolver(ref)
        elif project is not None:
            path = inside(project, ref['path'])
        else:
            report.update(status='NEEDS_CLARIFICATION', reason='SOURCE_REFERENCE_VERIFICATION_UNAVAILABLE')
            return report
        if sha(path) != ref['sha256']:
            raise StudioError('Dressing source changed: '+ref['path'])
    if 'dressing' not in plan:
        report['reason'] = 'LEGACY_DRESSING_NOT_ASSESSED'
        if 'layers' in plan and sum(node['kind'] == 'garment' for node in plan['layers']['nodes']) > 1:
            geometries = {obj.name: capture_collider(obj) for obj in colliders}
            report['layer_order'] = layer_order_report(payload, coords_cm, plan, geometries)
            if report['layer_order']['missing']:
                report['status'] = 'NEEDS_CLARIFICATION'
            elif not report['layer_order']['ok']:
                report['status'] = 'NEEDS_CORRECTION'
        return report
    if structural['status'] == 'NEEDS_CLARIFICATION' and 'layers' not in plan:
        return report
    report['problems'].extend(structural.get('missing', []))
    dressing = plan['dressing']
    if not dressing['regions'] or not dressing['openings'] or not dressing['assignments']:
        report.update(status='NEEDS_CLARIFICATION' if dressing['required'] else 'NOT_ASSESSED',
                      reason='BODY_PASSAGE_GEOMETRY_NOT_DECLARED')
        return report
    geometries = {obj.name: capture_collider(obj) for obj in colliders}
    report['collider_geometry_sha256'] = {name: value['sha256'] for name, value in geometries.items()}
    report['layer_order'] = layer_order_report(payload, coords_cm, plan, geometries)
    regions = {item['id']: item for item in dressing['regions']}
    for region in regions.values():
        axis = _sub(region['axis_end_cm'], region['axis_start_cm'])
        for parameter in region['section_parameters']:
            origin = [a+parameter*b for a, b in zip(region['axis_start_cm'], axis)]
            section = section_segments(geometries[region['collider']], origin, axis)
            report['regions'].append({'id': region['id'], 'parameter': parameter, **section})
    by_id = {item['id']: item for item in dressing['openings']}
    for opening_id in dressing['mount_order']:
        opening = by_id[opening_id]
        region = regions[opening['region']]
        report['openings'].append(audit_opening(payload, coords_cm, opening, region,
                                             geometries[region['collider']], plan))
    report['exterior'] = [_exterior_report(payload, coords_cm, item, regions[item['region']])
                          for item in dressing['assignments']]
    if contact_check is None:
        report['problems'].append('STATIC_CONTACT_AUDIT_UNAVAILABLE')
    else:
        report['contact'] = contact_check(coords_cm)
    states = []
    for milestone in dressing['milestones']:
        state = [list(point) for point in coords_cm]
        touched = {}
        for piece, translation in milestone['translations_cm'].items():
            for index in payload['panels'][piece]['indices']:
                target = [coords_cm[index][k]+translation[k] for k in range(3)]
                if index in touched and math.dist(touched[index], target) > 1e-8:
                    raise StudioError('Dressing milestone contradicts a consolidated shared vertex')
                touched[index] = target
                state[index] = target
        states.append((milestone['id'], state))
    if states:
        states.append(('prepared', coords_cm))
        if source_coords_cm is None:
            report['problems'].append('MILESTONE_SOURCE_PLACEMENT_BASE_MISSING')
        elif (len(source_coords_cm) != len(coords_cm) or any(
                len(point) != 3 or not all(math.isfinite(value) for value in point) for point in source_coords_cm)):
            raise StudioError('Dressing milestone source placement base does not match the current mesh')
        else:
            report['milestone_displacement_from_source'] = []
            for state_id, state in states:
                maximum = max(math.dist(a, b) for a, b in zip(source_coords_cm, state))
                within = maximum <= plan['assembly']['max_displacement_cm']
                report['milestone_displacement_from_source'].append({'id': state_id, 'max_cm': maximum,
                    'limit_cm': plan['assembly']['max_displacement_cm'], 'ok': within})
                if not within:
                    report['motion'].append({'ok': False, 'reason': 'MILESTONE_EXCEEDS_SOURCE_PLACEMENT_BUDGET',
                                             'to': state_id, 'max_displacement_cm': maximum})
        if motion_check is None:
            report['problems'].append('PLACEMENT_PATH_AUDIT_UNAVAILABLE')
        else:
            for (previous_id, previous), (current_id, current) in zip(states, states[1:]):
                delta = max(math.dist(a, b) for a, b in zip(previous, current))
                if delta > plan['assembly']['max_displacement_cm']:
                    report['motion'].append({'ok': False, 'reason': 'MILESTONE_SEGMENT_EXCEEDS_DISPLACEMENT_BUDGET',
                                             'from': previous_id, 'to': current_id, 'max_displacement_cm': delta})
                else:
                    report['motion'].append({'from': previous_id, 'to': current_id,
                                             **motion_check(previous, current, previous_id, current_id)})
    report['path_scope'] = 'DECLARED_RIGID_TRANSLATION_MILESTONES' if states else 'CONSTRUCTED_CONFIGURATION_ONLY_NO_DRESSING_TRAJECTORY_CLAIM'
    measured = report['regions']+report['openings']+report['exterior']+report['motion']
    if report['layer_order']['missing']:
        report['problems'].append('LAYER_GEOMETRY_OR_OUTWARD_SIDE_MISSING')
    else:
        measured.append(report['layer_order'])
    if 'contact' in report:
        measured.append(report['contact'])
    report['status'] = ('NEEDS_CORRECTION' if any(not item.get('ok', False) for item in measured)
                        else 'NEEDS_CLARIFICATION' if report['problems'] else 'READY')
    report['measured_status'] = ('GEOMETRY_CHECKS_PASSED' if report['status'] == 'READY' else report['status'])
    if report['status'] == 'READY' and not report['full_coverage']:
        report.update(status='NOT_ASSESSED', reason='PARTIAL_OR_OPTIONAL_DRESSING_CANNOT_QUALIFY_FULL_CONFIGURATION')
    report['coverage'] = 'SOURCED_SECTION_OPENING_AND_EXTERIOR_GEOMETRY_PLUS_DECLARED_CONTACT_CALLBACKS_NOT_PHYSICAL_FITTING'
    return report
