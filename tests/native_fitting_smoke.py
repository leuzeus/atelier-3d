"""Isolated native closure support and read-only fitting; no consumer files."""
import copy,math,sys,uuid
from pathlib import Path
ROOT=Path(__file__).resolve().parents[1];sys.path.insert(0,str(ROOT))
import bpy
from a3d.core import StudioError,atomic_json,read_json,sha,digest
from a3d.packages import extract_package
from a3d.sewing import fitting_tack_payload,weld_permanent
from blender.operations import dispatch
from blender.sewing import grid_probe,make_object,simulate_object,mesh_digest,collider_info
from tests.test_fitting import fitting_sources
import tests.support as support
root=ROOT/('work/native-fitting-'+uuid.uuid4().hex);root.mkdir()
bpy.ops.wm.read_factory_settings(use_empty=True)
bpy.context.preferences.filepaths.temporary_directory=str(root);bpy.context.preferences.filepaths.save_version=0
recipe=read_json(ROOT/'templates/sewing-recipe.json')
tack={'id':'temporary-close','seam_id':'coupon','phase':'mount','source_ref':'synthetic source closure correspondence',
    'force_mode':'shared_native_sewing','sewing_force_per_kg':recipe['phases']['mount']['sewing_force_per_kg'],
    'frame_start':1,'frame_end':recipe['phases']['mount']['frames']}
recipe['fitting_tacks']=[tack]
payload=grid_probe(2,True);payload['seams']['coupon']['kind']='closure'
before=digest(payload);trial=fitting_tack_payload(payload,recipe,'mount');obj=make_object(trial,'SYNTHETIC_TACK_COUPONS')
recipe['phases']['mount']['gravity_m_s2']=[0,0,0]
coords,closed=simulate_object(obj,trial,recipe,'mount',[],[])
assert closed['final_gap_cm']<.5 and closed['executed']['fitting_tacks']
assert closed['executed']['cache']==[1,tack['frame_end'],False]
assert not any(m.type=='CLOTH' for m in obj.modifiers)
try:weld_permanent(coords,trial['faces'],trial['seams'],.5)
except StudioError as exc:assert 'No permanent seam pairs' in str(exc)
else:raise AssertionError('Temporary closure was welded')
assert digest(payload)==before and payload['seams']['coupon']['kind']=='closure'
bpy.data.objects.remove(obj,do_unlink=True)
original_source=support.garment_source
def closed_source(path):
    original_source(path);data=read_json(path/'garment.json');fixture,_,_=fitting_sources()
    data['seams']=fixture['seams'];data['seams'][0]['orientation']='forward';atomic_json(path/'garment.json',data)
support.garment_source=closed_source
try:project=support.ready_project(root/'project',True)
finally:support.garment_source=original_source
bpy.ops.wm.read_factory_settings(use_empty=True)
original=root/'original.blend';bpy.ops.wm.save_as_mainfile(filepath=str(original));original_sha=sha(original)
dispatch(str(project.root),'prepare',{})
bpy.ops.mesh.primitive_cube_add(size=.08,location=(0,0,.2));body=bpy.context.object;body.name='SYNTHETIC_TARGET'
body.modifiers.new('Collision','COLLISION');body.collision.thickness_outer=.001;body.collision.thickness_inner=.001
info=collider_info(body)
target=bpy.data.objects.new('SYNTHETIC_BODY_REFERENCE',body.data.copy());target.matrix_world=body.matrix_world.copy()
bpy.context.scene.collection.objects.link(target)
data,recipe,plan=fitting_sources()
recipe['colliders']=[{k:info[k] for k in ('object','dimensions_cm','geometry_sha256','outer_thickness_cm','inner_thickness_cm')}]
recipe['colliders'][0].update(role='mannequin',tolerance_cm=.01);recipe['no_collision_reason']=''
recipe['placements']={pid:{'mode':'cylinder','position_cm':[0,0,0],'rotation_degrees':[90,0,0],
    'radius_cm':20/math.pi,'origin_2d_cm':[-20 if pid=='back' else 0,0]} for pid in data['pieces']}
# Unused sleeves are placed away; no change to the source pattern or trial.
for pid in ('sleeve-left','sleeve-right'):recipe['placements'][pid]['position_cm']=[100,0,0]
recipe['pins']=[{'piece':pid,'edge':'top','weight':1} for pid in ('front','back')]
plan['body']={'object':target.name,'geometry_sha256':mesh_digest(target,True),'role':'target'}
plan['envelope']={'object':body.name,'geometry_sha256':info['geometry_sha256'],'role':'proxy'}
plan['measurements'][0]['ease_cm']=12
atomic_json(project.root/'fit.json',plan);recipe['fitting_plan']={'path':'fit.json','sha256':sha(project.root/'fit.json')}
atomic_json(project.root/'recipe.json',recipe)
component=project.state()['components']['garment.coat'];extracted=project.data/'reconstruction/extracted'
extract_package(project.root/component['package']['path'],extracted)
built=dispatch(str(project.root),'garment',{'package_dir':extracted.relative_to(project.root).as_posix(),'recipe_path':'recipe.json'})
obj=bpy.data.objects[built['object']];before_mesh=mesh_digest(obj);gates=copy.deepcopy(project.state()['gates'])
db_sha=sha(project.db);working_sha=sha(Path(bpy.data.filepath));source_sha=sha(extracted/'garment.json')
args={'component_id':'garment.coat','recipe_path':'recipe.json','fit_path':'fit.json'}
fit=dispatch(str(project.root),'inspect_garment_fit',args)
assert fit['fit_status']=='INCOMPATIBLE' and abs(fit['rows'][0]['body']['circumference_cm']-32)<1e-4
assert abs(fit['rows'][0]['deficit_cm']-4)<1e-4
proposal=dispatch(str(project.root),'propose_pattern_adjustment',args)
assert proposal['applied'] is False and proposal['proposals'][0]['status']=='PROPOSED_NOT_APPLIED'
assert sha(project.db)==db_sha and sha(Path(bpy.data.filepath))==working_sha and sha(extracted/'garment.json')==source_sha and mesh_digest(obj)==before_mesh
try:dispatch(str(project.root),'simulate_sewn',{'component_id':'garment.coat','recipe_path':'recipe.json','phase':'mount','scope':'full'})
except StudioError as exc:assert 'Measured fitting deficit' in str(exc)
else:raise AssertionError('Known capacity deficit admitted full')
dispatch(str(project.root),'restore_checkpoint',{})
obj=bpy.data.objects[built['object']]
# Same approved cut, now an explicitly unqualified measurement plan for a
# bounded construction trial. Native tacks must live only on its disposable mesh.
plan['measurements'][0]['landmark_status']='assumed';atomic_json(project.root/'fit.json',plan)
recipe['fitting_plan']['sha256']=sha(project.root/'fit.json')
recipe['fitting_tacks']=[{**tack,'seam_id':'opening','frame_end':recipe['phases']['mount']['frames']}]
recipe['placements']['back']['position_cm'][2]=1
recipe['pins'][1]['weight']=.02
atomic_json(project.root/'recipe.json',recipe)
built=dispatch(str(project.root),'garment',{'package_dir':extracted.relative_to(project.root).as_posix(),'recipe_path':'recipe.json','rebuild':True})
obj=bpy.data.objects[built['object']];before_mesh=mesh_digest(obj)
local_result=dispatch(str(project.root),'simulate_sewn',{'component_id':'garment.coat','recipe_path':'recipe.json','phase':'mount','scope':'local'})
local_report=read_json(project.root/local_result['report'])
assert local_report['qualification']=='CONSTRUCTION_FITTING_ONLY' and local_report['fitting_tacks']
assert local_report['fitting']['fit_status']=='NOT_QUALIFIED' and mesh_digest(obj)==before_mesh
assert not any(o.name.startswith('A3D.LocalTrial.') for o in bpy.data.objects)
assert 'a3d_fitting_tacks' not in obj and sha(extracted/'garment.json')==source_sha
try:dispatch(str(project.root),'simulate_sewn',{'component_id':'garment.coat','recipe_path':'recipe.json','phase':'mount','scope':'full'})
except StudioError as exc:assert 'construction trial only' in str(exc)
else:raise AssertionError('Basted local qualified full')
assert not project.state().get('pending_blender_operation')
target=bpy.data.objects['SYNTHETIC_BODY_REFERENCE'];target.data.vertices[0].co.x-=.005;target.data.update()
try:dispatch(str(project.root),'inspect_garment_fit',args)
except StudioError as exc:assert 'geometry/pose changed' in str(exc) or 'geometry differ' in str(exc),str(exc)
else:raise AssertionError('Changed body admitted stale fitting')
assert project.state()['gates']==gates and sha(original)==original_sha
atomic_json(root/'result.json',{'status':'PASS','blender':bpy.app.version_string,'native_tack':closed,
    'closure_kind_and_unwelded':'PASS','source_rest_untouched':'PASS','readonly_fitting':'PASS','measured_deficit':fit,
    'proposal':proposal,'local_basting_cleanup_and_full_refusal':'PASS','local_result':local_result,
    'full_blocked_for_measured_deficit':'PASS','changed_body_invalidates':'PASS','consumer':'UNTOUCHED'})
print('A3D_NATIVE_FITTING_RESULT='+str(root/'result.json'),flush=True)
