"""Exact Studio operation for pose artifact preparation/application and staleness."""
import copy,sys,uuid
from pathlib import Path
ROOT=Path(__file__).resolve().parents[1];sys.path.insert(0,str(ROOT))
import bpy,numpy as np
from a3d.core import atomic_json,sha,read_json,StudioError,digest
from a3d.packages import extract_package
from blender.operations import dispatch
from blender.sewing import mesh_digest,object_mesh,make_object
from blender.body_source import data_ids,live_geometry
from tests.support import ready_project
from tests.test_sewing import sources

def run(output):
    from blender.fitting_pose import apply_pose
    out=Path(output);out.mkdir(parents=True,exist_ok=True);project=ready_project(out/'project',True)
    dispatch(str(project.root),'prepare',{})
    _,recipe=sources();atomic_json(project.root/'recipe.json',recipe)
    component=project.state()['components']['garment.coat'];extracted=project.data/'reconstruction/extracted'
    extract_package(project.root/component['package']['path'],extracted)
    built=dispatch(str(project.root),'garment',{'package_dir':extracted.relative_to(project.root).as_posix(),'recipe_path':'recipe.json'})
    obj=bpy.data.objects[built['object']];payload=read_json(project.root/obj['a3d_sewing_mesh']);coords=np.array(object_mesh(obj)[0])*100
    edge=lambda name:coords[payload['panels']['sleeve-left']['edges'][name]].mean(axis=0)
    origin=edge('left');axis=edge('right');transverse=edge('top');offset=np.array([0,0,.02])
    baseline=data_ids();saved_active=bpy.context.view_layer.objects.active;selected=list(bpy.context.selected_objects)
    armature=bpy.data.armatures.new('PoseOperation.Rig');rig=bpy.data.objects.new('PoseOperation.Rig',armature)
    bpy.context.scene.collection.objects.link(rig)
    for x in selected:x.select_set(False)
    rig.select_set(True);bpy.context.view_layer.objects.active=rig
    bpy.ops.object.mode_set(mode='EDIT');bone=armature.edit_bones.new('arm')
    bone.head=(origin+offset)/100;bone.tail=(axis+offset)/100;bpy.ops.object.mode_set(mode='OBJECT')
    mesh=bpy.data.meshes.new('PoseOperation.Body');mesh.from_pydata([list((origin+offset)/100),list((axis+offset)/100),list((transverse+offset)/100)],[],[(0,1,2)])
    body=bpy.data.objects.new('PoseOperation.Body',mesh)
    source=project.root/'pose-body.blend';bpy.data.libraries.write(str(source),{body,rig},fake_user=True)
    bpy.data.batch_remove(ids=data_ids()-baseline)
    bpy.context.view_layer.objects.active=saved_active
    for x in selected:x.select_set(True)
    selection={'version':1,'source_blend':'pose-body.blend','source_sha256':sha(source),'source_ref':'native synthetic matching body/garment frame',
        'frame':1,'unit_scale_m':1,'meshes':['PoseOperation.Body'],'dependencies':['PoseOperation.Rig'],'reference_object':'PoseOperation.Target'}
    atomic_json(project.root/'body-selection.json',selection)
    reference=dispatch(str(project.root),'prepare_body_reference',{'selection_path':'body-selection.json'})
    ref={'path':'.a3d/'+reference['receipt'],'sha256':sha(project.data/reference['receipt'])}
    frame={'id':'arm','source_ref':'actual evaluated synthetic body bone and source boundary centers','moving_pieces':['sleeve-left'],
        'origin_edges':[{'piece':'sleeve-left','edge':'left'}],'axis_edges':[{'piece':'sleeve-left','edge':'right'}],
        'transverse_edges':[{'piece':'sleeve-left','edge':'top'}],
        'target_origin':{'rig':'PoseOperation.Rig','bone':'arm','endpoint':'head_cm'},'target_axis':{'rig':'PoseOperation.Rig','bone':'arm','endpoint':'tail_cm'},
        'target_transverse_cm':(transverse-origin).tolist(),'feather_cm':40,'max_axis_length_difference_cm':.001}
    spec={'version':1,'component_id':'garment.coat','body_receipt':ref,'max_displacement_cm':1,'steps':4,'frames':[frame]}
    atomic_json(project.root/'pose.json',spec)
    before=(mesh_digest(obj),live_geometry(),sha(project.db),sha(Path(bpy.data.filepath)))
    report=dispatch(str(project.root),'prepare_fitting_pose',{'component_id':'garment.coat','recipe_path':'recipe.json','pose_path':'pose.json'})
    assert (mesh_digest(obj),live_geometry(),sha(project.db),sha(Path(bpy.data.filepath)))==before
    with bpy.data.libraries.load(str(project.root/reference['artifact']['path']),link=False) as (_,loaded):loaded.objects=[reference['reference_object']]
    bpy.context.scene.collection.objects.link(loaded.objects[0])
    plan={'body':{'object':reference['reference_object'],'geometry_sha256':reference['geometry_sha256'],'role':'target'}}
    atomic_json(project.root/'fit-test.json',plan)
    fitting_recipe={**recipe,'fitting_pose':report['artifact'],'fitting_plan':{'path':'fit-test.json','sha256':sha(project.root/'fit-test.json')}}
    candidate=copy.deepcopy(payload);candidate['placed_cm']=coords.tolist();clone=make_object(candidate,'PoseOperation.Candidate')
    clone['a3d_sewing_mesh_sha256']=obj['a3d_sewing_mesh_sha256']
    applied=apply_pose(project,clone,candidate,fitting_recipe,mesh_digest(obj))
    assert applied['status']=='PLACED_NOT_SIMULATED' and candidate['placed_cm']!=coords.tolist()
    assert digest(candidate['rest_cm'])==digest(payload['rest_cm']) and candidate['pins']==payload['pins']
    stale=copy.deepcopy(fitting_recipe);stale['fitting_pose']['sha256']='0'*64
    try:apply_pose(project,clone,candidate,stale,mesh_digest(obj))
    except StudioError:pass
    else:raise AssertionError('Changed pose field admitted')
    result={'status':'PASS','native_operation':report,'applied':applied,'source_db_file_unchanged':True,
        'rest_pins_preserved':True,'stale_field_refused':True,'production_qualification':'NOT_EXECUTED'}
    atomic_json(out/'pose-operation-result.json',result);return result

if __name__=='__main__':print(run(ROOT/('work/native-pose-operation-'+uuid.uuid4().hex)))
