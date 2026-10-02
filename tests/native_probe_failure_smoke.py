"""Real failed native sewing coupon; garment trial must remain NOT_EXECUTED."""
import copy
import sys
import uuid
from pathlib import Path
ROOT=Path(__file__).resolve().parents[1];sys.path.insert(0,str(ROOT))
import bpy
from a3d.core import StudioError, atomic_json, read_json, sha
from a3d.packages import extract_package
from blender.operations import dispatch
from blender.sewing import collider_info, mesh_digest, managed_inputs, preflight, trial_binding
from tests.support import ready_project
root=ROOT/('work/native-probe-failure-'+uuid.uuid4().hex);root.mkdir()
bpy.context.preferences.filepaths.temporary_directory=str(root);bpy.context.preferences.filepaths.save_version=0
project=ready_project(root/'project',True)
bpy.ops.wm.read_factory_settings(use_empty=True)
original=root/'original.blend';bpy.ops.wm.save_as_mainfile(filepath=str(original));original_sha=sha(original)
dispatch(str(project.root),'prepare',{})
recipe=read_json(ROOT/'templates/sewing-recipe.json')
bpy.ops.mesh.primitive_uv_sphere_add(segments=16,ring_count=8,radius=.1,location=(10,10,10))
mannequin=bpy.context.object;mannequin.name='SYNTHETIC_DISTANT_MANNEQUIN'
mannequin.modifiers.new('Collision','COLLISION')
mannequin.collision.thickness_outer=.001;mannequin.collision.thickness_inner=.001
info=collider_info(mannequin)
recipe['colliders']=[{k:info[k] for k in ('object','dimensions_cm','geometry_sha256','outer_thickness_cm','inner_thickness_cm')}]
recipe['colliders'][0].update(role='mannequin',tolerance_cm=.01);recipe['no_collision_reason']=''
profile=recipe['phases']['mount']
profile.update(frames=48,quality=16,tension_stiffness=40,compression_stiffness=40,shear_stiffness=20,
    bending_stiffness=4,structural_damping=3,sewing_force_per_kg=5000)
atomic_json(project.root/'recipe.json',recipe)
component=project.state()['components']['garment.coat']
extracted=project.data/'reconstruction/extracted';extract_package(project.root/component['package']['path'],extracted)
built=dispatch(str(project.root),'garment',{'package_dir':extracted.relative_to(project.root).as_posix(),'recipe_path':'recipe.json'})
obj,payload,_=managed_inputs(project,'garment.coat','recipe.json');context,_,_=preflight(obj,payload,recipe)
before=mesh_digest(obj);gates=copy.deepcopy(project.state()['gates'])
# Seed only a synthetic latest-PASS projection to prove invalidation. This is
# not a physical PASS or acceptance; never used to run the full garment.
local_path=project.data/'blender/sewing/garment.coat-local.json';local_path.parent.mkdir(exist_ok=True)
atomic_json(local_path,{'simulation':'PASS','binding':trial_binding(obj,payload,recipe,'mount',context)})
args={'component_id':'garment.coat','recipe_path':'recipe.json','phase':'mount','scope':'local'}
try:dispatch(str(project.root),'simulate_sewn',args)
except StudioError as exc:assert 'Seams did not settle' in str(exc),str(exc)
else:raise AssertionError('Rigid native coupon unexpectedly settled; fixture needs review')
attempt=max((project.data/'blender/sewing').glob('attempt-*'),key=lambda p:p.stat().st_mtime_ns)
failure=read_json(attempt/'failure.json');diag=read_json(attempt/'diagnostic.json')
assert failure['execution_stage']=='backend_probe' and failure['garment_simulation']=='NOT_EXECUTED'
assert failure['backend_probe_simulation']=='FAIL' and failure['diagnostic']['sha256']==sha(attempt/'diagnostic.json')
assert diag['probe']['case']=='sewing' and diag['probe']['requested_phase_frames']==48
assert diag['probe']['configured_frames']==24 and diag['frame']==24 and len(diag['frames'])==24
assert diag['probe']['completed_cases']==['gravity']
assert diag['executed']['cache']==[1,24,False] and diag['geometry']['mapping_domain']=='synthetic_coupon'
assert diag['geometry']['seam_gaps']['coupon']['max_gap_cm']>.5 and diag['probe']['supports']
assert (attempt/'backend-probes/gravity.json').exists() and not (attempt/'backend-probes/sewing.json').exists()
assert not any(o.name.startswith(('A3D.Probe.','A3D.LocalTrial.')) for o in bpy.data.objects)
assert not any(s.name.startswith('A3D.BackendProbes.') for s in bpy.data.scenes)
assert mesh_digest(obj)==before and project.state()['gates']==gates
inspect_args={'component_id':'garment.coat','attempt_dir':attempt.relative_to(project.root).as_posix()}
db_sha=sha(project.db);inspection=dispatch(str(project.root),'inspect_sewing_failure',inspect_args)
assert sha(project.db)==db_sha and inspection['garment_simulation']=='NOT_EXECUTED'
assert inspection['backend_probe_simulation']=='FAIL' and inspection['probe']['case']=='sewing'
checksum=sha(attempt/'diagnostic.json');dispatch(str(project.root),'restore_checkpoint',{})
assert checksum==sha(attempt/'diagnostic.json') and dispatch(str(project.root),'inspect_sewing_failure',inspect_args)==inspection
assert read_json(local_path)['simulation']=='FAIL'
try:dispatch(str(project.root),'simulate_sewn',{**args,'scope':'full'})
except StudioError as exc:assert 'current local sleeve/armhole' in str(exc),str(exc)
else:raise AssertionError('Old PASS admitted a full after failed probe')
dispatch(str(project.root),'restore_checkpoint',{})
assert project.state()['gates']==gates and sha(original)==original_sha
atomic_json(root/'result.json',{'status':'PASS','blender':bpy.app.version_string,'probe_failure':'PRESERVED',
    'garment_simulation':'NOT_EXECUTED','24_of_requested_48_frames':'PASS','support_and_profile_context':'PASS',
    'cleanup_restore_integrity':'PASS','old_pass_cannot_admit_full':'PASS','inspection':inspection,'consumer':'UNTOUCHED'})
print('A3D_PROBE_FAILURE_RESULT='+str(root/'result.json'),flush=True)
