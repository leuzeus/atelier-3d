"""Small isolated Blender dressing/ordering proofs; no Cloth or consumer scene."""
import copy
import json
import math
import os
from pathlib import Path
import sys

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))

import bpy
from a3d.core import StudioError, atomic_json, digest, sha
from blender.cloth_contacts import build_contact_context, check_contacts, check_motion
from blender.dressing import audit_dressing, layer_order_report
from tests.test_dressing import dressing_fixture, section_components

OUT = Path(os.environ['A3D_VALIDATION_OUTPUT'])


def object_from_geometry(name, geometry):
    mesh = bpy.data.meshes.new(name+'.mesh')
    mesh.from_pydata([[x/100 for x in point] for point in geometry['vertices_cm']], [], geometry['faces'])
    mesh.update()
    obj = bpy.data.objects.new(name, mesh)
    bpy.context.scene.collection.objects.link(obj)
    return obj


def run_case(name, transform=None, large_body=False, motion=False, stale=False,
             inward=False, missing_base=False, excessive_source_budget=False, legacy=False, optional=False,
             section_variant=None):
    payload, coords, plan, geometry = dressing_fixture()
    if section_variant in ('distant_parts', 'wrong_axis'):
        geometry = section_components(geometry, [lambda p: list(p),
            lambda p: [p[0]+10., p[1], p[2]], lambda p: [p[0]-10., p[1], p[2]]])
    elif section_variant == 'nested':
        geometry = section_components(geometry, [lambda p: list(p),
            lambda p: [1.5*p[0], 1.5*p[1], p[2]]])
    elif section_variant == 'crossing':
        geometry = section_components(geometry, [lambda p: list(p),
            lambda p: [p[0]+1.5, p[1]+.25, p[2]]])
    if section_variant in ('wrong_axis', 'outside_axis', 'touching_axis'):
        shift = {'wrong_axis': 10., 'outside_axis': 4., 'touching_axis': 1.}[section_variant]
        for key in ('axis_start_cm', 'axis_end_cm'):
            plan['dressing']['regions'][0][key][0] += shift
    if transform:
        coords = [transform(point) for point in coords]
        geometry['vertices_cm'] = [transform(point) for point in geometry['vertices_cm']]
        region = plan['dressing']['regions'][0]
        for key in ('axis_start_cm', 'axis_end_cm'):
            region[key] = transform(region[key])
    if large_body:
        geometry['vertices_cm'] = [[3*x, 3*y, z] for x, y, z in geometry['vertices_cm']]
    if motion:
        plan['dressing']['milestones'] = [{'id': 'before', 'source_ref': plan['dressing']['source_ref'],
                                          'translations_cm': {'sleeve': [-6., 0., 0.]}}]
    if missing_base or excessive_source_budget:
        plan['dressing']['milestones'] = [{'id': 'identical', 'source_ref': plan['dressing']['source_ref'],
                                          'translations_cm': {'sleeve': [0., 0., 0.]}}]
    if inward:
        plan['dressing']['assignments'][0]['outward_normal_sign'] = -1
    if optional:
        plan['dressing']['required'] = False
    folder = OUT/name
    source = folder/'evidence/body.json'
    atomic_json(source, {'geometry': geometry, 'region': plan['dressing']['regions'][0]})
    ref = {'path': 'evidence/body.json', 'sha256': sha(source)}
    def references(value):
        if isinstance(value, dict):
            if 'source_ref' in value and isinstance(value['source_ref'], dict):
                value['source_ref'] = copy.deepcopy(ref)
            for child in value.values(): references(child)
        elif isinstance(value, list):
            for child in value: references(child)
    references(plan)
    if legacy:
        del plan['dressing']
    if stale:
        atomic_json(source, {'changed': True})
    obj = object_from_geometry('body', geometry)
    try:
        bpy.context.view_layer.update()
        context = build_contact_context(payload, [obj], clearance_cm=plan['collision']['clearance_cm'])
        before = digest([payload, coords, plan])
        try:
            report = audit_dressing(payload, coords, plan, colliders=[obj], project=folder,
                source_coords_cm=(None if missing_base else [[x+20, y, z] for x, y, z in coords]
                                  if excessive_source_budget else coords),
                contact_check=lambda points: check_contacts(context, points),
                motion_check=lambda a, b, i, j: check_motion(context, a, b, i, j,
                    max_step_cm=.2, max_subdivisions=64))
        except StudioError as error:
            if not stale:
                raise
            report = {'status': 'EXPECTED_SOURCE_REFUSAL', 'message': str(error), 'qualification': 'NONE'}
        assert digest([payload, coords, plan]) == before
        atomic_json(folder/'report.json', report)
        return report
    finally:
        mesh = obj.data
        bpy.data.objects.remove(obj, do_unlink=True)
        bpy.data.meshes.remove(mesh)


def layer_cases():
    payload, _, plan, _ = dressing_fixture()
    payload['rest_cm'] = [[x, y, z] for z in (0., .5) for x, y in ((0., 0.), (2., 0.), (2., 2.), (0., 2.))]
    coords = copy.deepcopy(payload['rest_cm'])
    payload['faces'] = [[0, 1, 2], [0, 2, 3], [4, 5, 6], [4, 6, 7]]
    payload['panels'] = {name: {'indices': list(range(start, start+4)), 'edges': {}, 'boundary': []}
                         for name, start in (('inner', 0), ('outer', 4))}
    ref = plan['layers']['source_ref']
    plan['layers'] = {'version': 1, 'source_ref': ref, 'mode': 'ordered', 'interaction': 'one_way_declared',
        'nodes': [{'id': name, 'kind': 'garment', 'panels': [name], 'colliders': [],
                   'source_ref': ref, 'outward_normal_sign': 1} for name in ('inner', 'outer')],
        'inside_to_outside': [['inner', 'outer']]}
    plan['dressing']['assignments'] = []
    correct = layer_order_report(payload, coords, plan, {})
    assert correct['ok']
    inverted = copy.deepcopy(coords)
    for point in inverted[4:]: point[2] = -.5
    wrong = layer_order_report(payload, inverted, plan, {})
    assert not wrong['ok'] and wrong['relations'][0]['minimum_signed_normal_clearance_cm'] < 0
    plan['layers']['nodes'][0].pop('outward_normal_sign')
    missing = layer_order_report(payload, coords, plan, {})
    assert not missing['ok'] and missing['missing']
    return {'ordered_bands': correct, 'inverted_bands': wrong, 'missing_sourced_side': missing}


angle = math.radians(37.)
def tilt(point):
    x, y, z = point
    return [x*math.cos(angle)+z*math.sin(angle)+5., y-3., -x*math.sin(angle)+z*math.cos(angle)+11.]

cases = {'sleeve': run_case('sleeve'), 'tilted_sleeve': run_case('tilted-sleeve', transform=tilt),
         'closed_shoulder': run_case('closed-shoulder', large_body=True),
         'traversing_motion': run_case('traversing-motion', motion=True),
         'stale_source': run_case('stale-source', stale=True),
         'inward_side': run_case('inward-side', inward=True),
         'missing_motion_base': run_case('missing-motion-base', missing_base=True),
         'source_budget': run_case('source-budget', excessive_source_budget=True),
         'legacy_dressing': run_case('legacy-dressing', legacy=True),
         'legacy_stale_layer_source': run_case('legacy-stale-layer-source', legacy=True, stale=True),
         'optional_contract': run_case('optional-contract', optional=True),
         'distant_sections': run_case('distant-sections', section_variant='distant_parts'),
         'wrong_axis_section': run_case('wrong-axis-section', section_variant='wrong_axis'),
         'axis_outside_sections': run_case('axis-outside-sections', section_variant='outside_axis'),
         'axis_touching_section': run_case('axis-touching-section', section_variant='touching_axis'),
         'nested_sections': run_case('nested-sections', section_variant='nested'),
         'crossing_sections': run_case('crossing-sections', section_variant='crossing'),
         'layers': layer_cases()}
assert cases['sleeve']['status'] == cases['tilted_sleeve']['status'] == 'READY'
assert cases['closed_shoulder']['status'] == cases['traversing_motion']['status'] == 'NEEDS_CORRECTION'
assert cases['stale_source']['status'] == 'EXPECTED_SOURCE_REFUSAL'
assert cases['inward_side']['status'] == cases['source_budget']['status'] == 'NEEDS_CORRECTION'
assert cases['missing_motion_base']['status'] == 'NEEDS_CLARIFICATION'
assert cases['legacy_dressing']['status'] == 'NOT_ASSESSED'
assert cases['legacy_stale_layer_source']['status'] == 'EXPECTED_SOURCE_REFUSAL'
assert cases['optional_contract']['status'] == 'NOT_ASSESSED'
assert cases['optional_contract']['measured_status'] == 'GEOMETRY_CHECKS_PASSED'
assert cases['optional_contract']['full_coverage'] is False
assert cases['distant_sections']['status'] == 'READY'
section = cases['distant_sections']['openings'][0]['body_section']
assert len(section['loops']) == 3 and len(section['excluded_loops']) == 2
assert section['selected_segment_count'] == 8 and section['triangle_intersection_count'] == 24
assert cases['wrong_axis_section']['status'] == 'NEEDS_CORRECTION'
assert cases['wrong_axis_section']['openings'][0]['body_section']['selected_loop'] == 1
for name, reason in (('axis_outside_sections', 'SOURCED_AXIS_OUTSIDE_SECTION_LOOPS'),
                     ('axis_touching_section', 'SOURCED_AXIS_TOUCHES_SECTION'),
                     ('nested_sections', 'SOURCED_AXIS_IN_MULTIPLE_SECTION_LOOPS'),
                     ('crossing_sections', 'SECTION_LOOPS_TOUCH_OR_INTERSECT')):
    assert cases[name]['status'] == 'NEEDS_CORRECTION', (name, cases[name]['status'])
    assert cases[name]['openings'][0]['body_section']['reason'] == reason
assert cases['traversing_motion']['motion'] and not cases['traversing_motion']['motion'][0]['ok']
result = {'status': 'PASS_GEOMETRIC_DRESSING_ONLY', 'blender': bpy.app.version_string,
          'cases': cases, 'simulation': 'NOT_EXECUTED', 'qualification': 'NONE',
          'interactive_scene': 'UNTOUCHED_SEPARATE_BACKGROUND_PROCESS'}
atomic_json(OUT/'result.json', result)
print(json.dumps({'status': result['status'], 'cases': list(cases)}))
