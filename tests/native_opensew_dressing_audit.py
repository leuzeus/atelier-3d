"""Recheck dressing only, reusing exact bound static contact/metric evidence.

Input is a completed native_opensew_regional_audit output directory. Opening
the exact master and checking hashes does not activate Cloth or alter a source.
Every reused artifact keeps its original execution epoch explicitly.
"""
import copy
import os
from pathlib import Path
import struct
import sys

ROOT=Path(__file__).resolve().parents[1];sys.path.insert(0,str(ROOT))
import bpy
from a3d.core import StudioError,atomic_json,digest,inside,read_json,sha
from a3d.dressing import source_references
from a3d.pattern_assembly import map_digest
from blender.dressing import audit_dressing
from blender.sewing import context_colliders,mesh_digest,object_mesh,rest_key_name


def main():
    arguments=sys.argv[sys.argv.index('--')+1:]
    if len(arguments)!=1:raise ValueError('Pass the completed regional native audit directory')
    prior=Path(arguments[0]).resolve(strict=True);output=Path(os.environ['A3D_VALIDATION_OUTPUT']).resolve()
    if prior.drive.upper()!='G:' or output.drive.upper()!='G:' or prior==output:
        raise ValueError('Distinct G: source evidence and output required')
    summary_file=prior/'result.json';previous=read_json(summary_file)
    assert previous['status']=='AUDIT_COMPLETE' and previous['exact_reopen'] and not previous['source_placement_fallback']
    assert previous['source_refs_unchanged'] and previous['geometry_changed'] is False
    verified={str(summary_file):sha(summary_file),**previous['verified_refs']}
    assert all(sha(Path(path))==value for path,value in verified.items())
    project=Path(previous['source_run'])/'project'
    def verified_ref(ref):
        path=inside(project,ref['path'])
        if sha(path)!=ref['sha256']:raise StudioError('Reused source changed: '+ref['path'])
        verified[str(path)]=ref['sha256']
        return path
    receipt_paths=[Path(path) for path in previous['verified_refs'] if Path(path).name=='receipt.json']
    master_paths=[Path(path) for path in previous['verified_refs'] if Path(path).name=='master-preparation-v001.blend']
    assert len(receipt_paths)==len(master_paths)==1
    native=read_json(receipt_paths[0]);master=master_paths[0]
    payload=read_json(verified_ref(native['derived_mesh']));recipe=read_json(verified_ref(native['recipe']))
    plan_file=prior/'audit-plan.json';plan=read_json(plan_file)
    assert digest(plan)==previous['declaration_change']['audit_plan_sha256']
    assert map_digest(payload)==plan['mapping_sha256'] and digest(recipe)==native['recipe_sha256']
    assert digest(read_json(inside(project,payload['source_garment'])))==payload['source_garment_sha256']
    for ref in source_references(plan):verified_ref(ref)
    assert not plan['dressing']['milestones'],'This replay covers a static dressing configuration only'
    files={name:prior/name for name in ('full-original-dressing.json','full-contact.json','full-quality.json','launch.json')}
    files['audit-plan.json']=plan_file
    for path in files.values():verified[str(path)]=sha(path)
    old_dressing=read_json(files['full-original-dressing.json']);contacts=read_json(files['full-contact.json'])
    quality=read_json(files['full-quality.json']);epoch=read_json(files['launch.json'])
    assert epoch['exit_code']==0 and epoch['code_changed_during_run']==[]
    assert quality['metrics']['limits']==native['assessment']['effective_quality_limits']
    assert contacts['clearance_cm']==plan['collision']['clearance_cm']
    assert contacts['self_contact']['declared_seam_adjacency_tolerance_cm']==plan['consolidation']['weld_gap_cm']
    bpy.ops.wm.open_mainfile(filepath=str(master),load_ui=False,use_scripts=False)
    obj=bpy.data.objects[native['object']]
    assert mesh_digest(obj)==native['mesh_sha256']
    positions,faces=object_mesh(obj);coords=[[value*100 for value in point] for point in positions]
    expected_float=lambda value:struct.unpack('f',struct.pack('f',value/100))[0]
    assert positions==[[expected_float(value) for value in point] for point in payload['placed_cm']]
    assert faces==payload['faces'] and object_mesh(obj,True)==(positions,faces)
    assert digest(coords)==old_dressing['coordinates_sha256']
    rest=obj.data.shape_keys.key_blocks[rest_key_name(payload)]
    assert [list(vertex.co) for vertex in rest.data]==[[expected_float(value) for value in point] for point in payload['rest_cm']]
    assert rest.value==0. and not any(modifier.type=='CLOTH' for modifier in obj.modifiers)
    colliders,trees,snapshots=context_colliders(recipe)
    reused={name:{'path':str(path),'sha256':verified[str(path)]} for name,path in files.items()}
    def fixed_contact(points):
        assert digest(points)==old_dressing['coordinates_sha256']
        result=copy.deepcopy(contacts)
        result['evidence_reuse']={'artifact':reused['full-contact.json'],'epoch':str(prior),
            'recomputed':False,'geometry_and_reserve_unchanged':True,
            'diagnostic_scope':'PRIOR_WORST_FACE_IS_GARMENT_FACE_COLLIDER_TRIANGLE_WAS_NOT_PRESERVED',
            'later_contact_change':'DIAGNOSTIC_COPY_AND_COLLIDER_FACE_LABELS_ONLY_NO_ADMISSION_ALGORITHM_CHANGE'}
        return result
    print('Exact native replay verified; rechecking only dressing section selection',flush=True)
    current=audit_dressing(payload,coords,plan,colliders=colliders,project=project,contact_check=fixed_contact)
    assert current['collider_geometry_sha256']==old_dressing['collider_geometry_sha256']
    assert digest(current['contact']['point_samples'])==digest(contacts['point_samples'])
    assert mesh_digest(obj)==native['mesh_sha256'] and context_colliders(recipe)[2]==snapshots
    assert all(sha(Path(path))==value for path,value in verified.items())
    atomic_json(output/'dressing.json',current)
    report={'status':'DRESSING_AUDIT_COMPLETE','blender':bpy.app.version_string,
        'source_run':previous['source_run'],'source_audit_epoch':str(prior),
        'current_epoch':str(output),'reused_artifacts':reused,
        'prior_runtime_sha256':previous['runtime_sha256'],
        'current_runtime_sha256':{name:sha(ROOT/name) for name in ('tests/native_opensew_dressing_audit.py',
            'blender/dressing.py','a3d/dressing.py','blender/cloth_contacts.py','a3d/contact_geometry.py','a3d/cloth_metrics.py')},
        'exact_native_geometry_rest_source_refs_unchanged':True,'geometry_changed':False,
        'contact_and_metrics_recomputed':False,'dressing_recomputed':True,
        'prior_dressing_status':old_dressing['status'],'current_dressing_status':current['status'],
        'problems':current['problems'],'openings':[{key:opening.get(key) for key in ('id','ok','reason','detail',
            'max_plane_offset_cm','minimum_passage_clearance_cm','required_clearance_cm','section_inside_opening')}
            for opening in current['openings']],
        'failed_exterior_panels':[row['piece'] for row in current['exterior'] if not row['ok']],
        'full_contact_ok':contacts['ok'],'minimum_signed_offset_cm':contacts['minimum_signed_offset_cm'],
        'contact_count_interpretation':'TRIANGLE_PAIR_CROSSING_OR_RESERVE_VIOLATIONS_NOT_DISTINCT_FACES; REGIONAL_COUNTS_OVERLAP_AT_COLLAR',
        'full_quality':quality['status'],'regional_previous_evidence':previous['regions'],
        'simulation':'NOT_EXECUTED','fitting':'NOT_QUALIFIED','behavior':'NOT_QUALIFIED',
        'visual_validation':'NOT_EXECUTED','accepted':False,'export_eligible':False}
    atomic_json(output/'result.json',report)
    print('DRESSING_AUDIT_COMPLETE; no Cloth or fitting qualification',flush=True)


if __name__=='__main__':main()
