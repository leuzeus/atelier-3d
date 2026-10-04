"""Bounded, separate pattern proposals from explicit numerical design intent.

Only immutable source UV is transformed. A nominal limb design path is never
an accepted anatomical homology, and an open torso envelope is never used as
a closed material girth. No operation here binds packages or grants fitting.
"""
import copy
import hashlib
import json
import math
import time
import zipfile
from pathlib import Path
from xml.sax.saxutils import escape

from .core import StudioError,atomic_json,contract,digest,inside,sha
from .board_contract import simple_polygon,validate_patterns
from .garment_fit import _path
from .sewing import edge_chain,sample_chain
from .garment_measurements import source_edge_at_v


def _split_source_boundary_triangles(source,old_to_new,insertions):
    """Subdivide only existing triangles adjacent to inserted source edges."""
    from .garment_guides import _source_limb_mesh
    _source_limb_mesh(source,1)
    faces=[{'source_face':index,'vertices':[old_to_new[i]for i in face]}
        for index,face in enumerate(source['faces'])]
    count=len(source['vertices'])
    for edge,points in sorted(insertions.items()):
        a,b=old_to_new[edge],old_to_new[(edge+1)%count]
        adjacent=[]
        for index,row in enumerate(faces):
            face=row['vertices']
            for position in range(3):
                x,y=face[position],face[(position+1)%3]
                if set((x,y))==set((a,b)):adjacent.append((index,position,x==a))
        if len(adjacent)!=1:
            raise StudioError('Densification needs one actual source triangle adjacent to each inserted boundary segment')
        index,position,forward=adjacent[0];row=faces.pop(index);face=row['vertices']
        indices=[record['new_vertex_index']for record in points]
        if not forward:indices.reverse()
        chain=[face[position],*indices,face[(position+1)%3]];opposite=face[(position+2)%3]
        faces[index:index]=[{'source_face':row['source_face'],'vertices':[x,y,opposite]}for x,y in zip(chain,chain[1:])]
    mapping={str(i):[]for i in range(len(source['faces']))}
    for index,row in enumerate(faces):mapping[str(row['source_face'])].append(index)
    return [row['vertices']for row in faces],mapping


def _length(piece,edge):
    curve=edge_chain(piece,edge)[1]
    return math.fsum(math.dist(a,b)for a,b in zip(curve,curve[1:]))


def _bounds(piece):
    return [[min(p[k]for p in piece['vertices']),max(p[k]for p in piece['vertices'])]for k in (0,1)]


def _targets(decision,compiled):
    if (decision.get('status')!='NUMERIC_EASE_DESIGN_INTENT_APPROVED' or decision.get('approved')is not True
            or not {'numeric_ease_design_targets','underlayer_intent'}.issubset(decision.get('approved_scope',[]))):
        raise StudioError('Pattern grading requires explicit approved numerical design intent and underlayer scope')
    if decision.get('body_ref')!=compiled['assembly_spec']['body_ref']or decision.get('dossier_ref')!=compiled['source_ref']:
        raise StudioError('Pattern design intent belongs to another exact source dossier or unchanged body')
    owners={row['id']for row in compiled['components']if row['pipeline']=='PATTERN_SEWN'}
    if not decision.get('component_ids')or len(set(decision['component_ids']))!=len(decision['component_ids'])or set(decision['component_ids'])-owners:
        raise StudioError('Pattern design intent must identify actual textile component owners')
    targets={}
    for row in decision.get('targets',[]):
        name=row['body_landmark'];ease=row['ease_cm'];body=row['body_girth_cm']
        values=[body,row['body_plus_target_cm']]+[ease[key]for key in ('minimum','target','maximum','movement','underlayers','style')]
        if (name in targets or any(type(v)not in(int,float)or not math.isfinite(v)or v<0 for v in values)
                or body<=0 or not ease['minimum']<=ease['target']<=ease['maximum']
                or abs(math.fsum(ease[key]for key in ('movement','underlayers','style'))-ease['target'])>1e-8
                or abs(body+ease['target']-row['body_plus_target_cm'])>1e-8
                or row.get('body_plus_target_interpretation')not in('CLOSED_LIMB_NOMINAL_REFERENCE_REQUIRES_HOMOLOGY','SPATIAL_REFERENCE_ENVELOPE_NOT_CLOSED_MATERIAL_GIRTH')):
            raise StudioError('Pattern design targets, bounds and explicit ease breakdown are inconsistent')
        targets[name]=row
    if not targets:raise StudioError('Pattern grading needs explicit numerical design targets')
    return targets


def _parameters(compiled,policy):
    owners={};variables=[];fixed={};families={}
    for family in sorted(policy['families'],key=lambda row:row['id']):
        fid=family['id']
        if fid in families:raise StudioError('Pattern grading family IDs must be unique')
        families[fid]=family
        for pid in family['pieces']:
            if pid in owners or pid not in compiled['textiles']:
                raise StudioError('Pattern grading families must own actual textile pieces without overlap')
            owners[pid]=fid;source=compiled['textiles'][pid]
            if source['component_id']not in policy['_decision_components']:
                raise StudioError('Pattern grading cannot propagate into a component outside the design decision')
            if family['mode']=='WIDTH_BY_V_STATIONS':
                if source['grain_direction']not in([0,1],[0,-1])or source['semantics']['longitudinal_uv_axis']!='v':
                    raise StudioError('Width by V needs an explicit unchanged source grain along V')
                stations=family['stations'];heights=[row['v_cm']for row in stations];piece=source['source_geometry']
                if heights!=sorted(set(heights))or heights[0]>_bounds(piece)[1][0]or heights[-1]<_bounds(piece)[1][1]:
                    raise StudioError('Width stations must be ordered, unique and cover the actual source V domain')
                if any(not any(abs(vertex[1]-height)<=1e-9 for vertex in piece['vertices'])for height in heights):
                    raise StudioError('Unsupported width station: it has no source vertex; densification must be a separate explicit topology proposal')
            elif set(family['anchor_vertices'])!=set(family['pieces']):
                raise StudioError('Affine grading needs one declared immutable source anchor vertex per piece')
            if family['mode']=='AFFINE_SOURCE_UV'and family['anchor_vertices'][pid]>=len(source['source_geometry']['vertices']):
                raise StudioError('Affine grading anchor is outside its actual source vertices')
        params=([(fid+':x',family['scale_x']),(fid+':y',family['scale_y'])]if family['mode']=='AFFINE_SOURCE_UV'else
            [(fid+':station:'+str(i),row['scale_x'])for i,row in enumerate(family['stations'])])
        for key,value in params:
            if not value['minimum']<=value['initial']<=value['maximum']:
                raise StudioError('Pattern grading initial value is outside declared parameter bounds')
            if value['minimum']==value['maximum']:fixed[key]=value['minimum']
            else:variables.append((key,value))
    return owners,families,variables,fixed


def _densified_compilation(compiled,policy):
    """Insert declared source-boundary points, with explicit index provenance."""
    result=copy.deepcopy(compiled);mappings={}
    for family in sorted(policy['families'],key=lambda row:row['id']):
        option=family.get('densification')
        if option is None:continue
        if family['mode']!='WIDTH_BY_V_STATIONS' or set(option['edges_by_piece'])!=set(family['pieces']):
            raise StudioError('Densification must explicitly cover its width-station family and both named source partners')
        for pid in sorted(family['pieces']):
            owner=compiled['textiles'].get(pid)
            if owner is None:raise StudioError('Densification cannot invent a source piece')
            source=owner['source_geometry'];selected=option['edges_by_piece'][pid]
            partners=[row for row in compiled['links']if row['kind']=='permanent'and row['piece_a']==row['piece_b']==pid
                and set((row['edge_a'],row['edge_b']))==set(selected)]
            if len(selected)!=2 or len(set(selected))!=2 or len(partners)!=1:
                raise StudioError('Densification needs both actual named edges of one permanent source self seam')
            if owner['source']['pattern']['cut_outline_cm']!=source['vertices']or owner['source'].get('seam_allowance_cm')!=0:
                raise StudioError('Boundary densification currently needs exact cut=sewing contour and zero allowance; other cut outlines need an explicit separate policy')
            count=len(source['vertices']);insertions={};provenance=[]
            for edge in sorted(selected):
                indices,curve,_=edge_chain(source,edge)
                for station in family['stations']:
                    height=station['v_cm']
                    if height<min(p[1]for p in curve)-1e-9 or height>max(p[1]for p in curve)+1e-9:continue
                    if any(abs(p[1]-height)<=1e-9 for p in curve):continue
                    selector=source_edge_at_v(source,edge,height);hits=[]
                    for i,j in zip(indices,indices[1:]):
                        a,b=source['vertices'][i],source['vertices'][j]
                        if a[1]==b[1]:continue
                        t=(height-a[1])/(b[1]-a[1])
                        if not 0<t<1:continue
                        if (i+1)%count==j:key=i;order=t
                        elif (j+1)%count==i:key=j;order=1-t
                        else:raise StudioError('Densification source edge skips polygon boundary vertices')
                        point=[a[0]+t*(b[0]-a[0]),height]
                        if min(math.dist(point,a),math.dist(point,b))<option['minimum_segment_length_cm']:
                            raise StudioError('Densification breakpoint would create a segment below its declared source budget')
                        hits.append((key,order,point,i,j,t))
                    if len(hits)!=1:raise StudioError('Densification needs one unambiguous interior source boundary segment')
                    key,order,point,i,j,t=hits[0]
                    if any(abs(previous['polygon_fraction']-order)<1e-10 for previous in insertions.get(key,[])):
                        raise StudioError('Densification attempted to duplicate a source boundary breakpoint')
                    record={'source_edge':edge,'source_edge_fraction':selector['fraction'],'source_vertex_pair':[i,j],
                        'source_segment_fraction':t,'source_uv_cm':point,'station_v_cm':height,'polygon_fraction':order}
                    insertions.setdefault(key,[]).append(record);provenance.append(record)
            if len(provenance)>option['max_inserted_vertices_per_piece']:
                raise StudioError('Densification exceeds its declared inserted-vertex budget')
            for edge,values in insertions.items():
                values.sort(key=lambda row:row['polygon_fraction'])
                chain=[source['vertices'][edge],*[row['source_uv_cm']for row in values],source['vertices'][(edge+1)%count]]
                if min(math.dist(a,b)for a,b in zip(chain,chain[1:]))<option['minimum_segment_length_cm']:
                    raise StudioError('Densification breakpoints create a segment below their declared source budget')
            vertices=[];old_to_new={};edge_new={}
            for i,point in enumerate(source['vertices']):
                old_to_new[i]=len(vertices);vertices.append(copy.deepcopy(point));added=[]
                for record in insertions.get(i,[]):
                    record['new_vertex_index']=len(vertices);added.append(len(vertices));vertices.append(copy.deepcopy(record['source_uv_cm']))
                edge_new[i]=added
            def remap(chain,closed=False):
                mapped=[];pairs=list(zip(chain,chain[1:]+chain[:1]))if closed else list(zip(chain,chain[1:]))
                for i,j in pairs:
                    mapped.append(old_to_new[i])
                    if (i+1)%count==j:mapped.extend(edge_new[i])
                    elif (j+1)%count==i:mapped.extend(reversed(edge_new[j]))
                if not closed:mapped.append(old_to_new[chain[-1]])
                return mapped
            geometry=copy.deepcopy(source);geometry['vertices']=vertices
            geometry['edges']={name:remap(chain)for name,chain in source['edges'].items()}
            if provenance:
                geometry['faces'],face_regions=_split_source_boundary_triangles(source,old_to_new,insertions)
                from .garment_guides import _source_limb_mesh
                _source_limb_mesh(geometry,1)
            else:
                geometry['faces']=copy.deepcopy(source['faces']);face_regions={str(i):[i]for i in range(len(source['faces']))}
            result['textiles'][pid]['source_geometry']=geometry
            result['textiles'][pid]['source']['pattern']['cut_outline_cm']=copy.deepcopy(vertices)
            mappings[pid]={'source_geometry_sha256':digest(source),'densified_source_geometry_sha256':digest(geometry),
                'inserted_vertices':copy.deepcopy(provenance),'old_to_new_vertex_indices':{str(i):j for i,j in old_to_new.items()},
                'source_vertex_count':count,'variant_vertex_count':len(vertices),'face_count_preserved':len(source['faces'])==len(geometry['faces']),
                'source_face_count':len(source['faces']),'variant_face_count':len(geometry['faces']),
                'face_policy':option['face_policy']if provenance else'SOURCE_FACES_UNCHANGED',
                'source_faces_sha256':digest(source['faces']),'variant_faces_sha256':digest(geometry['faces']),
                'old_to_new_face_regions':face_regions,
                'named_edge_ids_preserved':set(source['edges'])==set(geometry['edges']),
                'source_contour_before_grading':'UNCHANGED_COLLINEAR_SOURCE_BREAKPOINTS_ONLY'}
    return result,mappings


def _nominal_path(compiled,row):
    current=copy.deepcopy(row)
    if row['path_parameterization']=='SOURCE_V_CM':
        if 'source_v_cm'not in row:raise StudioError('A nominal V path needs its explicitly declared source V station')
        for segment in current['segments']:
            piece=compiled['textiles'][segment['piece']]['source_geometry']
            for endpoint in ('from','to'):
                segment[endpoint]=source_edge_at_v(piece,segment[endpoint]['edge'],row['source_v_cm'])
    elif 'source_v_cm'in row:
        raise StudioError('A normalized arc path cannot claim a fixed source V station')
    return current


def _point(point,piece,family,values):
    if family['mode']=='AFFINE_SOURCE_UV':
        anchor=piece['vertices'][family['anchor_vertices'][family['_piece']]]
        return [point[k]if values[family['id']+(':'+axis)]==1 else
            anchor[k]+values[family['id']+(':'+axis)]*(point[k]-anchor[k])for k,axis in enumerate(('x','y'))]
    center=math.fsum(_bounds(piece)[0])/2
    stations=family['stations'];v=point[1]
    if v<=stations[0]['v_cm']:factor=values[family['id']+':station:0']
    elif v>=stations[-1]['v_cm']:factor=values[family['id']+':station:'+str(len(stations)-1)]
    else:
        for i,(a,b)in enumerate(zip(stations,stations[1:])):
            if a['v_cm']<=v<=b['v_cm']:
                t=(v-a['v_cm'])/(b['v_cm']-a['v_cm'])
                factor=(1-t)*values[family['id']+':station:'+str(i)]+t*values[family['id']+':station:'+str(i+1)];break
    return list(point)if factor==1 else[center+(point[0]-center)*factor,v]


def _candidate(compiled,data,owners,families,values):
    candidate=copy.deepcopy(data);annotations={}
    for pid,row in sorted(compiled['textiles'].items()):
        source=row['source_geometry'];info=copy.deepcopy(row['source']);piece=candidate[row['component_id']]['pieces'][pid]
        if pid in owners:
            piece=copy.deepcopy(source);candidate[row['component_id']]['pieces'][pid]=piece
            family={**families[owners[pid]],'_piece':pid};transform=lambda p:_point(p,source,family,values)
            piece['vertices']=[transform(p)for p in source['vertices']]
            pattern=info['pattern'];pattern['cut_outline_cm']=[transform(p)for p in pattern['cut_outline_cm']]
            for fold in pattern['folds']:fold['line_cm']=[transform(p)for p in fold['line_cm']]
            info['dimensions_cm'][:2]=[b-a for a,b in _bounds(piece)]
        annotations[pid]=info
    return candidate,annotations


def _seams(compiled,candidate,limits):
    rows=[]
    for link in sorted(compiled['links'],key=lambda row:row['id']):
        source=candidate[link['component_id']]['pieces'];a=source[link['piece_a']];b=source[link['piece_b']]
        x=_length(a,link['edge_a']);y=_length(b,link['edge_b']);delta=abs(x-y)
        tol=max(limits['seam_length_absolute_cm'],limits['seam_length_relative']*max(x,y))
        row={'id':link['id'],'kind':link['kind'],'orientation':link['orientation'],'piece_a':link['piece_a'],
            'edge_a':link['edge_a'],'piece_b':link['piece_b'],'edge_b':link['edge_b'],
            'length_a_cm':x,'length_b_cm':y,'mismatch_cm':delta,'tolerance_cm':tol,
            'status':'COMPATIBLE'if delta<=tol else'INCOMPATIBLE',
            'source_length_a_cm':_length(compiled['textiles'][link['piece_a']]['source_geometry'],link['edge_a']),
            'source_length_b_cm':_length(compiled['textiles'][link['piece_b']]['source_geometry'],link['edge_b'])}
        if link['kind']=='permanent'and link['piece_a']==link['piece_b']:
            ca=edge_chain(a,link['edge_a'])[1];cb=edge_chain(b,link['edge_b'])[1]
            if link['orientation']=='reverse':cb=list(reversed(cb))
            da=[math.dist(u,v)for u,v in zip(ca,ca[1:])];db=[math.dist(u,v)for u,v in zip(cb,cb[1:])]
            row['self_seam_arc_increments_cm']={'a':da,'b':db}
            row['self_seam_parameterization']=('COMPATIBLE'if len(da)==len(db)and all(abs(u-v)<=tol for u,v in zip(da,db))else'INCOMPATIBLE')
            if row['self_seam_parameterization']!='COMPATIBLE':row['status']='INCOMPATIBLE'
        rows.append(row)
    return rows


def _linear(matrix,rhs):
    values=[row[:]+[v]for row,v in zip(matrix,rhs)];n=len(rhs)
    for k in range(n):
        pivot=max(range(k,n),key=lambda j:abs(values[j][k]));values[k],values[pivot]=values[pivot],values[k]
        if abs(values[k][k])<1e-20:raise StudioError('Pattern grading damped numerical system is singular')
        divisor=values[k][k];values[k]=[v/divisor for v in values[k]]
        for j in range(n):
            if j!=k:
                factor=values[j][k];values[j]=[a-factor*b for a,b in zip(values[j],values[k])]
    return [row[-1]for row in values]


def _material_notches(compiled,grading,best,mode):
    """Map actual source notches through the exported boundary deformation."""
    rows=[];diagnostics=[];admissible=True
    for pid,owner in sorted(compiled['textiles'].items()):
        cid=owner['component_id'];source=owner['source_geometry'];basis=grading['textiles'][pid]['source_geometry']
        candidate=best['candidate_garments'][cid]['pieces'][pid]
        for mark in owner['source']['pattern']['assembly_marks']:
            seam=next((row for row in best['candidate_garments'][cid]['seams']if row['id']==mark['seam_id']),None)
            if seam is None or pid not in(seam['piece_a'],seam['piece_b']):
                raise StudioError('Source notch must belong to a real declared sewing relation: '+pid+' / '+mark['id'])
            bindings=[]
            for side in('a','b'):
                if seam['piece_'+side]!=pid:continue
                edge=seam['edge_'+side];original_curve=edge_chain(source,edge)[1]
                source_position=mark.get('seam_side_positions',{}).get(side,mark['position'])
                point=sample_chain(original_curve,source_position);old=edge_chain(basis,edge)[1];new=edge_chain(candidate,edge)[1]
                total=math.fsum(math.dist(a,b)for a,b in zip(new,new[1:]));offset=0.;matches=[]
                for a,b,x,y in zip(old,old[1:],new,new[1:]):
                    delta=[b[k]-a[k]for k in(0,1)];norm=math.fsum(v*v for v in delta)
                    if norm<=0 or total<=0:raise StudioError('Source notch cannot map through a collapsed boundary segment')
                    t=math.fsum((point[k]-a[k])*delta[k]for k in(0,1))/norm
                    residual=math.dist(point,[a[k]+t*delta[k]for k in(0,1)])
                    if -1e-10<=t<=1+1e-10 and residual<=1e-7:
                        t=max(0.,min(1.,t));target=[x[k]+t*(y[k]-x[k])for k in(0,1)]
                        matches.append(((offset+t*math.dist(x,y))/total,target,residual))
                    offset+=math.dist(x,y)
                if not matches or any(abs(row[0]-matches[0][0])>1e-10 or math.dist(row[1],matches[0][1])>1e-7 for row in matches):
                    raise StudioError('Source notch has no unique source-boundary material image: '+pid+' / '+mark['id'])
                fraction,target,residual=matches[0];retained=sample_chain(new,source_position)
                bindings.append({'side':side,'edge':edge,'source_position':source_position,'source_uv_cm':point,
                    'transformed_material_uv_cm':target,'mapped_fraction':fraction,'source_residual_cm':residual,
                    'normalized_fraction_uv_cm':retained,'normalized_to_material_delta_cm':math.dist(retained,target)})
            positions=[row['mapped_fraction']for row in bindings]
            represented=max(positions)-min(positions)<=1e-10
            unary=seam['piece_a']==seam['piece_b']
            partner_residual=(abs(positions[1]-(1-positions[0]if seam['orientation']=='reverse'else positions[0]))if unary else None)
            if mode=='PRESERVE_MATERIAL_POINTS':
                if(unary and partner_residual<=1e-6)or(not unary and represented):
                    actual=next(row for row in best['piece_annotations'][pid]['pattern']['assembly_marks']if row['id']==mark['id']and row['seam_id']==mark['seam_id'])
                    if unary and(not represented or 'seam_side_positions'in mark):
                        actual['seam_side_positions']={row['side']:row['mapped_fraction']for row in bindings}
                    else:actual['position']=positions[0]
                    status='MATERIAL_POINT_PRESERVED'
                else:
                    admissible=False;status='UNREPRESENTABLE_UNARY_MATERIAL_NOTCH'
                    diagnostics.append({'code':status,'piece':pid,'mark_id':mark['id'],'seam_id':mark['seam_id'],
                        'required_partner_fractions':positions,'status':'NEEDS_DATA'})
            else:
                status='MATERIAL_POINT_PRESERVED'if max(row['normalized_to_material_delta_cm']for row in bindings)<=1e-7 else'NORMALIZED_ARC_NOTCH_REPOSITIONING_PROPOSED'
                if status!='MATERIAL_POINT_PRESERVED':diagnostics.append({'code':status,'piece':pid,'mark_id':mark['id'],'seam_id':mark['seam_id'],'status':'REVIEW_REQUIRED'})
            rows.append({'piece':pid,'mark_id':mark['id'],'seam_id':mark['seam_id'],'symbol':mark['symbol'],
                'policy':mode,'status':status,'bindings':bindings,'unary_partner_fraction_residual':partner_residual,'acceptance':'NOT_GRANTED'})
    return rows,diagnostics,admissible


def prepare_pattern_ease_variant(compiled,source_data,decision,policy,clock=time.monotonic):
    """Pure deterministic UV proposal; callers supply already authenticated files."""
    started=clock()
    contract('pattern-ease-variant',policy)
    if compiled.get('status')!='READY_TO_PLAN' or not compiled.get('assembly_spec'):
        raise StudioError('Pattern grading needs complete exact source compilation')
    if (policy['compiled_sha256']!=digest(compiled)or policy['body_ref']!=compiled['assembly_spec']['body_ref']
            or policy['dossier_ref']!=compiled['source_ref']):
        raise StudioError('Pattern grading policy differs from exact source compilation or unchanged body')
    targets=_targets(decision,compiled);before=digest([compiled,source_data,decision,policy])
    expected={row['id']for row in compiled['components']if row['pipeline']=='PATTERN_SEWN'}
    if set(source_data)!=expected:raise StudioError('Pattern variant must preserve every actual source textile component')
    for cid,data in source_data.items():
        contract('garment',data);owned={pid:row for pid,row in compiled['textiles'].items()if row['component_id']==cid}
        if data['component_id']!=cid or set(data['pieces'])!=set(owned)or any(row['source_geometry']!=data['pieces'][pid]for pid,row in owned.items()):
            raise StudioError('Pattern variant source geometry or component inventory differs from exact compilation')
        links=[{key:copy.deepcopy(link[key])for key in ('id','piece_a','piece_b','edge_a','edge_b','kind','orientation')}
               for link in compiled['links']if link['component_id']==cid]
        for link in links:link['id']=link['id'].split('::',1)[1]
        if sorted(links,key=digest)!=sorted(data['seams'],key=digest):raise StudioError('Pattern variant cannot alter source seam kinds, topology or orientation')
    private={**policy,'_decision_components':decision['component_ids']}
    grading,topology_mappings=_densified_compilation(compiled,policy)
    owners,families,variables,fixed=_parameters(grading,private)
    names=[row['body_landmark']for row in policy['nominal_paths']]
    if (len(set(names))!=len(names)or any(name not in targets for name in names)
            or len({row['id']for row in policy['nominal_paths']})!=len(names)):
        raise StudioError('Nominal grading paths must name unique actual numerical design targets and path IDs')
    for row in policy['nominal_paths']:
        name=row['body_landmark'];anatomical,_,side=name.rpartition('.')
        allowed_role={'upper-arm':'sleeve','wrist':'cuff'}.get(anatomical)
        if (allowed_role is None or side not in('left','right')or targets[name]['body_plus_target_interpretation']!='CLOSED_LIMB_NOMINAL_REFERENCE_REQUIRES_HOMOLOGY'
                or row['path_kind']!='closed_girth' or row['component_id']not in decision['component_ids']
                or any(compiled['textiles'][segment['piece']]['semantics']['role']!=allowed_role
                    or compiled['textiles'][segment['piece']]['semantics']['side']!=side for segment in row['segments'])):
            raise StudioError('Nominal grading paths cannot relabel anatomy or turn open torso/collar coverage into a closed material girth')
        if row['path_parameterization']=='SOURCE_V_CM':
            for segment in row['segments']:
                if segment['piece']in owners:
                    family=families[owners[segment['piece']]]
                    if family['mode']=='AFFINE_SOURCE_UV'and any(family['scale_y'][key]!=1 for key in('minimum','initial','maximum')):
                        raise StudioError('A fixed nominal source V path needs length-preserving grading; use an explicitly normalized arc path for other longitudinal policies')
        _path(grading,_nominal_path(grading,row),set(decision['component_ids']))
    if len(variables)>32:raise StudioError('Pattern grading has more than the bounded 32 free parameters')
    budgets=policy['budgets'];limits=policy['constraints'];evaluations=0;history=[]
    def evaluate(values,initial=False):
        nonlocal evaluations
        if not initial and(evaluations>=budgets['max_evaluations']or clock()-started>budgets['max_seconds']):raise TimeoutError
        evaluations+=1;candidate,annotations=_candidate(grading,source_data,owners,families,values)
        modified=copy.deepcopy(compiled)
        for pid,row in modified['textiles'].items():row['source_geometry']=candidate[row['component_id']]['pieces'][pid]
        checks=[];residual=[]
        for row in sorted(policy['nominal_paths'],key=lambda x:x['id']):
            actual_path=_nominal_path(modified,row);length,spans=_path(modified,actual_path,set(decision['component_ids']));target=targets[row['body_landmark']]
            low=target['body_girth_cm']+target['ease_cm']['minimum'];high=target['body_girth_cm']+target['ease_cm']['maximum'];aim=target['body_plus_target_cm']
            checks.append({'id':row['id'],'body_landmark':row['body_landmark'],'material_length_cm':length,
                'target_cm':aim,'minimum_cm':low,'maximum_cm':high,'target_residual_cm':length-aim,
                'status':'WITHIN_DECLARED_NOMINAL_RANGE'if low-limits['target_absolute_cm']<=length<=high+limits['target_absolute_cm']else'OUTSIDE_DECLARED_NOMINAL_RANGE',
                'objective':row['objective'],'path_parameterization':row['path_parameterization'],
                'declared_source_v_cm':row.get('source_v_cm'),'actual_source_spans':spans,'actual_segments':actual_path['segments'],
                'homology':'PENDING','qualification':'NOMINAL_DESIGN_PATH_ONLY'})
            error=length-aim if row['objective']=='TARGET'else min(0.,length-low)+max(0.,length-high)
            residual.append(error*limits['target_weight'])
        seams=_seams(compiled,candidate,limits)
        for seam in seams:
            if seam['kind']!='permanent':continue
            residual.append((seam['length_a_cm']-seam['length_b_cm'])*limits['seam_weight'])
            if 'self_seam_arc_increments_cm'in seam:
                arcs=seam['self_seam_arc_increments_cm']
                if len(arcs['a'])!=len(arcs['b']):raise StudioError('Source self seam lacks compatible explicit homologous arc stations')
                residual.extend((a-b)*limits['seam_weight']for a,b in zip(arcs['a'],arcs['b']))
        if not initial and clock()-started>budgets['max_seconds']:raise TimeoutError
        return {'values':copy.deepcopy(values),'candidate_garments':candidate,'piece_annotations':annotations,
            'target_checks':checks,'seam_constraints':seams,'residual':residual,'score':math.fsum(v*v for v in residual)}
    values={**fixed,**{key:bounds['initial']for key,bounds in variables}};best=evaluate(values,initial=True);initial=copy.deepcopy(best);stop='MAX_ITERATIONS';stagnation=0
    try:
        for iteration in range(budgets['max_iterations']):
            if clock()-started>budgets['max_seconds']:raise TimeoutError
            history.append({'iteration':iteration,'score':best['score'],'parameters':copy.deepcopy(best['values'])})
            if best['score']<=limits['target_absolute_cm']**2:stop='TARGET_RESIDUAL_REACHED';break
            if not variables:stop='NO_FREE_PARAMETERS';break
            base=best;columns=[]
            for key,bounds in variables:
                h=min(budgets['finite_difference_step'],bounds['maximum']-base['values'][key])
                if h<=0:h=-min(budgets['finite_difference_step'],base['values'][key]-bounds['minimum'])
                displaced=copy.deepcopy(base['values']);displaced[key]=max(bounds['minimum'],min(bounds['maximum'],base['values'][key]+h))
                h=displaced[key]-base['values'][key]
                if h==0:raise StudioError('Pattern grading parameter interval has no representable finite-difference step')
                observed=evaluate(displaced)
                columns.append([(a-b)/h for a,b in zip(observed['residual'],base['residual'])])
            n=len(variables);matrix=[[math.fsum(a*b for a,b in zip(columns[i],columns[j]))+(budgets['damping']if i==j else 0.)for j in range(n)]for i in range(n)]
            rhs=[-math.fsum(a*b for a,b in zip(column,base['residual']))for column in columns];direction=_linear(matrix,rhs)
            step=1.;improved=False
            while step>=budgets['minimum_step']:
                trial=copy.deepcopy(base['values'])
                for (key,bounds),delta in zip(variables,direction):trial[key]=max(bounds['minimum'],min(bounds['maximum'],base['values'][key]+step*delta))
                found=evaluate(trial)
                if found['score']<best['score']-1e-14:
                    best=found;improved=True;break
                step*=.5
            stagnation=0 if improved else stagnation+1
            if stagnation>=budgets['stagnation_iterations']:stop='STAGNATION';break
    except TimeoutError:stop='TIME_OR_EVALUATION_BUDGET'
    diagnostics=[]
    for name,target in sorted(targets.items()):
        if name not in names:diagnostics.append({'code':'OPEN_COVERAGE_OVERLAP_REQUIRED'if target['body_plus_target_interpretation']=='SPATIAL_REFERENCE_ENVELOPE_NOT_CLOSED_MATERIAL_GIRTH'else'NOMINAL_PATH_NOT_DECLARED',
            'body_landmark':name,'reference_envelope_cm':target['body_plus_target_cm'],'status':'NEEDS_DATA'})
    incompatible=[row for row in best['seam_constraints']if row['kind']=='permanent'and row['status']!='COMPATIBLE']
    outside=[row for row in best['target_checks']if row['status']!='WITHIN_DECLARED_NOMINAL_RANGE']
    for row in incompatible:diagnostics.append({'code':'PERMANENT_ARC_CONSTRAINT_INCOMPATIBLE','id':row['id'],'mismatch_cm':row['mismatch_cm'],'self_seam_parameterization':row.get('self_seam_parameterization')})
    for row in outside:diagnostics.append({'code':'NOMINAL_TARGET_RANGE_NOT_REACHED','id':row['id'],'target_residual_cm':row['target_residual_cm']})
    notch_mode=policy.get('notch_policy','PRESERVE_MATERIAL_POINTS')
    notches,notch_diagnostics,notches_ok=_material_notches(compiled,grading,best,notch_mode);diagnostics.extend(notch_diagnostics)
    geometry_ok=notches_ok
    for pid,row in sorted(compiled['textiles'].items()):
        piece=best['candidate_garments'][row['component_id']]['pieces'][pid];info=best['piece_annotations'][pid]
        if not simple_polygon(piece['vertices'])or not simple_polygon(info['pattern']['cut_outline_cm']):
            geometry_ok=False;diagnostics.append({'code':'VARIANT_POLYGON_INVALID','piece':pid})
        if pid in topology_mappings and topology_mappings[pid]['inserted_vertices']:
            from .garment_guides import _source_limb_mesh
            try:_source_limb_mesh(piece,1)
            except StudioError as error:
                geometry_ok=False;diagnostics.append({'code':'VARIANT_SOURCE_TRIANGLE_COVERAGE_INVALID','piece':pid,'message':str(error)})
            minimum=families[owners[pid]]['densification']['minimum_segment_length_cm']
            for record in topology_mappings[pid]['inserted_vertices']:
                index=record['new_vertex_index'];point=piece['vertices'][index]
                for partner in((index-1)%len(piece['vertices']),(index+1)%len(piece['vertices'])):
                    distance=math.dist(point,piece['vertices'][partner])
                    if distance<minimum:
                        geometry_ok=False;diagnostics.append({'code':'VARIANT_BREAKPOINT_SEGMENT_BUDGET','piece':pid,
                            'vertices':[index,partner],'measured_cm':distance,'minimum_cm':minimum})
        for index,face in enumerate(piece['faces']):
            source=(row['source_geometry']['vertices']if pid in topology_mappings and topology_mappings[pid]['inserted_vertices']else
                [row['source_geometry']['vertices'][i]for i in row['source_geometry']['faces'][index]])
            modified=[piece['vertices'][i]for i in face]
            area=lambda points:math.fsum(a[0]*b[1]-b[0]*a[1]for a,b in zip(points,points[1:]+points[:1]))/2
            if area(source)*area(modified)<=0:
                geometry_ok=False;diagnostics.append({'code':'VARIANT_FACE_ORIENTATION_INVALID','piece':pid,'face_index':index})
    dossier={'components':{cid:{'pieces':[best['piece_annotations'][pid]for pid in sorted(data['pieces'])]}for cid,data in source_data.items()}}
    try:validate_patterns(dossier,best['candidate_garments'])
    except StudioError as error:geometry_ok=False;diagnostics.append({'code':'VARIANT_MANUFACTURING_INVALID','message':str(error)})
    if clock()-started>budgets['max_seconds']:stop='TIME_BUDGET_POSTPROCESSING'
    incomplete=stop in('TIME_OR_EVALUATION_BUDGET','TIME_BUDGET_POSTPROCESSING','MAX_ITERATIONS')
    if incomplete:diagnostics.append({'code':'NUMERICAL_BUDGET_EXHAUSTED','stop_reason':stop,'status':'INCOMPLETE'})
    feasible=not incompatible and not outside and geometry_ok and not incomplete
    diffs=[]
    for pid,row in sorted(compiled['textiles'].items()):
        source=row['source_geometry'];piece=best['candidate_garments'][row['component_id']]['pieces'][pid]
        diffs.append({'piece':pid,'component_id':row['component_id'],'family':owners.get(pid),
            'source_geometry_sha256':digest(source),'variant_geometry_sha256':digest(piece),
            'source_bounds_uv_cm':_bounds(source),'variant_bounds_uv_cm':_bounds(piece),
            'max_vertex_displacement_cm':max(math.dist(a,b)for a,b in zip(grading['textiles'][pid]['source_geometry']['vertices'],piece['vertices'])),
            'source_vertex_max_displacement_cm':max(math.dist(a,piece['vertices'][topology_mappings[pid]['old_to_new_vertex_indices'][str(i)]if pid in topology_mappings else i])for i,a in enumerate(source['vertices'])),
            'vertices_preserved':len(source['vertices'])==len(piece['vertices']),'faces_preserved':source['faces']==piece['faces'],
            'edges_preserved':source['edges']==piece['edges'],'grain_direction':copy.deepcopy(row['grain_direction']),
            'layer':row['semantics']['layer'],'assembly_marks_preserved':best['piece_annotations'][pid]['pattern']['assembly_marks']==row['source']['pattern']['assembly_marks'],
            'assembly_mark_identifiers_preserved':True,
            'material_notch_points_preserved':all(mark['status']=='MATERIAL_POINT_PRESERVED'for mark in notches if mark['piece']==pid),
            'topology_mapping':copy.deepcopy(topology_mappings.get(pid))})
    result={'version':1,'status':'INCOMPLETE_BUDGET'if incomplete else'REFUSED_CONSTRAINTS'if not feasible else'NEEDS_DATA'if diagnostics else'PROPOSAL_READY_FOR_REVIEW',
        'source_compilation_sha256':digest(compiled),'design_decision_ref':copy.deepcopy(policy['design_decision_ref']),
        'body_ref':copy.deepcopy(policy['body_ref']),'dossier_ref':copy.deepcopy(policy['dossier_ref']),
        'policy_sha256':digest(policy),'candidate_garments':best['candidate_garments'],'piece_annotations':best['piece_annotations'],
        'piece_diff':diffs,'target_checks':best['target_checks'],'seam_constraints':best['seam_constraints'],'diagnostics':diagnostics,
        'notch_policy':notch_mode,'material_notches':notches,
        'solver':{'stop_reason':stop,'evaluations':evaluations,'iterations':len(history),'initial_score':initial['score'],
            'best_score':best['score'],'parameters':best['values'],'history':history,'seconds_elapsed':clock()-started,'budgets':copy.deepcopy(budgets)},
        'packages_allowed_for_review':feasible,'source_text':'PRESERVED_HISTORICAL_NOT_REVIEWED_FOR_VARIANT',
        'textile_count':len(compiled['textiles']),'rigid_parts':copy.deepcopy(compiled['rigid_parts']),
        'source_mutated':False,'body_rescaled':False,'topology_changed':any(row['inserted_vertices']for row in topology_mappings.values()),
        'topology_mappings':topology_mappings,
        'qualification':'PATTERN_PROPOSAL_ONLY','homology':'PENDING','fitting':'NOT_EXECUTED','acceptance':'NOT_GRANTED',
        'next':'Review the exact variant and nominal paths; reconstruct guides, approve actual homology and open coverage, then rerun native preparation before any fitting.'}
    if digest([compiled,source_data,decision,policy])!=before:raise StudioError('Pattern variant preparation mutated its immutable inputs')
    result['proposal_sha256']=digest(result);return result


def _snapshot(project,path):
    file=inside(project.root,path);raw=file.read_bytes()
    return json.loads(raw),{'path':path,'sha256':hashlib.sha256(raw).hexdigest()}


def _review(project,decision,decision_ref):
    state=project.state();reviews=[]
    required=[decision_ref,decision['dossier_ref'],decision['body_ref'],decision['proposal_ref'],decision['review_ref']]
    for cid in decision['component_ids']:
        key='ease-design.'+cid;gate=state['gates'].get(key,{})
        if gate.get('approved')is not True or gate.get('source')!='human':raise StudioError('Pattern variant requires its canonical human ease-design decision: '+key)
        project.require_gate(state,key);refs=[{k:row[k]for k in('path','sha256')}for row in gate['evidence'].values()]
        if any(ref not in refs for ref in required)or gate.get('source_ref')!=decision.get('source_ref')or gate.get('statement')!=decision.get('statement'):
            raise StudioError('Pattern variant design gate did not review these exact decision/body/dossier/proposal files')
        reviews.append({'gate':key,'decision_id':gate['decision_id'],'source_ref':gate['source_ref']})
    return reviews


def _svg(garment):
    values=[p for piece in garment['pieces'].values()for p in piece['vertices']]
    low=[min(p[k]for p in values)for k in(0,1)];high=[max(p[k]for p in values)for k in(0,1)]
    polygons=['<polygon id="'+escape(pid)+'" points="'+' '.join(str(p[0])+','+str(p[1])for p in piece['vertices'])+'" />'for pid,piece in sorted(garment['pieces'].items())]
    return ('<svg xmlns="http://www.w3.org/2000/svg" viewBox="'+str(low[0])+' '+str(low[1])+' '+str(high[0]-low[0])+' '+str(high[1]-low[1])+'">'+''.join(polygons)+'</svg>\n').encode('utf-8')


def _review_svg(compiled,result):
    """A measured source/variant overlay; drawing layout never changes UV."""
    rows=[];pieces=sorted(compiled['textiles']);columns=3;width=400;height=330
    for index,pid in enumerate(pieces):
        owner=compiled['textiles'][pid];source=owner['source_geometry'];variant=result['candidate_garments'][owner['component_id']]['pieces'][pid]
        all_points=source['vertices']+variant['vertices'];low=[min(p[k]for p in all_points)for k in(0,1)];high=[max(p[k]for p in all_points)for k in(0,1)]
        scale=min(340/(high[0]-low[0]),220/(high[1]-low[1]));x=(index%columns)*width+30;y=(index//columns)*height+70
        point=lambda p:[x+(p[0]-low[0])*scale,y+(high[1]-p[1])*scale]
        coordinates=lambda vertices:' '.join(str(p[0])+','+str(p[1])for p in map(point,vertices))
        rows.append('<text x="'+str(x)+'" y="'+str(y-35)+'" font-family="sans-serif" font-size="16">'+escape(pid)+'</text>')
        rows.append('<polygon points="'+coordinates(source['vertices'])+'" fill="none" stroke="#777" stroke-dasharray="5 4"/>')
        rows.append('<polygon points="'+coordinates(variant['vertices'])+'" fill="#cce7ff" fill-opacity="0.4" stroke="#185da8"/>')
        line=0
        for check in result['target_checks']:
            spans=[row for row in check['actual_source_spans']if row['piece']==pid]
            if not spans:continue
            for span in spans:
                rows.append('<polyline points="'+coordinates([span['from_uv_cm'],span['to_uv_cm']])+'" fill="none" stroke="#b52830" stroke-width="2"/>')
            label=check['body_landmark']+': '+format(check['material_length_cm'],'.4f')+' cm; '+check['path_parameterization']
            if check['declared_source_v_cm']is not None:label+=' V='+format(check['declared_source_v_cm'],'.7g')
            rows.append('<text x="'+str(x)+'" y="'+str(y+235+line*16)+'" font-family="sans-serif" font-size="11">'+escape(label)+'</text>');line+=1
    title='<text x="20" y="24" font-family="sans-serif" font-size="16">Proposition de patrons — source grise, variante bleue, chemins nominaux rouges — homologie en attente</text>'
    return ('<svg xmlns="http://www.w3.org/2000/svg" viewBox="0 0 1200 '+str(math.ceil(len(pieces)/columns)*height+50)+'">'+title+''.join(rows)+'</svg>\n').encode('utf-8')


def prepare_project_pattern_ease_variant(project,compiled_dossier_path,design_decision_path,policy_path,output_dir):
    """Write new review artifacts only; never modify project bindings or gates."""
    from .production_dossier import compile_project_dossier
    from .packages import inspect_package,build_package
    compiled,compiled_ref=_snapshot(project,compiled_dossier_path);decision,decision_ref=_snapshot(project,design_decision_path);policy,policy_ref=_snapshot(project,policy_path)
    contract('pattern-ease-variant',policy)
    if compile_project_dossier(project,compiled['source_ref']['path'],compiled['specification_source_ref']['path'])!=compiled:
        raise StudioError('Pattern variant compiled dossier differs from exact current source reconstruction')
    if policy['design_decision_ref']!=decision_ref:raise StudioError('Pattern grading policy targets another exact numerical design decision')
    reviews=_review(project,decision,decision_ref);refs=[compiled_ref,decision_ref,policy_ref,decision['proposal_ref'],decision['review_ref'],compiled['source_ref'],compiled['specification_source_ref'],decision['body_ref']]
    if 'nominal_basis_ref'in policy:
        basis,basis_ref=_snapshot(project,policy['nominal_basis_ref']['path'])
        if basis_ref!=policy['nominal_basis_ref']:
            raise StudioError('Pattern nominal station basis differs from its exact declared reference')
        refs.append(basis_ref)
        for ref in basis.get('input_refs',[]):
            if set(ref)!=set(('path','sha256')):
                raise StudioError('Pattern nominal station basis inputs must be exact typed file references')
            refs.append(ref)
    data={};archives={}
    for row in compiled['components']:
        if row['pipeline']!='PATTERN_SEWN':continue
        ref=row['package_source_ref'];archive=inside(project.root,ref['path'])
        if sha(archive)!=ref['sha256']:raise StudioError('Pattern variant source archive changed')
        inspect_package(archive);refs.append(ref);archives[row['id']]=archive
        with zipfile.ZipFile(archive)as z:data[row['id']]=json.loads(z.read('garment.json'))
    for ref in refs:
        if sha(inside(project.root,ref['path']))!=ref['sha256']:raise StudioError('Pattern variant source or reviewed decision artifact changed')
    if not output_dir.startswith('variants/')or output_dir=='variants/':raise StudioError('Pattern variant output must be a fresh directory under variants/')
    output=inside(project.root,output_dir,must_exist=False)
    if output.exists():raise StudioError('Pattern variant output must not exist; preserve previous proposals')
    result=prepare_pattern_ease_variant(compiled,data,decision,policy)
    for ref in refs:
        if sha(inside(project.root,ref['path']))!=ref['sha256']:raise StudioError('Pattern variant source or decision changed during calculation')
    if _review(project,decision,decision_ref)!=reviews:raise StudioError('Pattern variant canonical design review changed during calculation')
    dossier=json.loads(inside(project.root,compiled['source_ref']['path']).read_bytes())
    for component in dossier['components'].values():
        component['pieces']=[copy.deepcopy(result['piece_annotations'].get(row['id'],row))for row in component['pieces']]
    output.mkdir(parents=True,exist_ok=False);package_results={}
    try:
        atomic_json(output/'candidate-dossier.json',dossier)
        atomic_json(output/'candidate-garments.json',result['candidate_garments'])
        atomic_json(output/'measured-diff.json',{'pieces':result['piece_diff'],'targets':result['target_checks'],'seams':result['seam_constraints'],'material_notches':result['material_notches']})
        (output/'review-patterns.svg').write_bytes(_review_svg(compiled,result))
        if result['packages_allowed_for_review']:
            for cid,archive in sorted(archives.items()):
                source=output/'package-sources'/cid;source.mkdir(parents=True,exist_ok=False)
                with zipfile.ZipFile(archive)as z:
                    for name in z.namelist():
                        if name=='manifest.json':continue
                        target=inside(source,name,must_exist=False);target.parent.mkdir(parents=True,exist_ok=True);target.write_bytes(z.read(name))
                atomic_json(source/'garment.json',result['candidate_garments'][cid]);(source/'pattern.svg').write_bytes(_svg(result['candidate_garments'][cid]))
                atomic_json(source/'variant-source-dossier.json',dossier)
                atomic_json(source/'variant-provenance.json',{'compiled_dossier_ref':compiled_ref,'design_decision_ref':decision_ref,
                    'policy_ref':policy_ref,'qualification':'PATTERN_PROPOSAL_ONLY','source_package_ref':next(row['package_source_ref']for row in compiled['components']if row['id']==cid)})
                package=build_package(source,output/'packages'/(cid+'.garmentpkg'),dossier['asset_id'],cid,'PATTERN_SEWN',
                    {'source':'pattern-ease-variant','created_by':'Atelier 3D source-bound pattern grader','notes':'Separate PATTERN_PROPOSAL_ONLY; exact lineage in variant-provenance.json; no fitting or design acceptance.'})
                package_results[cid]={'path':Path(package['path']).relative_to(project.root).as_posix(),'sha256':package['sha256'],'manifest':package['manifest']}
        for ref in refs:
            if sha(inside(project.root,ref['path']))!=ref['sha256']:raise StudioError('Pattern variant source or decision changed during artifact preparation')
        if _review(project,decision,decision_ref)!=reviews:raise StudioError('Pattern variant design review changed during artifact preparation')
        result.update(input_refs=refs,canonical_design_reviews=reviews,packages=package_results,production_binding='NOT_CHANGED',
            review_pattern_ref={'path':output_dir+'/review-patterns.svg','sha256':sha(output/'review-patterns.svg')})
        result['proposal_sha256']=digest({k:v for k,v in result.items()if k!='proposal_sha256'});atomic_json(output/'proposal.json',result)
    except BaseException as error:
        try:atomic_json(output/'failure.json',{'error':str(error),'candidate_preserved':True,'qualification':'NONE','production_binding':'NOT_CHANGED'})
        except BaseException:pass
        raise
    return {'status':result['status'],'proposal_ref':{'path':output_dir+'/proposal.json','sha256':sha(output/'proposal.json')},
        'review_pattern_ref':result['review_pattern_ref'],
        'packages':package_results,'diagnostics':result['diagnostics'],'target_checks':result['target_checks'],
        'seam_constraints':result['seam_constraints'],'solver':result['solver'],'qualification':'PATTERN_PROPOSAL_ONLY',
        'fitting':'NOT_EXECUTED','acceptance':'NOT_GRANTED','production_binding':'NOT_CHANGED','next':result['next']}
