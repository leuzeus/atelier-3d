"""Metric, source-UV volume guides; these guides do not qualify fitting."""
import math

from a3d.core import StudioError


def length(a,b):return math.sqrt(math.fsum((x-y)**2 for x,y in zip(a,b)))


def sample_curve(curve,s):
    if (len(curve)<2 or not math.isfinite(s) or any(len(p)!=3 or not all(math.isfinite(x) for x in p) for p in curve)):
        raise StudioError('Volume guide requires finite 3D points and an arc coordinate')
    lengths=[length(a,b) for a,b in zip(curve,curve[1:])]
    if min(lengths)<=1e-12:raise StudioError('Volume guide has a zero-length segment')
    total=math.fsum(lengths)
    if s<0 or s>total:raise StudioError('Volume guide arc exceeds its explicit polyline')
    cumulative=0.
    for index,(a,b,edge) in enumerate(zip(curve,curve[1:],lengths)):
        end=cumulative+edge
        if s<=end or index==len(lengths)-1:
            t=(s-cumulative)/edge
            return [x+(y-x)*t for x,y in zip(a,b)]
        cumulative=end


def edge_coordinate(piece,edge,v):
    points=[piece['vertices'][i] for i in piece['edges'][edge]]
    hits=[]
    for a,b in zip(points,points[1:]):
        if abs(a[1]-b[1])<1e-10:continue
        if min(a[1],b[1])-1e-8<=v<=max(a[1],b[1])+1e-8:
            t=(v-a[1])/(b[1]-a[1]);hits.append(a[0]+t*(b[0]-a[0]))
    if not hits or max(hits)-min(hits)>1e-5:
        raise StudioError('Volume guide row needs a unique source named-edge intersection')
    return math.fsum(hits)/len(hits)


def half_ellipse(half_perimeter,aspect,center_xy,z,side,segments=256):
    """Set the declared auxiliary arc length; never scale source UV."""
    base=[[side*aspect*math.sin(math.pi*i/segments),-math.cos(math.pi*i/segments)] for i in range(segments+1)]
    scale=half_perimeter/math.fsum(length(a,b) for a,b in zip(base,base[1:]))
    return [[center_xy[0]+scale*x,center_xy[1]+scale*y,z] for x,y in base]


def extend_tangent(curve,extra=2.):
    result=[list(p) for p in curve]
    a,b=result[-2:];edge=length(a,b)
    result.append([y+(y-x)*extra/edge for x,y in zip(a,b)])
    return result


def _smooth_rows(rows,key,window,slope):
    result=[]
    for row in rows:
        values=[(other[key],max(0.,1-abs(other['v_cm']-row['v_cm'])/(window/2))) for other in rows]
        result.append(math.fsum(value*weight for value,weight in values)/math.fsum(weight for _,weight in values))
    # Bound only the variation of the auxiliary guide. Source coordinates,
    # source girths and simulation strain gates are retained independently.
    for _ in range(64):
        changed=False
        for i in range(len(rows)-1):
            limit=slope*(rows[i+1]['v_cm']-rows[i]['v_cm']);delta=result[i+1]-result[i]
            if abs(delta)>limit+1e-9:
                correction=(abs(delta)-limit)*.5*(1 if delta>0 else -1)
                result[i]+=correction;result[i+1]-=correction;changed=True
        if not changed:break
    # Finish with an explicit bound even if the symmetric projection exhausted
    # its iteration budget. This modifies the guide alone, not source metrics.
    for i in range(1,len(rows)):
        bound=slope*(rows[i]['v_cm']-rows[i-1]['v_cm'])
        result[i]=max(result[i-1]-bound,min(result[i-1]+bound,result[i]))
    return result


def _origin_convention(data,group):
    if group.get('uv_origin_cm')!=[0.,0.]:raise StudioError('Volume guide requires an explicit source UV origin convention [0,0]')
    for role in ('center','back'):
        piece=data['pieces'][group[role]]
        if any(abs(piece['vertices'][i][0])>1e-8 for i in piece['edges']['center']):
            raise StudioError('Volume guide source center edge does not match its declared zero UV origin')
    for role in ('front','side','back'):
        piece=data['pieces'][group[role]]
        if any(abs(piece['vertices'][i][1])>1e-8 for i in piece['edges']['hem']):
            raise StudioError('Volume guide source hem does not match its declared zero UV origin')


def shoulder_curve(neck_length,neck_radius,neck_center,shoulder,side,maximum_u,is_back):
    # The two source neckline arc lengths end at one sourced shoulder guide.
    # Front starts at the front opening; back starts at the center back.
    count=max(8,math.ceil(neck_length/.25))
    start=math.pi if is_back else 0.
    direction=-1 if is_back else 1
    curve=[]
    for i in range(count+1):
        theta=start+direction*(neck_length/neck_radius)*(i/count)
        curve.append([neck_center[0]+side*neck_radius*math.sin(theta),
            neck_center[1]-neck_radius*math.cos(theta),neck_center[2]])
    anchor=curve[-1];vector=[b-a for a,b in zip(anchor,shoulder)];size=length(anchor,shoulder)
    distance_to_cover=maximum_u-neck_length+3.
    curve.append([a+v*distance_to_cover/size for a,v in zip(anchor,vector)])
    return curve


def volume_frames(data,groups,body_frame,upper_blend=0.,guide_smoothing_cm=40.):
    """Build explicit curves from source side seams and a sourced body frame.

    Each group names a source front, center, side and back. Source sections seed
    a bounded, smoothed guide; their raw girths remain separately reported.
    A separately declared upper guide bends toward shoulders. Open seam gaps
    are measured rather than erased by changing the immutable source metric.
    """
    if not math.isfinite(upper_blend) or not 0<=upper_blend<=1:raise StudioError('Upper guide blend must be bounded')
    if not math.isfinite(guide_smoothing_cm) or guide_smoothing_cm<=0:raise StudioError('Volume guide smoothing window must be positive and finite')
    panels={};report={'body_frame':body_frame,'upper_blend':upper_blend,'sections':[],
        'status':'UNQUALIFIED_PLACEMENT_HYPOTHESIS','source_uv_scaled':False,
        'body_changed':False,'explicit_curve_tangent_extension_cm':2.,
        'guide_smoothing':{'window_cm':guide_smoothing_cm,'half_girth_max_slope_cm_per_cm':.45,'side_offset_max_slope_cm_per_cm':.2,
            'purpose':'geometric guide variation only; raw source girth and quality gates unchanged'}}
    for group in groups:
        _origin_convention(data,group)
        front=data['pieces'][group['front']];side_piece=data['pieces'][group['side']];back=data['pieces'][group['back']]
        shared_top=min(max(front['vertices'][i][1] for i in front['edges']['side']),
            max(side_piece['vertices'][i][1] for i in side_piece['edges']['front']),
            max(back['vertices'][i][1] for i in back['edges']['side']))
        maximum_v=max(p[1] for pid in group['pieces'] for p in data['pieces'][pid]['vertices'])
        row_values=sorted(set([0.,shared_top,maximum_v]+[float(v) for v in range(5,math.ceil(shared_top),5)]+[shared_top+f*(maximum_v-shared_top) for f in (.25,.5,.75)]))
        raw_rows=[]
        for v in row_values:
            sv=min(v,shared_top)
            f=edge_coordinate(front,'side',sv);sf=edge_coordinate(side_piece,'front',sv)
            sb=edge_coordinate(side_piece,'back',sv);b=edge_coordinate(back,'side',sv)
            raw_rows.append({'v_cm':v,'source_v_cm':sv,'front_cm':f,'side_cm':sb-sf,'back_cm':b,
                'half_girth_cm':f+(sb-sf)+b,'side_arc_offset_cm':f-sf})
        half_values=_smooth_rows(raw_rows,'half_girth_cm',guide_smoothing_cm,.45)
        offset_values=_smooth_rows(raw_rows,'side_arc_offset_cm',guide_smoothing_cm,.2)
        frames={pid:[] for pid in group['pieces']}
        for row_index,v in enumerate(row_values):
            raw=raw_rows[row_index];half=half_values[row_index];side_offset=offset_values[row_index]
            curve=half_ellipse(half,body_frame['aspect_ratio'],body_frame['center_xy_cm'],
                body_frame['hem_z_cm']+v,group['side_sign'])
            curve=extend_tangent(curve)
            report['sections'].append({'side':group['side_sign'],'source_v_cm':raw['source_v_cm'],'v_cm':v,
                'raw_source':raw,'applied_guide':{'half_girth_cm':half,'side_arc_offset_cm':side_offset},
                'above_underarm_extension':v>shared_top})
            for pid in group['pieces']:
                direction=-1 if pid==group['back'] else 1
                offset=half if direction==-1 else side_offset if pid==group['side'] else 0.
                target=curve
                factor=upper_blend*max(0.,min(1.,(v-(shared_top-15.))/(maximum_v-(shared_top-15.))))
                if factor and pid!=group['side']:
                    piece=data['pieces'][pid];maximum_u=max(p[0] for p in piece['vertices'])
                    neck_length=group['back_neck_cm'] if pid==group['back'] else group['front_neck_cm']
                    top=shoulder_curve(neck_length,(group['front_neck_cm']+group['back_neck_cm'])/math.pi,
                        body_frame['neck_center_cm'],body_frame['shoulders_cm'][str(group['side_sign'])],
                        group['side_sign'],maximum_u,pid==group['back'])
                    # Reparameterize the blended guide by its actual arc. UV is
                    # never averaged with another source island or rescaled.
                    us=[maximum_u*i/128 for i in range(129)]
                    target=[]
                    for u in us:
                        old=sample_curve(curve,offset+direction*u);new=sample_curve(top,u)
                        # Carry each row's own vertical material coordinate.
                        # Blending every row toward one fixed shoulder height
                        # would collapse its v metric near the upper boundary.
                        new[2]+=v-maximum_v
                        target.append([(1-factor)*x+factor*y for x,y in zip(old,new)])
                    total=math.fsum(length(a,b) for a,b in zip(target,target[1:]))
                    target=extend_tangent(target,max(2.,maximum_u-total+2.))
                    offset=0.;direction=1
                frames[pid].append({'v_cm':v,'arc_offset_cm':offset,'curve_cm':target})
        for pid,sections in frames.items():
            panels[pid]={'source_ref':body_frame['source_ref']+'; named source contour girth; explicit unqualified upper guide '+pid,
                'arc_sections':sections,'u_direction':1 if upper_blend and pid!=group['side'] else -1 if pid==group['back'] else 1}
            # Arc direction is a frame-level contract. If the back guide uses
            # positive source-u above, use positive-u below as well.
            if upper_blend and pid==group['back']:
                for row in sections:
                    if row['arc_offset_cm']:
                        old=row['curve_cm'];offset=row['arc_offset_cm']
                        maximum_u=max(p[0] for p in data['pieces'][pid]['vertices'])
                        row['curve_cm']=[sample_curve(old,offset-maximum_u*i/128) for i in range(129)]
                        row['curve_cm']=extend_tangent(row['curve_cm'])
                        row['arc_offset_cm']=0.
    return panels,report


def paired_volume_frames(data,group,body_frame,guide_smoothing_cm=40.):
    """A real front/back cut, without inventing opening or side panels.

    Named source contours determine signed material coordinates and raw girth.
    Rows above the side seam retain their v coordinate; shoulder shaping and
    seam closure need separate measured preparation and qualification.
    """
    if group.get('uv_origin_cm')!=[0.,0.]:
        raise StudioError('Paired torso guide requires the source UV origin convention [0,0]')
    if not math.isfinite(guide_smoothing_cm) or guide_smoothing_cm<=0:
        raise StudioError('Paired torso smoothing window must be positive and finite')
    roles={role:data['pieces'][group[role]] for role in ('front','back')}
    signs={};edges=group['source_edges']
    for role,piece in roles.items():
        declared=edges[role]
        if not all(name in piece['edges'] for name in declared.values()):
            raise StudioError('Paired torso guide references a missing named source edge: '+group[role])
        if any(abs(piece['vertices'][i][1])>1e-8 for i in piece['edges'][declared['hem']]):
            raise StudioError('Paired torso source hem must match its declared zero UV origin')
        values=[piece['vertices'][i][0] for i in piece['edges'][declared['side']]]
        if not values or not all(math.isfinite(v) for v in values) or min(values)*max(values)<=0:
            raise StudioError('Paired torso side edge needs one nonzero source transverse direction')
        signs[role]=1 if values[0]>0 else -1
        if any(signs[role]*point[0]<-1e-8 for point in piece['vertices']):
            raise StudioError('Paired torso panel crosses its declared source center')
    back=roles['back']
    if any(abs(back['vertices'][i][0])>1e-8 for i in back['edges'][edges['back']['center']]):
        raise StudioError('Paired torso back center must match its declared zero UV origin')
    shared_top=min(max(piece['vertices'][i][1] for i in piece['edges'][edges[role]['side']])
                   for role,piece in roles.items())
    maximum_v=max(point[1] for piece in roles.values() for point in piece['vertices'])
    if shared_top<=0 or maximum_v<shared_top:
        raise StudioError('Paired torso side contour has no usable longitudinal range')
    rows=sorted(set([0.,shared_top,maximum_v]+[float(v) for v in range(5,math.ceil(shared_top),5)]))
    raw=[]
    for v in rows:
        widths={role:signs[role]*edge_coordinate(piece,edges[role]['side'],min(v,shared_top))
                for role,piece in roles.items()}
        if min(widths.values())<=0:
            raise StudioError('Paired torso source section is collapsed')
        raw.append({'v_cm':v,'source_v_cm':min(v,shared_top),
                    'front_cm':widths['front'],'back_cm':widths['back'],
                    'half_girth_cm':math.fsum(widths.values())})
    # A pair has no intervening side panel to absorb an altered guide offset.
    # Smoothing its half-girth independently of both side contours can make
    # their interiors overlap or open a seam that matched the source metric.
    smoothed=_smooth_rows(raw,'half_girth_cm',guide_smoothing_cm,.45)
    covering=[max(row['half_girth_cm'],value) for row,value in zip(raw,smoothed)]
    # Minimal Lipschitz majorant: retain source coverage while bounding the
    # change of the auxiliary arc, including at the end of the side seam.
    half_values=[max(value-.45*abs(row['v_cm']-other['v_cm'])
                     for other,value in zip(raw,covering)) for row in raw]
    panels={group[role]:{'source_ref':body_frame['source_ref']+'; paired source contours '+group[role],
                         'arc_sections':[],'u_direction':signs[role]*(1 if role=='front' else -1)}
            for role in roles}
    sections=[]
    for row,half in zip(raw,half_values):
        curve=extend_tangent(half_ellipse(half,body_frame['aspect_ratio'],body_frame['center_xy_cm'],
                          body_frame['hem_z_cm']+row['v_cm'],group['side_sign']))
        sections.append({'v_cm':row['v_cm'],'raw_source':row,
                         'applied_guide':{'half_girth_cm':half},'above_underarm_extension':row['v_cm']>shared_top})
        for role in roles:
            panels[group[role]]['arc_sections'].append({'v_cm':row['v_cm'],
                'arc_offset_cm':0. if role=='front' else half,'curve_cm':curve})
    return panels,{'status':'UNQUALIFIED_PLACEMENT_HYPOTHESIS','cut':'FRONT_BACK_PAIR',
                   'body_frame':body_frame,'sections':sections,'source_uv_scaled':False,
                   'body_changed':False,'fabricated_source_panels':[],
                   'guide_smoothing':{'mode':'SOURCE_COVERING_SMOOTHED_GIRTH','window_cm':guide_smoothing_cm,
                                      'half_girth_max_slope_cm_per_cm':.45,
                                      'source_coverage':'NO_HALF_GIRTH_BELOW_RAW_PAIR'},
                   'shoulder_shaping':'NOT_EXECUTED','closure':'NOT_EXECUTED'}
