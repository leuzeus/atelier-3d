"""Compose explicitly scoped pattern inputs, without human or native admission.

These helpers receive already parsed JSON values. They neither authenticate a
human review nor replace the project consumer's source, package and gate checks.
Array order and every JSON number are compared without a geometric tolerance.
"""
import copy

from .core import StudioError, canonical, contract, digest


def _json(value, label):
    try:
        pending = [value]; seen = set()
        while pending:
            current = pending.pop()
            if isinstance(current, (dict, list)):
                if id(current) in seen:
                    continue
                seen.add(id(current))
                if isinstance(current, dict):
                    if any(not isinstance(key, str) for key in current):
                        raise TypeError('JSON object keys must be strings')
                    pending.extend(current.values())
                else:
                    pending.extend(current)
            elif current is not None and type(current) not in (str, bool, int, float):
                raise TypeError('Value is not a JSON scalar or array')
        return canonical(value)
    except (TypeError, ValueError, RecursionError) as error:
        raise StudioError(label+' must contain finite JSON values') from error


def _same(a, b):
    return _json(a, 'Comparison input') == _json(b, 'Comparison input')


def _id(value, label):
    if not isinstance(value, str) or not value.strip():
        raise StudioError(label+' requires a nonempty string ID')
    return value


def _scope(piece_ids, available):
    if not isinstance(piece_ids, (list, tuple)) or not piece_ids:
        raise StudioError('Reviewed piece scope must be a nonempty explicit sequence')
    values = [_id(pid, 'Reviewed piece scope') for pid in piece_ids]
    if len(values) != len(set(values)):
        raise StudioError('Reviewed piece scope contains duplicate IDs')
    absent = set(values)-set(available)
    if absent:
        raise StudioError('Reviewed piece scope contains absent pieces: '+', '.join(sorted(absent)))
    return values, set(values)


def _metadata():
    return {'version': 1, 'status': 'COMPOSED_INPUTS_ONLY', 'qualification': 'NONE',
            'construction': 'NOT_GRANTED', 'fitting': 'NOT_GRANTED',
            'permission': 'NOT_GRANTED', 'human_review': 'NOT_GRANTED'}


def _garment(data, label):
    if not isinstance(data, dict):
        raise StudioError(label+' must be a garment JSON object')
    _json(data, label)
    contract('garment', data)
    if not data['pieces']:
        raise StudioError(label+' requires a nonempty piece inventory')
    for pid in data['pieces']:
        _id(pid, label+' piece')
    seen = set()
    for row in data['seams']:
        if row['id'] in seen:
            raise StudioError(label+' contains duplicate seam IDs: '+row['id'])
        seen.add(row['id'])
        for side in ('a', 'b'):
            pid, edge = row['piece_'+side], row['edge_'+side]
            if pid not in data['pieces'] or edge not in data['pieces'][pid]['edges']:
                raise StudioError(label+' seam references an absent piece or named edge: '+row['id'])
    return data['pieces']


def verify_pattern_variant_scope(approved_garment, variant_garment, reviewed_piece_ids):
    """Reject every package change outside the explicit piece-level scope.

    Global fields include component identity, units, complete seam array order
    and material. Reviewed geometry may change; piece and named-edge IDs remain
    stable. The return value reports comparison only and grants no admission.
    """
    original = _garment(approved_garment, 'Approved garment')
    candidate = _garment(variant_garment, 'Variant garment')
    if set(original) != set(candidate):
        raise StudioError('Variant garment piece inventory or IDs changed')
    scope, selected = _scope(reviewed_piece_ids, original)
    if not _same({k: v for k, v in approved_garment.items() if k != 'pieces'},
                 {k: v for k, v in variant_garment.items() if k != 'pieces'}):
        raise StudioError('Variant garment global fields, component, seams or material changed')
    changed = []
    for pid, piece in original.items():
        other = candidate[pid]
        if set(piece['edges']) != set(other['edges']):
            raise StudioError('Variant garment named-edge IDs changed: '+pid)
        if not _same(piece, other):
            if pid not in selected:
                raise StudioError('Variant garment changed a piece outside reviewed scope: '+pid)
            changed.append(pid)
    return dict(_metadata(), component_id=approved_garment['component_id'],
                reviewed_piece_ids=scope, changed_piece_ids=changed,
                preserved_piece_ids=[pid for pid in original if pid not in selected],
                approved_garment_sha256=digest(approved_garment),
                variant_garment_sha256=digest(variant_garment),
                comparison='EXACT_JSON_NO_EPSILON')


def _rows(dossier, label):
    if not isinstance(dossier, dict) or not isinstance(dossier.get('components'), dict) or not dossier['components']:
        raise StudioError(label+' requires a nonempty component inventory')
    _json(dossier, label)
    rows = {}
    for cid, component in dossier['components'].items():
        _id(cid, label+' component')
        if not isinstance(component, dict) or not isinstance(component.get('pieces'), list) or not component['pieces']:
            raise StudioError(label+' component requires explicit piece rows: '+cid)
        for position, row in enumerate(component['pieces']):
            if not isinstance(row, dict):
                raise StudioError(label+' piece row must be a JSON object')
            pid = _id(row.get('id'), label+' piece row')
            if pid in rows:
                raise StudioError(label+' contains duplicate piece IDs: '+pid)
            pattern = row.get('pattern')
            if pattern is not None:
                if not isinstance(pattern, dict):
                    raise StudioError(label+' piece pattern must be a JSON object: '+pid)
                for field in ('assembly_marks', 'folds'):
                    if field not in pattern:
                        continue
                    values = pattern[field]
                    if not isinstance(values, list):
                        raise StudioError(label+' '+field+' must be an ordered array: '+pid)
                    seen = set()
                    for value in values:
                        if not isinstance(value, dict):
                            raise StudioError(label+' '+field+' row must be a JSON object: '+pid)
                        name = _id(value.get('id'), label+' '+field)
                        identity = ((_id(value.get('seam_id'), label+' assembly mark seam'), name)
                                    if field == 'assembly_marks' else name)
                        if identity in seen:
                            raise StudioError(label+' contains duplicate '+field+' IDs: '+pid+' / '+name)
                        seen.add(identity)
            rows[pid] = (cid, position, row)
    return rows


def _differences(before, after, path=''):
    """Keep exact excluded values, including order changes and single-ULP changes."""
    if _same(before, after):
        return []
    if isinstance(before, dict) and isinstance(after, dict):
        result = []
        for key in list(before)+[key for key in after if key not in before]:
            location = path+'/'+key.replace('~', '~0').replace('/', '~1')
            if key not in before or key not in after:
                record = {'path': location, 'approved_present': key in before, 'variant_present': key in after}
                if key in before: record['approved_value'] = copy.deepcopy(before[key])
                if key in after: record['variant_value'] = copy.deepcopy(after[key])
                result.append(record)
            else:
                result.extend(_differences(before[key], after[key], location))
        return result
    if isinstance(before, list) and isinstance(after, list) and len(before) == len(after):
        return [row for i, (a, b) in enumerate(zip(before, after))
                for row in _differences(a, b, path+'/'+str(i))]
    return [{'path': path, 'approved_present': True, 'variant_present': True,
             'approved_value': copy.deepcopy(before), 'variant_value': copy.deepcopy(after)}]


def compose_pattern_variant_dossier(approved_dossier, variant_dossier, reviewed_piece_ids):
    """Copy only reviewed rows, retaining every other original row and order.

    The caller must separately run ``verify_pattern_variant_scope`` for every
    affected package and authenticate the actual review. Nonreviewed candidate
    rows may differ, but their complete changes are excluded and reported.
    """
    original = _rows(approved_dossier, 'Approved dossier')
    candidate = _rows(variant_dossier, 'Variant dossier')
    if set(approved_dossier['components']) != set(variant_dossier['components']):
        raise StudioError('Variant dossier component inventory or IDs changed')
    if set(original) != set(candidate):
        raise StudioError('Variant dossier piece inventory or IDs changed')
    scope, selected = _scope(reviewed_piece_ids, original)
    if not _same({k: v for k, v in approved_dossier.items() if k != 'components'},
                 {k: v for k, v in variant_dossier.items() if k != 'components'}):
        raise StudioError('Variant dossier global fields changed')
    for cid, component in approved_dossier['components'].items():
        other = variant_dossier['components'][cid]
        if not _same({k: v for k, v in component.items() if k != 'pieces'},
                     {k: v for k, v in other.items() if k != 'pieces'}):
            raise StudioError('Variant dossier component global fields changed: '+cid)
    for pid, (cid, _, _) in original.items():
        if candidate[pid][0] != cid:
            raise StudioError('Variant dossier changed a piece component owner: '+pid)
    composed = copy.deepcopy(approved_dossier)
    excluded = []
    replaced = []
    order_changes = []
    for cid, component in approved_dossier['components'].items():
        original_order = [row['id'] for row in component['pieces']]
        variant_order = [row['id'] for row in variant_dossier['components'][cid]['pieces']]
        if original_order != variant_order:
            order_changes.append({'component_id': cid, 'approved_piece_order': original_order,
                                  'variant_piece_order': variant_order, 'composition': 'APPROVED_ORDER_PRESERVED'})
        for position, row in enumerate(component['pieces']):
            pid = row['id']; other = candidate[pid][2]
            if pid in selected:
                composed['components'][cid]['pieces'][position] = copy.deepcopy(other)
                replaced.append({'component_id': cid, 'piece_id': pid, 'approved_row_index': position,
                                 'variant_row_index': candidate[pid][1], 'changed': not _same(row, other)})
            elif not _same(row, other):
                excluded.append({'component_id': cid, 'piece_id': pid, 'approved_row_index': position,
                                 'variant_row_index': candidate[pid][1],
                                 'approved_row_sha256': digest(row), 'variant_row_sha256': digest(other),
                                 'composition': 'APPROVED_ROW_PRESERVED', 'differences': _differences(row, other)})
    return dict(_metadata(), reviewed_piece_ids=scope, dossier=composed,
                replaced_rows=replaced, excluded_unreviewed_differences=excluded,
                excluded_variant_order_changes=order_changes,
                approved_dossier_sha256=digest(approved_dossier), variant_dossier_sha256=digest(variant_dossier),
                composed_dossier_sha256=digest(composed), comparison='EXACT_JSON_NO_EPSILON',
                package_scope_verification='REQUIRED_SEPARATELY', source_and_review_authentication='REQUIRED_SEPARATELY')
