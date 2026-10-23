"""Guarded viewport framing; no geometry, visibility, camera or file edits."""
import math

from a3d.core import StudioError


def frame_view(project_root, component_id, object_name):
    import bpy
    from blender.operations import working

    project, session = working(project_root)
    component = project.state()['components'][component_id]
    obj = bpy.data.objects.get(object_name)
    if obj is None or obj.type != 'MESH' or obj.get('a3d_component_id') != component_id:
        raise StudioError('Viewport target is not the requested component mesh')
    if bpy.context.mode != 'OBJECT':
        raise StudioError('Viewport framing requires Object Mode; do not change mesh mode implicitly')
    layer = bpy.context.view_layer
    if layer.objects.get(object_name) != obj or not obj.visible_get(view_layer=layer) or obj.hide_select:
        raise StudioError('Viewport target must already be visible and selectable in the current view layer')
    if str(obj.get('a3d_role', '')).startswith('archived'):
        raise StudioError('Viewport target is an archive, not the current candidate')
    if component['route']['selected'] == 'PATTERN_SEWN':
        if obj.get('a3d_package_sha256') != component['package']['sha256']:
            raise StudioError('Viewport target package identity mismatch')
    else:
        # Multiview assembly stores artifact identity on the component parent.
        expected = component.get('reconstruction', {}).get('artifact', {}).get('sha256')
        ancestor = obj
        matched = False
        while ancestor is not None and ancestor.get('a3d_component_id') == component_id:
            if expected and ancestor.get('a3d_source_sha256') == expected:
                matched = True
                break
            ancestor = ancestor.parent
        if not matched:
            raise StudioError('Viewport target reconstruction identity mismatch')
    window = bpy.context.window
    screen = window.screen if window else None
    area = next((a for a in screen.areas if a.type == 'VIEW_3D'), None) if screen else None
    region = next((r for r in area.regions if r.type == 'WINDOW'), None) if area else None
    space = area.spaces.active if area else None
    view = space.region_3d if space else None
    if not region or not view or space.region_quadviews or view.view_perspective == 'CAMERA' or view.lock_rotation:
        raise StudioError('Use a normal unlocked 3D viewport outside camera/quad view; no UI or camera is changed implicitly')
    if space.lock_object or space.lock_cursor or space.lock_camera:
        raise StudioError('Viewport framing refuses object/cursor/camera locks')
    selected = [o for o in layer.objects if o.select_get(view_layer=layer)]
    active = layer.objects.active
    smooth_view = bpy.context.preferences.view.smooth_view
    before = {'location': view.view_location.copy(), 'distance': view.view_distance,
              'rotation': view.view_rotation.copy(), 'perspective': view.view_perspective}
    try:
        bpy.context.preferences.view.smooth_view = 0
        for other in selected:
            other.select_set(False, view_layer=layer)
        obj.select_set(True, view_layer=layer)
        layer.objects.active = obj
        with bpy.context.temp_override(window=window, area=area, region=region):
            if not bpy.ops.view3d.view_selected.poll():
                raise StudioError('3D viewport framing unavailable in this Blender context')
            result = bpy.ops.view3d.view_selected(use_all_regions=False)
        if 'FINISHED' not in result or not math.isfinite(view.view_distance) or view.view_distance <= 0:
            raise StudioError('3D viewport framing did not complete')
        after = {'location': list(view.view_location), 'distance': view.view_distance}
    except BaseException:
        view.view_location = before['location']
        view.view_distance = before['distance']
        raise
    finally:
        bpy.context.preferences.view.smooth_view = smooth_view
        view.view_rotation = before['rotation']
        view.view_perspective = before['perspective']
        obj.select_set(False, view_layer=layer)
        for other in selected:
            other.select_set(True, view_layer=layer)
        layer.objects.active = active
        view.update()
        area.tag_redraw()
    return {'operation': 'frame_view', 'component_id': component_id, 'object': object_name,
            'working': session['working'], 'viewport': after, 'selection_restored': True,
            'visual_validation': 'NOT_EXECUTED',
            'next': 'Capture VIEW_3D pixels with get_screenshot_of_area_as_image and compare against original references. Framing is not visual acceptance.'}
