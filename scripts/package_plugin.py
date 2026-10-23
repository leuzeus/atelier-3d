"""Allowlist-only source bundle. Never includes local config, models or state."""
import argparse
import hashlib
import json
from pathlib import Path
import sys
import zipfile

ROOT=Path(__file__).resolve().parents[1]
ROOT_FILES=("plugin.json","mcp.json","README.md","VALIDATION.md","CHANGELOG.md","LICENSE","SECURITY.md","CONTRIBUTING.md","pyproject.toml",".gitignore",".gitattributes","BUG-2026-10-03-completude-pieces-blender.md")
DIRS=(".codex-plugin","a3d","assets","blender","hooks","references","schemas","scripts","servers","skills","templates","tests","workflows")
EXTENSIONS={".py",".json",".md",".svg",".png",".ps1"}

def inventory(root=ROOT):
    files=[]
    for name in ROOT_FILES:
        path=root/name
        if not path.is_file(): raise ValueError(f"Missing distribution file: {name}")
        files.append(path)
    for name in DIRS:
        base=root/name
        if not base.is_dir(): raise ValueError(f"Missing directory: {name}")
        for path in base.rglob("*"):
            if path.is_symlink() or (hasattr(path,"is_junction") and path.is_junction()):
                raise ValueError(f"Links cannot be distributed: {path}")
            if path.is_file() and "__pycache__" not in path.parts and path.suffix in EXTENSIONS:
                if not path.resolve().is_relative_to(root.resolve()):
                    raise ValueError("File escaped package root")
                if path.name in ("config.local.json","runtime.local.json",".env"): raise ValueError("Local configuration cannot be distributed")
                files.append(path)
    return sorted(files,key=lambda p:p.relative_to(root).as_posix())

def build(destination):
    target=Path(destination)
    if target.suffix.lower()!=".zip": raise ValueError("Output must end in .zip")
    if not target.parent.is_dir(): raise ValueError("Create the output directory explicitly first")
    files=inventory()
    records={}
    with zipfile.ZipFile(target,"x",compression=zipfile.ZIP_DEFLATED,compresslevel=9) as archive:
        for path in files:
            name=path.relative_to(ROOT).as_posix()
            data=path.read_bytes()
            info=zipfile.ZipInfo(name,(2026,9,30,0,0,0))
            info.compress_type=zipfile.ZIP_DEFLATED
            info.external_attr=0o100644<<16
            archive.writestr(info,data)
            records[name]=hashlib.sha256(data).hexdigest()
        info=zipfile.ZipInfo("PACKAGE-CONTENTS.json",(2026,9,30,0,0,0))
        info.compress_type=zipfile.ZIP_DEFLATED
        archive.writestr(info,json.dumps({"version":json.loads((ROOT/"plugin.json").read_text(encoding="utf-8"))["version"],"files":records},indent=2).encode())
    with zipfile.ZipFile(target) as archive:
        if archive.testzip() is not None: raise ValueError("Corrupt archive")
        listed=json.loads(archive.read("PACKAGE-CONTENTS.json"))["files"]
        if set(archive.namelist()) != set(listed)|{"PACKAGE-CONTENTS.json"}: raise ValueError("Inventory mismatch")
        for name,expected in listed.items():
            if hashlib.sha256(archive.read(name)).hexdigest()!=expected: raise ValueError("Checksum mismatch")
    return {"path":str(target.resolve()),"files":len(files),"bytes":target.stat().st_size,
            "sha256":hashlib.sha256(target.read_bytes()).hexdigest(),"checksums":"PASS"}

if __name__=="__main__":
    parser=argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--output",required=True)
    args=parser.parse_args()
    try: print(json.dumps(build(args.output),indent=2))
    except Exception as exc:
        print(str(exc),file=sys.stderr); raise SystemExit(1)
