"""Bounded stdio client for official Comfy-Org/comfy-mcp; no ComfyUI HTTP API."""
import json
import os
import queue
import shutil
import subprocess
import threading
import time
from pathlib import Path
from .core import StudioError


class OfficialToolError(StudioError):
    pass


class OfficialMCP:
    def __init__(self, config, project_root=None):
        self.config, self.project_root = config, project_root
        self.process, self.sequence = None, 0
        self.responses, self.names = queue.Queue(), set()

    def __enter__(self):
        opts = self.config["comfyui"]
        command = opts["mcp_command"]
        executable = command if Path(command).is_absolute() else shutil.which(command)
        cli = opts["cli_command"]
        if not executable or not Path(executable).is_file():
            raise StudioError("Official comfy-mcp not installed/configured; installation is a separate step")
        if not (shutil.which(cli) or Path(cli).is_file()):
            raise StudioError("Official comfy-cli not installed/configured; comfy >= 1.14.0 required")
        env = os.environ.copy()
        for key in ("COMFYUI_URL", "COMFYUI_HOST", "COMFYUI_PORT", "COMFY_API_KEY", "COMFY_PROJECT"):
            env.pop(key, None)
        env.update(COMFY_LOCAL_URL=opts["base_url"], COMFY_BIN=cli)
        if self.project_root:
            env["COMFY_PROJECT"] = str(Path(self.project_root).resolve(strict=True))
        self.process = subprocess.Popen([str(executable)], stdin=subprocess.PIPE, stdout=subprocess.PIPE,
            stderr=subprocess.DEVNULL, encoding="utf-8", text=True, env=env, bufsize=1,
            creationflags=subprocess.CREATE_NO_WINDOW if os.name == "nt" else 0)
        threading.Thread(target=self._reader, args=(self.process.stdout,), daemon=True).start()
        try:
            reply = self.rpc("initialize", {"protocolVersion": "2025-06-18", "capabilities": {},
                "clientInfo": {"name": "atelier-3d", "version": "0.1.3"}})
            if "tools" not in reply.get("capabilities", {}):
                raise StudioError("Official MCP has no tools capability")
            self.send({"jsonrpc": "2.0", "method": "notifications/initialized"})
            page = self.rpc("tools/list", {})
            for _ in range(20):
                self.names.update(t["name"] for t in page.get("tools", []))
                if not page.get("nextCursor"):
                    return self
                page = self.rpc("tools/list", {"cursor": page["nextCursor"]})
            raise StudioError("Too many native discovery pages")
        except BaseException:
            self.close()
            raise

    def _reader(self, stream):
        try:
            while True:
                line = stream.readline(16 * 1024 * 1024 + 1)
                if not line:
                    break
                if len(line) > 16 * 1024 * 1024:
                    raise ValueError("Oversized MCP response")
                self.responses.put(json.loads(line))
        except Exception:
            self.responses.put(StudioError("Official MCP transport failed"))
        finally:
            self.responses.put(EOFError())

    def send(self, value):
        self.process.stdin.write(json.dumps(value) + "\n")
        self.process.stdin.flush()

    def rpc(self, method, params):
        self.sequence += 1
        rid = self.sequence
        self.send({"jsonrpc": "2.0", "id": rid, "method": method, "params": params})
        deadline = time.monotonic() + self.config["comfyui"]["request_timeout_seconds"]
        while True:
            if time.monotonic() >= deadline:
                raise StudioError("Official MCP timeout; submission outcome may be unknown")
            try:
                message = self.responses.get(timeout=max(.001, deadline - time.monotonic()))
            except queue.Empty:
                raise StudioError("Official MCP timeout; submission outcome may be unknown") from None
            if isinstance(message, BaseException):
                raise StudioError("Official MCP ended or returned invalid output")
            if "method" in message:
                if "id" in message:
                    self.send({"jsonrpc": "2.0", "id": message["id"], "error": {"code": -32601,
                        "message": "Interactive action must use the native user client"}})
                continue
            if message.get("id") != rid:
                continue
            if "error" in message:
                raise OfficialToolError("Official MCP protocol call failed")
            return message.get("result", {})

    def call(self, name, arguments=None):
        if name not in self.names:
            raise StudioError(f"Official MCP capability missing: {name}")
        result = self.rpc("tools/call", {"name": name, "arguments": arguments or {}})
        if result.get("isError"):
            raise OfficialToolError(f"Official MCP {name} failed; inspect native diagnostics")
        data = result.get("structuredContent")
        if data is None:
            for block in result.get("content", []):
                if block.get("type") == "text":
                    try:
                        data = json.loads(block["text"])
                        break
                    except (ValueError, KeyError):
                        pass
        if isinstance(data, dict) and set(data) == {"result"}:
            data = data["result"]
        if not isinstance(data, dict):
            raise StudioError(f"Unrecognized official {name} result")
        if data.get("error") or data.get("ok") is False:
            raise OfficialToolError(f"Official MCP {name} reports failure")
        return data

    def close(self):
        if self.process:
            try:
                self.process.stdin.close()
                self.process.wait(timeout=2)
            except (OSError, subprocess.TimeoutExpired):
                self.process.terminate()
                try:
                    self.process.wait(timeout=2)
                except subprocess.TimeoutExpired:
                    self.process.kill()
                    self.process.wait(timeout=2)
            self.process.stdout.close()
            self.process = None

    def __exit__(self, *args):
        self.close()
