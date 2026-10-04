"""Actual source-metric contact correction on a synthetic native coupon only."""
import copy
import os
from pathlib import Path
import sys
ROOT=Path(__file__).resolve().parents[1];sys.path.insert(0,str(ROOT))
import bpy
from a3d.core import atomic_json,digest
from blender.placement_correction import correct_preparation
from blender.sewing import mesh_digest

bpy.ops.wm.read_factory_settings(use_empty=True)
bpy.ops.mesh.primitive_cube_add(size=.1,location=(.01,.01,-.04))
body=bpy.context.object;body.name='SYNTHETIC_FIXED_BODY'
unchanged=mesh_digest(body,True)
points=[[0.,0.,0.],[2.,0.,0.],[2.,2.,0.],[0.,2.,0.]]
payload={'version':1,'component_id':'synthetic.coupon','rest_cm':points,'placed_cm':[[x,y,.8] for x,y,_ in points],
    'faces':[[0,1,2],[0,2,3]],'panels':{'coupon':{'indices':[0,1,2,3]}},'pins':{},'seams':{},
    'package_sha256':digest('synthetic-unmodified-source')}
quality={'min_angle_degrees':15.,'min_edge_cm':.01,'min_stretch':.9,'max_stretch':1.1}
recipe={'mesh':quality}
plan={'quality':quality,'assembly':{'max_displacement_cm':2.,'max_step_cm':.05,'iterations':50,'max_initial_gap_cm':.5},
    'collision':{'required':True,'clearance_cm':.1},'consolidation':{'weld_gap_cm':.05}}
spec={'regular_mesh':{'target_min_angle_degrees':15.},'placement_correction':{'version':1,'kernels':['rigid','relaxation'],
    'quality':quality,'budgets':{'max_iterations':50,'max_seconds':60.,'max_proposals_per_iteration':4,
        'max_displacement_cm':2.,'max_step_cm':.05,'stagnation_iterations':2,'min_improvement':1e-8,'target_score':1e-8}}}
before=digest([payload,recipe,plan,spec])
solved=correct_preparation(payload,recipe,plan,spec,[body])
assert solved['status']=='GEOMETRIC_GATES_PASSED',solved
assert solved['measurement']['static_contact']['ok'] is True
assert solved['history'][0]['measurement']['hard_valid'] is False
assert digest([payload,recipe,plan,spec])==before and mesh_digest(body,True)==unchanged
protected=copy.deepcopy(payload);protected['pins']={str(i):1. for i in range(4)}
refused=correct_preparation(protected,recipe,plan,spec,[body])
assert refused['status']=='NEEDS_CORRECTION' and refused['stop_reason']=='STAGNATION'
assert refused['coordinates_cm']==protected['placed_cm'] and mesh_digest(body,True)==unchanged
compressed=copy.deepcopy(payload);compressed['placed_cm']=[[x*.5,y,1.2] for x,y,_ in points]
compressed['panels']['coupon']['edges']={'anchor':[0,3],'opposite':[1,2]}
recovery_spec=copy.deepcopy(spec)
recovery_spec.update(version=1,component_id='synthetic.coupon',source_ref='fixture:immutable-flat-source',
    regular_mesh={'spacing_cm':1.,'min_spacing_cm':.2,'refinement_distance_cm':1.,'max_vertices':20,'target_min_angle_degrees':15.},
    metric_recovery={'version':1,'piece_ids':['coupon'],'protected_edges':[{'piece':'coupon','edge':'anchor'}],
        'strain_weight':100.,'budgets':{'max_iterations':20,'max_seconds':30.,'max_displacement_cm':2.,'max_step_cm':.5,
            'cg_iterations':80,'cg_tolerance':1e-5,'stagnation_iterations':3}})
recovery_before=digest([compressed,recovery_spec]);recovered=correct_preparation(compressed,recipe,plan,recovery_spec,[body])
assert recovered['status']=='GEOMETRIC_GATES_PASSED',recovered
assert recovered['metric_recovery']['status']=='SOURCE_METRIC_RECOVERED'
assert recovered['measurement']['static_contact']['ok']is True
assert recovered['displacement_reference_sha256']==digest(compressed['placed_cm'])
assert recovered['max_displacement_cm']<=2.
assert digest([compressed,recovery_spec])==recovery_before and mesh_digest(body,True)==unchanged
# A two-piece fixture exercises the exact seam quotient through the native
# contact adapter. It remains a static synthetic case, without any Cloth.
from tests.test_guide_metric_solver import seamed_fixture
coupled,guide,coupled_quality,stops=seamed_fixture()
coupled['placed_cm']=[[x,y,1.2]for x,y,z in guide]
coupled.update(version=2,component_id='synthetic.coupled',package_sha256=digest('synthetic-coupled-source'))
coupled_spec=copy.deepcopy(recovery_spec)
coupled_spec.update(component_id='synthetic.coupled')
coupled_spec['metric_recovery'].update(piece_ids=['a','b'],protected_edges=stops,seam_ids=['ab'],
    max_initial_seam_gap_cm=0.)
coupled_spec['metric_recovery']['budgets']['max_iterations']=30
coupled_before=digest([coupled,coupled_spec])
coupled_result=correct_preparation(coupled,{'mesh':coupled_quality},plan,coupled_spec,[body])
assert coupled_result['status']=='GEOMETRIC_GATES_PASSED',coupled_result
assert coupled_result['metric_recovery']['seam_coupling']['final_max_cohort_gap_cm']==0.
assert coupled_result['measurement']['static_contact']['ok']is True
for first,last in coupled['seams']['ab']['pairs']:
    assert coupled_result['coordinates_cm'][first]==coupled_result['coordinates_cm'][last]
assert digest([coupled,coupled_spec])==coupled_before and mesh_digest(body,True)==unchanged
out=Path(os.environ['A3D_VALIDATION_OUTPUT']);out.mkdir(parents=True,exist_ok=True)
mesh=bpy.data.meshes.new('SYNTHETIC_COUPLED_SOURCE_METRIC')
mesh.from_pydata([[v/100 for v in point]for point in coupled_result['coordinates_cm']],[],coupled['faces']);mesh.update()
obj=bpy.data.objects.new(mesh.name,mesh);bpy.context.collection.objects.link(obj)
import json
obj['a3d_source_pairs']=json.dumps(coupled['seams']['ab']['pairs'])
coupled_native_sha=mesh_digest(obj,True)
scene=out/'synthetic-coupled-recovery.blend'
bpy.ops.wm.save_as_mainfile(filepath=str(scene))
bpy.ops.wm.open_mainfile(filepath=str(scene))
assert mesh_digest(bpy.data.objects['SYNTHETIC_FIXED_BODY'],True)==unchanged
reopened=bpy.data.objects['SYNTHETIC_COUPLED_SOURCE_METRIC']
assert mesh_digest(reopened,True)==coupled_native_sha
for first,last in json.loads(reopened['a3d_source_pairs']):
    assert list(reopened.data.vertices[first].co)==list(reopened.data.vertices[last].co)
atomic_json(out/'result.json',{'status':'PASS_SYNTHETIC_STATIC_CORRECTION_ONLY','solved':solved,'protected':refused,'metric_recovery':recovered,
    'coupled_metric_recovery':coupled_result,'coupled_native_mesh_sha256':coupled_native_sha,'native_scene_reopened':True,
    'qualification':'NATIVE_SYNTHETIC_COUPON_ONLY','simulation':'NOT_EXECUTED','fitting':'NOT_QUALIFIED','body_sha256':unchanged})
print('NATIVE_PLACEMENT_CORRECTION_RESULT='+str(out/'result.json'),flush=True)
