"""Private, bounded source partitions for measured polyline guide cages.

Rational UV identities keep adjacent clipped material faces conforming. Targets
always use the existing section evaluator; these cages confer no admission.
"""
from bisect import bisect_left, bisect_right
from fractions import Fraction
import copy
import math
import struct

from .core import StudioError
from .pattern_assembly import _cage_point, _compile_arc_sections, _compile_cage, _vertex_manifold


def _cross(a, b, c):
    return (b[0]-a[0])*(c[1]-a[1])-(b[1]-a[1])*(c[0]-a[0])


def _line(a, b):
    x, y = a[1]-b[1], b[0]-a[0]
    z = -x*a[0]-y*a[1]
    scale = x if x else y
    return x/scale, y/scale, z/scale


def _rounded_source_segment(point, a, b):
    """Can the exact source line round to both received binary64 coordinates?

    Intersect exact rational rounding bins; no distance epsilon is used.
    Source vertices are the authoritative, exact binary64 inputs.
    """
    lower, upper = Fraction(0), Fraction(1)
    lower_closed = upper_closed = True
    for value, start, end in zip(point, a, b):
        delta = Fraction(end)-Fraction(start)
        if not delta:
            if value != start:
                return False
            continue
        previous = math.nextafter(float(value), -math.inf)
        following = math.nextafter(float(value), math.inf)
        if not math.isfinite(previous) or not math.isfinite(following):
            return False
        low = (Fraction(previous)+Fraction(value))/2
        high = (Fraction(value)+Fraction(following))/2
        x, y = sorted(((low-Fraction(start))/delta, (high-Fraction(start))/delta))
        closed = not (int.from_bytes(struct.pack('>d', float(value)), 'big') & 1)
        if x > lower:
            lower, lower_closed = x, closed
        elif x == lower:
            lower_closed = lower_closed and closed
        if y < upper:
            upper, upper_closed = y, closed
        elif y == upper:
            upper_closed = upper_closed and closed
        if lower > upper or (lower == upper and not (lower_closed and upper_closed)):
            return False
    return True


def _clip_axis(polygon, axis, cut, below):
    result = []
    for a, b in zip(polygon, polygon[1:]+polygon[:1]):
        da, db = a[axis]-cut, b[axis]-cut
        inside_a, inside_b = (da <= 0, db <= 0) if below else (da >= 0, db >= 0)
        if inside_a:
            result.append(a)
        if inside_a != inside_b:
            t = da/(da-db)
            result.append(tuple(a[k]+t*(b[k]-a[k]) for k in (0, 1)))
    return list(dict.fromkeys(result))


def _strips(polygon, axis, cuts, budget):
    remaining = polygon
    for cut in cuts:
        budget.check()
        if not remaining:
            return
        low = min(p[axis] for p in remaining); high = max(p[axis] for p in remaining)
        if cut <= low:
            continue
        if cut >= high:
            break
        left = _clip_axis(remaining, axis, cut, True)
        if len(left) >= 3:
            yield left
        remaining = _clip_axis(remaining, axis, cut, False)
    if len(remaining) >= 3:
        yield remaining


def _ears(polygon, budget):
    # Convex cells may retain collinear boundary controls from neighbouring
    # bands. Removing the largest nonzero ear retains those controls without
    # adding a hand-placed interior support or discarding a source partition.
    remaining = list(polygon)
    while len(remaining) > 3:
        budget.check()
        total = abs(sum(_cross((0, 0), a, b) for a, b in zip(remaining, remaining[1:]+remaining[:1])))
        candidates = [(abs(_cross(remaining[i-1], p, remaining[(i+1) % len(remaining)])), i)
                      for i, p in enumerate(remaining)
                      if 0 < abs(_cross(remaining[i-1], p, remaining[(i+1) % len(remaining)])) < total]
        if not candidates:
            raise StudioError('Section-conforming material cell cannot retain its boundary controls')
        area, index = max(candidates, key=lambda row: (row[0], -row[1]))
        if not area:
            raise StudioError('Section-conforming material cell is collapsed')
        yield [remaining[index-1], remaining[index], remaining[(index+1) % len(remaining)]]
        remaining.pop(index)
    if not _cross(*remaining):
        raise StudioError('Section-conforming material cell cannot retain its boundary controls')
    yield remaining


def section_cage_state(piece, frame, pid, n, budget, evaluate):
    """Preserve declared source refinement and partition it at measured V rows.

    U interpolation remains a measured hypothesis. In particular, near-equal
    arc knots are not fused and no tiny U cells are manufactured to conceal
    the existing minimum cage determinant. Final material gates still apply.
    """
    from .garment_guides import _source_limb_mesh
    from .source_seam_coupling import _refinement_keys
    # These are lower bounds for any V partition of the declared seed. Check
    # them before allocating that refinement, then charge only added cells.
    budget.reserve(len(piece['vertices']), len(piece['faces'])*n*n)
    seed_uv, seed_faces = _source_limb_mesh(piece, n)
    budget.reserve(len(seed_uv)-len(piece['vertices']), 0)
    reserved_controls, reserved_triangles = len(seed_uv), len(seed_faces)
    keys = _refinement_keys(piece, n, budget)
    for i, point in enumerate(piece['vertices']):
        seed_uv[keys[((i, n),)]] = list(point)
    compiled = _compile_arc_sections(frame, pid)
    vertices = [tuple(Fraction(v) for v in point) for point in seed_uv]
    # Evaluate original material boundary identities before rounding, instead
    # of turning the old weighted float's accumulated round-off into geometry.
    for a in range(len(piece['vertices'])):
        b = (a+1) % len(piece['vertices'])
        for step in range(n+1):
            key = tuple(sorted((i, weight) for i, weight in ((a, n-step), (b, step)) if weight))
            vertices[keys[key]] = tuple(sum(Fraction(piece['vertices'][i][k])*weight for i, weight in key)/n
                                       for k in (0, 1))
    if min(p[1] for p in vertices) < compiled[0]['v_cm'] or max(p[1] for p in vertices) > compiled[-1]['v_cm']:
        raise StudioError('Source material V domain exceeds its measured guide sections: '+pid)
    rows = [Fraction(row['v_cm']) for row in compiled]
    fragments = []; lines = {}
    source_ids = [i for i, _ in sorted(enumerate(piece['faces']), key=lambda row:tuple(sorted(row[1])))
                  for _ in range(n*n)]
    for face_id, face in zip(source_ids, seed_faces):
        budget.check()
        for cell in _strips([vertices[i] for i in face], 1, rows[1:-1], budget):
            fragments.append((face_id, cell))
            if len(fragments)+budget.triangles-reserved_triangles > budget.limits['max_triangles']:
                raise StudioError('Section-conforming cage triangle budget exhausted')
            for a, b in zip(cell, cell[1:]+cell[:1]):
                lines.setdefault(_line(a, b), set()).update((a, b))
    indexed_lines = {}
    for key, points in lines.items():
        budget.check()
        axis = 0 if key[1] else 1
        ordered = sorted(points, key=lambda p: p[axis])
        indexed_lines[key] = (axis, ordered, [p[axis] for p in ordered])
    source_corners = {tuple(Fraction(v) for v in p):list(p) for p in piece['vertices']}
    controls = {}; uv = []; triangles = []; source_faces = []
    def control(point):
        if point not in controls:
            if len(uv) >= reserved_controls:
                budget.reserve(1, 0)
            controls[point] = len(uv); uv.append(source_corners.get(point, [float(v) for v in point]))
        return controls[point]
    for face_id, cell in fragments:
        budget.check(); boundary = []
        for a, b in zip(cell, cell[1:]+cell[:1]):
            axis, points, values = indexed_lines[_line(a, b)]
            low, high = sorted((a[axis], b[axis]))
            segment = points[bisect_left(values, low):bisect_right(values, high)]
            if a[axis] > b[axis]:
                segment = list(reversed(segment))
            boundary.extend(segment[:-1])
        for face in _ears(boundary, budget):
            if len(triangles) >= reserved_triangles:
                budget.reserve(0, 1)
            triangles.append([control(point) for point in face]); source_faces.append(face_id)
    # Enforce the existing cage representation limit before target evaluation;
    # a near-coincident cut is reported, never silently merged or widened.
    for face_id, face in enumerate(triangles):
        budget.check()
        determinant = _cross(*(uv[i] for i in face))
        if abs(determinant) < 1e-10:
            error = StudioError('Collapsed source-UV preform cage triangle: '+pid)
            error.guide_diagnostic = {'reason':'SECTION_PARTITION_NOT_REPRESENTABLE',
                'piece':pid, 'cage_triangle':face_id, 'source_face_index':source_faces[face_id],
                'source_uv_cm':[uv[i] for i in face], 'determinant_cm2':determinant,
                'existing_minimum_abs_determinant_cm2':1e-10, 'qualification':'NONE',
                'source_mutated':False, 'cuts_merged':False}
            raise error
    targets = []
    for point in uv:
        budget.check(); targets.append(evaluate(point))
    cage = {'source_ref':frame['source_ref'], 'uv_cm':uv, 'target_cm':targets, 'triangles':triangles}
    if len(uv) < reserved_controls or len(triangles) < reserved_triangles:
        raise StudioError('Section partition discarded existing source refinement controls or faces')
    return validated_cage_state(piece, cage, pid, n, budget, evaluate,
                                reserved=True, source_faces=source_faces)


def validated_cage_state(piece, frame, pid, n, budget, evaluate, *, reserved=False, source_faces=None):
    """Validate material support and manifold disk, then preserve its controls.

    This accepts only source-conforming faces. A received alternative source
    triangulation crossing original faces is refused, rather than assigning
    fictitious source-face provenance or trusting a marker in its reference.
    """
    from .garment_guides import _source_limb_mesh
    from .source_seam_coupling import _near_parameter, _triangle_edges
    _source_limb_mesh(piece, 1)
    if not reserved:
        budget.reserve(len(frame.get('uv_cm', [])), len(frame.get('triangles', [])))
    compiled = _compile_cage(frame, pid, check_time=budget.check)
    uv = copy.deepcopy(frame['uv_cm']); triangles = copy.deepcopy(frame['triangles'])
    if len(set(map(tuple, uv))) != len(uv):
        raise StudioError('Source-conforming cage has duplicate UV controls: '+pid)
    source = piece['vertices']; lookup = {tuple(p):i for i, p in enumerate(uv)}
    if any(tuple(p) not in lookup for p in source):
        raise StudioError('Source-conforming cage must retain every exact source corner: '+pid)
    source_orientation = math.fsum(_cross([0., 0.], a, b) for a, b in zip(source, source[1:]+source[:1]))
    owners = {}; oriented = {}; incident = {}; used = set(); measured_area = 0.
    supports = []
    material_frame = {'uv_cm':source, 'target_cm':[list(p)+[0.] for p in source],
                      'triangles':piece['faces']}
    material_faces = _compile_cage(material_frame, pid, check_time=budget.check)
    def supported(point, face_id):
        # Reuse canonical cage membership, including its existing arithmetic
        # boundary handling. No new source-support tolerance is introduced.
        budget.check()
        try:
            _cage_point(material_frame, [material_faces[face_id]], point, pid)
            return True
        except StudioError:
            return False
    for face_id, face, a, b, c, det in compiled:
        budget.check()
        if det*source_orientation <= 0:
            raise StudioError('Source-conforming cage winding differs from its material source: '+pid)
        used.update(face); measured_area += abs(det)/2
        for vertex in face:
            incident.setdefault(vertex, []).append(face)
        candidates = [source_faces[face_id]] if source_faces is not None else range(len(piece['faces']))
        support = next((i for i in candidates if all(supported(uv[j], i) for j in face)), None)
        if support is None:
            raise StudioError('Cage triangle is not supported by one original source material face: '+pid)
        supports.append(support)
        for x, y in zip(face, face[1:]+face[:1]):
            edge = tuple(sorted((x, y)))
            owners.setdefault(edge, set()).add(face_id); oriented.setdefault(edge, []).append((x, y))
    if used != set(range(len(uv))) or len(uv)-len(owners)+len(triangles) != 1:
        raise StudioError('Source-conforming cage is not a complete material disk: '+pid)
    for edge, uses in oriented.items():
        budget.check()
        if len(uses) not in (1, 2) or (len(uses) == 2 and uses[0] != tuple(reversed(uses[1]))):
            raise StudioError('Source-conforming cage has nonmanifold or contradictory edges: '+pid)
    # The existing validator has no callback. Check each incident star with
    # it, rather than leaving all vertex-link traversals between deadlines.
    # Neighbour links in a star are subsets incident to its centre; edge
    # ownership has already bounded their degree. The central link is exact.
    for star in incident.values():
        budget.check(); _vertex_manifold(star); budget.check()
    boundary_edges = []
    for edge, uses in owners.items():
        budget.check()
        if len(uses) == 1:
            boundary_edges.append(edge)
    segments = {}; assigned = set()
    for a in range(len(source)):
        budget.check(); b = (a+1) % len(source); lo, hi = sorted((a, b))
        axis = max((0, 1), key=lambda k: abs(source[hi][k]-source[lo][k]))
        span = source[hi][axis]-source[lo][axis]; entries = {}
        # Original corners delimit their original material segment. Interior
        # controls are admitted only on actual boundary edges, never by a
        # search for nearby world targets.
        for edge in boundary_edges:
            budget.check()
            ts = [(uv[i][axis]-source[lo][axis])/span for i in edge]
            if (all(0 <= t <= 1 or _near_parameter(t, 0.) or _near_parameter(t, 1.) for t in ts)
                    and all(_rounded_source_segment(uv[i], source[lo], source[hi]) for i in edge)):
                if edge in assigned:
                    raise StudioError('Source-conforming cage boundary has ambiguous source ownership: '+pid)
                assigned.add(edge)
                for i, t in zip(edge, ts):
                    entries[i] = 0. if i == lookup[tuple(source[lo])] else 1. if i == lookup[tuple(source[hi])] else t
        controls = sorted((t, i) for i, t in entries.items())
        if (not controls or controls[0] != (0., lookup[tuple(source[lo])])
                or controls[-1] != (1., lookup[tuple(source[hi])])
                or any(_near_parameter(a[0], b[0]) for a, b in zip(controls, controls[1:]))
                or any(len(owners.get(tuple(sorted((a[1], b[1]))), set())) != 1
                       for a, b in zip(controls, controls[1:]))):
            error = StudioError('Source-conforming cage boundary does not cover an original source segment once: '+pid)
            error.guide_diagnostic = {'reason':'SOURCE_BOUNDARY_NOT_REPRESENTED', 'source_segment_vertex_ids':[lo, hi],
                'source_endpoints_cm':[source[lo], source[hi]], 'controls':controls,
                'source_uv_cm':[uv[i] for _, i in controls], 'qualification':'NONE'}
            raise error
        segments[lo, hi] = controls
    if assigned != set(boundary_edges):
        raise StudioError('Source-conforming cage has a hole or foreign material boundary: '+pid)
    source_area = abs(source_orientation)/2
    if abs(measured_area-source_area) > max(1e-7, source_area*1e-10):
        raise StudioError('Source-conforming cage does not cover its original source area: '+pid)
    return {'uv':uv, 'triangles':triangles, 'original':copy.deepcopy(frame['target_cm']),
        'evaluate':evaluate, 'keys':{((i, n),):lookup[tuple(p)] for i, p in enumerate(source)},
        'segments':segments, 'owners':owners, 'triangle_source_faces':supports, 'inserted':[]}
