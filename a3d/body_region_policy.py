"""Prepare generic limb measurement inputs from an exact anatomical adapter.

No measurements, body edits, garment-specific coordinates or acceptance occur
here. Portable references still require canonical native admission by the
consumer; a signature is not evidence that a body was created or introduced.
"""
import copy
import math

from .catalog_anatomy import region_guides
from .core import ROOT, StudioError, contract, digest, inside, read_json, sha


def _reference(value):
    if (not isinstance(value,dict) or set(value)!={'path','sha256'} or
            not isinstance(value['path'],str) or not value['path'] or
            not isinstance(value['sha256'],str) or len(value['sha256'])!=64 or
            any(c not in '0123456789abcdef' for c in value['sha256'])):
        raise StudioError('Body region policy needs an explicit exact source reference')


def _centroid_roundtrip_bound(vertices,ids):
    # Native body vertices are stored by Blender as float32 metres; sourced
    # transformed guides retain doubles. Bound one float32 rounding per source
    # coordinate, then average it over the exact source centroid's vertices.
    # This is representation uncertainty, never an anatomical or fit tolerance.
    axis=[]
    for dim in range(3):
        errors=[]
        for i in ids:
            value=abs(vertices[i][dim])/100.
            exponent=math.frexp(value)[1] if value else -125
            errors.append(100.*2.**(max(exponent,-125)-25))
        axis.append(sum(errors)/len(ids)+1e-10)
    return math.sqrt(sum(value*value for value in axis))


def build_body_region_policy(profile,geometry,triangles,adapter,source_geometry,refs,options):
    """Return a prepared body-region-sections policy, never measured sections.

    Options use body-region-policy-options.schema.json. References are explicit
    profile_ref/geometry_ref/triangles_ref/adapter_ref/source_geometry_ref.
    Each arm domain contains all actual same-side upper-arm, forearm and hand
    memberships: this keeps oblique limb-end contours on their source skin.
    Missing source domains/joints yield NEEDS_DATA, without guessed coordinates.
    Inconsistent geometry, references or source joint positions are refused.
    """
    contract('body-region-policy-options',options)
    before=digest([profile,geometry,triangles,adapter,source_geometry,refs,options])
    required_refs=('profile_ref','geometry_ref','triangles_ref','adapter_ref','source_geometry_ref')
    if not isinstance(refs,dict) or set(refs)!=set(required_refs):
        raise StudioError('Body region policy requires all exact body and adapter references')
    for value in refs.values():_reference(value)
    fractions=options['fractions'];lo,hi=options['fraction_domain']
    if (not lo<hi or fractions!=sorted(set(fractions)) or fractions[0]!=lo or fractions[-1]!=hi):
        raise StudioError('Body region policy fractions must cover both explicit domain boundaries uniquely')
    requested=len(options['regions'])*len(options['sides'])*len(fractions)
    if requested>options['budgets']['max_sections']:
        raise StudioError('Prepared body region sample count exceeds the explicit section budget')
    missing=[name for name,value in (('profile',profile),('geometry',geometry),('triangles',triangles),
                                   ('adapter',adapter),('source_geometry',source_geometry)) if not value]
    diagnostics=[{'source':name,'reason':'SOURCE_DATA_REQUIRED'} for name in missing]
    policy=None;derivation=[]
    if not missing:
        labels=geometry.get('face_sets',[])
        if (adapter.get('source_geometry_sha256')!=digest([source_geometry.get('vertices_cm'),source_geometry.get('faces'),source_geometry.get('face_sets')]) or
                geometry.get('faces')!=source_geometry.get('faces') or labels!=source_geometry.get('face_sets') or
                len(geometry.get('vertices_cm',[]))!=len(source_geometry.get('vertices_cm',[])) or
                geometry.get('source_sha256')!=source_geometry.get('source_sha256') or
                (isinstance(adapter.get('source_ref'),dict) and adapter['source_ref'].get('sha256')!=geometry.get('source_sha256'))):
            raise StudioError('Body region policy source adapter, original metric or variant topology changed')
        if not adapter.get('source_ref'):
            diagnostics.append({'source':'adapter.source_ref','reason':'SOURCE_PROVENANCE_REQUIRED'})
        if not adapter.get('torso_regions'):
            diagnostics.append({'source':'adapter.torso_regions','reason':'SOURCE_SEGMENTATION_REQUIRED'})
        if diagnostics:
            guides=None
        else:
            # Recompute original source rings/centroids without rebinding the
            # adapter to a stature or regional body variant's changed metric.
            guides=region_guides(source_geometry,adapter)
        identity={'profile_sha256':digest(profile),'profile_cache_key':profile.get('cache_key'),
                  'geometry_sha256':digest([geometry['vertices_cm'],geometry['faces']]),
                  'source_sha256':geometry['source_sha256'],'pose_sha256':geometry['pose_sha256'],
                  'face_sets_sha256':digest(labels),'triangles_sha256':digest(triangles)}
        from .body_region_sections import _identity,_joint,_plane
        probe={'identity':identity}
        _identity(profile,geometry,triangles,probe)
        memberships=adapter.get('region_to_bone',{})
        if (not isinstance(memberships,dict) or any(not isinstance(k,str) or not k.isdecimal() or
                str(int(k))!=k or not isinstance(v,str) or not v for k,v in memberships.items())):
            raise StudioError('Body region policy needs unambiguous integer source region memberships')
        policy={'version':1,'purpose':options['purpose'],'identity':identity,
                'bindings':{key:copy.deepcopy(refs[key]) for key in required_refs[:3]},
                'numerical_tolerance_cm':options['numerical_tolerance_cm'],'regions':[],
                'budgets':copy.deepcopy(options['budgets'])}

        joint_checks={}
        def joint(name,in_profile=True):
            if guides is None or name not in guides['rig_landmarks'] or name not in geometry.get('rig_landmarks',{}):
                diagnostics.append({'source':name,'reason':'SOURCED_JOINT_REQUIRED'});return None
            evidence=guides['joint_evidence'][name]
            if 'boundary_vertices' in evidence:ids=evidence['boundary_vertices']
            else:ids=sorted({i for index,face in enumerate(geometry['faces'])
                            if labels[index] in evidence['regions'] for i in face})
            expected=[sum(geometry['vertices_cm'][i][axis] for i in ids)/len(ids) for axis in range(3)]
            actual=_joint(profile,geometry,name,in_profile)
            residual=math.dist(actual,expected);bound=_centroid_roundtrip_bound(geometry['vertices_cm'],ids)
            if residual>bound:
                raise StudioError('Body region policy joint differs from its exact source ring or centroid: '+name)
            joint_checks[name]={'centroid_residual_cm':residual,'native_float32_centroid_roundtrip_bound_cm':bound,
                                'source_vertex_ids_sha256':digest(ids),'representation_scope':'FLOAT32_METRE_VERTEX_STORAGE_DOUBLE_SOURCE_GUIDE'}
            return actual

        for side in options['sides']:
            bones=['upper_arm.'+side,'forearm.'+side,'hand.'+side]
            by_bone={bone:sorted(int(k) for k,v in memberships.items() if v==bone) for bone in bones}
            for bone,values in by_bone.items():
                if not values:diagnostics.append({'source':bone,'reason':'SOURCE_REGION_MEMBERSHIP_REQUIRED'})
                elif set(values)-set(labels):raise StudioError('Body region policy mapping names absent source skin: '+bone)
            selected={label for values in by_bone.values() for label in values}
            ids=[i for i,label in enumerate(labels) if label in selected]
            for region in options['regions']:
                start_name=('shoulder.' if region=='upper' else 'wrist.')+side;end_name='elbow.'+side
                start,end=joint(start_name),joint(end_name)
                if any(not by_bone[bone] for bone in bones) or start is None or end is None:continue
                _plane(profile,start,end,options['plane_reference_axis'])
                policy['regions'].append({'id':region+'.'+side,'side':side,
                    'domain':'SHOULDER_TO_ELBOW_ONLY' if region=='upper' else 'WRIST_TO_ELBOW_ONLY',
                    'axis_start_landmark':start_name,'axis_end_landmark':end_name,
                    'plane_reference_axis':options['plane_reference_axis'],
                    'fraction_domain':copy.deepcopy(options['fraction_domain']),'fractions':copy.deepcopy(fractions),
                    'face_ids':ids,'source_ref':copy.deepcopy(refs['adapter_ref'])})
                derivation.append({'id':region+'.'+side,'membership_labels':copy.deepcopy(by_bone),
                                   'source_face_ids_sha256':digest(ids),
                                   'axis_landmarks':[start_name,end_name],'source_joint_evidence':
                                   {name:copy.deepcopy(guides['joint_evidence'][name]) for name in (start_name,end_name)}})
            if options['include_hand_envelopes']:
                hand_labels=by_bone['hand.'+side];center_labels=adapter.get('centers',{}).get('hand.'+side,[])
                if not center_labels or set(center_labels)-set(hand_labels):
                    diagnostics.append({'source':'hand.'+side,'reason':'SOURCED_HAND_CENTER_REQUIRED'});continue
                wrist,hand=joint('wrist.'+side),joint('hand.'+side,False)
                if not hand_labels or wrist is None or hand is None:continue
                _plane(profile,wrist,hand,options['plane_reference_axis'])
                policy.setdefault('hand_envelopes',[]).append({'id':'hand-envelope.'+side,'side':side,
                    'plane_reference_axis':options['plane_reference_axis'],'source_ref':copy.deepcopy(refs['adapter_ref'])})
                hand_ids=[i for i,label in enumerate(labels) if label in hand_labels]
                derivation.append({'id':'hand-envelope.'+side,'membership_labels':{'hand.'+side:copy.deepcopy(hand_labels)},
                    'source_face_ids_sha256':digest(hand_ids),'source_center_labels':copy.deepcopy(center_labels),
                    'axis_landmarks':['wrist.'+side,'hand.'+side],
                    'scope':'WHOLE_MAPPED_HAND_SKIN_PROJECTION_DOMAIN_ONLY_ANATOMICAL_GIRTH_NOT_MEASURED'})
        if policy.get('hand_envelopes'):
            policy['hand_source']={key:copy.deepcopy(refs[key]) for key in ('adapter_ref','source_geometry_ref')}
            policy['hand_source'].update(adapter_sha256=digest(adapter),source_geometry_sha256=digest(source_geometry))
        if policy['regions']:contract('body-region-sections',policy)
        else:policy=None
    result={'version':1,'status':'NEEDS_DATA' if diagnostics else 'BODY_REGION_POLICY_PREPARED_NOT_MEASURED',
            'policy':policy,'diagnostics':diagnostics,'derivation':derivation,'refs':copy.deepcopy(refs),
            'options':copy.deepcopy(options),'adapter_rebound_to_variant':False,
            'source_face_domain':'EXACT_SAME_SIDE_UPPER_ARM_FOREARM_HAND_MEMBERSHIPS',
            'measurements':'NOT_EXECUTED','body_changed':False,'anatomical_targets_changed':False,
            'physical_hand_passage':'NOT_QUALIFIED','fitting':'NOT_EXECUTED','acceptance':'NOT_GRANTED',
            'native_body_origin':'NOT_CHECKED_BY_PORTABLE_POLICY_BUILDER'}
    result['source_joint_checks']=joint_checks if policy is not None else {}
    result['code_sha256']={name:sha(ROOT/('a3d/'+name+'.py')) for name in
                           ('body_region_policy','body_region_sections','catalog_anatomy','dressing_derivation',
                            'shoulder_surface','head_surface','garment_guides','anatomy_profile','contact_geometry','sewing','core')}
    result['options_schema_sha256']=sha(ROOT/'schemas/body-region-policy-options.schema.json')
    if before!=digest([profile,geometry,triangles,adapter,source_geometry,refs,options]):
        raise StudioError('Body region policy builder changed an immutable source input')
    result['cache_key']=digest(result)
    return result


def prepare_project_body_region_policy(project,options_path,profile_ref):
    """Derive references from a genuine native body result, without mutations.

    The client chooses an exact measured profile and explicit policy options.
    All other source references come from its canonical completed native
    creation/introduction receipt. No client signature replaces that origin.
    """
    from .native_evidence import checked_reference,native_origin
    _reference(profile_ref);checked_reference(project,profile_ref)
    options_file=inside(project.root,options_path);options=contract('body-region-policy-options',read_json(options_file))
    options_ref={'path':options_path,'sha256':sha(options_file)}
    native,origin=native_origin(project,lambda doc:
        (doc.get('operation')=='prepare_body_target' and doc.get('result',{}).get('artifacts',{}).get('profile')==profile_ref) or
        (doc.get('operation')=='introduce_body_target' and doc.get('result',{}).get('profile_ref')==profile_ref))
    context_ref=None
    if native['operation']=='introduce_body_target':
        from .body_context import body_context_descriptor
        descriptor=body_context_descriptor(project,native['arguments']['context_path']);receipt=descriptor['receipt']
        profile=descriptor['profile'];geometry=descriptor['geometry'];result=native['result']
        if (result.get('status')!='BODY_TARGET_INTRODUCED' or
                result.get('binding_sha256')!=descriptor['binding_sha256'] or
                result.get('profile_cache_key')!=profile['cache_key'] or result.get('context')!=descriptor['context_ref'] or
                result.get('body_target_receipt')!=descriptor['context']['body_target_receipt'] or
                result.get('source_artifact')!=receipt['artifact'] or
                result.get('geometry_ref')!=receipt['artifacts']['geometry'] or
                result.get('actual_geometry_sha256')!=digest({key:geometry[key] for key in ('vertices_cm','faces','face_sets')})):
            raise StudioError('Body region policy introduction differs from its exact native body context')
        context_ref=descriptor['context_ref']
    else:receipt=native['result']
    if (receipt.get('cache_key')!=digest({k:v for k,v in receipt.items() if k!='cache_key'}) or
            receipt.get('status')!='NATIVE_BODY_TARGET_MEASURED' or receipt.get('native_reopened') is not True or
            receipt.get('artifacts',{}).get('profile')!=profile_ref):
        raise StudioError('Body region policy requires the exact reopened measured native body result')
    # Verify all physical body artifacts and selected-source inputs, including
    # the original adapter metric. Source anatomy cannot be replaced by a
    # signed client policy, even if the target profile happens to be unchanged.
    checked_reference(project,receipt['artifact'])
    for ref in [*receipt['artifacts'].values(),*receipt['evidence'].values()]:checked_reference(project,ref)
    from .body_target import target_descriptor
    target=target_descriptor(project,receipt['evidence']['selection']['path'],receipt['evidence']['target']['path'])
    if target['evidence']!=receipt['evidence']:
        raise StudioError('Body region policy selected source or target differs from its exact native origin')
    refs={key:copy.deepcopy(receipt['artifacts'][name]) for key,name in
          (('profile_ref','profile'),('geometry_ref','geometry'),('triangles_ref','triangles'),('source_geometry_ref','source-geometry'))}
    refs['adapter_ref']=copy.deepcopy(receipt['evidence']['adapter'])
    values=[read_json(inside(project.root,refs[key]['path'])) for key in
            ('profile_ref','geometry_ref','triangles_ref','adapter_ref','source_geometry_ref')]
    result=build_body_region_policy(*values,refs,options)
    if checked_reference(project,profile_ref)!=refs['profile_ref']:
        raise StudioError('Body region policy profile changed during source derivation')
    result.update(native_body_origin=origin,options_ref=options_ref,body_context_ref=context_ref)
    result['code_sha256'].update({name:sha(ROOT/('a3d/'+name+'.py')) for name in ('native_evidence','body_context','body_target')})
    result['cache_key']=digest({k:v for k,v in result.items() if k!='cache_key'})
    return result
