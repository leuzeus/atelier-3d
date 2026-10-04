"""Observe every Cloth frame against an actual native animated body.

The garment between observed integer frames is linearly interpolated; the body
is independently reevaluated at each check time. No exact intermediate Cloth
state, exhaustive nonlinear CCD or dynamic cache restart is asserted.
"""
import copy
import math
import time
import uuid

from a3d.core import StudioError, atomic_json, digest, inside, read_json, sha
from a3d.garment_motion import clip_coverage, interval_subdivisions, motion_inputs


class _Stopped(Exception):
    def __init__(self, reason, status='INCOMPLETE', details=None):
        self.reason, self.status, self.details = reason, status, details


def _time(scene, value):
    import bpy
    frame = math.floor(value); scene.frame_set(frame, subframe=value-frame)
    bpy.context.view_layer.update(); bpy.context.evaluated_depsgraph_get().update()


def _body_sample(body, rig, expected, triangles):
    import bpy
    from blender.body_motion import action_payload, native_weights_payload
    from blender.body_target import evaluated_mesh
    if (digest(action_payload(rig.animation_data.action)) != expected['action_sha256'] or
            digest(native_weights_payload(body, rig)) != expected['weights_sha256']):
        raise StudioError('Current body Action, weights, bones or modifiers changed during Cloth')
    geometry, evaluated_triangles = evaluated_mesh(body, bpy.context.evaluated_depsgraph_get(), 1.)
    topology = digest([len(geometry['vertices_cm']), geometry['faces'], triangles, geometry['face_sets']])
    if topology != expected['topology_sha256']:
        raise StudioError('Evaluated animated body lost its source vertex, polygon or region identities')
    return {'vertices_cm':geometry['vertices_cm'], 'triangles':triangles,
            'faces':geometry['faces'],'face_sets':geometry['face_sets'],
            'geometry_sha256':digest([geometry['vertices_cm'],geometry['faces']]),
            'evaluated_native_triangulation_sha256':digest(evaluated_triangles),
            'action_sha256':expected['action_sha256'], 'weights_sha256':expected['weights_sha256'],
            'topology_sha256':topology}


def _contacts(payload, colliders, coords, recipe, execution, frame):
    from blender.cloth_contacts import build_contact_context, check_contacts
    physics = recipe['phases']['drape']; policy = payload.get('pattern_assembly',{}).get('contact_policy',{})
    context = build_contact_context(payload, colliders, clearance_cm=policy.get('clearance_cm',0.),
        self_clearance_cm=physics['self_distance_cm'] if physics['self_collision'] else 0.,
        seam_tolerance_cm=recipe['limits']['weld_gap_cm'],
        max_penetration_cm=recipe['limits']['max_penetration_cm'], max_pairs=execution['max_pairs'])
    report = check_contacts(context, coords, frame=frame)
    if not report['ok']:
        status = 'INCOMPLETE' if 'BUDGET' in str(report.get('reason','')) else 'NEEDS_CORRECTION'
        raise _Stopped(report.get('reason','MOVING_BODY_CONTACT_REFUSED'), status, report)
    return report


def _key_rest(obj, include_matrix=True):
    keys=obj.data.shape_keys
    if not keys or not keys.use_relative:raise StudioError('Animated inner surface requires an exact relative native Key cache')
    return digest({'faces':[list(face.vertices) for face in obj.data.polygons],
        'matrix_world':[list(row) for row in obj.matrix_world] if include_matrix else None,
        'keys':[{'name':key.name,'relative_key':key.relative_key.name,'slider_min':key.slider_min,'slider_max':key.slider_max,
                 'interpolation':key.interpolation,'mute':key.mute,'points':[list(vertex.co) for vertex in key.data]}
                for key in keys.key_blocks]})


def _composed_state(candidate):
    from blender.body_motion import action_payload
    from blender.asset_export import candidate_animation_owners
    objects=candidate['objects'];names={obj:name for name,obj in objects.items()};rows=[]
    for name,obj in sorted(objects.items()):
        row={'name':name,'type':obj.type,'parent':names.get(obj.parent),'parent_inverse':[list(v) for v in obj.matrix_parent_inverse]}
        if obj.constraints:raise StudioError('Composed collider constraints require an unsupported dependency contract')
        row['modifiers']=[{'type':m.type,'name':m.name,'enabled':m.show_viewport,'target':names.get(getattr(m,'object',None)),
            'preserve_volume':getattr(m,'use_deform_preserve_volume',None),'vertex_groups':getattr(m,'use_vertex_groups',None),
            'bone_envelopes':getattr(m,'use_bone_envelopes',None)} for m in obj.modifiers if m.type!='COLLISION']
        if any(m.type not in ('ARMATURE','COLLISION') for m in obj.modifiers):
            raise StudioError('Composed collider requires persistent baked mesh or exact Armature dependencies')
        if obj.type=='MESH':
            row.update(points=[list(v.co) for v in obj.data.vertices],faces=[list(f.vertices) for f in obj.data.polygons],
                groups=[{obj.vertex_groups[g.group].name:g.weight for g in v.groups} for v in obj.data.vertices])
            if obj.data.shape_keys:row['keys']=_key_rest(obj,False)
        elif obj.type=='ARMATURE':
            row['bones']=[{'name':b.name,'parent':b.parent.name if b.parent else None,'matrix':[list(v) for v in b.matrix_local]} for b in obj.data.bones]
            if any(b.constraints for b in obj.pose.bones):raise StudioError('Composed collider has unsupported pose constraints')
        rows.append(row)
    actions=[]
    for (name,target),owner in sorted(candidate_animation_owners(objects).items()):
        animation=owner.animation_data
        if animation and (animation.drivers or animation.nla_tracks):raise StudioError('Composed collider has implicit animation dependencies')
        if animation and animation.action:
            actions.append({'object_name':name,'target':target,'slot':animation.action_slot.identifier,
                            'action':action_payload(animation.action)})
    return digest([rows,actions])


def _layer_sample(obj, expected, candidate=None):
    from blender.body_motion import action_payload
    from blender.sewing import object_mesh
    if candidate is not None:
        if _composed_state(candidate)!=expected['composed_state_sha256']:
            raise StudioError('Composed collider native Actions, dependencies, topology or weights changed')
    else:
        keys=obj.data.shape_keys;animation=keys.animation_data if keys else None
        if (not animation or not animation.action or animation.action_slot.identifier!=expected['slot_identifier'] or
            digest(action_payload(animation.action))!=expected['action_sha256'] or _key_rest(obj)!=expected['key_rest_sha256']):
            raise StudioError('Animated inner collider native Key Action, slot, rest or world transform changed')
    points,faces=object_mesh(obj,True);points=[[v*100 for v in p] for p in points]
    if digest([len(points),faces])!=expected['topology_sha256'] or any(not math.isfinite(v) for p in points for v in p):
        raise StudioError('Animated inner collider evaluated immutable source topology changed')
    return {'vertices_cm':points,'faces':faces,'triangles':expected.get('triangles',faces),'geometry_sha256':digest([points,faces]),
            'action_sha256':expected.get('action_sha256'),'key_rest_sha256':expected.get('key_rest_sha256'),
            'topology_sha256':expected['topology_sha256']}


def _load_composed(project, entry, scene):
    import bpy
    from blender.asset_export import assign_clip,candidate_animation_owners
    from blender.body_motion import action_payload
    with bpy.data.libraries.load(str(inside(project.root,entry['declaration']['artifact']['path'])),link=False) as (available,loaded):
        names=list(available.objects);action_names=list(available.actions)
        if len(names)>128 or entry['declaration']['object_name'] not in names:
            raise StudioError('Composed collider has missing owner or exceeds object dependency budget')
        loaded.objects=list(names);loaded.actions=list(action_names)
    candidate={'scene':scene,'objects':dict(zip(names,loaded.objects,strict=True)),
               'actions':dict(zip(action_names,loaded.actions,strict=True))}
    for obj in loaded.objects:scene.collection.objects.link(obj)
    tracks=[entry['clip']]+entry['clip'].get('tracks',[])
    for track in tracks:
        if digest(action_payload(candidate['actions'][track['action_name']]))!=track['action_sha256']:
            raise StudioError('Composed source collider Action differs from its measured native track')
        assign_clip(candidate,track)
    obj=candidate['objects'][entry['declaration']['object_name']]
    if obj.type!='MESH':raise StudioError('Declared composed collider is not a native evaluated mesh')
    obj.data.calc_loop_triangles()
    expected={'composed_state_sha256':_composed_state(candidate),
              'topology_sha256':digest([len(obj.data.vertices),[list(face.vertices) for face in obj.data.polygons]]),
              'triangles':[list(triangle.vertices) for triangle in obj.data.loop_triangles]}
    return obj,candidate,expected


def _activate_collision(obj, declared, name):
    """Configure the copied apparatus before reading native collision settings.

    Observed Key caches intentionally contain no modifiers. Consequently their
    Object.collision is None until a Collision modifier is created; reading
    collider_info before this step cannot describe a usable Cloth collider.
    All thicknesses come from the bound recipe, never a missing-data default.
    """
    modifiers=[modifier for modifier in obj.modifiers if modifier.type=='COLLISION']
    if len(modifiers)>1:
        raise StudioError('Animated collider has ambiguous multiple native Collision modifiers')
    modifier=modifiers[0] if modifiers else obj.modifiers.new(name,'COLLISION')
    modifier.show_viewport=True;modifier.show_render=True
    if obj.collision is None:
        raise StudioError('Declared animated collider did not initialize native Collision settings')
    obj.collision.thickness_outer=declared['outer_thickness_cm']/100
    obj.collision.thickness_inner=declared['inner_thickness_cm']/100


def _load_layers(project, inputs, scene, evaluation, start_frame):
    import bpy
    from blender.body_motion import action_payload
    from blender.sewing import collider_info
    result=[]
    for entry in inputs['animated_colliders']:
        if entry['kind']=='COMPOSED_NATIVE_ANIMATION':
            obj,candidate,expected=_load_composed(project,entry,scene)
            eval_obj,eval_candidate,eval_expected=_load_composed(project,entry,evaluation)
            if expected!=eval_expected:raise StudioError('Separate composed collider dependency copies differ')
            obj['a3d_animated_collider_id']=entry['declaration']['id']
            with bpy.context.temp_override(scene=scene,view_layer=scene.view_layers[0]):
                declared=entry['expected']
                _activate_collision(obj,declared,'A3D.ComposedMotion.Collision')
                _time(scene,start_frame);sample=_layer_sample(obj,expected,candidate);info=collider_info(obj)
                if (info['geometry_sha256']!=declared['geometry_sha256'] or
                        any(abs(a-b)>declared['tolerance_cm'] for a,b in zip(info['dimensions_cm'],declared['dimensions_cm']))):
                    raise StudioError('Composed obstacle first pose differs from its source recipe')
                data=read_json(inside(project.root,entry['source']['clips_artifact']['path']))
                measured=next(row for row in data['clips'] if row['id']==entry['clip']['id'])
                source_sample=next(row for row in measured['samples'] if row['time']==start_frame)['meshes'][entry['declaration']['object_name']]
                if sample['geometry_sha256']!=source_sample['geometry_sha256']:
                    raise StudioError('Composed obstacle actual starting geometry differs from registered clip sample')
            result.append({'object':obj,'evaluation_object':eval_obj,'expected':expected,'input':entry,
                           'candidate':candidate,'evaluation_candidate':eval_candidate})
            continue
        declaration=entry['declaration'];clip=entry['source']['clip']
        with bpy.data.libraries.load(str(inside(project.root,declaration['artifact']['path'])),link=False) as (available,loaded):
            if declaration['object_name'] not in available.objects or clip['action_name'] not in available.actions:
                raise StudioError('Native inner artifact lost its declared cache owner or Action')
            loaded.objects=[declaration['object_name']]
        obj=loaded.objects[0];scene.collection.objects.link(obj)
        if (obj.type!='MESH' or obj.modifiers or obj.constraints or obj.parent or obj.animation_data or
                obj.data.shape_keys is None or obj.data.shape_keys.animation_data is None or
                obj.data.shape_keys.animation_data.drivers or obj.data.shape_keys.animation_data.nla_tracks):
            raise StudioError('Inner cache must be a standalone baked mesh without implicit modifiers, drivers or parents')
        keys=obj.data.shape_keys;animation=keys.animation_data
        if animation.action_slot.target_id_type!='KEY' or digest(action_payload(animation.action))!=clip['action_sha256']:
            raise StudioError('Native inner artifact actual Key Action differs from registered clip')
        obj['a3d_animated_collider_id']=declaration['id']
        expected={'action_sha256':clip['action_sha256'],'slot_identifier':clip['slot_identifier'],
                  'key_rest_sha256':_key_rest(obj),'topology_sha256':digest([len(obj.data.vertices),[list(face.vertices) for face in obj.data.polygons]])}
        eval_obj=obj.copy();eval_obj.data=obj.data.copy();evaluation.collection.objects.link(eval_obj)
        with bpy.context.temp_override(scene=scene,view_layer=scene.view_layers[0]):
            declared=entry['expected']
            _activate_collision(obj,declared,'A3D.InnerMotion.Collision')
            _time(scene,start_frame);actual=_layer_sample(obj,expected);info=collider_info(obj)
            if 'geometry_sha256' in declared and (info['geometry_sha256']!=declared['geometry_sha256'] or
                    any(abs(a-b)>declared['tolerance_cm'] for a,b in zip(info['dimensions_cm'],declared['dimensions_cm']))):
                raise StudioError('Inner animated collider first pose differs from its source recipe')
            source_frames=read_json(inside(project.root,entry['source']['observations_artifact']['path']))['frames']
            observed=next((row for row in source_frames if row['frame']==start_frame),None)
            if observed is None or max(math.dist(a,b) for a,b in zip(actual['vertices_cm'],observed['vertices_cm'],strict=True))>.001:
                raise StudioError('Inner native cache is not the actually observed registered starting geometry')
        result.append({'object':obj,'evaluation_object':eval_obj,'expected':expected,'input':entry})
    return result


def _bake(obj, observations, profile, scene, expired):
    """A separate native Key Action represents only actually observed geometry."""
    import bpy
    from blender.body_motion import action_payload, _curves
    count = len(observations)*len(obj.data.vertices)
    if count > profile['execution']['max_cache_vertex_frames']:
        raise _Stopped('OBSERVED_GEOMETRY_CACHE_BUDGET')
    baked = obj.copy(); baked.data = obj.data.copy(); baked.name = 'A3D.ObservedCloth.'+profile['id']
    scene.collection.objects.link(baked)
    for modifier in list(baked.modifiers): baked.modifiers.remove(modifier)
    keys = baked.data.shape_keys
    keys.animation_data_clear()
    for key in keys.key_blocks: key.value = 0.
    for observation in observations:
        if expired(): raise _Stopped('TIME_BUDGET_DURING_OBSERVED_GEOMETRY_CACHE')
        frame = observation['frame']; key = baked.shape_key_add(name='Observed.Frame.'+str(frame))
        for vertex, point in zip(key.data,observation['vertices_cm'],strict=True): vertex.co = [v/100 for v in point]
        key.value = 0.; key.keyframe_insert('value',frame=frame-1)
        key.value = 1.; key.keyframe_insert('value',frame=frame)
        key.value = 0.; key.keyframe_insert('value',frame=frame+1)
    action = keys.animation_data.action; action.name = 'A3D.ObservedCloth.Keys.'+profile['id']
    for curve in _curves(action):
        curve.extrapolation = 'CONSTANT'
        for key in curve.keyframe_points: key.interpolation = 'LINEAR'
    baked['a3d_observed_cache'] = profile['id']
    baked['a3d_component_id'] = profile['component_id']
    baked['a3d_geometry_scope'] = 'BAKED_OBSERVED_FRAME_GEOMETRY_LINEAR_INTERPOLATION'
    first,last = observations[0]['frame'],observations[-1]['frame']
    clip = {'id':profile['id'], 'object_name':baked.name,'action_name':action.name,
            'slot_identifier':keys.animation_data.action_slot.identifier, 'animation_target':'SHAPE_KEYS',
            'frame_start':first,'frame_end':last,'interpolation':'LINEAR',
            'geometry_scope':baked['a3d_geometry_scope'],'action_sha256':digest(action_payload(action)),
            'cache_vertex_frames':count}
    return baked,clip


def _reopen_cache(artifact, observations, profile, body_expected, specification, body_profile, expired):
    import bpy
    from blender.body_source import data_ids
    from blender.body_motion import action_payload, native_weights_payload
    from blender.sewing import object_mesh
    from blender.moving_contacts import interpolate
    baseline = data_ids()
    try:
        scene = bpy.data.scenes.new('A3D.ObservedCloth.Reopen.'+uuid.uuid4().hex)
        scene.unit_settings.system = 'METRIC'; scene.unit_settings.scale_length = 1.
        scene.render.fps = body_profile['fps']
        with bpy.data.libraries.load(str(artifact),link=False) as (available,loaded):
            if len(available.objects) != len(profile['_artifact_object_names']): raise StudioError('Motion cache artifact lost garment, body, rig or collider dependencies')
            names=list(available.objects)
            loaded.objects = list(available.objects)
        object_map=dict(zip(names,loaded.objects,strict=True))
        for item in loaded.objects: scene.collection.objects.link(item)
        baked=object_map[profile['_garment_object_name']]
        body=object_map[profile['_body_object_name']];rig=object_map[profile['_rig_object_name']]
        keys = baked.data.shape_keys
        if not keys or not keys.animation_data or not keys.animation_data.action:
            raise StudioError('Observed geometry cache lost its native Key Action')
        if digest(action_payload(keys.animation_data.action)) != profile['_baked_action_sha256']:
            raise StudioError('Reopened cache Key Action changed')
        if (digest(action_payload(rig.animation_data.action)) != body_expected['action_sha256'] or
                digest(native_weights_payload(body,rig)) != body_expected['weights_sha256']):
            raise StudioError('Reopened body Action or weights changed')
        first,last = observations[0]['frame'],observations[-1]['frame']
        times = sorted(set([float(first),float(last),(first+last)//2,first+.5 if last>first else first]))
        lookup = {row['frame']:row['vertices_cm'] for row in observations}; checks = []
        with bpy.context.temp_override(scene=scene,view_layer=scene.view_layers[0]):
            for sample_time in times:
                if expired(): raise _Stopped('TIME_BUDGET_DURING_CACHE_REIMPORT')
                _time(scene,sample_time); actual,faces = object_mesh(baked,True)
                actual = [[v*100 for v in point] for point in actual]
                low,high = math.floor(sample_time),math.ceil(sample_time)
                expected = interpolate(lookup[low],lookup[high],sample_time-low)
                error = max(math.dist(a,b) for a,b in zip(actual,expected,strict=True))
                if faces != profile['_faces'] or error > .001:
                    raise StudioError('Reopened native Key cache differs from observed frame/interpolation geometry')
                inner_checks=[]
                for declared in profile['_layers']:
                    inner=object_map[declared['object_name']]
                    source_candidate=None
                    if declared['kind']=='COMPOSED_NATIVE_ANIMATION':
                        source_candidate={'objects':{row['logical_name']:object_map[row['actual_name']] for row in declared['dependency_objects']}}
                    measured=_layer_sample(inner,declared['native_identity'],source_candidate)
                    before=next(row for row in observations if row['frame']==low)['animated_colliders'][profile['_layers'].index(declared)]
                    after=next(row for row in observations if row['frame']==high)['animated_colliders'][profile['_layers'].index(declared)]
                    expected_inner=interpolate(before['vertices_cm'],after['vertices_cm'],sample_time-low)
                    if declared['kind']=='COMPOSED_NATIVE_ANIMATION':
                        expected_inner=profile['_reopen_expected_layers'][sample_time][profile['_layers'].index(declared)]['vertices_cm']
                    inner_error=max(math.dist(a,b) for a,b in zip(measured['vertices_cm'],expected_inner,strict=True))
                    if inner_error>.001:raise StudioError('Reopened inner cache differs from actually evaluated frame/interpolation geometry')
                    inner_checks.append({'id':declared['id'],'maximum_error_cm':inner_error,'geometry_sha256':measured['geometry_sha256']})
                # The native body Action is reevaluated, not linearly treated as
                # a mesh cache. Its source body observations include these times.
                reference=profile['_reopen_expected_body'][sample_time]
                measured_body=_body_sample(body,rig,body_expected,reference['triangles'])
                if measured_body['geometry_sha256']!=reference['geometry_sha256']:
                    raise StudioError('Reopened body actual animated geometry changed')
                checks.append({'time':sample_time,'maximum_error_cm':error,'geometry_sha256':digest(actual),
                               'body_geometry_sha256':measured_body['geometry_sha256'],'animated_colliders':inner_checks})
        return {'status':'REOPENED_OBSERVED_GEOMETRY_MATCHES','samples':checks,
                'maximum_error_cm':max(row['maximum_error_cm'] for row in checks),
                'rest_keys_retained':list(keys.key_blocks.keys())[:2]}
    finally:
        bpy.data.batch_remove(ids=data_ids()-baseline)


def _run(project, profile_path):
    import bpy
    from blender.body_source import data_ids, live_geometry
    from blender.body_motion import evaluate_clip, action_payload, native_weights_payload
    from blender.sewing import make_object, object_mesh, structural_inputs, apply_physics, physical_snapshot, verify_physics, collider_info
    from blender.moving_contacts import interpolate, swept_crossing
    from a3d.cloth_metrics import validate_metrics
    inputs = motion_inputs(project,profile_path); profile = inputs['profile']; execution = profile['execution']
    payload,recipe,body_profile = inputs['candidate'],inputs['recipe'],inputs['body_profile']
    component_continuity=None
    if profile['purpose']!='TEST_ONLY':
        from blender.textile_executor import verified_component_continuity
        component_continuity=verified_component_continuity(project,payload,recipe['limits']['weld_gap_cm'])
        from a3d.garment_motion import animated_continuity,require_production_continuity
        require_production_continuity(component_continuity)
        animated_continuity(payload,payload['placed_cm'],payload['faces'],component_continuity)
    baseline = data_ids(); original = bpy.context.scene; source_live = live_geometry()
    source_path = bpy.data.filepath; source_dirty = bpy.data.is_dirty; source_frame = original.frame_current
    source_subframe = original.frame_subframe; source_db = sha(project.db)
    start = time.monotonic(); expired = lambda:time.monotonic()-start >= execution['max_seconds']
    observations=[]; intervals=[]; terminal=None; stopped=None; clip=None; cache_check=None; artifact_ref=None
    body_execution_identity=None; object_inventory=None; layers=[]; token=uuid.uuid4().hex
    directory = project.data/('outputs/garment-motion-'+token); directory.mkdir(parents=True,exist_ok=False)
    try:
        scene = bpy.data.scenes.new('A3D.GarmentMotion.'+token)
        scene.unit_settings.system='METRIC'; scene.unit_settings.scale_length=1.
        evaluation = bpy.data.scenes.new('A3D.GarmentMotion.BodyEvaluation.'+token)
        evaluation.unit_settings.system='METRIC'; evaluation.unit_settings.scale_length=1.
        with bpy.data.libraries.load(str(inside(project.root,inputs['body_motion']['artifact']['path'])),link=False) as (available,loaded):
            if len(available.objects)!=2 or len(available.armatures)!=1 or len(available.actions)!=1:
                raise StudioError('Body-motion artifact requires its exact skin, rig and one Action')
            loaded.objects=list(available.objects)
        for item in loaded.objects: scene.collection.objects.link(item)
        body=next(item for item in loaded.objects if item.type=='MESH')
        rig=next(item for item in loaded.objects if item.type=='ARMATURE')
        eval_rig=rig.copy(); eval_rig.data=rig.data.copy(); evaluation.collection.objects.link(eval_rig)
        eval_body=body.copy(); eval_body.data=body.data.copy(); evaluation.collection.objects.link(eval_body)
        for modifier in eval_body.modifiers:
            if modifier.type=='ARMATURE': modifier.object=eval_rig
        with bpy.context.temp_override(scene=evaluation,view_layer=evaluation.view_layers[0]):
            recomputed=evaluate_clip(eval_body,eval_rig,body_profile,inputs['rig'],author=False)
        saved=read_json(inside(project.root,inputs['body_motion']['samples_artifact']['path']))
        for name in ('samples','motion_binding','action_sha256','weights_sha256','topology_sha256'):
            if recomputed[name]!=saved[name]: raise StudioError('Current native body differs from admitted motion evidence: '+name)
        if expired(): raise _Stopped('TIME_BUDGET_DURING_BODY_REVALIDATION')
        triangles=recomputed['samples'][0]['triangles']
        body_expected={name:recomputed[name] for name in ('action_sha256','weights_sha256','topology_sha256')}
        evaluation.render.fps=body_profile['fps']
        layers=_load_layers(project,inputs,scene,evaluation,body_profile['frame_start'])
        with bpy.context.temp_override(scene=scene,view_layer=scene.view_layers[0]):
            _time(scene,body_profile['frame_start'])
            if recipe['colliders']:
                declared=next(row for row in recipe['colliders'] if row['role']=='mannequin'); info=collider_info(body)
                if (info['geometry_sha256']!=declared['geometry_sha256'] or
                        any(abs(a-b)>declared['tolerance_cm'] for a,b in zip(info['dimensions_cm'],declared['dimensions_cm']))):
                    raise StudioError('Animated body first pose differs from the garment source collider')
                thickness=declared
            else: thickness=profile['body_collision']
            body.modifiers.new('A3D.Motion.Collision','COLLISION')
            body.collision.thickness_outer=thickness['outer_thickness_cm']/100
            body.collision.thickness_inner=thickness['inner_thickness_cm']/100
            sim_expected=dict(body_expected,weights_sha256=digest(native_weights_payload(body,rig)))
            body_execution_identity=sim_expected
            cloth_obj=make_object(payload,'A3D.GarmentMotion.Cloth.'+profile['id'])
            structural_inputs(cloth_obj,payload,recipe)
            cloth,_,_=apply_physics(cloth_obj,payload,recipe,'drape',[body]+[row['object'] for row in layers])
            first,last=body_profile['frame_start'],body_profile['frame_end']
            maximum_end=last+(profile.get('terminal_relax') or {}).get('max_frames',0)
            if maximum_end-first+1>recipe['phases']['drape']['frames']:
                raise StudioError('Whole clip and terminal relaxation exceed source recipe frame budget')
            scene.frame_start=first; scene.frame_end=maximum_end; scene.render.fps=body_profile['fps']
            cloth.point_cache.frame_start=first; cloth.point_cache.frame_end=maximum_end
            expected_physics=physical_snapshot(cloth_obj)
            if expected_physics['settings']['use_sewing_springs']:
                raise StudioError('Garment motion requires consolidated rest with sewing springs disabled')
            previous=None; previous_body=None; terminal_monitor=None
            previous_layers=None
            for frame in range(first,maximum_end+1):
                if frame-first>=execution['max_frames']: raise _Stopped('FRAME_BUDGET')
                if expired(): raise _Stopped('TIME_BUDGET')
                _time(scene,frame)
                vertices,faces=object_mesh(cloth_obj,True); coords=[[v*100 for v in p] for p in vertices]
                if faces!=payload['faces'] or len(coords)!=len(payload['placed_cm']) or any(not math.isfinite(v) for p in coords for v in p):
                    raise StudioError('Cloth evaluated source topology or finite geometry changed')
                verify_physics(cloth_obj,expected_physics)
                continuity=None
                if component_continuity is not None:
                    continuity=animated_continuity(payload,coords,faces,component_continuity)
                measured_body=_body_sample(body,rig,sim_expected,triangles)
                measured_layers=[_layer_sample(row['object'],row['expected'],row.get('candidate')) for row in layers]
                observation_vertices=len(coords)+len(measured_body['vertices_cm'])+sum(len(row['vertices_cm']) for row in measured_layers)
                if (len(observations)+1)*observation_vertices>execution['max_cache_vertex_frames']:
                    raise _Stopped('WHOLE_OBSERVED_VERTEX_FRAME_BUDGET')
                quality=validate_metrics(payload,coords,recipe['mesh'],include_faces=False)
                displacement=max(math.dist(a,b) for a,b in zip(payload['placed_cm'],coords,strict=True))
                if displacement>recipe['limits']['max_displacement_cm']:
                    raise _Stopped('CLOTH_DISPLACEMENT_LIMIT','NEEDS_CORRECTION',{'displacement_cm':displacement})
                gap=max((math.dist(coords[a],coords[b]) for seam in payload['seams'].values()
                         if seam['kind']=='permanent' for a,b in seam['pairs']),default=0.)
                if gap>recipe['limits']['max_seam_gap_cm']:
                    raise _Stopped('PERMANENT_SEAM_GAP_LIMIT','NEEDS_CORRECTION',{'gap_cm':gap})
                contact=_contacts(payload,[body]+[row['object'] for row in layers],coords,recipe,execution,frame)
                observation={'frame':frame,'vertices_cm':coords,'body_geometry_sha256':measured_body['geometry_sha256'],
                             'body':measured_body,'animated_colliders':measured_layers,
                             'quality':quality,'contacts':contact,'max_displacement_cm':displacement,'seam_gap_cm':gap,
                             'component_continuity':continuity,
                             'solver_max_iterations':cloth.solver_result.max_iterations if cloth.solver_result else None}
                # Intermediate body evaluation happens in another scene and cannot
                # rewind or invent a subframe state of this Cloth point cache.
                if previous is not None:
                    split=interval_subdivisions(previous['vertices_cm'],coords,previous_body['vertices_cm'],
                        measured_body['vertices_cm'],execution,body_profile['intermediate_substeps'])
                    for old,new in zip(previous_layers,measured_layers,strict=True):
                        reserve=interval_subdivisions(previous['vertices_cm'],coords,old['vertices_cm'],new['vertices_cm'],execution,body_profile['intermediate_substeps'])
                        if reserve['subdivisions']>split['subdivisions']:split=reserve
                    if split['status']!='READY': raise _Stopped(split['reason'],details=split)
                    checks=[]; swept=[]; sub_previous=previous['vertices_cm']; body_previous=previous_body
                    layers_previous=previous_layers
                    with bpy.context.temp_override(scene=evaluation,view_layer=evaluation.view_layers[0]):
                        for index in range(1,split['subdivisions']+1):
                            if expired(): raise _Stopped('TIME_BUDGET_DURING_MOVING_CONTACTS')
                            fraction=index/split['subdivisions']; sample_time=frame-1+fraction
                            _time(evaluation,sample_time)
                            sub_body=_body_sample(eval_body,eval_rig,body_expected,triangles)
                            sub_layers=[_layer_sample(row['evaluation_object'],row['expected'],row.get('evaluation_candidate')) for row in layers]
                            sub_coords=interpolate(previous['vertices_cm'],coords,fraction)
                            sub_continuity=(animated_continuity(payload,sub_coords,payload['faces'],component_continuity)
                                            if component_continuity is not None else None)
                            relative_increment=(max(math.dist(a,b) for a,b in zip(sub_previous,sub_coords,strict=True))+
                                max(math.dist(a,b) for a,b in zip(body_previous['vertices_cm'],sub_body['vertices_cm'],strict=True)))
                            if relative_increment>execution['max_step_cm']+1e-8:
                                raise _Stopped('ACTUAL_BODY_SUBSTEP_INCREMENT_BUDGET',details={
                                    'time':sample_time,'relative_increment_cm':relative_increment,'limit_cm':execution['max_step_cm']})
                            sub_contact=_contacts(payload,[eval_body]+[row['evaluation_object'] for row in layers],sub_coords,recipe,execution,sample_time)
                            crossing=swept_crossing(sub_previous,sub_coords,payload['faces'],body_previous['vertices_cm'],
                                sub_body['vertices_cm'],triangles,max_pairs=execution['max_pairs'],expired=expired)
                            if not crossing['ok']:
                                raise _Stopped(crossing['reason'],'INCOMPLETE' if crossing['status']=='INCOMPLETE' else 'NEEDS_CORRECTION',crossing)
                            layer_crossings=[]
                            for layer_index,(old,new) in enumerate(zip(layers_previous,sub_layers,strict=True)):
                                increment=(max(math.dist(a,b) for a,b in zip(sub_previous,sub_coords,strict=True))+
                                           max(math.dist(a,b) for a,b in zip(old['vertices_cm'],new['vertices_cm'],strict=True)))
                                if increment>execution['max_step_cm']+1e-8:
                                    raise _Stopped('ACTUAL_INNER_COLLIDER_SUBSTEP_BUDGET',details={'id':layers[layer_index]['input']['declaration']['id'],'time':sample_time})
                                layer_crossing=swept_crossing(sub_previous,sub_coords,payload['faces'],old['vertices_cm'],new['vertices_cm'],
                                    new['triangles'],max_pairs=execution['max_pairs'],expired=expired)
                                if not layer_crossing['ok']:
                                    raise _Stopped(layer_crossing['reason'],'INCOMPLETE' if layer_crossing['status']=='INCOMPLETE' else 'NEEDS_CORRECTION',layer_crossing)
                                layer_crossings.append(layer_crossing)
                            checks.append({'time':sample_time,'body_geometry_sha256':sub_body['geometry_sha256'],
                                           'body_native_triangulation_sha256':sub_body['evaluated_native_triangulation_sha256'],
                                           'animated_colliders':[{'id':row['input']['declaration']['id'],'geometry_sha256':value['geometry_sha256']}
                                                for row,value in zip(layers,sub_layers,strict=True)],
                                           'garment_geometry_sha256':digest(sub_coords),'contacts':sub_contact})
                            checks[-1]['component_continuity']=sub_continuity
                            swept.append({'body':crossing,'animated_colliders':layer_crossings})
                            sub_previous=sub_coords; body_previous=sub_body; layers_previous=sub_layers
                    intervals.append({'from_frame':frame-1,'to_frame':frame,'sampling':split,'checks':checks,'swept':swept})
                observations.append(observation); previous=observation; previous_body=measured_body; previous_layers=measured_layers
                if frame>last:
                    if terminal_monitor is None:
                        from a3d.simulation_control import ConvergenceMonitor
                        declared=profile['terminal_relax']
                        control={key:declared[key] for key in ('min_frames','window_frames','velocity_tolerance_cm_s')}
                        control['max_seconds']=max(.001,execution['max_seconds']-(time.monotonic()-start))
                        terminal_monitor=ConvergenceMonitor(control,body_profile['fps'],declared['max_frames'],recipe['limits']['max_seam_gap_cm'])
                    converged=terminal_monitor.observe(frame-last,coords,gap,True); terminal=terminal_monitor.report()
                    if converged: break
            if terminal_monitor: terminal_monitor.require_convergence()
            if profile.get('terminal_relax') and terminal_monitor is None:
                raise _Stopped('TERMINAL_RELAXATION_NOT_OBSERVED')
            if expired(): raise _Stopped('TIME_BUDGET_AFTER_CLIP')
            baked,clip=_bake(cloth_obj,observations,profile,scene,expired); clip['fps']=body_profile['fps']
            clip['key_rest_sha256']=_key_rest(baked)
            object_inventory={'garment':{'object_name':baked.name,'component_id':profile['component_id'],
                'package_sha256':payload.get('package_sha256'),'source_pieces':sorted(payload['panels']),
                'source_uv_sha256':inputs['source']['source_uv_sha256'],'topology_sha256':digest([len(payload['placed_cm']),payload['faces']]),
                'key_rest_sha256':clip['key_rest_sha256'],'source_face_provenance_sha256':digest({key:payload.get(key)
                    for key in ('source_rest_triangles_cm','source_face_vertex_ids','source_face_pieces','source_vertex_map')})},
                'body':{'object_name':body.name,'rig_name':rig.name,'motion_binding':inputs['body_motion']['motion_binding'],
                    'body_action':{'object_name':rig.name,'action_name':rig.animation_data.action.name,
                        'slot_identifier':rig.animation_data.action_slot.identifier,'animation_target':'OBJECT','action_sha256':sim_expected['action_sha256']}},
                'animated_colliders':[{'id':row['input']['declaration']['id'],'object_name':row['object'].name,
                    'kind':row['input']['kind'],
                    'source_receipt':row['input']['declaration']['source_receipt'],'source_artifact':row['input']['declaration']['artifact'],
                    'source_object_name':row['input']['declaration']['object_name'],'clip':row['input']['clip'],
                    'dependency_objects':[{'logical_name':name,'actual_name':obj.name} for name,obj in row.get('candidate',{}).get('objects',{}).items()],
                    'action_name':row['object'].data.shape_keys.animation_data.action.name if row['object'].data.shape_keys else None,
                    'native_identity':row['expected']}
                    for row in layers]}
            artifact=directory/'garment-motion.blend'
            artifact_objects={baked,body,rig,*[row['object'] for row in layers]}
            artifact_objects.update(obj for row in layers for obj in row.get('candidate',{}).get('objects',{}).values())
            verification_times=sorted(set([float(observations[0]['frame']),float(observations[-1]['frame']),
                (observations[0]['frame']+observations[-1]['frame'])//2,
                observations[0]['frame']+.5 if observations[-1]['frame']>observations[0]['frame'] else observations[0]['frame']]))
            expected_body_samples={};expected_layer_samples={}
            with bpy.context.temp_override(scene=evaluation,view_layer=evaluation.view_layers[0]):
                for verify_time in verification_times:
                    if expired():raise _Stopped('TIME_BUDGET_DURING_CACHE_SOURCE_COMPARISON')
                    _time(evaluation,verify_time)
                    expected_body_samples[verify_time]=_body_sample(eval_body,eval_rig,body_expected,triangles)
                    expected_layer_samples[verify_time]=[_layer_sample(row['evaluation_object'],row['expected'],row.get('evaluation_candidate')) for row in layers]
            bpy.data.libraries.write(str(artifact),artifact_objects,fake_user=True)
            artifact_ref={'path':artifact.relative_to(project.root).as_posix(),'sha256':sha(artifact)}
            checked_profile=dict(profile,_baked_action_sha256=clip['action_sha256'],_faces=payload['faces'],
                                 _layers=object_inventory['animated_colliders'],_body_samples=recomputed['samples'],
                                 _artifact_object_names=sorted(obj.name for obj in artifact_objects),
                                 _garment_object_name=baked.name,_body_object_name=body.name,_rig_object_name=rig.name,
                                 _reopen_expected_body=expected_body_samples,_reopen_expected_layers=expected_layer_samples)
            cache_check=_reopen_cache(artifact,observations,checked_profile,sim_expected,inputs['rig'],body_profile,expired)
            if expired(): raise _Stopped('TIME_BUDGET_AFTER_CACHE_REIMPORT')
    except _Stopped as error:
        stopped={'reason':error.reason,'status':error.status,'details':error.details}
    except StudioError as error:
        stopped={'reason':str(error),'status':getattr(error,'simulation_outcome','NEEDS_CORRECTION'),
                 'quality_metrics':getattr(error,'quality_metrics',None),'quality_violations':getattr(error,'quality_violations',None)}
    finally:
        bpy.data.batch_remove(ids=data_ids()-baseline)
    if (data_ids()!=baseline or bpy.context.scene!=original or bpy.data.filepath!=source_path or
            original.frame_current!=source_frame or original.frame_subframe!=source_subframe or
            bpy.data.is_dirty!=source_dirty or sha(project.db)!=source_db or live_geometry()!=source_live):
        raise StudioError('Whole-clip observation altered original scene or canonical project state')
    active_frames=[row['frame'] for row in observations if row['frame']<=body_profile['frame_end']]
    coverage=clip_coverage(body_profile,active_frames,stopped,terminal)
    complete=coverage['clip_complete'] and cache_check is not None and stopped is None
    result={'version':1,'status':'GARMENT_CLIP_SAMPLES_COMPLETE' if complete else (stopped or {}).get('status','INCOMPLETE'),
            'execution':'NATIVE_CLOTH_INTEGER_FRAMES','coverage':coverage,'source':inputs['source'],
            'bindings':copy.deepcopy(profile['bindings']),'profile':inputs['profile_ref'],
            'fit_context':copy.deepcopy(inputs['fit_context']),'fit_intent':copy.deepcopy(inputs['fit_intent']),
            'body_origin':inputs['body_origin'],'candidate_origin':inputs['candidate_origin'],
            'body_motion_binding':inputs['body_motion']['motion_binding'],'body_execution_identity':body_execution_identity,
            'purpose':profile['purpose'],'object_inventory':object_inventory,
            'component_continuity':component_continuity,
            'observed_frames':len(observations),'observed_geometry_sha256':digest(observations),
            'elapsed_seconds':time.monotonic()-start,'budgets':execution,'stopped':stopped,
            'clip':clip,'artifact':artifact_ref,'cache_reopened':cache_check,
            'qualification':'OBSERVED_CLIP_SAMPLES_AND_REOPENED_ANIMATION_ONLY' if complete else 'NOT_QUALIFIED',
            'geometry_scope':'BAKED_OBSERVED_FRAME_GEOMETRY_LINEAR_INTERPOLATION',
            'physical_restart':'NOT_QUALIFIED','continuous_collision_qualification':'NOT_GRANTED',
            'functional_pins_retained':copy.deepcopy(payload['pins']),'temporary_supports_active':False,
            'fitting':'NOT_QUALIFIED','product_acceptance':'NOT_GRANTED','accepted':False,
            'live_scene_mutated':False,'source_patterns_modified':False,'blender_version':bpy.app.version_string}
    observations_path=directory/'observations.json'; atomic_json(observations_path,{'frames':observations,'intervals':intervals})
    result['observations_artifact']={'path':observations_path.relative_to(project.root).as_posix(),'sha256':sha(observations_path)}
    result['cache_key']=digest(result); receipt=directory/'receipt.json'; atomic_json(receipt,result)
    result['receipt']={'path':receipt.relative_to(project.root).as_posix(),'sha256':sha(receipt)}
    return result


def run_garment_motion(project_root, profile_path):
    from a3d.store import Project
    return _run(Project(project_root),profile_path)
