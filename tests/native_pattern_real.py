"""Replay pattern assembly on an isolated copy of the retained real garment.

Run only with scripts/run_pattern_validation.py. This is a product experiment,
not a claim that the garment passes: native refusals are retained and reported.
The connected Blender and every source/consumer file remain untouched.
"""
import copy
import json
import math
import os
from pathlib import Path
import shutil
import sys
import traceback

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))

import bpy
from mathutils import Vector

from a3d.core import StudioError, atomic_json, digest, read_json, sha
from a3d.pattern_assembly import map_digest, support_weights
from a3d.store import Project
from blender.operations import dispatch
from blender.sewing import context_colliders, mesh_digest, object_mesh, penetration_cm


SOURCE = ROOT / 'work/real-preparation-3191df401d734c81a5bfc43382f6bea5/project'
ENVELOPE_REPORT = SOURCE.parent / 'r21-envelope-result.json'
COMPONENT = 'garment.coat'
STAGES = ('migrate', 'preposition', 'mount', 'close', 'consolidate', 'relax', 'drape')
LEGACY_OPTIONS = ('experimental_prefit', 'interface_preparation', 'panel_mount',
                  'fitting_placement', 'contact_recovery', 'fitting_pose', 'fitting_tacks')


def inventory(directory):
    """Hash the complete static witness, not just its currently selected blend."""
    files = sorted(path for path in directory.rglob('*') if path.is_file())
    if any(path.is_symlink() for path in files):
        raise RuntimeError('The retained real witness must contain regular local files')
    return {path.relative_to(directory).as_posix(): sha(path) for path in files}


def simulation_object():
    selected = [obj for obj in bpy.data.objects if obj.type == 'MESH'
                and obj.get('a3d_component_id') == COMPONENT
                and obj.get('a3d_role') == 'simulation']
    if len(selected) != 1:
        raise RuntimeError('Expected exactly one current real simulation candidate')
    return selected[0]


def source_supports(payload, recipe):
    supports = {'temporary': [], 'drape': [], 'functional': []}
    reconstructed = {}
    for ordinal, pin in enumerate(recipe['pins']):
        # Existing neckline supports retain the garment under gravity. Wrist
        # supports are construction aids, not invented final body attachments.
        role = 'drape' if pin['piece'] == 'a13-collar' or pin['edge'] == 'neck' else 'temporary'
        item = {**pin, 'id': f'retained-{role}-{ordinal:02d}',
                'source_ref': 'retained exact recipe pin; neckline support for drape'
                if role == 'drape' else 'retained exact recipe pin; wrist construction aid released before drape'}
        supports[role].append(item)
        for index in payload['panels'][pin['piece']]['edges'][pin['edge']]:
            key = str(index)
            reconstructed[key] = max(reconstructed.get(key, 0.), pin['weight'])
    if reconstructed != payload['pins']:
        raise RuntimeError('Named source-edge supports do not reproduce every retained source weight')
    return supports


def make_plan(payload, current_cm, recipe):
    panels = {}
    for pid, panel in payload['panels'].items():
        indices = panel['indices']
        local = {index: ordinal for ordinal, index in enumerate(indices)}
        faces = [face for face in payload['faces'] if all(index in local for index in face)]
        panels[pid] = {
            'source_ref': 'retained real derived mesh; exact current placement, immutable source UV correspondence',
            'uv_cm': [list(payload['rest_cm'][index][:2]) for index in indices],
            'target_cm': [list(current_cm[index]) for index in indices],
            'triangles': [[local[index] for index in face] for face in faces],
        }
    return {
        'version': 1, 'component_id': COMPONENT,
        'source_refs': ['retained approved coat package and source mapping; historical free assembly is evidence only',
                        'R21 original body and existing geometric envelope; historical deep contact remains unqualified'],
        'mapping_sha256': map_digest(payload),
        'preform': {'panels': panels},
        'assembly': {'max_initial_gap_cm': recipe['limits']['max_seam_gap_cm'],
                     'max_displacement_cm': recipe['limits']['max_displacement_cm'],
                     'max_step_cm': .03, 'iterations': 600,
                     'neighborhood_rings': 2, 'closure_support_release': 1.},
        'consolidation': {'weld_gap_cm': recipe['limits']['weld_gap_cm']},
        'quality': {key: recipe['mesh'][key] for key in
                    ('min_angle_degrees', 'min_edge_cm', 'min_stretch', 'max_stretch')},
        'supports': source_supports(payload, recipe),
        'collision': {'required': True, 'mode': 'drape_only', 'clearance_cm': .02,
                      'source_ref': 'explicit free assembly/continuous relaxation, then unchanged R21 envelope at drape; no contact tolerance increase'},
        'cloth': {'mount_phase': 'mount', 'relax_phase': 'drape', 'drape_phase': 'drape',
                  'mount_release_steps': [0., .5, 1.]},
    }


def measured_contact(obj, recipe):
    positions = [[value * 100 for value in point] for point in object_mesh(obj)[0]]
    _, trees, snapshots = context_colliders(recipe)
    worst = None
    offenders = 0
    for index, point in enumerate(positions):
        p = Vector([value / 100 for value in point])
        deepest = 0.
        for tree, snapshot in zip(trees, snapshots, strict=True):
            hit, normal, face, _ = tree.find_nearest(p)
            if hit is None:
                continue
            depth = -(p - hit).dot(normal) * 100
            deepest = max(deepest, depth)
            if worst is None or depth > worst['depth_cm']:
                worst = {'index': index, 'depth_cm': depth, 'point_cm': point,
                         'collider': snapshot['object'], 'surface_face': face}
        offenders += deepest > recipe['limits']['max_penetration_cm']
    return {'status': 'READ_ONLY_CONTACT_DIAGNOSIS',
            'max_penetration_cm': penetration_cm(positions, trees),
            'limit_cm': recipe['limits']['max_penetration_cm'],
            'offending_vertices': offenders, 'worst': worst,
            'coverage': 'signed vertex samples, not exhaustive intersection proof',
            'simulation': 'NOT_EXECUTED', 'fitting': 'NOT_QUALIFIED'}


def render_review(output, obj, payload, envelope_name):
    """Render true Blender pixels; inspection is performed by the calling agent."""
    directory = output / 'renders'
    directory.mkdir(exist_ok=True)
    scene = bpy.context.scene
    scene.render.engine = 'CYCLES'
    scene.cycles.device = 'CPU'
    scene.cycles.samples = 12
    scene.cycles.use_denoising = True
    scene.render.resolution_x = 640
    scene.render.resolution_y = 800
    scene.render.resolution_percentage = 100
    scene.render.image_settings.file_format = 'PNG'
    scene.render.film_transparent = False
    scene.world = scene.world or bpy.data.worlds.new('PatternReview.World')
    scene.world.use_nodes = True
    scene.world.node_tree.nodes['Background'].inputs['Color'].default_value = (.055, .065, .08, 1.)
    scene.world.node_tree.nodes['Background'].inputs['Strength'].default_value = .55
    allowed = {obj.name, envelope_name}
    for other in scene.objects:
        if other.type in {'MESH', 'CURVE', 'FONT', 'META', 'VOLUME', 'LIGHT'}:
            other.hide_render = other.name not in allowed
    for name, color in ((obj.name, (.44, .49, .57)), (envelope_name, (.18, .11, .085))):
        target = bpy.data.objects.get(name)
        if target is None:
            continue
        target.hide_set(False)
        target.hide_viewport = False
        target.hide_render = False
        material = bpy.data.materials.new('PatternReview.' + name)
        material.diffuse_color = (*color, 1.)
        material.use_nodes = True
        bsdf = material.node_tree.nodes.get('Principled BSDF')
        bsdf.inputs['Base Color'].default_value = (*color, 1.)
        bsdf.inputs['Roughness'].default_value = .8
        target.data.materials.clear()
        target.data.materials.append(material)
    for name, location, power, size in (
            ('Key', (-3, -4, 4), 700, 4), ('Fill', (3, -1, 3), 450, 3),
            ('Rim', (1, 3, 3), 850, 3)):
        light_data = bpy.data.lights.new('PatternReview.' + name, 'AREA')
        light_data.energy = power
        light_data.shape = 'DISK'
        light_data.size = size
        light = bpy.data.objects.new(light_data.name, light_data)
        scene.collection.objects.link(light)
        light.location = location
        light.rotation_euler = (Vector((0, 0, 1)) - light.location).to_track_quat('-Z', 'Y').to_euler()
    camera_data = bpy.data.cameras.new('PatternReview.Camera')
    camera = bpy.data.objects.new(camera_data.name, camera_data)
    scene.collection.objects.link(camera)
    scene.camera = camera
    camera_data.type = 'ORTHO'
    vertices = [Vector(point) for point in object_mesh(obj)[0]]
    low = Vector(tuple(min(point[axis] for point in vertices) for axis in range(3)))
    high = Vector(tuple(max(point[axis] for point in vertices) for axis in range(3)))
    center = (low + high) / 2
    scale = max(high.z - low.z, (high.x - low.x) * 800 / 640) * 1.15
    views = [(name, angle, center, scale) for name, angle in
             [('front', 0.), ('side', math.pi / 2), ('back', math.pi), ('threequarter', .64)]]
    for side in ('l', 'r'):
        indices = sorted({index for sid, seam in payload['seams'].items()
                          if 'emmanchure' in sid and sid.endswith('-' + side)
                          for pair in seam['pairs'] for index in pair})
        if indices:
            local_center = sum((vertices[index] for index in indices), Vector()) / len(indices)
            views.append(('armhole-' + side, -.64 if side == 'l' else .64, local_center, .56))
    images = []
    for name, angle, target, extent in views:
        camera.location = target + Vector((4 * math.sin(angle), -4 * math.cos(angle), .12))
        camera.rotation_euler = (target - camera.location).to_track_quat('-Z', 'Y').to_euler()
        camera_data.ortho_scale = extent
        destination = directory / (name + '.png')
        scene.render.filepath = str(destination)
        bpy.ops.render.render(write_still=True)
        images.append({'view': name, 'path': str(destination), 'sha256': sha(destination)})
    master = output / 'master-pattern-real-v001.blend'
    bpy.ops.wm.save_as_mainfile(filepath=str(master), copy=True, check_existing=False)
    return {'views': images, 'master': {'path': str(master), 'sha256': sha(master)},
            'visual_validation': 'PIXELS_PRODUCED_NOT_YET_INSPECTED',
            'surface_finish': 'no thickness or subdivision on the simulation candidate',
            'accepted': False, 'export_eligible': False}


def run(output, report):
    project_root = output / 'project'
    shutil.copytree(SOURCE, project_root)
    project = Project(project_root)
    session = read_json(project.data / 'blender/session.json')
    source_working = Path(session['working']).resolve()
    if not source_working.is_relative_to(SOURCE.resolve()):
        raise RuntimeError('Retained working scene is outside the approved real witness')
    working = project_root / source_working.relative_to(SOURCE)
    original = output / 'fixture-original.blend'
    shutil.copyfile(working, original)
    session.update(original=str(original), original_sha256=sha(original), working=str(working))
    atomic_json(project.data / 'blender/session.json', session)
    bpy.ops.wm.open_mainfile(filepath=str(working), load_ui=False, use_scripts=False)
    bpy.context.preferences.filepaths.temporary_directory = str(output / 'tmp')
    bpy.context.preferences.filepaths.save_version = 0
    obj = simulation_object()
    source_mesh = mesh_digest(obj)
    source_mapping_path = obj['a3d_sewing_mesh']
    payload = read_json(project_root / source_mapping_path)
    initial = [[value * 100 for value in point] for point in object_mesh(obj)[0]]
    previous = read_json(project_root / obj['a3d_sewn_stage_result'])
    recipe = copy.deepcopy(read_json(project_root / previous['recipe_path']))
    retained = {key: copy.deepcopy(payload[key]) for key in ('rest_cm', 'faces', 'seams', 'pins')}
    plan = make_plan(payload, initial, recipe)
    initial_weights, initial_supports = support_weights(payload, plan, 'assembly', release=0.)
    report['source'] = {'project': str(SOURCE), 'object': obj.name,
                        'mapping': source_mapping_path, 'mapping_sha256': map_digest(payload),
                        'source_garment': payload['source_garment'],
                        'source_garment_sha256': payload['source_garment_sha256'],
                        'package_sha256': payload['package_sha256'], 'vertices': len(initial),
                        'historical_simulation': previous.get('simulation'),
                        'historical_purpose': previous.get('purpose'),
                        'historical_gap_cm': previous.get('final_gap_cm'),
                        'historical_result_reused_as_new_pass': False}
    report['supports'] = {'source_pins_preserved_in_witness': True,
                          'source_weights_classified_exactly': True,
                          'initial_effective_weights_equal_source': initial_weights == payload['pins'],
                          'initial_transition': initial_supports,
                          'classification': plan['supports'],
                          'functional_attachment_invented': False}
    removed = {key: recipe.pop(key) for key in LEGACY_OPTIONS if key in recipe}
    report['legacy_preparation_fields_retained_in_source'] = list(removed)
    proxy = read_json(ENVELOPE_REPORT)
    envelope_path = project_root / proxy['artifact']['path']
    if sha(envelope_path) != proxy['artifact']['sha256']:
        raise RuntimeError('Retained envelope artifact identity mismatch')
    fit = read_json(project_root / 'body-only-fit.json')
    fit['envelope'] = {'object': proxy['object'], 'role': 'proxy',
                       'geometry_sha256': proxy['geometry_sha256']}
    atomic_json(project_root / 'pattern-fit.json', fit)
    recipe['fitting_plan'] = {'path': 'pattern-fit.json', 'sha256': sha(project_root / 'pattern-fit.json')}
    recipe['colliders'] = [{**{key: proxy['collider'][key] for key in
                              ('object', 'geometry_sha256', 'dimensions_cm', 'outer_thickness_cm', 'inner_thickness_cm')},
                            'role': 'mannequin', 'tolerance_cm': .01}]
    recipe['no_collision_reason'] = ''
    atomic_json(project_root / 'pattern-recipe.json', recipe)
    atomic_json(project_root / 'pattern-assembly.json', plan)
    atomic_json(output / 'source-pattern-invariants.json', retained)
    report['context'] = dispatch(str(project_root), 'introduce_fitting_context', {
        'component_id': COMPONENT, 'recipe_path': 'pattern-recipe.json', 'fit_path': 'pattern-fit.json',
        'source_blend': proxy['artifact']['path'], 'source_sha256': proxy['artifact']['sha256']})
    if mesh_digest(obj) != source_mesh:
        raise RuntimeError('Native body-context introduction changed the retained garment')
    report['initial_contact'] = measured_contact(obj, recipe)
    report['recipe_limits'] = copy.deepcopy(recipe['limits'])
    report['plan'] = {'path': str(project_root / 'pattern-assembly.json'),
                      'sha256': sha(project_root / 'pattern-assembly.json')}
    report['stages'] = {}
    for stage in STAGES:
        arguments = {'component_id': COMPONENT, 'recipe_path': 'pattern-recipe.json',
                     'plan_path': 'pattern-assembly.json', 'stage': stage}
        try:
            result = dispatch(str(project_root), 'transition_pattern_assembly', arguments)
            if result.get('accepted') is not False or result.get('export_eligible') is not False:
                raise RuntimeError('Construction stage unexpectedly granted acceptance/export')
            report['stages'][stage] = {'status': 'EXECUTED', 'result': result}
            report['last_completed_stage'] = stage
        except StudioError as error:
            diagnostic = getattr(error, 'garment_diagnostic', None)
            failure = read_json(project_root / diagnostic['path']) if diagnostic else {}
            report['stages'][stage] = {'status': 'REFUSED', 'error': str(error),
                                       'diagnostic': diagnostic, 'cause': failure.get('cause', 'admission'),
                                       'simulation': failure.get('simulation', 'NOT_EXECUTED')}
            if project.state().get('pending_blender_operation'):
                report['stages'][stage]['recovery'] = dispatch(str(project_root), 'restore_checkpoint', {})
            for remaining in STAGES[STAGES.index(stage) + 1:]:
                report['stages'][remaining] = {'status': 'NOT_EXECUTED', 'reason': 'prior native stage refused'}
            report['status'] = 'REAL_CANDIDATE_REFUSED'
            break
        atomic_json(output / 'report.json', report)
    else:
        report['status'] = 'NATIVE_CHAIN_EXECUTED_NOT_ACCEPTED'
    obj = simulation_object()
    candidate = read_json(project_root / obj['a3d_sewing_mesh'])
    report['residual_contact'] = measured_contact(obj, recipe)
    report['source_map_unchanged_in_clone'] = digest(read_json(project_root / source_mapping_path)) == digest(payload)
    report['render_review'] = render_review(output, obj, candidate, proxy['object'])
    report['candidate'] = {'rest_mode': candidate.get('rest_mode', 'source_flat_2d'),
                           'source_metric_faces': len(candidate.get('source_rest_triangles_cm', [])),
                           'vertices': len(obj.data.vertices), 'mesh_sha256': mesh_digest(obj),
                           'current_mapping': obj['a3d_sewing_mesh']}


def main():
    output = Path(os.environ['A3D_VALIDATION_OUTPUT']).resolve(strict=True)
    if output.drive.upper() != 'G:' or output == SOURCE or output.is_relative_to(SOURCE):
        raise RuntimeError('A distinct G: validation output is required')
    if not (output / 'tmp').is_dir():
        raise RuntimeError('Use the isolated validation launcher with its G: temporary directory')
    before = inventory(SOURCE)
    external_before = sha(ENVELOPE_REPORT)
    report = {'experiment': 'isolated real PATTERN_SEWN native replay', 'status': 'RUNNING',
              'blender': bpy.app.version_string, 'source_mutations': False,
              'consumer_live_blender': 'UNTOUCHED', 'fixture_results_transferred': False,
              'fitting': 'NOT_QUALIFIED', 'behavior': 'NOT_QUALIFIED',
              'artistic_acceptance': 'NOT_GRANTED', 'export_eligible': False,
              'visual_validation': 'NOT_EXECUTED', 'accepted': False}
    error = None
    try:
        run(output, report)
    except Exception as exception:
        error = exception
        report.update(status='HARNESS_OR_INTEGRATION_ERROR', error=str(exception), traceback=traceback.format_exc())
    finally:
        after = inventory(SOURCE)
        unchanged = before == after and sha(ENVELOPE_REPORT) == external_before
        report['source_files_unchanged'] = unchanged
        report['source_file_count'] = len(before)
        atomic_json(output / 'source-manifest.json', {'root': str(SOURCE), 'sha256_by_path': before,
                                                     'unchanged': unchanged, 'envelope_report_sha256': external_before})
        atomic_json(output / 'report.json', report)
        print(json.dumps({'output': str(output), 'status': report['status'],
                          'last_completed_stage': report.get('last_completed_stage'),
                          'source_files_unchanged': unchanged}, indent=2), flush=True)
        if not unchanged:
            raise RuntimeError('A source witness file changed during the isolated validation')
    if error is not None:
        raise error


if __name__ == '__main__':
    main()
