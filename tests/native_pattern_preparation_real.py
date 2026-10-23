"""Isolated real source preparation, native reports/renders, and no Cloth.

Invoke through scripts/run_pattern_validation.py with a fresh G: output. The
source witness is copied and fully hashed; no connected scene is accessed.
"""
import copy
import json
import math
import os
from pathlib import Path
import shutil
import sys
import traceback

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))

import bpy
from mathutils import Euler, Vector

from a3d.core import atomic_json, digest, read_json, sha
from a3d.pattern_assembly import map_digest
from a3d.pattern_preparation import preparation_statistics, prepare_regular_boundaries
from a3d.sewing import signed_area
from a3d.store import Project
from blender.operations import dispatch
from blender.sewing import mesh_digest, object_mesh, placed_point
from tests.native_pattern_real import (
    SOURCE, ENVELOPE_REPORT, COMPONENT, LEGACY_OPTIONS,
    inventory, simulation_object, source_supports, measured_contact,
)


def metric_preform(payload, recipe, data):
    """Source-metric placement, never the previously deformed full coordinates.

    Flat panels use exact rigid source-UV frames. Cylinders use an independent
    UV rectangle cage covering the approved source contour. Its arc samples
    are at most 0.5 cm apart; targets use the original metric placement formula.
    No old triangulation or previously simulated coordinates define this cage.
    """
    panels = {}
    for pid in payload['panels']:
        placement = recipe['placements'][pid]
        source_ref = 'original metric source placement in retained recipe; no simulated full coordinates reused: ' + pid
        if placement['mode'] == 'flat':
            matrix = Euler([math.radians(value) for value in placement['rotation_degrees']], 'XYZ').to_matrix()
            panels[pid] = {'source_ref': source_ref,
                           'origin_cm': list(placement['position_cm']),
                           'u_axis': list(matrix @ Vector((1, 0, 0))),
                           'v_axis': list(matrix @ Vector((0, 1, 0)))}
            continue
        source_uv = data['pieces'][pid]['vertices']
        u_min, u_max = min(point[0] for point in source_uv), max(point[0] for point in source_uv)
        v_min, v_max = min(point[1] for point in source_uv), max(point[1] for point in source_uv)
        columns = max(1, math.ceil((u_max - u_min) / .5))
        uv = [[u_min + (u_max - u_min) * column / columns, v]
              for v in (v_min, v_max) for column in range(columns + 1)]
        triangles = []
        for column in range(columns):
            a, b = column, column + 1
            c, d = column + columns + 1, column + columns + 2
            triangles.extend(([a, b, d], [a, d, c]))
        panels[pid] = {'source_ref': source_ref + '; independent source UV rectangle with <=0.5 cm arc samples', 'uv_cm': uv,
                       'target_cm': [placed_point(point, placement) for point in uv],
                       'triangles': triangles}
    return {'version': 1, 'component_id': COMPONENT,
            'source_refs': ['immutable approved real package; source metric placements reconstructed before any Cloth',
                            'rigid torso frames and metric sleeve/collar cylinders; placement is not accepted fitting'],
            'mapping_sha256': map_digest(payload), 'preform': {'panels': panels},
            'assembly': {'max_initial_gap_cm': 20.,
                         'max_displacement_cm': recipe['limits']['max_displacement_cm'],
                         'max_step_cm': .03, 'iterations': 600,
                         'neighborhood_rings': 2, 'closure_support_release': 1.},
            'consolidation': {'weld_gap_cm': recipe['limits']['weld_gap_cm']},
            'quality': {key: recipe['mesh'][key] for key in
                        ('min_angle_degrees', 'min_edge_cm', 'min_stretch', 'max_stretch')},
            'supports': source_supports(payload, recipe),
            'collision': {'required': True, 'mode': 'all_stages', 'clearance_cm': .02,
                          'source_ref': 'unchanged source-bound R21 geometric envelope, audited before any physics'},
            'cloth': {'mount_phase': 'mount', 'relax_phase': 'drape', 'drape_phase': 'drape',
                      'mount_release_steps': [0., .5, 1.]}}


def file_ref(project_root, path):
    return {'path': path.relative_to(project_root).as_posix(), 'sha256': sha(path)}


def verify_ref(project_root, reference):
    path = (project_root / reference['path']).resolve(strict=True)
    if not path.is_relative_to(project_root) or sha(path) != reference['sha256']:
        raise AssertionError('Native preparation returned a stale/outside artifact')
    return path


def run(output, report):
    project_root = output / 'project'
    shutil.copytree(SOURCE, project_root)
    project = Project(project_root)
    session = read_json(project.data / 'blender/session.json')
    source_working = Path(session['working']).resolve()
    if not source_working.is_relative_to(SOURCE.resolve()):
        raise RuntimeError('Retained working scene is outside the approved static witness')
    working = project_root / source_working.relative_to(SOURCE)
    original = output / 'fixture-original.blend'
    shutil.copyfile(working, original)
    session.update(original=str(original), original_sha256=sha(original), working=str(working))
    atomic_json(project.data / 'blender/session.json', session)
    bpy.ops.wm.open_mainfile(filepath=str(working), load_ui=False, use_scripts=False)
    bpy.context.preferences.filepaths.temporary_directory = str(output / 'tmp')
    bpy.context.preferences.filepaths.save_version = 0

    old_object = simulation_object()
    old_geometry = mesh_digest(old_object)
    old_mapping_path = old_object['a3d_sewing_mesh']
    old_payload = read_json(project_root / old_mapping_path)
    old_coords = [[coordinate * 100 for coordinate in point] for point in object_mesh(old_object)[0]]
    full = read_json(project_root / old_object['a3d_sewn_stage_result'])
    recipe = copy.deepcopy(read_json(project_root / full['recipe_path']))
    data = read_json(project_root / old_payload['source_garment'])
    source_data_hash = digest(data)
    old_statistics = preparation_statistics(old_payload, old_coords, recipe['mass'])
    report['historical_candidate'] = {'object': old_object.name, 'mesh_sha256': old_geometry,
                                      'mapping': old_mapping_path, 'statistics': old_statistics,
                                      'historical_purpose': full.get('purpose'),
                                      'historical_simulation': full.get('simulation'),
                                      'historical_pass_transferred': False}
    report['source_patterns'] = {'component_id': COMPONENT,
                                 'package_sha256': old_payload['package_sha256'],
                                 'source_garment_sha256': source_data_hash,
                                 'piece_ids': sorted(data['pieces']),
                                 'seam_ids': sorted(seam['id'] for seam in data['seams'])}
    removed = {key: recipe.pop(key) for key in LEGACY_OPTIONS if key in recipe}
    report['retired_preparation_inputs'] = sorted(removed)

    # Import only the pre-existing exact auxiliary through the supported native
    # body-context operation. The source geometry stays the successful witness.
    proxy = read_json(ENVELOPE_REPORT)
    verify_ref(project_root, proxy['artifact'])
    fitting_plan = read_json(project_root / 'body-only-fit.json')
    fitting_plan['envelope'] = {'object': proxy['object'], 'role': 'proxy',
                               'geometry_sha256': proxy['geometry_sha256']}
    atomic_json(project_root / 'preparation-fit.json', fitting_plan)
    recipe['fitting_plan'] = file_ref(project_root, project_root / 'preparation-fit.json')
    recipe['colliders'] = [{**{key: proxy['collider'][key] for key in
                              ('object', 'geometry_sha256', 'dimensions_cm',
                               'outer_thickness_cm', 'inner_thickness_cm')},
                            'role': 'mannequin', 'tolerance_cm': .01}]
    recipe['no_collision_reason'] = ''
    context_recipe_path = project_root / 'preparation-context-recipe.json'
    atomic_json(context_recipe_path, recipe)
    report['native_body_context'] = dispatch(str(project_root), 'introduce_fitting_context', {
        'component_id': COMPONENT, 'recipe_path': context_recipe_path.name,
        'fit_path': 'preparation-fit.json', 'source_blend': proxy['artifact']['path'],
        'source_sha256': proxy['artifact']['sha256']})
    assert mesh_digest(old_object) == old_geometry
    report['historical_candidate']['contact'] = measured_contact(old_object, recipe)

    # The new regular/adaptive derivation replaces the old corrective refinement
    # algorithm, while all minimum-quality, strain and final physical gates stay.
    old_refinement = recipe['mesh'].pop('quality_refinement', None)
    report['replaced_refinement_algorithm'] = old_refinement
    report['unchanged_limits'] = copy.deepcopy(recipe['limits'])
    report['unchanged_quality_gates'] = {key: recipe['mesh'][key] for key in
                                       ('min_angle_degrees', 'min_edge_cm', 'min_stretch', 'max_stretch')}
    plan = metric_preform(old_payload, recipe, data)
    plan_path = project_root / 'preparation-source-plan.json'
    atomic_json(plan_path, plan)
    recipe_path = project_root / 'preparation-recipe.json'
    atomic_json(recipe_path, recipe)
    regular_mesh = {'spacing_cm': 2., 'min_spacing_cm': 1.,
                    'refinement_distance_cm': 4., 'max_vertices': 30000,
                    'target_min_angle_degrees': 15.}
    dossier = project_root / 'construction-v3/dossier-construction.json'
    dossier_data = read_json(dossier)
    boundaries, _, _ = prepare_regular_boundaries(data, recipe, regular_mesh, dossier_data)
    area_cm2 = sum(abs(signed_area(boundary['polygon'])) for boundary in boundaries.values())
    if recipe['mass']['basis'] == 'total_kg':
        density = recipe['mass']['value'] / (area_cm2 / 10000)
    else:
        density = recipe['mass']['value']
    reinforced = sorted(info['id'] for info in dossier_data['components'][COMPONENT]['pieces']
                        if 'renforc' in info['material'].lower())
    ordinary = sorted(set(data['pieces']) - set(reinforced))
    material_profiles = [
        {'id': 'retained-main-cloth-hypothesis', 'category': 'main', 'cloth_profile': 'phase_base',
         'source_ref': 'source dossier inferred main cloth; unchanged scalar recipe stiffness and total mass; not a measured textile material',
         'pieces': ordinary, 'areal_density_kg_m2': density},
        {'id': 'retained-reinforcement-hypothesis', 'category': 'reinforcement', 'cloth_profile': 'phase_base',
         'source_ref': 'source dossier inferred coated reinforced cuffs; unchanged common phase base is a provisional hypothesis, no differentiated stiffness or local density qualification',
         'pieces': reinforced, 'areal_density_kg_m2': density}]
    spec = {'version': 1, 'component_id': COMPONENT,
            'source_ref': 'isolated real preparation from immutable source metric placements; no source edit or simulated full cage reuse',
            'regular_mesh': regular_mesh, 'assembly_plan': file_ref(project_root, plan_path),
            'construction_dossier': file_ref(project_root, dossier),
            'migration': {'retire_legacy_preparations': True},
            'mass_policy': 'native_uniform_vertex',
            'material_profiles': material_profiles}
    # The native preparer owns migration. Preserve the old options verbatim in
    # its input and require an archived source recipe plus a new clean recipe.
    recipe.update(removed)
    atomic_json(recipe_path, recipe)
    spec_path = project_root / 'pattern-preparation.json'
    atomic_json(spec_path, spec)
    report['preparation_inputs'] = {'recipe': file_ref(project_root, recipe_path),
                                     'spec': file_ref(project_root, spec_path),
                                     'plan': file_ref(project_root, plan_path),
                                     'derived_profile_density_kg_m2': density,
                                     'density_basis_area_cm2': area_cm2,
                                     'previous_deformed_positions_reused': False}
    before = {'patterns': digest(data), 'recipe': sha(recipe_path), 'spec': sha(spec_path),
              'plan': sha(plan_path), 'old_map': sha(project_root / old_mapping_path),
              'old_mesh': old_geometry}

    # A regression that unexpectedly reaches either solver path must fail this
    # preparation test. The plugin, not this script, produces the technical views.
    import blender.sewing as sewing_module
    import blender.pattern_assembly as assembly_module
    calls = []

    def forbidden_cloth(*args, **kwargs):
        calls.append('Cloth')
        raise AssertionError('Preparation must not execute Cloth or sewing simulation')

    solver, assembly_solver = sewing_module.simulate_object, assembly_module.simulate_object
    sewing_module.simulate_object = assembly_module.simulate_object = forbidden_cloth
    try:
        result = dispatch(str(project_root), 'prepare_pattern_assembly', {
            'component_id': COMPONENT, 'recipe_path': recipe_path.name,
            'preparation_path': spec_path.name})
    finally:
        sewing_module.simulate_object, assembly_module.simulate_object = solver, assembly_solver
    report['native_preparation'] = result
    report['readiness'] = result['readiness']
    assert result['readiness'] in ('READY', 'NEEDS_CORRECTION', 'NEEDS_CLARIFICATION')
    assert result['simulation'] == 'NOT_EXECUTED' and not calls
    assert result['accepted'] is False and result['export_eligible'] is False
    assert result['fitting'] == result['behavior'] == 'NOT_QUALIFIED'
    assert result['recipe_migration']['physics_validation_transferred'] is False
    assert result['recipe_migration']['retired_fields'] == removed
    assert sha(recipe_path) == before['recipe'] and sha(spec_path) == before['spec']
    assert sha(plan_path) == before['plan'] and sha(project_root / old_mapping_path) == before['old_map']
    assert digest(read_json(project_root / old_payload['source_garment'])) == before['patterns']
    assert mesh_digest(old_object) == before['old_mesh']
    for key in ('receipt', 'master', 'recipe'):
        verify_ref(project_root, result[key])
    report['new_candidate'] = {'statistics': result['statistics'], 'collision': result['collision'],
                               'source_audit': result['source_audit'],
                               'source_patterns_unchanged': True, 'old_geometry_unchanged': True,
                               'cloth_calls': len(calls), 'technical_views': result.get('technical_views')}
    if result.get('derived_mesh'):
        candidate = read_json(verify_ref(project_root, result['derived_mesh']))
        assert candidate['source_garment_sha256'] == source_data_hash
        assert candidate['package_sha256'] == old_payload['package_sha256']
        assert sorted(candidate['panels']) == sorted(old_payload['panels'])
        assert sorted(candidate['seams']) == sorted(old_payload['seams'])
        assert all(candidate['seams'][sid]['kind'] == old_payload['seams'][sid]['kind']
                   for sid in candidate['seams'])
        candidate_obj = bpy.data.objects[result['object']]
        assert not any(modifier.type == 'CLOTH' for modifier in candidate_obj.modifiers)
        report['new_candidate']['contact'] = measured_contact(candidate_obj, recipe)
        report['new_candidate']['new_map_sha256'] = map_digest(candidate)
        report['new_candidate']['source_mapping_sha256'] = map_digest(old_payload)
    else:
        report['new_candidate']['contact'] = {'status': 'NOT_EXECUTED_NO_SAFE_DERIVED_MESH'}
    report['status'] = 'NATIVE_PREPARATION_EXECUTED'
    report['visual_validation'] = 'PIXELS_REQUIRE_AGENT_REVIEW'


def main():
    output = Path(os.environ['A3D_VALIDATION_OUTPUT']).resolve(strict=True)
    if output.drive.upper() != 'G:' or output == SOURCE or output.is_relative_to(SOURCE):
        raise RuntimeError('A distinct G: validation output is required')
    if not (output / 'tmp').is_dir():
        raise RuntimeError('Use scripts/run_pattern_validation.py with its G: profile and temporary directory')
    source_before = inventory(SOURCE)
    envelope_before = sha(ENVELOPE_REPORT)
    report = {'experiment': 'real source-metric preparation without Cloth', 'status': 'RUNNING',
              'blender': bpy.app.version_string, 'fitting': 'NOT_QUALIFIED',
              'behavior': 'NOT_QUALIFIED', 'simulation': 'NOT_EXECUTED',
              'visual_validation': 'NOT_EXECUTED', 'accepted': False,
              'export_eligible': False, 'consumer_live_blender': 'UNTOUCHED'}
    error = None
    try:
        run(output, report)
    except Exception as exception:
        error = exception
        report.update(status='HARNESS_OR_INTEGRATION_ERROR', error=str(exception), traceback=traceback.format_exc())
    finally:
        unchanged = source_before == inventory(SOURCE) and sha(ENVELOPE_REPORT) == envelope_before
        report['source_files_unchanged'] = unchanged
        report['source_file_count'] = len(source_before)
        atomic_json(output / 'source-manifest.json', {'root': str(SOURCE), 'sha256_by_path': source_before,
                                                     'unchanged': unchanged, 'envelope_report_sha256': envelope_before})
        atomic_json(output / 'report.json', report)
        print(json.dumps({'output': str(output), 'status': report['status'],
                          'readiness': report.get('readiness'), 'source_files_unchanged': unchanged,
                          'simulation': 'NOT_EXECUTED'}, indent=2), flush=True)
        if not unchanged:
            raise RuntimeError('Source witness changed during isolated preparation')
    if error is not None:
        raise error


if __name__ == '__main__':
    main()
