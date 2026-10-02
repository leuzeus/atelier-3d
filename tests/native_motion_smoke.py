"""Native excursion stop retains the failed frame and its actual increment."""
import copy
import sys
import uuid
from pathlib import Path

ROOT=Path(__file__).resolve().parents[1];sys.path.insert(0,str(ROOT))
import bpy
from a3d.core import StudioError,atomic_json,read_json,digest
from a3d.sewing import distance
from blender.sewing import grid_probe,make_object,simulate_object,mesh_digest

root=ROOT/('work/native-motion-'+uuid.uuid4().hex);root.mkdir()
bpy.ops.wm.read_factory_settings(use_empty=True)
bpy.context.preferences.filepaths.temporary_directory=str(root)
recipe=read_json(ROOT/'templates/sewing-recipe.json')
recipe['mass']={'basis':'areal_density_kg_m2','value':.3}
recipe['limits']['max_displacement_cm']=.3
recipe['phases']['mount']['gravity_m_s2']=[0,0,-9.81]
recipe['phases']['mount']['frames']=12
payload=grid_probe(2)
payload['panels']={'coupon':{'indices':list(range(len(payload['rest_cm']))),'edges':{}}}
payload['source_vertex_indices']=[100+i for i in range(len(payload['rest_cm']))]
before=digest(payload);recipe_before=digest(recipe)
obj=make_object(payload,'ISOLATED_MOTION_COUPON');mesh_before=mesh_digest(obj)
saved=[];progress=[]
try:
    simulate_object(obj,payload,recipe,'mount',[],[],
        save_progress=lambda rows:progress.append(copy.deepcopy(rows)),save_diagnostic=saved.append)
except StudioError as exc:
    assert 'displacement budget exceeded' in str(exc),str(exc)
else:raise AssertionError('Expected native displacement refusal')
assert len(saved)==1
data=saved[0];motion=data['geometry']['motion']
assert data['frame']>1 and data['frames'][-1]['frame']==data['frame']==motion['frame']
assert progress[-1]==data['frames']
assert motion['budget_exceeded'] and motion['increment_status']=='MEASURED'
assert motion['previous_frame']==data['frame']-1
assert data['frames'][-1]['max_movement_cm']==motion['max_excursion']['distance_cm']
for key in ('max_excursion','max_increment'):
    node=motion[key]
    assert node['piece']=='coupon' and node['source_vertex_index']==100+node['index']
    assert abs(distance(node['from_cm'],node['to_cm'])-node['distance_cm'])<1e-10
assert motion['max_increment']['distance_cm']>0
assert digest(payload)==before and digest(recipe)==recipe_before and mesh_digest(obj)==mesh_before
assert not obj.modifiers and not any(c.name.startswith('A3D.Colliders.') for c in bpy.data.collections)
atomic_json(root/'diagnostic.json',data)
atomic_json(root/'result.json',{'status':'PASS','blender':bpy.app.version_string,
    'failed_frame_recorded':data['frame'],'motion':motion,'threshold_unchanged':True,
    'mesh_recipe_source_preserved':True,'synthetic':True,'garment_acceptance':'NOT_EXECUTED'})
print('A3D_MOTION_PROOF='+str(root/'result.json'),flush=True)
