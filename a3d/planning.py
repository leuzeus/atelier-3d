"""Reviewable construction plans and data-derived boards; never invent image analysis.

The agent supplies observed/inferred design data. SVG is the portable, lossless
image output. Pattern contours are read from the exact validated packages.
"""
from __future__ import annotations

import base64
import html
import json
import math
import uuid
import zipfile
from pathlib import Path

from .core import StudioError, atomic_json, contract, inside, read_json, route, sha
from .packages import inspect_package, png_dimensions

PIPELINES = ("PATTERN_SEWN", "MULTIVIEW_PART")


def propose(project, choices=None):
    choices = choices or {}
    state = project.state()
    if state["stage"] != "ANALYZED" or any(c["package"] for c in state["components"].values()):
        raise StudioError("Propose the pipeline at ANALYZED, before binding packages; later changes need a new revision project")
    if set(choices) - state["components"].keys():
        raise StudioError("Unknown component in pipeline proposal")
    components = {}
    for component in state["asset"]["components"]:
        cid = component["id"]
        recommendation = route(component)
        choice = choices.get(cid, {})
        selected = choice.get("selected", recommendation["selected"])
        reason = choice.get("reason", "")
        if selected not in PIPELINES:
            raise StudioError(f"Ambiguous route for {cid}: supply a proposed choice and reason, then ask for review")
        if (selected != recommendation["selected"] or recommendation["requires_human"]) and not reason.strip():
            raise StudioError(f"Explain the proposed route/alternative for {cid}")
        components[cid] = {"selected": selected, "recommendation": recommendation,
            "reason": reason or ", ".join(recommendation["reasons"]),
            "deliverables": (["orthographic views", "exploded garment", "polygon patterns in cm", "piece materials and measurements", "explicit seam graph", "human-reviewed three-part board", "sewn panels and drape validation"]
                if selected == "PATTERN_SEWN" else ["clean orthographic views", "independent part breakdown", "dimensions and anchors", "human-reviewed construction board", "per-part reconstruction and validation"])}
    proposal = {"schema_version": 1, "asset_id": state["asset"]["id"], "components": components,
        "status": "PROPOSED_NOT_APPROVED", "backend_qualification": "NOT_EXECUTED",
        "sequence": ["propose and review routes", "prepare exact component packages and technical dossier", "produce construction board", "human approves the board and cutting", "reconstruct using the reviewed packages", "validate silhouette before rig, LODs and export"],
        "limitations": "A route recommendation is not backend availability or human approval. No silent procedural substitute."}
    path = f".a3d/decisions/pipeline-{uuid.uuid4().hex}.json"
    atomic_json(inside(project.root, path, False), proposal)
    project.evidence("pipeline-proposal", path)
    return {"path": path, "evidence_key": "pipeline-proposal", "proposal": proposal,
        "next": "Present the proposal; record actual route.<component_id> decisions binding pipeline-proposal, then resolve each route."}


def require_route(project, state, cid):
    project.require_gate(state, "references")
    rec = project.verify_evidence(state, "pipeline-proposal")
    proposal = read_json(inside(project.root, rec["path"]))
    component = state["components"][cid]
    gate_name = "route." + cid
    project.require_gate(state, gate_name)
    if "pipeline-proposal" not in state["gates"][gate_name]["evidence"]:
        raise StudioError(f"{gate_name} must review the exact pipeline-proposal")
    if proposal["asset_id"] != state["asset"]["id"] or proposal["components"][cid]["selected"] != component["route"]["selected"]:
        raise StudioError("Selected route differs from the reviewed proposal")
    if component["route"].get("requires_human") or component["route"].get("human_decision") != state["gates"][gate_name]["decision_id"]:
        raise StudioError(f"Resolve the reviewed route for {cid}")


def package_records(project, state):
    records = {}
    for cid, component in state["components"].items():
        require_route(project, state, cid)
        record = component.get("package")
        if not record:
            raise StudioError(f"Missing package: {cid}")
        path = inside(project.root, record["path"])
        if sha(path) != record["sha256"]:
            raise StudioError(f"Bound package changed: {cid}")
        manifest = inspect_package(path)
        if manifest != record["manifest"] or manifest["pipeline"] != component["route"]["selected"]:
            raise StudioError(f"Package/route mismatch: {cid}")
        records[cid] = record
    return records


def _validate_dossier_structure(project, state, dossier, packages):
    contract("construction", dossier)
    if dossier["asset_id"] != state["asset"]["id"] or dossier["target"] != state["asset"]["target"] or dossier["height_cm"] != state["asset"]["height_cm"]:
        raise StudioError("Construction dossier identity/target/scale mismatch")
    if set(dossier["components"]) != set(state["components"]):
        raise StudioError("Dossier must cover every component")
    if dossier["unresolved_blockers"]:
        raise StudioError("Resolve construction blockers before producing the approval board; retain hypotheses explicitly")
    sources = {}
    source_refs = {}
    for source in dossier["source_references"]:
        key = source["evidence_key"]
        if key in source_refs or key not in state["gates"]["references"]["evidence"]:
            raise StudioError("Original reference must be unique and bound to human reference review")
        record = project.verify_evidence(state, key)
        path = inside(project.root, record["path"])
        png_dimensions(path.read_bytes())
        sources[record["path"]] = record["sha256"]
        source_refs[key] = {"evidence": record, "source_ref": source["source_ref"]}
    def trace_reference(item):
        if not item["source_evidence_keys"] or set(item["source_evidence_keys"]) - source_refs.keys():
            raise StudioError("Every design view and piece must cite the original image evidence")
    for view in list(dossier["orthographic"].values()) + [dossier["exploded"]]:
        trace_reference(view)
        path = inside(project.root, view["path"])
        data = path.read_bytes()
        if len(data) > 16 * 1024 * 1024:
            raise StudioError("Board source PNG exceeds 16 MiB")
        png_dimensions(data)
        sources[view["path"]] = sha(path)
    garments = {}
    for cid, info in dossier["components"].items():
        package = packages[cid]
        if info["pipeline"] != package["manifest"]["pipeline"]:
            raise StudioError(f"Dossier route mismatch: {cid}")
        ids = [p["id"] for p in info["pieces"]]
        for piece in info["pieces"]:
            trace_reference(piece)
        if len(set(ids)) != len(ids):
            raise StudioError("Duplicate construction piece id")
        if info["pipeline"] == "PATTERN_SEWN":
            with zipfile.ZipFile(inside(project.root, package["path"])) as archive:
                garment = json.loads(archive.read("garment.json"))
            if set(ids) != set(garment["pieces"]):
                raise StudioError(f"Board pieces must match exact garment package: {cid}")
            for piece in info["pieces"]:
                if not piece.get("grain_direction") or len(piece["grain_direction"]) != 2 or math.hypot(*piece["grain_direction"]) < 1e-9 or "seam_allowance_cm" not in piece:
                    raise StudioError("Each sewn piece needs a grain direction and an explicit seam allowance (zero is allowed for simulation)")
                vertices = garment["pieces"][piece["id"]]["vertices"]
                actual = [max(p[i] for p in vertices) - min(p[i] for p in vertices) for i in (0, 1)]
                if any(abs(a - b) > 0.01 for a, b in zip(actual, piece["dimensions_cm"][:2])):
                    raise StudioError(f"Pattern dimensions must match package bounds: {cid}/{piece['id']}")
            garments[cid] = garment
    from .board_contract import validate_patterns, validate_proportions
    validate_patterns(dossier, garments)
    validate_proportions(project, dossier, source_refs)
    return sources, garments, source_refs


def validate_dossier(project, state, dossier, packages):
    sources, garments, source_refs = _validate_dossier_structure(project, state, dossier, packages)
    from .board_contract import require_generation
    require_generation(project, state, dossier, packages, sources)
    return sources, garments, source_refs


def render_svg(project, dossier, garments, source_refs):
    from .board_render import render
    return render(project, dossier, garments, source_refs)


def render_html(project, dossier, garments, svg_name, source_refs):
    e = lambda value: html.escape(str(value))
    out = ['<!doctype html><html lang="fr"><meta charset="utf-8"><title>Dossier de construction</title>',
           '<style>body{font:16px Segoe UI,sans-serif;color:#183246;max-width:1500px;margin:32px auto;padding:20px}img{width:100%}table{border-collapse:collapse;width:100%;margin:20px 0}th,td{border:1px solid #bccbd4;padding:10px;text-align:left;vertical-align:top}th{background:#edf2f5}h2{margin-top:36px}code{white-space:pre-wrap}</style>',
           f'<h1>{e(dossier["title"])}</h1><p>Proposition à examiner. Cette page et son image ne constituent pas une acceptation humaine.</p><img src="{e(svg_name)}" alt="Board de construction en trois parties">']
    out.append('<h2>Références originales utilisées pour concevoir ce découpage</h2>')
    for key, source in source_refs.items():
        data = inside(project.root, source["evidence"]["path"]).read_bytes()
        out.append(f'<p>{e(key)} — source : {e(source["source_ref"])} — SHA-256 : {e(source["evidence"]["sha256"])}</p><img src="data:image/png;base64,{base64.b64encode(data).decode()}" alt="Référence originale">')
    def section(title, data):
        out.append(f'<h2>{e(title)}</h2><ul>' + ''.join(f'<li>{e(s)}</li>' for s in data) + '</ul>')
    section("Gabarit et mesures", dossier["body_measurements"])
    section("Hypothèses à examiner", dossier["assumptions"])
    section("Critères de silhouette", dossier["silhouette_checks"])
    section("Mouvements et collisions à qualifier", dossier["mobility_checks"])
    section("Livraison cible", dossier["delivery_requirements"])
    for cid, info in dossier["components"].items():
        out.append(f'<h2>{e(cid)} — {e(info["pipeline"])}</h2><p>{e(info["assembly_notes"])}</p><table><tr><th>Pièce</th><th>Matière</th><th>Dimensions cm / statut</th><th>Construction / droit-fil / marge</th></tr>')
        for p in info["pieces"]:
            out.append('<tr>' + ''.join(f'<td>{e(v)}</td>' for v in (p["id"] + " — " + p["label"], p["material"], f'{p["dimensions_cm"]} / {p["basis"]}', f'{p["construction"]}; droit-fil={p.get("grain_direction", "sans objet")}; marge={p.get("seam_allowance_cm", "sans objet")}; références={p["source_evidence_keys"]}; indices/extrapolations={p["reference_notes"]}')) + '</tr>')
        out.append('</table>')
        if cid in garments:
            out.append('<h3>Fabrication des pièces</h3><table><tr><th>Pièce / caractéristiques</th><th>Coupe</th><th>Plis / milieu</th><th>Repères d’assemblage</th></tr>')
            for p in info["pieces"]:
                pattern = p["pattern"]
                values = (p["label"] + ' — ' + '; '.join(p["characteristics"]),
                    f"Couper x{pattern['cut_quantity']} : {pattern['cut_instruction']}; contour cm={pattern['cut_outline_cm']}",
                    pattern['fold_notes'] + '; ' + json.dumps(pattern['folds'], ensure_ascii=False),
                    pattern['mark_notes'] + '; ' + json.dumps(pattern['assembly_marks'], ensure_ascii=False))
                out.append('<tr>' + ''.join(f'<td>{e(v)}</td>' for v in values) + '</tr>')
            out.append('</table>')
            out.append('<h3>Assemblages issus du package</h3><table><tr><th>Couture</th><th>Pièce / bord A</th><th>Pièce / bord B</th><th>Orientation</th></tr>')
            for index, s in enumerate(garments[cid]["seams"], 1):
                out.append('<tr>' + ''.join(f'<td>{e(v)}</td>' for v in (f'S{index:02} — ' + s["id"], s["piece_a"]+" / "+s["edge_a"], s["piece_b"]+" / "+s["edge_b"], s["orientation"])) + '</tr>')
            out.append('</table>')
    out.append('<h2>Contrôles des proportions sur les images originales</h2><table><tr><th>Vue / contrôle</th><th>Rapport référence</th><th>Rapport proposé</th><th>Écart relatif</th></tr>')
    from .board_contract import validate_proportions
    for check in validate_proportions(project, dossier, source_refs):
        values = (check['view']+' / '+check['label'], f"{check['reference_ratio']:.5f}", f"{check['view_ratio']:.5f}", f"{100*check['relative_error']:.2f}%")
        out.append('<tr>' + ''.join(f'<td>{e(v)}</td>' for v in values) + '</tr>')
    out.append('</table><p>Les points mesurés sont déclarés par l’opérateur : les examiner sur les pixels. Les contrôles numériques ne prouvent pas leur placement sémantique correct.</p>')
    out.append('<p>Vérifications géométriques et traçabilité seules : la justesse du découpage, le rendu et le drapé restent à examiner par un humain.</p></html>')
    return '\n'.join(out)


def build_board(project, dossier_path):
    state = project.state()
    if state["stage"] != "PACKAGED":
        raise StudioError("Build the approval board at PACKAGED, before reconstruction")
    packages = package_records(project, state)
    dossier = read_json(inside(project.root, dossier_path))
    sources, garments, source_refs = validate_dossier(project, state, dossier, packages)
    directory = inside(project.root, f".a3d/outputs/construction-{uuid.uuid4().hex}", False)
    directory.mkdir()
    (directory / "board.svg").write_text(render_svg(project, dossier, garments, source_refs), encoding="utf-8")
    (directory / "dossier.html").write_text(render_html(project, dossier, garments, "board.svg", source_refs), encoding="utf-8")
    dependencies = {dossier_path: sha(inside(project.root, dossier_path)), **sources}
    for name in ("board.svg", "dossier.html"):
        path = (directory / name).relative_to(project.root).as_posix()
        dependencies[path] = sha(directory / name)
    manifest = {"schema_version": 1, "board_contract_version": 2, "asset_id": state["asset"]["id"], "status": "AWAITING_HUMAN_CUTTING_REVIEW",
        "dossier_path": dossier_path, "dependencies": dependencies, "source_references": source_refs,
        "packages": {cid: {"sha256": p["sha256"], "pipeline": p["manifest"]["pipeline"]} for cid, p in packages.items()},
        "pipeline_proposal": project.verify_evidence(state, "pipeline-proposal"),
        "image": (directory / "board.svg").relative_to(project.root).as_posix(),
        "technical_dossier": (directory / "dossier.html").relative_to(project.root).as_posix()}
    manifest_path = (directory / "board.json").relative_to(project.root).as_posix()
    atomic_json(directory / "board.json", manifest)
    project.evidence("construction-board", manifest_path)
    return {**manifest, "manifest_path": manifest_path, "evidence_key": "construction-board",
        "next": "Open the image and dossier, show the user the three sections. Only an actual explicit approval of this cutting may be recorded as gate construction with construction-board."}


def require_board(project, state):
    project.require_gate(state, "construction")
    if "construction-board" not in state["gates"]["construction"]["evidence"]:
        raise StudioError("Human construction approval must bind construction-board")
    rec = project.verify_evidence(state, "construction-board")
    manifest = read_json(inside(project.root, rec["path"]))
    if manifest.get("board_contract_version") != 2:
        raise StudioError("Legacy board lacks manufacturing/Codex Image/proportion checks; rebuild and obtain a new human review")
    packages = package_records(project, state)
    expected = {cid: {"sha256": p["sha256"], "pipeline": p["manifest"]["pipeline"]} for cid, p in packages.items()}
    if "reviewed-source-adoption" in state["evidence"]:
        from .reviewed_source_adoption import require_reviewed_source_adoption
        return require_reviewed_source_adoption(project, state, manifest, packages)
    if "reviewed-pattern-composition" in state["evidence"]:
        from .reviewed_pattern_admission import require_reviewed_pattern_composition
        return require_reviewed_pattern_composition(project, state, manifest, packages)
    if manifest["asset_id"] != state["asset"]["id"] or manifest["packages"] != expected or manifest["pipeline_proposal"] != project.verify_evidence(state, "pipeline-proposal"):
        raise StudioError("Construction board no longer matches routes/packages; regenerate and request a new cutting review")
    for key, source in manifest["source_references"].items():
        if project.verify_evidence(state, key) != source["evidence"]:
            raise StudioError("Original reference binding changed; repeat board review")
    for path, expected_hash in manifest["dependencies"].items():
        if sha(inside(project.root, path)) != expected_hash:
            raise StudioError("Construction board/input changed; regenerate and request a new human cutting review")
    return manifest


def admission(project):
    state = project.state()
    issues = []
    if state["stage"] not in ("PACKAGED", "RECONSTRUCTING", "RECONSTRUCTED", "ASSEMBLING", "REFINING", "BEHAVIOR_AUTHORING", "VALIDATING"):
        issues.append("Stage is not admitted for production: " + state["stage"])
    try:
        from .lifecycle import no_pending_operation, reconstruction, assembly_plan, assembly_result, silhouette
        no_pending_operation(state)
        require_board(project, state)
        if state["stage"] in ("RECONSTRUCTED", "ASSEMBLING", "REFINING", "BEHAVIOR_AUTHORING", "VALIDATING"):
            for cid in state["components"]:
                reconstruction(project, state, cid)
        if state["stage"] == "ASSEMBLING":
            assembly_plan(project, state, verify_baseline="assembly-result" not in state["evidence"])
        if state["stage"] in ("REFINING", "BEHAVIOR_AUTHORING", "VALIDATING"):
            assembly_result(project, state)
        if state["stage"] in ("BEHAVIOR_AUTHORING", "VALIDATING"):
            silhouette(project, state)
    except (StudioError, KeyError, OSError) as exc:
        issues.append(str(exc))
    return {"admitted": not issues, "stage": state["stage"], "issues": issues,
        "scope": "Current stage prerequisites only; each transition/operation performs its own additional admission.",
        "next": "Resolve listed issues, then follow references/lifecycle-guards.md for the current stage. Failed/interrupted Blender mutations require restore_checkpoint before continuing."}
