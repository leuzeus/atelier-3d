"""Manufacturing annotations, image provenance and measurable board proportions."""
import json
import math
import uuid
import zipfile
from .core import StudioError, atomic_json, contract, digest, inside, read_json, sha
from .packages import png_dimensions


def pieces(dossier):
    return [(cid, piece) for cid, component in dossier["components"].items() for piece in component["pieces"]]


def design(dossier):
    # Output pixels/anchors and candidate measurements are completed after Image.
    return {k: dossier[k] for k in ("asset_id", "target", "height_cm", "components", "body_measurements", "assumptions", "silhouette_checks", "source_references")} | {
        "proportion_checks": [{k: v for k, v in c.items() if k != "view_spans_px"} for c in dossier["proportion_checks"]]}


def originals(project, state, dossier):
    project.require_gate(state, "references")
    records = {}
    for source in dossier["source_references"]:
        key = source["evidence_key"]
        if key in records or key not in state["gates"]["references"]["evidence"]:
            raise StudioError("Image generation needs unique reviewed original references")
        records[key] = project.verify_evidence(state, key)
        png_dimensions(inside(project.root, records[key]["path"]).read_bytes())
    return records


def prepare_exploded(project, dossier_path):
    from .planning import package_records
    state = project.state()
    if state["stage"] != "PACKAGED":
        raise StudioError("Prepare the exploded view at PACKAGED from the actual cutting data")
    dossier = contract("construction", read_json(inside(project.root, dossier_path)))
    packages = package_records(project, state)
    if dossier["asset_id"] != state["asset"]["id"] or set(dossier["components"]) != set(packages):
        raise StudioError("Exploded request does not match this project")
    if dossier['target'] != state['asset']['target'] or dossier['height_cm'] != state['asset']['height_cm'] or dossier['unresolved_blockers']:
        raise StudioError("Resolve the cutting design identity/scale/blockers before the image request")
    garments = {}
    for cid, info in dossier['components'].items():
        if info['pipeline'] != packages[cid]['manifest']['pipeline']:
            raise StudioError("Exploded design route differs from the bound package")
        ids = [p['id'] for p in info['pieces']]
        if len(set(ids)) != len(ids):
            raise StudioError("Duplicate exploded design piece")
        if info['pipeline'] == 'PATTERN_SEWN':
            with zipfile.ZipFile(inside(project.root, packages[cid]['path'])) as archive:
                garments[cid] = json.loads(archive.read('garment.json'))
            if set(ids) != set(garments[cid]['pieces']):
                raise StudioError("Codex Image inventory must match exact pattern pieces")
            for p in info['pieces']:
                vertices = garments[cid]['pieces'][p['id']]['vertices']
                actual = [max(v[i] for v in vertices)-min(v[i] for v in vertices) for i in (0,1)]
                if any(abs(a-b) > .01 for a,b in zip(actual,p['dimensions_cm'][:2])):
                    raise StudioError("Codex Image design dimensions must match the package")
                if 'seam_allowance_cm' not in p or len(p.get('grain_direction',[])) != 2 or math.hypot(*p['grain_direction']) < 1e-9:
                    raise StudioError("Pattern needs an explicit allowance and grain direction")
    validate_patterns(dossier, garments)
    sources = originals(project, state, dossier)
    rows = [f"{cid}/{p['id']} | {p['label']} | {p['dimensions_cm']} cm | {p['material']} | " + '; '.join(p['characteristics']) for cid, p in pieces(dossier)]
    prompt = ("Use case: infographic-diagram. Produce the exploded asset/garment component illustration for section 2 of a technical construction board. "
        "Use the attached original reference images as the design authority, not a generated mesh. Preserve their exact silhouette and relative dimensions; where present, preserve slenderness, sleeve/wrist widths, hood size, panel continuity and front openings. "
        "Use the following exact component and cutting-piece inventory; each entry must be separately visible once, including lining and detachable parts where listed. "
        "Keep relative dimensions consistent in a neutral front-facing orthographic exploded arrangement. Separate pieces by translation, not by resizing each to fill its slot. "
        "White background, clearly isolated pieces, no cropped edges, generous blank spaces around each piece for the compositor to place its name and leader line. Do not invent extra pieces or change materials. "
        "Do not render text: the board compositor adds exact numbered callouts, piece names, materials, dimensions and characteristics linked to each piece. "
        "This illustration is a human design-review proposal, not a measured sewing pattern.\n"
        + '\n'.join(rows) + "\nREFERENCE CONSTRAINTS AND MEASUREMENTS:\n" + json.dumps(design(dossier), ensure_ascii=False))
    request = {"provider": "Codex Image", "tool": "image_gen", "asset_id": dossier["asset_id"],
        "design_sha256": digest(design(dossier)), "packages": {cid: p["sha256"] for cid, p in packages.items()},
        "source_references": sources, "prompt": prompt, "referenced_image_paths": [str(inside(project.root, r["path"])) for r in sources.values()]}
    path = f".a3d/evidence/exploded-request-{uuid.uuid4().hex}.json"
    atomic_json(inside(project.root, path, False), request)
    project.evidence("exploded-image-request", path)
    return {"request_evidence_key": "exploded-image-request", "path": path, "request": request, "executed": False,
        "next": "Inspect original inputs, call built-in Codex Image with this prompt and referenced_image_paths, copy its actual PNG into the project, then studio_register_exploded_view. No silent Comfy/template substitute."}


def register_exploded(project, image_path, tool_source_ref):
    state = project.state()
    if state["stage"] != "PACKAGED" or not tool_source_ref.strip():
        raise StudioError("Register an actual Codex Image tool result at PACKAGED with its conversation/tool reference")
    rec = project.verify_evidence(state, "exploded-image-request")
    request = read_json(inside(project.root, rec["path"]))
    if request["provider"] != "Codex Image" or request["tool"] != "image_gen":
        raise StudioError("Exploded view requires Codex Image")
    for key, source in request["source_references"].items():
        if source != project.verify_evidence(state, key):
            raise StudioError("Original input changed since the image request")
    path = inside(project.root, image_path)
    png_dimensions(path.read_bytes())
    receipt = {"provider": "Codex Image", "tool": "image_gen", "tool_source_ref": tool_source_ref,
        "request": rec, "image": {"path": image_path, "sha256": sha(path)}, "visual_approval": "PENDING",
        "qualification": "Reported tool provenance; this receipt alone does not authenticate tool execution or visual fidelity."}
    target = f".a3d/evidence/exploded-generation-{uuid.uuid4().hex}.json"
    atomic_json(inside(project.root, target, False), receipt)
    project.evidence("exploded-image-generation", target)
    return {"evidence_key": "exploded-image-generation", "path": target, "receipt": receipt}


def require_generation(project, state, dossier, packages, sources):
    key = dossier["exploded"].get("generation_evidence_key")
    if not key:
        raise StudioError("Exploded view needs a registered Codex Image result")
    record = project.verify_evidence(state, key)
    receipt = read_json(inside(project.root, record["path"]))
    if receipt.get("provider") != "Codex Image" or receipt.get("tool") != "image_gen" or not receipt.get("tool_source_ref"):
        raise StudioError("Exploded view requires Codex Image provenance")
    req_record = project.verify_evidence(state, "exploded-image-request")
    if receipt["request"] != req_record:
        raise StudioError("Exploded image was generated for another request")
    request = read_json(inside(project.root, req_record["path"]))
    if request["design_sha256"] != digest(design(dossier)) or request["packages"] != {cid: p["sha256"] for cid, p in packages.items()}:
        raise StudioError("Cutting design changed after the Codex Image request; regenerate the exploded view")
    if request["source_references"] != originals(project, state, dossier):
        raise StudioError("Codex Image input references changed")
    image = receipt["image"]
    if image["path"] != dossier["exploded"]["path"] or sha(inside(project.root, image["path"])) != image["sha256"]:
        raise StudioError("Exploded pixels differ from the registered Codex Image result")
    sources.update({record["path"]: record["sha256"], req_record["path"]: req_record["sha256"]})


def distance(a, b):
    return math.dist(a, b)


def segment_distance(p, a, b):
    return distance(p, project_segment(p, a, b))


def project_segment(p, a, b):
    dx, dy = b[0]-a[0], b[1]-a[1]
    norm = dx*dx + dy*dy
    t = max(0, min(1, ((p[0]-a[0])*dx+(p[1]-a[1])*dy)/norm)) if norm else 0
    return (a[0]+t*dx, a[1]+t*dy)


def inside_polygon(point, polygon):
    x, y = point
    result = False
    for a, b in zip(polygon, polygon[1:]+polygon[:1]):
        if segment_distance(point, a, b) < 1e-7:
            return True
        if (a[1] > y) != (b[1] > y) and x < (b[0]-a[0])*(y-a[1])/(b[1]-a[1])+a[0]:
            result = not result
    return result


def simple_polygon(polygon):
    if len(set(map(tuple, polygon))) != len(polygon):
        return False
    area = sum(a[0]*b[1]-b[0]*a[1] for a, b in zip(polygon, polygon[1:]+polygon[:1]))
    if abs(area) < 1e-8:
        return False
    edges = list(zip(polygon, polygon[1:]+polygon[:1]))
    def cross(a, b, c): return (b[0]-a[0])*(c[1]-a[1])-(b[1]-a[1])*(c[0]-a[0])
    for i, (a,b) in enumerate(edges):
        for j, (c,d) in enumerate(edges[i+1:], i+1):
            if j == i+1 or (i == 0 and j == len(edges)-1):
                continue
            if cross(a,b,c)*cross(a,b,d) < 0 and cross(c,d,a)*cross(c,d,b) < 0:
                return False
            if min(segment_distance(a,c,d), segment_distance(b,c,d), segment_distance(c,a,b), segment_distance(d,a,b)) < 1e-7:
                return False
    return True


def at_edge(vertices, indexes, fraction):
    path = [vertices[i] for i in indexes]
    lengths = [distance(a,b) for a,b in zip(path,path[1:])]
    remaining = fraction * sum(lengths)
    for a,b,length in zip(path,path[1:],lengths):
        if remaining <= length and length:
            t = remaining / length
            return [a[i]+t*(b[i]-a[i]) for i in (0,1)]
        remaining -= length
    return path[-1]


def assembly_mark_position(mark, seam, side):
    """Read an explicit unary seam side, retaining the legacy shared fraction."""
    if side not in ('a','b'):
        raise StudioError('Assembly mark must name a source seam side')
    positions=mark.get('seam_side_positions')
    if 'seam_side_positions'in mark:
        if (seam['piece_a']!=seam['piece_b'] or not isinstance(positions,dict)
                or set(positions)!={'a','b'}):
            raise StudioError('Explicit assembly mark sides require both sides of one unary source seam')
        if any(type(value)not in(int,float) or not math.isfinite(value) or not 0<=value<=1
                for value in positions.values()):
            raise StudioError('Assembly mark side positions must be finite normalized source arcs')
        expected=1-positions['a']if seam['orientation']=='reverse'else positions['a']
        if abs(positions['b']-expected)>1e-6:
            raise StudioError('Assembly mark side positions disagree with the source seam orientation')
        return positions[side]
    position=mark.get('position')
    if type(position)not in(int,float) or not math.isfinite(position) or not 0<=position<=1:
        raise StudioError('Assembly mark needs a finite normalized source arc position')
    return position


def validate_patterns(dossier, garments):
    for cid, garment in garments.items():
        infos = {p["id"]: p for p in dossier["components"][cid]["pieces"]}
        seams = {s["id"]: s for s in garment["seams"]}
        if len(seams) != len(garment["seams"]):
            raise StudioError("Seam identifiers must be unique for assembly marks")
        for pid, info in infos.items():
            if "pattern" not in info:
                raise StudioError("Manufacturing patterns require cut outline, folds, grain and assembly marks")
            pattern = info["pattern"]
            outline = pattern["cut_outline_cm"]
            vertices = garment["pieces"][pid]["vertices"]
            if not simple_polygon(outline) or not simple_polygon(vertices):
                raise StudioError("Cutting and sewing contours must be simple nondegenerate polygons")
            # Sample every edge as well as vertices: concave cut lines must contain the sewing contour.
            samples = [at_edge(vertices, [i,(i+1)%len(vertices)], t/20) for i in range(len(vertices)) for t in range(21)]
            if any(not inside_polygon(v, outline) for v in samples):
                raise StudioError("Cut outline must contain the sewing contour")
            clearance = min(segment_distance(v,a,b) for v in samples for a,b in zip(outline,outline[1:]+outline[:1]))
            if clearance + 0.05 < info["seam_allowance_cm"]:
                raise StudioError("Drawn cut margin is smaller than the declared seam allowance")
            ids = [f["id"] for f in pattern["folds"]]
            if len(ids) != len(set(ids)):
                raise StudioError("Duplicate fold identifier")
            for fold in pattern["folds"]:
                line = fold["line_cm"]
                samples = [tuple(a[j]+t/20*(b[j]-a[j]) for j in (0,1)) for a,b in zip(line,line[1:]) for t in range(21)]
                if sum(distance(a,b) for a,b in zip(line,line[1:])) < 1e-8 or any(not inside_polygon(v, outline) for v in samples):
                    raise StudioError("Fold line must have length and remain inside its pattern")
            marks = pattern["assembly_marks"]
            if len({(m["seam_id"],m["id"]) for m in marks}) != len(marks):
                raise StudioError("Duplicate assembly mark")
            for mark in marks:
                seam = seams.get(mark["seam_id"])
                if not seam or pid not in (seam["piece_a"],seam["piece_b"]):
                    raise StudioError("Assembly mark must reference a seam belonging to the piece")
        for seam in garment["seams"]:
            left = {m["id"]: m for m in infos[seam["piece_a"]]["pattern"]["assembly_marks"] if m["seam_id"] == seam["id"]}
            right = {m["id"]: m for m in infos[seam["piece_b"]]["pattern"]["assembly_marks"] if m["seam_id"] == seam["id"]}
            if not left or left.keys() != right.keys():
                raise StudioError("Each seam needs matching assembly marks on both pieces")
            for key,a in left.items():
                b = right[key]
                position_a=assembly_mark_position(a,seam,'a');position_b=assembly_mark_position(b,seam,'b')
                target = 1-position_a if seam["orientation"] == "reverse" else position_a
                if abs(position_b-target)>1e-6 or a["symbol"] != b["symbol"]:
                    raise StudioError("Assembly marks disagree with the seam orientation")


def validate_proportions(project, dossier, source_refs):
    views = {**dossier["orthographic"], "exploded": dossier["exploded"]}
    heights = []
    for view in dossier["orthographic"].values():
        w,h = png_dimensions(inside(project.root, view["path"]).read_bytes())
        x,y,bw,bh = view["subject_bbox_px"]
        if bw<=0 or bh<=0 or x+bw>w or y+bh>h:
            raise StudioError("Orthographic subject crop lies outside its image")
        heights.append(view["subject_height_cm"])
    if max(heights)-min(heights)>0.01:
        raise StudioError("Orthographic views must use the same subject height and framing")
    expected = {(cid,p["id"]) for cid,p in pieces(dossier)}
    actual = [(a["component_id"],a["piece_id"]) for a in dossier["exploded"]["annotations"]]
    if len(set(actual))!=len(actual) or set(actual)!=expected:
        raise StudioError("Exploded callouts must identify every piece exactly once")
    if len({tuple(a['anchor_px']) for a in dossier['exploded']['annotations']}) != len(actual):
        raise StudioError("Each exploded piece needs its own callout anchor")
    w,h = png_dimensions(inside(project.root, dossier["exploded"]["path"]).read_bytes())
    if any(not (0<=a[field][0]<=w and 0<=a[field][1]<=h) for a in dossier["exploded"]["annotations"] for field in ('anchor_px','label_position_px')):
        raise StudioError("Exploded callout anchor lies outside the generated image")
    covered = set()
    results = []
    def ratio(spans, dimensions):
        if any(not (0<=p[0]<=dimensions[0] and 0<=p[1]<=dimensions[1]) for line in spans for p in line):
            raise StudioError("Proportion measurement lies outside its image")
        if spans[0] == spans[1] or spans[0] == list(reversed(spans[1])):
            raise StudioError("Proportion check must compare two distinct spans")
        lengths=[distance(*line) for line in spans]
        if min(lengths)<=1e-8:
            raise StudioError("Proportion measurement needs nonzero spans")
        return lengths[0]/lengths[1]
    for check in dossier["proportion_checks"]:
        key=check["source_evidence_key"]
        if key not in source_refs:
            raise StudioError("Proportion checks must use original reference evidence")
        dims=png_dimensions(inside(project.root, source_refs[key]["evidence"]["path"]).read_bytes())
        vdims=png_dimensions(inside(project.root, views[check["view"]]["path"]).read_bytes())
        ref=ratio(check["reference_spans_px"], dims)
        measured=ratio(check["view_spans_px"], vdims)
        error=abs(measured/ref-1)
        if error>check["tolerance_relative"]+1e-9:
            raise StudioError("Reference proportion mismatch: " + check["label"])
        covered.add(check["view"])
        results.append({"label":check["label"],"view":check["view"],"reference_ratio":ref,"view_ratio":measured,"relative_error":error})
    if covered != set(views):
        raise StudioError("Measure reference proportions for front, side, back and exploded views")
    return results
