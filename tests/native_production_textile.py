"""Coordinator-run source preparation/garment driver for an isolated project.

Set A3D_PRODUCTION_PROJECT and A3D_PRODUCTION_REQUEST (a project-relative JSON
path). The request supplies exact references and explicit execution booleans.
The body is introduced separately from its immutable approved native artifact.
Every scene mutation uses dispatch_current and its persistent run admission.
For a production MCP session, present each prepared operation for authorization
instead of using this isolated CLI driver as a permission substitute.
"""
import importlib
import os
from pathlib import Path
import sys

ROOT=Path(__file__).resolve().parents[1]
sys.path.insert(0,str(ROOT))


def execute_registered_run(project,specification_path):
    from a3d.core import StudioError
    from blender.bootstrap import dispatch_current
    runs=importlib.import_module('a3d.runs')
    run=runs.create_run(project,'garment',specification_path)
    while True:
        runs=importlib.import_module('a3d.runs')
        step=runs.next_run_step(project,run['run_id'])
        if step['status']=='COMPLETED':break
        if step['status']!='AWAITING_CONFIRMATION':
            return runs.run_status(project,run['run_id'])
        if step.get('executor') not in (None,'blender'):
            raise StudioError('Native garment driver cannot execute an external-provider job')
        # Arguments are the exact operation selected and persisted by the run.
        dispatch_current(str(project.root),step['operation'],step['arguments'])
    return importlib.import_module('a3d.runs').run_status(project,run['run_id'])


def main():
    import bpy
    from a3d.core import StudioError,atomic_json,contract,digest,inside,read_json,sha
    from a3d.store import Project
    from a3d.textile_executor import compile_textile_program,require_textile_program_admission
    from blender.textile_executor import bind_component_preparations,verified,reference
    project=Project(os.environ['A3D_PRODUCTION_PROJECT'])
    if not bpy.app.background:
        raise StudioError('Development textile driver requires an isolated background Blender')
    session=read_json(inside(project.root,'.a3d/blender/session.json'))
    working=Path(session['working']).resolve(strict=True)
    if not working.is_relative_to(project.data/'blender'):
        raise StudioError('Textile working scene is outside the isolated project')
    bpy.ops.wm.open_mainfile(filepath=str(working),load_ui=False)
    request_path=inside(project.root,os.environ['A3D_PRODUCTION_REQUEST']);request=read_json(request_path)
    templates_ref=request['templates_ref'];verified(project,templates_ref)
    assembly=verified(project,request['assembly_plan_ref'])
    binding=bind_component_preparations(project,templates_ref['path'],request['body_object'],
        request['body_geometry_ref'],request['output_directory'],request.get('envelope_review'))
    output=inside(project.root,request['output_directory'])
    result={'version':1,'status':'NATIVE_INPUTS_PREPARED','request':reference(project,request_path),
        'binding':binding,'qualification':'NONE','simulation':'NOT_EXECUTED','accepted':False}
    atomic_json(output/'driver-result.json',result)
    if not request.get('execute_preparation',False):return result
    if binding.get('component_run_specifications'):
        statuses={cid:execute_registered_run(project,ref['path']) for cid,ref in sorted(binding['component_run_specifications'].items())}
        result['preparation_runs']=statuses
        units=[unit for status in statuses.values() for unit in status['units']]
        complete=all(status['status']=='COMPLETED' for status in statuses.values())
    else:
        status=execute_registered_run(project,binding['run_specification']['path']);result['preparation_run']=status
        units=status['units'];complete=status['status']=='COMPLETED'
    if not complete:
        result['status']='PREPARATION_REQUIRES_CORRECTION';atomic_json(output/'driver-result.json',result);return result
    components=[];payloads={};recipes={};plans={}
    # Use the actual full native result stored by the canonical journal. The
    # conversational compact reply has no authority over downstream bindings.
    for unit in units:
        receipt=verified(project,unit['attempts'][-1]['receipt']);record=receipt['result'];cid=record['component_id']
        if record.get('readiness')!='READY' or record.get('accepted') is not False:
            raise StudioError('A completed preparation unit is not the exact unaccepted READY native candidate')
        package=project.state()['components'][cid]['package']
        components.append({'component_id':cid,'package_ref':{k:package[k] for k in ('path','sha256')},
            'derived_mesh_ref':record['derived_mesh'],'recipe_ref':record['recipe'],'plan_ref':record['assembly_plan']})
        payloads[cid]=verified(project,record['derived_mesh']);recipes[cid]=verified(project,record['recipe'])
        plans[cid]=verified(project,record['assembly_plan'])
    program_file=output/'program.json'
    program={'version':1,'purpose':'GARMENT_CANDIDATE','id':'main-textile-'+digest(components)[:16],'asset_id':project.state()['asset']['id'],
        'program_path':program_file.relative_to(project.root).as_posix(),'assembly_plan_ref':request['assembly_plan_ref'],
        'components':sorted(components,key=lambda row:row['component_id']),
        'run_budgets':{'max_attempts':2,'max_seconds':3600},
        'experimental_coupled_multilayer':request.get('experimental_coupled_multilayer',False),
        'frozen_collider_policy':request['frozen_collider_policy']}
    if request.get('fit_context'):program['fit_context']=request['fit_context']
    contract('textile-program',program);atomic_json(program_file,program)
    compiled=compile_textile_program(assembly,program,payloads,recipes,plans)
    atomic_json(output/'compiled-program.json',compiled)
    run_file=output/'textile-run.json';atomic_json(run_file,compiled['run_spec'])
    result.update(status='TEXTILE_PROGRAM_PREPARED',program=reference(project,program_file),
                  run_specification=reference(project,run_file),diagnostics=compiled['diagnostics'])
    try:result['textile_admission']=require_textile_program_admission(project,program,assembly)
    except StudioError as error:
        result.update(status='TEXTILE_PROGRAM_NEEDS_DATA',textile_admission={'status':'NEEDS_DATA','message':str(error)},simulation='NOT_EXECUTED')
        atomic_json(output/'driver-result.json',result);return result
    atomic_json(output/'driver-result.json',result)
    if request.get('execute_textile',False):
        if compiled['diagnostics']:raise StudioError('The native coupled-layer capability remains unqualified for execution')
        result['textile_run']=execute_registered_run(project,run_file.relative_to(project.root).as_posix())
        result['status']='TEXTILE_STAGE_RUN_'+result['textile_run']['status']
        result['simulation']='GROUP_EVIDENCE_ONLY_SEE_NATIVE_RECEIPTS';atomic_json(output/'driver-result.json',result)
    return result


if __name__=='__main__':
    result=main()
    print('NATIVE_PRODUCTION_TEXTILE_STATUS='+result['status'],flush=True)
