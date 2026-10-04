import json
import shutil
import uuid
import zipfile
from pathlib import Path
from .config import load_config
from .core import ROOT, StudioError, atomic_json, digest, ident, inside, now, read_json, relative, sha, validate
from .official_mcp import OfficialMCP
from .packages import png_dimensions
from .store import ACTIVE_JOBS, Project

class Comfy:
    """Domain admission and receipts; execution belongs to official Comfy MCP."""
    def __init__(self, config=None, factory=OfficialMCP):
        self.config = config or load_config()
        self.options = self.config["comfyui"]
        self.base = self.options["base_url"].rstrip("/")
        self.factory = factory

    def health(self):
        with self.factory(self.config) as native:
            value = native.call("server_info")
            server = value.get("server", value)
            if not isinstance(server, dict) or type(server.get("running")) is not bool:
                raise StudioError("Native server_info has no recognized running status")
            return {**value, "running": server["running"], "url": server.get("url", self.base)}

    def capabilities(self):
        with self.factory(self.config) as native:
            return {"provider": "Comfy-Org/comfy-mcp", "tools": sorted(native.names),
                    "nodes": native.call("nodes", {"action": "list"}),
                    "model_folders": native.call("search_models")}

    def template(self, workflow_id, overrides=None, project=None):
        ident(workflow_id)
        registry = read_json(ROOT / "workflows/comfy/registry.json")
        if workflow_id not in registry["workflows"]:
            if project is None:
                raise StudioError("Unknown workflow; register a reviewed API-format template first")
            from .workflow_variants import load_variant
            spec, graph, variant = load_variant(project, workflow_id)
            if variant['status'] != 'COMPATIBLE' or variant['endpoint'] != self.base:
                raise StudioError('Workflow variant is incompatible or belongs to another endpoint')
            if any(variant['parameters'].get(key) != value for key, value in (overrides or {}).items()):
                raise StudioError('Changed variant parameters require a newly prepared variant')
            overrides = dict(variant['parameters'])
        else:
            spec = registry["workflows"][workflow_id]
            graph = read_json(inside(ROOT / "workflows/comfy", spec["file"]))
        overrides = overrides or {}
        unknown = set(overrides) - spec["parameters"].keys()
        if unknown:
            raise StudioError(f"Unregistered parameters: {sorted(unknown)}")
        for name, descriptor in spec["parameters"].items():
            value = overrides.get(name, descriptor.get("default"))
            if value is None:
                if descriptor.get("required", False):
                    raise StudioError(f"Missing workflow parameter: {name}")
                continue
            validate(value, descriptor["schema"], f"parameters.{name}")
            node, field = descriptor["target"]
            if node not in graph or field not in graph[node]["inputs"]:
                raise StudioError("Registry target absent from API graph")
            graph[node]["inputs"][field] = value
        return spec, graph

    def admit(self, project, component_id, spec, graph, db=None):
        state = project.state(db)
        if component_id not in state["components"]:
            raise StudioError("Unknown component")
        if spec["phase"] == "reconstruction":
            from .lifecycle import no_pending_operation
            no_pending_operation(state)
            if state["stage"] != "RECONSTRUCTING":
                raise StudioError("Reconstruction submission requires RECONSTRUCTING")
            state, component = project.ready(component_id, db)
            if component["route"]["selected"] != spec["pipeline"]:
                raise StudioError("Workflow pipeline mismatches component")
            if component["stage"] == "RECONSTRUCTED":
                raise StudioError("Component already reconstructed; do not rerun successful work")
            if spec["pipeline"] != "MULTIVIEW_PART":
                raise StudioError("Garment sewing is performed in Blender")
            with zipfile.ZipFile(inside(project.root, component["package"]["path"])) as archive:
                part = json.loads(archive.read("part.json"))
            consumed = spec.get("view_parameters", {})
            if not set(part["required_views"]).issubset(consumed):
                raise StudioError("Workflow does not consume every required view")
            reviewed_hashes = {r["sha256"] for r in state["gates"]["references"]["evidence"].values()}
            for view, parameter in consumed.items():
                if view not in part["views"]:
                    raise StudioError(f"Consumed view missing from package: {view}")
                if not parameter:
                    raise StudioError(f"Workflow does not consume required view: {view}")
                node, field = spec["parameters"][parameter]["target"]
                value = graph[node]["inputs"][field]
                uploaded = state.get("uploads", {}).get(value)
                expected = component["package"]["manifest"]["checksums"][part["views"][view]["path"]]
                if expected not in reviewed_hashes:
                    raise StudioError(f"Clean view {view} was not bound to human reference approval")
                if not uploaded or uploaded["purpose"] != "clean" or uploaded["sha256"] != expected or uploaded["endpoint"] != self.base:
                    raise StudioError(f"View {view} does not match clean, bound package input")
                if sha(inside(project.root, uploaded["local_path"])) != expected:
                    raise StudioError("Uploaded local reference changed")
        elif spec["phase"] == "references":
            if state["stage"] not in ("SPECIFIED", "REFERENCES_GENERATING", "REFERENCES_READY"):
                raise StudioError("Project is not in reference generation phase")
            if not spec.get("source_parameters"):
                raise StudioError("Reference generation must consume an original source image")
            for parameter in spec["source_parameters"]:
                node, field = spec["parameters"][parameter]["target"]
                upload = state.get("uploads", {}).get(graph[node]["inputs"][field])
                if not upload or upload["purpose"] != "source" or upload["endpoint"] != self.base:
                    raise StudioError("Reference generation needs an uploaded original source")
                if sha(inside(project.root, upload["local_path"])) != upload["sha256"]:
                    raise StudioError("Original generation source changed")
                if not any(rec["path"] == upload["local_path"] and rec["sha256"] == upload["sha256"] for rec in state["evidence"].values()):
                    raise StudioError("Register the original reference as evidence before generation")
        else:
            raise StudioError("Unknown workflow phase")
        return state


    def validate_workflow(self, workflow_id, parameters=None, project_root=None):
        if not project_root:
            raise StudioError("Provide project_root to retain the exact validated graph")
        project = Project(project_root)
        _, graph = self.template(workflow_id, parameters, project)
        path = inside(project.root, f".a3d/logs/workflow-{digest(graph)}.json", False)
        atomic_json(path, graph)
        with self.factory(self.config, project.root) as native:
            report = native.call("validate_workflow", {"workflow_path": str(path)})
        return {"compatible": report.get("valid") is True, "native_report": report, "workflow_sha256": digest(graph)}

    def upload(self, project_root, path, purpose="clean", original_ref=None):
        project = Project(project_root)
        file = inside(project.root, path)
        if purpose not in ("clean", "mask", "source"):
            raise StudioError("Unsupported image purpose")
        if original_ref is not None:
            raise StudioError("Official MCP stages masks separately; automatic alpha merging is unavailable")
        if purpose == "clean" and any(v in path.lower() for v in (".mask.", "overlay", "annotations/")):
            raise StudioError("Annotations cannot be clean inputs")
        if file.stat().st_size > 32 * 1024 * 1024:
            raise StudioError("Input PNG exceeds 32 MiB")
        dimensions = png_dimensions(file.read_bytes())
        file_hash = sha(file)
        staging = inside(project.root, f".a3d/source/staged-{file_hash}.png", False)
        if not staging.exists():
            with file.open("rb") as src, staging.open("xb") as out:
                shutil.copyfileobj(src, out)
        if sha(staging) != file_hash:
            raise StudioError("Staged input changed")
        with self.factory(self.config, project.root) as native:
            receipt = native.call("upload_file", {"paths": [str(staging)], "overwrite": False})
        uploads = receipt.get("uploads", [])
        if len(uploads) != 1 or not isinstance(uploads[0].get("cloud_name"), str):
            raise StudioError("Unrecognized native upload receipt; do not guess the filename")
        name = relative(uploads[0]["cloud_name"])
        rec = {"local_path": path, "sha256": file_hash, "purpose": purpose, "dimensions": dimensions,
               "reference": {"filename": name, "type": "input", "subfolder": ""}, "input_name": name,
               "endpoint": self.base, "created_at": now(), "provider": "Comfy-Org/comfy-mcp"}
        with project.transaction() as db:
            state = project.state(db)
            state.setdefault("uploads", {})[name] = rec
            project.save(db, state, "native_upload", rec)
        return rec

    def submit(self, project_root, component_id, workflow_id, parameters, request_key):
        project = Project(project_root)
        ident(request_key)
        spec, graph = self.template(workflow_id, parameters, project)
        fingerprint = digest({"component_id": component_id, "workflow_id": workflow_id, "parameters": parameters,
                              "template_sha256": digest(graph), "endpoint": self.base})
        with project.transaction() as db:
            existing = next((j for j in project.jobs(db) if j["request_key"] == request_key), None)
            if existing:
                if existing["fingerprint"] != fingerprint:
                    raise StudioError("Request key reused with different arguments/template")
                return existing
            state = self.admit(project, component_id, spec, graph, db)
            if any(j["status"] in ACTIVE_JOBS or j["status"] == "preparing" for j in project.jobs(db)):
                raise StudioError("Resolve the active/unknown project job first")
            node, field = spec["output_prefix_target"]
            graph[node]["inputs"][field] = f"Atelier3D/{state['project_id']}/{component_id}/{request_key}"
            job_id = str(uuid.uuid4())
            path = inside(project.root, f".a3d/logs/jobs/{job_id}.workflow.json", False)
            atomic_json(path, graph)
            c = state["components"][component_id]
            job = {"job_id": job_id, "prompt_id": None, "request_key": request_key, "fingerprint": fingerprint,
                   "component_id": component_id, "workflow_id": workflow_id, "workflow_sha256": digest(graph),
                   "workflow_path": path.relative_to(project.root).as_posix(), "parameters": parameters,
                   "endpoint": self.base, "status": "preparing", "provider": "Comfy-Org/comfy-mcp",
                   "package_sha256": c["package"]["sha256"] if c["package"] else None,
                   "phase": spec["phase"], "created_at": now()}
            job["source_images"] = [dict(state["uploads"][graph[spec["parameters"][name]["target"][0]]["inputs"][spec["parameters"][name]["target"][1]]]) for name in spec.get("source_parameters", [])]
            project.save_job(db, job)
        try:
            with self.factory(self.config, project.root) as native:
                verdict = native.call("validate_workflow", {"workflow_path": str(path)})
                if verdict.get("valid") is not True:
                    raise StudioError("Native workflow validation did not pass")
                queue = native.call("job", {"action": "queue"})
                rows = queue.get("jobs")
                known = {"pending", "queued", "running", "allocated", "executing",
                         "completed", "error", "failed", "cancelled"}
                if not isinstance(rows, list) or any(not isinstance(r, dict) or r.get("status") not in known for r in rows):
                    raise StudioError("Native queue is unknown; cannot admit GPU work")
                busy = sum(r["status"] in {"pending", "queued", "running", "allocated", "executing"} for r in rows)
                if busy >= self.options["max_parallel_jobs"]:
                    raise StudioError("Native known-job capacity reached; wait and recheck")
                with project.transaction() as db:
                    self.admit(project, component_id, spec, graph, db)
                    if digest(read_json(path)) != job["workflow_sha256"]:
                        raise StudioError("Prepared workflow changed")
                    job["status"] = "submitting"
                    project.save_job(db, job)
                receipt = native.call("run_workflow", {"workflow_path": str(path), "wait": False, "timeout_seconds": 30.0, "confirm_spend": False})
                if not isinstance(receipt.get("prompt_id"), str) or not receipt["prompt_id"]:
                    raise StudioError("Native submission returned no prompt_id")
                job.update(prompt_id=receipt["prompt_id"], status="queued")
        except Exception as exc:
            job.update(status="submission_unknown" if job["status"] == "submitting" else "failed", error=str(exc))
        with project.transaction() as db:
            project.save_job(db, job)
            if spec["phase"] == "reconstruction":
                state = project.state(db)
                state["components"][component_id]["stage"] = "FAILED" if job["status"] == "failed" else "RECONSTRUCTING"
                project.save(db, state, "native_job", {"job_id": job_id, "status": job["status"]})
        return job

    def owned(self, project_root, job_id):
        project = Project(project_root)
        job = project.job(job_id)
        if job["endpoint"] != self.base:
            raise StudioError("Job belongs to a different endpoint")
        return project, job

    def reconcile(self, project_root, job_id):
        """Recover a lost prompt receipt from two provider observations, never resubmit."""
        from datetime import datetime
        project, job = self.owned(project_root, job_id)
        if job.get('prompt_id'):
            return self.status(project_root, job_id)
        if job['status'] != 'submission_unknown':
            raise StudioError('Only an uncertain submission can be reconciled')
        path = inside(project.root, job['workflow_path'])
        if digest(read_json(path)) != job['workflow_sha256']:
            raise StudioError('Uncertain submission graph changed')
        with self.factory(self.config, project.root) as native:
            queue = native.call('job', {'action': 'queue'})
            rows = queue.get('jobs')
            if not isinstance(rows, list):
                raise StudioError('Provider queue shape is unknown')
            candidates = []
            for row in rows:
                if not isinstance(row, dict) or not isinstance(row.get('prompt_id'), str):
                    raise StudioError('Provider queue identity is malformed')
                graph_hash = row.get('workflow_sha256')
                workflow = row.get('workflow_path')
                path_match = isinstance(workflow, str) and Path(workflow).is_absolute() and Path(workflow).resolve() == path
                if graph_hash == job['workflow_sha256'] or path_match:
                    if graph_hash is not None and graph_hash != job['workflow_sha256']:
                        raise StudioError('Provider graph identity contradicts its workflow path')
                    candidates.append(row)
            if len(candidates) != 1:
                return {**job, 'reconciliation': 'AMBIGUOUS' if candidates else 'INSUFFICIENT_PROVIDER_EVIDENCE',
                        'matches': len(candidates), 'next_action': 'Inspect provider evidence; never resubmit automatically'}
            row = candidates[0]
            receipt = native.call('job', {'action': 'status', 'prompt_id': row['prompt_id']})
        if receipt.get('prompt_id') != row['prompt_id']:
            raise StudioError('Provider reconciliation prompt identity contradicts queue')
        if row.get('where', 'local') != 'local':
            raise StudioError('Provider reconciliation target is not local')
        receipt_workflow = receipt.get('workflow')
        if not isinstance(receipt_workflow, str) or Path(receipt_workflow).resolve() != path:
            raise StudioError('Provider status does not corroborate exact workflow identity')
        submitted = receipt.get('submitted_at')
        try:
            if datetime.fromisoformat(submitted.replace('Z', '+00:00')) < datetime.fromisoformat(job['created_at'].replace('Z', '+00:00')):
                raise ValueError('Provider submission predates candidate')
        except (ValueError, TypeError, AttributeError):
            raise StudioError('Provider submission time does not corroborate candidate') from None
        if receipt.get('workflow_sha256', job['workflow_sha256']) != job['workflow_sha256']:
            raise StudioError('Provider status contradicts graph identity')
        mapping = {'pending': 'queued', 'queued': 'queued', 'running': 'running', 'allocated': 'running',
                   'executing': 'running', 'completed': 'completed', 'error': 'failed', 'failed': 'failed', 'cancelled': 'cancelled'}
        status = mapping.get(receipt.get('status'))
        if status is None:
            raise StudioError('Unknown provider status cannot reconcile submission')
        proof = {'provider': 'Comfy-Org/comfy-mcp', 'endpoint': self.base,
                 'observed_at': now(), 'queue': queue, 'status': receipt,
                 'job_id': job_id, 'workflow_sha256': job['workflow_sha256']}
        proof_path = inside(project.root, f'.a3d/logs/jobs/{job_id}.reconciliation-{uuid.uuid4().hex}.json', False)
        atomic_json(proof_path, proof)
        with project.transaction() as db:
            current = project.job(job_id, db)
            if current.get('prompt_id') or current['status'] != 'submission_unknown':
                raise StudioError('Submission changed during reconciliation; reread status')
            if any(j.get('prompt_id') == row['prompt_id'] for j in project.jobs(db) if j['job_id'] != job_id):
                raise StudioError('Provider prompt already belongs to another project job')
            current.update(prompt_id=row['prompt_id'], status=status,
                           reconciliation={'path': proof_path.relative_to(project.root).as_posix(), 'sha256': sha(proof_path)})
            project.save_job(db, current)
            state = project.state(db)
            project.save(db, state, 'native_job_reconciled', {'job_id': job_id, 'prompt_id': row['prompt_id'], 'proof': current['reconciliation']})
        return current

    def status(self, project_root, job_id):
        project, job = self.owned(project_root, job_id)
        if not job.get("prompt_id"):
            return {**job, "recovery": "No prompt_id receipt. Inspect official MCP queue and exact workflow output prefix; never resubmit automatically."}
        with self.factory(self.config, project.root) as native:
            receipt = native.call("job", {"action": "status", "prompt_id": job["prompt_id"]})
        if receipt.get("prompt_id", job["prompt_id"]) != job["prompt_id"]:
            raise StudioError("Upstream status identity mismatch")
        mapping = {"pending": "queued", "queued": "queued", "running": "running", "allocated": "running",
                   "executing": "running", "completed": "completed", "error": "failed", "failed": "failed", "cancelled": "cancelled"}
        raw = receipt.get("status")
        job["status"] = mapping.get(raw, "unknown") if isinstance(raw, str) else "unknown"
        with project.transaction() as db:
            project.save_job(db, job)
            if job["status"] in ("failed", "cancelled") and job["phase"] == "reconstruction":
                state = project.state(db)
                if state["components"][job["component_id"]]["stage"] != "RECONSTRUCTED" and state["stage"] != "COMPLETE":
                    state["components"][job["component_id"]]["stage"] = "FAILED"
                    project.save(db, state, "native_job_failed", {"job_id": job_id, "status": job["status"]})
        return job

    def outputs(self, project_root, job_id, download=False):
        project, job = self.owned(project_root, job_id)
        job = self.status(project_root, job_id)
        if job["status"] != "completed":
            raise StudioError("Outputs require a confirmed completed job")
        if not download:
            return {"job_id": job_id, "outputs": job.get("outputs", []), "downloaded": bool(job.get("outputs"))}
        if job.get("outputs"):
            for output in job["outputs"]:
                if sha(inside(project.root, output["path"])) != output["sha256"]:
                    raise StudioError("Collected output changed")
            return {"job_id": job_id, "outputs": job["outputs"], "geometry_validation": "NOT_EXECUTED"}
        out_dir = inside(project.root, f".a3d/reconstruction/{job['component_id']}/{job_id}/{uuid.uuid4().hex}", False)
        out_dir.mkdir(parents=True)
        with self.factory(self.config, project.root) as native:
            native.call("fetch_outputs", {"prompt_id": job["prompt_id"], "out_dir": str(out_dir),
                                         "url_only": False, "inline_images": False})
        results = []
        for path in out_dir.rglob("*"):
            if path.is_symlink() or (hasattr(path, "is_junction") and path.is_junction()):
                raise StudioError("Unexpected output link")
            if path.is_file():
                safe = inside(project.root, path.relative_to(project.root).as_posix())
                if safe.suffix.lower() not in (".png", ".jpg", ".jpeg", ".webp", ".glb", ".gltf", ".bin", ".obj", ".mtl", ".ply", ".stl"):
                    raise StudioError("Unexpected asset output extension")
                results.append({"path": safe.relative_to(project.root).as_posix(), "sha256": sha(safe), "bytes": safe.stat().st_size})
        if not results:
            raise StudioError("Native fetch produced no verified local outputs")
        with project.transaction() as db:
            job["outputs"] = results
            project.save_job(db, job)
        return {"job_id": job_id, "outputs": results, "geometry_validation": "NOT_EXECUTED"}

    def cancel(self, project_root, job_id):
        _, job = self.owned(project_root, job_id)
        if job["status"] in ("completed", "failed", "cancelled"):
            return job
        # Current official comfy-cli uses global /interrupt after a queue read.
        return {"job_id": job_id, "status": job["status"], "cancellation": "requires_native_review",
                "reason": "Official job(action=cancel) may interrupt the shared running slot. Review the active native queue before cancelling."}
