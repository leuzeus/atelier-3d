"""Source-bound review and export profiles; technical execution is not art approval."""
from .core import StudioError, contract, inside, read_json, sha


def delivery_profile(project, path):
    profile = contract('delivery-profile', read_json(inside(project.root, path)))
    source = inside(project.root, profile['source_ref']['path'])
    if sha(source) != profile['source_ref']['sha256']:
        raise StudioError('Delivery candidate source changed')
    if source.suffix.lower() != '.blend':
        raise StudioError('Current delivery profile requires a native Blender candidate')
    if len(set(profile['object_names'])) != len(profile['object_names']):
        raise StudioError('Delivery object identities must be unique')
    return profile, source


def verify_delivery_manifest(project, manifest):
    # A client-supplied reimport flag or list of clip names does not establish
    # native execution. Reuse the exporter proof verifier and its measured,
    # canonical native result instead of granting a second admission route.
    from .export_profiles import verify_export_manifest
    verified = verify_export_manifest(project, manifest)
    return {'status': 'DELIVERY_FILES_VERIFIED', 'artistic_review': 'STILL_REQUIRED',
            'animation_qualification': verified['animation_qualification'],
            'candidate': verified['candidate'], 'native_transport': verified['status']}
