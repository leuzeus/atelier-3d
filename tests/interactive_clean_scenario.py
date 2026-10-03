"""Scenario called through the official MCP socket in an isolated GUI Blender.

The runner owns its profile, port and project. Never run on a user's scene.
"""
import copy
from pathlib import Path
import bpy
from a3d.core import StudioError,atomic_json,read_json,sha
from blender.operations import dispatch
from tests.support import ready_project

project=None
baseline=None

def snapshot():
    import atelier_test_mcp
    from atelier_test_mcp import execute_interactive,mcp_to_blender_server
    prefs=bpy.context.preferences
    return {'background':bpy.app.background,'addons':sorted(prefs.addons.keys()),
        'undo_steps':prefs.edit.undo_steps,'mcp_port':prefs.addons['atelier_test_mcp'].preferences.port,
        'mcp_running':mcp_to_blender_server.is_running(),
        'mcp_timer':bpy.app.timers.is_registered(execute_interactive.run)}

def setup(root):
    global project,baseline
    project=ready_project(Path(root)/'project',True)
    bpy.context.preferences.edit.undo_steps=55
    bpy.context.preferences.filepaths.save_version=0
    bpy.context.preferences.filepaths.temporary_directory=str(Path(root))
    bpy.ops.mesh.primitive_cube_add();obj=bpy.context.object;obj.name='OLD_COLLIDER'
    obj.modifiers.new('old_collision','COLLISION')
    dispatch(str(project.root),'prepare',{})
    baseline=snapshot()
    assert not baseline['background'] and baseline['mcp_running'] and baseline['mcp_timer']
    return baseline

def dirty_trial():
    session=read_json(project.data/'blender/session.json')
    source=Path(session['working']);fingerprint=sha(source)
    args={'working_sha256':fingerprint}
    # A real guarded refusal must leave this isolated live scene unchanged.
    bpy.ops.mesh.primitive_cube_add()
    bpy.ops.ed.undo_push(message='Isolated dirty-scene admission test')
    assert bpy.data.is_dirty
    try:dispatch(str(project.root),'start_clean_construction',args)
    except StudioError as error:assert 'Save the current' in str(error)
    else:raise AssertionError('Dirty scene accepted')
    bpy.ops.wm.open_mainfile(filepath=str(source),load_ui=False)
    # The explicit undo push is a fixture-only UI change. Save the restored
    # fixture before binding the immutable witness for the subsequent trials.
    bpy.ops.wm.save_as_mainfile(filepath=str(source),check_existing=False)
    return {'dirty_refused':True}

def run():
    from unittest.mock import patch
    import blender.clean_construction as clean
    session=read_json(project.data/'blender/session.json')
    source=Path(session['working']);fingerprint=sha(source)
    db=sha(project.db);gates=copy.deepcopy(project.state()['gates'])
    args={'working_sha256':fingerprint}
    for value in ('0'*64,):
        try:dispatch(str(project.root),'start_clean_construction',{'working_sha256':value})
        except StudioError as error:assert 'identity changed' in str(error)
        else:raise AssertionError('Stale scene accepted')
    # Failure before the switch: copying the witness fails, no scene reload.
    with patch.object(clean.shutil,'copyfile',side_effect=OSError('before-switch injection')):
        try:dispatch(str(project.root),'start_clean_construction',args)
        except OSError:pass
        else:raise AssertionError('Injected failure missing')
    assert Path(bpy.data.filepath)==source and read_json(project.data/'blender/session.json')==session
    # Failure after the permitted operator: session publication fails once;
    # automatic rollback restores the old scene/session and retains evidence.
    real_atomic=clean.atomic_json
    switched=[]
    def fail_publication(path,data):
        if Path(path)==project.data/'blender/session.json' and data.get('empty_start'):
            switched.append(not bpy.data.objects)
            raise OSError('after-switch injection')
        return real_atomic(path,data)
    with patch.object(clean,'atomic_json',fail_publication):
        try:dispatch(str(project.root),'start_clean_construction',args)
        except OSError as error:assert 'after-switch' in str(error)
        else:raise AssertionError('Injected failure missing')
    assert switched==[True] and Path(bpy.data.filepath)==source and not bpy.data.is_dirty
    assert read_json(project.data/'blender/session.json')==session
    recoveries=list((project.data/'blender').glob('clean-recovery-*.json'))
    assert len(recoveries)==1 and read_json(recoveries[0])['status']=='ROLLED_BACK'
    assert snapshot()==baseline and sha(source)==fingerprint and sha(project.db)==db
    # Real native start through exactly the same MCP execution handler.
    empty=dispatch(str(project.root),'start_clean_construction',args)
    assert not bpy.data.objects and not bpy.context.scene.objects
    assert empty['construction_id'] and Path(bpy.data.filepath)!=source
    assert sha(source)==fingerprint and sha(project.root/empty['witness'])==fingerprint
    assert read_json(project.root/empty['previous_session'])==session
    assert project.state()['gates']==gates and sha(project.db)==db
    assert not project.state().get('pending_blender_operation') and snapshot()==baseline
    return {'status':'PASS','empty_start':empty,'preferences_addon_timer_preserved':True,
        'before_switch_failure':'PASS','after_switch_rollback':'PASS',
        'dirty_stale_refused':'PASS','source_session_db_preserved':True,
        'recovery':recoveries[0].relative_to(project.root).as_posix()}

def failed_rollback():
    from unittest.mock import patch
    import blender.clean_construction as clean
    session=read_json(project.data/'blender/session.json')
    source=Path(session['working']);fingerprint=sha(source);real_atomic=clean.atomic_json
    def fail_publication(path,data):
        if Path(path)==project.data/'blender/session.json' and data.get('working')!=session['working']:
            raise OSError('session publication fault')
        return real_atomic(path,data)
    with patch.object(clean,'atomic_json',fail_publication),patch.object(clean,'_open_source',side_effect=OSError('rollback fault')):
        try:dispatch(str(project.root),'start_clean_construction',{'working_sha256':fingerprint})
        except StudioError as error:assert 'rollback failed' in str(error)
        else:raise AssertionError('Missing rollback failure')
    paths=[p for p in (project.data/'blender').glob('clean-recovery-*.json') if read_json(p)['status']=='ROLLBACK_REQUIRED']
    assert len(paths)==1 and sha(source)==fingerprint and not project.state().get('pending_blender_operation')
    return {'recovery_path':paths[0].relative_to(project.root).as_posix(),'source_sha256':fingerprint}

def recover(path):
    result=dispatch(str(project.root),'recover_clean_construction',{'recovery_path':path})
    assert result['status']=='ROLLED_BACK' and snapshot()==baseline
    assert read_json(project.root/path)['status']=='ROLLED_BACK'
    return result
