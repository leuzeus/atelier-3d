"""Auxiliary guides from measured surface contours; no body projection."""
import math

from .core import StudioError, digest
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


def source_bound_torso_cages(data, panels, *, subdivisions=8):
    """Synchronize actual permanent torso boundaries in a source-UV cage.

    The existing measured-skin/shoulder guide remains the volume hypothesis.
    At each shared source boundary control, its proposals receive their
    unweighted common mean. Integer refinement of matching source corner
    partitions then gives both partners the same piecewise-linear boundary
    for the complete normalized arc domain, including between guide rows.
    This neither preserves/reviews front coverage nor grants metric/contact
    admission. Relations to pieces outside ``panels`` are left untouched.
    """
    # The source-only refinement is shared with limb cages. A local import
    # avoids the dispatcher -> semantic placement -> torso import cycle.
    from .garment_guides import _source_limb_mesh
    from .pattern_assembly import _compile_arc_sections, _section_point
    from .sewing import chain_lengths, edge_chain

    if type(subdivisions) is not int or not 2 <= subdivisions <= 16:
        raise StudioError('Torso cage subdivisions must be an integer in 2..16')
    if (not isinstance(panels, dict) or not panels or len(panels) > 16
            or not set(panels) <= set(data.get('pieces', {}))):
        raise StudioError('Torso cages require exact source pieces within the fixed panel budget')
    try:
        before = digest([data, panels])
    except (ValueError, TypeError) as error:
        raise StudioError('Torso cages require finite JSON source and guide inputs') from error
    frames = {}; originals = {}; lookup = {}
    for pid, frame in sorted(panels.items()):
        if (set(frame) != {'source_ref', 'arc_sections', 'u_direction'}
                or not isinstance(frame['source_ref'], str) or not frame['source_ref']):
            raise StudioError('Torso cage needs one complete existing arc guide without a hybrid frame: '+pid)
        piece = data['pieces'][pid]
        if (not isinstance(piece.get('vertices'), list) or not isinstance(piece.get('faces'), list)
                or any(not isinstance(point, (list, tuple)) or len(point) != 2 for point in piece['vertices'])
                or any(not isinstance(face, (list, tuple)) for face in piece['faces'])):
            raise StudioError('Torso cage requires actual finite source triangles: '+pid)
        uv, triangles = _source_limb_mesh(piece, subdivisions)
        compiled = _compile_arc_sections(frame, pid)
        targets = [_section_point(frame, compiled, point, pid)[0] for point in uv]
        if any(any(type(v) not in (int, float) or not math.isfinite(v) for v in point) for point in targets):
            raise StudioError('Torso cage source guide has nonfinite target coordinates: '+pid)
        if len(set(map(tuple, uv))) != len(uv):
            raise StudioError('Torso cage source controls have ambiguous duplicate UV coordinates: '+pid)
        frames[pid] = {'source_ref':frame['source_ref']+'; source-permanent-torso-cage:'+digest(data),
            'uv_cm':uv, 'target_cm':targets, 'triangles':triangles}
        originals[pid] = [list(point) for point in targets]
        lookup[pid] = {tuple(point):i for i, point in enumerate(uv)}
    if (sum(len(frame['triangles']) for frame in frames.values()) > 131072
            or sum(len(frame['uv_cm']) for frame in frames.values()) > 70000):
        raise StudioError('Torso cage exceeds its fixed total source refinement budget')

    relations = [s for s in data.get('seams', []) if s.get('kind') == 'permanent'
                 and s.get('piece_a') in frames and s.get('piece_b') in frames]
    ids = [s.get('id') for s in relations]
    if (not relations or len(relations) > 128 or any(not isinstance(sid, str) or not sid for sid in ids)
            or len(set(ids)) != len(ids)):
        raise StudioError('Torso cages require unique explicit permanent source sewing relations')
    parents = {}; witnesses = []; matched = set()

    def root(key):
        parents.setdefault(key, key)
        if parents[key] != key:
            parents[key] = root(parents[key])
        return parents[key]

    def unite(a, b):
        ra, rb = root(a), root(b)
        parents[max(ra, rb)] = min(ra, rb)

    def boundary(pid, name, reverse=False):
        piece = data['pieces'][pid]; indices = piece.get('edges', {}).get(name)
        if (not isinstance(indices, list) or len(indices) < 2 or len(set(indices)) != len(indices)
                or any(type(i) is not int or not 0 <= i < len(piece['vertices']) for i in indices)):
            raise StudioError('Torso cage relation must name valid original source boundary vertices: '+pid)
        indices, points, _ = edge_chain(piece, name)
        if reverse:
            indices, points = list(reversed(indices)), list(reversed(points))
        lengths = chain_lengths(points); total = lengths[-1]
        controls = []; fractions = []
        for interval, (a, b) in enumerate(zip(indices, indices[1:])):
            for step in range(subdivisions):
                weights = sorted(((a, subdivisions-step), (b, step)))
                uv = tuple(math.fsum(piece['vertices'][index][k]*weight for index, weight in weights)/subdivisions
                           for k in (0, 1))
                if uv not in lookup[pid]:
                    raise StudioError('Torso cage source boundary refinement is not represented by its actual triangles')
                controls.append((pid, lookup[pid][uv]))
                fractions.append((lengths[interval]+(lengths[interval+1]-lengths[interval])*step/subdivisions)/total)
        endpoint = tuple(piece['vertices'][indices[-1]][k]*subdivisions/subdivisions for k in (0, 1))
        controls.append((pid, lookup[pid][endpoint]))
        fractions.append(1.)
        return controls, fractions, [length/total for length in lengths], total

    for seam in sorted(relations, key=lambda s:s['id']):
        if seam.get('orientation') not in ('forward', 'reverse'):
            raise StudioError('Torso cage requires explicit source sewing orientation: '+seam['id'])
        a, fa, pa, la = boundary(seam['piece_a'], seam.get('edge_a'))
        b, fb, pb, lb = boundary(seam['piece_b'], seam.get('edge_b'), seam['orientation'] == 'reverse')
        if abs(la-lb) > 1e-7:
            raise StudioError('Torso cage cannot infer easing between unequal source sewing chains: '+seam['id'])
        if len(pa) != len(pb) or any(abs(x-y) > 1e-10 for x, y in zip(pa, pb)):
            error = StudioError('Torso cage cannot infer incompatible source sewing corner partitions: '+seam['id'])
            error.guide_diagnostic = {'reason':'SOURCE_SEAM_CORNER_PARTITIONS_INCOMPATIBLE',
                'source_seam_id':seam['id'], 'normalized_partitions':[pa, pb],
                'source_mutated':False, 'garment_impossibility':'NOT_ESTABLISHED'}
            raise error
        if any(abs(frames[x[0]]['uv_cm'][x[1]][1]-frames[y[0]]['uv_cm'][y[1]][1]) > 1e-8 for x,y in zip(a,b)):
            raise StudioError('Torso cage cannot infer oblique material V partners: '+seam['id'])
        for x, y in zip(a, b):
            unite(x, y)
        matched.update((seam['piece_a'], seam['piece_b']))
        witnesses.append({'source_seam_id':seam['id'], 'source_relation':dict(seam),
            'source_chain_lengths_cm':[la, lb], 'source_corner_partitions':pa,
            'common_fractions':fa, 'partner_fractions':fb,
            'paired_cage_controls':[[list(x),list(y)] for x,y in zip(a,b)],
            'max_initial_guide_gap_cm':max(math.dist(originals[x[0]][x[1]], originals[y[0]][y[1]]) for x,y in zip(a,b))})
    if matched != set(frames):
        raise StudioError('Torso cage has source pieces without explicit permanent torso sewing partners')
    cohorts = {}
    for key in sorted(parents):
        cohorts.setdefault(root(key), []).append(key)
    # Compute every mean from the untouched proposals before any target edit.
    targets = {key:[math.fsum(originals[pid][index][k] for pid,index in cohort)/len(cohort) for k in range(3)]
               for key, cohort in cohorts.items()}
    for key, cohort in cohorts.items():
        for pid, index in cohort:
            frames[pid]['target_cm'][index] = list(targets[key])
    displacements = {pid:max(math.dist(a,b) for a,b in zip(originals[pid],frame['target_cm']))
                     for pid, frame in frames.items()}
    for witness in witnesses:
        witness['max_common_control_gap_cm'] = max(math.dist(frames[a[0]]['target_cm'][a[1]],frames[b[0]]['target_cm'][b[1]])
                                                   for a,b in witness['paired_cage_controls'])
    if digest([data, panels]) != before:
        raise StudioError('Torso cage construction mutated its original source or guide inputs')
    report = {'method':'SOURCE_PERMANENT_BOUNDARY_COMMON_TARGET_CAGE', 'source_sha256':digest(data),
        'input_guide_sha256':digest(panels), 'cage_sha256':digest(frames), 'subdivisions':subdivisions,
        'relations':witnesses, 'max_target_correction_cm':displacements,
        'unprocessed_external_relations':sorted(s['id'] for s in data.get('seams', [])
            if s.get('kind') == 'permanent' and ((s.get('piece_a') in frames) != (s.get('piece_b') in frames))),
        'boundary_correspondence':'COMPLETE_PIECEWISE_LINEAR_CAGE_SOURCE_ARC_DOMAIN',
        'target_policy':'UNWEIGHTED_MEAN_OF_EXISTING_SKIN_AND_SHOULDER_GUIDE_PROPOSALS',
        'volume':'UNCHANGED_AUXILIARY_PROPOSAL_EXCEPT_REPORTED_SOURCE_SEAM_CONTROL_CORRECTIONS',
        'front_coverage':'NOT_REVIEWED', 'source_mutated':False, 'source_uv_scaled':False,
        'body_changed':False, 'qualification':'NONE', 'metric_assessment':'REQUIRED',
        'contact_assessment':'REQUIRED', 'simulation':'NOT_EXECUTED', 'fitting':'NOT_EXECUTED'}
    return frames, report
