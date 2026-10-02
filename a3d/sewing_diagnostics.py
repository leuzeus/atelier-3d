"""Measured failed Cloth states, never acceptance or replacement geometry."""
import math
import uuid
from pathlib import Path
from xml.sax.saxutils import escape

from .core import StudioError, atomic_json, inside, read_json, sha
from .sewing import distance


def failure_geometry(payload, coords, start, recipe, penetrations=()):
    source = payload.get('source_vertex_indices', list(range(len(payload['rest_cm']))))
    owners = {i: pid for pid, panel in payload.get('panels', {}).items() for i in panel['indices']}
    valid = len(coords) == len(payload['rest_cm']) and all(len(p) == 3 and all(math.isfinite(x) for x in p) for p in coords)
    base = {'evaluated_cm': [[x if math.isfinite(x) else None for x in p] for p in coords],
        'start_cm': start, 'rest_cm': payload['rest_cm'], 'faces': payload['faces'],
        'source_vertex_indices': source, 'source_face_indices': payload.get('source_face_indices', list(range(len(payload['faces'])))),
        'panels': payload.get('panels', {}), 'pins': payload['pins'], 'seams': payload['seams'],
        'fitting_tacks':payload.get('fitting_tacks',[]),
        'finite_matching_topology': valid, 'penetrations': list(penetrations), 'outlier_edges': [], 'outlier_faces': [], 'seam_gaps': {}}
    if not valid:
        return base
    limits = recipe['mesh']
    edges = sorted({tuple(sorted((a, b))) for f in payload['faces'] for a, b in zip(f, f[1:] + f[:1])})
    for a, b in edges:
        rest = distance(payload['rest_cm'][a], payload['rest_cm'][b])
        placed = distance(coords[a], coords[b])
        ratio = placed / rest if rest > 1e-8 else None
        reasons = []
        if ratio is None: reasons.append('collapsed_rest')
        elif ratio < limits['min_stretch']: reasons.append('compression')
        elif ratio > limits['max_stretch']: reasons.append('stretch')
        if placed < limits['min_edge_cm']: reasons.append('short_edge')
        if reasons:
            base['outlier_edges'].append({'indices': [a,b], 'source_indices': [source[a],source[b]],
                'pieces': sorted({owners.get(a, 'unknown'), owners.get(b, 'unknown')}), 'rest_cm': rest,
                'evaluated_cm': placed, 'ratio': ratio, 'reasons': reasons})
    for fi, face in enumerate(payload['faces']):
        lengths = [distance(coords[a],coords[b]) for a,b in zip(face, face[1:] + face[:1])]
        if len(face) != 3 or min(lengths) < 1e-8:
            angle, area = 0., 0.
        else:
            a,b,c = lengths; sem = sum(lengths)/2
            area = math.sqrt(max(0.,sem*(sem-a)*(sem-b)*(sem-c)))
            angle = min(math.degrees(math.acos(max(-1.,min(1.,(x*x+y*y-z*z)/(2*x*y)))))
                for x,y,z in ((a,b,c),(b,c,a),(c,a,b)))
        if area < 1e-8 or angle < limits['min_angle_degrees']:
            base['outlier_faces'].append({'face':fi, 'source_face':base['source_face_indices'][fi],
                'indices':face, 'pieces':sorted({owners.get(i,'unknown') for i in face}),
                'min_angle_degrees':angle, 'area_cm2':area})
    for sid, seam in payload['seams'].items():
        pairs = [{'indices':[a,b], 'source_indices':[source[a],source[b]], 'initial_cm':distance(start[a],start[b]),
            'evaluated_cm':distance(coords[a],coords[b])} for a,b in seam['pairs']]
        base['seam_gaps'][sid] = {'kind':seam['kind'], 'pieces':[seam.get('piece_a'),seam.get('piece_b')],
            'max_gap_cm':max((p['evaluated_cm'] for p in pairs), default=0.),
            'temporary_fitting_tack':any(t['seam_id']==sid for t in payload.get('fitting_tacks',[])),
            'outside_tolerance':sum(p['evaluated_cm'] > recipe['limits']['max_seam_gap_cm'] for p in pairs)
                if seam['kind'] == 'permanent' or any(t['seam_id']==sid for t in payload.get('fitting_tacks',[])) else None, 'pairs':pairs}
    base['piece_extents_cm'] = {pid: {'min':[min(coords[i][k] for i in panel['indices']) for k in range(3)],
        'max':[max(coords[i][k] for i in panel['indices']) for k in range(3)], 'vertices':len(panel['indices'])}
        for pid,panel in payload.get('panels', {}).items() if panel['indices']}
    base['subset_kind'] = 'whole-pattern-pieces' if 'source_vertex_indices' in payload else 'full-mesh'
    base['omitted_seams'] = payload.get('omitted_seams', [])
    return base


def inspect_failure(project, component_id, attempt_dir):
    directory = inside(project.root, attempt_dir)
    parent = project.data / 'blender/sewing'
    if directory.parent != parent or not directory.name.startswith('attempt-'):
        raise StudioError('Diagnostic must belong to an existing sewing attempt')
    failure = read_json(directory / 'failure.json')
    ref = failure.get('diagnostic')
    if failure.get('simulation') != 'FAIL' or not isinstance(ref, dict):
        raise StudioError('This attempt has no preserved evaluated failure diagnostic')
    path = inside(project.root, ref['path'])
    if path.parent != directory or sha(path) != ref['sha256']:
        raise StudioError('Failure diagnostic changed or targets another attempt')
    data = read_json(path)
    if data.get('component_id') != component_id or data.get('simulation') != 'FAIL' or data.get('binding') != failure.get('binding') or data.get('scope') != failure.get('scope'):
        raise StudioError('Failure diagnostic component/status mismatch')
    geometry = data['geometry']
    preview = data.get('preview')
    if preview:
        preview_path = inside(project.root, preview['path'])
        if preview_path.parent != directory or sha(preview_path) != preview['sha256']:
            raise StudioError('Failure diagnostic preview changed')
    placement = data.get('placement')
    if placement is not None:
        placement_path = inside(project.root, placement['path'])
        if placement_path.parent != directory or sha(placement_path) != placement['sha256']:
            raise StudioError('Initial placement diagnostic changed')
        initial = read_json(placement_path)
        if any(initial.get(k) != data[k] for k in ('component_id', 'package_sha256', 'recipe_sha256', 'boundary_map_sha256')):
            raise StudioError('Initial placement diagnostic identity mismatch')
    probe_ref = data.get('probe_diagnostic')
    if probe_ref:
        probe_path = inside(project.root, probe_ref['path'])
        if (probe_path.parent.parent != directory/'backend-probes' or not probe_path.parent.name.startswith('failed-')
            or sha(probe_path) != probe_ref['sha256']):
            raise StudioError('Backend probe diagnostic changed or targets another attempt')
        native = read_json(probe_path)
        if native.get('execution_stage') != 'backend_probe' or native.get('probe') != data.get('probe'):
            raise StudioError('Backend probe diagnostic identity mismatch')
        native_preview=native.get('native_preview')
        if native_preview:
            native_image=inside(project.root,(probe_path.parent.relative_to(project.root)/native_preview['name']).as_posix())
            if native_image.parent!=probe_path.parent or sha(native_image)!=native_preview['sha256']:
                raise StudioError('Backend probe preview changed')
    return {'simulation':'FAIL', 'accepted':False, 'diagnostic':ref, 'component_id':component_id,
        'preview':preview, 'placement':placement, 'frame':data['frame'], 'error':data['error'], 'scope':data['scope'], 'phase':data['phase'],
        'package_sha256':data['package_sha256'], 'recipe_sha256':data['recipe_sha256'],
        'boundary_map_sha256':data['boundary_map_sha256'], 'binding':data['binding'],
        'evaluated_vertices':len(geometry['evaluated_cm']), 'finite_matching_topology':geometry['finite_matching_topology'],
        'outlier_edges':geometry['outlier_edges'], 'outlier_faces':geometry['outlier_faces'],
        'seam_gaps':geometry['seam_gaps'], 'penetrations':geometry['penetrations'],
        'piece_extents_cm':geometry.get('piece_extents_cm', {}), 'subset_kind':geometry.get('subset_kind'),
        'execution_stage':data.get('execution_stage','garment'), 'probe':data.get('probe'), 'probe_diagnostic':probe_ref,
        'backend_probe_simulation':data.get('backend_probe_simulation','NOT_RECORDED'),
        'final_quality':data.get('final_quality'),
        'fitting':data.get('fitting'),'fitting_tacks':geometry.get('fitting_tacks',[]),
        'garment_simulation':data.get('garment_simulation','FAIL'), 'mapping_domain':geometry.get('mapping_domain','pattern-pieces'),
        'omitted_seams':geometry.get('omitted_seams', []), 'visual_validation':'NOT_EXECUTED',
        'note':'Historical failed state. For backend_probe, geometry belongs to synthetic coupons; package, boundary map and placement bind the parent request, not coupon vertices. No full simulation or acceptance is authorized.'}


def store_probe_failure(output_dir, data):
    """Unique native evidence before coupon cleanup, also for standalone probes."""
    directory=Path(output_dir)/('failed-'+data['probe']['case']+'-'+uuid.uuid4().hex)
    directory.mkdir(exist_ok=False)
    preview=preview_svg(data)
    if preview:
        (directory/'diagnostic.svg').write_text(preview,encoding='utf-8')
        data['native_preview']={'name':'diagnostic.svg','sha256':sha(directory/'diagnostic.svg')}
    path=directory/'diagnostic.json';atomic_json(path,data)
    ref={'path':str(path.resolve()),'sha256':sha(path)}
    atomic_json(directory/'failure.json',{'simulation':'FAIL','execution_stage':'backend_probe',
        'garment_simulation':'NOT_EXECUTED','case':data['probe']['case'],'diagnostic':ref})
    return ref


def preview_svg(data):
    """Three measured projections of the failed state, no inferred garment image."""
    geometry = data['geometry']
    if not geometry['finite_matching_topology']:
        return None
    coords = geometry['evaluated_cm']
    is_probe=data.get('execution_stage')=='backend_probe'
    title=('PROBE '+data['probe']['case'].upper()+' FAIL — vêtement NON EXÉCUTÉ') if is_probe else 'CLOTH FAIL — diagnostic mesuré, non accepté'
    subtitle=(f"Coupons synthétiques · {escape(data['phase'])} · frame {data['frame']} / {data['probe']['configured_frames']} · recette vêtement : {data['probe']['requested_phase_frames']} frames") if is_probe else f"{escape(data['component_id'])} · {escape(data['phase'])} / {escape(data['scope'])} · frame {data['frame']}"
    bad = {tuple(e['indices']) for e in geometry['outlier_edges']}
    edges = sorted({tuple(sorted((a,b))) for face in geometry['faces'] for a,b in zip(face,face[1:]+face[:1])})
    svg = ['<svg xmlns="http://www.w3.org/2000/svg" width="1380" height="720" viewBox="0 0 1380 720">',
        '<rect width="1380" height="720" fill="#f8fafc"/>',
        '<g font-family="sans-serif" fill="#172033">',
        f'<text x="25" y="32" font-size="21">{escape(title)}</text>',
        f'<text x="25" y="57">{subtitle}</text>',
        '<text x="25" y="79">Gris : arêtes · rouge : arêtes hors limites · violet : pénétrations. Projections du dernier état évalué.</text>']
    for column,(label,x,y) in enumerate((('XY',0,1),('XZ',0,2),('YZ',1,2))):
        left = 25+column*455
        lows = [min(p[k] for p in coords) for k in (x,y)]
        highs = [max(p[k] for p in coords) for k in (x,y)]
        scale = 370/max(highs[0]-lows[0],highs[1]-lows[1],1e-6)
        def position(index):
            p=coords[index]
            return (left+35+(p[x]-lows[0])*scale,510-(p[y]-lows[1])*scale)
        svg.append(f'<text x="{left}" y="110">Projection {label} · échelle {scale:.3f} px/cm</text>')
        for color,width,select in (('#9aa6b2',0.5,False),('#d32626',1.6,True)):
            svg.append(f'<g fill="none" stroke="{color}" stroke-width="{width}">')
            for a,b in edges:
                if ((a,b) in bad) != select:continue
                ax,ay=position(a);bx,by=position(b)
                svg.append(f'<path d="M{ax:.2f},{ay:.2f} L{bx:.2f},{by:.2f}"/>')
            svg.append('</g>')
        for point in geometry['penetrations']:
            px,py=position(point['index'])
            svg.append(f'<circle cx="{px:.2f}" cy="{py:.2f}" r="2.5" fill="#9520bc"/>')
    svg.append(f'<text x="25" y="555">Arêtes hors limites : {len(geometry["outlier_edges"])} · faces hors limites : {len(geometry["outlier_faces"])} · pénétrations : {len(geometry["penetrations"])}</text>')
    svg.append(f'<text x="25" y="579">Sous-ensemble : {escape(geometry["subset_kind"])} · panneaux : {escape(", ".join(geometry["panels"]))}</text>')
    for i,(sid,seam) in enumerate(sorted(geometry['seam_gaps'].items(),key=lambda p:p[1]['max_gap_cm'],reverse=True)[:4]):
        svg.append(f'<text x="25" y="{607+i*22}">{escape(sid)} ({escape(seam["kind"])}) : écart maximal {seam["max_gap_cm"]:.4f} cm</text>')
    svg.append('</g></svg>')
    return '\n'.join(svg)
