"""Pure source and board fixtures shared by portable and native textile tests."""
import copy

from a3d.core import atomic_json

RESPONSE_CONTROLS=('SOURCE_COINCIDENT_PERMANENT','DETACHABLE_SEPARATED_FORCE_CONTROL',
    'PERMANENT_0_1_CM_INITIAL_GAP','PERMANENT_0_4_CM_INITIAL_GAP','SOURCE_COINCIDENT_NO_SUPPORT_CONTROL')


def response_control(initial,plan,case):
    """One declared intervention on a disposable synthetic causal copy."""
    from a3d.pattern_assembly import support_weights
    if case not in RESPONSE_CONTROLS:raise ValueError('Unknown synthetic response control')
    payload=copy.deepcopy(initial)
    if case=='DETACHABLE_SEPARATED_FORCE_CONTROL':
        for seam in payload['seams'].values():seam['kind']='detachable'
    offset={'DETACHABLE_SEPARATED_FORCE_CONTROL':1.,'PERMANENT_0_1_CM_INITIAL_GAP':.1,
        'PERMANENT_0_4_CM_INITIAL_GAP':.4}.get(case,0.)
    for index in payload['panels']['outer']['indices']:payload['placed_cm'][index][0]+=offset
    payload['pins'],supports=support_weights(payload,plan,'assembly',0.)
    if case=='SOURCE_COINCIDENT_NO_SUPPORT_CONTROL':
        payload['pins']={};supports['diagnostic_override']='NO_SUPPORTS_ON_CAUSAL_COPY_ONLY'
    return payload,supports


def source(path, case):
    path.mkdir(parents=True, exist_ok=True)
    pieces = {}
    for pid in (['belt'] if case == 'belt' else ['inner', 'outer']):
        pieces[pid] = {'vertices': [[0, 0], [2, 0], [2, 8], [0, 8]],
            'faces': [[0, 1, 2], [0, 2, 3]],
            'edges': {'left': [0, 3], 'right': [1, 2], 'top': [3, 2], 'bottom': [0, 1]},
            'position_cm': [0, -2, 20], 'rotation_degrees': [90, 0, 0]}
    if case == 'belt':
        seam = {'id': 'ends', 'piece_a': 'belt', 'edge_a': 'left', 'piece_b': 'belt',
                'edge_b': 'right', 'orientation': 'forward', 'kind': 'closure'}
    else:
        seam = {'id': 'interface', 'piece_a': 'inner', 'edge_a': 'right', 'piece_b': 'outer',
                'edge_b': 'left', 'orientation': 'forward', 'kind': 'permanent' if case == 'coupled' else 'detachable'}
    result = {'component_id': 'garment.coat', 'units': 'cm', 'pieces': pieces, 'seams': [seam],
        'material': {'mass_kg': .3, 'tension_stiffness': 15, 'compression_stiffness': 15,
                     'shear_stiffness': 5, 'bending_stiffness': .5}}
    atomic_json(path/'garment.json', result)
    polygons = ''.join('<polygon id="'+pid+'" points="0,0 2,0 2,8 0,8"/>' for pid in pieces)
    (path/'pattern.svg').write_text('<svg xmlns="http://www.w3.org/2000/svg" width="2cm" height="8cm" viewBox="0 0 2 8">'+polygons+'</svg>', encoding='utf-8')
    return result


def annotate_dossier(result, data):
    base = result['components']['garment.coat']['pieces'][1]
    pieces = []
    for pid in data['pieces']:
        row = copy.deepcopy(base); row.update(id=pid, label='Synthetic native group '+pid, dimensions_cm=[2, 8])
        row['pattern']['cut_outline_cm'] = [[-1,-1],[3,-1],[3,9],[-1,9]]
        row['pattern']['folds'] = []; row['pattern']['assembly_marks'] = []
        for seam in data['seams']:
            if seam['piece_a'] == seam['piece_b'] == pid:
                # The board contract stores one shared mark per source piece,
                # including a closure between two edges of the same band.
                row['pattern']['assembly_marks'].append({'id': 'R-'+seam['id'], 'seam_id': seam['id'],
                    'position': .5, 'symbol': 'notch'})
                continue
            for side in ('a', 'b'):
                if seam['piece_'+side] == pid:
                    row['pattern']['assembly_marks'].append({'id': 'R-'+seam['id'], 'seam_id': seam['id'],
                        'position': .7 if side == 'b' and seam['orientation'] == 'reverse' else .3, 'symbol': 'notch'})
        pieces.append(row)
    result['components']['garment.coat']['pieces'] = pieces
    result['exploded']['annotations'] = [{'component_id': 'garment.coat', 'piece_id': p['id'],
        'anchor_px': [15+i*20, 45], 'label_position_px': [3, 85+i*15]} for i, p in enumerate(pieces)]
    return result
