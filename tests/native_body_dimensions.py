"""Fresh Blender stature/skin measurements; no production scene or fitting.

Run Blender --background --factory-startup --offline-mode --python-exit-code 1
--python tests/native_body_dimensions.py -- --output <new-directory>
--target-stature-cm 180. Validate arguments first with ordinary Python and
--validate-only. Output directories are deliberately never reused.
"""
import argparse
import copy
import json
import math
from pathlib import Path
import sys

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))
from a3d.anatomy_profile import profile_mesh
from a3d.body_dimensions import variant_by_stature
from a3d.catalog_anatomy import region_guides
from a3d.core import atomic_json, digest, read_json, sha
from a3d.mannequins import catalog
from a3d.shoulder_surface import measured_surface_shoulders, surface_anchors


def arguments(argv):
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--output', required=True)
    parser.add_argument('--target-stature-cm', type=float, required=True)
    parser.add_argument('--recheck-receipt', help='Remeasure exact existing native variants without rebuilding them')
    parser.add_argument('--validate-only', action='store_true')
    args = parser.parse_args(argv)
    output = Path(args.output)
    if not output.is_absolute() or output.exists():
        parser.error('--output must be an absolute new directory')
    if not math.isfinite(args.target_stature_cm) or not 30 <= args.target_stature_cm <= 400:
        parser.error('target stature must be within 30 to 400 cm')
    args.output = output.resolve()
    if args.output.is_relative_to(ROOT/'assets'):
        parser.error('native evidence cannot be written among immutable source assets')
    if args.recheck_receipt:
        receipt = Path(args.recheck_receipt)
        if not receipt.is_absolute() or not receipt.is_file():
            parser.error('--recheck-receipt must be an absolute existing receipt file')
        args.recheck_receipt = receipt.resolve()
    return args


def evaluated_mesh(body):
    import bpy
    evaluated = body.evaluated_get(bpy.context.evaluated_depsgraph_get())
    mesh = evaluated.to_mesh()
    try:
        points = [[float(value)*100 for value in evaluated.matrix_world@vertex.co] for vertex in mesh.vertices]
        faces = [list(face.vertices) for face in mesh.polygons]
        labels = mesh.attributes.get('.sculpt_face_set')
        assert labels is not None and labels.domain == 'FACE'
        face_sets = [value.value for value in labels.data]
        assert len(face_sets) == len(faces)
        mesh.calc_loop_triangles()
        triangles = [list(triangle.vertices) for triangle in mesh.loop_triangles]
        matrix = [[float(value) for value in row] for row in evaluated.matrix_world]
        return {'vertices_cm': points, 'faces': faces, 'face_sets': face_sets}, triangles, matrix
    finally:
        evaluated.to_mesh_clear()


def ref(path):
    return {'path': str(path), 'sha256': sha(path)}


def loaded_code_sources():
    names = ['a3d/body_dimensions.py', 'a3d/anatomy_profile.py', 'a3d/catalog_anatomy.py',
             'a3d/shoulder_surface.py', 'tests/native_body_dimensions.py']
    paths = {}
    for name in names:
        loaded_path = (__file__ if name.startswith('tests/')
                       else sys.modules[name[:-3].replace('/', '.')].__file__)
        actual = Path(loaded_path).resolve()
        assert actual == (ROOT/name).resolve(), 'Native test loaded a different module source'
        paths[name] = str(actual)
    return paths, {name: sha(path) for name, path in paths.items()}


def remeasure(output, target, previous_path):
    """Requalify measurement code against exact native artifacts; never rescale."""
    import bpy
    assert bpy.app.background and not bpy.data.filepath
    previous = read_json(previous_path)
    assert previous['status'] == 'NATIVE_STATURE_AND_SURFACE_MEASUREMENTS_PASS'
    assert previous['qualification'] == 'GEOMETRY_ONLY'
    entries = {entry['id']: entry for entry in catalog(ROOT)['entries']}
    assert {report['body'] for report in previous['reports']} == set(entries)
    output.mkdir(parents=True, exist_ok=False)
    scene = bpy.context.scene
    scene.frame_set(1)
    scene.unit_settings.system = 'METRIC'
    scene.unit_settings.scale_length = 1.
    for obj in list(scene.objects):
        bpy.data.objects.remove(obj, do_unlink=True)
    loaded_paths, hashes = loaded_code_sources()
    criteria_ref = previous['criteria']
    assert sha(criteria_ref['path']) == criteria_ref['sha256']
    criteria = read_json(criteria_ref['path'])
    assert criteria['target_stature_cm'] == target
    atomic_json(output/'criteria.json', criteria)
    reports = []
    for old in previous['reports']:
        entry = entries[old['body']]
        for name in ('source', 'segmentation_adapter', 'artifact', 'evaluated_geometry', 'options', 'transformation'):
            reference = old[name]
            assert sha(reference['path']) == reference['sha256']
        assert old['source']['sha256'] == entry['sha256']
        assert old['segmentation_adapter']['sha256'] == entry['anatomy_adapter_sha256']
        assert old['target_stature_cm'] == target
        source_path = ROOT/'assets/mannequins'/entry['file']
        assert source_path.resolve() == Path(old['source']['path']).resolve()
        with bpy.data.libraries.load(str(source_path), link=False) as (_, loaded):
            loaded.objects = list(entry['meshes'])
        source_body = loaded.objects[0]
        scene.collection.objects.link(source_body)
        bpy.context.view_layer.update()
        raw, source_triangles, source_matrix = evaluated_mesh(source_body)
        source_geometry = dict(raw, source_sha256=entry['sha256'],
                               pose_sha256=digest({'frame': scene.frame_current,
                                                    'evaluated_geometry': raw, 'matrix_world': source_matrix}))
        adapter = read_json(old['segmentation_adapter']['path'])
        guides = region_guides(source_geometry, adapter)
        source_geometry['rig_landmarks'] = guides['rig_landmarks']
        options = dict(copy.deepcopy(entry['orientation']), origin_cm=[0., 0., 0.],
                       torso_faces=guides['torso_faces'],
                       segmentation_source_ref=guides['segmentation_source_ref'], section_count=80)
        source_profile = measured_surface_shoulders(profile_mesh(source_geometry, options),
                                                    source_geometry, source_triangles)
        source_skin = surface_anchors(source_profile)
        with bpy.data.libraries.load(old['artifact']['path'], link=False) as (available, loaded):
            assert len(available.objects) == 1
            loaded.objects = list(available.objects)
        body = loaded.objects[0]
        assert body.type == 'MESH'
        scene.collection.objects.link(body)
        bpy.context.view_layer.update()
        actual, triangles, matrix = evaluated_mesh(body)
        geometry = read_json(old['evaluated_geometry']['path'])
        assert actual['vertices_cm'] == geometry['vertices_cm'] and actual['faces'] == geometry['faces']
        assert actual['face_sets'] == geometry['face_sets'] == raw['face_sets']
        assert actual['faces'] == raw['faces']
        transform = read_json(old['transformation']['path'])
        actual_identity = digest([actual['vertices_cm'], actual['faces']])
        native_pose = digest({'dimension_pose_sha256': transform['variant_pose_sha256'],
                             'evaluated_geometry_sha256': actual_identity,
                             'matrix_world': matrix, 'frame': scene.frame_current})
        assert native_pose == geometry['pose_sha256'] == old['evaluated_pose_sha256']
        assert actual_identity == old['evaluated_geometry_sha256']
        variant_options = read_json(old['options']['path'])
        profile = measured_surface_shoulders(profile_mesh(geometry, variant_options), geometry, triangles)
        skin = surface_anchors(profile)
        errors = {}
        for side in ('left', 'right'):
            point, factor = source_skin[side], transform['uniform_factor']
            predicted = [factor*point[0], factor*point[1],
                         source_profile['floor_cm']+factor*(point[2]-source_profile['floor_cm'])]
            errors[side] = math.dist(predicted, skin[side])
            assert errors[side] <= criteria['native_roundtrip_max_error_cm']
        assert abs(profile['stature_cm']-target) <= criteria['native_stature_error_cm']
        assert abs(profile['floor_cm']-source_profile['floor_cm']) <= criteria['native_floor_error_cm']
        source_profile_path = output/(entry['id']+'.source-profile.json')
        profile_path = output/(entry['id']+'.profile.json')
        atomic_json(source_profile_path, source_profile)
        atomic_json(profile_path, profile)
        report = copy.deepcopy(old)
        report.update(source_profile=ref(source_profile_path), profile=ref(profile_path),
                      profile_cache_key=profile['cache_key'], measured_stature_cm=profile['stature_cm'],
                      shoulder_surface_transform_error_cm=errors,
                      shoulder_surface_landmarks={side: profile['landmarks']['shoulder.surface.'+side]
                                                  for side in ('left', 'right')},
                      stature_variant_rebuilt=False, native_variant_loaded_for_measurement=True)
        reports.append(report)
        for obj in (body, source_body):
            bpy.data.objects.remove(obj, do_unlink=True)
        assert sha(source_path) == entry['sha256']
        assert sha(old['segmentation_adapter']['path']) == entry['anatomy_adapter_sha256']
    assert all(sha(ROOT/name) == identity for name, identity in hashes.items())
    result = {'version': 1, 'status': 'NATIVE_STATURE_AND_SURFACE_MEASUREMENTS_PASS',
              'qualification': 'GEOMETRY_ONLY', 'criteria': ref(output/'criteria.json'),
              'reports': reports, 'source_modules_sha256': hashes, 'loaded_module_source_paths': loaded_paths,
              'previous_receipt': ref(previous_path),
              'blender_version': bpy.app.version_string, 'blender_hash': bpy.app.build_hash.decode(),
              'background': bpy.app.background, 'factory_startup': True, 'production_connection': False,
              'ai_adjustments': 'NOT_USED', 'simulation': 'NOT_EXECUTED', 'fitting': 'NOT_EXECUTED',
              'stature_variant_rebuilt': False, 'measurement_recheck': True}
    atomic_json(output/'receipt.json', result)
    print(json.dumps({'status': result['status'], 'receipt': ref(output/'receipt.json'),
                      'qualification': result['qualification'], 'stature_variant_rebuilt': False}))


def run(output, target):
    import bpy
    assert bpy.app.background, 'Native scenario requires a fresh background process'
    assert not bpy.data.filepath, 'Native scenario requires factory startup without a production file'
    output.mkdir(parents=True, exist_ok=False)
    scene = bpy.context.scene
    scene.frame_set(1)
    scene.unit_settings.system = 'METRIC'
    scene.unit_settings.scale_length = 1.
    for obj in list(scene.objects):
        bpy.data.objects.remove(obj, do_unlink=True)
    criteria = {'version': 1, 'qualification': 'GEOMETRY_ONLY',
                'target_stature_cm': target, 'native_roundtrip_max_error_cm': .0001,
                'native_stature_error_cm': .0001, 'native_floor_error_cm': .0001,
                'native_reopen_max_error_cm': .0001,
                'source_unchanged_required': True, 'source_adapter_unchanged_required': True,
                'topology_unchanged_required': True,
                'body_adjustment': 'UNIFORM_STATURE_ONLY', 'floor_policy': 'PRESERVE_SOURCE_PLANE',
                'garment_fitting_gates_changed': False, 'garment_fitting': 'NOT_EXECUTED'}
    atomic_json(output/'criteria.json', criteria)
    loaded_paths, module_hashes = loaded_code_sources()
    catalog_path = ROOT/'assets/mannequins/catalog.json'
    catalog_before = sha(catalog_path)
    reports = []
    for entry in catalog(ROOT)['entries']:
        ident = entry['id']
        source_path = ROOT/'assets/mannequins'/entry['file']
        adapter_path = ROOT/'assets/mannequins'/entry['anatomy_adapter']
        source_before, adapter_before = sha(source_path), sha(adapter_path)
        adapter = read_json(adapter_path)
        adapter_value_before = digest(adapter)
        assert source_before == entry['sha256'] and adapter_before == entry['anatomy_adapter_sha256']
        with bpy.data.libraries.load(str(source_path), link=False) as (_, loaded):
            loaded.objects = list(entry['meshes'])
        assert len(loaded.objects) == 1 and loaded.objects[0].type == 'MESH'
        source_body = loaded.objects[0]
        scene.collection.objects.link(source_body)
        bpy.context.view_layer.update()
        raw, source_triangles, source_matrix = evaluated_mesh(source_body)
        original_mesh_identity = digest(raw)
        source_geometry = dict(raw, source_sha256=source_before,
                               pose_sha256=digest({'frame': scene.frame_current,
                                                    'evaluated_geometry': raw, 'matrix_world': source_matrix}))
        # The unchanged adapter is admitted only against the exact original metric.
        guides = region_guides(source_geometry, adapter)
        source_geometry['rig_landmarks'] = guides['rig_landmarks']
        options = dict(copy.deepcopy(entry['orientation']), origin_cm=[0., 0., 0.],
                       torso_faces=guides['torso_faces'],
                       segmentation_source_ref=guides['segmentation_source_ref'], section_count=80)
        source_profile = profile_mesh(source_geometry, options)
        source_profile = measured_surface_shoulders(source_profile, source_geometry, source_triangles)
        source_skin = surface_anchors(source_profile)
        immutable_input = digest([source_geometry, options])
        planned = variant_by_stature(source_geometry, options, target)
        assert digest([source_geometry, options]) == immutable_input
        planned_points = planned['geometry']['vertices_cm']
        mesh = bpy.data.meshes.new('A3D.StatureVariantMesh.'+ident)
        mesh.from_pydata([[value/100 for value in point] for point in planned_points], [], raw['faces'])
        mesh.update()
        labels = mesh.attributes.new('.sculpt_face_set', 'INT', 'FACE')
        for data, label in zip(labels.data, raw['face_sets']):
            data.value = label
        body = bpy.data.objects.new('A3D.StatureVariant.'+ident, mesh)
        scene.collection.objects.link(body)
        bpy.context.view_layer.update()
        actual, triangles, matrix = evaluated_mesh(body)
        assert actual['faces'] == raw['faces'] and actual['face_sets'] == raw['face_sets']
        assert len(actual['vertices_cm']) == len(planned_points)
        precision = max(math.dist(a, b) for a, b in zip(actual['vertices_cm'], planned_points))
        assert precision <= criteria['native_roundtrip_max_error_cm']
        actual_identity = digest([actual['vertices_cm'], actual['faces']])
        native_pose = digest({'dimension_pose_sha256': planned['geometry']['pose_sha256'],
                             'evaluated_geometry_sha256': actual_identity,
                             'matrix_world': matrix, 'frame': scene.frame_current})
        native_geometry = dict(actual, source_sha256=source_before, pose_sha256=native_pose,
                               rig_landmarks=copy.deepcopy(planned['geometry']['rig_landmarks']),
                               dimension_derivation=copy.deepcopy(planned['geometry']['dimension_derivation']))
        profile = profile_mesh(native_geometry, planned['options'])
        assert profile['geometry_sha256'] == actual_identity
        assert profile['pose_sha256'] == native_pose
        assert profile['cache_key'] != source_profile['cache_key']
        assert profile['cache_key'] != planned['profile']['cache_key']
        stature_error = abs(profile['stature_cm']-target)
        floor_error = abs(profile['floor_cm']-source_profile['floor_cm'])
        assert stature_error <= criteria['native_stature_error_cm']
        assert floor_error <= criteria['native_floor_error_cm']
        profile = measured_surface_shoulders(profile, native_geometry, triangles)
        native_skin = surface_anchors(profile)
        factor = planned['receipt']['uniform_factor']
        skin_errors = {}
        for side in ('left', 'right'):
            point = source_skin[side]
            predicted = [factor*point[0], factor*point[1],
                         source_profile['floor_cm']+factor*(point[2]-source_profile['floor_cm'])]
            skin_errors[side] = math.dist(predicted, native_skin[side])
            assert skin_errors[side] <= criteria['native_roundtrip_max_error_cm']
            assert profile['landmarks']['shoulder.surface.'+side]['distance_from_joint_cm'] > 0
        body['a3d_source_sha256'] = source_before
        body['a3d_dimension_operation_key'] = planned['receipt']['dimension_operation_key']
        body['a3d_evaluated_pose_sha256'] = native_pose
        body['a3d_target_stature_cm'] = target
        body['a3d_qualification'] = 'HEIGHT_ONLY'
        geometry_path = output/(ident+'.evaluated-geometry.json')
        source_profile_path = output/(ident+'.source-profile.json')
        profile_path = output/(ident+'.profile.json')
        options_path = output/(ident+'.options.json')
        transform_path = output/(ident+'.transformation.json')
        working_path = output/(ident+f'.{target:g}cm.blend')
        atomic_json(geometry_path, native_geometry)
        atomic_json(source_profile_path, source_profile)
        atomic_json(profile_path, profile)
        atomic_json(options_path, planned['options'])
        atomic_json(transform_path, planned['receipt'])
        bpy.data.libraries.write(str(working_path), {body}, fake_user=True)
        body_name = body.name
        bpy.data.objects.remove(body, do_unlink=True)
        with bpy.data.libraries.load(str(working_path), link=False) as (_, loaded):
            loaded.objects = [body_name]
        reopened_body = loaded.objects[0]
        scene.collection.objects.link(reopened_body)
        bpy.context.view_layer.update()
        reopened, reopened_triangles, reopened_matrix = evaluated_mesh(reopened_body)
        assert reopened['faces'] == actual['faces'] and reopened['face_sets'] == actual['face_sets']
        assert reopened_triangles == triangles and reopened_matrix == matrix
        reopened_error = max(math.dist(a, b) for a, b in zip(reopened['vertices_cm'], actual['vertices_cm']))
        assert reopened_error <= criteria['native_reopen_max_error_cm']
        original_after, _, _ = evaluated_mesh(source_body)
        assert digest(original_after) == original_mesh_identity
        assert sha(source_path) == source_before and sha(adapter_path) == adapter_before
        assert digest(adapter) == adapter_value_before
        girths = {name: point['girth_cm'] for name, point in profile['landmarks'].items() if 'girth_cm' in point}
        reports.append({'body': ident, 'status': 'NATIVE_STATURE_AND_SURFACE_MEASUREMENTS_PASS',
                        'qualification': 'GEOMETRY_ONLY', 'dimension_qualification': 'HEIGHT_ONLY',
                        'source': ref(source_path), 'segmentation_adapter': ref(adapter_path),
                        'source_adapter_rebound': False,
                        'segmentation': 'UNCHANGED_SOURCE_FACE_IDENTITIES',
                        'source_profile': ref(source_profile_path), 'transformation': ref(transform_path),
                        'evaluated_geometry': ref(geometry_path), 'profile': ref(profile_path),
                        'options': ref(options_path), 'artifact': ref(working_path),
                        'source_geometry_sha256': source_profile['geometry_sha256'],
                        'evaluated_geometry_sha256': profile['geometry_sha256'],
                        'evaluated_pose_sha256': native_pose, 'profile_cache_key': profile['cache_key'],
                        'target_stature_cm': target, 'measured_stature_cm': profile['stature_cm'],
                        'uniform_factor': factor, 'native_roundtrip_max_error_cm': precision,
                        'stature_error_cm': stature_error, 'floor_error_cm': floor_error,
                        'native_reopen_max_error_cm': reopened_error,
                        'measured_girths_cm': girths, 'girth_targets': 'NOT_REQUESTED',
                        'shoulder_surface_transform_error_cm': skin_errors,
                        'shoulder_surface_landmarks': {side: profile['landmarks']['shoulder.surface.'+side]
                                                       for side in ('left', 'right')},
                        'vertices': len(actual['vertices_cm']), 'faces': len(actual['faces']),
                        'triangles': len(triangles), 'topology_preserved': True,
                        'source_unchanged': True, 'source_adapter_unchanged': True,
                        'mensurations_review': 'REQUIRED_BEFORE_FITTING', 'rig_creation': 'NOT_EXECUTED',
                        'simulation': 'NOT_EXECUTED', 'contacts': 'NOT_EXECUTED',
                        'fitting': 'NOT_EXECUTED', 'production_connection': False})
        bpy.data.objects.remove(reopened_body, do_unlink=True)
        bpy.data.objects.remove(source_body, do_unlink=True)
    assert sha(catalog_path) == catalog_before
    assert all(sha(ROOT/name) == identity for name, identity in module_hashes.items())
    result = {'version': 1, 'status': 'NATIVE_STATURE_AND_SURFACE_MEASUREMENTS_PASS',
              'qualification': 'GEOMETRY_ONLY', 'criteria': ref(output/'criteria.json'),
              'reports': reports, 'source_modules_sha256': module_hashes,
              'loaded_module_source_paths': loaded_paths,
              'blender_version': bpy.app.version_string, 'blender_hash': bpy.app.build_hash.decode(),
              'background': bpy.app.background, 'factory_startup': True, 'production_connection': False,
              'ai_adjustments': 'NOT_USED', 'simulation': 'NOT_EXECUTED', 'fitting': 'NOT_EXECUTED'}
    atomic_json(output/'receipt.json', result)
    print(json.dumps({'status': result['status'], 'qualification': result['qualification'],
                      'receipt': ref(output/'receipt.json'),
                      'bodies': [{'body': report['body'], 'stature_cm': report['measured_stature_cm'],
                                  'girths_cm': report['measured_girths_cm'],
                                  'skin_errors_cm': report['shoulder_surface_transform_error_cm']}
                                 for report in reports]}, sort_keys=True))


if __name__ == '__main__':
    argv = sys.argv[sys.argv.index('--')+1:] if '--' in sys.argv else sys.argv[1:]
    args = arguments(argv)
    if args.validate_only:
        print(json.dumps({'arguments_valid': True, 'output': str(args.output),
                          'target_stature_cm': args.target_stature_cm, 'native_executed': False}))
    else:
        if args.recheck_receipt:
            remeasure(args.output, args.target_stature_cm, args.recheck_receipt)
        else:
            run(args.output, args.target_stature_cm)
