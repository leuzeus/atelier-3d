"""Isolated 0.4 multicomponent receipt-loss and 0.5.3 recovery proof.

Requires --legacy-root pointing to the public 0.4.0 source snapshot.
Imports coat, hood and belt through real old dispatch calls, modifies the coat
through a real guarded old script, then recovers proof without loading a scene.
No consumer project, live Blender MCP or physical simulation is used.
"""
import copy
import importlib
import json
import sys
import uuid
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))
import bpy
from a3d.core import StudioError, atomic_json, read_json, sha
from a3d.packages import build_package, extract_package
from a3d.planning import propose, build_board
from a3d.store import Project
from a3d.tools import blender_operation
from tests.support import (asset, garment_source, construction_dossier, png,
                           prepare_synthetic_exploded, PROVENANCE)

legacy = Path(sys.argv[sys.argv.index('--legacy-root') + 1]).resolve(strict=True)
assert read_json(legacy / '.codex-plugin/plugin.json')['version'] == '0.4.0'
root = ROOT / ('work/native-multigarment-' + uuid.uuid4().hex)
root.mkdir()
bpy.context.preferences.filepaths.temporary_directory = str(root)
bpy.context.preferences.filepaths.save_version = 0
spec = asset(True)
ids = ['garment.coat', 'garment.hood', 'garment.belt']
spec['components'] = [{**copy.deepcopy(spec['components'][0]), 'id': cid} for cid in ids]
project = Project.create(root / 'project', spec)
atomic_json(project.data / 'evidence/brief.json', {'brief': 'Synthetic multicomponent regression only'})
project.evidence('brief', '.a3d/evidence/brief.json')
project.transition('SPECIFIED', 'brief'); project.transition('REFERENCES_READY', 'brief')
(project.data / 'source/original.png').write_bytes(png())
project.evidence('reference.original', '.a3d/source/original.png')
project.gate('references', True, 'Synthetic references only', ['brief', 'reference.original'], 'test:references')
project.transition('REFERENCES_APPROVED', 'brief'); project.transition('ANALYZED', 'brief')
propose(project)
for cid in ids:
    project.gate('route.' + cid, True, 'Synthetic route only', ['pipeline-proposal'], 'test:route')
    project.resolve_route(cid, 'PATTERN_SEWN')
project.transition('ROUTED', 'brief')
for cid in ids:
    source = project.data / 'source' / cid
    data = garment_source(source); data['component_id'] = cid
    atomic_json(source / 'garment.json', data)
    package = project.data / 'packages' / (cid + '.garmentpkg')
    build_package(source, package, spec['id'], cid, 'PATTERN_SEWN', PROVENANCE)
    project.bind_package(cid, package.relative_to(project.root).as_posix())
project.transition('PACKAGED', 'brief')
garment_source(project.data / 'source/package')  # Input expected by the shared synthetic dossier helper.
dossier = construction_dossier(project, True)
dossier['components'] = {cid: copy.deepcopy(dossier['components']['garment.coat']) for cid in ids}
dossier['exploded']['annotations'] = [{'component_id':cid,'piece_id':piece['id'],
    'anchor_px':[10 + ci * 16,20 + pi * 20], 'label_position_px':[3 + ci * 16,20 + pi * 20]}
    for ci,cid in enumerate(ids) for pi,piece in enumerate(dossier['components'][cid]['pieces'])]
prepare_synthetic_exploded(project, dossier)
build_board(project, '.a3d/evidence/construction.json')
project.gate('construction', True, 'Synthetic multicomponent board only', ['construction-board'], 'test:board')
project.transition('RECONSTRUCTING', 'brief')
extracted = {}
for cid in ids:
    extracted[cid] = project.data / 'reconstruction' / cid
    component = project.state()['components'][cid]
    extract_package(project.root / component['package']['path'], extracted[cid])
    recipe = read_json(ROOT / 'templates/sewing-recipe.json'); recipe['component_id'] = cid
    atomic_json(project.root / (cid + '.recipe.json'), recipe)
codes = {op: blender_operation(str(project.root), op, {})['code'] for op in ('inspect', 'resume')}
gates_before = copy.deepcopy(project.state()['gates'])
source_hashes = {cid: sha(extracted[cid] / 'garment.json') for cid in ids}
package_hashes = {cid: sha(project.root / project.state()['components'][cid]['package']['path']) for cid in ids}
bpy.ops.wm.read_factory_settings(use_empty=True)
bpy.ops.wm.save_as_mainfile(filepath=str(root / 'original.blend'))
original_hash = sha(root / 'original.blend')
for name in list(sys.modules):
    if name in ('a3d', 'blender') or name.startswith(('a3d.', 'blender.')):
        del sys.modules[name]
sys.path[:] = [str(legacy)] + [entry for entry in sys.path if Path(entry or '.').resolve() != ROOT]
importlib.invalidate_caches()
from blender.operations import dispatch as old_dispatch
session = old_dispatch(str(project.root), 'prepare', {})
old_imports = []
for cid in ids:
    old_imports.append(old_dispatch(str(project.root), 'garment', {
        'package_dir': extracted[cid].relative_to(project.root).as_posix()}))
global_receipt = project.data / 'blender/garment-receipt.json'
assert read_json(global_receipt)['object'] == 'A3D.garment.belt'
global_bytes = global_receipt.read_bytes()
script = project.root / 'synthetic-densify.py'
script.write_text('''import bpy,bmesh
obj=bpy.data.objects['A3D.garment.coat']
bm=bmesh.new();bm.from_mesh(obj.data)
bmesh.ops.subdivide_edges(bm,edges=list(bm.edges),cuts=1,use_grid_fill=True)
bm.to_mesh(obj.data);bm.free();obj.data.update()
obj.shape_key_add(name='Basis');obj.shape_key_add(name='LegacyFlatRest')
''', encoding='utf-8')
atomic_json(project.root / 'old-plan.json', {'component_id':'garment.coat','type':'cloth',
    'frame_start':1,'frame_end':2,'quality':2,'collision_components':[],'baked':False,'max_frames':2})
old_dispatch(str(project.root), 'run_script', {'purpose':'simulate','path':script.name,
    'sha256':sha(script),'component_ids':['garment.coat'],'simulation_plan':'old-plan.json'})
bpy.ops.ed.undo_push(message='Synthetic dirty multicomponent scene')
assert bpy.data.is_dirty


def execute(code):
    namespace = {}; exec(code, namespace); return namespace['result']


inspection = execute(codes['inspect'])
assert inspection['runtime']['version'] == read_json(ROOT / 'plugin.json')['version']
from a3d.tools import blender_operation as current_operation
from blender.legacy import (all_data_ids, checkpoint_import_proof, legacy_snapshot,
                            validate_legacy_panels)
objects = {cid: bpy.data.objects['A3D.' + cid] for cid in ids}
snapshots = {cid: legacy_snapshot(obj) for cid, obj in objects.items()}
assert len(objects['garment.coat'].data.vertices) > old_imports[0]['vertices']
resume = execute(codes['resume'])
assert resume['dirty_before'] and resume['dirty_after'] and resume['working_file_unchanged']
state_before = project.state(); context_before = (bpy.data.filepath, bpy.data.is_dirty, all_data_ids())
codes['verify'] = current_operation(str(project.root), 'verify_legacy_import', {
    'package_dir': extracted['garment.coat'].relative_to(project.root).as_posix(),
    'checkpoint_receipt': '.a3d/blender/garment-receipt.json'})['code']
proof = execute(codes['verify'])
assert proof['checked_only'] and proof['observed']['object'] == 'A3D.garment.coat'
assert proof['observed']['vertices'] == old_imports[0]['vertices']
assert proof['checkpoint'] == old_imports[2]['checkpoint']
assert (bpy.data.filepath, bpy.data.is_dirty, all_data_ids()) == context_before
assert project.state() == state_before and global_receipt.read_bytes() == global_bytes
data = read_json(extracted['garment.coat'] / 'garment.json')
package_sha = project.state()['components']['garment.coat']['package']['sha256']
script_paths = [p.relative_to(project.root).as_posix() for p in (project.data / 'blender').glob('script-*.json')]
try:
    validate_legacy_panels(project, objects['garment.coat'], data, package_sha,
                           snapshots['garment.coat'], script_paths)
except Exception as error:
    assert type(error).__name__ == 'StudioError' and 'does not identify' in str(error)
else:
    raise AssertionError('The original 0.5.2 prerequisite must reproduce')

# Negative recovery cases are read-only calls: no artificial pending mutation.
record = read_json(global_receipt)
saved_checkpoint = project.root / record['checkpoint']['path']
checkpoint_bytes = saved_checkpoint.read_bytes()
saved_checkpoint.write_bytes(b'changed-checkpoint')
try:
    checkpoint_import_proof(project, objects['garment.coat'].name, data, package_sha,
                            '.a3d/blender/garment-receipt.json')
except Exception as error:
    assert type(error).__name__ == 'StudioError' and 'checkpoint' in str(error)
else:
    raise AssertionError('Changed checkpoint must be refused')
saved_checkpoint.write_bytes(checkpoint_bytes)
for target, fingerprint in (('A3D.missing', package_sha), ('A3D.garment.coat', '0' * 64)):
    try:
        checkpoint_import_proof(project, target, data, fingerprint, '.a3d/blender/garment-receipt.json')
    except Exception as error:
        assert type(error).__name__ == 'StudioError', repr(error)
    else:
        raise AssertionError('Foreign object/package must be refused')
foreign_data = copy.deepcopy(data); foreign_data['component_id'] = 'garment.other'
try:
    checkpoint_import_proof(project, 'A3D.garment.coat', foreign_data, package_sha,
                            '.a3d/blender/garment-receipt.json')
except Exception as error:
    assert type(error).__name__ == 'StudioError' and 'foreign component/package' in str(error)
else:
    raise AssertionError('Foreign component must be refused')
assert (bpy.data.filepath, bpy.data.is_dirty, all_data_ids()) == context_before
assert project.state() == state_before

receipts = {}
for cid in ids:
    args = {'package_dir':extracted[cid].relative_to(project.root).as_posix(),
            'recipe_path':cid + '.recipe.json','rebuild':True,'migrate_legacy':True}
    if cid != 'garment.belt':
        args['legacy_checkpoint_receipt'] = '.a3d/blender/garment-receipt.json'
    if cid == 'garment.coat':
        args.update(legacy_snapshot_sha256=snapshots[cid], legacy_script_receipts=script_paths)
    result = execute(current_operation(str(project.root), 'garment', args)['code'])
    receipts[cid] = result['receipt']
    obj = objects[cid]
    assert obj.get('a3d_role') == 'archived-legacy-panels' and not obj.get('a3d_component_id')
    assert not obj.get('a3d_sewing_mesh') and legacy_snapshot(obj) == snapshots[cid]
    new = bpy.data.objects[result['object']]
    assert new.get('a3d_role') == 'simulation' and new.data != obj.data
    assert new['a3d_garment_receipt'] == result['receipt']['path']
    stored = read_json(project.root / result['receipt']['path'])
    assert stored['component_id'] == cid and stored['package_sha256'] == package_hashes[cid]
    assert stored['result']['legacy_archive']['before_sha256'] == snapshots[cid]
    assert stored['result']['legacy_archive']['after_sha256'] == snapshots[cid]
    assert global_receipt.read_bytes() == global_bytes
    for other in ids[ids.index(cid)+1:]:
        assert objects[other].get('a3d_component_id') == other and legacy_snapshot(objects[other]) == snapshots[other]
assert objects['garment.coat'].data.shape_keys.key_blocks.get('LegacyFlatRest')
for cid in ids:
    assert sha(project.root / receipts[cid]['path']) == receipts[cid]['sha256']
rebuild = execute(current_operation(str(project.root), 'garment', {
    'package_dir':extracted['garment.coat'].relative_to(project.root).as_posix(),
    'recipe_path':'garment.coat.recipe.json','rebuild':True})['code'])
assert rebuild['receipt']['path'] != receipts['garment.coat']['path']
assert sha(project.root / receipts['garment.coat']['path']) == receipts['garment.coat']['sha256']
assert len(list((project.data / 'blender/garment-receipts/garment.coat').glob('*.json'))) == 2
assert len(list((project.data / 'blender/garment-receipts/garment.hood').glob('*.json'))) == 1
assert len(list((project.data / 'blender/garment-receipts/garment.belt').glob('*.json'))) == 1
assert project.state()['gates'] == gates_before and not project.state().get('pending_blender_operation')
assert all(sha(extracted[cid] / 'garment.json') == source_hashes[cid] for cid in ids)
assert sha(root / 'original.blend') == original_hash and global_receipt.read_bytes() == global_bytes
report = {'root':str(root),'blender':bpy.app.version_string,'runtime':inspection['runtime'],
    'real_0_4_imports':ids,'historical_receipt_overwritten':'REPRODUCED',
    'checkpoint_object_readback':proof,'temporary_ids_removed_and_context_preserved':'PASS',
    'altered_checkpoint_foreign_object_and_package_refused':'PASS',
    'densified_coat_archive_with_rest_preserved':'PASS','siblings_preserved':'PASS',
    'immutable_component_package_receipts':'PASS','rebuild_keeps_previous_receipt':'PASS',
    'historical_global_receipt_unchanged':'PASS','gates_sources_and_original_preserved':'PASS',
    'simulation':'NOT_EXECUTED','consumer_project_and_blender':'UNTOUCHED'}
atomic_json(root / 'result.json', report)
print('A3D_MULTIGARMENT_RESULT=' + str(root / 'result.json'))
