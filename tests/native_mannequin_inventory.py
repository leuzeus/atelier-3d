"""Fresh Blender catalog rig/rest checks and neutral views; no production use."""
import math
from pathlib import Path
import sys
import bpy
from mathutils import Vector

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))
from a3d.core import atomic_json, digest, read_json, sha
from a3d.mannequins import catalog
from a3d.mannequin_rig import prepare_rig
from blender.mannequin_rig import create_derived_rig


def evaluated_points(body):
    evaluated = body.evaluated_get(bpy.context.evaluated_depsgraph_get()); mesh = evaluated.to_mesh()
    try:
        return [[float(x)*100 for x in evaluated.matrix_world@v.co] for v in mesh.vertices], [list(p.vertices) for p in mesh.polygons]
    finally: evaluated.to_mesh_clear()


def render_views(body, output, ident):
    scene = bpy.context.scene; scene.render.engine = 'BLENDER_EEVEE'
    scene.render.resolution_x = 512; scene.render.resolution_y = 640; scene.render.resolution_percentage = 100
    scene.world.color = (.3, .3, .3)
    material = bpy.data.materials.new('Neutral inspection'); material.diffuse_color = (.48, .48, .48, 1.)
    body.data.materials.clear(); body.data.materials.append(material)
    for polygon in body.data.polygons: polygon.use_smooth = True
    target = Vector((0., 0., .85)); lights = []
    for position, energy in [((3., -4., 4.), 800.), ((-3., 1., 3.), 600.)]:
        data = bpy.data.lights.new('Inspection area', 'AREA'); data.energy = energy; data.shape = 'DISK'; data.size = 3.
        light = bpy.data.objects.new(data.name, data); scene.collection.objects.link(light); light.location = position
        light.rotation_euler = (target-light.location).to_track_quat('-Z', 'Y').to_euler(); lights.append(light)
    camera_data = bpy.data.cameras.new('Inspection camera'); camera_data.type = 'ORTHO'; camera_data.ortho_scale = 1.95
    camera = bpy.data.objects.new(camera_data.name, camera_data); scene.collection.objects.link(camera); scene.camera = camera
    views = []
    for name, position in [('front', (0., -4., .85)), ('side', (4., 0., .85)),
                           ('back', (0., 4., .85)), ('three-quarter', (3., -3., .85))]:
        camera.location = position; camera.rotation_euler = (target-camera.location).to_track_quat('-Z', 'Y').to_euler()
        path = output/(ident+'.'+name+'.png'); scene.render.filepath = str(path); bpy.ops.render.render(write_still=True)
        views.append({'view': name, 'path': str(path), 'sha256': sha(path)})
    for obj in lights+[camera]: bpy.data.objects.remove(obj, do_unlink=True)
    return views


def run(output):
    output = Path(output); output.mkdir(parents=True, exist_ok=True)
    scene = bpy.context.scene
    for obj in list(scene.objects): bpy.data.objects.remove(obj, do_unlink=True)
    criteria = {'rest_max_error_cm': .0001, 'motion_max_displacement_cm': 30.,
                'finite_motion_required': True, 'topology_unchanged_required': True,
                'qualification': 'STRUCTURE_ONLY', 'visual_review': 'REQUIRED'}
    atomic_json(output/'criteria.json', criteria)
    reports = []
    for entry in catalog(ROOT)['entries']:
        source_path = ROOT/'assets/mannequins'/entry['file']; before = sha(source_path)
        with bpy.data.libraries.load(str(source_path), link=False) as (_, loaded): loaded.objects = list(entry['meshes'])
        assert len(loaded.objects) == 1
        source = loaded.objects[0]; collection = bpy.data.collections.new(entry['id']); scene.collection.children.link(collection)
        collection.objects.link(source); bpy.context.view_layer.update()
        points = [[float(x)*100 for x in source.matrix_world@v.co] for v in source.data.vertices]
        faces = [list(p.vertices) for p in source.data.polygons]
        labels = [value.value for value in source.data.attributes['.sculpt_face_set'].data]
        geometry = {'vertices_cm': points, 'faces': faces, 'face_sets': labels,
                    'source_sha256': before, 'pose_sha256': digest([points, faces])}
        atomic_json(output/(entry['id']+'.evaluated-geometry.json'), geometry)
        adapter = read_json(ROOT/'assets/mannequins'/entry['anatomy_adapter'])
        spec = prepare_rig(geometry, adapter, entry['orientation'])
        assert len(spec['weights']) == len(points)
        assert max(abs(sum(row.values())-1.) for row in spec['weights']) < 1e-9
        body, rig = create_derived_rig(source, collection, spec)
        rest, actual_faces = evaluated_points(body)
        rest_error = max(math.dist(a, b) for a, b in zip(points, rest))
        assert actual_faces == faces and len(rest) == len(points) and rest_error <= criteria['rest_max_error_cm']
        for side in ('left', 'right'):
            bone = rig.pose.bones['forearm.'+side]; bone.rotation_mode = 'XYZ'; bone.rotation_euler.x = .075
        bpy.context.view_layer.update(); moved, moved_faces = evaluated_points(body)
        motion = max(math.dist(a, b) for a, b in zip(rest, moved))
        assert .001 < motion <= criteria['motion_max_displacement_cm']
        assert moved_faces == faces and all(math.isfinite(x) for p in moved for x in p)
        for bone in rig.pose.bones: bone.rotation_euler = (0., 0., 0.)
        bpy.context.view_layer.update(); restored, _ = evaluated_points(body)
        assert max(math.dist(a, b) for a, b in zip(points, restored)) <= criteria['rest_max_error_cm']
        assert sha(source_path) == before
        source.hide_render = True; source.hide_set(True)
        views = render_views(body, output, entry['id'])
        working = output/(entry['id']+'.working-rig.blend')
        bpy.data.libraries.write(str(working), {body, rig}, fake_user=True)
        saved_names = [body.name, rig.name]
        for obj in (body, rig): bpy.data.objects.remove(obj, do_unlink=True)
        with bpy.data.libraries.load(str(working), link=False) as (_, loaded): loaded.objects = saved_names[:]
        for obj in loaded.objects: collection.objects.link(obj)
        bpy.context.view_layer.update()
        reopened_body = next(obj for obj in loaded.objects if obj.type == 'MESH')
        reopened, reopened_faces = evaluated_points(reopened_body)
        reopen_error = max(math.dist(a, b) for a, b in zip(points, reopened))
        assert len(reopened) == len(points) and reopened_faces == faces
        assert reopen_error <= criteria['rest_max_error_cm'] and sha(source_path) == before
        reports.append({'id': entry['id'], 'source_sha256': before, 'rig_cache_key': spec['cache_key'],
                        'bones': len(spec['bones']), 'vertices': len(points), 'faces': len(faces),
                        'rest_max_error_cm': rest_error, 'motion_max_displacement_cm': motion,
                        'reopen_max_error_cm': reopen_error,
                        'criteria_sha256': sha(output/'criteria.json'), 'views': views,
                        'working_variant': {'path': str(working), 'sha256': sha(working)},
                        'qualification': 'REST_AND_SHORT_MOTION_STRUCTURE_ONLY',
                        'deformation_quality': 'NOT_QUALIFIED', 'mensuration_controls': 'NOT_CREATED',
                        'collision_envelope': 'NOT_CREATED', 'fitting': 'NOT_EXECUTED'})
        for obj in list(collection.objects): bpy.data.objects.remove(obj, do_unlink=True)
        bpy.data.collections.remove(collection)
    atomic_json(output/'inventory.json', {'status': 'REST_AND_SHORT_MOTION_STRUCTURE_PASS',
        'assets': reports, 'blender_version': bpy.app.version_string, 'blender_hash': bpy.app.build_hash.decode(),
        'background': bpy.app.background, 'production_connection': False})


if __name__ == '__main__': run(sys.argv[sys.argv.index('--')+1])
