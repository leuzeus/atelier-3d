"""Measured native Cloth bending response, not a textile calibration.

Only bending stiffness varies inside each pair. A fixed laboratory clamp is
functional, not a mounting support to be silently removed. Same topology,
source UV, start positions, mass, time, gravity and admission limits per pair.
"""
import copy
import math
import os
from pathlib import Path
import sys

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))

import bpy
from a3d.core import atomic_json, digest, read_json
from a3d.cloth_metrics import evaluate_metrics
from a3d.pattern_assembly import consolidate, map_digest
from blender.preform import preform_coordinates
from blender.sewing import commit_positions, make_object, rest_key_name, simulate_object
from tests.native_pattern_bend import coupon  # main is guarded; no import-time simulation.

OUT = Path(os.environ['A3D_VALIDATION_OUTPUT'])
STIFFNESSES = {'soft': .003, 'stiff': .3}
MIN_OBSERVABLE_RMS_CM = .001  # Prespecified experiment criterion, not a garment tolerance.


def mean(points):
    return [sum(point[k] for point in points)/len(points) for k in range(3)]


def response(payload, start, final):
    tip = sorted({index for panel in payload['panels'].values() for index in panel['edges']['top']})
    clamp = sorted({index for panel in payload['panels'].values() for index in panel['edges']['bottom']})
    tip_before, tip_after = mean([start[i] for i in tip]), mean([final[i] for i in tip])
    return {'free_edge_centroid_start_cm': tip_before, 'free_edge_centroid_final_cm': tip_after,
            'free_edge_displacement_cm': math.dist(tip_before, tip_after),
            'free_edge_vertical_delta_cm': tip_after[2]-tip_before[2],
            'rms_vertex_displacement_cm': math.sqrt(sum(math.dist(a, b)**2 for a, b in zip(start, final))/len(start)),
            'max_clamp_displacement_cm': max(math.dist(start[i], final[i]) for i in clamp),
            'bending_start': evaluate_metrics(payload, start, include_faces=False)['bending'],
            'bending_final': evaluate_metrics(payload, final, include_faces=False)['bending']}


def split_for_consolidation(payload, plan):
    """Two exact source islands, as in physics-02, without importing its runner.

    Duplicate only the declared x=4 partners, preserving world coordinates and
    functional clamp weights. Consolidation restores the same 66-vertex shape.
    No sewn FlatRest or average between distinct UV islands is constructed.
    """
    original = copy.deepcopy(payload)
    rest, placed, faces, panels, mappings, pins = [], [], [], {}, {}, {}
    for side in ('left', 'right'):
        keep = [i for i, p in enumerate(original['rest_cm']) if (p[0] <= 4. if side == 'left' else p[0] >= 4.)]
        mapping = {old: len(rest)+local for local, old in enumerate(keep)}
        mappings[side] = mapping
        for index in keep:
            point = original['rest_cm'][index]
            rest.append([point[0]-(4. if side == 'right' else 0.), point[1], 1000. if side == 'right' else 0.])
            placed.append(original['placed_cm'][index])
            if str(index) in original['pins']:
                pins[str(mapping[index])] = original['pins'][str(index)]
        faces.extend([[mapping[i] for i in face] for face in original['faces'] if all(i in mapping for i in face)])
        edges = {}
        for name, coordinate, value, reverse in [('bottom', 1, 0., False),
                ('right', 0, 4. if side == 'left' else 10., False), ('top', 1, 20., True),
                ('left', 0, 0. if side == 'left' else 4., True)]:
            indices = sorted((i for i in keep if original['rest_cm'][i][coordinate] == value),
                             key=lambda i: original['rest_cm'][i][1-coordinate], reverse=reverse)
            edges[name] = [mapping[i] for i in indices]
        panels[side] = {'indices': list(mapping.values()), 'edges': edges,
                        'boundary': sum((edges[key][:-1] for key in ('bottom', 'right', 'top', 'left')), [])}
    seam = sorted((i for i, point in enumerate(original['rest_cm']) if point[0] == 4.),
                  key=lambda i: original['rest_cm'][i][1])
    payload.update(rest_cm=rest, placed_cm=placed, faces=faces, panels=panels, pins=pins,
                   seams={'join': {'kind': 'permanent', 'piece_a': 'left', 'piece_b': 'right',
                       'parameters': [original['rest_cm'][i][1]/20 for i in seam],
                       'pairs': [[mappings['left'][i], mappings['right'][i]] for i in seam]}})
    plan = copy.deepcopy(plan)
    plan['preform']['panels'] = {pid: {'source_ref': 'metric source island of the same native bent coupon',
        'origin_cm': [0., 0., 0.], 'u_axis': [1., 0., 0.], 'v_axis': [0., 1., 0.]} for pid in panels}
    plan['mapping_sha256'] = map_digest(payload)
    plan['supports']['functional'] = [{'id': 'laboratory-clamp-'+pid, 'source_ref': 'same source bottom edge',
                                      'piece': pid, 'edge': 'bottom', 'weight': 1.} for pid in panels]
    return payload, plan


def main():
    bpy.context.preferences.filepaths.temporary_directory = str(OUT/'tmp')
    bpy.context.preferences.filepaths.save_version = 0
    source, plan = coupon(2.)
    plan['quality'].update(min_angle_degrees=15., min_stretch=.8, max_stretch=1.25)
    source['placed_cm'], preform = preform_coordinates(source, plan)
    source['pins'] = {str(index): 1. for index in source['panels']['sheet']['edges']['bottom']}
    source['pattern_assembly'] = {'version': 2, 'stage': 'relax', 'temporary_supports_active': False,
        'support_transition': {'temporary_supports_active': False, 'functional': 'SOURCED_LABORATORY_CLAMP'},
        'contact_policy': {'clearance_cm': 0.}}
    # Preserve exactly the previous rest coupon's admission limits and time.
    recipe = read_json(ROOT/'templates/sewing-recipe.json')
    recipe['mesh'].update(plan['quality'])
    recipe['limits']['min_movement_cm'] = .001
    recipe['limits']['max_displacement_cm'] = 10.
    recipe['phases']['drape'].update(frames=12, gravity_m_s2=[0., 0., -.5], self_collision=False)
    source_hash = digest(source)
    result = {'status': 'RUNNING', 'purpose': 'MEASURE_BENDING_RESPONSE_NOT_MATERIAL_CALIBRATION',
        'blender_version': bpy.app.version_string, 'blender_build_hash': bpy.app.build_hash.decode(),
        'source_sha256': source_hash, 'source_uv_sha256': digest(source['rest_cm']),
        'faces_sha256': digest(source['faces']), 'initial_geometry_sha256': digest(source['placed_cm']),
        'preform': preform, 'source_cm': source['rest_cm'], 'initial_cm': source['placed_cm'],
        'faces': source['faces'], 'stiffnesses': STIFFNESSES,
        'fixed_parameters': recipe, 'clamp': {'role': 'functional_laboratory_fixture',
            'source_ref': 'metric coupon named bottom edge', 'vertices': source['panels']['sheet']['edges']['bottom'],
            'weights': source['pins'], 'temporary_supports': False},
        'minimum_observable_rms_cm': MIN_OBSERVABLE_RMS_CM, 'runs': {}, 'comparisons': {},
        'qualification': 'NONE', 'real_fitting': 'NOT_QUALIFIED', 'material_calibration': 'NOT_QUALIFIED'}
    atomic_json(OUT/'experiment.json', result)
    failures = []
    for mode in ('flat_2d', 'assembled_3d'):
        payload = copy.deepcopy(source)
        if mode == 'assembled_3d':
            payload, continuous_plan = split_for_consolidation(payload, plan)
            payload, consolidation = consolidate(payload, payload['placed_cm'], continuous_plan)
        else:
            consolidation = {'status': 'SOURCE_2D_REST_CONTROL'}
        for name, stiffness in STIFFNESSES.items():
            key = mode+'-'+name
            bpy.ops.wm.read_factory_settings(use_empty=True)
            bpy.context.preferences.filepaths.temporary_directory = str(OUT/'tmp')
            bpy.context.preferences.filepaths.save_version = 0
            run_recipe = copy.deepcopy(recipe)
            run_recipe['phases']['drape']['bending_stiffness'] = stiffness
            current = copy.deepcopy(payload)
            initial = copy.deepcopy(current['placed_cm'])
            obj = make_object(current, 'BENDING.'+key)
            run = {'status': 'NOT_EXECUTED', 'bending_stiffness': stiffness,
                   'recipe_sha256': digest(run_recipe), 'source_uv_sha256': digest(source['rest_cm']),
                   'topology_sha256': digest(current['faces']), 'initial_sha256': digest(initial),
                   'rest_mode': mode, 'rest_key': rest_key_name(current),
                   'rest_sha256': digest(current['rest_cm']), 'consolidation': consolidation}
            before = digest(current)
            try:
                final, report = simulate_object(obj, current, run_recipe, 'drape', [], [],
                    save_progress=lambda rows, key=key: atomic_json(OUT/(key+'-progress.json'), rows),
                    save_diagnostic=lambda diagnostic, key=key: atomic_json(OUT/(key+'-failure.json'), diagnostic))
                assert digest(current) == before
                settings = report['executed']['settings']
                assert settings['use_dynamic_mesh'] is False
                assert settings['shrink_min'] == settings['shrink_max'] == 0.
                assert settings['use_sewing_springs'] is False
                assert report['executed']['rest_shape_key'] == rest_key_name(current)
                assert report['validation_contract']['temporary_supports_active'] is False
                assert math.isclose(settings['bending_stiffness'], stiffness, rel_tol=1e-5)
                assert all(row['quality']['status'] == 'PASS' and row['contact']['ok'] for row in report['frames'])
                run.update(status='PASS_PHYSICS_COUPON_ONLY', report=report,
                           measurements=response(current, initial, final), final_cm=final)
                commit_positions(obj, final)
                master = OUT/(key+'-v001.blend')
                bpy.ops.wm.save_as_mainfile(filepath=str(master), check_existing=False)
                run['master'] = str(master)
            except Exception as error:
                run.update(status='REFUSED', error=str(error))
                failures.append(key)
            result['runs'][key] = run
            atomic_json(OUT/'result.json', result)
            print('BENDING_CASE '+key+' '+run['status'], flush=True)
        left, right = (result['runs'][mode+'-'+name] for name in STIFFNESSES)
        if all(run['status'] == 'PASS_PHYSICS_COUPON_ONLY' for run in (left, right)):
            assert left['source_uv_sha256'] == right['source_uv_sha256']
            assert left['topology_sha256'] == right['topology_sha256']
            assert left['initial_sha256'] == right['initial_sha256']
            assert left['rest_sha256'] == right['rest_sha256']
            assert left['report']['mass'] == right['report']['mass']
            settings = []
            for run in (left, right):
                values = copy.deepcopy(run['report']['executed']['settings'])
                values.pop('bending_stiffness')
                settings.append(values)
            assert settings[0] == settings[1], 'An unintended physical parameter changed inside the pair'
            distances = [math.dist(a, b) for a, b in zip(left['final_cm'], right['final_cm'])]
            rms = math.sqrt(sum(value*value for value in distances)/len(distances))
            tip = math.dist(left['measurements']['free_edge_centroid_final_cm'],
                            right['measurements']['free_edge_centroid_final_cm'])
            result['comparisons'][mode] = {'status': 'MEASURED_EFFECT' if rms >= MIN_OBSERVABLE_RMS_CM else 'INCONCLUSIVE_SMALL_EFFECT',
                'rms_shape_difference_cm': rms, 'maximum_shape_difference_cm': max(distances),
                'free_edge_difference_cm': tip, 'only_stiffness_varied': True,
                'mass_kg': left['report']['mass']['total_mass_kg'], 'qualification': 'NONE'}
        else:
            result['comparisons'][mode] = {'status': 'INCONCLUSIVE_REFUSED_RUN', 'qualification': 'NONE'}
    assert digest(source) == source_hash
    result['source_unchanged'] = True
    measured = len(result['comparisons']) == 2 and all(value['status'] == 'MEASURED_EFFECT' for value in result['comparisons'].values())
    result['status'] = 'PASS_BENDING_EFFECT_COUPONS_ONLY' if not failures and measured else 'REFUSED_OR_INCONCLUSIVE'
    result['refused_runs'] = failures
    atomic_json(OUT/'result.json', result)
    print('BENDING_RESULT '+result['status'], flush=True)
    if result['status'] != 'PASS_BENDING_EFFECT_COUPONS_ONLY':
        raise RuntimeError('Bending comparison remains refused or inconclusive; inspect preserved evidence')


if __name__ == '__main__':
    try:
        main()
    except Exception as error:
        path = OUT/'result.json'
        preserved = read_json(path) if path.exists() else {'runs': {}}
        if preserved.get('status') != 'REFUSED_OR_INCONCLUSIVE':
            preserved['status'] = 'EXPERIMENT_CHECK_REFUSED'
        preserved['experiment_error'] = str(error)
        atomic_json(path, preserved)
        raise
