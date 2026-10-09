"""Create UV/LOD variants from copied native IDs, preserving sewn source data."""
import math
import time
import uuid

from a3d.asset_finishing import assess_lod, finishing_descriptor, source_uv_identity
from a3d.core import StudioError, atomic_json, digest, sha
from blender.asset_export import (ExportBudgetReached, action_payloads, check_deadline,
                                 image_payloads, load_candidate, pack_candidate_images, rest_payload, uv_payload)


def smart_project(obj, uv, scene):
    """Use a declared Smart Project operation on one copied rigid mesh only."""
    import bpy
    view_layer = scene.view_layers[0]
    with bpy.context.temp_override(scene=scene, view_layer=view_layer):
        if bpy.context.mode != 'OBJECT':
            raise StudioError('Finishing requires an isolated object-mode operation')
        selected = {candidate for candidate in view_layer.objects if candidate.select_get(view_layer=view_layer)}
        active = view_layer.objects.active
        for candidate in selected:
            candidate.select_set(False, view_layer=view_layer)
        obj.select_set(True, view_layer=view_layer); view_layer.objects.active = obj
        layer = obj.data.uv_layers.get(uv['layer_name']) or obj.data.uv_layers.new(name=uv['layer_name'])
        obj.data.uv_layers.active_index = list(obj.data.uv_layers).index(layer)
        try:
            with bpy.context.temp_override(active_object=obj, object=obj, selected_objects=[obj], selected_editable_objects=[obj]):
                if bpy.ops.object.mode_set(mode='EDIT') != {'FINISHED'} or obj.mode != 'EDIT':
                    raise StudioError('Native rigid Smart Project could not enter edit mode on the copied mesh')
                # A temporary scene still shares the visible window. Its
                # edit_object and objects-in-mode context can point at that
                # window's original scene even after the copied mesh entered
                # edit mode. Bind the actual editable owners explicitly.
                with bpy.context.temp_override(edit_object=obj, objects_in_mode=[obj], objects_in_mode_unique_data=[obj]):
                    bpy.ops.mesh.select_all(action='SELECT')
                    result = bpy.ops.uv.smart_project(angle_limit=math.radians(uv['angle_limit_degrees']),
                                                      island_margin=uv['island_margin'], area_weight=0.,
                                                      correct_aspect=False, scale_to_bounds=True)
                if result != {'FINISHED'}:
                    raise StudioError('Native rigid Smart Project did not finish')
        finally:
            if obj.mode != 'OBJECT':
                with bpy.context.temp_override(active_object=obj, object=obj, selected_objects=[obj], selected_editable_objects=[obj]):
                    bpy.ops.object.mode_set(mode='OBJECT')
            obj.select_set(False, view_layer=view_layer)
            for candidate in selected:
                candidate.select_set(True, view_layer=view_layer)
            view_layer.objects.active = active
    values = [list(value.uv) for value in obj.data.uv_layers[uv['layer_name']].data]
    if len(values) != len(obj.data.loops) or any(not math.isfinite(v) for point in values for v in point):
        raise StudioError('Native rigid Smart Project produced incomplete or nonfinite UVs')
    return values


def _surface(obj, unit_scale_m):
    mesh = obj.data; mesh.calc_loop_triangles(); factor = 100 * unit_scale_m
    points = [[value * factor for value in obj.matrix_world @ vertex.co] for vertex in mesh.vertices]
    triangles = [list(triangle.vertices) for triangle in mesh.loop_triangles]
    centers = [[value * factor for value in obj.matrix_world @ polygon.center] for polygon in mesh.polygons]
    return {'points': points, 'triangles': triangles, 'centers': centers, 'face_count': len(mesh.polygons)}


def measured_surface_error(source, lod, unit_scale_m, sample_budget, deadline):
    from mathutils import Vector
    from mathutils.bvhtree import BVHTree
    a, b = _surface(source, unit_scale_m), _surface(lod, unit_scale_m)
    expected = len(a['points']) + len(a['centers']) + len(b['points']) + len(b['centers'])
    metrics = {'source_faces': a['face_count'], 'source_triangles': len(a['triangles']),
               'lod_faces': b['face_count'], 'lod_triangles': len(b['triangles']),
               'expected_samples': expected, 'executed_samples': 0, 'max_surface_error_cm': None}
    if not a['triangles'] or not b['triangles']:
        return metrics
    if expected > sample_budget:
        return metrics
    tree_a = BVHTree.FromPolygons([Vector(point) for point in a['points']], a['triangles'], all_triangles=True)
    tree_b = BVHTree.FromPolygons([Vector(point) for point in b['points']], b['triangles'], all_triangles=True)
    maximum = 0.
    for points, target in (([*a['points'], *a['centers']], tree_b), ([*b['points'], *b['centers']], tree_a)):
        for point in points:
            if metrics['executed_samples'] % 512 == 0:
                check_deadline(deadline)
            nearest = target.find_nearest(Vector(point))
            if nearest is None or nearest[3] is None or not math.isfinite(nearest[3]):
                raise StudioError('LOD symmetric surface query failed')
            maximum = max(maximum, nearest[3]); metrics['executed_samples'] += 1
    metrics['max_surface_error_cm'] = maximum
    return metrics


def create_lod(source, request, candidate, unit_scale_m, sample_budget, deadline):
    import bpy
    if source.data.shape_keys or source.modifiers or source.constraints:
        raise StudioError('Rigid LOD V1 requires an unmodified, unconstrained mesh without shape keys')
    if source.vertex_groups:
        raise StudioError('Rigged LOD requires qualified weight/topology remapping')
    scene = candidate['scene']; clone = source.copy(); clone.data = source.data.copy()
    clone.name = 'A3D.LOD.' + request['id']; scene.collection.objects.link(clone)
    modifier = clone.modifiers.new('A3D.DeclaredLOD', 'DECIMATE')
    modifier.decimate_type = 'COLLAPSE'; modifier.ratio = request['ratio']
    modifier.use_collapse_triangulate = True; modifier.use_symmetry = False
    if not math.isclose(modifier.ratio, request['ratio'], rel_tol=2e-6, abs_tol=2e-6):
        raise StudioError('Native LOD ratio differs from its declared budget')
    with bpy.context.temp_override(scene=scene, view_layer=scene.view_layers[0]):
        scene.frame_set(scene.frame_current); depsgraph = bpy.context.evaluated_depsgraph_get(); depsgraph.update()
        evaluated = clone.evaluated_get(depsgraph)
        mesh = bpy.data.meshes.new_from_object(evaluated, preserve_all_data_layers=True, depsgraph=depsgraph)
        if mesh is None:
            raise StudioError('Native LOD produced no evaluated mesh')
        previous = clone.data; clone.modifiers.remove(modifier); clone.data = mesh
        if previous.users == 0:
            bpy.data.meshes.remove(previous)
        scene.view_layers[0].update()
    metrics = measured_surface_error(source, clone, unit_scale_m, sample_budget, deadline)
    assessment = assess_lod(request, metrics)
    assessment['native_object_name'] = clone.name
    assessment['input_geometry_sha256'] = digest(_surface(source, unit_scale_m))
    assessment['output_geometry_sha256'] = digest(_surface(clone, unit_scale_m))
    clone['a3d_lod_source_candidate'] = digest(candidate['source_ref'])
    clone['a3d_lod_request_sha256'] = digest(request)
    clone['a3d_qualification'] = 'LOD_GEOMETRY_VARIANT_REQUIRES_REVIEW'
    return clone, assessment


def prepare_asset_finishing(project_root, profile_path):
    import bpy
    from a3d.store import Project
    from blender.body_source import data_ids, live_geometry
    project = Project(project_root); inputs = finishing_descriptor(project, profile_path); profile = inputs['profile']
    if bpy.context.mode != 'OBJECT':
        raise StudioError('Finishing requires object mode to preserve the current editing context')
    original = data_ids(); live_before = live_geometry(); db_before = sha(project.db)
    live_scene = bpy.context.scene; frame = live_scene.frame_current; filepath = bpy.data.filepath
    selected = set(bpy.context.selected_objects); active = bpy.context.view_layer.objects.active
    started = time.monotonic(); deadline = started + profile['budgets']['max_seconds']
    directory = project.data / ('outputs/asset-finishing-' + uuid.uuid4().hex); directory.mkdir(parents=True, exist_ok=False)
    native_profile = dict(profile, clips=[])
    result = {'version': 1, 'candidate': profile['source_ref'], 'profile': inputs['profile_ref'],
              'source_preserved': True, 'uv_operations': [], 'lods': [],
              'animation_qualification': 'NOT_QUALIFIED', 'engine_qualification': 'NOT_QUALIFIED',
              'fitting': 'NOT_GRANTED', 'artistic_review': 'REQUIRED'}
    try:
        check_deadline(deadline); candidate = load_candidate(inputs['source'], native_profile, 'Finishing')
        candidate['source_ref'] = profile['source_ref']; scene = candidate['scene']; scene.frame_set(profile['reference_frame'])
        resources = pack_candidate_images(project, candidate, profile, inputs['source'])
        before = rest_payload(candidate); actions_before = action_payloads(candidate)
        remaining = profile['budgets']['max_error_samples']
        for operation in profile['operations']:
            check_deadline(deadline); obj = candidate['objects'][operation['object_name']]
            if obj.type != 'MESH':
                raise StudioError('UV/LOD finishing requires the declared source mesh')
            if (operation['role'] == 'RIGID' and (obj.get('a3d_role') in ('simulation', 'sewn', 'pattern') or
                    obj.data.shape_keys and any(key.name in ('Placement', 'FlatRest', 'SewnRest') for key in obj.data.shape_keys.key_blocks))):
                raise StudioError('A sewn source cannot be reclassified as a rigid Smart Project/LOD target')
            uv = operation['uv']; faces = [list(face.vertices) for face in obj.data.polygons]
            prior_uv = uv_payload(obj.data)
            if uv['method'] == 'PRESERVE_SOURCE':
                if uv['layer_name'] not in prior_uv or source_uv_identity(faces, prior_uv[uv['layer_name']]) != uv['source_uv_sha256']:
                    raise StudioError('Source sewn/rigid UV map is absent or differs from its exact declared mapping')
                values = prior_uv[uv['layer_name']]
            else:
                values = smart_project(obj, uv, scene)
                if any(layer != uv['layer_name'] and uv_payload(obj.data).get(layer) != values for layer, values in prior_uv.items()):
                    raise StudioError('Rigid UV operation modified an undeclared UV layer')
            result['uv_operations'].append({'object_name': operation['object_name'], 'role': operation['role'],
                                            'method': uv['method'], 'layer_name': uv['layer_name'],
                                            'uv_sha256': source_uv_identity(faces, values),
                                            'source_uv_preserved': uv['method'] == 'PRESERVE_SOURCE', 'parameters': uv})
            current = rest_payload(candidate)[operation['object_name']]
            expected = dict(before[operation['object_name']]); expected['mesh'] = dict(expected['mesh'], uv=current['mesh']['uv'])
            if current != expected:
                raise StudioError('UV finishing changed geometry, source topology, weights or rest pose')
            for request in operation['lods']:
                check_deadline(deadline)
                clone, assessment = create_lod(obj, request, candidate, profile['unit_scale_m'], remaining, deadline)
                remaining -= assessment['metrics']['executed_samples']
                candidate['objects'][operation['object_name'] + ':lod:' + request['id']] = clone
                result['lods'].append(assessment)
        after = rest_payload(candidate)
        if action_payloads(candidate) != actions_before:
            raise StudioError('Finishing changed source Actions')
        check_deadline(deadline); target = directory / 'asset-finishing.blend'
        bpy.data.libraries.write(str(target), {scene, *candidate['actions'].values(), *candidate['images'].values()}, fake_user=True)
        mapping = {key: obj.name for key, obj in candidate['objects'].items()}
        action_mapping = {key: action.name for key, action in candidate['actions'].items()}
        image_mapping = {key: image.name for key, image in candidate['images'].items()}
        reload_profile = dict(native_profile, object_names=list(mapping.values()), dependency_names=[],
                              action_names=list(action_mapping.values()), embedded_image_names=list(image_mapping.values()), resources=[])
        reopened = load_candidate(target, reload_profile, 'FinishingReimport', scene_name=scene.name)
        reopened['objects'] = {key: reopened['objects'][name] for key, name in mapping.items()}
        reopened['actions'] = {key: reopened['actions'][name] for key, name in action_mapping.items()}
        reopened['images'] = {key: reopened['images'][name] for key, name in image_mapping.items()}
        reopened['scene'].frame_set(profile['reference_frame'])
        if rest_payload(reopened) != after or action_payloads(reopened) != actions_before or image_payloads(reopened) != resources:
            raise StudioError('Finishing native reimport changed UVs, geometry, Actions or packed resources')
        comparison_path = directory / 'comparison.json'
        atomic_json(comparison_path, {'candidate': profile['source_ref'], 'source': before, 'variant': after,
                                      'actions': actions_before, 'resources': resources, 'native_reimport': 'MATCHED'})
        status = ('INCOMPLETE' if any(row['status'] == 'INCOMPLETE' for row in result['lods']) else
                  'NEEDS_CORRECTION' if any(row['status'] != 'LOD_GEOMETRY_WITHIN_BUDGET' for row in result['lods']) else
                  'ASSET_FINISHING_PREPARED')
        result.update(status=status, native_reopened=True, object_mapping=mapping, action_mapping=action_mapping,
                      image_mapping=image_mapping, packed_resources=resources,
                      artifact={'path': target.relative_to(project.root).as_posix(), 'sha256': sha(target)},
                      comparison_artifact={'path': comparison_path.relative_to(project.root).as_posix(), 'sha256': sha(comparison_path)},
                      sampled_surface_error_budget_remaining=remaining, qualification='REVERSIBLE_UV_AND_RIGID_LOD_VARIANTS_ONLY')
    except ExportBudgetReached as error:
        result.update(status='INCOMPLETE', stopped=str(error), native_reopened=False, qualification='NOT_QUALIFIED')
    finally:
        bpy.data.batch_remove(ids=data_ids() - original)
        if (data_ids() != original or live_geometry() != live_before or sha(project.db) != db_before or
                bpy.context.scene != live_scene or live_scene.frame_current != frame or bpy.data.filepath != filepath or
                set(bpy.context.selected_objects) != selected or bpy.context.view_layer.objects.active != active):
            raise StudioError('Finishing changed the production context or canonical project state')
        if sha(inputs['source']) != profile['source_ref']['sha256']:
            raise StudioError('Finishing source candidate changed during execution')
    result['elapsed_seconds'] = time.monotonic() - started; result['blender_version'] = bpy.app.version_string
    result['cache_key'] = digest(result); path = directory / 'receipt.json'; atomic_json(path, result)
    return dict(result, receipt={'path': path.relative_to(project.root).as_posix(), 'sha256': sha(path)})
