"""Animate copied calibrated rigid geometry from actually observed cloth frames."""
import copy
import math
import time
import uuid

from a3d.core import StudioError, atomic_json, digest, sha
from a3d.rigid_attachment import rigid_attachment_descriptor
from a3d.garment_motion import checked_reference
from a3d.export_profiles import compare_native_samples
from blender.asset_export import (ExportBudgetReached, action_payloads, assign_clip, check_deadline, image_payloads,
                                  load_candidate, native_samples, rest_payload)
from blender.animated_delivery import _source_candidate, _ref
from blender.body_motion import _curves, action_payload


def _run_attachment(project, inputs, directory, deadline):
    import bpy
    from mathutils import Matrix, Vector
    profile=inputs['profile']; source=inputs['source']; first=inputs['clips'][0]['target']['clip']
    resources={'source_resources':[]}; bounds=(first['frame_start'],first['frame_end'],first['fps'])
    source_candidate,_=_source_candidate(project,source['artifact'],resources,bounds,[],deadline)
    source_object=source_candidate['objects'][profile['object_name']]
    if (source_object.type!='MESH' or source_object.parent or source_object.constraints or source_object.modifiers or
            source_object.animation_data or source_object.data.shape_keys or
            max(abs(source_object.matrix_world[i][j]-(1. if i==j else 0.)) for i in range(4) for j in range(4))>1e-7):
        raise StudioError('Rigid attachment requires exact static world-calibrated source geometry')
    actual_rest={'vertices_cm':[[float(v)*100 for v in row.co] for row in source_object.data.vertices],
                 'faces':[list(row.vertices) for row in source_object.data.polygons]}
    source_rest=inputs['geometry'][profile['object_name']]
    compare_native_samples([{'clip_id':'rest','time':1,'meshes':{'rigid':source_rest}}],
                           [{'clip_id':'rest','time':1,'meshes':{'rigid':actual_rest}}],profile['geometry_tolerance_cm'])
    scene=bpy.data.scenes.new('A3D.RigidAttachment.'+uuid.uuid4().hex);scene.unit_settings.system='METRIC';scene.unit_settings.scale_length=1.
    scene.render.fps=first['fps'];scene.render.fps_base=1.
    scene.frame_start=min(row['frames'][0]['frame'] for row in inputs['clips']);scene.frame_end=max(row['frames'][-1]['frame'] for row in inputs['clips'])
    prefix='A3D.Attached.'+uuid.uuid4().hex+'.'
    rigid=source_object.copy();rigid.data=source_object.data.copy();rigid.name=prefix+profile['component_id'];scene.collection.objects.link(rigid)
    objects={rigid.name:rigid};actions={};images=dict(source_candidate['images']);clips=[];target_proofs=[];source_expected={}
    for group in inputs['clips']:
        check_deadline(deadline);cid=group['declaration']['id'];target=group['target'];primary=target['clip'];body=target['object_inventory']['body']
        candidate,native_profile=_source_candidate(project,target['artifact'],resources,(primary['frame_start'],primary['frame_end'],primary['fps']),[dict(primary,sample_step=1)],deadline)
        target_clip=dict(primary,sample_step=1,tracks=[{key:body['body_action'][key] for key in ('object_name','action_name','slot_identifier','animation_target')}])
        before=native_samples(candidate,dict(native_profile,clips=[target_clip]),deadline)[1:]
        cloth_name=target['object_inventory']['garment']['object_name'];body_name=body['object_name']
        if (digest(action_payload(candidate['actions'][primary['action_name']]))!=primary['action_sha256'] or
                digest(action_payload(candidate['actions'][body['body_action']['action_name']]))!=body['body_action']['action_sha256']):
            raise StudioError('Rigid target actual Actions differ from their registered source clip')
        wanted=[]
        for observed in group['observations']['frames']:
            meshes={cloth_name:{'vertices_cm':observed['vertices_cm'],'faces':group['candidate']['faces']},
                    body_name:{key:observed['body'][key] for key in ('vertices_cm','faces','face_sets')}}
            if 'face_sets' in before[len(wanted)]['meshes'][cloth_name]:meshes[cloth_name]['face_sets']=before[len(wanted)]['meshes'][cloth_name]['face_sets']
            wanted.append({'clip_id':primary['id'],'time':observed['frame'],'meshes':meshes})
        evaluated=[{'clip_id':primary['id'],'time':row['time'],'meshes':{name:row['meshes'][name] for name in (cloth_name,body_name)}} for row in before]
        target_proofs.append({'id':cid,'comparison':compare_native_samples(wanted,evaluated,profile['geometry_tolerance_cm']),
                              'target_receipt':group['declaration']['target_receipt'],'target_origin':group['target_origin'],'bindings':group['bindings'],'offset':group['offset']})
        name_map={name:prefix+cid+'.Target.'+name for name in candidate['objects']}
        for name,obj in candidate['objects'].items():
            obj.name=name_map[name];name_map[name]=obj.name;objects[obj.name]=obj;scene.collection.objects.link(obj)
        action_map={}
        for name,action in candidate['actions'].items():
            action.name=prefix+cid+'.TargetAction.'+name;action_map[name]=action.name;actions[action.name]=action
        for image in candidate['images'].values():images[image.name]=image
        tracks=[{'object_name':name_map[track['object_name']],'action_name':action_map[track['action_name']],
                 'slot_identifier':track['slot_identifier'],'animation_target':track['animation_target']}
                for track in (body['body_action'],primary)]
        rigid.animation_data_clear();previous=None
        with bpy.context.temp_override(scene=scene,view_layer=scene.view_layers[0]):
            for frame in group['frames']:
                check_deadline(deadline);quaternion=Matrix(frame['rotation']).to_quaternion()
                if previous is not None and quaternion.dot(previous)<0:quaternion.negate()
                previous=quaternion.copy();rigid.rotation_mode='QUATERNION';rigid.rotation_quaternion=quaternion
                rigid.location=[v/100 for v in frame['translation_cm']];rigid.scale=(1.,1.,1.)
                rigid.keyframe_insert('location',frame=frame['frame']);rigid.keyframe_insert('rotation_quaternion',frame=frame['frame'])
            action=rigid.animation_data.action;action.name=prefix+cid+'.RigidAction';actions[action.name]=action
            for curve in _curves(action):
                curve.extrapolation='CONSTANT'
                for point in curve.keyframe_points:point.interpolation='LINEAR'
            clip={'id':cid,'object_name':rigid.name,'action_name':action.name,'slot_identifier':rigid.animation_data.action_slot.identifier,
                  'animation_target':'OBJECT','frame_start':group['frames'][0]['frame'],'frame_end':group['frames'][-1]['frame'],'sample_step':1,'tracks':tracks}
            clips.append(clip)
        source_expected[cid]=[]
        for frame,row in zip(group['frames'],before,strict=True):
            transformed=[[sum(frame['rotation'][i][j]*point[j] for j in range(3))+frame['translation_cm'][i] for i in range(3)] for point in actual_rest['vertices_cm']]
            meshes={name_map[name]:mesh for name,mesh in row['meshes'].items()}
            meshes[rigid.name]={'vertices_cm':transformed,'faces':actual_rest['faces']}
            if '.sculpt_face_set' in rigid.data.attributes:
                meshes[rigid.name]['face_sets']=[item.value for item in rigid.data.attributes['.sculpt_face_set'].data]
            source_expected[cid].append({'clip_id':cid,'time':frame['frame'],'meshes':meshes})
    candidate={'scene':scene,'objects':objects,'actions':actions,'images':images}
    export={'version':1,'destination':'blender_animation','source_ref':{'path':'pending.blend','sha256':'0'*64},
            'object_names':sorted(name for name,obj in objects.items() if obj.type=='MESH'),'dependency_names':sorted(name for name,obj in objects.items() if obj.type!='MESH'),
            'action_names':sorted(actions),'embedded_image_names':sorted(images),'unit_scale_m':1.,'fps':first['fps'],'reference_frame':scene.frame_start,
            'clips':clips,'resources':[],'motion_receipts':[],'pack_resources':True,'geometry_tolerance_cm':profile['geometry_tolerance_cm'],
            'budgets':{'max_seconds':profile['budgets']['max_seconds'],'max_samples':profile['budgets']['max_samples']}}
    assign_clip(candidate,clips[0]); samples=native_samples(candidate,export,deadline);comparisons=[]
    for clip in clips:
        observed=[row for row in samples[1:] if row['clip_id']==clip['id']];expected=source_expected[clip['id']]
        names=set(expected[0]['meshes']); subset=[dict(row,meshes={name:row['meshes'][name] for name in names}) for row in observed]
        comparisons.append({'id':clip['id'],'comparison':compare_native_samples(expected,subset,profile['geometry_tolerance_cm'])})
    before_rest=rest_payload(candidate);before_actions=action_payloads(candidate);packed=image_payloads(candidate)
    artifact=directory/'attached-part.blend';check_deadline(deadline);scene.view_layers[0].update()
    bpy.data.libraries.write(str(artifact),{scene,*actions.values(),*images.values()},fake_user=True)
    export['source_ref']=_ref(project,artifact)
    reopened=load_candidate(artifact,export,'RigidAttachmentReopen',scene_name=scene.name)
    after=native_samples(reopened,export,deadline);reimport=compare_native_samples(samples,after,profile['geometry_tolerance_cm'])
    if rest_payload(reopened)!=before_rest or action_payloads(reopened)!=before_actions or image_payloads(reopened)!=packed:
        raise StudioError('Rigid attachment reimport changed source rest, UVs, Actions or dependencies')
    measured=[]
    for clip,group in zip(clips,inputs['clips'],strict=True):
        row=copy.deepcopy(clip);row.update(status='EXECUTED_FULL_CLIP',executed_times=[value['frame'] for value in group['frames']],
            action_sha256=digest(before_actions[clip['action_name']]),body_motion_binding=group['target']['body_motion_binding'],
            geometry_scope='RIGID_TRANSFORMS_FROM_OBSERVED_TEXTILE_FRAMES',interpolation='LINEAR_QUATERNION_COMPONENTS_NORMALIZED_BY_BLENDER')
        row['tracks']=[dict(track,action_sha256=digest(before_actions[track['action_name']])) for track in row['tracks']]
        row['samples']=[{'time':value['time'],'meshes':{name:dict(mesh,geometry_sha256=digest([mesh['vertices_cm'],mesh['faces']])) for name,mesh in value['meshes'].items()}}
                        for value in samples[1:] if value['clip_id']==clip['id']]
        measured.append(row)
    geometry_path=directory/'geometry.json';atomic_json(geometry_path,{rigid.name:actual_rest})
    frames_path=directory/'attachment-frames.json';atomic_json(frames_path,{'clips':[{'id':row['declaration']['id'],'frames':row['frames']} for row in inputs['clips']]})
    proof_path=directory/'comparison.json';atomic_json(proof_path,{'candidate':export['source_ref'],'target_source_comparisons':target_proofs,
        'expected_source_samples':source_expected,'attachment_comparisons':comparisons,'samples_before':samples,'samples_after':after,'native_reimport_comparison':reimport,
        'rest':before_rest,'actions':before_actions,'packed_images':packed})
    clips_path=directory/'clips.json';atomic_json(clips_path,{'candidate':export['source_ref'],'fps':first['fps'],'scope':'EXACT_CANDIDATE_ANIMATION','clips':measured})
    check_deadline(deadline)
    return {'status':'RIGID_PART_PREPARED_UNACCEPTED','artifact':export['source_ref'],'candidate':export['source_ref'],'geometry':_ref(project,geometry_path),
        'geometry_sha256':digest({rigid.name:actual_rest}),'object_names':[rigid.name],'native_reopened':True,'fps':first['fps'],
        'scope':'EXACT_CANDIDATE_ANIMATION','temporal_coverage':'COMPLETE','clips':[{k:v for k,v in row.items() if k!='samples'} for row in measured],
        'clips_artifact':_ref(project,clips_path),'comparison_artifact':_ref(project,proof_path),'attachment_frames_artifact':_ref(project,frames_path),
        'source_calibration_geometry_sha256':source['geometry_sha256'],'intrinsic_dimensions_cm':source['measured_dimensions_cm'],
        'native_reimport_comparison':reimport,'placement_binding':{'status':'SOURCE_BOUND','mode':'OBSERVED_TEXTILE_FRAME_ACTIONS','geometry_sha256':digest({rigid.name:actual_rest}),
            'source_refs':[profile['source_receipt'],source['artifact'],source['geometry'],source['candidate'],source['profile'],source['package'],source['dossier']],
            'target_refs':[ref for row in inputs['clips'] for ref in (row['declaration']['target_receipt'],row['target']['artifact'],row['target']['observations_artifact'],*row['target']['bindings'].values())],
            'orientation_source_ref':source['package'],'anchors_mapping_ref':profile['anchor_map_ref']},
        'object_inventory':{'body':{'source_motion_bindings':[{'id':row['declaration']['id'],'motion_binding':row['target']['body_motion_binding']} for row in inputs['clips']]}},
        'attachment_relation':'SOURCE_ATTACHED_SEPARATE_NO_MERGE','parent_created':False,'intermediate_frame_attachment':'NOT_QUALIFIED',
        'continuous_collision_qualification':'NOT_GRANTED','source_geometry_changed':False,'body_changed':False,'patterns_changed':False}


def attach_reconstructed_part(project_root,profile_path):
    import bpy
    from a3d.store import Project
    from blender.body_source import data_ids,live_geometry
    project=Project(project_root);inputs=rigid_attachment_descriptor(project,profile_path);profile=inputs['profile']
    baseline=data_ids();live=live_geometry();db_sha=sha(project.db);original=bpy.context.scene;frame=original.frame_current;subframe=original.frame_subframe
    filepath=bpy.data.filepath;selected=set(bpy.context.selected_objects);active=bpy.context.view_layer.objects.active
    start=time.monotonic();deadline=start+profile['budgets']['max_seconds'];directory=project.data/('outputs/rigid-attachment-'+uuid.uuid4().hex);directory.mkdir(parents=True,exist_ok=False)
    result={'version':1,'component_id':profile['component_id'],'piece_id':profile['piece_id'],'purpose':profile['purpose'],'profile':inputs['profile_ref'],
        'package':inputs['source']['package'],'dossier':inputs['source']['dossier'],'provider_source_ref':inputs['source']['candidate'],
        'source_origin':inputs['source_origin'],'binding_sha256':inputs['binding_sha256'],'accepted':False,'product_acceptance':'NOT_GRANTED',
        'fitting':'NOT_QUALIFIED','artistic_review':'REQUIRED','placement_review':'HUMAN_REVIEW_REQUIRED','original_preserved':True}
    try:result.update(_run_attachment(project,inputs,directory,deadline))
    except ExportBudgetReached as error:result.update(status='INCOMPLETE',temporal_coverage='INCOMPLETE',stopped=str(error),clips=[])
    finally:
        bpy.data.batch_remove(ids=data_ids()-baseline)
        if (data_ids()!=baseline or live_geometry()!=live or sha(project.db)!=db_sha or bpy.context.scene!=original or
                original.frame_current!=frame or original.frame_subframe!=subframe or bpy.data.filepath!=filepath or
                set(bpy.context.selected_objects)!=selected or bpy.context.view_layer.objects.active!=active):
            raise StudioError('Rigid attachment altered production context or canonical state')
        checked_reference(project,profile['source_receipt']);checked_reference(project,inputs['source']['artifact']);checked_reference(project,inputs['profile_ref'])
        for row in profile['clips']:checked_reference(project,row['target_receipt'])
    result['elapsed_seconds']=time.monotonic()-start;result['blender_version']=bpy.app.version_string;result['cache_key']=digest(result)
    path=directory/'receipt.json';atomic_json(path,result);return dict(result,receipt=_ref(project,path))
