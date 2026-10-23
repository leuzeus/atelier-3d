"""Source sewing supports and native path seeds for joint guide placement.

Both partners remain variables. A driver's proposed boundary is not converted
into fixed anatomy. File receipt/review authentication stays with the public
caller; this producer verifies the actual source, cage and body incidences.
"""
import bisect
from collections import defaultdict
import copy
import math
from pathlib import Path
import time

from .anatomical_placement import validate_anatomical_references
from .core import StudioError, digest, sha
from .pattern_assembly import _cage_point, _compile_cage
from .sewing import chain_lengths, edge_chain, sample_chain
from .source_seam_coupling import _Budget, _chain, _prepare_piece, _source


METHOD = 'HOMOLOGOUS_PATH_BAND_BOUNDARY_V1'
TARGETS = ('HOMOLOGOUS_DRIVER_BOUNDARY_TARGET', 'CURRENT_PARTNER_BOUNDARY_TARGET')
MAX_BINDINGS = 4096


def _finite(value):
    return type(value) in (int, float) and math.isfinite(value)


def _domain(rule, profile, geometry):
    if rule is None:
        return None
    if not isinstance(rule, dict) or rule.get('method') != 'REGIONAL_SURFACE_ENVELOPE_V1':
        raise StudioError('Boundary anatomical query needs an existing regional surface policy')
    regions = rule.get('source_region_ids'); direction = rule.get('direction_body')
    if (not isinstance(regions, list) or not 1 <= len(regions) <= 128 or
            any(type(i) is not int for i in regions) or len(set(regions)) != len(regions) or
            not set(regions) <= set(geometry['face_sets']) or
            not isinstance(direction, (list, tuple)) or len(direction) != 3 or
            not all(_finite(v) for v in direction)):
        raise StudioError('Boundary anatomical query needs actual distinct regions and finite direction')
    size = math.hypot(*direction)
    if not math.isfinite(size) or size <= 1e-10:
        raise StudioError('Boundary anatomical direction must be finite and nonzero')
    from .regional_surface_guides import _positive
    reserve = _positive(rule.get('reserve_cm'), 'reserve_cm', 20.)
    maximum = _positive(rule.get('max_displacement_cm'), 'max_displacement_cm', 100.)
    if reserve > maximum:
        raise StudioError('Boundary anatomical reserve exceeds its declared displacement budget')
    if 'source_v_range_cm' in rule:
        interval = rule['source_v_range_cm']
        if (not isinstance(interval, list) or len(interval) != 2 or
                not all(_finite(v) for v in interval) or interval[0] > interval[1]):
            raise StudioError('Boundary anatomical query material range is invalid')
    world = [math.fsum(direction[j]/size*profile['frame'][axis][k]
             for j, axis in enumerate(('right', 'forward', 'up'))) for k in range(3)]
    return {**copy.deepcopy(rule), 'direction_world': world}


def _material_location(piece, edge, reverse, fraction, budget):
    indices, points, _ = edge_chain(piece, edge)
    if reverse:
        indices, points = list(reversed(indices)), list(reversed(points))
    cumulative = chain_lengths(points); total = cumulative[-1]
    owners = []
    for i, (a, b) in enumerate(zip(indices, indices[1:])):
        budget.check()
        low, high = cumulative[i]/total, cumulative[i+1]/total
        if low <= fraction <= high:
            faces = [j for j, face in enumerate(piece['faces']) if any(
                {x, y} == {a, b} for x, y in zip(face, face[1:]+face[:1]))]
            if len(faces) != 1:
                raise StudioError('A selected source boundary needs one original material face owner')
            owners.append({'source_segment_index': i, 'oriented_vertex_ids': [a, b],
                'source_face_ids': faces,
                'segment_fraction': (fraction*total-cumulative[i])/(cumulative[i+1]-cumulative[i]),
                'normalized_fraction_interval': [low, high]})
    if not owners:
        raise StudioError('Homologous fraction has no original source boundary owner')
    corners = [index for index, length in zip(indices, cumulative) if fraction == length/total]
    return {'edge': edge, 'reverse_source_edge': reverse, 'common_fraction': fraction,
        'source_uv_cm': sample_chain(points, fraction), 'source_segment_owners': owners,
        'source_corner_vertex_ids': corners, 'source_edge_length_cm': total}


def _support(frame, compiled, uv, state, pid, budget):
    point, receipt = _cage_point(frame, compiled, uv, pid, budget.check)
    triangle_id = receipt['cage_triangle']; triangle = frame['triangles'][triangle_id]
    # Keep the canonical evaluator's unrounded weights, including arithmetic
    # boundary roundoff. Never choose a different support by world proximity.
    return {'cage_triangle': triangle_id, 'source_face': state['triangle_source_faces'][triangle_id],
        'control_indices': list(triangle), 'weights': receipt['barycentric_weights'],
        'evaluated_world_cm': point}


def prepare_source_boundary_bindings(data, frames, recipe, profile, geometry,
                                     anatomical_references, policy, *, clock=time.monotonic):
    """Prepare evaluated sewing equations and optional anatomical queries.

    ``anatomical_references`` is the resolved public input document (containing
    measured reports), not a normalized object with self-asserted provenance.
    Explicit UV/XYZ cages are required so returned supports address exactly the
    caller's current candidate. Missing domains do not discard sewing supports.
    Re-evaluate this producer after any cage/body/policy change; its identities
    bind both mutable candidate positions and immutable material coordinates.
    """
    required = {'version', 'method', 'driver_piece', 'source_seam_ids',
                'ease_distribution', 'query_target_kind', 'budgets'}
    if (not isinstance(policy, dict) or set(policy) != required or
            type(policy['version']) is not int or policy['version'] != 1 or
            policy['method'] != METHOD or policy['query_target_kind'] not in TARGETS or
            policy['ease_distribution'] != 'UNIFORM_NORMALIZED_SOURCE_ARC' or
            not isinstance(policy['budgets'], dict) or
            not isinstance(policy['driver_piece'], str) or not policy['driver_piece'] or
            not isinstance(policy['source_seam_ids'], list) or not 1 <= len(policy['source_seam_ids']) <= 128 or
            any(not isinstance(s, str) or not s for s in policy['source_seam_ids']) or
            len(set(policy['source_seam_ids'])) != len(policy['source_seam_ids'])):
        raise StudioError('Boundary bindings require an explicit bounded source sewing/path policy')
    budget = _Budget(policy['budgets'], clock)
    contracts = _source(data, frames, recipe, budget)
    try:
        references = validate_anatomical_references(profile, anatomical_references, geometry=geometry)
    except (ValueError, TypeError, OverflowError) as error:
        raise StudioError('Boundary anatomical inputs require finite canonical source data') from error
    budget.check()
    driver = policy['driver_piece']; rule = references['pieces'].get(driver)
    if driver not in data['pieces'] or not isinstance(rule, dict) or rule.get('guide_kind') != 'PATH_BAND_V1':
        raise StudioError('Boundary driver requires an actual declared PATH_BAND_V1 source piece')
    from .garment_guides import _declared_anchor
    reference = references['paths'].get(rule.get('path_ref'))
    if (not reference or reference['closed'] is not True or
            reference.get('geometry_validation') != 'EXACT_SOURCE_EDGES_VERIFIED' or
            'source_face_incidence' not in reference or rule.get('material_axis') not in ('u', 'v') or
            type(rule.get('path_direction')) is not int or rule['path_direction'] not in (-1, 1) or
            not _finite(rule.get('path_anchor_fraction')) or not 0 <= rule['path_anchor_fraction'] <= 1 or
            rule.get('surface_offset_cm', 0.) != 0.):
        raise StudioError('Boundary driver needs an exact closed native path and explicit material phase/direction')
    anchor = _declared_anchor(data['pieces'][driver], rule)
    along = 0 if rule['material_axis'] == 'u' else 1
    width = max(p[along] for p in data['pieces'][driver]['vertices'])-min(p[along] for p in data['pieces'][driver]['vertices'])
    maximum = rule.get('max_path_expansion_ratio')
    if (width <= 1e-8 or not _finite(maximum) or not 1 <= maximum <= 2 or
            not 1-1e-10 <= width/reference['length_cm'] <= maximum):
        raise StudioError('Boundary source width lies outside its explicit measured-path expansion domain')
    inventory = {s['id']: s for s in data['seams']}
    selected = []
    for sid in sorted(policy['source_seam_ids']):
        seam = inventory.get(sid)
        if (not seam or seam['kind'] != 'permanent' or driver not in (seam['piece_a'], seam['piece_b']) or
                seam['piece_a'] == seam['piece_b']):
            raise StudioError('Boundary selection requires actual permanent relations to distinct driver partners')
        selected.append(seam)
    pieces = {seam['piece_'+side] for seam in selected for side in ('a', 'b')}
    if not pieces <= set(frames):
        raise StudioError('Every selected boundary partner requires its current candidate cage')
    states = {}; compiled = {}
    for pid in sorted(pieces):
        if set(frames[pid]) != {'source_ref', 'uv_cm', 'target_cm', 'triangles'}:
            raise StudioError('Boundary solver supports require explicit current source-conforming cages')
        states[pid] = _prepare_piece(data['pieces'][pid], frames[pid], pid, 1, budget)
        compiled[pid] = _compile_cage(frames[pid], pid, budget.check)
    immutable = digest([data, frames, recipe, profile, geometry, anatomical_references, policy])
    native_edges = defaultdict(list); native_vertices = defaultdict(list)
    for fid, face in enumerate(geometry['faces']):
        budget.check()
        for vertex in face:
            native_vertices[vertex].append(fid)
        for a, b in zip(face, face[1:]+face[:1]):
            native_edges[tuple(sorted((a, b)))].append(fid)
    points = reference['points_world_cm']
    lengths = [math.dist(a, b) for a, b in zip(points, points[1:]+points[:1])]
    total = math.fsum(lengths); cumulative = [0.]
    for length in lengths:
        cumulative.append(cumulative[-1]+length)
    parent = {}
    def root(key):
        parent.setdefault(key, key)
        while parent[key] != key:
            key = parent[key]
        return key
    for seam in data['seams']:
        if seam['kind'] != 'permanent':
            continue
        a = data['pieces'][seam['piece_a']]['edges'][seam['edge_a']]
        b = data['pieces'][seam['piece_b']]['edges'][seam['edge_b']]
        if seam['orientation'] == 'reverse': b = list(reversed(b))
        for x, y in ((a[0], b[0]), (a[-1], b[-1])):
            ka, kb = root((seam['piece_a'], x)), root((seam['piece_b'], y))
            if ka != kb: parent[max(ka, kb)] = min(ka, kb)
    cohorts = defaultdict(list)
    for key in parent:
        cohorts[root(key)].append(list(key))
    rows = []; relations = []; missing = []
    for seam in selected:
        driver_side = 'a' if seam['piece_a'] == driver else 'b'
        partner_side = 'b' if driver_side == 'a' else 'a'; partner = seam['piece_'+partner_side]
        chains = {side: _chain(data['pieces'][seam['piece_'+side]], seam['edge_'+side],
            side == 'b' and seam['orientation'] == 'reverse', states[seam['piece_'+side]], seam['piece_'+side], 1)
            for side in ('a', 'b')}
        fractions = sorted(set(item['fraction'] for chain in chains.values() for item in chain['controls']))
        domain = _domain(references['pieces'].get(partner, {}).get('surface_envelope'), profile, geometry)
        relation_rows = []
        for fraction in fractions:
            budget.check()
            if len(rows) >= MAX_BINDINGS:
                raise StudioError('Source boundary binding count budget exhausted')
            links = {}
            for side in ('a', 'b'):
                pid = seam['piece_'+side]
                location = _material_location(data['pieces'][pid], seam['edge_'+side],
                    side == 'b' and seam['orientation'] == 'reverse', fraction, budget)
                support = _support(frames[pid], compiled[pid], location['source_uv_cm'], states[pid], pid, budget)
                controls = [x['index'] for x in chains[side]['controls'] if x['fraction'] == fraction]
                links[side] = {**location, 'piece': pid, 'existing_control_indices': controls, 'support': support,
                    'corner_cohorts': [cohorts.get(root((pid, i)), [[pid, i]]) for i in location['source_corner_vertex_ids']]}
            driver_link, partner_link = links[driver_side], links[partner_side]
            uv = driver_link['source_uv_cm']
            phase = (rule['path_anchor_fraction']+rule['path_direction']*(uv[along]-anchor[along])/width) % 1.
            arc = phase*total; segment = min(len(lengths)-1, bisect.bisect_right(cumulative, arc)-1)
            local = (arc-cumulative[segment])/lengths[segment]
            if not _finite(local) or not 0 <= local <= 1:
                raise StudioError('Derived native seed lies outside its exact source edge')
            edge = reference['edge_vertex_ids'][segment]
            vertex = edge[0] if local == 0 else edge[1] if local == 1 else None
            incidence = native_vertices[vertex] if vertex is not None else native_edges[tuple(sorted(edge))]
            allowed = [fid for fid in incidence if domain is not None and geometry['face_sets'][fid] in domain['source_region_ids']]
            target_link = driver_link if policy['query_target_kind'] == TARGETS[0] else partner_link
            target = target_link['support']['evaluated_world_cm']
            binding_id = digest({'source_seam': seam['id'], 'common_fraction': fraction})
            seed = {'kind': 'NATIVE_VERTEX' if vertex is not None else 'NATIVE_EDGE_INTERIOR',
                'path_ref': rule['path_ref'], 'path_sha256': reference['path_sha256'],
                'path_fraction': phase, 'path_segment_index': segment, 'edge_vertex_ids': list(edge),
                'edge_fraction': local, 'vertex_id': vertex,
                'native_incident_face_ids': list(incidence), 'allowed_native_incident_face_ids': allowed,
                'incidence_identity': copy.deepcopy(reference['source_face_incidence']['identity'])}
            reason = None
            if domain is None:
                reason = 'PARTNER_REGIONAL_DOMAIN_NOT_DECLARED'
            elif 'source_v_range_cm' in domain and not domain['source_v_range_cm'][0] <= partner_link['source_uv_cm'][1] <= domain['source_v_range_cm'][1]:
                reason = 'PARTNER_MATERIAL_POINT_OUTSIDE_DECLARED_REGIONAL_RANGE'
            elif not allowed:
                reason = 'NATIVE_SEED_OUTSIDE_DECLARED_REGIONAL_DOMAIN'
            query = None if reason else {'request_id': binding_id, 'seed_edge_vertex_ids': list(edge),
                'seed_fraction': local, 'seed_face_ids': allowed, 'target_world_cm': list(target)}
            row = {'binding_id': binding_id, 'source_seam_id': seam['id'], 'driver': driver_link,
                'partner': partner_link, 'body_seed': seed, 'domain': copy.deepcopy(domain),
                'query_target_kind': policy['query_target_kind'], 'anatomical_query': query,
                'anatomical_query_status': reason or 'INPUTS_PREPARED_NOT_TRACED',
                'sewing_support_status': 'BOTH_CURRENT_CAGE_SUPPORTS_PREPARED',
                'current_seam_gap_cm': math.dist(driver_link['support']['evaluated_world_cm'], partner_link['support']['evaluated_world_cm']),
                'fixed_anatomical_constraint_added': False}
            rows.append(row); relation_rows.append(binding_id)
            if reason: missing.append({'binding_id': binding_id, 'reason': reason})
        relations.append({'source_relation': copy.deepcopy(seam), 'recipe': copy.deepcopy(recipe['seams'][seam['id']]),
            'source_contract': contracts[seam['id']], 'ease_distribution': policy['ease_distribution'], 'binding_ids': relation_rows})
    budget.check()
    if digest([data, frames, recipe, profile, geometry, anatomical_references, policy]) != immutable:
        raise StudioError('Source boundary binding changed immutable inputs')
    identities = {'source_sha256': digest(data), 'recipe_sha256': digest(recipe), 'frames_sha256': digest(frames),
        'profile_sha256': digest(profile), 'geometry_sha256': profile['geometry_sha256'],
        'body_source_sha256': profile['source_sha256'], 'body_pose_sha256': profile['pose_sha256'],
        'face_sets_sha256': digest(geometry['face_sets']), 'anatomical_references_sha256': digest(anatomical_references),
        'policy_sha256': digest(policy), 'kernel_sha256': sha(Path(__file__))}
    binding_set_sha256 = digest([identities, relations, rows])
    budget.check()
    return {'version': 1, 'method': METHOD, 'status': 'PARTIAL_ANATOMICAL_INPUTS' if missing else 'SOURCE_BOUNDARY_BINDINGS_PREPARED',
        'identities': identities, 'binding_set_sha256': binding_set_sha256,
        'component_id': data['component_id'], 'driver_piece': driver, 'relations': relations, 'bindings': rows,
        'unresolved_anatomical_inputs': missing, 'source_corner_cohorts': sorted(cohorts.values()),
        'source_mutated': False, 'candidate_adjusted': False, 'new_fixed_anatomical_constraints': 0,
        'source_geometry_validation': 'SOURCE_CONFORMING_CAGES_AND_NATIVE_PATH_INCIDENCES_VERIFIED',
        'native_receipts_and_human_review': 'CALLER_MUST_VERIFY', 'qualification': 'NONE',
        'budgets': {**budget.limits, 'max_bindings': MAX_BINDINGS},
        'usage': {'controls': budget.controls, 'triangles': budget.triangles, 'bindings': len(rows)}}


def validate_current_boundary_policy(policy):
    """Validate the public diagnostic strategy before loading or calculating."""
    required = {'version', 'method', 'driver_piece', 'source_seam_ids',
        'ease_distribution', 'query_target_kind', 'budgets', 'continuation'}
    if not isinstance(policy, dict) or set(policy) != required or policy.get('query_target_kind') != TARGETS[1]:
        raise StudioError('Public boundary inspection requires explicit current partner targets')
    continuation = policy['continuation']
    if (not isinstance(continuation, dict) or set(continuation) != {'method', 'min_cosine', 'max_events'} or
            continuation['method'] != 'SEEDED_SURFACE_PATH_LIFT_V2' or
            not _finite(continuation['min_cosine']) or not 0 < continuation['min_cosine'] < 1 or
            type(continuation['max_events']) is not int or not 1 <= continuation['max_events'] <= 2000000):
        raise StudioError('Boundary continuation requires an explicit bounded V2 method')


def inspect_current_source_boundaries(data, frames, recipe, profile, geometry,
                                     anatomical_references, policy, *, clock=time.monotonic):
    """Prepare bilateral supports and trace their current partner positions.

    One deadline covers source preparation, native authentication and every
    domain batch. Timing is deliberately absent from this replayable report;
    exhaustion refuses the operation instead of publishing a timing-dependent
    partial result. Geometric refusals remain complete, deterministic evidence.
    No target is projected or added to the immutable attachment set.
    """
    validate_current_boundary_policy(policy)
    continuation = policy['continuation']
    budget = _Budget(policy['budgets'], clock)
    def shared_clock():
        budget.check()
        return budget.last_time
    before = digest([data, frames, recipe, profile, geometry, anatomical_references, policy])
    result = prepare_source_boundary_bindings(data, frames, recipe, profile, geometry,
        anatomical_references, {k: v for k, v in policy.items() if k != 'continuation'}, clock=shared_clock)
    from .dressing_derivation import _triangles
    from .surface_path_continuation import trace_surface_paths
    triangles = anatomical_references.get('triangles')
    _triangles(profile, geometry, triangles)
    budget.check()
    memberships = defaultdict(set)
    for fid, face in enumerate(geometry['faces']):
        budget.check()
        for index in face:
            memberships[index].add(fid)
    owners = []
    for triangle in triangles:
        budget.check()
        common = set.intersection(*(memberships[index] for index in triangle))
        if len(common) != 1:
            raise StudioError('Boundary continuation needs unique exact native triangle owners')
        owners.append(next(iter(common)))
    groups = defaultdict(list)
    for row in result['bindings']:
        if row['anatomical_query'] is not None:
            groups[digest(row['domain'])].append(row)
    batches = []; observations = []; work = 0
    for domain_id, rows in sorted(groups.items()):
        budget.check()
        if work >= continuation['max_events']:
            raise StudioError('Boundary continuation shared work budget exhausted')
        domain = rows[0]['domain']
        trace_policy = {'method': continuation['method'], 'source_region_ids': domain['source_region_ids'],
            'direction_world': domain['direction_world'], 'min_cosine': continuation['min_cosine'],
            'max_seconds': budget.limits['max_seconds'], 'max_events': continuation['max_events']-work}
        queries = [row['anatomical_query'] for row in rows]
        traced = trace_surface_paths(geometry['vertices_cm'], triangles, owners, geometry['face_sets'],
                                     trace_policy, queries, clock=shared_clock)
        if (traced.get('unprocessed_queries') or traced.get('reason') in ('TIME_BUDGET_EXHAUSTED', 'WORK_BUDGET_EXHAUSTED') or
                any(row.get('reason') in ('TIME_BUDGET_EXHAUSTED', 'WORK_BUDGET_EXHAUSTED') for row in traced['rows'])):
            raise StudioError('Boundary continuation shared time or work budget exhausted')
        work += traced['work_events']
        traced.pop('elapsed_seconds', None)
        by_id = {row['binding_id']: row for row in rows}
        for observed in traced['rows']:
            observed.pop('elapsed_seconds', None)
            binding = by_id[observed['request_id']]
            measured = {'binding_id': binding['binding_id'], 'continuation': copy.deepcopy(observed)}
            if observed['status'] == 'LOCAL_PATH_LIFT_REACHED':
                if observed['endpoint_normal_status'] != 'INTERIOR_TRIANGLE_NORMAL':
                    measured['selected_plane_reserve'] = {'status': 'NOT_VERIFIABLE_ENDPOINT_NORMAL_CONE'}
                else:
                    correction = max(0., observed['signed_ray_distance_cm']+domain['reserve_cm']/observed['cosine'])
                    within_displacement = correction <= domain['max_displacement_cm']
                    within_ray = abs(observed['signed_ray_distance_cm']) <= domain['max_displacement_cm']
                    measured['selected_plane_reserve'] = {'reserve_cm': domain['reserve_cm'],
                        **({'additional_directional_correction_cm': correction} if math.isfinite(correction) else {}),
                        'within_declared_displacement_budget': within_displacement,
                        'within_declared_ray_budget': within_ray,
                        'status': ('DIRECTIONAL_CORRECTION_NOT_REPRESENTABLE' if not math.isfinite(correction) else
                                   'DECLARED_DISPLACEMENT_BUDGET_EXCEEDED' if not within_displacement else
                                   'DECLARED_RAY_BUDGET_EXCEEDED' if not within_ray else
                                   'RESERVE_PRESERVED_AT_THIS_PLANE' if correction <= 1e-7 else 'ADDITIONAL_CORRECTION_REQUIRED')}
            observations.append(measured)
        batches.append({'domain_sha256': domain_id, 'policy': trace_policy, 'result': traced})
    if digest([data, frames, recipe, profile, geometry, anatomical_references, policy]) != before:
        raise StudioError('Current boundary inspection changed its exact source or candidate')
    unresolved = len(result['unresolved_anatomical_inputs'])
    refused = sum(row['continuation']['status'] != 'LOCAL_PATH_LIFT_REACHED' for row in observations)
    reserve_pending = sum(row['continuation']['status'] == 'LOCAL_PATH_LIFT_REACHED' and (
        row['selected_plane_reserve']['status'] != 'RESERVE_PRESERVED_AT_THIS_PLANE' or
        not row['selected_plane_reserve'].get('within_declared_displacement_budget', False) or
        not row['selected_plane_reserve'].get('within_declared_ray_budget', False)) for row in observations)
    result['current_surface_observations'] = {'method': continuation['method'],
        'policy_sha256': digest(policy), 'frames_sha256': digest(frames),
        'batches': batches, 'observations': observations,
        'unresolved_anatomical_inputs': unresolved, 'refused_paths': refused,
        'reserve_pending': reserve_pending, 'work_events': work,
        'timing': 'OMITTED_FOR_DETERMINISTIC_REPLAY',
        'scope': 'BOUNDARY_POINTS_ONLY', 'whole_body_segment_contact_admission': 'NOT_GRANTED',
        'qualification': 'NONE'}
    result['status'] = 'PARTIAL_BOUNDARY_CONTINUATION' if unresolved or refused or reserve_pending else 'CURRENT_BOUNDARY_POINTS_INSPECTED'
    budget.check()
    return result
