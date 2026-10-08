"""Canonical source adoption with an immutable, replayable V1 parent.

Only reviewed design bindings change. Blender, physical results and execution
permissions are outside this service. Historical V1 producers stay unchanged.
"""
import copy
from contextlib import ExitStack, closing
import json
import re
from pathlib import Path
import sqlite3
import time
import uuid

from .core import StudioError, atomic_json, canonical, digest, ident, inside, now, sha
from .reviewed_pattern_admission import (_base, _human, _parse, _ref, _reference, _state,
                                        prepare_reviewed_pattern_composition)
from .store import ACTIVE_JOBS, Project

KEY = 'reviewed-source-adoption'
REVALIDATION_KEY = 'reviewed-source-software-revalidation'
KIND = 'REVIEWED_SOURCE_ADOPTION'
MAX_FILE_BYTES = 64 * 1024 * 1024
MAX_MANIFEST_BYTES = 16 * 1024 * 1024
ACTIVE_WORK = {'PREPARING', 'PREPARED', 'RUNNING', 'EXECUTING', 'AWAITING_CONFIRMATION',
               'WAITING_RESULT', 'UNKNOWN_COMPLETION', 'SUBMITTING', 'WAITING_EXTERNAL',
               'SUBMISSION_UNKNOWN', 'WAITING_OUTPUTS', 'RECOVERY_REQUIRED', 'ROLLBACK_REQUIRED'}
GLOBAL_RESULTS = {'piece-completeness', 'assembly-plan', 'assembly-result', 'refinement-validation',
                  'silhouette-review', 'behavior-validation', 'final-validation', 'animated-delivery',
                  'export-validation'}


def _same(a, b):
    return canonical(a) == canonical(b)


def _codes():
    directory = Path(__file__).resolve().parent
    names = ('reviewed_source_adoption.py', 'reviewed_pattern_revisions.py',
             'reviewed_pattern_admission.py', 'pattern_variant_composition.py',
             'core.py', 'store.py', 'planning.py', 'packages.py', 'runs.py')
    return {'a3d/'+name: sha(directory/name) for name in names}


def _read(project, reference, json_value=True):
    reference = _ref(reference)
    try:
        file = inside(project.root, reference['path'])
        if file.stat().st_size > MAX_FILE_BYTES:
            raise StudioError('Source adoption dependency exceeds its bounded file size')
        raw = file.read_bytes()
    except OSError as error:
        raise StudioError('Source adoption dependency is missing or unreadable') from error
    import hashlib
    if len(raw) > MAX_FILE_BYTES or hashlib.sha256(raw).hexdigest() != reference['sha256']:
        raise StudioError('Source adoption dependency changed or exceeds its bounded file size')
    return _parse(raw) if json_value else file


def _events(project, kind, db=None):
    if db is not None:
        return [(row[0], _parse(row[1])) for row in db.execute('SELECT id,doc FROM events WHERE kind=?', (kind,))]
    with closing(sqlite3.connect(project.db.resolve().as_uri()+'?mode=ro', uri=True)) as connection:
        connection.execute('PRAGMA query_only=ON')
        return _events(project, kind, connection)


def _parent_baseline(project, snapshot):
    """Replay the real original ancestor; never impersonate a prior state."""
    if not isinstance(snapshot, dict) or set(snapshot) != {'board', 'packages', 'composition_ref'}:
        raise StudioError('Source adoption needs its exact immutable V1 parent snapshot')
    proof = _read(project, snapshot['composition_ref'])
    if proof.get('version') != 1 or proof.get('kind') != 'CALCULATED_SOURCE_COMPOSITION':
        raise StudioError('Initial source adoption supports a calculated V1 parent only')
    source = Project(proof['origin']['source_project'])
    if source.root == project.root:
        raise StudioError('Source adoption V1 parent must retain its distinct real ancestor')
    if digest(_state(project)['asset']) != digest(_state(source)['asset']):
        raise StudioError('Source adoption V1 parent belongs to another unchanged asset')
    replay = prepare_reviewed_pattern_composition(source, proof['request'])
    observed = copy.deepcopy(proof); expected = copy.deepcopy(replay['manifest_template'])
    revision = observed.pop('source_revision_observed', None); expected.pop('source_revision_observed')
    if type(revision) is not int or revision < 0:
        raise StudioError('Source adoption parent revision observation is malformed')
    expected['output'] = copy.deepcopy(proof['output'])
    if not _same(observed, expected):
        raise StudioError('Source adoption parent proof differs from authenticated ancestor replay')
    parent_packages = copy.deepcopy(_base(source, _state(source))[2])
    parent_packages.update(copy.deepcopy(replay['package_overrides']))
    if not _same(snapshot['packages'], parent_packages) or not _same(proof['output']['packages'], parent_packages):
        raise StudioError('Source adoption parent package inventory differs from scoped ancestor decisions')
    for name, gate in {**proof['base_gate_records'], **replay['extra_gates']}.items():
        project.require_gate(_state(project), name)
        if not _same(_state(project)['gates'].get(name), gate):
            raise StudioError('Source adoption inherited design gate changed: '+name)
    for key, record in replay['extra_evidence'].items():
        if not _same(project.verify_evidence(_state(project), key), record):
            raise StudioError('Source adoption inherited pattern evidence changed')
    for path, identity in proof['input_files'].items():
        _read(project, {'path': path, 'sha256': identity}, False)
        _read(source, {'path': path, 'sha256': identity}, False)
    parent = _read(project, proof['base_board_ref'])
    if not _same(parent, _read(source, proof['base_board_ref'])):
        raise StudioError('Source adoption original construction board changed')
    dossier_ref = proof['output']['dossier_ref']
    if not _same(_read(project, dossier_ref), replay['composed_dossier']):
        raise StudioError('Source adoption parent dossier differs from scoped ancestor composition')
    for record in parent_packages.values(): _read(project, _reference(record), False)
    view = copy.deepcopy(parent)
    view.update(status='CALCULATED_SOURCE_COMPOSITION_VERIFIED', kind='CALCULATED_SOURCE_COMPOSITION',
        dossier_path=dossier_ref['path'],
        dependencies={**proof['input_files'], dossier_ref['path']: dossier_ref['sha256'],
                      snapshot['composition_ref']['path']: snapshot['composition_ref']['sha256']},
        packages={cid: {'sha256': row['sha256'], 'pipeline': row['manifest']['pipeline']} for cid, row in parent_packages.items()},
        provenance={'kind': 'calculated', 'composition_ref': snapshot['composition_ref'],
                    'base_board_ref': proof['base_board_ref'], 'pattern_decision_origin': proof['pattern_decision_origin'],
                    'reviewed_piece_ids': proof['reviewed_piece_ids'], 'generation_origin': proof['generation_origin']},
        qualification='NONE', construction='NOT_GRANTED', fitting='NOT_GRANTED', permission='NOT_GRANTED',
        image_scope='BASE_DESIGN_ONLY_SCOPED_REVIEW_SEPARATE')
    if not _same(snapshot['board'], view):
        raise StudioError('Source adoption frozen parent view is not its authenticated V1 source view')
    return {'board': view, 'packages': parent_packages}, proof


def _roles(revision):
    gate = revision['human_gate_record']; roles = {}
    for role, ref in revision['epoch_basis']['roles'].items():
        matches = [key for key, row in gate['evidence'].items() if _same(_reference(row), ref)]
        if len(matches) != 1:
            raise StudioError('Source adoption role does not map to one exact human evidence key')
        roles[role] = matches[0]
    if set(roles) != {'proposal', 'review', 'candidate_dossier', 'variant_package'}:
        raise StudioError('Source adoption human role inventory is incomplete')
    return roles


def _producer_comparison(historical, current):
    """Only hash changes within the same explicit producer inventory are eligible."""
    if (not isinstance(historical, dict) or not historical or set(historical) != set(current) or
            any(not isinstance(value, str) or re.fullmatch('[0-9a-f]{64}', value) is None
                for value in [*historical.values(), *current.values()])):
        raise StudioError('Source software revalidation requires the same valid producer inventory')
    return {'historical': copy.deepcopy(historical), 'current': copy.deepcopy(current),
            'changed_paths': sorted(name for name in current if historical[name] != current[name])}


def _ancestor_roots(project, proof):
    roots = {Project(proof['origin']['source_project']).root}
    origins = [*proof['base_decision_origins'].values(), proof['pattern_decision_origin']]
    for origin in origins:
        roots.add(Project(origin['project']).root)
        roots.update(Project(row['project']).root for row in origin.get('import_lineage', []))
    generation = proof['generation_origin']; roots.add(Project(generation['source_project']).root)
    roots.update(Project(row['project']).root for row in generation.get('import_lineage', []))
    roots.discard(project.root)
    if len(roots) > 8:
        raise StudioError('Source adoption ancestor reservation budget exceeded')
    return sorted(roots, key=lambda path: str(path).casefold())


def _prepared_calculation(project, reference, baseline=None, *, software_replay=False):
    from .reviewed_pattern_revisions import calculate_reviewed_pattern_revision
    revision = _read(project, reference)
    if revision.get('status') != 'DESIGN_SOURCE_REVISION_PREPARED' or revision.get('source_revision') != 'ADOPTION_REQUIRED':
        raise StudioError('Source adoption requires exact prepared design data')
    gate_name = revision['human_decision_origin']['gate_name']
    roles = _roles(revision)
    calculated = calculate_reviewed_pattern_revision(project, gate_name, roles, baseline=baseline)
    observed = {key: value for key, value in revision.items() if key != 'outputs'}
    expected = calculated['result']
    comparison = _producer_comparison(observed.get('code_producers'), expected['code_producers'])
    if software_replay:
        observed = {key: value for key, value in observed.items() if key != 'code_producers'}
        expected = {key: value for key, value in expected.items() if key != 'code_producers'}
    if not _same(observed, expected):
        raise StudioError('Source adoption prepared revision differs from current authenticated replay')
    outputs = revision.get('outputs')
    if not isinstance(outputs, dict) or set(outputs) != {'effective-dossier.json', 'effective-packages.json'}:
        raise StudioError('Source adoption requires exact prepared dossier/package output references')
    if (not _same(_read(project, outputs['effective-dossier.json']), calculated['dossier']) or
            not _same(_read(project, outputs['effective-packages.json']), calculated['packages'])):
        raise StudioError('Source adoption prepared output differs from its calculated source revision')
    calculated['producer_comparison'] = comparison
    return revision, calculated


def _preflight(project, state, revision_ref):
    from .reviewed_pattern_revisions import _preflight_dependencies, MAX_SECONDS
    started = time.monotonic()
    def check():
        if time.monotonic()-started > MAX_SECONDS:
            raise StudioError('Source adoption preflight time budget exhausted')
    revision = _read(project, revision_ref)
    roles = _roles(revision)
    try:
        _preflight_dependencies(project, state, revision['human_decision_origin']['gate_name'], roles, check)
    except OSError as error:
        raise StudioError('Source adoption preflight dependency is missing or unreadable') from error


def _depends(value, identities):
    pending = [value]; count = 0
    while pending:
        count += 1
        if count > 1_000_000:
            raise StudioError('Source adoption dependency walk exceeds its budget')
        item = pending.pop()
        if isinstance(item, dict): pending.extend(item.values())
        elif isinstance(item, list): pending.extend(item)
        elif isinstance(item, str) and item in identities: return True
    return False


def _run_rows(db):
    if not db.execute("SELECT 1 FROM sqlite_master WHERE type='table' AND name='runs'").fetchone(): return []
    return [_parse(row[0]) for row in db.execute('SELECT doc FROM runs')]


def _no_active_work(state, db):
    if state.get('pending_blender_operation'):
        raise StudioError('Source adoption requires recovery of the pending Blender operation')
    for raw, in db.execute('SELECT doc FROM jobs'):
        if _parse(raw).get('status') in ACTIVE_JOBS:
            raise StudioError('Source adoption requires all provider jobs to be settled')
    for run in _run_rows(db):
        if run.get('status') in ACTIVE_WORK:
            raise StudioError('Source adoption cannot change bindings during active work')
        for unit in run.get('units', []):
            if unit.get('status') in ACTIVE_WORK or any(attempt.get('status') in ACTIVE_WORK for attempt in unit.get('attempts', [])):
                raise StudioError('Source adoption requires all active attempts to be settled or recovered')


def _invalidations(project, state, db, affected):
    identities = {ref['sha256'] for ref in affected}; invalid = {}
    cache = {}; memo = {}; seen_paths = {}; input_bytes = 0
    started = time.monotonic()
    def depends_reference(reference):
        """Follow only explicit authenticated JSON refs, with shared budgets."""
        nonlocal input_bytes
        reference = _reference(reference)
        start = (reference['path'], reference['sha256'])
        pending = [(reference, 0)]; visited = set()
        while pending:
            if time.monotonic()-started > 120:
                raise StudioError('Source adoption invalidation walk exhausted its time budget')
            ref, depth = pending.pop(); token = (ref['path'], ref['sha256'])
            if token in visited: continue
            if depth > 32:
                raise StudioError('Source adoption invalidation dependency depth budget exhausted')
            folded = ref['path'].casefold()
            if folded in seen_paths and seen_paths[folded] != token:
                raise StudioError('Source adoption invalidation refs have a case alias or contradictory identity')
            seen_paths[folded] = token; visited.add(token)
            if len(visited) > 256 or len(seen_paths) > 256:
                raise StudioError('Source adoption invalidation dependency file budget exhausted')
            if ref['sha256'] in identities or memo.get(token) is True:
                memo[start] = True; return True
            if memo.get(token) is False or not ref['path'].lower().endswith('.json'): continue
            if token not in cache:
                file = inside(project.root, ref['path']); size = file.stat().st_size
                if size > MAX_FILE_BYTES or input_bytes+size > 128*1024*1024:
                    raise StudioError('Source adoption invalidation dependency byte budget exhausted')
                value = _read(project, ref); input_bytes += size
                cache[token] = value
            value = cache[token]
            if _depends(value, identities): memo[start] = True; return True
            stack = [value]; count = 0
            while stack:
                count += 1
                if count > 1_000_000:
                    raise StudioError('Source adoption invalidation JSON node budget exhausted')
                item = stack.pop()
                if isinstance(item, dict):
                    if {'path', 'sha256'} <= item.keys(): pending.append((_reference(item), depth+1))
                    else: stack.extend(item.values())
                elif isinstance(item, list): stack.extend(item)
        # An exhausted closed graph has no dependent node, including cycles.
        for token in visited: memo[token] = False
        return False
    protected_names = {'references', 'construction'}
    protected_prefixes = ('route.', 'pattern-variant.', 'ease-design.', 'patronage.', 'patronage-sizing.', 'body')
    protected = {'construction-board', 'pipeline-proposal', 'approved-design-import',
                 'reviewed-pattern-composition', 'exploded-image-generation'}
    for name, gate in state['gates'].items():
        if name in protected_names or name.startswith(protected_prefixes): protected.update(gate.get('evidence', {}))
    for key, record in state['evidence'].items():
        if key in protected or key.startswith(('body', 'patronage', 'pattern-variant.', 'sleeve-variant.')): continue
        matches = key in GLOBAL_RESULTS or depends_reference(record)
        if matches: invalid[key] = copy.deepcopy(record)
    runs = []
    for run in _run_rows(db):
        dependent = _depends(run, identities)
        if not dependent:
            # create_run stores argument file identities in unit.inputs;
            # historical receipt/output projections remain history, not inputs.
            declared = list(run.get('inputs', []))
            if isinstance(run.get('specification'), dict): declared.append(run['specification'])
            for unit in run.get('units', []):
                declared.extend(unit.get('inputs', []))
                for attempt in unit.get('attempts', []): declared.extend(attempt.get('inputs', []))
            if len(declared) > 256:
                raise StudioError('Source adoption run input reference budget exhausted')
            for ref in declared:
                if depends_reference(ref): dependent = True; break
        if dependent: runs.append(run['run_id'])
    return invalid, runs


def adopt_reviewed_source_revision(project, revision_path, expected_parent_epoch, request_key):
    """Atomically adopt reviewed source bindings; grant no native permission."""
    ident(request_key)
    if not isinstance(expected_parent_epoch, str) or len(expected_parent_epoch) != 64:
        raise StudioError('Source adoption needs an exact expected parent epoch')
    revision_file = inside(project.root, revision_path)
    revision_ref = {'path': revision_path, 'sha256': sha(revision_file)}
    request = {'revision_ref': revision_ref, 'expected_parent_epoch': expected_parent_epoch, 'request_key': request_key}
    matches = [row for _, row in _events(project, 'reviewed_source_revision_adopted') if row.get('request', {}).get('request_key') == request_key]
    if matches:
        if len(matches) != 1 or not _same(matches[0]['request'], request):
            raise StudioError('Source adoption request key reused with different exact arguments')
        state = _state(project)
        from .planning import package_records
        base = _read(project, _reference(project.verify_evidence(state, 'construction-board')))
        require_reviewed_source_adoption(project, state, base, package_records(project, state))
        return copy.deepcopy(matches[0]['receipt'])
    state = _state(project)
    if state['stage'] != 'RECONSTRUCTING' or KEY in state['evidence']:
        raise StudioError('Initial source adoption requires RECONSTRUCTING with an existing V1 parent')
    from .planning import require_board, package_records
    _preflight(project, state, revision_ref)
    board = require_board(project, state); packages = package_records(project, state)
    snapshot = {'board': board, 'packages': packages,
                'composition_ref': _reference(project.verify_evidence(state, 'reviewed-pattern-composition'))}
    baseline, proof = _parent_baseline(project, snapshot)
    revision, calculation = _prepared_calculation(project, revision_ref, baseline)
    if revision['parent_source_epoch'] != expected_parent_epoch:
        raise StudioError('Source adoption expected parent epoch differs from the exact current design')
    cid = revision['component_id']; affected = [revision['epoch_basis']['parent']['dossier_ref'], _reference(packages[cid])]
    codes = _codes()
    roots = _ancestor_roots(project, proof)
    with ExitStack() as reservations:
        for root in sorted(roots, key=lambda path: str(path).casefold()): reservations.enter_context(Project(root).transaction())
        with project.transaction() as db:
            current = project.state(db)
            if not _same(current, state): raise StudioError('Source adoption canonical parent changed before its atomic reservation')
            _no_active_work(current, db)
            calculation['recheck'](); calculation['check_budget']()
            if _codes() != codes or not _same(_parent_baseline(project, snapshot)[0], baseline):
                raise StudioError('Source adoption parent/code changed before admission')
            invalid, invalid_runs = _invalidations(project, current, db, affected)
            directory = project.data/'evidence'/('reviewed-source-adoption-'+uuid.uuid4().hex)
            directory.mkdir(parents=True, exist_ok=False)
            snapshot_path = (directory/'parent.json').relative_to(project.root).as_posix()
            atomic_json(directory/'parent.json', snapshot)
            snapshot_ref = {'path': snapshot_path, 'sha256': sha(directory/'parent.json')}
            manifest = {'version': 2, 'kind': KIND, 'status': 'REVIEWED_SOURCE_INPUTS_ADOPTED',
                'project_id': current['project_id'], 'asset_sha256': digest(current['asset']),
                'request': request, 'parent_snapshot_ref': snapshot_ref, 'revision_ref': revision_ref,
                'source_epoch': revision['source_epoch'], 'parent_epoch': expected_parent_epoch,
                'effective_dossier_ref': revision['outputs']['effective-dossier.json'],
                'effective_packages': copy.deepcopy(calculation['packages']),
                'generation_origin': copy.deepcopy(proof['generation_origin']),
                'reviewed_piece_ids': copy.deepcopy(revision['reviewed_piece_ids']), 'component_id': cid,
                'code_producers': codes, 'affected_refs': affected,
                'invalidated_evidence': invalid, 'invalidated_run_ids': invalid_runs,
                'qualification': 'NONE', 'fitting': 'NOT_GRANTED', 'permission': 'NOT_GRANTED',
                'image_scope': 'BASE_DESIGN_ONLY_SCOPED_REVIEW_SEPARATE', 'created_at': now()}
            if len(canonical(manifest)) > MAX_MANIFEST_BYTES:
                raise StudioError('Source adoption manifest exceeds its bounded output size')
            atomic_json(directory/'manifest.json', manifest)
            active_record = {'path': (directory/'manifest.json').relative_to(project.root).as_posix(),
                             'sha256': sha(directory/'manifest.json'), 'recorded_at': now()}
            # Revalidate after artifact writes and before the only source event.
            calculation['recheck'](); calculation['check_budget']()
            _read(project, snapshot_ref); _read(project, _reference(active_record))
            if _codes() != codes or not _same(project.state(db), current):
                raise StudioError('Source adoption canonical parent/code changed before commit')
            current['components'][cid]['package'] = copy.deepcopy(calculation['packages'][cid])
            current['components'][cid]['stage'] = 'PACKAGED'
            for field in ('reconstruction', 'reconstruction_evidence'): current['components'][cid].pop(field, None)
            for key in invalid: current['evidence'].pop(key)
            current['evidence'][KEY] = active_record
            current['source_epoch'] = revision['source_epoch']
            current['source_adoption'] = {'manifest_ref': _reference(active_record), 'request_key': request_key,
                                         'parent_epoch': expected_parent_epoch, 'source_epoch': revision['source_epoch']}
            from .runs import invalidate_source_runs
            invalidate_source_runs(project, db, invalid_runs, expected_parent_epoch, revision['source_epoch'], request_key)
            receipt = {'status': 'REVIEWED_SOURCE_INPUTS_ADOPTED', 'source_epoch': revision['source_epoch'],
                       'parent_epoch': expected_parent_epoch, 'manifest_ref': _reference(active_record),
                       'reviewed_piece_ids': revision['reviewed_piece_ids'], 'component_id': cid,
                       'invalidated_evidence_keys': sorted(invalid), 'invalidated_run_ids': invalid_runs,
                       'qualification': 'NONE', 'fitting': 'NOT_GRANTED', 'permission': 'NOT_GRANTED'}
            project.save(db, current, 'reviewed_source_revision_adopted',
                         {'request': request, 'active_record': active_record, 'receipt': receipt,
                          'parent_snapshot_ref': snapshot_ref, 'affected_refs': affected,
                          'invalidated_evidence': invalid, 'invalidated_run_ids': invalid_runs})
    return receipt


def _verify_reviewed_source_adoption(project, state, base_manifest, packages, *, preparing_revalidation=False):
    """Verify current admission using immutable parent data and actual gates."""
    from .planning import package_records, _validate_dossier_structure
    if not _same(_state(project), state): raise StudioError('Source adoption requires current canonical state')
    record = project.verify_evidence(state, KEY); manifest = _read(project, _reference(record))
    codes = _codes()
    if (manifest.get('version') != 2 or manifest.get('kind') != KIND or manifest.get('status') != 'REVIEWED_SOURCE_INPUTS_ADOPTED' or
            manifest.get('project_id') != state['project_id'] or manifest.get('asset_sha256') != digest(state['asset'])):
        raise StudioError('Source adoption manifest identity or producer code is stale')
    producer_comparison = _producer_comparison(manifest.get('code_producers'), codes)
    rows = [row for _, row in _events(project, 'reviewed_source_revision_adopted') if row.get('request') == manifest.get('request')]
    if (len(rows) != 1 or not _same(rows[0]['active_record'], record) or
            not _same(rows[0]['parent_snapshot_ref'], manifest['parent_snapshot_ref']) or
            not _same(rows[0]['invalidated_evidence'], manifest['invalidated_evidence']) or
            not _same(rows[0]['invalidated_run_ids'], manifest['invalidated_run_ids'])):
        raise StudioError('Source adoption manifest lacks its exact canonical admission event')
    binding = {'manifest_ref': _reference(record), 'request_key': manifest['request']['request_key'],
               'parent_epoch': manifest['parent_epoch'], 'source_epoch': manifest['source_epoch']}
    if state.get('source_epoch') != manifest['source_epoch'] or not _same(state.get('source_adoption'), binding):
        raise StudioError('Source adoption active epoch differs from its canonical event')
    snapshot = _read(project, manifest['parent_snapshot_ref'])
    _preflight(project, state, manifest['revision_ref'])
    baseline, proof = _parent_baseline(project, snapshot)
    if not _same(base_manifest, _read(project, proof['base_board_ref'])):
        raise StudioError('Source adoption replaced its original reviewed construction board')
    revision, calculation = _prepared_calculation(project, manifest['revision_ref'], baseline, software_replay=True)
    if (manifest['source_epoch'] != revision['source_epoch'] or manifest['parent_epoch'] != revision['parent_source_epoch'] or
            manifest['component_id'] != revision['component_id'] or manifest['reviewed_piece_ids'] != revision['reviewed_piece_ids'] or
            not _same(manifest['generation_origin'], proof['generation_origin']) or
            not _same(manifest['effective_dossier_ref'], revision['outputs']['effective-dossier.json']) or
            not _same(manifest['effective_packages'], calculation['packages']) or
            not _same(package_records(project, state), calculation['packages']) or not _same(packages, calculation['packages'])):
        raise StudioError('Source adoption effective sources differ from exact scoped replay')
    dossier = _read(project, manifest['effective_dossier_ref'])
    if not _same(dossier, calculation['dossier']): raise StudioError('Source adoption effective dossier changed')
    _validate_dossier_structure(project, state, dossier, packages)
    calculation['recheck'](); calculation['check_budget']()
    if _codes() != codes or not _same(_state(project), state):
        raise StudioError('Source adoption canonical state or verification code changed during replay')
    replay = {'version': 1, 'status': 'EXACT_DESIGN_REPLAY_UNDER_CURRENT_SOFTWARE',
        'project_id': state['project_id'], 'adoption_ref': _reference(record),
        'revision_ref': manifest['revision_ref'], 'source_epoch': manifest['source_epoch'],
        'adoption_producers': producer_comparison, 'revision_producers': calculation['producer_comparison'],
        'design_result_sha256': digest({k: v for k, v in calculation['result'].items() if k != 'code_producers'}),
        'effective_dossier_sha256': digest(calculation['dossier']), 'effective_packages_sha256': digest(calculation['packages']),
        'comparison': 'ALL_DESIGN_FIELDS_AND_OUTPUTS_IDENTICAL_EXCEPT_PRODUCER_HASHES',
        'production_evidence': 'NOT_REVALIDATED', 'qualification': 'NONE', 'fitting': 'NOT_GRANTED', 'permission': 'NOT_GRANTED'}
    changed = producer_comparison['changed_paths'] or calculation['producer_comparison']['changed_paths']
    if changed and not preparing_revalidation:
        if REVALIDATION_KEY not in state['evidence']:
            raise StudioError('Source adoption software changed; run studio_revalidate_source_adoption before production')
        refreshed = project.verify_evidence(state, REVALIDATION_KEY)
        saved = _read(project, _reference(refreshed))
        events = [row for _, row in _events(project, 'reviewed_source_adoption_revalidated')
                  if _same(row.get('active_record'), refreshed)]
        if (not _same(saved, replay) or len(events) != 1 or
                events[0].get('replay_sha256') != digest(replay)):
            raise StudioError('Source adoption software revalidation is stale or lacks its canonical event')
    view = copy.deepcopy(baseline['board'])
    view.update(status='REVIEWED_SOURCE_ADOPTION_VERIFIED', kind=KIND,
        dossier_path=manifest['effective_dossier_ref']['path'],
        dependencies={**view['dependencies'], **revision['input_files'],
                      manifest['effective_dossier_ref']['path']: manifest['effective_dossier_ref']['sha256'],
                      record['path']: record['sha256'],
                      manifest['parent_snapshot_ref']['path']: manifest['parent_snapshot_ref']['sha256'],
                      manifest['revision_ref']['path']: manifest['revision_ref']['sha256']},
        packages={cid: {'sha256': row['sha256'], 'pipeline': row['manifest']['pipeline']} for cid, row in packages.items()},
        source_epoch=manifest['source_epoch'], qualification='NONE', fitting='NOT_GRANTED', permission='NOT_GRANTED',
        provenance={'kind': 'calculated', 'adoption_ref': _reference(record), 'parent_snapshot_ref': manifest['parent_snapshot_ref'],
                    'generation_origin': manifest['generation_origin'], 'reviewed_piece_ids': manifest['reviewed_piece_ids']})
    if changed and not preparing_revalidation:
        view['provenance']['software_revalidation_ref'] = _reference(refreshed)
        view['dependencies'][refreshed['path']] = refreshed['sha256']
    return view, replay, _ancestor_roots(project, proof)


def require_reviewed_source_adoption(project, state, base_manifest, packages):
    return _verify_reviewed_source_adoption(project, state, base_manifest, packages)[0]


def revalidate_source_adoption(project, output_dir):
    """Append a software attestation only after a full, identical design replay.

    Never modifies the adoption, its source epoch, packages, human gates or
    production results. The normal verifier still recalculates the full proof.
    """
    from .core import relative
    from .planning import package_records
    relative(output_dir)
    if not output_dir.startswith('preparation/') or output_dir == 'preparation/':
        raise StudioError('Source software revalidation requires a fresh preparation directory')
    output = inside(project.root, output_dir, False)
    if output.exists() or (output.parent.exists() and any(
            p.name.casefold() == output.name.casefold() for p in output.parent.iterdir())):
        raise StudioError('Preserve the existing software revalidation directory')
    state = _state(project)
    if state['stage'] != 'RECONSTRUCTING':
        raise StudioError('Source software revalidation requires RECONSTRUCTING')
    base = _read(project, _reference(project.verify_evidence(state, 'construction-board')))
    _, replay, roots = _verify_reviewed_source_adoption(project, state, base, package_records(project, state),
                                                       preparing_revalidation=True)
    with ExitStack() as reservations:
        for root in roots:
            reservations.enter_context(Project(root).transaction())
        with project.transaction() as db:
            current = project.state(db)
            if not _same(current, state):
                raise StudioError('Source software revalidation canonical state changed before recording')
            _no_active_work(current, db)
            # Recheck under the same ancestor reservations as source adoption.
            _, repeated, observed_roots = _verify_reviewed_source_adoption(
                project, current, base, package_records(project, current), preparing_revalidation=True)
            if not _same(repeated, replay) or observed_roots != roots:
                raise StudioError('Source software revalidation changed during recording')
            output.mkdir(parents=True, exist_ok=False)
            path = output/'revalidation.json'
            atomic_json(path, replay)
            record = {'path': path.relative_to(project.root).as_posix(), 'sha256': sha(path), 'recorded_at': now()}
            # Files and code are not protected by SQLite reservations: verify
            # them again after writing and before activating the attestation.
            _, after_write, final_roots = _verify_reviewed_source_adoption(
                project, current, base, package_records(project, current), preparing_revalidation=True)
            if (not _same(after_write, replay) or final_roots != roots or
                    not _same(project.state(db), current) or not _same(_read(project, _reference(record)), replay)):
                raise StudioError('Source software revalidation changed after writing')
            current['evidence'][REVALIDATION_KEY] = record
            project.save(db, current, 'reviewed_source_adoption_revalidated',
                         {'active_record': record, 'replay_sha256': digest(replay)})
    return {**replay, 'manifest_ref': _reference(record), 'source_bindings': 'UNCHANGED',
            'human_decisions': 'UNCHANGED', 'scene': 'UNCHANGED'}
