import hashlib
import json
import os
import re
import sys
from pathlib import Path
sys.path.insert(0, str(Path(__file__).resolve().parents[1]))
from a3d.core import ROOT, StudioError, atomic_json, now, read_json
from a3d.store import Project
from a3d.comfy import Comfy
from a3d.guard import admit_operation, parse_code


def locate(cwd):
    path = Path(cwd).resolve()
    for parent in (path, *path.parents):
        if (parent / ".a3d/state.sqlite3").is_file():
            return Project(parent)
    return None


def binding_path(event):
    # Native session identity isolates projectless chats. Never persist raw text.
    session_id = event.get("session_id")
    if not session_id:
        return None
    if os.environ.get("A3D_CONFIG"):
        base = Path(os.environ["A3D_CONFIG"]).resolve().parent / ".local/hook-sessions"
    else:
        base = Path(os.environ.get("PLUGIN_DATA", str(ROOT / ".local"))) / "hook-sessions"
    return base / (hashlib.sha256(str(session_id).encode()).hexdigest() + ".json")


def find_project(event):
    args = event.get("tool_input", {})
    if isinstance(args, str):
        try:
            args = json.loads(args)
        except ValueError:
            args = {}
    if not isinstance(args, dict):
        args = {}
    explicit = args.get("project_root")
    project = locate(explicit or event.get("cwd", "."))
    binding = binding_path(event)
    if explicit and project and event.get("tool_name", "").startswith("mcp__studio__") and binding:
        atomic_json(binding, {"project_root": str(project.root), "project_id": project.state()["project_id"]})
    if not project and binding and binding.exists():
        rec = read_json(binding)
        project = Project(rec["project_root"])
        if project.state()["project_id"] != rec["project_id"]:
            raise StudioError("Bound project identity changed; explicitly select the intended project")
    return project, args


def deny(reason):
    return {"hookSpecificOutput": {"hookEventName": "PreToolUse", "permissionDecision": "deny", "permissionDecisionReason": str(reason)}}


def handle(event):
    kind = event.get("hook_event_name", "")
    project, args = find_project(event)
    if not project:
        return {}
    summary = project.summary()
    if kind == "PreToolUse":
        tool = event.get("tool_name", "")
        try:
            if tool.startswith("mcp__blender"):
                short = tool.split("__")[-1]
                readonly = ("get_blendfile_summary_", "get_object_detail_summary", "get_objects_summary", "get_python_api_docs", "get_screenshot_", "search_api_docs", "search_manual_docs")
                if not short.startswith(readonly):
                    if short == 'jump_to_view3d_object_by_name':
                        raise StudioError('Use studio_blender_operation frame_view with component_id and object_name for guarded viewport framing; direct navigation may change visibility or target a foreign scene')
                    if short not in ("execute_blender_code", "execute_blender_code_for_cli"):
                        raise StudioError("Use a guarded Blender operation for scene/output changes")
                    payload = parse_code(args.get("code", ""))
                    if Path(payload["project_root"]).resolve() != project.root:
                        raise StudioError("Blender operation targets another project")
                    admit_operation(project, payload["operation"], payload["arguments"])
            elif tool.endswith(("comfy_submit_workflow", "comfy_run_template")):
                client = Comfy()
                spec, graph = client.template(args.get("workflow_id", args.get("template_id")), args.get("parameters", args.get("parameter_overrides", {})))
                client.admit(project, args["component_id"], spec, graph)
            elif "comfy" in tool.lower() and tool.endswith(("run_workflow", "run_template")):
                raise StudioError("Submit Comfy production through Studio so route and construction approval are checked")
            elif tool.split(".")[-1] in ("exec_command", "shell_command", "shell", "run_shell_command"):
                command = str(args.get("cmd", args.get("command", "")))
                if re.search(r"(?i)\b(blender(?:\.exe)?|bpy)\b", command):
                    raise StudioError("Direct Blender shell execution bypasses this project's reviewed pipeline. Use studio_blender_operation")
        except (StudioError, KeyError, OSError, ValueError) as exc:
            return deny(exc)
        return {"hookSpecificOutput": {"hookEventName": kind, "additionalContext": "Atelier 3D project: " + str(project.root) + ". Pipeline proposal, exact packages and human approval of the three-part construction board are required before production. Use studio_check_pipeline and studio_blender_operation. Do not bypass through scripts or substitute another modeling method."}}
    if kind == "Stop":
        if summary["stage"] != "COMPLETE" and not event.get("stop_hook_active"):
            return {"decision": "block", "reason": "3D project is " + summary["stage"] + ". Report remaining work and any pending human cutting/visual review. Continue only authorized unblocked work. Do not claim completion or loop waiting for approval."}
        return {}
    if kind in ("SessionEnd", "Interrupt"):
        atomic_json(project.data / "logs/session-recovery.json", {"timestamp": now(), "summary": summary,
                    "recovery": "Read canonical SQLite; verify pipeline/board admission and reconcile unknown jobs before production."})
        project.snapshot()
        return {}
    if kind == "PostToolUse":
        atomic_json(project.data / "logs/last-tool.json", {"timestamp": now(), "tool": event.get("tool_name", ""), "stage": summary["stage"]})
    return {"hookSpecificOutput": {"hookEventName": kind, "additionalContext": json.dumps(summary, ensure_ascii=False)}}


if __name__ == "__main__":
    event = {}
    try:
        event = json.loads(sys.stdin.read())
        print(json.dumps(handle(event), ensure_ascii=False))
    except Exception as exc:
        # Managed admission errors must not silently permit mutation.
        result = deny("Atelier 3D admission unavailable: " + type(exc).__name__) if event.get("hook_event_name") == "PreToolUse" else {"systemMessage": "Atelier 3D hook unavailable: " + type(exc).__name__}
        print(json.dumps(result, ensure_ascii=False))
