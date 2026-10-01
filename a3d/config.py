import ipaddress
import os
from pathlib import Path
from urllib.parse import urlsplit
from .core import ROOT, StudioError, contract, read_json

def load_config(path=None):
    configured = path or os.environ.get("A3D_CONFIG")
    if not configured and os.environ.get("PLUGIN_DATA"):
        candidate = Path(os.environ["PLUGIN_DATA"]) / "config.json"
        if candidate.is_file():
            configured = candidate
    if not configured and (ROOT / "config.local.json").is_file():
        configured = ROOT / "config.local.json"
    cfg = contract("config", read_json(configured or ROOT / "templates/config.json"))
    parsed = urlsplit(cfg["comfyui"]["base_url"])
    try:
        local = parsed.hostname == "localhost" or ipaddress.ip_address(parsed.hostname).is_loopback
        port = parsed.port
    except ValueError:
        local, port = False, None
    if parsed.scheme != "http" or not local or not port or parsed.path not in ("", "/") or parsed.username or parsed.password or parsed.query or parsed.fragment:
        raise StudioError("V1 requires an explicit local HTTP endpoint such as http://127.0.0.1:8188")
    return cfg
