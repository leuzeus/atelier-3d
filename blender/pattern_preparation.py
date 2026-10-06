"""Checkpointed source-pattern preparation with inspectable, unqualified outputs."""
import copy
import math
import uuid

from a3d.core import StudioError,atomic_json,contract,digest,inside,read_json,sha
from blender.pattern_assembly import reference,verified_reference,collision_guard,validate_envelope_review
from blender.sewing import build_mesh,make_object,mesh_digest,mesh_recipe_digest,context_colliders,simulation_quality


RETIRED_PREPARATIONS=('experimental_prefit','interface_preparation','panel_mount',
    'fitting_placement','contact_recovery','fitting_pose','fitting_tacks')


def meshing_partial_diagnostic(error):
    """Failure observations only; never serialize a native Vector candidate."""
    partial=getattr(error,'bounded_meshing_partial',None)
    if not isinstance(partial,dict):return None
    result={key:copy.deepcopy(partial.get(key)) for key in
            ('qualification','admission','active_piece','interior_grid',
             'last_completed_work_snapshot','snapshot_scope','costs_refunded')}
    result['best_safe_candidate_recorded_in_exception']=partial.get('best_safe_candidate') is not None
    result['candidate_admitted']=False
    return result


def preform_supports(payload,plan,coordinates):
    """Resolve the same source supports even when an initial guide is refused."""
    from a3d.pattern_assembly import support_weights
    from a3d.sewing import permanent_support_groups,distance
    weights,report=support_weights(payload,plan,'assembly',release=0.)
    source=payload.get('source_pins',{})
    report['source_pin_transition']={key:{'source_weight':source.get(key,0.),'prepared_weight':weights.get(key,0.)}
        for key in source.keys()|weights.keys() if source.get(key,0.)!=weights.get(key,0.)}
    variations=[];conflicts=[]
    for group in permanent_support_groups(payload):
        cohort={str(i):weights.get(str(i),0.) for i in group}
        if len(set(cohort.values()))>1:variations.append(cohort)
        fixed=[i for i in group if cohort[str(i)]>=1.]
        if any(distance(coordinates[a],coordinates[b])>plan['consolidation']['weld_gap_cm'] for a in fixed for b in fixed):conflicts.append(fixed)
    report.update(permanent_cohort_weight_variations=variations,contradictory_fixed_cohorts=conflicts)
    return weights,report


def migrate_preparation_recipe(source_recipe,spec):
    """Retire only redundant mechanics in a copy; never transfer qualification."""
    requested=spec.get('migration',{}).get('retire_legacy_preparations') is True
    retired={key:copy.deepcopy(source_recipe[key]) for key in RETIRED_PREPARATIONS if key in source_recipe}
    if requested and not spec.get('assembly_plan'):
        raise StudioError('Legacy preparation migration requires a sourced assembly plan reference')
    if retired and not requested:
        raise StudioError('Legacy preparation fields require explicit retire_legacy_preparations migration')
    recipe=copy.deepcopy(source_recipe)
    for key in retired:del recipe[key]
    return recipe,{'status':'MIGRATED' if retired else 'NOT_REQUIRED','retired_fields':retired,
        'source_recipe_sha256':digest(source_recipe),'prepared_recipe_sha256':digest(recipe),
        'source_inputs_preserved':True,'source_package_approval_retained':True,
        'physics_validation_transferred':False,'fitting_validation_transferred':False,
        'source_mutated':False,'replacement_plan':spec.get('assembly_plan')}


def prepared_receipt(project,obj,payload,recipe,plan_ref):
    """Admit only exact READY geometry; never replay placement on its result."""
    path=obj.get('a3d_pattern_preparation_receipt')
    if not path:return None
    ref={'path':path,'sha256':obj.get('a3d_pattern_preparation_receipt_sha256')}
    record=read_json(verified_reference(project,ref))
    if record.get('readiness')!='READY' or record.get('simulation')!='NOT_EXECUTED' or record.get('accepted') is not False:
        raise StudioError('Pattern assembly requires a READY preparation; inspect its corrections or missing inputs first')
    if record.get('validation_contract',{}).get('version')!=2:
        raise StudioError('Legacy READY keeps its historical metric/contact scope; prepare again with the current validator')
    if (record.get('component_id')!=payload['component_id'] or record.get('package_sha256')!=payload['package_sha256']
            or record.get('recipe_sha256')!=digest(recipe) or record.get('assembly_plan')!=plan_ref
            or record.get('derived_mesh',{}).get('sha256')!=obj.get('a3d_sewing_mesh_sha256')
            or record.get('mesh_sha256')!=mesh_digest(obj)):
        raise StudioError('Prepared geometry, recipe, source mapping or plan changed; prepare again')
    verified_reference(project,record['derived_mesh'])
    correction=record.get('placement_correction')
    if correction:
        observed=read_json(verified_reference(project,correction['receipt']))
        if (correction.get('candidate_sha256')!=digest(payload['placed_cm'])
                or observed.get('candidate_sha256')!=digest(payload['placed_cm'])
                or observed.get('status')!='GEOMETRIC_GATES_PASSED'):
            raise StudioError('Prepared native placement correction changed or was not geometrically admitted')
    spec=read_json(verified_reference(project,record['preparation_spec']))
    if spec.get('meshing_profile'):
        from a3d.meshing_profile import profile_binding
        observation=record.get('meshing_observation',{})
        work=payload.get('meshing_work',{})
        if (observation.get('status')!='COMPLETED_MESH_BUILD_ONLY'
            or payload.get('meshing_profile')!=profile_binding(spec['meshing_profile'])
            or observation.get('profile')!=payload.get('meshing_profile')
            or observation.get('work')!=work or work.get('component_id')!=payload['component_id']
            or work.get('qualification')!='NONE' or work.get('admission')!='NONE'
            or type(work.get('last_checkpoint'))not in(int,float)
            or type(work.get('absolute_deadline'))not in(int,float)
            or not work['last_checkpoint']<work['absolute_deadline']):
            raise StudioError('Prepared synchronized meshing observation is missing, expired or changed')
    for key in ('assembly_plan','construction_dossier'):
        if spec.get(key):verified_reference(project,spec[key])
    verified_reference(project,record['recipe'])
    verified_reference(project,record['construction_dossier'])
    from a3d.dressing import source_references
    for source in source_references(read_json(verified_reference(project,plan_ref))):verified_reference(project,source)
    migration=record.get('recipe_migration',{})
    if migration.get('archived_source_recipe'):
        legacy=read_json(verified_reference(project,migration['archived_source_recipe']))
        if digest(legacy)!=migration.get('source_recipe_sha256') or digest(recipe)!=migration.get('prepared_recipe_sha256'):
            raise StudioError('Prepared recipe migration provenance changed')
    return record,ref


def _area(payload):
    total=0.
    for face in payload['faces']:
        a,b,c=(payload['rest_cm'][i] for i in face)
        total+=abs((b[0]-a[0])*(c[1]-a[1])-(b[1]-a[1])*(c[0]-a[0]))/2
    return total


def _placement_displacement(payload,source_placement,coords,limit):
    from a3d.sewing import distance
    displacements=[distance(a,b) for a,b in zip(source_placement,coords,strict=True)]
    maximum=max(displacements,default=0.);index=displacements.index(maximum) if displacements else None
    return {'max_cm':maximum,'limit_cm':limit,'within_budget':maximum<=limit+1e-8,
        'source':'METRIC_RECIPE_DERIVED_PLACEMENT','target':'PREPARATION_PREFORM',
        'vertex':index,'source_uv_cm':payload['rest_cm'][index][:2] if index is not None else None,
        'pieces':[pid for pid,panel in payload['panels'].items() if index in panel['indices']]}


def _material_assessment(data,recipe,spec,payload):
    from a3d.sewing import mass_settings
    profiles=spec.get('material_profiles',[]);problems=[];owners={}
    bindings=[]
    for profile in profiles:
        for piece in profile['pieces']:
            if piece not in data['pieces'] or piece in owners:
                problems.append('Material profiles must partition existing source panels without duplicate assignments')
            owners[piece]=profile['id']
        declared=profile.get('cloth_profile')
        phases={}
        for name,phase in recipe['phases'].items():
            regional=phase.get('regional_stiffness')
            actual={piece:'phase_base' for piece in profile['pieces']}
            if regional:
                known={p['id'] for p in regional['profiles']}
                assigned={item['piece']:item['profile'] for item in regional['assignments']}
                actual={piece:assigned.get(piece,regional['default_profile']) for piece in profile['pieces']}
                if declared and declared not in known:
                    problems.append(f"Material {profile['id']} references absent Cloth profile {declared} in phase {name}")
            if declared and any(value!=declared for value in actual.values()):
                problems.append(f"Material {profile['id']} Cloth profile does not match its source-panel assignments in phase {name}")
            phases[name]={'base_profiles_by_piece':actual,
                'reinforcements':copy.deepcopy(regional.get('reinforcements',[])) if regional else []}
        bindings.append({'id':profile['id'],'category':profile.get('category'),'cloth_profile':declared,
            'cloth_profile_status':'EXPLICIT' if declared else 'INFERRED_FROM_UNCHANGED_RECIPE',
            'visual_material_ref':profile.get('visual_material_ref'),
            'visual_material_assignment':'REFERENCE_ONLY_NOT_APPLIED_TO_SIMULATION','phases':phases})
    densities={profile['areal_density_kg_m2'] for profile in profiles}
    if profiles and set(owners)!=set(data['pieces']):problems.append('Material profiles do not cover every source panel')
    if len(densities)>1:problems.append('One native Cloth object cannot realize distinct per-panel masses through its scalar mass setting; pin groups are not mass fields')
    if spec.get('mass_policy','native_uniform_vertex')=='require_exact_surface_density':
        problems.append('Exact tributary-area mass per vertex is not exposed by the native Cloth scalar mass setting')
    assignment=None
    if payload and payload['rest_cm']:
        area=_area(payload)
        assignment={phase:mass_settings(recipe['mass'],area,len(payload['rest_cm']),profile['sewing_force_per_kg'])
            for phase,profile in recipe['phases'].items()}
        if len(densities)==1:
            density=next(iter(densities));native_total=next(iter(assignment.values()))['total_mass_kg']
            if not math.isclose(density*area/10000,native_total,rel_tol=1e-6,abs_tol=1e-9):
                problems.append('Declared profile density does not match the unchanged native recipe mass')
    return {'profiles':profiles,'profile_bindings':bindings,'native_assignment':'uniform_per_vertex','configured_assignment':assignment,
        'profile_controls':{name:{'regional_stiffness':phase.get('regional_stiffness'),
            'stiffness':{k:phase[k] for k in ('tension_stiffness','compression_stiffness','shear_stiffness','bending_stiffness')}}
            for name,phase in recipe['phases'].items()},
        'limitations':problems,'simulation':'NOT_EXECUTED','pin_group_is_mass_distribution':False}


def prepare_pattern_assembly(project_root,component_id,recipe_path,preparation_path):
    import time
    meshing_started=time.monotonic()
    import bpy
    from blender.operations import working
    from a3d.packages import extract_package
    from a3d.pattern_assembly import map_digest,support_weights
    from blender.preform import preform_coordinates
    from a3d.pattern_preparation import audit_source,preparation_statistics,assess_preparation
    project,session=working(project_root)
    _,component=project.ready(component_id)
    if component['route']['selected']!='PATTERN_SEWN' or component['stage']=='RECONSTRUCTED':
        raise StudioError('Pattern preparation requires an unaccepted reviewed PATTERN_SEWN source package')
    spec_path=inside(project.root,preparation_path);spec=contract('pattern-preparation',read_json(spec_path))
    recipe_file=inside(project.root,recipe_path);source_recipe=contract('sewing-recipe',read_json(recipe_file))
    recipe,migration=migrate_preparation_recipe(source_recipe,spec)
    meshing_envelope=None
    if spec.get('meshing_profile'):
        from a3d.meshing_profile import create_envelope
        meshing_envelope=create_envelope(spec['meshing_profile'],component_id,recipe,
            spec['regular_mesh'],started_at=meshing_started)
        meshing_envelope.check('before_source_package_capture')
    if spec['component_id']!=component_id or recipe['component_id']!=component_id:raise StudioError('Preparation component mismatch')
    if spec['regular_mesh']['min_spacing_cm']>spec['regular_mesh']['spacing_cm']:
        raise StudioError('Regular preparation minimum spacing cannot exceed its base spacing')
    package=inside(project.root,component['package']['path'])
    if sha(package)!=component['package']['sha256']:raise StudioError('Approved source package changed')
    directory=project.data/('blender/pattern-preparation/attempt-'+uuid.uuid4().hex);directory.mkdir(parents=True)
    if migration['retired_fields']:
        import shutil
        archived_recipe=directory/'legacy-recipe.json';shutil.copyfile(recipe_file,archived_recipe)
        migration['archived_source_recipe']=reference(project,archived_recipe)
    output_recipe=directory/'recipe.json';atomic_json(output_recipe,recipe)
    source_dir=directory/'source';manifest=extract_package(package,source_dir)
    data=read_json(source_dir/'garment.json')
    if data['component_id']!=component_id:raise StudioError('Extracted source component mismatch')
    from a3d.planning import require_board
    board=require_board(project,project.state())
    dossier_ref={'path':board['dossier_path'],'sha256':board['dependencies'][board['dossier_path']]}
    if spec.get('construction_dossier') and spec['construction_dossier']!=dossier_ref:
        raise StudioError('Preparation cutting metadata must be the exact dossier bound to the approved construction board')
    dossier=read_json(verified_reference(project,dossier_ref))
    problems=[]
    def problem(kind,category,message):problems.append({'readiness':kind,'category':category,'message':str(message)})
    try:source_audit=audit_source(data,recipe,dossier)
    except StudioError as exc:
        source_audit={'status':'NEEDS_CORRECTION','source_sha256':digest(data),'error':str(exc),
            'issues':[{'category':'source_contract','code':'SOURCE_AUDIT_ERROR','message':str(exc)}]}
        problem('NEEDS_CORRECTION','source_pattern',exc)
    payload=None;plan=None;plan_ref=None;obj=None;preform=None;collision=None;statistics=None;dressing=None;layer_migration=None;placement_correction=None
    meshing_observation=None
    try:
        if meshing_envelope is not None:
            payload=build_mesh(data,recipe,regular_mesh=spec['regular_mesh'],dossier=dossier,
                meshing_profile=spec['meshing_profile'],meshing_envelope=meshing_envelope)
        else:payload=build_mesh(data,recipe,regular_mesh=spec['regular_mesh'],dossier=dossier)
        if meshing_envelope is not None:
            meshing_observation={'status':'COMPLETED_MESH_BUILD_ONLY','qualification':'NONE',
                'work':copy.deepcopy(payload['meshing_work']),'profile':copy.deepcopy(payload['meshing_profile'])}
    except StudioError as exc:
        payload=getattr(exc,'garment_payload',None)
        problem('NEEDS_CORRECTION','derived_mesh_or_initial_placement',exc)
        if meshing_envelope is not None:
            meshing_observation={'status':'REFUSED_OR_INCOMPLETE_MESH_BUILD','qualification':'NONE',
                'reason':getattr(exc,'reason',None),'execution_status':getattr(exc,'status',None),
                'message':str(exc),'last_phase':meshing_envelope.phase,
                'attempted_work':dict(meshing_envelope._counts),'costs_refunded':False,
                'owner_attempted_work':copy.deepcopy(meshing_envelope._owner_counts),
                'last_observed_elapsed_seconds':meshing_envelope._last_clock-meshing_envelope.start,
                'elapsed_scope':'LAST_COOPERATIVE_CLOCK_CHECK_NOT_COMPLETE_OPERATION_DURATION',
                'bounded_partial':meshing_partial_diagnostic(exc),
                'terminal_snapshot':'NOT_AVAILABLE_NO_SUCCESS_CLOCK_CHECK',
                'native_diagnostic':getattr(exc,'diagnostic',None)}
            problem('NEEDS_CORRECTION','synchronized_meshing_incomplete',
                'Synchronized mesh has no completed terminal observation; preform cannot clear this refusal')
    if payload:
        payload.update(package_sha256=component['package']['sha256'],source_garment=(source_dir/'garment.json').relative_to(project.root).as_posix(),
            source_pins=copy.deepcopy(payload['pins']),full_rest_area_cm2=_area(payload))
        if session.get('construction_id'):payload['construction_id']=session['construction_id']
        source_placement=copy.deepcopy(payload['placed_cm'])
        initial_preform_problem=None
        initial_preform_can_reconcile=False
        if spec.get('assembly_plan'):
            original_plan=contract('pattern-assembly',read_json(verified_reference(project,spec['assembly_plan'])))
            if original_plan['component_id']!=component_id:raise StudioError('Preparation assembly plan component mismatch')
            plan=copy.deepcopy(original_plan);plan['mapping_sha256']=map_digest(payload)
            from a3d.dressing import rebind_layer_execution
            plan=rebind_layer_execution(plan,payload)
            if 'layers' not in plan:
                from a3d.dressing import migrate_legacy_layers
                roles={item['object']:'body' if item['role']=='mannequin' else 'unknown' for item in recipe['colliders']}
                layer_migration=migrate_legacy_layers(payload,roles,spec['assembly_plan'])
                if layer_migration['layers']:plan['layers']=layer_migration['layers']
                else:problem('NEEDS_CLARIFICATION','layer_order',layer_migration['reason'])
            try:
                if spec.get('source_preform_budget'):
                    from a3d.textile_executor import verify_source_preform_budget
                    verify_source_preform_budget(data,plan['preform']['panels'],recipe['placements'],spec['source_preform_budget'])
                coords,preform=preform_coordinates(payload,plan)
                payload['placed_cm']=coords
                payload['pins'],support=preform_supports(payload,plan,coords)
                if support['contradictory_fixed_cohorts']:problem('NEEDS_CORRECTION','support_conflict','Fixed declared supports prevent their permanent seam partners from closing within tolerance')
                preform['supports']=support
                # The regular derivation is checked in its actual preform below.
                problems[:]=[p for p in problems if p['category']!='derived_mesh_or_initial_placement']
            except StudioError as exc:
                if getattr(exc,'preform_coordinates_cm',None):payload['placed_cm']=exc.preform_coordinates_cm
                initial_preform_can_reconcile=bool(getattr(exc,'preform_coordinates_cm',None))
                preform={'status':'NEEDS_CORRECTION','error':str(exc),
                    'correspondence':getattr(exc,'preform_correspondence',None),
                    'native_backends':getattr(exc,'preform_native_backends',{})}
                initial_preform_problem={'readiness':'NEEDS_CORRECTION','category':getattr(exc,'reason_category','preform'),'message':str(exc)}
                problems.append(initial_preform_problem)
                if getattr(exc,'preform_coordinates_cm',None):
                    try:
                        payload['pins'],support=preform_supports(payload,plan,payload['placed_cm']);preform['supports']=support
                        if support['contradictory_fixed_cohorts']:
                            problem('NEEDS_CORRECTION','support_conflict','Fixed declared supports prevent their permanent seam partners from closing within tolerance')
                    except StudioError as support_error:problem('NEEDS_CORRECTION','support_conflict',support_error)
            preform_limit=spec.get('source_preform_budget',{}).get('max_displacement_cm',plan['assembly']['max_displacement_cm'])
            displacement=_placement_displacement(payload,source_placement,payload['placed_cm'],preform_limit)
            displacement['budget_basis']='SOURCE_GUIDE_STAGING' if spec.get('source_preform_budget') else 'LEGACY_ASSEMBLY_DISPLACEMENT'
            displacement['physical_assembly_limit_cm']=plan['assembly']['max_displacement_cm']
            preform['placement_displacement']=displacement
            if not displacement['within_budget']:
                problem('NEEDS_CORRECTION','placement_budget',f"Preform displacement {displacement['max_cm']:.6g} cm exceeds its declared {displacement['limit_cm']:.6g} cm budget at source vertex {displacement['vertex']}")
            plan_path=directory/'assembly-plan.json';atomic_json(plan_path,plan);plan_ref=reference(project,plan_path)
            rebind={'source_plan':spec['assembly_plan'],'old_mapping_sha256':original_plan['mapping_sha256'],
                'new_mapping_sha256':plan['mapping_sha256'],'method':'SOURCE_IDS_AND_UV_REINTERPOLATION_NEW_ARC_MAPPING',
                'source_recipe_sha256':digest(recipe),'geometry_not_copied_from_old_triangulation':True}
        else:
            rebind=None;problem('NEEDS_CLARIFICATION','preform','A sourced target preform and explicit support roles are required before mounting')
        try:
            colliders,trees,snapshots=context_colliders(recipe)
            selected={o.name for o in colliders}
            if plan:
                from a3d.dressing import layer_collision_selection
                selection=layer_collision_selection(payload,plan,{item['object']:item['role'] for item in recipe['colliders']})
                if selection['status']=='LAYER_COLLIDERS_SELECTED':selected=set(selection['colliders'])
                else:problem('NEEDS_CLARIFICATION','layer_order',selection['reason'])
            inward=[(o,t,s) for o,t,s in zip(colliders,trees,snapshots,strict=True) if o.name in selected]
            collision_plan=copy.deepcopy(plan) if plan else {'collision':{'required':bool(recipe['colliders']),'clearance_cm':0.},'consolidation':{'weld_gap_cm':recipe['limits']['weld_gap_cm']}}
            if plan and spec.get('placement_correction'):
                from blender.placement_correction import correct_preparation
                before_correction=copy.deepcopy(payload['placed_cm'])
                try:
                    anchor_options={}
                    if spec.get('anchor_reserve_correction'):
                        from blender.anchor_reserve import verified_anchor_body
                        anchor_options['anchor_body']=verified_anchor_body(project,recipe,plan,spec)
                    placement_correction=correct_preparation(payload,recipe,plan,spec,[item[0] for item in inward],**anchor_options)
                    payload['placed_cm']=copy.deepcopy(placement_correction['coordinates_cm'])
                    if placement_correction['status']!='GEOMETRIC_GATES_PASSED':
                        problem('NEEDS_CORRECTION','placement_correction',placement_correction['stop_reason'])
                    elif initial_preform_problem and initial_preform_can_reconcile:
                        # Only the precise initial-guide error is superseded.
                        # Source/support/layer/audit issues and the final native
                        # preparation validator remain independently required.
                        problems[:]=[row for row in problems if row is not initial_preform_problem]
                        preform['initial_guide_failure']=copy.deepcopy(initial_preform_problem)
                        preform.update(status='CORRECTED_CANDIDATE_PREPOSITIONED',
                            corrected_candidate_sha256=digest(payload['placed_cm']),
                            correspondence_domain='ORIGINAL_SOURCE_GUIDE_BEFORE_CORRECTION')
                except StudioError as exc:
                    placement_correction={'status':'NEEDS_CORRECTION','error':str(exc),
                        'quality_violations':getattr(exc,'quality_violations',[]),
                        'contact_report':getattr(exc,'contact_report',None),'qualification':'NONE','simulation':'NOT_EXECUTED'}
                    problem('NEEDS_CORRECTION','placement_correction',exc)
                if spec.get('source_preform_budget'):
                    correction_limit=min(plan['assembly']['max_displacement_cm'],spec['placement_correction']['budgets']['max_displacement_cm'])
                    correction_delta=_placement_displacement(payload,before_correction,payload['placed_cm'],correction_limit)
                    correction_delta.update(source='SOURCE_GUIDE_PREFORM',target='CORRECTED_PREFORM',budget_basis='UNCHANGED_CORRECTION_AND_ASSEMBLY_LIMITS')
                    placement_correction['displacement_from_source_guide']=correction_delta
                    total_limit=preform_limit+correction_limit
                    if not correction_delta['within_budget']:
                        problem('NEEDS_CORRECTION','placement_budget','Correction exceeds its unchanged displacement budget from the declared source guide')
                else:total_limit=plan['assembly']['max_displacement_cm']
                corrected_displacement=_placement_displacement(payload,source_placement,payload['placed_cm'],total_limit)
                corrected_displacement['budget_basis']='SOURCE_GUIDE_BOUND_PLUS_UNCHANGED_CORRECTION_LIMIT' if spec.get('source_preform_budget') else 'LEGACY_ASSEMBLY_DISPLACEMENT'
                placement_correction['total_source_placement_displacement']=corrected_displacement
                if not corrected_displacement['within_budget']:
                    problem('NEEDS_CORRECTION','placement_budget','Corrected preform exceeds its declared total source-placement bound')
                correction_path=directory/'placement-correction.json';atomic_json(correction_path,placement_correction)
                placement_correction={'assessment':placement_correction['status'],'receipt':reference(project,correction_path),
                    'candidate_sha256':digest(payload['placed_cm']),'qualification':'NONE',
                    'final_readiness':'UNCHANGED_PREPARATION_VALIDATOR_REQUIRED'}
            # Preparation inspects the declared target even if assembly later
            # elects a collider-free mounting phase. No deep contact is hidden.
            collision=collision_guard(payload,[item[1] for item in inward],[item[2] for item in inward],collision_plan,self_contacts=True)(payload['placed_cm'])
            collision['declared_colliders']=snapshots;collision['stage_activation']='ALL_DECLARED_TARGETS_FOR_PREPARATION_AUDIT'
            if not collision['ok']:problem('NEEDS_CORRECTION','placement_or_layer_contacts','The prepared preform violates collision reserve or separate-layer contact checks')
            if plan:
                try:collision['envelope_review']=validate_envelope_review(project,plan,recipe,colliders)
                except StudioError as exc:problem('NEEDS_CLARIFICATION','collision_envelope_review',exc)
                from blender.pattern_assembly import dressing_measurement
                dressing=dressing_measurement(project,payload,plan,colliders,selected,source_placement)
                if dressing['status'] in ('NEEDS_CORRECTION','NEEDS_CLARIFICATION'):
                    problem(dressing['status'],'placement_enfilage',dressing.get('reason') or 'Sourced dressing geometry is not admitted')
        except StudioError as exc:
            collision={'ok':False,'error':str(exc)};problem('NEEDS_CLARIFICATION','collision_context',exc)
        preparation_limits={**recipe['mesh'],'min_angle_degrees':max(recipe['mesh']['min_angle_degrees'],spec['regular_mesh'].get('target_min_angle_degrees',15.))}
        try:simulation_quality(payload,payload['placed_cm'],preparation_limits)
        except StudioError as exc:problem('NEEDS_CORRECTION','strict_native_geometry',exc)
        try:statistics=preparation_statistics(payload,payload['placed_cm'],recipe['mass'])
        except StudioError as exc:
            statistics={'status':'UNAVAILABLE','error':str(exc)};problem('NEEDS_CORRECTION','geometry_statistics',exc)
        materials=_material_assessment(data,recipe,spec,payload)
        for message in materials['limitations']:problem('NEEDS_CLARIFICATION','native_material_mass',message)
        try:assessment=assess_preparation(payload,recipe,plan,collision,source_audit)
        except StudioError as exc:
            assessment={'status':'NEEDS_CORRECTION','error':str(exc)}
        if assessment.get('status') in ('NEEDS_CORRECTION','NEEDS_CLARIFICATION','REFUSED'):
            codes=[r.get('code','UNSPECIFIED') for r in assessment.get('reasons',[])]
            problem(assessment['status'] if assessment['status']!='REFUSED' else 'NEEDS_CORRECTION','preparation_assessment',
                ', '.join(codes) or assessment.get('error','Preparation needs correction'))
        readiness='NEEDS_CORRECTION' if any(p['readiness']=='NEEDS_CORRECTION' for p in problems) else 'NEEDS_CLARIFICATION' if problems else 'READY'
        payload['pattern_preparation']={'version':1,'readiness':readiness,'source_map_sha256':map_digest(payload)}
        payload['recipe_mesh_sha256']=mesh_recipe_digest(recipe)
        mesh_path=directory/'mesh.json';atomic_json(mesh_path,payload)
        obj=make_object(payload,'A3D.Prepared.'+component_id)
        obj['a3d_package_sha256']=payload['package_sha256'];obj['a3d_source_component_id']=component_id
        obj['a3d_sewing_mesh']=mesh_path.relative_to(project.root).as_posix();obj['a3d_sewing_mesh_sha256']=sha(mesh_path)
        obj['a3d_role']='preparation-candidate'
        derived=reference(project,mesh_path)
    else:
        readiness='NEEDS_CORRECTION';materials=_material_assessment(data,recipe,spec,None)
        assessment={'status':readiness,'reason':'No safe derived mesh could be constructed'};derived=None;rebind=None
    record={'schema_version':1,'operation':'prepare_pattern_assembly','component_id':component_id,
        'readiness':readiness,'package_sha256':component['package']['sha256'],'source_garment_sha256':digest(data),
        'source_package':reference(project,package),'preparation_spec':reference(project,spec_path),
        'construction_dossier':dossier_ref,
        'source_recipe':reference(project,recipe_file),'recipe':reference(project,output_recipe),
        'placement_correction':placement_correction,
        'recipe_sha256':digest(recipe),'derived_mesh':derived,
        'recipe_migration':migration,
        'assembly_plan':plan_ref,'mapping_rebind':rebind,'source_audit':source_audit,'preform':preform,
        'dressing':dressing,'layer_migration':layer_migration,
        'validation_contract':{'version':2,'metrics':'cloth-metrics/2','contacts':'triangle-contact/1',
            'dressing':dressing['status'] if dressing else 'NOT_ASSESSED','qualification':'PREPARATION_ONLY'},
        'statistics':statistics,'materials':materials,'collision':collision,'assessment':assessment,'problems':problems,
        'checkpoint':project.state()['pending_blender_operation']['checkpoint'],
        'object':obj.name if obj else None,'mesh_sha256':mesh_digest(obj) if obj else None,
        'simulation':'NOT_EXECUTED','fitting':'NOT_QUALIFIED','behavior':'NOT_QUALIFIED',
        'visual_validation':'NOT_EXECUTED','accepted':False,'export_eligible':False}
    if meshing_envelope is not None:record['meshing_observation']=meshing_observation
    from blender.piece_inventory import collect, remember_candidate, save_report
    remember_candidate(project, component_id, obj)
    coverage = collect(project, component_id, focus=obj, previews=True)
    record['piece_completeness'] = coverage
    record['summary'] = coverage['summary']
    record['next_piece_review'] = 'Present this local/global coverage and missing identities beside the technical views and in the chat. Preparation readiness is a separate verdict.'
    if obj:
        try:
            from blender.preparation_review import render_preparation
            record['technical_views']=render_preparation(project,obj,payload,directory,recipe=recipe)
        except Exception as exc:
            record['technical_views']={'status':'FAILED','error':repr(exc)}
            record['readiness']='NEEDS_CORRECTION';problem('NEEDS_CORRECTION','technical_outputs',exc)
        if record['readiness']=='READY':
            for previous in list(bpy.data.objects):
                if previous!=obj and previous.get('a3d_component_id')==component_id:
                    previous['a3d_source_component_id']=component_id;del previous['a3d_component_id']
                    previous['a3d_role']='archived-before-preparation';previous.hide_set(True);previous.hide_render=True
            obj['a3d_component_id']=component_id;obj['a3d_role']='simulation'
    receipt_path=directory/'receipt.json';atomic_json(receipt_path,record);receipt_ref=reference(project,receipt_path)
    if obj:
        obj['a3d_pattern_preparation_receipt']=receipt_ref['path'];obj['a3d_pattern_preparation_receipt_sha256']=receipt_ref['sha256']
        obj['a3d_pattern_preparation_readiness']=record['readiness']
    bpy.ops.wm.save_as_mainfile(filepath=session['working'],check_existing=False)
    master=directory/'master-preparation-v001.blend'
    if obj:
        from blender.preparation_review import save_preparation_master
        save_preparation_master(project,obj,recipe,master)
    else:bpy.ops.wm.save_as_mainfile(filepath=str(master),copy=True,check_existing=False)
    coverage['is_dirty'] = bool(bpy.data.is_dirty)
    images = list(record.get('technical_views', {}).get('views', {}).values())
    save_report(project, coverage, directory=directory, images=images)
    result={**record,'receipt':receipt_ref,'master':reference(project,master),
        'next_operation':'transition_pattern_assembly(stage=preposition)' if record['readiness']=='READY' else None}
    atomic_json(directory/'result.json',result)
    return result
