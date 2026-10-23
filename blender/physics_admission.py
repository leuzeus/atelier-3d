"""Verify the live static body against the exact reviewed native fit target."""
from a3d.core import StudioError, digest, inside, read_json
from a3d.physics_admission import require_recipe_fit_intent


def require_native_fit_body(project, body_ref, body_object):
    """Read-only live body check shared by legacy and grouped static physics."""
    import bpy
    from a3d.native_evidence import checked_reference, native_origin
    checked_reference(project, body_ref)
    body = body_object
    profile = read_json(inside(project.root, body_ref['path']))
    if body.type != 'MESH' or body.animation_data or body.constraints or body.data.shape_keys:
        raise StudioError('Legacy body physics requires the reviewed static body; use the motion executor for animation')
    if body.get('a3d_profile_cache_key') != profile['cache_key']:
        raise StudioError('Live body collider belongs to a different measured fit target')
    from blender.body_target import evaluated_mesh
    geometry, _ = evaluated_mesh(body, bpy.context.evaluated_depsgraph_get(), 1.)
    if digest([geometry['vertices_cm'], geometry['faces']]) != profile['geometry_sha256']:
        raise StudioError('Live body geometry differs from the exact reviewed fit target')
    native, _ = native_origin(project, lambda doc:
        (doc.get('operation') == 'prepare_body_target' and doc.get('result', {}).get('artifacts', {}).get('profile') == body_ref) or
        (doc.get('operation') == 'introduce_body_target' and doc.get('result', {}).get('profile_ref') == body_ref))
    reference = (native['result']['artifacts']['geometry'] if native['operation'] == 'prepare_body_target'
                 else native['result']['geometry_ref'])
    checked_reference(project, reference)
    expected = read_json(inside(project.root, reference['path']))
    if geometry != {key: expected[key] for key in ('vertices_cm', 'faces', 'face_sets')}:
        raise StudioError('Live body skin regions differ from the exact native fit target')
    return {'live_body_geometry_sha256': digest(geometry), 'live_body_checked': True,
            'body_ref': body_ref, 'body_object': body.name}


def require_native_recipe_fit_intent(project, recipe, colliders, payload=None):
    roles = {row['object']: row['role'] for row in recipe['colliders']}
    if any(obj.get('a3d_profile_cache_key') and roles.get(obj.name) != 'mannequin' for obj in colliders):
        raise StudioError('A measured body collider cannot be relabeled as a support or another layer')
    admission = require_recipe_fit_intent(project, recipe)
    if admission['purpose'] != 'GARMENT_CANDIDATE' or 'body_ref' not in admission:
        return admission
    import json
    import zipfile
    from a3d.native_evidence import checked_reference
    checked_reference(project, admission['package_ref'])
    with zipfile.ZipFile(inside(project.root, admission['package_ref']['path'])) as archive:
        source = json.loads(archive.read('garment.json'))
    if (payload is None or payload['package_sha256'] != admission['package_ref']['sha256'] or
            payload['source_garment_sha256'] != digest(source) or
            read_json(inside(project.root, payload['source_garment'])) != source):
        raise StudioError('Native physics source differs from the exact package whose ease was reviewed')
    bodies = [obj for obj in colliders if obj.name == admission['body_collider']]
    if len(bodies) != 1:
        raise StudioError('Reviewed static fit body is absent or duplicated in the evaluated colliders')
    admission.update(require_native_fit_body(project, admission['body_ref'], bodies[0]))
    admission['source_garment_sha256'] = digest(source)
    return admission
