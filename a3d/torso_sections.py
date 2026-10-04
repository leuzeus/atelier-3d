"""Auxiliary guides from measured surface contours; no body projection."""
import math

from .core import StudioError
from .preform_volume import sample_curve, extend_tangent


def half_section(section, side):
    if section.get('status') != 'MEASURED' or side not in (-1, 1):
        raise StudioError('Torso surface guide requires a measured closed section and declared side')
    points = section['curve_cm']
    low, high = section['bounds_xy_cm']
    center = (low[0]+high[0])/2
    cuts = []
    for index,(a,b) in enumerate(zip(points,points[1:]+points[:1])):
        if (a[0] <= center < b[0]) or (b[0] <= center < a[0]):
            t = (center-a[0])/(b[0]-a[0])
            cuts.append((index, [center, a[1]+t*(b[1]-a[1]), section['height_cm']]))
    if len(cuts) != 2:
        raise StudioError('Measured torso half has ambiguous center-plane intersections')
    (i,a),(j,b) = cuts
    candidates = [[a]+points[i+1:j+1]+[b], [b]+points[j+1:]+points[:i+1]+[a]]
    usable = [curve for curve in candidates if all(side*(p[0]-center) >= -1e-7 for p in curve)]
    if len(usable) != 1:
        raise StudioError('Measured torso section cannot identify one sourced lateral contour')
    curve = usable[0]
    # Profile forward is positive; the existing preform convention uses -forward.
    if curve[0][1] < curve[-1][1]:
        curve = list(reversed(curve))
    curve = [[p[0], -p[1], p[2]] for p in curve]
    length = sum(math.dist(a,b) for a,b in zip(curve,curve[1:]))
    if length <= 0:
        raise StudioError('Measured torso half contour is collapsed')
    return curve, length


def apply_measured_sections(panels, report, group, profile):
    chest_height = profile['landmarks']['chest']['section']['height_cm']
    sections = sorted((s for s in profile['sections'] if s.get('status') == 'MEASURED'
                       and s['height_cm'] <= chest_height), key=lambda s:s['height_cm'])
    if not sections:
        raise StudioError('No measured torso sections are available below the chest landmark')
    measured = [(s, *half_section(s, group['side_sign'])) for s in sections]
    evidence = []
    for row in report['sections']:
        height = report['body_frame']['hem_z_cm']+row['v_cm']
        a = max((m for m in measured if m[0]['height_cm'] <= height),
                key=lambda m:m[0]['height_cm'], default=measured[0])
        b = min((m for m in measured if m[0]['height_cm'] >= height),
                key=lambda m:m[0]['height_cm'], default=measured[-1])
        span = b[0]['height_cm']-a[0]['height_cm']
        factor = 0. if span <= 0 else max(0.,min(1.,(height-a[0]['height_cm'])/span))
        curve = []
        for i in range(257):
            p = list(a[1][-1]) if i == 256 else sample_curve(a[1],a[2]*i/256)
            q = list(b[1][-1]) if i == 256 else sample_curve(b[1],b[2]*i/256)
            curve.append([(1-factor)*p[0]+factor*q[0],(1-factor)*p[1]+factor*q[1],height])
        body_half = sum(math.dist(p,q) for p,q in zip(curve,curve[1:]))
        half = row['applied_guide']['half_girth_cm']
        if body_half > half+1e-7:
            raise StudioError('Source torso guide has a measured capacity deficit; review placement/correspondence before changing the cut')
        center = [(curve[0][k]+curve[-1][k])/2 for k in (0,1)]
        scale = half/body_half
        curve = [[center[0]+scale*(p[0]-center[0]),center[1]+scale*(p[1]-center[1]),height] for p in curve]
        curve = extend_tangent(curve)
        for role in ('front','back'):
            target = next(s for s in panels[group[role]]['arc_sections'] if s['v_cm'] == row['v_cm'])
            target['curve_cm'] = curve
        evidence.append({'source_v_cm':row['v_cm'],'guide_height_cm':height,
                         'measured_section_heights_cm':[a[0]['height_cm'],b[0]['height_cm']],
                         'surface_half_girth_cm':body_half,'guide_half_girth_cm':half,
                         'auxiliary_radial_factor':scale,
                         'above_measured_chest_extension':height>chest_height})
    report.update(surface_guide='MEASURED_SECTION_CONTOURS', measured_sections=evidence,
                  body_projection='NOT_EXECUTED', qualification='NONE')
    return panels, report
