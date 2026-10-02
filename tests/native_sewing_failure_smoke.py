"""Real evaluated Cloth failure, preserved diagnostic and recovery; isolated synthetic asset."""
import copy
import sys
import uuid
from pathlib import Path

ROOT=Path(__file__).resolve().parents[1]
sys.path.insert(0,str(ROOT))
import bpy
from a3d.core import StudioError, atomic_json, read_json, sha
from a3d.packages import extract_package
from blender.operations import dispatch
from blender.sewing import mesh_digest
import tests.support as support

root=ROOT/('work/native-sewing-failure-'+uuid.uuid4().hex);root.mkdir()
bpy.context.preferences.filepaths.temporary_directory=str(root)
bpy.context.preferences.filepaths.save_version=0
original_source=support.garment_source
def tube_source(path):
    original_source(path);data=read_json(path/'garment.json')
    for p in data['pieces'].values():p['edges']['bottom']=[0,1]
    data['seams']=[{'id':sid,'piece_a':a,'edge_a':ea,'piece_b':b,'edge_b':eb,'orientation':'forward'}
        for sid,a,ea,b,eb in (
            ('body-side','front','right','back','left'),('body-opening','front','left','back','right'),
            ('sleeve-side','sleeve-left','right','sleeve-right','left'),('sleeve-opening','sleeve-left','left','sleeve-right','right'),
            ('armhole-front','front','top','sleeve-left','bottom'),('armhole-back','back','top','sleeve-right','bottom'))]
    atomic_json(path/'garment.json',data)
support.garment_source=tube_source
try:project=support.ready_project(root/'project',True)
finally:support.garment_source=original_source
bpy.ops.wm.read_factory_settings(use_empty=True)
bpy.ops.wm.save_as_mainfile(filepath=str(root/'original.blend'))
original_sha=sha(root/'original.blend')
session=dispatch(str(project.root),'prepare',{})
recipe=read_json(ROOT/'templates/sewing-recipe.json')
data=read_json(project.data/'source/package/garment.json')
recipe['seams']={s['id']:{'kind':'closure' if 'opening' in s['id'] else 'permanent','ease_b_over_a':0,'tolerance_relative':.005} for s in data['seams']}
recipe['placements']={pid:{'mode':'cylinder','position_cm':[0,0,70 if pid.startswith('sleeve') else 0],
    'rotation_degrees':[90,0,0],'radius_cm':20/3.141592653589793,
    'origin_2d_cm':[-20 if pid in ('back','sleeve-right') else 0,0]} for pid in data['pieces']}
recipe['pins']=[{'piece':pid,'edge':'top' if pid.startswith('sleeve') else 'bottom','weight':1} for pid in data['pieces']]
recipe['trial_pieces']=['front','sleeve-left']
recipe['phases']['mount']['gravity_m_s2']=[0,0,0]
recipe['phases']['mount']['frames']=32
recipe['limits']['max_displacement_cm']=100
atomic_json(project.root/'recipe.json',recipe)
component=project.state()['components']['garment.coat']
extracted=project.data/'reconstruction/extracted';extract_package(project.root/component['package']['path'],extracted)
constructed=dispatch(str(project.root),'garment',{'package_dir':extracted.relative_to(project.root).as_posix(),'recipe_path':'recipe.json'})
obj=bpy.data.objects[constructed['object']]
before_mesh=mesh_digest(obj);gates=copy.deepcopy(project.state()['gates'])
args={'component_id':'garment.coat','recipe_path':'recipe.json','phase':'mount','scope':'local'}
try:dispatch(str(project.root),'simulate_sewn',args)
except StudioError as error:
    assert 'Collapsed or distorted placement' in str(error),str(error)
else:raise AssertionError('Real deliberately over-separated fixture did not fail quality')
attempt=max((project.data/'blender/sewing').glob('attempt-*'),key=lambda p:p.stat().st_mtime_ns)
failure=read_json(attempt/'failure.json')
diagnostic=read_json(attempt/'diagnostic.json')
assert diagnostic['frame']==32 and len(diagnostic['frames'])==32
assert diagnostic['geometry']['evaluated_cm']!=diagnostic['geometry']['start_cm']
assert diagnostic['geometry']['outlier_edges'] and diagnostic['geometry']['seam_gaps']
assert diagnostic['geometry']['source_vertex_indices'] and diagnostic['geometry']['source_face_indices']
assert diagnostic['checkpoint']==project.state()['pending_blender_operation']['checkpoint']
assert failure['diagnostic']['sha256']==sha(attempt/'diagnostic.json')
assert diagnostic['placement']['sha256']==sha(attempt/'placement.json')
placement=read_json(attempt/'placement.json')
assert placement['accepted'] is False and placement['simulation']=='NOT_EXECUTED'
assert placement['seams']['armhole-front']['max_gap_cm']>29
assert diagnostic['simulation']=='FAIL' and diagnostic['accepted'] is False
assert not (project.data/'blender/sewing/garment.coat-local.json').exists()
assert not any(o.name.startswith('A3D.LocalTrial.') for o in bpy.data.objects)
assert mesh_digest(obj)==before_mesh and project.state()['gates']==gates
inspect_args={'component_id':'garment.coat','attempt_dir':attempt.relative_to(project.root).as_posix()}
inspection=dispatch(str(project.root),'inspect_sewing_failure',inspect_args)
assert inspection['simulation']=='FAIL' and inspection['accepted'] is False
try:dispatch(str(project.root),'simulate_sewn',{**args,'scope':'full'})
except StudioError:pass
else:raise AssertionError('Failure inspection unlocked production')
diagnostic_sha=sha(attempt/'diagnostic.json')
restored=dispatch(str(project.root),'restore_checkpoint',{})
obj=bpy.data.objects[constructed['object']]
assert mesh_digest(obj)==before_mesh and project.state()['gates']==gates
assert sha(attempt/'diagnostic.json')==diagnostic_sha
assert diagnostic['placement']['sha256']==sha(attempt/'placement.json')
assert not project.state().get('pending_blender_operation')
after=dispatch(str(project.root),'inspect_sewing_failure',inspect_args)
assert after==inspection
assert sha(root/'original.blend')==original_sha
atomic_json(root/'result.json',{'status':'PASS','blender':bpy.app.version_string,'real_evaluation_frames':32,
    'quality_failure':'PASS','diagnostic_survives_cleanup_and_restore':'PASS','mesh_gates_source_preserved':'PASS',
    'no_pass_or_full_admission':'PASS','inspection':inspection,'restored':restored,
    'consumer_project':'UNTOUCHED','visual_acceptance':'NOT_EXECUTED'})
print('A3D_FAILURE_PROOF='+str(root/'result.json'),flush=True)
