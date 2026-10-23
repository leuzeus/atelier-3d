"""Portable exact interpolated HARD rows and separate IEEE target observations.

No optimizer, pins, metric admission or production consumer is provided here.
"""
import hashlib
import time
from fractions import Fraction as F
from pathlib import Path

from . import material_sample_carrier as uv
from . import material_surface_field as field
from .core import StudioError


DISCRIMINANT='MATERIAL_SURFACE_CONSTRAINTS_V1'
_EXTRA={'max_domains':8,'max_constraint_relations':64,'max_physical_stops':64,
        'max_numerical_targets':256,'max_hard_rows':256,'max_unknown_nodes':256,
        'max_constraint_coefficients':10000,'max_matrix_entries':65536,
        'max_elimination_operations':200000,'max_certificate_terms':50000}
_DEFAULTS={**field._DEFAULTS,**_EXTRA}
_HARD={**field._HARD,**_EXTRA}


def _refuse(reason,detail):
    field._refuse(reason,'constraints: '+detail)


class _Budget(field._Budget):
    """All domains use one clock/counter ledger, including dependency work."""
    def __init__(self,values,deadline,clock):
        # The first clock call precedes any inspection of caller budgets.
        super().__init__(None,deadline,clock)
        if values is None:values={}
        if(type(values)is not dict or len(values)>len(_DEFAULTS)or
           any(type(k)is not str or len(k)>128 for k in values)or set(values)-set(_DEFAULTS)):
            _refuse('INVALID_BUDGET','unknown or non-native shared budget')
        self.limits={**_DEFAULTS,**values}
        for key,value in self.limits.items():
            self.check('constraint_budget_capture')
            kind=type(value)in(int,float)if key=='max_seconds'else type(value)is int
            if not kind or not field._finite(value)or not 0<value<=_HARD[key]:
                _refuse('INVALID_BUDGET','invalid bounded value for '+key)
        self.deadline=min(self.start+self.limits['max_seconds'],deadline)if deadline is not None else self.start+self.limits['max_seconds']
        self.check('constraint_before_capture')


def _capture(originals,budgets,deadline,clock):
    budget=_Budget(budgets,deadline,clock)
    copied=field._snapshot(originals,budget)
    before=field._hash(copied,budget,'constraint_snapshot')
    if field._hash(originals,budget,'constraint_original')!=before:
        _refuse('REFERENCE_MUTATION','inputs changed during capture')
    return copied,before,budget


def _sample(state,identity):
    uv._identity(identity)
    matches=[s for s in state['material_uv']['samples']if s['id']==identity]
    if not matches:_refuse('INVALID_SAMPLE','an existing material sample is required')
    return matches[0]


def _binding(states,domain,identity,budget):
    uv._identity(domain)
    if domain not in states:_refuse('MISSING_DOMAIN','a supplied validated field is required')
    state=states[domain];sample=_sample(state,identity)
    point=sample['exact_uv_cm']
    current,support=field._interpolate(point,state['carrier_mesh'],state['current'],budget)
    fresh,fresh_support=field._interpolate(point,state['reference_mesh'],state['fresh'],budget)
    return {'domain_id':domain,'sample_id':identity,'exact_uv_cm':point,
        'source_identity':sample['source_identity'],'carrier_support':support,
        'fresh_support':fresh_support,'fresh_exact_cm':fresh,'current_exact_cm':current}


def _coefficients(binding,sign,budget):
    return {(binding['domain_id'],node):budget.q(sign*weight)
            for node,weight in binding['carrier_support']['sparse_vertex_weights'].items()if weight}


def _row(identity,role,bindings,rhs,states,budget):
    coefficients={}
    for binding,sign in bindings:
        for key,value in _coefficients(binding,sign,budget).items():
            coefficients[key]=budget.q(coefficients.get(key,F(0))+value)
    coefficients={key:value for key,value in coefficients.items()if value}
    budget.take('constraint_coefficients',len(coefficients))
    residual=[]
    for axis in range(3):
        value=F(0)
        for (domain,node),weight in coefficients.items():
            state=states[domain];index=state['carrier_mesh']['vertex_lookup'][node]
            value=budget.q(value+budget.q(weight*state['current'][index][axis]))
        residual.append(budget.q(value-rhs[axis]))
    return {'row_id':identity,'role':role,'strength':'HARD'if role in('permanent','physical_stop')else'SOFT_OBSERVATION',
        'coefficients':[{'domain_id':d,'node_id':n,'weight':w}for(d,n),w in sorted(coefficients.items())],
        'rhs_exact_cm':rhs,'provided_field_residual_exact_cm':residual,
        'provided_field_row_satisfied':all(v==0 for v in residual),
        'sample_bindings':[binding for binding,_ in bindings]}


def _check_local_declarations(raw,states,owner_bindings,budget):
    """A global relation cannot promote a closure or invent an existing edge link."""
    for side,owner in enumerate(raw['owners']):
        state=states[owner['domain_id']]
        records=[r for r in state['data']['relations']if r['id']==raw['id']]
        if len(records)!=1:_refuse('UNDECLARED_RELATION','relation must exist in each supplied local field')
        local=records[0]
        if(local['kind']!=raw['kind']or local['orientation']!=raw['orientation']):
            _refuse('RELATION_PROVENANCE','kind/orientation differs from the local source declaration')
        for ordinal,(declared,global_owner)in enumerate(zip(local['owners'],raw['owners'])):
            budget.check('constraint_relation_provenance')
            other=states[global_owner['domain_id']]
            if(declared['source_id']!=global_owner['domain_id']or declared['edge_id']!=global_owner['edge_id']or
                len(declared['samples'])!=len(global_owner['samples'])):
                _refuse('RELATION_PROVENANCE','owner or source partition differs')
            if declared['source_id']!=state['data']['source']['id']:
                if(declared.get('source_sha256')!=global_owner['source_sha256']or
                   declared.get('source_vertex_ids')!=other['data']['source']['edges'].get(global_owner['edge_id'])):
                    _refuse('RELATION_PROVENANCE','external source hash/chain differs from the actual supplied source')
            for entry,given,binding in zip(declared['samples'],global_owner['samples'],owner_bindings[ordinal]):
                budget.check('constraint_declared_partition')
                if(entry['sample_id']!=given['sample_id']or uv._fraction(entry['fraction'],budget)!=uv._fraction(given['fraction'],budget)):
                    _refuse('RELATION_PROVENANCE','sample identity or exact fraction differs')
                if declared['source_id']!=state['data']['source']['id']:
                    chain=other['data']['source']['edges'][global_owner['edge_id']]
                    traversal=list(reversed(chain))if ordinal==1 and raw['orientation']=='reverse'else chain
                    segment=entry['source_segment_vertex_ids']
                    if segment not in [traversal[i:i+2]for i in range(len(traversal)-1)]:
                        _refuse('RELATION_PROVENANCE','external segment does not follow the actual boundary')
                    a,b=[other['source_mesh']['points'][other['source_mesh']['vertex_lookup'][v]]for v in segment]
                    t=uv._fraction(entry['source_segment_parameter'],budget)
                    point=tuple(budget.q(a[k]+budget.q(t*(b[k]-a[k])))for k in range(2))
                    if point!=tuple(binding['exact_uv_cm']):
                        _refuse('RELATION_PROVENANCE','external declared segment target differs from the actual sample')


def _relations(raw,states,budget):
    if type(raw)is not list:_refuse('INVALID_RELATION','relations must be an explicit array')
    budget.take('constraint_relations',len(raw));seen=set();occupied=set();rows=[];records=[]
    for relation in sorted(raw,key=lambda r:r['id']if type(r)is dict and type(r.get('id'))is str else''):
        budget.check('constraint_relation')
        uv._fields(relation,('id','kind','orientation','owners'));identity=uv._identity(relation['id'])
        if identity in seen:_refuse('IDENTITY_COLLISION','relation identities collide')
        seen.add(identity)
        if(relation['kind']not in('permanent','closure','detachable')or relation['orientation']not in('forward','reverse')or
           type(relation['owners'])is not list or len(relation['owners'])!=2):
            _refuse('INVALID_RELATION','explicit kind, orientation and two actual owners required')
        bindings=[];partitions=[]
        for side,owner in enumerate(relation['owners']):
            uv._fields(owner,('domain_id','edge_id','source_sha256','samples'))
            domain=uv._identity(owner['domain_id']);edge=uv._identity(owner['edge_id'])
            if domain not in states:_refuse('MISSING_DOMAIN','relationship domain is not supplied')
            state=states[domain]
            if owner['source_sha256']!=field._hash(state['data']['source'],budget,'constraint_source_identity'):
                _refuse('RELATION_PROVENANCE','explicit source hash does not match the actual field')
            if type(owner['samples'])is not list or len(owner['samples'])<2:
                _refuse('INVALID_RELATION','explicit full endpoint partition required')
            budget.take('relation_owners',len(owner['samples']))
            fractions=[];bound=[];positions=[];identities=set()
            for entry in owner['samples']:
                uv._fields(entry,('sample_id','fraction'))
                sid=uv._identity(entry['sample_id'])
                if sid in identities:_refuse('IDENTITY_COLLISION','owner repeats a sample identity')
                identities.add(sid);fractions.append(uv._fraction(entry['fraction'],budget))
                item=_binding(states,domain,sid,budget);bound.append(item)
                positions.append(uv._walk(item['exact_uv_cm'],state['source_mesh'],edge,budget,side==1 and relation['orientation']=='reverse'))
            if(fractions[0]!=0 or fractions[-1]!=1 or any(a>=b for a,b in zip(fractions,fractions[1:]))or
               positions[0][0]!=0 or positions[-1][0]!=positions[-1][1]or any(a[0]>=b[0]for a,b in zip(positions,positions[1:]))):
                _refuse('INVALID_RELATION','partition contradicts its exact boundary orientation')
            if relation['kind']=='permanent':
                chain=state['data']['source']['edges'][edge]
                edges={(domain,tuple(sorted((a,b))))for a,b in zip(chain,chain[1:])}
                if edges&occupied:_refuse('AMBIGUOUS_RELATION','boundary assigned to two permanent relations')
                occupied.update(edges)
            bindings.append(bound);partitions.append(fractions)
        if partitions[0]!=partitions[1]:_refuse('INVALID_RELATION','paired fractions differ; no partition is invented')
        _check_local_declarations(relation,states,bindings,budget)
        if relation['kind']=='permanent':
            for fraction,a,b in zip(partitions[0],bindings[0],bindings[1]):
                budget.take('hard_rows')
                rows.append(_row(('seam',identity,str(fraction)),'permanent',[(a,F(1)),(b,F(-1))],[F(0)]*3,states,budget))
        records.append({'relation':relation,'geometry_binding_checked':True,
            'hard_rows_created':len(partitions[0])if relation['kind']=='permanent'else 0,
            'normalized_arc_measurement':'DECLARED_FRACTIONS_ONLY_NOT_MEASURED'})
    # Any provided-to-provided permanent declaration must be represented.
    uncovered=[]
    for domain,state in states.items():
        for r in state['data']['relations']:
            if r['id']not in seen:
                if r['kind']=='permanent'and all(o['source_id']in states for o in r['owners']):
                    _refuse('MISSING_RELATION','a supplied-domain permanent relation is absent')
                uncovered.append({'domain_id':domain,'relation_id':r['id'],'kind':r['kind'],'status':'NOT_COMPILED_EXTERNAL_OR_NONPERMANENT'})
    return rows,records,sorted(uncovered,key=lambda r:(r['domain_id'],r['relation_id']))


def _targets(raw,role,states,budget):
    if type(raw)is not list:_refuse('INVALID_TARGETS','targets/stops must be explicit arrays')
    budget.take('physical_stops'if role=='physical_stop'else'numerical_targets',len(raw))
    seen=set();rows=[]
    for target in sorted(raw,key=lambda r:r['id']if type(r)is dict and type(r.get('id'))is str else''):
        budget.check('constraint_target_binding')
        uv._fields(target,('id','domain_id','sample_id'),()if role=='physical_stop'else('target_cm',))
        if role!='physical_stop'and 'target_cm'not in target:_refuse('INVALID_TARGETS','explicit IEEE numerical target required')
        identity=uv._identity(target['id'])
        if identity in seen:_refuse('IDENTITY_COLLISION','target identities collide within their role')
        seen.add(identity);binding=_binding(states,target['domain_id'],target['sample_id'],budget)
        rhs=binding['fresh_exact_cm']if role=='physical_stop'else field._positions([target['target_cm']],1,budget,'soft_numerical_target')[0]
        if role=='physical_stop':budget.take('hard_rows')
        row=_row(('stop'if role=='physical_stop'else'target',identity),role,[(binding,F(1))],rhs,states,budget)
        row['rhs_origin']='COMPLETE_FRESH_FIELD_AT_EXACT_MATERIAL_SUPPORT'if role=='physical_stop'else'EXPLICIT_BINARY64_TARGET_SOFT_ONLY'
        if role!='physical_stop':
            row['target_cm']=target['target_cm'];row['conversion_observation']=field._cast(binding['current_exact_cm'],budget)
            row['binary64_residual_exact_cm']=[budget.q(F(value)-rhs[k])for k,value in enumerate(row['conversion_observation']['coordinates_cm'])]
        rows.append(row)
    return rows


def _op(value,budget):
    budget.take('elimination_operations')
    return budget.q(value)


def _reduce(matrix,lineage,column_count,budget):
    pivot_row=0;pivots=[]
    for col in range(column_count):
        budget.check('constraint_pivot_search')
        selected=None
        for index in range(pivot_row,len(matrix)):
            budget.take('elimination_operations')
            if matrix[index][col]:selected=index;break
        if selected is None:continue
        matrix[pivot_row],matrix[selected]=matrix[selected],matrix[pivot_row]
        lineage[pivot_row],lineage[selected]=lineage[selected],lineage[pivot_row]
        scale=matrix[pivot_row][col]
        matrix[pivot_row]=[_op(v/scale,budget)for v in matrix[pivot_row]]
        lineage[pivot_row]={key:_op(v/scale,budget)for key,v in lineage[pivot_row].items()}
        for index,row in enumerate(matrix):
            if index==pivot_row or not row[col]:continue
            factor=row[col]
            matrix[index]=[_op(v-_op(factor*w,budget),budget)for v,w in zip(row,matrix[pivot_row])]
            for key,value in lineage[pivot_row].items():
                lineage[index][key]=_op(lineage[index].get(key,F(0))-_op(factor*value,budget),budget)
                if not lineage[index][key]:del lineage[index][key]
        pivots.append(col);pivot_row+=1
        if pivot_row==len(matrix):break
    return pivots


def _certificate(rows,columns,requested,budget):
    if not requested:return {'status':'NOT_REQUESTED','qualification':'NONE','scope':'EXPLICIT_HARD_ROWS_ONLY'}
    count=len(columns);budget.take('matrix_entries',len(rows)*(count+3))
    lookup={key:i for i,key in enumerate(columns)};matrix=[];lineage=[]
    for index,row in enumerate(rows):
        budget.check('constraint_matrix_assembly');vector=[F(0)]*count
        for coefficient in row['coefficients']:
            vector[lookup[(coefficient['domain_id'],coefficient['node_id'])]]=coefficient['weight']
        matrix.append(vector+list(row['rhs_exact_cm']));lineage.append({index:F(1)})
    pivots=_reduce(matrix,lineage,count,budget)
    contradictions=[]
    for index,row in enumerate(matrix):
        budget.check('constraint_compatibility')
        if not any(row[:count])and any(row[count:]):
            budget.take('certificate_terms',len(lineage[index]))
            contradictions.append({'zero_lhs':True,'nonzero_rhs_exact_cm':row[count:],
                'original_row_combination':[{'row_id':rows[i]['row_id'],'coefficient':v}for i,v in sorted(lineage[index].items())]})
    rref=matrix
    budget.take('matrix_entries',(len(matrix)-len(pivots))*3)
    remaining=[list(r[count:])for r in matrix[len(pivots):]]
    remainder_lineage=[dict(item)for item in lineage[len(pivots):]]
    extra_rank=len(_reduce(remaining,remainder_lineage,3,budget))
    combinations=[]
    for items in lineage:
        budget.take('certificate_terms',len(items))
        combinations.append([{'row_id':rows[i]['row_id'],'coefficient':v}for i,v in sorted(items.items())])
    return {'status':'COMPATIBLE_EXACT_LINEAR_MODEL'if not contradictions else'INCOMPATIBLE_EXPLICIT_HARD_ROWS',
        'qualification':'NONE','scope':'EXPLICIT_HARD_ROWS_ONLY_NOT_PATTERN_OR_METRIC',
        'rank_A':len(pivots),'rank_augmented':len(pivots)+extra_rank,'unknown_nodes':count,'hard_row_count':len(rows),
        'pivot_columns':pivots,'rref_augmented_rows':rref,'row_combinations':combinations,
        'contradictions':contradictions,'provided_field_satisfies_hard':all(r['provided_field_row_satisfied']for r in rows),
        'numerical_targets_in_elimination':False,'pattern_impossibility':False}


def compile_material_surface_constraints(fields,relations,physical_stops,numerical_targets,*,
        certify_hard=True,budgets=None,deadline=None,clock=time.monotonic):
    """Revalidate supplied fields once; compile exact rows, never optimize/admit."""
    data={'fields':fields,'relations':relations,'physical_stops':physical_stops,
          'numerical_targets':numerical_targets,'certify_hard':certify_hard}
    originals=[data,budgets,deadline]
    try:
        copied,before,budget=_capture(originals,budgets,deadline,clock);data=copied[0]
        if type(data['fields'])is not dict or type(data['certify_hard'])is not bool:
            _refuse('INVALID_CONTRACT','fields object and explicit certification boolean required')
        budget.take('domains',len(data['fields']))
        if not data['fields']:_refuse('MISSING_DOMAIN','at least one supplied domain is required')
        states={};identities={}
        for domain,compiled in sorted(data['fields'].items()):
            budget.check('constraint_domain_revalidation');uv._identity(domain)
            state=field._from_compiled(compiled,budget)
            if state['data']['source']['id']!=domain:_refuse('DOMAIN_IDENTITY','domain ID must be its actual material source ID')
            states[domain]=state;identities[domain]=field._hashes(state,budget)
        rows,relation_records,uncovered=_relations(data['relations'],states,budget)
        rows+=_targets(data['physical_stops'],'physical_stop',states,budget)
        soft=_targets(data['numerical_targets'],'numerical_target',states,budget)
        rows.sort(key=lambda r:r['row_id']);soft.sort(key=lambda r:r['row_id'])
        columns=sorted((domain,node)for domain,state in states.items()for node in state['data']['carrier']['vertex_ids'])
        budget.take('unknown_nodes',len(columns))
        certificate=_certificate(rows,columns,data['certify_hard'],budget)
        signature={'columns':columns,'hard_rows':[
            {'row_id':r['row_id'],'coefficients':[(c['domain_id'],c['node_id'],str(c['weight']))for c in r['coefficients']],
             'rhs':[str(v)for v in r['rhs_exact_cm']]}for r in rows]}
        system_sha=field._hash(signature,budget,'constraint_system')
        result={'discriminant':DISCRIMINANT,'version':1,'purpose':'TEST_ONLY','qualification':'NONE',
            'status':'COMPILED_TEST_ONLY','physical_mesh':False,'is_installable':False,'inputs':data,
            'domain_identities':identities,'hard_rows':rows,'numerical_target_observations':soft,
            'unknown_nodes':[{'domain_id':d,'node_id':n}for d,n in columns],
            'hard_system_sha256':system_sha,'certificate':certificate,'relations':relation_records,
            'uncompiled_declared_relations':uncovered,'physical_pins_added':[],
            'domain_revalidation_count':{d:1 for d in states},'shared_work_ledger':True,
            'dependency_validation':'REVALIDATED_PER_CALL_TEST_ONLY',
            'metric':'NOT_ASSESSED','displacement_limits':'PRESERVED_NOT_REASSESSED',
            'twelve_bars':'NOT_ASSESSED','traces':'NOT_ASSESSED','lengths':'NOT_ASSESSED','trajectory':'NOT_ASSESSED',
            'contacts':'NOT_ASSESSED','cloth':'NOT_EXECUTED','fitting':'NOT_QUALIFIED'}
        hashes={'domains':identities,'hard_system':system_sha,'constraint_code':hashlib.sha256(Path(__file__).read_bytes()).hexdigest()}
        return field._finish(result,originals,before,budget,hashes)
    except StudioError as error:raise field._normalize_error(error)
