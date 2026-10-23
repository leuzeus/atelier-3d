"""Evidence admission for production milestones; hashes do not prove artistry."""
from .core import StudioError, contract, inside, read_json, sha
from .packages import png_dimensions


def verify_files(project, records):
    seen = set()
    for record in records:
        path = inside(project.root, record["path"])
        if record["path"] in seen or not path.is_file() or sha(path) != record["sha256"]:
            raise StudioError("Missing, duplicate or changed artifact: " + record["path"])
        seen.add(record["path"])
    return seen


def verify_checks(project, report, required):
    checks = report["checks"]
    if set(required) - checks.keys() or any(v != "PASS" for v in checks.values()):
        raise StudioError("Required checks are incomplete; FAIL/SKIP/NOT_EXECUTED/INCONCLUSIVE are not PASS")
    if set(checks) != set(report["check_evidence"]):
        raise StudioError("Every check must bind its exact evidence file")
    # One report may substantiate multiple checks; each binding is still exact.
    for record in report["check_evidence"].values():
        verify_files(project, [record])


def visual_review(project, state, evidence_key, purpose, expected_artifacts=None, current_scene=False):
    rec = project.verify_evidence(state, evidence_key)
    review = contract("visual-review", read_json(inside(project.root, rec["path"])))
    if review["asset_id"] != state["asset"]["id"] or review["purpose"] != purpose:
        raise StudioError("Visual review identity/purpose mismatch")
    verify_files(project, review["artifacts"])
    verify_files(project, review["images"])
    for image in review["images"]:
        png_dimensions(inside(project.root, image["path"]).read_bytes())
    project.require_gate(state, "references")
    for key in review["reference_evidence_keys"]:
        if key not in state["gates"]["references"]["evidence"]:
            raise StudioError("Visual comparison must use the reviewed reference images")
        ref = project.verify_evidence(state, key)
        png_dimensions(inside(project.root, ref["path"]).read_bytes())
    if expected_artifacts and any(record not in review["artifacts"] for record in expected_artifacts):
        raise StudioError("Visual review does not bind the exact candidate artifacts")
    if current_scene:
        session = read_json(inside(project.root, ".a3d/blender/session.json"))
        from pathlib import Path
        working = Path(session["working"]).resolve()
        if not working.is_relative_to(project.data / "blender") or sha(working) not in {a["sha256"] for a in review["artifacts"]}:
            raise StudioError("Visual review does not match the current working scene; capture a new immutable snapshot and review")
    return review


def reconstruction(project, state, cid):
    component = state["components"][cid]
    stored = component.get("reconstruction_evidence")
    if component["stage"] != "RECONSTRUCTED" or not stored:
        raise StudioError("Validated reconstruction evidence missing: " + cid)
    if project.verify_evidence(state, stored["key"]) != stored["record"]:
        raise StudioError("Reconstruction report changed: " + cid)
    report = contract("reconstruction", read_json(inside(project.root, stored["record"]["path"])))
    if report != component.get("reconstruction") or report["package_sha256"] != component["package"]["sha256"]:
        raise StudioError("Reconstruction/package no longer matches")
    verify_checks(project, report, {"scale", "orientation", "anchors", "identity", "separation", "geometry"})
    verify_files(project, [report["artifact"]])
    visual_review(project, state, report["visual_review_evidence"], "reconstruction", [report["artifact"]])
    return report


def assembly_plan(project, state, path=None, verify_baseline=True):
    project.require_gate(state, "assembly")
    if "assembly-plan" not in state["gates"]["assembly"]["evidence"]:
        raise StudioError("Assembly approval must bind the exact assembly-plan")
    rec = project.verify_evidence(state, "assembly-plan")
    if path is not None and inside(project.root, path) != inside(project.root, rec["path"]):
        raise StudioError("Operation targets a different assembly plan")
    plan = contract("assembly", read_json(inside(project.root, rec["path"])))
    if plan["asset_id"] != state["asset"]["id"] or plan["relationships"] != state["asset"]["relationships"]:
        raise StudioError("Assembly identity/relationships mismatch")
    ids = [p["id"] for p in plan["components"]]
    if len(set(ids)) != len(ids) or set(ids) != set(state["components"]):
        raise StudioError("Assembly plan must cover all components exactly once")
    verify_files(project, [{"path": plan["checkpoint"], "sha256": plan["checkpoint_sha256"]}])
    if verify_baseline:
        verify_files(project, [{"path": plan["working_blend"], "sha256": plan["working_sha256"]}])
    for part in plan["components"]:
        record = reconstruction(project, state, part["id"])
        if record["artifact"] != {"path": part["path"], "sha256": part["sha256"]}:
            raise StudioError("Assembly input differs from the validated reconstruction")
    return plan, rec


def assembly_result(project, state):
    from .piece_inventory import current_proof
    if any(c['route']['selected'] == 'PATTERN_SEWN' for c in state['components'].values()):
        current_proof(project, state, require_global=True)
    plan, rec = assembly_plan(project, state, verify_baseline=False)
    proof = project.verify_evidence(state, "assembly-result")
    receipt = read_json(inside(project.root, proof["path"]))
    if receipt.get("asset_id") != state["asset"]["id"] or receipt.get("plan_evidence") != rec or set(receipt.get("component_ids", [])) != set(state["components"]):
        raise StudioError("Assembly receipt does not match the approved plan/components")
    verify_files(project, [receipt["artifact"], receipt["checkpoint"]])
    return receipt


def silhouette(project, state, current_scene=False):
    project.require_gate(state, "silhouette")
    if "silhouette-review" not in state["gates"]["silhouette"]["evidence"]:
        raise StudioError("Silhouette approval must bind silhouette-review images and candidate")
    return visual_review(project, state, "silhouette-review", "silhouette", current_scene=current_scene)


def required_final_checks(state):
    asset = state["asset"]
    required = {"geometry", "scale", "orientation", "separation", "visual"}
    required |= {"animation": {"rig", "weighting", "clearance"}, "game": {"budget", "uv", "materials", "target_import"},
                 "3d_print": {"manifold", "thickness"}, "render": {"materials"}}[asset["target"]]
    if asset["target"] == "game" and any(c["features"].get("sewn") or c["features"].get("articulated") for c in asset["components"]):
        required |= {"rig", "weighting", "clearance"}
    return required | set(asset.get("required_checks", []))


def final_validation(project, state):
    from .piece_inventory import current_proof
    if any(c['route']['selected'] == 'PATTERN_SEWN' for c in state['components'].values()):
        current_proof(project, state, require_global=True)
    project.require_gate(state, "final")
    if "final-validation" not in state["gates"]["final"]["evidence"]:
        raise StudioError("Final gate must bind final-validation report")
    rec = project.verify_evidence(state, "final-validation")
    report = contract("validation", read_json(inside(project.root, rec["path"])))
    if report["asset_id"] != state["asset"]["id"] or report["target"] != state["asset"]["target"]:
        raise StudioError("Validation identity mismatch")
    verify_checks(project, report, required_final_checks(state))
    verify_files(project, report["artifacts"])
    if report["visual_review_evidence"] not in state["gates"]["final"]["evidence"]:
        raise StudioError("Final approval must also bind the exact visual review")
    visual_review(project, state, report["visual_review_evidence"], "final", report["artifacts"])
    silhouette(project, state)
    return report


def no_pending_operation(state):
    if state.get("pending_blender_operation"):
        raise StudioError("Previous Blender operation is incomplete/failed. Inspect its checkpoint and use restore_checkpoint before another mutation")


def stage_validation(project, state, key, stage, required):
    rec = project.verify_evidence(state, key)
    report = contract("stage-validation", read_json(inside(project.root, rec["path"])))
    if report["asset_id"] != state["asset"]["id"] or report["stage"] != stage:
        raise StudioError("Stage validation identity mismatch")
    verify_checks(project, report, required)
    verify_files(project, report["artifacts"])
    session = read_json(inside(project.root, ".a3d/blender/session.json"))
    from pathlib import Path
    working = Path(session["working"]).resolve()
    if not working.is_relative_to(project.data / "blender") or sha(working) not in {a["sha256"] for a in report["artifacts"]}:
        raise StudioError("Stage validation does not match the current working scene")
    return report


def simulation_plan(project, state, path, component_ids):
    plan = contract("simulation", read_json(inside(project.root, path)))
    if plan["component_id"] not in component_ids or len(component_ids) != 1 or plan["type"] != "cloth" or plan["baked"]:
        raise StudioError("Simulation plan must describe one pending cloth component")
    if plan["frame_end"] <= plan["frame_start"] or plan["frame_end"] - plan["frame_start"] + 1 > plan["max_frames"]:
        raise StudioError("Invalid simulation frame range or budget exceeded")
    if set(plan["collision_components"]) - state["components"].keys() or plan["component_id"] in plan["collision_components"]:
        raise StudioError("Simulation colliders must be distinct declared components")
    if "sewing_recipe" not in plan or "phase" not in plan:
        raise StudioError("Legacy simulation plan lacks sewing_recipe/phase; use the native local trial before full cloth")
    recipe = contract("sewing-recipe", read_json(inside(project.root, plan["sewing_recipe"])))
    profile = recipe["phases"][plan["phase"]]
    if recipe["component_id"] != plan["component_id"] or plan["frame_start"] != 1 or plan["frame_end"] != profile["frames"] or plan["quality"] != profile["quality"]:
        raise StudioError("Simulation plan and physical recipe disagree")
    return plan
