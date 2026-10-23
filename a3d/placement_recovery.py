"""Pure historical preflight for source-preserving placement recovery.

This module neither mutates geometry nor authenticates native production.
Caller-bound input digests identify observations, not an admission or a receipt.
Search deficits include nearest-clearance and exploratory triangle-plane terms;
they must not be reported as independently measured penetration depth.
"""
import math
import time

from .core import StudioError, digest
from .cloth_metrics import face_sources, triangle_metrics, validate_metrics


def _finite(value):
    return type(value) in (int, float) and math.isfinite(value)


def _index(value, count):
    return type(value) is int and 0 <= value < count


def _vector(value, dimensions):
    return isinstance(value, list) and len(value) in dimensions and all(_finite(x) for x in value)


def _require(condition, message):
    if not condition:
        raise StudioError('Placement recovery preflight: '+message)


def diagnose_placement_recovery(mesh, correction, recipe, source, preparation, *,
                                expected_digests, budgets, clock=time.monotonic):
    """Diagnose exact preserved inputs, without proposing admission or coordinates.

    Supported domain: triangular, pre-consolidation meshes with one source
    panel owner per vertex, explicit source seams and historical native search
    observations. Unknown relationships or ambiguous ownership are refused.
    All five complete input digests are mandatory; no historical archive is
    treated as a current runtime projection or production receipt.
    """
    start = clock()
    _require(isinstance(budgets, dict), 'explicit diagnostic budgets required')
    keys = ('max_vertices', 'max_faces', 'max_seam_pairs', 'max_contacts')
    _require(all(type(budgets.get(k)) is int and budgets[k] > 0 for k in keys)
             and _finite(budgets.get('max_seconds')) and budgets['max_seconds'] > 0,
             'positive finite work budgets required')

    def tick():
        _require(clock()-start <= budgets['max_seconds'], 'diagnostic time budget exhausted')

    inputs = dict(mesh=mesh, correction=correction, recipe=recipe, source=source,
                  preparation=preparation)
    _require(all(isinstance(v, dict) for v in inputs.values()), 'objects required')
    rest, faces, panels, seams = (mesh.get(k) for k in ('rest_cm', 'faces', 'panels', 'seams'))
    coordinates = correction.get('coordinates_cm')
    _require(isinstance(rest, list) and 0 < len(rest) <= budgets['max_vertices'], 'vertex budget or shape')
    _require(isinstance(faces, list) and 0 < len(faces) <= budgets['max_faces'], 'face budget or shape')
    count = len(rest)
    _require(isinstance(panels, dict) and panels and isinstance(seams, dict), 'panels and explicit seams required')
    _require(isinstance(coordinates, list) and len(coordinates) == count
             and isinstance(mesh.get('placed_cm'), list) and len(mesh['placed_cm']) == count,
             'candidate mapping incomplete')
    for points in (rest, coordinates, mesh['placed_cm']):
        _require(all(_vector(p, (3,)) for p in points), 'nonfinite or invalid 3D coordinate')
        tick()
    owners = {}
    for pid, panel in panels.items():
        _require(isinstance(pid, str) and pid and isinstance(panel, dict)
                 and isinstance(panel.get('indices'), list) and panel['indices'], 'invalid panel mapping')
        for index in panel['indices']:
            _require(_index(index, count) and index not in owners, 'ambiguous or missing source vertex owner')
            owners[index] = pid
        _require(isinstance(panel.get('edges', {}), dict), 'invalid source edge mapping')
        panel_ids = set(panel['indices'])
        for edge, indices in panel.get('edges', {}).items():
            _require(isinstance(edge, str) and isinstance(indices, list) and indices
                     and all(_index(i, count) and i in panel_ids for i in indices), 'invalid source edge indices')
        tick()
    _require(len(owners) == count, 'source vertex ownership incomplete')
    for face in faces:
        _require(isinstance(face, list) and len(face) == 3
                 and all(_index(i, count) for i in face) and len(set(face)) == 3, 'invalid triangle indices')
        _require(len({owners[i] for i in face}) == 1, 'triangle crosses an undeclared source panel')
    tick()
    source_seams = source.get('seams')
    _require(isinstance(source.get('pieces'), dict) and set(panels) == set(source['pieces'])
             and isinstance(source_seams, list), 'authoritative source piece/seam mapping required')
    source_by_id = {}
    for seam in source_seams:
        _require(isinstance(seam, dict) and isinstance(seam.get('id'), str)
                 and seam['id'] not in source_by_id, 'duplicate or missing source seam identity')
        source_by_id[seam['id']] = seam
    _require(set(seams) == set(source_by_id), 'derived seams differ from authoritative source seams')
    pair_count = 0
    for sid, seam in seams.items():
        _require(isinstance(seam, dict) and isinstance(seam.get('pairs'), list), 'explicit seam pairs required')
        authoritative = source_by_id[sid]
        _require(all(seam.get(k) == authoritative.get(k) and k in seam and k in authoritative
                     for k in ('kind', 'piece_a', 'piece_b')), 'seam relation changed')
        _require(seam['kind'] in ('permanent', 'detachable', 'closure'), 'unsupported seam kind')
        pair_count += len(seam['pairs'])
        _require(pair_count <= budgets['max_seam_pairs'], 'seam-pair budget exhausted')
        for pair in seam['pairs']:
            _require(isinstance(pair, list) and len(pair) == 2 and all(_index(i, count) for i in pair), 'invalid seam pair indices')
            _require(owners[pair[0]] == seam['piece_a'] and owners[pair[1]] == seam['piece_b'], 'seam pair source ownership changed')
        tick()
    measurement = correction.get('measurement')
    _require(isinstance(measurement, dict), 'historical measurement required')
    contacts = measurement.get('contacts')
    _require(isinstance(contacts, list) and len(contacts) <= budgets['max_contacts'], 'contact budget or shape')
    deficits = measurement.get('score_vertex_deficits_cm')
    _require(isinstance(deficits, dict) and len(deficits) <= count, 'explicit vertex search deficits required')
    for key, value in deficits.items():
        _require(isinstance(key, str) and key.isdigit() and str(int(key)) == key
                 and _index(int(key), count) and _finite(value) and value >= 0, 'invalid vertex search deficit')
    for row in contacts:
        _require(isinstance(row, dict) and _index(row.get('vertex'), count)
                 and _vector(row.get('normal'), (3,))
                 and abs(math.sqrt(sum(x*x for x in row['normal']))-1) <= 1e-6
                 and _finite(row.get('signed_offset_cm')) and _finite(row.get('clearance_cm'))
                 and row['clearance_cm'] >= 0, 'invalid historical contact proposal')
    _require(type(measurement.get('hard_valid')) is bool and _finite(measurement.get('score'))
             and measurement['score'] >= 0, 'invalid historical search score')
    tick()
    _require(isinstance(expected_digests, dict) and set(expected_digests) == set(inputs), 'all exact input identities required')
    observed = {}
    for key, value in inputs.items():
        try:
            observed[key] = digest(value)
        except (ValueError, TypeError) as error:
            raise StudioError('Placement recovery preflight: nonfinite or non-JSON input') from error
        _require(observed[key] == expected_digests[key], 'changed '+key+' input identity')
        tick()
    candidate_id = digest(coordinates)
    _require(correction.get('candidate_sha256') == candidate_id
             and measurement.get('candidate_sha256') == candidate_id
             and digest(mesh['placed_cm']) == candidate_id, 'stale candidate or measurement identity')
    _require(mesh.get('source_garment_sha256') == observed['source'], 'changed authoritative source identity')
    recipe_fields = ('component_id', 'mesh', 'placements', 'seams', 'pins')
    _require(all(k in recipe for k in recipe_fields), 'recipe mesh identity incomplete')
    recipe_identity = {k: recipe[k] for k in recipe_fields}
    for key in ('experimental_prefit', 'trial_mode', 'trial_pieces'):
        if key in recipe and (key != 'trial_pieces' or 'trial_mode' in recipe):
            recipe_identity[key] = recipe[key]
    _require(mesh.get('recipe_mesh_sha256') == digest(recipe_identity), 'changed recipe mesh identity')
    _require(isinstance(mesh.get('component_id'), str) and mesh['component_id']
             and mesh['component_id'] == source.get('component_id') == recipe.get('component_id'), 'component identity changed')
    specification = correction.get('effective_specification')
    _require(isinstance(specification, dict) and isinstance(specification.get('quality'), dict), 'effective quality required')
    limits = specification['quality']
    _require(all(_finite(limits.get(k)) and limits[k] > 0 for k in
                 ('min_angle_degrees', 'min_edge_cm', 'min_stretch', 'max_stretch'))
             and limits['min_stretch'] <= 1 <= limits['max_stretch'], 'invalid effective quality')
    # Never lower the source, regular mesh, or declared correction thresholds.
    for quality in (recipe['mesh'], preparation.get('placement_correction', {}).get('quality', {})):
        for key in ('min_angle_degrees', 'min_edge_cm', 'min_stretch'):
            _require(_finite(quality.get(key)) and limits[key] >= quality[key], 'lowered declared quality')
        _require(_finite(quality.get('max_stretch')) and limits['max_stretch'] <= quality['max_stretch'], 'raised stretch allowance')
    target_angle = preparation.get('regular_mesh', {}).get('target_min_angle_degrees', 15.)
    _require(_finite(target_angle) and target_angle > 0 and limits['min_angle_degrees'] >= target_angle, 'lowered source angle threshold')
    _require(correction.get('declared_specification_sha256') == digest(preparation.get('placement_correction')), 'changed declared correction policy')
    protected = specification.get('protected_indices', [])
    _require(isinstance(protected, list) and all(_index(i, count) for i in protected)
             and len(set(protected)) == len(protected), 'invalid protected anchor indices')
    pins = mesh.get('pins', {})
    _require(isinstance(pins, dict), 'invalid pin mapping')
    protected = set(protected)
    for key, value in pins.items():
        _require(isinstance(key, str) and key.isdigit() and str(int(key)) == key
                 and _index(int(key), count) and _finite(value) and 0 <= value <= 1, 'invalid pin support')
        if value > 0:
            protected.add(int(key))
    declared_protected = preparation['placement_correction'].get('protected_indices', [])
    _require(isinstance(declared_protected, list)
             and all(_index(i, count) and i in protected for i in declared_protected), 'declared protected support omitted')
    recovery = preparation.get('metric_recovery', {})
    _require(isinstance(recovery, dict) and isinstance(recovery.get('protected_edges', []), list), 'invalid metric recovery support policy')
    for stop in recovery.get('protected_edges', []):
        _require(isinstance(stop, dict) and stop.get('piece') in panels
                 and stop.get('edge') in panels[stop['piece']].get('edges', {}), 'missing protected source edge')
        edge = panels[stop['piece']]['edges'][stop['edge']]
        _require(edge[0] in protected and edge[-1] in protected, 'protected source edge endpoint omitted')
    for name in ('source_rest_triangles_cm', 'source_face_pieces', 'source_face_vertex_ids'):
        if name in mesh:
            _require(isinstance(mesh[name], list) and len(mesh[name]) == len(faces), 'incomplete source face binding')
    for triangle in mesh.get('source_rest_triangles_cm', []):
        _require(isinstance(triangle, list) and len(triangle) == 3
                 and all(_vector(point, (2, 3)) for point in triangle), 'invalid source rest triangle')
    for indices in mesh.get('source_face_vertex_ids', []):
        _require(isinstance(indices, list) and len(indices) == 3
                 and all(type(i) is int for i in indices) and len(set(indices)) == 3,
                 'invalid source face vertex identity')
    _require(all(isinstance(pid, str) and pid in panels for pid in mesh.get('source_face_pieces', [])),
             'invalid source face piece identity')
    binding = face_sources(mesh)
    _require(not binding['binding_issues'] and all(p in panels for p in binding['source_face_pieces']), 'ambiguous source triangle binding')
    worst = None
    bad_count = 0
    for fid, (face, triangle, pid) in enumerate(zip(faces, binding['source_rest_triangles_cm'], binding['source_face_pieces'], strict=True)):
        quality = triangle_metrics(triangle)
        if worst is None or quality['min_angle_degrees'] < worst['min_angle_degrees']:
            worst = dict(face=fid, piece=pid, vertices=list(face), source_uv_cm=triangle,
                         min_angle_degrees=quality['min_angle_degrees'])
        if quality['min_angle_degrees'] < limits['min_angle_degrees'] or quality['area_cm2'] < 1e-8:
            bad_count += 1
        if fid % 256 == 0:
            tick()
    try:
        metric = validate_metrics(mesh, coordinates, limits, include_faces=False, include_bending=False)
    except StudioError as error:
        if not hasattr(error, 'quality_metrics'):
            raise
        metric = error.quality_metrics
    tick()
    anchor_rows = [dict(vertex=i, piece=owners[i], search_deficit_cm=deficits[str(i)])
                   for i in sorted(protected) if deficits.get(str(i), 0) > 0]
    # Actual permanent pairs define vertex cohorts. Detachable relations never union.
    parent = {}
    def root(i):
        parent.setdefault(i, i)
        while parent[i] != i:
            parent[i] = parent[parent[i]]
            i = parent[i]
        return i
    for seam in seams.values():
        if seam['kind'] == 'permanent':
            for a, b in seam['pairs']:
                ra, rb = root(a), root(b)
                parent[max(ra, rb)] = min(ra, rb)
    groups = {}
    for i in sorted(parent):
        groups.setdefault(root(i), []).append(i)
    cohort_gap = {}
    for seam in seams.values():
        if seam['kind'] == 'permanent':
            for a, b in seam['pairs']:
                rid = root(a)
                cohort_gap[rid] = max(cohort_gap.get(rid, 0.), math.dist(coordinates[a], coordinates[b]))
    cohorts = [dict(vertices=ids, pieces=sorted({owners[i] for i in ids}),
                    protected_vertices=sorted(protected.intersection(ids)),
                    historical_max_permanent_pair_gap_cm=cohort_gap.get(rid, 0.))
               for rid, ids in sorted(groups.items())]
    actions = []
    if bad_count:
        actions.append('REMESH_DERIVED_REST')
    if anchor_rows:
        actions.append('PREPARE_ADMISSIBLE_GUIDE_ANCHORS')
    if not actions and not metric.get('violations'):
        actions.append('RUN_BOUNDED_RECOVERY')
    elif not actions:
        actions.append('REPAIR_SOURCE_GUIDE_METRIC')
    _require(all(digest(inputs[k]) == observed[k] for k in inputs), 'immutable input mutated')
    tick()
    return dict(version=1, status='DIAGNOSTIC_ONLY', qualification='NONE', admitted=False,
                scope='HISTORICAL_EXACT_INPUT_PREFLIGHT_NOT_NATIVE_PRODUCTION_AUTHENTICATION',
                identities=observed, candidate_sha256=candidate_id,
                pre_correction_source_payload_sha256=correction.get('source_sha256'),
                pre_correction_source_payload_authentication='NOT_RECONSTRUCTED_FROM_FINAL_MESH',
                source_rest=dict(worst_face=worst, inadmissible_faces=bad_count, angle_threshold_degrees=limits['min_angle_degrees']),
                candidate_metrics=metric, protected_anchors=dict(total=len(protected), deficits=anchor_rows),
                search_deficit_scope='HISTORICAL_NEAREST_CLEARANCE_AND_EXPLORATORY_CONTACT_PLANE_SEARCH_DEFICITS_NOT_PENETRATION_DEPTH',
                overall_score_scope='VERTEX_DEFICITS_PLUS_PERMANENT_GAP_AND_SELF_CONTACT_TERMS',
                permanent_vertex_cohorts=cohorts, next_actions=actions, source_mutated=False,
                native_execution='NOT_EXECUTED', simulation='NOT_EXECUTED', fitting='NOT_EXECUTED',
                final_readiness='UNCHANGED_NATIVE_PREPARATION_VALIDATOR_REQUIRED', budgets=dict(budgets))
