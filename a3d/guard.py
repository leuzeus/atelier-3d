"""Admission for known Blender entrypoints, not a sandbox for arbitrary Python."""
import ast
from .core import ROOT, StudioError, inside, read_json, sha
from .planning import require_board


def code_for(project_root, operation, arguments):
    payload = dict(project_root=project_root, operation=operation, arguments=arguments)
    return ("# Atelier 3D controlled operation v1\nimport sys\n"
        f"sys.path.insert(0, {str(ROOT)!r})\nfrom blender.operations import dispatch\n"
        f"result = dispatch(**{payload!r})\n")


def parse_code(code):
    try:
        tree = ast.parse(code)
        payload = ast.literal_eval(tree.body[-1].value.keywords[0].value)
        if code != code_for(**payload):
            raise ValueError()
        return payload
    except (SyntaxError, ValueError, AttributeError, KeyError, TypeError, IndexError):
        raise StudioError("Raw Blender code is not admitted in this managed project. Use studio_blender_operation; never substitute procedural geometry for a reviewed route.")


def admit_operation(project, operation, arguments):
    state = project.state()
    if operation not in ("prepare", "inspect", "garment", "assemble", "run_script", "restore_checkpoint"):
        raise StudioError("Unknown guarded Blender operation")
    required = {"prepare": set(), "inspect": set(), "garment": {"package_dir"}, "assemble": {"plan_path"},
        "run_script": {"purpose", "path", "sha256", "component_ids"}, "restore_checkpoint": set()}[operation]
    if operation == "run_script" and arguments.get("purpose") == "simulate":
        required = required | {"simulation_plan"}
    if set(arguments) != required:
        raise StudioError("Unexpected/missing operation arguments")
    from .lifecycle import no_pending_operation
    if operation == "restore_checkpoint":
        pending = state.get("pending_blender_operation")
        if not pending:
            raise StudioError("No interrupted operation to recover")
        from .lifecycle import verify_files
        verify_files(project, [pending["checkpoint"]])
        return
    if operation != "inspect":
        no_pending_operation(state)
    if operation in ("prepare", "inspect"):
        if state["stage"] == "COMPLETE" and operation == "prepare":
            raise StudioError("Completed project is immutable")
        return
    require_board(project, state)
    if operation == "garment":
        if state["stage"] != "RECONSTRUCTING":
            raise StudioError("Sewn panel construction requires RECONSTRUCTING")
        data_dir = inside(project.root, arguments["package_dir"])
        data = read_json(data_dir / "garment.json")
        _, component = project.ready(data["component_id"])
        if component["route"]["selected"] != "PATTERN_SEWN":
            raise StudioError("Sewn operation cannot change the selected pipeline")
        manifest = read_json(data_dir / "manifest.json")
        if manifest != component["package"]["manifest"]:
            raise StudioError("Extracted package mismatch")
        for path, checksum in manifest["checksums"].items():
            if sha(inside(data_dir, path)) != checksum:
                raise StudioError("Extracted pattern input changed")
    elif operation == "assemble":
        if state["stage"] != "ASSEMBLING":
            raise StudioError("Assembly requires ASSEMBLING")
        from .lifecycle import assembly_plan
        assembly_plan(project, state, arguments["plan_path"])
    else:
        stages = {"simulate": "RECONSTRUCTING", "refine": "REFINING", "behavior": "BEHAVIOR_AUTHORING", "validate": "VALIDATING", "export": "VALIDATING"}
        if stages.get(arguments["purpose"]) != state["stage"]:
            raise StudioError("Script purpose/stage mismatch; arbitrary reconstruction scripts are unsupported")
        if not arguments["component_ids"] or set(arguments["component_ids"]) - state["components"].keys():
            raise StudioError("Declare existing components for the script")
        if arguments["purpose"] == "simulate" and any(state["components"][cid]["route"]["selected"] != "PATTERN_SEWN" for cid in arguments["component_ids"]):
            raise StudioError("Simulation requires already sewn pattern components")
        if arguments["purpose"] == "simulate":
            from .lifecycle import simulation_plan
            if any(state["components"][cid]["stage"] == "RECONSTRUCTED" for cid in arguments["component_ids"]):
                raise StudioError("Accepted sewing reconstruction is immutable; create a new revision for another simulation")
            simulation_plan(project, state, arguments["simulation_plan"], arguments["component_ids"])
        if arguments["purpose"] in ("behavior", "export"):
            from .lifecycle import silhouette
            silhouette(project, state)
        path = inside(project.root, arguments["path"])
        if path.suffix != ".py" or sha(path) != arguments["sha256"]:
            raise StudioError("Script changed or is not a project Python file")
