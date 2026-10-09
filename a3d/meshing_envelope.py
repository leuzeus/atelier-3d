"""Caller-owned monotone work envelope for opt-in synchronized meshing."""
import copy
import json
import math
import time
from types import MappingProxyType
from .core import StudioError


def _refuse(reason, message):
    error = StudioError('Meshing envelope: ' + message)
    error.reason = reason
    error.status = 'INCOMPLETE' if reason in ('BUDGET_EXHAUSTED', 'DEADLINE_EXHAUSTED', 'STOP_REQUESTED') else 'REFUSED'
    raise error


def _finite_time(value):
    try:
        valid = type(value) in (int,float) and math.isfinite(value)
    except (OverflowError,TypeError,ValueError):
        valid = False
    if not valid:
        _refuse('INVALID_CLOCK', 'local time values must be finite and representable')
    return value


def _identity_json(value, check):
    """Strict JSON types prevent native-key coercion or container aliases."""
    active=set();count=[0]
    def visit(item,depth=0):
        check('material_control_identity')
        count[0]+=1
        if depth>64 or count[0]>4096:
            _refuse('INVALID_ENVELOPE','material identity structure exceeds its scalar bound')
        kind=type(item)
        if kind in (dict,list):
            if id(item) in active:_refuse('INVALID_ENVELOPE','cyclic material identity')
            active.add(id(item))
            try:
                if kind is dict:
                    for key,child in item.items():
                        if type(key) is not str:_refuse('INVALID_ENVELOPE','material JSON keys must be text')
                        visit(key,depth+1);visit(child,depth+1)
                else:
                    for child in item:visit(child,depth+1)
            finally:active.remove(id(item))
        elif kind is str:
            if len(item)>4096:_refuse('INVALID_ENVELOPE','material identity exceeds its scalar bound')
            try:item.encode('utf-8')
            except UnicodeError:_refuse('INVALID_ENVELOPE','material identity must be valid UTF-8')
        elif kind is float:
            if not math.isfinite(item):_refuse('INVALID_ENVELOPE','material identity must be finite')
        elif kind not in (int,bool,type(None)):
            _refuse('INVALID_ENVELOPE','material identity requires strict JSON types')
    visit(value)
    try:result=json.dumps(value,sort_keys=True,separators=(',',':'),allow_nan=False)
    except (TypeError,ValueError,OverflowError):
        _refuse('INVALID_ENVELOPE','material identity must be finite JSON data')
    if len(result.encode('utf-8'))>4096:
        _refuse('INVALID_ENVELOPE','material identity exceeds its declared scalar bound')
    check('after_material_identity_encoding')
    return result


class MeshingEnvelope:
    """One local clock, explicit global/owner limits, no refunds or admission.

    Limits describe work, not live mesh cardinality. The caller still verifies
    component-wide vertices independently. Absolute times are local diagnostics.
    """
    def __init__(self, component_id, limits, *, owner_limits=None, max_seconds=90.,
                 clock=time.monotonic, started_at=None, deadline=None, stop_requested=None):
        if type(component_id) is not str or not component_id:
            _refuse('INVALID_ENVELOPE', 'an explicit component identity is required')
        if type(limits) is not dict or not limits:
            _refuse('INVALID_ENVELOPE', 'explicit work limits are required')
        owners = {} if owner_limits is None else owner_limits
        if type(owners) is not dict:
            _refuse('INVALID_ENVELOPE', 'owner limits must be explicit counters')
        if any(type(k) is not str or not k or type(v) is not int or v < 0 for k,v in limits.items()):
            _refuse('INVALID_ENVELOPE', 'work limits must be nonnegative integers')
        if any(k not in limits or type(v) is not int or v < 0 for k,v in owners.items()):
            _refuse('INVALID_ENVELOPE', 'owner limits must refine existing work counters')
        try:
            valid_duration = type(max_seconds) in (int,float) and math.isfinite(max_seconds) and max_seconds > 0
        except (OverflowError,TypeError,ValueError):
            valid_duration = False
        if not valid_duration:
            _refuse('INVALID_ENVELOPE', 'time must be a positive finite duration')
        self.component_id = component_id
        self.limits = MappingProxyType(dict(limits))
        self.owner_limits = MappingProxyType(dict(owners))
        if not callable(clock):_refuse('INVALID_CLOCK','a callable local clock is required')
        if stop_requested is not None and not callable(stop_requested):
            _refuse('INVALID_ENVELOPE','controlled stop callback must be callable')
        self.clock = clock
        now = self._now()
        origin = now if started_at is None else started_at
        _finite_time(origin)
        if origin > now:
            _refuse('INVALID_CLOCK', 'origin must be from the same local clock before this call')
        if deadline is not None:_finite_time(deadline)
        self.start = origin
        try:self.deadline = min(origin + max_seconds, deadline) if deadline is not None else origin + max_seconds
        except (OverflowError,TypeError,ValueError):_refuse('INVALID_CLOCK','combined local deadline must remain representable')
        _finite_time(self.deadline)
        self._last_clock = now
        self.stop_requested = stop_requested
        self._counts = {key: 0 for key in limits}
        self._owner_counts = {}
        self._controls = {}
        self._control_keys = {}
        self.phase = 'before_capture'
        self.check(self.phase)

    @property
    def material_controls(self):
        return MappingProxyType(self._controls)

    def _now(self):
        try:value=self.clock()
        except StudioError as error:
            if getattr(error,'reason',None) in ('DEADLINE_EXHAUSTED','STOP_REQUESTED','BUDGET_EXHAUSTED'):
                raise
            _refuse('INVALID_CLOCK','local clock callback failed')
        except Exception:
            _refuse('INVALID_CLOCK','local clock callback failed')
        return _finite_time(value)

    def check(self, phase):
        self.phase = phase
        value = self._now()
        if value < self._last_clock:
            _refuse('INVALID_CLOCK', 'local clock must be finite and monotone')
        self._last_clock = value
        if value >= self.deadline:
            _refuse('DEADLINE_EXHAUSTED', 'deadline exhausted during ' + str(phase))
        if self.stop_requested is not None:
            try:stop=self.stop_requested()
            except StudioError:raise
            except Exception:_refuse('INVALID_ENVELOPE','controlled stop callback failed')
            if stop:_refuse('STOP_REQUESTED', 'controlled stop requested during ' + str(phase))

    def reserve(self, kind, amount, *, owner=None):
        self.check('before_reserve:' + str(kind))
        if kind not in self.limits or type(amount) is not int or amount < 0:
            _refuse('INVALID_ENVELOPE', 'reservation requires a declared counter and integer cost')
        if owner is not None and (type(owner) is not str or not owner):
            _refuse('INVALID_ENVELOPE', 'owner must be an explicit piece identity')
        if kind in self.owner_limits and owner is None:
            _refuse('INVALID_ENVELOPE', 'this counter requires a local piece owner')
        local = self._owner_counts.get(owner, {}) if owner is not None else {}
        if self._counts[kind] + amount > self.limits[kind]:
            _refuse('BUDGET_EXHAUSTED', 'component work budget exhausted for ' + kind)
        if kind in self.owner_limits and local.get(kind,0) + amount > self.owner_limits[kind]:
            _refuse('BUDGET_EXHAUSTED', 'piece work budget exhausted for ' + kind)
        self._counts[kind] += amount
        if owner is not None:
            self._owner_counts.setdefault(owner, {})[kind] = local.get(kind,0) + amount
        # A later expiration preserves the debit: no rollback refunds work.
        self.check('after_reserve:' + kind)

    def observe_material_controls(self, component_id, keys_by_piece):
        self.check('before_material_controls')
        if component_id != self.component_id or type(keys_by_piece) is not dict:
            _refuse('INVALID_ENVELOPE', 'material controls must belong to the same component')
        new = {}
        for owner, values in keys_by_piece.items():
            if type(owner) is not str or not owner or type(values) not in (list,tuple,set,frozenset):
                _refuse('INVALID_ENVELOPE', 'material control identities require an explicit piece')
            self.check('material_control_identity')
            identities = set()
            for value in values:
                identities.add(_identity_json(value,self.check))
            new[owner] = identities - self._control_keys.get(owner,set())
        # Preflight the whole component: no partly admitted control set.
        total = sum(map(len,new.values()))
        if self._counts.get('attempted_insertions',0) + total > self.limits.get('attempted_insertions',-1):
            _refuse('BUDGET_EXHAUSTED', 'component material controls exceed the insertion budget')
        for owner, identities in new.items():
            if 'attempted_insertions' in self.owner_limits:
                local = self._owner_counts.get(owner,{}).get('attempted_insertions',0)
                if local + len(identities) > self.owner_limits['attempted_insertions']:
                    _refuse('BUDGET_EXHAUSTED', 'piece material controls exceed the insertion budget')
        for owner, identities in new.items():
            self.reserve('attempted_insertions',len(identities),owner=owner)
            self._control_keys.setdefault(owner,set()).update(identities)
            self._controls[owner] = len(self._control_keys[owner])
        self.check('after_material_controls')
        return {'component':sum(self._controls.values()), 'by_piece':dict(self._controls)}

    def snapshot(self):
        self.check('envelope_snapshot')
        return {'version':1, 'component_id':self.component_id,
                'limits':dict(self.limits), 'owner_limits':dict(self.owner_limits),
                'work':dict(self._counts), 'owner_work':copy.deepcopy(self._owner_counts),
                'material_controls':dict(self._controls), 'costs_refunded':False,
                'clock_scope':'SINGLE_CALLER_LOCAL_PROCESS_NO_CROSS_PROCESS_DEADLINE',
                'start':self.start, 'absolute_deadline':self.deadline,
                'last_checkpoint':self._last_clock, 'last_phase':self.phase,
                'qualification':'NONE', 'admission':'NONE'}
