"""Fresh synthetic Cloth clip, canonical body origin and moving-obstacle refusal.

Run in Blender --background --factory-startup --offline-mode with a new G:
output. These fixtures are TEST_ONLY and never accept the production garment.
"""
import argparse
import copy
from pathlib import Path
import runpy
import shutil
import sys

ROOT=Path(__file__).resolve().parents[1]
sys.path.insert(0,str(ROOT))


def arguments(argv):
    parser=argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--output',required=True)
    parser.add_argument('--body-target-receipt',required=True)
    parser.add_argument('--validate-only',action='store_true')
    args=parser.parse_args(argv); output=Path(args.output); receipt=Path(args.body_target_receipt)
    if not output.is_absolute() or output.exists() or not receipt.is_absolute() or not receipt.is_file():
        parser.error('Require a new absolute output and an existing absolute body-target manifest')
    if output.drive.lower()!='g:':parser.error('Native campaign must remain on approved G: storage')
    args.output,args.body_target_receipt=output.resolve(),receipt.resolve()
    return args


def _copy_inputs(manifest_path, output):
    from a3d.body_source import selection
    from a3d.core import StudioError,digest,inside,read_json,sha
    from a3d.store import Project
    from tests.support import ready_project
    source=Project(manifest_path.parent/'project'); before=sha(source.db)
    manifest=read_json(manifest_path)
    if manifest['status']!='NATIVE_BODY_TARGET_PASS':raise StudioError('Expected measured target-body campaign')
    project=ready_project(output/'project',True)
    if digest(project.state()['asset'])!=digest(source.state()['asset']):
        raise StudioError('Synthetic campaign must preserve exact source asset identity')
    refs={}
    def collect(value):
        if isinstance(value,dict):
            if set(value)=={'path','sha256'}:
                if value['path'] in refs and refs[value['path']]!=value['sha256']:
                    raise StudioError('Input manifest has contradictory reference identities')
                refs[value['path']]=value['sha256']
            else:
                for child in value.values():collect(child)
        elif isinstance(value,list):
            for child in value:collect(child)
    for row in manifest['reports']:
        body=row['result']
        for name in ('evidence','artifact','artifacts','receipt'):collect(body[name])
        selected,file,_=selection(source,body['evidence']['selection']['path'])
        if not file.is_relative_to(source.root):raise StudioError('Body input source must be inside its exact project')
        refs[file.relative_to(source.root).as_posix()]=selected['source_sha256']
    copied=[]
    for relative,identity in sorted(refs.items()):
        if relative in ('.a3d/state.sqlite3','.a3d/project.json','.a3d/asset.json','.a3d/blender/session.json') or relative.startswith(('.a3d/runs/','.a3d/decisions/')):
            raise StudioError('Copying canonical state or old qualifications is forbidden')
        file=inside(source.root,relative); destination=inside(project.root,relative,False)
        if not file.is_file() or sha(file)!=identity:raise StudioError('Exact source-body input changed')
        if destination.exists():
            if sha(destination)!=identity:raise StudioError('Source input would replace a fresh fixture record')
        else:
            destination.parent.mkdir(parents=True,exist_ok=True);shutil.copyfile(file,destination)
        if sha(file)!=identity or sha(destination)!=identity:raise StudioError('Copy did not preserve exact input bytes')
        copied.append({'path':relative,'sha256':identity})
    if sha(source.db)!=before:raise StudioError('Input copy changed original canonical state')
    return project,manifest,{'source_database_copied':False,'source_run_receipts_copied':False,
        'source_qualifications_transferred':False,'source_project_preserved':True,'copied_inputs':copied}


def _dispatch(project,operation,args,inputs,directory,label,statuses):
    from a3d.core import atomic_json,digest
    from a3d.runs import create_run,next_run_step,run_status
    spec={'version':1,'id':label,'kind':'motion','asset_id':'test-character','inputs':[],
        'budgets':{'max_attempts':1,'max_seconds':600.},
        'units':[{'id':'native','dependencies':[],'executor':'blender','operation':operation,
                  'arguments':args,'inputs':inputs,'success_statuses':statuses}]}
    path=directory/(label+'.run.json');atomic_json(path,spec)
    info=create_run(project,'motion',path.relative_to(project.root).as_posix())
    prepared=next_run_step(project,info['run_id']);assert prepared['status']=='AWAITING_CONFIRMATION',prepared
    dispatch=runpy.run_path(str(ROOT/'blender/bootstrap.py'))['dispatch_current']
    result=dispatch(str(project.root),operation,args)
    journal=run_status(project,info['run_id']);attempt=journal['units'][0]['attempts'][0]
    assert attempt['receipt_event_id'] and attempt['receipt']
    return result,{'run_id':info['run_id'],'attempt':attempt,'status':journal['units'][0]['status']}


def _obstacle():
    """Native closed obstacle crosses a coupon while both endpoints are clear."""
    import bpy
    from a3d.core import digest
    from blender.body_source import data_ids
    from blender.body_motion import _curves
    from blender.cloth_contacts import build_contact_context,check_contacts
    from blender.moving_contacts import swept_crossing
    from blender.sewing import object_mesh
    baseline=data_ids()
    try:
        scene=bpy.data.scenes.new('TEST_ONLY.MovingObstacle');scene.unit_settings.scale_length=1.
        verts=[[x,y,z] for z in (-.25,.25) for x,y in ((-.2,-.2),(.2,-.2),(.2,.2),(-.2,.2))]
        faces=[]
        for i in range(4):j=(i+1)%4;faces.extend([[i,j,j+4],[i,j+4,i+4]])
        faces.extend([[0,2,1],[0,3,2],[4,5,6],[4,6,7]])
        mesh=bpy.data.meshes.new('TEST_ONLY.Obstacle');mesh.from_pydata([[v/100 for v in p] for p in verts],[],faces)
        obj=bpy.data.objects.new(mesh.name,mesh);scene.collection.objects.link(obj)
        obj.location.z=-.02;obj.keyframe_insert('location',index=2,frame=1)
        obj.location.z=.02;obj.keyframe_insert('location',index=2,frame=2)
        for curve in _curves(obj.animation_data.action):
            for key in curve.keyframe_points:key.interpolation='LINEAR'
        cloth=[[-5.,-5.,0.],[5.,-5.,0.],[0.,5.,0.]]
        payload={'rest_cm':cloth,'faces':[[0,1,2]],'panels':{'coupon':{'indices':[0,1,2]}},'seams':{}}
        captures=[];contacts=[]
        with bpy.context.temp_override(scene=scene,view_layer=scene.view_layers[0]):
            for sample in (1.,1.5,2.):
                scene.frame_set(int(sample),subframe=sample-int(sample));bpy.context.view_layer.update()
                points,triangles=object_mesh(obj,True);points=[[v*100 for v in p] for p in points]
                captures.append(points)
                context=build_contact_context(payload,[obj],clearance_cm=0.,self_clearance_cm=0.,max_penetration_cm=0.,max_pairs=10000)
                contacts.append(check_contacts(context,cloth,frame=sample))
        assert contacts[0]['ok'] and contacts[-1]['ok'],contacts
        assert not contacts[1]['ok'],contacts
        swept=swept_crossing(cloth,cloth,[[0,1,2]],captures[0],captures[-1],faces,max_pairs=10000)
        assert not swept['ok'] and swept['reason']=='RELATIVE_SWEPT_SURFACE_CROSSING',swept
        return {'status':'TEST_ONLY_BETWEEN_FRAME_OBSTACLE_REFUSED','endpoints_clear':True,
                'actual_native_midpoint_refused':True,'relative_swept_crossing':swept,
                'evaluated_geometry_sha256':[digest(points) for points in captures],'product_acceptance':'NOT_GRANTED'}
    finally:bpy.data.batch_remove(ids=data_ids()-baseline)


def run(output,manifest_path):
    import bpy
    from a3d.core import atomic_json,digest,read_json,sha
    from a3d.motion_profiles import standard_motion_profile
    from blender.body_motion import prepare_motion_inputs
    from blender.body_source import data_ids,live_geometry
    from tests.test_garment_motion import motion_profile,synthetic_candidate
    assert bpy.app.background and not bpy.data.filepath
    output.mkdir(parents=True,exist_ok=False)
    project,manifest,copied=_copy_inputs(manifest_path,output)
    directory=project.data/'native-garment-motion-inputs';directory.mkdir(parents=True,exist_ok=False)
    baseline=data_ids();live=live_geometry();reports=[]
    for target in manifest['reports']:
        cid=target['catalog_id'];target_ref=target['result']['receipt']
        rig=prepare_motion_inputs(project,target_ref['path'])['specification']
        profile=standard_motion_profile('walk',rig,'TEST_ONLY small native movement',frame_start=1,frame_end=5)
        for track in profile['tracks']:
            for key in track['keys']:key['radians']*=.01
        body_path=directory/(cid+'.body-motion.json');atomic_json(body_path,profile)
        body_args={'body_target_receipt_path':target_ref['path'],'motion_profile_path':body_path.relative_to(project.root).as_posix()}
        body,body_journal=_dispatch(project,'prepare_body_motion',body_args,
            [target_ref,{'path':body_args['motion_profile_path'],'sha256':sha(body_path)}],directory,cid+'.body-native',['CLIP_SAMPLES_COMPLETE'])
        assert body['status']=='CLIP_SAMPLES_COMPLETE',body
        recipe=read_json(ROOT/'templates/sewing-recipe.json');recipe['phases']['drape']['frames']=64
        recipe['phases']['drape']['gravity_m_s2']=[0.,0.,-.1]
        candidate=synthetic_candidate(recipe)
        bindings={'body_motion_receipt':body['receipt']}
        for name,value in [('recipe',recipe),('candidate',candidate)]:
            path=directory/(cid+'.'+name+'.json');atomic_json(path,value)
            bindings[name]={'path':path.relative_to(project.root).as_posix(),'sha256':sha(path)}
        snapshots={ref['path']:ref['sha256'] for ref in bindings.values()}
        cloth_profile=motion_profile(bindings);cloth_profile['id']=cid+'.observed-cloth'
        cloth_profile['execution']['max_seconds']=300.
        path=directory/(cid+'.garment-motion.json');atomic_json(path,cloth_profile)
        motion,args_journal=_dispatch(project,'run_garment_motion',{'profile_path':path.relative_to(project.root).as_posix()},
            [*bindings.values(),{'path':path.relative_to(project.root).as_posix(),'sha256':sha(path)}],directory,cid+'.cloth-native',['GARMENT_CLIP_SAMPLES_COMPLETE'])
        assert motion['status']=='GARMENT_CLIP_SAMPLES_COMPLETE',motion
        assert motion['coverage']['observed_frames']==[1,2,3,4,5] and motion['observed_frames']==5
        assert motion['clip']['animation_target']=='SHAPE_KEYS' and motion['cache_reopened']['status']=='REOPENED_OBSERVED_GEOMETRY_MATCHES'
        observations=read_json(project.root/motion['observations_artifact']['path'])
        assert all(row['checks'] for row in observations['intervals'])
        maximum=max(row['max_displacement_cm'] for row in observations['frames'])
        assert maximum>1e-5,('Cloth did not actually move',maximum)
        assert len({row['body_geometry_sha256'] for row in observations['frames']})>1
        assert args_journal['status']=='COMPLETED' and motion['accepted'] is False
        # A separately observed inner cloth supplies an exact native animated
        # obstacle; its original cache/source files remain immutable.
        outer=copy.deepcopy(candidate);outer['placed_cm']=[[x,y,z+.6] for x,y,z in outer['placed_cm']]
        outer['rest_cm']=copy.deepcopy(outer['placed_cm'])
        outer_file=directory/(cid+'.outer-candidate.json');atomic_json(outer_file,outer)
        outer_bindings=dict(bindings,candidate={'path':outer_file.relative_to(project.root).as_posix(),'sha256':sha(outer_file)})
        outer_profile=motion_profile(outer_bindings);outer_profile['id']=cid+'.outer-observed-cloth'
        outer_profile['execution']['max_seconds']=300.
        outer_profile['animated_colliders']=[{'id':'observed-inner','source_receipt':motion['receipt'],'artifact':motion['artifact'],
            'object_name':motion['clip']['object_name'],'recipe_object':'synthetic-inner-source','clip_id':motion['clip']['id']}]
        outer_path=directory/(cid+'.outer-profile.json');atomic_json(outer_path,outer_profile)
        layered,layered_journal=_dispatch(project,'run_garment_motion',{'profile_path':outer_path.relative_to(project.root).as_posix()},
            [*outer_bindings.values(),motion['receipt'],motion['artifact'],{'path':outer_path.relative_to(project.root).as_posix(),'sha256':sha(outer_path)}],
            directory,cid+'.layered-native',['GARMENT_CLIP_SAMPLES_COMPLETE'])
        assert layered['status']=='GARMENT_CLIP_SAMPLES_COMPLETE',layered
        layered_data=read_json(project.root/layered['observations_artifact']['path'])
        assert all(len(row['animated_colliders'])==1 for row in layered_data['frames'])
        assert all(check['animated_colliders'] for row in layered_data['intervals'] for check in row['checks'])
        assert layered['object_inventory']['animated_colliders'][0]['source_receipt']==motion['receipt']
        assert layered['cache_reopened']['samples'][0]['animated_colliders']
        short=copy.deepcopy(cloth_profile);short['id']=cid+'.insufficient-clip';short['execution']['max_frames']=2
        short_path=directory/(cid+'.short.json');atomic_json(short_path,short)
        incomplete,incomplete_journal=_dispatch(project,'run_garment_motion',{'profile_path':short_path.relative_to(project.root).as_posix()},
            [*bindings.values(),{'path':short_path.relative_to(project.root).as_posix(),'sha256':sha(short_path)}],directory,cid+'.short-native',['GARMENT_CLIP_SAMPLES_COMPLETE'])
        assert incomplete['status']=='INCOMPLETE' and not incomplete['coverage']['clip_complete']
        assert incomplete['artifact'] is None and incomplete_journal['status']!='COMPLETED'
        for file,identity in snapshots.items():assert sha(project.root/file)==identity
        assert data_ids()==baseline and live_geometry()==live
        reports.append({'catalog_id':cid,'body':body,'body_journal':body_journal,'cloth':motion,'cloth_journal':args_journal,
                        'layered_cloth':layered,'layered_cloth_journal':layered_journal,
                        'insufficient_clip':incomplete,'insufficient_clip_journal':incomplete_journal,'maximum_actual_cloth_displacement_cm':maximum})
    obstacle=_obstacle();assert data_ids()==baseline and live_geometry()==live
    receipt={'version':1,'status':'TEST_ONLY_GARMENT_MOTION_FIXTURES_COMPLETE','reports':reports,'obstacle':obstacle,
             'copied_inputs':copied,'original_scene_preserved':True,'fitting':'NOT_QUALIFIED','product_acceptance':'NOT_GRANTED','accepted':False}
    atomic_json(output/'receipt.json',receipt)
    print('TEST_ONLY_GARMENT_MOTION_FIXTURES_COMPLETE: '+str(output/'receipt.json'))


if __name__=='__main__':
    argv=sys.argv[sys.argv.index('--')+1:] if '--' in sys.argv else sys.argv[1:]
    args=arguments(argv)
    if args.validate_only:print('ARGUMENTS_VALIDATED: no native operation executed')
    else:run(args.output,args.body_target_receipt)
