"""Recognize the narrow 0.4 panel layout for archival, never for simulation."""
import json
import sqlite3
from contextlib import closing

from a3d.core import StudioError, digest, inside, read_json, sha


def legacy_snapshot(obj):
    """Bind archival to base geometry, transform, weights and saved rest shapes.

    This is an identity check, not topology validation or evaluated Cloth proof.
    The full pre-operation .blend checkpoint also preserves modifiers/materials.
    """
    mesh = obj.data
    return digest({'name': obj.name, 'mesh': mesh.name,
        'vertices': [list(v.co) for v in mesh.vertices],
        'edges': [list(e.vertices) for e in mesh.edges],
        'faces': [list(p.vertices) for p in mesh.polygons],
        'matrix': [list(row) for row in obj.matrix_world],
        'weights': [[(g.group, g.weight) for g in v.groups] for v in mesh.vertices],
        'groups': [g.name for g in obj.vertex_groups],
        'shapes': {key.name: [list(v.co) for v in key.data]
                   for key in mesh.shape_keys.key_blocks} if mesh.shape_keys else {}})


def verify_checkpoint(project, receipt):
    saved = receipt.get('checkpoint', {})
    try:
        path = inside(project.root, saved.get('path', ''))
        valid = path.is_relative_to(project.data / 'checkpoints') and path.suffix == '.blend' and sha(path) == saved.get('sha256')
    except (OSError, AttributeError, TypeError):
        valid = False
    if not valid:
        raise StudioError('Legacy panel checkpoint is missing or changed')
    return path


def has_legacy_identity(obj, component_id, package_sha256):
    return (obj.type == 'MESH' and obj.get('a3d_component_id') == component_id
            and obj.get('a3d_package_sha256') == package_sha256
            and not any(key in obj for key in ('a3d_role', 'a3d_sewing_mesh', 'a3d_sewing_mesh_sha256')))


def topology_matches(obj, topology):
    count, faces, edges, _ = topology
    return (len(obj.data.vertices) == count
            and [tuple(p.vertices) for p in obj.data.polygons] == faces
            and {tuple(sorted(e.vertices)) for e in obj.data.edges} == edges
            and len(obj.data.edges) == len(edges))


def all_data_ids():
    import bpy
    return {item for prop in bpy.data.bl_rna.properties if prop.type == 'COLLECTION'
            for item in getattr(bpy.data, prop.identifier) if isinstance(item, bpy.types.ID)}


def read_checkpoint_object(path, object_name, data, package_sha256):
    """Read an unlinked historical object; never switch the current scene/file."""
    import bpy
    before = all_data_ids()
    try:
        with bpy.data.libraries.load(str(path), link=False) as (available, loaded):
            if object_name not in available.objects:
                raise StudioError('Historical checkpoint does not contain the requested legacy object')
            loaded.objects = [object_name]
        obj = loaded.objects[0]
        if not has_legacy_identity(obj, data['component_id'], package_sha256):
            raise StudioError('Historical checkpoint object has a foreign component/package or versioned role')
        if not topology_matches(obj, legacy_topology(data)):
            raise StudioError('Historical checkpoint object is not the original package panel topology')
        mesh = obj.data
        # Do not use matrix_world on an unlinked library object as evaluated proof.
        geometry_sha256 = digest({'vertices_m': [list(v.co) for v in mesh.vertices],
                                  'faces': [list(p.vertices) for p in mesh.polygons],
                                  'edges': [list(e.vertices) for e in mesh.edges]})
        return {'object': object_name, 'component_id': data['component_id'],
                'package_sha256': package_sha256, 'vertices': len(mesh.vertices),
                'polygons': len(mesh.polygons), 'edges': len(mesh.edges),
                'geometry_sha256': geometry_sha256, 'source_topology_matches': True}
    finally:
        added = all_data_ids() - before
        if added:
            bpy.data.batch_remove(ids=added)


def recorded_checkpoint(project, checkpoint, operation):
    """Require the checkpoint to occur in the canonical guarded operation journal."""
    database = inside(project.root, '.a3d/state.sqlite3')
    with closing(sqlite3.connect(database.as_uri() + '?mode=ro', uri=True)) as connection:
        rows = connection.execute("SELECT id,kind,doc FROM events WHERE kind IN ('blender_started','blender_finished') ORDER BY id")
        for event_id, kind, encoded in rows:
            detail = json.loads(encoded)
            saved = detail.get('checkpoint', {})
            if (detail.get('operation') == operation and saved.get('path') == checkpoint['path']
                    and saved.get('sha256') == checkpoint['sha256']):
                return {'id': event_id, 'kind': kind, 'operation': operation, 'detail_sha256': digest(detail)}
    raise StudioError('Historical checkpoint is not recorded by a guarded operation in the project journal')


def checkpoint_import_proof(project, object_name, data, package_sha256, receipt_path):
    """Recover observed import evidence from an existing guarded global checkpoint.

    The receipt can belong to another component. It proves only the checkpoint;
    identity/topology of the requested component are checked in the .blend itself.
    """
    try:
        path = inside(project.root, receipt_path)
    except OSError as error:
        raise StudioError('Historical checkpoint receipt is missing') from error
    if path.parent != project.data / 'blender' or (path.name != 'garment-receipt.json'
            and not (path.name.startswith('script-') and path.suffix == '.json')):
        raise StudioError('Recovery requires an existing guarded garment/script checkpoint receipt')
    receipt_sha256 = sha(path)
    receipt = read_json(path)
    if path.name == 'garment-receipt.json':
        if not isinstance(receipt.get('object'), str) or not isinstance(receipt.get('vertices'), int):
            raise StudioError('Historical garment checkpoint receipt is malformed')
    else:
        script = inside(project.root, receipt.get('script', ''))
        if (receipt.get('operation') not in ('simulate', 'refine', 'behavior', 'validate', 'export')
                or not receipt.get('component_ids') or script.suffix != '.py'
                or sha(script) != receipt.get('sha256')):
            raise StudioError('Historical guarded script receipt or script has changed')
    saved = verify_checkpoint(project, receipt)
    event = recorded_checkpoint(project, receipt['checkpoint'], 'garment' if path.name == 'garment-receipt.json' else 'run_script')
    observed = read_checkpoint_object(saved, object_name, data, package_sha256)
    if sha(saved) != receipt['checkpoint']['sha256'] or sha(path) != receipt_sha256:
        raise StudioError('Historical checkpoint changed during inspection')
    return {'kind': 'guarded-checkpoint-object', 'checkpoint': receipt['checkpoint'],
            'canonical_event': event,
            'checkpoint_receipt': {'path': path.relative_to(project.root).as_posix(), 'sha256': receipt_sha256},
            'observed': observed, 'legacy_validity': 'NOT_VALIDATED'}


def legacy_topology(data):
    offsets, faces, count = {}, [], 0
    for pid, panel in data['pieces'].items():
        offsets[pid] = count
        faces.extend(tuple(count + i for i in face) for face in panel['faces'])
        count += len(panel['vertices'])
    seams = []
    for seam in data['seams']:
        a = data['pieces'][seam['piece_a']]['edges'][seam['edge_a']]
        b = data['pieces'][seam['piece_b']]['edges'][seam['edge_b']]
        if seam['orientation'] == 'reverse':
            b = list(reversed(b))
        if len(a) != len(b):
            raise StudioError('Legacy layout requires the original equal-count seam edges')
        seams.extend(tuple(sorted((offsets[seam['piece_a']] + x, offsets[seam['piece_b']] + y))) for x, y in zip(a, b))
    edges = set(seams)
    for face in faces:
        edges.update(tuple(sorted((face[i], face[(i + 1) % len(face)]))) for i in range(len(face)))
    return count, faces, edges, len(seams)


def validate_legacy_panels(project, obj, data, package_sha256, snapshot_sha256=None, script_receipts=None,
                           checkpoint_receipt=None):
    if not has_legacy_identity(obj, data['component_id'], package_sha256):
        raise StudioError('Legacy panel identity is missing, foreign or already versioned')
    count, faces, edges, seams = legacy_topology(data)
    current_topology_matches = topology_matches(obj, (count, faces, edges, seams))
    if not current_topology_matches and snapshot_sha256 is None:
        raise StudioError('Legacy panel topology does not match the approved source package')
    receipt, recovered = None, None
    if checkpoint_receipt is not None:
        recovered = checkpoint_import_proof(project, obj.name, data, package_sha256, checkpoint_receipt)
    else:
        receipt = read_json(inside(project.root, '.a3d/blender/garment-receipt.json'))
        if receipt.get('object') != obj.name or receipt.get('vertices') != count or receipt.get('sewing_edges') != seams:
            raise StudioError('Legacy panel receipt does not identify this mesh; verify_legacy_import can recover from a guarded global checkpoint')
        verify_checkpoint(project, receipt)
    history = []
    if snapshot_sha256 is not None:
        if legacy_snapshot(obj) != snapshot_sha256:
            raise StudioError('Legacy mesh changed since inspect; request a fresh snapshot')
        if not script_receipts:
            raise StudioError('Legacy modified mesh requires explicit script receipts')
        for relative in script_receipts:
            path = inside(project.root, relative)
            if path.parent != project.data / 'blender' or not path.name.startswith('script-') or path.suffix != '.json':
                raise StudioError('Legacy history must use guarded script receipts')
            record = read_json(path)
            script = inside(project.root, record.get('script', ''))
            if (record.get('operation') != 'simulate' or data['component_id'] not in record.get('component_ids', [])
                    or script.suffix != '.py' or sha(script) != record.get('sha256')):
                raise StudioError('Legacy script receipt or source is missing, foreign or changed')
            verify_checkpoint(project, record)
            history.append({'path': relative, 'sha256': sha(path)})
    # Coordinates and modifiers may be dirty. They are preserved in the archive;
    # only a freshly derived object gets a sewing map and simulation role.
    return {'source_topology_matches': current_topology_matches, 'script_receipts': history, 'import_receipt': receipt,
            'checkpoint_import_proof': recovered,
            'snapshot_sha256': snapshot_sha256, 'legacy_validity': 'NOT_VALIDATED'}
