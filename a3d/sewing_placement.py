"""Initial mounting measurements; never a drape or sewing acceptance."""
import math

from .sewing import distance
from .sewing_diagnostics import source_coordinates


def extents(points):
    if not points:
        return None
    return {'min': [min(p[k] for p in points) for k in range(3)],
            'max': [max(p[k] for p in points) for k in range(3)]}


def placement_geometry(payload, coords, recipe, nearest, crossings):
    """Callbacks use cm and declared collider identity, without scene mutations.

    Boundary arclengths identify derived samples on the source contour. They
    are not fabrication notches, an anatomical fit, or a collision-free path.
    """
    source = payload.get('source_vertex_indices', list(range(len(coords))))
    anchors = {}
    for pid, panel in payload['panels'].items():
        arc = dict(zip(panel['boundary'], panel['boundary_source_arclength_cm'], strict=True))
        for index in panel['indices']:
            anchors[(pid,index)] = {'index': index, 'source_vertex_index': source[index], 'piece': pid,
                **source_coordinates(payload,index,pid), 'position_cm': coords[index],
                'boundary_source_arclength_cm': arc.get(index),
                'named_edges': [name for name, ids in panel['edges'].items() if index in ids],
                'pin_weight': payload['pins'].get(str(index), 0.)}
    near_cache = {}
    def node(index,piece):
        if index not in near_cache:
            near_cache[index] = nearest(coords[index])
        return {**anchors[(piece,index)], 'nearest_colliders': near_cache[index]}
    seams = {}
    for sid, seam in payload['seams'].items():
        pairs = []
        for a, b in seam['pairs']:
            pairs.append({'a': node(a,seam['piece_a']), 'b': node(b,seam['piece_b']), 'gap_cm': distance(coords[a], coords[b]),
                'straight_segment_hits': crossings(coords[a], coords[b])})
        seams[sid] = {k: seam[k] for k in ('kind', 'piece_a', 'piece_b', 'edge_a', 'edge_b')}
        seams[sid].update(pairs=pairs, max_gap_cm=max((p['gap_cm'] for p in pairs), default=0.),
            segments_crossing_collider=sum(bool(p['straight_segment_hits']) for p in pairs),
            above_final_seam_tolerance=sum(p['gap_cm'] > recipe['limits']['max_seam_gap_cm'] for p in pairs)
                if seam['kind'] == 'permanent' else None)
    face_owner = {i: pid for pid, p in payload['panels'].items() for i in p['indices']}
    regions = {pid: {} for pid in payload['panels']}
    for fi, face in enumerate(payload['faces']):
        a, b, c = (coords[i] for i in face)
        u, v = ([p[k]-a[k] for k in range(3)] for p in (b, c))
        normal = [u[1]*v[2]-u[2]*v[1], u[2]*v[0]-u[0]*v[2], u[0]*v[1]-u[1]*v[0]]
        length = math.sqrt(sum(x*x for x in normal))
        normal = [x/length for x in normal] if length else [0., 0., 0.]
        center = [sum(coords[i][k] for i in face)/3 for k in range(3)]
        for hit in nearest(center):
            region = regions[face_owner[face[0]]].setdefault(hit['object'], [])
            region.append({'face': fi, 'surface_face': hit['face'], 'surface_cm': hit['point_cm'],
                'distance_cm': hit['distance_cm'], 'signed_offset_cm': hit['signed_offset_cm'],
                'normal_dot_collider': sum(a*b for a, b in zip(normal, hit['normal']))})
    panels = {}
    for pid, panel in payload['panels'].items():
        panels[pid] = {'placement': recipe['placements'][pid], 'source_contour_sha256': panel['source_contour_sha256'],
            'extents_cm': extents([coords[i] for i in panel['indices']]),
            'supports': [node(i,pid) for i in panel['indices'] if payload['pins'].get(str(i), 0.) > 0],
            'collider_regions': {name: {'surface_extents_cm': extents([r['surface_cm'] for r in rows]),
                'distance_range_cm': [min(r['distance_cm'] for r in rows), max(r['distance_cm'] for r in rows)],
                'normal_dot_range': [min(r['normal_dot_collider'] for r in rows), max(r['normal_dot_collider'] for r in rows)],
                'inward_faces': sum(r['normal_dot_collider'] < -.25 for r in rows),
                'faces': rows} for name, rows in regions[pid].items()}}
    return {'seams': seams, 'panels': panels,
        'warnings': {'permanent_seams_above_final_tolerance': [sid for sid, s in seams.items() if s['above_final_seam_tolerance']],
            'seams_with_straight_segment_hits': [sid for sid, s in seams.items() if s['segments_crossing_collider']]},
        'interpretation': 'Initial measurements only. Final tolerances are not initial fit gates. Straight-segment hits and normal dots do not prove draping impossible. Collider regions are spatial samples, not anatomical labels.',
        'accepted': False, 'simulation': 'NOT_EXECUTED', 'visual_validation': 'NOT_EXECUTED'}
