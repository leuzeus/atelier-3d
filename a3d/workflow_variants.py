"""Project-owned, immutable parameter variants of reviewed Comfy templates."""
import copy
import uuid
from .core import ROOT, StudioError, atomic_json, digest, ident, inside, now, read_json, sha


def template_identity(template_id):
    registry = ROOT / 'workflows/comfy/registry.json'
    specs = read_json(registry)['workflows']
    if template_id not in specs:
        raise StudioError('Variants require a registered reviewed template')
    spec = copy.deepcopy(specs[template_id])
    graph = inside(ROOT / 'workflows/comfy', spec['file'])
    return spec, {'registry_sha256': sha(registry), 'template_sha256': sha(graph)}


def load_variant(project, variant_id):
    ident(variant_id)
    ref = project.state().get('workflow_variants', {}).get(variant_id)
    if not ref:
        raise StudioError('Unknown project workflow variant')
    path = inside(project.root, ref['path'])
    if sha(path) != ref['sha256']:
        raise StudioError('Workflow variant receipt changed')
    record = read_json(path)
    spec, identity = template_identity(record['template_id'])
    if identity != record['template_identity'] or spec != record['specification']:
        raise StudioError('Workflow template changed; prepare and validate a new variant')
    graph_path = inside(project.root, record['graph']['path'])
    graph = read_json(graph_path)
    if sha(graph_path) != record['graph']['sha256'] or digest(graph) != record['graph_digest']:
        raise StudioError('Workflow variant graph changed')
    return spec, graph, record


def prepare_variant(project, client, template_id, variant_id, parameters):
    ident(variant_id)
    if variant_id in read_json(ROOT/'workflows/comfy/registry.json')['workflows']:
        raise StudioError('Variant id collides with registered template')
    spec, identity = template_identity(template_id)
    spec, graph = client.template(template_id, parameters)
    fingerprint = digest({'template': template_id, 'identity': identity,
                          'parameters': parameters, 'graph': graph, 'endpoint': client.base})
    if variant_id in project.state().get('workflow_variants', {}):
        _, _, previous = load_variant(project, variant_id)
        if previous['fingerprint'] != fingerprint:
            raise StudioError('Immutable workflow variant id reused with different inputs')
        return previous
    base_graph = read_json(inside(ROOT/'workflows/comfy', spec['file']))
    changes = []
    for node in sorted(graph):
        for field in sorted(graph[node]['inputs']):
            before, after = base_graph[node]['inputs'][field], graph[node]['inputs'][field]
            if before != after:
                changes.append({'node': node, 'input': field, 'before': before, 'after': after})
    folder = inside(project.root, '.a3d/workflows/'+variant_id+'/'+uuid.uuid4().hex, False)
    folder.mkdir(parents=True, exist_ok=False)
    graph_path = folder/'workflow.api.json'
    atomic_json(graph_path, graph)
    with client.factory(client.config, project.root) as native:
        report = native.call('validate_workflow', {'workflow_path': str(graph_path)})
    record = {'version': 1, 'variant_id': variant_id, 'template_id': template_id,
              'template_identity': identity, 'specification': spec,
              'fingerprint': fingerprint, 'graph_digest': digest(graph),
              'graph': {'path': graph_path.relative_to(project.root).as_posix(), 'sha256': sha(graph_path)},
              'parameters': copy.deepcopy(parameters), 'diff': changes,
              'endpoint': client.base, 'compatibility': report,
              'status': 'COMPATIBLE' if report.get('valid') is True else 'INCOMPATIBLE',
              'created_at': now(), 'submission': 'NOT_EXECUTED', 'admission': 'STILL_REQUIRED'}
    path = folder/'receipt.json'
    atomic_json(path, record)
    with project.transaction() as db:
        state = project.state(db)
        if variant_id in state.get('workflow_variants', {}):
            raise StudioError('Workflow variant concurrently created')
        state.setdefault('workflow_variants', {})[variant_id] = {
            'path': path.relative_to(project.root).as_posix(), 'sha256': sha(path)}
        project.save(db, state, 'workflow_variant_prepared', {'variant_id': variant_id, 'fingerprint': fingerprint})
    return record
