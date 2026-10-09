"""Apply a prepared rig only to a new derived body copy in the given collection."""
from a3d.core import StudioError, digest


def create_derived_rig(source, collection, specification):
    import bpy
    from mathutils import Vector
    if bpy.context.mode != 'OBJECT':
        raise StudioError('Derived rig preparation requires an object-mode working context')
    if source.type != 'MESH' or specification['status'] != 'RIG_PREPARED_NOT_QUALIFIED':
        raise StudioError('Derived rig requires a mesh and a prepared source-bound specification')
    if digest({key: value for key, value in specification.items() if key != 'cache_key'}) != specification['cache_key']:
        raise StudioError('Prepared rig specification changed after measurement')
    points = [[float(x)*100 for x in source.matrix_world@v.co] for v in source.data.vertices]
    faces = [list(p.vertices) for p in source.data.polygons]
    labels = [v.value for v in source.data.attributes['.sculpt_face_set'].data]
    if digest([points, faces, labels]) != specification['geometry_sha256']:
        raise StudioError('Prepared rig is stale for the native body topology or metric')
    if source.modifiers or source.vertex_groups or source.data.shape_keys:
        raise StudioError('Catalog rig preparation currently requires the declared unmodified base mesh')
    body = source.copy(); body.data = source.data.copy(); body.animation_data_clear()
    body.name = source.name+'.Working'; body.parent = None
    collection.objects.link(body)
    data = bpy.data.armatures.new(body.name+'.Rig')
    rig = bpy.data.objects.new(body.name+'.Rig', data); collection.objects.link(rig)
    rig_name = rig.name
    view_layer = bpy.context.view_layer
    previous = view_layer.objects.active
    if previous is not None and previous.name not in view_layer.objects:
        previous = None
    # A scene/view-layer context override may still report selected objects
    # from the visible window's original layer. They do not belong to this
    # temporary layer and must never be deselected or restored through it.
    selected = [obj for obj in bpy.context.selected_objects if obj.name in view_layer.objects]
    try:
        for obj in selected: obj.select_set(False, view_layer=view_layer)
        rig.select_set(True, view_layer=view_layer); view_layer.objects.active = rig
        # active_object can also retain the visible window's object under a
        # scene-only override. Mode operators must target this derived rig
        # explicitly; otherwise edit_bones may never be committed on it.
        with bpy.context.temp_override(active_object=rig, object=rig,
                selected_objects=[rig], selected_editable_objects=[rig]):
            bpy.ops.object.mode_set(mode='EDIT')
            for row in specification['bones']:
                bone = data.edit_bones.new(row['name'])
                bone.head = Vector(row['head_cm'])/100; bone.tail = Vector(row['tail_cm'])/100
                if row['parent']: bone.parent = data.edit_bones[row['parent']]
            bpy.ops.object.mode_set(mode='OBJECT')
        if set(bone.name for bone in data.bones) != {row['name'] for row in specification['bones']}:
            raise StudioError('Derived rig did not commit its exact declared native bone inventory')
        for row in specification['bones']:
            group = body.vertex_groups.new(name=row['name'])
            for i, weights in enumerate(specification['weights']):
                if row['name'] in weights: group.add([i], weights[row['name']], 'REPLACE')
        modifier = body.modifiers.new('A3D.DerivedRig', 'ARMATURE'); modifier.object = rig
        body['a3d_source_sha256'] = specification['source_sha256']
        body['a3d_rig_cache_key'] = specification['cache_key']
        body['a3d_rig_qualification'] = 'REST_AND_DEFORMATION_REQUIRE_VALIDATION'
        bpy.context.view_layer.update()
    except Exception:
        if rig.mode != 'OBJECT':
            with bpy.context.temp_override(active_object=rig, object=rig,
                    selected_objects=[rig], selected_editable_objects=[rig]):
                bpy.ops.object.mode_set(mode='OBJECT')
        bpy.data.objects.remove(body, do_unlink=True); bpy.data.objects.remove(rig, do_unlink=True)
        raise
    finally:
        remaining = bpy.data.objects.get(rig_name)
        if remaining is not None: remaining.select_set(False, view_layer=view_layer)
        for obj in selected:
            if obj.name in view_layer.objects: obj.select_set(True, view_layer=view_layer)
        view_layer.objects.active = previous
    return body, rig
