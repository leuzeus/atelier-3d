"""Opt-in experimental prepositioning. No topology/rest edits or Cloth qualification."""
import numpy as np
from mathutils import Vector
from a3d.core import StudioError

def solve_prefit(payload,recipe,trees):
    options=recipe['experimental_prefit'];iterations=options['iterations']
    selected=options['seam_ids']
    n=len(payload['rest_cm']);rest=np.array(payload['rest_cm']);start=np.array(payload['placed_cm']);points=start.copy()
    parent=list(range(n))
    def root(i):
        while parent[i]!=i:parent[i]=parent[parent[i]];i=parent[i]
        return i
    active=set();members=set()
    for sid in selected:
        seam=payload['seams'][sid]
        for side in ('a','b'):active.update(payload['panels'][seam['piece_'+side]]['indices'])
        for a,b in seam['pairs']:parent[root(b)]=root(a);members.update((a,b))
    roots=sorted({root(i) for i in active});lookup={r:j for j,r in enumerate(roots)}
    node=np.array([lookup.get(root(i),-1) for i in range(n)]);m=len(roots)
    def project(value):
        p=Vector(value/100)
        for tree in trees:
            hit,normal,_,_=tree.find_nearest(p)
            if hit is not None and (p-hit).dot(normal)*100<options['clearance_cm']:p=hit+normal*(options['clearance_cm']/100)
        return np.array(p)*100
    reference={i for pid in options['reference_pieces'] for i in payload['panels'][pid]['indices']}
    fixed=set(reference)
    for declaration in options['fixed_edges']:
        indices=payload['panels'][declaration['piece']]['edges'][declaration['edge']]
        fixed.update(i for i in indices if not declaration['exclude_joined_vertices'] or i not in members)
    if not fixed <= active:raise StudioError('Prefit landmarks must belong to its active seam component')
    fixed_nodes={}
    for i in sorted(fixed):
        value=project(start[i]) if i in reference else start[i]
        j=node[i]
        if j in fixed_nodes and np.linalg.norm(fixed_nodes[j]-value)>1e-4:
            raise StudioError('Conflicting fixed landmarks on a selected seam; declare exclusions explicitly')
        fixed_nodes[j]=value
    # Every connected active panel group needs a declared reference. Otherwise
    # the reduced Laplacian has unconstrained rigid translation modes.
    panel_parent={pid:pid for pid,p in payload['panels'].items() if set(p['indices']) & active}
    def panel_root(pid):
        while panel_parent[pid]!=pid:pid=panel_parent[pid]
        return pid
    for sid in selected:
        seam=payload['seams'][sid];panel_parent[panel_root(seam['piece_b'])]=panel_root(seam['piece_a'])
    covered={panel_root(pid) for pid in options['reference_pieces']}
    if any(panel_root(pid) not in covered for pid in panel_parent):
        raise StudioError('Each active prefit component needs an explicit reference piece')
    fixed_ids=np.array(sorted(fixed_nodes));fixed_points=np.array([fixed_nodes[i] for i in fixed_ids])
    active_ids=np.array(sorted(active));q=np.zeros((m,3));count=np.zeros(m)
    np.add.at(q,node[active_ids],start[active_ids]);np.add.at(count,node[active_ids],1);q/=count[:,None]
    original_q=q.copy()
    edge=np.array(sorted({tuple(sorted((a,b))) for f in payload['faces'] if f[0] in active for a,b in zip(f,f[1:]+f[:1])}))
    a,b=edge[:,0],edge[:,1];va,vb=node[a],node[b];d=rest[a]-rest[b]
    lengths=np.linalg.norm(d,axis=1);w=1/lengths
    diagonal=np.zeros(m);np.add.at(diagonal,va,w);np.add.at(diagonal,vb,w)
    free=np.ones(m,dtype=bool);free[fixed_ids]=False
    def lap(x):
        y=np.zeros_like(x);delta=(x[va]-x[vb])*w[:,None]
        np.add.at(y,va,delta);np.add.at(y,vb,-delta);return y
    def solve(rhs,x,penalty,targets):
        def mv(value):
            result=lap(value)+penalty[:,None]*value;result[~free]=0;return result
        locked=np.zeros_like(x);locked[fixed_ids]=fixed_points
        right=rhs+penalty[:,None]*targets-lap(locked);right[~free]=0
        guess=x.copy();guess[~free]=0;r=right-mv(guess)
        pre=diagonal+penalty;z=r/np.maximum(pre,1e-10)[:,None];p=z.copy();rz=np.sum(r*z,axis=0)
        for _ in range(300):
            ap=mv(p);denom=np.sum(p*ap,axis=0)
            alpha=np.divide(rz,denom,out=np.zeros(3),where=np.abs(denom)>1e-25)
            guess+=p*alpha;r-=ap*alpha
            if np.max(np.abs(r))<1e-6:break
            z=r/np.maximum(pre,1e-10)[:,None];new=np.sum(r*z,axis=0)
            beta=np.divide(new,rz,out=np.zeros(3),where=np.abs(rz)>1e-25);p=z+p*beta;rz=new
        guess[fixed_ids]=fixed_points;return guess
    landmark_values=fixed_points.copy()
    fixed_points=landmark_values-original_q[fixed_ids]
    harmonic=solve(np.zeros((m,3)),np.zeros((m,3)),np.zeros(m),np.zeros((m,3)))
    q=original_q+harmonic;fixed_points=landmark_values;q[fixed_ids]=fixed_points
    history=[]
    for step in range(1,iterations+1):
        current=q[node[active_ids]];points[active_ids]=current
        cov=np.zeros((n,3,3));outer=d[:,:,None]*(points[a]-points[b])[:,None,:]*w[:,None,None]
        np.add.at(cov,a,outer);np.add.at(cov,b,outer)
        u,_,vh=np.linalg.svd(cov);v=np.swapaxes(vh,1,2);ut=np.swapaxes(u,1,2)
        sign=np.linalg.det(v@ut);v[:,:,2]*=np.where(sign<0,-1,1)[:,None];rotation=v@ut
        rotated=np.einsum('nij,nj->ni',(rotation[a]+rotation[b])*.5,d)*w[:,None]
        rhs=np.zeros((m,3));np.add.at(rhs,va,rotated);np.add.at(rhs,vb,-rotated)
        targets=np.array([project(p) for p in q]);contact=np.linalg.norm(targets-q,axis=1)>1e-5
        penalty=np.where(contact,diagonal*20,0.)
        q=solve(rhs,q,penalty,targets)
        # Signed surface samples are inequalities; settle contacts outside after
        # each local/global solve, retaining the explicit landmark constraints.
        for i in np.flatnonzero(free):q[i]=project(q[i])
        q[fixed_ids]=fixed_points
        points[active_ids]=q[node[active_ids]]
        ratios=np.linalg.norm(points[a]-points[b],axis=1)/lengths
        history.append({'step':step,'min_stretch':float(ratios.min()),'max_stretch':float(ratios.max()),
            'max_displacement_cm':float(np.linalg.norm(points-start,axis=1).max())})
        if not np.isfinite(points).all():raise StudioError('Non-finite experimental prefit candidate')
    return points.tolist(),history


def apply_prefit(obj,payload,recipe,trees):
    """Bound and recheck candidates on the disposable garment construction only."""
    import copy
    from a3d.core import digest
    from blender.sewing import distance,preflight
    options=recipe['experimental_prefit']
    original=copy.deepcopy(payload['placed_cm'])
    immutable=digest({k:payload[k] for k in ('rest_cm','faces','panels','seams','pins')})
    def set_points(coords):
        for i,p in enumerate(coords):
            value=[x/100 for x in p]
            obj.data.vertices[i].co=value
            obj.data.shape_keys.key_blocks[0].data[i].co=value
        obj.data.update()
    def gaps(coords):
        return {sid:max(distance(coords[a],coords[b]) for a,b in payload['seams'][sid]['pairs'])
                for sid in options['seam_ids']}
    report={'status':'REJECTED','experimental':True,'accepted':False,
        'simulation':'NOT_EXECUTED','visual_validation':'NOT_EXECUTED',
        'source_ref':options['source_ref'],'recipe_mesh_sha256':payload['recipe_mesh_sha256'],
        'seam_ids':options['seam_ids'],'reference_pieces':options['reference_pieces'],
        'fixed_edges':options['fixed_edges'],'before_gaps_cm':gaps(original),'rejections':[]}
    payload['experimental_prefit']=report
    try:
        target,history=solve_prefit(payload,recipe,trees)
        report['solver_history']=history
        displacement=max(distance(a,b) for a,b in zip(original,target,strict=True))
        if displacement<1e-6:raise StudioError('Experimental prefit produced no measurable placement change')
        fraction=min(1.,options['max_displacement_cm']/displacement)
        for _ in range(options['max_backtracks']+1):
            if fraction<options['min_fraction']:break
            candidate=[[a[k]+fraction*(b[k]-a[k]) for k in range(3)] for a,b in zip(original,target,strict=True)]
            set_points(candidate)
            try:context,_,_=preflight(obj,payload,recipe)
            except StudioError as exc:
                report['rejections'].append({'fraction':fraction,'error':str(exc)})
                fraction*=.5
                continue
            report.update(status='PREPOSITIONED_NOT_SIMULATED',fraction=fraction,
                max_displacement_cm=max(distance(a,b) for a,b in zip(original,candidate,strict=True)),
                after_gaps_cm=gaps(candidate),quality=context['quality'],
                collider_snapshots=context['colliders'])
            payload['placed_cm']=candidate;payload['quality']=context['quality']
            assert immutable==digest({k:payload[k] for k in ('rest_cm','faces','panels','seams','pins')})
            return context
        raise StudioError('Experimental prefit has no candidate within the declared displacement/fraction and existing preflight gates')
    except Exception:
        set_points(original)
        raise
