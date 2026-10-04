"""Source-bound measurement path proposals; no ease or homology approval.

Material lengths belong to the immutable source polygon. A guide-derived
anatomical correspondence is a proposal, including its plane/axis limitations.
An open torso span never becomes a girth by adding another spatial layer.
"""
import copy
import hashlib
import math
import json
import zipfile
import time
import struct

from .core import StudioError,contract,digest,inside,read_json,sha
from .sewing import edge_chain,sample_chain
from .fitting import path_inside
from .preform_volume import sample_curve
from .sewing import segment_distance


def _dot(a,b):return math.fsum(x*y for x,y in zip(a,b))
def _sub(a,b):return [x-y for x,y in zip(a,b)]


def source_edge_at_v(piece,edge,v_cm):
    """Unique actual named-edge intersection, expressed as source arc fraction."""
    _,chain,_=edge_chain(piece,edge);length=sum(math.dist(a,b) for a,b in zip(chain,chain[1:]));hits=[];offset=0.
    if length<=1e-8:raise StudioError('Measurement named source edge is collapsed')
    for a,b in zip(chain,chain[1:]):
        span=math.dist(a,b);dy=b[1]-a[1]
        if abs(dy)<1e-10:
            if abs(a[1]-v_cm)<1e-7:raise StudioError('Measurement plane is coincident with a named source edge')
        else:
            fraction=(v_cm-a[1])/dy
            if -1e-8<=fraction<=1+1e-8:
                fraction=min(1.,max(0.,fraction));arc=(offset+span*fraction)/length
                if not any(abs(old-arc)<1e-8 for old in hits):hits.append(arc)
        offset+=span
    if len(hits)!=1:raise StudioError('Measurement needs one unambiguous crossing of its named source edge')
    return {'edge':edge,'fraction':hits[0]}


def _span(compiled,pid,a,b,v):
    row=compiled['textiles'][pid];piece=row['source_geometry']
    selectors=[source_edge_at_v(piece,edge,v) for edge in (a,b)]
    points=[sample_chain(edge_chain(piece,s['edge'])[1],s['fraction']) for s in selectors]
    if math.dist(*points)<=1e-8 or not path_inside(*points,piece['vertices']):
        raise StudioError('Measurement material path crosses empty source space or is collapsed')
    return {'piece':pid,'from':selectors[0],'to':selectors[1]}, {
        'piece':pid,'source_v_cm':v,'source_uv_cm':points,'source_material_length_cm':math.dist(*points),
        'source_geometry_sha256':digest(piece),'package_ref':copy.deepcopy(row['package_source_ref'])}


def _torso_v(frame,profile,height):
    basis=profile['frame'];rows=[]
    for section in frame.get('arc_sections',[]):
        heights=[_dot(_sub(p,basis['origin_cm']),basis['up']) for p in section['curve_cm']]
        rows.append((section['v_cm'],min(heights),max(heights)))
    rows.sort();choices=[]
    for a,b in zip(rows,rows[1:]):
        if a[2]-a[1]>1e-7 or b[2]-b[1]>1e-7 or abs(b[1]-a[1])<1e-8:continue
        t=(height-a[1])/(b[1]-a[1])
        if -1e-8<=t<=1+1e-8:
            v=a[0]+min(1.,max(0.,t))*(b[0]-a[0])
            if not any(abs(v-old['source_v_cm'])<1e-7 for old in choices):
                choices.append({'source_v_cm':v,'guide_bracket_v_cm':[a[0],b[0]],
                    'guide_bracket_height_cm':[a[1],b[1]],'body_section_height_cm':height})
    if len(choices)!=1:raise StudioError('Anatomical plane has no unique nonextrapolated planar source-guide correspondence')
    return choices[0]


def _trace(compiled,segments):
    """Trace actual source sewing and exact normalized partner parameters."""
    endpoints={(i,side):(s['piece'],s[side]['edge'],s[side]['fraction'])
        for i,s in enumerate(segments) for side in ('from','to')};neighbors={}
    for link in compiled['links']:
        if link['kind']!='permanent':continue
        a=[node for node,value in endpoints.items() if value[:2]==(link['piece_a'],link['edge_a'])]
        b=[node for node,value in endpoints.items() if value[:2]==(link['piece_b'],link['edge_b'])]
        if not a or not b:continue
        if len(a)!=1 or len(b)!=1 or a[0]==b[0]:raise StudioError('Measurement source sewing has ambiguous ownership')
        x,y=a[0],b[0];expected=endpoints[x][2] if link['orientation']=='forward' else 1-endpoints[x][2]
        if abs(expected-endpoints[y][2])>1e-7:
            error=StudioError('Body-plane crossings are not homologous normalized partners of their source seam')
            error.measurement_diagnostic={'link':link['id'],'actual_fraction_a':endpoints[x][2],
                'actual_fraction_b':endpoints[y][2],'expected_fraction_b':expected}
            raise error
        if x in neighbors or y in neighbors:raise StudioError('Measurement source sewing branches or repeats an endpoint')
        neighbors[x]=(y,link['id']);neighbors[y]=(x,link['id'])
    ends=sorted(set(endpoints)-set(neighbors));closed=not ends
    if len(ends)not in (0,2):raise StudioError('Measurement material path is disconnected or has several open ends')
    start=ends[0] if ends else min(endpoints);current=start;ordered=[];joins=[];visited=set()
    while current[0]not in visited:
        index,entry=current;visited.add(index);segment=copy.deepcopy(segments[index])
        if entry=='to':
            segment['from'],segment['to']=segment['to'],segment['from']
            if 'source_uv_polyline_cm'in segment:segment['source_uv_polyline_cm'].reverse()
        ordered.append(segment);exit_node=(index,'to' if entry=='from' else 'from')
        if exit_node not in neighbors:break
        current,link=neighbors[exit_node];joins.append(link)
    if len(visited)!=len(segments) or (closed and current!=start):
        raise StudioError('Measurement must cover its source cohort once without disconnected material')
    return {'path_kind':'closed_girth' if closed else 'open_material_span','segments':ordered,'joins':joins,'engaged_links':[]}


def _center(section):
    curve=section['curve_cm'];length=sum(math.dist(a,b) for a,b in zip(curve,curve[1:]))
    if math.dist(curve[0],curve[-1])>1e-7:raise StudioError('Limb homology needs an actual closed source-guide ring')
    opposite=sample_curve(curve,length/2)
    center=[(a+b)/2 for a,b in zip(curve[0],opposite)];offset=0.
    for i,point in enumerate(curve[:-1]):
        partner=sample_curve(curve,(offset+length/2)%length)
        if math.dist(center,[(a+b)/2 for a,b in zip(point,partner)])>1e-6:
            raise StudioError('Limb source-guide ring has no authenticated common antipodal center')
        offset+=math.dist(curve[i],curve[i+1])
    return center


def _limb_v(frame,section):
    rows=sorted(frame['arc_sections'],key=lambda row:row['v_cm'])
    if len(rows)!=2:raise StudioError('Limb homology requires the declared two-ring source guide')
    a,b=[_center(row) for row in rows];direction=_sub(b,a);length=math.sqrt(_dot(direction,direction))
    if length<=1e-8:raise StudioError('Limb source-guide axis is collapsed')
    t=_dot(_sub(section['center_cm'],a),direction)/(length*length)
    if not 0<=t<=1:raise StudioError('Measured limb section is outside the source-guide longitudinal domain')
    v=rows[0]['v_cm']+t*(rows[1]['v_cm']-rows[0]['v_cm'])
    projected=[a[k]+t*direction[k] for k in range(3)]
    alignment=abs(_dot([x/length for x in direction],section['plane']['normal_world']))
    return {'source_v_cm':v,'source_guide_axis_cm':[a,b],'body_section_center_cm':section['center_cm'],
        'axis_lateral_offset_cm':math.dist(projected,section['center_cm']),
        'body_plane_to_guide_ring_angle_degrees':math.degrees(math.acos(min(1.,max(0.,alignment)))),
        'oblique_plane_material_curve':'NOT_DERIVED','correspondence':'NOMINAL_AXIS_PROJECTION_PROPOSAL'}


def collar_open_path_options(compiled,profile,guides,request):
    """Source closure endpoint rows, without choosing/engaging the closure."""
    owners=[(pid,row)for pid,row in compiled['textiles'].items()
        if row['component_id']==request['component_id'] and row['semantics']['layer']==request['layer']
        and row['semantics']['role']=='collar']
    if len(owners)!=1:raise StudioError('Collar homology requires one actual owned source band')
    pid,row=owners[0];piece=row['source_geometry'];links=[link for link in compiled['links']
        if link['kind']=='closure' and link['piece_a']==link['piece_b']==pid]
    if len(links)!=1 or row['semantics'].get('longitudinal_uv_axis')!='u':
        raise StudioError('Collar band lacks an explicit unary closure and circumferential source U axis')
    closure=links[0];domains=[]
    for edge in (closure['edge_a'],closure['edge_b']):
        _,chain,_=edge_chain(piece,edge);values=[p[1]for p in chain];domains.append((min(values),max(values)))
    lo=max(domain[0]for domain in domains);hi=min(domain[1]for domain in domains)
    if hi-lo<=1e-8:raise StudioError('Collar closure sides have no common source band-height domain')
    frame=guides[row['component_id']]['panels'][pid];basis=profile['frame'];neck=profile['landmarks']['neck'];options=[]
    from .pattern_assembly import _compile_arc_sections,_section_point
    arc=_compile_arc_sections(frame,pid)
    for index,v in enumerate((lo,hi)):
        segment,span=_span(compiled,pid,closure['edge_a'],closure['edge_b'],v)
        world=[_section_point(frame,arc,p,pid)[0]for p in span['source_uv_cm']]
        heights=[_dot(_sub(p,basis['origin_cm']),basis['up'])for p in world]
        try:
            correspondence=_torso_v(frame,profile,neck['section']['height_cm'])
            corresponds=(neck['section']['status']=='MEASURED'and abs(correspondence['source_v_cm']-v)<=1e-7)
        except StudioError:corresponds=False
        option={'id':request['id']+'.open-source-endpoint-row.'+str(index),
            'path_kind':'open_material_span','segments':[segment],'joins':[],'engaged_links':[],
            'source_closure':copy.deepcopy(closure),'source_closure_state':'NOT_ENGAGED_PROPOSAL',
            'source_spans':[span],'source_material_length_cm':span['source_material_length_cm'],
            'guide_body_frame_height_cm':heights,'body_girth_cm':neck['girth_cm']if corresponds else None,
            'body_plane_correspondence':'MEASURED_NECK_PLANE_PROPOSAL'if corresponds else 'ACTUAL_BODY_SECTION_AT_THIS_HEIGHT_REQUIRED',
            'source_row_basis':'ACTUAL_COMMON_CLOSURE_EDGE_ENDPOINT_V_DOMAIN',
            'configuration_choice':'HUMAN_REVIEW_REQUIRED','homology':'HUMAN_REVIEW_REQUIRED',
            'admissible_for_fit':False,'qualification':'NONE','ease_cm':None}
        try:option['source_neckline_attachment']=_collar_neckline_row(compiled,pid,v,span['source_uv_cm'])
        except StudioError as error:option['source_neckline_attachment']={'status':'NEEDS_DATA','message':str(error)}
        options.append(option)
    return options


def _collar_neckline_row(compiled,pid,v,ends):
    """Prove one full material row is attached to declared source neck edges.

    Names of free-form edges do not establish their anatomical role. Each
    counterpart must carry an explicit neck or inner-front anchor declaration;
    its actual permanent attachment intervals must cover the row once.
    """
    piece=compiled['textiles'][pid]['source_geometry'];intervals=[];links=[]
    for link in compiled['links']:
        if link['kind']!='permanent' or pid not in (link['piece_a'],link['piece_b']):continue
        side='a'if link['piece_a']==pid else'b';other='b'if side=='a'else'a'
        partner=compiled['textiles'][link['piece_'+other]];semantics=partner['semantics'];named=semantics.get('guide_edges',{})
        declared=([named['neck']]if semantics['role']in ('front','back')and'neck'in named else
                  [named[key]for key in ('anchor','anchor_end')if key in named]if semantics['role']=='inner_front'else [])
        _,chain,_=edge_chain(piece,link['edge_'+side])
        if any(abs(point[1]-v)>1e-7 for point in chain):continue
        if link['edge_'+other]not in declared:
            raise StudioError('Collar row has an attachment whose partner is not a declared anatomical neck edge')
        values=[point[0]for point in chain]
        if any((b-a)*(values[-1]-values[0])<=0 for a,b in zip(values,values[1:])):
            raise StudioError('Collar neckline attachment is folded or collapsed in its source U row')
        intervals.append((min(values),max(values)));links.append(copy.deepcopy(link))
    lo,hi=sorted(point[0]for point in ends);cursor=lo
    for a,b in sorted(intervals):
        if abs(a-cursor)>1e-7 or b<=a:
            raise StudioError('Collar neckline row has missing or overlapping actual permanent attachment coverage')
        cursor=b
    if not intervals or abs(cursor-hi)>1e-7:
        raise StudioError('Collar material row is not fully attached to declared source neckline edges')
    return {'status':'SOURCE_NECKLINE_ROW_ATTACHED','source_v_cm':v,'source_u_interval_cm':[lo,hi],
        'permanent_source_attachments':sorted(links,key=lambda row:row['id']),
        'coverage':'FULL_SOURCE_ROW_ONCE','source_geometry_sha256':digest(piece)}


def _source_selector_at_point(piece,edge,point,epsilon):
    _,chain,_=edge_chain(piece,edge);length=sum(math.dist(a,b)for a,b in zip(chain,chain[1:]));offset=0.;hits=[]
    for a,b in zip(chain,chain[1:]):
        span=math.dist(a,b)
        if segment_distance(point,a,b)<=epsilon:
            t=_dot(_sub(point,a),_sub(b,a))/(span*span)
            fraction=(offset+min(1.,max(0.,t))*span)/length
            if not any(abs(old-fraction)<epsilon/length for old in hits):hits.append(fraction)
        offset+=span
    if len(hits)!=1:raise StudioError('Guide-plane material endpoint has no unique actual source seam parameter')
    return {'edge':edge,'fraction':hits[0]}


def reconcile_source_boundary_uv(piece,panel,rest_cm,*,seam_witnesses=None):
    """Recover source anchors from their recorded perimeter coordinates.

    The native CDT historically stored binary32 UV. Reconstruction is permitted
    only when the immutable contour identity and binary32 round-trip prove that
    cause. An authenticated named-seam parameter can disambiguate a perimeter
    key straddling a binary32 midpoint; its exact round-trip is still required.
    The native mesh is never changed. Source perimeter keys carry eight
    decimal places, so their material uncertainty is at most 0.5e-8 cm.
    """
    if panel.get('source_contour_sha256')!=digest(piece['vertices']):
        raise StudioError('UV precision reconciliation belongs to another exact immutable source contour')
    ids=panel['boundary'];keys=panel.get('boundary_source_arclength_cm')
    if (not isinstance(keys,list)or len(keys)!=len(ids)or len(set(ids))!=len(ids)
            or any(type(index)is not int or not 0<=index<len(rest_cm)for index in ids)):
        raise StudioError('UV precision reconciliation requires complete actual source perimeter bindings')
    chain=piece['vertices']+[piece['vertices'][0]]
    from .sewing import chain_lengths
    stops=chain_lengths(chain);total=stops[-1];reconstructed={};evidence=[]
    f32=lambda x:struct.unpack('f',struct.pack('f',x))[0]
    for index,key in zip(ids,keys):
        if type(key)not in (int,float)or not math.isfinite(key)or not 0<=key<total or round(key,8)!=key:
            raise StudioError('UV precision reconciliation requires the actual eight-decimal source perimeter key')
        corners=[i for i,stop in enumerate(stops[:-1])if round(stop,8)==key]
        if len(corners)>1:raise StudioError('UV precision reconciliation cannot disambiguate collapsed source perimeter stops')
        uv=copy.deepcopy(chain[corners[0]])if corners else sample_chain(chain,key/total)
        native=rest_cm[index][:2];binary32=list(map(f32,uv));witness=None
        if native!=binary32 and seam_witnesses and index in seam_witnesses:
            witness=copy.deepcopy(seam_witnesses[index]);uv=copy.deepcopy(witness['source_uv_cm'])
            binary32=list(map(f32,uv))
        if native!=binary32:
            raise StudioError('Native source UV differs from its immutable perimeter position and exact binary32 round-trip')
        delta=math.dist(uv,native)
        reconstructed[index]=uv
        evidence.append({'vertex':index,'source_perimeter_key_cm':key,'native_uv_cm':copy.deepcopy(native),
            'source_uv_cm':uv,'native_to_source_delta_cm':delta,'binary32_round_trip':'EXACT',
            'source_stop':'EXACT_ORIGINAL_CORNER'if corners else('CANONICAL_NAMED_SEAM_PARAMETER'if witness else'RECORDED_SOURCE_ARCLENGTH'),
            **({'canonical_seam_witness':witness}if witness else{})})
    return reconstructed,{'status':'IMMUTABLE_SOURCE_BOUNDARY_RECONSTRUCTED_FROM_NATIVE_BINARY32',
        'source_contour_sha256':panel['source_contour_sha256'],'source_perimeter_keys_sha256':digest(keys),
        'boundary_vertex_bindings':evidence,'maximum_native_to_source_delta_cm':max(row['native_to_source_delta_cm']for row in evidence),
        'perimeter_key_uncertainty_cm':.5e-8,'native_mesh_changed':False,'source_cut_changed':False,
        'qualification':'NONE','admissible_for_fit':False}


def intersect_guide_material_plane(piece,frame,triangles,section,seam_edges,*,max_faces=50000,
                                   max_points=20000,max_seconds=15.,epsilon_cm=1e-7,clock=time.monotonic,
                                   triangulated_boundary_uv=None):
    """Intersect real source-UV triangles evaluated on the declared guide.

    Barycentric UV interpolation measures the flat material polyline, independent
    of stretch in the guide. This is a discretized hypothesis, not the physical
    garment or an accepted anatomical homology. No triangulator is invented.
    """
    from .pattern_assembly import _compile_arc_sections,_section_point,_compile_cage,_cage_point
    if (type(max_faces)is not int or max_faces<1 or type(max_points)is not int or max_points<2
            or type(max_seconds)not in(int,float) or not math.isfinite(max_seconds) or max_seconds<=0
            or type(epsilon_cm)not in(int,float) or not math.isfinite(epsilon_cm) or not 0<epsilon_cm<=1e-4
            or len(set(seam_edges))!=2):raise StudioError('Guide-plane computational budgets and two source seam edges must be explicit')
    if not isinstance(triangles,(list,tuple)) or not triangles or len(triangles)>max_faces:
        raise StudioError('Guide-plane source triangle budget exhausted or missing')
    normal=section['plane']['normal_world'];center=section['center_cm']
    if (len(normal)!=3 or len(center)!=3 or any(not math.isfinite(x)for x in normal+center)
            or abs(_dot(normal,normal)-1)>1e-7):raise StudioError('Guide-plane intersection needs a finite actual unit-normal body section')
    boundary=piece['vertices']if triangulated_boundary_uv is None else triangulated_boundary_uv
    if len(boundary)<3 or any(len(p)!=2 or any(not math.isfinite(v)for v in p)for p in boundary):
        raise StudioError('Guide-plane native source-UV boundary is invalid')
    started=clock()
    def check_time():
        if clock()-started>max_seconds:raise StudioError('Guide-plane material computation time budget exhausted')
    source=digest([piece,frame,triangles,section,seam_edges,boundary])
    if 'arc_sections' in frame:
        compiled=_compile_arc_sections(frame,'measurement')
        def evaluate(uv):return _section_point(frame,compiled,uv,'measurement')[0]
    elif 'uv_cm' in frame:
        if not isinstance(frame.get('uv_cm'),list) or not isinstance(frame.get('triangles'),list):
            raise StudioError('Guide-plane cage requires explicit source UV points and triangles')
        if len(frame['uv_cm'])>max_points or len(frame['triangles'])>max_faces:
            raise StudioError('Guide-plane cage computational budget exhausted')
        check_time();compiled=_compile_cage(frame,'measurement',check_time);check_time()
        def evaluate(uv):return _cage_point(frame,compiled,uv,'measurement',check_time)[0]
    else:
        raise StudioError('Guide-plane measurement requires explicit arc sections or a source UV cage')
    vertices={};nodes={};segments=set();bindings={};edges={};edge_directions={};faces=set();area=0.
    for index,uvs in enumerate(triangles):
        check_time()
        if len(uvs)!=3 or any(len(p)!=2 or any(not math.isfinite(v)for v in p)for p in uvs):
            raise StudioError('Guide-plane source triangle coordinates must be finite material UV')
        determinant=(uvs[1][0]-uvs[0][0])*(uvs[2][1]-uvs[0][1])-(uvs[1][1]-uvs[0][1])*(uvs[2][0]-uvs[0][0])
        if abs(determinant)<1e-12:raise StudioError('Guide-plane source triangle is collapsed')
        area+=abs(determinant)/2
        if any(not path_inside(a,b,boundary)for a,b in zip(uvs,uvs[1:]+uvs[:1])):
            raise StudioError('Guide-plane triangulation crosses empty declared source-UV mesh domain')
        keys=[tuple(uv)for uv in uvs]
        face=tuple(sorted(keys))
        if face in faces:raise StudioError('Guide-plane source triangulation contains a duplicate UV face')
        faces.add(face)
        for key in keys:
            if key not in vertices:vertices[key]=evaluate(list(key))
        distances=[_dot(_sub(vertices[key],center),normal)for key in keys]
        if all(abs(value)<=epsilon_cm for value in distances):raise StudioError('Body plane is coplanar with guide triangles; material section is ambiguous')
        cuts={}
        for i,j in ((0,1),(1,2),(2,0)):
            edge=tuple(sorted((keys[i],keys[j])));edges[edge]=edges.get(edge,0)+1
            direction=(1 if keys[i]<keys[j]else -1)*(1 if determinant>0 else -1)
            edge_directions[edge]=edge_directions.get(edge,0)+direction
            for k in (i,j):
                if abs(distances[k])<=epsilon_cm:
                    node=('vertex',keys[k]);cuts[node]=[1. if q==k else 0. for q in range(3)]
                    nodes[node]={'uv':list(keys[k]),'world':vertices[keys[k]]}
            if (distances[i]<-epsilon_cm and distances[j]>epsilon_cm)or(distances[j]<-epsilon_cm and distances[i]>epsilon_cm):
                a,b=edge;da,db=[_dot(_sub(vertices[key],center),normal)for key in (a,b)];t=da/(da-db)
                node=('edge',edge);uv=[a[k]+t*(b[k]-a[k])for k in range(2)]
                world=[vertices[a][k]+t*(vertices[b][k]-vertices[a][k])for k in range(3)]
                weights=[(1-t if key==a else t if key==b else 0.)for key in keys]
                nodes[node]={'uv':uv,'world':world};cuts[node]=weights
        if len(cuts)==1:continue  # A plane tangent at one actual vertex has no material length.
        if cuts and len(cuts)!=2:raise StudioError('Guide-plane source triangle has an ambiguous intersection')
        if len(cuts)==2:
            pair=tuple(sorted(cuts));segments.add(pair)
            for node in pair:bindings.setdefault(node,[]).append({'source_triangle':index,'barycentric_weights':cuts[node]})
        if len(nodes)>max_points:raise StudioError('Guide-plane material point budget exhausted')
    check_time()
    polygon=piece['vertices'];expected_area=abs(sum(a[0]*b[1]-b[0]*a[1]for a,b in zip(boundary,boundary[1:]+boundary[:1])))/2
    if abs(area-expected_area)>max(epsilon_cm*max(1.,expected_area),1e-6)or any(count>2 for count in edges.values()):
        raise StudioError('Guide-plane triangles do not cover a source manifold material domain once')
    border={}
    for (a,b),count in edges.items():
        check_time()
        if count==2:
            if edge_directions[(a,b)]!=0:raise StudioError('Guide-plane internal UV edges have inconsistent material ownership')
        else:border.setdefault(a,set()).add(b);border.setdefault(b,set()).add(a)
    if not border or any(len(neighbors)!=2 for neighbors in border.values()):
        raise StudioError('Guide-plane triangulation has no single closed manifold source boundary')
    start=min(border);previous=None;current=start;visited=set();border_length=0.
    while current not in visited:
        check_time();visited.add(current)
        choices=border[current]-({previous}if previous is not None else set())
        following=min(choices);midpoint=[(current[k]+following[k])/2 for k in range(2)]
        for point in (current,midpoint):
            if min(segment_distance(point,a,b)for a,b in zip(boundary,boundary[1:]+boundary[:1]))>epsilon_cm:
                raise StudioError('Guide-plane triangulated boundary differs from its declared native source-UV material boundary')
        border_length+=math.dist(current,following);previous,current=current,following
    if current!=start or len(visited)!=len(border):
        raise StudioError('Guide-plane triangulation has missing, disconnected or internal material boundary cohorts')
    perimeter=sum(math.dist(a,b)for a,b in zip(boundary,boundary[1:]+boundary[:1]))
    if abs(border_length-perimeter)>max(1e-6,epsilon_cm*perimeter):
        raise StudioError('Guide-plane triangulated boundary does not cover its actual source-UV perimeter once')
    check_time()
    graph={}
    for a,b in segments:
        check_time();graph.setdefault(a,set()).add(b);graph.setdefault(b,set()).add(a)
    ends=sorted(node for node,neighbors in graph.items()if len(neighbors)==1)
    if len(ends)!=2 or any(len(neighbors)not in (1,2)for neighbors in graph.values()):
        raise StudioError('Guide-plane material path is absent, disconnected, branched or internally closed')
    ordered=[];current=ends[0];previous=None;visited=set()
    while current not in visited:
        check_time();visited.add(current);ordered.append(current);following=graph[current]-({previous}if previous is not None else set())
        if not following:break
        previous,current=current,next(iter(following))
    if len(ordered)!=len(graph):raise StudioError('Guide-plane has several disconnected material contours')
    points=[nodes[node]['uv']for node in ordered];worlds=[nodes[node]['world']for node in ordered]
    selectors=[]
    for point in (points[0],points[-1]):
        check_time()
        found=[]
        for edge in seam_edges:
            try:found.append(_source_selector_at_point(piece,edge,point,epsilon_cm))
            except StudioError:pass
            check_time()
        if len(found)!=1:
            error=StudioError('Guide-plane material curve ends outside its actual unary source sewing cohort')
            error.guide_plane_diagnostic={'status':'SOURCE_SEAM_ENDPOINT_CORRESPONDENCE_REFUSED',
                'source_uv_polyline_cm':points,'guide_world_polyline_cm':worlds,
                'source_material_length_cm':sum(math.dist(a,b)for a,b in zip(points,points[1:])),
                'guide_world_length_cm':sum(math.dist(a,b)for a,b in zip(worlds,worlds[1:])),
                'maximum_plane_residual_cm':max(abs(_dot(_sub(p,center),normal))for p in worlds),
                'unmatched_endpoint_uv_cm':point,'source_edge_distances_cm':{
                    edge:min(segment_distance(point,a,b)for a,b in zip(edge_chain(piece,edge)[1],edge_chain(piece,edge)[1][1:]))
                    for edge in seam_edges},'numerical_tolerance_cm':epsilon_cm,
                'source_triangles_sha256':digest(triangles),'source_triangle_bindings':[bindings[node]for node in ordered],
                'source_geometry_sha256':digest(piece),'guide_sha256':digest(frame),'body_section_sha256':digest(section),
                'admissible_for_fit':False,'qualification':'NONE','source_mutated':False}
            raise error
        selectors.append(found[0])
    if selectors[0]['edge']==selectors[1]['edge']:raise StudioError('Guide-plane contour returns to one seam side instead of crossing the material cohort')
    for a,b in zip(points,points[1:]):
        check_time()
        if not path_inside(a,b,polygon):raise StudioError('Guide-plane inverse UV path crosses empty source material')
    if digest([piece,frame,triangles,section,seam_edges,boundary])!=source:raise StudioError('Guide-plane intersection changed its exact source inputs')
    check_time()
    result={'status':'DISCRETIZED_GUIDE_MATERIAL_CURVE_MEASURED','from':selectors[0],'to':selectors[1],
        'source_uv_polyline_cm':points,'guide_world_polyline_cm':worlds,
        'source_material_length_cm':sum(math.dist(a,b)for a,b in zip(points,points[1:])),
        'guide_world_length_cm':sum(math.dist(a,b)for a,b in zip(worlds,worlds[1:])),
        'maximum_plane_residual_cm':max(abs(_dot(_sub(p,center),normal))for p in worlds),
        'source_triangle_bindings':[bindings[node]for node in ordered],
        'source_triangle_count':len(triangles),'source_triangles_sha256':digest(triangles),
        'guide_sha256':digest(frame),'body_section_sha256':digest(section),
        'triangulation_domain':'CANONICAL_NATIVE_DERIVED_SOURCE_UV_BOUNDARY'if triangulated_boundary_uv is not None else'ORIGINAL_SOURCE_POLYGON',
        'triangulated_boundary_sha256':digest(boundary),'material_curve_domain':'ORIGINAL_IMMUTABLE_SOURCE_POLYGON',
        'numerical_tolerance_cm':epsilon_cm,'surface_discretization_error':'NOT_ESTIMATED',
        'homology':'REVIEW_REQUIRED','fitting':'NOT_EXECUTED','qualification':'NONE',
        'budgets':{'max_faces':max_faces,'max_points':max_points,'max_seconds':max_seconds}}
    check_time();return result


def _source_guide_curve(row,pid,frame,source_meshes,section,seam_edges,source_links):
    """Intersect an actual native source triangulation, never a nominal UV row."""
    cid=row['component_id']
    if not source_meshes or cid not in source_meshes:
        raise StudioError('An explicit source cage needs actual source triangulation for body-plane material measurement; no nominal V is inferred')
    from .cloth_metrics import face_sources
    native=source_meshes[cid]
    if (not isinstance(native,dict)or not isinstance(native.get('panels'),dict)
            or not isinstance(native['panels'].get(pid),dict)
            or not isinstance(native.get('rest_cm'),list)or not isinstance(native.get('faces'),list)):
        raise StudioError('Measured guide mesh is missing its actual source panel or indexed triangulation')
    panel=native['panels'][pid]
    if (not isinstance(panel.get('indices'),list)or not isinstance(panel.get('boundary'),list)
            or len(panel['boundary'])<3
            or any(type(index)is not int or not 0<=index<len(native['rest_cm'])
                   for index in panel['indices']+panel['boundary'])
            or not set(panel['boundary'])<=set(panel['indices'])):
        raise StudioError('Measured guide mesh has incomplete actual source panel/boundary ownership')
    source=face_sources(native)
    if source['binding_issues']:raise StudioError('Measured guide mesh has invalid actual source face/UV correspondence')
    actual_triangles=[uv for uv,owner in zip(source['source_rest_triangles_cm'],source['source_face_pieces'])if owner==pid]
    from .source_uv_witnesses import source_boundary_seam_witnesses
    witnesses=source_boundary_seam_witnesses(row['source_geometry'],pid,cid,native,source_links)
    restored,reconciliation=reconcile_source_boundary_uv(row['source_geometry'],panel,native['rest_cm'],seam_witnesses=witnesses)
    owned_faces=[face for face,owner in zip(native['faces'],source['source_face_pieces'])if owner==pid]
    triangles=[[copy.deepcopy(restored.get(index,native['rest_cm'][index][:2]))for index in face]for face in owned_faces]
    boundary=[restored[index]for index in native['panels'][pid]['boundary']]
    curve=intersect_guide_material_plane(row['source_geometry'],frame,triangles,section,seam_edges,
        triangulated_boundary_uv=boundary)
    curve['native_source_triangles_sha256']=digest(actual_triangles)
    curve['source_uv_precision_reconciliation']=reconciliation
    return {'piece':pid,'from':curve['from'],'to':curve['to'],'source_uv_polyline_cm':curve['source_uv_polyline_cm']}, {
        'piece':pid,'source_material_length_cm':curve['source_material_length_cm'],
        'source_geometry_sha256':digest(row['source_geometry']),'package_ref':copy.deepcopy(row['package_source_ref']),
        'guide_plane_material_curve':curve}


def propose_measurement_paths(compiled,profile,guides,required,body_regions=None,region_mapping=(),source_meshes=None,configuration=None):
    """Prepare homology proposals without inventing style/ease/take-up values.

    Pure callers supply trusted source compilations and optional authenticated
    body-region descriptors. The project wrapper recomputes their provenance.
    Every path still requires its exact homology review before fit consumption.
    """
    from .garment_guides import _profile
    _profile(profile);before=digest([compiled,profile,guides,required,body_regions,region_mapping,source_meshes,configuration])
    if compiled.get('status')!='READY_TO_PLAN' or not compiled.get('assembly_spec'):
        raise StudioError('Measurement proposals need the exact complete source compilation')
    if len({row['id'] for row in required})!=len(required):raise StudioError('Measurement requirement IDs must be unique')
    if not required or any(not isinstance(row.get(key),str) or not row[key]
            for row in required for key in ('id','component_id','layer','body_landmark')):
        raise StudioError('Measurement proposals need explicit nonempty source-owner/layer/anatomical requirements')
    for cid,guide in guides.items():
        own={pid:row for pid,row in compiled['textiles'].items() if row['component_id']==cid}
        semantics={pid:row['semantics'] for pid,row in own.items()}
        if (guide.get('profile_sha256')!=digest(profile) or guide.get('profile_cache_key')!=profile['cache_key']
                or guide.get('semantics_sha256')!=digest(semantics) or set(guide['panels'])!=set(own)):
            raise StudioError('Measurement guide belongs to another body, source role declaration or source inventory')
    if body_regions and (body_regions['identity']['profile_sha256']!=digest(profile) or
            body_regions['identity']['profile_cache_key']!=profile['cache_key']):
        raise StudioError('Measurement limb section belongs to another exact body profile')
    mapping={row['body_landmark']:row['section_id'] for row in region_mapping}
    if len(mapping)!=len(region_mapping):raise StudioError('Measurement limb homology mapping is ambiguous')
    proposals=[];diagnostics=[]
    for request in sorted(required,key=lambda row:row['id']):
        owner=[(pid,row) for pid,row in sorted(compiled['textiles'].items())
            if row['component_id']==request['component_id'] and row['semantics']['layer']==request['layer']]
        segments=[];evidence=[];homology=[];landmark=request['body_landmark'];body_girth=None;extra={}
        try:
            if not owner:raise StudioError('Measurement owner/layer has no source material')
            if request['component_id']not in guides:
                raise StudioError('Measurement source owner has no exact body-bound guide proposal')
            native=profile['landmarks'].get(landmark,{});body_section=native.get('section',{})
            if body_section.get('status')=='MEASURED':
                if landmark=='neck'and configuration and configuration.get('wearing_configuration')=='open_front':
                    options=collar_open_path_options(compiled,profile,guides,request)
                    candidates=[option for option in options if option['body_plane_correspondence']=='MEASURED_NECK_PLANE_PROPOSAL'
                        and option['source_neckline_attachment']['status']=='SOURCE_NECKLINE_ROW_ATTACHED']
                    if len(candidates)!=1:
                        raise StudioError('Open collar needs one actual measured neck-plane source row with complete declared neckline attachments')
                    selected=candidates[0];segments.extend(selected['segments']);evidence.extend(selected['source_spans'])
                    body_girth=selected['body_girth_cm'];homology.append({'piece':selected['segments'][0]['piece'],
                        'correspondence':'SOURCE_ATTACHED_NECKLINE_AT_MEASURED_NECK_PLANE_OPEN_PROPOSAL',
                        'source_neckline_attachment':selected['source_neckline_attachment'],
                        'guide_body_frame_height_cm':selected['guide_body_frame_height_cm'],
                        'configuration_source':copy.deepcopy(configuration)})
                    extra={'source_open_collar_options':options,'source_closure':selected['source_closure'],
                        'source_closure_state':'NOT_ENGAGED_PROPOSAL','configuration_choice':'DECLARED_OPEN_FRONT_SOURCE_ROW_PROPOSAL'}
                elif landmark not in ('chest','waist','hip'):
                    raise StudioError('Neck needs explicit collar configuration and source-path homology; closure engagement is not inferred')
                else:
                    body_girth=native['girth_cm']
                height=body_section['height_cm']
                for pid,row in ([]if landmark=='neck'else owner):
                    role=row['semantics']['role'];edges=row['semantics'].get('guide_edges',{})
                    if role not in ('front','back'):continue
                    if 'side'not in edges or ('opening'if role=='front'else'center')not in edges:
                        raise StudioError('Open torso measurement requires explicit source side/opening/centre edges')
                    frame=guides[row['component_id']]['panels'][pid]
                    ends=(edges['opening'],edges['side']) if role=='front' else (edges['side'],edges['center'])
                    if 'uv_cm'in frame:
                        basis=profile['frame']
                        section={'center_cm':[basis['origin_cm'][k]+height*basis['up'][k]for k in range(3)],
                            'plane':{'normal_world':copy.deepcopy(basis['up'])}}
                        segment,span=_source_guide_curve(row,pid,frame,source_meshes,section,ends,compiled['links'])
                        correspondence={'correspondence':'ACTUAL_BODY_PLANE_IN_EXPLICIT_SOURCE_UV_CAGE',
                            'source_v_inferred':False,'body_section_height_cm':height,
                            'anatomical_homology':'REVIEW_REQUIRED',
                            'oblique_plane_material_curve':'DISCRETIZED_SOURCE_UV_CURVE_MEASURED_REVIEW_REQUIRED'}
                    else:
                        correspondence=_torso_v(frame,profile,height)
                        segment,span=_span(compiled,pid,*ends,correspondence['source_v_cm'])
                    segments.append(segment);evidence.append(span);homology.append({'piece':pid,**correspondence})
            else:
                found=body_regions and body_regions['sections'].get(mapping.get(landmark))
                if not found or found['section'].get('status')!='MEASURED' or found['section'].get('ok')is not True:
                    raise StudioError('Actual measured anatomical limb section is missing')
                region,section=found['region'],found['section'];body_girth=section['girth_cm'];side=region['side']
                name,separator,requested_side=landmark.rpartition('.')
                if not separator or requested_side!=side:
                    raise StudioError('Measurement limb contour cannot relabel its measured anatomical side')
                domains={'upper-arm':'SHOULDER_TO_ELBOW_ONLY','wrist':'WRIST_TO_ELBOW_ONLY'}
                if name not in domains or domains[name]!=region['domain']:
                    raise StudioError('Measurement limb contour cannot relabel its measured anatomical source domain')
                role='cuff'if name=='wrist'else'sleeve'
                if role=='cuff':
                    wrist=profile['landmarks'].get(landmark,{});point=wrist.get('point_cm');basis=profile['frame']
                    if not wrist.get('source_ref')or not isinstance(point,list)or len(point)!=3 or any(not math.isfinite(x)for x in point):
                        raise StudioError('Measurement wrist needs its actual sourced body landmark')
                    world=[basis['origin_cm'][i]+_dot(point,[basis[key][i]for key in ('right','forward','up')])for i in range(3)]
                    parameter=section.get('parameter');endpoint=region.get('axis_start_cm'if parameter==0 else'axis_end_cm')
                    if parameter not in (0,1)or endpoint!=section['center_cm']or math.dist(world,section['center_cm'])>1e-7:
                        raise StudioError('Measurement wrist girth needs its actual sourced wrist endpoint section')
                pieces=[(pid,row) for pid,row in owner if row['semantics']['role']==role and row['semantics']['side']==side]
                if len(pieces)!=1:raise StudioError('Anatomical limb section needs one explicitly owned matching source role')
                pid,row=pieces[0];frame=guides[row['component_id']]['panels'][pid]
                if role=='cuff':
                    edge=row['semantics'].get('guide_edges',{}).get('distal')
                    if not edge:raise StudioError('Wrist homology requires the explicit distal named source edge')
                    values=[row['source_geometry']['vertices'][i][1] for i in row['source_geometry']['edges'][edge]]
                    if max(values)-min(values)>1e-7:raise StudioError('Wrist source stop is not a constant-V ring')
                    correspondence={'source_v_cm':values[0],'distal_edge':edge,'body_distal_anchor':landmark,
                        'correspondence':'EXPLICIT_SOURCE_DISTAL_ANCHOR_PROPOSAL'}
                elif 'uv_cm' in frame:
                    if not source_meshes or row['component_id'] not in source_meshes:
                        raise StudioError('An explicit limb cage needs actual source triangulation for oblique material measurement; no nominal V is inferred')
                    correspondence={'correspondence':'ACTUAL_BODY_PLANE_IN_EXPLICIT_SOURCE_UV_CAGE',
                        'source_v_inferred':False,'anatomical_homology':'REVIEW_REQUIRED'}
                else:correspondence=_limb_v(frame,section)
                seams=[link for link in compiled['links'] if link['kind']=='permanent' and link['piece_a']==link['piece_b']==pid]
                if len(seams)!=1:raise StudioError('Closed limb capacity requires one actual unary permanent source seam')
                if role=='sleeve' and source_meshes and row['component_id']in source_meshes:
                    segment,span=_source_guide_curve(row,pid,frame,source_meshes,section,
                        [seams[0]['edge_a'],seams[0]['edge_b']],compiled['links'])
                    correspondence.update(oblique_plane_material_curve='DISCRETIZED_SOURCE_UV_CURVE_MEASURED_REVIEW_REQUIRED')
                else:segment,span=_span(compiled,pid,seams[0]['edge_a'],seams[0]['edge_b'],correspondence['source_v_cm'])
                segments.append(segment);evidence.append(span);homology.append({'piece':pid,'body_section_id':section['id'],**correspondence})
            if not segments:raise StudioError('No source material path matches the anatomical measurement requirement')
            path=_trace(compiled,segments);raw=sum(row['source_material_length_cm'] for row in evidence)
            proposals.append({**copy.deepcopy(request),**path,'status':'HOMOLOGY_PROPOSED_REVIEW_REQUIRED',
                'source_material_length_cm':raw,'body_girth_cm':body_girth,'source_spans':evidence,'homology':homology,
                'takeup':'EXPLICIT_DECLARATION_REQUIRED','ease':'NUMERIC_INTENT_REQUIRED',
                'ease_cm':None,'spatial_coverage':'NOT_MEASURED','open_front_overlap':'NOT_MEASURED',
                'admissible_for_fit':False,'qualification':'NONE',**extra})
        except StudioError as error:
            diagnostic={**copy.deepcopy(request),'code':'HOMOLOGOUS_SOURCE_PATH_NEEDS_DATA','message':str(error),
                'candidate_spans':evidence,'candidate_homology':homology,
                **({'source_join':error.measurement_diagnostic} if hasattr(error,'measurement_diagnostic')else{}),
                **({'guide_plane_material_candidate':error.guide_plane_diagnostic}if hasattr(error,'guide_plane_diagnostic')else{})}
            if landmark=='neck':
                try:diagnostic['source_open_collar_options']=collar_open_path_options(compiled,profile,guides,request)
                except StudioError as missing:diagnostic['source_open_collar_options_missing']=str(missing)
            diagnostics.append(diagnostic)
    if digest([compiled,profile,guides,required,body_regions,region_mapping,source_meshes,configuration])!=before:
        raise StudioError('Measurement proposal changed immutable material, guide, body or requirement data')
    result={'version':1,'status':'MEASUREMENT_PATH_PROPOSALS_NEED_REVIEW','proposals':proposals,'diagnostics':diagnostics,
        'compiled_sha256':digest(compiled),'body_profile_sha256':digest(profile),'guides_sha256':digest(guides),
        'source_mutated':False,'body_rescaled':False,'qualification':'NONE','acceptance':'NOT_GRANTED',
        'fitting':'NOT_EXECUTED','numeric_intent':'NOT_INFERRED_FROM_CLASSIFICATION'}
    result['proposal_sha256']=digest(result);return result


def propose_compiled_measurement_paths(project,compiled,guides_path,fit_path,body_regions_override=None,derived_mesh_refs=None,guide_policy_path=None):
    """Authenticate an in-memory source compilation without writing a temp file.

    Optional derived_mesh_refs maps actual component IDs to exact canonical
    prepare_pattern_assembly output refs, used only as source-UV triangulations.
    A refused preparation remains a refused placement; its original material
    correspondence can support this separate measurement hypothesis.
    """
    from .production_dossier import compile_project_dossier
    fit=contract('garment-fit',read_json(inside(project.root,fit_path)))
    if compile_project_dossier(project,compiled['source_ref']['path'],compiled['specification_source_ref']['path'])!=compiled:
        raise StudioError('Measurement source compilation differs from exact source reconstruction')
    def load(ref):
        path=inside(project.root,ref['path'])
        if sha(path)!=ref['sha256']:raise StudioError('Measurement proposal source reference changed')
        return read_json(path)
    if fit['body_ref']!=compiled['assembly_spec']['body_ref'] or fit['dossier_ref']!=compiled['source_ref']:
        raise StudioError('Measurement intent belongs to another approved source dossier or exact measured body')
    profile=load(fit['body_ref']);load(fit['source_ref'])
    from .native_evidence import native_origin
    native,origin=native_origin(project,lambda doc:
        (doc.get('operation')=='prepare_body_target' and doc.get('result',{}).get('artifacts',{}).get('profile')==fit['body_ref']) or
        (doc.get('operation')=='introduce_body_target' and doc.get('result',{}).get('profile_ref')==fit['body_ref']))
    if fit['body_ref']not in native['files'] or native['result'].get('profile_cache_key')!=profile['cache_key']:
        raise StudioError('Measurement proposals need their exact canonical measured native body profile')
    geometry_ref=(native['result']['artifacts']['geometry'] if native['operation']=='prepare_body_target'
                  else native['result']['geometry_ref'])
    geometry=load(geometry_ref)
    if profile['geometry_sha256']!=digest([geometry['vertices_cm'],geometry['faces']]):
        raise StudioError('Measurement body profile differs from its actual native skin topology')
    guides=read_json(inside(project.root,guides_path));declaration=body_regions_override or fit.get('body_regions')
    source_data={}
    for component in compiled['components']:
        if component['pipeline']!='PATTERN_SEWN':continue
        ref=component['package_source_ref'];path=inside(project.root,ref['path'])
        if sha(path)!=ref['sha256']:raise StudioError('Measurement source package changed')
        with zipfile.ZipFile(path)as archive:data=json.loads(archive.read('garment.json'))
        source_data[component['id']]=data
        if component['id']not in guides or guides[component['id']].get('source_sha256')!=digest(data):
            raise StudioError('Measurement guides belong to another exact garment source package')
    if guide_policy_path:
        from .garment_guide_policy import verify_guide_policy
        policy_path=inside(project.root,guide_policy_path);policy_bytes=policy_path.read_bytes()
        policy_sha256=hashlib.sha256(policy_bytes).hexdigest();policy=json.loads(policy_bytes)
        guide_reconstruction=verify_guide_policy(compiled,profile,geometry,geometry_ref,source_data,policy,guides)
        if sha(policy_path)!=policy_sha256:raise StudioError('Guide policy artifact changed during source reconstruction')
        guide_reconstruction['policy_ref']={'path':guide_policy_path,'sha256':policy_sha256}
    else:
        guide_reconstruction={'status':'NEEDS_DATA','diagnostics':[{'code':'GUIDE_POLICY_MISSING',
            'message':'A versioned source/body/skin/code policy is required to reconstruct the supplied guide coordinates'}],
            'qualification':'NONE','admissible_for_fit':False,'comparison':'NOT_EXECUTED'}
    source_meshes={};mesh_origins={}
    for cid,ref in sorted((derived_mesh_refs or {}).items()):
        if cid not in source_data:raise StudioError('Measurement derived mesh belongs to an undeclared source component')
        payload=load(ref);component=next(row for row in compiled['components']if row['id']==cid)
        garment_path=inside(project.root,payload['source_garment'])
        if (payload.get('component_id')!=cid or payload.get('source_garment_sha256')!=digest(source_data[cid])
                or payload.get('package_sha256')!=component['package_source_ref']['sha256']
                or read_json(garment_path)!=source_data[cid]):
            raise StudioError('Measurement derived mesh changed its immutable exact source package or component')
        from .native_evidence import native_observation_origin
        preparation,receipt=native_observation_origin(project,lambda doc:
            doc.get('operation')=='prepare_pattern_assembly' and doc.get('result',{}).get('derived_mesh')==ref
            and doc.get('result',{}).get('component_id')==cid,observed_artifact_ref=ref)
        if ref not in preparation['files']:raise StudioError('Measurement source triangulation has no actual canonical native preparation origin')
        source_meshes[cid]=payload;mesh_origins[cid]={'derived_mesh_ref':copy.deepcopy(ref),'native_preparation_origin':receipt,
            'placement_readiness':preparation['result']['readiness'],'placement_qualification':'NOT_TRANSFERRED'}
    descriptor=None;failure=None
    if declaration:
        from .body_region_sections import body_region_descriptor
        try:
            load(declaration['specification_ref'])
            descriptor=body_region_descriptor(project,declaration['specification_ref']['path'],declaration['supplement_ref'])
        except StudioError as error:failure=str(error)
    result=propose_measurement_paths(compiled,profile,guides,fit['required_measurements'],descriptor,
        declaration.get('landmark_sections',[])if declaration else [],source_meshes,fit['classification'])
    result['input_refs']=[{'path':p,'sha256':sha(inside(project.root,p))} for p in (guides_path,fit_path)]+[fit['body_ref']]
    result['native_body_origin']=origin
    result['guide_reconstruction']=guide_reconstruction
    if guide_policy_path:result['input_refs'].append(guide_reconstruction['policy_ref'])
    if mesh_origins:result['source_uv_triangulations']=mesh_origins
    if declaration:result['body_regions']=copy.deepcopy(declaration)
    if failure:result['body_region_source_reconciliation']={'status':'NEEDS_DATA','message':failure}
    if guide_policy_path and sha(policy_path)!=policy_sha256:
        raise StudioError('Guide policy artifact changed during measurement reconstruction')
    result['proposal_sha256']=digest({k:v for k,v in result.items()if k!='proposal_sha256'})
    return result


def propose_project_measurement_paths(project,compiled_path,guides_path,fit_path,body_regions_override=None,derived_mesh_refs=None,guide_policy_path=None):
    """Read the saved compilation and delegate to the same read-only kernel."""
    compiled=read_json(inside(project.root,compiled_path))
    result=propose_compiled_measurement_paths(project,compiled,guides_path,fit_path,body_regions_override,derived_mesh_refs,guide_policy_path)
    result['input_refs'].insert(0,{'path':compiled_path,'sha256':sha(inside(project.root,compiled_path))})
    result['proposal_sha256']=digest({k:v for k,v in result.items()if k!='proposal_sha256'})
    return result
