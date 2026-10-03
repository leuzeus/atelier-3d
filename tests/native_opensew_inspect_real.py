"""Read-only geometry diagnosis in a separate Blender process, output on G:."""
import os,sys,math
from pathlib import Path
ROOT=Path(__file__).resolve().parents[1];sys.path.insert(0,str(ROOT))
import bpy
from mathutils import Vector
from a3d.core import read_json,atomic_json
from blender.sewing import context_colliders
from blender.pattern_assembly import collision_check

out=Path(os.environ['A3D_VALIDATION_OUTPUT'])
prior=ROOT/'work/pattern-preparation-20261003/real-native-bend-02'
record=read_json(prior/'report.json')['native_preparation'];project=prior/'project'
bpy.context.preferences.filepaths.temporary_directory=str(out/'tmp')
bpy.ops.wm.open_mainfile(filepath=str(project/record['master']['path']),load_ui=False,use_scripts=False)
mesh=read_json(project/record['derived_mesh']['path']);recipe=read_json(project/record['recipe']['path'])
colliders,trees,snapshots=context_colliders(recipe)
rows={}
for pid,panel in mesh['panels'].items():
    coords=[mesh['placed_cm'][i] for i in panel['indices']]
    rows[pid]={'bounds_cm':[[min(p[k] for p in coords),max(p[k] for p in coords)] for k in range(3)],
        'contact':collision_check(coords,trees,snapshots,.02)}
sections=[]
for z in (142.5,149.,151.5,154.,156.5,159.,161.5):
    radii=[]
    for index in range(48):
        direction=Vector((math.cos(index*math.tau/48),math.sin(index*math.tau/48),0))
        start=Vector((0,0,z/100))+direction*.6
        hit,normal,face,d=trees[0].ray_cast(start,-direction,.6)
        if hit is not None:radii.append({'theta_degrees':index*360/48,'radius_cm':(hit-Vector((0,0,z/100))).length*100,'point_cm':list(hit*100)})
    sections.append({'z_cm':z,'radial_hits':radii})
env=read_json(project/'r21-envelope.json');body=read_json(project/env['body_receipt']['path'])
target=bpy.data.objects[body['reference_object']]
source_regions=[]
for item in body['meshes']:
    if not any(word in item['object'] for word in ('Thorax','Cervical','Skull')):continue
    pts=[list((target.matrix_world@target.data.vertices[i].co)*100) for i in range(item['vertex_offset'],item['vertex_offset']+item['vertices'])]
    source_regions.append({'name':item['object'],'bounds_cm':[[min(p[k] for p in pts),max(p[k] for p in pts)] for k in range(3)]})
atomic_json(out/'inspection.json',{'panels':rows,'sections':sections,'colliders':snapshots,'source_regions':source_regions,
    'qualification':'DIAGNOSTIC_ONLY_ENVELOPE_NOT_ANATOMICALLY_APPROVED'})
print({pid:round(r['contact']['minimum_signed_offset_cm'],4) for pid,r in rows.items()},flush=True)
print([{'z_cm':r['z_cm'],'radius_min':min((p['radius_cm'] for p in r['radial_hits']),default=None),'radius_max':max((p['radius_cm'] for p in r['radial_hits']),default=None)} for r in sections],flush=True)
