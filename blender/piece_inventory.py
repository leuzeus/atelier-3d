"""Read actual scene topology and immutable source maps; never count objects."""
import copy
import uuid
from pathlib import Path

from a3d.core import StudioError, atomic_json, digest, inside, now, read_json, sha
from a3d.piece_inventory import expected_inventory, face_piece_ids, mapped_pieces, reconcile, require_complete, write_review


def remember_candidate(project, component_id, obj):
    path = project.data/'blender/piece-candidates.json'
    registry = read_json(path) if path.is_file() else {}
    registry[component_id] = ({'object': obj.name, 'map_sha256': obj.get('a3d_sewing_mesh_sha256')}
                              if obj else {'object': None, 'map_sha256': None})
    atomic_json(path, registry)


def collect(project, component_id=None, focus=None, previews=False):
    import bpy
    from blender.sewing import mesh_digest
    try:
        expected = expected_inventory(project)
    except (StudioError, OSError, KeyError) as exc:
        return {'schema_version': 1, 'scope': {'kind': 'global', 'component_id': None},
                'global': {'status': 'NON_VERIFIABLE', 'expected': None, 'present': None, 'missing': [],
                           'duplicates': [], 'unknown': [{'reason': str(exc)}]}, 'components': {},
                'summary': 'Complétude non vérifiable : ' + str(exc), 'candidate_mode': 'preview' if previews else 'active',
                'dependencies': [], 'is_dirty': bool(bpy.data.is_dirty),
                'qualification': 'NOT_VERIFIED', 'observations': []}
    session_path = project.data/'blender/session.json'
    session = read_json(session_path)
    registry_path = project.data/'blender/piece-candidates.json'
    registry = read_json(registry_path) if previews and registry_path.is_file() else {}
    if focus is not None:
        registry[component_id] = {'object': focus.name, 'map_sha256': focus.get('a3d_sewing_mesh_sha256')}
    observations, errors, excluded = [], [], []
    dependencies = [{'path': session_path.relative_to(project.root).as_posix(), 'sha256': sha(session_path)}]
    if previews and registry_path.is_file():
        dependencies.append({'path': registry_path.relative_to(project.root).as_posix(), 'sha256': sha(registry_path)})
    scene_records, rigid_presence = [], []
    for obj in bpy.context.scene.objects:
        if obj.type != 'MESH': continue
        cid = obj.get('a3d_component_id') or obj.get('a3d_source_component_id')
        if not cid: continue
        role = obj.get('a3d_role')
        if cid not in expected['components']: continue
        if expected['components'][cid]['kind'] != 'textile':
            rigid_presence.append({'component_id': cid, 'object': obj.name,
                                   'visible_in_view_layer': bool(obj.visible_get()),
                                   'provenance': 'NOT_VERIFIED', 'qualification': 'NOT_INFERRED'})
            continue
        scene_records.append({'object': obj.name, 'component_id': cid, 'role': role,
                              'mesh_sha256': mesh_digest(obj), 'map_sha256': obj.get('a3d_sewing_mesh_sha256'),
                              'visible': bool(obj.visible_get()), 'hide_render': bool(obj.hide_render)})
        current = registry.get(cid)
        if current is not None:
            selected = (current['object'] is not None and obj.get('a3d_sewing_mesh_sha256') == current['map_sha256']
                        and role in ('simulation', 'render', 'preparation-candidate'))
        else:
            selected = (role in ('simulation', 'render')
                        or (previews and role == 'preparation-candidate')
                        or (role is None and obj.get('a3d_component_id')))
        if not selected:
            excluded.append({'object': obj.name, 'component_id': cid, 'role': role}); continue
        item = {'component_id': cid, 'object': obj.name, 'package_sha256': obj.get('a3d_package_sha256'),
                'pieces': [], 'source_sha256': None, 'mesh_sha256': mesh_digest(obj),
                'visible': bool(obj.visible_get()), 'render_enabled': not obj.hide_render,
                'readiness': obj.get('a3d_pattern_preparation_readiness', 'NOT_INFERRED')}
        try:
            info = expected['components'][cid]
            if item['package_sha256'] != info['package']['sha256']: raise StudioError('Package provenance changed')
            if session.get('construction_id') and obj.get('a3d_construction_id') != session['construction_id']:
                raise StudioError('Candidate belongs to another construction')
            path = inside(project.root, obj.get('a3d_sewing_mesh', ''))
            ref = {'path': path.relative_to(project.root).as_posix(), 'sha256': sha(path)}
            if ref['sha256'] != obj.get('a3d_sewing_mesh_sha256'): raise StudioError('Source map changed')
            payload = read_json(path)
            if payload['component_id'] != cid or payload['package_sha256'] != item['package_sha256']:
                raise StudioError('Source map identity differs from the object')
            item['source_sha256'] = payload['source_garment_sha256']
            item['pieces'] = mapped_pieces(payload, [list(f.vertices) for f in obj.data.polygons], len(obj.data.vertices))
            item['correspondence'] = ref; dependencies.append(ref)
        except (StudioError, OSError, KeyError, TypeError) as exc:
            item['error'] = str(exc)
        observations.append(item)
    report = reconcile(expected, observations, component_id, errors)
    report.update(observed_at=now(), project_revision=project.state()['revision'],
                  candidate_mode='preview' if previews else 'active', scene_sha256=digest(scene_records),
                  scene_objects=scene_records, excluded_objects=excluded, collection_errors=errors,
                  dependencies=dependencies, is_dirty=bool(bpy.data.is_dirty),
                  capture_visibility='NOT_VERIFIED', rigid_scene_presence=rigid_presence)
    return report


def save_report(project, report, directory=None, images=()):
    session = read_json(project.data/'blender/session.json')
    working = Path(session['working']).resolve()
    if not working.is_relative_to(project.data/'blender'): raise StudioError('Completeness scene is outside managed Blender storage')
    report['artifact'] = {'path': working.relative_to(project.root).as_posix(), 'sha256': sha(working)}
    directory = directory or project.data/('blender/piece-inventory/inspection-'+uuid.uuid4().hex)
    review = write_review(project, report, directory/'review.html', images)
    report['review'] = review
    atomic_json(directory/'completeness.json', report)
    # Dirty observations are useful diagnostics, never current saved-scene proofs.
    projection = {**report, 'proof_path': (directory/'completeness.json').relative_to(project.root).as_posix()}
    atomic_json(project.data/'blender/piece-completeness.json', projection)
    if report['candidate_mode'] == 'active':
        atomic_json(project.data/'blender/piece-active-proof.json', projection)
    return report


def require_live(project, component_id=None):
    report = collect(project, component_id)
    require_complete(report, component_id)
    return report


def bind_frozen_map(project, result, payload, faces, coords, mapping=None):
    """Preserve face/source identities after an explicit weld or continuous copy."""
    source_faces = payload['faces']
    labels = face_piece_ids(payload, source_faces, len(payload['rest_cm']))
    frozen = copy.deepcopy(payload)
    frozen.update(faces=faces, rest_cm=[[v*100 for v in p] for p in coords],
                  placed_cm=[[v*100 for v in p] for p in coords], source_face_pieces=labels,
                  inventory_map_kind='FROZEN_SOURCE_FACE_IDENTITIES')
    if len(faces) != len(source_faces): raise StudioError('Freeze lost source faces')
    if mapping:
        for panel in frozen['panels'].values():
            panel['indices'] = sorted({mapping[i] for i in panel['indices']})
    path = project.data/('blender/piece-inventory/frozen-map-'+uuid.uuid4().hex+'.json')
    atomic_json(path, frozen)
    result['a3d_sewing_mesh'] = path.relative_to(project.root).as_posix()
    result['a3d_sewing_mesh_sha256'] = sha(path)
    if payload.get('construction_id'): result['a3d_construction_id'] = payload['construction_id']
