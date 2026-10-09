"""Render every native clip frame in temporary scenes, then reload actual H264 media."""
import itertools
import time
import uuid

from a3d.core import StudioError, atomic_json, digest, inside, sha
from a3d.export_profiles import clip_tracks, motion_qualification
from a3d.review_motion import camera_plan, review_motion_descriptor, validate_movie_metadata


class ReviewStopped(StudioError):
    pass


def _deadline(deadline):
    if time.monotonic() > deadline:
        raise ReviewStopped('TIME_BUDGET')


def _corners(low, high):
    return [list(point) for point in itertools.product(*zip(low, high))]


def _capture(candidate, export, frame, vertex_limit):
    import bpy
    scene = candidate['scene']; scene.frame_set(frame)
    graph = bpy.context.evaluated_depsgraph_get(); graph.update()
    meshes = {}; corners = []; count = 0
    for name, obj in candidate['objects'].items():
        if obj.type != 'MESH':
            continue
        evaluated = obj.evaluated_get(graph); mesh = evaluated.to_mesh()
        try:
            count += len(mesh.vertices)
            if count > vertex_limit:
                raise ReviewStopped('SAMPLE_VERTEX_FRAME_BUDGET')
            points = [[float(v)*100*export['unit_scale_m'] for v in evaluated.matrix_world@vertex.co]
                      for vertex in mesh.vertices]
            faces = [list(face.vertices) for face in mesh.polygons]
            if not points or not faces:
                raise StudioError('Motion review requires every declared mesh to evaluate nonempty')
            low = [min(point[i] for point in points) for i in range(3)]
            high = [max(point[i] for point in points) for i in range(3)]
            corners.extend(_corners(low, high))
            meshes[name] = {'geometry_sha256': digest([points, faces]),
                            'topology_sha256': digest([len(points), faces]),
                            'vertex_count': len(points), 'face_count': len(faces), 'bounds_cm': [low, high]}
        finally:
            evaluated.to_mesh_clear()
    if not meshes:
        raise StudioError('Motion review has no native evaluated mesh')
    return {'time': frame, 'meshes': meshes}, corners, count


def _camera(candidate, plan, resolution, unit_scale):
    import bpy
    from mathutils import Vector
    scene = candidate['scene']; cm_to_native = 1/(100*unit_scale)
    data = bpy.data.cameras.new('A3D.MotionReview.Camera'); data.type = 'ORTHO'
    data.ortho_scale = plan['ortho_scale_cm']*cm_to_native
    data.clip_start = .001*cm_to_native
    data.clip_end = (plan['distance_cm']*3+max(plan['projected_extents_cm'])+1)*cm_to_native
    obj = bpy.data.objects.new('A3D.MotionReview.Camera', data); scene.collection.objects.link(obj); scene.camera = obj
    center = Vector(plan['center_cm'])*cm_to_native
    obj.location = center+Vector(plan['direction'])*plan['distance_cm']*cm_to_native
    obj.rotation_euler = (center-obj.location).to_track_quat('-Z', 'Y').to_euler()
    scene.render.resolution_x, scene.render.resolution_y = resolution
    scene.render.resolution_percentage = 100
    scene.view_layers[0].update()
    return obj


def _verify_camera(scene, camera, corners_cm, unit_scale):
    from bpy_extras.object_utils import world_to_camera_view
    from mathutils import Vector
    projected = [world_to_camera_view(scene, camera, Vector(point)/(100*unit_scale)) for point in corners_cm]
    if not projected or any(not (.01 <= p.x <= .99 and .01 <= p.y <= .99 and p.z > 0) for p in projected):
        raise StudioError('Motion review measured camera bounds crop the native clip')
    return {'minimum_x': min(p.x for p in projected), 'maximum_x': max(p.x for p in projected),
            'minimum_y': min(p.y for p in projected), 'maximum_y': max(p.y for p in projected),
            'verified_measured_clip_bbox_corners': len(projected)}


def _display(candidate, profile, camera_plan_cm, unit_scale):
    import bpy
    from mathutils import Vector
    scene = candidate['scene']; world = bpy.data.worlds.new('A3D.MotionReview.World'); scene.world = world
    world.color = (.08, .08, .08)
    if profile['display'] == 'NEUTRAL':
        scene.render.engine = 'BLENDER_WORKBENCH'
        shading = scene.display.shading; shading.light = 'STUDIO'; shading.color_type = 'SINGLE'
        shading.single_color = (.58, .63, .68); shading.show_cavity = True; shading.background_type = 'WORLD'
    else:
        scene.render.engine = 'BLENDER_EEVEE'
        for obj in list(scene.objects):
            if obj.type == 'LIGHT':
                light = obj.data; bpy.data.objects.remove(obj, do_unlink=True)
                if light.users == 0:
                    bpy.data.lights.remove(light)
        world.use_nodes = True
        background = world.node_tree.nodes.get('Background')
        if background is not None:
            background.inputs['Color'].default_value = (.12, .12, .12, 1.)
            background.inputs['Strength'].default_value = .35
        cm_to_native = 1/(100*unit_scale)
        center = Vector(camera_plan_cm['center_cm'])*cm_to_native
        distance = max(camera_plan_cm['ortho_scale_cm'], 50.)*cm_to_native
        for index, direction in enumerate(((1., -1., 1.5), (-1., -.5, .8), (0., 1., 1.))):
            light = bpy.data.lights.new('A3D.MotionReview.Light.'+str(index), 'AREA')
            light.energy = (1000., 650., 900.)[index]; light.shape = 'DISK'; light.size = distance
            obj = bpy.data.objects.new(light.name, light); scene.collection.objects.link(obj)
            obj.location = center+Vector(direction).normalized()*distance*2
            obj.rotation_euler = (center-obj.location).to_track_quat('-Z', 'Y').to_euler()
    if hasattr(scene.render.image_settings, 'media_type'):
        scene.render.image_settings.media_type = 'IMAGE'
    scene.render.image_settings.file_format = 'PNG'; scene.render.image_settings.color_mode = 'RGBA'
    scene.render.use_file_extension = True


def _configure_movie_output(render, codec_ffmpeg):
    """Select the native video domain before its dynamic FFmpeg format.

    Blender 5.2 separates IMAGE and VIDEO media. Its Video Editing factory
    template sets media_type first; querying static enum_items in IMAGE mode
    cannot establish whether the native build has a video encoder.
    """
    if codec_ffmpeg is not True:
        raise ReviewStopped('MOVIE_CODEC_UNAVAILABLE')
    try:
        if hasattr(render.image_settings, 'media_type'):
            render.image_settings.media_type = 'VIDEO'
        render.image_settings.file_format = 'FFMPEG'
        settings = render.ffmpeg
        if settings is None:
            raise AttributeError('FFmpeg settings are absent in this native build')
        settings.format = 'MPEG4'; settings.codec = 'H264'
        settings.audio_codec = 'NONE'; settings.constant_rate_factor = 'HIGH'
        if (render.image_settings.file_format != 'FFMPEG' or
                settings.format != 'MPEG4' or settings.codec != 'H264'):
            raise ValueError('The native encoder did not retain the requested format')
    except (TypeError, ValueError, AttributeError) as error:
        raise ReviewStopped('MOVIE_CODEC_UNAVAILABLE') from error


def _encode_movie(paths, destination, profile, deadline, progress):
    """Encode the saved PNG sequence with Blender, without rerunning source geometry."""
    import bpy
    _deadline(deadline)
    scene = bpy.data.scenes.new('A3D.MotionReview.Encode.'+uuid.uuid4().hex)
    scene.render.resolution_x, scene.render.resolution_y = profile['resolution']
    scene.render.resolution_percentage = 100; scene.render.fps = profile['fps']; scene.render.fps_base = 1.
    scene.frame_start = 1; scene.frame_end = len(paths)
    _configure_movie_output(scene.render, bpy.app.build_options.codec_ffmpeg)
    scene.render.filepath = str(destination); scene.render.use_file_extension = True
    scene.render.use_sequencer = True; editor = scene.sequence_editor_create()
    strips = getattr(editor, 'strips', None)
    if strips is None:
        strips = getattr(editor, 'sequences', None)
    if strips is None or not hasattr(strips, 'new_image'):
        raise ReviewStopped('NATIVE_IMAGE_SEQUENCE_ENCODER_UNAVAILABLE')
    strip = strips.new_image('A3D.ObservedReviewFrames', str(paths[0]), channel=1, frame_start=1)
    for path in paths[1:]:
        strip.elements.append(path.name)
    strip.frame_final_duration = len(paths)
    existing_files = set(destination.parent.iterdir())
    with bpy.context.temp_override(scene=scene, view_layer=scene.view_layers[0]):
        bpy.ops.render.render(animation=True, scene=scene.name)
    progress['rendered'] += len(paths)
    _deadline(deadline)
    outputs = [path for path in destination.parent.iterdir() if path not in existing_files and path.is_file()
               and path.suffix.lower() == '.mp4' and path.stem.startswith(destination.stem)]
    if len(outputs) != 1 or outputs[0].stat().st_size == 0:
        raise StudioError('Native H264 encoder did not produce the declared movie')
    actual_path = outputs[0]; movie = bpy.data.movieclips.load(str(actual_path), check_existing=False)
    verified = validate_movie_metadata(movie.frame_duration, movie.size, len(paths), profile['resolution'], movie.fps, profile['fps'])
    _deadline(deadline)
    return actual_path, verified


def render_motion_review(project_root, profile_path):
    import bpy
    from a3d.store import Project
    from blender.asset_export import (action_payloads, assign_clip, candidate_animation_owners,
                                      load_candidate, pack_candidate_images, rest_payload)
    from blender.body_source import data_ids, live_geometry
    project = Project(project_root); descriptor = review_motion_descriptor(project, profile_path)
    profile = descriptor['profile']; inputs = descriptor['export']; export = inputs['profile']
    original = data_ids(); live = live_geometry(); db_sha = sha(project.db)
    original_scene = bpy.context.scene; frame = original_scene.frame_current; filepath = bpy.data.filepath
    selected = set(bpy.context.selected_objects); active = bpy.context.view_layer.objects.active
    started = time.monotonic(); deadline = started+profile['budgets']['max_seconds']
    directory = project.data/('outputs/motion-review-'+uuid.uuid4().hex); directory.mkdir(parents=True, exist_ok=False)
    result = {'version': 1, 'profile': descriptor['profile_ref'], 'export_profile': profile['export_profile_ref'],
              'candidate': export['source_ref'], 'binding_sha256': descriptor['binding_sha256'],
              'display': profile['display'], 'qualification': 'PIXELS_ONLY', 'fitting': 'NOT_QUALIFIED',
              'artistic_review': 'REQUIRED', 'product_acceptance': 'NOT_GRANTED', 'fps': export['fps'],
              'schedule': descriptor['schedule'], 'clips': [], 'movies': [], 'images': [],
              'sampling_vertex_frame_limit': descriptor['max_sample_vertex_frames'], 'original_preserved': True,
              'source_frame_scope': 'EVERY_DECLARED_INTEGER_FRAME', 'continuous_motion': 'NOT_QUALIFIED'}
    progress = {'rendered': 0}; sampled_vertices = 0
    try:
        _deadline(deadline); candidate = load_candidate(inputs['source'], export, 'MotionReview')
        pack_candidate_images(project, candidate, export, inputs['source'])
        scene = candidate['scene']; owners = candidate_animation_owners(candidate['objects'])
        initial = {key: (owner.animation_data.action, owner.animation_data.action_slot) if owner.animation_data else (None, None)
                   for key, owner in owners.items()}
        def restore():
            for key, owner in owners.items():
                action, slot = initial[key]
                if owner.animation_data:
                    owner.animation_data.action = action
                    if action is not None and slot is not None:
                        owner.animation_data.action_slot = slot
        with bpy.context.temp_override(scene=scene, view_layer=scene.view_layers[0]):
            scene.frame_set(export['reference_frame']); rest = rest_payload(candidate); actions = action_payloads(candidate)
            action_hashes = {key: digest(value) for key, value in actions.items()}
            if any(action_hashes.get(name) != identity for name, identity in descriptor['expected_actions'].items()):
                raise StudioError('Motion review native Action changed from its canonical receipt')
            mesh_names = {name for name, obj in candidate['objects'].items() if obj.type == 'MESH'}
            qualification = motion_qualification(export, inputs['receipts'], action_hashes, mesh_names)
            if qualification['status'] != 'EXACT_CANDIDATE_CLIPS_VERIFIED':
                raise StudioError('Motion review native mesh inventory differs from complete source measurements')
            for clip in export['clips']:
                _deadline(deadline); assign_clip(candidate, clip); measurements = []; clip_corners = []; topology = None
                for current in range(clip['frame_start'], clip['frame_end']+1):
                    _deadline(deadline)
                    sample, corners, count = _capture(candidate, export, current,
                        descriptor['max_sample_vertex_frames']-sampled_vertices)
                    sampled_vertices += count; measurements.append(sample); clip_corners.extend(corners)
                    current_topology = {name: row['topology_sha256'] for name, row in sample['meshes'].items()}
                    if topology is not None and topology != current_topology:
                        raise StudioError('Motion review observed native topology or inventory changed across the clip')
                    topology = current_topology
                record = {'id': clip['id'], 'frame_start': clip['frame_start'], 'frame_end': clip['frame_end'],
                          'tracks': [dict(row) for row in clip_tracks(clip)],
                          'samples': measurements, 'views': []}
                result['clips'].append(record)
                for view in profile['views']:
                    _deadline(deadline); camera = camera_plan(clip_corners, view, profile['resolution'])
                    native_camera = _camera(candidate, camera, profile['resolution'], export['unit_scale_m'])
                    _display(candidate, profile, camera, export['unit_scale_m'])
                    projection = _verify_camera(scene, native_camera, clip_corners, export['unit_scale_m'])
                    frames_dir = directory/clip['id']/view; frames_dir.mkdir(parents=True, exist_ok=False); paths = []
                    for sample in measurements:
                        _deadline(deadline)
                        actual, _, count = _capture(candidate, export, sample['time'],
                            descriptor['max_sample_vertex_frames']-sampled_vertices)
                        sampled_vertices += count
                        if actual != sample:
                            raise StudioError('Motion review geometry changed between measured bounds and rendered frame')
                        path = frames_dir/('frame-'+str(sample['time']).zfill(6)+'.png'); scene.render.filepath = str(path)
                        bpy.ops.render.render(write_still=True, scene=scene.name); progress['rendered'] += 1
                        if not path.is_file():
                            raise StudioError('Native motion review did not produce every declared still')
                        image = bpy.data.images.load(str(path), check_existing=False)
                        if list(image.size) != profile['resolution']:
                            raise StudioError('Native review PNG dimensions differ from its profile')
                        result['images'].append({'clip_id': clip['id'], 'view': view, 'frame': sample['time'],
                            'path': path.relative_to(project.root).as_posix(), 'sha256': sha(path), 'size': list(image.size)})
                        paths.append(path); _deadline(deadline)
                    movie_path = directory/clip['id']/(view+'.mp4')
                    movie_path, movie = _encode_movie(paths, movie_path, profile, deadline, progress)
                    result['movies'].append(dict(movie, clip_id=clip['id'], view=view, fps=export['fps'],
                        path=movie_path.relative_to(project.root).as_posix(), sha256=sha(movie_path)))
                    record['views'].append({'id': view, 'camera': camera, 'projection': projection,
                                            'rendered_frames': [sample['time'] for sample in measurements]})
                restore(); scene.frame_set(export['reference_frame'])
            restore(); scene.frame_set(export['reference_frame'])
            if rest_payload(candidate) != rest or action_payloads(candidate) != actions:
                raise StudioError('Motion review changed copied rest/UV/material/Key state or native Actions')
        if progress['rendered'] != descriptor['schedule']['total_render_frames']:
            raise StudioError('Motion review did not render and encode every budgeted frame')
        result['status'] = 'REVIEW_MEDIA_RENDERED'
    except ReviewStopped as error:
        result.update(status='INCOMPLETE', stopped=str(error))
    finally:
        bpy.data.batch_remove(ids=data_ids()-original)
        if (data_ids() != original or live_geometry() != live or sha(project.db) != db_sha or
                bpy.context.scene != original_scene or original_scene.frame_current != frame or bpy.data.filepath != filepath or
                set(bpy.context.selected_objects) != selected or bpy.context.view_layer.objects.active != active):
            raise StudioError('Native motion review changed source scene or canonical state')
        for reference in descriptor['evidence']:
            if sha(inside(project.root, reference['path'])) != reference['sha256']:
                raise StudioError('Motion review source/profile/resource changed during rendering')
    result['rendered_frame_count'] = progress['rendered']; result['sampled_vertex_frames'] = sampled_vertices
    result['elapsed_seconds'] = time.monotonic()-started; result['blender_version'] = bpy.app.version_string
    result['cache_key'] = digest(result); path = directory/'receipt.json'; atomic_json(path, result)
    return dict(result, receipt={'path': path.relative_to(project.root).as_posix(), 'sha256': sha(path)})
