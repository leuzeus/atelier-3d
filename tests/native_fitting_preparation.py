"""Native auxiliary preparation and continuous pose field on an owned fixture."""
import copy,sys,uuid
from pathlib import Path
ROOT=Path(__file__).resolve().parents[1];sys.path.insert(0,str(ROOT))
import bpy
from a3d.core import StudioError,atomic_json,sha,digest,read_json
from blender.operations import dispatch
from blender.body_source import data_ids,live_geometry
from blender.sewing import mesh_digest,build_mesh,object_mesh,make_object
from tests.support import ready_project
from tests.test_sewing import sources

def run(output,project=None):
    from blender.fitting_pose import pose_field,apply_pose
    out=Path(output);out.mkdir(parents=True,exist_ok=True)
    project=project or ready_project(out/'project',True)
    if not (project.data/'blender/session.json').is_file():dispatch(str(project.root),'prepare',{})
    baseline=data_ids();before=live_geometry();db=sha(project.db);file=sha(Path(bpy.data.filepath))
    # Synthetic closed body source without importing the connected scene.
    mesh=bpy.data.meshes.new('Preparation.Body');mesh.from_pydata([(-.02,-.02,0),(.02,-.02,0),(.02,.02,0),(-.02,.02,0),
        (-.02,-.02,.2),(.02,-.02,.2),(.02,.02,.2),(-.02,.02,.2)],[],[(0,3,2,1),(4,5,6,7),(0,1,5,4),(1,2,6,5),(2,3,7,6),(3,0,4,7)])
    obj=bpy.data.objects.new('Preparation.Body',mesh);source=project.root/'preparation-body.blend'
    bpy.data.libraries.write(str(source),{obj},fake_user=True);bpy.data.batch_remove(ids=data_ids()-baseline)
    spec={'version':1,'source_blend':'preparation-body.blend','source_sha256':sha(source),'source_ref':'synthetic closed body',
        'frame':1,'unit_scale_m':1,'meshes':['Preparation.Body'],'dependencies':[],'reference_object':'Preparation.Target'}
    atomic_json(project.root/'preparation-body.json',spec)
    body=dispatch(str(project.root),'prepare_body_reference',{'selection_path':'preparation-body.json'})
    receipt={'path':'.a3d/'+body['receipt'],'sha256':sha(project.data/body['receipt'])}
    envelope={'version':1,'body_receipt':receipt,'object':'Preparation.Envelope','source_ref':'synthetic geometric auxiliary',
        'regions':[{'id':'body','source_meshes':['Preparation.Body'],'partition_bones':[]}],
        'voxel_cm':.2,'padding_cm':.8,'max_body_outside_cm':.1,'thickness_outer_cm':.3,'thickness_inner_cm':.1}
    atomic_json(project.root/'envelope.json',envelope)
    proxy=dispatch(str(project.root),'prepare_fitting_envelope',{'envelope_path':'envelope.json'})
    assert proxy['nonmanifold_edges']==0 and proxy['body_coverage']['outside_vertices']==0
    assert proxy['closed_shell_count']==1 and all(c['signed_volume_m3']>0 for c in proxy['closed_shells'])
    assert data_ids()==baseline and live_geometry()==before and sha(project.db)==db and sha(Path(bpy.data.filepath))==file
    # A connected strip (two source panels and seam partners), fixed neck pin,
    # preserved source rest, tiny bounded change of measured endpoint frame.
    data,recipe=sources();recipe['mesh']['min_stretch']=.75;recipe['mesh']['max_stretch']=1.25
    points=[[x,y,0.] for y in range(3) for x in range(5)]
    payload={'placed_cm':copy.deepcopy(points),'rest_cm':copy.deepcopy(points),'faces':[],
        'panels':{'torso':{'indices':list(range(9)),'edges':{}},'sleeve':{'indices':list(range(9,15)),
            'edges':{'root':[9,10],'wrist':[13,14],'transverse':[9,14]}}},'pins':{'0':1.},'seams':{}}
    for y in range(2):
        for x in range(4):i=y*5+x;payload['faces'] += [[i,i+1,i+6],[i,i+6,i+5]]
    body_pose={'bones':{'rig':{'arm':{'head_cm':[2,2,0],'tail_cm':[3.999,2.06,0]}}}}
    frame={'id':'arm','source_ref':'synthetic measured source edges and target frame','moving_pieces':['sleeve'],
        'origin_edges':[{'piece':'sleeve','edge':'root'}],'axis_edges':[{'piece':'sleeve','edge':'wrist'}],
        'transverse_edges':[{'piece':'sleeve','edge':'transverse'}],
        'target_origin':{'rig':'rig','bone':'arm','endpoint':'head_cm'},'target_axis':{'rig':'rig','bone':'arm','endpoint':'tail_cm'},
        'target_transverse_cm':[0,0,1],'feather_cm':20,'max_axis_length_difference_cm':20}
    # Use actual planar edge centers for identity then a .02 cm translation.
    import numpy as np
    from blender.fitting_pose import basis
    center=lambda name:np.mean([points[i] for i in payload['panels']['sleeve']['edges'][name]],axis=0)
    origin=center('root');axis=center('wrist');transverse=center('transverse')
    frame['target_transverse_cm']=(transverse-origin).tolist()
    body_pose['bones']['rig']['arm']={'head_cm':(origin+np.array([0,0,.02])).tolist(),'tail_cm':(axis+np.array([0,0,.02])).tolist()}
    pose={'frames':[frame],'max_displacement_cm':1,'steps':4}
    coords,report=pose_field(payload,pose,body_pose,recipe)
    assert coords[0]==points[0] and report['max_displacement_cm']>.01 and report['scaling']=='NOT_APPLIED'
    assert payload['placed_cm']==points and payload['rest_cm']==points
    for mode in ('budget','collapsed','strain'):
        b=copy.deepcopy(body_pose);s=copy.deepcopy(pose)
        if mode=='budget':s['max_displacement_cm']=.001
        if mode=='collapsed':b['bones']['rig']['arm']['tail_cm']=b['bones']['rig']['arm']['head_cm']
        if mode=='strain':b['bones']['rig']['arm']['head_cm'][2]+=30
        try:pose_field(payload,s,b,recipe)
        except StudioError:pass
        else:raise AssertionError('Common pose refusal missing: '+mode)
    result={'status':'PASS','envelope':proxy,'continuous_common_pose':report,'fixed_pin_and_rest_preserved':True,
        'pose_refusals':['budget','collapsed','strain'],'live_scene_db_unchanged':True,'production_qualification':'NOT_EXECUTED'}
    atomic_json(out/'fitting-preparation-result.json',result);return result

if __name__=='__main__':print(run(ROOT/('work/native-fitting-preparation-'+uuid.uuid4().hex)))
