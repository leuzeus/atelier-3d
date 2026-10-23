"""Source-metric body-volume placement variant of the isolated real harness.

Use ``probe <prior-run>`` through run_pattern_validation for three bounded
geometry-only candidates, reusing the prior immutable derived source map.
Without arguments, replay the full real preparation harness with the guide.
"""
import copy
import json
import os
from pathlib import Path
import sys

ROOT=Path(__file__).resolve().parents[1]
sys.path.insert(0,str(ROOT))
import bpy
import numpy as np
from a3d.core import StudioError,atomic_json,digest,read_json,sha
from a3d.pattern_assembly import map_digest,preform_coordinates
from a3d.pattern_preparation import preparation_statistics
from a3d.preform_volume import volume_frames
from blender.fitting_pose import basis
from blender.sewing import placed_point,context_colliders
from blender.pattern_assembly import collision_guard
from tests import native_pattern_preparation_real as real

ORIGINAL_PREFORM=real.metric_preform
LAST_GUIDE=None
UPPER_BLEND=float(os.environ.get('A3D_VOLUME_UPPER_BLEND','0.25'))


def body_frame(project,recipe):
    envelope=read_json(project/'r21-envelope.json');ref=envelope['body_receipt']
    if sha(project/ref['path'])!=ref['sha256']:raise StudioError('Body guide receipt changed')
    body=read_json(project/ref['path']);bones=body['bones']['RIG_Robe']
    obj=bpy.data.objects[body['reference_object']]
    region=next(row for row in body['meshes'] if row['object']=='V3_Thorax_Masked')
    points=[list((obj.matrix_world@obj.data.vertices[i].co)*100)
        for i in range(region['vertex_offset'],region['vertex_offset']+region['vertices'])]
    low=bones['chest']['head_cm'][2];high=bones['upper_arm.L']['head_cm'][2]
    selected=[p for p in points if low<=p[2]<=high]
    bounds=[[min(p[k] for p in selected),max(p[k] for p in selected)] for k in range(3)]
    source='body receipt '+ref['path']+' sha256='+ref['sha256']+'; exact thorax vertices between chest head and upper-arm head; geometric hypothesis'
    return {'source_ref':source,'body_geometry_sha256':body['geometry_sha256'],
        'envelope_geometry_sha256':recipe['colliders'][0]['geometry_sha256'],
        'thorax_section_bounds_cm':bounds,'sample_vertices':len(selected),
        'aspect_ratio':(bounds[0][1]-bounds[0][0])/(bounds[1][1]-bounds[1][0]),
        'center_xy_cm':[(a+b)/2 for a,b in bounds[:2]],'hem_z_cm':17.,
        'hem_source_ref':'unchanged metric recipe panel placement z=17cm',
        'neck_center_cm':bones['neck']['head_cm'],
        'shoulders_cm':{'-1':bones['upper_arm.L']['head_cm'],'1':bones['upper_arm.R']['head_cm']},
        'bones':bones,'anatomical_validation':'NOT_QUALIFIED'}


def orient_sleeves(plan,data,recipe,frame):
    reports=[]
    for side,bone_side in (('l','L'),('r','R')):
        def center(selectors):
            points=[]
            for pid,edge in selectors:
                piece=data['pieces'][pid]
                points.extend(placed_point(piece['vertices'][i],recipe['placements'][pid]) for i in piece['edges'][edge])
            return np.mean(points,axis=0)
        upper='a07-upper-'+side;under='a07-under-'+side
        source_origin=center([(upper,'cap-front'),(upper,'cap-back'),(under,'cap-back'),(under,'cap-side')])
        source_axis=center([('a08-upper-'+side,'wrist'),('a08-under-'+side,'wrist')])
        source_transverse=center([(upper,'front'),(under,'front')])
        target_origin=np.array(frame['bones']['upper_arm.'+bone_side]['head_cm'])
        target_axis=np.array(frame['bones']['forearm.'+bone_side]['tail_cm'])
        sb,sl=basis(source_origin,source_axis,source_transverse)
        tb,tl=basis(target_origin,target_axis,target_origin+np.array([0.,-1.,0.]))
        rotation=tb@sb.T;translation=target_origin-rotation@source_origin
        if abs(sl-tl)>12.:raise StudioError('Source sleeve axis differs from target beyond retained pose correspondence budget')
        for prefix in ('a07-upper-','a07-under-','a08-upper-','a08-under-'):
            panel=plan['preform']['panels'][prefix+side]
            if 'target_cm' in panel:
                panel['target_cm']=[(rotation@np.array(p)+translation).tolist() for p in panel['target_cm']]
            else:
                panel['origin_cm']=(rotation@np.array(panel['origin_cm'])+translation).tolist()
                for axis in ('u_axis','v_axis'):panel[axis]=(rotation@np.array(panel[axis])).tolist()
            panel['source_ref']+='; rigid unscaled frame from named source edges to exact R21 shoulder/wrist bones'
        reports.append({'side':side,'source_origin_cm':source_origin.tolist(),'source_axis_cm':source_axis.tolist(),
            'target_origin_cm':target_origin.tolist(),'target_axis_cm':target_axis.tolist(),
            'source_axis_length_cm':sl,'target_axis_length_cm':tl,'rotation':rotation.tolist(),
            'translation_cm':translation.tolist(),'scaling_applied':False})
    return reports


def volume_plan(payload,recipe,data,frame,blend):
    plan=ORIGINAL_PREFORM(payload,recipe,data)
    groups=[]
    for side,sign in (('l',-1),('r',1)):
        ids={role:prefix+side for role,prefix in [('front','a04-front-'),('center','a06-center-'),('side','a05-side-'),('back','a05-back-')]}
        groups.append({**ids,'pieces':list(ids.values()),'side_sign':sign,'front_neck_cm':11.,'back_neck_cm':9.,'uv_origin_cm':[0.,0.]})
    panels,guide=volume_frames(data,groups,frame,blend)
    plan['preform']['panels'].update(panels)
    guide['sleeve_frames']=orient_sleeves(plan,data,recipe,frame)
    guide['collar']='SOURCE_METRIC_CYLINDER_UNCHANGED; its deep proxy contact remains a separate refusal'
    guide['neck_arc_lengths_cm']={'front':11.,'back':9.,'source':'approved a06.neck and a05.neck source edges'}
    plan['source_refs'].append('Metric volume guide hypothesis; source girth and named seam topology; upper_blend='+str(blend))
    return plan,guide


def metric_preform(payload,recipe,data):
    global LAST_GUIDE
    project=Path(os.environ['A3D_VALIDATION_OUTPUT'])/'project'
    plan,LAST_GUIDE=volume_plan(payload,recipe,data,body_frame(project,recipe),UPPER_BLEND)
    path=project/'volume-guide-hypothesis.json';atomic_json(path,LAST_GUIDE)
    plan['source_refs'].append(path.name+' sha256='+sha(path))
    return plan


def probe(prior,blends=(0.,.15,.25)):
    prior=Path(prior).resolve();out=Path(os.environ['A3D_VALIDATION_OUTPUT'])
    if prior.drive.upper()!='G:' or out.drive.upper()!='G:':raise ValueError('G: only')
    previous=read_json(prior/'report.json')['native_preparation'];project=prior/'project'
    master=project/previous['master']['path']
    bpy.ops.wm.open_mainfile(filepath=str(master),load_ui=False,use_scripts=False)
    payload=read_json(project/previous['derived_mesh']['path'])
    recipe=read_json(project/previous['recipe']['path']);data=read_json(project/payload['source_garment'])
    frame=body_frame(project,recipe);colliders,trees,snapshots=context_colliders(recipe)
    results=[]
    for blend in blends:
        plan,guide=volume_plan(payload,recipe,data,frame,blend)
        plan['mapping_sha256']=map_digest(payload);error=None
        try:coords,preform=preform_coordinates(payload,plan)
        except StudioError as exc:
            error=str(exc);coords=getattr(exc,'preform_coordinates_cm',None)
            if coords is None:
                result={'upper_blend':blend,'error':error,'coords_available':False};results.append(result)
                atomic_json(out/'result.json',results);print(json.dumps(result),flush=True);continue
            preform={'error':error}
        candidate=copy.deepcopy(payload);candidate['placed_cm']=coords
        statistics=preparation_statistics(candidate,coords,recipe['mass'])
        collision=collision_guard(candidate,trees,snapshots,plan,self_contacts=True)(coords)
        from blender.pattern_preparation import _placement_displacement
        source=[placed_point(p[:2],recipe['placements'][pid]) for pid,panel in payload['panels'].items() for p in [payload['rest_cm'][i] for i in panel['indices']]]
        displacement=_placement_displacement(payload,source,coords,plan['assembly']['max_displacement_cm'])
        label='blend-'+str(blend).replace('.','-');directory=out/label;directory.mkdir()
        for name,value in [('plan',plan),('guide',guide),('mesh',candidate),('statistics',statistics),('collision',collision)]:atomic_json(directory/(name+'.json'),value)
        extrema=statistics['extrema']
        gaps={sid:row['gap_distribution_cm']['max'] for sid,row in statistics['per_seam'].items()}
        result={'upper_blend':blend,'error':error,'coords_available':True,
            'min_principal_stretch':extrema['min_principal_stretch']['value'],
            'max_principal_stretch':extrema['max_principal_stretch']['value'],
            'min_placed_angle_degrees':extrema['min_placed_angle_degrees']['value'],
            'max_gap_cm':max(gaps.values()),'shoulder_gap_cm':max(gaps['epaule-l'],gaps['epaule-r']),
            'minimum_signed_offset_cm':collision['minimum_signed_offset_cm'],
            'self_contact_count':collision['self_contact']['nonadjacent_overlap_count'],
            'placement_displacement':displacement,'simulation':'NOT_EXECUTED'}
        results.append(result);atomic_json(out/'result.json',results);print(json.dumps(result),flush=True)


if __name__=='__main__':
    args=sys.argv[sys.argv.index('--')+1:] if '--' in sys.argv else []
    if args and args[0]=='probe':probe(args[1],tuple(float(value) for value in args[2:]) if len(args)>2 else (0.,.15,.25))
    else:
        real.metric_preform=metric_preform
        original_run=real.run
        def run(output,report):
            original_run(output,report);report['volume_guide_hypothesis']=LAST_GUIDE
        real.run=run;real.main()
