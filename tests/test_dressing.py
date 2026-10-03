import copy
import math
import unittest

from a3d.core import StudioError, digest
from a3d.dressing import (layer_collision_selection, migrate_legacy_layers, select_colliders,
                         source_references, validate_dressing)
from blender.dressing import audit_opening, loop_from_opening, section_segments
from tests.test_pattern_assembly import example
from a3d.pattern_assembly import map_digest


def dressing_fixture():
    ref = {'path': 'evidence/body.json', 'sha256': 'a'*64}
    # Open square sleeve around a closed four-sided body, all in centimetres.
    coords = [[x, y, z] for z in (-1., 1.) for x, y in ((-2., -2.), (2., -2.), (2., 2.), (-2., 2.))]
    faces = []
    for i in range(4):
        j = (i+1) % 4
        faces.extend([[i, j, j+4], [i, j+4, i+4]])
    payload, plan = example()
    payload.update(rest_cm=copy.deepcopy(coords), placed_cm=copy.deepcopy(coords), faces=faces,
                   panels={'sleeve': {'indices': list(range(8)), 'boundary': list(range(8)),
                                      'edges': {'entry': [0, 1, 2, 3, 0]}}}, seams={})
    plan['preform']['panels'] = {'sleeve': plan['preform']['panels']['left']}
    plan['assembly']['max_displacement_cm'] = 10.
    plan['collision']['clearance_cm'] = .2
    plan['layers'] = {'version': 1, 'source_ref': ref, 'mode': 'single',
        'interaction': 'one_way_declared', 'nodes': [
            {'id': 'body', 'kind': 'body', 'panels': [], 'colliders': ['body'], 'source_ref': ref},
            {'id': 'cloth', 'kind': 'garment', 'panels': ['sleeve'], 'colliders': [], 'source_ref': ref}],
        'inside_to_outside': [['body', 'cloth']]}
    region = {'id': 'limb', 'source_ref': ref, 'collider': 'body',
              'axis_start_cm': [0., 0., -2.], 'axis_end_cm': [0., 0., 2.],
              'section_parameters': [.25, .5, .75]}
    opening = {'id': 'entry', 'source_ref': ref, 'region': 'limb', 'section_parameter': .25,
               'edges': [{'piece': 'sleeve', 'edge': 'entry'}], 'plane_tolerance_cm': .01}
    plan['dressing'] = {'version': 1, 'required': True, 'source_ref': ref,
        'regions': [region], 'openings': [opening],
        'assignments': [{'piece': 'sleeve', 'region': 'limb', 'outward_normal_sign': 1}],
        'mount_order': ['entry'], 'milestones': []}
    body = [[x, y, z] for z in (-2., 2.) for x, y in ((-1., -1.), (1., -1.), (1., 1.), (-1., 1.))]
    geometry = {'object': 'body', 'vertices_cm': body,
                'faces': faces+[[0, 2, 1], [0, 3, 2], [4, 5, 6], [4, 6, 7]]}
    plan['mapping_sha256'] = map_digest(payload)
    return payload, coords, plan, geometry


def section_components(geometry, transforms):
    """Independent closed shells in one collider, without changing their shape."""
    result = {'object': geometry['object'], 'vertices_cm': [], 'faces': []}
    for transform in transforms:
        offset = len(result['vertices_cm'])
        result['vertices_cm'].extend(transform(point) for point in geometry['vertices_cm'])
        result['faces'].extend([[index+offset for index in face] for face in geometry['faces']])
    return result


class DressingContracts(unittest.TestCase):
    def test_absent_historical_contract_is_not_assessed(self):
        payload, plan = example()
        report = validate_dressing(payload, plan)
        self.assertEqual(report['status'], 'NOT_ASSESSED')
        self.assertEqual(report['qualification'], 'NONE')

    def test_changed_source_mapping_cannot_reuse_dressing_admission(self):
        payload, _, plan, _ = dressing_fixture()
        payload['rest_cm'][0][0] += .001
        with self.assertRaisesRegex(StudioError, 'source mapping is stale'):
            validate_dressing(payload, plan, ['body'])

    def test_required_assigned_region_without_passage_needs_clarification(self):
        payload, _, plan, _ = dressing_fixture()
        plan['dressing']['openings'] = []
        plan['dressing']['mount_order'] = []
        result = validate_dressing(payload, plan, ['body'])
        self.assertEqual(result['status'], 'NEEDS_CLARIFICATION')
        self.assertIn('ASSIGNED_REGION_PASSAGE_MISSING', result['missing'])

    def test_monolayer_migration_preserves_many_panels_and_many_body_parts(self):
        payload, plan = example()
        original = digest([payload, plan])
        ref = {'path': 'evidence/source.json', 'sha256': 'b'*64}
        report = migrate_legacy_layers(payload, {'bones': 'body', 'envelope': 'auxiliary_body'}, ref)
        self.assertEqual(report['status'], 'MIGRATED_EXPLICIT_SINGLE_LAYER')
        self.assertEqual(report['layers']['nodes'][-1]['panels'], ['left', 'right'])
        self.assertEqual(report['dressing'], 'NOT_ASSESSED')
        self.assertEqual(digest([payload, plan]), original)
        for roles in ({'undercoat': 'garment'}, {'unclassified': 'unknown'}):
            self.assertEqual(migrate_legacy_layers(payload, roles, ref)['status'], 'NEEDS_CLARIFICATION')

    def test_sourced_contract_and_layer_collider_selection(self):
        payload, coords, plan, _ = dressing_fixture()
        original = digest([payload, coords, plan])
        report = validate_dressing(payload, plan, ['body'])
        self.assertEqual(report['status'], 'DRESSING_CONTRACT_VALIDATED')
        self.assertEqual(select_colliders(plan['layers'], 'cloth'), ['body'])
        self.assertEqual(select_colliders(plan['layers'], 'body'), [])
        self.assertEqual(len(source_references(plan)), 1)
        self.assertEqual(digest([payload, coords, plan]), original)

    def test_optional_or_partial_contract_does_not_claim_full_coverage(self):
        payload, _, plan, _ = dressing_fixture()
        self.assertTrue(validate_dressing(payload, plan, ['body'])['full_coverage'])
        plan['dressing']['required'] = False
        self.assertFalse(validate_dressing(payload, plan, ['body'])['full_coverage'])
        plan['dressing']['assignments'] = []
        report = validate_dressing(payload, plan, ['body'])
        self.assertFalse(report['full_coverage'])
        self.assertEqual(report['unassigned_panels'], ['sleeve'])

    def test_cycles_unknown_panels_colliders_edges_and_source_paths_are_refused(self):
        for failure in ('cycle', 'panel', 'collider', 'edge', 'source', 'axis', 'order', 'milestone'):
            payload, _, plan, _ = dressing_fixture()
            if failure == 'cycle': plan['layers']['inside_to_outside'].append(['cloth', 'body'])
            if failure == 'panel': plan['layers']['nodes'][1]['panels'].append('unknown')
            if failure == 'collider': plan['dressing']['regions'][0]['collider'] = 'unknown'
            if failure == 'edge': plan['dressing']['openings'][0]['edges'][0]['edge'] = 'unknown'
            if failure == 'source': plan['dressing']['source_ref'] = {'path': '../escape.json', 'sha256': 'a'*64}
            if failure == 'axis': plan['dressing']['regions'][0]['axis_end_cm'] = [0., 0., -2.]
            if failure == 'order': plan['dressing']['mount_order'] = []
            if failure == 'milestone': plan['dressing']['milestones'] = [{'id': 'far', 'source_ref': plan['dressing']['source_ref'], 'translations_cm': {'sleeve': [100., 0., 0.]}}]
            with self.subTest(failure=failure), self.assertRaises(StudioError):
                validate_dressing(payload, plan, ['body'])

    def test_incomparable_garment_layers_are_not_given_an_invented_order(self):
        payload, _, plan, _ = dressing_fixture()
        layers = plan['layers']
        layers['mode'] = 'ordered'
        layers['nodes'].append({'id': 'undercoat', 'kind': 'garment', 'panels': [],
                                'colliders': ['undercoat'], 'source_ref': layers['source_ref']})
        layers['inside_to_outside'].append(['body', 'undercoat'])
        report = validate_dressing(payload, plan, ['body', 'undercoat'])
        self.assertEqual(report['status'], 'NEEDS_CLARIFICATION')
        layers['inside_to_outside'].append(['undercoat', 'cloth'])
        self.assertEqual(select_colliders(layers, 'cloth'), ['body', 'undercoat'])
        self.assertEqual(validate_dressing(payload, plan, ['body', 'undercoat'])['status'], 'DRESSING_CONTRACT_VALIDATED')
        self.assertEqual(layer_collision_selection(payload, plan)['colliders'], ['body', 'undercoat'])

    def test_two_active_layers_require_separate_native_simulations(self):
        payload, plan = example()
        ref = {'path': 'evidence/source.json', 'sha256': 'b'*64}
        plan['layers'] = {'version': 1, 'source_ref': ref, 'mode': 'ordered',
            'interaction': 'one_way_declared', 'nodes': [
                {'id': 'lining', 'kind': 'garment', 'panels': ['left'], 'colliders': [], 'source_ref': ref},
                {'id': 'outer', 'kind': 'garment', 'panels': ['right'], 'colliders': [], 'source_ref': ref}],
            'inside_to_outside': [['lining', 'outer']]}
        report = layer_collision_selection(payload, plan)
        self.assertEqual(report['status'], 'NEEDS_CLARIFICATION')
        self.assertEqual(report['reason'], 'SEPARATE_PER_LAYER_NATIVE_SIMULATIONS_REQUIRED')
        self.assertEqual(report['colliders'], [])


class MeasuredBodyPassages(unittest.TestCase):
    def test_unique_axis_section_excludes_other_body_parts_before_opening_check(self):
        payload, coords, plan, geometry = dressing_fixture()
        geometry = section_components(geometry, [lambda p: list(p),
            lambda p: [p[0]+10., p[1], p[2]], lambda p: [p[0]-10., p[1], p[2]]])
        before = digest([payload, coords, plan, geometry])
        result = audit_opening(payload, coords, plan['dressing']['openings'][0],
                               plan['dressing']['regions'][0], geometry, plan)
        self.assertTrue(result['ok'])
        self.assertAlmostEqual(result['minimum_passage_clearance_cm'], 1.)
        section = result['body_section']
        self.assertEqual(len(section['loops']), 3)
        self.assertEqual(len(section['excluded_loops']), 2)
        self.assertEqual(section['triangle_intersection_count'], 24)
        self.assertEqual(section['selected_segment_count'], 8)
        self.assertTrue(section['loops'][section['selected_loop']]['contains_sourced_axis'])
        self.assertEqual(digest([payload, coords, plan, geometry]), before)
        # A different sourced axis selects the other part, independently of what
        # fits this opening. It must now refuse passage; no "best fit" selection.
        region = copy.deepcopy(plan['dressing']['regions'][0])
        for key in ('axis_start_cm', 'axis_end_cm'):
            region[key][0] += 10.
        wrong_axis = audit_opening(payload, coords, plan['dressing']['openings'][0], region, geometry, plan)
        self.assertFalse(wrong_axis['ok'])
        self.assertEqual(wrong_axis['body_section']['selected_loop'], 1)

    def test_section_requires_exactly_one_strictly_axis_containing_loop(self):
        _, _, _, geometry = dressing_fixture()
        for origin, reason in (([4., 0., 0.], 'SOURCED_AXIS_OUTSIDE_SECTION_LOOPS'),
                               ([1., 0., 0.], 'SOURCED_AXIS_TOUCHES_SECTION')):
            result = section_segments(geometry, origin, [0., 0., 1.])
            self.assertFalse(result['ok'])
            self.assertEqual(result['reason'], reason)
        nested = section_components(geometry, [lambda p: list(p),
                                                lambda p: [2*p[0], 2*p[1], p[2]]])
        result = section_segments(nested, [0., 0., 0.], [0., 0., 1.])
        self.assertFalse(result['ok'])
        self.assertEqual(result['reason'], 'SOURCED_AXIS_IN_MULTIPLE_SECTION_LOOPS')
        self.assertEqual(result['containing_loops'], [0, 1])

    def test_touching_crossing_or_coincident_sections_remain_ambiguous(self):
        _, _, _, geometry = dressing_fixture()
        for shift in (0., 1.5, 2.):
            combined = section_components(geometry, [lambda p: list(p),
                lambda p: [p[0]+shift, p[1]+.25 if shift == 1.5 else p[1], p[2]]])
            result = section_segments(combined, [0., 0., 0.], [0., 0., 1.])
            self.assertFalse(result['ok'], shift)
            self.assertIn(result['reason'], ('SECTION_COINCIDENT_INTERSECTIONS_AMBIGUOUS',
                'SECTION_LOOPS_TOUCH_OR_INTERSECT', 'SECTION_NOT_CLOSED_OR_EMPTY'))

    def test_sleeve_passage_uses_actual_body_section(self):
        payload, coords, plan, geometry = dressing_fixture()
        opening, region = plan['dressing']['openings'][0], plan['dressing']['regions'][0]
        original = digest([payload, coords, plan, geometry])
        result = audit_opening(payload, coords, opening, region, geometry, plan)
        self.assertTrue(result['ok'])
        self.assertAlmostEqual(result['minimum_passage_clearance_cm'], 1.)
        self.assertEqual(digest([payload, coords, plan, geometry]), original)

    def test_tilted_limb_and_sleeve_keep_the_same_measured_passage(self):
        payload, coords, plan, geometry = dressing_fixture()
        def tilt(p):
            angle = math.radians(37.)
            return [p[0]*math.cos(angle)+p[2]*math.sin(angle)+5., p[1]-3.,
                    -p[0]*math.sin(angle)+p[2]*math.cos(angle)+11.]
        coords = [tilt(p) for p in coords]
        geometry['vertices_cm'] = [tilt(p) for p in geometry['vertices_cm']]
        region = plan['dressing']['regions'][0]
        for key in ('axis_start_cm', 'axis_end_cm'): region[key] = tilt(region[key])
        result = audit_opening(payload, coords, plan['dressing']['openings'][0], region, geometry, plan)
        self.assertTrue(result['ok'])
        self.assertAlmostEqual(result['minimum_passage_clearance_cm'], 1.)

    def test_closed_shoulder_larger_than_collar_is_refused_not_projected(self):
        payload, coords, plan, geometry = dressing_fixture()
        geometry['vertices_cm'] = [[3*x, 3*y, z] for x, y, z in geometry['vertices_cm']]
        before = digest(coords)
        result = audit_opening(payload, coords, plan['dressing']['openings'][0],
                               plan['dressing']['regions'][0], geometry, plan)
        self.assertFalse(result['ok'])
        self.assertFalse(result['section_inside_opening'])
        self.assertEqual(digest(coords), before)

    def test_a_hollow_skeleton_or_coplanar_section_is_not_a_solid_passage_proof(self):
        _, _, _, geometry = dressing_fixture()
        self.assertFalse(section_segments(geometry, [0., 0., 2.], [0., 0., 1.])['ok'])
        geometry['faces'].pop()
        self.assertEqual(section_segments(geometry, [0., 0., 0.], [0., 0., 1.])['reason'], 'REGION_COLLIDER_NOT_CLOSED')

    def test_only_declared_permanent_initial_gap_can_bridge_an_unsewn_opening(self):
        payload, coords, plan, _ = dressing_fixture()
        payload['panels']['sleeve']['edges']['first'] = [0, 1]
        payload['panels']['sleeve']['edges']['second'] = [8, 2, 3, 0]
        coords.append([2., -1.7, -1.])
        payload['panels']['sleeve']['indices'].append(8)
        payload['rest_cm'].append(list(coords[-1]))
        payload['seams']['join'] = {'kind': 'permanent', 'pairs': [[1, 8]]}
        opening = copy.deepcopy(plan['dressing']['openings'][0])
        opening['edges'] = [{'piece': 'sleeve', 'edge': 'first'}, {'piece': 'sleeve', 'edge': 'second'}]
        before = digest(coords)
        result = loop_from_opening(payload, coords, opening, plan)
        self.assertAlmostEqual(result['bridged_permanent_seams'][0]['gap_cm'], .3)
        self.assertGreater(.3, plan['consolidation']['weld_gap_cm'])
        self.assertEqual(digest(coords), before)
        for kind in ('closure', 'detachable'):
            payload['seams']['join']['kind'] = kind
            with self.assertRaises(StudioError): loop_from_opening(payload, coords, opening, plan)
        payload['seams']['join']['kind'] = 'permanent'
        coords[8][1] = 0.
        with self.assertRaises(StudioError): loop_from_opening(payload, coords, opening, plan)


if __name__ == '__main__':
    unittest.main()
