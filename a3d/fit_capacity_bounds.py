"""Exact piecewise-affine bounds for unary sewn source transverse paths.

The measured family is a single material segment between homologous points of
one permanent source seam. Closure adds zero material length. Bounds concern
flat nominal material at zero stretch, never all possible worn sleeve contours.
"""
import copy
import math

from .core import ROOT, StudioError, digest, inside, read_json, sha
from .fitting import path_inside
from .sewing import chain_lengths, edge_chain, sample_chain


def _cross(a,b):return a[0]*b[1]-a[1]*b[0]
def _sub(a,b):return [a[i]-b[i] for i in range(2)]
def _lerp(a,b,t):return [a[i]+t*(b[i]-a[i]) for i in range(2)]


def _roots(c0,c1,c2):
    scale=max(abs(c0),abs(c1),abs(c2),1e-30)
    if abs(c2)<=1e-14*scale:
        return [] if abs(c1)<=1e-14*scale else [-c0/c1]
    discriminant=c1*c1-4*c2*c0
    if discriminant<0:return []
    root=math.sqrt(discriminant)
    q=-.5*(c1+math.copysign(root,c1))
    return [-c1/(2*c2)] if abs(q)<=1e-30 else [q/c2,c0/q]


def _coverage(a0,a1,b0,b1,polygon):
    """Partition the continuous family at every boundary-vertex contact.

    Endpoints stay on their declared straight source boundary atoms. A chord's
    boundary-crossing topology can therefore change only when it contains an
    outline vertex, or at the atom boundaries already in the outer partition.
    Collinearity with each vertex is a quadratic in the local parameter. Check
    those critical paths and every open interval between them, not a fixed grid.
    """
    ad=_sub(a1,a0);bd=_sub(b1,b0);d0=_sub(b0,a0);dd=_sub(bd,ad)
    cuts={0.,1.}
    for point in polygon:
        c=_sub(point,a0)
        coefficients=(_cross(d0,c),_cross(dd,c)-_cross(d0,ad),-_cross(dd,ad))
        cuts.update(max(0.,min(1.,t)) for t in _roots(*coefficients) if -1e-12<=t<=1+1e-12)
    values=sorted(cuts);checked=sorted(set(values+[(a+b)/2 for a,b in zip(values,values[1:])]))
    for parameter in checked:
        a,b=_lerp(a0,a1,parameter),_lerp(b0,b1,parameter)
        if not path_inside(a,b,polygon):
            raise StudioError('Transverse source family leaves material inside a continuous parameter interval')
    return {'critical_local_parameters':values,'checked_paths':len(checked),
            'proof':'BOUNDARY_VERTEX_CONTACT_PARTITION_AND_EVERY_OPEN_INTERVAL'}


def transverse_capacity_bound(compiled,piece_id):
    """Measure only the complete family of one compatible unary source seam."""
    before=digest(compiled);row=compiled.get('textiles',{}).get(piece_id)
    if (row is None or not row.get('source_geometry') or row['semantics'].get('role') not in ('sleeve','cuff') or
            row['semantics'].get('side') not in ('left','right')):
        raise StudioError('Transverse capacity bound requires one declared source sleeve or cuff')
    piece=row['source_geometry'];polygon=piece['vertices']
    if (not polygon or any(not isinstance(p,list) or len(p)!=2 or any(type(v) not in (int,float) or not math.isfinite(v) for v in p) for p in polygon)):
        raise StudioError('Transverse capacity needs finite metric source coordinates')
    from .board_contract import simple_polygon
    if not simple_polygon(polygon):raise StudioError('Transverse capacity requires a simple source material outline')
    seams=[link for link in compiled['links'] if link['piece_a']==link['piece_b']==piece_id and link['kind']=='permanent']
    if (len(seams)!=1 or seams[0]['orientation']!='reverse' or
            {seams[0]['edge_a'],seams[0]['edge_b']}!={'underarm-front','underarm-back'} or
            seams[0]['component_id']!=row['component_id'] or seams[0]['source_ref']!=row['package_source_ref']):
        raise StudioError('Transverse capacity requires exactly one compatible permanent unary underarm source seam')
    seam=seams[0];ids_a,a,_=edge_chain(piece,seam['edge_a']);ids_b,b,_=edge_chain(piece,seam['edge_b'])
    if set(ids_a)&set(ids_b):raise StudioError('Unary transverse closure cannot reuse a source endpoint or boundary atom')
    b=list(reversed(b));lengths_a=chain_lengths(a);lengths_b=chain_lengths(b)
    breaks=sorted({*(s/lengths_a[-1] for s in lengths_a),*(s/lengths_b[-1] for s in lengths_b)})
    cells=[];candidates=[]
    for lo,hi in zip(breaks,breaks[1:]):
        a0,a1=sample_chain(a,lo),sample_chain(a,hi);b0,b1=sample_chain(b,lo),sample_chain(b,hi)
        proof=_coverage(a0,a1,b0,b1,polygon);d0=_sub(b0,a0);delta=_sub(_sub(b1,a1),d0)
        squared=sum(x*x for x in delta);local=max(0.,min(1.,-sum(x*y for x,y in zip(d0,delta))/squared)) if squared>1e-24 else 0.
        for t in (0.,local,1.):
            aa,bb=_lerp(a0,a1,t),_lerp(b0,b1,t)
            candidates.append({'fraction_a':lo+t*(hi-lo),'fraction_b':1-(lo+t*(hi-lo)),
                               'a_uv_cm':aa,'b_uv_cm':bb,'capacity_cm':math.dist(aa,bb)})
        cells.append({'fraction_domain':[lo,hi],'a_endpoints_uv_cm':[a0,a1],'b_endpoints_uv_cm':[b0,b1],
                      'minimum_local_parameter':local,'inside_material':proof})
    minimum=min(candidates,key=lambda item:(item['capacity_cm'],item['fraction_a']))
    maximum=max(candidates,key=lambda item:(item['capacity_cm'],-item['fraction_a']))
    if minimum['capacity_cm']<=1e-7:raise StudioError('Closed transverse source path collapses somewhere in its declared domain')
    result={'version':1,'status':'NOMINAL_TRANSVERSE_CAPACITY_BOUND','piece_id':piece_id,'component_id':row['component_id'],
        'role':row['semantics']['role'],'side':row['semantics']['side'],'layer':row['semantics']['layer'],
        'package_ref':copy.deepcopy(row['package_source_ref']),'source_geometry_sha256':digest(piece),
        'source_seam':copy.deepcopy(seam),'parameter_domain':[0.,1.],'parameterization':'NORMALIZED_SOURCE_EDGE_ARCLENGTH',
        'source_seam_edge_arclengths_cm':[lengths_a[-1],lengths_b[-1]],'native_seam_alignment':'NOT_OBSERVED',
        'breakpoints':breaks,'cells':cells,'minimum':minimum,'maximum':maximum,
        'minimum_capacity_cm':minimum['capacity_cm'],'maximum_capacity_cm':maximum['capacity_cm'],
        'bound_proof':'AFFINE_ENDPOINT_DIFFERENCE_PER_CELL_CONVEX_NORM_MAXIMUM_AT_CELL_ENDPOINTS',
        'minimum_proof':'CLAMPED_ANALYTICAL_MINIMUM_OF_AFFINE_DIFFERENCE_NORM',
        'loop':'ONE_SOURCE_MATERIAL_SEGMENT_CLOSED_BY_ONE_PERMANENT_UNARY_SOURCE_JOIN',
        'assumed_material_strain':0.,'material_state':'FLAT_SOURCE_NOMINAL_ZERO_STRETCH',
        'source_cut_allowance_used':False,'bounding_box_used':False,'layers_summed':False,
        'full_body_path_homology':'NOT_QUALIFIED','worn_girth':'NOT_MEASURED','physical_dressing':'NOT_EXECUTED',
        'fitting':'NOT_EXECUTED','acceptance':'NOT_GRANTED','source_changed':False}
    if digest(compiled)!=before:raise StudioError('Transverse capacity measurement changed its source compilation')
    result['cache_key']=digest(result);return result


def compare_body_section(bound,section):
    """A nominal geometric signal, without anatomical or physical admission."""
    if section.get('status')!='MEASURED' or section.get('ok') is not True:
        raise StudioError('Capacity signal needs an actually measured canonical skin section')
    body=section['girth_cm'];curve=section['curve_cm']
    if (type(body) not in (int,float) or not math.isfinite(body) or body<=0 or
            abs(sum(math.dist(a,b) for a,b in zip(curve,curve[1:]+curve[:1]))-body)>1e-7):
        raise StudioError('Capacity signal skin girth differs from its source contour')
    return {'scope':'NOMINAL_TRANSVERSE_CAPACITY_BOUND','body_section_id':section['id'],'body_girth_cm':body,
            'nominal_source_maximum_cm':bound['maximum_capacity_cm'],
            'nominal_maximum_minus_body_cm':bound['maximum_capacity_cm']-body,
            'signal':'BODY_SECTION_EXCEEDS_NOMINAL_TRANSVERSE_MAXIMUM' if body>bound['maximum_capacity_cm'] else 'NOMINAL_BOUND_NOT_EXCEEDED',
            'homology':'CONDITIONAL_SOURCE_TRANSVERSE_FAMILY_ONLY','material_strain_assumption':0.,
            'numeric_ease_target':'NOT_DEFINED','physical_impossibility':'NOT_ESTABLISHED','fitting':'NOT_EXECUTED','acceptance':'NOT_GRANTED'}


def project_capacity_bounds(project,compiled_path,body_policy_path=None,body_supplement_ref=None):
    from .production_dossier import compile_project_dossier
    compiled_file=inside(project.root,compiled_path);compiled=read_json(compiled_file)
    source=compiled['source_ref'];metadata=compiled['specification_source_ref']
    if (sha(inside(project.root,source['path']))!=source['sha256'] or
            sha(inside(project.root,metadata['path']))!=metadata['sha256'] or
            compile_project_dossier(project,source['path'],metadata['path'])!=compiled):
        raise StudioError('Transverse capacity requires the exact current recompiled source dossier')
    bounds=[transverse_capacity_bound(compiled,pid) for pid,row in sorted(compiled['textiles'].items())
            if row['semantics']['role'] in ('sleeve','cuff')]
    signals=[];region_evidence=None
    if (body_policy_path is None)!=(body_supplement_ref is None):raise StudioError('Capacity signals require both exact body policy and supplement')
    if body_policy_path is not None:
        from .body_region_sections import body_region_descriptor
        descriptor=body_region_descriptor(project,body_policy_path,body_supplement_ref)
        region_evidence={key:copy.deepcopy(descriptor[key]) for key in ('identity','specification_ref','supplement_ref','native_body_origin')}
        for bound in bounds:
            if bound['role']!='sleeve':continue
            found=descriptor['sections'].get('upper.'+bound['side']+'.section.1')
            if (found is None or found['region']['side']!=bound['side'] or found['region']['domain']!='SHOULDER_TO_ELBOW_ONLY' or
                    found['section']['parameter']!=.5):raise StudioError('Capacity proposal needs the actual declared middle upper-arm source section')
            signals.append(dict(compare_body_section(bound,found['section']),piece_id=bound['piece_id']))
    result={'version':1,'status':'NOMINAL_CAPACITY_PROPOSAL','compiled_ref':{'path':compiled_path,'sha256':sha(compiled_file)},
            'dossier_ref':source,'metadata_ref':metadata,'bounds':bounds,'body_region_evidence':region_evidence,'signals':signals,
            'numeric_ease_targets':'NOT_DEFINED','design_variant':'NOT_CREATED','body_changed':False,'patterns_changed':False,
            'fitting':'NOT_EXECUTED','physical_impossibility':'NOT_ESTABLISHED','acceptance':'NOT_GRANTED'}
    result['code_sha256']={name:sha(ROOT/('a3d/'+name+'.py')) for name in ('fit_capacity_bounds','fitting','sewing','board_contract')}
    result['cache_key']=digest(result);return result
