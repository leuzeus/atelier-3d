"""Admission and coverage for actual whole-clip Cloth with animated bodies.

Canonical native origin, physical execution and final product acceptance are
separate. Subframe garment checks interpolate observed integer Cloth samples;
they do not pretend to restore or evaluate an exact subframe Cloth cache.
"""
import copy
import math

from .core import ROOT, StudioError, contract, digest, ident, inside, read_json, sha


# Compatibility aliases for existing physical and transport consumers.
from .native_evidence import checked_reference, native_origin as _native_origin


def canonical_body_motion(project, ref):
    checked_reference(project, ref)
    native, origin = _native_origin(project, lambda row: row.get('operation') == 'prepare_body_motion' and
                                   row.get('result', {}).get('receipt') == ref)
    motion = read_json(inside(project.root, ref['path']))
    if motion.get('status') != 'CLIP_SAMPLES_COMPLETE':
        raise StudioError('Garment motion needs an admitted complete body-motion clip')
    payload = dict(motion); cache_key = payload.pop('cache_key', None)
    if cache_key != digest(payload) or any(native['result'].get(key) != value for key, value in motion.items()):
        raise StudioError('Body-motion artifact differs from the actual native dispatch result')
    for name in ('artifact','samples_artifact','rig_artifact','motion_profile','body_target_receipt'):
        checked_reference(project, motion[name])
        if motion[name] not in native['files']:raise StudioError('Body-motion dependency is absent from its canonical native receipt')
    # Common dispatcher evolution is not a change to observed body geometry.
    # Bind the physical body handlers; reevaluate the actual rig/Action/skin in
    # the native consumer before any Cloth frame can qualify.
    modules = native['result'].get('runtime', {}).get('loaded_modules', {})
    for module in ('blender.body_motion','blender.mannequin_rig','a3d.motion_profiles','a3d.mannequin_rig'):
        if modules.get(module) != sha(ROOT/(module.replace('.', '/')+'.py')):
            raise StudioError('Body-motion implementation changed; regenerate its native evidence')
    return motion, origin


def garment_physics_modules(profile):
    """Handlers needed to reuse a production clip as current physical evidence.

    The journal/dispatcher are deliberately outside this list: changes to
    orchestration do not change observed cloth. TEST_ONLY transport authenticates
    historical samples without qualifying their implementation for production.
    """
    modules = ('a3d.garment_motion', 'a3d.native_evidence', 'a3d.garment_fit', 'blender.garment_motion', 'blender.moving_contacts',
               'blender.sewing', 'a3d.sewing', 'blender.regional_cloth', 'a3d.regional_cloth',
               'blender.cloth_contacts', 'a3d.contact_geometry', 'a3d.cloth_metrics',
               'a3d.pattern_assembly', 'blender.textile_executor', 'a3d.textile_executor',
               'blender.body_motion', 'blender.body_target', 'a3d.motion_profiles',
               'blender.mannequin_rig', 'a3d.mannequin_rig', 'blender.asset_export')
    if profile.get('terminal_relax'):
        modules += ('a3d.simulation_control',)
    return modules


def canonical_garment_clip(project, ref):
    """Authenticate an observed garment leaf without granting product gates."""
    checked_reference(project,ref)
    native,origin=_native_origin(project,lambda row:row.get('operation')=='run_garment_motion' and row.get('result',{}).get('receipt')==ref)
    result=read_json(inside(project.root,ref['path']));payload=dict(result);key=payload.pop('cache_key',None)
    if (key!=digest(payload) or any(native['result'].get(name)!=value for name,value in result.items()) or
            result.get('status')!='GARMENT_CLIP_SAMPLES_COMPLETE' or result.get('coverage',{}).get('clip_complete') is not True or
            result.get('cache_reopened',{}).get('status')!='REOPENED_OBSERVED_GEOMETRY_MATCHES' or not result.get('artifact')):
        raise StudioError('Layer needs a complete exact native observed garment clip')
    for name in ('artifact','observations_artifact','profile'):
        checked_reference(project,result[name])
        if result[name] not in native['files']:raise StudioError('Garment leaf dependency is absent from its canonical native receipt')
    profile=contract('garment-motion',read_json(inside(project.root,result['profile']['path'])))
    for ref in profile['bindings'].values():checked_reference(project,ref)
    if profile['purpose']=='GARMENT_CANDIDATE':
        modules=native['result'].get('runtime',{}).get('loaded_modules',{})
        for module in garment_physics_modules(profile):
            if modules.get(module)!=sha(ROOT/(module.replace('.','/')+'.py')):
                raise StudioError('Garment motion physical implementation changed; regenerate its native evidence: '+module)
    return result,origin


def canonical_composed_clip(project, ref):
    checked_reference(project,ref)
    native,origin=_native_origin(project,lambda row:row.get('operation')=='compose_animated_delivery' and row.get('result',{}).get('receipt')==ref)
    result=read_json(inside(project.root,ref['path']))
    if (any(native['result'].get(name)!=value for name,value in result.items()) or result.get('status')!='CLIPS_EXECUTED' or
            result.get('scope')!='EXACT_CANDIDATE_ANIMATION' or result.get('temporal_coverage')!='COMPLETE' or
            result.get('purpose')!='GARMENT_CANDIDATE' or result.get('whole_asset_inventory_status')!='SOURCE_INVENTORY_COMPLETE'):
        raise StudioError('External rigid obstacle needs complete native production composition evidence')
    from .export_profiles import _measured_clips
    measured,_=_measured_clips(project,native)
    if {clip['id'] for clip in result['clips']}!=set(measured):
        raise StudioError('Composed obstacle lacks exact complete native clip measurements')
    for name in ('candidate','clips_artifact'):
        checked_reference(project,result[name])
        if result[name] not in native['files']:raise StudioError('Composed obstacle dependency is absent from its canonical native receipt')
    return result,origin


def collider_inputs(project, profile, recipe, body_profile, body_binding):
    """Every additional recipe collider needs exact native animation evidence."""
    declarations=profile.get('animated_colliders',[])
    if len({row['id'] for row in declarations})!=len(declarations) or len({row['recipe_object'] for row in declarations})!=len(declarations):
        raise StudioError('Animated collider identities and recipe ownership must be unique')
    auxiliaries=[row for row in recipe['colliders'] if row['role']!='mannequin']
    if profile['purpose']=='GARMENT_CANDIDATE' and {row['object'] for row in auxiliaries}!={row['recipe_object'] for row in declarations}:
        raise StudioError('Every source auxiliary collider needs one exact native motion binding')
    result=[];last=body_profile['frame_end']+(profile.get('terminal_relax') or {}).get('max_frames',0)
    for declaration in declarations:
        try:
            source,origin=canonical_garment_clip(project,declaration['source_receipt']);kind='OBSERVED_KEY_CACHE'
        except StudioError:
            source,origin=canonical_composed_clip(project,declaration['source_receipt']);kind='COMPOSED_NATIVE_ANIMATION'
        if kind=='OBSERVED_KEY_CACHE':
            source_profile=read_json(inside(project.root,source['profile']['path']));clip=source['clip']
            valid=(source['artifact']==declaration['artifact'] and clip['object_name']==declaration['object_name'] and
                   clip.get('animation_target')=='SHAPE_KEYS' and clip.get('interpolation')=='LINEAR' and
                   clip.get('geometry_scope')=='BAKED_OBSERVED_FRAME_GEOMETRY_LINEAR_INTERPOLATION' and
                   source.get('body_motion_binding')==body_binding and
                   (profile['purpose']=='TEST_ONLY' or source_profile['purpose']=='GARMENT_CANDIDATE'))
        else:
            matches=[clip for clip in source['clips'] if clip['id']==declaration['clip_id']]
            if len(matches)!=1:raise StudioError('Composed obstacle clip is missing or ambiguous')
            clip=matches[0];clip=dict(clip,fps=source['fps'])
            data=read_json(inside(project.root,source['clips_artifact']['path']))
            measured=next(row for row in data['clips'] if row['id']==clip['id'])
            motions=source.get('object_inventory',{}).get('body',{}).get('source_motion_bindings',[])
            bound=any(row.get('id')==clip['id'] and row.get('motion_binding')==body_binding for row in motions)
            valid=(source['candidate']==declaration['artifact'] and bound and
                   all(declaration['object_name'] in sample['meshes'] for sample in measured['samples']))
        if (not valid or
                clip['id']!=declaration['clip_id'] or kind=='OBSERVED_KEY_CACHE' and clip.get('animation_target')!='SHAPE_KEYS' or
                clip['fps']!=body_profile['fps'] or clip['frame_start']>body_profile['frame_start'] or clip['frame_end']<last or
                kind=='COMPOSED_NATIVE_ANIMATION' and profile['purpose']!='GARMENT_CANDIDATE'):
            raise StudioError('Animated inner collider has stale artifact, clip, body, time coverage or scope')
        checked_reference(project,declaration['artifact'])
        if profile['purpose']=='TEST_ONLY':
            # A synthetic recipe has no declared production collider snapshot;
            # its extra collider thickness must nevertheless be explicit.
            physics=profile['body_collision']
            expected={'object':declaration['recipe_object'],'role':'support',**physics}
        else:expected=next(row for row in auxiliaries if row['object']==declaration['recipe_object'])
        result.append({'declaration':copy.deepcopy(declaration),'source':source,'origin':origin,'expected':expected,
                       'kind':kind,'clip':clip})
    return result


def validate_candidate(candidate, recipe):
    from .cloth_metrics import face_sources, validate_metrics
    from blender.sewing import mesh_recipe_digest
    if candidate.get('rest_mode') != 'assembled_3d':
        raise StudioError('Whole-clip motion requires consolidated continuous 3D rest geometry')
    if candidate.get('fitting_tacks') or candidate.get('pattern_assembly', {}).get('temporary_supports_active') is not False:
        raise StudioError('Whole-clip motion requires removal of temporary construction supports and fitting tacks')
    if candidate.get('recipe_mesh_sha256') != mesh_recipe_digest(recipe):
        raise StudioError('Motion candidate source mapping no longer matches its cited recipe')
    if candidate.get('component_id') != recipe['component_id']:
        raise StudioError('Motion candidate and recipe identify different components')
    coords = candidate.get('placed_cm', [])
    if not coords or any(len(p) != 3 or any(type(v) not in (int,float) or not math.isfinite(v) for v in p) for p in coords):
        raise StudioError('Motion candidate needs finite observed placed coordinates')
    if len(coords) != len(candidate.get('rest_cm', [])):
        raise StudioError('Motion source vertex correspondence changed')
    faces = candidate.get('faces', [])
    if not faces or any(len(f) != 3 or len(set(f)) != 3 or any(type(i) is not int or not 0 <= i < len(coords) for i in f) for f in faces):
        raise StudioError('Motion candidate requires valid immutable source triangles')
    face_sources(candidate); validate_metrics(candidate, coords, recipe['mesh'], include_faces=False)
    return {'vertices':len(coords), 'faces':len(faces), 'topology_sha256':digest(faces),
            'source_uv_sha256':digest(face_sources(candidate)), 'pins':copy.deepcopy(candidate['pins'])}


def motion_inputs(project, profile_path):
    profile = contract('garment-motion', read_json(inside(project.root, profile_path)))
    ident(profile['id']); ident(profile['component_id'])
    state=project.state()
    if profile['component_id'] not in state['components'] or not any(
            part['id']==profile['component_id'] and part['type']=='garment' for part in state['asset']['components']):
        raise StudioError('Garment motion requires a declared garment component in this project')
    bindings = {key:checked_reference(project, ref) for key, ref in profile['bindings'].items()}
    if len({ref['path'] for ref in bindings.values()}) != len(bindings):
        raise StudioError('Garment, recipe and motion bindings must identify distinct records')
    candidate = read_json(inside(project.root, bindings['candidate']['path']))
    recipe = contract('sewing-recipe', read_json(inside(project.root, bindings['recipe']['path'])))
    if recipe['component_id'] != profile['component_id']:
        raise StudioError('Garment motion profile identifies another component')
    source = validate_candidate(candidate, recipe)
    colliders = recipe['colliders'];fit_intent=None;fit_context=None
    if profile['purpose'] == 'TEST_ONLY':
        if candidate.get('synthetic') is not True:
            raise StudioError('TEST_ONLY motion must explicitly identify its synthetic candidate')
        if colliders or 'body_collision' not in profile:
            raise StudioError('TEST_ONLY requires no recipe colliders and explicit body collision thickness')
        candidate_origin = None
    else:
        fit_context=profile.get('fit_context')
        if fit_context is None:
            raise StudioError('Production garment motion requires exact reviewed fit_context classification and numeric ease')
        for ref in fit_context.values():checked_reference(project,ref)
        from .garment_fit import require_fit_intent
        fit_intent=require_fit_intent(project,fit_context['compiled_dossier_ref']['path'],fit_context['fit_profile_ref']['path'])
        fit_spec=read_json(inside(project.root,fit_context['fit_profile_ref']['path']))
        if profile['component_id'] not in fit_spec['component_ids']:
            raise StudioError('Garment motion component is absent from the exact reviewed fit intent')
        if profile['component_id'] not in {row.get('component_id') for row in fit_intent.get('checks', [])}:
            raise StudioError('Garment motion component has no measured checks in the exact reviewed fit intent')
        from .planning import require_board
        require_board(project,state)
        component=state['components'][profile['component_id']]
        package=component.get('package')
        if (component['route'].get('selected')!='PATTERN_SEWN' or not package or
                candidate.get('package_sha256')!=package['sha256'] or sha(inside(project.root,package['path']))!=package['sha256']):
            raise StudioError('Garment motion candidate must retain its current canonical approved package')
        if sum(row['role']=='mannequin' for row in colliders)!=1:
            raise StudioError('Garment motion requires exactly one source mannequin collider')
        if 'body_collision' in profile:
            raise StudioError('Garment body collision thickness must come from its source recipe')
        proof=candidate.get('component_continuity')
        if not isinstance(proof,dict):
            raise StudioError('Production garment motion requires complete source group continuity evidence')
        for key in ('source_ref','program_ref','package_ref'):
            checked_reference(project,proof[key])
        for group in proof.get('groups',[]):
            checked_reference(project,group['derived_mesh_ref'])
        def derived(row):
            result = row.get('result', {})
            if row.get('arguments',{}).get('stage')!='drape' or result.get('stage')!='drape':return False
            if row.get('operation')=='transition_pattern_assembly':
                return (result.get('derived_mesh')==bindings['candidate'] and
                        row['arguments'].get('recipe_path')==bindings['recipe']['path'] and
                        result.get('recipe_sha256')==digest(recipe))
            if row.get('operation')=='transition_textile_group':
                return (result.get('purpose')=='GARMENT_CANDIDATE' and result.get('status')=='GROUP_STAGE_COMPLETED' and any(
                    part.get('component_id')==profile['component_id'] and part.get('component_coverage')=='COMPLETE' and
                    part.get('derived_mesh')==bindings['candidate'] for part in result.get('component_results',[])))
            return False
        native, candidate_origin = _native_origin(project, derived)
        if native['operation']=='transition_textile_group':
            program_ref=checked_reference(project,native['result']['program_ref'])
            program=contract('textile-program',read_json(inside(project.root,program_ref['path'])))
            if program['purpose']!='GARMENT_CANDIDATE':
                raise StudioError('Production garment motion cannot reuse TEST_ONLY textile program evidence')
            if not any(row['component_id']==profile['component_id'] and row['recipe_ref']==bindings['recipe'] for row in program['components']):
                raise StudioError('Garment motion recipe differs from the completed source textile program')
    motion, origin = canonical_body_motion(project, bindings['body_motion_receipt'])
    if fit_context is not None:
        fit_profile=read_json(inside(project.root,fit_context['fit_profile_ref']['path']))
        target=read_json(inside(project.root,motion['body_target_receipt']['path']))
        if fit_profile['body_ref']!=target['artifacts']['profile']:
            raise StudioError('Garment fit intent and motion must use the same exact reviewed target body')
    body_profile = read_json(inside(project.root, motion['motion_profile']['path']))
    rig = read_json(inside(project.root, motion['rig_artifact']['path']))
    from .motion_profiles import validate_motion_profile
    validate_motion_profile(body_profile, rig)
    if body_profile['sample_interval_frames'] != 1:
        raise StudioError('Garment motion V1 requires a body clip with every integer frame covered')
    if recipe['phases'][profile['phase']]['fps'] != body_profile['fps']:
        raise StudioError('Body clip and source textile recipe must have the same frame rate')
    if profile['execution']['max_frames'] > recipe['phases'][profile['phase']]['frames']:
        raise StudioError('Garment motion cannot exceed the source recipe frame budget')
    terminal = profile.get('terminal_relax')
    if terminal and (terminal['min_frames'] > terminal['max_frames'] or terminal['window_frames'] >= terminal['max_frames']):
        raise StudioError('Terminal relaxation window cannot fit its declared observation budget')
    layers=collider_inputs(project,profile,recipe,body_profile,motion['motion_binding'])
    return {'profile':profile, 'profile_ref':{'path':profile_path,'sha256':sha(inside(project.root,profile_path))},
            'fit_context':copy.deepcopy(fit_context),'fit_intent':fit_intent,
            'candidate':candidate, 'recipe':recipe, 'source':source, 'body_motion':motion,
            'body_profile':body_profile, 'rig':rig, 'body_origin':origin, 'candidate_origin':candidate_origin,'animated_colliders':layers}


def require_production_continuity(verified):
    """Every authenticated native drape root must belong to production scope.

    The caller obtains this object from verified_component_continuity, which
    authenticates current group geometry/receipts. Geometry of a test coupon
    cannot supply production execution admission or a fitting acceptance.
    """
    roots=verified.get('native_group_receipts')
    if (verified.get('status')!='COMPONENT_CONTINUITY_VERIFIED' or verified.get('purpose')!='GARMENT_CANDIDATE' or
            verified.get('native_root_scope')!='COMPLETED_GROUP_DRAPE_PHYSICS_ONLY' or
            not isinstance(roots,list) or not roots or
            len({row.get('group_id') for row in roots})!=len(roots) or
            any(row.get('purpose')!='GARMENT_CANDIDATE' or row.get('scope')!='GROUP_DRAPE_PHYSICS_ONLY' for row in roots)):
        raise StudioError('Production garment execution requires GARMENT_CANDIDATE native drape roots; TEST_ONLY continuity is insufficient')


def animated_continuity(payload, coordinates, faces, verified):
    """Shared source unions must remain shared in every evaluated clip sample."""
    if verified.get('status')!='COMPONENT_CONTINUITY_VERIFIED':
        raise StudioError('Current clip requires verified complete component continuity')
    if (faces!=payload['faces'] or len(coordinates)!=len(payload['placed_cm']) or
            any(len(point)!=3 or any(type(v) not in (int,float) or not math.isfinite(v) for v in point) for point in coordinates)):
        raise StudioError('Animated component continuity lost its exact current topology')
    from .textile_executor import _component_continuity_map
    if _component_continuity_map(payload)!=verified['result_mapping_sha256']:
        raise StudioError('Animated component continuity source mapping or cohorts changed')
    count=0
    for seam in payload['seams'].values():
        if seam['kind']!='permanent':continue
        for a,b in seam['pairs']:
            if a!=b or not 0<=a<len(coordinates):
                raise StudioError('Animated permanent source partner is not the same consolidated native vertex')
            count+=1
    return {'status':'ANIMATED_SOURCE_CONTINUITY_VERIFIED','proof_sha256':verified['proof_sha256'],
            'result_mapping_sha256':verified['result_mapping_sha256'],'permanent_pair_count':count,
            'topology_sha256':digest([len(coordinates),faces]),'qualification':'GEOMETRY_ONLY',
            'current_physics_validation_required':True}


def interval_subdivisions(before, after, body_before, body_after, execution, body_substeps):
    if len(before) != len(after) or len(body_before) != len(body_after):
        raise StudioError('Moving-contact source vertex correspondence changed')
    if (type(body_substeps) is not int or body_substeps < 1 or
            any(not points or any(len(p)!=3 or any(type(v) not in (int,float) or not math.isfinite(v) for v in p)
                for p in points) for points in (before,after,body_before,body_after))):
        raise StudioError('Moving-contact samples need finite points and explicit positive substeps')
    movement = max((math.dist(a,b) for a,b in zip(before,after)), default=0.)
    body_movement = max((math.dist(a,b) for a,b in zip(body_before,body_after)), default=0.)
    needed = max(execution['min_substeps'], math.ceil((movement+body_movement)/execution['max_step_cm']))
    count = math.ceil(needed/body_substeps)*body_substeps
    return {'subdivisions':count, 'garment_max_increment_cm':movement, 'body_max_increment_cm':body_movement,
            'status':'READY' if count <= execution['max_subdivisions'] else 'INCOMPLETE',
            'reason':None if count <= execution['max_subdivisions'] else 'MOVING_CONTACT_SAMPLING_BUDGET'}


def clip_coverage(body_profile, observed_frames, stopped=None, terminal=None):
    required = list(range(body_profile['frame_start'],body_profile['frame_end']+1))
    if observed_frames != required[:len(observed_frames)]:
        raise StudioError('Cloth clip samples must advance every consecutive integer frame')
    complete = observed_frames == required and stopped is None
    return {'status':'GARMENT_CLIP_SAMPLES_COMPLETE' if complete else 'INCOMPLETE',
            'required_frames':required, 'observed_frames':list(observed_frames), 'clip_complete':complete,
            'stopped':stopped, 'terminal_relax':copy.deepcopy(terminal),
            'garment_subframe_geometry':'LINEAR_INTERPOLATION_OF_OBSERVED_INTEGER_CLOTH_FRAMES',
            'body_subframe_geometry':'ACTUAL_EVALUATED_NATIVE_ANIMATION_AT_DECLARED_CHECK_TIMES',
            'continuous_collision_qualification':'NOT_GRANTED', 'fitting':'NOT_QUALIFIED', 'accepted':False}
