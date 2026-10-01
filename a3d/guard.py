"""Admission for known Blender entrypoints, not a sandbox for arbitrary Python."""
import ast
from .core import ROOT, StudioError, inside, read_json, sha
from .planning import require_board


def code_for(project_root, operation, arguments):
    payload = dict(project_root=project_root, operation=operation, arguments=arguments)
    return ("# Atelier 3D controlled operation v2\nimport runpy\n"
        f"dispatch = runpy.run_path({str(ROOT / 'blender/bootstrap.py')!r})['dispatch_current']\n"
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
    if operation not in ("prepare", "resume", "inspect", "garment", "assemble", "run_script", "restore_checkpoint", "simulate_sewn", "freeze_sewn"):
        raise StudioError("Unknown guarded Blender operation")
    required = {"prepare": set(), "resume": set(), "inspect": set(), "garment": {"package_dir"}, "assemble": {"plan_path"},
        "run_script": {"purpose", "path", "sha256", "component_ids"}, "restore_checkpoint": set(),
        "simulate_sewn": {"component_id", "recipe_path", "phase", "scope"},
        "freeze_sewn": {"component_id", "recipe_path"}}[operation]
    if operation == "garment" and "recipe_path" in arguments:
        required = required | {"recipe_path"}
    if operation == "garment" and "rebuild" in arguments:
        required = required | {"rebuild"}
        if not isinstance(arguments['rebuild'], bool):raise StudioError('rebuild must be a boolean')
    if operation == "garment" and "migrate_legacy" in arguments:
        required = required | {"migrate_legacy"}
        if not isinstance(arguments['migrate_legacy'], bool):
            raise StudioError('migrate_legacy must be a boolean')
        if arguments['migrate_legacy'] and arguments.get('rebuild') is not True:
            raise StudioError('Legacy migration requires explicit rebuild=true')
    if operation == 'garment' and {'legacy_snapshot_sha256', 'legacy_script_receipts'} & set(arguments):
        required |= {'legacy_snapshot_sha256', 'legacy_script_receipts'}
        fingerprint = arguments.get('legacy_snapshot_sha256')
        receipts = arguments.get('legacy_script_receipts')
        if arguments.get('migrate_legacy') is not True:
            raise StudioError('Legacy snapshot archival requires migrate_legacy=true')
        if not isinstance(fingerprint, str) or len(fingerprint) != 64 or any(c not in '0123456789abcdef' for c in fingerprint):
            raise StudioError('Legacy snapshot must be the SHA-256 returned by inspect')
        if not isinstance(receipts, list) or not receipts or any(not isinstance(p, str) or not p for p in receipts):
            raise StudioError('Legacy modified mesh requires explicit script receipts')
        if len(set(receipts)) != len(receipts):
            raise StudioError('Legacy script receipts must be unique')
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
    if operation in ("prepare", "resume", "inspect"):
        if state["stage"] == "COMPLETE" and operation != "inspect":
            raise StudioError("Completed project is immutable")
        return
    require_board(project, state)
    if operation in ("simulate_sewn", "freeze_sewn"):
        if state["stage"] != "RECONSTRUCTING":
            raise StudioError("Native sewing requires RECONSTRUCTING")
        _, component = project.ready(arguments["component_id"])
        if component["route"]["selected"] != "PATTERN_SEWN" or component["stage"] == "RECONSTRUCTED":
            raise StudioError("Native sewing requires an unaccepted sewn component")
        from .core import contract
        recipe = contract("sewing-recipe", read_json(inside(project.root, arguments["recipe_path"])))
        if recipe["component_id"] != arguments["component_id"]:
            raise StudioError("Sewing recipe identity mismatch")
        if operation == "simulate_sewn" and (arguments["phase"] not in ("mount", "drape") or arguments["scope"] not in ("local", "full")):
            raise StudioError("Unknown sewing phase or scope")
        return
    if operation == "garment":
        if state["stage"] != "RECONSTRUCTING":
            raise StudioError("Sewn panel construction requires RECONSTRUCTING")
        data_dir = inside(project.root, arguments["package_dir"])
        data = read_json(data_dir / "garment.json")
        _, component = project.ready(data["component_id"])
        if component['stage']=='RECONSTRUCTED':
            raise StudioError('Accepted sewing reconstruction is immutable; create a new revision')
        if component["route"]["selected"] != "PATTERN_SEWN":
            raise StudioError("Sewn operation cannot change the selected pipeline")
        manifest = read_json(data_dir / "manifest.json")
        if manifest != component["package"]["manifest"]:
            raise StudioError("Extracted package mismatch")
        for path, checksum in manifest["checksums"].items():
            if sha(inside(data_dir, path)) != checksum:
                raise StudioError("Extracted pattern input changed")
        if "recipe_path" not in arguments:
            raise StudioError("garment requires recipe_path for its derived simulation mesh; keep approved packages unchanged")
        from .sewing import validate_recipe
        validate_recipe(data, read_json(inside(project.root, arguments["recipe_path"])))
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
