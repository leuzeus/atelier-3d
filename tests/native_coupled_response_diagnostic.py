"""Controlled response experiment on the failed synthetic source checkpoint.

The immutable campaign inputs stay unchanged. Two explicitly labelled copies
isolate a coincident sewing edge from a disconnected control and a small source
panel translation. None of these controls qualifies a production garment.
"""
import copy
import math
import os
from pathlib import Path
import sys
ROOT=Path(__file__).resolve().parents[1];sys.path.insert(0,str(ROOT))
import bpy
from a3d.core import atomic_json,inside,read_json,sha
from blender.sewing import make_object,context_colliders,simulate_object,mesh_digest
from blender.cloth_contacts import precise_self_contacts
from tests.textile_fixtures import response_control,RESPONSE_CONTROLS

project=Path(os.environ['A3D_COUPLED_DIAGNOSTIC_PROJECT'])
failure=read_json(inside(project,os.environ['A3D_COUPLED_DIAGNOSTIC_FAILURE']))
def verified(ref):
    path=inside(project,ref['path']);assert sha(path)==ref['sha256'],ref
    return read_json(path)
bundle=verified(failure['bundle']);prior=verified(failure['previous']);initial=verified(prior['derived_mesh'])
checkpoint=inside(project,failure['checkpoint']['path']);assert sha(checkpoint)==failure['checkpoint']['sha256']
output=Path(os.environ['A3D_VALIDATION_OUTPUT']);output.mkdir(parents=True,exist_ok=True)
results={}
for case in RESPONSE_CONTROLS:
    bpy.ops.wm.open_mainfile(filepath=str(checkpoint),load_ui=False)
    plan=copy.deepcopy(bundle['plan']);recipe=copy.deepcopy(bundle['recipe'])
    payload,supports=response_control(initial,plan,case)
    recipe['phases']['mount']['frames']=6
    recipe['limits']['max_seam_gap_cm']=plan['assembly']['max_initial_gap_cm']
    recipe['limits']['max_displacement_cm']=plan['assembly']['max_displacement_cm']
    admission=precise_self_contacts(payload,payload['placed_cm'],recipe['limits']['weld_gap_cm'],
        recipe['phases']['mount']['self_distance_cm'])
    assert admission['ok'],(case,admission)
    colliders,trees,snapshots=context_colliders(recipe)
    body_before={body.name:mesh_digest(body,True) for body in colliders}
    pairs=[pair for seam in payload['seams'].values() if seam['kind']=='permanent' for pair in seam['pairs']]
    gaps=[math.dist(payload['placed_cm'][a],payload['placed_cm'][b]) for a,b in pairs]
    record={'scope':'SYNTHETIC_CAUSAL_CONTROL_ONLY','case':case,'input_pair_lengths_cm':gaps,
        'source_pins':copy.deepcopy(payload['pins']),'supports':supports,'input_phase':recipe['phases']['mount'],
        'qualification':'NONE','physical_failure':None,'body_sha256_before':body_before,
        'initial_self_contact_admission':admission}
    obj=make_object(payload,'A3D.CoupledResponseDiagnostic')
    def diagnostic(data):
        record['physical_failure']=data;atomic_json(output/(case+'.failure.json'),data)
    def progress(rows):
        record['frames']=rows
    try:
        coordinates,physical=simulate_object(obj,payload,recipe,'mount',colliders,trees,progress,diagnostic)
        record.update(status='RESPONDED_WITH_EXISTING_GATES',result=physical)
    except Exception as error:record.update(status='REFUSED',error=str(error))
    record['body_sha256_after']={body.name:mesh_digest(body,True) for body in colliders}
    assert record['body_sha256_after']==body_before
    results[case]=record;atomic_json(output/'result.json',results)
print('NATIVE_COUPLED_RESPONSE_DIAGNOSTIC='+str(output/'result.json'),flush=True)
