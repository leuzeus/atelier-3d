"""One-piece cloth preparation is explicit; it never proves a fastened belt."""
import copy
import unittest
from unittest.mock import patch

from a3d.core import StudioError, contract, digest
from a3d.pattern_assembly import bounded_close, consolidate, map_digest, preform_coordinates
from a3d.sewing import validate_recipe, weld_permanent
from blender.sewing import build_mesh, mesh_recipe_digest
from tests.test_pattern_assembly import example
from tests.test_sewing import sources


def belt_recipe():
    data, recipe = sources()
    piece = copy.deepcopy(data['pieces']['front'])
    piece['vertices'] = [[0, 0], [2, 0], [2, 2], [0, 2]]
    data['component_id'] = recipe['component_id'] = 'garment.belt'
    data['pieces'] = {'belt': piece}
    data['seams'] = [{'id': 'buckle-opening', 'piece_a': 'belt', 'edge_a': 'left',
                     'piece_b': 'belt', 'edge_b': 'right', 'orientation': 'forward', 'kind': 'closure'}]
    recipe.update(trial_mode='single_panel', trial_pieces=['belt'], pins=[],
                  seams={'buckle-opening': {'kind': 'closure', 'ease_b_over_a': 0., 'tolerance_relative': .02}},
                  placements={'belt': copy.deepcopy(recipe['placements']['front'])})
    recipe['mesh']['spacing_cm'] = 4.
    return data, recipe


def belt_assembly():
    payload, plan = example()
    payload.update(rest_cm=payload['rest_cm'][:4], placed_cm=payload['placed_cm'][:4],
                   faces=payload['faces'][:2], panels={'left': payload['panels']['left']},
                   source_vertex_indices=[10, 11, 12, 13],
                   seams={'opening': {'kind': 'closure', 'piece_a': 'left', 'piece_b': 'left',
                                      'parameters': [0., 1.], 'pairs': [[0, 1], [3, 2]]},
                          'removable': {'kind': 'detachable', 'piece_a': 'left', 'piece_b': 'left',
                                        'parameters': [0., 1.], 'pairs': [[3, 0], [2, 1]]}},
                   trial_mode='single_panel')
    payload['single_panel_source'] = {'component_id': payload['component_id'],
        'source_garment_sha256': payload['source_garment_sha256'],
        'piece_ids': ['left'], 'trial_pieces': ['left'],
        'seam_kinds': {'opening': 'closure', 'removable': 'detachable'}}
    plan['preform']['panels'].pop('right')
    plan['mapping_sha256'] = map_digest(payload)
    return payload, plan


class SinglePanelRecipe(unittest.TestCase):
    def test_explicit_single_panel_preserves_closure_kind_and_source(self):
        data, recipe = belt_recipe()
        before = copy.deepcopy((data, recipe))
        reports, _ = validate_recipe(data, recipe)
        self.assertEqual(reports[0]['kind'], 'closure')
        self.assertEqual((data, recipe), before)
        data['seams'][0]['kind'] = recipe['seams']['buckle-opening']['kind'] = 'detachable'
        self.assertEqual(validate_recipe(data, recipe)[0][0]['kind'], 'detachable')

    def test_single_panel_without_links_is_allowed(self):
        data, recipe = belt_recipe()
        data['seams'], recipe['seams'] = [], {}
        self.assertEqual(validate_recipe(data, recipe)[0], [])

    def test_default_and_explicit_sewn_mode_still_need_two_panels(self):
        for mode in (None, 'sewn'):
            data, recipe = belt_recipe()
            if mode is None:
                recipe.pop('trial_mode')
            else:
                recipe['trial_mode'] = mode
            with self.subTest(mode=mode), self.assertRaises(StudioError):
                contract('sewing-recipe', recipe)
            with self.assertRaises(StudioError):
                validate_recipe(data, recipe)
        data, recipe = sources()
        validate_recipe(data, recipe)
        recipe['trial_pieces'] = ['front', 'sleeve-right']
        with self.assertRaisesRegex(StudioError, 'permanent seam'):
            validate_recipe(data, recipe)

    def test_duplicate_foreign_hidden_panel_and_hidden_permanent_are_refused(self):
        for case in ('duplicate', 'foreign', 'two_source_panels', 'permanent', 'hidden_permanent', 'changed_kind'):
            data, recipe = belt_recipe()
            if case == 'duplicate':
                recipe['trial_pieces'] = ['belt', 'belt']
            elif case == 'foreign':
                recipe['trial_pieces'] = ['unknown']
            elif case == 'two_source_panels':
                data['pieces']['other'] = copy.deepcopy(data['pieces']['belt'])
                recipe['placements']['other'] = copy.deepcopy(recipe['placements']['belt'])
            elif case == 'permanent':
                recipe['seams']['buckle-opening']['kind'] = data['seams'][0]['kind'] = 'permanent'
            elif case == 'hidden_permanent':
                data['seams'][0]['kind'] = 'permanent'
            else:
                data['seams'][0]['kind'] = 'detachable'
            with self.subTest(case=case), self.assertRaises(StudioError):
                validate_recipe(data, recipe)

    def test_collision_pin_and_quality_declarations_are_still_checked(self):
        for case in ('collision', 'pin', 'strain'):
            data, recipe = belt_recipe()
            if case == 'collision':
                recipe['no_collision_reason'] = ''
            elif case == 'pin':
                recipe['pins'] = [{'piece': 'belt', 'edge': 'missing', 'weight': 1.}]
            else:
                recipe['mesh']['min_stretch'] = recipe['mesh']['max_stretch']
            with self.subTest(case=case), self.assertRaises(StudioError):
                validate_recipe(data, recipe)

    def test_build_mesh_emits_source_provenance_without_changing_legacy_digest(self):
        data, recipe = sources()
        self.assertEqual(mesh_recipe_digest(recipe), digest({key: recipe[key] for key in
                         ('component_id', 'mesh', 'placements', 'seams', 'pins')}))
        data, recipe = belt_recipe()
        def rectangle(boundary, _recipe, _regular):
            points = copy.deepcopy(boundary['polygon'])
            self.assertEqual(len(points), 4)
            return points, [[0, 1, 2], [0, 2, 3]], {i: i for i in range(4)}
        with patch('blender.sewing.triangulate', rectangle), patch('blender.sewing.placed_point', lambda p, _: [*p, 0.]):
            payload = build_mesh(data, recipe)
        self.assertEqual(payload['single_panel_source'], {
            'component_id': 'garment.belt', 'source_garment_sha256': digest(data),
            'piece_ids': ['belt'], 'trial_pieces': ['belt'], 'seam_kinds': {'buckle-opening': 'closure'}})
        original = mesh_recipe_digest(recipe)
        recipe['trial_pieces'] = ['other']
        self.assertNotEqual(mesh_recipe_digest(recipe), original)
        recipe['trial_pieces'] = ['belt']
        recipe['trial_mode'] = 'sewn'
        self.assertNotEqual(mesh_recipe_digest(recipe), original)


class SinglePanelAssembly(unittest.TestCase):
    def test_noop_close_and_consolidate_preserve_all_geometry_and_link_endpoints(self):
        payload, plan = belt_assembly()
        original = copy.deepcopy(payload)
        coords, _ = preform_coordinates(payload, plan)
        closed, closure = bounded_close(payload, coords, plan)
        self.assertEqual(closed, coords)
        self.assertEqual(closure['status'], 'GEOMETRY_READY')
        self.assertEqual(closure['accepted_steps'], 0)
        self.assertEqual(closure['max_displacement_cm'], 0.)
        with patch('a3d.pattern_assembly.weld_permanent', side_effect=AssertionError('No weld for one panel')):
            result, report = consolidate(payload, closed, plan)
        for record in (closure, report):
            self.assertEqual(record['operation'], 'SINGLE_PANEL_NO_OP')
            self.assertEqual(record['explicit_unions'], 0)
            self.assertFalse(record['sewing_executed'])
            self.assertFalse(record['welding_executed'])
            self.assertEqual(record['closure_behavior'], 'NOT_QUALIFIED')
            self.assertEqual(record['qualification'], 'NONE')
        self.assertEqual(result['rest_cm'], coords)
        self.assertEqual(result['placed_cm'], coords)
        for key in ('panels', 'faces', 'seams', 'source_garment_sha256', 'source_vertex_indices', 'single_panel_source'):
            self.assertEqual(result[key], payload[key], key)
        self.assertEqual(result['source_vertex_map'], {str(i): i for i in range(4)})
        self.assertEqual(result['source_vertex_cohorts'], {str(i): [10+i] for i in range(4)})
        self.assertEqual(result['source_rest_triangles_cm'],
                         [[payload['rest_cm'][i][:2] for i in face] for face in payload['faces']])
        self.assertEqual(result['source_face_vertex_ids'], payload['faces'])
        self.assertEqual(result['source_face_pieces'], ['left', 'left'])
        self.assertEqual(result['quality']['rest_area_cm2'], 4.)
        self.assertEqual(payload, original)

    def test_missing_inconsistent_or_subset_provenance_is_refused(self):
        for case in ('missing', 'component', 'source_sha', 'source_panels', 'trial', 'seam_kind', 'hidden_permanent'):
            payload, plan = belt_assembly()
            source = payload['single_panel_source']
            if case == 'missing':
                payload.pop('single_panel_source')
            elif case == 'component':
                source['component_id'] = 'other'
            elif case == 'source_sha':
                source['source_garment_sha256'] = 'changed'
            elif case == 'source_panels':
                source['piece_ids'].append('hidden')
            elif case == 'trial':
                source['trial_pieces'].append('left')
            elif case == 'seam_kind':
                source['seam_kinds']['opening'] = 'detachable'
            else:
                source['seam_kinds']['hidden'] = 'permanent'
            plan['mapping_sha256'] = map_digest(payload)
            with self.subTest(case=case), self.assertRaises(StudioError):
                bounded_close(payload, payload['placed_cm'], plan)
            with self.assertRaises(StudioError):
                consolidate(payload, payload['placed_cm'], plan)

    def test_adding_permanent_pair_to_mode_cannot_enable_a_weld(self):
        payload, plan = belt_assembly()
        payload['seams']['opening']['kind'] = 'permanent'
        payload['single_panel_source']['seam_kinds']['opening'] = 'permanent'
        plan['mapping_sha256'] = map_digest(payload)
        with self.assertRaises(StudioError):
            consolidate(payload, payload['placed_cm'], plan)

    def test_no_op_requires_opt_in_and_does_not_weaken_general_weld(self):
        payload, plan = belt_assembly()
        payload.pop('trial_mode')
        plan['mapping_sha256'] = map_digest(payload)
        self.assertEqual(bounded_close(payload, payload['placed_cm'], plan)[1]['status'], 'REFUSED')
        with self.assertRaisesRegex(StudioError, 'No permanent seam pairs'):
            consolidate(payload, payload['placed_cm'], plan)
        with self.assertRaisesRegex(StudioError, 'No permanent seam pairs'):
            weld_permanent(payload['placed_cm'], payload['faces'], payload['seams'], .01)

    def test_legacy_mapping_identity_and_two_panel_refusal(self):
        payload, plan = example()
        self.assertEqual(map_digest(payload), digest({key: payload.get(key) for key in
            ('version', 'component_id', 'source_garment_sha256', 'rest_cm', 'faces', 'panels', 'seams')}))
        payload['trial_mode'] = 'single_panel'
        payload['single_panel_source'] = {'component_id': payload['component_id'],
            'source_garment_sha256': payload['source_garment_sha256'],
            'piece_ids': ['left', 'right'], 'trial_pieces': ['left'], 'seam_kinds': {}}
        payload['seams'] = {}
        plan['mapping_sha256'] = map_digest(payload)
        with self.assertRaisesRegex(StudioError, 'complete and consistent'):
            bounded_close(payload, payload['placed_cm'], plan)
        with self.assertRaisesRegex(StudioError, 'complete and consistent'):
            consolidate(payload, payload['placed_cm'], plan)

    def test_binding_collision_geometry_support_and_topology_gates_remain(self):
        payload, plan = belt_assembly()
        baseline = plan['mapping_sha256']
        payload['single_panel_source']['trial_pieces'] = ['changed']
        self.assertNotEqual(map_digest(payload), baseline)
        with self.assertRaisesRegex(StudioError, 'mapping changed'):
            bounded_close(payload, payload['placed_cm'], plan)
        payload, plan = belt_assembly()
        plan['collision']['required'] = True
        self.assertEqual(bounded_close(payload, payload['placed_cm'], plan)[1]['status'], 'REFUSED')
        self.assertEqual(bounded_close(payload, payload['placed_cm'], plan, lambda _: False)[1]['status'], 'REFUSED')
        coords = copy.deepcopy(payload['placed_cm'])
        coords[1][0] *= 2
        self.assertEqual(bounded_close(payload, coords, plan, lambda _: True)[1]['reason_category'], 'geometry_safety')
        with self.assertRaises(StudioError):
            consolidate(payload, coords, plan)
        plan['supports']['functional'] = [{'id': 'bad', 'piece': 'missing', 'weight': 1., 'source_ref': 'fixture:bad'}]
        with self.assertRaises(StudioError):
            consolidate(payload, payload['placed_cm'], plan)
        payload, plan = belt_assembly()
        payload['faces'].append(copy.deepcopy(payload['faces'][0]))
        plan['mapping_sha256'] = map_digest(payload)
        with self.assertRaises(StudioError):
            consolidate(payload, payload['placed_cm'], plan)


if __name__ == '__main__':
    unittest.main()
