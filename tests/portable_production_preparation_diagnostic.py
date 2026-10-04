"""Compile a new immutable guide proposal and compare source-bound preparations.

No Blender, canonical mutation, Cloth, body modification or acceptance is run.
The prior triangulation stays an observation source, never a new qualification.
"""
import argparse
import copy
import json
import math
from pathlib import Path
import sys
import zipfile

ROOT=Path(__file__).resolve().parents[1]
sys.path.insert(0,str(ROOT))
from a3d.core import StudioError,atomic_json,digest,inside,read_json,sha
from a3d.cloth_metrics import evaluate_metrics
from a3d.garment_guides import garment_volume_frames
from a3d.pattern_assembly import preform_coordinates
from a3d.pattern_preparation import prepare_regular_boundaries
from a3d.textile_executor import prepare_component_templates
from a3d.production_dossier import compile_project_dossier
from a3d.garment_planner import plan_assembly
from types import SimpleNamespace


def main():
    parser=argparse.ArgumentParser()
    parser.add_argument('--project',required=True)
    parser.add_argument('--request',required=True)
    parser.add_argument('--previous-result',required=True)
    parser.add_argument('--skin-sections',required=True)
    parser.add_argument('--suffix',required=True)
    parser.add_argument('--production-spec',help='Separate explicit semantic proposal; originals remain unchanged')
    parser.add_argument('--resume-exact',action='store_true')
    args=parser.parse_args();project=Path(args.project).resolve()
    if not args.suffix.isalnum():raise StudioError('Diagnostic suffix must be an alphanumeric identity')
    outputs={name:inside(project,'preparation/'+filename,False) for name,filename in {
        'guides':'source-guide-proposals-'+args.suffix+'.json',
        'templates':'component-preparation-templates-'+args.suffix+'.json',
        'request':'native-source-request-'+args.suffix+'.json',
        'execution_request':'native-source-execution-request-'+args.suffix+'.json',
        'diagnostic':'source-preparation-diagnostic-'+args.suffix+'.json'}.items()}
    if args.production_spec:
        outputs.update({name:inside(project,'preparation/'+filename,False) for name,filename in {
            'compiled':'compiled-production-dossier-'+args.suffix+'.json',
            'assembly':'assembly-plan-proposal-'+args.suffix+'.json'}.items()})
    if any(path.exists() for path in outputs.values()) and not args.resume_exact:
        raise StudioError('Diagnostic output identity already exists; explicit exact recovery is required')
    def persist(path,value):
        if path.exists():
            if read_json(path)!=value:raise StudioError('Existing diagnostic artifact differs from exact reconstruction')
        else:atomic_json(path,value)
    def reference(path):return {'path':path.relative_to(project).as_posix(),'sha256':sha(path)}
    def verified(ref):
        path=inside(project,ref['path'])
        if sha(path)!=ref['sha256']:raise StudioError('Diagnostic source reference changed: '+ref['path'])
        return read_json(path)
    request_path=inside(project,args.request);request=read_json(request_path)
    stored=verified(request['templates_ref']);inputs=copy.deepcopy(stored['compiler_inputs'])
    if args.production_spec:
        spec_path=inside(project,args.production_spec);inputs['production_spec_ref']=reference(spec_path)
        compiled=compile_project_dossier(SimpleNamespace(root=project),inputs['dossier_ref']['path'],args.production_spec)
        if compiled['status']!='READY_TO_PLAN':raise StudioError('Separate semantic proposal still has missing production metadata')
        persist(outputs['compiled'],compiled)
        assembly=plan_assembly(compiled['assembly_spec'],capabilities=['coupled_multilayer'])
        persist(outputs['assembly'],assembly);inputs['assembly_plan_ref']=reference(outputs['assembly'])
    spec=verified(inputs['production_spec_ref']);profile=verified(spec['body_ref'])
    dossier=verified(inputs['dossier_ref']);standard=verified(inputs['standard_recipe_ref'])
    assembly=verified(inputs['assembly_plan_ref']);skin_path=inside(project,args.skin_sections)
    skin=read_json(skin_path);sources={};guides={}
    for item in spec['packages']:
        path=inside(project,item['source_ref']['path'])
        if sha(path)!=item['source_ref']['sha256']:raise StudioError('Approved diagnostic package changed')
        with zipfile.ZipFile(path) as archive:data=json.loads(archive.read('garment.json'))
        cid=item['component_id'];sources[cid]={'source_ref':item['source_ref'],'data':data}
        guides[cid]=garment_volume_frames(data,{pid:spec['piece_semantics'][pid] for pid in data['pieces']},
            profile,skin_sections=skin)
    if any(g['status']!='GARMENT_GUIDES_PREPARED' for g in guides.values()):
        raise StudioError('New proposal still has missing source-bound guides')
    # The proposed outputs are separate immutable inputs. No existing pointer,
    # source recipe, package, measured body or canonical state is overwritten.
    persist(outputs['guides'],guides);inputs['guides_ref']=reference(outputs['guides'])
    templates=prepare_component_templates(assembly,sources,guides,standard,dossier,inputs['dossier_ref'],inputs)
    persist(outputs['templates'],templates)
    new_request=copy.deepcopy(request);new_request['templates_ref']=reference(outputs['templates'])
    new_request['output_directory']='preparation/native-source-'+args.suffix
    new_request['execution_status']='SCHEDULED_NOT_EXECUTED'
    new_request['execute_preparation']=False;new_request['execute_textile']=False
    persist(outputs['request'],new_request)
    executable=copy.deepcopy(new_request);executable['execute_preparation']=True
    persist(outputs['execution_request'],executable)
    prior_path=inside(project,args.previous_result);prior=read_json(prior_path)
    diagnostic={'version':1,'status':'PORTABLE_SOURCE_PREPARATION_DIAGNOSTIC',
        'previous_result_ref':reference(prior_path),'request_ref':reference(request_path),
        'skin_sections_ref':reference(skin_path),'body_ref':spec['body_ref'],
        'new_request_ref':reference(outputs['request']),'components':{},
        'qualification':'NONE','simulation':'NOT_EXECUTED','accepted':False,
        'native_contact_replay':'REQUIRED','fit_and_ease_assessment':'REQUIRED_SEPARATELY',
        'code_refs':{name:sha(ROOT/name) for name in ('a3d/sewing.py','a3d/pattern_preparation.py',
            'a3d/torso_sections.py','a3d/garment_guides.py','a3d/textile_executor.py')}}
    for cid,source in sources.items():
        row=templates['components'][cid]
        boundaries,seams,sampling=prepare_regular_boundaries(source['data'],row['recipe_template'],
            row['preparation_template']['regular_mesh'],dossier)
        unit=prior['preparation_runs'][cid]['units'][0]
        receipt_ref=unit['attempts'][-1]['receipt'];result=verified(receipt_ref)['result']
        payload=verified(result['derived_mesh']);plan=verified(result['assembly_plan'])
        source_before=digest(payload);old=copy.deepcopy(plan);new=copy.deepcopy(plan)
        new['preform']['panels']=guides[cid]['panels'];comparisons={}
        for label,candidate in (('previous_guide',old),('new_guide',new)):
            refusal=None
            try:coords,_=preform_coordinates(payload,candidate)
            except StudioError as error:
                if not hasattr(error,'preform_coordinates_cm'):raise
                coords=error.preform_coordinates_cm;refusal=str(error)
            metrics=evaluate_metrics(payload,coords,include_faces=True,include_bending=False)
            pieces={}
            for pid in payload['panels']:
                faces=[face for face in metrics['face_metrics'] if face['piece']==pid]
                principal=[face['principal_stretch'] for face in faces if face['principal_stretch'] is not None]
                pieces[pid]={'faces':len(faces),'source_area_cm2':sum(f['source_area_cm2'] for f in faces),
                    'placed_area_cm2':sum(f['placed_area_cm2'] for f in faces),
                    'source_min_angle_degrees':min(f['source_min_angle_degrees'] for f in faces),
                    'placed_min_angle_degrees':min(f['placed_min_angle_degrees'] for f in faces),
                    'min_principal_stretch':min(p[0] for p in principal),
                    'max_principal_stretch':max(p[1] for p in principal)}
            comparisons[label]={'refusal':refusal,'piece_metrics':pieces,
                **{k:metrics[k] for k in ('min_principal_stretch','max_principal_stretch','min_angle_degrees','extrema')}}
        if digest(payload)!=source_before:raise StudioError('Diagnostic changed the historical derived source map')
        diagnostic['components'][cid]={'package_ref':source['source_ref'],'native_previous_receipt_ref':receipt_ref,
            'previous_derived_mesh_ref':result['derived_mesh'],'historical_native_readiness':result['readiness'],
            'topology_scope':'PREVIOUS_NATIVE_TRIANGULATION_NEW_GUIDE_ONLY',
            'comparisons':comparisons,'new_boundary_min_edge_cm':{pid:min(math.dist(a,b)
                for a,b in zip(panel['polygon'],panel['polygon'][1:]+panel['polygon'][:1]))
                for pid,panel in boundaries.items()},'boundary_sampling_policy':sampling['boundary_sampling_policy'],
            'source_polygon_immutable':True,'body_immutable':True,
            'source_preform_budget_cm':row['preparation_template']['source_preform_budget']['max_displacement_cm'],
            'physical_max_displacement_cm':row['plan_fields']['assembly']['max_displacement_cm'],
            'placement_correction_max_displacement_cm':row['preparation_template']['placement_correction']['budgets']['max_displacement_cm']}
    persist(outputs['diagnostic'],diagnostic)
    print(json.dumps({'status':diagnostic['status'],'outputs':{key:reference(path) for key,path in outputs.items()},
        'pieces':sum(len(s['data']['pieces']) for s in sources.values()),'qualification':'NONE'}))


if __name__=='__main__':main()
