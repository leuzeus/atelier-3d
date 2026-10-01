import shutil
from a3d.core import ROOT, atomic_json, contract, read_json, route, sha
from a3d.packages import build_package, extract_package
from a3d.store import Project
from tests.support import PROVENANCE, ready_project
from tests.test_core import Case

class FixtureTests(Case):
    def test_garment_contract_fixture_roundtrip(self):
        source=ROOT/"tests/fixtures/garment-coat"
        data=contract("asset",read_json(source/"asset.json"))
        self.assertEqual(route(data["components"][0])["selected"],"PATTERN_SEWN")
        path=self.root/"coat.garmentpkg"
        build_package(source/"package",path,data["id"],"garment.coat","PATTERN_SEWN",PROVENANCE)
        manifest=extract_package(path,self.root/"extracted")
        self.assertEqual(manifest["component_id"],"garment.coat")

    def test_skeleton_contract_fixture_keeps_parts_independent(self):
        source=ROOT/"tests/fixtures/articulated-skeleton"
        data=contract("asset",read_json(source/"asset.json"))
        project=Project.create(self.root,data)
        self.assertEqual(len(project.state()["components"]),3)
        atomic_json(project.data / "evidence/brief.json", {"synthetic": True})
        project.evidence("brief", ".a3d/evidence/brief.json")
        for stage in ("SPECIFIED", "REFERENCES_READY"):
            project.transition(stage, "brief")
        project.gate("references", True, "Approve synthetic fixture references", ["brief"], "test:fixture")
        for stage in ("REFERENCES_APPROVED", "ANALYZED"):
            project.transition(stage, "brief")
        from a3d.planning import propose
        propose(project)
        for cid in project.state()["components"]:
            project.gate("route." + cid, True, "Approve synthetic part routes", ["pipeline-proposal"], "test:route")
            project.resolve_route(cid, "MULTIVIEW_PART")
        project.transition("ROUTED", "brief")
        for component in data["components"]:
            cid=component["id"]
            self.assertEqual(route(component)["selected"],"MULTIVIEW_PART")
            dest=project.data/"packages"/(cid+".partpkg")
            build_package(source/"packages"/cid,dest,data["id"],cid,"MULTIVIEW_PART",PROVENANCE)
            project.bind_package(cid,dest.relative_to(project.root).as_posix())
        self.assertTrue(all(c["package"] for c in project.state()["components"].values()))
        self.assertTrue(all(r["must_remain_separate"] for r in data["relationships"]))

    def test_synthetic_state_lifecycle_reaches_complete_only_with_evidence(self):
        from tests.lifecycle_support import final_ready
        project=ready_project(self.root)
        final_ready(project)
        self.assertEqual(project.transition("COMPLETE","final-validation")["stage"],"COMPLETE")
