"""Exact measured body introduction inputs, without fitting or envelope admission."""
import copy
import math

from .body_target import target_descriptor
from .core import StudioError, contract, digest, inside, read_json, sha
from .head_surface import head_surface_section
from .shoulder_surface import surface_anchors


def body_context_descriptor(project, context_path):
    """Read the source-bound body context without changing canonical state."""
    path = inside(project.root, context_path); context = contract('body-context', read_json(path))
    receipt_ref = context['body_target_receipt']; receipt_path = inside(project.root, receipt_ref['path'])
    if sha(receipt_path) != receipt_ref['sha256']:
        raise StudioError('Body context target receipt changed')
    receipt = read_json(receipt_path)
    if (receipt.get('cache_key') != digest({k: v for k, v in receipt.items() if k != 'cache_key'}) or
            receipt.get('status') != 'NATIVE_BODY_TARGET_MEASURED' or receipt.get('native_reopened') is not True):
        raise StudioError('Body context requires an exact reopened and measured native body target')
    evidence = [{'path': context_path, 'sha256': sha(path)}, receipt_ref, receipt['artifact'],
                *receipt['artifacts'].values(), *receipt['evidence'].values()]
    for reference in evidence:
        if sha(inside(project.root, reference['path'])) != reference['sha256']:
            raise StudioError('Body context source artifact changed: ' + reference['path'])
    source = target_descriptor(project, receipt['evidence']['selection']['path'], receipt['evidence']['target']['path'])
    if source['evidence'] != receipt['evidence']:
        raise StudioError('Body context original source selection or target changed')
    geometry = read_json(inside(project.root, receipt['artifacts']['geometry']['path']))
    original = read_json(inside(project.root, receipt['artifacts']['source-geometry']['path']))
    profile = read_json(inside(project.root, receipt['artifacts']['profile']['path']))
    options = read_json(inside(project.root, receipt['artifacts']['options']['path']))
    vertices, faces, labels = (geometry.get(k) for k in ('vertices_cm', 'faces', 'face_sets'))
    if (not isinstance(vertices, list) or not vertices or not isinstance(faces, list) or not faces or
            not isinstance(labels, list) or len(labels) != len(faces) or
            any(not isinstance(p, list) or len(p) != 3 or any(type(x) not in (int, float) or not math.isfinite(x) for x in p) for p in vertices) or
            any(not isinstance(f, list) or len(f) < 3 or any(type(i) is not int or not 0 <= i < len(vertices) for i in f) for f in faces) or
            any(type(label) is not int for label in labels)):
        raise StudioError('Body context needs exact finite source vertices, faces and face-region identities')
    if (faces != original.get('faces') or labels != original.get('face_sets') or
            len(vertices) != len(original.get('vertices_cm', [])) or receipt.get('source_face_ids_preserved') is not True or
            profile.get('geometry_sha256') != digest([vertices, faces]) or
            any(profile.get(k) != geometry.get(k) for k in ('source_sha256', 'pose_sha256')) or
            profile.get('options_sha256') != digest(options) or
            profile.get('rig_landmarks_sha256') != digest(geometry.get('rig_landmarks', {})) or
            receipt.get('profile_cache_key') != profile.get('cache_key') or
            any(receipt.get(k) != profile.get(k) for k in ('geometry_sha256', 'pose_sha256'))):
        raise StudioError('Body context geometry, pose, source regions or profile identity changed')
    surface_anchors(profile); head_surface_section(profile)
    return {'context': copy.deepcopy(context), 'context_ref': evidence[0], 'receipt': receipt,
            'artifact': inside(project.root, receipt['artifact']['path']), 'geometry': geometry, 'profile': profile,
            'target': source['target'], 'evidence': evidence,
            'binding_sha256': digest([context, receipt['cache_key'], receipt['artifact'], profile['cache_key']])}
