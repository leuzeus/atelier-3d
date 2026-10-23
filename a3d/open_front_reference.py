"""Measured central-front references; no wearing target or design adoption.

The caller authenticates project/package/native receipts. This pure kernel
checks their supplied geometric identities and measures existing source cuts
in existing guides. A guide is a reference proposal, never a fitted surface.
"""
import copy
import hashlib
import html
import json
import math
import time

from .core import StudioError, digest
from .garment_guides import _profile
from .garment_measurements import _source_guide_curve


_CAPS = {'max_input_bytes': 64*1024*1024, 'max_vertices': 20000,
         'max_faces': 50000, 'max_boundary_edges': 10000,
         'max_curve_points': 20000, 'max_output_bytes': 8*1024*1024}


class _Limit(StudioError):
    pass


def _point(value, size):
    return isinstance(value, list) and len(value) == size and all(
        type(x) in (int, float) and math.isfinite(x) for x in value)


def _world(profile, point):
    basis = profile['frame']
    return [basis['origin_cm'][k]+sum(point[j]*basis[axis][k]
            for j, axis in enumerate(('right', 'forward', 'up'))) for k in range(3)]


def _local(profile, point):
    delta = [point[k]-profile['frame']['origin_cm'][k] for k in range(3)]
    return [sum(delta[k]*profile['frame'][axis][k] for k in range(3))
            for axis in ('right', 'forward', 'up')]


def _encoded(value, limit, check):
    """Bound both canonical serialization and hashing without a giant copy."""
    size = 0; result = hashlib.sha256()
    try:
        for part in json.JSONEncoder(ensure_ascii=False, sort_keys=True,
                                    separators=(',', ':'), allow_nan=False).iterencode(value):
            check(); chunk = part.encode('utf-8'); size += len(chunk)
            if size > limit:
                raise _Limit('OPEN_FRONT_SERIALIZED_BYTE_BUDGET')
            result.update(chunk)
    except (TypeError, ValueError, RecursionError) as error:
        if isinstance(error, StudioError):
            raise
        raise StudioError('Open-front inputs must be finite JSON values') from error
    return result.hexdigest(), size


def _budgets(values, clock):
    if not isinstance(values, dict) or set(values) != set(_CAPS) | {'max_seconds'}:
        raise StudioError('Open-front reference needs all explicit computational budgets')
    if any(type(values[key]) is not int or not 1 <= values[key] <= cap
           for key, cap in _CAPS.items()):
        raise StudioError('Open-front computational budgets exceed their qualified domain')
    seconds = values['max_seconds']
    if type(seconds) not in (int, float) or not math.isfinite(seconds) or not 0 < seconds <= 60:
        raise StudioError('Open-front time budget must be finite and within 60 seconds')
    last = started = clock()
    if type(started) not in (int, float) or not math.isfinite(started):
        raise StudioError('Open-front clock must be finite and monotonic')
    def check():
        nonlocal last
        current = clock()
        if type(current) not in (int, float) or not math.isfinite(current) or current < last:
            raise StudioError('Open-front clock must be finite and monotonic')
        last = current
        if current-started > seconds:
            raise _Limit('OPEN_FRONT_TIME_BUDGET')
    return check


def _free_sides(data, pid, own, links, budgets, check):
    """Use original vertex incidence, never point proximity or edge names."""
    attachments = {}
    for side in ('left', 'right'):
        matches = []
        for link in links:
            check()
            if link.get('kind', 'permanent') != 'permanent':
                continue
            for a, b in (('a', 'b'), ('b', 'a')):
                partner = link['piece_'+b]
                if (link['piece_'+a] == pid and partner in own
                        and own[partner]['semantics'].get('role') == 'front'
                        and own[partner]['semantics'].get('side') == side):
                    matches.append({'side': side, 'source_link_id': link.get('source_link_id', link['id']),
                        'compiled_link_id': link['id'], 'edge': link['edge_'+a],
                        'partner_piece': partner, 'partner_edge': link['edge_'+b],
                        'kind': 'permanent', 'orientation': link['orientation']})
        if len(matches) != 1:
            return None, [{'code': 'CENTRAL_FRONT_ATTACHMENT_MAPPING_REQUIRED', 'side': side,
                           'candidate_count': len(matches)}]
        attachments[side] = matches[0]
    from .dressing_derivation import source_boundary_graph_from_validated
    graph = source_boundary_graph_from_validated(data, max_edges=budgets['max_boundary_edges']); check()
    if graph['status'] != 'SOURCE_BOUNDARY_DERIVED':
        raise _Limit('OPEN_FRONT_SOURCE_BOUNDARY_EDGE_BUDGET')
    free = {tuple(sorted(atom['vertices'])): atom['named_edges']
            for component in graph['components'] for atom in component['atoms'] if atom['piece'] == pid}
    piece = data['pieces'][pid]; axis = own[pid]['semantics'].get('longitudinal_uv_axis')
    if axis not in ('u', 'v'):
        return None, [{'code': 'CENTRAL_FRONT_LONGITUDINAL_AXIS_REQUIRED'}]
    axis = 0 if axis == 'u' else 1; selected = {}
    for side, attachment in attachments.items():
        candidates = []
        attached_ids = set(piece['edges'][attachment['edge']])
        for name, chain in piece['edges'].items():
            check(); atoms = [tuple(sorted((a, b))) for a, b in zip(chain, chain[1:])]
            if (not atoms or not all(atom in free for atom in atoms)
                    or not attached_ids.intersection(chain)
                    or len({piece['vertices'][i][axis] for i in chain}) == 1):
                continue
            candidates.append({'edge': name, 'source_vertex_ids': list(chain),
                               'aliases': sorted({alias for atom in atoms for alias in free[atom]})})
        if len(candidates) != 1 or candidates[0]['aliases'] != [candidates[0]['edge']]:
            return None, [{'code': 'CENTRAL_FRONT_FREE_BOUNDARY_MAPPING_REQUIRED', 'side': side,
                           'candidates': candidates}]
        selected[side] = dict(candidates[0], attachment=attachment)
    if selected['left']['edge'] == selected['right']['edge']:
        return None, [{'code': 'CENTRAL_FRONT_DISTINCT_FREE_BOUNDARIES_REQUIRED'}]
    return selected, []


def _validate_source(compiled, profile, guides, source_data, source_meshes, pid, budgets, check):
    row = compiled['textiles'][pid]; cid = row['component_id']
    if any(cid not in value for value in (guides, source_data, source_meshes)):
        raise StudioError('Open-front reference needs its exact component source, guide and native mesh')
    own = {p: r for p, r in compiled['textiles'].items() if r['component_id'] == cid}
    data = source_data[cid]; native = source_meshes[cid]; guide = guides[cid]
    if (data.get('component_id') != cid or native.get('component_id') != cid
            or set(data['pieces']) != set(own) or set(native['panels']) != set(own)
            or set(native.get('seams', {})) != {s['id'] for s in data['seams']}):
        raise StudioError('Open-front source/native/compiled inventory differs')
    if (sum(len(p['vertices']) for p in data['pieces'].values()) > budgets['max_vertices']
            or sum(len(p['faces']) for p in data['pieces'].values()) > budgets['max_faces']
            or len(native['rest_cm']) > budgets['max_vertices'] or len(native['faces']) > budgets['max_faces']):
        raise _Limit('OPEN_FRONT_SOURCE_OR_NATIVE_GEOMETRY_BUDGET')
    if (native.get('source_garment_sha256') != digest(data) or guide.get('source_sha256') != digest(data)
            or any(r['source_geometry'] != data['pieces'][p] for p, r in own.items())
            or any(r['package_source_ref'] != row['package_source_ref'] for r in own.values())
            or native.get('package_sha256') != row['package_source_ref']['sha256']):
        raise StudioError('Open-front source or native package identity differs')
    if (guide.get('profile_sha256') != digest(profile) or guide.get('profile_cache_key') != profile['cache_key']
            or guide.get('semantics_sha256') != digest({p: r['semantics'] for p, r in own.items()})
            or set(guide['panels']) != set(own)):
        raise StudioError('Open-front guide belongs to another source role, inventory or body')
    frame = guide['panels'][pid]
    if (not isinstance(frame.get('uv_cm'), list) or not isinstance(frame.get('target_cm'), list)
            or not isinstance(frame.get('triangles'), list)):
        raise StudioError('Open-front reference requires its existing explicit source UV guide cage')
    if len(frame['uv_cm']) > budgets['max_vertices'] or len(frame['triangles']) > budgets['max_faces']:
        raise _Limit('OPEN_FRONT_GUIDE_GEOMETRY_BUDGET')
    links = [link for link in compiled['links'] if link.get('component_id') == cid
             or (link.get('component_id') is None and link['piece_a'] in own and link['piece_b'] in own)]
    actual = {s['id']: {k: s[k] for k in ('piece_a', 'piece_b', 'edge_a', 'edge_b', 'orientation')}
              | {'kind': s.get('kind', 'permanent')} for s in data['seams']}
    observed = {s.get('source_link_id', s['id']): {k: s[k] for k in ('piece_a', 'piece_b', 'edge_a', 'edge_b', 'orientation')}
                | {'kind': s.get('kind', 'permanent')} for s in links}
    if len(observed) != len(links) or observed != actual:
        raise StudioError('Open-front compiled links differ from the actual source seam declarations')
    check(); return cid, row, own, data, native, guide, frame, links


def prepare_open_front_reference(compiled, profile, guides, source_data, source_meshes, section_landmarks,
                                 *, budgets, provenance, source_path_proposals=(), clock=time.monotonic):
    """Measure one declared inner_front/center reference at three chosen sections.

    source_data/source_meshes/guides are keyed by component_id. The native mesh
    is the caller-authenticated observation with its exact ephemeral
    _canonical_source_uv_storage replay. provenance is retained, not reverified
    as a receipt here. No file access, native execution, target or variant.

    Geometry caps apply separately to the complete component source, complete
    native mesh and selected central guide. Byte/time caps cover all inputs.
    An existing guide-plane primitive has its own stricter 15-second budget;
    this wrapper checks its overall deadline before and after each call.
    """
    check = _budgets(budgets, clock)
    if (not isinstance(section_landmarks, (list, tuple)) or len(section_landmarks) != 3
            or any(not isinstance(name, str) or not name for name in section_landmarks)
            or len(set(section_landmarks)) != 3):
        raise StudioError('Open-front reference requires three distinct explicit anatomical section names')
    if not isinstance(provenance, dict) or not provenance:
        raise StudioError('Open-front reference requires a caller-authenticated provenance summary')
    inputs = [compiled, profile, guides, source_data, source_meshes, section_landmarks,
              budgets, provenance, source_path_proposals]
    result = {'version': 1, 'status': 'NEEDS_MAPPING', 'qualification': 'REFERENCE_MEASUREMENTS_ONLY',
        'admissible_for_fit': False, 'target_adopted': False, 'variant_adopted': False,
        'simulation': 'NOT_EXECUTED', 'fitting': 'NOT_EXECUTED', 'spatial_coverage': 'NOT_QUALIFIED',
        'open_front_overlap': 'NOT_MEASURED', 'visibility': {'status': 'UNSELECTED',
            'left_margin_cm': None, 'right_margin_cm': None},
        'current_outer_opening_is_target': False, 'budgets': copy.deepcopy(budgets),
        'sections': [], 'diagnostics': [], 'input_immutability_verified': False}
    try:
        before, input_bytes = _encoded(inputs, budgets['max_input_bytes'], check)
        _profile(profile)
        if not _point(profile['frame'].get('origin_cm'), 3):
            raise StudioError('Open-front reference needs a finite measured body origin')
        if (compiled.get('status') != 'READY_TO_PLAN' or not compiled.get('assembly_spec')
                or compiled.get('compiled_sha256') != digest({k: v for k, v in compiled.items() if k != 'compiled_sha256'})):
            raise StudioError('Open-front reference needs its exact complete source compilation')
        central = [(pid, row) for pid, row in compiled['textiles'].items()
                   if row['semantics'].get('role') == 'inner_front' and row['semantics'].get('side') == 'center']
        result['identity'] = {'inputs_sha256': before, 'input_bytes': input_bytes,
            'compiled_sha256': compiled['compiled_sha256'], 'profile_sha256': digest(profile),
            'profile_cache_key': profile['cache_key'], 'profile_geometry_sha256': profile.get('geometry_sha256'),
            'profile_pose_sha256': profile.get('pose_sha256'), 'guides_sha256': digest(guides),
            'source_path_proposals_sha256': digest(source_path_proposals),
            'provenance': copy.deepcopy(provenance),
            'provenance_verification': 'SUPPLIED_BY_CALLER_NOT_AUTHENTICATED_BY_PURE_KERNEL'}
        if len(central) != 1:
            result['diagnostics'].append({'code': 'UNIQUE_DECLARED_CENTRAL_FRONT_REQUIRED', 'candidate_count': len(central)})
        else:
            pid, _ = central[0]
            cid, row, own, data, native, guide, frame, links = _validate_source(
                compiled, profile, guides, source_data, source_meshes, pid, budgets, check)
            result['identity'].update({'component_id': cid, 'piece_id': pid,
                'package_ref': copy.deepcopy(row['package_source_ref']), 'source_data_sha256': digest(data),
                'source_geometry_sha256': digest(row['source_geometry']), 'guide_sha256': digest(frame),
                'native_mesh_sha256': digest(native), 'canonical_source_uv_storage_sha256':
                    native.get('_canonical_source_uv_storage', {}).get('content_sha256')})
            sides, diagnostics = _free_sides(data, pid, own, links, budgets, check)
            result['diagnostics'].extend(diagnostics)
            if sides:
                result['reference_piece'] = {'piece_id': pid, 'component_id': cid,
                    'semantics': copy.deepcopy(row['semantics']), 'source_uv_outline_cm': copy.deepcopy(row['source_geometry']['vertices']),
                    'free_boundaries': copy.deepcopy(sides), 'declared_layer_relations':
                        copy.deepcopy(compiled['assembly_spec'].get('layers', {}).get('inside_to_outside', [])),
                    'guide_status': 'EXISTING_GUIDE_PROPOSAL_NOT_FITTED', 'attachments': {}}
                from .pattern_assembly import _compile_cage
                from .garment_measurements import _prepare_linear_cage_evaluator
                compiled_cage = _compile_cage(frame, pid, check)
                evaluate = _prepare_linear_cage_evaluator(frame, compiled_cage, check)
                used_points = 0
                for side, boundary in sides.items():
                    check(); attachment = copy.deepcopy(boundary['attachment'])
                    indices = data['pieces'][pid]['edges'][attachment['edge']]
                    uv = [data['pieces'][pid]['vertices'][i] for i in indices]
                    used_points += len(uv)
                    if used_points > budgets['max_curve_points']:
                        raise _Limit('OPEN_FRONT_CURVE_POINT_BUDGET')
                    world = [evaluate(point)[0] for point in uv]
                    attachment.update({'source_vertex_ids': list(indices), 'source_uv_polyline_cm': copy.deepcopy(uv),
                        'guide_world_polyline_cm': world,
                        'source_material_length_cm': sum(math.dist(a, b) for a, b in zip(uv, uv[1:])),
                        'qualification': 'SOURCE_ATTACHMENT_REFERENCE_ONLY'})
                    result['reference_piece']['attachments'][side] = attachment
                for name in section_landmarks:
                    check(); body = profile['landmarks'].get(name, {}).get('section', {})
                    curve = body.get('curve_cm'); height = body.get('height_cm')
                    if (body.get('status') != 'MEASURED' or not isinstance(curve, list) or len(curve) < 3
                            or not all(_point(point, 3) for point in curve)
                            or type(height) not in (int, float) or not math.isfinite(height)
                            or any(abs(point[2]-height) > 1e-7 for point in curve)):
                        result['diagnostics'].append({'code': 'ACTUAL_HORIZONTAL_BODY_SECTION_REQUIRED', 'body_landmark': name})
                        continue
                    used_points += len(curve)
                    if len(curve) > budgets['max_vertices'] or used_points > budgets['max_curve_points']:
                        raise _Limit('OPEN_FRONT_CURVE_POINT_BUDGET')
                    section = {'center_cm': _world(profile, [0., 0., height]),
                               'plane': {'normal_world': copy.deepcopy(profile['frame']['up'])}}
                    try:
                        segment, span = _source_guide_curve(row, pid, frame, source_meshes, section,
                            [sides['left']['edge'], sides['right']['edge']], links)
                    except StudioError as error:
                        check(); result['diagnostics'].append({'code': 'CENTRAL_FRONT_SECTION_NOT_MEASURED',
                            'body_landmark': name, 'message': str(error)})
                        continue
                    check(); material = span['guide_plane_material_curve']
                    used_points += len(material['source_uv_polyline_cm'])
                    if used_points > budgets['max_curve_points']:
                        raise _Limit('OPEN_FRONT_CURVE_POINT_BUDGET')
                    world = material['guide_world_polyline_cm']; selectors = [segment['from'], segment['to']]
                    if {s['edge'] for s in selectors} != {sides['left']['edge'], sides['right']['edge']}:
                        raise StudioError('Open-front measured endpoints differ from the exact mapped free boundaries')
                    anterior = max(point[1] for point in curve); endpoints = {}
                    for side, boundary in sides.items():
                        index = 0 if selectors[0]['edge'] == boundary['edge'] else -1
                        point = world[index]; local = _local(profile, point)
                        endpoints[side] = {'selector': copy.deepcopy(selectors[0 if index == 0 else 1]),
                            'source_uv_cm': copy.deepcopy(material['source_uv_polyline_cm'][index]),
                            'guide_world_cm': copy.deepcopy(point), 'body_frame_cm': local,
                            'signed_recess_from_section_front_cm': anterior-local[1]}
                    local_world = [_local(profile, p) for p in world]
                    result['sections'].append({'body_landmark': name, 'body_section_sha256': digest(body),
                        'body_section_height_cm': height, 'body_section_curve_cm': copy.deepcopy(curve),
                        'body_section_world_curve_cm': [_world(profile, p) for p in curve],
                        'body_section_front_forward_cm': anterior, 'material_width_cm': span['source_material_length_cm'],
                        'guide_world_length_cm': material['guide_world_length_cm'],
                        'endpoint_distance_cm': math.dist(world[0], world[-1]),
                        'projected_right_span_cm': abs(endpoints['left']['body_frame_cm'][0]-endpoints['right']['body_frame_cm'][0]),
                        'endpoints': endpoints, 'guide_body_frame_polyline_cm': local_world,
                        'source_segment': segment, 'source_span': span,
                        'recess_sign': 'POSITIVE_TOWARD_BODY_BACK_FROM_ACTUAL_SECTION_FRONT',
                        'homology': 'REVIEW_REQUIRED', 'guide_status': 'EXISTING_GUIDE_PROPOSAL_NOT_FITTED',
                        'physical_layer_recess': 'NOT_MEASURED', 'visibility': 'UNSELECTED', 'margin_cm': None})
                result['status'] = 'CENTRAL_FRONT_REFERENCE_MEASURED' if len(result['sections']) == 3 else 'NEEDS_DATA'
        after, _ = _encoded(inputs, budgets['max_input_bytes'], check)
        if before != after:
            raise StudioError('Open-front reference inputs mutated during computation')
        result['input_immutability_verified'] = True
        result['source_mutated'] = False; result['body_mutated'] = False
        result['integrity_scope'] = 'CANONICAL_REPORT_CONTENT_ONLY_NOT_PROVENANCE_AUTHENTICATION'
        result['report_sha256'], _ = _encoded(result, budgets['max_output_bytes'], check)
        _encoded(result, budgets['max_output_bytes'], check)
        return result
    except _Limit as error:
        # No partial measurement is qualified after an unverified deadline.
        return {'version': 1, 'status': 'INCOMPLETE', 'qualification': 'NONE',
            'admissible_for_fit': False, 'target_adopted': False, 'variant_adopted': False,
            'input_immutability_verified': False, 'sections': [],
            'visibility': {'status': 'UNSELECTED', 'left_margin_cm': None, 'right_margin_cm': None},
            'diagnostics': [{'code': str(error)}]}


def render_open_front_reference(profile, report, *, max_output_bytes):
    """Render the measured body/guide curves as SVG, without selecting a gap."""
    if type(max_output_bytes) is not int or not 1 <= max_output_bytes <= _CAPS['max_output_bytes']:
        raise StudioError('Open-front SVG requires an explicit bounded output budget')
    if (report.get('status') != 'CENTRAL_FRONT_REFERENCE_MEASURED'
            or report['identity']['profile_sha256'] != digest(profile)
            or len(report.get('sections', [])) != 3):
        raise StudioError('Open-front SVG requires three exact measured references for this body')
    before, _ = _encoded([profile, report], _CAPS['max_output_bytes'], lambda: None)
    content_sha256, _ = _encoded({key: value for key, value in report.items() if key != 'report_sha256'},
                                _CAPS['max_output_bytes'], lambda: None)
    if report.get('report_sha256') != content_sha256:
        raise StudioError('Open-front SVG report integrity differs from its measured content')
    count = len(report['reference_piece']['source_uv_outline_cm'])
    count += sum(len(a['source_uv_polyline_cm']) for a in report['reference_piece']['attachments'].values())
    count += sum(len(row[key]) for row in report['sections']
                 for key in ('body_section_curve_cm', 'guide_body_frame_polyline_cm'))
    count += sum(len(row['source_segment']['source_uv_polyline_cm']) for row in report['sections'])
    if count > 3*_CAPS['max_curve_points']:
        raise StudioError('Open-front SVG point budget exhausted')
    esc = lambda value: html.escape(str(value), quote=True)
    parts = ['<svg xmlns="http://www.w3.org/2000/svg" width="1200" height="850" viewBox="0 0 1200 850">',
             '<rect width="1200" height="850" fill="#f8fafc"/>',
             '<g font-family="sans-serif" fill="#172033">',
             '<text x="28" y="32" font-size="21">Devant central — références mesurées</text>',
             '<text x="28" y="58" font-size="14">Guide existant, sans fitting. Visibilité et marges : UNSELECTED. Aucune cible adoptée.</text>']
    def poly(points, stroke, width=2, dashed=False):
        return '<polyline fill="none" stroke="'+stroke+'" stroke-width="'+str(width)+'"'+(
            ' stroke-dasharray="5 4"' if dashed else '')+' points="'+' '.join(f'{x:.4f},{y:.4f}' for x, y in points)+'"/>'
    for index, row in enumerate(report['sections']):
        left = 25+index*395; body = row['body_section_curve_cm']; guide = row['guide_body_frame_polyline_cm']
        # Anatomy sections with this exact source identity represent a selected
        # closed mesh/plane loop; their cyclic array omits a repeated endpoint.
        section = profile['landmarks'].get(row['body_landmark'], {}).get('section', {})
        cyclic = (section.get('status') == 'MEASURED' and section.get('confidence') == 'MEASURED_SECTION'
                  and type(section.get('loop_count')) is int and type(section.get('excluded_loops')) is int
                  and section['loop_count']-section['excluded_loops'] == 1
                  and section.get('curve_cm') == body and digest(section) == row['body_section_sha256'])
        display_body = body+[body[0]] if cyclic and body[0] != body[-1] else body
        points = body+guide
        xmin, xmax = min(p[0] for p in points), max(p[0] for p in points)
        ymin, ymax = min(p[1] for p in points), max(p[1] for p in points)
        scale = min(320/max(xmax-xmin, 1e-9), 215/max(ymax-ymin, 1e-9))
        def project(point):
            return (left+180+(point[0]-(xmin+xmax)/2)*scale,
                    257.5-(point[1]-(ymin+ymax)/2)*scale)
        parts += [f'<text x="{left}" y="94" font-size="18">{esc(row["body_landmark"])}</text>',
                  f'<text x="{left}" y="115" font-size="13">Coupe horizontale réelle — avant vers le haut</text>',
                  poly([project(p) for p in display_body], '#64748b'), poly([project(p) for p in guide], '#0369a1', 3)]
        for side, endpoint in row['endpoints'].items():
            x, y = project(endpoint['body_frame_cm'])
            parts += [f'<circle cx="{x:.4f}" cy="{y:.4f}" r="4" fill="#0369a1"/>',
                      f'<text x="{x+7:.4f}" y="{max(150., min(380., y-7)):.4f}" font-size="12">{esc(side)}</text>']
        labels = [f'Matière : {row["material_width_cm"]:.2f} cm',
                  f'Projection droite : {row["projected_right_span_cm"]:.2f} cm',
                  f'Distance endpoints : {row["endpoint_distance_cm"]:.2f} cm',
                  'Retrait signé / avant du corps :',
                  ' / '.join(f'{side} {e["signed_recess_from_section_front_cm"]:+.2f} cm' for side, e in row['endpoints'].items())]
        parts += [f'<text x="{left}" y="{405+n*21}" font-size="13">{esc(label)}</text>' for n, label in enumerate(labels)]
    ref = report['reference_piece']; outline = ref['source_uv_outline_cm']; xmin = min(p[0] for p in outline); xmax = max(p[0] for p in outline)
    ymin = min(p[1] for p in outline); ymax = max(p[1] for p in outline); scale = min(450/max(xmax-xmin, 1e-9), 300/max(ymax-ymin, 1e-9))
    def uv_project(point):
        return (275+(point[0]-(xmin+xmax)/2)*scale, 680-(point[1]-(ymin+ymax)/2)*scale)
    parts += ['<text x="28" y="522" font-size="18">UV source — coupe conservée et attaches permanentes</text>',
              poly([uv_project(p) for p in outline+[outline[0]]], '#64748b')]
    for attachment in ref['attachments'].values():
        parts.append(poly([uv_project(p) for p in attachment['source_uv_polyline_cm']], '#d97706', 4))
    for row in report['sections']:
        parts.append(poly([uv_project(p) for p in row['source_segment']['source_uv_polyline_cm']], '#0369a1', 2))
    info = ['Pièce : '+ref['piece_id'], 'Bleu : courbes de matière / guide ; gris : corps ou bord source.',
            'Orange : attaches permanentes réelles, limitées aux bords déclarés.',
            'La largeur de matière et sa projection spatiale sont distinctes.',
            'Le retrait est relatif à l’avant de la coupe du corps,',
            'pas une distance qualifiée entre les deux couches textiles.',
            'Couverture physique, recouvrement et contacts : non qualifiés.',
            'Visibilité : UNSELECTED ; marge gauche / droite : UNSELECTED.',
            'Homologie et décision esthétique : revue requise.']
    parts += [f'<text x="550" y="{552+n*26}" font-size="14">{esc(label)}</text>' for n, label in enumerate(info)]
    parts += ['</g></svg>']; result = ''.join(parts)
    if len(result.encode('utf-8')) > max_output_bytes:
        raise StudioError('Open-front SVG output byte budget exhausted')
    if digest([profile, report]) != before:
        raise StudioError('Open-front SVG inputs mutated during rendering')
    return result
