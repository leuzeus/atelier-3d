"""Explicit rigid landmark placement; no surface projection or scaling."""
import numpy as np
from a3d.core import StudioError,inside,read_json,sha


def rigid_frame(source,target,tolerance):
    a=np.array(source,dtype=float);b=np.array(target,dtype=float)
    if not np.isfinite(a).all() or not np.isfinite(b).all():raise StudioError('Fitting landmark coordinates must be finite')
    ac=a-a.mean(axis=0);bc=b-b.mean(axis=0)
    if min(np.linalg.svd(ac,compute_uv=False)[1],np.linalg.svd(bc,compute_uv=False)[1])<1e-6:
        raise StudioError('Fitting landmarks are collinear or collapsed')
    u,_,vt=np.linalg.svd(ac.T@bc)
    correction=np.eye(3);correction[2,2]=-1 if np.linalg.det(u@vt)<0 else 1
    rotation=u@correction@vt;translation=b.mean(axis=0)-a.mean(axis=0)@rotation
    residual=float(np.linalg.norm(a@rotation+translation-b,axis=1).max())
    if residual>tolerance:raise StudioError('Fitting landmark frame is incompatible without deformation or scaling')
    return rotation,translation,residual


def place_for_fitting(project,obj,payload,recipe):
    import bpy
    from blender.sewing import object_mesh,mesh_digest,commit_positions
    ref=recipe.get('fitting_plan')
    if not ref or sha(inside(project.root,ref['path']))!=ref['sha256']:
        raise StudioError('Explicit fitting placement requires an unchanged measurement plan')
    plan=read_json(inside(project.root,ref['path']));body_ref=plan.get('body',{})
    if body_ref.get('role')!='target':raise StudioError('Explicit fitting placement requires an identified target body, not a proxy')
    body=bpy.data.objects.get(body_ref.get('object',''))
    if body is None or body.type!='MESH' or mesh_digest(body,True)!=body_ref['geometry_sha256']:
        raise StudioError('Fitting target geometry/pose changed')
    if any(abs(s-1)>1e-6 for s in body.scale):raise StudioError('Fitting target scale must be applied')
    body_vertices=[[x*100 for x in p] for p in object_mesh(body,True)[0]]
    start=np.array(payload['placed_cm'],dtype=float);q=start.copy();reports=[]
    options=recipe['fitting_placement']
    for group in options['groups']:
        indices=sorted({i for pid in group['pieces'] for i in payload['panels'][pid]['indices']})
        source_indices=group['source_indices'];target_indices=group['target_indices']
        if not set(source_indices)<=set(indices) or max(target_indices)>=len(body_vertices):
            raise StudioError('Fitting landmark index is outside its source group or body')
        rotation,translation,residual=rigid_frame(start[source_indices],[body_vertices[i] for i in target_indices],group['tolerance_cm'])
        q[indices]=start[indices]@rotation+translation
        for index in indices:
            if payload['pins'].get(str(index),0)>=1 and np.linalg.norm(q[index]-start[index])>1e-6:
                raise StudioError('Explicit fitting placement would move a fixed pin')
        reports.append({'pieces':group['pieces'],'labels':group['labels'],'source_indices':source_indices,
            'target_indices':target_indices,'rotation':rotation.tolist(),'translation_cm':translation.tolist(),
            'landmark_residual_cm':residual,'source_ref':group['source_ref']})
    movement=float(np.linalg.norm(q-start,axis=1).max())
    if not np.isfinite(q).all() or movement>options['max_displacement_cm']:
        raise StudioError('Explicit fitting placement exceeded its finite displacement budget')
    commit_positions(obj,q.tolist());payload['placed_cm']=q.tolist()
    return {'groups':reports,'max_displacement_cm':movement,'status':'PLACED_NOT_SIMULATED',
        'simulation':'NOT_EXECUTED','accepted':False,'scaling':'NOT_APPLIED','surface_projection':'NOT_APPLIED'}
