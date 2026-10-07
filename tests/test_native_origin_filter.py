"""Canonical operation selection never substitutes receipt authentication."""
import copy
import json
import sqlite3
import tempfile
import unittest
from contextlib import closing
from pathlib import Path
from unittest.mock import patch

from a3d.core import ROOT, StudioError, atomic_json, read_json, sha
from a3d.native_evidence import native_origin
from tests.test_body_source_paths import native_project


class NativeOperationSelection(unittest.TestCase):
    def setUp(self):
        base = ROOT/'work'/'test-runs'; base.mkdir(parents=True, exist_ok=True)
        self.temporary = tempfile.TemporaryDirectory(dir=base)
        self.root = Path(self.temporary.name)
        self.project, _ = native_project(self.root)

    def tearDown(self):
        self.temporary.cleanup()

    def add_foreign(self):
        atomic_json(self.root/'foreign.json', {'operation': 'prepare_pattern_assembly', 'result': {}})
        ref = {'path': 'foreign.json', 'sha256': sha(self.root/'foreign.json')}
        event = {'run_id': 'run.foreign', 'unit_id': 'foreign', 'attempt_id': 'attempt.foreign',
                 'receipt': ref, 'binding_sha256': 'f'*64}
        run = {'units': [{'id': 'foreign', 'status': 'COMPLETED', 'attempts': [
            {'id': 'attempt.foreign', 'operation': 'prepare_pattern_assembly'}]}]}
        with closing(sqlite3.connect(self.project.db)) as database, database:
            database.execute('INSERT INTO events VALUES(2,?,?)', ('run_native_receipt', json.dumps(event)))
            database.execute('INSERT INTO runs VALUES(?,?)', ('run.foreign', json.dumps(run)))

    def predicate(self, receipt):
        return receipt.get('operation') == 'prepare_body_target'

    def test_foreign_receipt_is_not_read_when_canonical_operation_is_filtered(self):
        self.add_foreign()
        before = self.project.db.read_bytes()
        def checked_read(path):
            if path.name == 'foreign.json':
                raise AssertionError('Foreign artifact read before canonical selection')
            return read_json(path)
        with patch('a3d.native_evidence.read_json', side_effect=checked_read):
            receipt, origin = native_origin(self.project, self.predicate,
                                            operation_filter=('prepare_body_target', 'introduce_body_target'))
        self.assertEqual(receipt['operation'], 'prepare_body_target')
        self.assertEqual(origin['event_id'], 1)
        self.assertEqual(before, self.project.db.read_bytes())
        unfiltered_receipt, unfiltered_origin = native_origin(self.project, self.predicate)
        self.assertEqual(receipt, unfiltered_receipt)
        self.assertEqual(origin, unfiltered_origin)

    def test_default_search_still_reads_foreign_receipts(self):
        self.add_foreign(); seen = []
        def capture(path):
            seen.append(path.name); return read_json(path)
        with patch('a3d.native_evidence.read_json', side_effect=capture):
            receipt, origin = native_origin(self.project, self.predicate)
        self.assertIn('foreign.json', seen)
        self.assertEqual(origin['event_id'], 1)

    def test_selected_failed_attempt_and_changed_binding_remain_refused(self):
        with closing(sqlite3.connect(self.project.db)) as database:
            original = json.loads(database.execute('SELECT doc FROM runs WHERE id=?', ('run.body',)).fetchone()[0])
        for mode in ('failed', 'binding'):
            run = copy.deepcopy(original)
            if mode == 'failed':
                run['units'][0]['attempts'][0]['status'] = 'FAILED'
            else:
                run['units'][0]['attempts'][0]['binding_sha256'] = 'f'*64
            with closing(sqlite3.connect(self.project.db)) as database, database:
                database.execute('UPDATE runs SET doc=? WHERE id=?', (json.dumps(run), 'run.body'))
            with self.subTest(mode=mode), self.assertRaises(StudioError):
                native_origin(self.project, self.predicate, operation_filter=('prepare_body_target',))

    def test_selected_receipt_operation_mismatch_and_source_file_mutation_are_refused(self):
        native = read_json(self.root/'native.json')
        native['operation'] = 'introduce_body_target'
        atomic_json(self.root/'native.json', native)
        ref = {'path': 'native.json', 'sha256': sha(self.root/'native.json')}
        with closing(sqlite3.connect(self.project.db)) as database, database:
            event = json.loads(database.execute('SELECT doc FROM events WHERE id=1').fetchone()[0])
            run = json.loads(database.execute('SELECT doc FROM runs WHERE id=?', ('run.body',)).fetchone()[0])
            event['receipt'] = ref; run['units'][0]['attempts'][0]['receipt'] = ref
            database.execute('UPDATE events SET doc=? WHERE id=1', (json.dumps(event),))
            database.execute('UPDATE runs SET doc=? WHERE id=?', (json.dumps(run), 'run.body'))
        with self.assertRaises(StudioError):
            native_origin(self.project, lambda receipt: True, operation_filter=('prepare_body_target',))
        native['operation'] = 'prepare_body_target'; atomic_json(self.root/'native.json', native)
        ref['sha256'] = sha(self.root/'native.json')
        with closing(sqlite3.connect(self.project.db)) as database, database:
            event['receipt'] = ref; run['units'][0]['attempts'][0]['receipt'] = ref
            database.execute('UPDATE events SET doc=? WHERE id=1', (json.dumps(event),))
            database.execute('UPDATE runs SET doc=? WHERE id=?', (json.dumps(run), 'run.body'))
        (self.root/'geometry.json').write_text('{}', encoding='utf-8')
        with self.assertRaises(StudioError):
            native_origin(self.project, self.predicate, operation_filter=('prepare_body_target',))

    def test_empty_invalid_or_unmatched_selection_grants_no_origin(self):
        for value in ((), 'prepare_body_target', (None,), ('x'*201,), ('unknown_operation',)):
            with self.subTest(value=value), self.assertRaises(StudioError):
                native_origin(self.project, self.predicate, operation_filter=value)
