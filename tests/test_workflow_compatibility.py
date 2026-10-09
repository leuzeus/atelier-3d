import copy
import unittest
from a3d.workflow_compatibility import validate_node_inputs


class Provider:
    def __init__(self):
        self.nodes = {'Load': {'name': 'Load', 'output_types': ['IMAGE'], 'inputs': [
            {'name': 'model', 'required': True, 'type': 'COMBO', 'choices': ['installed.safetensors'], 'is_link': False}]},
            'Compute': {'name': 'Compute', 'output_types': ['IMAGE'], 'inputs': [
                {'name': 'image', 'required': True, 'type': 'IMAGE', 'is_link': True},
                {'name': 'steps', 'required': True, 'type': 'INT', 'is_link': False, 'options': {'min': 1, 'max': 80}}]}}
        self.calls = []

    def call(self, name, arguments):
        self.calls.append((name, arguments))
        return self.nodes[arguments['name']]


class CompatibilityTests(unittest.TestCase):
    def setUp(self):
        self.provider = Provider()
        self.graph = {'1': {'class_type': 'Load', 'inputs': {'model': 'installed.safetensors'}},
                      '2': {'class_type': 'Compute', 'inputs': {'image': ['1', 0], 'steps': 20}}}

    def test_installed_schema_and_links_are_checked_without_execution(self):
        report = validate_node_inputs(self.graph, self.provider)
        self.assertTrue(report['valid'])
        self.assertEqual(report['execution'], 'NOT_EXECUTED')
        self.assertTrue(all(name == 'nodes' for name, _ in self.provider.calls))

    def test_missing_model_required_input_and_node_are_rejected(self):
        for edit, reason in ((lambda g: g['1']['inputs'].update(model='missing.safetensors'), 'CHOICE_UNAVAILABLE'),
                             (lambda g: g['2']['inputs'].pop('steps'), 'MISSING_REQUIRED_INPUT'),
                             (lambda g: g['2'].update(class_type='Missing'), 'NODE_SCHEMA_UNAVAILABLE'),
                             (lambda g: g['2']['inputs'].update(image=['1', 3]), 'INCOMPATIBLE_LINK'),
                             (lambda g: g['2']['inputs'].update(steps=100), 'NUMBER_OUTSIDE_PROVIDER_DOMAIN')):
            graph = copy.deepcopy(self.graph); edit(graph)
            result = validate_node_inputs(graph, self.provider)
            self.assertFalse(result['valid'])
            self.assertIn(reason, {error['reason'] for error in result['errors']})
