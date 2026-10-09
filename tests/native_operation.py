"""Execute one exact registered operation in an isolated background Blender.

This coordinator driver is for native development/qualification campaigns.
Interactive MCP calls still require the plugin's exact-operation user approval.
Supply A3D_NATIVE_PROJECT and a portable A3D_NATIVE_REQUEST run specification.
"""
import os
from pathlib import Path
import runpy
import sys

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))


def main():
    import bpy
    from a3d.core import StudioError, atomic_json, inside, read_json
    from a3d.store import Project
    from a3d.runs import create_run, next_run_step, run_status
    if not bpy.app.background:
        raise StudioError('Development driver requires an isolated background Blender')
    project = Project(os.environ['A3D_NATIVE_PROJECT'])
    specification_path = os.environ['A3D_NATIVE_REQUEST']
    specification = read_json(inside(project.root, specification_path))
    if len(specification['units']) != 1 or specification['units'][0]['executor'] != 'blender':
        raise StudioError('This native driver executes one exact Blender operation')
    dispatch = runpy.run_path(str(ROOT/'blender/bootstrap.py'))['dispatch_current']
    session_path = project.data/'blender/session.json'
    setup = None
    if os.environ.get('A3D_NATIVE_SCENE') == 'EMPTY_WORKING_COPY':
        if session_path.exists():
            raise StudioError('Explicit empty bootstrap cannot replace an existing working session')
        bpy.ops.wm.read_homefile(use_empty=True, use_factory_startup=True, load_ui=False, use_splash=False)
        bpy.context.scene.unit_settings.system = 'METRIC'; bpy.context.scene.unit_settings.scale_length = 1.
        setup = dispatch(str(project.root), 'prepare', {})
    if session_path.exists():
        working = Path(read_json(session_path)['working']).resolve(strict=True)
        if not working.is_relative_to(project.data/'blender'):
            raise StudioError('Working scene is outside the isolated project')
        bpy.ops.wm.open_mainfile(filepath=str(working), load_ui=False)
    info = create_run(project, specification['kind'], specification_path)
    step = next_run_step(project, info['run_id'])
    if step['status'] != 'AWAITING_CONFIRMATION':
        raise StudioError('Native operation is not the exact admissible next step')
    result = dispatch(str(project.root), step['operation'], step['arguments'])
    next_run_step(project, info['run_id'])
    status = run_status(project, info['run_id'])
    output = Path(os.environ['A3D_VALIDATION_OUTPUT'])
    atomic_json(output/'receipt.json', {'version': 1, 'run': status, 'result': result, 'setup': setup,
                'scope': 'ISOLATED_NATIVE_DEVELOPMENT_OPERATION', 'product_acceptance': 'NOT_GRANTED'})
    print('NATIVE_OPERATION_STATUS='+status['status'], flush=True)
    return status


if __name__ == '__main__':
    main()
