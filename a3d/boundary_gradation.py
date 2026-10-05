"""Source-bound boundary grading only; no triangulator, pin or admission.

The caller owns the shared envelope and native coordinate transport. The
algorithm is the reviewed corner selection followed by synchronized post-union
grading. An opaque caller ledger persists into later meshing; this module never
opens a clock, resets counters, or manufactures an execution permission.
"""
import copy
from fractions import Fraction
import hashlib
import json
import math

from .core import StudioError, digest
from .cloth_metrics import triangle_metrics
from .sewing import (chain_lengths, distance, edge_chain, prepare_boundaries,
                     sample_chain, signed_area)
from .board_contract import simple_polygon

VERSION = 'SYNCHRONIZED_SOURCE_BOUNDARY_GRADATION_V1'


class GradedBoundaryRefusal(StudioError):
    def __init__(self, reason, report=None):
        self.reason = reason
        self.status = 'INCOMPLETE' if reason in (
            'BUDGET_EXHAUSTED','DEADLINE_EXHAUSTED','STOP_REQUESTED','CALLER_STOP_OR_DEADLINE') else 'REFUSED'
        self.diagnostic = {'graded_boundary_report': report or {
            'status': 'REFUSED_SOURCE_BOUNDARY_PREPARATION',
            'qualification': 'NONE', 'native': 'NOT_EXECUTED', 'refusal': reason}}
        super().__init__(reason)


def _tick(envelope, phase):
    envelope.check(phase)
    envelope.reserve('work_steps', 1)
    envelope.check(phase)


def _json_text_size(value, check):
    size = 2
    for char in value:
        check()
        number = ord(char)
        if char in ('"', '\\') or char in ('\b', '\f', '\n', '\r', '\t'):
            size += 2
        elif number < 32:
            size += 6
        elif 0xD800 <= number <= 0xDFFF:
            raise GradedBoundaryRefusal('NON_UTF8_SOURCE_STRING')
        else:
            size += 1 if number < 128 else 2 if number < 2048 else 3 if number < 65536 else 4
    return size


def _shape(value, check, active=None):
    """Whole compact-UTF8 output accounting, including keys and receipt data.

    Native numeric maps in the sampler's working DTO are permitted, with their
    key types retained by the preservation hash. Mixed string/numeric keys and
    JSON key aliases are rejected. Returned boundary DTOs omit those work maps.
    """
    active = set() if active is None else active
    check()
    kind = type(value)
    if kind in (dict, list):
        if id(value) in active:
            raise GradedBoundaryRefusal('CYCLIC_SOURCE_INPUT')
        active.add(id(value)); nodes = 1; size = 2
        try:
            if kind is dict:
                numeric = [type(key) in (int, float) for key in value]
                if numeric and any(numeric) and not all(numeric):
                    raise GradedBoundaryRefusal('MIXED_SOURCE_KEY_TYPES')
                encoded = set()
                for key, item in value.items():
                    check()
                    if type(key) not in (str, int, float) or type(key) is float and not math.isfinite(key):
                        raise GradedBoundaryRefusal('INVALID_SOURCE_KEY_TYPE')
                    text = key if type(key) is str else str(key)
                    if text in encoded:
                        raise GradedBoundaryRefusal('SOURCE_JSON_KEY_ALIAS')
                    encoded.add(text)
                    child_nodes, child_size = _shape(item, check, active)
                    nodes += 1 + child_nodes
                    size += _json_text_size(text, check) + 1 + child_size
            else:
                for item in value:
                    child_nodes, child_size = _shape(item, check, active)
                    nodes += child_nodes; size += child_size
            return nodes, size + max(0, len(value)-1)
        finally:
            active.remove(id(value))
    if kind is str:
        return 1, _json_text_size(value, check)
    if kind is bool:
        return 1, 4 if value else 5
    if value is None:
        return 1, 4
    if kind in (int, float):
        if kind is float and not math.isfinite(value):
            raise GradedBoundaryRefusal('NONFINITE_SOURCE_INPUT')
        # Reserve work before conversion of a possibly large native integer.
        if kind is int:
            for _ in range(max(1, value.bit_length() // 64)):
                check()
        return 1, len(json.dumps(value, allow_nan=False))
    raise GradedBoundaryRefusal('NON_STRUCTURED_SOURCE_INPUT')


def _preservation_hash(value, check):
    """Streaming, type-sensitive identity, including native numeric map keys."""
    result = hashlib.sha256()
    def visit(item):
        check(); kind = type(item)
        result.update(kind.__name__.encode('ascii') + b':')
        if kind is dict:
            for key in sorted(item):
                visit(key); visit(item[key])
        elif kind is list:
            for child in item:
                visit(child)
        else:
            result.update(json.dumps(item, ensure_ascii=False, allow_nan=False,
                separators=(',', ':')).encode('utf-8'))
        result.update(b';')
    visit(value); check()
    return result.hexdigest()


def _capture(value, envelope):
    check = lambda: _tick(envelope, 'capture')
    nodes, size = _shape(value, check)
    envelope.reserve('capture_nodes', nodes)
    envelope.reserve('capture_bytes', size)
    envelope.check('before_capture_copy')
    identity = _preservation_hash(value, check)
    captured = copy.deepcopy(value)
    envelope.check('after_capture_copy')
    if _preservation_hash(captured, check) != identity:
        raise GradedBoundaryRefusal('SOURCE_MUTATED_DURING_CAPTURE')
    return captured, identity


def _existing_source_perimeter_key(source, chain, parameter, perimeter, check):
    """Replay only the existing sampler's ``put`` storage-key route.

    Eight-decimal keys and the segment-stop branch are inherited from
    prepare_boundaries; they are not a coordinate tolerance. No point is
    inserted, snapped or changed here, and neighbouring arc samples cannot
    acquire SOURCE_VERTEX provenance through this function.
    """
    check(); lengths = chain_lengths([source[index] for index in chain])
    vertex = next((index for index, stop in zip(chain, lengths)
                   if parameter == stop / lengths[-1]), None)
    if vertex is not None:
        key = round(perimeter[vertex] % perimeter[-1], 8)
    else:
        target = parameter * lengths[-1]
        for j, (a, b) in enumerate(zip(chain, chain[1:])):
            check()
            if target <= lengths[j+1] + 1e-8:
                fraction = min(1., max(0., (target-lengths[j])/(lengths[j+1]-lengths[j])))
                lower = a if (b-a) % len(source) == 1 else b
                along = fraction if lower == a else 1-fraction
                position = (perimeter[lower] + along *
                            (perimeter[lower+1]-perimeter[lower])) % perimeter[-1]
                key = round(position, 8)
                break
        else:
            raise GradedBoundaryRefusal('SOURCE_SEAM_SAMPLE_CHANGED')
    if abs(key-perimeter[-1]) < 1e-8:
        key = 0.
    check()
    return key


def _source_identity(data, boundaries, seams, recipe, check):
    """Check exact captured route/UV consistency, without native admission.

    Public grading also re-samples the declared source and requires every old
    coordinate at its exact retained key. This local check alone does not
    authenticate a caller-asserted interpolation as the canonical last writer.
    """
    if set(boundaries) != set(data['pieces']) or set(seams) != {s['id'] for s in data['seams']}:
        raise GradedBoundaryRefusal('SOURCE_PIECE_OR_SEAM_INVENTORY_CHANGED')
    if len(data['seams']) != len(seams):
        raise GradedBoundaryRefusal('DUPLICATE_SOURCE_SEAM_ID')
    # Replay the sampler's declared oriented seam and uncovered free-run
    # routes. Adjacency alone would admit an invented backtracking chain.
    routes = {pid: set() for pid in data['pieces']}
    covered = {pid: set() for pid in data['pieces']}
    for seam in data['seams']:
        for side in ('a', 'b'):
            check(); pid = seam['piece_' + side]
            if pid not in routes:
                raise GradedBoundaryRefusal('MISSING_DECLARED_SOURCE_PARTNER')
            chain, _, _ = edge_chain(data['pieces'][pid], seam['edge_' + side])
            if side == 'b' and seam['orientation'] == 'reverse':
                chain = list(reversed(chain))
            routes[pid].add(tuple(chain))
            covered[pid].update(tuple(sorted((a,b))) for a,b in zip(chain,chain[1:]))
    for pid, piece in data['pieces'].items():
        check(); n = len(piece['vertices'])
        anchors = {0} | {i for edge in piece['edges'].values() for i in (edge[0],edge[-1])}
        for i in range(n):
            check()
            if ((tuple(sorted(((i-1)%n,i))) in covered[pid]) !=
                (tuple(sorted((i,(i+1)%n))) in covered[pid])):
                anchors.add(i)
        anchors = sorted(anchors)
        for start, end in zip(anchors,anchors[1:]+[anchors[0]+n]):
            check(); chain = [i%n for i in range(start,end+1)]
            sewn = [tuple(sorted((a,b))) in covered[pid] for a,b in zip(chain,chain[1:])]
            if not any(sewn):
                routes[pid].add(tuple(chain))
            elif not all(sewn):
                raise GradedBoundaryRefusal('INVALID_SOURCE_ARC_IDENTITY')
    for pid, row in sorted(boundaries.items()):
        check(); source = data['pieces'][pid]['vertices']
        if row['source'] != source or row['source_sha256'] != digest(source):
            raise GradedBoundaryRefusal('FOREIGN_BASELINE_SOURCE')
        if row['perimeter'] != chain_lengths(source + source[:1]):
            raise GradedBoundaryRefusal('FOREIGN_BASELINE_PERIMETER')
        polygon, keys, provenance = row['polygon'], row['keys'], row['sample_provenance']
        if len(keys) != len(polygon) or len(provenance) != len(polygon) or keys != sorted(keys) or len(set(keys)) != len(keys):
            raise GradedBoundaryRefusal('SOURCE_PARAMETER_KEY_ALIAS')
        mandatory = {0} | {i for edge in data['pieces'][pid]['edges'].values() for i in (edge[0],edge[-1])}
        closed = source + source[:1]
        for index,(a,b,c) in enumerate(zip(closed,closed[1:],closed[2:]),1):
            check()
            u=[Fraction(b[k])-Fraction(a[k]) for k in (0,1)]
            v=[Fraction(c[k])-Fraction(b[k]) for k in (0,1)]
            if u[0]*v[1]!=u[1]*v[0] or sum(x*y for x,y in zip(u,v))<=0:
                mandatory.add(index)
        lookup=dict(zip(keys,polygon))
        for index in mandatory:
            check();key=round(row['perimeter'][index],8)
            if key not in lookup or lookup[key]!=source[index]:
                raise GradedBoundaryRefusal('MANDATORY_SOURCE_CORNER_OR_STOP_LOST')
        for index, (point, key, identity) in enumerate(zip(polygon, keys, provenance)):
            check()
            if len(point) != 2 or any(type(x) not in (int, float) or not math.isfinite(x) for x in point):
                raise GradedBoundaryRefusal('INVALID_SOURCE_UV_POINT')
            if identity['kind'] == 'SOURCE_VERTEX':
                vertex = identity['source_vertex']
                if type(vertex) is not int or not 0 <= vertex < len(source):
                    raise GradedBoundaryRefusal('INVALID_SOURCE_VERTEX_IDENTITY')
                expected = source[vertex]
            elif identity['kind'] == 'SOURCE_ARC_INTERPOLATION':
                chain, parameter = identity['source_chain'], identity['source_parameter']
                if (len(chain) < 2 or any(type(j) is not int or not 0 <= j < len(source) for j in chain)
                    or any((b-a) % len(source) not in (1, len(source)-1) for a,b in zip(chain,chain[1:]))
                    or tuple(chain) not in routes[pid]
                    or type(parameter) not in (int,float) or not math.isfinite(parameter) or not 0 <= parameter <= 1):
                    raise GradedBoundaryRefusal('INVALID_SOURCE_ARC_IDENTITY')
                expected = sample_chain([source[j] for j in chain], parameter)
                if _existing_source_perimeter_key(source, chain, parameter,
                        row['perimeter'], check) != key:
                    raise GradedBoundaryRefusal('SOURCE_MATERIAL_UV_CHANGED')
            else:
                raise GradedBoundaryRefusal('UNKNOWN_SOURCE_MATERIAL_IDENTITY')
            if point != expected or identity.get('source_perimeter_key_cm', key) != key:
                raise GradedBoundaryRefusal('SOURCE_MATERIAL_UV_CHANGED')
            if identity.get('derived_boundary_vertex', index) != index:
                raise GradedBoundaryRefusal('SOURCE_LOCAL_VERTEX_IDENTITY_CHANGED')
    for source in data['seams']:
        check(); sid = source['id']; relation = seams[sid]
        if any(relation[key] != source[key] for key in ('piece_a', 'piece_b')) or relation['kind'] != recipe['seams'][sid]['kind']:
            raise GradedBoundaryRefusal('SOURCE_SEAM_RELATION_CHANGED')
        values = relation['parameters']
        if (values != sorted(values) or len(set(values)) != len(values) or
            any(type(t) not in (int,float) or not math.isfinite(t) or not 0 <= t <= 1 for t in values)):
            raise GradedBoundaryRefusal('INVALID_EXACT_COMMON_PARAMETERS')
        for side in ('a', 'b'):
            pid = source['piece_' + side]
            if pid not in boundaries:
                raise GradedBoundaryRefusal('MISSING_DECLARED_SOURCE_PARTNER')
            chain_ids, chain, _ = edge_chain(data['pieces'][pid], source['edge_' + side])
            if side == 'b' and source['orientation'] == 'reverse':
                chain_ids = list(reversed(chain_ids))
                chain = list(reversed(chain))
            indices = relation[side]
            if len(indices) != len(values) or len(set(indices)) != len(indices):
                raise GradedBoundaryRefusal('SOURCE_SEAM_PHYSICAL_IDENTITY_ALIAS')
            for parameter, index in zip(values, indices):
                check()
                if type(index) is not int or not 0 <= index < len(boundaries[pid]['polygon']):
                    raise GradedBoundaryRefusal('INVALID_SOURCE_SEAM_BOUNDARY_ID')
                if boundaries[pid]['polygon'][index] != sample_chain(chain, parameter):
                    # The sampler may bind a common fraction to the last
                    # interpolation written at its existing storage key, or
                    # preserve an authored vertex there. Its exact UV and
                    # provenance were checked above; replay both key routes
                    # without re-interpolating or tolerating a UV error.
                    row = boundaries[pid]; identity = row['sample_provenance'][index]
                    if identity['kind'] == 'SOURCE_VERTEX':
                        vertex = identity.get('source_vertex')
                        if (type(vertex) is not int or vertex not in chain_ids
                            or row['polygon'][index] != row['source'][vertex]):
                            raise GradedBoundaryRefusal('SOURCE_SEAM_SAMPLE_CHANGED')
                        stored_key = round(row['perimeter'][vertex] % row['perimeter'][-1], 8)
                        if abs(stored_key-row['perimeter'][-1]) < 1e-8:
                            stored_key = 0.
                    elif identity['kind'] == 'SOURCE_ARC_INTERPOLATION':
                        stored_chain = identity['source_chain']
                        stored_parameter = identity['source_parameter']
                        lengths = chain_lengths([row['source'][j] for j in stored_chain])
                        check()
                        # Exact authored stops take the sampler's vertex
                        # branch. A fabricated interpolation cannot replace
                        # that mandatory material identity in this fallback.
                        if any(stored_parameter == stop / lengths[-1] for stop in lengths):
                            raise GradedBoundaryRefusal('SOURCE_SEAM_SAMPLE_CHANGED')
                        stored_key = _existing_source_perimeter_key(row['source'],
                            stored_chain, stored_parameter, row['perimeter'], check)
                    else:
                        raise GradedBoundaryRefusal('SOURCE_SEAM_SAMPLE_CHANGED')
                    route_key = _existing_source_perimeter_key(row['source'],
                        chain_ids, parameter, row['perimeter'], check)
                    if row['keys'][index] != stored_key or route_key != stored_key:
                        raise GradedBoundaryRefusal('SOURCE_SEAM_SAMPLE_CHANGED')


def _transport_point(point, transport, check):
    check(); argument = list(point)
    result = transport(argument)
    check()
    if argument != point:
        raise GradedBoundaryRefusal('TRANSPORT_MUTATED_ITS_ARGUMENT')
    if type(result) not in (list,tuple) or len(result) != 2 or any(type(x) not in (int,float) or not math.isfinite(x) for x in result):
        raise GradedBoundaryRefusal('INVALID_COORDINATE_TRANSPORT')
    return list(result)


def _transport_aliases(boundaries, transport, check):
    for pid, row in sorted(boundaries.items()):
        seen = {}
        for point, key in zip(row['polygon'],row['keys']):
            value = tuple(_transport_point(point, transport, check))
            if value in seen and seen[value] != key:
                raise GradedBoundaryRefusal('DISTINCT_SOURCE_CONTROLS_ALIAS_AFTER_TRANSPORT',
                    {'status':'REFUSED_SOURCE_BOUNDARY_PREPARATION','qualification':'NONE',
                     'native':'NOT_EXECUTED','refusal':'DISTINCT_SOURCE_CONTROLS_ALIAS_AFTER_TRANSPORT',
                     'piece':pid,'source_keys':[seen[value],key],'transported_uv_cm':list(value)})
            seen[value] = key


def _sampling_cost(data, recipe, parameters, envelope, check):
    """Reserve conservative work for the existing, cooperative sampler.

    Raw grids, source turns, propagation and optional-seed comparisons are
    bounded before this legacy API is entered. No timeout interrupts it; checks
    on both sides ensure an expired operation cannot return qualified output.
    """
    source_count = sum(len(p['vertices']) for p in data['pieces'].values())
    raw = source_count + sum(len(v) for v in parameters.values())
    for piece in data['pieces'].values():
        check(); perimeter = chain_lengths(piece['vertices'] + piece['vertices'][:1])[-1]
        if not math.isfinite(perimeter / recipe['mesh']['spacing_cm']):
            raise GradedBoundaryRefusal('UNREPRESENTABLE_SOURCE_SAMPLING_DOMAIN')
        raw += math.ceil(perimeter / recipe['mesh']['spacing_cm']) + 1
    # This is attempted work, not a new geometric threshold or vertex cap.
    envelope.reserve('work_steps', max(1,raw * max(1,source_count) * max(1,len(data['seams']))))


def _sample(data, recipe, regular, parameters, baseline, envelope, check):
    check()
    envelope.reserve('sampling_calls', 1)
    envelope.reserve('sampling_point_slots', min(regular['max_vertices'],recipe['mesh']['max_vertices']))
    _sampling_cost(data,recipe,parameters,envelope,check)
    check()
    parts, seams, reports = prepare_boundaries(data,recipe,seam_parameters=parameters,
        regular_boundary_spacing_cm=regular['min_spacing_cm'])
    # The existing API has allocated its bounded batch. Register every new
    # material identity immediately, BEFORE validation or a downstream consumer.
    identities = {}
    for pid, part in sorted(parts.items()):
        if pid not in baseline:
            raise GradedBoundaryRefusal('SOURCE_PIECE_INVENTORY_CHANGED')
        original = set(baseline[pid]['keys'])
        identities[pid] = [{'source_sha256':part['source_sha256'], 'source_perimeter_key_cm':key}
                           for key in part['keys'] if key not in original]
    envelope.observe_material_controls(data['component_id'], identities)
    check()
    if sum(len(p['polygon']) for p in parts.values()) > min(regular['max_vertices'], recipe['mesh']['max_vertices']):
        raise GradedBoundaryRefusal('GLOBAL_SOURCE_BOUNDARY_BUDGET')
    _source_identity(data,parts,seams,recipe,check)
    return parts,seams,reports

def partition_distances(length,first_width,target_angle,max_insertions,check):
    """Minimal geometric straight-strip partition, with no new admission gate."""
    if (any(not math.isfinite(v) for v in (length,first_width,target_angle))
        or not 0<first_width<=length or not 0<target_angle<=60
        or type(max_insertions) is not int or max_insertions<0
        or not math.isfinite(length/first_width)):
        raise ValueError('INVALID_SOURCE_BOUNDARY_PARTITION_DOMAIN')
    growth_limit=1+1/math.tan(math.radians(target_angle))
    count=1
    while sum(growth_limit**k for k in range(count)) < length/first_width:
        check();count+=1
        if count-1>max_insertions:raise ValueError('DERIVED_BOUNDARY_INSERTION_BUDGET')
    if count>length/first_width:raise ValueError('NO_MONOTONE_STRAIGHT_BOUNDARY_PARTITION')
    lo,hi=1.,growth_limit
    for _ in range(64):
        check();mid=(lo+hi)*.5
        if sum(mid**k for k in range(count))<length/first_width:lo=mid
        else:hi=mid
    growth=(lo+hi)*.5;total=0.;values=[]
    for k in range(count):total+=first_width*growth**k;values.append(total)
    values[-1]=length
    return values,{'segments':count,'geometric_growth':growth,'straight_strip_growth_bound':growth_limit,
        'first_width_cm':first_width,'length_cm':length,'target_angle_degrees':target_angle,
        'scalar_bisection_steps':64,'qualification':'NONE'}


def _fan_math_candidate(polygon, corner, divisions, vector, metrics, area):
    previous, center, following = polygon[corner-1], polygon[corner], polygon[(corner+1)%len(polygon)]
    vprev = [a-b for a,b in zip(previous,center)]
    vnext = [a-b for a,b in zip(following,center)]
    lp, ln = math.hypot(*vprev), math.hypot(*vnext)
    sign = 1 if area(polygon) > 0 else -1
    incoming = [-x for x in vprev]
    turn = math.atan2(sign*(incoming[0]*vnext[1]-incoming[1]*vnext[0]),
                     sum(a*b for a,b in zip(incoming,vnext)))
    theta = math.pi-turn
    if ln <= lp:
        start, end, short, long, rotation = vnext, previous, ln, lp, sign
        short_index, long_index = (corner+1)%len(polygon), (corner-1)%len(polygon)
    else:
        start, end, short, long, rotation = vprev, following, lp, ln, -sign
        short_index, long_index = (corner-1)%len(polygon), (corner+1)%len(polygon)
    angle0 = math.atan2(start[1],start[0])
    exact = [polygon[short_index]]
    for k in range(1,divisions):
        radius = short*(long/short)**(k/divisions)
        angle = angle0+rotation*theta*k/divisions
        exact.append([center[0]+radius*math.cos(angle),center[1]+radius*math.sin(angle)])
    exact.append(end)
    values = [exact[0]]+[list(vector(p)) for p in exact[1:-1]]+[exact[-1]]
    triangles = [[center,a,b] for a,b in zip(values,values[1:])]
    rows = [metrics(t) for t in triangles]
    signs = [area(t) for t in triangles]
    unchanged = all(area([center,exact[k],exact[k+1]])*signs[k] > 0 for k in range(divisions))
    return {'source_corner':corner, 'source_short_endpoint':short_index,
        'source_long_endpoint':long_index, 'source_corner_cm':list(center),
        'source_endpoints_cm':[list(exact[0]),list(exact[-1])],
        'short_length_cm':short, 'long_length_cm':long,
        'interior_angle_degrees':math.degrees(theta), 'divisions':divisions,
        'radial_ratio':(long/short)**(1/divisions), 'step_angle_degrees':math.degrees(theta)/divisions,
        'source_derived_interior_radii_cm':[short*(long/short)**(k/divisions) for k in range(1,divisions)],
        'minimum_angle_degrees':min(r['min_angle_degrees'] for r in rows),
        'minimum_edge_cm':min(min(r['edges_cm']) for r in rows),
        'per_triangle_minimum_angles_degrees':[r['min_angle_degrees'] for r in rows],
        'orientation_preserved_after_vector':unchanged,
        'noncollapse_existing_conditioner_gate':all(abs(s)*2 > 1e-12 for s in signs),
        'new_points_cm':values[1:-1], 'source_anchors_exact':True}


def selection(boundaries,seams,recipe,regular,vector,fan_math,check,envelope):
    """Select every source-derived transition; never insert an interior point."""
    target=regular['target_min_angle_degrees'];minedge=recipe['mesh']['min_edge_cm']
    limit=recipe['mesh'].get('quality_refinement',{}).get('max_added_vertices',4000)
    parameters={sid:set(seam['parameters']) for sid,seam in seams.items()}
    report={'status':'PREPARING_DERIVED_BOUNDARY_PARTITIONS','qualification':'NONE',
        'policy':'ALL_PREPARED_SOURCE_CORNERS_MINIMUM_FAN_N_GREATER_THAN_TWO',
        'target_angle_degrees':target,'min_edge_cm':minedge,'corners':[],
        'long_source_segments':[],'parameter_proposals':[],'source_relations_added':False,
        'initial_interior_points_added':0,'authored_physical_presence_claim':'NONE'}
    def refuse(reason):
        report['status']='REFUSED_INCOMPLETE_DERIVED_BOUNDARY_BATCH';report['refusal']=reason
        raise GradedBoundaryRefusal(reason,report)
    if (not math.isfinite(target) or not 0<target<=60 or not math.isfinite(minedge) or minedge<=0
        or type(limit) is not int or limit<0):refuse('INVALID_EXISTING_BOUNDARY_GRADING_LIMITS')
    long_segments={}
    for pid,boundary in sorted(boundaries.items()):
        polygon=boundary['polygon'];n=len(polygon)
        if n<3 or any(len(p)!=2 or any(not math.isfinite(x) for x in p) for p in polygon):refuse('NONFINITE_DERIVED_BOUNDARY')
        for corner in range(n):
            check()
            try:
                probe=fan_math(polygon,corner,1,vector,triangle_metrics)
            except (ArithmeticError,ValueError):refuse('UNREPRESENTABLE_SOURCE_CORNER_GRADING')
            maximum=math.floor(probe['interior_angle_degrees']/target);chosen=None
            for count in range(1,maximum+1):
                check()
                try:candidate=fan_math(polygon,corner,count,vector,triangle_metrics)
                except (ArithmeticError,ValueError):refuse('UNREPRESENTABLE_SOURCE_CORNER_GRADING')
                if (candidate['minimum_angle_degrees']>=target and candidate['minimum_edge_cm']>=minedge
                    and candidate['orientation_preserved_after_vector'] and candidate['noncollapse_existing_conditioner_gate']):
                    chosen=candidate;break
            row={'piece':pid,'corner':corner,'minimum_divisions':chosen['divisions'] if chosen else None,
                'eligible':bool(chosen and chosen['divisions']>2)};report['corners'].append(row)
            if chosen is None:refuse('SOURCE_CORNER_HAS_NO_ANALYTIC_DIVISION')
            if chosen['divisions']<=2:continue
            first_width=chosen['short_length_cm'];other=chosen['source_long_endpoint']
            if first_width<minedge:refuse('PROTECTED_SOURCE_SEGMENT_BELOW_EXISTING_MIN_EDGE')
            if other not in ((corner-1)%n,(corner+1)%n):refuse('SOURCE_LONG_SEGMENT_NOT_ADJACENT')
            key=(pid,corner,other);long_segments[key]=min(long_segments.get(key,math.inf),first_width)
    # A shared material interval is graded once. Partner constraints remain
    # exact source-parameter identities; no proximity/key-based fusion occurs.
    groups={}
    for (pid,start,end),first_width in sorted(long_segments.items()):
        check();polygon=boundaries[pid]['polygon'];length=distance(polygon[start],polygon[end]);owners=[]
        for sid,seam in sorted(seams.items()):
            check()
            for side in ('a','b'):
                if seam['piece_'+side]!=pid:continue
                for k,(a,b) in enumerate(zip(seam[side],seam[side][1:])):
                    check()
                    if (a,b)==(start,end):first,last=seam['parameters'][k:k+2]
                    elif (b,a)==(start,end):last,first=seam['parameters'][k:k+2]
                    else:continue
                    key=(sid,Fraction(first),Fraction(last));span=abs(Fraction(last)-Fraction(first))
                    short=(start-1)%len(polygon) if end==(start+1)%len(polygon) else (start+1)%len(polygon)
                    # Prefer the exact common interval of this same short edge.
                    short_span=None
                    for j,(u,v) in enumerate(zip(seam[side],seam[side][1:])):
                        check()
                        if {u,v}=={start,short}:
                            short_span=abs(Fraction(seam['parameters'][j+1])-Fraction(seam['parameters'][j]));break
                    short_interval_sourced=short_span is not None
                    if short_span is None:short_span=span*Fraction(first_width)/Fraction(length)
                    owner={'seam':sid,'side':side,'piece':pid,'source_prepared_segment':[start,end],
                        'partner_piece':seam['piece_b' if side=='a' else 'piece_a'],
                        'oriented_common_interval':[first,last],'short_common_span_fraction':str(short_span),
                        'short_length_cm':first_width,'long_length_cm':length,
                        'common_short_interval_sourced':short_interval_sourced}
                    owners.append(owner)
                    group=groups.setdefault(key,{'owners':[],'first_width_common':short_span})
                    group['owners'].append(owner);group['first_width_common']=min(group['first_width_common'],short_span)
        if not owners:refuse('SELECTED_SOURCE_SEGMENT_HAS_NO_EXISTING_SEAM_OWNER')
        if len(owners)!=1:refuse('AMBIGUOUS_SOURCE_SEAM_PARAMETER_OWNER')
    for (sid,first,last),group in sorted(groups.items()):
        check();span=abs(last-first);canonical=group['owners'][0];length=canonical['long_length_cm']
        first_width=float(group['first_width_common']/span)*length
        try:distances,partition=partition_distances(length,first_width,target,limit,check)
        except ValueError as error:refuse(str(error))
        row={'common_seam':sid,'oriented_common_interval':[float(first),float(last)],
            'piece':canonical['piece'],'source_prepared_segment':canonical['source_prepared_segment'],
            'shared_partner_constraints':group['owners'],'strictest_short_common_span_fraction':str(group['first_width_common']),
            **partition,'fractions':[v/length for v in distances[:-1]]}
        report['long_source_segments'].append(row)
        for fraction in row['fractions']:
            check();exact=first+Fraction(fraction)*(last-first);value=float(exact)
            if not math.isfinite(value) or not min(float(first),float(last))<value<max(float(first),float(last)):
                refuse('INVALID_DERIVED_COMMON_PARAMETER')
            if value not in parameters[sid]:envelope.reserve('fraction_requests',1,owner=sid)
            parameters[sid].add(value)
            report['parameter_proposals'].append({'piece':canonical['piece'],
                'source_prepared_segment':canonical['source_prepared_segment'],'fraction':fraction,
                'common_parameter':value,'common_parameter_fraction_before_transport':str(exact),
                'owners':[dict(owner,common_parameter=value) for owner in group['owners']],
                'source_parameter_identity_policy':'ONE_PARTITION_PER_DECLARED_ORIENTED_COMMON_INTERVAL'})
    report['status']='COMPLETE_DERIVED_BOUNDARY_PARAMETER_PROPOSALS_NOT_QUALIFIED'
    return {sid:sorted(values) for sid,values in parameters.items()},report


def synchronized_parameters(data,recipe,regular,baseline,oldseams,parameters,check,envelope):
    """Enforce the existing straight-strip growth bound after every source union.

    No interior point, CDT or topology is produced here. Every physical boundary
    allocation ever observed remains charged from the original baseline.
    """
    immutable=copy.deepcopy((data,recipe,regular,baseline,oldseams,parameters))
    seed={sid:tuple(values) for sid,values in sorted(parameters.items())}
    current={sid:set(values) for sid,values in seed.items()}
    baseline_keys={pid:set(row['keys']) for pid,row in baseline.items()}
    seen={pid:set() for pid in baseline};journal=[];snapshots=[]
    report={'status':'PREPARING_POST_UNION_GRADATION','qualification':'NONE',
        'native':'NOT_EXECUTED','source_relations_added':False,'interior_points_added':0,
        'reason':'POST_UNION_STRAIGHT_SOURCE_RATIO_EXCEEDS_EXISTING_PARTITION_BOUND',
        'growth_bound':1+1/math.tan(math.radians(regular['target_min_angle_degrees'])),
        'target_angle_degrees':regular['target_min_angle_degrees'],'min_edge_cm':recipe['mesh']['min_edge_cm'],
        'journal':journal,'iterations':snapshots,'attempted_fraction_requests':0,
        'charged_material_controls_by_piece':{pid:0 for pid in sorted(baseline)},
        'attempted_work_refunded':False,'physical_mesh_qualified':False}
    def fail(reason):
        report.update(status='REFUSED_INCOMPLETE_POST_UNION_GRADATION',refusal=reason)
        raise GradedBoundaryRefusal(reason,copy.deepcopy(report))
    def timed():
        try:check()
        except Exception as error:
            report.update(status='INCOMPLETE_POST_UNION_GRADATION',refusal='CALLER_STOP_OR_DEADLINE',
                caller_error={'type':type(error).__name__,'message':str(error)})
            raise GradedBoundaryRefusal('CALLER_STOP_OR_DEADLINE',copy.deepcopy(report)) from error
    if set(current)!=set(oldseams):fail('SOURCE_RELATION_INVENTORY_CHANGED')
    if any(any(type(t)not in(int,float) or isinstance(t,bool) or not math.isfinite(t) or not 0<=t<=1
        for t in values) or sorted(values)!=list(values) or len(set(values))!=len(values) for values in seed.values()):
        fail('INVALID_EXACT_COMMON_PARAMETERS')
    derived=copy.deepcopy(recipe);derived['mesh']['spacing_cm']=regular['min_spacing_cm']
    derived['mesh']['max_vertices']=min(regular['max_vertices'],recipe['mesh']['max_vertices'])
    cap=recipe['mesh'].get('quality_refinement',{}).get('max_added_vertices',4000)
    iteration=0
    while True:
        timed();requested={sid:sorted(values) for sid,values in sorted(current.items())}
        try:parts,seams,_=_sample(data,derived,regular,requested,baseline,envelope,timed)
        except Exception as error:
            report['existing_API_error']={'type':type(error).__name__,'message':str(error)}
            if getattr(error,'reason',None) in ('BUDGET_EXHAUSTED','DEADLINE_EXHAUSTED','STOP_REQUESTED'):
                report.update(status='INCOMPLETE_POST_UNION_GRADATION',refusal=error.reason)
                raise GradedBoundaryRefusal(error.reason,copy.deepcopy(report)) from error
            fail('SOURCE_PROPAGATION_REFUSED')
        # Charge the observed allocation before validation or any future CDT.
        for pid,part in sorted(parts.items()):
            if pid not in seen:fail('SOURCE_PIECE_INVENTORY_CHANGED')
            seen[pid].update(k for k in part['keys'] if k not in baseline_keys[pid])
            report['charged_material_controls_by_piece'][pid]=len(seen[pid])
        timed()
        if set(parts)!=set(baseline) or set(seams)!=set(oldseams):fail('SOURCE_PIECE_OR_SEAM_INVENTORY_CHANGED')
        for pid,part in sorted(parts.items()):
            timed();old=baseline[pid];lookup={key:i for i,key in enumerate(part['keys'])}
            if len(lookup)!=len(part['keys']):fail('SOURCE_PARAMETER_KEY_ALIAS')
            if any(k not in lookup or part['polygon'][lookup[k]]!=old['polygon'][i] for i,k in enumerate(old['keys'])):
                fail('OLD_PREPARED_COORDINATE_OR_IDENTITY_CHANGED')
            if any(part[k]!=old[k] for k in ('source','source_sha256','perimeter','flip')):
                fail('AUTHORED_SOURCE_PROPERTY_CHANGED')
            if sum(len(values) for values in seen.values())>cap:fail('COMPONENT_DERIVED_BOUNDARY_INITIAL_INSERTION_BUDGET')
            if len(part['polygon'])>derived['mesh']['max_vertices']:fail('DERIVED_BOUNDARY_POINT_BUDGET')
            if min(distance(a,b) for a,b in zip(part['polygon'],part['polygon'][1:]+part['polygon'][:1]))<recipe['mesh']['min_edge_cm']:
                fail('DERIVED_SOURCE_EDGE_BELOW_EXISTING_MINIMUM')
        if sum(len(part['polygon']) for part in parts.values())>regular['max_vertices']:fail('GLOBAL_SOURCE_BOUNDARY_BUDGET')
        for sid,seam in sorted(seams.items()):
            timed();old=oldseams[sid]
            if any(seam[k]!=old[k] for k in ('piece_a','piece_b','kind')):fail('SOURCE_SEAM_RELATION_CHANGED')
            if not set(requested[sid]).issubset(seam['parameters']):fail('EXACT_REQUESTED_PARAMETER_NOT_RETAINED')
            if not set(old['parameters']).issubset(seam['parameters']):fail('OLD_COMMON_PARAMETER_LOST')
            current[sid].update(seam['parameters'])
        groups={};violations=[]
        for pid,part in sorted(parts.items()):
            polygon=part['polygon'];n=len(polygon)
            for corner in range(n):
                timed();previous,center,following=polygon[corner-1],polygon[corner],polygon[(corner+1)%n]
                u=[Fraction(x)-Fraction(y) for x,y in zip(previous,center)]
                v=[Fraction(x)-Fraction(y) for x,y in zip(following,center)]
                # Exact supplied source geometry, never an epsilon straightness test.
                if u[0]*v[1]-u[1]*v[0]!=0 or sum(a*b for a,b in zip(u,v))>=0:continue
                lengths=[distance(previous,center),distance(center,following)]
                short=min(lengths);long=max(lengths)
                if short<=0:fail('COLLAPSED_SOURCE_SEGMENT')
                if long/short<=report['growth_bound']:continue
                end=(corner+1)%n if lengths[0]<lengths[1] else (corner-1)%n
                short_end=(corner-1)%n if end==(corner+1)%n else (corner+1)%n
                owners=[]
                for sid,seam in sorted(seams.items()):
                    for side in ('a','b'):
                        if seam['piece_'+side]!=pid:continue
                        for k,(a,b) in enumerate(zip(seam[side],seam[side][1:])):
                            if (a,b)==(corner,end):first,last=seam['parameters'][k:k+2]
                            elif (b,a)==(corner,end):last,first=seam['parameters'][k:k+2]
                            else:continue
                            first,last=Fraction(first),Fraction(last);span=abs(last-first)
                            short_span=None
                            for j,(a,b) in enumerate(zip(seam[side],seam[side][1:])):
                                if {a,b}=={corner,short_end}:
                                    short_span=abs(Fraction(seam['parameters'][j+1])-Fraction(seam['parameters'][j]));break
                            if short_span is None:short_span=span*Fraction(short)/Fraction(long)
                            other='b' if side=='a' else 'a'
                            if seam['piece_'+other]not in parts:fail('MISSING_DECLARED_SOURCE_PARTNER')
                            owner={'piece':pid,'side':side,'seam':sid,'partner_piece':seam['piece_'+other],
                                'source_boundary_ids':[corner,end],'source_short_boundary_ids':[corner,short_end],
                                'source_keys':[part['keys'][corner],part['keys'][end]],
                                'source_sha256':part['source_sha256'],'source_provenance':[
                                    part['sample_provenance'][i] for i in (corner,end)],
                                'oriented_common_interval':[float(first),float(last)],
                                'short_common_span_fraction':str(short_span),'short_length_cm':short,
                                'long_length_cm':long,'ratio_before':long/short}
                            owners.append(owner);group=groups.setdefault((sid,first,last),{'owners':[],'short':short_span})
                            group['owners'].append(owner);group['short']=min(group['short'],short_span)
                if len(owners)!=1:fail('MISSING_OR_AMBIGUOUS_DECLARED_SOURCE_OWNER')
                violations.append({'piece':pid,'corner':corner,'ratio':long/short,'owners':owners})
        snapshot={'iteration':iteration,'violations':violations,'piece_counts':{p:len(v['polygon']) for p,v in sorted(parts.items())},
            'charged_material_controls_by_piece':copy.deepcopy(report['charged_material_controls_by_piece'])}
        snapshots.append(snapshot)
        if not groups:
            timed()
            if immutable!=(data,recipe,regular,baseline,oldseams,parameters):fail('SOURCE_INPUT_MUTATION')
            report.update(status='FIXPOINT_SOURCE_GRADATION_ONLY',source_inputs_immutable=True,
                total_initial_charged_boundary_insertions=sum(report['charged_material_controls_by_piece'].values()),
                iterations_executed=iteration+1,old_seed_parameters_preserved=True,
                exact_source_binding_checks='FINAL_V1_PREPARE_VALIDATION_REQUIRED',
                global_quality_claim='NONE',physical_presence_claim='NONE')
            result={sid:sorted(values) for sid,values in sorted(current.items())}
            timed()
            return result,report
        added=0
        for (sid,first,last),group in sorted(groups.items()):
            timed();canonical=group['owners'][0];length=canonical['long_length_cm'];span=abs(last-first)
            first_width=float(group['short']/span)*length
            try:distances,partition=partition_distances(length,first_width,regular['target_min_angle_degrees'],cap,timed)
            except ValueError as error:fail(str(error))
            for position in distances[:-1]:
                timed();exact=first+Fraction(position/length)*(last-first);value=float(exact)
                if not math.isfinite(value) or not min(float(first),float(last))<value<max(float(first),float(last)):
                    fail('INVALID_DERIVED_COMMON_PARAMETER')
                if value in current[sid]:continue
                envelope.reserve('fraction_requests',1,owner=sid);current[sid].add(value);added+=1;report['attempted_fraction_requests']+=1
                journal.append({'iteration':iteration,'common_seam':sid,'common_parameter':value,
                    'common_parameter_fraction_before_transport':str(exact),
                    'reason':report['reason'],'owners':copy.deepcopy(group['owners']),
                    'partition':partition,'source_parameter_identity_policy':'EXACT_SOURCE_INTERVAL_NO_PROXIMITY',
                    'debit_policy':'ALLOCATION_CHARGED_BEFORE_ANY_CDT_NOT_REFUNDED'})
        if added==0:fail('POST_UNION_GRADATION_STAGNATION')
        iteration+=1


def _public_boundaries(parts):
    fields = ('source','perimeter','keys','polygon','flip','source_sha256',
              'sample_provenance','edges','regular_sampling_report')
    return {pid:{key:part[key] for key in fields if key in part} for pid,part in sorted(parts.items())}


def _grade_shared_boundaries(data, derived_recipe, regular_mesh,
                            baseline_boundaries, baseline_seams, *, transport_2d, envelope):
    """Prepare source-bound partitions; the caller performs final notch rebinding.

    ``envelope`` is the already-open caller protocol: check(phase),
    reserve(kind,amount,owner=None), observe_material_controls(component_id,
    keys_by_piece), snapshot(). It survives this call and later meshing. The
    caller owns all caps and their component scope. No default clock or ledger
    is created here. ``transport_2d`` is the caller's native numerical transport,
    not a source edit, arbitrary coordinate placement, or physical pin.
    """
    for name in ('check','reserve','observe_material_controls','snapshot'):
        if not callable(getattr(envelope,name,None)):
            raise GradedBoundaryRefusal('MISSING_SHARED_ENVELOPE_PROTOCOL')
    envelope.check('before_capture')
    check = lambda: _tick(envelope,'boundary_gradation')
    originals = [data,derived_recipe,regular_mesh,baseline_boundaries,baseline_seams]
    captured, input_hash = _capture(originals,envelope)
    source, recipe, regular, baseline, oldseams = captured
    mesh = recipe['mesh']
    limit = mesh.get('quality_refinement',{}).get('max_added_vertices',4000)
    if (type(limit) is not int or limit<0 or type(regular['max_vertices']) is not int
        or type(mesh['max_vertices']) is not int or min(regular['max_vertices'],mesh['max_vertices'])<3
        or type(regular['min_spacing_cm']) not in (int,float) or regular['min_spacing_cm']<=0
        or type(regular['target_min_angle_degrees']) not in (int,float)):
        raise GradedBoundaryRefusal('INVALID_EXISTING_BOUNDARY_GRADING_LIMITS')
    if not callable(transport_2d):
        raise GradedBoundaryRefusal('MISSING_COORDINATE_TRANSPORT')
    if sum(len(p['polygon']) for p in baseline.values())>min(regular['max_vertices'],mesh['max_vertices']):
        raise GradedBoundaryRefusal('GLOBAL_BASELINE_POINT_BUDGET')
    _source_identity(source,baseline,oldseams,recipe,check)
    _transport_aliases(baseline,transport_2d,check)
    def vector(point):
        return _transport_point(point,transport_2d,check)
    def fan_math(polygon,corner,count,transport,metrics):
        check()
        envelope.reserve('work_steps', max(1,count))
        result = _fan_math_candidate(polygon,corner,count,transport,metrics,signed_area)
        check()
        return result
    parameters, report = selection(baseline,oldseams,recipe,regular,vector,fan_math,check,envelope)
    parameters, cascade = synchronized_parameters(source,recipe,regular,baseline,oldseams,
        parameters,check,envelope)
    report['post_union_cascade'] = cascade
    derived = copy.deepcopy(recipe)
    derived['mesh']['spacing_cm'] = regular['min_spacing_cm']
    derived['mesh']['max_vertices'] = min(regular['max_vertices'],mesh['max_vertices'])
    parts,seams,seam_reports = _sample(source,derived,regular,parameters,baseline,envelope,check)
    _transport_aliases(parts,transport_2d,check)
    piece_reports = {}
    for pid, part in sorted(parts.items()):
        check(); old=baseline[pid];lookup={key:i for i,key in enumerate(part['keys'])}
        if any(key not in lookup or part['polygon'][lookup[key]]!=old['polygon'][i] for i,key in enumerate(old['keys'])):
            raise GradedBoundaryRefusal('OLD_PREPARED_COORDINATE_OR_IDENTITY_CHANGED')
        piece_reports[pid] = {'old_boundary_vertices':len(old['polygon']),
            'new_boundary_vertices':len(part['polygon']),
            'initial_charged_boundary_insertions':cascade['charged_material_controls_by_piece'][pid],
            'old_to_new_boundary_vertex':[lookup[key] for key in old['keys']],
            'source_sha256':part['source_sha256'],'all_old_prepared_coordinates_exact':True,
            'authored_physical_presence_claim':'NONE'}
    check()
    report.update(version=VERSION,status='BUILT_SOURCE_BOUNDARY_GRADATION_ONLY',
        qualification='NONE',native='NOT_EXECUTED',component_id=source['component_id'],
        source_sha256=digest(source),recipe_sha256=digest(recipe),regular_mesh_sha256=digest(regular),
        input_binding_sha256=input_hash,source_inputs_immutable=True,
        full_piece_count=len(parts),full_seam_count=len(seams),pieces=piece_reports,
        boundary_count_before=sum(len(p['polygon']) for p in baseline.values()),
        boundary_count_after=sum(len(p['polygon']) for p in parts.values()),
        total_initial_charged_boundary_insertions=sum(cascade['charged_material_controls_by_piece'].values()),
        insertion_budget_scope='COMPONENT_CONTROLS_PLUS_LATER_INTERIOR_INSERTIONS',
        max_component_added_vertices=limit,
        source_notch_rebind='CALLER_REQUIRED_ON_NEW_BOUNDARIES',
        global_quality_claim='NONE',authored_physical_presence_claim='NONE',seam_reports=seam_reports)
    # The envelope is caller-owned. This snapshot is explicitly prior to output
    # reservations; it must not be presented as terminal accounting of a run.
    report['envelope_before_output'] = envelope.snapshot()
    check()
    output = {'boundaries':_public_boundaries(parts),'seams':seams,'report':report}
    report['content_sha256'] = digest(output)
    check()
    nodes, size = _shape(output,check)
    envelope.reserve('output_nodes',nodes)
    envelope.reserve('output_bytes',size)
    envelope.check('before_output_copy')
    result = copy.deepcopy(output)
    envelope.check('after_output_copy')
    if _preservation_hash(originals,check) != input_hash:
        raise GradedBoundaryRefusal('SOURCE_INPUT_MUTATION')
    envelope.check('terminal_after_preservation_hash')
    return result['boundaries'],result['seams'],result['report']


def grade_shared_boundaries(data, derived_recipe, regular_mesh,
                           baseline_boundaries, baseline_seams, *, transport_2d, envelope):
    """Prepare a full sourced batch under the caller's shared work envelope.

    Input schema failures are localized refusals. Existing source contracts,
    deadline/stop failures and monotone debits retain their original meaning.
    This function does not declare native or physical quality.
    """
    try:
        return _grade_shared_boundaries(data,derived_recipe,regular_mesh,
            baseline_boundaries,baseline_seams,transport_2d=transport_2d,envelope=envelope)
    except StudioError:
        raise
    except (KeyError,IndexError,TypeError,ValueError,OverflowError,RecursionError) as error:
        raise GradedBoundaryRefusal('SOURCE_BOUNDARY_CONTRACT_REFUSED',{
            'status':'REFUSED_SOURCE_BOUNDARY_PREPARATION','refusal':'SOURCE_BOUNDARY_CONTRACT_REFUSED',
            'error':{'type':type(error).__name__,'message':str(error)},
            'qualification':'NONE','native':'NOT_EXECUTED'}) from error
