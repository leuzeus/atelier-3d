"""Deterministic preparation of a derived cloth mesh; never edits a package.

Coordinates here are cm. Blender integration supplies the constrained triangulator.
Seam parameters are normalized arc lengths on the original named boundary, not
indices guessed from proximity in a placed garment.
"""
import math
from .core import StudioError, contract, digest


def distance(a, b):
    return math.dist(a, b)


def chain_lengths(points):
    lengths = [0.0]
    for a, b in zip(points, points[1:]):
        length = distance(a, b)
        if length < 1e-8:
            raise StudioError("Collapsed source boundary segment")
        lengths.append(lengths[-1] + length)
    return lengths


def sample_chain(points, t):
    lengths = chain_lengths(points)
    target = min(1., max(0., t)) * lengths[-1]
    for i in range(len(points) - 1):
        if target <= lengths[i + 1] + 1e-9:
            f = (target - lengths[i]) / (lengths[i + 1] - lengths[i])
            return [points[i][k] + f * (points[i + 1][k] - points[i][k]) for k in range(2)]
    return list(points[-1])


def segment_distance(p, a, b):
    d = [b[i] - a[i] for i in range(len(a))]
    n = sum(x*x for x in d)
    if n < 1e-20:
        return distance(p, a)
    t = max(0., min(1., sum((p[i]-a[i])*d[i] for i in range(len(a))) / n))
    return distance(p, [a[i]+t*d[i] for i in range(len(a))])


def resample_parameters(chains, spacing, error):
    """Common samples, refined only where the precise source contour needs them."""
    lengths = [chain_lengths(p) for p in chains]
    count = max(1, math.ceil(max(v[-1] for v in lengths) / spacing))
    ts = {i/count for i in range(count+1)}
    # The maximum distance to a chord on each source straight segment is attained
    # at a source vertex. Inserting that parameter gives a finite refinement.
    while True:
        values = sorted(ts)
        insert = set()
        for points, cumulative in zip(chains, lengths):
            for lo, hi in zip(values, values[1:]):
                a, b = sample_chain(points, lo), sample_chain(points, hi)
                candidates = [(segment_distance(p, a, b), s/cumulative[-1])
                    for p, s in zip(points, cumulative) if lo < s/cumulative[-1] < hi]
                if candidates:
                    deviation, t = max(candidates)
                    if deviation > error:
                        insert.add(t)
        if not insert:
            return values
        ts.update(insert)


def signed_area(points):
    return sum(a[0]*b[1]-a[1]*b[0] for a, b in zip(points, points[1:]+points[:1])) / 2


def point_inside(p, polygon):
    inside = False
    for a, b in zip(polygon, polygon[1:]+polygon[:1]):
        if (a[1] > p[1]) != (b[1] > p[1]) and p[0] < (b[0]-a[0])*(p[1]-a[1])/(b[1]-a[1])+a[0]:
            inside = not inside
    return inside


def edge_chain(piece, name):
    ids = piece["edges"][name]
    n = len(piece["vertices"])
    signs = {1 if (b-a) % n == 1 else -1 if (a-b) % n == 1 else 0 for a, b in zip(ids, ids[1:])}
    if len(signs) != 1 or 0 in signs:
        raise StudioError("Sewing edge must follow a contiguous source boundary: " + name)
    return ids, [piece["vertices"][i] for i in ids], next(iter(signs))


def seam_report(data, recipe):
    if set(recipe["seams"]) != {s["id"] for s in data["seams"]}:
        raise StudioError("Recipe must type every seam explicitly, including closures and detachable links")
    reports, used, equations = [], set(), []
    for seam in data["seams"]:
        sid = seam["id"]
        declared = recipe["seams"][sid]
        _, a, da = edge_chain(data["pieces"][seam["piece_a"]], seam["edge_a"])
        _, b, db = edge_chain(data["pieces"][seam["piece_b"]], seam["edge_b"])
        for pid, eid in ((seam["piece_a"], seam["edge_a"]), (seam["piece_b"], seam["edge_b"])):
            ids, _, _ = edge_chain(data["pieces"][pid], eid)
            for x, y in zip(ids, ids[1:]):
                key = (pid, min(x,y), max(x,y))
                if key in used:
                    raise StudioError("Source boundary used by multiple seams")
                used.add(key)
        la, lb = chain_lengths(a)[-1], chain_lengths(b)[-1]
        residual = abs(lb/la - (1+declared["ease_b_over_a"]))
        if residual > declared["tolerance_relative"] + 1e-8:
            raise StudioError("Undeclared ease or seam length mismatch: " + sid)
        if seam.get("kind", declared["kind"]) != declared["kind"]:
            raise StudioError("Recipe cannot change a seam kind declared in its package")
        # Solve panel winding for a consistent topological join. A forward pair
        # must run in opposite directions around the two oriented boundaries.
        same = da == db * (-1 if seam["orientation"] == "reverse" else 1)
        if declared["kind"] == "permanent":
            equations.append((seam["piece_a"], seam["piece_b"], int(same)))
        reports.append({"id":sid, "kind":declared["kind"], "length_a_cm":la,
            "length_b_cm":lb, "ease_b_over_a":declared["ease_b_over_a"], "residual":residual})
    flips = {}
    for seed in data["pieces"]:
        if seed in flips:
            continue
        flips[seed] = 0
        pending = [seed]
        while pending:
            p = pending.pop()
            for a, b, parity in equations:
                if p not in (a,b):
                    continue
                q = b if p == a else a
                expected = flips[p] ^ parity
                if q in flips and flips[q] != expected:
                    raise StudioError("Contradictory permanent seam orientation")
                if q not in flips:
                    flips[q] = expected
                    pending.append(q)
    return reports, flips


def validate_recipe(data, recipe):
    contract("sewing-recipe", recipe)
    if set(recipe['seams']) != {s['id'] for s in data['seams']}:
        raise StudioError('Recipe must type every seam explicitly, including closures and detachable links')
    if recipe["component_id"] != data["component_id"]:
        raise StudioError("Sewing recipe component mismatch")
    if set(recipe["placements"]) != set(data["pieces"]):
        raise StudioError("Declare the placement of every panel")
    if any(p.get('mirror_u', False) and p['mode'] != 'cylinder' for p in recipe['placements'].values()):
        raise StudioError('mirror_u is supported only for cylindrical placement')
    if recipe["mesh"]["min_stretch"] >= recipe["mesh"]["max_stretch"]:
        raise StudioError("Invalid placement strain bounds")
    if set(recipe["trial_pieces"]) - data["pieces"].keys() or len(set(recipe["trial_pieces"])) < 2:
        raise StudioError("Local trial needs at least two declared panels")
    trial = [s for s in data["seams"] if s["piece_a"] in recipe["trial_pieces"] and s["piece_b"] in recipe["trial_pieces"]
             and recipe["seams"][s["id"]]["kind"] == "permanent"]
    if not trial:
        raise StudioError("Local trial must contain a permanent seam")
    for pin in recipe["pins"]:
        if pin["piece"] not in data["pieces"] or pin["edge"] not in data["pieces"][pin["piece"]]["edges"]:
            raise StudioError("Pin group refers to an unknown pattern edge")
    if not recipe["colliders"] and not recipe["no_collision_reason"].strip():
        raise StudioError("Missing mannequin/collider or explicit free-test reason")
    if len({c["object"] for c in recipe["colliders"]}) != len(recipe["colliders"]):
        raise StudioError("Duplicate collision object")
    if len({s['id'] for s in data['seams']}) != len(data['seams']):
        raise StudioError('Duplicate seam identifiers')
    tacks=recipe.get('fitting_tacks',[])
    if len({t['id'] for t in tacks})!=len(tacks) or len({(t['seam_id'],t['phase']) for t in tacks})!=len(tacks):
        raise StudioError('Duplicate temporary fitting tack')
    seams={s['id']:s for s in data['seams']}
    for tack in tacks:
        sid=tack['seam_id'];seam=seams.get(sid);profile=recipe['phases'][tack['phase']]
        if seam is None or recipe['seams'][sid]['kind']!='closure':raise StudioError('Temporary fitting tack requires an existing closure')
        if {seam['piece_a'],seam['piece_b']}-set(recipe['trial_pieces']):raise StudioError('Temporary closure must retain both panels in the local trial')
        if tack['frame_end']!=profile['frames'] or tack['sewing_force_per_kg']!=profile['sewing_force_per_kg']:
            raise StudioError('Native fitting tacks share the Cloth sewing force and span the entire declared local phase')
    return seam_report(data, recipe)


def fitting_tack_payload(payload,recipe,phase):
    """A construction-only copy; original closure kind and source pairs remain."""
    import copy
    result=copy.deepcopy(payload);selected=[]
    for tack in recipe.get('fitting_tacks',[]):
        if tack['phase']!=phase:continue
        seam=result['seams'].get(tack['seam_id'])
        if seam is None or seam['kind']!='closure':raise StudioError('Temporary closure absent from trial mapping')
        selected.append({**tack,'pairs':copy.deepcopy(seam['pairs'])})
    result['fitting_tacks']=selected
    return result


def active_sewing_pairs(payload):
    permanent=[p for seam in payload['seams'].values() if seam['kind']=='permanent' for p in seam['pairs']]
    temporary=[p for tack in payload.get('fitting_tacks',[]) for p in tack['pairs']]
    return permanent+temporary


def prepare_boundaries(data, recipe):
    reports, flips = validate_recipe(data, recipe)
    spacing = recipe["mesh"]["spacing_cm"]
    error = recipe["mesh"]["max_boundary_error_cm"]
    samples, seam_samples, covered = {}, {}, {}
    for pid, piece in data["pieces"].items():
        points = piece["vertices"]
        perimeter = chain_lengths(points + points[:1])
        samples[pid] = {"source":points, "perimeter":perimeter, "points":{}}
        covered[pid] = set()

    def put(pid, chain, t):
        piece = data["pieces"][pid]
        pts = [piece["vertices"][i] for i in chain]
        lengths = chain_lengths(pts)
        target = t * lengths[-1]
        for j, (a,b) in enumerate(zip(chain, chain[1:])):
            if target <= lengths[j+1] + 1e-8:
                f = min(1., max(0., (target-lengths[j])/(lengths[j+1]-lengths[j])))
                n = len(piece["vertices"])
                index = a if (b-a) % n == 1 else b
                along = f if index == a else 1-f
                perimeter = samples[pid]["perimeter"]
                s = (perimeter[index]+along*(perimeter[index+1]-perimeter[index])) % perimeter[-1]
                key = round(s, 8)
                if abs(key-perimeter[-1])<1e-8:key=0.
                samples[pid]["points"][key] = sample_chain(pts,t)
                return key
        raise StudioError("Boundary sampling failed")

    for seam in data["seams"]:
        pa, pb = seam["piece_a"], seam["piece_b"]
        ca, a, _ = edge_chain(data["pieces"][pa], seam["edge_a"])
        cb, b, _ = edge_chain(data["pieces"][pb], seam["edge_b"])
        if seam["orientation"] == "reverse":
            cb, b = list(reversed(cb)), list(reversed(b))
        ts = resample_parameters([a,b],spacing,error)
        # Preserve named-edge endpoints used by pin groups, while carrying every
        # inserted parameter to both sides of this seam.
        for pid, chain, points in ((pa,ca,a),(pb,cb,b)):
            lengths = chain_lengths(points)
            endpoints = {i for e in data["pieces"][pid]["edges"].values() for i in (e[0],e[-1])}
            ts = sorted(set(ts) | {lengths[j]/lengths[-1] for j,i in enumerate(chain) if i in endpoints})
        seam_samples[seam["id"]] = {"piece_a":pa,"piece_b":pb,"kind":recipe["seams"][seam["id"]]["kind"],
            "parameters":ts,"a":[put(pa,ca,t) for t in ts],"b":[put(pb,cb,t) for t in ts]}
        for pid, chain in ((pa,ca),(pb,cb)):
            covered[pid].update(tuple(sorted((a,b))) for a,b in zip(chain,chain[1:]))
    for pid,piece in data["pieces"].items():
        n=len(piece["vertices"])
        # Unsewn boundary runs are resampled as polylines too; dense source curves
        # need not dictate the number of simulation vertices.
        anchors={i for e in piece["edges"].values() for i in (e[0],e[-1])} | {0}
        for i in range(n):
            prev=tuple(sorted(((i-1)%n,i))); nxt=tuple(sorted((i,(i+1)%n)))
            if (prev in covered[pid]) != (nxt in covered[pid]): anchors.add(i)
        anchors=sorted(anchors)
        for start,end in zip(anchors,anchors[1:]+[anchors[0]+n]):
            chain=[i%n for i in range(start,end+1)]
            if all(tuple(sorted((a,b))) in covered[pid] for a,b in zip(chain,chain[1:])):
                continue
            if any(tuple(sorted((a,b))) in covered[pid] for a,b in zip(chain,chain[1:])):
                raise StudioError("Overlapping source boundary declarations")
            ts=resample_parameters([[piece["vertices"][i] for i in chain]],spacing,error)
            for t in ts:put(pid,chain,t)
        keys=sorted(samples[pid]["points"])
        polygon=[samples[pid]["points"][s] for s in keys]
        from .board_contract import simple_polygon
        if len(polygon)<3 or abs(signed_area(polygon))<1e-6 or not simple_polygon(polygon):
            raise StudioError("Invalid derived boundary")
        samples[pid].update(keys=keys,polygon=polygon,flip=flips[pid],source_sha256=digest(piece["vertices"]))
        edge_ids={}
        for name in piece["edges"]:
            chain,points,sign=edge_chain(piece,name)
            start=samples[pid]["perimeter"][chain[0]]; length=chain_lengths(points)[-1]; total=samples[pid]["perimeter"][-1]
            selected=sorted((((s-start)*sign)%total,i) for i,s in enumerate(keys))
            edge_ids[name]=[i for along,i in selected if along<=length+1e-6 or total-along<1e-6]
            edge_ids[name].sort(key=lambda i:0 if total-((keys[i]-start)*sign)%total<1e-6 else ((keys[i]-start)*sign)%total)
        samples[pid]["edges"]=edge_ids
    for seam in seam_samples.values():
        for side in ("a","b"):
            lookup={v:i for i,v in enumerate(samples[seam["piece_"+side]]["keys"])}
            seam[side]=[lookup[k] for k in seam[side]]
    return samples,seam_samples,reports


def mesh_quality(rest, placed, faces, limits):
    if len(rest)!=len(placed) or any(not math.isfinite(v) for p in rest+placed for v in p):
        raise StudioError("Nonfinite or mismatched simulation geometry")
    minimum_angle=180.; minimum_area=float("inf"); minimum_edge=float("inf")
    low=float("inf"); high=0.; total_area=0.
    for face in faces:
        if len(face)!=3 or len(set(face))!=3:
            raise StudioError("Simulation mesh must contain nondegenerate triangles")
        r=[rest[i] for i in face]; q=[placed[i] for i in face]
        lengths=[distance(r[i],r[(i+1)%3]) for i in range(3)]
        world=[distance(q[i],q[(i+1)%3]) for i in range(3)]
        minimum_edge=min(minimum_edge,*world)
        if min(lengths)<1e-8:
            raise StudioError("Collapsed rest edge")
        ratios=[b/a for a,b in zip(lengths,world)]
        low=min(low,*ratios);high=max(high,*ratios)
        for ls in (lengths,world):
            if min(ls)<1e-8:raise StudioError("Collapsed placed edge")
            a,b,c=ls; sem=(a+b+c)/2; area=math.sqrt(max(0,sem*(sem-a)*(sem-b)*(sem-c)))
            minimum_area=min(minimum_area,area)
            for i in range(3):
                x,y,z=ls[i],ls[(i+1)%3],ls[(i+2)%3]
                minimum_angle=min(minimum_angle,math.degrees(math.acos(max(-1.,min(1.,(x*x+y*y-z*z)/(2*x*y))))))
        a,b,c=lengths;sem=(a+b+c)/2;total_area+=math.sqrt(max(0,sem*(sem-a)*(sem-b)*(sem-c)))
    result={"min_angle_degrees":minimum_angle,"min_area_cm2":minimum_area,"min_edge_cm":minimum_edge,
        "min_stretch":low,"max_stretch":high,"rest_area_cm2":total_area}
    if not faces or minimum_area<1e-8 or minimum_angle<limits["min_angle_degrees"]:
        raise StudioError("Degenerate/sliver simulation triangles: " + str(result))
    if minimum_edge<limits["min_edge_cm"] or low<limits["min_stretch"] or high>limits["max_stretch"]:
        raise StudioError("Collapsed or distorted placement: " + str(result))
    return result


def mass_settings(mass, area_cm2, count, force_per_kg):
    if count<3 or area_cm2<=0:
        raise StudioError("Mass needs positive rest area and vertex count")
    total=mass["value"] if mass["basis"]=="total_kg" else mass["value"]*area_cm2/10000
    per_vertex=total/count
    return {"total_mass_kg":total,"mass_per_vertex_kg":per_vertex,"sewing_force_max":per_vertex*force_per_kg}


def weld_permanent(vertices, faces, seams, max_gap):
    parent=list(range(len(vertices)))
    def root(i):
        while parent[i]!=i:
            parent[i]=parent[parent[i]];i=parent[i]
        return i
    count=0
    for seam in seams.values():
        if seam["kind"]!="permanent":continue
        for a,b in seam["pairs"]:
            if distance(vertices[a],vertices[b])>max_gap:
                raise StudioError("Permanent seam is not settled; refusing forced weld")
            ra,rb=root(a),root(b)
            if ra!=rb:parent[rb]=ra;count+=1
    if not count:raise StudioError("No permanent seam pairs to freeze")
    groups={}
    for i in range(len(vertices)):groups.setdefault(root(i),[]).append(i)
    remap={}; result=[]
    for ids in groups.values():
        for i in ids:remap[i]=len(result)
        result.append([sum(vertices[i][k] for i in ids)/len(ids) for k in range(3)])
    output=[]; edge_faces={}; unique=set()
    for f in faces:
        if len(f)!=3:raise StudioError('Freeze requires the derived triangular simulation mesh')
        new=[remap[i] for i in f]
        if len(set(new))!=len(new):raise StudioError("Weld would collapse a face")
        # Index uniqueness alone does not prevent a flattened triangle after
        # averaging a transitive seam junction. Coordinates here are meters.
        a,b,c=[result[i] for i in new]
        u=[b[k]-a[k] for k in range(3)];v=[c[k]-a[k] for k in range(3)]
        cross=[u[1]*v[2]-u[2]*v[1],u[2]*v[0]-u[0]*v[2],u[0]*v[1]-u[1]*v[0]]
        if sum(x*x for x in cross)<1e-20:raise StudioError('Weld would create a zero-area face')
        key=tuple(sorted(new))
        if key in unique:raise StudioError("Weld would duplicate a face")
        unique.add(key);output.append(new)
        for a,b in zip(new,new[1:]+new[:1]):edge_faces.setdefault(tuple(sorted((a,b))),[]).append((a,b))
    if any(len(v)>2 or len(v)==2 and v[0]==v[1] for v in edge_faces.values()):
        raise StudioError("Weld would create nonmanifold or inconsistently oriented edges")
    return result,output,remap,count
