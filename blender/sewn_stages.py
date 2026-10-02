"""Checkpointed assembly continuation and separate collider fitting entry."""
import copy
import uuid
from a3d.core import StudioError,atomic_json,digest,inside,read_json,sha
from a3d.sewn_continuity import transfer_coordinates
from a3d.sewing import distance,mesh_quality
from blender.sewing import (managed_inputs,preflight,context_colliders,mesh_digest,
    mesh_recipe_digest,object_mesh,make_object,commit_positions,trial_binding,structural_inputs)


def snapshot_ref(project,path):
    return {'path':path.relative_to(project.root).as_posix(),'sha256':sha(path)}


def stage_receipt(project,obj,payload,allow_completed=False):
    path=inside(project.root,obj.get('a3d_sewn_stage_receipt',''))
    if not path.is_file() or sha(path)!=obj.get('a3d_sewn_stage_receipt_sha256'):
        raise StudioError('Missing or changed sewn stage receipt')
    value=read_json(path)
    mesh_matches=value.get('mesh_sha256')==mesh_digest(obj)
    if not mesh_matches and allow_completed:
        result=inside(project.root,obj.get('a3d_sewn_stage_result',''))
        if result.is_file() and sha(result)==obj.get('a3d_sewn_stage_result_sha256'):
            full=read_json(result)
            mesh_matches=(full.get('simulation')=='PASS' and full.get('scope')=='full'
                and full.get('recipe_sha256')==value.get('recipe_sha256')
                and full.get('result_mesh_sha256')==mesh_digest(obj)
                and full.get('boundary_map_sha256')==obj['a3d_sewing_mesh_sha256'])
    if value.get('component_id')!=payload['component_id'] or value.get('package_sha256')!=payload['package_sha256'] or value.get('map_sha256')!=obj['a3d_sewing_mesh_sha256'] or not mesh_matches:
        raise StudioError('Sewn stage receipt does not bind the current geometry/package/map')
    return value,snapshot_ref(project,path)


def save_copy(project,session,old,payload,recipe,record):
    """The original rest, topology, source edges, seams and weights remain intact."""
    import bpy
    immutable=digest({k:payload[k] for k in ('rest_cm','faces','panels','seams','pins')})
    payload['recipe_mesh_sha256']=mesh_recipe_digest(recipe)
    obj=make_object(payload,'A3D.'+payload['component_id'])
    obj['a3d_component_id']=payload['component_id'];obj['a3d_package_sha256']=payload['package_sha256']
    path=project.data/('blender/sewing-mesh-'+uuid.uuid4().hex+'.json');atomic_json(path,payload)
    obj['a3d_sewing_mesh']=path.relative_to(project.root).as_posix();obj['a3d_sewing_mesh_sha256']=sha(path)
    record.update(component_id=payload['component_id'],package_sha256=payload['package_sha256'],
        recipe=copy.deepcopy(recipe),recipe_sha256=digest(recipe),map_sha256=sha(path),
        immutable_geometry_sha256=immutable,mesh_sha256=mesh_digest(obj),units='cm',
        checkpoint=project.state()['pending_blender_operation']['checkpoint'],object=obj.name,
        simulation='NOT_EXECUTED',visual_validation='NOT_EXECUTED',accepted=False)
    receipt_path=project.data/('blender/sewing/stage-'+uuid.uuid4().hex+'.json');atomic_json(receipt_path,record)
    obj['a3d_sewn_stage_receipt']=receipt_path.relative_to(project.root).as_posix()
    obj['a3d_sewn_stage_receipt_sha256']=sha(receipt_path)
    from a3d.garment_receipts import write_receipt
    garment=write_receipt(project,payload['component_id'],payload['package_sha256'],{
        'operation':record['operation'],'object':obj.name,'checkpoint':record['checkpoint'],
        'derived_mesh':obj['a3d_sewing_mesh'],'derived_mesh_sha256':sha(path),
        'stage_receipt':snapshot_ref(project,receipt_path),'simulation':'NOT_EXECUTED','visual_validation':'NOT_EXECUTED'})
    obj['a3d_garment_receipt']=garment['path'];obj['a3d_garment_receipt_sha256']=garment['sha256']
    old['a3d_source_component_id']=payload['component_id'];del old['a3d_component_id']
    old['a3d_role']='archived-simulation';old.hide_set(True);old.hide_render=True
    bpy.ops.wm.save_as_mainfile(filepath=session['working'],check_existing=False)
    return {**record,'receipt':snapshot_ref(project,receipt_path),'garment_receipt':garment,'derived_mesh':obj['a3d_sewing_mesh']}


def apply_sewn_result(project_root,component_id,recipe_path,result_path,result_sha256):
    from blender.operations import working
    project,session=working(project_root)
    obj,payload,recipe=managed_inputs(project,component_id,recipe_path)
    path=inside(project.root,result_path)
    if sha(path)!=result_sha256:raise StudioError('Sewing result identity changed')
    report=read_json(path);context,_,_=preflight(obj,payload,recipe)
    if report.get('component_id')!=component_id or report.get('package_sha256')!=payload['package_sha256'] or report.get('recipe_sha256')!=digest(recipe):
        raise StudioError('Sewing result package/component/recipe binding changed')
    if report.get('phase') not in recipe['phases'] or report.get('binding')!=trial_binding(obj,payload,recipe,report['phase'],context):
        raise StudioError('Sewing result trial binding is stale')
    current=copy.deepcopy(payload);current['placed_cm']=[[x*100 for x in p] for p in object_mesh(obj)[0]]
    coords,indices=transfer_coordinates(current,recipe,report)
    payload=copy.deepcopy(payload);payload['placed_cm']=coords
    from a3d.garment_rejections import seam_directions
    record={'operation':'apply_sewn_result','stage':'assembly','phase':report['phase'],
        'source_result':snapshot_ref(project,path),'transferred_source_indices':indices,
        'qualification':'PARTIAL_ASSEMBLY','full_preflight':'NOT_EXECUTED',
        'directions':seam_directions(payload,coords),
        'resume_local_recipe_sha256':digest(recipe)}
    return save_copy(project,session,obj,payload,recipe,record)


def assembly_resume(project,obj,payload,recipe,phase):
    if not obj.get('a3d_sewn_stage_receipt'):return False
    value,_=stage_receipt(project,obj,payload)
    if value['stage']!='assembly' or value.get('phase')!=phase or value.get('resume_local_recipe_sha256')!=digest(recipe):return False
    source=value['source_result'];path=inside(project.root,source['path'])
    if sha(path)!=source['sha256']:raise StudioError('Assembly source result changed')
    return read_json(path).get('simulation')=='PASS'


def prepare_sewn_stage(project_root,component_id,recipe_path,stage):
    import bpy
    from mathutils import Vector
    from blender.operations import working
    project,session=working(project_root)
    obj,payload,recipe=managed_inputs(project,component_id,recipe_path,check_placement=False)
    previous,previous_ref=stage_receipt(project,obj,payload,allow_completed=True)
    structural_inputs(obj,payload,previous['recipe'])
    for key in ('mesh','placements','seams','pins'):
        if previous['recipe'][key]!=recipe[key]:raise StudioError('Stage transition cannot change the approved derived rest, source placement, seams or pins')
    source=previous.get('source_result')
    if stage=='fitting':
        if not any(c['role']=='mannequin' for c in recipe['colliders']):raise StudioError('Fitting entry requires an identified mannequin')
        result=inside(project.root,obj.get('a3d_sewn_stage_result',''))
        if not result.is_file() or sha(result)!=obj.get('a3d_sewn_stage_result_sha256'):raise StudioError('Fitting entry requires an immutable full assembly result')
        full=read_json(result)
        if full.get('purpose')!='assembly' or full.get('scope')!='full' or full.get('simulation')!='PASS' or full.get('result_mesh_sha256')!=mesh_digest(obj) or full.get('boundary_map_sha256')!=obj['a3d_sewing_mesh_sha256']:
            raise StudioError('Fitting cannot reuse an incomplete or changed full assembly')
        source=snapshot_ref(project,result)
    elif previous['stage']!='assembly':raise StudioError('Assembly entry cannot discard a fitting stage')
    # Pose/geometry/thickness are checked before attempting bounded contact repair.
    _,trees,snapshots=context_colliders(recipe)
    before=[[x*100 for x in p] for p in object_mesh(obj)[0]]
    candidate=copy.deepcopy(payload);candidate['placed_cm']=copy.deepcopy(before)
    candidate['recipe_mesh_sha256']=mesh_recipe_digest(recipe)
    temporary=make_object(candidate,'A3D.StageCandidate.'+uuid.uuid4().hex[:8])
    record={'operation':'prepare_sewn_stage','stage':stage,'source_stage':previous_ref,
        'source_result':source,'colliders':snapshots,'phase':previous.get('phase'),
        'resume_local_recipe_sha256':None,'contact_recovery':None}
    try:
        if recipe.get('panel_mount'):
            if stage!='assembly':raise StudioError('Scoped panel mount belongs to free assembly')
            from blender.panel_mount import mount_panels
            mount_panels(temporary,candidate,recipe)
            record['panel_mount']=candidate['panel_mount']
        if recipe.get('interface_preparation'):
            if stage!='assembly':raise StudioError('Local interface preparation belongs to free assembly')
            from blender.interfaces import prepare_interfaces
            prepare_interfaces(temporary,candidate,recipe)
            record['interface_preparation']=candidate['interface_preparation']
        if stage=='assembly' and recipe.get('experimental_prefit'):
            from blender.prefit import apply_prefit
            apply_prefit(temporary,candidate,recipe,trees)
            record['experimental_prefit']=candidate['experimental_prefit']
        try:context,_,_=preflight(temporary,candidate,recipe)
        except StudioError as initial:
            record['initial_error']=str(initial);record['initial_contacts']=getattr(initial,'initial_contacts',[])
            recovery=recipe.get('contact_recovery')
            if stage!='fitting' or not recovery or not record['initial_contacts']:raise
            coords=copy.deepcopy(before)
            for attempt in range(recovery['max_passes']):
                for i,value in enumerate(coords):
                    if payload['pins'].get(str(i),0.)>=1.:continue
                    p=Vector([x/100 for x in value])
                    for tree in trees:
                        hit,normal,_,_=tree.find_nearest(p)
                        if hit is not None and (p-hit).dot(normal)*100<recovery['clearance_cm']:
                            p=hit+normal*(recovery['clearance_cm']/100)
                    coords[i]=[x*100 for x in p]
                movement=max(distance(a,b) for a,b in zip(before,coords,strict=True))
                if movement>recovery['max_displacement_cm']:raise StudioError('Contact recovery exceeded its declared displacement budget')
                commit_positions(temporary,coords)
                try:context,_,_=preflight(temporary,candidate,recipe)
                except StudioError as error:
                    if getattr(error,'initial_contacts',[]) and attempt+1<recovery['max_passes']:continue
                    raise
                candidate['placed_cm']=coords
                record['contact_recovery']={**recovery,'max_displacement_cm_measured':movement,'quality':context['quality']}
                break
        candidate['placed_cm']=[[x*100 for x in p] for p in object_mesh(temporary)[0]]
        if stage=='fitting':
            from blender.fitting import recipe_fit
            record['fitting']=recipe_fit(project,temporary,candidate,recipe)
        record['context']=context
    except StudioError as exc:
        from a3d.garment_rejections import save_rejection
        candidate['stage_transition']=record
        data=read_json(inside(project.root,payload['source_garment']))
        ref=save_rejection(project,data,recipe,candidate,exc,project.state()['pending_blender_operation']['checkpoint'])
        exc.garment_diagnostic=ref
        raise
    finally:
        bpy.data.objects.remove(temporary,do_unlink=True)
    return save_copy(project,session,obj,candidate,recipe,record)
