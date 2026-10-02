"""Isolated native mounting diagnostics: two tapered sleeve panels, armhole coupons,
and a closed posed-arm collider. Not an anatomical torso or a garment fit proof.
"""
import copy
import math
import sys
import uuid
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))
import bpy
from mathutils import Euler, Vector
from a3d.core import StudioError, atomic_json, read_json, sha
from a3d.packages import extract_package
from blender.operations import dispatch
from blender.sewing import collider_info, mesh_digest
import tests.support as support

root = ROOT/('work/native-sewing-placement-'+uuid.uuid4().hex); root.mkdir()
bpy.context.preferences.filepaths.temporary_directory = str(root)
bpy.context.preferences.filepaths.save_version = 0
original_source = support.garment_source


def source(path):
    original_source(path); data = read_json(path/'garment.json')
    for pid, panel in data['pieces'].items():
        panel['edges']['bottom'] = [0, 1]
        if pid.startswith('sleeve'):
            panel['vertices'] = [[0, 0], [20, 0], [18, 40], [2, 40]]
    data['seams'] = [{'id': sid, 'piece_a': a, 'edge_a': ea, 'piece_b': b, 'edge_b': eb, 'orientation': 'forward'}
        for sid, a, ea, b, eb in (
            ('body-side', 'front', 'right', 'back', 'left'), ('body-opening', 'front', 'left', 'back', 'right'),
            ('sleeve-side', 'sleeve-left', 'right', 'sleeve-right', 'left'),
            ('sleeve-opening', 'sleeve-left', 'left', 'sleeve-right', 'right'),
            ('armhole-front', 'front', 'top', 'sleeve-left', 'bottom'),
            ('armhole-back', 'back', 'top', 'sleeve-right', 'bottom'))]
    atomic_json(path/'garment.json', data)
    polygons = ''.join('<polygon id="'+pid+'" points="'+' '.join(str(x)+','+str(y) for x, y in p['vertices'])+'"/>'
        for pid, p in data['pieces'].items())
    (path/'pattern.svg').write_text('<svg xmlns="http://www.w3.org/2000/svg" width="20cm" height="40cm" viewBox="0 0 20 40">'+polygons+'</svg>')


support.garment_source = source
try:
    project = support.ready_project(root/'project', True)
finally:
    support.garment_source = original_source
bpy.ops.wm.read_factory_settings(use_empty=True)
original = root/'original.blend'; bpy.ops.wm.save_as_mainfile(filepath=str(original)); original_sha = sha(original)
dispatch(str(project.root), 'prepare', {})
pose = Euler((0, math.radians(35), 0), 'XYZ').to_matrix()
rotation = [math.degrees(x) for x in (pose@Euler((math.pi/2, 0, 0), 'XYZ').to_matrix()).to_euler('XYZ')]
bpy.ops.mesh.primitive_cylinder_add(vertices=48, radius=.055, depth=1.05)
arm = bpy.context.object; arm.name = 'SYNTHETIC_POSED_ARM'
# Bake the pose into the auxiliary collider's vertices, retaining unit scale.
for v in arm.data.vertices:
    v.co = pose@(v.co+Vector((0, 0, .4)))
arm.data.update(); arm.color = (.5, .5, .5, 1)
arm.modifiers.new('Collision', 'COLLISION')
arm.collision.thickness_outer = .001; arm.collision.thickness_inner = .001
info = collider_info(arm)
recipe = read_json(ROOT/'templates/sewing-recipe.json')
data = read_json(project.data/'source/package/garment.json')
recipe['seams'] = {s['id']: {'kind': 'closure' if 'opening' in s['id'] else 'permanent',
    'ease_b_over_a': 0, 'tolerance_relative': .005} for s in data['seams']}
recipe['colliders'] = [{k: info[k] for k in ('object', 'dimensions_cm', 'geometry_sha256', 'outer_thickness_cm', 'inner_thickness_cm')}]
recipe['colliders'][0].update(role='mannequin', tolerance_cm=.01); recipe['no_collision_reason'] = ''
recipe['trial_pieces'] = list(data['pieces'])
recipe['pins'] = [{'piece': pid, 'edge': 'top' if pid.startswith('sleeve') else 'bottom', 'weight': .02}
    for pid in data['pieces']]
recipe['placements'] = {pid: {'mode': 'flat', 'position_cm': list(pose@Vector((-10,
    7 if pid in ('back', 'sleeve-right') else -7, 41 if pid.startswith('sleeve') else 0))),
    'rotation_degrees': rotation, 'radius_cm': 20/math.pi, 'origin_2d_cm': [0, 0]} for pid in data['pieces']}
atomic_json(project.root/'recipe.json', recipe)
component = project.state()['components']['garment.coat']
extracted = project.data/'reconstruction/extracted'; extract_package(project.root/component['package']['path'], extracted)
build_args = {'package_dir': extracted.relative_to(project.root).as_posix(), 'recipe_path': 'recipe.json'}
constructed = dispatch(str(project.root), 'garment', build_args)
args = {'component_id': 'garment.coat', 'recipe_path': 'recipe.json'}


def inspect_preserved():
    obj = bpy.data.objects[constructed['object']]
    before = (sha(project.db), sha(project.root/constructed['derived_mesh']), mesh_digest(obj),
        bpy.context.scene.frame_current, bpy.context.view_layer.objects.active, list(bpy.context.selected_objects))
    report = dispatch(str(project.root), 'inspect_sewing_placement', args)
    assert before == (sha(project.db), sha(project.root/constructed['derived_mesh']), mesh_digest(obj),
        bpy.context.scene.frame_current, bpy.context.view_layer.objects.active, list(bpy.context.selected_objects))
    assert not report['accepted'] and report['simulation'] == 'NOT_EXECUTED'
    return report


flat = inspect_preserved(); atomic_json(root/'flat.json', flat)
assert flat['seams']['sleeve-side']['segments_crossing_collider'] > 0
assert flat['seams']['sleeve-side']['max_gap_cm'] > 20
gates = copy.deepcopy(project.state()['gates']); package_sha = component['package']['sha256']
old_obj = bpy.data.objects[constructed['object']]; old_sha = mesh_digest(old_obj)
recipe['placements'] = {pid: {'mode': 'cylinder', 'position_cm': list(pose@Vector((0, 0, 41 if pid.startswith('sleeve') else 0))),
    'rotation_degrees': rotation, 'radius_cm': 20/math.pi, 'origin_2d_cm': [-20 if pid in ('back', 'sleeve-right') else 0, 0]}
    for pid in data['pieces']}
atomic_json(project.root/'recipe.json', recipe)
constructed = dispatch(str(project.root), 'garment', {**build_args, 'rebuild': True})
cylinder = inspect_preserved(); atomic_json(root/'cylinder.json', cylinder)
assert cylinder['seams']['sleeve-side']['max_gap_cm'] < 4
assert cylinder['seams']['sleeve-side']['segments_crossing_collider'] == 0
assert cylinder['warnings']['permanent_seams_above_final_tolerance']  # taper remains open; not a local PASS
assert mesh_digest(old_obj) == old_sha and old_obj['a3d_role'] == 'archived-simulation'
assert project.state()['gates'] == gates and project.state()['components']['garment.coat']['package']['sha256'] == package_sha
assert sha(original) == original_sha and not project.state().get('pending_blender_operation')
# Negative runtime checks: declared collider drift and active Cloth must fail.
saved_vertex = arm.data.vertices[0].co.copy()
arm.data.vertices[0].co.x += .01; arm.data.update()
try:
    inspect_preserved()
except StudioError as exc:
    assert 'pose or geometry' in str(exc)
else:
    raise AssertionError('Collider drift admitted')
arm.data.vertices[0].co = saved_vertex; arm.data.update()
obj = bpy.data.objects[constructed['object']]; cloth = obj.modifiers.new('ForbiddenActiveCloth', 'CLOTH')
try:
    dispatch(str(project.root), 'inspect_sewing_placement', args)
except StudioError as exc:
    assert 'before Cloth' in str(exc)
else:
    raise AssertionError('Active Cloth inspection admitted')
obj.modifiers.remove(cloth)
# Render the measured derived panels around the posed auxiliary arm, before Cloth.
camera_data = bpy.data.cameras.new('ProofCamera'); camera = bpy.data.objects.new('ProofCamera', camera_data)
bpy.context.scene.collection.objects.link(camera); bpy.context.scene.camera = camera
target = pose@Vector((0, 0, .4)); camera.location = target+Vector((1.8, -3, 1.2))
camera.rotation_euler = (target-camera.location).to_track_quat('-Z', 'Y').to_euler()
camera_data.type = 'ORTHO'; camera_data.ortho_scale = 1.3
scene = bpy.context.scene; scene.render.engine = 'BLENDER_WORKBENCH'
scene.render.resolution_x = 900; scene.render.resolution_y = 900; scene.render.resolution_percentage = 100
scene.display.shading.color_type = 'OBJECT'; scene.display.shading.show_cavity = True
obj.color = (.12, .42, .65, 1)
scene.render.image_settings.file_format = 'PNG'; scene.render.filepath = str(root/'posed-arm-placement.png')
bpy.ops.render.render(write_still=True)
atomic_json(root/'result.json', {'status': 'PASS', 'diagnostic': 'PASS', 'synthetic': True,
    'blender': bpy.app.version_string, 'flat_gap_cm': flat['seams']['sleeve-side']['max_gap_cm'],
    'cylinder_gap_cm': cylinder['seams']['sleeve-side']['max_gap_cm'],
    'flat_segments_crossing': flat['seams']['sleeve-side']['segments_crossing_collider'],
    'cylinder_segments_crossing': cylinder['seams']['sleeve-side']['segments_crossing_collider'],
    'read_only_state_mesh_frame_selection': 'PASS', 'source_package_board_preserved': 'PASS',
    'collider_drift_refused': 'PASS', 'active_cloth_refused': 'PASS', 'render': str(root/'posed-arm-placement.png'),
    'local_cloth': 'NOT_EXECUTED', 'real_garment_fit': 'NOT_EXECUTED', 'consumer_project': 'UNTOUCHED'})
print('A3D_PLACEMENT_RESULT='+str(root/'result.json'), flush=True)
