"""Read-only source composition backed by existing canonical human decisions.

The caller owns file copying, evidence registration and stage transitions. A
composition is calculated data; it never creates a human approval or a physics
permission. V1 accepts an original board parent, not another calculated board.
"""
import copy
import json
import sqlite3
from contextlib import closing
from pathlib import Path
import re
import zipfile

from .core import StudioError, canonical, digest, ident, inside, sha
from .packages import inspect_package
from .pattern_variant_composition import compose_pattern_variant_dossier, verify_pattern_variant_scope
from .store import Project

KEY = 'reviewed-pattern-composition'
KIND = 'CALCULATED_SOURCE_COMPOSITION'
_REF_FIELDS = ('proposal_ref', 'review_ref', 'candidate_dossier_ref', 'variant_package_ref',
               'numeric_design_decision_ref', 'body_ref', 'original_dossier_ref')
_BOUND_ROLES = ('proposal_ref', 'review_ref', 'candidate_dossier_ref', 'variant_package_ref')
_SOURCE_CODES = ('reviewed_pattern_admission.py', 'pattern_variant_composition.py')


def _equal(a, b):
    return canonical(a) == canonical(b)


def _parse(raw):
    def unique(rows):
        result = {}
        for key, value in rows:
            if key in result: raise StudioError('Composition JSON contains a duplicate object key: '+key)
            result[key] = value
        return result
    try:
        value = json.loads(raw, object_pairs_hook=unique)
        canonical(value)
        return value
    except (ValueError, TypeError, RecursionError) as error:
        raise StudioError('Composition inputs require finite unambiguous JSON') from error


def _state(project):
    with closing(sqlite3.connect(project.db.resolve().as_uri()+'?mode=ro', uri=True)) as db:
        db.execute('PRAGMA query_only=ON')
        return _parse(db.execute('SELECT doc FROM state WHERE id=1').fetchone()[0])


def _event(project, kind, predicate):
    with closing(sqlite3.connect(project.db.resolve().as_uri()+'?mode=ro', uri=True)) as db:
        db.execute('PRAGMA query_only=ON')
        return [(index, value) for index, raw in db.execute('SELECT id,doc FROM events WHERE kind=?', (kind,))
                if predicate(value := _parse(raw))]


def _ref(value):
    if (not isinstance(value, dict) or set(value) != {'path', 'sha256'} or
            not isinstance(value['path'], str) or not isinstance(value['sha256'], str) or
            not re.fullmatch('[0-9a-f]{64}', value['sha256'])):
        raise StudioError('Composition needs exact path/sha256 references')
    return value


def _reference(record):
    if not isinstance(record, dict) or not {'path', 'sha256'} <= record.keys():
        raise StudioError('Composition evidence needs an exact file identity')
    return _ref({key: record[key] for key in ('path', 'sha256')})


def _read(project, reference, *, json_value=True):
    reference = _ref(reference)
    try:
        file = inside(project.root, reference['path']); raw = file.read_bytes()
    except OSError as error:
        raise StudioError('Composition source file is missing or unreadable: '+reference['path']) from error
    import hashlib
    if hashlib.sha256(raw).hexdigest() != reference['sha256']:
        raise StudioError('Composition source file changed: '+reference['path'])
    return _parse(raw) if json_value else file


def _human(project, state, name, *, direct=True, visited=()):
    """Pattern review must be direct; original design may use legacy import."""
    project.require_gate(state, name)
    gate = state['gates'][name]
    if (gate.get('source') != 'human' or not isinstance(gate.get('statement'), str) or not gate['statement'].strip()
            or not isinstance(gate.get('source_ref'), str) or not gate['source_ref'].strip()
            or not isinstance(gate.get('decision_id'), str) or not gate['decision_id']):
        raise StudioError('Composition requires an actual canonical human decision: '+name)
    rows = _event(project, 'human_decision', lambda row: row.get('decision_id') == gate['decision_id'])
    if rows:
        if len(rows) != 1 or rows[0][1].get('name') != name or not _equal({k: v for k, v in rows[0][1].items() if k != 'name'}, gate):
            raise StudioError('Composition human decision contradicts its canonical event: '+name)
        return {'project': str(project.root), 'project_id': state['project_id'], 'event_id': rows[0][0],
                'decision_id': gate['decision_id'], 'gate_name': name, 'import_lineage': []}, copy.deepcopy(gate)
    if direct:
        raise StudioError('Composition pattern review lacks a direct canonical human event: '+name)
    if str(project.root) in visited or len(visited) >= 8:
        raise StudioError('Original design approval import lineage is cyclic or exceeds V1 depth')
    record = project.verify_evidence(state, 'approved-design-import')
    imported = _read(project, _reference(record))
    events = _event(project, 'approved_design_context_imported', lambda row: _equal(row, imported))
    if (not isinstance(imported, dict) or len(events) != 1 or imported.get('status') != 'EXACT_APPROVED_DESIGN_IMPORTED' or
            imported.get('human_decision_ids', {}).get(name) != gate['decision_id']):
        raise StudioError('Original human decision lacks its exact canonical design import')
    parent = Project(imported['source_project']); parent_state = _state(parent)
    if not _equal(parent_state['gates'].get(name), gate):
        raise StudioError('Original human decision changed in its import parent')
    from .planning import require_board
    require_board(parent, parent_state)
    origin, original_gate = _human(parent, parent_state, name, direct=False, visited=(*visited, str(project.root)))
    origin['import_lineage'].insert(0, {'project': str(project.root), 'project_id': state['project_id'],
                                      'event_id': events[0][0], 'import_ref': _reference(record)})
    return origin, original_gate


def _codes():
    directory = Path(__file__).resolve().parent
    return {'a3d/'+name: sha(directory/name) for name in _SOURCE_CODES}


def _base(project, state):
    if KEY in state['evidence']:
        raise StudioError('Calculated composition nesting is unsupported in V1')
    from .planning import require_board, package_records
    board = require_board(project, state)
    origin = board.get('origin')
    if origin is not None and not isinstance(origin, dict):
        raise StudioError('Original source board has malformed origin metadata')
    if board.get('kind') == KIND or isinstance(origin, dict) and origin.get('kind') == 'calculated':
        raise StudioError('V1 composition requires its original reviewed construction board')
    reference = _reference(project.verify_evidence(state, 'construction-board'))
    if not _equal(_read(project, reference), board):
        raise StudioError('Original source board is not its exact registered artifact')
    names = ['references', 'construction']+['route.'+cid for cid in state['components']]
    parents = {}; gates = {}
    for name in names:
        parents[name], gates[name] = _human(project, state, name, direct=False)
    return board, reference, package_records(project, state), parents, gates


def _generation_origin(project, state, board, packages, dossier, *, visited=()):
    """Validate original generation at its real parent, never a new design.

    Legacy approved-input imports deliberately copied the generation receipt,
    not the request evidence slot. Only that exact canonical import can lead to
    the existing request in its unchanged original project.
    """
    from .planning import require_board, package_records, validate_dossier
    generation_key = dossier['exploded'].get('generation_evidence_key')
    receipt_record = project.verify_evidence(state, generation_key)
    receipt = _read(project, _reference(receipt_record))
    request_record = receipt.get('request') if isinstance(receipt, dict) else None
    _reference(request_record)
    if 'exploded-image-request' in state['evidence']:
        validate_dossier(project, state, dossier, packages)
        return {'kind': 'EXISTING_ORIGINAL_DESIGN_GENERATION', 'source_project': str(project.root),
                'source_project_id': state['project_id'], 'board_ref': _reference(project.verify_evidence(state, 'construction-board')),
                'request': copy.deepcopy(project.verify_evidence(state, 'exploded-image-request')),
                'receipt': copy.deepcopy(receipt_record), 'import_lineage': [],
                'design_scope': 'ORIGINAL_APPROVED_INPUTS_ONLY'}
    if str(project.root) in visited or len(visited) >= 8:
        raise StudioError('Original generation import lineage is cyclic or exceeds V1 depth')
    imported_record = project.verify_evidence(state, 'approved-design-import')
    imported = _read(project, _reference(imported_record))
    events = _event(project, 'approved_design_context_imported', lambda row: _equal(row, imported))
    if (not isinstance(imported, dict) or imported.get('status') != 'EXACT_APPROVED_DESIGN_IMPORTED' or len(events) != 1 or
            not isinstance(imported.get('source_project'), str) or
            imported.get('asset_sha256') != digest(state['asset'])):
        raise StudioError('Missing original generation request needs an exact canonical legacy import')
    parent = Project(imported['source_project']); parent_state = _state(parent)
    parent_board = require_board(parent, parent_state); parent_packages = package_records(parent, parent_state)
    parent_record = parent.verify_evidence(parent_state, generation_key)
    if (not _equal(parent_board, board) or not _equal(parent_packages, packages) or
            not _equal(parent_record, receipt_record) or
            imported.get('files', {}).get(receipt_record['path']) != receipt_record['sha256']):
        raise StudioError('Original generation parent board, packages or copied receipt changed')
    parent_dossier = _read(parent, {'path': board['dossier_path'], 'sha256': board['dependencies'][board['dossier_path']]})
    if not _equal(parent_dossier, dossier):
        raise StudioError('Original generation parent dossier differs from the copied original')
    for name in ['references', 'construction']+['route.'+cid for cid in packages]:
        if (not _equal(parent_state['gates'].get(name), state['gates'].get(name)) or
                imported.get('human_decision_ids', {}).get(name) != state['gates'][name]['decision_id']):
            raise StudioError('Original generation parent human decision changed')
    origin = _generation_origin(parent, parent_state, parent_board, parent_packages, parent_dossier,
                                visited=(*visited, str(project.root)))
    origin['import_lineage'].insert(0, {'project': str(project.root), 'project_id': state['project_id'],
                                      'event_id': events[0][0], 'import_ref': _reference(imported_record)})
    return origin


def _decision(source, state, request):
    if not isinstance(request, dict) or set(request) != {'gate_name', 'decision_evidence_key'}:
        raise StudioError('Composition request requires only gate_name and decision_evidence_key')
    for value in request.values(): ident(value)
    if not request['gate_name'].startswith('pattern-variant.'):
        raise StudioError('Composition may preserve only a scoped pattern-variant human gate')
    origin, gate = _human(source, state, request['gate_name'])
    key = request['decision_evidence_key']; record = source.verify_evidence(state, key)
    if not _equal(gate['evidence'].get(key), record):
        raise StudioError('Pattern decision evidence is not bound to this exact human gate')
    reference = _reference(record); decision = _read(source, reference)
    if (not isinstance(decision, dict) or type(decision.get('version')) is not int or
            decision['version'] != 1 or decision.get('approved') is not True):
        raise StudioError('Pattern decision requires an explicit approved V1 document')
    status = decision.get('status'); scope = decision.get('approved_scope'); ids = decision.get('piece_ids')
    if (status not in ('TWO_SLEEVE_PATTERN_VARIANT_APPROVED', 'SCOPED_PATTERN_VARIANT_APPROVED') or
            not isinstance(scope, list) or not scope or any(not isinstance(v, str) or not v.strip() for v in scope) or len(scope) != len(set(scope)) or
            not isinstance(ids, list) or not ids or any(not isinstance(v, str) or not v.strip() for v in ids) or len(ids) != len(set(ids))):
        raise StudioError('Pattern decision needs a supported type and explicit unique review scope')
    expected = 'two_sleeve_pattern_shapes' if status == 'TWO_SLEEVE_PATTERN_VARIANT_APPROVED' else 'pattern_shapes'
    if expected not in scope or status == 'TWO_SLEEVE_PATTERN_VARIANT_APPROVED' and len(ids) != 2:
        raise StudioError('Pattern decision does not grant the declared shape review scope')
    if decision.get('statement') != gate['statement'] or decision.get('source_ref') != gate['source_ref']:
        raise StudioError('Pattern decision statement or conversation source differs from its human gate')
    refs = {field: _ref(decision.get(field)) for field in _REF_FIELDS}
    if len({ref['path'].casefold() for ref in [reference, *refs.values()]}) != len(refs)+1:
        raise StudioError('Pattern decision roles contain duplicate reference bindings')
    for ref in refs.values(): _read(source, ref, json_value=False)
    bound_roles = {'decision_ref': reference, **{field: refs[field] for field in _BOUND_ROLES}}
    for field, ref in bound_roles.items():
        matches = [record for record in gate['evidence'].values() if _equal(_reference(record), ref)]
        aliases = [record for record in gate['evidence'].values()
                   if _reference(record)['path'].casefold() == ref['path'].casefold()]
        if len(matches) != 1 or len(aliases) != 1:
            raise StudioError('Pattern '+field+' must bind one exact artifact in the same human gate')
    return decision, reference, origin, gate


def prepare_reviewed_pattern_composition(source, request):
    """Authenticate and calculate inputs; never writes files or project state."""
    from .planning import _validate_dossier_structure
    before = _codes(); state = _state(source)
    board, board_ref, packages, parents, base_gates = _base(source, state)
    decision, decision_ref, origin, gate = _decision(source, state, request)
    cid = decision.get('component_id')
    if cid not in packages or packages[cid]['manifest']['pipeline'] != 'PATTERN_SEWN':
        raise StudioError('Pattern review component is not an original sewn package')
    original_ref = {'path': board['dossier_path'], 'sha256': board['dependencies'][board['dossier_path']]}
    if not _equal(decision['original_dossier_ref'], original_ref):
        raise StudioError('Pattern decision original dossier differs from its approved board parent')
    original = _read(source, original_ref); candidate = _read(source, decision['candidate_dossier_ref'])
    # The original generation remains validated solely against original inputs.
    generation_origin = _generation_origin(source, state, board, packages, original)
    variant_file = _read(source, decision['variant_package_ref'], json_value=False)
    variant_manifest = inspect_package(variant_file)
    if (variant_manifest['asset_id'] != state['asset']['id'] or variant_manifest['component_id'] != cid or variant_manifest['pipeline'] != 'PATTERN_SEWN'):
        raise StudioError('Pattern variant package asset, component or route differs')
    with zipfile.ZipFile(inside(source.root, packages[cid]['path'])) as archive:
        garment = _parse(archive.read('garment.json'))
    with zipfile.ZipFile(variant_file) as archive:
        variant = _parse(archive.read('garment.json'))
    if any(row['id'] not in garment['pieces'] for row in original['components'][cid]['pieces']):
        raise StudioError('Original package and dossier component inventory differ')
    if any(pid not in garment['pieces'] for pid in decision['piece_ids']):
        raise StudioError('Pattern decision scope belongs to another component')
    package_comparison = verify_pattern_variant_scope(garment, variant, decision['piece_ids'])
    composition = compose_pattern_variant_dossier(original, candidate, decision['piece_ids'])
    override = dict(copy.deepcopy(decision['variant_package_ref']), manifest=variant_manifest)
    current_packages = copy.deepcopy(packages); current_packages[cid] = override
    sources, _, _ = _validate_dossier_structure(source, state, composition['dossier'], current_packages)
    files = {}
    def add(ref):
        ref = _ref(ref)
        if ref['path'] in files and files[ref['path']] != ref['sha256']:
            raise StudioError('Composition source identities contradict')
        files[ref['path']] = ref['sha256']
    add(board_ref); add(decision_ref)
    for path, value in board['dependencies'].items(): add({'path': path, 'sha256': value})
    for record in packages.values(): add(_reference(record))
    for ref in (decision[field] for field in _REF_FIELDS): add(ref)
    for rec in [*gate['evidence'].values(), *(record for parent in base_gates.values() for record in parent['evidence'].values())]: add(_reference(rec))
    # Retain the old receipt as an input. The ancestor request stays in its
    # canonical project; no new generation evidence slot is fabricated.
    add(_reference(source.verify_evidence(state, original['exploded']['generation_evidence_key'])))
    for path, value in sources.items(): add({'path': path, 'sha256': value})
    for path, value in files.items(): _read(source, {'path': path, 'sha256': value}, json_value=False)
    latest = _state(source)
    if (_codes() != before or not _equal(_base(source, latest)[0], board) or
            not _equal(_decision(source, latest, request)[3], gate) or
            not _equal(_generation_origin(source, latest, board, packages, original), generation_origin) or
            any(not _equal(latest['gates'].get(name), record) for name, record in base_gates.items())):
        raise StudioError('Composition source approvals or producer code changed during preparation')
    for path, value in files.items(): _read(source, {'path': path, 'sha256': value}, json_value=False)
    flags = {'qualification': 'NONE', 'construction': 'NOT_GRANTED', 'fitting': 'NOT_GRANTED',
             'permission': 'NOT_GRANTED', 'human_review': 'NOT_GRANTED',
             'image_scope': 'BASE_DESIGN_ONLY_SCOPED_REVIEW_SEPARATE'}
    template = dict(flags, version=1, kind=KIND, status='COMPOSED_INPUTS_ONLY',
        origin={'kind': 'calculated', 'source_project': str(source.root), 'source_project_id': state['project_id']},
        source_revision_observed=state['revision'], request=copy.deepcopy(request), base_board_ref=board_ref,
        base_decision_origins=parents, base_gate_records=base_gates,
        pattern_decision_origin=origin, pattern_gate_record=copy.deepcopy(gate), decision_ref=decision_ref,
        generation_origin=generation_origin,
        reviewed_piece_ids=copy.deepcopy(decision['piece_ids']), component_id=cid, input_files=files,
        package_comparison=package_comparison, dossier_comparison={k: v for k, v in composition.items() if k != 'dossier'},
        code_producers=before, output={'dossier_ref': None, 'packages': None})
    return dict(flags, status='COMPOSED_INPUTS_ONLY', files=files, sources=sources,
        extra_gates={request['gate_name']: copy.deepcopy(gate)}, extra_evidence=copy.deepcopy(gate['evidence']),
        package_overrides={cid: override}, composed_dossier=composition['dossier'], manifest_template=template)


def require_reviewed_pattern_composition(project, state, base_manifest, packages):
    """Replay a registered calculated proof and return its current source view."""
    from .planning import package_records, _validate_dossier_structure
    if not _equal(_state(project), state):
        raise StudioError('Calculated composition state is not the current canonical state')
    record = project.verify_evidence(state, KEY); reference = _reference(record)
    manifest = _read(project, reference)
    if (not isinstance(manifest, dict) or type(manifest.get('version')) is not int or
            manifest['version'] != 1 or manifest.get('kind') != KIND or
            not isinstance(manifest.get('origin'), dict) or manifest['origin'].get('kind') != 'calculated' or
            not isinstance(manifest['origin'].get('source_project'), str) or
            not manifest['origin']['source_project'].strip() or 'request' not in manifest):
        raise StudioError('Registered proof is not a typed calculated source composition')
    source = Project(manifest['origin']['source_project'])
    if source.root == project.root:
        raise StudioError('Calculated composition must retain a distinct original source project')
    replay = prepare_reviewed_pattern_composition(source, manifest['request'])
    expected = replay['manifest_template']; observed = copy.deepcopy(manifest)
    revision = observed.pop('source_revision_observed', None)
    expected = copy.deepcopy(expected); expected.pop('source_revision_observed')
    if type(revision) is not int or revision < 0:
        raise StudioError('Composition observed revision must be a nonnegative integer')
    output = observed.get('output')
    if not isinstance(output, dict) or set(output) != {'dossier_ref', 'packages'}:
        raise StudioError('Composition requires an exact output dossier and package inventory')
    expected['output'] = copy.deepcopy(output)
    if not _equal(observed, expected):
        raise StudioError('Calculated composition manifest differs from its authenticated replay')
    if digest(state['asset']) != digest(_state(source)['asset']):
        raise StudioError('Calculated composition belongs to another unchanged asset')
    parent = _read(source, manifest['base_board_ref'])
    if not _equal(base_manifest, parent):
        raise StudioError('Calculated composition base manifest differs from its original board')
    for name, gate in manifest['base_gate_records'].items():
        project.require_gate(state, name)
        if not _equal(state['gates'].get(name), gate):
            raise StudioError('Copied original human gate differs: '+name)
    for name, gate in replay['extra_gates'].items():
        project.require_gate(state, name)
        if not _equal(state['gates'].get(name), gate):
            raise StudioError('Copied pattern human gate differs from its source')
    board_record = project.verify_evidence(state, 'construction-board')
    if not _equal(_reference(board_record), manifest['base_board_ref']):
        raise StudioError('Calculated composition replaced the original construction board')
    for key, rec in replay['extra_evidence'].items():
        if not _equal(project.verify_evidence(state, key), rec):
            raise StudioError('Copied pattern evidence differs from its original record')
    for path, value in manifest['input_files'].items(): _read(project, {'path': path, 'sha256': value}, json_value=False)
    dossier_ref = _ref(output['dossier_ref'])
    original_paths = {path.casefold() for path in manifest['input_files']}
    if (dossier_ref['path'].casefold() in original_paths or reference['path'].casefold() in original_paths or
            dossier_ref['path'].casefold() == reference['path'].casefold()):
        raise StudioError('Calculated output cannot replace an original source or its proof')
    composed = _read(project, dossier_ref)
    if not _equal(composed, replay['composed_dossier']):
        raise StudioError('Calculated output dossier differs from exact source composition')
    actual = package_records(project, state)
    expected_packages = copy.deepcopy(_base(source, _state(source))[2]); expected_packages.update(replay['package_overrides'])
    if not _equal(actual, packages) or not _equal(actual, expected_packages) or not _equal(output['packages'], actual):
        raise StudioError('Calculated output packages differ from reviewed source packages')
    _validate_dossier_structure(project, state, composed, actual)
    latest_source = _state(source)
    source_base = _base(source, latest_source)
    original = _read(source, {'path': parent['dossier_path'], 'sha256': parent['dependencies'][parent['dossier_path']]})
    if (not _equal(_state(project), state) or _codes() != manifest['code_producers'] or
            not _equal(source_base[0], parent) or
            not _equal(_decision(source, latest_source, manifest['request'])[3], manifest['pattern_gate_record']) or
            not _equal(_generation_origin(source, latest_source, parent, source_base[2], original), manifest['generation_origin']) or
            any(not _equal(latest_source['gates'].get(name), gate) for name, gate in manifest['base_gate_records'].items())):
        raise StudioError('Calculated composition state or code changed during replay')
    for path, value in manifest['input_files'].items():
        _read(source, {'path': path, 'sha256': value}, json_value=False)
        _read(project, {'path': path, 'sha256': value}, json_value=False)
    view = copy.deepcopy(base_manifest)
    view.update(status='CALCULATED_SOURCE_COMPOSITION_VERIFIED', kind=KIND,
        dossier_path=dossier_ref['path'], dependencies={**manifest['input_files'], dossier_ref['path']: dossier_ref['sha256'], reference['path']: reference['sha256']},
        packages={cid: {'sha256': rec['sha256'], 'pipeline': rec['manifest']['pipeline']} for cid, rec in actual.items()},
        provenance={'kind': 'calculated', 'composition_ref': reference, 'base_board_ref': manifest['base_board_ref'],
                    'pattern_decision_origin': manifest['pattern_decision_origin'], 'reviewed_piece_ids': manifest['reviewed_piece_ids'],
                    'generation_origin': manifest['generation_origin']},
        qualification='NONE', construction='NOT_GRANTED', fitting='NOT_GRANTED', permission='NOT_GRANTED',
        image_scope='BASE_DESIGN_ONLY_SCOPED_REVIEW_SEPARATE')
    return view
