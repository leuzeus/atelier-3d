"""Portable affine 3D fields with exact material supports; no production caller."""
import math
import time
import hashlib
import json
from fractions import Fraction as F
from pathlib import Path

from . import material_sample_carrier as uv
from .core import StudioError


DISCRIMINANT = 'MATERIAL_SURFACE_FIELD_V1'
_DEFAULTS = {**uv._DEFAULTS, 'max_fraction_operations': 300000,
             'max_reference_vertices': 4000, 'max_reference_triangles': 8000,
             'max_refinement_patches': 50000, 'max_patch_vertex_checks': 300000,
             'max_metric_faces': 8000, 'max_queries': 10000,
             'max_targets': 10000, 'max_output_nodes': 500000,
             'max_output_bytes': 8388608}
_HARD = {**uv._HARD, **{k:v for k,v in _DEFAULTS.items()if k not in uv._HARD}}
_LIMITS = {'min_stretch': .9, 'max_stretch': 1.1,
           'max_displacement_cm': 8., 'max_step_cm': .5}


def _finite(value):
    if type(value)not in(int,float):return False
    try:return math.isfinite(value)
    except OverflowError:return False


def _refuse(reason, detail):
    error=StudioError('Material surface field: '+detail)
    error.reason=reason;error.qualification='NONE'
    error.status='INCOMPLETE'if reason in ('DEADLINE_EXHAUSTED','BUDGET_EXHAUSTED')else'REFUSED'
    raise error


class _Budget:
    """One cooperative clock from before capture through final return checks."""
    def __init__(self, values, deadline, clock):
        if not callable(clock):_refuse('INVALID_CLOCK','monotone clock required')
        if deadline is not None and not _finite(deadline):
            _refuse('INVALID_DEADLINE','finite absolute deadline required')
        self.clock=clock;self.counts={};self.declared_deadline=deadline
        self.start=self.now()
        self.deadline=min(self.start+60.,deadline)if deadline is not None else self.start+60.
        self.check('before_budget_capture')
        if values is None:values={}
        if(type(values)is not dict or len(values)>len(_DEFAULTS)or
            any(type(key)is not str or len(key)>128 for key in values)or set(values)-set(_DEFAULTS)):
            _refuse('INVALID_BUDGET','unknown or non-object budget')
        self.limits={**_DEFAULTS,**values}
        for key,value in self.limits.items():
            self.check('budget_capture')
            kind=type(value)in(int,float)if key=='max_seconds'else type(value)is int
            if not kind or not 0<value<=_HARD[key]or not _finite(value):
                _refuse('INVALID_BUDGET','invalid bounded value for '+key)
        self.deadline=min(self.start+self.limits['max_seconds'],deadline)if deadline is not None else self.start+self.limits['max_seconds']
        self.check('before_capture')

    def now(self):
        try:value=self.clock()
        except Exception:_refuse('INVALID_CLOCK','clock callback failed')
        if not _finite(value)or(hasattr(self,'last')and value<self.last):
            _refuse('INVALID_CLOCK','clock must return finite monotone times')
        self.last=value
        return value

    def check(self,phase):
        self.phase=phase
        if self.now()>=self.deadline:_refuse('DEADLINE_EXHAUSTED','deadline exhausted during '+phase)

    def take(self,key,count=1):
        self.check(key)
        used=self.counts.get(key,0)+count
        if used>self.limits['max_'+key]:_refuse('BUDGET_EXHAUSTED',key+' work cap exhausted')
        self.counts[key]=used

    def available(self,key,count):
        self.check('available_'+key)
        if self.counts.get(key,0)+count>self.limits['max_'+key]:
            _refuse('BUDGET_EXHAUSTED',key+' work cannot fit the shared cap')

    def q(self,value):
        self.take('fraction_operations')
        if max(value.numerator.bit_length(),value.denominator.bit_length())>self.limits['max_fraction_bits']:
            _refuse('BUDGET_EXHAUSTED','rational precision cap exhausted')
        return value


def _snapshot(value,budget):
    """Native containers only, bounded copy before hashing, with timed traversal."""
    size=0
    def visit(item,depth):
        nonlocal size
        budget.take('input_nodes');size+=8
        if depth>32:_refuse('INVALID_REFERENCE','nesting/cyclic reference is unsupported')
        if type(item)is dict:
            result={}
            for key,child in item.items():
                if type(key)is not str or len(key)>128:_refuse('INVALID_REFERENCE','invalid native key')
                size+=6*len(key)+3;result[key]=visit(child,depth+1)
        elif type(item)is list:result=[visit(x,depth+1)for x in item]
        elif type(item)is str and len(item)<=2048:size+=6*len(item)+2;result=item
        elif type(item)is int and item.bit_length()<=4096:size+=len(str(item));result=item
        elif type(item)is float and math.isfinite(item):size+=len(repr(item));result=item
        elif item is None or type(item)is bool:result=item
        else:_refuse('INVALID_REFERENCE','bounded finite native JSON values required')
        if size>budget.limits['max_input_bytes']:_refuse('BUDGET_EXHAUSTED','input byte cap exhausted')
        return result
    return visit(value,0)


def _hash(value,budget,phase):
    budget.check(phase+'_before_hash');result=uv._digest(value);budget.check(phase+'_after_hash')
    return result


def _capture(originals,budgets,deadline,clock):
    budget=_Budget(budgets,deadline,clock)
    copied=_snapshot(originals,budget)
    before=_hash(copied,budget,'snapshot')
    if _hash(originals,budget,'original')!=before:_refuse('REFERENCE_MUTATION','inputs changed during capture')
    return copied,before,budget


def _encode(value,budget):
    def visit(item):
        budget.take('output_nodes')
        if isinstance(item,F):result=str(budget.q(item))
        elif type(item)is dict:
            result={key:visit(child)for key,child in item.items()}
        elif type(item)in(list,tuple):result=[visit(v)for v in item]
        else:result=item
        return result
    return visit(value)


def _measure_output_bytes(encoded,budget):
    """Size the complete compact UTF8 return, including its own size counter."""
    encoder=json.JSONEncoder(ensure_ascii=False,allow_nan=False,separators=(',',':'))
    # Only the integer value changes, never the receipt's node count. Starting
    # at zero reaches the fixed point in a number of passes bounded by the
    # declared byte cap's digit count. Re-serializations are not extra outputs.
    for _ in range(len(str(budget.limits['max_output_bytes']))+2):
        size=0
        for chunk in encoder.iterencode(encoded):
            budget.check('output_serialization')
            size+=len(chunk.encode('utf8'))
            if size>budget.limits['max_output_bytes']:
                _refuse('BUDGET_EXHAUSTED','complete output byte cap exhausted')
        budget.check('output_serialization_after')
        if size==encoded['receipt']['work']['output_bytes']:
            budget.counts['output_bytes']=size
            return
        encoded['receipt']['work']['output_bytes']=size
    _refuse('BUDGET_EXHAUSTED','complete output size counter did not settle')


def _finish(value,originals,before,budget,input_hashes):
    # Reserve both ledger keys before counting the receipt; adding a key after
    # traversal would itself introduce an uncharged returned JSON value.
    budget.counts.setdefault('output_nodes',0)
    budget.counts.setdefault('output_bytes',0)
    encoded=_encode(value,budget)
    if _hash(originals,budget,'preservation')!=before:_refuse('REFERENCE_MUTATION','inputs changed during operation')
    receipt={'purpose':'TEST_ONLY','qualification':'NONE','input_sha256':before,
        'input_hashes':input_hashes,'content_sha256':_hash(encoded,budget,'content'),
        'budgets':dict(budget.limits),'work':dict(budget.counts),
        'clock_start_before_capture':budget.start,'absolute_deadline':budget.deadline,
        'caller_absolute_deadline':budget.declared_deadline,'elapsed_seconds':budget.now()-budget.start,
        'source_uv_rounded':False,'identities_merged':False,'inputs_preserved':True,
        'constraints_3d_qualified':False,'physical_mesh_qualified':False,
        'clock_contract':'READ_ONLY_MONOTONE_COOPERATIVE'}
    # Payload nodes and receipt nodes are visited exactly once, including every
    # nested budget/work value. Dictionary keys are not JSON value nodes.
    encoded['receipt']=_encode(receipt,budget)
    encoded['receipt']['work'].update(budget.counts)
    budget.check('final_return')
    if _hash(originals,budget,'final_preservation')!=before:_refuse('REFERENCE_MUTATION','inputs changed before return')
    budget.check('return')
    # A caller clock is required to be a read-only monotone clock. Recheck after
    # that callback too, so a hostile clock mutation cannot certify an input.
    if uv._digest(originals)!=before:_refuse('REFERENCE_MUTATION','inputs changed in final clock callback')
    budget.check('final_deadline_after_preservation')
    encoded['receipt']['elapsed_seconds']=budget.last-budget.start
    _measure_output_bytes(encoded,budget)
    if _hash(originals,budget,'output_preservation')!=before:_refuse('REFERENCE_MUTATION','inputs changed during complete output accounting')
    budget.check('output_return')
    if uv._digest(originals)!=before:_refuse('REFERENCE_MUTATION','inputs changed in output return clock callback')
    budget.check('output_deadline_after_preservation')
    if uv._digest(originals)!=before:_refuse('REFERENCE_MUTATION','inputs changed in final output clock callback')
    budget.check('output_terminal_deadline')
    return encoded


def _positions(raw,count,budget,label):
    if type(raw)is not list or len(raw)!=count:_refuse('INVALID_COORDINATES',label+' count differs from mesh')
    rows=[]
    for point in raw:
        budget.check(label+'_coordinates')
        if type(point)is not list or len(point)!=3:_refuse('INVALID_COORDINATES','explicit three-coordinate rows required')
        row=[]
        for value in point:
            if type(value)not in(int,float):_refuse('INVALID_COORDINATES','recorded finite binary64 coordinates required')
            try:f=float(value)
            except(OverflowError,ValueError):_refuse('INVALID_COORDINATES','coordinate not representable as finite binary64')
            if not math.isfinite(f)or F(value)!=F(f):_refuse('INVALID_COORDINATES','coordinate not exactly representable as finite binary64')
            row.append(budget.q(F(value)))
        rows.append(row)
    return rows


def _limits(raw):
    raw={}if raw is None else raw
    if type(raw)is not dict or set(raw)-set(_LIMITS):_refuse('INVALID_LIMITS','unknown field limit')
    result={**_LIMITS,**raw}
    for key,value in result.items():
        if not _finite(value)or value<=0:
            _refuse('INVALID_LIMITS','limits must be positive finite native numbers')
    if(result['min_stretch']<_LIMITS['min_stretch']or result['max_stretch']>_LIMITS['max_stretch']or
        result['min_stretch']>result['max_stretch']or result['max_displacement_cm']>8 or result['max_step_cm']>.5):
        _refuse('INVALID_LIMITS','declared safety bounds may be tightened, never relaxed')
    return result


def _parsed(raw,budget):
    # Raw meshes have already passed the unchanged UV builder in this operation.
    points=[tuple(budget.q(uv._number(v,budget))for v in row)for row in raw['uv_cm']]
    return {'raw':raw,'points':points,'faces':raw['triangles'],
            'triangles':[[points[i]for i in face]for face in raw['triangles']],
            'vertex_lookup':{v:i for i,v in enumerate(raw['vertex_ids'])},
            'face_lookup':{v:i for i,v in enumerate(raw['face_ids'])}}


def _interpolate(point,mesh,positions,budget):
    support=uv._support(point,mesh,budget)
    ids=mesh['vertex_lookup']
    values=[budget.q(sum(w*positions[ids[vertex]][k]for vertex,w in support['sparse_vertex_weights'].items()))for k in range(3)]
    return values,support


def _cast(point,budget):
    result=[];errors=[]
    for x in point:
        budget.check('binary64_conversion')
        try:value=float(x)
        except(OverflowError,ValueError):_refuse('INVALID_COORDINATES','evaluated coordinate overflows binary64')
        if not math.isfinite(value):_refuse('INVALID_COORDINATES','nonfinite evaluated coordinate')
        result.append(value);errors.append(budget.q(F(value)-x))
    return {'coordinates_exact_cm':point,'coordinates_cm':result,
            'binary64_conversion_component_errors_cm':errors,
            'binary64_conversion_max_absolute_error_cm':max(map(abs,errors)),
            'binary64_conversion_observed':True}


def _compile(data,budget):
    required=('source','carrier','reference','coordinates_cm','samples','marks','relations','targets','previous_coordinates_cm','limits')
    uv._fields(data,required)
    source,carrier,reference=data['source'],data['carrier'],data['reference']
    uv._fields(reference,('mesh','coordinates_cm'))
    # No cached flag or supplied proof bypasses either full domain validation.
    material_uv=uv._build(source,carrier,data['samples'],data['marks'],data['relations'],budget)
    class ReferenceBudget:
        limits=budget.limits
        def check(self,phase):budget.check(phase)
        def take(self,key,count=1):
            budget.take('reference_'+key[len('source_'):]if key in('source_vertices','source_triangles')else key,count)
        def available(self,key,count):budget.available(key,count)
    reference_uv=uv._build(reference['mesh'],carrier,[],[],[],ReferenceBudget())
    sm,cm,rm=[_parsed(raw,budget)for raw in(source,carrier,reference['mesh'])]
    current=_positions(data['coordinates_cm'],len(cm['points']),budget,'candidate')
    fresh=_positions(reference['coordinates_cm'],len(rm['points']),budget,'fresh_reference')
    previous=None if data['previous_coordinates_cm']is None else _positions(data['previous_coordinates_cm'],len(cm['points']),budget,'previous_candidate')
    limits=_limits(data['limits'])
    patches=[];coverage={}
    for original in material_uv['source_carrier_intersections']:
        key=(original['source_face_id'],original['carrier_face_id'])
        coverage[key]=F(0)
        for rindex,triangle in enumerate(rm['triangles']):
            budget.take('pair_checks');poly=uv._clip(original['uv_polygon_cm'],triangle,budget)
            if len(poly)<3 or not uv._area(poly):continue
            budget.take('refinement_patches');area=budget.q(uv._area(poly));coverage[key]+=area
            sindex=sm['face_lookup'][key[0]];cindex=cm['face_lookup'][key[1]]
            patches.append({'source_face_id':key[0],'reference_face_id':reference['mesh']['face_ids'][rindex],
                'carrier_face_id':key[1],'uv_polygon_cm':poly,'area_cm2':area,
                'source_barycentric_weights':[uv._bary(p,sm['triangles'][sindex])for p in poly],
                'reference_barycentric_weights':[uv._bary(p,triangle)for p in poly],
                'carrier_barycentric_weights':[uv._bary(p,cm['triangles'][cindex])for p in poly]})
        if coverage[key]!=original['area_cm2']:_refuse('DOMAIN_COVERAGE','triple refinement does not cover source/carrier patch exactly')
    budget.take('targets',len(data['targets'])if type(data['targets'])is list else 0)
    if type(data['targets'])is not list:_refuse('INVALID_TARGETS','targets must be an explicit array')
    sample_lookup={r['id']:r for r in material_uv['samples']};target_ids=set();target_records=[]
    for raw in data['targets']:
        budget.check('target_binding');uv._fields(raw,('id','sample_id','target_cm','role'))
        identity=uv._identity(raw['id'])
        if identity in target_ids:_refuse('IDENTITY_COLLISION','target identities collide')
        target_ids.add(identity)
        if type(raw['sample_id'])is not str or raw['sample_id']not in sample_lookup or raw['role']not in('physical_stop','numerical_target'):
            _refuse('INVALID_TARGETS','target must bind an existing sample and explicit supported role')
        point=sample_lookup[raw['sample_id']]['exact_uv_cm']
        target=_positions([raw['target_cm']],1,budget,'target')[0]
        actual,support=_interpolate(point,cm,current,budget)
        cast=_cast(actual,budget)
        residual=[budget.q(x-y)for x,y in zip(actual,target)]
        float_residual=[budget.q(F(x)-y)for x,y in zip(cast['coordinates_cm'],target)]
        target_records.append({'id':identity,'sample_id':raw['sample_id'],'role':raw['role'],
            'target_exact_cm':target,'candidate_support':support,
            'residual_exact_cm':residual,'residual_binary64_cm':float_residual,
            'exact_target_satisfied':all(x==0 for x in residual),
            'binary64_target_satisfied':all(x==0 for x in float_residual),**cast})
    return {'data':data,'source_mesh':sm,'carrier_mesh':cm,'reference_mesh':rm,
            'current':current,'fresh':fresh,'previous':previous,'limits':limits,
            'material_uv':material_uv,'reference_uv':reference_uv,
            'patches':patches,'targets':target_records}


def _base(state):
    return {'discriminant':DISCRIMINANT,'version':1,'purpose':'TEST_ONLY','qualification':'NONE',
        'physical_mesh':False,'is_installable':False,'inputs':state['data'],
        'uv_qualification':'EXACT_SOURCE_REFERENCE_CARRIER_DOMAIN_COVERAGE',
        'constraints_3d':'NOT_QUALIFIED_RANK_TRACE_AND_COHORT_FEASIBILITY_NOT_PROVEN',
        'trajectory':'NOT_ASSESSED','contacts':'NOT_ASSESSED','simulation':'NOT_EXECUTED','fitting':'NOT_QUALIFIED',
        'source_vertex_bindings':state['material_uv']['source_vertex_bindings'],
        'samples':state['material_uv']['samples'],'assembly_marks':state['data']['marks'],
        'relations':state['data']['relations'],'physical_pins_added':[],
        'source_carrier_intersections':state['material_uv']['source_carrier_intersections'],
        'reference_carrier_intersections':state['reference_uv']['source_carrier_intersections'],
        'material_reference_carrier_patches':state['patches'],'target_observations':state['targets'],
        'external_source_references':state['material_uv']['external_source_references']}


def _hashes(state,budget):
    return {key:_hash(value,budget,key)for key,value in {
        'source':state['data']['source'],'carrier':state['data']['carrier'],
        'fresh_reference':state['data']['reference'],'candidate':state['data']['coordinates_cm'],
        'previous_candidate':state['data']['previous_coordinates_cm'],'limits':state['data']['limits'],'samples':state['data']['samples'],
        'marks':state['data']['marks'],'relations':state['data']['relations'],'targets':state['data']['targets'],
        'compiler_code':{'field':hashlib.sha256(Path(__file__).read_bytes()).hexdigest(),
                         'uv':hashlib.sha256(Path(uv.__file__).read_bytes()).hexdigest()}}.items()}


def _jacobian(triangle,positions,budget):
    a,b,c=triangle;x,y,z=positions
    e1=[b[k]-a[k]for k in range(2)];e2=[c[k]-a[k]for k in range(2)]
    determinant=budget.q(e1[0]*e2[1]-e2[0]*e1[1])
    return [[budget.q(((y[k]-x[k])*e2[1]-(z[k]-x[k])*e1[1])/determinant),
             budget.q((-(y[k]-x[k])*e2[0]+(z[k]-x[k])*e1[0])/determinant)]for k in range(3)]


def _psd(matrix,budget):
    determinant=budget.q(matrix[0][0]*matrix[1][1]-matrix[0][1]*matrix[1][0])
    return {'diagonal':[matrix[0][0],matrix[1][1]],'determinant':determinant,
            'satisfied':matrix[0][0]>=0 and matrix[1][1]>=0 and determinant>=0}


def _observe(state,budget):
    cm=state['carrier_mesh'];metrics=[]
    lower,upper=F(state['limits']['min_stretch'])**2,F(state['limits']['max_stretch'])**2
    for index,face in enumerate(cm['faces']):
        budget.take('metric_faces');budget.check('metric_gram')
        jac=_jacobian(cm['triangles'][index],[state['current'][i]for i in face],budget)
        gram=[[budget.q(sum(row[a]*row[b]for row in jac))for b in range(2)]for a in range(2)]
        low=[[gram[a][b]-(lower if a==b else 0)for b in range(2)]for a in range(2)]
        high=[[(upper if a==b else 0)-gram[a][b]for b in range(2)]for a in range(2)]
        lp,hp=_psd(low,budget),_psd(high,budget)
        metrics.append({'carrier_face_id':cm['raw']['face_ids'][index],'jacobian_exact':jac,
            'gram_exact':gram,'lower_psd':lp,'upper_psd':hp,'metric_bounds_met':lp['satisfied']and hp['satisfied']})
    observations=[];maximum=F(0);max_step=F(0);maximum_at=None;step_at=None
    limit=F(state['limits']['max_displacement_cm'])**2;step_limit=F(state['limits']['max_step_cm'])**2
    for index,patch in enumerate(state['patches']):
        for corner,point in enumerate(patch['uv_polygon_cm']):
            budget.take('patch_vertex_checks')
            c,support=_interpolate(point,cm,state['current'],budget)
            fresh,ref_support=_interpolate(point,state['reference_mesh'],state['fresh'],budget)
            sq=budget.q(sum((x-y)**2 for x,y in zip(c,fresh)))
            cast_c,cast_f=_cast(c,budget),_cast(fresh,budget)
            float_sq=budget.q(sum((F(x)-F(y))**2 for x,y in zip(cast_c['coordinates_cm'],cast_f['coordinates_cm'])))
            step_sq=float_step_sq=None
            if state['previous']is not None:
                previous,_=_interpolate(point,cm,state['previous'],budget);cast_p=_cast(previous,budget)
                step_sq=budget.q(sum((x-y)**2 for x,y in zip(c,previous)))
                float_step_sq=budget.q(sum((F(x)-F(y))**2 for x,y in zip(cast_c['coordinates_cm'],cast_p['coordinates_cm'])))
                if step_sq>max_step:max_step=step_sq;step_at=[index,corner]
            if sq>maximum:maximum=sq;maximum_at=[index,corner]
            observations.append({'patch_index':index,'corner_index':corner,'uv_cm':point,
                'candidate_support':support,'reference_support':ref_support,
                'displacement_squared_exact_cm2':sq,'displacement_squared_binary64_cm2':float_sq,
                'displacement_limit_met':sq<=limit and float_sq<=limit,
                'step_squared_exact_cm2':step_sq,'step_squared_binary64_cm2':float_step_sq,
                'step_limit_met':None if step_sq is None else step_sq<=step_limit and float_step_sq<=step_limit})
    violations=[]
    if any(not r['metric_bounds_met']for r in metrics):violations.append('FIELD_METRIC_BOUNDS')
    if any(not r['displacement_limit_met']for r in observations):violations.append('ORIGINAL_REFERENCE_DISPLACEMENT')
    if any(r['step_limit_met']is False for r in observations):violations.append('PREVIOUS_FIELD_STEP')
    if any(r['role']=='physical_stop'and(not r['exact_target_satisfied']or not r['binary64_target_satisfied'])for r in state['targets']):
        violations.append('PROVIDED_PHYSICAL_STOP_RESIDUAL')
    return {'method':'EXACT_AFFINE_JACOBIAN_GRAM_PSD_AND_CONVEX_PATCH_CORNER_DISTANCE',
        'limits':state['limits'],'limits_rational':{k:F(v)for k,v in state['limits'].items()},
        'epsilon_allowance':False,'carrier_face_metrics':metrics,'patch_corner_observations':observations,
        'max_displacement_squared_exact_cm2':maximum,'maximum_displacement_patch_corner':maximum_at,
        'max_step_squared_exact_cm2':None if state['previous']is None else max_step,
        'maximum_step_patch_corner':step_at,'step_assessed':state['previous']is not None,
        'target_observations':state['targets'],'violations':violations,
        'binary64_distance_scope':'OBSERVED_PATCH_VERTICES_NOT_A_CONTINUOUS_ROUNDED_FIELD_PROOF',
        'local_field_checks':'FAIL'if violations else'PASS_TEST_ONLY',
        'metric_scope':'PROVIDED_AFFINE_SURFACE_FIELD_ONLY_NOT_PHYSICAL_MESH',
        'constraints_3d':'NOT_QUALIFIED','trajectory':'NOT_ASSESSED'}


def _from_compiled(compiled,budget):
    if(type(compiled)is not dict or compiled.get('discriminant')!=DISCRIMINANT or
        compiled.get('status')!='COMPILED_TEST_ONLY'or type(compiled.get('inputs'))is not dict):
        _refuse('INVALID_CONTRACT','explicit material surface field compilation required')
    receipt=compiled.get('receipt')
    if type(receipt)is not dict or type(receipt.get('input_hashes'))is not dict:
        _refuse('INVALID_CONTRACT','input identities required; flags are not evidence')
    state=_compile(compiled['inputs'],budget)
    if _hashes(state,budget)!=receipt['input_hashes']:_refuse('REFERENCE_MUTATION','compiled input identities changed')
    return state


def _normalize_error(error):
    if not hasattr(error,'reason'):error.reason='INVALID_CONTRACT'
    error.qualification='NONE'
    error.status='INCOMPLETE'if error.reason in('DEADLINE_EXHAUSTED','BUDGET_EXHAUSTED')else'REFUSED'
    return error


def compile_material_surface_field(source,carrier,reference,coordinates_cm,*,samples=None,marks=None,
        relations=None,targets=None,previous_coordinates_cm=None,limits=None,budgets=None,
        deadline=None,clock=time.monotonic):
    """Compile a supplied free affine C field; preserve the complete fresh field."""
    data={'source':source,'carrier':carrier,'reference':reference,'coordinates_cm':coordinates_cm,
          'samples':[]if samples is None else samples,'marks':[]if marks is None else marks,
          'relations':[]if relations is None else relations,'targets':[]if targets is None else targets,
          'previous_coordinates_cm':previous_coordinates_cm,'limits':limits}
    originals=[data,budgets,deadline]
    try:
        copied,before,budget=_capture(originals,budgets,deadline,clock)
        state=_compile(copied[0],budget);result=_base(state);result['status']='COMPILED_TEST_ONLY'
        return _finish(result,originals,before,budget,_hashes(state,budget))
    except StudioError as error:raise _normalize_error(error)


def evaluate_material_field(compiled,requests=None,*,budgets=None,deadline=None,clock=time.monotonic):
    """Evaluate named existing samples/vertices or explicitly identified exact UVs."""
    originals=[compiled,requests,budgets,deadline]
    try:
        copied,before,budget=_capture(originals,budgets,deadline,clock)
        state=_from_compiled(copied[0],budget);requests=copied[1]
        sample_map={r['id']:r for r in state['material_uv']['samples']}
        if requests is None:requests=[{'id':sid,'sample_id':sid}for sid in sample_map]
        if type(requests)is not list:_refuse('INVALID_QUERY','queries must be explicit lists')
        budget.take('queries',len(requests));records=[];identities=set()
        for raw in requests:
            budget.check('query_binding')
            uv._fields(raw,('id',),('sample_id','source_vertex_id','uv_cm'))
            identity=uv._identity(raw['id'])
            if identity in identities:_refuse('IDENTITY_COLLISION','query identities collide')
            identities.add(identity)
            if len(set(raw)&{'sample_id','source_vertex_id','uv_cm'})!=1:
                _refuse('INVALID_QUERY','query needs exactly one explicit source binding')
            if 'sample_id'in raw:
                if type(raw['sample_id'])is not str or raw['sample_id']not in sample_map:_refuse('INVALID_QUERY','unknown material sample')
                point=sample_map[raw['sample_id']]['exact_uv_cm']
            elif 'source_vertex_id'in raw:
                lookup=state['source_mesh']['vertex_lookup']
                if type(raw['source_vertex_id'])is not str or raw['source_vertex_id']not in lookup:_refuse('INVALID_QUERY','unknown material source vertex')
                point=state['source_mesh']['points'][lookup[raw['source_vertex_id']]]
            else:
                if type(raw['uv_cm'])is not list or len(raw['uv_cm'])!=2:_refuse('INVALID_QUERY','explicit 2D material UV required')
                point=tuple(budget.q(uv._number(v,budget))for v in raw['uv_cm'])
            source_support=uv._support(point,state['source_mesh'],budget)
            current,carrier_support=_interpolate(point,state['carrier_mesh'],state['current'],budget)
            fresh,reference_support=_interpolate(point,state['reference_mesh'],state['fresh'],budget)
            records.append({'id':identity,'query':raw,'exact_uv_cm':point,
                'source_support':source_support,'carrier_support':carrier_support,'reference_support':reference_support,
                **_cast(current,budget),'fresh_reference_evaluation':_cast(fresh,budget)})
        result={'discriminant':DISCRIMINANT,'purpose':'TEST_ONLY','qualification':'NONE',
            'status':'EVALUATED_TEST_ONLY','evaluations':records,'physical_mesh':False,'is_installable':False,
            'constraints_3d':'NOT_QUALIFIED','trajectory':'NOT_ASSESSED'}
        return _finish(result,originals,before,budget,_hashes(state,budget))
    except StudioError as error:raise _normalize_error(error)


def observe_material_surface_field(compiled,*,budgets=None,deadline=None,clock=time.monotonic):
    """Observe all field metrics and budgets, with no constraint/product admission."""
    originals=[compiled,budgets,deadline]
    try:
        copied,before,budget=_capture(originals,budgets,deadline,clock)
        state=_from_compiled(copied[0],budget);observed=_observe(state,budget)
        result={'discriminant':DISCRIMINANT,'purpose':'TEST_ONLY','qualification':'NONE',
                'status':'OBSERVED_TEST_ONLY','observations':observed,'physical_mesh':False,'is_installable':False}
        return _finish(result,originals,before,budget,_hashes(state,budget))
    except StudioError as error:raise _normalize_error(error)


def validate_material_surface_field(compiled,*,budgets=None,deadline=None,clock=time.monotonic):
    """Validate only declared local field checks; never emit READY or qualification."""
    result=observe_material_surface_field(compiled,budgets=budgets,deadline=deadline,clock=clock)
    # The observation's checked return is the final operation; validation does
    # not mutate its receipt/content or create an extra untimed admission step.
    return result
