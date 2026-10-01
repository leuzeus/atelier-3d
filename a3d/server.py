"""Dependency-free MCP stdio subset: lifecycle, ping, tools/list and tools/call.

Only capabilities implemented here are advertised. All diagnostics go to stderr.
"""
import json
import sys

from . import __version__
from .core import StudioError
from .tools import TOOLS, call

PROTOCOLS = ("2025-06-18", "2025-03-26", "2024-11-05")


def error(request_id, code, message):
    return {"jsonrpc": "2.0", "id": request_id, "error": {"code": code, "message": message}}


class Server:
    def __init__(self):
        self.initialized = False
        self.ready = False

    def handle(self, request):
        if not isinstance(request, dict) or request.get("jsonrpc") != "2.0" or not isinstance(request.get("method"), str):
            return error(None, -32600, "Invalid JSON-RPC request")
        method, request_id = request["method"], request.get("id")
        if "id" not in request:
            if method == "notifications/initialized" and self.initialized:
                self.ready = True
            return None
        if not isinstance(request_id, (int, str)) or isinstance(request_id, bool):
            return error(None, -32600, "Invalid request id")
        params = request.get("params", {})
        if not isinstance(params, dict):
            return error(request_id, -32602, "Invalid params")
        if method == "initialize":
            self.initialized = True
            version = params.get("protocolVersion")
            result = {"protocolVersion": version if version in PROTOCOLS else PROTOCOLS[0],
                      "capabilities": {"tools": {"listChanged": False}},
                      "serverInfo": {"name": "atelier-3d", "version": __version__},
                      "instructions": "Use explicit project roots. Human approval must come from the user. Never infer geometric or artistic success from HTTP completion."}
        elif method == "ping":
            result = {}
        elif not self.ready:
            return error(request_id, -32000, "Initialize and send notifications/initialized first")
        elif method == "tools/list":
            result = {"tools": [v["descriptor"] for v in TOOLS.values()]}
        elif method == "tools/call":
            name = params.get("name")
            if name not in TOOLS:
                return error(request_id, -32602, "Unknown tool")
            try:
                value = call(name, params.get("arguments", {}))
                result = {"content": [{"type": "text", "text": json.dumps(value, ensure_ascii=False, allow_nan=False)}], "structuredContent": value, "isError": False}
            except (StudioError, FileNotFoundError, FileExistsError, KeyError, ValueError) as exc:
                result = {"content": [{"type": "text", "text": str(exc)}], "isError": True}
            except Exception as exc:
                print(f"Tool failed: {type(exc).__name__}", file=sys.stderr)
                result = {"content": [{"type": "text", "text": f"Internal failure: {type(exc).__name__}"}], "isError": True}
        else:
            return error(request_id, -32601, "Method not found")
        return {"jsonrpc": "2.0", "id": request_id, "result": result}


def main():
    if hasattr(sys.stdin, "reconfigure"):
        sys.stdin.reconfigure(encoding="utf-8")
        sys.stdout.reconfigure(encoding="utf-8")
    server = Server()
    while True:
        line = sys.stdin.readline(4 * 1024 * 1024 + 1)
        if not line:
            return
        if len(line) > 4 * 1024 * 1024:
            print("Oversized MCP message; closing transport", file=sys.stderr)
            return
        try:
            response = server.handle(json.loads(line))
        except (ValueError, TypeError):
            response = error(None, -32700, "Invalid JSON")
        if response is not None:
            print(json.dumps(response, ensure_ascii=False, allow_nan=False), flush=True)
