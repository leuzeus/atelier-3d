"""Separate source-bound limb sections and conservative whole-hand projections.

This module reads geometry; it never changes an approved body/profile. Limb
girths follow actual native triangle/plane contours, without a hull or bounding
box. A whole-hand projection is explicitly a conservative skin hull, never a
measured anatomical girth, a fitting result or a physical passage admission.
"""
import copy
import math
from collections import defaultdict

from .anatomy_profile import unit
from .contact_geometry import cross, dot, sub
from .core import ROOT, StudioError, contract, digest, inside, read_json, sha
from .sewing import point_inside, segment_distance


def _ordered_perimeter_sum(lengths):
    """Preserve the stored 3.11 left-to-right additions across Python versions.

    Perimeters are exact cache inputs. Builtin sum changed its floating-point
    algorithm in 3.12; compensated summation would change existing measurements.
    """
    total = 0
    for length in lengths:
        total += length
    return total


def _point(value):
    return isinstance(value, (list, tuple)) and len(value) == 3 and all(
        type(x) in (int, float) and math.isfinite(x) for x in value)


def _world(profile, point):
    basis = profile['frame']
    return [basis['origin_cm'][i]+sum(point[j]*basis[key][i]
            for j, key in enumerate(('right', 'forward', 'up'))) for i in range(3)]


def _base_identity(profile):
    """Authenticate existing optional surfaces before unwrapping the base cache."""
    base = copy.deepcopy(profile)
    if 'surface_landmarks_source' in base:
        from .shoulder_surface import surface_anchors
        surface_anchors(base)
        source = base.pop('surface_landmarks_source'); base['cache_key'] = source['previous_cache_key']
        for side in ('left', 'right'): del base['landmarks']['shoulder.surface.'+side]
    if 'head_surface_source' in base:
        from .head_surface import head_surface_section
        head_surface_section(base)
        source = base.pop('head_surface_source'); base['cache_key'] = source['previous_cache_key']
        del base['surface_sections']['head']
        if not base['surface_sections']: del base['surface_sections']
    keys = ('source_sha256', 'pose_sha256', 'geometry_sha256', 'options_sha256', 'rig_landmarks_sha256')
    if (any(key not in base for key in keys) or base.get('cache_key') != digest({key: base[key] for key in keys})):
        raise StudioError('Body region measurements require the exact base profile cache')


def _identity(profile, geometry, triangles, specification):
    _base_identity(profile)
    # Reuse the exact native triangulation/skin authentication used by dressing.
    # This helper is pure Python and neither imports bpy nor captures a scene.
    from .dressing_derivation import _triangles
    _triangles(profile, geometry, triangles)
    labels = geometry.get('face_sets', [])
    if len(labels) != len(geometry['faces']) or any(type(x) is not int for x in labels):
        raise StudioError('Body regions require exact source face-region identities')
    expected = {'profile_sha256': digest(profile), 'profile_cache_key': profile['cache_key'],
                'geometry_sha256': digest([geometry['vertices_cm'], geometry['faces']]),
                'source_sha256': geometry['source_sha256'], 'pose_sha256': geometry['pose_sha256'],
                'face_sets_sha256': digest(labels), 'triangles_sha256': digest(triangles)}
    if any(specification['identity'].get(key) != value for key, value in expected.items()):
        raise StudioError('Body region source, profile, pose, triangulation or face regions changed')
    if digest(geometry.get('rig_landmarks', {})) != profile.get('rig_landmarks_sha256'):
        raise StudioError('Body region rig landmarks differ from the measured source profile')
    memberships = defaultdict(set)
    for index, face in enumerate(geometry['faces']):
        for vertex in face: memberships[vertex].add(index)
    return [next(iter(set.intersection(*(memberships[i] for i in triangle)))) for triangle in triangles]


def _joint(profile, geometry, name, in_profile=True):
    source = geometry.get('rig_landmarks', {}).get(name, {})
    if not source.get('source_ref') or not _point(source.get('point_cm')):
        raise StudioError('Body region requires a sourced evaluated joint: '+name)
    if in_profile:
        landmark = profile['landmarks'].get(name, {})
        if (not _point(landmark.get('point_cm')) or landmark.get('source_ref') != source['source_ref'] or
                math.dist(_world(profile, landmark['point_cm']), source['point_cm']) > 1e-7):
            raise StudioError('Body region joint differs from its exact measured source: '+name)
    return list(source['point_cm'])


def _plane(profile, start, end, reference_axis):
    normal = unit(sub(end, start)); reference = profile['frame'][reference_axis]
    tangent = [reference[i]-dot(reference, normal)*normal[i] for i in range(3)]
    if math.sqrt(dot(tangent, tangent)) < 1e-8:
        raise StudioError('Declared body-frame reference axis is parallel to the limb plane normal')
    u = unit(tangent)
    return normal, u, list(cross(normal, u))


def _project(point, origin, u, v):
    delta = sub(point, origin)
    return [dot(delta, u), dot(delta, v)]


def _touch(a, b, c, d, epsilon):
    if any(max(a[i], b[i])+epsilon < min(c[i], d[i]) or
           max(c[i], d[i])+epsilon < min(a[i], b[i]) for i in (0, 1)): return False
    def orient(p, q, r):
        return (q[0]-p[0])*(r[1]-p[1])-(q[1]-p[1])*(r[0]-p[0])
    if orient(a,b,c)*orient(a,b,d) < 0 and orient(c,d,a)*orient(c,d,b) < 0: return True
    return min(segment_distance(a,c,d), segment_distance(b,c,d),
               segment_distance(c,a,b), segment_distance(d,a,b)) <= epsilon


def _section(vertices, triangles, triangle_ids, origin, normal, u, v, epsilon):
    """Join intersections by source edge IDs, never by proximity across shells."""
    points, graph, source_edges = {}, defaultdict(set), {}
    result = {'ok': False, 'status': 'NOT_QUALIFIED', 'center_cm': list(origin),
              'plane': {'normal_world': normal, 'u_world': u, 'v_world': v},
              'segments_cm': [], 'loops': [], 'selection': 'EXACT_SOURCE_DOMAIN_SINGLE_CLOSED_LOOP',
              'coverage': 'ACTUAL_EVALUATED_TRIANGLE_PLANE_INTERSECTION',
              'surface_discretization_error': 'NOT_ESTIMATED', 'numerical_tolerance_cm': epsilon}
    def refuse(reason): return dict(result, reason=reason)
    for index in triangle_ids:
        triangle = triangles[index]; signed = {i: dot(sub(vertices[i], origin), normal) for i in triangle}
        hits = []
        for a, b in zip(triangle, triangle[1:]+triangle[:1]):
            da, db = signed[a], signed[b]
            if abs(da) <= epsilon and abs(db) <= epsilon:
                return refuse('COPLANAR_SECTION_EDGE_OR_FACE')
            for i, distance in ((a, da), (b, db)):
                if abs(distance) <= epsilon:
                    key = ('vertex', i); points[key] = [vertices[i][j]-distance*normal[j] for j in range(3)]
                    hits.append(key)
            if da*db < 0 and abs(da) > epsilon and abs(db) > epsilon:
                aa, bb = sorted((a, b)); sa, sb = signed[aa], signed[bb]
                t = sa/(sa-sb); key = ('edge', aa, bb)
                points[key] = [vertices[aa][j]+t*(vertices[bb][j]-vertices[aa][j]) for j in range(3)]
                hits.append(key)
        hits = list(dict.fromkeys(hits))
        if len(hits) > 2: return refuse('AMBIGUOUS_TRIANGLE_INTERSECTION')
        if len(hits) == 2:
            a, b = hits
            if math.dist(points[a], points[b]) <= epsilon: return refuse('DEGENERATE_SECTION_SEGMENT')
            edge = tuple(sorted((a,b)))
            if edge in source_edges: return refuse('DUPLICATE_SECTION_SEGMENT')
            source_edges[edge] = index; graph[a].add(b); graph[b].add(a)
    result['segments_cm'] = [[points[a],points[b]] for a,b in sorted(source_edges)]
    result['triangle_intersection_count'] = len(source_edges)
    if not graph: return refuse('SECTION_EMPTY_OR_OUTSIDE_SKIN')
    if any(len(neighbors) != 2 for neighbors in graph.values()): return refuse('SECTION_OPEN_OR_BRANCHING')
    remaining = set(graph)
    while remaining:
        start = min(remaining); current = start; previous = None; curve = []
        while current not in curve:
            curve.append(current)
            following = min(p for p in graph[current] if p != previous)
            previous, current = current, following
        if current != start: return refuse('SECTION_LOOP_TRAVERSAL_AMBIGUOUS')
        remaining.difference_update(curve)
        world = [points[key] for key in curve]; polygon = [_project(p, origin, u, v) for p in world]
        result['loops'].append({'index': len(result['loops']), 'points_cm': world,
                                'source_nodes': [list(key) for key in curve], 'plane_points_cm': polygon})
    if len(result['loops']) != 1: return refuse('MULTIPLE_SOURCE_DOMAIN_SECTION_LOOPS')
    loop = result['loops'][0]; polygon = loop['plane_points_cm']; edges = list(zip(polygon, polygon[1:]+polygon[:1]))
    if len(edges) < 3 or abs(sum(a[0]*b[1]-b[0]*a[1] for a,b in edges)) <= epsilon**2:
        return refuse('DEGENERATE_SECTION_LOOP')
    for i, (a,b) in enumerate(edges):
        for j in range(i+1,len(edges)):
            if j == i+1 or (i == 0 and j == len(edges)-1): continue
            if _touch(a,b,*edges[j],epsilon): return refuse('SELF_INTERSECTING_SECTION_LOOP')
    distance = min(segment_distance([0.,0.],a,b) for a,b in edges)
    if distance <= epsilon or not point_inside([0.,0.],polygon): return refuse('SOURCED_AXIS_OUTSIDE_OR_ON_SKIN')
    curve = loop['points_cm']; girth = _ordered_perimeter_sum(math.dist(a,b) for a,b in zip(curve,curve[1:]+curve[:1]))
    result.update(ok=True,status='MEASURED',reason=None,selected_loop=0,curve_cm=copy.deepcopy(curve),
                  girth_cm=girth,minimum_axis_boundary_distance_cm=distance,
                  numerical_error_bound_cm=2*epsilon*len(curve),confidence='EXACT_MESH_SECTION_ONLY')
    return result


def _domain(profile, geometry, declaration):
    side = declaration['side']; start_name, end_name = declaration['axis_start_landmark'], declaration['axis_end_landmark']
    required = ({'shoulder.'+side, 'elbow.'+side} if declaration['domain'] == 'SHOULDER_TO_ELBOW_ONLY'
                else {'wrist.'+side, 'elbow.'+side})
    if {start_name,end_name} != required: raise StudioError('Body region cannot relabel its declared anatomical domain')
    lo, hi = declaration['fraction_domain']; fractions = declaration['fractions']
    if (not lo <= hi or not fractions or fractions != sorted(set(fractions)) or
            fractions[0] != lo or fractions[-1] != hi or any(not lo <= p <= hi for p in fractions)):
        raise StudioError('Body region fractions must uniquely cover both declared domain boundaries')
    return _joint(profile,geometry,start_name), _joint(profile,geometry,end_name)


def _hull(points):
    ordered = sorted(set(tuple(p) for p in points))
    def orient(a,b,c): return (b[0]-a[0])*(c[1]-a[1])-(b[1]-a[1])*(c[0]-a[0])
    if len(ordered) < 3: raise StudioError('Conservative hand projection is degenerate')
    lower = []; upper = []
    for target, sequence in ((lower,ordered),(upper,ordered[::-1])):
        for p in sequence:
            while len(target)>1 and orient(target[-2],target[-1],p) <= 0: target.pop()
            target.append(p)
    result = lower[:-1]+upper[:-1]
    if len(result)<3: raise StudioError('Conservative hand projection is collinear')
    return [list(p) for p in result]


def _hand(profile, geometry, declaration, specification, adapter, source_geometry, epsilon):
    binding = specification.get('hand_source', {})
    if (not adapter or not source_geometry or digest(adapter) != binding.get('adapter_sha256') or
            digest(source_geometry) != binding.get('source_geometry_sha256') or
            adapter.get('source_geometry_sha256') != digest([source_geometry['vertices_cm'],source_geometry['faces'],source_geometry['face_sets']]) or
            geometry['faces'] != source_geometry['faces'] or geometry['face_sets'] != source_geometry['face_sets']):
        raise StudioError('Whole-hand domain requires the exact source adapter, original topology and face labels')
    side = declaration['side']; hand_name = 'hand.'+side; wrist_name = 'wrist.'+side
    labels = {int(label) for label,bone in adapter.get('region_to_bone',{}).items() if bone == hand_name}
    if not labels or not adapter.get('source_ref'): raise StudioError('Whole-hand source regions are unavailable')
    if set(adapter.get('centers',{}).get(hand_name,[]))-labels or not adapter.get('centers',{}).get(hand_name):
        raise StudioError('Whole-hand center is outside its declared hand region mapping')
    ids = [i for i,label in enumerate(geometry['face_sets']) if label in labels]
    if not ids or set(geometry['face_sets'][i] for i in ids) != labels:
        raise StudioError('Whole-hand region mapping names absent source skin')
    wrist = _joint(profile,geometry,wrist_name); hand = _joint(profile,geometry,hand_name,False)
    center_labels=set(adapter['centers'][hand_name])
    center_ids=sorted({i for index,face in enumerate(geometry['faces'])
                       if geometry['face_sets'][index] in center_labels for i in face})
    if math.dist(hand,[sum(geometry['vertices_cm'][i][axis] for i in center_ids)/len(center_ids)
                       for axis in range(3)])>1e-7:
        raise StudioError('Whole-hand center differs from its actual mapped source-region centroid')
    normal,u,v = _plane(profile,wrist,hand,declaration['plane_reference_axis'])
    vertices = sorted({i for index in ids for i in geometry['faces'][index]})
    if len(vertices)>specification['budgets']['max_projection_vertices']:
        return {'id':declaration['id'],'side':side,'status':'INCOMPLETE',
                'reason':'HAND_PROJECTION_VERTEX_BUDGET_EXHAUSTED','source_vertex_count':len(vertices),
                'physical_hand_passage':'NOT_QUALIFIED'}
    # Include every mapped palm/finger surface vertex, independent of whether a
    # section through a digit happens to be disconnected from another digit.
    projected = [_project(geometry['vertices_cm'][i],wrist,u,v) for i in vertices]
    hull = _hull(projected)
    if not point_inside(_project(hand,wrist,u,v),hull): raise StudioError('Sourced hand guide lies outside its complete projected skin')
    for point in projected:
        if not point_inside(point,hull) and min(segment_distance(point,a,b) for a,b in zip(hull,hull[1:]+hull[:1])) > epsilon:
            raise StudioError('Conservative hand hull failed complete projected skin containment')
    return {'id':declaration['id'],'side':side,'status':'CONSERVATIVE_SKIN_PROJECTION_MEASURED',
        'measurement_scope':'CONSERVATIVE_PROJECTED_WHOLE_HAND_SKIN_HULL','origin_cm':wrist,
        'axis_source_landmarks':[wrist_name,hand_name], 'normal_world':normal,'u_world':u,'v_world':v,
        'source_face_ids':ids,'source_vertex_ids':vertices,'source_labels':sorted(labels),
        'hull_plane_cm':hull,'hull_world_cm':[[wrist[i]+p[0]*u[i]+p[1]*v[i] for i in range(3)] for p in hull],
        'hull_perimeter_cm':_ordered_perimeter_sum(math.dist(a,b) for a,b in zip(hull,hull[1:]+hull[:1])),
        'projection_contains_all_declared_skin_vertices':True,'plane_source_axis':declaration['plane_reference_axis'],
        'numerical_error_bound_cm':epsilon,'numerical_margin_required_cm':epsilon,
        'anatomical_girth':'NOT_MEASURED','physical_hand_passage':'NOT_QUALIFIED','mesh_discretization_error':'NOT_ESTIMATED',
        'source_ref':copy.deepcopy(declaration['source_ref']),'adapter_ref':copy.deepcopy(binding['adapter_ref'])}


def measure_body_regions(profile, geometry, native_triangles, specification, adapter=None, source_geometry=None):
    """Return a separate deterministic supplement at explicit sampled fractions.

    Caller-supplied source references are proposals in this portable function.
    Use measure_project_body_regions to authenticate disk/native provenance.
    No finite list of sections qualifies the unsampled limb interval.
    """
    contract('body-region-sections',specification)
    before = digest([profile,geometry,native_triangles,specification,adapter,source_geometry])
    owners = _identity(profile,geometry,native_triangles,specification); epsilon=specification['numerical_tolerance_cm']
    budget=specification['budgets']; declarations=specification['regions']; hands=specification.get('hand_envelopes',[])
    all_ids=[row['id'] for row in [*declarations,*hands]]
    if not all_ids: raise StudioError('Body region supplement requires at least one declared measurement domain')
    if len(set(all_ids))!=len(all_ids): raise StudioError('Body region/envelope IDs must be unique')
    requested=sum(len(row['fractions']) for row in declarations)
    count=0; regions=[]; diagnostics=[]
    for row in sorted(declarations,key=lambda item:item['id']):
        ids=row['face_ids']
        if (not ids or len(set(ids))!=len(ids) or any(type(i) is not int or not 0<=i<len(geometry['faces']) for i in ids)):
            raise StudioError('Body region needs actual unique source face IDs')
        start,end=_domain(profile,geometry,row);normal,u,v=_plane(profile,start,end,row['plane_reference_axis'])
        selected_ids=set(ids);selected=[i for i,owner in enumerate(owners) if owner in selected_ids]
        if not selected: raise StudioError('Body region face domain has no native triangles')
        sections=[]
        for index,parameter in enumerate(row['fractions']):
            center=[a+parameter*(b-a) for a,b in zip(start,end)]
            if sum(len(r['sections']) for r in regions)+len(sections)>=budget['max_sections'] or count+len(selected)>budget['max_triangle_evaluations']:
                sections.append({'id':row['id']+'.section.'+str(index),'parameter':parameter,'center_cm':center,'ok':False,'status':'INCOMPLETE','reason':'BODY_REGION_BUDGET_EXHAUSTED'})
                continue
            count+=len(selected);section=_section(geometry['vertices_cm'],native_triangles,selected,center,normal,u,v,epsilon)
            section.update(id=row['id']+'.section.'+str(index),parameter=parameter);sections.append(section)
        region={'id':row['id'],'side':row['side'],'axis_start_cm':start,'axis_end_cm':end,'domain':row['domain'],
                'fraction_domain':copy.deepcopy(row['fraction_domain']),'source_face_ids':sorted(ids),'source_ref':copy.deepcopy(row['source_ref']),
                'plane_source_axis':row['plane_reference_axis'],'geometry_sha256':profile['geometry_sha256'],'pose_sha256':profile['pose_sha256'],
                'profile_sha256':digest(profile),'sections':sections,'status':'MEASURED_SECTIONS' if all(s['ok'] for s in sections) else 'NEEDS_DATA',
                'temporal_coverage':'STATIC_EVALUATED_POSE_ONLY','spatial_coverage':'DECLARED_SAMPLES_ONLY',
                'continuous_interval_maximum':'NOT_QUALIFIED','full_hand_passage':'NOT_QUALIFIED','qualification':'MEASURED_BODY_SECTIONS_ONLY'}
        region['axis_landmark_review']='SOURCE_GUIDE_REVIEW_REQUIRED'
        regions.append(region)
        diagnostics += [{'region':row['id'],'parameter':s['parameter'],'reason':s['reason']} for s in sections if not s['ok']]
    envelopes=[]
    for row in sorted(hands,key=lambda item:item['id']):
        envelope=_hand(profile,geometry,row,specification,adapter,source_geometry,epsilon);envelopes.append(envelope)
        if envelope['status']=='INCOMPLETE': diagnostics.append({'region':row['id'],'reason':envelope['reason']})
    if any('BUDGET_EXHAUSTED' in s['reason'] for s in diagnostics):
        status='INCOMPLETE'
    else: status='BODY_REGIONS_MEASURED' if not diagnostics else 'BODY_REGIONS_NEED_DATA'
    result={'version':1,'status':status,'purpose':specification['purpose'],'identity':copy.deepcopy(specification['identity']),
        'bindings':copy.deepcopy(specification['bindings']),'regions':regions,'hand_envelopes':envelopes,'diagnostics':diagnostics,
        'requested_sections':requested,'triangle_evaluations':count,'measurement_specification_sha256':digest(specification),
        'body_profile_changed':False,'body_geometry_changed':False,'anatomical_targets_changed':False,
        'fitting':'NOT_EXECUTED','dressing':'NOT_EXECUTED','physical_passage':'NOT_QUALIFIED','acceptance':'NOT_GRANTED',
        'qualification':'SEPARATE_GEOMETRY_MEASUREMENTS_ONLY','native_body_origin':'NOT_CHECKED_BY_PORTABLE_KERNEL'}
    result['measurement_code_sha256']={name:sha(ROOT/('a3d/'+name+'.py')) for name in
        ('body_region_sections','dressing_derivation','shoulder_surface','head_surface','garment_guides',
         'anatomy_profile','contact_geometry','sewing','core')}
    if digest([profile,geometry,native_triangles,specification,adapter,source_geometry])!=before:
        raise StudioError('Body region measurement mutated immutable source inputs')
    result['cache_key']=digest(result)
    return result


def verified_region(profile,geometry,triangles,specification,supplement,region_id,adapter=None,source_geometry=None):
    """Remeasure source inputs before consuming a region, not just its signature."""
    expected=measure_body_regions(profile,geometry,triangles,specification,adapter,source_geometry)
    if expected!=supplement: raise StudioError('Body region supplement differs from remeasured exact source inputs')
    rows=[row for row in expected['regions'] if row['id']==region_id]
    if len(rows)!=1: raise StudioError('Requested body region is absent or ambiguous')
    return copy.deepcopy(rows[0])


def measure_project_body_regions(project,specification_path):
    """Read exact native body provenance, then measure without writing any state."""
    specification=contract('body-region-sections',read_json(inside(project.root,specification_path)))
    def checked(reference,document=True):
        path=inside(project.root,reference['path'])
        if sha(path)!=reference['sha256']: raise StudioError('Body region referenced source changed: '+reference['path'])
        return read_json(path) if document else path
    refs=specification['bindings'];profile=checked(refs['profile_ref']);geometry=checked(refs['geometry_ref']);triangles=checked(refs['triangles_ref'])
    for row in [*specification['regions'],*specification.get('hand_envelopes',[])]: checked(row['source_ref'],False)
    from .native_evidence import native_origin as _native_origin
    native,origin=_native_origin(project,lambda doc:
        (doc.get('operation')=='prepare_body_target' and doc.get('result',{}).get('artifacts',{}).get('profile')==refs['profile_ref']) or
        (doc.get('operation')=='introduce_body_target' and doc.get('result',{}).get('profile_ref')==refs['profile_ref']),
        operation_filter=('prepare_body_target','introduce_body_target'))
    if native['operation']=='introduce_body_target':
        from .body_context import body_context_descriptor
        descriptor=body_context_descriptor(project,native['arguments']['context_path']);receipt=descriptor['receipt']
        if (native['result'].get('status')!='BODY_TARGET_INTRODUCED' or native['result'].get('binding_sha256')!=descriptor['binding_sha256'] or
                native['result'].get('profile_cache_key')!=profile['cache_key'] or native['result'].get('context')!=descriptor['context_ref'] or
                native['result'].get('body_target_receipt')!=descriptor['context']['body_target_receipt'] or
                native['result'].get('source_artifact')!=receipt['artifact'] or
                native['result'].get('geometry_ref')!=receipt['artifacts']['geometry'] or
                native['result'].get('actual_geometry_sha256')!=digest({key:geometry[key] for key in ('vertices_cm','faces','face_sets')})):
            raise StudioError('Body region introduction differs from exact native body context')
    else: receipt=native['result']
    if (receipt.get('status')!='NATIVE_BODY_TARGET_MEASURED' or receipt.get('native_reopened') is not True or
            any(receipt['artifacts'][name]!=refs[key] for name,key in (('profile','profile_ref'),('geometry','geometry_ref'),('triangles','triangles_ref')))):
        raise StudioError('Body region measurements require exact reopened native body artifacts')
    adapter=source_geometry=None
    if specification.get('hand_envelopes'):
        hand=specification['hand_source'];adapter=checked(hand['adapter_ref']);source_geometry=checked(hand['source_geometry_ref'])
        if hand['adapter_ref']!=receipt['evidence']['adapter'] or hand['source_geometry_ref']!=receipt['artifacts']['source-geometry']:
            raise StudioError('Whole-hand source adapter or original geometry differs from the native body origin')
    result=measure_body_regions(profile,geometry,triangles,specification,adapter,source_geometry)
    result['native_body_origin']=origin
    result['specification_ref']={'path':specification_path,'sha256':sha(inside(project.root,specification_path))}
    result['measurement_code_sha256']['native_evidence']=sha(ROOT/'a3d/native_evidence.py')
    result['measurement_code_sha256']['body_context']=sha(ROOT/'a3d/body_context.py')
    result['cache_key']=digest({k:v for k,v in result.items() if k!='cache_key'})
    return result


def body_region_descriptor(project,specification_path,supplement_ref):
    """Authenticate a saved supplement by canonical native origin and recomputation.

    A client cache key, scope label or MEASURED flag cannot substitute for this
    comparison. Reading this descriptor never registers evidence or changes
    the approved body/profile and has no fitting or anatomical gate effects.
    """
    if not isinstance(supplement_ref,dict) or set(supplement_ref)!={'path','sha256'}:
        raise StudioError('Body region supplement requires an exact path and SHA-256')
    path=inside(project.root,supplement_ref['path'])
    if sha(path)!=supplement_ref['sha256']: raise StudioError('Body region supplement artifact changed')
    supplement=read_json(path);expected=measure_project_body_regions(project,specification_path)
    if supplement!=expected: raise StudioError('Body region supplement differs from actual canonical source remeasurement')
    sections={section['id']:{'region':row,'section':section}
              for row in expected['regions'] for section in row['sections']}
    return {'specification_ref':copy.deepcopy(expected['specification_ref']),'supplement_ref':copy.deepcopy(supplement_ref),
            'identity':copy.deepcopy(expected['identity']),'native_body_origin':copy.deepcopy(expected['native_body_origin']),
            'supplement':expected,'sections':sections,'hand_envelopes':{row['id']:row for row in expected['hand_envelopes']}}


def body_region_section(project,specification_path,supplement_ref,section_id):
    """Return one authenticated actual oblique skin contour, never a hand hull."""
    descriptor=body_region_descriptor(project,specification_path,supplement_ref)
    found=descriptor['sections'].get(section_id)
    if not found or found['section'].get('status')!='MEASURED' or found['section'].get('ok') is not True:
        raise StudioError('Requested body region section is missing or not measured on its exact source skin')
    row,section=found['region'],copy.deepcopy(found['section'])
    section.update(region_id=row['id'],domain=row['domain'],source_ref=copy.deepcopy(row['source_ref']),
                   identity=copy.deepcopy(descriptor['identity']),supplement_ref=copy.deepcopy(supplement_ref),
                   specification_ref=copy.deepcopy(descriptor['specification_ref']),
                   native_body_origin=copy.deepcopy(descriptor['native_body_origin']),
                   measurement_scope='EXACT_OBLIQUE_LIMB_SKIN_SECTION',physical_passage='NOT_QUALIFIED')
    return section


def conservative_hand_envelope(project,specification_path,supplement_ref,envelope_id):
    """Return the complete projected skin envelope with its conservative scope."""
    descriptor=body_region_descriptor(project,specification_path,supplement_ref)
    row=descriptor['hand_envelopes'].get(envelope_id)
    if row is None or row.get('status')!='CONSERVATIVE_SKIN_PROJECTION_MEASURED':
        raise StudioError('Requested conservative hand envelope is unavailable or incomplete')
    result=copy.deepcopy(row)
    result.update(identity=copy.deepcopy(descriptor['identity']),supplement_ref=copy.deepcopy(supplement_ref),
                  specification_ref=copy.deepcopy(descriptor['specification_ref']),native_body_origin=copy.deepcopy(descriptor['native_body_origin']))
    return result
