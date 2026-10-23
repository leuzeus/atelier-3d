"""Source changes affect resumability, not historical receipt qualification."""
import copy
import unittest
from unittest.mock import patch

from a3d.core import StudioError
from a3d.runs import create_run, next_run_step, run_status, invalidate_source_runs, _verify_source_epoch
import tests.test_runs as fixtures


class RunSourceEpochs(unittest.TestCase):
    def setUp(self):
        fixtures.Runs.setUp(self)

    def tearDown(self):
        fixtures.Runs.tearDown(self)

    def activate(self, epoch):
        with self.project.transaction() as db:
            state = self.project.state(db)
            state['source_epoch'] = epoch
            self.project.save(db, state, 'synthetic_epoch', {'epoch': epoch})

    def test_current_source_epoch_is_bound_and_old_key_cannot_reuse_new_epoch(self):
        self.activate('a'*64)
        run = create_run(self.project, 'garment', 'run.json')
        self.assertEqual(run['source_epoch'], 'a'*64)
        self.assertEqual(create_run(self.project, 'garment', 'run.json')['run_id'], run['run_id'])
        self.activate('b'*64)
        with self.assertRaisesRegex(StudioError, 'different specification'):
            create_run(self.project, 'garment', 'run.json')
        self.assertEqual(run_status(self.project, run['run_id'])['run_id'], run['run_id'])

    def test_old_epoch_is_refused_before_receipt_reconciliation_or_native_preparation(self):
        run = create_run(self.project, 'garment', 'run.json')
        self.activate('b'*64)
        before = copy.deepcopy(run_status(self.project, run['run_id']))
        with patch('a3d.runs.reconcile_native_run_result', side_effect=AssertionError('No replay')), \
             patch('a3d.runs._ready_event', side_effect=AssertionError('No receipt reuse')):
            with self.assertRaisesRegex(StudioError, 'source epoch changed'):
                next_run_step(self.project, run['run_id'])
        self.assertEqual(before, run_status(self.project, run['run_id']))

    def test_dependency_invalidation_rolls_back_with_adoption_transaction(self):
        run = create_run(self.project, 'garment', 'run.json')
        before = copy.deepcopy(run_status(self.project, run['run_id']))
        with self.assertRaises(RuntimeError):
            with self.project.transaction() as db:
                invalidate_source_runs(self.project, db, [run['run_id']], 'a'*64, 'b'*64, 'revision.test')
                raise RuntimeError('Synthetic interrupted adoption')
        self.assertEqual(before, run_status(self.project, run['run_id']))

    def test_independent_comfy_and_coupon_runs_do_not_inherit_garment_epoch(self):
        for kind in ('comfy', 'material_bench'):
            with self.subTest(kind=kind):
                _verify_source_epoch(self.project, {'kind': kind}, {'source_epoch': 'b'*64})

    def test_explicit_source_dependency_blocks_other_kinds_without_erasing_history(self):
        run = create_run(self.project, 'garment', 'run.json')
        with self.project.transaction() as db:
            invalidate_source_runs(self.project, db, [run['run_id'], run['run_id']], 'a'*64, 'b'*64, 'revision.test')
        from a3d.runs import _load
        with self.project.transaction() as db:
            updated = _load(db, run['run_id'])
        self.assertEqual(updated['units'], run['units'])
        self.assertEqual(updated['status'], run['status'])
        self.assertEqual(updated['revision'], run['revision']+1)
        with self.assertRaisesRegex(StudioError, 'adopted source revision'):
            _verify_source_epoch(self.project, dict(updated, kind='comfy'))
