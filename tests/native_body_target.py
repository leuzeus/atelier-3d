"""Factory-startup native target operation on both immutable catalog bodies.

Run through a fresh native Blender background process, never production MCP.
Ordinary Python --validate-only checks arguments without running Blender.
"""
import argparse
import json
from pathlib import Path
import sys
import runpy

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))


def arguments(argv):
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--output', required=True)
    parser.add_argument('--validate-only', action='store_true')
    args = parser.parse_args(argv); output = Path(args.output)
    if not output.is_absolute() or output.exists():
        parser.error('--output must identify an absolute new directory')
    args.output = output.resolve()
    if args.output.is_relative_to(ROOT/'assets'):
        parser.error('Native output cannot be written among immutable assets')
    return args


def run(output):
    import bpy
    from a3d.core import atomic_json, read_json, sha
    from a3d.mannequins import catalog, select_catalog_body
    from a3d.store import Project
    from blender.body_source import data_ids, live_geometry
    from a3d.runs import create_run, next_run_step, run_status
    from tests.support import asset
    from tests.test_body_target import target_fixture
    assert bpy.app.background and not bpy.data.filepath
    output.mkdir(parents=True, exist_ok=False)
    project = Project.create(output/'project', asset(True)); reports = []
    baseline_ids = data_ids(); baseline_live = live_geometry()
    source_hashes = {entry['id']: entry['sha256'] for entry in catalog()['entries']}
    for entry in catalog()['entries']:
        selected = select_catalog_body(project, entry['id'])
        target = target_fixture(selected['selection']['sha256'], selected['anatomy_adapter']['sha256'])
        target['anatomy_adapter'] = selected['anatomy_adapter']
        target['orientation'] = dict(entry['orientation'], origin_cm=[0., 0., 0.])
        target['provenance']['source_ref'] = 'native test declared 180 cm; anatomical acceptance not granted'
        path = project.root/(entry['id']+'.target.json'); atomic_json(path, target)
        arguments = {'selection_path': selected['selection']['path'], 'target_path': path.relative_to(project.root).as_posix()}
        specification = {'version': 1, 'id': entry['id']+'.target-run', 'kind': 'garment',
                         'asset_id': 'test-character', 'inputs': [],
                         'budgets': {'max_attempts': 1, 'max_seconds': 300.},
                         'units': [{'id': 'prepare-body', 'dependencies': [], 'executor': 'blender',
                                    'operation': 'prepare_body_target', 'arguments': arguments,
                                    'success_statuses': ['NATIVE_BODY_TARGET_MEASURED'],
                                    'inputs': [selected['selection'], selected['anatomy_adapter'],
                                               {'path': arguments['target_path'], 'sha256': sha(path)}]}]}
        spec_path = project.root/(entry['id']+'.run.json'); atomic_json(spec_path, specification)
        run_info = create_run(project, 'garment', spec_path.relative_to(project.root).as_posix())
        next_step = next_run_step(project, run_info['run_id']); assert next_step['status'] == 'AWAITING_CONFIRMATION'
        # Native isolated test harness invokes the actual fresh-install bootstrap;
        # it does not constitute permission for a production MCP call.
        dispatch = runpy.run_path(str(ROOT/'blender/bootstrap.py'))['dispatch_current']
        result = dispatch(str(project.root), 'prepare_body_target', arguments)
        assert result['status'] == 'NATIVE_BODY_TARGET_MEASURED', result
        assert result['native_reopened'] and abs(result['measured_stature_cm']-180.) <= .0001
        assert result['fitting'] == 'NOT_EXECUTED' and result['rig_creation'] == 'NOT_EXECUTED'
        assert result['adapter_rebound_to_variant'] is False
        assert data_ids() == baseline_ids and live_geometry() == baseline_live
        journal = run_status(project, run_info['run_id'])
        assert journal['units'][0]['status'] == 'COMPLETED', journal
        assert journal['units'][0]['attempts'][0]['receipt_event_id']
        assert not (project.data/'blender/session.json').exists()
        receipt = read_json(project.root/result['receipt']['path'])
        assert receipt['cache_key'] == result['cache_key']
        assert sha(project.root/selected['source']['path']) == source_hashes[entry['id']]
        reports.append({'catalog_id': entry['id'], 'result': result,
                        'native_dispatch_journal_registered': True, 'run_id': run_info['run_id']})
    assert all(sha(ROOT/'assets/mannequins'/entry['file']) == source_hashes[entry['id']] for entry in catalog()['entries'])
    result = {'version': 1, 'status': 'NATIVE_BODY_TARGET_PASS', 'reports': reports,
              'qualification': 'GEOMETRY_ONLY', 'target_stature_cm': 180.,
              'live_scene_unchanged': True, 'body_operation_db_unchanged': True,
              'journal_updated_by_native_dispatch': True, 'production_connection': False,
              'fitting': 'NOT_EXECUTED', 'blender_version': bpy.app.version_string}
    atomic_json(output/'receipt.json', result)
    print(json.dumps({'status': result['status'], 'receipt': str(output/'receipt.json'), 'qualification': result['qualification']}))


if __name__ == '__main__':
    argv = sys.argv[sys.argv.index('--')+1:] if '--' in sys.argv else sys.argv[1:]
    args = arguments(argv)
    if args.validate_only:
        print(json.dumps({'arguments_valid': True, 'native_executed': False, 'output': str(args.output)}))
    else:
        run(args.output)
