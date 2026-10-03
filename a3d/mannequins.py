"""Offline, source-bound catalog assets; personal scenes are never packaged."""
import shutil
import uuid
from pathlib import Path

from .core import ROOT, StudioError, atomic_json, inside, read_json, sha


ASSET_IDS = {'body.realistic-male', 'body.realistic-female'}
ALLOWED_FILES = {'realistic-male-v1.blend', 'realistic-female-v1.blend',
                 'realistic-male-rig-v1.blend', 'realistic-female-rig-v1.blend'}


def catalog(root=ROOT):
    root = Path(root).resolve(strict=True)
    directory = root/'assets/mannequins'
    if not directory.exists():
        return {'version': 1, 'status': 'UNAVAILABLE', 'entries': [],
                'additional_choices': ['Importer un mannequin', 'Utiliser le mannequin sélectionné']}
    manifest = read_json(inside(root, 'assets/mannequins/catalog.json'))
    if manifest.get('version') != 1:
        raise StudioError('Unsupported mannequin catalog version')
    entries = manifest.get('entries', [])
    if len(entries) != 2 or {entry.get('id') for entry in entries} != ASSET_IDS:
        raise StudioError('Catalog must identify the two explicitly selected realistic bases')
    filenames = set()
    for entry in entries:
        name = entry.get('file')
        prefix = entry['id'].removeprefix('body.')
        if name not in ALLOWED_FILES or not name.startswith(prefix+'-') or name in filenames:
            raise StudioError('Mannequin file is outside the approved asset allowlist')
        filenames.add(name)
        path = inside(root, 'assets/mannequins/'+name)
        if path.suffix != '.blend' or path.stat().st_size > 10_000_000 or sha(path) != entry.get('sha256'):
            raise StudioError('Catalog mannequin identity, size or file format changed')
        if entry.get('license') != 'CC0-1.0' or not entry.get('source_url') or not entry.get('author'):
            raise StudioError('Catalog mannequin requires explicit CC0 source provenance')
        if entry.get('unit_scale_m') != 1. or not 30 <= entry.get('stature_cm', 0) <= 400:
            raise StudioError('Catalog mannequin dimensions or units are unsupported')
        if (not entry.get('meshes') or any(not isinstance(name, str) or not name for name in entry['meshes'])
                or not isinstance(entry.get('pipeline_ready'), bool)):
            raise StudioError('Catalog mannequin must declare mesh identities and preparation status')
        if entry['pipeline_ready'] and (entry.get('rig_status') != 'QUALIFIED'
                or entry.get('pose_status') != 'QUALIFIED' or entry.get('collision_envelope') != 'QUALIFIED'
                or entry.get('anatomical_review') != 'APPROVED'):
            raise StudioError('Catalog readiness needs separate rig, pose, anatomy and envelope qualification')
        adapter = inside(root, 'assets/mannequins/'+entry['anatomy_adapter'])
        if sha(adapter) != entry.get('anatomy_adapter_sha256'):
            raise StudioError('Catalog anatomical adapter changed')
    notice = inside(root, 'assets/mannequins/NOTICE-CC0.md')
    if sha(notice) != manifest.get('license_notice_sha256'):
        raise StudioError('Catalog license notice changed')
    return manifest


def distribution_files(root=ROOT):
    manifest = catalog(root)
    if manifest['status'] == 'UNAVAILABLE':
        return []
    return [inside(root, 'assets/mannequins/'+entry['file']) for entry in manifest['entries']]


def select_catalog_body(project, asset_id):
    """Copy into the project, preserving the immutable original and old choices.

    A selected candidate can be inspected while not ready. No collision, anatomy
    or fitting admission follows merely from selecting its catalog label.
    """
    manifest = catalog()
    matches = [entry for entry in manifest['entries'] if entry['id'] == asset_id]
    if len(matches) != 1:
        raise StudioError('Unknown catalog mannequin')
    entry = matches[0]
    token = uuid.uuid4().hex
    directory = inside(project.root, 'sources/mannequins/'+token, False)
    directory.mkdir(parents=True, exist_ok=False)
    source = inside(ROOT, 'assets/mannequins/'+entry['file'])
    target = directory/'body.blend'
    shutil.copy2(source, target)
    if sha(target) != entry['sha256'] or sha(source) != entry['sha256']:
        raise StudioError('Catalog source changed during project copy')
    descriptor = {'version': 1, 'source_blend': target.relative_to(project.root).as_posix(),
                  'source_sha256': entry['sha256'], 'source_ref': asset_id+' version '+str(entry['version'])+'; '+entry['source_url'],
                  'frame': 1, 'unit_scale_m': entry['unit_scale_m'], 'meshes': entry['meshes'],
                  'dependencies': entry['dependencies'], 'reference_object': 'A3D.BodyReference'}
    path = directory/'selection.json'
    atomic_json(path, descriptor)
    adapter = read_json(inside(ROOT, 'assets/mannequins/'+entry['anatomy_adapter']))
    adapter['source_ref'] = {'path': descriptor['source_blend'], 'sha256': entry['sha256']}
    adapter_path = directory/'anatomy-adapter.json'
    atomic_json(adapter_path, adapter)
    return {'status': 'BODY_SELECTED_NOT_EVALUATED', 'catalog_id': asset_id,
            'selection': {'path': path.relative_to(project.root).as_posix(), 'sha256': sha(path)},
            'source': {'path': descriptor['source_blend'], 'sha256': entry['sha256']},
            'anatomy_adapter': {'path': adapter_path.relative_to(project.root).as_posix(), 'sha256': sha(adapter_path)},
            'pipeline_ready': entry['pipeline_ready'], 'qualification': 'NONE',
            'next': 'Inspect the selected native source and prepare a body reference; selection does not create collisions or accept fitting.'}
