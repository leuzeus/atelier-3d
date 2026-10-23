"""Prepare a closed geometric auxiliary proxy, never replace the target anatomy."""
import math,uuid
from a3d.core import StudioError,atomic_json,digest,sha
from a3d.fitting_preparation import envelope_spec

def prepare_fitting_envelope(project_root,envelope_path):
    import bpy,bmesh,numpy as np
    from mathutils import Vector
    from mathutils.bvhtree import BVHTree
    from blender.operations import working
    from blender.body_source import data_ids,live_geometry
    from blender.sewing import object_mesh,mesh_digest,collider_info
    project,_=working(project_root);spec,body,artifact=envelope_spec(project,envelope_path)
    if bpy.data.objects.get(spec['object']):raise StudioError('Envelope name already exists; use a new auxiliary artifact')
    original=data_ids();before=(live_geometry(),bpy.data.filepath,bpy.data.is_dirty,sha(project.db),bpy.context.scene.frame_current)
    output=None
    try:
        with bpy.data.libraries.load(str(artifact),link=False) as (available,loaded):loaded.objects=[body['reference_object']]
        target=loaded.objects[0]
        if target is None or mesh_digest(target)!=body['geometry_sha256']:raise StudioError('Body reference geometry changed')
        points,faces=object_mesh(target);points=np.array(points);rows={r['object']:r for r in body['meshes']}
        hull_points=[];hull_faces=[];regions=[]
        for region in spec['regions']:
            ids=[i for name in region['source_meshes'] for i in range(rows[name]['vertex_offset'],rows[name]['vertex_offset']+rows[name]['vertices'])]
            source=points[ids];bones=region['partition_bones'];partitions=[source]
            if bones:
                distances=[]
                for ref in bones:
                    bone=body['bones'][ref['rig']][ref['bone']];a=np.array(bone['head_cm'])/100;b=np.array(bone['tail_cm'])/100
                    d=b-a;length=float(d@d)
                    if length<1e-10:raise StudioError('Envelope partition bone is collapsed')
                    t=np.clip((source-a)@d/length,0,1);distances.append(np.linalg.norm(source-(a+t[:,None]*d),axis=1))
                labels=np.argmin(distances,axis=0);partitions=[source[labels==i] for i in range(len(bones))]
            for number,subset in enumerate(partitions):
                if len(subset)==0:
                    regions.append({'id':region['id'],'partition':number,'source_vertices':0,'hull_vertices':0,
                        'bone':bones[number],'status':'EMPTY_SOURCE_PARTITION_NO_GEOMETRY_INVENTED'})
                    continue
                if len(subset)<4:raise StudioError('Envelope partition has insufficient body geometry: '+region['id']+'/'+str(number))
                # Quantize ONLY the auxiliary construction; preserve original points for coverage.
                cell=spec['voxel_cm']/200
                _,unique=np.unique(np.floor(subset/cell).astype(np.int64),axis=0,return_index=True)
                bm=bmesh.new()
                try:
                    verts=[bm.verts.new(v) for v in subset[sorted(unique)]]
                    result=bmesh.ops.convex_hull(bm,input=verts,use_existing_faces=False)
                    disposable=[g for g in result.get('geom_unused',[])+result.get('geom_interior',[]) if isinstance(g,bmesh.types.BMVert) and g.is_valid]
                    if disposable:bmesh.ops.delete(bm,geom=list(set(disposable)),context='VERTS')
                    bm.normal_update()
                    if not bm.faces:raise StudioError('Envelope region is planar or collapsed')
                    for v in bm.verts:v.co+=v.normal*(spec['padding_cm']/100)
                    bm.verts.ensure_lookup_table();bm.verts.index_update();offset=len(hull_points)
                    hull_points.extend([list(v.co) for v in bm.verts]);hull_faces.extend([[v.index+offset for v in f.verts] for f in bm.faces])
                    regions.append({'id':region['id'],'partition':number,'source_vertices':len(subset),'hull_vertices':len(bm.verts),
                        'bone':bones[number] if bones else None})
                finally:bm.free()
        mesh=bpy.data.meshes.new(spec['object']);mesh.from_pydata(hull_points,[],hull_faces);mesh.update()
        proxy=bpy.data.objects.new(spec['object'],mesh)
        temp=bpy.data.scenes.new('A3D.Envelope.'+uuid.uuid4().hex);temp.collection.objects.link(proxy)
        modifier=proxy.modifiers.new('A3D.AuxiliaryVoxelUnion','REMESH');modifier.mode='VOXEL';modifier.voxel_size=spec['voxel_cm']/100;modifier.use_smooth_shade=False
        with bpy.context.temp_override(scene=temp,view_layer=temp.view_layers[0]):
            dg=bpy.context.evaluated_depsgraph_get();dg.update();evaluated=proxy.evaluated_get(dg)
            union=bpy.data.meshes.new_from_object(evaluated,depsgraph=dg)
        proxy.modifiers.remove(modifier);proxy.data=union
        bm=bmesh.new()
        try:
            bm.from_mesh(union);bmesh.ops.recalc_face_normals(bm,faces=list(bm.faces));bm.normal_update()
            nonmanifold=sum(not e.is_manifold for e in bm.edges);volume=bm.calc_volume(signed=True)
            remaining=set(bm.faces);components=[]
            while remaining:
                seed=remaining.pop();component={seed};queue=[seed]
                while queue:
                    face=queue.pop()
                    for edge in face.edges:
                        for adjacent in edge.link_faces:
                            if adjacent in remaining:remaining.remove(adjacent);component.add(adjacent);queue.append(adjacent)
                signed=0.
                for face in component:
                    a=face.verts[0].co
                    for b,c in zip(face.verts[1:-1],face.verts[2:]):signed+=a.dot(b.co.cross(c.co))/6
                components.append({'faces':len(component),'signed_volume_m3':signed})
            if nonmanifold or volume<=0:raise StudioError('Auxiliary envelope must be closed with outward normals')
            if any(c['signed_volume_m3']<=0 for c in components):raise StudioError('Every auxiliary shell must have outward normals and positive volume')
            bm.to_mesh(union)
        finally:bm.free()
        union.update();v,f=object_mesh(proxy);tree=BVHTree.FromPolygons([Vector(p) for p in v],f)
        signed=[]
        for point in points:
            hit,normal,_,_=tree.find_nearest(Vector(point));signed.append(float((Vector(point)-hit).dot(normal))*100)
        if max(signed)>spec['max_body_outside_cm']:
            raise StudioError('Auxiliary envelope does not cover the selected pose within the declared bound: %.4f cm'%max(signed))
        proxy['a3d_role']='auxiliary_collider';proxy['a3d_body_geometry_sha256']=body['geometry_sha256']
        proxy['a3d_body_source_sha256']=body['source_sha256'];proxy['a3d_body_frame']=body['frame']
        proxy['a3d_envelope_spec_sha256']=sha(project.root/envelope_path)
        proxy.modifiers.new('A3D.Collision','COLLISION');proxy.collision.thickness_outer=spec['thickness_outer_cm']/100;proxy.collision.thickness_inner=spec['thickness_inner_cm']/100
        collider=collider_info(proxy)
        if any(not math.isclose(collider[a],spec[b],rel_tol=1e-5) for a,b in (('outer_thickness_cm','thickness_outer_cm'),('inner_thickness_cm','thickness_inner_cm'))):
            raise StudioError('Blender clamped envelope collision thicknesses')
        token=uuid.uuid4().hex;out=project.data/('blender/fitting-envelope-'+token+'.blend')
        bpy.data.libraries.write(str(out),{proxy},fake_user=True)
        output={'status':'GEOMETRIC_ENVELOPE_PREPARED','object':proxy.name,'geometry_sha256':mesh_digest(proxy),
            'body_receipt':spec['body_receipt'],'target_geometry_sha256':body['geometry_sha256'],'source_sha256':body['source_sha256'],
            'frame':body['frame'],'spec_sha256':sha(project.root/envelope_path),'regions':regions,'nonmanifold_edges':nonmanifold,
            'closed_shell_count':len(components),'closed_shells':components,'continuous_body_skin':'NOT_CLAIMED',
            'signed_volume_m3':volume,'body_coverage':{'max_outside_cm':max(signed),'outside_vertices':sum(x>spec['max_body_outside_cm'] for x in signed)},
            'bounds_cm':[[min(p[k] for p in v)*100 for k in range(3)],[max(p[k] for p in v)*100 for k in range(3)]],
            'collider':collider,'artifact':{'path':out.relative_to(project.root).as_posix(),'sha256':sha(out)},
            'receipt':'blender/fitting-envelope-'+token+'.json','anatomical_shape':'NOT_VALIDATED_GEOMETRIC_PROXY',
            'donning':'NOT_EXECUTED','simulation':'NOT_EXECUTED','accepted':False,'visual_validation':'NOT_EXECUTED'}
    finally:bpy.data.batch_remove(ids=data_ids()-original)
    if (data_ids()!=original or (live_geometry(),bpy.data.filepath,bpy.data.is_dirty,sha(project.db),bpy.context.scene.frame_current)!=before):
        raise StudioError('Envelope preparation changed the live construction')
    atomic_json(project.data/output['receipt'],output)
    return output
