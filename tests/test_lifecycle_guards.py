from a3d.core import StudioError, atomic_json, read_json, sha
from a3d.guard import admit_operation
from a3d.lifecycle import required_final_checks, simulation_plan
from a3d.comfy import Comfy
from a3d.store import Project
from tests.test_core import Case
from tests.support import ready_project, asset, png, FakeNative
from tests.lifecycle_support import accept, plan, assembled, refined, final_ready, reconstruction_report, evidence, stage_report, visual


class LifecycleTests(Case):
    def test_reconstruction_pass_without_check_proof_is_refused(self):
        p = ready_project(self.root)
        report = reconstruction_report(p)
        report["check_evidence"].pop("geometry")
        evidence(p, "reconstruction", report)
        with self.assertRaisesRegex(StudioError, "Every check"):
            p.accept_reconstruction("body.skull", "reconstruction")

    def test_reconstruction_visual_must_bind_exact_artifact(self):
        p = ready_project(self.root)
        report = reconstruction_report(p)
        key = report["visual_review_evidence"]
        data = read_json(p.root / p.state()["evidence"][key]["path"])
        data["artifacts"] = [{"path": ".a3d/source/original.png", "sha256": sha(p.data / "source/original.png")}]
        evidence(p, key, data)
        evidence(p, "reconstruction", report)
        with self.assertRaisesRegex(StudioError, "exact candidate"):
            p.accept_reconstruction("body.skull", "reconstruction")

    def test_accepted_reconstruction_cannot_be_replaced_in_place(self):
        p = ready_project(self.root)
        report = reconstruction_report(p)
        evidence(p, "reconstruction", report)
        p.accept_reconstruction("body.skull", "reconstruction")
        with self.assertRaisesRegex(StudioError, "only once"):
            p.accept_reconstruction("body.skull", "reconstruction")

    def test_assembly_rechecks_accepted_input(self):
        p = ready_project(self.root)
        accept(p)
        data = plan(p)
        (p.root / data["components"][0]["path"]).write_bytes(b"changed")
        with self.assertRaisesRegex(StudioError, "changed artifact"):
            p.transition("ASSEMBLING", "brief")

    def test_assembly_approval_of_brief_does_not_approve_plan(self):
        p = ready_project(self.root)
        accept(p)
        plan(p)
        p.gate("assembly", True, "Synthetic wrong evidence", ["brief"], "test:wrong")
        with self.assertRaisesRegex(StudioError, "exact assembly-plan"):
            p.transition("ASSEMBLING", "brief")

    def test_assembly_requires_every_component_once(self):
        p = ready_project(self.root)
        accept(p)
        data = plan(p)
        data["components"] *= 2
        evidence(p, "assembly-plan", data)
        p.gate("assembly", True, "Synthetic duplicate plan", ["assembly-plan"], "test:duplicate")
        with self.assertRaisesRegex(StudioError, "all components exactly once"):
            p.transition("ASSEMBLING", "brief")

    def test_changed_working_scene_invalidates_assembly_baseline(self):
        p = ready_project(self.root)
        accept(p)
        data = plan(p)
        (p.root / data["working_blend"]).write_bytes(b"unreviewed edits")
        with self.assertRaisesRegex(StudioError, "changed artifact"):
            p.transition("ASSEMBLING", "brief")

    def test_refinement_cannot_start_before_assembly_receipt(self):
        p = ready_project(self.root)
        accept(p)
        plan(p)
        p.transition("ASSEMBLING", "brief")
        with self.assertRaises(StudioError):
            p.transition("REFINING", "brief")

    def test_behavior_requires_refinement_checks_and_silhouette(self):
        p = ready_project(self.root)
        assembled(p)
        with self.assertRaises(StudioError):
            p.transition("BEHAVIOR_AUTHORING", "brief")
        stage_report(p, "refinement-validation", "REFINING", ("geometry", "scale", "orientation", "separation"))
        p.gate("silhouette", True, "Synthetic wrong approval", ["brief"], "test:wrong")
        with self.assertRaisesRegex(StudioError, "silhouette-review"):
            p.transition("BEHAVIOR_AUTHORING", "brief")
        refined(p)

    def test_visual_approval_cannot_transfer_to_another_scene(self):
        p = ready_project(self.root)
        data = assembled(p)
        old_artifact = stage_report(p, "refinement-validation", "REFINING", ("geometry", "scale", "orientation", "separation"))
        visual(p, "silhouette-review", "silhouette", [old_artifact])
        p.gate("silhouette", True, "Synthetic silhouette", ["silhouette-review"], "test:visual")
        (p.root / data["working_blend"]).write_bytes(b"new candidate")
        stage_report(p, "updated-refinement", "REFINING", ("geometry", "scale", "orientation", "separation"))
        # Keep the old visual snapshot immutable; refresh only technical checks.
        report = read_json(p.data / "evidence/updated-refinement.json")
        evidence(p, "refinement-validation", report)
        with self.assertRaisesRegex(StudioError, "current working scene"):
            p.transition("BEHAVIOR_AUTHORING", "brief")

    def test_animation_cannot_skip_behavior_validation(self):
        p = ready_project(self.root)
        assembled(p)
        refined(p)
        with self.assertRaises(StudioError):
            p.transition("VALIDATING", "brief")

    def test_game_garment_requires_rig_clearance_and_engine_import(self):
        data = asset(True)
        data["target"] = "game"
        checks = required_final_checks({"asset": data})
        self.assertTrue({"rig", "weighting", "clearance", "target_import", "uv", "budget"} <= checks)
        data["components"][0]["features"].update(sewn=False, articulated=False)
        self.assertNotIn("rig", required_final_checks({"asset": data}))

    def test_final_approval_requires_the_visual_manifest(self):
        p = ready_project(self.root)
        final_ready(p)
        p.gate("final", True, "Synthetic incomplete approval", ["final-validation"], "test:missing-view")
        with self.assertRaisesRegex(StudioError, "also bind"):
            p.transition("COMPLETE", "brief")

    def test_final_changed_check_evidence_is_rejected(self):
        p = ready_project(self.root)
        report = final_ready(p)
        (p.root / report["check_evidence"]["rig"]["path"]).write_bytes(b"changed proof")
        with self.assertRaisesRegex(StudioError, "changed artifact"):
            p.transition("COMPLETE", "brief")

    def test_final_changed_review_image_is_rejected(self):
        p = ready_project(self.root)
        final_ready(p)
        (p.data / "evidence/final-review.png").write_bytes(png(32, 32))
        with self.assertRaisesRegex(StudioError, "changed artifact"):
            p.transition("COMPLETE", "brief")

    def test_pending_operation_blocks_mutations_and_transitions_but_allows_recovery(self):
        p = ready_project(self.root)
        checkpoint = p.data / "checkpoints/synthetic.blend"
        checkpoint.write_bytes(b"synthetic checkpoint")
        with p.transaction() as db:
            state = p.state(db)
            state["pending_blender_operation"] = {"checkpoint": {"path": checkpoint.relative_to(p.root).as_posix(), "sha256": sha(checkpoint)}}
            p.save(db, state, "fixture", {})
        with self.assertRaisesRegex(StudioError, "restore_checkpoint"):
            admit_operation(p, "prepare", {})
        with self.assertRaisesRegex(StudioError, "restore_checkpoint"):
            p.transition("RECONSTRUCTED", "brief")
        admit_operation(p, "inspect", {})
        from a3d.planning import admission
        self.assertFalse(admission(p)["admitted"])
        self.assertIn("restore_checkpoint", admission(p)["issues"][0])
        self.assertTrue(p.summary()["pending_blender_operation"])
        admit_operation(p, "restore_checkpoint", {})
        checkpoint.write_bytes(b"corrupt checkpoint")
        with self.assertRaises(StudioError):
            admit_operation(p, "restore_checkpoint", {})

    def test_simulation_budget_and_colliders_are_checked(self):
        p = ready_project(self.root, garment=True)
        data = {"component_id": "garment.coat", "type": "cloth", "frame_start": 1, "frame_end": 24,
                "quality": 10, "collision_components": [], "baked": False, "max_frames": 24,
                "sewing_recipe": ".a3d/evidence/sewing-recipe.json", "phase": "mount"}
        from a3d.core import ROOT, read_json
        atomic_json(p.root / data['sewing_recipe'], read_json(ROOT / 'templates/sewing-recipe.json'))
        path = ".a3d/evidence/simulation.json"
        atomic_json(p.root / path, data)
        simulation_plan(p, p.state(), path, ["garment.coat"])
        for patch in ({"frame_end": 200}, {"collision_components": ["unknown.collider"]}, {"baked": True}):
            atomic_json(p.root / path, {**data, **patch})
            with self.assertRaises(StudioError):
                simulation_plan(p, p.state(), path, ["garment.coat"])


class ReferenceSourceTests(Case):
    def setUp(self):
        super().setUp()
        self.p = Project.create(self.root, asset())
        evidence(self.p, "brief", {"synthetic": True})
        self.p.transition("SPECIFIED", "brief")
        (self.p.data / "source/original.png").write_bytes(png())
        self.p.evidence("reference.original", ".a3d/source/original.png")
        self.native = FakeNative()
        self.client = Comfy(factory=self.native)

    def test_text_alone_cannot_generate_reference(self):
        with self.assertRaises(StudioError):
            self.client.submit(self.root, "body.skull", "reference-sd15", {"prompt": "synthetic test"}, "reference-1")
        self.assertFalse(any(n == "run_workflow" for n, _ in self.native.calls))

    def test_original_image_is_consumed_and_provenance_retained(self):
        upload = self.client.upload(self.root, ".a3d/source/original.png", purpose="source")
        job = self.client.submit(self.root, "body.skull", "reference-sd15", {"prompt": "synthetic test", "source": upload["input_name"]}, "reference-1")
        self.assertEqual(job["source_images"], [upload])
        args = next(a for n, a in self.native.calls if n == "run_workflow")
        graph = read_json(args["workflow_path"])
        self.assertEqual(graph["4"]["class_type"], "VAEEncode")
        self.assertEqual(graph["8"]["inputs"]["image"], upload["input_name"])
        self.assertNotIn("EmptyLatentImage", str(graph))

    def test_clean_upload_cannot_impersonate_original(self):
        upload = self.client.upload(self.root, ".a3d/source/original.png", purpose="clean")
        with self.assertRaisesRegex(StudioError, "original source"):
            self.client.submit(self.root, "body.skull", "reference-sd15", {"prompt": "test", "source": upload["input_name"]}, "reference-1")

    def test_changed_original_blocks_reference_generation(self):
        upload = self.client.upload(self.root, ".a3d/source/original.png", purpose="source")
        (self.p.data / "source/original.png").write_bytes(png(32, 64))
        with self.assertRaisesRegex(StudioError, "source changed"):
            self.client.submit(self.root, "body.skull", "reference-sd15", {"prompt": "test", "source": upload["input_name"]}, "reference-1")
