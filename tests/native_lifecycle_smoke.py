"""Run with Blender --background --factory-startup --python; synthetic only."""
import json
import shutil
import sys
import uuid
from pathlib import Path
sys.path.insert(0, str(Path(__file__).resolve().parents[1]))
import bpy
from a3d.core import ROOT, StudioError, atomic_json, read_json, sha
from a3d.packages import extract_package
from tests.support import ready_project
from tests.lifecycle_support import accept, plan, record
from blender.operations import dispatch


def script(project, filename, body, purpose, **extra):
    path = project.data / ("blender/" + filename + ".py")
    path.write_text(body, encoding="utf-8")
    return {"path": path.relative_to(project.root).as_posix(), "sha256": sha(path), "purpose": purpose,
        "component_ids": list(project.state()["components"]), **extra}


def expect_block(call, text):
    try:
        call()
    except StudioError as exc:
        assert text in str(exc), str(exc)
    else:
        raise AssertionError("Expected admission rejection: " + text)


root = ROOT / ("work/native-lifecycle-" + uuid.uuid4().hex)
root.mkdir()
results = {"root": str(root), "blender": bpy.app.version_string, "fixture": "SYNTHETIC - no artistic qualification"}
for garment in (False, True):
    label = "sewn" if garment else "imported"
    bpy.ops.wm.read_factory_settings(use_empty=True)
    original = root / (label + "-original.blend")
    bpy.ops.wm.save_as_mainfile(filepath=str(original))
    original_hash = sha(original)
    project = ready_project(root / label, garment=garment)
    session = dispatch(str(project.root), "prepare", {})
    if garment:
        component = project.state()["components"]["garment.coat"]
        extracted = project.data / "reconstruction/extracted"
        extract_package(project.root / component["package"]["path"], extracted)
        recipe = read_json(ROOT / "templates/sewing-recipe.json")
        # The fixture reverses these seam chains. Place the paired panels with
        # matching directions; physics is tested in native_sewing_smoke.py.
        for pid in ("back", "sleeve-right"):
            recipe["placements"][pid]["rotation_degrees"][0] = -90
        atomic_json(project.root / "recipe.json", recipe)
        construction = dispatch(str(project.root), "garment", {
            "package_dir": extracted.relative_to(project.root).as_posix(), "recipe_path": "recipe.json"})
        expected_vertices = len(bpy.data.objects[construction["object"]].data.vertices)
        sewn_snapshot = project.data / "outputs/sewn-reconstruction.blend"
        shutil.copyfile(session["working"], sewn_snapshot)
        accept(project, record(project, sewn_snapshot))
    else:
        accept(project)
        expected_vertices = 3
    data = plan(project, "existing" if garment else "import")
    project.transition("ASSEMBLING", "assembly-plan")
    # Inject a failure after a receipt exists: recovery must invalidate it too.
    import blender.operations as operations
    perform = operations._perform
    def fail_after_assembly(*args):
        perform(*args)
        raise RuntimeError("Synthetic failure after assembly receipt")
    operations._perform = fail_after_assembly
    try:
        dispatch(str(project.root), "assemble", {"plan_path": ".a3d/evidence/assembly-plan.json"})
    except RuntimeError as exc:
        assert "after assembly receipt" in str(exc)
    else:
        raise AssertionError("Fixture must throw after assembly")
    finally:
        operations._perform = perform
    assert "assembly-result" in project.state()["evidence"]
    dispatch(str(project.root), "restore_checkpoint", {})
    assert "assembly-result" not in project.state()["evidence"]
    expect_block(lambda: project.transition("REFINING", "brief"), "assembly-result")
    data = plan(project, "existing" if garment else "import")
    result = dispatch(str(project.root), "assemble", {"plan_path": ".a3d/evidence/assembly-plan.json"})
    assert result["visual_validation"] == "NOT_EXECUTED"
    assert not project.state().get("pending_blender_operation")
    project.transition("REFINING", "assembly-result")
    mesh_objects = [o for o in bpy.data.objects if o.type == "MESH" and o.get("a3d_component_id")]
    assert len(mesh_objects) == 1
    assert len(mesh_objects[0].data.vertices) == expected_vertices
    stable_assembly_hash = result["artifact"]["sha256"]
    fail = script(project, "intentional-failure", "import bpy\nbpy.data.objects.new('FAILED_PARTIAL_OBJECT', None)\nraise RuntimeError('Synthetic failure after mutation')\n", "refine")
    try:
        dispatch(str(project.root), "run_script", fail)
    except RuntimeError as exc:
        assert "Synthetic failure" in str(exc)
    else:
        raise AssertionError("Fixture must throw")
    assert project.state()["pending_blender_operation"]["status"] == "failed"
    assert bpy.data.objects.get("FAILED_PARTIAL_OBJECT") is not None
    expect_block(lambda: dispatch(str(project.root), "run_script", fail), "restore_checkpoint")
    expect_block(lambda: project.transition("BEHAVIOR_AUTHORING", "brief"), "restore_checkpoint")
    restored = dispatch(str(project.root), "restore_checkpoint", {})
    assert bpy.data.objects.get("FAILED_PARTIAL_OBJECT") is None
    assert Path(session["working"]).is_file() and restored["restored"] != session["working"]
    assert not project.state().get("pending_blender_operation")
    dispatch(str(project.root), "run_script", script(project, "successful-fixture", "import bpy\nbpy.context.scene['a3d_fixture_checked'] = True\n", "refine"))
    assert bpy.context.scene["a3d_fixture_checked"]
    assert sha(project.root / result["artifact"]["path"]) == stable_assembly_hash
    assert sha(original) == original_hash
    results[label] = {"assembly": "PASS", "vertices": expected_vertices, "failure_blocks_continuation": "PASS",
        "recovered_assembly_receipt_invalidated": "PASS",
        "recovery": "PASS", "subsequent_operation": "PASS", "original_unchanged": "PASS",
        "immutable_assembly_snapshot": "PASS", "cloth_bake": "NOT_EXECUTED", "visual_validation": "NOT_EXECUTED"}
atomic_json(root / "result.json", results)
print("A3D_NATIVE_RESULT=" + str(root / "result.json"))
