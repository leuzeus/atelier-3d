"""Checkpointed exact body introduction and idempotence on fresh test state.

Run only in isolated factory-startup Blender with --python-exit-code 1.
This proves import/collision identity, never garment fitting or human review.
"""
import argparse
import json
from pathlib import Path
import runpy
import sys

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))


def arguments(argv):
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--output', required=True); parser.add_argument('--body-target-receipt', required=True)
    parser.add_argument('--validate-only', action='store_true'); args = parser.parse_args(argv)
    output, receipt = Path(args.output), Path(args.body_target_receipt)
    if not output.is_absolute() or output.exists() or not receipt.is_file() or output.resolve().is_relative_to(ROOT/'assets'):
        parser.error('Use a new absolute output directory and an existing measured-body manifest')
    args.output, args.body_target_receipt = output.resolve(), receipt.resolve()
    return args


def _managed(project, path, tag):
    from a3d.body_context import body_context_descriptor
    from a3d.core import atomic_json, digest
    from a3d.runs import create_run, next_run_step, run_status
    inputs = body_context_descriptor(project, path.relative_to(project.root).as_posix())
    spec = {'version': 1, 'id': 'native.body-context.'+tag+'.'+digest(str(project.root))[:12],
            'kind': 'garment', 'asset_id': project.state()['asset']['id'], 'inputs': [],
            'budgets': {'max_attempts': 1, 'max_seconds': 600.},
            'units': [{'id': 'body-context', 'dependencies': [], 'executor': 'blender', 'operation': 'introduce_body_target',
                       'arguments': {'context_path': path.relative_to(project.root).as_posix()},
                       'inputs': inputs['evidence'], 'success_statuses': ['BODY_TARGET_INTRODUCED']}]}
    spec_path = project.data/('native-body-context-'+tag+'.json'); atomic_json(spec_path, spec)
    info = create_run(project, 'garment', spec_path.relative_to(project.root).as_posix())
    assert next_run_step(project, info['run_id'])['status'] == 'AWAITING_CONFIRMATION'
    dispatch = runpy.run_path(str(ROOT/'blender/bootstrap.py'))['dispatch_current']
    result = dispatch(str(project.root), 'introduce_body_target', spec['units'][0]['arguments'])
    state = run_status(project, info['run_id']); assert state['units'][0]['status'] == 'COMPLETED'
    attempt = state['units'][0]['attempts'][0]
    assert attempt['receipt_event_id'] and attempt['entry_checkpoint'] and not project.state().get('pending_blender_operation')
    return result, {'run_id': info['run_id'], 'receipt': attempt['receipt'], 'checkpoint': attempt['entry_checkpoint']}


def _prepare_test_construction(project):
    """Generate scoped test-only gates in fresh state; never copy prior reviews."""
    from a3d.core import atomic_json, digest
    from a3d.packages import build_package
    from a3d.planning import build_board, propose
    from tests.support import (asset, construction_dossier, garment_source, png,
                               prepare_synthetic_exploded, PROVENANCE)
    assert digest(project.state()['asset']) == digest(asset(True))
    atomic_json(project.data/'evidence/brief.json', {'brief': 'BODY_CONTEXT_SYNTHETIC_FIXTURE_ONLY'})
    project.evidence('brief', '.a3d/evidence/brief.json')
    project.transition('SPECIFIED', 'brief'); project.transition('REFERENCES_READY', 'brief')
    source = project.data/'source/package'; garment_source(source)
    (project.data/'source/original.png').write_bytes(png()); project.evidence('reference.original', '.a3d/source/original.png')
    project.gate('references', True, 'SYNTHETIC fixture references only', ['brief', 'reference.original'], 'test:fixture-only')
    project.transition('REFERENCES_APPROVED', 'brief'); project.transition('ANALYZED', 'brief'); propose(project)
    project.gate('route.garment.coat', True, 'SYNTHETIC route only', ['pipeline-proposal'], 'test:fixture-route')
    project.resolve_route('garment.coat', 'PATTERN_SEWN'); project.transition('ROUTED', 'brief')
    package = project.data/'packages/component.garmentpkg'
    build_package(source, package, 'test-character', 'garment.coat', 'PATTERN_SEWN', PROVENANCE)
    project.bind_package('garment.coat', package.relative_to(project.root).as_posix()); project.transition('PACKAGED', 'brief')
    prepare_synthetic_exploded(project, construction_dossier(project, True))
    build_board(project, '.a3d/evidence/construction.json')
    project.gate('construction', True, 'SYNTHETIC cutting board only', ['construction-board'], 'test:fixture-board')
    project.transition('RECONSTRUCTING', 'brief')


def run(output, body_receipt_path):
    import bpy
    from a3d.core import atomic_json, read_json, sha
    from blender.body_target import evaluated_mesh
    from tests.native_body_motion import copy_target_inputs
    from tests.test_body_context import context_profile
    assert bpy.app.background and not bpy.data.filepath and bpy.context.mode == 'OBJECT'
    output.mkdir(parents=True, exist_ok=False)
    project, source_project, copy_manifest = copy_target_inputs(body_receipt_path, output)
    _prepare_test_construction(project)
    source_database = sha(source_project.db); before = read_json(body_receipt_path)
    scene = bpy.data.scenes.new('A3D.Native.BodyContext'); scene.unit_settings.system = 'METRIC'; scene.unit_settings.scale_length = 1.
    bpy.context.window.scene = scene
    working = project.data/'blender/working-native-body-context.blend'
    bpy.ops.wm.save_as_mainfile(filepath=str(working), check_existing=False)
    atomic_json(project.data/'blender/session.json', {'original': None, 'working': str(working)})
    reports = []
    for index, entry in enumerate(before['reports']):
        target = entry['result']; context = context_profile(target['receipt'], 'A3D.BodyTarget.NativeContext.'+str(index))
        path = project.root/('context-'+str(index)+'.json'); atomic_json(path, context)
        first, journal = _managed(project, path, 'first-'+str(index)); obj = bpy.data.objects[first['object']]
        actual, _ = evaluated_mesh(obj, bpy.context.evaluated_depsgraph_get(), 1.)
        expected = read_json(project.root/target['artifacts']['geometry']['path'])
        assert actual == {key: expected[key] for key in ('vertices_cm', 'faces', 'face_sets')}
        assert first['status'] == 'BODY_TARGET_INTRODUCED' and not first['idempotent_reuse']
        assert first['profile_cache_key'] == target['profile_cache_key'] and first['fitting'] == 'NOT_EXECUTED'
        count = len(bpy.data.objects); repeat, repeat_journal = _managed(project, path, 'repeat-'+str(index))
        assert repeat['idempotent_reuse'] and repeat['object'] == first['object'] and len(bpy.data.objects) == count
        immutable = sha(project.root/first['artifact']['path'])
        # Reopen the immutable output witness, then reconnect the working copy.
        bpy.ops.wm.open_mainfile(filepath=str(project.root/first['artifact']['path']), load_ui=False)
        obj = bpy.data.objects[first['object']]
        reopened, _ = evaluated_mesh(obj, bpy.context.evaluated_depsgraph_get(), 1.)
        assert reopened == actual and obj['a3d_profile_cache_key'] == first['profile_cache_key']
        assert len([mod for mod in obj.modifiers if mod.type == 'COLLISION']) == 1
        bpy.ops.wm.open_mainfile(filepath=str(working), load_ui=False)
        assert sha(project.root/first['artifact']['path']) == immutable
        reports.append({'catalog_id': entry['catalog_id'], 'first': first, 'repeat': repeat,
                        'reopened_exact_geometry': True, 'journals': [journal, repeat_journal]})
    # A changed connected collider cannot be silently relabelled or repaired
    # as an idempotent introduction. Preserve the failure and restore its entry.
    last = reports[-1]['first']; obj = bpy.data.objects[last['object']]
    obj.collision.thickness_outer = .002
    dispatch = runpy.run_path(str(ROOT/'blender/bootstrap.py'))['dispatch_current']
    try:
        dispatch(str(project.root), 'introduce_body_target', {'context_path': path.relative_to(project.root).as_posix()})
    except ValueError as error:
        assert 'collision settings' in str(error)
    else:
        raise AssertionError('Changed body collider was admitted as the original exact context')
    assert project.state().get('pending_blender_operation')
    recovery = dispatch(str(project.root), 'restore_checkpoint', {})
    # The checkpoint deliberately preserves the observed changed setting; it
    # restores the operation boundary, never invents anatomical acceptance.
    assert not project.state().get('pending_blender_operation')
    assert sha(source_project.db) == source_database
    for entry in before['reports']:
        for ref in [entry['result']['artifact'], *entry['result']['artifacts'].values(), entry['result']['receipt']]:
            assert sha(project.root/ref['path']) == ref['sha256']
    receipt = {'version': 1, 'status': 'NATIVE_BODY_CONTEXT_PASS', 'purpose': 'BODY_CONTEXT_FUNCTION_FIXTURE_ONLY',
               'reports': reports, 'copy_manifest': copy_manifest, 'modified_collider_refused': True,
               'checkpoint_recovery': recovery, 'source_database_unchanged': True, 'source_body_inputs_unchanged': True,
               'test_construction_gates': 'GENERATED_SCOPED_SYNTHETIC_ONLY_NEVER_IMPORTED',
               'final_connected_collider': 'OBSERVED_CHANGED_INPUT_AT_RECOVERED_ENTRY_NOT_ACCEPTED',
               'simulation': 'NOT_EXECUTED', 'fitting': 'NOT_EXECUTED', 'anatomical_review': 'NOT_IMPORTED',
               'artistic_acceptance': 'NOT_EXECUTED', 'blender_version': bpy.app.version_string}
    atomic_json(output/'receipt.json', receipt)
    print(json.dumps({'status': receipt['status'], 'receipt': str(output/'receipt.json')}))


if __name__ == '__main__':
    args = arguments(sys.argv[sys.argv.index('--')+1:] if '--' in sys.argv else sys.argv[1:])
    if args.validate_only:
        print(json.dumps({'arguments_valid': True, 'native_executed': False, 'output': str(args.output)}))
    else:
        run(args.output, args.body_target_receipt)
