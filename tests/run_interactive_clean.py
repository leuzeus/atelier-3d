"""Opt-in official MCP integration test; launches its OWN hidden GUI Blender.

python tests/run_interactive_clean.py --blender ... --addon ... --output G:/...
No connection to port 9876 or to any pre-existing Blender is made.
"""
import argparse,json,os,socket,subprocess,time
from pathlib import Path

def main():
    p=argparse.ArgumentParser()
    p.add_argument('--blender',required=True);p.add_argument('--addon',required=True)
    p.add_argument('--output',required=True);p.add_argument('--runtime');p.add_argument('--body-selection')
    p.add_argument('--fitting-preparation',action='store_true')
    p.add_argument('--catalog-selection',action='store_true')
    args=p.parse_args();out=Path(args.output).resolve();out.mkdir(parents=True,exist_ok=True)
    if (out/'owned-pid.txt').exists():raise ValueError('Choose a fresh isolated output directory')
    root=Path(args.runtime).resolve() if args.runtime else Path(__file__).resolve().parents[1]
    with socket.socket() as reserve:
        reserve.bind(('127.0.0.1',0));port=reserve.getsockname()[1]
    assert port!=9876
    addon=Path(args.addon).resolve()
    bootstrap=out/'bootstrap.py'
    bootstrap.write_text(f'''import sys,importlib.util,bpy
sys.dont_write_bytecode=True
sys.path.insert(0,{str(root)!r})
spec=importlib.util.spec_from_file_location('atelier_test_mcp',{str(addon/'__init__.py')!r},submodule_search_locations=[{str(addon)!r}])
module=importlib.util.module_from_spec(spec);sys.modules[spec.name]=module
entry=bpy.context.preferences.addons.new();entry.module=spec.name
spec.loader.exec_module(module);module.register()
prefs=bpy.context.preferences.addons[spec.name].preferences
prefs.host='127.0.0.1';prefs.port={port};prefs.use_autostart=False
bpy.ops.blmcp.server_start()
''',encoding='utf-8')
    env=dict(os.environ,BLENDER_USER_RESOURCES=str(out/'profile'),PYTHONDONTWRITEBYTECODE='1',
        APPDATA=str(out/'appdata'),LOCALAPPDATA=str(out/'localappdata'),
        TMP=str(out),TEMP=str(out))
    for directory in ('profile','appdata','localappdata'):
        (out/directory).mkdir(parents=True,exist_ok=True)
    log=(out/'interactive.log').open('w',encoding='utf-8')
    # Launch hidden via native PowerShell; exactly this owned PID is stopped.
    def quote(s):return "'"+str(s).replace("'","''")+"'"
    command=('$p=Start-Process -FilePath '+quote(args.blender)+' -ArgumentList '+quote(
        '--factory-startup --disable-autoexec --online-mode --python "'+str(bootstrap)+'"')+
        ' -WindowStyle Hidden -RedirectStandardOutput '+quote(out/'blender.stdout.log')+
        ' -RedirectStandardError '+quote(out/'blender.stderr.log')+' -PassThru; '+
        'Set-Content -LiteralPath '+quote(out/'owned-pid.txt')+' -Value $p.Id')
    try:
        subprocess.run(['powershell','-NoProfile','-Command',command],env=env,
            stdout=subprocess.DEVNULL,stderr=log,check=True,
            creationflags=subprocess.CREATE_NO_WINDOW,timeout=15)
        pid=int((out/'owned-pid.txt').read_text(encoding='utf-8-sig').strip())
        def execute(code):
            with socket.create_connection(('127.0.0.1',port),timeout=5) as s:
                s.settimeout(90)
                s.sendall(json.dumps({'type':'execute','code':code,'strict_json':True}).encode()+b'\0')
                chunks=bytearray()
                while b'\0' not in chunks:
                    b=s.recv(65536)
                    if not b:raise RuntimeError('MCP connection closed before result')
                    chunks.extend(b)
                return json.loads(chunks.split(b'\0')[0])
        deadline=time.monotonic()+35
        while True:
            try:response=execute('result={"ready":True}')
            except (ConnectionError,TimeoutError,OSError):
                if time.monotonic()>deadline:raise
                time.sleep(.5);continue
            assert response['status']=='ok',response
            break
        control=execute('import bpy\nbpy.ops.wm.read_factory_settings(use_empty=True)')
        assert control['status']=='error' and 'read_homefile' in control['message'],control
        setup=execute('from tests import interactive_clean_scenario as scenario\nresult=scenario.setup('+repr(str(out))+')')
        assert setup['status']=='ok',setup
        dirty=execute('from tests import interactive_clean_scenario as scenario\nresult=scenario.dirty_trial()')
        assert dirty['status']=='ok',dirty
        run=execute('from tests import interactive_clean_scenario as scenario\nresult=scenario.run()')
        assert run['status']=='ok',run
        fault=execute('from tests import interactive_clean_scenario as scenario\nresult=scenario.failed_rollback()')
        assert fault['status']=='ok',fault
        recovery=execute('from tests import interactive_clean_scenario as scenario\nresult=scenario.recover('+repr(fault['result']['recovery_path'])+')')
        assert recovery['status']=='ok',recovery
        body=execute('from tests import interactive_clean_scenario as scenario\nfrom tests import native_body_source_scenario\nresult=native_body_source_scenario.run(scenario.project,'+repr(args.body_selection)+','+repr(args.catalog_selection)+')')
        assert body['status']=='ok',body
        preparation=None;regional=None;pose=None
        if args.fitting_preparation:
            preparation=execute('from tests import interactive_clean_scenario as scenario\nfrom tests import native_fitting_preparation\nresult=native_fitting_preparation.run('+repr(str(out/'native-preparation'))+',scenario.project)')
            assert preparation['status']=='ok',preparation
            regional=execute('from tests import native_regional_cloth\nresult=native_regional_cloth.run('+repr(str(out/'regional-coupons'))+')')
            assert regional['status']=='ok',regional
            pose=execute('from tests import native_pose_operation\nresult=native_pose_operation.run('+repr(str(out/'pose-operation'))+')')
            assert pose['status']=='ok',pose
            restored=execute('import bpy\nfrom a3d.core import read_json\nfrom tests import interactive_clean_scenario as scenario\nbpy.ops.wm.open_mainfile(filepath=read_json(scenario.project.data/"blender/session.json")["working"],load_ui=False)\nresult={"fixture_scene_restored":True}')
            assert restored['status']=='ok',restored
        continuity=execute('from tests import interactive_clean_scenario as scenario\nresult=scenario.snapshot()')
        assert continuity['status']=='ok' and continuity['result']==setup['result'],continuity
        runtime=execute('from blender.bootstrap import dispatch_current\nfrom tests import interactive_clean_scenario as scenario\nresult=dispatch_current(str(scenario.project.root),"inspect",{})["runtime"]')
        assert runtime['status']=='ok' and Path(runtime['result']['root']).resolve()==root,runtime
        proof={'status':'PASS','runtime':runtime['result'],'port':port,'background':False,
            'official_guard_active':True,'separate_requests_after_reload':'PASS',
            'baseline':setup['result'],'scenario':run['result'],'continuity':continuity['result']}
        proof.update(failed_rollback=fault['result'],native_recovery=recovery['result'],body_source=body['result'])
        if preparation:proof.update(fitting_preparation=preparation['result'],regional_stiffness=regional['result'],pose_operation=pose['result'])
        (out/'interactive-result.json').write_text(json.dumps(proof,indent=2),encoding='utf-8')
        print(json.dumps({'status':'PASS','proof':str(out/'interactive-result.json'),'runtime':runtime['result']}),flush=True)
    finally:
        log.close()
        owned=out/'owned-pid.txt'
        if owned.exists():
            pid=int(owned.read_text(encoding='utf-8-sig').strip())
            stop=('$p=Get-CimInstance Win32_Process -Filter '+quote('ProcessId='+str(pid))+
                '; if ($p.CommandLine -and $p.CommandLine.Contains('+quote(bootstrap)+')) { Stop-Process -Id '+str(pid)+' }')
            subprocess.run(['powershell','-NoProfile','-Command',stop],
                creationflags=subprocess.CREATE_NO_WINDOW,timeout=15)

if __name__=='__main__':main()
