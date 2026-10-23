"""Synthetic UV/LOD and packed Blender-animation transport on a fresh project.

Run ONLY in isolated factory-startup background Blender with
--python-exit-code 1. Fixtures never qualify the fifteen-piece production asset.
"""
import argparse
import copy
import json
from pathlib import Path
import runpy
import sys

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))


def arguments(argv):
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--output', required=True)
    parser.add_argument('--validate-only', action='store_true')
    args = parser.parse_args(argv); output = Path(args.output)
    if not output.is_absolute() or output.exists() or output.resolve().is_relative_to(ROOT/'assets'):
        parser.error('Use an absolute new output directory outside immutable source assets')
    args.output = output.resolve()
    return args


def _managed(project, operation, profile_path, statuses, tag):
    from a3d.core import atomic_json, digest, read_json, sha
    from a3d.runs import create_run, next_run_step, run_status
    profile = read_json(profile_path)
    references = [{'path': profile_path.relative_to(project.root).as_posix(), 'sha256': sha(profile_path)},
                  profile['source_ref'], *[row['file_ref'] for row in profile['resources']], *profile.get('motion_receipts', [])]
    campaign = digest(str(project.root))[:12]
    spec = {'version': 1, 'id': 'native.'+tag+'.'+campaign, 'kind': 'export', 'asset_id': 'test-character',
            'inputs': [], 'budgets': {'max_attempts': 1, 'max_seconds': 600.},
            'units': [{'id': tag, 'dependencies': [], 'executor': 'blender', 'operation': operation,
                       'arguments': {'profile_path': profile_path.relative_to(project.root).as_posix()},
                       'inputs': references, 'success_statuses': statuses}]}
    spec_path = project.data/('native-'+tag+'-run.json'); atomic_json(spec_path, spec)
    info = create_run(project, 'export', spec_path.relative_to(project.root).as_posix())
    assert next_run_step(project, info['run_id'])['status'] == 'AWAITING_CONFIRMATION'
    dispatch = runpy.run_path(str(ROOT/'blender/bootstrap.py'))['dispatch_current']
    result = dispatch(str(project.root), operation, spec['units'][0]['arguments'])
    status = run_status(project, info['run_id']); unit = status['units'][0]
    assert unit['attempts'][0]['receipt_event_id']
    return result, {'run_id': info['run_id'], 'unit_status': unit['status'], 'canonical_native_receipt': unit['attempts'][0]['receipt']}


def _fixture(project):
    import bpy
    from a3d.asset_finishing import source_uv_identity
    from a3d.core import sha
    from blender.body_motion import _curves
    from tests.support import png
    texture = project.root/'fixture-texture.png'; texture.write_bytes(png())
    image = bpy.data.images.load(str(texture), check_existing=False); image.name = 'NATIVE.Texture'
    material = bpy.data.materials.new('NATIVE.Material'); material.use_nodes = True
    texture_node = material.node_tree.nodes.new('ShaderNodeTexImage'); texture_node.image = image
    principled = next(node for node in material.node_tree.nodes if node.type == 'BSDF_PRINCIPLED')
    material.node_tree.links.new(texture_node.outputs['Color'], principled.inputs['Base Color'])
    mesh = bpy.data.meshes.new('NATIVE.Pattern'); faces = [[0, 1, 2], [0, 2, 3]]
    mesh.from_pydata([[.4, 0., 0.], [.6, 0., 0.], [.6, .4, 0.], [.4, .4, 0.]], [], faces); mesh.update()
    uv = mesh.uv_layers.new(name='SourcePattern'); source_uv = [[0., 0.], [20., 0.], [20., 40.], [0., 0.], [20., 40.], [0., 40.]]
    for value, point in zip(uv.data, source_uv, strict=True): value.uv = point
    regions = mesh.attributes.new('.sculpt_face_set', 'INT', 'FACE')
    for value in regions.data: value.value = 1
    cloth = bpy.data.objects.new('cloth', mesh); cloth['a3d_role'] = 'simulation'; cloth.data.materials.append(material)
    bpy.context.scene.collection.objects.link(cloth)
    cloth.shape_key_add(name='Basis'); observed = cloth.shape_key_add(name='Observed.Frame.2')
    for point in observed.data: point.co.z += .02
    for frame, value in ((1, 0.), (2, 1.), (3, 0.)):
        observed.value = value; observed.keyframe_insert('value', frame=frame)
    shape_action = cloth.data.shape_keys.animation_data.action; shape_action.name = 'NATIVE.ObservedGeometry'
    for curve in _curves(shape_action):
        for key in curve.keyframe_points: key.interpolation = 'LINEAR'
    shape_slot = cloth.data.shape_keys.animation_data.action_slot.identifier
    assert cloth.animation_data is None and cloth.data.shape_keys.animation_data.action_slot.target_id_type == 'KEY'
    points = [[x*.05, y*.05, .04] for y in range(5) for x in range(5)]; grid = []
    for y in range(4):
        for x in range(4):
            a = y*5+x; grid.extend([[a, a+1, a+6], [a, a+6, a+5]])
    rigid_mesh = bpy.data.meshes.new('NATIVE.Rigid'); rigid_mesh.from_pydata(points, [], grid); rigid_mesh.update()
    buckle = bpy.data.objects.new('buckle', rigid_mesh); bpy.context.scene.collection.objects.link(buckle)
    for frame in (1, 2, 3):
        buckle.location.x = .01*(frame-1); buckle.keyframe_insert('location', index=0, frame=frame)
    action = buckle.animation_data.action; action.name = 'NATIVE.Translation'
    for curve in _curves(action):
        for key in curve.keyframe_points: key.interpolation = 'LINEAR'
    slot = buckle.animation_data.action_slot.identifier
    bpy.context.scene.frame_set(1); bpy.context.view_layer.update()
    path = project.root/'fixture.blend'; bpy.data.libraries.write(str(path), {cloth, buckle, action, shape_action}, fake_user=True)
    return {'source_ref': {'path': path.name, 'sha256': sha(path)}, 'uv_sha256': source_uv_identity(faces, source_uv),
            'resource': {'kind': 'IMAGE', 'datablock_name': image.name, 'file_ref': {'path': texture.name, 'sha256': sha(texture)}},
            'action_name': action.name, 'slot_identifier': slot,
            'shape_action_name': shape_action.name, 'shape_slot_identifier': shape_slot}


def run(output):
    import bpy
    from a3d.core import atomic_json, digest, read_json, sha
    from a3d.export_profiles import export_descriptor, verify_export_manifest
    from a3d.store import Project
    from blender.body_source import data_ids, live_geometry
    from tests.support import asset
    from tests.test_asset_finishing import profile as finishing_profile
    from tests.test_asset_export import clip_receipt, profile as export_profile
    assert bpy.app.background and not bpy.data.filepath and bpy.context.mode == 'OBJECT'
    output.mkdir(parents=True, exist_ok=False); project = Project.create(output/'project', asset(True))
    baseline = data_ids(); before = live_geometry(); selected = set(bpy.context.selected_objects)
    active = bpy.context.view_layer.objects.active; live_frame = bpy.context.scene.frame_current
    fixture = _fixture(project); bpy.context.scene.frame_set(live_frame)
    bpy.data.batch_remove(ids=data_ids()-baseline)
    assert data_ids() == baseline and live_geometry() == before
    finish = finishing_profile(fixture['source_ref'], fixture['uv_sha256'])
    finish['action_names'] = [fixture['action_name'], fixture['shape_action_name']]; finish['resources'] = [fixture['resource']]
    finish['operations'][1]['lods'][0].update(max_faces=20, max_geometry_error_cm=.0001)
    finish_path = project.root/'finish.json'; atomic_json(finish_path, finish)
    result, finishing_journal = _managed(project, 'prepare_asset_finishing', finish_path, ['ASSET_FINISHING_PREPARED'], 'finishing')
    assert result['status'] == 'ASSET_FINISHING_PREPARED' and result['native_reopened']
    assert result['uv_operations'][0]['source_uv_preserved'] and result['uv_operations'][0]['uv_sha256'] == fixture['uv_sha256']
    assert result['uv_operations'][1]['method'] == 'SMART_PROJECT'
    assert len(result['lods']) == 1 and result['lods'][0]['status'] == 'LOD_GEOMETRY_WITHIN_BUDGET'
    assert result['lods'][0]['metrics']['lod_faces'] <= 20 and result['lods'][0]['metrics']['max_surface_error_cm'] <= .0001
    assert result['lods'][0]['metrics']['executed_samples'] == result['lods'][0]['metrics']['expected_samples']
    assert finishing_journal['unit_status'] == 'COMPLETED'
    comparison = read_json(project.root/result['comparison_artifact']['path'])
    export = export_profile(result['artifact'])
    export['object_names'] = list(result['object_mapping'].values()); export['dependency_names'] = []
    export['action_names'] = list(result['action_mapping'].values()); export['embedded_image_names'] = list(result['image_mapping'].values())
    export['clips'] = [{'id': 'translation', 'object_name': result['object_mapping']['buckle'],
                        'action_name': result['action_mapping'][fixture['action_name']], 'slot_identifier': fixture['slot_identifier'],
                        'frame_start': 1, 'frame_end': 3, 'sample_step': 2},
                       {'id': 'observed-geometry', 'object_name': result['object_mapping']['cloth'],
                        'action_name': result['action_mapping'][fixture['shape_action_name']],
                        'slot_identifier': fixture['shape_slot_identifier'], 'animation_target': 'SHAPE_KEYS',
                        'frame_start': 1, 'frame_end': 3, 'sample_step': 1}]
    export['clips'][0]['tracks'] = [{'object_name': result['object_mapping']['cloth'],
                                    'action_name': result['action_mapping'][fixture['shape_action_name']],
                                    'slot_identifier': fixture['shape_slot_identifier'], 'animation_target': 'SHAPE_KEYS'}]
    export['clips'][1]['tracks'] = [{'object_name': result['object_mapping']['buckle'],
                                    'action_name': result['action_mapping'][fixture['action_name']],
                                    'slot_identifier': fixture['slot_identifier'], 'animation_target': 'OBJECT'}]
    manual = clip_receipt(export, digest(comparison['actions'][fixture['action_name']]))
    # Even a complete client claim cannot create native dispatch provenance.
    manual['native_dispatch_verified'] = True; manual['clip_measurements_verified'] = ['translation']
    manual['cache_key'] = digest({key: value for key, value in manual.items() if key != 'cache_key'})
    manual_path = project.root/'manual-motion.json'; atomic_json(manual_path, manual)
    export['motion_receipts'] = [{'path': manual_path.name, 'sha256': sha(manual_path)}]
    export_path = project.root/'export.json'; atomic_json(export_path, export)
    assert export_descriptor(project, export_path.name)['receipts'][0]['native_dispatch_verified'] is False
    exported, export_journal = _managed(project, 'export_blender_animation', export_path, ['BLENDER_EXPORT_REOPENED'], 'export')
    assert exported['status'] == 'BLENDER_EXPORT_REOPENED' and exported['reimport'] == 'EXECUTED'
    assert exported['native_comparison']['sample_count'] == 6
    assert exported['native_comparison']['max_vertex_delta_cm'] <= .0001
    assert exported['animation_qualification'] == 'NOT_QUALIFIED' and exported['clips_executed'] == []
    assert exported['packed_resources'] and export_journal['unit_status'] == 'COMPLETED'
    assert verify_export_manifest(project, exported)['status'] == 'BLENDER_TRANSPORT_VERIFIED'
    native_comparison = read_json(project.root/exported['snapshots_artifact']['path'])
    observed_samples = [row for row in native_comparison['samples_before'] if row['clip_id'] == 'observed-geometry']
    cloth_name = result['object_mapping']['cloth']
    assert [row['time'] for row in observed_samples] == [1, 2, 3]
    assert observed_samples[0]['meshes'][cloth_name]['vertices_cm'] != observed_samples[1]['meshes'][cloth_name]['vertices_cm']
    assert observed_samples[0]['meshes'][cloth_name]['vertices_cm'] == observed_samples[2]['meshes'][cloth_name]['vertices_cm']
    assert native_comparison['rest'][cloth_name]['mesh']['shape_key_settings']['action'] is not None
    # Keep the successful candidate unchanged and prepare separate test variants.
    insufficient = copy.deepcopy(finish); insufficient['budgets']['max_error_samples'] = 1
    insufficient_path = project.root/'insufficient-lod-budget.json'; atomic_json(insufficient_path, insufficient)
    partial, partial_journal = _managed(project, 'prepare_asset_finishing', insufficient_path, ['ASSET_FINISHING_PREPARED'], 'partial-lod')
    assert partial['status'] == 'INCOMPLETE' and partial['native_reopened']
    assert partial['lods'][0]['status'] == 'INCOMPLETE' and partial_journal['unit_status'] == 'INCOMPLETE'
    bad_uv = copy.deepcopy(finish); bad_uv['operations'][0]['uv']['source_uv_sha256'] = 'a'*64
    bad_path = project.root/'wrong-source-uv.json'; atomic_json(bad_path, bad_uv)
    dispatch = runpy.run_path(str(ROOT/'blender/bootstrap.py'))['dispatch_current']
    try:
        dispatch(str(project.root), 'prepare_asset_finishing', {'profile_path': bad_path.name})
    except ValueError as error:
        assert 'UV map' in str(error)
    else:
        raise AssertionError('Native finishing changed a mismatched immutable sewn UV')
    missing = copy.deepcopy(finish); missing['resources'][0]['file_ref']['path'] = 'missing-texture.png'
    missing_path = project.root/'missing-resource.json'; atomic_json(missing_path, missing)
    try:
        dispatch(str(project.root), 'prepare_asset_finishing', {'profile_path': missing_path.name})
    except (ValueError, FileNotFoundError):
        pass
    else:
        raise AssertionError('Native finishing accepted a missing texture dependency')
    assert sha(project.root/fixture['source_ref']['path']) == fixture['source_ref']['sha256']
    assert sha(project.root/fixture['resource']['file_ref']['path']) == fixture['resource']['file_ref']['sha256']
    assert data_ids() == baseline and live_geometry() == before and set(bpy.context.selected_objects) == selected
    assert bpy.context.view_layer.objects.active == active and bpy.context.scene.frame_current == live_frame
    receipt = {'version': 1, 'status': 'NATIVE_ASSET_EXPORT_PASS', 'purpose': 'SYNTHETIC_FUNCTION_FIXTURE_ONLY',
               'finishing': result, 'export': exported, 'incomplete_lod': partial,
               'journals': [finishing_journal, export_journal, partial_journal],
               'wrong_sewn_uv_refused': True, 'missing_resource_refused': True, 'manual_motion_claim_not_qualified': True,
               'native_shape_key_action_reopened': True, 'shape_key_owner_without_object_action': True,
               'source_files_unchanged': True, 'live_context_unchanged': True,
               'production_connection': False, 'production_inventory': 'NOT_EXECUTED', 'fitting': 'NOT_EXECUTED',
               'garment_motion': 'NOT_EXECUTED', 'artistic_acceptance': 'NOT_EXECUTED', 'blender_version': bpy.app.version_string}
    atomic_json(output/'receipt.json', receipt)
    print(json.dumps({'status': receipt['status'], 'receipt': str(output/'receipt.json'), 'purpose': receipt['purpose']}))


if __name__ == '__main__':
    argv = sys.argv[sys.argv.index('--')+1:] if '--' in sys.argv else sys.argv[1:]
    args = arguments(argv)
    if args.validate_only:
        print(json.dumps({'arguments_valid': True, 'native_executed': False, 'output': str(args.output)}))
    else:
        run(args.output)
