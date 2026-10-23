"""Native preparation review pixels, isolated from the simulation scene.

Display copies use the exact prepared geometry. Smooth shading and wireframe
are views, not geometric repair or physical/artist qualification.
"""
from a3d.core import sha


def save_preparation_master(project, obj, recipe, path):
    """Save an inspectable copy without changing the working scene's display.

    Rejected candidates remain separate from the active simulation. The master
    shows the candidate and declared body, while retaining all original data.
    """
    import bpy
    from mathutils import Vector
    if path.exists():
        raise RuntimeError('Preparation master cannot overwrite an existing version')
    allowed={obj.name}|{entry['object'] for entry in recipe.get('colliders',[])}
    layer=bpy.context.view_layer
    states=[(item,item.hide_get(),item.hide_render,item.select_get()) for item in layer.objects]
    active=layer.objects.active
    view_states=[]
    try:
        for item,_,_,_ in states:
            item.hide_set(item.name not in allowed)
            item.hide_render=item.name not in allowed
            item.select_set(item==obj)
        layer.objects.active=obj
        points=[obj.matrix_world@v.co for v in obj.data.vertices]
        lo=Vector([min(v[k] for v in points) for k in range(3)])
        hi=Vector([max(v[k] for v in points) for k in range(3)])
        if bpy.context.screen:
            for area in bpy.context.screen.areas:
                if area.type!='VIEW_3D':
                    continue
                space=area.spaces.active
                region=space.region_3d
                if region is None:
                    continue
                view_states.append((region,region.view_location.copy(),region.view_rotation.copy(),
                                    region.view_distance,region.view_perspective))
                region.view_location=(lo+hi)/2
                region.view_rotation=Vector((-1,1,-.2)).to_track_quat('-Z','Y')
                region.view_distance=max((hi-lo).length*1.3,.1)
                region.view_perspective='ORTHO'
        bpy.ops.wm.save_as_mainfile(filepath=str(path),copy=True,check_existing=False)
    finally:
        for item,hidden,render,selected in states:
            item.hide_set(hidden)
            item.hide_render=render
            item.select_set(selected)
        layer.objects.active=active
        for region,location,rotation,distance,perspective in view_states:
            region.view_location=location
            region.view_rotation=rotation
            region.view_distance=distance
            region.view_perspective=perspective
    return {'path':path.relative_to(project.root).as_posix(),'sha256':sha(path)}


def render_preparation(project, obj, payload, directory, recipe=None):
    import bpy
    from mathutils import Vector

    directory.mkdir(parents=True, exist_ok=True)
    review = bpy.data.scenes.new('A3D.PreparationReview')
    owned_objects, owned_meshes, owned_cameras = [], [], []
    render_obj = None

    def clone(source, color, name):
        # Evaluate only collider copies. The candidate must keep its exact
        # simulation vertices, with no postprocessing or Cloth evaluation.
        if source is obj:
            points = [list(source.matrix_world @ v.co) for v in source.data.vertices]
            faces = [list(p.vertices) for p in source.data.polygons]
        else:
            from blender.sewing import object_mesh
            points, faces = object_mesh(source, True)
        mesh = bpy.data.meshes.new(name)
        mesh.from_pydata(points, [], faces)
        mesh.update()
        owned_meshes.append(mesh)
        target = bpy.data.objects.new(name, mesh)
        review.collection.objects.link(target)
        owned_objects.append(target)
        target.color = color
        return target

    def camera_at(center, direction, scale):
        camera.location = center + Vector(direction).normalized() * max(2., scale * 3.)
        camera.rotation_euler = (center-camera.location).to_track_quat('-Z', 'Y').to_euler()
        camera.data.ortho_scale = scale

    images = {}
    try:
        render_obj = clone(obj, (.58, .63, .68, 1.), 'A3D.Review.Neutral')
        wire = clone(obj, (.025, .032, .04, 1.), 'A3D.Review.Wire')
        wire_mod = wire.modifiers.new('Display only: actual triangle edges', 'WIREFRAME')
        wire_mod.thickness = .00028
        wire_mod.use_replace = True
        wire_mod.use_boundary = True
        # Center the display ribbons across the surface: an outward-only
        # offset hides edges when inspecting the reverse side of a pattern.
        wire_mod.offset = 0.
        bodies = []
        for entry in (recipe or {}).get('colliders', []):
            source = bpy.data.objects.get(entry['object'])
            if source is not None and source.type == 'MESH':
                bodies.append(clone(source, (.38, .23, .16, 1.), 'A3D.Review.Collider'))
        camera_data = bpy.data.cameras.new('A3D.PreparationReview.Camera')
        owned_cameras.append(camera_data)
        camera = bpy.data.objects.new(camera_data.name, camera_data)
        owned_objects.append(camera)
        review.collection.objects.link(camera)
        review.camera = camera
        camera_data.type = 'ORTHO'
        camera_data.clip_start = .001
        camera_data.clip_end = 1000.
        review.render.engine = 'BLENDER_WORKBENCH'
        review.render.resolution_x = 720
        review.render.resolution_y = 840
        review.render.resolution_percentage = 100
        review.render.image_settings.file_format = 'PNG'
        review.display.shading.light = 'STUDIO'
        review.display.shading.color_type = 'OBJECT'
        review.display.shading.show_shadows = True
        review.display.shading.show_cavity = True
        review.display.shading.background_type = 'WORLD'
        review.world = bpy.data.worlds.new('A3D.PreparationReview.World')
        review.world.color = (.09, .09, .09)
        points = [v.co.copy() for v in render_obj.data.vertices]
        lo = Vector([min(v[k] for v in points) for k in range(3)])
        hi = Vector([max(v[k] for v in points) for k in range(3)])
        center = (lo + hi) / 2
        span = hi-lo
        scale = max(span.z, max(span.x, span.y)*840/720, .1)*1.18
        views = [('front', (0, -1, 0)), ('side', (1, 0, 0)),
                 ('back', (0, 1, 0)), ('threequarter', (1, -1, .25))]
        for style in ('neutral', 'wireframe'):
            wire.hide_render = style != 'wireframe'
            for polygon in render_obj.data.polygons:
                polygon.use_smooth = style == 'neutral'
            for label, direction in views:
                camera_at(center, direction, scale)
                path = directory / (style+'-'+label+'.png')
                review.render.filepath = str(path)
                bpy.ops.render.render(write_still=True, scene=review.name)
                images[style+'-'+label] = {'path': path.relative_to(project.root).as_posix(), 'sha256': sha(path)}

        # Locate closeups from source seam identities, never an old triangle ID.
        candidates = [(sid, seam) for sid, seam in payload['seams'].items()
                      if any(token in sid+' '+seam['piece_a']+' '+seam['piece_b']
                             for token in ('armhole', 'emmanchure', 'manche', 'sleeve'))]
        # Prefer explicit armholes to longitudinal sleeve seams. Otherwise a
        # second focus on the same arm can consume the opposite armhole view.
        candidates.sort(key=lambda item: not any(
            token in item[0].lower() for token in ('armhole', 'emmanchure')))
        if not candidates:
            candidates = list(payload['seams'].items())
        seen = []
        closeups = []
        for sid, seam in candidates:
            ids = sorted({i for pair in seam['pairs'] for i in pair})
            seam_points = [points[i] for i in ids]
            if not seam_points:
                continue
            focus = sum(seam_points, Vector())/len(seam_points)
            if any((focus-old).length < scale*.15 for old in seen):
                continue
            seen.append(focus)
            extent = max((p-focus).length for p in seam_points)*2.8
            closeups.append((sid, focus, max(.08, min(scale*.65, extent))))
            if len(closeups) == 2:
                break
        for ordinal, (sid, focus, extent) in enumerate(closeups, 1):
            for style in ('neutral', 'wireframe'):
                wire.hide_render = style != 'wireframe'
                for polygon in render_obj.data.polygons:
                    polygon.use_smooth = style == 'neutral'
                direction = (1 if focus.x >= center.x else -1, -1, .3)
                camera_at(focus, direction, extent)
                label = style+'-connection-'+str(ordinal)
                path = directory / (label+'.png')
                review.render.filepath = str(path)
                bpy.ops.render.render(write_still=True, scene=review.name)
                images[label] = {'path': path.relative_to(project.root).as_posix(),
                                 'sha256': sha(path), 'seam_id': sid,
                                 'focus_cm': [value*100 for value in focus]}
    finally:
        world = review.world
        bpy.data.scenes.remove(review)
        for item in owned_objects:
            bpy.data.objects.remove(item, do_unlink=True)
        for item in owned_meshes:
            bpy.data.meshes.remove(item)
        for item in owned_cameras:
            bpy.data.cameras.remove(item)
        if world is not None and world.users == 0:
            bpy.data.worlds.remove(world)
    return {'views': images,
            'geometry': 'EXACT_PREPARED_MESH_DISPLAY_COPIES',
            'neutral': 'SMOOTH_SHADING_ONLY_NO_SUBDIVISION',
            'wireframe': 'ACTUAL_TRIANGLE_EDGES_FLAT_SHADING',
            'visual_validation': 'NOT_EXECUTED', 'simulation': 'NOT_EXECUTED', 'accepted': False}
