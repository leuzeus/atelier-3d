"""Portable recovery contract; fake Blender files are not native geometry proof."""
import copy
import json
import sqlite3
import sys
import types
import unittest
from contextlib import closing, nullcontext
from pathlib import Path
from unittest.mock import patch

from a3d.core import ROOT, StudioError, atomic_json, digest, sha
from a3d.guard import admit_operation
from a3d.runs import (next_run_step, record_native_run_checkpoint, record_native_run_result,
                      returned_run_recovery, run_status)
from blender.operations import dispatch
from tests import test_runs as fixtures


class ReturnedRunRecovery(unittest.TestCase):
    setUp = fixtures.Runs.setUp
    tearDown = fixtures.Runs.tearDown
    create = fixtures.Runs.create
    events = fixtures.Runs.events
    native_entry = fixtures.Runs.native_entry

    def returned(self, outcome='NEEDS_CORRECTION', elapsed=1., legacy_session=False):
        run = self.create(); prepared = next_run_step(self.project, run['run_id'])
        ref = self.native_entry()
        record_native_run_checkpoint(self.project, 'inspect', {}, ref)
        modules = {'a3d.runs': sha(ROOT/'a3d/runs.py')}
        result = {'readiness': outcome, 'runtime': {'loaded_modules': modules,
                  'loaded_source_sha256': digest(modules)}}
        if legacy_session:
            self.fake_blender()
            result.update(session={'path': '.a3d/blender/session.json',
                                  'sha256': sha(self.project.data/'blender/session.json')},
                          working={'path': '.a3d/blender/working-abcd.blend',
                                   'sha256': sha(self.project.data/'blender/working-abcd.blend')})
        with self.project.transaction() as db:
            state = self.project.state(db)
            binding = state['pending_blender_operation']['run_binding']
            state['pending_blender_operation']['status'] = 'RESULT_READY'
            self.project.save(db, state, 'run_native_result_ready', {
                **{key: binding[key] for key in ('run_id', 'unit_id', 'attempt_id', 'binding_sha256')},
                'operation': 'inspect', 'arguments': {}, 'result': result,
                'result_sha256': digest(result), 'entry_checkpoint': ref,
                'elapsed_seconds': elapsed, 'runtime_sha256': digest(modules)})
        legacy = patch('a3d.run_projection_archive.archive_projection_references',
                       side_effect=lambda project, attempt, refs: (refs, [])) if legacy_session else nullcontext()
        with legacy:
            record_native_run_result(self.project, 'inspect', {}, result, ref, elapsed)
        reconciled = next_run_step(self.project, run['run_id'])
        self.assertTrue(reconciled['reconciled'])
        self.assertNotIn('pending_blender_operation', self.project.state())
        return run, {'run_id': run['run_id'], 'attempt_id': prepared['attempt_id']}, ref

    def fake_blender(self):
        working = self.project.data/'blender/working-abcd.blend'
        working.parent.mkdir(exist_ok=True)
        working.write_bytes(b'rejected candidate scene')
        atomic_json(self.project.data/'blender/session.json', {
            'original': None, 'working': str(working)})
        bpy = types.SimpleNamespace(data=types.SimpleNamespace(filepath=str(working), is_dirty=False))
        calls = []

        def open_mainfile(filepath):
            calls.append(('open', filepath)); bpy.data.filepath = filepath

        def save_as_mainfile(filepath, check_existing):
            calls.append(('save', filepath))
            Path(filepath).write_bytes(Path(bpy.data.filepath).read_bytes())
            bpy.data.filepath = filepath

        bpy.ops = types.SimpleNamespace(wm=types.SimpleNamespace(
            open_mainfile=open_mainfile, save_as_mainfile=save_as_mainfile))
        return bpy, calls

    def change_run(self, run_id, change):
        with self.project.transaction() as db:
            doc = json.loads(db.execute('SELECT doc FROM runs WHERE id=?', (run_id,)).fetchone()[0])
            change(doc)
            db.execute('UPDATE runs SET doc=? WHERE id=?', (json.dumps(doc), run_id))

    def test_returned_pending_removed_restore_idempotent_then_replay(self):
        run, args, ref = self.returned()
        before = sha(self.project.db); gates = copy.deepcopy(self.project.state()['gates'])
        admit_operation(self.project, 'restore_checkpoint', args)
        descriptor = returned_run_recovery(self.project, **args)
        self.assertEqual(sha(self.project.db), before)
        self.assertEqual(descriptor['checkpoint'], ref)
        self.assertEqual(next_run_step(self.project, run['run_id'])['reason'], 'RESTORE_ENTRY_CHECKPOINT_BEFORE_REPLAY')
        bpy, calls = self.fake_blender()
        with patch.dict(sys.modules, {'bpy': bpy}):
            restored = dispatch(str(self.root), 'restore_checkpoint', args)
            self.assertFalse(restored['already_restored'])
            boundary = sha(self.project.db)
            repeat = dispatch(str(self.root), 'restore_checkpoint', args)
            self.assertTrue(repeat['already_restored'])
            self.assertEqual(sha(self.project.db), boundary)
        self.assertEqual([kind for kind, _ in calls], ['open', 'save'])
        self.assertEqual(self.project.state()['gates'], gates)
        replay = next_run_step(self.project, run['run_id'])
        self.assertEqual(replay['status'], 'AWAITING_CONFIRMATION')
        self.assertNotEqual(replay['attempt_id'], args['attempt_id'])
        with self.assertRaisesRegex(StudioError, 'latest native attempt'):
            returned_run_recovery(self.project, **args)

    def test_historical_runtime_restores_but_cannot_replay_new_code(self):
        run, args, _ = self.returned()
        bpy, calls = self.fake_blender()
        with patch('a3d.runs._runtime', return_value='f'*64), \
                patch('a3d.runs._unit_runtime', return_value={'patched.py': 'a'*64}), \
                patch.dict(sys.modules, {'bpy': bpy}):
            self.assertEqual(dispatch(str(self.root), 'restore_checkpoint', args)['qualification'], 'NOT_GRANTED')
            with self.assertRaisesRegex(StudioError, 'code fingerprint changed'):
                next_run_step(self.project, run['run_id'])
        self.assertEqual(len(calls), 2)

    def test_legacy_session_archived_before_native_mutation_and_receipt_unchanged(self):
        run, args, ref = self.returned(legacy_session=True)
        receipt_ref = run_status(self.project, run['run_id'])['units'][0]['attempts'][-1]['receipt']
        receipt_bytes = (self.root/receipt_ref['path']).read_bytes()
        original_session = (self.project.data/'blender/session.json').read_bytes()
        bpy, calls = self.fake_blender()
        before = sha(self.project.db)
        descriptor = returned_run_recovery(self.project, **args)
        self.assertEqual(sha(self.project.db), before)
        self.assertFalse(any((self.project.data/'runs/native/projections').rglob('*')))
        with patch.dict(sys.modules, {'bpy': bpy}):
            restored = dispatch(str(self.root), 'restore_checkpoint', args)
            repeat = dispatch(str(self.root), 'restore_checkpoint', args)
        self.assertFalse(restored['already_restored'])
        self.assertTrue(repeat['already_restored'])
        self.assertEqual([kind for kind, _ in calls], ['open', 'save'])
        archived = next(row for row in descriptor['historical_project_projections']
                        if row['observed_ref']['path'] == '.a3d/blender/session.json')
        self.assertEqual((self.root/archived['archive_ref']['path']).read_bytes(), original_session)
        self.assertEqual((self.root/receipt_ref['path']).read_bytes(), receipt_bytes)
        # Historical recovery never converts an old live reference into current admission.
        from a3d.native_evidence import native_observation_origin
        with self.assertRaisesRegex(StudioError, 'reference changed'):
            native_observation_origin(self.project, lambda doc: True)

    def test_partial_restore_reconstructs_exact_legacy_session_then_reopens_entry(self):
        run, args, ref = self.returned(legacy_session=True)
        original_session = (self.project.data/'blender/session.json').read_bytes()
        bpy, calls = self.fake_blender()
        partial = self.project.data/'blender/working-recovered-cdef.blend'
        partial.write_bytes(b'partial saved boundary')
        session_path = self.project.data/'blender/session.json'
        session = json.loads(original_session)
        session['working'] = str(partial)
        atomic_json(session_path, session)
        bpy.data.filepath = str(partial)
        before = sha(self.project.db)
        descriptor = returned_run_recovery(self.project, **args)
        self.assertIsNone(descriptor['restored_event'])
        self.assertEqual(sha(self.project.db), before)
        with patch.dict(sys.modules, {'bpy': bpy}):
            restored = dispatch(str(self.root), 'restore_checkpoint', args)
        self.assertEqual(restored['checkpoint'], ref)
        self.assertEqual([kind for kind, _ in calls], ['open', 'save'])
        archived = next(row for row in descriptor['historical_project_projections']
                        if row['observed_ref']['path'] == '.a3d/blender/session.json')
        self.assertEqual((self.root/archived['archive_ref']['path']).read_bytes(), original_session)

    def test_historical_descriptor_checks_the_exact_receipt_bytes_it_decodes(self):
        run, args, _ = self.returned(legacy_session=True)
        receipt_ref = run_status(self.project, run['run_id'])['units'][0]['attempts'][-1]['receipt']
        path = self.root/receipt_ref['path']
        read_bytes = Path.read_bytes
        before = sha(self.project.db)

        def changed_bytes(selected):
            data = read_bytes(selected)
            return data+b' ' if selected == path else data

        with patch.object(Path, 'read_bytes', changed_bytes):
            with self.assertRaisesRegex(StudioError, 'before historical decoding'):
                returned_run_recovery(self.project, **args)
        self.assertEqual(sha(self.project.db), before)

    def test_receipt_changed_after_descriptor_is_refused_before_archive_and_open(self):
        run, args, _ = self.returned(legacy_session=True)
        receipt_ref = run_status(self.project, run['run_id'])['units'][0]['attempts'][-1]['receipt']
        path = self.root/receipt_ref['path']
        read_bytes = Path.read_bytes
        reads = 0
        bpy, calls = self.fake_blender()
        before = sha(self.project.db)

        def changed_second_read(selected):
            nonlocal reads
            data = read_bytes(selected)
            if selected == path:
                reads += 1
                if reads == 2:
                    return data+b' '
            return data

        with patch.object(Path, 'read_bytes', changed_second_read), patch.dict(sys.modules, {'bpy': bpy}):
            from blender.operations import restore_checkpoint
            with self.assertRaisesRegex(StudioError, 'before archival'):
                restore_checkpoint(str(self.root), **args)
        self.assertEqual(reads, 2)
        self.assertEqual(calls, [])
        self.assertFalse(any((self.project.data/'runs/native/projections').rglob('*')))
        self.assertEqual(sha(self.project.db), before)

    def test_completed_attempt_cannot_be_recovered(self):
        _, args, _ = self.returned('READY')
        with self.assertRaisesRegex(StudioError, 'refused or incomplete'):
            returned_run_recovery(self.project, **args)

    def test_incomplete_returned_budget_can_restore(self):
        _, args, _ = self.returned('READY', elapsed=11.)
        self.assertTrue(returned_run_recovery(self.project, **args)['restoration_only'])

    def test_changed_receipt_and_changed_checkpoint_refused(self):
        run, args, ref = self.returned()
        attempt = run_status(self.project, run['run_id'])['units'][0]['attempts'][-1]
        receipt = self.root/attempt['receipt']['path']; original = receipt.read_bytes()
        receipt.write_bytes(original+b' ')
        with self.assertRaises(StudioError): returned_run_recovery(self.project, **args)
        receipt.write_bytes(original)
        (self.root/ref['path']).write_bytes(b'foreign checkpoint')
        with self.assertRaises(StudioError): returned_run_recovery(self.project, **args)

    def test_forged_attempt_binding_refused(self):
        run, args, _ = self.returned()
        self.change_run(run['run_id'], lambda doc: doc['units'][0]['attempts'][-1].update(binding_sha256='a'*64))
        with self.assertRaisesRegex(StudioError, 'binding changed'):
            returned_run_recovery(self.project, **args)

    def test_missing_native_checkpoint_registration_refused(self):
        _, args, _ = self.returned()
        with self.project.transaction() as db:
            db.execute("DELETE FROM events WHERE kind='run_native_checkpoint'")
        with self.assertRaisesRegex(StudioError, 'canonical binding event'):
            returned_run_recovery(self.project, **args)

    def test_missing_result_registration_refused(self):
        _, args, _ = self.returned()
        with self.project.transaction() as db:
            db.execute("DELETE FROM events WHERE kind='run_native_registered'")
        with self.assertRaisesRegex(StudioError, 'result status'):
            returned_run_recovery(self.project, **args)

    def test_foreign_recovery_event_does_not_unlock_replay(self):
        run, args, ref = self.returned()
        binding = returned_run_recovery(self.project, **args)['run_binding']
        binding['attempt_id'] = 'attempt.foreign'
        with self.project.transaction() as db:
            self.project.save(db, self.project.state(db), 'blender_recovered', {
                'checkpoint': ref, 'run_binding': binding})
        self.assertEqual(next_run_step(self.project, run['run_id'])['reason'], 'RESTORE_ENTRY_CHECKPOINT_BEFORE_REPLAY')
        self.assertIsNone(returned_run_recovery(self.project, **args)['restored_event'])

    def test_another_pending_or_unresolved_unit_blocks_recovery(self):
        run, args, ref = self.returned()
        with self.project.transaction() as db:
            state = self.project.state(db); state['pending_blender_operation'] = {'checkpoint': ref}
            self.project.save(db, state, 'test_pending', {})
        with self.assertRaisesRegex(StudioError, 'pending Blender'):
            returned_run_recovery(self.project, **args)
        with self.project.transaction() as db:
            state = self.project.state(db); state.pop('pending_blender_operation')
            self.project.save(db, state, 'test_clear', {})
        self.change_run(run['run_id'], lambda doc: doc['units'].append({
            'id': 'other', 'status': 'WAITING_RESULT', 'attempts': [], 'executor': 'blender'}))
        with self.assertRaisesRegex(StudioError, 'unresolved run'):
            returned_run_recovery(self.project, **args)

    def test_exact_arguments_no_arbitrary_checkpoint_path(self):
        _, args, _ = self.returned()
        for wrong in ({'run_id': args['run_id']}, {**args, 'checkpoint_path': 'anything.blend'}):
            with self.assertRaisesRegex(StudioError, 'arguments'):
                admit_operation(self.project, 'restore_checkpoint', wrong)
        with self.assertRaisesRegex(StudioError, 'No interrupted operation'):
            admit_operation(self.project, 'restore_checkpoint', {})

    def test_current_scene_must_belong_to_project_and_restored_copy(self):
        _, args, _ = self.returned()
        bpy, calls = self.fake_blender()
        with patch.dict(sys.modules, {'bpy': bpy}):
            initial = bpy.data.filepath; bpy.data.filepath = str(self.root/'foreign.blend')
            with self.assertRaisesRegex(StudioError, 'working copy'):
                dispatch(str(self.root), 'restore_checkpoint', args)
            self.assertEqual(calls, [])
            bpy.data.filepath = initial
            result = dispatch(str(self.root), 'restore_checkpoint', args)
            Path(result['restored']).write_bytes(b'changed recovered scene')
            with self.assertRaisesRegex(StudioError, 'stale'):
                dispatch(str(self.root), 'restore_checkpoint', args)

    def test_idempotence_refuses_unsaved_changes_and_another_current_copy(self):
        _, args, _ = self.returned()
        bpy, _ = self.fake_blender()
        with patch.dict(sys.modules, {'bpy': bpy}):
            dispatch(str(self.root), 'restore_checkpoint', args)
            bpy.data.is_dirty = True
            with self.assertRaisesRegex(StudioError, 'unsaved changes'):
                dispatch(str(self.root), 'restore_checkpoint', args)
            bpy.data.is_dirty = False
            other = self.project.data/'blender/other.blend'; other.write_bytes(b'another scene')
            bpy.data.filepath = str(other)
            atomic_json(self.project.data/'blender/session.json', {'original': None, 'working': str(other)})
            with self.assertRaisesRegex(StudioError, 'no longer the current'):
                dispatch(str(self.root), 'restore_checkpoint', args)

    def test_existing_pending_restore_without_arguments_is_preserved(self):
        run = self.create(); next_run_step(self.project, run['run_id'])
        ref = self.native_entry()
        bpy, calls = self.fake_blender()
        admit_operation(self.project, 'restore_checkpoint', {})
        with patch.dict(sys.modules, {'bpy': bpy}):
            restored = dispatch(str(self.root), 'restore_checkpoint', {})
        self.assertEqual(restored['checkpoint'], ref)
        self.assertEqual(len(calls), 2)
        self.assertNotIn('pending_blender_operation', self.project.state())

    def test_changed_source_or_missing_creation_fingerprint_refused(self):
        _, args, _ = self.returned()
        original = self.path.read_bytes(); self.path.write_bytes(original+b' ')
        with self.assertRaisesRegex(StudioError, 'stale'):
            returned_run_recovery(self.project, **args)
        self.path.write_bytes(original)
        with self.project.transaction() as db:
            db.execute("DELETE FROM events WHERE kind='run_created'")
        with self.assertRaisesRegex(StudioError, 'creation fingerprint'):
            returned_run_recovery(self.project, **args)


if __name__ == '__main__': unittest.main()
