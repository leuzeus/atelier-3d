"""Render exact R21 source/envelope copies with identical upper-body cameras.

Run through run_pattern_validation.py in an isolated G: Blender process. This
is evidence collection only: no source geometry edits, simulation, scene save,
or automatic anatomical approval. The optional argument selects a real run.
"""
import os
from pathlib import Path
import sys

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))

import bpy
from mathutils import Vector

from a3d.core import atomic_json, digest, read_json, sha
from blender.sewing import mesh_digest, object_mesh


def main():
    out = Path(os.environ['A3D_VALIDATION_OUTPUT']).resolve()
    arguments = sys.argv[sys.argv.index('--') + 1:] if '--' in sys.argv else []
    prior = Path(arguments[0]).resolve() if arguments else ROOT / 'work/opensew-implementation-20261003/real-03'
    assert out.drive.upper() == 'G:' and prior.drive.upper() == 'G:'
    project = prior / 'project'
    report_path = prior / 'report.json'
    record = read_json(report_path)['native_preparation']
    envelope_path = project / 'r21-envelope.json'
    envelope = read_json(envelope_path)
    body_path = project / envelope['body_receipt']['path']
    assert sha(body_path) == envelope['body_receipt']['sha256']
    body = read_json(body_path)
    master = project / record['master']['path']
    assert sha(master) == record['master']['sha256']
    source = Path(body['source_blend'])
    assert sha(source) == body['source_sha256']
    protected = {str(path): sha(path) for path in (master, source, report_path, envelope_path, body_path)}
    bpy.context.preferences.filepaths.temporary_directory = str(out / 'tmp')
    bpy.ops.wm.open_mainfile(filepath=str(master), load_ui=False, use_scripts=False)
    original_scene = bpy.context.scene
    original_frame = original_scene.frame_current
    original_active = bpy.context.view_layer.objects.active
    selection = {obj.name: obj.select_get() for obj in bpy.context.view_layer.objects}
    inventories = {name: set(getattr(bpy.data, name).keys())
                   for name in ('objects', 'meshes', 'cameras', 'worlds', 'scenes')}
    reference = bpy.data.objects[body['reference_object']]
    proxy = bpy.data.objects[envelope['object']]
    geometry_before = {obj.name: mesh_digest(obj, evaluated=True) for obj in (reference, proxy)}
    geometry = {obj.name: object_mesh(obj, evaluated=True) for obj in (reference, proxy)}

    # Camera framing comes from the retained source rig, never from enlarging
    # or shrinking the proxy. It includes chest, neck and both shoulder heads.
    bones = body['bones']['RIG_Robe']
    shoulder_points = [Vector(bones['upper_arm.' + side]['head_cm']) / 100 for side in ('L', 'R')]
    chest = Vector(bones['chest']['head_cm']) / 100
    neck = Vector(bones['neck']['tail_cm']) / 100
    center = (chest + neck) / 2
    center.y = sum(point.y for point in shoulder_points) / 2
    scale = max(abs(shoulder_points[1].x - shoulder_points[0].x) * 1.4,
                abs(neck.z - chest.z) * 1.8, .1)
    review = bpy.data.scenes.new('A3D.EnvelopeComparison')
    owned_objects, owned_meshes = [], []
    camera_data = world = None
    images, cameras = {}, {}
    try:
        clones = {}
        for label, obj in (('source-r21', reference), ('envelope', proxy)):
            points, faces = geometry[obj.name]
            mesh = bpy.data.meshes.new('A3D.EnvelopeComparison.' + label)
            owned_meshes.append(mesh)
            mesh.from_pydata(points, [], faces)
            mesh.update()
            for polygon in mesh.polygons:
                polygon.use_smooth = True
            clone = bpy.data.objects.new(mesh.name, mesh)
            owned_objects.append(clone)
            review.collection.objects.link(clone)
            clone.color = (.62, .67, .72, 1.)
            clones[label] = clone
            assert len(clone.data.vertices) == len(points)
            assert [list(face.vertices) for face in clone.data.polygons] == faces
        camera_data = bpy.data.cameras.new('A3D.EnvelopeComparison.Camera')
        camera = bpy.data.objects.new(camera_data.name, camera_data)
        owned_objects.append(camera)
        review.collection.objects.link(camera)
        review.camera = camera
        camera_data.type = 'ORTHO'
        camera_data.ortho_scale = scale
        camera_data.clip_start = .001
        camera_data.clip_end = 100.
        review.render.engine = 'BLENDER_WORKBENCH'
        review.render.resolution_x = review.render.resolution_y = 1024
        review.render.resolution_percentage = 100
        review.render.image_settings.file_format = 'PNG'
        review.display.shading.light = 'STUDIO'
        review.display.shading.color_type = 'OBJECT'
        review.display.shading.show_shadows = True
        review.display.shading.show_cavity = True
        review.display.shading.background_type = 'WORLD'
        world = bpy.data.worlds.new('A3D.EnvelopeComparison.World')
        world.color = (.07, .07, .07)
        review.world = world
        directions = [('front', (0, -1, 0)), ('side', (1, 0, 0)),
                      ('back', (0, 1, 0)), ('threequarter', (1, -1, .18))]
        for view, direction in directions:
            camera.location = center + Vector(direction).normalized() * max(2., 3 * scale)
            camera.rotation_euler = (center - camera.location).to_track_quat('-Z', 'Y').to_euler()
            cameras[view] = {'location_m': list(camera.location),
                             'rotation_euler_radians': list(camera.rotation_euler),
                             'orthographic_scale_m': scale, 'focus_cm': list(center * 100)}
            for label, clone in clones.items():
                for name, other in clones.items():
                    other.hide_render = name != label
                path = out / (label + '-' + view + '.png')
                review.render.filepath = str(path)
                bpy.ops.render.render(write_still=True, scene=review.name)
                images[label + '-' + view] = {'path': str(path), 'sha256': sha(path),
                                               'camera': view, 'source_object': reference.name if label == 'source-r21' else proxy.name}
    finally:
        bpy.data.scenes.remove(review)
        for obj in owned_objects:
            bpy.data.objects.remove(obj, do_unlink=True)
        for mesh in owned_meshes:
            bpy.data.meshes.remove(mesh)
        if camera_data is not None:
            bpy.data.cameras.remove(camera_data)
        if world is not None:
            bpy.data.worlds.remove(world)

    protected_after = {path: sha(Path(path)) for path in protected}
    geometry_after = {obj.name: mesh_digest(obj, evaluated=True) for obj in (reference, proxy)}
    assert protected_after == protected
    assert geometry_after == geometry_before
    assert bpy.context.scene is original_scene and original_scene.frame_current == original_frame
    assert bpy.context.view_layer.objects.active is original_active
    assert selection == {obj.name: obj.select_get() for obj in bpy.context.view_layer.objects}
    assert inventories == {name: set(getattr(bpy.data, name).keys()) for name in inventories}
    result = {'status': 'RENDER_EVIDENCE_COLLECTED', 'source_run': str(prior),
              'protected_files_sha256_before': protected, 'protected_files_sha256_after': protected_after,
              'evaluated_geometry_sha256_before': geometry_before,
              'evaluated_geometry_sha256_after': geometry_after,
              'geometry': {name: {'vertices': len(points), 'faces': len(faces),
                                  'world_coordinates_and_connectivity_sha256': digest([points, faces])}
                           for name, (points, faces) in geometry.items()},
              'framing': 'SOURCE_RIG_CHEST_NECK_AND_SHOULDERS_IDENTICAL_CAMERAS',
              'display': 'EVALUATED_WORLD_GEOMETRY_COPIES_SMOOTH_SHADING_ONLY_NO_SUBDIVISION',
              'cameras': cameras, 'images': images, 'source_scene_restored': True,
              'anatomical_validation': 'NOT_QUALIFIED', 'visual_validation': 'PENDING_PIXEL_INSPECTION',
              'suitability': 'NOT_APPROVED', 'simulation': 'NOT_EXECUTED', 'accepted': False}
    atomic_json(out / 'result.json', result)
    print('ENVELOPE_REVIEW_RESULT=' + str(out / 'result.json'), flush=True)


if __name__ == '__main__':
    main()
