"""One bounded metric solve on an explicitly frozen sewing/halo band.

Uses the existing experimental QR solver and audits the entire partner after
reinsertion. A result never changes the canonical scene or qualifies fitting.
"""
import argparse, copy, json, math, sys
from pathlib import Path
import numpy as np
import solve_piece_metric
import solve_piece_contact
from solve_piece_metric import solve, metric
from solve_piece_contact import sha, require, Budget, Body, contact_summary
from propose_partner_rigid import evaluate


def main():
    ap=argparse.ArgumentParser();ap.add_argument('--request',required=True);rp=Path(ap.parse_args().request)
    req=json.loads(rp.read_text(encoding='utf-8'));out=Path(req['output_directory']);out.mkdir(exist_ok=False)
    budget=Budget(req['budgets']);artifacts={};report={'status':'INCOMPLETE','qualification':'NONE'}
    def read(ref):
        require(sha(ref['path'])==ref['sha256'],'STALE_INPUT');artifacts[ref['path']]=ref['sha256']
        return json.loads(Path(ref['path']).read_text(encoding='utf-8'))
    def save(name,data):
        p=out/name;p.write_text(json.dumps(data,separators=(',',':'),allow_nan=False),encoding='utf-8');return sha(p)
    try:
        band=read(req['band_ref']);require(band['status']=='BLOCK_PREPARED_NOT_SOLVED','FROZEN_BLOCK_HAS_KNOWN_PATH_CONFLICT')
        inputs=read(req['solver_input_ref']);frames=read(inputs['current_frames_ref']);bindings=read(inputs['source_bindings_ref'])
        original=read(req['trust_origin_ref']);geometry=read(req['body_geometry_ref']);triangles=read(req['body_triangles_ref'])
        recipe=read(req['recipe_ref']);reserve=recipe['colliders'][req['collider_index']]['outer_thickness_cm'];piece=band['piece']
        require(frames[piece]==band['original_full_cage'],'BAND_SOURCE_CHANGED')
        for path,h in band['artifacts'].items():require(sha(path)==h,'BAND_PROVENANCE_CHANGED')
        for module in (solve_piece_metric,solve_piece_contact):artifacts[module.__file__]=sha(module.__file__)
        candidate, receipt=solve(band['sub_cage'],band['fixed_local_indices'],req['solver_settings'],out)
        report['metric_solve']=receipt;budget.check()
        result=copy.deepcopy(frames)
        for i,p in zip(band['global_control_indices'],candidate['target_cm']):result[piece]['target_cm'][i]=p
        report['candidate_sha256']=save('candidate-cages.json',result)
        xyz=np.asarray(result[piece]['target_cm']);report['whole_piece_metric']=metric(result[piece])
        require(all(result[piece][k]==original[piece][k] for k in ('uv_cm','triangles')),'TRUST_ORIGIN_SOURCE_MISMATCH')
        report['max_displacement_from_original_cm']=float(np.linalg.norm(xyz-np.asarray(original[piece]['target_cm']),axis=1).max())
        gaps=[math.dist(evaluate(row['partner']['support'],result[piece]),evaluate(row['driver']['support'],result[row['driver']['piece']]))
            for row in bindings['bindings'] if row['partner']['piece']==piece]
        report['sewing_bindings']={'count':len(gaps),'maximum_gap_cm':max(gaps)}
        sys.path.insert(0,req['source_root']);import a3d.contact_geometry as kernel
        artifacts[kernel.__file__]=sha(kernel.__file__)
        body=Body(geometry,triangles if isinstance(triangles,list) else triangles['triangles'],kernel,budget)
        audit=body.audit(result[piece],xyz,reserve);report['contacts']=contact_summary(audit,reserve)
        report['contact_sha256']=save('contacts.json',audit);budget.check()
        report.update(status='LOCAL_BAND_EVALUATED_NOT_ADMITTED',piece=piece,
            source_uv_and_topology_unchanged=True,other_pieces_unchanged=all(result[k]==frames[k] for k in frames if k!=piece),
            physical_reserve_cm=reserve,max_displacement_cm=req['max_displacement_cm'],
            self_contacts='NOT_ASSESSED',global_inside_outside='NOT_ASSESSED',cloth_and_fitting='NOT_EXECUTED')
    except Exception as error:report.update(status='REFUSED_OR_INCOMPLETE',reason=str(error))
    finally:
        report.update(artifacts=artifacts,request_sha256=sha(rp),helper_sha256=sha(__file__),elapsed_seconds=budget.elapsed)
        save('report.json',report)
        print(json.dumps({k:v for k,v in report.items() if k not in ('artifacts','metric_solve')}))


if __name__=='__main__':main()
