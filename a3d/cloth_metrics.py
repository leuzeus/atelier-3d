"""Common source-UV cloth metrics. Geometry evidence is not physical approval.

The singular values of the 3-by-2 deformation gradient measure in-plane strain
independently of rigid rotation. Positions alone cannot identify an isolated
face's material-side inversion: oriented source correspondence and topology are
checked instead. Dihedral bending is reported separately without a new limit.
"""
import copy
import math

from .core import StudioError, digest

METRIC_VERSION = 2
VALIDATOR_VERSION = 'cloth-metrics/2'
METRIC_SCOPE = 'SOURCE_UV_PRINCIPAL_STRAIN_AREA_ORIENTED_TOPOLOGY_AND_SEPARATE_BENDING'


def _cross(a, b):
    return [a[1]*b[2]-a[2]*b[1], a[2]*b[0]-a[0]*b[2], a[0]*b[1]-a[1]*b[0]]


def _normal(points):
    points = [list(p)+[0.] if len(p)==2 else p for p in points]
    return _cross([points[1][k]-points[0][k] for k in range(3)],
                  [points[2][k]-points[0][k] for k in range(3)])


def triangle_metrics(points):
    edges = [math.dist(a, b) for a, b in zip(points, points[1:]+points[:1])]
    normal = _normal(points)
    area = math.sqrt(sum(x*x for x in normal))/2
    if min(edges) < 1e-12:
        return {'area_cm2': area, 'min_angle_degrees': 0., 'aspect_ratio': None, 'edges_cm': edges}
    a, b, c = edges
    angle = min(math.degrees(math.acos(max(-1., min(1., (x*x+y*y-z*z)/(2*x*y)))))
                for x, y, z in ((a, b, c), (b, c, a), (c, a, b)))
    return {'area_cm2': area, 'min_angle_degrees': angle,
            'aspect_ratio': max(edges)**2*math.sqrt(3)/(4*area) if area > 1e-12 else None,
            'edges_cm': edges}


def principal_stretches(source, placed):
    x1, y1 = (source[1][k]-source[0][k] for k in range(2))
    x2, y2 = (source[2][k]-source[0][k] for k in range(2))
    determinant = x1*y2-x2*y1
    if abs(determinant) < 1e-12:
        return None
    e1, e2 = [[placed[j][k]-placed[0][k] for k in range(3)] for j in (1, 2)]
    a = [(e1[k]*y2-e2[k]*y1)/determinant for k in range(3)]
    b = [(-e1[k]*x2+e2[k]*x1)/determinant for k in range(3)]
    xx, yy, xy = sum(x*x for x in a), sum(x*x for x in b), sum(x*y for x, y in zip(a, b))
    high2 = (xx+yy+math.hypot(xx-yy, 2*xy))/2
    # det(F^T F)=|a cross b|^2 avoids subtracting nearly equal eigenvalues.
    determinant2 = sum(x*x for x in _cross(a, b))
    return [math.sqrt(max(0., determinant2/high2)) if high2 else 0., math.sqrt(max(0., high2))]


def distribution(values):
    if not values:
        return {'count': 0, 'min': None, 'median': None, 'p95': None, 'max': None, 'mean': None, 'coefficient_of_variation': None}
    ordered = sorted(values); mean = sum(values)/len(values)
    return {'count': len(values), 'min': ordered[0], 'median': ordered[(len(values)-1)//2],
        'p95': ordered[min(len(values)-1, int(.95*(len(values)-1)))], 'max': ordered[-1],
        'mean': mean, 'coefficient_of_variation': math.sqrt(sum((x-mean)**2 for x in values)/len(values))/mean if mean else None}


def face_sources(payload):
    """Return distinct UV islands and unambiguous face ownership after unions."""
    faces, rest = payload['faces'], payload['rest_cm']
    stored = payload.get('source_rest_triangles_cm')
    pieces = payload.get('source_face_pieces')
    source_ids = payload.get('source_face_vertex_ids')
    for name, value in (('source_rest_triangles_cm', stored), ('source_face_pieces', pieces),
                        ('source_face_vertex_ids', source_ids)):
        if value is not None and len(value) != len(faces):
            raise StudioError('Source face binding does not cover every face: '+name)
    if payload.get('rest_mode') == 'assembled_3d' and stored is None:
        raise StudioError('Continuous cloth requires immutable source UV per face; 3D rest cannot replace it')
    memberships = {}
    for pid, panel in payload.get('panels', {}).items():
        for index in panel['indices']:
            memberships.setdefault(index, set()).add(pid)
    triangles, owners, bindings, issues = [], [], [], []
    mapping = payload.get('source_vertex_map', {})
    for index, face in enumerate(faces):
        if (len(face) != 3 or len(set(face)) != 3 or
                any(type(i) is not int or not 0 <= i < len(rest) for i in face)):
            raise StudioError('Cloth metrics require valid indexed triangles')
        uv = copy.deepcopy(stored[index] if stored is not None else [rest[i][:2] for i in face])
        if len(uv)!=3 or any(len(p) not in (2,3) or any(not math.isfinite(x) for x in p[:2]) for p in uv):
            raise StudioError('Source face UV must contain three finite metric points')
        uv = [list(p[:2]) for p in uv]
        ids = list(source_ids[index]) if source_ids is not None else list(face)
        if source_ids is not None:
            if len(ids)!=3 or len(set(ids))!=3 or any(type(i) is not int for i in ids):
                raise StudioError('Source face vertex binding is invalid')
            expected = [mapping.get(str(i), i) for i in ids]
            if expected != list(face):
                rotations = [expected[k:]+expected[:k] for k in range(3)]
                if list(face) in rotations:
                    k = rotations.index(list(face));uv=uv[k:]+uv[:k];ids=ids[k:]+ids[:k]
                else:
                    issues.append({'face':index,'code':'SOURCE_FACE_WINDING_OR_BINDING_CHANGED',
                                   'expected_vertices':expected,'vertices':list(face)})
        common = set.intersection(*(memberships.get(vertex, set()) for vertex in face))
        owner = pieces[index] if pieces is not None else next(iter(common)) if len(common)==1 else None
        if pieces is not None and (not isinstance(owner,str) or owner not in common):
            issues.append({'face':index,'code':'SOURCE_FACE_PIECE_BINDING_CHANGED','piece':owner})
        triangles.append(uv);owners.append(owner);bindings.append(ids)
    return {'source_rest_triangles_cm':triangles,'source_face_pieces':owners,
            'source_face_vertex_ids':bindings,'binding_issues':issues,
            'binding_origin':'EXPLICIT_PER_FACE' if source_ids is not None else 'RECONSTRUCTED_FROM_CURRENT_SOURCE_MAP'}


def bending_statistics(payload, coords, source_triangles, invalid_faces, source_face_pieces=None):
    """Geometric dihedrals; no stretch limit is reused as a bending limit."""
    owners = source_face_pieces if source_face_pieces is not None else face_sources(payload)['source_face_pieces']
    normals, source_normals, adjacency = [], [], {}
    for index, (face, uv) in enumerate(zip(payload['faces'], source_triangles, strict=True)):
        normal = _normal([coords[i] for i in face]);length=math.sqrt(sum(x*x for x in normal))
        normals.append([x/length for x in normal] if length else None)
        signed = _normal(uv)[2]
        source_normals.append([0.,0.,math.copysign(1.,signed)] if signed else None)
        for a,b in zip(face,face[1:]+face[:1]):
            adjacency.setdefault(tuple(sorted((a,b))),[]).append((index,a,b))
    values={pid:{'placed':[],'source':[]} for pid in payload.get('panels',{})}
    excluded={'open_boundary':0,'nonmanifold':0,'panel_interface_or_ambiguous':0,
              'degenerate_face':0,'inconsistent_orientation':0}
    def angle(a,b):
        return math.degrees(math.atan2(math.sqrt(sum(x*x for x in _cross(a,b))),
                                      max(-1.,min(1.,sum(x*y for x,y in zip(a,b))))))
    for uses in adjacency.values():
        if len(uses)!=2:
            excluded['open_boundary' if len(uses)==1 else 'nonmanifold']+=1;continue
        left,right=uses;a,b=left[0],right[0];pid=owners[a]
        if pid is None or pid!=owners[b]:excluded['panel_interface_or_ambiguous']+=1
        elif a in invalid_faces or b in invalid_faces or normals[a] is None or normals[b] is None or source_normals[a] is None or source_normals[b] is None:
            excluded['degenerate_face']+=1
        elif left[1:]!=(right[2],right[1]):excluded['inconsistent_orientation']+=1
        else:
            values.setdefault(pid,{'placed':[],'source':[]})['placed'].append(angle(normals[a],normals[b]))
            values[pid]['source'].append(angle(source_normals[a],source_normals[b]))
    def report(placed,source):
        return {'metric':'GEOMETRIC_3D_DIHEDRAL_NOT_PHYSICAL','units':'degrees',
                'scope':'CONSISTENTLY_ORIENTED_INTERIOR_EDGES_WITHIN_ONE_SOURCE_PANEL',
                'placed_dihedral_degrees':distribution(placed),'source_dihedral_degrees':distribution(source),
                'qualification':'NONE'}
    local={pid:report(value['placed'],value['source']) for pid,value in values.items()}
    total=report([a for value in values.values() for a in value['placed']],
                 [a for value in values.values() for a in value['source']]);total['excluded_edges']=excluded
    return total,local


def evaluate_metrics(payload, coords, include_faces=True, include_bending=True):
    if len(coords)!=len(payload['rest_cm']) or any(len(p)!=3 or any(not math.isfinite(x) for x in p) for p in coords):
        raise StudioError('Nonfinite or mismatched simulation geometry')
    binding=face_sources(payload);records=[];extrema={};invalid=[];edge_uses={}
    areas=[];placed_areas=[];source_signs={}
    def extreme(name,value,record,lower=False):
        if value is None:return
        if name not in extrema or (value<extrema[name]['value'] if lower else value>extrema[name]['value']):
            extrema[name]={'value':value,'face':record['face'],'piece':record['piece'],
                'vertices':record['vertices'],'source_uv_cm':record['source_uv_cm']}
    for index,(face,uv,piece) in enumerate(zip(payload['faces'],binding['source_rest_triangles_cm'],binding['source_face_pieces'],strict=True)):
        source=triangle_metrics(uv);placed=triangle_metrics([coords[i] for i in face]);principal=principal_stretches(uv,[coords[i] for i in face])
        ratios=[b/a if a>1e-12 else None for a,b in zip(source['edges_cm'],placed['edges_cm'])]
        signed=_normal(uv)[2]/2
        source_signs.setdefault(piece,set()).add(1 if signed>0 else -1 if signed<0 else 0)
        record={'face':index,'piece':piece,'vertices':list(face),'source_uv_cm':uv,
            'source_area_cm2':source['area_cm2'],'placed_area_cm2':placed['area_cm2'],
            'area_ratio':placed['area_cm2']/source['area_cm2'] if source['area_cm2'] else None,
            'source_signed_area_cm2':signed,'principal_stretch':principal,
            'source_min_angle_degrees':source['min_angle_degrees'],'placed_min_angle_degrees':placed['min_angle_degrees'],
            'source_aspect_ratio':source['aspect_ratio'],'placed_aspect_ratio':placed['aspect_ratio'],
            'edge_stretch':ratios,'source_edges_cm':source['edges_cm'],'placed_edges_cm':placed['edges_cm']}
        areas.append(source['area_cm2']);placed_areas.append(placed['area_cm2'])
        if min(source['area_cm2'],placed['area_cm2'])<1e-8:invalid.append(index)
        for name,values in (('source',source),('placed',placed)):
            extreme('min_'+name+'_angle_degrees',values['min_angle_degrees'],record,True)
            extreme('min_'+name+'_area_cm2',values['area_cm2'],record,True)
            extreme('min_'+name+'_edge_cm',min(values['edges_cm']),record,True)
        for ratio in ratios:
            extreme('min_edge_stretch',ratio,record,True);extreme('max_edge_stretch',ratio,record)
        if principal is not None:
            extreme('min_principal_stretch',principal[0],record,True);extreme('max_principal_stretch',principal[1],record)
        extreme('min_area_ratio',record['area_ratio'],record,True);extreme('max_area_ratio',record['area_ratio'],record)
        for a,b in zip(face,face[1:]+face[:1]):edge_uses.setdefault(tuple(sorted((a,b))),[]).append((a,b,index))
        if include_faces:records.append(record)
    conflicts=[{'edge':list(edge),'faces':[u[2] for u in uses]} for edge,uses in edge_uses.items()
               if len(uses)==2 and uses[0][:2]==uses[1][:2]]
    nonmanifold=[list(edge) for edge,uses in edge_uses.items() if len(uses)>2]
    orientation={'source_binding_issues':binding['binding_issues'],'inconsistent_oriented_edges':conflicts,
        'nonmanifold_edges':nonmanifold,'source_winding_by_piece':{str(k):sorted(v) for k,v in source_signs.items()},
        'material_side_inversion':'NOT_DETERMINABLE_FROM_POSITIONS_ONLY',
        'normal_world_sign_is_inversion':False,'rigid_rotations_preserve_metric':True}
    def val(name,default=None):return extrema.get(name,{}).get('value',default)
    result={'version':METRIC_VERSION,'metric_version':METRIC_VERSION,'validator_version':VALIDATOR_VERSION,
        'metric_scope':METRIC_SCOPE,'source_metric_domain':'immutable_source_uv_per_face',
        'source_binding_origin':binding['binding_origin'],'vertices':len(coords),'faces':len(payload['faces']),
        'rest_area_cm2':sum(areas),'placed_area_cm2':sum(placed_areas),
        'min_angle_degrees':min(val('min_source_angle_degrees',0),val('min_placed_angle_degrees',0)),
        'min_area_cm2':min(val('min_source_area_cm2',0),val('min_placed_area_cm2',0)),
        'min_edge_cm':val('min_placed_edge_cm',0),
        'min_stretch':val('min_edge_stretch',0),'max_stretch':val('max_edge_stretch',0),
        'min_principal_stretch':val('min_principal_stretch',0),'max_principal_stretch':val('max_principal_stretch',0),
        'extrema':extrema,'orientation':orientation,'invalid_faces':invalid,
        'qualification':'NONE','historical_pass_transferred':False}
    if include_faces:result['face_metrics']=records
    if include_bending:
        result['bending'],result['bending_per_piece']=bending_statistics(payload,coords,binding['source_rest_triangles_cm'],set(invalid),binding['source_face_pieces'])
    return result


def validate_metrics(payload, coords, limits, include_faces=False, include_bending=True):
    result=evaluate_metrics(payload,coords,include_faces=include_faces,include_bending=include_bending)
    violations=[]
    if not result['faces'] or result['min_area_cm2']<1e-8 or result['min_angle_degrees']<limits['min_angle_degrees']:
        violations.append('degenerate_or_sliver')
    if result['min_edge_cm']<limits['min_edge_cm']:violations.append('short_edge')
    if result['min_stretch']<limits['min_stretch']:violations.append('compression')
    if result['max_stretch']>limits['max_stretch']:violations.append('stretch')
    if result['min_principal_stretch']<limits['min_stretch']:violations.append('principal_compression')
    if result['max_principal_stretch']>limits['max_stretch']:violations.append('principal_stretch')
    orientation=result['orientation']
    if orientation['source_binding_issues'] or orientation['inconsistent_oriented_edges'] or orientation['nonmanifold_edges']:
        violations.append('source_orientation_or_topology')
    result['limits']=dict(limits);result['violations']=violations
    if violations:
        error=StudioError('Source cloth metric rejected: '+', '.join(violations))
        error.quality_metrics=result;error.quality_violations=violations;error.reason_category='geometry_safety'
        raise error
    return result


def validate_linear_motion(payload, before, after):
    """Reject collapse on an explicitly linear geometric update, not a pose.

    This is valid for the bounded closure/union's actual vertex interpolation.
    It must not be used to infer the unobserved trajectory between Cloth frames
    or to reject an arbitrary rigid pose. Squared triangle area is quartic in
    interpolation time; its derivative's real roots locate every minimum.
    """
    def polynomial(coefficients, x):
        value=0.
        for coefficient in reversed(coefficients):value=value*x+coefficient
        return value
    def roots(coefficients):
        while len(coefficients)>1 and coefficients[-1]==0.:coefficients=coefficients[:-1]
        if len(coefficients)==1:return []
        critical=roots([i*coefficients[i] for i in range(1,len(coefficients))])
        boundaries=[0.]+critical+[1.];found=[]
        for a,b in zip(boundaries,boundaries[1:]):
            fa,fb=polynomial(coefficients,a),polynomial(coefficients,b)
            if fa==0.:found.append(a)
            if fa*fb<0:
                for _ in range(55):
                    mid=(a+b)/2;fm=polynomial(coefficients,mid)
                    if fa*fm<=0:b=mid
                    else:a=mid;fa=fm
                found.append((a+b)/2)
        if polynomial(coefficients,1.)==0.:found.append(1.)
        return sorted(set(found))
    lowest=None;worst=None
    for index,face in enumerate(payload['faces']):
        p,q=[[before[i] for i in face],[after[i] for i in face]]
        a,b=[[p[j][k]-p[0][k] for k in range(3)] for j in (1,2)]
        da,db=[[q[j][k]-q[0][k]-edge[k] for k in range(3)] for j,edge in ((1,a),(2,b))]
        normals=[_cross(a,b),[x+y for x,y in zip(_cross(da,b),_cross(a,db))],_cross(da,db)]
        squared=[sum(normals[i][k]*normals[j][k] for i in range(3) for j in range(3)
                     if i+j==degree for k in range(3)) for degree in range(5)]
        candidates=[0.,1.]+roots([i*squared[i] for i in range(1,5)])
        for t in candidates:
            # Evaluate the vector itself at a minimum to avoid cancellation of
            # the squared polynomial near an exact collapse.
            normal=[sum(normals[i][k]*t**i for i in range(3)) for k in range(3)]
            area=math.sqrt(sum(x*x for x in normal))/2
            if lowest is None or area<lowest:
                lowest=area;worst={'face':index,'vertices':list(face),'fraction':t,'area_cm2':area}
    report={'metric_version':METRIC_VERSION,'validator_version':VALIDATOR_VERSION,
            'trajectory':'EXPLICIT_LINEAR_VERTEX_INTERPOLATION','minimum_area_cm2':lowest,
            'worst':worst,'qualification':'NONE'}
    if lowest is None or lowest<1e-8:
        error=StudioError('Explicit linear geometry motion collapses a face')
        error.quality_metrics=report;error.quality_violations=['linear_motion_face_collapse']
        error.reason_category='geometry_safety'
        raise error
    return report


def legacy_metric_evidence(receipt):
    """Keep historical edge-only PASS within its actual validation scope."""
    return {'source_receipt_sha256':digest(receipt),'historical_result':receipt.get('simulation',receipt.get('status','unknown')),
        'historical_metric_scope':'LEGACY_EDGE_RATIOS_UNLESS_EXPLICITLY_VERSIONED_IN_SOURCE_RECEIPT',
        'current_metric_version':METRIC_VERSION,'current_validator_version':VALIDATOR_VERSION,
        'current_metrics_executed':False,'historical_pass_transferred':False,'qualification':'NONE'}
