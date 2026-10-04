"""Measured mesh sections in a declared body frame; no sex-based cut rules.

Stature fractions bound landmark searches only. Actual section geometry chooses
the landmarks. Ambiguous/open sections remain unqualified. Source coordinates
are never changed, and a measured landmark does not qualify garment fitting.
"""
import math
from collections import defaultdict

from .core import StudioError, digest
from .contact_geometry import dot, cross, norm, sub
from .sewing import point_inside


def unit(vector):
    size = norm(vector)
    if size < 1e-10:
        raise StudioError('Anatomical orientation requires a nonzero axis')
    return [x/size for x in vector]


def frame(options):
    for key in ('up_axis', 'forward_axis', 'origin_cm'):
        vector = options.get(key, [0., 0., 0.] if key == 'origin_cm' else [])
        if len(vector) != 3 or not all(isinstance(x, (int, float)) and math.isfinite(x) for x in vector):
            raise StudioError('Body frame requires finite three-dimensional axes and origin')
    up = unit(options['up_axis'])
    forward = unit(options['forward_axis'])
    if abs(dot(up, forward)) > 1e-6:
        raise StudioError('Body forward and up axes must be perpendicular')
    right = unit(cross(forward, up))
    return {'right': right, 'forward': forward, 'up': up,
            'origin_cm': list(options.get('origin_cm', [0., 0., 0.]))}


def surface_section(vertices, faces, height_cm, seed_xy_cm):
    """Select a unique closed mesh/plane contour containing the torso seed.

    Other loops (arms, accessories) are excluded explicitly. No convex hull
    closes a missing surface or bridges disconnected anatomy.
    """
    graph = defaultdict(set)
    coplanar = False
    for face in faces:
        heights = [vertices[index][2] for index in face]
        if min(heights) > height_cm or max(heights) < height_cm:
            continue
        intersections = []
        for a, b in zip(face, face[1:]+face[:1]):
            pa, pb = vertices[a], vertices[b]
            da, db = pa[2]-height_cm, pb[2]-height_cm
            if abs(da) < 1e-8 and abs(db) < 1e-8:
                coplanar = True
            if da <= 0 < db or db <= 0 < da:
                t = da/(da-db)
                intersections.append(tuple(round(pa[i]+t*(pb[i]-pa[i]), 5) for i in (0, 1)))
        intersections = list(dict.fromkeys(intersections))
        if len(intersections) == 2:
            a, b = intersections
            if a != b:
                graph[a].add(b); graph[b].add(a)
    remaining = set(graph); loops = []
    while remaining:
        seed = min(remaining); pending = [seed]; members = set()
        while pending:
            current = pending.pop()
            if current not in members:
                members.add(current); pending.extend(graph[current]-members)
        remaining.difference_update(members)
        if not all(len(graph[p]) == 2 for p in members):
            loops.append({'closed': False, 'contains_seed': False})
            continue
        curve = []; previous = None; current = seed
        while current not in curve:
            curve.append(current)
            following = min(p for p in graph[current] if p != previous)
            previous, current = current, following
        closed = current == seed and len(curve) == len(members)
        loops.append({'closed': closed, 'contains_seed': closed and point_inside(seed_xy_cm, curve),
                      'curve': curve})
    selected = [loop for loop in loops if loop['closed'] and loop['contains_seed']]
    result = {'height_cm': height_cm, 'loop_count': len(loops),
              'excluded_loops': len(loops)-len(selected),
              'status': 'MEASURED' if len(selected) == 1 and not coplanar else 'NOT_QUALIFIED'}
    if result['status'] != 'MEASURED':
        result['reason'] = 'SECTION_OPEN_AMBIGUOUS_OR_COPLANAR'
        return result
    curve = selected[0]['curve']
    result.update(curve_cm=[[x, y, height_cm] for x, y in curve],
                  girth_cm=sum(math.dist(a, b) for a, b in zip(curve, curve[1:]+curve[:1])),
                  bounds_xy_cm=[[min(p[i] for p in curve) for i in (0, 1)],
                                [max(p[i] for p in curve) for i in (0, 1)]],
                  confidence='MEASURED_SECTION',
                  numerical_error_bound_cm=math.sqrt(2)*.00001*len(curve))
    return result


def profile_mesh(geometry, options):
    """Geometry is evaluated mesh in cm, with immutable source and pose hashes.

    Forward/up are declared or supplied by a qualified rig adapter. Their signs
    are never inferred from catalog labels. `torso_faces` may be an explicitly
    sourced segmentation (e.g. rig weights); a single central loop otherwise
    excludes disconnected limb sections while reporting that limitation.
    """
    vertices, faces = geometry['vertices_cm'], geometry['faces']
    if not vertices or not faces or any(len(p) != 3 or not all(math.isfinite(x) for x in p) for p in vertices):
        raise StudioError('Body profile requires finite evaluated mesh geometry')
    if any(len(face) < 3 or any(type(i) is not int or i < 0 or i >= len(vertices) for i in face) for face in faces):
        raise StudioError('Body profile face indices are invalid')
    for key in ('source_sha256', 'pose_sha256'):
        value = geometry.get(key, '')
        if len(value) != 64 or any(c not in '0123456789abcdef' for c in value):
            raise StudioError('Body profile requires source and evaluated pose identities')
    basis = frame(options)
    coords = [[dot(sub(p, basis['origin_cm']), basis[key]) for key in ('right', 'forward', 'up')]
              for p in vertices]
    bounds = [[min(p[i] for p in coords) for i in range(3)],
              [max(p[i] for p in coords) for i in range(3)]]
    floor = bounds[0][2]; stature = bounds[1][2]-floor
    if not 30 <= stature <= 400:
        raise StudioError('Body stature or units unsupported: expected 30 to 400 cm; inspect units explicitly')
    face_ids = options.get('torso_faces', list(range(len(faces))))
    if not face_ids or len(set(face_ids)) != len(face_ids) or any(type(i) is not int or not 0 <= i < len(faces) for i in face_ids):
        raise StudioError('Torso segmentation must identify unique actual faces')
    if 'torso_faces' in options and not options.get('segmentation_source_ref'):
        raise StudioError('Torso segmentation needs source provenance')
    torso = [faces[i] for i in face_ids]
    seed = options.get('torso_seed_xy_cm', [(bounds[0][0]+bounds[1][0])/2,
                                         (bounds[0][1]+bounds[1][1])/2])
    if len(seed) != 2 or not all(math.isfinite(x) for x in seed):
        raise StudioError('Torso interior seed must be finite')
    count = options.get('section_count', 80)
    if type(count) is not int or not 24 <= count <= 200:
        raise StudioError('Section count must stay within 24 to 200')
    fractions = [.4+i*.5/(count-1) for i in range(count)]
    sections = []
    for fraction in fractions:
        height = floor+stature*fraction+.000031
        actual_seed = seed
        if 'torso_seed_xy_cm' not in options:
            band = [p for p in coords if abs(p[2]-height) < stature*.008
                    and abs(p[0]-seed[0]) < stature*.08]
            if band:
                actual_seed = [sum(p[i] for p in band)/len(band) for i in (0, 1)]
        section = surface_section(coords, torso, height, actual_seed)
        section['seed_xy_cm'] = actual_seed
        sections.append(section)
    ranges = {'hip': (.43, .56, max), 'waist': (.54, .68, min),
              'chest': (.67, .78, max), 'neck': (.82, .9, min)}
    landmarks = {}; missing = []
    for name, (lo, hi, choose) in ranges.items():
        candidates = [section for section in sections if section['status'] == 'MEASURED'
                      and lo <= (section['height_cm']-floor)/stature <= hi]
        if not candidates:
            missing.append(name); continue
        chosen = choose(candidates, key=lambda section: section['girth_cm'])
        low, high = chosen['bounds_xy_cm']
        landmarks[name] = {'point_cm': [(low[0]+high[0])/2, (low[1]+high[1])/2, chosen['height_cm']],
                           'girth_cm': chosen['girth_cm'], 'section_height_cm': chosen['height_cm'],
                           'confidence': 'MEASURED_WITH_SEARCH_RANGE',
                           'search_fraction_range': [lo, hi], 'section': chosen}
    pose_landmarks = geometry.get('rig_landmarks', {})
    required = ('shoulder.left', 'shoulder.right', 'elbow.left', 'elbow.right',
                'wrist.left', 'wrist.right', 'head.center')
    for name in required:
        provided = pose_landmarks.get(name)
        if provided and provided.get('source_ref') and len(provided.get('point_cm', [])) == 3:
            point = provided['point_cm']
            if not all(math.isfinite(x) for x in point):
                raise StudioError('Rig landmark must be finite')
            local = [dot(sub(point, basis['origin_cm']), basis[key]) for key in ('right', 'forward', 'up')]
            if any(local[i] < bounds[0][i]-.02*stature or local[i] > bounds[1][i]+.02*stature for i in range(3)):
                raise StudioError('Rig landmark lies outside the evaluated body bounds: '+name)
            landmarks[name] = {'point_cm': local,
                               'confidence': 'RIG_GUIDE_REQUIRES_MESH_REVIEW',
                               'source_ref': provided['source_ref']}
        else:
            missing.append(name)
    # Impossible or collapsed guides cannot become an apparently complete profile.
    # These broad geometric bounds are admission checks, not anatomical approval.
    for side in ('left', 'right'):
        chain = ['shoulder.'+side, 'elbow.'+side, 'wrist.'+side]
        for a, b in zip(chain, chain[1:]):
            if a in landmarks and b in landmarks:
                length = math.dist(landmarks[a]['point_cm'], landmarks[b]['point_cm'])
                if not .02*stature <= length <= .4*stature:
                    raise StudioError('Rig limb guide length is collapsed or unsupported: '+a+' / '+b)
    if all(name in landmarks for name in ('shoulder.left', 'shoulder.right')):
        span = math.dist(landmarks['shoulder.left']['point_cm'], landmarks['shoulder.right']['point_cm'])
        if not .05*stature <= span <= .5*stature:
            raise StudioError('Rig shoulder guides are collapsed or unsupported')
    if 'torso_faces' not in options:
        # A closed contour may still include connected arms. Its girth is a
        # surface measurement only until an explicit torso segmentation exists.
        missing.append('torso.segmentation')
    report = {'version': 1, 'status': 'NEEDS_CLARIFICATION' if missing else 'PROFILE_MEASURED',
              'qualification': 'GEOMETRY_ONLY', 'source_sha256': geometry['source_sha256'],
              'pose_sha256': geometry['pose_sha256'], 'geometry_sha256': digest([vertices, faces]),
              'options_sha256': digest(options), 'rig_landmarks_sha256': digest(pose_landmarks), 'frame': basis, 'bounds_cm': bounds,
              'floor_cm': floor, 'stature_cm': stature, 'landmarks': landmarks,
              'missing_landmarks': missing, 'sections': sections,
              'segmentation': 'EXPLICIT_SOURCE' if 'torso_faces' in options else 'CENTRAL_CLOSED_LOOP_ONLY',
              'source_mutated': False, 'sex_classification': 'NOT_PERFORMED',
              'fitting': 'NOT_EXECUTED', 'collision_envelope': 'NOT_CREATED',
              'anatomical_review': 'REQUIRED_BEFORE_FITTING'}
    report['cache_key'] = digest({key: report[key] for key in
                                ('source_sha256', 'pose_sha256', 'geometry_sha256', 'options_sha256', 'rig_landmarks_sha256')})
    return report
