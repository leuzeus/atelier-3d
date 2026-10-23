"""Observe supplied affine fields along exact UV paths; never optimize/admit."""
import hashlib
import math
import time
from fractions import Fraction as F
from pathlib import Path

from . import material_sample_carrier as uv
from . import material_surface_field as field
from . import material_surface_constraints as constraints
from .core import StudioError


DISCRIMINANT = 'MATERIAL_SURFACE_TRACES_V1'


def _refuse(reason, detail):
    field._refuse(reason, 'traces: '+detail)


def _cross(a, b, p, budget):
    x = budget.q(b[0]-a[0]); y = budget.q(b[1]-a[1])
    u = budget.q(p[0]-a[0]); v = budget.q(p[1]-a[1])
    return budget.q(budget.q(x*v)-budget.q(y*u))


def _interval(a, b, triangle, budget):
    """Closed rational t interval of a segment in one closed triangle."""
    if _cross(*triangle, budget) < 0: triangle = list(reversed(triangle))
    lo, hi = F(0), F(1)
    for p, q in zip(triangle, triangle[1:]+triangle[:1]):
        budget.check('trace_clipping')
        c = _cross(p, q, a, budget)
        slope = budget.q(_cross(p, q, b, budget)-c)
        if not slope:
            if c < 0: return None
            continue
        t = budget.q(-c/slope)
        if slope > 0: lo = max(lo, t)
        else: hi = min(hi, t)
        if lo > hi: return None
    return lo, hi


def _point(a, b, t, budget):
    return tuple(budget.q(x+budget.q(t*budget.q(y-x))) for x, y in zip(a, b))


def _outward(value, upper, budget):
    budget.check('trace_length_conversion')
    try: result = float(value)
    except (OverflowError, ValueError): _refuse('INVALID_LENGTH', 'length overflows binary64')
    if not math.isfinite(result): _refuse('INVALID_LENGTH', 'finite length interval required')
    if (F(result) < value if upper else F(result) > value):
        result = math.nextafter(result, math.inf if upper else -math.inf)
    if not math.isfinite(result): _refuse('INVALID_LENGTH', 'finite outward bound required')
    budget.q(F(result))
    return result


def _norm(a, b, budget):
    """Binary64 brackets are certified by rational squared comparisons."""
    q = F(0)
    for x, y in zip(a, b):
        d = budget.q(y-x); q = budget.q(q+budget.q(d*d))
    if not q:
        return {'squared_norm_exact_cm2': q, 'lower_exact_cm': F(0),
                'upper_exact_cm': F(0), 'lower_cm': 0., 'upper_cm': 0.}
    # Scale before float conversion: a finite norm can have an overflowing q.
    exponent = 2*((q.numerator.bit_length()-q.denominator.bit_length())//2)
    scale = budget.q(F(2)**(-exponent))
    scaled = budget.q(q*scale)
    budget.check('trace_sqrt')
    try: estimate = math.ldexp(math.sqrt(float(scaled)), exponent//2)
    except (OverflowError, ValueError): _refuse('INVALID_LENGTH', 'finite norm bracket unavailable')
    budget.check('trace_sqrt_after')
    if not math.isfinite(estimate): _refuse('INVALID_LENGTH', 'finite norm bracket unavailable')
    lo = max(0., math.nextafter(estimate, -math.inf))
    hi = math.nextafter(estimate, math.inf)
    while budget.q(F(lo)*F(lo)) > q:
        budget.check('trace_sqrt_refinement'); lo = max(0., math.nextafter(lo, -math.inf))
    while math.isfinite(hi) and budget.q(F(hi)*F(hi)) < q:
        budget.check('trace_sqrt_refinement'); hi = math.nextafter(hi, math.inf)
    if not math.isfinite(hi): _refuse('INVALID_LENGTH', 'finite norm bracket unavailable')
    return {'squared_norm_exact_cm2': q, 'lower_exact_cm': budget.q(F(lo)),
            'upper_exact_cm': budget.q(F(hi)), 'lower_cm': lo, 'upper_cm': hi}


def _sum_lengths(records, budget):
    lo, hi = F(0), F(0)
    for row in records:
        lo = budget.q(lo+row['lower_exact_cm']); hi = budget.q(hi+row['upper_exact_cm'])
    return {'lower_exact_cm': lo, 'upper_exact_cm': hi,
            'lower_cm': _outward(lo, False, budget), 'upper_cm': _outward(hi, True, budget)}


def _band(raw, quantity, measured, budget):
    if raw is None: return {'status': 'MEASURED_NO_ACCEPTANCE_BOUND', 'quantity': quantity}
    uv._fields(raw, ('quantity', 'lower_cm', 'upper_cm'))
    if raw['quantity'] != quantity: _refuse('INVALID_LENGTH_BAND', 'band is for a different measured quantity')
    values = field._positions([[raw['lower_cm'], raw['upper_cm'], 0]], 1, budget, 'length band')[0]
    lo, hi = values[:2]
    if not 0 <= lo <= hi: _refuse('INVALID_LENGTH_BAND', 'nonnegative ordered length band required')
    a, b = measured['lower_exact_cm'], measured['upper_exact_cm']
    status = 'WITHIN_DECLARED_BAND' if lo <= a and b <= hi else (
        'OUTSIDE_DECLARED_BAND' if b < lo or a > hi else 'INDETERMINATE_BOUND_OVERLAP')
    return {'status': status, 'quantity': quantity, 'declared_lower_exact_cm': lo,
            'declared_upper_exact_cm': hi, 'qualification': 'NONE', 'strength': 'OBSERVATION_ONLY'}


def _evaluate(point, state, budget):
    budget.take('queries'); budget.take('patch_vertex_checks', 3)
    source = uv._support(point, state['source_mesh'], budget)
    current, carrier = field._interpolate(point, state['carrier_mesh'], state['current'], budget)
    fresh, reference = field._interpolate(point, state['reference_mesh'], state['fresh'], budget)
    result = {'exact_uv_cm': point, 'source_support': source, 'carrier_support': carrier,
              'reference_support': reference, 'candidate': field._cast(current, budget),
              'fresh_reference': field._cast(fresh, budget), 'previous': None}
    if state['previous'] is not None:
        previous, _ = field._interpolate(point, state['carrier_mesh'], state['previous'], budget)
        result['previous'] = field._cast(previous, budget)
    return result


def _vertices(raw, state, budget):
    if type(raw) is not list or len(raw) < 2: _refuse('INVALID_TRACE', 'at least two explicit path vertices required')
    budget.available('queries', len(raw))
    samples = {r['id']: r for r in state['material_uv']['samples']}
    identities, records = set(), []
    for vertex in raw:
        budget.check('trace_vertex_binding')
        uv._fields(vertex, ('id',), ('uv_cm', 'sample_id', 'source_vertex_id', 'fraction', 'target_cm'))
        identity = uv._identity(vertex['id'])
        if identity in identities: _refuse('IDENTITY_COLLISION', 'path vertex identities collide')
        identities.add(identity)
        if len(set(vertex)&{'uv_cm', 'sample_id', 'source_vertex_id'}) != 1:
            _refuse('INVALID_TRACE', 'exactly one explicit material vertex binding required')
        if 'uv_cm' in vertex:
            if type(vertex['uv_cm']) is not list or len(vertex['uv_cm']) != 2:
                _refuse('INVALID_TRACE', 'explicit 2D material coordinates required')
            point = tuple(budget.q(uv._number(x, budget)) for x in vertex['uv_cm'])
        elif 'sample_id' in vertex:
            if type(vertex['sample_id']) is not str or vertex['sample_id'] not in samples:
                _refuse('INVALID_SAMPLE', 'path names an absent source sample')
            point = tuple(samples[vertex['sample_id']]['exact_uv_cm'])
        else:
            lookup = state['source_mesh']['vertex_lookup']
            if type(vertex['source_vertex_id']) is not str or vertex['source_vertex_id'] not in lookup:
                _refuse('INVALID_SOURCE_VERTEX', 'path names an absent source vertex')
            point = state['source_mesh']['points'][lookup[vertex['source_vertex_id']]]
        observation = _evaluate(point, state, budget)
        row = {'id': identity, 'binding': vertex, **observation}
        if 'fraction' in vertex: row['declared_fraction_exact'] = budget.q(uv._fraction(vertex['fraction'], budget))
        if 'target_cm' in vertex:
            target = field._positions([vertex['target_cm']], 1, budget, 'numerical target')[0]
            exact = observation['candidate']['coordinates_exact_cm']
            ieee = observation['candidate']['coordinates_cm']
            row['target_observation'] = {'strength': 'SOFT_OBSERVATION', 'target_exact_cm': target,
                'residual_exact_cm': [budget.q(a-b) for a, b in zip(exact, target)],
                'residual_binary64_cm': [budget.q(F(a)-b) for a, b in zip(ieee, target)]}
        records.append(row)
    return records


def _edge(raw, vertices, state, budget):
    if 'edge_id' not in raw: return
    uv._identity(raw['edge_id'])
    reverse = raw.get('orientation', 'forward') == 'reverse'
    mesh = state['source_mesh']; chain = mesh['raw'].get('edges', {}).get(raw['edge_id'])
    if chain is None: _refuse('INVALID_BOUNDARY', 'explicit source edge is absent')
    walked = [uv._walk(row['exact_uv_cm'], mesh, raw['edge_id'], budget, reverse)[0] for row in vertices]
    for i, (a, b) in enumerate(zip(walked, walked[1:])):
        if a >= b: _refuse('INVALID_BOUNDARY', 'path does not follow the declared source edge order')
        ordered = list(reversed(chain)) if reverse else chain
        p, q = vertices[i]['exact_uv_cm'], vertices[i+1]['exact_uv_cm']
        for ordinal in range(math.floor(a)+1, math.ceil(b)):
            budget.check('trace_source_edge_corners')
            corner = mesh['points'][mesh['vertex_lookup'][ordered[ordinal]]]
            if _cross(p, q, corner, budget) != 0:
                _refuse('MISSING_SOURCE_CORNER', 'path skips a geometric corner of its source edge')


def _segments(vertices, state, budget):
    meshes = {k: state[k+'_mesh'] for k in ('source', 'reference', 'carrier')}
    pieces, segments = [], []
    for ordinal, (va, vb) in enumerate(zip(vertices, vertices[1:])):
        a, b = va['exact_uv_cm'], vb['exact_uv_cm']; cuts = {F(0), F(1)}; intervals = {}
        budget.available('pair_checks', sum(len(m['triangles']) for m in meshes.values()))
        for kind, mesh in meshes.items():
            intervals[kind] = []
            for index, triangle in enumerate(mesh['triangles']):
                budget.take('pair_checks'); interval = _interval(a, b, triangle, budget)
                if interval is None: continue
                budget.take('intersection_patches'); cuts.update(interval)
                intervals[kind].append((interval, index))
        cuts = sorted(cuts)
        budget.available('queries', len(cuts)+len(cuts)-1)
        events = [{'t': t, 'path_vertex_ids': ([va['id']] if t == 0 else [vb['id']] if t == 1 else []),
                   **_evaluate(_point(a, b, t, budget), state, budget)} for t in cuts]
        chunk_records = []
        for j, (lo, hi) in enumerate(zip(cuts, cuts[1:])):
            budget.check('trace_interval_coverage')
            faces = {}
            for kind, mesh in meshes.items():
                covering = [index for (start, end), index in intervals[kind] if start <= lo and hi <= end]
                if not covering: _refuse('TRACE_DOMAIN_COVERAGE', 'positive path interval is outside '+kind)
                faces[kind] = sorted(mesh['raw']['face_ids'][index] for index in covering)
            # Shared-edge multiplicity is legal only for the existing identical sparse support rule.
            midpoint = _point(a, b, budget.q((lo+hi)/2), budget)
            budget.take('queries'); budget.take('patch_vertex_checks', 3)
            supports = {kind: uv._support(midpoint, mesh, budget) for kind, mesh in meshes.items()}
            lengths = {}
            for key in ('candidate', 'fresh_reference', 'previous'):
                x, y = events[j][key], events[j+1][key]
                if x is not None: lengths[key] = _norm(x['coordinates_exact_cm'], y['coordinates_exact_cm'], budget)
            chunk = {'input_segment_index': ordinal, 't_interval': [lo, hi],
                'start_event_index': j, 'end_event_index': j+1, 'covering_face_ids': faces,
                'midpoint_supports': supports, 'lengths': lengths}
            chunk_records.append(chunk); pieces.append(chunk)
        segments.append({'input_segment_index': ordinal, 'source_path_vertex_ids': [va['id'], vb['id']],
                         'coverage_exact_t_interval': [F(0), F(1)], 'events': events, 'chunks': chunk_records})
    return segments, pieces


def _trace(raw, states, identities, budget):
    uv._fields(raw, ('id', 'domain_id', 'source_sha256', 'vertices'),
               ('edge_id', 'orientation', 'length_band', 'historical_observation',
                'partner_trace_id', 'require_continuous_partner'))
    identity = uv._identity(raw['id']); domain = uv._identity(raw['domain_id'])
    if domain not in states: _refuse('MISSING_DOMAIN', 'trace needs a supplied revalidated field')
    if raw['source_sha256'] != identities[domain]['source']:
        _refuse('SOURCE_IDENTITY', 'trace source hash differs from its supplied domain')
    if raw.get('orientation', 'forward') not in ('forward', 'reverse'):
        _refuse('INVALID_BOUNDARY', 'explicit forward/reverse orientation required')
    if type(raw.get('require_continuous_partner', False)) is not bool:
        _refuse('INVALID_TRACE', 'continuous partner requirement must be a boolean')
    if raw.get('require_continuous_partner', False):
        _refuse('MISSING_TRANSPORT', 'this observer does not invent continuous partner transport')
    if 'partner_trace_id' in raw: uv._identity(raw['partner_trace_id'])
    state = states[domain]; vertices = _vertices(raw['vertices'], state, budget)
    _edge(raw, vertices, state, budget)
    segments, pieces = _segments(vertices, state, budget)
    totals, chords = {}, {}
    for key in ('candidate', 'fresh_reference', 'previous'):
        if vertices[0][key] is None: continue
        totals[key] = _sum_lengths([p['lengths'][key] for p in pieces], budget)
        chords[key] = _norm(vertices[0][key]['coordinates_exact_cm'], vertices[-1][key]['coordinates_exact_cm'], budget)
    return {'id': identity, 'domain_id': domain, 'declaration': raw, 'vertices': vertices,
        'segments': segments, 'coverage': 'COMPLETE_EXACT_PROVIDED_UV_PATH',
        'continuous_lengths': totals, 'endpoint_chords': chords,
        'length_observation': _band(raw.get('length_band'), 'candidate_continuous_trace_length', totals['candidate'], budget),
        'historical_bounds_applied_to_continuous_length': False,
        'partner_observation': 'NOT_ASSESSED_NO_CONTINUOUS_TRANSPORT' if 'partner_trace_id' in raw else 'NOT_REQUESTED'}


def _bars(raw, traces, budget):
    if type(raw) is not list: _refuse('INVALID_BAR', 'bars must be an explicit list')
    result = []; identities = set(); declarations = {}
    for bar in raw:
        uv._fields(bar, ('id', 'trace_id', 'start_vertex_id', 'end_vertex_id'),
                   ('source_length_cm', 'length_band', 'historical_observation'))
        identity = uv._identity(bar['id'])
        if identity in identities: _refuse('IDENTITY_COLLISION', 'bar identities collide')
        identities.add(identity); declarations[identity] = bar
    for identity, bar in sorted(declarations.items()):
        if type(bar['trace_id']) is not str or bar['trace_id'] not in traces:
            _refuse('INVALID_BAR', 'bar needs an observed trace')
        trace = traces[bar['trace_id']]; lookup = {row['id']: i for i, row in enumerate(trace['vertices'])}
        for key in ('start_vertex_id', 'end_vertex_id'):
            if type(bar[key]) is not str or bar[key] not in lookup: _refuse('INVALID_BAR', 'bar endpoint binding is absent')
        a, b = lookup[bar['start_vertex_id']], lookup[bar['end_vertex_id']]
        if a >= b: _refuse('INVALID_BAR', 'bar needs a nonzero ordered source interval')
        chords, lengths = {}, {}
        pieces = [p for seg in trace['segments'][a:b] for p in seg['chunks']]
        for key in trace['continuous_lengths']:
            chords[key] = _norm(trace['vertices'][a][key]['coordinates_exact_cm'],
                                trace['vertices'][b][key]['coordinates_exact_cm'], budget)
            lengths[key] = _sum_lengths([p['lengths'][key] for p in pieces], budget)
        row = {'id': identity, 'declaration': bar, 'endpoint_chords': chords, 'continuous_lengths': lengths,
               'length_observation': _band(bar.get('length_band'), 'candidate_chord_length', chords['candidate'], budget),
               'historical_bounds_applied_to_continuous_length': False}
        if 'source_length_cm' in bar:
            source = field._positions([[bar['source_length_cm'], 0, 0]], 1, budget, 'bar source length')[0][0]
            if source <= 0: _refuse('INVALID_BAR', 'positive source length required')
            row['source_chord_residual_interval_cm'] = [budget.q(chords['candidate'][k]-source)
                                                       for k in ('lower_exact_cm', 'upper_exact_cm')]
        result.append(row)
    return result


def observe_material_surface_traces(fields, traces, bars=None, *, context,
        budgets=None, deadline=None, clock=time.monotonic):
    """Revalidate once/domain, observe all supplied paths under one ledger."""
    data = {'fields': fields, 'traces': traces, 'bars': [] if bars is None else bars, 'context': context}
    originals = [data, budgets, deadline]
    budget = None
    try:
        copied, before, budget = constraints._capture(originals, budgets, deadline, clock); data = copied[0]
        if type(data['fields']) is not dict or not data['fields'] or type(data['context']) is not dict:
            _refuse('INVALID_CONTRACT', 'fields and declared provenance context must be objects')
        context_keys = ('source_package_sha256', 'body_sha256', 'pose_sha256', 'recipe_sha256', 'generator_sha256')
        uv._fields(data['context'], context_keys, ('metadata',))
        for value in (data['context'][key] for key in context_keys):
            if value is not None and (type(value) is not str or len(value) != 64 or
                                      any(c not in '0123456789abcdef' for c in value)):
                _refuse('INVALID_CONTEXT', 'provenance must be a declared SHA256 or explicit null')
        budget.take('domains', len(data['fields'])); states, identities = {}, {}
        for domain, compiled in sorted(data['fields'].items()):
            budget.check('trace_domain_revalidation'); uv._identity(domain)
            state = field._from_compiled(compiled, budget)
            if domain != state['data']['source']['id']: _refuse('DOMAIN_IDENTITY', 'no alias of source domain')
            states[domain] = state; identities[domain] = field._hashes(state, budget)
        if type(data['traces']) is not list or not data['traces']:
            _refuse('INVALID_TRACE', 'explicit nonempty traces required')
        # Reject duplicate IDs before work; order is canonical, not a geometric modification.
        lookup = {}
        for raw in data['traces']:
            if type(raw) is not dict: _refuse('INVALID_TRACE', 'trace must be an object')
            identity = uv._identity(raw.get('id'))
            if identity in lookup: _refuse('IDENTITY_COLLISION', 'trace identities collide')
            lookup[identity] = raw
        observed = {}
        for identity, raw in sorted(lookup.items()):
            if 'partner_trace_id' in raw and (type(raw['partner_trace_id']) is not str or raw['partner_trace_id'] not in lookup):
                _refuse('MISSING_PARTNER', 'declared partner trace is absent')
            observed[identity] = _trace(raw, states, identities, budget)
        bars = _bars(data['bars'], observed, budget)
        result = {'discriminant': DISCRIMINANT, 'version': 1, 'status': 'OBSERVED_TEST_ONLY',
            'purpose': 'TEST_ONLY', 'qualification': 'NONE', 'physical_mesh': False, 'is_installable': False,
            'context': data['context'], 'context_validation': 'CALLER_DECLARED_IDENTITIES_ONLY',
            'undeclared_context_identities': [key for key in context_keys if data['context'][key] is None],
            'domain_identities': identities, 'domain_revalidation_count': {d: 1 for d in states},
            'traces': list(observed.values()), 'bars': bars, 'shared_work_ledger': True,
            'cross_api_budget_qualification': 'NOT_QUALIFIED_WITHOUT_PROGRAM_EXECUTOR',
            'metric': 'NOT_ASSESSED', 'constraint_feasibility': 'NOT_ASSESSED',
            'physical_pins_added': [], 'hard_rows_added': [], 'native': 'NOT_EXECUTED',
            'contacts': 'NOT_ASSESSED', 'cloth': 'NOT_EXECUTED', 'fitting': 'NOT_QUALIFIED'}
        hashes = {'domains': identities, 'context': field._hash(data['context'], budget, 'trace_context'),
            'paths': field._hash(data['traces'], budget, 'trace_paths'),
            'bars': field._hash(data['bars'], budget, 'trace_bars'),
            'observer_code': hashlib.sha256(Path(__file__).read_bytes()).hexdigest(),
            'constraints_code': hashlib.sha256(Path(constraints.__file__).read_bytes()).hexdigest()}
        return field._finish(result, originals, before, budget, hashes)
    except StudioError as error:
        error = field._normalize_error(error)
        if budget is not None:
            error.work = dict(budget.counts); error.phase = budget.phase
            error.absolute_deadline = budget.deadline
        raise error
