"""Two overlapping source layers joined at one edge in one native Cloth object."""
import copy
import math
from pathlib import Path
import sys
import bpy
ROOT = Path(__file__).resolve().parents[1]; sys.path.insert(0, str(ROOT))
from a3d.core import atomic_json, digest, read_json, sha
from a3d.dressing import layer_collision_selection, sewing_graph_digest
from a3d.pattern_assembly import map_digest
from blender.sewing import grid_probe, make_object, simulate_object


def run(output):
    output = Path(output); output.mkdir(parents=True, exist_ok=True)
    payload = grid_probe(2., two=True); count = len(payload['rest_cm'])//2
    for i in range(len(payload['placed_cm'])):
        u, v, _ = payload['rest_cm'][i]
        panel = int(i >= count)
        payload['placed_cm'][i] = [panel*.3, v, 6.-(10.-u if panel else u)]
    payload['seams']['coupon'].update(piece_a='synthetic-0', piece_b='synthetic-1')
    atomic_json(output/'source.json', payload)
    reference = {'path': 'source.json', 'sha256': sha(output/'source.json')}
    layers = {'version': 1, 'source_ref': reference, 'mode': 'ordered', 'interaction': 'one_way_declared',
        'nodes': [{'id': 'inner', 'kind': 'garment', 'panels': ['synthetic-0'], 'colliders': [], 'source_ref': reference},
                  {'id': 'outer', 'kind': 'garment', 'panels': ['synthetic-1'], 'colliders': [], 'source_ref': reference}],
        'inside_to_outside': [['inner', 'outer']]}
    plan = {'layers': layers, 'layer_execution': {'version': 1, 'mode': 'joint_coupled_single_object',
            'source_ref': reference, 'source_mapping_sha256': map_digest(payload), 'sewing_graph_sha256': sewing_graph_digest(payload)}}
    selected = layer_collision_selection(payload, plan)
    assert selected['status'] == 'LAYER_COLLIDERS_SELECTED' and selected['execution'] == 'joint_coupled_single_object'
    recipe = read_json(ROOT/'templates/sewing-recipe.json')
    profile = recipe['phases']['mount']
    profile.update(frames=96, gravity_m_s2=[0., 0., -.01], self_collision=True, self_distance_cm=.1,
                   collision_distance_cm=.15)
    profile['execution_control'] = {'max_seconds': 20., 'min_frames': 8, 'window_frames': 3,
                                    'velocity_tolerance_cm_s': .5}
    recipe['limits'].update(max_seam_gap_cm=.2, max_displacement_cm=2., min_movement_cm=.0001)
    # This fixture's declared limits are frozen before executing any frame.
    criteria = {'recipe': recipe, 'initial_layer_separation_cm': .3,
                'source_metric_immutable': True, 'one_cloth_object_required': True,
                'all_source_permanent_pairs_required': True, 'qualification': 'COUPLED_COUPON_ONLY'}
    atomic_json(output/'criteria.json', criteria); atomic_json(output/'source.json', payload)
    code_paths = ['a3d/core.py', 'a3d/dressing.py', 'a3d/pattern_assembly.py', 'a3d/sewing.py',
                  'a3d/cloth_metrics.py', 'a3d/contact_geometry.py', 'a3d/sewing_diagnostics.py',
                  'a3d/simulation_control.py', 'blender/sewing.py', 'blender/cloth_contacts.py',
                  'blender/pattern_assembly.py', 'blender/regional_cloth.py',
                  'tests/native_joint_layers.py', 'schemas/sewing-recipe.schema.json',
                  'schemas/pattern-assembly.schema.json']
    code_identity = {path: sha(ROOT/path) for path in code_paths}
    before = digest(payload); obj = make_object(payload, 'TEST.JointLayerCoupon')
    positions, report = simulate_object(obj, payload, recipe, 'mount', [], [],
        save_progress=lambda value: atomic_json(output/'progress.json', value),
        save_diagnostic=lambda value: atomic_json(output/'failure.json', value))
    assert report['simulation'] == 'PASS' and digest(payload) == before
    assert report['execution_control']['stop_reason'] == 'MEASURED_CONVERGENCE'
    assert report['final_gap_cm'] <= .2 and report['final_gap_cm'] < report['initial_gap_cm']*.95
    assert len(positions) == len(payload['rest_cm'])
    assert all(sha(ROOT/path) == value for path, value in code_identity.items())
    atomic_json(output/'receipt.json', {'status': 'JOINT_COUPLED_COUPON_PASS', 'selection': selected,
        'simulation': report, 'source_unchanged': True, 'blender_version': bpy.app.version_string,
        'source_code': code_identity, 'source_code_sha256': digest(code_identity),
        'full_garment': 'NOT_EXECUTED', 'bidirectional_external_cloth': 'NOT_SUPPORTED',
        'fitting': 'NOT_EXECUTED', 'production_connection': False})


if __name__ == '__main__': run(sys.argv[sys.argv.index('--')+1])
