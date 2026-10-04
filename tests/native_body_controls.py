"""TEST_ONLY torso-girth variants on both native measured catalog bodies.

These relative test targets never change a reviewed production body selection.
Source target artifacts are read only, copies are saved to a new output folder.
"""
import argparse
import copy
import json
import math
from pathlib import Path
import sys

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))


def arguments(argv):
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--output', required=True)
    parser.add_argument('--body-target-receipt', required=True)
    parser.add_argument('--validate-only', action='store_true')
    args = parser.parse_args(argv)
    output, receipt = Path(args.output), Path(args.body_target_receipt)
    if not output.is_absolute() or output.exists() or not receipt.is_absolute() or not receipt.is_file():
        parser.error('Use an absolute new output directory and an absolute existing body target receipt')
    args.output, args.body_target_receipt = output.resolve(), receipt.resolve()
    if args.output.is_relative_to(ROOT/'assets'):
        parser.error('Native controls evidence cannot be stored among immutable assets')
    return args


def section_ratios(geometry, options, source_profile):
    from a3d.anatomy_profile import surface_section
    from a3d.contact_geometry import dot, sub
    basis = source_profile['frame']
    local = [[dot(sub(point, basis['origin_cm']), basis[key]) for key in ('right', 'forward', 'up')]
             for point in geometry['vertices_cm']]
    faces = [geometry['faces'][index] for index in options['torso_faces']]
    result = {}
    for name in ('hip', 'waist', 'chest'):
        landmark = source_profile['landmarks'][name]
        section = surface_section(local, faces, landmark['section_height_cm'], landmark['point_cm'][:2])
        assert section['status'] == 'MEASURED', (name, section)
        low, high = section['bounds_xy_cm']
        width, depth = high[0]-low[0], high[1]-low[1]
        assert width > 0. and depth > 0.
        result[name] = {'width_cm': width, 'depth_cm': depth, 'width_depth_ratio': width/depth,
                        'section_height_cm': landmark['section_height_cm']}
    return result


def run(output, previous_path):
    import bpy
    from a3d.anatomy_profile import profile_mesh
    from a3d.body_controls import cage_from_segmentation, solve_girths
    from a3d.body_target import STATURE_TARGET_BUDGETS
    from a3d.core import atomic_json, digest, read_json, sha
    from tests.native_body_motion import copy_target_inputs
    from blender.body_source import data_ids, live_geometry
    from blender.body_target import evaluated_mesh
    assert bpy.app.background and not bpy.data.filepath
    previous = read_json(previous_path); assert previous['status'] == 'NATIVE_BODY_TARGET_PASS'
    output.mkdir(parents=True, exist_ok=False)
    project, source_project, input_manifest = copy_target_inputs(previous_path, output)
    source_db = sha(project.db)
    source_state = digest(project.state()); baseline_ids = data_ids(); live_before = live_geometry()
    scene = bpy.context.scene; scene.unit_settings.system = 'METRIC'; scene.unit_settings.scale_length = 1.
    criteria = {'version': 1, 'purpose': 'TEST_ONLY', 'girth_target_factors': {'hip': 1.03, 'waist': .97, 'chest': 1.03},
                'girth_residual_tolerance_cm': .1, 'native_roundtrip_error_cm': .0001,
                'relative_section_width_depth_ratio_tolerance': .01,
                'source_production_targets_changed': False, 'fitting': 'NOT_EXECUTED'}
    atomic_json(output/'criteria.json', criteria); reports = []
    for entry in previous['reports']:
        original = entry['result']; artifact_refs = original['artifacts']
        for reference in (original['artifact'], artifact_refs['geometry'], artifact_refs['options']):
            assert sha(project.root/reference['path']) == reference['sha256']
        geometry = read_json(project.root/artifact_refs['geometry']['path'])
        options = read_json(project.root/artifact_refs['options']['path'])
        source_profile = profile_mesh(geometry, options)
        cage = cage_from_segmentation(geometry, options)
        before = digest([geometry, options, cage]); source_ratios = section_ratios(geometry, options, source_profile)
        targets = {name: source_profile['landmarks'][name]['girth_cm']*factor
                   for name, factor in criteria['girth_target_factors'].items()}
        budgets = copy.deepcopy(STATURE_TARGET_BUDGETS)
        result = solve_girths(geometry, options, cage, targets, criteria['girth_residual_tolerance_cm'], budgets)
        assert result['receipt']['status'] == 'TARGETS_MEASURED', result['receipt']
        assert all(abs(value) <= .1 for value in result['receipt']['residuals_cm'].values())
        assert digest([geometry, options, cage]) == before
        assert all(result['geometry']['vertices_cm'][i] == geometry['vertices_cm'][i] for i in cage['protected_vertex_ids'])
        assert result['geometry']['faces'] == geometry['faces'] and result['geometry']['face_sets'] == geometry['face_sets']
        assert abs(result['profile']['stature_cm']-source_profile['stature_cm']) <= 1e-9
        assert abs(result['profile']['floor_cm']-source_profile['floor_cm']) <= 1e-9
        # The fixed source cut planes are measured again, including protected
        # cut-edge endpoints; solver compensation must preserve their ratios.
        changed_ratios = section_ratios(result['geometry'], options, source_profile)
        ratio_errors = {name: abs(changed_ratios[name]['width_depth_ratio']/source_ratios[name]['width_depth_ratio']-1.)
                        for name in targets}
        assert all(error <= criteria['relative_section_width_depth_ratio_tolerance'] for error in ratio_errors.values()), ratio_errors
        assert result['receipt']['width_depth_preserved']
        assert all(error <= result['receipt']['width_depth_relative_tolerance'] for error in ratio_errors.values())
        limited_budgets = dict(budgets, max_evaluations=1)
        limited = solve_girths(geometry, options, cage, {'chest': 300.}, .1, limited_budgets)
        assert limited['receipt']['status'] == 'BUDGET_EXHAUSTED' and limited['receipt']['evaluations'] == 1
        assert limited['geometry']['vertices_cm'] == geometry['vertices_cm']
        impossible = solve_girths(geometry, options, cage, {'chest': 300.}, .1, budgets)
        assert impossible['receipt']['status'] in ('STAGNATED', 'BUDGET_EXHAUSTED')
        assert abs(impossible['receipt']['residuals_cm']['chest']) > .1
        directory = output/entry['catalog_id']; directory.mkdir()
        mesh = bpy.data.meshes.new('TEST_ONLY.TorsoControls.'+entry['catalog_id'])
        mesh.from_pydata([[value/100 for value in point] for point in result['geometry']['vertices_cm']], [], geometry['faces']); mesh.update()
        regions = mesh.attributes.new('.sculpt_face_set', 'INT', 'FACE')
        for label, value in zip(regions.data, geometry['face_sets']): label.value = value
        body = bpy.data.objects.new('TEST_ONLY.TorsoControls.'+entry['catalog_id'], mesh); scene.collection.objects.link(body)
        bpy.context.view_layer.update(); dg = bpy.context.evaluated_depsgraph_get(); dg.update()
        actual, triangles = evaluated_mesh(body, dg, 1.)
        error = max(math.dist(a, b) for a, b in zip(actual['vertices_cm'], result['geometry']['vertices_cm']))
        assert error <= .0001 and actual['faces'] == geometry['faces'] and actual['face_sets'] == geometry['face_sets']
        native = dict(actual, source_sha256=geometry['source_sha256'],
                      pose_sha256=digest({'source_control_pose': result['geometry']['pose_sha256'], 'actual_geometry': actual}),
                      rig_landmarks=copy.deepcopy(result['geometry']['rig_landmarks']))
        profile = profile_mesh(native, options)
        residuals = {name: profile['landmarks'][name]['girth_cm']-value for name, value in targets.items()}
        assert all(abs(value) <= .1 for value in residuals.values()), residuals
        assert all(math.dist(actual['vertices_cm'][i], geometry['vertices_cm'][i]) <= .0001 for i in cage['protected_vertex_ids'])
        path = directory/'TEST_ONLY.body.blend'; name = body.name
        bpy.data.libraries.write(str(path), {body}, fake_user=True); bpy.data.objects.remove(body, do_unlink=True)
        with bpy.data.libraries.load(str(path), link=False) as (_, loaded): loaded.objects = [name]
        reopened = loaded.objects[0]; scene.collection.objects.link(reopened); bpy.context.view_layer.update(); dg.update()
        reopened_geometry, reopened_triangles = evaluated_mesh(reopened, dg, 1.)
        assert reopened_geometry == actual and reopened_triangles == triangles
        atomic_json(directory/'geometry.json', native); atomic_json(directory/'profile.json', profile)
        atomic_json(directory/'solver.json', result['receipt']); atomic_json(directory/'cage.json', cage)
        atomic_json(directory/'impossible.json', impossible['receipt']); atomic_json(directory/'budget-exhausted.json', limited['receipt'])
        reports.append({'catalog_id': entry['catalog_id'], 'purpose': 'TEST_ONLY', 'status': 'NATIVE_TORSO_CONTROLS_PASS',
                        'targets_cm': targets, 'measured_girths_cm': {name: profile['landmarks'][name]['girth_cm'] for name in targets},
                        'residuals_cm': residuals, 'native_roundtrip_error_cm': error,
                        'relative_section_width_depth_ratio_errors': ratio_errors,
                        'protected_vertices': len(cage['protected_vertex_ids']), 'protected_vertices_preserved': True,
                        'source_floor_cm': source_profile['floor_cm'], 'native_floor_cm': profile['floor_cm'],
                        'source_stature_cm': source_profile['stature_cm'], 'native_stature_cm': profile['stature_cm'],
                        'artifact': {'path': str(path), 'sha256': sha(path)}, 'native_reopened_exact': True,
                        'impossible_status': impossible['receipt']['status'], 'budget_status': limited['receipt']['status'],
                        'production_body_changed': False, 'rig_qualification': 'NOT_EXECUTED', 'fitting': 'NOT_EXECUTED'})
        bpy.data.batch_remove(ids=data_ids()-baseline_ids)
        assert data_ids() == baseline_ids and live_geometry() == live_before
        assert sha(project.db) == source_db and digest(project.state()) == source_state
        assert sha(project.root/original['artifact']['path']) == original['artifact']['sha256']
    receipt = {'version': 1, 'status': 'NATIVE_BODY_CONTROLS_PASS', 'purpose': 'TEST_ONLY',
               'qualification': 'TORSO_GIRTH_CONTROLS_GEOMETRY_ONLY', 'reports': reports,
               'criteria': {'path': str(output/'criteria.json'), 'sha256': sha(output/'criteria.json')},
               'source_receipt': {'path': str(previous_path), 'sha256': sha(previous_path)},
               'input_copy_manifest': {'path': str(output/'input-copy-manifest.json'), 'sha256': sha(output/'input-copy-manifest.json')},
               'source_project_and_body_artifacts_unchanged': True, 'production_connection': False,
               'fitting': 'NOT_EXECUTED', 'blender_version': bpy.app.version_string}
    atomic_json(output/'receipt.json', receipt)
    assert sha(source_project.db) == input_manifest['source_database_sha256']
    print(json.dumps({'status': receipt['status'], 'receipt': str(output/'receipt.json'), 'purpose': 'TEST_ONLY'}))


if __name__ == '__main__':
    argv = sys.argv[sys.argv.index('--')+1:] if '--' in sys.argv else sys.argv[1:]
    args = arguments(argv)
    if args.validate_only:
        print(json.dumps({'arguments_valid': True, 'native_executed': False, 'output': str(args.output)}))
    else:
        run(args.output, args.body_target_receipt)
