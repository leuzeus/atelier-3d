"""Native synchronized animation transport from an existing canonical TEST_ONLY leaf.

Run only isolated Blender --background --factory-startup --python-exit-code 1.
The source is an actual TEST_ONLY Cloth campaign: its existing SQLite journal
is extended by new native fixture operations, never copied or forged. Three
transport clips reuse that one physical experiment to exercise Action changes;
they do not claim three separate physical body-movement experiments.
"""
import argparse
import copy
from pathlib import Path
import runpy
import sys

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))


def arguments(argv):
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--output', required=True)
    parser.add_argument('--source-project', required=True)
    parser.add_argument('--source-receipt', required=True)
    parser.add_argument('--validate-only', action='store_true')
    args = parser.parse_args(argv)
    output, project, receipt = map(Path, (args.output, args.source_project, args.source_receipt))
    if (not all(path.is_absolute() and path.drive.lower() == 'g:' for path in (output, project, receipt)) or
            output.exists() or not (project/'.a3d/state.sqlite3').is_file() or not receipt.is_file() or
            not receipt.resolve().is_relative_to(project.resolve()) or output.resolve().is_relative_to(ROOT/'assets')):
        parser.error('Require a new G: output, an existing exact project and its canonical leaf receipt')
    args.output, args.source_project, args.source_receipt = output.resolve(), project.resolve(), receipt.resolve()
    return args


def dispatch(project, operation, profile_path, references, campaign, label, statuses):
    from a3d.core import atomic_json
    from a3d.runs import create_run, next_run_step, run_status
    spec = {'version': 1, 'id': 'native.composition.'+campaign+'.'+label, 'kind': 'export',
            'asset_id': project.state()['asset']['id'], 'inputs': [], 'budgets': {'max_attempts': 1, 'max_seconds': 1200.},
            'units': [{'id': label, 'dependencies': [], 'executor': 'blender', 'operation': operation,
                       'arguments': {'profile_path': profile_path.relative_to(project.root).as_posix()},
                       'inputs': references, 'success_statuses': statuses}]}
    path = project.data/('native-compose-'+campaign+'.'+label+'.run.json'); atomic_json(path, spec)
    created = create_run(project, 'export', path.relative_to(project.root).as_posix())
    prepared = next_run_step(project, created['run_id'])
    assert prepared['status'] == 'AWAITING_CONFIRMATION', prepared
    operation_result = runpy.run_path(str(ROOT/'blender/bootstrap.py'))['dispatch_current'](str(project.root), operation, spec['units'][0]['arguments'])
    status = run_status(project, created['run_id']); unit = status['units'][0]
    assert unit['status'] == 'COMPLETED', status
    return operation_result, {'run_id': created['run_id'], 'receipt': unit['attempts'][0]['receipt']}


def run(output, source_project, source_receipt):
    import bpy
    from a3d.core import StudioError, atomic_json, digest, read_json, sha
    from a3d.store import Project
    from a3d.garment_motion import canonical_garment_clip
    from a3d.animated_delivery import prepare_composed_export_profile
    from a3d.export_profiles import export_descriptor, verify_export_manifest
    from blender.body_source import data_ids, live_geometry
    from tests.test_animated_delivery import profile
    assert bpy.app.background and not bpy.data.filepath and bpy.context.mode == 'OBJECT'
    project = Project(source_project); reference = {'path': source_receipt.relative_to(project.root).as_posix(), 'sha256': sha(source_receipt)}
    leaf, origin = canonical_garment_clip(project, reference)
    if leaf['purpose'] != 'TEST_ONLY': raise StudioError('Synthetic composition fixture refuses all production source projects/leaves')
    output.mkdir(parents=True, exist_ok=False); campaign = digest(str(output))[:12]
    inventory = leaf['object_inventory']['garment']
    expected = [{key: inventory[key] for key in ('component_id', 'source_pieces', 'package_sha256')}]
    if expected[0]['package_sha256'] is None: expected[0].pop('package_sha256')
    expected[0]['kind'] = 'TEXTILE'
    value = profile([reference], expected)
    value['clips'] = [{'id': 'transport-'+letter, 'source_receipts': [reference]} for letter in ('a', 'b', 'c')]
    needed = 1+3*(leaf['clip']['frame_end']-leaf['clip']['frame_start']+1)
    value['budgets'].update(max_seconds=900., max_samples=needed+1, max_cache_vertex_frames=10000000)
    source_refs = {reference['path']: reference['sha256'], origin['receipt']['path']: origin['receipt']['sha256']}
    def collect(document):
        if isinstance(document, dict):
            if set(document) == {'path', 'sha256'}:
                source_refs[document['path']] = document['sha256']
            else:
                for child in document.values(): collect(child)
        elif isinstance(document, list):
            for child in document: collect(child)
    collect(leaf)
    protected = dict(source_refs)
    baseline, live = data_ids(), live_geometry()
    directory = project.data/('native-composition-'+campaign); directory.mkdir(parents=True, exist_ok=False)
    path = directory/'composition.json'; atomic_json(path, value)
    source_refs[path.relative_to(project.root).as_posix()] = sha(path)
    references = [{'path': name, 'sha256': identity} for name, identity in sorted(source_refs.items())]
    result, composition_journal = dispatch(project, 'compose_animated_delivery', path, references, campaign, 'compose', ['CLIPS_EXECUTED'])
    assert result['purpose'] == 'TEST_ONLY' and result['whole_asset_inventory_status'] == 'TEST_INVENTORY_ONLY'
    assert result['qualification_scope'] == 'FUNCTION_FIXTURE_ANIMATION_ONLY' and result['qualified_whole_asset'] is False
    assert result['source_comparison']['sample_count'] == needed-1 and result['native_reimport_comparison']['sample_count'] == needed
    assert len(result['clips']) == 3 and all(row['tracks'] and row['animation_target'] == 'OBJECT' for row in result['clips'])
    assert all(row['tracks'][0]['animation_target'] == 'SHAPE_KEYS' for row in result['clips'])
    template = read_json(project.root/result['export_profile_template']['path'])
    generated = prepare_composed_export_profile(project, result['receipt'], (directory/'export.json').relative_to(project.root).as_posix())
    export_profile = read_json(project.root/generated['path'])
    assert template['motion_receipts'] == [] and export_profile['motion_receipts'] == [composition_journal['receipt']]
    inputs = export_descriptor(project, generated['path'])
    assert inputs['receipts'][0]['clip_measurements_verified'] == ['transport-a', 'transport-b', 'transport-c']
    refs = [generated, result['candidate'], composition_journal['receipt']]
    exported, export_journal = dispatch(project, 'export_blender_animation', project.root/generated['path'], refs, campaign, 'export', ['BLENDER_EXPORT_REOPENED'])
    verified = verify_export_manifest(project, exported)
    assert verified['animation_qualification'] == 'EXACT_CANDIDATE_CLIPS_VERIFIED'
    assert exported['clips_executed'] == ['transport-a', 'transport-b', 'transport-c']
    assert exported['fitting'] == 'NOT_GRANTED' and exported['artistic_review'] == 'REQUIRED'
    for name, identity in protected.items(): assert sha(project.root/name) == identity
    assert data_ids() == baseline and live_geometry() == live
    receipt = {'version': 1, 'status': 'NATIVE_SYNCHRONIZED_COMPOSITION_TRANSPORT_PASS', 'scope': 'FUNCTION_FIXTURE_ANIMATION_ONLY',
               'source_project': str(source_project), 'physical_experiment_count': 1, 'transport_clip_count': 3,
               'composition': result, 'composition_journal': composition_journal, 'export': exported,
               'export_journal': export_journal, 'verification': verified, 'original_source_files_preserved': True,
               'fitting': 'NOT_QUALIFIED', 'whole_asset_qualification': 'NOT_GRANTED', 'artistic_review': 'REQUIRED'}
    atomic_json(output/'receipt.json', receipt)
    print('NATIVE_SYNCHRONIZED_COMPOSITION_TRANSPORT_PASS: '+str(output/'receipt.json'))


if __name__ == '__main__':
    argv = sys.argv[sys.argv.index('--')+1:] if '--' in sys.argv else sys.argv[1:]
    args = arguments(argv)
    if args.validate_only: print('ARGUMENTS_VALIDATED: no native operation executed')
    else: run(args.output, args.source_project, args.source_receipt)
