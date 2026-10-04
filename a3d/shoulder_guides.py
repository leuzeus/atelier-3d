"""Source shoulder frames and measured anatomical placement hypotheses."""
import math

from .anatomy_profile import unit
from .contact_geometry import dot
from .core import StudioError
from .preform_volume import sample_curve, extend_tangent


def material_plane(piece, shoulder_edge, sign, ridge, shoulder_surface, chest):
    points = sorted([sign*piece['vertices'][i][0], piece['vertices'][i][1]]
                    for i in piece['edges'][shoulder_edge])
    anchor, end = points[0], points[-1]
    delta = [end[i]-anchor[i] for i in range(2)]
    length = math.dist(anchor, end)
    if length < 1e-8 or any(abs((p[0]-anchor[0])*delta[1]-(p[1]-anchor[1])*delta[0]) > 1e-6
                            for p in points):
        raise StudioError('Upper guide needs a straight noncollapsed source shoulder edge')
    tangent_uv = [x/length for x in delta]
    up_uv = [-tangent_uv[1], tangent_uv[0]]
    tangent = unit([b-a for a,b in zip(ridge, shoulder_surface)])
    inward = [ridge[i]-chest[i] for i in range(3)]
    projection = dot(inward, tangent)
    normal = unit([inward[i]-projection*tangent[i] for i in range(3)])
    def point(u, v):
        du, dv = u-anchor[0], v-anchor[1]
        along = du*tangent_uv[0]+dv*tangent_uv[1]
        across = du*up_uv[0]+dv*up_uv[1]
        return [ridge[i]+along*tangent[i]+across*normal[i] for i in range(3)]
    return point, {'source_shoulder_uv_cm': points, 'source_shoulder_length_cm': length,
                   'ridge_anchor_cm': ridge, 'measured_shoulder_cm': shoulder_surface,
                   'plane_tangent': tangent, 'plane_normal': normal}


def shape_paired_shoulders(data, group, body_frame, panels, report, blend):
    if body_frame.get('shoulder_anchor_kind') != 'MEASURED_BODY_SURFACE':
        raise StudioError('Garment shoulder frames require a measured skin anchor, not an internal joint center')
    if not math.isfinite(blend) or not 0 < blend <= 1:
        raise StudioError('Upper shoulder blend must be finite, positive and at most one')
    neck = body_frame['neck_center_cm']
    radius = (group['front_neck_cm']+group['back_neck_cm'])/math.pi
    side = group['side_sign']
    ridge = [neck[0]+side*radius, neck[1], neck[2]]
    shoulder_surface = body_frame['shoulders_cm'][str(side)]
    low, high = body_frame['chest_bounds_xy_cm']
    top = max(p[1] for piece in data['pieces'].values() for p in piece['vertices'])
    underarm = min(max(piece['vertices'][i][1] for i in piece['edges'][group['source_edges'][role]['side']])
                   for role,piece in ((r, data['pieces'][group[r]]) for r in ('front','back')))
    start = underarm
    if top <= start:
        raise StudioError('Upper guide has no source longitudinal transition domain')
    frames = {}
    for role in ('front','back'):
        pid = group[role]; piece = data['pieces'][pid]
        declared = group['source_edges'][role]
        edge = declared.get('shoulder')
        if edge not in piece['edges']:
            raise StudioError('Upper guide needs an explicit source shoulder edge: '+pid)
        sign = 1 if piece['vertices'][piece['edges'][declared['side']][0]][0] > 0 else -1
        chest = [(low[0]+high[0])/2, high[1] if role == 'back' else low[1],
                 body_frame['chest_height_cm']]
        plane, frames[role] = material_plane(piece, edge, sign, ridge, shoulder_surface, chest)
        neck_u = frames[role]['source_shoulder_uv_cm'][0][0]
        if neck_u <= 0:
            raise StudioError('Upper paired guide needs a positive source shoulder neckline stop')
        maximum_u = max(sign*p[0] for p in piece['vertices'])
        frame = panels[pid]
        old_direction = frame['u_direction']
        for row in frame['arc_sections']:
            factor = blend*max(0., min(1., (row['v_cm']-start)/(top-start)))
            target = []
            for index in range(129):
                u = maximum_u*index/128
                old = sample_curve(row['curve_cm'], row['arc_offset_cm']+old_direction*sign*u)
                new = plane(u, row['v_cm'])
                if u < neck_u:
                    t = u/neck_u
                    theta = t*math.pi/2
                    neck_point = [neck[0]+side*radius*math.sin(theta),
                                  neck[1]+(1 if role=='back' else -1)*radius*math.cos(theta),
                                  body_frame['hem_z_cm']+row['v_cm']]
                    weight = t*t*(3-2*t)
                    new = [(1-weight)*a+weight*b for a,b in zip(neck_point,new)]
                target.append([(1-factor)*a+factor*b for a,b in zip(old,new)])
            total = sum(math.dist(a,b) for a,b in zip(target,target[1:]))
            row['curve_cm'] = extend_tangent(target, max(2., maximum_u-total+2.))
            row['arc_offset_cm'] = 0.
        frame['u_direction'] = sign
    if frames['front']['source_shoulder_uv_cm'] != frames['back']['source_shoulder_uv_cm']:
        raise StudioError('Paired shoulder material frames disagree; review source correspondence')
    report.update(shoulder_shaping='MEASURED_MATERIAL_PLANES', upper_blend=blend,
                  shoulder_anchor_kind=body_frame['shoulder_anchor_kind'],
                  upper_material_frames=frames, transition_start_v_cm=start,
                  collision_assessment='REQUIRED', qualification='NONE')
    return panels, report
