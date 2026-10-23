"""Generic synthetic source membership tests; no anatomical admission."""
import copy
import json
import math
import unittest

from a3d.anatomy_profile import profile_mesh
from a3d.body_region_policy import build_body_region_policy,prepare_project_body_region_policy
from a3d.catalog_anatomy import region_guides
from a3d.core import StudioError,digest
from a3d.shoulder_surface import measured_surface_shoulders
from tests.test_body_region_sections import box


def fixture(rotated=False,scaled=False):
    vertices,faces,_=box();labels=[1]*len(faces)
    joints={};centers={'head.center':[1]};membership={'1':'spine.upper'}
    for side,x,names in [('left',30.,[9,12,21]),('right',-30.,[10,11,20])]:
        offset=len(vertices);count=8
        vertices += [[x+3*math.cos(i*math.tau/count),3*math.sin(i*math.tau/count),z]
                     for z in (80.,110.,140.,170.,180.) for i in range(count)]
        for level,label in enumerate(names+[1]):
            faces += [[offset+level*count+i,offset+level*count+(i+1)%count,
                       offset+(level+1)*count+(i+1)%count,offset+(level+1)*count+i] for i in range(count)]
            labels += [label]*count
        faces += [[offset+i for i in reversed(range(count))],[offset+4*count+i for i in range(count)]]
        labels += [names[0],1]
        joints.update({'shoulder.'+side:[1,names[2]],'elbow.'+side:[names[2],names[1]],'wrist.'+side:[names[1],names[0]]})
        centers['hand.'+side]=[names[0]]
        membership.update({str(label):bone+'.'+side for label,bone in zip(names,['hand','forearm','upper_arm'])})
    original={'vertices_cm':vertices,'faces':faces,'face_sets':labels,'source_sha256':'a'*64,'pose_sha256':digest(vertices)}
    adapter={'source_geometry_sha256':digest([vertices,faces,labels]),
             'source_ref':{'path':'synthetic.blend','sha256':'a'*64},'torso_regions':[1],
             'joints':joints,'centers':centers,'region_to_bone':membership}
    original['rig_landmarks']=region_guides(original,adapter)['rig_landmarks']
    # Head is deliberately a guide only; body region policy never uses it as a
    # surface or invents hand/finger landmarks from it.
    original['rig_landmarks']['head.center']['point_cm']=[0.,0.,175.]
    geometry=copy.deepcopy(original)
    options={'up_axis':[0.,0.,1.],'forward_axis':[0.,-1.,0.],'origin_cm':[0.,0.,0.],
             'torso_faces':list(range(6)),'segmentation_source_ref':'synthetic:source-box','section_count':24}
    if rotated or scaled:
        angle=.41 if rotated else 0.
        def transform(p):
            x,y,z=p;z*=1.05 if scaled else 1.
            return [11+x,-7+math.cos(angle)*y-math.sin(angle)*z,5+math.sin(angle)*y+math.cos(angle)*z]
        def direction(p):
            x,y,z=p;return [x,math.cos(angle)*y-math.sin(angle)*z,math.sin(angle)*y+math.cos(angle)*z]
        geometry['vertices_cm']=[transform(p) for p in geometry['vertices_cm']]
        for row in geometry['rig_landmarks'].values():row['point_cm']=transform(row['point_cm'])
        geometry['pose_sha256']=digest(geometry['vertices_cm'])
        options.update(up_axis=direction([0.,0.,1.]),forward_axis=direction([0.,-1.,0.]),origin_cm=[11.,-7.,5.])
    triangles=[]
    for face in faces:
        triangles += [[face[0],face[i],face[i+1]] for i in range(1,len(face)-1)]
    profile=measured_surface_shoulders(profile_mesh(geometry,options),geometry,triangles)
    refs={key:{'path':key+'.json','sha256':'b'*64} for key in
          ('profile_ref','geometry_ref','triangles_ref','adapter_ref','source_geometry_ref')}
    policy_options={'purpose':'TEST_ONLY','regions':['upper','forearm'],'sides':['left','right'],
                    'include_hand_envelopes':True,'fraction_domain':[0.,1.],'fractions':[0.,.5,1.],
                    'plane_reference_axis':'forward','numerical_tolerance_cm':.000001,
                    'budgets':{'max_sections':12,'max_triangle_evaluations':10000,'max_projection_vertices':1000}}
    return profile,geometry,triangles,adapter,original,refs,policy_options


class BodyRegionPolicy(unittest.TestCase):
    def test_source_memberships_create_four_regions_two_hands_without_measurement_or_mutation(self):
        values=fixture();before=digest(values);r=build_body_region_policy(*values)
        self.assertEqual(r['status'],'BODY_REGION_POLICY_PREPARED_NOT_MEASURED')
        self.assertEqual(r['measurements'],'NOT_EXECUTED');self.assertEqual(r['fitting'],'NOT_EXECUTED')
        self.assertEqual(r['acceptance'],'NOT_GRANTED');self.assertFalse(r['adapter_rebound_to_variant'])
        self.assertEqual(len(r['policy']['regions']),4);self.assertEqual(len(r['policy']['hand_envelopes']),2)
        for row in r['policy']['regions']:
            bones={'upper_arm.'+row['side'],'forearm.'+row['side'],'hand.'+row['side']}
            expected=[i for i,label in enumerate(values[1]['face_sets']) if values[3]['region_to_bone'][str(label)] in bones]
            self.assertEqual(row['face_ids'],expected)
        self.assertEqual(r['native_body_origin'],'NOT_CHECKED_BY_PORTABLE_POLICY_BUILDER')
        self.assertEqual(digest(values),before);self.assertEqual(r,build_body_region_policy(*values))
        self.assertEqual(r,json.loads(json.dumps(r)))

    def test_rotated_and_stature_variant_use_same_source_domains_without_rebinding_adapter(self):
        a=build_body_region_policy(*fixture());values=fixture(True,True);b=build_body_region_policy(*values)
        for first,second in zip(a['policy']['regions'],b['policy']['regions']):self.assertEqual(first['face_ids'],second['face_ids'])
        self.assertEqual(b['policy']['hand_source']['source_geometry_sha256'],digest(values[4]))
        self.assertNotEqual(values[3]['source_geometry_sha256'],digest([values[1]['vertices_cm'],values[1]['faces'],values[1]['face_sets']]))
        self.assertFalse(b['body_changed'])

    def test_absent_data_localized_and_no_guessed_joint_or_hand_domains(self):
        values=list(fixture());values[3]=None;r=build_body_region_policy(*values)
        self.assertEqual(r['status'],'NEEDS_DATA');self.assertIsNone(r['policy'])
        self.assertIn({'source':'adapter','reason':'SOURCE_DATA_REQUIRED'},r['diagnostics'])
        values=list(fixture());del values[3]['joints']['shoulder.left'];r=build_body_region_policy(*values)
        self.assertEqual(r['status'],'NEEDS_DATA');self.assertNotIn('upper.left',[x['id'] for x in r['policy']['regions']])
        values=list(fixture());del values[3]['region_to_bone']['9'];r=build_body_region_policy(*values)
        self.assertEqual(r['status'],'NEEDS_DATA')
        self.assertFalse(any(x['side']=='left' for x in r['policy']['regions']))
        self.assertFalse(any(x['side']=='left' for x in r['policy']['hand_envelopes']))

    def test_topology_original_metric_pose_cache_triangulation_and_absent_mapping_refused(self):
        for change in ('original_metric','topology','pose','cache','triangles','mapping_absent','mapping_alias'):
            values=list(fixture());p,g,t,a,o,refs,options=values
            if change=='original_metric':o['vertices_cm'][0][0]+=.01
            if change=='topology':g['faces'][0].reverse()
            if change=='pose':g['pose_sha256']='c'*64
            if change=='cache':p['cache_key']='d'*64
            if change=='triangles':t.reverse()
            if change=='mapping_absent':a['region_to_bone']['999']='hand.left'
            if change=='mapping_alias':a['region_to_bone']['09']='hand.left'
            with self.subTest(change=change),self.assertRaises(StudioError):build_body_region_policy(*values)

    def test_forged_consistently_reprofiled_joint_rejected_against_source_ring(self):
        values=list(fixture());g=values[1]
        g['rig_landmarks']['elbow.left']['point_cm'][0]+=.01
        options={'up_axis':[0.,0.,1.],'forward_axis':[0.,-1.,0.],'origin_cm':[0.,0.,0.],
                 'torso_faces':list(range(6)),'segmentation_source_ref':'synthetic:source-box','section_count':24}
        values[0]=measured_surface_shoulders(profile_mesh(g,options),g,values[2])
        with self.assertRaisesRegex(StudioError,'exact source ring'):build_body_region_policy(*values)

    def test_native_float32_vertex_roundtrip_keeps_source_double_guides_with_reported_bound(self):
        import struct
        values=list(fixture(True,True));g=values[1]
        g['vertices_cm']=[[100.*struct.unpack('f',struct.pack('f',value/100.))[0] for value in point]
                          for point in g['vertices_cm']]
        angle=.41
        options={'up_axis':[0.,-math.sin(angle),math.cos(angle)],
                 'forward_axis':[0.,-math.cos(angle),-math.sin(angle)],'origin_cm':[11.,-7.,5.],
                 'torso_faces':list(range(6)),'segmentation_source_ref':'synthetic:source-box','section_count':24}
        values[0]=measured_surface_shoulders(profile_mesh(g,options),g,values[2])
        r=build_body_region_policy(*values)
        self.assertEqual(r['status'],'BODY_REGION_POLICY_PREPARED_NOT_MEASURED')
        for row in r['source_joint_checks'].values():
            self.assertLessEqual(row['centroid_residual_cm'],row['native_float32_centroid_roundtrip_bound_cm'])
        self.assertTrue(any(row['centroid_residual_cm']>1e-7 for row in r['source_joint_checks'].values()))

    def test_explicit_options_and_budgets_no_parallel_axis_or_domain_fallback(self):
        for change in ('missing','fraction_order','fraction_domain','budget','parallel_axis','manual_coordinate','unknown_side'):
            values=list(fixture());o=values[-1]
            if change=='missing':del o['fractions']
            if change=='fraction_order':o['fractions']=[0.,1.,.5]
            if change=='fraction_domain':o['fraction_domain']=[.2,.8]
            if change=='budget':o['budgets']['max_sections']=11
            if change=='parallel_axis':o['plane_reference_axis']='up'
            if change=='manual_coordinate':o['hand_center_world']=[1.,2.,3.]
            if change=='unknown_side':o['sides']=['left','female']
            with self.subTest(change=change),self.assertRaises(StudioError):build_body_region_policy(*values)


def project_inputs(project):
    """Portable wrapper unit inputs only; native origin must be mocked or fail."""
    from a3d.core import atomic_json,sha
    from tests.test_body_target import target_fixture
    p,g,t,a,o,_,options=fixture()
    artifact=project.root/'body.blend';artifact.write_bytes(b'PORTABLE_UNIT_ONLY_NO_NATIVE_BODY_EXECUTION')
    for geo in (g,o):geo['source_sha256']=sha(artifact)
    a['source_ref']={'path':'body.blend','sha256':sha(artifact)}
    native_options={'up_axis':[0.,0.,1.],'forward_axis':[0.,-1.,0.],'origin_cm':[0.,0.,0.],
                    'torso_faces':list(range(6)),'segmentation_source_ref':'synthetic:source-box','section_count':24}
    p=measured_surface_shoulders(profile_mesh(g,native_options),g,t)
    selected={'version':1,'source_blend':'body.blend','source_sha256':sha(artifact),
              'source_ref':'PORTABLE_UNIT_FIXTURE_ONLY','frame':1,'unit_scale_m':1.,
              'meshes':['body'],'dependencies':[],'reference_object':'reference'}
    atomic_json(project.root/'selection.json',selected);atomic_json(project.root/'anatomy.json',a)
    atomic_json(project.root/'target.json',target_fixture(sha(project.root/'selection.json'),sha(project.root/'anatomy.json')))
    artifacts={}
    for name,value in [('profile',p),('geometry',g),('triangles',t),('source-geometry',o),('options',native_options)]:
        path=project.root/(name+'.json');atomic_json(path,value);artifacts[name]={'path':path.name,'sha256':sha(path)}
    evidence={name:{'path':name+'.json','sha256':sha(project.root/(name+'.json'))} for name in ('selection','target','anatomy')}
    evidence['adapter']=evidence.pop('anatomy')
    receipt={'status':'NATIVE_BODY_TARGET_MEASURED','native_reopened':True,'artifacts':artifacts,
             'evidence':evidence,'artifact':{'path':'body.blend','sha256':sha(artifact)}}
    receipt['cache_key']=digest(receipt)
    atomic_json(project.root/'options-policy.json',options)
    return {'operation':'prepare_body_target','result':receipt},{'scope':'MOCKED_PORTABLE_UNIT_ORIGIN_ONLY'},artifacts['profile']


class ProjectBodyRegionPolicy(unittest.TestCase):
    def temporary(self):
        import tempfile
        from a3d.core import ROOT
        (ROOT/'work/test-runs').mkdir(parents=True,exist_ok=True)
        return tempfile.TemporaryDirectory(dir=ROOT/'work/test-runs')

    def test_wrapper_uses_receipt_derived_refs_readonly_with_mocked_unit_origin(self):
        from pathlib import Path
        from unittest.mock import patch
        from a3d.core import sha
        from tests.support import ready_project
        with self.temporary() as directory:
            project=ready_project(Path(directory),True);native,origin,ref=project_inputs(project)
            files={str(path):sha(path) for path in project.root.rglob('*') if path.is_file()}
            with patch('a3d.native_evidence.native_origin',return_value=(native,origin)):
                r=prepare_project_body_region_policy(project,'options-policy.json',ref)
            self.assertEqual(r['status'],'BODY_REGION_POLICY_PREPARED_NOT_MEASURED')
            self.assertEqual(r['native_body_origin'],origin)
            self.assertEqual(r['refs']['adapter_ref'],native['result']['evidence']['adapter'])
            self.assertEqual(r['refs']['source_geometry_ref'],native['result']['artifacts']['source-geometry'])
            self.assertEqual(r['options_ref']['sha256'],sha(project.root/'options-policy.json'))
            self.assertEqual(files,{str(path):sha(path) for path in project.root.rglob('*') if path.is_file()})

    def test_signed_client_wrapper_registered_as_ordinary_evidence_is_not_native(self):
        from pathlib import Path
        from a3d.core import atomic_json,sha
        from tests.support import ready_project
        with self.temporary() as directory:
            project=ready_project(Path(directory),True);native,_,ref=project_inputs(project)
            client=dict(native,origin='NATIVE_DISPATCH',execution='RETURNED',scope='PORTABLE_NEGATIVE_ONLY')
            client['cache_key']=digest(client);atomic_json(project.root/'client-native-wrapper.json',client)
            project.evidence('client.native-wrapper','client-native-wrapper.json');database=sha(project.db)
            with self.assertRaisesRegex(StudioError,'canonical native run origin'):
                prepare_project_body_region_policy(project,'options-policy.json',ref)
            self.assertEqual(sha(project.db),database)

    def test_changed_real_file_and_rehashed_wrong_target_still_refused(self):
        from pathlib import Path
        from unittest.mock import patch
        from a3d.core import atomic_json,read_json,sha
        from tests.support import ready_project
        for change in ('profile','adapter','original','source_blend','selection_rehashed','not_reopened'):
            with self.subTest(change=change),self.temporary() as directory:
                project=ready_project(Path(directory),True);native,origin,ref=project_inputs(project)
                if change in ('profile','adapter','original','source_blend'):
                    name={'profile':'profile.json','adapter':'anatomy.json','original':'source-geometry.json','source_blend':'body.blend'}[change]
                    (project.root/name).write_bytes(b'CHANGED_SOURCE_UNIT_NEGATIVE_ONLY')
                if change=='selection_rehashed':
                    selection=read_json(project.root/'selection.json');selection['frame']=2
                    atomic_json(project.root/'selection.json',selection)
                    native['result']['evidence']['selection']['sha256']=sha(project.root/'selection.json')
                    native['result']['cache_key']=digest({k:v for k,v in native['result'].items() if k!='cache_key'})
                if change=='not_reopened':
                    native['result']['native_reopened']=False
                    native['result']['cache_key']=digest({k:v for k,v in native['result'].items() if k!='cache_key'})
                before=sha(project.db)
                with patch('a3d.native_evidence.native_origin',return_value=(native,origin)),self.assertRaises(StudioError):
                    prepare_project_body_region_policy(project,'options-policy.json',ref)
                self.assertEqual(sha(project.db),before)

    def test_introduced_native_branch_checks_exact_context_binding_and_source_geometry(self):
        from pathlib import Path
        from unittest.mock import patch
        from a3d.core import read_json,sha
        from tests.support import ready_project
        with self.temporary() as directory:
            project=ready_project(Path(directory),True);prepared,origin,ref=project_inputs(project)
            receipt=prepared['result'];p=read_json(project.root/ref['path']);g=read_json(project.root/receipt['artifacts']['geometry']['path'])
            context_ref={'path':'context.json','sha256':'a'*64};body_ref={'path':'body-receipt.json','sha256':'b'*64}
            descriptor={'receipt':receipt,'profile':p,'geometry':g,'binding_sha256':'c'*64,
                        'context_ref':context_ref,'context':{'body_target_receipt':body_ref}}
            result={'status':'BODY_TARGET_INTRODUCED','profile_ref':ref,'binding_sha256':'c'*64,
                    'profile_cache_key':p['cache_key'],'context':context_ref,'body_target_receipt':body_ref,
                    'source_artifact':receipt['artifact'],'geometry_ref':receipt['artifacts']['geometry'],
                    'actual_geometry_sha256':digest({key:g[key] for key in ('vertices_cm','faces','face_sets')})}
            native={'operation':'introduce_body_target','arguments':{'context_path':'context.json'},'result':result}
            before=sha(project.db)
            with patch('a3d.native_evidence.native_origin',return_value=(native,origin)),patch('a3d.body_context.body_context_descriptor',return_value=descriptor):
                self.assertEqual(prepare_project_body_region_policy(project,'options-policy.json',ref)['body_context_ref'],context_ref)
                result['actual_geometry_sha256']='d'*64
                with self.assertRaisesRegex(StudioError,'exact native body context'):prepare_project_body_region_policy(project,'options-policy.json',ref)
            self.assertEqual(sha(project.db),before)


if __name__=='__main__':unittest.main()
