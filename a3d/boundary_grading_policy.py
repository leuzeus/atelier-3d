"""Prepare explicit local grading controls from an attached source row.

This creates a policy, not a candidate or an anatomical/fitting decision.
Protected edges and numerical budgets are caller data, never inferred ease.
"""
import copy
import math

from .core import StudioError, contract, digest
from .garment_measurements import _span, _assembled_row_topology, _collar_neckline_row
from .sewing import edge_chain


def material_row_reference(compiled, component_id, piece, edge_from, edge_to, source_v_cm):
    """Source-bound row with permanent endpoint closure and full attachments."""
    owner = compiled['textiles'].get(piece)
    if type(source_v_cm) not in (int, float) or not math.isfinite(source_v_cm):
        raise StudioError('Material row height must be finite source data')
    if owner is None or owner['component_id'] != component_id:
        raise StudioError('Material reference must name an actual source component and piece')
    segment, span = _span(compiled, piece, edge_from, edge_to, source_v_cm)
    topology = _assembled_row_topology(compiled, segment)
    if topology['status'] != 'CLOSED_PERMANENT_ENDPOINT_CYCLE':
        raise StudioError('Local row policy requires an actual permanent source endpoint cycle')
    attachment = _collar_neckline_row(compiled, piece, source_v_cm, span['source_uv_cm'])
    return {'domain': 'PERMANENT_ENDPOINT_CYCLE', 'component_id': component_id,
        'piece': piece, 'source_geometry_sha256': digest(owner['source_geometry']),
        'source_v_cm': source_v_cm, 'segments': [segment],
        'source_material_length_cm': span['source_material_length_cm'],
        'topology': topology, 'attachment': attachment}


def prepare_local_row_policy(compiled, material_reference, design_decision_ref,
                             protected_edges_by_piece, scale_bounds, constraints, budgets,
                             *, weight_profile='SOURCE_VERTEX_BINARY'):
    """Build weighted source controls; no point placement or design admission.

    Partner vertices belonging to the attached row have weight one, except
    explicitly protected source edges. Other vertices have weight zero.
    The band accumulates expansion only on intervals with an active partner.
    This restricted family may be unable to meet a target; the solver must
    retain that refusal rather than relax protected geometry.
    """
    bounds = copy.deepcopy(scale_bounds)
    if weight_profile not in ('SOURCE_VERTEX_BINARY', 'SOURCE_ARC_QUADRATIC_TAPER'):
        raise StudioError('Local row needs an explicit supported source weight profile')
    if (set(bounds) != {'minimum', 'initial', 'maximum'} or
        any(type(v) not in (int, float) or not math.isfinite(v) or not .05 <= v <= 5
            for v in bounds.values()) or
        not bounds['minimum'] <= bounds['initial'] <= bounds['maximum']):
        raise StudioError('Local row parameter bounds must be explicit and finite')
    before = digest([compiled, material_reference, design_decision_ref,
                     protected_edges_by_piece, scale_bounds, constraints, budgets])
    ref = material_reference; pid = ref['piece']; cid = ref['component_id']
    segments = ref['segments']
    if len(segments) != 1 or segments[0]['piece'] != pid:
        raise StudioError('Local row policy needs one exact declared source span')
    segment = segments[0]
    actual = material_row_reference(compiled, cid, pid, segment['from']['edge'],
                                    segment['to']['edge'], ref['source_v_cm'])
    if actual != ref:
        raise StudioError('Local row policy material reference changed')
    piece = compiled['textiles'][pid]['source_geometry']
    attachments = ref['attachment']['permanent_source_attachments']
    neck_edges = {}; band_intervals = []
    for link in attachments:
        side = 'a' if link['piece_a'] == pid else 'b'; other = 'b' if side == 'a' else 'a'
        partner = link['piece_' + other]
        if partner == pid:
            raise StudioError('Local row controls do not support a self-attached source row')
        neck_edges.setdefault(partner, set()).add(link['edge_' + other])
        chain = edge_chain(piece, link['edge_' + side])[1]
        band_intervals.append((min(p[0] for p in chain), max(p[0] for p in chain), partner, link['edge_' + other]))
    participants = {pid, *neck_edges}
    if set(protected_edges_by_piece) != participants:
        raise StudioError('Local row protections must explicitly cover every participant')
    protected = {}; families = []; weights = {}
    for partner in sorted(participants):
        geometry = compiled['textiles'][partner]['source_geometry']
        names = protected_edges_by_piece[partner]
        if not isinstance(names, list) or len(names) != len(set(names)):
            raise StudioError('Protected edges must be unique declared source names')
        protected[partner] = {index for name in names for index in edge_chain(geometry, name)[0]}
        if partner == pid:
            continue
        active = {index for name in neck_edges[partner] for index in edge_chain(geometry, name)[0]}
        values = [1. if i in active and i not in protected[partner] else 0.
                  for i in range(len(geometry['vertices']))]
        if weight_profile == 'SOURCE_ARC_QUADRATIC_TAPER':
            adjacency = {i: set() for i in active}
            for name in sorted(neck_edges[partner]):
                indices = edge_chain(geometry, name)[0]
                for a, b in zip(indices, indices[1:]):
                    adjacency[a].add(b); adjacency[b].add(a)
            ends = sorted(i for i, neighbors in adjacency.items() if len(neighbors) == 1)
            if len(ends) != 2 or any(len(neighbors) not in (1, 2) for neighbors in adjacency.values()):
                raise StudioError('Source arc taper needs one unbranched attached partner path')
            chain = [ends[0]]; previous = None
            while chain[-1] != ends[1]:
                choices = adjacency[chain[-1]] - ({previous} if previous is not None else set())
                if len(choices) != 1:
                    raise StudioError('Source arc taper partner path is ambiguous')
                following = choices.pop()
                if following in chain:
                    raise StudioError('Source arc taper cannot substitute a cyclic partner path')
                previous = chain[-1]; chain.append(following)
            if set(chain) != active:
                raise StudioError('Source arc taper cannot omit disconnected partner material')
            lengths = [math.dist(geometry['vertices'][a], geometry['vertices'][b])
                       for a, b in zip(chain, chain[1:])]
            length = math.fsum(lengths)
            if not math.isfinite(length) or length <= 0 or any(v <= 0 for v in lengths):
                raise StudioError('Source arc taper requires noncollapsed finite material edges')
            for position, i in enumerate(chain):
                t = math.fsum(lengths[:position]) / length
                values[i] = 0. if i in protected[partner] else 4 * t * (1 - t)
        weights[partner] = values
        zero = [i for i, value in enumerate(values) if value == 0]
        if not zero:
            raise StudioError('Local partner controls need an unchanged source anchor')
        families.append({'id': 'local-row.' + partner, 'pieces': [partner], 'mode': 'WEIGHTED_SOURCE_UV',
            'anchor_vertices': {partner: zero[0]}, 'weights_by_piece': {partner: values},
            'protected_edges_by_piece': {partner: copy.deepcopy(names)},
            'scale_x': copy.deepcopy(bounds) if any(values) else {'minimum': 1., 'initial': 1., 'maximum': 1.},
            'scale_y': copy.deepcopy(bounds) if any(values) else {'minimum': 1., 'initial': 1., 'maximum': 1.}})
    active_intervals = []
    for lo, hi, partner, edge in sorted(band_intervals):
        indices = edge_chain(compiled['textiles'][partner]['source_geometry'], edge)[0]
        if any(weights[partner][i] > 0 for i in indices):
            active_intervals.append((lo, hi))
    if not active_intervals:
        raise StudioError('All attached row partners are protected; no local expansion is supported')
    ends = [span for span in ref['topology']['endpoints'] if span['piece'] == pid]
    anchor = min((end['source_vertex_id'] for end in ends), key=lambda i: piece['vertices'][i][0])
    origin = piece['vertices'][anchor][0]
    values = []
    for i, point in enumerate(piece['vertices']):
        u = point[0]
        progress = math.fsum(max(0., min(u, hi) - max(origin, lo)) for lo, hi in active_intervals)
        weight = 0. if u == origin else progress / (u - origin)
        if not 0 <= weight <= 1 or (i in protected[pid] and weight != 0):
            raise StudioError('Band interval controls conflict with explicit protected source geometry')
        values.append(weight)
    fixed = {'minimum': 1., 'initial': 1., 'maximum': 1.}
    families.append({'id': 'local-row.' + pid, 'pieces': [pid], 'mode': 'WEIGHTED_SOURCE_UV',
        'anchor_vertices': {pid: anchor}, 'weights_by_piece': {pid: values},
        'protected_edges_by_piece': {pid: copy.deepcopy(protected_edges_by_piece[pid])},
        'scale_x': copy.deepcopy(bounds), 'scale_y': fixed})
    policy = {'version': 1, 'compiled_sha256': digest(compiled),
        'design_decision_ref': copy.deepcopy(design_decision_ref),
        'body_ref': copy.deepcopy(compiled['assembly_spec']['body_ref']),
        'dossier_ref': copy.deepcopy(compiled['source_ref']), 'unlisted_pieces': 'PRESERVE_EXACT',
        'families': families, 'nominal_paths': [{'id': 'local-row.' + pid,
            'body_landmark': 'source-boundary.' + pid, 'component_id': cid,
            'layer': compiled['textiles'][pid]['semantics']['layer'],
            'path_kind': 'open_material_span', 'segments': copy.deepcopy(segments),
            'joins': [], 'engaged_links': [], 'takeup': [], 'objective': 'TARGET',
            'path_parameterization': 'SOURCE_V_CM', 'source_v_cm': ref['source_v_cm']}],
        'constraints': copy.deepcopy(constraints), 'budgets': copy.deepcopy(budgets),
        'notch_policy': 'PRESERVE_MATERIAL_POINTS'}
    contract('pattern-ease-variant', policy)
    if digest([compiled, material_reference, design_decision_ref, protected_edges_by_piece,
               scale_bounds, constraints, budgets]) != before:
        raise StudioError('Local row controls changed immutable inputs')
    return policy
