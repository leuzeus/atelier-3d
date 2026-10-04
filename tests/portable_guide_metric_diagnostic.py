"""Run only the pure metric kernel on an exact refused native preparation."""
import argparse
import json
from pathlib import Path
import sys

ROOT=Path(__file__).resolve().parents[1];sys.path.insert(0,str(ROOT))
from a3d.core import StudioError,atomic_json,digest,inside,read_json,sha
from a3d.cloth_metrics import validate_metrics
from a3d.pattern_preparation import assess_preparation
import copy
from a3d.guide_metric_solver import recover_guide_metric
from a3d.pattern_assembly import preform_coordinates


parser=argparse.ArgumentParser()
for name in ('project','request','previous-result','component','output'):parser.add_argument('--'+name,required=True)
parser.add_argument('--seconds',type=float,default=60.)
parser.add_argument('--cg-iterations',type=int,default=60)
parser.add_argument('--cg-tolerance',type=float,default=1e-5)
parser.add_argument('--assess-candidate',help='Reassess one exact prior candidate under its actual source preparation limits')
args=parser.parse_args();project=Path(args.project).resolve();output=inside(project,args.output,False)
if output.exists():raise StudioError('Metric diagnostic identity already exists')
def verified(ref):
    path=inside(project,ref['path'])
    if sha(path)!=ref['sha256']:raise StudioError('Metric diagnostic source reference changed')
    return read_json(path)
request_path=inside(project,args.request);request=read_json(request_path)
templates=verified(request['templates_ref']);inputs=templates['compiler_inputs']
spec=verified(inputs['production_spec_ref']);guides=verified(inputs['guides_ref'])
prior_path=inside(project,args.previous_result);prior=read_json(prior_path)
receipt_ref=prior['preparation_runs'][args.component]['units'][0]['attempts'][-1]['receipt']
previous=verified(receipt_ref)['result'];payload=verified(previous['derived_mesh']);plan=verified(previous['assembly_plan'])
plan['preform']['panels']=guides[args.component]['panels']
try:coordinates,_=preform_coordinates(payload,plan)
except StudioError as error:
    if not hasattr(error,'preform_coordinates_cm'):raise
    coordinates=error.preform_coordinates_cm
semantics=spec['piece_semantics'];pieces=[pid for pid in payload['panels'] if semantics[pid]['role']in ('front','back')]
stops=[{'piece':pid,'edge':semantics[pid]['guide_edges']['shoulder']} for pid in pieces]
if args.assess_candidate:
    candidate_path=inside(project,args.assess_candidate);candidate=read_json(candidate_path)
    if (candidate['source_payload_sha256']!=digest(payload) or candidate['initial_candidate_sha256']!=digest(coordinates)
            or candidate['candidate_sha256']!=digest(candidate['coordinates_cm'])):
        raise StudioError('Metric assessment requires the exact source payload, original guide and computed candidate')
    recipe=verified(previous['recipe']);assessed=copy.deepcopy(payload);assessed['placed_cm']=candidate['coordinates_cm']
    assessment=assess_preparation(assessed,recipe,plan,source_audit=previous['source_audit'])
    quality=assessment['effective_quality_limits'];error=None
    try:metric=validate_metrics(payload,candidate['coordinates_cm'],quality,include_faces=False,include_bending=False)
    except StudioError as exc:error=str(exc);metric=exc.quality_metrics
    result={'version':1,'status':'SOURCE_METRIC_VALID' if error is None else 'NEEDS_CORRECTION',
        'stop_reason':'EXACT_SOURCE_PREPARATION_ASSESSMENT','metric':metric,'quality':quality,
        'recipe_ref':previous['recipe'],'plan_ref':previous['assembly_plan'],
        'candidate_ref':{'path':args.assess_candidate,'sha256':sha(candidate_path)},
        'candidate_sha256':candidate['candidate_sha256'],'original_candidate_status':candidate['status'],
        'original_candidate_policy':candidate['policy'],'metric_error':error,
        'preparation_assessment':{k:assessment[k] for k in ('status','effective_quality_limits','reasons')},
        'qualification':'NONE','contacts':'NOT_ASSESSED','simulation':'NOT_EXECUTED',
        'fitting':'NOT_EXECUTED','accepted':False}
else:
    quality=templates['components'][args.component]['preparation_template']['placement_correction']['quality']
    quality={**quality,'min_angle_degrees':templates['components'][args.component]['preparation_template']['regular_mesh']['target_min_angle_degrees']}
    result=recover_guide_metric(payload,coordinates,quality,pieces,stops,max_iterations=100,
        max_seconds=args.seconds,max_displacement_cm=8.,max_step_cm=.5,cg_iterations=args.cg_iterations,
        cg_tolerance=args.cg_tolerance)
result['inputs']={'request_ref':{'path':args.request,'sha256':sha(request_path)},
    'previous_result_ref':{'path':args.previous_result,'sha256':sha(prior_path)},
    'native_previous_receipt_ref':receipt_ref,'derived_mesh_ref':previous['derived_mesh'],
    'guides_ref':inputs['guides_ref'],'production_spec_ref':inputs['production_spec_ref'],
    'body_ref':spec['body_ref'],'code_sha256':sha(ROOT/'a3d/guide_metric_solver.py')}
atomic_json(output,result)
print(json.dumps({**{k:result[k] for k in ('status','stop_reason','iterations','elapsed_seconds','max_displacement_cm','energy') if k in result},
    'min_principal_stretch':result['metric']['min_principal_stretch'],
    'max_principal_stretch':result['metric']['max_principal_stretch'],
    'min_angle_degrees':result['metric']['min_angle_degrees'],
    'output_ref':{'path':args.output,'sha256':sha(output)}}))
