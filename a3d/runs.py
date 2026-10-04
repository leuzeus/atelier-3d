"""Canonical bounded run journals; no Blender execution or arbitrary receipts.

The four public functions operate on Project. The record_native_run_* hooks
are internal native-dispatch callbacks, never MCP tools or user evidence imports.
They register exact results in SQLite events before a receipt may advance a run.
An interrupted unit resumes at its entry checkpoint, never at an inferred
continuous Cloth state. Existing Project and guard admissions remain mandatory.
"""
import copy
import ast
import json
import math
import sqlite3
import time
import uuid
from contextlib import closing
from datetime import datetime
from pathlib import Path

from .core import ROOT, StudioError, atomic_json, canonical, contract, digest, ident, inside, now, sha
from .run_diagnostics import diagnose_run

KINDS = {'garment', 'comfy', 'material_bench', 'motion', 'export'}
FAILED_RESULTS = {'FAIL', 'FAILED', 'REFUSED', 'NEEDS_CORRECTION', 'NEEDS_CLARIFICATION',
                  'INCOMPLETE', 'NOT_EXECUTED', 'ROLLBACK_REQUIRED'}
KNOWN_RESULTS = {'PASS', 'READY', 'COMPLETED', 'SUCCEEDED', 'SUCCESS', 'PREPARED', 'NOT_QUALIFIED',
                 'GEOMETRY_ONLY', 'HEIGHT_ONLY', 'REVIEW_REQUIRED', 'CREATED', 'CONFIGURED', 'EXPORTED'}
OPERATION_MODULES = {
    'inspect': [], 'prepare': [], 'resume': [], 'restore_checkpoint': [], 'assemble': [], 'garment': ['blender/sewing.py'],
    'run_script': ['blender/sewing.py'], 'verify_legacy_import': ['blender/legacy.py'],
    'frame_view': ['blender/viewport.py'], 'prepare_body_target': ['blender/body_target.py'],
    'inspect_body_source': ['blender/body_source.py'], 'prepare_body_reference': ['blender/body_source.py'],
    'prepare_fitting_envelope': ['blender/fitting_envelope.py'], 'prepare_fitting_pose': ['blender/fitting_pose.py'],
    'inspect_garment_fit': ['blender/fitting.py'], 'propose_pattern_adjustment': ['blender/fitting.py'],
    'inspect_sewing_placement': ['blender/placement.py'], 'inspect_garment_failure': ['a3d/garment_rejections.py'],
    'inspect_sewing_failure': ['a3d/sewing_diagnostics.py'],
    'start_clean_construction': ['blender/clean_construction.py'], 'recover_clean_construction': ['blender/clean_construction.py'],
    'introduce_fitting_context': ['blender/clean_construction.py'], 'simulate_sewn': ['blender/sewing.py'],
    'freeze_sewn': ['blender/sewing.py'], 'prepare_sewn_stage': ['blender/sewn_stages.py'],
    'apply_sewn_result': ['blender/sewn_stages.py'], 'prepare_pattern_assembly': ['blender/pattern_preparation.py'],
    'transition_pattern_assembly': ['blender/pattern_assembly.py'], 'submit_workflow': ['a3d/comfy.py'],
    'prepare_body_motion': ['blender/body_motion.py'], 'render_asset_review': ['blender/delivery.py'],
    'advance_textile_program': ['blender/textile_executor.py'], 'transition_textile_group': ['blender/textile_group.py'],
    'run_material_bench': ['a3d/material_bench.py'], 'inspect_dressing_plan': ['a3d/dressing.py'],
    'export_blender_animation': ['blender/asset_export.py'], 'prepare_asset_finishing': ['blender/asset_finishing.py'],
    'inspect_reconstructed_part': ['blender/part_preparation.py'], 'run_garment_motion': ['blender/garment_motion.py'],
    'prepare_reconstructed_part': ['blender/part_preparation.py'],
    'introduce_body_target': ['blender/body_context.py'],
    'compose_animated_delivery': ['blender/animated_delivery.py'],
}
COMMON_CODE_PATHS = ['a3d/runs.py', 'a3d/run_diagnostics.py', 'a3d/core.py', 'a3d/store.py',
    'a3d/guard.py', 'a3d/planning.py', 'a3d/lifecycle.py', 'blender/bootstrap.py',
    'blender/operations.py', 'schemas/run.schema.json']


def _migrate(db):
    db.execute('CREATE TABLE IF NOT EXISTS runs (id TEXT PRIMARY KEY, request_key TEXT UNIQUE NOT NULL, doc TEXT NOT NULL)')


def _table(db):
    return db.execute("SELECT 1 FROM sqlite_master WHERE type='table' AND name='runs'").fetchone() is not None


def _load(db, run_id):
    ident(run_id)
    row = db.execute('SELECT doc FROM runs WHERE id=?', (run_id,)).fetchone() if _table(db) else None
    if not row:
        raise StudioError('Run is not owned by this project')
    return json.loads(row[0])


def _save(db, run, kind, detail):
    run['revision'] += 1
    run['updated_at'] = now()
    db.execute('UPDATE runs SET doc=? WHERE id=?', (canonical(run).decode(), run['run_id']))
    return db.execute('INSERT INTO events(created_at,kind,doc) VALUES (?,?,?)',
               (now(), kind, canonical(dict(detail, run_id=run['run_id'])).decode())).lastrowid


def _code_inventory(paths, traverse=True):
    files = {}; pending = list(paths)
    while pending:
        relative = pending.pop()
        if relative in files: continue
        path = inside(ROOT, relative)
        if not path.is_file() or path.suffix not in ('.py', '.json'):
            raise StudioError('Run code paths must identify installed Python or schema files')
        files[relative] = sha(path)
        if not traverse or path.suffix != '.py' or relative in COMMON_CODE_PATHS: continue
        tree = ast.parse(path.read_text(encoding='utf-8-sig'))
        for node in ast.walk(tree):
            if isinstance(node, ast.Import): modules = [item.name for item in node.names]
            elif isinstance(node, ast.ImportFrom):
                package = relative.rsplit('/', 1)[0].replace('/', '.')
                base = package.split('.')[:len(package.split('.'))-node.level+1] if node.level else []
                module = '.'.join(base+([node.module] if node.module else []))
                modules = [module]+[module+'.'+item.name for item in node.names]
            else: modules = []
            for module in modules:
                if module.split('.')[0] not in ('a3d', 'blender'): continue
                candidate = module.replace('.', '/')+'.py'
                if (ROOT/candidate).is_file(): pending.append(candidate)
            if isinstance(node, ast.Call) and isinstance(node.func, ast.Name) and node.func.id == 'contract' and node.args:
                first = node.args[0]
                if isinstance(first, ast.Constant) and isinstance(first.value, str):
                    candidate = 'schemas/'+first.value+'.schema.json'
                    if (ROOT/candidate).is_file(): pending.append(candidate)
    return dict(sorted(files.items()))


def _runtime():
    # These modules govern every unit. Handler modules and unrelated schemas
    # are bound separately; changing them invalidates only dependent units.
    return digest(_code_inventory(COMMON_CODE_PATHS, traverse=False))


def _unit_runtime(unit):
    explicit = unit.get('code_paths', [])
    if unit['operation'] not in OPERATION_MODULES and not explicit:
        raise StudioError('New run operation requires reviewed handler code_paths in its specification')
    paths = OPERATION_MODULES.get(unit['operation'], [])+explicit
    # The shared guard and dispatcher are bound by _runtime; traversing their
    # conditional imports would incorrectly couple unrelated handler modules.
    return _code_inventory(paths)


def _reference(project, value):
    if not isinstance(value, dict) or not {'path', 'sha256'} <= set(value):
        raise StudioError('Run inputs and receipts require path and SHA-256')
    identity = value['sha256']
    if not isinstance(identity, str) or len(identity) != 64 or any(c not in '0123456789abcdef' for c in identity):
        raise StudioError('Run reference SHA-256 is invalid')
    value_path = value['path']
    if not isinstance(value_path, str):
        raise StudioError('Run reference path must be a string')
    path = Path(value_path)
    if path.is_absolute():
        try:
            value_path = path.resolve().relative_to(project.root).as_posix()
        except ValueError as error:
            raise StudioError('Run references must stay inside this project') from error
    try:
        path = inside(project.root, value_path)
    except FileNotFoundError as error:
        raise StudioError('Run reference is missing: '+value_path) from error
    if not path.is_file() or sha(path) != identity:
        raise StudioError('Run reference is missing or stale: '+value_path)
    return {'path': value_path, 'sha256': identity}


def _references(project, value):
    result = {}
    def visit(item):
        if isinstance(item, dict):
            if {'path', 'sha256'} <= set(item):
                ref = _reference(project, item)
                if ref['path'] in result and result[ref['path']] != ref:
                    raise StudioError('Run binds contradictory input identities')
                result[ref['path']] = ref
            else:
                for child in item.values(): visit(child)
        elif isinstance(item, list):
            for child in item: visit(child)
    visit(value)
    return [result[key] for key in sorted(result)]


def _argument_inputs(project, arguments):
    """Bind actual named path arguments in addition to explicit source refs."""
    refs = _references(project, arguments)
    def visit(value):
        if not isinstance(value, dict):
            return
        if set(value) == {'$unit', 'field'}:
            return
        for key, item in value.items():
            if isinstance(item, dict): visit(item)
            elif isinstance(item, str) and (key.endswith('_path') or key in ('source_blend', 'checkpoint_receipt', 'package_dir')):
                if Path(item).is_absolute():
                    try:
                        item = Path(item).resolve().relative_to(project.root).as_posix()
                    except ValueError as error:
                        raise StudioError('Run argument file must stay inside its project') from error
                path = inside(project.root, item, False)
                if path.is_file():
                    refs.append({'path': item, 'sha256': sha(path)})
                elif path.is_dir():
                    files = sorted(path.rglob('*'))
                    if len(files) > 4096:
                        raise StudioError('Run input directory exceeds its bounded inventory')
                    for file in files:
                        if file.is_file():
                            rel = file.relative_to(project.root).as_posix()
                            inside(project.root, rel)
                            refs.append({'path': rel, 'sha256': sha(file)})
    visit(arguments)
    return _references(project, refs)


def _dag(units):
    mapping = {unit['id']: unit for unit in units}
    if len(mapping) != len(units):
        raise StudioError('Run has duplicate unit identities')
    remaining = set(mapping); order = []
    for unit in units:
        ident(unit['id'])
        if (len(set(unit['dependencies'])) != len(unit['dependencies']) or
                any(dep not in mapping or dep == unit['id'] for dep in unit['dependencies'])):
            raise StudioError('Run dependencies must identify distinct existing units')
        if {'project_root', 'request_key'} & set(unit['arguments']):
            raise StudioError('Run owns its project and request key; unit arguments cannot override them')
        def references(value):
            if isinstance(value, dict):
                if '$unit' in value:
                    if (set(value) != {'$unit', 'field'} or value['$unit'] not in unit['dependencies']
                            or not isinstance(value['field'], str) or not value['field']
                            or any(not part for part in value['field'].split('.'))):
                        raise StudioError('Unit result arguments require a declared dependency and exact field')
                else:
                    for child in value.values(): references(child)
            elif isinstance(value, list):
                for child in value: references(child)
        references(unit['arguments'])
    while remaining:
        ready = sorted(key for key in remaining if not (set(mapping[key]['dependencies']) & remaining))
        if not ready:
            raise StudioError('Run dependency graph contains a cycle')
        order.extend(ready); remaining.difference_update(ready)
    return order


def _verify_run(project, run):
    if _runtime() != run['runtime_sha256']:
        raise StudioError('Run code fingerprint changed; create a reviewed new run specification identity')
    _reference(project, run['specification'])
    for ref in run['inputs']: _reference(project, ref)


def _verify_unit(project, unit):
    if _unit_runtime(unit) != unit['code_sources']:
        raise StudioError('Run unit handler or admission dependency changed: '+unit['id'])
    for ref in unit['inputs']: _reference(project, ref)


def create_run(project, kind, specification_path):
    if kind not in KINDS:
        raise StudioError('Unknown run kind')
    path = inside(project.root, specification_path)
    spec = contract('run', json.loads(path.read_text(encoding='utf-8-sig')))
    ident(spec['id'])
    if spec['kind'] != kind:
        raise StudioError('Run kind and specification differ')
    order = _dag(spec['units'])
    state = project.state()
    if spec['asset_id'] != state['asset']['id']:
        raise StudioError('Run targets another asset')
    if state.get('pending_blender_operation'):
        raise StudioError('Recover the pending Blender operation before creating a run')
    if state['stage'] == 'COMPLETE':
        raise StudioError('Completed project is immutable')
    source_ref = {'path': specification_path, 'sha256': sha(path)}
    inputs = _references(project, spec['inputs'])
    runtime = _runtime()
    units = []
    for definition in sorted(spec['units'], key=lambda unit: order.index(unit['id'])):
        unit = copy.deepcopy(definition)
        unit['inputs'] = _references(project, unit['inputs']+_argument_inputs(project, unit['arguments']))
        unit['code_sources'] = _unit_runtime(unit)
        unit['runtime_sha256'] = digest(unit['code_sources'])
        unit.update(status='PENDING', attempts=[], qualification='NOT_GRANTED')
        units.append(unit)
    binding = digest({'specification': source_ref, 'definition': spec, 'runtime_sha256': runtime,
                      'inputs': inputs, 'units_inputs': {unit['id']: unit['inputs'] for unit in units},
                      'units_code': {unit['id']: unit['code_sources'] for unit in units}})
    request_key = kind+'.'+spec['id']
    with project.transaction() as db:
        if project.state(db).get('pending_blender_operation'):
            raise StudioError('A pending Blender operation prevents run mutation')
        _migrate(db)
        existing = db.execute('SELECT doc FROM runs WHERE request_key=?', (request_key,)).fetchone()
        if existing:
            run = json.loads(existing[0])
            if run['fingerprint'] != binding:
                raise StudioError('Run request key reused with different specification, inputs or code')
            return copy.deepcopy(run)
        run = {'version': 1, 'run_id': 'run.'+uuid.uuid4().hex, 'request_key': request_key,
               'project_id': state['project_id'], 'asset_id': spec['asset_id'], 'kind': kind,
               'specification': source_ref, 'fingerprint': binding, 'runtime_sha256': runtime,
               'inputs': inputs, 'budgets': copy.deepcopy(spec['budgets']), 'units': units,
               'status': 'CREATED', 'revision': 0, 'created_at': now(), 'updated_at': now(),
               'stop_requested': False, 'accepted': False, 'qualification': 'NOT_GRANTED'}
        db.execute('INSERT INTO runs VALUES (?,?,?)', (run['run_id'], request_key, canonical(run).decode()))
        _save(db, run, 'run_created', {'fingerprint': binding})
    return copy.deepcopy(run)


def _verified_receipt(project, db, run, unit, attempt):
    _verify_unit(project, unit)
    for ref in attempt['inputs']: _reference(project, ref)
    ref = _reference(project, attempt['receipt'])
    row = db.execute('SELECT kind,doc FROM events WHERE id=?', (attempt['receipt_event_id'],)).fetchone()
    expected = {'run_id': run['run_id'], 'unit_id': unit['id'], 'attempt_id': attempt['id'],
                'receipt': ref, 'binding_sha256': attempt['binding_sha256']}
    if not row or row[0] != 'run_native_receipt' or json.loads(row[1]) != expected:
        raise StudioError('Native run receipt has no matching canonical dispatch registration')
    receipt = json.loads(inside(project.root, ref['path']).read_text())
    if (receipt.get('origin') != 'NATIVE_DISPATCH' or receipt.get('binding_sha256') != attempt['binding_sha256']
            or receipt.get('run_id') != run['run_id'] or receipt.get('unit_id') != unit['id']
            or receipt.get('attempt_id') != attempt['id'] or receipt.get('operation') != attempt['operation']
            or receipt.get('arguments') != attempt['arguments'] or receipt.get('runtime_sha256') != unit['runtime_sha256']
            or receipt.get('orchestrator_sha256') != run['runtime_sha256']):
        raise StudioError('Native run receipt is stale or belongs to another unit')
    for artifact in receipt['files']: _reference(project, artifact)
    if receipt.get('entry_checkpoint'): _reference(project, receipt['entry_checkpoint'])
    return receipt


def _resolve(project, db, run, value):
    if isinstance(value, dict):
        if set(value) == {'$unit', 'field'}:
            source = next(unit for unit in run['units'] if unit['id'] == value['$unit'])
            if source['status'] != 'COMPLETED' or source['executor'] != 'blender':
                raise StudioError('Dependent argument has no completed registered native result')
            result = _verified_receipt(project, db, run, source, source['attempts'][-1])['result']
            try:
                for key in value['field'].split('.'): result = result[key]
            except (KeyError, TypeError) as error:
                raise StudioError('Declared dependency result field is unavailable') from error
            return copy.deepcopy(result)
        return {key: _resolve(project, db, run, child) for key, child in value.items()}
    if isinstance(value, list): return [_resolve(project, db, run, child) for child in value]
    return copy.deepcopy(value)


def _verify_dependencies(project, db, run, unit):
    required = list(unit['dependencies']); checked = set()
    while required:
        dependency = required.pop()
        if dependency in checked: continue
        checked.add(dependency)
        source = next(item for item in run['units'] if item['id'] == dependency)
        _verify_unit(project, source)
        if source['executor'] == 'blender' and source['attempts'] and source['attempts'][-1].get('receipt'):
            _verified_receipt(project, db, run, source, source['attempts'][-1])
        elif source['executor'] == 'comfy' and source['status']=='COMPLETED':
            _verified_comfy_receipt(project, db, run, source, source['attempts'][-1])
        required.extend(source['dependencies'])


def _prepared(project, attempt):
    from .guard import admit_operation, code_for
    admit_operation(project, attempt['operation'], attempt['arguments'])
    code = code_for(str(project.root), attempt['operation'], attempt['arguments'])
    if digest(code) != attempt['code_sha256']:
        raise StudioError('Prepared run code changed')
    return {'status': 'AWAITING_CONFIRMATION', 'unit_id': attempt['unit_id'], 'attempt_id': attempt['id'],
            'operation': attempt['operation'], 'arguments': copy.deepcopy(attempt['arguments']),
            'code': code, 'code_sha256': attempt['code_sha256'], 'executed': False,
            'execution_permission_required': True, 'qualification': 'NOT_GRANTED',
            'budgets': copy.deepcopy(attempt['budgets']),
            'next': 'Present this exact operation and effects, ask for permission, wait for an affirmative reply, then use the guarded Blender MCP. Preparation is not execution permission.'}


def _recovery(project, pending):
    ref = pending.get('checkpoint')
    if not ref:
        return {'status': 'RECOVERY_REQUIRED', 'reason': 'PENDING_OPERATION_WITHOUT_ENTRY_CHECKPOINT', 'executed': False}
    _reference(project, ref)
    from .guard import admit_operation, code_for
    admit_operation(project, 'restore_checkpoint', {})
    return {'status': 'RECOVERY_REQUIRED', 'checkpoint': copy.deepcopy(ref),
            'code': code_for(str(project.root), 'restore_checkpoint', {}),
            'executed': False, 'execution_permission_required': True,
            'resume_mode': 'RESTORE_ENTRY_CHECKPOINT_THEN_REPLAY_UNIT', 'continuous_physics_resume': False}


def _restored(db, attempt):
    checkpoint = attempt.get('entry_checkpoint')
    if not checkpoint:
        return False
    boundary = max(attempt.get('receipt_event_id', 0),
                   attempt.get('checkpoint_boundary_event_id', attempt.get('checkpoint_event_id', 0)))
    rows = db.execute("SELECT doc FROM events WHERE kind='blender_recovered' AND id>? ORDER BY id", (boundary,))
    for row in rows:
        recorded = json.loads(row[0]).get('checkpoint', {})
        if all(recorded.get(key) == checkpoint[key] for key in ('path', 'sha256')):
            return True
    return False


def _verified_native_checkpoint(project, db, run, unit, attempt):
    """Only the native checkpoint callback can authorize interrupted replay."""
    event_id = attempt.get('checkpoint_event_id')
    if event_id is None:
        return False
    checkpoint = _reference(project, attempt.get('entry_checkpoint'))
    row = db.execute("SELECT doc FROM events WHERE kind='run_native_checkpoint' AND id=?", (event_id,)).fetchone()
    if not row:
        raise StudioError('Native entry checkpoint lacks its canonical binding event')
    event = json.loads(row[0])
    expected = {'run_id': run['run_id'], 'unit_id': unit['id'], 'attempt_id': attempt['id'],
                'binding_sha256': attempt['binding_sha256'], 'operation': attempt['operation'],
                'arguments': attempt['arguments'], 'entry_checkpoint': checkpoint}
    if any(event.get(key) != value for key, value in expected.items()):
        raise StudioError('Native entry checkpoint event differs from the prepared attempt')
    started = db.execute("SELECT doc FROM events WHERE kind='blender_started' AND id=?",
                         (event.get('blender_started_event_id'),)).fetchone()
    if not started or not _native_start_matches(json.loads(started[0]), run, unit, attempt):
        raise StudioError('Native entry checkpoint lost its exact dispatcher start binding')
    if _reference(project, json.loads(started[0]).get('checkpoint')) != checkpoint:
        raise StudioError('Native dispatcher checkpoint differs from its journal boundary')
    return True


def _native_start_matches(event, run, unit, attempt):
    binding = event.get('run_binding')
    expected = {'run_id': run['run_id'], 'unit_id': unit['id'], 'attempt_id': attempt['id'],
                'binding_sha256': attempt['binding_sha256']}
    return (isinstance(binding, dict) and all(binding.get(key) == value for key, value in expected.items())
            and event.get('operation') == attempt['operation'] and event.get('arguments') == attempt['arguments']
            and event.get('status') == 'running')


def _attach_native_checkpoint(db, run, unit, attempt, reference, started_event):
    if attempt.get('entry_checkpoint') and any(attempt['entry_checkpoint'].get(key) != reference[key]
                                               for key in ('path', 'sha256')):
        raise StudioError('Native attempt cannot replace its declared entry checkpoint')
    attempt['entry_checkpoint'] = reference
    attempt['checkpoint_boundary_event_id'] = started_event
    detail = {'unit_id': unit['id'], 'attempt_id': attempt['id'], 'binding_sha256': attempt['binding_sha256'],
              'operation': attempt['operation'], 'arguments': copy.deepcopy(attempt['arguments']),
              'entry_checkpoint': reference, 'blender_started_event_id': started_event}
    attempt['checkpoint_event_id'] = _save(db, run, 'run_native_checkpoint', detail)
    db.execute('UPDATE runs SET doc=? WHERE id=?', (canonical(run).decode(), run['run_id']))


def _discover_native_checkpoint(project, db, run, unit, attempt):
    """Recover the small crash window after dispatcher start but before its hook."""
    if attempt.get('checkpoint_event_id') is not None:
        return
    matches = [(row[0], json.loads(row[1])) for row in db.execute(
        "SELECT id,doc FROM events WHERE kind='blender_started' ORDER BY id")]
    matches = [(event_id, event) for event_id, event in matches if _native_start_matches(event, run, unit, attempt)]
    if not matches:
        return
    if len(matches) != 1:
        raise StudioError('Interrupted native attempt has several canonical entry boundaries')
    event_id, event = matches[0]
    _attach_native_checkpoint(db, run, unit, attempt, _reference(project, event.get('checkpoint')), event_id)


def next_run_step(project, run_id):
    # A native completion can outlive a lost callback or rolled-back journal.
    # Reconcile its canonical event before examining pending; execute no code.
    with closing(sqlite3.connect(project.db.as_uri()+'?mode=ro', uri=True)) as reader:
        existing = _load(reader, run_id)
        pending_ready = project.state(reader).get('pending_blender_operation', {}).get('status') == 'RESULT_READY'
        if any(unit['executor'] == 'blender' and unit['attempts'] and
               (unit['status'] == 'WAITING_RESULT' or pending_ready and unit['attempts'][-1].get('receipt')) and
               _ready_event(project, reader, existing, unit, unit['attempts'][-1]) is not None
               for unit in existing['units']):
            return reconcile_native_run_result(project, run_id)
    with project.transaction() as db:
        run = _load(db, run_id)
        pending = project.state(db).get('pending_blender_operation')
        if pending:
            return _recovery(project, pending)
        _verify_run(project, run)
        if run['stop_requested'] and not any(unit['executor'] == 'comfy' and unit['attempts'] and
                unit['attempts'][-1].get('external_pending') for unit in run['units']):
            return {'run_id': run_id, 'status': run['status'], 'executed': False, 'qualification': 'NOT_GRANTED'}
        for interrupted in run['units']:
            if interrupted['executor'] != 'blender' or interrupted['status'] != 'WAITING_RESULT':
                continue
            last = interrupted['attempts'][-1]
            _verify_unit(project, interrupted)
            _discover_native_checkpoint(project, db, run, interrupted, last)
            if (_verified_native_checkpoint(project, db, run, interrupted, last) and _restored(db, last)):
                last['status'] = 'INTERRUPTED'
                interrupted['status'] = run['status'] = 'INCOMPLETE'
                interrupted['reason'] = 'NATIVE_INTERRUPTED_ENTRY_CHECKPOINT_RESTORED'
                _save(db, run, 'run_native_interrupted', {'unit_id': interrupted['id'], 'attempt_id': last['id'],
                    'entry_checkpoint': last['entry_checkpoint'], 'continuous_physics_resume': False})
        outstanding = next((unit for unit in run['units'] if unit['status'] in ('AWAITING_CONFIRMATION', 'WAITING_RESULT', 'SUBMITTING', 'WAITING_EXTERNAL', 'SUBMISSION_UNKNOWN', 'WAITING_OUTPUTS') or
                            unit['executor']=='comfy' and unit['attempts'] and unit['attempts'][-1].get('external_pending')), None)
        if outstanding:
            _verify_unit(project, outstanding)
            _verify_dependencies(project, db, run, outstanding)
            attempt = outstanding['attempts'][-1]
            for ref in attempt['inputs']: _reference(project, ref)
            if outstanding['executor'] == 'blender':
                if outstanding['status'] == 'WAITING_RESULT':
                    return {'run_id': run_id, 'unit_id': outstanding['id'], 'attempt_id': attempt['id'],
                            'status': 'UNKNOWN_COMPLETION', 'reason': 'NATIVE_EXECUTION_STARTED_WITHOUT_REGISTERED_RESULT',
                            'executed': False, 'reapplication_allowed': False, 'qualification': 'NOT_GRANTED'}
                return dict(_prepared(project, attempt), run_id=run_id)
            action = ('reconcile', run, outstanding, attempt)
        else:
            unit = next((item for item in run['units'] if item['status'] != 'COMPLETED'), None)
            if unit is None:
                for completed in run['units']:
                    _verify_unit(project, completed)
                    if completed['executor'] == 'blender':
                        _verified_receipt(project, db, run, completed, completed['attempts'][-1])
                    else: _verified_comfy_receipt(project, db, run, completed, completed['attempts'][-1])
                if run['status'] != 'COMPLETED':
                    run['status'] = 'COMPLETED'; _save(db, run, 'run_completed', {})
                return {'run_id': run_id, 'status': 'COMPLETED', 'executed': False, 'qualification': 'NOT_GRANTED', 'accepted': False}
            _verify_unit(project, unit)
            _verify_dependencies(project, db, run, unit)
            if any(next(item for item in run['units'] if item['id'] == dependency)['status'] != 'COMPLETED' for dependency in unit['dependencies']):
                return {'run_id': run_id, 'status': 'DEPENDENCIES_INCOMPLETE', 'unit_id': unit['id'], 'executed': False}
            if unit['status'] == 'UNKNOWN_COMPLETION':
                return {'run_id': run_id, 'status': 'UNKNOWN_COMPLETION', 'unit_id': unit['id'],
                        'reason': 'NATIVE_RETURN_NOT_ESTABLISHED', 'executed': False}
            if unit['status'] in ('NEEDS_CORRECTION', 'INCOMPLETE'):
                last = unit['attempts'][-1]
                if unit['executor'] != 'blender' or not _restored(db, last):
                    return {'run_id': run_id, 'status': unit['status'], 'unit_id': unit['id'],
                            'reason': 'RESTORE_ENTRY_CHECKPOINT_BEFORE_REPLAY', 'executed': False}
            budgets = unit.get('budgets', run['budgets'])
            if len(unit['attempts']) >= budgets['max_attempts']:
                return {'run_id': run_id, 'status': 'INCOMPLETE', 'reason': 'ATTEMPT_BUDGET', 'unit_id': unit['id'], 'executed': False}
            if sum(attempt.get('elapsed_seconds') or 0 for attempt in unit['attempts']) >= budgets['max_seconds']:
                return {'run_id': run_id, 'status': 'INCOMPLETE', 'reason': 'TIME_BUDGET', 'unit_id': unit['id'], 'executed': False}
            others = [json.loads(row[0]) for row in db.execute('SELECT doc FROM runs WHERE id<>?', (run_id,))]
            if any(other_unit['status'] in ('AWAITING_CONFIRMATION', 'WAITING_RESULT', 'SUBMITTING', 'WAITING_EXTERNAL', 'SUBMISSION_UNKNOWN')
                   or other_unit['attempts'] and other_unit['attempts'][-1].get('external_pending')
                   for item in others for other_unit in item['units']):
                raise StudioError('Another run has an unresolved operation; reconcile it before preparing a new unit')
            arguments = _resolve(project, db, run, unit['arguments'])
            bound = _references(project, unit['inputs']+_argument_inputs(project, arguments))
            attempt = {'id': 'attempt.'+uuid.uuid4().hex, 'unit_id': unit['id'], 'operation': unit['operation'],
                       'arguments': arguments, 'inputs': bound, 'created_at': now(),
                       'budgets': copy.deepcopy(budgets),
                       'sequence': len(unit['attempts'])+1, 'status': 'PREPARED'}
            attempt['binding_sha256'] = digest({'run_fingerprint': run['fingerprint'], 'attempt_id': attempt['id'],
                                               'unit_id': unit['id'], 'operation': unit['operation'], 'arguments': arguments, 'inputs': bound})
            if unit['executor'] == 'blender':
                from .guard import code_for
                attempt['code_sha256'] = digest(code_for(str(project.root), unit['operation'], arguments))
                response = _prepared(project, attempt)
                unit['attempts'].append(attempt); unit['status'] = 'AWAITING_CONFIRMATION'
                run['status'] = 'AWAITING_CONFIRMATION'
                _save(db, run, 'run_unit_prepared', {'unit_id': unit['id'], 'attempt_id': attempt['id'], 'binding_sha256': attempt['binding_sha256']})
                return dict(response, run_id=run_id)
            if unit['operation'] != 'submit_workflow':
                raise StudioError('Initial Comfy run adapter supports submit_workflow only; history/status/output use the owned job primitives')
            if set(arguments) != {'component_id', 'workflow_id', 'parameters'}:
                raise StudioError('Comfy run submission requires component_id, workflow_id and parameters')
            attempt['request_key'] = 'run.'+digest([run['request_key'], unit['id']])[:32]
            attempt['status'] = 'SUBMITTING'
            attempt['submitted_at'] = now(); attempt['external_pending'] = True
            unit['attempts'].append(attempt); unit['status'] = 'SUBMITTING'; run['status'] = 'WAITING_EXTERNAL'
            _save(db, run, 'run_comfy_submitting', {'unit_id': unit['id'], 'attempt_id': attempt['id'], 'request_key': attempt['request_key']})
            action = ('submit', run, unit, attempt)
    return _comfy_step(project, *action)


def _comfy_step(project, action, run, unit, attempt):
    from .comfy import Comfy
    error = None; started = time.monotonic(); outputs = None
    try:
        client = Comfy()
        if action == 'submit':
            client.submit(str(project.root), request_key=attempt['request_key'], **attempt['arguments'])
        job = next((job for job in project.jobs() if job['request_key'] == attempt['request_key']), None)
        if job:
            client.reconcile(str(project.root), job['job_id'])
            job = project.job(job['job_id'])
            if job['status'] == 'completed':
                if job.get('outputs'):
                    outputs = _references(project, job['outputs'])
                else:
                    if attempt.get('outputs_attempts', 0) >= attempt['budgets']['max_attempts']:
                        raise StudioError('Owned output collection attempt budget exhausted; inspect the original job outputs')
                    attempt['outputs_attempts'] = attempt.get('outputs_attempts', 0)+1
                    collected = client.outputs(str(project.root), job['job_id'], download=True)
                    outputs = _references(project, collected.get('outputs', []))
                if not outputs: raise StudioError('Completed provider job has no verified local outputs')
    except Exception as exc:
        error = str(exc)
        job = next((job for job in project.jobs() if job['request_key'] == attempt['request_key']), None)
    with project.transaction() as db:
        current = _load(db, run['run_id'])
        selected = next(item for item in current['units'] if item['id'] == unit['id'])
        stored = selected['attempts'][-1]
        if stored['id'] != attempt['id']:
            raise StudioError('Comfy run attempt changed during reconciliation')
        stored['elapsed_seconds'] = stored.get('elapsed_seconds', 0.) + time.monotonic()-started
        stored['outputs_attempts'] = attempt.get('outputs_attempts', 0)
        stored['phase_elapsed_seconds'] = max(0., (datetime.fromisoformat(now())-
                                                  datetime.fromisoformat(stored['submitted_at'])).total_seconds())
        if job:
            stored['job_id'] = job['job_id']; stored['job_status'] = job['status']
        if not job or job['status'] in ('preparing', 'submitting', 'submission_unknown', 'unknown'):
            selected['status'] = current['status'] = 'SUBMISSION_UNKNOWN'
            selected['reason'] = 'OWNED_JOB_SUBMISSION_NOT_ESTABLISHED'
        elif job['status'] == 'completed':
            if outputs:
                _register_comfy_outputs(project, db, current, selected, stored, job, outputs)
                selected['status'] = 'COMPLETED'; current['status'] = 'RUNNING'
            else:
                selected['status'] = current['status'] = 'WAITING_OUTPUTS'
                selected['reason'] = 'VERIFIED_LOCAL_OUTPUTS_REQUIRED'
        elif job['status'] in ('failed', 'cancelled'):
            selected['status'] = current['status'] = 'INCOMPLETE'
            selected['reason'] = 'OWNED_JOB_'+job['status'].upper()
        else:
            selected['status'] = current['status'] = 'WAITING_EXTERNAL'
        if error: stored['error'] = error
        stored['external_pending'] = not job or job['status'] not in ('completed','failed','cancelled') or selected['status']=='WAITING_OUTPUTS'
        if stored['phase_elapsed_seconds'] > stored['budgets']['max_seconds']:
            selected['reason'] = 'TIME_BUDGET'
            # A timed-out owned job still requires reconciliation; never discard
            # its uncertain state or turn a elapsed budget into a cancellation.
            selected['status'] = current['status'] = 'INCOMPLETE'
        if current['stop_requested']:
            current['status'] = 'STOP_REQUESTED' if stored['external_pending'] else 'STOPPED_INCOMPLETE'
        stored['status'] = selected['status']
        _save(db, current, 'run_comfy_reconciled', {'unit_id': unit['id'], 'attempt_id': attempt['id'], 'job_id': stored.get('job_id'), 'status': selected['status']})
    return {'run_id': current['run_id'], 'unit_id': unit['id'], 'status': current['status'],
            'request_key': attempt['request_key'], 'job_id': stored.get('job_id'),
            'qualification': 'NOT_GRANTED', 'submission_repeated': False,
            'next': 'Use the owned job status/output primitives. Unknown submission is never resubmitted; stop does not issue a global interrupt.'}


def _register_comfy_outputs(project, db, run, unit, attempt, job, outputs):
    arguments = attempt['arguments']
    if job['request_key'] != attempt['request_key'] or any(job.get(key) != arguments[key] for key in ('component_id','workflow_id','parameters')):
        raise StudioError('Owned Comfy result differs from its prepared run unit')
    workflow_path = inside(project.root, job['workflow_path'])
    if digest(json.loads(workflow_path.read_text(encoding='utf-8-sig'))) != job['workflow_sha256'] or not job.get('prompt_id'):
        raise StudioError('Owned Comfy output has no exact workflow or native prompt identity')
    receipt = {'origin':'OWNED_COMFY_OUTPUTS', 'run_id':run['run_id'], 'unit_id':unit['id'],
        'attempt_id':attempt['id'], 'binding_sha256':attempt['binding_sha256'], 'request_key':attempt['request_key'],
        'job_id':job['job_id'], 'prompt_id':job.get('prompt_id'), 'job_fingerprint':job['fingerprint'],
        'workflow_sha256':job['workflow_sha256'], 'arguments':arguments, 'files':outputs,
        'workflow':{'path':job['workflow_path'], 'sha256':sha(workflow_path)},
        'accepted':False, 'qualification':'NOT_GRANTED'}
    path = project.data/'runs/comfy'/(attempt['id']+'.json')
    if path.exists():
        if json.loads(path.read_text(encoding='utf-8-sig')) != receipt:
            raise StudioError('Owned Comfy output receipt orphan contradicts the original job')
    else: atomic_json(path, receipt)
    ref = {'path':path.relative_to(project.root).as_posix(), 'sha256':sha(path)}
    detail = {'run_id':run['run_id'], 'unit_id':unit['id'], 'attempt_id':attempt['id'],
              'receipt':ref, 'binding_sha256':attempt['binding_sha256']}
    previous = attempt.get('receipt_event_id')
    if previous:
        _verified_comfy_receipt(project, db, run, unit, attempt)
        return
    cursor = db.execute('INSERT INTO events(created_at,kind,doc) VALUES (?,?,?)',
                       (now(),'run_comfy_output_receipt',canonical(detail).decode()))
    attempt.update(receipt=ref, receipt_event_id=cursor.lastrowid)


def _verified_comfy_receipt(project, db, run, unit, attempt):
    _verify_unit(project, unit)
    ref = _reference(project, attempt['receipt'])
    event = db.execute('SELECT kind,doc FROM events WHERE id=?',(attempt['receipt_event_id'],)).fetchone()
    expected = {'run_id':run['run_id'], 'unit_id':unit['id'], 'attempt_id':attempt['id'],
                'receipt':ref, 'binding_sha256':attempt['binding_sha256']}
    if not event or event[0]!='run_comfy_output_receipt' or json.loads(event[1])!=expected:
        raise StudioError('Comfy outputs have no canonical owned-job registration')
    receipt = json.loads(inside(project.root, ref['path']).read_text())
    job = project.job(attempt['job_id'], db)
    if (receipt.get('origin')!='OWNED_COMFY_OUTPUTS' or receipt['binding_sha256']!=attempt['binding_sha256'] or
            receipt['job_id']!=job['job_id'] or receipt['request_key']!=job['request_key'] or
            receipt['job_fingerprint']!=job['fingerprint'] or receipt['workflow_sha256']!=job['workflow_sha256'] or
            receipt['arguments']!=attempt['arguments']):
        raise StudioError('Comfy run output binding is stale')
    _references(project, receipt['files'])
    _reference(project, receipt['workflow'])
    if _references(project, job.get('outputs', [])) != receipt['files'] or receipt.get('prompt_id') != job.get('prompt_id'):
        raise StudioError('Canonical Comfy output inventory differs from its registered run result')
    if not receipt['files']: raise StudioError('Comfy receipt contains no verified asset files')
    return receipt


def record_native_run_started(project, operation, arguments, entry_checkpoint=None):
    """Native guard callback before dispatch; intent never permits blind replay."""
    with project.transaction() as db:
        if not _table(db): return None
        matches = []
        for row in db.execute('SELECT doc FROM runs'):
            run = json.loads(row[0])
            for unit in run['units']:
                if unit['executor'] != 'blender' or not unit['attempts']: continue
                attempt = unit['attempts'][-1]
                if (unit['status'] in ('AWAITING_CONFIRMATION', 'WAITING_RESULT') and
                        attempt['operation'] == operation and attempt['arguments'] == arguments):
                    matches.append((run, unit, attempt))
        if not matches: return None
        if len(matches) != 1: raise StudioError('Native start matches several run units')
        run, unit, attempt = matches[0]
        if unit['status'] != 'AWAITING_CONFIRMATION':
            raise StudioError('Native execution already started; reconcile or restore its boundary before replay')
        if run['stop_requested']: raise StudioError('Stopped run cannot start its prepared native operation')
        _verify_run(project, run); _verify_unit(project, unit)
        for ref in attempt['inputs']: _reference(project, ref)
        checkpoint = _reference(project, entry_checkpoint) if entry_checkpoint else None
        attempt.update(status='WAITING_RESULT', started_at=now(), entry_checkpoint=checkpoint)
        unit['status'] = run['status'] = 'WAITING_RESULT'
        _save(db, run, 'run_native_started', {'unit_id': unit['id'], 'attempt_id': attempt['id'],
            'operation': operation, 'arguments': copy.deepcopy(arguments), 'binding_sha256': attempt['binding_sha256'],
            'entry_checkpoint': checkpoint})
    return {'run_id': run['run_id'], 'unit_id': unit['id'], 'attempt_id': attempt['id'],
            'binding_sha256': attempt['binding_sha256'], 'status': 'WAITING_RESULT'}


def record_native_run_checkpoint(project, operation, arguments, checkpoint):
    """Bind the persisted native entry boundary before the first mutation.

    The dispatcher calls this immediately after its canonical blender_started
    event. A lost result can then be replayed only after restoration of this
    exact path and SHA; a saved result-ready event still takes precedence.
    """
    with project.transaction() as db:
        if not _table(db): return None
        matches = []
        for row in db.execute('SELECT doc FROM runs'):
            run = json.loads(row[0])
            for unit in run['units']:
                if unit['executor'] != 'blender' or unit['status'] != 'WAITING_RESULT' or not unit['attempts']:
                    continue
                attempt = unit['attempts'][-1]
                if attempt['operation'] == operation and attempt['arguments'] == arguments:
                    matches.append((run, unit, attempt))
        if not matches: return None
        if len(matches) != 1: raise StudioError('Native checkpoint matches several run units')
        run, unit, attempt = matches[0]
        _verify_run(project, run); _verify_unit(project, unit)
        for ref in attempt['inputs']: _reference(project, ref)
        reference = _reference(project, checkpoint)
        pending = project.state(db).get('pending_blender_operation', {})
        if (pending.get('status') != 'running' or pending.get('operation') != operation or
                _reference(project, pending.get('checkpoint')) != reference or
                'arguments' in pending and pending['arguments'] != arguments):
            raise StudioError('Native entry checkpoint differs from the persisted pending boundary')
        started_event = None
        for row in db.execute("SELECT id,doc FROM events WHERE kind='blender_started' ORDER BY id DESC"):
            event = json.loads(row[1])
            if (_native_start_matches(event, run, unit, attempt) and event.get('checkpoint') and
                    _reference(project, event['checkpoint']) == reference):
                started_event = row[0]; break
        if started_event is None:
            raise StudioError('Native entry checkpoint lacks its canonical dispatcher start event')
        if attempt.get('checkpoint_event_id') is not None:
            if _reference(project, attempt['entry_checkpoint']) != reference:
                raise StudioError('Native attempt cannot replace its persisted entry checkpoint')
            _verified_native_checkpoint(project, db, run, unit, attempt)
        else:
            _attach_native_checkpoint(db, run, unit, attempt, reference, started_event)
    return {'run_id': run['run_id'], 'unit_id': unit['id'], 'attempt_id': attempt['id'],
            'binding_sha256': attempt['binding_sha256'], 'status': 'WAITING_RESULT', 'entry_checkpoint': reference}


def native_attempt_binding(project, operation, arguments):
    """Read-only native dispatcher lookup; no table migration or reservation."""
    with closing(sqlite3.connect(project.db.as_uri()+'?mode=ro', uri=True)) as db:
        if not _table(db): return None
        matches = []
        for row in db.execute('SELECT doc FROM runs'):
            run = json.loads(row[0])
            for unit in run['units']:
                if unit['executor'] != 'blender' or unit['status'] not in ('AWAITING_CONFIRMATION', 'WAITING_RESULT'): continue
                attempt = unit['attempts'][-1]
                if attempt['operation'] == operation and attempt['arguments'] == arguments:
                    _verify_run(project, run); _verify_unit(project, unit)
                    matches.append({'run_id': run['run_id'], 'unit_id': unit['id'], 'attempt_id': attempt['id'],
                        'binding_sha256': attempt['binding_sha256'], 'status': unit['status']})
        if len(matches) > 1: raise StudioError('Native operation matches several run attempts')
        return matches[0] if matches else None


def _ready_event(project, db, run, unit, attempt):
    rows = db.execute("SELECT id,doc FROM events WHERE kind='run_native_result_ready' ORDER BY id DESC")
    for event_id, text in rows:
        ready = json.loads(text)
        identity = ('run_id', 'unit_id', 'attempt_id', 'binding_sha256')
        expected = {'run_id': run['run_id'], 'unit_id': unit['id'], 'attempt_id': attempt['id'],
                    'binding_sha256': attempt['binding_sha256']}
        if any(ready.get(key) != expected[key] for key in identity): continue
        if ready.get('operation') != attempt['operation'] or ready.get('arguments') != attempt['arguments']:
            raise StudioError('Canonical native completion arguments do not match the prepared unit')
        result = ready.get('result')
        if not isinstance(result, dict) or digest(result) != ready.get('result_sha256'):
            raise StudioError('Canonical native completion result identity is invalid')
        runtime = result.get('runtime', {})
        modules = runtime.get('loaded_modules')
        if (not isinstance(modules, dict) or not modules or digest(modules) != ready.get('runtime_sha256')
                or runtime.get('loaded_source_sha256') != ready['runtime_sha256']):
            raise StudioError('Canonical completion is missing the actual native runtime identity')
        required_sources = {**{path:sha(ROOT/path) for path in COMMON_CODE_PATHS}, **unit['code_sources']}
        for module, identity in modules.items():
            path = module.replace('.', '/')+'.py'
            if not (ROOT/path).is_file(): path = module.replace('.', '/')+'/__init__.py'
            if not module.startswith(('a3d', 'blender')) or not (ROOT/path).is_file() or path in required_sources and required_sources[path] != identity:
                raise StudioError('Native completion loaded code differs from the current installation')
        _verify_run(project, run); _verify_unit(project, unit)
        _references(project, result)
        if ready.get('entry_checkpoint'): _reference(project, ready['entry_checkpoint'])
        return dict(ready, event_id=event_id)
    return None


def reconcile_native_run_result(project, run_id):
    """Recover a real canonical completion without rerunning its native code."""
    with closing(sqlite3.connect(project.db.as_uri()+'?mode=ro', uri=True)) as db:
        run = _load(db, run_id)
        pending = project.state(db).get('pending_blender_operation', {})
        matches = [(unit, _ready_event(project, db, run, unit, unit['attempts'][-1]))
                   for unit in run['units'] if unit['executor']=='blender' and unit['attempts'] and
                   (unit['status']=='WAITING_RESULT' or unit['attempts'][-1].get('receipt') and
                    pending.get('status')=='RESULT_READY' and pending.get('operation')==unit['operation'])]
        matches = [(unit, ready) for unit, ready in matches if ready is not None]
        if pending.get('status')=='RESULT_READY':
            matches = [(unit, ready) for unit, ready in matches if ready.get('entry_checkpoint') and
                       all(ready['entry_checkpoint'].get(key)==pending.get('checkpoint', {}).get(key) for key in ('path','sha256'))]
        if len(matches) != 1:
            raise StudioError('Exactly one canonical native completion is required for reconciliation')
        unit, ready = matches[0]
        if unit['attempts'][-1].get('receipt'):
            receipt = _verified_receipt(project, db, run, unit, unit['attempts'][-1])
            if receipt['result'] != ready['result']:
                raise StudioError('Registered receipt contradicts the canonical native completion')
            result = {'run_id':run_id, 'unit_id':unit['id'], 'receipt':unit['attempts'][-1]['receipt'],
                      'status':unit['status'], 'accepted':False}
        else: result = None
    if result is None:
        result = record_native_run_result(project, ready['operation'], ready['arguments'], ready['result'],
            entry_checkpoint=ready.get('entry_checkpoint'), elapsed_seconds=ready.get('elapsed_seconds'))
    if result is None: raise StudioError('Native attempt changed before its completion could be reconciled')
    with project.transaction() as db:
        state = project.state(db); pending = state.get('pending_blender_operation')
        if pending:
            checkpoint = ready.get('entry_checkpoint')
            same_checkpoint = checkpoint and pending.get('checkpoint') and all(
                checkpoint.get(key) == pending['checkpoint'].get(key) for key in ('path', 'sha256'))
            if pending.get('status') != 'RESULT_READY' or pending.get('operation') != ready['operation'] or not same_checkpoint:
                raise StudioError('Registered completion cannot clear an unrelated native pending boundary')
            if 'arguments' in pending and pending['arguments'] != ready['arguments']:
                raise StudioError('Registered completion cannot clear different native pending arguments')
            state.pop('pending_blender_operation')
            project.save(db, state, 'blender_finished', {'operation': ready['operation'],
                'run_id': run_id, 'native_result_ready_event_id': ready['event_id'], 'reconciled_without_reexecution': True})
    return dict(result, executed=False, reconciled=True, native_result_ready_event_id=ready['event_id'])


def _record_native(project, operation, arguments, result, checkpoint, failed, elapsed_seconds):
    """Only call from actual managed native dispatch, never from user evidence."""
    with project.transaction() as db:
        if not _table(db): return None
        matches = []
        for row in db.execute('SELECT doc FROM runs'):
            run = json.loads(row[0])
            for unit in run['units']:
                if unit['executor'] == 'blender' and unit['status'] in ('AWAITING_CONFIRMATION', 'WAITING_RESULT'):
                    attempt = unit['attempts'][-1]
                    if attempt['operation'] == operation and attempt['arguments'] == arguments:
                        matches.append((run, unit, attempt))
        if not matches: return None
        if len(matches) != 1:
            raise StudioError('Native dispatch matches several run units')
        run, unit, attempt = matches[0]
        if not isinstance(result, dict):
            raise StudioError('Native run result must be an object')
        if elapsed_seconds is not None and (isinstance(elapsed_seconds, bool) or not isinstance(elapsed_seconds, (int, float))
                or not math.isfinite(elapsed_seconds) or elapsed_seconds < 0):
            raise StudioError('Native execution elapsed seconds must be finite and non-negative')
        canonical(result)
        _verify_run(project, run)
        _verify_unit(project, unit)
        for reference in attempt['inputs']: _reference(project, reference)
        files = _references(project, _references(project, result)+_argument_inputs(project, result))
        checkpoint_ref = _reference(project, checkpoint) if checkpoint else None
        receipt = {'version': 1, 'origin': 'NATIVE_DISPATCH', 'run_id': run['run_id'], 'unit_id': unit['id'],
                   'attempt_id': attempt['id'], 'binding_sha256': attempt['binding_sha256'],
                   'runtime_sha256': unit['runtime_sha256'], 'orchestrator_sha256': run['runtime_sha256'],
                   'code_sources': copy.deepcopy(unit['code_sources']), 'operation': operation, 'arguments': copy.deepcopy(arguments),
                   'result': copy.deepcopy(result), 'files': files, 'entry_checkpoint': checkpoint_ref,
                   'execution': 'FAILED' if failed else 'RETURNED', 'created_at': now(),
                   'elapsed_seconds': elapsed_seconds, 'budget': copy.deepcopy(attempt['budgets']),
                   'accepted': False, 'qualification': result.get('qualification', 'NOT_GRANTED')}
        path = project.data/'runs'/'native'/(attempt['id']+'.json')
        if path.exists():
            orphan = json.loads(path.read_text(encoding='utf-8-sig'))
            # A transaction rollback may leave the immutable atomic file. Only
            # this actual native callback may recover exactly the same result;
            # differing content is retained for explicit boundary recovery.
            expected = dict(receipt); observed = dict(orphan)
            expected.pop('created_at'); observed.pop('created_at', None)
            if observed != expected:
                raise StudioError('Native receipt orphan differs from the exact callback; restore the entry checkpoint')
        else:
            atomic_json(path, receipt)
        reference = {'path': path.relative_to(project.root).as_posix(), 'sha256': sha(path)}
        event = {'run_id': run['run_id'], 'unit_id': unit['id'], 'attempt_id': attempt['id'],
                 'receipt': reference, 'binding_sha256': attempt['binding_sha256']}
        cursor = db.execute('INSERT INTO events(created_at,kind,doc) VALUES (?,?,?)',
                            (now(), 'run_native_receipt', canonical(event).decode()))
        attempt.update(receipt=reference, receipt_event_id=cursor.lastrowid, entry_checkpoint=checkpoint_ref,
                       elapsed_seconds=elapsed_seconds)
        status = result.get('status', result.get('readiness'))
        accepted_statuses = unit.get('success_statuses')
        elapsed_total = sum(item.get('elapsed_seconds') or 0 for item in unit['attempts'])
        if elapsed_total > attempt['budgets']['max_seconds']:
            unit['status'] = 'INCOMPLETE'; status = 'TIME_BUDGET'
        elif failed or status == 'INCOMPLETE':
            unit['status'] = 'INCOMPLETE'
        elif status in FAILED_RESULTS or accepted_statuses and status not in accepted_statuses:
            unit['status'] = 'NEEDS_CORRECTION'
        elif status not in KNOWN_RESULTS and not (accepted_statuses and status in accepted_statuses):
            unit['status'] = 'UNKNOWN_COMPLETION'
        else:
            unit['status'] = 'COMPLETED'
        unit['qualification'] = copy.deepcopy(receipt['qualification'])
        unit['reason'] = status or ('NATIVE_EXCEPTION' if failed else 'NATIVE_RETURNED')
        attempt['status'] = unit['status']
        run['status'] = 'RUNNING' if unit['status'] == 'COMPLETED' else unit['status']
        if run['stop_requested']: run['status'] = 'STOPPED_INCOMPLETE'
        _save(db, run, 'run_native_registered', {'unit_id': unit['id'], 'attempt_id': attempt['id'], 'status': unit['status']})
    return {'run_id': run['run_id'], 'unit_id': unit['id'], 'receipt': reference, 'status': unit['status'], 'accepted': False}


def record_native_run_result(project, operation, arguments, result, entry_checkpoint=None, elapsed_seconds=None):
    return _record_native(project, operation, arguments, result, entry_checkpoint, False, elapsed_seconds)


def record_native_run_failure(project, operation, arguments, error, entry_checkpoint=None, elapsed_seconds=None):
    return _record_native(project, operation, arguments, {'status': 'INCOMPLETE', 'error': str(error)}, entry_checkpoint, True, elapsed_seconds)


def run_status(project, run_id=None):
    """Read-only SQLite access: even an old project is never migrated here."""
    with closing(sqlite3.connect(project.db.as_uri()+'?mode=ro', uri=True)) as db:
        if run_id is None:
            runs = [json.loads(row[0]) for row in db.execute('SELECT doc FROM runs ORDER BY rowid')] if _table(db) else []
            return {'runs': [dict(run, diagnostics=diagnose_run(run)) for run in runs], 'read_only': True}
        run = _load(db, run_id)
        result = copy.deepcopy(run)
        try:
            _verify_run(project, run)
            for unit in run['units']:
                _verify_unit(project, unit)
                if unit['executor'] == 'blender' and unit['attempts'] and unit['attempts'][-1].get('receipt'):
                    _verified_receipt(project, db, run, unit, unit['attempts'][-1])
                elif unit['executor'] == 'comfy' and unit['attempts'] and unit['attempts'][-1].get('receipt'):
                    _verified_comfy_receipt(project, db, run, unit, unit['attempts'][-1])
            result['binding_status'] = 'CURRENT'
        except StudioError as error:
            result['binding_status'] = 'STALE_OR_UNVERIFIED'; result['binding_error'] = str(error)
        result['diagnostics'] = diagnose_run(run); result['read_only'] = True
        return result


def request_run_stop(project, run_id):
    """Record a boundary stop; never cancel unknown jobs or clear native pending."""
    with project.transaction() as db:
        run = _load(db, run_id)
        if not run['stop_requested']:
            run['stop_requested'] = True
            pending = project.state(db).get('pending_blender_operation')
            if not pending:
                for unit in run['units']:
                    if unit['executor'] == 'blender' and unit['status'] == 'AWAITING_CONFIRMATION':
                        unit['status'] = unit['attempts'][-1]['status'] = 'CANCELLED_UNEXECUTED'
            unresolved = pending or any(
                unit['status'] in ('SUBMITTING', 'WAITING_EXTERNAL', 'SUBMISSION_UNKNOWN','WAITING_OUTPUTS') or
                unit['attempts'] and unit['attempts'][-1].get('external_pending') for unit in run['units'])
            run['status'] = 'STOP_REQUESTED' if unresolved else 'STOPPED_INCOMPLETE'
            _save(db, run, 'run_stop_requested', {'native_or_external_pending': bool(unresolved)})
    return {'run_id': run_id, 'status': run['status'], 'stop_requested': True,
            'execution_complete': all(unit['status'] == 'COMPLETED' for unit in run['units']),
            'qualification': 'NOT_GRANTED', 'native_pending_cleared': False, 'external_cancel_sent': False}
