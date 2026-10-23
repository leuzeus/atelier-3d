"""Empty branch, strict rejected-fit readings and explicit rigid pose guards."""
import copy,runpy,sys
from pathlib import Path
ROOT=Path(__file__).resolve().parents[1];sys.path.insert(0,str(ROOT))
import bpy
from a3d.core import StudioError,atomic_json,read_json,sha,digest
from blender.operations import dispatch
from blender.sewing import object_mesh,mesh_digest,commit_positions,collider_info
state=runpy.run_path(str(ROOT/'tests/native_fitting_smoke.py'))
restored_body=bpy.data.objects['SYNTHETIC_BODY_REFERENCE']
restored_body.data.vertices[0].co.x+=.005;restored_body.data.update();bpy.context.view_layer.update()
project=state['project'];root=state['root'];args=state['args'];recipe=state['recipe']
obj=bpy.data.objects[state['built']['object']]
payload=read_json(project.root/obj['a3d_sewing_mesh'])
start=[[x*100 for x in p] for p in object_mesh(obj)[0]]
# Alter only this owned fixture: the diagnostic must survive contact and bad
# strain, while source structure, body identity and all mutation gates remain.
bad=copy.deepcopy(start);bad[0]=[0,0,20];commit_positions(obj,bad)
before=(mesh_digest(obj),sha(project.db),sha(Path(bpy.data.filepath)))
report=dispatch(str(project.root),'inspect_garment_fit',args)
assert report['placement_diagnosis']['preflight']['status']=='REJECTED'
assert report['accepted'] is False and report['simulation']=='NOT_EXECUTED'
assert (mesh_digest(obj),sha(project.db),sha(Path(bpy.data.filepath)))==before
obj.data.shape_keys.key_blocks['A3D.FlatRest'].data[0].co.x+=.001
try:dispatch(str(project.root),'inspect_garment_fit',args)
except StudioError as error:assert 'rest shape was edited' in str(error)
else:raise AssertionError('Edited rest admitted')
obj.data.shape_keys.key_blocks['A3D.FlatRest'].data[0].co.x-=.001
obj.vertex_groups['A3D.Pins'].add([0],.123,'REPLACE')
try:dispatch(str(project.root),'inspect_garment_fit',args)
except StudioError as error:assert 'pin weights differ' in str(error)
else:raise AssertionError('Edited pins admitted')
commit_positions(obj,start)
bpy.ops.wm.save_as_mainfile(filepath=bpy.data.filepath)
working=Path(bpy.data.filepath);before_sha=sha(working);gates=copy.deepcopy(project.state()['gates'])
try:dispatch(str(project.root),'start_clean_construction',{'working_sha256':'0'*64})
except StudioError as error:assert 'identity changed' in str(error)
else:raise AssertionError('Stale witness accepted')
empty=dispatch(str(project.root),'start_clean_construction',{'working_sha256':before_sha})
assert not bpy.data.objects and not bpy.context.scene.objects and not project.state().get('pending_blender_operation')
assert sha(working)==before_sha and sha(project.root/empty['witness'])==before_sha and project.state()['gates']==gates
# A rigid group is placed from three explicit source and target vertices. This
# is a pose test, not Cloth fitting or a guessed anatomical correspondence.
from blender.donning import rigid_frame,place_for_fitting
import numpy as np
source=[[0,0,0],[1,0,0],[0,1,0]];target=[[2,3,0],[2,4,0],[1,3,0]]
rotation,translation,residual=rigid_frame(source,target,1e-5)
assert np.max(np.abs(np.array(source)@rotation+translation-target))<1e-6
for points in ([[0,0,0],[1,0,0],[2,0,0]],[[0,0,0],[2,0,0],[0,2,0]]):
    try:rigid_frame(source,points,1e-5)
    except StudioError:pass
    else:raise AssertionError('Collapsed/scaled target admitted')
mesh=bpy.data.meshes.new('pose-source');mesh.from_pydata([[x/100 for x in p] for p in source],[],[[0,1,2]])
pose=bpy.data.objects.new('pose-source',mesh);bpy.context.scene.collection.objects.link(pose)
pose.shape_key_add(name='Placement');pose.shape_key_add(name='A3D.FlatRest')
body_mesh=bpy.data.meshes.new('pose-body');body_mesh.from_pydata([[x/100 for x in p] for p in target],[],[[0,1,2]])
body=bpy.data.objects.new('pose-body',body_mesh);bpy.context.scene.collection.objects.link(body)
plan={'body':{'object':body.name,'geometry_sha256':mesh_digest(body,True),'role':'target'}}
atomic_json(project.root/'pose-test.json',plan)
pose_recipe={'fitting_plan':{'path':'pose-test.json','sha256':sha(project.root/'pose-test.json')},
    'fitting_placement':{'max_displacement_cm':5,'groups':[{'pieces':['p'],'source_indices':[0,1,2],
        'target_indices':[0,1,2],'labels':['shoulder','elbow','wrist'],'source_ref':'synthetic validated frame','tolerance_cm':.001}]}}
pose_payload={'placed_cm':source,'panels':{'p':{'indices':[0,1,2]}},'pins':{}}
placed=place_for_fitting(project,pose,pose_payload,pose_recipe)
assert placed['status']=='PLACED_NOT_SIMULATED' and placed['surface_projection']=='NOT_APPLIED'
assert max(__import__('math').dist(a,b) for a,b in zip(pose_payload['placed_cm'],target))<1e-5
for mode in ('budget','fixed_pin','proxy','stale'):
    candidate=copy.deepcopy(pose_payload);candidate['placed_cm']=copy.deepcopy(source)
    r=copy.deepcopy(pose_recipe);p=copy.deepcopy(plan)
    if mode=='budget':r['fitting_placement']['max_displacement_cm']=.001
    if mode=='fixed_pin':candidate['pins']={'0':1}
    if mode=='proxy':p['body']['role']='proxy'
    if mode=='stale':p['body']['geometry_sha256']='0'*64
    atomic_json(project.root/'pose-test.json',p);r['fitting_plan']['sha256']=sha(project.root/'pose-test.json')
    before_mesh=mesh_digest(pose)
    try:place_for_fitting(project,pose,candidate,r)
    except StudioError:pass
    else:raise AssertionError('Pose refusal missing: '+mode)
    assert mesh_digest(pose)==before_mesh
atomic_json(root/'clean-fitting-result.json',{'status':'PASS','rejected_fit_readonly':'PASS','rest_pins_refused':'PASS',
    'empty_branch':empty,'rigid_pose':placed,'pose_refusals':['scaled','collinear','budget','fixed_pin','proxy','stale']})
print('NATIVE_CLEAN_FITTING_PASS='+str(root/'clean-fitting-result.json'),flush=True)
