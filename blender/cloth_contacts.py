"""Precise static contacts and bounded discrete motion checks; never a solver.

Triangle AABB BVHs conservatively include coplanar and near-surface pairs;
float64 closest-feature predicates then decide contact. Body signs retain the
native nearest-surface/ray classifier. No positions or Blender objects change.
"""
import copy
import math

from a3d.core import StudioError,digest
from a3d.contact_geometry import TriangleBVH,triangle_contact,separated_projection,cross,sub,norm

VERSION=1
COVERAGE='TRIANGLE_DISTANCE_AND_INTERSECTION_WITH_COPLANAR_CASES_STATIC_FLOAT64'


def _surface(obj):
    import bpy
    evaluated=obj.evaluated_get(bpy.context.evaluated_depsgraph_get())
    mesh=evaluated.to_mesh()
    try:
        mesh.calc_loop_triangles()
        coords=[[float(value)*100 for value in evaluated.matrix_world@vertex.co] for vertex in mesh.vertices]
        faces=[list(triangle.vertices) for triangle in mesh.loop_triangles]
        polygons=[triangle.polygon_index for triangle in mesh.loop_triangles]
    finally:evaluated.to_mesh_clear()
    if not faces:raise StudioError('Contact collider has no evaluated triangles: '+obj.name)
    if any(not math.isfinite(value) for point in coords for value in point):
        raise StudioError('Contact collider coordinates are nonfinite: '+obj.name)
    return coords,faces,polygons,digest({'coords_cm':coords,'triangles':faces,'polygons':polygons})


def _triangles(coords,faces):
    triangles=[]
    for index,face in enumerate(faces):
        if len(face)!=3 or len(set(face))!=3:raise StudioError('Contact face is not a valid triangle: '+str(index))
        triangle=[coords[i] for i in face]
        maximum=max(math.dist(triangle[i],triangle[(i+1)%3]) for i in range(3))
        if norm(cross(sub(triangle[1],triangle[0]),sub(triangle[2],triangle[0])))<=max(1e-10,maximum*1e-10)*maximum:
            raise StudioError('Contact face is degenerate: '+str(index))
        triangles.append(triangle)
    return triangles


def _max_edge(triangles):
    return max((math.dist(t[i],t[(i+1)%3]) for t in triangles for i in range(3)),default=0.)


def _owners(payload):
    memberships={i:set() for i in range(len(payload['rest_cm']))}
    for pid,panel in payload['panels'].items():
        for i in panel['indices']:memberships[i].add(pid)
    return [sorted(set.intersection(*(memberships[i] for i in face))) for face in payload['faces']]


def _closed_orientation(coords,faces,uses):
    """Refuse invalid closed-volume winding instead of reversing user geometry."""
    if not all(len(rows)==2 for rows in uses.values()):return False,[]
    if not all(rows[0][:2]==rows[1][:2][::-1] for rows in uses.values()):
        return True,[{'reason':'INCONSISTENT_CLOSED_WINDING'}]
    from a3d.contact_geometry import dot
    neighbors=[set() for _ in faces]
    for rows in uses.values():
        a,b=rows[0][2],rows[1][2];neighbors[a].add(b);neighbors[b].add(a)
    unseen=set(range(len(faces)));issues=[]
    while unseen:
        first=min(unseen);pending=[first];component=[];unseen.remove(first)
        while pending:
            current=pending.pop();component.append(current)
            for neighbor in neighbors[current]&unseen:
                unseen.remove(neighbor);pending.append(neighbor)
        indices=set(i for f in component for i in faces[f])
        origin=[sum(coords[i][k] for i in indices)/len(indices) for k in range(3)]
        volume=math.fsum(dot(sub(coords[faces[f][0]],origin),
            cross(sub(coords[faces[f][1]],origin),sub(coords[faces[f][2]],origin)))/6 for f in component)
        if volume<=0:issues.append({'reason':'NONPOSITIVE_ORIENTED_VOLUME','first_triangle':first,
                                     'face_count':len(component),'signed_volume_cm3':volume})
    return True,issues


def build_contact_context(payload,colliders,*,clearance_cm=0.,self_clearance_cm=0.,
                          seam_tolerance_cm=.15,max_penetration_cm=0.,max_pairs=200000,check_self=True):
    """Capture fixed evaluated collision surfaces. Changed bodies are refused.

    Open collider meshes support surface contact only; closed orientable meshes
    additionally support signed inside/outside checks. Rebuild after an explicit
    body transition; rebuilding alone never validates that body's trajectory.
    """
    from mathutils import Vector
    from mathutils.bvhtree import BVHTree
    for value in (clearance_cm,self_clearance_cm,seam_tolerance_cm,max_penetration_cm):
        if not math.isfinite(value) or value<0:raise StudioError('Contact reserves and tolerances must be finite and nonnegative')
    if type(max_pairs) is not int or max_pairs<1:raise StudioError('Contact pair budget must be positive')
    bodies=[]
    for obj in colliders:
        coords,faces,polygons,identity=_surface(obj)
        uses={}
        for index,face in enumerate(faces):
            for a,b in zip(face,face[1:]+face[:1]):uses.setdefault(tuple(sorted((a,b))),[]).append((a,b,index))
        closed,orientation_issues=_closed_orientation(coords,faces,uses)
        triangles=_triangles(coords,faces)
        bodies.append({'object':obj,'name':obj.name,'coords':coords,'faces':faces,'polygons':polygons,
            'sha256':identity,'triangles':triangles,'aabb':TriangleBVH(triangles),'closed':closed,
            'orientation_issues':orientation_issues,
            'max_edge_cm':_max_edge(triangles),
            'tree':BVHTree.FromPolygons([Vector([v/100 for v in p]) for p in coords],faces,all_triangles=True),
            'snapshot':{'object':obj.name,'dimensions_cm':[max(p[k] for p in coords)-min(p[k] for p in coords) for k in range(3)]}})
    source={key:copy.deepcopy(payload[key]) for key in ('faces','panels','seams','rest_cm')}
    if payload.get('source_rest_triangles_cm'):source['source_rest_triangles_cm']=copy.deepcopy(payload['source_rest_triangles_cm'])
    if payload.get('rest_mode'):source['rest_mode']=payload['rest_mode']
    return {'version':VERSION,'source':source,'source_sha256':digest(source),'owners':_owners(payload),
        'bodies':bodies,'clearance_cm':clearance_cm,'self_clearance_cm':self_clearance_cm,
        'seam_tolerance_cm':seam_tolerance_cm,'max_penetration_cm':max_penetration_cm,
        'max_pairs':max_pairs,'check_self':bool(check_self)}


def _body_binding(context):
    for body in context['bodies']:
        if body['orientation_issues']:
            return {'ok':False,'reason':'COLLIDER_VOLUME_ORIENTATION','collider':body['name'],
                    'orientation_issues':body['orientation_issues'],'status':'REFUSED'}
        try:identity=_surface(body['object'])[3]
        except Exception as error:return {'ok':False,'reason':'COLLIDER_UNAVAILABLE','collider':body['name'],'error':str(error)}
        if identity!=body['sha256']:
            return {'ok':False,'reason':'COLLIDER_GEOMETRY_CHANGED','collider':body['name'],
                    'expected_sha256':body['sha256'],'observed_sha256':identity,
                    'body_motion':'NOT_COVERED_REQUIRES_EXPLICIT_TRAJECTORY'}
    return None


def _face(context,index):
    source=context['source'];face=source['faces'][index]
    uv=source.get('source_rest_triangles_cm')
    return {'face':index,'pieces':context['owners'][index],'vertices':list(face),
        'source_uv_cm':uv[index] if uv else [source['rest_cm'][i][:2] for i in face]}


def _adjacency(payload,coords,tolerance):
    partner={i:set() for i in range(len(coords))};settled=set()
    if payload.get('rest_mode')!='assembled_3d':
        for seam in payload['seams'].values():
            if seam['kind']!='permanent':continue
            for a,b in seam['pairs']:
                if math.dist(coords[a],coords[b])<=tolerance:
                    partner[a].add(b);partner[b].add(a);settled.add(tuple(sorted((a,b))))
    neighbors=[set(face) for face in payload['faces']]
    return lambda a,b:bool(neighbors[a]&neighbors[b] or any(partner[i]&neighbors[b] for i in neighbors[a])),len(settled)


def precise_self_contacts(payload,coords,tolerance,clearance=0.,max_pairs=200000):
    triangles=_triangles(coords,payload['faces']);tree=TriangleBVH(triangles)
    adjacent,settled=_adjacency(payload,coords,tolerance)
    epsilon=max(1e-10,_max_edge(triangles)*1e-10)
    contacts=[];excluded=0;tested=0;candidates=0;count=0;overlaps=0;feature_tests=0
    for a,b in tree.pairs(tree,clearance+epsilon,same=True):
        candidates+=1
        if adjacent(a,b):excluded+=1;continue
        tested+=1
        if tested>max_pairs:
            return {'ok':False,'reason':'CONTACT_PAIR_BUDGET','tested_pairs':tested-1,'max_pairs':max_pairs,
                    'nonadjacent_overlap_count':overlaps,'nonadjacent_face_overlaps':[r['faces'] for r in contacts]}
        if separated_projection(triangles[a],triangles[b],clearance+epsilon):continue
        feature_tests+=1
        contact=triangle_contact(triangles[a],triangles[b])
        intersection=contact['kind']!='SEPARATED'
        if intersection or contact['distance_cm']<clearance-contact['numerical_epsilon_cm']:
            count+=1;overlaps+=int(intersection)
            if len(contacts)<32:contacts.append({'faces':[a,b],**contact,'required_clearance_cm':clearance})
    return {'ok':count==0,'version':VERSION,'nonadjacent_face_overlaps':[r['faces'] for r in contacts],
        'nonadjacent_overlap_count':overlaps,'contact_count':count,'contacts':contacts,
        'broadphase_candidates':candidates,'tested_pairs':tested,'excluded_adjacency_pairs':excluded,
        'closest_feature_tests':feature_tests,
        'coverage':COVERAGE,'broadphase':'CONSERVATIVE_TRIANGLE_AABB_BVH_DISTANCE_LOWER_BOUND',
        'seam_adjacency_policy':'DIRECT_DECLARED_PERMANENT_PAIRS_WITHIN_TOLERANCE_NO_TRANSITIVE_UNION',
        'settled_direct_permanent_pairs':settled,'declared_seam_adjacency_tolerance_cm':tolerance,
        'required_clearance_cm':clearance,'max_pairs':max_pairs}


def _check_contacts(context,coords,frame=None,verify_body=True):
    from blender.pattern_assembly import collision_check
    source=context['source']
    if len(coords)!=len(source['rest_cm']) or any(len(p)!=3 or any(not math.isfinite(v) for v in p) for p in coords):
        raise StudioError('Contact coordinates must match the finite current source map')
    result={'ok':True,'version':VERSION,'frame':frame,'source_sha256':context['source_sha256'],
        'colliders':[{'object':b['name'],'geometry_sha256':b['sha256'],'closed_volume':b['closed']} for b in context['bodies']],
        'clearance_cm':context['clearance_cm'],'max_penetration_cm':context['max_penetration_cm'],
        'max_pairs':context['max_pairs'],'coverage':COVERAGE,'qualification':'NONE'}
    changed=_body_binding(context) if verify_body else None
    if changed:return {**result,**changed}
    triangles=_triangles(coords,source['faces']);cloth_tree=TriangleBVH(triangles)
    samples=list(coords)+[[sum(p[k] for p in t)/3 for k in range(3)] for t in triangles]
    closed=[body for body in context['bodies'] if body['closed']]
    signed=collision_check(samples,[b['tree'] for b in closed],[b['snapshot'] for b in closed],
        context['clearance_cm'] if context['clearance_cm']>0 else -context['max_penetration_cm'],
        surface_triangles=[b['triangles'] for b in closed])
    result.update(ok=signed['ok'],minimum_signed_offset_cm=signed['minimum_signed_offset_cm'],
                  worst=copy.deepcopy(signed['worst']),point_samples=signed)
    if result['worst']:
        body=next(body for body in closed if body['name']==result['worst']['collider'])
        triangle=result['worst']['face']
        result['worst'].update(collider_triangle=triangle,collider_face=body['polygons'][triangle])
        sample=result['worst']['sample']
        if sample>=len(coords):result['worst'].update(_face(context,sample-len(coords)))
        else:result['worst'].update(vertex=sample,pieces=sorted(pid for pid,p in source['panels'].items() if sample in p['indices']))
    tested=0;contacts=[];count=0;minimum=None;surface_kinds={}
    for body in context['bodies']:
        epsilon=max(1e-10,max(_max_edge(triangles),body['max_edge_cm'])*1e-10)
        for a,b in cloth_tree.pairs(body['aabb'],context['clearance_cm']+epsilon):
            tested+=1
            if tested>context['max_pairs']:
                return {**result,'ok':False,'reason':'CONTACT_PAIR_BUDGET','tested_pairs':tested-1,'contacts':contacts}
            if separated_projection(triangles[a],body['triangles'][b],context['clearance_cm']+epsilon):continue
            contact=triangle_contact(triangles[a],body['triangles'][b])
            surface_kinds[contact['kind']]=surface_kinds.get(contact['kind'],0)+1
            minimum=contact['distance_cm'] if minimum is None else min(minimum,contact['distance_cm'])
            # Crossing a surface is not made acceptable by a penetration budget.
            bad=contact['kind']=='TRANSVERSE_INTERSECTION' or contact['distance_cm']<context['clearance_cm']-contact['numerical_epsilon_cm']
            if bad:
                count+=1
                if len(contacts)<32:contacts.append({**_face(context,a),**contact,'collider':body['name'],
                    'collider_triangle':b,'collider_face':body['polygons'][b],
                    'required_clearance_cm':context['clearance_cm'],
                    'depth_cm':None,'depth_scope':'INTERSECTION_HAS_NO_SINGLE_PENETRATION_DEPTH'})
    result.update(ok=result['ok'] and count==0,contact_count=count,contacts=contacts,tested_pairs=tested,
                  minimum_candidate_triangle_distance_cm=minimum,
                  surface_pair_kinds=surface_kinds,
                  broadphase='CONSERVATIVE_TRIANGLE_AABB_BVH_DISTANCE_LOWER_BOUND')
    if context['check_self']:
        self_report=precise_self_contacts(source,coords,context['seam_tolerance_cm'],context['self_clearance_cm'],
                                         max(0,context['max_pairs']-tested))
        for contact in self_report.get('contacts',[]):
            contact['source_faces']=[_face(context,index) for index in contact['faces']]
        result['self_contact']=self_report;result['ok']=result['ok'] and self_report['ok']
    result['status']='CONTACTS_CLEAR_STATIC' if result['ok'] else 'REFUSED'
    return result


def check_contacts(context,coords,frame=None):
    """Check one actual state; no claim about unobserved times between states."""
    return _check_contacts(context,coords,frame)


def check_motion(context,previous,coords,previous_frame,frame,*,max_step_cm,max_subdivisions):
    """Vertex segments plus bounded linearly interpolated triangle snapshots.

    This is discrete trajectory evidence, not exhaustive continuous collision
    detection. A changed collider or an insufficient subdivision budget refuses
    the motion instead of silently dropping samples or changing the reserve.
    """
    from mathutils import Vector
    if not math.isfinite(max_step_cm) or max_step_cm<=0 or type(max_subdivisions) is not int or max_subdivisions<1:
        raise StudioError('Discrete contact motion requires explicit positive step and subdivision budgets')
    if len(previous)!=len(coords) or len(coords)!=len(context['source']['rest_cm']):
        raise StudioError('Contact motion topology changed')
    if any(len(point)!=3 or any(not math.isfinite(value) for value in point) for point in previous+coords):
        raise StudioError('Nonfinite or malformed contact motion coordinates')
    maximum=max((math.dist(a,b) for a,b in zip(previous,coords,strict=True)),default=0.)
    if not math.isfinite(maximum):raise StudioError('Nonfinite contact motion')
    subdivisions=max(1,math.ceil(maximum/max_step_cm))
    record={'ok':False,'version':VERSION,'frame':frame,'previous_frame':previous_frame,
        'max_vertex_step_cm':maximum,'max_step_cm':max_step_cm,'max_subdivisions':max_subdivisions,
        'required_subdivisions':subdivisions,'coverage':'VERTEX_SEGMENTS_AND_BOUNDED_LINEAR_INTERPOLATION_DISCRETE_NOT_EXHAUSTIVE_CCD',
        'collider_motion':'FIXED_BOUND_SURFACES_ONLY','qualification':'NONE'}
    changed=_body_binding(context)
    if changed:return {**record,**changed}
    if subdivisions>max_subdivisions:return {**record,'reason':'CONTACT_MOTION_UNDERSAMPLED','status':'REFUSED','evaluated_samples':0}
    # These rays catch a vertex passing completely through even a thin body
    # between snapshots. Interior endpoint contacts are still checked below.
    swept=[];tangent_events=0
    for index,(a,b) in enumerate(zip(previous,coords,strict=True)):
        start,end=(Vector([v/100 for v in p]) for p in (a,b));delta=end-start
        if delta.length==0:continue
        direction=delta.normalized()
        numerical=max(1e-10,max(*(abs(v) for v in start),*(abs(v) for v in end))*8*(2**-23))
        for body in context['bodies']:
            offset=0.
            for ray_event in range(64):
                hit,normal,face,distance=body['tree'].ray_cast(start+direction*offset,direction,delta.length-offset)
                if hit is None:break
                total=offset+distance
                if total>=delta.length-numerical:break
                if numerical<total and abs(normal.dot(direction))>1e-7:
                    # A ray can hit a side face precisely on its top edge while
                    # travelling along the top surface. Only an edge event with
                    # a nearby point ON an incident tangent surface establishes
                    # this local tangency; it never excuses a later ray hit.
                    triangle=[Vector([v/100 for v in p]) for p in body['triangles'][face]]
                    edge_distances=[]
                    for a,b in zip(triangle,triangle[1:]+triangle[:1]):
                        edge=b-a;t=max(0.,min(1.,(hit-a).dot(edge)/edge.length_squared))
                        edge_distances.append((hit-(a+edge*t)).length)
                    tangent=False
                    if min(edge_distances)<=numerical*2:
                        probe=min(numerical*8,total/2,(delta.length-total)/2)
                        for sign in (-1.,1.):
                            point=hit+direction*(probe*sign)
                            nearest,n,_,d=body['tree'].find_nearest(point)
                            if nearest is not None and d<=numerical*2 and abs(n.dot(direction))<=1e-7:
                                tangent=True;break
                    if tangent and context['clearance_cm']==0:
                        tangent_events+=1
                    else:
                        swept.append({'vertex':index,'pieces':sorted(pid for pid,p in context['source']['panels'].items() if index in p['indices']),
                            'collider':body['name'],'collider_triangle':face,'collider_face':body['polygons'][face],
                            'fraction':total/delta.length,'point_cm':[v*100 for v in hit],
                            'depth_cm':None,'reason':'SWEPT_RESERVE_CONTACT' if tangent else 'VERTEX_SEGMENT_CROSSES_SURFACE'})
                        break
                offset=total+numerical*4
                if offset>=delta.length:break
            else:
                return {**record,'reason':'SWEPT_RAY_BUDGET','status':'REFUSED','vertex':index,
                        'collider':body['name'],'ray_event_budget':64,'evaluated_samples':0}
            if len(swept)>=32:break
        if len(swept)>=32:break
    if swept:return {**record,'reason':'SWEPT_VERTEX_CROSSING','status':'REFUSED','swept_contacts':swept,
                     'external_tangent_events':tangent_events,'evaluated_samples':0}
    worst=None;count=0
    for index in range(subdivisions+1):
        fraction=index/subdivisions
        candidate=[[a[k]+fraction*(b[k]-a[k]) for k in range(3)] for a,b in zip(previous,coords,strict=True)]
        current=_check_contacts(context,candidate,frame,verify_body=False);count+=1
        if not current['ok']:
            return {**record,'status':'REFUSED','reason':'INTERPOLATED_CONTACT','fraction':fraction,
                    'evaluated_samples':count,'contact':current}
        if worst is None or (current['minimum_signed_offset_cm'] is not None and
                             (worst['minimum_signed_offset_cm'] is None or current['minimum_signed_offset_cm']<worst['minimum_signed_offset_cm'])):
            worst=current
    return {**record,'ok':True,'status':'CONTACTS_CLEAR_DISCRETE','evaluated_samples':count,
            'actual_max_step_cm':maximum/subdivisions,'worst_sample':worst,'swept_contacts':[],
            'external_tangent_events':tangent_events}
