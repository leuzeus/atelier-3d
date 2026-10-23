"""Source-bound auxiliary thorax/cervical split on an isolated real-03 copy.

The approved body, exact prepared garment, limits and original proxy are never
edited. The candidate is diagnostic, not activated or anatomically approved.
"""
import copy
import math
import os
from pathlib import Path
import shutil
import sys
import traceback

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))

import bpy

from a3d.core import atomic_json, digest, read_json, sha
from a3d.fitting_preparation import envelope_spec
from a3d.store import Project
from blender.cloth_contacts import build_contact_context, check_contacts
from blender.fitting_envelope import prepare_fitting_envelope
from blender.pattern_assembly import collision_check
from blender.sewing import mesh_digest, object_mesh
from tests.native_pattern_real import inventory
from tests import native_opensew_envelope_review as review


def measure(payload, coords, collider, plan):
    context = build_contact_context(payload, [collider],
        clearance_cm=plan['collision']['clearance_cm'],
        seam_tolerance_cm=plan['consolidation']['weld_gap_cm'],
        max_penetration_cm=0., check_self=False)
    result = check_contacts(context, coords)
    owner = {i: pid for pid, panel in payload['panels'].items() for i in panel['indices']}
    panel_faces = {pid: [] for pid in payload['panels']}
    for index, face in enumerate(payload['faces']):
        assert len({owner[i] for i in face}) == 1
        panel_faces[owner[face[0]]].append(index)
    per_piece = {}
    for pid, panel in payload['panels'].items():
        vertices, faces = panel['indices'], panel_faces[pid]
        samples = [coords[i] for i in vertices] + [
            [math.fsum(coords[i][k] for i in payload['faces'][face]) / 3 for k in range(3)]
            for face in faces]
        measured = collision_check(samples, [b['tree'] for b in context['bodies']],
            [b['snapshot'] for b in context['bodies']], plan['collision']['clearance_cm'],
            surface_triangles=[b['triangles'] for b in context['bodies']])
        worst = measured.get('worst')
        if worst:
            sample = worst['sample']
            if sample < len(vertices):
                index = vertices[sample]
                worst.update(vertex=index, source_uv_cm=payload['rest_cm'][index][:2], point_cm=coords[index])
            else:
                index = faces[sample - len(vertices)]
                worst.update(source_face=index, source_uv_cm=[payload['rest_cm'][i][:2] for i in payload['faces'][index]],
                             point_cm=samples[sample])
        per_piece[pid] = measured
    return {'body_contacts': result, 'per_piece_signed_samples': per_piece,
            'self_contacts': 'NOT_REEXECUTED_EXACT_UNCHANGED_GARMENT',
            'scope': 'STATIC_COMPARISON_FIXED_REAL03_PREFORM_AGAINST_ONE_AUXILIARY',
            'qualification': 'NONE'}


def main():
    out = Path(os.environ['A3D_VALIDATION_OUTPUT']).resolve()
    prior = ROOT / 'work/opensew-implementation-20261003/real-03'
    source_project = prior / 'project'
    assert out.drive.upper() == 'G:'
    before = inventory(source_project)
    atomic_json(out / 'source-project-before.json', before)
    original_record = read_json(prior / 'report.json')['native_preparation']
    original_master = source_project / original_record['master']['path']
    assert sha(original_master) == original_record['master']['sha256']
    project_path = out / 'project'
    shutil.copytree(source_project, project_path)
    project = Project(project_path)
    master = project_path / original_record['master']['path']
    session = read_json(project.data / 'blender/session.json')
    session.update(working=str(master), original=str(original_master), original_sha256=sha(original_master))
    atomic_json(project.data / 'blender/session.json', session)
    bpy.context.preferences.filepaths.temporary_directory = str(out / 'tmp')
    bpy.ops.wm.open_mainfile(filepath=str(master), load_ui=False, use_scripts=False)
    original_spec = read_json(project_path / 'r21-envelope.json')
    body = read_json(project_path / original_spec['body_receipt']['path'])
    source_blend = Path(body['source_blend'])
    source_hash = sha(source_blend)
    assert source_hash == body['source_sha256']
    payload = read_json(project_path / original_record['derived_mesh']['path'])
    assert sha(project_path / original_record['derived_mesh']['path']) == original_record['derived_mesh']['sha256']
    garment = bpy.data.objects[original_record['object']]
    reference = bpy.data.objects[body['reference_object']]
    old_proxy = bpy.data.objects[original_spec['object']]
    protected_objects = (garment, reference, old_proxy)
    geometry_before = {obj.name: mesh_digest(obj, evaluated=True) for obj in protected_objects}
    coords = payload['placed_cm']
    native_points, native_faces = object_mesh(garment)
    assert native_faces == payload['faces']
    native_error = max(math.dist([v * 100 for v in point], coord)
                       for point, coord in zip(native_points, coords, strict=True))
    assert native_error < 1e-4
    plan = read_json(project_path / original_record['assembly_plan']['path'])

    split = next(region for region in original_spec['regions'] if region['id'] == 'thorax-neck')
    assert not split['partition_bones']
    thorax = [name for name in split['source_meshes'] if name == 'V3_Thorax_Masked']
    cervical = [name for name in split['source_meshes'] if name.startswith('V3_Cervical_')]
    assert thorax and cervical and set(thorax + cervical) == set(split['source_meshes'])
    candidate_spec = copy.deepcopy(original_spec)
    candidate_spec['object'] = original_spec['object'] + '.ThoraxCervicalSplit.v001'
    candidate_spec['source_ref'] = ('Auxiliary hypothesis: split the retained thorax-neck source group into '
        'its existing thorax mesh and cervical meshes; same body, pose, padding, voxel and limits; '
        'no manual dimensions, projection or source geometry edits; anatomical suitability unqualified.')
    candidate_spec['regions'] = []
    for region in original_spec['regions']:
        candidate_spec['regions'].extend([
            {'id': 'thorax', 'source_meshes': thorax, 'partition_bones': []},
            {'id': 'cervical', 'source_meshes': cervical, 'partition_bones': []}]
            if region['id'] == 'thorax-neck' else [copy.deepcopy(region)])
    for key in ('voxel_cm', 'padding_cm', 'max_body_outside_cm', 'thickness_outer_cm', 'thickness_inner_cm'):
        assert candidate_spec[key] == original_spec[key]
    atomic_json(project_path / 'r21-envelope-original.json', original_spec)
    atomic_json(project_path / 'r21-envelope.json', candidate_spec)
    envelope_spec(project, 'r21-envelope.json')
    print('ENVELOPE_CANDIDATE_BUILD_BEGIN', flush=True)
    construction = prepare_fitting_envelope(str(project_path), 'r21-envelope.json')
    atomic_json(out / 'construction.json', construction)
    print('ENVELOPE_CANDIDATE_BUILD_COMPLETE', flush=True)
    artifact = project_path / construction['artifact']['path']
    assert sha(artifact) == construction['artifact']['sha256']
    with bpy.data.libraries.load(str(artifact), link=False) as (available, loaded):
        loaded.objects = [construction['object']]
    candidate = loaded.objects[0]
    bpy.context.scene.collection.objects.link(candidate)
    assert mesh_digest(candidate) == construction['geometry_sha256']
    print('ENVELOPE_ORIGINAL_CONTACT_BEGIN', flush=True)
    original_contacts = measure(payload, coords, old_proxy, plan)
    atomic_json(out / 'original-contacts.json', original_contacts)
    print('ENVELOPE_CANDIDATE_CONTACT_BEGIN', flush=True)
    candidate_contacts = measure(payload, coords, candidate, plan)
    atomic_json(out / 'candidate-contacts.json', candidate_contacts)
    print('ENVELOPE_CONTACT_COMPLETE', flush=True)
    assert geometry_before == {obj.name: mesh_digest(obj, evaluated=True) for obj in protected_objects}
    assert sha(source_blend) == source_hash

    # Only the disposable copied master gets display changes. Its active
    # recipe/receipts are not promoted to the new collider or READY status.
    allowed = {garment.name, candidate.name}
    for obj in bpy.context.view_layer.objects:
        obj.hide_render = obj.name not in allowed
        obj.hide_set(obj.name not in allowed)
        obj.select_set(obj is garment)
    bpy.context.view_layer.objects.active = garment
    candidate_master = project.data / 'blender/master-envelope-candidate-v001.blend'
    bpy.ops.wm.save_as_mainfile(filepath=str(candidate_master), copy=True, check_existing=False)
    candidate_record = copy.deepcopy(original_record)
    candidate_record['master'] = {'path': candidate_master.relative_to(project_path).as_posix(), 'sha256': sha(candidate_master)}
    # This small view manifest is only consumed by the render harness. It is
    # explicitly not a newly validated preparation receipt.
    atomic_json(out / 'report.json', {'native_preparation': candidate_record,
        'scope': 'DISPLAY_MANIFEST_EXACT_REAL03_GARMENT_NEW_AUXILIARY_NOT_A_PREPARATION_REVALIDATION',
        'accepted': False})
    argv = sys.argv
    try:
        sys.argv = [str(review.__file__), '--', str(out)]
        review.main()
    finally:
        sys.argv = argv
    render = read_json(out / 'result.json')
    atomic_json(out / 'render-evidence.json', render)
    after = inventory(source_project)
    atomic_json(out / 'source-project-after.json', after)
    assert before == after and sha(source_blend) == source_hash
    source_refs = {key: original_record[key] for key in ('master', 'derived_mesh', 'recipe', 'assembly_plan')}
    summary = {'status': 'AUXILIARY_CANDIDATE_MEASURED_NOT_QUALIFIED',
        'source_run': str(prior), 'source_refs': source_refs,
        'source_project_files_unchanged': len(before), 'original_r21_sha256': source_hash,
        'protected_geometry_sha256': geometry_before, 'exact_prefrom_native_float32_error_cm': native_error,
        'unchanged_preform_coordinates_sha256': digest(coords),
        'hypothesis': candidate_spec['source_ref'], 'construction': construction,
        'original_spec': {'path': 'project/r21-envelope-original.json', 'sha256': sha(project_path / 'r21-envelope-original.json')},
        'candidate_spec': {'path': 'project/r21-envelope.json', 'sha256': sha(project_path / 'r21-envelope.json')},
        'contacts': {'original': {'path': 'original-contacts.json', 'sha256': sha(out / 'original-contacts.json')},
                     'candidate': {'path': 'candidate-contacts.json', 'sha256': sha(out / 'candidate-contacts.json')}},
        'render_evidence': {'path': 'render-evidence.json', 'sha256': sha(out / 'render-evidence.json')},
        'master': candidate_record['master'], 'anatomical_validation': 'NOT_QUALIFIED',
        'fitting': 'NOT_QUALIFIED', 'visual_validation': 'PENDING_PIXEL_INSPECTION',
        'simulation': 'NOT_EXECUTED', 'activated_in_nominal_recipe': False, 'accepted': False, 'export_eligible': False}
    atomic_json(out / 'result.json', summary)
    print('ENVELOPE_CANDIDATE_RESULT=' + str(out / 'result.json'), flush=True)


if __name__ == '__main__':
    try:
        main()
    except Exception as exc:
        atomic_json(Path(os.environ['A3D_VALIDATION_OUTPUT']) / 'failure.json',
                    {'status': 'REFUSED_OR_EXECUTION_FAILURE', 'type': type(exc).__name__,
                     'error': str(exc), 'traceback': traceback.format_exc(), 'accepted': False})
        raise
