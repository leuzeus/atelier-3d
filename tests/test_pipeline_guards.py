import copy
import importlib.util
import json
import os
from pathlib import Path
from unittest.mock import patch

from a3d.core import ROOT, StudioError, atomic_json, read_json, sha
from a3d.guard import admit_operation, code_for, parse_code
from a3d.planning import admission, build_board, require_board
from a3d.tools import call
from tests.test_core import Case
from tests.support import ready_project, construction_dossier


class PipelineGuards(Case):
    def test_prepared_blender_code_requires_user_permission_before_execution(self):
        ready_project(self.root, True, False)
        result = call("studio_blender_operation", {
            "project_root": str(self.root), "operation": "prepare", "arguments": {}})
        self.assertFalse(result["executed"])
        self.assertEqual(parse_code(result["code"])["operation"], "prepare")
        self.assertIn("explicitly ask for permission", result["next"])
        self.assertIn("wait for their affirmative reply", result["next"])
        self.assertIn("execute_blender_code_for_cli", result["next"])
        self.assertIn("never bypass it", result["next"])

    def test_cutting_board_does_not_approve_itself(self):
        p = ready_project(self.root, True, False)
        self.assertNotIn("construction", p.state()["gates"])
        self.assertFalse(admission(p)["admitted"])
        with self.assertRaisesRegex(StudioError, "construction"):
            p.transition("RECONSTRUCTING", "brief")

    def test_human_rejection_blocks_reconstruction(self):
        p = ready_project(self.root, True, False)
        p.gate("construction", False, "Sleeve cutting rejected", ["construction-board"], "test:reject")
        with self.assertRaises(StudioError):
            p.transition("RECONSTRUCTING", "brief")

    def test_approval_of_unrelated_evidence_is_insufficient(self):
        p = ready_project(self.root, True, False)
        p.gate("construction", True, "General permission to start", ["brief"], "test:general")
        with self.assertRaisesRegex(StudioError, "construction-board"):
            p.transition("RECONSTRUCTING", "brief")

    def test_both_routes_with_reviewed_boards_are_admitted(self):
        for garment in (True, False):
            with self.subTest(garment=garment):
                root = self.root / str(garment)
                p = ready_project(root, garment)
                self.assertTrue(admission(p)["admitted"])
                p.ready("garment.coat" if garment else "body.skull")

    def test_changed_dossier_invalidates_cutting_approval(self):
        p = ready_project(self.root, True)
        path = p.data / "evidence/construction.json"
        data = read_json(path); data["assumptions"].append("Different mannequin")
        atomic_json(path, data)
        with self.assertRaisesRegex(StudioError, "changed"):
            p.ready("garment.coat")

    def test_changed_exploded_image_invalidates_cutting_approval(self):
        p = ready_project(self.root, True)
        (p.data / "evidence/synthetic-board.png").write_bytes(b"changed")
        self.assertFalse(admission(p)["admitted"])

    def test_changed_board_pixels_invalidates_approval(self):
        p = ready_project(self.root, True)
        board = require_board(p, p.state())
        (p.root / board["image"]).write_text("changed")
        self.assertFalse(admission(p)["admitted"])

    def test_changed_package_invalidates_approval(self):
        p = ready_project(self.root, True)
        package = p.root / p.state()["components"]["garment.coat"]["package"]["path"]
        with package.open("ab") as f: f.write(b"changed")
        self.assertFalse(admission(p)["admitted"])

    def test_route_cannot_silently_switch(self):
        p = ready_project(self.root, True)
        with p.transaction() as db:
            s = p.state(db); s["components"]["garment.coat"]["route"]["selected"] = "MULTIVIEW_PART"
            p.save(db, s, "test_corruption", {})
        self.assertFalse(admission(p)["admitted"])

    def test_dossier_must_cover_exact_pattern_pieces(self):
        p = ready_project(self.root, True, False)
        data = construction_dossier(p, True)
        data["components"]["garment.coat"]["pieces"].pop()
        atomic_json(p.data / "evidence/construction.json", data)
        with self.assertRaisesRegex(StudioError, "exact garment"):
            build_board(p, ".a3d/evidence/construction.json")

    def test_dimension_mismatch_rejected(self):
        p = ready_project(self.root, True, False)
        data = construction_dossier(p, True)
        data["components"]["garment.coat"]["pieces"][0]["dimensions_cm"] = [18, 40]
        atomic_json(p.data / "evidence/construction.json", data)
        with self.assertRaisesRegex(StudioError, "dimensions"):
            build_board(p, ".a3d/evidence/construction.json")

    def test_board_has_three_sections_and_package_contours(self):
        import xml.etree.ElementTree as ET
        p = ready_project(self.root, True, False)
        manifest = read_json(p.root / p.state()["evidence"]["construction-board"]["path"])
        svg = (p.root / manifest["image"]).read_text(encoding="utf-8")
        for text in ("1. VUES ORTHOGRAPHIQUES", "2. DÉCOMPOSITION", "3. PATRONS 2D", "PROPOSITION À VALIDER"):
            self.assertIn(text, svg)
        dom = ET.fromstring(svg)
        self.assertEqual(len(dom.findall("{http://www.w3.org/2000/svg}polygon")), 4)
        self.assertEqual(len(dom.findall(".//{http://www.w3.org/2000/svg}image")), 5)
        self.assertIn("torso-right", (p.root / manifest["technical_dossier"]).read_text())

    def test_board_requires_original_reference_trace_for_every_piece(self):
        p = ready_project(self.root, True, False)
        data = construction_dossier(p, True)
        data["components"]["garment.coat"]["pieces"][0]["source_evidence_keys"] = ["unrelated-image"]
        atomic_json(p.data / "evidence/construction.json", data)
        with self.assertRaisesRegex(StudioError, "original image"):
            build_board(p, ".a3d/evidence/construction.json")

    def test_construction_board_cannot_use_result_mesh_as_design_basis(self):
        p = ready_project(self.root, True, False)
        data = construction_dossier(p, True)
        data["orthographic"]["front"]["basis"] = "mesh-render"
        atomic_json(p.data / "evidence/construction.json", data)
        with self.assertRaises(StudioError):
            build_board(p, ".a3d/evidence/construction.json")

    def test_changed_original_reference_invalidates_review(self):
        p = ready_project(self.root, True)
        (p.data / "source/original.png").write_bytes(b"another image")
        self.assertFalse(admission(p)["admitted"])

    def test_arbitrary_reconstruction_script_is_rejected(self):
        p = ready_project(self.root, True)
        path = p.root / "surfaces.py"; path.write_text("raise AssertionError('must not execute')")
        for purpose in ("reconstruct", "refine", "behavior", "export"):
            with self.subTest(purpose=purpose), self.assertRaises(StudioError):
                admit_operation(p, "run_script", {"purpose": purpose, "path": "surfaces.py", "sha256": sha(path), "component_ids": ["garment.coat"]})

    def test_exact_trampoline_rejects_added_code(self):
        code = code_for(str(self.root), "prepare", {})
        self.assertEqual(parse_code(code)["operation"], "prepare")
        with self.assertRaises(StudioError): parse_code(code + "bpy.ops.mesh.primitive_cube_add()\n")

    def test_dispatch_rechecks_before_importing_blender(self):
        from blender.operations import dispatch
        p = ready_project(self.root, True, False)
        with self.assertRaisesRegex(StudioError, "construction"):
            dispatch(str(p.root), "garment", {"package_dir": "missing"})

    def test_legacy_analyzed_project_is_blocked_without_rewriting_history(self):
        p = ready_project(self.root, True, False)
        with p.transaction() as db:
            s = p.state(db); s["stage"] = "ANALYZED"; s["gates"].pop("construction", None)
            s["components"]["garment.coat"]["package"] = None
            p.save(db, s, "legacy_fixture", {})
        before = p.state()
        self.assertFalse(call("studio_check_pipeline", {"project_root": str(p.root)})["admitted"])
        self.assertEqual(before, p.state())


class HookGuards(Case):
    def setUp(self):
        super().setUp()
        spec = importlib.util.spec_from_file_location("pipeline_hook", ROOT / "hooks/handler.py")
        self.hook = importlib.util.module_from_spec(spec); spec.loader.exec_module(self.hook)

    def event(self, tool, args=None, **kwargs):
        return {"hook_event_name": "PreToolUse", "cwd": str(self.root), "tool_name": tool, "tool_input": args or {}, **kwargs}

    def test_raw_blender_denied_while_summaries_allowed(self):
        ready_project(self.root, True, False)
        result = self.hook.handle(self.event("mcp__blender_lab__execute_blender_code", {"code": "import bpy\nbpy.ops.mesh.primitive_cube_add()"}))
        self.assertEqual(result["hookSpecificOutput"]["permissionDecision"], "deny")
        result = self.hook.handle(self.event("mcp__blender_lab__get_blendfile_summary_path_info"))
        self.assertNotIn("permissionDecision", result["hookSpecificOutput"])

    def test_session_binding_survives_projectless_cwd(self):
        project_root = self.root / "asset"
        ready_project(project_root, True, False)
        with patch.dict(os.environ, {"PLUGIN_DATA": str(self.root / "data"), "A3D_CONFIG": ""}):
            self.hook.handle(self.event("mcp__studio__studio_project_status", {"project_root": str(project_root)}, session_id="thread-one"))
            event = self.event("mcp__blender_lab__execute_blender_code", {"code": "import bpy"}, session_id="thread-one")
            self.assertEqual(self.hook.handle(event)["hookSpecificOutput"]["permissionDecision"], "deny")
            self.assertEqual(self.hook.handle({**event, "session_id": "another-thread"}), {})

    def test_known_shell_and_native_comfy_bypasses_rejected(self):
        ready_project(self.root, True, False)
        for name, args in (("exec_command", {"cmd": "blender.exe --background --python surfaces.py"}), ("mcp__comfy__run_workflow", {})):
            self.assertEqual(self.hook.handle(self.event(name, args))["hookSpecificOutput"]["permissionDecision"], "deny")

    def test_prepare_is_allowed_without_fabricating_approval(self):
        ready_project(self.root, True, False)
        code = code_for(str(self.root), "prepare", {})
        result = self.hook.handle(self.event("mcp__blender_lab__execute_blender_code", {"code": code}))
        self.assertNotIn("permissionDecision", result["hookSpecificOutput"])
