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


def _semantic_cohorts(payload,selected,active,fixed,initial,binding,seam_ids,gap,budget,deadline,clock):
    """Quotient actual permanent pairs; vertex proximity never creates a link."""
    seams=payload.get('seams')
    if not isinstance(seams,dict) or any(sid not in seams for sid in seam_ids):
        raise StudioError('Coupled guide recovery requires exact existing permanent seam IDs')
    owners={}
    for pid,panel in payload['panels'].items():
        for index in panel['indices']:owners.setdefault(index,set()).add(pid)
    if any(owners[index]-selected for index in active):
        raise StudioError('Coupled guide recovery cannot move a vertex owned by an unselected piece')
    boundaries={};piece_counts={pid:{}for pid in selected}
    for offset,(face,owner)in enumerate(zip(payload['faces'],binding['source_face_pieces'])):
        if offset%256==0 and clock()>=deadline:
            raise StudioError('Coupled guide recovery time budget exhausted before alignment')
        if owner in selected:
            counts=piece_counts[owner]
            for a,b in zip(face,face[1:]+face[:1]):
                edge=tuple(sorted((a,b)));counts[edge]=counts.get(edge,0)+1
    for pid,counts in piece_counts.items():
        if clock()>=deadline:raise StudioError('Coupled guide recovery time budget exhausted before alignment')
        if not counts or any(count>2 for count in counts.values()):
            raise StudioError('Coupled guide recovery requires actual manifold source boundaries')
        boundaries[pid]={edge for edge,count in counts.items() if count==1}
    parent={index:index for index in active}
    def root(index):
        while parent[index]!=index:
            parent[index]=parent[parent[index]];index=parent[index]
        return index
    def union(a,b):
        a,b=root(a),root(b)
        if a!=b:parent[max(a,b)]=min(a,b)
    relations=[]
    for sid in sorted(seam_ids):
        if clock()>=deadline:raise StudioError('Coupled guide recovery time budget exhausted before alignment')
        seam=seams[sid]
        if not isinstance(seam,dict) or seam.get('kind')!='permanent':
            raise StudioError('Coupled guide recovery accepts only declared permanent source seams: '+sid)
        a,b=seam.get('piece_a'),seam.get('piece_b')
        if a not in selected or b not in selected:
            raise StudioError('Coupled source seam crosses an unselected piece: '+sid)
        pairs=seam.get('pairs');parameters=seam.get('parameters')
        if (not isinstance(pairs,list) or len(pairs)<2 or any(not isinstance(pair,(list,tuple))
                or len(pair)!=2 or any(type(i)is not int or i not in active for i in pair)for pair in pairs)
                or len({tuple(pair)for pair in pairs})!=len(pairs)):
            raise StudioError('Coupled guide recovery requires unique actual source seam pairs: '+sid)
        if parameters is not None and (not isinstance(parameters,list)or len(parameters)!=len(pairs)
                or any(type(t)not in(int,float)or not math.isfinite(t)or not 0<=t<=1 for t in parameters)
                or parameters[0]!=0 or parameters[-1]!=1
                or any(x>=y for x,y in zip(parameters,parameters[1:]))):
            raise StudioError('Coupled guide recovery rejects changed source seam parameters: '+sid)
        orientation=seam.get('orientation')
        if orientation is not None and orientation not in('forward','reverse'):
            raise StudioError('Coupled guide recovery requires an explicit valid source seam orientation')
        edges={}
        for side,pid,column in (('a',a,0),('b',b,1)):
            panel=payload['panels'][pid];paired=[pair[column]for pair in pairs]
            if len(set(paired))!=len(paired) or not set(paired)<=set(panel['indices']):
                raise StudioError('Source seam vertices do not belong to their exact source piece: '+sid)
            if 'boundary'in panel and not set(paired)<=set(panel['boundary']):
                raise StudioError('Source seam vertices are not on their declared native boundary: '+sid)
            candidates=[]
            for name,ids in panel.get('edges',{}).items():
                if (not isinstance(ids,list)or len(ids)<2 or any(type(i)is not int or i not in active for i in ids)
                        or len(set(ids))!=len(ids)or not set(ids)<=set(panel['indices'])):continue
                if any(tuple(sorted(edge))not in boundaries[pid]for edge in zip(ids,ids[1:])):continue
                if paired==ids or paired==list(reversed(ids)):candidates.append(name)
            explicit=seam.get('edge_'+side)
            if explicit is not None:
                if explicit not in candidates:raise StudioError('Source seam does not cover its exact named boundary: '+sid)
                name=explicit
            elif len(candidates)==1:name=candidates[0]
            else:raise StudioError('Source seam requires an unambiguous actual named boundary: '+sid)
            ids=panel['edges'][name]
            if orientation is not None:
                expected=list(reversed(ids))if side=='b'and orientation=='reverse'else ids
                if paired!=expected:raise StudioError('Source seam pair order contradicts its named boundary orientation: '+sid)
            edges[side]=name
        for first,last in pairs:union(first,last)
        relations.append({'seam_id':sid,'piece_a':a,'piece_b':b,'edge_a':edges['a'],'edge_b':edges['b'],
                          'pairs_sha256':digest(pairs),'source_seam_sha256':digest(seam),'pair_count':len(pairs)})
    groups={}
    for index in sorted(active):groups.setdefault(root(index),[]).append(index)
    aligned=copy.deepcopy(initial);records=[]
    for representative,members in groups.items():
        if len(members)<2:continue
        diameter=0.
        for offset,index in enumerate(members):
            if clock()>=deadline:raise StudioError('Coupled guide recovery time budget exhausted before alignment')
            for next_offset,j in enumerate(members[offset+1:]):
                if next_offset%256==0 and clock()>=deadline:
                    raise StudioError('Coupled guide recovery time budget exhausted before alignment')
                diameter=max(diameter,math.dist(initial[index],initial[j]))
        if diameter>gap:raise StudioError('Initial semantic seam cohort exceeds the declared seam gap budget')
        pinned=[index for index in members if index in fixed]
        if pinned and any(digest(initial[index])!=digest(initial[pinned[0]])for index in pinned[1:]):
            raise StudioError('Semantic seam cohort has incompatible exact fixed source stops or pins')
        if pinned:point=list(initial[pinned[0]])
        else:
            anchor=initial[members[0]]
            point=[anchor[k]+math.fsum(initial[index][k]-anchor[k]for index in members)/len(members)for k in range(3)]
        for index in members:aligned[index]=list(point)
        displacement=max(math.dist(initial[index],point)for index in members)
        if displacement>budget:raise StudioError('Semantic seam alignment exceeds the declared displacement budget')
        records.append({'representative':representative,'indices':members,'initial_gap_cm':diameter,
                        'fixed_source_indices':pinned,'initial_alignment_displacement_cm':displacement})
    validate_linear_motion(payload,initial,aligned)
    return groups,aligned,{'seam_ids':sorted(seam_ids),'relations':relations,'cohorts':records,
        'initial_max_cohort_gap_cm':max((row['initial_gap_cm']for row in records),default=0.),
        'initial_alignment_displacement_cm':max((row['initial_alignment_displacement_cm']for row in records),default=0.),
        'initial_alignment': 'EXPLICIT_SEMANTIC_PAIRS_WITHIN_DECLARED_BUDGET',
        'topology_modified':False,'source_uv_modified':False,'weld_performed':False,'qualification':'NONE'}


def _fixed_stop_bounds(payload,coordinates,quality,protected_edges,binding,margin,deadline,clock):
    """A fixed chord cannot be longer than a bounded-strain material path."""
    segments={}
    for offset,(face,uv,pid)in enumerate(zip(payload['faces'],binding['source_rest_triangles_cm'],binding['source_face_pieces'])):
        if offset%256==0 and clock()>=deadline:
            raise StudioError('Fixed source stop preflight time budget exhausted before optimization')
        for offset,(a,b)in enumerate(zip(face,face[1:]+face[:1])):
            key=(pid,min(a,b),max(a,b))
            segments.setdefault(key,[]).append(math.dist(uv[offset],uv[(offset+1)%3]))
    records=[];binding_sha256=digest(binding)
    for edge in protected_edges:
        if clock()>=deadline:raise StudioError('Fixed source stop preflight time budget exhausted before optimization')
        pid,name=edge['piece'],edge['edge'];ids=payload['panels'][pid]['edges'][name];lengths=[]
        for offset,(a,b)in enumerate(zip(ids,ids[1:])):
            if offset%256==0 and clock()>=deadline:
                raise StudioError('Fixed source stop preflight time budget exhausted before optimization')
            candidates=segments.get((pid,min(a,b),max(a,b)),[])
            if len(candidates)!=1 or not math.isfinite(candidates[0])or candidates[0]<=0:
                raise StudioError('Protected source stop requires one exact source-UV boundary path: '+pid+'/'+name)
            lengths.append(candidates[0])
        length=math.fsum(lengths);chord=math.dist(coordinates[ids[0]],coordinates[ids[-1]])
        records.append({'piece':pid,'edge':name,'source_vertex_indices':list(ids),
            'source_uv_path_length_cm':length,'fixed_stop_indices':[ids[0],ids[-1]],
            'fixed_stop_coordinates_cm':[list(coordinates[ids[0]]),list(coordinates[ids[-1]])],
            'fixed_stop_chord_cm':chord,'minimum_required_stretch':chord/length,
            'maximum_declared_stretch':quality['max_stretch'],
            'source_uv_face_binding_sha256':binding_sha256,'numerical_margin':margin,
            'impossible_with_fixed_stops':chord/length>quality['max_stretch']+margin})
    return {'status':'IMPOSSIBLE_FIXED_STOPS'if any(row['impossible_with_fixed_stops']for row in records)else'NO_IMPOSSIBILITY_DETECTED',
        'method':'FIXED_STOP_CHORD_OVER_SOURCE_UV_BOUNDARY_POLYLINE',
        'numerical_margin':margin,'records':records,'qualification':'NONE',
        'sufficiency_for_metric_recovery':'NOT_GRANTED'}


def recover_guide_metric(payload,coordinates,quality,piece_ids,protected_edges=(),*,
        max_iterations=100,max_seconds=60.,max_displacement_cm=8.,max_step_cm=.5,
        cg_iterations=80,cg_tolerance=1e-5,stagnation_iterations=5,strain_weight=100.,protected_indices=(),
        seam_ids=(),max_initial_seam_gap_cm=None,fixed_stop_stretch_margin=0.,clock=time.monotonic):
    """Recover only declared pieces and freeze actual source stops/pins.

    Each protected edge is ``{piece,edge}``; its existing first and last source
    map vertices stay fixed. Interior boundary samples remain derived vertices.
    Every result remains unqualified until the normal downstream gates run.
    ``seam_ids`` explicitly selects permanent semantic pairs for a quotient
    solve; it requires a declared finite ``max_initial_seam_gap_cm``. Both seam
    owners must be active. Stops/pins stay exact, and no weld or UV change occurs.
    A fixed-stop chord/source-UV path bound rejects impossible stretch before
    optimization. Its explicit numerical margin never relaxes final metrics.
    """
    if (type(max_iterations)is not int or max_iterations<1 or type(cg_iterations)is not int or cg_iterations<1
            or type(stagnation_iterations)is not int or stagnation_iterations<1
            or any(type(v)not in (int,float) or not math.isfinite(v) or v<=0 for v in
                (max_seconds,max_displacement_cm,max_step_cm,cg_tolerance,strain_weight))):
        raise StudioError('Guide metric recovery needs finite positive declared budgets')
    if (not isinstance(seam_ids,(list,tuple))or any(not isinstance(sid,str)or not sid for sid in seam_ids)
            or len(seam_ids)!=len(set(seam_ids))):
        raise StudioError('Coupled guide recovery requires explicit unique source seam IDs')
    if ((seam_ids and max_initial_seam_gap_cm is None)or(max_initial_seam_gap_cm is not None
            and(type(max_initial_seam_gap_cm)not in(int,float)or not math.isfinite(max_initial_seam_gap_cm)
                or max_initial_seam_gap_cm<0))):
        raise StudioError('Coupled guide recovery needs an explicit finite nonnegative initial seam gap budget')
    if (type(fixed_stop_stretch_margin)not in(int,float)or not math.isfinite(fixed_stop_stretch_margin)
            or not 0<=fixed_stop_stretch_margin<=1e-6):
        raise StudioError('Fixed source stop bounds need a finite explicit numerical margin between zero and 1e-6')
    try:before=digest([payload,coordinates,quality,piece_ids,protected_edges,protected_indices,seam_ids,max_initial_seam_gap_cm,fixed_stop_stretch_margin])
    except(TypeError,ValueError)as error:
        raise StudioError('Guide metric recovery requires finite structured source inputs')from error
    start=clock();deadline=start+max_seconds
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
        if not isinstance(edge,dict):raise StudioError('Protected source stops require explicit piece and edge identities')
        if edge.get('piece')not in selected:raise StudioError('Protected source stop belongs to an undeclared repair piece')
        ids=payload['panels'][edge['piece']]['edges'].get(edge.get('edge'))
        if (not isinstance(ids,list)or len(ids)<2 or len(set(ids))!=len(ids)
                or any(type(i)is not int or i not in payload['panels'][edge['piece']]['indices'] for i in ids)):
            raise StudioError('Protected source stop requires an actual named source edge')
        fixed.update((ids[0],ids[-1]))
    if any(not active.intersection(payload['panels'][pid]['indices']).intersection(fixed) for pid in selected):
        raise StudioError('Each recovered source piece requires an explicit fixed source stop')
    protected=set(range(len(initial)))-active|fixed
    coupling=None;baseline=initial;groups={index:[index]for index in sorted(active)}
    if seam_ids:
        groups,baseline,coupling=_semantic_cohorts(payload,selected,active,fixed,initial,binding,
            seam_ids,max_initial_seam_gap_cm,max_displacement_cm,deadline,clock)
    representatives={index:root for root,members in groups.items()for index in members}
    fixed_roots={root for root,members in groups.items()if set(members)&fixed}
    free=sorted(set(groups)-fixed_roots)
    lookup={index:i for i,root in enumerate(free)for index in groups[root]}
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
    best=copy.deepcopy(baseline);best_energy=residual(best);history=[];stagnant=0;stop='ITERATION_BUDGET';iterations=0
    def admitted(points):
        try:validate_metrics(payload,points,quality,include_faces=False,include_bending=False)
        except StudioError:return False
        return True
    initial_valid=admitted(initial)
    stop_bounds=_fixed_stop_bounds(payload,initial,quality,protected_edges,binding,fixed_stop_stretch_margin,deadline,clock)
    impossible_stops=stop_bounds['status']=='IMPOSSIBLE_FIXED_STOPS'
    if impossible_stops:stop='FIXED_SOURCE_STOP_BOUND_EXCEEDS_METRIC'
    for iteration in range(1,1 if impossible_stops else max_iterations+1):
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
                    for j,h in zip(ids,gradients):
                        representative=representatives[j]
                        row[representative]=row.get(representative,0.)+weighted_area*_dot(g,h)
        diagonal=[row[free[i]] for i,row in enumerate(matrix)]
        rows=[[(lookup[j],weight) for j,weight in row.items() if j in lookup] for row in matrix]
        fixed_terms=[[(j,weight) for j,weight in row.items() if j not in lookup] for row in matrix]
        if any(d<=0 for d in diagonal):raise StudioError('Guide metric recovery source system is singular')
        for k in range(3):
            for index,terms in enumerate(fixed_terms):rhs[k][index]-=sum(weight*(baseline[j][k]-origin[k]) for j,weight in terms)
        trial=copy.deepcopy(best);linear=[]
        for k in range(3):
            solved,report=_pcg(rows,diagonal,rhs[k],[best[i][k]-origin[k] for i in free],cg_iterations,cg_tolerance,deadline,clock)
            linear.append(report)
            for root,value in zip(free,solved):
                for i in groups[root]:trial[i][k]=value+origin[k]
        if clock()>=deadline:stop='TIME_BUDGET';break
        raw=max((math.dist(best[i],trial[i]) for i in free),default=0.)
        factor=min(1.,max_step_cm/raw) if raw else 0.;accepted=False
        for fraction in (factor,factor/2,factor/4,factor/8):
            if coupling:
                candidate=copy.deepcopy(best)
                for root in free:
                    point=[best[root][k]+fraction*(trial[root][k]-best[root][k])for k in range(3)]
                    for index in groups[root]:candidate[index]=list(point)
            else:candidate=[[a[k]+fraction*(b[k]-a[k]) for k in range(3)] for a,b in zip(best,trial)]
            movement=max(math.dist(a,b) for a,b in zip(initial,candidate));energy=residual(candidate)
            if movement>max_displacement_cm or energy>=best_energy-1e-10:continue
            try:validate_linear_motion(payload,best,candidate)
            except StudioError:continue
            best=candidate;best_energy=energy;accepted=True;break
        history.append({'iteration':iteration,'energy':best_energy,'accepted':accepted,'linear_systems':linear,
            'max_displacement_cm':max(math.dist(a,b) for a,b in zip(initial,best))})
        stagnant=0 if accepted else stagnant+1
        if stagnant>=stagnation_iterations:stop='STAGNATION';break
    valid=not impossible_stops and admitted(best)
    if valid:stop='SOURCE_METRIC_RECOVERED'
    if digest([payload,coordinates,quality,piece_ids,protected_edges,protected_indices,seam_ids,max_initial_seam_gap_cm,fixed_stop_stretch_margin])!=before:
        raise StudioError('Guide metric recovery changed an immutable input')
    if any((digest(best[i])!=digest(initial[i])if coupling else best[i]!=initial[i])for i in protected):
        raise StudioError('Guide metric recovery changed a protected source stop or undeclared piece')
    if coupling:
        coupling['final_max_cohort_gap_cm']=max((math.dist(best[i],best[j])for members in groups.values()
                                               for i,j in zip(members,members[1:])),default=0.)
        if coupling['final_max_cohort_gap_cm']!=0.:
            raise StudioError('Guide metric quotient recovery did not preserve exact semantic seam equality')
        coupling['quotient_unknown_count']=len(free)
        coupling['free_vertex_count']=len(lookup)
        coupling['fixed_cohort_indices']=sorted(i for root in fixed_roots for i in groups[root])
    final=evaluate_metrics(payload,best,include_faces=False,include_bending=False)
    result={'version':1,'status':'SOURCE_METRIC_RECOVERED' if valid else 'NEEDS_CORRECTION','stop_reason':stop,
        'coordinates_cm':best,'source_payload_sha256':digest(payload),'initial_candidate_sha256':digest(initial),
        'candidate_sha256':digest(best),'initial_metric_valid':initial_valid,'metric':final,
        'fixed_stop_bounds':stop_bounds,
        'piece_ids':sorted(selected),'protected_indices':sorted(protected),
        'policy':{'quality':copy.deepcopy(quality),'max_iterations':max_iterations,'max_seconds':max_seconds,
            'max_displacement_cm':max_displacement_cm,'max_step_cm':max_step_cm,'cg_iterations':cg_iterations,
            'cg_tolerance':cg_tolerance,'stagnation_iterations':stagnation_iterations,'strain_weight':strain_weight,
            'protected_indices':list(protected_indices),
            'fixed_stop_stretch_margin':fixed_stop_stretch_margin,
            'protected_edges':copy.deepcopy(protected_edges)},
        'iterations':iterations,'elapsed_seconds':clock()-start,'history':history,'energy':best_energy,
        'max_displacement_cm':max(math.dist(a,b) for a,b in zip(initial,best)),
        'numerical_frame_origin_cm':origin,
        'source_mutated':False,'qualification':'NONE','contacts':'NOT_ASSESSED','simulation':'NOT_EXECUTED',
        'fitting':'NOT_EXECUTED','final_assessment':'UNCHANGED_DOWNSTREAM_GATES_REQUIRED'}
    if coupling:
        result['seam_coupling']=coupling
        result['policy'].update(seam_ids=list(seam_ids),max_initial_seam_gap_cm=max_initial_seam_gap_cm)
    return result
