"""Measured garment preflight rejections, separate from evaluated Cloth failures."""
import math
import uuid

from .core import StudioError, atomic_json, digest, inside, read_json, sha


def cosine(a, b):
    length = math.sqrt(sum(x*x for x in a)*sum(x*x for x in b))
    return max(-1., min(1., sum(x*y for x, y in zip(a, b))/length)) if length > 1e-12 else None


def seam_directions(payload, coords, source=None):
    """Same local -0.5 guard as before; endpoint chords are context only."""
    source_seams = {s['id']: s for s in source['seams']} if source else {}
    summaries = {}; violations = []; threshold = -.5
    for sid, seam in payload['seams'].items():
        if seam['kind'] != 'permanent':
            continue
        pairs = seam['pairs']; samples = []
        for j, ((a, b), (c, d)) in enumerate(zip(pairs, pairs[1:])):
            u = [coords[c][i]-coords[a][i] for i in range(3)]
            v = [coords[d][i]-coords[b][i] for i in range(3)]
            value = cosine(u, v); samples.append(value)
            if value is None or value < threshold:
                def point(index):
                    return {'index': index, 'rest_uv_cm': payload['rest_cm'][index][:2], 'position_cm': coords[index]}
                named = source_seams.get(sid, seam)
                violations.append({'seam_id': sid, 'piece_a': seam['piece_a'], 'piece_b': seam['piece_b'],
                    'edge_a': named.get('edge_a'), 'edge_b': named.get('edge_b'), 'segment': j,
                    'previous_pair': [point(a), point(b)], 'next_pair': [point(c), point(d)],
                    'cosine': value, 'threshold': threshold,
                    'reason': 'undefined_zero_length_tangent' if value is None else 'opposed_local_tangents'})
        if len(pairs) > 1:
            a, b = pairs[0]; c, d = pairs[-1]
            chord = cosine([coords[c][i]-coords[a][i] for i in range(3)], [coords[d][i]-coords[b][i] for i in range(3)])
        else:
            chord = None
        bad = sum(v is not None and v < threshold for v in samples)
        summaries[sid] = {'segments': len(samples), 'opposed_segments': bad,
            'undefined_segments': sum(v is None for v in samples), 'endpoint_chord_cosine': chord,
            'opposition_extent': 'all_local_segments' if samples and bad == len(samples) else 'some_local_segments' if bad else 'none'}
    return {'threshold': threshold, 'seams': summaries, 'violations': violations,
        'interpretation': 'Local tangent test controls rejection; endpoint chords only describe overall direction. Local curve tangents may oppose while chords agree. Neither statistic proves a recipe error, Cloth defect, or false positive.'}


def save_rejection(project, data, recipe, payload, error, checkpoint):
    directory = project.data/('blender/garment-rejections/attempt-'+uuid.uuid4().hex)
    directory.mkdir(parents=True, exist_ok=False)
    component = project.state()['components'][data['component_id']]
    report = {'schema_version': 1, 'status': 'REJECTED', 'operation': 'garment',
        'simulation': 'NOT_EXECUTED', 'accepted': False, 'visual_validation': 'NOT_EXECUTED',
        'component_id': data['component_id'], 'package_sha256': component['package']['sha256'],
        'source_garment_sha256': digest(data), 'recipe_sha256': digest(recipe), 'recipe': recipe,
        'checkpoint': checkpoint, 'error': str(error), 'directions': None, 'outlier_edges': [], 'outlier_faces': [],
        'initial_contacts': getattr(error, 'initial_contacts', []), 'colliders': getattr(error, 'collider_snapshots', []),
        'contact_interpretation': 'Nearest-surface signed vertex samples; not exhaustive triangle intersection or a Cloth result.'}
    if payload:
        coords=getattr(error, 'initial_coords_cm', payload['placed_cm'])
        report['candidate_boundary_map_sha256'] = digest(payload)
        report['vertex_count'] = len(payload['rest_cm'])
        report['directions'] = seam_directions(payload, coords, data)
        from .sewing_diagnostics import failure_geometry
        geometry = failure_geometry(payload, coords, payload['placed_cm'], recipe)
        report['outlier_edges'] = geometry['outlier_edges']; report['outlier_faces'] = geometry['outlier_faces']
    path = directory/'diagnostic.json'; atomic_json(path, report)
    ref = {'path': path.relative_to(project.root).as_posix(), 'sha256': sha(path)}
    atomic_json(directory/'failure.json', {'status': 'REJECTED', 'operation': 'garment',
        'component_id': data['component_id'], 'package_sha256': report['package_sha256'], 'diagnostic': ref})
    return ref


def inspect_rejection(project, component_id, attempt_dir):
    directory = inside(project.root, attempt_dir)
    if directory.parent != project.data/'blender/garment-rejections' or not directory.name.startswith('attempt-'):
        raise StudioError('Diagnostic must belong to an existing garment rejection')
    failure = read_json(directory/'failure.json'); ref = failure.get('diagnostic')
    if failure.get('status') != 'REJECTED' or failure.get('operation') != 'garment' or not isinstance(ref, dict):
        raise StudioError('No preserved garment preflight rejection diagnostic')
    path = inside(project.root, ref['path'])
    if path.parent != directory or sha(path) != ref['sha256']:
        raise StudioError('Garment rejection diagnostic changed or targets another attempt')
    report = read_json(path)
    if (report.get('component_id') != component_id or failure.get('component_id') != component_id
        or report.get('package_sha256') != failure.get('package_sha256') or report.get('status') != 'REJECTED'
        or report.get('operation') != 'garment' or report.get('simulation') != 'NOT_EXECUTED' or report.get('accepted') is not False):
        raise StudioError('Garment rejection diagnostic identity/status mismatch')
    return {**report, 'diagnostic': ref,
        'note': 'Historical rejected candidate; no garment receipt or Cloth acceptance. Inspection does not clear pending recovery.'}
