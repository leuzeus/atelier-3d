"""Source-bound preforms evaluated by native Blender geometry modifiers.

Bend runs in an isolated temporary scene through the dependency graph. No
operators, selection changes, source mesh edits, Cloth simulation or saves are
needed. The pure assembly module retains all placement and strain gates.
"""
import math

from a3d.core import StudioError, digest
from a3d.pattern_assembly import preform_coordinates as _source_preform_coordinates


def _bend_panel(payload, piece_id, frame):
    import bpy

    indices = payload['panels'][piece_id]['indices']
    local_index = {index: local for local, index in enumerate(indices)}
    faces = []
    for face in payload['faces']:
        belongs = [index in local_index for index in face]
        if any(belongs):
            if not all(belongs):
                raise StudioError('Native Bend cannot cross source panel ownership: ' + piece_id)
            faces.append([local_index[index] for index in face])
    if not faces:
        raise StudioError('Native Bend needs the current derived panel faces: ' + piece_id)
    offset = frame.get('offset_uv_cm', [0., 0.])
    local_cm = [[payload['rest_cm'][index][0]-offset[0],
                 payload['rest_cm'][index][1]-offset[1], 0.] for index in indices]
    if any(not math.isfinite(value) for point in local_cm for value in point):
        raise StudioError('Native Bend source local coordinates must be finite: ' + piece_id)
    parameters = {**frame['native_bend'],
                  'rotation_degrees': frame['native_bend'].get('rotation_degrees', [0., 0., 0.])}
    scene = mesh = obj = origin = evaluated = None
    report = None
    try:
        # A separate depsgraph avoids evaluating or modifying the user's scene.
        scene = bpy.data.scenes.new('A3D_Preform_Bend_Temporary')
        mesh = bpy.data.meshes.new('A3D_Preform_Bend_Mesh')
        mesh.from_pydata([[value/100 for value in point] for point in local_cm], [], faces)
        mesh.update()
        obj = bpy.data.objects.new('A3D_Preform_Bend_Panel', mesh)
        origin = bpy.data.objects.new('A3D_Preform_Bend_Origin', None)
        scene.collection.objects.link(obj)
        scene.collection.objects.link(origin)
        origin.location = [value/100 for value in parameters['origin_cm']]
        origin.rotation_mode = 'XYZ'
        origin.rotation_euler = [math.radians(value) for value in parameters['rotation_degrees']]
        modifier = obj.modifiers.new('A3D_Native_Bend', 'SIMPLE_DEFORM')
        modifier.deform_method = 'BEND'
        modifier.deform_axis = parameters['deform_axis']
        modifier.angle = math.radians(parameters['angle_degrees'])
        modifier.origin = origin
        modifier.limits = (0., 1.)
        modifier.show_viewport = modifier.show_render = True
        # Float RNA properties can clamp out-of-range finite inputs. Refuse
        # that change instead of silently evaluating a different recipe.
        actual = {'angle_degrees': math.degrees(modifier.angle),
                  'deform_axis': modifier.deform_axis,
                  'origin_cm': [float(value)*100 for value in origin.location],
                  'rotation_degrees': [math.degrees(value) for value in origin.rotation_euler]}
        for key in ('angle_degrees', 'origin_cm', 'rotation_degrees'):
            requested = parameters[key] if isinstance(parameters[key], list) else [parameters[key]]
            observed = actual[key] if isinstance(actual[key], list) else [actual[key]]
            if any(not math.isfinite(b) or not math.isclose(a, b, rel_tol=2e-6, abs_tol=2e-6)
                   for a, b in zip(requested, observed, strict=True)):
                raise StudioError('Native Bend parameter exceeds Blender representation: ' + key)
        original_edges = sorted(tuple(sorted(edge.vertices)) for edge in mesh.edges)
        with bpy.context.temp_override(scene=scene, view_layer=scene.view_layers[0]):
            depsgraph = bpy.context.evaluated_depsgraph_get()
            depsgraph.update()
            evaluated = obj.evaluated_get(depsgraph)
            result = evaluated.to_mesh()
            if result is None:
                raise StudioError('Native Bend returned no evaluated mesh: ' + piece_id)
            actual_faces = [list(polygon.vertices) for polygon in result.polygons]
            actual_edges = sorted(tuple(sorted(edge.vertices)) for edge in result.edges)
            if (len(result.vertices) != len(indices) or actual_faces != faces
                    or actual_edges != original_edges):
                raise StudioError('Native Bend changed source vertex count or connectivity: ' + piece_id)
            bent_cm = [[float(value)*100 for value in vertex.co] for vertex in result.vertices]
            if any(not math.isfinite(value) for point in bent_cm for value in point):
                raise StudioError('Native Bend produced nonfinite coordinates: ' + piece_id)
            evaluated.to_mesh_clear()
            evaluated = None
        u, v = frame['u_axis'], frame['v_axis']
        normal = [u[1]*v[2]-u[2]*v[1], u[2]*v[0]-u[0]*v[2], u[0]*v[1]-u[1]*v[0]]
        coords = {index: [frame['origin_cm'][k]+point[0]*u[k]+point[1]*v[k]+point[2]*normal[k]
                          for k in range(3)] for index, point in zip(indices, bent_cm, strict=True)}
        report = {'backend': 'BLENDER_SIMPLE_DEFORM_BEND', 'backend_version': 1,
                  'blender_version': bpy.app.version_string,
                  'parameters': parameters, 'evaluated_parameters': actual,
                  'source_ref': frame['source_ref'], 'source_frame_sha256': digest(frame),
                  'source_mapping_sha256': digest({'indices': indices, 'source_uv_cm':
                      [payload['rest_cm'][index][:2] for index in indices]}),
                  'input_geometry_sha256': digest({'local_cm': local_cm, 'faces': faces}),
                  'output_geometry_sha256': digest({'local_cm': bent_cm, 'faces': faces}),
                  'vertex_count': len(indices), 'face_count': len(faces),
                  'connectivity_preserved': True, 'native_limits': [0., 1.],
                  'local_coordinate_system': 'SOURCE_UV_MINUS_OFFSET_XY_CENTIMETRES',
                  'world_coordinate_system': 'RIGID_U_V_CROSS_U_V_FRAME_CENTIMETRES',
                  'simulation': 'NOT_EXECUTED', 'qualification': 'NONE'}
        return coords, report
    except StudioError:
        raise
    except Exception as error:
        raise StudioError('Native Blender Bend evaluation failed for ' + piece_id + ': ' + str(error)) from error
    finally:
        if evaluated is not None:
            evaluated.to_mesh_clear()
        if obj is not None:
            bpy.data.objects.remove(obj, do_unlink=True)
        if origin is not None:
            bpy.data.objects.remove(origin, do_unlink=True)
        if mesh is not None:
            bpy.data.meshes.remove(mesh)
        if scene is not None:
            bpy.data.scenes.remove(scene)
        if report is not None:
            report['temporary_data_cleaned'] = True


def preform_coordinates(payload, plan):
    """Use the actual Bend modifier when requested, preserving source plan/data."""
    coords, report = _source_preform_coordinates(payload, plan, native_evaluator=_bend_panel)
    report['source_plan_sha256'] = digest(plan)
    return coords, report
