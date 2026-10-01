import copy
import json
import subprocess
import sys
from types import SimpleNamespace
from unittest.mock import patch

from a3d.core import ROOT, StudioError, atomic_json, sha
from a3d.guard import admit_operation, code_for, parse_code
from a3d.packages import extract_package
from a3d.store import Project
from blender.legacy import checkpoint_import_proof, legacy_topology, validate_legacy_panels
from tests.support import asset, garment_source, ready_project
from tests.test_core import Case


class BootstrapTests(Case):
    def test_stale_packages_and_submodules_are_replaced_before_admission(self):
        project = Project.create(self.root / 'project', asset())
        code = code_for(str(project.root), 'unknown-operation', {})
        script = '''
import json,sys,types
from pathlib import Path
root=Path(sys.argv[1]).resolve()
for name in ('a3d','a3d.core','a3d.guard','a3d.sewing','blender','blender.operations','blender.sewing'):
    module=types.ModuleType(name);module.__file__='/obsolete-0.4/'+name+'.py'
    module.__path__=['/obsolete-0.4'];module.stale=True;sys.modules[name]=module
sentinel=types.ModuleType('another_plugin');sys.modules['another_plugin']=sentinel
try:exec(sys.stdin.read(),{})
except Exception as error:
    assert type(error).__name__=='StudioError' and 'Unknown guarded' in str(error),repr(error)
else:raise AssertionError('Admission was bypassed')
assert sys.modules['another_plugin'] is sentinel
for name,module in list(sys.modules.items()):
    if name in ('a3d','blender') or name.startswith(('a3d.','blender.')):
        assert not getattr(module,'stale',False),name
        assert Path(module.__file__).resolve().is_relative_to(root),name
assert sys.modules['blender'].__path__==[str(root/'blender')]
print('PASS')
'''
        run = subprocess.run([sys.executable, '-B', '-c', script, str(ROOT)], input=code,
                             text=True, capture_output=True, timeout=15)
        self.assertEqual(run.returncode, 0, run.stderr)
        self.assertEqual(run.stdout.strip(), 'PASS')

    def test_trampoline_loader_and_payload_cannot_be_rewritten(self):
        code = code_for(str(self.root), 'resume', {})
        self.assertEqual(parse_code(code)['operation'], 'resume')
        for changed in (code.replace('bootstrap.py', 'operations.py'), code.replace("['dispatch_current']", "['dispatch']"),
                        code + 'print("extra")\n'):
            with self.subTest(code=changed), self.assertRaises(StudioError):
                parse_code(changed)


class ResumeAdmissionTests(Case):
    def test_resume_needs_no_new_board_but_cannot_bypass_pending_or_complete(self):
        project = Project.create(self.root, asset())
        before = project.state()
        admit_operation(project, 'resume', {})
        self.assertEqual(before, project.state())
        with self.assertRaises(StudioError):
            admit_operation(project, 'resume', {'force': True})
        with project.transaction() as db:
            state = project.state(db); state['pending_blender_operation'] = {'status': 'failed'}
            project.save(db, state, 'synthetic_failure', {})
        with self.assertRaisesRegex(StudioError, 'restore_checkpoint'):
            admit_operation(project, 'resume', {})
        with project.transaction() as db:
            state = project.state(db); state.pop('pending_blender_operation'); state['stage'] = 'COMPLETE'
            project.save(db, state, 'synthetic_complete', {})
        with self.assertRaisesRegex(StudioError, 'immutable'):
            admit_operation(project, 'resume', {})


class LegacyMigrationTests(Case):
    def setUp(self):
        super().setUp()
        self.project = Project.create(self.root, asset(True))
        self.data = garment_source(self.project.data / 'source/package')
        count, faces, edges, seam_count = legacy_topology(self.data)
        class MeshObject(dict):
            type = 'MESH'
            name = 'A3D.garment.coat'
        self.obj = MeshObject(a3d_component_id='garment.coat', a3d_package_sha256='a' * 64)
        self.obj.data = SimpleNamespace(vertices=list(range(count)), polygons=[SimpleNamespace(vertices=f) for f in faces],
                                        edges=[SimpleNamespace(vertices=e) for e in sorted(edges)])
        self.checkpoint = self.project.data / 'checkpoints/legacy.blend'
        self.checkpoint.write_bytes(b'synthetic checkpoint')
        self.receipt = {'object': self.obj.name, 'vertices': count, 'sewing_edges': seam_count,
                        'checkpoint': {'path': '.a3d/checkpoints/legacy.blend', 'sha256': sha(self.checkpoint)}}
        atomic_json(self.project.data / 'blender/garment-receipt.json', self.receipt)
        with self.project.transaction() as db:
            state = self.project.state(db)
            self.project.save(db, state, 'blender_started', {'operation':'garment',
                                                           'checkpoint':self.receipt['checkpoint']})

    def validate(self):
        return validate_legacy_panels(self.project, self.obj, self.data, 'a' * 64)

    def test_matching_legacy_is_recognized_without_promoting_or_mutating_it(self):
        before = dict(self.obj)
        self.validate()
        self.assertEqual(dict(self.obj), before)
        self.assertNotIn('a3d_sewing_mesh', self.obj)

    def test_foreign_identity_or_versioned_mesh_is_not_legacy(self):
        for key, value in (('a3d_component_id', 'other'), ('a3d_package_sha256', 'b' * 64),
                           ('a3d_role', 'render'), ('a3d_sewing_mesh', 'fake.json')):
            original = dict(self.obj)
            with self.subTest(key=key), self.assertRaisesRegex(StudioError, 'identity'):
                self.obj[key] = value; self.validate()
            self.obj.clear(); self.obj.update(original)

    def test_unrelated_topology_is_refused_even_with_matching_tags(self):
        self.obj.data.edges.pop()
        with self.assertRaisesRegex(StudioError, 'topology'):
            self.validate()

    def test_receipt_and_checkpoint_must_match(self):
        changed = copy.deepcopy(self.receipt); changed['object'] = 'AnotherMesh'
        atomic_json(self.project.data / 'blender/garment-receipt.json', changed)
        with self.assertRaisesRegex(StudioError, 'receipt'):
            self.validate()
        atomic_json(self.project.data / 'blender/garment-receipt.json', self.receipt)
        self.checkpoint.write_bytes(b'changed')
        with self.assertRaisesRegex(StudioError, 'checkpoint'):
            self.validate()

    def modified_history(self):
        self.obj.data.edges.pop()
        script = self.project.root / 'old-script.py'
        script.write_text('# synthetic historical operation\n', encoding='utf-8')
        receipt = {**self.receipt, 'operation': 'simulate', 'component_ids': ['garment.coat'],
                   'script': 'old-script.py', 'sha256': sha(script)}
        path = self.project.data / 'blender/script-old.json'
        atomic_json(path, receipt)
        return script, path, receipt

    def test_modified_archive_requires_current_snapshot_and_verified_history(self):
        script, path, receipt = self.modified_history()
        paths = [path.relative_to(self.project.root).as_posix()]
        with patch('blender.legacy.legacy_snapshot', return_value='c' * 64):
            proof = validate_legacy_panels(self.project, self.obj, self.data, 'a' * 64, 'c' * 64, paths)
            self.assertFalse(proof['source_topology_matches'])
            self.assertEqual(proof['legacy_validity'], 'NOT_VALIDATED')
            self.assertNotIn('a3d_role', self.obj)
            self.assertEqual(proof['import_receipt'], self.receipt)
            with self.assertRaisesRegex(StudioError, 'changed since inspect'):
                validate_legacy_panels(self.project, self.obj, self.data, 'a' * 64, 'd' * 64, paths)
            script.write_text('# changed', encoding='utf-8')
            with self.assertRaisesRegex(StudioError, 'receipt or source'):
                validate_legacy_panels(self.project, self.obj, self.data, 'a' * 64, 'c' * 64, paths)

    def test_modified_archive_refuses_foreign_or_missing_history(self):
        _, path, receipt = self.modified_history()
        paths = [path.relative_to(self.project.root).as_posix()]
        with patch('blender.legacy.legacy_snapshot', return_value='c' * 64):
            for records in (None, [], ['../foreign.json']):
                with self.subTest(records=records), self.assertRaises(StudioError):
                    validate_legacy_panels(self.project, self.obj, self.data, 'a' * 64, 'c' * 64, records)
            receipt['component_ids'] = ['other']; atomic_json(path, receipt)
            with self.assertRaisesRegex(StudioError, 'foreign'):
                validate_legacy_panels(self.project, self.obj, self.data, 'a' * 64, 'c' * 64, paths)

    def test_overwritten_receipt_recovers_observed_checkpoint_evidence_without_relabeling_it(self):
        receipt = {**self.receipt, 'object': 'A3D.garment.belt', 'vertices': 944, 'sewing_edges': 462}
        path = self.project.data / 'blender/garment-receipt.json'
        atomic_json(path, receipt); original = path.read_bytes()
        observed = {'object': self.obj.name, 'component_id': 'garment.coat', 'package_sha256': 'a' * 64}
        with patch('blender.legacy.read_checkpoint_object', return_value=observed) as native:
            proof = validate_legacy_panels(self.project, self.obj, self.data, 'a' * 64,
                                           checkpoint_receipt='.a3d/blender/garment-receipt.json')
            self.assertIsNone(proof['import_receipt'])
            self.assertEqual(proof['checkpoint_import_proof']['observed'], observed)
            self.assertEqual(proof['checkpoint_import_proof']['kind'], 'guarded-checkpoint-object')
            native.assert_called_once_with(self.checkpoint, self.obj.name, self.data, 'a' * 64)
        self.assertEqual(path.read_bytes(), original)
        self.assertNotIn('a3d_role', self.obj)

    def test_recovery_refuses_missing_changed_or_unguarded_checkpoint_before_loading(self):
        with patch('blender.legacy.read_checkpoint_object') as native:
            for path in ('.a3d/blender/missing.json', '../outside.json'):
                with self.subTest(path=path), self.assertRaises(StudioError):
                    checkpoint_import_proof(self.project, self.obj.name, self.data, 'a' * 64, path)
            self.checkpoint.write_bytes(b'changed')
            with self.assertRaisesRegex(StudioError, 'checkpoint'):
                checkpoint_import_proof(self.project, self.obj.name, self.data, 'a' * 64,
                                        '.a3d/blender/garment-receipt.json')
            native.assert_not_called()

    def test_checkpoint_file_with_matching_hash_without_guarded_journal_entry_is_refused(self):
        with self.project.transaction() as db:
            db.execute("DELETE FROM events WHERE kind='blender_started'")
        with patch('blender.legacy.read_checkpoint_object') as native, self.assertRaisesRegex(StudioError, 'journal'):
            checkpoint_import_proof(self.project, self.obj.name, self.data, 'a' * 64,
                                    '.a3d/blender/garment-receipt.json')
        native.assert_not_called()

    def test_migration_requires_explicit_rebuild_and_keeps_board_gates(self):
        project = ready_project(self.root / 'approved', True)
        recipe = json.loads((ROOT / 'templates/sewing-recipe.json').read_text(encoding='utf-8'))
        atomic_json(project.root / 'recipe.json', recipe)
        component = project.state()['components']['garment.coat']
        extract_package(project.root / component['package']['path'], project.root / 'extracted')
        args = {'package_dir': 'extracted', 'recipe_path': 'recipe.json', 'migrate_legacy': True}
        with self.assertRaisesRegex(StudioError, 'explicit rebuild'):
            admit_operation(project, 'garment', args)
        before = project.state()
        admit_operation(project, 'garment', {**args, 'rebuild': True})
        self.assertEqual(project.state(), before)
        for value in (1, 'true'):
            with self.assertRaisesRegex(StudioError, 'boolean'):
                admit_operation(project, 'garment', {**args, 'rebuild': True, 'migrate_legacy': value})
        extras = {'legacy_snapshot_sha256': 'c' * 64, 'legacy_script_receipts': ['.a3d/blender/script-old.json']}
        admit_operation(project, 'garment', {**args, 'rebuild': True, **extras})
        for invalid in ({'legacy_snapshot_sha256': 'bad'}, {'legacy_script_receipts': []},
                        {'legacy_script_receipts': 'script.json'}, {'migrate_legacy': False}):
            with self.subTest(invalid=invalid), self.assertRaises(StudioError):
                admit_operation(project, 'garment', {**args, 'rebuild': True, **extras, **invalid})
        receipt_path = project.data / 'blender/garment-receipt.json'
        atomic_json(receipt_path, self.receipt)
        before = project.state()
        admit_operation(project, 'verify_legacy_import', {'package_dir':'extracted',
                                                         'checkpoint_receipt':'.a3d/blender/garment-receipt.json'})
        self.assertEqual(project.state(), before)
        admit_operation(project, 'garment', {**args, 'rebuild': True,
            'legacy_checkpoint_receipt': '.a3d/blender/garment-receipt.json'})
        with self.assertRaises(StudioError):
            admit_operation(project, 'garment', {**args, 'rebuild': True,
                'migrate_legacy':False, 'legacy_checkpoint_receipt':'.a3d/blender/garment-receipt.json'})
