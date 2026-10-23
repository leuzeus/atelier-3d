"""Experimental source-bound group staging using the existing Cloth engine.

No fake canonical component is registered. A disposable group retains source
component/piece/face/UV identities, then emits separate component copies. Each
stage is its own guarded operation and checkpoint; interruptions replay that
stage after restoring its entry scene, without velocity continuity claims.
"""
import copy
import time
import uuid

from a3d.core import StudioError, atomic_json, digest, inside, read_json, sha
from a3d.textile_executor import (STAGES, load_textile_program, split_group_payload, consolidate_group,
                                 assemble_component_fragments,mount_release_batches,component_continuity_proof)
from blender.textile_executor import (current_group, program_directory, program_identity, reference, verified,
    prepare_group_bundle,require_native_textile_program_admission)


def _group_object(directory, group_id):
    import bpy
    objects = [obj for obj in bpy.context.scene.objects if obj.get('a3d_textile_program_sha256') == program_identity(directory)
               and obj.get('a3d_textile_group_id') == group_id and obj.get('a3d_role') == 'textile-group-simulation']
    if len(objects) != 1: raise StudioError('Native textile group candidate is missing or duplicated')
    return objects[0]


def _component_copies(project, payload, recipes, record, directory, compiled, specification):
    import bpy
    from blender.sewing import make_object, mesh_recipe_digest
    outputs = []
    for cid in sorted(payload['source_components']):
        fragments = [];groups=[]
        for entry in compiled['groups']:
            if cid not in entry['payload']['source_components']: continue
            if entry['group']['id'] == record['group_id']:
                candidate = payload;group_ref=record['derived_mesh']
            else:
                prior = current_group(project, directory.parents[2], entry['group']['id'])
                if not prior or prior[0]['stage'] != 'drape': continue
                candidate = verified(project, prior[0]['derived_mesh']);group_ref=prior[0]['derived_mesh']
            fragments.append(split_group_payload(candidate, cid))
            groups.append({'group_id':entry['group']['id'],'derived_mesh_ref':group_ref,'payload':candidate})
        binding = next(row for row in specification['components'] if row['component_id'] == cid)
        source = verified(project, binding['derived_mesh_ref'])
        complete = {pid for part in fragments for pid in part['panels']} == set(source['panels'])
        part = assemble_component_fragments(source, fragments) if complete else split_group_payload(payload, cid)
        if complete:
            part['component_continuity']=component_continuity_proof(source,binding['derived_mesh_ref'],part,groups,
                record['program_ref'],binding['package_ref'],recipes[cid]['limits']['weld_gap_cm'])
        part['recipe_mesh_sha256'] = mesh_recipe_digest(recipes[cid])
        part['source_garment'] = source['source_garment']
        file = directory/(cid+'.mesh.json'); atomic_json(file, part)
        # Earlier group snapshots remain inspectable, but exactly one current
        # per-component candidate participates in inventory observations.
        for old in list(bpy.context.scene.objects):
            if complete and old.get('a3d_component_id') == cid:
                old['a3d_source_component_id'] = cid; del old['a3d_component_id']
                old['a3d_role'] = 'archived-before-textile-group'; old.hide_set(True); old.hide_render = True
        obj = make_object(part, 'A3D.TextileComponent.'+cid)
        obj['a3d_source_component_id'] = cid
        if complete: obj['a3d_component_id'] = cid
        else: obj['a3d_role'] = 'textile-component-fragment'
        obj['a3d_package_sha256'] = part['package_sha256']
        obj['a3d_sewing_mesh'] = file.relative_to(project.root).as_posix(); obj['a3d_sewing_mesh_sha256'] = sha(file)
        obj['a3d_textile_group_result'] = record['group_id']; obj['a3d_fitting'] = 'NOT_QUALIFIED'
        obj['a3d_physics_purpose']=specification['purpose'];obj['a3d_product_acceptance']='NOT_GRANTED'
        outputs.append({'component_id': cid, 'object': obj.name, 'derived_mesh': reference(project, file),
                        'purpose':specification['purpose'],'production_qualification':'NOT_GRANTED',
                        'source_pieces': sorted(part['panels']), 'component_coverage': 'COMPLETE' if complete else 'PARTIAL',
                        'qualification': 'GROUP_PHYSICS_ONLY',
                        'continuity_proof_sha256':part.get('component_continuity',{}).get('proof_sha256'),
                        'continuity_scope':'GEOMETRY_ONLY_COMPLETED_NATIVE_GROUP_ROOTS_REQUIRED' if complete else 'PARTIAL_UNQUALIFIED'})
    return outputs


def transition_textile_group(project_root, program_path, group_id, stage):
    import bpy
    from blender.operations import working
    from blender.sewing import (managed_inputs, structural_inputs, mesh_digest, make_object, object_mesh,
                                context_colliders, simulate_object, mesh_recipe_digest)
    from blender.preform import preform_coordinates
    from blender.pattern_assembly import collision_guard, dressing_measurement, validate_envelope_review
    from a3d.pattern_assembly import support_weights, bounded_close, continuous_quality
    project, session = working(project_root)
    if stage not in STAGES: raise StudioError('Unknown native textile group stage')
    spec, compiled = load_textile_program(project, program_path)
    admission=require_native_textile_program_admission(project,spec,compiled)
    entry = next((row for row in compiled['groups'] if row['group']['id'] == group_id), None)
    if entry is None: raise StudioError('Native stage group is not owned by the program')
    if len(entry['group']['layers']) > 1 and not spec.get('experimental_coupled_multilayer', False):
        raise StudioError('Coupled multilayer native stage requires the declared experimental path')
    directory = program_directory(project, program_path)
    prepared = directory/group_id/'prepared-bundle.json'
    if not prepared.is_file(): raise StudioError('Prepare the exact group bundle with advance_textile_program first')
    bundle_ref = read_json(prepared); bundle = verified(project, bundle_ref)
    # Reconstruct all policies from their hashed sources and actual completed
    # inner geometry. A rewritten mutable pointer cannot substitute weaker
    # quality/contact gates or different supports after preparation.
    expected_bundle, _ = prepare_group_bundle(project, program_path, group_id, persist=False)
    if digest(bundle) != digest(expected_bundle):
        raise StudioError('Prepared textile bundle differs from the exact source-bound recipe, plan or inner receipts')
    if (bundle.get('program_ref') != reference(project, inside(project.root, program_path)) or
            bundle['group'] != entry['group'] or digest(bundle['payload']) != digest(entry['payload'])):
        raise StudioError('Prepared textile bundle changed source group or program identity')
    for ref in bundle['inner_group_receipts']: verified(project, ref)
    prior = current_group(project, directory, group_id)
    expected = 'preposition' if prior is None else STAGES[STAGES.index(prior[0]['stage'])+1] if prior[0]['stage'] != 'drape' else None
    if stage != expected: raise StudioError('Group stages are sequential and single-use; expected '+str(expected))
    recipe, plan = copy.deepcopy(bundle['recipe']), copy.deepcopy(bundle['plan'])
    initial = copy.deepcopy(bundle['payload']); initial['recipe_mesh_sha256'] = mesh_recipe_digest(recipe)
    originals = []; prepared_sources = []
    if prior is None:
        for binding in spec['components']:
            cid = binding['component_id']
            if cid not in initial['source_components']: continue
            obj, source, original_recipe = managed_inputs(project, cid, binding['recipe_ref']['path'], check_placement=False)
            structural_inputs(obj, source, original_recipe)
            if digest(source) != initial['source_components'][cid]['source_map_sha256']:
                raise StudioError('Connected component no longer matches the program source mesh')
            if obj.get('a3d_pattern_preparation_receipt'):
                from blender.pattern_preparation import prepared_receipt
                admitted=prepared_receipt(project,obj,source,original_recipe,binding['plan_ref'])
                prepared_sources.append({'component_id':cid,'receipt':admitted[1]})
            if any('native_bend' in frame for pid, frame in plan['preform']['panels'].items()
                   if pid in initial['source_components'][cid]['pieces']) and obj.get('a3d_pattern_preparation_readiness') != 'READY':
                raise StudioError('Group native Bend requires the exact source READY preparation')
            originals.append(obj)
        payload = copy.deepcopy(initial)
    else:
        obj = _group_object(directory, group_id)
        payload = verified(project, prior[0]['derived_mesh'])
        if prior[0]['bundle_source_sha256'] != digest(initial):
            raise StudioError('Group continuation changed immutable source correspondence')
        actual, faces = object_mesh(obj)
        if faces != payload['faces'] or digest([[v*100 for v in p] for p in actual]) != digest(payload['placed_cm']):
            # Float32 Blender coordinates require the same numeric band as
            # existing sewing structural checks; identity stays mesh-bound.
            if faces != payload['faces'] or max(sum((a[i]*100-b[i])**2 for i in range(3))**.5
                    for a, b in zip(actual, payload['placed_cm'], strict=True)) > 1e-3:
                raise StudioError('Group connected topology or coordinates changed')
    output = directory/group_id/'stages'/('s-'+uuid.uuid4().hex[:16]); output.mkdir(parents=True,exist_ok=False)
    record = {'version': 1, 'origin': 'NATIVE_TEXTILE_GROUP', 'group_id': group_id, 'stage': stage,
              'purpose':spec['purpose'],'execution_admission':admission,'production_qualification':'NOT_GRANTED',
              'program_ref': bundle['program_ref'], 'bundle': bundle_ref, 'bundle_source_sha256': digest(initial),
              'previous': prior[1] if prior else None, 'simulation': 'NOT_EXECUTED',
              'qualification': 'EXPERIMENTAL_GROUP_STAGE_ONLY', 'fitting': 'NOT_QUALIFIED', 'accepted': False,
              'source_components': copy.deepcopy(payload['source_components']),
              'checkpoint': project.state().get('pending_blender_operation', {}).get('checkpoint'),
              'restart': 'ZERO_VELOCITY_AT_STAGE_BOUNDARY', 'velocity_continuity': 'NOT_CLAIMED'}
    started = time.monotonic(); temporary = None
    old_settings = (bpy.context.scene.frame_current, bpy.context.scene.frame_start, bpy.context.scene.frame_end,
                    bpy.context.scene.render.fps, bpy.context.scene.render.fps_base,
                    list(bpy.context.scene.gravity), bpy.context.scene.use_gravity)
    try:
        colliders, trees, snapshots = context_colliders(recipe)
        record['colliders'] = snapshots
        payload['pattern_assembly'] = {'version': 2, 'stage': stage, 'contact_policy': {'clearance_cm': plan['collision']['clearance_cm']}}
        active_collision = plan['collision'].get('mode', 'all_stages') != 'drape_only' or stage == 'drape'
        effective_plan = copy.deepcopy(plan)
        if not active_collision:
            colliders, trees, snapshots = [], [], []
            effective_plan['collision']['required'] = False
        check = collision_guard(payload, trees, snapshots, effective_plan, self_contacts=stage == 'close')
        if stage == 'preposition':
            if prepared_sources:
                if {row['component_id'] for row in prepared_sources}!=set(initial['source_components']):
                    raise StudioError('Group mixes prepared candidates with unprepared source components; prepare every component first')
                payload['placed_cm']=copy.deepcopy(initial['placed_cm'])
                record['preform']={'status':'SOURCE_READY_PREPARATIONS_REUSED','sources':prepared_sources,
                    'corrected_candidate_sha256':digest(initial['placed_cm']),'source_guide_replayed':False}
            else:payload['placed_cm'], record['preform'] = preform_coordinates(initial, plan)
            payload['pins'], record['supports'] = support_weights(payload, plan, 'assembly', 0.)
            record['collision'] = check(payload['placed_cm'])
            if not record['collision']['ok']: raise StudioError('Group source placement violates the unchanged collision reserve')
            if plan.get('dressing'):
                record['dressing'] = dressing_measurement(project, payload, plan, colliders,
                    {obj.name for obj in colliders}, initial['placed_cm'])
                if record['dressing']['status'] in ('NEEDS_CORRECTION', 'NEEDS_CLARIFICATION'):
                    raise StudioError('Group dressing/enfilage failed its source-bound admission')
        elif stage == 'close':
            payload['pins'], record['supports'] = support_weights(payload, plan, 'closure', plan['assembly']['closure_support_release'])
            payload['placed_cm'], record['closure'] = bounded_close(payload, payload['placed_cm'], effective_plan, collision_check=check)
            if record['closure']['status'] != 'GEOMETRY_READY': raise StudioError('Group permanent closure failed its unchanged geometric gates')
        elif stage == 'consolidate':
            payload, record['consolidation'] = consolidate_group(payload, payload['placed_cm'], plan)
            record['collision'] = collision_guard(payload, trees, snapshots, effective_plan, self_contacts=True)(payload['placed_cm'])
            if not record['collision']['ok']: raise StudioError('Group consolidation violates the unchanged collision reserve')
        else:
            if stage in ('relax', 'drape') and payload.get('rest_mode') != 'assembled_3d':
                raise StudioError('Group relaxation/drape requires approved permanent consolidation')
            phase = plan.get('cloth', {}).get(stage+'_phase', 'mount' if stage == 'mount' else 'drape')
            if phase not in recipe['phases']: raise StudioError('Group Cloth phase is missing')
            if recipe['phases'][phase]['frames'] > entry['group']['budgets']['max_frames']:
                raise StudioError('Group frame budget cannot execute the declared Cloth phase')
            if stage == 'drape' and not any(row['role'] == 'mannequin' for row in recipe['colliders']):
                raise StudioError('Whole-group drape needs the identified target body collider')
            if stage == 'drape':
                record['envelope_review'] = validate_envelope_review(project, plan, recipe, colliders)
                if plan.get('dressing', {}).get('required'):
                    record['dressing_entry'] = dressing_measurement(project, payload, plan, colliders,
                        {obj.name for obj in colliders}, initial['placed_cm'], check_milestones=False)
                    if record['dressing_entry']['status'] != 'READY':
                        raise StudioError('Group drape entry lacks admitted measured dressing geometry')
            releases = plan.get('cloth', {}).get('mount_release_steps', [0., .5, 1.]) if stage == 'mount' else [1.]
            frames = recipe['phases'][phase]['frames']
            if frames < 2*len(releases): raise StudioError('Group frame budget cannot cover support release transitions')
            record['cloth_runs'] = []
            if stage=='mount':batches=mount_release_batches(payload,plan,releases,frames)
            else:
                pins,support=support_weights(payload,plan,stage,1.)
                batches=[{'pins':pins,'support':support,'frames':frames,'releases':[1.]}]
            for number,batch in enumerate(batches):
                payload['pins'],support=copy.deepcopy(batch['pins']),copy.deepcopy(batch['support'])
                support['declared_release_steps']=batch['releases']
                payload['pattern_assembly']['temporary_supports_active'] = support['temporary_supports_active']
                trial_recipe = copy.deepcopy(recipe)
                trial_recipe['colliders'] = recipe['colliders'] if active_collision else []
                if not active_collision: trial_recipe['no_collision_reason'] = plan['collision']['source_ref']
                trial_recipe['phases'][phase]['frames'] = batch['frames']
                if stage == 'mount':
                    trial_recipe['limits']['max_seam_gap_cm'] = plan['assembly']['max_initial_gap_cm']
                    trial_recipe['limits']['max_displacement_cm'] = plan['assembly']['max_displacement_cm']
                temporary = make_object(payload, 'A3D.TextileTrial.'+uuid.uuid4().hex[:8])

                def progress(rows):
                    atomic_json(output/('progress-'+str(number)+'.json'), {'frames': rows, 'support_transition': support})
                    if time.monotonic()-started >= entry['group']['budgets']['max_seconds']:
                        raise StudioError('Group simulation time budget exhausted; restore entry checkpoint before replay')
                def diagnostic(data):
                    atomic_json(output/('physical-failure-'+str(number)+'.json'),data)
                coordinates, physical = simulate_object(temporary, payload, trial_recipe, phase, colliders, trees, progress,diagnostic)
                payload['placed_cm'] = coordinates; physical['support_transition'] = support
                record['cloth_runs'].append(physical)
                bpy.data.objects.remove(temporary, do_unlink=True); temporary = None
            record['simulation'] = 'PASS'
            if stage == 'drape':
                record['qualification'] = 'GROUP_DRAPE_PHYSICS_ONLY'
                if plan.get('dressing', {}).get('required'):
                    record['dressing'] = dressing_measurement(project, payload, plan, colliders,
                        {obj.name for obj in colliders}, initial['placed_cm'], check_milestones=False)
                    if record['dressing']['status'] != 'READY':
                        raise StudioError('Group drape final dressing geometry failed its unchanged gates')
        record['quality'] = continuous_quality(payload, payload['placed_cm'], plan['quality'])
        if time.monotonic()-started >= entry['group']['budgets']['max_seconds']:
            raise StudioError('Group stage time budget exhausted; restore entry checkpoint before replay')
        if prior:
            old = _group_object(directory, group_id)
            old['a3d_role'] = 'archived-textile-group'; old.hide_set(True); old.hide_render = True
        for obj in originals:
            # Several ordered groups may own disjoint pieces of this same
            # source component. Retain its exact source object until every
            # piece has a completed native result; its source map stays valid.
            obj.hide_render = True
        file = output/'mesh.json'; atomic_json(file, payload)
        obj = make_object(payload, 'A3D.TextileGroup.'+group_id)
        obj['a3d_role'] = 'textile-group-simulation'; obj['a3d_textile_program_sha256'] = program_identity(directory)
        obj['a3d_textile_group_id'] = group_id
        obj['a3d_physics_purpose']=spec['purpose'];obj['a3d_product_acceptance']='NOT_GRANTED'
        record['object'] = obj.name; record['mesh_sha256'] = mesh_digest(obj); record['derived_mesh'] = reference(project, file)
        if stage == 'drape':
            recipes = {row['component_id']: verified(project, row['recipe_ref']) for row in spec['components']}
            record['component_results'] = _component_copies(project, payload, recipes, record, output, compiled, spec)
            obj.hide_render = True
        record['status'] = 'GROUP_STAGE_COMPLETED'; record['elapsed_seconds'] = time.monotonic()-started
        receipt_file = output/'receipt.json'; atomic_json(receipt_file, record); ref = reference(project, receipt_file)
        obj['a3d_textile_group_receipt'] = ref['path']; obj['a3d_textile_group_receipt_sha256'] = ref['sha256']
        atomic_json(directory/group_id/'latest.json', ref)
        (current, start, end, fps, fps_base, gravity, use_gravity) = old_settings
        bpy.context.scene.frame_start = start; bpy.context.scene.frame_end = end
        bpy.context.scene.render.fps = fps; bpy.context.scene.render.fps_base = fps_base
        bpy.context.scene.gravity = gravity; bpy.context.scene.use_gravity = use_gravity
        bpy.context.scene.frame_set(current)
        bpy.ops.wm.save_as_mainfile(filepath=session['working'], check_existing=False)
        return {**record, 'receipt': ref}
    except Exception as error:
        try:
            atomic_json(output/'failure.json', {**record, 'status': 'REFUSED', 'error': str(error),
                'elapsed_seconds': time.monotonic()-started, 'recovery': 'RESTORE_ENTRY_CHECKPOINT_AND_REPLAY'})
        except Exception as preservation_error:
            error.add_note('Native failure artifact could not be saved: '+repr(preservation_error))
        raise
    finally:
        if temporary is not None and temporary.name in bpy.data.objects: bpy.data.objects.remove(temporary, do_unlink=True)
        (current, start, end, fps, fps_base, gravity, use_gravity) = old_settings
        bpy.context.scene.frame_start = start; bpy.context.scene.frame_end = end
        bpy.context.scene.render.fps = fps; bpy.context.scene.render.fps_base = fps_base
        bpy.context.scene.gravity = gravity; bpy.context.scene.use_gravity = use_gravity
        bpy.context.scene.frame_set(current)
