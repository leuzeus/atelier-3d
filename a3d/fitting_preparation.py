"""Explicit auxiliary-envelope and common-pose inputs, bound to native receipts."""
from .core import StudioError,contract,inside,read_json,sha

def body_receipt(project,ref):
    path=inside(project.root,ref['path'])
    if sha(path)!=ref['sha256']:raise StudioError('Body reference receipt changed')
    value=read_json(path)
    if not all(k in value for k in ('artifact','geometry_sha256','meshes','bones','reference_object','source_sha256','frame')):
        raise StudioError('Expected a native body reference receipt')
    artifact=inside(project.root,value['artifact']['path'])
    if sha(artifact)!=value['artifact']['sha256']:raise StudioError('Body reference artifact changed')
    return value,artifact

def envelope_spec(project,path):
    spec=contract('fitting-envelope',read_json(inside(project.root,path)))
    body,artifact=body_receipt(project,spec['body_receipt'])
    named={r['object'] for r in body['meshes']};used=set();ids=set()
    for region in spec['regions']:
        if region['id'] in ids or not set(region['source_meshes'])<=named or set(region['source_meshes'])&used:
            raise StudioError('Envelope regions require unique IDs and disjoint existing source meshes')
        ids.add(region['id']);used.update(region['source_meshes'])
        for ref in region['partition_bones']:
            if ref['bone'] not in body['bones'].get(ref['rig'],{}):raise StudioError('Envelope partition requires an evaluated source bone')
    if used!=named:raise StudioError('Envelope regions must account for every selected body mesh')
    if spec['object']==body['reference_object']:raise StudioError('Auxiliary envelope cannot replace the target body')
    return spec,body,artifact

def pose_spec(project,path):
    spec=contract('fitting-pose',read_json(inside(project.root,path)))
    body,_=body_receipt(project,spec['body_receipt'])
    if len({f['id'] for f in spec['frames']})!=len(spec['frames']):raise StudioError('Common pose frame IDs must be unique')
    for f in spec['frames']:
        for ref in (f['target_origin'],f['target_axis']):
            if ref['bone'] not in body['bones'].get(ref['rig'],{}):raise StudioError('Common pose requires evaluated target bones')
    return spec,body
