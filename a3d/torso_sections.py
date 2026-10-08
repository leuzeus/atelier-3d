"""Auxiliary guides from measured surface contours; no body projection."""
import math
import time

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
    length = math.fsum(math.dist(a,b) for a,b in zip(curve,curve[1:]))
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
        body_half = math.fsum(math.dist(p,q) for p,q in zip(curve,curve[1:]))
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


def source_bound_torso_cages(data, panels, *, subdivisions=8, budgets=None, _clock=time.monotonic,
                             synchronize_boundaries=True, section_parameterization='POLYLINE_ARCLENGTH_V1'):
    """Synchronize actual permanent torso boundaries in a source-UV cage.

    The existing measured-skin/shoulder guide remains the volume hypothesis.
    The declared integer source refinement is partitioned at measured V rows.
    At shared source boundary controls, proposals receive their unweighted
    common mean. The checked union of actual boundary partitions then gives
    both partners the same piecewise-linear boundary for the complete source
    arc domain. U interpolation remains an unqualified volume hypothesis.
    This neither preserves/reviews front coverage nor grants metric/contact
    admission. Relations to pieces outside ``panels`` are left untouched.
    """
    from .guide_cage_sampling import section_cage_state
    from .source_seam_coupling import _Budget, _evaluator, _chain, _partition_union, _at_fraction
    from .sewing import chain_lengths, edge_chain

    if section_parameterization not in ('POLYLINE_ARCLENGTH_V1', 'SOURCE_MATERIAL_U_V1'):
        raise StudioError('Unsupported torso cage section parameterization')
    material_parameters = section_parameterization == 'SOURCE_MATERIAL_U_V1'
    seed_subdivisions = 1 if material_parameters else subdivisions
    if type(subdivisions) is not int or not 2 <= subdivisions <= 16:
        raise StudioError('Torso cage subdivisions must be an integer in 2..16')
    if type(synchronize_boundaries) is not bool:
        raise StudioError('Torso boundary synchronization must be explicitly boolean')
    if (not isinstance(panels, dict) or not panels or len(panels) > 16
            or not set(panels) <= set(data.get('pieces', {}))):
        raise StudioError('Torso cages require exact source pieces within the fixed panel budget')
    try:
        before = digest([data, panels])
    except (ValueError, TypeError) as error:
        raise StudioError('Torso cages require finite JSON source and guide inputs') from error
    budget = _Budget(budgets, _clock)
    if any(not isinstance(data['pieces'][pid], dict)
           or not isinstance(data['pieces'][pid].get('vertices'), list)
           or not isinstance(data['pieces'][pid].get('faces'), list) for pid in panels):
        raise StudioError('Torso cage requires actual source vertices and faces')
    if (sum(len(data['pieces'][pid].get('vertices', [])) for pid in panels) > budget.limits['max_source_points']
            or sum(len(data['pieces'][pid].get('faces', [])) for pid in panels) > budget.limits['max_source_triangles']):
        raise StudioError('Torso cage original source budget exhausted')
    frames = {}; states = {}; material_sampling = {}
    for pid, frame in sorted(panels.items()):
        frame_keys = ({'source_ref', 'sampling_contract', 'material_sections'} if material_parameters else
                      {'source_ref', 'arc_sections', 'u_direction'})
        if (not isinstance(frame, dict) or set(frame) != frame_keys
                or not isinstance(frame['source_ref'], str) or not frame['source_ref']):
            raise StudioError(('Torso cage needs one complete declared material guide without a hybrid frame: ' if material_parameters
                               else 'Torso cage needs one complete existing arc guide without a hybrid frame: ')+pid)
        piece = data['pieces'][pid]
        if (not isinstance(piece.get('vertices'), list) or not isinstance(piece.get('faces'), list)
                or any(not isinstance(point, (list, tuple)) or len(point) != 2 for point in piece['vertices'])
                or any(not isinstance(face, (list, tuple)) for face in piece['faces'])):
            raise StudioError('Torso cage requires actual finite source triangles: '+pid)
        if material_parameters:
            from .material_section_sampling import material_section_cage_state
            state = states[pid] = material_section_cage_state(piece, frame, pid, budget)
            material_sampling[pid] = state['sampling_report']
        else:
            evaluate = _evaluator(frame, pid, budget)
            state = states[pid] = section_cage_state(piece, frame, pid, subdivisions, budget, evaluate)
        frames[pid] = {'source_ref':frame['source_ref']+'; source-permanent-torso-cage:'+digest(data),
            'uv_cm':state['uv'], 'target_cm':state['original'], 'triangles':state['triangles']}

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
        chain = _chain(piece, name, reverse, states[pid], pid, seed_subdivisions)
        return chain, [length/total for length in lengths], total

    for seam in sorted(relations, key=lambda s:s['id']):
        if seam.get('orientation') not in ('forward', 'reverse'):
            raise StudioError('Torso cage requires explicit source sewing orientation: '+seam['id'])
        ca, pa, la = boundary(seam['piece_a'], seam.get('edge_a'))
        cb, pb, lb = boundary(seam['piece_b'], seam.get('edge_b'), seam['orientation'] == 'reverse')
        if abs(la-lb) > 1e-7:
            raise StudioError('Torso cage cannot infer easing between unequal source sewing chains: '+seam['id'])
        if len(pa) != len(pb) or any(abs(x-y) > 1e-10 for x, y in zip(pa, pb)):
            error = StudioError('Torso cage cannot infer incompatible source sewing corner partitions: '+seam['id'])
            error.guide_diagnostic = {'reason':'SOURCE_SEAM_CORNER_PARTITIONS_INCOMPATIBLE',
                'source_seam_id':seam['id'], 'normalized_partitions':[pa, pb],
                'source_mutated':False, 'garment_impossibility':'NOT_ESTABLISHED'}
            raise error
        common = _partition_union(ca, cb)
        a = []; b = []
        for row in common:
            budget.check(); pair = []
            for chain in (ca, cb):
                pid = chain['piece']
                index, _ = _at_fraction(data['pieces'][pid], states[pid], chain, row['fraction'], budget, seed_subdivisions)
                pair.append((pid, index))
            if abs(frames[pair[0][0]]['uv_cm'][pair[0][1]][1]-frames[pair[1][0]]['uv_cm'][pair[1][1]][1]) > 1e-8:
                raise StudioError('Torso cage cannot infer oblique material V partners: '+seam['id'])
            a.append(pair[0]); b.append(pair[1])
        for x, y in zip(a, b):
            unite(x, y)
        matched.update((seam['piece_a'], seam['piece_b']))
        witnesses.append({'source_seam_id':seam['id'], 'source_relation':dict(seam),
            'source_chain_lengths_cm':[la, lb], 'source_corner_partitions':pa,
            'common_fractions':[row['fraction'] for row in common], 'partner_fractions':[row['fraction'] for row in common],
            'paired_cage_controls':[[list(x),list(y)] for x,y in zip(a,b)],
            'max_initial_guide_gap_cm':max(math.dist(states[x[0]]['original'][x[1]], states[y[0]]['original'][y[1]]) for x,y in zip(a,b))})
    if matched != set(frames):
        raise StudioError('Torso cage has source pieces without explicit permanent torso sewing partners')
    originals = {pid:[list(p) for p in state['original']] for pid, state in states.items()}
    cohorts = {}
    for key in sorted(parents):
        budget.check()
        cohorts.setdefault(root(key), []).append(key)
    # Compute every mean from the untouched proposals before any target edit.
    targets = {}
    for key, cohort in cohorts.items():
        budget.check()
        targets[key] = [math.fsum(originals[pid][index][k] for pid,index in cohort)/len(cohort) for k in range(3)]
    if synchronize_boundaries:
        for key, cohort in cohorts.items():
            budget.check()
            for pid, index in cohort:
                frames[pid]['target_cm'][index] = list(targets[key])
    displacements = {pid:max(math.dist(a,b) for a,b in zip(originals[pid],frame['target_cm']))
                     for pid, frame in frames.items()}
    for witness in witnesses:
        budget.check()
        witness['max_common_control_gap_cm'] = max(math.dist(frames[a[0]]['target_cm'][a[1]],frames[b[0]]['target_cm'][b[1]])
                                                   for a,b in witness['paired_cage_controls'])
    if digest([data, panels]) != before:
        raise StudioError('Torso cage construction mutated its original source or guide inputs')
    budget.check()
    report = {'method':'SOURCE_PERMANENT_BOUNDARY_COMMON_TARGET_CAGE', 'source_sha256':digest(data),
        'input_guide_sha256':digest(panels), 'cage_sha256':digest(frames), 'subdivisions':subdivisions,
        'relations':witnesses, 'max_target_correction_cm':displacements,
        'sampling':'DECLARED_SOURCE_REFINEMENT_PARTITIONED_AT_SECTION_ROWS',
        'interpolation':'MEASURED_HYPOTHESIS_REQUIRING_FINAL_MATERIAL_AND_CONTACT_GATES',
        'budgets':dict(budget.limits), 'controls':budget.controls, 'triangles':budget.triangles,
        'unprocessed_external_relations':sorted(s['id'] for s in data.get('seams', [])
            if s.get('kind') == 'permanent' and ((s.get('piece_a') in frames) != (s.get('piece_b') in frames))),
        'boundary_correspondence':'COMPLETE_PIECEWISE_LINEAR_CAGE_SOURCE_ARC_DOMAIN',
        'target_policy':('UNWEIGHTED_MEAN_OF_EXISTING_SKIN_AND_SHOULDER_GUIDE_PROPOSALS' if synchronize_boundaries
                         else 'UNCHANGED_GUIDE_TARGETS_AWAIT_COUPLED_REST_METRIC_SOLVE'),
        'volume':'UNCHANGED_AUXILIARY_PROPOSAL_EXCEPT_REPORTED_SOURCE_SEAM_CONTROL_CORRECTIONS',
        'front_coverage':'NOT_REVIEWED', 'source_mutated':False, 'source_uv_scaled':False,
        'body_changed':False, 'qualification':'NONE', 'metric_assessment':'REQUIRED',
        'contact_assessment':'REQUIRED', 'simulation':'NOT_EXECUTED', 'fitting':'NOT_EXECUTED'}
    if material_parameters:
        from bisect import bisect_right
        from .cloth_metrics import principal_stretches
        from .pattern_assembly import _compile_arc_sections, _section_point
        final_metrics = {}; comparisons = {}
        for pid, frame in sorted(frames.items()):
            low = math.inf; high = -math.inf; unmeasurable = []
            for index, face in enumerate(frame['triangles']):
                budget.check()
                metric = principal_stretches([frame['uv_cm'][i] for i in face],
                                            [frame['target_cm'][i] for i in face])
                if metric is None:
                    unmeasurable.append(index)
                else:
                    low = min(low, metric[0]); high = max(high, metric[1])
            final_metrics[pid] = {'stage':'AFTER_SOURCE_BOUNDARY_PROCESSING',
                'principal_range':[low, high] if math.isfinite(low) else None,
                'unmeasurable_triangle_count':len(unmeasurable), 'unmeasurable_triangle_examples':unmeasurable[:16],
                'qualification':'NONE', 'acceptance_criteria':'UNCHANGED_DOWNSTREAM_MATERIAL_GATES'}
            rows = panels[pid]['material_sections']
            directions = {1 if row['material_u_cm'][-1] > row['material_u_cm'][0] else -1 for row in rows}
            if len(directions) != 1 or any(row['material_u_cm'][0] != 0. for row in rows):
                comparisons[pid] = {'status':'NOT_COMPARABLE',
                    'reason':'HISTORICAL_ZERO_ORIGIN_AND_COMMON_DIRECTION_NOT_ESTABLISHED', 'qualification':'NONE'}
                continue
            old_frame = {'source_ref':panels[pid]['source_ref'], 'u_direction':next(iter(directions)),
                'arc_sections':[{'v_cm':row['v_cm'], 'arc_offset_cm':0., 'curve_cm':row['curve_cm']} for row in rows]}
            budget.check()
            try:
                # This compiler has no budget callback: only historical arc
                # representability errors are converted to a comparison gap.
                old_compiled = _compile_arc_sections(old_frame, pid)
            except StudioError:
                comparisons[pid] = {'status':'NOT_COMPARABLE',
                    'reason':'HISTORICAL_ARC_GEOMETRY_NOT_REPRESENTABLE', 'qualification':'NONE'}
                continue
            budget.check()
            positions = [row['v_cm'] for row in old_compiled]; outside = None
            for index, uv in enumerate(frame['uv_cm']):
                budget.check()
                lower = min(len(positions)-2, bisect_right(positions,uv[1])-1)
                s = old_frame['u_direction']*uv[0]
                if any(not 0 <= s <= old_compiled[i]['total_length_cm'] for i in (lower,lower+1)):
                    outside = {'control':index, 'source_uv_cm':uv, 'historical_arc_coordinate_cm':s}
                    break
            if outside is not None:
                comparisons[pid] = {'status':'NOT_COMPARABLE', 'reason':'HISTORICAL_ARC_DOMAIN_DOES_NOT_COVER_SOURCE_CONTROLS',
                    'first_uncovered_control':outside, 'qualification':'NONE'}
                continue
            maximum = 0.; worst = None
            for index, (uv, target) in enumerate(zip(frame['uv_cm'], originals[pid])):
                budget.check()
                previous = _section_point(old_frame,old_compiled,uv,pid)[0]; distance = math.dist(previous, target)
                if distance > maximum:
                    maximum = distance
                    worst = {'control':index, 'source_uv_cm':uv,
                             'historical_target_cm':previous, 'material_parameter_target_cm':target}
            comparisons[pid] = {'status':'MEASURED_AT_SOURCE_CONTROLS',
                'stage':'BEFORE_BOUNDARY_TARGET_SYNCHRONIZATION', 'samples':len(originals[pid]),
                'maximum_shift_cm':maximum, 'worst_control':worst,
                'same_mapping_claimed':False, 'qualification':'NONE'}
        budget.check()
        report.update(section_parameterization=section_parameterization, source_seed_subdivisions=seed_subdivisions,
            sampling='ORIGINAL_SOURCE_FACES_PARTITIONED_AT_EXPLICIT_MATERIAL_U_AND_V',
            material_sampling=material_sampling, final_cage_metrics=final_metrics,
            historical_arclength_comparison=comparisons)
    return frames, report
