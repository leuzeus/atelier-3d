"""Read-only exact-body admission and refusal campaign on genuine native input.

Coordinator only: Blender --background --factory-startup --python-exit-code 1
--python tests/native_physics_admission.py -- --project <G: project>
--body-profile <exact portable relative JSON> --source-blend <native artifact
or registered entry checkpoint> --body-object <exact source name> --output
<new G: directory outside the source project>. Ordinary Python can run the
same arguments with --validate-only; this authenticates sources without bpy.

Only a named body is appended into the factory process. Mutations used to
exercise rejection are immediately restored in memory. No scene, project,
gate, run, native receipt or canonical SQLite journal is saved or copied.
"""
import argparse
from contextlib import closing
import copy
import json
from pathlib import Path
import sqlite3
import sys

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))


def arguments(argv):
    from a3d.core import inside
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--project', required=True)
    parser.add_argument('--body-profile', required=True)
    parser.add_argument('--source-blend', required=True)
    parser.add_argument('--body-object', required=True)
    parser.add_argument('--output', required=True)
    parser.add_argument('--validate-only', action='store_true')
    args = parser.parse_args(argv)
    project, output = Path(args.project), Path(args.output)
    if (not project.is_absolute() or not output.is_absolute() or
            project.resolve().drive.lower() != 'g:' or output.resolve().drive.lower() != 'g:' or
            not (project/'.a3d/state.sqlite3').is_file() or output.exists() or
            output.resolve().is_relative_to(project.resolve()) or output.resolve().is_relative_to(ROOT)):
        parser.error('Require a genuine G: project and a new G: output outside project and source checkout')
    if not args.body_object.strip():
        parser.error('Require the exact nonempty native body object name')
    try:
        profile = inside(project, args.body_profile)
        source_arg = Path(args.source_blend)
        source_relative = (source_arg.resolve(strict=True).relative_to(project.resolve()).as_posix()
                           if source_arg.is_absolute() else args.source_blend)
        source = inside(project, source_relative)
        if profile.suffix.lower() != '.json' or source.suffix.lower() != '.blend':
            raise ValueError('Require a native body JSON profile and a .blend input')
    except (ValueError, OSError) as error:
        parser.error(str(error))
    args.project, args.output = project.resolve(), output.resolve()
    args.source_blend = source_relative
    return args


def _database_identity(project):
    from a3d.core import sha
    # A read-only campaign must not create a journal, WAL or shared-memory file.
    return {suffix: sha(Path(str(project.db)+suffix)) if Path(str(project.db)+suffix).is_file() else None
            for suffix in ('', '-wal', '-shm', '-journal')}


def _state_identity(project):
    from a3d.core import digest
    with closing(sqlite3.connect(project.db.as_uri()+'?mode=ro', uri=True)) as db:
        row = db.execute('SELECT doc FROM state WHERE id=1').fetchone()
        if row is None:
            raise ValueError('Source project has no canonical state')
        return digest(json.loads(row[0]))


def _source_origin(project, native, source_ref):
    """Accept body artifacts or an actual dispatcher-bound entry checkpoint."""
    from a3d.core import StudioError
    from a3d.runs import _verified_native_checkpoint
    result = native['result']
    artifacts = [result.get('artifact'), result.get('source_artifact')]
    if source_ref in artifacts and source_ref in native['files']:
        return {'kind': 'CANONICAL_BODY_ARTIFACT', 'reference': source_ref}
    with closing(sqlite3.connect(project.db.as_uri()+'?mode=ro', uri=True)) as db:
        for document, in db.execute('SELECT doc FROM runs'):
            run = json.loads(document)
            for unit in run['units']:
                for attempt in unit['attempts']:
                    checkpoint = attempt.get('entry_checkpoint', {}) or {}
                    if {key: checkpoint.get(key) for key in ('path', 'sha256')} != source_ref:
                        continue
                    if _verified_native_checkpoint(project, db, run, unit, attempt):
                        return {'kind': 'CANONICAL_NATIVE_ENTRY_CHECKPOINT', 'reference': source_ref,
                                'run_id': run['run_id'], 'unit_id': unit['id'], 'attempt_id': attempt['id'],
                                'checkpoint_event_id': attempt['checkpoint_event_id']}
    raise StudioError('Source .blend is neither an exact body artifact nor a canonically registered native checkpoint')


def authenticate_inputs(args):
    """No bpy and no output effects: re-read genuine immutable native origin."""
    from a3d.core import StudioError, digest, inside, read_json, sha
    from a3d.native_evidence import checked_reference, native_origin
    from a3d.store import Project
    project = Project(args.project)
    database_before, state_before = _database_identity(project), _state_identity(project)
    body_ref = {'path': args.body_profile, 'sha256': sha(inside(project.root, args.body_profile))}
    checked_reference(project, body_ref)
    native, origin = native_origin(project, lambda doc:
        (doc.get('operation') == 'prepare_body_target' and doc.get('result', {}).get('artifacts', {}).get('profile') == body_ref) or
        (doc.get('operation') == 'introduce_body_target' and doc.get('result', {}).get('profile_ref') == body_ref))
    profile = read_json(inside(project.root, body_ref['path'])); result = native['result']
    if native['operation'] == 'prepare_body_target' and (
            result.get('status') != 'NATIVE_BODY_TARGET_MEASURED' or result.get('native_reopened') is not True):
        raise StudioError('Identity campaign requires a measured and actually reopened native target')
    geometry_ref = (result['artifacts']['geometry'] if native['operation'] == 'prepare_body_target'
                    else result['geometry_ref'])
    checked_reference(project, geometry_ref)
    geometry = read_json(inside(project.root, geometry_ref['path']))
    if (body_ref not in native['files'] or profile.get('status') != 'PROFILE_MEASURED' or
            result.get('profile_cache_key') != profile.get('cache_key') or
            profile.get('geometry_sha256') != digest([geometry['vertices_cm'], geometry['faces']])):
        raise StudioError('Body profile differs from its exact measured native origin')
    references = [origin['receipt'], *native['files'], geometry_ref, body_ref]
    if native['operation'] == 'introduce_body_target':
        from a3d.body_context import body_context_descriptor
        context = body_context_descriptor(project, native['arguments']['context_path'])
        if (context['profile'] != profile or context['receipt']['artifacts']['profile'] != body_ref or
                result.get('status') != 'BODY_TARGET_INTRODUCED' or context['context_ref'] != result['context'] or
                context['binding_sha256'] != result['binding_sha256'] or context['geometry'] != geometry or
                result.get('actual_geometry_sha256') != digest({key: geometry[key] for key in ('vertices_cm', 'faces', 'face_sets')})):
            raise StudioError('Introduced native body does not match the exact measured source context')
        references.extend(context['evidence'])
    source_ref = {'path': args.source_blend, 'sha256': sha(inside(project.root, args.source_blend))}
    checked_reference(project, source_ref)
    source_origin = _source_origin(project, native, source_ref)
    if (native['operation'] == 'introduce_body_target' and source_ref == result['artifact'] and
            args.body_object != result['object']):
        raise StudioError('Requested body name differs from its exact native context artifact')
    protected = {}
    for reference in [*references, source_ref]:
        checked_reference(project, reference)
        if reference['path'] in protected and protected[reference['path']] != reference['sha256']:
            raise StudioError('Native source references contradict each other')
        protected[reference['path']] = reference['sha256']
    if _database_identity(project) != database_before or _state_identity(project) != state_before:
        raise StudioError('Source canonical project changed during read-only input authentication')
    return {'project': project, 'body_ref': body_ref, 'profile': profile, 'geometry_ref': geometry_ref,
            'geometry': geometry, 'native_body_origin': origin, 'source_blend_ref': source_ref,
            'source_blend_origin': source_origin, 'protected_sources': protected,
            'database_before': database_before, 'state_before': state_before}


def _assert_preserved(inputs):
    from a3d.core import StudioError, inside, sha
    project = inputs['project']
    if (_database_identity(project) != inputs['database_before'] or
            _state_identity(project) != inputs['state_before']):
        raise StudioError('Read-only identity campaign changed the canonical source project')
    for path, identity in inputs['protected_sources'].items():
        if sha(inside(project.root, path)) != identity:
            raise StudioError('Read-only identity campaign source changed: '+path)


def run(args, inputs):
    import bpy
    from a3d.core import StudioError, atomic_json, digest, inside, read_json, sha
    from blender.body_target import evaluated_mesh
    from blender.physics_admission import require_native_fit_body, require_native_recipe_fit_intent
    project = inputs['project']
    if (not bpy.app.background or bpy.data.filepath or bpy.context.mode != 'OBJECT' or
            not any(value == '--factory-startup' for value in sys.argv[:sys.argv.index('--') if '--' in sys.argv else len(sys.argv)])):
        raise StudioError('Identity campaign requires isolated background factory-startup Blender with no loaded scene')
    args.output.mkdir(parents=True, exist_ok=False)
    (args.output/'tmp').mkdir()
    bpy.context.preferences.filepaths.temporary_directory = str(args.output/'tmp')
    bpy.context.scene.unit_settings.system = 'METRIC'
    bpy.context.scene.unit_settings.scale_length = 1.
    receipt = {'version': 1, 'status': 'NATIVE_PHYSICS_ADMISSION_RUNNING',
               'purpose': 'TEST_ONLY_IDENTITY_ADMISSION_ONLY', 'source_project': str(project.root),
               'body_ref': inputs['body_ref'], 'geometry_ref': inputs['geometry_ref'],
               'source_blend_ref': inputs['source_blend_ref'], 'source_blend_origin': inputs['source_blend_origin'],
               'native_body_origin': inputs['native_body_origin'], 'body_object': args.body_object, 'checks': [],
               'implementation': {path: sha(ROOT/path) for path in
                    ('tests/native_physics_admission.py', 'a3d/native_evidence.py', 'a3d/physics_admission.py',
                     'blender/physics_admission.py', 'blender/body_target.py')},
               'blender_version': bpy.app.version_string,
               'simulation': 'NOT_EXECUTED', 'fitting': 'NOT_EXECUTED', 'product_acceptance': 'NOT_GRANTED',
               'accepted': False, 'source_scene_saved': False, 'canonical_journal_written': False}
    try:
        with bpy.data.libraries.load(str(inside(project.root, args.source_blend)), link=False) as (available, loaded):
            if args.body_object not in available.objects:
                raise StudioError('Exact body object is absent from the authenticated source .blend')
            loaded.objects = [args.body_object]
        body = loaded.objects[0]
        if body is None or body.name != args.body_object or body.type != 'MESH':
            raise StudioError('Body input changed its exact name or mesh identity during isolated loading')
        bpy.context.scene.collection.objects.link(body)
        bpy.context.view_layer.update()
        baseline, _ = evaluated_mesh(body, bpy.context.evaluated_depsgraph_get(), 1.)
        expected = {key: inputs['geometry'][key] for key in ('vertices_cm', 'faces', 'face_sets')}
        if baseline != expected:
            raise StudioError('Loaded body differs from the canonical measured geometry before any experiment')
        identity = require_native_fit_body(project, inputs['body_ref'], body)
        receipt['checks'].append({'id': 'exact_body', 'status': 'PASS', 'identity': identity,
                                   'geometry_sha256': digest(baseline)})
        original_cache = body.get('a3d_profile_cache_key')
        labels = body.data.attributes.get('.sculpt_face_set')
        if not body.data.vertices or labels is None or labels.data_type != 'INT' or labels.domain != 'FACE' or not labels.data:
            raise StudioError('Native body requires actual vertices and per-face source-region labels for refusal experiments')
        initial_effects = {'objects': sorted(obj.name for obj in bpy.data.objects),
                          'frame': bpy.context.scene.frame_current,
                          'modifiers': [(modifier.name, modifier.type) for modifier in body.modifiers]}

        def restored():
            bpy.context.view_layer.update()
            actual, _ = evaluated_mesh(body, bpy.context.evaluated_depsgraph_get(), 1.)
            if actual != baseline or body.get('a3d_profile_cache_key') != original_cache:
                raise StudioError('A temporary refusal mutation was not restored to exact native identity')
            if initial_effects != {'objects': sorted(obj.name for obj in bpy.data.objects),
                                   'frame': bpy.context.scene.frame_current,
                                   'modifiers': [(modifier.name, modifier.type) for modifier in body.modifiers]}:
                raise StudioError('Identity admission unexpectedly created effects or advanced a frame')

        def refused(identifier, call, expected_reason, observations):
            try:
                call()
            except StudioError as error:
                if expected_reason not in str(error):
                    raise AssertionError('Refused for an unrelated reason: '+str(error)) from error
                receipt['checks'].append({'id': identifier, 'status': 'REFUSED_AS_REQUIRED',
                                           'reason': str(error), **observations})
            else:
                raise AssertionError(identifier+' unexpectedly passed exact native-body admission')

        coordinate = body.data.vertices[0].co.copy()
        try:
            body.data.vertices[0].co.x += .01
            body.data.update(); bpy.context.view_layer.update()
            changed, _ = evaluated_mesh(body, bpy.context.evaluated_depsgraph_get(), 1.)
            if changed['faces'] != baseline['faces'] or changed['face_sets'] != baseline['face_sets'] or changed['vertices_cm'] == baseline['vertices_cm']:
                raise AssertionError('Vertex refusal experiment did not preserve topology and source regions')
            refused('vertex_changed', lambda: require_native_fit_body(project, inputs['body_ref'], body),
                    'Live body geometry differs', {'changed_geometry_sha256': digest(changed), 'topology_preserved': True})
        finally:
            body.data.vertices[0].co = coordinate; body.data.update(); restored()

        label = labels.data[0].value
        try:
            labels.data[0].value = label+1
            body.data.update(); bpy.context.view_layer.update()
            changed, _ = evaluated_mesh(body, bpy.context.evaluated_depsgraph_get(), 1.)
            if changed['vertices_cm'] != baseline['vertices_cm'] or changed['faces'] != baseline['faces'] or changed['face_sets'] == baseline['face_sets']:
                raise AssertionError('Face-region refusal experiment changed mesh geometry or failed to change its label')
            refused('face_set_only_changed', lambda: require_native_fit_body(project, inputs['body_ref'], body),
                    'Live body skin regions differ', {'vertices_faces_unchanged': True,
                     'vertices_faces_sha256': digest([changed['vertices_cm'], changed['faces']]),
                     'changed_face_sets_sha256': digest(changed['face_sets'])})
        finally:
            labels.data[0].value = label; body.data.update(); restored()

        try:
            body['a3d_profile_cache_key'] = digest([original_cache, 'TEST_ONLY_INVALID_CACHE'])
            changed, _ = evaluated_mesh(body, bpy.context.evaluated_depsgraph_get(), 1.)
            if changed != baseline:
                raise AssertionError('Cache refusal experiment must leave evaluated geometry unchanged')
            refused('cache_changed', lambda: require_native_fit_body(project, inputs['body_ref'], body),
                    'different measured fit target', {'geometry_unchanged': True, 'geometry_sha256': digest(changed)})
        finally:
            body['a3d_profile_cache_key'] = original_cache; restored()

        # Complete schema-valid recipe is deliberately TEST_ONLY. Its measured
        # object dimensions are not anatomical girths, and no physical recipe
        # is applied. Relabel rejection must precede portable scope handling.
        recipe = copy.deepcopy(read_json(ROOT/'templates/sewing-recipe.json'))
        from blender.sewing import mesh_digest
        recipe.update(physics_purpose='TEST_ONLY', colliders=[{
            'object': body.name, 'role': 'support', 'dimensions_cm': [float(value)*100 for value in body.dimensions],
            'geometry_sha256': mesh_digest(body, True), 'outer_thickness_cm': 0., 'inner_thickness_cm': 0.,
            'tolerance_cm': .001}], no_collision_reason='')
        refused('measured_body_relabeled_support', lambda: require_native_recipe_fit_intent(project, recipe, [body]),
                'cannot be relabeled', {'body_cache_unchanged': True, 'geometry_unchanged': True,
                                        'physics_executed': False})
        restored()
        final_identity = require_native_fit_body(project, inputs['body_ref'], body)
        if final_identity != identity:
            raise StudioError('Final restored native body identity differs from its initial admitted identity')
        _assert_preserved(inputs)
        receipt.update(status='NATIVE_PHYSICS_IDENTITY_ADMISSION_PASS', mutations_restored_in_memory=True,
                       source_files_preserved=True, source_database_preserved=True,
                       canonical_state_preserved=True, protected_sources=inputs['protected_sources'],
                       source_database_identity=inputs['database_before'], source_state_sha256=inputs['state_before'],
                       final_restored_identity=final_identity)
    except BaseException as error:
        receipt.update(status='NATIVE_PHYSICS_IDENTITY_ADMISSION_FAIL', error=str(error))
        try:
            _assert_preserved(inputs)
            receipt.update(source_files_preserved=True, source_database_preserved=True, canonical_state_preserved=True)
        except BaseException as preservation_error:
            receipt['source_preservation_error'] = str(preservation_error)
        atomic_json(args.output/'receipt.json', receipt)
        raise
    atomic_json(args.output/'receipt.json', receipt)
    print(json.dumps({'status': receipt['status'], 'receipt': str(args.output/'receipt.json'),
                      'scope': receipt['purpose'], 'accepted': False}))
    return receipt


if __name__ == '__main__':
    argv = sys.argv[sys.argv.index('--')+1:] if '--' in sys.argv else sys.argv[1:]
    args = arguments(argv)
    inputs = authenticate_inputs(args)
    if args.validate_only:
        print(json.dumps({'arguments_valid': True, 'sources_authenticated': True, 'native_executed': False,
                          'body_ref': inputs['body_ref'], 'native_body_origin': inputs['native_body_origin'],
                          'source_blend_origin': inputs['source_blend_origin'], 'output_created': False}))
    else:
        run(args, inputs)
