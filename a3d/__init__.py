"""Local, resumable 3D production contracts."""
import json
from pathlib import Path

# This manifest is present in both the portable checkout and the Windows
# compatibility installation, where root plugin.json is intentionally renamed.
__version__ = json.loads((Path(__file__).resolve().parents[1] /
    '.codex-plugin/plugin.json').read_text(encoding='utf-8-sig'))['version']
