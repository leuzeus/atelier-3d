"""Native rest/metric/motion coupons, never a qualification of the real garment."""
import copy,os,sys
from pathlib import Path
ROOT=Path(__file__).resolve().parents[1];sys.path.insert(0,str(ROOT))
import bpy
from a3d.core import atomic_json,read_json,digest
from a3d.pattern_assembly import consolidate,map_digest
from blender.preform import preform_coordinates
from blender.sewing import make_object,simulate_object,commit_positions,rest_key_name
from tests.native_pattern_bend import coupon

out=Path(os.environ['A3D_VALIDATION_OUTPUT'])
bpy.context.preferences.filepaths.temporary_directory=str(out/'tmp')
bpy.context.preferences.filepaths.save_version=0
results={}

def split_coupon(payload,plan):
    """Declare two source islands with duplicated partners at the evaluated bend."""
    original=copy.deepcopy(payload);rest=[];placed=[];faces=[];panels={};maps={}
    for side in ('left','right'):
        keep=[i for i,p in enumerate(original['rest_cm']) if (p[0]<=4. if side=='left' else p[0]>=4.)]
        mapping={old:len(rest)+i for i,old in enumerate(keep)};maps[side]=mapping
        for i in keep:
            uv=original['rest_cm'][i]
            rest.append([uv[0]-(4. if side=='right' else 0.),uv[1],1000. if side=='right' else 0.])
            placed.append(original['placed_cm'][i])
        local_faces=[[mapping[i] for i in f] for f in original['faces'] if all(i in mapping for i in f)]
        faces.extend(local_faces)
        edges={}
        for name,coordinate,value,reverse in [('bottom',1,0.,False),('right',0,4. if side=='left' else 10.,False),
                ('top',1,20.,True),('left',0,0. if side=='left' else 4.,True)]:
            edge=sorted((i for i in keep if original['rest_cm'][i][coordinate]==value),key=lambda i:original['rest_cm'][i][1-coordinate],reverse=reverse)
            edges[name]=[mapping[i] for i in edge]
        panels[side]={'indices':list(mapping.values()),'edges':edges,
            'boundary':sum((edges[k][:-1] for k in ('bottom','right','top','left')),[])}
    ids=sorted((i for i,p in enumerate(original['rest_cm']) if p[0]==4.),key=lambda i:original['rest_cm'][i][1])
    payload.update(rest_cm=rest,placed_cm=placed,faces=faces,panels=panels,seams={'join':{
        'kind':'permanent','piece_a':'left','piece_b':'right','parameters':[original['rest_cm'][i][1]/20 for i in ids],
        'pairs':[[maps['left'][i],maps['right'][i]] for i in ids]}})
    plan['preform']['panels']={pid:{'source_ref':'synthetic independently bound source island; native Bend already evaluated',
        'origin_cm':[0.,0.,0.],'u_axis':[1.,0.,0.],'v_axis':[0.,1.,0.]} for pid in panels}
    plan['mapping_sha256']=map_digest(payload)
    return payload,plan

for mode in ('flat_2d','assembled_3d'):
    bpy.ops.wm.read_factory_settings(use_empty=True)
    bpy.context.preferences.filepaths.temporary_directory=str(out/'tmp')
    payload,plan=coupon(2.)
    plan['quality'].update(min_angle_degrees=15.,min_stretch=.8,max_stretch=1.25)
    payload['placed_cm'],preform=preform_coordinates(payload,plan)
    payload['pattern_assembly']={'version':2,'stage':'relax','temporary_supports_active':False,
        'contact_policy':{'clearance_cm':0.}}
    if mode=='assembled_3d':
        payload,plan=split_coupon(payload,plan)
        payload,consolidation=consolidate(payload,payload['placed_cm'],plan)
    else:consolidation={'status':'NOT_APPLICABLE_SOURCE_REST_CONTROL'}
    recipe=read_json(ROOT/'templates/sewing-recipe.json')
    recipe['mesh'].update(plan['quality'])
    recipe['limits']['min_movement_cm']=.001
    recipe['limits']['max_displacement_cm']=10.
    recipe['phases']['drape'].update(frames=12,gravity_m_s2=[0.,0.,-.5],self_collision=False)
    obj=make_object(payload,'COUPON.'+mode)
    start=digest(payload['rest_cm'])
    try:
        coords,report=simulate_object(obj,payload,recipe,'drape',[],[],
            save_progress=lambda rows:atomic_json(out/(mode+'-progress.json'),rows),
            save_diagnostic=lambda value:atomic_json(out/(mode+'-failure.json'),value))
    except Exception:
        atomic_json(out/'result.json',{'completed':results,'failed':mode});raise
    assert digest(payload['rest_cm'])==start
    assert report['executed']['rest_shape_key']==rest_key_name(payload)
    assert report['executed']['settings']['use_dynamic_mesh'] is False
    assert report['executed']['settings']['use_sewing_springs'] is False
    assert report['executed']['settings']['shrink_min']==report['executed']['settings']['shrink_max']==0.
    assert all(row['quality']['status']=='PASS' and row['contact']['ok'] for row in report['frames'])
    assert report['validation_contract']['temporary_supports_active'] is False
    commit_positions(obj,coords)
    master=out/(mode+'-rest-v001.blend')
    bpy.ops.wm.save_as_mainfile(filepath=str(master),check_existing=False)
    bpy.ops.wm.open_mainfile(filepath=str(master),load_ui=False,use_scripts=False)
    reopened=bpy.data.objects['COUPON.'+mode]
    assert rest_key_name(payload) in reopened.data.shape_keys.key_blocks
    results[mode]={'report':report,'preform':preform,'consolidation':consolidation,
        'master':str(master),'reopened_rest_key':rest_key_name(payload),'qualified_scope':'SYNTHETIC_COUPON_ONLY'}
    atomic_json(out/'result.json',{'status':'PASS_COUPONS_ONLY','cases':results,'real_fitting':'NOT_QUALIFIED'})
print('Native rest coupons complete',flush=True)
