"""Canonical TEST_ONLY source-grip execution, not a garment passage approval.

The fixture uses a new project, catalog skin measured by real native dispatch,
an explicit open band and a tiny sourced grip trajectory away from the skin.
It checks Cloth observations, grip removal, preservation, budget and missing
data outcomes. It never claims that this isolated grip test dresses the body.
"""
import argparse
import copy
from pathlib import Path
import sys

ROOT=Path(__file__).resolve().parents[1];sys.path.insert(0,str(ROOT))


def arguments(argv):
    parser=argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--output',required=True)
    parser.add_argument('--catalog-id',choices=('body.realistic-male','body.realistic-female'),default='body.realistic-male')
    parser.add_argument('--validate-only',action='store_true');args=parser.parse_args(argv)
    output=Path(args.output)
    if not output.is_absolute() or output.exists() or output.drive.lower()!='g:':
        parser.error('Require a new absolute output on approved G: storage')
    args.output=output.resolve();return args


def _project(directory):
    from a3d.core import atomic_json,read_json
    import tests.support as support
    from tests.textile_fixtures import annotate_dossier,source
    original_source=support.garment_source;original_dossier=support.construction_dossier
    def dossier(project,garment=False):
        file=project.data/'source/package/garment.json';data=read_json(file)
        atomic_json(file,dict(data,seams=[]))
        try:result=original_dossier(project,garment)
        finally:atomic_json(file,data)
        return annotate_dossier(result,data)
    support.garment_source=lambda path:source(path,'belt');support.construction_dossier=dossier
    try:return support.ready_project(directory,True)
    finally:support.garment_source=original_source;support.construction_dossier=original_dossier


def _source_controls(project,body,directory):
    """Real compiler + exact body skin; all placement values are fixture sources."""
    from a3d.core import atomic_json,digest,read_json,sha
    from a3d.production_dossier import compile_project_dossier
    from a3d.garment_planner import plan_assembly
    from a3d.textile_executor import prepare_component_templates
    from a3d.dressing_derivation import dressing_derivation_descriptor
    from a3d.dressing_paths import dressing_paths_descriptor
    from tests.test_garment_planner import example
    cid='garment.coat';data=read_json(project.data/'source/package/garment.json')
    package=project.state()['components'][cid]['package'];package={key:package[key] for key in ('path','sha256')}
    def save(name,value):
        path=directory/(name+'.json');atomic_json(path,value)
        return {'path':path.relative_to(project.root).as_posix(),'sha256':sha(path)}
    dossier_ref={'path':'.a3d/evidence/construction.json','sha256':sha(project.data/'evidence/construction.json')}
    body_ref=body['artifacts']['profile'];profile=read_json(project.root/body_ref['path'])
    geometry=read_json(project.root/body['artifacts']['geometry']['path'])
    spec={'version':1,'source_ref':dossier_ref,'body_ref':body_ref,
        'packages':[{'component_id':cid,'source_ref':package}],
        'piece_semantics':{'belt':{'role':'belt','side':'center','layer':'cloth'}},
        'layers':{'version':1,'source_ref':dossier_ref,'mode':'ordered','interaction':'one_way_declared',
            'nodes':[{'id':'body','kind':'body','panels':[],'colliders':['source-measured-body'],'source_ref':body_ref},
                     {'id':'cloth','kind':'garment','panels':['belt'],'colliders':[],'source_ref':package}],
            'inside_to_outside':[['body','cloth']]},'budgets':example()['budgets']}
    spec_ref=save('production-spec',spec)
    compiled=compile_project_dossier(project,dossier_ref['path'],spec_ref['path'])
    assert compiled['status']=='READY_TO_PLAN',compiled
    assembly=plan_assembly(compiled['assembly_spec'],capabilities=['coupled_multilayer']);assembly_ref=save('assembly',assembly)
    # Source declares a plane 50 cm outside the actual evaluated skin bounds.
    # This is an apparatus clearance for a grip fixture, not a fitted placement.
    origin=[max(point[0] for point in geometry['vertices_cm'])+50.,0.,100.]
    seed_ref=save('explicit-fixture-seed',{'purpose':'TEST_ONLY_SOURCE_GRIP_APPARATUS',
        'origin_cm':origin,'skin_bbox_clearance_x_cm':50.,'support_translation_cm':[.01,0.,0.],
        'endpoint_tolerance_cm':.25,'physical_passage':'NOT_QUALIFIED'})
    guide={'source_ref':seed_ref,'arc_sections':[{'v_cm':v,'arc_offset_cm':0.,
        'curve_cm':[[origin[0],origin[1]+v,origin[2]],[origin[0]+2.,origin[1]+v,origin[2]]]} for v in (0.,8.)]}
    semantics={pid:{key:value for key,value in row.items() if key not in ('id','component_id','edges','source_ref')}
               for pid,row in assembly['piece_semantics'].items()}
    guides={cid:{'status':'GARMENT_GUIDES_PREPARED','source_sha256':digest(data),'semantics_sha256':digest(semantics),
        'profile_sha256':digest(profile),'profile_cache_key':profile['cache_key'],'panels':{'belt':guide},
        'qualification':'TEST_ONLY_SOURCE_PLANE_NOT_FITTED'}}
    guide_ref=save('guides',guides)
    standard=read_json(ROOT/'templates/sewing-recipe.json');standard['phases']['drape']['frames']=64
    standard['phases']['drape']['gravity_m_s2']=[0.,0.,-.1]
    standard_ref=save('declared-standard-recipe',standard)
    compiler_inputs={'dossier_ref':dossier_ref,'production_spec_ref':spec_ref,'assembly_plan_ref':assembly_ref,
                     'guides_ref':guide_ref,'standard_recipe_ref':standard_ref}
    templates=prepare_component_templates(assembly,{cid:{'source_ref':package,'data':data}},guides,standard,
        read_json(project.root/dossier_ref['path']),dossier_ref,compiler_inputs)
    templates_ref=save('templates',templates)
    policy={'version':1,'bindings':{'templates_ref':templates_ref,'body_geometry_ref':body['artifacts']['geometry'],
        'body_triangles_ref':body['artifacts']['triangles']},'section_parameters':[0.,.5,1.],
        'source_edge_spacing_cm':.5,'budgets':{'max_boundary_edges':1000,'max_body_triangles':100000,
            'max_methods':8,'max_sections':24,'max_candidate_orders':4,'max_path_points':2000}}
    policy_ref=save('derivation-spec',policy);derived=dressing_derivation_descriptor(project,policy_ref['path'])
    assert len(derived['derivation']['methods'])==1
    derived_ref=save('derived',derived['derivation'])
    request={'version':1,'bindings':{'derivation_spec_ref':policy_ref,'derivation_ref':derived_ref},'max_path_points':2000}
    request_ref=save('paths-spec',request);paths=dressing_paths_descriptor(project,request_ref['path'])['paths'];paths_ref=save('paths',paths)
    return data,package,templates['components'][cid]['recipe_template'],paths,request_ref,paths_ref,seed_ref,save


def run(output,catalog_id):
    import bpy
    from a3d.core import atomic_json,digest,read_json,sha
    from a3d.mannequins import catalog,select_catalog_body
    from a3d.motion_profiles import standard_motion_profile
    from a3d.dressing_paths import dressing_execution_descriptor
    from blender.body_source import data_ids,live_geometry
    from blender.body_motion import prepare_motion_inputs
    from blender.sewing import build_mesh,mesh_recipe_digest
    from tests.test_body_target import target_fixture
    from tests.test_garment_motion import motion_profile
    from tests.native_garment_motion import _dispatch
    assert bpy.app.background and not bpy.data.filepath
    output.mkdir(parents=True,exist_ok=False);project=_project(output/'project')
    directory=project.data/'native-dressing-inputs';directory.mkdir(parents=True,exist_ok=False)
    baseline=data_ids();live=live_geometry();selected=select_catalog_body(project,catalog_id)
    entry=next(row for row in catalog()['entries'] if row['id']==catalog_id)
    target=target_fixture(selected['selection']['sha256'],selected['anatomy_adapter']['sha256'])
    target['anatomy_adapter']=selected['anatomy_adapter'];target['orientation']=dict(entry['orientation'],origin_cm=[0.,0.,0.])
    target_path=directory/'target.json';atomic_json(target_path,target)
    def ref(path):return {'path':path.relative_to(project.root).as_posix(),'sha256':sha(path)}
    body_args={'selection_path':selected['selection']['path'],'target_path':ref(target_path)['path']}
    body,body_journal=_dispatch(project,'prepare_body_target',body_args,[selected['selection'],selected['anatomy_adapter'],ref(target_path)],directory,
        'source-native-body-target',['NATIVE_BODY_TARGET_MEASURED'])
    rig=prepare_motion_inputs(project,body['receipt']['path'])['specification']
    motion=standard_motion_profile('walk',rig,'TEST_ONLY referenced body motion; dressing uses fixed measured target',frame_start=1,frame_end=5)
    for track in motion['tracks']:
        for key in track['keys']:key['radians']*=.01
    body_motion_path=directory/'body-motion.json';atomic_json(body_motion_path,motion)
    body_motion,body_motion_journal=_dispatch(project,'prepare_body_motion',
        {'body_target_receipt_path':body['receipt']['path'],'motion_profile_path':ref(body_motion_path)['path']},
        [body['receipt'],ref(body_motion_path)],directory,'source-native-body-motion',['CLIP_SAMPLES_COMPLETE'])
    data,package,recipe,paths,path_spec,path_ref,seed_ref,save=_source_controls(project,body,directory)
    recipe['pins']=[{'piece':'belt','edge':'right','weight':1.}]
    payload=build_mesh(data,recipe);uv=copy.deepcopy(payload['rest_cm'])
    payload.update(version=2,synthetic=True,rest_mode='assembled_3d',rest_cm=copy.deepcopy(payload['placed_cm']),
        recipe_mesh_sha256=mesh_recipe_digest(recipe),package_sha256=package['sha256'],
        source_rest_triangles_cm=[[uv[index][:2] for index in face] for face in payload['faces']],
        source_face_vertex_ids=copy.deepcopy(payload['faces']),source_face_pieces=['belt']*len(payload['faces']),
        pattern_assembly={'temporary_supports_active':False})
    candidate_ref=save('native-source-candidate',payload);recipe_ref=save('native-recipe',recipe)
    profile=motion_profile({'candidate':candidate_ref,'recipe':recipe_ref,'body_motion_receipt':body_motion['receipt']})
    motion_ref=save('source-motion-profile',profile)
    method=paths['controls'][0]['method_id'];vertex=payload['panels']['belt']['edges']['left'][0]
    initial=payload['placed_cm'][vertex];last=[initial[0]+.01,initial[1],initial[2]]
    targets_ref=save('source-grip-targets',{'entry':initial,'last':last,'seed_ref':seed_ref,'physical_passage':'NOT_QUALIFIED'})
    order_ref=save('source-order',{'mount_order':[method],'source_seed':seed_ref})
    instructions={'version':1,'paths_sha256':paths['paths_sha256'],'entry_candidate_ref':candidate_ref,'mount_order':[method],
        'mount_order_source_ref':order_ref,'method_stages':[{'method_id':method,'start_frame':1,'end_frame':5}],
        'frame_end':5,'supports':[{'id':'source-left-grip','method_id':method,'start_frame':1,'piece':'belt','edge':'left','edge_vertex':0,
            'weight':1.,'release_frame':4,'waypoints':[{'frame':1,'source_ref':targets_ref,'pointer':'/entry'},
                                                   {'frame':3,'source_ref':targets_ref,'pointer':'/last'}]}],
        'endpoint_constraints':[{'method_id':method,'piece':'belt','edge':'left','edge_vertex':0,
            'source_ref':targets_ref,'pointer':'/last','tolerance_cm':.25}]}
    instructions_ref=save('instructions',instructions)
    execution={'version':1,'id':'test-only-source-grip-sequence','component_id':'garment.coat','purpose':'TEST_ONLY','method_ids':[method],
        'bindings':{'paths_spec_ref':path_spec,'paths_ref':path_ref,'motion_profile_ref':motion_ref,'instructions_ref':instructions_ref},
        'execution':{'max_frames':5,'max_seconds':120.,'max_cache_vertex_frames':1000000}}
    execution_ref=save('execution-profile',execution)
    descriptor=dressing_execution_descriptor(project,execution_ref['path']);assert descriptor['status']=='DRESSING_INSTRUCTIONS_PREPARED'
    hashes={row['path']:row['sha256'] for row in descriptor['evidence']}
    native,journal=_dispatch(project,'run_dressing_program',{'profile_path':execution_ref['path']},descriptor['evidence'],directory,
        'native-source-grip-sequence',['DRESSING_SEQUENCE_SAMPLES_COMPLETE'])
    assert native['status']=='DRESSING_SEQUENCE_SAMPLES_COMPLETE',native
    observations=read_json(project.root/native['observations_artifact']['path'])
    assert [row['frame'] for row in observations['frames']]==[1,2,3,4,5]
    assert all(row['checks'] for row in observations['intervals']) and native['native_reopened']
    assert all(row['supports'][0]['weight']==0. for row in observations['frames'][-2:])
    assert all(row['full_weight_grip_errors'][0]['error_cm']<=.001 for row in observations['frames'][:3])
    assert native['support_weight_driver']['kind']=='NATIVE_CONSTANT_WEIGHT_MIX_ACTION'
    assert all(not row['point_cache']['is_outdated'] for row in observations['frames'])
    assert all(row['evaluated_pin_weights'].get(str(vertex),0.)==1. for row in observations['frames'][:3])
    assert all(str(vertex) not in row['evaluated_pin_weights'] for row in observations['frames'][3:])
    displacement=max(row['max_displacement_cm'] for row in observations['frames']);assert displacement>1e-5
    assert native['body_pose']=='FIXED_EXACT_MEASURED_TARGET' and native['fitting']=='NOT_QUALIFIED' and not native['accepted']
    short=copy.deepcopy(execution);short['id']='test-only-budget-refusal';short['execution']['max_frames']=2
    short_ref=save('short-profile',short);short_desc=dressing_execution_descriptor(project,short_ref['path'])
    incomplete,short_journal=_dispatch(project,'run_dressing_program',{'profile_path':short_ref['path']},short_desc['evidence'],directory,
        'native-source-grip-insufficient-budget',['DRESSING_SEQUENCE_SAMPLES_COMPLETE'])
    assert incomplete['status']=='INCOMPLETE' and incomplete['observed_frames']==2 and incomplete['artifact'] is None
    missing=copy.deepcopy(execution);missing['id']='test-only-missing-inputs';del missing['bindings']['instructions_ref']
    missing_ref=save('missing-profile',missing);missing_desc=dressing_execution_descriptor(project,missing_ref['path'])
    needs_data,missing_journal=_dispatch(project,'run_dressing_program',{'profile_path':missing_ref['path']},missing_desc['evidence'],directory,
        'native-source-grip-missing-data',['DRESSING_SEQUENCE_SAMPLES_COMPLETE'])
    assert needs_data['status']=='NEEDS_DATA' and needs_data['simulation']=='NOT_EXECUTED' and not needs_data['native_scene_created']
    assert data_ids()==baseline and live_geometry()==live
    assert all(sha(project.root/path)==identity for path,identity in hashes.items())
    result={'version':1,'status':'TEST_ONLY_DRESSING_SOURCE_GRIP_FIXTURE_COMPLETE','catalog_id':catalog_id,
        'source_conditions':read_json(project.root/seed_ref['path']),'body':body,'body_journal':body_journal,
        'body_motion':body_motion,'body_motion_journal':body_motion_journal,'execution':native,'journal':journal,
        'insufficient_budget':incomplete,'insufficient_budget_journal':short_journal,
        'missing_data':needs_data,'missing_data_journal':missing_journal,'original_scene_preserved':True,
        'physical_body_passage':'NOT_QUALIFIED','closure_behavior':'NOT_QUALIFIED','fitting':'NOT_QUALIFIED','product_acceptance':'NOT_GRANTED'}
    atomic_json(output/'receipt.json',result);print(result['status']+': '+str(output/'receipt.json'))


if __name__=='__main__':
    argv=sys.argv[sys.argv.index('--')+1:] if '--' in sys.argv else sys.argv[1:];args=arguments(argv)
    if args.validate_only:print('ARGUMENTS_VALIDATED: no native operation executed')
    else:run(args.output,args.catalog_id)
