"""Source-bound dressing and layer contracts. No geometry or cut is changed.

These reports qualify input/geometry only, never Cloth or artistic fitting.
An absent historical dressing contract is explicitly NOT_ASSESSED.
"""
import copy
import math

from .core import StudioError, contract, digest, relative


def _error(message, category='dressing'):
    error = StudioError(message)
    error.reason_category = category
    raise error


def _reference(ref):
    if not isinstance(ref, dict) or set(ref) != {'path', 'sha256'}:
        _error('Dressing/layer data require an exact path and SHA-256 source reference')
    relative(ref['path'])
    value = ref['sha256']
    if not isinstance(value, str) or len(value) != 64 or any(c not in '0123456789abcdef' for c in value):
        _error('Invalid dressing/layer source SHA-256')


def _unique(items, name):
    ids = [item['id'] for item in items]
    if len(ids) != len(set(ids)):
        _error('Duplicate '+name+' IDs')
    return {item['id']: item for item in items}


def _finite(point):
    return len(point) == 3 and all(type(v) in (int, float) and math.isfinite(v) for v in point)


def migrate_legacy_layers(payload, collider_roles, source_ref):
    """Translate a demonstrated monocouche case; never infer garment order.

    collider_roles maps actual collider names to body/auxiliary_body/garment/
    unknown. Several body parts do not imply several clothing layers. More
    than one source package also does not establish an order.
    """
    _reference(source_ref)
    unknown = [name for name, role in collider_roles.items()
               if role not in ('body', 'auxiliary_body')]
    if unknown:
        return {'version': 1, 'status': 'NEEDS_CLARIFICATION', 'layers': None,
                'reason': 'LEGACY_LAYER_ORDER_UNKNOWN', 'colliders': sorted(unknown),
                'qualification': 'NONE', 'source_mutated': False}
    nodes = [{'id': 'garment', 'kind': 'garment', 'panels': sorted(payload['panels']),
              'colliders': [], 'source_ref': copy.deepcopy(source_ref)}]
    edges = []
    if collider_roles:
        nodes.insert(0, {'id': 'body', 'kind': 'body', 'panels': [],
                        'colliders': sorted(collider_roles), 'source_ref': copy.deepcopy(source_ref)})
        edges = [['body', 'garment']]
    layers = {'version': 1, 'source_ref': copy.deepcopy(source_ref), 'mode': 'single',
              'interaction': 'one_way_declared', 'nodes': nodes, 'inside_to_outside': edges}
    return {'version': 1, 'status': 'MIGRATED_EXPLICIT_SINGLE_LAYER', 'layers': layers,
            'qualification': 'NONE', 'source_mutated': False,
            'dressing': 'NOT_ASSESSED', 'physics_validation_transferred': False}


def validate_layers(payload, layers, collider_ids):
    _reference(layers['source_ref'])
    nodes = _unique(layers['nodes'], 'layer')
    owned_panels, owned_colliders = [], []
    for node in nodes.values():
        _reference(node['source_ref'])
        owned_panels += node['panels']
        owned_colliders += node['colliders']
        if not node['panels'] and not node['colliders']:
            _error('A layer node must identify actual panels or colliders: '+node['id'], 'layers')
        if node['kind'] == 'body' and node['panels']:
            _error('A body layer cannot own garment source panels', 'layers')
    if sorted(owned_panels) != sorted(payload['panels']):
        _error('Layers must partition the current source panels exactly once', 'layers')
    if sorted(owned_colliders) != sorted(collider_ids):
        _error('Layers must partition the actual collider identities exactly once', 'layers')
    edges = [tuple(edge) for edge in layers['inside_to_outside']]
    if len(set(edges)) != len(edges):
        _error('Duplicate layer order relation', 'layers')
    ancestors = {key: set() for key in nodes}
    for inner, outer in edges:
        if inner not in nodes or outer not in nodes or inner == outer:
            _error('Unknown or self-referential layer relation', 'layers')
        ancestors[outer].add(inner)
    for _ in nodes:
        for key in nodes:
            ancestors[key].update(set().union(*(ancestors[parent] for parent in list(ancestors[key]))))
    if any(key in parents for key, parents in ancestors.items()):
        _error('Layer order contains a cycle', 'layers')
    order = sorted(nodes, key=lambda key: (len(ancestors[key]), key))
    garments = [key for key, node in nodes.items() if node['kind'] == 'garment']
    unresolved = [[a, b] for i, a in enumerate(garments) for b in garments[i+1:]
                  if a not in ancestors[b] and b not in ancestors[a]]
    if layers['mode'] == 'single' and len(garments) != 1:
        _error('Explicit single-layer mode requires exactly one garment layer', 'layers')
    for body, node in nodes.items():
        if node['kind'] == 'body' and any(body not in ancestors[g] for g in garments):
            _error('Body colliders must precede every garment layer', 'layers')
    return {'version': 1, 'status': 'NEEDS_CLARIFICATION' if unresolved else 'LAYER_CONTRACT_VALIDATED',
            'reason': 'INCOMPARABLE_GARMENT_LAYERS' if unresolved else None,
            'unresolved_pairs': unresolved, 'topological_order': order,
            'ancestors': {key: sorted(value) for key, value in ancestors.items()},
            'interaction': layers['interaction'], 'qualification': 'NONE'}


def select_colliders(layers, layer_id):
    """Names of inward obstacle cages; not a mutation of a Blender collection."""
    nodes = {item['id']: item for item in layers['nodes']}
    if layer_id not in nodes:
        _error('Unknown layer requested for collider selection', 'layers')
    parents = {layer_id}
    for _ in nodes:
        parents.update(inner for inner, outer in layers['inside_to_outside'] if outer in parents)
    parents.discard(layer_id)
    return sorted({name for key in parents for name in nodes[key]['colliders']})


def layer_collision_selection(payload, plan, collider_roles=None):
    """Select one native Cloth obstacle collection; never merge active layers.

    Multiple current garment layers need separately sequenced simulations.
    External inner garments may contribute evaluated collider cages when
    their DAG order and sourced outward sides are explicit.
    """
    layers = plan.get('layers')
    if layers is None:
        return {'status': 'NEEDS_CLARIFICATION', 'reason': 'LAYER_ORDER_NOT_DECLARED',
                'colliders': [], 'qualification': 'NONE'}
    colliders = list(collider_roles) if collider_roles is not None else [
        name for node in layers['nodes'] for name in node['colliders']]
    validation = validate_layers(payload, layers, colliders)
    active = [node['id'] for node in layers['nodes'] if node['panels']]
    if validation['status'] == 'NEEDS_CLARIFICATION' or len(active) != 1:
        return {'status': 'NEEDS_CLARIFICATION',
                'reason': 'SEPARATE_PER_LAYER_NATIVE_SIMULATIONS_REQUIRED' if len(active) != 1 else validation['reason'],
                'active_layers': active, 'colliders': [], 'qualification': 'NONE'}
    return {'status': 'LAYER_COLLIDERS_SELECTED', 'active_layer': active[0],
            'colliders': select_colliders(layers, active[0]),
            'interaction': 'one_way_declared', 'qualification': 'NONE'}


def validate_dressing(payload, plan, collider_ids=()):
    """Structural validation; the native audit measures the actual geometry."""
    contract('pattern-assembly', plan)
    from .pattern_assembly import map_digest
    expected_mapping = (payload.get('source_mapping_sha256') if payload.get('rest_mode') == 'assembled_3d'
                        else map_digest(payload))
    if plan['component_id'] != payload['component_id'] or plan['mapping_sha256'] != expected_mapping:
        _error('Dressing source mapping is stale or belongs to another component', 'geometry_safety')
    result = {'version': 1, 'status': 'NOT_ASSESSED', 'qualification': 'NONE',
              'contract_sha256': digest({key: plan.get(key) for key in ('dressing', 'layers')}),
              'layers': None, 'required': bool(plan.get('dressing', {}).get('required')),
              'full_coverage': False}
    if 'layers' in plan:
        result['layers'] = validate_layers(payload, plan['layers'], collider_ids)
    dressing = plan.get('dressing')
    if dressing is None:
        if result['layers'] and result['layers']['status'] == 'NEEDS_CLARIFICATION':
            result['status'] = 'NEEDS_CLARIFICATION'
        return result
    _reference(dressing['source_ref'])
    regions = _unique(dressing['regions'], 'region')
    openings = _unique(dressing['openings'], 'opening')
    for region in regions.values():
        _reference(region['source_ref'])
        if region['collider'] not in collider_ids:
            _error('Dressing region names an unavailable collider: '+region['id'])
        if not all(_finite(region[key]) for key in ('axis_start_cm', 'axis_end_cm')) or math.dist(
                region['axis_start_cm'], region['axis_end_cm']) <= 1e-8:
            _error('Dressing region requires a finite nonzero sourced axis: '+region['id'])
        ts = region['section_parameters']
        if ts != sorted(set(ts)):
            _error('Dressing section parameters must be unique and increasing: '+region['id'])
    assignments = dressing['assignments']
    pieces = [assignment['piece'] for assignment in assignments]
    if len(pieces) != len(set(pieces)) or not set(pieces) <= set(payload['panels']):
        _error('Dressing assignments require unique current panel IDs')
    if dressing['required'] and set(pieces) != set(payload['panels']):
        _error('Required dressing must assign every current panel to a sourced region')
    for assignment in assignments:
        if assignment['region'] not in regions:
            _error('Dressing assignment names an unknown body region')
    uncovered_regions = ({assignment['region'] for assignment in assignments}
                         - {opening['region'] for opening in openings.values()})
    for opening in openings.values():
        _reference(opening['source_ref'])
        if opening['region'] not in regions:
            _error('Opening names an unknown dressing region')
        if opening['section_parameter'] not in regions[opening['region']]['section_parameters']:
            _error('Opening must select an explicitly measured body section')
        for edge in opening['edges']:
            if edge['piece'] not in payload['panels'] or edge['edge'] not in payload['panels'][edge['piece']]['edges']:
                _error('Opening must use current source panel and named-edge IDs')
        if len({(edge['piece'], edge['edge']) for edge in opening['edges']}) != len(opening['edges']):
            _error('An opening cannot repeat its source edge')
    if sorted(dressing['mount_order']) != sorted(openings):
        _error('Mount order must list every declared opening exactly once')
    milestones = _unique(dressing['milestones'], 'dressing milestone')
    for milestone in milestones.values():
        _reference(milestone['source_ref'])
        if set(milestone['translations_cm']) - set(payload['panels']):
            _error('Dressing milestone references an unknown panel')
        if any(not _finite(vector) or math.dist(vector, (0, 0, 0)) > plan['assembly']['max_displacement_cm']
               for vector in milestone['translations_cm'].values()):
            _error('Dressing milestone exceeds the existing assembly displacement budget')
    missing = []
    if dressing['required'] and uncovered_regions:
        missing.append('ASSIGNED_REGION_PASSAGE_MISSING')
    if dressing['required'] and (not regions or not openings):
        missing.append('REQUIRED_BODY_PASSAGE_DATA_MISSING')
    if 'layers' not in plan:
        missing.append('LAYER_ORDER_NOT_DECLARED')
    elif result['layers']['status'] == 'NEEDS_CLARIFICATION':
        missing.append('LAYER_ORDER_INCOMPLETE')
    result.update(status='NEEDS_CLARIFICATION' if missing else 'DRESSING_CONTRACT_VALIDATED',
                  missing=missing, region_ids=list(regions), opening_ids=list(openings),
                  assigned_panels=sorted(pieces), unassigned_panels=sorted(set(payload['panels'])-set(pieces)),
                  regions_without_passage=sorted(uncovered_regions),
                  full_coverage=bool(dressing['required'] and not missing and regions and openings
                                     and set(pieces) == set(payload['panels'])))
    return result


def source_references(plan):
    """All exact refs needed by the native reader; no source validation by flag."""
    found = {}
    def visit(value):
        if isinstance(value, dict):
            if set(value) == {'path', 'sha256'}:
                _reference(value)
                if value['path'] in found and found[value['path']]['sha256'] != value['sha256']:
                    _error('Conflicting source hashes in dressing contract')
                found[value['path']] = value
            else:
                for child in value.values():
                    visit(child)
        elif isinstance(value, list):
            for child in value:
                visit(child)
    visit({key: plan.get(key) for key in ('dressing', 'layers')})
    return [copy.deepcopy(found[key]) for key in sorted(found)]
