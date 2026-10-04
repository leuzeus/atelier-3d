"""Exact source sewing witnesses for quantized native boundary coordinates.

The caller authenticates the source piece, compiled links and native observation.
This pure helper only proves coordinates at explicitly paired sewing samples. It
does not search for a nearby contour point or qualify a garment for fitting.
"""
import math
import struct

from .core import StudioError, digest
from .sewing import chain_lengths, edge_chain, sample_chain


def _number(value):
    return type(value) in (int, float) and math.isfinite(value)


def _binary32(point):
    try:
        return [struct.unpack('f', struct.pack('f', value))[0] for value in point]
    except (OverflowError, struct.error) as error:
        raise StudioError('Source sewing UV exceeds the native binary32 domain') from error


def _index_list(value, count, label, *, unique=True):
    if not isinstance(value, list) or not value or any(
            type(index) is not int or not 0 <= index < count for index in value):
        raise StudioError('Invalid native source sewing ' + label)
    if unique and len(set(value)) != len(value):
        raise StudioError('Duplicate native source sewing ' + label)
    return value


def _panel(native, pid, count):
    panels = native.get('panels')
    panel = panels.get(pid) if isinstance(panels, dict) else None
    if not isinstance(panel, dict):
        raise StudioError('Source sewing witness requires its exact native panel: ' + pid)
    indices = _index_list(panel.get('indices'), count, 'panel indices')
    boundary = _index_list(panel.get('boundary'), count, 'boundary indices')
    if not set(boundary) <= set(indices) or not isinstance(panel.get('edges'), dict):
        raise StudioError('Native source sewing boundary is not owned by its panel')
    return panel, set(indices), set(boundary)


def _native_edge(panel, boundary, indices, name, count):
    edge = _index_list(panel['edges'].get(name), count, 'named edge: ' + str(name))
    if not set(edge) <= boundary or not set(edge) <= indices:
        raise StudioError('Native source sewing edge is not an owned boundary: ' + str(name))
    return edge


def _source_edge(piece, name):
    ids = piece['edges'].get(name)
    if not isinstance(name, str) or not isinstance(ids, list) or len(ids) < 2 or any(
            type(index) is not int or not 0 <= index < len(piece['vertices']) for index in ids):
        raise StudioError('Source sewing witness requires its original named edge')
    if len(set(ids)) != len(ids) and not (ids[0] == ids[-1] and
            len(set(ids[:-1])) == len(ids) - 1):
        raise StudioError('Source sewing witness edge repeats source vertices')
    n = len(piece['vertices'])
    if any((b - a) % n not in (1, n - 1) for a, b in zip(ids, ids[1:])):
        raise StudioError('Source sewing witness edge must follow consecutive original polygon vertices')
    return edge_chain(piece, name)


def _perimeter_witness(piece, source_ids, points, parameter, perimeter):
    """Reproduce the source sampler's semantic segment-to-perimeter identity.

    The segment comes from named source vertex IDs and arc length, never from a
    projection of a native point. The endpoint rule is the existing
    ``prepare_boundaries.put`` rule; the UV itself remains ``sample_chain``.
    """
    lengths = chain_lengths(points)
    target = parameter * lengths[-1]
    for offset, (a, b) in enumerate(zip(source_ids, source_ids[1:])):
        if target <= lengths[offset + 1] + 1e-8:
            fraction = min(1., max(0., (target - lengths[offset]) /
                                      (lengths[offset + 1] - lengths[offset])))
            n = len(piece['vertices'])
            index = a if (b - a) % n == 1 else b
            along = fraction if index == a else 1. - fraction
            position = (perimeter[index] + along *
                        (perimeter[index + 1] - perimeter[index])) % perimeter[-1]
            return position, [a, b], fraction
    raise StudioError('Source sewing witness has no semantic boundary segment')


def source_boundary_seam_witnesses(piece, pid, cid, native, links):
    """Return ``{native_index: {source_uv_cm, evidence}}`` for exact witnesses.

    Missing sewing observations produce an empty mapping. A present relation,
    parameter, native vertex or perimeter identity that contradicts the source
    raises ``StudioError``; it cannot silently fall back to rounded-key sampling.
    Inputs are not mutated. External source authentication belongs to the caller.
    """
    if not isinstance(native, dict):
        raise StudioError('Source sewing witness requires a native observation mapping')
    if 'seams' not in native or native['seams'] == {}:
        return {}
    if not isinstance(native['seams'], dict):
        raise StudioError('Invalid native source sewing witness relations')
    if not isinstance(pid, str) or not pid or not isinstance(cid, str) or not cid:
        raise StudioError('Source sewing witness requires explicit piece and component identities')
    if not isinstance(piece, dict) or not isinstance(piece.get('vertices'), list) or \
            len(piece['vertices']) < 3 or not isinstance(piece.get('edges'), dict):
        raise StudioError('Source sewing witness requires the original polygon and named edges')
    if any(not isinstance(point, list) or len(point) != 2 or
           any(not _number(value) for value in point) for point in piece['vertices']):
        raise StudioError('Source sewing witness polygon must contain finite material UV coordinates')
    perimeter = chain_lengths(piece['vertices'] + piece['vertices'][:1])
    if not math.isfinite(perimeter[-1]):
        raise StudioError('Source sewing witness perimeter is not finite')
    if not isinstance(native, dict) or native.get('component_id') != cid:
        raise StudioError('Source sewing witness component differs from its native observation')
    rest = native.get('rest_cm')
    if not isinstance(rest, list) or not rest:
        raise StudioError('Source sewing witness requires the actual native rest vertices')
    panel, indices, boundary = _panel(native, pid, len(rest))
    if panel.get('source_contour_sha256') != digest(piece['vertices']):
        raise StudioError('Source sewing witness contour differs from the native source contour')
    keys = panel.get('boundary_source_arclength_cm')
    if not isinstance(keys, list) or len(keys) != len(panel['boundary']) or any(
            not _number(key) or not 0 <= key < perimeter[-1] or round(key, 8) != key
            for key in keys) or len(set(keys)) != len(keys):
        raise StudioError('Source sewing witness requires unique exact rounded source perimeter keys')
    key_by_index = dict(zip(panel['boundary'], keys))
    seams = native.get('seams')
    if not isinstance(seams, dict) or not isinstance(links, list):
        raise StudioError('Source sewing witness requires native seams and compiled source links')
    if any(not isinstance(sid, str) or not isinstance(seam, dict) for sid, seam in seams.items()):
        raise StudioError('Invalid native source sewing witness relation')
    source_links = {}
    for link in links:
        if not isinstance(link, dict):
            raise StudioError('Invalid compiled source sewing witness link')
        if link.get('component_id') != cid:
            continue
        sid = link.get('source_link_id')
        if not isinstance(sid, str) or not sid or sid in source_links:
            raise StudioError('Source sewing witnesses require unique explicit source link identities')
        source_links[sid] = link
    witnesses = {}
    for sid, seam in sorted(seams.items()):
        if not isinstance(sid, str) or not isinstance(seam, dict):
            raise StudioError('Invalid native source sewing witness relation')
        link = source_links.get(sid)
        if pid not in (seam.get('piece_a'), seam.get('piece_b')) and \
                (not link or pid not in (link.get('piece_a'), link.get('piece_b'))):
            continue
        if not isinstance(link, dict) or any(seam.get(field) != link.get(field)
                for field in ('piece_a', 'piece_b', 'kind')) or \
                link.get('kind') not in ('permanent', 'closure', 'detachable') or \
                link.get('orientation') not in ('forward', 'reverse'):
            raise StudioError('Native sewing witness differs from its compiled source relation: ' + sid)
        parameters, pairs = seam.get('parameters'), seam.get('pairs')
        if not isinstance(parameters, list) or len(parameters) < 2 or any(
                not _number(value) or not 0 <= value <= 1 for value in parameters) or \
                parameters[0] != 0 or parameters[-1] != 1 or any(
                    a >= b for a, b in zip(parameters, parameters[1:])):
            raise StudioError('Source sewing witness parameters must uniquely cover [0,1]: ' + sid)
        if not isinstance(pairs, list) or len(pairs) != len(parameters) or any(
                not isinstance(pair, list) or len(pair) != 2 or any(
                    type(index) is not int or not 0 <= index < len(rest) for index in pair)
                for pair in pairs):
            raise StudioError('Native sewing witness pairs do not cover their source parameters: ' + sid)
        for side, column in (('a', 0), ('b', 1)):
            owner, name = link.get('piece_' + side), link.get('edge_' + side)
            if not isinstance(owner, str) or not owner or not isinstance(name, str) or not name:
                raise StudioError('Source sewing witness requires explicit side and named edge: ' + sid)
            peer, peer_indices, peer_boundary = _panel(native, owner, len(rest))
            edge = _native_edge(peer, peer_boundary, peer_indices, name, len(rest))
            paired = [pair[column] for pair in pairs]
            if set(paired) != set(edge):
                raise StudioError('Native sewing witness pairs must cover the exact named edge: ' + sid)
            expected = edge + edge[:1] if len(paired) == len(edge) + 1 and \
                paired[0] == paired[-1] else list(edge)
            if side == 'b' and link['orientation'] == 'reverse':
                expected.reverse()
            if paired != expected:
                raise StudioError('Native sewing witness order differs from the source edge orientation: ' + sid)
            if owner != pid:
                continue
            source_ids, points, _ = _source_edge(piece, name)
            for pair_index, (common_parameter, pair) in enumerate(zip(parameters, pairs)):
                index = pair[column]
                local_parameter = 1. - common_parameter if side == 'b' and \
                    link['orientation'] == 'reverse' else common_parameter
                source_uv = sample_chain(points, local_parameter)
                point = rest[index]
                if not isinstance(point, list) or len(point) != 3 or any(
                        not _number(value) for value in point):
                    raise StudioError('Native sewing witness requires a finite actual rest vertex')
                native_uv = point[:2]
                if native_uv != _binary32(native_uv) or native_uv != _binary32(source_uv):
                    raise StudioError('Native sewing UV differs from its exact source parameter binary32 round-trip')
                position, segment, fraction = _perimeter_witness(
                    piece, source_ids, points, local_parameter, perimeter)
                key = key_by_index[index]
                if round(position, 8) != key:
                    raise StudioError('Native sewing witness perimeter key differs from its exact source parameter')
                witness = {'source_link_id': sid, 'source_link_sha256': digest(link),
                    'side': side, 'edge': name, 'kind': link['kind'],
                    'orientation': link['orientation'], 'pair_index': pair_index,
                    'common_parameter': common_parameter, 'local_parameter': local_parameter,
                    'source_segment_vertex_ids': segment, 'source_segment_fraction': fraction}
                if 'source_ref' in link:
                    witness['source_ref'] = dict(link['source_ref']) if isinstance(link['source_ref'], dict) \
                        else link['source_ref']
                if index in witnesses:
                    previous = witnesses[index]
                    if previous['source_uv_cm'] != source_uv or \
                            previous['evidence']['source_perimeter_position_cm'] != position:
                        raise StudioError('Multiple source sewing witnesses disagree at the same native boundary vertex')
                    previous['evidence']['witnesses'].append(witness)
                else:
                    witnesses[index] = {'source_uv_cm': source_uv, 'evidence': {
                        'method': 'EXACT_NATIVE_SOURCE_SEAM_PARAMETER_WITNESS',
                        'piece': pid, 'component_id': cid, 'source_contour_sha256': digest(piece['vertices']),
                        'source_perimeter_key_cm': key, 'source_perimeter_position_cm': position,
                        'native_uv_cm': native_uv, 'binary32_round_trip': 'EXACT',
                        'perimeter_key_round_trip': 'EXACT', 'witnesses': [witness],
                        'source_cut_changed': False, 'native_mesh_changed': False,
                        'qualification': 'NONE', 'admissible_for_fit': False}}
    return witnesses
