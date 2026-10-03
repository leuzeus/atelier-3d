"""Source-bound continuous common-pose field; unchanged rest, pins and topology."""
import heapq,math,uuid
from a3d.core import StudioError,atomic_json,digest,inside,read_json,sha
from a3d.fitting_preparation import pose_spec

def basis(origin,axis,transverse):
    import numpy as np
    a=np.array(axis)-origin;t=np.array(transverse)-origin;length=float(np.linalg.norm(a))
    if length<1e-6:raise StudioError('Common pose axis is collapsed')
    a/=length;t-=a*float(t@a)
    if np.linalg.norm(t)<1e-6:raise StudioError('Common pose transverse frame is collinear')
    t/=np.linalg.norm(t)
    return np.stack((a,t,np.cross(a,t)),axis=1),length

def pose_field(payload,spec,body,recipe):
    import numpy as np
    from a3d.sewing import mesh_quality,active_sewing_pairs,distance
    start=np.array(payload['placed_cm'],dtype=float);delta=np.zeros_like(start);sum_weight=np.zeros(len(start));reports=[]
    graph=[{} for _ in start]
    for face in payload['faces']:
        for a,b in zip(face,face[1:]+face[:1]):graph[a][b]=graph[b][a]=distance(start[a],start[b])
    for a,b in active_sewing_pairs(payload):graph[a][b]=graph[b][a]=distance(start[a],start[b])
    def edge_center(edges):
        ids=set()
        for ref in edges:
            if ref['piece'] not in payload['panels'] or ref['edge'] not in payload['panels'][ref['piece']]['edges']:
                raise StudioError('Common pose frame must use existing named source edges')
            ids.update(payload['panels'][ref['piece']]['edges'][ref['edge']])
        return np.mean(start[sorted(ids)],axis=0)
    moving=set();frame_edges=[]
    for frame in spec['frames']:
        if not set(frame['moving_pieces'])<=payload['panels'].keys():raise StudioError('Common pose moving panels must exist')
        seed={i for pid in frame['moving_pieces'] for i in payload['panels'][pid]['indices']}
        if seed & moving:raise StudioError('Common pose moving panels must be disjoint')
        moving|=seed
        origin=edge_center(frame['origin_edges']);axis=edge_center(frame['axis_edges']);transverse=edge_center(frame['transverse_edges'])
        frame_edges.append((frame,origin,axis,transverse))
        def target(ref):return np.array(body['bones'][ref['rig']][ref['bone']][ref['endpoint']],dtype=float)
        target_origin=target(frame['target_origin']);target_axis=target(frame['target_axis'])
        target_transverse=target_origin+np.array(frame['target_transverse_cm'])
        source_basis,source_length=basis(origin,axis,transverse);target_basis,target_length=basis(target_origin,target_axis,target_transverse)
        if abs(source_length-target_length)>frame['max_axis_length_difference_cm']:
            raise StudioError('Common pose axis lengths differ beyond the declared correspondence tolerance; no scaling is allowed')
        rotation=target_basis@source_basis.T;translation=target_origin-rotation@origin
        distances=[math.inf]*len(start);queue=[]
        for i in seed:distances[i]=0.;heapq.heappush(queue,(0.,i))
        while queue:
            d,i=heapq.heappop(queue)
            if d!=distances[i] or d>=frame['feather_cm']:continue
            for j,length in graph[i].items():
                nd=d+length
                if nd<distances[j]:distances[j]=nd;heapq.heappush(queue,(nd,j))
        weight=np.array([max(0.,1-d/frame['feather_cm']) for d in distances]);weight=weight*weight*(3-2*weight)
        for key,value in payload['pins'].items():
            if value>=1:weight[int(key)]=0.
        delta+=(start@rotation.T+translation-start)*weight[:,None];sum_weight+=weight
        reports.append({'id':frame['id'],'source_origin_cm':origin.tolist(),'source_axis_cm':axis.tolist(),
            'source_transverse_cm':transverse.tolist(),'target_origin_cm':target_origin.tolist(),'target_axis_cm':target_axis.tolist(),
            'target_transverse_cm':target_transverse.tolist(),'source_axis_length_cm':source_length,'target_axis_length_cm':target_length,
            'rotation':rotation.tolist(),'translation_cm':translation.tolist(),'weight_sha256':digest(weight.tolist()),
            'source_ref':frame['source_ref'],'correspondence':'DECLARED_MEASURED_EDGES_AND_BONES_NOT_ANATOMICAL_ACCEPTANCE'})
    delta/=np.maximum(1.,sum_weight)[:,None];movement=float(np.linalg.norm(delta,axis=1).max())
    if not np.isfinite(delta).all() or movement>min(spec['max_displacement_cm'],recipe['limits']['max_displacement_cm']):
        raise StudioError('Common pose field exceeded its finite displacement budget')
    initial=max((distance(start[a],start[b]) for a,b in active_sewing_pairs(payload)),default=0.)
    quality=None;relaxation=spec.get('strain_relaxation');history=[]
    edges=sorted({tuple(sorted((a,b))) for face in payload['faces'] for a,b in zip(face,face[1:]+face[:1])})
    aa=np.array([a for a,b in edges]);bb=np.array([b for a,b in edges]);rest=np.array(payload['rest_cm'])
    lengths=np.linalg.norm(rest[bb]-rest[aa],axis=1);degree=np.bincount(np.concatenate([aa,bb]),minlength=len(start))
    movable=np.ones(len(start))
    pairs=active_sewing_pairs(payload)
    pair_a=np.array([a for a,b in pairs],dtype=int);pair_b=np.array([b for a,b in pairs],dtype=int)
    gap_limit=max(initial,recipe['limits']['max_seam_gap_cm'])
    for key,value in payload['pins'].items():
        if value>=1:movable[int(key)]=0.
    for step in range(1,spec['steps']+1):
        q=start+delta*(step/spec['steps'])
        if relaxation:
            # Project only the existing structural length inequalities. No
            # contact projection, source-rest edit or relaxation of thresholds.
            margin=min(.01,(recipe['mesh']['max_stretch']-recipe['mesh']['min_stretch'])/20)
            lo=recipe['mesh']['min_stretch']+margin;hi=recipe['mesh']['max_stretch']-margin
            for _ in range(relaxation['passes']):
                d=q[bb]-q[aa];actual=np.linalg.norm(d,axis=1);desired=np.clip(actual,lengths*lo,lengths*hi)
                correction=d*(1-desired/np.maximum(actual,1e-12))[:,None]
                changes=np.zeros_like(q);np.add.at(changes,aa,correction);np.add.at(changes,bb,-correction)
                q+=changes/np.maximum(degree,1)[:,None]*movable[:,None]*.8
                if pairs:
                    d=q[pair_b]-q[pair_a];actual=np.linalg.norm(d,axis=1)
                    desired=np.minimum(actual,max(0.,gap_limit-min(.01,gap_limit/10)))
                    total=movable[pair_a]+movable[pair_b]
                    correction=d*(1-desired/np.maximum(actual,1e-12))[:,None]/np.maximum(total,1)[:,None]
                    changes=np.zeros_like(q);counts=np.zeros(len(q))
                    np.add.at(changes,pair_a,correction*movable[pair_a,None]);np.add.at(changes,pair_b,-correction*movable[pair_b,None])
                    np.add.at(counts,pair_a,1);np.add.at(counts,pair_b,1)
                    q+=changes/np.maximum(counts,1)[:,None]*.8
        excursion=float(np.linalg.norm(q-start,axis=1).max())
        if not np.isfinite(q).all() or excursion>min(spec['max_displacement_cm'],recipe['limits']['max_displacement_cm']):
            raise StudioError('Common pose relaxation exceeded the displacement budget')
        quality=mesh_quality(payload['rest_cm'],q.tolist(),payload['faces'],recipe['mesh'])
        gap=max((distance(q[a],q[b]) for a,b in active_sewing_pairs(payload)),default=0.)
        if gap>max(initial,recipe['limits']['max_seam_gap_cm'])+1e-6:
            raise StudioError('Common pose field separates permanent seam partners')
        history.append({'step':step,'max_displacement_cm':excursion,'min_stretch':quality['min_stretch'],'max_stretch':quality['max_stretch'],'seam_gap_cm':gap})
    if relaxation:
        for (frame,origin,axis,transverse),row in zip(frame_edges,reports,strict=True):
            residual=[]
            for name,old in [('origin_edges',origin),('axis_edges',axis),('transverse_edges',transverse)]:
                ids=sorted({i for ref in frame[name] for i in payload['panels'][ref['piece']]['edges'][ref['edge']]})
                expected=old@np.array(row['rotation']).T+row['translation_cm']
                residual.append(float(np.linalg.norm(np.mean(q[ids],axis=0)-expected)))
            row['relaxed_frame_residual_cm']=max(residual)
            if max(residual)>relaxation['max_frame_residual_cm']:
                raise StudioError('Common pose relaxation no longer respects its declared frame')
    for key,value in payload['pins'].items():
        if value>=1 and np.linalg.norm(q[int(key)]-start[int(key)])>1e-8:raise StudioError('Common pose would move a fixed pin')
    return q.tolist(),{'frames':reports,'steps':spec['steps'],'history':history,'strain_relaxation':relaxation,
        'max_displacement_cm':float(np.linalg.norm(q-start,axis=1).max()),'quality':quality,
        'seam_gap_cm':gap,'scaling':'NOT_APPLIED','surface_projection':'NOT_APPLIED','fixed_pins':'PRESERVED',
        'closure_welding':'NOT_APPLIED','simulation':'NOT_EXECUTED','accepted':False,'anatomical_fit':'NOT_QUALIFIED'}

def prepare_fitting_pose(project_root,component_id,recipe_path,pose_path):
    from blender.operations import working
    from blender.sewing import managed_inputs,object_mesh,mesh_digest,structural_inputs
    project,_=working(project_root);obj,payload,recipe=managed_inputs(project,component_id,recipe_path,check_placement=False)
    structural_inputs(obj,payload,recipe);spec,body=pose_spec(project,pose_path)
    if spec['component_id']!=component_id:raise StudioError('Common pose component mismatch')
    payload={**payload,'placed_cm':[[x*100 for x in p] for p in object_mesh(obj)[0]]}
    coords,report=pose_field(payload,spec,body,recipe)
    token=uuid.uuid4().hex;path=project.data/('blender/fitting-pose-'+token+'.json')
    record={**report,'version':1,'component_id':component_id,'body_receipt':spec['body_receipt'],
        'target_object':body['reference_object'],'target_geometry_sha256':body['geometry_sha256'],
        'source_mesh_sha256':mesh_digest(obj),'boundary_map_sha256':obj['a3d_sewing_mesh_sha256'],
        'source_spec_sha256':sha(inside(project.root,pose_path)),
        'structural_recipe_sha256':digest({k:recipe[k] for k in ('mesh','placements','seams','pins')}),
        'positions_cm':coords,'status':'COMMON_POSE_FIELD_PREPARED_NOT_APPLIED'}
    atomic_json(path,record)
    return {**{k:v for k,v in record.items() if k!='positions_cm'},'artifact':{'path':path.relative_to(project.root).as_posix(),'sha256':sha(path)}}

def apply_pose(project,obj,payload,recipe,source_mesh_sha256):
    import bpy
    from blender.sewing import mesh_digest,commit_positions
    ref=recipe['fitting_pose'];path=inside(project.root,ref['path'])
    if sha(path)!=ref['sha256']:raise StudioError('Prepared common pose field changed')
    from a3d.fitting_preparation import body_receipt
    record=read_json(path);body,_=body_receipt(project,record['body_receipt'])
    if record.get('version')!=1 or record.get('component_id')!=payload['component_id'] or record.get('status')!='COMMON_POSE_FIELD_PREPARED_NOT_APPLIED':
        raise StudioError('Prepared common pose identity/status is invalid')
    target=bpy.data.objects.get(record['target_object']);plan_ref=recipe.get('fitting_plan')
    if not plan_ref or sha(inside(project.root,plan_ref['path']))!=plan_ref['sha256']:raise StudioError('Common pose needs an unchanged fitting plan')
    plan=read_json(inside(project.root,plan_ref['path']))
    if plan.get('body')!={'object':record['target_object'],'geometry_sha256':record['target_geometry_sha256'],'role':'target'}:
        raise StudioError('Common pose requires its actual target body, never a proxy')
    if target is None or mesh_digest(target,True)!=body['geometry_sha256'] or body['geometry_sha256']!=record['target_geometry_sha256']:
        raise StudioError('Common pose target geometry/pose changed')
    if abs(bpy.context.scene.unit_settings.scale_length-1)>1e-8 or any(abs(s-1)>1e-6 for s in target.scale):
        raise StudioError('Common pose requires meters and applied body scale')
    if (source_mesh_sha256!=record['source_mesh_sha256'] or obj.get('a3d_sewing_mesh_sha256')!=record['boundary_map_sha256'] or
        digest({k:recipe[k] for k in ('mesh','placements','seams','pins')})!=record['structural_recipe_sha256']):
        raise StudioError('Common pose source geometry, boundary map or structural recipe changed')
    coords=record['positions_cm'];start=payload['placed_cm']
    if len(coords)!=len(start) or any(not math.isfinite(x) for p in coords for x in p):raise StudioError('Invalid prepared common pose coordinates')
    if max(math.dist(a,b) for a,b in zip(coords,start,strict=True))>recipe['limits']['max_displacement_cm']:raise StudioError('Common pose displacement exceeds recipe')
    for key,value in payload['pins'].items():
        if value>=1 and math.dist(start[int(key)],coords[int(key)])>1e-6:raise StudioError('Common pose would move a fixed pin')
    commit_positions(obj,coords);payload['placed_cm']=coords
    return {k:v for k,v in {**record,'status':'PLACED_NOT_SIMULATED','artifact':ref}.items() if k!='positions_cm'}
