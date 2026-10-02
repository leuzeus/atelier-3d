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

root=ROOT/('work/native-prefit-'+uuid.uuid4().hex);root.mkdir()
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
recipe['placements']['back']['position_cm'][1]=.2
recipe['experimental_prefit']={'experimental':True,'source_ref':'test:small-native-seam-translation',
    'seam_ids':['body-side'],'reference_pieces':['front'],'fixed_edges':[],
    'iterations':5,'clearance_cm':0,'max_displacement_cm':2,'min_fraction':.125,'max_backtracks':3,
    'preserve_reference_positions':True}
atomic_json(project.root/'recipe.json',recipe)
component=project.state()['components']['garment.coat']
extracted=project.data/'reconstruction/extracted';extract_package(project.root/component['package']['path'],extracted)

from a3d.core import digest
from blender.sewing import build_mesh,preflight
before=build_mesh(data,recipe)
package_sha=sha(project.root/component['package']['path'])
constructed=dispatch(str(project.root),'garment',{'package_dir':extracted.relative_to(project.root).as_posix(),'recipe_path':'recipe.json'})
payload=read_json(project.root/constructed['derived_mesh'])
report=constructed['experimental_prefit']
assert report['status']=='PREPOSITIONED_NOT_SIMULATED' and report['accepted'] is False
assert constructed['simulation']=='NOT_EXECUTED' and constructed['visual_validation']=='NOT_EXECUTED'
assert report['before_gaps_cm']['body-side']>report['after_gaps_cm']['body-side']
assert 0<report['max_displacement_cm']<=2 and report['fraction']>=.125
for key in ('rest_cm','faces','panels','seams','pins'):assert digest(before[key])==digest(payload[key]),key
assert all(payload['placed_cm'][i]==before['placed_cm'][i] for i in before['panels']['front']['indices'])
assert payload['seams']['body-opening']['kind']=='closure'
obj=bpy.data.objects[constructed['object']];preflight(obj,payload,recipe)
assert sha(project.root/component['package']['path'])==package_sha and sha(root/'original.blend')==original_sha
# An impossible fixed-reference pair is rejected and never archives the current mesh.
recipe['experimental_prefit']['reference_pieces']=['front','back']
recipe['experimental_prefit']['preserve_reference_positions']=False
atomic_json(project.root/'recipe-conflict.json',recipe)
previous=mesh_digest(obj)
try:dispatch(str(project.root),'garment',{'package_dir':extracted.relative_to(project.root).as_posix(),'recipe_path':'recipe-conflict.json','rebuild':True})
except StudioError as exc:assert 'Conflicting fixed landmarks' in str(exc),str(exc)
else:raise AssertionError('Conflicting fixed references were accepted')
assert mesh_digest(obj)==previous and not obj.hide_get()
assert sha(root/'original.blend')==original_sha
atomic_json(root/'result.json',{'status':'PASS','prefit':report,'conflict_refusal':'PASS','source_unchanged':True})
print('NATIVE_PREFIT_PASS='+str(root/'result.json'),flush=True)
