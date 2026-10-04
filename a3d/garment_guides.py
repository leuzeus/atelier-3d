"""Complete source-bound guide dispatch for a measured body.

Torso, limb and belt guides retain their existing algorithms. Collar, central
inner front, hood and yoke use explicit source anchor edges and measured body
surfaces. Planar and developable guides are starting hypotheses; curved hood
and shoulder drape require the subsequent metric/contact solver and Cloth.
No missing piece, side, grain axis or source contour is manufactured here.
"""
import copy
import math

from .anatomy_profile import unit
from .contact_geometry import cross, dot
from .core import StudioError, digest
from .preform_volume import half_ellipse, sample_curve, extend_tangent
from .semantic_placement import torso_volume_frames, limb_volume_frames, belt_volume_frames


SPECIAL_ROLES = {'collar', 'inner_front', 'hood', 'yoke'}


def _profile(profile):
    if (profile.get('status') != 'PROFILE_MEASURED' or profile.get('segmentation') != 'EXPLICIT_SOURCE'
            or not profile.get('cache_key')):
        raise StudioError('Garment guides require a measured source-bound segmented body profile')
    basis = profile['frame']
    for key in ('right', 'forward', 'up'):
        value = basis[key]
        if len(value) != 3 or any(not math.isfinite(v) for v in value) or abs(dot(value, value)-1) > 1e-7:
            raise StudioError('Measured garment guide frame must be orthonormal')
    if any(abs(dot(basis[a], basis[b])) > 1e-7 for a, b in (('right', 'up'), ('right', 'forward'), ('forward', 'up'))):
        raise StudioError('Measured garment guide axes must be perpendicular')


def _surface(profile, landmark, axis, sign=1):
    if landmark == 'head':
        from .head_surface import head_surface_section
        section = head_surface_section(profile)
    else:
        section = profile['landmarks'].get(landmark, {}).get('section', {})
    points = section.get('curve_cm')
    if section.get('status') != 'MEASURED' or not points or len(points) < 3:
        raise StudioError('Guide requires an actual measured surface section: '+landmark)
    if any(len(p) != 3 or any(not math.isfinite(v) for v in p) for p in points):
        raise StudioError('Guide surface contour must contain finite body-frame points')
    # An extremal *actual sample*, not a manufactured bounding-box corner.
    return list(max(points, key=lambda p: (sign*p[axis], tuple(p))))


def _rotate_closed_curve(curve, start_distance):
    """Change the seam phase while retaining the same measured polyline arc."""
    cumulative = [0.]
    for a, b in zip(curve, curve[1:]):
        cumulative.append(cumulative[-1]+math.dist(a, b))
    total = cumulative[-1]; start_distance %= total
    start = sample_curve(curve, start_distance)
    result = [start]+[list(p) for p, s in zip(curve, cumulative) if start_distance < s < total]
    result += [list(curve[0])]+[list(p) for p, s in zip(curve, cumulative) if 0 < s < start_distance]+[start]
    return [p for i, p in enumerate(result) if not i or math.dist(p, result[i-1]) > 1e-12]


def _source_anchor(piece, semantic):
    names = semantic.get('guide_edges', {})
    if 'anchor' not in names:
        raise StudioError('Specialised guide requires an explicitly named source anchor edge')
    anchors = []
    for name in ('anchor', 'anchor_end'):
        if name not in names:
            continue
        edge = names[name]
        indices = piece['edges'].get(edge)
        if not indices or len(indices) < 2 or any(type(i) is not int or not 0 <= i < len(piece['vertices']) for i in indices):
            raise StudioError('Guide anchor edge is missing or has invalid source vertices: '+edge)
        curve = [piece['vertices'][i] for i in indices]
        lengths = [math.dist(a, b) for a, b in zip(curve, curve[1:])]
        if min(lengths) <= 1e-10:
            raise StudioError('Guide anchor edge has a collapsed source segment')
        remaining = sum(lengths)/2
        for a, b, size in zip(curve, curve[1:], lengths):
            if remaining <= size:
                anchors.append([a[i]+remaining/size*(b[i]-a[i]) for i in (0, 1)])
                break
            remaining -= size
    return [sum(p[i] for p in anchors)/len(anchors) for i in (0, 1)]


def _world(profile, point):
    basis = profile['frame']
    return [basis['origin_cm'][i]+sum(point[j]*basis[key][i]
            for j, key in enumerate(('right', 'forward', 'up'))) for i in range(3)]


def _planar(piece, anchor_uv, anchor_body, u_axis, v_axis, profile):
    lo = [min(p[i] for p in piece['vertices']) for i in (0, 1)]
    hi = [max(p[i] for p in piece['vertices']) for i in (0, 1)]
    if min(hi[i]-lo[i] for i in (0, 1)) <= 1e-10:
        raise StudioError('Source guide contour is collapsed')
    u_axis, v_axis = unit(u_axis), unit(v_axis)
    if abs(dot(u_axis, v_axis)) > 1e-8:
        raise StudioError('Planar source guide must preserve orthogonal material axes')

    def point(u, v):
        return _world(profile, [anchor_body[i]+(u-anchor_uv[0])*u_axis[i]+(v-anchor_uv[1])*v_axis[i]
                               for i in range(3)])
    return {'u_direction': 1, 'arc_sections': [{'v_cm': v, 'arc_offset_cm': -lo[0],
             'curve_cm': [point(lo[0], v), point(hi[0], v)]} for v in (lo[1], hi[1])]}


def specialised_volume_frames(data, semantics, profile):
    """Source-edge/body-surface guides for collar, inner front, hood and yoke.

    ``guide_edges.anchor`` (and optional ``anchor_end``) names actual edges;
    their arc midpoints define the material anchor. A nonnegative explicitly
    declared guide_surface_offset_cm may translate the hypothesis, never UV.
    Hood guide is sagittal, yoke guide follows measured skin shoulders, and
    the single inner-front stays one source piece. Their metrics are isometric.
    """
    _profile(profile)
    if set(semantics) != set(data['pieces']):
        raise StudioError('Garment guides require exact immutable source piece coverage')
    original = digest([data, semantics, profile]); frames = {}; evidence = []; pending = []
    for pid, semantic in sorted(semantics.items()):
        role = semantic.get('role')
        if role not in SPECIAL_ROLES:
            pending.append(pid); continue
        piece = data['pieces'][pid]
        if not piece.get('vertices') or any(len(p) != 2 or any(not math.isfinite(v) for v in p) for p in piece['vertices']):
            raise StudioError('Specialised guide requires a finite immutable 2D source contour: '+pid)
        if semantic.get('longitudinal_uv_axis') not in ('u', 'v'):
            raise StudioError('Specialised guide requires its explicit material axis: '+pid)
        anchor_uv = _source_anchor(piece, semantic)
        offset = semantic.get('guide_surface_offset_cm', 0.)
        if type(offset) not in (int, float) or not math.isfinite(offset) or not 0 <= offset <= 20:
            raise StudioError('Guide surface offset must be explicit, finite and bounded')
        if role == 'inner_front':
            if semantic.get('side') != 'center' or semantic['longitudinal_uv_axis'] != 'v':
                raise StudioError('Inner front is a single central source piece with vertical material axis')
            anchor = _surface(profile, 'neck', 1); anchor[1] += offset
            frame = _planar(piece, anchor_uv, anchor, [1., 0., 0.], [0., 0., 1.], profile)
            kind = 'SOURCE_ISOMETRIC_CENTRAL_FRONT_PLANE'
        elif role == 'hood':
            if semantic.get('side') not in ('left', 'right') or semantic['longitudinal_uv_axis'] != 'v':
                raise StudioError('Hood guide requires an explicit source side and vertical material axis')
            sign = 1 if semantic['side'] == 'right' else -1
            anchor = _surface(profile, 'head', 0, sign); anchor[0] += sign*offset
            head = profile['landmarks']['head.center']['point_cm']; neck = profile['landmarks']['neck']['point_cm']
            up = unit([b-a for a, b in zip(neck, head)])
            sagittal = [0., -1., 0.]
            sagittal = unit([sagittal[i]-dot(sagittal, up)*up[i] for i in range(3)])
            frame = _planar(piece, anchor_uv, anchor, sagittal, up, profile)
            kind = 'SOURCE_ISOMETRIC_SAGITTAL_HOOD_PLANE'
        elif role == 'yoke':
            from .shoulder_surface import surface_anchors
            shoulders = surface_anchors(profile)
            u = unit([b-a for a, b in zip(shoulders['left'], shoulders['right'])])
            v = unit(cross([0., 0., 1.], u))
            normal = unit(cross(u, v))
            anchor = _surface(profile, 'neck', 1)
            anchor = [anchor[i]+offset*normal[i] for i in range(3)]
            frame = _planar(piece, anchor_uv, anchor, u, v, profile)
            kind = 'SOURCE_ISOMETRIC_MEASURED_SHOULDER_PLANE'
        else:
            if semantic['longitudinal_uv_axis'] != 'u':
                raise StudioError('Collar band requires a circumferential source u axis')
            section = profile['landmarks'].get('neck', {}).get('section', {})
            _surface(profile, 'neck', 1)
            lo, hi = section['bounds_xy_cm']
            if min(hi[i]-lo[i] for i in (0, 1)) <= 0:
                raise StudioError('Measured neck has no transverse section')
            width = max(p[0] for p in piece['vertices'])-min(p[0] for p in piece['vertices'])
            height = max(p[1] for p in piece['vertices'])-min(p[1] for p in piece['vertices'])
            if min(width, height) <= 1e-10:
                raise StudioError('Source collar band has no usable material span')
            center = [(lo[i]+hi[i])/2 for i in (0, 1)]
            center[1] += offset
            # Material width sets auxiliary perimeter; the body provides its
            # centre, aspect and elevation. UV circumference is never rescaled.
            arc = half_ellipse(width/2, (hi[0]-lo[0])/(hi[1]-lo[1]), center, section['height_cm'], 1)
            arc += list(reversed(half_ellipse(width/2, (hi[0]-lo[0])/(hi[1]-lo[1]), center, section['height_cm'], -1)))[1:]
            minimum_u = min(p[0] for p in piece['vertices'])
            arc = _rotate_closed_curve(arc, width/2-(anchor_uv[0]-minimum_u))
            actual_width = sum(math.dist(a, b) for a, b in zip(arc, arc[1:]))
            # Account for floating-point accumulation without scaling UV or
            # altering the source circumferential span.
            arc = extend_tangent(arc, max(0., width-actual_width)+1e-8)
            rows = []
            for v in (min(p[1] for p in piece['vertices']), max(p[1] for p in piece['vertices'])):
                rows.append({'v_cm': v, 'arc_offset_cm': -minimum_u,
                             'curve_cm': [_world(profile, [p[0], p[1], p[2]+v-anchor_uv[1]]) for p in arc]})
            frame = {'u_direction': 1, 'arc_sections': rows}
            kind = 'SOURCE_DEVELOPABLE_NECK_BAND'
        frame['source_ref'] = 'measured-body-profile:'+profile['cache_key']+'; source-piece:'+pid+'; '+kind
        frames[pid] = frame
        evidence.append({'piece': pid, 'role': role, 'guide_kind': kind,
                         'source_anchor_edges': copy.deepcopy(semantic['guide_edges']),
                         'source_anchor_uv_cm': anchor_uv, 'source_contour_sha256': digest(piece),
                         'source_uv_scaled': False, 'contact_assessment': 'REQUIRED',
                         'curved_surface_drape': 'REQUIRED' if role in ('hood', 'yoke') else 'NOT_EXECUTED'})
    if digest([data, semantics, profile]) != original:
        raise StudioError('Garment guides changed an immutable input')
    return {'version': 1, 'status': 'PARTIAL_GUIDES' if pending else 'SPECIALISED_GUIDES_PREPARED',
            'panels': frames, 'pending_pieces': pending, 'guides': evidence,
            'source_sha256': digest(data), 'semantics_sha256': digest(semantics),
            'profile_cache_key': profile['cache_key'], 'profile_sha256': digest(profile),
            'source_mutated': False, 'source_uv_scaled': False, 'qualification': 'NONE',
            'simulation': 'NOT_EXECUTED', 'fitting': 'NOT_EXECUTED', 'collision_assessment': 'REQUIRED'}


def measured_native_skin_sections(profile, geometry, heights_cm):
    """Measure exact whole-skin contours separately from approved girths.

    The closed central contour can include connected arm skin. It is only an
    obstacle guide contour, never a replacement anatomical torso measurement.
    Segmented torso refusals remain in the original immutable profile.
    """
    from .anatomy_profile import surface_section
    _profile(profile)
    if (profile.get('geometry_sha256')!=digest([geometry['vertices_cm'],geometry['faces']]) or
            any(profile.get(key)!=geometry.get(key) for key in ('source_sha256','pose_sha256'))):
        raise StudioError('Additional skin sections require the exact approved evaluated geometry and pose')
    basis=profile['frame']
    coordinates=[[dot([p[i]-basis['origin_cm'][i] for i in range(3)],basis[key])
                  for key in ('right','forward','up')] for p in geometry['vertices_cm']]
    sections=[]
    for height in sorted(set(heights_cm)):
        if type(height) not in (int,float) or not math.isfinite(height): raise StudioError('Skin guide height must be finite')
        source=min(profile['sections'],key=lambda row:abs(row['height_cm']-height))
        seed=source.get('seed_xy_cm')
        if not seed or len(seed)!=2: raise StudioError('Additional native skin section requires the explicit source-profile interior seed')
        section=surface_section(coordinates,geometry['faces'],height,seed)
        if section.get('status')=='MEASURED' and section['open_loop_count']:
            section['status']='NOT_QUALIFIED';section['reason']='WHOLE_SKIN_SECTION_HAS_OPEN_COMPONENTS'
        section.update(seed_xy_cm=copy.deepcopy(seed),source_face_domain='ALL_NATIVE_SKIN',
            anatomical_girth='NOT_QUALIFIED',body_surface_extrapolated=False,
            contour_selection='UNIQUE_CLOSED_NATIVE_CONTOUR_CONTAINING_EXPLICIT_SOURCE_SEED',
            connected_arm_skin='MAY_BE_INCLUDED_NOT_A_TORSO_GIRTH',
            disconnected_skin_loops='EXCLUDED_AND_REPORTED')
        sections.append(section)
    result={'version':1,'profile_sha256':digest(profile),'geometry_sha256':profile['geometry_sha256'],
        'source_sha256':profile['source_sha256'],'pose_sha256':profile['pose_sha256'],'frame':copy.deepcopy(basis),
        'source_face_domain':'ALL_NATIVE_SKIN','sections':sections,'approved_profile_mutated':False,
        'qualification':'OBSTACLE_GUIDE_CONTOURS_ONLY','anatomical_girths_replaced':False}
    result['sections_sha256']=digest(result)
    return result


def garment_volume_frames(data, semantics, profile, upper_blend=1., surface_sections=True, skin_sections=None):
    """Dispatch complete source coverage; return pending unsupported roles.

    A missing declaration or impossible native guide produces an actionable
    diagnostic. Existing complete roles may still be examined as partial data;
    pending pieces keep the result inadmissible for whole-garment preparation.
    """
    _profile(profile)
    if skin_sections and (skin_sections.get('profile_sha256')!=digest(profile) or
            skin_sections.get('sections_sha256')!=digest({k:v for k,v in skin_sections.items() if k!='sections_sha256'}) or
            any(skin_sections.get(key)!=profile.get(key) for key in ('geometry_sha256','source_sha256','pose_sha256','frame'))):
        raise StudioError('Additional skin-section evidence is stale for the approved body/profile/frame')
    if set(semantics) != set(data['pieces']):
        raise StudioError('Garment guide dispatcher requires exact source piece coverage')
    frames = {}; reports = []; diagnostics = []
    families = [('torso', {'front', 'back', 'side'}, torso_volume_frames),
                ('limb', {'sleeve', 'cuff'}, limb_volume_frames),
                ('belt', {'belt'}, belt_volume_frames),
                ('specialised', SPECIAL_ROLES, specialised_volume_frames)]
    for name, roles, build in families:
        if not any(p.get('role') in roles for p in semantics.values()):
            continue
        try:
            report = (build(data, semantics, profile, upper_blend=upper_blend, surface_sections=surface_sections,skin_sections=skin_sections)
                      if name == 'torso' else build(data, semantics, profile))
        except StudioError as error:
            diagnostics.append({'family': name, 'code': 'GUIDE_INPUT_OR_CAPABILITY_MISSING', 'message': str(error),
                                'pieces': sorted(pid for pid, row in semantics.items() if row.get('role') in roles),
                                **({'measurement': error.guide_diagnostic} if getattr(error,'guide_diagnostic',None) else {})})
            continue
        if set(frames).intersection(report['panels']):
            raise StudioError('Several guide families own one source piece')
        frames.update(report['panels']); reports.append({'family': name, 'report': report})
    pending = sorted(set(data['pieces'])-set(frames))
    return {'version': 1, 'status': 'PARTIAL_GUIDES' if pending else 'GARMENT_GUIDES_PREPARED',
            'panels': frames, 'pending_pieces': pending, 'diagnostics': diagnostics, 'families': reports,
            'source_sha256': digest(data), 'semantics_sha256': digest(semantics),
            'profile_cache_key': profile['cache_key'], 'profile_sha256': digest(profile),
            'source_mutated': False, 'source_uv_scaled': False, 'qualification': 'NONE',
            'simulation': 'NOT_EXECUTED', 'fitting': 'NOT_EXECUTED', 'collision_assessment': 'REQUIRED'}
