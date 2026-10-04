"""Classify fit intent and measure homologous immutable material paths.

Categories never imply a number of centimetres. Ease is garment capacity minus
the sourced homologous body girth; clearance, seam allowance and open coverage
remain different quantities. This preflight cannot grant native fitting or
human approval, even when all declared source-capacity comparisons succeed.
"""
import copy
import math

from .core import StudioError, contract, digest, inside, read_json, sha
from .fitting import path_inside
from .sewing import edge_chain, sample_chain


def _finite(value):
    return type(value) in (int, float) and math.isfinite(value)


def _cross(a, b):
    return a[0]*b[1]-a[1]*b[0]


def _sub(a, b):
    return [x-y for x, y in zip(a, b)]


def _edge_anchor(piece, selector):
    return sample_chain(edge_chain(piece, selector['edge'])[1], selector['fraction'])


def _material_segment(piece, a, b):
    """Reuse the seam-line kernel for the entire straight material span.

    Checking endpoints or a few samples would miss a narrow concave gap. Split
    at every source boundary crossing and check every resulting interval.
    """
    if math.dist(a, b) <= 1e-8:
        raise StudioError('Fit measurement material span is collapsed')
    if not path_inside(a, b, piece['vertices']):
        raise StudioError('Fit measurement crosses empty space outside its source material')
    return math.dist(a, b)


def _path(compiled, measurement, components):
    segments = measurement['segments']; closed = measurement['path_kind'] == 'closed_girth'
    joins = measurement['joins']; required = len(segments) if closed else len(segments)-1
    if len(joins) != required:
        raise StudioError('Fit measurement must declare every actual path join')
    if len(set(joins)) != len(joins):
        raise StudioError('Fit girth must be a simple cycle; a source join cannot count twice')
    links = {link['id']: link for link in compiled['links']}
    lengths = []; evidence = []; spans = {}; layers = set()
    for segment in segments:
        row = compiled['textiles'].get(segment['piece'])
        if (row is None or row['component_id'] not in components or row['source_geometry'] is None
                or row['component_id'] != measurement['component_id'] or row['semantics']['layer'] != measurement['layer']):
            raise StudioError('Fit measurement references an undeclared source textile')
        piece = row['source_geometry']
        layers.add(row['semantics']['layer'])
        if any(len(p) != 2 or any(not _finite(v) for v in p) for p in piece['vertices']):
            raise StudioError('Fit source material must have finite metric UV coordinates')
        a, b = [_edge_anchor(piece, segment[key]) for key in ('from', 'to')]
        length = _material_segment(piece, a, b)
        for old_a, old_b in spans.setdefault(segment['piece'], []):
            direction = _sub(b, a)
            old_direction = _sub(old_b, old_a); denominator = _cross(direction, old_direction)
            if abs(denominator) > 1e-10:
                t = _cross(_sub(old_a, a), old_direction)/denominator
                u = _cross(_sub(old_a, a), direction)/denominator
                if 1e-8 < t < 1-1e-8 and 1e-8 < u < 1-1e-8:
                    raise StudioError('Fit path self-intersects within the same source material')
            if abs(_cross(direction, _sub(old_a, a))) < 1e-8 and abs(_cross(direction, _sub(old_b, a))) < 1e-8:
                axis = 0 if abs(direction[0]) >= abs(direction[1]) else 1
                lo, hi = sorted((a[axis], b[axis])); x, y = sorted((old_a[axis], old_b[axis]))
                if min(hi, y)-max(lo, x) > 1e-8:
                    raise StudioError('Fit path counts the same material span twice')
        spans[segment['piece']].append((a, b)); lengths.append(length)
        evidence.append({'piece': segment['piece'], 'from_uv_cm': a, 'to_uv_cm': b,
                         'material_length_cm': length, 'piece_geometry_sha256': digest(piece),
                         'package_ref': copy.deepcopy(row['package_source_ref'])})
    if closed and len(layers) != 1:
        raise StudioError('A closed fit path cannot add material from different spatial layers')
    engaged = set(measurement['engaged_links']); needed_engaged = set()
    for index, link_id in enumerate(joins):
        link = links.get(link_id)
        if link is None: raise StudioError('Fit path cannot invent a source seam or closure')
        if link.get('kind') not in ('permanent', 'closure', 'detachable'):
            raise StudioError('Fit path requires an explicit approved source link kind')
        if closed and link['kind'] == 'detachable':
            raise StudioError('A detachable attachment cannot certify a closed garment girth')
        current, following = segments[index], segments[(index+1) % len(segments)]
        for left, right in (('a', 'b'), ('b', 'a')):
            if (current['piece'], current['to']['edge'], following['piece'], following['from']['edge']) == (
                    link['piece_'+left], link['edge_'+left], link['piece_'+right], link['edge_'+right]):
                expected = current['to']['fraction'] if link['orientation'] == 'forward' else 1-current['to']['fraction']
                if abs(following['from']['fraction']-expected) > 1e-7:
                    raise StudioError('Fit path crosses nonhomologous points of an approved source join')
                break
        else:
            raise StudioError('Fit path join does not connect its actual source endpoint edges')
        if link['kind'] != 'permanent': needed_engaged.add(link_id)
    if engaged != needed_engaged:
        raise StudioError('Fit path must explicitly engage exactly its nonpermanent closures or attachments')
    takeup = sum(row['amount_cm'] for row in measurement['takeup'])
    if len({digest({**row, 'amount_cm': float(row['amount_cm'])}) for row in measurement['takeup']}) != len(measurement['takeup']):
        raise StudioError('Fit take-up must not deduct the same sourced allowance twice')
    if sum(lengths)-takeup <= 0:
        raise StudioError('Fit take-up consumes its entire nominal material capacity')
    return sum(lengths)-takeup, evidence


def _profile_identity(profile):
    """Retain the body service's measured shoulder/head/cache contracts."""
    base = copy.deepcopy(profile)
    if 'surface_landmarks_source' in base:
        from .shoulder_surface import surface_anchors
        surface_anchors(base)
        source = base.pop('surface_landmarks_source'); base['cache_key'] = source['previous_cache_key']
        for side in ('left', 'right'): del base['landmarks']['shoulder.surface.'+side]
    if 'head_surface_source' in base:
        from .head_surface import head_surface_section
        head_surface_section(base)
        source = base.pop('head_surface_source'); base['cache_key'] = source['previous_cache_key']
        del base['surface_sections']['head']
        if not base['surface_sections']: del base['surface_sections']
    keys = ('source_sha256', 'pose_sha256', 'geometry_sha256', 'options_sha256', 'rig_landmarks_sha256')
    if any(key not in base for key in keys) or base['cache_key'] != digest({key: base[key] for key in keys}):
        raise StudioError('Fit body source, geometry, pose or measurement options cache changed')


def _girth(landmark):
    section = landmark.get('section', {}); measured = landmark.get('girth_cm')
    if section.get('status') != 'MEASURED' or measured is None: return None
    curve = section.get('curve_cm', [])
    if (not _finite(measured) or measured <= 0 or len(curve) < 3 or
            any(len(p) != 3 or any(not _finite(v) for v in p) for p in curve) or
            not _finite(section.get('height_cm')) or
            any(abs(p[2]-section['height_cm']) > 1e-7 for p in curve)):
        raise StudioError('Fit body section is missing its finite measured surface contour')
    perimeter = sum(math.dist(a, b) for a, b in zip(curve, curve[1:]+curve[:1]))
    if (not _finite(section.get('girth_cm')) or abs(section['girth_cm']-measured) > 1e-7 or
            abs(perimeter-measured) > 1e-7):
        raise StudioError('Fit body girth differs from its measured homologous section')
    return measured


def _region_girth(body_profile, specification, descriptor, landmark):
    """Consume actual oblique limb contours separately from torso heights."""
    declaration = specification.get('body_regions')
    if declaration is None: return None
    if descriptor is None:
        raise StudioError('Fit supplemental body measurements require source remeasurement')
    if (descriptor['specification_ref'] != declaration['specification_ref'] or
            descriptor['supplement_ref'] != declaration['supplement_ref'] or
            descriptor['identity']['profile_sha256'] != digest(body_profile) or
            descriptor['identity']['profile_cache_key'] != body_profile['cache_key']):
        raise StudioError('Fit limb supplement belongs to another exact body profile or policy')
    mapping = declaration['landmark_sections']
    if len({row['body_landmark'] for row in mapping}) != len(mapping):
        raise StudioError('Fit limb measurement cannot ambiguously map a body landmark')
    rows = [row for row in mapping if row['body_landmark'] == landmark]
    if not rows: return None
    found = descriptor['sections'].get(rows[0]['section_id'])
    if found is None: raise StudioError('Fit limb section is absent from its source policy')
    region, section = found['region'], found['section']
    name, separator, side = landmark.rpartition('.')
    if not separator or side != region['side']:
        raise StudioError('Fit limb contour cannot relabel its measured source side')
    expected_domain = {'upper-arm': 'SHOULDER_TO_ELBOW_ONLY',
                       'forearm': 'WRIST_TO_ELBOW_ONLY', 'wrist': 'WRIST_TO_ELBOW_ONLY'}
    if name not in expected_domain or expected_domain[name] != region['domain']:
        raise StudioError('Fit limb contour cannot relabel its anatomical source domain')
    if name == 'wrist':
        sourced = body_profile['landmarks'].get(landmark, {})
        point = sourced.get('point_cm'); basis = body_profile.get('frame', {})
        if not sourced.get('source_ref') or not isinstance(point, list) or len(point) != 3 or not basis:
            raise StudioError('Fit wrist section needs its actual sourced body landmark')
        world = [basis['origin_cm'][i]+sum(point[j]*basis[key][i]
            for j, key in enumerate(('right', 'forward', 'up'))) for i in range(3)]
        parameter = section['parameter']
        endpoint = region.get('axis_start_cm' if parameter == 0 else 'axis_end_cm')
        if (parameter not in (0, 1) or endpoint != section['center_cm'] or
                math.dist(world, section['center_cm']) > 1e-7):
            raise StudioError('Fit wrist girth must use its actual source wrist section')
    if section.get('status') != 'MEASURED' or section.get('ok') is not True: return None
    curve = section['curve_cm']; center = section['center_cm']; normal = section['plane']['normal_world']
    if (len(curve) < 3 or any(len(p) != 3 or any(not _finite(v) for v in p) for p in curve) or
            len(center) != 3 or len(normal) != 3 or any(not _finite(v) for v in center+normal) or
            abs(sum(v*v for v in normal)-1) > 1e-7 or
            any(abs(sum((p[i]-center[i])*normal[i] for i in range(3))) > 1e-7 for p in curve)):
        raise StudioError('Fit limb girth needs its finite actual oblique surface contour')
    perimeter = sum(math.dist(a, b) for a, b in zip(curve, curve[1:]+curve[:1]))
    if not _finite(section['girth_cm']) or abs(perimeter-section['girth_cm']) > 1e-7 or perimeter <= 0:
        raise StudioError('Fit limb girth differs from its measured oblique section')
    return perimeter


def assess_source_fit(compiled, body_profile, specification, body_regions=None):
    """Compare source paths, without declaring spatial coverage or fitting."""
    contract('garment-fit', specification)
    before = digest([compiled, body_profile, specification])
    if compiled.get('status') != 'READY_TO_PLAN' or not compiled.get('assembly_spec'):
        raise StudioError('Fit preflight requires complete approved source compilation')
    if body_profile.get('status') != 'PROFILE_MEASURED' or not body_profile.get('cache_key'):
        raise StudioError('Fit preflight requires an exact measured body profile')
    _profile_identity(body_profile)
    components = set(specification['component_ids'])
    if components-set(row['id'] for row in compiled['components'] if row['pipeline'] == 'PATTERN_SEWN'):
        raise StudioError('Fit classification cannot target undeclared textile components')
    if (compiled.get('source_ref') != specification['dossier_ref'] or
            compiled.get('assembly_spec', {}).get('body_ref') != specification['body_ref']):
        raise StudioError('Fit intent belongs to a different source dossier or body target')
    rows = specification['measurements']
    required = {row['id']: row for row in specification['required_measurements']}
    if len(required) != len(specification['required_measurements']) or len({row['id'] for row in rows}) != len(rows):
        raise StudioError('Fit preflight cannot duplicate a measurement path ID')
    for row in rows:
        if required.get(row['id']) != {key: row[key] for key in ('id', 'component_id', 'layer', 'body_landmark')}:
            raise StudioError('Fit measurement is outside its explicitly required owner/layer/body domain')
    diagnostics = []; checks = []
    required_owners = {row['component_id'] for row in specification['required_measurements']}
    if required_owners-components:
        raise StudioError('Required fit measurements target undeclared components')
    for cid in sorted(components-required_owners):
        diagnostics.append({'code': 'FIT_COMPONENT_MEASUREMENTS_REQUIRED', 'component_id': cid})
    for field, value in specification['classification'].items():
        if value == 'unspecified': diagnostics.append({'code': 'FIT_CLASSIFICATION_REQUIRED', 'field': field})
    if specification['classification']['wearing_configuration'] == 'open_front' and 'open_front' not in specification:
        diagnostics.append({'code': 'OPEN_FRONT_OVERLAP_INTENT_REQUIRED'})
    for name in sorted(set(required)-{row['id'] for row in rows}):
        diagnostics.append({'code': 'FIT_MEASUREMENT_PATH_REQUIRED', **copy.deepcopy(required[name])})
    for measurement in sorted(rows, key=lambda row: row['id']):
        ease = measurement['ease']
        values = [ease[key] for key in ('minimum_cm', 'target_cm', 'maximum_cm', 'movement_cm', 'underlayers_cm', 'style_cm')]
        if (not all(_finite(v) for v in values) or not ease['minimum_cm'] <= ease['target_cm'] <= ease['maximum_cm']
                or abs(ease['movement_cm']+ease['underlayers_cm']+ease['style_cm']-ease['target_cm']) > 1e-8):
            raise StudioError('Explicit ease bounds and movement/underlayers/style breakdown are inconsistent')
        material, spans = _path(compiled, measurement, components)
        landmark = body_profile['landmarks'].get(measurement['body_landmark'], {})
        measured = _girth(landmark)
        if measured is None: measured = _region_girth(body_profile, specification, body_regions, measurement['body_landmark'])
        closed = measurement['path_kind'] == 'closed_girth'
        actual = material-measured if closed and measured is not None else None
        status = ('MISSING_BODY_MEASUREMENT' if measured is None else 'OPEN_SPATIAL_COVERAGE_REQUIRED' if not closed else
                  'BELOW_DECLARED_EASE' if actual < ease['minimum_cm']-1e-8 else
                  'ABOVE_DECLARED_EASE' if actual > ease['maximum_cm']+1e-8 else 'WITHIN_DECLARED_SOURCE_EASE')
        checks.append({'id': measurement['id'], 'component_id': measurement['component_id'], 'layer': measurement['layer'],
            'body_landmark': measurement['body_landmark'], 'measurement_scope': 'NOMINAL_SOURCE_CAPACITY',
            'path_kind': measurement['path_kind'], 'status': status, 'body_girth_cm': measured,
            'source_material_length_cm': material, 'ease_cm': actual,
            'ease_intent': copy.deepcopy(ease), 'source_spans': spans,
            'takeup': copy.deepcopy(measurement['takeup']),
            'closure_state': 'DECLARED_NOMINAL_NOT_OBSERVED' if measurement['engaged_links'] else 'SOURCE_PERMANENT_PATH',
            'homology_source_ref': copy.deepcopy(measurement['homology_source_ref']),
            'spatial_overlap': 'NOT_MEASURED', 'source_uv_scaled': False})
    if any(row['status'] in ('BELOW_DECLARED_EASE', 'ABOVE_DECLARED_EASE') for row in checks): status = 'SOURCE_EASE_MISMATCH'
    elif diagnostics or any(row['status'] != 'WITHIN_DECLARED_SOURCE_EASE' for row in checks): status = 'FIT_PREFLIGHT_INCOMPLETE'
    else: status = 'SOURCE_EASE_COMPARED'
    result = {'version': 1, 'status': status, 'classification': copy.deepcopy(specification['classification']),
        'component_ids': copy.deepcopy(specification['component_ids']),
        'diagnostics': diagnostics, 'checks': checks, 'open_front': copy.deepcopy(specification.get('open_front')),
        'specification_sha256': digest(specification), 'compiled_dossier_sha256': digest(compiled),
        'body_profile_sha256': digest(body_profile), 'body_profile_cache_key': body_profile['cache_key'],
        'qualification': 'SOURCE_DIMENSIONS_ONLY', 'intent_review': 'REQUIRES_CANONICAL_HUMAN_DECISION',
        'spatial_coverage': 'NOT_MEASURED', 'collision_clearance': 'NOT_ASSESSED',
        'dressing': 'NOT_EXECUTED', 'fitting': 'NOT_EXECUTED', 'acceptance': 'NOT_GRANTED',
        'source_mutated': False, 'body_rescaled': False}
    if digest([compiled, body_profile, specification]) != before: raise StudioError('Fit assessment mutated its sources')
    result['assessment_sha256'] = digest(result)
    return result


def assess_project_fit(project, compiled_path, specification_path):
    return assess_compiled_fit(project, read_json(inside(project.root, compiled_path)), specification_path)


def _reviewed(project, state, gate_name, required_refs):
    """An intent decision must review these exact persisted source files."""
    gate = state['gates'].get(gate_name, {})
    if gate.get('source') != 'human' or gate.get('approved') is not True:
        return {'status': 'PENDING', 'gate': gate_name}
    project.require_gate(state, gate_name)
    records = [{key: record[key] for key in ('path', 'sha256')} for record in gate['evidence'].values()]
    if any(reference not in records for reference in required_refs):
        return {'status': 'PENDING_EXACT_REFERENCES', 'gate': gate_name}
    return {'status': 'REVIEWED', 'gate': gate_name, 'decision_id': gate['decision_id'],
            'source_ref': gate['source_ref'], 'statement': gate['statement']}


def _fit_reviews(project, specification, specification_ref):
    state = project.state(); rows = []
    for cid in specification['component_ids']:
        numeric = _reviewed(project, state, 'fit-intent.'+cid,
            [specification_ref, specification['dossier_ref'], specification['body_ref']])
        silhouette_ref = specification.get('silhouette_review_ref', specification['source_ref'])
        silhouette = _reviewed(project, state, 'fit-silhouette.'+cid, [silhouette_ref])
        if silhouette['status'] == 'REVIEWED':
            decision = read_json(inside(project.root, silhouette_ref['path']))
            if (cid not in decision.get('component_ids', []) or
                    decision.get('dossier_ref') != specification['dossier_ref'] or
                    decision.get('body_ref') != specification['body_ref'] or
                    not {'category', 'silhouette_intent'}.issubset(decision.get('approved_scope', [])) or
                    any(decision.get(key) != specification['classification'][key]
                        for key in ('category', 'silhouette_intent'))):
                raise StudioError('Reviewed silhouette belongs to a different classification, source or body')
        rows.append({'component_id': cid, 'silhouette': silhouette, 'numeric_ease': numeric})
    return rows


def require_fit_intent(project, compiled_path, specification_path):
    """Admit exploratory production physics after source and intent review.

    Open-front coverage still needs the exact placed candidate. This admission
    permits that measurement to be executed; it cannot qualify its result.
    """
    result = assess_project_fit(project, compiled_path, specification_path)
    if result['diagnostics'] or not result['checks']:
        raise StudioError('Production garment needs complete classification, homologous paths and explicit ease targets')
    if set(result['component_ids'])-{row['component_id'] for row in result['checks']}:
        raise StudioError('Every production fit component requires its own measured source path')
    admissible = {'WITHIN_DECLARED_SOURCE_EASE', 'OPEN_SPATIAL_COVERAGE_REQUIRED'}
    if any(row['status'] not in admissible for row in result['checks']):
        raise StudioError('Production garment source ease is incompatible or its body measurements are missing')
    if any(row['numeric_ease']['status'] != 'REVIEWED' for row in result['human_reviews']):
        raise StudioError('Production garment numeric ease intent requires an exact human review')
    result['admission'] = 'EXPLORATORY_PHYSICS_ONLY'
    result['assessment_sha256'] = digest({key: value for key, value in result.items() if key != 'assessment_sha256'})
    return result


def assess_compiled_fit(project, compiled, specification_path):
    """Recompile disk sources; a client-signed compiled document is insufficient."""
    from .production_dossier import compile_project_dossier
    source = compiled.get('source_ref', {}); spec_ref = compiled.get('specification_source_ref', {})
    for reference in (source, spec_ref):
        if set(reference) != {'path', 'sha256'} or sha(inside(project.root, reference['path'])) != reference['sha256']:
            raise StudioError('Fit assessment source compilation changed')
    rebuilt = compile_project_dossier(project, source['path'], spec_ref['path'])
    if rebuilt != compiled: raise StudioError('Fit assessment needs the exact recompiled source dossier')
    specification = contract('garment-fit', read_json(inside(project.root, specification_path)))
    references = [specification['source_ref'], specification['dossier_ref'], specification['body_ref']]
    if specification.get('silhouette_review_ref'): references.append(specification['silhouette_review_ref'])
    if specification.get('body_regions'):
        references += [specification['body_regions'][key] for key in ('specification_ref', 'supplement_ref')]
    if specification.get('open_front'): references.append(specification['open_front']['source_ref'])
    for row in specification['measurements']:
        references += [row['homology_source_ref'], row['ease']['source_ref']]
        references += [item['source_ref'] for item in row['takeup']]
    for reference in references:
        if sha(inside(project.root, reference['path'])) != reference['sha256']:
            raise StudioError('Fit intent or homologous measurement provenance changed')
    body = read_json(inside(project.root, specification['body_ref']['path']))
    from .native_evidence import native_origin
    native, origin = native_origin(project, lambda doc:
        (doc.get('operation') == 'prepare_body_target' and
         doc.get('result', {}).get('artifacts', {}).get('profile') == specification['body_ref']) or
        (doc.get('operation') == 'introduce_body_target' and
         doc.get('result', {}).get('profile_ref') == specification['body_ref']))
    if (specification['body_ref'] not in native['files'] or
            native['result'].get('profile_cache_key') != body.get('cache_key')):
        raise StudioError('Fit body profile lacks its exact canonical measured body origin')
    if native['operation'] == 'introduce_body_target':
        from .body_context import body_context_descriptor
        context = body_context_descriptor(project, native['arguments']['context_path'])
        if (context['profile'] != body or context['receipt']['artifacts']['profile'] != specification['body_ref'] or
                context['context_ref'] != native['result']['context'] or
                native['result'].get('status') != 'BODY_TARGET_INTRODUCED' or
                native['result'].get('binding_sha256') != context['binding_sha256'] or
                native['result'].get('body_target_receipt') != context['context']['body_target_receipt'] or
                native['result'].get('source_artifact') != context['receipt']['artifact'] or
                native['result'].get('geometry_ref') != context['receipt']['artifacts']['geometry'] or
                native['result'].get('actual_geometry_sha256') != digest({key: context['geometry'][key]
                    for key in ('vertices_cm', 'faces', 'face_sets')})):
            raise StudioError('Fit introduced body differs from its actual source-bound native context')
    body_regions = None
    if specification.get('body_regions'):
        from .body_region_sections import body_region_descriptor
        regions = specification['body_regions']
        body_regions = body_region_descriptor(project, regions['specification_ref']['path'], regions['supplement_ref'])
    result = assess_source_fit(compiled, body, specification, body_regions)
    if body_regions is not None:
        result['body_region_measurements'] = {key: copy.deepcopy(body_regions[key])
            for key in ('specification_ref', 'supplement_ref', 'identity', 'native_body_origin')}
    result['native_body_origin'] = origin
    result['human_reviews'] = _fit_reviews(project, specification,
        {'path': specification_path, 'sha256': sha(inside(project.root, specification_path))})
    if all(row['numeric_ease']['status'] == 'REVIEWED' for row in result['human_reviews']):
        result['intent_review'] = 'REVIEWED_EXACT_NUMERIC_INTENT'
    result['assessment_sha256'] = digest({key: value for key, value in result.items() if key != 'assessment_sha256'})
    return result
