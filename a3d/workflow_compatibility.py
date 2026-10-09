"""Validate a graph against the node schemas observed on the target provider."""
import math
from .core import StudioError, digest


def validate_node_inputs(graph, native):
    schemas, errors = {}, []
    for name in sorted({row['class_type'] for row in graph.values()}):
        try:
            node = native.call('nodes', {'action': 'get', 'name': name})
            if node.get('name') != name or not isinstance(node.get('inputs'), list) or not isinstance(node.get('output_types'), list):
                raise StudioError('Unrecognized provider node schema')
            schemas[name] = node
        except Exception as exc:
            errors.append({'node_type': name, 'reason': 'NODE_SCHEMA_UNAVAILABLE', 'detail': str(exc)})
    for node_id, row in graph.items():
        schema = schemas.get(row['class_type'])
        if schema is None:
            continue
        inputs = row['inputs']
        descriptors = {entry['name']: entry for entry in schema['inputs']}
        for field in sorted(set(inputs)-set(descriptors)):
            errors.append({'node': node_id, 'input': field, 'reason': 'UNKNOWN_INPUT'})
        for field, descriptor in descriptors.items():
            if field not in inputs:
                if descriptor.get('required') is True:
                    errors.append({'node': node_id, 'input': field, 'reason': 'MISSING_REQUIRED_INPUT'})
                continue
            value = inputs[field]; kind = descriptor.get('type')
            linked = isinstance(value, list) and len(value) == 2 and isinstance(value[0], str) and type(value[1]) is int
            if linked:
                origin = graph.get(value[0]); source = schemas.get(origin['class_type']) if origin else None
                outputs = source.get('output_types', []) if source else []
                if value[1] < 0 or value[1] >= len(outputs) or kind not in (outputs[value[1]], '*') and outputs[value[1]] != '*':
                    errors.append({'node': node_id, 'input': field, 'reason': 'INCOMPATIBLE_LINK'})
            elif descriptor.get('is_link') is True:
                errors.append({'node': node_id, 'input': field, 'reason': 'LINK_REQUIRED'})
            elif kind == 'COMBO' and value not in descriptor.get('choices', []):
                errors.append({'node': node_id, 'input': field, 'reason': 'CHOICE_UNAVAILABLE', 'value': value})
            elif kind in ('INT', 'FLOAT'):
                options = descriptor.get('options', {})
                if type(value) not in (int, float) or kind == 'INT' and type(value) is not int or not math.isfinite(value):
                    errors.append({'node': node_id, 'input': field, 'reason': 'INVALID_NUMBER'})
                elif value < options.get('min', -math.inf) or value > options.get('max', math.inf):
                    errors.append({'node': node_id, 'input': field, 'reason': 'NUMBER_OUTSIDE_PROVIDER_DOMAIN'})
            elif kind == 'STRING' and not isinstance(value, str) or kind == 'BOOLEAN' and type(value) is not bool:
                errors.append({'node': node_id, 'input': field, 'reason': 'INVALID_VALUE_TYPE'})
    return {'valid': not errors, 'errors': errors, 'node_schema_sha256': digest(schemas),
            'graph_sha256': digest(graph), 'scope': 'OBSERVED_PROVIDER_NODE_SCHEMAS', 'execution': 'NOT_EXECUTED'}


def compatibility_report(native, path, spec, graph):
    provider = native.call('validate_workflow', {'workflow_path': str(path)})
    if not spec.get('node_schema_preflight'):
        return provider
    observed = validate_node_inputs(graph, native)
    return {'valid': provider.get('valid') is True and observed['valid'],
            'provider': provider, 'node_inputs': observed}
