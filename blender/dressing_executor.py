"""Execute explicitly sourced grips against native fixed skin and moving layers.

Integer frames advance actual Cloth. Intermediate garment surfaces interpolate
observed frames; separate evaluated obstacles and relative sweeps are checked.
This is sampled dressing execution, not exact subframe dynamics or fitting.
"""
import copy
import math
import time
import uuid

from a3d.core import StudioError,atomic_json,digest,inside,read_json,sha
from a3d.dressing_paths import dressing_execution_descriptor,support_sample


def pin_weights(obj,evaluated=False):
    group=obj.vertex_groups.get('A3D.Pins')
    if group is None:raise StudioError('Dressing native pin group is absent')
    if evaluated:
        import bpy
        obj=obj.evaluated_get(bpy.context.evaluated_depsgraph_get())
    return {str(vertex.index):membership.weight for vertex in obj.data.vertices
            for membership in vertex.groups if membership.group==group.index and membership.weight>0.}


def other_weights(obj):
    return digest({group.name:[(vertex.index,membership.weight) for vertex in obj.data.vertices
                  for membership in vertex.groups if membership.group==group.index]
                   for group in obj.vertex_groups if group.name!='A3D.Pins'})


def apply_supports(obj,target,supports,frame,functional_pins):
    """Only named source grips move; release removes their real native weights."""
    group=obj.vertex_groups.get('A3D.Pins');weights=dict(functional_pins);states=[]
    for support in supports:
        state=support_sample(support,frame);states.append(dict(state,id=support['id']))
        vertex=state['vertex'];group.remove([vertex])
        if state['weight']>0.:group.add([vertex],state['weight'],'REPLACE');weights[str(vertex)]=state['weight']
        if target is not None:target.data[vertex].co=[value/100 for value in state['point_cm']]
    actual=pin_weights(obj)
    if set(actual)!=set(weights) or any(abs(actual[key]-value)>1e-6 for key,value in weights.items()):
        raise StudioError('Dressing native support weights differ from their explicit release schedule')
    return states,weights


def support_key_schedule(support,index,end_frame):
    """Triangular native Key influences, exactly interpolating sourced points."""
    keys=support['resolved_waypoints'];row=keys[index];values={row['frame']:1.}
    if index:values[keys[index-1]['frame']]=0.
    elif support['start_frame']>1:values[support['start_frame']-1]=0.
    if index+1<len(keys):values[keys[index+1]['frame']]=0.
    else:values[end_frame]=1.
    return sorted(values.items())


def _curve_value(schedule,frame):
    if frame<=schedule[0][0]:return schedule[0][1]
    if frame>=schedule[-1][0]:return schedule[-1][1]
    a,b=next((a,b) for a,b in zip(schedule,schedule[1:]) if a[0]<=frame<=b[0])
    return a[1]+(b[1]-a[1])*(frame-a[0])/(b[0]-a[0])


def author_support_action(obj,supports,end_frame,max_vertex_keys):
    """Time dependencies exist before Cloth; no edits to Key data during cache."""
    from blender.body_motion import _curves,action_payload
    from blender.garment_motion import _key_rest,_Stopped
    count=len(obj.data.vertices)*sum(len(row['resolved_waypoints']) for row in supports)
    if count>max_vertex_keys:raise _Stopped('DRESSING_SUPPORT_VERTEX_KEY_BUDGET')
    records=[]
    for support in supports:
        for index,waypoint in enumerate(support['resolved_waypoints']):
            key=obj.shape_key_add(name='A3D.DressingTarget.'+support['id']+'.'+str(index),from_mix=False)
            key.data[support['vertex']].co=[value/100 for value in waypoint['point_cm']]
            schedule=support_key_schedule(support,index,end_frame)
            for frame,value in schedule:key.value=value;key.keyframe_insert('value',frame=frame)
            records.append({'key_name':key.name,'support_id':support['id'],'source_index':index,'schedule':schedule})
    keys=obj.data.shape_keys;animation=keys.animation_data
    if not animation or not animation.action or animation.action_slot.target_id_type!='KEY':
        raise StudioError('Dressing support trajectory has no actual native Key Action and slot')
    action=animation.action;action.name='A3D.DressingTargets.'+uuid.uuid4().hex
    for curve in _curves(action):
        curve.extrapolation='CONSTANT'
        for key in curve.keyframe_points:key.interpolation='LINEAR'
    return {'kind':'NATIVE_LINEAR_KEY_ACTION','action_name':action.name,
        'slot_identifier':animation.action_slot.identifier,'action_sha256':digest(action_payload(action)),
        'source_key_geometry_sha256':_key_rest(obj),'vertex_keys':count,'keys':records}


def _support_action_identity(obj):
    from blender.body_motion import action_payload
    from blender.garment_motion import _key_rest
    keys=obj.data.shape_keys;animation=keys.animation_data if keys else None
    action=animation.action if animation else None;slot=animation.action_slot if animation else None
    return {'action_name':action.name if action else None,
            'action_sha256':digest(action_payload(action)) if action else None,
            'slot_identifier':slot.identifier if slot else None,'slot_type':slot.target_id_type if slot else None,
            'drivers':bool(animation and animation.drivers),'nla_tracks':bool(animation and animation.nla_tracks),
            'source_key_geometry_sha256':_key_rest(obj) if keys else None}


def _verify_support_action_identity(obj,driver):
    expected={key:driver[key] for key in ('action_name','action_sha256','slot_identifier','source_key_geometry_sha256')}
    expected.update(slot_type='KEY',drivers=False,nla_tracks=False);actual=_support_action_identity(obj)
    changed={key:{'expected':value,'actual':actual[key]} for key,value in expected.items() if actual[key]!=value}
    if changed:
        error=StudioError('Dressing source trajectory Action, Key data or native slot changed')
        error.details={'source_trajectory_identity_mismatches':changed};raise error
    return actual


def verify_support_action(obj,driver,frame):
    _verify_support_action_identity(obj,driver);keys=obj.data.shape_keys
    values=[]
    for row in driver['keys']:
        actual=keys.key_blocks[row['key_name']].value;expected=_curve_value(row['schedule'],frame)
        if abs(actual-expected)>1e-6:raise StudioError('Dressing source Key influence differs from its native frame schedule')
        values.append({'key_name':row['key_name'],'value':actual})
    return values


def support_weight_schedule(support,end_frame):
    """Stepwise native influences: exact start and release, never a fade."""
    values={1:0.,support['start_frame']:support['weight'],support['release_frame']:0.,end_frame:0.}
    return sorted(values.items())


def _step_value(schedule,frame):
    return next((value for at,value in reversed(schedule) if at<=frame),schedule[0][1])


def author_support_weights(obj,supports,end_frame):
    """Author evaluated pin weights before Cloth, without runtime RNA edits.

    Each fixed mask owns one source grip vertex. A native Object Action changes
    only the mix influence. The source pin group and rest mesh remain immutable
    throughout the simulation, avoiding geometry recalc/cache invalidation.
    """
    import bpy
    from blender.body_motion import _curves,action_payload
    # Blender's automatic keying may reuse an Action with multiple owner slots.
    # A fresh Object Action keeps its CONSTANT curves separate from the Key
    # Action whose LINEAR trajectory was already bound before this operation.
    source_identity=_support_action_identity(obj)
    if obj.animation_data and (obj.animation_data.action or obj.animation_data.drivers or obj.animation_data.nla_tracks):
        raise StudioError('Dressing release authoring requires an unanimated temporary Object owner')
    obj.animation_data_create();action=bpy.data.actions.new('A3D.DressingGripWeights.'+uuid.uuid4().hex)
    obj.animation_data.action=action
    records=[]
    for support in supports:
        mask=obj.vertex_groups.new(name='A3D.DressingGrip.'+support['id'])
        mask.add([support['vertex']],1.,'REPLACE')
        modifier=obj.modifiers.new('A3D.DressingWeight.'+support['id'],'VERTEX_WEIGHT_MIX')
        modifier.vertex_group_a='A3D.Pins';modifier.vertex_group_b=mask.name
        modifier.mix_mode='SET';modifier.mix_set='B'
        modifier.default_weight_a=modifier.default_weight_b=0.
        modifier.normalize=False;modifier.invert_vertex_group_a=False;modifier.invert_vertex_group_b=False
        modifier.mask_vertex_group='';modifier.mask_texture=None
        schedule=support_weight_schedule(support,end_frame)
        for frame,value in schedule:
            modifier.mask_constant=value;modifier.keyframe_insert('mask_constant',frame=frame)
        records.append({'support_id':support['id'],'vertex':support['vertex'],'mask_group':mask.name,
                        'modifier_name':modifier.name,'schedule':schedule})
    animation=obj.animation_data
    if not animation or not animation.action or animation.action_slot.target_id_type!='OBJECT':
        raise StudioError('Dressing release schedule lacks an actual native Object Action and slot')
    if animation.action!=action or action==obj.data.shape_keys.animation_data.action:
        raise StudioError('Dressing native weight and trajectory Actions must have distinct owners')
    for curve in _curves(action):
        curve.extrapolation='CONSTANT'
        for key in curve.keyframe_points:key.interpolation='CONSTANT'
    actual_identity=_support_action_identity(obj)
    if actual_identity!=source_identity:
        error=StudioError('Dressing release authoring changed the source trajectory Action or Key geometry')
        error.details={'source_trajectory_identity_mismatches':{key:{'expected':value,'actual':actual_identity[key]}
                       for key,value in source_identity.items() if actual_identity[key]!=value}};raise error
    return {'kind':'NATIVE_CONSTANT_WEIGHT_MIX_ACTION','action_name':action.name,
            'action_sha256':digest(action_payload(action)),'slot_identifier':animation.action_slot.identifier,
            'raw_pin_weights':pin_weights(obj),'non_pin_groups_sha256':other_weights(obj),'records':records}


def verify_support_weights(obj,driver,supports,frame,functional_pins):
    from blender.body_motion import action_payload
    animation=obj.animation_data
    if (not animation or animation.drivers or animation.nla_tracks or not animation.action or
            animation.action_slot.identifier!=driver['slot_identifier'] or
            digest(action_payload(animation.action))!=driver['action_sha256'] or
            pin_weights(obj)!=driver['raw_pin_weights'] or other_weights(obj)!=driver['non_pin_groups_sha256']):
        raise StudioError('Dressing native weight Action, static groups or Object slot changed')
    records=[];ordered=list(obj.modifiers);cloth=next((m for m in ordered if m.type=='CLOTH'),None)
    for record in driver['records']:
        modifier=obj.modifiers.get(record['modifier_name'])
        expected=_step_value(record['schedule'],frame)
        if (modifier is None or modifier.type!='VERTEX_WEIGHT_MIX' or cloth is None or ordered.index(modifier)>=ordered.index(cloth) or
                not modifier.show_viewport or not modifier.show_render or modifier.vertex_group_a!='A3D.Pins' or
                modifier.vertex_group_b!=record['mask_group'] or modifier.mix_mode!='SET' or modifier.mix_set!='B' or
                modifier.default_weight_a!=0. or modifier.default_weight_b!=0. or modifier.normalize or
                modifier.invert_vertex_group_a or modifier.invert_vertex_group_b or modifier.mask_vertex_group or modifier.mask_texture or
                abs(modifier.mask_constant-expected)>1e-6):
            raise StudioError('Dressing evaluated pin modifier differs from its sourced step schedule')
        records.append({'id':record['support_id'],'mask_constant':modifier.mask_constant,'expected':expected})
    states=[dict(support_sample(support,frame),id=support['id']) for support in supports]
    expected_weights=dict(functional_pins)
    for state in states:
        if state['weight']>0.:expected_weights[str(state['vertex'])]=state['weight']
    actual=pin_weights(obj,evaluated=True)
    if set(actual)!=set(expected_weights) or any(abs(actual[key]-value)>1e-6 for key,value in expected_weights.items()):
        raise StudioError('Dressing actual evaluated pin weights differ from sourced start/release frames')
    return states,actual,records


def endpoint_report(coords,constraints):
    rows=[{'method_id':row['method_id'],'vertex':row['vertex'],'error_cm':math.dist(coords[row['vertex']],row['point_cm']),
           'tolerance_cm':row['tolerance_cm']} for row in constraints]
    return {'ok':all(row['error_cm']<=row['tolerance_cm'] for row in rows),'constraints':rows,
            'scope':'DECLARED_SOURCE_ENDPOINTS_ONLY','fitting':'NOT_QUALIFIED'}


def verify_full_weight_grips(coords,states):
    from blender.garment_motion import _Stopped
    errors=[{'id':state['id'],'vertex':state['vertex'],'error_cm':math.dist(coords[state['vertex']],state['point_cm'])}
            for state in states if state['weight']>=1.]
    if any(row['error_cm']>.001 for row in errors):
        raise _Stopped('DRESSING_NATIVE_FULL_WEIGHT_GRIP_TARGET_MISMATCH','NEEDS_CORRECTION',errors)
    return errors


def _geometry(obj):
    from blender.sewing import object_mesh
    vertices,faces=object_mesh(obj,True)
    return {'vertices_cm':[[value*100 for value in point] for point in vertices],'faces':faces}


def _verify_parameters(obj,expected,non_pins,rest_key,rest_digest,weights):
    from blender.sewing import physical_snapshot,verify_physics
    actual=physical_snapshot(obj)
    # Raw groups and parameters never change during cache. Scheduled pin weights
    # are supplied by the native modifiers and observed on evaluated geometry.
    if other_weights(obj)!=non_pins or digest([list(vertex.co) for vertex in rest_key.data])!=rest_digest:
        raise StudioError('Dressing altered source rest geometry or non-support material/contact groups')
    observed=pin_weights(obj,evaluated=True)
    if set(observed)!=set(weights) or any(abs(observed[key]-value)>1e-6 for key,value in weights.items()):
        raise StudioError('Dressing observed pin weights do not match their planned native frame')
    verify_physics(obj,expected)
    return actual


def _source_uv(obj,payload):
    layer=obj.data.uv_layers.new(name='A3D.SourceUV.cm')
    pieces=sorted(payload['panels']);attribute=obj.data.attributes.new('a3d_source_piece','INT','FACE')
    for polygon,uv,piece in zip(obj.data.polygons,payload['source_rest_triangles_cm'],payload['source_face_pieces'],strict=True):
        for loop,point in zip(polygon.loop_indices,uv,strict=True):layer.data[loop].uv=point
        attribute.data[polygon.index].value=pieces.index(piece)
    return digest([payload['source_rest_triangles_cm'],payload['source_face_pieces']])


def run_dressing_program(project_root,profile_path):
    from a3d.store import Project
    project=Project(project_root);descriptor=dressing_execution_descriptor(project,profile_path)
    result={'version':1,'profile':descriptor['profile_ref'],'purpose':descriptor['profile']['purpose'],
            'bindings':copy.deepcopy(descriptor['profile']['bindings']),'binding_sha256':descriptor['binding_sha256'],
            'qualification':'NONE','fitting':'NOT_QUALIFIED','product_acceptance':'NOT_GRANTED','accepted':False,
            'source_cut_preserved':True,'source_mutated':False,'continuous_contacts':'NOT_QUALIFIED',
            'cache_restart':'NOT_QUALIFIED','body_pose':'FIXED_EXACT_MEASURED_TARGET',
            'artifacts':{},'simulation':'NOT_EXECUTED','diagnostics':descriptor['diagnostics']}
    result['driver_implementation_sources']={
        'vertex_group_rna_geometry_recalc':'https://raw.githubusercontent.com/blender/blender/blender-v5.2-release/source/blender/makesrna/intern/rna_object.cc',
        'native_weight_mix_rna':'https://raw.githubusercontent.com/blender/blender/blender-v5.2-release/source/blender/makesrna/intern/rna_modifier.cc'}
    if descriptor['status']=='NEEDS_DATA':
        result['status']='NEEDS_DATA';result['native_scene_created']=False
        directory=project.data/('outputs/dressing-'+uuid.uuid4().hex);directory.mkdir(parents=True,exist_ok=False)
        path=directory/'receipt.json';result['cache_key']=digest(result);atomic_json(path,result)
        return dict(result,receipt={'path':path.relative_to(project.root).as_posix(),'sha256':sha(path)})
    import bpy
    from a3d.cloth_metrics import validate_metrics
    from a3d.garment_motion import animated_continuity,interval_subdivisions
    from blender.body_source import data_ids,live_geometry
    from blender.body_target import evaluated_mesh
    from blender.garment_motion import (_Stopped,_activate_collision,_contacts,_layer_sample,_load_layers,_time)
    from blender.moving_contacts import interpolate,swept_crossing
    from blender.sewing import (apply_physics,collider_info,make_object,physical_snapshot,rest_key_name,structural_inputs)
    inputs=descriptor['motion_inputs'];source=inputs['candidate'];recipe=inputs['recipe'];profile=descriptor['profile']
    execution=dict(inputs['profile']['execution'],**profile['execution'])
    continuity=None
    if profile['purpose']=='GARMENT_CANDIDATE':
        from blender.textile_executor import verified_component_continuity
        continuity=verified_component_continuity(project,source,recipe['limits']['weld_gap_cm'])
        from a3d.garment_motion import require_production_continuity
        require_production_continuity(continuity)
        animated_continuity(source,source['placed_cm'],source['faces'],continuity)
    baseline=data_ids();live=live_geometry();original=bpy.context.scene;original_frame=original.frame_current
    original_subframe=original.frame_subframe;original_path=bpy.data.filepath;db_sha=sha(project.db)
    selected=set(bpy.context.selected_objects);active=bpy.context.view_layer.objects.active
    started=time.monotonic();expired=lambda:time.monotonic()-started>=execution['max_seconds']
    directory=project.data/('outputs/dressing-'+uuid.uuid4().hex);directory.mkdir(parents=True,exist_ok=False)
    observations=[];intervals=[];stopped=None;artifact_ref=None;final_ref=None;endpoints=None;layers=[];cloth_started=False
    try:
        scene=bpy.data.scenes.new('A3D.Dressing.Sequence');scene.unit_settings.scale_length=1.
        evaluation=bpy.data.scenes.new('A3D.Dressing.Obstacles');evaluation.unit_settings.scale_length=1.
        body_record=descriptor['body_target'];body_geometry=read_json(inside(project.root,body_record['artifacts']['geometry']['path']))
        triangles=read_json(inside(project.root,body_record['artifacts']['triangles']['path']))
        with bpy.data.libraries.load(str(inside(project.root,body_record['artifact']['path'])),link=False) as (available,loaded):
            if len(available.objects)!=1:raise StudioError('Dressing target artifact must contain its one exact evaluated skin')
            loaded.objects=list(available.objects)
        body=loaded.objects[0]
        if body.type!='MESH' or body.modifiers or body.constraints or body.parent or body.animation_data or body.data.shape_keys:
            raise StudioError('Dressing static body must not have hidden motion or geometry dependencies')
        scene.collection.objects.link(body);evaluation.collection.objects.link(body)
        scene.render.fps=evaluation.render.fps=recipe['phases']['drape']['fps']
        declared=(next(row for row in recipe['colliders'] if row['role']=='mannequin')
                  if profile['purpose']=='GARMENT_CANDIDATE' else inputs['profile']['body_collision'])
        _activate_collision(body,declared,'A3D.Dressing.BodyCollision')
        with bpy.context.temp_override(scene=scene,view_layer=scene.view_layers[0]):
            actual,native_triangles=evaluated_mesh(body,bpy.context.evaluated_depsgraph_get(),1.)
            if actual['vertices_cm']!=body_geometry['vertices_cm'] or actual['faces']!=body_geometry['faces'] or native_triangles!=triangles:
                raise StudioError('Dressing loaded body differs from its measured native geometry and triangulation')
            body_sha=digest([actual['vertices_cm'],actual['faces']]);info=collider_info(body)
            if profile['purpose']=='GARMENT_CANDIDATE' and (info['geometry_sha256']!=declared['geometry_sha256'] or
                    any(abs(a-b)>declared['tolerance_cm'] for a,b in zip(info['dimensions_cm'],declared['dimensions_cm']))):
                raise StudioError('Dressing actual body differs from the garment source recipe collider')
        layers=_load_layers(project,inputs,scene,evaluation,1)
        with bpy.context.temp_override(scene=scene,view_layer=scene.view_layers[0]):
            runtime=copy.deepcopy(source);runtime['placed_cm']=copy.deepcopy(descriptor['entry']['placed_cm'])
            runtime['pins']=dict(source['pins'])
            obj=make_object(runtime,'A3D.Dressing.Cloth');structural_inputs(obj,runtime,recipe)
            uv_sha=_source_uv(obj,source)
            # Admission evaluates the exact entry before Cloth can move it.
            entry_contact=_contacts(source,[body]+[row['object'] for row in layers],runtime['placed_cm'],recipe,execution,0)
            result['entry_contacts']=entry_contact
            if continuity:animated_continuity(source,runtime['placed_cm'],source['faces'],continuity)
            driver=author_support_action(obj,descriptor['supports'],descriptor['instructions']['frame_end'],execution['max_cache_vertex_frames'])
            result['support_driver']=driver
            _verify_support_action_identity(obj,driver)
            weight_driver=author_support_weights(obj,descriptor['supports'],descriptor['instructions']['frame_end'])
            result['support_weight_driver']=weight_driver
            _verify_support_action_identity(obj,driver)
            cloth,_,_=apply_physics(obj,runtime,recipe,'drape',[body]+[row['object'] for row in layers])
            cloth.point_cache.frame_end=descriptor['instructions']['frame_end'];scene.frame_end=cloth.point_cache.frame_end
            # apply_physics adds its source collision exclusion group once,
            # before frame advancement; include it in the immutable baseline.
            weight_driver['non_pin_groups_sha256']=other_weights(obj)
            expected=physical_snapshot(obj);non_pins=other_weights(obj)
            rest=obj.data.shape_keys.key_blocks[rest_key_name(source)];rest_digest=digest([list(v.co) for v in rest.data])
            if expected['settings']['use_sewing_springs']:raise StudioError('Dressing must preserve continuous rest without sewing springs')
            previous=None;previous_layers=None
            for frame in range(1,descriptor['instructions']['frame_end']+1):
                if frame>execution['max_frames']:raise _Stopped('DRESSING_FRAME_BUDGET')
                if expired():raise _Stopped('DRESSING_TIME_BUDGET')
                for support in descriptor['supports']:
                    if frame==support['start_frame'] and previous is not None:
                        error=math.dist(previous['vertices_cm'][support['vertex']],support['resolved_waypoints'][0]['point_cm'])
                        if error>.001:raise _Stopped('DRESSING_NEXT_GRIP_SOURCE_ENTRY_MISMATCH','NEEDS_CORRECTION',{'id':support['id'],'error_cm':error})
                cloth_started=True;_time(scene,frame)
                if cloth.point_cache.is_outdated:raise _Stopped('DRESSING_NATIVE_CACHE_OUTDATED','NEEDS_CORRECTION')
                driver_values=verify_support_action(obj,driver,frame)
                states,weights,weight_driver_values=verify_support_weights(obj,weight_driver,descriptor['supports'],frame,source['pins'])
                geometry=_geometry(obj);coords=geometry['vertices_cm']
                if geometry['faces']!=source['faces'] or len(coords)!=len(source['placed_cm']) or any(not math.isfinite(v) for p in coords for v in p):
                    raise StudioError('Dressing Cloth changed source topology or finite native geometry')
                observed_body=_geometry(body)
                if digest([observed_body['vertices_cm'],observed_body['faces']])!=body_sha:
                    raise StudioError('Dressing body changed from its fixed measured pose')
                measured_layers=[_layer_sample(row['object'],row['expected'],row.get('candidate')) for row in layers]
                count=len(coords)+len(observed_body['vertices_cm'])+sum(len(row['vertices_cm']) for row in measured_layers)
                if frame*count>execution['max_cache_vertex_frames']:raise _Stopped('DRESSING_OBSERVED_VERTEX_FRAME_BUDGET')
                physics=_verify_parameters(obj,expected,non_pins,rest,rest_digest,weights)
                grip_errors=verify_full_weight_grips(coords,states)
                quality=validate_metrics(source,coords,recipe['mesh'],include_faces=False)
                movement=max(math.dist(a,b) for a,b in zip(runtime['placed_cm'],coords,strict=True))
                if movement>recipe['limits']['max_displacement_cm']:raise _Stopped('DRESSING_SOURCE_DISPLACEMENT_LIMIT','NEEDS_CORRECTION')
                contact=_contacts(source,[body]+[row['object'] for row in layers],coords,recipe,execution,frame)
                for stage in descriptor['instructions']['method_stages']:
                    if frame==stage['end_frame']:
                        stage_end=endpoint_report(coords,[row for row in descriptor['constraints'] if row['method_id']==stage['method_id']])
                        if not stage_end['ok']:raise _Stopped('DRESSING_STAGE_ENDPOINTS_NOT_REACHED','NEEDS_CORRECTION',stage_end)
                continuous=animated_continuity(source,coords,source['faces'],continuity) if continuity else None
                if previous is not None:
                    split=interval_subdivisions(previous['vertices_cm'],coords,observed_body['vertices_cm'],observed_body['vertices_cm'],execution,2)
                    for old,new in zip(previous_layers,measured_layers,strict=True):
                        more=interval_subdivisions(previous['vertices_cm'],coords,old['vertices_cm'],new['vertices_cm'],execution,2)
                        if more['subdivisions']>split['subdivisions']:split=more
                    if split['status']!='READY':raise _Stopped(split['reason'])
                    checks=[];old_coords=previous['vertices_cm'];old_layers=previous_layers
                    with bpy.context.temp_override(scene=evaluation,view_layer=evaluation.view_layers[0]):
                        for substep in range(1,split['subdivisions']+1):
                            if expired():raise _Stopped('DRESSING_TIME_BUDGET_DURING_CONTACTS')
                            fraction=substep/split['subdivisions'];sample_time=frame-1+fraction;_time(evaluation,sample_time)
                            sub_coords=interpolate(previous['vertices_cm'],coords,fraction)
                            sub_layers=[_layer_sample(row['evaluation_object'],row['expected'],row.get('evaluation_candidate')) for row in layers]
                            sub_contact=_contacts(source,[body]+[row['evaluation_object'] for row in layers],sub_coords,recipe,execution,sample_time)
                            sweeps=[swept_crossing(old_coords,sub_coords,source['faces'],observed_body['vertices_cm'],observed_body['vertices_cm'],triangles,max_pairs=execution['max_pairs'],expired=expired)]
                            for old,new in zip(old_layers,sub_layers,strict=True):
                                relative=max(math.dist(a,b) for a,b in zip(old_coords,sub_coords,strict=True))+max(math.dist(a,b) for a,b in zip(old['vertices_cm'],new['vertices_cm'],strict=True))
                                if relative>execution['max_step_cm']+1e-8:raise _Stopped('DRESSING_ACTUAL_LAYER_SUBSTEP_BUDGET')
                                sweeps.append(swept_crossing(old_coords,sub_coords,source['faces'],old['vertices_cm'],new['vertices_cm'],new['triangles'],max_pairs=execution['max_pairs'],expired=expired))
                            for sweep in sweeps:
                                if not sweep['ok']:raise _Stopped(sweep['reason'],'INCOMPLETE' if sweep['status']=='INCOMPLETE' else 'NEEDS_CORRECTION',sweep)
                            if continuity:animated_continuity(source,sub_coords,source['faces'],continuity)
                            checks.append({'time':sample_time,'contacts':sub_contact,'sweeps':sweeps,
                                           'garment_geometry_sha256':digest(sub_coords),'body_geometry_sha256':body_sha,
                                           'layer_geometry_sha256':[row['geometry_sha256'] for row in sub_layers]})
                            old_coords=sub_coords;old_layers=sub_layers
                    intervals.append({'from_frame':frame-1,'to_frame':frame,'sampling':split,'checks':checks})
                if expired():raise _Stopped('DRESSING_TIME_BUDGET_AFTER_CONTACTS')
                observation={'frame':frame,'vertices_cm':coords,'body_geometry_sha256':body_sha,
                             'animated_colliders':measured_layers,'contacts':contact,'quality':quality,'supports':states,
                             'physics_sha256':digest(physics),'continuity':continuous,'max_displacement_cm':movement,
                             'full_weight_grip_errors':grip_errors,'support_driver_values':driver_values,
                             'support_weight_driver_values':weight_driver_values,'evaluated_pin_weights':weights,
                             'point_cache':{'is_outdated':cloth.point_cache.is_outdated,'info':cloth.point_cache.info}}
                observations.append(observation);previous=observation;previous_layers=measured_layers
            if any(state['weight']>0 for state in observations[-1]['supports']):raise StudioError('Dressing ended with temporary grips still active')
            endpoints=endpoint_report(observations[-1]['vertices_cm'],descriptor['constraints'])
            if not endpoints['ok']:raise _Stopped('DRESSING_DECLARED_ENDPOINTS_NOT_REACHED','NEEDS_CORRECTION',endpoints)
            # Save an observed static final geometry on a copy, preserving source
            # rest keys/UV/provenance. It is not a dynamic Cloth checkpoint.
            final=obj.copy();final.data=obj.data.copy();scene.collection.objects.link(final)
            final.animation_data_clear()
            final.data.shape_keys.animation_data_clear()
            for modifier in list(final.modifiers):
                if modifier.type=='CLOTH' or modifier.name in {r['modifier_name'] for r in weight_driver['records']}:
                    final.modifiers.remove(modifier)
            for record in weight_driver['records']:final.vertex_groups.remove(final.vertex_groups[record['mask_group']])
            for block in final.data.shape_keys.key_blocks:block.value=0.
            observed=final.shape_key_add(name='A3D.ObservedDressingFinal')
            for vertex,point in zip(observed.data,observations[-1]['vertices_cm'],strict=True):vertex.co=[v/100 for v in point]
            observed.value=1.;artifact=directory/'dressed.blend';name=final.name
            bpy.data.libraries.write(str(artifact),{final},fake_user=True)
            with bpy.data.libraries.load(str(artifact),link=False) as (_,loaded):loaded.objects=[name]
            reopened=loaded.objects[0];scene.collection.objects.link(reopened);scene.view_layers[0].update();reopened_geometry=_geometry(reopened)
            error=max(math.dist(a,b) for a,b in zip(reopened_geometry['vertices_cm'],observations[-1]['vertices_cm'],strict=True))
            if reopened_geometry['faces']!=source['faces'] or error>.001:raise StudioError('Dressing observed final artifact did not re-open within native precision')
            validate_metrics(source,reopened_geometry['vertices_cm'],recipe['mesh'],include_faces=False)
            _contacts(source,[body]+[row['object'] for row in layers],reopened_geometry['vertices_cm'],recipe,execution,scene.frame_current)
            endpoints=endpoint_report(reopened_geometry['vertices_cm'],descriptor['constraints'])
            if not endpoints['ok']:raise _Stopped('DRESSING_REOPENED_ENDPOINTS_NOT_REACHED','NEEDS_CORRECTION',endpoints)
            if expired():raise _Stopped('DRESSING_TIME_BUDGET_DURING_ROUNDTRIP')
            final_payload=copy.deepcopy(source);final_payload['placed_cm']=reopened_geometry['vertices_cm']
            final_payload['dressing_observation']={'profile':descriptor['profile_ref'],'source_candidate':inputs['profile']['bindings']['candidate'],
                'frame':descriptor['instructions']['frame_end'],'temporary_grips_removed':True,'qualification':'SAMPLED_SOURCE_DRESSING_SEQUENCE'}
            final_path=directory/'candidate.json';atomic_json(final_path,final_payload)
            artifact_ref={'path':artifact.relative_to(project.root).as_posix(),'sha256':sha(artifact)}
            final_ref={'path':final_path.relative_to(project.root).as_posix(),'sha256':sha(final_path)}
            result.update(native_reopened=True,native_roundtrip_error_cm=error,source_uv_sha256=uv_sha)
    except _Stopped as error:stopped={'status':error.status,'reason':error.reason,'details':error.details}
    except StudioError as error:stopped={'status':getattr(error,'simulation_outcome','NEEDS_CORRECTION'),'reason':str(error),
        'details':getattr(error,'details',None),
        'metrics':getattr(error,'quality_metrics',None),'violations':getattr(error,'quality_violations',None)}
    finally:bpy.data.batch_remove(ids=data_ids()-baseline)
    if (data_ids()!=baseline or live_geometry()!=live or bpy.context.scene!=original or original.frame_current!=original_frame or
            original.frame_subframe!=original_subframe or bpy.data.filepath!=original_path or sha(project.db)!=db_sha or
            set(bpy.context.selected_objects)!=selected or bpy.context.view_layer.objects.active!=active):
        raise StudioError('Dressing changed the original scene or canonical state')
    for ref in descriptor['evidence']:
        if sha(inside(project.root,ref['path']))!=ref['sha256']:raise StudioError('Dressing source changed during native execution')
    complete=stopped is None and len(observations)==descriptor['instructions']['frame_end'] and artifact_ref is not None
    result.update(status='DRESSING_SEQUENCE_SAMPLES_COMPLETE' if complete else (stopped or {}).get('status','INCOMPLETE'),
        simulation='NATIVE_CLOTH_INTEGER_FRAMES' if cloth_started else 'NOT_EXECUTED',
        qualification='SAMPLED_SOURCE_DRESSING_SEQUENCE' if complete else 'NONE',observed_frames=len(observations),
        required_frames=descriptor['instructions']['frame_end'],stopped=stopped,endpoint_constraints=endpoints,
        component_continuity=continuity,body_origin=descriptor['body_origin'],entry_origin=descriptor['entry_origin'],
        body_regions=descriptor['body_regions'],fit_intent=inputs['fit_intent'],
        source_method_configurations=descriptor['source_method_configurations'],source_open_link_states=descriptor['source_open_link_states'],
        cloth_subframes='LINEAR_INTERPOLATION_OF_OBSERVED_FRAMES_NOT_EXACT_CLOTH',elapsed_seconds=time.monotonic()-started,
        temporary_supports_removed=bool(complete),artifact=artifact_ref if complete else None,derived_mesh=final_ref if complete else None,
        frame_coverage='COMPLETE' if complete else 'INCOMPLETE',drape_convergence='NOT_QUALIFIED',
        closure_behavior='NOT_QUALIFIED',native_scene_created=True,original_scene_preserved=True)
    samples_path=directory/'observations.json';atomic_json(samples_path,{'frames':observations,'intervals':intervals,'source':descriptor['profile_ref']})
    result['observations_artifact']={'path':samples_path.relative_to(project.root).as_posix(),'sha256':sha(samples_path)}
    result['cache_key']=digest(result);receipt=directory/'receipt.json';atomic_json(receipt,result)
    return dict(result,receipt={'path':receipt.relative_to(project.root).as_posix(),'sha256':sha(receipt)})
