"""Bounded interior smoothing; source boundary anchors and topology never move."""
import math
from .core import StudioError
from .cloth_metrics import triangle_metrics


def improve_interior(vertices,faces,boundary_indices,*,target_angle,min_edge,max_displacement,passes=8):
    """Improve only derived interior coordinates under explicit finite budgets.

    Both windings are supported; every triangle retains its initial sign.
    Topological boundary vertices are fixed even if omitted by the caller.
    A returned candidate can remain below target and is never a source repair.
    """
    if (not vertices or not faces
            or any(len(p)!=2 or any(type(x) not in (float,int) or not math.isfinite(x) for x in p) for p in vertices)
            or type(passes) is not int or passes<0
            or any(type(x) not in (float,int) or not math.isfinite(x) for x in (target_angle,min_edge,max_displacement))
            or not 0<target_angle<=60 or min_edge<=0 or max_displacement<0):
        raise StudioError('Interior refinement needs finite 2D geometry and nonnegative bounded settings')
    source=[list(v) for v in vertices];points=[p[:] for p in source]
    fixed=set(boundary_indices);incident=[[] for _ in points];neighbors=[set() for _ in points]
    if any(type(i) is not int or not 0<=i<len(points) for i in fixed):
        raise StudioError('Interior refinement boundary anchor index is invalid')
    edges={};orientation=[]
    for fi,face in enumerate(faces):
        if len(face)!=3 or len(set(face))!=3 or any(type(i) is not int or not 0<=i<len(points) for i in face):
            raise StudioError('Interior refinement requires valid indexed triangles')
        a,b,c=[points[i] for i in face]
        signed=(b[0]-a[0])*(c[1]-a[1])-(b[1]-a[1])*(c[0]-a[0])
        if not math.isfinite(signed) or abs(signed)<=1e-12:
            raise StudioError('Interior refinement cannot repair a collapsed source triangle')
        orientation.append(1 if signed>0 else -1)
        for a,b in zip(face,face[1:]+face[:1]):
            edges.setdefault(tuple(sorted((a,b))),[]).append((a,b))
        for i in face:
            incident[i].append(fi);neighbors[i].update(j for j in face if j!=i)
    if any(len(uses)>2 or (len(uses)==2 and uses[0]==uses[1]) for uses in edges.values()):
        raise StudioError('Interior refinement cannot repair inconsistent source mesh topology')
    boundary={i for edge,uses in edges.items() if len(uses)==1 for i in edge}
    fixed.update(boundary)
    def state(ids):
        rows=[triangle_metrics([points[i] for i in faces[f]]) for f in ids]
        return (min((r['min_angle_degrees'] for r in rows),default=180.),
            min((min(r['edges_cm']) for r in rows),default=math.inf),
            sum(max(0.,target_angle-r['min_angle_degrees'])**2 for r in rows),
            [r['min_angle_degrees'] for r in rows])
    before=state(range(len(faces)));moves=0;completed=0
    for iteration in range(passes):
        changed=False
        for i in range(len(points)):
            if i in fixed or not incident[i]:continue
            old=state(incident[i])
            if old[0]>=target_angle-1e-7:continue
            origin=points[i][:];near=sorted(neighbors[i])
            center=[sum(points[j][k] for j in near)/len(near) for k in range(2)]
            targets=[center]
            for f,angle in zip(incident[i],old[3]):
                if angle>=target_angle:continue
                others=[j for j in faces[f] if j!=i];a,b=[points[j] for j in others]
                length=math.dist(a,b);mid=[(a[k]+b[k])/2 for k in range(2)]
                normal=[-(b[1]-a[1])/length,(b[0]-a[0])/length]
                if sum(normal[k]*(origin[k]-mid[k]) for k in range(2))<0:normal=[-x for x in normal]
                # A thin triangle opposite a tiny immutable boundary segment
                # needs its interior apex nearer that segment, not the distant
                # neighbour barycentre. This is a target, never a forced move.
                height=.45*length/math.tan(math.radians(target_angle)/2)
                targets.append([mid[k]+normal[k]*height for k in range(2)])
            best=None;best_state=None
            for target in targets:
                for fraction in (1.,.5,.25,.125,.0625):
                    trial=[origin[k]+fraction*(target[k]-origin[k]) for k in range(2)]
                    if math.dist(source[i],trial)>max_displacement:continue
                    points[i]=trial
                    # No reflection, collapse or boundary crossing through an
                    # incident triangle is allowed, whichever winding was supplied.
                    positive=all(orientation[f]*((points[b][0]-points[a][0])*(points[c][1]-points[a][1])-
                        (points[b][1]-points[a][1])*(points[c][0]-points[a][0]))>1e-12
                        for f in incident[i] for a,b,c in (faces[f],))
                    new=state(incident[i]) if positive else None
                    if (new and new[0]>=old[0]-1e-7 and new[1]>=min(min_edge,old[1])-1e-9
                            and new[2]<old[2]-1e-9
                            and all(after>=min(target_angle,before)-1e-7 for before,after in zip(old[3],new[3]))
                            and (best_state is None or (-new[0],new[2])<(-best_state[0],best_state[2]))):
                        best=trial;best_state=new
                    points[i]=origin
            if best is not None:points[i]=best;changed=True;moves+=1
        completed=iteration+1
        if not changed:break
    after=state(range(len(faces)))
    return points,{'algorithm':'BOUNDED_INTERIOR_LOCAL_ANGLE_IMPROVEMENT_V2',
        'passes':completed,'accepted_vertex_moves':moves,'boundary_anchors_changed':False,
        'boundary_vertex_count':len(boundary),'fixed_vertex_count':len(fixed),
        'topology_changed':False,'min_angle_before_degrees':before[0],
        'min_angle_after_degrees':after[0],'min_edge_after_cm':after[1],
        'maximum_displacement_cm':max((math.dist(a,b) for a,b in zip(source,points)),default=0.),
        'displacement_budget_cm':max_displacement,
        'target_reached':bool(faces) and after[0]>=target_angle-1e-7 and after[1]>=min_edge,
        'remaining_bad_faces':[f for f in range(len(faces)) if state([f])[0]<target_angle-1e-7 or state([f])[1]<min_edge]}
