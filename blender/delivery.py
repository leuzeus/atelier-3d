"""Native comparable review pixels in a temporary scene, preserving production."""
import time
import uuid
from a3d.core import StudioError, atomic_json, digest, sha


def render_asset_review(project_root, profile_path):
    import bpy
    from mathutils import Vector
    from a3d.delivery import delivery_profile
    from a3d.store import Project
    from blender.body_source import data_ids, live_geometry
    project = Project(project_root); profile, source = delivery_profile(project, profile_path)
    original = data_ids(); before = live_geometry(); original_frame = bpy.context.scene.frame_current
    directory = project.data/('outputs/review-'+uuid.uuid4().hex)
    directory.mkdir(parents=True, exist_ok=False)
    started = time.monotonic(); images = {}; stopped = None; candidate_geometry = {}
    try:
        with bpy.data.libraries.load(str(source), link=False) as (available, loaded):
            if not set(profile['object_names']) <= set(available.objects):
                raise StudioError('Review candidate objects are missing')
            loaded.objects = profile['object_names']
        selected = list(loaded.objects)
        added = data_ids()-original
        for block in added:
            animation = getattr(block, 'animation_data', None)
            if animation and animation.drivers:
                raise StudioError('Review requires driver-free evaluated candidate or a qualified motion receipt')
        review = bpy.data.scenes.new('A3D.AssetReview.'+uuid.uuid4().hex)
        review.unit_settings.system = 'METRIC'; review.unit_settings.scale_length = 1.
        for obj in selected: review.collection.objects.link(obj)
        review.frame_set(profile['frame'])
        with bpy.context.temp_override(scene=review, view_layer=review.view_layers[0]):
            depsgraph = bpy.context.evaluated_depsgraph_get(); depsgraph.update()
            display = []
            for obj in selected:
                if obj.type != 'MESH': continue
                evaluated = obj.evaluated_get(depsgraph); mesh = evaluated.to_mesh()
                try:
                    points = [list(evaluated.matrix_world@v.co) for v in mesh.vertices]
                    faces = [list(p.vertices) for p in mesh.polygons]
                finally: evaluated.to_mesh_clear()
                candidate_geometry[obj.name] = {'vertices_m': points, 'faces': faces}
                output_mesh = bpy.data.meshes.new('A3D.ReviewMesh'); output_mesh.from_pydata(points, [], faces); output_mesh.update()
                clone = bpy.data.objects.new('A3D.ReviewMesh', output_mesh)
                clone.color = (.58, .63, .68, 1.); review.collection.objects.link(clone); display.append(clone)
                obj.hide_render = True
            points = [Vector(point) for row in candidate_geometry.values() for point in row['vertices_m']]
            if not points: raise StudioError('Review candidate has no evaluated mesh')
            low = Vector([min(p[i] for p in points) for i in range(3)])
            high = Vector([max(p[i] for p in points) for i in range(3)])
            center = (low+high)/2; span = high-low
            w, h = profile['resolution']; scale = max(span.z, span.x*h/w, span.y*h/w, .1)*1.18
            camera_data = bpy.data.cameras.new('A3D.ReviewCamera'); camera_data.type = 'ORTHO'; camera_data.ortho_scale = scale
            camera_data.clip_start = .001; camera_data.clip_end = 1000.
            camera = bpy.data.objects.new('A3D.ReviewCamera', camera_data); review.collection.objects.link(camera); review.camera = camera
            review.render.engine = 'BLENDER_WORKBENCH'; review.render.resolution_x = w; review.render.resolution_y = h
            review.render.resolution_percentage = 100; review.render.image_settings.file_format = 'PNG'
            review.display.shading.light = 'STUDIO'; review.display.shading.color_type = 'OBJECT'
            review.display.shading.show_cavity = True; review.display.shading.background_type = 'WORLD'
            world = bpy.data.worlds.new('A3D.ReviewWorld'); review.world = world; world.color = (.09, .09, .09)
            for view in profile['views']:
                if time.monotonic()-started > profile['max_seconds']:
                    stopped = 'TIME_BUDGET'; break
                direction = {'front':(0,-1,0), 'side':(1,0,0), 'back':(0,1,0), 'threequarter':(1,-1,.25)}[view]
                camera.location = center+Vector(direction).normalized()*max(2., scale*3.)
                camera.rotation_euler = (center-camera.location).to_track_quat('-Z','Y').to_euler()
                path = directory/(view+'.png'); review.render.filepath = str(path)
                bpy.ops.render.render(write_still=True, scene=review.name)
                images[view] = {'path':path.relative_to(project.root).as_posix(), 'sha256':sha(path)}
                if time.monotonic()-started > profile['max_seconds']:
                    stopped = 'TIME_BUDGET'; break
    finally:
        bpy.data.batch_remove(ids=data_ids()-original)
    if data_ids() != original or live_geometry() != before or bpy.context.scene.frame_current != original_frame:
        raise StudioError('Asset review changed production scene')
    if sha(source) != profile['source_ref']['sha256']: raise StudioError('Review source changed while rendering')
    record = {'version':1, 'status':'REVIEW_RENDERED' if stopped is None else 'INCOMPLETE',
              'candidate':profile['source_ref'], 'profile':{'path':profile_path,'sha256':sha(project.root/profile_path)},
              'geometry_sha256':digest(candidate_geometry), 'images':images, 'elapsed_seconds':time.monotonic()-started,
              'stopped':stopped, 'display':'NEUTRAL_EVALUATED_GEOMETRY', 'original_preserved':True,
              'artistic_review':'NOT_EXECUTED', 'fitting':'NOT_QUALIFIED', 'qualification':'REVIEW_ARTIFACTS_ONLY'}
    path = directory/'receipt.json'; atomic_json(path, record)
    return dict(record, receipt={'path':path.relative_to(project.root).as_posix(),'sha256':sha(path)})
