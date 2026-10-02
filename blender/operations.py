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
        raise StudioError("A working scene already exists; use resume on that connected scene")
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


def resume(project_root):
    """Preserve the live (including dirty) working scene without replacing it."""
    import bpy
    project, rec = working(project_root)
    working_hash = sha(Path(rec['working']))
    dirty = bpy.data.is_dirty
    saved = checkpoint(project_root)
    working(project_root)
    if sha(Path(rec['working'])) != working_hash:
        raise StudioError('Resume unexpectedly changed the on-disk working scene')
    receipt = {'working': rec['working'], 'checkpoint': saved, 'dirty_before': dirty,
               'dirty_after': bpy.data.is_dirty, 'working_file_unchanged': True,
               'visual_validation': 'NOT_EXECUTED'}
    atomic_json(project.data / ('blender/resume-' + uuid.uuid4().hex + '.json'), receipt)
    return receipt


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


def garment(project_root, package_dir, recipe_path=None, rebuild=False, migrate_legacy=False,
            legacy_snapshot_sha256=None, legacy_script_receipts=None, legacy_checkpoint_receipt=None):
    import bpy
    from mathutils import Euler, Vector
    project, rec = working(project_root)
    state = project.state()
    if state["stage"] not in ("RECONSTRUCTING", "ASSEMBLING"):
        raise StudioError("Garment construction requires reconstruction/assembly stage")
    data_dir = inside(project.root, package_dir)
    data = contract("garment", read_json(data_dir / "garment.json"))
    _, component = project.ready(data["component_id"])
    if component['stage']=='RECONSTRUCTED':raise StudioError('Accepted sewing reconstruction is immutable')
    if component["route"]["selected"] != "PATTERN_SEWN":
        raise StudioError("Component is not routed to sewn panels")
    manifest = read_json(data_dir / "manifest.json")
    if manifest != component["package"]["manifest"]:
        raise StudioError("Extracted package mismatch")
    for name, expected in manifest["checksums"].items():
        if sha(inside(data_dir, name)) != expected:
            raise StudioError("Extracted garment package changed")
    previous=[o for o in bpy.data.objects if o.get('a3d_component_id')==data['component_id']]
    legacy = False
    legacy_proof = None
    if previous:
        if not rebuild:raise StudioError('Garment already constructed; explicit rebuild=true archives the previous derived simulation mesh')
        if len(previous)!=1 or previous[0].type!='MESH' or previous[0].get('a3d_package_sha256')!=component['package']['sha256']:
            raise StudioError('Rebuild requires one mesh with the current component and package identity')
        if previous[0].get('a3d_role')!='simulation':
            if not migrate_legacy:
                raise StudioError('Legacy panels require explicit migrate_legacy=true and provenance checks')
            from blender.legacy import legacy_snapshot, validate_legacy_panels
            legacy_proof = validate_legacy_panels(project, previous[0], data, component['package']['sha256'],
                                                 legacy_snapshot_sha256, legacy_script_receipts,
                                                 legacy_checkpoint_receipt)
            legacy_proof['before_sha256'] = legacy_snapshot(previous[0])
            legacy = True
        elif migrate_legacy:
            raise StudioError('Legacy archival cannot target an existing native simulation')
    elif migrate_legacy:
        raise StudioError('No legacy mesh to archive')
    saved = state.get("pending_blender_operation", {}).get("checkpoint") or checkpoint(project_root)
    if recipe_path is None:
        raise StudioError("A derived sewing recipe is required; use templates/sewing-recipe.json without modifying approved contours")
    from blender.sewing import build_mesh, make_object, preflight
    recipe = read_json(inside(project.root, recipe_path))
    payload = None
    try:
        payload = build_mesh(data, recipe)
        payload.update(package_sha256=component["package"]["sha256"],
            source_garment=(data_dir / "garment.json").relative_to(project.root).as_posix())
        obj = make_object(payload, "A3D." + data["component_id"])
        obj["a3d_component_id"] = data["component_id"]
        obj["a3d_package_sha256"] = component["package"]["sha256"]
        bpy.context.scene.unit_settings.system = "METRIC"
        # Never change a non-metric scene scale to make an invalid placement pass.
        context, _, trees = preflight(obj, payload, recipe)
        if recipe.get('experimental_prefit'):
            from blender.prefit import apply_prefit
            context = apply_prefit(obj, payload, recipe, trees)
    except StudioError as exc:
        from a3d.garment_rejections import save_rejection
        ref = save_rejection(project, data, recipe, payload or getattr(exc, 'garment_payload', None), exc, saved)
        error = StudioError(str(exc)+'; garment diagnostic='+ref['path']+' sha256='+ref['sha256'])
        error.garment_diagnostic = ref
        raise error from exc
    path = project.data / ("blender/sewing-mesh-" + uuid.uuid4().hex + ".json")
    atomic_json(path, payload)
    obj["a3d_sewing_mesh"] = path.relative_to(project.root).as_posix()
    obj["a3d_sewing_mesh_sha256"] = sha(path)
    for old in previous:
        old['a3d_source_component_id']=data['component_id'];del old['a3d_component_id']
        old['a3d_role']='archived-legacy-panels' if legacy else 'archived-simulation'
        old.hide_set(True);old.hide_render=True
    if legacy:
        legacy_proof['after_sha256'] = legacy_snapshot(previous[0])
        if legacy_proof['before_sha256'] != legacy_proof['after_sha256']:
            raise StudioError('Legacy mesh changed during archival; restore checkpoint')
    receipt = {"checkpoint": saved, "object": obj.name, "vertices": len(payload["rest_cm"]),
        "archived_simulations": [] if legacy else [o.name for o in previous],
        "archived_legacy_panels": [o.name for o in previous] if legacy else [],
        "legacy_archive": legacy_proof,
        "sewing_edges": sum(len(s["pairs"]) for s in payload["seams"].values() if s["kind"] == "permanent"),
        "derived_mesh": obj["a3d_sewing_mesh"], "derived_mesh_sha256": sha(path), "context": context,
        "simulation": "NOT_EXECUTED", "visual_validation": "NOT_EXECUTED",
        "experimental_prefit": payload.get('experimental_prefit')}
    from a3d.garment_receipts import write_receipt
    stored = write_receipt(project, data['component_id'], component['package']['sha256'], receipt)
    obj['a3d_garment_receipt'] = stored['path']
    obj['a3d_garment_receipt_sha256'] = stored['sha256']
    # Persist the object-to-receipt binding, preserving the historical global file.
    bpy.ops.wm.save_as_mainfile(filepath=rec['working'], check_existing=False)
    receipt['receipt'] = stored
    return receipt


def verify_legacy_import(project_root, package_dir, checkpoint_receipt):
    """Check a recoverable historical import without starting a scene mutation."""
    import bpy
    from blender.legacy import checkpoint_import_proof, has_legacy_identity
    project, _ = working(project_root)
    data = read_json(inside(project.root, package_dir) / 'garment.json')
    _, component = project.ready(data['component_id'])
    objects = [obj for obj in bpy.data.objects if obj.get('a3d_component_id') == data['component_id']]
    if len(objects) != 1 or not has_legacy_identity(objects[0], data['component_id'], component['package']['sha256']):
        raise StudioError('Recovery requires one current unversioned legacy mesh with this component/package')
    proof = checkpoint_import_proof(project, objects[0].name, data, component['package']['sha256'], checkpoint_receipt)
    return {**proof, 'checked_only': True, 'visual_validation': 'NOT_EXECUTED'}


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
        if not any(key in obj for key in ('a3d_role', 'a3d_sewing_mesh', 'a3d_sewing_mesh_sha256')):
            from blender.legacy import legacy_snapshot
            objects[-1]['legacy_snapshot_sha256'] = legacy_snapshot(obj)
    from blender.sewing import collider_info
    colliders = [collider_info(o) for o in bpy.context.scene.objects if o.type == "MESH" and any(m.type == "COLLISION" for m in o.modifiers)]
    report = {"blender_version": bpy.app.version_string, "working": rec["working"], "is_dirty": bpy.data.is_dirty, "objects": objects, "auxiliary_colliders": colliders,
              "evaluated_geometry": "NOT_EXECUTED", "identity": "NOT_EXECUTED", "visual": "NOT_EXECUTED",
              "note": "Counts are evidence, not automatic acceptance; evaluate modifiers, rig deformation and silhouette separately."}
    atomic_json(project.data / "blender/inspection.json", report)
    return report


def _perform(project_root, operation, arguments):
    if operation != "run_script":
        from blender.sewing import simulate_sewn, freeze_sewn
        from blender.viewport import frame_view
        from blender.placement import inspect_sewing_placement
        from blender.fitting import inspect_garment_fit, propose_pattern_adjustment
        from a3d.sewing_diagnostics import inspect_failure
        from a3d.garment_rejections import inspect_rejection
        if operation == 'inspect_garment_failure':
            return inspect_rejection(Project(project_root), **arguments)
        if operation == 'inspect_sewing_failure':
            return inspect_failure(Project(project_root), **arguments)
        return {"prepare": prepare, "resume": resume, "inspect": inspect, "frame_view": frame_view, "verify_legacy_import": verify_legacy_import,
            "garment": garment, "assemble": assemble,
            "inspect_sewing_placement": inspect_sewing_placement,
            "inspect_garment_fit": inspect_garment_fit, "propose_pattern_adjustment": propose_pattern_adjustment,
            "simulate_sewn": simulate_sewn, "freeze_sewn": freeze_sewn}[operation](project_root, **arguments)
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
        from blender.sewing import (managed_inputs, preflight, apply_physics, physical_snapshot,
            mesh_digest, trial_binding, object_mesh)
        from a3d.core import digest
        sim_obj, sim_payload, sim_recipe = managed_inputs(project, plan["component_id"], plan["sewing_recipe"])
        sim_context, sim_colliders, sim_trees = preflight(sim_obj, sim_payload, sim_recipe)
        local_path = project.data / "blender/sewing" / (plan["component_id"] + "-local.json")
        expected_binding = trial_binding(sim_obj, sim_payload, sim_recipe, plan["phase"], sim_context)
        if not local_path.exists() or read_json(local_path).get("binding") != expected_binding or read_json(local_path).get("simulation") != "PASS":
            raise StudioError("Custom simulation requires the current native local trial")
        if not any(c["role"] == "mannequin" for c in sim_recipe["colliders"]):
            raise StudioError("Custom garment simulation requires its auxiliary mannequin")
        sim_initial = object_mesh(sim_obj)[0]
        sim_base_hash = mesh_digest(sim_obj)
        _, _, sim_collection = apply_physics(sim_obj, sim_payload, sim_recipe, plan["phase"], sim_colliders)
        sim_expected = physical_snapshot(sim_obj)
    saved = state.get("pending_blender_operation", {}).get("checkpoint") or checkpoint(project_root)
    path = inside(project.root, arguments["path"])
    if sha(path) != arguments["sha256"]:
        raise StudioError("Script changed after admission")
    # Authored scripts remain trusted Python, not sandboxed code. They cannot
    # serve as arbitrary reconstruction entrypoints; retain a recovery copy.
    runpy.run_path(str(path), init_globals={"A3D_PROJECT_ROOT": str(project.root)}, run_name="__a3d_operation__")
    working(project_root)
    if arguments["purpose"] == "simulate":
        from blender.sewing import verify_physics, preflight, object_mesh, penetration_cm
        from a3d.sewing import distance, mesh_quality
        verify_physics(sim_obj, sim_expected)
        preflight(sim_obj, sim_payload, sim_recipe)
        final = object_mesh(sim_obj, True)[0]
        if mesh_digest(sim_obj) != sim_base_hash:
            raise StudioError("Custom simulation changed the base mesh instead of evaluating Cloth")
        movement = max(distance(a,b)*100 for a,b in zip(sim_initial,final,strict=True))
        if bpy.context.scene.frame_current != plan["frame_end"] or movement < sim_recipe["limits"]["min_movement_cm"]:
            raise StudioError("Custom script produced no measured completed cloth response")
        final_cm = [[v*100 for v in p] for p in final]
        mesh_quality(sim_payload['rest_cm'], final_cm, sim_payload['faces'], sim_recipe['mesh'])
        if movement > sim_recipe['limits']['max_displacement_cm'] or penetration_cm(final_cm, sim_trees) > sim_recipe['limits']['max_penetration_cm']:
            raise StudioError('Custom simulation exceeded displacement or contact limits')
        if any(distance(final_cm[a], final_cm[b]) > sim_recipe['limits']['max_seam_gap_cm']
            for seam in sim_payload['seams'].values() if seam['kind'] == 'permanent' for a,b in seam['pairs']):
            raise StudioError('Custom simulation did not settle the permanent seams')
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
    if operation in ("prepare", "resume", "inspect", "frame_view", "inspect_sewing_failure", "inspect_garment_failure", "inspect_sewing_placement", "inspect_garment_fit", "propose_pattern_adjustment", "verify_legacy_import"):
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
            if getattr(exc, 'garment_diagnostic', None):
                state['pending_blender_operation']['diagnostic'] = exc.garment_diagnostic
            project.save(db, state, "blender_failed", {"operation": operation, "error": str(exc)})
        raise
