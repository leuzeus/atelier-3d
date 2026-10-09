"""Deterministic surface anchors from evaluated native triangles and pose."""
import copy
import math
from collections import Counter, defaultdict

from .core import StudioError, digest
from .contact_geometry import cross, dot, sub


def measured_surface_shoulders(profile, geometry, triangles):
    points, faces = geometry['vertices_cm'], geometry['faces']
    identity = digest([points, faces])
    if (identity != profile.get('geometry_sha256') or
            geometry.get('source_sha256') != profile.get('source_sha256') or
            geometry.get('pose_sha256') != profile.get('pose_sha256')):
        raise StudioError('Surface shoulder measurement requires the exact evaluated profile geometry and pose')
    if (not triangles or any(len(t) != 3 or len(set(t)) != 3 or
            any(type(i) is not int or not 0 <= i < len(points) for i in t) for t in triangles)):
        raise StudioError('Surface shoulders require native evaluated mesh triangles')
    memberships = defaultdict(set); by_face = defaultdict(list)
    for index, face in enumerate(faces):
        for vertex in face:
            memberships[vertex].add(index)
    if len({tuple(sorted(t)) for t in triangles}) != len(triangles):
        raise StudioError('Surface triangulation contains duplicate triangles')
    for triangle in triangles:
        owners = set.intersection(*(memberships[i] for i in triangle))
        if len(owners) != 1:
            raise StudioError('Every surface triangle must belong to one exact evaluated face')
        by_face[next(iter(owners))].append(triangle)
    mesh_edges = Counter()
    for index, face in enumerate(faces):
        parts = by_face[index]
        if len(parts) != len(face)-2:
            raise StudioError('Surface triangles must cover every evaluated source face')
        edges = Counter((a,b) for t in parts for a,b in zip(t,t[1:]+t[:1]))
        boundary = set(zip(face,face[1:]+face[:1]))
        if any(edges[edge] != 1 or edges[(edge[1],edge[0])] for edge in boundary):
            raise StudioError('Surface triangulation must preserve the face boundary and winding')
        for edge,count in edges.items():
            if edge not in boundary and (count != 1 or edges[(edge[1],edge[0])] != 1):
                raise StudioError('Surface triangulation has an incomplete or overlapping face interior')
        mesh_edges.update(boundary)
    if any(count != 1 or mesh_edges[(b,a)] != 1 for (a,b),count in mesh_edges.items()):
        raise StudioError('Surface shoulder exits require a closed consistently oriented body mesh')
    if 'surface_landmarks_source' in profile or any(name.startswith('shoulder.surface.') for name in profile['landmarks']):
        raise StudioError('Remeasure from the original profile, without stale surface landmarks')
    basis = profile['frame']; direction = basis['up']; anchors = {}
    for side in ('left', 'right'):
        joint = profile['landmarks']['shoulder.'+side]['point_cm']
        origin = [basis['origin_cm'][i]+math.fsum(joint[j]*basis[key][i]
                  for j,key in enumerate(('right','forward','up'))) for i in range(3)]
        hits = []
        for index, triangle in enumerate(triangles):
            a,b,c = [points[i] for i in triangle]
            e1,e2 = sub(b,a),sub(c,a); h = cross(direction,e2); det = dot(e1,h)
            if abs(det) < 1e-12:
                continue
            s = sub(origin,a); u = dot(s,h)/det
            q = cross(s,e1); v = dot(direction,q)/det
            distance = dot(e2,q)/det
            if u >= -1e-9 and v >= -1e-9 and u+v <= 1+1e-9 and distance > 1e-7:
                normal = cross(e1,e2); size = math.sqrt(dot(normal,normal))
                if size > 1e-12:
                    hits.append((distance,index,[x/size for x in normal]))
        hits.sort(); unique = []
        for hit in hits:
            if not unique or abs(hit[0]-unique[-1][0]) > 1e-6:
                unique.append(hit)
        if not unique or len(unique)%2 != 1:
            raise StudioError('Shoulder joint is outside or has an ambiguous surface exit: '+side)
        distance,index,normal = unique[0]
        if distance >= .1*profile['stature_cm'] or dot(normal,direction) <= 0:
            raise StudioError('Shoulder surface exit is too far away or inward oriented: '+side)
        hit = [origin[i]+distance*direction[i] for i in range(3)]
        local = [dot(sub(hit,basis['origin_cm']),basis[key]) for key in ('right','forward','up')]
        anchors['shoulder.surface.'+side] = {'point_cm':local,
            'source_ref':'evaluated-surface-ray:'+identity,
            'confidence':'MEASURED_SURFACE_RAY_REQUIRES_REVIEW',
            'source_joint_cm':copy.deepcopy(joint), 'distance_from_joint_cm':distance,
            'triangle_index':index, 'triangle_vertices':list(triangles[index]),
            'normal_world':normal, 'ray_direction_world':list(direction)}
    result = copy.deepcopy(profile); result['landmarks'].update(anchors)
    result['surface_landmarks_source'] = {'geometry_sha256':identity,
        'base_profile_sha256':digest(profile),
        'source_sha256':geometry['source_sha256'], 'pose_sha256':geometry['pose_sha256'],
        'previous_cache_key':profile['cache_key'], 'triangles_sha256':digest(triangles),
        'method':'EVALUATED_TRIANGLE_UPWARD_EXIT_FROM_INTERNAL_SHOULDER_JOINT',
        'body_mutated':False, 'surface_landmarks_sha256':digest(anchors)}
    result['cache_key'] = digest({'profile':profile['cache_key'], 'base_profile':digest(profile),
        'surface_landmarks':anchors, 'triangles':digest(triangles)})
    return result


def surface_anchors(profile):
    source = profile.get('surface_landmarks_source', {})
    if (any(source.get(k) != profile.get(k) for k in
            ('geometry_sha256','source_sha256','pose_sha256')) or
            source.get('body_mutated') is not False):
        raise StudioError('Upper garment guides require measured surface shoulders bound to this body and pose')
    anchors = {name:profile['landmarks'].get(name) for name in
               ('shoulder.surface.left','shoulder.surface.right')}
    if any(not row or row.get('source_ref') != 'evaluated-surface-ray:'+profile['geometry_sha256'] or
           row.get('source_joint_cm') != profile['landmarks']['shoulder.'+name.rsplit('.',1)[-1]]['point_cm']
           for name,row in anchors.items()):
        raise StudioError('Surface shoulder landmarks changed or lack their measured joint correspondence')
    if digest(anchors) != source.get('surface_landmarks_sha256') or profile['cache_key'] != digest({
            'profile':source.get('previous_cache_key'), 'base_profile':source.get('base_profile_sha256'), 'surface_landmarks':anchors,
            'triangles':source.get('triangles_sha256')}):
        raise StudioError('Surface shoulder cache identity changed; remeasure the evaluated body')
    base = copy.deepcopy(profile); del base['surface_landmarks_source']
    base['cache_key'] = source['previous_cache_key']
    for name in anchors:
        del base['landmarks'][name]
    if digest(base) != source.get('base_profile_sha256'):
        raise StudioError('Surface shoulder base profile changed; remeasure its frame and body landmarks')
    return {side:anchors['shoulder.surface.'+side]['point_cm'] for side in ('left','right')}
