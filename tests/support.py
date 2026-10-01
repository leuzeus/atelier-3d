import copy
import json
import struct
import zlib
from pathlib import Path

from a3d.core import ROOT, atomic_json, now, sha, read_json
from a3d.packages import build_package
from a3d.store import Project

def png(width=64, height=128):
    def chunk(tag, data):
        return struct.pack(">I", len(data))+tag+data+struct.pack(">I", zlib.crc32(tag+data)&0xffffffff)
    rows=b"".join(b"\0"+bytes([220,220,220])*width for _ in range(height))
    return b"\x89PNG\r\n\x1a\n"+chunk(b"IHDR",struct.pack(">IIBBBBB",width,height,8,2,0,0,0))+chunk(b"IDAT",zlib.compress(rows))+chunk(b"IEND",b"")

def asset(garment=False):
    cid="garment.coat" if garment else "body.skull"
    return {"id":"test-character","name":"Synthetic contract fixture","target":"animation","height_cm":180,"units":"cm",
      "components":[{"id":cid,"type":"garment" if garment else "anatomy",
        "features":{"sheet_like":garment,"sewn":garment,"rigid":not garment,"articulated":not garment,"hidden_structure":False},
        "evidence":["fixture-source"],"independent_geometry":True}], "relationships":[]}

def part_source(root, cid="body.skull"):
    root=Path(root); root.mkdir(parents=True,exist_ok=True)
    views={}
    for view,axis in (("front",[0,-1,0]),("left",[-1,0,0])):
        path=root/f"{view}.clean.png"; path.write_bytes(png())
        views[view]={"path":path.name,"role":"clean","dimensions":[64,128],
            "camera":{"projection":"orthographic","view":view,"axis":axis,"up":[0,0,1],"height_cm":24}}
    part={"component_id":cid,"required_views":["front","left"],"views":views,"anchors":{"neck":[0,0,0]},
          "relationships":[],"topology_target":"animation"}
    atomic_json(root/"part.json",part)
    return part

def garment_source(root):
    root=Path(root); root.mkdir(parents=True,exist_ok=True)
    pieces={}
    polygons=[]
    # Front/back torso plus two sleeves, an actual seam topology fixture.
    for pid,position in (("front",[0,-15,80]),("back",[0,15,80]),("sleeve-left",[-25,0,100]),("sleeve-right",[25,0,100])):
        verts=[[0,0],[20,0],[20,40],[0,40]]
        pieces[pid]={"vertices":verts,"faces":[[0,1,2],[0,2,3]],"edges":{"left":[0,3],"right":[1,2],"top":[3,2]},
                     "position_cm":position,"rotation_degrees":[90,0,0]}
        polygons.append(f'<polygon id="{pid}" points="0,0 20,0 20,40 0,40"/>')
    data={"component_id":"garment.coat","units":"cm","pieces":pieces,"seams":[
      {"id":"torso-right","piece_a":"front","edge_a":"right","piece_b":"back","edge_b":"left","orientation":"reverse"},
      {"id":"sleeve-left","piece_a":"front","edge_a":"left","piece_b":"sleeve-left","edge_b":"right","orientation":"forward"},
      {"id":"sleeve-right","piece_a":"back","edge_a":"right","piece_b":"sleeve-right","edge_b":"left","orientation":"forward"}],
      "material":{"mass_kg":0.3,"tension_stiffness":15,"compression_stiffness":15,"shear_stiffness":5,"bending_stiffness":0.5}}
    atomic_json(root/"garment.json",data)
    (root/"pattern.svg").write_text('<svg xmlns="http://www.w3.org/2000/svg" width="20cm" height="40cm" viewBox="0 0 20 40">'+''.join(polygons)+'</svg>')
    return data

PROVENANCE={"source":"synthetic-test","created_by":"test-suite","notes":"Contract fixture only; no artistic or production qualification."}

def construction_dossier(project, garment=False):
    cid = "garment.coat" if garment else "body.skull"
    image = project.data / "evidence/synthetic-board.png"
    image.write_bytes(png())
    view = {"path": image.relative_to(project.root).as_posix(), "basis": "inferred-design", "notes": "SYNTHETIC contract image only, never a production reference", "source_evidence_keys": ["reference.original"]}
    pieces = [{"id": pid, "label": "Synthetic " + pid, "material": "test cotton", "dimensions_cm": [20, 40],
        "basis": "inferred", "construction": "Synthetic contract fixture only", "grain_direction": [0, 1], "seam_allowance_cm": 0,
        "source_evidence_keys": ["reference.original"], "reference_notes": "Synthetic rectangular silhouette fixture, not an analysis of a real garment"}
        for pid in (["front", "back", "sleeve-left", "sleeve-right"] if garment else [cid])]
    for p in pieces:
        p["characteristics"] = ["Synthetic contract piece; no production fitting"]
        if garment:
            p["seam_allowance_cm"] = 1
            p["pattern"] = {"cut_quantity": 1, "cut_instruction": "Synthetic one piece only", "cut_outline_cm": [[-1,-1],[21,-1],[21,41],[-1,41]],
                "folds": [{"id":"F1","label":"Pli milieu","kind":"fold","line_cm":[[10,0],[10,40]]}] if p["id"]=="front" else [],
                "fold_notes": "Synthetic center fold" if p["id"]=="front" else "No fold on this synthetic piece", "assembly_marks":[], "mark_notes":"Synthetic paired sewing notches"}
    if garment:
        data = read_json(project.data / "source/package/garment.json")
        by_id={p["id"]:p for p in pieces}
        for i,seam in enumerate(data["seams"],1):
            for side in ("a","b"):
                position=0.7 if side=="b" and seam["orientation"]=="reverse" else 0.3
                by_id[seam["piece_"+side]]["pattern"]["assembly_marks"].append({"id": "R"+str(i), "seam_id":seam["id"], "position":position, "symbol":"notch"})
    return {"schema_version": 1, "asset_id": "test-character", "title": "SYNTHETIC TEST ONLY - not a usable cutting plan", "units": "cm", "target": "animation", "height_cm": 180,
        "orthographic": {k: dict(view,subject_bbox_px=[0,0,64,128],subject_height_cm=160) for k in ("front", "side", "back")},
        "exploded": dict(view,annotations=[{"component_id":cid,"piece_id":p["id"],"anchor_px":[10+i*12,50],"label_position_px":[3,80+i*12]} for i,p in enumerate(pieces)]),
        "proportion_checks": [{"label":"Synthetic width/height "+v,"source_evidence_key":"reference.original","view":v,
            "reference_spans_px":[[[0,0],[40,0]],[[0,0],[0,100]]],"view_spans_px":[[[0,0],[40,0]],[[0,0],[0,100]]],"tolerance_relative":0.05} for v in ("front","side","back","exploded")],
        "source_references": [{"evidence_key": "reference.original", "source_ref": "test:original-image-fixture"}],
        "components": {cid: {"pipeline": "PATTERN_SEWN" if garment else "MULTIVIEW_PART", "assembly_notes": "Synthetic test assembly", "pieces": pieces}},
        "body_measurements": ["Synthetic height 180 cm; no real fitting"], "assumptions": ["Synthetic data"], "unresolved_blockers": [],
        "silhouette_checks": ["Compare sleeve and wrist width against reference"], "mobility_checks": ["Run and raised arm poses"], "delivery_requirements": ["Synthetic contract test only"]}


def ready_project(root, garment=False, approve_board=True):
    project=Project.create(root,asset(garment))
    ev=project.data/"evidence"/"brief.json"; atomic_json(ev,{"brief":"synthetic"})
    project.evidence("brief",".a3d/evidence/brief.json")
    project.transition("SPECIFIED","brief"); project.transition("REFERENCES_READY","brief")
    source=project.data/"source"/"package"
    if garment: garment_source(source)
    else: part_source(source)
    (project.data / "source/original.png").write_bytes(png())
    project.evidence("reference.original", ".a3d/source/original.png")
    keys=["brief", "reference.original"]
    for name in ("front","left") if not garment else ():
        rel=f".a3d/source/package/{name}.clean.png"; key=f"reference.{name}"
        project.evidence(key,rel); keys.append(key)
    project.gate("references",True,"Approve synthetic test references",keys,"test:user-message")
    project.transition("REFERENCES_APPROVED","brief"); project.transition("ANALYZED","brief")
    cid="garment.coat" if garment else "body.skull"
    from a3d.planning import propose, build_board
    propose(project)
    project.gate("route." + cid, True, "Approve synthetic route", ["pipeline-proposal"], "test:route-message")
    project.resolve_route(cid, "PATTERN_SEWN" if garment else "MULTIVIEW_PART")
    project.transition("ROUTED", "brief")
    suffix=".garmentpkg" if garment else ".partpkg"
    path=project.data/"packages"/("component"+suffix)
    build_package(source,path,asset(garment)["id"],cid,"PATTERN_SEWN" if garment else "MULTIVIEW_PART",PROVENANCE)
    project.bind_package(cid,path.relative_to(project.root).as_posix())
    project.transition("PACKAGED","brief")
    dossier = construction_dossier(project, garment)
    prepare_synthetic_exploded(project, dossier)
    build_board(project, ".a3d/evidence/construction.json")
    if approve_board:
        project.gate("construction", True, "Approve the synthetic test cutting board only", ["construction-board"], "test:cutting-message")
        project.transition("RECONSTRUCTING","brief")
    return project


def prepare_synthetic_exploded(project, dossier):
    """Test-only provider fixture; NEVER a real Codex Image execution claim."""
    from a3d.board_contract import prepare_exploded, register_exploded
    atomic_json(project.data / "evidence/construction.json", dossier)
    prepare_exploded(project, ".a3d/evidence/construction.json")
    register_exploded(project, dossier["exploded"]["path"], "test:synthetic-provider-fixture-NOT-A-REAL-IMAGEGEN-CALL")
    dossier["exploded"]["generation_evidence_key"]="exploded-image-generation"
    atomic_json(project.data / "evidence/construction.json", dossier)
    return dossier


class FakeNative:
    def __init__(self):
        self.calls=[]; self.queue=[]; self.valid=True; self.status="completed"; self.fail_submit=False; self.receipt={}
        self.names={"server_info","validate_workflow","upload_file","run_workflow","job","fetch_outputs"}
    def __call__(self, config, project_root=None):
        return self
    def __enter__(self): return self
    def __exit__(self,*args): pass
    def call(self,name,args=None):
        args=args or {}; self.calls.append((name,args))
        if name=="server_info": return {"running":True}
        if name=="validate_workflow": return {"valid":self.valid,"errors":[]}
        if name=="upload_file": return {"uploads":[{"cloud_name":Path(args["paths"][0]).name}]}
        if name=="run_workflow":
            if self.fail_submit: raise TimeoutError("synthetic after dispatch")
            return {"prompt_id":"native-prompt-1"}
        if name=="job" and args.get("action")=="queue": return {"jobs":self.queue}
        if name=="job": return {"prompt_id":args["prompt_id"],"status":self.status}
        if name=="fetch_outputs":
            (Path(args["out_dir"])/"mesh.glb").write_bytes(b"synthetic-fixture-not-a-real-glb")
            return {"files":["mesh.glb"]}
        raise AssertionError(name)
