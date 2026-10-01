"""Recognize the narrow 0.4 panel layout for archival, never for simulation."""
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
    path = inside(project.root, saved.get('path', ''))
    if not path.is_relative_to(project.data / 'checkpoints') or path.suffix != '.blend' or sha(path) != saved.get('sha256'):
        raise StudioError('Legacy panel checkpoint is missing or changed')


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


def validate_legacy_panels(project, obj, data, package_sha256, snapshot_sha256=None, script_receipts=None):
    if (obj.type != 'MESH' or obj.get('a3d_component_id') != data['component_id']
            or obj.get('a3d_package_sha256') != package_sha256
            or any(key in obj for key in ('a3d_role', 'a3d_sewing_mesh', 'a3d_sewing_mesh_sha256'))):
        raise StudioError('Legacy panel identity is missing, foreign or already versioned')
    count, faces, edges, seams = legacy_topology(data)
    topology_matches = (len(obj.data.vertices) == count
            and [tuple(p.vertices) for p in obj.data.polygons] == faces
            and {tuple(sorted(e.vertices)) for e in obj.data.edges} == edges
            and len(obj.data.edges) == len(edges))
    if not topology_matches and snapshot_sha256 is None:
        raise StudioError('Legacy panel topology does not match the approved source package')
    receipt = read_json(inside(project.root, '.a3d/blender/garment-receipt.json'))
    if receipt.get('object') != obj.name or receipt.get('vertices') != count or receipt.get('sewing_edges') != seams:
        raise StudioError('Legacy panel receipt does not identify this mesh')
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
    return {'source_topology_matches': topology_matches, 'script_receipts': history, 'import_receipt': receipt,
            'snapshot_sha256': snapshot_sha256, 'legacy_validity': 'NOT_VALIDATED'}
