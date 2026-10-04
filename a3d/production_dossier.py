"""Compile approved structured sources without interpreting prose as geometry.

The construction board documents the cut; packages own named edges and seam
partners. A separate, reviewed specification owns semantic roles and spatial
order. Missing declarations are diagnostics, never guessed from IDs or labels.
The pure compiler does not grant native execution, construction or fitting
admission. ``compile_project_dossier`` additionally checks on-disk provenance.
"""
import copy
import json
import math
import zipfile

from .core import StudioError, contract, digest, inside, read_json, sha
from .dressing import _reference
from .garment_planner import plan_assembly


def _sorted_dossier(dossier):
    result = copy.deepcopy(dossier)
    for component in result.get('components', {}).values():
        component['pieces'] = sorted(component.get('pieces', []), key=lambda p: p['id'])
        for piece in component['pieces']:
            pattern = piece.get('pattern', {})
            for field in ('assembly_marks', 'folds'):
                if field in pattern:
                    pattern[field] = sorted(pattern[field], key=digest)
            if 'source_evidence_keys' in piece:
                piece['source_evidence_keys'].sort()
    if 'source_references' in result:
        result['source_references'] = sorted(result['source_references'], key=digest)
    return result


def compile_production_dossier(dossier, packages, spec=None):
    """Return complete inventories and an assembly spec only when explicit.

    ``packages`` maps component IDs to ``{source_ref, data}``. Pure callers
    supply trusted package data; the project wrapper verifies archive hashes
    and runs the existing package validator. ``spec`` follows production-dossier.
    No image interpretation, named-piece heuristic or construction rewrite occurs.
    """
    if not isinstance(dossier, dict) or dossier.get('units') != 'cm' or not isinstance(dossier.get('components'), dict):
        raise StudioError('Production compilation requires a centimetre construction dossier')
    if spec is not None:
        contract('production-dossier', spec)
        _reference(spec['source_ref'])
        _reference(spec['body_ref'])
    original = digest([dossier, packages, spec])
    diagnostics = []

    def missing(code, **where):
        diagnostics.append({'code': code, 'category': 'missing_metadata', **where})

    declared = {} if spec is None else spec.get('piece_semantics', {})
    source_ref = None if spec is None else spec['source_ref']
    textiles = {}; rigid = []; components = []; links = []; piece_ids = set()
    for component_id, component in sorted(_sorted_dossier(dossier)['components'].items()):
        pipeline = component.get('pipeline')
        if pipeline not in ('PATTERN_SEWN', 'MULTIVIEW_PART'):
            raise StudioError('Unknown explicit component pipeline: '+component_id)
        pieces = component.get('pieces', [])
        if not isinstance(pieces, list) or any(not isinstance(p, dict) or not p.get('id') for p in pieces):
            raise StudioError('Construction pieces require explicit stable IDs')
        for piece in pieces:
            if piece['id'] in piece_ids:
                raise StudioError('Duplicate source piece ID: '+piece['id'])
            piece_ids.add(piece['id'])
        if pipeline == 'MULTIVIEW_PART':
            rigid.extend({'id': p['id'], 'component_id': component_id,
                          'pipeline': pipeline, 'source': copy.deepcopy(p)} for p in pieces)
            components.append({'id': component_id, 'pipeline': pipeline, 'pieces': sorted(p['id'] for p in pieces)})
            continue
        package = packages.get(component_id)
        if package is None:
            missing('PACKAGE_MISSING', component_id=component_id)
            data = None
        else:
            if set(package) != {'source_ref', 'data'}:
                raise StudioError('Compiler package needs source_ref and immutable data')
            _reference(package['source_ref'])
            data = contract('garment', package['data'])
            if data['component_id'] != component_id:
                raise StudioError('Package component identity differs from dossier')
            if set(data['pieces']) != {p['id'] for p in pieces}:
                raise StudioError('Package source pieces differ from approved dossier inventory: '+component_id)
        components.append({'id': component_id, 'pipeline': pipeline, 'pieces': sorted(p['id'] for p in pieces),
                           'package_source_ref': None if package is None else copy.deepcopy(package['source_ref'])})
        for piece in sorted(pieces, key=lambda p: p['id']):
            pid = piece['id']; pattern = piece.get('pattern', {})
            if pattern.get('cut_quantity') != 1:
                missing('EXPLICIT_CUT_INVENTORY_REQUIRED', piece=pid)
            grain = piece.get('grain_direction')
            if (not isinstance(grain, list) or len(grain) != 2 or
                    any(type(v) not in (float, int) or not math.isfinite(v) for v in grain) or
                    sum(v*v for v in grain) == 0):
                missing('GRAIN_DIRECTION_MISSING', piece=pid)
            actual = None if data is None else data['pieces'][pid]
            semantic = copy.deepcopy(declared.get(pid, {}))
            for field in ('role', 'side', 'layer'):
                if field not in semantic:
                    missing('PIECE_'+field.upper()+'_MISSING', piece=pid)
            if 'longitudinal_uv_axis' not in semantic and grain in ([0, 1], [0, -1], [1, 0], [-1, 0]):
                semantic['longitudinal_uv_axis'] = 'v' if grain[0] == 0 else 'u'
            if actual is not None:
                for edge in semantic.get('guide_edges', {}).values():
                    if edge not in actual['edges']:
                        raise StudioError('Semantic guide references missing source edge: '+pid+' / '+edge)
            textiles[pid] = {'id': pid, 'component_id': component_id, 'pipeline': pipeline,
                'semantics': semantic, 'source': copy.deepcopy(piece),
                'source_geometry': copy.deepcopy(actual),
                'package_source_ref': None if package is None else copy.deepcopy(package['source_ref']),
                'grain_direction': copy.deepcopy(grain),
                'assembly_marks': sorted(copy.deepcopy(pattern.get('assembly_marks', [])), key=digest)}
        if data is not None:
            seam_ids = set(); permanent_edges = {}
            for seam in sorted(data['seams'], key=lambda row: row['id']):
                if seam['id'] in seam_ids:
                    raise StudioError('Duplicate package seam ID: '+seam['id'])
                seam_ids.add(seam['id'])
                if 'kind' not in seam:
                    missing('SOURCE_LINK_KIND_MISSING', component_id=component_id, link=seam['id'])
                for side in ('a', 'b'):
                    pid, edge = seam['piece_'+side], seam['edge_'+side]
                    if pid not in data['pieces'] or edge not in data['pieces'][pid]['edges']:
                        raise StudioError('Source seam references missing named edge: '+seam['id'])
                    if seam.get('kind') == 'permanent':
                        if (pid, edge) in permanent_edges:
                            raise StudioError('Two permanent source seams own the same named edge: '+pid+' / '+edge)
                        permanent_edges[(pid, edge)] = seam['id']
                links.append({**copy.deepcopy(seam), 'id': component_id+'::'+seam['id'],
                              'source_link_id': seam['id'], 'component_id': component_id,
                              'source_ref': copy.deepcopy(package['source_ref'])})
            for piece in pieces:
                for mark in piece.get('pattern', {}).get('assembly_marks', []):
                    candidates = [s for s in data['seams'] if s['id'] == mark.get('seam_id') and
                                  piece['id'] in (s['piece_a'], s['piece_b'])]
                    if len(candidates) != 1:
                        raise StudioError('Assembly mark lacks its exact source seam: '+piece['id'])
                    if type(mark.get('position')) not in (int, float) or not 0 <= mark['position'] <= 1:
                        raise StudioError('Assembly mark needs a bounded source arc position')
    if set(packages)-{c['id'] for c in components if c['pipeline'] == 'PATTERN_SEWN'}:
        raise StudioError('Compiler received an undeclared textile package')
    if set(declared)-set(textiles):
        raise StudioError('Semantic specification references an undeclared textile source piece')
    if spec is not None:
        supplied = {p['component_id']: p['source_ref'] for p in spec.get('packages', [])}
        if len(supplied) != len(spec.get('packages', [])):
            raise StudioError('Duplicate specification package component')
        for cid, package in packages.items():
            if supplied.get(cid) != package['source_ref']:
                raise StudioError('Package source reference differs from specification: '+cid)
    measurement_paths = [] if spec is None else copy.deepcopy(spec.get('measurement_paths', []))
    for measurement in measurement_paths:
        if measurement['piece'] not in textiles or textiles[measurement['piece']]['source_geometry'] is None:
            raise StudioError('Measurement path requires an actual textile source piece')
        edges = textiles[measurement['piece']]['source_geometry']['edges']
        if any(edge not in edges for edge in measurement['edges']):
            raise StudioError('Measurement path references a missing named source edge')
    if spec is None or 'layers' not in spec:
        missing('SPATIAL_ORDER_MISSING')
    if spec is None or 'budgets' not in spec:
        missing('RUN_BUDGETS_MISSING')
    assembly = None
    if not diagnostics:
        assembly = {'version': 1, 'source_ref': copy.deepcopy(source_ref), 'body_ref': copy.deepcopy(spec['body_ref']),
            'pieces': [{'id': pid, 'component_id': p['component_id'], **copy.deepcopy(p['semantics']),
                        'edges': sorted(p['source_geometry']['edges']), 'source_ref': copy.deepcopy(p['package_source_ref'])}
                       for pid, p in sorted(textiles.items())],
            'links': [{k: copy.deepcopy(link[k]) for k in ('id', 'kind', 'piece_a', 'edge_a', 'piece_b', 'edge_b', 'source_ref')}
                      for link in sorted(links, key=lambda row: row['id'])],
            'layers': copy.deepcopy(spec['layers']), 'budgets': copy.deepcopy(spec['budgets'])}
        # Validate topology/order with explicit consumer capabilities. A plan
        # is not evidence that the coupled native solver has been qualified.
        plan_assembly(assembly, capabilities=('coupled_multilayer',))
        assembly['layers']['nodes'].sort(key=lambda row: row['id'])
        for node in assembly['layers']['nodes']:
            node['panels'].sort(); node['colliders'].sort()
        assembly['layers']['inside_to_outside'].sort()
    if digest([dossier, packages, spec]) != original:
        raise StudioError('Production compiler changed an immutable source')
    result = {'version': 1, 'status': 'READY_TO_PLAN' if assembly else 'NEEDS_CLARIFICATION',
        'qualification': 'NONE', 'source_mutated': False, 'simulation': 'NOT_EXECUTED', 'fitting': 'NOT_EXECUTED',
        'dossier_sha256': digest(_sorted_dossier(dossier)), 'source_ref': copy.deepcopy(source_ref),
        'textile_count': len(textiles), 'rigid_count': len(rigid), 'components': components,
        'textiles': textiles, 'rigid_parts': sorted(rigid, key=lambda row: row['id']),
        'links': sorted(links, key=lambda row: row['id']), 'measurement_paths': sorted(measurement_paths, key=lambda row: row['id']),
        'diagnostics': sorted(diagnostics, key=digest), 'assembly_spec': assembly,
        'review': 'REQUIRED_BEFORE_NATIVE_EXECUTION'}
    result['compiled_sha256'] = digest(result)
    return result


def compile_project_dossier(project, dossier_path, specification_path):
    """Load sources safely inside one project and verify all declared hashes."""
    from .packages import inspect_package
    dossier_file = inside(project.root, dossier_path)
    spec_file = inside(project.root, specification_path)
    spec = contract('production-dossier', read_json(spec_file))
    if spec['source_ref'] != {'path': dossier_path, 'sha256': sha(dossier_file)}:
        raise StudioError('Production specification is not bound to the exact dossier file')

    def verify(value):
        if isinstance(value, dict):
            if set(value) == {'path', 'sha256'}:
                _reference(value)
                if sha(inside(project.root, value['path'])) != value['sha256']:
                    raise StudioError('Production source hash changed: '+value['path'])
            else:
                for item in value.values(): verify(item)
        elif isinstance(value, list):
            for item in value: verify(item)
    verify(spec)
    packages = {}
    for item in spec.get('packages', []):
        package_file = inside(project.root, item['source_ref']['path'])
        inspect_package(package_file)
        with zipfile.ZipFile(package_file) as archive:
            data = json.loads(archive.read('garment.json'))
        packages[item['component_id']] = {'source_ref': item['source_ref'], 'data': data}
    result = compile_production_dossier(read_json(dossier_file), packages, spec)
    result['specification_source_ref'] = {'path': specification_path, 'sha256': sha(spec_file)}
    result['compiled_sha256'] = digest({k: v for k, v in result.items() if k != 'compiled_sha256'})
    return result
