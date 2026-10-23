"""Isolated real preparation with source-measured neck frame and dressing audit."""
import math,os,sys
from pathlib import Path
ROOT=Path(__file__).resolve().parents[1];sys.path.insert(0,str(ROOT))
import bpy
from mathutils import Vector
from a3d.core import atomic_json,read_json,sha
from a3d.dressing import migrate_legacy_layers
from a3d.pattern_assembly import validate_plan
from tests import native_pattern_preparation_bend as bend
from tests import native_pattern_preparation_volume as volume


def measured_preform(payload,recipe,data):
    project=Path(os.environ['A3D_VALIDATION_OUTPUT'])/'project'
    frame=volume.body_frame(project,recipe)
    env=read_json(project/'r21-envelope.json');body_ref=env['body_receipt']
    body=read_json(project/body_ref['path']);target=bpy.data.objects[body['reference_object']]
    centers=[];source_rows=[]
    for number in (1,7):
        rows=[r for r in body['meshes'] if r['object'].startswith('V3_Cervical_'+str(number)+'_')]
        points=[list((target.matrix_world@target.data.vertices[i].co)*100) for row in rows
                for i in range(row['vertex_offset'],row['vertex_offset']+row['vertices'])]
        bounds=[[min(p[k] for p in points),max(p[k] for p in points)] for k in range(3)]
        centers.append([(a+b)/2 for a,b in bounds]);source_rows.append({'objects':[r['object'] for r in rows],'bounds_cm':bounds})
    axis=(Vector(centers[1])-Vector(centers[0])).normalized()
    # Keep the existing recipe's declared neck-base height. Only its local
    # source-measured center and axis replace the old world-origin assumption.
    base_z=recipe['placements']['a13-collar']['position_cm'][2]
    neck_base=Vector(centers[0])+axis*((base_z-centers[0][2])/axis.z)
    old_neck=frame['neck_center_cm'];frame['neck_center_cm']=list(neck_base)
    plan,guide=volume.volume_plan(payload,recipe,data,frame,volume.UPPER_BLEND)
    # Serialize the declared frame in float64. mathutils vectors are float32:
    # squaring their rounded norm can exceed the unchanged 1e-7 frame gate.
    collar=plan['preform']['panels']['a13-collar']
    raw=[centers[1][k]-centers[0][k] for k in range(3)]
    norm=math.sqrt(math.fsum(x*x for x in raw));v=[x/norm for x in raw]
    raw=[(-1. if k==0 else 0.)+v[k]*v[0] for k in range(3)]
    norm=math.sqrt(math.fsum(x*x for x in raw));u=[x/norm for x in raw]
    w=Vector((u[1]*v[2]-u[2]*v[1],u[2]*v[0]-u[0]*v[2],u[0]*v[1]-u[1]*v[0]))
    radius=recipe['placements']['a13-collar']['radius_cm']
    collar.update(origin_cm=list(neck_base-w*radius),u_axis=list(u),v_axis=list(v))
    collar['source_ref']+='; source-measured cervical mesh center and axis, unchanged base height/radius, no projection'
    landmarks={'version':1,'body_receipt':body_ref,'cervical_source_bounds':source_rows,
        'neck_axis_cm':centers,'neck_base_cm':list(neck_base),'previous_neck_frame_cm':old_neck,
        'source_patterns_changed':False,'body_or_envelope_changed':False,
        'material_side_convention':{'outward_normal_sign':-1,
            'evidence':'Source flat frames orient front/back/side triangle normals toward torso; permanent seam winding retains this convention.',
            'scope':'Geometric convention only; the approved source does not identify textile right/wrong sides.'},
        'anatomical_validation':'NOT_QUALIFIED_GEOMETRIC_LANDMARK_HYPOTHESIS'}
    path=project/'dressing-landmarks.json';atomic_json(path,landmarks)
    ref={'path':path.name,'sha256':sha(path)};collider=recipe['colliders'][0]['object']
    regions=[{'id':'neck','source_ref':ref,'collider':collider,'axis_start_cm':list(neck_base),
        'axis_end_cm':list(neck_base+axis*5),'section_parameters':[0.,.5,1.]},
        {'id':'torso','source_ref':body_ref,'collider':collider,
         'axis_start_cm':frame['bones']['pelvis']['head_cm'],
         'axis_end_cm':frame['bones']['chest']['tail_cm'],'section_parameters':[0.,.5,1.]}]
    openings=[{'id':'collar-base','source_ref':ref,'region':'neck','section_parameter':0.,
        'plane_tolerance_cm':.05,'edges':[{'piece':'a13-collar','edge':edge,'reverse':False}
            for edge in ('front-l','back-l','back-r','front-r')]}]
    for side in ('l','r'):
        regions.append({'id':'arm-'+side,'source_ref':body_ref,'collider':collider,
            'axis_start_cm':frame['bones']['upper_arm.'+side.upper()]['head_cm'],
            'axis_end_cm':frame['bones']['forearm.'+side.upper()]['tail_cm'],'section_parameters':[0.,.5,1.]})
        openings.append({'id':'wrist-'+side,'source_ref':ref,'region':'arm-'+side,'section_parameter':1.,
            'plane_tolerance_cm':1.,'edges':[{'piece':'a08-upper-'+side,'edge':'wrist','reverse':False},
                {'piece':'a08-under-'+side,'edge':'wrist','reverse':True}]})
    assignments=[{'piece':pid,'region':'neck' if pid=='a13-collar' else 'arm-'+pid[-1]
        if pid.startswith(('a07-','a08-')) else 'torso','outward_normal_sign':-1} for pid in payload['panels']]
    plan['dressing']={'version':1,'required':True,'source_ref':ref,'regions':regions,'openings':openings,
        'assignments':assignments,'mount_order':[o['id'] for o in openings],'milestones':[]}
    plan['layers']=migrate_legacy_layers(payload,{collider:'body'},ref)['layers']
    guide['neck_frame_correction']=landmarks;volume.LAST_GUIDE=guide
    atomic_json(project/'volume-guide-hypothesis.json',guide)
    validate_plan(payload,plan)  # Fail this harness before expensive derivation if its frame is invalid.
    return plan


if __name__=='__main__':
    volume.ORIGINAL_PREFORM=bend.metric_bend_preform
    volume.real.metric_preform=measured_preform
    volume.real.main()
