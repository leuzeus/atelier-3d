"""Piece identity reconciliation. Object counts are never garment coverage."""
import json
import zipfile
from collections import Counter
from html import escape
from pathlib import Path

from .core import StudioError, digest, inside, read_json, sha


def expected_inventory(project, state=None):
    from .planning import require_board
    state = state or project.state()
    board = require_board(project, state)
    dossier = read_json(inside(project.root, board['dossier_path']))
    components = {}
    for cid, component in state['components'].items():
        package = component['package']
        textile = component['route']['selected'] == 'PATTERN_SEWN'
        info = {'package': package, 'kind': 'textile' if textile else 'rigid',
                'label': cid, 'pieces': [], 'source_sha256': None}
        if textile:
            with zipfile.ZipFile(inside(project.root, package['path'])) as archive:
                source = json.loads(archive.read('garment.json'))
            ids = [p['id'] for p in dossier['components'][cid]['pieces']]
            if len(ids) != len(set(ids)) or set(ids) != set(source['pieces']):
                raise StudioError('Reviewed cutting inventory differs from source package: ' + cid)
            info.update(pieces=sorted(ids), source_sha256=digest(source))
        components[cid] = info
    return {'project_id': state['project_id'], 'asset_id': state['asset']['id'],
            'construction_board': state['evidence']['construction-board'],
            'components': components}


def face_piece_ids(payload, faces, vertex_count):
    """Require every actual face to carry one unambiguous source-piece identity."""
    if payload.get('faces') != faces or len(payload.get('rest_cm', [])) != vertex_count:
        raise StudioError('Actual topology differs from the source correspondence')
    labels = payload.get('source_face_pieces')
    if labels is None:
        # Legacy maps can prove a disconnected original panel mesh only.
        owners_by_vertex = {}
        for pid, panel in payload.get('panels', {}).items():
            for index in panel.get('indices', []):
                owners_by_vertex.setdefault(index, set()).add(pid)
        labels = []
        for face in faces:
            owners = set.intersection(*(owners_by_vertex.get(index, set()) for index in face)) if face else set()
            if len(owners) != 1:
                raise StudioError('Source piece correspondence is missing or ambiguous')
            labels.append(next(iter(owners)))
    if len(labels) != len(faces) or not faces or any(not isinstance(p, str) or not p for p in labels):
        raise StudioError('Every actual face requires a source piece identity')
    if any(len(set(f)) < 3 or any(type(i) is not int or i < 0 or i >= vertex_count for i in f) for f in faces):
        raise StudioError('Invalid actual face indices')
    if set(labels) != set(payload.get('panels', {})):
        raise StudioError('Source panels and actual face identities differ')
    return labels


def mapped_pieces(payload, faces, vertex_count):
    return sorted(set(face_piece_ids(payload, faces, vertex_count)))


def reconcile(expected, observations, component_id=None, errors=()):
    if component_id is not None and component_id not in expected['components']:
        raise StudioError('Unknown inventory scope')
    counts, visible, rows, unknown, unexpected = Counter(), set(), [], list(errors), []
    for item in observations:
        cid = item['component_id']
        info = expected['components'].get(cid)
        if not info or info['kind'] != 'textile':
            unexpected.append(item); continue
        if item.get('error') or item.get('package_sha256') != info['package']['sha256'] or item.get('source_sha256') != info['source_sha256']:
            unknown.append({'component_id': cid, 'object': item.get('object'),
                            'reason': item.get('error') or 'Candidate source/package provenance differs'})
            continue
        for pid in item['pieces']:
            key = (cid, pid)
            if pid not in info['pieces']:
                unexpected.append({'component_id': cid, 'piece_id': pid}); continue
            counts[key] += 1
            if item.get('visible'): visible.add(key)
        rows.append(item)

    def coverage(cids):
        keys = {(cid, pid) for cid in cids for pid in expected['components'][cid]['pieces']}
        missing = sorted(keys - counts.keys())
        duplicates = sorted(k for k in keys if counts[k] > 1)
        scoped_unknown = [u for u in unknown if u.get('component_id') in cids or not u.get('component_id')]
        scoped_extra = [u for u in unexpected if u.get('component_id') in cids or not u.get('component_id')]
        return {'status': 'NON_VERIFIABLE' if scoped_unknown else 'INCOMPLETE' if missing or duplicates or scoped_extra else 'COMPLETE',
                'expected': len(keys), 'present': len(keys & counts.keys()),
                'visible_in_view_layer': len(keys & visible), 'missing': [list(k) for k in missing],
                'duplicates': [{'component_id': k[0], 'piece_id': k[1], 'count': counts[k]} for k in duplicates],
                'unknown': scoped_unknown, 'unexpected': scoped_extra,
                'capture_visibility': 'NOT_VERIFIED', 'technical_acceptance': 'NOT_INFERRED'}

    textile = [cid for cid, info in expected['components'].items() if info['kind'] == 'textile']
    global_coverage = coverage(textile)
    local = {cid: coverage([cid]) for cid in textile}
    g = global_coverage
    summary = f"Vêtement : {g['present']}/{g['expected']} pièces textiles présentes ; {len(g['missing'])} pièces manquantes"
    if component_id in local:
        c = local[component_id]
        summary = f"{component_id} : {c['present']}/{c['expected']} ; " + summary
    if g['status'] == 'NON_VERIFIABLE': summary += ' ; correspondance non vérifiable'
    if g['duplicates']: summary += f" ; {len(g['duplicates'])} identités en doublon"
    if not textile: summary = 'Aucune pièce textile attendue ; composants rigides suivis séparément'
    return {'schema_version': 1, 'scope': {'kind': 'component' if component_id else 'global', 'component_id': component_id},
            'expected_inventory': expected, 'inventory_sha256': digest(expected), 'global': g, 'components': local,
            'rigid_components': [cid for cid, info in expected['components'].items() if info['kind'] != 'textile'],
            'observations': rows, 'summary': summary,
            'qualification': 'PRESENCE_ONLY_NOT_SIMULATION_OR_VISUAL_ACCEPTANCE'}


def require_complete(report, component_id=None):
    coverage = report['components'].get(component_id) if component_id else report['global']
    if not coverage or coverage['status'] != 'COMPLETE':
        raise StudioError('Piece completeness blocks this milestone: ' + report['summary'])


def write_review(project, report, path, images=()):
    """Keep explicit coverage beside original pixels, including partial previews."""
    from urllib.parse import quote
    cards = []
    for image in images:
        image_path = inside(project.root, image['path'])
        if sha(image_path) != image['sha256']: raise StudioError('Review image changed')
        import os
        src = quote(os.path.relpath(image_path, path.parent).replace('\\', '/'), safe='/')
        cards.append(f'<figure><img src="{src}" alt="Vue technique partielle"><figcaption>{escape(report["summary"])}</figcaption></figure>')
    missing = ''.join('<li>'+escape('/'.join(k))+'</li>' for k in report['global']['missing'])
    rows = ''.join(f'<tr><td>{escape(cid)}</td><td>{c["present"]}/{c["expected"]}</td><td>{escape(c["status"])}</td></tr>'
                   for cid,c in report['components'].items())
    anomalies = report['global'].get('duplicates', []) + report['global'].get('unknown', []) + report['global'].get('unexpected', [])
    details = ''.join('<li>'+escape(json.dumps(a, ensure_ascii=False))+'</li>' for a in anomalies)
    history = ('<p><b>Reproduction historique depuis le maillage dérivé sauvegardé ; scène Blender vivante non réinspectée.</b></p>'
               if report.get('evidence_scope') == 'HISTORICAL_SAVED_DERIVED_MAP_ONLY_NOT_LIVE_BLENDER' else '')
    text = ('<!doctype html><html lang="fr"><meta charset="utf-8"><title>Complétude des pièces</title>'
            '<style>body{font:16px sans-serif;max-width:1000px;margin:2rem auto}img{max-width:100%;max-height:720px}strong{display:block;padding:1rem;background:#fff0c0}</style>'
            f'<h1>Complétude des pièces</h1>{history}<strong>{escape(report["summary"])}</strong>'
            f'<p>Statut : {escape(report["global"]["status"])}. Présence ≠ visibilité dans la capture ≠ qualification.</p>'
            '<p>Les aperçus portent sur le candidat local ; cadrage et occultation restent à vérifier visuellement.</p>'
            '<table><tr><th>Composant</th><th>Présence</th><th>Statut</th></tr>'+rows+'</table>'
            '<h2>Pièces manquantes</h2><ul>'+missing+'</ul><h2>Anomalies de correspondance</h2><ul>'+details+'</ul>'+''.join(cards)+'</html>')
    path.parent.mkdir(parents=True, exist_ok=True); path.write_text(text, encoding='utf-8')
    return {'path': path.relative_to(project.root).as_posix(), 'sha256': sha(path)}


def current_proof(project, state=None, require_global=False):
    """A saved scene/package/candidate change invalidates earlier coverage."""
    state = state or project.state()
    path = project.data/('blender/piece-active-proof.json' if require_global else 'blender/piece-completeness.json')
    try:
        report = read_json(path)
        if report.get('is_dirty'):
            raise StudioError('Live observation is dirty; save the managed scene and inspect again')
        expected = expected_inventory(project, state)
        session = read_json(project.data/'blender/session.json')
        working = Path(session['working']).resolve()
        if not working.is_relative_to(project.data/'blender') or report['artifact'] != {'path': working.relative_to(project.root).as_posix(), 'sha256': sha(working)}:
            raise StudioError('Completeness proof no longer matches the saved scene')
        if report['inventory_sha256'] != digest(expected): raise StudioError('Completeness packages/board changed')
        for dep in report['dependencies']:
            if sha(inside(project.root, dep['path'])) != dep['sha256']: raise StudioError('Completeness correspondence changed')
        rebuilt = reconcile(expected, report['observations'], report['scope']['component_id'], report.get('collection_errors', []))
        if rebuilt['global'] != report['global']: raise StudioError('Completeness reconciliation changed')
        if require_global:
            if report.get('candidate_mode') != 'active': raise StudioError('Global milestone requires active geometry, not preparation previews')
            require_complete(report)
        return report
    except (OSError, KeyError, ValueError) as exc:
        raise StudioError('Current Blender piece completeness is required; run inspect: '+str(exc)) from exc


def cached_status(project):
    try:
        result = current_proof(project)
        return {'status': result['global']['status'], 'summary': result['summary'], 'global': result['global'],
                'live_scene': 'NOT_REINSPECTED', 'review': result.get('review')}
    except StudioError as exc:
        return {'status': 'NON_VERIFIABLE', 'reason': str(exc), 'live_scene': 'NOT_REINSPECTED'}
