import copy
import unittest
from a3d.core import StudioError, contract, digest
from a3d.dressing import layer_collision_selection, sewing_graph_digest, rebind_layer_execution
from a3d.pattern_assembly import map_digest
from tests.test_pattern_assembly import example


def fixture():
    payload, plan = example(); ref = {'path': 'evidence/group.json', 'sha256': 'a'*64}
    plan['layers'] = {'version': 1, 'source_ref': ref, 'mode': 'ordered', 'interaction': 'one_way_declared',
        'nodes': [{'id': 'lining', 'kind': 'garment', 'panels': ['left'], 'colliders': [], 'source_ref': ref},
                  {'id': 'outer', 'kind': 'garment', 'panels': ['right'], 'colliders': [], 'source_ref': ref}],
        'inside_to_outside': [['lining', 'outer']]}
    plan['layer_execution'] = {'version': 1, 'mode': 'joint_coupled_single_object', 'source_ref': ref,
                               'source_mapping_sha256': map_digest(payload), 'sewing_graph_sha256': sewing_graph_digest(payload)}
    return payload, plan


class JointLayers(unittest.TestCase):
    def test_one_joint_object_retains_cross_layer_permanent_link_without_qualification(self):
        payload, plan = fixture(); before = digest([payload, plan]); contract('pattern-assembly', plan)
        result = layer_collision_selection(payload, plan)
        self.assertEqual(result['status'], 'LAYER_COLLIDERS_SELECTED')
        self.assertEqual(result['execution'], 'joint_coupled_single_object')
        self.assertEqual(result['qualification'], 'NONE')
        self.assertEqual(digest([payload, plan]), before)

    def test_detachable_or_closure_cannot_couple_independent_layers(self):
        for kind in ('detachable', 'closure'):
            payload, plan = fixture(); payload['seams']['join']['kind'] = kind
            plan['layer_execution']['source_mapping_sha256'] = map_digest(payload)
            plan['layer_execution']['sewing_graph_sha256'] = sewing_graph_digest(payload)
            with self.subTest(kind=kind):
                self.assertEqual(layer_collision_selection(payload, plan)['reason'], 'SEPARATE_UNCOUPLED_GROUPS_REQUIRED')

    def test_rest_link_type_owner_and_declared_mapping_drift_are_refused(self):
        for failure in ('rest', 'kind', 'owner', 'mapping'):
            payload, plan = fixture()
            if failure == 'rest': payload['rest_cm'][0][0] += .01
            if failure == 'kind': payload['seams']['join']['kind'] = 'detachable'
            if failure == 'owner': payload['seams']['join']['piece_b'] = 'left'
            if failure == 'mapping': plan['layer_execution']['source_mapping_sha256'] = 'b'*64
            with self.subTest(failure=failure), self.assertRaises(StudioError): layer_collision_selection(payload, plan)

    def test_external_frozen_layer_remains_inward_collider(self):
        payload, plan = fixture(); ref = plan['layers']['source_ref']
        plan['layers']['nodes'].insert(0, {'id': 'body', 'kind': 'body', 'panels': [], 'colliders': ['Body'], 'source_ref': ref})
        plan['layers']['inside_to_outside'].append(['body', 'lining'])
        result = layer_collision_selection(payload, plan, {'Body': 'mannequin'})
        self.assertEqual(result['colliders'], ['Body'])
        plan['layers']['nodes'][1]['colliders'] = ['ActiveLining']
        with self.assertRaises(StudioError): layer_collision_selection(payload, plan, {'Body': 'mannequin', 'ActiveLining': 'garment'})

    def test_regular_derivation_rebind_preserves_graph_and_original_plan(self):
        payload, plan = fixture(); before = digest(plan)
        payload['rest_cm'][0][0] += .01
        result = rebind_layer_execution(plan, payload)
        self.assertEqual(result['layer_execution']['source_mapping_sha256'], map_digest(payload))
        self.assertEqual(digest(plan), before)
        payload['seams']['join']['kind'] = 'detachable'
        with self.assertRaises(StudioError): rebind_layer_execution(plan, payload)
