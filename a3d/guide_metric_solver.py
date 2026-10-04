"""Bounded local/global recovery of a derived guide's source UV metric.

Local polar projections use the original triangle metric. A matrix-free,
diagonally preconditioned conjugate-gradient solve reconciles shared vertices.
This is geometric preparation, never cloth, contact or fitting acceptance.
"""
import copy
import math
import time

from .cloth_metrics import evaluate_metrics,face_sources,validate_linear_motion,validate_metrics
from .core import StudioError,digest


def _dot(a,b):return sum(x*y for x,y in zip(a,b))


def _pcg(rows,diagonal,rhs,initial,maximum,tolerance,deadline,clock):
    def multiply(vector):return [sum(weight*vector[j] for j,weight in row) for row in rows]
    x=list(initial);ax=multiply(x);r=[b-a for a,b in zip(ax,rhs)];z=[v/d for v,d in zip(r,diagonal)]
    direction=list(z);rz=_dot(r,z);norm=max(math.sqrt(_dot(rhs,rhs)),1.);count=0
    for count in range(1,maximum+1):
        if math.sqrt(_dot(r,r))/norm<=tolerance or clock()>=deadline:break
        ad=multiply(direction);den=_dot(direction,ad)
        if den<=1e-24:break
        step=rz/den;x=[a+step*b for a,b in zip(x,direction)];r=[a-step*b for a,b in zip(r,ad)]
        z=[v/d for v,d in zip(r,diagonal)];next_rz=_dot(r,z)
        beta=next_rz/rz if rz else 0.;direction=[a+beta*b for a,b in zip(z,direction)];rz=next_rz
    return x,{'iterations':count,'relative_residual':math.sqrt(_dot(r,r))/norm}


def recover_guide_metric(payload,coordinates,quality,piece_ids,protected_edges=(),*,
        max_iterations=100,max_seconds=60.,max_displacement_cm=8.,max_step_cm=.5,
        cg_iterations=80,cg_tolerance=1e-5,stagnation_iterations=5,strain_weight=100.,protected_indices=(),clock=time.monotonic):
    """Recover only declared pieces and freeze actual source stops/pins.

    Each protected edge is ``{piece,edge}``; its existing first and last source
    map vertices stay fixed. Interior boundary samples remain derived vertices.
    Every result remains unqualified until the normal downstream gates run.
    """
    before=digest([payload,coordinates,quality,piece_ids,protected_edges,protected_indices]);start=clock();deadline=start+max_seconds
    if (type(max_iterations)is not int or max_iterations<1 or type(cg_iterations)is not int or cg_iterations<1
            or type(stagnation_iterations)is not int or stagnation_iterations<1
            or any(type(v)not in (int,float) or not math.isfinite(v) or v<=0 for v in
                (max_seconds,max_displacement_cm,max_step_cm,cg_tolerance,strain_weight))):
        raise StudioError('Guide metric recovery needs finite positive declared budgets')
    if not piece_ids or len(piece_ids)!=len(set(piece_ids)) or not set(piece_ids)<=payload['panels'].keys():
        raise StudioError('Guide metric recovery requires exact existing source piece IDs')
    initial=copy.deepcopy(coordinates);metrics=evaluate_metrics(payload,initial,include_faces=True,include_bending=False)
    binding=face_sources(payload)
    if binding['binding_issues']:raise StudioError('Guide metric recovery rejects changed source UV/topology bindings')
    selected=set(piece_ids);active={i for pid in selected for i in payload['panels'][pid]['indices']}
    # Solve displacements in a translated numerical frame. The physical world
    # offset must not set the conjugate-gradient stopping tolerance or leak
    # through cancellation in the zero-sum source gradient.
    origin=[math.fsum(initial[i][k] for i in sorted(active))/len(active) for k in range(3)]
    fixed=set()
    if any(type(i)is not int or not 0<=i<len(initial) for i in protected_indices):
        raise StudioError('Protected guide supports require exact actual source vertex indices')
    fixed.update(protected_indices)
    for index,weight in payload.get('pins',{}).items():
        if (not isinstance(index,str) or not index.isdigit() or str(int(index))!=index or
                not 0<=int(index)<len(initial) or type(weight)not in (int,float) or
                not math.isfinite(weight) or not 0<=weight<=1):
            raise StudioError('Guide metric recovery requires exact existing finite source pin weights')
        if weight>0:fixed.add(int(index))
    for edge in protected_edges:
        if edge.get('piece')not in selected:raise StudioError('Protected source stop belongs to an undeclared repair piece')
        ids=payload['panels'][edge['piece']]['edges'].get(edge.get('edge'))
        if not ids:raise StudioError('Protected source stop requires an actual named source edge')
        fixed.update((ids[0],ids[-1]))
    free=sorted(active-fixed);lookup={index:i for i,index in enumerate(free)}
    if any(not active.intersection(payload['panels'][pid]['indices']).intersection(fixed) for pid in selected):
        raise StudioError('Each recovered source piece requires an explicit fixed source stop')
    faces=[]
    for face,uv,pid in zip(payload['faces'],binding['source_rest_triangles_cm'],binding['source_face_pieces']):
        if pid not in selected:continue
        x1,y1=uv[1][0]-uv[0][0],uv[1][1]-uv[0][1];x2,y2=uv[2][0]-uv[0][0],uv[2][1]-uv[0][1]
        det=x1*y2-x2*y1
        if abs(det)<1e-8:raise StudioError('Guide metric recovery cannot repair a degenerate source triangle')
        gradients=[((y1-y2)/det,(x2-x1)/det),(y2/det,-x2/det),(-y1/det,x1/det)]
        area=abs(det)/2
        faces.append((list(face),gradients,area))
    def residual(points):
        total=0.
        for ids,gradients,area in faces:
            fu=[sum((points[i][k]-origin[k])*g[0] for i,g in zip(ids,gradients)) for k in range(3)]
            fv=[sum((points[i][k]-origin[k])*g[1] for i,g in zip(ids,gradients)) for k in range(3)]
            a,b,d=_dot(fu,fu),_dot(fu,fv),_dot(fv,fv)
            trace=a+d;delta=math.sqrt(max(0.,(a-d)**2+4*b*b))
            lo=math.sqrt(max(0.,(trace-delta)/2));hi=math.sqrt(max(0.,(trace+delta)/2))
            squared=(lo-1)**2+(hi-1)**2
            total+=area*(squared+strain_weight*squared*squared/2)
        return total
    best=copy.deepcopy(initial);best_energy=residual(best);history=[];stagnant=0;stop='ITERATION_BUDGET';iterations=0
    def admitted(points):
        try:validate_metrics(payload,points,quality,include_faces=False,include_bending=False)
        except StudioError:return False
        return True
    initial_valid=admitted(initial)
    for iteration in range(1,max_iterations+1):
        if admitted(best):stop='SOURCE_METRIC_RECOVERED';break
        if clock()>=deadline:stop='TIME_BUDGET';break
        iterations=iteration;rhs=[[0.]*len(free) for _ in range(3)];matrix=[{} for _ in free]
        for ids,gradients,area in faces:
            fu=[sum((best[i][k]-origin[k])*g[0] for i,g in zip(ids,gradients)) for k in range(3)]
            fv=[sum((best[i][k]-origin[k])*g[1] for i,g in zip(ids,gradients)) for k in range(3)]
            a,b,d=_dot(fu,fu),_dot(fu,fv),_dot(fv,fv);det=a*d-b*b
            if det<=1e-20:raise StudioError('Guide metric recovery rejects a collapsed current triangle')
            delta=math.sqrt(max(0.,(a-d)**2+4*b*b))
            lo=math.sqrt(max(0.,(a+d-delta)/2));hi=math.sqrt(max(0.,(a+d+delta)/2))
            weighted_area=area*(1+strain_weight*((lo-1)**2+(hi-1)**2))
            root=math.sqrt(det);scale=math.sqrt(a+d+2*root)/((a+root)*(d+root)-b*b)
            uu=scale*(d+root);uv=-scale*b;vv=scale*(a+root)
            u=[uu*x+uv*y for x,y in zip(fu,fv)];v=[uv*x+vv*y for x,y in zip(fu,fv)]
            for i,g in zip(ids,gradients):
                if i in lookup:
                    for k in range(3):rhs[k][lookup[i]]+=weighted_area*(u[k]*g[0]+v[k]*g[1])
                    row=matrix[lookup[i]]
                    for j,h in zip(ids,gradients):row[j]=row.get(j,0.)+weighted_area*_dot(g,h)
        diagonal=[row[free[i]] for i,row in enumerate(matrix)]
        rows=[[(lookup[j],weight) for j,weight in row.items() if j in lookup] for row in matrix]
        fixed_terms=[[(j,weight) for j,weight in row.items() if j not in lookup] for row in matrix]
        if any(d<=0 for d in diagonal):raise StudioError('Guide metric recovery source system is singular')
        for k in range(3):
            for index,terms in enumerate(fixed_terms):rhs[k][index]-=sum(weight*(initial[j][k]-origin[k]) for j,weight in terms)
        trial=copy.deepcopy(best);linear=[]
        for k in range(3):
            solved,report=_pcg(rows,diagonal,rhs[k],[best[i][k]-origin[k] for i in free],cg_iterations,cg_tolerance,deadline,clock)
            linear.append(report)
            for i,value in zip(free,solved):trial[i][k]=value+origin[k]
        if clock()>=deadline:stop='TIME_BUDGET';break
        raw=max((math.dist(best[i],trial[i]) for i in free),default=0.)
        factor=min(1.,max_step_cm/raw) if raw else 0.;accepted=False
        for fraction in (factor,factor/2,factor/4,factor/8):
            candidate=[[a[k]+fraction*(b[k]-a[k]) for k in range(3)] for a,b in zip(best,trial)]
            movement=max(math.dist(a,b) for a,b in zip(initial,candidate));energy=residual(candidate)
            if movement>max_displacement_cm or energy>=best_energy-1e-10:continue
            try:validate_linear_motion(payload,best,candidate)
            except StudioError:continue
            best=candidate;best_energy=energy;accepted=True;break
        history.append({'iteration':iteration,'energy':best_energy,'accepted':accepted,'linear_systems':linear,
            'max_displacement_cm':max(math.dist(a,b) for a,b in zip(initial,best))})
        stagnant=0 if accepted else stagnant+1
        if stagnant>=stagnation_iterations:stop='STAGNATION';break
    valid=admitted(best)
    if valid:stop='SOURCE_METRIC_RECOVERED'
    if digest([payload,coordinates,quality,piece_ids,protected_edges,protected_indices])!=before:
        raise StudioError('Guide metric recovery changed an immutable input')
    if any(best[i]!=initial[i] for i in set(range(len(initial)))-set(free)):
        raise StudioError('Guide metric recovery changed a protected source stop or undeclared piece')
    final=evaluate_metrics(payload,best,include_faces=False,include_bending=False)
    return {'version':1,'status':'SOURCE_METRIC_RECOVERED' if valid else 'NEEDS_CORRECTION','stop_reason':stop,
        'coordinates_cm':best,'source_payload_sha256':digest(payload),'initial_candidate_sha256':digest(initial),
        'candidate_sha256':digest(best),'initial_metric_valid':initial_valid,'metric':final,
        'piece_ids':sorted(selected),'protected_indices':sorted(set(range(len(initial)))-set(free)),
        'policy':{'quality':copy.deepcopy(quality),'max_iterations':max_iterations,'max_seconds':max_seconds,
            'max_displacement_cm':max_displacement_cm,'max_step_cm':max_step_cm,'cg_iterations':cg_iterations,
            'cg_tolerance':cg_tolerance,'stagnation_iterations':stagnation_iterations,'strain_weight':strain_weight,
            'protected_indices':list(protected_indices),
            'protected_edges':copy.deepcopy(protected_edges)},
        'iterations':iterations,'elapsed_seconds':clock()-start,'history':history,'energy':best_energy,
        'max_displacement_cm':max(math.dist(a,b) for a,b in zip(initial,best)),
        'numerical_frame_origin_cm':origin,
        'source_mutated':False,'qualification':'NONE','contacts':'NOT_ASSESSED','simulation':'NOT_EXECUTED',
        'fitting':'NOT_EXECUTED','final_assessment':'UNCHANGED_DOWNSTREAM_GATES_REQUIRED'}
