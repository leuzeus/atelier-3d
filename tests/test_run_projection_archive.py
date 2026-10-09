import copy
import tempfile
import unittest
from pathlib import Path

from a3d.core import ROOT,StudioError,sha
from a3d.run_projection_archive import archive_projection_references,verify_projection_archives
from a3d.store import Project
from tests.support import asset


class ProjectionArchives(unittest.TestCase):
    def setUp(self):
        directory=ROOT/'work/test-run-projections';directory.mkdir(parents=True,exist_ok=True)
        self.temp=tempfile.TemporaryDirectory(dir=directory);self.root=Path(self.temp.name)
        self.project=Project.create(self.root,asset())
        self.live=self.project.data/'blender/working-abcd.blend';self.live.parent.mkdir(exist_ok=True)
        self.live.write_bytes(b'exact historical scene')
        self.observed={'path':'.a3d/blender/working-abcd.blend','sha256':sha(self.live)}
        self.files,self.rows=archive_projection_references(self.project,'attempt.test',[self.observed])
        self.receipt={'attempt_id':'attempt.test','files':self.files,'project_projections':self.rows}

    def tearDown(self):self.temp.cleanup()

    def test_live_changes_and_removal_leave_exact_archive_and_trace(self):
        self.live.write_bytes(b'next scene')
        row=verify_projection_archives(self.project,self.receipt)[0]
        self.assertEqual(row['current_projection_status'],'CHANGED')
        self.live.unlink()
        row=verify_projection_archives(self.project,self.receipt)[0]
        self.assertEqual(row['current_projection_status'],'ABSENT')
        self.assertEqual((self.root/self.files[0]['path']).read_bytes(),b'exact historical scene')

    def test_unknown_files_stay_artifacts_and_wrong_aliases_are_refused(self):
        unknown=self.root/'mesh.json';unknown.write_text('{}')
        ref={'path':'mesh.json','sha256':sha(unknown)}
        self.assertEqual(archive_projection_references(self.project,'attempt.test',[ref]),([ref],[]))
        for kind in ('artifact-alias','other-attempt','missing-binding','changed-sha','duplicate'):
            receipt=copy.deepcopy(self.receipt)
            if kind=='artifact-alias':receipt['project_projections'][0]['observed_ref']=ref
            elif kind=='other-attempt':receipt['attempt_id']='attempt.other'
            elif kind=='missing-binding':receipt['files']=[]
            elif kind=='changed-sha':receipt['project_projections'][0]['archive_ref']['sha256']='0'*64
            else:receipt['project_projections']*=2
            with self.subTest(kind=kind),self.assertRaises(StudioError):
                verify_projection_archives(self.project,receipt)

    def test_modified_archive_and_orphan_are_refused_without_overwrite(self):
        target=self.root/self.files[0]['path'];target.write_bytes(b'changed archive')
        with self.assertRaises(StudioError):verify_projection_archives(self.project,self.receipt)
        with self.assertRaises(StudioError):
            archive_projection_references(self.project,'attempt.test',[self.observed])
        self.assertEqual(target.read_bytes(),b'changed archive')
