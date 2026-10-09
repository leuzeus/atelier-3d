"""Source-sewn limb domains and conforming, bounded auxiliary cages.

No anatomy or garment role is inferred here. The caller supplies its measured
axis, center law and anatomical attachment; this kernel preserves source UV.
"""
from fractions import Fraction
import math

from .core import StudioError, digest, sha
from .cloth_metrics import principal_stretches
from .guide_cage_sampling import _strips, _ears, _cross, validated_cage_state


MODE = 'SOURCE_SEWN_DOMAIN_V1'
MAX_CAGE_TRIANGLES = 32768


def _finite(value):
    return type(value) in (int, float) and math.isfinite(value)


def compile_sewn_domain(piece, paired_records, pid, budget):
    """Bind the monotone paired source domain, never the whole bounding box."""
    from .garment_guides import _source_limb_mesh, _source_span
    budget.check(); _source_limb_mesh(piece, 1)
    if not isinstance(paired_records, list) or not 2 <= len(paired_records) <= len(piece['vertices']):
        raise StudioError('Sewn limb domain requires explicit paired source records: '+pid)
    records = []
    for record in paired_records:
        budget.check()
        if not isinstance(record, dict) or not _finite(record.get('source_v_cm')):
            raise StudioError('Sewn limb domain requires finite material V records: '+pid)
        pair = record.get('source_uv_pair_cm'); v = record['source_v_cm']
        if (not isinstance(pair, (list, tuple)) or len(pair) != 2
                or any(not isinstance(p, (list, tuple)) or len(p) != 2
                       or not all(_finite(x) for x in p) for p in pair)
                or any(abs(p[1]-v) > 1e-8 for p in pair)):
            raise StudioError('Sewn limb domain requires source partners at one material V: '+pid)
        width = abs(pair[0][0]-pair[1][0])
        if not math.isfinite(width) or width <= 1e-10:
            raise StudioError('Sewn limb circumference is collapsed: '+pid)
        records.append((v, sorted(p[0] for p in pair)))
    delta = [b[0]-a[0] for a, b in zip(records, records[1:])]
    if any(not math.isfinite(value) or value == 0 for value in delta) or not (
            all(value > 0 for value in delta) or all(value < 0 for value in delta)):
        raise StudioError('Sewn limb source domain must be strictly monotone in V: '+pid)
    records.sort()
    low, high = records[0][0], records[-1][0]
    source_low = min(p[1] for p in piece['vertices']); source_high = max(p[1] for p in piece['vertices'])
    if not math.isfinite(source_high-source_low) or low < source_low or high > source_high:
        raise StudioError('Sewn limb domain exceeds its actual source support: '+pid)
    # All changes of either source boundary are checked. Between these rows
    # both the paired chains and the polygon edges are linear in material V.
    rows = sorted({p[1] for p in piece['vertices']} | {row[0] for row in records})
    for v in rows:
        budget.check()
        actual = _source_span(piece, v)
        if low <= v <= high:
            index = next(i for i in range(len(records)-1) if records[i][0] <= v <= records[i+1][0])
            a, b = records[index:index+2]; fraction = (v-a[0])/(b[0]-a[0])
            expected = [a[1][k]+fraction*(b[1][k]-a[1][k]) for k in (0, 1)]
            if (not all(_finite(value) for value in (*actual, *expected))
                    or not math.isfinite(actual[1]-actual[0]) or actual[1]-actual[0] <= 1e-10
                    or any(abs(x-y) > 1e-8 for x, y in zip(actual, expected))):
                raise StudioError('Sewn limb partners do not bound the entire source interval: '+pid)
    terminal = [list(_source_span(piece, v)) for v in (low, high)]
    if any(not _finite(a) or not _finite(b) or not math.isfinite(b-a) or b-a <= 1e-10 for a, b in terminal):
        raise StudioError('Sewn limb terminal circumference is collapsed: '+pid)
    for u, v in piece['vertices']:
        budget.check()
        interval = terminal[0] if v < low else terminal[1] if v > high else None
        if interval is not None and not interval[0] <= u <= interval[1]:
            raise StudioError('Open limb extension exceeds its terminal sewn U interval: '+pid)
    return {'method': MODE, 'source_piece_sha256': digest(piece), 'source_pairs_sha256': digest(paired_records),
        'source_v_domain_cm': [source_low, source_high], 'sewn_v_domain_cm': [low, high],
        'terminal_source_u_intervals_cm': terminal, 'source_v_knots_cm': rows,
        'map_policy': 'PAIRED_SOURCE_V_TUBE_WITH_CONSTANT_TERMINAL_U_RADIUS_EXTENSION',
        'continuity': 'C0_AT_SEWN_LIMITS_V_DERIVATIVE_MAY_CHANGE',
        'extension_outside_terminal_u_interval': 'REFUSED',
        'source_uv_scaled': False, 'source_mutated': False, 'qualification': 'NONE'}


def sewn_domain_interval(piece, domain, query, pid, budget):
    """Use the terminal circumference outside the actually sewn V interval."""
    from .garment_guides import _source_span
    budget.check()
    if (not isinstance(query, (list, tuple)) or len(query) != 2
            or not all(_finite(x) for x in query)):
        raise StudioError('Sewn limb evaluation requires finite material UV: '+pid)
    u, v = query; source_low, source_high = domain['source_v_domain_cm']
    if not source_low <= v <= source_high:
        raise StudioError('Sewn limb query lies outside source material V: '+pid)
    actual_low, actual_high = _source_span(piece, v)
    if not actual_low-1e-8 <= u <= actual_high+1e-8:
        raise StudioError('Sewn limb query lies outside actual source support: '+pid)
    low, high = domain['sewn_v_domain_cm']
    interval = (domain['terminal_source_u_intervals_cm'][0] if v < low else
                domain['terminal_source_u_intervals_cm'][1] if v > high else
                _source_span(piece, v))
    if interval[1]-interval[0] <= 1e-10 or not interval[0]-1e-8 <= u <= interval[1]+1e-8:
        raise StudioError('Sewn limb query lies outside its noncollapsed terminal U interval: '+pid)
    return interval


def sewn_domain_cage(piece, domain, pid, subdivisions, evaluate, source_ref, budget):
    """Partition source triangles at V knots, then refine rationally once."""
    if type(subdivisions) is not int or not 2 <= subdivisions <= 16 or not callable(evaluate):
        raise StudioError('Sewn limb cage requires subdivisions in 2..16 and a declared evaluator')
    if not isinstance(source_ref, str) or not source_ref or digest(piece) != domain['source_piece_sha256']:
        raise StudioError('Sewn limb cage source identity is missing or stale: '+pid)
    before = digest([piece, domain]); budget.check()
    vertices = [tuple(Fraction(x) for x in point) for point in piece['vertices']]
    cuts = [Fraction(x) for x in domain['source_v_knots_cm']]
    cells = []; area = Fraction(0)
    source_area = sum(abs(_cross(*(vertices[i] for i in face))) for face in piece['faces'])/2
    try:
        source_area_cm2 = float(source_area)
    except OverflowError as error:
        raise StudioError('Sewn limb source material area is not representable: '+pid) from error
    if not math.isfinite(source_area_cm2):
        raise StudioError('Sewn limb source material area is not finite: '+pid)
    for owner, face in sorted(enumerate(piece['faces']), key=lambda row: tuple(sorted(row[1]))):
        budget.check()
        for polygon in _strips([vertices[i] for i in face], 1, cuts, budget):
            for triangle in _ears(polygon, budget):
                cells.append((owner, triangle)); area += abs(_cross(*triangle))/2
                count = len(cells)*subdivisions**2
                if count > MAX_CAGE_TRIANGLES or count+budget.triangles > budget.limits['max_triangles']:
                    raise StudioError('Sewn limb cage triangle budget exhausted before refinement: '+pid)
    if area != source_area:
        raise StudioError('Sewn limb partition failed exact rational source area conservation: '+pid)
    corners = {point: list(original) for point, original in zip(vertices, piece['vertices'])}
    ids = {}; uv = []; triangles = []; owners = []

    def control(point):
        if point not in ids:
            budget.reserve(1, 0); ids[point] = len(uv)
            uv.append(corners.get(point, [float(x) for x in point]))
        return ids[point]

    for owner, triangle in cells:
        budget.check(); grid = {}
        for i in range(subdivisions+1):
            for j in range(subdivisions+1-i):
                budget.check(); weights = (subdivisions-i-j, i, j)
                point = tuple(sum(p[k]*w for p, w in zip(triangle, weights))/subdivisions for k in (0, 1))
                grid[i, j] = control(point)
        for i in range(subdivisions):
            for j in range(subdivisions-i):
                budget.reserve(0, 1)
                triangles.append([grid[i, j], grid[i+1, j], grid[i, j+1]]); owners.append(owner)
                if j < subdivisions-i-1:
                    budget.reserve(0, 1)
                    triangles.append([grid[i+1, j], grid[i+1, j+1], grid[i, j+1]]); owners.append(owner)
    targets = []
    for point in uv:
        budget.check(); targets.append(evaluate(point))
    frame = {'source_ref': source_ref+'; '+MODE+'; sewn-domain:'+digest(domain)+'; kernel:'+sha(__file__),
             'uv_cm': uv, 'target_cm': targets, 'triangles': triangles}
    state = validated_cage_state(piece, frame, pid, 1, budget, evaluate, reserved=True, source_faces=owners)
    ranges = {name: [math.inf, -math.inf] for name in ('SEWN', 'OPEN_EXTENSION')}
    counts = {name: 0 for name in ranges}; low, high = domain['sewn_v_domain_cm']
    for face in triangles:
        budget.check(); source = [uv[i] for i in face]
        placed = [targets[i] for i in face]; metric = principal_stretches(source, placed)
        if metric is None or not all(_finite(x) for x in metric):
            raise StudioError('Sewn limb cage has an unmeasurable principal metric: '+pid)
        middle = math.fsum(p[1] for p in source)/3
        name = 'SEWN' if low <= middle <= high else 'OPEN_EXTENSION'
        ranges[name][0] = min(ranges[name][0], metric[0]); ranges[name][1] = max(ranges[name][1], metric[1])
        counts[name] += 1
    if before != digest([piece, domain]):
        raise StudioError('Sewn limb partition mutated source or declared domain: '+pid)
    return frame, {'method': 'RATIONAL_SOURCE_V_PARTITION_THEN_BARYCENTRIC_REFINEMENT',
        'kernel_code_sha256': sha(__file__), 'subdivisions': subdivisions,
        'source_faces': len(piece['faces']), 'partition_base_triangles': len(cells),
        'control_vertices': len(uv), 'control_triangles': len(triangles),
        'source_faces_covered': len(set(state['triangle_source_faces'])),
        'triangle_source_faces': state['triangle_source_faces'], 'source_segments': len(state['segments']),
        'source_area_cm2': source_area_cm2, 'exact_rational_partition_area_preserved': True,
        'source_boundary_validation': 'EXISTING_SOURCE_VALIDATOR_PASS', 'source_topology_changed': False,
        'cuts_cm': domain['source_v_knots_cm'], 'maximum_cage_triangles': MAX_CAGE_TRIANGLES,
        'principal_ranges_by_domain': {name: values if counts[name] else None for name, values in ranges.items()},
        'triangle_counts_by_domain': counts, 'metric_stage': 'BEFORE_RIGID_ANATOMICAL_ATTACHMENT',
        'material_admission': 'NOT_GRANTED', 'qualification': 'NONE'}
