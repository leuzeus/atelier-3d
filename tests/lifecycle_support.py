"""Synthetic contract helpers. These reports never qualify production geometry."""
import shutil
from pathlib import Path
from a3d.core import atomic_json, sha
from a3d.lifecycle import required_final_checks
from tests.support import png


def record(project, path):
    path = Path(path)
    return {"path": path.relative_to(project.root).as_posix(), "sha256": sha(path)}


def evidence(project, key, data):
    path = project.data / ("evidence/" + key + ".json")
    atomic_json(path, data)
    project.evidence(key, path.relative_to(project.root).as_posix())
    return key


def checks(project, names):
    path = project.data / "evidence/synthetic-checks.txt"
    path.write_text("SYNTHETIC state-machine fixture, not actual geometry/rig/engine validation.")
    return {"checks": {k: "PASS" for k in names}, "check_evidence": {k: record(project, path) for k in names}}


def visual(project, key, purpose, artifacts):
    path = project.data / ("evidence/" + key + ".png")
    path.write_bytes(png())
    return evidence(project, key, {"asset_id": project.state()["asset"]["id"], "purpose": purpose,
        "artifacts": artifacts, "images": [record(project, path)], "reference_evidence_keys": ["reference.original"],
        "notes": "SYNTHETIC fixture only. No human assessed production artwork."})


def reconstruction_report(project, cid=None, artifact=None):
    cid = cid or next(iter(project.state()["components"]))
    if artifact is None:
        path = project.data / ("outputs/" + cid + ".obj")
        path.write_text("# synthetic triangle\nv 0 0 0\nv .1 0 0\nv 0 0 .1\nf 1 2 3\n")
        artifact = record(project, path)
    return {"component_id": cid, "package_sha256": project.state()["components"][cid]["package"]["sha256"],
        "artifact": artifact, "visual_review_evidence": visual(project, "reconstruction-view-" + cid, "reconstruction", [artifact]),
        **checks(project, ("scale", "orientation", "anchors", "identity", "separation", "geometry"))}


def accept(project, artifact=None):
    for cid in project.state()["components"]:
        report = reconstruction_report(project, cid, artifact)
        key = evidence(project, "reconstruction-" + cid, report)
        project.accept_reconstruction(cid, key)
    project.transition("RECONSTRUCTED", "brief")


def plan(project, mode="import"):
    session_path = project.data / "blender/session.json"
    if not session_path.exists():
        path = project.data / "blender/working-fixture.blend"
        path.write_bytes(b"SYNTHETIC state-machine scene, not a Blender file")
        atomic_json(session_path, {"working": str(path), "original": None})
    from a3d.core import read_json
    session = read_json(session_path)
    working = Path(session["working"])
    checkpoint = project.data / "checkpoints/plan-baseline.blend"
    shutil.copyfile(working, checkpoint)
    data = {"asset_id": project.state()["asset"]["id"], "working_blend": working.relative_to(project.root).as_posix(),
        "working_sha256": sha(working), "checkpoint": checkpoint.relative_to(project.root).as_posix(), "checkpoint_sha256": sha(checkpoint),
        "original_blend": session["original"], "relationships": project.state()["asset"]["relationships"], "components": []}
    for cid, component in project.state()["components"].items():
        data["components"].append({"id": cid, **component["reconstruction"]["artifact"], "mode": mode,
            "position_cm": [0, 0, 0], "rotation_degrees": [0, 0, 0], "scale": 1, "anchor_local": [0, 0, 0], "anchor_world_cm": [0, 0, 0]})
    evidence(project, "assembly-plan", data)
    project.gate("assembly", True, "Synthetic plan approval", ["assembly-plan"], "test:assembly")
    return data


def assembled(project):
    accept(project)
    data = plan(project)
    project.transition("ASSEMBLING", "assembly-plan")
    snapshot = project.data / "outputs/assembled-fixture.blend"
    shutil.copyfile(project.root / data["working_blend"], snapshot)
    evidence(project, "assembly-result", {"asset_id": project.state()["asset"]["id"],
        "plan_evidence": project.state()["evidence"]["assembly-plan"], "component_ids": list(project.state()["components"]),
        "artifact": record(project, snapshot), "checkpoint": {"path": data["checkpoint"], "sha256": data["checkpoint_sha256"]}})
    project.transition("REFINING", "assembly-result")
    return data


def stage_report(project, key, stage, names):
    from a3d.core import read_json
    working = Path(read_json(project.data / "blender/session.json")["working"])
    snapshot = project.data / ("outputs/" + key + ".blend")
    shutil.copyfile(working, snapshot)
    artifact = record(project, snapshot)
    evidence(project, key, {"asset_id": project.state()["asset"]["id"], "stage": stage, "artifacts": [artifact], **checks(project, names)})
    return artifact


def refined(project):
    artifact = stage_report(project, "refinement-validation", "REFINING", ("geometry", "scale", "orientation", "separation"))
    visual(project, "silhouette-review", "silhouette", [artifact])
    project.gate("silhouette", True, "Synthetic silhouette approval", ["silhouette-review"], "test:silhouette")
    project.transition("BEHAVIOR_AUTHORING", "refinement-validation")


def final_ready(project):
    assembled(project)
    refined(project)
    artifact = stage_report(project, "behavior-validation", "BEHAVIOR_AUTHORING", ("rig", "weighting", "clearance"))
    project.transition("VALIDATING", "behavior-validation")
    key = visual(project, "final-review", "final", [artifact])
    report = {"asset_id": project.state()["asset"]["id"], "target": project.state()["asset"]["target"],
        "artifacts": [artifact], "visual_review_evidence": key, **checks(project, required_final_checks(project.state()))}
    evidence(project, "final-validation", report)
    project.gate("final", True, "Synthetic final approval", ["final-validation", key], "test:final")
    return report
