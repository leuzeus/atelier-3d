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

    Independent current garment groups need separately sequenced simulations.
    An explicitly bound permanent cohort can use one joint native Cloth object.
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
    execution = plan.get('layer_execution')
    if validation['status'] != 'NEEDS_CLARIFICATION' and len(active) > 1 and execution:
        _reference(execution['source_ref'])
        from .pattern_assembly import map_digest
        mapping = payload.get('source_mapping_sha256') if payload.get('rest_mode') == 'assembled_3d' else map_digest(payload)
        graph = sewing_graph_digest(payload)
        if execution.get('mode') != 'joint_coupled_single_object' or execution.get('version') != 1:
            _error('Unsupported native layer execution mode', 'layers')
        if execution.get('source_mapping_sha256') != mapping or execution.get('sewing_graph_sha256') != graph:
            _error('Joint layer execution is stale for the source mapping or sewing graph', 'geometry_safety')
        parents = {pid: pid for pid in payload['panels']}
        def find(pid):
            while parents[pid] != pid:
                parents[pid] = parents[parents[pid]]; pid = parents[pid]
            return pid
        def union(a, b):
            a, b = find(a), find(b); parents[max(a, b)] = min(a, b)
        for node in layers['nodes']:
            for pid in node['panels'][1:]: union(node['panels'][0], pid)
            if node['panels'] and node['colliders']:
                _error('Joint active panels cannot also be declared frozen collider objects', 'layers')
        for sid, seam in payload['seams'].items():
            a, b = seam.get('piece_a'), seam.get('piece_b')
            if a not in parents or b not in parents:
                _error('Joint native group needs source identities on every sewing link: '+sid, 'layers')
            if seam['kind'] == 'permanent': union(a, b)
        if len({find(pid) for pid in parents}) != 1:
            return {'status': 'NEEDS_CLARIFICATION', 'reason': 'SEPARATE_UNCOUPLED_GROUPS_REQUIRED',
                    'active_layers': active, 'colliders': [], 'qualification': 'NONE'}
        return {'status': 'LAYER_COLLIDERS_SELECTED', 'active_layers': sorted(active),
                'colliders': sorted(set().union(*(set(select_colliders(layers, lid)) for lid in active))),
                'execution': 'joint_coupled_single_object', 'sewing_graph_sha256': graph,
                'interaction': 'joint_self_collision_and_one_way_external', 'qualification': 'NONE'}
    if validation['status'] == 'NEEDS_CLARIFICATION' or len(active) != 1:
        return {'status': 'NEEDS_CLARIFICATION',
                'reason': 'SEPARATE_PER_LAYER_NATIVE_SIMULATIONS_REQUIRED' if len(active) != 1 else validation['reason'],
                'active_layers': active, 'colliders': [], 'qualification': 'NONE'}
    return {'status': 'LAYER_COLLIDERS_SELECTED', 'active_layer': active[0],
            'colliders': select_colliders(layers, active[0]),
            'interaction': 'one_way_declared', 'qualification': 'NONE'}


def sewing_graph_digest(payload):
    """Link types and source owners remain bound across geometric consolidation."""
    return digest({sid: {key: seam.get(key) for key in ('piece_a', 'piece_b', 'kind')}
                   for sid, seam in sorted(payload['seams'].items())})


def rebind_layer_execution(plan, payload):
    """Rebind a regular derived map only when the source link graph is unchanged."""
    result = copy.deepcopy(plan)
    execution = result.get('layer_execution')
    if execution:
        if execution['sewing_graph_sha256'] != sewing_graph_digest(payload):
            _error('Regular preparation changed the declared source sewing graph; review a new plan', 'layers')
        from .pattern_assembly import map_digest
        execution['source_mapping_sha256'] = map_digest(payload)
    return result


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


def _dressing_bindings(project, bindings):
    from .core import inside, sha
    result = {}
    for key, ref in bindings.items():
        _reference(ref)
        path = inside(project.root, ref['path'])
        if not path.is_file() or sha(path) != ref['sha256']:
            _error('Dressing binding is stale: '+key, 'geometry_safety')
        result[key] = copy.deepcopy(ref)
    return result


def _dressing_code_sources():
    from .core import ROOT, sha
    files = ['a3d/dressing.py', 'a3d/pattern_assembly.py', 'blender/dressing.py',
             'blender/cloth_contacts.py', 'blender/sewing.py', 'schemas/dressing-plan.schema.json']
    return {path: sha(ROOT/path) for path in files}


def compile_dressing_plan(project, payload, assembly_plan, specification_path, output_dir):
    """Compile sourced openings, paths and release times without fitting by AI.

    Existing panel cuts, opening assignments and layer order remain immutable.
    A missing opening or trajectory is a clarification, never a guessed passage.
    The resulting run asks the native evaluator to measure geometric clearance;
    it performs no Cloth and schedules no accepted support removal by itself.
    """
    from .core import atomic_json, ident, inside, read_json, sha
    from .pattern_assembly import map_digest
    state = project.state()
    if state.get('pending_blender_operation') or state['stage'] == 'COMPLETE':
        _error('Pending or completed project prevents dressing preparation')
    spec = contract('dressing-plan', read_json(inside(project.root, specification_path)))
    ident(spec['id']); ident(spec['component_id'])
    if spec['component_id'] != payload['component_id'] or spec['component_id'] not in state['components']:
        _error('Dressing target does not identify this source garment', 'geometry_safety')
    bindings = _dressing_bindings(project, spec['bindings'])
    if read_json(inside(project.root, bindings['candidate']['path'])) != payload:
        _error('Dressing candidate record differs from the prepared source map', 'geometry_safety')
    if read_json(inside(project.root, bindings['assembly']['path'])) != assembly_plan:
        _error('Dressing assembly record differs from the current reviewed plan', 'geometry_safety')
    recipe = contract('sewing-recipe', read_json(inside(project.root, bindings['recipe']['path'])))
    if recipe['component_id'] != spec['component_id']:
        _error('Dressing recipe identifies another garment', 'geometry_safety')
    collider_ids = [item['object'] for item in recipe['colliders']]
    structural = validate_dressing(payload, assembly_plan, collider_ids)
    if structural['status'] != 'DRESSING_CONTRACT_VALIDATED' or not structural['full_coverage']:
        _error('Dressing needs a complete sourced opening, region and layer contract')
    for ref in source_references(assembly_plan):
        _dressing_bindings(project, {'assembly_source': ref})
    declared = assembly_plan['dressing']['mount_order']
    if [path['opening_id'] for path in spec['paths']] != declared:
        _error('Dressing paths must preserve every approved opening and its mount order exactly')
    waypoint_order = []; milestones = []
    for path in spec['paths']:
        for point in path['waypoints']:
            ident(point['id']); _dressing_bindings(project, {'waypoint': point['source_ref']})
            if point['id'] in waypoint_order or point['id']=='prepared':
                _error('Dressing waypoint IDs must be globally unique')
            if not point['translations_cm'] or set(point['translations_cm']) - set(payload['panels']):
                _error('Dressing waypoint must identify actual source panels')
            if any(not _finite(value) or math.dist(value, (0,0,0)) > assembly_plan['assembly']['max_displacement_cm']
                   for value in point['translations_cm'].values()):
                _error('Dressing waypoint exceeds the approved displacement budget', 'geometry_safety')
            waypoint_order.append(point['id']); milestones.append(copy.deepcopy(point))
    temporary = {item['id']: item for item in assembly_plan['supports']['temporary']}
    released = [item['support_id'] for item in spec['support_release']]
    if sorted(released) != sorted(temporary) or len(released) != len(set(released)):
        _error('Dressing must schedule each temporary support exactly once and preserve functional supports')
    for item in spec['support_release']:
        _dressing_bindings(project, {'support_release': item['source_ref']})
        if item['after_waypoint'] not in waypoint_order:
            _error('Temporary support release must follow a declared source waypoint')
        if item['release_frames'] > max(profile['frames'] for profile in recipe['phases'].values()):
            _error('Temporary support release exceeds the source physical frame budget')
    derived = copy.deepcopy(assembly_plan)
    derived['dressing']['milestones'] = milestones
    validate_dressing(payload, derived, collider_ids)
    output = inside(project.root, output_dir, False)
    if output.exists(): _error('Dressing output must be a new project directory')
    document = {'version':1, 'id':spec['id'], 'component_id':spec['component_id'],
        'specification':{'path':specification_path,'sha256':sha(inside(project.root,specification_path))},
        'bindings':bindings, 'source_mapping_sha256':map_digest(payload), 'assembly':derived,
        'source_assembly_sha256':digest(assembly_plan), 'paths':copy.deepcopy(spec['paths']),
        'support_release':copy.deepcopy(spec['support_release']), 'execution':copy.deepcopy(spec['execution']),
        'waypoint_order':waypoint_order, 'code_sources':_dressing_code_sources(),
        'qualification':'NOT_EXECUTED', 'accepted':False, 'source_patterns_changed':False,
        'support_removal':'SCHEDULED_NOT_EXECUTED'}
    document['fingerprint'] = digest(document)
    output.mkdir(parents=True); path = output/'dressing.json'; atomic_json(path, document)
    ref = {'path':path.relative_to(project.root).as_posix(), 'sha256':sha(path)}
    run = {'version':1, 'id':spec['id'], 'asset_id':state['asset']['id'], 'kind':'garment',
        'inputs':list(bindings.values())+[ref], 'budgets':{'max_attempts':1,'max_seconds':spec['execution']['max_seconds']},
        'units':[{'id':'dressing.clearance', 'dependencies':[], 'executor':'blender',
            'operation':'inspect_dressing_plan', 'arguments':{'component_id':spec['component_id'],
                'recipe_path':bindings['recipe']['path'], 'dressing_path':ref['path']},
            'inputs':list(bindings.values())+[ref], 'code_paths':list(document['code_sources']), 'success_statuses':['READY']}]}
    contract('run',run); run_path=output/'run.json'; atomic_json(run_path,run)
    return {'status':'PREPARED','dressing':ref,
        'run_specification':{'path':run_path.relative_to(project.root).as_posix(),'sha256':sha(run_path)},
        'executed':False,'qualification':'NOT_EXECUTED','accepted':False,'support_removal':'SCHEDULED_NOT_EXECUTED'}


def support_schedule_at(document, waypoint_id):
    """Return coded release intent; do not claim native pin changes occurred."""
    if waypoint_id not in document['waypoint_order']:
        _error('Unknown dressing source waypoint')
    completed = set(document['waypoint_order'][:document['waypoint_order'].index(waypoint_id)+1])
    released = [item for item in document['support_release'] if item['after_waypoint'] in completed]
    return {'release':copy.deepcopy(released),
            'retain_functional':copy.deepcopy(document['assembly']['supports']['functional']),
            'executed':False,'qualification':'NOT_EXECUTED'}


def _compiled_dressing(project, dressing_path):
    from .core import inside, read_json, sha
    doc = read_json(inside(project.root,dressing_path)); bound=dict(doc); fingerprint=bound.pop('fingerprint',None)
    if digest(bound)!=fingerprint or doc['code_sources']!=_dressing_code_sources():
        _error('Compiled dressing plan or its evaluator changed', 'geometry_safety')
    _dressing_bindings(project,doc['bindings'])
    if sha(inside(project.root,doc['specification']['path']))!=doc['specification']['sha256']:
        _error('Dressing specification changed', 'geometry_safety')
    spec=contract('dressing-plan',read_json(inside(project.root,doc['specification']['path'])))
    from .pattern_assembly import map_digest
    candidate=read_json(inside(project.root,doc['bindings']['candidate']['path']))
    source=read_json(inside(project.root,doc['bindings']['assembly']['path']))
    derived=copy.deepcopy(source)
    derived['dressing']['milestones']=[copy.deepcopy(point) for path in spec['paths'] for point in path['waypoints']]
    if (doc['bindings']!=spec['bindings'] or doc['assembly']!=derived or doc['source_assembly_sha256']!=digest(source)
            or doc['component_id']!=spec['component_id'] or doc['id']!=spec['id'] or doc['source_mapping_sha256']!=map_digest(candidate)
            or doc['paths']!=spec['paths'] or doc['support_release']!=spec['support_release'] or doc['execution']!=spec['execution']
            or doc['waypoint_order']!=[point['id'] for path in spec['paths'] for point in path['waypoints']]):
        _error('Compiled dressing changed the approved source paths or assembly contract', 'geometry_safety')
    return doc


def inspect_dressing_plan(project_root, component_id, recipe_path, dressing_path):
    """Native read-only audit of actual openings, contacts and declared paths.

    Discrete geometric motion samples use one fixed evaluated body pose. They
    are neither continuous contact proof nor execution of physical dressing.
    """
    import time
    import uuid
    from .core import atomic_json, inside, sha
    from .store import Project
    from blender.sewing import managed_inputs, structural_inputs, context_colliders, object_mesh
    from blender.dressing import audit_dressing
    from blender.cloth_contacts import build_contact_context, check_contacts, check_motion
    project=Project(project_root); document=_compiled_dressing(project,dressing_path)
    if component_id!=document['component_id'] or recipe_path!=document['bindings']['recipe']['path']:
        _error('Native dressing audit differs from its compiled source target', 'geometry_safety')
    obj,payload,recipe=managed_inputs(project,component_id,recipe_path,check_placement=False)
    from .pattern_assembly import map_digest
    if map_digest(payload)!=document['source_mapping_sha256']:
        _error('Native dressing source map changed', 'geometry_safety')
    structural_inputs(obj,payload,recipe)
    evaluated,faces=object_mesh(obj,True)
    coords=[[float(value)*100 for value in point] for point in evaluated]
    if faces!=payload['faces'] or len(coords)!=len(payload['rest_cm']) or any(not _finite(point) for point in coords):
        _error('Native evaluated dressing mesh changed topology or has nonfinite geometry', 'geometry_safety')
    colliders,_,snapshots=context_colliders(recipe)
    plan=document['assembly']; execution=document['execution']; started=time.monotonic()
    context=build_contact_context(payload,colliders,clearance_cm=plan['collision']['clearance_cm'],
        self_clearance_cm=recipe['phases']['drape']['self_distance_cm'] if recipe['phases']['drape']['self_collision'] else 0.,
        seam_tolerance_cm=recipe['limits']['weld_gap_cm'],max_penetration_cm=recipe['limits']['max_penetration_cm'])
    order=document['waypoint_order']+['prepared']
    def expired(): return time.monotonic()-started>=execution['max_seconds']
    def contact(points):
        if expired(): return {'ok':False,'reason':'DRESSING_TIME_BUDGET'}
        return check_contacts(context,points,frame=0)
    def motion(previous,current,previous_id,current_id):
        if expired(): return {'ok':False,'reason':'DRESSING_TIME_BUDGET'}
        return check_motion(context,previous,current,order.index(previous_id),order.index(current_id),
            max_step_cm=execution['max_step_cm'],max_subdivisions=execution['max_subdivisions'])
    report=audit_dressing(payload,coords,plan,colliders=colliders,project=project.root,
        contact_check=contact,motion_check=motion,source_coords_cm=payload['placed_cm'])
    if expired() or any(item.get('reason') in ('DRESSING_TIME_BUDGET','CONTACT_MOTION_UNDERSAMPLED',
        'CONTACT_PAIR_BUDGET','SWEPT_RAY_BUDGET') for item in report.get('motion',[])):
        report.update(status='INCOMPLETE',reason='DRESSING_EVALUATION_BUDGET')
    report.update(bindings=copy.deepcopy(document['bindings']),compiled_plan_sha256=sha(inside(project.root,dressing_path)),
        actual_collider_snapshots=snapshots,actual_coordinates_sha256=digest(coords),
        actual_geometry='EVALUATED_NATIVE_CAGE_WORLD_CENTIMETRES',
        support_release=copy.deepcopy(document['support_release']),support_removal='SCHEDULED_NOT_EXECUTED',
        physical_simulation='NOT_EXECUTED',fitting='NOT_EXECUTED',accepted=False,qualification='GEOMETRY_ONLY',
        elapsed_seconds=time.monotonic()-started,
        trajectory_scope='DECLARED_DISCRETE_PLACEMENT_SEQUENCE_ON_FIXED_EVALUATED_BODY_POSE')
    path=project.data/'blender/dressing'/('audit-'+uuid.uuid4().hex+'.json'); atomic_json(path,report)
    return {'status':report['status'],'report':{'path':path.relative_to(project.root).as_posix(),'sha256':sha(path)},
        'qualification':'GEOMETRY_ONLY','accepted':False,'support_removal':'SCHEDULED_NOT_EXECUTED',
        'physical_simulation':'NOT_EXECUTED','fitting':'NOT_EXECUTED'}
