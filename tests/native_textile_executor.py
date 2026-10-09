"""Isolated native group mechanics, never a garment or fitting acceptance.

The parent coordinator runs this through run_pattern_validation.py. Every
production stage uses the guarded dispatcher on a synthetic approved project.
"""
import copy
import importlib
import os
from pathlib import Path
import sys
from unittest.mock import patch

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))
import bpy
from a3d.core import StudioError, atomic_json, digest, read_json, sha
from a3d.garment_planner import plan_assembly
from a3d.packages import extract_package
from a3d.pattern_assembly import map_digest
from blender.operations import dispatch
from blender.sewing import collider_info
from blender.textile_executor import current_group, program_directory
import tests.support as support
from tests.textile_fixtures import source,annotate_dossier

OUT = Path(os.environ['A3D_VALIDATION_OUTPUT'])
ORIGINAL_SOURCE = support.garment_source
ORIGINAL_DOSSIER = support.construction_dossier


def dossier(project, garment=False):
    file = project.data/'source/package/garment.json'; data = read_json(file)
    atomic_json(file, {'seams': []})
    try: result = ORIGINAL_DOSSIER(project, garment)
    finally: atomic_json(file, data)
    return annotate_dossier(result,data)


def run(case):
    bpy.ops.wm.read_factory_settings(use_empty=True)
    bpy.context.preferences.filepaths.temporary_directory = str(OUT/'tmp')
    bpy.context.preferences.filepaths.save_version = 0
    support.garment_source = lambda path: source(path, case)
    support.construction_dossier = dossier
    try: project = support.ready_project(OUT/case, True)
    finally:
        support.garment_source = ORIGINAL_SOURCE; support.construction_dossier = ORIGINAL_DOSSIER
    original = OUT/(case+'-original.blend'); bpy.ops.wm.save_as_mainfile(filepath=str(original)); original_sha = sha(original)
    dispatch(str(project.root), 'prepare', {})
    bpy.ops.mesh.primitive_cube_add(size=.1, location=(.01, .10, .24))
    body = bpy.context.object; body.name = 'SYNTHETIC_UNCHANGED_BODY_OBSTACLE'
    body_name = body.name
    body.modifiers.new('Collision', 'COLLISION')
    body.collision.thickness_outer = .001; body.collision.thickness_inner = .001
    body_info = collider_info(body)
    recipe = read_json(ROOT/'templates/sewing-recipe.json'); data = read_json(project.data/'source/package/garment.json')
    recipe['mesh']['spacing_cm'] = 1
    recipe['seams'] = {s['id']: {'kind': s['kind'], 'ease_b_over_a': 0, 'tolerance_relative': .01} for s in data['seams']}
    recipe['placements'] = {}; frames = {}
    for pid in data['pieces']:
        origin = [2.1 if case == 'coupled' and pid == 'outer' else 0, -3 if case == 'ordered' and pid == 'outer' else -2, 20]
        recipe['placements'][pid] = {'mode': 'flat', 'position_cm': origin, 'rotation_degrees': [90,0,0], 'radius_cm': 10, 'origin_2d_cm': [0,0]}
        frames[pid] = {'source_ref': 'synthetic:known-coupon-frame:'+pid, 'origin_cm': origin,
                      'u_axis': [1,0,0], 'v_axis': [0,0,1], 'offset_uv_cm': [0,0]}
    recipe['trial_pieces'] = list(data['pieces']); recipe['pins'] = []
    if case == 'belt': recipe['trial_mode'] = 'single_panel'
    elif case == 'ordered': recipe['trial_mode'] = 'seam_free'
    recipe['colliders'] = [{**{k:body_info[k] for k in ('object','dimensions_cm','geometry_sha256','outer_thickness_cm','inner_thickness_cm')},
                            'role':'mannequin','tolerance_cm':.01}]
    recipe['physics_purpose']='TEST_ONLY'
    recipe['no_collision_reason'] = ''
    for phase in recipe['phases'].values():
        phase.update(frames=12, gravity_m_s2=[0,0,-2], self_collision=True, collision_distance_cm=.3, self_distance_cm=.3)
    atomic_json(project.root/'recipe.json', recipe)
    package = project.state()['components']['garment.coat']['package']
    extracted = project.data/'reconstruction/extracted'; extract_package(project.root/package['path'], extracted)
    created = dispatch(str(project.root), 'garment', {'package_dir': extracted.relative_to(project.root).as_posix(), 'recipe_path': 'recipe.json'})
    payload = read_json(project.root/created['derived_mesh'])
    quality = {k:v for k,v in recipe['mesh'].items() if k not in ('spacing_cm','max_boundary_error_cm','max_vertices')}
    plan = {'version':1,'component_id':'garment.coat','source_refs':['synthetic:'+case], 'mapping_sha256':map_digest(payload),
        'preform':{'panels':frames},'assembly':{'max_initial_gap_cm':.5,'max_displacement_cm':3,'max_step_cm':.05,
            'iterations':40,'neighborhood_rings':2,'closure_support_release':1},
        'consolidation':{'weld_gap_cm':.05},'quality':quality,'cloth':{'mount_release_steps':[0.,1.]},
        'supports':{'temporary':[],'drape':[{'id':'top-'+pid,'piece':pid,'edge':'top','weight':.7,'source_ref':'synthetic:coupon-support'} for pid in data['pieces']], 'functional':[]},
        'collision':{'required':True,'clearance_cm':.1,'source_ref':'synthetic:fixed-body-obstacle'}}
    atomic_json(project.root/'plan.json', plan)
    def ref(path): return {'path':path.relative_to(project.root).as_posix(),'sha256':sha(path)}
    source_ref = ref(project.root/'recipe.json'); body_ref = source_ref
    pieces = [{'id':pid,'component_id':'garment.coat','role':'belt' if pid=='belt' else 'lining','side':'center',
        'layer':pid if case!='belt' else 'cloth','edges':sorted(panel['edges']), 'source_ref':source_ref} for pid,panel in data['pieces'].items()]
    layers = [{'id':'body','kind':'body','panels':[],'colliders':[body.name],'source_ref':body_ref}]
    layers.extend({'id':p['layer'],'kind':'garment','panels':[p['id']],'colliders':[],'source_ref':source_ref} for p in pieces)
    links = [{**{k:s[k] for k in ('piece_a','piece_b','edge_a','edge_b','kind')}, 'id':'garment.coat::'+s['id'],'source_ref':source_ref} for s in data['seams']]
    assembly = plan_assembly({'version':1,'source_ref':source_ref,'body_ref':body_ref,'pieces':pieces,'links':links,
        'layers':{'version':1,'source_ref':source_ref,'mode':'ordered','interaction':'one_way_declared','nodes':layers,
                  'inside_to_outside':[['body',p['layer']] for p in pieces]+([['inner','outer']] if case!='belt' else [])},
        'budgets':{'max_frames':120,'max_iterations':100,'max_seconds':120,'max_displacement_cm':3,'max_strain_relative':.25}},
        capabilities=['coupled_multilayer'] if case=='coupled' else [])
    atomic_json(project.root/'assembly.json', assembly)
    program = {'version':1,'purpose':'TEST_ONLY','id':'native-textile-'+case,'asset_id':'test-character','program_path':'program.json',
        'assembly_plan_ref':ref(project.root/'assembly.json'),'components':[{'component_id':'garment.coat',
            'package_ref':{k:package[k] for k in ('path','sha256')},'derived_mesh_ref':ref(project.root/created['derived_mesh']),
            'recipe_ref':ref(project.root/'recipe.json'),'plan_ref':ref(project.root/'plan.json')}],
        'run_budgets':{'max_attempts':2,'max_seconds':1200},'experimental_coupled_multilayer':case=='coupled',
        'frozen_collider_policy':{'outer_thickness_cm':.3,'inner_thickness_cm':.3,'tolerance_cm':.001,'outward_normal_sign':1}}
    atomic_json(project.root/'program.json', program)
    # Actual native entry functions must reject an unlabeled production fit
    # attempt before creating any group/collider copies or stage artifacts.
    from blender.textile_executor import advance_textile_program,prepare_group_bundle
    from blender.textile_group import transition_textile_group
    missing=copy.deepcopy(program);missing.update(purpose='GARMENT_CANDIDATE',program_path='missing-fit.json')
    atomic_json(project.root/'missing-fit.json',missing)
    before_objects=sorted(obj.name for obj in bpy.context.scene.objects)
    missing_directory=program_directory(project,'missing-fit.json');admission_refusals=[]
    for label,call in (
            ('advance',lambda:advance_textile_program(str(project.root),'missing-fit.json')),
            ('bundle',lambda:prepare_group_bundle(project,'missing-fit.json',assembly['groups'][0]['id'])),
            ('transition',lambda:transition_textile_group(str(project.root),'missing-fit.json',assembly['groups'][0]['id'],'preposition'))):
        try:call()
        except Exception as error:
            assert type(error).__name__=='StudioError' and 'reviewed numeric intent' in str(error),repr(error)
            admission_refusals.append({'entry':label,'status':'REFUSED_BEFORE_NATIVE_MUTATION','reason':str(error)})
        else:raise AssertionError('Missing production fit intent entered '+label)
        assert sorted(obj.name for obj in bpy.context.scene.objects)==before_objects
        assert not missing_directory.exists()
    receipts = []; replay = None; journal_recovery = None
    for group in assembly['groups']:
        for stage in ('preposition','mount','close','consolidate','relax','drape'):
            prepared = dispatch(str(project.root),'advance_textile_program',{'program_path':'program.json'})
            assert prepared['stage_executed'] is False and prepared['stage']==stage and prepared['group_id']==group['id']
            args = prepared['prepared_operation']['arguments']
            if case=='ordered' and not receipts:
                bundle=read_json(project.root/prepared['bundle']['path'])
                bundle['plan']['quality']['max_stretch']=1.9
                tampered=project.root/'tampered-bundle.json';atomic_json(tampered,bundle)
                pointer=program_directory(project,'program.json')/group['id']/'prepared-bundle.json'
                atomic_json(pointer,ref(tampered))
                try:dispatch(str(project.root),'transition_textile_group',args)
                except StudioError as error:
                    assert 'exact source-bound' in str(error),str(error)
                    dispatch(str(project.root),'restore_checkpoint',{})
                else:raise AssertionError('A rewritten bundle substituted weaker geometry gates')
                prepared=dispatch(str(project.root),'advance_textile_program',{'program_path':'program.json'})
                args=prepared['prepared_operation']['arguments']
            if case=='ordered' and not receipts:
                from a3d.runs import create_run,next_run_step
                run_spec={'version':1,'id':'native-canonical-stage','asset_id':project.state()['asset']['id'],
                    'kind':'garment','inputs':[ref(project.root/'program.json')],
                    'budgets':{'max_attempts':2,'max_seconds':1200},'units':[{'id':'native-source-stage','dependencies':[],
                        'executor':'blender','operation':'transition_textile_group','arguments':args,
                        'inputs':[ref(project.root/'program.json')],'success_statuses':['GROUP_STAGE_COMPLETED']}]}
                atomic_json(project.root/'native-journal-run.json',run_spec)
                run_doc=create_run(project,'garment','native-journal-run.json')
                scheduled=next_run_step(project,run_doc['run_id']);attempt=scheduled['attempt_id']
                original_import=importlib.import_module;callbacks={}
                def import_with_lost_callback(name,package=None):
                    loaded=original_import(name,package)
                    if name=='blender.operations':
                        current_runs=original_import('a3d.runs')
                        callbacks['module']=current_runs;callbacks['original']=current_runs.record_native_run_result
                        def lost(*a,**kw):raise RuntimeError('INJECTED_RESULT_CALLBACK_LOST_AFTER_NATIVE_SAVE')
                        current_runs.record_native_run_result=lost
                    return loaded
                from blender.bootstrap import dispatch_current
                with patch('importlib.import_module',side_effect=import_with_lost_callback):
                    try:dispatch_current(str(project.root),'transition_textile_group',args)
                    except RuntimeError as error:assert str(error)=='INJECTED_RESULT_CALLBACK_LOST_AFTER_NATIVE_SAVE'
                    else:raise AssertionError('The lost native result callback was not exercised')
                callbacks['module'].record_native_run_result=callbacks['original']
                assert project.state()['pending_blender_operation']['status']=='RESULT_READY'
                saved=current_group(project,program_directory(project,'program.json'),group['id'])
                actual_sha=saved[0]['mesh_sha256'];saved_receipt=saved[1]
                reconciled=callbacks['module'].next_run_step(project,run_doc['run_id'])
                assert reconciled['reconciled'] is True and reconciled['executed'] is False
                assert 'pending_blender_operation' not in project.state()
                after=current_group(project,program_directory(project,'program.json'),group['id'])
                assert after[1]==saved_receipt and after[0]['mesh_sha256']==actual_sha
                terminal=callbacks['module'].next_run_step(project,run_doc['run_id'])
                assert terminal['status']=='COMPLETED' and terminal['executed'] is False
                status=callbacks['module'].run_status(project,run_doc['run_id'])
                assert status['status']=='COMPLETED' and len(status['units'][0]['attempts'])==1
                assert status['units'][0]['attempts'][0]['id']==attempt
                journal_recovery={'run_id':run_doc['run_id'],'attempt_id':attempt,'reconciled':reconciled,
                    'source_stage_receipt':saved_receipt,'stage_reexecuted':False,'native_mesh_sha256':actual_sha}
                completed=saved[0]
            else:completed = dispatch(str(project.root),'transition_textile_group',args)
            receipts.append(completed)
            if replay is None and stage == 'mount':
                # Restore exactly this stage's entry checkpoint, leaving its
                # newer append-only receipt on disk. The scene wins, and the
                # replay must create one replacement rather than advance.
                checkpoint = completed['_entry_checkpoint']
                working = read_json(project.data/'blender/session.json')['working']
                bpy.ops.wm.open_mainfile(filepath=str(project.root/checkpoint['path']),load_ui=False,use_scripts=False)
                bpy.ops.wm.save_as_mainfile(filepath=working,check_existing=False)
                before = current_group(project,program_directory(project,'program.json'),group['id'])
                assert before[0]['stage']=='preposition'
                again = dispatch(str(project.root),'advance_textile_program',{'program_path':'program.json'})
                assert again['stage']=='mount'
                replay = dispatch(str(project.root),'transition_textile_group',again['prepared_operation']['arguments'])
                assert replay['stage']=='mount' and replay['previous']==before[1]
            atomic_json(OUT/(case+'-progress.json'),{'receipts':receipts,'replay':replay,'journal_recovery':journal_recovery})
    final = dispatch(str(project.root),'advance_textile_program',{'program_path':'program.json'})
    assert final['status']=='PROGRAM_STAGES_COMPLETED' and final['accepted'] is False
    assert final['purpose']=='TEST_ONLY' and final['production_qualification']=='NOT_GRANTED'
    assert all(row['purpose']=='TEST_ONLY' and row['production_qualification']=='NOT_GRANTED' for row in receipts)
    assert sha(original)==original_sha and collider_info(bpy.data.objects[body_name])==body_info
    last = receipts[-1]['component_results'][0]
    assert last['component_coverage']=='COMPLETE' and set(last['source_pieces'])==set(data['pieces'])
    component = read_json(project.root/last['derived_mesh']['path'])
    assert component['source_garment_sha256']==digest(data)
    from blender.textile_executor import verified_component_continuity
    continuity=verified_component_continuity(project,component,recipe['limits']['weld_gap_cm'])
    assert continuity['status']=='COMPONENT_CONTINUITY_VERIFIED'
    assert len(continuity['native_group_receipts'])==len(assembly['groups'])
    assert continuity['native_drape_receipts_required'] is False and continuity['current_clip_validation_required']
    assert continuity['qualification']=='GEOMETRY_ONLY' and continuity['cloth_evidence_created'] is False
    assert continuity['purpose']=='TEST_ONLY' and continuity['production_qualification']=='NOT_GRANTED'
    # The dispatcher reloads source modules between stages. The domain error
    # class imported when this driver started is a different Python identity.
    continuity_errors=tuple({StudioError,verified_component_continuity.__globals__['StudioError'],
        importlib.import_module('a3d.textile_executor').StudioError,
        importlib.import_module('a3d.core').StudioError})
    continuity_refusals=[]
    for change in ('missing-group','changed-group-ref','extra-source-relation'):
        candidate=copy.deepcopy(component)
        if change=='missing-group':candidate['component_continuity']['groups'].pop()
        elif change=='changed-group-ref':candidate['component_continuity']['groups'][0]['derived_mesh_ref']['sha256']='0'*64
        else:
            seam=next(iter(candidate['seams'].values()),None)
            candidate['seams']['invented']={**copy.deepcopy(seam),'kind':'detachable'} if seam else {
                'kind':'detachable','piece_a':next(iter(candidate['panels'])),'piece_b':next(iter(candidate['panels'])),
                'parameters':[0.,1.],'pairs':[[0,1],[1,2]]}
        try:verified_component_continuity(project,candidate,recipe['limits']['weld_gap_cm'])
        except continuity_errors as error:continuity_refusals.append({'case':change,'status':'REFUSED','reason':str(error)})
        else:raise AssertionError('Native component continuity admitted '+change)
    if case=='belt':
        assert component['seams']['ends']['kind']=='closure'
        assert all(a!=b for a,b in component['seams']['ends']['pairs'])
    if case=='ordered':
        assert receipts[5]['component_results'][0]['component_coverage']=='PARTIAL'
        assert any(row['object'].startswith('A3D.TextileCollider.') for row in receipts[6]['colliders'])
        assert component['seams']['interface']['kind']=='detachable'
        assert all(a!=b for a,b in component['seams']['interface']['pairs'])
    if case=='coupled':
        consolidation=next(row['consolidation'] for row in receipts if row['stage']=='consolidate')
        assert consolidation['permanent_continuity']['status']=='CONTINUITY_VERIFIED'
        assert consolidation['permanent_continuity']['source_permanent_pair_count']>0
        assert consolidation['explicit_unions']>0
        for row in receipts:
            if row['stage'] in ('relax','drape'):
                for physical in row['cloth_runs']:
                    seams=physical['final_checks']['seams']
                    assert seams['status']=='CONTINUITY_VERIFIED' and seams['active_pair_count']==0
                    assert seams['permanent_continuity']['proof_sha256']==consolidation['permanent_continuity']['proof_sha256']
                    assert physical['executed']['settings']['use_sewing_springs'] is False
                    assert physical['simulation']=='PASS' and physical['final_contact']['ok']
        assert component['seams']['interface']['kind']=='permanent'
        assert all(a==b for a,b in component['seams']['interface']['pairs'])
    return {'status':'PASS_SYNTHETIC_MECHANICS_ONLY','case':case,'receipts':receipts,'replay':replay,'journal_recovery':journal_recovery,
            'production_admission_refusals':admission_refusals,'purpose':'TEST_ONLY','production_qualification':'NOT_GRANTED',
            'component_continuity':continuity,'continuity_refusals':continuity_refusals,
            'qualification':'EXPERIMENTAL_NATIVE_FIXTURE_ONLY','fitting':'NOT_QUALIFIED','artistic':'NOT_APPROVED'}


results = {}
for case in ('ordered','belt','coupled'):
    try: results[case] = run(case)
    except Exception as error:
        results[case] = {'status':'FAIL','error':str(error),'type':type(error).__name__}
        atomic_json(OUT/'result.json',results); raise
    atomic_json(OUT/'result.json',results)
print('NATIVE_TEXTILE_EXECUTOR_RESULT='+str(OUT/'result.json'),flush=True)
