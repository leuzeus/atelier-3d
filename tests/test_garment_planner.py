import copy
import unittest

from a3d.core import StudioError, digest
from a3d.garment_planner import plan_assembly


def example():
    ref = {'path': 'approved/board.json', 'sha256': 'a'*64}
    pieces = [{'id': pid, 'component_id': 'garment', 'role': role, 'side': 'center',
               'layer': layer, 'edges': ['left', 'right'], 'source_ref': ref}
              for pid, role, layer in [('shirt', 'front', 'inner'), ('coat', 'front', 'outer')]]
    nodes = [{'id': 'body', 'kind': 'body', 'panels': [], 'colliders': ['body'], 'source_ref': ref}]
    nodes += [{'id': layer, 'kind': 'garment', 'panels': [pid], 'colliders': [], 'source_ref': ref}
              for pid, layer in [('shirt', 'inner'), ('coat', 'outer')]]
    return {'version': 1, 'source_ref': ref, 'body_ref': {'path': 'body/selection.json', 'sha256': 'b'*64},
            'pieces': pieces, 'links': [],
            'layers': {'version': 1, 'source_ref': ref, 'mode': 'ordered',
                       'interaction': 'one_way_declared', 'nodes': nodes,
                       'inside_to_outside': [['body', 'inner'], ['inner', 'outer']]},
            'budgets': {'max_frames': 120, 'max_iterations': 12, 'max_seconds': 60,
                        'max_displacement_cm': 2., 'max_strain_relative': .1}}


def link(kind='permanent'):
    return {'id': 'bridge', 'kind': kind, 'piece_a': 'shirt', 'edge_a': 'left',
            'piece_b': 'coat', 'edge_b': 'right', 'source_ref': example()['source_ref']}


class GarmentPlanner(unittest.TestCase):
    def test_source_bound_semantics_survive_planning_and_invalidate_changed_material_axes(self):
        data=example();data['pieces'][0].update(longitudinal_uv_axis='v',guide_edges={'side':'left'})
        first=plan_assembly(data)
        self.assertEqual(first['piece_semantics']['shirt']['longitudinal_uv_axis'],'v')
        data['pieces'][0]['longitudinal_uv_axis']='u'
        self.assertNotEqual(plan_assembly(data)['plan_sha256'],first['plan_sha256'])
        data['pieces'][0]['guide_edges']['side']='missing'
        with self.assertRaises(StudioError) as raised:plan_assembly(data)
        self.assertEqual(raised.exception.diagnostic['reason'],'UNKNOWN_GUIDE_EDGE')

    def test_independent_layers_are_ordered_and_receive_frozen_inner_colliders(self):
        data = example(); before = digest(data)
        plan = plan_assembly(data)
        inner, outer = plan['groups']
        self.assertEqual(inner['pieces'], ['shirt'])
        self.assertEqual(outer['pieces'], ['coat'])
        self.assertEqual(outer['inner_group_colliders'], [inner['id']])
        self.assertEqual(outer['body_colliders'], ['body'])
        self.assertEqual(plan['simulation'], 'NOT_EXECUTED')
        self.assertEqual(plan['qualification'], 'NONE')
        self.assertEqual(digest(data), before)

    def test_permanent_cross_layer_link_requires_qualified_joint_capability(self):
        data = example(); data['links'] = [link()]
        with self.assertRaises(StudioError) as raised:
            plan_assembly(data)
        self.assertEqual(raised.exception.diagnostic['reason'], 'COUPLED_MULTILAYER_UNAVAILABLE')
        plan = plan_assembly(data, capabilities=['coupled_multilayer'])
        self.assertEqual(len(plan['groups']), 1)
        self.assertEqual(plan['groups'][0]['pieces'], ['coat', 'shirt'])
        self.assertEqual(plan['groups'][0]['cross_layer_permanent_links'], ['bridge'])
        self.assertEqual(plan['link_graph'][0]['kind'], 'permanent')
        self.assertEqual(plan['qualification'], 'NONE')

    def test_nonpermanent_links_do_not_couple_or_disappear(self):
        for kind in ['closure', 'detachable', 'free_contact', 'temporary_support']:
            data = example(); data['links'] = [link(kind)]
            plan = plan_assembly(data)
            self.assertEqual(len(plan['groups']), 2)
            self.assertEqual(plan['link_graph'], data['links'])
            self.assertTrue(all(g['links'] == ['bridge'] for g in plan['groups']))

    def test_detachable_link_can_share_a_permanent_named_edge(self):
        data = example(); data['links'] = [link(), {**link('detachable'), 'id': 'removable'}]
        self.assertEqual(len(plan_assembly(data, ['coupled_multilayer'])['link_graph']), 2)
        data['links'][1]['kind'] = 'permanent'
        with self.assertRaisesRegex(StudioError, 'Two permanent links'):
            plan_assembly(data, ['coupled_multilayer'])

    def test_input_array_permutations_do_not_change_plan(self):
        data = example(); plan = plan_assembly(data)
        data['pieces'].reverse(); data['layers']['nodes'].reverse()
        data['layers']['inside_to_outside'].reverse()
        for piece in data['pieces']:piece['edges'].reverse()
        self.assertEqual(plan_assembly(data), plan)

    def test_body_identity_or_budget_changes_invalidate_plan(self):
        data = example(); plan = plan_assembly(data)
        for field in ['body_ref', 'budgets']:
            candidate = copy.deepcopy(data)
            if field == 'body_ref': candidate[field]['sha256'] = 'c'*64
            else: candidate[field]['max_frames'] += 1
            self.assertNotEqual(plan_assembly(candidate)['plan_sha256'], plan['plan_sha256'])

    def test_missing_wrong_layer_unknown_edges_duplicate_and_cycle_are_refused(self):
        for failure in ['layer', 'missing', 'edge', 'duplicate', 'cycle', 'budget', 'role']:
            data = example()
            if failure == 'layer': data['pieces'][0]['layer'] = 'outer'
            if failure == 'missing': data['layers']['nodes'][1]['panels'] = ['absent']
            if failure == 'edge': data['links'] = [{**link('closure'), 'edge_a': 'absent'}]
            if failure == 'duplicate': data['pieces'].append(copy.deepcopy(data['pieces'][0]))
            if failure == 'cycle': data['layers']['inside_to_outside'].append(['outer', 'inner'])
            if failure == 'budget': data['budgets']['max_frames'] = 0
            if failure == 'role': data['pieces'][0]['role'] = 'guess_from_sex'
            with self.subTest(failure=failure), self.assertRaises(StudioError):
                plan_assembly(data)

    def test_contraction_cycle_refused_before_any_simulation(self):
        data = example()
        piece = copy.deepcopy(data['pieces'][0]); piece.update(id='middle', layer='middle')
        data['pieces'].append(piece)
        node = copy.deepcopy(data['layers']['nodes'][1]); node.update(id='middle', panels=['middle'])
        data['layers']['nodes'].append(node)
        data['layers']['inside_to_outside'] = [['body', 'inner'], ['inner', 'middle'], ['middle', 'outer']]
        data['links'] = [link()]
        with self.assertRaises(StudioError) as raised:
            plan_assembly(data, ['coupled_multilayer'])
        self.assertEqual(raised.exception.diagnostic['reason'], 'COUPLED_ORDER_CYCLE')

    def test_panel_unique_still_has_the_full_stage_sequence_without_fictitious_link(self):
        data = example(); data['pieces'] = data['pieces'][:1]
        data['layers']['nodes'] = data['layers']['nodes'][:2]
        data['layers']['mode'] = 'single'; data['layers']['inside_to_outside'] = [['body', 'inner']]
        plan = plan_assembly(data)
        self.assertEqual(len(plan['groups']), 1)
        self.assertEqual(plan['link_graph'], [])
        self.assertEqual(plan['groups'][0]['stages'][-1], 'motion')
