"""Isolated Blender continuity proof; supply an extracted 0.4.0 source snapshot.

blender --background --factory-startup --disable-autoexec --python-exit-code 1
        --python tests/native_continuity_smoke.py -- --legacy-root <snapshot>
No user scene/project or live MCP connection is opened. No physics is run.
"""
import argparse
import copy
import importlib
import math
import sys
import uuid
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))
import bpy
from a3d.core import atomic_json, read_json, sha
from a3d.packages import extract_package
from a3d.tools import blender_operation
from tests.support import ready_project

parser = argparse.ArgumentParser()
parser.add_argument('--legacy-root', required=True)
parser.add_argument('--modified-legacy', action='store_true')
args = parser.parse_args(sys.argv[sys.argv.index('--') + 1:])
legacy = Path(args.legacy_root).resolve(strict=True)
assert read_json(legacy / '.codex-plugin/plugin.json')['version'] == '0.4.0'
root = ROOT / ('work/native-continuity-' + uuid.uuid4().hex)
root.mkdir()
bpy.context.preferences.filepaths.temporary_directory = str(root)
bpy.context.preferences.filepaths.save_version = 0
project = ready_project(root / 'project', True)
component = project.state()['components']['garment.coat']
extracted = project.data / 'reconstruction/extracted'
extract_package(project.root / component['package']['path'], extracted)
recipe = read_json(ROOT / 'templates/sewing-recipe.json')
atomic_json(project.root / 'recipe.json', recipe)
codes = {op: blender_operation(str(project.root), op, {})['code'] for op in ('inspect', 'resume')}
codes['garment'] = blender_operation(str(project.root), 'garment', {
    'package_dir': extracted.relative_to(project.root).as_posix(), 'recipe_path': 'recipe.json',
    'rebuild': True, 'migrate_legacy': True})['code']
gates_before = copy.deepcopy(project.state()['gates'])
package_before = sha(project.root / component['package']['path'])
source_before = sha(extracted / 'garment.json')
bpy.ops.wm.read_factory_settings(use_empty=True)
original = root / 'original.blend'
bpy.ops.wm.save_as_mainfile(filepath=str(original))
original_sha = sha(original)

# Recreate the actual old module cache in this same Blender interpreter.
for name in list(sys.modules):
    if name in ('a3d', 'blender') or name.startswith(('a3d.', 'blender.')):
        del sys.modules[name]
sys.path[:] = [str(legacy)] + [entry for entry in sys.path if Path(entry or '.').resolve() != ROOT]
importlib.invalidate_caches()
from blender.operations import dispatch as legacy_dispatch
assert Path(sys.modules['blender.operations'].__file__).is_relative_to(legacy)
session = legacy_dispatch(str(project.root), 'prepare', {})
old_receipt = legacy_dispatch(str(project.root), 'garment', {'package_dir': extracted.relative_to(project.root).as_posix()})
obj = bpy.data.objects[old_receipt['object']]
assert not obj.get('a3d_role') and not obj.get('a3d_sewing_mesh')
if args.modified_legacy:
    # The old guarded simulate entrypoint allowed topology edits. Reproduce that
    # historical behavior without running physics or importing consumer scripts.
    script = project.root / 'synthetic-legacy-edit.py'
    script.write_text('''import bpy,bmesh
obj=bpy.data.objects['A3D.garment.coat']
bm=bmesh.new();bm.from_mesh(obj.data)
bmesh.ops.subdivide_edges(bm,edges=list(bm.edges),cuts=1,use_grid_fill=True)
bm.to_mesh(obj.data);bm.free();obj.data.update()
obj.shape_key_add(name='Basis');obj.shape_key_add(name='LegacyFlatRest')
''', encoding='utf-8')
    atomic_json(project.root / 'legacy-plan.json', {'component_id':'garment.coat','type':'cloth',
        'frame_start':1,'frame_end':2,'quality':2,'collision_components':[],'baked':False,'max_frames':2})
    legacy_dispatch(str(project.root), 'run_script', {'purpose':'simulate',
        'path':script.name,'sha256':sha(script),'component_ids':['garment.coat'], 'simulation_plan':'legacy-plan.json'})
    assert len(obj.data.vertices) != old_receipt['vertices'] and obj.data.shape_keys
bpy.context.view_layer.objects.active = obj; obj.select_set(True)
bpy.ops.transform.translate(value=(0.003, 0, 0))
bpy.ops.ed.undo_push(message='Synthetic unsaved geometry change')
assert bpy.data.is_dirty, 'Fixture must actually be dirty'
working_hash = sha(Path(session['working']))
session_bytes = (project.data / 'blender/session.json').read_bytes()
state_before = project.state()

def execute(code):
    namespace = {}
    exec(code, namespace)
    return namespace['result']

inspection = execute(codes['inspect'])
assert 'auxiliary_colliders' in inspection and inspection['is_dirty']
assert Path(inspection['runtime']['root']) == ROOT
for name, module in list(sys.modules.items()):
    if name in ('a3d', 'blender') or name.startswith(('a3d.', 'blender.')):
        assert Path(module.__file__).resolve().is_relative_to(ROOT), name
from blender.sewing import mesh_digest
from blender.legacy import legacy_snapshot
old_digest = mesh_digest(obj)
old_snapshot = legacy_snapshot(obj)
assert inspection['objects'][0]['legacy_snapshot_sha256'] == old_snapshot
if args.modified_legacy:
    from a3d.tools import blender_operation as current_operation
    codes['garment'] = current_operation(str(project.root), 'garment', {
        'package_dir': extracted.relative_to(project.root).as_posix(), 'recipe_path':'recipe.json',
        'rebuild':True,'migrate_legacy':True,'legacy_snapshot_sha256':old_snapshot,
        'legacy_script_receipts':[p.relative_to(project.root).as_posix() for p in (project.data/'blender').glob('script-*.json')]})['code']
resume = execute(codes['resume'])
assert resume['dirty_before'] and resume['dirty_after']
assert bpy.data.filepath == session['working'] and bpy.data.is_dirty
assert sha(Path(session['working'])) == working_hash
assert (project.data / 'blender/session.json').read_bytes() == session_bytes
assert project.state() == state_before and mesh_digest(obj) == old_digest
copy_path = project.root / resume['checkpoint']['path']
assert sha(copy_path) == resume['checkpoint']['sha256']
# Read the checkpoint's serialized object, without switching the active file.
with bpy.data.libraries.load(str(copy_path), link=False) as (available, loaded):
    loaded.objects = [obj.name]
copy_obj = loaded.objects[0]
# An unlinked library object has no evaluated matrix_world. Verify serialized
# mesh coordinates and transform properties directly, without linking it.
assert [list(v.co) for v in copy_obj.data.vertices] == [list(v.co) for v in obj.data.vertices]
assert [list(p.vertices) for p in copy_obj.data.polygons] == [list(p.vertices) for p in obj.data.polygons]
assert list(copy_obj.location) == list(obj.location) and copy_obj.location.x != 0
assert list(copy_obj.rotation_euler) == list(obj.rotation_euler)
assert list(copy_obj.scale) == list(obj.scale)
bpy.data.objects.remove(copy_obj, do_unlink=True)

construction = execute(codes['garment'])
assert construction['archived_legacy_panels'] == [obj.name]
assert obj.get('a3d_role') == 'archived-legacy-panels' and not obj.get('a3d_component_id')
assert not obj.get('a3d_sewing_mesh') and mesh_digest(obj) == old_digest
assert legacy_snapshot(obj) == old_snapshot
assert construction['legacy_archive']['before_sha256'] == construction['legacy_archive']['after_sha256'] == old_snapshot
assert construction['legacy_archive']['source_topology_matches'] is not args.modified_legacy
assert construction['legacy_archive']['legacy_validity'] == 'NOT_VALIDATED'
if args.modified_legacy:
    assert obj.data.shape_keys.key_blocks.get('LegacyFlatRest') and any(m.type=='CLOTH' for m in obj.modifiers)
derived = bpy.data.objects[construction['object']]
assert derived.get('a3d_role') == 'simulation' and derived.get('a3d_sewing_mesh')
assert derived.data != obj.data and len(derived.data.vertices) > len(obj.data.vertices)
assert not project.state().get('pending_blender_operation')
assert project.state()['gates'] == gates_before
assert sha(project.root / component['package']['path']) == package_before
assert sha(extracted / 'garment.json') == source_before and sha(original) == original_sha

# Explicit U reversal reproduces the collar formula while leaving flat rest and
# source topology intact. This is a synthetic placement check, not a collar fit.
from blender.sewing import placed_point, build_mesh, preflight
placement = {'mode': 'cylinder', 'radius_cm': 10., 'origin_2d_cm': [0., 0.],
             'rotation_degrees': [90., 0., 0.], 'position_cm': [0., 0., 149.]}
for x,y in ((0.,0.),(5.,2.),(math.pi*5.,7.)):
    default = placed_point([x,y], placement)
    forward = placed_point([x,y], {**placement, 'mirror_u': False})
    reverse = placed_point([x,y], {**placement, 'mirror_u': True})
    assert default == forward
    assert max(abs(a-b) for a,b in zip(reverse, [-10*math.sin(x/10),-10*math.cos(x/10),149+y])) < .0001
data = read_json(extracted / 'garment.json')
forward_recipe = copy.deepcopy(recipe); forward_recipe['placements']['front']['mode'] = 'cylinder'
forward_recipe['placements']['front']['radius_cm'] = 40.
reverse_recipe = copy.deepcopy(forward_recipe); reverse_recipe['placements']['front']['mirror_u'] = True
forward_payload = build_mesh(data, forward_recipe); reverse_payload = build_mesh(data, reverse_recipe)
for key in ('rest_cm', 'faces', 'panels', 'seams', 'pins', 'source_garment_sha256'):
    assert forward_payload[key] == reverse_payload[key], key
assert forward_payload['placed_cm'] != reverse_payload['placed_cm']
assert forward_payload['recipe_mesh_sha256'] != reverse_payload['recipe_mesh_sha256']
try:
    preflight(derived, forward_payload, reverse_recipe)
except Exception as error:
    assert type(error).__name__ == 'StudioError' and 'rebuild' in str(error), str(error)
else:
    raise AssertionError('Changed U direction must invalidate the derived mesh')

# A previously generated resume command must still refuse a foreign live scene.
checkpoint_count = len(list((project.data / 'checkpoints').glob('*.blend')))
bpy.ops.wm.save_as_mainfile(filepath=str(root / 'foreign.blend'))
try:
    execute(codes['resume'])
except Exception as error:
    assert type(error).__name__ == 'StudioError' and 'working copy' in str(error)
else:
    raise AssertionError('Foreign scene must be refused')
assert len(list((project.data / 'checkpoints').glob('*.blend'))) == checkpoint_count
report = {'blender': bpy.app.version_string, 'root': str(root), 'legacy_root': str(legacy),
          'modified_legacy': args.modified_legacy,
          'runtime': inspection['runtime'], 'activation_in_existing_interpreter': 'PASS',
          'dirty_resume_copy_verified': 'PASS', 'foreign_scene_refused': 'PASS',
          'legacy_archive_without_geometry_changes': 'PASS', 'fresh_derived_mapping': 'PASS',
          'board_approvals_and_sources_preserved': 'PASS', 'simulation': 'NOT_EXECUTED',
          'cylinder_u_direction_and_unchanged_rest': 'PASS', 'changed_winding_requires_rebuild': 'PASS',
          'consumer_project_and_open_blender': 'UNTOUCHED'}
atomic_json(root / 'result.json', report)
print('A3D_CONTINUITY_RESULT=' + str(root / 'result.json'))
