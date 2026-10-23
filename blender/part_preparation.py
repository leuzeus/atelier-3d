"""Temporary native inspection of an owned multiview rigid reconstruction."""
import time
import uuid

from a3d.core import StudioError, atomic_json, digest, sha


def inspect_reconstructed_part(project_root, profile_path, _normalize=False):
    import bpy
    from a3d.store import Project
    from a3d.part_preparation import part_descriptor, dimension_proposal, calibrate_geometry
    from blender.body_source import data_ids, live_geometry
    project = Project(project_root); inputs = part_descriptor(project, profile_path, normalize=_normalize)
    profile = inputs['profile']; before_ids = data_ids(); before = live_geometry()
    old_scene = bpy.context.window.scene; old_file = bpy.data.filepath
    directory = project.data/('outputs/part-'+uuid.uuid4().hex); directory.mkdir(parents=True, exist_ok=False)
    started = time.monotonic(); geometry = {}; result = None
    def time_budget():
        if time.monotonic()-started > profile['budgets']['max_seconds']:
            raise StudioError('Rigid inspection exceeded its cooperative native time budget')
    try:
        scene = bpy.data.scenes.new('A3D.PartInspection.'+uuid.uuid4().hex)
        scene.unit_settings.system = 'METRIC'; scene.unit_settings.scale_length = 1.
        # The importer uses the active window scene. This isolated temporary
        # scene is restored even when native import or evaluation fails.
        bpy.context.window.scene = scene
        bpy.ops.import_scene.gltf(filepath=str(inputs['source']))
        time_budget()
        imported = list(scene.objects)
        if any(obj.type not in ('MESH', 'EMPTY') for obj in imported):
            raise StudioError('Rigid source contains undeclared non-mesh dependencies')
        meshes = [obj for obj in imported if obj.type == 'MESH']
        if not meshes: raise StudioError('Rigid provider source contains no mesh')
        if any(obj.animation_data or obj.constraints or obj.modifiers for obj in imported):
            raise StudioError('Rigid source contains unsupported dynamic dependencies')
        if any(obj.data.shape_keys for obj in meshes):
            raise StudioError('Static rigid source contains unsupported morph dependencies')
        depsgraph = bpy.context.evaluated_depsgraph_get(); depsgraph.update()
        vertices = 0; faces_count = 0
        for index, obj in enumerate(sorted(meshes, key=lambda value: value.name)):
            time_budget()
            obj.name = profile['component_id']+'.candidate.'+str(index)
            obj['a3d_component_id'] = profile['component_id']
            obj['a3d_package_sha256'] = profile['package_ref']['sha256']
            obj['a3d_provider_source_sha256'] = profile['source_ref']['sha256']
            evaluated = obj.evaluated_get(depsgraph); mesh = evaluated.to_mesh()
            try:
                points = [[float(v)*100 for v in evaluated.matrix_world@point.co] for point in mesh.vertices]
                faces = [list(face.vertices) for face in mesh.polygons]
                geometry[obj.name] = {'vertices_cm': points, 'faces': faces}
                vertices += len(points); faces_count += len(faces)
            finally: evaluated.to_mesh_clear()
        if vertices > profile['budgets']['max_vertices'] or faces_count > profile['budgets']['max_faces']:
            raise StudioError('Rigid evaluated geometry exceeds its declared topology budget')
        calibration = None
        if _normalize:
            from mathutils import Matrix
            transformed, calibration = calibrate_geometry(geometry, inputs['dimensions_cm'],
                profile['normalization']['max_axis_ratio_change'])
            for obj in meshes:
                # Each instance owns its copy before the world-space transform;
                # source geometry, shared imported meshes and UVs are preserved.
                obj.data = obj.data.copy(); obj.parent = None; obj.matrix_world = Matrix.Identity(4)
                for vertex, point in zip(obj.data.vertices, transformed[obj.name]['vertices_cm'], strict=True):
                    vertex.co = [value/100 for value in point]
                obj.data.update()
            depsgraph.update()
            for obj in meshes:
                evaluated = obj.evaluated_get(depsgraph); mesh = evaluated.to_mesh()
                try:
                    actual_faces = [list(face.vertices) for face in mesh.polygons]
                    if actual_faces != geometry[obj.name]['faces']:
                        raise StudioError('Rigid dimension calibration changed its source topology')
                    geometry[obj.name]['vertices_cm'] = [[float(v)*100 for v in evaluated.matrix_world@point.co] for point in mesh.vertices]
                finally: evaluated.to_mesh_clear()
        all_points = [point for row in geometry.values() for point in row['vertices_cm']]
        low = [min(point[axis] for point in all_points) for axis in range(3)]
        high = [max(point[axis] for point in all_points) for axis in range(3)]
        measured = [high[axis]-low[axis] for axis in (0, 2, 1)]
        geometry_path = directory/'geometry.json'; atomic_json(geometry_path, geometry)
        time_budget()
        artifact = directory/'candidate.blend'
        for image in bpy.data.images:
            if image not in before_ids and not image.packed_file: image.pack()
        bpy.data.libraries.write(str(artifact), {scene, *imported}, path_remap='RELATIVE', fake_user=True, compress=True)
        elapsed = time.monotonic()-started
        result = {'version': 1, 'status': 'RIGID_GEOMETRY_INSPECTED' if elapsed <= profile['budgets']['max_seconds'] else 'INCOMPLETE',
                  'component_id': profile['component_id'], 'piece_id': profile['piece_id'],
                  'profile': {'path': profile_path, 'sha256': sha(project.root/profile_path)},
                  'candidate': profile['source_ref'], 'package': profile['package_ref'], 'dossier': profile['dossier_ref'],
                  'artifact': {'path': artifact.relative_to(project.root).as_posix(), 'sha256': sha(artifact)},
                  'geometry': {'path': geometry_path.relative_to(project.root).as_posix(), 'sha256': sha(geometry_path)},
                  'object_names': sorted(geometry), 'vertices': vertices, 'faces': faces_count,
                  'bounds_cm': {'minimum_xyz': low, 'maximum_xyz': high},
                  'measured_dimensions_cm': measured, 'dimension_basis': inputs['dimension_basis'],
                  'proposal': dimension_proposal(measured, inputs['dimensions_cm']),
                  'elapsed_seconds': elapsed, 'geometry_sha256': digest(geometry),
                  'time_budget_scope': 'COOPERATIVE_CHECKS_BETWEEN_NATIVE_OPERATIONS_NO_PREEMPTION',
                  'orientation': 'PROVIDER_NATIVE_UNREVIEWED', 'anchors': 'NOT_QUALIFIED',
                  'qualification': 'NATIVE_INSPECTION_ONLY', 'accepted': False, 'artistic_review': 'REQUIRED'}
        if calibration:
            residuals = [actual-goal for actual, goal in zip(measured, inputs['dimensions_cm'], strict=True)]
            passed = max(abs(value) for value in residuals) <= profile['normalization']['dimension_tolerance_cm']
            result.update(status='RIGID_DIMENSION_CALIBRATED_UNACCEPTED' if passed and elapsed <= profile['budgets']['max_seconds'] else 'NEEDS_CORRECTION',
                          calibration=calibration, dimension_residuals_cm=residuals,
                          dimensions_status='PASS' if passed else 'FAIL', qualification='DIMENSIONS_ONLY',
                          placement_binding='NOT_PREPARED', anchors='TARGET_MAPPING_REQUIRED')
    finally:
        bpy.context.window.scene = old_scene
        bpy.data.batch_remove(ids=data_ids()-before_ids)
    if data_ids() != before_ids or live_geometry() != before or bpy.data.filepath != old_file:
        raise StudioError('Rigid inspection changed the live scene')
    if sha(inputs['source']) != profile['source_ref']['sha256']:
        raise StudioError('Rigid provider source changed during inspection')
    result['original_preserved'] = True
    receipt = directory/'receipt.json'; atomic_json(receipt, result)
    return dict(result, receipt={'path': receipt.relative_to(project.root).as_posix(), 'sha256': sha(receipt)})


def prepare_reconstructed_part(project_root, profile_path):
    return inspect_reconstructed_part(project_root, profile_path, _normalize=True)
