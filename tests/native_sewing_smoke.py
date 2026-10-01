"""Blender --background --factory-startup --disable-autoexec --python-exit-code 1.

Synthetic physics and guarded-operation tests only. Never loads a user .blend.
Writes artifacts under work/native-sewing-<uuid>; no artistic or game acceptance.
"""
import copy
import math
import sys
import uuid
from pathlib import Path
sys.path.insert(0,str(Path(__file__).resolve().parents[1]))
import bpy
from mathutils import Vector
from a3d.core import ROOT, StudioError, atomic_json, read_json, sha
from a3d.packages import extract_package
from blender.operations import dispatch
from blender.sewing import (apply_physics, backend_probes, build_mesh, collider_info,
    grid_probe, make_object, mesh_digest, object_mesh, physical_snapshot, preflight,
    simulate_object, verify_physics)
import tests.support as support

root=ROOT/('work/native-sewing-'+uuid.uuid4().hex);root.mkdir()
bpy.context.preferences.filepaths.temporary_directory=str(root)
bpy.context.preferences.filepaths.save_version=0
results={'blender':bpy.app.version_string,'synthetic':True,'visual_validation':'NOT_EXECUTED','root':str(root)}


def blocked(fn,contains):
    try:fn()
    except StudioError as exc:
        assert contains in str(exc),str(exc)
    else:raise AssertionError('Expected refusal: '+contains)


def render(name,obj,target=(.05,.05,.03),scale=.45,view='front'):
    scene=bpy.context.scene
    camera_data=bpy.data.cameras.new('ProofCamera')
    camera=bpy.data.objects.new('ProofCamera',camera_data);scene.collection.objects.link(camera);scene.camera=camera
    offsets={'front':(0,-3,1),'side':(3,0,1),'back':(0,3,1),'threequarter':(2,-3,1.5)}
    camera.location=Vector(target)+Vector(offsets[view]);camera.rotation_euler=(Vector(target)-camera.location).to_track_quat('-Z','Y').to_euler()
    camera_data.type='ORTHO';camera_data.ortho_scale=scale
    scene.render.engine='BLENDER_WORKBENCH';scene.render.resolution_x=640;scene.render.resolution_y=640;scene.render.resolution_percentage=100
    scene.display.shading.light='STUDIO';scene.display.shading.color_type='OBJECT';scene.display.shading.show_shadows=True
    scene.display.shading.show_cavity=True;scene.display.shading.cavity_type='BOTH'
    if scene.world is None:scene.world=bpy.data.worlds.new('ProofWorld')
    scene.display.shading.background_type='WORLD';scene.world.color=(.12,.12,.12)
    obj.color=(.12,.42,.65,1);scene.render.image_settings.file_format='PNG'
    scene.render.filepath=str(root/(name+'.png'));bpy.ops.render.render(write_still=True)
    bpy.data.objects.remove(camera,do_unlink=True)


recipe=read_json(ROOT/'templates/sewing-recipe.json')
def proof(case,when,obj):
    # All pixels come from the native fixture, never a generated garment image.
    render(case+'-'+when,obj,view='threequarter')
    coords,_=object_mesh(obj)
    if case=='gravity' and when=='after':
        zs=[p[2]*100 for p in coords]
        results['gravity_final_height_range_cm']=[min(zs),max(zs)]

results['probes']=backend_probes(recipe,'mount',root/'probes',proof)
# A second density checks physical normalization, not visual similarity alone.
finer=copy.deepcopy(recipe);finer['mesh']['spacing_cm']=1.
results['finer_probes']=backend_probes(finer,'mount',root/'probes-finer')
assert abs(results['probes']['checks']['gravity']['mass']['total_mass_kg']-
           results['finer_probes']['checks']['gravity']['mass']['total_mass_kg'])<1e-10
atomic_json(root/'probe-results.json',results)
zero=copy.deepcopy(recipe);zero['phases']['mount']['gravity_m_s2']=[0,0,0]
zero_payload=grid_probe(2.)
zero_obj=make_object(zero_payload,'A3D.ZeroResponse')
blocked(lambda:simulate_object(zero_obj,zero_payload,zero,'mount',[],[]),'No measured cloth response')
bpy.data.objects.remove(zero_obj,do_unlink=True)

# A new synthetic, explicitly approved test project: body fragment and sleeve,
# each split in two half-cylinders, with a nonpermanent longitudinal closure.
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
recipe['colliders']=[{k:info[k] for k in ('object','dimensions_cm','geometry_sha256','outer_thickness_cm','inner_thickness_cm')}]
recipe['colliders'][0].update(role='mannequin',tolerance_cm=.01)
recipe['no_collision_reason']='';recipe['trial_pieces']=['front','sleeve-left']
recipe['phases']['mount']['gravity_m_s2']=[0,0,0]
recipe['phases']['mount']['frames']=32
atomic_json(project.root/'recipe.json',recipe)
component=project.state()['components']['garment.coat']
extracted=project.data/'reconstruction/extracted';extract_package(project.root/component['package']['path'],extracted)
before_state=copy.deepcopy(project.state()['gates'])
construction=dispatch(str(project.root),'garment',{'package_dir':extracted.relative_to(project.root).as_posix(),'recipe_path':'recipe.json'})
old_obj=bpy.data.objects[construction['object']]
old_hash=mesh_digest(old_obj)
recipe['mesh']['spacing_cm']=1.8
atomic_json(project.root/'recipe.json',recipe)
construction=dispatch(str(project.root),'garment',{'package_dir':extracted.relative_to(project.root).as_posix(),
    'recipe_path':'recipe.json','rebuild':True})
assert old_obj.get('a3d_role')=='archived-simulation' and mesh_digest(old_obj)==old_hash
assert not old_obj.get('a3d_component_id') and project.state()['gates']==before_state
obj=bpy.data.objects[construction['object']]
payload=read_json(project.root/construction['derived_mesh'])
render('armhole-placement',obj,target=(0,0,.4),scale=1.2,view='threequarter')
# Failure context checks act before a global physics run.
bad=copy.deepcopy(recipe);bad['colliders'][0]['geometry_sha256']='0'*64
blocked(lambda:preflight(obj,payload,bad),'pose or geometry')
obj.data.vertices[1].co=obj.data.vertices[0].co
blocked(lambda:preflight(obj,payload,recipe),'Collapsed')
for i,p in enumerate(payload['placed_cm']):obj.data.vertices[i].co=[v/100 for v in p]
context,colliders,trees=preflight(obj,payload,recipe)
mod,_,collection=apply_physics(obj,payload,recipe,'mount',colliders)
expected=physical_snapshot(obj);obj.modifiers.remove(mod)
replacement,_,collection2=apply_physics(obj,payload,recipe,'mount',colliders)
replacement.settings.mass*=10
blocked(lambda:verify_physics(obj,expected),'Executed Cloth')
replacement.settings.mass=expected['settings']['mass']
obj.vertex_groups['A3D.SeamSelfExclusion'].add([0],.25,'REPLACE')
blocked(lambda:verify_physics(obj,expected),'Executed Cloth')
obj.modifiers.remove(replacement)
bpy.data.collections.remove(collection);bpy.data.collections.remove(collection2)
args={'component_id':'garment.coat','recipe_path':'recipe.json','phase':'mount','scope':'full'}
blocked(lambda:dispatch(str(project.root),'simulate_sewn',args),'local sleeve/armhole')
dispatch(str(project.root),'restore_checkpoint',{})
local=dispatch(str(project.root),'simulate_sewn',{**args,'scope':'local'})
# A successful Python return with no completed evaluation cannot qualify Cloth.
plan={'component_id':'garment.coat','type':'cloth','frame_start':1,'frame_end':32,'quality':10,
    'max_frames':32,'collision_components':[],'baked':False,'sewing_recipe':'recipe.json','phase':'mount'}
atomic_json(project.root/'simulation.json',plan)
script=project.root/'no-response.py';script.write_text('# Deliberately does not evaluate any frame.\n',encoding='utf-8')
blocked(lambda:dispatch(str(project.root),'run_script',{'purpose':'simulate','path':'no-response.py',
    'sha256':sha(script),'component_ids':['garment.coat'],'simulation_plan':'simulation.json'}),'no measured completed')
dispatch(str(project.root),'restore_checkpoint',{})
# Exercise the retry circuit without spending two real whole-garment runs.
import blender.sewing as native
real_simulate=native.simulate_object
def injected_failure(*args,**kwargs):raise StudioError('Synthetic solver failure')
native.simulate_object=injected_failure
try:
    for _ in range(2):
        blocked(lambda:dispatch(str(project.root),'simulate_sewn',args),'Synthetic solver failure')
        dispatch(str(project.root),'restore_checkpoint',{})
    blocked(lambda:dispatch(str(project.root),'simulate_sewn',args),'Two full attempts failed')
    dispatch(str(project.root),'restore_checkpoint',{})
finally:native.simulate_object=real_simulate
local=dispatch(str(project.root),'simulate_sewn',{**args,'scope':'local'})
full=dispatch(str(project.root),'simulate_sewn',args)
obj=next(o for o in bpy.data.objects if o.get('a3d_component_id')=='garment.coat')
render('armhole-sewn',obj,target=(0,0,.4),scale=1.2,view='threequarter')
frozen=dispatch(str(project.root),'freeze_sewn',{'component_id':'garment.coat','recipe_path':'recipe.json'})
assert set(frozen['preserved_links'])=={'body-opening','sleeve-opening'}
assert frozen['vertices_after']<frozen['vertices_before']
final=bpy.data.objects[frozen['object']]
for view in ('front','side','back'):render('frozen-'+view,final,target=(0,0,.4),scale=1.2,view=view)
assert sha(original)==original_hash
assert project.state()['gates']==before_state
assert not project.state().get('pending_blender_operation')
results.update(local=local,full=full,frozen=frozen,original_unchanged=True,board_decision_unchanged=True,
    guards={'changed_collider':'PASS','collapsed_placement':'PASS','recreated_modifier_drift':'PASS',
        'collision_group_weights_drift':'PASS','full_before_local':'PASS','zero_response':'PASS',
        'custom_no_op':'PASS','two_full_failures_require_local':'PASS'})
results['guards']['rebuild_archives_without_new_board']='PASS'
atomic_json(root/'result.json',results)
print('A3D_SEWING_RESULT='+str(root/'result.json'),flush=True)
