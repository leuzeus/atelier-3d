"""Data-driven local metric experiment with explicit numerical halo.

The partner boundary is temporarily driven by the saved driver curve. These
are sewing targets for this block, never newly approved anatomical anchors.
A necessary path conflict refuses only this frozen-boundary subproblem.
"""
import argparse, copy, heapq, json, math
from pathlib import Path
import numpy as np
from solve_piece_contact import require, sha
from propose_partner_rigid import evaluate


def distances(uv, triangles, seed):
    adjacent=[{} for _ in uv]
    for face in triangles:
        for a,b in zip(face,face[1:]+face[:1]):
            length=math.dist(uv[a],uv[b]);adjacent[a][b]=length;adjacent[b][a]=length
    values={seed:0.}; heap=[(0.,seed)]
    while heap:
        d,i=heapq.heappop(heap)
        if values.get(i)!=d:continue
        for j,length in adjacent[i].items():
            n=d+length
            if n<values.get(j,math.inf): values[j]=n;heapq.heappush(heap,(n,j))
    return values


def prepare(frames, bindings, piece, block):
    cage=frames[piece]; target=copy.deepcopy(cage); targets={}; provenance={}; variable_supports=[]
    selected=[row for row in bindings if row['partner']['piece']==piece]
    for row in selected:
        support=row['partner']['support']
        unit=[i for i,w in zip(support['control_indices'],support['weights']) if w==1.]
        if len(unit)!=1 or any(w not in (0.,1.) for w in support['weights']):
            variable_supports.append(row['binding_id']);continue
        for i in unit:
            point=evaluate(row['driver']['support'],frames[row['driver']['piece']])
            if i in targets: require(math.dist(point,targets[i])<1e-10,'CONFLICTING_SOURCE_CORNER_TARGETS')
            else:targets[i]=point
            provenance.setdefault(i,[]).append(row['binding_id'])
    require(targets,'NO_BOUNDARY_CONTROLS')
    free=set(block['free_control_indices']); halo=set(block['halo_control_indices'])
    require(set(targets)<=free,'BOUNDARY_OUTSIDE_DECLARED_BLOCK')
    touched=[j for j,face in enumerate(cage['triangles']) if any(i in free for i in face)]
    used=sorted(set(i for j in touched for i in cage['triangles'][j])); reverse={i:j for j,i in enumerate(used)}
    require(set(used)==free|halo,'HALO_DOES_NOT_COVER_ALL_TOUCHED_FACES')
    for i,p in targets.items():target['target_cm'][i]=p
    # Necessary upper length bound along actual material triangle edges.
    conflicts=[]
    for i,p in targets.items():
        paths=distances(cage['uv_cm'],cage['triangles'],i)
        for j in halo:
            chord=math.dist(p,cage['target_cm'][j]); upper=1.02*paths[j]
            if chord>upper+1e-9:
                conflicts.append({'boundary_control':i,'halo_control':j,'source_edge_path_cm':paths[j],
                    'target_chord_cm':chord,'necessary_upper_bound_excess_cm':chord-upper})
    sub={k:copy.deepcopy(v) for k,v in cage.items() if k not in ('uv_cm','target_cm','triangles')}
    sub.update(uv_cm=[cage['uv_cm'][i] for i in used],target_cm=[target['target_cm'][i] for i in used],
        triangles=[[reverse[i] for i in cage['triangles'][j]] for j in touched])
    return {'status':'FROZEN_BLOCK_NECESSARY_PATH_CONFLICT' if conflicts else 'BLOCK_PREPARED_NOT_SOLVED',
        'qualification':'NONE','piece':piece,'temporary_sewing_targets':targets,'binding_provenance':provenance,
        'nonunit_sewing_supports_not_frozen':variable_supports,
        'material_edge_band_cm':block['material_edge_band_cm'],'halo_role':'NUMERICAL_BOUNDARY_NOT_ANATOMICAL_ATTACHMENT',
        'global_control_indices':used,'global_triangle_indices':touched,
        'fixed_local_indices':sorted(reverse[i] for i in halo|set(targets)),
        'necessary_path_conflicts':conflicts,'sub_cage':sub,'original_full_cage':cage}


def main():
    ap=argparse.ArgumentParser();ap.add_argument('--request',required=True);path=Path(ap.parse_args().request)
    request=json.loads(path.read_text(encoding='utf-8'));out=Path(request['output_directory']);out.mkdir(exist_ok=False)
    artifacts={}
    def read(ref):
        require(sha(ref['path'])==ref['sha256'],'STALE_INPUT');artifacts[ref['path']]=ref['sha256']
        return json.loads(Path(ref['path']).read_text(encoding='utf-8'))
    inputs=read(request['solver_input_ref']);frames=read(inputs['current_frames_ref']);bindings=read(inputs['source_bindings_ref'])
    report=read(request['coupling_report_ref']); summaries=[]
    for item in request['pieces']:
        row=next(row for row in report['partners'] if row['piece']==item['piece'])
        block=next(row for row in row['blocks'] if row['material_edge_band_cm']==item['material_edge_band_cm'])
        result=prepare(frames,bindings['bindings'],item['piece'],block)
        result.update(artifacts=artifacts,helper_sha256=sha(__file__),request_sha256=sha(path))
        dest=out/(item['piece']+'.json');dest.write_text(json.dumps(result,separators=(',',':')),encoding='utf-8')
        summaries.append({'piece':item['piece'],'status':result['status'],'controls':len(result['sub_cage']['uv_cm']),
            'fixed':len(result['fixed_local_indices']),'conflicts':len(result['necessary_path_conflicts']),
            'max_excess_cm':max((r['necessary_upper_bound_excess_cm'] for r in result['necessary_path_conflicts']),default=0.),
            'path':str(dest),'sha256':sha(dest)})
    (out/'report.json').write_text(json.dumps({'summaries':summaries,'qualification':'NONE'},indent=2),encoding='utf-8')
    print(json.dumps(summaries))


if __name__=='__main__':main()
