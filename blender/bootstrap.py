"""Load the requested installation in a long-lived Blender Python process.

Executed by absolute filename through the exact guarded trampoline. Never use
an already imported a3d/blender module to decide which installation to activate.
This is runtime selection, not admission: dispatch repeats all project checks.
"""
import importlib
import hashlib
import json
import sys
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
    result = module.dispatch(project_root, operation, arguments)
    if operation in ('prepare_pattern_assembly', 'transition_pattern_assembly'):
        from a3d.native_transport import compact_preparation_reply
        result = compact_preparation_reply(result)
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
    return {**result, 'runtime': {'version': version, 'root': str(root),
                                 'loaded_source_sha256': identity, 'loaded_modules': loaded_sources}}
