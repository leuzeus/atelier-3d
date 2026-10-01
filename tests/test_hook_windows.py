import json
import os
from pathlib import Path
import shutil
import subprocess
import sys
import tempfile
import unittest

from a3d.core import ROOT


@unittest.skipUnless(os.name == "nt", "Windows command integration")
class WindowsHookTests(unittest.TestCase):
    def test_commands_work_in_cmd_and_powershell_with_local_paths(self):
        # The previous CMD-only command failed before Python under native PowerShell.
        # Use space/non-ASCII paths and a controlled handler to verify stdin and config.
        work = ROOT / "work/test-runs"
        work.mkdir(parents=True, exist_ok=True)
        declarations = json.loads((ROOT / "hooks/hooks.json").read_text(encoding="utf-8"))["hooks"]
        with tempfile.TemporaryDirectory(prefix="hooks espace été ", dir=work) as tmp:
            root = Path(tmp)
            hooks = root / "hooks"
            hooks.mkdir()
            shutil.copy2(ROOT / "hooks/launch.py", hooks / "launch.py")
            config = root / "configuration été.json"
            config.write_text("{}", encoding="utf-8")
            (hooks / "runtime.local.json").write_text(json.dumps({"python": sys.executable, "config": str(config)}), encoding="utf-8")
            (hooks / "handler.py").write_text(
                "import json,os,sys\ne=json.load(sys.stdin)\n"
                "print(json.dumps({'event':e['hook_event_name'],'label':e['label'],'config':os.environ['A3D_CONFIG']}))\n",
                encoding="utf-8")
            env = dict(os.environ, PLUGIN_ROOT=str(root))
            shells = [("cmd", os.environ.get("COMSPEC", "cmd.exe"))]
            powershell = shutil.which("pwsh") or shutil.which("powershell")
            self.assertIsNotNone(powershell, "A PowerShell executable is required for this regression")
            shells.append(("powershell", powershell))
            for event, groups in declarations.items():
                command = groups[0]["hooks"][0]["commandWindows"]
                for shell, program in shells:
                    with self.subTest(event=event, shell=shell):
                        argv = (f'"{program}" /C "{command}"' if shell == "cmd" else
                                [program, "-NoLogo", "-NoProfile", "-Command", command])
                        run = subprocess.run(argv, input=json.dumps({"hook_event_name": event, "label": "référence"}),
                            env=env, cwd=root, capture_output=True, text=True, encoding="utf-8", timeout=10,
                            creationflags=subprocess.CREATE_NO_WINDOW)
                        self.assertEqual(run.returncode, 0, run.stderr)
                        self.assertEqual(json.loads(run.stdout), {"event": event, "label": "référence", "config": str(config)})

    def test_real_stop_hook_outside_project_is_noop(self):
        command = json.loads((ROOT / "hooks/hooks.json").read_text(encoding="utf-8"))["hooks"]["Stop"][0]["hooks"][0]["commandWindows"]
        program = shutil.which("pwsh") or shutil.which("powershell")
        self.assertIsNotNone(program)
        run = subprocess.run([program, "-NoLogo", "-NoProfile", "-Command", command],
            input=json.dumps({"hook_event_name": "Stop", "cwd": str(ROOT), "stop_hook_active": False}),
            env=dict(os.environ, PLUGIN_ROOT=str(ROOT)), cwd=ROOT, capture_output=True, text=True,
            encoding="utf-8", timeout=10, creationflags=subprocess.CREATE_NO_WINDOW)
        self.assertEqual(run.returncode, 0, run.stderr)
        self.assertEqual(json.loads(run.stdout), {})
