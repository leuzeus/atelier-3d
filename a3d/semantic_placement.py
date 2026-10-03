"""Measured torso guides from source semantic roles and the common body profile.

Reuse the existing source-UV volume generator. A supported torso group has an
opening strip, front, side and back per side. Unsupported or missing roles are
reported before attempting placement; no guessed panel is substituted.
"""
import math

from .core import StudioError, digest
from .preform_volume import half_ellipse, volume_frames
from .anatomy_profile import unit
from .contact_geometry import dot, cross


def torso_volume_frames(data, semantics, profile, upper_blend=0.):
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
    chest = landmarks['chest']['section']; low, high = chest['bounds_xy_cm']
    width, depth = high[0]-low[0], high[1]-low[1]
    if min(width, depth) <= 0:
        raise StudioError('Measured torso section has no usable transverse frame')
    center = [(low[0]+high[0])/2, -(low[1]+high[1])/2]

    def world(point):
        return [basis['origin_cm'][i]+point[0]*basis['right'][i]
                -point[1]*basis['forward'][i]+point[2]*basis['up'][i] for i in range(3)]

    for (layer, side), mapping in sorted(groups.items()):
        if set(mapping) != {'center', 'front', 'side', 'back'}:
            raise StudioError('Torso semantic group is missing approved source roles: '+layer+' / '+side)
        subset = {'pieces': {pid: data['pieces'][pid] for pid in mapping.values()}}
        maximum_v = max(p[1] for piece in subset['pieces'].values() for p in piece['vertices'])
        neck = landmarks['neck']['point_cm']
        group = dict(mapping, pieces=sorted(mapping.values()), side_sign=1 if side == 'right' else -1,
                     uv_origin_cm=[0., 0.])
        for role in ('front', 'back'):
            piece = subset['pieces'][mapping[role]]
            if upper_blend:
                if 'neck' not in piece['edges']:
                    raise StudioError('Upper torso guide needs a declared source neckline edge: '+mapping[role])
                chain = [piece['vertices'][i] for i in piece['edges']['neck']]
                group[role+'_neck_cm'] = sum(math.dist(a, b) for a, b in zip(chain, chain[1:]))
            else:
                group[role+'_neck_cm'] = 0.
        body_frame = {'source_ref': 'measured-body-profile:'+profile['cache_key'],
                      'aspect_ratio': width/depth, 'center_xy_cm': center,
                      'hem_z_cm': neck[2]-maximum_v, 'neck_center_cm': [neck[0], -neck[1], neck[2]],
                      'shoulders_cm': {str(sign): [landmarks['shoulder.'+name]['point_cm'][0],
                            -landmarks['shoulder.'+name]['point_cm'][1], landmarks['shoulder.'+name]['point_cm'][2]]
                            for sign, name in ((1, 'right'), (-1, 'left'))}}
        panels, report = volume_frames(subset, [group], body_frame, upper_blend=upper_blend)
        for pid, frame in panels.items():
            for section in frame['arc_sections']:
                section['curve_cm'] = [world(point) for point in section['curve_cm']]
            frame['source_ref'] += '; source-semantic-layer:'+layer
            frames[pid] = frame
        diagnostics.append({'layer': layer, 'side': side, 'guide': report,
                            'measured_body_girth_cm': landmarks['chest']['girth_cm']})
    pending = sorted(set(data['pieces'])-assigned)
    return {'version': 1, 'status': 'PARTIAL_GUIDES' if pending else 'TORSO_GUIDES_PREPARED',
            'panels': frames, 'pending_pieces': pending, 'groups': diagnostics,
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
        sections = []
        for v in (lo[1], hi[1]):
            center = [anchor[i]+downward[i]*(hi[1]-v) for i in range(3)]
            curve = [world([center[i]+p[0]*tangent[i]+p[1]*transverse[i] for i in range(3)]) for p in arc]
            sections.append({'v_cm': v, 'arc_offset_cm': -lo[0], 'curve_cm': curve})
        frames[pid] = {'source_ref': 'measured-body-profile:'+profile['cache_key']+'; source-role:'+pid,
                       'arc_sections': sections, 'u_direction': 1}
        evidence.append({'piece': pid, 'role': row['role'], 'side': side,
                         'source_circumference_cm': width, 'source_longitudinal_length_cm': height,
                         'shoulder_wrist_axis_length_cm': math.dist(shoulder, wrist),
                         'body_rescaling': False, 'native_contact_check': 'REQUIRED'})
    return {'status': 'PARTIAL_GUIDES' if pending else 'LIMB_GUIDES_PREPARED',
            'panels': frames, 'pending_pieces': pending, 'evidence': evidence,
            'source_sha256': digest(data), 'semantics_sha256': digest(semantics),
            'profile_cache_key': profile['cache_key'], 'source_mutated': False,
            'source_uv_scaled': False, 'qualification': 'NONE', 'simulation': 'NOT_EXECUTED'}
