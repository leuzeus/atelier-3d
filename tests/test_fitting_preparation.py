import copy
from a3d.core import atomic_json,sha,StudioError,contract
from a3d.fitting_preparation import envelope_spec,pose_spec
from a3d.guard import admit_operation
from tests.test_core import Case
from tests.support import ready_project

class PreparationTests(Case):
    def setup_receipt(self):
        project=ready_project(self.root,True);artifact=self.root/'body.blend';artifact.write_bytes(b'owned unit fixture')
        body={'artifact':{'path':'body.blend','sha256':sha(artifact)},'geometry_sha256':'a'*64,
            'meshes':[{'object':'body','vertex_offset':0,'vertices':4}],'bones':{'rig':{'arm':{}}},
            'reference_object':'target','source_sha256':'b'*64,'frame':1}
        atomic_json(self.root/'body.json',body)
        spec={'version':1,'body_receipt':{'path':'body.json','sha256':sha(self.root/'body.json')},
            'object':'envelope','source_ref':'explicit auxiliary hypothesis','regions':[{'id':'body','source_meshes':['body'],'partition_bones':[]}],
            'voxel_cm':.5,'padding_cm':1,'max_body_outside_cm':.1,'thickness_outer_cm':.3,'thickness_inner_cm':.1}
        return project,spec

    def test_envelope_source_identity_partition_and_admission(self):
        project,spec=self.setup_receipt();atomic_json(self.root/'envelope.json',spec);db=sha(project.db)
        envelope_spec(project,'envelope.json');admit_operation(project,'prepare_fitting_envelope',{'envelope_path':'envelope.json'})
        self.assertEqual(db,sha(project.db))
        for mode in ('stale','missing','duplicate','target','bone'):
            s=copy.deepcopy(spec)
            if mode=='stale':s['body_receipt']['sha256']='0'*64
            if mode=='missing':s['regions'][0]['source_meshes']=['invented']
            if mode=='duplicate':s['regions'].append(s['regions'][0])
            if mode=='target':s['object']='target'
            if mode=='bone':s['regions'][0]['partition_bones']=[{'rig':'rig','bone':'invented'}]
            atomic_json(self.root/'envelope.json',s)
            with self.subTest(mode=mode),self.assertRaises(StudioError):envelope_spec(project,'envelope.json')
        atomic_json(self.root/'envelope.json',spec);(self.root/'body.blend').write_bytes(b'changed')
        with self.assertRaisesRegex(StudioError,'artifact changed'):envelope_spec(project,'envelope.json')

    def test_pose_requires_actual_receipt_bones_and_guarded_arguments(self):
        project,spec=self.setup_receipt();edge={'piece':'front','edge':'top'}
        frame={'id':'arm','source_ref':'measured correspondence','moving_pieces':['front'],'origin_edges':[edge],
            'axis_edges':[edge],'transverse_edges':[edge],'target_origin':{'rig':'rig','bone':'arm','endpoint':'head_cm'},
            'target_axis':{'rig':'rig','bone':'arm','endpoint':'tail_cm'},'target_transverse_cm':[0,1,0],
            'feather_cm':10,'max_axis_length_difference_cm':1}
        pose={'version':1,'component_id':'garment.coat','body_receipt':spec['body_receipt'],'max_displacement_cm':1,'steps':4,'frames':[frame]}
        atomic_json(self.root/'pose.json',pose);pose_spec(project,'pose.json')
        pose['frames'][0]['target_axis']['bone']='invented';atomic_json(self.root/'pose.json',pose)
        with self.assertRaisesRegex(StudioError,'evaluated target bones'):pose_spec(project,'pose.json')
        with self.assertRaisesRegex(StudioError,'Unexpected/missing'):admit_operation(project,'prepare_fitting_pose',{'pose_path':'pose.json'})

    def test_reject_unbounded_voxel_padding_or_transition(self):
        project,spec=self.setup_receipt()
        for key,value in [('voxel_cm',0),('padding_cm',50),('max_body_outside_cm',10)]:
            s={**spec,key:value}
            with self.assertRaises(StudioError):contract('fitting-envelope',s)
