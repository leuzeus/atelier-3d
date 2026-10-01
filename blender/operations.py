"""Execute through the user's existing Blender MCP Python tool.

This module is imported inside Blender, never by the ComfyUI server. Operations
use centimeters in contracts and meters in Blender, with Z up and front -Y.
"""
import json
import math
import shutil
import sys
import uuid
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))
from a3d.core import StudioError, atomic_json, contract, inside, now, read_json, sha
from a3d.store import Project


def prepare(project_root):
    import bpy
    project = Project(project_root)
    if (project.data / "blender/session.json").exists():
        raise StudioError("A working scene already exists; explicitly resume that scene")
    original = Path(bpy.data.filepath).resolve() if bpy.data.filepath else None
    original_hash = sha(original) if original and original.is_file() else None
    working = inside(project.root, f".a3d/blender/working-{uuid.uuid4().hex}.blend", False)
    # Saving as a new file also preserves an unsaved/dirty scene without touching
    # its on-disk original. No file is loaded or scene cleared.
    bpy.ops.wm.save_as_mainfile(filepath=str(working), check_existing=False)
    if original_hash and sha(original) != original_hash:
        raise StudioError("Original file unexpectedly changed")
    rec = {"original": str(original) if original else None, "original_sha256": original_hash,
           "working": str(working), "created_at": now()}
    atomic_json(project.data / "blender/session.json", rec)
    return rec


def working(project_root):
    import bpy
    project = Project(project_root)
    rec = read_json(inside(project.root, ".a3d/blender/session.json"))
    path = Path(rec["working"]).resolve(strict=True)
    if not path.is_relative_to(project.data / "blender") or Path(bpy.data.filepath).resolve() != path:
        raise StudioError("Connected Blender scene is not this project's working copy")
    if rec["original"] and path == Path(rec["original"]).resolve():
        raise StudioError("Working scene cannot be the original")
    return project, rec


def checkpoint(project_root):
    import bpy
    project, rec = working(project_root)
    path = inside(project.root, f".a3d/checkpoints/pre-{uuid.uuid4().hex}.blend", False)
    bpy.ops.wm.save_as_mainfile(filepath=str(path), copy=True, check_existing=False)
    result = {"path": path.relative_to(project.root).as_posix(), "sha256": sha(path), "created_at": now()}
    atomic_json(project.data / "blender/last-checkpoint.json", result)
    return result


def assemble(project_root, plan_path):
    import bpy
    from mathutils import Euler, Matrix, Vector
    project, rec = working(project_root)
    state = project.state()
    from a3d.lifecycle import assembly_plan
    plan, plan_evidence = assembly_plan(project, state, plan_path)
    from a3d.planning import require_board
    require_board(project, state)
    if plan["asset_id"] != state["asset"]["id"] or state["stage"] != "ASSEMBLING":
        raise StudioError("Assembly not admitted for this asset/stage")
    project.require_gate(state, "assembly")
    if inside(project.root, plan["working_blend"]) != Path(rec["working"]):
        raise StudioError("Assembly plan targets another scene")
    if plan["relationships"] != state["asset"]["relationships"]:
        raise StudioError("Plan cannot change separation/relationship contract")
    if plan["original_blend"] != rec["original"]:
        raise StudioError("Assembly plan original does not match the prepared session")
    for part in plan["components"]:
        path = inside(project.root, part["path"])
        existing = [o for o in bpy.data.objects if o.get("a3d_component_id") == part["id"]]
        if part.get("mode", "import") == "existing":
            meshes = [o for o in existing if o.type == "MESH"]
            if not meshes:
                raise StudioError("Existing assembly component has no geometry")
            component = state["components"][part["id"]]
            if component["route"]["selected"] != "PATTERN_SEWN":
                raise StudioError("Existing assembly mode is reserved for package-derived sewn components")
            if any(o.get("a3d_package_sha256") != component["package"]["sha256"] for o in meshes):
                raise StudioError("Existing sewing geometry no longer matches its package")
        elif existing:
            raise StudioError("Component already imported; do not duplicate it")
        elif path.suffix.lower() not in (".glb", ".obj", ".ply", ".stl"):
            raise StudioError("Unsupported mesh import")
    saved = state.get("pending_blender_operation", {}).get("checkpoint") or checkpoint(project_root)
    imported = []
    for part in plan["components"]:
        path = inside(project.root, part["path"])
        before = set(bpy.data.objects)
        if part.get("mode", "import") == "existing":
            added = {o for o in bpy.data.objects if o.get("a3d_component_id") == part["id"]}
        elif path.suffix.lower() == ".glb":
            bpy.ops.import_scene.gltf(filepath=str(path))
        elif path.suffix.lower() == ".obj":
            bpy.ops.wm.obj_import(filepath=str(path))
        elif path.suffix.lower() == ".ply":
            bpy.ops.wm.ply_import(filepath=str(path))
        else:
            bpy.ops.wm.stl_import(filepath=str(path))
        if part.get("mode", "import") != "existing":
            added = set(bpy.data.objects) - before
        if not any(o.type == "MESH" for o in added):
            raise StudioError("Import produced no mesh; restore checkpoint before retry")
        root = bpy.data.objects.new("A3D." + part["id"], None)
        bpy.context.scene.collection.objects.link(root)
        root["a3d_component_id"] = part["id"]
        root["a3d_source_sha256"] = part["sha256"]
        for obj in added:
            obj["a3d_component_id"] = part["id"]
            if obj.parent not in added:
                matrix = obj.matrix_world.copy()
                obj.parent = root
                obj.matrix_world = matrix
        rotation = Euler([math.radians(x) for x in part["rotation_degrees"]], "XYZ").to_matrix().to_4x4()
        scale = Matrix.Scale(part["scale"], 4)
        # Local anchor is in source Blender units after import; world is cm.
        local = Vector(part["anchor_local"])
        target = Vector([v / 100 for v in part["anchor_world_cm"]])
        offset = Vector([v / 100 for v in part["position_cm"]])
        root.matrix_world = Matrix.Translation(target + offset - (rotation @ scale @ local)) @ rotation @ scale
        imported.append({"component_id": part["id"], "objects": sorted(o.name for o in added)})
    bpy.context.scene.unit_settings.system = "METRIC"
    bpy.context.scene.unit_settings.scale_length = 1.0
    # No join, weld, remesh, boolean or automatic fusion.
    bpy.ops.wm.save_as_mainfile(filepath=rec["working"], check_existing=False)
    snapshot = project.data / ("outputs/assembled-" + uuid.uuid4().hex + ".blend")
    shutil.copyfile(rec["working"], snapshot)
    receipt = {"asset_id": state["asset"]["id"], "plan_evidence": plan_evidence,
        "component_ids": [p["id"] for p in plan["components"]],
        "artifact": {"path": snapshot.relative_to(project.root).as_posix(), "sha256": sha(snapshot)},
        "checkpoint": saved, "imports": imported, "working": rec["working"], "visual_validation": "NOT_EXECUTED"}
    receipt_path = project.data / ("blender/assembly-" + uuid.uuid4().hex + ".json")
    atomic_json(receipt_path, receipt)
    project.evidence("assembly-result", receipt_path.relative_to(project.root).as_posix())
    return receipt


def garment(project_root, package_dir):
    import bpy
    from mathutils import Euler, Vector
    project, rec = working(project_root)
    state = project.state()
    if state["stage"] not in ("RECONSTRUCTING", "ASSEMBLING"):
        raise StudioError("Garment construction requires reconstruction/assembly stage")
    data_dir = inside(project.root, package_dir)
    data = contract("garment", read_json(data_dir / "garment.json"))
    _, component = project.ready(data["component_id"])
    if component["route"]["selected"] != "PATTERN_SEWN":
        raise StudioError("Component is not routed to sewn panels")
    manifest = read_json(data_dir / "manifest.json")
    if manifest != component["package"]["manifest"]:
        raise StudioError("Extracted package mismatch")
    for name, expected in manifest["checksums"].items():
        if sha(inside(data_dir, name)) != expected:
            raise StudioError("Extracted garment package changed")
    if any(o.get("a3d_component_id") == data["component_id"] for o in bpy.data.objects):
        raise StudioError("Garment already constructed")
    saved = state.get("pending_blender_operation", {}).get("checkpoint") or checkpoint(project_root)
    vertices, faces, edges, offsets = [], [], [], {}
    for pid, panel in data["pieces"].items():
        offsets[pid] = len(vertices)
        rotation = Euler([math.radians(x) for x in panel["rotation_degrees"]], "XYZ").to_matrix()
        position = Vector([v / 100 for v in panel["position_cm"]])
        vertices.extend(tuple(rotation @ Vector((p[0] / 100, p[1] / 100, 0)) + position) for p in panel["vertices"])
        faces.extend([i + offsets[pid] for i in face] for face in panel["faces"])
    for seam in data["seams"]:
        a = data["pieces"][seam["piece_a"]]["edges"][seam["edge_a"]]
        b = data["pieces"][seam["piece_b"]]["edges"][seam["edge_b"]]
        if seam["orientation"] == "reverse":
            b = list(reversed(b))
        edges.extend((offsets[seam["piece_a"]] + x, offsets[seam["piece_b"]] + y) for x, y in zip(a, b, strict=True))
    mesh = bpy.data.meshes.new("A3D.panels." + data["component_id"])
    mesh.from_pydata(vertices, edges, faces)
    mesh.update()
    obj = bpy.data.objects.new("A3D." + data["component_id"], mesh)
    bpy.context.scene.collection.objects.link(obj)
    obj["a3d_component_id"] = data["component_id"]
    obj["a3d_package_sha256"] = component["package"]["sha256"]
    cloth = obj.modifiers.new("Sewing", "CLOTH")
    cloth.settings.use_sewing_springs = True
    cloth.settings.mass = data["material"]["mass_kg"]
    for key in ("tension_stiffness", "compression_stiffness", "shear_stiffness", "bending_stiffness"):
        setattr(cloth.settings, key, data["material"][key])
    cloth.collision_settings.use_self_collision = True
    # Simulation is intentionally separate: collision mannequin and frame budget
    # need a live scene-specific decision before a potentially expensive bake.
    bpy.ops.wm.save_as_mainfile(filepath=rec["working"], check_existing=False)
    receipt = {"checkpoint": saved, "object": obj.name, "vertices": len(vertices), "sewing_edges": len(edges),
               "simulation": "NOT_EXECUTED", "visual_validation": "NOT_EXECUTED"}
    atomic_json(project.data / "blender/garment-receipt.json", receipt)
    return receipt


def inspect(project_root):
    import bpy
    import bmesh
    project, rec = working(project_root)
    objects = []
    for obj in bpy.data.objects:
        if obj.type != "MESH" or not obj.get("a3d_component_id"):
            continue
        mesh = obj.data
        bm = bmesh.new()
        bm.from_mesh(mesh)
        nonmanifold = sum(not e.is_manifold for e in bm.edges)
        degenerate = sum(f.calc_area() < 1e-12 for f in bm.faces)
        bm.free()
        objects.append({"name": obj.name, "component_id": obj["a3d_component_id"], "vertices": len(mesh.vertices),
                        "polygons": len(mesh.polygons), "nonmanifold_edges": nonmanifold, "degenerate_faces": degenerate,
                        "dimensions_m": list(obj.dimensions), "materials": len(mesh.materials),
                        "uv_layers": len(mesh.uv_layers), "armature_modifiers": sum(m.type == "ARMATURE" for m in obj.modifiers)})
    report = {"blender_version": bpy.app.version_string, "working": rec["working"], "objects": objects,
              "evaluated_geometry": "NOT_EXECUTED", "identity": "NOT_EXECUTED", "visual": "NOT_EXECUTED",
              "note": "Counts are evidence, not automatic acceptance; evaluate modifiers, rig deformation and silhouette separately."}
    atomic_json(project.data / "blender/inspection.json", report)
    return report


def _perform(project_root, operation, arguments):
    if operation != "run_script":
        return {"prepare": prepare, "inspect": inspect, "garment": garment, "assemble": assemble}[operation](project_root, **arguments)
    import bpy
    import runpy
    project, rec = working(project_root)
    state = project.state()
    for cid in arguments["component_ids"]:
        objects = [o for o in bpy.data.objects if o.type == "MESH" and o.get("a3d_component_id") == cid]
        if not objects:
            raise StudioError("Operation requires existing package-derived geometry: " + cid)
        if arguments["purpose"] == "simulate" and any(o.get("a3d_package_sha256") != state["components"][cid]["package"]["sha256"] for o in objects):
            raise StudioError("Sewing geometry does not match the reviewed package")
    if arguments["purpose"] in ("behavior", "export"):
        project.require_gate(state, "silhouette")
    if arguments["purpose"] == "simulate":
        from a3d.lifecycle import simulation_plan
        plan = simulation_plan(project, state, arguments["simulation_plan"], arguments["component_ids"])
        for cid in plan["collision_components"]:
            colliders = [o for o in bpy.data.objects if o.type == "MESH" and o.get("a3d_component_id") == cid]
            if not colliders or any(not any(m.type == "COLLISION" for m in o.modifiers) for o in colliders):
                raise StudioError("Declared collision component needs actual collision geometry: " + cid)
        cloths = [m for o in bpy.data.objects if o.get("a3d_component_id") == plan["component_id"] for m in o.modifiers if m.type == "CLOTH"]
        if not cloths:
            raise StudioError("Sewn geometry has no Cloth modifier")
        bpy.context.scene.frame_start = plan["frame_start"]
        bpy.context.scene.frame_end = plan["frame_end"]
        for modifier in cloths:
            modifier.settings.quality = plan["quality"]
            modifier.point_cache.frame_start = plan["frame_start"]
            modifier.point_cache.frame_end = plan["frame_end"]
    saved = state.get("pending_blender_operation", {}).get("checkpoint") or checkpoint(project_root)
    path = inside(project.root, arguments["path"])
    if sha(path) != arguments["sha256"]:
        raise StudioError("Script changed after admission")
    # Authored scripts remain trusted Python, not sandboxed code. They cannot
    # serve as arbitrary reconstruction entrypoints; retain a recovery copy.
    runpy.run_path(str(path), init_globals={"A3D_PROJECT_ROOT": str(project.root)}, run_name="__a3d_operation__")
    working(project_root)
    bpy.ops.wm.save_as_mainfile(filepath=rec["working"], check_existing=False)
    receipt = {"operation": arguments["purpose"], "script": arguments["path"], "sha256": arguments["sha256"],
        "component_ids": arguments["component_ids"], "checkpoint": saved, "visual_validation": "NOT_EXECUTED"}
    atomic_json(project.data / ("blender/script-" + uuid.uuid4().hex + ".json"), receipt)
    return receipt


def restore_checkpoint(project_root):
    import bpy
    project, session = working(project_root)
    pending = project.state()["pending_blender_operation"]
    source = inside(project.root, pending["checkpoint"]["path"])
    bpy.ops.wm.open_mainfile(filepath=str(source))
    # A failed scene stays on disk for diagnosis; recovery gets a new path.
    restored = project.data / ("blender/working-recovered-" + uuid.uuid4().hex + ".blend")
    bpy.ops.wm.save_as_mainfile(filepath=str(restored), check_existing=False)
    session["working"] = str(restored)
    atomic_json(project.data / "blender/session.json", session)
    with project.transaction() as db:
        state = project.state(db)
        state.pop("pending_blender_operation")
        if pending["operation"] == "assemble":
            state["evidence"].pop("assembly-result", None)
        project.save(db, state, "blender_recovered", {"checkpoint": pending["checkpoint"], "working": str(restored)})
    return {"restored": str(restored), "checkpoint": pending["checkpoint"], "visual_validation": "NOT_EXECUTED"}


def dispatch(project_root, operation, arguments):
    """Repeat admission, retain a recovery checkpoint across failures/crashes."""
    from a3d.guard import admit_operation
    project = Project(project_root)
    admit_operation(project, operation, arguments)
    if operation == "restore_checkpoint":
        return restore_checkpoint(project_root)
    if operation in ("prepare", "inspect"):
        return _perform(project_root, operation, arguments)
    import bpy
    saved = checkpoint(project_root)
    before_ids = {o.get("a3d_component_id") for o in bpy.data.objects if o.type == "MESH" and o.get("a3d_component_id")}
    with project.transaction() as db:
        state = project.state(db)
        from a3d.lifecycle import no_pending_operation
        no_pending_operation(state)
        state["pending_blender_operation"] = {"operation": operation, "checkpoint": saved, "status": "running"}
        project.save(db, state, "blender_started", state["pending_blender_operation"])
    try:
        result = _perform(project_root, operation, arguments)
        after_ids = {o.get("a3d_component_id") for o in bpy.data.objects if o.type == "MESH" and o.get("a3d_component_id")}
        if before_ids - after_ids:
            raise StudioError("Operation removed independent component geometry; restore checkpoint")
        for relation in project.state()["asset"]["relationships"]:
            if relation["must_remain_separate"]:
                a = {o.data for o in bpy.data.objects if o.type == "MESH" and o.get("a3d_component_id") == relation["a"]}
                b = {o.data for o in bpy.data.objects if o.type == "MESH" and o.get("a3d_component_id") == relation["b"]}
                if a & b:
                    raise StudioError("Separate components share mesh data; restore checkpoint")
        with project.transaction() as db:
            state = project.state(db)
            state.pop("pending_blender_operation")
            project.save(db, state, "blender_finished", {"operation": operation, "checkpoint": saved})
        return result
    except BaseException as exc:
        with project.transaction() as db:
            state = project.state(db)
            state["pending_blender_operation"].update(status="failed", error=str(exc))
            project.save(db, state, "blender_failed", {"operation": operation, "error": str(exc)})
        raise
