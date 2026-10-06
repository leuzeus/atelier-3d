"""Portable native-adapter fixtures; no actual Blender surface is qualified."""
import copy
import hashlib
import json
import tempfile
import unittest
from pathlib import Path
from types import SimpleNamespace
from unittest.mock import patch

from a3d.core import ROOT,StudioError,contract,digest
from blender.anchor_reserve import moving_indices,measure_anchor_reserve,propose_anchor_reserve,verified_anchor_body
from tests.test_anchor_reserve import fixture


class NativeAnchorReserveAdapter(unittest.TestCase):
    def setUp(self):
        directory=ROOT/'work/test-native-anchor-reserve';directory.mkdir(parents=True,exist_ok=True)
        self.temp=tempfile.TemporaryDirectory(dir=directory);self.root=Path(self.temp.name).resolve()
        self.geometry={'vertices_cm':[[0.,0.,0.],[0.,1.,0.],[0.,0.,1.]],'faces':[[0,1,2]],'face_sets':[1],
                       'source_sha256':'source','pose_sha256':'pose'}
        self.actual={k:copy.deepcopy(self.geometry[k]) for k in ('vertices_cm','faces','face_sets')}
        self.profile={'frame':{'up':[1.,0.,0.]},'pose_sha256':'pose','source_sha256':'source','cache_key':'cache',
                      'geometry_sha256':digest([self.geometry['vertices_cm'],self.geometry['faces']])}
        self.file=self.root/'body.json';self.raw=json.dumps(self.profile).encode();self.file.write_bytes(self.raw)
        self.ref={'path':'body.json','sha256':hashlib.sha256(self.raw).hexdigest()}
        self.geometry_file=self.root/'geometry.json';self.geometry_raw=json.dumps(self.geometry).encode()
        self.geometry_file.write_bytes(self.geometry_raw)
        self.geometry_ref={'path':'geometry.json','sha256':hashlib.sha256(self.geometry_raw).hexdigest()}
        self.binding={'profile_ref':self.ref,'profile_file':str(self.file),'profile_sha256':digest(self.profile),
                      'geometry_ref':self.geometry_ref,'geometry_file':str(self.geometry_file),
                      'canonical_geometry':copy.deepcopy(self.actual),'profile_cache_key':'cache','source_sha256':'source',
                      'frame':self.profile['frame'],'pose_sha256':'pose','geometry_sha256':self.profile['geometry_sha256'],
                      'native_body_origin':{'event_id':1},'collider_names':['target']}
        self.body=SimpleNamespace(name='target',type='MESH',get=lambda key:'cache' if key=='a3d_profile_cache_key' else None)
        self.bpy=SimpleNamespace(data=SimpleNamespace(objects=SimpleNamespace(get=lambda name:self.body if name=='target' else None)),
                                 context=SimpleNamespace(evaluated_depsgraph_get=lambda:object()))
        self.bpy_patch=patch.dict('sys.modules',{'bpy':self.bpy});self.bpy_patch.start();self.addCleanup(self.bpy_patch.stop)
        self.evaluate_patch=patch('blender.body_target.evaluated_mesh',side_effect=lambda *args:(copy.deepcopy(self.actual),[[0,1,2]]))
        self.evaluate_patch.start();self.addCleanup(self.evaluate_patch.stop)
        self.payload,self.points,_,_=fixture()
        self.payload['placed_cm']=copy.deepcopy(self.points)
        self.context={'bodies':[{'name':'target','closed':True,'orientation_issues':[],'sha256':'surface',
                                 'object':self.body,'coords':copy.deepcopy(self.actual['vertices_cm']),'faces':[[0,1,2]],
                                 'tree':object(),'snapshot':{},'triangles':[[[0,0,0],[0,1,0],[0,0,1]]]}]}
        self.plan={'collision':{'clearance_cm':.3},'supports':{},
                   'layers':{'nodes':[{'kind':'body','source_ref':self.ref,'colliders':['target']}]}}
        self.budgets={'max_displacement_cm':2.,'max_step_cm':.1,'max_iterations':20,'max_seconds':10.}
        self.declared={'version':1,'mode':'PERMANENT_COMPONENT_BODY_AXIS_TRANSLATION_V1','body_ref':self.ref,
                       'direction':'BODY_FRAME_UP','reserve_source':'PLAN_COLLISION_CLEARANCE','budgets':self.budgets}
        self.spec={'version':1,'component_id':'fixture','source_ref':'fixture',
                   'regular_mesh':{'spacing_cm':1.,'min_spacing_cm':.2,'refinement_distance_cm':1.,'max_vertices':100},
                   'anchor_reserve_correction':self.declared,
                   'metric_recovery':{'protected_edges':[],'budgets':self.budgets},'placement_correction':{}}
        self.quality={'min_angle_degrees':15.,'min_edge_cm':.001,'min_stretch':.5,'max_stretch':2.}

    def tearDown(self):self.temp.cleanup()

    def signed(self,offset=.4):
        return {'ambiguous_sign_count':0,'minimum_signed_offset_cm':offset,'clearance_cm':.3,
                'distance_metric':'NEAREST_SURFACE_EUCLIDEAN_NORMAL_SIGN_WITH_UNANIMOUS_RAY_PARITY_FOR_FLOAT32_SIGN_UNCERTAINTY',
                'worst':{'collider':'target','sample':0,'face':0,'signed_offset_cm':offset,'sign_classification':'NEAREST_NORMAL'}}

    def source_spec(self):
        from tests.test_native_placement_correction import fixture as placement_fixture
        _,_,placement,_=placement_fixture()
        spec=copy.deepcopy(self.spec);spec['placement_correction']=placement
        spec['metric_recovery']={'version':1,'piece_ids':['first'],'protected_edges':[{'piece':'first','edge':'anchor'}],
            'strain_weight':1.,'budgets':{'max_iterations':20,'max_seconds':10.,'max_displacement_cm':2.,
             'max_step_cm':.1,'cg_iterations':5,'cg_tolerance':.001,'stagnation_iterations':3}}
        return spec

    def native(self,operation='prepare_body_target',mutate=None):
        result={'status':'NATIVE_BODY_TARGET_MEASURED' if operation=='prepare_body_target' else 'BODY_TARGET_INTRODUCED',
                'geometry_sha256':self.profile['geometry_sha256'],'pose_sha256':'pose','profile_cache_key':'cache'}
        if operation=='prepare_body_target':result['artifacts']={'profile':self.ref,'geometry':self.geometry_ref}
        else:result.update(profile_ref=self.ref,geometry_ref=self.geometry_ref)
        receipt={'operation':operation,'files':[self.ref,self.geometry_ref],'result':result}
        if mutate:mutate(receipt)
        raw=json.dumps(receipt).encode();path=self.root/'native.json';path.write_bytes(raw)
        origin={'event_id':1,'receipt':{'path':'native.json','sha256':hashlib.sha256(raw).hexdigest()}}
        def match(project,predicate):
            if not predicate(receipt):raise StudioError('No exact completed fixture native origin')
            return receipt,origin
        return match

    def test_signed_callback_covers_full_body_surface_and_every_stop(self):
        identity={'surface':'surface'};moving=moving_indices(self.payload,{0,1})
        with patch('blender.cloth_contacts._body_binding',return_value=None),\
                patch('blender.pattern_assembly.collision_check',return_value=self.signed()) as query:
            result=measure_anchor_reserve(self.payload,self.points,self.context,self.plan,self.binding,[0,1],moving,identity)
        self.assertEqual(result['status'],'MEASURED');self.assertEqual(query.call_count,2)
        self.assertEqual(query.call_args.kwargs['surface_triangles'],[self.context['bodies'][0]['triangles']])
        self.assertEqual(result['moving_indices'],list(range(9)))
        self.assertEqual(result['protected_contacts'],[{'vertex':i,'signed_offset_cm':.4,'clearance_cm':.3} for i in (0,1)])

    def test_changed_profile_body_orientation_or_sign_cannot_supply_measurement(self):
        self.file.write_bytes(b'changed')
        with patch('blender.cloth_contacts._body_binding') as body:
            result=measure_anchor_reserve(self.payload,self.points,self.context,self.plan,self.binding,[0],[0],{})
            self.assertEqual(result['status'],'UNAVAILABLE');body.assert_not_called()
        self.file.write_bytes(self.raw)
        with patch('blender.cloth_contacts._body_binding',return_value={'ok':False}):
            self.assertEqual(measure_anchor_reserve(self.payload,self.points,self.context,self.plan,self.binding,[0],[0],{})['status'],'UNAVAILABLE')
        with patch('blender.cloth_contacts._body_binding',return_value=None),\
                patch('blender.pattern_assembly.collision_check',return_value={'ambiguous_sign_count':1}):
            self.assertEqual(measure_anchor_reserve(self.payload,self.points,self.context,self.plan,self.binding,[0],[0],{})['status'],'AMBIGUOUS')

    def test_invalid_rest_stops_before_any_body_query_or_translation(self):
        bad=copy.deepcopy(self.payload);bad['rest_cm'][2]=[.0001,.0001,0.]
        with patch('blender.anchor_reserve.measure_anchor_reserve') as query:
            result=propose_anchor_reserve(bad,self.points,self.context,{'pins':[]},self.plan,self.spec,self.binding,
                self.quality,self.points,{'budgets':self.budgets,'protected_indices':[0]})
        query.assert_not_called();self.assertEqual(result['status'],'NOT_EXECUTED_INVALID_SOURCE_REST')
        self.assertEqual(result['coordinates_cm'],self.points)

    def test_rotated_sourced_axis_rigid_proposal_keeps_original_budget_and_no_admission(self):
        before=digest([self.payload,self.points,self.plan,self.spec])
        def query(source,points,context,plan,binding,stops,moving,identity):
            return {'status':'MEASURED','context_identity':identity,'source_sha256':digest(source),
                    'candidate_sha256':digest(points),'method':'FULL_BODY_COLLISION','sign_status':'UNAMBIGUOUS',
                    'moving_indices':moving,'protected_contacts':[{'vertex':i,'signed_offset_cm':points[i][0],
                                                                  'clearance_cm':.3} for i in stops]}
        with patch('blender.anchor_reserve.measure_anchor_reserve',side_effect=query):
            result=propose_anchor_reserve(self.payload,self.points,self.context,{'pins':[]},self.plan,self.spec,
                self.binding,self.quality,self.points,{'budgets':self.budgets,'protected_indices':[0]})
        self.assertEqual(result['status'],'ANCHORS_ADMISSIBLE_ONLY');self.assertEqual(result['qualification'],'NONE')
        self.assertEqual(result['body_frame_up'],[1.,0.,0.])
        self.assertEqual(result['displacement_reference_sha256'],digest(self.points))
        self.assertEqual(result['coordinates_cm'][9],self.points[9])
        self.assertEqual(digest([self.payload,self.points,self.plan,self.spec]),before)

    def test_declared_profile_must_match_plan_and_native_origin_before_axis_use(self):
        # Fill the existing metric/placement schema with a valid bounded fixture.
        spec=self.source_spec()
        recipe={'colliders':[{'object':'target'}]}
        with patch('a3d.native_evidence.native_origin',side_effect=self.native()):
            binding=verified_anchor_body(SimpleNamespace(root=self.root),recipe,self.plan,spec)
        self.assertEqual(binding['frame'],self.profile['frame'])
        other=copy.deepcopy(self.plan);other['layers']['nodes'][0]['source_ref']['sha256']='0'*64
        with patch('a3d.native_evidence.native_origin') as origin,self.assertRaises(StudioError):
            verified_anchor_body(SimpleNamespace(root=self.root),recipe,other,spec)
        origin.assert_not_called()

    def test_schema_requires_explicit_reserve_and_forbids_unknown_axis_or_extra_coordinates(self):
        schema=__import__('a3d.core',fromlist=['read_json']).read_json(ROOT/'schemas/pattern-preparation.schema.json')['properties']['anchor_reserve_correction']
        from a3d.core import validate
        validate(self.declared,schema)
        for key,value in [('direction','WORLD_Z'),('coordinates_cm',[[0,0,1]]),('reserve_source','USER_CONSTANT')]:
            bad={**self.declared,key:value}
            with self.subTest(key=key),self.assertRaises(StudioError):validate(bad,schema)

    def test_opt_out_preserves_default_without_body_access(self):
        with patch('a3d.native_evidence.native_origin') as origin:
            self.assertIsNone(verified_anchor_body(None,{}, {}, {}))
        origin.assert_not_called()

    def test_completed_introduction_binds_both_exact_body_artifacts(self):
        with patch('a3d.native_evidence.native_origin',side_effect=self.native('introduce_body_target')):
            binding=verified_anchor_body(SimpleNamespace(root=self.root),{'colliders':[{'object':'target'}]},
                                         self.plan,self.source_spec())
        self.assertEqual(binding['geometry_ref'],self.geometry_ref)
        self.assertEqual(binding['profile_cache_key'],'cache')
        self.assertEqual(binding['canonical_geometry'],self.actual)

    def test_artifact_merely_listed_in_receipt_is_not_profile_origin(self):
        origin=self.native(mutate=lambda row:row['result']['artifacts'].__setitem__('profile',{'path':'other.json','sha256':'0'*64}))
        with patch('a3d.native_evidence.native_origin',side_effect=origin),self.assertRaises(StudioError):
            verified_anchor_body(SimpleNamespace(root=self.root),{'colliders':[{'object':'target'}]},self.plan,self.source_spec())

    def test_profile_geometry_must_share_same_completed_receipt(self):
        origin=self.native(mutate=lambda row:row['files'].remove(self.geometry_ref))
        with patch('a3d.native_evidence.native_origin',side_effect=origin),self.assertRaises(StudioError):
            verified_anchor_body(SimpleNamespace(root=self.root),{'colliders':[{'object':'target'}]},self.plan,self.source_spec())

    def test_raw_native_receipt_replacement_after_origin_is_refused(self):
        real_origin=self.native()
        def replaced(project,predicate):
            receipt,origin=real_origin(project,predicate)
            (self.root/'native.json').write_bytes(b'{}')
            return receipt,origin
        with patch('a3d.native_evidence.native_origin',side_effect=replaced),self.assertRaisesRegex(StudioError,'native body receipt changed'):
            verified_anchor_body(SimpleNamespace(root=self.root),{'colliders':[{'object':'target'}]},self.plan,self.source_spec())

    def test_changed_canonical_geometry_pose_and_source_are_refused(self):
        for key in ('source_sha256','pose_sha256','vertices_cm'):
            with self.subTest(key=key):
                changed=copy.deepcopy(self.geometry)
                changed[key]='other' if key!='vertices_cm' else [[1.,0.,0.],*changed['vertices_cm'][1:]]
                raw=json.dumps(changed).encode();self.geometry_file.write_bytes(raw)
                self.geometry_ref['sha256']=hashlib.sha256(raw).hexdigest()
                with patch('a3d.native_evidence.native_origin',side_effect=self.native()),self.assertRaisesRegex(StudioError,'geometry or pose'):
                    verified_anchor_body(SimpleNamespace(root=self.root),{'colliders':[{'object':'target'}]},self.plan,self.source_spec())
        self.geometry_file.write_bytes(self.geometry_raw)

    def test_authenticated_profile_different_actual_body_or_cache_cannot_bind(self):
        origin=self.native()
        self.actual['face_sets']=[9]
        with patch('a3d.native_evidence.native_origin',side_effect=origin),self.assertRaisesRegex(StudioError,'evaluated body differs'):
            verified_anchor_body(SimpleNamespace(root=self.root),{'colliders':[{'object':'target'}]},self.plan,self.source_spec())
        self.actual['face_sets']=[1];self.body.get=lambda key:'other-cache'
        with patch('a3d.native_evidence.native_origin',side_effect=origin),self.assertRaisesRegex(StudioError,'another measured body'):
            verified_anchor_body(SimpleNamespace(root=self.root),{'colliders':[{'object':'target'}]},self.plan,self.source_spec())

    def test_unchanged_capture_of_wrong_body_is_not_accepted(self):
        self.actual['vertices_cm'][0][0]=1.
        with patch('blender.cloth_contacts._body_binding',return_value=None),\
                patch('blender.pattern_assembly.collision_check') as query:
            result=measure_anchor_reserve(self.payload,self.points,self.context,self.plan,self.binding,[0],[0],{})
        self.assertEqual(result['status'],'UNAVAILABLE');query.assert_not_called()

    def test_forged_capture_triangles_and_cache_are_refused_before_query(self):
        with patch('blender.cloth_contacts._body_binding',return_value=None),\
                patch('blender.pattern_assembly.collision_check') as query:
            self.context['bodies'][0]['triangles'][0][0]=[9,9,9]
            result=measure_anchor_reserve(self.payload,self.points,self.context,self.plan,self.binding,[0],[0],{})
            self.assertEqual(result['status'],'UNAVAILABLE');query.assert_not_called()

    def test_body_files_and_evaluated_surface_are_rechecked_after_measurement(self):
        def change(*args,**kwargs):
            self.geometry_file.write_bytes(b'changed')
            return self.signed()
        with patch('blender.cloth_contacts._body_binding',return_value=None),\
                patch('blender.pattern_assembly.collision_check',side_effect=change):
            result=measure_anchor_reserve(self.payload,self.points,self.context,self.plan,self.binding,[0],[0],{})
        self.assertEqual(result['status'],'UNAVAILABLE')
        self.geometry_file.write_bytes(self.geometry_raw)
        with patch('blender.cloth_contacts._body_binding',side_effect=[None,{'reason':'COLLIDER_GEOMETRY_CHANGED'}]),\
                patch('blender.pattern_assembly.collision_check',return_value=self.signed()):
            result=measure_anchor_reserve(self.payload,self.points,self.context,self.plan,self.binding,[0],[0],{})
        self.assertEqual(result['status'],'UNAVAILABLE')

    def test_unknown_classifier_or_native_exception_is_unavailable(self):
        for value in ({},dict(self.signed(),distance_metric='UNKNOWN')):
            with self.subTest(value=value),patch('blender.cloth_contacts._body_binding',return_value=None),\
                    patch('blender.pattern_assembly.collision_check',return_value=value):
                result=measure_anchor_reserve(self.payload,self.points,self.context,self.plan,self.binding,[0],[0],{})
            self.assertEqual(result['status'],'UNAVAILABLE')
        with patch('blender.cloth_contacts._body_binding',return_value=None),\
                patch('blender.pattern_assembly.collision_check',side_effect=OSError('unavailable')):
            result=measure_anchor_reserve(self.payload,self.points,self.context,self.plan,self.binding,[0],[0],{})
        self.assertEqual(result['status'],'UNAVAILABLE')

    def test_geometry_file_raw_sha_is_required_before_surface_queries(self):
        self.geometry_file.write_bytes(b'{}')
        with patch('blender.cloth_contacts._body_binding') as body,\
                patch('blender.pattern_assembly.collision_check') as query:
            result=measure_anchor_reserve(self.payload,self.points,self.context,self.plan,self.binding,[0],[0],{})
        self.assertEqual(result['status'],'UNAVAILABLE');body.assert_not_called();query.assert_not_called()


if __name__=='__main__':unittest.main()
