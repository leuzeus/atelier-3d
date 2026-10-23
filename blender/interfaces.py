"""Bounded local tangent preparation, with unchanged reference panels and rest."""
import heapq
import math
import numpy as np
from a3d.core import StudioError
from a3d.garment_rejections import seam_directions
from a3d.sewing import distance


def interface_candidate(payload,start,options):
    points=np.array(start,dtype=float);baseline=points.copy()
    edges=sorted({tuple(sorted((a,b))) for f in payload['faces'] for a,b in zip(f,f[1:]+f[:1])})
    adjacency={i:[] for i in range(len(start))}
    for a,b in edges:
        length=distance(start[a],start[b]);adjacency[a].append((b,length));adjacency[b].append((a,length))
    history=[]
    for iteration in range(options['max_passes']):
        seeds={};selected_pieces=set()
        before=seam_directions(payload,points.tolist())
        if not before['violations']:return points.tolist(),history
        for declaration in options['interfaces']:
            sid=declaration['seam_id'];side=declaration['moving_side'];seam=payload['seams'][sid]
            selected_pieces.add(seam['piece_'+side]);moving=0 if side=='a' else 1;reference=1-moving
            for first,second in zip(seam['pairs'],seam['pairs'][1:]):
                a,b=first[moving],second[moving];c,d=first[reference],second[reference]
                v=points[b]-points[a];u=points[d]-points[c]
                lv,lu=np.linalg.norm(v),np.linalg.norm(u)
                if min(lv,lu)<1e-10:raise StudioError('Undefined tangent cannot be repaired by local interface preparation')
                cosine=float(np.clip(np.dot(v,u)/(lv*lu),-1,1))
                if cosine>=options['target_cosine']:continue
                axis=np.cross(v,u);size=np.linalg.norm(axis)
                if size<1e-10:raise StudioError('Ambiguous antiparallel interface needs an explicit preparation frame')
                axis/=size;angle=math.acos(cosine)-math.acos(options['target_cosine'])
                rotated=v*math.cos(angle)+np.cross(axis,v)*math.sin(angle)+axis*np.dot(axis,v)*(1-math.cos(angle))
                center=(points[a]+points[b])/2
                for index,target in ((a,center-rotated/2),(b,center+rotated/2)):
                    if payload['pins'].get(str(index),0)>=1:raise StudioError('Local interface target would move a fixed pin')
                    seeds.setdefault(index,[]).append(target-points[index])
        if not seeds:return points.tolist(),history
        moving_ids={i for pid in selected_pieces for i in payload['panels'][pid]['indices']}
        distances={i:0. for i in seeds};queue=[(0.,i) for i in seeds];heapq.heapify(queue)
        while queue:
            dist,i=heapq.heappop(queue)
            if dist!=distances[i]:continue
            for j,length in adjacency[i]:
                value=dist+length
                if j in moving_ids and value<=options['radius_cm'] and value<distances.get(j,float('inf')):
                    distances[j]=value;heapq.heappush(queue,(value,j))
        active=sorted(distances);lookup={i:j for j,i in enumerate(active)}
        locked={lookup[i]:np.mean(values,axis=0) for i,values in seeds.items()}
        for i in active:
            if payload['pins'].get(str(i),0)>=1:locked[lookup[i]]=np.zeros(3)
        count=len(active);diagonal=np.zeros(count);links=[]
        for i in active:
            a=lookup[i]
            for j,length in adjacency[i]:
                weight=1/max(length,1e-8);diagonal[a]+=weight
                if j in lookup:links.append((a,lookup[j],weight))
        free=np.ones(count,dtype=bool);free[list(locked)]=False
        fixed=np.zeros((count,3))
        for i,value in locked.items():fixed[i]=value
        def lap(x):
            y=diagonal[:,None]*x
            for a,b,w in links:y[a]-=w*x[b]
            return y
        right=-lap(fixed);right[~free]=0
        def multiply(x):
            y=lap(x);y[~free]=0;return y
        delta=np.zeros((count,3));r=right.copy();z=r/np.maximum(diagonal,1e-10)[:,None];p=z.copy();rz=np.sum(r*z,axis=0)
        for _ in range(300):
            ap=multiply(p);den=np.sum(p*ap,axis=0);alpha=np.divide(rz,den,out=np.zeros(3),where=np.abs(den)>1e-25)
            delta+=p*alpha;r-=ap*alpha
            if np.max(np.abs(r))<1e-7:break
            z=r/np.maximum(diagonal,1e-10)[:,None];new=np.sum(r*z,axis=0)
            p=z+p*np.divide(new,rz,out=np.zeros(3),where=np.abs(rz)>1e-25);rz=new
        delta[~free]=fixed[~free];points[active]+=delta
        # Local length projection on the existing embedding, with the target
        # exterior/reference panels held fixed; shared endpoints remain movable.
        # It is preparation only, never a substitute for native Cloth gates.
        movable={i for i in active if payload['pins'].get(str(i),0)<1}
        local_edges=[(a,b,distance(start[a],start[b])) for a,b in edges if a in movable or b in movable]
        for _ in range(120):
            for a,b,length in local_edges:
                delta=points[b]-points[a];actual=np.linalg.norm(delta)
                if actual<1e-10:continue
                wa=int(a in movable);wb=int(b in movable)
                correction=delta*(1-length/actual)/(wa+wb)
                if wa:points[a]+=correction
                if wb:points[b]-=correction
            # Shared polyline endpoints must not be frozen at independently
            # averaged rotation targets: that would prescribe incompatible
            # adjacent edge lengths. Project angular inequalities jointly.
            for declaration in options['interfaces']:
                seam=payload['seams'][declaration['seam_id']];m=0 if declaration['moving_side']=='a' else 1
                for first,second in zip(seam['pairs'],seam['pairs'][1:]):
                    a,b=first[m],second[m];c,d=first[1-m],second[1-m]
                    v=points[b]-points[a];u=points[d]-points[c];size=np.linalg.norm(v)*np.linalg.norm(u)
                    if size<1e-10:continue
                    cosine=float(np.clip(np.dot(v,u)/size,-1,1))
                    if cosine>=options['target_cosine']:continue
                    axis=np.cross(v,u);norm=np.linalg.norm(axis)
                    if norm<1e-10:continue
                    axis/=norm;angle=math.acos(cosine)-math.acos(options['target_cosine'])
                    rotated=v*math.cos(angle)+np.cross(axis,v)*math.sin(angle)+axis*np.dot(axis,v)*(1-math.cos(angle))
                    wa=int(a in movable);wb=int(b in movable)
                    if wa+wb:
                        change=(rotated-v)/(wa+wb)
                        if wa:points[a]-=change
                        if wb:points[b]+=change
        movement=float(np.linalg.norm(points-baseline,axis=1).max())
        history.append({'pass':iteration+1,'source_indices':active,'seed_indices':sorted(seeds),
            'max_displacement_cm':movement,'before_violations':len(before['violations'])})
        if not np.isfinite(points).all() or movement>options['max_displacement_cm']:
            raise StudioError('Local interface preparation exceeded its finite displacement budget')
    return points.tolist(),history


def prepare_interfaces(obj,payload,recipe):
    from blender.sewing import commit_positions,preflight
    original=[list(p) for p in payload['placed_cm']]
    report={'status':'REJECTED','simulation':'NOT_EXECUTED','accepted':False,
        'source_ref':recipe['interface_preparation']['source_ref'],'before':seam_directions(payload,original)}
    payload['interface_preparation']=report
    try:
        coords,history=interface_candidate(payload,original,recipe['interface_preparation'])
        report.update(history=history,after=seam_directions(payload,coords),
            max_displacement_cm=max(distance(a,b) for a,b in zip(original,coords,strict=True)))
        commit_positions(obj,coords)
        context,_,_=preflight(obj,payload,recipe)
        payload['placed_cm']=coords
        report.update(status='PREPARED_NOT_SIMULATED',context=context)
        return context
    except Exception:
        commit_positions(obj,original)
        raise
