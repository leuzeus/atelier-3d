"""Create declared Actions and evaluate moving body colliders at every sample.

No Cloth or garment contact acceptance is inferred from body-motion evaluation.
Slotted Action channels use the Blender 4.4+ API, including Blender 5.x.
"""
import copy
import math
import uuid

from a3d.core import StudioError, atomic_json, digest, inside, read_json, sha
from a3d.motion_profiles import motion_evidence_binding, sample_times, target_rig_specification, validate_motion_profile, verify_sample_coverage


def _curves(action):
    curves = []
    for layer in action.layers:
        for strip in layer.strips:
            if strip.type != 'KEYFRAME':
                raise StudioError('Motion Action contains an unsupported non-keyframe strip')
            for channelbag in strip.channelbags:
                curves.extend(channelbag.fcurves)
    return curves


def action_payload(action):
    """Hash actual curves, handles and modifiers, rather than just Action name."""
    if action is None:
        raise StudioError('Motion body has no actual Action')
    return {'slots': [{'identifier': slot.identifier, 'target_id_type': slot.target_id_type} for slot in action.slots],
            'layers': [{'name': layer.name, 'influence': getattr(layer, 'influence', None),
                        'mix_mode': getattr(layer, 'mix_mode', None)} for layer in action.layers],
            'curves': sorted([{'data_path': curve.data_path, 'array_index': curve.array_index,
                       'extrapolation': curve.extrapolation, 'mute': curve.mute,
                       'keys': [{'co': list(key.co), 'interpolation': key.interpolation,
                                 'left': list(key.handle_left), 'right': list(key.handle_right),
                                 'left_type': key.handle_left_type, 'right_type': key.handle_right_type}
                                for key in curve.keyframe_points],
                       'modifiers': [{'type': modifier.type} for modifier in curve.modifiers]}
                      for curve in _curves(action)], key=lambda row: (row['data_path'], row['array_index']))}


def native_weights_payload(body, rig):
    groups = {group.index: group.name for group in body.vertex_groups}
    return {'vertex_groups': [{groups[group.group]: float(group.weight) for group in vertex.groups}
                              for vertex in body.data.vertices],
            'bones': [{'name': bone.name, 'head_local': list(bone.head_local), 'tail_local': list(bone.tail_local),
                       'matrix_local': [list(row) for row in bone.matrix_local],
                       'parent': bone.parent.name if bone.parent else None} for bone in rig.data.bones],
            'body_matrix_world': [list(row) for row in body.matrix_world],
            'rig_matrix_world': [list(row) for row in rig.matrix_world],
            'modifiers': [{'type': modifier.type, 'name': modifier.name,
                          'target': 'DECLARED_RIG' if modifier.type == 'ARMATURE' and modifier.object == rig else None,
                          'enabled': modifier.show_viewport,
                          'preserve_volume': getattr(modifier, 'use_deform_preserve_volume', None),
                          'vertex_groups': getattr(modifier, 'use_vertex_groups', None),
                          'bone_envelopes': getattr(modifier, 'use_bone_envelopes', None)} for modifier in body.modifiers]}


def author_clip(rig, profile, specification):
    import bpy
    validate_motion_profile(profile, specification)
    expected_bones = {row['name'] for row in specification['bones']}
    actual_bones = {bone.name for bone in rig.data.bones} if rig.type == 'ARMATURE' else set()
    if rig.type != 'ARMATURE' or actual_bones != expected_bones:
        raise StudioError('Motion Action requires its exact derived rig bone inventory; missing='+
                          repr(sorted(expected_bones-actual_bones))+'; unexpected='+repr(sorted(actual_bones-expected_bones)))
    if rig.animation_data and rig.animation_data.nla_tracks:
        raise StudioError('Motion authoring does not admit mixed NLA context')
    rig.animation_data_create(); action = bpy.data.actions.new('A3D.Motion.'+profile['clip_id']+'.'+uuid.uuid4().hex)
    rig.animation_data.action = action
    for bone in rig.pose.bones:
        bone.rotation_mode = 'XYZ'; bone.rotation_euler = (0., 0., 0.)
        bone.location = (0., 0., 0.); bone.scale = (1., 1., 1.)
        if bone.constraints:
            raise StudioError('Declared motion clip requires an unconstrained derived rest rig')
    for track in profile['tracks']:
        bone = rig.pose.bones[track['bone']]; axis = 'XYZ'.index(track['axis'])
        for key in track['keys']:
            bone.rotation_euler[axis] = key['radians']
            bone.keyframe_insert('rotation_euler', index=axis, frame=key['frame'], group=bone.name)
    for curve in _curves(action):
        curve.extrapolation = 'CONSTANT'
        for key in curve.keyframe_points:
            key.interpolation = profile['interpolation']
    action['a3d_motion_profile_sha256'] = digest(profile)
    action['a3d_rig_specification_sha256'] = specification['cache_key']
    action['a3d_qualification'] = 'DECLARED_INSPECTION_MOTION_REQUIRES_REVIEW'
    return action


def evaluate_clip(body, rig, profile, specification, author=True):
    import bpy
    from blender.body_target import evaluated_mesh
    validate_motion_profile(profile, specification)
    if (len(body.modifiers) != 1 or body.modifiers[0].type != 'ARMATURE' or
            body.modifiers[0].object != rig or not body.modifiers[0].show_viewport or
            any(bone.constraints for bone in rig.pose.bones) or
            rig.animation_data and (rig.animation_data.nla_tracks or rig.animation_data.drivers)):
        raise StudioError('Motion requires the declared derived Armature without mixed modifiers, constraints or drivers')
    if abs(bpy.context.scene.unit_settings.scale_length-1.) > 1e-9:
        raise StudioError('Motion evaluation requires declared meter units')
    # Native quad tessellation can switch diagonals as an Armature deforms.
    # Keep the native rest-mesh triangulation as the collider's stable source
    # correspondence while still checking actual evaluated polygons/labels.
    body.data.calc_loop_triangles()
    source_faces = [list(face.vertices) for face in body.data.polygons]
    source_triangles = [list(triangle.vertices) for triangle in body.data.loop_triangles]
    source_regions = [value.value for value in body.data.attributes['.sculpt_face_set'].data]
    source_count = len(body.data.vertices)
    action = author_clip(rig, profile, specification) if author else rig.animation_data.action
    expected = {(rig.pose.bones[track['bone']].path_from_id('rotation_euler'), 'XYZ'.index(track['axis'])): track
                for track in profile['tracks']}
    actual = {(curve.data_path, curve.array_index): curve for curve in _curves(action)}
    if set(actual) != set(expected):
        raise StudioError('Motion Action channels changed from the declared clip')
    for identity, track in expected.items():
        curve = actual[identity]
        if (curve.modifiers or curve.mute or curve.extrapolation != 'CONSTANT' or
                len(curve.keyframe_points) != len(track['keys']) or
                any(abs(key.co[0]-source['frame']) > 1e-6 or abs(key.co[1]-source['radians']) > 1e-6 or
                    key.interpolation != profile['interpolation']
                    for key, source in zip(curve.keyframe_points, track['keys']))):
            raise StudioError('Motion Action keys changed from the declared clip')
    before_action = digest(action_payload(action)); before_weights = digest(native_weights_payload(body, rig))
    if (action.get('a3d_motion_profile_sha256') != digest(profile) or
            action.get('a3d_rig_specification_sha256') != specification['cache_key']):
        raise StudioError('Motion Action is not bound to this declared profile and rig')
    scene = bpy.context.scene; scene.render.fps = profile['fps']; samples = []
    topology = None
    for time in sample_times(profile):
        frame = math.floor(time); scene.frame_set(frame, subframe=time-frame)
        depsgraph = bpy.context.evaluated_depsgraph_get(); depsgraph.update()
        geometry, evaluated_triangles = evaluated_mesh(body, depsgraph, 1.)
        if (len(geometry['vertices_cm']) != source_count or geometry['faces'] != source_faces or
                geometry['face_sets'] != source_regions):
            raise StudioError('Animated body collider changed evaluated source vertices, polygons or region identities')
        triangles = source_triangles
        current_topology = digest([source_count, source_faces, source_triangles, source_regions])
        if topology is not None and topology != current_topology:
            raise StudioError('Animated body collider changed evaluated source topology')
        topology = current_topology
        points = geometry['vertices_cm']
        sample = {'time': time, 'topology_sha256': topology, 'vertices_cm': points,
                  'faces': geometry['faces'], 'triangles': triangles,
                  'evaluated_native_triangulation_sha256': digest(evaluated_triangles),
                  'collider_triangulation_policy': 'FIXED_NATIVE_REST_MESH_DIAGONALS',
                  'geometry_sha256': digest([points, geometry['faces']]),
                  'bounds_cm': [[min(point[i] for point in points) for i in range(3)],
                                [max(point[i] for point in points) for i in range(3)]]}
        # BVH is rebuilt from the actual evaluated native sample. It is never
        # serialized or reused for another body pose.
        tree = collider_tree(sample)
        sample['collider_tree_created'] = tree is not None
        samples.append(sample)
    if digest(action_payload(action)) != before_action or digest(native_weights_payload(body, rig)) != before_weights:
        raise StudioError('Action or weights changed while evaluating its collider clip')
    coverage = verify_sample_coverage(profile, samples)
    binding = motion_evidence_binding(profile, specification, before_action, before_weights, topology)
    return {'version': 1, 'status': coverage['status'], 'profile_sha256': digest(profile),
            'motion_binding': binding, 'action_sha256': before_action, 'weights_sha256': before_weights,
            'topology_sha256': topology, 'rig_specification_sha256': specification['cache_key'],
            'collider_triangulation_policy': 'FIXED_NATIVE_REST_MESH_DIAGONALS',
            'coverage': coverage, 'samples': samples, 'action_name': action.name,
            'qualification': 'EVALUATED_BODY_MOTION_SAMPLES_ONLY',
            'anatomical_review': 'REQUIRED', 'bone_axis_review': 'REQUIRED',
            'garment_contacts': 'NOT_EXECUTED', 'simulation': 'NOT_EXECUTED', 'fitting': 'NOT_EXECUTED'}


def collider_tree(sample):
    from mathutils.bvhtree import BVHTree
    from mathutils import Vector
    # Core geometry uses centimeters, including collider-tree queries.
    return BVHTree.FromPolygons([Vector(point) for point in sample['vertices_cm']], sample['triangles'], all_triangles=True)


def prepare_motion_inputs(project, body_target_receipt_path, motion_profile_path=None):
    """Admit exact generated artifacts without modifying native or project state."""
    receipt_path = inside(project.root, body_target_receipt_path); receipt = read_json(receipt_path)
    if receipt.get('status') != 'NATIVE_BODY_TARGET_MEASURED' or receipt.get('native_reopened') is not True:
        raise StudioError('Body motion requires an exact re-opened measured target-body receipt')
    payload = {key: value for key, value in receipt.items() if key != 'cache_key'}
    if receipt.get('cache_key') != digest(payload):
        raise StudioError('Native body target receipt changed')
    references = [receipt['artifact'], *receipt['artifacts'].values(), *receipt['evidence'].values()]
    for reference in references:
        if sha(inside(project.root, reference['path'])) != reference['sha256']:
            raise StudioError('Motion body input artifact changed: '+reference['path'])
    from a3d.body_target import target_descriptor
    descriptor = target_descriptor(project, receipt['evidence']['selection']['path'], receipt['evidence']['target']['path'])
    if descriptor['evidence'] != receipt['evidence']:
        raise StudioError('Motion body target selection provenance changed')
    native = read_json(inside(project.root, receipt['artifacts']['geometry']['path']))
    source = read_json(inside(project.root, receipt['artifacts']['source-geometry']['path']))
    profile = read_json(inside(project.root, receipt['artifacts']['profile']['path']))
    specification = target_rig_specification(source, descriptor['adapter'], descriptor['target']['orientation'], native, profile)
    motion = read_json(inside(project.root, motion_profile_path)) if motion_profile_path else None
    if motion is not None:
        validate_motion_profile(motion, specification)
    return {'body_receipt': receipt, 'body_receipt_sha256': sha(receipt_path),
            'specification': specification, 'motion': motion}


def _prepare_motion(project, body_target_receipt_path, motion_profile_path):
    import bpy
    from blender.body_source import data_ids, live_geometry
    from blender.mannequin_rig import create_derived_rig
    inputs = prepare_motion_inputs(project, body_target_receipt_path, motion_profile_path)
    original_ids = data_ids(); scene = bpy.context.scene; filepath = bpy.data.filepath
    frame = scene.frame_current; dirty = bpy.data.is_dirty; db_before = sha(project.db); live_before = live_geometry()
    token = uuid.uuid4().hex
    try:
        temporary = bpy.data.scenes.new('A3D.BodyMotion.'+token)
        temporary.unit_settings.system = 'METRIC'; temporary.unit_settings.scale_length = 1.
        artifact = inside(project.root, inputs['body_receipt']['artifact']['path'])
        with bpy.data.libraries.load(str(artifact), link=False) as (available, loaded):
            if len(available.objects) != 1 or available.armatures or available.actions:
                raise StudioError('Measured body target artifact must contain one static evaluated mesh')
            loaded.objects = list(available.objects)
        source = loaded.objects[0]; temporary.collection.objects.link(source)
        with bpy.context.temp_override(scene=temporary, view_layer=temporary.view_layers[0]):
            bpy.context.view_layer.update()
            body, rig = create_derived_rig(source, temporary.collection, inputs['specification'])
            motion = evaluate_clip(body, rig, inputs['motion'], inputs['specification'])
            directory = project.data/('outputs/body-motion-'+token); directory.mkdir(parents=True, exist_ok=False)
            target = directory/'body-motion.blend'; bpy.data.libraries.write(str(target), {body, rig}, fake_user=True)
            atomic_json(directory/'rig.json', inputs['specification']); atomic_json(directory/'samples.json', motion)
            result = {key: value for key, value in motion.items() if key != 'samples'}
            result.update(body_target_receipt={'path': body_target_receipt_path, 'sha256': inputs['body_receipt_sha256']},
                          motion_profile={'path': motion_profile_path, 'sha256': sha(inside(project.root, motion_profile_path))},
                          artifact={'path': target.relative_to(project.root).as_posix(), 'sha256': sha(target)},
                          samples_artifact={'path': (directory/'samples.json').relative_to(project.root).as_posix(), 'sha256': sha(directory/'samples.json')},
                          rig_artifact={'path': (directory/'rig.json').relative_to(project.root).as_posix(), 'sha256': sha(directory/'rig.json')},
                          live_scene_mutated=False, source_adapter_rebound=False, blender_version=bpy.app.version_string)
            result['cache_key'] = digest(result); receipt_path = directory/'receipt.json'; atomic_json(receipt_path, result)
            result['receipt'] = {'path': receipt_path.relative_to(project.root).as_posix(), 'sha256': sha(receipt_path)}
    finally:
        bpy.data.batch_remove(ids=data_ids()-original_ids)
    if (data_ids() != original_ids or bpy.context.scene != scene or bpy.data.filepath != filepath or
            scene.frame_current != frame or bpy.data.is_dirty != dirty or sha(project.db) != db_before or live_geometry() != live_before):
        raise StudioError('Body-motion artifact preparation changed live scene or canonical project state')
    return result


def prepare_body_motion(project_root, body_target_receipt_path, motion_profile_path):
    from a3d.store import Project
    return _prepare_motion(Project(project_root), body_target_receipt_path, motion_profile_path)
