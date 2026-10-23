"""Native five-panel bodice and asymmetric sleeveless construction fixtures.

Run only in an isolated Blender process via scripts/run_pattern_validation.py.
Fixtures prove mechanics, never qualify a consumer garment or artistic fitting.
"""
import copy
import math
import os
from pathlib import Path
import sys

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))
import bpy
from mathutils import Vector
from a3d.core import StudioError, atomic_json, digest, read_json, sha
from a3d.packages import extract_package
from a3d.pattern_assembly import map_digest
from blender.operations import dispatch
from blender.sewing import collider_info
import tests.support as support

OUT = Path(os.environ['A3D_VALIDATION_OUTPUT'])
bpy.context.preferences.filepaths.temporary_directory = str(OUT / 'tmp')
bpy.context.preferences.filepaths.save_version = 0
ORIGINAL_SOURCE = support.garment_source
ORIGINAL_DOSSIER = support.construction_dossier


def pattern_source(path, asymmetric):
    path.mkdir(parents=True, exist_ok=True)
    pieces = {}
    for index in range(5):
        # The low side panels leave the upper armhole boundaries open. The
        # asymmetric variant has unequal front top heights; no sleeve assumption.
        height = (30 if index in (1, 3) else 40) if asymmetric else 40
        if asymmetric and index == 4:
            height = 36
        inset = 2 if asymmetric else 0
        verts = [[0, 0], [12, 0], [12, 25], [12-inset, height], [inset, height], [0, 25]]
        pieces['p'+str(index)] = {'vertices': verts,
            'faces': [[0, 1, 2], [0, 2, 5], [5, 2, 3], [5, 3, 4]],
            'edges': {'left': [0, 5] if asymmetric else [0, 5, 4],
                      'right': [1, 2] if asymmetric else [1, 2, 3],
                      'top': [4, 3], 'bottom': [0, 1]},
            'position_cm': [0, 0, 0], 'rotation_degrees': [90, 0, 0]}
    seams = [{'id': 'side-'+str(i), 'piece_a': 'p'+str(i), 'edge_a': 'right',
              'piece_b': 'p'+str((i+1) % 5), 'edge_b': 'left',
              'orientation': 'forward'} for i in range(5)]
    data = {'component_id': 'garment.coat', 'units': 'cm', 'pieces': pieces, 'seams': seams,
            'material': {'mass_kg': .3, 'tension_stiffness': 15,
                         'compression_stiffness': 15, 'shear_stiffness': 5, 'bending_stiffness': .5}}
    atomic_json(path / 'garment.json', data)
    polygons = ''.join('<polygon id="'+pid+'" points="'+' '.join(f'{x},{y}' for x, y in p['vertices'])+'"/>' for pid, p in pieces.items())
    (path / 'pattern.svg').write_text('<svg xmlns="http://www.w3.org/2000/svg" width="12cm" height="40cm" viewBox="0 0 12 40">'+polygons+'</svg>', encoding='utf-8')
    return data


def dossier(project, garment=False):
    # Reuse the real board/package admission, explicitly synthetic decisions only.
    data = read_json(project.data / 'source/package/garment.json')
    synthetic = copy.deepcopy(data)
    source = project.data / 'source/package/garment.json'
    atomic_json(source, {'seams': []})
    try:
        result = ORIGINAL_DOSSIER(project, garment)
    finally:
        atomic_json(source, synthetic)
    base = result['components']['garment.coat']['pieces'][1]
    entries = []
    for i, (pid, panel) in enumerate(data['pieces'].items()):
        item = copy.deepcopy(base)
        height = max(p[1] for p in panel['vertices'])
        item.update(id=pid, label='Synthetic panel '+pid, dimensions_cm=[12, height])
        item['pattern']['cut_outline_cm'] = [[-1,-1],[13,-1],[13,height+1],[-1,height+1]]
        item['pattern']['assembly_marks'] = [{'id':'R'+str(j), 'seam_id':s['id'], 'position':.3, 'symbol':'notch'}
            for j,s in enumerate(data['seams']) if pid in (s['piece_a'],s['piece_b'])]
        entries.append(item)
    result['components']['garment.coat']['pieces'] = entries
    result['exploded']['annotations'] = [{'component_id':'garment.coat','piece_id':p['id'],
        'anchor_px':[5+i*10,50],'label_position_px':[3,70+i*10]} for i,p in enumerate(entries)]
    return result


def views(name, obj):
    scene = bpy.context.scene
    scene.render.engine = 'BLENDER_WORKBENCH'
    scene.render.resolution_x = 700
    scene.render.resolution_y = 700
    scene.render.resolution_percentage = 100
    scene.render.image_settings.file_format = 'PNG'
    scene.display.shading.light = 'STUDIO'
    scene.display.shading.color_type = 'OBJECT'
    scene.display.shading.show_shadows = True
    scene.display.shading.show_cavity = True
    obj.color = (.22,.38,.58,1)
    mesh_points = [obj.matrix_world @ v.co for v in obj.data.vertices]
    center = sum(mesh_points, Vector()) / len(mesh_points)
    camera_data = bpy.data.cameras.new('ValidationCamera')
    camera = bpy.data.objects.new('ValidationCamera', camera_data)
    scene.collection.objects.link(camera)
    scene.camera = camera
    camera_data.type = 'ORTHO'
    camera_data.ortho_scale = .65
    for label, direction in [('front',(0,-1,0)),('side',(1,0,0)),('back',(0,1,0)),('three-quarter',(1,-1,.3))]:
        camera.location = center + Vector(direction).normalized()*1.5
        camera.rotation_euler = (center-camera.location).to_track_quat('-Z','Y').to_euler()
        scene.render.filepath = str(OUT / (name+'-'+label+'.png'))
        bpy.ops.render.render(write_still=True)


def run_case(name, asymmetric=False, perturb=False):
    bpy.ops.wm.read_factory_settings(use_empty=True)
    bpy.context.preferences.filepaths.temporary_directory = str(OUT / 'tmp')
    support.garment_source = lambda path: pattern_source(path, asymmetric)
    support.construction_dossier = dossier
    try:
        project = support.ready_project(OUT / name, True)
    finally:
        support.garment_source = ORIGINAL_SOURCE
        support.construction_dossier = ORIGINAL_DOSSIER
    original = OUT / (name+'-original.blend')
    bpy.ops.wm.save_as_mainfile(filepath=str(original))
    source_hash = sha(original)
    dispatch(str(project.root), 'prepare', {})
    # Fixed closed target present from the start, smaller than the shell by a
    # measured reserve. Its dimensions never change to make a candidate pass.
    bpy.ops.mesh.primitive_cylinder_add(vertices=48,radius=.06,depth=.42,location=(0,0,.20))
    body = bpy.context.object
    body.name = 'SYNTHETIC_FIXED_TARGET'
    body.color = (.65,.65,.65,1)
    body.modifiers.new('Collision','COLLISION')
    body.collision.thickness_outer = .001
    body.collision.thickness_inner = .001
    body_identity = collider_info(body)
    recipe = read_json(ROOT / 'templates/sewing-recipe.json')
    data = read_json(project.data / 'source/package/garment.json')
    recipe['mesh']['spacing_cm'] = 3
    recipe['seams'] = {s['id']:{'kind':'closure' if s['id']=='side-4' else 'permanent',
        'ease_b_over_a':0,'tolerance_relative':.01} for s in data['seams']}
    recipe['placements'] = {}
    frames = {}
    # Four permanent interfaces, and a declared open front: five 70-degree
    # panels leave a 10-degree opening so unrelated closure edges cannot start
    # coincident or interpenetrate merely because they have different indices.
    sector = math.radians(70)
    radius = 12/(2*math.sin(sector/2))
    for index, pid in enumerate(data['pieces']):
        theta = index*sector
        start = [radius*math.cos(theta), radius*math.sin(theta), 0]
        end = [radius*math.cos(theta+sector), radius*math.sin(theta+sector), 0]
        angle = math.atan2(end[1]-start[1],end[0]-start[0])
        # Deterministic admissible perturbations: +/- 1.5 mm and +/- 1 degree.
        if perturb:
            start[0] += .15 * (-1 if index%2 else 1)
            start[1] += .10 * math.sin(index)
            angle += math.radians((-1 if index%2 else 1))
        recipe['placements'][pid] = {'mode':'flat','position_cm':start,
            'rotation_degrees':[90,0,math.degrees(angle)],'radius_cm':10,'origin_2d_cm':[0,0]}
        frames[pid] = {'source_ref':'fixture:metric-panel-local-frame:'+pid,
            'origin_cm':start,'u_axis':[math.cos(angle),math.sin(angle),0],
            'v_axis':[0,0,1],'offset_uv_cm':[0,0]}
    recipe['trial_pieces'] = ['p0','p1']
    recipe['pins'] = []
    recipe['colliders'] = [{**{k:body_identity[k] for k in ('object','dimensions_cm','geometry_sha256','outer_thickness_cm','inner_thickness_cm')},
                           'role':'mannequin','tolerance_cm':.01}]
    recipe['phases']['mount']['gravity_m_s2'] = [0,0,-.5]
    recipe['phases']['mount']['frames'] = 8
    recipe['phases']['drape']['frames'] = 12
    # Open front boundaries can meet during release; the physical solver must
    # retain self-contact now checked throughout the motion, not only at its end.
    recipe['phases']['drape']['self_collision'] = True
    recipe['no_collision_reason'] = ''
    atomic_json(project.root / 'recipe.json', recipe)
    extracted = project.data / 'reconstruction/extracted'
    extract_package(project.root / project.state()['components']['garment.coat']['package']['path'], extracted)
    created = dispatch(str(project.root), 'garment', {'package_dir':extracted.relative_to(project.root).as_posix(),'recipe_path':'recipe.json'})
    payload = read_json(project.root / created['derived_mesh'])
    plan = {'version':1,'component_id':'garment.coat','source_refs':['fixture:'+name],
        'mapping_sha256':map_digest(payload),'preform':{'panels':frames},
        'assembly':{'max_initial_gap_cm':1,'max_displacement_cm':2,'max_step_cm':.05,
            'iterations':160,'neighborhood_rings':3,'closure_support_release':1},
        'consolidation':{'weld_gap_cm':.15},'quality':copy.deepcopy(recipe['mesh']),
        'cloth':{'mount_release_steps':[0,1/3,2/3,1]},
        'supports':{'temporary':[],'drape':[],'functional':[]},
        'collision':{'required':True,'clearance_cm':.1,'source_ref':'fixture:fixed-closed-target'}}
    for key in ('spacing_cm','max_boundary_error_cm','max_vertices'):
        plan['quality'].pop(key)
    # Source-bound upper edge attachments hold the open test shell for draping.
    plan['supports']['drape'] = [{'id':'upper-'+pid,'piece':pid,'edge':'top','weight':.7,'source_ref':'fixture:upper-support:'+pid} for pid in data['pieces']]
    plan['supports']['temporary'] = [{'id':'mount-'+pid,'piece':pid,'edge':'bottom','weight':.2,'source_ref':'fixture:temporary-hem:'+pid} for pid in data['pieces']]
    atomic_json(project.root / 'plan.json', plan)
    results = {}
    args = {'component_id':'garment.coat','recipe_path':'recipe.json','plan_path':'plan.json'}
    for stage in ('preposition','mount','close','consolidate','relax','drape'):
        results[stage] = dispatch(str(project.root),'transition_pattern_assembly',{**args,'stage':stage})
        atomic_json(OUT / (name+'-progress.json'),results)
        if stage == 'close':
            # Reopen the persisted checkpointed stage, including new IDs/maps.
            session = read_json(project.data/'blender/session.json')
            bpy.ops.wm.open_mainfile(filepath=session['working'],load_ui=False,use_scripts=False)
    if name == 'bodice-five':
        for operation, arguments in [('transition_pattern_assembly',{**args,'stage':'close'}),
                ('freeze_sewn',{'component_id':'garment.coat','recipe_path':'recipe.json'})]:
            try:
                dispatch(str(project.root),operation,arguments)
            except StudioError as exc:
                assert ('sequential' in str(exc) if operation=='transition_pattern_assembly' else 'qualified drape' in str(exc)),str(exc)
                dispatch(str(project.root),'restore_checkpoint',{})
            else:
                raise AssertionError('Expected refusal of repeated closure/unqualified freeze')
    obj = bpy.data.objects[results['drape']['object']]
    continuous = read_json(project.root/obj['a3d_sewing_mesh'])
    assert continuous['rest_mode']=='assembled_3d'
    assert len(continuous['source_rest_triangles_cm'])==len(continuous['faces'])
    assert 'A3D.FlatRest' not in obj.data.shape_keys.key_blocks
    assert results['consolidate']['consolidation']['preserved_links']==['side-4']
    for stage in ('mount','relax','drape'):
        for run in results[stage]['cloth_runs']:
            assert run['validation_contract']['version']==2
            assert run['final_contact']['ok'] is True
            for frame in run['frames']:
                assert frame['quality']['status']=='PASS'
                assert frame['quality']['metrics']['metric_version']==2
                assert frame['quality']['metrics']['validator_version']=='cloth-metrics/2'
                assert frame['quality']['metrics']['min_principal_stretch']>=recipe['mesh']['min_stretch']
                assert frame['quality']['metrics']['max_principal_stretch']<=recipe['mesh']['max_stretch']
                assert frame['contact']['ok'] is True
    for stage in ('relax','drape'):
        for run in results[stage]['cloth_runs']:
            assert run['executed']['collisions']['use_self_collision'] is True
            assert not run['executed']['settings']['use_sewing_springs']
            assert run['executed']['rest_shape_key']=='A3D.AssembledRest'
            assert not run['support_transition']['temporary_supports_active']
    assert read_json(project.data/'source/package/garment.json')==data
    views(name,obj)
    master = OUT / (name+'-master-v001.blend')
    bpy.ops.wm.save_as_mainfile(filepath=str(master),copy=True)
    assert sha(original)==source_hash
    assert collider_info(bpy.data.objects['SYNTHETIC_FIXED_TARGET'])==body_identity
    return {'status':'PASS_MECHANICS_ONLY','stages':results,'master':str(master),
            'source_garment_sha256':digest(data),
            'source_preserved':True,'synthetic':True,'fitting':'NOT_QUALIFIED','artistic':'NOT_APPROVED'}


results = {}
for name, asymmetric, perturb in [('bodice-five',False,False),('bodice-five-perturbed',False,True),
                                   ('sleeveless-asymmetric',True,False),('sleeveless-asymmetric-perturbed',True,True)]:
    try:
        results[name] = run_case(name,asymmetric,perturb)
    except Exception as exc:
        results[name] = {'status':'FAIL','error':str(exc),'type':type(exc).__name__}
        atomic_json(OUT / 'result.json',results)
        raise
    atomic_json(OUT / 'result.json',results)
for name in ('bodice-five','sleeveless-asymmetric'):
    assert results[name]['source_garment_sha256']==results[name+'-perturbed']['source_garment_sha256']
print('NATIVE_PATTERN_ASSEMBLY_RESULT='+str(OUT / 'result.json'),flush=True)
