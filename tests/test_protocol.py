import ast
import importlib.util
import json
import subprocess
import sys
import unittest
from pathlib import Path

from a3d.core import ROOT, StudioError
from a3d.server import Server
from a3d.tools import TOOLS, call


class ProtocolTests(unittest.TestCase):
    def test_runtime_versions_match_both_manifests_and_pyproject(self):
        import tomllib
        from a3d import __version__
        expected=json.loads((ROOT/'plugin.json').read_text(encoding='utf-8'))['version']
        self.assertEqual(__version__,expected)
        self.assertEqual(tomllib.loads((ROOT/'pyproject.toml').read_text(encoding='utf-8'))['project']['version'],expected)
        self.assertEqual(Server().handle({'jsonrpc':'2.0','id':1,'method':'initialize','params':{}})['result']['serverInfo']['version'],expected)

    def test_installed_compatibility_layout_starts_and_reports_version(self):
        import shutil
        import tempfile
        (ROOT/'work/test-runs').mkdir(parents=True,exist_ok=True)
        with tempfile.TemporaryDirectory(dir=ROOT/'work/test-runs') as tmp:
            target=Path(tmp)
            for folder in ('a3d','servers','templates','schemas','.codex-plugin'):
                shutil.copytree(ROOT/folder,target/folder,ignore=shutil.ignore_patterns('__pycache__'))
            shutil.copy2(ROOT/'plugin.json',target/'plugin.portable.json')
            self.assertFalse((target/'plugin.json').exists())
            messages=[{'jsonrpc':'2.0','id':1,'method':'initialize','params':{}},
                {'jsonrpc':'2.0','method':'notifications/initialized'},
                {'jsonrpc':'2.0','id':2,'method':'tools/call','params':{'name':'studio_doctor','arguments':{'live_comfy':False}}}]
            run=subprocess.run([sys.executable,'-B',str(target/'servers/studio/main.py')],
                input='\n'.join(json.dumps(v) for v in messages)+'\n',cwd=target,
                capture_output=True,text=True,encoding='utf-8',timeout=10)
            self.assertEqual(run.returncode,0,run.stderr)
            output=[json.loads(v) for v in run.stdout.splitlines()]
            self.assertFalse(output[1]['result']['isError'])
            doctor=json.loads(output[1]['result']['content'][0]['text'])
            self.assertEqual(doctor['plugin']['version'],output[0]['result']['serverInfo']['version'])
            self.assertEqual(doctor['plugin']['status'],'PASS')

    def initialized(self):
        s=Server()
        s.handle({"jsonrpc":"2.0","id":1,"method":"initialize","params":{"protocolVersion":"2025-06-18"}})
        s.handle({"jsonrpc":"2.0","method":"notifications/initialized"})
        return s

    def test_lifecycle_and_discovery(self):
        s=self.initialized(); response=s.handle({"jsonrpc":"2.0","id":2,"method":"tools/list"})
        self.assertGreater(len(response["result"]["tools"]),15)

    def test_body_path_review_public_arguments_and_artifact_annotation(self):
        from unittest.mock import patch
        descriptor=TOOLS['studio_prepare_body_path_review']['descriptor']
        self.assertFalse(descriptor['annotations']['readOnlyHint'])
        self.assertFalse(descriptor['annotations']['destructiveHint'])
        arguments={'project_root':'selected-project','body_profile_path':'profile.json',
                   'specification_path':'paths.json','output_dir':'preparation/fresh'}
        with patch('a3d.tools.Project', return_value='project') as project, \
                patch('a3d.body_source_paths.prepare_project_body_path_review',
                      return_value={'status':'BODY_SOURCE_PATH_REVIEW_PREPARED'}) as prepare:
            self.assertEqual(call('studio_prepare_body_path_review',arguments),
                             {'status':'BODY_SOURCE_PATH_REVIEW_PREPARED'})
            project.assert_called_once_with('selected-project')
            prepare.assert_called_once_with('project','profile.json','paths.json','preparation/fresh')
        with self.assertRaises(StudioError):
            call('studio_prepare_body_path_review',dict(arguments, implicit_anatomy=True))

    def test_preinitialize_tools_refused(self):
        s=Server(); r=s.handle({"jsonrpc":"2.0","id":1,"method":"tools/list"})
        self.assertIn("error",r)

    def test_notification_has_no_response(self):
        self.assertIsNone(Server().handle({"jsonrpc":"2.0","method":"notifications/initialized"}))

    def test_unknown_tool_is_protocol_error(self):
        r=self.initialized().handle({"jsonrpc":"2.0","id":2,"method":"tools/call","params":{"name":"delete-everything"}})
        self.assertEqual(r["error"]["code"],-32602)

    def test_invalid_arguments_are_tool_error(self):
        r=self.initialized().handle({"jsonrpc":"2.0","id":2,"method":"tools/call","params":{"name":"studio_project_status","arguments":{}}})
        self.assertTrue(r["result"]["isError"])

    def test_stdio_smoke_process(self):
        messages=[
          {"jsonrpc":"2.0","id":1,"method":"initialize","params":{"protocolVersion":"2025-06-18"}},
          {"jsonrpc":"2.0","method":"notifications/initialized"},
          {"jsonrpc":"2.0","id":2,"method":"tools/list"},
          {"jsonrpc":"2.0","id":3,"method":"tools/call","params":{"name":"studio_doctor","arguments":{"live_comfy":False}}},
          {"jsonrpc":"2.0","id":4,"method":"ping"}]
        run=subprocess.run([sys.executable,"-B",str(ROOT/"servers/studio/main.py")],
            input="\n".join(json.dumps(v) for v in messages)+"\n",capture_output=True,text=True,encoding="utf-8",timeout=10)
        self.assertEqual(run.returncode,0,run.stderr)
        output=[json.loads(v) for v in run.stdout.splitlines()]
        self.assertEqual([r["id"] for r in output],[1,2,3,4])
        self.assertFalse(output[2]["result"]["isError"])

    def test_hook_stop_has_loop_guard(self):
        from tests.test_core import Case
        import tempfile
        from tests.support import ready_project
        spec=importlib.util.spec_from_file_location("studio_hook",ROOT/"hooks/handler.py")
        mod=importlib.util.module_from_spec(spec); spec.loader.exec_module(mod)
        (ROOT/"work/test-runs").mkdir(parents=True,exist_ok=True)
        with tempfile.TemporaryDirectory(dir=ROOT/"work/test-runs") as root:
            ready_project(root)
            event={"cwd":root,"hook_event_name":"Stop"}
            self.assertEqual(mod.handle(event)["decision"],"block")
            self.assertEqual(mod.handle({**event,"stop_hook_active":True}),{})

    def test_all_delivered_python_parses(self):
        from scripts.package_plugin import inventory
        for path in inventory():
            if path.suffix == ".py":
                with self.subTest(path=path): ast.parse(path.read_text(encoding="utf-8-sig"))

    def test_schemas_and_skill_links_exist(self):
        from a3d.core import read_json
        import re
        self.assertEqual(len(list((ROOT/"skills").glob("*/SKILL.md"))),12)
        for path in (ROOT/"skills").glob("*/SKILL.md"):
            text=path.read_text(encoding="utf-8")
            self.assertIn("name: "+path.parent.name,text)
            for relative in re.findall(r"\]\(([^)]+)\)",text):
                self.assertTrue((path.parent/relative).resolve().is_file(),relative)
        for path in (ROOT/"schemas").glob("*.json"): read_json(path)

    def test_distribution_contains_mcp_entrypoint_and_excludes_machine_state(self):
        from scripts.package_plugin import inventory
        files={p.relative_to(ROOT).as_posix() for p in inventory()}
        self.assertIn("servers/studio/main.py",files)
        self.assertIn("mcp.json",files)
        self.assertIn("hooks/handler.py",files)
        self.assertIn("skills/patronage/SKILL.md",files)
        self.assertIn("templates/agents/atelier3d-patronage.toml",files)
        self.assertNotIn("config.local.json",files)
        self.assertFalse(any(name.startswith("work/") or ".sqlite3" in name for name in files))


class HealthContractTests(unittest.TestCase):
    def test_native_nested_server_state_is_normalized(self):
        from unittest.mock import MagicMock
        from a3d.comfy import Comfy
        native=MagicMock()
        native.__enter__.return_value=native
        native.call.return_value={"server":{"running":True,"url":"http://127.0.0.1:8188"},"workspace":{"path":"example"}}
        result=Comfy(factory=lambda *args:native).health()
        self.assertTrue(result["running"])
        self.assertEqual(result["workspace"],{"path":"example"})

    def test_native_stopped_server_is_not_available(self):
        from unittest.mock import MagicMock
        from a3d.comfy import Comfy
        native=MagicMock();native.__enter__.return_value=native
        native.call.return_value={"server":{"running":False}}
        self.assertFalse(Comfy(factory=lambda *args:native).health()["running"])

    def test_unknown_server_shape_does_not_claim_health(self):
        from unittest.mock import MagicMock
        from a3d.comfy import Comfy
        native=MagicMock();native.__enter__.return_value=native
        native.call.return_value={"server":{}}
        with self.assertRaises(StudioError):Comfy(factory=lambda *args:native).health()
