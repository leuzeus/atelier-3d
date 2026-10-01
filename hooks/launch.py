"""Shell-independent hook bootstrap; machine paths stay in local install data."""
import json
import os
from pathlib import Path
import subprocess
import sys


def main():
    directory = Path(__file__).resolve().parent
    local = directory / "runtime.local.json"
    runtime = json.loads(local.read_text(encoding="utf-8")) if local.is_file() else {}
    interpreter = runtime.get("python", sys.executable)
    env = dict(os.environ, PYTHONUTF8="1", PYTHONIOENCODING="utf-8")
    if runtime.get("config"):
        env["A3D_CONFIG"] = runtime["config"]
    return subprocess.run(
        [interpreter, "-X", "utf8", "-B", str(directory / "handler.py")],
        env=env,
    ).returncode


if __name__ == "__main__":
    raise SystemExit(main())
