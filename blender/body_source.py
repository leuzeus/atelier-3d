"""Evaluate only explicitly selected body dependencies in a temporary scene.

The live garment/file/SQLite are untouched. Export is a static world-space body
reference, not an imported rig, fitted garment, collider or anatomy generator.
"""
import math,uuid
from pathlib import Path
from a3d.core import StudioError,atomic_json,digest,sha

def data_ids():
    import bpy
    result=set()
    for prop in bpy.data.bl_rna.properties:
        if prop.type=='COLLECTION':
            result.update(v for v in getattr(bpy.data,prop.identifier) if isinstance(v,bpy.types.ID))
    return result

def live_geometry():
    import bpy
    from blender.sewing import mesh_digest
    return digest({obj.name:{'type':obj.type,'world':[list(row) for row in obj.matrix_world],
        'mesh':mesh_digest(obj) if obj.type=='MESH' else None,
        'pose':[list(row) for bone in obj.pose.bones for row in bone.matrix] if obj.type=='ARMATURE' else None}
        for obj in bpy.data.objects})

def _evaluate(project,selection_path,export):
    import bpy
    from a3d.body_source import selection
    from blender.sewing import mesh_digest
    data,source,selection_sha=selection(project,selection_path)
    names=set(data['meshes'])|set(data['dependencies'])
    if any(bpy.data.objects.get(n) for n in names):
        raise StudioError('Body source names already exist in the live scene; inspect the existing context instead')
    if bpy.data.objects.get(data['reference_object']):
        raise StudioError('Body reference object name already exists')
    original_ids=data_ids();live_scene=bpy.context.scene;frame=live_scene.frame_current
    filepath=bpy.data.filepath;dirty=bpy.data.is_dirty;db_sha=sha(project.db)
    live_sha=live_geometry()
    vertices=[];faces=[];rows=[];bones={};artifact=None
    try:
        with bpy.data.libraries.load(str(source),link=False) as (available,loaded):
            if not names<=set(available.objects):raise StudioError('Selected body source objects are missing')
            loaded.objects=sorted(names)
        added=set(bpy.data.objects)-{d for d in original_ids if isinstance(d,bpy.types.Object)}
        actual={o.name for o in added}
        if actual!=names:
            raise StudioError('Undeclared body dependencies: '+repr(sorted(actual-names)))
        objects={o.name:o for o in added}
        for name,obj in objects.items():
            if obj.get('a3d_component_id'):
                raise StudioError('Body source cannot include construction geometry')
            if (name in data['meshes'] and obj.type!='MESH' or
                name in data['dependencies'] and obj.type not in ('ARMATURE','EMPTY')):
                raise StudioError('Body selection must contain only meshes and declared rig/empty dependencies')
        # Simple native driver expressions with explicit ID targets may be
        # evaluated. Arbitrary Python drivers or dependencies on the live scene
        # would make a selective snapshot depend on an undeclared context.
        loaded_ids=data_ids()-original_ids
        drivers=[]
        for block in loaded_ids:
            animation=getattr(block,'animation_data',None)
            for curve in animation.drivers if animation else ():
                driver=curve.driver
                if driver.type=='SCRIPTED' and not driver.is_simple_expression:
                    raise StudioError('Body source has a scripted driver requiring unbounded context')
                targets=[t.id for v in driver.variables for t in v.targets if t.id]
                if any(t not in loaded_ids for t in targets):
                    raise StudioError('Body driver refers to an undeclared live dependency')
                drivers.append({'path':curve.data_path,'expression':driver.expression,
                    'targets':[t.name for t in targets]})
        temp=bpy.data.scenes.new('A3D.BodySource.'+uuid.uuid4().hex)
        temp.unit_settings.system='METRIC';temp.unit_settings.scale_length=data['unit_scale_m']
        for obj in added:temp.collection.objects.link(obj)
        with bpy.context.temp_override(scene=temp,view_layer=temp.view_layers[0]):
            temp.frame_set(data['frame']);dg=bpy.context.evaluated_depsgraph_get();dg.update()
            for name in sorted(data['meshes']):
                obj=objects[name];evaluated=obj.evaluated_get(dg);mesh=evaluated.to_mesh()
                try:
                    points=[[float(x)*data['unit_scale_m'] for x in evaluated.matrix_world@v.co] for v in mesh.vertices]
                    polygons=[list(p.vertices) for p in mesh.polygons]
                    if not points or not polygons or any(not math.isfinite(x) for p in points for x in p):
                        raise StudioError('Body evaluation has empty or invalid geometry')
                    offset=len(vertices);vertices.extend(points)
                    faces.extend([[i+offset for i in f] for f in polygons])
                    rows.append({'object':name,'vertex_offset':offset,'vertices':len(points),'faces':len(polygons),
                        'evaluated_geometry_sha256':digest([points,polygons]),
                        'parent':obj.parent.name if obj.parent else None,
                        'matrix_world':[list(row) for row in evaluated.matrix_world],
                        'modifiers':[{'type':m.type,'enabled':m.show_viewport} for m in obj.modifiers]})
                finally:evaluated.to_mesh_clear()
            for name in sorted(data['dependencies']):
                obj=objects[name]
                if obj.type=='ARMATURE':
                    evaluated=obj.evaluated_get(dg)
                    bones[name]={b.name:{'head_cm':[float(x)*data['unit_scale_m']*100 for x in evaluated.matrix_world@b.head],
                        'tail_cm':[float(x)*data['unit_scale_m']*100 for x in evaluated.matrix_world@b.tail]} for b in evaluated.pose.bones}
        bounds=[[min(p[i] for p in vertices)*100 for i in range(3)],
            [max(p[i] for p in vertices)*100 for i in range(3)]]
        report={'source_blend':str(source),'source_sha256':data['source_sha256'],
            'selection_path':selection_path,'selection_sha256':selection_sha,'source_ref':data['source_ref'],
            'frame':data['frame'],'unit_scale_m':data['unit_scale_m'],'evaluation':'VIEWPORT',
            'meshes':rows,'dependencies':sorted(data['dependencies']),'drivers':drivers,'bones':bones,
            'bounds_cm':bounds,'height_cm':bounds[1][2]-bounds[0][2],
            'vertices':len(vertices),'faces':len(faces),'anatomical_landmarks':'NOT_VALIDATED',
            'collider':'NOT_CREATED','fitting':'NOT_EXECUTED','accepted':False,'visual_validation':'NOT_EXECUTED'}
        if export:
            mesh=bpy.data.meshes.new(data['reference_object']);mesh.from_pydata(vertices,[],faces);mesh.update()
            reference=bpy.data.objects.new(data['reference_object'],mesh)
            reference['a3d_role']='body_reference';reference['a3d_body_source_sha256']=data['source_sha256']
            reference['a3d_body_selection_sha256']=selection_sha;reference['a3d_body_frame']=data['frame']
            report['reference_object']=reference.name;report['geometry_sha256']=mesh_digest(reference)
            token=uuid.uuid4().hex;artifact=project.data/('blender/body-reference-'+token+'.blend')
            # Writes only this object and its mesh, no source scene, materials,
            # rig, animation, previous garment or existing live construction.
            bpy.data.libraries.write(str(artifact),{reference},fake_user=True)
            report['artifact']={'path':artifact.relative_to(project.root).as_posix(),'sha256':sha(artifact)}
            report['receipt']=('blender/body-reference-'+token+'.json')
        if sha(source)!=data['source_sha256']:raise StudioError('Body source changed while evaluating')
    finally:
        bpy.data.batch_remove(ids=data_ids()-original_ids)
    if (data_ids()!=original_ids or bpy.context.scene!=live_scene or live_scene.frame_current!=frame or
        bpy.data.filepath!=filepath or bpy.data.is_dirty!=dirty or sha(project.db)!=db_sha or live_geometry()!=live_sha):
        raise StudioError('Body source evaluation changed the live scene or project')
    if export:atomic_json(project.data/report['receipt'],report)
    return report

def inspect_body_source(project_root,selection_path):
    from blender.operations import working
    project,_=working(project_root)
    return _evaluate(project,selection_path,False)

def prepare_body_reference(project_root,selection_path):
    from blender.operations import working
    project,_=working(project_root)
    return _evaluate(project,selection_path,True)
