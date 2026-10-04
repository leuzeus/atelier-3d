"""Introduce an exact static measured body into a checkpointed working copy."""
import uuid
from pathlib import Path

from a3d.body_context import body_context_descriptor
from a3d.core import StudioError, atomic_json, digest, sha


def _other_geometry(excluded_name):
    import bpy
    from blender.sewing import mesh_digest
    return digest({obj.name: {'type': obj.type, 'world': [list(row) for row in obj.matrix_world],
        'mesh': mesh_digest(obj) if obj.type == 'MESH' else None,
        'pose': [list(row) for bone in obj.pose.bones for row in bone.matrix] if obj.type == 'ARMATURE' else None}
        for obj in bpy.data.objects if obj.name != excluded_name})


def _validate_body(obj, inputs):
    import bpy
    from blender.body_target import evaluated_mesh
    from blender.sewing import collider_info
    if (obj.type != 'MESH' or obj.parent is not None or obj.vertex_groups or obj.data.shape_keys or obj.constraints or
            obj.animation_data or len(obj.modifiers) != 1 or obj.modifiers[0].type != 'COLLISION' or
            not obj.modifiers[0].show_viewport or not obj.modifiers[0].show_render or
            any(abs(value-1.) > 1e-8 for value in obj.scale) or
            obj.get('a3d_body_context_binding_sha256') != inputs['binding_sha256'] or
            obj.get('a3d_profile_cache_key') != inputs['profile']['cache_key']):
        raise StudioError('Working body context is absent, modified or belongs to another exact target')
    actual, _ = evaluated_mesh(obj, bpy.context.evaluated_depsgraph_get(), 1.)
    if actual != {k: inputs['geometry'][k] for k in ('vertices_cm', 'faces', 'face_sets')}:
        raise StudioError('Working body geometry or source face regions differ from the measured target')
    current = collider_info(obj); requested = inputs['context']['collision']
    if (not current['visible'] or not current['collision_enabled'] or obj.hide_render or
            any(abs(current[k]-requested[k]) > 1e-6 for k in ('outer_thickness_cm', 'inner_thickness_cm'))):
        raise StudioError('Working body collision settings differ from the explicit source-bound context')
    return actual, current


def introduce_body_target(project_root, context_path):
    import bpy
    from blender.body_source import data_ids
    from blender.operations import working
    project, session = working(project_root); inputs = body_context_descriptor(project, context_path)
    if bpy.context.mode != 'OBJECT' or abs(bpy.context.scene.unit_settings.scale_length-1.) > 1e-9:
        raise StudioError('Body introduction requires object mode and a working scene measured in meters')
    original_ids = data_ids(); database_sha = sha(project.db)
    selected = set(bpy.context.selected_objects); active = bpy.context.view_layer.objects.active
    scene = bpy.context.scene; frame = scene.frame_current; name = inputs['context']['object_name']
    original_geometry = _other_geometry(name)
    existing = bpy.data.objects.get(name)
    owners = [obj for obj in bpy.data.objects if obj.get('a3d_body_context_binding_sha256') == inputs['binding_sha256']]
    if owners and (owners != [existing] or existing.name not in scene.objects):
        raise StudioError('Another object or scene already owns this exact body context')
    introduced = existing is None; body = existing
    try:
        if body is not None:
            if body.name not in scene.objects:
                raise StudioError('Named body context is outside the current working scene')
        else:
            with bpy.data.libraries.load(str(inputs['artifact']), link=False) as (available, loaded):
                if len(available.objects) != 1 or available.armatures or available.actions:
                    raise StudioError('Measured body artifact must contain exactly one static evaluated mesh')
                loaded.objects = list(available.objects)
            body = loaded.objects[0]
            if {obj for obj in data_ids()-original_ids if isinstance(obj, bpy.types.Object)} != {body}:
                raise StudioError('Body target introduction loaded undeclared object dependencies')
            if body.type != 'MESH' or body.modifiers or body.vertex_groups or body.data.shape_keys or body.animation_data or body.parent:
                raise StudioError('Body target introduction requires its unmodified static measured mesh')
            scene.collection.objects.link(body); body.name = name
            body.hide_set(False); body.hide_viewport = False; body.hide_render = False
            bpy.context.view_layer.update()
            body.modifiers.new('A3D.BodyCollision', 'COLLISION')
            body.collision.thickness_outer = inputs['context']['collision']['outer_thickness_cm']/100
            body.collision.thickness_inner = inputs['context']['collision']['inner_thickness_cm']/100
            body['a3d_role'] = 'measured_body_target'
            body['a3d_body_context_binding_sha256'] = inputs['binding_sha256']
            body['a3d_body_context_path'] = inputs['context_ref']['path']
            body['a3d_body_context_sha256'] = inputs['context_ref']['sha256']
            body['a3d_target_geometry_sha256'] = inputs['profile']['geometry_sha256']
            body['a3d_target_pose_sha256'] = inputs['profile']['pose_sha256']
            body['a3d_profile_cache_key'] = inputs['profile']['cache_key']
        actual, collider = _validate_body(body, inputs)
        if body_context_descriptor(project, context_path)['binding_sha256'] != inputs['binding_sha256']:
            raise StudioError('Body target inputs changed during introduction')
        # Originals and all other production objects stay byte-for-byte in
        # their live geometry; only the explicitly introduced body may be new.
        if (_other_geometry(name) != original_geometry or sha(project.db) != database_sha or
                bpy.context.scene != scene or scene.frame_current != frame or
                set(bpy.context.selected_objects) != selected or bpy.context.view_layer.objects.active != active):
            raise StudioError('Body introduction changed another scene object or canonical state')
        directory = project.data/('outputs/body-context-'+uuid.uuid4().hex)
        directory.mkdir(parents=True, exist_ok=False); snapshot = directory/'context.blend'
        bpy.ops.wm.save_as_mainfile(filepath=session['working'], check_existing=False)
        bpy.ops.wm.save_as_mainfile(filepath=str(snapshot), copy=True, check_existing=False)
    except BaseException:
        if introduced:
            bpy.data.batch_remove(ids=data_ids()-original_ids)
        raise
    result = {'version': 1, 'status': 'BODY_TARGET_INTRODUCED', 'object': body.name,
              'idempotent_reuse': not introduced, 'context': inputs['context_ref'],
              'binding_sha256': inputs['binding_sha256'], 'body_target_receipt': inputs['context']['body_target_receipt'],
              'source_artifact': inputs['receipt']['artifact'], 'profile_ref': inputs['receipt']['artifacts']['profile'],
              'geometry_ref': inputs['receipt']['artifacts']['geometry'], 'geometry_sha256': inputs['profile']['geometry_sha256'],
              'pose_sha256': inputs['profile']['pose_sha256'], 'profile_cache_key': inputs['profile']['cache_key'],
              'actual_geometry_sha256': digest(actual), 'collider': collider,
              'artifact': {'path': snapshot.relative_to(project.root).as_posix(), 'sha256': sha(snapshot)},
              'working': session['working'],
              'source_mutated': False, 'anatomy_transformed': False, 'source_face_ids_preserved': True,
              'simulation': 'NOT_EXECUTED', 'fitting': 'NOT_EXECUTED', 'collision_envelope_qualification': 'NOT_GRANTED',
              'anatomical_review': 'SOURCE_DECISION_NOT_INFERRED_OR_TRANSFERRED', 'qualification': 'EXACT_BODY_CONTEXT_ONLY',
              'artistic_review': 'NOT_EXECUTED', 'next': 'Bind garment preparation to this exact measured body and explicit collider snapshot'}
    result['cache_key'] = digest(result); receipt_path = directory/'receipt.json'; atomic_json(receipt_path, result)
    return dict(result, receipt={'path': receipt_path.relative_to(project.root).as_posix(), 'sha256': sha(receipt_path)})
