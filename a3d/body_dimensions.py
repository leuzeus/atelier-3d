"""Deterministic stature variants of an immutable evaluated body mesh.

This operation targets height only. A uniform scale also changes all girths;
those girths are measured again, never treated as approved wearer targets.
The source foot plane stays fixed, and no garment or regional body correction
is performed. Scene creation and rig persistence belong to the native caller.
"""
import copy
import math

from .anatomy_profile import profile_mesh
from .core import StudioError, digest, relative


def _finite_vector(value, size=3):
    return (isinstance(value, (list, tuple)) and len(value) == size
            and all(type(x) in (int, float) and math.isfinite(x) for x in value))


def _source_reference(value):
    if isinstance(value, str) and value:
        return
    if not isinstance(value, dict) or set(value) != {'path', 'sha256'}:
        raise StudioError('Body landmark provenance needs a nonempty label or exact path and SHA-256')
    relative(value['path'])
    identity = value['sha256']
    if not isinstance(identity, str) or len(identity) != 64 or any(c not in '0123456789abcdef' for c in identity):
        raise StudioError('Body landmark provenance has an invalid source SHA-256')


def _validate(geometry, options, target):
    if type(target) not in (int, float) or not math.isfinite(target) or not 30 <= target <= 400:
        raise StudioError('Target body stature must be finite and within 30 to 400 cm')
    if not isinstance(geometry, dict) or not isinstance(options, dict):
        raise StudioError('Body dimensions require evaluated geometry and declared frame options')
    points, faces = geometry.get('vertices_cm'), geometry.get('faces')
    if (not isinstance(points, (list, tuple)) or not points
            or any(not _finite_vector(point) for point in points)
            or not isinstance(faces, (list, tuple)) or not faces
            or any(not isinstance(face, (list, tuple)) or len(face) < 3
                   or any(type(index) is not int or not 0 <= index < len(points) for index in face)
                   or len(set(face)) != len(face)
                   for face in faces)):
        raise StudioError('Body dimensions require finite mesh points and distinct valid face indices')
    for key in ('source_sha256', 'pose_sha256'):
        value = geometry.get(key)
        if not isinstance(value, str) or len(value) != 64 or any(c not in '0123456789abcdef' for c in value):
            raise StudioError('Body dimensions require immutable source and evaluated pose identities')
    for key in ('up_axis', 'forward_axis'):
        if not _finite_vector(options.get(key)):
            raise StudioError('Body dimensions require finite declared up and forward axes')
    if not _finite_vector(options.get('origin_cm', [0., 0., 0.])):
        raise StudioError('Body frame origin must be finite')
    if 'torso_seed_xy_cm' in options and not _finite_vector(options['torso_seed_xy_cm'], 2):
        raise StudioError('Body section seed must be finite in the declared frame')
    landmarks = geometry.get('rig_landmarks', {})
    if (not isinstance(landmarks, dict)
            or any(not isinstance(value, dict) or not _finite_vector(value.get('point_cm'))
                   for value in landmarks.values())):
        raise StudioError('Evaluated rig landmarks need finite world points and source provenance')
    for value in landmarks.values():
        _source_reference(value.get('source_ref'))
    try:
        digest([geometry, options])
    except (TypeError, ValueError) as error:
        raise StudioError('Body inputs must be finite serializable evaluated evidence') from error


def variant_by_stature(geometry, options, target_stature_cm):
    """Return a new evaluated geometry, frame options, profile and source receipt.

    The geometry contract uses world vertices/rig landmarks in cm, valid faces,
    source_sha256 and pose_sha256. Options follow anatomy_profile.profile_mesh.
    Scaling is uniform around frame.origin_cm + source.floor_cm * frame.up;
    the source floor plane and orientation therefore remain unchanged. Existing
    section seeds and rig landmarks follow the same transform. Unrecognized
    geometry metadata is not copied as if it remained valid for the variant.

    The evaluated pose receives a new identity even for a height-only operation.
    Measurement and placement evidence from the source must not be reused.
    No body regions, garment geometry, fitting gates or source data are edited.
    """
    _validate(geometry, options, target_stature_cm)
    source_before = digest([geometry, options])
    source = profile_mesh(geometry, options)
    factor = float(target_stature_cm)/source['stature_cm']
    basis = source['frame']
    anchor = [basis['origin_cm'][i]+source['floor_cm']*basis['up'][i] for i in range(3)]

    def transform(point):
        return [anchor[i]+factor*(point[i]-anchor[i]) for i in range(3)]

    points = [transform(point) for point in geometry['vertices_cm']]
    faces = [list(face) for face in geometry['faces']]
    geometry_identity = digest([points, faces])
    operation = {'method': 'UNIFORM_STATURE_SOURCE_FLOOR',
                 'source_sha256': geometry['source_sha256'],
                 'source_pose_sha256': geometry['pose_sha256'],
                 'source_geometry_sha256': source['geometry_sha256'],
                 'source_profile_cache_key': source['cache_key'],
                 'source_rig_landmark_references': {name: copy.deepcopy(value['source_ref'])
                    for name, value in geometry.get('rig_landmarks', {}).items()},
                 'target_stature_cm': float(target_stature_cm), 'uniform_factor': factor,
                 'frame': copy.deepcopy(basis), 'floor_anchor_world_cm': anchor,
                 'variant_geometry_sha256': geometry_identity}
    operation_key = digest(operation)
    variant = {'vertices_cm': points, 'faces': faces, 'source_sha256': geometry['source_sha256'],
               'pose_sha256': digest({'source_pose_sha256': geometry['pose_sha256'],
                                      'dimension_operation_key': operation_key}),
               'dimension_derivation': dict(operation, cache_key=operation_key)}
    if 'rig_landmarks' in geometry:
        variant['rig_landmarks'] = {}
        for name, value in geometry['rig_landmarks'].items():
            landmark = copy.deepcopy(value)
            reference = value['source_ref']
            landmark.update(point_cm=transform(value['point_cm']),
                            source_ref='stature-variant:'+operation_key+':'+(
                                reference if isinstance(reference, str) else digest(reference)))
            variant['rig_landmarks'][name] = landmark
    variant_options = copy.deepcopy(options)
    if 'torso_seed_xy_cm' in options:
        variant_options['torso_seed_xy_cm'] = [factor*x for x in options['torso_seed_xy_cm']]
    measured = profile_mesh(variant, variant_options)
    if (abs(measured['stature_cm']-target_stature_cm) > 1e-9*target_stature_cm
            or abs(measured['floor_cm']-source['floor_cm']) > 1e-9*target_stature_cm):
        raise StudioError('Dimension transform failed its target stature or preserved floor check')
    if digest([geometry, options]) != source_before:
        raise StudioError('Body source or measurement options changed during dimensioning')
    girths = {name: point['girth_cm'] for name, point in measured['landmarks'].items()
              if 'girth_cm' in point}
    receipt = dict(operation, version=1, status='STATURE_VARIANT_MEASURED',
                   qualification='HEIGHT_ONLY', units='cm', dimension_operation_key=operation_key,
                   source_input_sha256=source_before, source_stature_cm=source['stature_cm'],
                   measured_stature_cm=measured['stature_cm'], floor_policy='PRESERVE_SOURCE_PLANE',
                   source_floor_cm=source['floor_cm'], measured_floor_cm=measured['floor_cm'],
                   topology_sha256=digest(faces), topology_preserved=True,
                   variant_pose_sha256=variant['pose_sha256'], variant_profile_cache_key=measured['cache_key'],
                   variant_options_sha256=digest(variant_options), measured_bounds_cm=measured['bounds_cm'],
                   measured_girths_cm=girths, girth_targets='NOT_REQUESTED',
                   mensurations_review='REQUIRED_BEFORE_FITTING', source_mutated=False,
                   regional_adjustments='NOT_PERFORMED', garment_adjustments='NOT_PERFORMED',
                   ai_adjustments='NOT_USED', simulation='NOT_EXECUTED', fitting='NOT_EXECUTED',
                   prior_evidence_invalidated=['ANATOMY_PROFILE', 'SURFACE_LANDMARKS', 'BODY_CONTACTS',
                                               'GARMENT_PLACEMENT', 'CLOTH', 'FITTING', 'ARTISTIC_REVIEW'])
    receipt['cache_key'] = digest(receipt)
    return {'geometry': variant, 'options': variant_options, 'profile': measured, 'receipt': receipt}
