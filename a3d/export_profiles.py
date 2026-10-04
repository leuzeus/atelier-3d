"""Exact Blender-animation export inputs and bounded native comparisons.

Reopening files verifies transport. Motion qualification is separate and must
come from complete clip receipts bound to the same candidate and Actions.
"""
import copy
import math
import sqlite3
from contextlib import closing

from .core import StudioError, contract, digest, inside, read_json, sha


def export_sample_times(clip):
    start, end, step = clip['frame_start'], clip['frame_end'], clip['sample_step']
    if end < start:
        raise StudioError('Export clip end precedes its start')
    times = list(range(start, end + 1, step))
    if times[-1] != end:
        times.append(end)
    return times


def clip_tracks(clip):
    """Primary legacy binding plus explicit simultaneous additional owners."""
    fields = ('object_name', 'action_name', 'slot_identifier')
    rows = [clip, *clip.get('tracks', [])]; result = []
    for row in rows:
        track = {key: row[key] for key in fields}
        track['animation_target'] = row.get('animation_target', 'OBJECT')
        if row.get('action_sha256') is not None:
            track['action_sha256'] = row['action_sha256']
        result.append(track)
    owners = [(row['object_name'], row['animation_target']) for row in result]
    if len(set(owners)) != len(owners):
        raise StudioError('A global export clip must bind each native animation owner exactly once')
    return result


def track_bindings(clip, action_sha=None):
    rows = clip_tracks(clip)
    if action_sha is not None:
        rows = [dict(row, action_sha256=action_sha.get(row['action_name'])) for row in rows]
    return sorted(rows, key=lambda row: (row['object_name'], row['animation_target']))


def validate_export_profile(profile):
    contract('export-profile', profile)
    objects = set(profile['object_names'])
    dependencies = set(profile['dependency_names'])
    if objects & dependencies:
        raise StudioError('Export objects and dependencies must be distinct')
    clips = profile['clips']
    if len({clip['id'] for clip in clips}) != len(clips):
        raise StudioError('Export clip identities must be unique')
    if any(clip['id'] == 'reference' for clip in clips):
        raise StudioError('Export clip identity reference is reserved for the source snapshot')
    for clip in clips:
        for track in clip_tracks(clip):
            if track['object_name'] not in objects | dependencies or track['action_name'] not in profile['action_names']:
                raise StudioError('Export clip tracks require explicit candidate objects and Actions')
        export_sample_times(clip)
    needed = sum(len(export_sample_times(clip)) for clip in clips) + 1
    if needed > profile['budgets']['max_samples']:
        raise StudioError('Export sample budget cannot cover all declared clips and endpoints')
    resources = profile['resources']
    if len({row['datablock_name'] for row in resources}) != len(resources):
        raise StudioError('Export resource datablock names must be unique')
    if set(profile['embedded_image_names']) & {row['datablock_name'] for row in resources}:
        raise StudioError('Embedded and external image declarations must be distinct')
    return profile


def export_descriptor(project, profile_path):
    path = inside(project.root, profile_path)
    profile = validate_export_profile(read_json(path))
    source = inside(project.root, profile['source_ref']['path'])
    if source.suffix.lower() != '.blend' or sha(source) != profile['source_ref']['sha256']:
        raise StudioError('Export requires the exact current native Blender candidate')
    evidence = [{'path': profile_path, 'sha256': sha(path)}, profile['source_ref']]
    for resource in profile['resources']:
        reference = resource['file_ref']
        if sha(inside(project.root, reference['path'])) != reference['sha256']:
            raise StudioError('Missing or changed export resource: ' + reference['path'])
        evidence.append(reference)
    receipts = []
    for reference in profile['motion_receipts']:
        receipt_path = inside(project.root, reference['path'])
        if sha(receipt_path) != reference['sha256']:
            raise StudioError('Export motion receipt changed')
        receipt = read_json(receipt_path)
        receipts.append(_motion_record(project, reference, receipt))
        evidence.append(reference)
    return {'profile': profile, 'source': source, 'receipts': receipts,
            'profile_ref': evidence[0], 'evidence': evidence, 'cache_key': digest(evidence)}


def _motion_record(project, reference, document):
    """Only a registered native callback can establish executed motion provenance."""
    if document.get('origin') != 'NATIVE_DISPATCH':
        payload = {key: value for key, value in document.items() if key not in ('cache_key', 'receipt')}
        if document.get('cache_key') != digest(payload):
            raise StudioError('Export motion receipt is not authenticated')
        return dict(document, native_dispatch_verified=False, clip_measurements_verified=[], clip_measured_meshes={})
    from .runs import _load, _verified_receipt, _verify_run
    with closing(sqlite3.connect(project.db)) as db:
        run = _load(db, document['run_id']); _verify_run(project, run)
        units = [row for row in run['units'] if row['id'] == document.get('unit_id')]
        if len(units) != 1 or units[0]['status'] != 'COMPLETED' or units[0]['executor'] != 'blender':
            raise StudioError('Export motion has no completed native run unit')
        unit = units[0]; attempts = [row for row in unit['attempts'] if row['id'] == document.get('attempt_id')]
        if len(attempts) != 1 or attempts[0].get('receipt') != reference:
            raise StudioError('Export motion receipt differs from its canonical attempt identity')
        native = _verified_receipt(project, db, run, unit, attempts[0])
        if native != document or native.get('execution') != 'RETURNED':
            raise StudioError('Export motion has no exact returned native dispatch')
    result = copy.deepcopy(native['result'])
    result['native_dispatch_verified'] = True
    result['clip_measurements_verified'], result['clip_measured_meshes'] = _measured_clips(project, native)
    return result


def _measured_clips(project, native):
    result = native['result']; reference = result.get('clips_artifact')
    if not reference or reference not in native['files']:
        return [], {}
    data = read_json(inside(project.root, reference['path']))
    if (data.get('candidate') != result.get('candidate') or data.get('fps') != result.get('fps') or
            data.get('scope') != 'EXACT_CANDIDATE_ANIMATION'):
        return [], {}
    verified = []; measured_meshes = {}
    for clip in result.get('clips', []):
        rows = [row for row in data.get('clips', []) if row.get('id') == clip.get('id')]
        if len(rows) != 1:
            continue
        measured = rows[0]
        if (any(measured.get(key) != clip.get(key) for key in ('object_name', 'action_name', 'slot_identifier', 'action_sha256')) or
                measured.get('animation_target', 'OBJECT') != clip.get('animation_target', 'OBJECT')):
            continue
        if track_bindings(measured) != track_bindings(clip):
            continue
        samples = measured.get('samples', [])
        if not samples or [sample.get('time') for sample in samples] != clip.get('executed_times'):
            continue
        topology = {}; complete = True; expected_names = set(samples[0].get('meshes', {}))
        for sample in samples:
            meshes = sample.get('meshes', {})
            if not meshes or set(meshes) != expected_names:
                complete = False; break
            for name, mesh in meshes.items():
                points, faces = mesh.get('vertices_cm', []), mesh.get('faces', [])
                if (not points or not faces or any(len(point) != 3 or any(type(v) not in (int, float) or not math.isfinite(v) for v in point) for point in points) or
                        any(len(face) < 3 or any(type(v) is not int or v < 0 or v >= len(points) for v in face) for face in faces) or
                        mesh.get('geometry_sha256') != digest([points, faces])):
                    complete = False; break
                identity = digest([len(points), faces])
                if name in topology and topology[name] != identity:
                    complete = False; break
                topology[name] = identity
            if not complete:
                break
            if set(meshes) != set(topology):
                complete = False; break
        if complete:
            verified.append(clip['id'])
            measured_meshes[clip['id']] = sorted(expected_names)
    return verified, measured_meshes


def motion_qualification(profile, receipts, native_actions, native_mesh_names=None):
    """Do not turn endpoint export samples, names or body-only tests into motion acceptance.

The accepted receipt format describes complete original clip execution. The
native Action digest is checked again while exporting, so old Action evidence
cannot qualify a new saved candidate merely because the name is unchanged.
"""
    qualified, missing = [], []
    for clip in profile['clips']:
        matches = []
        for receipt in receipts:
            if (receipt.get('candidate') != profile['source_ref'] or
                    receipt.get('status') != 'CLIPS_EXECUTED' or
                    receipt.get('scope') != 'EXACT_CANDIDATE_ANIMATION' or
                    receipt.get('temporal_coverage') != 'COMPLETE' or receipt.get('fps') != profile['fps'] or
                    receipt.get('native_dispatch_verified') is not True or clip['id'] not in receipt.get('clip_measurements_verified', [])):
                continue
            if native_mesh_names is not None and set(receipt.get('clip_measured_meshes', {}).get(clip['id'], [])) != set(native_mesh_names):
                continue
            for result in receipt.get('clips', []):
                times = result.get('executed_times', [])
                covered = (isinstance(times, list) and bool(times) and
                           all(type(value) in (int, float) and math.isfinite(value) for value in times) and
                           all(a < b for a, b in zip(times, times[1:])) and
                           times[0] == clip['frame_start'] and times[-1] == clip['frame_end'] and
                           set(range(clip['frame_start'], clip['frame_end']+1)) <= set(times))
                action_sha = native_actions.get(clip['action_name'])
                if (result.get('id') == clip['id'] and result.get('status') == 'EXECUTED_FULL_CLIP' and
                        result.get('frame_start') == clip['frame_start'] and
                        result.get('frame_end') == clip['frame_end'] and
                        result.get('object_name') == clip['object_name'] and
                        result.get('action_name') == clip['action_name'] and
                        result.get('slot_identifier') == clip['slot_identifier'] and
                        result.get('animation_target', 'OBJECT') == clip.get('animation_target', 'OBJECT') and
                        track_bindings(result) == track_bindings(clip, native_actions) and
                        isinstance(action_sha, str) and len(action_sha) == 64 and covered and
                        result.get('action_sha256') == action_sha):
                    matches.append(result)
        if len(matches) == 1:
            qualified.append(clip['id'])
        else:
            missing.append({'clip': clip['id'], 'reason': 'NO_EXACT_COMPLETE_RECEIPT' if not matches else 'AMBIGUOUS_RECEIPTS'})
    return {'status': 'EXACT_CANDIDATE_CLIPS_VERIFIED' if profile['clips'] and not missing else 'NOT_QUALIFIED',
            'clips_executed': qualified, 'unqualified_clips': missing,
            'garment_fitting': 'NOT_GRANTED', 'artistic_review': 'REQUIRED'}


def compare_native_samples(before, after, tolerance_cm):
    if len(before) != len(after):
        raise StudioError('Native reimport has incomplete sample coverage')
    maximum = 0.
    for a, b in zip(before, after, strict=True):
        if a['clip_id'] != b['clip_id'] or a['time'] != b['time'] or set(a['meshes']) != set(b['meshes']):
            raise StudioError('Native reimport sample identities changed')
        for name in a['meshes']:
            left, right = a['meshes'][name], b['meshes'][name]
            if left['faces'] != right['faces'] or len(left['vertices_cm']) != len(right['vertices_cm']):
                raise StudioError('Native reimport changed evaluated topology: ' + name)
            if left.get('face_sets') != right.get('face_sets'):
                raise StudioError('Native reimport changed source face-region identities: ' + name)
            for x, y in zip(left['vertices_cm'], right['vertices_cm'], strict=True):
                if len(x) != 3 or len(y) != 3 or any(not math.isfinite(v) for v in [*x, *y]):
                    raise StudioError('Native reimport returned nonfinite geometry')
                delta = math.dist(x, y)
                maximum = max(maximum, delta)
                if delta > tolerance_cm:
                    raise StudioError('Native reimport changed evaluated geometry beyond tolerance: ' + name)
    return {'status': 'NATIVE_SAMPLES_MATCH', 'sample_count': len(before),
            'max_vertex_delta_cm': maximum, 'tolerance_cm': tolerance_cm,
            'temporal_scope': 'DECLARED_EXPORT_SAMPLES_ONLY'}


def _export_payload(document):
    return {key: value for key, value in document.items() if key not in ('receipt', 'runtime')}


def registered_export_manifest(project, manifest):
    """Find one exact completed native callback, never accept client execution flags."""
    from .runs import _load, _table, _verified_receipt, _verify_run
    matches = []
    with closing(sqlite3.connect(project.db.as_uri()+'?mode=ro', uri=True)) as db:
        if _table(db):
            for (run_id,) in db.execute('SELECT id FROM runs'):
                run = _load(db, run_id)
                for unit in run['units']:
                    if (unit['executor'] != 'blender' or unit['operation'] != 'export_blender_animation' or
                            unit['status'] != 'COMPLETED'):
                        continue
                    for attempt in unit['attempts']:
                        if not attempt.get('receipt'):
                            continue
                        document = read_json(inside(project.root, attempt['receipt']['path']))
                        if _export_payload(document.get('result', {})) != _export_payload(manifest):
                            continue
                        _verify_run(project, run); document = _verified_receipt(project, db, run, unit, attempt)
                        if (document.get('execution') != 'RETURNED' or
                                document.get('arguments') != {'profile_path': manifest['profile']['path']}):
                            raise StudioError('Export receipt is not an exact returned native operation')
                        result = document['result']; receipt_ref = result.get('receipt')
                        if (not receipt_ref or receipt_ref not in document['files'] or
                                read_json(inside(project.root, receipt_ref['path'])) != _export_payload(result)):
                            raise StudioError('Export native result differs from its persisted manifest')
                        matches.append(document)
    if len(matches) != 1:
        raise StudioError('Export transport requires one exact registered completed native receipt')
    return matches[0]


def verify_export_manifest(project, manifest):
    """Validate registered and measured native transport, independent of art approval."""
    payload = {key: value for key, value in _export_payload(manifest).items() if key != 'cache_key'}
    if manifest.get('cache_key') != digest(payload):
        raise StudioError('Export manifest changed')
    if manifest.get('destination') != 'blender_animation' or manifest.get('reimport') != 'EXECUTED':
        raise StudioError('Blender export requires actual native reimport')
    if manifest.get('status') != 'BLENDER_EXPORT_REOPENED' or not manifest.get('artifact'):
        raise StudioError('Incomplete Blender export cannot pass delivery transport')
    references = [manifest['candidate'], manifest['profile'], manifest['artifact'], *manifest.get('resources', [])]
    if not manifest.get('snapshots_artifact'):
        raise StudioError('Native reimport comparison evidence is missing')
    references.append(manifest['snapshots_artifact'])
    for reference in references:
        if sha(inside(project.root, reference['path'])) != reference['sha256']:
            raise StudioError('Missing or changed Blender export dependency: ' + reference['path'])
    native = registered_export_manifest(project, manifest)
    if any(reference not in native['files'] for reference in references):
        raise StudioError('Export dependency is not registered with the exact native callback')
    inputs = export_descriptor(project, manifest['profile']['path']); profile = inputs['profile']
    proof = read_json(inside(project.root, manifest['snapshots_artifact']['path']))
    if (proof.get('candidate') != manifest['candidate'] or profile['source_ref'] != manifest['candidate'] or
            not isinstance(proof.get('rest'), dict) or not isinstance(proof.get('actions'), dict) or
            set(proof['rest']) != set(profile['object_names'] + profile['dependency_names']) or
            set(proof['actions']) != set(profile['action_names']) or
            proof.get('packed_images') != manifest.get('packed_resources') or
            manifest.get('candidate_binding') != digest([proof['rest'], proof['actions'], proof.get('packed_images')])):
        raise StudioError('Native export comparison does not bind its exact source, Actions and dependencies')
    expected = [('reference', profile['reference_frame'])]
    expected += [(clip['id'], time) for clip in profile['clips'] for time in export_sample_times(clip)]
    mesh_names = {name for name, row in proof['rest'].items() if row.get('type') == 'MESH'}
    for key in ('samples_before', 'samples_after'):
        samples = proof.get(key)
        if (not isinstance(samples, list) or [(row.get('clip_id'), row.get('time')) for row in samples] != expected or
                not mesh_names or any(set(row.get('meshes', {})) != mesh_names for row in samples)):
            raise StudioError('Native export comparison has incomplete exact sample or mesh coverage')
    comparison = compare_native_samples(proof['samples_before'], proof['samples_after'], profile['geometry_tolerance_cm'])
    if proof.get('comparison') != comparison or manifest.get('native_comparison') != comparison:
        raise StudioError('Native export comparison metrics differ from its measured samples')
    qualification = motion_qualification(profile, inputs['receipts'], {name: digest(value) for name, value in proof['actions'].items()}, mesh_names)
    if (manifest.get('animation_qualification') != qualification['status'] or
            manifest.get('clips_executed') != qualification['clips_executed']):
        raise StudioError('Export clip qualification differs from exact measured motion provenance')
    return {'status': 'BLENDER_TRANSPORT_VERIFIED', 'candidate': manifest['candidate'],
            'animation_qualification': manifest['animation_qualification'],
            'artistic_review': 'REQUIRED', 'engine_qualification': 'NOT_QUALIFIED'}
