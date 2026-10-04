"""Measured torso guides from source semantic roles and the common body profile.

Reuse the existing source-UV volume generator. A supported torso group has an
opening strip, front, side and back per side. Unsupported or missing roles are
reported before attempting placement; no guessed panel is substituted.
"""
import math
import copy

from .core import StudioError, digest
from .preform_volume import half_ellipse, volume_frames, paired_volume_frames
from .anatomy_profile import unit
from .contact_geometry import dot, cross


def torso_volume_frames(data, semantics, profile, upper_blend=0., surface_sections=False, skin_sections=None,
                        source_cage_budgets=None):
    if (profile.get('status') != 'PROFILE_MEASURED' or profile.get('segmentation') != 'EXPLICIT_SOURCE'
            or not profile.get('cache_key')):
        raise StudioError('Semantic placement requires a complete source-bound segmented body profile')
    if set(semantics) != set(data['pieces']):
        raise StudioError('Semantic placement needs exact source piece coverage; correct or regenerate missing approved pieces')
    groups = {}; assigned = set()
    for pid, row in sorted(semantics.items()):
        if row.get('role') not in ('front', 'side', 'back'):
            continue
        side = row.get('side'); layer = row.get('layer')
        if side not in ('left', 'right') or not isinstance(layer, str) or not layer:
            raise StudioError('Torso role needs its explicit side and spatial layer: '+pid)
        role = 'center' if row.get('subrole') == 'opening_strip' else row['role']
        if role == 'center' and row['role'] != 'front':
            raise StudioError('Opening-strip semantic role must be a front panel: '+pid)
        group = groups.setdefault((layer, side), {})
        if role in group:
            raise StudioError('Several source pieces own the same torso role; review the declared cut: '+pid)
        group[role] = pid; assigned.add(pid)
    if not groups:
        raise StudioError('No supported torso semantic group is present')
    frames = {}; diagnostics = []
    landmarks = profile['landmarks']; basis = profile['frame']
    if upper_blend:
        from .shoulder_surface import surface_anchors
        skin_shoulders = surface_anchors(profile)
    chest = landmarks['chest']['section']; low, high = chest['bounds_xy_cm']
    width, depth = high[0]-low[0], high[1]-low[1]
    if min(width, depth) <= 0:
        raise StudioError('Measured torso section has no usable transverse frame')
    center = [(low[0]+high[0])/2, -(low[1]+high[1])/2]

    def world(point):
        return [basis['origin_cm'][i]+point[0]*basis['right'][i]
                -point[1]*basis['forward'][i]+point[2]*basis['up'][i] for i in range(3)]

    for (layer, side), mapping in sorted(groups.items()):
        paired=set(mapping)=={'front','back'}
        if surface_sections and not paired:
            raise StudioError('Measured surface contours currently require a real paired torso cut')
        if not paired and set(mapping) != {'center', 'front', 'side', 'back'}:
            raise StudioError('Torso semantic group is missing approved source roles: '+layer+' / '+side)
        subset = {'pieces': {pid: data['pieces'][pid] for pid in mapping.values()}}
        maximum_v = max(p[1] for piece in subset['pieces'].values() for p in piece['vertices'])
        neck = landmarks['neck']['point_cm']
        group = dict(mapping, pieces=sorted(mapping.values()), side_sign=1 if side == 'right' else -1,
                     uv_origin_cm=[0., 0.])
        opening_edge=semantics[mapping['front']].get('guide_edges',{}).get('opening')
        if opening_edge:
            front=mapping['front']; source=data['pieces'][front]
            centers=[pid for pid,row in semantics.items() if row.get('role')=='inner_front' and row.get('side')=='center']
            attachments=[s for s in data.get('seams',[]) if s.get('kind')=='permanent' and
                         {s['piece_a'],s['piece_b']}=={front,centers[0] if len(centers)==1 else None}]
            owned=[s for s in data.get('seams',[]) if any(s['piece_'+side]==front and s['edge_'+side]==opening_edge for side in ('a','b'))]
            if (len(centers)!=1 or not attachments or opening_edge not in source['edges'] or owned):
                raise StudioError('Open torso guide needs one sourced central inner-front, actual permanent upper attachments and an unsewn declared free edge')
            values=[source['vertices'][i][1] for i in source['edges'][opening_edge]]
            group['source_open_front']={'piece':front,'free_edge':opening_edge,'inner_front_piece':centers[0],
                'permanent_attachment_ids':sorted(s['id'] for s in attachments),
                'source_sha256':digest(data),'free_edge_v_domain_cm':[min(values),max(values)]}
        for role in ('front', 'back'):
            piece = subset['pieces'][mapping[role]]
            if upper_blend:
                neck_edge=semantics[mapping[role]].get('guide_edges',{}).get('neck','neckline' if paired else 'neck')
                if neck_edge not in piece['edges']:
                    raise StudioError('Upper torso guide needs a declared source neckline edge: '+mapping[role])
                chain = [piece['vertices'][i] for i in piece['edges'][neck_edge]]
                group[role+'_neck_cm'] = sum(math.dist(a, b) for a, b in zip(chain, chain[1:]))
            else:
                group[role+'_neck_cm'] = 0.
        body_frame = {'source_ref': 'measured-body-profile:'+profile['cache_key'],
                      'aspect_ratio': width/depth, 'center_xy_cm': center,
                      'chest_bounds_xy_cm':[[low[0],-high[1]],[high[0],-low[1]]],
                      'chest_height_cm':landmarks['chest']['section'].get('height_cm',landmarks['chest'].get('point_cm',[0.,0.,neck[2]])[2]),
                      'hem_z_cm': neck[2]-maximum_v, 'neck_center_cm': [neck[0], -neck[1], neck[2]],
                      'shoulders_cm': {str(sign): [landmarks['shoulder.'+name]['point_cm'][0],
                            -landmarks['shoulder.'+name]['point_cm'][1], landmarks['shoulder.'+name]['point_cm'][2]]
                            for sign, name in ((1, 'right'), (-1, 'left'))}}
        if upper_blend:
            body_frame['shoulders_cm'] = {str(sign):[skin_shoulders[name][0],-skin_shoulders[name][1],skin_shoulders[name][2]]
                                         for sign,name in ((1,'right'),(-1,'left'))}
            body_frame['shoulder_anchor_kind'] = 'MEASURED_BODY_SURFACE'
        if paired:
            group['source_edges']={}
            for role in ('front','back'):
                piece=subset['pieces'][mapping[role]]
                declared=dict(semantics[mapping[role]].get('guide_edges',{}))
                declared.setdefault('side','side');declared.setdefault('hem','hem')
                if upper_blend:declared.setdefault('shoulder','shoulder')
                if role=='back' and 'center' not in declared:
                    candidates=[name for name in ('center','center-back') if name in piece['edges']]
                    if len(candidates)!=1:
                        raise StudioError('Paired torso needs one explicit named source back center')
                    declared['center']=candidates[0]
                group['source_edges'][role]=declared
            if upper_blend:
                transition=min(max(data['pieces'][group[role]]['vertices'][i][1]
                    for i in data['pieces'][group[role]]['edges'][group['source_edges'][role]['side']]) for role in ('front','back'))
                group['measured_shoulder_transition']={'source_start_v_cm':transition,
                    'source_edges':copy.deepcopy(group['source_edges']),
                    'source_skin_anchors_cm':copy.deepcopy(skin_shoulders),'source_profile_cache_key':profile['cache_key'],
                    'upper_blend':upper_blend,'method':'SOURCE_MATERIAL_PLANES_FROM_MEASURED_SKIN_SHOULDERS'}
            panels,report=paired_volume_frames(subset,group,body_frame)
            if surface_sections:
                from .torso_sections import apply_measured_sections
                panels,report=apply_measured_sections(panels,report,group,profile,skin_sections=skin_sections)
            if upper_blend:
                from .shoulder_guides import shape_paired_shoulders
                panels,report=shape_paired_shoulders(subset,group,body_frame,panels,report,upper_blend)
        else:
            panels, report = volume_frames(subset, [group], body_frame, upper_blend=upper_blend)
        for pid, frame in panels.items():
            for section in frame['arc_sections']:
                section['curve_cm'] = [world(point) for point in section['curve_cm']]
            frame['source_ref'] += '; source-semantic-layer:'+layer
            frames[pid] = frame
        diagnostics.append({'layer': layer, 'side': side, 'guide': report,
                            'measured_body_girth_cm': landmarks['chest']['girth_cm']})
    pending = sorted(set(data['pieces'])-assigned)
    boundary_cage = None
    if surface_sections:
        from .torso_sections import source_bound_torso_cages
        frames, boundary_cage = source_bound_torso_cages(data, frames, budgets=source_cage_budgets)
    return {'version': 1, 'status': 'PARTIAL_GUIDES' if pending else 'TORSO_GUIDES_PREPARED',
            'panels': frames, 'pending_pieces': pending, 'groups': diagnostics,
            **({'source_boundary_cage':boundary_cage} if boundary_cage else {}),
            'source_sha256': digest(data), 'semantics_sha256': digest(semantics),
            'profile_cache_key': profile['cache_key'], 'source_uv_scaled': False,
            'source_mutated': False, 'qualification': 'NONE', 'simulation': 'NOT_EXECUTED',
            'fitting': 'NOT_EXECUTED', 'collision_assessment': 'REQUIRED'}


def limb_volume_frames(data, semantics, profile):
    """Developable sleeve/cuff guides; source width sets circumference.

    No source coordinate is scaled to the body. A straight shoulder-to-wrist
    axis is an initial guide, not an elbow wrap, a donning path or collision
    admission. Native contact checks must evaluate it before simulation.
    """
    if profile.get('status') != 'PROFILE_MEASURED' or set(semantics) != set(data['pieces']):
        raise StudioError('Limb guides need a complete body profile and exact source semantic coverage')
    basis = profile['frame']; frames = {}; pending = []; evidence = []

    def world(point):
        return [basis['origin_cm'][i]+sum(point[j]*basis[key][i]
                for j, key in enumerate(('right', 'forward', 'up'))) for i in range(3)]

    for pid, row in sorted(semantics.items()):
        if row.get('role') not in ('sleeve', 'cuff'):
            pending.append(pid); continue
        side = row.get('side')
        if side not in ('left', 'right'):
            raise StudioError('A limb source role needs an explicit anatomical side: '+pid)
        if row.get('longitudinal_uv_axis') != 'v':
            raise StudioError('Limb source must declare its longitudinal UV axis; no inferred grain direction: '+pid)
        shoulder = profile['landmarks']['shoulder.'+side]['point_cm']
        wrist = profile['landmarks']['wrist.'+side]['point_cm']
        downward = unit([b-a for a, b in zip(shoulder, wrist)])
        forward = [0., 1., 0.]
        projection = dot(forward, downward)
        transverse = unit([forward[i]-projection*downward[i] for i in range(3)])
        tangent = unit(cross(downward, transverse))
        vertices = data['pieces'][pid]['vertices']
        lo = [min(p[i] for p in vertices) for i in (0, 1)]
        hi = [max(p[i] for p in vertices) for i in (0, 1)]
        width, height = hi[0]-lo[0], hi[1]-lo[1]
        if min(width, height) <= 0:
            raise StudioError('Limb source contour is collapsed: '+pid)
        arc = half_ellipse(width/2, 1., [0., 0.], 0., 1)
        arc += list(reversed(half_ellipse(width/2, 1., [0., 0.], 0., -1)))[1:]
        anchor = shoulder if row['role'] == 'sleeve' else wrist
        cuff_policy = None
        if row['role']=='cuff':
            declared=row.get('guide_edges',{});stops={}
            for key in ('distal','proximal'):
                edge=declared.get(key);indices=data['pieces'][pid].get('edges',{}).get(edge)
                if not indices or len(indices)<2 or any(type(i)is not int or not 0<=i<len(vertices) for i in indices):
                    raise StudioError('Cuff guide requires explicit existing distal/proximal named source edges: '+pid)
                values=[vertices[i][1] for i in indices]
                if max(values)-min(values)>1e-7:
                    raise StudioError('Cuff anchor rings require constant source V; unsupported edge: '+str(edge))
                stops[key]=values[0]
            if abs(stops['proximal']-stops['distal'])<1e-8:
                raise StudioError('Cuff distal/proximal source anchors must have a nonzero longitudinal span')
            cuff_sign=1 if stops['proximal']>stops['distal'] else -1
            cuff_policy={'distal_edge':declared['distal'],'proximal_edge':declared['proximal'],
                'distal_source_v_cm':stops['distal'],'proximal_source_v_cm':stops['proximal'],
                'body_distal_anchor':'wrist.'+side,'proximal_direction':'TOWARD_SOURCE_SHOULDER',
                'source_orientation':'EXPLICIT_NAMED_EDGES','source_v_sign':cuff_sign}
        sections = []
        for v in (lo[1], hi[1]):
            offset=(hi[1]-v) if cuff_policy is None else -(v-stops['distal'])*cuff_sign
            center = [anchor[i]+downward[i]*offset for i in range(3)]
            curve = [world([center[i]+p[0]*tangent[i]+p[1]*transverse[i] for i in range(3)]) for p in arc]
            sections.append({'v_cm': v, 'arc_offset_cm': -lo[0], 'curve_cm': curve})
        frames[pid] = {'source_ref': 'measured-body-profile:'+profile['cache_key']+'; source-role:'+pid,
                       'arc_sections': sections, 'u_direction': 1}
        evidence.append({'piece': pid, 'role': row['role'], 'side': side,
                         'source_circumference_cm': width, 'source_longitudinal_length_cm': height,
                         'shoulder_wrist_axis_length_cm': math.dist(shoulder, wrist),
                         **({'source_longitudinal_anchor_policy':cuff_policy} if cuff_policy else {}),
                         'body_rescaling': False, 'native_contact_check': 'REQUIRED'})
    return {'status': 'PARTIAL_GUIDES' if pending else 'LIMB_GUIDES_PREPARED',
            'panels': frames, 'pending_pieces': pending, 'evidence': evidence,
            'source_sha256': digest(data), 'semantics_sha256': digest(semantics),
            'profile_cache_key': profile['cache_key'], 'source_mutated': False,
            'source_uv_scaled': False, 'qualification': 'NONE', 'simulation': 'NOT_EXECUTED'}


def belt_volume_frames(data,semantics,profile,opening_clearance_cm=.5):
    """Open waist guides with the source material length, preserving closures.

    The extra arc is empty space between the ends, not extra source material.
    It avoids assigning coincident ends before a declared closure is evaluated.
    No buckle, closed seam, body fit or collider is invented by this guide.
    """
    if (profile.get('status')!='PROFILE_MEASURED' or profile.get('segmentation')!='EXPLICIT_SOURCE'
            or not profile.get('cache_key') or set(semantics)!=set(data['pieces'])):
        raise StudioError('Belt guides require a segmented body profile and exact source semantic coverage')
    if (type(opening_clearance_cm) not in (int,float) or not math.isfinite(opening_clearance_cm)
            or not 0<opening_clearance_cm<=5.):
        raise StudioError('Belt opening clearance must be finite, positive and at most 5 cm')
    waist=profile['landmarks']['waist'];low,high=waist['section']['bounds_xy_cm']
    width,depth=high[0]-low[0],high[1]-low[1]
    if min(width,depth)<=0:raise StudioError('Measured waist has no usable transverse frame')
    basis=profile['frame'];panels={};pending=[];evidence=[]
    def world(point):
        return [basis['origin_cm'][i]+point[0]*basis['right'][i]-point[1]*basis['forward'][i]
                +point[2]*basis['up'][i] for i in range(3)]
    for pid,row in sorted(semantics.items()):
        if row.get('role')!='belt':pending.append(pid);continue
        if row.get('longitudinal_uv_axis')!='u':
            raise StudioError('Belt material direction must be explicitly declared along source u: '+pid)
        vertices=data['pieces'][pid]['vertices']
        if not vertices or any(len(p)!=2 or any(not math.isfinite(x) for x in p) for p in vertices):
            raise StudioError('Belt source requires finite metric UV coordinates')
        lo=[min(p[i] for p in vertices) for i in (0,1)]
        hi=[max(p[i] for p in vertices) for i in (0,1)]
        length,height=hi[0]-lo[0],hi[1]-lo[1]
        if min(length,height)<=0 or opening_clearance_cm>=length:
            raise StudioError('Belt source or opening is outside the supported longitudinal domain')
        center=[waist['point_cm'][0],-waist['point_cm'][1]];sections=[]
        for v in (lo[1],hi[1]):
            z=waist['point_cm'][2]+v-(lo[1]+hi[1])/2
            half=(length+opening_clearance_cm)/2
            curve=half_ellipse(half,width/depth,center,z,1)
            curve+=list(reversed(half_ellipse(half,width/depth,center,z,-1)))[1:]
            sections.append({'v_cm':v,'arc_offset_cm':-lo[0],'curve_cm':[world(p) for p in curve]})
        panels[pid]={'source_ref':'measured-body-profile:'+profile['cache_key']+'; source-role:'+pid,
                     'arc_sections':sections,'u_direction':1}
        evidence.append({'piece':pid,'source_material_length_cm':length,'source_height_cm':height,
                         'measured_waist_girth_cm':waist['girth_cm'],
                         'empty_guide_arc_cm':opening_clearance_cm,'closure':'NOT_EXECUTED',
                         'rigid_buckle':'NOT_CREATED','contact_assessment':'REQUIRED'})
    return {'status':'PARTIAL_GUIDES' if pending else 'BELT_GUIDES_PREPARED','panels':panels,
            'pending_pieces':pending,'evidence':evidence,'source_sha256':digest(data),
            'semantics_sha256':digest(semantics),'profile_cache_key':profile['cache_key'],
            'source_uv_scaled':False,'source_mutated':False,'simulation':'NOT_EXECUTED',
            'fitting':'NOT_EXECUTED','qualification':'NONE'}
