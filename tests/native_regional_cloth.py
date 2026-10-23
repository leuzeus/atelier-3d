"""Owned, bounded regional coupons; no production fitting or visual acceptance."""
import copy,sys,uuid
from pathlib import Path
ROOT=Path(__file__).resolve().parents[1];sys.path.insert(0,str(ROOT))
import bpy
from a3d.core import atomic_json,StudioError,digest
from blender.sewing import grid_probe,make_object,apply_physics,physical_snapshot,verify_physics,object_mesh,subset_mesh
from a3d.regional_cloth import regional_weights
from tests.test_sewing import sources
from tests.test_regional_cloth import configuration

def run(output):
    out=Path(output);out.mkdir(parents=True,exist_ok=True);_,recipe=sources()
    recipe['phases']['mount'].update(frames=40,bending_stiffness=.001,tension_stiffness=12,compression_stiffness=12,shear_stiffness=6)
    config=configuration();config['reinforcements']=[]
    config['ceilings'].update(bending_stiffness_max=50,tension_stiffness_max=12,compression_stiffness_max=12,shear_stiffness_max=6)
    config['assignments']=[{'piece':'stiff','profile':'reinforced'}]
    recipe['phases']['mount']['regional_stiffness']=config
    payload=grid_probe(1.,False,height=30.);n=len(payload['rest_cm']);second=copy.deepcopy(payload)
    payload['rest_cm']+= [[x,y,z+1000] for x,y,z in second['rest_cm']]
    payload['placed_cm']+= [[x+20,y,z] for x,y,z in second['placed_cm']]
    payload['faces']+= [[i+n for i in face] for face in second['faces']]
    payload['full_rest_area_cm2']*=2
    payload['panels']={p:{'indices':list(range(o,o+n)),'boundary':[],'edges':{}} for p,o in (('soft',0),('stiff',n))}
    # Cantilever strips with identical pins and mass; only bending weight differs.
    payload['pins']={str(i):1. for i,p in enumerate(payload['placed_cm']) if p[0] in (0,20)}
    obj=make_object(payload,'A3D.RegionalCoupon');before=digest(payload['rest_cm'])
    cloth,mass,collection=apply_physics(obj,payload,recipe,'mount',[]);expected=physical_snapshot(obj)
    actual=mass['regional_stiffness'];assert actual['executed_weights']['bending'][:n]==[0.]*n
    assert actual['executed_weights']['bending'][n:]==[1.]*n
    for frame in range(1,41):bpy.context.scene.frame_set(frame);positions=object_mesh(obj,True)[0]
    verify_physics(obj,expected)
    ends={p:[positions[i][2]*100 for i in panel['indices'] if abs(payload['placed_cm'][i][0]-(10 if p=='soft' else 30))<1e-5] for p,panel in payload['panels'].items()}
    response={p:30-sum(values)/len(values) for p,values in ends.items()}
    assert abs(response['soft']-response['stiff'])>.01,response
    obj.vertex_groups['A3D.Stiffness.bending'].add([0],.5,'REPLACE')
    try:verify_physics(obj,expected)
    except StudioError:pass
    else:raise AssertionError('Changed regional group admitted')
    obj.modifiers.remove(cloth);bpy.data.collections.remove(collection)
    local=subset_mesh(payload,['stiff']);weights,_=regional_weights(local,config)
    assert weights['bending']==[1.]*n and local['source_vertex_indices']==list(range(n,2*n))
    clone=make_object(copy.deepcopy(payload),'A3D.RegionalTransfer');cloth,mass,collection=apply_physics(clone,payload,recipe,'mount',[])
    assert mass['regional_stiffness']['executed_weights_sha256']==actual['executed_weights_sha256']
    assert digest(payload['rest_cm'])==before
    obj.modifiers.clear();clone.modifiers.remove(cloth);bpy.data.collections.remove(collection)
    r=copy.deepcopy(recipe);r['phases']['mount']['regional_stiffness']['ceilings']['bending_stiffness_max']=10001
    try:apply_physics(clone,payload,r,'mount',[])
    except StudioError as exc:assert 'clamp' in str(exc),str(exc)
    else:raise AssertionError('Clamped regional ceiling admitted')
    clone.modifiers.clear()
    uniform=copy.deepcopy(recipe);uniform['phases']['mount'].pop('regional_stiffness')
    cloth,_,collection=apply_physics(clone,payload,uniform,'mount',[])
    assert not cloth.settings.vertex_group_bending and not cloth.settings.vertex_group_structural_stiffness
    clone.modifiers.remove(cloth);bpy.data.collections.remove(collection)
    result={'status':'PASS','blender':bpy.app.version_string,'coupon_tip_drop_cm':response,'executed':actual,
        'changed_weights_refused':True,'local_source_mapping_preserved':True,'transfer_weights_preserved':True,
        'clamped_ceiling_refused':True,'uniform_compatible':True,'rest_unchanged':True,'production_qualification':'NOT_EXECUTED'}
    atomic_json(out/'regional-result.json',result);return result

if __name__=='__main__':print(run(ROOT/('work/native-regional-'+uuid.uuid4().hex)))
