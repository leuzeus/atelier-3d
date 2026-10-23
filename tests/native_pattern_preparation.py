"""Native preparation of two fronts, a back and two sleeves; isolated G: only.

The second design omits sleeves and has an asymmetric upper edge. These are
synthetic preparation witnesses, never garment fitting or Cloth approvals.
"""
import copy
import math
import os
from pathlib import Path
import sys

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))
import bpy
from a3d.core import StudioError, atomic_json, digest, read_json, sha
from blender.operations import dispatch
from blender.sewing import collider_info, object_mesh
from tests import support

OUT = Path(os.environ['A3D_VALIDATION_OUTPUT'])
SOURCE = support.garment_source
DOSSIER = support.construction_dossier


def torso(width, height=35):
    points = [[0,0],[width,0],[width,25],[width,height],
              [width/2,height],[0,height],[0,25]]
    return {'vertices':points, 'faces':[[0,1,2],[0,2,6],[6,2,3],[6,3,4],[6,4,5]],
            'edges':{'left':[0,6],'right':[1,2], 'armhole-l':[6,5],'armhole-r':[2,3],
                     'shoulder-l':[5,4],'shoulder-r':[4,3], 'top':[5,4,3],
                     'closure-l':[0,6,5],'closure-r':[1,2,3], 'bottom':[0,1]},
            'position_cm':[0,0,0], 'rotation_degrees':[90,0,0]}


def pattern_source(path, sleeveless=False):
    path.mkdir(parents=True, exist_ok=True)
    pieces = {'front-l':torso(12), 'front-r':torso(12,32 if sleeveless else 35), 'back':torso(24)}
    seams = []
    def seam(sid,a,ea,b,eb,orientation='forward',kind='permanent'):
        seams.append(dict(id=sid,piece_a=a,edge_a=ea,piece_b=b,edge_b=eb,orientation=orientation,kind=kind))
    for side in ('l','r'):
        seam('side-'+side,'front-'+side,'left' if side=='l' else 'right','back','left' if side=='l' else 'right')
        seam('shoulder-'+side,'front-'+side,'top','back','shoulder-'+side)
    seam('front-opening','front-l','closure-r','front-r','closure-l',kind='closure')
    if sleeveless:
        # Different open front lengths are declared as an explicit design ease;
        # the opening remains unsewn. Permanent partners have identical lengths.
        pass
    else:
        for side in ('l','r'):
            pid='sleeve-'+side
            pieces[pid]={'vertices':[[0,0],[18,0],[18,20],[0,20],[0,10]],
                'faces':[[0,1,4],[1,2,4],[2,3,4]],
                'edges':{'cap-front':[0,4],'cap-back':[4,3],'bottom':[0,1],'top':[3,2],'wrist':[1,2]},
                'position_cm':[0,0,0],'rotation_degrees':[0,0,0]}
            seam('armhole-front-'+side,'front-'+side,'armhole-'+side,pid,'cap-front')
            seam('armhole-back-'+side,'back','armhole-'+side,pid,'cap-back','reverse')
            seam('sleeve-longitudinal-'+side,pid,'bottom',pid,'top')
    data={'component_id':'garment.coat','units':'cm','pieces':pieces,'seams':seams,
          'material':{'mass_kg':.3,'tension_stiffness':15,'compression_stiffness':15,'shear_stiffness':5,'bending_stiffness':.5}}
    atomic_json(path/'garment.json',data)
    polygons=''.join('<polygon id="'+pid+'" points="'+' '.join(f'{x},{y}' for x,y in piece['vertices'])+'"/>' for pid,piece in pieces.items())
    (path/'pattern.svg').write_text('<svg xmlns="http://www.w3.org/2000/svg" width="24cm" height="35cm" viewBox="0 0 24 35">'+polygons+'</svg>',encoding='utf-8')
    return data


def dossier(project, garment=False):
    path=project.data/'source/package/garment.json'
    data=read_json(path)
    atomic_json(path,{'seams':[]})
    try:
        result=DOSSIER(project,garment)
    finally:
        atomic_json(path,data)
    prototype=result['components']['garment.coat']['pieces'][1]
    entries=[]
    for pid,piece in data['pieces'].items():
        item=copy.deepcopy(prototype)
        width=max(p[0] for p in piece['vertices'])
        height=max(p[1] for p in piece['vertices'])
        item.update(id=pid,label='Synthetic '+pid,dimensions_cm=[width,height])
        item['pattern']['cut_outline_cm']=[[-1,-1],[width+1,-1],[width+1,height+1],[-1,height+1]]
        item['pattern']['assembly_marks']=[]
        for i,s in enumerate(data['seams']):
            for side in ('a','b'):
                if s['piece_'+side]==pid:
                    # One mark ID at the same arc parameter applies to both
                    # explicitly named forward partners of a self-seam.
                    if s['piece_a']==s['piece_b'] and side=='b':
                        continue
                    item['pattern']['assembly_marks'].append({'id':'R'+str(i),'seam_id':s['id'],
                        'position':.7 if side=='b' and s['orientation']=='reverse' else .3,'symbol':'notch'})
        entries.append(item)
    result['components']['garment.coat']['pieces']=entries
    result['exploded']['annotations']=[{'component_id':'garment.coat','piece_id':p['id'],
        'anchor_px':[5+i*10,50],'label_position_px':[3,70+i*10]} for i,p in enumerate(entries)]
    return result


def make_preform(data, perturb):
    panels={}
    for ordinal,(pid,piece) in enumerate(data['pieces'].items()):
        dx=.15*(-1 if ordinal%2 else 1) if perturb else 0.
        dy=.10*math.sin(ordinal) if perturb else 0.
        theta=math.radians((-1 if ordinal%2 else 1) if perturb else 0.)
        # 7 mm nominal clearance around the fixed 36 mm thick torso leaves
        # the declared 4 mm reserve under these millimetre/degree perturbations.
        origin={'front-l':[-12,-2.5,0],'front-r':[0,-2.5,0],'back':[-12,2.5,0]}.get(pid)
        if origin:
            width=max(p[0] for p in piece['vertices'])
            # The native Bend modifier curves this regular sheet; the fixed
            # body and source UV remain unchanged. 2.8 cm is the declared
            # centre-plane placement, including the 4 mm collision reserve.
            origin[1]=2.8 if pid=='back' else -2.8
            panels[pid]={'source_ref':'fixture native Blender Bend around fixed torso '+pid,
                'origin_cm':[origin[0]+dx,origin[1]+dy,0.],
                'u_axis':[math.cos(theta),math.sin(theta),0.], 'v_axis':[0.,0.,1.],
                'native_bend':{'angle_degrees':math.degrees(width/180.)*(-1 if pid=='back' else 1),
                    'deform_axis':'Z','origin_cm':[width/2,0.,0.],
                    'rotation_degrees':[-90.,0.,0.]}}
        else:
            side=-1 if pid.endswith('-l') else 1
            radius=20/(2*math.pi)
            panels[pid]={'source_ref':'fixture native Blender Bend; source 20cm sleeve circumference and fixed arm axis '+pid,
                'origin_cm':[side*12.3+dx,dy,30-radius],
                'u_axis':[side*math.cos(theta),side*math.sin(theta),0.],
                'v_axis':[math.sin(theta),-math.cos(theta),0.],
                'native_bend':{'angle_degrees':360.,'deform_axis':'X',
                    'origin_cm':[0.,0.,0.], 'rotation_degrees':[-90.*side,0.,0.]}}
    return panels


def native_prepare(project, recipe_path='recipe.json', preparation_path='preparation.json'):
    # Execute the exact code produced by the official MCP-facing entrypoint in
    # this isolated Blender. No connected consumer or installed plugin reload.
    from a3d.tools import blender_operation
    from a3d.guard import parse_code
    request={'component_id':'garment.coat','recipe_path':recipe_path,'preparation_path':preparation_path}
    generated=blender_operation(str(project.root),'prepare_pattern_assembly',request)
    assert generated['executed'] is False
    assert parse_code(generated['code'])['arguments']==request
    scope={}
    exec(compile(generated['code'],'<official-plugin-operation>','exec'),scope)
    return scope['result']


def native_refusals(project, prep, plan, recipe, active_name):
    active=bpy.data.objects[active_name]
    active_before=object_mesh(active)
    results={}
    for label in ('deep-contact','contradictory-support','incompatible-length'):
        candidate_plan=copy.deepcopy(plan)
        candidate_recipe=copy.deepcopy(recipe)
        if label=='deep-contact':
            candidate_plan['preform']['panels']['front-l']['origin_cm'][1]+=2.8
        elif label=='contradictory-support':
            for item in candidate_plan['supports']['drape']:
                item['weight']=1.
        else:
            candidate_recipe['seams']['side-l']['ease_b_over_a']=.12
        plan_path=project.root/(label+'-plan.json')
        recipe_path=project.root/(label+'-recipe.json')
        spec_path=project.root/(label+'-preparation.json')
        atomic_json(plan_path,candidate_plan)
        atomic_json(recipe_path,candidate_recipe)
        spec=copy.deepcopy(prep)
        spec['assembly_plan']={'path':plan_path.name,'sha256':sha(plan_path)}
        atomic_json(spec_path,spec)
        refused=native_prepare(project,recipe_path.name,spec_path.name)
        assert refused['readiness']=='NEEDS_CORRECTION',label
        assert refused['simulation']=='NOT_EXECUTED' and refused['accepted'] is False
        assert object_mesh(active)==active_before
        assert active.get('a3d_role')=='simulation'
        results[label]={'status':'EXPECTED_REFUSAL','receipt':refused['receipt'],
                        'categories':sorted({p['category'] for p in refused['problems']})}
    stale=copy.deepcopy(prep)
    stale['assembly_plan']['sha256']='0'*64
    atomic_json(project.root/'stale-preparation.json',stale)
    try:
        native_prepare(project,preparation_path='stale-preparation.json')
    except ValueError as error:
        # bootstrap deliberately reloads a3d.core: compare the current class,
        # not the StudioError object imported before the first MCP operation.
        assert type(error).__name__=='StudioError'
        assert 'changed' in str(error)
        assert not project.state().get('pending_blender_operation')
        results['stale-source']={'status':'EXPECTED_ADMISSION_REFUSAL','message':str(error)}
    else:
        raise AssertionError('Stale preparation reference admitted')
    return results


def run_case(name,sleeveless=False,perturb=False,spacing=2.5):
    bpy.ops.wm.read_factory_settings(use_empty=True)
    bpy.context.preferences.filepaths.temporary_directory=str(OUT/'tmp')
    support.garment_source=lambda path:pattern_source(path,sleeveless)
    support.construction_dossier=dossier
    try:
        project=support.ready_project(OUT/name,True)
    finally:
        support.garment_source=SOURCE
        support.construction_dossier=DOSSIER
    data=read_json(project.data/'source/package/garment.json')
    immutable=sha(project.root/project.state()['components']['garment.coat']['package']['path'])
    original=OUT/(name+'-original.blend')
    bpy.ops.wm.save_as_mainfile(filepath=str(original))
    original_hash=sha(original)
    dispatch(str(project.root),'prepare',{})
    # Fixed synthetic closed targets, not anatomical fitting evidence.
    bpy.ops.mesh.primitive_cube_add(size=1,location=(0,0,.16))
    body=bpy.context.object
    body.name='SYNTHETIC_FIXED_TORSO'
    body.dimensions=(.18,.036,.32)
    bpy.ops.object.transform_apply(location=False,rotation=False,scale=True)
    bodies=[body]
    if not sleeveless:
        for side in (-1,1):
            bpy.ops.mesh.primitive_cylinder_add(vertices=32,radius=.012,depth=.14,
                location=(side*.21,0,.30),rotation=(0,math.pi/2,0))
            arm=bpy.context.object
            arm.name='SYNTHETIC_FIXED_ARM_'+str(side)
            bodies.append(arm)
    for body in bodies:
        body.modifiers.new('Collision','COLLISION')
        body.collision.thickness_outer=.001
        body.collision.thickness_inner=.001
    identities=[collider_info(o) for o in bodies]
    recipe=read_json(ROOT/'templates/sewing-recipe.json')
    recipe['mesh'].update(spacing_cm=spacing,min_stretch=.90,max_stretch=1.10)
    recipe['placements']={}
    for pid in data['pieces']:
        source_origin={'front-l':[-12,-2.5,0],'front-r':[0,-2.5,0],'back':[-12,2.5,0]}.get(pid)
        if source_origin:
            origin=source_origin;rotation=[90,0,0]
        else:
            side=-1 if pid.endswith('-l') else 1
            origin=[side*12.3,0,20];rotation=[90,0,180 if side==-1 else 0]
        recipe['placements'][pid]={'mode':'flat','position_cm':origin,'rotation_degrees':rotation,
                                  'radius_cm':10,'origin_2d_cm':[0,0]}
    recipe['seams']={s['id']:{'kind':s['kind'],'ease_b_over_a':
        (32/35-1 if sleeveless and s['id']=='front-opening' else 0),'tolerance_relative':.01} for s in data['seams']}
    recipe['pins']=[]
    recipe['trial_pieces']=['front-l','back']
    recipe['colliders']=[{**{k:entry[k] for k in ('object','dimensions_cm','geometry_sha256','outer_thickness_cm','inner_thickness_cm')},
        'role':'mannequin','tolerance_cm':.01} for entry in identities]
    recipe['no_collision_reason']=''
    atomic_json(project.root/'recipe.json',recipe)
    plan={'version':1,'component_id':'garment.coat','source_refs':['fixture:fixed-target-and-metric-patterns'],
          'mapping_sha256':'0'*64,'preform':{'panels':make_preform(data,perturb)},
          # Forming the initially flat 20 cm sleeve circumference into its
          # cylinder moves the far rim by 13.184 cm. This construction budget
          # contains that declared operation and the small pose perturbations;
          # the independent 1.5 mm weld and 4 mm body reserves stay unchanged.
          'assembly':{'max_initial_gap_cm':7,'max_displacement_cm':15,'max_step_cm':.05,
              'iterations':160,'neighborhood_rings':3,'closure_support_release':1},
          'consolidation':{'weld_gap_cm':.15},'quality':{k:recipe['mesh'][k] for k in
              ('min_angle_degrees','min_edge_cm','min_stretch','max_stretch')},
          'supports':{'temporary':[],'drape':[],'functional':[]},
          'collision':{'required':True,'clearance_cm':.4,'source_ref':'fixture exact closed torso and arm envelopes'}}
    # Shared permanent top interfaces all carry the same influence. Other pins
    # are construction-only and released by the assembly plan.
    plan['supports']['drape']=[{'id':'neck-'+pid,'piece':pid,'edge':'top','weight':.4,
        'source_ref':'fixture neckline support'} for pid in ('front-l','front-r')]
    plan['supports']['drape'].append({'id':'neck-back','piece':'back','edge':'top','weight':.4,'source_ref':'fixture neckline support'})
    atomic_json(project.root/'plan.json',plan)
    prep={'version':1,'component_id':'garment.coat','source_ref':'synthetic metric source, declared collar and arm axes',
          'regular_mesh':{'spacing_cm':spacing,'min_spacing_cm':spacing/2,'refinement_distance_cm':3.,'max_vertices':30000},
          'assembly_plan':{'path':'plan.json','sha256':sha(project.root/'plan.json')},
          'construction_dossier':{'path':'.a3d/evidence/construction.json','sha256':sha(project.data/'evidence/construction.json')},
          'mass_policy':'native_uniform_vertex',
          'material_profiles':[{'id':'main','source_ref':'synthetic shared cloth profile','pieces':list(data['pieces']),'areal_density_kg_m2':.3}]}
    atomic_json(project.root/'preparation.json',prep)
    result=native_prepare(project)
    atomic_json(OUT/(name+'-preparation.json'),result)
    assert result['readiness']=='READY',{'readiness':result['readiness'],
        'reasons':result.get('assessment',{}).get('reasons'),
        'problems':[{k:p[k] for k in ('category','message') if k in p} for p in result.get('problems',[])]}
    obj=bpy.data.objects[result['object']]
    before=object_mesh(obj)[0]
    # The handoff must persist the prepared geometry and exact current mapping.
    session=read_json(project.data/'blender/session.json')
    bpy.ops.wm.open_mainfile(filepath=session['working'],load_ui=False,use_scripts=False)
    handed=dispatch(str(project.root),'transition_pattern_assembly',{
        'component_id':'garment.coat','recipe_path':result['recipe']['path'],
        'plan_path':result['assembly_plan']['path'],'stage':'preposition'})
    after=object_mesh(bpy.data.objects[handed['object']])[0]
    assert before==after,'Assembly reset the prepared coordinates'
    assert sha(project.root/project.state()['components']['garment.coat']['package']['path'])==immutable
    assert sha(original)==original_hash
    assert [collider_info(bpy.data.objects[e['object']]) for e in identities]==identities
    payload=read_json(project.root/result['derived_mesh']['path'])
    refusals=native_refusals(project,prep,plan,recipe,handed['object']) if name=='five-panels' else {}
    return {'status':'PASS_PREPARATION_ONLY','preparation':result,'handoff':handed,
            'native_refusals':refusals,
            'source_garment_sha256':digest(data),'source_preserved':True,
            'vertices':len(payload['rest_cm']),'faces':len(payload['faces']),
            'seams':{sid:{'parameters':s['parameters'],'pairs':s['pairs']} for sid,s in payload['seams'].items()},
            'simulation':'NOT_EXECUTED','fitting':'NOT_QUALIFIED','artistic':'NOT_APPROVED'}


if __name__=='__main__':
    results={}
    for name,sleeveless,perturb,spacing in [('five-panels',False,False,2.5),
            ('five-panels-perturbed',False,True,2.5),('asymmetric-sleeveless',True,False,2.5),
            ('asymmetric-sleeveless-perturbed',True,True,2.5),('five-panels-remeshed',False,False,2.)]:
        try:
            results[name]=run_case(name,sleeveless,perturb,spacing)
        except BaseException as exc:
            results[name]={'status':'FAIL','error':str(exc),'type':type(exc).__name__}
            atomic_json(OUT/'result.json',results)
            raise
        atomic_json(OUT/'result.json',results)
    for base in ('five-panels','asymmetric-sleeveless'):
        assert results[base]['source_garment_sha256']==results[base+'-perturbed']['source_garment_sha256']
        assert results[base]['seams']==results[base+'-perturbed']['seams']
    assert results['five-panels']['source_garment_sha256']==results['five-panels-remeshed']['source_garment_sha256']
    assert results['five-panels']['vertices']!=results['five-panels-remeshed']['vertices']
    print('NATIVE_PATTERN_PREPARATION_RESULT='+str(OUT/'result.json'),flush=True)
