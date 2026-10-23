"""Read-only replay and regional diagnosis of one isolated real preparation.

Run through run_pattern_validation.py, passing the prior run directory. The
source master is opened only in that factory-background process and never saved.
Only the audit's copied torso-axis declaration may differ; no positions change.
"""
import copy
import math
import os
from pathlib import Path
import struct
import sys

ROOT=Path(__file__).resolve().parents[1]
sys.path.insert(0,str(ROOT))
import bpy
from a3d.core import StudioError,atomic_json,digest,inside,read_json,sha
from a3d.cloth_metrics import face_sources,validate_metrics
from a3d.dressing import source_references
from a3d.pattern_assembly import map_digest
from blender.cloth_contacts import build_contact_context,check_contacts,check_motion
from blender.dressing import audit_dressing
from blender.sewing import context_colliders,mesh_digest,object_mesh,rest_key_name,subset_mesh,placed_point


def regional_subset(payload,side):
    """Whole source triangles only; no cutting, new UV or simulation mesh."""
    pieces=['a13-collar']+[prefix+side for prefix in
        ('a06-center-','a04-front-','a05-back-','a05-side-',
         'a07-upper-','a07-under-','a08-upper-','a08-under-')]
    sub=subset_mesh(payload,pieces)
    binding=face_sources(sub)
    # Keep triangles touching the sourced upper torso band. Collar and arm
    # panels stay complete. The band is diagnostic selection, never a new cut.
    selected=[i for i,(pid,uv) in enumerate(zip(binding['source_face_pieces'],
        binding['source_rest_triangles_cm'],strict=True))
        if pid=='a13-collar' or pid.startswith(('a07-','a08-')) or max(p[1] for p in uv)>=100.]
    keep=sorted({v for i in selected for v in sub['faces'][i]})
    remap={old:new for new,old in enumerate(keep)}
    result=copy.deepcopy(sub)
    for key in ('rest_cm','placed_cm'):result[key]=[sub[key][i] for i in keep]
    result['faces']=[[remap[v] for v in sub['faces'][i]] for i in selected]
    result['source_face_indices']=[sub['source_face_indices'][i] for i in selected]
    result['source_vertex_indices']=[sub['source_vertex_indices'][i] for i in keep]
    for key in ('source_rest_triangles_cm','source_face_pieces','source_face_vertex_ids'):
        result[key]=[binding[key][i] for i in selected]
    prior_map=sub.get('source_vertex_map',{str(i):i for i in range(len(sub['rest_cm']))})
    result['source_vertex_map']={key:remap[current] for key,current in prior_map.items() if current in remap}
    if 'source_vertex_cohorts' in sub:
        result['source_vertex_cohorts']={str(remap[int(key)]):value for key,value in sub['source_vertex_cohorts'].items() if int(key) in remap}
    result['pins']={str(remap[int(key)]):value for key,value in sub['pins'].items() if int(key) in remap}
    result['seams']={}
    for sid,seam in sub['seams'].items():
        pairs=[[remap[a],remap[b]] for a,b in seam['pairs'] if a in remap and b in remap]
        if pairs:result['seams'][sid]={**seam,'pairs':pairs}
    for pid,panel in result['panels'].items():
        panel['indices']=[remap[i] for i in sub['panels'][pid]['indices'] if i in remap]
        panel['boundary']=[remap[i] for i in sub['panels'][pid]['boundary'] if i in remap]
        panel['edges']={key:[remap[i] for i in values if i in remap] for key,values in sub['panels'][pid]['edges'].items()}
    assert not face_sources(result)['binding_issues']
    for index,source in enumerate(result['source_face_indices']):
        assert [payload['placed_cm'][v] for v in payload['faces'][source]]==[result['placed_cm'][v] for v in result['faces'][index]]
    result['diagnostic_only']={'source_uv_torso_v_min_cm':100.,'selection':'WHOLE_TRIANGLES_TOUCHING_UPPER_BAND',
        'source_changed':False,'cut_changed':False,'admissible_for_simulation_or_assembly':False,
        'omitted_seams':sub['omitted_seams'],'other_half_and_lower_torso_contacts':'ONLY_IN_FULL_AUDIT'}
    return result


def measured_quality(payload,coords,limits):
    try:return {'status':'GEOMETRY_CHECKS_PASSED','metrics':validate_metrics(payload,coords,limits)}
    except StudioError as exc:
        return {'status':'REFUSED','error':str(exc),'metrics':getattr(exc,'quality_metrics',None),
                'violations':getattr(exc,'quality_violations',[]),'qualification':'NONE'}


def main():
    args=sys.argv[sys.argv.index('--')+1:]
    if len(args)!=1:raise ValueError('Pass exactly one completed preparation run directory')
    prior=Path(args[0]).resolve(strict=True);output=Path(os.environ['A3D_VALIDATION_OUTPUT']).resolve()
    if prior.drive.upper()!='G:' or output.drive.upper()!='G:' or output==prior:
        raise ValueError('Distinct G: source and audit directories required')
    project=prior/'project';main_report=read_json(prior/'report.json');native=main_report['native_preparation']
    verified={}
    def referenced(ref):
        path=inside(project,ref['path'])
        actual=sha(path)
        if actual!=ref['sha256']:raise StudioError('Source reference changed: '+ref['path'])
        verified[str(path)]=actual
        return path
    master=referenced(native['master']);receipt=read_json(referenced(native['receipt']))
    payload=read_json(referenced(native['derived_mesh']));plan=read_json(referenced(native['assembly_plan']))
    recipe=read_json(referenced(native['recipe']))
    expected_bends={pid for pid,frame in plan['preform']['panels'].items() if 'native_bend' in frame}
    measured_bends=set(native.get('preform',{}).get('native_backends',{}))
    if expected_bends-measured_bends:
        raise StudioError('Regional volume audit refuses source-placement fallback; native preform was not evaluated: '
                          +str(sorted(expected_bends-measured_bends)))
    for key in ('source_package','preparation_spec','construction_dossier','source_recipe'):
        referenced(native[key])
    for ref in source_references(plan):referenced(ref)
    source_path=inside(project,payload['source_garment']);data=read_json(source_path)
    assert digest(data)==payload['source_garment_sha256']==native['source_garment_sha256']
    verified[str(source_path)]=sha(source_path)
    assert map_digest(payload)==plan['mapping_sha256']
    assert digest(recipe)==native['recipe_sha256']
    bpy.ops.wm.open_mainfile(filepath=str(master),load_ui=False,use_scripts=False)
    obj=bpy.data.objects[native['object']]
    assert mesh_digest(obj)==native['mesh_sha256']==receipt['mesh_sha256']
    coords_m,faces=object_mesh(obj)
    assert faces==payload['faces']
    expected_float=lambda x:struct.unpack('f',struct.pack('f',x/100))[0]
    assert coords_m==[[expected_float(value) for value in point] for point in payload['placed_cm']]
    rest=obj.data.shape_keys.key_blocks[rest_key_name(payload)]
    assert [list(vertex.co) for vertex in rest.data]==[[expected_float(value) for value in point] for point in payload['rest_cm']]
    assert rest.value==0.
    assert object_mesh(obj,True)==(coords_m,faces)
    assert not any(modifier.type=='CLOTH' for modifier in obj.modifiers)
    coords=[[value*100 for value in point] for point in coords_m]
    native_rounding=max(math.dist(a,b) for a,b in zip(coords,payload['placed_cm'],strict=True))
    geometry_before=digest({'coords':payload['placed_cm'],'faces':faces,'rest':payload['rest_cm']})
    colliders,trees,snapshots=context_colliders(recipe)
    limits=copy.deepcopy(native['assessment']['effective_quality_limits'])
    common={'clearance_cm':plan['collision']['clearance_cm'],
            'seam_tolerance_cm':plan['consolidation']['weld_gap_cm']}
    context=build_contact_context(payload,colliders,**common)
    full_contact=check_contacts(context,coords)
    full_quality=measured_quality(payload,coords,limits)
    source_coords=[None]*len(coords)
    for pid,panel in payload['panels'].items():
        for index in panel['indices']:source_coords[index]=placed_point(payload['rest_cm'][index][:2],recipe['placements'][pid])
    def fixed_contact(points):
        assert points==coords
        return copy.deepcopy(full_contact)
    def dressing(candidate):
        return audit_dressing(payload,coords,candidate,colliders=colliders,project=project,
            source_coords_cm=source_coords,contact_check=fixed_contact,
            motion_check=lambda a,b,i,j:check_motion(context,a,b,i,j,
                max_step_cm=plan['assembly']['max_step_cm'],max_subdivisions=128))
    print('Full audit: exact reopened geometry, source metrics and contacts',flush=True)
    original=dressing(plan)
    envelope=read_json(project/'r21-envelope.json');body=read_json(referenced(envelope['body_receipt']))
    bones=body['bones']['RIG_Robe'];corrected=copy.deepcopy(plan)
    torso=next(region for region in corrected['dressing']['regions'] if region['id']=='torso')
    previous_axis={key:copy.deepcopy(torso[key]) for key in ('axis_start_cm','axis_end_cm')}
    torso.update(axis_start_cm=bones['pelvis']['head_cm'],axis_end_cm=bones['chest']['tail_cm'],source_ref=envelope['body_receipt'])
    declaration={'reason':'Keep the sourced pelvis/chest torso axis separate from the cervical axis',
        'source_ref':envelope['body_receipt'],'old_axis':previous_axis,
        'new_axis':{key:torso[key] for key in previous_axis},'geometry_changed':False,
        'original_plan_sha256':digest(plan),'audit_plan_sha256':digest(corrected),
        'scope':'AUDIT_ONLY_NOT_A_PREPARATION_OR_ASSEMBLY_TRANSITION'}
    amended=dressing(corrected)
    atomic_json(output/'audit-plan.json',corrected)
    atomic_json(output/'full-original-dressing.json',original)
    atomic_json(output/'full-audit-dressing.json',amended)
    atomic_json(output/'full-contact.json',full_contact)
    atomic_json(output/'full-quality.json',full_quality)
    regions={}
    for side in ('l','r'):
        print('Regional source-face audit '+side,flush=True)
        measured_payload=copy.deepcopy(payload);measured_payload['placed_cm']=coords
        local=regional_subset(measured_payload,side)
        quality=measured_quality(local,local['placed_cm'],limits)
        contact=check_contacts(build_contact_context(local,colliders,**common),local['placed_cm'])
        atomic_json(output/('region-'+side+'-mesh.json'),local)
        atomic_json(output/('region-'+side+'-quality.json'),quality)
        atomic_json(output/('region-'+side+'-contact.json'),contact)
        regions[side]={'panels':list(local['panels']),'vertices':len(local['rest_cm']),'faces':len(local['faces']),
            'quality_status':quality['status'],'violations':quality.get('violations',[]),
            'contacts_ok':contact['ok'],'contact_reason':contact.get('reason'),
            'minimum_signed_offset_cm':contact.get('minimum_signed_offset_cm'),
            'body_intersections':contact.get('contact_count'),'self_contact_count':contact.get('self_contact',{}).get('contact_count'),
            'source_face_indices_sha256':digest(local['source_face_indices']),
            'source_binding_issues':face_sources(local)['binding_issues'],
            'scope':local['diagnostic_only']}
    assert geometry_before==digest({'coords':payload['placed_cm'],'faces':payload['faces'],'rest':payload['rest_cm']})
    assert mesh_digest(obj)==native['mesh_sha256']
    assert context_colliders(recipe)[2]==snapshots
    assert all(sha(Path(path))==value for path,value in verified.items())
    report={'status':'AUDIT_COMPLETE','blender':bpy.app.version_string,
        'source_run':str(prior),'readiness':native['readiness'],'exact_reopen':True,
        'native_preform_panels':sorted(measured_bends),'source_placement_fallback':False,
        'evaluated_coordinate_source':'UNCHANGED_REOPENED_NATIVE_FLOAT32_STORAGE',
        'native_storage_rounding_max_cm':native_rounding,
        'source_refs_unchanged':True,'verified_refs':verified,'geometry_changed':False,
        'rest_key':rest.name,'source_metric_domain':'IMMUTABLE_SOURCE_2D_PER_FACE',
        'declaration_change':declaration,'full_original_dressing':original['status'],
        'full_amended_dressing':amended['status'],'full_quality':full_quality['status'],
        'full_contact_ok':full_contact['ok'],'minimum_signed_offset_cm':full_contact.get('minimum_signed_offset_cm'),
        'regions':regions,'simulation':'NOT_EXECUTED','fitting':'NOT_QUALIFIED','behavior':'NOT_QUALIFIED',
        'visual_validation':'NOT_EXECUTED','accepted':False,'export_eligible':False,
        'runtime_sha256':{name:sha(ROOT/name) for name in ('tests/native_opensew_regional_audit.py',
            'blender/cloth_contacts.py','a3d/contact_geometry.py','a3d/cloth_metrics.py','blender/dressing.py','blender/sewing.py')}}
    atomic_json(output/'result.json',report)
    print('AUDIT_COMPLETE; no Cloth, fitting or artistic qualification',flush=True)


if __name__=='__main__':main()
