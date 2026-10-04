"""Prepare the next exact group operation from current native receipts.

This operation may create derived collider copies and recipe/bundle files. It
never executes a stage returned in ``prepared_operation``. That distinct stage
must pass the dispatcher and the normal explicit Blender authorization.
"""
import copy
import json
import uuid

from a3d.core import StudioError, atomic_json, contract, digest, inside, read_json, sha
from a3d.textile_executor import STAGES, load_textile_program, require_textile_program_admission


def program_directory(project, program_path):
    file = inside(project.root, program_path)
    ref=reference(project,file)
    directory=project.data/'blender'/'textile'/ref['sha256'][:16]
    identity=directory/'program-ref.json'
    if identity.is_file() and read_json(identity)!=ref:
        raise StudioError('Short textile program directory collides with another exact program reference')
    return directory


def program_identity(directory):
    file=directory/'program-ref.json'
    if not file.is_file():return None
    ref=read_json(file)
    if ref['sha256'][:16]!=directory.name:
        raise StudioError('Textile program directory identity changed')
    return ref['sha256']


def verified(project, ref):
    file = inside(project.root, ref['path'])
    if sha(file) != ref['sha256']: raise StudioError('Native textile reference changed')
    return read_json(file)


def reference(project, path):
    return {'path': path.relative_to(project.root).as_posix(), 'sha256': sha(path)}


def require_native_textile_program_admission(project,specification,compiled,assembly_plan=None):
    """Check reviewed intent and the connected exact body before any copies."""
    admission=require_textile_program_admission(project,specification,assembly_plan)
    if specification['purpose']=='TEST_ONLY':return admission
    import bpy
    from blender.physics_admission import require_native_fit_body
    from blender.sewing import collider_info
    names={name for entry in compiled['groups'] for name in entry['group']['body_colliders']}
    if len(names)!=1 or any(set(entry['group']['body_colliders'])!=names for entry in compiled['groups']):
        raise StudioError('Production textile groups require the same single exact reviewed body obstacle')
    name=next(iter(names));body=bpy.data.objects.get(name)
    if body is None or bpy.context.scene.objects.get(name)!=body:
        raise StudioError('Production textile reviewed body is absent from the connected scene')
    evidence=require_native_fit_body(project,admission['body_ref'],body)
    actual=collider_info(body)
    if not actual['collision_enabled'] or not actual['visible']:
        raise StudioError('Production textile exact reviewed body collider must be enabled and visible')
    for entry in compiled['groups']:
        snapshots=[row for row in entry['recipe']['colliders'] if row['object']==name]
        if len(snapshots)!=1 or snapshots[0]['role']!='mannequin':
            raise StudioError('Every production textile group must own its exact reviewed mannequin snapshot')
        for key in ('geometry_sha256','dimensions_cm','outer_thickness_cm','inner_thickness_cm'):
            if snapshots[0][key]!=actual[key]:
                raise StudioError('Production textile body collision policy differs from its source-bound actual snapshot')
    admission['native_body']=evidence
    return admission


def current_group(project, directory, gid):
    # The connected scene is the continuation authority after checkpoint
    # restoration. An append-only newer receipt on disk cannot advance an
    # older restored scene or create a group absent from that checkpoint.
    try:
        import bpy
    except ImportError:
        bpy = None
    if bpy is not None:
        identity=program_identity(directory)
        objects = [o for o in bpy.context.scene.objects if identity and o.get('a3d_textile_program_sha256') == identity
                   and o.get('a3d_textile_group_id') == gid and o.get('a3d_role') == 'textile-group-simulation']
        if not objects: return None
        if len(objects) != 1: raise StudioError('Several native candidates own the same textile group')
        obj = objects[0]
        ref = {'path': obj.get('a3d_textile_group_receipt'), 'sha256': obj.get('a3d_textile_group_receipt_sha256')}
        record = verified(project, ref)
        from blender.sewing import mesh_digest
        if (record.get('origin') != 'NATIVE_TEXTILE_GROUP' or record.get('group_id') != gid or
                record.get('object') != obj.name or record.get('program_ref',{}).get('sha256') != identity or
                record.get('stage') not in STAGES or record.get('status') != 'GROUP_STAGE_COMPLETED'):
            raise StudioError('Connected textile group receipt does not identify its actual program, object and stage')
        if record.get('mesh_sha256') != mesh_digest(obj):
            raise StudioError('Native group mesh changed after its stage receipt')
        return record, ref
    file = directory/gid/'latest.json'
    if not file.is_file(): return None
    ref = read_json(file); record = verified(project, ref)
    if record.get('group_id') != gid or record.get('origin') != 'NATIVE_TEXTILE_GROUP':
        raise StudioError('Group continuation lacks a native source-bound receipt')
    return record, ref


def verified_component_continuity(project,payload,weld_limit_cm):
    """Resolve portable group roots to actual connected completed native drapes."""
    import bpy
    if bpy.context.scene is None:raise StudioError('Native component continuity requires its connected scene')
    from a3d.textile_executor import verify_component_continuity
    proof=payload.get('component_continuity')
    if not proof:raise StudioError('Native component lacks complete source group continuity evidence')
    source=verified(project,proof['source_ref']);program=verified(project,proof['program_ref'])
    cid=payload['component_id'];binding=next((row for row in program['components'] if row['component_id']==cid),None)
    canonical=project.state()['components'][cid]['package']
    if (binding is None or binding['derived_mesh_ref']!=proof['source_ref'] or binding['package_ref']!=proof['package_ref']
            or {key:canonical[key] for key in ('path','sha256')}!=proof['package_ref']
            or sha(inside(project.root,canonical['path']))!=canonical['sha256']):
        raise StudioError('Native component continuity canonical source/package binding changed')
    _,compiled=load_textile_program(project,proof['program_ref']['path'])
    expected_groups={row['group']['id'] for row in compiled['groups'] if cid in row['payload']['source_components']}
    if {row['group_id'] for row in proof['groups']}!=expected_groups:
        raise StudioError('Native component continuity does not cover every actual program group')
    directory=program_directory(project,proof['program_ref']['path']);groups=[];native=[]
    for root in proof['groups']:
        prior=current_group(project,directory,root['group_id'])
        if not prior:raise StudioError('Component continuity native group is absent from the connected checkpoint')
        record,receipt=prior
        if (record.get('stage')!='drape' or record.get('status')!='GROUP_STAGE_COMPLETED'
                or record.get('purpose')!=program['purpose']
                or record.get('simulation')!='PASS' or record.get('program_ref')!=proof['program_ref']
                or record.get('qualification')!='GROUP_DRAPE_PHYSICS_ONLY'
                or record.get('derived_mesh')!=root['derived_mesh_ref'] or not record.get('cloth_runs')
                or any(run.get('simulation')!='PASS' or run.get('validation_contract',{}).get('version')!=2
                       for run in record['cloth_runs'])):
            raise StudioError('Component continuity needs actual completed current-validator native group drape receipts')
        group=verified(project,root['derived_mesh_ref'])
        groups.append({'group_id':root['group_id'],'derived_mesh_ref':root['derived_mesh_ref'],'payload':group})
        native.append({'group_id':root['group_id'],'receipt':receipt,'derived_mesh_ref':root['derived_mesh_ref'],
            'scope':record['qualification'],'purpose':record['purpose']})
    result=verify_component_continuity(source,payload,groups,weld_limit_cm)
    result.update(native_group_receipts=native,native_drape_receipts_required=False,
        purpose=program['purpose'],production_qualification='NOT_GRANTED',
        native_root_scope='COMPLETED_GROUP_DRAPE_PHYSICS_ONLY',current_clip_validation_required=True,
        fitting='NOT_QUALIFIED',artistic='NOT_REVIEWED')
    return result


def _source_relations(state, assembly):
    semantics = assembly['piece_semantics']
    separate = {frozenset((row['a'], row['b'])) for row in state['asset']['relationships']
                if row['must_remain_separate'] or not row['may_merge']}
    for link in assembly['link_graph']:
        a, b = (semantics[link['piece_'+side]]['component_id'] for side in ('a', 'b'))
        if a != b and link['kind'] == 'permanent' and frozenset((a, b)) in separate:
            raise StudioError('Permanent group consolidation contradicts approved separate asset components')


def _inner_colliders(project, directory, group, policy, create=True):
    import bpy
    from blender.sewing import collider_info, mesh_digest, object_mesh
    result = []; refs = []
    for gid in group['inner_group_colliders']:
        prior = current_group(project, directory, gid)
        if not prior or prior[0].get('stage') != 'drape' or prior[0].get('simulation') != 'PASS':
            raise StudioError('Inner textile group requires its actual completed native drape: '+gid)
        record, receipt = prior
        source = bpy.data.objects.get(record['object'])
        if source is None or mesh_digest(source) != record['mesh_sha256']:
            raise StudioError('Inner textile group geometry changed after its native drape')
        if policy is None:
            raise StudioError('Frozen inner collider thickness and orientation policy must be explicitly reviewed')
        name = 'A3D.TextileCollider.'+gid+'.'+receipt['sha256'][:12]
        obj = bpy.data.objects.get(name)
        if obj is None:
            if not create: raise StudioError('Prepared frozen inner collider is absent from the connected scene')
            obj = source.copy(); obj.data = source.data.copy(); obj.name = name
            bpy.context.scene.collection.objects.link(obj)
            for modifier in list(obj.modifiers): obj.modifiers.remove(modifier)
            if policy['outward_normal_sign'] == -1:
                points = [list(vertex.co) for vertex in obj.data.vertices]
                faces = [list(reversed(face.vertices)) for face in obj.data.polygons]
                replacement = bpy.data.meshes.new(name+'.Mesh'); replacement.from_pydata(points, [], faces); replacement.update()
                obj.data = replacement
            obj.modifiers.new('A3D.FrozenCollision', 'COLLISION')
            obj.collision.thickness_outer = policy['outer_thickness_cm']/100
            obj.collision.thickness_inner = policy['inner_thickness_cm']/100
            obj['a3d_role'] = 'frozen-textile-collider'; obj['a3d_source_group_receipt'] = receipt['path']
            obj['a3d_source_group_receipt_sha256'] = receipt['sha256']
            obj.hide_set(False); obj.hide_render = True
        info = collider_info(obj)
        source_points, source_faces = object_mesh(source)
        if policy['outward_normal_sign'] == -1: source_faces = [list(reversed(face)) for face in source_faces]
        expected_geometry = digest({'vertices_m':[[round(value,7) for value in point] for point in source_points], 'faces':source_faces})
        mismatches=[]
        for key,expected in (('collision_enabled',True),('visible',True),('geometry_sha256',expected_geometry)):
            if info[key]!=expected:mismatches.append({'field':key,'expected':expected,'observed':info[key]})
        if obj.get('a3d_source_group_receipt_sha256')!=receipt['sha256']:
            mismatches.append({'field':'source_receipt_sha256','expected':receipt['sha256'],
                               'observed':obj.get('a3d_source_group_receipt_sha256')})
        for key,rna_name in (('outer_thickness_cm','thickness_outer'),('inner_thickness_cm','thickness_inner')):
            if abs(info[key]-policy[key])>1e-5:
                rna=obj.collision.bl_rna.properties[rna_name]
                mismatches.append({'field':key,'expected_cm':policy[key],'observed_cm':info[key],
                    'rna_hard_min_cm':rna.hard_min*100,'rna_hard_max_cm':rna.hard_max*100})
        if mismatches:
            error=StudioError('Frozen inner collider policy changed: '+repr(mismatches))
            error.frozen_collider_mismatches=mismatches;raise error
        result.append({k: info[k] for k in ('object', 'geometry_sha256', 'dimensions_cm', 'outer_thickness_cm', 'inner_thickness_cm')}
                      | {'role': 'support', 'tolerance_cm': policy['tolerance_cm']})
        refs.append(receipt)
    return result, refs


def prepare_group_bundle(project, program_path, group_id, persist=True):
    """Generate exact recipe collider hashes, without executing group physics."""
    from blender.operations import working
    from a3d.pattern_assembly import validate_plan
    from a3d.core import contract
    working(str(project.root))
    spec, compiled = load_textile_program(project, program_path)
    assembly = verified(project, spec['assembly_plan_ref'])
    admission=require_native_textile_program_admission(project,spec,compiled,assembly)
    _source_relations(project.state(), assembly)
    entry = next((g for g in compiled['groups'] if g['group']['id'] == group_id), None)
    if entry is None: raise StudioError('Group is not owned by this textile program')
    if len(entry['group']['layers']) > 1 and not spec.get('experimental_coupled_multilayer', False):
        raise StudioError('Coupled multilayer group requires the declared experimental native trial')
    if len(entry['group']['layers']) > 1 and any(not p['self_collision'] for p in entry['recipe']['phases'].values()):
        raise StudioError('Coupled multilayer trial requires native self collision in every declared phase')
    directory = program_directory(project, program_path)
    colliders, receipts = _inner_colliders(project, directory, entry['group'], spec.get('frozen_collider_policy'), create=persist)
    bundle = copy.deepcopy(entry)
    bundle['purpose']=spec['purpose'];bundle['execution_admission']=admission
    bundle['production_qualification']='NOT_GRANTED'
    # Retain reviewed body/support obstacles owned by body nodes. Previously
    # recorded garment snapshots are superseded by the actual inner receipts.
    body_names = set(entry['group']['body_colliders'])
    existing = {row['object']: row for row in bundle['recipe']['colliders'] if row['object'] in body_names}
    existing.update({row['object']: row for row in colliders})
    bundle['recipe']['colliders'] = [existing[name] for name in sorted(existing)]
    if body_names-set(existing):
        raise StudioError('Textile group recipe lacks its declared body obstacle snapshots')
    semantics = assembly['piece_semantics']; active = entry['group']['layers']
    nodes = [{'id': layer, 'kind': 'garment', 'panels': sorted(pid for pid in entry['group']['pieces'] if semantics[pid]['layer'] == layer),
              'colliders': [], 'source_ref': spec['assembly_plan_ref']} for layer in active]
    order = [row for row in assembly['spatial_graph']['inside_to_outside'] if row[0] in active and row[1] in active]
    if body_names:
        nodes.append({'id': 'program-body', 'kind': 'body', 'panels': [], 'colliders': sorted(body_names),
                      'source_ref': assembly['body_ref']})
        order.extend(['program-body', layer] for layer in active)
    for collider, receipt, gid in zip(colliders, receipts, entry['group']['inner_group_colliders'], strict=True):
        frozen_id = 'frozen.'+gid
        nodes.append({'id': frozen_id, 'kind': 'garment', 'panels': [], 'colliders': [collider['object']],
                      # The collider copy has already received the explicitly
                      # declared winding correction; use its actual outward face.
                      'source_ref': receipt, 'outward_normal_sign': 1})
        order.extend([frozen_id, layer] for layer in active)
        if body_names: order.append(['program-body', frozen_id])
    bundle['plan']['layers'] = {'version': 1, 'source_ref': spec['assembly_plan_ref'], 'mode': 'ordered',
                                'interaction': 'one_way_declared', 'nodes': nodes, 'inside_to_outside': sorted(order)}
    if len(active) > 1:
        from a3d.dressing import sewing_graph_digest
        from a3d.pattern_assembly import map_digest
        bundle['plan']['layer_execution'] = {'version': 1, 'mode': 'joint_coupled_single_object',
            'source_ref': spec['assembly_plan_ref'], 'source_mapping_sha256': map_digest(bundle['payload']),
            'sewing_graph_sha256': sewing_graph_digest(bundle['payload'])}
    contract('sewing-recipe', bundle['recipe']); validate_plan(bundle['payload'], bundle['plan'])
    bundle['program_ref'] = reference(project, inside(project.root, program_path))
    bundle['inner_group_receipts'] = receipts
    bundle['origin'] = 'NATIVE_TEXTILE_BUNDLE'; bundle['stage_execution'] = 'NOT_EXECUTED'
    if not persist: return bundle, None
    directory.mkdir(parents=True,exist_ok=True)
    identity=directory/'program-ref.json'
    if identity.is_file() and read_json(identity)!=bundle['program_ref']:
        raise StudioError('Short textile program directory identity collides')
    if not identity.is_file():atomic_json(identity,bundle['program_ref'])
    path = directory/group_id/'bundles'/('b-'+uuid.uuid4().hex[:16]+'.json')
    if path.exists():raise StudioError('Unique textile bundle name unexpectedly already exists')
    atomic_json(path, bundle); ref = reference(project, path)
    atomic_json(directory/group_id/'prepared-bundle.json', ref)
    return bundle, ref


def advance_textile_program(project_root, program_path):
    """Prepare exactly one next operation; authorization remains separate."""
    import bpy
    from blender.operations import working
    from a3d.guard import code_for
    project, session = working(project_root)
    spec, compiled = load_textile_program(project, program_path)
    admission=require_native_textile_program_admission(project,spec,compiled)
    directory = program_directory(project, program_path)
    for entry in compiled['groups']:
        gid = entry['group']['id']; prior = current_group(project, directory, gid)
        if prior and prior[0].get('stage') == 'drape': continue
        if any(not current_group(project, directory, dep) or current_group(project, directory, dep)[0].get('stage') != 'drape'
               for dep in entry['group']['dependencies']):
            continue
        bundle, ref = prepare_group_bundle(project, program_path, gid)
        stage = 'preposition' if prior is None else STAGES[STAGES.index(prior[0]['stage'])+1]
        arguments = {'program_path': program_path, 'group_id': gid, 'stage': stage}
        bpy.ops.wm.save_as_mainfile(filepath=session['working'], check_existing=False)
        return {'status': 'NEXT_OPERATION_PREPARED', 'group_id': gid, 'stage': stage,
                'purpose':spec['purpose'],'execution_admission':admission,'production_qualification':'NOT_GRANTED',
                'bundle': ref, 'inner_group_receipts': bundle['inner_group_receipts'],
                'prepared_operation': {'operation': 'transition_textile_group', 'arguments': arguments,
                                       'code': code_for(project_root, 'transition_textile_group', arguments)},
                'execution_permission_required': True, 'stage_executed': False,
                'qualification': 'NONE', 'simulation': 'NOT_EXECUTED', 'fitting': 'NOT_QUALIFIED'}
    return {'status': 'PROGRAM_STAGES_COMPLETED', 'qualification': 'NONE', 'accepted': False,
            'purpose':spec['purpose'],'execution_admission':admission,'production_qualification':'NOT_GRANTED',
            'fitting': 'REQUIRES_FULL_GARMENT_MEASUREMENT', 'stage_executed': False}


def bind_component_preparations(project, templates_path, body_object, body_geometry_ref, output_directory,
                                envelope_review=None,policy_path=None):
    """Bind templates to real native maps and the exact approved body copy.

    This prepares files, not a scene operation. The resulting preparation DAG
    must still use the guarded dispatcher, with separate exact authorization
    for every production operation. No Cloth or placement admission occurs.
    """
    import bpy
    from a3d.pattern_assembly import map_digest
    from a3d.sewing import validate_recipe
    from blender.body_target import evaluated_mesh
    from blender.sewing import build_mesh,collider_info
    file=inside(project.root,templates_path); templates=read_json(file)
    if templates.get('status')!='SOURCE_PREPARATION_TEMPLATES_READY':
        raise StudioError('Native preparation binding requires complete portable templates')
    if templates.get('prepared_sha256')!=digest({k:v for k,v in templates.items() if k!='prepared_sha256'}):
        raise StudioError('Portable source preparation template identity changed')
    inputs=templates.get('compiler_inputs')
    if not inputs:raise StudioError('Native binding needs reconstructable source compiler inputs')
    for ref in inputs.values():verified(project,ref)
    from a3d.production_dossier import compile_project_dossier
    from a3d.garment_planner import plan_assembly
    from a3d.textile_executor import prepare_component_templates
    compiled=compile_project_dossier(project,inputs['dossier_ref']['path'],inputs['production_spec_ref']['path'])
    guide_reconstruction=None
    if policy_path:
        from a3d.garment_guide_policy import verify_project_guides
        guide_reconstruction=verify_project_guides(project,compiled,verified(project,inputs['guides_ref']),policy_path)
    source_assembly=verified(project,inputs['assembly_plan_ref'])
    if source_assembly!=plan_assembly(compiled['assembly_spec'],capabilities=['coupled_multilayer']):
        raise StudioError('Source assembly differs from reconstruction of its exact approved dossier and specification')
    production=verified(project,inputs['production_spec_ref']);sources={}
    for item in production['packages']:
        with __import__('zipfile').ZipFile(inside(project.root,item['source_ref']['path'])) as archive:
            sources[item['component_id']]={'source_ref':item['source_ref'],'data':json.loads(archive.read('garment.json'))}
    reconstructed=prepare_component_templates(source_assembly,sources,verified(project,inputs['guides_ref']),
        verified(project,inputs['standard_recipe_ref']),verified(project,inputs['dossier_ref']),inputs['dossier_ref'],inputs)
    if reconstructed!=templates:
        raise StudioError('Portable template differs from reconstruction of its exact sources, guides and recipe policy')
    profile=verified(project,templates['body_ref']); geometry=verified(project,body_geometry_ref)
    if (digest([geometry['vertices_cm'],geometry['faces']])!=profile['geometry_sha256'] or
            any(geometry.get(key)!=profile.get(key) for key in ('source_sha256','pose_sha256'))):
        raise StudioError('Native body geometry or pose differs from the exact measured profile used by source guides')
    obj=bpy.data.objects.get(body_object)
    if obj is None or obj.type!='MESH' or obj.get('a3d_profile_cache_key')!=profile['cache_key']:
        raise StudioError('Prepared body collider is absent or belongs to another measured body profile')
    actual,_=evaluated_mesh(obj,bpy.context.evaluated_depsgraph_get(),1.)
    if actual!={key:geometry[key] for key in ('vertices_cm','faces','face_sets')}:
        raise StudioError('Connected body geometry differs from the exact approved measured body copy')
    info=collider_info(obj)
    if not info['visible'] or not info['collision_enabled'] or any(abs(v-1)>1e-8 for v in info['scale']):
        raise StudioError('Exact target body collider must be visible, evaluated and have identity scale')
    output=inside(project.root,output_directory,False);reusing=output.is_dir()
    old_binding=None
    if reusing:
        if not (output/'binding.json').is_file():
            raise StudioError('Native preparation binding stopped before its boundary; preserve it and choose a fresh output directory')
        old_binding=read_json(output/'binding.json')
    else:output.mkdir(parents=True,exist_ok=False)
    def save_expected(path,value):
        if reusing:
            if not path.is_file() or read_json(path)!=value:
                raise StudioError('Persisted native preparation binding differs from its exact source reconstruction: '+path.name)
        else:atomic_json(path,value)
    inputs=[reference(project,file),templates['body_ref'],body_geometry_ref]+templates.get('input_refs',[])
    if guide_reconstruction:inputs.append(guide_reconstruction['policy_ref'])
    bindings={};units=[];prior=[];state=project.state()
    for cid,template in sorted(templates['components'].items()):
        if (template['guide_identity']['profile_sha256']!=digest(profile)
                or template['guide_identity']['profile_cache_key']!=profile['cache_key']):
            raise StudioError('Source guides belong to another measured body profile')
        package=state['components'][cid]['package'];source_ref=template['source_ref']
        if {k:package[k] for k in ('path','sha256')}!=source_ref or sha(inside(project.root,source_ref['path']))!=source_ref['sha256']:
            raise StudioError('Preparation source package differs from canonical approved component')
        with __import__('zipfile').ZipFile(inside(project.root,source_ref['path'])) as archive:
            data=json.loads(archive.read('garment.json'))
        if digest(data)!=template['source_garment_sha256']:raise StudioError('Source garment changed before native binding')
        recipe=copy.deepcopy(template['recipe_template'])
        recipe['colliders']=[{**{k:info[k] for k in ('object','dimensions_cm','geometry_sha256','outer_thickness_cm','inner_thickness_cm')},
            'role':'mannequin','tolerance_cm':.001}];recipe['no_collision_reason']=''
        validate_recipe(data,recipe)
        plan=copy.deepcopy(template['plan_fields'])
        declared={name for n in plan['layers']['nodes'] if n['kind']=='body' for name in n['colliders']}
        if declared!={body_object}:raise StudioError('Native collider identity differs from the explicit source layer graph')
        prep=copy.deepcopy(template['preparation_template'])
        dossier=verified(project,prep['construction_dossier'])
        if envelope_review:
            verified(project,envelope_review);plan['collision']['envelope_review']=copy.deepcopy(envelope_review)
        probe_quality=None
        try:payload=build_mesh(data,recipe,regular_mesh=prep['regular_mesh'],dossier=dossier)
        except StudioError as error:
            payload=getattr(error,'garment_payload',None)
            if payload is None:raise
            probe_quality={'status':'NEEDS_CORRECTION','message':str(error)}
        plan['mapping_sha256']=map_digest(payload)
        contract('pattern-assembly',plan)
        component=output/cid
        if not reusing:component.mkdir()
        recipe_file=component/'recipe.json';plan_file=component/'plan.json';prep_file=component/'preparation.json'
        save_expected(recipe_file,recipe);save_expected(plan_file,plan)
        prep['assembly_plan']=reference(project,plan_file);contract('pattern-preparation',prep);save_expected(prep_file,prep)
        bindings[cid]={'component_id':cid,'package_ref':source_ref,'recipe_ref':reference(project,recipe_file),
            'plan_ref':reference(project,plan_file),'preparation_ref':reference(project,prep_file),
            'native_probe_mapping_sha256':map_digest(payload),'probe_quality':probe_quality,
            'native_mesh_sha256':'NOT_SAVED_YET','readiness':'NOT_EXECUTED'}
        unit={'id':'prepare-'+cid,'dependencies':[],'executor':'blender','operation':'prepare_pattern_assembly',
            'arguments':{'component_id':cid,'recipe_path':recipe_file.relative_to(project.root).as_posix(),
                         'preparation_path':prep_file.relative_to(project.root).as_posix()},
            'inputs':inputs+[source_ref,reference(project,recipe_file),reference(project,plan_file),reference(project,prep_file)],
            'success_statuses':['READY']}
        units.append(unit)
    prior_run=verified(project,old_binding['run_specification']) if reusing else None
    run={'version':1,'id':prior_run['id'] if prior_run else 'source-preparation-'+uuid.uuid4().hex[:16],'asset_id':state['asset']['id'],'kind':'garment',
        'inputs':inputs,'budgets':{'max_attempts':2,'max_seconds':3600},'units':units}
    contract('run',run);run_file=output/'run.json';save_expected(run_file,run)
    component_runs={}
    for unit in units:
        cid=unit['arguments']['component_id'];component_run=copy.deepcopy(run)
        component_run['id']=run['id']+'-'+cid;component_run['units']=[unit]
        component_file=output/cid/'run.json';contract('run',component_run);save_expected(component_file,component_run)
        component_runs[cid]=reference(project,component_file)
    result={'version':1,'status':'NATIVE_PREPARATION_INPUTS_BOUND','templates':reference(project,file),
        'body_ref':templates['body_ref'],'body_geometry_ref':body_geometry_ref,'collider':info,
        'components':bindings,'run_specification':reference(project,run_file),'component_run_specifications':component_runs,'qualification':'NONE',
        'simulation':'NOT_EXECUTED','source_mutated':False}
    if guide_reconstruction:result['guide_reconstruction']=guide_reconstruction
    save_expected(output/'binding.json',result)
    return result
