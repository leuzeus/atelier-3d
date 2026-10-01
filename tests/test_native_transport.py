import io
import json
import os
import subprocess
import sys
import unittest
from unittest.mock import patch
from a3d.config import load_config
from a3d.core import ROOT, StudioError
from a3d.official_mcp import OfficialMCP, OfficialToolError

class NativeTransportTests(unittest.TestCase):
    def client(self):
        return OfficialMCP(load_config(ROOT/"templates/config.json"),ROOT)

    def test_real_stdio_discovery_environment_results_and_elicitation(self):
        real_popen=subprocess.Popen
        def spawn(argv,**kwargs):
            self.assertEqual(argv,[sys.executable])
            return real_popen([sys.executable,"-B",str(ROOT/"tests/fake_official_mcp.py")],**kwargs)
        with patch("a3d.official_mcp.shutil.which",return_value=sys.executable), \
             patch("a3d.official_mcp.subprocess.Popen",side_effect=spawn), \
             patch.dict(os.environ,{"COMFYUI_URL":"https://example.invalid","COMFY_API_KEY":"synthetic-key"}):
            client=self.client()
            with client as native:
                self.assertIn("text-result",native.names)
                probe=native.call("probe")
                self.assertEqual(probe["url"],"http://127.0.0.1:8188")
                self.assertEqual(probe["project"],str(ROOT.resolve()))
                self.assertTrue(probe["remote_removed"]); self.assertTrue(probe["key_removed"])
                self.assertEqual(native.call("text-result"),{"answer":42})
                self.assertTrue(native.call("elicitation")["rejected"])
                with self.assertRaises(OfficialToolError): native.call("error-result")
                with self.assertRaises(StudioError): native.call("not-discovered")
            self.assertIsNone(client.process)

    def test_missing_binary_fails_without_install(self):
        client=self.client()
        with patch("a3d.official_mcp.shutil.which",return_value=None), self.assertRaises(StudioError):
            client.__enter__()
        self.assertIsNone(client.process)

    def test_invalid_transport_is_not_success(self):
        client=self.client(); client._reader(io.StringIO("invalid json\n"))
        client.send=lambda msg: None
        with self.assertRaises(StudioError): client.rpc("ping",{})

    def test_notification_stream_cannot_bypass_deadline(self):
        client=self.client(); client.send=lambda msg: None
        client.responses.put({"method":"notifications/progress"})
        client.responses.put({"method":"notifications/progress"})
        with patch("a3d.official_mcp.time.monotonic",side_effect=[0,1,1,46]):
            with self.assertRaisesRegex(StudioError,"timeout"): client.rpc("ping",{})
