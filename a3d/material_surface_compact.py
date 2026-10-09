"""Separate exact storage for supplied affine fields; no V1 consumer or solver.

The internal caller owns capture, the already-validated field state, and the
single budget. This module never creates a clock or changes a field cap.
"""
from fractions import Fraction as F
import hashlib
import json
from pathlib import Path
import re

from . import material_sample_carrier as uv
from . import material_surface_field as field
from .core import StudioError


DISCRIMINANT = 'MATERIAL_SURFACE_FIELD_COMPACT_V1'
_GEOMETRY_KEYS = ('source_carrier', 'reference_carrier', 'source_reference_carrier')
_STATUSES = ('COMPILED_TEST_ONLY', 'VALIDATED_STORAGE_TEST_ONLY')
_PROVENANCE_SCOPE = 'NON_ADMITTED_NOT_APPLIED_TO_COMPUTATION'


def _refuse(reason, detail):
    field._refuse(reason, 'compact storage: ' + detail)


def _budget(budget):
    # An internal caller supplies the real existing ledger, never a no-op
    # adapter or a newly opened budget hidden inside a representation helper.
    if type(budget) is not field._Budget:
        _refuse('INVALID_BUDGET', 'the existing field budget instance is required')
    budget.check('compact_before_input_access')
    if set(budget.limits) != set(field._DEFAULTS):
        _refuse('INVALID_BUDGET', 'the unchanged field cap set is required')
    for key, value in budget.limits.items():
        budget.check('compact_existing_caps')
        valid = type(value) in (int, float) if key == 'max_seconds' else type(value) is int
        if not valid or not field._finite(value) or not 0 < value <= field._HARD[key]:
            _refuse('INVALID_BUDGET', 'no compact cap may relax the existing hard caps')
    for key, value in budget.counts.items():
        budget.check('compact_existing_ledger')
        if ('max_'+key not in budget.limits or type(value) is not int or
            not 0 <= value <= budget.limits['max_'+key]):
            _refuse('INVALID_BUDGET', 'bounded nonnegative cumulative counters are required')


def _code_hashes(budget):
    result = {}
    for label, path in (('compact', __file__), ('field', field.__file__), ('uv', uv.__file__)):
        budget.check('compact_code_before_read')
        value = Path(path).read_bytes()
        budget.check('compact_code_after_read')
        result[label] = hashlib.sha256(value).hexdigest()
        budget.check('compact_code_after_hash')
    return result


def _same(expected, actual, budget):
    """Type-sensitive equality against the canonical closed JSON encoding.

    This does not produce another output or reset a converter. Rational
    comparisons consume the existing rational ledger; input capture has
    already charged the actual supplied JSON nodes and bytes.
    """
    budget.check('compact_exact_comparison')
    if type(expected) is F:
        return type(actual) is str and actual == str(budget.q(expected))
    if type(expected) is dict:
        return (type(actual) is dict and set(expected) == set(actual) and
                all(_same(value, actual[key], budget) for key, value in expected.items()))
    if type(expected) in (list, tuple):
        return (type(actual) is list and len(expected) == len(actual) and
                all(_same(a, b, budget) for a, b in zip(expected, actual)))
    if type(expected) is not type(actual):
        return False
    if type(expected) is float:
        return expected.hex() == actual.hex()
    return expected == actual


def _binding(originals, before, budget, *, packing, data=None, provenance=None, compact=None):
    _budget(budget)
    count = 4 if packing else 3
    if type(originals) is not list or len(originals) != count:
        _refuse('INVALID_CAPTURE', 'explicit original capture scope is required')
    if type(before) is not str or not re.fullmatch('[0-9a-f]{64}', before):
        _refuse('INVALID_CAPTURE', 'a captured SHA-256 is required')
    declaration = originals[2 if packing else 1]
    deadline = originals[3 if packing else 2]
    if (declaration is not None and type(declaration) is not dict or
        {**field._DEFAULTS, **({} if declaration is None else declaration)} != budget.limits or
        deadline != budget.declared_deadline):
        _refuse('INVALID_CAPTURE', 'capture must bind the actual budget declaration and deadline')
    if field._hash(originals, budget, 'compact_original_capture') != before:
        _refuse('REFERENCE_MUTATION', 'original capture has changed')
    scoped = ([data, provenance, declaration, deadline] if packing else
              [compact, declaration, deadline])
    if field._hash(scoped, budget, 'compact_captured_scope') != before:
        _refuse('INVALID_CAPTURE', 'data and provenance must belong to the same original capture')


def _pair_rows(records, budget, estimated_nodes):
    rows = []; lookup = {}
    for record in records:
        budget.check('compact_binary_parent')
        first, carrier = record['source_face_id'], record['carrier_face_id']
        key = (first, carrier)
        if key in lookup:
            _refuse('INVALID_PARENT', 'a binary parent pair must have one exact record')
        polygon = record['uv_polygon_cm']
        if len(polygon) < 3:
            _refuse('INVALID_PATCH', 'a positive-area polygon needs at least three corners')
        estimated_nodes[0] += 5 + 3 * len(polygon)
        budget.available('output_nodes', estimated_nodes[0])
        lookup[key] = len(rows)
        rows.append([first, carrier, polygon, record['area_cm2']])
    return rows, lookup


def _geometry(state, budget):
    # State is internal output from the unchanged _compile in this caller.
    # This is storage only; the untrusted-format validator below recompiles
    # independently before comparing every parent, polygon and exact area.
    estimated_nodes = [4]
    source, source_lookup = _pair_rows(
        state['material_uv']['source_carrier_intersections'], budget, estimated_nodes)
    reference, reference_lookup = _pair_rows(
        state['reference_uv']['source_carrier_intersections'], budget, estimated_nodes)
    triples = []; seen = set()
    for record in state['patches']:
        budget.check('compact_triple_parent')
        source_key = (record['source_face_id'], record['carrier_face_id'])
        reference_key = (record['reference_face_id'], record['carrier_face_id'])
        if source_key not in source_lookup or reference_key not in reference_lookup:
            _refuse('INVALID_PARENT', 'a triple needs both actual binary parents')
        parents = (source_lookup[source_key], reference_lookup[reference_key])
        if parents in seen:
            _refuse('INVALID_PARENT', 'the same exact parent intersection was repeated')
        seen.add(parents); polygon = record['uv_polygon_cm']
        if len(polygon) < 3:
            _refuse('INVALID_PATCH', 'a triple needs a positive-area polygon')
        estimated_nodes[0] += 5 + 3 * len(polygon)
        budget.available('output_nodes', estimated_nodes[0])
        triples.append([*parents, polygon, record['area_cm2']])
    return dict(zip(_GEOMETRY_KEYS, (source, reference, triples)))


def _payload(state, provenance, budget, status):
    result = field._base(state)
    # Omit only deterministic storage redundancy. Original full inputs and
    # every other semantic record remain unchanged and explicitly present.
    for key in ('source_carrier_intersections', 'reference_carrier_intersections',
                'material_reference_carrier_patches'):
        del result[key]
    result.update(discriminant=DISCRIMINANT, status=status,
                  geometry=_geometry(state, budget), provenance=provenance,
                  provenance_scope=_PROVENANCE_SCOPE)
    return result


def _input_hashes(state, provenance, budget):
    values = field._hashes(state, budget)
    code = _code_hashes(budget)
    values['compact_code'] = code['compact']
    values['provenance'] = field._hash(provenance, budget, 'compact_provenance')
    return values, code


def _whole_nodes(value, budget):
    budget.check('compact_complete_node_measurement')
    if type(value) is dict:
        return 1 + sum(_whole_nodes(child, budget) for child in value.values())
    if type(value) is list:
        return 1 + sum(_whole_nodes(child, budget) for child in value)
    return 1


def _whole_bytes(value, budget):
    size = 0
    encoder = json.JSONEncoder(ensure_ascii=False, allow_nan=False, separators=(',', ':'))
    for chunk in encoder.iterencode(value):
        budget.check('compact_complete_serialization')
        size += len(chunk.encode('utf-8'))
        if size > field._HARD['max_output_bytes']:
            _refuse('BUDGET_EXHAUSTED', 'complete compact representation exceeds the output hard cap')
    budget.check('compact_complete_serialization_after')
    return size


def _preservation_digest(value):
    """Local last-work boundary, followed by a deadline check by the caller."""
    return uv._digest(value)


def _finish(value, originals, before, budget, input_hashes, code):
    """One result's complete size plus the caller's monotone output totals.

    The JSON value-node ledger is charged once as the result is encoded.
    Sizing passes are stream inspections, not new returned objects or full
    serialized buffers; the settled complete representation is charged once.
    No prior output byte counter is assigned a smaller/current-only value.
    """
    budget.check('compact_before_output')
    nodes_before = budget.counts.setdefault('output_nodes', 0)
    bytes_before = budget.counts.setdefault('output_bytes', 0)
    encoded = field._encode(value, budget)
    if field._hash(originals, budget, 'compact_preservation') != before:
        _refuse('REFERENCE_MUTATION', 'inputs changed during packing')
    receipt = {
        'purpose':'TEST_ONLY','qualification':'NONE','input_sha256':before,
        'input_hashes':input_hashes,'code_sha256':code,
        'content_sha256':field._hash(encoded, budget, 'compact_content'),
        'budgets':dict(budget.limits),'work':dict(budget.counts),
        'output':{'nodes':0,'bytes':0},
        'clock_start_before_capture':budget.start,'absolute_deadline':budget.deadline,
        'caller_absolute_deadline':budget.declared_deadline,'elapsed_seconds':0.,
        'source_uv_rounded':False,'identities_merged':False,'inputs_preserved':True,
        'constraints_3d_qualified':False,'physical_mesh_qualified':False,
        'clock_contract':'READ_ONLY_MONOTONE_COOPERATIVE',
        'output_scope':'COMPLETE_RESULT_INCLUDING_RECEIPT',
        'work_scope':'CALLER_CUMULATIVE_NO_RESET_OR_REFUND',
    }
    encoded['receipt'] = field._encode(receipt, budget)
    encoded['receipt']['output']['nodes'] = budget.counts['output_nodes'] - nodes_before
    encoded['receipt']['work'].update(budget.counts)
    budget.check('compact_before_complete_size')
    encoded['receipt']['elapsed_seconds'] = budget.last - budget.start
    # Both decimal counters refer to this same representation. The bounded
    # fixed point changes only scalar values, never the charged node count.
    settled = False
    for _ in range(len(str(budget.limits['max_output_bytes'])) + 3):
        size = _whole_bytes(encoded, budget)
        budget.available('output_bytes', size)
        if size == encoded['receipt']['output']['bytes']:
            settled = True
            break
        encoded['receipt']['output']['bytes'] = size
        encoded['receipt']['work']['output_bytes'] = bytes_before + size
    if not settled:
        _refuse('BUDGET_EXHAUSTED', 'complete output counters did not settle')
    budget.take('output_bytes', size)
    if encoded['receipt']['work']['output_bytes'] != budget.counts['output_bytes']:
        _refuse('INVALID_OUTPUT_ACCOUNTING', 'cumulative output byte counters differ')
    if _code_hashes(budget) != code:
        _refuse('CODE_MUTATION', 'consumed field, UV or compact code changed')
    if field._hash(originals, budget, 'compact_output_preservation') != before:
        _refuse('REFERENCE_MUTATION', 'inputs changed during complete output accounting')
    budget.check('compact_output_return')
    if _preservation_digest(originals) != before:
        _refuse('REFERENCE_MUTATION', 'inputs changed in the final clock callback')
    budget.check('compact_output_after_preservation')
    if _preservation_digest(originals) != before:
        _refuse('REFERENCE_MUTATION', 'inputs changed before the final preservation hash')
    budget.check('compact_output_terminal_deadline')
    return encoded


def pack_material_surface_state(state, *, originals, before, budget,
                                input_hashes=None, provenance=None):
    """Pack trusted internal _compile output under the caller's same ledger.

    ``originals`` is [data, provenance, budget_declaration, deadline], captured
    before _compile. This is not an API that admits arbitrary supplied state.
    Untrusted persisted compact objects require the recompiler below.
    """
    try:
        _budget(budget)
        if type(state) is not dict or type(state.get('data')) is not dict:
            _refuse('INVALID_CONTRACT', 'internal compiled state is required')
        _binding(originals, before, budget, packing=True,
                 data=state['data'], provenance=provenance)
        hashes, code = _input_hashes(state, provenance, budget)
        if input_hashes is not None:
            base_hashes = {key:value for key,value in hashes.items()
                           if key not in ('compact_code','provenance')}
            if not _same(base_hashes, input_hashes, budget):
                _refuse('REFERENCE_MUTATION', 'provided field input hashes differ')
        result = _payload(state, provenance, budget, _STATUSES[0])
        return _finish(result, originals, before, budget, hashes, code)
    except StudioError as error:
        raise field._normalize_error(error)
    except (KeyError, TypeError, ValueError, IndexError):
        _refuse('INVALID_CONTRACT', 'invalid internal state or compact contract')


def _receipt_check(compact, expected_hashes, code, budget):
    receipt = compact['receipt']
    required = ('purpose','qualification','input_sha256','input_hashes','code_sha256',
        'content_sha256','budgets','work','output','clock_start_before_capture',
        'absolute_deadline','caller_absolute_deadline','elapsed_seconds',
        'source_uv_rounded','identities_merged','inputs_preserved','constraints_3d_qualified',
        'physical_mesh_qualified','clock_contract','output_scope','work_scope')
    uv._fields(receipt, required)
    for key, expected in {
        'purpose':'TEST_ONLY','qualification':'NONE','source_uv_rounded':False,
        'identities_merged':False,'inputs_preserved':True,'constraints_3d_qualified':False,
        'physical_mesh_qualified':False,'clock_contract':'READ_ONLY_MONOTONE_COOPERATIVE',
        'output_scope':'COMPLETE_RESULT_INCLUDING_RECEIPT',
        'work_scope':'CALLER_CUMULATIVE_NO_RESET_OR_REFUND',
    }.items():
        if not _same(expected, receipt[key], budget):
            _refuse('INVALID_RECEIPT', 'a storage receipt cannot claim admission')
    if (not _same(expected_hashes, receipt['input_hashes'], budget) or
        not _same(code, receipt['code_sha256'], budget)):
        _refuse('REFERENCE_MUTATION', 'compact input, provenance or code identities differ')
    for key in ('input_sha256','content_sha256'):
        if type(receipt[key]) is not str or not re.fullmatch('[0-9a-f]{64}',receipt[key]):
            _refuse('INVALID_RECEIPT', 'SHA-256 receipt identities are required')
    payload = {key:value for key,value in compact.items() if key != 'receipt'}
    if field._hash(payload, budget, 'compact_supplied_content') != receipt['content_sha256']:
        _refuse('REFERENCE_MUTATION', 'compact content identity differs')
    if not _same(budget.limits, receipt['budgets'], budget):
        _refuse('INVALID_RECEIPT', 'the same declared caller caps are required')
    uv._fields(receipt['output'], ('nodes','bytes'))
    output = receipt['output']; work = receipt['work']
    if type(work) is not dict:
        _refuse('INVALID_RECEIPT', 'cumulative work object is required')
    for key, count in work.items():
        budget.check('compact_supplied_work')
        if ('max_'+key not in budget.limits or type(count) is not int or
            not 0 <= count <= budget.limits['max_'+key]):
            _refuse('INVALID_RECEIPT', 'invalid bounded cumulative work counter')
    for key, measured in (('nodes',_whole_nodes(compact,budget)),
                          ('bytes',_whole_bytes(compact,budget))):
        value = output[key]
        if (type(value) is not int or value != measured or value <= 0 or
            type(work.get('output_'+key)) is not int or
            work['output_'+key] < value or value > budget.limits['max_output_'+key]):
            _refuse('INVALID_RECEIPT', 'complete result size and cumulative ledger differ')
    for key in ('clock_start_before_capture','absolute_deadline','elapsed_seconds'):
        if not field._finite(receipt[key]):
            _refuse('INVALID_RECEIPT', 'finite historical time observations are required')
    start = receipt['clock_start_before_capture']; deadline = receipt['absolute_deadline']
    declared = receipt['caller_absolute_deadline']
    if declared is not None and not field._finite(declared):
        _refuse('INVALID_RECEIPT', 'finite historical caller deadline required')
    expected_deadline = (min(start+budget.limits['max_seconds'],declared)
                         if declared is not None else start+budget.limits['max_seconds'])
    if deadline != expected_deadline:
        _refuse('INVALID_RECEIPT', 'historical phase deadline differs')
    if not 0 <= receipt['elapsed_seconds'] < deadline-start:
        _refuse('INVALID_RECEIPT', 'historical elapsed checkpoint exceeds its phase')


def _validated(compact, originals, before, budget):
    _binding(originals, before, budget, packing=False, compact=compact)
    if type(compact) is not dict or compact.get('discriminant') != DISCRIMINANT:
        _refuse('INVALID_CONTRACT', 'the separate compact discriminant is required')
    if compact.get('status') not in _STATUSES:
        _refuse('INVALID_CONTRACT', 'explicit compact storage status is required')
    state = field._compile(compact['inputs'], budget)
    provenance = compact['provenance']
    expected = _payload(state, provenance, budget, compact['status'])
    supplied = {key:value for key,value in compact.items() if key != 'receipt'}
    if not _same(expected, supplied, budget):
        _refuse('COMPACT_GEOMETRY_MISMATCH', 'full reconstructed storage, parents or exact polygons differ')
    hashes, code = _input_hashes(state, provenance, budget)
    _receipt_check(compact, hashes, code, budget)
    return state, provenance, hashes, code


def validate_material_surface_compact(compact, *, originals, before, budget):
    """Recompile and compare every closed record without a ledger/clock reset.

    Capture [compact, budget_declaration, deadline] under this same caller
    ledger before calling. This validates storage, not field metrics/3D rows.
    """
    try:
        state, provenance, hashes, code = _validated(compact, originals, before, budget)
        result = _payload(state, provenance, budget, _STATUSES[1])
        return _finish(result, originals, before, budget, hashes, code)
    except StudioError as error:
        raise field._normalize_error(error)
    except (KeyError, TypeError, ValueError, IndexError):
        _refuse('INVALID_CONTRACT', 'invalid closed compact field contract')


def expand_material_surface_compact_geometry(compact, *, originals, before, budget):
    """Fixture-only exact verbose geometry; never a V1-compatible compilation.

    Omitted corner IDs and barycentric weights are rederived by the unchanged
    field/UV recompiler. The complete expansion plus receipt is charged again
    under the same output caps, and may refuse even if compact packing passed.
    """
    try:
        state, _, hashes, code = _validated(compact, originals, before, budget)
        result = {'discriminant':'MATERIAL_SURFACE_COMPACT_GEOMETRY_EXPANSION_TEST_V1',
            'purpose':'TEST_ONLY','qualification':'NONE','status':'EXPANDED_GEOMETRY_TEST_ONLY',
            'physical_mesh':False,'is_installable':False,'v1_consumer_compatible':False,
            'source_carrier_intersections':state['material_uv']['source_carrier_intersections'],
            'reference_carrier_intersections':state['reference_uv']['source_carrier_intersections'],
            'material_reference_carrier_patches':state['patches']}
        return _finish(result, originals, before, budget, hashes, code)
    except StudioError as error:
        raise field._normalize_error(error)
    except (KeyError, TypeError, ValueError, IndexError):
        _refuse('INVALID_CONTRACT', 'invalid compact expansion contract')
