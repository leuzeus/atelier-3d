"""Native resumable pattern assembly; geometry is never a fitting approval.

Every mutation is dispatched through the existing checkpoint protocol. Source
patterns and former objects remain immutable; each stage owns a new map/receipt.
"""
import copy
import uuid

from a3d.core import StudioError,atomic_json,digest,inside,read_json,sha
from blender.sewing import (managed_inputs,structural_inputs,make_object,object_mesh,
    mesh_digest,mesh_recipe_digest,context_colliders,preflight,commit_positions,
    simulate_object,simulation_quality)

STAGES=('preposition','mount','close','consolidate','relax','drape')
LEGACY_PREPARATIONS=('experimental_prefit','panel_mount','interface_preparation',
                     'fitting_pose','fitting_placement','contact_recovery')


def require_prepared_native_preform(plan,preparation):
    """Native Bend enters assembly only through its exact READY preparation."""
    if (any('native_bend' in frame for frame in plan['preform']['panels'].values())
            and (not preparation or preparation[0].get('readiness')!='READY')):
        error=StudioError('Native Bend assembly requires its exact READY preparation; run prepare_pattern_assembly before preposition')
        error.reason_category='placement_enfilage'
        raise error


def reference(project,path):
    return {'path':path.relative_to(project.root).as_posix(),'sha256':sha(path)}


def verified_reference(project,ref):
    path=inside(project.root,ref['path'])
    if not path.is_file() or sha(path)!=ref['sha256']:
        raise StudioError('Pattern assembly referenced artifact changed: '+ref['path'])
    return path


def current_receipt(project,obj,payload,recipe,plan_ref):
    path=obj.get('a3d_pattern_assembly_receipt')
    if not path:return None
    ref={'path':path,'sha256':obj.get('a3d_pattern_assembly_receipt_sha256')}
    record=read_json(verified_reference(project,ref))
    checks=(record.get('component_id')==payload['component_id'],
        record.get('package_sha256')==payload['package_sha256'],
        record.get('recipe_sha256')==digest(recipe),record.get('plan')==plan_ref,
        record.get('derived_mesh',{}).get('sha256')==obj['a3d_sewing_mesh_sha256'],
        record.get('mesh_sha256')==mesh_digest(obj),record.get('accepted') is False)
    if not all(checks):raise StudioError('Pattern assembly stage binding is stale; resume its exact checkpoint and plan')
    verified_reference(project,record['derived_mesh'])
    if record.get('previous'):verified_reference(project,record['previous'])
    return record,ref


def nearest_signed_distance_cm(point,hit,normal):
    """Surface distance signed by orientation, including exterior edge points.

The normal projection alone is zero for a point outside a face's boundary in
that face's plane. Its nonzero nearest-surface distance is real clearance.
This remains a nearest-normal sample, not an exhaustive inside/outside proof.
"""
    delta=[point[k]-hit[k] for k in range(3)]
    length=sum(x*x for x in delta)**.5*100
    projected=sum(delta[k]*normal[k] for k in range(3))
    return -length if projected < -1e-10 else length


def collision_check(coords,trees,snapshots,clearance,*,surface_triangles=None):
    """Signed nearest distance with ray classification for uncertain normals.

    At an edge/corner, the nearest face normal can be tangent to the actual
    nearest-point vector. Float32 noise must not turn that exterior clearance
    into a deep penetration. The numerical band only selects a classifier;
    it never changes the measured distance or the required collision reserve.
    """
    from mathutils import Vector
    import math
    directions=[Vector(v).normalized() for v in ((1.,.371,.529),(-.419,1.,.237),(.193,-.613,1.))]
    def parity(point,tree,step):
        votes=[]
        for direction in directions:
            start=point.copy();count=0;previous_face=None
            for _ in range(256):
                hit,normal,face,distance=tree.ray_cast(start,direction)
                if hit is None:
                    votes.append(bool(count%2));break
                if (not math.isfinite(distance) or abs(normal.dot(direction))<1e-6
                        or face==previous_face):
                    votes.append(None);break
                count+=1;previous_face=face
                start=hit+direction*step
            else:votes.append(None)
        # No majority silently resolves an ambiguous collision boundary.
        return (votes[0] if None not in votes and len(set(votes))==1 else None),votes
    minimum=None;worst=None;uncertain=[];classifications=0;surface_witnesses=0
    if surface_triangles is not None and len(surface_triangles)!=len(trees):
        raise StudioError('Precise boundary surfaces must match collision trees')
    for i,p in enumerate(coords):
        point=Vector([v/100 for v in p])
        for body_index,(tree,snapshot) in enumerate(zip(trees,snapshots,strict=True)):
            hit,normal,face,_=tree.find_nearest(point)
            if hit is None:continue
            delta=point-hit;distance=delta.length*100;projected=delta.dot(normal)
            scale=max(*(abs(v) for v in point),*(abs(v) for v in hit),
                      *(v/100 for v in snapshot.get('dimensions_cm',[])),1e-12)
            numerical_band_m=8*(2**-23)*scale
            classification='NEAREST_NORMAL'
            signed=-distance if projected<0 else distance
            boundary=False
            if surface_triangles is not None and distance<=numerical_band_m*100:
                # Float32 BVH proximity can leave a tangential residual for a
                # point exactly on a face. Resolve only a float64 on-triangle
                # witness; the wider native sign band is not a contact margin.
                from a3d.contact_geometry import closest_point_triangle
                triangle=surface_triangles[body_index][face]
                exact_distance=math.dist(p,closest_point_triangle(p,triangle))
                epsilon=max(1e-10,max(math.dist(triangle[j],triangle[(j+1)%3]) for j in range(3))*1e-10)
                if exact_distance<=epsilon:
                    boundary=True;signed=0.;classification='FLOAT64_ON_SURFACE_WITNESS'
                    surface_witnesses+=1
            if not boundary and distance>0 and abs(projected)<=numerical_band_m:
                inside,votes=parity(point,tree,numerical_band_m)
                classifications+=1;classification='UNANIMOUS_THREE_RAY_PARITY'
                if inside is None:
                    uncertain.append({'sample':i,'collider':snapshot['object'],'face':face,
                        'ray_inside_votes':votes,'nearest_distance_cm':distance,
                        'numerical_sign_band_cm':numerical_band_m*100})
                    classification='AMBIGUOUS_REFUSED'
                else:signed=-distance if inside else distance
            if minimum is None or signed<minimum:
                minimum=signed;worst={'sample':i,'collider':snapshot['object'],'face':face,
                    'signed_offset_cm':signed,'sign_classification':classification}
    return {'ok':not uncertain and (minimum is None or minimum>=clearance-1e-6),
        'minimum_signed_offset_cm':minimum,'clearance_cm':clearance,'worst':worst,
        'distance_metric':'NEAREST_SURFACE_EUCLIDEAN_NORMAL_SIGN_WITH_UNANIMOUS_RAY_PARITY_FOR_FLOAT32_SIGN_UNCERTAINTY',
        'ray_classified_samples':classifications,'ambiguous_sign_count':len(uncertain),
        'float64_surface_witnesses':surface_witnesses,
        'ambiguous_sign_samples':uncertain[:32],
        'coverage':'VERTEX_AND_TRIANGLE_CENTROID_SAMPLES_PLUS_EDGE_RAYS_NOT_EXHAUSTIVE_INTERSECTION_PROOF'}


def self_contact_report(payload,coords,tolerance):
    """Precise narrow phase after a conservative triangle AABB BVH."""
    from blender.cloth_contacts import precise_self_contacts
    return precise_self_contacts(payload,coords,tolerance)


def collision_guard(payload,trees,snapshots,plan,self_contacts=False):
    import bpy
    from blender.cloth_contacts import build_contact_context,check_contacts
    required=plan['collision']['required'];clearance=plan['collision']['clearance_cm']
    if required and not trees:raise StudioError('Pattern placement requires its declared collision envelope')
    colliders=[]
    for snapshot in snapshots:
        obj=bpy.data.objects.get(snapshot['object'])
        if obj is None:raise StudioError('Precise contact requires the bound evaluated collider: '+snapshot['object'])
        colliders.append(obj)
    context=build_contact_context(payload,colliders,clearance_cm=clearance,
        seam_tolerance_cm=plan['consolidation']['weld_gap_cm'],check_self=self_contacts)
    def check(coords):
        report=check_contacts(context,coords)
        report['edge_crossings']=[]  # legacy field; full triangle contacts are above
        return report
    return check


def require_envelope_review(project,recipe,colliders):
    """A hollow skeleton's auxiliary skin needs source-bound visual evidence."""
    # This is a review of the auxiliary only, never artistic garment acceptance.
    plan_ref=recipe.get('fitting_plan')
    fit_plan=read_json(verified_reference(project,plan_ref)) if plan_ref else {}
    proxies=[o for o in colliders if o.get('a3d_body_geometry_sha256') or o.get('a3d_role')=='auxiliary_collider'
        or (fit_plan.get('envelope',{}).get('object')==o.name and fit_plan['envelope'].get('role')=='proxy')]
    return proxies


def validate_envelope_review(project,plan,recipe,colliders):
    proxies=require_envelope_review(project,recipe,colliders)
    if not proxies:return None
    ref=plan['collision'].get('envelope_review')
    if not ref:raise StudioError('Auxiliary fitting envelope requires source-bound front/side/back/threequarter visual review')
    record=read_json(verified_reference(project,ref))
    if record.get('visual_validation')!='REVIEWED' or not record.get('source_ref') or record.get('collision_use')!='SUITABLE':
        raise StudioError('Auxiliary envelope review must explicitly establish suitability for collision use')
    views=record.get('views')
    if not isinstance(views,dict) or not {'front','side','back','threequarter'}<=set(views):
        raise StudioError('Auxiliary envelope review requires immutable image references for every required view')
    for view in ('front','side','back','threequarter'):
        image_ref=views[view]
        if not isinstance(image_ref,dict) or set(image_ref)!={'path','sha256'}:
            raise StudioError('Auxiliary envelope review has an invalid '+view+' image reference')
        image_path=verified_reference(project,image_ref)
        with image_path.open('rb') as stream:header=stream.read(32)
        png=image_path.suffix.lower()=='.png' and header.startswith(b'\x89PNG\r\n\x1a\n')
        jpeg=image_path.suffix.lower() in ('.jpg','.jpeg') and header.startswith(b'\xff\xd8\xff')
        webp=image_path.suffix.lower()=='.webp' and header.startswith(b'RIFF') and header[8:12]==b'WEBP'
        if len(header)<32 or not (png or jpeg or webp):
            raise StudioError('Auxiliary envelope review must reference actual PNG/JPEG/WebP image evidence')
    identities=record.get('geometry_sha256')
    if len(proxies)!=1 or identities!=mesh_digest(proxies[0],True):
        raise StudioError('Auxiliary envelope visual review belongs to another geometry')
    target=proxies[0].get('a3d_body_geometry_sha256')
    if not target and recipe.get('fitting_plan'):
        fitting=read_json(verified_reference(project,recipe['fitting_plan']))
        target=fitting.get('body',{}).get('geometry_sha256')
    if not target or record.get('target_geometry_sha256')!=target:
        raise StudioError('Auxiliary envelope review must bind the exact target body geometry/pose')
    return ref


def dressing_measurement(project,payload,plan,colliders,selected,source_coords,check_milestones=True):
    from blender.dressing import audit_dressing
    from blender.cloth_contacts import build_contact_context,check_contacts,check_motion
    context=None
    if plan.get('dressing'):
        context=build_contact_context(payload,[o for o in colliders if o.name in selected],
            clearance_cm=plan['collision']['clearance_cm'],seam_tolerance_cm=plan['consolidation']['weld_gap_cm'])
    audit_plan=copy.deepcopy(plan)
    if not check_milestones and audit_plan.get('dressing'):audit_plan['dressing']['milestones']=[]
    result=audit_dressing(payload,payload['placed_cm'],audit_plan,colliders=colliders,project=project.root,
        source_coords_cm=source_coords,
        contact_check=(lambda coords:check_contacts(context,coords)) if context else None,
        motion_check=(lambda a,b,i,j:check_motion(context,a,b,i,j,
            max_step_cm=plan['assembly']['max_step_cm'],max_subdivisions=128)) if context else None)
    if not check_milestones:
        result.update(path_scope='STATIC_RECHECK_CURRENT_DRESSING_ORIGINAL_PLACEMENT_PATH_NOT_REPLAYED',source_plan_sha256=digest(plan))
    return result


def _save_stage(project,session,old,payload,recipe,record,directory):
    import bpy
    from a3d.garment_receipts import write_receipt
    payload['recipe_mesh_sha256']=mesh_recipe_digest(recipe)
    mesh_path=directory/'mesh.json';atomic_json(mesh_path,payload)
    obj=make_object(payload,'A3D.PatternAssembly.'+payload['component_id'])
    obj['a3d_component_id']=payload['component_id'];obj['a3d_package_sha256']=payload['package_sha256']
    obj['a3d_sewing_mesh']=mesh_path.relative_to(project.root).as_posix();obj['a3d_sewing_mesh_sha256']=sha(mesh_path)
    record.update(schema_version=1,operation='transition_pattern_assembly',component_id=payload['component_id'],
        package_sha256=payload['package_sha256'],source_garment_sha256=payload['source_garment_sha256'],
        recipe_sha256=digest(recipe),derived_mesh=reference(project,mesh_path),mesh_sha256=mesh_digest(obj),
        checkpoint=project.state()['pending_blender_operation']['checkpoint'],object=obj.name,
        accepted=False,visual_validation='NOT_EXECUTED',export_eligible=False)
    path=directory/'receipt.json';atomic_json(path,record)
    obj['a3d_pattern_assembly_receipt']=path.relative_to(project.root).as_posix()
    obj['a3d_pattern_assembly_receipt_sha256']=sha(path)
    garment=write_receipt(project,payload['component_id'],payload['package_sha256'],{
        'operation':'transition_pattern_assembly','stage':record['stage'],'object':obj.name,
        'checkpoint':record['checkpoint'],'stage_receipt':reference(project,path),
        'derived_mesh':record['derived_mesh'],'simulation':record['simulation'],
        'visual_validation':'NOT_EXECUTED','accepted':False})
    obj['a3d_garment_receipt']=garment['path'];obj['a3d_garment_receipt_sha256']=garment['sha256']
    old['a3d_source_component_id']=payload['component_id'];del old['a3d_component_id']
    old['a3d_role']='archived-simulation';old.hide_set(True);old.hide_render=True
    bpy.ops.wm.save_as_mainfile(filepath=session['working'],check_existing=False)
    return {**record,'receipt':reference(project,path),'garment_receipt':garment}


def freeze_continuous(project,session,obj,payload,recipe):
    """Create a render copy only from the exact qualified continuous drape.

No synthetic legacy local/full report is written and no second weld occurs.
Behaviour, silhouette and export gates remain independent downstream decisions.
"""
    import bpy
    if recipe.get('physics_purpose') == 'TEST_ONLY':
        raise StudioError('TEST_ONLY physics cannot become a production frozen fitting result')
    from a3d.physics_admission import require_recipe_fit_intent
    fit_admission = require_recipe_fit_intent(project, recipe)
    if recipe['colliders']:
        from blender.physics_admission import require_native_recipe_fit_intent
        colliders, _, _ = context_colliders(recipe)
        fit_admission = require_native_recipe_fit_intent(project, recipe, colliders, payload)
    from blender.fitting import recipe_fit
    ref={'path':obj.get('a3d_pattern_assembly_receipt',''),
         'sha256':obj.get('a3d_pattern_assembly_receipt_sha256')}
    value=read_json(verified_reference(project,ref))
    from a3d.dressing import source_references
    for source in source_references(read_json(verified_reference(project,value['plan']))):verified_reference(project,source)
    record,_=current_receipt(project,obj,payload,recipe,value['plan'])
    if record.get('stage')!='drape' or record.get('simulation')!='PASS' or record.get('qualification')!='FITTING_PHYSICS_ONLY':
        raise StudioError('Continuous freeze requires the exact qualified drape; free assembly, closure and relaxation are insufficient')
    runs=record.get('cloth_runs',[])
    if not runs or any(run.get('simulation')!='PASS' or run.get('executed',{}).get('settings',{}).get('use_sewing_springs') is not False
            or run.get('support_transition',{}).get('temporary_supports_active') is not False for run in runs):
        raise StudioError('Continuous drape must execute without sewing springs or temporary mounting supports')
    if any(run.get('validation_contract',{}).get('version')!=2 for run in runs):
        raise StudioError('Legacy drape evidence covers its original checks only; requalify per-face metrics and motion contacts before freeze')
    dressing=record.get('dressing',{})
    if dressing.get('status')!='READY' or dressing.get('required') is not True or dressing.get('full_coverage') is not True:
        raise StudioError('Continuous fitting requires measured source-bound dressing before freeze')
    fitting=recipe_fit(project,obj,payload,recipe)
    previous=record.get('fitting')
    if not fitting or fitting.get('fit_status')!='CAPACITY_SUFFICIENT' or fitting.get('donning',{}).get('missing') or not isinstance(previous,dict) or fitting.get('fit_binding')!=previous.get('fit_binding'):
        raise StudioError('Continuous fitting evidence is missing, changed or unqualified; requalify before freeze')
    coords,faces=object_mesh(obj)
    simulation_quality(payload,[[x*100 for x in p] for p in coords],recipe['mesh'])
    mesh=bpy.data.meshes.new('A3D.ContinuousSewnSurface');mesh.from_pydata(coords,[],faces);mesh.update()
    result=bpy.data.objects.new('A3D.Sewn.'+payload['component_id'],mesh);bpy.context.scene.collection.objects.link(result)
    result['a3d_component_id']=payload['component_id'];result['a3d_package_sha256']=payload['package_sha256'];result['a3d_role']='render'
    result['a3d_source_simulation']=obj.name
    from blender.piece_inventory import bind_frozen_map
    bind_frozen_map(project, result, payload, faces, coords)
    result['a3d_pattern_assembly_receipt']=ref['path'];result['a3d_pattern_assembly_receipt_sha256']=ref['sha256']
    obj['a3d_source_component_id']=payload['component_id'];del obj['a3d_component_id']
    obj['a3d_role']='archived-simulation';obj.hide_set(True);obj.hide_render=True
    frozen={'operation':'freeze_sewn','component_id':payload['component_id'],'object':result.name,
        'rest_mode':'assembled_3d','vertices_before':len(coords),'vertices_after':len(coords),'explicit_unions':0,
        'consolidation':'ALREADY_VERIFIED_NO_SECOND_WELD','source_drape_receipt':ref,
        'package_sha256':payload['package_sha256'],'source_garment_sha256':payload['source_garment_sha256'],
        'derived_mesh_sha256':obj['a3d_sewing_mesh_sha256'],'fitting_binding':fitting['fit_binding'],
        'preserved_links':[sid for sid,seam in payload['seams'].items() if seam['kind']!='permanent'],
        'simulation':'PASS','qualification':'FITTING_PHYSICS_ONLY','behavior':'NOT_QUALIFIED',
        'fit_intent_admission':fit_admission,
        'visual_validation':'NOT_EXECUTED','accepted':False,'export_eligible':False,
        'checkpoint':project.state()['pending_blender_operation']['checkpoint']}
    path=project.data/('blender/pattern-assembly/frozen-'+uuid.uuid4().hex+'.json');atomic_json(path,frozen)
    bpy.ops.wm.save_as_mainfile(filepath=session['working'],check_existing=False)
    return {**frozen,'receipt':reference(project,path)}


def transition_pattern_assembly(project_root,component_id,recipe_path,plan_path,stage):
    import bpy
    from blender.operations import working
    from a3d.pattern_assembly import (validate_plan,support_weights,
        bounded_close,consolidate,migrate_legacy_receipt)
    from blender.preform import preform_coordinates
    project,session=working(project_root)
    obj,payload,recipe=managed_inputs(project,component_id,recipe_path,check_placement=False)
    if stage in ('mount', 'relax', 'drape'):
        from a3d.physics_admission import require_recipe_fit_intent
        require_recipe_fit_intent(project, recipe)
    from blender.piece_inventory import require_live
    require_live(project, component_id)
    if stage not in ('migrate',)+STAGES:raise StudioError('Unknown pattern assembly stage')
    migration_recipe=None
    if stage=='migrate' and mesh_recipe_digest(recipe)!=payload['recipe_mesh_sha256']:
        from blender.sewn_stages import stage_receipt
        legacy,_=stage_receipt(project,obj,payload,allow_completed=True)
        migration_recipe=legacy.get('recipe')
        if not migration_recipe or any(migration_recipe[k]!=recipe[k] for k in ('mesh','placements','seams','pins')):
            raise StudioError('Legacy migration cannot change source meshing, placement, seams or source pins')
        structural_inputs(obj,payload,migration_recipe)
    else:structural_inputs(obj,payload,recipe)
    path=inside(project.root,plan_path);plan=read_json(path);plan_ref=reference(project,path)
    prior=current_receipt(project,obj,payload,recipe,plan_ref)
    preparation=None
    if not prior and obj.get('a3d_pattern_preparation_receipt'):
        from blender.pattern_preparation import prepared_receipt
        preparation=prepared_receipt(project,obj,payload,recipe,plan_ref)
        if stage!='preposition':raise StudioError('A READY preparation enters pattern assembly through preposition without replacing its geometry')
    if prior:
        previous,previous_ref=prior
        original_ref=previous['source_map'];source=read_json(verified_reference(project,original_ref))
        expected='preposition' if previous['stage']=='migrate' else STAGES[STAGES.index(previous['stage'])+1] if previous['stage']!='drape' else None
        if stage!=expected:raise StudioError('Pattern assembly transitions are sequential and closure is single-use; expected '+str(expected))
    else:
        if stage not in ('migrate','preposition'):raise StudioError('Start pattern assembly with migration or preposition')
        previous=None;previous_ref=None;source=copy.deepcopy(payload)
        original_ref={'path':obj['a3d_sewing_mesh'],'sha256':obj['a3d_sewing_mesh_sha256']}
    plan_validation=validate_plan(source,plan)
    if stage=='preposition':require_prepared_native_preform(plan,preparation)
    if plan['consolidation']['weld_gap_cm']>recipe['limits']['weld_gap_cm']:
        raise StudioError('Assembly consolidation tolerance cannot exceed the unchanged final recipe weld tolerance')
    candidate=copy.deepcopy(payload)
    candidate['placed_cm']=[[x*100 for x in p] for p in object_mesh(obj)[0]]
    candidate['pattern_assembly']={'version':2,'source_map':original_ref,'plan_sha256':plan_ref['sha256'],'stage':stage,
        'contact_policy':{'clearance_cm':plan['collision']['clearance_cm']}}
    declared_colliders,declared_trees,declared_snapshots=context_colliders(recipe)
    fit_admission = None
    if stage in ('mount', 'relax', 'drape'):
        from blender.physics_admission import require_native_recipe_fit_intent
        fit_admission = require_native_recipe_fit_intent(project, recipe, declared_colliders, payload)
    from a3d.dressing import migrate_legacy_layers,layer_collision_selection,source_references
    layer_plan=copy.deepcopy(plan);layer_migration=None
    collider_roles={item['object']:'body' if item['role']=='mannequin' else 'unknown' for item in recipe['colliders']}
    if 'layers' not in layer_plan:
        layer_migration=migrate_legacy_layers(candidate,collider_roles,plan_ref)
        if layer_migration['layers']:layer_plan['layers']=layer_migration['layers']
    for ref in source_references(layer_plan):verified_reference(project,ref)
    layer_selection=layer_collision_selection(candidate,layer_plan,collider_roles)
    if layer_selection['status']!='LAYER_COLLIDERS_SELECTED':
        raise StudioError('Layer collision admission requires clarification: '+layer_selection['reason'])
    selected=set(layer_selection['colliders'])
    selected_context=[(o,t,s) for o,t,s in zip(declared_colliders,declared_trees,declared_snapshots,strict=True) if o.name in selected]
    active_collision=plan['collision'].get('mode','all_stages')!='drape_only' or stage=='drape'
    colliders,trees,snapshots=([list(items) for items in zip(*selected_context)] if selected_context else ([],[],[])) if active_collision else ([],[],[])
    effective_recipe=copy.deepcopy(recipe)
    effective_recipe['colliders']=[item for item in recipe['colliders'] if item['object'] in selected]
    if not active_collision:
        effective_recipe['colliders']=[]
        effective_recipe['no_collision_reason']=plan['collision']['source_ref']
    effective_plan=copy.deepcopy(plan)
    if not active_collision:effective_plan['collision']['required']=False
    if not active_collision:candidate['pattern_assembly']['contact_policy']['clearance_cm']=0.
    directory=project.data/('blender/pattern-assembly/attempt-'+uuid.uuid4().hex);directory.mkdir(parents=True)
    record={'stage':stage,'previous':previous_ref,'source_map':original_ref,'plan':plan_ref,
        'plan_validation':plan_validation,'simulation':'NOT_EXECUTED','qualification':'CONSTRUCTION_ONLY',
        'colliders':snapshots,'declared_colliders':declared_snapshots,'collision_active':active_collision,
        'layer_migration':layer_migration,'layer_selection':layer_selection,
        'legacy_preparations_not_executed':[k for k in LEGACY_PREPARATIONS if recipe.get(k)],
        'fitting':'NOT_QUALIFIED','behavior':'NOT_QUALIFIED','cause':'NOT_ESTABLISHED'}
    if fit_admission is not None:
        record['fit_intent_admission'] = fit_admission
    temporary=None;physics_in_progress=False
    original_settings=(bpy.context.scene.frame_current,bpy.context.scene.frame_start,bpy.context.scene.frame_end,
        bpy.context.scene.render.fps,bpy.context.scene.render.fps_base,list(bpy.context.scene.gravity),bpy.context.scene.use_gravity)
    try:
        check=collision_guard(candidate,trees,snapshots,effective_plan,self_contacts=stage=='close')
        if stage=='migrate':
            legacy={}
            if obj.get('a3d_sewn_stage_receipt'):
                ref={'path':obj['a3d_sewn_stage_receipt'],'sha256':obj['a3d_sewn_stage_receipt_sha256']}
                legacy=read_json(verified_reference(project,ref));record['legacy_receipt']=ref
            record['migration']=migrate_legacy_receipt(legacy)
            if migration_recipe:record['migration']['retired_recipe_sha256']=digest(migration_recipe)
            record['qualification']='MIGRATED_NOT_PHYSICALLY_REQUALIFIED'
        elif stage=='preposition':
            if preparation:
                record['preparation']=preparation[1]
                record['preform']={'status':'CONSUMED_READY_PREPARATION','geometry_reset':False,
                    'prepared_mesh_sha256':preparation[0]['mesh_sha256']}
            else:candidate['placed_cm'],record['preform']=preform_coordinates(source,plan)
            movement=max(sum((a[k]-b[k])**2 for k in range(3))**.5 for a,b in zip(
                [[x*100 for x in p] for p in object_mesh(obj)[0]],candidate['placed_cm'],strict=True))
            if movement>plan['assembly']['max_displacement_cm']:
                error=StudioError('Preform placement exceeded its declared displacement budget')
                error.reason_category='placement_enfilage';raise error
            record['preform']['max_displacement_cm_measured']=movement
            candidate['pins'],record['supports']=support_weights(candidate,plan,'assembly',release=0.)
            record['collision']=check(candidate['placed_cm'])
            if not record['collision']['ok']:raise StudioError('Preform placement/enfilage intersects its collision reserve; no body remodeling or tolerance increase is allowed')
            record['dressing']=dressing_measurement(project,candidate,layer_plan,declared_colliders,selected,source['placed_cm'])
            if record['dressing']['status'] in ('NEEDS_CORRECTION','NEEDS_CLARIFICATION'):
                error=StudioError('Sourced placement/enfilage is not admitted: '+str(record['dressing'].get('reason',record['dressing']['status'])))
                error.reason_category='placement_enfilage';raise error
        elif stage=='close':
            candidate['pins'],record['supports']=support_weights(candidate,plan,'closure',release=plan['assembly']['closure_support_release'])
            candidate['placed_cm'],record['closure']=bounded_close(candidate,candidate['placed_cm'],plan,collision_check=check)
            if record['closure']['status']!='GEOMETRY_READY':
                error=StudioError('Bounded geometric closure refused: '+str(record['closure']))
                error.reason_category=record['closure'].get('reason_category','geometric_closure');raise error
        elif stage=='consolidate':
            candidate,record['consolidation']=consolidate(candidate,candidate['placed_cm'],plan)
            record['collision']=collision_guard(candidate,trees,snapshots,effective_plan,self_contacts=True)(candidate['placed_cm'])
            if not record['collision']['ok']:raise StudioError('Permanent consolidation violates the collision reserve')
            record['qualification']='GEOMETRY_CONSOLIDATED_ONLY'
        else:
            cloth_plan=plan.get('cloth',{})
            phase=cloth_plan.get(stage+'_phase','mount' if stage=='mount' else 'drape')
            if phase not in recipe['phases']:raise StudioError('Unknown declared Cloth phase')
            local_recipe=copy.deepcopy(effective_recipe)
            # Assembly budgets cannot rewrite final tolerances or the recipe.
            if stage=='mount':
                local_recipe['limits']['max_seam_gap_cm']=plan['assembly']['max_initial_gap_cm']
                local_recipe['limits']['max_displacement_cm']=plan['assembly']['max_displacement_cm']
            releases=cloth_plan.get('mount_release_steps',[0.,.5,1.]) if stage=='mount' else [1.]
            frames=recipe['phases'][phase]['frames']
            if frames<2*len(releases):raise StudioError('Cloth frame budget cannot execute every support release transition')
            if stage in ('relax','drape') and candidate.get('rest_mode')!='assembled_3d':
                raise StudioError('Relaxation and drape require geometric consolidation and a declared 3D rest')
            if stage=='drape':
                if not any(c['role']=='mannequin' for c in recipe['colliders']):raise StudioError('Drape requires the identified target collision envelope')
                record['collision']=check(candidate['placed_cm'])
                if not record['collision']['ok']:
                    error=StudioError('Drape entry has unresolved placement/enfilage contact; deep body contact cannot become a tolerance adjustment')
                    error.reason_category='placement_enfilage';raise error
                record['envelope_review']=validate_envelope_review(project,plan,recipe,colliders)
                record['dressing_entry']=dressing_measurement(project,candidate,layer_plan,declared_colliders,selected,source['placed_cm'],check_milestones=False)
                if plan.get('dressing',{}).get('required') and record['dressing_entry']['status']!='READY':
                    error=StudioError('Drape entry requires admitted source-bound dressing geometry')
                    error.reason_category='placement_enfilage';raise error
            record['cloth_runs']=[];start=copy.deepcopy(candidate['placed_cm'])
            if stage=='mount':
                record['solver_restart']='ZERO_VELOCITY_AT_EACH_SUPPORT_TRANSITION'
                record['evaluated_steps']=frames-len(releases)
                record['physical_time_continuity']='NOT_CLAIMED_QUASISTATIC_MOUNTING_TRANSITIONS'
            for index,release in enumerate(releases):
                support_stage='assembly' if stage=='mount' else stage
                candidate['pins'],support=support_weights(candidate,plan,support_stage,release=release)
                candidate['pattern_assembly']['temporary_supports_active']=support['temporary_supports_active']
                candidate['pattern_assembly']['support_transition']=copy.deepcopy(support)
                temporary=make_object(candidate,'A3D.AssemblyCandidate.'+uuid.uuid4().hex[:8])
                temporary['a3d_component_id']=component_id;temporary['a3d_package_sha256']=candidate['package_sha256']
                temporary['a3d_sewing_mesh_sha256']=obj['a3d_sewing_mesh_sha256']
                preflight(temporary,candidate,local_recipe)
                local_recipe['phases'][phase]['frames']=frames//len(releases)+(1 if index<frames%len(releases) else 0)
                def save_progress(rows):atomic_json(directory/('progress-'+str(index)+'.json'),{'frames':rows,'support_transition':support})
                def save_diagnostic(value):atomic_json(directory/('physics-failure-'+str(index)+'.json'),value)
                physics_in_progress=True
                coords,result=simulate_object(temporary,candidate,local_recipe,phase,colliders,trees,save_progress,save_diagnostic)
                physics_in_progress=False
                result.update(support_transition=support,temporary_release=release)
                record['cloth_runs'].append(result)
                if max(sum((a[k]-b[k])**2 for k in range(3))**.5 for a,b in zip(start,coords,strict=True))>local_recipe['limits']['max_displacement_cm']:
                    raise StudioError('Combined support release Cloth runs exceed the stage displacement budget')
                candidate['placed_cm']=coords
                bpy.data.objects.remove(temporary,do_unlink=True);temporary=None
            record['simulation']='PASS';record['qualification']='ASSEMBLY_PHYSICS_ONLY' if stage=='mount' else 'CONTINUOUS_RELAXATION_ONLY'
            if stage=='drape':
                record['dressing']=dressing_measurement(project,candidate,layer_plan,declared_colliders,selected,source['placed_cm'],check_milestones=False)
                if plan.get('dressing',{}).get('required') and record['dressing']['status']!='READY':
                    error=StudioError('Final source-bound dressing geometry is not admitted after Cloth')
                    error.reason_category='placement_enfilage';raise error
                temporary=make_object(candidate,'A3D.FittingCandidate.'+uuid.uuid4().hex[:8])
                temporary['a3d_sewing_mesh_sha256']=obj['a3d_sewing_mesh_sha256']
                from blender.fitting import recipe_fit
                fitting=recipe_fit(project,temporary,candidate,recipe)
                record['fitting']=fitting or 'NOT_QUALIFIED'
                if fitting and fitting.get('fit_status')=='INCOMPATIBLE':
                    error=StudioError('Demonstrated source-pattern capacity deficit blocks fitting qualification')
                    error.reason_category='demonstrated_pattern_deficit';raise error
                qualified=bool(fitting and fitting.get('fit_status')=='CAPACITY_SUFFICIENT' and not fitting.get('donning',{}).get('missing')
                    and record.get('dressing',{}).get('status')=='READY'
                    and record['dressing'].get('required') is True and record['dressing'].get('full_coverage') is True)
                record['qualification']='FITTING_PHYSICS_ONLY' if qualified else 'DRAPE_PHYSICS_ONLY_FITTING_NOT_QUALIFIED'
        record['quality']=simulation_quality(candidate,candidate['placed_cm'],recipe['mesh'])
        if context_colliders(recipe)[2]!=declared_snapshots:raise StudioError('Target body/envelope changed during the native transition')
        return _save_stage(project,session,obj,candidate,recipe,record,directory)
    except BaseException as exc:
        category=getattr(exc,'reason_category',None) or ('physical_failure' if physics_in_progress else 'placement_enfilage' if stage in ('preposition','drape') else 'geometric_consolidation' if stage=='consolidate' else 'construction')
        simulation=getattr(exc,'simulation_outcome','FAIL') if physics_in_progress else record['simulation']
        if simulation=='NOT_EXECUTED' and record.get('cloth_runs'):simulation='INCOMPLETE'
        failure={**record,'status':'REFUSED','error':str(exc),'cause':category,
            'simulation':simulation,'accepted':False,'visual_validation':'NOT_EXECUTED',
            'checkpoint':project.state()['pending_blender_operation']['checkpoint'],
            'candidate_cm':candidate['placed_cm'],'source_rest_triangles_cm':candidate.get('source_rest_triangles_cm')}
        path=directory/'failure.json';atomic_json(path,failure);exc.garment_diagnostic=reference(project,path)
        raise
    finally:
        if temporary is not None and temporary.name in bpy.data.objects:bpy.data.objects.remove(temporary,do_unlink=True)
        scene=bpy.context.scene
        frame,scene.frame_start,scene.frame_end,scene.render.fps,scene.render.fps_base,gravity,scene.use_gravity=original_settings
        scene.gravity=gravity;scene.frame_set(frame)
