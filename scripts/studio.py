from pathlib import Path
import argparse
import json
import sys

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))
from a3d.core import StudioError, atomic_json, read_json, ROOT
from a3d.tools import TOOLS, call, doctor

def main():
    parser = argparse.ArgumentParser(description="Atelier 3D local tools")
    sub = parser.add_subparsers(dest="command", required=True)
    sub.add_parser("tools")
    d = sub.add_parser("doctor")
    d.add_argument("--project-root")
    d.add_argument("--live-comfy", action="store_true")
    c = sub.add_parser("call")
    c.add_argument("tool", choices=sorted(TOOLS))
    c.add_argument("--arguments", required=True, help="UTF-8 JSON file of tool arguments")
    cfg = sub.add_parser("configure")
    cfg.add_argument("--output", required=True)
    args = parser.parse_args()
    try:
        if args.command == "tools":
            result = [v["descriptor"] for v in TOOLS.values()]
        elif args.command == "doctor":
            result = doctor(args.project_root, args.live_comfy)
        elif args.command == "configure":
            target = Path(args.output)
            if target.exists():
                raise StudioError("Configuration already exists; edit it explicitly")
            atomic_json(target, read_json(ROOT / "templates/config.json"))
            result = {"path": str(target.resolve()), "next": "Edit then set A3D_CONFIG to this path"}
        else:
            result = call(args.tool, read_json(args.arguments))
        print(json.dumps(result, ensure_ascii=False, indent=2))
    except Exception as exc:
        print(json.dumps({"error": type(exc).__name__, "message": str(exc)}, ensure_ascii=False), file=sys.stderr)
        return 1
    return 0

if __name__ == "__main__":
    raise SystemExit(main())
