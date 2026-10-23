"""Bounded, data-driven rigid proposals from authenticated sewing supports.

This is an experiment, never admission. The driver stays unchanged. Rank
ambiguity is refused by the existing product kernel, without a roll fallback.
Every proposed partner is audited against the complete recorded body surface.
"""
import argparse
import copy
import json
import math
from pathlib import Path
import sys
import numpy as np

from solve_piece_metric import metric
from solve_piece_contact import Budget, Body, contact_summary, require, sha
import solve_piece_metric
import solve_piece_contact


def evaluate(support, cage):
    indices, weights = support['control_indices'], support['weights']
    require(len(indices) == len(weights) == 3, 'TRIANGLE_SUPPORT_REQUIRED')
    require(math.isclose(math.fsum(weights), 1., abs_tol=1e-12), 'INVALID_SUPPORT_SUM')
    return [math.fsum(w*cage['target_cm'][i][k] for i,w in zip(indices,weights)) for k in range(3)]


def rows_for_piece(bindings, frames, piece):
    groups = {}
    for binding in bindings:
        if binding['partner']['piece'] == piece:
            groups.setdefault(binding['source_seam_id'], []).append(binding)
    rows=[]
    for sid, members in sorted(groups.items()):
        members=sorted(members,key=lambda row: row['partner']['common_fraction'])
        fractions=[row['partner']['common_fraction'] for row in members]
        require(fractions[0]==0. and fractions[-1]==1., 'INCOMPLETE_SOURCE_PARTITION')
        require(all(a < b for a,b in zip(fractions,fractions[1:])), 'NONINCREASING_SOURCE_PARTITION')
        for i,row in enumerate(members):
            a=fractions[i-1] if i else fractions[i]
            b=fractions[i+1] if i+1<len(fractions) else fractions[i]
            weight=(b-a)*row['partner']['source_edge_length_cm']/2
            points=[evaluate(row[side]['support'],frames[row[side]['piece']]) for side in ('partner','driver')]
            for side, point in zip(('partner','driver'),points):
                require(math.dist(point,row[side]['support']['evaluated_world_cm']) < 1e-10, 'STALE_SUPPORT_VALUE')
            rows.append({'source_point_cm':points[0],'target_point_cm':points[1],
                'weight':weight,'source_seam_id':sid,'binding_id':row['binding_id']})
    return rows


def main():
    ap=argparse.ArgumentParser(); ap.add_argument('--request',required=True)
    request_path=Path(ap.parse_args().request); request=json.loads(request_path.read_text(encoding='utf-8'))
    out=Path(request['output_directory']); out.mkdir(exist_ok=False)
    budget=Budget(request['settings']); budget.limits={'max_controls':request['settings']['max_controls']}
    artifacts={}; report={'status':'INCOMPLETE','qualification':'NONE','pieces':{},'artifacts':artifacts}
    def read(ref):
        require(sha(ref['path'])==ref['sha256'],'STALE_INPUT:'+ref['path'])
        artifacts[ref['path']]=ref['sha256']; budget.check()
        return json.loads(Path(ref['path']).read_text(encoding='utf-8'))
    def save(name,data):
        p=out/name; p.write_text(json.dumps(data,separators=(',',':'),allow_nan=False),encoding='utf-8'); return sha(p)
    try:
        inputs=read(request['solver_input_ref']); frames=read(inputs['current_frames_ref'])
        bindings=read(inputs['source_bindings_ref']); original=read(request['trust_origin_ref'])
        geometry=read(request['body_geometry_ref']); raw=read(request['body_triangles_ref'])
        recipe=read(request['recipe_ref']); reserve=recipe['colliders'][request['collider_index']]['outer_thickness_cm']
        sys.path.insert(0,request['source_root'])
        from a3d.rigid_guide_alignment import proper_rigid_fit, transform
        import a3d.rigid_guide_alignment as rigid_kernel
        import a3d.contact_geometry as contact_kernel
        for module in (rigid_kernel,contact_kernel,solve_piece_metric,solve_piece_contact): artifacts[module.__file__]=sha(module.__file__)
        body=Body(geometry, raw if isinstance(raw,list) else raw['triangles'],contact_kernel,budget)
        result=copy.deepcopy(frames); driver=bindings['driver_piece']
        partners=sorted(set(row['partner']['piece'] for row in bindings['bindings']))
        for piece in partners:
            budget.check(); cage=frames[piece]
            require(all(cage[k]==original[piece][k] for k in ('uv_cm','triangles')), 'TRUST_ORIGIN_SOURCE_MISMATCH')
            require(not any(row['piece']==piece for row in inputs['fixed_anatomical_attachments']), 'FIXED_PARTNER_NOT_SUPPORTED')
            rows=rows_for_piece(bindings['bindings'],frames,piece); fit=proper_rigid_fit(rows,budget)
            observed={'fit':fit,'initial_metric':metric(cage)}; report['pieces'][piece]=observed
            if fit['status']!='RIGID_SEED_PROPOSED': continue
            xyz=np.asarray([transform(fit,p) for p in cage['target_cm']])
            budget.check()
            result[piece]['target_cm']=xyz.tolist()
            observed['metric']=metric(cage,xyz)
            budget.check()
            observed['max_displacement_from_original_cm']=float(np.linalg.norm(xyz-np.asarray(original[piece]['target_cm']),axis=1).max())
            observed['within_trust_budget']=observed['max_displacement_from_original_cm']<=request['max_displacement_cm']
            audit=body.audit(cage,xyz,reserve)
            observed['contacts']=contact_summary(audit,reserve)
            observed['contact_audit_sha256']=save(piece+'-contacts.json',audit)
            # Saved even when the proposal fails contacts or the original trust limit.
            save('candidate-cages.json',result)
        require(result[driver]==frames[driver], 'DRIVER_CHANGED')
        candidate_sha=save('candidate-cages.json',result)
        budget.check()
        report.update(status='EXPLORATORY_RIGID_PROPOSALS_EVALUATED',
            driver_unchanged=True, source_uv_and_topology_unchanged=True,
            fixed_attachments_unchanged=True, physical_reserve_cm=reserve,
            max_displacement_cm=request['max_displacement_cm'],
            candidate_sha256=candidate_sha,
            scope='PARTNER_RIGID_PROPOSALS_ONLY; SEAMS_AND_GLOBAL_ASSEMBLY_NOT_ADMITTED',
            self_contacts='NOT_ASSESSED',global_inside_outside='NOT_ASSESSED',cloth_and_fitting='NOT_EXECUTED')
    except Exception as error:
        report.update(status='REFUSED_OR_INCOMPLETE',reason=str(error))
    finally:
        report.update(elapsed_seconds=budget.elapsed,work=dict(budget.counts),helper_sha256=sha(__file__),request_sha256=sha(request_path))
        save('report.json',report)
        print(json.dumps({k:v for k,v in report.items() if k!='artifacts'}))


if __name__=='__main__': main()
