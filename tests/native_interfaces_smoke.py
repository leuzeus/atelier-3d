"""Local preparation preserves references; inspection reads rejected geometry."""
import copy,sys,uuid,runpy
from pathlib import Path
ROOT=Path(__file__).resolve().parents[1];sys.path.insert(0,str(ROOT))
import bpy
from a3d.core import StudioError,atomic_json,read_json,sha,digest
from a3d.sewing import mesh_quality
from a3d.garment_rejections import seam_directions
from blender.interfaces import interface_candidate
points=[[0,0,0],[0,1,0],[1,0,0],[3,0,0],[3,-1,.1],[4,0,0]]
p={'rest_cm':copy.deepcopy(points),'placed_cm':copy.deepcopy(points),'faces':[[0,1,2],[3,4,5]],
    'panels':{'ref':{'indices':[0,1,2]},'moving':{'indices':[3,4,5]}},'pins':{},
    'seams':{'s':{'kind':'permanent','piece_a':'ref','piece_b':'moving','pairs':[[0,3],[1,4]]}}}
options={'source_ref':'test:local','interfaces':[{'seam_id':'s','moving_side':'b'}],
    'radius_cm':5,'max_displacement_cm':2,'target_cosine':-.4,'max_passes':4}
before=copy.deepcopy(p)
result,history=interface_candidate(p,points,options)
assert result[:3]==points[:3] and p==before and not seam_directions(p,result)['violations']
mesh_quality(p['rest_cm'],result,p['faces'],{'min_angle_degrees':2,'min_edge_cm':.01,'min_stretch':.8,'max_stretch':1.25})
try:interface_candidate(p,points,{**options,'max_displacement_cm':.001})
except StudioError as exc:assert 'budget' in str(exc)
else:raise AssertionError('Expected budget refusal')
p['pins']={'3':1}
try:interface_candidate(p,points,options)
except StudioError as exc:assert 'fixed pin' in str(exc)
else:raise AssertionError('Expected fixed pin refusal')
p=copy.deepcopy(before)
from blender.panel_mount import mount_candidate
mount_recipe={'mesh':{'min_stretch':.8,'max_stretch':1.25},'panel_mount':{'source_ref':'test:scoped',
    'moving_pieces':['moving'],'seam_ids':['s'],'max_displacement_cm':5,
    'iterations':200,'settle_iterations':200,'strain_margin':.02}}
mounted,mount_report=mount_candidate(p,mount_recipe)
assert mounted[:3]==points[:3] and p==before
assert mount_report['max_gap_cm']<.5 and mount_report['simulation']=='NOT_EXECUTED'
mesh_quality(p['rest_cm'],mounted,p['faces'],{'min_angle_degrees':2,'min_edge_cm':.01,'min_stretch':.8,'max_stretch':1.25})
mount_recipe['panel_mount']['max_displacement_cm']=.001
try:mount_candidate(p,mount_recipe)
except StudioError as exc:assert 'budget' in str(exc)
else:raise AssertionError('Expected scoped mount budget refusal')

# Run the existing guarded native fixture, then alter only its disposable
# simulation geometry to test read-only rejection measurement and structure.
state=runpy.run_path(str(ROOT/'tests/native_sewn_stages_smoke.py'))
project=state['project'];dispatch=state['dispatch'];root=state['root']
obj=next(o for o in bpy.data.objects if o.get('a3d_component_id')=='garment.coat' and o.get('a3d_role')=='simulation')
payload=read_json(project.root/obj['a3d_sewing_mesh'])
from blender.sewing import commit_positions,object_mesh,mesh_digest
coords=[[x*100 for x in q] for q in object_mesh(obj)[0]]
for i in payload['panels']['sleeve-left']['indices']:coords[i]=[-coords[i][0],-coords[i][1],coords[i][2]]
commit_positions(obj,coords)
before_mesh=mesh_digest(obj);before_db=sha(project.db);before_file=sha(Path(bpy.data.filepath))
report=dispatch(str(project.root),'inspect_sewing_placement',{'component_id':'garment.coat','recipe_path':'fit.json'})
# Spatial tangents remain observable even when source topology is consistent;
# collider/quality checks may independently reject this rotated placement.
assert report['directions']['violations']
assert not report['accepted'] and report['simulation']=='NOT_EXECUTED'
assert mesh_digest(obj)==before_mesh and sha(project.db)==before_db and sha(Path(bpy.data.filepath))==before_file
obj.data.shape_keys.key_blocks['A3D.FlatRest'].data[0].co.x+=.01
try:dispatch(str(project.root),'inspect_sewing_placement',{'component_id':'garment.coat','recipe_path':'fit.json'})
except StudioError as exc:assert 'rest shape was edited' in str(exc)
else:raise AssertionError('Diagnostic cannot ignore edited rest')
obj.data.shape_keys.key_blocks['A3D.FlatRest'].data[0].co.x-=.01
obj.vertex_groups['A3D.Pins'].add([0],.123,'REPLACE')
try:dispatch(str(project.root),'inspect_sewing_placement',{'component_id':'garment.coat','recipe_path':'fit.json'})
except StudioError as exc:assert 'pin weights differ' in str(exc)
else:raise AssertionError('Diagnostic cannot ignore edited pins')
atomic_json(root/'interfaces-result.json',{'status':'PASS','preparation_history':history,
    'mount':mount_report,'rejected_geometry_inspection':'PASS','rest_pin_tamper_refused':True,'read_only':'PASS'})
print('NATIVE_INTERFACES_PASS='+str(root/'interfaces-result.json'),flush=True)
