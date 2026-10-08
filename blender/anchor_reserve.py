"""Native full-body signed measurements for the opt-in pure anchor kernel.

Only preparation calls this adapter after its immutable REST quality passes.
The body must be the exact closed, oriented evaluated target of the plan.
No auxiliary proxy, unsourced axis, independent stop move or admission exists.
"""
import copy
import hashlib
import json
import math
from dataclasses import dataclass
from pathlib import Path

from a3d.core import StudioError,contract,digest,inside


def _read_bound_bytes(file,ref,label):
    raw=Path(file).read_bytes()
    if hashlib.sha256(raw).hexdigest()!=ref['sha256']:
        raise StudioError('Anchor reserve '+label+' changed')
    return raw


def _read_bound_json(file,ref,label):
    """Authenticate the exact bytes that are decoded, including duplicate keys."""
    raw=_read_bound_bytes(file,ref,label)
    def pairs(rows):
        result={}
        for key,value in rows:
            if key in result:raise StudioError('Anchor reserve duplicate JSON key: '+key)
            result[key]=value
        return result
    try:
        def finite_float(text):
            value=float(text)
            if not math.isfinite(value):raise StudioError('Nonfinite body JSON')
            return value
        return json.loads(raw.decode('utf-8-sig'),object_pairs_hook=pairs,
            parse_float=finite_float,
            parse_constant=lambda value:(_ for _ in ()).throw(StudioError('Nonfinite body JSON')))
    except (UnicodeDecodeError,json.JSONDecodeError) as error:
        raise StudioError('Anchor reserve '+label+' is not valid JSON') from error


def _target_artifacts(receipt):
    result=receipt.get('result',{})
    if not isinstance(result,dict):return None,None
    if receipt.get('operation')=='prepare_body_target':
        artifacts=result.get('artifacts',{})
        if not isinstance(artifacts,dict):return None,None
        return artifacts.get('profile'),artifacts.get('geometry')
    if receipt.get('operation')=='introduce_body_target':
        return result.get('profile_ref'),result.get('geometry_ref')
    return None,None


def _current_body_geometry(body,binding,*,include_contact_surface=False):
    import bpy
    from blender.body_target import evaluated_mesh
    if (body is None or body.type!='MESH' or body.name not in binding['collider_names'] or
            body.get('a3d_profile_cache_key')!=binding['profile_cache_key']):
        raise StudioError('Anchor reserve actual collider belongs to another measured body profile')
    captured=evaluated_mesh(body,bpy.context.evaluated_depsgraph_get(),1.,
                            include_contact_surface=include_contact_surface)
    actual=captured[0]
    if actual!=binding['canonical_geometry']:
        raise StudioError('Anchor reserve actual evaluated body differs from its exact native geometry')
    return captured


def _current_contact_body(context,binding):
    """One evaluated mesh verifies canonical body and the fixed contact capture."""
    bodies=context['bodies']
    if (len(bodies)!=len(binding['collider_names']) or
            {body['name'] for body in bodies}!=set(binding['collider_names']) or
            any(not body['closed'] or body['orientation_issues'] for body in bodies)):
        raise StudioError('Anchor reserve requires the exact closed oriented body context')
    for body in bodies:
        actual,faces,polygons,surface_sha256=_current_body_geometry(
            body['object'],binding,include_contact_surface=True)
        if (surface_sha256!=body['sha256'] or body['coords']!=actual['vertices_cm'] or
                body['faces']!=faces or body['polygons']!=polygons or
                body['triangles']!=[[actual['vertices_cm'][i] for i in face] for face in faces]):
            raise StudioError('Captured contact surface differs from the exact evaluated accepted body')
    return bodies


def _freeze_binding(value):
    """Private immutable, type-exact tree; floats retain their exact bits."""
    kind=type(value)
    if kind is dict:
        if any(type(key) is not str for key in value):raise StudioError('Body binding keys must be text')
        return (dict,tuple((key,_freeze_binding(child))for key,child in sorted(value.items())))
    if kind in (list,tuple):return (kind,tuple(_freeze_binding(child)for child in value))
    if kind is float:
        if not math.isfinite(value):raise StudioError('Nonfinite body binding')
        return (float,value.hex())
    if kind in (str,int,bool,type(None)):return (kind,value)
    raise StudioError('Body binding requires immutable JSON-compatible identities')


def _matches_binding(value,frozen):
    kind,expected=frozen
    if type(value) is not kind:return False
    if kind is dict:
        return (len(value)==len(expected) and all(key in value and _matches_binding(value[key],child)
                for key,child in expected))
    if kind in (list,tuple):
        return len(value)==len(expected) and all(_matches_binding(v,child)for v,child in zip(value,expected))
    if kind is float:return value.hex()==expected
    return value==expected


@dataclass(frozen=True,slots=True)
class _BoundBodyArtifactCache:
    snapshot:tuple
    seal:tuple
    files:tuple
    files_sha256:str


def _create_bound_body_cache(binding):
    """Validate once in this call; cache neither a live body nor permission."""
    snapshot=_freeze_binding(binding)
    _bound_body_files(binding)
    seal=_freeze_binding(binding)
    if snapshot!=seal:raise StudioError('Anchor reserve body binding changed during cache creation')
    files=tuple((name,str(binding[name+'_file']),binding[name+'_ref']['sha256'])for name in ('profile','geometry'))
    return _BoundBodyArtifactCache(snapshot,seal,files,digest(files))


def _bound_body_files(binding,*,artifact_cache=None):
    if artifact_cache is not None:
        if (type(artifact_cache) is not _BoundBodyArtifactCache or
                artifact_cache.snapshot!=artifact_cache.seal or
                digest(artifact_cache.files)!=artifact_cache.files_sha256):
            raise StudioError('Anchor reserve body artifact cache changed')
        if not _matches_binding(binding,artifact_cache.snapshot):
            raise StudioError('Anchor reserve body binding changed after artifact authentication')
        files=tuple((name,str(binding[name+'_file']),binding[name+'_ref']['sha256'])for name in ('profile','geometry'))
        if files!=artifact_cache.files:raise StudioError('Anchor reserve cached artifact references changed')
        for name,file,identity in files:
            _read_bound_bytes(file,{'sha256':identity},'body '+name)
        return
    profile=_read_bound_json(binding['profile_file'],binding['profile_ref'],'body profile')
    geometry=_read_bound_json(binding['geometry_file'],binding['geometry_ref'],'body geometry')
    if (digest(profile)!=binding['profile_sha256'] or
            digest([geometry['vertices_cm'],geometry['faces']])!=binding['geometry_sha256'] or
            any(geometry.get(k)!=profile.get(k) or profile.get(k)!=binding[k]
                for k in ('source_sha256','pose_sha256')) or
            profile.get('cache_key')!=binding['profile_cache_key'] or
            {k:geometry[k] for k in ('vertices_cm','faces','face_sets')}!=binding['canonical_geometry']):
        raise StudioError('Anchor reserve bound body identity changed')


def verified_anchor_body(project,recipe,plan,preparation):
    declared=preparation.get('anchor_reserve_correction')
    if declared is None:return None
    contract('pattern-preparation',preparation)
    if not preparation.get('metric_recovery') or not preparation.get('placement_correction'):
        raise StudioError('Anchor reserve requires explicit metric recovery and placement correction')
    nodes=[node for node in plan['layers']['nodes'] if node['kind']=='body']
    if len(nodes)!=1 or nodes[0]['source_ref']!=declared['body_ref']:
        raise StudioError('Anchor reserve body differs from the sole sourced body layer')
    names=nodes[0]['colliders']
    if len(names)!=1 or names[0] not in {row['object'] for row in recipe['colliders']}:
        raise StudioError('Anchor reserve V1 requires one actual declared body collider')
    ref=declared['body_ref'];file=inside(project.root,ref['path'])
    profile=_read_bound_json(file,ref,'body profile')
    from a3d.native_evidence import native_origin
    receipt,origin=native_origin(project,lambda receipt:
        _target_artifacts(receipt)[0]==ref and ref in receipt.get('files',[]) and
        _target_artifacts(receipt)[1] in receipt.get('files',[]))
    # native_origin registers a canonical completed attempt; re-read its receipt
    # once so the bytes inspected here carry that same authenticated SHA.
    canonical=_read_bound_json(inside(project.root,origin['receipt']['path']),origin['receipt'],'native body receipt')
    if canonical!=receipt:raise StudioError('Anchor reserve native body receipt changed after authentication')
    profile_ref,geometry_ref=_target_artifacts(canonical)
    if profile_ref!=ref or not isinstance(geometry_ref,dict) or set(geometry_ref)!={'path','sha256'}:
        raise StudioError('Anchor reserve profile and geometry must be artifacts of one completed native receipt')
    geometry_file=inside(project.root,geometry_ref['path'])
    geometry=_read_bound_json(geometry_file,geometry_ref,'body geometry')
    if (not isinstance(profile,dict) or not isinstance(geometry,dict) or
            any(not isinstance(profile.get(k),str) or not profile[k]
                for k in ('geometry_sha256','source_sha256','pose_sha256','cache_key')) or
            digest([geometry['vertices_cm'],geometry['faces']])!=profile['geometry_sha256'] or
            any(geometry.get(key)!=profile.get(key) for key in ('source_sha256','pose_sha256'))):
        raise StudioError('Anchor reserve native geometry or pose differs from the exact measured profile')
    result=canonical['result']
    expected_status=('NATIVE_BODY_TARGET_MEASURED' if canonical['operation']=='prepare_body_target'
                     else 'BODY_TARGET_INTRODUCED')
    if result.get('status')!=expected_status:
        raise StudioError('Anchor reserve requires a completed measured target body result')
    if any(result.get(key)!=profile[value] for key,value in
           (('geometry_sha256','geometry_sha256'),('pose_sha256','pose_sha256'),('profile_cache_key','cache_key'))):
        raise StudioError('Anchor reserve completed native result differs from its profile identity')
    frame=profile.get('frame');axis=frame.get('up') if isinstance(frame,dict) else None
    if (not isinstance(axis,list) or len(axis)!=3 or
            any(type(v) not in (int,float) or not math.isfinite(v) for v in axis) or math.hypot(*axis)==0):
        raise StudioError('Anchor reserve needs the exact measured body frame')
    binding={'profile_ref':copy.deepcopy(ref),'profile_file':str(file),'profile_sha256':digest(profile),
            'geometry_ref':copy.deepcopy(geometry_ref),'geometry_file':str(geometry_file),
            'canonical_geometry':{k:copy.deepcopy(geometry[k]) for k in ('vertices_cm','faces','face_sets')},
            'profile_cache_key':profile['cache_key'],'source_sha256':profile['source_sha256'],
            'frame':copy.deepcopy(frame),'pose_sha256':profile.get('pose_sha256'),
            'geometry_sha256':profile.get('geometry_sha256'),'native_body_origin':origin,
            'collider_names':list(names)}
    import bpy
    _current_body_geometry(bpy.data.objects.get(names[0]),binding)
    _bound_body_files(binding)
    return binding


def measure_anchor_reserve(payload,coordinates,context,plan,binding,stops,moving,identity,*,
                           expected_source_sha256=None,artifact_cache=None,artifact_cache_loader=None,
                           contact_identity_loader=None):
    """Measure stops against full evaluated target triangles; no plane witnesses."""
    from blender.pattern_assembly import collision_check
    try:
        if artifact_cache_loader is not None:
            if artifact_cache is not None or not callable(artifact_cache_loader):
                raise StudioError('Anchor reserve requires one internal artifact cache source')
            artifact_cache=artifact_cache_loader()
        _bound_body_files(binding,artifact_cache=artifact_cache)
        if 'collision_sha256' in identity and digest(plan['collision'])!=identity['collision_sha256']:
            raise StudioError('Anchor reserve collision plan differs from the measured context identity')
        contact_guard=contact_identity_loader() if contact_identity_loader is not None else None
        if contact_guard is None:bodies=_current_contact_body(context,binding)
        else:
            from blender.contact_body_identity import verify_contact_body_identity
            bodies=verify_contact_body_identity(context,binding,plan,contact_guard,expected_guard=contact_guard)
        clearance=plan['collision']['clearance_cm'];contacts=[]
        if type(clearance) not in (int,float) or not math.isfinite(clearance) or clearance<0:
            return {'status':'UNAVAILABLE','reason':'INVALID_DECLARED_COLLISION_RESERVE'}
        for index in stops:
            measured=collision_check([coordinates[index]],[body['tree'] for body in bodies],
                [body['snapshot'] for body in bodies],clearance,
                surface_triangles=[body['triangles'] for body in bodies])
            if (not isinstance(measured,dict) or type(measured.get('ambiguous_sign_count')) is not int or
                    measured['ambiguous_sign_count']<0):
                return {'status':'UNAVAILABLE','reason':'SIGNED_FULL_BODY_MEASUREMENT_UNAVAILABLE'}
            offset=measured.get('minimum_signed_offset_cm')
            if (measured['ambiguous_sign_count'] or type(offset) not in (int,float) or not math.isfinite(offset)):
                return {'status':'AMBIGUOUS','reason':'SIGNED_FULL_BODY_MEASUREMENT_INCOMPLETE'}
            worst=measured.get('worst');body=bodies[0]
            if (measured.get('distance_metric')!='NEAREST_SURFACE_EUCLIDEAN_NORMAL_SIGN_WITH_UNANIMOUS_RAY_PARITY_FOR_FLOAT32_SIGN_UNCERTAINTY' or
                    measured.get('clearance_cm')!=clearance or not isinstance(worst,dict) or
                    worst.get('collider')!=body['name'] or worst.get('sample')!=0 or
                    type(worst.get('face')) is not int or not 0<=worst['face']<len(body['triangles']) or
                    worst.get('signed_offset_cm')!=offset or
                    worst.get('sign_classification') not in
                    ('NEAREST_NORMAL','UNANIMOUS_THREE_RAY_PARITY','FLOAT64_ON_SURFACE_WITNESS')):
                return {'status':'UNAVAILABLE','reason':'UNKNOWN_OR_INCOMPLETE_SIGNED_BODY_CLASSIFIER'}
            contacts.append({'vertex':index,'signed_offset_cm':offset,'clearance_cm':clearance})
        _bound_body_files(binding,artifact_cache=artifact_cache)
        if 'collision_sha256' in identity and digest(plan['collision'])!=identity['collision_sha256']:
            raise StudioError('Anchor reserve collision plan changed during measurement')
        if contact_guard is None:_current_contact_body(context,binding)
        else:verify_contact_body_identity(context,binding,plan,contact_guard,expected_guard=contact_guard)
    except Exception as error:
        return {'status':'UNAVAILABLE','reason':'EXACT_NATIVE_BODY_MEASUREMENT_UNAVAILABLE','error':str(error)}
    return {'status':'MEASURED','context_identity':copy.deepcopy(identity),
            'source_sha256':digest(payload) if expected_source_sha256 is None else expected_source_sha256,
            'candidate_sha256':digest(coordinates),
            'method':'FULL_BODY_COLLISION','sign_status':'UNAMBIGUOUS',
            'moving_indices':sorted(moving),'protected_contacts':contacts}


def propose_anchor_reserve(payload,coordinates,context,recipe,plan,preparation,binding,quality,
                           original_guide,placement_limits):
    from a3d.anchor_reserve import DOMAIN,solve_anchor_reserve
    from a3d.cloth_metrics import validate_metrics
    if binding is None:raise StudioError('Anchor reserve body must be authenticated before native correction')
    stops=set(placement_limits.get('protected_indices',[]))
    for row in preparation['metric_recovery']['protected_edges']:
        indices=payload['panels'][row['piece']]['edges'][row['edge']]
        stops.update((indices[0],indices[-1]))
    try:rest_metric=validate_metrics(payload,payload['rest_cm'],quality,include_faces=False,include_bending=False)
    except StudioError as error:
        return {'status':'NOT_EXECUTED_INVALID_SOURCE_REST','stop_reason':'IMMUTABLE_SOURCE_MESH_QUALITY',
                'coordinates_cm':copy.deepcopy(coordinates),'rest_metric':getattr(error,'quality_metrics',None),
                'qualification':'NONE','simulation':'NOT_EXECUTED','fitting':'NOT_EXECUTED'}
    declared=preparation['anchor_reserve_correction'];budgets=copy.deepcopy(declared['budgets'])
    for key in ('max_displacement_cm','max_step_cm','max_iterations','max_seconds'):
        budgets[key]=min(budgets[key],placement_limits['budgets'][key],preparation['metric_recovery']['budgets'][key])
    specification={'version':1,'enabled':True,'domain':DOMAIN,'budgets':budgets}
    identity={'body':{key:copy.deepcopy(binding[key]) for key in
              ('profile_ref','profile_sha256','geometry_ref','profile_cache_key','source_sha256',
               'frame','pose_sha256','geometry_sha256','native_body_origin')},
              'evaluated_surfaces':[{ 'object':body['name'],'sha256':body['sha256']} for body in context['bodies']],
              'collision_sha256':digest(plan['collision'])}
    supports=set()
    for stage in ('temporary','drape','functional'):
        if plan.get('supports',{}).get(stage):
            raise StudioError('Anchor reserve V1 cannot move authored physical supports')
    if recipe.get('pins'):raise StudioError('Anchor reserve V1 cannot move a recipe with physical pins')
    source_identity=digest(payload);moving=moving_indices(payload,stops);ordered_stops=sorted(stops)
    artifact_cache=None
    contact_identity=None;contact_identity_initialized=False
    def cached_artifacts():
        # Lazy inside measure_anchor_reserve's existing failure wrapper and
        # within the search clock. A failed construction is never memoized.
        nonlocal artifact_cache
        if artifact_cache is None:artifact_cache=_create_bound_body_cache(binding)
        return artifact_cache
    def cached_contact_identity():
        nonlocal contact_identity,contact_identity_initialized
        if not contact_identity_initialized:
            from blender.contact_body_identity import create_contact_body_identity
            contact_identity=create_contact_body_identity(context,binding,plan,_current_contact_body)
            contact_identity_initialized=True
        return contact_identity
    result=solve_anchor_reserve(payload,coordinates,
        lambda source,points:measure_anchor_reserve(source,points,context,plan,binding,ordered_stops,
            moving,identity,expected_source_sha256=source_identity,artifact_cache_loader=cached_artifacts,
            contact_identity_loader=cached_contact_identity),specification,
        body_frame_up=binding['frame']['up'],context_identity=identity,
        displacement_reference=original_guide,
        rest_precondition={'status':'PASSED','source_sha256':source_identity,'candidate_sha256':digest(coordinates)},
        protected_indices=ordered_stops,support_indices=sorted(supports))
    result.update(rest_metric=rest_metric,body_ref=copy.deepcopy(binding['profile_ref']),
                  reserve_source='PLAN_COLLISION_CLEARANCE',final_readiness='UNCHANGED_DOWNSTREAM_GATES_REQUIRED')
    return result


def moving_indices(payload,stops):
    # Use the same pure ownership/closure calculation as the kernel, avoiding
    # garment IDs and independently invented component relationships.
    from a3d.anchor_reserve import _structure,_groups
    owners,neighbours=_structure(payload,payload['placed_cm'])
    groups=_groups(owners,neighbours,set(stops))
    return sorted({index for pieces in groups for piece in pieces for index in payload['panels'][piece]['indices']})
