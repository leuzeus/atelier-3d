"""Explicit source-bound motion programs and whole-clip temporal evidence."""
import copy
import math

from .core import StudioError, contract, digest


def validate_motion_profile(profile, rig_specification=None):
    contract('motion-profile', profile)
    if profile['frame_end'] <= profile['frame_start']:
        raise StudioError('Motion clip end must follow its start')
    if (profile['frame_end']-profile['frame_start'])*profile['intermediate_substeps'] > 20000:
        raise StudioError('Motion clip exceeds the bounded temporal evaluation budget')
    identities = set()
    for track in profile['tracks']:
        identity = (track['bone'], track['axis'])
        if identity in identities:
            raise StudioError('Motion profile repeats a bone rotation channel')
        identities.add(identity)
        frames = [key['frame'] for key in track['keys']]
        if frames != sorted(set(frames)) or frames[0] != profile['frame_start'] or frames[-1] != profile['frame_end']:
            raise StudioError('Every motion track must have ordered keys covering the complete clip')
    if rig_specification is not None:
        names = {bone['name'] for bone in rig_specification['bones']}
        if any(track['bone'] not in names for track in profile['tracks']):
            raise StudioError('Motion clip refers to a missing derived bone')
        if (profile['body_geometry_sha256'] != rig_specification.get('evaluated_geometry_sha256') or
                profile['rig_specification_sha256'] != rig_specification['cache_key']):
            raise StudioError('Motion profile is stale for the exact target geometry or rig specification')
    return profile


def sample_times(profile):
    validate_motion_profile(profile)
    start, end = profile['frame_start'], profile['frame_end']
    major = list(range(start, end, profile['sample_interval_frames']))+[end]
    times = []
    for left, right in zip(major, major[1:]):
        times.extend(left+(right-left)*step/profile['intermediate_substeps']
                     for step in range(profile['intermediate_substeps']))
    return times+[float(end)]


def verify_sample_coverage(profile, samples):
    expected = sample_times(profile)
    if not isinstance(samples, list) or [sample.get('time') for sample in samples] != expected:
        raise StudioError('Motion evidence does not cover every required frame and intermediate sample')
    topology = samples[0].get('topology_sha256'); intervals = []
    if not topology:
        raise StudioError('Motion collider samples need exact source topology identities')
    for sample in samples:
        if sample.get('topology_sha256') != topology:
            raise StudioError('Motion collider topology changes across the clip')
        vertices = sample.get('vertices_cm')
        if (not isinstance(vertices, list) or not vertices or any(not isinstance(p, list) or len(p) != 3 or
                any(type(x) not in (int, float) or not math.isfinite(x) for x in p) for p in vertices)):
            raise StudioError('Motion collider samples require finite evaluated vertices')
    for previous, current in zip(samples, samples[1:]):
        if len(previous['vertices_cm']) != len(current['vertices_cm']):
            raise StudioError('Motion collider vertex correspondence changed')
        maximum = max(math.dist(a, b) for a, b in zip(previous['vertices_cm'], current['vertices_cm']))
        intervals.append({'from_time': previous['time'], 'to_time': current['time'],
                          'max_increment_cm': maximum,
                          'within_declared_sampling_budget': maximum <= profile['max_increment_cm']})
    complete = all(row['within_declared_sampling_budget'] for row in intervals)
    return {'status': 'CLIP_SAMPLES_COMPLETE' if complete else 'TEMPORAL_RESOLUTION_INSUFFICIENT',
            'profile_sha256': digest(profile), 'samples': len(samples), 'intervals': intervals,
            'frame_start': profile['frame_start'], 'frame_end': profile['frame_end'],
            'topology_sha256': topology, 'sampling_policy': 'EVALUATED_FRAMES_AND_DECLARED_INTERMEDIATE_SUBSTEPS',
            'continuous_collision_qualification': 'NOT_GRANTED', 'fitting': 'NOT_EXECUTED'}


def standard_motion_profile(clip_id, rig_specification, source_ref, frame_start=1, frame_end=25):
    """Declared inspection clips; bone-axis and artistic review remain required."""
    midpoint = (frame_start+frame_end)//2
    def track(bone, axis, values):
        return {'bone': bone, 'axis': axis, 'keys': [{'frame': frame, 'radians': value}
                for frame, value in zip((frame_start, midpoint, frame_end), values)]}
    if clip_id == 'elbow_flexion':
        tracks = [track('forearm.'+side, 'X', (0., 1.2, 0.)) for side in ('left', 'right')]
    elif clip_id == 'arm_raise':
        tracks = [track('upper_arm.'+side, 'Z', (0., sign*.8, 0.))
                  for side, sign in [('left', 1.), ('right', -1.)]]
    elif clip_id == 'walk':
        tracks = [track(bone+'.'+side, 'X', (sign*angle, -sign*angle, sign*angle))
                  for bone, angle in [('thigh', .3), ('upper_arm', -.2)]
                  for side, sign in [('left', 1.), ('right', -1.)]]
        tracks += [track('shin.'+side, 'X', (0., .35, 0.)) for side in ('left', 'right')]
    else:
        raise StudioError('Unknown standard inspection motion clip')
    profile = {'version': 1, 'clip_id': clip_id,
               'body_geometry_sha256': rig_specification['evaluated_geometry_sha256'],
               'rig_specification_sha256': rig_specification['cache_key'], 'source_ref': source_ref,
               'fps': 24, 'frame_start': frame_start, 'frame_end': frame_end,
               'sample_interval_frames': 1, 'intermediate_substeps': 2, 'max_increment_cm': 3.,
               'interpolation': 'LINEAR', 'axis_convention': 'DERIVED_BONE_LOCAL_XYZ_REQUIRES_REVIEW', 'tracks': tracks}
    return validate_motion_profile(profile, rig_specification)


def target_rig_specification(source_geometry, source_adapter, orientation, target_geometry, target_profile, smoothing_passes=4):
    """Derive target skeleton and weights from the unchanged source rig recipe.

    Source adapter admission runs against the original metric. The target uses
    its measured derived landmarks; the original adapter is never rebound to it.
    Native deformations and bone-axis reviews remain separate qualification.
    """
    from .mannequin_rig import prepare_rig
    source = prepare_rig(source_geometry, source_adapter, orientation, smoothing_passes)
    if (source_geometry['faces'] != target_geometry['faces'] or
            source_geometry.get('face_sets') != target_geometry.get('face_sets') or
            source_geometry['source_sha256'] != target_geometry['source_sha256'] or
            digest([target_geometry['vertices_cm'], target_geometry['faces']]) != target_profile['geometry_sha256'] or
            target_geometry['pose_sha256'] != target_profile['pose_sha256']):
        raise StudioError('Target motion rig requires exact preserved source topology and current measured profile')
    points = {name: row['point_cm'] for name, row in target_geometry.get('rig_landmarks', {}).items()}
    basis = target_profile['frame']
    def world(point):
        return [basis['origin_cm'][i]+sum(point[j]*basis[key][i] for j, key in enumerate(('right', 'forward', 'up')))
                for i in range(3)]
    for name in ('waist', 'chest'):
        points[name+'.center'] = world(target_profile['landmarks'][name]['point_cm'])
    head = target_profile['landmarks']['head.center']['point_cm']
    points['head.top'] = world([head[0], head[1], target_profile['bounds_cm'][1][2]])
    endpoints = {'pelvis': ('pelvis.center', 'waist.center'), 'spine.lower': ('waist.center', 'chest.center'),
                 'spine.upper': ('chest.center', 'neck.base'), 'neck': ('neck.base', 'head.center'),
                 'head': ('head.center', 'head.top')}
    for side in ('left', 'right'):
        for bone, start, end in [('upper_arm', 'shoulder', 'elbow'), ('forearm', 'elbow', 'wrist'),
                                 ('hand', 'wrist', 'hand'), ('thigh', 'hip', 'knee'), ('shin', 'knee', 'ankle'),
                                 ('foot', 'ankle', 'foot')]:
            endpoints[bone+'.'+side] = (start+'.'+side, end+'.'+side)
    bones = []
    for original in source['bones']:
        start, end = endpoints[original['name']]
        if start not in points or end not in points or math.dist(points[start], points[end]) < .5:
            raise StudioError('Target motion rig lacks noncollapsed source-derived anatomical endpoints')
        bones.append(dict(copy.deepcopy(original), head_cm=list(points[start]), tail_cm=list(points[end])))
    specification = dict(copy.deepcopy(source), bones=bones,
                         geometry_sha256=digest([target_geometry['vertices_cm'], target_geometry['faces'], target_geometry['face_sets']]),
                         evaluated_geometry_sha256=target_profile['geometry_sha256'],
                         profile_cache_key=target_profile['cache_key'], source_rig_sha256=source['cache_key'],
                         source_adapter_rebound=False, target_pose_sha256=target_profile['pose_sha256'],
                         topology_sha256=digest([target_geometry['faces'], target_geometry['face_sets']]),
                         weights_sha256=digest(source['weights']),
                         target_derivation_sha256=digest(target_geometry.get('dimension_derivation', {})),
                         deformation='NOT_EXECUTED', anatomical_review='REQUIRED',
                         bone_axis_review='REQUIRED', qualification='PREPARED_DERIVED_RIG_ONLY')
    specification.pop('cache_key', None); specification['cache_key'] = digest(specification)
    return specification


def motion_evidence_binding(profile, rig_specification, action_sha256, weights_sha256, topology_sha256):
    validate_motion_profile(profile, rig_specification)
    values = [action_sha256, weights_sha256, topology_sha256]
    if any(not isinstance(value, str) or len(value) != 64 or any(c not in '0123456789abcdef' for c in value) for value in values):
        raise StudioError('Motion evidence needs exact Action, weights and topology identities')
    return digest({'profile': profile, 'rig': rig_specification['cache_key'], 'action': action_sha256,
                   'weights': weights_sha256, 'topology': topology_sha256})
