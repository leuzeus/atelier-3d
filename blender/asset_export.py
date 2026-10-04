"""Pack a native animation candidate and actually reimport it in isolation.

All loading and sampling occurs in temporary scenes. Originals and canonical
project state stay untouched; no motion, fitting or artistic PASS is invented.
"""
import hashlib
import time
import uuid
from pathlib import Path

from a3d.core import StudioError, atomic_json, digest, inside, sha
from a3d.export_profiles import clip_tracks, compare_native_samples, export_descriptor, export_sample_times, motion_qualification


class ExportBudgetReached(StudioError):
    pass


def check_deadline(deadline):
    if time.monotonic() > deadline:
        raise ExportBudgetReached('TIME_BUDGET')


def candidate_animation_owners(objects):
    """Return the exact object and native Key owners, including unanimated objects."""
    rows = objects.items() if isinstance(objects, dict) else ((obj.name, obj) for obj in objects)
    owners = {}
    for name, obj in rows:
        owners[(name, 'OBJECT')] = obj
        keys = getattr(getattr(obj, 'data', None), 'shape_keys', None)
        if keys is not None:
            owners[(name, 'SHAPE_KEYS')] = keys
    return owners


def candidate_action_names(objects):
    """Discover actual object and Key Actions without treating either as qualified."""
    return sorted({owner.animation_data.action.name
                   for owner in candidate_animation_owners(objects).values()
                   if owner.animation_data and owner.animation_data.action})


def load_candidate(source, profile, label, scene_name=None):
    """Load declared IDs and reject implicit undeclared object/Action/image IDs."""
    import bpy
    from blender.body_source import data_ids
    baseline = data_ids()
    object_names = [*profile['object_names'], *profile['dependency_names']]
    image_names = [*profile['embedded_image_names'], *[row['datablock_name'] for row in profile['resources']]]
    with bpy.data.libraries.load(str(source), link=False) as (available, loaded):
        for key, names in (('objects', object_names), ('actions', profile['action_names']), ('images', image_names)):
            if not set(names) <= set(getattr(available, key)):
                raise StudioError('Candidate is missing declared ' + key)
            # Blender replaces the strings in assigned lists with loaded ID
            # objects on context exit. Retain our source names and immutable
            # profile lists by handing the loader a separate disposable list.
            setattr(loaded, key, list(names))
        if scene_name:
            if scene_name not in available.scenes:
                raise StudioError('Exported native scene is missing')
            loaded.scenes = [scene_name]
    objects = dict(zip(object_names, loaded.objects, strict=True))
    actions = dict(zip(profile['action_names'], loaded.actions, strict=True))
    images = dict(zip(image_names, loaded.images, strict=True))
    added = data_ids() - baseline
    for kind, declared in ((bpy.types.Object, objects), (bpy.types.Action, actions), (bpy.types.Image, images)):
        if {block for block in added if isinstance(block, kind)} != set(declared.values()):
            raise StudioError('Candidate has undeclared native dependencies: ' + kind.__name__)
    for block in added:
        if block.library:
            raise StudioError('Candidate retains a linked library dependency')
        animation = getattr(block, 'animation_data', None)
        if animation and (animation.drivers or animation.nla_tracks):
            raise StudioError('Native export V1 requires driver-free Actions without mixed NLA')
        if isinstance(block, (bpy.types.CacheFile, bpy.types.Sound, bpy.types.MovieClip, bpy.types.Volume)):
            raise StudioError('Native external cache/audio/movie/volume resource requires an unsupported export profile')
        if isinstance(block, bpy.types.VectorFont) and block.filepath and block.filepath != '<builtin>':
            raise StudioError('External fonts require an unsupported export profile')
    for obj in objects.values():
        if obj.type not in ('MESH', 'ARMATURE', 'EMPTY'):
            raise StudioError('Native export V1 supports declared meshes, armatures and empties')
        if any(modifier.type in ('CLOTH', 'FLUID', 'SOFT_BODY', 'PARTICLE_SYSTEM', 'MESH_CACHE', 'MESH_SEQUENCE_CACHE') for modifier in obj.modifiers):
            raise StudioError('Native simulation/cache persistence must be qualified before animation export')
    for (_, target), owner in candidate_animation_owners(objects).items():
        animation = owner.animation_data
        if animation and animation.action:
            slot = animation.action_slot
            if (animation.action not in actions.values() or slot is None or
                    not any(candidate == slot for candidate in animation.action.slots) or
                    slot.target_id_type != ('KEY' if target == 'SHAPE_KEYS' else 'OBJECT')):
                raise StudioError('Native animation owner requires its exact declared Action and target slot')
    first = min([profile['reference_frame'], *[clip['frame_start'] for clip in profile['clips']]])
    last = max([profile['reference_frame'], *[clip['frame_end'] for clip in profile['clips']]])
    if scene_name:
        scene = loaded.scenes[0]
        if (set(scene.objects) != set(objects.values()) or scene.unit_settings.system != 'METRIC' or
                abs(scene.unit_settings.scale_length - profile['unit_scale_m']) > 1e-7 or
                scene.render.fps != profile['fps'] or scene.render.fps_base != 1. or
                scene.frame_start != first or scene.frame_end != last):
            raise StudioError('Native reopened scene dependencies, units or animation range changed')
    else:
        scene = bpy.data.scenes.new('A3D.' + label + '.' + uuid.uuid4().hex)
        scene.unit_settings.system = 'METRIC'; scene.unit_settings.scale_length = profile['unit_scale_m']
        scene.render.fps = profile['fps']; scene.render.fps_base = 1.
        scene.frame_start = first; scene.frame_end = last
        for obj in objects.values():
            scene.collection.objects.link(obj)
    return {'scene': scene, 'objects': objects, 'actions': actions, 'images': images}


def pack_candidate_images(project, candidate, profile, source):
    """Pack only loaded copies, preserving the original source/resource bytes."""
    declarations = {row['datablock_name']: row for row in profile['resources']}
    for name, image in candidate['images'].items():
        if image.source not in ('FILE', 'GENERATED'):
            raise StudioError('Image sequence/movie/UDIM export is not supported: ' + name)
        if name in declarations:
            reference = declarations[name]['file_ref']; expected = inside(project.root, reference['path'])
            if image.packed_file:
                if hashlib.sha256(bytes(image.packed_file.data)).hexdigest() != reference['sha256']:
                    raise StudioError('Packed native image contradicts its declared source resource: ' + name)
            else:
                path = image.filepath
                resolved = (source.parent / path[2:] if path.startswith('//') else Path(path)).resolve(strict=True)
                if resolved != expected or sha(resolved) != reference['sha256']:
                    raise StudioError('Native image filepath contradicts its exact declared resource: ' + name)
                image.filepath = str(expected)
                image.pack()
        elif not image.packed_file:
            if image.source != 'GENERATED':
                raise StudioError('Embedded image declaration requires packed native data: ' + name)
            image.pack()
        if image.packed_file is None:
            raise StudioError('Native image packing did not produce persistent bytes: ' + name)
    return image_payloads(candidate)


def image_payloads(candidate):
    result = {}
    for name, image in candidate['images'].items():
        if image.packed_file is None:
            raise StudioError('Reimported native image is not packed: ' + name)
        result[name] = {'packed_sha256': hashlib.sha256(bytes(image.packed_file.data)).hexdigest(),
                        'size': list(image.size), 'colorspace': image.colorspace_settings.name,
                        'alpha_mode': image.alpha_mode}
    return result


def uv_payload(mesh):
    return {layer.name: [list(value.uv) for value in layer.data] for layer in mesh.uv_layers}


def _native_value(value, identities):
    import bpy
    if isinstance(value, bpy.types.ID):
        if value not in identities:
            raise StudioError('Native dependency does not belong to the declared candidate: ' + value.name)
        return {'id': identities[value]}
    if isinstance(value, (str, bool, int, float)) or value is None:
        return value
    if hasattr(value, '__iter__'):
        return [_native_value(item, identities) for item in value]
    raise StudioError('Unsupported native dependency property')


def _shader_tree(tree, identities, visited=None):
    visited = set() if visited is None else visited
    if tree in visited:
        raise StudioError('Recursive shader node groups require a dedicated export profile')
    visited = visited | {tree}; nodes = []
    for node in tree.nodes:
        row = {'name': node.name, 'type': node.bl_idname,
               'inputs': [{'identifier': socket.identifier, 'value': _native_value(socket.default_value, identities)}
                          for socket in node.inputs if hasattr(socket, 'default_value')], 'parameters': {}}
        for name in ('image', 'object', 'attribute_name', 'uv_map', 'interpolation', 'projection', 'extension',
                     'operation', 'blend_type', 'data_type', 'clamp', 'use_clamp', 'space', 'vector_type'):
            if hasattr(node, name):
                row['parameters'][name] = _native_value(getattr(node, name), identities)
        if getattr(node, 'node_tree', None):
            row['group'] = _shader_tree(node.node_tree, identities, visited)
        nodes.append(row)
    links = [[link.from_node.name, link.from_socket.identifier, link.to_node.name, link.to_socket.identifier] for link in tree.links]
    return {'nodes': nodes, 'links': sorted(links)}


def _mesh_attributes(mesh):
    result = {}
    for attribute in mesh.attributes:
        if attribute.name in mesh.uv_layers or attribute.name == 'position' or attribute.name.startswith('.') and attribute.name != '.sculpt_face_set':
            continue
        values = []
        for item in attribute.data:
            field = next((key for key in ('value', 'vector', 'color') if hasattr(item, key)), None)
            if field is None:
                raise StudioError('Native mesh attribute serialization is unsupported: ' + attribute.name)
            value = getattr(item, field)
            values.append(list(value) if hasattr(value, '__iter__') and not isinstance(value, str) else value)
        result[attribute.name] = {'domain': attribute.domain, 'data_type': attribute.data_type, 'values': values}
    return result


def rest_payload(candidate):
    """Preserve source topology, UVs, weights, bone rest pose and RNA dependencies."""
    import bpy
    identities = {obj: 'OBJECT:' + name for name, obj in candidate['objects'].items()}
    identities.update({action: 'ACTION:' + name for name, action in candidate['actions'].items()})
    identities.update({image: 'IMAGE:' + name for name, image in candidate['images'].items()})
    for obj in candidate['objects'].values():
        if obj.data:
            identities[obj.data] = 'DATA:' + identities[obj]
            if getattr(obj.data, 'shape_keys', None) is not None:
                identities[obj.data.shape_keys] = 'KEY:' + identities[obj]
        for index, slot in enumerate(obj.material_slots):
            if slot.material:
                identities[slot.material] = 'MATERIAL:' + identities[obj] + ':' + str(index)
    result = {}
    for name, obj in candidate['objects'].items():
        row = {'type': obj.type, 'matrix_local': [list(vector) for vector in obj.matrix_local],
               'parent': _native_value(obj.parent, identities), 'parent_type': obj.parent_type,
               'parent_bone': obj.parent_bone, 'matrix_parent_inverse': [list(vector) for vector in obj.matrix_parent_inverse],
               'modifiers': [], 'constraints': [], 'action': None}
        row['materials'] = []
        for slot in obj.material_slots:
            material = slot.material
            row['materials'].append(None if material is None else {
                'identity': identities[material], 'link': slot.link, 'use_nodes': material.use_nodes,
                'diffuse_color': list(material.diffuse_color), 'metallic': material.metallic, 'roughness': material.roughness,
                'shader': _shader_tree(material.node_tree, identities) if material.use_nodes and material.node_tree else None})
        if obj.animation_data and obj.animation_data.action:
            row['action'] = _native_value(obj.animation_data.action, identities)
            row['slot'] = obj.animation_data.action_slot.identifier if obj.animation_data.action_slot else None
        for key in ('modifiers', 'constraints'):
            for block in getattr(obj, key):
                properties = {}
                for prop in block.bl_rna.properties:
                    if prop.identifier in ('rna_type', 'name') or prop.is_readonly:
                        continue
                    if prop.type in ('BOOLEAN', 'INT', 'FLOAT', 'STRING', 'ENUM', 'POINTER'):
                        value = getattr(block, prop.identifier)
                        # Non-ID pointer collections (e.g. curve mapping) need
                        # a dedicated profile instead of an incomplete digest.
                        if prop.type == 'POINTER' and value is not None and not isinstance(value, bpy.types.ID):
                            raise StudioError('Unsupported native modifier/constraint pointer: ' + prop.identifier)
                        properties[prop.identifier] = _native_value(value, identities)
                row[key].append({'type': block.type, 'properties': properties})
        if obj.type == 'MESH':
            mesh = obj.data
            groups = {group.index: group.name for group in obj.vertex_groups}
            row['mesh'] = {'vertices': [list(vertex.co) for vertex in mesh.vertices],
                           'faces': [list(face.vertices) for face in mesh.polygons], 'uv': uv_payload(mesh),
                           'attributes': _mesh_attributes(mesh),
                           'weights': [{groups[group.group]: group.weight for group in vertex.groups} for vertex in mesh.vertices],
                           'shape_keys': [{"name": key.name, "value": key.value,
                                           "relative_key": key.relative_key.name,
                                           "interpolation": key.interpolation, "mute": key.mute,
                                           "slider_min": key.slider_min, "slider_max": key.slider_max,
                                           "vertex_group": key.vertex_group, "frame": key.frame,
                                           "coordinates": [list(point.co) for point in key.data]}
                                          for key in mesh.shape_keys.key_blocks] if mesh.shape_keys else []}
            if mesh.shape_keys:
                keys = mesh.shape_keys; animation = keys.animation_data
                row['mesh']['shape_key_settings'] = {'use_relative': keys.use_relative, 'eval_time': keys.eval_time,
                    'action': _native_value(animation.action, identities) if animation and animation.action else None,
                    'slot': animation.action_slot.identifier if animation and animation.action_slot else None}
        if obj.type == 'ARMATURE':
            row['bones'] = [{'name': bone.name, 'parent': bone.parent.name if bone.parent else None,
                             'matrix_local': [list(vector) for vector in bone.matrix_local],
                             'use_deform': bone.use_deform} for bone in obj.data.bones]
            if any(bone.constraints for bone in obj.pose.bones):
                raise StudioError('Pose-bone constraints require a dedicated persistent export contract')
        result[name] = row
    return result


def action_payloads(candidate):
    from blender.body_motion import action_payload
    actions = {}
    for name, action in candidate['actions'].items():
        if any(curve.modifiers for layer in action.layers for strip in layer.strips if strip.type == 'KEYFRAME'
               for bag in strip.channelbags for curve in bag.fcurves):
            raise StudioError('Action F-curve modifiers require explicit export serialization support')
        actions[name] = action_payload(action)
    return actions


def assign_clip(candidate, clip):
    owners = candidate_animation_owners(candidate['objects']); prepared = []
    for track in clip_tracks(clip):
        target = track['animation_target']; owner = owners.get((track['object_name'], target))
        action = candidate['actions'][track['action_name']]
        if owner is None:
            raise StudioError('Export clip animation target is absent from the exact candidate')
        slots = [slot for slot in action.slots if slot.identifier == track['slot_identifier'] and
                 slot.target_id_type == ('KEY' if target == 'SHAPE_KEYS' else 'OBJECT')]
        if len(slots) != 1:
            raise StudioError('Export clip requires its exact native Action slot')
        if track.get('action_sha256') is not None:
            from blender.body_motion import action_payload
            if digest(action_payload(action)) != track['action_sha256']:
                raise StudioError('Export clip requires its exact native Action content')
        prepared.append((owner, action, slots[0]))
    for owner, action, slot in prepared:
        owner.animation_data_create(); owner.animation_data.action = action; owner.animation_data.action_slot = slot


def native_samples(candidate, profile, deadline):
    import bpy
    scene = candidate['scene']; snapshots = []
    owners = candidate_animation_owners(candidate['objects'])
    initial = {identity: (owner.animation_data.action, owner.animation_data.action_slot) if owner.animation_data else (None, None)
               for identity, owner in owners.items()}
    def restore_actions():
        for identity, owner in owners.items():
            action, slot = initial[identity]
            if owner.animation_data:
                owner.animation_data.action = action
                if action and slot:
                    owner.animation_data.action_slot = slot
    def capture(clip_id, frame):
        check_deadline(deadline); scene.frame_set(frame)
        depsgraph = bpy.context.evaluated_depsgraph_get(); depsgraph.update()
        meshes = {}
        for name, obj in candidate['objects'].items():
            if obj.type != 'MESH':
                continue
            evaluated = obj.evaluated_get(depsgraph); mesh = evaluated.to_mesh()
            try:
                points = [[float(value)*100*profile['unit_scale_m'] for value in evaluated.matrix_world@vertex.co]
                          for vertex in mesh.vertices]
                faces = [list(face.vertices) for face in mesh.polygons]
                if not points or not faces:
                    raise StudioError('Export requires nonempty evaluated source meshes: ' + name)
                row = {'vertices_cm': points, 'faces': faces}
                labels = mesh.attributes.get('.sculpt_face_set')
                if labels is not None:
                    if labels.domain != 'FACE' or labels.data_type != 'INT' or len(labels.data) != len(faces):
                        raise StudioError('Export source face-region identities changed: ' + name)
                    row['face_sets'] = [value.value for value in labels.data]
                meshes[name] = row
            finally:
                evaluated.to_mesh_clear()
        if not meshes:
            raise StudioError('Native asset export requires an evaluated candidate mesh')
        snapshots.append({'clip_id': clip_id, 'time': frame, 'meshes': meshes})
    with bpy.context.temp_override(scene=scene, view_layer=scene.view_layers[0]):
        try:
            capture('reference', profile['reference_frame'])
            for clip in profile['clips']:
                assign_clip(candidate, clip)
                for frame in export_sample_times(clip):
                    capture(clip['id'], frame)
                restore_actions()
        finally:
            restore_actions()
            scene.frame_set(profile['reference_frame'])
    return snapshots


def export_blender_animation(project_root, profile_path):
    import bpy
    from a3d.store import Project
    from blender.body_source import data_ids, live_geometry
    project = Project(project_root); inputs = export_descriptor(project, profile_path); profile = inputs['profile']
    original = data_ids(); before = live_geometry(); db_sha = sha(project.db)
    original_scene = bpy.context.scene; filepath = bpy.data.filepath
    frame = original_scene.frame_current; selected = set(bpy.context.selected_objects); active = bpy.context.view_layer.objects.active
    started = time.monotonic(); deadline = started + profile['budgets']['max_seconds']
    directory = project.data / ('outputs/asset-export-' + uuid.uuid4().hex); directory.mkdir(parents=True, exist_ok=False)
    result = {'version': 1, 'candidate': profile['source_ref'], 'profile': inputs['profile_ref'],
              'destination': 'blender_animation', 'original_preserved': True, 'engine_qualification': 'NOT_QUALIFIED',
              'artistic_review': 'REQUIRED', 'fitting': 'NOT_GRANTED', 'resources': [row['file_ref'] for row in profile['resources']]}
    try:
        check_deadline(deadline); candidate = load_candidate(inputs['source'], profile, 'Export')
        resource_payload = pack_candidate_images(project, candidate, profile, inputs['source'])
        before_samples = native_samples(candidate, profile, deadline)
        before_rest = rest_payload(candidate); before_actions = action_payloads(candidate)
        blend = directory / 'asset.blend'; check_deadline(deadline)
        bpy.data.libraries.write(str(blend), {candidate['scene'], *candidate['actions'].values(), *candidate['images'].values()}, fake_user=True)
        result['artifact'] = {'path': blend.relative_to(project.root).as_posix(), 'sha256': sha(blend)}
        mapping = {key: obj.name for key, obj in candidate['objects'].items()}
        action_mapping = {key: action.name for key, action in candidate['actions'].items()}
        image_mapping = {key: image.name for key, image in candidate['images'].items()}
        reimport_profile = dict(profile, object_names=[mapping[name] for name in profile['object_names']],
                                dependency_names=[mapping[name] for name in profile['dependency_names']],
                                action_names=[action_mapping[name] for name in profile['action_names']],
                                embedded_image_names=[image_mapping[name] for name in candidate['images']], resources=[])
        check_deadline(deadline); reopened = load_candidate(blend, reimport_profile, 'Reimport', scene_name=candidate['scene'].name)
        reopened['objects'] = {name: reopened['objects'][mapping[name]] for name in mapping}
        reopened['actions'] = {name: reopened['actions'][action_mapping[name]] for name in action_mapping}
        reopened['images'] = {name: reopened['images'][image_mapping[name]] for name in image_mapping}
        after_samples = native_samples(reopened, profile, deadline)
        comparison = compare_native_samples(before_samples, after_samples, profile['geometry_tolerance_cm'])
        if rest_payload(reopened) != before_rest or action_payloads(reopened) != before_actions or image_payloads(reopened) != resource_payload:
            raise StudioError('Native reimport changed rest geometry, UVs, rig, Actions or packed resources')
        actions_sha = {name: digest(value) for name, value in before_actions.items()}
        qualification = motion_qualification(profile, inputs['receipts'], actions_sha, before_samples[0]['meshes'])
        snapshots = {'candidate': profile['source_ref'], 'rest': before_rest, 'actions': before_actions,
                     'packed_images': resource_payload, 'samples_before': before_samples, 'samples_after': after_samples,
                     'comparison': comparison}
        snapshots_path = directory / 'comparison.json'; atomic_json(snapshots_path, snapshots)
        result.update(status='BLENDER_EXPORT_REOPENED', reimport='EXECUTED', native_comparison=comparison,
                      snapshots_artifact={'path': snapshots_path.relative_to(project.root).as_posix(), 'sha256': sha(snapshots_path)},
                      object_mapping=mapping, action_mapping=action_mapping, packed_resources=resource_payload,
                      clips_executed=qualification['clips_executed'], animation_qualification=qualification['status'],
                      motion_qualification=qualification, candidate_binding=digest([before_rest, before_actions, resource_payload]))
    except ExportBudgetReached as error:
        result.update(status='INCOMPLETE', reimport='NOT_EXECUTED', stopped=str(error), clips_executed=[], animation_qualification='NOT_QUALIFIED')
    finally:
        bpy.data.batch_remove(ids=data_ids() - original)
        if (data_ids() != original or live_geometry() != before or sha(project.db) != db_sha or
                bpy.context.scene != original_scene or original_scene.frame_current != frame or bpy.data.filepath != filepath or
                set(bpy.context.selected_objects) != selected or bpy.context.view_layer.objects.active != active):
            raise StudioError('Native export changed the production context or canonical state')
        if sha(inputs['source']) != profile['source_ref']['sha256']:
            raise StudioError('Export source candidate changed during execution')
    result['elapsed_seconds'] = time.monotonic() - started; result['blender_version'] = bpy.app.version_string
    result['cache_key'] = digest(result); path = directory / 'receipt.json'; atomic_json(path, result)
    return dict(result, receipt={'path': path.relative_to(project.root).as_posix(), 'sha256': sha(path)})
