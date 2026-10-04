"""Compose copied observed caches and exact body Actions, then reimport them.

Every integer source frame is reevaluated and compared. The derived linear
cache is animation transport evidence, never a new physical or fitting result.
"""
import copy
import time
import uuid

from a3d.core import StudioError, atomic_json, digest, inside, sha
from a3d.animated_delivery import animated_delivery_descriptor, checked
from a3d.export_profiles import clip_tracks, compare_native_samples
from blender.asset_export import (ExportBudgetReached, action_payloads, assign_clip, check_deadline,
                                  image_payloads, load_candidate, native_samples, pack_candidate_images,
                                  rest_payload, uv_payload, _mesh_attributes)
from blender.body_motion import _curves, action_payload, native_weights_payload


def _ref(project, path):
    return {'path': path.relative_to(project.root).as_posix(), 'sha256': sha(path)}


def _track(clip):
    return {key: clip[key] for key in ('object_name', 'action_name', 'slot_identifier', 'animation_target')}


def _source_candidate(project, artifact, profile, bounds, clips, deadline):
    """Inventory native IDs from the exact producer artifact before loading copies."""
    import bpy
    source = checked(project, artifact); check_deadline(deadline)
    with bpy.data.libraries.load(str(source), link=False) as (available, unused):
        names = list(available.objects); actions = list(available.actions); images = list(available.images)
    resources = [dict(kind='IMAGE', datablock_name=row['datablock_name'], file_ref=row['file_ref'])
                 for row in profile['source_resources'] if row['source_artifact'] == artifact]
    explicit = {row['datablock_name'] for row in resources}
    if not explicit <= set(images):
        raise StudioError('Composition resource declaration names an absent native source image')
    native_profile = {'object_names': names, 'dependency_names': [], 'action_names': actions,
                      'embedded_image_names': [name for name in images if name not in explicit], 'resources': resources,
                      'unit_scale_m': 1., 'fps': bounds[2], 'reference_frame': bounds[0], 'clips': clips}
    candidate = load_candidate(source, native_profile, 'CompositionSource')
    pack_candidate_images(project, candidate, native_profile, source)
    return candidate, native_profile


def _garment_rest(obj):
    if (obj.type != 'MESH' or obj.parent or obj.constraints or obj.modifiers or obj.animation_data or
            not obj.data.shape_keys or not obj.data.shape_keys.use_relative):
        raise StudioError('Composition requires the actual unmodified observed garment cache')
    keys = obj.data.shape_keys
    return {'vertices': [list(row.co) for row in obj.data.vertices],
            'faces': [list(row.vertices) for row in obj.data.polygons], 'uv': uv_payload(obj.data),
            'attributes': _mesh_attributes(obj.data), 'world': [list(row) for row in obj.matrix_world],
            'rest_keys': [{'name': key.name, 'relative_key': key.relative_key.name, 'mute': key.mute,
                           'vertex_group': key.vertex_group, 'coordinates': [list(row.co) for row in key.data]}
                          for key in keys.key_blocks if not key.name.startswith('Observed.Frame.')]}


def _body_rest(body, rig):
    return {'mesh': {'vertices': [list(row.co) for row in body.data.vertices],
                     'faces': [list(row.vertices) for row in body.data.polygons],
                     'uv': uv_payload(body.data), 'attributes': _mesh_attributes(body.data)},
            'rig_and_weights': native_weights_payload(body, rig)}


def _rig_rest(rig):
    return {'world': [list(row) for row in rig.matrix_world],
            'bones': [{'name': bone.name, 'parent': bone.parent.name if bone.parent else None,
                       'matrix_local': [list(row) for row in bone.matrix_local]} for bone in rig.data.bones]}


def _copy_object(source, name, scene):
    obj = source.copy(); obj.name = name
    if source.data is not None: obj.data = source.data.copy()
    scene.collection.objects.link(obj)
    return obj


def _source_frames(candidate, native_profile, primary, body_track, observations, deadline, tolerance):
    clip = dict(primary, sample_step=1, tracks=[_track(body_track)])
    samples = native_samples(candidate, dict(native_profile, clips=[clip]), deadline)[1:]
    garment_name, body_name = primary['object_name'], observations['body_name']
    expected = []
    for row in observations['frames']:
        meshes = {garment_name: {'vertices_cm': row['vertices_cm'], 'faces': observations['garment_faces']},
                  body_name: {key: row['body'][key] for key in ('vertices_cm', 'faces', 'face_sets')}}
        actual = samples[len(expected)]['meshes']
        # Cloth source face sets are optional native attributes. This comparison
        # preserves their presence in the file without inventing them in logs.
        if 'face_sets' in actual[garment_name]: meshes[garment_name]['face_sets'] = actual[garment_name]['face_sets']
        expected.append({'clip_id': primary['id'], 'time': row['frame'], 'meshes': meshes})
    primary_samples = [{'clip_id': primary['id'], 'time': row['time'],
                        'meshes': {name: row['meshes'][name] for name in (garment_name, body_name)}} for row in samples]
    comparison = compare_native_samples(expected, primary_samples, tolerance)
    return samples, comparison


def _build_actions(obj, frames_by_clip, scene, actions, deadline):
    """Preserve rest keys; derive unique observed keys and a complete Action per clip."""
    import bpy
    from mathutils import Vector
    keys = obj.data.shape_keys; keys.animation_data_clear()
    for key in list(keys.key_blocks):
        if key.name.startswith('Observed.Frame.'):
            obj.shape_key_remove(key)
    for key in keys.key_blocks: key.value = 0.
    inverse = obj.matrix_world.inverted(); rows = {}
    for clip_id, frames in frames_by_clip.items():
        rows[clip_id] = []
        for row in frames:
            check_deadline(deadline); name = 'Clip.'+clip_id+'.Frame.'+str(row['time'])
            key = obj.shape_key_add(name=name)
            if key.name != name: raise StudioError('Derived clip key identity collided')
            for point, observed in zip(key.data, row['mesh']['vertices_cm'], strict=True):
                point.co = inverse @ Vector([value/100 for value in observed])
            key.value = 0.; rows[clip_id].append((row['time'], key))
    tracks = {}
    with bpy.context.temp_override(scene=scene, view_layer=scene.view_layers[0]):
        for clip_id, frames in frames_by_clip.items():
            check_deadline(deadline); keys.animation_data_clear()
            first, last = frames[0]['time'], frames[-1]['time']
            active_keys = {key.name for _, key in rows[clip_id]}
            for key in keys.key_blocks:
                key.value = 0.
                if key == keys.reference_key: continue
                if key.name not in active_keys:
                    key.keyframe_insert('value', frame=first); key.keyframe_insert('value', frame=last)
            for frame, key in rows[clip_id]:
                for time_value, value in ((frame-1, 0.), (frame, 1.), (frame+1, 0.)):
                    key.value = value; key.keyframe_insert('value', frame=time_value)
                key.value = 0.
            action = keys.animation_data.action
            action.name = 'A3D.Delivery.'+clip_id+'.'+obj.name
            for curve in _curves(action):
                curve.extrapolation = 'CONSTANT'
                for point in curve.keyframe_points: point.interpolation = 'LINEAR'
            actions[action.name] = action
            tracks[clip_id] = {'object_name': obj.name, 'action_name': action.name,
                              'slot_identifier': keys.animation_data.action_slot.identifier, 'animation_target': 'SHAPE_KEYS'}
        keys.animation_data_clear()
        for key in keys.key_blocks: key.value = 0.
    return tracks


def _compose(project, inputs, directory, deadline):
    import bpy
    token = uuid.uuid4().hex; prefix = 'A3D.Delivery.'+token+'.'
    body_name = prefix+'Body'; rig_name = prefix+'Rig'
    garment_names = {row['component_id']: prefix+'Garment.'+row['component_id'] for row in inputs['expected_inventory'] if row['kind']=='TEXTILE'}
    profile = inputs['profile']; source_evidence = []; source_scenes = []
    loaded = {}; source_frames = {}; first_body = None; first_rig = None; body_fingerprint = None
    source_objects = {}; garment_fingerprints = {}; garment_frames = {}; body_actions = {}
    vertex_frames = 0
    for group in inputs['clips']:
        clip_id = group['declaration']['id']; merged = {}; body_samples = None
        for leaf in group['leaves']:
            result = leaf['result']; inventory = result['object_inventory']; primary = result['clip']
            body_info = inventory['body']; body_track = body_info['body_action']; garment = inventory['garment']
            key = digest(result['artifact'])
            if key not in loaded:
                loaded[key] = _source_candidate(project, result['artifact'], profile, group['bounds'], [dict(primary, sample_step=1)], deadline)
                source_scenes.append(loaded[key][0]['scene'])
            candidate, native_profile = loaded[key]
            body = candidate['objects'][body_info['object_name']]; rig = candidate['objects'][body_info['rig_name']]
            cloth = candidate['objects'][garment['object_name']]; cid = garment['component_id']
            from blender.garment_motion import _key_rest
            if (digest(action_payload(candidate['actions'][primary['action_name']])) != primary['action_sha256'] or
                    digest(action_payload(candidate['actions'][body_track['action_name']])) != body_track['action_sha256'] or
                    _key_rest(cloth) != garment['key_rest_sha256'] or
                    digest([len(cloth.data.vertices), [list(row.vertices) for row in cloth.data.polygons]]) != garment['topology_sha256']):
                raise StudioError('Native composition source Action differs from its registered observed leaf')
            body_current = _body_rest(body, rig); cloth_current = _garment_rest(cloth)
            if first_body is None:
                first_body, first_rig, body_fingerprint = body, rig, body_current
            elif body_current != body_fingerprint:
                raise StudioError('Global clips changed source body rest geometry, regions, rig or weights')
            if cid in garment_fingerprints and garment_fingerprints[cid] != cloth_current:
                raise StudioError('Global clips changed source cloth rest keys, UVs, transforms or topology')
            garment_fingerprints[cid] = cloth_current; source_objects.setdefault(cid, cloth)
            observations = dict(leaf['observations'], body_name=body_info['object_name'], garment_faces=cloth_current['faces'])
            samples, proof = _source_frames(candidate, native_profile, primary, body_track, observations, deadline, profile['geometry_tolerance_cm'])
            source_evidence.append({'clip_id': clip_id, 'source_receipt': leaf['source_receipt'], 'source_reopen_comparison': proof})
            garment_frames.setdefault(cid, {})[clip_id] = [{'time': row['time'], 'mesh': row['meshes'][garment['object_name']]} for row in samples]
            current_body = [{'clip_id': clip_id, 'time': row['time'], 'meshes': {body_name: row['meshes'][body_info['object_name']]}} for row in samples]
            if body_samples is not None:
                compare_native_samples(body_samples, current_body, profile['geometry_tolerance_cm'])
            body_samples = current_body
            for row in samples:
                merged.setdefault(row['time'], {})[garment_names[cid]] = row['meshes'][garment['object_name']]
            body_actions[clip_id] = candidate['actions'][body_track['action_name']]
            vertex_frames += len(cloth.data.vertices)*len(samples)
            if vertex_frames > profile['budgets']['max_cache_vertex_frames']:
                raise ExportBudgetReached('OBSERVED_CACHE_VERTEX_FRAME_BUDGET')
        for row in body_samples: merged[row['time']].update(row['meshes'])
        source_frames[clip_id] = [{'clip_id': clip_id, 'time': frame, 'meshes': meshes} for frame, meshes in sorted(merged.items())]
    scene = bpy.data.scenes.new('A3D.AnimatedDelivery.'+uuid.uuid4().hex)
    scene.unit_settings.system = 'METRIC'; scene.unit_settings.scale_length = 1.
    scene.render.fps = inputs['clips'][0]['bounds'][2]; scene.render.fps_base = 1.
    objects = {}; rig = _copy_object(first_rig, rig_name, scene); rig.animation_data_clear(); objects[rig.name] = rig
    body = _copy_object(first_body, body_name, scene); objects[body.name] = body
    if body.parent is not None:
        if body.parent != first_rig: raise StudioError('Body composition contains an undeclared native parent')
        body.parent = rig
    for modifier in body.modifiers:
        if modifier.type == 'ARMATURE':
            if modifier.object != first_rig: raise StudioError('Body composition has an undeclared rig dependency')
            modifier.object = rig
    actions = {}; clips = []; cloth_tracks = {}; inventory = []
    for cid, source in source_objects.items():
        cloth = _copy_object(source, garment_names[cid], scene); objects[cloth.name] = cloth
        cloth_tracks[cid] = _build_actions(cloth, garment_frames[cid], scene, actions, deadline)
        source_row = next(row for row in inputs['expected_inventory'] if row['component_id'] == cid)
        inventory.append(dict(source_row, object_name=cloth.name, source_rest_sha256=digest(garment_fingerprints[cid])))
    rigid_inventory = [];rigid_tracks={group['declaration']['id']:[] for group in inputs['clips']}
    for item in inputs['rigid_parts']:
        request = item['request']; result = item['result']; cid = request['component_id']
        source, native_profile = _source_candidate(project, item['artifact'], profile, inputs['clips'][0]['bounds'], [], deadline)
        obj = source['objects'][request['object_name']]
        dynamic=result.get('placement_binding',{}).get('mode')=='OBSERVED_TEXTILE_FRAME_ACTIONS'
        if (not dynamic and obj.animation_data) or getattr(obj.data, 'shape_keys', None) or obj.constraints or obj.modifiers:
            raise StudioError('Rigid animation requires a dedicated exact attachment/Action source contract')
        if dynamic and obj.parent:raise StudioError('Observed textile rigid Action must not invent an additional native parent')
        if obj.parent is not None:
            target = obj.parent; binding = result.get('attachment_binding', {})
            if (target.type != 'ARMATURE' or binding.get('status') != 'SOURCE_BOUND' or binding.get('target_role') != 'BODY_RIG' or
                    not binding.get('source_ref') or _rig_rest(target) != _rig_rest(first_rig) or
                    obj.parent_type != 'BONE' or obj.parent_bone not in rig.data.bones):
                raise StudioError('Rigid native parent is not an exact sourced attachment to this body rig')
            checked(project, binding['source_ref'])
        elif profile['purpose'] == 'GARMENT_CANDIDATE' and not dynamic:
            raise StudioError('Production rigid cannot acquire an invented animated attachment')
        copied = _copy_object(obj, prefix+'Rigid.'+cid, scene); objects[copied.name] = copied
        if obj.parent: copied.parent = rig
        source_row = next(row for row in inputs['expected_inventory'] if row['component_id'] == cid)
        rigid_inventory.append(dict(source_row, object_name=copied.name, attachment='OBSERVED_TEXTILE_FRAME_ACTIONS' if dynamic else 'NATIVE_SOURCE_PARENT_PRESERVED' if obj.parent else 'STATIC_TEST_ONLY'))
        for group in inputs['clips']:
            clip_id = group['declaration']['id']; bounds = group['bounds']
            source_clip = []
            if dynamic:
                matching=[clip for clip in result['clips'] if clip['id']==clip_id]
                if (len(matching)!=1 or matching[0]['object_name']!=request['object_name'] or matching[0].get('animation_target')!='OBJECT' or
                        matching[0]['frame_start']!=bounds[0] or matching[0]['frame_end']!=bounds[1] or result['fps']!=bounds[2] or
                        matching[0]['body_motion_binding']!=group['common_motion_binding']):
                    raise StudioError('Rigid textile attachment uses another body, clip, bounds or actual source owner')
                source_clip=[dict(matching[0],sample_step=1)];source_action=source['actions'][matching[0]['action_name']]
                if digest(action_payloads(source)[matching[0]['action_name']])!=matching[0]['action_sha256']:
                    raise StudioError('Rigid textile attachment Action content changed')
                action=source_action.copy();action.name='A3D.Delivery.Rigid.'+token+'.'+cid+'.'+clip_id;actions[action.name]=action
                rigid_tracks[clip_id].append({'object_name':copied.name,'action_name':action.name,
                    'slot_identifier':matching[0]['slot_identifier'],'animation_target':'OBJECT'})
            elif obj.parent:
                source['actions'][body_actions[clip_id].name] = body_actions[clip_id]
                slot = next(slot for slot in body_actions[clip_id].slots if slot.target_id_type == 'OBJECT')
                source_clip = [{'id': clip_id, 'object_name': request['object_name'], 'action_name': body_actions[clip_id].name,
                                'slot_identifier': slot.identifier, 'animation_target': 'OBJECT',
                                'frame_start': bounds[0], 'frame_end': bounds[1], 'sample_step': 1}]
                # Bind the actual parent, never the rigid object itself.
                source['objects']['A3D.SourceRigidParent'] = obj.parent; source_clip[0]['object_name'] = 'A3D.SourceRigidParent'
            if source_clip:
                rows = native_samples(source, dict(native_profile, clips=source_clip), deadline)[1:]
            else:
                rows = native_samples(source, dict(native_profile, clips=[]), deadline)
                rows = [dict(rows[0], time=frame) for frame in range(bounds[0], bounds[1]+1)]
            for row, expected in zip(rows, source_frames[clip_id], strict=True):
                expected['meshes'][copied.name] = row['meshes'][request['object_name']]
    for group in inputs['clips']:
        clip_id = group['declaration']['id']; source_action = body_actions[clip_id]; action = source_action.copy()
        action.name = 'A3D.Delivery.Body.'+clip_id; actions[action.name] = action
        if action_payload(action) != action_payload(source_action): raise StudioError('Copied native body Action changed')
        slots = [slot for slot in action.slots if slot.target_id_type == 'OBJECT']
        if len(slots) != 1: raise StudioError('Body Action has an ambiguous native target slot')
        clips.append({'id': clip_id, 'object_name': rig.name, 'action_name': action.name,
                      'slot_identifier': slots[0].identifier, 'animation_target': 'OBJECT',
                      'frame_start': group['bounds'][0], 'frame_end': group['bounds'][1], 'sample_step': 1,
                      'tracks': [cloth_tracks[cid][clip_id] for cid in sorted(cloth_tracks)]+rigid_tracks[clip_id]})
    images = {}
    for candidate, unused in loaded.values():
        for image in candidate['images'].values():
            images.setdefault(image.name, image)
    # Retain only images actually referenced by copied source materials. The
    # first candidate owns the preserved material source; unused leaf images
    # need not become whole-asset dependencies.
    used = set()
    def image_nodes(tree):
        for node in tree.nodes:
            if getattr(node, 'image', None): used.add(node.image)
            if getattr(node, 'node_tree', None): image_nodes(node.node_tree)
    for obj in objects.values():
        for slot in obj.material_slots:
            if slot.material and slot.material.node_tree: image_nodes(slot.material.node_tree)
    images = {image.name: image for image in used}
    candidate = {'scene': scene, 'objects': objects, 'actions': actions, 'images': images}
    # source rigid materials can own images absent from textile leaves. They
    # were already declared/packed by their exact source artifact loader.
    packed = image_payloads(candidate)
    first = min(group['bounds'][0] for group in inputs['clips']); last = max(group['bounds'][1] for group in inputs['clips'])
    scene.frame_start, scene.frame_end = first, last
    export = {'version': 1, 'destination': 'blender_animation', 'source_ref': {'path': 'pending.blend', 'sha256': '0'*64},
              'object_names': sorted(name for name, obj in objects.items() if obj.type == 'MESH'),
              'dependency_names': sorted(name for name, obj in objects.items() if obj.type != 'MESH'),
              'action_names': sorted(actions), 'embedded_image_names': sorted(images), 'resources': [], 'motion_receipts': [],
              'unit_scale_m': 1., 'fps': scene.render.fps, 'reference_frame': first, 'clips': clips, 'pack_resources': True,
              'geometry_tolerance_cm': profile['geometry_tolerance_cm'],
              'budgets': {'max_seconds': profile['budgets']['max_seconds'], 'max_samples': profile['budgets']['max_samples']}}
    assign_clip(candidate, clips[0]); actual = native_samples(candidate, export, deadline)
    expected = [row for group in inputs['clips'] for row in source_frames[group['declaration']['id']]]
    comparison = compare_native_samples(expected, actual[1:], profile['geometry_tolerance_cm'])
    before_rest = rest_payload(candidate); before_actions = action_payloads(candidate)
    artifact = directory/'asset.blend'; check_deadline(deadline)
    bpy.data.libraries.write(str(artifact), {scene, *actions.values(), *images.values()}, fake_user=True)
    export['source_ref'] = _ref(project, artifact)
    reopened = load_candidate(artifact, export, 'CompositionReimport', scene_name=scene.name)
    after = native_samples(reopened, export, deadline)
    reimport = compare_native_samples(actual, after, profile['geometry_tolerance_cm'])
    if (rest_payload(reopened) != before_rest or action_payloads(reopened) != before_actions or
            image_payloads(reopened) != packed):
        raise StudioError('Composition reimport changed native rest, Actions or dependencies')
    check_deadline(deadline)
    measured = []
    for clip in clips:
        row = copy.deepcopy(clip); row['status'] = 'EXECUTED_FULL_CLIP'; row['executed_times'] = list(range(clip['frame_start'], clip['frame_end']+1))
        row['action_sha256'] = digest(before_actions[clip['action_name']])
        row['tracks'] = [dict(track, action_sha256=digest(before_actions[track['action_name']])) for track in clip.get('tracks', [])]
        row['samples'] = []
        for sample in actual[1:]:
            if sample['clip_id'] != clip['id']: continue
            meshes = {name: dict(mesh, geometry_sha256=digest([mesh['vertices_cm'], mesh['faces']])) for name, mesh in sample['meshes'].items()}
            row['samples'].append({'time': sample['time'], 'meshes': meshes})
        measured.append(row)
    proof = directory/'comparison.json'
    atomic_json(proof, {'candidate': export['source_ref'], 'source_evidence': source_evidence, 'source_samples': expected,
                        'samples_before': actual, 'samples_after': after, 'source_comparison': comparison, 'reimport_comparison': reimport,
                        'rest': before_rest, 'actions': before_actions, 'packed_images': packed})
    clip_file = directory/'clips.json'
    atomic_json(clip_file, {'candidate': export['source_ref'], 'fps': export['fps'], 'scope': 'EXACT_CANDIDATE_ANIMATION', 'clips': measured})
    export_path = directory/'export-profile-template.json'; atomic_json(export_path, export)
    check_deadline(deadline)
    return {'status': 'CLIPS_EXECUTED', 'scope': 'EXACT_CANDIDATE_ANIMATION', 'temporal_coverage': 'COMPLETE',
            'candidate': export['source_ref'], 'artifact': export['source_ref'], 'fps': export['fps'],
            'clips': [{key: value for key, value in row.items() if key != 'samples'} for row in measured],
            'clips_artifact': _ref(project, clip_file), 'comparison_artifact': _ref(project, proof),
            'export_profile_template': _ref(project, export_path), 'native_reopened': True,
            'source_comparison': comparison, 'native_reimport_comparison': reimport,
            'object_inventory': {'garments': inventory, 'rigid_parts': rigid_inventory,
                                 'body': {'object_name': body.name, 'rig_name': rig.name,
                                          'source_motion_bindings': [{'id': group['declaration']['id'], 'motion_binding': group['common_motion_binding']} for group in inputs['clips']]}},
            'geometry_scope': 'BAKED_OBSERVED_FRAME_GEOMETRY_LINEAR_INTERPOLATION', 'cache_vertex_frames': vertex_frames,
            'qualified_whole_asset': False, 'physical_restart': 'NOT_QUALIFIED'}


def compose_animated_delivery(project_root, profile_path):
    import bpy
    from a3d.store import Project
    from blender.body_source import data_ids, live_geometry
    project = Project(project_root); inputs = animated_delivery_descriptor(project, profile_path); profile = inputs['profile']
    baseline = data_ids(); live = live_geometry(); database = sha(project.db); original = bpy.context.scene
    filepath = bpy.data.filepath; frame = original.frame_current; subframe = original.frame_subframe
    selected = set(bpy.context.selected_objects); active = bpy.context.view_layer.objects.active
    started = time.monotonic(); deadline = started+profile['budgets']['max_seconds']
    directory = project.data/('outputs/animated-delivery-'+uuid.uuid4().hex); directory.mkdir(parents=True, exist_ok=False)
    result = {'version': 1, 'profile': inputs['profile_ref'], 'purpose': profile['purpose'], 'binding_sha256': inputs['binding_sha256'],
              'whole_asset_inventory_status': inputs['clips'][0]['inventory']['status'],
              'source_inventory': inputs['expected_inventory'], 'source_cut_preserved': True,
              'product_acceptance': 'NOT_GRANTED', 'fitting': 'NOT_QUALIFIED', 'artistic_review': 'REQUIRED',
              'qualification_scope': 'SOURCE_INVENTORY_ANIMATION_TRANSPORT_ONLY' if profile['purpose'] == 'GARMENT_CANDIDATE' else 'FUNCTION_FIXTURE_ANIMATION_ONLY',
              'original_preserved': True, 'live_scene_mutated': False, 'budgets': profile['budgets']}
    try:
        result.update(_compose(project, inputs, directory, deadline))
    except ExportBudgetReached as error:
        result.update(status='INCOMPLETE', scope='EXACT_CANDIDATE_ANIMATION', temporal_coverage='INCOMPLETE', stopped=str(error), clips=[])
    finally:
        bpy.data.batch_remove(ids=data_ids()-baseline)
        if (data_ids()!=baseline or live_geometry()!=live or sha(project.db)!=database or bpy.context.scene!=original or
                bpy.data.filepath!=filepath or original.frame_current!=frame or original.frame_subframe!=subframe or
                set(bpy.context.selected_objects)!=selected or bpy.context.view_layer.objects.active!=active):
            raise StudioError('Composition changed original live context or canonical state')
        for group in inputs['clips']:
            for leaf in group['leaves']: checked(project, leaf['result']['artifact']); checked(project, leaf['source_receipt'])
        for item in inputs['rigid_parts']: checked(project, item['artifact']); checked(project, item['request']['source_receipt'])
        checked(project, inputs['profile_ref'])
    result['elapsed_seconds'] = time.monotonic()-started; result['blender_version'] = bpy.app.version_string
    result['cache_key'] = digest(result); receipt = directory/'receipt.json'; atomic_json(receipt, result)
    return dict(result, receipt=_ref(project, receipt))
