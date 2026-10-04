"""Source-bound assembly scheduling, independent of placement and simulation.

Permanent sewing determines coupled groups; spatial layers determine their
order. No link is retyped and no placement, physics or fitting is qualified.
"""
import copy

from .core import StudioError, contract, digest
from .dressing import validate_layers, _reference


STAGES = ('place', 'correct', 'mount', 'close', 'consolidate', 'relax', 'drape', 'motion')
ROLES = {'front', 'back', 'side', 'sleeve', 'cuff', 'hood', 'yoke', 'belt', 'lining', 'reinforcement', 'collar', 'inner_front'}
LINKS = {'permanent', 'closure', 'detachable', 'free_contact', 'temporary_support'}


def _refuse(reason, message, identities=(), remedy=None):
    error = StudioError(message)
    error.reason_category = 'assembly_planning'
    error.diagnostic = {'reason': reason, 'identities': sorted(identities),
                        'remedy': remedy, 'qualification': 'NONE'}
    raise error


def plan_assembly(spec, capabilities=()):
    """Return a deterministic plan; capability names must describe tested paths.

    Supporting a coupled group requires explicit `coupled_multilayer` admission
    from the consumer. That flag does not itself qualify the native solver.
    """
    contract('garment-automation', spec)
    _reference(spec['source_ref'])
    _reference(spec['body_ref'])
    pieces = {}
    for piece in spec['pieces']:
        _reference(piece['source_ref'])
        if piece['id'] in pieces:
            _refuse('DUPLICATE_PIECE', 'Duplicate source piece identity', [piece['id']])
        if any(edge not in piece['edges'] for edge in piece.get('guide_edges',{}).values()):
            _refuse('UNKNOWN_GUIDE_EDGE','Semantic placement references a missing named source edge', [piece['id']],
                    'Correct the declared guide edge using the approved source contour')
        if piece.get('subrole')=='opening_strip' and piece['role']!='front':
            _refuse('INVALID_OPENING_ROLE','An opening strip must be a declared front panel',[piece['id']])
        pieces[piece['id']] = piece
    layers = spec['layers']
    collider_ids = [name for node in layers['nodes'] for name in node['colliders']]
    layer_report = validate_layers({'panels': pieces}, layers, collider_ids)
    if layer_report['status'] == 'NEEDS_CLARIFICATION':
        _refuse('LAYER_ORDER_INCOMPLETE', 'Garment layer order needs clarification',
                remedy='Declare the relative order of the reported incomparable layers')
    nodes = {node['id']: node for node in layers['nodes']}
    owners = {pid: node['id'] for node in layers['nodes'] for pid in node['panels']}
    for pid, piece in pieces.items():
        if piece['layer'] != owners[pid]:
            _refuse('PIECE_LAYER_MISMATCH', 'Semantic piece layer differs from the spatial graph', [pid])
    parent = {pid: pid for pid in pieces}

    def find(pid):
        while parent[pid] != pid:
            parent[pid] = parent[parent[pid]]
            pid = parent[pid]
        return pid

    def union(a, b):
        ra, rb = find(a), find(b)
        parent[max(ra, rb)] = min(ra, rb)

    links = {}
    permanent_owners = {}
    for link in spec['links']:
        sid = link['id']
        if sid in links:
            _refuse('DUPLICATE_LINK', 'Duplicate source link identity', [sid])
        _reference(link['source_ref'])
        for side in ('a', 'b'):
            pid, edge = link['piece_'+side], link['edge_'+side]
            if pid not in pieces or edge not in pieces[pid]['edges']:
                _refuse('LINK_SOURCE_MISSING', 'Link must identify an existing source piece and named edge', [sid, pid])
            if link['kind'] == 'permanent':
                key = (pid, edge)
                if key in permanent_owners:
                    _refuse('DUPLICATE_PERMANENT_EDGE', 'Two permanent links own the same named source edge',
                            [sid, permanent_owners[key], pid], 'Correct the source partners; retain valid detachable attachments')
                permanent_owners[key] = sid
        links[sid] = link
        if link['kind'] == 'permanent':
            union(link['piece_a'], link['piece_b'])
    # Independent panels in a spatial layer share its simulation group.
    # This avoids collisions between two simultaneously active Cloth objects.
    for node in layers['nodes']:
        for pid in node['panels'][1:]:
            union(node['panels'][0], pid)
    cohorts = {}
    for pid in sorted(pieces):
        cohorts.setdefault(find(pid), []).append(pid)
    group_for = {pid: 'group-'+digest(cohort)[:16] for cohort in cohorts.values() for pid in cohort}
    groups = {}
    for cohort in cohorts.values():
        gid = group_for[cohort[0]]
        touched = sorted({owners[pid] for pid in cohort})
        crossing = sorted(sid for sid, link in links.items()
                          if link['kind'] == 'permanent' and owners[link['piece_a']] != owners[link['piece_b']]
                          and link['piece_a'] in cohort)
        if len(touched) > 1 and 'coupled_multilayer' not in capabilities:
            _refuse('COUPLED_MULTILAYER_UNAVAILABLE', 'Permanent seams couple several spatial layers',
                    crossing, 'Qualify a joint simulation path; do not discard seams or simulate coupled layers independently')
        groups[gid] = {'id': gid, 'pieces': cohort, 'layers': touched,
                       'cross_layer_permanent_links': crossing, 'dependencies': [],
                       'body_colliders': [], 'inner_group_colliders': [],
                       'links': sorted(sid for sid, link in links.items()
                                       if link['piece_a'] in cohort or link['piece_b'] in cohort),
                       'budgets': copy.deepcopy(spec['budgets'])}
    for inner, outer in layers['inside_to_outside']:
        outside = {group_for[pid] for pid in nodes[outer]['panels']}
        inside = {group_for[pid] for pid in nodes[inner]['panels']}
        for gid in outside:
            groups[gid]['dependencies'].extend(inside-{gid})
    remaining = set(groups)
    order = []
    while remaining:
        ready = sorted(gid for gid in remaining if not (set(groups[gid]['dependencies']) & remaining))
        if not ready:
            _refuse('COUPLED_ORDER_CYCLE', 'Coupled sewing groups cannot be sequenced in the declared spatial order',
                    remaining, 'Use a qualified joint group for the intervening layers or revise the declared construction explicitly')
        order.extend(ready)
        remaining.difference_update(ready)
    for gid in order:
        group = groups[gid]
        dependencies = set(group['dependencies'])
        for dependency in list(dependencies):
            dependencies.update(groups[dependency]['inner_group_colliders'])
        group['dependencies'] = sorted(set(group['dependencies']))
        group['inner_group_colliders'] = sorted(dependencies)
        inward = set().union(*(set(layer_report['ancestors'][lid]) for lid in group['layers']))
        group['body_colliders'] = sorted({name for lid in inward if nodes[lid]['kind'] == 'body'
                                          for name in nodes[lid]['colliders']})
        group['stages'] = list(STAGES)
        group['interaction'] = 'one_way_frozen_inner_groups'
    # Normalize arrays that are sets, while preserving the explicit layer order.
    normalized = copy.deepcopy(spec)
    normalized['pieces'] = sorted(normalized['pieces'], key=lambda item: item['id'])
    for piece in normalized['pieces']:piece['edges'].sort()
    normalized['links'] = sorted(normalized['links'], key=lambda item: item['id'])
    normalized['layers']['nodes'] = sorted(normalized['layers']['nodes'], key=lambda item: item['id'])
    for node in normalized['layers']['nodes']:
        node['panels'].sort()
        node['colliders'].sort()
    normalized['layers']['inside_to_outside'].sort()
    plan = {'version': 1, 'status': 'PLANNED', 'qualification': 'NONE',
            'source_sha256': digest(normalized), 'source_ref': copy.deepcopy(spec['source_ref']),
            'body_ref': copy.deepcopy(spec['body_ref']), 'groups': [groups[gid] for gid in order],
            'piece_semantics': {piece['id']:copy.deepcopy(piece) for piece in normalized['pieces']},
            'link_graph': [copy.deepcopy(links[sid]) for sid in sorted(links)],
            'spatial_graph': copy.deepcopy(normalized['layers']),
            'source_mutated': False, 'simulation': 'NOT_EXECUTED',
            'physical_body_introduction': 'EXPLICIT_STAGE_REQUIRED'}
    plan['plan_sha256'] = digest(plan)
    return plan
