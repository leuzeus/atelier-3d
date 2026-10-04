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


def apply_measured_sections(panels, report, group, profile, skin_sections=None):
    sections = sorted((s for s in profile['sections'] if s.get('status') == 'MEASURED'), key=lambda s:s['height_cm'])
    if not sections:
        raise StudioError('No measured torso sections are available')
    measured = [(s, *half_section(s, group['side_sign'])) for s in sections]
    evidence = []
    for row in report['sections']:
        height = report['body_frame']['hem_z_cm']+row['v_cm']
        upper=group.get('measured_shoulder_transition')
        if upper and row['v_cm'] >= upper['source_start_v_cm']:
            # At and above the arm opening, a closed whole-skin circumference
            # may include connected arms. The following shoulder kernel uses
            # the real skin anchors and source material edges instead.
            # Its zero-blend base needs material continuity with the preceding
            # qualified guide, rather than the unrelated auxiliary ellipse.
            # This is a translated material guide, never a body measurement at
            # the new height and never an arm-containing torso circumference.
            bases=[item for item in evidence if item.get('measured_section_heights_cm') and
                item['source_v_cm'] < upper['source_start_v_cm'] and item.get('surface_guide') in
                ('ACTUAL_SKIN_WITH_APPROVED_FREE_FRONT_OPENING','BRACKETED_MEASURED_SECTION_AT_ACTUAL_HEIGHT')]
            if not bases:
                raise StudioError('Shoulder material continuity requires a qualified lower torso guide')
            base=max(bases,key=lambda item:item['source_v_cm'])
            delta=row['v_cm']-base['source_v_cm']
            for role in ('front','back'):
                sections=panels[group[role]]['arc_sections']
                source=next(item for item in sections if item['v_cm']==base['source_v_cm'])
                target=next(item for item in sections if item['v_cm']==row['v_cm'])
                target['curve_cm']=[[p[0],p[1],p[2]+delta] for p in source['curve_cm']]
                target['arc_offset_cm']=source['arc_offset_cm']
            evidence.append({'source_v_cm':row['v_cm'],'guide_height_cm':height,
                'surface_guide':'MEASURED_SKIN_SHOULDER_MATERIAL_PLANE_TRANSITION',
                'source_shoulder_transition':upper,'body_surface_extrapolated':False,
                'material_continuity_base_v_cm':base['source_v_cm'],
                'material_guide_translation_cm':[0.,0.,delta],
                'measurement_at_requested_height':'NOT_USED',
                'continuity_only':True,'source_uv_scaled':False,
                'circumference_of_connected_arms_used':False,'contact_assessment':'REQUIRED'})
            continue
        if height < measured[0][0]['height_cm']:
            # Open lower panels may extend below the measured torso region.
            # Keep their source-length auxiliary guide and explicitly refrain
            # from describing a hip contour translated downward as skin.
            evidence.append({'source_v_cm':row['v_cm'],'guide_height_cm':height,
                'surface_guide':'SOURCE_AUXILIARY_BELOW_MEASURED_TORSO',
                'measured_section_heights_cm':[], 'body_surface_extrapolated':False,
                'contact_assessment':'REQUIRED'})
            continue
        if height > measured[-1][0]['height_cm']:
            error = StudioError('Source torso guide height exceeds the actual measured section domain; measure the missing skin region')
            error.guide_diagnostic = {'reason':'BODY_SECTION_HEIGHT_UNAVAILABLE','guide_height_cm':height,
                'measured_height_domain_cm':[measured[0][0]['height_cm'],measured[-1][0]['height_cm']],
                'source_v_cm':row['v_cm'], 'body_surface_extrapolated':False}
            raise error
        extra = next((s for s in (skin_sections or {}).get('sections',[]) if abs(s['height_cm']-height)<1e-8),None)
        if extra is not None:
            if extra.get('status') != 'MEASURED':
                error=StudioError('Actual native skin section at the requested guide height is not qualified')
                error.guide_diagnostic={'reason':'BODY_SKIN_SECTION_NOT_QUALIFIED','guide_height_cm':height,
                    'source_v_cm':row['v_cm'],'section':extra,'body_surface_extrapolated':False}
                raise error
            a=b=(extra,*half_section(extra,group['side_sign']))
        else:
            a = max((m for m in measured if m[0]['height_cm'] <= height),
                key=lambda m:m[0]['height_cm'], default=measured[0])
            b = min((m for m in measured if m[0]['height_cm'] >= height),
                key=lambda m:m[0]['height_cm'], default=measured[-1])
        span = b[0]['height_cm']-a[0]['height_cm']
        rejected = [s for s in profile['sections'] if a[0]['height_cm'] < s['height_cm'] < b[0]['height_cm']
                    and s.get('status') != 'MEASURED']
        if rejected:
            error = StudioError('Torso guide crosses unqualified measured sections; provide actual skin sections in the missing region')
            error.guide_diagnostic = {'reason':'BODY_SECTION_INTERVAL_UNQUALIFIED','source_v_cm':row['v_cm'],
                'guide_height_cm':height,'measured_section_heights_cm':[a[0]['height_cm'],b[0]['height_cm']],
                'unqualified_section_heights_cm':[s['height_cm'] for s in rejected],
                'body_surface_extrapolated':False,'garment_impossibility':'NOT_ESTABLISHED'}
            raise error
        factor = 0. if span <= 0 else max(0.,min(1.,(height-a[0]['height_cm'])/span))
        curve = []
        for i in range(257):
            p = list(a[1][-1]) if i == 256 else sample_curve(a[1],a[2]*i/256)
            q = list(b[1][-1]) if i == 256 else sample_curve(b[1],b[2]*i/256)
            curve.append([(1-factor)*p[0]+factor*q[0],(1-factor)*p[1]+factor*q[1],height])
        body_half = sum(math.dist(p,q) for p,q in zip(curve,curve[1:]))
        half = row['applied_guide']['half_girth_cm']
        opening=group.get('source_open_front',{})
        open_interval=opening.get('free_edge_v_domain_cm',[])
        deficit=body_half-half
        if deficit>1e-7 and len(open_interval)==2 and open_interval[0] <= row['v_cm'] <= open_interval[1]:
            # Shift both partners by the same arc length: permanent side and
            # centre-back correspondences remain intact. Only the empty front
            # opening grows; the material UV and source lengths never change.
            for role in ('front','back'):
                target=next(s for s in panels[group[role]]['arc_sections'] if s['v_cm']==row['v_cm'])
                target['curve_cm']=extend_tangent(curve)
                target['arc_offset_cm']+=deficit
            evidence.append({'source_v_cm':row['v_cm'],'guide_height_cm':height,
                'measured_section_heights_cm':[a[0]['height_cm'],b[0]['height_cm']],
                'surface_half_girth_cm':body_half,'guide_half_girth_cm':half,
                'empty_front_arc_increase_cm':deficit,'source_open_front':opening,
                'source_uv_scaled':False,'body_surface_extrapolated':False,
                'surface_guide':'ACTUAL_SKIN_WITH_APPROVED_FREE_FRONT_OPENING',
                'inner_front_coverage':'REQUIRES_CONTACT_AND_DRESSING_ASSESSMENT'})
            continue
        if body_half > half+1e-7:
            error = StudioError('Source torso guide has a measured capacity deficit at its actual height; review open-front/source correspondence before changing the cut')
            error.guide_diagnostic = {'reason':'SOURCE_GUIDE_CAPACITY_DEFICIT','source_v_cm':row['v_cm'],
                'guide_height_cm':height,'measured_section_heights_cm':[a[0]['height_cm'],b[0]['height_cm']],
                'measured_half_girth_cm':body_half,'source_guide_half_girth_cm':half,'deficit_cm':body_half-half,
                'side_sign':group['side_sign'],'body_surface_extrapolated':False,
                'garment_impossibility':'NOT_ESTABLISHED','body_change':'NOT_PROPOSED','cut_change':'NOT_PROPOSED'}
            raise error
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
                         'body_surface_extrapolated':False,
                         'surface_guide':'BRACKETED_MEASURED_SECTION_AT_ACTUAL_HEIGHT'})
    report.update(surface_guide='MEASURED_SECTION_CONTOURS', measured_sections=evidence,
                  body_projection='NOT_EXECUTED', qualification='NONE')
    return panels, report
