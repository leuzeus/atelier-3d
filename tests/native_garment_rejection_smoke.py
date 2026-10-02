"""Isolated native garment preflight rejections, before any Cloth frame."""
import copy
import sys
import uuid
from pathlib import Path

ROOT=Path(__file__).resolve().parents[1];sys.path.insert(0,str(ROOT))
import bpy
from a3d.core import StudioError, atomic_json, read_json, sha
from a3d.packages import extract_package
from blender.operations import dispatch
from blender.sewing import collider_info, mesh_digest
from tests.support import ready_project

root=ROOT/('work/native-garment-rejection-'+uuid.uuid4().hex);root.mkdir()
bpy.context.preferences.filepaths.temporary_directory=str(root)
bpy.context.preferences.filepaths.save_version=0
project=ready_project(root/'project',True)
bpy.ops.wm.read_factory_settings(use_empty=True)
original=root/'original.blend';bpy.ops.wm.save_as_mainfile(filepath=str(original));original_sha=sha(original)
dispatch(str(project.root),'prepare',{})
recipe=read_json(ROOT/'templates/sewing-recipe.json');atomic_json(project.root/'recipe.json',recipe)
component=project.state()['components']['garment.coat'];package_sha=component['package']['sha256']
extracted=project.data/'reconstruction/extracted';extract_package(project.root/component['package']['path'],extracted)
args={'package_dir':extracted.relative_to(project.root).as_posix(),'recipe_path':'recipe.json'}
built=dispatch(str(project.root),'garment',args)
good_obj=bpy.data.objects[built['object']];good_sha=mesh_digest(good_obj)
gates=copy.deepcopy(project.state()['gates']); receipt_sha=built['receipt']['sha256']


def reject(expected):
    try:dispatch(str(project.root),'garment',{**args,'rebuild':True})
    except StudioError as exc:
        assert expected in str(exc),str(exc)
        ref=exc.garment_diagnostic
    else:raise AssertionError('Expected native preflight rejection')
    pending=project.state()['pending_blender_operation']
    assert pending['status']=='failed' and pending['diagnostic']==ref
    assert not any(m.type=='CLOTH' for o in bpy.data.objects for m in o.modifiers)
    assert mesh_digest(bpy.data.objects[built['object']])==good_sha
    assert sha(project.root/built['receipt']['path'])==receipt_sha
    directory=(project.root/ref['path']).parent
    inspect_args={'component_id':'garment.coat','attempt_dir':directory.relative_to(project.root).as_posix()}
    before=sha(project.db); report=dispatch(str(project.root),'inspect_garment_failure',inspect_args)
    assert sha(project.db)==before and not report['accepted'] and report['simulation']=='NOT_EXECUTED'
    try:dispatch(str(project.root),'garment',{**args,'rebuild':True})
    except StudioError as exc:assert 'restore_checkpoint before another mutation' in str(exc),str(exc)
    else:raise AssertionError('Inspection cleared the recovery guard')
    checksum=sha(project.root/ref['path']);dispatch(str(project.root),'restore_checkpoint',{})
    assert sha(project.root/ref['path'])==checksum
    assert dispatch(str(project.root),'inspect_garment_failure',inspect_args)==report
    assert project.state()['gates']==gates and not project.state().get('pending_blender_operation')
    assert mesh_digest(bpy.data.objects[built['object']])==good_sha
    assert project.state()['components']['garment.coat']['package']['sha256']==package_sha
    assert sha(original)==original_sha
    return report


recipe['placements']['back']['rotation_degrees']=[90,0,0]
atomic_json(project.root/'recipe.json',recipe)
orientation=reject('Placed seam directions oppose each other')
bad=orientation['directions']['violations'][0]
assert bad['seam_id']=='torso-right' and bad['edge_a']=='right' and bad['edge_b']=='left'
assert bad['cosine']<-.5 and bad['threshold']==-.5
assert orientation['directions']['seams']['torso-right']['endpoint_chord_cosine']<-.99
assert bad['previous_pair'][0]['rest_uv_cm'] and bad['next_pair'][1]['position_cm']
recipe=read_json(ROOT/'templates/sewing-recipe.json')
recipe['placements']['front'].update(mode='cylinder',radius_cm=.1)
atomic_json(project.root/'recipe.json',recipe)
quality=reject('Collapsed or distorted placement')
assert quality['outlier_edges'] and quality['vertex_count']>0
recipe=read_json(ROOT/'templates/sewing-recipe.json')
bpy.ops.mesh.primitive_uv_sphere_add(segments=24, ring_count=12, radius=.15, location=(.1,-.15,1.))
body=bpy.context.object;body.name='SYNTHETIC_CONTACT_VOLUME';body.modifiers.new('Collision','COLLISION')
body.collision.thickness_outer=.001;body.collision.thickness_inner=.001
info=collider_info(body)
recipe['colliders']=[{k:info[k] for k in ('object','dimensions_cm','geometry_sha256','outer_thickness_cm','inner_thickness_cm')}]
recipe['colliders'][0].update(role='mannequin',tolerance_cm=.01);recipe['no_collision_reason']=''
atomic_json(project.root/'recipe.json',recipe)
contact=reject('Cloth starts inside a collider')
assert contact['initial_contacts']
assert all(c['piece']=='front' and c['collider']=='SYNTHETIC_CONTACT_VOLUME' and c['depth_cm']>c['threshold_cm']
    for c in contact['initial_contacts'])
assert all(c['rest_uv_cm'] and len(c['position_cm'])==3 and len(c['surface_normal'])==3 for c in contact['initial_contacts'])
assert not list((project.data/'blender/sewing').glob('*-local.json'))
atomic_json(root/'result.json',{'status':'PASS','blender':bpy.app.version_string,'orientation_localized':'PASS',
    'contact_localized':'PASS','quality_rejection_preserved':'PASS','immutable_diagnostics_survive_restore':'PASS','state_mesh_package_receipt_board_preserved':'PASS',
    'pending_recovery_guard':'PASS','orientation':orientation,'contact':contact,'cloth':'NOT_EXECUTED','consumer':'UNTOUCHED'})
print('A3D_REJECTION_RESULT='+str(root/'result.json'),flush=True)
