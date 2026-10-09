"""Explicit source-material section parameters, compiled into existing cages.

This is an opt-in auxiliary guide. It never reinterprets historical arc lengths,
changes source UV, grants material admission or extrapolates missing sections.
"""
from bisect import bisect_left, bisect_right
from fractions import Fraction
import math

from .core import StudioError, digest


def _finite(value):
    return type(value) in (int, float) and math.isfinite(value)


def compile_material_sections(frame, pid, budget):
    """Validate and snapshot transported material coordinates without inferring them."""
    budget.check()
    if (not isinstance(frame, dict) or set(frame) != {'source_ref', 'sampling_contract', 'material_sections'}
            or not isinstance(frame['source_ref'], str) or not frame['source_ref']
            or frame['sampling_contract'] != 'SOURCE_MATERIAL_U_V1'
            or not isinstance(frame['material_sections'], list) or not 2 <= len(frame['material_sections']) <= 128):
        raise StudioError('Material section guide requires explicit SOURCE_MATERIAL_U_V1 sections: '+pid)
    rows = []; total = 0
    for index, row in enumerate(frame['material_sections']):
        budget.check()
        if (not isinstance(row, dict) or set(row) != {'v_cm', 'material_u_cm', 'curve_cm'}
                or not _finite(row['v_cm']) or (index and row['v_cm'] <= rows[-1]['v_cm'])
                or not isinstance(row['material_u_cm'], list) or not isinstance(row['curve_cm'], list)
                or not 2 <= len(row['material_u_cm']) <= 4096 or len(row['material_u_cm']) != len(row['curve_cm'])
                or not all(_finite(u) for u in row['material_u_cm'])
                or any(not isinstance(point, (list, tuple)) or len(point) != 3
                       or not all(_finite(x) for x in point) for point in row['curve_cm'])):
            raise StudioError('Material section requires increasing finite V and matched explicit U/XYZ samples: '+pid)
        total += len(row['material_u_cm'])
        if total > budget.limits['max_source_points']:
            raise StudioError('Material section input sample budget exhausted: '+pid)
        values = row['material_u_cm']
        ascending = all(a < b for a, b in zip(values, values[1:]))
        descending = all(a > b for a, b in zip(values, values[1:]))
        if not ascending and not descending:
            raise StudioError('Material U parameters must be strictly monotone without merged or duplicate samples: '+pid)
        order = list(range(len(values))) if ascending else list(reversed(range(len(values))))
        rows.append({'v_cm': row['v_cm'], 'material_u_cm': [values[i] for i in order],
                     'curve_cm': [list(row['curve_cm'][i]) for i in order],
                     'original_curve_indices': order})
    return {'sampling_contract': 'SOURCE_MATERIAL_U_V1', 'source_ref': frame['source_ref'],
            'source_frame_sha256': digest(frame), 'sections': rows,
            'v_values': [row['v_cm'] for row in rows], 'input_sample_count': total}


def material_section_point(compiled, uv, pid, budget):
    """Evaluate a bounded piecewise bilinear source map and retain its bindings."""
    budget.check()
    if (not isinstance(uv, (list, tuple)) or len(uv) != 2 or not all(_finite(x) for x in uv)):
        raise StudioError('Material section query requires finite source UV: '+pid)
    u, v = uv; positions = compiled['v_values']
    if not positions[0] <= v <= positions[-1]:
        raise StudioError('Source material V lies outside its explicitly transported section domain: '+pid)
    band = min(len(positions)-2, bisect_right(positions, v)-1)
    points = []; bindings = []
    for section_id in (band, band+1):
        row = compiled['sections'][section_id]; values = row['material_u_cm']; curve = row['curve_cm']
        if not values[0] <= u <= values[-1]:
            raise StudioError('Source material U lies outside its explicitly transported section domain: '+pid)
        segment = min(len(values)-2, bisect_right(values, u)-1)
        weight = (u-values[segment])/(values[segment+1]-values[segment])
        points.append([(1-weight)*a+weight*b for a, b in zip(curve[segment], curve[segment+1])])
        bindings.append({'section': section_id, 'source_u_interval_cm': values[segment:segment+2],
                         'original_curve_indices': row['original_curve_indices'][segment:segment+2],
                         'segment_weights': [1-weight, weight]})
    blend = (v-positions[band])/(positions[band+1]-positions[band])
    point = [(1-blend)*a+blend*b for a, b in zip(*points)]
    if not all(_finite(value) for value in point):
        raise StudioError('Material section interpolation produced a nonfinite target: '+pid)
    return point, {'sampling_contract': 'SOURCE_MATERIAL_U_V1', 'source_uv_cm': list(uv),
                   'section_indices': [band, band+1], 'section_weights': [1-blend, blend],
                   'material_samples': bindings}


def material_section_cage_state(piece, frame, pid, budget):
    """Partition original faces at transported U/V knots, with one shared budget.

    Rational cuts retain actual source ownership and adjacent boundary controls.
    The unchanged cage validator rejects slivers it cannot represent. The final
    piecewise affine cage approximates the piecewise bilinear section map;
    measured interior errors are observations, never a continuous certificate.
    """
    from .cloth_metrics import principal_stretches
    from .garment_guides import _source_limb_mesh
    from .guide_cage_sampling import _strips, _ears, _line, _cross, validated_cage_state
    compiled = compile_material_sections(frame, pid, budget)
    if (not isinstance(piece, dict) or not isinstance(piece.get('vertices'), list)
            or not isinstance(piece.get('faces'), list)
            or len(piece['vertices']) > budget.limits['max_source_points']
            or len(piece['faces']) > budget.limits['max_source_triangles']):
        raise StudioError('Material section cage requires bounded original source faces: '+pid)
    _source_limb_mesh(piece, 1)
    try:
        before = digest([piece, frame])
    except (TypeError, ValueError) as error:
        raise StudioError('Material section cage requires finite serializable source inputs') from error
    vertices = [tuple(Fraction(value) for value in point) for point in piece['vertices']]
    v_rows = [Fraction(value) for value in compiled['v_values']]
    if min(p[1] for p in vertices) < v_rows[0] or max(p[1] for p in vertices) > v_rows[-1]:
        raise StudioError('Source material V domain exceeds its explicit section domain: '+pid)
    u_rows = [set(map(Fraction, row['material_u_cm'])) for row in compiled['sections']]
    unions = [sorted(a | b) for a, b in zip(u_rows, u_rows[1:])]
    fragments = []; lines = {}; prospective = set()
    for source_id, face in sorted(enumerate(piece['faces']), key=lambda row: tuple(sorted(row[1]))):
        budget.check()
        for strip in _strips([vertices[i] for i in face], 1, v_rows[1:-1], budget):
            middle = (min(p[1] for p in strip)+max(p[1] for p in strip))/2
            band = min(len(unions)-1, bisect_right(v_rows, middle)-1)
            for cell in _strips(strip, 0, unions[band], budget):
                fragments.append((source_id, cell))
                if len(fragments)+budget.triangles > budget.limits['max_triangles']:
                    raise StudioError('Material section partition triangle budget exhausted')
                for a, b in zip(cell, cell[1:]+cell[:1]):
                    prospective.update((a, b))
                    if len(prospective)+budget.controls > budget.limits['max_controls']:
                        raise StudioError('Material section partition control budget exhausted')
                    lines.setdefault(_line(a, b), set()).update((a, b))
    indexed = {}
    for key, points in lines.items():
        budget.check(); axis = 0 if key[1] else 1
        ordered = sorted(points, key=lambda point: point[axis])
        indexed[key] = axis, ordered, [point[axis] for point in ordered]
    corners = {point: list(original) for point, original in zip(vertices, piece['vertices'])}
    ids = {}; uv = []; faces = []; source_faces = []

    def vertex(point):
        if point not in ids:
            budget.reserve(1, 0)
            ids[point] = len(uv); uv.append(corners.get(point, [float(value) for value in point]))
        return ids[point]

    for source_id, cell in fragments:
        budget.check(); boundary = []
        for a, b in zip(cell, cell[1:]+cell[:1]):
            axis, points, positions = indexed[_line(a, b)]
            low, high = sorted((a[axis], b[axis]))
            chain = points[bisect_left(positions, low):bisect_right(positions, high)]
            if a[axis] > b[axis]: chain = list(reversed(chain))
            boundary.extend(chain[:-1])
        for triangle in _ears(boundary, budget):
            budget.reserve(0, 1)
            face = [vertex(point) for point in triangle]
            determinant = _cross(*(uv[index] for index in face))
            if not math.isfinite(determinant) or abs(determinant) < 1e-10:
                error = StudioError('Collapsed source-UV material section cage triangle: '+pid)
                error.guide_diagnostic = {'reason': 'MATERIAL_SECTION_PARTITION_NOT_REPRESENTABLE',
                    'piece': pid, 'source_face_index': source_id, 'source_uv_cm': [uv[index] for index in face],
                    'determinant_cm2': determinant, 'existing_minimum_abs_determinant_cm2': 1e-10,
                    'source_mutated': False, 'cuts_merged': False, 'qualification': 'NONE'}
                raise error
            faces.append(face); source_faces.append(source_id)

    def evaluate(point):
        return material_section_point(compiled, point, pid, budget)[0]

    targets = [evaluate(point) for point in uv]
    cage = {'source_ref': frame['source_ref']+'; SOURCE_MATERIAL_U_V1; source-uv-knot-partition',
            'uv_cm': uv, 'target_cm': targets, 'triangles': faces}
    state = validated_cage_state(piece, cage, pid, 1, budget, evaluate,
                                 reserved=True, source_faces=source_faces)
    minimum = math.inf; maximum = -math.inf; area = 0.; worst_error = 0.; worst_sample = None; count = 0
    for index, face in enumerate(faces):
        budget.check()
        source = [uv[i] for i in face]; placed = [targets[i] for i in face]
        stretches = principal_stretches(source, placed)
        if stretches is None or not all(_finite(x) for x in stretches):
            raise StudioError('Material section cage has an unmeasurable principal metric: '+pid)
        minimum = min(minimum, stretches[0]); maximum = max(maximum, stretches[1]); area += abs(_cross(*source))/2
        for weights in ((1/3, 1/3, 1/3), (.6, .2, .2), (.2, .6, .2), (.2, .2, .6)):
            budget.check()
            query = [sum(weight*uv[i][k] for weight, i in zip(weights, face)) for k in (0, 1)]
            affine = [sum(weight*targets[i][k] for weight, i in zip(weights, face)) for k in range(3)]
            actual = evaluate(query); distance = math.dist(affine, actual); count += 1
            if distance > worst_error:
                worst_error = distance
                worst_sample = {'cage_triangle_index': index, 'source_face_index': source_faces[index],
                    'source_uv_cm': query, 'barycentric_weights': list(weights), 'affine_target_cm': affine,
                    'section_map_target_cm': actual, 'distance_cm': distance}
    if digest([piece, frame]) != before:
        raise StudioError('Material section cage changed its source or parameter inputs')
    state['sampling_report'] = {'method': 'SOURCE_MATERIAL_U_V1', 'stage': 'INITIAL_SOURCE_MATERIAL_PARTITION',
        'source_piece_sha256': digest(piece), 'input_frame_sha256': digest(frame), 'cage_sha256': digest(cage),
        'seed_subdivisions': 1, 'controls': len(uv), 'triangles': len(faces),
        'source_segments': len(state['segments']), 'source_faces_covered': len(set(source_faces)),
        'material_area_cm2': area, 'principal_range': [minimum, maximum],
        'interior_interpolation': {'sample_count': count, 'maximum_error_over_samples_cm': worst_error,
            'worst_sample': worst_sample, 'certified_continuous_bound': False},
        'source_mutated': False, 'body_mutated': False, 'source_uv_scaled': False,
        'material_admission': 'NOT_GRANTED', 'qualification': 'NONE'}
    return state
