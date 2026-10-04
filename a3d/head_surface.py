"""Measured head cross-section from reviewed source face identities."""
import copy

from .anatomy_profile import surface_section
from .contact_geometry import dot, sub
from .core import StudioError, digest


def head_face_ids(geometry, adapter):
    """Retain source face identities, without rebinding an original adapter."""
    labels = geometry.get('face_sets', [])
    if len(labels) != len(geometry['faces']):
        raise StudioError('Head section requires exact source face-region identities')
    regions = {int(label) for label, bone in adapter.get('region_to_bone', {}).items() if bone == 'head'}
    if not regions:
        regions = set(adapter.get('centers', {}).get('head.center', []))
    selected = [index for index, label in enumerate(labels) if label in regions]
    if not selected or not adapter.get('source_ref'):
        raise StudioError('Head section requires explicitly sourced head segmentation')
    return selected


def measured_head_surface(profile, geometry, face_ids, source_ref):
    identity = digest([geometry['vertices_cm'], geometry['faces']])
    if (profile.get('geometry_sha256') != identity or
            profile.get('source_sha256') != geometry.get('source_sha256') or
            profile.get('pose_sha256') != geometry.get('pose_sha256')):
        raise StudioError('Head section requires exact evaluated body profile geometry and pose')
    if ('head_surface_source' in profile or 'surface_landmarks_source' in profile or
            profile.get('surface_sections', {}).get('head')):
        raise StudioError('Measure head before shoulder surfaces, from a clean base profile')
    head = profile['landmarks'].get('head.center')
    if not head or not head.get('source_ref'):
        raise StudioError('Head section requires a sourced evaluated head center')
    if (not isinstance(face_ids, list) or not face_ids or len(set(face_ids)) != len(face_ids) or
            any(type(index) is not int or not 0 <= index < len(geometry['faces']) for index in face_ids) or
            not source_ref):
        raise StudioError('Head section needs actual unique source face IDs and provenance')
    basis = profile['frame']
    local = [[dot(sub(point, basis['origin_cm']), basis[key]) for key in ('right', 'forward', 'up')]
             for point in geometry['vertices_cm']]
    center = head['point_cm']; section = surface_section(local, [geometry['faces'][i] for i in face_ids],
                                                        center[2]+.000031, center[:2])
    section['source_ref'] = copy.deepcopy(source_ref)
    section['measurement_plane'] = 'EVALUATED_HEAD_CENTER_HEIGHT_IN_DECLARED_FRAME'
    section['full_head_envelope'] = 'NOT_QUALIFIED'
    result = copy.deepcopy(profile); result.setdefault('surface_sections', {})['head'] = section
    evidence = {'geometry_sha256': identity, 'source_sha256': geometry['source_sha256'],
                'pose_sha256': geometry['pose_sha256'], 'base_profile_sha256': digest(profile),
                'previous_cache_key': profile['cache_key'], 'face_ids_sha256': digest(face_ids),
                'source_ref': copy.deepcopy(source_ref), 'head_center_sha256': digest(head),
                'section_sha256': digest(section), 'body_mutated': False}
    result['head_surface_source'] = evidence
    result['cache_key'] = digest({'base_profile': profile['cache_key'], 'head_surface_source': evidence})
    return result


def head_section(profile):
    """Return the authenticated section, including any explicit refusal state."""
    # Shoulder authentication binds the complete pre-shoulder profile. Verify it
    # before returning to the pre-shoulder head evidence for its own checks.
    if 'surface_landmarks_source' in profile:
        from .shoulder_surface import surface_anchors
        surface_anchors(profile)
        base = copy.deepcopy(profile); source = base.pop('surface_landmarks_source')
        base['cache_key'] = source['previous_cache_key']
        for side in ('left', 'right'):
            del base['landmarks']['shoulder.surface.'+side]
    else:
        base = copy.deepcopy(profile)
    evidence = base.get('head_surface_source', {}); section = base.get('surface_sections', {}).get('head')
    if (not section or any(evidence.get(key) != base.get(key) for key in
            ('geometry_sha256', 'source_sha256', 'pose_sha256')) or
            evidence.get('body_mutated') is not False or evidence.get('section_sha256') != digest(section) or
            evidence.get('head_center_sha256') != digest(base['landmarks'].get('head.center')) or
            base['cache_key'] != digest({'base_profile': evidence.get('previous_cache_key'), 'head_surface_source': evidence})):
        raise StudioError('Head section changed or lacks exact evaluated surface provenance')
    original = copy.deepcopy(base); del original['head_surface_source']; del original['surface_sections']['head']
    if not original['surface_sections']:
        del original['surface_sections']
    original['cache_key'] = evidence['previous_cache_key']
    if digest(original) != evidence.get('base_profile_sha256'):
        raise StudioError('Head measurement base profile changed; remeasure the evaluated body')
    return copy.deepcopy(section)


def head_surface_section(profile):
    """Public accessor matching the garment-guide surface naming."""
    return head_section(profile)
