"""Whole-clip moving colliders and re-opened rig/Action identity on both bodies.

Input is an existing native_body_target receipt of the current code candidate.
Run in isolated Blender factory-startup; no production file or MCP connection.
"""
import argparse
import json
from pathlib import Path
import shutil
import sys
import runpy

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))


def copy_target_inputs(body_receipt_path, output):
    """Create a fresh canonical project and copy only exact source-body inputs.

    Never copy SQLite, gates, run journals, project snapshots or execution PASS.
    Preserving relative file names keeps source descriptors byte-identical.
    """
    from a3d.body_source import selection
    from a3d.core import StudioError, atomic_json, digest, inside, read_json, sha
    from a3d.store import Project
    source_project = Project(body_receipt_path.parent/'project')
    source_database_sha = sha(source_project.db)
    source_asset = read_json(source_project.data/'asset.json')
    if digest(source_asset) != digest(source_project.state()['asset']):
        raise StudioError('Native source asset differs from its canonical specification')
    project = Project.create(output/'project', source_asset)
    if sha(project.data/'asset.json') != sha(source_project.data/'asset.json'):
        raise StudioError('Fresh native campaign did not preserve its exact asset specification')
    previous = read_json(body_receipt_path)
    if previous.get('status') != 'NATIVE_BODY_TARGET_PASS':
        raise StudioError('Native campaign requires a measured target-body manifest')
    references = {}
    def collect(value):
        if isinstance(value, dict):
            if {'path', 'sha256'} <= set(value):
                path = value['path']; identity = value['sha256']
                if not isinstance(path, str) or Path(path).is_absolute():
                    raise StudioError('Body-input copy accepts only project-relative exact references')
                if path in references and references[path] != identity:
                    raise StudioError('Body-input manifest has contradictory file identities')
                references[path] = identity
            else:
                for child in value.values(): collect(child)
        elif isinstance(value, list):
            for child in value: collect(child)
    for entry in previous['reports']:
        body = entry['result']
        collect(body['evidence']); collect(body['artifact']); collect(body['artifacts']); collect(body['receipt'])
        selected, source, _ = selection(source_project, body['evidence']['selection']['path'])
        if source.is_relative_to(source_project.root):
            references[source.relative_to(source_project.root).as_posix()] = selected['source_sha256']
        else:
            raise StudioError('Native catalog campaign requires source bodies inside its source project')
    forbidden = {'.a3d/state.sqlite3', '.a3d/project.json', '.a3d/asset.json', '.a3d/blender/session.json'}
    copied = []
    for relative, identity in sorted(references.items()):
        if relative in forbidden or relative.startswith(('.a3d/runs/', '.a3d/decisions/')):
            raise StudioError('Native body manifest cannot transfer canonical state, runs or human decisions')
        source = inside(source_project.root, relative)
        if not source.is_file() or sha(source) != identity:
            raise StudioError('Native body input is missing or changed: '+relative)
        destination = inside(project.root, relative, False)
        if destination.exists():
            raise StudioError('Native body input would overwrite a fresh campaign file: '+relative)
        destination.parent.mkdir(parents=True, exist_ok=True)
        shutil.copyfile(source, destination)
        if sha(source) != identity or sha(destination) != identity:
            raise StudioError('Native body input copy changed bytes: '+relative)
        copied.append({'path': relative, 'sha256': identity})
    if sha(source_project.db) != source_database_sha:
        raise StudioError('Native campaign input copy changed the original canonical project')
    state = project.state()
    if state['stage'] != 'INIT' or state['gates'] or state['evidence']:
        raise StudioError('Native campaign inherited an old qualification or approval gate')
    manifest = {'version': 1, 'status': 'EXACT_BODY_INPUTS_COPIED_TO_FRESH_PROJECT',
                'source_manifest': {'path': str(body_receipt_path), 'sha256': sha(body_receipt_path)},
                'source_database_sha256': source_database_sha, 'asset_sha256': sha(project.data/'asset.json'),
                'copied_inputs': copied, 'canonical_database_copied': False,
                'run_journals_copied': False, 'approval_gates_copied': False,
                'source_project_unchanged': True, 'qualification': 'NOT_TRANSFERRED'}
    atomic_json(output/'input-copy-manifest.json', manifest)
    return project, source_project, manifest


def arguments(argv):
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--output', required=True)
    parser.add_argument('--body-target-receipt', required=True)
    parser.add_argument('--validate-only', action='store_true')
    args = parser.parse_args(argv)
    output, receipt = Path(args.output), Path(args.body_target_receipt)
    if not output.is_absolute() or output.exists() or not receipt.is_absolute() or not receipt.is_file():
        parser.error('Use an absolute new output directory and an absolute existing target receipt')
    args.output, args.body_target_receipt = output.resolve(), receipt.resolve()
    if args.output.is_relative_to(ROOT/'assets'):
        parser.error('Native motion output cannot be stored among immutable source assets')
    return args


def run(output, body_receipt_path):
    import bpy
    from a3d.core import StudioError, atomic_json, digest, read_json, sha
    from a3d.motion_profiles import standard_motion_profile
    from blender.body_motion import evaluate_clip, prepare_motion_inputs, action_payload, native_weights_payload
    from a3d.runs import create_run, next_run_step, run_status
    from blender.body_source import data_ids, live_geometry
    assert bpy.app.background and not bpy.data.filepath
    previous = read_json(body_receipt_path)
    assert previous['status'] == 'NATIVE_BODY_TARGET_PASS'
    output.mkdir(parents=True, exist_ok=False)
    project, source_project, input_manifest = copy_target_inputs(body_receipt_path, output)
    campaign_id = digest({'output': str(output.resolve())})[:12]
    campaign_inputs = project.data/'native-motion-inputs'/campaign_id
    campaign_inputs.mkdir(parents=True, exist_ok=False)
    baseline = data_ids(); before_geometry = live_geometry(); reports = []
    before_selected = {obj.name for obj in bpy.context.selected_objects}
    before_active = bpy.context.view_layer.objects.active
    for item in previous['reports']:
        target_receipt = item['result']['receipt']['path']
        specification = prepare_motion_inputs(project, target_receipt)['specification']
        assert specification['source_adapter_rebound'] is False
        for clip_id in ('walk', 'elbow_flexion', 'arm_raise'):
            profile = standard_motion_profile(clip_id, specification, 'native declared inspection clip, movement/artistic review required')
            profile_path = campaign_inputs/(item['catalog_id']+'.'+clip_id+'.motion.json'); atomic_json(profile_path, profile)
            arguments = {'body_target_receipt_path': target_receipt,
                         'motion_profile_path': profile_path.relative_to(project.root).as_posix()}
            specification_id = item['catalog_id']+'.'+clip_id+'.motion-run.'+campaign_id
            spec = {'version': 1, 'id': specification_id, 'kind': 'motion',
                    'asset_id': 'test-character', 'inputs': [],
                    'budgets': {'max_attempts': 1, 'max_seconds': 600.},
                    'units': [{'id': 'prepare-motion', 'dependencies': [], 'executor': 'blender',
                               'operation': 'prepare_body_motion', 'arguments': arguments,
                               'success_statuses': ['CLIP_SAMPLES_COMPLETE'],
                               'inputs': [{'path': target_receipt, 'sha256': sha(project.root/target_receipt)},
                                          {'path': arguments['motion_profile_path'], 'sha256': sha(profile_path)}]}]}
            spec_path = campaign_inputs/(specification_id+'.json'); atomic_json(spec_path, spec)
            run_info = create_run(project, 'motion', spec_path.relative_to(project.root).as_posix())
            prepared = next_run_step(project, run_info['run_id']); assert prepared['status'] == 'AWAITING_CONFIRMATION'
            dispatch = runpy.run_path(str(ROOT/'blender/bootstrap.py'))['dispatch_current']
            motion = dispatch(str(project.root), 'prepare_body_motion', arguments)
            assert motion['status'] == 'CLIP_SAMPLES_COMPLETE', motion['coverage']
            samples = read_json(project.root/motion['samples_artifact']['path'])
            assert samples['samples'][0]['time'] == 1. and samples['samples'][-1]['time'] == 25.
            assert len(samples['samples']) == 49 and all(row['collider_tree_created'] for row in samples['samples'])
            assert any(row['max_increment_cm'] > 0. for row in samples['coverage']['intervals'])
            assert data_ids() == baseline and live_geometry() == before_geometry
            journal = run_status(project, run_info['run_id'])
            assert journal['units'][0]['status'] == 'COMPLETED', journal
            assert journal['units'][0]['attempts'][0]['receipt_event_id']
            assert {obj.name for obj in bpy.context.selected_objects} == before_selected
            assert bpy.context.view_layer.objects.active == before_active
            temporary = bpy.data.scenes.new('NATIVE.MOTION.REOPEN'); temporary.unit_settings.system = 'METRIC'
            temporary.unit_settings.scale_length = 1.
            with bpy.data.libraries.load(str(project.root/motion['artifact']['path']), link=False) as (available, loaded):
                assert len(available.objects) == 2 and len(available.armatures) == 1 and len(available.actions) == 1
                loaded.objects = list(available.objects)
            for obj in loaded.objects: temporary.collection.objects.link(obj)
            body = next(obj for obj in loaded.objects if obj.type == 'MESH')
            rig = next(obj for obj in loaded.objects if obj.type == 'ARMATURE')
            with bpy.context.temp_override(scene=temporary, view_layer=temporary.view_layers[0]):
                bpy.context.view_layer.update()
                reopened = evaluate_clip(body, rig, profile, specification, author=False)
                assert reopened['motion_binding'] == motion['motion_binding']
                assert reopened['action_sha256'] == digest(action_payload(rig.animation_data.action))
                assert reopened['weights_sha256'] == digest(native_weights_payload(body, rig))
                assert reopened['samples'] == samples['samples']
                # A modified channel cannot reuse the declared clip evidence.
                curve = next(iter(rig.animation_data.action.layers[0].strips[0].channelbags[0].fcurves))
                curve.keyframe_points[1].co[1] += .01
                try:
                    evaluate_clip(body, rig, profile, specification, author=False)
                except StudioError as error:
                    assert 'Action keys changed' in str(error)
                else:
                    raise AssertionError('Changed Action silently reused declared motion')
            bpy.data.batch_remove(ids=data_ids()-baseline)
            reports.append({'catalog_id': item['catalog_id'], 'clip': clip_id,
                            'motion': motion, 'native_reopened_exact': True, 'action_mutation_refused': True,
                            'native_dispatch_journal_registered': True, 'run_id': run_info['run_id']})
    result = {'version': 1, 'status': 'NATIVE_BODY_MOTION_PASS', 'reports': reports,
              'source_receipt': {'path': str(body_receipt_path), 'sha256': sha(body_receipt_path)},
              'input_copy_manifest': {'path': str(output/'input-copy-manifest.json'), 'sha256': sha(output/'input-copy-manifest.json')},
              'qualification': 'BODY_MOTION_SAMPLES_ONLY', 'bone_axis_review': 'REQUIRED',
              'garment_contacts': 'NOT_EXECUTED', 'simulation': 'NOT_EXECUTED', 'fitting': 'NOT_EXECUTED',
              'live_scene_unchanged': True, 'native_body_operation_db_unchanged': True,
              'native_dispatch_journal_registered': True, 'production_connection': False,
              'blender_version': bpy.app.version_string}
    atomic_json(output/'receipt.json', result)
    assert sha(source_project.db) == input_manifest['source_database_sha256']
    print(json.dumps({'status': result['status'], 'receipt': str(output/'receipt.json'), 'reports': len(reports)}))


if __name__ == '__main__':
    argv = sys.argv[sys.argv.index('--')+1:] if '--' in sys.argv else sys.argv[1:]
    args = arguments(argv)
    if args.validate_only:
        print(json.dumps({'arguments_valid': True, 'native_executed': False, 'output': str(args.output)}))
    else:
        run(args.output, args.body_target_receipt)
