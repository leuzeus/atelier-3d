import copy
import math
from unittest.mock import patch

from a3d.core import StudioError, atomic_json, digest, sha
from a3d.rigid_attachment import (attachment_frames, bind_selectors, canonical_calibrated_part,
                                 selector_uv, source_axes)
from tests.test_core import Case
from tests.support import ready_project


def candidate():
    uv=[[0.,0.],[4.,0.],[4.,4.],[0.,4.]];faces=[[0,1,2],[0,2,3]]
    return {'rest_mode':'assembled_3d','rest_cm':[[u,v,0.] for u,v in uv],
            'placed_cm':[[u,v,0.] for u,v in uv],'faces':faces,'panels':{'belt':{'indices':[0,1,2,3]}},
            'source_rest_triangles_cm':[[uv[i] for i in face] for face in faces],
            'source_face_pieces':['belt','belt'],'source_face_vertex_ids':copy.deepcopy(faces),'source_vertex_map':{}}


def mapping():
    return {'piece_id':'belt','origin':{'kind':'UV','uv_cm':[2.,2.]},
            'right':{'kind':'UV','uv_cm':[3.,2.]},'up':{'kind':'UV','uv_cm':[2.,3.]}}


def piece():
    return {'vertices':[[0.,0.],[4.,0.],[4.,4.],[0.,4.]],'edges':{'bottom':[0,1],'side':[1,2]}}


class RigidAttachmentTests(Case):
    def test_edge_distance_and_uv_face_bindings_use_source_ids_after_union_or_cyclic_rotation(self):
        data=candidate();params=mapping();params['origin']={'kind':'EDGE','edge_id':'bottom','fraction':.5}
        self.assertEqual(selector_uv(params['origin'],piece()),[2.,0.])
        data['source_face_vertex_ids']=[[10,11,12],[10,12,13]]
        data['source_vertex_map']={str(i+10):i for i in range(4)}
        data['faces'][0]=[1,2,0]
        bound=bind_selectors(data,params,piece());self.assertEqual(bound['origin']['uv_cm'],[2.,0.])
        points=[[u+10,v+20,30.] for u,v,z in data['placed_cm']]
        frames=[{'frame':1,'vertices_cm':points,'body_geometry_sha256':'a'*64}]
        output=attachment_frames(data,frames,bound,source_axes({'axis':[0,-1,0],'up':[0,0,1]}),[0,0,0],.5,60,[0,0,1],.0001)
        self.assertEqual(output[0]['target_origin_cm'],[12.,20.,30.])
        self.assertEqual(output[0]['translation_cm'],[12.,20.,30.5])

    def test_frame_rotation_is_rigid_source_anchor_exact_and_all_inputs_remain_unchanged(self):
        data=candidate();params=mapping();bound=bind_selectors(data,params,piece())
        frames=[{'frame':n,'vertices_cm':[[u+10+n,v+20,30.] for u,v,z in data['placed_cm']], 'body_geometry_sha256':'a'*64} for n in (1,2,3)]
        before=digest([data,params,frames])
        result=attachment_frames(data,frames,bound,source_axes({'axis':[0,-1,0],'up':[0,0,1]}),[1.,2.,3.],.7,60,[0,0,1],.0001)
        for row in result:
            matrix=row['rotation']
            for a in range(3):
                for b in range(3):self.assertAlmostEqual(sum(matrix[k][a]*matrix[k][b] for k in range(3)),float(a==b))
            source_anchor=[sum(matrix[i][j]*[1.,2.,3.][j] for j in range(3))+row['translation_cm'][i] for i in range(3)]
            self.assertAlmostEqual(source_anchor[2],30.7)
        self.assertEqual(before,digest([data,params,frames]))

    def test_missing_edges_marks_off_panel_uv_corrupt_binding_and_degenerate_frame_refused(self):
        for change in ('edge','mark','uv','binding','degenerate'):
            data=candidate();params=mapping()
            if change=='edge':params['origin']={'kind':'EDGE','edge_id':'invented','fraction':.5}
            if change=='mark':params['origin']={'kind':'MARK','mark_id':'invented'}
            if change=='uv':params['origin']['uv_cm']=[40.,40.]
            if change=='binding':data['source_face_vertex_ids'][0]=[1,0,2]
            if change=='degenerate':params['up']=copy.deepcopy(params['right'])
            with self.subTest(change=change),self.assertRaises(StudioError):bind_selectors(data,params,piece())

    def test_incomplete_observations_body_normal_opposition_and_temporal_flip_refused(self):
        data=candidate();bound=bind_selectors(data,mapping(),piece());axes=source_axes({'axis':[0,-1,0],'up':[0,0,1]})
        frames=[{'frame':n,'vertices_cm':copy.deepcopy(data['placed_cm']),'body_geometry_sha256':'a'*64} for n in (1,2,3)]
        for change in ('coverage','normal','flip','vertices'):
            current=copy.deepcopy(frames);normal=[0,0,1]
            if change=='coverage':current.pop(1)
            if change=='normal':normal=[0,0,-1]
            if change=='flip':current[1]['vertices_cm']=[[u,-v,-z] for u,v,z in data['placed_cm']]
            if change=='vertices':current[1]['vertices_cm'].pop()
            with self.subTest(change=change),self.assertRaises(StudioError):attachment_frames(data,current,bound,axes,[0,0,0],.5,45,normal,.0001)

    def test_manual_calibration_and_missing_native_source_dependency_cannot_admit_attachment(self):
        project=ready_project(self.root);path=self.root/'manual.json'
        atomic_json(path,{'status':'RIGID_DIMENSION_CALIBRATED_UNACCEPTED','dimensions_status':'PASS'})
        ref={'path':path.name,'sha256':sha(path)}
        with self.assertRaisesRegex(StudioError,'canonical native'):canonical_calibrated_part(project,ref)
        dependency=self.root/'source.blend';dependency.write_bytes(b'fixture');dep={'path':dependency.name,'sha256':sha(dependency)}
        raw={'status':'RIGID_DIMENSION_CALIBRATED_UNACCEPTED','dimensions_status':'PASS',
             'artifact':dep,'geometry':dep,'profile':dep,'candidate':dep,'package':dep,'dossier':dep}
        atomic_json(path,raw);ref['sha256']=sha(path)
        with patch('a3d.garment_motion._native_origin',return_value=({'result':raw,'files':[]},{})):
            # Imported local symbol is the authenticated route used by descriptor.
            with patch('a3d.rigid_attachment._native_origin',return_value=({'result':raw,'files':[]},{})):
                with self.assertRaisesRegex(StudioError,'canonically registered'):canonical_calibrated_part(project,ref)
