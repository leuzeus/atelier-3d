"""Complete source-bound guide dispatch for a measured body.

Torso and belt guides retain their existing algorithms. Limb guides bind the
actual paired source sewing boundaries through a refined source-UV cage.
Collar, central
inner front, hood and yoke use explicit source anchor edges and measured body
surfaces. Planar and developable guides are starting hypotheses; curved hood
and shoulder drape require the subsequent metric/contact solver and Cloth.
No missing piece, side, grain axis or source contour is manufactured here.
"""
import copy
import math
from fractions import Fraction

from .anatomy_profile import unit
from .contact_geometry import cross, dot
from .core import StudioError, digest
from .preform_volume import half_ellipse, sample_curve, extend_tangent
from .semantic_placement import torso_volume_frames, belt_volume_frames
from .sewing import edge_chain, sample_chain


SPECIAL_ROLES = {'collar', 'inner_front', 'hood', 'yoke'}


def _vector(value, name, *, nonzero=True):
    if (not isinstance(value, (list, tuple)) or len(value) != 3 or
            any(type(x) not in (int, float) or not math.isfinite(x) for x in value) or
            (nonzero and math.fsum(x*x for x in value) <= 1e-20)):
        raise StudioError('Anatomical guide requires a finite '+name)
    return list(value)


def _fraction(value, name):
    if type(value) not in (int, float) or not math.isfinite(value) or not 0 <= value <= 1:
        raise StudioError('Anatomical guide requires an explicit '+name+' in [0, 1]')
    return value


def _declared_anchor(piece, policy):
    name = policy.get('source_anchor_edge')
    if name not in piece.get('edges', {}):
        raise StudioError('Anatomical guide needs an actual named source attachment edge')
    return sample_chain(edge_chain(piece, name)[1],
                        _fraction(policy.get('source_anchor_fraction'), 'source attachment fraction'))


def _path_reference(references, name, pid):
    path = references.get('paths', {}).get(name)
    if not path:
        raise StudioError('Anatomical path reference is unavailable for '+pid+': '+str(name))
    return path


def _validate_limb_region(reference, semantic, axis_names, pid):
    """A selected path label cannot silently invert a lateral source part."""
    region = reference.get('region')
    side = semantic.get('side')
    if not isinstance(region, str) or not region:
        raise StudioError('Limb attachment requires an explicit anatomical region: '+pid)
    if region.startswith('custom:'):
        if not region[7:].strip():
            raise StudioError('Custom limb attachment region must be explicitly named')
    else:
        suffix = region.rsplit('.', 1)[-1]
        if suffix in ('left', 'right') and suffix != side:
            raise StudioError('Limb attachment body-region side contradicts its source semantic side: '+pid)
        if semantic.get('role') in ('sleeve', 'cuff') and not region.startswith(('upper_arm.', 'lower_arm.', 'hand.')):
            raise StudioError('Sleeve or cuff attachment requires an explicitly selected arm/hand region: '+pid)
    for name in axis_names:
        suffix = name.rsplit('.', 1)[-1]
        if suffix in ('left', 'right') and suffix != side:
            raise StudioError('Limb axis landmark side contradicts its source semantic side: '+pid)


def anatomical_attachment_controls(data, frames, references):
    """Immutable source-UV constraints, distinct from numerical seam anchors.

    Bind a limb's actual named attachment point. A band additionally retains
    all existing cage controls on its declared attachment edge. An interior
    edge fraction can use barycentric support; the coupled solver reports that
    conservative support explicitly instead of pretending it is a mesh vertex.
    """
    from .pattern_assembly import _compile_cage, _cage_point
    from .sewing import segment_distance
    constraints = []
    for pid, policy in sorted((references or {}).get('pieces', {}).items()):
        kind = policy.get('guide_kind')
        if pid not in frames or kind not in ('PATH_BAND_V1', 'LIMB_ATTACHMENT_V1'):
            continue
        piece = data['pieces'][pid]; frame = frames[pid]
        controls = [_declared_anchor(piece, policy)]
        if kind == 'PATH_BAND_V1':
            chain = edge_chain(piece, policy['source_anchor_edge'])[1]
            controls.extend(uv for uv in frame['uv_cm'] if any(
                segment_distance(uv, a, b) <= 1e-9 for a, b in zip(chain, chain[1:])))
        controls = sorted(set(tuple(uv) for uv in controls))
        compiled = _compile_cage(frame, pid)
        path_name = policy['path_ref'] if kind == 'PATH_BAND_V1' else policy['attachment_path_ref']
        path = references['paths'][path_name]
        for uv in controls:
            constraints.append({'piece': pid, 'source_uv_cm': list(uv),
                'target_world_cm': _cage_point(frame, compiled, uv, pid)[0],
                'tolerance_cm': 1e-7, 'source_ref': 'anatomical-path:'+path['path_sha256']+
                    '; source-edge:'+policy['source_anchor_edge']})
    return constraints


def anatomical_attachment_residuals(frames, constraints):
    from .pattern_assembly import _compile_cage, _cage_point
    compiled = {}; records = []; invalid = []
    for row in constraints:
        pid = row['piece']
        if pid not in compiled:
            compiled[pid] = _compile_cage(frames[pid], pid)
        observed = _cage_point(frames[pid], compiled[pid], row['source_uv_cm'], pid)[0]
        distance = math.dist(observed, row['target_world_cm'])
        record = {**row, 'observed_world_cm': observed, 'residual_cm': distance,
                  'status': 'PRESERVED' if distance <= row['tolerance_cm'] else 'ANATOMICAL_ATTACHMENT_DRIFT'}
        records.append(record)
        if distance > row['tolerance_cm']:
            invalid.append(record)
    return {'status': 'ANATOMICAL_ATTACHMENT_DRIFT' if invalid else 'ANATOMICAL_ATTACHMENTS_PRESERVED',
        'controls': records, 'violations': len(invalid), 'max_residual_cm': max(
            (row['residual_cm'] for row in records), default=0.), 'qualification': 'CONSTRAINT_RESIDUALS_ONLY'}


def _path_knot_partition(piece, axis, cuts, pid, evaluate, budget, source_ref):
    """Partition original material faces with exact rational shared identities."""
    from .guide_cage_sampling import _strips, _ears, validated_cage_state
    _source_limb_mesh(piece, 1)
    source = [tuple(Fraction(value) for value in point) for point in piece['vertices']]
    rows = sorted(set(Fraction(value) for value in cuts))
    controls = {}; uv = []; triangles = []; owners = []
    source_corners = {point: list(original) for point, original in zip(source, piece['vertices'])}

    def control(point):
        if point not in controls:
            budget.reserve(1, 0)
            controls[point] = len(uv)
            uv.append(source_corners.get(point, [float(value) for value in point]))
        return controls[point]

    for source_id, face in sorted(enumerate(piece['faces']), key=lambda row: tuple(sorted(row[1]))):
        budget.check()
        for cell in _strips([source[i] for i in face], axis, rows, budget):
            for triangle in _ears(cell, budget):
                budget.reserve(0, 1)
                triangles.append([control(point) for point in triangle]); owners.append(source_id)
    targets = []
    for point in uv:
        budget.check(); targets.append(evaluate(point))
    frame = {'source_ref': source_ref, 'uv_cm': uv, 'target_cm': targets, 'triangles': triangles}
    state = validated_cage_state(piece, frame, pid, 1, budget, evaluate,
                                 reserved=True, source_faces=owners)
    return frame, {'cut_axis': 'u' if axis == 0 else 'v', 'path_knot_cuts_cm': list(cuts),
        'control_vertices': len(uv), 'control_triangles': len(triangles),
        'triangle_source_face_indices': state['triangle_source_faces'],
        'source_uv_scaled': False, 'source_topology_changed': False,
        'source_boundary_validation': 'EXACT_SOURCE_SEGMENTS_COVERED_ONCE',
        'budgets': dict(budget.limits), 'qualification': 'NONE'}


def anatomical_band_frame(piece, policy, profile, references, pid, *, subdivisions=8):
    """Map source material onto an explicitly selected 3D attachment curve.

    Uniform expansion changes the auxiliary path, never the source pattern.
    Unit transverse fibres preserve material height at every sampled U. An
    arbitrary nonplanar loop is not developable: its remaining shear/stretch
    must be measured by the unchanged material gate before it can be admitted.
    """
    from .anatomical_placement import path_frames, sample_path
    reference = _path_reference(references, policy.get('path_ref'), pid)
    if reference['closed'] is not True:
        raise StudioError('Path band requires an explicitly closed measured attachment path')
    axis = policy.get('material_axis')
    if axis not in ('u', 'v'):
        raise StudioError('Path band requires its explicit circumferential material axis')
    along = 0 if axis == 'u' else 1; across = 1-along
    anchor = _declared_anchor(piece, policy)
    phase = _fraction(policy.get('path_anchor_fraction'), 'body path anchor fraction')
    path_direction = policy.get('path_direction', 1)
    if type(path_direction) is not int or path_direction not in (-1, 1):
        raise StudioError('Path band direction must be the explicit integer +1 or -1')
    normal = _vector(policy.get('longitudinal_direction_body'), 'band longitudinal direction')
    width = max(p[along] for p in piece['vertices'])-min(p[along] for p in piece['vertices'])
    maximum = policy.get('max_path_expansion_ratio')
    if (type(maximum) not in (int, float) or not math.isfinite(maximum) or not 1 <= maximum <= 2 or
            width <= 1e-8 or not 1-1e-10 <= width/reference['length_cm'] <= maximum):
        raise StudioError('Source band circumference lies outside the declared measured-path expansion domain')
    if policy.get('surface_offset_cm', 0.) != 0:
        raise StudioError('Path band offset must be expressed by an explicit reviewed path, not an implicit extra ease')
    points = reference['points_body_cm']
    samples = sample_path(points, [i/128 for i in range(128)], closed=True)
    center = [math.fsum(p[k] for p in samples)/len(samples) for k in range(3)]
    scale = width/reference['length_cm']
    expanded = [[center[k]+scale*(p[k]-center[k]) for k in range(3)] for p in points]
    transverse_field = policy.get('transverse_field', 'SEGMENT_ORTHOGONAL_V1')
    sampling = policy.get('cage_sampling', 'SOURCE_TRIANGLE_GRID_V1')
    if sampling not in ('SOURCE_TRIANGLE_GRID_V1', 'PATH_KNOT_PARTITION_V1'):
        raise StudioError('Path band requires a supported explicit cage sampling mode')
    source_ref = ('measured-body-profile:'+profile['cache_key']+'; source-piece:'+pid+
                  '; measured-path:'+reference['path_sha256']+'; SOURCE_PATH_BAND_V1')
    partition = None
    if sampling == 'PATH_KNOT_PARTITION_V1':
        import time
        from .source_seam_coupling import _Budget
        if transverse_field != 'BODY_DIRECTION_CONSTANT_V1':
            raise StudioError('Path-knot band partition requires BODY_DIRECTION_CONSTANT_V1')
        # A constant direction parallel to any segment collapses that complete
        # material strip, even if no control happened to sample its interior.
        lengths = [math.dist(a, b) for a, b in zip(expanded, expanded[1:]+expanded[:1])]
        total = math.fsum(lengths); cumulative = 0.; knots = []
        for length in lengths:
            knots.append(cumulative/total); cumulative += length
        path_frames(expanded, [(fraction+length/(2*total)) % 1.
                    for fraction, length in zip(knots, lengths)], closed=True,
                    reference_normal=normal, transverse_field=transverse_field)
        lower = min(p[along] for p in piece['vertices']); upper = max(p[along] for p in piece['vertices'])
        cuts = sorted(set(anchor[along]+path_direction*(fraction-phase+wrap)*width
                          for fraction in knots for wrap in (-1, 0, 1)
                          if lower < anchor[along]+path_direction*(fraction-phase+wrap)*width < upper))

        def evaluate(point):
            fraction = (phase+path_direction*(point[along]-anchor[along])/width) % 1.
            row = path_frames(expanded, [fraction], closed=True, reference_normal=normal,
                              transverse_field=transverse_field)[0]
            return _world(profile, [row['point_cm'][k]+(point[across]-anchor[across])*row['normal'][k]
                                    for k in range(3)])

        frame, partition = _path_knot_partition(piece, along, cuts, pid, evaluate,
                                                _Budget(None, time.monotonic),
                                                source_ref+'; PATH_KNOT_PARTITION_V1')
    else:
        uv, triangles = _source_limb_mesh(piece, subdivisions)
        fractions = [(phase+path_direction*(p[along]-anchor[along])/width) % 1. for p in uv]
        oriented = path_frames(expanded, fractions, closed=True, reference_normal=normal,
                               transverse_field=transverse_field)
        target = [_world(profile, [row['point_cm'][k]+(p[across]-anchor[across])*row['normal'][k]
                                  for k in range(3)]) for p, row in zip(uv, oriented)]
        frame = {'source_ref': source_ref, 'uv_cm': uv, 'target_cm': target, 'triangles': triangles}
    return frame, {'piece': pid, 'guide_kind': 'SOURCE_PATH_BAND_V1',
        'path_sha256': reference['path_sha256'], 'body_path_length_cm': reference['length_cm'],
        'source_circumference_cm': width, 'auxiliary_path_expansion_ratio': scale,
        'auxiliary_path_expansion_center_body_cm': center,
        'path_geometry_policy': 'SOURCE_WIDTH_EXPANSION_OF_MEASURED_3D_SHAPE_NOT_A_NEW_BODY_MEASUREMENT',
        'path_discretization': 'SOURCE_TRIANGLE_CAGE_SAMPLING_REQUIRES_FINAL_METRIC_AND_CONTACT_CHECKS',
        'source_anchor_uv_cm': anchor, 'path_anchor_fraction': phase, 'path_direction': path_direction,
        **({'transverse_field': transverse_field} if 'transverse_field' in policy else {}),
        **({'cage_sampling': sampling} if 'cage_sampling' in policy else {}),
        **({'path_knot_partition': partition} if partition is not None else {}),
        'longitudinal_direction_body': normal, 'material_height_policy': 'UNIT_TRANSVERSE_FIBRES',
        'source_contour_sha256': digest(piece), 'source_uv_scaled': False,
        'body_rescaling': False, 'surface_following': 'ACTUAL_THREE_DIMENSIONAL_PATH',
        'metric_assessment': 'REQUIRED_NONPLANAR_PATH_MAY_SHEAR',
        'contact_assessment': 'REQUIRED', 'qualification': 'NONE'}


def permanent_component_pieces(data, seeds):
    """Expand exact permanent graph connectivity, never detachable relations."""
    if (not isinstance(seeds, list) or not seeds or len(set(seeds)) != len(seeds) or
            not set(seeds) <= set(data.get('pieces', {}))):
        raise StudioError('Permanent component expansion needs distinct actual source seed pieces')
    selected = set(seeds)
    relations = [s for s in data.get('seams', []) if s.get('kind') == 'permanent']
    for relation in relations:
        if any(relation.get('piece_'+side) not in data['pieces'] for side in ('a', 'b')):
            raise StudioError('Permanent source relation names a nonexistent source piece')
    while True:
        previous = set(selected)
        for relation in relations:
            pair = {relation['piece_a'], relation['piece_b']}
            if pair & selected:
                selected.update(pair)
        if previous == selected:
            return sorted(selected)


def _source_span(piece, v):
    """Unique material interval at V, including real horizontal boundary stops."""
    hits = []; horizontal = []
    points = piece['vertices']
    for a, b in zip(points, points[1:]+points[:1]):
        if abs(a[1]-b[1]) <= 1e-12:
            if abs(v-a[1]) <= 1e-10:
                hits.extend((a[0], b[0]))
                horizontal.append(sorted((a[0], b[0])))
        elif min(a[1], b[1])-1e-10 <= v <= max(a[1], b[1])+1e-10:
            fraction = (v-a[1])/(b[1]-a[1])
            hits.append(a[0]+fraction*(b[0]-a[0]))
    intervals = []
    for lo, hi in sorted(horizontal):
        if intervals and lo <= intervals[-1][1]+1e-9:
            intervals[-1][1] = max(intervals[-1][1], hi)
        else:
            intervals.append([lo, hi])
    hits = [p for p in hits if not any(lo+1e-9 < p < hi-1e-9 for lo, hi in intervals)]
    unique = []
    for value in sorted(hits):
        if not unique or abs(value-unique[-1]) > 1e-9:
            unique.append(value)
    if not unique or len(unique) > 2:
        raise StudioError('Limb cage needs a single actual source material interval at V')
    return unique[0], unique[-1]


def _source_limb_mesh(piece, subdivisions):
    """Refine existing triangles only; never triangulate a new material domain."""
    vertices = piece.get('vertices'); faces = piece.get('faces')
    if (not vertices or len(vertices) > 5000 or any(len(p) != 2 or
            any(type(v) not in (int, float) or not math.isfinite(v) for v in p) for p in vertices)
            or not faces or len(faces)*subdivisions**2 > 32768):
        raise StudioError('Limb cage requires finite actual source triangles within its fixed face budget')
    boundary = {tuple(sorted((i, (i+1) % len(vertices)))) for i in range(len(vertices))}
    edges = {}; directions = {}; area = 0.
    polygon_area = math.fsum(a[0]*b[1]-b[0]*a[1] for a, b in zip(vertices, vertices[1:]+vertices[:1]))/2
    seen = set()
    for face in faces:
        if (len(face) != 3 or len(set(face)) != 3 or any(type(i) is not int or not 0 <= i < len(vertices) for i in face)
                or tuple(sorted(face)) in seen):
            raise StudioError('Limb cage requires unique valid existing source triangles')
        seen.add(tuple(sorted(face))); a, b, c = [vertices[i] for i in face]
        determinant = (b[0]-a[0])*(c[1]-a[1])-(b[1]-a[1])*(c[0]-a[0])
        if determinant*polygon_area <= 1e-12:
            raise StudioError('Limb cage source triangle winding or material area is invalid')
        area += determinant/2
        for i, j in zip(face, face[1:]+face[:1]):
            edge = tuple(sorted((i, j))); edges[edge] = edges.get(edge, 0)+1
            directions[edge] = directions.get(edge, 0)+(1 if i < j else -1)
    if (abs(area-polygon_area) > max(1e-7, abs(polygon_area)*1e-10)
            or {e for e, count in edges.items() if count == 1} != boundary
            or any(count not in (1, 2) or (count == 2 and directions[e] != 0) for e, count in edges.items())):
        raise StudioError('Limb cage source triangles must cover the actual material boundary once')
    # A key uses integer barycentric source weights. Adjacent source faces
    # therefore share exactly the same UV control vertices at their common edge.
    controls = {}; triangles = []
    # Preserve the exact binary64 material source until the final conversion.
    # fsum(source * weight) cannot recover rounding already introduced by
    # each multiplication; on oblique boundaries that can put a control off
    # its source segment even though its integer barycentric identity is right.
    exact_vertices = [tuple(Fraction(value) for value in point) for point in vertices]
    for face in sorted(faces, key=lambda f: tuple(sorted(f))):
        grid = {}
        for i in range(subdivisions+1):
            for j in range(subdivisions+1-i):
                weights = (subdivisions-i-j, i, j)
                key = tuple(sorted((index, weight) for index, weight in zip(face, weights) if weight))
                if key not in controls:
                    controls[key] = [float(sum(exact_vertices[index][k]*weight for index, weight in key)/subdivisions)
                                     for k in (0, 1)]
                grid[i, j] = key
        for i in range(subdivisions):
            for j in range(subdivisions-i):
                triangles.append([grid[i, j], grid[i+1, j], grid[i, j+1]])
                if j < subdivisions-i-1:
                    triangles.append([grid[i+1, j], grid[i+1, j+1], grid[i, j+1]])
    ordered = sorted(controls); indices = {key: index for index, key in enumerate(ordered)}
    return [controls[key] for key in ordered], [[indices[key] for key in face] for face in triangles]


def _limb_chain(piece, name):
    indices = piece.get('edges', {}).get(name)
    if (not indices or len(indices) < 2 or any(type(i) is not int or not 0 <= i < len(piece['vertices']) for i in indices)):
        raise StudioError('Limb cage source relation must name valid original boundary vertices')
    return edge_chain(piece, name)[1]


def _paired_limb_boundary(data, pid):
    seams = [row for row in data.get('seams', []) if row.get('kind') == 'permanent'
             and row.get('piece_a') == row.get('piece_b') == pid]
    if len(seams) != 1 or seams[0].get('orientation') not in ('forward', 'reverse'):
        raise StudioError('Limb cage requires one explicit unary permanent source sewing relation: '+pid)
    seam = seams[0]; piece = data['pieces'][pid]
    if not isinstance(seam.get('id'), str) or not seam['id']:
        raise StudioError('Limb cage requires the original stable source sewing ID')
    a = _limb_chain(piece, seam.get('edge_a')); b = _limb_chain(piece, seam.get('edge_b'))
    if seam['orientation'] == 'reverse':
        b = list(reversed(b))
    lengths = [[math.dist(x, y) for x, y in zip(chain, chain[1:])] for chain in (a, b)]
    if any(not sizes or min(sizes) <= 1e-10 for sizes in lengths):
        raise StudioError('Limb sewing source chain is collapsed')
    totals = [math.fsum(sizes) for sizes in lengths]
    if abs(totals[0]-totals[1]) > 1e-7:
        raise StudioError('Limb cage cannot infer easing between unequal source sewing chains')
    partitions = []
    for sizes, total in zip(lengths, totals):
        offset = 0.; fractions = [0.]
        for size in sizes:
            offset += size; fractions.append(offset/total)
        partitions.append(fractions)
    if (len(partitions[0]) != len(partitions[1]) or
            any(abs(x-y) > 1e-10 for x, y in zip(*partitions))):
        raise StudioError('Limb cage cannot infer unmatched source sewing corner partitions; a synchronized source guide is required')
    spans = []; records = []
    for fraction in partitions[0]:
        x, y = [sample_chain(chain, fraction) for chain in (a, b)]
        if abs(x[1]-y[1]) > 1e-8:
            raise StudioError('Limb cage requires source sewing partners at the same material V; oblique source pairing is unsupported')
        lo, hi = _source_span(piece, x[1])
        if (hi-lo <= 1e-10 or abs(min(x[0], y[0])-lo) > 1e-8 or abs(max(x[0], y[0])-hi) > 1e-8):
            raise StudioError('Limb sewing partners must bound the actual source material interval')
        spans.append(hi-lo); records.append({'fraction_a': fraction,
            'fraction_b': fraction if seam['orientation'] == 'forward' else 1-fraction,
            'source_v_cm': x[1], 'source_uv_pair_cm': [x, y]})
    for chain in (a, b):
        deltas = [y[1]-x[1] for x, y in zip(chain, chain[1:])]
        if not deltas or min(deltas)*max(deltas) <= 0:
            raise StudioError('Limb source sewing chains must have a strict monotonic material V domain')
    return seam, records, spans


def validate_limb_parameterization(value):
    if type(value) is not str or value not in ('SOURCE_ROW_CIRCUMFERENCE_V1', 'SOURCE_SEWN_DOMAIN_V1'):
        raise StudioError('Unsupported limb surface parameterization')


def limb_volume_frames(data, semantics, profile, *, cage_subdivisions=8, anatomical_references=None,
                       limb_parameterization='SOURCE_ROW_CIRCUMFERENCE_V1', source_cage_budgets=None):
    """Seam-bound auxiliary cages for explicit sleeves and cuffs.

    Actual source faces receive uniform integer barycentric refinement. Their
    targets use each real horizontal material span, rather than the bounding
    box width. Equal normalized source sewing partners share the same target
    boundary polyline. This is a geometric starting hypothesis: neither metric
    admission, anatomical homology, skin contact nor fitting is granted here.
    """
    validate_limb_parameterization(limb_parameterization)
    sewn_domain_mode = limb_parameterization == 'SOURCE_SEWN_DOMAIN_V1'
    if sewn_domain_mode:
        import time
        from .source_seam_coupling import _Budget
        from .limb_surface_sampling import compile_sewn_domain, sewn_domain_interval, sewn_domain_cage
        source_budget = _Budget(source_cage_budgets, time.monotonic)
        source_points = source_faces = 0
    _profile(profile)
    if set(semantics) != set(data['pieces']):
        raise StudioError('Limb cages require exact source semantic coverage')
    if type(cage_subdivisions) is not int or not 2 <= cage_subdivisions <= 16:
        raise StudioError('Limb cage subdivisions must be an explicit integer in 2..16')
    original = digest([data, semantics, profile]); frames = {}; evidence = []; pending = []
    for pid, semantic in sorted(semantics.items()):
        policy = (anatomical_references or {}).get('pieces', {}).get(pid, {})
        attachment = policy.get('guide_kind') == 'LIMB_ATTACHMENT_V1'
        segment_axis = policy.get('guide_kind') == 'LIMB_SEGMENT_AXIS_V1'
        if semantic.get('role') not in ('sleeve', 'cuff') and not (attachment or segment_axis):
            pending.append(pid); continue
        side = semantic.get('side')
        if side not in (('left', 'right', 'center') if (attachment or segment_axis) else ('left', 'right')) or semantic.get('longitudinal_uv_axis') != 'v':
            raise StudioError('Limb cage requires an explicit anatomical side and longitudinal material V axis: '+pid)
        piece = data['pieces'][pid]
        if sewn_domain_mode:
            source_budget.check()
            source_points += len(piece.get('vertices', [])); source_faces += len(piece.get('faces', []))
            if (source_points > source_budget.limits['max_source_points']
                    or source_faces > source_budget.limits['max_source_triangles']):
                raise StudioError('Sewn limb source point or triangle budget exhausted')
            _source_limb_mesh(piece, 1)
        else:
            uv, triangles = _source_limb_mesh(piece, cage_subdivisions)
        seam, pairs, spans = _paired_limb_boundary(data, pid)
        if sewn_domain_mode:
            sewn_domain = compile_sewn_domain(piece, pairs, pid, source_budget)
        axis_names = policy.get('axis_landmarks') if (attachment or segment_axis) else ['shoulder.'+side, 'wrist.'+side]
        if (not isinstance(axis_names, list) or len(axis_names) != 2 or
                any(not isinstance(name, str) or not name for name in axis_names)):
            raise StudioError('Limb attachment requires explicit proximal/distal axis landmarks: '+pid)
        if attachment:
            _validate_limb_region(_path_reference(anatomical_references, policy.get('attachment_path_ref'), pid),
                                  semantic, axis_names, pid)
        segment_binding = None
        if segment_axis:
            from .limb_axis_binding import resolve_segment_axis, segment_center
            segment_binding = resolve_segment_axis(piece, profile, policy)
            _validate_limb_region({'region': policy['anatomical_region']}, semantic, axis_names, pid)
        shoulder, wrist = [profile['landmarks'].get(name, {}).get('point_cm') for name in axis_names]
        if any(not isinstance(point, (list, tuple)) or len(point) != 3 or
               any(type(v) not in (int, float) or not math.isfinite(v) for v in point) for point in (shoulder, wrist)):
            raise StudioError('Limb cages require finite measured shoulder and wrist landmarks')
        if segment_binding is not None:
            downward = segment_binding['downward_body']
            transverse = segment_binding['transverse_body']
            tangent = segment_binding['tangent_body']
        else:
            downward = unit([b-a for a, b in zip(shoulder, wrist)])
            forward = _vector(policy.get('transverse_direction_body'), 'limb transverse direction') if attachment else [0., 1., 0.]
            projection = dot(forward, downward)
            transverse = unit([forward[i]-projection*downward[i] for i in range(3)])
            tangent = unit(cross(downward, transverse))
        v_lo = min(p[1] for p in piece['vertices']); v_hi = max(p[1] for p in piece['vertices'])
        cuff_policy = None
        if semantic['role'] == 'cuff' and not segment_axis:
            declared = semantic.get('guide_edges', {}); stops = {}
            for name in ('distal', 'proximal'):
                edge = declared.get(name)
                if edge not in piece.get('edges', {}):
                    raise StudioError('Cuff cage requires its explicit existing distal/proximal source edges')
                values = [p[1] for p in _limb_chain(piece, edge)]
                if max(values)-min(values) > 1e-7:
                    raise StudioError('Cuff cage source distal/proximal edges must have constant V')
                stops[name] = values[0]
            if abs(stops['proximal']-stops['distal']) <= 1e-8 or sorted(stops.values()) != [v_lo, v_hi]:
                raise StudioError('Cuff cage source anchors must bound its nonzero longitudinal domain')
            sign = 1 if stops['proximal'] > stops['distal'] else -1
            cuff_policy = {'distal_edge': declared['distal'], 'proximal_edge': declared['proximal'],
                'distal_source_v_cm': stops['distal'], 'proximal_source_v_cm': stops['proximal'],
                'body_distal_anchor': axis_names[1], 'proximal_direction': ('TOWARD_DECLARED_PROXIMAL_AXIS_LANDMARK'
                    if attachment else 'TOWARD_SOURCE_SHOULDER'),
                'source_orientation': 'EXPLICIT_NAMED_EDGES', 'source_v_sign': sign}

        def center(v):
            if segment_binding is not None:
                return segment_center(segment_binding, v)
            offset = v_hi-v if cuff_policy is None else -(v-stops['distal'])*sign
            anchor = shoulder if cuff_policy is None else wrist
            return [anchor[i]+downward[i]*offset for i in range(3)]

        source_ref = 'measured-body-profile:'+profile['cache_key']+'; source-piece:'+pid+\
                     '; source-seam:'+seam['id']+'; SOURCE_PAIRED_LIMB_CAGE'
        if segment_binding is not None:
            source_ref += '; segment-axis:'+segment_binding['evidence']['binding_sha256']
        if sewn_domain_mode:
            def evaluate(query):
                u, v = query; lo, hi = sewn_domain_interval(piece, sewn_domain, query, pid, source_budget)
                width = hi-lo; point = center(v)
                angle = 0. if abs(u-lo) <= 1e-9 or abs(u-hi) <= 1e-9 else 2*math.pi*(u-lo)/width
                radius = width/(2*math.pi)
                point = [point[i]+radius*(-math.cos(angle)*transverse[i]+math.sin(angle)*tangent[i]) for i in range(3)]
                return _world(profile, point)
            frame, sampling_report = sewn_domain_cage(piece, sewn_domain, pid, cage_subdivisions,
                                                       evaluate, source_ref, source_budget)
            uv = frame['uv_cm']; triangles = frame['triangles']; target = frame['target_cm']
        else:
            target = []
            for u, v in uv:
                lo, hi = _source_span(piece, v); width = hi-lo; point = center(v)
                if width > 1e-10:
                    if not lo-1e-8 <= u <= hi+1e-8:
                        raise StudioError('Limb cage control lies outside the actual horizontal material interval')
                    phase = (u-lo)/width
                    # Both actual sewing sides use exactly the same phase, avoiding
                    # sin(2*pi) round-off in a supposedly common source target.
                    angle = 0. if abs(u-lo) <= 1e-9 or abs(u-hi) <= 1e-9 else 2*math.pi*phase
                    radius = width/(2*math.pi)
                    point = [point[i]+radius*(-math.cos(angle)*transverse[i]+math.sin(angle)*tangent[i]) for i in range(3)]
                target.append(_world(profile, point))
            frame = {'source_ref': source_ref, 'uv_cm': uv, 'target_cm': target, 'triangles': triangles}
        attachment_evidence = None
        if attachment:
            from .anatomical_placement import sample_path
            from .pattern_assembly import _compile_cage, _cage_point
            reference = _path_reference(anatomical_references, policy.get('attachment_path_ref'), pid)
            fraction = _fraction(policy.get('path_fraction'), 'limb attachment path fraction')
            anchor_uv = _declared_anchor(piece, policy)
            target_body = sample_path(reference['points_body_cm'], [fraction], closed=reference['closed'])[0]
            offset = _vector(policy.get('attachment_offset_body'), 'limb attachment offset', nonzero=False)
            if math.hypot(*offset) > 100.:
                raise StudioError('Limb attachment offset exceeds its bounded placement domain')
            expected = _world(profile, [a+b for a, b in zip(target_body, offset)])
            if sewn_domain_mode:
                compiled_cage = _compile_cage(frame, pid, check_time=source_budget.check)
                observed = _cage_point(frame, compiled_cage, anchor_uv, pid, check_time=source_budget.check)[0]
            else:
                observed = _cage_point(frame, _compile_cage(frame, pid), anchor_uv, pid)[0]
            translation = [b-a for a, b in zip(observed, expected)]
            frame['target_cm'] = [[a+b for a, b in zip(point, translation)] for point in target]
            frame['source_ref'] += '; measured-attachment:'+reference['path_sha256']
            attachment_evidence = {'method': 'SOURCE_ANCHOR_TO_MEASURED_PATH_RIGID_TRANSLATION',
                'path_sha256': reference['path_sha256'], 'path_fraction': fraction,
                'source_anchor_uv_cm': anchor_uv, 'target_attachment_world_cm': expected,
                'translation_world_cm': translation, 'axis_landmarks': list(axis_names),
                'axis_landmarks_usage': 'ORIENTATION_ONLY_NOT_SKIN_ATTACHMENT',
                'attachment_offset_body_cm': offset, 'material_metric_changed_by_attachment': False}
            if sewn_domain_mode:
                residual = math.dist(_cage_point(frame, compiled_cage, anchor_uv, pid,
                                                check_time=source_budget.check)[0], expected)
                if residual > 1e-8:
                    raise StudioError('Sewn limb cage failed the unchanged anatomical anchor: '+pid)
                attachment_evidence.update(placement_recomputed_on_new_cage=True,
                    unplaced_anchor_world_cm=observed, actual_anchor_residual_cm=residual,
                    anatomical_target_changed=False, native_contact_check='REQUIRED')
        frames[pid] = frame
        evidence.append({'piece': pid, 'role': semantic['role'], 'side': side,
            'guide_kind': 'SOURCE_PAIRED_LIMB_CAGE', 'source_contour_sha256': digest(piece),
            'source_seam': copy.deepcopy(seam), 'source_seam_sha256': digest(seam),
            'source_sewing_pairs': pairs, 'source_pair_partition': 'MATCHED_ORIGINAL_NORMALIZED_SOURCE_SEGMENTS',
            'source_circumference_domain_cm': [min(spans), max(spans)],
            'source_longitudinal_length_cm': v_hi-v_lo, 'source_v_domain_cm': [v_lo, v_hi],
            'source_guide_axis_cm': [_world(profile, center(v_lo)), _world(profile, center(v_hi))],
            **({'declared_axis_length_cm': math.dist(shoulder, wrist)} if attachment else
               {'shoulder_wrist_axis_length_cm': math.dist(shoulder, wrist)}),
            'cage_refinement': sampling_report if sewn_domain_mode else {'method': 'UNIFORM_BARYCENTRIC_EXISTING_SOURCE_FACES',
                'subdivisions': cage_subdivisions, 'source_faces': len(piece['faces']),
                'control_vertices': len(uv), 'control_triangles': len(triangles),
                'source_topology_changed': False},
            **({'limb_parameterization': limb_parameterization, 'source_sewn_domain': sewn_domain}
               if sewn_domain_mode else {}),
            **({'source_longitudinal_anchor_policy': cuff_policy} if cuff_policy else {}),
            **({'source_segment_axis': segment_binding['evidence']} if segment_binding is not None else {}),
            **({'anatomical_attachment': attachment_evidence} if attachment_evidence else {}),
            'source_uv_scaled': False, 'body_rescaling': False,
            'anatomical_homology': 'REVIEW_REQUIRED', 'metric_admission': 'REQUIRED',
            'native_contact_check': 'REQUIRED', 'fitting': 'NOT_EXECUTED'})
    if digest([data, semantics, profile]) != original:
        raise StudioError('Limb cages changed immutable source, semantics or body')
    if sewn_domain_mode:
        source_budget.check()
        if not frames:
            raise StudioError('Source sewn limb parameters need an actual limb guide family')
    return {'status': 'PARTIAL_GUIDES' if pending else 'LIMB_GUIDES_PREPARED',
        'panels': frames, 'pending_pieces': pending, 'evidence': evidence,
        'source_sha256': digest(data), 'semantics_sha256': digest(semantics),
        'profile_sha256': digest(profile), 'profile_cache_key': profile['cache_key'],
        **({'limb_parameterization': limb_parameterization, 'source_cage_budget': {
                'limits': dict(source_budget.limits), 'controls': source_budget.controls,
                'triangles': source_budget.triangles, 'source_points': source_points,
                'source_triangles': source_faces}} if sewn_domain_mode else {}),
        'source_mutated': False, 'source_uv_scaled': False, 'qualification': 'NONE',
        'simulation': 'NOT_EXECUTED', 'fitting': 'NOT_EXECUTED'}


def _profile(profile):
    if (profile.get('status') != 'PROFILE_MEASURED' or profile.get('segmentation') != 'EXPLICIT_SOURCE'
            or not profile.get('cache_key')):
        raise StudioError('Garment guides require a measured source-bound segmented body profile')
    basis = profile['frame']
    for key in ('right', 'forward', 'up'):
        value = basis[key]
        if len(value) != 3 or any(not math.isfinite(v) for v in value) or abs(dot(value, value)-1) > 1e-7:
            raise StudioError('Measured garment guide frame must be orthonormal')
    if any(abs(dot(basis[a], basis[b])) > 1e-7 for a, b in (('right', 'up'), ('right', 'forward'), ('forward', 'up'))):
        raise StudioError('Measured garment guide axes must be perpendicular')


def _surface(profile, landmark, axis, sign=1):
    if landmark == 'head':
        from .head_surface import head_surface_section
        section = head_surface_section(profile)
    else:
        section = profile['landmarks'].get(landmark, {}).get('section', {})
    points = section.get('curve_cm')
    if section.get('status') != 'MEASURED' or not points or len(points) < 3:
        raise StudioError('Guide requires an actual measured surface section: '+landmark)
    if any(len(p) != 3 or any(not math.isfinite(v) for v in p) for p in points):
        raise StudioError('Guide surface contour must contain finite body-frame points')
    # An extremal *actual sample*, not a manufactured bounding-box corner.
    return list(max(points, key=lambda p: (sign*p[axis], tuple(p))))


def _rotate_closed_curve(curve, start_distance):
    """Change the seam phase while retaining the same measured polyline arc."""
    cumulative = [0.]
    for a, b in zip(curve, curve[1:]):
        cumulative.append(cumulative[-1]+math.dist(a, b))
    total = cumulative[-1]; start_distance %= total
    start = sample_curve(curve, start_distance)
    result = [start]+[list(p) for p, s in zip(curve, cumulative) if start_distance < s < total]
    result += [list(curve[0])]+[list(p) for p, s in zip(curve, cumulative) if 0 < s < start_distance]+[start]
    return [p for i, p in enumerate(result) if not i or math.dist(p, result[i-1]) > 1e-12]


def _source_anchor(piece, semantic, *, periodic_u=None):
    """Arc midpoints of actual named edges, optionally in a periodic U frame.

    Two collar anchors can straddle the material interval's closing boundary.
    Their shortest circular midpoint must then replace the arithmetic U mean.
    The 32-ULP margin below accounts only for source-coordinate arithmetic;
    it is not a spatial proximity or a garment acceptance tolerance.
    Single anchors and nonperiodic material coordinates retain their mapping.
    """
    names = semantic.get('guide_edges', {})
    if 'anchor' not in names:
        raise StudioError('Specialised guide requires an explicitly named source anchor edge')
    anchors = []
    for name in ('anchor', 'anchor_end'):
        if name not in names:
            continue
        edge = names[name]
        indices = piece['edges'].get(edge)
        if not indices or len(indices) < 2 or any(type(i) is not int or not 0 <= i < len(piece['vertices']) for i in indices):
            raise StudioError('Guide anchor edge is missing or has invalid source vertices: '+edge)
        curve = [piece['vertices'][i] for i in indices]
        lengths = [math.dist(a, b) for a, b in zip(curve, curve[1:])]
        if min(lengths) <= 1e-10:
            raise StudioError('Guide anchor edge has a collapsed source segment')
        remaining = math.fsum(lengths)/2
        for a, b, size in zip(curve, curve[1:], lengths):
            if remaining <= size:
                anchors.append([a[i]+remaining/size*(b[i]-a[i]) for i in (0, 1)])
                break
            remaining -= size
    result = [math.fsum(p[i] for p in anchors)/len(anchors) for i in (0, 1)]
    if periodic_u is None or len(anchors) == 1:
        return result
    if (not isinstance(periodic_u, (list, tuple)) or len(periodic_u) != 2 or
            any(type(value) not in (int, float) or not math.isfinite(value) for value in periodic_u)):
        raise StudioError('Periodic source anchor needs a finite material U origin and width')
    minimum, width = periodic_u
    if width <= 0 or not math.isfinite(minimum+width):
        raise StudioError('Periodic source anchor needs a positive finite material U interval')
    maximum = minimum+width
    margin = 32*max(math.ulp(value) for value in (minimum, maximum, width, *(p[0] for p in anchors)))
    if margin >= width/4:
        raise StudioError('Periodic source anchor interval is not resolved by source coordinate precision')
    if any(not minimum-margin <= p[0] <= maximum+margin for p in anchors):
        raise StudioError('Periodic source anchor midpoint lies outside its material U interval')

    def normalized(value):
        value %= width
        return 0. if min(value, width-value) <= margin else value

    positions = sorted(normalized(p[0]-minimum) for p in anchors)
    separation = positions[1]-positions[0]
    if abs(separation-width/2) <= margin:
        raise StudioError('Antipodal source anchor midpoints have an ambiguous collar phase')
    # Sort before unwrapping so swapping anchor/anchor_end has the same result.
    midpoint = (positions[0]+positions[1]-(width if separation > width/2 else 0.))/2
    result[0] = minimum+normalized(midpoint)
    return result


def _world(profile, point):
    basis = profile['frame']
    return [basis['origin_cm'][i]+math.fsum(point[j]*basis[key][i]
            for j, key in enumerate(('right', 'forward', 'up'))) for i in range(3)]


def _planar(piece, anchor_uv, anchor_body, u_axis, v_axis, profile):
    lo = [min(p[i] for p in piece['vertices']) for i in (0, 1)]
    hi = [max(p[i] for p in piece['vertices']) for i in (0, 1)]
    if min(hi[i]-lo[i] for i in (0, 1)) <= 1e-10:
        raise StudioError('Source guide contour is collapsed')
    u_axis, v_axis = unit(u_axis), unit(v_axis)
    if abs(dot(u_axis, v_axis)) > 1e-8:
        raise StudioError('Planar source guide must preserve orthogonal material axes')

    def point(u, v):
        return _world(profile, [anchor_body[i]+(u-anchor_uv[0])*u_axis[i]+(v-anchor_uv[1])*v_axis[i]
                               for i in range(3)])
    return {'u_direction': 1, 'arc_sections': [{'v_cm': v, 'arc_offset_cm': -lo[0],
             'curve_cm': [point(lo[0], v), point(hi[0], v)]} for v in (lo[1], hi[1])]}


def specialised_volume_frames(data, semantics, profile, *, anatomical_references=None):
    """Source-edge/body-surface guides for collar, inner front, hood and yoke.

    ``guide_edges.anchor`` (and optional ``anchor_end``) names actual edges;
    their arc midpoints define the material anchor. A nonnegative explicitly
    declared guide_surface_offset_cm may translate the hypothesis, never UV.
    Hood guide is sagittal, yoke guide follows measured skin shoulders, and
    the single inner-front stays one source piece. Their metrics are isometric.
    """
    _profile(profile)
    if set(semantics) != set(data['pieces']):
        raise StudioError('Garment guides require exact immutable source piece coverage')
    original = digest([data, semantics, profile]); frames = {}; evidence = []; pending = []
    for pid, semantic in sorted(semantics.items()):
        role = semantic.get('role')
        policy = (anatomical_references or {}).get('pieces', {}).get(pid, {})
        if policy.get('guide_kind') == 'PATH_BAND_V1':
            frame, record = anatomical_band_frame(data['pieces'][pid], policy, profile, anatomical_references, pid)
            frames[pid] = frame; evidence.append(record)
            continue
        if role not in SPECIAL_ROLES or policy.get('guide_kind') == 'LIMB_ATTACHMENT_V1':
            pending.append(pid); continue
        piece = data['pieces'][pid]
        if not piece.get('vertices') or any(len(p) != 2 or any(not math.isfinite(v) for v in p) for p in piece['vertices']):
            raise StudioError('Specialised guide requires a finite immutable 2D source contour: '+pid)
        if semantic.get('longitudinal_uv_axis') not in ('u', 'v'):
            raise StudioError('Specialised guide requires its explicit material axis: '+pid)
        periodic_u = None
        if role == 'collar':
            minimum_u = min(p[0] for p in piece['vertices'])
            periodic_u = (minimum_u, max(p[0] for p in piece['vertices'])-minimum_u)
        anchor_uv = _source_anchor(piece, semantic, periodic_u=periodic_u)
        offset = semantic.get('guide_surface_offset_cm', 0.)
        if type(offset) not in (int, float) or not math.isfinite(offset) or not 0 <= offset <= 20:
            raise StudioError('Guide surface offset must be explicit, finite and bounded')
        if role == 'inner_front':
            if semantic.get('side') != 'center' or semantic['longitudinal_uv_axis'] != 'v':
                raise StudioError('Inner front is a single central source piece with vertical material axis')
            anchor = _surface(profile, 'neck', 1); anchor[1] += offset
            frame = _planar(piece, anchor_uv, anchor, [1., 0., 0.], [0., 0., 1.], profile)
            kind = 'SOURCE_ISOMETRIC_CENTRAL_FRONT_PLANE'
        elif role == 'hood':
            if semantic.get('side') not in ('left', 'right') or semantic['longitudinal_uv_axis'] != 'v':
                raise StudioError('Hood guide requires an explicit source side and vertical material axis')
            sign = 1 if semantic['side'] == 'right' else -1
            anchor = _surface(profile, 'head', 0, sign); anchor[0] += sign*offset
            head = profile['landmarks']['head.center']['point_cm']; neck = profile['landmarks']['neck']['point_cm']
            up = unit([b-a for a, b in zip(neck, head)])
            sagittal = [0., -1., 0.]
            sagittal = unit([sagittal[i]-dot(sagittal, up)*up[i] for i in range(3)])
            frame = _planar(piece, anchor_uv, anchor, sagittal, up, profile)
            kind = 'SOURCE_ISOMETRIC_SAGITTAL_HOOD_PLANE'
        elif role == 'yoke':
            from .shoulder_surface import surface_anchors
            shoulders = surface_anchors(profile)
            u = unit([b-a for a, b in zip(shoulders['left'], shoulders['right'])])
            v = unit(cross([0., 0., 1.], u))
            normal = unit(cross(u, v))
            anchor = _surface(profile, 'neck', 1)
            anchor = [anchor[i]+offset*normal[i] for i in range(3)]
            frame = _planar(piece, anchor_uv, anchor, u, v, profile)
            kind = 'SOURCE_ISOMETRIC_MEASURED_SHOULDER_PLANE'
        else:
            if semantic['longitudinal_uv_axis'] != 'u':
                raise StudioError('Collar band requires a circumferential source u axis')
            section = profile['landmarks'].get('neck', {}).get('section', {})
            _surface(profile, 'neck', 1)
            lo, hi = section['bounds_xy_cm']
            if min(hi[i]-lo[i] for i in (0, 1)) <= 0:
                raise StudioError('Measured neck has no transverse section')
            width = max(p[0] for p in piece['vertices'])-min(p[0] for p in piece['vertices'])
            height = max(p[1] for p in piece['vertices'])-min(p[1] for p in piece['vertices'])
            if min(width, height) <= 1e-10:
                raise StudioError('Source collar band has no usable material span')
            center = [(lo[i]+hi[i])/2 for i in (0, 1)]
            center[1] += offset
            # Material width sets auxiliary perimeter; the body provides its
            # centre, aspect and elevation. UV circumference is never rescaled.
            arc = half_ellipse(width/2, (hi[0]-lo[0])/(hi[1]-lo[1]), center, section['height_cm'], 1)
            arc += list(reversed(half_ellipse(width/2, (hi[0]-lo[0])/(hi[1]-lo[1]), center, section['height_cm'], -1)))[1:]
            minimum_u = min(p[0] for p in piece['vertices'])
            arc = _rotate_closed_curve(arc, width/2-(anchor_uv[0]-minimum_u))
            actual_width = math.fsum(math.dist(a, b) for a, b in zip(arc, arc[1:]))
            # Account for floating-point accumulation without scaling UV or
            # altering the source circumferential span.
            arc = extend_tangent(arc, max(0., width-actual_width)+1e-8)
            rows = []
            for v in (min(p[1] for p in piece['vertices']), max(p[1] for p in piece['vertices'])):
                rows.append({'v_cm': v, 'arc_offset_cm': -minimum_u,
                             'curve_cm': [_world(profile, [p[0], p[1], p[2]+v-anchor_uv[1]]) for p in arc]})
            frame = {'u_direction': 1, 'arc_sections': rows}
            kind = 'SOURCE_DEVELOPABLE_NECK_BAND'
        frame['source_ref'] = 'measured-body-profile:'+profile['cache_key']+'; source-piece:'+pid+'; '+kind
        frames[pid] = frame
        evidence.append({'piece': pid, 'role': role, 'guide_kind': kind,
                         'source_anchor_edges': copy.deepcopy(semantic['guide_edges']),
                         'source_anchor_uv_cm': anchor_uv, 'source_contour_sha256': digest(piece),
                         'source_uv_scaled': False, 'contact_assessment': 'REQUIRED',
                         'curved_surface_drape': 'REQUIRED' if role in ('hood', 'yoke') else 'NOT_EXECUTED'})
    if digest([data, semantics, profile]) != original:
        raise StudioError('Garment guides changed an immutable input')
    return {'version': 1, 'status': 'PARTIAL_GUIDES' if pending else 'SPECIALISED_GUIDES_PREPARED',
            'panels': frames, 'pending_pieces': pending, 'guides': evidence,
            'source_sha256': digest(data), 'semantics_sha256': digest(semantics),
            'profile_cache_key': profile['cache_key'], 'profile_sha256': digest(profile),
            'source_mutated': False, 'source_uv_scaled': False, 'qualification': 'NONE',
            'simulation': 'NOT_EXECUTED', 'fitting': 'NOT_EXECUTED', 'collision_assessment': 'REQUIRED'}


def measured_native_skin_sections(profile, geometry, heights_cm):
    """Measure exact whole-skin contours separately from approved girths.

    The closed central contour can include connected arm skin. It is only an
    obstacle guide contour, never a replacement anatomical torso measurement.
    Segmented torso refusals remain in the original immutable profile.
    """
    from .anatomy_profile import surface_section
    _profile(profile)
    if (profile.get('geometry_sha256')!=digest([geometry['vertices_cm'],geometry['faces']]) or
            any(profile.get(key)!=geometry.get(key) for key in ('source_sha256','pose_sha256'))):
        raise StudioError('Additional skin sections require the exact approved evaluated geometry and pose')
    basis=profile['frame']
    coordinates=[[dot([p[i]-basis['origin_cm'][i] for i in range(3)],basis[key])
                  for key in ('right','forward','up')] for p in geometry['vertices_cm']]
    sections=[]
    for height in sorted(set(heights_cm)):
        if type(height) not in (int,float) or not math.isfinite(height): raise StudioError('Skin guide height must be finite')
        source=min(profile['sections'],key=lambda row:abs(row['height_cm']-height))
        seed=source.get('seed_xy_cm')
        if not seed or len(seed)!=2: raise StudioError('Additional native skin section requires the explicit source-profile interior seed')
        section=surface_section(coordinates,geometry['faces'],height,seed)
        if section.get('status')=='MEASURED' and section['open_loop_count']:
            section['status']='NOT_QUALIFIED';section['reason']='WHOLE_SKIN_SECTION_HAS_OPEN_COMPONENTS'
        section.update(seed_xy_cm=copy.deepcopy(seed),source_face_domain='ALL_NATIVE_SKIN',
            anatomical_girth='NOT_QUALIFIED',body_surface_extrapolated=False,
            contour_selection='UNIQUE_CLOSED_NATIVE_CONTOUR_CONTAINING_EXPLICIT_SOURCE_SEED',
            connected_arm_skin='MAY_BE_INCLUDED_NOT_A_TORSO_GIRTH',
            disconnected_skin_loops='EXCLUDED_AND_REPORTED')
        sections.append(section)
    result={'version':1,'profile_sha256':digest(profile),'geometry_sha256':profile['geometry_sha256'],
        'source_sha256':profile['source_sha256'],'pose_sha256':profile['pose_sha256'],'frame':copy.deepcopy(basis),
        'source_face_domain':'ALL_NATIVE_SKIN','sections':sections,'approved_profile_mutated':False,
        'qualification':'OBSTACLE_GUIDE_CONTOURS_ONLY','anatomical_girths_replaced':False}
    result['sections_sha256']=digest(result)
    return result


def validate_section_parameterization(value, upper_blend, surface_sections):
    """Require explicit material provenance without changing legacy arc evaluation."""
    if value not in ('POLYLINE_ARCLENGTH_V1', 'SOURCE_MATERIAL_U_V1'):
        raise StudioError('Unsupported torso section parameterization')
    if value == 'SOURCE_MATERIAL_U_V1' and (
            surface_sections is not True or type(upper_blend) not in (int, float)
            or not math.isfinite(upper_blend) or not 0. < upper_blend <= 1.):
        raise StudioError('Source material torso parameters require measured surface sections and a sourced shoulder producer')


def garment_volume_frames(data, semantics, profile, upper_blend=1., surface_sections=True, skin_sections=None,
                          *,source_seam_coupling=None,seam_recipe=None, anatomical_references=None,
                          anatomical_geometry=None, section_parameterization='POLYLINE_ARCLENGTH_V1',
                          limb_parameterization='SOURCE_ROW_CIRCUMFERENCE_V1', source_boundary_bindings=None,
                          attachment_clearance=None):
    """Dispatch complete source coverage; return pending unsupported roles.

    A missing declaration or impossible native guide produces an actionable
    diagnostic. Existing complete roles may still be examined as partial data;
    pending pieces keep the result inadmissible for whole-garment preparation.
    """
    validate_section_parameterization(section_parameterization, upper_blend, surface_sections)
    validate_limb_parameterization(limb_parameterization)
    _profile(profile)
    if skin_sections and (skin_sections.get('profile_sha256')!=digest(profile) or
            skin_sections.get('sections_sha256')!=digest({k:v for k,v in skin_sections.items() if k!='sections_sha256'}) or
            any(skin_sections.get(key)!=profile.get(key) for key in ('geometry_sha256','source_sha256','pose_sha256','frame'))):
        raise StudioError('Additional skin-section evidence is stale for the approved body/profile/frame')
    if set(semantics) != set(data['pieces']):
        raise StudioError('Garment guide dispatcher requires exact source piece coverage')
    references = None
    if anatomical_references is not None:
        from .anatomical_placement import validate_anatomical_references
        references = validate_anatomical_references(profile, anatomical_references,
            geometry=(anatomical_geometry or {}).get('geometry'))
        if not set(references['pieces']) <= set(data['pieces']):
            raise StudioError('Anatomical guide policy names a piece outside the actual source')
    if section_parameterization == 'SOURCE_MATERIAL_U_V1' and not any(
            row.get('role') in ('front', 'back', 'side') and
            (references or {}).get('pieces', {}).get(pid, {}).get('guide_kind') is None
            for pid, row in semantics.items()):
        raise StudioError('Source material torso parameters need an actual torso guide family')
    if limb_parameterization == 'SOURCE_SEWN_DOMAIN_V1' and not any(
            (references or {}).get('pieces', {}).get(pid, {}).get('guide_kind') in ('LIMB_ATTACHMENT_V1', 'LIMB_SEGMENT_AXIS_V1')
            or (row.get('role') in ('sleeve', 'cuff') and
                (references or {}).get('pieces', {}).get(pid, {}).get('guide_kind') is None)
            for pid, row in semantics.items()):
        raise StudioError('Source sewn limb parameters need an actual limb guide family')
    frames = {}; reports = []; diagnostics = []
    families = [('torso', {'front', 'back', 'side'}, torso_volume_frames),
                ('limb', {'sleeve', 'cuff'}, limb_volume_frames),
                ('belt', {'belt'}, belt_volume_frames),
                ('specialised', SPECIAL_ROLES, specialised_volume_frames)]
    for name, roles, build in families:
        family_semantics = copy.deepcopy(semantics)
        for pid, policy in (references or {}).get('pieces', {}).items():
            kind = policy.get('guide_kind')
            if kind not in (None, 'PATH_BAND_V1', 'LIMB_ATTACHMENT_V1', 'LIMB_SEGMENT_AXIS_V1'):
                raise StudioError('Unsupported anatomical piece guide kind: '+str(kind))
            owner = {'PATH_BAND_V1': 'specialised', 'LIMB_ATTACHMENT_V1': 'limb', 'LIMB_SEGMENT_AXIS_V1': 'limb'}.get(kind)
            if owner is not None and owner != name:
                family_semantics[pid]['role'] = 'owned_by_explicit_anatomical_guide'
        extra_kinds = {'limb': ('LIMB_ATTACHMENT_V1', 'LIMB_SEGMENT_AXIS_V1'), 'specialised': ('PATH_BAND_V1',)}.get(name, ())
        if not any(p.get('role') in roles for p in family_semantics.values()) and not (
                any(p.get('guide_kind') in extra_kinds for p in (references or {}).get('pieces', {}).values())):
            continue
        try:
            report = (build(data, family_semantics, profile, upper_blend=upper_blend, surface_sections=surface_sections,skin_sections=skin_sections,
                            source_cage_budgets=source_seam_coupling['budgets'] if source_seam_coupling else None,
                            synchronize_boundaries=not (source_seam_coupling or {}).get('strategy') == 'COUPLED_REST_METRIC_V2',
                            **({'section_parameterization':section_parameterization}
                               if section_parameterization != 'POLYLINE_ARCLENGTH_V1' else {}))
                      if name == 'torso' else build(data, family_semantics, profile, anatomical_references=references,
                          **({'limb_parameterization': limb_parameterization,
                              'source_cage_budgets': source_seam_coupling['budgets'] if source_seam_coupling else None}
                             if name == 'limb' and limb_parameterization == 'SOURCE_SEWN_DOMAIN_V1' else {}))
                      if name in ('limb', 'specialised') else build(data, family_semantics, profile))
        except StudioError as error:
            diagnostics.append({'family': name, 'code': 'GUIDE_INPUT_OR_CAPABILITY_MISSING', 'message': str(error),
                                'pieces': sorted(pid for pid, row in semantics.items() if row.get('role') in roles),
                                **({'measurement': error.guide_diagnostic} if getattr(error,'guide_diagnostic',None) else {})})
            continue
        if set(frames).intersection(report['panels']):
            raise StudioError('Several guide families own one source piece')
        frames.update(report['panels']); reports.append({'family': name, 'report': report})
    attachment_controls = anatomical_attachment_controls(data, frames, references)
    attachment_clearance_report = None
    attachment_clearance_blocked = False
    if attachment_clearance is not None:
        from .attachment_guide_guard import inspect_fixed_attachment_reserve
        if references is None or seam_recipe is None:
            raise StudioError('Attachment clearance requires declared anatomical references and a source recipe')
        attachment_clearance_report = inspect_fixed_attachment_reserve(
            data, attachment_controls, profile, anatomical_geometry, seam_recipe, attachment_clearance)
        attachment_clearance_blocked = attachment_clearance_report['status'] != 'ALL_TARGET_CLEARANCES_VERIFIED'
        if attachment_clearance_blocked:
            diagnostics.append({'family': 'anatomical_constraints', 'code': 'FIXED_ATTACHMENT_BODY_RESERVE_CONFLICT',
                'message': 'A fixed source-bound target contradicts the declared body collider reserve',
                'conflicts': attachment_clearance_report['clearance']['conflict_count']})
    envelope_report = None
    envelope_policies = {pid: row['surface_envelope'] for pid, row in (references or {}).get('pieces', {}).items()
                         if 'surface_envelope' in row and pid in frames}
    if envelope_policies:
        from .regional_surface_guides import apply_regional_surface_envelopes
        frames, envelope_report = apply_regional_surface_envelopes(
            data, frames, profile, anatomical_geometry, envelope_policies)
        diagnostics.extend({'family': 'regional_surface_envelope', **row} for row in envelope_report['diagnostics'])
    before_coupling_attachments = anatomical_attachment_residuals(frames, attachment_controls)
    if before_coupling_attachments['violations']:
        diagnostics.append({'family': 'anatomical_constraints', 'code': 'SURFACE_AND_ATTACHMENT_CONSTRAINTS_CONFLICT',
            'violations': before_coupling_attachments['violations'],
            'message': 'The proposed surface correction conflicts with an immutable measured attachment'})
    coupling_report=None
    if source_seam_coupling is not None:
        from .source_seam_coupling import couple_source_seams
        selected=source_seam_coupling['pieces']
        scope = source_seam_coupling.get('piece_scope', 'EXPLICIT')
        if scope == 'PERMANENT_COMPONENT':
            selected = permanent_component_pieces(data, selected)
        elif scope != 'EXPLICIT':
            raise StudioError('Unsupported source sewing piece scope')
        missing = sorted(set(selected)-set(frames))
        if missing and scope == 'PERMANENT_COMPONENT':
            diagnostics.append({'family': 'source_rigid_alignment', 'code': 'PERMANENT_COMPONENT_GUIDES_MISSING',
                'pieces': missing, 'message': 'The complete permanent source component needs these missing guides'})
            selected = [pid for pid in selected if pid in frames]
        minimum = 1 if source_seam_coupling.get('strategy') == 'COUPLED_REST_METRIC_V2' else 2
        if (not isinstance(selected,list)or (len(selected)<minimum and not missing) or len(set(selected))!=len(selected)
                or not set(selected)<=set(frames)):
            raise StudioError('Source-seam coupling requires its explicit distinct prepared source panels')
        if attachment_clearance_blocked:
            cages = {}; coupling_report = {'strategy': source_seam_coupling.get('strategy'),
                'status': 'NOT_EXECUTED_FIXED_ATTACHMENT_CLEARANCE_CONFLICT', 'qualification': 'NONE'}
        elif before_coupling_attachments['violations']:
            cages = {}; coupling_report = {'strategy': source_seam_coupling.get('strategy'),
                'status': 'NOT_EXECUTED_ANATOMICAL_CONSTRAINT_CONFLICT', 'qualification': 'NONE'}
        elif len(selected) < minimum:
            cages = {}; coupling_report = {'strategy': source_seam_coupling.get('strategy'),
                'status': 'NOT_EXECUTED_MISSING_COMPONENT_GUIDES', 'qualification': 'NONE'}
        else:
            cages,coupling_report=couple_source_seams(data,{pid:frames[pid]for pid in selected},seam_recipe,
                subdivisions=source_seam_coupling['subdivisions'],budgets=source_seam_coupling['budgets'],semantics=semantics,
                **({'anatomical_attachments': [row for row in attachment_controls if row['piece'] in selected]}
                    if source_seam_coupling.get('strategy') == 'COUPLED_REST_METRIC_V2' else {}),
                **({key: source_seam_coupling[key] for key in ('strategy', 'relaxation', 'numerical_anchor_edges') if key in source_seam_coupling}))
        frames.update(cages)
        coupling_report['piece_scope'] = scope
        coupling_report['missing_component_guides'] = missing
        if coupling_report.get('strategy') == 'COUPLED_REST_METRIC_V2' and (
                coupling_report.get('unprocessed_external_relations') or missing):
            diagnostics.append({'family': 'source_rigid_alignment', 'code': 'PERMANENT_COMPONENT_INCOMPLETE',
                'pieces': missing, 'message': 'Permanent sewing partners are not all prepared in the current candidate'})
        elif coupling_report.get('strategy') == 'COUPLED_REST_METRIC_V2' and coupling_report.get('status') != 'PROPOSAL_TARGETS_REACHED':
            diagnostics.append({'family': 'source_rigid_alignment', 'code': 'COUPLED_MATERIAL_PROPOSAL_INCOMPLETE',
                'status': coupling_report.get('status'), 'message': 'The measured seam/material proposal has not reached its declared numerical targets'})
        alignment=coupling_report.get('rigid_alignment',{})
        for row in alignment.get('diagnostics',[]):
            diagnostics.append({'family':'source_rigid_alignment',**row})
        if alignment.get('status')=='PARTIAL_ROLE_SEEDS_PREPARED':
            diagnostics.append({'family':'source_rigid_alignment','code':'PARTIAL_SOURCE_RELATION_ALIGNMENT',
                'message':'Rigid seeds cover front attachments only; other permanent relations still require correction'})
    elif seam_recipe is not None and source_boundary_bindings is None and attachment_clearance is None:
        raise StudioError('A sewing recipe cannot enable undeclared guide coupling')
    final_attachments = anatomical_attachment_residuals(frames, attachment_controls)
    if final_attachments['violations']:
        diagnostics.append({'family': 'anatomical_constraints', 'code': 'FINAL_ANATOMICAL_ATTACHMENT_DRIFT',
            'violations': final_attachments['violations'], 'max_residual_cm': final_attachments['max_residual_cm'],
            'message': 'The final guide no longer retains its measured source-bound anatomical attachment'})
    final_envelope = None
    if envelope_policies and coupling_report is not None:
        # Requery the final geometry, without adopting this second correction.
        # The metric solve cannot silently spend the body reserve established
        # before assembly. A changed source-ref on the discarded copy is not
        # an authorization to project, modify or qualify the final candidate.
        _, final_envelope = apply_regional_surface_envelopes(
            data, frames, profile, anatomical_geometry, envelope_policies)
        violations = [row for row in final_envelope['pieces']
                      if row['unresolved_controls'] or row['max_displacement_cm'] > 1e-7]
        if violations:
            diagnostics.append({'family': 'anatomical_constraints', 'code': 'FINAL_REGIONAL_SURFACE_RESERVE_NOT_PRESERVED',
                'pieces': [row['piece'] for row in violations],
                'message': 'Final guide controls require additional regional clearance or lack measured coverage'})
    coverage = None
    if references is not None:
        from .anatomical_placement import region_coverage
        coverage = region_coverage(references)
        coverage['prepared_piece_guides'] = [{'piece': pid, 'guide_kind': row.get('guide_kind', 'LEGACY_ROLE_GUIDE'),
            'prepared': pid in frames, 'surface_envelope_declared': 'surface_envelope' in row}
            for pid, row in sorted(references['pieces'].items())]
    boundary_report = None
    if source_boundary_bindings is not None:
        from .source_boundary_bindings import inspect_current_source_boundaries
        if references is None or not isinstance(anatomical_geometry, dict) or seam_recipe is None:
            raise StudioError('Boundary inspection needs explicit anatomical references, native geometry and source recipe')
        boundary_report = inspect_current_source_boundaries(data, frames, seam_recipe, profile,
            anatomical_geometry.get('geometry'), anatomical_references, source_boundary_bindings)
        if boundary_report['status'] == 'PARTIAL_BOUNDARY_CONTINUATION':
            diagnostics.append({'family': 'source_boundary_bindings', 'code': 'CURRENT_BOUNDARY_CONTINUATION_INCOMPLETE',
                'message': 'Current sewing supports remain available; anatomical paths or boundary reserve are unresolved'})
    pending = sorted(set(data['pieces'])-set(frames))
    return {'version': 1, 'status': 'PARTIAL_GUIDES' if pending or any(
                row.get('family') in ('source_rigid_alignment', 'regional_surface_envelope', 'anatomical_constraints', 'source_boundary_bindings') for row in diagnostics) else 'GARMENT_GUIDES_PREPARED',
            'panels': frames, 'pending_pieces': pending, 'diagnostics': diagnostics, 'families': reports,
            **({'source_seam_coupling':coupling_report}if coupling_report is not None else {}),
            **({'regional_surface_envelope': envelope_report} if envelope_report is not None else {}),
            **({'anatomical_attachment_constraints': final_attachments} if attachment_controls else {}),
            **({'attachment_clearance': attachment_clearance_report} if attachment_clearance_report is not None else {}),
            **({'post_coupling_surface_reserve': final_envelope} if final_envelope is not None else {}),
            **({'anatomical_region_coverage': coverage} if coverage is not None else {}),
            **({'anatomical_references_sha256': digest(anatomical_references)} if references is not None else {}),
            **({'source_boundary_bindings': boundary_report} if boundary_report is not None else {}),
            'source_sha256': digest(data), 'semantics_sha256': digest(semantics),
            'profile_cache_key': profile['cache_key'], 'profile_sha256': digest(profile),
            'source_mutated': False, 'source_uv_scaled': False, 'qualification': 'NONE',
            'simulation': 'NOT_EXECUTED', 'fitting': 'NOT_EXECUTED', 'collision_assessment': 'REQUIRED'}
