"""Read-only source audit and metric preparation of derived sewing geometry.

All lengths are centimetres. No source repair, triangulator, Blender operation,
physical qualification or artistic acceptance is hidden in these functions.
"""
import copy
import math
from fractions import Fraction

from .core import StudioError, contract, digest
from .board_contract import assembly_mark_position
from .cloth_metrics import (METRIC_VERSION, VALIDATOR_VERSION, METRIC_SCOPE,
    face_sources, evaluate_metrics, distribution as _distribution)
from .sewing import (chain_lengths, edge_chain, point_inside, prepare_boundaries,
                     sample_chain, segment_distance, seam_report, signed_area)


def _issue(code, message, category, **location):
    return {'code': code, 'message': message, 'category': category, **location}


def _inversion_invariant_notch(position):
    """The board's side-free self-seam mark denotes both edges only at a fixed point."""
    return (type(position) in (int, float) and math.isfinite(position)
            and position == .5)


def audit_source(data, recipe, dossier=None):
    """Audit garment geometry plus the separately approved cutting dossier.

    Garment v1 contains no grain or notch metadata; absence is reported, never
    repaired by inventing it. Named seam endpoints provide geometric stops.
    """
    before = digest(data)
    issues, panels, seams = [], {}, []
    try:
        contract('garment', data)
    except StudioError as error:
        issues.append(_issue('SOURCE_CONTRACT', str(error), 'source_contract'))
        return {'version': 1, 'status': 'NEEDS_CORRECTION', 'source_sha256': before,
            'issues': issues, 'panels': panels, 'seams': seams, 'accepted': False,
            'source_immutable': digest(data) == before, 'qualification': 'NONE'}
    from .board_contract import simple_polygon
    infos = {} if dossier is None else {
        item['id']: item for item in dossier.get('components', {}).get(data['component_id'], {}).get('pieces', [])}
    if dossier is None:
        issues.append(_issue('CUTTING_DOSSIER_MISSING',
            'Approved grain, cutting outline and paired notches need their source dossier', 'missing_metadata'))
    elif dossier.get('units') != 'cm':
        issues.append(_issue('DOSSIER_UNITS', 'Cutting dossier must declare the same metric centimetre units', 'source_contract'))
    for pid, piece in data['pieces'].items():
        polygon = piece['vertices']
        signed = signed_area(polygon)
        area = abs(signed)
        occurrences = {}
        for index, point in enumerate(polygon):
            occurrences.setdefault(tuple(point), []).append(index)
        duplicate_groups = [ids for ids in occurrences.values() if len(ids) > 1]
        simple = simple_polygon(polygon)
        if not simple or area < 1e-8:
            issues.append(_issue('INVALID_SOURCE_CONTOUR', 'Source contour intersects itself or is degenerate',
                                 'demonstrated_source_defect', piece=pid))
        lengths = [math.dist(a, b) for a, b in zip(polygon, polygon[1:]+polygon[:1])]
        if min(lengths) < 1e-8:
            issues.append(_issue('DUPLICATE_SOURCE_VERTEX', 'Consecutive source boundary vertices collapse',
                                 'demonstrated_source_defect', piece=pid))
        edge_reports = {}
        for name in piece['edges']:
            try:
                ids, points, sign = edge_chain(piece, name)
                length = chain_lengths(points)[-1]
                edge_reports[name] = {'source_indices': list(ids), 'length_cm': length,
                    'boundary_direction': sign, 'geometric_stops_uv_cm': [list(points[0]), list(points[-1])]}
            except (StudioError, IndexError) as error:
                issues.append(_issue('INVALID_NAMED_EDGE', str(error), 'source_contract', piece=pid, edge=name))
        info = infos.get(pid)
        grain = None
        if dossier is not None and info is None:
            issues.append(_issue('PANEL_METADATA_MISSING', 'Source panel has no cutting dossier entry', 'missing_metadata', piece=pid))
        if info is not None:
            grain = info.get('grain_direction')
            if not isinstance(grain, list) or len(grain) != 2 or any(type(x) not in (int, float) or not math.isfinite(x) for x in grain) or math.hypot(*grain) < 1e-9:
                issues.append(_issue('GRAIN_MISSING_OR_INVALID', 'Panel grain must be explicitly sourced and nonzero', 'missing_metadata', piece=pid))
            pattern = info.get('pattern', {})
            cut = pattern.get('cut_outline_cm')
            if not cut:
                issues.append(_issue('CUT_OUTLINE_MISSING', 'Approved cut outline is absent', 'missing_metadata', piece=pid))
            elif not simple_polygon(cut):
                issues.append(_issue('INVALID_CUT_OUTLINE', 'Approved cut outline is not a simple polygon', 'demonstrated_source_defect', piece=pid))
            else:
                from .board_contract import inside_polygon
                # A sampled containment audit follows the existing manufacturing
                # contract; it is deliberately not labelled an exact polygon proof.
                samples = [[a[k]+t/20*(b[k]-a[k]) for k in range(2)]
                           for a, b in zip(polygon, polygon[1:]+polygon[:1]) for t in range(21)]
                if any(not inside_polygon(p, cut) for p in samples):
                    issues.append(_issue('CUT_DOES_NOT_CONTAIN_SEWING_CONTOUR',
                        'Cut outline does not contain the sewing contour at a measured sample',
                        'demonstrated_source_defect', piece=pid))
                allowance = info.get('seam_allowance_cm')
                if type(allowance) not in (int, float) or not math.isfinite(allowance) or allowance < 0:
                    issues.append(_issue('ALLOWANCE_MISSING_OR_INVALID', 'Declared seam allowance is absent or invalid', 'missing_metadata', piece=pid))
                else:
                    clearance = min(segment_distance(p, a, b) for p in samples for a, b in zip(cut, cut[1:]+cut[:1]))
                    if clearance+.05 < allowance:
                        issues.append(_issue('CUT_ALLOWANCE_CONFLICT', 'Measured cut margin is less than the declared source allowance',
                            'demonstrated_source_defect', piece=pid, measured_cm=clearance, declared_cm=allowance))
        bbox = [[min(p[k] for p in polygon) for k in range(2)], [max(p[k] for p in polygon) for k in range(2)]]
        panels[pid] = {'area_cm2': area, 'signed_area_cm2': signed,
            'winding': 'CCW' if signed > 0 else 'CW' if signed < 0 else 'DEGENERATE',
            'source_bbox_cm': bbox, 'source_dimensions_cm': [bbox[1][k]-bbox[0][k] for k in range(2)],
            'duplicate_source_coordinate_groups': duplicate_groups,
            'nonconsecutive_duplicate_pairs': [[a, b] for ids in duplicate_groups for a in ids for b in ids
                if a < b and b-a not in (1, len(polygon)-1)],
            'perimeter_cm': sum(lengths), 'source_vertex_count': len(polygon),
            'source_contour_sha256': digest(polygon), 'simple_contour': simple,
            'source_segment_min_cm': min(lengths), 'source_segment_max_cm': max(lengths),
            'grain_direction': copy.deepcopy(grain), 'named_edges': edge_reports}
    declared = recipe.get('seams', {})
    source_ids = [s['id'] for s in data['seams']]
    if len(set(source_ids)) != len(source_ids):
        issues.append(_issue('DUPLICATE_SEAM_ID', 'Seam IDs must be unique', 'source_contract'))
    if set(declared) != set(source_ids):
        issues.append(_issue('SEAM_DECLARATION_INCOMPLETE', 'Every seam needs an explicit kind and ease declaration', 'missing_metadata'))
    for seam in data['seams']:
        sid = seam['id']; declaration = declared.get(sid)
        if declaration is None:
            continue
        try:
            left_ids, left, _ = edge_chain(data['pieces'][seam['piece_a']], seam['edge_a'])
            right_ids, right, _ = edge_chain(data['pieces'][seam['piece_b']], seam['edge_b'])
            a, b = chain_lengths(left)[-1], chain_lengths(right)[-1]
            ease = declaration.get('ease_b_over_a')
            tolerance = declaration.get('tolerance_relative')
            if type(ease) not in (int, float) or type(tolerance) not in (int, float) or not math.isfinite(ease) or not math.isfinite(tolerance) or tolerance < 0 or ease <= -1:
                raise StudioError('Missing explicit ease and length tolerance')
            if declaration.get('kind') not in ('permanent', 'closure', 'detachable'):
                raise StudioError('Every source seam needs a supported explicit permanent/closure/detachable kind')
            residual = abs(b/a-(1+ease))
            if residual > tolerance+1e-8:
                issues.append(_issue('SEAM_LENGTH_OR_EASE_CONFLICT',
                    'Measured seam lengths disagree with the declared ease; do not infer a cutting defect before review',
                    'cut_or_assembly_spec_conflict', seam_id=sid, residual_relative=residual, tolerance_relative=tolerance))
            if seam.get('kind', declaration.get('kind')) != declaration.get('kind'):
                issues.append(_issue('SEAM_KIND_CHANGED', 'Recipe retypes an immutable declared source seam', 'source_contract', seam_id=sid))
            report = {'id': sid, 'kind': declaration.get('kind'), 'orientation': seam['orientation'],
                'length_a_cm': a, 'length_b_cm': b, 'ease_b_over_a': ease, 'residual_relative': residual,
                'stops_source': 'named_source_edge_endpoints', 'stops_a_uv_cm': [left[0], left[-1]],
                'stops_b_uv_cm': [right[-1], right[0]] if seam['orientation'] == 'reverse' else [right[0], right[-1]],
                'notches': []}
            if dossier is not None and seam['piece_a'] in infos and seam['piece_b'] in infos:
                marks = []
                for side in ('a', 'b'):
                    entries = [m for m in infos[seam['piece_'+side]].get('pattern', {}).get('assembly_marks', []) if m.get('seam_id') == sid]
                    if len({m.get('id') for m in entries}) != len(entries):
                        issues.append(_issue('DUPLICATE_NOTCH_ID', 'Seam has duplicate notch identifiers', 'source_contract', seam_id=sid))
                    marks.append({m.get('id'): m for m in entries})
                if (seam['piece_a'] == seam['piece_b'] and seam['orientation'] == 'reverse'
                        and any('seam_side_positions'not in m and not _inversion_invariant_notch(m.get('position')) for m in marks[0].values())):
                    issues.append(_issue('SELF_SEAM_NOTCH_SIDE_UNSPECIFIED',
                        'The source mark format does not identify which edge of this self-seam carries each notch',
                        'missing_metadata', seam_id=sid, piece=seam['piece_a']))
                elif not marks[0] or marks[0].keys() != marks[1].keys():
                    issues.append(_issue('PAIRED_NOTCHES_MISSING', 'Each source seam requires paired identified notches', 'missing_metadata', seam_id=sid))
                else:
                    for mid, mark in marks[0].items():
                        other = marks[1][mid]
                        ta, tb = assembly_mark_position(mark,seam,'a'), assembly_mark_position(other,seam,'b')
                        valid = type(ta) in (int, float) and type(tb) in (int, float) and 0 <= ta <= 1 and 0 <= tb <= 1
                        expected = 1-ta if valid and seam['orientation'] == 'reverse' else ta
                        if (not valid or abs(tb-expected) > 1e-6
                                or mark.get('symbol') not in ('notch', 'double-notch')
                                or mark.get('symbol') != other.get('symbol')):
                            issues.append(_issue('NOTCH_ORIENTATION_CONFLICT', 'Paired notch parameters disagree with source seam orientation', 'source_contract', seam_id=sid, notch_id=mid))
                        report['notches'].append({'id': mid, 'a': ta, 'b': tb, 'symbol': mark.get('symbol')})
            seams.append(report)
        except (StudioError, KeyError, IndexError, ZeroDivisionError) as error:
            issues.append(_issue('SEAM_SOURCE_BINDING', str(error), 'source_contract', seam_id=sid))
    try:
        _, flips = seam_report(data, recipe)
    except (StudioError, KeyError, IndexError) as error:
        flips = None
        issues.append(_issue('SOURCE_SEAM_GRAPH', str(error), 'source_contract'))
    errors = [i for i in issues if i['category'] != 'missing_metadata']
    status = 'NEEDS_CORRECTION' if errors else 'NEEDS_CLARIFICATION' if issues else 'SOURCE_AUDITED'
    return {'version': 1, 'status': status, 'source_sha256': before,
        'dossier_sha256': digest(dossier) if dossier is not None else None,
        'units': data['units'], 'panels': panels, 'seams': seams, 'panel_orientation_flips': flips,
        'issues': issues, 'accepted': False, 'source_immutable': digest(data) == before,
        'qualification': 'NONE', 'cut_containment_method': 'source_boundary_samples_20_per_segment',
        'seam_stop_scope': 'geometric_source_endpoints_not_invented_backtack_instructions'}


def _mesh_config(config):
    required = ('spacing_cm', 'min_spacing_cm', 'refinement_distance_cm', 'max_vertices')
    if any(key not in config for key in required):
        raise StudioError('Regular mesh needs spacing, minimum spacing, refinement distance and vertex budget')
    h, fine, band, maximum = (config[k] for k in required)
    if any(type(v) not in (int, float) or not math.isfinite(v) for v in (h, fine, band)) or not 0 < fine <= h or band < 0 or type(maximum) is not int or maximum < 3:
        raise StudioError('Invalid regular mesh metric budget')
    return h, fine, band, maximum


def _contour_parameter_requirements(points, parameters, error):
    lengths = chain_lengths(points)
    required = set()
    for lo, hi in zip(parameters, parameters[1:]):
        a, b = sample_chain(points, lo), sample_chain(points, hi)
        candidates = [(segment_distance(point,a,b),value/lengths[-1])
            for point,value in zip(points,lengths) if lo < value/lengths[-1] < hi]
        if candidates:
            deviation,t = max(candidates)
            if deviation > error+1e-9:
                required.add(t)
    return required


def _source_corner_indices(points):
    """Identify exact source turns without an angle or distance threshold.

    Source coordinates define the polygon. An exact determinant over those
    binary-float values distinguishes a turn from a straight subdivision;
    there is no angle or distance threshold that can remove a shallow corner.
    Named physical stops are protected by the common sampler. Material notches
    receive source-bound references separately, without forcing a cloth vertex.
    """
    turns = set()
    for index, (a, b, c) in enumerate(zip(points, points[1:], points[2:]), 1):
        first = [Fraction(b[k]) - Fraction(a[k]) for k in range(2)]
        second = [Fraction(c[k]) - Fraction(b[k]) for k in range(2)]
        if first[0] * second[1] != first[1] * second[0] or \
                sum(x * y for x, y in zip(first, second)) <= 0:
            turns.add(index)
    return turns


def _source_corner_parameters(points):
    lengths = chain_lengths(points)
    return {lengths[index] / lengths[-1] for index in _source_corner_indices(points)}


def _verify_prepared_source_corners(data, boundaries):
    """Refuse a lost or conflicting mandatory corner; never repair its output."""
    bindings = {}
    for pid, piece in data['pieces'].items():
        points = piece['vertices'] + piece['vertices'][:1]
        lengths = chain_lengths(points)
        corners = sorted({0} | _source_corner_indices(points))
        boundary = boundaries[pid]
        lookup = {key: index for index, key in enumerate(boundary['keys'])}
        used, rows = set(), []
        for source_index in corners:
            key = round(lengths[source_index], 8)
            if key in used or key not in lookup:
                raise StudioError('Source corners exceed boundary key precision or a mandatory corner was omitted: ' + pid)
            used.add(key)
            derived_index = lookup[key]
            if boundary['polygon'][derived_index] != piece['vertices'][source_index]:
                raise StudioError('Prepared mandatory corner differs from its exact original source vertex: ' + pid)
            rows.append({'source_vertex': source_index, 'derived_boundary_vertex': derived_index,
                         'source_perimeter_key_cm': key})
        bindings[pid] = rows
    return bindings


def regular_chain_parameters(points, sampled, spacing, error):
    """Remove optional rim-grid points while preserving every source turn."""
    lengths = chain_lengths(points)
    count = max(1,math.ceil(lengths[-1]/spacing))
    grid = {i/count for i in range(count+1)}
    required = set(sampled)-grid | {0.,1.}
    required.update(_source_corner_parameters(points))
    required.update(t for t in sampled if any(abs(t-s/lengths[-1])<1e-14 for s in lengths))
    while True:
        selected = set(required)
        for t in sorted(set(sampled)-required):
            if min(abs(t-other)*lengths[-1] for other in selected) >= spacing/2-1e-8:
                selected.add(t)
        result = sorted(selected)
        missing = _contour_parameter_requirements(points,result,error)-required
        if not missing:
            return result
        required.update(missing)


def regular_shared_parameters(pieces, chains, sampled, required, spacing, error):
    """Prune optional grid seeds together across their source arc graph.

    Named stops, every real source corner and explicitly required physical
    parameters are protected. Closely spaced required samples are reported and
    retained; they are never snapped or merged to satisfy a density target.
    """
    from .shared_seam_sampling import shared_parameters
    if type(spacing) not in (float,int) or not math.isfinite(spacing) or spacing<=0:
        raise StudioError('Regular boundary sampling needs a positive metric spacing')
    source_curves = {sid:[ [pieces[pid]['vertices'][i] for i in chain] for pid,chain in partners]
                     for sid,partners in chains.items()}
    lengths = {sid:min(chain_lengths(points)[-1] for points in curves) for sid,curves in source_curves.items()}
    required = {sid:set(values) for sid,values in required.items()}
    source_corners = {sid:set().union(*(_source_corner_parameters(points) for points in curves))
                      for sid,curves in source_curves.items()}
    for sid, values in source_corners.items():
        required[sid].update(values)
    candidates = [(sid,t) for sid in sorted(sampled) for t in sorted(sampled[sid])]
    removed = []
    while True:
        selected = shared_parameters(pieces,chains,required)
        protected = {sid:set(values) for sid,values in selected.items()}
        removed = []
        for sid,t in candidates:
            if t in selected[sid]:
                continue
            seed = {key:list(values) for key,values in selected.items()}
            seed[sid].append(t)
            proposal = shared_parameters(pieces,chains,seed)
            conflict = False
            for key,values in proposal.items():
                old = set(selected[key])
                added = set(values)-old
                for value in added:
                    if any(1e-7 < abs(value-other)*lengths[key] < spacing/2-1e-8
                           for other in values if other!=value):
                        conflict = True
                        break
                if conflict:
                    break
            if conflict:
                removed.append({'seam_id':sid,'common_parameter':t})
            else:
                selected = proposal
        missing = {sid:set() for sid in chains}
        for sid,curves in source_curves.items():
            for points in curves:
                missing[sid].update(_contour_parameter_requirements(points,selected[sid],error))
            missing[sid].difference_update(protected[sid])
        if not any(missing.values()):
            break
        for sid,values in missing.items():
            required[sid].update(values)
    near = []
    for sid,values in protected.items():
        values=sorted(values)
        for a,b in zip(values,values[1:]):
            gap=(b-a)*lengths[sid]
            if 1e-7 < gap < spacing/2-1e-8:
                near.append({'seam_id':sid,'parameters':[a,b],'minimum_partner_arc_gap_cm':gap})
    return selected, {'version':1,'policy':'REMOVE_OPTIONAL_GRID_SEEDS_ON_BOTH_PARTNERS',
        'minimum_optional_arc_gap_cm':spacing/2,'max_source_contour_error_cm':error,
        'source_corner_policy':'PRESERVE_EVERY_EXACT_SOURCE_TURN_BEFORE_PRUNING',
        'source_corner_parameters':{sid:sorted(values) for sid,values in source_corners.items()},
        'protected_parameters':{sid:sorted(values) for sid,values in protected.items()},
        'removed_optional_seeds':removed,'close_required_parameters_preserved':near,
        'source_vertices_moved':False,'source_seam_correspondence_changed':False}


def _bind_source_notch(data, boundaries, seams, notch):
    """Bind an exact authored material mark to existing physical boundary IDs.

    The immutable UV is its identity. Numerical reconstruction of an arc mark
    is reported separately; no residual is a tolerance or admission gate.
    """
    source = next(row for row in data['seams'] if row['id']==notch['seam_id'])
    side, pid = notch['side'], notch['piece']
    if side not in ('a','b') or pid!=source['piece_'+side]:
        raise StudioError('Source notch binding has the wrong source seam owner')
    mark = notch['source_mark']
    if (mark['id']!=notch['notch_id'] or mark['seam_id']!=source['id']
            or mark.get('symbol')!=notch['symbol']
            or assembly_mark_position(mark,source,side)!=notch['source_local_parameter']):
        raise StudioError('Source notch binding differs from its declared material mark')
    chain, points, _ = edge_chain(data['pieces'][pid], source['edge_'+side])
    position = notch['source_local_parameter']
    lengths = chain_lengths(points)
    source_vertex = next((index for index, stop in zip(chain, lengths)
                          if position==stop/lengths[-1]), None)
    source_uv = sample_chain(points, position)
    seam, boundary = seams[notch['seam_id']], boundaries[pid]
    parameters, indices = seam['parameters'], seam[side]
    reverse = side=='b' and source['orientation']=='reverse'
    common = 1-position if reverse else position
    provenance = boundary['sample_provenance']
    vertex_matches = []
    for sample, (parameter, index) in enumerate(zip(parameters, indices)):
        local_parameter = 1-parameter if reverse else parameter
        identity = provenance[index]
        exact_vertex = source_vertex is not None and identity['kind']=='SOURCE_VERTEX' and identity['source_vertex']==source_vertex
        if boundary['polygon'][index]==source_uv and (local_parameter==position or exact_vertex):
            vertex_matches.append((local_parameter!=position, sample, index))
    base = {'source_edge':source['edge_'+side], 'source_chain':list(chain),
            'source_chain_sha256':digest(points), 'source_uv_cm':source_uv,
            'source_vertex':source_vertex, 'common_parameter':common}
    def finish(result):
        # A completed row can be checked by rederiving it; stored weights,
        # source identity and UV are never accepted as independent claims.
        if result['binding']['kind']=='BOUNDARY_SEGMENT' and any(
                key in notch for key in ('common_sample','derived_boundary_vertex')):
            raise StudioError('A material segment notch cannot claim a physical common sample or vertex')
        if any(key in notch and notch[key]!=value for key,value in result.items()):
            raise StudioError('Stored source notch binding differs from its exact source derivation')
        return result
    if vertex_matches:
        if len({index for _,_,index in vertex_matches})!=1:
            raise StudioError('Source notch has ambiguous physical vertex identities')
        _, sample, index = min(vertex_matches)
        base.update(common_sample=sample, derived_boundary_vertex=index,
            binding={'kind':'BOUNDARY_VERTEX','index_space':'PIECE_BOUNDARY_LOCAL',
                     'boundary_vertex':index,'physical_common_parameter':parameters[sample]},
            reconstructed_uv_cm=list(boundary['polygon'][index]),
            numeric_reconstruction_residual_cm=0.)
        return finish(base)
    bracket = next((i for i,(lo,hi) in enumerate(zip(parameters,parameters[1:]))
                    if lo<=common<=hi), None)
    if bracket is None:
        raise StudioError('Source notch is outside its prepared source seam boundary')
    lo, hi = parameters[bracket:bracket+2]
    endpoints = indices[bracket:bracket+2]
    if hi<=lo or len(set(endpoints))!=2:
        raise StudioError('Source notch needs a nondegenerate physical boundary interval')
    weights = [(hi-common)/(hi-lo), (common-lo)/(hi-lo)]
    if any(not math.isfinite(weight) or not 0<=weight<=1 for weight in weights):
        raise StudioError('Source notch has invalid source arc interpolation weights')
    reconstructed = [sum(weight*boundary['polygon'][index][axis]
                         for weight,index in zip(weights,endpoints)) for axis in range(2)]
    base.update(binding={'kind':'BOUNDARY_SEGMENT','index_space':'PIECE_BOUNDARY_LOCAL',
        'boundary_vertices':endpoints,'physical_common_parameters':[lo,hi],
        'weights':weights,'parameter_scope':'ORIENTED_SOURCE_SEAM_ARCLENGTH'},
        reconstructed_uv_cm=reconstructed,
        numeric_reconstruction_residual_cm=math.dist(source_uv,reconstructed))
    return finish(base)


def _notch_physical_identity(notch):
    binding = notch['binding']
    if binding['kind']=='BOUNDARY_VERTEX':return ((binding['boundary_vertex'],1.),)
    return tuple(sorted((index,weight) for index,weight in zip(
        binding['boundary_vertices'],binding['weights']) if weight!=0.))


def prepare_regular_boundaries(data, recipe, regular_mesh, dossier=None, *,
                               meshing_envelope=None, transport_2d=None):
    """Same source IDs/shared arc sampler, explicitly rebuilt at rim resolution."""
    if (meshing_envelope is None)!=(transport_2d is None):
        raise StudioError('Synchronized boundary preparation requires both envelope and native transport')
    if meshing_envelope is not None:meshing_envelope.check('before_regular_boundary_capture')
    _, fine, _, maximum = _mesh_config(regular_mesh)
    derived = copy.deepcopy(recipe)
    derived['mesh']['spacing_cm'] = fine
    derived['mesh']['max_vertices'] = min(maximum, derived['mesh']['max_vertices'])
    notch_sources, ambiguous_notches, seen_notches = [], [], set()
    seam_by_id = {s['id']: s for s in data['seams']}
    infos = [] if dossier is None else dossier.get('components', {}).get(data['component_id'], {}).get('pieces', [])
    for info in infos:
        pid = info['id']
        for mark in info.get('pattern', {}).get('assembly_marks', []):
            seam = seam_by_id.get(mark.get('seam_id'))
            if seam is None or pid not in (seam['piece_a'], seam['piece_b']):
                raise StudioError('Source notch must reference its own declared seam and panel')
            identity = (pid,seam['id'],mark['id'])
            if identity in seen_notches:
                raise StudioError('Source notch identities must be unique within their panel and seam')
            seen_notches.add(identity)
            position = assembly_mark_position(mark,seam,'a'if seam['piece_a']==pid else'b')
            if (seam['piece_a'] == seam['piece_b'] and seam['orientation'] == 'reverse'
                    and 'seam_side_positions'not in mark and not _inversion_invariant_notch(position)):
                ambiguous_notches.append({'seam_id': seam['id'], 'notch_id': mark['id'], 'piece': pid,
                    'reason': 'source_mark_has_no_self_seam_side', 'requires_clarification': True})
                continue
            # These are material positions on the original source arcs. They do
            # not add required physical samples to the cloth boundary.
            sides = [side for side in ('a', 'b') if seam['piece_'+side] == pid]
            for side in sides:
                position=assembly_mark_position(mark,seam,side)
                notch_sources.append({'seam_id': seam['id'], 'notch_id': mark['id'],
                    'piece': pid, 'side': side, 'source_local_parameter': position,
                    'symbol':mark.get('symbol'), 'source_mark':copy.deepcopy(mark)})
    if meshing_envelope is not None:
        from .boundary_gradation import _sampling_cost
        meshing_envelope.reserve('sampling_calls',1)
        meshing_envelope.reserve('sampling_point_slots',derived['mesh']['max_vertices'])
        _sampling_cost(data,derived,{},meshing_envelope,
            lambda:meshing_envelope.check('baseline_sampling_cost'))
        meshing_envelope.check('before_baseline_sampling')
    boundaries, seams, seam_reports = prepare_boundaries(data, derived,
        regular_boundary_spacing_cm=fine)
    gradation=None
    if meshing_envelope is not None:
        from .boundary_gradation import grade_shared_boundaries
        meshing_envelope.check('after_baseline_sampling')
        normalized=copy.deepcopy(regular_mesh);normalized.setdefault('target_min_angle_degrees',15.)
        boundaries,seams,gradation=grade_shared_boundaries(data,derived,normalized,
            boundaries,seams,transport_2d=transport_2d,envelope=meshing_envelope)
        seam_reports=gradation['seam_reports']
    source_corner_bindings = _verify_prepared_source_corners(data, boundaries)
    for notch in notch_sources:
        notch.update(_bind_source_notch(data,boundaries,seams,notch))
    paired_self_notches = {}
    for notch in notch_sources:
        source = seam_by_id[notch['seam_id']]
        if source['piece_a'] == source['piece_b']:
            key = (notch['seam_id'], notch['notch_id'])
            paired_self_notches.setdefault(key, {})[notch['side']] = _notch_physical_identity(notch)
    if any(set(pair) != {'a', 'b'} or pair['a'] == pair['b'] for pair in paired_self_notches.values()):
        raise StudioError('Self-seam paired notches require distinct source-bound boundary references')
    count = sum(len(p['polygon']) for p in boundaries.values())
    if count > maximum:
        raise StudioError('Shared source boundary samples exceed the preparation vertex budget')
    result={'version': 1, 'source_sha256': digest(data),
        'sampling': 'existing_common_source_arclength', 'boundary_spacing_cm': fine,
        'boundary_vertices': count, 'seams': seam_reports, 'source_immutable': True,
        'boundary_sampling_policy':next(iter(boundaries.values())).get('regular_sampling_report'),
        'source_corner_bindings':source_corner_bindings,
        'source_notch_binding_version':1,
        'source_notch_policy':'MATERIAL_REFERENCE_WITHOUT_REQUIRED_PHYSICAL_VERTEX',
        'notch_index_space':'PIECE_BOUNDARY_LOCAL',
        'dossier_sha256': digest(dossier) if dossier is not None else None,
        'source_notches': notch_sources, 'ambiguous_source_notches': ambiguous_notches}
    if meshing_envelope is not None:
        result['source_boundary_gradation']=gradation
        meshing_envelope.check('after_source_corner_and_notch_rebinding')
    return boundaries,seams,result


def regular_interior_points(boundary, mesh_config, *, meshing_envelope=None):
    """Nested triangular lattices with a graded source-boundary refinement band.

    Returned points are interior seeds only: constrained Delaunay in Blender
    retains all common seam/boundary samples and supplies the triangulation.
    """
    spacing, fine, band, maximum = _mesh_config(mesh_config)
    identity = digest([boundary, mesh_config]) if meshing_envelope is not None else None
    def check(phase):
        if meshing_envelope is not None:
            meshing_envelope.check('regular_grid:'+phase)
    check('before_source_validation')
    owner = None
    if meshing_envelope is not None:
        owner = boundary.get('piece_id')
        if type(owner) is not str or owner not in meshing_envelope.material_controls:
            raise StudioError('Bounded interior grid requires its reserved source owner')
    def source_work(count):
        check('source_validation')
        meshing_envelope.reserve('work_steps',count,owner=owner)
    polygon = boundary['polygon']
    if len(polygon) < 3:
        raise StudioError('Regular mesh requires a nondegenerate source polygon')
    from .board_contract import simple_polygon
    if not (simple_polygon(polygon) if meshing_envelope is None else
            simple_polygon(polygon,work=source_work)):
        raise StudioError('Regular mesh cannot repair a non-simple source boundary')
    check('after_source_validation')
    xmin, xmax = min(p[0] for p in polygon), max(p[0] for p in polygon)
    ymin, ymax = min(p[1] for p in polygon), max(p[1] for p in polygon)
    dy = fine*math.sqrt(3)/2
    nx, ny = math.ceil((xmax-xmin)/fine)+2, math.ceil((ymax-ymin)/dy)+2
    if nx*ny > maximum*64:
        raise StudioError('Adaptive lattice candidate count exceeds the bounded preparation budget')
    segments = list(zip(polygon, polygon[1:]+polygon[:1]))
    queries = None
    if meshing_envelope is not None:
        from .interior_grid_queries import InteriorGridQueries
        queries = InteriorGridQueries(polygon,
            check=lambda:check('source_query'),
            reserve=lambda count:meshing_envelope.reserve('work_steps',count,owner=owner))
    max_level = max(0, int(math.floor(math.log2(spacing/fine)+1e-10)))
    points, levels, considered = [], {}, 0
    # Bound each row by x rather than following the skew lattice outside the bbox.
    for row in range(ny):
        check('row')
        y = ymin+row*dy
        if y > ymax:
            continue
        first = math.ceil(-row/2)
        for col in range(first, first+nx):
            x = xmin+(col+row/2)*fine
            if x > xmax:
                continue
            considered += 1
            check('candidate')
            p = [x, y]
            if not (queries.contains(p) if queries is not None else point_inside(p, polygon)):
                continue
            distance = (queries.distance(p) if queries is not None else
                        min(segment_distance(p, a, b) for a, b in segments))
            level = min(max_level, max(0, int(math.floor(math.log2(max(1., 1+(distance-band)/fine))))))
            step = 2**level
            if row % step or col % step or distance < .38*fine*step:
                continue
            points.append(p)
            levels[level] = levels.get(level, 0)+1
            if len(points)+len(polygon) > maximum:
                raise StudioError('Regular interior seeds exceed the preparation vertex budget')
    check('before_return')
    if identity is not None and digest([boundary,mesh_config])!=identity:
        raise StudioError('Bounded interior grid changed its immutable source or policy')
    report = {'version': 1, 'algorithm': 'nested_triangular_lattice_boundary_grading',
        'boundary_sha256': digest(polygon), 'requested_spacing_cm': spacing,
        'fine_spacing_cm': fine, 'coarse_spacing_cm': fine*2**max_level,
        'refinement_distance_cm': band, 'interior_vertices': len(points),
        'boundary_vertices': len(polygon), 'candidate_count': considered,
        'levels': {str(level): {'spacing_cm': fine*2**level, 'count': count} for level, count in levels.items()},
        'triangulation': 'requires_native_constrained_delaunay', 'qualification': 'NONE'}
    if queries is not None:
        report['query_work'] = queries.report()
        report['query_policy'] = 'EXACT_SOURCE_SEGMENTS_INDEXED_NO_GEOMETRY_CHANGE'
    check('final_return')
    if identity is not None and digest([boundary,mesh_config])!=identity:
        raise StudioError('Bounded interior grid changed its immutable source or policy')
    return points, report


def preparation_statistics(payload, coords=None, mass=None):
    """Localized geometric metrics and truthful ideal/native mass comparison."""
    coords = payload['placed_cm'] if coords is None else coords
    rest, faces = payload['rest_cm'], payload['faces']
    if len(rest) != len(coords) or any(len(p) != 3 or any(not math.isfinite(x) for x in p) for p in coords):
        raise StudioError('Preparation coordinates must be finite and match the current derived map')
    common_metrics = evaluate_metrics(payload, coords)
    source_triangles = [metric['source_uv_cm'] for metric in common_metrics['face_metrics']]
    extrema, source_edges, placed_edges, area_per_vertex = {}, {}, {}, [0.]*len(rest)
    piece_extrema = {}
    source_areas, placed_areas, face_metrics, invalid = [], [], [], []
    def extreme(name, value, location, lower=False):
        if value is None:
            return
        prior = extrema.get(name)
        if prior is None or (value < prior['value'] if lower else value > prior['value']):
            extrema[name] = {'value': value, **location}
        local = piece_extrema.setdefault(location['piece'], {})
        prior = local.get(name)
        if prior is None or (value < prior['value'] if lower else value > prior['value']):
            local[name] = {'value': value, **location}
    for index, (face, uv) in enumerate(zip(faces, source_triangles)):
        if len(face) != 3 or len(set(face)) != 3 or len(uv) != 3:
            raise StudioError('Preparation requires the current triangular derived mesh')
        positions = [coords[i] for i in face]
        metric = common_metrics['face_metrics'][index]
        src, dst = [{key: metric[domain+'_'+key] for key in ('area_cm2', 'min_angle_degrees', 'aspect_ratio', 'edges_cm')}
                    for domain in ('source', 'placed')]
        principal = metric['principal_stretch']
        location = {'face': index, 'piece': metric['piece'], 'vertices': list(face),
                    'source_uv_cm': copy.deepcopy(uv), 'placed_cm': copy.deepcopy(positions)}
        if src['area_cm2'] < 1e-10 or dst['area_cm2'] < 1e-10:
            invalid.append(location)
        source_areas.append(src['area_cm2']); placed_areas.append(dst['area_cm2'])
        for vertex in face:
            area_per_vertex[vertex] += src['area_cm2']/3
        ratios = []
        for side, (a, b) in enumerate(zip(face, face[1:]+face[:1])):
            # One welded edge may retain different metric lengths on its two
            # source panels (declared ease); never overwrite one island by it.
            key = (metric['piece'], *sorted((a, b)))
            source_edges[key] = src['edges_cm'][side]; placed_edges[key] = dst['edges_cm'][side]
            ratio = dst['edges_cm'][side]/src['edges_cm'][side] if src['edges_cm'][side] > 1e-12 else None
            if ratio is not None:
                ratios.append(ratio)
                edge_location = {**location, 'edge': [a, b]}
                extreme('min_edge_stretch', ratio, edge_location, True)
                extreme('max_edge_stretch', ratio, edge_location)
                extreme('min_source_edge_cm', src['edges_cm'][side], edge_location, True)
                extreme('max_source_edge_cm', src['edges_cm'][side], edge_location)
                extreme('min_placed_edge_cm', dst['edges_cm'][side], edge_location, True)
                extreme('max_placed_edge_cm', dst['edges_cm'][side], edge_location)
        for domain, metrics in (('source', src), ('placed', dst)):
            extreme('min_'+domain+'_angle_degrees', metrics['min_angle_degrees'], location, True)
            extreme('max_'+domain+'_aspect_ratio', metrics['aspect_ratio'], location)
            extreme('min_'+domain+'_area_cm2', metrics['area_cm2'], location, True)
            extreme('max_'+domain+'_area_cm2', metrics['area_cm2'], location)
        if principal is not None:
            extreme('min_principal_stretch', principal[0], location, True)
            extreme('max_principal_stretch', principal[1], location)
        face_metrics.append({'face': index, 'piece': metric['piece'], 'source_uv_cm': copy.deepcopy(uv),
            'vertices': list(face), 'area_ratio': metric['area_ratio'],
            'source_signed_area_cm2': metric['source_signed_area_cm2'],
            'source_area_cm2': src['area_cm2'], 'placed_area_cm2': dst['area_cm2'],
            'source_min_angle_degrees': src['min_angle_degrees'], 'placed_min_angle_degrees': dst['min_angle_degrees'],
            'source_aspect_ratio': src['aspect_ratio'], 'placed_aspect_ratio': dst['aspect_ratio'],
            'min_edge_stretch': min(ratios) if ratios else None, 'max_edge_stretch': max(ratios) if ratios else None,
            'principal_stretch': principal})
    mass_report = None
    if mass is not None:
        if mass.get('basis') not in ('areal_density_kg_m2', 'total_kg') or type(mass.get('value')) not in (int, float) or not math.isfinite(mass['value']) or mass['value'] <= 0:
            raise StudioError('Preparation mass needs an explicit positive total or areal basis')
        area = sum(source_areas)
        if area <= 0 or not rest:
            raise StudioError('Cannot assign mass to a zero-area preparation')
        density = mass['value'] if mass['basis'] == 'areal_density_kg_m2' else mass['value']/(area/10000)
        ideal = [a/10000*density for a in area_per_vertex]
        total, native = sum(ideal), sum(ideal)/len(rest)
        errors = [abs(native/value-1) for value in ideal if value > 0]
        mass_report = {'basis': mass['basis'], 'areal_density_kg_m2': density, 'source_area_cm2': area,
            'total_mass_kg': total, 'native_mass_per_vertex_kg': native,
            'native_assignment': 'uniform_scalar_per_vertex_not_exact_local_areal_mass',
            'vertex_group_mass_semantics': 'pin_weights_not_density',
            'tributary_area_cm2': area_per_vertex, 'ideal_areal_vertex_mass_kg': ideal,
            'tributary_area_distribution': _distribution(area_per_vertex),
            'uniform_assignment_relative_local_density_error': _distribution(errors),
            'zero_area_vertices': [i for i, a in enumerate(area_per_vertex) if a <= 0],
            'source_area_mass_conserved': math.isclose(total, density*area/10000, rel_tol=1e-12)}
    bending, piece_bending = common_metrics['bending'], common_metrics['bending_per_piece']
    by_piece = {}
    for pid, panel in payload['panels'].items():
        ids = panel['indices']
        piece_uv = [point for metric in face_metrics if metric['piece']==pid for point in metric['source_uv_cm']]
        source_bbox = ([[min(p[k] for p in piece_uv) for k in range(2)], [max(p[k] for p in piece_uv) for k in range(2)]]
                       if piece_uv else None)
        placed_bbox = [[min(coords[i][k] for i in ids) for k in range(3)], [max(coords[i][k] for i in ids) for k in range(3)]]
        metrics = [m for m in face_metrics if m['piece'] == pid]
        source_local_edges = [length for edge, length in source_edges.items() if edge[0] == pid]
        placed_local_edges = [length for edge, length in placed_edges.items() if edge[0] == pid]
        by_piece[pid] = {'vertices': len(ids), 'faces': len(metrics),
            'source_bbox_cm': source_bbox, 'source_dimensions_cm': [source_bbox[1][k]-source_bbox[0][k] for k in range(2)] if source_bbox else None,
            'placed_bbox_cm': placed_bbox, 'placed_dimensions_cm': [placed_bbox[1][k]-placed_bbox[0][k] for k in range(3)],
            'source_area_cm2': sum(m['source_area_cm2'] for m in metrics),
            'placed_area_cm2': sum(m['placed_area_cm2'] for m in metrics),
            'source_edge_distribution_cm': _distribution(source_local_edges),
            'placed_edge_distribution_cm': _distribution(placed_local_edges),
            'source_triangle_angle_distribution_degrees': _distribution([m['source_min_angle_degrees'] for m in metrics]),
            'placed_triangle_angle_distribution_degrees': _distribution([m['placed_min_angle_degrees'] for m in metrics]),
            'source_triangle_area_distribution_cm2': _distribution([m['source_area_cm2'] for m in metrics]),
            'placed_triangle_area_distribution_cm2': _distribution([m['placed_area_cm2'] for m in metrics]),
            'extrema': piece_extrema.get(pid, {}), 'bending': piece_bending[pid]}
    by_seam = {}
    for sid, seam in payload.get('seams', {}).items():
        gaps = [math.dist(coords[a], coords[b]) for a, b in seam['pairs']]
        worst = max(range(len(gaps)), key=lambda i: gaps[i]) if gaps else None
        pairs = seam['pairs']
        by_seam[sid] = {'id': sid, 'kind': seam['kind'], 'piece_a': seam['piece_a'], 'piece_b': seam['piece_b'],
            'pair_count': len(pairs), 'gap_distribution_cm': _distribution(gaps),
            'arc_parameters': list(seam.get('parameters', [])),
            'worst_pair': None if worst is None else {'pair_index': worst, 'vertices': list(pairs[worst]),
                'parameter': seam.get('parameters', [None]*len(pairs))[worst], 'gap_cm': gaps[worst],
                'source_uv_a_cm': list(rest[pairs[worst][0]][:2]), 'source_uv_b_cm': list(rest[pairs[worst][1]][:2]),
                'placed_a_cm': list(coords[pairs[worst][0]]), 'placed_b_cm': list(coords[pairs[worst][1]])}}
    from .pattern_assembly import _edges, _vertex_manifold
    edge_faces = _edges(faces)
    nonmanifold = [list(edge) for edge, uses in edge_faces.items() if len(uses) > 2]
    orientations = [list(edge) for edge, uses in edge_faces.items() if len(uses) == 2 and uses[0] == uses[1]]
    duplicate_faces = len(faces)-len({tuple(sorted(face)) for face in faces})
    vertex_error = None
    try:
        _vertex_manifold(faces)
    except StudioError as error:
        vertex_error = str(error)
    topology = {'boundary_edges': sum(len(v) == 1 for v in edge_faces.values()),
        'interior_edges': sum(len(v) == 2 for v in edge_faces.values()),
        'nonmanifold_edges': nonmanifold[:20], 'nonmanifold_edge_count': len(nonmanifold),
        'inconsistent_oriented_edges': orientations[:20], 'inconsistent_oriented_edge_count': len(orientations),
        'duplicate_face_count': duplicate_faces, 'vertex_manifold': vertex_error is None,
        'vertex_manifold_issue': vertex_error, 'surface_boundary_policy': 'open_source_pattern_boundaries_are_expected'}
    return {'version': METRIC_VERSION, 'metric_version': METRIC_VERSION, 'validator_version': VALIDATOR_VERSION,
        'metric_scope': METRIC_SCOPE, 'orientation': common_metrics['orientation'],
        'historical_pass_transferred': False,
        'vertices': len(rest), 'faces': len(faces), 'source_area_cm2': sum(source_areas),
        'placed_area_cm2': sum(placed_areas), 'source_edge_distribution_cm': _distribution(list(source_edges.values())),
        'placed_edge_distribution_cm': _distribution(list(placed_edges.values())),
        'source_triangle_area_distribution_cm2': _distribution(source_areas),
        'placed_triangle_area_distribution_cm2': _distribution(placed_areas),
        'extrema': extrema, 'per_piece': by_piece, 'per_seam': by_seam, 'topology': topology, 'bending': bending,
        'invalid_faces': invalid[:20], 'invalid_face_count': len(invalid),
        'face_metrics': face_metrics, 'source_rest_triangles_cm': copy.deepcopy(source_triangles),
        'source_metric_domain': 'immutable_source_uv_per_face', 'mass': mass_report,
        'qualification': 'NONE', 'accepted': False}


def assess_preparation(payload, recipe, plan=None, collision_report=None, source_audit=None):
    """Readiness for the next controlled native stage; never an acceptance gate."""
    plan = plan or {}
    statistics = preparation_statistics(payload, mass=recipe.get('mass'))
    # Preparation can tighten an assembly plan; it cannot weaken the immutable
    # recipe, including principal strain that edge ratios alone may understate.
    requested = plan.get('quality', {})
    limits = {key: max(recipe['mesh'][key], requested.get(key, recipe['mesh'][key]))
              for key in ('min_angle_degrees', 'min_edge_cm', 'min_stretch')}
    limits['max_stretch'] = min(recipe['mesh']['max_stretch'], requested.get('max_stretch', recipe['mesh']['max_stretch']))
    if payload.get('regular_preparation_mesh'):
        limits['min_angle_degrees'] = max(limits['min_angle_degrees'],
            payload['regular_preparation_mesh'].get('target_min_angle_degrees', 15.))
    reasons = []
    if source_audit is None:
        reasons.append(_issue('SOURCE_AUDIT_MISSING', 'Preparation requires a source and cutting metadata audit', 'missing_metadata'))
    else:
        reasons.extend(copy.deepcopy(source_audit['issues']))
        if source_audit.get('source_sha256') != payload.get('source_garment_sha256'):
            reasons.append(_issue('SOURCE_AUDIT_STALE', 'Source audit is not bound to this derived garment', 'source_contract'))
    if statistics['invalid_face_count']:
        reasons.append(_issue('DEGENERATE_DERIVED_FACE', 'Derived mesh has a collapsed source or placed face', 'derived_geometry'))
    topology = statistics['topology']
    if (topology['nonmanifold_edge_count'] or topology['inconsistent_oriented_edge_count'] or topology['duplicate_face_count']
            or not topology['vertex_manifold'] or statistics['orientation']['source_binding_issues']):
        reasons.append(_issue('DERIVED_TOPOLOGY', 'Derived surface has an orientation, duplicate face or manifold conflict',
                              'derived_geometry', evidence=topology))
    for name, threshold, lower in (
            ('min_source_angle_degrees', limits['min_angle_degrees'], True),
            ('min_placed_angle_degrees', limits['min_angle_degrees'], True),
            ('min_source_edge_cm', limits['min_edge_cm'], True),
            ('min_placed_edge_cm', limits['min_edge_cm'], True),
            ('min_principal_stretch', limits['min_stretch'], True),
            ('max_principal_stretch', limits['max_stretch'], False)):
        observed = statistics['extrema'].get(name)
        if observed and (observed['value'] < threshold-1e-8 if lower else observed['value'] > threshold+1e-8):
            reasons.append(_issue(name.upper(), 'Preparation exceeds its declared metric quality limit',
                'placement' if 'stretch' in name or 'placed' in name else 'derived_geometry',
                observed=observed, limit=threshold))
    if collision_report is None and (recipe.get('colliders') or plan.get('collision', {}).get('required')):
        reasons.append(_issue('COLLISION_EVIDENCE_MISSING', 'Placed candidate needs its sourced body collision reserve check', 'missing_metadata'))
    elif collision_report is not None and collision_report.get('ok') is not True:
        reasons.append(_issue('PLACEMENT_CONTACT', 'Placed candidate violates the unchanged collision reserve',
                             'placement', evidence=copy.deepcopy(collision_report)))
    if statistics['mass'] is None:
        reasons.append(_issue('MASS_BASIS_MISSING', 'Explicit source-area mass basis is required', 'missing_metadata'))
    elif statistics['mass']['zero_area_vertices']:
        reasons.append(_issue('UNUSED_DERIVED_VERTICES', 'Vertices without source tributary area cannot receive physical mass', 'derived_geometry'))
    errors = [r for r in reasons if r['category'] != 'missing_metadata']
    status = 'NEEDS_CORRECTION' if errors else 'NEEDS_CLARIFICATION' if reasons else 'READY'
    return {'version': METRIC_VERSION, 'metric_version': METRIC_VERSION, 'validator_version': VALIDATOR_VERSION,
        'historical_pass_transferred': False, 'status': status, 'reasons': reasons, 'statistics': statistics,
        'effective_quality_limits': limits,
        'source_sha256': payload.get('source_garment_sha256'), 'source_audit': copy.deepcopy(source_audit),
        'collision': copy.deepcopy(collision_report), 'accepted': False, 'qualification': 'PREPARATION_ONLY',
        'fitting': 'NOT_QUALIFIED', 'behavior': 'NOT_QUALIFIED', 'artistic': 'NOT_REVIEWED',
        'cloth_executed': False, 'export_eligible': False}
