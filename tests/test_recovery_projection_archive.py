"""Portable historical identity tests; fake scenes are not native Blender proof."""
import copy
import json
import os
import tempfile
import unittest
from pathlib import Path
from types import SimpleNamespace
from unittest.mock import patch

from a3d.core import ROOT,StudioError,atomic_json,sha
from a3d.run_projection_archive import (RECOVERY_ROLE,archive_projection_references,
    archive_recovery_projections,is_project_projection,verify_projection_archives,
    verify_recovery_projections,_archive_io_path)
from a3d.runs import _reference
from a3d.native_evidence import checked_reference


class RecoveryProjectionArchives(unittest.TestCase):
    def setUp(self):
        directory=ROOT/'work/test-recovery-projections';directory.mkdir(parents=True,exist_ok=True)
        self.temp=tempfile.TemporaryDirectory(dir=directory);self.root=Path(self.temp.name).resolve()
        self.project=SimpleNamespace(root=self.root)
        self.working=self.root/'.a3d/blender/working-abcd.blend'
        self.working.parent.mkdir(parents=True);self.working.write_bytes(b'historical working scene')
        self.checkpoint=self.root/'.a3d/checkpoints/pre-abcd.blend'
        self.checkpoint.parent.mkdir(parents=True);self.checkpoint.write_bytes(b'entry checkpoint')
        self.session=self.root/'.a3d/blender/session.json'
        self.session_doc={'original':None,'working':str(self.working),'created_at':'historical',
                          'label':'épaules','construction_id':'abcd'}
        atomic_json(self.session,self.session_doc)
        self.db=self.root/'.a3d/state.sqlite3';self.db.write_bytes(b'untouched state witness')
        self.receipt={'attempt_id':'attempt.recovery','files':[
            self.reference(self.working),self.reference(self.session),self.reference(self.checkpoint)]}

    def tearDown(self):self.temp.cleanup()

    def reference(self,path):return {'path':path.relative_to(self.root).as_posix(),'sha256':sha(path)}

    def tree(self):return {p.relative_to(self.root).as_posix():p.read_bytes()
                          for p in self.root.rglob('*') if p.is_file()}

    def changed_session(self,**updates):
        recovered=self.root/'.a3d/blender/working-recovered-ef12.blend'
        recovered.write_bytes(b'restored working scene')
        atomic_json(self.session,{**self.session_doc,'working':str(recovered),**updates})
        return recovered

    def test_legacy_intact_read_only_identity_no_files_or_db_changes(self):
        before=self.tree();receipt=copy.deepcopy(self.receipt)
        rows=verify_recovery_projections(self.project,self.receipt)
        self.assertEqual(len(rows),2)
        self.assertTrue(all(row['role']==RECOVERY_ROLE and row['evidence_source']=='EXACT_LIVE'
                            for row in rows))
        self.assertEqual(self.tree(),before);self.assertEqual(self.receipt,receipt)
        self.assertFalse((self.root/'.a3d/runs').exists())

    def test_freeze_before_live_changes_preserves_receipt_and_sqlite(self):
        receipt=copy.deepcopy(self.receipt);db=sha(self.db)
        frozen=archive_recovery_projections(self.project,self.receipt)
        self.assertTrue(all(row['evidence_source']=='EXACT_ARCHIVE' for row in frozen))
        self.changed_session();self.working.write_bytes(b'changed working')
        self.assertEqual(verify_recovery_projections(self.project,self.receipt),frozen)
        self.assertEqual(self.receipt,receipt);self.assertEqual(sha(self.db),db)
        self.assertEqual(archive_recovery_projections(self.project,self.receipt),frozen)

    def test_exact_session_reconstruction_is_memory_only_until_freeze(self):
        self.changed_session();before=self.tree()
        rows=verify_recovery_projections(self.project,self.receipt)
        session=next(row for row in rows if row['observed_ref']['path'].endswith('session.json'))
        self.assertEqual(session['evidence_source'],'EXACT_SESSION_RECONSTRUCTION')
        self.assertEqual(self.tree(),before)
        archived=archive_recovery_projections(self.project,self.receipt)
        row=next(row for row in archived if row['observed_ref']==session['observed_ref'])
        expected=json.dumps(self.session_doc,ensure_ascii=False,indent=2,allow_nan=False).encode()+b'\n'
        self.assertEqual((self.root/row['archive_ref']['path']).read_bytes(),expected)
        self.assertEqual(self.session.read_bytes(),before['.a3d/blender/session.json'])

    def test_recovered_working_family_is_exact_and_eligible_for_unique_binding(self):
        recovered=self.root/'.a3d/blender/working-recovered-ef12.blend'
        recovered.write_bytes(b'historical recovered working')
        self.session_doc['working']=str(recovered);atomic_json(self.session,self.session_doc)
        self.receipt['files']=[self.reference(recovered),self.reference(self.session),self.reference(self.checkpoint)]
        atomic_json(self.session,{**self.session_doc,'working':str(self.working)})
        rows=verify_recovery_projections(self.project,self.receipt)
        self.assertEqual(len(rows),2)
        self.assertEqual(rows[0]['evidence_source'],'EXACT_SESSION_RECONSTRUCTION')

    def test_reconstruction_rejects_any_other_field_change(self):
        for change in ({'created_at':'new'},{'label':'another'},{'new_field':True}):
            with self.subTest(change=change):
                self.changed_session(**change)
                with self.assertRaises(StudioError):verify_recovery_projections(self.project,self.receipt)
        self.assertFalse((self.root/'.a3d/runs').exists())

    def test_reconstruction_requires_unique_real_working(self):
        self.changed_session()
        other=self.root/'.a3d/blender/working-cdef.blend';other.write_bytes(b'other working')
        for refs in (self.receipt['files'][1:],self.receipt['files']+[self.reference(other)]):
            with self.subTest(refs=refs),self.assertRaises(StudioError):
                verify_recovery_projections(self.project,{**self.receipt,'files':refs})
        self.working.unlink()
        with self.assertRaises(StudioError):verify_recovery_projections(self.project,self.receipt)

    def test_wrong_canonical_session_hash_is_refused(self):
        self.changed_session()
        self.receipt['files'][1]['sha256']='0'*64
        with self.assertRaises(StudioError):archive_recovery_projections(self.project,self.receipt)
        self.assertFalse((self.root/'.a3d/runs').exists())

    def test_strict_managed_session_refuses_bad_json_and_unmanaged_working(self):
        self.changed_session()
        valid=json.loads(self.session.read_text(encoding='utf-8'))
        invalid=[b'{"working":"x","working":"y"}',b'{"working":"x","a":NaN}',
                 b'{"working":"x","a":1e999}',b'[]',b'{}',b'\xef\xbb\xbf{}',b'\xff']
        invalid += [json.dumps({**valid,'working':value}).encode()
                    for value in ('working-abcd.blend',str(self.checkpoint),str(self.root.parent/'outside.blend'))]
        for content in invalid:
            with self.subTest(content=content):
                self.session.write_bytes(content)
                with self.assertRaises(StudioError):verify_recovery_projections(self.project,self.receipt)

    def test_immutable_checkpoint_and_unknown_file_cannot_be_reconstructed(self):
        self.changed_session()
        self.checkpoint.write_bytes(b'changed checkpoint')
        with self.assertRaises(StudioError):archive_recovery_projections(self.project,self.receipt)
        self.assertFalse((self.root/'.a3d/runs').exists())
        self.checkpoint.write_bytes(b'entry checkpoint')
        unknown=self.root/'asset.json';unknown.write_bytes(b'{}')
        self.receipt['files'].append(self.reference(unknown));unknown.unlink()
        with self.assertRaises(StudioError):verify_recovery_projections(self.project,self.receipt)

    def test_changed_working_without_archive_is_not_reconstructible(self):
        self.changed_session();self.working.write_bytes(b'other scene')
        with self.assertRaises(StudioError):verify_recovery_projections(self.project,self.receipt)

    def test_changed_archive_or_differing_orphan_preserved(self):
        rows=verify_recovery_projections(self.project,self.receipt)
        archive=self.root/rows[0]['archive_ref']['path']
        archive.parent.mkdir(parents=True);archive.write_bytes(b'differing orphan')
        before=self.tree()
        for function in (verify_recovery_projections,archive_recovery_projections):
            with self.assertRaises(StudioError):function(self.project,self.receipt)
            self.assertEqual(self.tree(),before)
        archive.unlink();rows=archive_recovery_projections(self.project,self.receipt)
        archive.write_bytes(b'tampered archive')
        with self.assertRaises(StudioError):verify_recovery_projections(self.project,self.receipt)
        self.assertEqual(archive.read_bytes(),b'tampered archive')

    def test_missing_session_must_have_real_archive(self):
        self.session.unlink()
        with self.assertRaises(StudioError):verify_recovery_projections(self.project,self.receipt)

    def test_archive_metadata_requires_exact_attempt_binding(self):
        rows=archive_recovery_projections(self.project,self.receipt)
        other={**self.receipt,'attempt_id':'attempt.other'}
        self.session.unlink()
        with self.assertRaises(StudioError):verify_recovery_projections(self.project,other)
        self.assertTrue(all((self.root/row['archive_ref']['path']).is_file() for row in rows))

    def test_duplicate_or_invalid_reference_refused(self):
        for files in (self.receipt['files']*2,[{'path':'.a3d/blender/session.json','sha256':'bad'}],
                      [{'path':'../escape','sha256':'0'*64}], [{'path':'.a3d/blender/session.json','sha256':'0'*64,'extra':1}]):
            with self.subTest(files=files),self.assertRaises(StudioError):
                verify_recovery_projections(self.project,{**self.receipt,'files':files})

    def test_unknown_names_remain_immutable_artifacts(self):
        names=['.a3d/blender/working-clean-abcd.blend','.a3d/blender/working-abcd.BLEND',
               '.a3d/blender/working-recovered-nohex.blend','.a3d/blender/session-abcd.json',
               '.a3d/blender/working-ABCD.blend','.a3d/blender/session.json.bak']
        for name in names:
            self.assertFalse(is_project_projection(name),name)
            file=self.root/name;file.write_bytes(b'immutable')
            ref=self.reference(file)
            self.assertEqual(verify_recovery_projections(self.project,{'attempt_id':'attempt.test','files':[ref]}),[])
            file.write_bytes(b'changed')
            with self.assertRaises(StudioError):
                verify_recovery_projections(self.project,{'attempt_id':'attempt.test','files':[ref]})

    def test_recovery_archives_are_not_generic_replay_receipt_aliases(self):
        rows=archive_recovery_projections(self.project,self.receipt)
        self.changed_session()
        forged={**self.receipt,'project_projections':rows}
        with self.assertRaises(StudioError):verify_projection_archives(self.project,forged)
        self.assertNotIn('project_projections',self.receipt)

    def test_existing_registered_archives_are_authenticated_but_no_legacy_rows_added(self):
        files,rows=archive_projection_references(self.project,self.receipt['attempt_id'],self.receipt['files'])
        receipt={**self.receipt,'files':files,'project_projections':rows}
        self.changed_session();self.working.write_bytes(b'changed')
        self.assertEqual(verify_recovery_projections(self.project,receipt),[])
        (self.root/rows[0]['archive_ref']['path']).write_bytes(b'tampered')
        with self.assertRaises(StudioError):verify_recovery_projections(self.project,receipt)


@unittest.skipUnless(os.name=='nt','Windows archive I/O contract')
class WindowsLongProjectionArchives(unittest.TestCase):
    """Simulate a Windows host without longPathAware; native Blender is separate."""

    def setUp(self):
        self.fixture=RecoveryProjectionArchives();self.fixture.setUp()
        self.root=self.fixture.root
        self.long_root=self.root/('nested-'+'x'*90)
        self.long_root.mkdir()
        self.long_project=SimpleNamespace(root=self.long_root)
        self.long_working=self.long_root/'.a3d/blender/working-recovered-0123456789abcdef0123456789abcdef.blend'
        self.long_working.parent.mkdir(parents=True)
        self.long_working.write_bytes(b'exact historical working')
        self.long_session=self.long_root/'.a3d/blender/session.json'
        atomic_json(self.long_session,{'working':str(self.long_working),'label':'épaules'})
        self.long_receipt={'attempt_id':'attempt.0123456789abcdef0123456789abcdef','files':[
            {'path':file.relative_to(self.long_root).as_posix(),'sha256':sha(file)}
            for file in (self.long_working,self.long_session)]}

    def tearDown(self):self.fixture.tearDown()

    def restricted_open(self,path,*args,**kwargs):
        if len(str(path))>=260 and not str(path).startswith('\\\\?\\'):
            raise FileNotFoundError('Simulated host MAX_PATH boundary: '+str(path))
        return self.real_open(path,*args,**kwargs)

    def test_native_archival_and_historical_readback_under_host_path_limit(self):
        receipt=copy.deepcopy(self.long_receipt)
        self.real_open=Path.open
        with patch.object(Path,'open',self.restricted_open_adapter()):
            files,rows=archive_projection_references(self.long_project,receipt['attempt_id'],receipt['files'])
            self.assertTrue(any(len(str(self.long_root/ref['path']))>=260 for ref in files))
            bound={**receipt,'files':files,'project_projections':rows}
            self.assertEqual([_reference(self.long_project,ref) for ref in files],files)
            self.assertEqual([checked_reference(self.long_project,ref) for ref in files],files)
            _archive_io_path(self.long_working).write_bytes(b'changed live working')
            self.assertEqual(len(verify_projection_archives(self.long_project,bound)),2)
            self.assertEqual(verify_recovery_projections(self.long_project,bound),[])
        self.assertEqual(self.long_receipt,receipt)
        self.assertTrue(all('\\' not in ref['path'] for ref in files))

    def restricted_open_adapter(self):
        owner=self
        def guarded(path,*args,**kwargs):return owner.restricted_open(path,*args,**kwargs)
        return guarded

    def test_legacy_freeze_is_idempotent_and_preserves_exact_relative_identity(self):
        receipt=copy.deepcopy(self.long_receipt)
        self.real_open=Path.open
        with patch.object(Path,'open',self.restricted_open_adapter()):
            expected=verify_recovery_projections(self.long_project,receipt)
            target=self.long_root/next(row['archive_ref']['path'] for row in expected
                                      if row['observed_ref']['path'].endswith('.blend'))
            self.assertGreaterEqual(len(str(target)),260)
            with self.assertRaises(FileNotFoundError):target.open('xb')
            rows=archive_recovery_projections(self.long_project,receipt)
            _archive_io_path(self.long_working).write_bytes(b'changed live working')
            self.assertEqual(archive_recovery_projections(self.long_project,receipt),rows)
        self.assertEqual(self.long_receipt,receipt)
        self.assertEqual([row['archive_ref'] for row in rows],[row['archive_ref'] for row in expected])

    def test_extended_drive_unc_and_prefixed_paths_do_not_change_identity(self):
        with patch.object(Path,'lstat',side_effect=FileNotFoundError):
            for source,expected in [('G:/project/archive.bin','\\\\?\\G:\\project\\archive.bin'),
                                    ('\\\\server\\share\\archive.bin','\\\\?\\UNC\\server\\share\\archive.bin'),
                                    ('\\\\?\\G:\\project\\archive.bin','\\\\?\\G:\\project\\archive.bin')]:
                self.assertEqual(str(_archive_io_path(Path(source))),expected)
            with self.assertRaises(StudioError):_archive_io_path(Path('relative.bin'))

    def test_long_archive_reparse_point_is_refused_before_io(self):
        target=self.long_root/('.a3d/runs/native/projections/'+'x'*100+'/archive.bin')
        real_lstat=Path.lstat
        def probe(path,*args,**kwargs):
            if str(path).startswith('\\\\?\\') and path.name=='x'*100:
                return SimpleNamespace(st_mode=0,st_file_attributes=0x400)
            return real_lstat(path,*args,**kwargs)
        with patch.object(Path,'lstat',probe),self.assertRaisesRegex(StudioError,'Symlink/junction'):
            _archive_io_path(target)

    def test_long_differing_archive_is_refused_and_preserved(self):
        self.real_open=Path.open
        with patch.object(Path,'open',self.restricted_open_adapter()):
            rows=archive_recovery_projections(self.long_project,self.long_receipt)
            ref=next(row['archive_ref'] for row in rows if row['archive_ref']['path'].endswith('.blend'))
            target=_archive_io_path(self.long_root/ref['path']);target.write_bytes(b'differing orphan')
            with self.assertRaises(StudioError):archive_recovery_projections(self.long_project,self.long_receipt)
            self.assertEqual(target.read_bytes(),b'differing orphan')

    def test_long_source_session_reconstruction_under_strict_resolution_limit(self):
        self.assertGreaterEqual(len(str(self.long_working)),260)
        original=self.long_session.read_bytes()
        recovered=self.long_working.with_name('working-recovered-fedcba9876543210fedcba9876543210.blend')
        _archive_io_path(recovered).write_bytes(b'new live working')
        changed=json.loads(original);changed['working']=str(recovered)
        atomic_json(self.long_session,changed)
        live_before=self.long_session.read_bytes()
        real_resolve=Path.resolve;self.real_open=Path.open
        def guarded_resolve(path,*args,**kwargs):
            strict=kwargs.get('strict',args[0] if args else False)
            if strict and len(str(path))>=260 and not str(path).startswith('\\\\?\\'):
                raise FileNotFoundError('Simulated strict host resolution limit')
            return real_resolve(path,*args,**kwargs)
        with patch.object(Path,'open',self.restricted_open_adapter()),patch.object(Path,'resolve',guarded_resolve):
            rows=verify_recovery_projections(self.long_project,self.long_receipt)
            self.assertIn('EXACT_SESSION_RECONSTRUCTION',[row['evidence_source'] for row in rows])
            frozen=archive_recovery_projections(self.long_project,self.long_receipt)
            for row in frozen:
                self.assertEqual(_reference(self.long_project,row['archive_ref']),row['archive_ref'])
                self.assertEqual(checked_reference(self.long_project,row['archive_ref']),row['archive_ref'])
        self.assertEqual(self.long_session.read_bytes(),live_before)
        session_row=next(row for row in frozen if row['observed_ref']['path'].endswith('session.json'))
        self.assertEqual(_archive_io_path(self.long_root/session_row['archive_ref']['path']).read_bytes(),original)


if __name__=='__main__':unittest.main()
