import shutil
from a3d.core import ROOT, atomic_json, contract, read_json, route, sha
from a3d.packages import build_package, extract_package
from a3d.store import Project
from tests.support import PROVENANCE, ready_project
from tests.test_core import Case

class FixtureTests(Case):
    def test_package_allows_different_source_seam_sampling(self):
        import xml.etree.ElementTree as ET
        source=self.root/'source'
        shutil.copytree(ROOT/'tests/fixtures/garment-coat/package',source)
        data=read_json(source/'garment.json');panel=data['pieces']['front']
        panel['vertices'].insert(2,[20,20]);panel['faces']=[[0,1,2],[0,2,3],[0,3,4]]
        panel['edges']={'left':[0,4],'right':[1,2,3],'top':[4,3]}
        atomic_json(source/'garment.json',data)
        tree=ET.parse(source/'pattern.svg')
        polygon=next(e for e in tree.getroot().iter() if e.get('id')=='front')
        polygon.set('points',' '.join(','.join(map(str,p)) for p in panel['vertices']))
        tree.write(source/'pattern.svg',encoding='utf-8')
        build_package(source,self.root/'unequal.garmentpkg','test.coat','garment.coat','PATTERN_SEWN',PROVENANCE)
        extract_package(self.root/'unequal.garmentpkg',self.root/'extracted')
        self.assertEqual(read_json(self.root/'extracted/garment.json'),data)

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
