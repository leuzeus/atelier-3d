"""Prepare a Windows Codex compatibility marketplace; never edits Codex caches or hook trust."""
import argparse
import json
import os
from pathlib import Path
import shutil
import sys

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))
from scripts.package_plugin import inventory
from a3d.config import load_config


def write_json(path, value):
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps(value, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")


def prepare(config_path, python_path):
    if os.name != "nt":
        raise ValueError("This installation profile is qualified only on Windows")
    config_path = Path(config_path).resolve(strict=True)
    python_path = Path(python_path).resolve(strict=True)
    if not config_path.is_file() or not python_path.is_file():
        raise ValueError("Configuration and Python must be existing files")
    for value in (str(config_path), str(python_path)):
        if any(char in value for char in ('"', '%', '!', '\r', '\n')):
            raise ValueError("Path cannot safely be embedded in the Windows hook command")
    config = load_config(config_path)
    manifest = json.loads((ROOT / 'plugin.json').read_text(encoding='utf-8'))
    name, version = manifest['name'], manifest['version']
    if any(c not in 'abcdefghijklmnopqrstuvwxyz0123456789-.' for c in name + version):
        raise ValueError("Unsafe plugin identity or version")
    market = ROOT / '.local/marketplace'
    stage = market / 'plugins' / (name + '-' + version)
    if not stage.resolve().is_relative_to(ROOT.resolve()):
        raise ValueError("Marketplace must stay inside this checkout")
    if stage.exists():
        raise ValueError("Version already prepared; preserve it and increment the source version")
    files = inventory(ROOT)
    stage.mkdir(parents=True)
    for path in files:
        relative = path.relative_to(ROOT)
        # Codex 0.159.2 ignores all plugin hooks when a root plugin.json exists.
        target = stage / ('plugin.portable.json' if relative.as_posix() == 'plugin.json' else relative)
        target.parent.mkdir(parents=True, exist_ok=True)
        shutil.copy2(path, target)
    mcp_path = stage / '.codex-plugin/mcp.json'
    mcp = json.loads(mcp_path.read_text(encoding='utf-8'))
    server = mcp['mcpServers']['studio']
    server['command'] = str(python_path)
    temp = ROOT / '.local/tmp'
    temp.mkdir(parents=True, exist_ok=True)
    server['env'].update(A3D_CONFIG=str(config_path), TEMP=str(temp), TMP=str(temp),
                         PYTHONUTF8='1', DO_NOT_TRACK='1', COMFY_NO_TELEMETRY='1',
                         COMFY_CACHE_DIR=str(Path(config['comfyui']['data_root']) / 'cache/comfy-cli'))
    write_json(mcp_path, mcp)
    # Do not embed CMD syntax in commandWindows: Codex may select PowerShell.
    # The common Python bootstrap handles paths and passes stdin unchanged.
    write_json(stage / 'hooks/runtime.local.json', {'python': str(python_path), 'config': str(config_path)})
    catalog = {'name': name + '-local', 'interface': {'displayName': 'Atelier 3D local'},
               'plugins': [{'name': name, 'source': {'source': 'local',
                   'path': './' + stage.relative_to(market).as_posix()},
                   'policy': {'installation': 'AVAILABLE', 'authentication': 'ON_INSTALL'},
                   'category': 'Productivity'}]}
    write_json(market / '.agents/plugins/marketplace.json', catalog)
    return {'marketplace': str(market), 'stage': str(stage), 'version': version,
            'install': 'codex plugin add ' + name + '@' + name + '-local',
            'hooks': 'Require native user trust review; this script does not grant it'}


if __name__ == '__main__':
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--config', default=str(ROOT / 'config.local.json'))
    parser.add_argument('--python', default=str(ROOT / '.venv/Scripts/python.exe'))
    args = parser.parse_args()
    print(json.dumps(prepare(args.config, args.python), indent=2))
