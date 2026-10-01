import copy
import importlib.util
import json
import sqlite3
import tempfile
import unittest
import zipfile
from pathlib import Path

from a3d.core import ROOT, StudioError, atomic_json, contract, inside, read_json, relative, route, sha, validate
from a3d.packages import build_package, extract_package, inspect_package
from a3d.store import Project
from tests.support import asset, garment_source, part_source, PROVENANCE, ready_project


class Case(unittest.TestCase):
    def setUp(self):
        (ROOT/"work/test-runs").mkdir(parents=True,exist_ok=True)
        self.temp=tempfile.TemporaryDirectory(dir=ROOT/"work/test-runs")
        self.root=Path(self.temp.name)
    def tearDown(self): self.temp.cleanup()


class ContractTests(Case):
    def test_component_routes_are_independent(self):
        self.assertEqual(route(asset()["components"][0])["selected"],"MULTIVIEW_PART")
        self.assertEqual(route(asset(True)["components"][0])["selected"],"PATTERN_SEWN")

    def test_ambiguous_route_requires_human(self):
        c=asset()["components"][0]; c["features"]["sheet_like"]=True
        self.assertTrue(route(c)["requires_human"]); self.assertIsNone(route(c)["selected"])

    def test_missing_evidence_requires_review(self):
        c=asset()["components"][0]; c["evidence"]=[]
        self.assertTrue(route(c)["requires_human"])

    def test_invalid_component_rejected(self):
        c=asset()["components"][0]; c["features"]["rigid"]="yes"
        with self.assertRaises(StudioError): route(c)

    def test_paths_reject_cross_platform_escape(self):
        for value in ("../secret","a/../../x","C:/x","/tmp/x","a\\b","a//b","a/./b","aux.txt","file:stream"):
            with self.subTest(value=value), self.assertRaises(StudioError): relative(value)

    def test_new_output_remains_scoped(self):
        self.assertEqual(inside(self.root,"a/b.json",False),self.root/"a/b.json")

    def test_unknown_schema_keyword_fails_closed(self):
        with self.assertRaises(StudioError): validate({},{"surprise":True})

    def test_duplicate_component_ids(self):
        a=asset(); a["components"].append(copy.deepcopy(a["components"][0]))
        with self.assertRaises(StudioError): Project.create(self.root,a)

    def test_relationship_contradiction(self):
        a=asset(); c=copy.deepcopy(a["components"][0]); c["id"]="body.jaw"; a["components"].append(c)
        a["relationships"]=[{"a":"body.skull","b":"body.jaw","type":"hinged","must_remain_separate":True,"may_merge":True,"requires_clearance_in_reference":True}]
        with self.assertRaises(StudioError): Project.create(self.root,a)


class PackageTests(Case):
    def package(self,garment=False):
        source=self.root/"source"; source.mkdir()
        garment_source(source) if garment else part_source(source)
        dest=self.root/("coat.garmentpkg" if garment else "head.partpkg")
        build_package(source,dest,"test-character","garment.coat" if garment else "body.skull",
                      "PATTERN_SEWN" if garment else "MULTIVIEW_PART",PROVENANCE)
        return source,dest

    def test_part_roundtrip_and_identity(self):
        source,dest=self.package()
        manifest=extract_package(dest,self.root/"extracted")
        self.assertEqual(manifest["component_id"],"body.skull")
        self.assertEqual(sha(source/"front.clean.png"),sha(self.root/"extracted/front.clean.png"))

    def test_garment_fixture_seams(self):
        _,dest=self.package(True)
        self.assertEqual(inspect_package(dest)["pipeline"],"PATTERN_SEWN")

    def test_no_archive_overwrite(self):
        src,dest=self.package()
        with self.assertRaises(StudioError): build_package(src,dest,"test-character","body.skull","MULTIVIEW_PART",PROVENANCE)

    def test_no_extract_overwrite(self):
        _,dest=self.package(); (self.root/"existing").mkdir()
        with self.assertRaises(StudioError): extract_package(dest,self.root/"existing")

    def test_changed_payload_detected(self):
        _,dest=self.package(); modified=self.root/"bad.partpkg"
        with zipfile.ZipFile(dest) as src,zipfile.ZipFile(modified,"w") as out:
            for name in src.namelist(): out.writestr(name,b"changed" if name=="front.clean.png" else src.read(name))
        with self.assertRaises(StudioError): inspect_package(modified)

    def test_zip_traversal_rejected_before_extraction(self):
        _,dest=self.package()
        with zipfile.ZipFile(dest,"a") as out: out.writestr("../outside.txt",b"bad")
        with self.assertRaises(StudioError): extract_package(dest,self.root/"extract")
        self.assertFalse((self.root/"outside.txt").exists())

    def test_mask_cannot_be_clean_view(self):
        source=self.root/"source"; part=part_source(source); part["views"]["front"]["role"]="mask"
        atomic_json(source/"part.json",part)
        with self.assertRaises(StudioError):
            build_package(source,self.root/"bad.partpkg","test-character","body.skull","MULTIVIEW_PART",PROVENANCE)

    def test_missing_view_detected(self):
        source=self.root/"source"; part=part_source(source); del part["views"]["left"]
        atomic_json(source/"part.json",part)
        with self.assertRaises(StudioError):
            build_package(source,self.root/"bad.partpkg","test-character","body.skull","MULTIVIEW_PART",PROVENANCE)

    def test_svg_must_match_geometry(self):
        source=self.root/"source"; garment_source(source)
        svg=(source/"pattern.svg").read_text().replace("20,40","21,40"); (source/"pattern.svg").write_text(svg)
        with self.assertRaises(StudioError):
            build_package(source,self.root/"bad.garmentpkg","test-character","garment.coat","PATTERN_SEWN",PROVENANCE)

    def test_dangling_seam_detected(self):
        source=self.root/"source"; data=garment_source(source); data["seams"][0]["edge_a"]="missing"
        atomic_json(source/"garment.json",data)
        with self.assertRaises(StudioError):
            build_package(source,self.root/"bad.garmentpkg","test-character","garment.coat","PATTERN_SEWN",PROVENANCE)


class StateTests(Case):
    def test_reopen_reads_canonical_database(self):
        p=ready_project(self.root)
        atomic_json(p.data/"project.json",{"stage":"COMPLETE"})
        self.assertEqual(Project(self.root).state()["stage"],"RECONSTRUCTING")

    def test_project_creation_never_overwrites(self):
        Project.create(self.root,asset())
        with self.assertRaises(FileExistsError): Project.create(self.root,asset())

    def test_illegal_transition(self):
        p=Project.create(self.root,asset())
        with self.assertRaises(StudioError): p.transition("COMPLETE")

    def test_stale_human_gate(self):
        p=ready_project(self.root); (p.data/"evidence/brief.json").write_text("changed")
        with self.assertRaises(StudioError): p.ready("body.skull")

    def test_changed_bound_archive(self):
        p=ready_project(self.root)
        with (p.data/"packages/component.partpkg").open("ab") as out: out.write(b"x")
        with self.assertRaises(StudioError): p.ready("body.skull")

    def test_block_resume_only_same_stage(self):
        p=ready_project(self.root); p.transition("BLOCKED","brief")
        with self.assertRaises(StudioError): p.transition("ASSEMBLING","brief")
        self.assertEqual(p.transition("RECONSTRUCTING","brief")["stage"],"RECONSTRUCTING")

    def test_unexecuted_reconstruction_not_accepted(self):
        from tests.lifecycle_support import reconstruction_report, evidence
        p=ready_project(self.root)
        report = reconstruction_report(p)
        report["checks"]["geometry"] = "NOT_EXECUTED"
        evidence(p, "reconstruction", report)
        with self.assertRaisesRegex(StudioError, "Required checks"):
            p.accept_reconstruction("body.skull", "reconstruction")

    def test_final_profile_requires_rig_and_exact_files(self):
        from tests.lifecycle_support import final_ready, evidence
        p=ready_project(self.root)
        report = final_ready(p)
        report["checks"].pop("rig")
        report["check_evidence"].pop("rig")
        evidence(p, "final-validation", report)
        p.gate("final", True, "Synthetic incomplete approval", ["final-validation", "final-review"], "test:incomplete")
        with self.assertRaisesRegex(StudioError, "Required checks"):
            p.transition("COMPLETE", "brief")
        report["checks"]["rig"] = "PASS"
        report["check_evidence"]["rig"] = report["check_evidence"]["geometry"]
        evidence(p, "final-validation", report)
        p.gate("final", True, "Synthetic revised approval", ["final-validation", "final-review"], "test:revised")
        (p.root / report["artifacts"][0]["path"]).write_bytes(b"changed")
        with self.assertRaisesRegex(StudioError, "changed artifact"):
            p.transition("COMPLETE", "brief")
