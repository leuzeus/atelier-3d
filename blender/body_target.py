"""Native measured target-body artifact, created in an isolated temporary scene.

The live scene and source libraries are preserved. The artifact is an evaluated
mesh copy; no animation rig, collision envelope or garment fitting is qualified.
"""
import copy
import math
import uuid

from a3d.core import StudioError, atomic_json, digest, sha


def evaluated_mesh(obj, depsgraph, unit_scale_m):
    evaluated = obj.evaluated_get(depsgraph)
    mesh = evaluated.to_mesh()
    try:
        points = [[float(x)*unit_scale_m*100 for x in evaluated.matrix_world@vertex.co]
                  for vertex in mesh.vertices]
        faces = [list(face.vertices) for face in mesh.polygons]
        labels = mesh.attributes.get('.sculpt_face_set')
        if not labels or labels.domain != 'FACE' or labels.data_type != 'INT':
            raise StudioError('Body target source requires exact source face-region identities')
        if not points or not faces or any(not math.isfinite(x) for point in points for x in point):
            raise StudioError('Body target source has empty or invalid evaluated geometry')
        mesh.calc_loop_triangles()
        return {'vertices_cm': points, 'faces': faces,
                'face_sets': [value.value for value in labels.data]}, [list(t.vertices) for t in mesh.loop_triangles]
    finally:
        evaluated.to_mesh_clear()


def _reference(project, path):
    return {'path': path.relative_to(project.root).as_posix(), 'sha256': sha(path)}


def _prepare(project, selection_path, target_path):
    import bpy
    from a3d.body_target import prepare_target_geometry, target_descriptor
    from a3d.anatomy_profile import profile_mesh
    from a3d.shoulder_surface import measured_surface_shoulders
    from a3d.head_surface import head_face_ids, measured_head_surface
    from blender.body_source import data_ids, live_geometry
    descriptor = target_descriptor(project, selection_path, target_path)
    selection, target, source = descriptor['selection'], descriptor['target'], descriptor['source']
    names = set(selection['meshes'])|set(selection['dependencies'])
    if any(bpy.data.objects.get(name) for name in names):
        raise StudioError('Selected body source names already exist in the live scene')
    original_ids = data_ids(); live_scene = bpy.context.scene
    original_frame = live_scene.frame_current; original_path = bpy.data.filepath
    original_dirty = bpy.data.is_dirty; database_sha = sha(project.db); live_sha = live_geometry()
    token = uuid.uuid4().hex; result = None
    try:
        with bpy.data.libraries.load(str(source), link=False) as (available, loaded):
            if not names <= set(available.objects):
                raise StudioError('Selected body source objects are missing')
            loaded.objects = sorted(names)
        added = set(bpy.data.objects)-{block for block in original_ids if isinstance(block, bpy.types.Object)}
        if {obj.name for obj in added} != names:
            raise StudioError('Selected body has undeclared object dependencies')
        objects = {obj.name: obj for obj in added}; loaded_ids = data_ids()-original_ids
        for name, obj in objects.items():
            if obj.get('a3d_component_id') or (name in selection['meshes'] and obj.type != 'MESH') or (
                    name in selection['dependencies'] and obj.type not in ('ARMATURE', 'EMPTY')):
                raise StudioError('Body selection must contain only meshes and declared rig/empty dependencies')
        for block in loaded_ids:
            animation = getattr(block, 'animation_data', None)
            for curve in animation.drivers if animation else ():
                driver = curve.driver
                if driver.type == 'SCRIPTED' and not driver.is_simple_expression:
                    raise StudioError('Body target source has an unbounded scripted driver')
                if any(t.id and t.id not in loaded_ids for variable in driver.variables for t in variable.targets):
                    raise StudioError('Body target source driver depends on undeclared live context')
        temporary = bpy.data.scenes.new('A3D.BodyTarget.'+token)
        temporary.unit_settings.system = 'METRIC'; temporary.unit_settings.scale_length = selection['unit_scale_m']
        for obj in added:
            temporary.collection.objects.link(obj)
        with bpy.context.temp_override(scene=temporary, view_layer=temporary.view_layers[0]):
            temporary.frame_set(selection['frame'])
            depsgraph = bpy.context.evaluated_depsgraph_get(); depsgraph.update()
            raw = {'vertices_cm': [], 'faces': [], 'face_sets': []}; triangles = []; matrices = {}
            for name in sorted(selection['meshes']):
                part, part_triangles = evaluated_mesh(objects[name], depsgraph, selection['unit_scale_m'])
                offset = len(raw['vertices_cm']); raw['vertices_cm'].extend(part['vertices_cm'])
                raw['faces'].extend([[index+offset for index in face] for face in part['faces']])
                raw['face_sets'].extend(part['face_sets'])
                triangles.extend([[index+offset for index in triangle] for triangle in part_triangles])
                matrices[name] = [list(row) for row in objects[name].evaluated_get(depsgraph).matrix_world]
            geometry = dict(raw, source_sha256=selection['source_sha256'],
                            pose_sha256=digest({'frame': selection['frame'], 'geometry': raw, 'matrices': matrices}))
            planned = prepare_target_geometry(geometry, triangles, target, descriptor['adapter'])
            temporary.unit_settings.scale_length = 1.
            mesh = bpy.data.meshes.new('A3D.BodyTargetMesh.'+token)
            mesh.from_pydata([[value/100 for value in point] for point in planned['geometry']['vertices_cm']],
                             [], planned['geometry']['faces']); mesh.update()
            regions = mesh.attributes.new('.sculpt_face_set', 'INT', 'FACE')
            for label, value in zip(regions.data, planned['geometry']['face_sets']):
                label.value = value
            body = bpy.data.objects.new('A3D.BodyTarget.'+token, mesh); temporary.collection.objects.link(body)
            depsgraph.update()
            actual, actual_triangles = evaluated_mesh(body, depsgraph, 1.)
            roundtrip_error = max(math.dist(a, b) for a, b in zip(actual['vertices_cm'], planned['geometry']['vertices_cm']))
            if (actual['faces'] != planned['geometry']['faces'] or actual['face_sets'] != raw['face_sets'] or
                    roundtrip_error > target['tolerances']['roundtrip_cm']):
                raise StudioError('Native target roundtrip changed source topology, regions or metric beyond tolerance')
            native = dict(actual, source_sha256=geometry['source_sha256'],
                          pose_sha256=digest({'planned_pose_sha256': planned['geometry']['pose_sha256'],
                                             'native_geometry_sha256': digest(actual), 'frame': selection['frame']}),
                          rig_landmarks=copy.deepcopy(planned['geometry']['rig_landmarks']),
                          dimension_derivation=copy.deepcopy(planned['geometry']['dimension_derivation']))
            profile = measured_head_surface(profile_mesh(native, planned['options']), native,
                                            head_face_ids(native, descriptor['adapter']), descriptor['adapter']['source_ref'])
            profile = measured_surface_shoulders(profile, native, actual_triangles)
            stature_error = abs(profile['stature_cm']-target['target_stature_cm'])
            floor_error = abs(profile['floor_cm']-planned['source_profile']['floor_cm'])
            girth_residuals = {name: profile['landmarks'][name]['girth_cm']-value
                               for name, value in target.get('target_girths_cm', {}).items()}
            if stature_error > target['tolerances']['stature_cm'] or floor_error > target['tolerances']['floor_cm']:
                raise StudioError('Native target failed stature or floor tolerance')
            directory = project.data/('outputs/body-target-'+token); directory.mkdir(parents=True, exist_ok=False)
            artifact = directory/'body.blend'; body_name = body.name
            body['a3d_role'] = 'measured_body_target'; body['a3d_source_sha256'] = geometry['source_sha256']
            body['a3d_target_sha256'] = descriptor['evidence']['target']['sha256']
            body['a3d_profile_cache_key'] = profile['cache_key']; body['a3d_qualification'] = 'MEASURED_STATIC_BODY_COPY'
            bpy.data.libraries.write(str(artifact), {body}, fake_user=True)
            bpy.data.objects.remove(body, do_unlink=True)
            with bpy.data.libraries.load(str(artifact), link=False) as (_, reloaded):
                reloaded.objects = [body_name]
            reopened = reloaded.objects[0]; temporary.collection.objects.link(reopened); depsgraph.update()
            reopened_geometry, reopened_triangles = evaluated_mesh(reopened, depsgraph, 1.)
            if reopened_geometry != actual or reopened_triangles != actual_triangles:
                raise StudioError('Saved target body did not re-open with its exact native geometry')
            references = {}
            for name, value in [('geometry', native), ('source-geometry', geometry),
                                ('triangles', actual_triangles), ('options', planned['options']),
                                ('profile', profile), ('source-profile', planned['source_profile']),
                                ('derivation', planned['receipt'])]:
                path = directory/(name+'.json'); atomic_json(path, value); references[name] = _reference(project, path)
            complete = (planned['receipt']['status'] == 'BODY_TARGET_MEASURED' and
                        all(abs(value) <= target['tolerances']['girth_cm'] for value in girth_residuals.values()))
            result = dict(planned['receipt'], status='NATIVE_BODY_TARGET_MEASURED' if complete else 'NATIVE_BODY_TARGET_INCOMPLETE',
                          evidence=descriptor['evidence'], artifact=_reference(project, artifact), artifacts=references,
                          geometry_sha256=profile['geometry_sha256'], pose_sha256=profile['pose_sha256'],
                          profile_cache_key=profile['cache_key'], measured_stature_cm=profile['stature_cm'],
                          measured_floor_cm=profile['floor_cm'],
                          measured_girths_cm={name: row['girth_cm'] for name, row in profile['landmarks'].items() if 'girth_cm' in row},
                          native_girth_residuals_cm=girth_residuals, native_roundtrip_error_cm=roundtrip_error,
                          native_stature_error_cm=stature_error, native_floor_error_cm=floor_error,
                          native_reopened=True, live_scene_mutated=False,
                          source_artifact_unchanged=True, blender_version=bpy.app.version_string,
                          rig_creation='NOT_EXECUTED', export_kind='STATIC_EVALUATED_BODY_COPY',
                          next='Review measured target proportions before garment preparation and fitting')
            # Native evidence has its own identity, distinct from the portable derivation.
            result.pop('cache_key', None); result['cache_key'] = digest(result)
            receipt_path = directory/'receipt.json'; atomic_json(receipt_path, result)
            result['receipt'] = _reference(project, receipt_path)
        if sha(source) != selection['source_sha256']:
            raise StudioError('Body target source changed during preparation')
        # Revalidate input files after native preparation; never silently accept
        # replacement of a selection or target while the work is running.
        if target_descriptor(project, selection_path, target_path)['evidence'] != descriptor['evidence']:
            raise StudioError('Body target input evidence changed during preparation')
    finally:
        bpy.data.batch_remove(ids=data_ids()-original_ids)
    if (data_ids() != original_ids or bpy.context.scene != live_scene or live_scene.frame_current != original_frame or
            bpy.data.filepath != original_path or bpy.data.is_dirty != original_dirty or
            sha(project.db) != database_sha or live_geometry() != live_sha):
        raise StudioError('Body target preparation changed live scene or project state')
    return result


def prepare_body_target(project_root, selection_path, target_path):
    from a3d.store import Project
    return _prepare(Project(project_root), selection_path, target_path)
