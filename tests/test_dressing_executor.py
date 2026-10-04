"""Portable admission/schedule tests; fake origins are never native evidence."""
import copy
import math
from types import SimpleNamespace
from unittest.mock import patch

from a3d.core import StudioError,atomic_json,digest,read_json,sha,ROOT
from a3d.dressing_derivation import derive_dressing_contract
from a3d.dressing_paths import (_source_point,dressing_execution_descriptor,
                                generate_dressing_paths,source_grip_vertex,support_sample,_body_target)
from blender.dressing_executor import (apply_supports,endpoint_report,pin_weights,run_dressing_program,
                                      support_key_schedule,_curve_value,support_weight_schedule,_step_value,
                                      verify_support_weights,other_weights,verify_full_weight_grips,
                                      author_support_weights,verify_support_action)
from tests.test_core import Case
from tests.test_dressing_derivation import fixture,hood_yoke_fixture
from tests.support import ready_project


class DressingExecutor(Case):
    def setUp(self):
        super().setUp();self.project=ready_project(self.root)
        values=fixture();self.derived=derive_dressing_contract(*values);self.paths=generate_dressing_paths(self.derived)
        self.method='source.belt.wrap';self.cid='source.belt'
        self.refs={}
        def save(name,value):
            path=self.root/(name+'.json');atomic_json(path,value)
            ref={'path':path.name,'sha256':sha(path)};self.refs[name]=ref;return ref
        self.save=save
        source=self.derived['component_sources'][self.cid]
        points=[[0.,0.,50.],[10.,0.,50.],[10.,3.,50.],[0.,3.,50.]]
        self.candidate={'component_id':self.cid,'rest_cm':points,'placed_cm':copy.deepcopy(points),
            'faces':[[0,1,2],[0,2,3]],'panels':{'belt':{'indices':[0,1,2,3],
                'edges':{'bottom':[0,1],'right':[1,2],'top':[2,3],'left':[0,3]},
                'source_contour_sha256':source['source_piece_contours_sha256']['belt']}},
            'pins':{},'seams':{},'source_garment_sha256':source['source_garment_sha256'],
            'package_sha256':source['source_ref']['sha256'],
            'source_rest_triangles_cm':[[[points[i][0],points[i][1]] for i in f] for f in [[0,1,2],[0,2,3]]],
            'source_face_vertex_ids':[[0,1,2],[0,2,3]],'source_face_pieces':['belt','belt']}
        save('candidate',self.candidate);save('entry',self.candidate);save('paths',self.paths);save('paths-spec',{})
        recipe=read_json(ROOT/'templates/sewing-recipe.json');recipe['component_id']=self.cid
        save('recipe',recipe)
        self.instructions={'version':1,'paths_sha256':self.paths['paths_sha256'],'entry_candidate_ref':self.refs['entry'],
            'mount_order':[self.method],'mount_order_source_ref':save('order',{'mount_order':[self.method]}),
            'method_stages':[{'method_id':self.method,'start_frame':1,'end_frame':5}],
            'frame_end':5,'supports':[{'id':'source-grip','method_id':self.method,'start_frame':1,
                'piece':'belt','edge':'bottom','edge_vertex':0,'weight':1.,'release_frame':4,
                'waypoints':[{'frame':1,'source_ref':save('targets',{'entry':points[0],'last':points[0]}),'pointer':'/entry'},
                             {'frame':3,'source_ref':self.refs['targets'],'pointer':'/last'}]}],
            'endpoint_constraints':[{'method_id':self.method,'piece':'belt','edge':'bottom','edge_vertex':0,
                'source_ref':self.refs['targets'],'pointer':'/last','tolerance_cm':.01}]}
        save('instructions',self.instructions)
        self.body={'version':1,'status':'NATIVE_BODY_TARGET_MEASURED','native_reopened':True,
            'artifact':save('body-blend',{'SYNTHETIC':'NOT_A_BLEND'}),
            'artifacts':{'geometry':save('body-geometry',{}),'triangles':save('body-triangles',[])},
            'geometry_sha256':self.derived['body_geometry_sha256'],'pose_sha256':self.derived['body_pose_sha256']}
        self.body['cache_key']=digest(self.body);save('body-receipt',self.body)
        self.derived['policy']['bindings']['body_geometry_ref']=self.body['artifacts']['geometry']
        self.derived['policy']['bindings']['body_triangles_ref']=self.body['artifacts']['triangles']
        self.motion={'profile':{'component_id':self.cid,'purpose':'TEST_ONLY','bindings':{'candidate':self.refs['candidate'],'recipe':self.refs['recipe']}},
            'candidate':self.candidate,'recipe':recipe,'body_motion':{'body_target_receipt':self.refs['body-receipt']},
            'animated_colliders':[],'fit_context':None,'fit_intent':None}
        save('motion-profile',{})
        self.profile={'version':1,'id':'portable-source-dressing','component_id':self.cid,'purpose':'TEST_ONLY','method_ids':[self.method],
            'bindings':{'paths_spec_ref':self.refs['paths-spec'],'paths_ref':self.refs['paths'],
                        'instructions_ref':self.refs['instructions'],'motion_profile_ref':self.refs['motion-profile']},
            'execution':{'max_frames':5,'max_seconds':10.,'max_cache_vertex_frames':100000}}
        self.write_profile()

    def write_profile(self):self.save('execute',self.profile)

    def descriptor(self):
        native={'operation':'prepare_body_target','result':self.body,'files':[self.body['artifact'],*self.body['artifacts'].values()]}
        with patch('a3d.dressing_paths.dressing_paths_descriptor',return_value={'paths':self.paths,'derivation':self.derived,'evidence':[]}),\
             patch('a3d.garment_motion.motion_inputs',return_value=self.motion),\
             patch('a3d.garment_motion._native_origin',return_value=(native,{'SYNTHETIC':'PORTABLE_CONTRACT_ONLY'})):
            return dressing_execution_descriptor(self.project,'execute.json')

    def mutate_instructions(self,change):
        change(self.instructions);self.profile['bindings']['instructions_ref']=self.save('instructions',self.instructions);self.write_profile()

    def test_preparation_binds_exact_named_source_grips_without_mutating_sources(self):
        before=sha(self.project.db);original=digest(self.candidate);descriptor=self.descriptor()
        self.assertEqual(descriptor['status'],'DRESSING_INSTRUCTIONS_PREPARED')
        self.assertEqual(descriptor['supports'][0]['vertex'],0);self.assertEqual(descriptor['qualification'],'NONE')
        self.assertEqual(descriptor['simulation'],'NOT_EXECUTED')
        self.assertEqual(sha(self.project.db),before);self.assertEqual(digest(self.candidate),original)

    def test_missing_source_instructions_does_not_call_motion_or_create_native_scene(self):
        del self.profile['bindings']['instructions_ref'];self.write_profile();before=sha(self.project.db)
        with patch('a3d.dressing_paths.dressing_paths_descriptor',return_value={'paths':self.paths,'derivation':self.derived,'evidence':[]}),\
             patch('a3d.garment_motion.motion_inputs') as motion:
            result=run_dressing_program(str(self.root),'execute.json')
        motion.assert_not_called();self.assertEqual(result['status'],'NEEDS_DATA');self.assertFalse(result['native_scene_created'])
        self.assertEqual(result['simulation'],'NOT_EXECUTED');self.assertFalse(result['accepted']);self.assertEqual(sha(self.project.db),before)

    def test_hood_missing_mode_or_unresolved_skin_refuses_before_native_motion(self):
        for configured,height,reason in ((False,97.,'HOOD_YOKE_SOURCE_MODE_AND_OPEN_LINK_STATES_REQUIRED'),
                                         (True,110.,'HOOD_YOKE_MEASURED_REGION_UNRESOLVED')):
            self.derived=derive_dressing_contract(*hood_yoke_fixture(configured,height));self.paths=generate_dressing_paths(self.derived)
            method=next(row for row in self.derived['methods'] if row['method']=='OPEN_HOOD_YOKE')
            self.profile['component_id']=method['component_id'];self.profile['method_ids']=[method['id']]
            self.profile['bindings']['paths_ref']=self.save('paths',self.paths);self.write_profile()
            before=sha(self.project.db)
            with patch('a3d.dressing_paths.dressing_paths_descriptor',return_value={'paths':self.paths,'derivation':self.derived,'evidence':[]}),\
                    patch('a3d.garment_motion.motion_inputs') as motion:
                result=run_dressing_program(str(self.root),'execute.json')
            motion.assert_not_called();self.assertEqual(result['status'],'NEEDS_DATA')
            self.assertFalse(result['native_scene_created']);self.assertEqual(result['simulation'],'NOT_EXECUTED')
            self.assertIn(reason,{row['reason'] for row in result['diagnostics']});self.assertEqual(sha(self.project.db),before)

    def test_declared_open_hood_descriptor_preserves_configuration_and_refuses_grips_on_detached_lower_unit(self):
        values=hood_yoke_fixture(True)
        values[-1]['bindings']['body_geometry_ref']=self.body['artifacts']['geometry']
        values[-1]['bindings']['body_triangles_ref']=self.body['artifacts']['triangles']
        self.derived=derive_dressing_contract(*values);self.paths=generate_dressing_paths(self.derived)
        method=next(row for row in self.derived['methods'] if row['method']=='OPEN_HOOD_YOKE');cid=method['component_id']
        data=values[1][cid]['data'];identity=self.derived['component_sources'][cid]
        points=[];faces=[];panels={};source_uv=[];source_ids=[];owners=[]
        for pid,piece in sorted(data['pieces'].items()):
            offset=len(points);points.extend([[u,v,80.] for u,v in piece['vertices']])
            panels[pid]={'indices':list(range(offset,len(points))),
                         'edges':{name:[offset+i for i in chain] for name,chain in piece['edges'].items()},
                         'source_contour_sha256':identity['source_piece_contours_sha256'][pid]}
            for face in piece['faces']:
                faces.append([offset+i for i in face]);source_uv.append([piece['vertices'][i] for i in face]);source_ids.append([offset+i for i in face]);owners.append(pid)
        self.candidate={'component_id':cid,'rest_cm':points,'placed_cm':copy.deepcopy(points),'faces':faces,'panels':panels,
                        'pins':{},'seams':{},'source_rest_triangles_cm':source_uv,'source_face_vertex_ids':source_ids,'source_face_pieces':owners,
                        'source_garment_sha256':identity['source_garment_sha256'],'package_sha256':identity['source_ref']['sha256']}
        self.profile['component_id']=cid;self.profile['method_ids']=[method['id']]
        self.profile['bindings']['paths_ref']=self.save('paths',self.paths)
        self.motion['candidate']=self.candidate;self.motion['profile']['component_id']=cid
        self.motion['profile']['bindings']['candidate']=self.save('candidate',self.candidate)
        self.instructions['entry_candidate_ref']=self.save('entry',self.candidate);self.instructions['paths_sha256']=self.paths['paths_sha256']
        self.instructions['mount_order']=[method['id']]
        self.instructions['mount_order_source_ref']=self.save('order',{'mount_order':[method['id']]})
        self.instructions['method_stages'][0]['method_id']=method['id']
        grip=self.instructions['supports'][0];grip.update(method_id=method['id'],piece='hood-left',edge='face-free')
        target=points[panels['hood-left']['edges']['face-free'][0]]
        target_ref=self.save('targets',{'entry':target,'last':target})
        for waypoint in grip['waypoints']:waypoint['source_ref']=target_ref
        constraint=self.instructions['endpoint_constraints'][0]
        constraint.update(method_id=method['id'],piece='hood-left',edge='face-free',source_ref=target_ref)
        self.profile['bindings']['instructions_ref']=self.save('instructions',self.instructions);self.write_profile()
        # Pure descriptor preparation remains unqualified, with mocked native
        # origin explicitly limited to this portable contract test.
        descriptor=self.descriptor();self.assertEqual(descriptor['status'],'DRESSING_INSTRUCTIONS_PREPARED')
        self.assertEqual(descriptor['source_method_configurations'][method['id']]['mode'],'RAISED_OPEN_HOOD')
        self.assertEqual(descriptor['source_open_link_states'][method['id']],method['configuration']['source_link_states'])
        self.assertEqual(descriptor['qualification'],'NONE');self.assertEqual(descriptor['simulation'],'NOT_EXECUTED')
        for item in (grip,constraint):
            old=copy.deepcopy(item);item.update(piece='yoke-lower',edge='front-left')
            self.profile['bindings']['instructions_ref']=self.save('instructions',self.instructions);self.write_profile()
            with self.assertRaisesRegex(StudioError,'outside its exact permanent source unit'):self.descriptor()
            item.clear();item.update(old)
        self.profile['bindings']['instructions_ref']=self.save('instructions',self.instructions)

    def test_rewritten_source_controls_are_rejected_even_when_resigned(self):
        changed=copy.deepcopy(self.paths);changed['controls'][0]['clearance_cm']+=1.;changed.pop('paths_sha256');changed['paths_sha256']=digest(changed)
        self.profile['bindings']['paths_ref']=self.save('paths',changed);self.write_profile()
        with self.assertRaisesRegex(StudioError,'reconstructed'):self.descriptor()

    def test_source_package_and_cut_mismatch_refused_before_entry(self):
        self.motion['candidate']=copy.deepcopy(self.candidate);self.motion['candidate']['package_sha256']='b'*64
        with self.assertRaisesRegex(StudioError,'approved cut'):self.descriptor()
        self.motion['candidate']['package_sha256']=self.candidate['package_sha256'];self.motion['candidate']['panels']['belt']['source_contour_sha256']='c'*64
        with self.assertRaisesRegex(StudioError,'approved cut'):self.descriptor()

    def test_changed_entry_rest_or_topology_is_refused(self):
        changed=copy.deepcopy(self.candidate);changed['faces'][0].reverse();self.instructions['entry_candidate_ref']=self.save('entry',changed)
        self.mutate_instructions(lambda _:None)
        with self.assertRaisesRegex(StudioError,'immutable source'):self.descriptor()

    def test_support_cannot_release_functional_pin_or_use_unnamed_nearest_vertex(self):
        self.candidate['pins']={'0':.5}
        with self.assertRaisesRegex(StudioError,'functional source pin'):self.descriptor()
        self.candidate['pins']={};self.mutate_instructions(lambda value:value['supports'][0].update(edge='nearest'))
        with self.assertRaisesRegex(StudioError,'exact native named'):self.descriptor()

    def test_source_mount_intervals_require_actual_order_and_complete_coverage(self):
        self.mutate_instructions(lambda value:value['method_stages'][0].update(start_frame=2))
        with self.assertRaisesRegex(StudioError,'nonoverlapping frame coverage'):self.descriptor()

    def test_release_must_precede_stage_end_and_source_grab_covers_entry(self):
        self.mutate_instructions(lambda value:value['supports'][0].update(release_frame=5))
        with self.assertRaisesRegex(StudioError,'strictly ordered native frames'):self.descriptor()

    def test_body_target_geometry_binding_must_be_identical(self):
        self.derived['policy']['bindings']['body_triangles_ref']=self.refs['body-geometry']
        with self.assertRaisesRegex(StudioError,'measured source regions'):self.descriptor()

    def test_exact_native_introduction_retains_target_origin_and_source_bindings(self):
        body=copy.deepcopy(self.body)
        body['artifacts']['profile']=self.save('introduced-profile',{'cache_key':'source-profile-cache'})
        geometry={'vertices_cm':[[0.,0.,0.]],'faces':[[0,0,0]],'face_sets':[1]}
        body['artifacts']['geometry']=self.save('introduced-geometry',geometry)
        body['cache_key']=digest({k:v for k,v in body.items() if k!='cache_key'})
        ref=self.save('introduced-target-receipt',body)
        context_ref=self.save('body-context',{'body_target_receipt':ref})
        context={'context':{'body_target_receipt':ref},'context_ref':context_ref,'receipt':body,
            'profile':{'cache_key':'source-profile-cache'},'geometry':geometry,'binding_sha256':'exact-native-context',
            'evidence':[ref,context_ref,body['artifact'],*body['artifacts'].values()]}
        result={'status':'BODY_TARGET_INTRODUCED','binding_sha256':context['binding_sha256'],
            'profile_cache_key':context['profile']['cache_key'],'context':context_ref,'body_target_receipt':ref,
            'source_artifact':body['artifact'],'profile_ref':body['artifacts']['profile'],
            'geometry_ref':body['artifacts']['geometry'],'geometry_sha256':body['geometry_sha256'],
            'pose_sha256':body['pose_sha256'],'actual_geometry_sha256':digest(geometry)}
        native={'operation':'introduce_body_target','arguments':{'context_path':context_ref['path']},
                'result':result,'files':context['evidence']}
        origin={'event_id':'SYNTHETIC_PORTABLE_BINDING_TEST_ONLY'};before=sha(self.project.db)
        with patch('a3d.garment_motion._native_origin',return_value=(native,origin)) as authenticate,\
             patch('a3d.body_context.body_context_descriptor',return_value=context):
            measured,actual_origin,evidence=_body_target(self.project,ref)
        self.assertEqual(measured,body);self.assertEqual(actual_origin,origin);self.assertIn(context_ref,evidence)
        predicate=authenticate.call_args.args[1]
        self.assertTrue(predicate(native))
        self.assertFalse(predicate(dict(native,result=dict(result,body_target_receipt=self.refs['body-receipt']))))
        self.assertEqual(sha(self.project.db),before)
        for field in ('binding_sha256','source_artifact','profile_ref','geometry_ref','profile_cache_key',
                      'geometry_sha256','pose_sha256','actual_geometry_sha256','context','status'):
            changed=dict(native,result=dict(result,**{field:'wrong-source-binding'}))
            with self.subTest(field=field),\
                 patch('a3d.garment_motion._native_origin',return_value=(changed,origin)),\
                 patch('a3d.body_context.body_context_descriptor',return_value=context):
                with self.assertRaisesRegex(StudioError,'introduction differs'):_body_target(self.project,ref)
        changed=dict(native,files=[r for r in context['evidence'] if r!=ref])
        with patch('a3d.garment_motion._native_origin',return_value=(changed,origin)),\
             patch('a3d.body_context.body_context_descriptor',return_value=context):
            with self.assertRaisesRegex(StudioError,'absent from its canonical'):_body_target(self.project,ref)

    def test_copied_target_and_fake_introduction_file_do_not_create_native_origin(self):
        self.save('fake-introduction',{'operation':'introduce_body_target','status':'BODY_TARGET_INTRODUCED',
                                     'body_target_receipt':self.refs['body-receipt']})
        with self.assertRaisesRegex(StudioError,'canonical native run origin'):
            _body_target(self.project,self.refs['body-receipt'])

    def test_production_missing_classification_is_missing_data_before_native_motion(self):
        self.profile['purpose']='GARMENT_CANDIDATE';self.write_profile()
        descriptor=self.descriptor();self.assertEqual(descriptor['status'],'NEEDS_DATA')
        self.assertIn('EXPLICIT_SOURCE_BOUND_FIT_CLASSIFICATION_AND_EASE_REQUIRED',{row['reason'] for row in descriptor['diagnostics']})

    def test_json_pointer_is_finite_exact_and_never_python_index_or_expression(self):
        document={'a/b':{'~value':[[1.,2.,3.]]}}
        self.assertEqual(_source_point(document,'/a~1b/~0value/0'),[1.,2.,3.])
        for pointer in ('','/a~1b/~0value/-1','/a~1b/~0value/00','/a~1b/~0value/__import__','/a~3b'):
            with self.subTest(pointer=pointer),self.assertRaises(StudioError):_source_point(document,pointer)
        for value in (True,math.nan,math.inf):
            with self.assertRaises(StudioError):_source_point({'point':[value,2.,3.]},'/point')

    def test_support_is_inactive_before_stage_interpolates_then_actually_releases(self):
        support={'start_frame':2,'release_frame':5,'vertex':3,'weight':.7,
            'resolved_waypoints':[{'frame':2,'point_cm':[0.,0.,0.]},{'frame':4,'point_cm':[2.,4.,6.]}]}
        self.assertEqual(support_sample(support,1)['weight'],0.)
        middle=support_sample(support,3.);self.assertEqual(middle['point_cm'],[1.,2.,3.]);self.assertFalse(middle['released'])
        self.assertEqual(support_sample(support,5)['weight'],0.);self.assertTrue(support_sample(support,9)['released'])
        for time in (True,math.nan,math.inf):
            with self.assertRaises(StudioError):support_sample(support,time)

    def test_endpoint_scope_uses_actual_observed_coordinates_not_client_success(self):
        constraint={'method_id':self.method,'vertex':0,'point_cm':[0.,0.,0.],'tolerance_cm':.01}
        report=endpoint_report([[0.,0.,.02]],[constraint]);self.assertFalse(report['ok']);self.assertEqual(report['fitting'],'NOT_QUALIFIED')
        self.assertEqual(report['scope'],'DECLARED_SOURCE_ENDPOINTS_ONLY')

    def test_native_weight_schedule_changes_only_temporary_source_vertex(self):
        vertices=[SimpleNamespace(index=index,groups=[]) for index in range(3)]
        class Group:
            index=0
            def remove(_,ids):
                for index in ids:vertices[index].groups=[]
            def add(_,ids,weight,mode):
                for index in ids:vertices[index].groups=[SimpleNamespace(group=0,weight=weight)]
        group=Group();group.add([0],.6,'REPLACE')
        obj=SimpleNamespace(vertex_groups={'A3D.Pins':group},data=SimpleNamespace(vertices=vertices))
        target=SimpleNamespace(data=[SimpleNamespace(co=[0.,0.,0.]) for _ in vertices])
        support={'id':'grip','start_frame':1,'release_frame':4,'vertex':1,'weight':1.,
            'resolved_waypoints':[{'frame':1,'point_cm':[0.,0.,0.]},{'frame':3,'point_cm':[2.,0.,0.]}]}
        states,weights=apply_supports(obj,target,[support],2,{'0':.6})
        self.assertEqual(pin_weights(obj),{'0':.6,'1':1.});self.assertEqual(target.data[1].co,[.01,0.,0.])
        states,weights=apply_supports(obj,target,[support],4,{'0':.6})
        self.assertTrue(states[0]['released']);self.assertEqual(pin_weights(obj),{'0':.6});self.assertEqual(weights,{'0':.6})

    def test_native_fixture_sources_recompile_through_real_portable_pipeline(self):
        from tests.native_dressing_executor import _project,_source_controls
        project=_project(self.root/'fresh-source-fixture');directory=project.data/'dressing-inputs';directory.mkdir()
        _,_,profile,geometry,triangles,*_=fixture()
        artifacts={}
        for name,value in (('profile',profile),('geometry',geometry),('triangles',triangles)):
            path=directory/(name+'.json');atomic_json(path,value)
            artifacts[name]={'path':path.relative_to(project.root).as_posix(),'sha256':sha(path)}
        before=sha(project.db)
        data,package,recipe,paths,path_spec,path_ref,seed_ref,_=_source_controls(project,{'artifacts':artifacts},directory)
        self.assertEqual(data['component_id'],'garment.coat');self.assertEqual(set(data['pieces']),{'belt'})
        self.assertEqual(paths['controls'][0]['method'],'OPEN_WRAP')
        self.assertEqual(paths['controls'][0]['entry_configuration'],'MISSING')
        self.assertEqual(read_json(project.root/seed_ref['path'])['physical_passage'],'NOT_QUALIFIED')
        self.assertEqual(sha(project.db),before)

    def test_native_key_driver_interpolates_source_points_without_frame_data_edits(self):
        support={'start_frame':1,'release_frame':6,'vertex':0,'weight':1.,'resolved_waypoints':[
            {'frame':1,'point_cm':[0.,0.,0.]},{'frame':3,'point_cm':[.01,0.,0.]},{'frame':5,'point_cm':[.01,.02,0.]}]}
        schedules=[support_key_schedule(support,index,8) for index in range(3)]
        for frame in (1.,1.5,2.,3.,4.,5.,6.,8.):
            values=[_curve_value(row,frame) for row in schedules]
            observed=[sum(value*point['point_cm'][axis] for value,point in zip(values,support['resolved_waypoints'])) for axis in range(3)]
            self.assertAlmostEqual(sum(values),1.);self.assertEqual(observed,support_sample(support,frame)['point_cm'])
        later=dict(support,start_frame=3,release_frame=8,
            resolved_waypoints=[{'frame':3,'point_cm':[0.,0.,0.]},{'frame':7,'point_cm':[1.,0.,0.]}])
        self.assertTrue(all(_curve_value(support_key_schedule(later,index,9),1)==0. for index in range(2)))

    def test_weight_schedule_is_constant_with_exact_release_and_late_start(self):
        support={'start_frame':1,'release_frame':4,'weight':1.}
        schedule=support_weight_schedule(support,5)
        for frame in (1.,1.5,2.,3.,3.999999):self.assertEqual(_step_value(schedule,frame),1.)
        for frame in (4.,4.5,5.):self.assertEqual(_step_value(schedule,frame),0.)
        late=support_weight_schedule(dict(support,start_frame=3,release_frame=7,weight=.7),8)
        self.assertEqual(_step_value(late,2.999999),0.)
        self.assertEqual(_step_value(late,3.),.7);self.assertEqual(_step_value(late,7.),0.)

    def test_weight_action_is_explicitly_distinct_and_retains_source_linear_keys(self):
        # Synthetic Blender owners model auto-keying into an existing Action.
        # They establish isolation/refusal, never native dynamics or cache proof.
        source_curve=SimpleNamespace(extrapolation='CONSTANT',keyframe_points=[SimpleNamespace(interpolation='LINEAR')])
        source_action=SimpleNamespace(name='source-trajectory',curves=[source_curve])
        source_animation=SimpleNamespace(action=source_action,action_slot=SimpleNamespace(identifier='KEY.source',target_id_type='KEY'),
                                         drivers=[],nla_tracks=[])
        vertices=[SimpleNamespace(index=0,groups=[]),SimpleNamespace(index=1,groups=[SimpleNamespace(group=0,weight=.6)])]
        class Groups(list):
            def get(self,name):return next((group for group in self if group.name==name),None)
            def new(self,name):
                group=SimpleNamespace(index=len(self),name=name)
                def add(indices,weight,mode):
                    for index in indices:vertices[index].groups.append(SimpleNamespace(group=group.index,weight=weight))
                group.add=add;self.append(group);return group
        obj=SimpleNamespace(data=SimpleNamespace(vertices=vertices,shape_keys=SimpleNamespace(animation_data=source_animation)),
                            vertex_groups=Groups([SimpleNamespace(name='A3D.Pins',index=0)]),animation_data=None)
        obj.animation_data_create=lambda:setattr(obj,'animation_data',SimpleNamespace(action=None,action_slot=None,drivers=[],nla_tracks=[]))
        class Modifiers(list):
            def new(self,name,kind):
                modifier=SimpleNamespace(name=name,type=kind)
                def keyframe_insert(path,frame):
                    if obj.animation_data is None:obj.animation_data_create()
                    # The dangerous default shares the source Action; the
                    # implementation must select a new Action before keying.
                    if obj.animation_data.action is None:obj.animation_data.action=source_action
                    obj.animation_data.action_slot=SimpleNamespace(identifier='OBJECT.fixture',target_id_type='OBJECT')
                    obj.animation_data.action.curves.append(SimpleNamespace(extrapolation='CONSTANT',
                        keyframe_points=[SimpleNamespace(interpolation='BEZIER')]))
                modifier.keyframe_insert=keyframe_insert;self.append(modifier);return modifier
        obj.modifiers=Modifiers();created=[]
        def new_action(name):
            action=SimpleNamespace(name=name,curves=[]);created.append(action);return action
        def payload(action):
            return {'fixture':True,'curves':[[curve.extrapolation,[key.interpolation for key in curve.keyframe_points]]
                                           for curve in action.curves]}
        support={'id':'grip','vertex':0,'weight':1.,'start_frame':1,'release_frame':4}
        fake_bpy=SimpleNamespace(data=SimpleNamespace(actions=SimpleNamespace(new=new_action)))
        with patch.dict('sys.modules',{'bpy':fake_bpy}),patch('blender.body_motion._curves',side_effect=lambda action:action.curves),\
                patch('blender.body_motion.action_payload',side_effect=payload),patch('blender.garment_motion._key_rest',return_value='portable-source-rest'):
            before=digest(payload(source_action));driver=author_support_weights(obj,[support],5)
            self.assertEqual(len(created),1);self.assertIs(obj.animation_data.action,created[0])
            self.assertIsNot(obj.animation_data.action,source_action);self.assertEqual(digest(payload(source_action)),before)
            self.assertEqual(source_curve.keyframe_points[0].interpolation,'LINEAR')
            self.assertTrue(all(key.interpolation=='CONSTANT' for curve in created[0].curves for key in curve.keyframe_points))
            self.assertEqual(driver['slot_identifier'],'OBJECT.fixture');self.assertEqual(driver['raw_pin_weights'],{'1':.6})
            with self.assertRaisesRegex(StudioError,'unanimated temporary Object owner'):author_support_weights(obj,[support],5)

    def test_source_trajectory_identity_refusal_reports_exact_mismatch(self):
        key=SimpleNamespace(value=.5);payload={'SYNTHETIC_PORTABLE_ACTION_ONLY':True}
        action=SimpleNamespace(name='actual-key-action')
        animation=SimpleNamespace(action=action,action_slot=SimpleNamespace(identifier='KEY.actual',target_id_type='KEY'),drivers=[],nla_tracks=[])
        obj=SimpleNamespace(data=SimpleNamespace(shape_keys=SimpleNamespace(animation_data=animation,key_blocks={'key':key})))
        driver={'action_name':action.name,'slot_identifier':'KEY.expected','action_sha256':digest(payload),
                'source_key_geometry_sha256':'source-rest','keys':[{'key_name':'key','schedule':[(1,0.),(3,1.)]}]}
        with patch('blender.body_motion.action_payload',return_value=payload),patch('blender.garment_motion._key_rest',return_value='source-rest'):
            with self.assertRaisesRegex(StudioError,'native slot changed') as failure:verify_support_action(obj,driver,2)
            self.assertEqual(failure.exception.details,{'source_trajectory_identity_mismatches':{
                'slot_identifier':{'expected':'KEY.expected','actual':'KEY.actual'}}})
            driver['slot_identifier']='KEY.actual';self.assertEqual(verify_support_action(obj,driver,2),[{'key_name':'key','value':.5}])
            animation.drivers=['unsupported'];key.value=.75
            with self.assertRaises(StudioError) as failure:verify_support_action(obj,driver,2)
            self.assertIn('drivers',failure.exception.details['source_trajectory_identity_mismatches'])

    def test_evaluated_weight_schedule_observation_never_edits_source_groups(self):
        source_vertices=[SimpleNamespace(index=0,groups=[]),
            SimpleNamespace(index=1,groups=[SimpleNamespace(group=0,weight=.6)])]
        groups={'A3D.Pins':SimpleNamespace(index=0), 'source-mask':SimpleNamespace(index=1)}
        source_vertices[0].groups=[SimpleNamespace(group=1,weight=1.)]
        class Groups:
            def get(_,name):return groups.get(name)
            def __iter__(_):
                return iter([SimpleNamespace(name=name,index=value.index) for name,value in groups.items()])
        modifier=SimpleNamespace(name='source-weight',type='VERTEX_WEIGHT_MIX',show_viewport=True,show_render=True,
            vertex_group_a='A3D.Pins',vertex_group_b='source-mask',mix_mode='SET',mix_set='B',
            default_weight_a=0.,default_weight_b=0.,normalize=False,invert_vertex_group_a=False,
            invert_vertex_group_b=False,mask_vertex_group='',mask_texture=None,mask_constant=1.)
        class Modifiers(list):
            def get(self,name):return next((m for m in self if m.name==name),None)
        animation=SimpleNamespace(drivers=[],nla_tracks=[],action=object(),action_slot=SimpleNamespace(identifier='fixture-slot'))
        evaluated_vertices=[SimpleNamespace(index=0,groups=[SimpleNamespace(group=0,weight=1.)]),
                            SimpleNamespace(index=1,groups=[SimpleNamespace(group=0,weight=.6)])]
        obj=SimpleNamespace(vertex_groups=Groups(),data=SimpleNamespace(vertices=source_vertices),
            animation_data=animation,modifiers=Modifiers([modifier,SimpleNamespace(type='CLOTH')]),
            evaluated_get=lambda graph:SimpleNamespace(data=SimpleNamespace(vertices=evaluated_vertices)))
        support={'id':'grip','start_frame':1,'release_frame':4,'weight':1.,'vertex':0,
            'resolved_waypoints':[{'frame':1,'point_cm':[0.,0.,0.]},{'frame':3,'point_cm':[.01,0.,0.]}]}
        record={'support_id':'grip','vertex':0,'mask_group':'source-mask','modifier_name':'source-weight',
                'schedule':support_weight_schedule(support,5)}
        payload={'SYNTHETIC_PORTABLE_ACTION_ONLY':True}
        driver={'slot_identifier':'fixture-slot','action_sha256':digest(payload),'raw_pin_weights':pin_weights(obj),
            'non_pin_groups_sha256':other_weights(obj),'records':[record]}
        fake_bpy=SimpleNamespace(context=SimpleNamespace(evaluated_depsgraph_get=lambda:object()))
        with patch.dict('sys.modules',{'bpy':fake_bpy}),patch('blender.body_motion.action_payload',return_value=payload):
            snapshot=lambda:digest([[v.index,[(g.group,g.weight) for g in v.groups]] for v in source_vertices])
            before=snapshot()
            states,actual,records=verify_support_weights(obj,driver,[support],3,{'1':.6})
            self.assertEqual(actual,{'0':1.,'1':.6});self.assertEqual(states[0]['point_cm'],[.01,0.,0.])
            modifier.mask_constant=0.;evaluated_vertices[0].groups=[]
            states,actual,records=verify_support_weights(obj,driver,[support],4,{'1':.6})
            self.assertEqual(actual,{'1':.6});self.assertTrue(states[0]['released'])
            self.assertEqual(snapshot(),before)
            modifier.mask_constant=.1
            with self.assertRaisesRegex(StudioError,'sourced step schedule'):
                verify_support_weights(obj,driver,[support],4,{'1':.6})

    def test_full_weight_observation_retains_fixed_native_precision_refusal(self):
        from blender.garment_motion import _Stopped
        states=[{'id':'grip','vertex':0,'point_cm':[0.,0.,0.],'weight':1.}]
        self.assertLess(verify_full_weight_grips([[.000999,0.,0.]],states)[0]['error_cm'],.001)
        with self.assertRaises(_Stopped) as failure:verify_full_weight_grips([[.001001,0.,0.]],states)
        self.assertEqual(failure.exception.status,'NEEDS_CORRECTION')
        self.assertEqual(failure.exception.reason,'DRESSING_NATIVE_FULL_WEIGHT_GRIP_TARGET_MISMATCH')
        self.assertEqual(verify_full_weight_grips([[.1,0.,0.]],[dict(states[0],weight=0.)]),[])

    def test_failure_diagnostic_requires_exact_registered_failed_attempt(self):
        import json
        from tests.native_dressing_driver_diagnostic import historical_failure
        failed={'purpose':'TEST_ONLY','status':'NEEDS_CORRECTION',
                'stopped':{'reason':'DRESSING_NATIVE_FULL_WEIGHT_GRIP_TARGET_MISMATCH'},'qualification':'NONE'}
        failed_ref=self.save('actual-failure',failed)
        profile_path='fixture-execution.json';attempt_id='diagnostic.failed-attempt';run_id='diagnostic.run'
        wrapper={'origin':'NATIVE_DISPATCH','execution':'RETURNED','operation':'run_dressing_program',
            'arguments':{'profile_path':profile_path},'run_id':run_id,'unit_id':'native','attempt_id':attempt_id,
            'binding_sha256':'source-bound-diagnostic-fixture','result':dict(failed,receipt=failed_ref),'files':[failed_ref]}
        wrapper_ref=self.save('actual-dispatch',wrapper)
        event={'run_id':run_id,'unit_id':'native','attempt_id':attempt_id,
               'binding_sha256':wrapper['binding_sha256'],'receipt':wrapper_ref}
        attempt={'id':attempt_id,'status':'NEEDS_CORRECTION','operation':wrapper['operation'],
                 'arguments':wrapper['arguments'],'receipt':wrapper_ref,'binding_sha256':wrapper['binding_sha256']}
        with self.project.transaction() as db:
            db.execute('CREATE TABLE runs (id TEXT PRIMARY KEY,doc TEXT NOT NULL)')
            cursor=db.execute('INSERT INTO events(created_at,kind,doc) VALUES (?,?,?)',
                              ('PORTABLE_FIXTURE_ONLY','run_native_receipt',json.dumps(event)))
            attempt['receipt_event_id']=cursor.lastrowid
            unit={'id':'native','status':'NEEDS_CORRECTION','attempts':[attempt]};run={'units':[unit]}
            db.execute('INSERT INTO runs(id,doc) VALUES (?,?)',(run_id,json.dumps(run)))
        before=sha(self.project.db)
        receipt,native,origin=historical_failure(self.project,profile_path,failed_ref['path'])
        self.assertEqual(receipt,failed);self.assertEqual(native,wrapper)
        self.assertEqual(origin['scope'],'HISTORICAL_FAILED_DIAGNOSTIC_ONLY');self.assertEqual(sha(self.project.db),before)
        with self.assertRaisesRegex(StudioError,'exact canonical failed attempt'):
            historical_failure(self.project,'another-profile.json',failed_ref['path'])
        unit['status']='COMPLETED'
        with self.project.transaction() as db:db.execute('UPDATE runs SET doc=? WHERE id=?',(json.dumps(run),run_id))
        with self.assertRaisesRegex(StudioError,'exact canonical failed attempt'):
            historical_failure(self.project,profile_path,failed_ref['path'])
        with self.project.transaction() as db:db.execute("DELETE FROM events WHERE kind='run_native_receipt'")
        with self.assertRaisesRegex(StudioError,'without its canonical failed dispatch'):
            historical_failure(self.project,profile_path,failed_ref['path'])
