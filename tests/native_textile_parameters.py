"""Small isolated RNA probe; no simulation or product qualification."""
import os
from pathlib import Path
import sys
ROOT=Path(__file__).resolve().parents[1];sys.path.insert(0,str(ROOT))
import bpy
from a3d.core import atomic_json

bpy.ops.wm.read_factory_settings(use_empty=True)
mesh=bpy.data.meshes.new('ParameterProbe');mesh.from_pydata([(0,0,0),(1,0,0),(0,1,0)],[],[(0,1,2)])
obj=bpy.data.objects.new('ParameterProbe',mesh);bpy.context.scene.collection.objects.link(obj)
cloth=obj.modifiers.new('RNAProbe','CLOTH');collision=cloth.collision_settings
rows=[]
for field in ('distance_min','self_distance_min'):
    rna=collision.bl_rna.properties[field]
    for cm in (.05,.3):
        setattr(collision,field,cm/100)
        rows.append({'field':field,'declared_cm':cm,'requested_m':cm/100,'observed_m':getattr(collision,field),
                     'rna_hard_min_m':rna.hard_min,'rna_hard_max_m':rna.hard_max})
obj.modifiers.new('FrozenRNAProbe','COLLISION')
for field in ('thickness_outer','thickness_inner'):
    rna=obj.collision.bl_rna.properties[field]
    for cm in (.05,.3):
        setattr(obj.collision,field,cm/100)
        rows.append({'field':field,'declared_cm':cm,'requested_m':cm/100,'observed_m':getattr(obj.collision,field),
                     'rna_hard_min_m':rna.hard_min,'rna_hard_max_m':rna.hard_max})
out=Path(os.environ['A3D_VALIDATION_OUTPUT']);out.mkdir(parents=True,exist_ok=True)
atomic_json(out/'result.json',{'version':1,'status':'NATIVE_PARAMETER_OBSERVATION','rows':rows,
    'simulation':'NOT_EXECUTED','qualification':'NONE'})
print('NATIVE_TEXTILE_PARAMETER_PROBE='+str(out/'result.json'),flush=True)
