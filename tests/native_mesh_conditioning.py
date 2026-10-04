"""Native, synthetic conditioning observation. No real project or product gates."""
import argparse
import copy
import math
import os
from pathlib import Path
import sys
import time

sys.dont_write_bytecode = True
ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))
import bpy
from a3d.core import StudioError, atomic_json, digest, sha
from a3d.cloth_metrics import triangle_metrics
from a3d.sewing import signed_area
from blender.sewing import triangulate

parser = argparse.ArgumentParser(description='Isolated TEST_ONLY native mesh conditioning observation')
parser.add_argument('--output', type=Path, default=os.environ.get('A3D_VALIDATION_OUTPUT'))
arguments = sys.argv[sys.argv.index('--') + 1:] if '--' in sys.argv else []
args = parser.parse_args(arguments)
if args.output is None: parser.error('--output or A3D_VALIDATION_OUTPUT is required')
OUT = Path(args.output).resolve()
if OUT == ROOT or OUT in ROOT.parents or ROOT in OUT.parents or 'program-production-main-v1' in OUT.parts:
    raise StudioError('Native conditioning output must be isolated from source and production MAIN')
if not bpy.app.background or bpy.data.filepath:
    raise StudioError('Native conditioning requires background factory startup with no loaded blend')
if OUT.exists() and not OUT.is_dir(): raise StudioError('Native test requires an output directory')
if any((OUT / name).exists() for name in ('receipt.json', 'conditioning.blend',
        'regular-square.json', 'short-fixed-source-intervals.json', 'immutable-acute-source-corner.json')):
    raise StudioError('Native conditioning observation requires fresh output files')
OUT.mkdir(parents=True, exist_ok=True)
if not (OUT / 'tmp').exists(): (OUT / 'tmp').mkdir()
bpy.ops.wm.read_factory_settings(use_empty=True)
bpy.context.preferences.filepaths.temporary_directory = str(OUT / 'tmp')
bpy.context.preferences.filepaths.save_version = 0
started = time.monotonic()
maximum_seconds = 120.


def check_budget():
    if time.monotonic() - started > maximum_seconds:
        raise StudioError('Native conditioning fixture exceeded its declared boundary time budget')


def measured(points, faces):
    rows = [triangle_metrics([points[i] for i in face]) for face in faces]
    return {'min_angle_degrees': min(row['min_angle_degrees'] for row in rows),
            'min_edge_cm': min(min(row['edges_cm']) for row in rows),
            'area_cm2': sum(row['area_cm2'] for row in rows)}


recipe = {'mesh': {'spacing_cm': 1., 'max_vertices': 4000, 'min_angle_degrees': 2.,
                  'min_edge_cm': .001,
                  'quality_refinement': {'target_min_angle_degrees': 15.,
                                         'max_passes': 8, 'max_added_vertices': 4000}}}
regular = {'spacing_cm': 2., 'min_spacing_cm': 1., 'refinement_distance_cm': 4.,
           'max_vertices': 4000, 'target_min_angle_degrees': 15.}
bottom = sorted(set([float(i) for i in range(18)] + [8.08353554762748, 12.08353554762748]))
strip = [[x, 0.] for x in bottom]
strip.extend([[17., float(i)] for i in range(1, 8)])
strip.extend([[float(i), 7.] for i in range(16, -1, -1)])
strip.extend([[0., float(i)] for i in range(6, 0, -1)])
# This wrapper consumes an already sampled boundary. A four-corner square
# leaves four-centimetre boundary edges next to the one-centimetre interior
# lattice, unlike the supported regular preparation path. Declare its exact
# one-centimetre contour stops here; the four corners and area are unchanged.
square = [[float(i), 0.] for i in range(4)]
square.extend([[4., float(i)] for i in range(4)])
square.extend([[float(i), 4.] for i in range(4, 0, -1)])
square.extend([[0., float(i)] for i in range(4, 0, -1)])
fixtures = [
    ('regular-square', square, 'TARGET_REACHED'),
    ('short-fixed-source-intervals', strip, None),
    ('immutable-acute-source-corner', [[0., 0.], [4., 0.], [4., .05]], 'NEEDS_CORRECTION')]
cases = []
native_before = {}
for name, polygon, expected in fixtures:
    check_budget()
    boundary = {'polygon': copy.deepcopy(polygon), 'source': copy.deepcopy(polygon), 'flip': False}
    original = digest([boundary['polygon'], boundary['source'], recipe, regular])
    case_path = OUT / (name + '.json')
    case = {'id': name, 'purpose': 'TEST_ONLY', 'status': 'STARTED', 'expected': expected,
            'source_polygon_cm': polygon, 'source_sha256': original,
            'source_boundary_stops': len(polygon), 'qualification': 'NONE',
            'loaded_code': {str(path.relative_to(ROOT)): sha(path) for path in (
                ROOT / 'blender/sewing.py', ROOT / 'a3d/mesh_refinement.py',
                ROOT / 'a3d/pattern_preparation.py', ROOT / 'tests/native_mesh_conditioning.py')}}
    atomic_json(case_path, case)
    try:
        coordinates, faces, mapping = triangulate(boundary, recipe, regular)
    except Exception as error:
        case.update(status='REFUSED', stage='NATIVE_TRIANGULATION', error_type=type(error).__name__,
                    message=str(error), conditioning=boundary.get('preparation_refinement'),
                    refinement_metrics=getattr(error, 'refinement_metrics', None))
        atomic_json(case_path, case)
        raise
    report = boundary['preparation_refinement']
    case.update(status=report['status'], stage='TRIANGULATION_RETURNED', conditioning=report,
                coordinates_cm=coordinates, face_indices=faces, source_anchor_mapping=mapping)
    atomic_json(case_path, case)
    material = measured(coordinates, faces)
    checks = {
        'source_anchors_preserved': [coordinates[mapping[i]] for i in range(len(polygon))] == polygon,
        'source_inputs_preserved': digest([boundary['polygon'], boundary['source'], recipe, regular]) == original,
        'source_area_preserved': abs(material['area_cm2'] - abs(signed_area(polygon))) < 1e-8,
        'positive_winding': all(signed_area([coordinates[i] for i in face]) > 0 for face in faces),
        'candidate_count_within_budget': len(report['conditioning_history']) <= recipe['mesh']['quality_refinement']['max_passes'] + 1,
        'conditioning_bounds_observed': all(candidate['exact_source_anchors_restored']
            and candidate['interior_smoothing']['boundary_anchors_changed'] is False
            and candidate['interior_smoothing']['maximum_displacement_cm'] <= .5 + 1e-12
            for candidate in report['conditioning_history']),
        'reported_material_target_verified': report['status'] != 'TARGET_REACHED'
            or (material['min_angle_degrees'] >= 15. and material['min_edge_cm'] >= .001),
        'expected_status_matches': expected is None or report['status'] == expected}
    case.update(status=report['status'], stage='MATERIAL_MEASURED',
                source_hash_preserved=checks['source_inputs_preserved'], vertices=len(coordinates),
                faces=len(faces), material_metrics=material, conditioning=report,
                coordinates_cm=coordinates, face_indices=faces, source_anchor_mapping=mapping, checks=checks)
    # Keep the real native result, including all coordinates and a failed
    # expectation, before any assertion can stop this diagnostic.
    atomic_json(case_path, case)
    mesh = bpy.data.meshes.new('TEST_ONLY_' + name)
    mesh.from_pydata([[p[0] / 100, p[1] / 100, 0.] for p in coordinates], [], faces)
    mesh.update()
    obj = bpy.data.objects.new('TEST_ONLY_' + name, mesh)
    bpy.context.collection.objects.link(obj)
    native_before[obj.name] = {'vertices_m': [list(v.co) for v in mesh.vertices],
                               'faces': [list(p.vertices) for p in mesh.polygons]}
    native_cm = [[value * 100 for value in v.co] for v in mesh.vertices]
    native_quality = measured(native_cm, faces)
    checks['reported_native_target_verified'] = report['status'] != 'TARGET_REACHED' or (
        native_quality['min_angle_degrees'] >= 15. and native_quality['min_edge_cm'] >= .001)
    case.update(stage='NATIVE_GEOMETRY_MEASURED', native_geometry_metrics=native_quality,
                maximum_native_roundtrip_error_cm=max(math.dist(
                    [a[0], a[1], 0.], b) for a, b in zip(coordinates, native_cm)),
                validation_status='PASS' if all(checks.values()) else 'FAIL')
    cases.append(case)
    atomic_json(case_path, case)
    assert all(checks.values()), (name, checks, report)
check_budget()
scene_path = OUT / 'conditioning.blend'
bpy.ops.wm.save_as_mainfile(filepath=str(scene_path))
bpy.ops.wm.open_mainfile(filepath=str(scene_path))
for name, original in native_before.items():
    obj = bpy.data.objects[name]
    assert [list(v.co) for v in obj.data.vertices] == original['vertices_m']
    assert [list(p.vertices) for p in obj.data.polygons] == original['faces']
check_budget()
atomic_json(OUT / 'receipt.json', {
    'version': 1, 'purpose': 'TEST_ONLY', 'status': 'TEST_ONLY_NATIVE_CONDITIONING_OBSERVED',
    'scope': 'SYNTHETIC_CDT_CONDITIONING_FIXED_SOURCE_ANCHORS_AND_REOPEN',
    'cases': cases, 'scene': {'path': str(scene_path), 'sha256': sha(scene_path)},
    'loaded_code': {str(path.relative_to(ROOT)): sha(path) for path in (
        ROOT / 'blender/sewing.py', ROOT / 'a3d/mesh_refinement.py',
        ROOT / 'a3d/pattern_preparation.py', ROOT / 'tests/native_mesh_conditioning.py')},
    'budgets': {'max_seconds_at_boundaries': maximum_seconds,
                'max_cdt_passes': 8, 'max_added_vertices': 4000,
                'smoothing_passes_per_candidate': 8, 'smoothing_displacement_cm': .5},
    'elapsed_seconds': time.monotonic() - started, 'source_anchors_preserved': True,
    'reopened_equal': True, 'qualification': 'NONE', 'cloth': 'NOT_EXECUTED',
    'fitting': 'NOT_EXECUTED', 'product_acceptance': 'NOT_GRANTED',
    'short_interval_target': next(case['status'] for case in cases if case['id'] == 'short-fixed-source-intervals')})
