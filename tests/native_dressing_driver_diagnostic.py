"""Read-only historical failure diagnostic; no dressing or fitting acceptance.

Each branch recreates the same TEST_ONLY source fixture in temporary native
scenes. It records the source Key Action, a separate pre-Cloth copy and actual
Cloth output around the first failed frame. Source files/SQLite are read-only;
no dispatcher receipt is fabricated and no parameter or tolerance is tuned.
"""
import argparse
import copy
import json
import math
from pathlib import Path
import sqlite3
import sys
import time
from contextlib import closing

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))


def arguments(argv):
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--source-project', required=True)
    parser.add_argument('--profile-path', default='.a3d/native-dressing-inputs/execution-profile.json')
    parser.add_argument('--failed-receipt', required=True)
    parser.add_argument('--output', required=True)
    parser.add_argument('--validate-only', action='store_true')
    args = parser.parse_args(argv)
    source, output = Path(args.source_project), Path(args.output)
    if not source.is_absolute() or not source.is_dir() or source.drive.lower() != 'g:':
        parser.error('Require an existing absolute source project on approved G: storage')
    if not output.is_absolute() or output.exists() or output.drive.lower() != 'g:':
        parser.error('Require a new absolute output on approved G: storage')
    args.source_project, args.output = source.resolve(), output.resolve()
    if args.output == args.source_project or args.source_project in args.output.parents:
        parser.error('Diagnostic output must be outside the read-only source project')
    return args


def historical_failure(project, profile_path, failed_path):
    """Authenticate a failed dispatch without treating it as a successful input."""
    from a3d.core import StudioError, inside, read_json, sha
    from a3d.native_evidence import checked_reference
    failed_ref = {'path': failed_path, 'sha256': sha(inside(project.root, failed_path))}
    failed = read_json(inside(project.root, failed_path))
    if (failed.get('purpose') != 'TEST_ONLY' or failed.get('status') != 'NEEDS_CORRECTION' or
            failed.get('stopped', {}).get('reason') != 'DRESSING_NATIVE_FULL_WEIGHT_GRIP_TARGET_MISMATCH'):
        raise StudioError('Diagnostic requires the actual TEST_ONLY full-weight grip failure')
    with closing(sqlite3.connect(project.db.as_uri()+'?mode=ro', uri=True)) as db:
        for event_id, document in db.execute("SELECT id,doc FROM events WHERE kind='run_native_receipt' ORDER BY id DESC"):
            event = json.loads(document)
            checked_reference(project, event['receipt'])
            wrapper = read_json(inside(project.root, event['receipt']['path']))
            if wrapper.get('operation') != 'run_dressing_program' or wrapper.get('result', {}).get('receipt') != failed_ref:
                continue
            row = db.execute('SELECT doc FROM runs WHERE id=?', (event['run_id'],)).fetchone()
            run = json.loads(row[0]) if row else {}
            unit = next((u for u in run.get('units', []) if u['id'] == event['unit_id']), None)
            attempt = next((a for a in unit['attempts'] if a['id'] == event['attempt_id']), None) if unit else None
            if (not attempt or unit['status'] != 'NEEDS_CORRECTION' or attempt.get('status') != 'NEEDS_CORRECTION' or
                    attempt.get('receipt_event_id') != event_id or attempt.get('receipt') != event['receipt'] or
                    wrapper.get('origin') != 'NATIVE_DISPATCH' or wrapper.get('execution') != 'RETURNED' or
                    wrapper.get('arguments') != {'profile_path': profile_path} or
                    wrapper.get('arguments') != attempt['arguments'] or wrapper.get('operation') != attempt['operation'] or
                    any(wrapper.get(k) != event[k] for k in ('run_id', 'unit_id', 'attempt_id', 'binding_sha256')) or
                    wrapper.get('binding_sha256') != attempt['binding_sha256'] or
                    any(wrapper['result'].get(k) != v for k, v in failed.items()) or failed_ref not in wrapper['files']):
                raise StudioError('Historical failure differs from its exact canonical failed attempt')
            for ref in wrapper['files']:
                checked_reference(project, ref)
            return failed, wrapper, {'event_id': event_id, **event, 'scope': 'HISTORICAL_FAILED_DIAGNOSTIC_ONLY'}
    raise StudioError('Diagnostic cannot use a failure file without its canonical failed dispatch')


def prepare(args):
    from a3d.core import StudioError, sha
    from a3d.store import Project
    from a3d.dressing_paths import dressing_execution_descriptor
    project = Project(args.source_project)
    before = sha(project.db)
    failed, wrapper, origin = historical_failure(project, args.profile_path, args.failed_receipt)
    descriptor = dressing_execution_descriptor(project, args.profile_path)
    if (descriptor['status'] != 'DRESSING_INSTRUCTIONS_PREPARED' or descriptor['profile']['purpose'] != 'TEST_ONLY' or
            descriptor['profile_ref'] != failed['profile'] or descriptor['motion_inputs']['animated_colliders'] or
            descriptor['instructions']['frame_end'] != 5 or len(descriptor['entry']['placed_cm']) > 1000):
        raise StudioError('Diagnostic is bounded to the exact five-frame, fixed-body source fixture')
    if sha(project.db) != before:
        raise StudioError('Diagnostic admission changed canonical state')
    return project, descriptor, failed, wrapper, origin


def _context(obj=None, cloth=None, read_evaluated_keys=False):
    import bpy
    from a3d.core import digest
    from blender.body_motion import action_payload
    graph = bpy.context.evaluated_depsgraph_get()
    scene = bpy.context.scene
    result = {'scene': scene.name, 'frame': scene.frame_current, 'subframe': scene.frame_subframe,
              'view_layer': bpy.context.view_layer.name,
              'depsgraph_scene': graph.scene.name, 'depsgraph_scene_eval': graph.scene_eval.name,
              'depsgraph_frame': graph.scene_eval.frame_current, 'depsgraph_subframe': graph.scene_eval.frame_subframe,
              'depsgraph_pointer': graph.as_pointer()}
    if obj is not None:
        keys = obj.data.shape_keys
        result['keys'] = {k.name: k.value for k in keys.key_blocks}
        if read_evaluated_keys:
            evaluated_keys = obj.evaluated_get(graph).data.shape_keys
            result['evaluated_keys'] = {k.name: k.value for k in evaluated_keys.key_blocks} if evaluated_keys else None
        animation = keys.animation_data
        result['action_sha256'] = digest(action_payload(animation.action))
        result['slot_identifier'] = animation.action_slot.identifier
    if cloth is not None:
        cache = cloth.point_cache
        result['point_cache'] = {k: getattr(cache, k) for k in
            ('frame_start', 'frame_end', 'is_outdated', 'is_baked', 'is_frame_skip', 'info') if hasattr(cache, k)}
    return result


def _grips(geometry, states):
    return [{'id': s['id'], 'vertex': s['vertex'], 'target_cm': s['point_cm'], 'weight': s['weight'],
             'observed_cm': geometry['vertices_cm'][s['vertex']],
             'error_cm': math.dist(geometry['vertices_cm'][s['vertex']], s['point_cm'])} for s in states]


def _branch(project, descriptor, branch, intermediate, input_first, output):
    import bpy
    from a3d.core import StudioError, atomic_json, digest, inside, read_json
    from blender.body_source import data_ids, live_geometry
    from blender.body_target import evaluated_mesh
    from blender.dressing_executor import (_geometry, apply_supports, author_support_action, verify_support_action,
                                           _source_uv, pin_weights)
    from blender.garment_motion import _activate_collision, _contacts, _time
    from blender.sewing import apply_physics, make_object, physical_snapshot, structural_inputs
    baseline, live = data_ids(), live_geometry()
    inputs = descriptor['motion_inputs']
    source, recipe = inputs['candidate'], inputs['recipe']
    execution = dict(inputs['profile']['execution'], **descriptor['profile']['execution'])
    frames, intervals = [], []
    started = time.monotonic()
    try:
        scene = bpy.data.scenes.new('A3D.Dressing.Diagnostic.'+branch)
        evaluation = bpy.data.scenes.new('A3D.Dressing.Diagnostic.Obstacles.'+branch)
        scene.unit_settings.scale_length = evaluation.unit_settings.scale_length = 1.
        scene.render.fps = evaluation.render.fps = recipe['phases']['drape']['fps']
        body_record = descriptor['body_target']
        body_geometry = read_json(inside(project.root, body_record['artifacts']['geometry']['path']))
        body_triangles = read_json(inside(project.root, body_record['artifacts']['triangles']['path']))
        with bpy.data.libraries.load(str(inside(project.root, body_record['artifact']['path'])), link=False) as (available, loaded):
            if len(available.objects) != 1:
                raise StudioError('Diagnostic target requires exactly its source skin')
            loaded.objects = list(available.objects)
        body = loaded.objects[0]
        if body.type != 'MESH' or body.modifiers or body.parent or body.constraints or body.animation_data or body.data.shape_keys:
            raise StudioError('Diagnostic body has unexpected native dependencies')
        scene.collection.objects.link(body)
        evaluation.collection.objects.link(body)
        with bpy.context.temp_override(scene=scene, view_layer=scene.view_layers[0]):
            actual, triangles = evaluated_mesh(body, bpy.context.evaluated_depsgraph_get(), 1.)
            if actual['vertices_cm'] != body_geometry['vertices_cm'] or actual['faces'] != body_geometry['faces'] or triangles != body_triangles:
                raise StudioError('Diagnostic loaded skin differs from its exact source measurement')
            _activate_collision(body, inputs['profile']['body_collision'], 'A3D.Dressing.Diagnostic.BodyCollision')
            runtime = copy.deepcopy(source)
            runtime['placed_cm'] = copy.deepcopy(descriptor['entry']['placed_cm'])
            runtime['pins'] = dict(source['pins'])
            for support in descriptor['supports']:
                if support['start_frame'] == 1:
                    runtime['pins'][str(support['vertex'])] = support['weight']
            obj = make_object(runtime, 'A3D.Dressing.Diagnostic.Cloth')
            structural_inputs(obj, runtime, recipe)
            _source_uv(obj, source)
            entry = _contacts(source, [body], runtime['placed_cm'], recipe, execution, 0)
            driver = author_support_action(obj, descriptor['supports'], 5, execution['max_cache_vertex_frames'])
            # Snapshot the actual animated input before installing Cloth. The
            # independent mesh owns its Key data, sharing only the immutable Action.
            pre = obj.copy()
            pre.data = obj.data.copy()
            pre.name = 'A3D.Dressing.Diagnostic.PreCloth'
            scene.collection.objects.link(pre)
            if pre.modifiers or pre.data.shape_keys == obj.data.shape_keys:
                raise StudioError('Diagnostic pre-Cloth copy is not an independent native Key input')
            cloth, _, _ = apply_physics(obj, runtime, recipe, 'drape', [body])
            cloth.point_cache.frame_end = scene.frame_end = 5
            fixed_physics = physical_snapshot(obj)
            for frame in range(1, 6):
                if time.monotonic()-started > execution['max_seconds']:
                    raise StudioError('Diagnostic exceeds the unchanged source time budget')
                states, _ = apply_supports(obj, None, descriptor['supports'], frame, source['pins'])
                obj.data.update()
                _time(scene, frame)
                context_before = _context(obj, cloth)
                driver_values = verify_support_action(obj, driver, frame)
                before_input = _geometry(pre) if input_first else None
                first = _geometry(obj)
                context_first = _context(obj, cloth, read_evaluated_keys=True)
                second = _geometry(obj)
                pre_geometry = before_input or _geometry(pre)
                if any(g['faces'] != source['faces'] for g in (first, second, pre_geometry)):
                    raise StudioError('Diagnostic changed native source topology')
                observed_body = _geometry(body)
                if observed_body != {'vertices_cm': body_geometry['vertices_cm'], 'faces': body_geometry['faces']}:
                    raise StudioError('Diagnostic skin changed its exact source pose')
                contact = _contacts(source, [body], first['vertices_cm'], recipe, execution, frame)
                row = {'frame': frame, 'context_before': context_before, 'context_after_first_output': context_first,
                       'context_after_input': _context(obj, cloth), 'driver_values': driver_values,
                       'native_pin_weights': pin_weights(obj),
                       'raw_mesh_grips_cm': [[v*100 for v in obj.data.vertices[s['vertex']].co] for s in states],
                       'pre_cloth': _grips(pre_geometry, states), 'cloth_first': _grips(first, states),
                       'cloth_second': _grips(second, states), 'contacts': contact,
                       'cloth_vertices_cm': first['vertices_cm'], 'faces': first['faces'],
                       'pre_cloth_geometry_sha256': digest([pre_geometry['vertices_cm'], pre_geometry['faces']]),
                       'cloth_geometry_sha256': digest([first['vertices_cm'], first['faces']]),
                       'physics_snapshot': physical_snapshot(obj)}
                frames.append(row)
                atomic_json(output/(branch+'.frames.json'), frames)
                if intermediate and frame >= 2:
                    checks = []
                    with bpy.context.temp_override(scene=evaluation, view_layer=evaluation.view_layers[0]):
                        # Same shared fixed body and times as the failing kernel's
                        # minimum two subdivisions; Cloth is absent from this scene.
                        for sample_time in (frame-.5, float(frame)):
                            _time(evaluation, sample_time)
                            skin = _geometry(body)
                            if skin != observed_body:
                                raise StudioError('Intermediate diagnostic skin is not source identical')
                            checks.append({'time': sample_time, 'context': _context(),
                                           'body_geometry_sha256': digest([skin['vertices_cm'], skin['faces']])})
                    intervals.append({'after_frame': frame, 'samples': checks, 'restored_context': _context(obj, cloth)})
            return {'id': branch, 'status': 'DIAGNOSTIC_OBSERVATIONS_COMPLETE',
                    'intermediate_scene_reads': intermediate, 'pre_cloth_read_before_output': input_first,
                    'entry_contacts': entry, 'support_driver': driver, 'initial_physics': fixed_physics,
                    'frames': frames, 'intervals': intervals, 'elapsed_seconds': time.monotonic()-started,
                    'acceptance_tolerance_cm': .001, 'physical_qualification': 'NONE'}
    finally:
        bpy.data.batch_remove(ids=data_ids()-baseline)
        if data_ids() != baseline or live_geometry() != live:
            raise StudioError('Diagnostic branch changed original native data')


def run(args):
    import bpy
    from a3d.core import StudioError, atomic_json, inside, sha
    from blender.body_source import data_ids, live_geometry
    if not bpy.app.background or bpy.data.filepath:
        raise StudioError('Diagnostic requires a factory/background process with no production scene')
    project, descriptor, failed, wrapper, origin = prepare(args)
    baseline, live = data_ids(), live_geometry()
    scene = bpy.context.scene
    frame, subframe, filepath = scene.frame_current, scene.frame_subframe, bpy.data.filepath
    selected, active = set(bpy.context.selected_objects), bpy.context.view_layer.objects.active
    refs = descriptor['evidence']+[origin['receipt'], {'path': args.failed_receipt, 'sha256': sha(inside(project.root, args.failed_receipt))}]
    source_hashes = {r['path']: r['sha256'] for r in refs}
    db_hash = sha(project.db)
    args.output.mkdir(parents=True, exist_ok=False)
    result = {'version': 1, 'status': 'DIAGNOSTIC_INCOMPLETE', 'scope': 'TEST_ONLY_HISTORICAL_FAILURE_DIAGNOSTIC',
              'historical_origin': origin, 'historical_failure': failed['stopped'], 'profile': descriptor['profile_ref'],
              'historical_code_sources': wrapper['code_sources'],
              'current_source_files': {p: sha(ROOT/p) for p in ('tests/native_dressing_driver_diagnostic.py',
                  'blender/dressing_executor.py', 'blender/garment_motion.py', 'blender/sewing.py', 'blender/body_motion.py')},
              'source_project': str(project.root), 'branches': [], 'physical_qualification': 'NONE',
              'fitting': 'NOT_QUALIFIED', 'product_acceptance': 'NOT_GRANTED', 'parameter_changes': [],
              'cache_restart': 'NOT_QUALIFIED', 'canonical_result_registered': False}
    error = None
    try:
        for branch, intermediate, input_first in (
                ('single-scene-output-first', False, False),
                ('two-scenes-output-first', True, False),
                ('two-scenes-input-first', True, True)):
            result['branches'].append(_branch(project, descriptor, branch, intermediate, input_first, args.output))
            atomic_json(args.output/'diagnostic.json', result)
        result['status'] = 'DIAGNOSTIC_OBSERVATIONS_COMPLETE'
    except Exception as exc:
        error = exc
        result['error'] = {'type': type(exc).__name__, 'message': str(exc)}
    finally:
        preserved = (data_ids() == baseline and live_geometry() == live and bpy.context.scene == scene and
                     scene.frame_current == frame and scene.frame_subframe == subframe and bpy.data.filepath == filepath and
                     set(bpy.context.selected_objects) == selected and bpy.context.view_layer.objects.active == active and
                     sha(project.db) == db_hash and all(sha(inside(project.root, p)) == value for p, value in source_hashes.items()))
        result['original_scene_and_source_preserved'] = preserved
        result['source_sqlite_sha256'] = db_hash
        result['source_files'] = source_hashes
        atomic_json(args.output/'diagnostic.json', result)
        if not preserved:
            raise StudioError('Diagnostic source/scene preservation failed')
    print(result['status']+': '+str(args.output/'diagnostic.json'))
    if error:
        raise error


if __name__ == '__main__':
    argv = sys.argv[sys.argv.index('--')+1:] if '--' in sys.argv else sys.argv[1:]
    args = arguments(argv)
    if args.validate_only:
        project, descriptor, failed, wrapper, origin = prepare(args)
        print('ARGUMENTS_AND_CANONICAL_FAILED_SOURCE_VALIDATED: no native operation executed; event '+str(origin['event_id']))
    else:
        run(args)
