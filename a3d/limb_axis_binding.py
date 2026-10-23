"""Source-sized tube guides on an explicitly selected measured body segment.

The axial endpoint is a geometric reference, not a new skin attachment. No
source length is scaled to the distance between body landmarks.
"""
import copy
import math
from pathlib import Path

from .anatomy_profile import unit
from .anatomical_placement import STANDARD_REGIONS
from .contact_geometry import cross, dot
from .core import StudioError, digest, sha
from .sewing import edge_chain


MODE = 'LIMB_SEGMENT_AXIS_V1'


def _vector(value, label):
    if (not isinstance(value, (list, tuple)) or len(value) != 3 or
            any(type(x) not in (int, float) or not math.isfinite(x) for x in value)):
        raise StudioError('Segment axis requires finite '+label)
    return list(value)


def resolve_segment_axis(piece, profile, policy):
    required = {'guide_kind', 'anatomical_region', 'axis_landmarks',
                'transverse_direction_body', 'source_end_edges', 'source_anchor_end'}
    if (not isinstance(policy, dict) or set(policy)-{'surface_envelope'} != required
            or policy.get('guide_kind') != MODE):
        raise StudioError('Segment axis requires an explicit complete policy')
    region = policy['anatomical_region']
    if (not isinstance(region, str) or
            (region not in STANDARD_REGIONS and not (region.startswith('custom:') and region[7:].strip()))):
        raise StudioError('Segment axis requires a declared anatomical region')
    names = policy['axis_landmarks']
    if (not isinstance(names, list) or len(names) != 2 or
            any(not isinstance(name, str) or not name for name in names) or names[0] == names[1]):
        raise StudioError('Segment axis requires two distinct proximal/distal landmarks')
    endpoints = [_vector(profile.get('landmarks', {}).get(name, {}).get('point_cm'), 'measured landmarks')
                 for name in names]
    axis = [b-a for a, b in zip(*endpoints)]
    axis_length = math.hypot(*axis)
    if not math.isfinite(axis_length) or axis_length <= 1e-10:
        raise StudioError('Segment axis landmarks must define a nonzero segment')
    downward = [x/axis_length for x in axis]
    forward = _vector(policy['transverse_direction_body'], 'transverse direction')
    length = math.hypot(*forward)
    if not math.isfinite(length) or length <= 1e-10:
        raise StudioError('Segment axis transverse direction must be finite and nonzero')
    forward = [x/length for x in forward]
    transverse = [forward[i]-dot(forward, downward)*downward[i] for i in range(3)]
    if math.hypot(*transverse) <= 1e-10:
        raise StudioError('Segment axis transverse direction is parallel or zero')
    transverse = unit(transverse)
    edges = policy['source_end_edges']
    if (not isinstance(edges, dict) or set(edges) != {'proximal', 'distal'} or
            any(not isinstance(name, str) or name not in piece.get('edges', {}) for name in edges.values()) or
            edges['proximal'] == edges['distal']):
        raise StudioError('Segment axis requires two distinct actual source end edges')
    stops = {}
    for end, name in edges.items():
        chain = edge_chain(piece, name)[1]
        values = [point[1] for point in chain]
        if not values or min(values) != max(values):
            raise StudioError('Segment source end edges must have constant material V')
        stops[end] = values[0]
    bounds = [min(p[1] for p in piece['vertices']), max(p[1] for p in piece['vertices'])]
    if (not all(type(x) in (int, float) and math.isfinite(x) for x in stops.values()) or
            bounds[1]-bounds[0] <= 1e-10 or sorted(stops.values()) != bounds):
        raise StudioError('Segment source end edges must bound the full material V domain')
    anchor = policy['source_anchor_end']
    if anchor not in ('proximal', 'distal'):
        raise StudioError('Segment axis requires an explicit source anchor end')
    sign = 1. if stops['distal'] > stops['proximal'] else -1.
    origin = endpoints[0 if anchor == 'proximal' else 1]
    other_end = 'distal' if anchor == 'proximal' else 'proximal'
    opposite_center = [origin[i]+downward[i]*sign*(stops[other_end]-stops[anchor]) for i in range(3)]
    identity = {'mode': MODE, 'policy': copy.deepcopy(policy), 'profile_sha256': digest(profile),
                'source_piece_sha256': digest(piece), 'kernel_sha256': sha(Path(__file__))}
    return {'origin_body_cm': origin, 'downward_body': downward,
            'transverse_body': transverse, 'tangent_body': unit(cross(downward, transverse)),
            'source_anchor_v_cm': stops[anchor], 'source_v_direction': sign,
            'evidence': {'mode': MODE, 'binding_sha256': digest(identity), **identity,
                'source_end_v_cm': stops, 'anchor_end': anchor, 'axis_landmarks': list(names),
                'anchor_landmark': names[0 if anchor == 'proximal' else 1],
                'anchor_body_cm': list(origin), 'body_segment_length_cm': math.hypot(*axis),
                'source_axial_length_cm': bounds[1]-bounds[0], 'source_axial_scale': 1.,
                'opposite_end_center_body_cm': opposite_center,
                'opposite_landmark_residual_cm': math.dist(opposite_center, endpoints[1 if anchor == 'proximal' else 0]),
                'anatomical_attachment_added': False, 'longitudinal_correspondence': 'DECLARED_GUIDE_HYPOTHESIS',
                'source_uv_scaled': False, 'body_rescaling': False, 'qualification': 'NONE'}}


def segment_center(binding, source_v):
    offset = binding['source_v_direction']*(source_v-binding['source_anchor_v_cm'])
    return [binding['origin_body_cm'][i]+binding['downward_body'][i]*offset for i in range(3)]
