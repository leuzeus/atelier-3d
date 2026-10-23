"""Bounded native animation review. Rendered pixels never grant fitting or art approval."""
import copy
import math

from .core import StudioError, contract, digest, inside, read_json, sha
from .dressing import _reference
from .export_profiles import clip_tracks, export_descriptor, motion_qualification


VIEW_DIRECTIONS = {'front': (0., -1., 0.), 'side': (1., 0., 0.),
                   'back': (0., 1., 0.), 'threequarter': (1., -1., .25)}


def render_schedule(profile, export_profile):
    """Every original integer frame, plus every H264 encoder frame, is budgeted."""
    if profile['clip_ids'] != [clip['id'] for clip in export_profile['clips']]:
        raise StudioError('Motion review must preserve all source clip identities and their order')
    if not profile['clip_ids']:
        raise StudioError('Motion review requires complete source clips')
    if profile['object_names'] != export_profile['object_names'] or profile['fps'] != export_profile['fps']:
        raise StudioError('Motion review objects and FPS must match the exact export profile')
    if any(value % 2 for value in profile['resolution']):
        raise StudioError('H264 review resolution must have even dimensions')
    frames = sum(clip['frame_end'] - clip['frame_start'] + 1 for clip in export_profile['clips'])
    still_count = frames * len(profile['views'])
    if still_count * 2 > profile['budgets']['max_render_frames']:
        raise StudioError('Motion review render budget cannot cover every still and encoder frame')
    return {'still_frames': still_count, 'encoder_frames': still_count,
            'total_render_frames': still_count * 2,
            'clips': [{'id': clip['id'], 'frames': list(range(clip['frame_start'], clip['frame_end'] + 1))}
                      for clip in export_profile['clips']]}


def _expected_actions(export_profile, receipts):
    """Use canonical measured receipts, never a flag on the review profile."""
    actions = {}
    for receipt in receipts:
        if receipt.get('native_dispatch_verified') is not True:
            continue
        if receipt.get('candidate') != export_profile['source_ref']:
            continue
        for clip in receipt.get('clips', []):
            if clip.get('id') not in {row['id'] for row in export_profile['clips']}:
                continue
            for track in clip_tracks(clip):
                identity = track.get('action_sha256')
                if not isinstance(identity, str) or len(identity) != 64:
                    raise StudioError('Motion review requires exact canonical native Action digests')
                previous = actions.setdefault(track['action_name'], identity)
                if previous != identity:
                    raise StudioError('Motion review canonical Action identity is ambiguous')
    qualification = motion_qualification(export_profile, receipts, actions)
    if qualification['status'] != 'EXACT_CANDIDATE_CLIPS_VERIFIED':
        raise StudioError('Motion review requires canonical complete measured native clips')
    return actions


def review_motion_descriptor(project, profile_path):
    path = inside(project.root, profile_path)
    profile = contract('review-motion', read_json(path))
    reference = profile['export_profile_ref']; _reference(reference)
    if sha(inside(project.root, reference['path'])) != reference['sha256']:
        raise StudioError('Motion review export profile changed')
    export = export_descriptor(project, reference['path'])
    schedule = render_schedule(profile, export['profile'])
    expected_actions = _expected_actions(export['profile'], export['receipts'])
    evidence = [{'path': profile_path, 'sha256': sha(path)}, *export['evidence']]
    return {'profile': copy.deepcopy(profile), 'profile_ref': evidence[0], 'export': export,
            'schedule': schedule, 'expected_actions': expected_actions,
            'max_sample_vertex_frames': profile['budgets'].get('max_sample_vertex_frames', 10000000),
            'evidence': evidence, 'binding_sha256': digest(evidence)}


def camera_plan(points_cm, view, resolution, margin=.08):
    """Conservative orthographic bounds over every evaluated source frame."""
    if view not in VIEW_DIRECTIONS or not points_cm:
        raise StudioError('Motion review needs a supported view and measured clip bounds')
    if any(len(point) != 3 or any(type(v) not in (int, float) or not math.isfinite(v) for v in point)
           for point in points_cm):
        raise StudioError('Motion review clip bounds contain invalid coordinates')
    if (len(resolution) != 2 or any(type(v) is not int or v <= 0 for v in resolution) or
            type(margin) not in (int, float) or not math.isfinite(margin) or not 0 < margin < .4):
        raise StudioError('Motion review camera aspect or margin is invalid')
    def unit(value):
        length = math.sqrt(sum(v*v for v in value))
        return [v/length for v in value]
    def cross(a, b):
        return [a[1]*b[2]-a[2]*b[1], a[2]*b[0]-a[0]*b[2], a[0]*b[1]-a[1]*b[0]]
    low = [min(p[i] for p in points_cm) for i in range(3)]
    high = [max(p[i] for p in points_cm) for i in range(3)]
    center = [(a+b)/2 for a, b in zip(low, high)]
    outward = unit(VIEW_DIRECTIONS[view]); look = [-v for v in outward]
    right = unit(cross(look, (0., 0., 1.))); up = cross(right, look)
    extents = []
    for axis in (right, up, outward):
        values = [sum((p[i]-center[i])*axis[i] for i in range(3)) for p in points_cm]
        extents.append(max(values)-min(values))
    aspect = resolution[0]/resolution[1]
    # Covers either Blender sensor-fit convention; native projection verifies
    # all vertices as well. The camera may have generous blank margins.
    scale = max(extents[0], extents[1], .1)*max(aspect, 1/aspect, 1.)/(1-2*margin)
    distance = max(200., scale*3, extents[2]*3)
    return {'center_cm': center, 'direction': outward, 'right': right, 'up': up,
            'ortho_scale_cm': scale, 'distance_cm': distance,
            'bounds_cm': [low, high], 'projected_extents_cm': extents, 'minimum_margin': margin}


def validate_movie_metadata(frame_count, size, expected_frames, resolution, observed_fps=None, expected_fps=None):
    if type(frame_count) is not int or frame_count != expected_frames or list(size) != list(resolution):
        raise StudioError('Reloaded review movie duration or dimensions differ from every rendered frame')
    if expected_fps is not None and (type(observed_fps) not in (int, float) or not math.isfinite(observed_fps)
                                    or not math.isclose(observed_fps, expected_fps, rel_tol=0, abs_tol=1e-6)):
        raise StudioError('Reloaded review movie FPS differs from its exact source')
    return {'status': 'MOVIE_RELOADED_METADATA_MATCHES', 'frame_count': frame_count,
            'size': list(size), 'fps': observed_fps,
            'decode_scope': 'NATIVE_MOVIE_METADATA_NOT_PIXEL_IDENTITY_WITH_LOSSY_H264'}
