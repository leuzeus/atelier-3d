"""Append-only garment operation receipts, bound to a component and package."""
import uuid

from .core import canonical, ident, inside, now, sha


def write_receipt(project, component_id, package_sha256, result):
    ident(component_id)
    path = inside(project.root, '.a3d/blender/garment-receipts/' + component_id +
                  '/receipt-' + uuid.uuid4().hex + '.json', False)
    path.parent.mkdir(parents=True, exist_ok=True)
    record = {'schema_version': 1, 'operation': 'garment', 'component_id': component_id,
              'package_sha256': package_sha256, 'created_at': now(), 'result': result}
    # An existing proof is never replaced, including in the unlikely UUID clash.
    with path.open('xb') as stream:
        stream.write(canonical(record) + b'\n')
    return {'path': path.relative_to(project.root).as_posix(), 'sha256': sha(path)}
