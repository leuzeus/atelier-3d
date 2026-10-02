"""Scoped source-seam placement with fixed exterior and final native gates."""
import numpy as np
from a3d.core import StudioError
from a3d.sewing import distance


def mount_candidate(payload,recipe):
    options=recipe['panel_mount'];start=np.array(payload['placed_cm']);q=start.copy()
    moving={i for pid in options['moving_pieces'] for i in payload['panels'][pid]['indices']}
    edges=np.array(sorted({tuple(sorted((a,b))) for f in payload['faces'] if f[0] in moving for a,b in zip(f,f[1:]+f[:1])}))
    a,b=edges[:,0],edges[:,1];rest=np.array(payload['rest_cm']);lengths=np.linalg.norm(rest[a]-rest[b],axis=1)
    weights=np.array([float(i in moving and payload['pins'].get(str(i),0)<1) for i in range(len(q))])
    degree=np.zeros(len(q));np.add.at(degree,a,1);np.add.at(degree,b,1)
    pairs=np.array([pair for sid in options['seam_ids'] for pair in payload['seams'][sid]['pairs']]);sa,sb=pairs[:,0],pairs[:,1]
    lo=recipe['mesh']['min_stretch']+options['strain_margin'];hi=recipe['mesh']['max_stretch']-options['strain_margin']
    def lengths_step():
        v=q[b]-q[a];actual=np.linalg.norm(v,axis=1);desired=np.clip(actual,lengths*lo,lengths*hi)
        correction=v*(1-desired/np.maximum(actual,1e-12))[:,None]
        delta=np.zeros_like(q);np.add.at(delta,a,correction);np.add.at(delta,b,-correction)
        q[:]+=delta/np.maximum(degree,1)[:,None]*weights[:,None]*.8
    def budget():
        movement=float(np.linalg.norm(q-start,axis=1).max())
        if not np.isfinite(q).all() or movement>options['max_displacement_cm']:
            raise StudioError('Scoped panel mount exceeded its finite displacement budget')
        return movement
    history=[]
    for step in range(options['iterations']):
        for _ in range(4):lengths_step()
        delta=np.zeros_like(q);counts=np.zeros(len(q));diff=q[sb]-q[sa];total=weights[sa]+weights[sb]
        change=diff/np.maximum(total,1)[:,None]
        np.add.at(delta,sa,change*weights[sa,None]);np.add.at(delta,sb,-change*weights[sb,None])
        np.add.at(counts,sa,weights[sa]);np.add.at(counts,sb,weights[sb]);q+=delta/np.maximum(counts,1)[:,None]*.5
        movement=budget()
        if step%50==0 or step==options['iterations']-1:
            history.append({'step':step+1,'max_displacement_cm':movement,'max_gap_cm':float(np.linalg.norm(q[sa]-q[sb],axis=1).max())})
    # Stop seam attraction before final strain relaxation. A residual gap may
    # remain; it is input for Cloth, not a sewing qualification or forced weld.
    for _ in range(options['settle_iterations']):lengths_step();budget()
    return q.tolist(),{'status':'MOUNTED_NOT_SIMULATED','source_ref':options['source_ref'],
        'moving_pieces':options['moving_pieces'],'seam_ids':options['seam_ids'],'source_indices':sorted(moving),
        'max_displacement_cm':budget(),'max_gap_cm':float(np.linalg.norm(q[sa]-q[sb],axis=1).max()),
        'history':history,'simulation':'NOT_EXECUTED','accepted':False}


def mount_panels(obj,payload,recipe):
    from blender.sewing import commit_positions,preflight
    start=[list(p) for p in payload['placed_cm']]
    try:
        coords,report=mount_candidate(payload,recipe);payload['panel_mount']=report
        commit_positions(obj,coords);context,_,_=preflight(obj,payload,recipe)
        payload['placed_cm']=coords;report['context']=context
        return context
    except Exception:
        commit_positions(obj,start)
        raise
