"""Declared reversible UV and static rigid LOD variants, never source edits."""
import math

from .core import StudioError, contract, digest, inside, read_json, sha


def validate_finishing_profile(profile):
    contract('asset-finishing', profile)
    if set(profile['object_names']) & set(profile['dependency_names']):
        raise StudioError('Finishing source objects and dependencies must be distinct')
    names = [row['object_name'] for row in profile['operations']]
    if len(set(names)) != len(names) or not set(names) <= set(profile['object_names']):
        raise StudioError('Finishing requires one declared operation per selected source object')
    lod_ids = []
    for operation in profile['operations']:
        uv = operation['uv']
        if operation['role'] == 'PATTERN_SEWN' and (uv['method'] != 'PRESERVE_SOURCE' or operation['lods']):
            raise StudioError('Sewn source UV and topology must be preserved; pattern LOD needs a separate qualified mapping')
        lod_ids.extend(row['id'] for row in operation['lods'])
    if len(set(lod_ids)) != len(lod_ids):
        raise StudioError('LOD variant identities must be unique')
    if len(lod_ids) > profile['budgets']['max_lod_clones']:
        raise StudioError('Finishing LOD clone budget is insufficient')
    if len({row['datablock_name'] for row in profile['resources']}) != len(profile['resources']):
        raise StudioError('Finishing resources must have unique native identities')
    if set(profile['embedded_image_names']) & {row['datablock_name'] for row in profile['resources']}:
        raise StudioError('Finishing embedded and external resources must be distinct')
    return profile


def finishing_descriptor(project, profile_path):
    path = inside(project.root, profile_path); profile = validate_finishing_profile(read_json(path))
    source = inside(project.root, profile['source_ref']['path'])
    if source.suffix.lower() != '.blend' or sha(source) != profile['source_ref']['sha256']:
        raise StudioError('Finishing requires the exact immutable native candidate')
    evidence = [{'path': profile_path, 'sha256': sha(path)}, profile['source_ref']]
    for resource in profile['resources']:
        reference = resource['file_ref']
        if sha(inside(project.root, reference['path'])) != reference['sha256']:
            raise StudioError('Finishing resource changed: ' + reference['path'])
        evidence.append(reference)
    return {'profile': profile, 'profile_ref': evidence[0], 'source': source,
            'evidence': evidence, 'cache_key': digest(evidence)}


def source_uv_identity(faces, values):
    if sum(len(face) for face in faces) != len(values) or any(len(point) != 2 or any(not math.isfinite(x) for x in point) for point in values):
        raise StudioError('Source UV must retain one finite pair per immutable face corner')
    return digest({'faces': faces, 'uv': values})


def assess_lod(request, measured):
    """Classify actual native face counts and symmetric sampled surface error.

This metric covers all declared source/LOD vertices and face centroids. It is
not a continuous Hausdorff bound or a rig, material, fitting or engine PASS.
"""
    for name in ('source_faces', 'source_triangles', 'lod_faces', 'lod_triangles', 'expected_samples', 'executed_samples'):
        if type(measured.get(name)) is not int or measured[name] < 0:
            raise StudioError('LOD has invalid native count: ' + name)
    error = measured.get('max_surface_error_cm')
    if error is not None and (type(error) not in (float, int) or not math.isfinite(error) or error < 0.):
        raise StudioError('LOD surface error must be finite and nonnegative')
    if measured['source_faces'] < 1 or measured['source_triangles'] < 1 or measured['expected_samples'] < 1:
        raise StudioError('LOD source surface is empty')
    defects = []
    if measured['executed_samples'] != measured['expected_samples'] or error is None:
        status = 'INCOMPLETE'; defects.append('SURFACE_SAMPLE_BUDGET')
    else:
        if measured['lod_faces'] < 1 or measured['lod_faces'] > request['max_faces']:
            defects.append('FACE_BUDGET')
        if measured['lod_triangles'] > measured['source_triangles']:
            defects.append('TRIANGLE_COUNT_INCREASED')
        if error > request['max_geometry_error_cm']:
            defects.append('GEOMETRY_ERROR_BUDGET')
        status = 'LOD_GEOMETRY_WITHIN_BUDGET' if not defects else 'NEEDS_CORRECTION'
    return {'id': request['id'], 'status': status, 'requested_triangle_ratio': request['ratio'],
            'observed_triangle_ratio': measured['lod_triangles']/measured['source_triangles'],
            'metrics': measured, 'defects': defects, 'metric_scope': 'SYMMETRIC_VERTICES_AND_FACE_CENTROIDS',
            'continuous_surface_bound': 'NOT_QUALIFIED', 'animation_qualification': 'NOT_QUALIFIED',
            'engine_qualification': 'NOT_QUALIFIED', 'artistic_review': 'REQUIRED'}
