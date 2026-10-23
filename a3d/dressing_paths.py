"""Bounded controls from source UV edges and measured anatomical sections.

These controls are a reviewable geometric proposal. A native entry geometry,
source grips, support trajectories and observed contact checks are still needed
to compile an executable dressing trajectory. No translation is invented here.
"""
import copy
import math

from .core import StudioError, contract, digest, inside, read_json, sha
from .dressing import _reference
from .dressing_derivation import dressing_derivation_descriptor
from .pattern_assembly import _compile_arc_sections, _section_point


def _uv(point):
    return isinstance(point,list) and len(point)==2 and all(type(v) in (int,float) and math.isfinite(v) for v in point)


def _edge_count(vertices,chain,spacing):
    if not chain or len(chain)<2 or any(type(i) is not int or not 0<=i<len(vertices) for i in chain):
        raise StudioError('Dressing path requires a valid original named source edge')
    if any(not _uv(vertices[i]) for i in chain):
        raise StudioError('Dressing path source UV coordinates must be finite')
    lengths=[math.dist(vertices[a],vertices[b]) for a,b in zip(chain,chain[1:])]
    if any(length<=1e-12 for length in lengths):
        raise StudioError('Dressing path source edge contains a collapsed segment')
    return 1+sum(math.ceil(length/spacing) for length in lengths)


def _sample_edge(vertices,chain,spacing):
    samples=[]
    for segment,(a,b) in enumerate(zip(chain,chain[1:])):
        count=math.ceil(math.dist(vertices[a],vertices[b])/spacing)
        for step in range(count):
            fraction=step/count
            samples.append({'uv_cm':[vertices[a][k]*(1-fraction)+vertices[b][k]*fraction for k in range(2)],
                            'source_segment':segment,'source_vertex_ids':[a,b],'source_weights':[1-fraction,fraction]})
    samples.append({'uv_cm':list(vertices[chain[-1]]),'source_segment':len(chain)-2,
                    'source_vertex_ids':chain[-2:],'source_weights':[0.,1.]})
    return samples


def _control_edges(method):
    return [('RIM',edge) for edge in method['source_edges']]+[
        ('PERMANENT_SOURCE_ANCHOR',edge) for edge in method.get('source_anchor_edges',[])]


def generate_dressing_paths(derivation,max_path_points=None):
    """Map exact source rims to existing guides, refusing budget or domain gaps.

    The source-to-guide mapping uses the same strict arc evaluator as textile
    preparation: no clamping, curve wrapping, missing domain extrapolation,
    panel resizing or generated seam is permitted.
    """
    original=digest(derivation);payload=dict(derivation);key=payload.pop('derivation_sha256',None)
    if key!=digest(payload) or derivation.get('qualification')!='EXPLORATORY_DRESSING_GEOMETRY_ONLY':
        raise StudioError('Dressing paths require an exact source derivation, not claimed passage evidence')
    policy=contract('dressing-derivation',derivation['policy'])
    limit=policy['budgets']['max_path_points'] if max_path_points is None else max_path_points
    if type(limit) is not int or not 2<=limit<=policy['budgets']['max_path_points']:
        raise StudioError('Dressing path point limit must fit the explicit derivation budget')
    spacing=policy['source_edge_spacing_cm'];counts={};required=0
    methods=derivation['methods'];ids=[row['id'] for row in methods]
    if len(set(ids))!=len(ids):raise StudioError('Dressing path method identities are duplicated')
    regions={row['id']:row for row in derivation['regions']}
    if len(regions)!=len(derivation['regions']):raise StudioError('Dressing path anatomical region identities are duplicated')
    for method in methods:
        region=regions.get(method['body_region'])
        if region is None or digest(region)!=method['region_sha256']:
            raise StudioError('Dressing path region changed from its measured source method')
        required+=len(region['sections'])
        seen=set()
        for _,edge in _control_edges(method):
            pid,name=edge['piece'],edge['edge']
            if (pid,name) in seen:raise StudioError('Dressing source rim edge is duplicated')
            seen.add((pid,name))
            try:vertices=method['source_vertices'][pid];chain=method['source_named_edges'][pid][name]
            except KeyError as error:raise StudioError('Dressing rim is absent from its original panel source') from error
            count=_edge_count(vertices,chain,spacing);counts[(method['id'],pid,name)]=count;required+=count
    diagnostics=copy.deepcopy(derivation['diagnostics']);controls=[]
    if required>limit:
        diagnostics.append({'category':'BUDGET_INCOMPLETE','reason':'SOURCE_PATH_POINT_BUDGET',
                            'required_points':required,'max_path_points':limit})
        status='INCOMPLETE'
    else:
        for method in methods:
            rims=[];anchors=[];unmapped=[]
            for role,edge in _control_edges(method):
                pid,name=edge['piece'],edge['edge'];frame=method['source_guides'][pid]
                if not isinstance(frame.get('arc_sections'),list) or len(frame['arc_sections'])<2:
                    unmapped.append({'category':'UNSUPPORTED_METHOD','reason':'SOURCE_GUIDE_PARAMETERIZATION_UNSUPPORTED',
                                     'method_id':method['id'],'piece':pid,'edge':name});continue
                try:
                    compiled=_compile_arc_sections(frame,pid)
                    samples=_sample_edge(method['source_vertices'][pid],method['source_named_edges'][pid][name],spacing)
                    points=[]
                    for sample in samples:
                        point,binding=_section_point(frame,compiled,sample['uv_cm'],pid)
                        if len(point)!=3 or any(type(v) not in (int,float) or not math.isfinite(v) for v in point):
                            raise StudioError('Source guide produced a nonfinite dressing control')
                        points.append({**sample,'guide_point_cm':point,'guide_binding':binding})
                    target=anchors if role=='PERMANENT_SOURCE_ANCHOR' else rims
                    target.append({'piece':pid,'edge':name,'source_guide_sha256':digest(frame),
                                   'source_edge_sha256':digest([method['source_vertices'][pid],method['source_named_edges'][pid][name]]),
                                   'samples':points,**({'source_link_id':edge['source_link_id']} if role=='PERMANENT_SOURCE_ANCHOR' else {})})
                except StudioError as error:
                    unmapped.append({'category':'IMPOSSIBLE_SOURCE_GEOMETRY','reason':'SOURCE_RIM_OUTSIDE_DECLARED_GUIDE',
                                     'method_id':method['id'],'piece':pid,'edge':name,'detail':str(error)})
            region=regions[method['body_region']]
            body_controls=[{'parameter':row['parameter'],'center_cm':copy.deepcopy(row['center_cm']),
                            'section_status':'MEASURED' if row['ok'] else 'UNRESOLVED',
                            'section_sha256':digest(row)} for row in region['sections']]
            diagnostics.extend(unmapped)
            controls.append({'method_id':method['id'],'method':method['method'],'component_id':method['component_id'],
                'source_method_sha256':digest(method),'body_region':method['body_region'],
                'clearance_cm':method['clearance_cm'],'source_rims':rims,'body_axis_controls':body_controls,
                'source_anchor_rims':anchors,'source_open_links':copy.deepcopy(method.get('source_open_links',[])),
                'mode_proposals':copy.deepcopy(method.get('mode_proposals',[])),
                'configuration':copy.deepcopy(method.get('configuration')),
                'control_scope':'SOURCE_GUIDE_RIMS_AND_MEASURED_BODY_AXIS',
                'entry_configuration':'MISSING','trajectory':None,'executable':False,
                'passage':'NOT_QUALIFIED','status':'NEEDS_DATA' if not unmapped else 'UNRESOLVED_SOURCE_GUIDE'})
        status='NEEDS_DATA' if diagnostics else 'GEOMETRIC_CONTROLS_DERIVED'
    if digest(derivation)!=original:raise StudioError('Dressing path generation mutated source derivation')
    result={'version':1,'status':status,'derivation_sha256':key,'controls':controls,
            'point_budget':{'required_points':required,'max_path_points':limit},
            'mount_dag':copy.deepcopy(derivation['mount_dag']),'diagnostics':diagnostics,
            'qualification':'EXPLORATORY_DRESSING_GEOMETRY_ONLY','simulation':'NOT_EXECUTED',
            'continuous_contacts':'NOT_QUALIFIED','fitting':'NOT_QUALIFIED','source_cut_preserved':True,
            'source_mutated':False,'accepted':False,'executable':False}
    result['paths_sha256']=digest(result)
    return result


def dressing_paths_descriptor(project,specification_path):
    """Recompute the derivation rather than trust a re-signed user JSON result."""
    path=inside(project.root,specification_path);request=contract('dressing-paths',read_json(path))
    refs=request['bindings'];evidence=[{'path':specification_path,'sha256':sha(path)}]
    for reference in refs.values():
        _reference(reference);source=inside(project.root,reference['path'])
        if sha(source)!=reference['sha256']:raise StudioError('Dressing path source reference changed')
        evidence.append(copy.deepcopy(reference))
    derived=dressing_derivation_descriptor(project,refs['derivation_spec_ref']['path'])
    if read_json(inside(project.root,refs['derivation_ref']['path']))!=derived['derivation']:
        raise StudioError('Dressing derivation differs from reconstruction of its source policies')
    result=generate_dressing_paths(derived['derivation'],request['max_path_points'])
    evidence.extend(ref for ref in derived['evidence'] if ref not in evidence)
    return {'request':request,'evidence':evidence,'paths':result,'derivation':derived['derivation'],
            'binding_sha256':digest(evidence)}


def _source_point(document,pointer):
    """Resolve a finite measured/planned point; no expressions or defaults."""
    if not isinstance(pointer,str) or not pointer.startswith('/'):
        raise StudioError('Dressing source waypoint pointer must be an absolute JSON pointer')
    try:
        for token in pointer.split('/')[1:]:
            if any(token[index:index+2] not in ('~0','~1') for index,char in enumerate(token) if char=='~'):
                raise ValueError('Invalid JSON pointer escape')
            token=token.replace('~1','/').replace('~0','~')
            if isinstance(document,list):
                if not token.isascii() or not token.isdigit() or (len(token)>1 and token.startswith('0')):
                    raise ValueError('Invalid JSON array index')
                document=document[int(token)]
            else:document=document[token]
    except (KeyError,IndexError,ValueError,TypeError) as error:
        raise StudioError('Dressing source waypoint pointer is absent') from error
    if not isinstance(document,list) or len(document)!=3 or any(type(v) not in (int,float) or not math.isfinite(v) for v in document):
        raise StudioError('Dressing source waypoint must be an exact finite 3D point')
    return copy.deepcopy(document)


def source_grip_vertex(candidate,grip):
    try:chain=candidate['panels'][grip['piece']]['edges'][grip['edge']];index=chain[grip['edge_vertex']]
    except (KeyError,IndexError,TypeError) as error:
        raise StudioError('Dressing grip is absent from the exact native named source edge') from error
    if type(grip['edge_vertex']) is not int or grip['edge_vertex']<0 or type(index) is not int or not 0<=index<len(candidate['rest_cm']):
        raise StudioError('Dressing grip native source vertex identity is invalid')
    return index


def support_sample(support,frame):
    """Linear interpolation of explicitly sourced support targets, then release."""
    if type(frame) not in (int,float) or not math.isfinite(frame):raise StudioError('Dressing support time must be finite')
    keys=support['resolved_waypoints']
    if not keys:raise StudioError('Dressing support has no declared source interval')
    if frame<support['start_frame']:
        return {'vertex':support['vertex'],'weight':0.,'released':False,'active':False,'point_cm':list(keys[0]['point_cm'])}
    if frame>=support['release_frame']:
        return {'vertex':support['vertex'],'weight':0.,'released':True,'active':False,'point_cm':list(keys[-1]['point_cm'])}
    if frame>=keys[-1]['frame']:point=list(keys[-1]['point_cm'])
    else:
        pair=next((a,b) for a,b in zip(keys,keys[1:]) if a['frame']<=frame<=b['frame'])
        a,b=pair;alpha=(frame-a['frame'])/(b['frame']-a['frame'])
        point=[a['point_cm'][k]*(1-alpha)+b['point_cm'][k]*alpha for k in range(3)]
    return {'vertex':support['vertex'],'weight':support['weight'],'released':False,'active':True,'point_cm':point}


def _body_target(project,target_ref):
    """Accept a local measurement or an exact canonical native introduction.

    An introduced target retains its original receipt and source artifacts.
    Its actual evaluated skin hash and context binding must match; copied
    source files alone never create a local native measurement event.
    """
    from .garment_motion import checked_reference,_native_origin
    checked_reference(project,target_ref)
    native,origin=_native_origin(project,lambda row:
        (row.get('operation')=='prepare_body_target' and row.get('result',{}).get('receipt')==target_ref) or
        (row.get('operation')=='introduce_body_target' and row.get('result',{}).get('body_target_receipt')==target_ref))
    body=read_json(inside(project.root,target_ref['path']));payload=dict(body);key=payload.pop('cache_key',None)
    if key!=digest(payload) or body.get('status')!='NATIVE_BODY_TARGET_MEASURED' or body.get('native_reopened') is not True:
        raise StudioError('Dressing body target is not an exact reopened canonical native measurement')
    evidence=[copy.deepcopy(target_ref)]
    if native['operation']=='introduce_body_target':
        from .body_context import body_context_descriptor
        context=body_context_descriptor(project,native['arguments']['context_path'])
        result=native['result'];profile=context['profile'];geometry=context['geometry']
        expected={'status':'BODY_TARGET_INTRODUCED','binding_sha256':context['binding_sha256'],
            'profile_cache_key':profile['cache_key'],'context':context['context_ref'],'body_target_receipt':target_ref,
            'source_artifact':body['artifact'],'profile_ref':body['artifacts']['profile'],
            'geometry_ref':body['artifacts']['geometry'],'geometry_sha256':body['geometry_sha256'],
            'pose_sha256':body['pose_sha256'],
            'actual_geometry_sha256':digest({name:geometry[name] for name in ('vertices_cm','faces','face_sets')})}
        if (context['context']['body_target_receipt']!=target_ref or context['receipt']!=body or
                any(result.get(name)!=value for name,value in expected.items())):
            raise StudioError('Dressing body introduction differs from its exact native target context')
        for ref in (target_ref,context['context_ref'],body['artifact'],body['artifacts']['profile'],body['artifacts']['geometry']):
            if ref not in native['files']:
                raise StudioError('Dressing body introduction dependency is absent from its canonical native receipt')
        evidence.extend(ref for ref in context['evidence'] if ref not in evidence)
    else:
        if any(native['result'].get(name)!=value for name,value in body.items()):
            raise StudioError('Dressing body target is not an exact reopened canonical native measurement')
        for ref in [body['artifact'],*body['artifacts'].values()]:
            if ref not in native['files']:
                raise StudioError('Dressing body dependency is absent from its native origin')
    for ref in [body['artifact'],*body['artifacts'].values()]:
        checked_reference(project,ref)
        if ref not in evidence:evidence.append(copy.deepcopy(ref))
    return body,origin,evidence


def dressing_execution_descriptor(project,profile_path):
    """Admit only explicit entry/targets, preserving missing-data outcomes.

    motion_inputs supplies canonical current source groups, recipe and animated
    obstacles. The body target stays in its exact measured source pose during
    dressing; no target anatomy or support trajectory is manufactured.
    """
    from .garment_motion import checked_reference,_native_origin,motion_inputs
    path=inside(project.root,profile_path);profile=contract('dressing-execution',read_json(path))
    refs=profile['bindings'];evidence=[{'path':profile_path,'sha256':sha(path)}]
    for ref in refs.values():checked_reference(project,ref);evidence.append(copy.deepcopy(ref))
    derived=dressing_paths_descriptor(project,refs['paths_spec_ref']['path'])
    if read_json(inside(project.root,refs['paths_ref']['path']))!=derived['paths']:
        raise StudioError('Dressing controls differ from their reconstructed source derivation')
    evidence.extend(ref for ref in derived['evidence'] if ref not in evidence)
    paths=derived['paths'];derivation=derived['derivation'];methods={row['id']:row for row in derivation['methods']}
    if any(key not in methods or methods[key]['component_id']!=profile['component_id'] for key in profile['method_ids']):
        raise StudioError('Dressing executable methods must belong to the exact selected source component')
    diagnostics=[]
    if paths['status']=='INCOMPLETE':diagnostics.append({'category':'BUDGET_INCOMPLETE','reason':'DRESSING_CONTROLS_INCOMPLETE'})
    for name in ('motion_profile_ref','instructions_ref'):
        if name not in refs:diagnostics.append({'category':'MISSING_DATA','reason':'DRESSING_'+name.upper()+'_REQUIRED'})
    regions={row['id']:row for row in derivation['regions']}
    for key in profile['method_ids']:
        method=methods[key]
        if method['method'] in ('OPEN_HOOD_YOKE','OPEN_DETACHABLE_YOKE'):
            if method.get('configuration') is None:
                diagnostics.append({'category':'MISSING_DATA','reason':'HOOD_YOKE_SOURCE_MODE_AND_OPEN_LINK_STATES_REQUIRED',
                                    'method_id':key,'mode_proposals':method['mode_proposals']})
            if regions[method['body_region']]['status']!='MEASURED_SECTIONS':
                diagnostics.append({'category':'MISSING_DATA','reason':'HOOD_YOKE_MEASURED_REGION_UNRESOLVED','method_id':key})
    body_regions=None
    if 'body_regions_spec_ref' in refs:
        from .body_region_sections import measure_project_body_regions
        body_regions=measure_project_body_regions(project,refs['body_regions_spec_ref']['path'])
        if (body_regions['identity']['geometry_sha256']!=derivation['body_geometry_sha256'] or
                body_regions['identity']['pose_sha256']!=derivation['body_pose_sha256']):
            raise StudioError('Dressing limb/hand supplement belongs to another measured body pose')
        def collect_region_refs(value):
            if isinstance(value,dict):
                if set(value)=={'path','sha256'}:
                    checked_reference(project,value)
                    if value not in evidence:evidence.append(copy.deepcopy(value))
                else:
                    for child in value.values():collect_region_refs(child)
            elif isinstance(value,list):
                for child in value:collect_region_refs(child)
        collect_region_refs(body_regions)
    if profile['purpose']=='GARMENT_CANDIDATE':
        if 'fit_profile_ref' not in refs or 'compiled_dossier_ref' not in refs:
            diagnostics.append({'category':'MISSING_DATA','reason':'EXPLICIT_SOURCE_BOUND_FIT_CLASSIFICATION_AND_EASE_REQUIRED'})
        for key in profile['method_ids']:
            side=key.rsplit('.',1)[-1]
            envelope=next((row for row in (body_regions or {}).get('hand_envelopes',[]) if row['side']==side and
                row['status']=='CONSERVATIVE_SKIN_PROJECTION_MEASURED' and row['measurement_scope']=='CONSERVATIVE_PROJECTED_WHOLE_HAND_SKIN_HULL'),None)
            if methods[key]['method']=='CLOSED_CUFF' and envelope is None:
                diagnostics.append({'category':'MISSING_DATA','reason':'MEASURED_FULL_HAND_ENTRY_DOMAIN_REQUIRED','method_id':key})
    if diagnostics:
        return {'status':'NEEDS_DATA','profile':profile,'profile_ref':evidence[0],'paths':paths,
                'derivation':derivation,'evidence':evidence,'diagnostics':diagnostics,
                'qualification':'NONE','simulation':'NOT_EXECUTED','binding_sha256':digest(evidence)}
    inputs=motion_inputs(project,refs['motion_profile_ref']['path'])
    if inputs['profile']['purpose']!=profile['purpose'] or inputs['profile']['component_id']!=profile['component_id']:
        raise StudioError('Dressing candidate scope differs from its admitted source motion descriptor')
    if profile['purpose']=='GARMENT_CANDIDATE':
        fit_context={key:refs[key] for key in ('compiled_dossier_ref','fit_profile_ref')}
        if inputs['fit_context']!=fit_context:
            raise StudioError('Dressing and garment source motion have different reviewed fit intents')
        fit_spec=read_json(inside(project.root,refs['fit_profile_ref']['path']))
        if profile['component_id'] not in fit_spec['component_ids']:
            raise StudioError('Dressing component is absent from the exact reviewed fit intent')
    evidence.extend(ref for ref in inputs['profile']['bindings'].values() if ref not in evidence)
    instructions=contract('dressing-instructions',read_json(inside(project.root,refs['instructions_ref']['path'])))
    if instructions['paths_sha256']!=paths['paths_sha256'] or set(instructions['mount_order'])!=set(profile['method_ids']):
        raise StudioError('Dressing instructions refer to different source controls or methods')
    order=checked_reference(project,instructions['mount_order_source_ref']);evidence.append(order)
    if read_json(inside(project.root,order['path'])).get('mount_order')!=instructions['mount_order']:
        raise StudioError('Dressing mount order differs from its exact source decision')
    seen=set()
    for key in instructions['mount_order']:
        if not set(paths['mount_dag']['dependencies'][key]).intersection(profile['method_ids'])<=seen:
            raise StudioError('Dressing mount order contradicts the approved source layer DAG')
        seen.add(key)
    stages=instructions['method_stages'];stage_by_id={row['method_id']:row for row in stages}
    if ([row['method_id'] for row in stages]!=instructions['mount_order'] or stages[0]['start_frame']!=1 or
            stages[-1]['end_frame']!=instructions['frame_end'] or
            any(row['end_frame']-row['start_frame']<3 for row in stages) or
            any(a['end_frame']+1!=b['start_frame'] for a,b in zip(stages,stages[1:]))):
        raise StudioError('Dressing method intervals must follow the exact source order with complete nonoverlapping frame coverage')
    candidate=inputs['candidate'];entry_ref=checked_reference(project,instructions['entry_candidate_ref']);evidence.append(entry_ref)
    source_identity=derivation['component_sources'][profile['component_id']]
    if (candidate.get('source_garment_sha256')!=source_identity['source_garment_sha256'] or
            candidate.get('package_sha256')!=source_identity['source_ref']['sha256'] or
            set(candidate['panels'])!=set(source_identity['source_piece_contours_sha256']) or
            any(candidate['panels'][pid].get('source_contour_sha256')!=identity for pid,identity in source_identity['source_piece_contours_sha256'].items())):
        raise StudioError('Dressing candidate differs from the exact source package and approved cut contours')
    entry=read_json(inside(project.root,entry_ref['path']))
    immutable=('rest_cm','faces','panels','seams','source_rest_triangles_cm','source_face_vertex_ids','source_face_pieces',
               'source_vertex_map','source_vertex_cohorts','source_face_origins','package_sha256','source_garment_sha256')
    if any(entry.get(key)!=candidate.get(key) for key in immutable) or len(entry.get('placed_cm',[]))!=len(candidate['placed_cm']):
        raise StudioError('Dressing entry changed immutable source rest, panels, maps, topology or links')
    if any(not isinstance(p,list) or len(p)!=3 or any(type(v) not in (int,float) or not math.isfinite(v) for v in p) for p in entry['placed_cm']):
        raise StudioError('Dressing entry needs finite exact observed coordinates')
    entry_origin=None
    if profile['purpose']=='GARMENT_CANDIDATE':
        _,entry_origin=_native_origin(project,lambda row:row.get('operation') in ('prepare_pattern_assembly','transition_pattern_assembly','transition_textile_group') and
            (row.get('result',{}).get('derived_mesh')==entry_ref or any(part.get('derived_mesh')==entry_ref for part in row.get('result',{}).get('component_results',[]))))
    target_ref=inputs['body_motion']['body_target_receipt']
    body,target_origin,body_evidence=_body_target(project,target_ref)
    evidence.extend(ref for ref in body_evidence if ref not in evidence)
    if (body['artifacts']['geometry']!=derivation['policy']['bindings']['body_geometry_ref'] or
            body['artifacts']['triangles']!=derivation['policy']['bindings']['body_triangles_ref'] or
            body.get('geometry_sha256')!=derivation['body_geometry_sha256'] or body.get('pose_sha256')!=derivation['body_pose_sha256']):
        raise StudioError('Dressing target body differs from the measured source regions')
    end=instructions['frame_end']
    if end>inputs['recipe']['phases']['drape']['frames']:
        raise StudioError('Dressing sequence exceeds the source recipe frame budget')
    if inputs['animated_colliders'] and any(end>row['clip']['frame_end'] or row['clip']['frame_start']>1 for row in inputs['animated_colliders']):
        raise StudioError('Dressing layers do not cover the entire declared native sequence')
    resolved=[];vertices=set();support_ids=set()
    def point(source_ref,pointer):
        checked_reference(project,source_ref);evidence.append(copy.deepcopy(source_ref))
        return _source_point(read_json(inside(project.root,source_ref['path'])),pointer)
    for support in instructions['supports']:
        stage=stage_by_id.get(support['method_id'])
        if stage is None:raise StudioError('Dressing grip belongs to an unselected source method')
        method=methods[support['method_id']]
        if method['method'] in ('OPEN_HOOD_YOKE','OPEN_DETACHABLE_YOKE') and support['piece'] not in method['pieces']:
            raise StudioError('Dressing hood/yoke grip is outside its exact permanent source unit')
        vertex=source_grip_vertex(candidate,support)
        if vertex in vertices or support['id'] in support_ids:
            raise StudioError('Dressing grips must own unique native source vertices and identities')
        vertices.add(vertex);support_ids.add(support['id'])
        if str(vertex) in candidate['pins']:
            raise StudioError('Dressing cannot release or override an existing functional source pin')
        keys=[{'frame':row['frame'],'point_cm':point(row['source_ref'],row['pointer'])} for row in support['waypoints']]
        if (keys[0]['frame']!=support['start_frame'] or keys[-1]['frame']!=support['release_frame']-1 or
                support['start_frame']<stage['start_frame'] or support['release_frame']>=stage['end_frame'] or
                any(a['frame']>=b['frame'] for a,b in zip(keys,keys[1:]))):
            raise StudioError('Dressing targets must cover entry through release with strictly ordered native frames')
        if support['start_frame']==1 and math.dist(keys[0]['point_cm'],entry['placed_cm'][vertex])>1e-5:
            raise StudioError('Dressing grip first target differs from its exact entry geometry')
        resolved.append(dict(support,vertex=vertex,resolved_waypoints=keys))
    if {row['method_id'] for row in resolved}!=set(profile['method_ids']):
        raise StudioError('Dressing explicit grips must cover every selected source method')
    constraints=[];covered=set()
    for constraint in instructions['endpoint_constraints']:
        if constraint['method_id'] not in profile['method_ids']:raise StudioError('Dressing endpoint names an unselected source method')
        method=methods[constraint['method_id']]
        if method['method'] in ('OPEN_HOOD_YOKE','OPEN_DETACHABLE_YOKE') and constraint['piece'] not in method['pieces']:
            raise StudioError('Dressing hood/yoke endpoint is outside its exact permanent source unit')
        vertex=source_grip_vertex(candidate,constraint);covered.add(constraint['method_id'])
        constraints.append(dict(constraint,vertex=vertex,point_cm=point(constraint['source_ref'],constraint['pointer'])))
    if covered!=set(profile['method_ids']):raise StudioError('Dressing final constraints must cover every selected source method')
    from .cloth_metrics import validate_metrics
    validate_metrics(candidate,entry['placed_cm'],inputs['recipe']['mesh'],include_faces=False)
    return {'status':'DRESSING_INSTRUCTIONS_PREPARED','profile':profile,'profile_ref':evidence[0],
            'paths':paths,'derivation':derivation,'motion_inputs':inputs,'instructions':instructions,
            'entry':entry,'entry_origin':entry_origin,'body_target':body,'body_origin':target_origin,
            'body_regions':body_regions,
            'source_method_configurations':{key:copy.deepcopy(methods[key]['configuration']) for key in profile['method_ids']
                                           if 'configuration' in methods[key]},
            'source_open_link_states':{key:copy.deepcopy(methods[key]['configuration']['source_link_states']) for key in profile['method_ids']
                                      if methods[key].get('configuration')},
            'supports':resolved,'constraints':constraints,'evidence':evidence,'diagnostics':[],
            'qualification':'NONE','simulation':'NOT_EXECUTED','binding_sha256':digest(evidence)}
