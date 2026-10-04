"""Source-bound dressing topology and measured regions. No guessed opening or physique.

The source boundary graph identifies only declared permanent endpoints. It is
not native welding, passage admission, a fitted body or an executed trajectory.
"""
import copy
import json
import math
import zipfile
from collections import Counter, defaultdict

from .core import StudioError, contract, digest, inside, read_json, sha
from .dressing import _reference
from .garment_guides import _profile


def _point(point):
    return isinstance(point, list) and len(point) == 3 and all(type(v) in (int, float) and math.isfinite(v) for v in point)


def world_point(profile, local):
    if not _point(local):
        raise StudioError('Dressing derivation requires a finite measured body point')
    basis = profile['frame']
    return [basis['origin_cm'][i]+sum(local[j]*basis[key][i]
            for j, key in enumerate(('right', 'forward', 'up'))) for i in range(3)]


def source_boundary_graph(data, max_edges=10000):
    """Mesh boundary atoms, including aliases, after permanent endpoint equivalence.

Aliases of a free border are kept on one physical segment. Closure/detachable
partners remain separate. No union by proximity or coincident coordinates.
"""
    contract('garment', data); original = digest(data)
    if type(max_edges) is not int or max_edges < 1:
        raise StudioError('Dressing boundary budget must be a positive integer')
    parent = {}; consumed = set(); aliases = defaultdict(set); all_boundary = {}
    def find(node):
        parent.setdefault(node, node)
        if parent[node] != node:
            parent[node] = find(parent[node])
        return parent[node]
    def union(a, b):
        a, b = find(a), find(b)
        parent[max(a, b)] = min(a, b)
    for pid, piece in sorted(data['pieces'].items()):
        vertices = piece['vertices']; edges = Counter()
        if any(not isinstance(point,list) or len(point)!=2 or any(type(v) not in (int,float) or not math.isfinite(v) for v in point) for point in vertices):
            raise StudioError('Dressing source contains nonfinite panel vertices')
        for face in piece['faces']:
            if len(face)!=len(set(face)) or any(type(i) is not int or not 0<=i<len(vertices) for i in face):
                raise StudioError('Dressing source face has invalid original indices')
            for a, b in zip(face, face[1:]+face[:1]):
                edges[tuple(sorted((a, b)))] += 1
        if any(count > 2 for count in edges.values()):
            raise StudioError('Dressing source boundary is nonmanifold')
        for edge, count in edges.items():
            if count == 1:
                all_boundary[(pid, *edge)] = edge
        for name, chain in piece['edges'].items():
            if len(chain) < 2 or any(type(i) is not int or not 0 <= i < len(vertices) for i in chain):
                raise StudioError('Dressing named source edge has invalid original vertex indices')
            for a, b in zip(chain, chain[1:]):
                key = (pid, *sorted((a, b)))
                if key not in all_boundary:
                    raise StudioError('Dressing named source edge is not an actual mesh boundary segment')
                aliases[key].add(name)
    if len(all_boundary) > max_edges:
        return {'status': 'INCOMPLETE', 'reason': 'SOURCE_BOUNDARY_EDGE_BUDGET', 'components': [], 'source_sha256': original}
    bridges = []
    for seam in sorted(data['seams'], key=lambda row: row['id']):
        if seam.get('kind','permanent') != 'permanent':
            continue
        chains = []
        for side in ('a', 'b'):
            pid, edge = seam['piece_'+side], seam['edge_'+side]
            chain = data['pieces'][pid]['edges'][edge]; chains.append(chain)
            for a, b in zip(chain, chain[1:]):
                key = (pid, *sorted((a, b)))
                if key in consumed:
                    raise StudioError('Two permanent links consume the same source boundary segment')
                consumed.add(key)
        a, b = chains
        if seam['orientation'] == 'reverse':
            b = list(reversed(b))
        pairs = [((seam['piece_a'], a[0]), (seam['piece_b'], b[0])),
                 ((seam['piece_a'], a[-1]), (seam['piece_b'], b[-1]))]
        for left, right in pairs:
            union(left, right)
        bridges.append({'source_link_id': seam['id'], 'kind': 'PERMANENT_ENDPOINT_EQUIVALENCE_ONLY',
                        'source_vertex_pairs': [[list(a), list(b)] for a, b in pairs]})
    atoms = []
    for key in sorted(set(all_boundary)-consumed):
        pid, a, b = key
        atoms.append({'piece': pid, 'vertices': [a, b], 'named_edges': sorted(aliases[key]),
                      'nodes': [find((pid, a)), find((pid, b))]})
    adjacency = defaultdict(list)
    for index, atom in enumerate(atoms):
        for node in atom['nodes']:
            adjacency[node].append(index)
    unseen = set(range(len(atoms))); components = []
    while unseen:
        first = min(unseen); todo = [first]; selected = set()
        while todo:
            index = todo.pop()
            if index in selected:
                continue
            selected.add(index); unseen.discard(index)
            for node in atoms[index]['nodes']:
                todo.extend(i for i in adjacency[node] if i not in selected)
        nodes = {node for index in selected for node in atoms[index]['nodes']}
        closed = bool(selected) and all(len(adjacency[node]) == 2 for node in nodes)
        ordered = []; oriented = []; current = atoms[first]['nodes'][0]; previous = None
        remaining = set(selected)
        if closed:
            while remaining:
                candidates = [i for i in adjacency[current] if i in remaining]
                index = min(candidates); atom = atoms[index]; left, right = atom['nodes']
                reverse = current != left
                ordered.append(index); oriented.append(dict(atom, reverse=reverse))
                remaining.remove(index); previous = current; current = left if reverse else right
        else:
            ordered = sorted(selected); oriented = [dict(atoms[i], reverse=False) for i in ordered]
        source_edges = sorted({(atoms[i]['piece'], name) for i in selected for name in atoms[i]['named_edges']})
        row = {'id': data['component_id']+'.boundary.'+str(len(components)), 'closed_graph': closed,
               'status': 'CLOSED_SOURCE_GRAPH_ONLY' if closed else 'OPEN_OR_BRANCHING_SOURCE_GRAPH',
               'pieces': sorted({atoms[i]['piece'] for i in selected}),
               'source_edges': [{'piece': pid, 'edge': edge} for pid, edge in source_edges],
               'atoms': [{k: ([list(node) for node in v] if k == 'nodes' else v) for k, v in atom.items()} for atom in oriented],
               'node_degrees': sorted(len(adjacency[node]) for node in nodes),
               'passage': 'NOT_ASSESSED', 'native_consolidation': 'NOT_EXECUTED'}
        components.append(row)
    if digest(data) != original:
        raise StudioError('Dressing boundary derivation mutated source data')
    return {'status': 'SOURCE_BOUNDARY_DERIVED', 'source_sha256': original, 'components': components,
            'permanent_bridges': bridges, 'source_boundary_atoms': len(all_boundary),
            'permanent_atoms_consumed': len(consumed), 'qualification': 'SOURCE_TOPOLOGY_ONLY',
            'closure_links_preserved': [copy.deepcopy(row) for row in data['seams'] if row.get('kind','permanent') != 'permanent'],
            'source_mutated': False, 'native_consolidation': 'NOT_EXECUTED'}


def _triangles(profile, geometry, triangles):
    _profile(profile)
    points, faces = geometry['vertices_cm'], geometry['faces']
    if (digest([points, faces]) != profile['geometry_sha256'] or
            any(geometry.get(key) != profile.get(key) for key in ('source_sha256', 'pose_sha256')) or
            any(not _point(point) for point in points)):
        raise StudioError('Dressing body geometry/pose differs from its exact measured profile')
    from .shoulder_surface import surface_anchors, measured_surface_shoulders
    if 'surface_landmarks_source' not in profile:
        raise StudioError('Dressing requires source-bound measured shoulder skin and native triangulation')
    surface_anchors(profile)
    if digest(triangles) != profile['surface_landmarks_source']['triangles_sha256']:
        raise StudioError('Dressing requires the exact native triangulation used by body measurements')
    base = copy.deepcopy(profile); source = base.pop('surface_landmarks_source'); base['cache_key'] = source['previous_cache_key']
    for name in ('shoulder.surface.left', 'shoulder.surface.right'):
        del base['landmarks'][name]
    measured = measured_surface_shoulders(base, geometry, triangles)
    if measured != profile:
        raise StudioError('Dressing anatomical profile differs from remeasured source frame/triangulation')
    return {'vertices_cm': points, 'faces': triangles}


def _region(profile, collider, region_id, start, end, fractions, domain):
    from blender.dressing import section_segments
    if math.dist(start, end) <= 1e-8:
        raise StudioError('Dressing measured region axis is collapsed')
    axis = [b-a for a, b in zip(start, end)]; sections = []
    for fraction in fractions:
        center = [a+fraction*b for a, b in zip(start, axis)]
        report = section_segments(collider, center, axis)
        sections.append({'parameter': fraction, 'center_cm': center, **report})
    return {'id': region_id, 'axis_start_cm': start, 'axis_end_cm': end,
            'domain': domain, 'geometry_sha256': profile['geometry_sha256'], 'pose_sha256': profile['pose_sha256'],
            'profile_sha256': digest(profile), 'sections': sections,
            'status': 'MEASURED_SECTIONS' if all(row['ok'] for row in sections) else 'NEEDS_DATA',
            'full_hand_passage': 'NOT_QUALIFIED' if domain == 'WRIST_TO_ELBOW_ONLY' else 'NOT_APPLICABLE',
            'qualification': 'MEASURED_BODY_SECTIONS_ONLY'}


def mount_orders(methods, layers, max_orders=8, selected=None):
    """Enumerate a bounded DAG, without converting a tie to a human choice."""
    if type(max_orders) is not int or max_orders<1:
        raise StudioError('Dressing candidate order budget must be a positive integer')
    nodes = {row['id']: row for row in methods}; relation = set(map(tuple, layers['inside_to_outside']))
    if len(nodes)!=len(methods):
        raise StudioError('Dressing method identities must be unique')
    while True:
        closure = relation | {(a, d) for a, b in relation for c, d in relation if b == c}
        if closure == relation:
            break
        relation = closure
    dependencies = {key: set() for key in nodes}
    for a, left in nodes.items():
        for b, right in nodes.items():
            if a != b and any((x, y) in relation for x in left['layers'] for y in right['layers']):
                dependencies[b].add(a)
    if selected is not None:
        if len(selected) != len(nodes) or set(selected) != set(nodes):
            raise StudioError('Dressing selected mount order must cover every derived method exactly once')
        seen = set()
        for node in selected:
            if not dependencies[node] <= seen:
                raise StudioError('Dressing selected mount order contradicts the approved layer DAG')
            seen.add(node)
        orders = [list(selected)]; incomplete = False
    else:
        orders = []
        def visit(order):
            if len(orders) > max_orders:
                return
            if len(order) == len(nodes):
                orders.append(order); return
            seen = set(order)
            for node in sorted(set(nodes)-seen):
                if dependencies[node] <= seen:
                    visit([*order, node])
        visit([]); incomplete = len(orders) > max_orders
    if not orders and nodes:
        raise StudioError('Dressing method DAG is cyclic')
    return {'dependencies': {key: sorted(value) for key, value in sorted(dependencies.items())},
            'candidate_orders': orders[:max_orders], 'status': 'INCOMPLETE' if incomplete else
            ('AMBIGUOUS_ORDER' if len(orders) > 1 else 'ORDER_DERIVED'),
            'reason': 'MOUNT_ORDER_ENUMERATION_BUDGET' if incomplete else
            ('MULTIPLE_SOURCE_COMPATIBLE_METHOD_ORDERS' if len(orders) > 1 else None),
            'selected_order': orders[0] if len(orders) == 1 and not incomplete else None,
            'physics': 'NOT_EXECUTED'}


def hood_yoke_units(data, semantics, graph):
    """Partition only permanent source links; never close a detachable opening."""
    roles={pid:semantics[pid]['role'] for pid in data['pieces']}
    special={pid for pid,role in roles.items() if role in ('hood','yoke')}
    if not special:return [],[]
    if len({link['id'] for link in data['seams']})!=len(data['seams']):
        raise StudioError('Dressing hood/yoke source relation identities must be unique')
    adjacency={pid:set() for pid in data['pieces']}
    for link in data['seams']:
        if link.get('kind','permanent')=='permanent':
            adjacency[link['piece_a']].add(link['piece_b']);adjacency[link['piece_b']].add(link['piece_a'])
    units=[];unseen=set(special);issues=[]
    free_atoms={(atom['piece'],tuple(sorted(atom['vertices']))) for row in graph['components'] for atom in row['atoms']}
    def free_edge(pid,name):
        chain=data['pieces'][pid]['edges'].get(name)
        return bool(chain and all((pid,tuple(sorted((a,b)))) in free_atoms for a,b in zip(chain,chain[1:])))
    while unseen:
        todo=[min(unseen)];unit=set()
        while todo:
            pid=todo.pop()
            if pid not in unit:unit.add(pid);todo.extend(adjacency[pid]-unit)
        unseen-=unit;hoods=sorted(pid for pid in unit if roles[pid]=='hood');yokes=sorted(pid for pid in unit if roles[pid]=='yoke')
        def issue(category,reason):
            issues.append({'category':category,'reason':reason,'component_id':data['component_id'],'pieces':sorted(unit)})
        if not unit<=special or len(yokes)!=1 or (hoods and (len(hoods)!=2 or {semantics[pid]['side'] for pid in hoods}!={'left','right'})):
            issue('AMBIGUOUS_DECISION','HOOD_YOKE_PERMANENT_SOURCE_UNIT_AMBIGUOUS');continue
        yoke=yokes[0]
        front=[link for link in data['seams'] if link.get('kind')=='closure' and link['piece_a']==link['piece_b']==yoke]
        if len(front)!=1:
            issue('MISSING_DATA' if not front else 'AMBIGUOUS_DECISION','YOKE_EXPLICIT_FRONT_CLOSURE_REQUIRED');continue
        closure=front[0];rims=[{'piece':yoke,'edge':closure['edge_'+side]} for side in ('a','b')]
        if any(not free_edge(row['piece'],row['edge']) for row in rims):
            raise StudioError('Dressing yoke front closure consumes a permanent source boundary')
        anchors=[];permanent=[copy.deepcopy(link) for link in data['seams'] if link.get('kind','permanent')=='permanent' and
                            (link['piece_a'] in unit or link['piece_b'] in unit)]
        if hoods:
            crown=[link for link in permanent if {link['piece_a'],link['piece_b']}==set(hoods)]
            if not crown:
                issue('MISSING_DATA','HOOD_EXPLICIT_PERMANENT_CROWN_REQUIRED');continue
            missing=False
            for pid in hoods:
                edges=semantics[pid].get('guide_edges',{});face=edges.get('opening','face-free');anchor=edges.get('anchor','neck-base')
                bindings=[link for link in permanent if any(link['piece_'+side]==pid and link['edge_'+side]==anchor and
                          link['piece_'+other]==yoke for side,other in (('a','b'),('b','a')))]
                if not free_edge(pid,face) or anchor not in data['pieces'][pid]['edges'] or len(bindings)!=1:
                    missing=True;break
                rims.append({'piece':pid,'edge':face});anchors.append({'piece':pid,'edge':anchor,'source_link_id':bindings[0]['id']})
            if missing:
                issue('MISSING_DATA','HOOD_EXPLICIT_FREE_FACE_AND_PERMANENT_NECK_BINDINGS_REQUIRED');continue
        else:
            edges=semantics[yoke].get('guide_edges',{});names=[edges.get('anchor','neck-left'),edges.get('anchor_end','neck-right')]
            if any(not free_edge(yoke,name) for name in names):
                issue('MISSING_DATA','YOKE_EXPLICIT_OPEN_NECK_EDGES_REQUIRED');continue
            rims.extend({'piece':yoke,'edge':name} for name in names)
        links=[copy.deepcopy(link) for link in data['seams'] if link.get('kind') in ('closure','detachable') and
               (link['piece_a'] in unit or link['piece_b'] in unit)]
        units.append({'id':data['component_id']+('.hood-yoke' if hoods else '.yoke.'+yoke),
                      'method':'OPEN_HOOD_YOKE' if hoods else 'OPEN_DETACHABLE_YOKE','pieces':sorted(unit),
                      'source_edges':sorted(rims,key=lambda row:(row['piece'],row['edge'])),
                      'source_anchor_edges':anchors,'source_permanent_links':permanent,'source_open_links':links,
                      'mode_proposals':['RAISED_OPEN_HOOD','LOWERED_OPEN_HOOD'] if hoods else ['OPEN_SHOULDER_YOKE']})
    return units,issues


def _method_configuration(proposal, configurations):
    """Admit declared open source relations only; absence remains reviewable data."""
    rows=[row for row in configurations if row['method_id']==proposal['id']]
    if len(rows)>1:raise StudioError('Dressing method configurations repeat an exact source method identity')
    if not rows:return None
    configuration=rows[0]
    if configuration['mode'] not in proposal['mode_proposals']:
        raise StudioError('Dressing selected mode is incompatible with its permanent source unit')
    expected={row['id'] for row in proposal['source_open_links']};states=configuration['source_link_states']
    if (len(states)!=len(expected) or {row['source_link_id'] for row in states}!=expected or
            any(row['state']!='OPEN' for row in states)):
        raise StudioError('Dressing configuration must keep every exact source closure/detachable relation OPEN')
    return copy.deepcopy(configuration)


def derive_dressing_contract(compiled, sources, profile, geometry, triangles, guides, templates, policy):
    """Return source methods and missing domains, without granting passage admission."""
    contract('dressing-derivation', policy)
    original = digest([compiled, sources, profile, geometry, triangles, guides, templates, policy])
    if len(triangles) > policy['budgets']['max_body_triangles']:
        raise StudioError('Dressing body triangle budget cannot cover its complete native collider')
    if policy['section_parameters']!=sorted(policy['section_parameters']):
        raise StudioError('Dressing section parameters must be strictly increasing')
    collider = _triangles(profile, geometry, triangles)
    semantics = {pid: row['semantics'] for pid, row in compiled['textiles'].items()}
    methods = []; regions = []; boundaries = {}; issues = [];configurable_ids=set()
    configurations=policy.get('method_configurations',[])
    if len({row['method_id'] for row in configurations})!=len(configurations):
        raise StudioError('Dressing method configurations repeat an exact source method identity')
    def issue(category, reason, **details):
        issues.append({'category': category, 'reason': reason, **details})
    def measured_region(*args):
        if (len(methods)>=policy['budgets']['max_methods'] or
                (len(regions)+1)*len(policy['section_parameters'])>policy['budgets']['max_sections']):
            raise StudioError('Dressing method/section budget cannot cover its derived source inventory')
        return _region(profile,collider,*args)
    for cid, source in sorted(sources.items()):
        data = source['data']; guide = guides[cid]; component = templates['components'][cid]
        if (guide['source_sha256'] != digest(data) or guide['profile_sha256'] != digest(profile) or
                guide['profile_cache_key'] != profile['cache_key'] or component['source_ref'] != source['source_ref'] or
                component['plan_fields']['preform']['panels'] != guide['panels'] or
                any(compiled['textiles'][pid]['source_geometry'] != piece for pid, piece in data['pieces'].items())):
            raise StudioError('Dressing source pieces/guides/templates differ from their exact compiled sources')
        fields = component['plan_fields']; reserve = fields['collision']['clearance_cm']
        graph = source_boundary_graph(data, policy['budgets']['max_boundary_edges']); boundaries[cid] = graph
        if graph['status'] == 'INCOMPLETE':
            issue('BUDGET_INCOMPLETE', graph['reason'], component_id=cid); continue
        roles = {pid: semantics[pid]['role'] for pid in data['pieces']}
        def method(method_id, kind, pieces, source_edges, region, **details):
            methods.append({'id': method_id, 'method': kind, 'component_id': cid, 'pieces': sorted(pieces),
                'layers': sorted({semantics[pid]['layer'] for pid in pieces}), 'source_edges': source_edges,
                'source_ref': copy.deepcopy(source['source_ref']), 'body_region': region['id'],
                'region_sha256': digest(region), 'clearance_cm': reserve,
                'source_assembly_budget': copy.deepcopy(fields['assembly']),
                'source_guides': {pid: copy.deepcopy(guide['panels'][pid]) for pid in pieces},
                'source_vertices': {pid: copy.deepcopy(data['pieces'][pid]['vertices']) for pid in pieces},
                'source_named_edges': {pid: copy.deepcopy(data['pieces'][pid]['edges']) for pid in pieces},
                'qualification': 'EXPLORATORY_SOURCE_METHOD', 'passage': 'NOT_QUALIFIED',
                'entry_configuration': 'REQUIRED_BEFORE_PHYSICAL_DRESSING', **details})
        cuff_pieces = [pid for pid, role in roles.items() if role == 'cuff']
        for pid in cuff_pieces:
            side = semantics[pid]['side']; wrist, elbow = 'wrist.'+side, 'elbow.'+side
            if side not in ('left', 'right') or any(name not in profile['landmarks'] for name in (wrist, elbow)):
                issue('MISSING_DATA', 'MEASURED_ARM_AXIS_REQUIRED', piece=pid); continue
            candidates = [row for row in graph['components'] if row['closed_graph'] and row['pieces'] == [pid]]
            if len(candidates) != 1:
                issue('AMBIGUOUS_DECISION', 'CUFF_SOURCE_BOUNDARY_NOT_UNIQUE', piece=pid); continue
            region = measured_region(cid+'.forearm.'+side,
                world_point(profile, profile['landmarks'][wrist]['point_cm']),
                world_point(profile, profile['landmarks'][elbow]['point_cm']), policy['section_parameters'], 'WRIST_TO_ELBOW_ONLY')
            regions.append(region)
            method(cid+'.cuff.'+side, 'CLOSED_CUFF', [pid], candidates[0]['source_edges'], region,
                   source_boundary_id=candidates[0]['id'], required_anatomical_domain='HAND_THROUGH_FOREARM')
            issue('MISSING_DATA', 'MEASURED_HAND_ENTRY_DOMAIN_REQUIRED', piece=pid)
        belts = [pid for pid, role in roles.items() if role == 'belt']
        for pid in belts:
            closures = [row for row in data['seams'] if row['kind'] == 'closure' and row['piece_a'] == row['piece_b'] == pid]
            if len(closures) != 1 or 'waist' not in profile['landmarks']:
                issue('MISSING_DATA', 'BELT_SOURCE_CLOSURE_AND_WAIST_REQUIRED', piece=pid); continue
            waist = profile['landmarks']['waist']; v_values = [p[1] for p in data['pieces'][pid]['vertices']]
            width = max(v_values)-min(v_values); center = list(waist['point_cm'])
            start = world_point(profile, [center[0], center[1], center[2]-width/2])
            end = world_point(profile, [center[0], center[1], center[2]+width/2])
            region = measured_region(cid+'.waist', start, end, policy['section_parameters'], 'SOURCE_BAND_WIDTH_AT_MEASURED_WAIST')
            regions.append(region); link = closures[0]
            method(cid+'.wrap', 'OPEN_WRAP', [pid], [{'piece': pid, 'edge': link['edge_a']}, {'piece': pid, 'edge': link['edge_b']}],
                   region, source_closure=copy.deepcopy(link), band_width_cm=width,
                   opening_interpretation='OPEN_BAND_NEVER_CLOSED_PASSAGE_FROM_FLAT_PERIMETER')
        fronts = [pid for pid, role in roles.items() if role == 'front' and 'opening' in semantics[pid].get('guide_edges', {})]
        if fronts:
            opening_edges = [{'piece': pid, 'edge': semantics[pid]['guide_edges']['opening']} for pid in sorted(fronts)]
            permanent_names = {(row['piece_'+side], row['edge_'+side]) for row in data['seams'] if row['kind'] == 'permanent' for side in ('a', 'b')}
            if any((row['piece'], row['edge']) in permanent_names for row in opening_edges):
                raise StudioError('Approved free front edge is consumed by a permanent source seam')
            if len(fronts) != 2 or {semantics[pid]['side'] for pid in fronts} != {'left', 'right'}:
                issue('AMBIGUOUS_DECISION', 'OPEN_FRONT_METHOD_NEEDS_TWO_EXPLICIT_SIDES', component_id=cid)
            elif any(key not in profile['landmarks'] for key in ('hip', 'neck')):
                issue('MISSING_DATA', 'MEASURED_TORSO_AXIS_REQUIRED', component_id=cid)
            else:
                region = measured_region(cid+'.torso', world_point(profile, profile['landmarks']['hip']['point_cm']),
                    world_point(profile, profile['landmarks']['neck']['point_cm']), policy['section_parameters'], 'HIP_TO_NECK_SURFACE')
                regions.append(region); method(cid+'.open-front', 'OPEN_FRONT', list(data['pieces']), opening_edges, region,
                    opening_interpretation='SOURCE_FRONT_FREE_EDGES_NO_VIRTUAL_FRONT_WELD')
        proposals,source_issues=hood_yoke_units(data,semantics,graph);issues.extend(source_issues)
        for proposal in proposals:
            configurable_ids.add(proposal['id']);configuration=_method_configuration(proposal,configurations)
            is_hood=proposal['method']=='OPEN_HOOD_YOKE';names=('neck','head.center') if is_hood else ('chest','neck')
            if any(name not in profile['landmarks'] for name in names):
                issue('MISSING_DATA','MEASURED_HOOD_OR_SHOULDER_AXIS_REQUIRED',method_id=proposal['id'],landmarks=list(names));continue
            domain='NECK_TO_HEAD_CENTER_ONLY' if is_hood else 'CHEST_TO_NECK_ONLY'
            region=measured_region(proposal['id']+'.region',*(world_point(profile,profile['landmarks'][name]['point_cm']) for name in names),
                                   policy['section_parameters'],domain)
            if is_hood:region['full_head_passage']='NOT_QUALIFIED'
            regions.append(region)
            method(proposal['id'],proposal['method'],proposal['pieces'],proposal['source_edges'],region,
                   source_anchor_edges=proposal['source_anchor_edges'],source_permanent_links=proposal['source_permanent_links'],
                   source_open_links=proposal['source_open_links'],mode_proposals=proposal['mode_proposals'],configuration=configuration,
                   configuration_status='DECLARED_OPEN_SOURCE_CONFIGURATION' if configuration else 'NEEDS_DATA',
                   opening_interpretation='SOURCE_OPEN_FACE_FRONT_AND_DETACHABLE_RELATIONS_NO_VIRTUAL_WELD',
                   closure_behavior='NOT_EXECUTED',full_head_passage='NOT_QUALIFIED' if is_hood else 'NOT_APPLICABLE')
            if configuration is None:
                issue('MISSING_DATA','HOOD_YOKE_SOURCE_MODE_AND_OPEN_LINK_STATES_REQUIRED',method_id=proposal['id'],
                      mode_proposals=proposal['mode_proposals'],source_link_ids=[row['id'] for row in proposal['source_open_links']])
    if len(methods) > policy['budgets']['max_methods'] or len(regions)*len(policy['section_parameters']) > policy['budgets']['max_sections']:
        raise StudioError('Dressing method/section budget cannot cover its derived source inventory')
    for region in regions:
        if region['status'] != 'MEASURED_SECTIONS':
            issue('MISSING_DATA', 'ANATOMICAL_SECTION_UNRESOLVED', region=region['id'],
                  reasons=[row['reason'] for row in region['sections'] if not row['ok']])
    if any(row['method_id'] not in configurable_ids for row in configurations):
        raise StudioError('Dressing configuration names an absent or unresolved source method')
    selected = policy.get('mount_order')
    if (selected is None) != (policy.get('mount_order_source_ref') is None):
        raise StudioError('An explicit mount order requires its exact human/source decision reference')
    order = mount_orders(methods, compiled['assembly_spec']['layers'], policy['budgets']['max_candidate_orders'], selected)
    if order['status'] != 'ORDER_DERIVED':
        issue('BUDGET_INCOMPLETE' if order['status'] == 'INCOMPLETE' else 'AMBIGUOUS_DECISION', order['reason'])
    issue('MISSING_DATA', 'NATIVE_ENTRY_CONFIGURATION_AND_SOURCE_GRIPS_REQUIRED')
    if digest([compiled, sources, profile, geometry, triangles, guides, templates, policy]) != original:
        raise StudioError('Dressing derivation mutated immutable inputs')
    result = {'version': 1, 'status': 'NEEDS_DATA' if issues else 'SOURCE_METHODS_DERIVED',
              'component_sources':{cid:{'source_ref':copy.deepcopy(row['source_ref']),
                  'source_garment_sha256':digest(row['data']),
                  'source_piece_contours_sha256':{pid:digest(piece['vertices']) for pid,piece in row['data']['pieces'].items()}}
                  for cid,row in sorted(sources.items())},
              'source_inputs_sha256': original, 'body_profile_sha256': digest(profile), 'body_geometry_sha256': profile['geometry_sha256'],
              'body_pose_sha256': profile['pose_sha256'], 'boundaries': boundaries, 'methods': methods, 'regions': regions,
              'mount_dag': order, 'diagnostics': issues, 'policy': copy.deepcopy(policy),
              'qualification': 'EXPLORATORY_DRESSING_GEOMETRY_ONLY', 'source_cut_preserved': True,
              'source_mutated': False, 'simulation': 'NOT_EXECUTED', 'fitting': 'NOT_QUALIFIED', 'accepted': False}
    result['derivation_sha256'] = digest(result)
    return result


def dressing_derivation_descriptor(project, specification_path):
    """Rebuild templates from their exact approved sources before deriving anything."""
    from .production_dossier import compile_project_dossier
    from .garment_planner import plan_assembly
    from .textile_executor import prepare_component_templates
    policy = contract('dressing-derivation', read_json(inside(project.root, specification_path)))
    evidence = [{'path': specification_path, 'sha256': sha(inside(project.root, specification_path))}]
    def verified(reference):
        _reference(reference); path = inside(project.root, reference['path'])
        if sha(path) != reference['sha256']:
            raise StudioError('Dressing derivation input changed: '+reference['path'])
        evidence.append(copy.deepcopy(reference)); return read_json(path)
    bindings = policy['bindings']; templates = verified(bindings['templates_ref']); inputs = templates['compiler_inputs']
    for reference in inputs.values():
        verified(reference)
    compiled = compile_project_dossier(project, inputs['dossier_ref']['path'], inputs['production_spec_ref']['path'])
    assembly = verified(inputs['assembly_plan_ref'])
    if assembly != plan_assembly(compiled['assembly_spec'], capabilities=['coupled_multilayer']):
        raise StudioError('Dressing source assembly differs from its exact compiled construction')
    metadata = verified(inputs['production_spec_ref']); sources = {}
    for row in metadata['packages']:
        reference = row['source_ref']; _reference(reference); path = inside(project.root, reference['path'])
        if sha(path) != reference['sha256']:
            raise StudioError('Dressing source package changed')
        evidence.append(copy.deepcopy(reference))
        with zipfile.ZipFile(path) as archive:
            sources[row['component_id']] = {'source_ref': reference, 'data': json.loads(archive.read('garment.json'))}
    guides = verified(inputs['guides_ref'])
    rebuilt = prepare_component_templates(assembly, sources, guides, verified(inputs['standard_recipe_ref']),
        verified(inputs['dossier_ref']), inputs['dossier_ref'], inputs)
    if rebuilt != templates:
        raise StudioError('Dressing templates differ from reconstruction of their exact source policies and guides')
    profile = verified(templates['body_ref']); geometry = verified(bindings['body_geometry_ref']); triangles = verified(bindings['body_triangles_ref'])
    if 'mount_order_source_ref' in policy:
        decision=verified(policy['mount_order_source_ref'])
        if not isinstance(decision,dict) or decision.get('mount_order')!=policy.get('mount_order'):
            raise StudioError('Dressing selected order differs from its exact source decision document')
    for configuration in policy.get('method_configurations',[]):
        decision=verified(configuration['source_ref'])
        if decision!={key:value for key,value in configuration.items() if key!='source_ref'}:
            raise StudioError('Dressing method configuration differs from its exact source decision document')
    result = derive_dressing_contract(compiled, sources, profile, geometry, triangles, guides, templates, policy)
    return {'policy': policy, 'evidence': evidence, 'derivation': result, 'binding_sha256': digest(evidence)}
