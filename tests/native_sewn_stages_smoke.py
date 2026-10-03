"""Guarded assembly transfer, full free sewing and fitting on a synthetic fixture."""
import copy,math,sys,uuid
from pathlib import Path
ROOT=Path(__file__).resolve().parents[1];sys.path.insert(0,str(ROOT))
import bpy
from a3d.core import StudioError,atomic_json,read_json,sha,digest
from a3d.packages import extract_package
from blender.operations import dispatch
from blender.sewing import collider_info,mesh_digest,object_mesh
import tests.support as support
root=ROOT/('work/native-sewn-stages-'+uuid.uuid4().hex);root.mkdir()
bpy.context.preferences.filepaths.temporary_directory=str(root)
bpy.context.preferences.filepaths.save_version=0
def refused(operation,args,expected):
    try:dispatch(str(project.root),operation,args)
    except StudioError as error:assert expected in str(error),str(error)
    else:raise AssertionError('Expected refusal: '+expected)
    if project.state().get('pending_blender_operation'):dispatch(str(project.root),'restore_checkpoint',{})
original_source=support.garment_source
def tube_source(path):
    original_source(path);data=read_json(path/'garment.json')
    for p in data['pieces'].values():p['edges']['bottom']=[0,1]
    data['seams']=[
        {'id':'body-side','piece_a':'front','edge_a':'right','piece_b':'back','edge_b':'left','orientation':'forward'},
        {'id':'body-opening','piece_a':'front','edge_a':'left','piece_b':'back','edge_b':'right','orientation':'forward'},
        {'id':'sleeve-side','piece_a':'sleeve-left','edge_a':'right','piece_b':'sleeve-right','edge_b':'left','orientation':'forward'},
        {'id':'sleeve-opening','piece_a':'sleeve-left','edge_a':'left','piece_b':'sleeve-right','edge_b':'right','orientation':'forward'},
        {'id':'armhole-front','piece_a':'front','edge_a':'top','piece_b':'sleeve-left','edge_b':'bottom','orientation':'forward'},
        {'id':'armhole-back','piece_a':'back','edge_a':'top','piece_b':'sleeve-right','edge_b':'bottom','orientation':'forward'}]
    atomic_json(path/'garment.json',data)
support.garment_source=tube_source
try:project=support.ready_project(root/'project',True)
finally:support.garment_source=original_source
bpy.ops.wm.read_factory_settings(use_empty=True)
original=root/'original.blend';bpy.ops.wm.save_as_mainfile(filepath=str(original));original_hash=sha(original)
session=dispatch(str(project.root),'prepare',{})
bpy.ops.mesh.primitive_cylinder_add(vertices=48,radius=.055,depth=1.05,location=(0,0,.4))
body=bpy.context.object;body.name='SYNTHETIC_ARM';body.color=(.42,.42,.42,1)
body.modifiers.new('Collision','COLLISION');body.collision.thickness_outer=.001;body.collision.thickness_inner=.001
info=collider_info(body)
recipe=read_json(ROOT/'templates/sewing-recipe.json')
data=read_json(project.data/'source/package/garment.json')
recipe['seams']={s['id']:{'kind':'closure' if 'opening' in s['id'] else 'permanent','ease_b_over_a':0,'tolerance_relative':.005} for s in data['seams']}
recipe['placements']={pid:{'mode':'cylinder','position_cm':[0,0,41 if pid.startswith('sleeve') else 0],
    'rotation_degrees':[90,0,0],'radius_cm':20/math.pi,'origin_2d_cm':[-20 if pid in ('back','sleeve-right') else 0,0]} for pid in data['pieces']}
recipe['pins']=[{'piece':pid,'edge':'top' if pid.startswith('sleeve') else 'bottom','weight':1} for pid in data['pieces']]
recipe['colliders']=[]
recipe['no_collision_reason']='Declared free sewing before fitting; visible body excluded';recipe['trial_pieces']=['front','sleeve-left']
recipe['phases']['mount']['gravity_m_s2']=[0,0,0]
recipe['phases']['mount']['frames']=32
atomic_json(project.root/'recipe.json',recipe)
component=project.state()['components']['garment.coat']
extracted=project.data/'reconstruction/extracted';extract_package(project.root/component['package']['path'],extracted)

before=copy.deepcopy(project.state()['gates'])
constructed=dispatch(str(project.root),'garment',{'package_dir':extracted.relative_to(project.root).as_posix(),'recipe_path':'recipe.json'})
obj=bpy.data.objects[constructed['object']];base=read_json(project.root/constructed['derived_mesh'])
args={'component_id':'garment.coat','recipe_path':'recipe.json','phase':'mount','scope':'local','purpose':'assembly'}
local=dispatch(str(project.root),'simulate_sewn',args)
result_path=project.root/local['report'];result=read_json(result_path)
assert result['executed']['collisions']['use_collision'] is False and result['executed']['collection']==[]
transfer={'component_id':'garment.coat','recipe_path':'recipe.json','result_path':local['report'],'result_sha256':sha(result_path)}
refused('apply_sewn_result',{**transfer,'result_sha256':'0'*64},'identity changed')
recipe['phases']['mount']['frames']+=1;atomic_json(project.root/'changed.json',recipe)
refused('apply_sewn_result',{**transfer,'recipe_path':'changed.json'},'binding changed')
recipe['phases']['mount']['frames']-=1
receipt=dispatch(str(project.root),'apply_sewn_result',transfer)
new=bpy.data.objects[receipt['object']];payload=read_json(project.root/receipt['derived_mesh'])
for key in ('rest_cm','faces','panels','seams','pins'):assert digest(payload[key])==digest(base[key]),key
for i,p in zip(receipt['transferred_source_indices'],result['local_result_cm'],strict=True):assert payload['placed_cm'][i]==p
archived=bpy.data.objects[constructed['object']]
assert not archived.get('a3d_component_id') and archived.hide_get()
refused('prepare_sewn_stage',{'component_id':'garment.coat','recipe_path':'recipe.json','stage':'fitting'},'identified mannequin')
full=dispatch(str(project.root),'simulate_sewn',{**args,'scope':'full'})
full_report=read_json(project.root/full['report'])
assert full_report['qualification']=='ASSEMBLY_PHYSICS_ONLY'
assert full_report['executed']['collisions']['use_collision'] is False
assert len(full_report['result_cm'])==len(base['rest_cm']) and set(full_report['source_vertex_indices'])==set(range(len(base['rest_cm'])))
refused('freeze_sewn',{'component_id':'garment.coat','recipe_path':'recipe.json'},'fit before freeze')
body=bpy.data.objects['SYNTHETIC_ARM'];info=collider_info(body)
fit=copy.deepcopy(recipe);fit['colliders']=[{k:info[k] for k in ('object','dimensions_cm','geometry_sha256','outer_thickness_cm','inner_thickness_cm')}]
fit['colliders'][0].update(role='mannequin',tolerance_cm=.01);fit['no_collision_reason']=''
atomic_json(project.root/'fit.json',fit)
# Keep this owned synthetic fixture's full-assembly snapshot for the independent
# no-obstacle fitting branch. No consumer scene or runtime is loaded.
assembly_snapshot=root/'fixture-full-assembly.blend'
refused('prepare_sewn_stage',{'component_id':'garment.coat','recipe_path':'fit.json','stage':'fitting'},'starts inside a collider')
# This declared fixture envelope is intentionally incompatible with the sewn
# coupon. Recovery with a tiny budget must refuse, rather than enlarge gates.
fit['contact_recovery']={'source_ref':'test:bounded-contact-repair','clearance_cm':.02,'max_displacement_cm':.001,'max_passes':2}
atomic_json(project.root/'fit-bounded.json',fit)
refused('prepare_sewn_stage',{'component_id':'garment.coat','recipe_path':'fit-bounded.json','stage':'fitting'},'explicit garment/body pose')
# Separate small, explicitly identified synthetic target, not a resized envelope.
bpy.ops.mesh.primitive_cylinder_add(vertices=48,radius=.025,depth=1.05,location=(0,0,.4))
body=bpy.context.object;body.name='TARGET_FIXTURE_ENVELOPE';body.modifiers.new('Collision','COLLISION')
body.collision.thickness_outer=.001;body.collision.thickness_inner=.001
info=collider_info(body)
fit['colliders']=[{k:info[k] for k in ('object','dimensions_cm','geometry_sha256','outer_thickness_cm','inner_thickness_cm')}]
fit['colliders'][0].update(role='mannequin',tolerance_cm=.01)
fit.pop('contact_recovery')
atomic_json(project.root/'fit.json',fit)
# A separate tiny auxiliary collider challenges exactly one unpinned vertex.
# Save the full assembly together with this explicit target for the independent
# fitting branch; the original larger envelope remains unchanged.
bpy.ops.wm.save_as_mainfile(filepath=str(assembly_snapshot),copy=True)
# It verifies bounded correction, without altering the synthetic target body.
free_index=next(i for i in range(len(base['rest_cm'])) if base['pins'].get(str(i),0.)==0)
point=full_report['result_cm'][free_index]
bpy.ops.mesh.primitive_uv_sphere_add(segments=16,ring_count=8,radius=.001,location=[x/100 for x in point])
obstacle=bpy.context.object;obstacle.name='RECOVERY_FIXTURE_OBSTACLE';obstacle.modifiers.new('Collision','COLLISION')
obstacle.collision.thickness_outer=.0001;obstacle.collision.thickness_inner=.0001
obstacle_info=collider_info(obstacle)
recovery_fit=copy.deepcopy(fit)
obstacle_contract={k:obstacle_info[k] for k in ('object','dimensions_cm','geometry_sha256','outer_thickness_cm','inner_thickness_cm')}
obstacle_contract.update(role='support',tolerance_cm=.01)
recovery_fit['colliders'].append(obstacle_contract)
recovery_fit['contact_recovery']={'source_ref':'test:small-unpinned-contact','clearance_cm':.02,'max_displacement_cm':.2,'max_passes':2}
atomic_json(project.root/'fit-recovery.json',recovery_fit)
recovery_entry=dispatch(str(project.root),'prepare_sewn_stage',{'component_id':'garment.coat','recipe_path':'fit-recovery.json','stage':'fitting'})
assert 0<recovery_entry['contact_recovery']['max_displacement_cm_measured']<=.2
for key in ('rest_cm','faces','panels','seams','pins'):
    assert digest(read_json(project.root/recovery_entry['derived_mesh'])[key])==digest(base[key]),key
repaired=read_json(project.root/recovery_entry['derived_mesh'])['placed_cm']
for index,weight in base['pins'].items():
    if weight>=1:assert math.dist(repaired[int(index)],full_report['result_cm'][int(index)])<1e-4
entry=recovery_entry
fitted=bpy.data.objects[entry['object']];fit_payload=read_json(project.root/entry['derived_mesh'])
assert max(math.dist(a,b) for a,b in zip(fit_payload['placed_cm'],full_report['result_cm'],strict=True))<=.2
for key in ('rest_cm','faces','panels','seams','pins'):assert digest(fit_payload[key])==digest(base[key]),key
assert entry['simulation']=='NOT_EXECUTED' and entry['stage']=='fitting'
fitting_args={**args,'recipe_path':'fit-recovery.json','purpose':'fitting'}
refused('simulate_sewn',{**fitting_args,'scope':'full'},'local sleeve/armhole')
# The auxiliary sphere is a placement-repair fixture, not evidence of stable
# cloth behavior. Its corrected stage is not used as a final qualification.
recovered_working=read_json(project.data/'blender/session.json')['working']
bpy.ops.wm.open_mainfile(filepath=str(assembly_snapshot))
bpy.ops.wm.save_as_mainfile(filepath=recovered_working)
entry=dispatch(str(project.root),'prepare_sewn_stage',{'component_id':'garment.coat','recipe_path':'fit.json','stage':'fitting'})
entry_payload=read_json(project.root/entry['derived_mesh'])
assert max(math.dist(a,b) for a,b in zip(entry_payload['placed_cm'],full_report['result_cm'],strict=True))<1e-4
fitting_args={**args,'recipe_path':'fit.json','purpose':'fitting'}
fit_local=dispatch(str(project.root),'simulate_sewn',fitting_args)
fit_full=dispatch(str(project.root),'simulate_sewn',{**fitting_args,'scope':'full'})
assert read_json(project.root/fit_full['report'])['executed']['collisions']['use_collision'] is True
assert sha(original)==original_hash and project.state()['gates']==before
atomic_json(root/'result.json',{'status':'PASS','local':local,'transfer':receipt,'full_assembly':full,'fitting_entry':entry,'bounded_contact_recovery':recovery_entry,
    'fitting_local':fit_local,'fitting_full':fit_full,'sources_unchanged':True,'visual_validation':'NOT_EXECUTED'})
print('NATIVE_SEWN_STAGES_PASS='+str(root/'result.json'),flush=True)
