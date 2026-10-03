from __future__ import annotations

import copy
import json
import sqlite3
import uuid
from contextlib import contextmanager, closing
from pathlib import Path

from .core import StudioError, atomic_json, canonical, contract, digest, ident, inside, now, read_json, route, sha

STAGES = "INIT SPECIFIED REFERENCES_GENERATING REFERENCES_READY REFERENCES_APPROVED ANALYZED ROUTED PACKAGED RECONSTRUCTING RECONSTRUCTED ASSEMBLING REFINING BEHAVIOR_AUTHORING VALIDATING COMPLETE".split()
ACTIVE_JOBS = {"preparing", "submitting", "submission_unknown", "queued", "running", "unknown", "cancel_requested"}


class Project:
    """SQLite is canonical; project.json is a human-readable snapshot only."""

    def __init__(self, root):
        self.root = Path(root).resolve(strict=True)
        self.data = inside(self.root, ".a3d")
        self.db = inside(self.root, ".a3d/state.sqlite3")

    @classmethod
    def create(cls, root, asset):
        contract("asset", asset)
        ids = [c["id"] for c in asset["components"]]
        if len(set(ids)) != len(ids):
            raise StudioError("Duplicate component id")
        for rel in asset["relationships"]:
            if rel["a"] not in ids or rel["b"] not in ids or rel["a"] == rel["b"]:
                raise StudioError("Relationship endpoints must reference distinct components")
            if rel["must_remain_separate"] and (rel["may_merge"] or rel["type"] == "fused"):
                raise StudioError("Contradictory separation policy")
        root = Path(root).absolute()
        root.mkdir(parents=True, exist_ok=True)
        data = root / ".a3d"
        data.mkdir(exist_ok=False)
        for name in ("source", "references", "annotations", "packages", "reconstruction", "blender", "checkpoints", "decisions", "logs", "outputs", "evidence"):
            (data / name).mkdir()
        state = {"schema_version": 1, "project_id": str(uuid.uuid4()), "asset": asset, "stage": "INIT", "revision": 0,
                 "components": {c["id"]: {"stage": "INIT", "route": {**route(c), "requires_human": True}, "package": None} for c in asset["components"]},
                 "gates": {}, "evidence": {}, "created_at": now(), "updated_at": now()}
        with closing(sqlite3.connect(data / "state.sqlite3")) as db, db:
            db.execute("CREATE TABLE state (id INTEGER PRIMARY KEY CHECK(id=1), doc TEXT NOT NULL)")
            db.execute("CREATE TABLE jobs (id TEXT PRIMARY KEY, request_key TEXT UNIQUE NOT NULL, doc TEXT NOT NULL)")
            db.execute("CREATE TABLE events (id INTEGER PRIMARY KEY, created_at TEXT NOT NULL, kind TEXT NOT NULL, doc TEXT NOT NULL)")
            db.execute("INSERT INTO state VALUES (1, ?)", (canonical(state).decode(),))
        atomic_json(data / "asset.json", asset)
        atomic_json(data / "project.json", state)
        return cls(root)

    @contextmanager
    def transaction(self):
        db = sqlite3.connect(self.db, timeout=5)
        try:
            db.execute("PRAGMA synchronous=FULL")
            db.execute("BEGIN IMMEDIATE")
            yield db
            db.commit()
        except BaseException:
            db.rollback()
            raise
        finally:
            db.close()

    def state(self, db=None):
        if db is not None:
            return json.loads(db.execute("SELECT doc FROM state WHERE id=1").fetchone()[0])
        with closing(sqlite3.connect(self.db)) as conn:
            return self.state(conn)

    def save(self, db, state, kind, detail):
        state["revision"] += 1
        state["updated_at"] = now()
        db.execute("UPDATE state SET doc=? WHERE id=1", (canonical(state).decode(),))
        db.execute("INSERT INTO events(created_at,kind,doc) VALUES (?,?,?)", (now(), kind, canonical(detail).decode()))

    def snapshot(self):
        with self.transaction() as db:
            state = self.state(db)
            atomic_json(self.data / "project.json", state)
        return state

    def evidence(self, key, path):
        ident(key)
        file = inside(self.root, path)
        if not file.is_file():
            raise StudioError("Evidence must be a file")
        rec = {"path": path, "sha256": sha(file), "recorded_at": now()}
        with self.transaction() as db:
            s = self.state(db)
            if s["stage"] == "COMPLETE":
                raise StudioError("Completed project is immutable; create a new revision project")
            s["evidence"][key] = rec
            self.save(db, s, "evidence", {"key": key, **rec})
        return rec

    def verify_evidence(self, state, key):
        rec = state["evidence"].get(key)
        if not rec or sha(inside(self.root, rec["path"])) != rec["sha256"]:
            raise StudioError(f"Missing or changed evidence: {key}")
        return rec

    def gate(self, name, approved, user_statement, evidence_keys, source_ref):
        ident(name)
        if not user_statement.strip() or not source_ref.strip() or not evidence_keys:
            raise StudioError("Human gate requires actual user statement, message reference and reviewed evidence")
        with self.transaction() as db:
            s = self.state(db)
            if s["stage"] == "COMPLETE":
                raise StudioError("Completed project is immutable")
            evidence = {k: copy.deepcopy(self.verify_evidence(s, k)) for k in evidence_keys}
            rec = {"decision_id": str(uuid.uuid4()), "source": "human", "source_ref": source_ref, "statement": user_statement,
                   "approved": bool(approved), "evidence": evidence, "timestamp": now()}
            s["gates"][name] = rec
            self.save(db, s, "human_decision", {"name": name, **rec})
        return rec

    def require_gate(self, state, name):
        gate = state["gates"].get(name, {})
        if gate.get("approved") is not True:
            raise StudioError(f"Human review pending: {name}")
        for key, rec in gate["evidence"].items():
            if self.verify_evidence(state, key) != rec:
                raise StudioError(f"Human review stale: {name}")

    def resolve_route(self, component_id, selected):
        with self.transaction() as db:
            s = self.state(db)
            c = s["components"][component_id]
            if selected not in ("PATTERN_SEWN", "MULTIVIEW_PART") or c["package"]:
                raise StudioError("Route invalid or package already bound")
            self.require_gate(s, "route." + component_id)
            proposal_rec = self.verify_evidence(s, "pipeline-proposal")
            proposal = read_json(inside(self.root, proposal_rec["path"]))
            if s["stage"] != "ANALYZED" or "pipeline-proposal" not in s["gates"]["route." + component_id]["evidence"] or proposal["components"][component_id]["selected"] != selected:
                raise StudioError("Resolve only the exact reviewed pipeline proposal at ANALYZED")
            c["route"].update(selected=selected, requires_human=False, human_decision=s["gates"]["route." + component_id]["decision_id"])
            self.save(db, s, "route_resolved", {"component": component_id, "selected": selected})
        return c["route"]

    def bind_package(self, component_id, package_path):
        from .packages import inspect_package
        from .planning import require_route
        path = inside(self.root, package_path)
        manifest = inspect_package(path)
        with self.transaction() as db:
            s = self.state(db)
            c = s["components"][component_id]
            if s["stage"] not in ("ROUTED", "PACKAGED"):
                raise StudioError("Package binding requires reviewed ROUTED/PACKAGED stage")
            require_route(self, s, component_id)
            if s["stage"] == "COMPLETE" or c["stage"] not in ("INIT", "ROUTED", "PACKAGED", "FAILED", "BLOCKED"):
                raise StudioError("Cannot replace package during reconstruction or after completion")
            if manifest["component_id"] != component_id or manifest["asset_id"] != s["asset"]["id"]:
                raise StudioError("Package identity mismatch")
            if c["route"]["requires_human"] or manifest["pipeline"] != c["route"]["selected"]:
                raise StudioError("Unresolved or mismatched route")
            c.update(package={"path": package_path, "sha256": sha(path), "manifest": manifest}, stage="PACKAGED")
            self.save(db, s, "package_bound", {"component": component_id, "sha256": sha(path)})
        return c

    def ready(self, component_id, db=None):
        from .packages import inspect_package
        from .planning import require_board
        s = self.state(db)
        if s["stage"] not in ("RECONSTRUCTING", "RECONSTRUCTED", "ASSEMBLING", "REFINING", "BEHAVIOR_AUTHORING", "VALIDATING"):
            raise StudioError("Project is not admitted for reconstruction")
        require_board(self, s)
        self.require_gate(s, "references")
        c = s["components"][component_id]
        if c["route"]["requires_human"] or c["package"] is None:
            raise StudioError("Component route/package not ready")
        package = inside(self.root, c["package"]["path"])
        if sha(package) != c["package"]["sha256"]:
            raise StudioError("Bound package changed")
        inspect_package(package)
        return s, c

    def transition(self, stage, evidence_key=None):
        with self.transaction() as db:
            s = self.state(db)
            old = s["stage"]
            from .lifecycle import no_pending_operation
            if stage not in ("BLOCKED", "FAILED"):
                no_pending_operation(s)
            if old == "COMPLETE":
                raise StudioError("Completed project is immutable")
            if stage in ("BLOCKED", "FAILED"):
                if evidence_key is None:
                    raise StudioError("A failure/block requires evidence")
                self.verify_evidence(s, evidence_key)
                if old not in ("BLOCKED", "FAILED"):
                    s["resume_stage"] = old
            elif old in ("BLOCKED", "FAILED"):
                if stage != s.get("resume_stage"):
                    raise StudioError("Resume only at last active stage")
                s.pop("resume_stage", None)
            else:
                next_index = STAGES.index(old) + 1
                allowed = {STAGES[next_index]} if next_index < len(STAGES) else set()
                if old == "SPECIFIED":
                    allowed.add("REFERENCES_READY")
                if stage not in allowed:
                    raise StudioError(f"Illegal transition {old} -> {stage}")
            if stage not in ("INIT", "BLOCKED", "FAILED"):
                if evidence_key is None:
                    raise StudioError("Each transition requires saved evidence")
                self.verify_evidence(s, evidence_key)
            if stage == "REFERENCES_APPROVED":
                self.require_gate(s, "references")
            if stage == "ROUTED":
                from .planning import require_route
                for cid in s["components"]:
                    require_route(self, s, cid)
            if stage == "PACKAGED" and any(not c["package"] for c in s["components"].values()):
                raise StudioError("Missing packages")
            if stage in STAGES[STAGES.index("RECONSTRUCTING"):]:
                from .planning import require_board
                require_board(self, s)
            if stage == "RECONSTRUCTED" and any(c["stage"] != "RECONSTRUCTED" for c in s["components"].values()):
                raise StudioError("Some components have no validated reconstruction")
            if stage == "RECONSTRUCTED":
                from .lifecycle import reconstruction
                for cid in s["components"]:
                    reconstruction(self, s, cid)
            if stage == "ASSEMBLING":
                from .lifecycle import assembly_plan
                assembly_plan(self, s)
            if stage == "REFINING":
                from .lifecycle import assembly_result
                assembly_result(self, s)
            if stage == "BEHAVIOR_AUTHORING":
                from .lifecycle import silhouette, stage_validation
                stage_validation(self, s, "refinement-validation", "REFINING", {"geometry", "scale", "orientation", "separation"})
                silhouette(self, s, current_scene=True)
            if stage == "VALIDATING":
                from .lifecycle import required_final_checks, stage_validation
                checks = required_final_checks(s) & {"rig", "weighting", "clearance"}
                if checks:
                    stage_validation(self, s, "behavior-validation", "BEHAVIOR_AUTHORING", checks)
            if stage == "COMPLETE":
                from .lifecycle import final_validation, assembly_result
                assembly_result(self, s)
                final_validation(self, s)
                if any(j["status"] in ACTIVE_JOBS for j in self.jobs(db)):
                    raise StudioError("Jobs still active or unknown")
            s["stage"] = stage
            self.save(db, s, "transition", {"from": old, "to": stage, "evidence": evidence_key})
        return self.snapshot()

    def accept_reconstruction(self, component_id, evidence_key):
        with self.transaction() as db:
            s, c = self.ready(component_id, db)
            from .lifecycle import no_pending_operation, verify_checks, visual_review
            no_pending_operation(s)
            if s["stage"] != "RECONSTRUCTING" or c["stage"] == "RECONSTRUCTED":
                raise StudioError("Accept reconstruction only once during RECONSTRUCTING; later changes require a new revision")
            rec = self.verify_evidence(s, evidence_key)
            report = contract("reconstruction", read_json(inside(self.root, rec["path"])))
            if report["component_id"] != component_id or report["package_sha256"] != c["package"]["sha256"]:
                raise StudioError("Reconstruction report identity mismatch")
            verify_checks(self, report, {"scale", "orientation", "anchors", "identity", "separation", "geometry"})
            if sha(inside(self.root, report["artifact"]["path"])) != report["artifact"]["sha256"]:
                raise StudioError("Reconstruction output changed")
            visual_review(self, s, report["visual_review_evidence"], "reconstruction", [report["artifact"]])
            c.update(stage="RECONSTRUCTED", reconstruction=report, reconstruction_evidence={"key": evidence_key, "record": rec})
            self.save(db, s, "reconstruction_accepted", {"component": component_id, "evidence": rec})
        return c

    def jobs(self, db=None):
        if db is not None:
            return [json.loads(r[0]) for r in db.execute("SELECT doc FROM jobs ORDER BY rowid")]
        with closing(sqlite3.connect(self.db)) as conn:
            return self.jobs(conn)

    def job(self, job_id, db=None):
        matches = [j for j in self.jobs(db) if j["job_id"] == job_id]
        if not matches:
            raise StudioError("Job is not owned by this project")
        return matches[0]

    def save_job(self, db, job):
        job["updated_at"] = now()
        db.execute("INSERT INTO jobs(id,request_key,doc) VALUES (?,?,?) ON CONFLICT(id) DO UPDATE SET doc=excluded.doc", (job["job_id"], job["request_key"], canonical(job).decode()))

    def summary(self):
        s = self.state()
        from .piece_inventory import cached_status
        return {"project_id": s["project_id"], "asset_id": s["asset"]["id"], "stage": s["stage"],
                "components": {k: v["stage"] for k, v in s["components"].items()},
                "jobs": [{k: j.get(k) for k in ("job_id", "prompt_id", "component_id", "status")} for j in self.jobs()],
                "pending_routes": [k for k, v in s["components"].items() if v["route"]["requires_human"]],
                "pending_blender_operation": s.get("pending_blender_operation"),
                "construction_review": "RECORDED_RECHECK_REQUIRED" if s["gates"].get("construction", {}).get("approved") else "PENDING",
                "pipeline_proposal": s["evidence"].get("pipeline-proposal"),
                "construction_board": s["evidence"].get("construction-board"),
                "piece_completeness": cached_status(self)}
