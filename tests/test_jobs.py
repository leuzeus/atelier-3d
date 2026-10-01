from pathlib import Path
from a3d.comfy import Comfy
from a3d.core import StudioError, atomic_json, read_json
from a3d.config import load_config
from tests.test_core import Case
from tests.support import FakeNative, ready_project


class NativeAdapterTests(Case):
    def setUp(self):
        super().setUp()
        self.project=ready_project(self.root)
        self.native=FakeNative()
        self.client=Comfy(factory=self.native)
        self.params={}
        for view in ("front","left"):
            rec=self.client.upload(self.root,f".a3d/source/package/{view}.clean.png")
            self.params[view]=rec["input_name"]

    def submit(self,key="run-1"):
        return self.client.submit(self.root,"body.skull","hunyuan-multiview",self.params,key)

    def test_submits_through_official_mcp_async_without_spending(self):
        job=self.submit()
        args=[a for n,a in self.native.calls if n=="run_workflow"][0]
        self.assertFalse(args["wait"]); self.assertFalse(args["confirm_spend"])
        self.assertTrue(Path(args["workflow_path"]).is_file())
        self.assertEqual(job["prompt_id"],"native-prompt-1")

    def test_request_key_prevents_duplicate_submission(self):
        first=self.submit(); second=self.submit()
        self.assertEqual(first["job_id"],second["job_id"])
        self.assertEqual(sum(n=="run_workflow" for n,_ in self.native.calls),1)

    def test_key_cannot_change_parameters(self):
        self.submit(); self.params["seed"]=900
        with self.assertRaises(StudioError): self.submit()

    def test_invalid_native_validation_never_submits(self):
        self.native.valid=False
        self.assertEqual(self.submit()["status"],"failed")
        self.assertFalse(any(n=="run_workflow" for n,_ in self.native.calls))

    def test_transport_uncertainty_never_automatically_retries(self):
        self.native.fail_submit=True
        self.assertEqual(self.submit()["status"],"submission_unknown")
        self.submit()
        self.assertEqual(sum(n=="run_workflow" for n,_ in self.native.calls),1)
        with self.assertRaises(StudioError): self.submit("run-2")

    def test_pending_gate_blocks_gpu(self):
        self.project.gate("references",False,"Rejected",["brief"],"test:reject")
        with self.assertRaises(StudioError): self.submit()
        self.assertFalse(any(n=="run_workflow" for n,_ in self.native.calls))

    def test_upload_cannot_escape_project(self):
        with self.assertRaises(StudioError): self.client.upload(self.root,"../private.png")

    def test_local_reference_change_blocks_gpu(self):
        (self.project.data/"source/package/front.clean.png").write_bytes(b"changed")
        with self.assertRaises(StudioError): self.submit()

    def test_annotations_rejected_as_clean(self):
        path=self.project.data/"annotations/front.overlay.png"; path.write_bytes(b"x")
        with self.assertRaises(StudioError): self.client.upload(self.root,".a3d/annotations/front.overlay.png")

    def test_unknown_status_not_complete(self):
        job=self.submit(); self.native.status="new-status"
        self.assertEqual(self.client.status(self.root,job["job_id"])["status"],"unknown")

    def test_completed_job_is_not_accepted_geometry(self):
        job=self.submit()
        self.assertEqual(self.client.status(self.root,job["job_id"])["status"],"completed")
        self.assertEqual(self.project.state()["components"]["body.skull"]["stage"],"RECONSTRUCTING")

    def test_outputs_download_hash_and_reuse(self):
        job=self.submit(); first=self.client.outputs(self.root,job["job_id"],True)
        second=self.client.outputs(self.root,job["job_id"],True)
        self.assertEqual(first,second); self.assertTrue(first["outputs"])
        self.assertEqual(sum(n=="fetch_outputs" for n,_ in self.native.calls),1)

    def test_late_failed_status_does_not_undo_accepted_reconstruction(self):
        from tests.lifecycle_support import accept
        job = self.submit()
        accept(self.project)
        self.native.status = "failed"
        self.assertEqual(self.client.status(self.root, job["job_id"])["status"], "failed")
        self.assertEqual(self.project.state()["components"]["body.skull"]["stage"], "RECONSTRUCTED")

    def test_changed_output_not_silently_reused(self):
        job=self.submit(); result=self.client.outputs(self.root,job["job_id"],True)
        (self.root/result["outputs"][0]["path"]).write_bytes(b"changed")
        with self.assertRaises(StudioError): self.client.outputs(self.root,job["job_id"],True)

    def test_foreign_job_refused(self):
        with self.assertRaises(StudioError): self.client.status(self.root,"not-owned")

    def test_cancellation_does_not_issue_global_interrupt(self):
        job=self.submit(); response=self.client.cancel(self.root,job["job_id"])
        self.assertEqual(response["cancellation"],"requires_native_review")
        self.assertFalse(any(n=="job" and a.get("action")=="cancel" for n,a in self.native.calls))

    def test_pipeline_mismatch_refused(self):
        with self.project.transaction() as db:
            state=self.project.state(db); state["components"]["body.skull"]["route"]["selected"]="PATTERN_SEWN"
            self.project.save(db,state,"fixture",{})
        with self.assertRaises(StudioError): self.submit()

    def test_clean_views_must_be_explicitly_reviewed(self):
        self.project.gate("references",True,"Only brief approved",["brief"],"test:limited")
        with self.assertRaises(StudioError): self.submit()


    def test_busy_known_native_queue_never_submits(self):
        self.native.queue=[{"prompt_id":"other-project","status":"running"}]
        self.assertEqual(self.submit()["status"],"failed")
        self.assertFalse(any(n=="run_workflow" for n,_ in self.native.calls))

    def test_unknown_native_queue_never_submits(self):
        self.native.queue=[{"prompt_id":"other-project","status":"unknown-new-value"}]
        self.assertEqual(self.submit()["status"],"failed")
        self.assertFalse(any(n=="run_workflow" for n,_ in self.native.calls))
