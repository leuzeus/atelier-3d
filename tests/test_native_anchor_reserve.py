"""Portable native-adapter fixtures; no actual Blender surface is qualified."""
import copy
import hashlib
import json
import tempfile
import unittest
from pathlib import Path
from types import SimpleNamespace
from unittest.mock import Mock,patch

from a3d.core import ROOT,StudioError,contract,digest
from blender.anchor_reserve import (moving_indices,measure_anchor_reserve,propose_anchor_reserve,verified_anchor_body,
                                   _create_bound_body_cache,_bound_body_files,_read_bound_bytes)
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
        def capture(*args,include_contact_surface=False):
            actual=copy.deepcopy(self.actual);triangles=[[0,1,2]];polygons=[0]
            if include_contact_surface:
                return actual,triangles,polygons,digest({'coords_cm':actual['vertices_cm'],
                                                       'triangles':triangles,'polygons':polygons})
            return actual,triangles
        self.capture=capture
        self.evaluate_patch=patch('blender.body_target.evaluated_mesh',side_effect=capture)
        self.evaluate=self.evaluate_patch.start();self.addCleanup(self.evaluate_patch.stop)
        self.payload,self.points,_,_=fixture()
        self.payload['placed_cm']=copy.deepcopy(self.points)
        self.context={'bodies':[{'name':'target','closed':True,'orientation_issues':[],
                                 'sha256':digest({'coords_cm':self.actual['vertices_cm'],'triangles':[[0,1,2]],'polygons':[0]}),
                                 'object':self.body,'coords':copy.deepcopy(self.actual['vertices_cm']),'faces':[[0,1,2]],
                                 'polygons':[0],
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
        self.context['bodies'][0]['orientation_issues']=[{'reason':'INCONSISTENT_CLOSED_WINDING'}]
        with patch('blender.pattern_assembly.collision_check') as query:
            self.assertEqual(measure_anchor_reserve(self.payload,self.points,self.context,self.plan,self.binding,[0],[0],{})['status'],'UNAVAILABLE')
            query.assert_not_called()
        self.context['bodies'][0]['orientation_issues']=[]
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
        def query(source,points,context,plan,binding,stops,moving,identity,*,expected_source_sha256=None,
                  artifact_cache=None,artifact_cache_loader=None):
            return {'status':'MEASURED','context_identity':identity,'source_sha256':expected_source_sha256 or digest(source),
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
        def changed_surface(*args,**kwargs):
            self.actual['vertices_cm'][0][0]=1.
            return self.signed()
        with patch('blender.pattern_assembly.collision_check',side_effect=changed_surface):
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

    def test_single_native_capture_per_boundary_and_no_duplicate_surface_evaluation(self):
        from blender.anchor_reserve import _bound_body_files
        with patch('blender.cloth_contacts._body_binding',side_effect=AssertionError('duplicate evaluation')) as old,\
                patch('blender.anchor_reserve._bound_body_files',wraps=_bound_body_files) as files,\
                patch('blender.pattern_assembly.collision_check',return_value=self.signed()):
            result=measure_anchor_reserve(self.payload,self.points,self.context,self.plan,self.binding,[0],[0],{})
        self.assertEqual(result['status'],'MEASURED');old.assert_not_called()
        self.assertEqual(self.evaluate.call_count,2);self.assertEqual(files.call_count,2)
        self.assertTrue(all(call.kwargs=={'include_contact_surface':True} for call in self.evaluate.call_args_list))

    def test_stale_contact_digest_or_polygon_mapping_is_refused(self):
        for key,value in (('sha256','0'*64),('polygons',[1])):
            with self.subTest(key=key):
                context=copy.deepcopy(self.context);context['bodies'][0][key]=value
                with patch('blender.pattern_assembly.collision_check') as query:
                    result=measure_anchor_reserve(self.payload,self.points,context,self.plan,self.binding,[0],[0],{})
                self.assertEqual(result['status'],'UNAVAILABLE');query.assert_not_called()

    def test_changed_evaluated_triangulation_is_not_accepted_by_same_canonical_polygons(self):
        def capture(*args,**kwargs):
            actual=copy.deepcopy(self.actual);triangles=[[0,2,1]];polygons=[0]
            return actual,triangles,polygons,digest({'coords_cm':actual['vertices_cm'],'triangles':triangles,'polygons':polygons})
        self.evaluate.side_effect=capture
        with patch('blender.pattern_assembly.collision_check') as query:
            result=measure_anchor_reserve(self.payload,self.points,self.context,self.plan,self.binding,[0],[0],{})
        self.assertEqual(result['status'],'UNAVAILABLE');query.assert_not_called()

    def test_open_or_wrong_named_context_cannot_query_signed_body(self):
        for key,value in (('closed',False),('name','proxy')):
            with self.subTest(key=key):
                context=copy.deepcopy(self.context);context['bodies'][0][key]=value
                with patch('blender.pattern_assembly.collision_check') as query:
                    result=measure_anchor_reserve(self.payload,self.points,context,self.plan,self.binding,[0],[0],{})
                self.assertEqual(result['status'],'UNAVAILABLE');query.assert_not_called()

    def test_profile_pose_file_is_checked_again_after_signed_measurement(self):
        def changed(*args,**kwargs):
            value=copy.deepcopy(self.profile);value['pose_sha256']='other-pose'
            self.file.write_bytes(json.dumps(value).encode())
            return self.signed()
        with patch('blender.pattern_assembly.collision_check',side_effect=changed):
            result=measure_anchor_reserve(self.payload,self.points,self.context,self.plan,self.binding,[0],[0],{})
        self.assertEqual(result['status'],'UNAVAILABLE')

    def test_source_digest_can_be_reused_only_under_pure_kernel_postconditions(self):
        source_id=digest(self.payload)
        with patch('blender.anchor_reserve.digest',wraps=digest) as hashes,\
                patch('blender.pattern_assembly.collision_check',return_value=self.signed()):
            result=measure_anchor_reserve(self.payload,self.points,self.context,self.plan,self.binding,[0],[0],{},
                                         expected_source_sha256=source_id)
        self.assertEqual(result['status'],'MEASURED');self.assertEqual(result['source_sha256'],source_id)
        self.assertFalse(any(call.args[0] is self.payload for call in hashes.call_args_list))

    def test_call_local_artifact_cache_preserves_exact_measurements_and_body_captures(self):
        cache=_create_bound_body_cache(self.binding);identity={'source':'fixture'}
        moving=moving_indices(self.payload,{0,1})
        with patch('blender.pattern_assembly.collision_check',return_value=self.signed()) as query:
            original=measure_anchor_reserve(self.payload,self.points,self.context,self.plan,self.binding,[0,1],moving,identity)
        self.assertEqual(query.call_count,2);self.evaluate.reset_mock()
        before=digest([self.payload,self.points,self.binding,self.plan,identity])
        with patch('blender.anchor_reserve._read_bound_json',side_effect=AssertionError('Do not re-decode authenticated bytes')),\
                patch('blender.anchor_reserve._read_bound_bytes',wraps=_read_bound_bytes) as raw,\
                patch('blender.pattern_assembly.collision_check',return_value=self.signed()) as query:
            cached=measure_anchor_reserve(self.payload,self.points,self.context,self.plan,self.binding,[0,1],moving,identity,
                                         artifact_cache=cache)
        self.assertEqual(original,cached)
        self.assertEqual(query.call_count,2);self.assertEqual(self.evaluate.call_count,2)
        self.assertEqual(raw.call_count,4)
        self.assertEqual(before,digest([self.payload,self.points,self.binding,self.plan,identity]))

    def test_artifact_cache_is_isolated_and_immutable_without_global_state(self):
        from dataclasses import FrozenInstanceError
        first=_create_bound_body_cache(self.binding);second=_create_bound_body_cache(copy.deepcopy(self.binding))
        self.assertEqual(first,second);self.assertIsNot(first,second)
        self.assertIsNot(first.snapshot,second.snapshot);self.assertIsNot(first.snapshot,first.seal)
        with self.assertRaises(FrozenInstanceError):first.files=()
        with self.assertRaises(TypeError):first.snapshot[1][0]=('changed',None)
        _bound_body_files(self.binding,artifact_cache=second)

    def test_bound_bytes_modified_or_replaced_between_measurements_refuse_cached_path(self):
        import os
        for mode in ('same-length-bytes','replacement'):
            with self.subTest(mode=mode):
                self.file.write_bytes(self.raw);cache=_create_bound_body_cache(self.binding)
                with patch('blender.pattern_assembly.collision_check',return_value=self.signed()):
                    result=measure_anchor_reserve(self.payload,self.points,self.context,self.plan,self.binding,[0],[0],{},artifact_cache=cache)
                self.assertEqual(result['status'],'MEASURED')
                changed=self.raw.replace(b'pose',b'xxxx',1);self.assertEqual(len(changed),len(self.raw))
                stamp=self.file.stat()
                if mode=='replacement':
                    other=self.root/'replacement.json';other.write_bytes(changed);os.replace(other,self.file)
                else:self.file.write_bytes(changed)
                os.utime(self.file,ns=(stamp.st_atime_ns,stamp.st_mtime_ns))
                with patch('blender.pattern_assembly.collision_check') as query:
                    result=measure_anchor_reserve(self.payload,self.points,self.context,self.plan,self.binding,[0],[0],{},artifact_cache=cache)
                self.assertEqual(result['status'],'UNAVAILABLE');query.assert_not_called()
        self.file.write_bytes(self.raw)

    def test_cached_profile_changed_during_query_is_refused_after_measurement(self):
        cache=_create_bound_body_cache(self.binding)
        def change(*args,**kwargs):
            self.file.write_bytes(self.raw.replace(b'pose',b'xxxx',1));return self.signed()
        with patch('blender.pattern_assembly.collision_check',side_effect=change):
            result=measure_anchor_reserve(self.payload,self.points,self.context,self.plan,self.binding,[0],[0],{},artifact_cache=cache)
        self.assertEqual(result['status'],'UNAVAILABLE')

    def test_cache_refuses_every_binding_field_and_nested_coordinate_mutation(self):
        cache=_create_bound_body_cache(self.binding)
        modes=('profile_ref','geometry_ref','profile_file','geometry_file','profile_sha256','geometry_sha256',
               'source_sha256','pose_sha256','profile_cache_key','frame','canonical_geometry','native_body_origin',
               'collider_names','container-type','number-type','negative-zero')
        for mode in modes:
            binding=copy.deepcopy(self.binding)
            if mode in ('profile_ref','geometry_ref'):binding[mode]['sha256']='0'*64
            elif mode in ('profile_file','geometry_file'):binding[mode]+='.different'
            elif mode=='frame':binding['frame']['up'][0]=2.
            elif mode=='canonical_geometry':binding[mode]['vertices_cm'][0][0]=.1
            elif mode=='native_body_origin':binding[mode]['event_id']=2
            elif mode=='collider_names':binding[mode].append('extra')
            elif mode=='container-type':binding['canonical_geometry']['vertices_cm'][0]=tuple(binding['canonical_geometry']['vertices_cm'][0])
            elif mode=='number-type':binding['canonical_geometry']['face_sets'][0]=True
            elif mode=='negative-zero':binding['canonical_geometry']['vertices_cm'][0][0]=-0.
            else:binding[mode]='changed'
            with self.subTest(mode=mode),self.assertRaisesRegex(StudioError,'binding changed'):
                _bound_body_files(binding,artifact_cache=cache)

    def test_cache_mutation_even_bypassing_frozen_attributes_is_refused(self):
        for mode in ('snapshot','files','integrity'):
            cache=_create_bound_body_cache(self.binding)
            if mode=='snapshot':object.__setattr__(cache,'snapshot',('different',()))
            if mode=='files':object.__setattr__(cache,'files',())
            if mode=='integrity':object.__setattr__(cache,'files_sha256','0'*64)
            with self.subTest(mode=mode),self.assertRaisesRegex(StudioError,'artifact cache changed'):
                _bound_body_files(self.binding,artifact_cache=cache)
        with self.assertRaisesRegex(StudioError,'artifact cache changed'):
            _bound_body_files(self.binding,artifact_cache={})

    def test_cache_creation_never_skips_duplicate_or_nonfinite_initial_decode(self):
        for raw in (b'{"pose_sha256":"pose","pose_sha256":"pose"}',b'{"value":NaN}',b'{"value":1e999}'):
            binding=copy.deepcopy(self.binding);self.file.write_bytes(raw)
            binding['profile_ref']['sha256']=hashlib.sha256(raw).hexdigest()
            with self.subTest(raw=raw),self.assertRaisesRegex(StudioError,'duplicate|Nonfinite'):
                _create_bound_body_cache(binding)
        self.file.write_bytes(self.raw)

    def test_cached_body_geometry_mutated_between_or_during_measurements_is_refused(self):
        cache=_create_bound_body_cache(self.binding)
        with patch('blender.pattern_assembly.collision_check',return_value=self.signed()):
            result=measure_anchor_reserve(self.payload,self.points,self.context,self.plan,self.binding,[0],[0],{},artifact_cache=cache)
        self.assertEqual(result['status'],'MEASURED')
        self.actual['vertices_cm'][0][0]=1.
        with patch('blender.pattern_assembly.collision_check') as query:
            result=measure_anchor_reserve(self.payload,self.points,self.context,self.plan,self.binding,[0],[0],{},artifact_cache=cache)
        self.assertEqual(result['status'],'UNAVAILABLE');query.assert_not_called()
        self.actual['vertices_cm'][0][0]=0.
        def change(*args,**kwargs):
            self.actual['vertices_cm'][0][0]=1.;return self.signed()
        with patch('blender.pattern_assembly.collision_check',side_effect=change):
            result=measure_anchor_reserve(self.payload,self.points,self.context,self.plan,self.binding,[0],[0],{},artifact_cache=cache)
        self.assertEqual(result['status'],'UNAVAILABLE')

    def test_binding_mutation_during_cache_creation_is_refused(self):
        from blender.anchor_reserve import _read_bound_json
        def changed(*args,**kwargs):
            result=_read_bound_json(*args,**kwargs);self.binding['frame']['up'][0]=2.;return result
        with patch('blender.anchor_reserve._read_bound_json',side_effect=changed),self.assertRaisesRegex(StudioError,'binding changed during'):
            _create_bound_body_cache(self.binding)

    def test_initial_missing_or_changed_artifact_keeps_proposal_failure_semantics(self):
        actual_measure=measure_anchor_reserve
        def uncached(*args,**kwargs):
            kwargs.pop('artifact_cache_loader',None)
            return actual_measure(*args,**kwargs)
        for mode in ('missing-geometry','changed-profile'):
            self.file.write_bytes(self.raw);self.geometry_file.write_bytes(self.geometry_raw)
            if mode=='missing-geometry':self.geometry_file.unlink()
            else:self.file.write_bytes(self.raw.replace(b'pose',b'xxxx',1))
            args=(self.payload,self.points,self.context,{'pins':[]},self.plan,self.spec,self.binding,
                  self.quality,self.points,{'budgets':self.budgets,'protected_indices':[0]})
            with self.subTest(mode=mode),patch('blender.pattern_assembly.collision_check') as query:
                cached=propose_anchor_reserve(*args)
                with patch('blender.anchor_reserve.measure_anchor_reserve',side_effect=uncached):
                    original=propose_anchor_reserve(*args)
            query.assert_not_called()
            for result in (cached,original):
                self.assertEqual(result['status'],'NEEDS_MEASUREMENT')
                self.assertEqual(result['stop_reason'],'MEASUREMENT_UNAVAILABLE')
                self.assertEqual(result['coordinates_cm'],self.points)
                self.assertEqual(result['spent_budget']['measurement_calls'],1)
                self.assertEqual(result['qualification'],'NONE')
            for key in ('source_sha256','initial_candidate_sha256','candidate_sha256','translation_scalar_cm'):
                self.assertEqual(cached[key],original[key])
        self.file.write_bytes(self.raw);self.geometry_file.write_bytes(self.geometry_raw)

    def test_proposal_cache_is_created_only_once_inside_successful_measurements(self):
        def signed_points(coordinates,*args,**kwargs):return self.signed(offset=coordinates[0][0])
        with patch('blender.anchor_reserve._create_bound_body_cache',wraps=_create_bound_body_cache) as create,\
                patch('blender.pattern_assembly.collision_check',side_effect=signed_points):
            result=propose_anchor_reserve(self.payload,self.points,self.context,{'pins':[]},self.plan,self.spec,self.binding,
                self.quality,self.points,{'budgets':self.budgets,'protected_indices':[0]})
        self.assertEqual(result['status'],'ANCHORS_ADMISSIBLE_ONLY')
        self.assertGreater(result['spent_budget']['measurement_calls'],1)
        create.assert_called_once()


class SingleEvaluatedBodyCapture(unittest.TestCase):
    """Fake evaluated meshes prove capture identity, never native qualification."""
    def fixture(self):
        class Matrix:
            def __matmul__(self,point):return point
        mesh=SimpleNamespace(vertices=[SimpleNamespace(co=[0.,0.,0.]),SimpleNamespace(co=[1.,0.,0.]),
                                       SimpleNamespace(co=[1.,1.,0.]),SimpleNamespace(co=[0.,1.,0.])],
            polygons=[SimpleNamespace(vertices=[0,1,2,3])],
            loop_triangles=[SimpleNamespace(vertices=[0,1,2],polygon_index=0),
                            SimpleNamespace(vertices=[0,2,3],polygon_index=0)],
            attributes={' .unused':None,'.sculpt_face_set':SimpleNamespace(domain='FACE',data_type='INT',data=[SimpleNamespace(value=7)])},
            calc_loop_triangles=Mock())
        evaluated=SimpleNamespace(matrix_world=Matrix(),to_mesh=Mock(return_value=mesh),to_mesh_clear=Mock())
        obj=SimpleNamespace(name='fixture',evaluated_get=Mock(return_value=evaluated))
        return obj,evaluated,mesh

    def test_default_two_tuple_and_opt_in_contact_identity_equal_legacy_surface(self):
        from blender.body_target import evaluated_mesh
        from blender.cloth_contacts import _surface
        obj,evaluated,mesh=self.fixture()
        actual,triangles=evaluated_mesh(obj,object(),1.)
        self.assertEqual(len(evaluated_mesh(obj,object(),1.)),2)
        self.assertEqual(actual['faces'],[[0,1,2,3]]);self.assertEqual(actual['face_sets'],[7])
        evaluated.to_mesh.reset_mock();evaluated.to_mesh_clear.reset_mock();obj.evaluated_get.reset_mock()
        capture=evaluated_mesh(obj,object(),1.,include_contact_surface=True)
        self.assertEqual(capture[:2],(actual,triangles));self.assertEqual(capture[2],[0,0])
        self.assertEqual(capture[3],digest({'coords_cm':actual['vertices_cm'],'triangles':triangles,'polygons':[0,0]}))
        evaluated.to_mesh.assert_called_once();evaluated.to_mesh_clear.assert_called_once();obj.evaluated_get.assert_called_once()
        bpy=SimpleNamespace(context=SimpleNamespace(evaluated_depsgraph_get=lambda:object()))
        with patch.dict('sys.modules',{'bpy':bpy}):
            points,faces,polygons,identity=_surface(obj)
        self.assertEqual((points,faces,polygons,identity),(actual['vertices_cm'],triangles,capture[2],capture[3]))

    def test_opt_in_is_strict_and_mesh_is_released_on_capture_failure(self):
        from blender.body_target import evaluated_mesh
        obj,evaluated,mesh=self.fixture()
        with self.assertRaises(StudioError):evaluated_mesh(obj,object(),1.,include_contact_surface='true')
        obj.evaluated_get.assert_not_called()
        del mesh.attributes['.sculpt_face_set']
        with self.assertRaises(StudioError):evaluated_mesh(obj,object(),1.,include_contact_surface=True)
        evaluated.to_mesh_clear.assert_called_once()


if __name__=='__main__':unittest.main()
