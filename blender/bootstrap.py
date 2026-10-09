"""Load the requested installation in a long-lived Blender Python process.

Executed by absolute filename through the exact guarded trampoline. Never use
an already imported a3d/blender module to decide which installation to activate.
This is runtime selection, not admission: dispatch repeats all project checks.
"""
import importlib
import hashlib
import json
import sys
import time
from pathlib import Path


def dispatch_current(project_root, operation, arguments):
    root = Path(__file__).resolve().parents[1]
    # Fail before activation if the installation was removed during an update.
    version = json.loads((root / '.codex-plugin/plugin.json').read_text(encoding='utf-8-sig'))['version']
    for relative in ('a3d/__init__.py', 'a3d/guard.py', 'blender/__init__.py', 'blender/operations.py'):
        if not (root / relative).is_file():
            raise RuntimeError('Atelier 3D installation incomplete; request fresh operation code')
    names = [name for name in sys.modules
             if name in ('a3d', 'blender') or name.startswith(('a3d.', 'blender.'))]
    for name in names:
        del sys.modules[name]
    sys.path[:] = [str(root)] + [entry for entry in sys.path if entry != str(root)]
    importlib.invalidate_caches()
    module = importlib.import_module('blender.operations')
    for name, loaded in list(sys.modules.items()):
        if name in ('a3d', 'blender') or name.startswith(('a3d.', 'blender.')):
            filename = getattr(loaded, '__file__', None)
            if not filename or not Path(filename).resolve().is_relative_to(root):
                raise RuntimeError('Atelier 3D runtime mixed with another installation: ' + name)
    from a3d.runs import record_native_run_result, record_native_run_failure, record_native_run_started
    from a3d.guard import admit_operation
    from a3d.core import digest
    from a3d.store import Project
    project = Project(project_root)
    admit_operation(project, operation, arguments)
    binding = record_native_run_started(project, operation, arguments)
    started = time.monotonic()
    try:
        result = module.dispatch(project_root, operation, arguments)
    except BaseException as error:
        pending = project.state().get('pending_blender_operation', {})
        record_native_run_failure(project, operation, arguments, str(error),
                                  entry_checkpoint=pending.get('checkpoint'), elapsed_seconds=time.monotonic()-started)
        raise
    elapsed = time.monotonic()-started
    entry_checkpoint = result.pop('_entry_checkpoint', None)
    # Exact roots and source identities distinguish a disk installation from
    # the modules actually selected in this long-lived Blender interpreter.
    loaded_sources = {}
    for name, loaded in list(sys.modules.items()):
        if name in ('a3d', 'blender') or name.startswith(('a3d.', 'blender.')):
            filename = Path(loaded.__file__).resolve()
            if not filename.is_relative_to(root):
                raise RuntimeError('Atelier 3D runtime changed installation during dispatch: '+name)
            loaded_sources[name] = hashlib.sha256(filename.read_bytes()).hexdigest()
    identity = hashlib.sha256(json.dumps(loaded_sources,sort_keys=True,separators=(',', ':')).encode()).hexdigest()
    result = {**result, 'runtime': {'version': version, 'root': str(root),
                                  'loaded_source_sha256': identity, 'loaded_modules': loaded_sources}}
    if binding:
        with project.transaction() as db:
            state = project.state(db)
            project.save(db, state, 'run_native_result_ready', {
                **{key:binding[key] for key in ('run_id','unit_id','attempt_id','binding_sha256')},
                'operation':operation, 'arguments':arguments, 'result':result, 'result_sha256':digest(result),
                'entry_checkpoint':entry_checkpoint, 'elapsed_seconds':elapsed, 'runtime_sha256':identity})
    record_native_run_result(project, operation, arguments, result, entry_checkpoint=entry_checkpoint,
                             elapsed_seconds=elapsed)
    if entry_checkpoint:
        # Successful scene mutation remains recoverable until its native receipt
        # has actually reached canonical storage. A callback failure leaves it
        # pending, so admission cannot prepare a second mutation blindly.
        with project.transaction() as db:
            state = project.state(db)
            pending = state.get('pending_blender_operation')
            if (pending and pending['status'] == 'RESULT_READY' and pending['checkpoint'] == entry_checkpoint
                    and pending['operation'] == operation and pending.get('arguments') == arguments):
                state.pop('pending_blender_operation')
                project.save(db, state, 'blender_finished', {'operation':operation,'checkpoint':entry_checkpoint})
    if operation in ('prepare_pattern_assembly', 'transition_pattern_assembly'):
        from a3d.native_transport import compact_preparation_reply
        result = compact_preparation_reply(result)
    return result
