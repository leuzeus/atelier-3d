"""Limited native Cloth groups, rebuilt from immutable pattern indices per trial."""
import math
from a3d.core import StudioError,digest
from a3d.regional_cloth import regional_weights,MAXIMA

GROUPS={'structural':'vertex_group_structural_stiffness','shear':'vertex_group_shear_stiffness','bending':'vertex_group_bending'}

def apply_regions(obj,payload,profile,settings):
    config=profile.get('regional_stiffness')
    if not config:
        for field in GROUPS.values():setattr(settings,field,'')
        return None
    weights,receipt=regional_weights(payload,config);actual={}
    for key,field in GROUPS.items():
        name='A3D.Stiffness.'+key
        group=obj.vertex_groups.get(name) or obj.vertex_groups.new(name=name)
        group.remove(list(range(len(obj.data.vertices))))
        for i,value in enumerate(weights[key]):group.add([i],value,'REPLACE')
        setattr(settings,field,group.name)
        values=[next((g.weight for g in v.groups if g.group==group.index),0.) for v in obj.data.vertices]
        if any(not math.isclose(a,b,rel_tol=1e-6,abs_tol=1e-7) for a,b in zip(values,weights[key],strict=True)):
            raise StudioError('Blender clamped regional stiffness weights')
        actual[key]=values
    for field,value in config['ceilings'].items():
        prop=settings.bl_rna.properties[field]
        if not math.isfinite(value) or not prop.hard_min<=value<=prop.hard_max:
            raise StudioError('Regional stiffness ceiling is outside the native RNA range; clamping is not allowed')
        setattr(settings,field,value)
        if not math.isclose(getattr(settings,field),value,rel_tol=1e-6,abs_tol=1e-7):
            raise StudioError('Blender clamped regional stiffness ceiling')
    return {**receipt,'executed_weights':actual,'executed_weights_sha256':digest(actual),
        'executed_groups':{k:getattr(settings,v) for k,v in GROUPS.items()},
        'executed_ceilings':{k:getattr(settings,k) for k in MAXIMA}}
