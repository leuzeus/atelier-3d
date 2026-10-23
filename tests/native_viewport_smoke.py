"""Isolated native viewport framing regression; never connects to consumer Blender.

Run in Blender --factory-startup --python this_file (GUI for viewport pixels).
All inputs are synthetic; image quality is not an asset acceptance.
"""
import json
import sys
import uuid
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))
import bpy
from mathutils import Quaternion, Vector
from a3d.core import StudioError, atomic_json, read_json, sha
from a3d.packages import extract_package
from a3d.tools import blender_operation
from blender.sewing import mesh_digest
from tests.support import ready_project


def main():
    root = ROOT / ('work/native-viewport-' + uuid.uuid4().hex)
    root.mkdir()
    bpy.context.preferences.filepaths.temporary_directory = str(root)
    bpy.context.preferences.filepaths.save_version = 0
    project = ready_project(root / 'project', True)


    def execute(operation, arguments):
        namespace = {}
        exec(blender_operation(str(project.root), operation, arguments)['code'], namespace)
        return namespace['result']


    try:
        bpy.data.objects['Cube'].location.x = 5
        bpy.ops.wm.save_as_mainfile(filepath=str(root / 'original.blend'))
        original_sha = sha(root / 'original.blend')
        session = execute('prepare', {})
        package = project.state()['components']['garment.coat']['package']
        extracted = project.data / 'reconstruction/garment.coat'
        extract_package(project.root / package['path'], extracted)
        recipe = read_json(ROOT / 'templates/sewing-recipe.json')
        atomic_json(project.root / 'recipe.json', recipe)
        receipt = execute('garment', {'package_dir': extracted.relative_to(project.root).as_posix(), 'recipe_path': 'recipe.json'})
        target = next(o for o in bpy.data.objects if o.get('a3d_component_id') == 'garment.coat')
        cube = bpy.data.objects['Cube']
        bpy.context.view_layer.objects.active = cube
        for o in bpy.context.view_layer.objects: o.select_set(o == cube)
        bpy.context.scene.frame_set(1)
        area = next(a for a in bpy.context.screen.areas if a.type == 'VIEW_3D')
        space = area.spaces.active
        view = space.region_3d
        view.view_perspective = 'ORTHO'
        view.view_rotation = Quaternion((1, 0, 0), 1.5707963267948966)
        view.view_distance = 100
        view.view_location = Vector((0, 0, 0))
        working_sha = sha(session['working'])
        db_sha = sha(project.db)
        selected = sorted(o.name for o in bpy.context.selected_objects)
        active = bpy.context.view_layer.objects.active
        geometry = {o.name: mesh_digest(o) for o in bpy.data.objects if o.type == 'MESH'}
        transforms = {o.name: [list(r) for r in o.matrix_world] for o in bpy.data.objects}
        before_files = {p.relative_to(project.root).as_posix(): sha(p) for p in project.root.rglob('*') if p.is_file()}
        args = {'component_id': 'garment.coat', 'object_name': target.name}
        results = []
        for perspective in ('ORTHO', 'PERSP'):
            view.view_perspective = perspective
            rotation = list(view.view_rotation)
            view.view_distance = 100
            results.append(execute('frame_view', args))
            assert 0 < view.view_distance < 10, view.view_distance
            assert view.view_perspective == perspective and list(view.view_rotation) == rotation
            assert selected == sorted(o.name for o in bpy.context.selected_objects)
            assert bpy.context.view_layer.objects.active == active
        assert geometry == {o.name: mesh_digest(o) for o in bpy.data.objects if o.type == 'MESH'}
        assert transforms == {o.name: [list(r) for r in o.matrix_world] for o in bpy.data.objects}
        assert before_files == {p.relative_to(project.root).as_posix(): sha(p) for p in project.root.rglob('*') if p.is_file()}
        # Failure cases must leave viewport, selection and canonical state intact.
        def rejected(arguments=args, contains=None):
            before = (list(view.view_location), view.view_distance, list(view.view_rotation), view.view_perspective)
            try: execute('frame_view', arguments)
            except Exception as error:
                assert type(error).__name__ == 'StudioError', repr(error)
                if contains: assert contains in str(error), str(error)
            else: raise AssertionError('Foreign/unsupported target admitted')
            assert before == (list(view.view_location), view.view_distance, list(view.view_rotation), view.view_perspective)
            assert selected == sorted(o.name for o in bpy.context.selected_objects)
            assert bpy.context.view_layer.objects.active == active
        rejected({**args, 'object_name': 'Cube'}, 'requested component')
        rejected({**args, 'object_name': 'absent'}, 'requested component')
        target['a3d_package_sha256'] = '0' * 64
        rejected(contains='package identity')
        target['a3d_package_sha256'] = package['sha256']
        target.hide_set(True); rejected(contains='visible'); target.hide_set(False)
        target.hide_select = True; rejected(contains='selectable'); target.hide_select = False
        target['a3d_role'] = 'archived-simulation'; rejected(contains='archive'); target['a3d_role'] = 'simulation'
        view.view_perspective = 'CAMERA'; rejected(contains='camera/quad'); view.view_perspective = 'PERSP'
        space.lock_camera = True; rejected(contains='locks'); space.lock_camera = False
        bpy.context.view_layer.objects.active = cube
        bpy.ops.object.mode_set(mode='EDIT'); rejected(contains='Object Mode'); bpy.ops.object.mode_set(mode='OBJECT')
        assert geometry == {o.name: mesh_digest(o) for o in bpy.data.objects if o.type == 'MESH'}
        assert transforms == {o.name: [list(r) for r in o.matrix_world] for o in bpy.data.objects}
        view.view_perspective = 'ORTHO'; view.view_rotation = Quaternion((1, 0, 0), 1.5707963267948966)
        execute('frame_view', args)
        assert geometry == {o.name: mesh_digest(o) for o in bpy.data.objects if o.type == 'MESH'}
        assert transforms == {o.name: [list(r) for r in o.matrix_world] for o in bpy.data.objects}
        assert sha(session['working']) == working_sha and sha(root / 'original.blend') == original_sha
        assert sha(project.db) == db_sha and not project.state().get('pending_blender_operation')
        assert before_files == {p.relative_to(project.root).as_posix(): sha(p) for p in project.root.rglob('*') if p.is_file()}
        pixels = 'NOT_EXECUTED'
        if not bpy.app.background:
            bpy.context.scene.render.resolution_x = 640; bpy.context.scene.render.resolution_y = 640
            bpy.context.scene.render.resolution_percentage = 100
            bpy.context.scene.render.filepath = str(root / 'framed.png')
            region = next(r for r in area.regions if r.type == 'WINDOW')
            with bpy.context.temp_override(window=bpy.context.window, area=area, region=region):
                bpy.ops.wm.redraw_timer(type='DRAW_WIN_SWAP', iterations=2)
                bpy.ops.screen.screenshot(filepath=str(root / 'window.png'))
                bpy.ops.render.opengl(write_still=True, view_context=True)
            assert (root / 'framed.png').is_file()
            pixels = 'PASS: synthetic viewport capture'
        foreign = root / 'foreign.blend'
        bpy.ops.wm.save_as_mainfile(filepath=str(foreign))
        rejected(contains="working copy")
        assert sha(session['working']) == working_sha and sha(project.db) == db_sha
        atomic_json(root / 'result.json', {'status': 'PASS', 'blender': bpy.app.version_string,
            'framing': results, 'negative_cases': 'PASS', 'geometry_transforms_selection_sources_state': 'PASS',
            'viewport_pixels': pixels, 'consumer_scene': 'UNTOUCHED', 'visual_acceptance': 'NOT_EXECUTED'})
        print('A3D_VIEWPORT_PROOF=' + str(root / 'result.json'), flush=True)
    except BaseException as error:
        atomic_json(root / 'result.json', {'status': 'FAIL', 'error': repr(error)})
        raise
    finally:
        if not bpy.app.background: bpy.ops.wm.quit_blender()

if bpy.app.background:
    main()
else:
    # Allow the UI to initialize before capturing viewport pixels.
    bpy.app.timers.register(main, first_interval=1.)
