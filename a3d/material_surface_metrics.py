"""Internal affine metrics on fresh compiler state; no domain or product gate."""
from fractions import Fraction as F
import hashlib
from pathlib import Path

from . import material_surface_field as field
from . import material_surface_compact as storage
from .core import StudioError


DISCRIMINANT = 'MATERIAL_SURFACE_AFFINE_METRICS_V1'


def _code_hash(budget):
    budget.check('metrics_code_before_read')
    raw = Path(__file__).read_bytes()
    budget.check('metrics_code_after_read')
    result = hashlib.sha256(raw).hexdigest()
    budget.check('metrics_code_after_hash')
    return result


def _used_inputs(state, budget):
    """Hash existing exact values, without creating/debiting new rationals.

    These read/hash guards do not reset work or encode another output. Domain
    validation and construction of these internal values belong to the caller.
    """
    def rational(value):
        budget.check('metrics_used_input_value')
        if type(value) is not F:
            field._refuse('INVALID_CONTRACT', 'fresh exact compiler coordinates required')
        if max(value.numerator.bit_length(), value.denominator.bit_length()) > budget.limits['max_fraction_bits']:
            field._refuse('BUDGET_EXHAUSTED', 'used rational precision cap exhausted')
        return str(value)
    cm = state['carrier_mesh']
    return {'carrier_face_ids':cm['raw']['face_ids'], 'carrier_faces':cm['faces'],
        'carrier_triangles_exact_uv':[[[rational(v) for v in point] for point in triangle]
                                     for triangle in cm['triangles']],
        'current_exact_cm':[[rational(v) for v in point] for point in state['current']],
        'limits':state['limits']}


def _face_metrics(state, budget):
    """The metric-only section of field._observe, using its exact helpers."""
    cm = state['carrier_mesh']; metrics = []
    lower, upper = F(state['limits']['min_stretch'])**2, F(state['limits']['max_stretch'])**2
    for index, face in enumerate(cm['faces']):
        budget.take('metric_faces'); budget.check('metrics_gram')
        jac = field._jacobian(cm['triangles'][index], [state['current'][i] for i in face], budget)
        gram = [[budget.q(sum(row[a]*row[b] for row in jac)) for b in range(2)] for a in range(2)]
        low = [[gram[a][b]-(lower if a==b else 0) for b in range(2)] for a in range(2)]
        high = [[(upper if a==b else 0)-gram[a][b] for b in range(2)] for a in range(2)]
        lp, hp = field._psd(low,budget), field._psd(high,budget)
        metrics.append({'carrier_face_id':cm['raw']['face_ids'][index], 'jacobian_exact':jac,
            'gram_exact':gram, 'lower_psd':lp, 'upper_psd':hp,
            'metric_bounds_met':lp['satisfied'] and hp['satisfied']})
    return metrics, lower, upper


def observe_material_surface_metrics(state, *, originals, before, budget,
                                     input_hashes=None, provenance=None):
    """Internal TEST_ONLY/NONE route after the caller's one fresh _compile.

    Supply the original [data, provenance, budget declaration, deadline] capture
    and its same actual field._Budget. This function neither captures/recompiles
    a persisted client object nor validates a domain from supplied state/flags.
    Only affine metrics are measured. Displacement, stops, contacts and fitting
    remain unassessed even when every face meets its metric bounds.
    """
    try:
        storage._budget(budget)
        if type(state) is not dict or type(state.get('data')) is not dict:
            field._refuse('INVALID_CONTRACT', 'fresh internal compiler state required')
        storage._binding(originals,before,budget,packing=True,data=state['data'],provenance=provenance)
        hashes, code = storage._input_hashes(state,provenance,budget)
        if input_hashes is not None:
            base = {key:value for key,value in hashes.items() if key not in ('compact_code','provenance')}
            if not storage._same(base,input_hashes,budget):
                field._refuse('REFERENCE_MUTATION', 'provided compiler input hashes differ')
        metrics_code = _code_hash(budget)
        used_before = field._hash(_used_inputs(state,budget),budget,'metrics_used_inputs')
        hashes.update(metrics_code=metrics_code,metric_inputs=used_before)
        metrics, lower, upper = _face_metrics(state,budget)
        violated = [row['carrier_face_id'] for row in metrics if not row['metric_bounds_met']]
        result = {'discriminant':DISCRIMINANT, 'version':1, 'purpose':'TEST_ONLY',
            'qualification':'NONE', 'status':'OBSERVED_AFFINE_METRICS_TEST_ONLY',
            'physical_mesh':False, 'is_installable':False,
            'domain_validation':'CALLER_FRESH_COMPILER_STATE_REQUIRED_NOT_REVALIDATED',
            'metric_scope':'PROVIDED_AFFINE_SURFACE_FIELD_ONLY_NOT_PHYSICAL_MESH',
            'method':'EXACT_AFFINE_JACOBIAN_GRAM_PSD', 'epsilon_allowance':False,
            'lower_gram_bound_squared_exact':lower, 'upper_gram_bound_squared_exact':upper,
            'carrier_face_metrics':metrics,
            'metric_checks':{'evaluated_faces':len(metrics), 'passed_faces':len(metrics)-len(violated),
                'violated_faces':len(violated), 'violating_face_ids':violated,
                'all_bounds_met':not violated},
            'metrics_code_sha256':metrics_code, 'metric_inputs_sha256':used_before,
            'receipt_scope':'COMPACT_FINALIZER_CHECKPOINT_BEFORE_METRICS_RETURN_GUARDS',
            'return_guard_scope':'METRICS_CODE_ORIGINALS_USED_INPUT_HASHES_AND_SAME_DEADLINE',
            'displacement':'NOT_ASSESSED', 'step':'NOT_ASSESSED', 'physical_stops':'NOT_ASSESSED',
            'contacts':'NOT_ASSESSED', 'constraints_3d':'NOT_QUALIFIED',
            'trajectory':'NOT_ASSESSED', 'simulation':'NOT_EXECUTED', 'fitting':'NOT_QUALIFIED'}
        encoded = storage._finish(result,originals,before,budget,hashes,code)
        # _finish validates its compact/field/UV code. The separate observer is
        # linked by actual bytes in input_hashes and checked after that checkpoint.
        # No counter or encoded receipt is changed by these timed read/hash guards.
        if _code_hash(budget) != metrics_code:
            field._refuse('CODE_MUTATION', 'metrics module changed during finalization')
        if field._hash(originals,budget,'metrics_final_originals') != before:
            field._refuse('REFERENCE_MUTATION', 'original capture changed during metrics')
        if field._hash(_used_inputs(state,budget),budget,'metrics_final_used_inputs') != used_before:
            field._refuse('REFERENCE_MUTATION', 'used internal metric inputs changed')
        budget.check('metrics_return_terminal_deadline')
        return encoded
    except StudioError as error:
        raise field._normalize_error(error)
    except (KeyError,TypeError,ValueError,IndexError,AttributeError,ZeroDivisionError):
        field._refuse('INVALID_CONTRACT', 'malformed internal metric state or capture')
