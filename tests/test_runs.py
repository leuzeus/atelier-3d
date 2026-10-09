import copy
import json
import sqlite3
import tempfile
import unittest
from contextlib import closing
from pathlib import Path
from unittest.mock import patch

from a3d.core import ROOT, StudioError, atomic_json, canonical, sha
from a3d.runs import (create_run, next_run_step, run_status, request_run_stop,
                      record_native_run_result, record_native_run_failure, record_native_run_started,
                      record_native_run_checkpoint, native_attempt_binding)
from a3d.store import Project
from tests.support import asset


def unit(ident='inspect', dependencies=()):
    return {'id': ident, 'dependencies': list(dependencies), 'executor': 'blender',
            'operation': 'inspect', 'arguments': {}, 'inputs': []}


class Runs(unittest.TestCase):
    def setUp(self):
        directory = ROOT/'work/test-runs'
        directory.mkdir(parents=True, exist_ok=True)
        self.temp = tempfile.TemporaryDirectory(dir=directory)
        self.root = Path(self.temp.name)
        self.project = Project.create(self.root, asset())
        self.spec = {'version': 1, 'id': 'test-run', 'kind': 'garment', 'asset_id': 'test-character',
                     'inputs': [], 'budgets': {'max_attempts': 2, 'max_seconds': 10.}, 'units': [unit()]}
        self.path = self.root/'run.json'
        atomic_json(self.path, self.spec)

    def tearDown(self):
        self.temp.cleanup()

    def create(self, spec=None):
        if spec: atomic_json(self.path, spec)
        return create_run(self.project, (spec or self.spec)['kind'], 'run.json')

    def events(self):
        with closing(sqlite3.connect(self.project.db)) as db:
            return db.execute('SELECT kind,doc FROM events ORDER BY id').fetchall()

    def native_entry(self):
        binding = record_native_run_started(self.project, 'inspect', {})
        checkpoint = self.project.data/'checkpoints/hard-crash.blend'
        checkpoint.write_bytes(b'persisted entry scene')
        reference = {'path': checkpoint.relative_to(self.root).as_posix(), 'sha256': sha(checkpoint)}
        with self.project.transaction() as db:
            state = self.project.state(db)
            state['pending_blender_operation'] = {'operation': 'inspect', 'arguments': {},
                'status': 'running', 'checkpoint': reference, 'run_binding': binding}
            self.project.save(db, state, 'blender_started', state['pending_blender_operation'])
        return reference

    def restore_entry(self, reference):
        with self.project.transaction() as db:
            state = self.project.state(db)
            state.pop('pending_blender_operation', None)
            self.project.save(db, state, 'blender_recovered', {'checkpoint': reference})

    def test_status_of_old_project_has_no_migration_or_file_mutation(self):
        before = sha(self.project.db)
        result = run_status(self.project)
        self.assertEqual(result['runs'], [])
        self.assertTrue(result['read_only'])
        self.assertEqual(sha(self.project.db), before)
        with closing(sqlite3.connect(self.project.db)) as db:
            self.assertIsNone(db.execute("SELECT name FROM sqlite_master WHERE name='runs'").fetchone())

    def test_create_idempotent_and_reused_spec_or_code_is_refused(self):
        first = self.create(); events = self.events()
        self.assertEqual(self.create()['run_id'], first['run_id'])
        self.assertEqual(self.events(), events)
        changed = copy.deepcopy(self.spec); changed['budgets']['max_seconds'] = 9.
        atomic_json(self.path, changed)
        with self.assertRaises(StudioError): create_run(self.project, 'garment', 'run.json')
        atomic_json(self.path, self.spec)
        with patch('a3d.runs._runtime', return_value='f'*64), self.assertRaises(StudioError):
            create_run(self.project, 'garment', 'run.json')

    def test_shared_archive_and_native_evidence_changes_invalidate_run(self):
        from a3d.runs import COMMON_CODE_PATHS,_runtime
        run=self.create();original=_runtime()
        for name in ('a3d/run_projection_archive.py','a3d/native_evidence.py'):
            self.assertIn(name,COMMON_CODE_PATHS)
            def changed(path):return '0'*64 if Path(path)==ROOT/name else sha(path)
            with self.subTest(name=name),patch('a3d.runs.sha',side_effect=changed):
                self.assertNotEqual(_runtime(),original)
                with self.assertRaises(StudioError):next_run_step(self.project,run['run_id'])

    def test_blender_next_prepares_exact_guarded_code_only_and_is_idempotent(self):
        run = self.create(); before_state = self.project.state()
        prepared = next_run_step(self.project, run['run_id']); before = self.events()
        self.assertEqual(prepared['status'], 'AWAITING_CONFIRMATION')
        self.assertTrue(prepared['execution_permission_required'])
        self.assertFalse(prepared['executed'])
        self.assertIn('dispatch', prepared['code'])
        self.assertEqual(next_run_step(self.project, run['run_id']), prepared)
        self.assertEqual(self.events(), before)
        self.assertEqual(self.project.state(), before_state)
        self.assertEqual(len(run_status(self.project, run['run_id'])['units'][0]['attempts']), 1)

    def test_arbitrary_pass_evidence_and_wrong_native_operation_do_not_advance(self):
        run = self.create(); next_run_step(self.project, run['run_id'])
        forged = self.root/'fake-pass.json'; atomic_json(forged, {'status': 'PASS'})
        self.project.evidence('fake-native-receipt', 'fake-pass.json')
        self.assertIsNone(record_native_run_result(self.project, 'resume', {}, {'status': 'PASS'}))
        self.assertEqual(next_run_step(self.project, run['run_id'])['status'], 'AWAITING_CONFIRMATION')
        self.assertEqual(run_status(self.project, run['run_id'])['units'][0]['status'], 'AWAITING_CONFIRMATION')

    def test_registered_native_result_exact_artifact_and_dependency_field(self):
        dependent = unit('second', ['inspect'])
        dependent['operation'] = 'inspect_body_source'
        dependent['arguments'] = {'selection_path': {'$unit': 'inspect', 'field': 'artifact.path'}}
        spec = dict(self.spec, units=[dependent, unit()])
        run = self.create(spec); next_run_step(self.project, run['run_id'])
        artifact = self.root/'selection.json'; artifact.write_text('{}')
        result = {'status': 'READY', 'qualification': 'GEOMETRY_ONLY',
                  'artifact': {'path': 'selection.json', 'sha256': sha(artifact)}}
        registered = record_native_run_result(self.project, 'inspect', {}, result)
        self.assertEqual(registered['status'], 'COMPLETED')
        with patch('a3d.guard.admit_operation'):
            next_step = next_run_step(self.project, run['run_id'])
        self.assertEqual(next_step['unit_id'], 'second')
        self.assertEqual(next_step['arguments'], {'selection_path': 'selection.json'})
        artifact.write_text('changed')
        before = sha(self.project.db)
        status = run_status(self.project, run['run_id'])
        self.assertEqual(status['binding_status'], 'STALE_OR_UNVERIFIED')
        self.assertEqual(sha(self.project.db), before)
        with self.assertRaises(StudioError): next_run_step(self.project, run['run_id'])

    def test_native_receipt_requires_canonical_registration(self):
        run = self.create(); next_run_step(self.project, run['run_id'])
        record_native_run_result(self.project, 'inspect', {}, {'status': 'PASS', 'qualification': 'COUPON_ONLY'})
        with closing(sqlite3.connect(self.project.db)) as db, db:
            db.execute("DELETE FROM events WHERE kind='run_native_receipt'")
        self.assertEqual(run_status(self.project, run['run_id'])['binding_status'], 'STALE_OR_UNVERIFIED')
        with self.assertRaises(StudioError): next_run_step(self.project, run['run_id'])

    def test_execution_completion_does_not_promote_any_gate(self):
        run = self.create(); before = self.project.state()['gates']
        next_run_step(self.project, run['run_id'])
        record_native_run_result(self.project, 'inspect', {}, {'status': 'PASS', 'qualification': 'COUPON_ONLY'})
        completed = next_run_step(self.project, run['run_id'])
        self.assertEqual(completed['status'], 'COMPLETED')
        self.assertEqual(completed['qualification'], 'NOT_GRANTED')
        self.assertFalse(completed['accepted'])
        self.assertEqual(self.project.state()['gates'], before)
        self.assertEqual(run_status(self.project, run['run_id'])['diagnostics']['qualifications'], {'inspect': 'COUPON_ONLY'})

    def test_needs_correction_is_executed_but_blocks_downstream(self):
        spec = dict(self.spec, units=[unit(), unit('second', ['inspect'])])
        run = self.create(spec); next_run_step(self.project, run['run_id'])
        receipt = record_native_run_result(self.project, 'inspect', {}, {'status': 'NEEDS_CORRECTION'})
        self.assertEqual(receipt['status'], 'NEEDS_CORRECTION')
        self.assertEqual(next_run_step(self.project, run['run_id'])['status'], 'NEEDS_CORRECTION')
        self.assertEqual(run_status(self.project, run['run_id'])['units'][1]['attempts'], [])
        from a3d.native_evidence import native_origin, native_observation_origin
        before = sha(self.project.db)
        with self.assertRaisesRegex(StudioError, 'canonical completed attempt'):
            native_origin(self.project, lambda doc:doc['operation']=='inspect')
        observed, origin = native_observation_origin(self.project, lambda doc:doc['operation']=='inspect')
        self.assertEqual(observed['result']['status'], 'NEEDS_CORRECTION')
        self.assertEqual(origin['scope'], 'OBSERVATION_ONLY')
        self.assertEqual(origin['attempt_status'], 'NEEDS_CORRECTION')
        self.assertFalse(origin['accepted'])
        self.assertEqual(origin['product_acceptance'], 'NOT_GRANTED')
        self.assertEqual(sha(self.project.db), before)

    def test_diagnostic_origin_still_refuses_changed_outputs_and_unreturned_work(self):
        from a3d.native_evidence import native_observation_origin
        run = self.create(); next_run_step(self.project, run['run_id'])
        with self.assertRaises(StudioError):
            native_observation_origin(self.project, lambda doc:True)
        output = self.root/'observed.json'; output.write_text('{}')
        record_native_run_result(self.project, 'inspect', {}, {'status':'NEEDS_CORRECTION',
            'artifact':{'path':'observed.json','sha256':sha(output)}})
        native_observation_origin(self.project, lambda doc:doc['operation']=='inspect')
        output.write_text('changed')
        before = sha(self.project.db)
        with self.assertRaisesRegex(StudioError, 'reference changed'):
            native_observation_origin(self.project, lambda doc:doc['operation']=='inspect')
        self.assertEqual(sha(self.project.db), before)

    def test_legacy_targeted_observation_traces_stale_continuation_but_never_admits_it(self):
        from a3d.native_evidence import native_origin, native_observation_origin
        run = self.create(); next_run_step(self.project, run['run_id'])
        mesh = self.root/'observed.json'; mesh.write_text('{}')
        projection = self.project.data/'blender/piece-candidates.json'
        projection.parent.mkdir(parents=True, exist_ok=True); projection.write_text('{}')
        mesh_ref = {'path':'observed.json', 'sha256':sha(mesh)}
        # Emulate an older native receipt produced before projection archival.
        with patch('a3d.run_projection_archive.archive_projection_references',
                   side_effect=lambda project,attempt,refs:(refs,[])):
            record_native_run_result(self.project, 'inspect', {}, {'status':'NEEDS_CORRECTION',
                'artifact':mesh_ref, 'projection':{'path':'.a3d/blender/piece-candidates.json','sha256':sha(projection)}})
        projection.write_text('{"newer_component":true}')
        before = sha(self.project.db)
        with self.assertRaises(StudioError): native_origin(self.project, lambda doc:True)
        with self.assertRaisesRegex(StudioError,'reference changed'):
            native_observation_origin(self.project, lambda doc:True)
        _, observed = native_observation_origin(self.project, lambda doc:True, mesh_ref)
        self.assertEqual(observed['stale_project_projections'][0]['current_ref']['sha256'],sha(projection))
        self.assertEqual(observed['scope'],'OBSERVATION_ONLY');self.assertFalse(observed['accepted'])
        with self.assertRaisesRegex(StudioError,'not bound'):
            native_observation_origin(self.project,lambda doc:True,{'path':'observed.json','sha256':'f'*64})
        mesh.write_text('changed')
        with self.assertRaisesRegex(StudioError,'reference changed'):
            native_observation_origin(self.project,lambda doc:True,mesh_ref)
        self.assertEqual(sha(self.project.db),before)

    def test_registered_projection_archive_survives_live_changes_but_not_artifact_changes(self):
        from a3d.native_evidence import native_origin
        run=self.create();next_run_step(self.project,run['run_id'])
        mesh=self.root/'observed.json';mesh.write_text('{}')
        projection=self.project.data/'blender/piece-candidates.json'
        projection.parent.mkdir(parents=True,exist_ok=True);projection.write_text('{}')
        result={'status':'PASS','qualification':'COUPON_ONLY',
            'artifact':{'path':'observed.json','sha256':sha(mesh)},
            'projection':{'path':'.a3d/blender/piece-candidates.json','sha256':sha(projection)}}
        record_native_run_result(self.project,'inspect',{},result)
        projection.unlink();before=sha(self.project.db)
        receipt,origin=native_origin(self.project,lambda doc:doc['operation']=='inspect')
        self.assertEqual(receipt['result'],result)
        self.assertFalse(receipt['accepted']);self.assertEqual(receipt['qualification'],'COUPON_ONLY')
        self.assertEqual(origin['archived_project_projections'][0]['current_projection_status'],'ABSENT')
        self.assertEqual(sha(self.project.db),before)
        self.assertEqual(next_run_step(self.project,run['run_id'])['status'],'COMPLETED')
        before=sha(self.project.db)
        mesh.write_text('changed')
        with self.assertRaisesRegex(StudioError,'reference changed'):native_origin(self.project,lambda doc:True)
        self.assertEqual(sha(self.project.db),before)

    def test_archive_orphan_without_registered_callback_never_creates_native_origin(self):
        from a3d.native_evidence import native_origin
        run=self.create();next_run_step(self.project,run['run_id'])
        record_native_run_started(self.project,'inspect',{})
        projection=self.project.data/'blender/piece-candidates.json'
        projection.parent.mkdir(parents=True,exist_ok=True);projection.write_text('{}')
        result={'status':'PASS','projection':{'path':'.a3d/blender/piece-candidates.json','sha256':sha(projection)}}
        with patch('a3d.runs._save',side_effect=RuntimeError('journal rollback')):
            with self.assertRaises(RuntimeError):record_native_run_result(self.project,'inspect',{},result)
        self.assertTrue(list((self.project.data/'runs/native/projections').rglob('*.json')))
        with self.assertRaisesRegex(StudioError,'canonically registered'):native_origin(self.project,lambda doc:True)
        self.assertEqual(next_run_step(self.project,run['run_id'])['status'],'UNKNOWN_COMPLETION')

    def test_pending_recovery_and_recorded_restore_before_replay(self):
        run = self.create(); prepared = next_run_step(self.project, run['run_id'])
        checkpoint = self.project.data/'checkpoints/entry.blend'; checkpoint.write_bytes(b'checkpoint fixture')
        reference = {'path': checkpoint.relative_to(self.root).as_posix(), 'sha256': sha(checkpoint), 'created_at': '2026-10-03T12:00:00Z'}
        with self.project.transaction() as db:
            state = self.project.state(db)
            state['pending_blender_operation'] = {'operation': 'inspect', 'status': 'failed', 'checkpoint': reference}
            self.project.save(db, state, 'blender_failed', {})
        record_native_run_failure(self.project, 'inspect', {}, 'interrupted', reference)
        before = self.events(); result = next_run_step(self.project, run['run_id'])
        self.assertEqual(result['status'], 'RECOVERY_REQUIRED')
        self.assertFalse(result['continuous_physics_resume'])
        self.assertEqual(self.events(), before)
        with self.assertRaises(StudioError): create_run(self.project, 'garment', 'run.json')
        with self.project.transaction() as db:
            state = self.project.state(db); state.pop('pending_blender_operation')
            self.project.save(db, state, 'manual_pending_clear', {})
        self.assertEqual(next_run_step(self.project, run['run_id'])['status'], 'INCOMPLETE')
        with self.project.transaction() as db:
            self.project.save(db, self.project.state(db), 'blender_recovered', {'checkpoint': reference})
        replay = next_run_step(self.project, run['run_id'])
        self.assertNotEqual(replay['attempt_id'], prepared['attempt_id'])
        self.assertFalse(replay['executed'])
        record_native_run_failure(self.project, 'inspect', {}, 'second failure', reference)
        with self.project.transaction() as db:
            self.project.save(db, self.project.state(db), 'blender_recovered', {'checkpoint': reference})
        self.assertEqual(next_run_step(self.project, run['run_id'])['reason'], 'ATTEMPT_BUDGET')

    def test_stop_is_incomplete_idempotent_and_does_not_clear_pending(self):
        run = self.create(); next_run_step(self.project, run['run_id'])
        with self.project.transaction() as db:
            state = self.project.state(db); state['pending_blender_operation'] = {'status': 'running'}
            self.project.save(db, state, 'blender_started', {})
        stopped = request_run_stop(self.project, run['run_id']); events = self.events()
        self.assertEqual(stopped['status'], 'STOP_REQUESTED')
        self.assertEqual(request_run_stop(self.project, run['run_id']), stopped)
        self.assertEqual(self.events(), events)
        self.assertEqual(self.project.state()['pending_blender_operation'], {'status': 'running'})
        self.assertFalse(stopped['execution_complete'])

    def test_dag_refs_input_and_budget_failures_do_not_create_runs(self):
        for failure in ('cycle', 'unknown', 'duplicate', 'target', 'input', 'budget', 'request_override', 'dependency_field'):
            spec = copy.deepcopy(self.spec)
            if failure == 'cycle': spec['units'] = [unit('a', ['b']), unit('b', ['a'])]
            if failure == 'unknown': spec['units'][0]['dependencies'] = ['missing']
            if failure == 'duplicate': spec['units'] *= 2
            if failure == 'target': spec['asset_id'] = 'other'
            if failure == 'input': spec['inputs'] = [{'path': 'absent.json', 'sha256': 'a'*64}]
            if failure == 'budget': spec['budgets']['max_attempts'] = True
            if failure == 'request_override': spec['units'][0]['arguments']['request_key'] = 'different'
            if failure == 'dependency_field': spec['units'][0]['arguments'] = {'selection_path': {'$unit': 'missing', 'field': 'artifact.path'}}
            atomic_json(self.path, spec)
            with self.subTest(failure=failure), self.assertRaises((StudioError, FileNotFoundError)):
                create_run(self.project, 'garment', 'run.json')
        self.assertEqual(run_status(self.project)['runs'], [])

    def test_unknown_comfy_submission_is_never_repeated(self):
        comfy = unit('render'); comfy.update(executor='comfy', operation='submit_workflow',
            arguments={'component_id': 'body.skull', 'workflow_id': 'registered-workflow', 'parameters': {}})
        spec = dict(self.spec, kind='comfy', units=[comfy])
        run = self.create(spec)
        with patch('a3d.comfy.Comfy') as client:
            client.return_value.submit.side_effect = TimeoutError('unknown native receipt')
            first = next_run_step(self.project, run['run_id'])
            second = next_run_step(self.project, run['run_id'])
            self.assertEqual(first['status'], 'SUBMISSION_UNKNOWN')
            self.assertEqual(second['status'], 'SUBMISSION_UNKNOWN')
            self.assertEqual(client.return_value.submit.call_count, 1)
            self.assertEqual(first['request_key'], second['request_key'])

    def test_native_time_budget_excludes_approval_waiting_and_refuses_invalid_timing(self):
        run = self.create(); prepared = next_run_step(self.project, run['run_id'])
        self.assertEqual(prepared['budgets']['max_seconds'], 10.)
        for invalid in (True, float('nan'), -1):
            with self.subTest(invalid=invalid), self.assertRaises(StudioError):
                record_native_run_result(self.project, 'inspect', {}, {'status': 'PASS'}, elapsed_seconds=invalid)
        result = record_native_run_result(self.project, 'inspect', {}, {'status': 'PASS'}, elapsed_seconds=11.)
        self.assertEqual(result['status'], 'INCOMPLETE')
        status = run_status(self.project, run['run_id'])
        self.assertEqual(status['units'][0]['reason'], 'TIME_BUDGET')
        self.assertEqual(status['units'][0]['attempts'][0]['elapsed_seconds'], 11.)

    def test_missing_source_is_diagnostic_and_refuses_advancement(self):
        source = self.root/'source.json'; source.write_text('{}')
        spec = dict(self.spec, inputs=[{'path': 'source.json', 'sha256': sha(source)}])
        run = self.create(spec); source.unlink(); before = sha(self.project.db)
        self.assertEqual(run_status(self.project, run['run_id'])['binding_status'], 'STALE_OR_UNVERIFIED')
        self.assertEqual(sha(self.project.db), before)
        with self.assertRaises(StudioError): next_run_step(self.project, run['run_id'])

    def test_stop_prepared_unexecuted_unit_allows_new_run_without_fake_completion(self):
        run = self.create(); next_run_step(self.project, run['run_id'])
        self.assertEqual(request_run_stop(self.project, run['run_id'])['status'], 'STOPPED_INCOMPLETE')
        self.assertEqual(run_status(self.project, run['run_id'])['units'][0]['status'], 'CANCELLED_UNEXECUTED')
        spec = dict(self.spec, id='other-run'); other = self.create(spec)
        self.assertEqual(next_run_step(self.project, other['run_id'])['status'], 'AWAITING_CONFIRMATION')

    def test_unknown_native_completion_does_not_replay_or_complete(self):
        run = self.create(); next_run_step(self.project, run['run_id'])
        registered = record_native_run_result(self.project, 'inspect', {}, {})
        self.assertEqual(registered['status'], 'UNKNOWN_COMPLETION')
        before = self.events()
        self.assertEqual(next_run_step(self.project, run['run_id'])['status'], 'UNKNOWN_COMPLETION')
        self.assertEqual(self.events(), before)

    def test_unrelated_handler_change_invalidates_only_dependent_units(self):
        spec = dict(self.spec, units=[unit('a'), unit('b')])
        run = self.create(spec); next_run_step(self.project, run['run_id'])
        record_native_run_result(self.project, 'inspect', {}, {'status': 'PASS'})
        from a3d.runs import _unit_runtime
        original = _unit_runtime
        def changed(selected):
            result = original(selected)
            if selected['id'] == 'a': result = dict(result, altered='0'*64)
            return result
        with patch('a3d.runs._unit_runtime', side_effect=changed):
            self.assertEqual(run_status(self.project, run['run_id'])['binding_status'], 'STALE_OR_UNVERIFIED')
            self.assertEqual(next_run_step(self.project, run['run_id'])['unit_id'], 'b')

    def test_started_callback_failure_never_prepares_duplicate_native_mutation(self):
        run = self.create(); next_run_step(self.project, run['run_id'])
        started = record_native_run_started(self.project, 'inspect', {})
        self.assertEqual(started['status'], 'WAITING_RESULT')
        with self.assertRaises(StudioError): record_native_run_started(self.project, 'inspect', {})
        outcome = next_run_step(self.project, run['run_id'])
        self.assertEqual(outcome['status'], 'UNKNOWN_COMPLETION')
        self.assertFalse(outcome['reapplication_allowed'])
        self.assertNotIn('code', outcome)

    def test_hard_crash_requires_exact_restoration_then_prepares_one_replay(self):
        run = self.create(); prepared = next_run_step(self.project, run['run_id'])
        reference = self.native_entry()
        bound = record_native_run_checkpoint(self.project, 'inspect', {}, reference)
        self.assertEqual(bound['attempt_id'], prepared['attempt_id'])
        events = self.events()
        self.assertEqual(record_native_run_checkpoint(self.project, 'inspect', {}, reference), bound)
        self.assertEqual(self.events(), events)
        recovery = next_run_step(self.project, run['run_id'])
        self.assertEqual(recovery['status'], 'RECOVERY_REQUIRED')
        self.assertFalse(recovery['continuous_physics_resume'])
        self.assertEqual(len(run_status(self.project, run['run_id'])['units'][0]['attempts']), 1)
        with self.project.transaction() as db:
            state = self.project.state(db); state.pop('pending_blender_operation')
            self.project.save(db, state, 'manual_pending_clear', {})
        outcome = next_run_step(self.project, run['run_id'])
        self.assertEqual(outcome['status'], 'UNKNOWN_COMPLETION')
        self.assertFalse(outcome['reapplication_allowed'])
        wrong = dict(reference, sha256='e'*64)
        self.restore_entry(wrong)
        self.assertEqual(next_run_step(self.project, run['run_id'])['status'], 'UNKNOWN_COMPLETION')
        self.restore_entry(reference)
        replay = next_run_step(self.project, run['run_id'])
        self.assertEqual(replay['status'], 'AWAITING_CONFIRMATION')
        self.assertNotEqual(replay['attempt_id'], prepared['attempt_id'])
        self.assertEqual(next_run_step(self.project, run['run_id']), replay)
        attempts = run_status(self.project, run['run_id'])['units'][0]['attempts']
        self.assertEqual(len(attempts), 2)
        self.assertEqual(attempts[0]['status'], 'INTERRUPTED')
        self.assertNotIn('receipt', attempts[0])

    def test_saved_result_without_canonical_full_result_restores_before_replay(self):
        run = self.create(); prepared = next_run_step(self.project, run['run_id'])
        reference = self.native_entry()
        record_native_run_checkpoint(self.project, 'inspect', {}, reference)
        with self.project.transaction() as db:
            state = self.project.state(db)
            state['pending_blender_operation']['status'] = 'RESULT_READY'
            self.project.save(db, state, 'blender_result_ready', {'operation': 'inspect',
                'arguments': {}, 'checkpoint': reference})
        self.assertEqual(next_run_step(self.project, run['run_id'])['status'], 'RECOVERY_REQUIRED')
        self.restore_entry(reference)
        replay = next_run_step(self.project, run['run_id'])
        self.assertNotEqual(replay['attempt_id'], prepared['attempt_id'])
        self.assertNotIn('receipt', run_status(self.project, run['run_id'])['units'][0]['attempts'][0])

    def test_crash_between_dispatcher_checkpoint_and_callback_uses_canonical_binding(self):
        run = self.create(); prepared = next_run_step(self.project, run['run_id'])
        reference = self.native_entry()  # process stops before record_native_run_checkpoint
        self.assertEqual(next_run_step(self.project, run['run_id'])['status'], 'RECOVERY_REQUIRED')
        self.restore_entry(reference)
        replay = next_run_step(self.project, run['run_id'])
        self.assertEqual(replay['status'], 'AWAITING_CONFIRMATION')
        self.assertNotEqual(replay['attempt_id'], prepared['attempt_id'])
        self.assertEqual(next_run_step(self.project, run['run_id']), replay)
        attempts = run_status(self.project, run['run_id'])['units'][0]['attempts']
        self.assertEqual(len(attempts), 2)
        self.assertEqual(attempts[0]['status'], 'INTERRUPTED')

    def test_checkpoint_discovery_refuses_unrelated_run_binding(self):
        run = self.create(); next_run_step(self.project, run['run_id'])
        reference = self.native_entry()
        with self.project.transaction() as db:
            row = db.execute("SELECT id,doc FROM events WHERE kind='blender_started'").fetchone()
            event = json.loads(row[1]); event['run_binding']['attempt_id'] = 'attempt.unrelated'
            db.execute('UPDATE events SET doc=? WHERE id=?', (canonical(event).decode(), row[0]))
        self.restore_entry(reference)
        result = next_run_step(self.project, run['run_id'])
        self.assertEqual(result['status'], 'UNKNOWN_COMPLETION')
        self.assertFalse(result['reapplication_allowed'])
        self.assertEqual(len(run_status(self.project, run['run_id'])['units'][0]['attempts']), 1)

    def test_native_checkpoint_requires_dispatcher_event_and_refuses_changed_boundary(self):
        run = self.create(); next_run_step(self.project, run['run_id'])
        reference = self.native_entry()
        with self.project.transaction() as db:
            db.execute("DELETE FROM events WHERE kind='blender_started'")
        before = sha(self.project.db)
        with self.assertRaises(StudioError): record_native_run_checkpoint(self.project, 'inspect', {}, reference)
        self.assertEqual(sha(self.project.db), before)
        with self.project.transaction() as db:
            self.project.save(db, self.project.state(db), 'blender_started',
                              self.project.state(db)['pending_blender_operation'])
        record_native_run_checkpoint(self.project, 'inspect', {}, reference)
        changed = self.project.data/'checkpoints/other.blend'; changed.write_bytes(b'other scene')
        other = {'path': changed.relative_to(self.root).as_posix(), 'sha256': sha(changed)}
        with self.project.transaction() as db:
            state = self.project.state(db); state['pending_blender_operation']['checkpoint'] = other
            self.project.save(db, state, 'blender_started', state['pending_blender_operation'])
        with self.assertRaises(StudioError): record_native_run_checkpoint(self.project, 'inspect', {}, other)
        (self.root/reference['path']).write_bytes(b'stale scene')
        self.restore_entry(reference)
        with self.assertRaises(StudioError): next_run_step(self.project, run['run_id'])

    def test_orphan_atomic_receipt_after_rollback_can_only_reconcile_exact_native_callback(self):
        run = self.create(); next_run_step(self.project, run['run_id'])
        record_native_run_started(self.project, 'inspect', {})
        with patch('a3d.runs._save', side_effect=RuntimeError('injected journal rollback')):
            with self.assertRaises(RuntimeError):
                record_native_run_result(self.project, 'inspect', {}, {'status': 'PASS'}, elapsed_seconds=1.)
        self.assertEqual(next_run_step(self.project, run['run_id'])['status'], 'UNKNOWN_COMPLETION')
        with self.assertRaises(StudioError):
            record_native_run_result(self.project, 'inspect', {}, {'status': 'READY'}, elapsed_seconds=1.)
        recovered = record_native_run_result(self.project, 'inspect', {}, {'status': 'PASS'}, elapsed_seconds=1.)
        self.assertEqual(recovered['status'], 'COMPLETED')

    def test_canonical_result_ready_recovers_callback_failure_without_reexecution(self):
        run = self.create(); prepared = next_run_step(self.project, run['run_id'])
        before = sha(self.project.db)
        self.assertEqual(native_attempt_binding(self.project, 'inspect', {})['attempt_id'], prepared['attempt_id'])
        self.assertEqual(sha(self.project.db), before)
        binding = record_native_run_started(self.project, 'inspect', {})
        modules = {'a3d.runs': sha(ROOT/'a3d/runs.py'), 'blender.operations': sha(ROOT/'blender/operations.py')}
        from a3d.core import digest
        result = {'status':'PASS', 'qualification':'COUPON_ONLY', 'runtime':
            {'loaded_modules':modules, 'loaded_source_sha256':digest(modules)}}
        event = {**{key:binding[key] for key in ('run_id','unit_id','attempt_id','binding_sha256')},
            'operation':'inspect', 'arguments':{}, 'result':result, 'result_sha256':digest(result),
            'entry_checkpoint':None, 'elapsed_seconds':1., 'runtime_sha256':digest(modules)}
        with self.project.transaction() as db:
            self.project.save(db, self.project.state(db), 'run_native_result_ready', event)
        with patch('a3d.runs._save', side_effect=RuntimeError('injected lost callback')):
            with self.assertRaises(RuntimeError):
                record_native_run_result(self.project, 'inspect', {}, result, elapsed_seconds=1.)
        reconciled = next_run_step(self.project, run['run_id'])
        self.assertTrue(reconciled['reconciled']); self.assertFalse(reconciled['executed'])
        self.assertEqual(reconciled['status'], 'COMPLETED')
        self.assertEqual(run_status(self.project, run['run_id'])['units'][0]['qualification'], 'COUPON_ONLY')

    def test_result_registered_before_pending_finalization_is_finalized_without_restore(self):
        from a3d.core import digest
        run = self.create(); next_run_step(self.project, run['run_id'])
        checkpoint = self.project.data/'checkpoints/ready.blend'; checkpoint.write_bytes(b'entry')
        ref = {'path':checkpoint.relative_to(self.root).as_posix(), 'sha256':sha(checkpoint)}
        binding = record_native_run_started(self.project, 'inspect', {}, ref)
        modules = {'a3d.runs':sha(ROOT/'a3d/runs.py')}
        projection=self.project.data/'blender/piece-candidates.json'
        projection.parent.mkdir(parents=True,exist_ok=True);projection.write_text('{}')
        result = {'status':'PASS', 'runtime':{'loaded_modules':modules, 'loaded_source_sha256':digest(modules)},
            'projection':{'path':'.a3d/blender/piece-candidates.json','sha256':sha(projection)}}
        event = {**{key:binding[key] for key in ('run_id','unit_id','attempt_id','binding_sha256')},
            'operation':'inspect', 'arguments':{}, 'result':result, 'result_sha256':digest(result),
            'entry_checkpoint':ref, 'elapsed_seconds':1., 'runtime_sha256':digest(modules)}
        with self.project.transaction() as db:
            state=self.project.state(db); state['pending_blender_operation']={
                'operation':'inspect', 'arguments':{}, 'checkpoint':ref, 'status':'RESULT_READY'}
            self.project.save(db,state,'run_native_result_ready',event)
        record_native_run_result(self.project,'inspect',{},result,ref,1.)
        projection.write_text('{"newer_projection":true}')
        reconciled=next_run_step(self.project,run['run_id'])
        self.assertTrue(reconciled['reconciled'])
        self.assertNotIn('pending_blender_operation',self.project.state())
        self.assertEqual(run_status(self.project,run['run_id'])['units'][0]['status'],'COMPLETED')

    def comfy_owned_job(self, status):
        from a3d.core import digest
        def submit(project_root, request_key, **arguments):
            workflow=self.root/'workflow.json'; atomic_json(workflow,{})
            job={'job_id':'native-job', 'request_key':request_key, **arguments, 'status':status,
                'prompt_id':'native-prompt', 'fingerprint':'a'*64, 'workflow_path':'workflow.json',
                'workflow_sha256':digest({}), 'outputs':[]}
            with self.project.transaction() as db: self.project.save_job(db,job)
            return job
        return submit

    def test_comfy_wall_clock_phase_budget_includes_queue_time_between_polls(self):
        comfy=unit('render'); comfy.update(executor='comfy',operation='submit_workflow',
            arguments={'component_id':'body.skull','workflow_id':'registered-workflow','parameters':{}})
        run=self.create(dict(self.spec,kind='comfy',units=[comfy]))
        with patch('a3d.comfy.Comfy') as client:
            client.return_value.submit.side_effect=self.comfy_owned_job('queued')
            with patch('a3d.runs.now',return_value='2026-10-03T10:00:00+00:00'):
                self.assertEqual(next_run_step(self.project,run['run_id'])['status'],'WAITING_EXTERNAL')
            with patch('a3d.runs.now',return_value='2026-10-03T10:01:00+00:00'):
                self.assertEqual(next_run_step(self.project,run['run_id'])['status'],'INCOMPLETE')
            self.assertEqual(client.return_value.submit.call_count,1)
        status=run_status(self.project,run['run_id']); attempt=status['units'][0]['attempts'][0]
        self.assertEqual(attempt['phase_elapsed_seconds'],60.)
        self.assertTrue(attempt['external_pending'])
        self.assertEqual(request_run_stop(self.project,run['run_id'])['status'],'STOP_REQUESTED')

    def test_comfy_completion_requires_local_outputs_and_canonical_registration(self):
        comfy=unit('render'); comfy.update(executor='comfy',operation='submit_workflow',
            arguments={'component_id':'body.skull','workflow_id':'registered-workflow','parameters':{}})
        run=self.create(dict(self.spec,kind='comfy',units=[comfy]))
        def outputs(project_root, job_id, download):
            self.assertTrue(download)
            path=self.root/'native-output.glb'; path.write_bytes(b'UNIT TEST NOT GEOMETRY PROOF')
            ref={'path':'native-output.glb','sha256':sha(path)}
            with self.project.transaction() as db:
                job=self.project.job(job_id,db); job['outputs']=[ref]; self.project.save_job(db,job)
            return {'job_id':job_id,'outputs':[ref]}
        with patch('a3d.comfy.Comfy') as client:
            client.return_value.submit.side_effect=self.comfy_owned_job('completed')
            client.return_value.outputs.side_effect=StudioError('outputs unavailable')
            self.assertEqual(next_run_step(self.project,run['run_id'])['status'],'WAITING_OUTPUTS')
            client.return_value.outputs.side_effect=outputs
            self.assertEqual(next_run_step(self.project,run['run_id'])['status'],'RUNNING')
            self.assertEqual(client.return_value.submit.call_count,1)
        self.assertEqual(next_run_step(self.project,run['run_id'])['status'],'COMPLETED')
        self.assertFalse(run_status(self.project,run['run_id'])['accepted'])
        (self.root/'native-output.glb').write_bytes(b'changed')
        self.assertEqual(run_status(self.project,run['run_id'])['binding_status'],'STALE_OR_UNVERIFIED')


if __name__ == '__main__': unittest.main()
