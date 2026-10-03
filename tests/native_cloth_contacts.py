"""Static and discrete trajectory contact witnesses, factory Blender on G:."""
import copy
import os
from pathlib import Path
import sys
import time

ROOT=Path(__file__).resolve().parents[1]
sys.path.insert(0,str(ROOT))
import bpy
from a3d.core import atomic_json
from blender.cloth_contacts import build_contact_context,check_contacts,check_motion,precise_self_contacts


def source(coords,faces=None):
    faces=faces or [[0,1,2]]
    return {'rest_cm':copy.deepcopy(coords),'placed_cm':copy.deepcopy(coords),'faces':faces,'seams':{},
        'panels':{str(i):{'indices':list(face),'edges':{}} for i,face in enumerate(faces)}}


def box(inward=False):
    coords=[[-1,-1,-1],[1,-1,-1],[1,1,-1],[-1,1,-1],[-1,-1,1],[1,-1,1],[1,1,1],[-1,1,1]]
    faces=[[0,3,2,1],[4,5,6,7],[0,1,5,4],[1,2,6,5],[2,3,7,6],[3,0,4,7]]
    if inward:faces=[list(reversed(face)) for face in faces]
    mesh=bpy.data.meshes.new('TEST.ClosedBody')
    mesh.from_pydata([[x/100 for x in p] for p in coords],[],faces)
    obj=bpy.data.objects.new('TEST.ClosedBody',mesh)
    bpy.context.scene.collection.objects.link(obj)
    bpy.context.view_layer.update()
    return obj


def main():
    output=Path(os.environ['A3D_VALIDATION_OUTPUT'])
    assert output.drive.upper()=='G:'
    body=box();results={}
    # The entire box section lies strictly inside this large triangle, while
    # every vertex, edge and centroid remains outside the body.
    crossing=[[-10.,-10.,0.],[30.,-10.,0.],[-10.,30.,0.]]
    payload=source(crossing)
    context=build_contact_context(payload,[body],max_penetration_cm=.05)
    report=check_contacts(context,crossing,frame=1)
    assert not report['ok'] and any(c['kind']=='TRANSVERSE_INTERSECTION' for c in report['contacts']),report
    assert report['point_samples']['ok'],report
    results['face_crossing_vertices_edges_centroid_outside']=report
    centered=[[-3.,-2.,0.],[3.,-2.,0.],[0.,4.,0.]]
    centered_context=build_contact_context(source(centered),[body])
    localized=check_contacts(centered_context,centered)
    assert localized['worst']['sample']==len(centered),localized
    assert localized['worst']['face']==0 and localized['worst']['pieces']==['0'],localized
    native_worst=localized['point_samples']['worst']
    assert 'pieces' not in native_worst and 'source_uv_cm' not in native_worst,native_worst
    assert native_worst['face']==localized['worst']['collider_triangle'],localized
    assert localized['worst']['collider_face']==centered_context['bodies'][0]['polygons'][native_worst['face']],localized
    results['collider_and_source_face_ids_remain_distinct']=localized
    limited=build_contact_context(payload,[body],max_pairs=1)
    exhausted=check_contacts(limited,crossing)
    assert not exhausted['ok'] and exhausted['reason']=='CONTACT_PAIR_BUDGET',exhausted
    results['pair_budget_exhaustion']=exhausted
    top=max(p[2] for p in context['bodies'][0]['coords'])
    tangent=[[p[0],p[1],top] for p in crossing]
    report=check_contacts(context,tangent,frame=1)
    assert report['ok'],report
    assert report['surface_pair_kinds'].get('COPLANAR_OVERLAP',0)>0,report
    results['external_coplanar_tangency']=report
    tangent_start=[[-2.,-.1,top],[-2.,.1,top],[-2.2,0.,top]]
    tangent_end=[[p[0]+4.2,p[1],p[2]] for p in tangent_start]
    tangent_context=build_contact_context(source(tangent_start),[body])
    tangent_motion=check_motion(tangent_context,tangent_start,tangent_end,1,2,max_step_cm=.25,max_subdivisions=32)
    assert tangent_motion['ok'],tangent_motion
    results['external_tangent_motion']=tangent_motion
    shallow=[[-.5,-.5,top-.0001],[.5,-.5,top-.0001],[0.,.5,top-.0001]]
    shallow_report=check_contacts(build_contact_context(source(shallow),[body]),shallow)
    assert not shallow_report['ok'] and shallow_report['minimum_signed_offset_cm']<-.00009,shallow_report
    results['shallow_penetration_still_refused']=shallow_report
    inverted=box(inward=True)
    inside=[[-.2,-.2,0.],[.2,-.2,0.],[0.,.2,0.]]
    invalid=check_contacts(build_contact_context(source(inside),[inverted]),inside)
    assert not invalid['ok'] and invalid['reason']=='COLLIDER_VOLUME_ORIENTATION',invalid
    results['inward_closed_body_refused']=invalid
    strict=build_contact_context(payload,[body],clearance_cm=.01)
    assert not check_contacts(strict,tangent)['ok']
    results['tangency_with_positive_reserve']='EXPECTED_REFUSAL'
    lower=[[-.5,-.5,-2.],[.5,-.5,-2.],[0.,.5,-2.]]
    upper=[[p[0],p[1],2.] for p in lower]
    context=build_contact_context(source(lower),[body])
    assert check_contacts(context,lower)['ok'] and check_contacts(context,upper)['ok']
    motion=check_motion(context,lower,upper,1,2,max_step_cm=.25,max_subdivisions=32)
    assert not motion['ok'] and motion['reason']=='SWEPT_VERTEX_CROSSING',motion
    results['between_frame_crossing']=motion
    budget=check_motion(context,lower,upper,1,2,max_step_cm=.01,max_subdivisions=4)
    assert not budget['ok'] and budget['reason']=='CONTACT_MOTION_UNDERSAMPLED',budget
    results['undersampled_motion']=budget
    slow=[[p[0]+.1,p[1],p[2]] for p in lower]
    clear=check_motion(context,lower,slow,1,2,max_step_cm=.05,max_subdivisions=32)
    assert clear['ok'] and clear['status']=='CONTACTS_CLEAR_DISCRETE',clear
    results['clear_discrete_motion']=clear
    body.location.x=.001;bpy.context.view_layer.update()
    changed=check_motion(context,lower,slow,1,2,max_step_cm=.05,max_subdivisions=32)
    assert not changed['ok'] and changed['reason']=='COLLIDER_GEOMETRY_CHANGED',changed
    results['moving_body_without_trajectory']=changed
    body.location.x=0.;bpy.context.view_layer.update()
    a=[[0.,0.,0.],[2.,0.,0.],[0.,2.,0.]]
    separated=a+[[p[0],p[1],.1] for p in a]
    layers=source(separated,[[0,1,2],[3,4,5]])
    close=precise_self_contacts(layers,separated,.15,clearance=.05)
    assert close['ok'],close
    results['close_separate_layers']=close
    assert not precise_self_contacts(layers,separated,.15,clearance=.2)['ok']
    coplanar=a+copy.deepcopy(a)
    overlap=precise_self_contacts(layers,coplanar,.15)
    assert not overlap['ok'] and overlap['contacts'][0]['kind']=='COPLANAR_OVERLAP',overlap
    results['coplanar_separate_layers']=overlap
    policy=copy.deepcopy(layers)
    policy_coords=copy.deepcopy(coplanar)+[[0.,0.,0.]]
    policy['rest_cm'].append([0.,0.,0.])
    for label,kind,pairs in [('far','permanent',[[0,4]]),('closure','closure',[[0,3]]),
                            ('detachable','detachable',[[0,3]]),
                            ('transitive','permanent',[[0,6],[6,3]])]:
        policy['seams']={'test':{'kind':kind,'pairs':pairs}}
        rejected=precise_self_contacts(policy,policy_coords,.15)
        assert not rejected['ok'],(label,rejected)
    policy['seams']={'test':{'kind':'permanent','pairs':[[0,3]]}}
    assert precise_self_contacts(policy,policy_coords,.15)['ok']
    results['seam_exclusion_policy']='DIRECT_SETTLED_PERMANENT_ONLY_ALL_FOUR_COUNTEREXAMPLES_REFUSED'
    # Relative self-motion: neither endpoint intersects, midpoint does.
    start=[[p[0],p[1],-1.] for p in a]+[[p[0],p[1],1.] for p in a]
    end=[[p[0],p[1],1.] for p in a]+[[p[0],p[1],-1.] for p in a]
    layer_context=build_contact_context(layers,[])
    trajectory=check_motion(layer_context,start,end,3,4,max_step_cm=.25,max_subdivisions=32)
    assert not trajectory['ok'] and trajectory['reason']=='INTERPOLATED_CONTACT',trajectory
    results['between_frame_layer_crossing']=trajectory
    from tests.native_pattern_collision import box_tree
    from blender.pattern_assembly import collision_check
    tree,snapshot=box_tree([(-9.,9.),(-1.8,1.8),(0.,32.)])
    corner=collision_check([[-11.991112947,2.400147037,1.7478e-8]],[tree],[snapshot],.4)
    assert corner['ok'] and corner['minimum_signed_offset_cm']>3.,corner
    results['prior_exterior_corner']=corner
    if '--benchmark' in sys.argv:
        size=100
        vertices=[[float(i),float(j),0.] for j in range(size+1) for i in range(size+1)]
        faces=[]
        for j in range(size):
            for i in range(size):
                k=j*(size+1)+i
                faces.extend([[k,k+1,k+size+2],[k,k+size+2,k+size+1]])
        big={'rest_cm':vertices,'faces':faces,'seams':{},
             'panels':{'sheet':{'indices':list(range(len(vertices))),'edges':{}}}}
        start=time.perf_counter()
        measured=precise_self_contacts(big,vertices,.15)
        elapsed=time.perf_counter()-start
        assert measured['ok'],measured
        results['twenty_thousand_faces_benchmark']={'seconds':elapsed,'vertices':len(vertices),
            'faces':len(faces),'broadphase_candidates':measured['broadphase_candidates'],
            'tested_pairs':measured['tested_pairs'],'status':'STATIC_COUPON_ONLY'}
    report={'status':'PASS','version':1,'blender_version':bpy.app.version_string,
            'cases':results,'simulation':'NOT_EXECUTED','qualification':'NONE'}
    atomic_json(output/'result.json',report)
    print('PASS precise static and bounded discrete contacts',flush=True)


if __name__=='__main__':main()
