import copy
from a3d.core import StudioError,atomic_json,sha
from a3d.body_source import selection
from a3d.guard import admit_operation
from tests.test_core import Case
from tests.support import ready_project

class BodySourceTests(Case):
    def test_explicit_selection_identity_types_and_arguments(self):
        project=ready_project(self.root,True)
        source=project.root/'body.blend';source.write_bytes(b'owned body fixture')
        data={'version':1,'source_blend':'body.blend','source_sha256':sha(source),
            'source_ref':'explicit test body choice','frame':1,'unit_scale_m':1,
            'meshes':['body'],'dependencies':['rig'],'reference_object':'BODY_REFERENCE'}
        atomic_json(project.root/'selection.json',data);db=sha(project.db)
        for op in ('inspect_body_source','prepare_body_reference'):
            admit_operation(project,op,{'selection_path':'selection.json'})
        self.assertEqual(sha(project.db),db)
        for field,value in [('source_sha256','0'*64),('frame',True),('frame',-1),
            ('meshes',['body','body']),('dependencies',['body']),('unit_scale_m',0)]:
            bad=copy.deepcopy(data);bad[field]=value;atomic_json(project.root/'selection.json',bad)
            with self.subTest(field=field,value=value),self.assertRaises(StudioError):selection(project,'selection.json')
        atomic_json(project.root/'selection.json',data)
        with self.assertRaises(StudioError):admit_operation(project,'inspect_body_source',{'selection_path':'selection.json','include_all':True})

    def test_clean_recovery_native_identity_and_superseded_session(self):
        project=ready_project(self.root,True)
        root=project.data/'blender';root.mkdir(exist_ok=True)
        source=root/'working-old.blend';source.write_bytes(b'original fixture')
        witness=root/'witness-test.blend';witness.write_bytes(source.read_bytes())
        session={'working':str(source.resolve()),'original':None};archive=root/'session-test.json'
        atomic_json(archive,session);atomic_json(root/'session.json',session)
        rec={'source':str(source.resolve()),'source_sha256':sha(source),
            'witness':witness.relative_to(project.root).as_posix(),
            'previous_session':archive.relative_to(project.root).as_posix(),'previous_session_sha256':sha(archive),
            'candidate':'.a3d/blender/working-clean-test.blend','status':'ROLLBACK_REQUIRED'}
        path=root/'clean-recovery-test.json';atomic_json(path,rec)
        args={'recovery_path':path.relative_to(project.root).as_posix()}
        admit_operation(project,'recover_clean_construction',args)
        rec['status']='COMPLETED';atomic_json(path,rec)
        with self.assertRaisesRegex(StudioError,'does not require recovery'):admit_operation(project,'recover_clean_construction',args)
        rec['status']='ROLLBACK_REQUIRED';atomic_json(path,rec)
        atomic_json(root/'session.json',{'working':str(root/'newer.blend')})
        with self.assertRaisesRegex(StudioError,'supersedes'):admit_operation(project,'recover_clean_construction',args)
        atomic_json(root/'session.json',session);source.write_bytes(b'changed fixture')
        with self.assertRaisesRegex(StudioError,'source identity'):admit_operation(project,'recover_clean_construction',args)
