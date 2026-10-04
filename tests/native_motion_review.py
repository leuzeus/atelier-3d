"""Render actual canonical TEST_ONLY composition clips; no forged receipt or production gate.

Use Blender --background --factory-startup --offline-mode --python-exit-code 1.
The existing source project keeps its native journal. Only new review profiles,
rendered artefacts and their real dispatch receipts are added there.
"""
import argparse
from pathlib import Path
import sys

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))


def arguments(argv):
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--output', required=True)
    parser.add_argument('--source-project', required=True)
    parser.add_argument('--source-campaign-receipt', required=True)
    parser.add_argument('--display', choices=('BOTH', 'NEUTRAL', 'MATERIALS'), default='BOTH')
    parser.add_argument('--max-seconds', type=float, default=300.)
    parser.add_argument('--validate-only', action='store_true')
    args = parser.parse_args(argv)
    output, project, receipt = map(Path, (args.output, args.source_project, args.source_campaign_receipt))
    if (not all(path.is_absolute() and path.drive.lower() == 'g:' for path in (output, project, receipt)) or
            output.exists() or not (project/'.a3d/state.sqlite3').is_file() or not receipt.is_file() or
            output.resolve().is_relative_to(ROOT/'assets') or not 1 <= args.max_seconds <= 7200):
        parser.error('Require a new G: output, existing source journal/campaign and finite bounded render time')
    args.output, args.source_project, args.source_campaign_receipt = output.resolve(), project.resolve(), receipt.resolve()
    return args


def run(args):
    import bpy
    from a3d.core import StudioError, atomic_json, digest, read_json, sha
    from a3d.export_profiles import export_descriptor
    from a3d.review_motion import review_motion_descriptor
    from a3d.store import Project
    from blender.body_source import data_ids, live_geometry
    from tests.native_animated_delivery import dispatch
    assert bpy.app.background and not bpy.data.filepath and bpy.context.mode == 'OBJECT'
    source = read_json(args.source_campaign_receipt)
    if (source.get('status') != 'NATIVE_SYNCHRONIZED_COMPOSITION_TRANSPORT_PASS' or
            source.get('scope') != 'FUNCTION_FIXTURE_ANIMATION_ONLY' or
            Path(source.get('source_project', '')).resolve() != args.source_project or
            source.get('composition', {}).get('purpose') != 'TEST_ONLY'):
        raise StudioError('Motion review fixture requires the actual existing TEST_ONLY native composition campaign')
    project = Project(args.source_project); export_ref = source['export']['profile']
    if sha(project.root/export_ref['path']) != export_ref['sha256']:
        raise StudioError('Motion review source export profile differs from its real campaign receipt')
    inputs = export_descriptor(project, export_ref['path'])
    if (not inputs['receipts'] or any(row.get('purpose') != 'TEST_ONLY' or
                                     row.get('native_dispatch_verified') is not True for row in inputs['receipts'])):
        raise StudioError('Motion review fixture refuses production or noncanonical motion receipt sources')
    if len(inputs['profile']['clips']) != 3:
        raise StudioError('Motion review fixture requires the three declared source transport clips')
    campaign_sha = sha(args.source_campaign_receipt)
    protected = {ref['path']: ref['sha256'] for ref in inputs['evidence']}
    baseline, live = data_ids(), live_geometry()
    args.output.mkdir(parents=True, exist_ok=False); campaign = digest(str(args.output))[:12]
    folder = project.data/('native-motion-review-'+campaign); folder.mkdir(parents=True, exist_ok=False)
    modes = ['NEUTRAL', 'MATERIALS'] if args.display == 'BOTH' else [args.display]
    reports = []
    for mode in modes:
        export = inputs['profile']; still_count = sum(clip['frame_end']-clip['frame_start']+1 for clip in export['clips'])
        profile = {'version': 1, 'export_profile_ref': export_ref, 'object_names': list(export['object_names']),
                   'clip_ids': [clip['id'] for clip in export['clips']], 'fps': export['fps'],
                   'views': ['threequarter'], 'resolution': [128, 192], 'display': mode,
                   'budgets': {'max_render_frames': still_count*2, 'max_seconds': args.max_seconds,
                               'max_sample_vertex_frames': 5000000}}
        path = folder/(mode.lower()+'.json'); atomic_json(path, profile)
        descriptor = review_motion_descriptor(project, path.relative_to(project.root).as_posix())
        result, native = dispatch(project, 'render_motion_review', path, descriptor['evidence'],
                                  campaign, 'review-'+mode.lower(), ['REVIEW_MEDIA_RENDERED'])
        assert result['status'] == 'REVIEW_MEDIA_RENDERED', result
        assert result['rendered_frame_count'] == still_count*2
        assert len(result['images']) == still_count and len(result['movies']) == 3
        assert result['qualification'] == 'PIXELS_ONLY' and result['fitting'] == 'NOT_QUALIFIED'
        assert result['artistic_review'] == 'REQUIRED' and result['product_acceptance'] == 'NOT_GRANTED'
        for clip in export['clips']:
            expected = list(range(clip['frame_start'], clip['frame_end']+1))
            images = [row for row in result['images'] if row['clip_id'] == clip['id']]
            assert [row['frame'] for row in images] == expected
            film = next(row for row in result['movies'] if row['clip_id'] == clip['id'])
            assert film['frame_count'] == len(expected) and film['size'] == profile['resolution'] and film['fps'] == export['fps']
        for media in result['images']+result['movies']:
            assert sha(project.root/media['path']) == media['sha256']
        assert data_ids() == baseline and live_geometry() == live
        assert protected == {name: sha(project.root/name) for name in protected}
        assert sha(args.source_campaign_receipt) == campaign_sha
        reports.append({'display': mode, 'review': result, 'native_journal': native})
    receipt = {'version': 1, 'status': 'TEST_ONLY_NATIVE_MOTION_REVIEW_MEDIA_PASS',
               'source_project': str(args.source_project), 'source_campaign': str(args.source_campaign_receipt),
               'source_campaign_sha256': campaign_sha,
               'scope': 'PIXELS_ONLY', 'source_profile': export_ref, 'reports': reports,
               'source_files_preserved': True, 'fitting': 'NOT_QUALIFIED', 'artistic_review': 'REQUIRED',
               'whole_asset_qualification': 'NOT_GRANTED'}
    atomic_json(args.output/'receipt.json', receipt)
    print('TEST_ONLY_NATIVE_MOTION_REVIEW_MEDIA_PASS: '+str(args.output/'receipt.json'))


if __name__ == '__main__':
    argv = sys.argv[sys.argv.index('--')+1:] if '--' in sys.argv else sys.argv[1:]
    args = arguments(argv)
    if args.validate_only:
        print('ARGUMENTS_VALIDATED: no Blender render or journal mutation')
    else:
        run(args)
