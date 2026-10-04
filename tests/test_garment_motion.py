"""Portable admission/crossing tests; synthetic receipts never qualify a body."""
import copy
import json
import tempfile
import unittest
from pathlib import Path
from unittest.mock import patch
from types import SimpleNamespace

from a3d.core import ROOT, StudioError, atomic_json, canonical, contract, digest, now, read_json, sha
from a3d.garment_motion import (_native_origin, canonical_body_motion, checked_reference,
                              animated_continuity, canonical_composed_clip, canonical_garment_clip,
                              garment_physics_modules, clip_coverage, collider_inputs, interval_subdivisions, motion_inputs, validate_candidate)
from a3d.store import Project
from blender.moving_contacts import interpolate, swept_crossing
from blender.sewing import grid_probe, mesh_recipe_digest
from tests.support import asset


def synthetic_candidate(recipe):
    payload=grid_probe(5.)
    uv=copy.deepcopy(payload['rest_cm'])
    payload['placed_cm']=[[x+150,y,z+100] for x,y,z in payload['placed_cm']]
    payload.update(version=2,component_id=recipe['component_id'],synthetic=True,rest_mode='assembled_3d',
        rest_cm=copy.deepcopy(payload['placed_cm']),recipe_mesh_sha256=mesh_recipe_digest(recipe),
        source_rest_triangles_cm=[[uv[i][:2] for i in face] for face in payload['faces']],
        source_face_vertex_ids=copy.deepcopy(payload['faces']),source_face_pieces=['synthetic-0']*len(payload['faces']),
        pattern_assembly={'temporary_supports_active':False})
    payload['pins']={str(i):1. for i in (0,1,2)}
    return payload


def motion_profile(bindings, max_frames=5):
    return {'version':1,'id':'synthetic-cloth-clip','component_id':'garment.coat','purpose':'TEST_ONLY',
        'phase':'drape','bindings':copy.deepcopy(bindings),
        'body_collision':{'outer_thickness_cm':.01,'inner_thickness_cm':.01},
        'execution':{'max_frames':max_frames,'max_seconds':120.,'max_step_cm':1.,
                     'min_substeps':2,'max_subdivisions':128,'max_pairs':200000,'max_cache_vertex_frames':1000000}}


class GarmentMotion(unittest.TestCase):
    def test_coupon_continuity_cannot_admit_production_execution(self):
        from a3d.garment_motion import require_production_continuity
        verified={'status':'COMPONENT_CONTINUITY_VERIFIED','purpose':'GARMENT_CANDIDATE',
            'native_root_scope':'COMPLETED_GROUP_DRAPE_PHYSICS_ONLY','native_group_receipts':[
                {'group_id':'inner','scope':'GROUP_DRAPE_PHYSICS_ONLY','purpose':'GARMENT_CANDIDATE'},
                {'group_id':'outer','scope':'GROUP_DRAPE_PHYSICS_ONLY','purpose':'GARMENT_CANDIDATE'}]}
        before=digest(verified);self.assertIsNone(require_production_continuity(verified));self.assertEqual(digest(verified),before)
        for change in ('test-program','test-root','absent-root','no-roots','duplicate-root','wrong-scope'):
            bad=copy.deepcopy(verified)
            if change=='test-program':bad['purpose']='TEST_ONLY'
            if change=='test-root':bad['native_group_receipts'][0]['purpose']='TEST_ONLY'
            if change=='absent-root':bad['native_group_receipts'][0].pop('purpose')
            if change=='no-roots':bad['native_group_receipts']=[]
            if change=='duplicate-root':bad['native_group_receipts'][1]['group_id']='inner'
            if change=='wrong-scope':bad['native_group_receipts'][0]['scope']='PASS'
            with self.subTest(change=change),self.assertRaisesRegex(StudioError,'TEST_ONLY continuity is insufficient'):
                require_production_continuity(bad)

    def test_animated_production_continuity_uses_actual_shared_source_unions(self):
        from tests.test_textile_executor import TextileExecutor
        from a3d.textile_executor import verify_component_continuity
        source,payload,groups=TextileExecutor().sewn_component_continuity_fixture()
        verified=verify_component_continuity(source,payload,groups,.01)
        coords=[[x,y,z+1] for x,y,z in payload['placed_cm']]
        before=digest(payload)
        report=animated_continuity(payload,coords,payload['faces'],verified)
        self.assertEqual(report['status'],'ANIMATED_SOURCE_CONTINUITY_VERIFIED')
        self.assertEqual(report['permanent_pair_count'],2)
        self.assertEqual(report['qualification'],'GEOMETRY_ONLY')
        self.assertTrue(report['current_physics_validation_required'])
        self.assertEqual(before,digest(payload))
        for change in ('proof','map','topology','nonfinite','source-pair'):
            candidate=copy.deepcopy(payload);native=copy.deepcopy(verified);points=copy.deepcopy(coords);faces=copy.deepcopy(payload['faces'])
            if change=='proof':native['status']='PASS'
            if change=='map':candidate['source_vertex_cohorts']['0'].append(999)
            if change=='topology':faces[0].reverse()
            if change=='nonfinite':points[0][0]=float('nan')
            if change=='source-pair':
                seam=next(row for row in candidate['seams'].values() if row['kind']=='permanent')
                seam['pairs'][0][1]=(seam['pairs'][0][0]+1)%len(points)
            with self.subTest(change=change),self.assertRaises(StudioError):
                animated_continuity(candidate,points,faces,native)

    def setUp(self):
        folder=ROOT/'work/test-garment-motion'; folder.mkdir(parents=True,exist_ok=True)
        self.temp=tempfile.TemporaryDirectory(dir=folder); self.root=Path(self.temp.name)
        self.project=Project.create(self.root,asset(True))
        self.recipe=read_json(ROOT/'templates/sewing-recipe.json'); self.candidate=synthetic_candidate(self.recipe)
        self.bindings={}
        for name,value in [('recipe',self.recipe),('candidate',self.candidate),('body_motion_receipt',{'status':'PASS'})]:
            path=self.root/(name+'.json'); atomic_json(path,value)
            self.bindings[name]={'path':path.name,'sha256':sha(path)}
        self.profile=motion_profile(self.bindings); atomic_json(self.root/'motion.json',self.profile)

    def tearDown(self): self.temp.cleanup()

    def native_fixture(self, operation='prepare_body_motion', result=None):
        # A deliberately synthetic DB fixture tests canonical consistency only.
        arguments={'fixture':'SYNTHETIC_NOT_NATIVE_QUALIFICATION'}
        receipt={'origin':'NATIVE_DISPATCH','execution':'RETURNED','operation':operation,'arguments':arguments,
            'run_id':'test','unit_id':'body','attempt_id':'try1','binding_sha256':'a'*64,'files':[],
            'result':result or {'receipt':self.bindings['body_motion_receipt']}}
        def collect(value):
            if isinstance(value,dict):
                if set(value)=={'path','sha256'}:
                    if value not in receipt['files']:receipt['files'].append(copy.deepcopy(value))
                else:
                    for child in value.values():collect(child)
            elif isinstance(value,list):
                for child in value:collect(child)
        collect(receipt['result'])
        path=self.root/'canonical.json'; atomic_json(path,receipt); ref={'path':path.name,'sha256':sha(path)}
        event={key:receipt[key] for key in ('run_id','unit_id','attempt_id','binding_sha256')}; event['receipt']=ref
        attempt={'id':'try1','status':'COMPLETED','operation':operation,'arguments':arguments,
                 'binding_sha256':'a'*64,'receipt':ref}
        with self.project.transaction() as db:
            db.execute('CREATE TABLE IF NOT EXISTS runs (id TEXT PRIMARY KEY, request_key TEXT UNIQUE NOT NULL, doc TEXT NOT NULL)')
            cursor=db.execute('INSERT INTO events(created_at,kind,doc) VALUES(?,?,?)',(now(),'run_native_receipt',canonical(event).decode()))
            attempt['receipt_event_id']=cursor.lastrowid
            run={'units':[{'id':'body','status':'COMPLETED','attempts':[attempt]}]}
            db.execute('INSERT OR REPLACE INTO runs(id,request_key,doc) VALUES(?,?,?)',('test','fixture',json.dumps(run)))
        return receipt,path,ref

    def test_user_pass_file_cannot_admit_body_and_read_does_not_migrate_database(self):
        before=sha(self.project.db)
        with self.assertRaisesRegex(StudioError,'canonical native run origin'):
            canonical_body_motion(self.project,self.bindings['body_motion_receipt'])
        self.assertEqual(sha(self.project.db),before)
        self.project.evidence('body-pass',self.bindings['body_motion_receipt']['path'])
        with self.assertRaises(StudioError): motion_inputs(self.project,'motion.json')

    def test_receipt_requires_matching_completed_attempt_and_unchanged_files(self):
        receipt,path,ref=self.native_fixture(); before=sha(self.project.db)
        loaded,origin=_native_origin(self.project,lambda row:row['operation']=='prepare_body_motion')
        self.assertEqual(loaded,receipt); self.assertEqual(origin['receipt'],ref); self.assertEqual(sha(self.project.db),before)
        with self.project.transaction() as db:
            doc=json.loads(db.execute('SELECT doc FROM runs').fetchone()[0]); doc['units'][0]['status']='WAITING_RESULT'
            db.execute('UPDATE runs SET doc=?',(json.dumps(doc),))
        with self.assertRaisesRegex(StudioError,'canonical completed attempt'):
            _native_origin(self.project,lambda row:True)
        path.write_text('{}')
        with self.assertRaisesRegex(StudioError,'file alone'):_native_origin(self.project,lambda row:True)

    def test_native_body_receipt_hash_and_current_code_are_bound(self):
        motion={'status':'CLIP_SAMPLES_COMPLETE'}
        for name in ('artifact','samples_artifact','rig_artifact','motion_profile','body_target_receipt'):
            path=self.root/(name+'.json'); atomic_json(path,{'fixture':name})
            motion[name]={'path':path.name,'sha256':sha(path)}
        motion['cache_key']=digest(motion); atomic_json(self.root/'body_motion_receipt.json',motion)
        ref={'path':'body_motion_receipt.json','sha256':sha(self.root/'body_motion_receipt.json')}
        runtime={'loaded_modules':{module:sha(ROOT/(module.replace('.','/')+'.py'))
            for module in ('blender.body_motion','blender.mannequin_rig','a3d.motion_profiles','a3d.mannequin_rig')}}
        receipt,path,_=self.native_fixture(result=dict(motion,receipt=ref,runtime=runtime))
        actual,_=canonical_body_motion(self.project,ref); self.assertEqual(actual,motion)
        with patch('a3d.garment_motion.sha',side_effect=lambda p:'f'*64 if str(p).endswith('motion_profiles.py') else sha(p)):
            with self.assertRaisesRegex(StudioError,'implementation changed'):canonical_body_motion(self.project,ref)

    def test_production_garment_receipt_binds_physics_not_shared_dispatcher(self):
        production=dict(self.profile,purpose='GARMENT_CANDIDATE')
        atomic_json(self.root/'motion.json',production)
        result={'status':'GARMENT_CLIP_SAMPLES_COMPLETE','coverage':{'clip_complete':True},
                'cache_reopened':{'status':'REOPENED_OBSERVED_GEOMETRY_MATCHES'},
                'profile':{'path':'motion.json','sha256':sha(self.root/'motion.json')}}
        for name in ('artifact','observations_artifact'):
            path=self.root/(name+'.json');atomic_json(path,{'fixture':'NOT_NATIVE','kind':name})
            result[name]={'path':path.name,'sha256':sha(path)}
        result['cache_key']=digest(result);atomic_json(self.root/'leaf.json',result)
        ref={'path':'leaf.json','sha256':sha(self.root/'leaf.json')}
        runtime={'loaded_modules':{module:sha(ROOT/(module.replace('.','/')+'.py'))
                                  for module in garment_physics_modules(production)}}
        self.native_fixture(operation='run_garment_motion',result=dict(result,receipt=ref,runtime=runtime))
        self.assertEqual(canonical_garment_clip(self.project,ref)[0],result)
        for handler in ('moving_contacts.py','cloth_metrics.py','textile_executor.py','body_target.py'):
            with patch('a3d.garment_motion.sha',side_effect=lambda path:'f'*64 if str(path).endswith(handler) else sha(path)):
                with self.subTest(handler=handler),self.assertRaisesRegex(StudioError,'physical implementation changed'):
                    canonical_garment_clip(self.project,ref)
        with patch('a3d.garment_motion.sha',side_effect=lambda path:'f'*64 if str(path).endswith(('runs.py','guard.py','operations.py')) else sha(path)):
            self.assertEqual(canonical_garment_clip(self.project,ref)[0],result)
        runtime['loaded_modules'].pop('blender.moving_contacts')
        self.native_fixture(operation='run_garment_motion',result=dict(result,receipt=ref,runtime=runtime))
        with self.assertRaisesRegex(StudioError,'physical implementation changed'):
            canonical_garment_clip(self.project,ref)
        self.assertNotIn('a3d.simulation_control',garment_physics_modules(production))
        self.assertIn('a3d.simulation_control',garment_physics_modules(dict(production,terminal_relax={'max_frames':1})))

    def test_test_only_leaf_transport_does_not_require_current_physical_handlers(self):
        result={'status':'GARMENT_CLIP_SAMPLES_COMPLETE','coverage':{'clip_complete':True},
                'cache_reopened':{'status':'REOPENED_OBSERVED_GEOMETRY_MATCHES'},
                'profile':{'path':'motion.json','sha256':sha(self.root/'motion.json')}}
        for name in ('artifact','observations_artifact'):
            path=self.root/(name+'.json');atomic_json(path,{'fixture':'NOT_NATIVE','kind':name})
            result[name]={'path':path.name,'sha256':sha(path)}
        result['cache_key']=digest(result);atomic_json(self.root/'leaf.json',result)
        ref={'path':'leaf.json','sha256':sha(self.root/'leaf.json')}
        self.native_fixture(operation='run_garment_motion',result=dict(result,receipt=ref,runtime={'loaded_modules':{}}))
        self.assertEqual(canonical_garment_clip(self.project,ref)[0],result)
        (self.root/'observations_artifact.json').write_text('{}')
        with self.assertRaises(StudioError):canonical_garment_clip(self.project,ref)

    def test_immutable_source_uv_rest_mapping_and_support_admission(self):
        before=digest(self.candidate); validated=validate_candidate(self.candidate,self.recipe)
        self.assertEqual(digest(self.candidate),before); self.assertEqual(validated['vertices'],9)
        for failure in ('supports','tacks','rest','uv','topology','mesh','nan','bool'):
            bad=copy.deepcopy(self.candidate)
            if failure=='supports':bad['pattern_assembly']['temporary_supports_active']=True
            if failure=='tacks':bad['fitting_tacks']=[{'fixture':'temporary'}]
            if failure=='rest':bad['rest_mode']='flat'
            if failure=='uv':bad.pop('source_rest_triangles_cm')
            if failure=='topology':bad['faces'][0][0]=bad['faces'][0][1]
            if failure=='mesh':bad['recipe_mesh_sha256']='0'*64
            if failure=='nan':bad['placed_cm'][0][0]=float('nan')
            if failure=='bool':bad['placed_cm'][0][0]=True
            with self.subTest(failure=failure),self.assertRaises(StudioError):validate_candidate(bad,self.recipe)

    def test_profile_budgets_explicit_thickness_and_numeric_types(self):
        contract('garment-motion',self.profile)
        for failure in ('bool','nan','missing','phase','thickness'):
            bad=copy.deepcopy(self.profile)
            if failure=='bool':bad['execution']['max_frames']=True
            if failure=='nan':bad['execution']['max_seconds']=float('nan')
            if failure=='missing':bad['execution'].pop('max_cache_vertex_frames')
            if failure=='phase':bad['phase']='relax'
            if failure=='thickness':bad['body_collision']['outer_thickness_cm']=-.1
            with self.subTest(failure=failure),self.assertRaises(StudioError):contract('garment-motion',bad)
        bad=copy.deepcopy(self.profile); bad.pop('body_collision'); atomic_json(self.root/'missing-thickness.json',bad)
        with self.assertRaisesRegex(StudioError,'explicit body collision'):motion_inputs(self.project,'missing-thickness.json')

    def test_production_requires_exact_reviewed_fit_context_before_body_or_mutation(self):
        profile=dict(self.profile,purpose='GARMENT_CANDIDATE')
        atomic_json(self.root/'production.json',profile);before=sha(self.project.db)
        with patch('a3d.garment_motion.canonical_body_motion') as body,self.assertRaisesRegex(StudioError,'fit_context'):
            motion_inputs(self.project,'production.json')
        body.assert_not_called();self.assertEqual(sha(self.project.db),before)
        profile['fit_context']={'compiled_dossier_ref':self.bindings['candidate'],'fit_profile_ref':self.bindings['recipe']}
        atomic_json(self.root/'production.json',profile)
        with patch('a3d.garment_fit.require_fit_intent',side_effect=StudioError('Exact numeric review missing')) as fit:
            with self.assertRaisesRegex(StudioError,'numeric review missing'):motion_inputs(self.project,'production.json')
        fit.assert_called_once_with(self.project,self.bindings['candidate']['path'],self.bindings['recipe']['path'])

    def test_production_review_cannot_cover_another_component_implicitly(self):
        fit_path=self.root/'other-component-fit.json';atomic_json(fit_path,{'component_ids':['garment.hood']})
        profile=dict(self.profile,purpose='GARMENT_CANDIDATE',fit_context={
            'compiled_dossier_ref':self.bindings['candidate'],
            'fit_profile_ref':{'path':fit_path.name,'sha256':sha(fit_path)}})
        atomic_json(self.root/'production.json',profile)
        with patch('a3d.garment_fit.require_fit_intent',return_value={'admission':'EXPLORATORY_PHYSICS_ONLY'}),\
                patch('a3d.garment_motion.canonical_body_motion') as body:
            with self.assertRaisesRegex(StudioError,'absent from the exact reviewed fit intent'):
                motion_inputs(self.project,'production.json')
        body.assert_not_called()

    def test_component_list_without_component_measurements_cannot_admit_motion(self):
        fit_path=self.root/'listed-unmeasured-component-fit.json'
        atomic_json(fit_path,{'component_ids':[self.profile['component_id'],'garment.hood']})
        profile=dict(self.profile,purpose='GARMENT_CANDIDATE',fit_context={
            'compiled_dossier_ref':self.bindings['candidate'],
            'fit_profile_ref':{'path':fit_path.name,'sha256':sha(fit_path)}})
        atomic_json(self.root/'production.json',profile);before=sha(self.project.db)
        with patch('a3d.garment_fit.require_fit_intent',return_value={
                'admission':'EXPLORATORY_PHYSICS_ONLY','checks':[{'component_id':'garment.hood'}]}),\
                patch('a3d.garment_motion.canonical_body_motion') as body,\
                patch('a3d.planning.require_board') as board:
            with self.assertRaisesRegex(StudioError,'no measured checks'):
                motion_inputs(self.project,'production.json')
        body.assert_not_called();board.assert_not_called();self.assertEqual(sha(self.project.db),before)

    def test_complete_clip_needs_every_frame_budgets_do_not_turn_partial_into_pass(self):
        body={'frame_start':1,'frame_end':5}
        partial=clip_coverage(body,[1,2],{'reason':'FRAME_BUDGET'})
        self.assertEqual(partial['status'],'INCOMPLETE'); self.assertFalse(partial['clip_complete'])
        complete=clip_coverage(body,[1,2,3,4,5]); self.assertEqual(complete['status'],'GARMENT_CLIP_SAMPLES_COMPLETE')
        self.assertFalse(complete['accepted']); self.assertEqual(complete['fitting'],'NOT_QUALIFIED')
        self.assertEqual(complete['continuous_collision_qualification'],'NOT_GRANTED')
        self.assertEqual(clip_coverage(body,[1,2,3,4,5],{'reason':'CACHE_BUDGET'})['status'],'INCOMPLETE')
        for bad in ([1,3],[2],[1,2,3,4,5,6]):
            with self.assertRaises(StudioError):clip_coverage(body,bad)

    def test_sampling_covers_declared_body_times_and_refuses_insufficient_budget(self):
        before=[[0.,0.,0.]]; after=[[.7,0.,0.]]; body_after=[[.8,0.,0.]]
        report=interval_subdivisions(before,after,before,body_after,self.profile['execution'],3)
        self.assertEqual(report['subdivisions'],3); self.assertEqual(report['status'],'READY')
        budget=dict(self.profile['execution'],max_subdivisions=2)
        self.assertEqual(interval_subdivisions(before,after,before,body_after,budget,3)['status'],'INCOMPLETE')
        for bad in (True,0):
            with self.assertRaises(StudioError):interval_subdivisions(before,after,before,body_after,budget,bad)

    def test_references_cannot_be_retargeted_or_supplied_as_unbound_paths(self):
        for bad in ('candidate.json',{'path':'candidate.json','sha256':'0'*64},
                    dict(self.bindings['candidate'],status='PASS'),{'path':'../outside','sha256':'a'*64}):
            with self.assertRaises(StudioError):checked_reference(self.project,bad)

    def test_inner_clip_requires_exact_native_artifact_body_and_entire_coverage(self):
        artifact=self.root/'inner.blend';artifact.write_bytes(b'SYNTHETIC_NOT_NATIVE')
        ref={'path':artifact.name,'sha256':sha(artifact)}
        profile_path=self.root/'inner-profile.json';atomic_json(profile_path,self.profile)
        source={'artifact':ref,'profile':{'path':profile_path.name,'sha256':sha(profile_path)},'body_motion_binding':'actual-body-binding',
            'clip':{'id':'inner','object_name':'inner-cache','animation_target':'SHAPE_KEYS','interpolation':'LINEAR',
                    'geometry_scope':'BAKED_OBSERVED_FRAME_GEOMETRY_LINEAR_INTERPOLATION','fps':24,'frame_start':1,'frame_end':5}}
        declaration={'id':'inner-obstacle','source_receipt':self.bindings['body_motion_receipt'],'artifact':ref,
                     'object_name':'inner-cache','recipe_object':'inner-source','clip_id':'inner'}
        profile=dict(self.profile,animated_colliders=[declaration]);body={'fps':24,'frame_start':1,'frame_end':5}
        with patch('a3d.garment_motion.canonical_garment_clip',return_value=(source,{'fixture':'NOT_NATIVE'})):
            self.assertEqual(len(collider_inputs(self.project,profile,self.recipe,body,'actual-body-binding')),1)
            for field,value in [('fps',30),('frame_end',4),('object_name','wrong-owner'),('interpolation','BEZIER')]:
                bad=copy.deepcopy(source);bad['clip'][field]=value
                with patch('a3d.garment_motion.canonical_garment_clip',return_value=(bad,{})),self.subTest(field=field),self.assertRaises(StudioError):
                    collider_inputs(self.project,profile,self.recipe,body,'actual-body-binding')
            with self.assertRaises(StudioError):collider_inputs(self.project,profile,self.recipe,body,'different-body')
            duplicate=dict(profile,animated_colliders=[declaration,declaration])
            with self.assertRaisesRegex(StudioError,'unique'):collider_inputs(self.project,duplicate,self.recipe,body,'actual-body-binding')
            production=dict(profile,purpose='GARMENT_CANDIDATE')
            recipe=dict(self.recipe,colliders=[{'role':'support','object':'inner-source'}])
            with self.assertRaises(StudioError):collider_inputs(self.project,production,recipe,body,'actual-body-binding')

    def test_convergence_report_cannot_shorten_active_clip_or_complete_failed_terminal(self):
        terminal={'stop_reason':'MEASURED_CONVERGENCE','evaluated_frames':3}
        partial=clip_coverage({'frame_start':1,'frame_end':5},[1,2],terminal=terminal)
        self.assertFalse(partial['clip_complete']);self.assertEqual(partial['status'],'INCOMPLETE')
        failed=clip_coverage({'frame_start':1,'frame_end':5},[1,2,3,4,5],{'reason':'TERMINAL_FRAME_BUDGET'},terminal)
        self.assertFalse(failed['clip_complete']);self.assertEqual(failed['status'],'INCOMPLETE')

    def test_canonical_composition_cannot_promote_a_synthetic_or_partial_inventory(self):
        for purpose,coverage in [('TEST_ONLY','SOURCE_INVENTORY_COMPLETE'),('GARMENT_CANDIDATE','PARTIAL')]:
            result={'status':'CLIPS_EXECUTED','scope':'EXACT_CANDIDATE_ANIMATION','temporal_coverage':'COMPLETE',
                    'purpose':purpose,'whole_asset_inventory_status':coverage}
            atomic_json(self.root/'body_motion_receipt.json',result)
            ref={'path':'body_motion_receipt.json','sha256':sha(self.root/'body_motion_receipt.json')}
            self.native_fixture(operation='compose_animated_delivery',result=dict(result,receipt=ref))
            with self.subTest(purpose=purpose,coverage=coverage),self.assertRaisesRegex(StudioError,'complete native production'):
                canonical_composed_clip(self.project,ref)


class NativeColliderPreparation(unittest.TestCase):
    def test_standalone_key_cache_initializes_exact_collision_before_native_read(self):
        from blender.garment_motion import _activate_collision
        obj=SimpleNamespace(collision=None)
        class Modifiers(list):
            def new(self,name,kind):
                self.append(SimpleNamespace(name=name,type=kind,show_viewport=False,show_render=False))
                obj.collision=SimpleNamespace(thickness_outer=None,thickness_inner=None)
                return self[-1]
        obj.modifiers=Modifiers()
        _activate_collision(obj,{'outer_thickness_cm':.3,'inner_thickness_cm':.15},'observed-inner')
        self.assertEqual(len(obj.modifiers),1)
        self.assertTrue(obj.modifiers[0].show_viewport)
        self.assertAlmostEqual(obj.collision.thickness_outer,.003)
        self.assertAlmostEqual(obj.collision.thickness_inner,.0015)
        _activate_collision(obj,{'outer_thickness_cm':.6,'inner_thickness_cm':.2},'same-observed-inner')
        self.assertEqual(len(obj.modifiers),1)
        self.assertAlmostEqual(obj.collision.thickness_outer,.006)
    def test_missing_native_settings_or_multiple_collision_modifiers_refuses_declared_layer(self):
        from blender.garment_motion import _activate_collision
        declared={'outer_thickness_cm':.3,'inner_thickness_cm':.15}
        modifier=SimpleNamespace(type='COLLISION',show_viewport=True,show_render=True)
        for obj in (SimpleNamespace(modifiers=[modifier],collision=None),
                    SimpleNamespace(modifiers=[modifier,modifier],collision=SimpleNamespace())):
            with self.assertRaises(StudioError):_activate_collision(obj,declared,'declared-inner')


class RelativeSweptContacts(unittest.TestCase):
    def setUp(self):
        self.cloth=[[-5.,-5.,0.],[5.,-5.,0.],[0.,5.,0.]]
        self.faces=[[0,1,2]]
        self.before=[[-.2,-.2,-2.],[.2,-.2,-2.],[0.,.2,-2.]]
        self.after=[[x,y,2.] for x,y,z in self.before]

    def test_obstacle_crosses_coupon_between_clear_endpoints_without_source_edits(self):
        identities=digest([self.cloth,self.before,self.after])
        report=swept_crossing(self.cloth,self.cloth,self.faces,self.before,self.after,self.faces,max_pairs=10)
        self.assertEqual(report['status'],'REFUSED'); self.assertEqual(report['reason'],'RELATIVE_SWEPT_SURFACE_CROSSING')
        self.assertAlmostEqual(report['witnesses'][0]['fraction'],.5)
        self.assertEqual(digest([self.cloth,self.before,self.after]),identities)

    def test_shared_translation_does_not_create_relative_crossing(self):
        translated=[[x+1,y,z] for x,y,z in self.cloth]
        remote=[[x+1,y,z] for x,y,z in self.before]
        report=swept_crossing(self.cloth,translated,self.faces,self.before,remote,self.faces,max_pairs=10)
        self.assertTrue(report['ok'])
        self.assertEqual(interpolate(self.before,self.after,.5),[[x,y,0.] for x,y,z in self.before])

    def test_crossing_at_exact_check_boundary_cannot_disappear_from_adjacent_segments(self):
        midpoint=interpolate(self.before,self.after,.5)
        for before,after in ((self.before,midpoint),(midpoint,self.after)):
            report=swept_crossing(self.cloth,self.cloth,self.faces,before,after,self.faces,max_pairs=10)
            self.assertEqual(report['status'],'INCOMPLETE')
            self.assertEqual(report['reason'],'MOVING_CONTACT_ENDPOINT_DIRECTION_UNRESOLVED')

    def test_unobserved_pair_budget_and_coplanar_sliding_are_incomplete(self):
        report=swept_crossing(self.cloth,self.cloth,self.faces,self.before,self.after,self.faces,max_pairs=10,expired=lambda:True)
        self.assertEqual(report['status'],'INCOMPLETE')
        before=[[x,y,0.] for x,y,z in self.before]; after=[[x+.1,y,0.] for x,y,z in before]
        report=swept_crossing(self.cloth,self.cloth,self.faces,before,after,self.faces,max_pairs=10)
        self.assertEqual(report['status'],'INCOMPLETE')


if __name__=='__main__':unittest.main()
