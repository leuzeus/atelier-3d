"""Native, bounded cloth recipe. Imported only inside Blender.

Reference contours, a derived simulation mesh and a frozen render copy are
separate artifacts. No proximity-based welding or editing of source packages.
"""
import copy
import math
import uuid
from pathlib import Path
from a3d.core import StudioError, atomic_json, contract, digest, inside, read_json, sha
from a3d.sewing import (distance, mass_settings, mesh_quality, point_inside,
    prepare_boundaries, segment_distance, signed_area, validate_recipe, weld_permanent,
    active_sewing_pairs, fitting_tack_payload)


def mesh_recipe_digest(recipe):
    fields={k:recipe[k] for k in ("component_id","mesh","placements","seams","pins")}
    if 'experimental_prefit' in recipe:fields['experimental_prefit']=recipe['experimental_prefit']
    if 'trial_mode' in recipe:
        fields['trial_mode']=recipe['trial_mode']
        fields['trial_pieces']=recipe['trial_pieces']
    return digest(fields)


def simulation_pairs(payload):
    """A continuous sewn surface has no loose sewing springs."""
    return [] if payload.get('rest_mode')=='assembled_3d' else active_sewing_pairs(payload)


def rest_key_name(payload):
    return 'A3D.AssembledRest' if payload.get('rest_mode')=='assembled_3d' else 'A3D.FlatRest'


def simulation_quality(payload,coords,limits):
    from a3d.cloth_metrics import validate_metrics
    return validate_metrics(payload,coords,limits,include_faces=False)


def triangulate(boundary, recipe, regular_mesh=None):
    from mathutils import Vector
    from mathutils.geometry import delaunay_2d_cdt
    polygon=boundary["polygon"]
    spacing=recipe["mesh"]["spacing_cm"]
    points=[Vector(p) for p in polygon]
    xmin,xmax=min(p[0] for p in polygon),max(p[0] for p in polygon)
    ymin,ymax=min(p[1] for p in polygon),max(p[1] for p in polygon)
    nx,ny=math.ceil((xmax-xmin)/spacing),math.ceil((ymax-ymin)/spacing)
    if nx*ny>recipe["mesh"]["max_vertices"]*4:
        raise StudioError("Interior grid exceeds the declared mesh budget")
    if regular_mesh:
        from a3d.pattern_preparation import regular_interior_points
        interior,_=regular_interior_points(boundary,regular_mesh)
        points.extend(Vector(p) for p in interior)
    else:
        for j in range(1,ny):
            for i in range(1,nx):
                p=[xmin+i*spacing,ymin+j*spacing]
                if point_inside(p,polygon) and min(segment_distance(p,a,b) for a,b in zip(polygon,polygon[1:]+polygon[:1])) >= .4*spacing:
                    points.append(Vector(p))
    ids=list(range(len(polygon)))
    if signed_area(polygon)<0:ids.reverse()
    refinement=recipe['mesh'].get('quality_refinement');added=0;passes=0;refusal=None;best=None;rejected_candidate=None
    conditioning_history=[];smoothing=None;coordinates=None
    if regular_mesh:
        refinement={**(refinement or {'max_passes':8,'max_added_vertices':4000}),
            'target_min_angle_degrees':max(regular_mesh.get('target_min_angle_degrees',15.),
                recipe['mesh']['min_angle_degrees'],(refinement or {}).get('target_min_angle_degrees',0.))}
    def angle(face,points_override=None):
        values=verts if points_override is None else points_override
        lengths=[distance(values[a],values[b]) for a,b in zip(face,face[1:]+face[:1])]
        if min(lengths)<1e-10:return 0.
        return min(math.degrees(math.acos(max(-1.,min(1.,(x*x+y*y-z*z)/(2*x*y)))))
            for x,y,z in ((lengths[0],lengths[1],lengths[2]),(lengths[1],lengths[2],lengths[0]),(lengths[2],lengths[0],lengths[1])))
    def exact_source_coordinates(vertices,triangles,origins):
        mapping={j:i for i,inputs in enumerate(origins) for j in inputs}
        if any(i not in mapping for i in range(len(polygon))) or len({mapping[i] for i in range(len(polygon))})!=len(polygon):
            raise StudioError("Triangulator collapsed a boundary anchor")
        if any(distance(vertices[mapping[i]],polygon[i])>1e-4 for i in range(len(polygon))):
            raise StudioError("Triangulator moved a boundary anchor")
        if any(len(f)!=3 for f in triangles):raise StudioError("Constrained triangulation did not produce triangles")
        restored=[list(v) for v in vertices]
        for source_index,point in enumerate(polygon):restored[mapping[source_index]]=list(point)
        if any(signed_area([vertices[i] for i in face])*signed_area([restored[i] for i in face])<=0
               for face in triangles):
            raise StudioError("Exact source anchor restoration inverted or collapsed a derived triangle")
        return restored,mapping

    while True:
        verts,edges,faces,orig,_,_=delaunay_2d_cdt(points,[],[ids],1,1e-6,True)
        if not refinement:break
        if regular_mesh:
            from a3d.mesh_refinement import improve_interior
            raw_angle=min((angle(f) for f in faces),default=0.)
            anchors={i for i,inputs in enumerate(orig) if any(j<len(polygon) for j in inputs)}
            # Judge complete candidates, not an intermediate CDT result. Each
            # candidate has the same bounded smoothing and fixed source anchors.
            improved,smoothing=improve_interior([list(v) for v in verts],faces,anchors,
                target_angle=refinement['target_min_angle_degrees'],min_edge=recipe['mesh']['min_edge_cm'],
                max_displacement=regular_mesh['min_spacing_cm']*.5)
            verts=[Vector(p) for p in improved]
            coordinates,mapping=exact_source_coordinates(verts,faces,orig)
            measured_angle=min((angle(f,coordinates) for f in faces),default=0.)
            measured_edge=min((distance(coordinates[a],coordinates[b]) for f in faces for a,b in zip(f,f[1:]+f[:1])),default=0.)
            conditioning={'passes':passes,'added_vertices':added,'raw_cdt_min_angle_degrees':raw_angle,
                'conditioned_min_angle_degrees':measured_angle,'conditioned_min_edge_cm':measured_edge,
                'interior_smoothing':smoothing,'exact_source_anchors_restored':True}
            conditioning_history.append(conditioning)
            if best and (measured_angle<best['min_angle_degrees']-1e-7 or
                    measured_edge<min(best['min_edge_cm'],recipe['mesh']['min_edge_cm'])-1e-9):
                rejected_candidate={**conditioning,'min_angle_degrees':measured_angle,'min_edge_cm':measured_edge}
                conditioning['decision']='ROLLED_BACK_AFTER_CONDITIONING'
                verts,edges,faces,orig=best['triangulation']
                coordinates,mapping=best['coordinates'],best['mapping']
                smoothing=best['smoothing']
                added,passes=best['added_vertices'],best['passes']
                refusal='NON_MONOTONIC_REFINEMENT_ROLLED_BACK';break
            conditioning['decision']='BEST_CONDITIONED_CANDIDATE_PRESERVED'
            best={'triangulation':(verts,edges,faces,orig),'min_angle_degrees':measured_angle,
                'min_edge_cm':measured_edge,'added_vertices':added,'passes':passes,
                'coordinates':coordinates,'mapping':mapping,'smoothing':smoothing}
        bad=[f for f in faces if angle(f,coordinates if regular_mesh else None)<refinement['target_min_angle_degrees']]
        if not bad:break
        if passes>=refinement['max_passes']:
            if regular_mesh:
                refusal='PASS_BUDGET_EXHAUSTED';break
            error=StudioError('Derived mesh refinement did not reach the declared angle target within its pass budget')
            error.refinement_metrics={'min_angle_degrees':min(angle(f) for f in faces),'bad_faces':len(bad),
                'added_vertices':added,'source_polygon':boundary['source'],
                'examples':[[list(verts[i]) for i in f] for f in bad[:5]]}
            raise error
        existing={(round(v.x,6),round(v.y,6)) for v in points};insert=[]
        for face in bad:
            a,b=min(((verts[a],verts[b]) for a,b in zip(face,face[1:]+face[:1])),key=lambda p:distance(*p))
            d=b-a;mid=(a+b)*.5;normal=Vector((-d.y,d.x))
            opposite=next(verts[i] for i in face if verts[i]!=a and verts[i]!=b)
            if normal.dot(opposite-mid)<0:normal=-normal
            value=mid+normal*math.sqrt(3)/2
            tri=[verts[i] for i in face]
            x,y,z=tri
            det=2*(x.x*(y.y-z.y)+y.x*(z.y-x.y)+z.x*(x.y-y.y))
            if abs(det)>1e-12:
                xx,yy,zz=x.length_squared,y.length_squared,z.length_squared
                center=Vector(((xx*(y.y-z.y)+yy*(z.y-x.y)+zz*(x.y-y.y))/det,
                    (xx*(z.x-y.x)+yy*(x.x-z.x)+zz*(y.x-x.x))/det))
                if point_inside(center,polygon):value=center
            inside_face=all((v.x-u.x)*(value.y-u.y)-(v.y-u.y)*(value.x-u.x)>=-1e-9
                for u,v in zip(tri,tri[1:]+tri[:1]))
            if not inside_face and not point_inside(value,polygon):value=sum(tri,Vector((0.,0.)))/3
            key=(round(value.x,6),round(value.y,6))
            if key not in existing and point_inside(value,polygon):
                if regular_mesh:
                    separation=max(recipe['mesh']['min_edge_cm'],distance(a,b)*.2)
                    if any(distance(value,p)<separation for p in points+insert):continue
                    if min(segment_distance(value,u,v) for u,v in zip(polygon,polygon[1:]+polygon[:1]))<separation:continue
                existing.add(key);insert.append(value)
        if not insert:
            if regular_mesh:
                refusal='REFINEMENT_STALLED';break
            raise StudioError('Derived refinement stalled; source boundary anchors remain unchanged')
        vertex_budget=min(recipe['mesh']['max_vertices'],regular_mesh['max_vertices'] if regular_mesh else recipe['mesh']['max_vertices'])
        if added+len(insert)>refinement['max_added_vertices'] or len(points)+len(insert)>vertex_budget:
            if regular_mesh:
                refusal='VERTEX_BUDGET_EXHAUSTED';break
            raise StudioError('Derived mesh refinement exceeds the declared vertex budget')
        points.extend(insert);added+=len(insert);passes+=1
    coordinates,mapping=exact_source_coordinates(verts,faces,orig)
    if regular_mesh:
        # Use the exact returned material coordinates, including restored source
        # anchors, for success. A smoothing report alone cannot grant this gate.
        final_angle=min((angle(f,coordinates) for f in faces),default=0.)
        final_edge=min((distance(coordinates[a],coordinates[b]) for f in faces for a,b in zip(f,f[1:]+f[:1])),default=0.)
        if faces and final_angle>=refinement['target_min_angle_degrees'] and final_edge>=recipe['mesh']['min_edge_cm']:refusal=None
        elif refusal is None:refusal='INTERIOR_QUALITY_TARGET_NOT_REACHED'
        boundary['preparation_refinement']={'status':'NEEDS_CORRECTION' if refusal else 'TARGET_REACHED',
            'refusal':refusal,'target_min_angle_degrees':refinement['target_min_angle_degrees'],
            'min_angle_degrees':final_angle,'min_edge_cm':final_edge,'passes':passes,'added_vertices':added,
            'max_passes':refinement['max_passes'],'max_added_vertices':refinement['max_added_vertices'],
            'source_anchors_changed':False,'rejected_candidate':rejected_candidate,
            'interior_smoothing':smoothing,
            'conditioning_policy':'BOUNDED_SMOOTHING_AND_EXACT_ANCHOR_RESTORATION_BEFORE_MONOTONE_COMPARISON',
            'conditioning_history':conditioning_history,
            'best_safe_candidate_preserved':True,
            'bad_faces':[list(f) for f in faces if angle(f,coordinates)<refinement['target_min_angle_degrees']]}
    # CDT faces are CCW. Preserve the source boundary's orientation, corrected by
    # the explicit seam graph rather than by arbitrary proximity of panels.
    if bool(boundary["flip"]) ^ (signed_area(boundary["source"])<0):
        faces=[list(reversed(f)) for f in faces]
    return coordinates,faces,mapping


def placed_point(point, placement):
    from mathutils import Euler,Vector
    x,y=point
    if placement["mode"]=="cylinder":
        radius=placement["radius_cm"]
        angle=(x-placement["origin_2d_cm"][0])/radius
        if placement.get('mirror_u', False):angle=-angle
        local=(radius*math.sin(angle),y-placement["origin_2d_cm"][1],radius*math.cos(angle))
    else:local=(x,y,0.)
    rotation=Euler([math.radians(v) for v in placement["rotation_degrees"]],"XYZ").to_matrix()
    return list(rotation@Vector(local)+Vector(placement["position_cm"]))


def build_mesh(data, recipe, regular_mesh=None, dossier=None, *,
               meshing_profile=None, meshing_envelope=None, anatomical_attachments=None):
    synchronized=meshing_profile is not None
    if not synchronized and meshing_envelope is not None:
        raise StudioError('Meshing envelope requires the explicit synchronized profile')
    if synchronized:
        from a3d.meshing_profile import create_envelope,validate_profile,verify_inventory,verify_envelope,profile_binding
        from mathutils import Vector
        if not regular_mesh:raise StudioError('Synchronized meshing requires regular mesh settings')
        validate_profile(meshing_profile,data['component_id'],recipe,regular_mesh)
        if meshing_envelope is None:
            meshing_envelope=create_envelope(meshing_profile,data['component_id'],recipe,regular_mesh)
        verify_envelope(meshing_profile,data['component_id'],recipe,regular_mesh,meshing_envelope)
        verify_inventory(meshing_profile,data,meshing_envelope)
    if regular_mesh:
        from a3d.pattern_preparation import prepare_regular_boundaries
        if synchronized:
            boundaries,seams,sampling=prepare_regular_boundaries(data,recipe,regular_mesh,dossier,
                meshing_envelope=meshing_envelope,transport_2d=lambda p:list(Vector(p)),
                anatomical_attachments=anatomical_attachments)
        else:boundaries,seams,sampling=prepare_regular_boundaries(data,recipe,regular_mesh,dossier,
                anatomical_attachments=anatomical_attachments)
        reports=sampling['seams']
    else:
        from a3d.pattern_preparation import anatomical_boundary_requirements
        mandatory=anatomical_boundary_requirements(data,anatomical_attachments)
        boundaries,seams,reports=prepare_boundaries(data,recipe,mandatory_source_uv=mandatory)
    from a3d.sewing import mandatory_boundary_bindings
    mandatory={pid:part['mandatory_source_uv_cm'] for pid,part in boundaries.items() if part.get('mandatory_source_uv_cm')}
    boundary_bindings=mandatory_boundary_bindings(boundaries,mandatory,
        check=(lambda:meshing_envelope.check('mandatory_native_boundary_binding')) if synchronized else None,
        work=(lambda amount:meshing_envelope.reserve('work_steps',amount)) if synchronized else None)
    native_bindings=[]
    rest,placed,faces=[],[],[]
    panels={};pins={}
    for index,(pid,boundary) in enumerate(boundaries.items()):
        if synchronized:
            from blender.bounded_pattern_meshing import triangulate as bounded_triangulate,ConditionedPointRefusal
            meshing_envelope.check('before_piece:'+pid)
            maximum=min(recipe['mesh']['max_vertices'],regular_mesh['max_vertices'])
            future=sum(len(row['polygon'])for name,row in boundaries.items()if name not in panels and name!=pid)
            available=maximum-len(rest)-future
            if available<20:raise StudioError('Component vertex budget leaves no supported per-piece mesh allocation')
            local_regular={**regular_mesh,'max_vertices':available}
            boundary['piece_id']=pid
            try:
                verts,local_faces,mapping=bounded_triangulate(boundary,recipe,local_regular,envelope=meshing_envelope)
            except ConditionedPointRefusal as cause:
                error=StudioError('Synchronized native meshing refused: '+str(cause))
                error.reason=cause.reason;error.status='REFUSED';error.diagnostic=cause.diagnostic
                error.bounded_meshing_partial=getattr(cause,'bounded_meshing_partial',None)
                raise error from cause
            meshing_envelope.check('after_piece:'+pid)
        else:verts,local_faces,mapping=triangulate(boundary,recipe,regular_mesh)
        offset=len(rest)
        rest.extend([[v[0],v[1],index*1000.] for v in verts])
        placed.extend(placed_point(v,recipe["placements"][pid]) for v in verts)
        faces.extend([[offset+i for i in f] for f in local_faces])
        panels[pid]={"indices":list(range(offset,len(rest))),
            "source_contour_sha256":boundary["source_sha256"],
            "boundary":[offset+mapping[i] for i in range(len(boundary["polygon"]))],
            "boundary_source_arclength_cm":boundary["keys"],
            "edges":{name:[offset+mapping[i] for i in ids] for name,ids in boundary["edges"].items()}}
        for binding in boundary_bindings:
            if binding['piece'] != pid:
                continue
            native_index=offset+mapping[binding['boundary_vertex']]
            if rest[native_index][:2] != boundary['polygon'][binding['boundary_vertex']]:
                raise StudioError('Triangulation or smoothing moved a mandatory anatomical material control: '+pid)
            native_bindings.append({**binding,'native_vertex':native_index,
                'index_space':'COMPONENT_MESH_GLOBAL','boundary_index_space':'PIECE_BOUNDARY_LOCAL'})
        for seam in seams.values():
            for side in ("a","b"):
                if seam["piece_"+side]==pid:seam[side]=[offset+mapping[i] for i in seam[side]]
        if len(rest)>min(recipe["mesh"]["max_vertices"],regular_mesh['max_vertices'] if regular_mesh else recipe['mesh']['max_vertices']):raise StudioError("Simulation vertex budget exceeded")
    for seam in seams.values():seam["pairs"]=list(zip(seam.pop("a"),seam.pop("b"),strict=True))
    for pin in recipe["pins"]:
        for i in panels[pin["piece"]]["edges"][pin["edge"]]:pins[str(i)]=max(pins.get(str(i),0),pin["weight"])
    if pins and all(pins.get(str(i),0)>=1 for i in range(len(rest))):raise StudioError("Every simulation vertex is pinned")
    payload={"version":1,"component_id":data["component_id"],"recipe_mesh_sha256":mesh_recipe_digest(recipe),
        "source_garment_sha256":digest(data),"rest_cm":rest,"placed_cm":placed,"faces":faces,"panels":panels,
        "seams":seams,"pins":pins,"seam_lengths":reports}
    if anatomical_attachments is not None:
        payload['mandatory_anatomical_boundary_bindings']=native_bindings
        payload['anatomical_attachments_sha256']=digest(anatomical_attachments)
    if recipe.get('trial_mode') == 'single_panel':
        payload['trial_mode'] = 'single_panel'
        payload['single_panel_source'] = {
            'component_id': data['component_id'], 'source_garment_sha256': digest(data),
            'piece_ids': sorted(data['pieces']), 'trial_pieces': list(recipe['trial_pieces']),
            'seam_kinds': {s['id']: s.get('kind', recipe['seams'][s['id']]['kind']) for s in data['seams']}}
    if regular_mesh:
        payload['regular_preparation_mesh']=copy.deepcopy(regular_mesh)
        payload['regular_preparation_sampling']=sampling
        payload['regular_preparation_refinement']={pid:boundary['preparation_refinement'] for pid,boundary in boundaries.items()}
    try:quality=mesh_quality(rest,placed,faces,recipe["mesh"])
    except StudioError as exc:
        exc.garment_payload=payload
        raise
    payload.update(quality=quality,full_rest_area_cm2=quality['rest_area_cm2'])
    if synchronized:
        meshing_envelope.check('after_complete_mesh_quality')
        payload['meshing_profile']=profile_binding(meshing_profile)
        payload['meshing_work']=meshing_envelope.snapshot()
        meshing_envelope.check('terminal_complete_mesh_build')
    return payload


def subset_mesh(payload, piece_ids):
    keep=sorted({i for pid in piece_ids for i in payload["panels"][pid]["indices"]})
    mapping={old:i for i,old in enumerate(keep)}
    sub=copy.deepcopy(payload)
    source_indices=payload.get('source_vertex_indices', list(range(len(payload['rest_cm']))))
    source_faces=payload.get('source_face_indices', list(range(len(payload['faces']))))
    sub['source_vertex_indices']=[source_indices[i] for i in keep]
    sub['source_face_indices']=[source_faces[i] for i,f in enumerate(payload['faces']) if all(v in mapping for v in f)]
    sub['omitted_seams']=[sid for sid,s in payload['seams'].items() if s['piece_a'] not in piece_ids or s['piece_b'] not in piece_ids]
    for key in ("rest_cm","placed_cm"):sub[key]=[payload[key][i] for i in keep]
    sub["faces"]=[[mapping[i] for i in f] for f in payload["faces"] if all(i in mapping for i in f)]
    face_ids=[i for i,f in enumerate(payload['faces']) if all(v in mapping for v in f)]
    for key in ('source_rest_triangles_cm','source_face_pieces','source_face_vertex_ids'):
        if key in payload:sub[key]=[copy.deepcopy(payload[key][i]) for i in face_ids]
    if 'source_vertex_map' in payload:
        sub['source_vertex_map']={str(source):mapping[current] for source,current in payload['source_vertex_map'].items()
                                  if current in mapping}
    elif 'source_face_vertex_ids' in payload:
        sub['source_vertex_map']={str(old):new for old,new in mapping.items()}
    if 'source_vertex_cohorts' in payload:
        sub['source_vertex_cohorts']={str(mapping[int(current)]):copy.deepcopy(sources)
                                     for current,sources in payload['source_vertex_cohorts'].items() if int(current) in mapping}
    if 'mandatory_anatomical_boundary_bindings' in payload:
        sub['mandatory_anatomical_boundary_bindings']=[{**row,'native_vertex':mapping[row['native_vertex']]}
            for row in payload['mandatory_anatomical_boundary_bindings'] if row['piece'] in piece_ids]
    sub["pins"]={str(mapping[int(i)]):w for i,w in payload["pins"].items() if int(i) in mapping}
    sub["seams"]={sid:{**s,"pairs":[[mapping[a],mapping[b]] for a,b in s["pairs"]]}
        for sid,s in payload["seams"].items() if s["piece_a"] in piece_ids and s["piece_b"] in piece_ids}
    sub["panels"]={pid:{**payload["panels"][pid],"indices":[mapping[i] for i in payload["panels"][pid]["indices"]],
        "boundary":[mapping[i] for i in payload['panels'][pid]['boundary']],
        "edges":{name:[mapping[i] for i in ids] for name,ids in payload['panels'][pid]['edges'].items()}}
        for pid in piece_ids}
    return sub


def make_object(payload, name):
    import bpy
    edges=sorted({tuple(sorted(p)) for p in simulation_pairs(payload)})
    mesh=bpy.data.meshes.new(name)
    mesh.from_pydata([[v/100 for v in p] for p in payload["placed_cm"]],edges,payload["faces"]);mesh.update()
    obj=bpy.data.objects.new(name,mesh);bpy.context.scene.collection.objects.link(obj)
    obj.shape_key_add(name="Placement")
    rest=obj.shape_key_add(name=rest_key_name(payload))
    for v,p in zip(rest.data,payload["rest_cm"],strict=True):v.co=[x/100 for x in p]
    rest.value=0.
    group=obj.vertex_groups.new(name="A3D.Pins")
    for i,w in payload["pins"].items():group.add([int(i)],w,"REPLACE")
    obj["a3d_role"]="simulation"
    if payload.get('construction_id'):obj['a3d_construction_id']=payload['construction_id']
    if payload.get('fitting_tacks'):
        import json
        obj['a3d_fitting_tacks']=json.dumps(payload['fitting_tacks'],sort_keys=True)
    return obj


def object_mesh(obj, evaluated=False):
    import bpy
    target=obj.evaluated_get(bpy.context.evaluated_depsgraph_get()) if evaluated else obj
    mesh=target.to_mesh() if evaluated else obj.data
    try:
        vertices=[list(obj.matrix_world@v.co) for v in mesh.vertices]
        faces=[list(p.vertices) for p in mesh.polygons]
        return vertices,faces
    finally:
        if evaluated:target.to_mesh_clear()


def mesh_digest(obj, evaluated=False):
    v,f=object_mesh(obj,evaluated)
    return digest({"vertices_m":[[round(x,7) for x in p] for p in v],"faces":f})


def collider_info(obj):
    import bpy
    bpy.context.view_layer.update()
    return {"object":obj.name,"dimensions_cm":[round(v*100,5) for v in obj.dimensions],
        "geometry_sha256":mesh_digest(obj,True),"scale":list(obj.scale),
        "visible":obj.visible_get(),"collision_enabled":any(m.type=="COLLISION" and m.show_viewport for m in obj.modifiers),
        "outer_thickness_cm":obj.collision.thickness_outer*100,"inner_thickness_cm":obj.collision.thickness_inner*100}


def context_colliders(recipe):
    import bpy
    from mathutils.bvhtree import BVHTree
    from mathutils import Vector
    if abs(bpy.context.scene.unit_settings.scale_length-1)>1e-8:
        raise StudioError("Cloth recipe requires Blender meters (scale_length=1)")
    trees=[];objects=[];snapshots=[]
    for expected in recipe["colliders"]:
        obj=bpy.data.objects.get(expected["object"])
        if obj is None or obj.type!="MESH":raise StudioError("Missing declared auxiliary collider: "+expected["object"])
        current=collider_info(obj)
        if not current["collision_enabled"] or not current["visible"] or any(abs(s-1)>1e-6 for s in obj.scale):
            raise StudioError("Collider must be visible, have applied scale and an enabled Collision modifier")
        if current["geometry_sha256"]!=expected["geometry_sha256"] or any(abs(a-b)>expected["tolerance_cm"] for a,b in zip(current["dimensions_cm"],expected["dimensions_cm"])):
            raise StudioError("Mannequin dimensions, pose or geometry differ from the recipe")
        if any(abs(current[k]-expected[k])>1e-5 for k in ('outer_thickness_cm','inner_thickness_cm')):
            raise StudioError('Executed collider thickness differs from the recipe')
        vertices,faces=object_mesh(obj,True)
        edges={}
        for f in faces:
            for a,b in zip(f,f[1:]+f[:1]):edges[tuple(sorted((a,b)))]=edges.get(tuple(sorted((a,b))),0)+1
        if expected["role"]=="mannequin" and any(n!=2 for n in edges.values()):
            raise StudioError("Mannequin collision volume must be closed")
        trees.append(BVHTree.FromPolygons([Vector(p) for p in vertices],faces))
        objects.append(obj);snapshots.append(current)
    return objects,trees,snapshots


def penetration_cm(coords, trees):
    from mathutils import Vector
    maximum=0.
    for point in coords:
        p=Vector([x/100 for x in point])
        for tree in trees:
            hit,normal,_,_=tree.find_nearest(p)
            if hit is not None:maximum=max(maximum,-(p-hit).dot(normal)*100)
    return maximum


def structural_inputs(obj,payload,recipe):
    """Identity/rest/topology/pins checks remain mandatory even for diagnostics."""
    import bpy
    from mathutils import Matrix
    if payload.get('construction_id') and obj.get('a3d_construction_id')!=payload['construction_id']:
        raise StudioError('Clean construction identity changed')
    if mesh_recipe_digest(recipe)!=payload["recipe_mesh_sha256"]:
        raise StudioError("Meshing, seams, pins or placement changed; rebuild a derived toile without changing the approved package")
    if any(abs(obj.matrix_world[i][j]-Matrix.Identity(4)[i][j])>1e-7 for i in range(4) for j in range(4)):
        raise StudioError("Apply placement in the recipe; simulation object transform must be identity")
    if obj.hide_get() or not obj.visible_get():raise StudioError("Simulation cloth is hidden/excluded from the active view layer")
    if any(m.type not in ("CLOTH",) for m in obj.modifiers):raise StudioError("Keep render/armature modifiers off the simulation mesh")
    coords,faces=object_mesh(obj)
    coords=[[x*100 for x in p] for p in coords]
    if any(not math.isfinite(x) for p in coords for x in p):raise StudioError('Non-finite simulation coordinates')
    if faces!=payload["faces"]:raise StudioError("Simulation topology differs from its boundary map")
    keys=obj.data.shape_keys
    rest_name=rest_key_name(payload)
    if keys is None or rest_name not in keys.key_blocks:raise StudioError("Missing declared rest shape key: "+rest_name)
    if any(distance([x*100 for x in v.co],p)>1e-3 for v,p in zip(keys.key_blocks[rest_name].data,payload["rest_cm"],strict=True)):
        raise StudioError("Flat rest shape was edited" if rest_name=='A3D.FlatRest' else 'Assembled 3D rest shape was edited')
    if any(abs(k.value)>1e-8 for k in keys.key_blocks[1:]):raise StudioError("Rest/display shape keys must not deform the base mesh")
    group=obj.vertex_groups.get("A3D.Pins")
    if group is None:raise StudioError("Missing construction pin group")
    actual={}
    for v in obj.data.vertices:
        for g in v.groups:
            if g.group==group.index and g.weight>0:actual[str(v.index)]=g.weight
    if set(actual)!=set(payload["pins"]) or any(abs(w-payload["pins"][i])>1e-6 for i,w in actual.items()):
        raise StudioError("Construction pin weights differ from the recipe")
    return coords,faces


def preflight(obj,payload,recipe):
    coords,faces=structural_inputs(obj,payload,recipe)
    try:quality=simulation_quality(payload,coords,recipe['mesh'])
    except StudioError as exc:
        exc.initial_coords_cm=coords
        raise
    from a3d.garment_rejections import seam_directions
    directions=seam_directions(payload,coords)
    # Current derived maps validate source arc correspondence and topology.
    # A spatial tangent reversal during mounting is diagnostic, not proof of a
    # reversed source seam. Old maps lacking arc correspondence keep their gate
    # until an explicit migration/rebuild supplies a verifiable current map.
    source_topology=payload.get('rest_mode')=='assembled_3d' and bool(payload.get('pattern_assembly'))
    if payload.get('rest_mode')!='assembled_3d' and payload.get('panels') and all('parameters' in s for s in payload['seams'].values()):
        from a3d.pattern_assembly import _topology
        _topology(payload);source_topology=True
    if directions['violations'] and not source_topology:
        bad=directions['violations'][0]
        error=StudioError('Placed seam directions oppose each other; seam=%s pieces=%s/%s segment=%d cosine=%s threshold=%s; inspect orientation before sewing'
            %(bad['seam_id'],bad['piece_a'],bad['piece_b'],bad['segment'],bad['cosine'],bad['threshold']))
        error.initial_coords_cm=coords
        raise error
    colliders,trees,snapshots=context_colliders(recipe)
    penetration=penetration_cm(coords,trees)
    if penetration>recipe["limits"]["max_penetration_cm"]:
        from mathutils import Vector
        from a3d.sewing_diagnostics import source_coordinates
        owners={i:pid for pid,panel in payload['panels'].items() for i in panel['indices']}
        contacts=[]
        for index,point in enumerate(coords):
            p=Vector([x/100 for x in point])
            for tree,snapshot in zip(trees,snapshots,strict=True):
                hit,normal,face,_=tree.find_nearest(p)
                if hit is None:continue
                depth=-(p-hit).dot(normal)*100
                if depth>recipe['limits']['max_penetration_cm']:
                    pid=owners[index];panel=payload['panels'][pid]
                    contacts.append({'index':index,'piece':pid,**source_coordinates(payload,index),
                        'position_cm':point,'named_edges':[name for name,ids in panel['edges'].items() if index in ids],
                        'pin_weight':payload['pins'].get(str(index),0.),'collider':snapshot['object'],'surface_face':face,
                        'surface_cm':[x*100 for x in hit],'surface_normal':list(normal),'depth_cm':depth,
                        'threshold_cm':recipe['limits']['max_penetration_cm']})
        worst=max(contacts,key=lambda c:c['depth_cm'])
        error=StudioError("Cloth starts inside a collider: %.4f cm; piece=%s vertex=%d collider=%s threshold=%.4f cm"
            %(penetration,worst['piece'],worst['index'],worst['collider'],worst['threshold_cm']))
        error.initial_contacts=contacts;error.collider_snapshots=snapshots;error.initial_coords_cm=coords
        raise error
    return {"quality":quality,"colliders":snapshots,"max_penetration_cm":penetration,
        'seam_directions':directions,'orientation_policy':'SOURCE_TOPOLOGY' if source_topology else 'LEGACY_3D_TANGENTS'},colliders,trees


def apply_physics(obj,payload,recipe,phase,colliders):
    import bpy
    scene=bpy.context.scene;profile=recipe["phases"][phase]
    for m in list(obj.modifiers):
        if m.type=="CLOTH":obj.modifiers.remove(m)
    scene.frame_set(1);scene.frame_start=1;scene.frame_end=profile["frames"]
    scene.render.fps=profile["fps"];scene.render.fps_base=1.;scene.use_gravity=True;scene.gravity=profile["gravity_m_s2"]
    cloth=obj.modifiers.new("A3D.Cloth", "CLOTH");settings=cloth.settings
    area=simulation_quality(payload,payload['placed_cm'],recipe['mesh'])["rest_area_cm2"]
    mass=copy.deepcopy(recipe["mass"])
    if mass["basis"]=="total_kg":mass["value"]*=area/payload["full_rest_area_cm2"]
    calculated=mass_settings(mass,area,len(payload["rest_cm"]),profile["sewing_force_per_kg"])
    settings.mass=calculated["mass_per_vertex_kg"];settings.sewing_force_max=calculated["sewing_force_max"]
    settings.use_sewing_springs=bool(simulation_pairs(payload))
    settings.rest_shape_key=obj.data.shape_keys.key_blocks[rest_key_name(payload)];settings.use_dynamic_mesh=False
    settings.shrink_min=0.;settings.shrink_max=0.
    settings.vertex_group_mass="A3D.Pins";settings.pin_stiffness=1.;settings.quality=profile["quality"];settings.time_scale=1.
    damping_scale=calculated["mass_per_vertex_kg"]/profile["damping_reference_mass_kg"]
    calculated['damping_scale']=damping_scale
    settings.effector_weights.gravity=1.;settings.air_damping=profile["air_damping"]*damping_scale
    for name in ("tension_stiffness","compression_stiffness","shear_stiffness","bending_stiffness"):
        setattr(settings,name,profile[name])
    from blender.regional_cloth import apply_regions
    regional=apply_continuous_regions(obj,payload,profile,settings) if payload.get('rest_mode')=='assembled_3d' and profile.get('regional_stiffness') else apply_regions(obj,payload,profile,settings)
    if regional:calculated['regional_stiffness']=regional
    for name in ("tension_damping","compression_damping","shear_damping","bending_damping"):
        setattr(settings,name,profile["structural_damping"]*damping_scale)
    collection=bpy.data.collections.new(recipe["collision_collection"]+"."+uuid.uuid4().hex[:8])
    scene.collection.children.link(collection)
    for collider in colliders:collection.objects.link(collider)
    collision=cloth.collision_settings;collision.collection=collection
    collision.use_collision=bool(colliders);collision.use_self_collision=profile["self_collision"]
    collision.distance_min=profile["collision_distance_cm"]/100;collision.self_distance_min=profile["self_distance_cm"]/100
    collision.collision_quality=profile["collision_quality"]
    # Current Blender groups EXCLUDE triangles from contact. Name and content
    # deliberately describe that meaning; do not use an "interior inclusion" group.
    group=obj.vertex_groups.get("A3D.SeamSelfExclusion") or obj.vertex_groups.new(name="A3D.SeamSelfExclusion")
    group.remove(list(range(len(obj.data.vertices))))
    seam_ids={i for pair in simulation_pairs(payload) for i in pair}
    ids=sorted(seam_ids | {i for face in payload['faces'] if seam_ids.intersection(face) for i in face})
    if ids:group.add(ids,1.,"REPLACE")
    collision.vertex_group_self_collisions=group.name;collision.vertex_group_object_collisions=""
    cloth.point_cache.frame_start=1;cloth.point_cache.frame_end=profile["frames"];cloth.point_cache.use_disk_cache=False
    if not math.isclose(settings.mass,calculated["mass_per_vertex_kg"],rel_tol=1e-5) or not math.isclose(settings.sewing_force_max,calculated["sewing_force_max"],rel_tol=1e-5):
        raise StudioError("Blender clamped the planned physical parameters")
    assigned={k:profile[k] for k in ('tension_stiffness','compression_stiffness','shear_stiffness','bending_stiffness')}
    assigned.update({k:profile['structural_damping']*damping_scale for k in
        ('tension_damping','compression_damping','shear_damping','bending_damping')})
    assigned['air_damping']=profile['air_damping']*damping_scale
    contacts={'distance_min':profile['collision_distance_cm']/100,'self_distance_min':profile['self_distance_cm']/100}
    mismatches=[]
    for owner,expected in ((settings,assigned),(collision,contacts)):
        for key,value in expected.items():
            observed=getattr(owner,key)
            if not math.isclose(observed,value,rel_tol=1e-5,abs_tol=1e-9):
                rna=owner.bl_rna.properties[key]
                mismatches.append({'parameter':key,'expected':value,'observed':observed,
                    'rna_hard_min':getattr(rna,'hard_min',None),'rna_hard_max':getattr(rna,'hard_max',None)})
    if mismatches:
        error=StudioError('Blender clamped stiffness, damping or contact distances; revise the technical recipe: '+repr(mismatches))
        error.physical_parameter_mismatches=mismatches
        raise error
    return cloth,calculated,collection


def apply_continuous_regions(obj,payload,profile,settings):
    """Map source 2D material weights through declared permanent unions."""
    from a3d.regional_cloth import regional_weights,MAXIMA
    from blender.regional_cloth import GROUPS
    source=payload.get('regional_source');mapping=payload.get('source_vertex_map')
    if not source or not mapping:raise StudioError('Continuous regional stiffness requires the immutable source UV map')
    weights,receipt=regional_weights(source,profile['regional_stiffness'])
    actual={};count=len(payload['rest_cm'])
    for channel,field in GROUPS.items():
        values=[0.]*count
        for old,new in mapping.items():values[new]=max(values[new],weights[channel][int(old)])
        group=obj.vertex_groups.get('A3D.Stiffness.'+channel) or obj.vertex_groups.new(name='A3D.Stiffness.'+channel)
        group.remove(list(range(count)))
        for i,value in enumerate(values):group.add([i],value,'REPLACE')
        setattr(settings,field,group.name)
        measured=[next((g.weight for g in v.groups if g.group==group.index),0.) for v in obj.data.vertices]
        if any(not math.isclose(a,b,rel_tol=1e-6,abs_tol=1e-7) for a,b in zip(values,measured,strict=True)):
            raise StudioError('Blender clamped continuous regional stiffness weights')
        actual[channel]=measured
    for field,value in profile['regional_stiffness']['ceilings'].items():
        prop=settings.bl_rna.properties[field]
        if not math.isfinite(value) or not prop.hard_min<=value<=prop.hard_max:
            raise StudioError('Continuous regional stiffness ceiling is outside the native RNA range')
        setattr(settings,field,value)
        if not math.isclose(getattr(settings,field),value,rel_tol=1e-6,abs_tol=1e-7):
            raise StudioError('Blender clamped continuous regional stiffness ceiling')
    return {**receipt,'source_vertex_map_sha256':digest(mapping),'junction_policy':'MAX_SOURCE_WEIGHT_PER_CHANNEL',
        'executed_weights':actual,'executed_weights_sha256':digest(actual),
        'executed_groups':{k:getattr(settings,v) for k,v in GROUPS.items()},
        'executed_ceilings':{k:getattr(settings,k) for k in MAXIMA}}


def physical_snapshot(obj):
    import bpy
    cloths=[m for m in obj.modifiers if m.type=="CLOTH"]
    if len(cloths)!=1:raise StudioError("Expected exactly one Cloth modifier")
    m=cloths[0];s=m.settings;c=m.collision_settings;scene=bpy.context.scene
    fields=("mass","sewing_force_max","use_sewing_springs","quality","time_scale","use_dynamic_mesh","shrink_min","shrink_max","vertex_group_mass","pin_stiffness",
        "tension_stiffness","compression_stiffness","shear_stiffness","bending_stiffness","tension_damping","compression_damping","shear_damping","bending_damping","air_damping",
        "vertex_group_structural_stiffness","vertex_group_shear_stiffness","vertex_group_bending",
        "tension_stiffness_max","compression_stiffness_max","shear_stiffness_max","bending_stiffness_max")
    groups={g.name:g.index for g in obj.vertex_groups}
    weights={name:[(v.index,round(w.weight,7)) for v in obj.data.vertices for w in v.groups if w.group==index]
        for name,index in groups.items() if name in (s.vertex_group_mass,c.vertex_group_self_collisions,c.vertex_group_object_collisions,
            s.vertex_group_structural_stiffness,s.vertex_group_shear_stiffness,s.vertex_group_bending)}
    return {"settings":{k:getattr(s,k) for k in fields},"rest_shape_key":s.rest_shape_key.name if s.rest_shape_key else None,
        "sewing_edges_sha256":digest(sorted(sorted(e.vertices) for e in obj.data.edges if e.is_loose)),
        "fitting_tacks":obj.get('a3d_fitting_tacks'),
        "group_weights_sha256":digest(weights),
        "gravity_weight":s.effector_weights.gravity,"cache":[m.point_cache.frame_start,m.point_cache.frame_end,m.point_cache.use_disk_cache],
        "collisions":{k:getattr(c,k) for k in ("use_collision","use_self_collision","distance_min","self_distance_min","collision_quality","vertex_group_self_collisions","vertex_group_object_collisions")},
        "collection":sorted(o.name for o in c.collection.objects) if c.collection else None,
        "gravity":list(scene.gravity),"use_gravity":scene.use_gravity,"fps":scene.render.fps,"fps_base":scene.render.fps_base,
        "scale_length":scene.unit_settings.scale_length,"modifier_enabled":m.show_viewport and m.show_render}


def verify_physics(obj, expected):
    if physical_snapshot(obj)!=expected:raise StudioError("Executed Cloth/cache/context parameters differ from the recipe (including recreated modifiers)")


def contact_refusal(report,initial=False):
    reasons=[];uncertain=False;demonstrated=False
    def visit(value):
        nonlocal uncertain,demonstrated
        if isinstance(value,dict):
            if value.get('reason'):reasons.append(value['reason'])
            uncertain=uncertain or value.get('ambiguous_sign_count',0)>0
            demonstrated=demonstrated or value.get('contact_count',0)>0 or bool(value.get('swept_contacts'))
            worst=value.get('worst') or {}
            if (worst.get('sign_classification') not in (None,'AMBIGUOUS_REFUSED')
                    and worst.get('signed_offset_cm',0)<value.get('clearance_cm',-math.inf)-1e-6):
                demonstrated=True
            for key in ('contact','self_contact','point_samples'):visit(value.get(key))
    visit(report)
    if any(reason in ('CONTACT_MOTION_UNDERSAMPLED','CONTACT_PAIR_BUDGET','SWEPT_RAY_BUDGET') for reason in reasons):
        category='contact_sampling';outcome='INCOMPLETE'
    elif any(reason in ('COLLIDER_GEOMETRY_CHANGED','COLLIDER_UNAVAILABLE','COLLIDER_VOLUME_ORIENTATION') for reason in reasons):
        category='contact_context';outcome='INCOMPLETE'
    elif uncertain and not demonstrated:
        category='contact_sign_uncertainty';outcome='INCOMPLETE'
    else:
        category='placement_enfilage' if initial else 'sampled_motion_contact';outcome='FAIL'
    error=StudioError('Precise cloth contact admission refused: '+str(report.get('reason',report.get('status','REFUSED'))))
    error.contact_report=report;error.reason_category=category;error.simulation_outcome=outcome
    return error


def simulate_object(obj,payload,recipe,phase,colliders,trees,save_progress=None,save_diagnostic=None):
    import bpy
    from a3d.sewing_diagnostics import motion_metrics
    cloth,mass,collection=apply_physics(obj,payload,recipe,phase,colliders)
    expected=physical_snapshot(obj)
    start=[[x*100 for x in p] for p in object_mesh(obj)[0]]
    pairs=simulation_pairs(payload)
    initial_gap=max((distance(start[a],start[b]) for a,b in pairs),default=0.)
    history=[];maximum_displacement=0.;coords=start;frame=0;final_quality=None
    previous=None;previous_frame=None;evaluated_frame=0;motion=None;final_checks=None
    contact=None;context=None;monitor=None
    try:
        from blender.cloth_contacts import build_contact_context,check_contacts,check_motion
        from a3d.cloth_metrics import face_sources
        source_metrics=face_sources(payload)
        profile=recipe['phases'][phase]
        if profile.get('execution_control'):
            from a3d.simulation_control import ConvergenceMonitor
            monitor=ConvergenceMonitor(profile['execution_control'],profile['fps'],profile['frames'],recipe['limits']['max_seam_gap_cm'])
        policy=payload.get('pattern_assembly',{}).get('contact_policy',{})
        clearance=policy.get('clearance_cm',0.)
        context=build_contact_context(payload,colliders,clearance_cm=clearance,
            self_clearance_cm=profile['self_distance_cm'] if profile['self_collision'] else 0.,
            seam_tolerance_cm=recipe['limits']['weld_gap_cm'],
            max_penetration_cm=recipe['limits']['max_penetration_cm'])
        reserves=[v for v in (profile['collision_distance_cm'],profile['self_distance_cm'],clearance) if v>0.]
        contact_step=min([.25]+[v/2 for v in reserves])
        evidence={'version':2,'metric_scope':'SOURCE_2D_PRINCIPAL_PER_FACE_EVERY_EVALUATED_FRAME',
            'source_face_metrics_sha256':digest(source_metrics),'native_rest':rest_key_name(payload),
            'native_rest_sha256':digest(payload['rest_cm']),
            'dynamic_mesh':False,'shrink_min':0.,'shrink_max':0.,
            'contact_scope':'STATIC_COLLIDERS_DISCRETE_LINEAR_INTERVAL_SAMPLES_NOT_EXHAUSTIVE_CCD',
            'motion_max_step_cm':contact_step,'motion_max_subdivisions':128,
            'temporary_supports_active':payload.get('pattern_assembly',{}).get('temporary_supports_active','NOT_RECORDED')}
        permanent_continuity=None
        if payload.get('rest_mode')=='assembled_3d' and any(seam['kind']=='permanent' for seam in payload['seams'].values()):
            from a3d.pattern_assembly import verify_permanent_continuity
            permanent_continuity=verify_permanent_continuity(payload,recipe['limits']['weld_gap_cm'])
            evidence['permanent_continuity']=permanent_continuity
        if payload.get('rest_mode')=='assembled_3d' and (expected['settings']['use_sewing_springs'] or
                evidence['temporary_supports_active'] is True):
            raise StudioError('Continuous relaxation requires zero sewing springs and no temporary supports')
        contact=check_contacts(context,start,frame=0)
        if not contact['ok']:
            raise contact_refusal(contact,initial=True)
        for frame in range(1,recipe["phases"][phase]["frames"]+1):
            if monitor:monitor.before_frame()
            previous=coords;previous_frame=evaluated_frame
            bpy.context.scene.frame_set(frame)
            # Explicit depsgraph evaluation on EVERY frame, not just frame_set or
            # an API return code; otherwise a background cloth may never advance.
            coords=[[x*100 for x in p] for p in object_mesh(obj,True)[0]]
            if len(coords)!=len(start) or any(not math.isfinite(x) for p in coords for x in p):raise StudioError("Nonfinite cloth or changed evaluated topology")
            evaluated_frame=frame
            motion=motion_metrics(payload,coords,start,frame,previous,previous_frame,
                recipe['limits']['max_displacement_cm'],include_pieces=False)
            movement=motion['max_excursion']['distance_cm']
            maximum_displacement=max(maximum_displacement,movement)
            gap=max((distance(coords[a],coords[b]) for a,b in pairs),default=0.)
            quality_error=None
            try:final_quality=simulation_quality(payload,coords,recipe['mesh'])
            except StudioError as exc:
                final_quality=getattr(exc,'quality_metrics',None);quality_error=exc
            contact=check_motion(context,previous,coords,previous_frame,frame,
                max_step_cm=contact_step,max_subdivisions=128)
            solver=cloth.solver_result
            history.append({"frame":frame,"max_movement_cm":movement,"max_seam_gap_cm":gap,
                "motion":motion,'quality':{'status':'FAIL' if quality_error else 'PASS','metrics':final_quality,
                    'violations':getattr(quality_error,'quality_violations',[])},'contact':contact,
                "solver_max_iterations":solver.max_iterations if solver else None})
            if save_progress:save_progress(history)
            if quality_error:raise quality_error
            if not contact['ok']:
                raise contact_refusal(contact)
            if maximum_displacement>recipe["limits"]["max_displacement_cm"]:raise StudioError("Cloth displacement budget exceeded; diagnose the local case")
            if monitor and monitor.observe(frame,coords,gap,True):break
        if monitor:monitor.require_convergence()
        verify_physics(obj,expected)
        quality_error=None
        try:final_quality=simulation_quality(payload,coords,recipe['mesh'])
        except StudioError as exc:
            final_quality=getattr(exc,'quality_metrics',None);quality_error=exc
        final_contact=check_contacts(context,coords,frame=frame)
        if not final_contact['ok']:raise contact_refusal(final_contact)
        penetration=max(0.,-(final_contact['minimum_signed_offset_cm'] or 0.))
        final_gap=history[-1]['max_seam_gap_cm']
        final_checks={'quality':{'status':'FAIL' if quality_error else 'PASS','metrics':final_quality,
                'violations':getattr(quality_error,'quality_violations',[])},
            'penetration':{'measured_cm':penetration,'limit_cm':recipe['limits']['max_penetration_cm'],
                'status':'FAIL' if penetration>recipe['limits']['max_penetration_cm'] else 'PASS'},
            'seams':{'measured_max_gap_cm':final_gap if pairs else None,'limit_cm':recipe['limits']['max_seam_gap_cm'],
                'status':('FAIL' if final_gap>recipe['limits']['max_seam_gap_cm'] else 'PASS') if pairs else 'CONTINUITY_VERIFIED' if permanent_continuity else 'NOT_APPLICABLE',
                'active_pair_count':len(pairs),
                'source_seam_kinds':{sid:seam['kind'] for sid,seam in payload['seams'].items()},
                'scope':'ACTIVE_PERMANENT_AND_EXPLICIT_TEMPORARY_PAIRS',
                'reason':None if pairs else 'EXPLICIT_PERMANENT_SOURCE_UNIONS_VERIFIED' if permanent_continuity else 'NO_ACTIVE_SEWING_PAIRS_IN_SOURCE_SCOPE',
                'permanent_continuity':permanent_continuity}}
        if not pairs and any(seam['kind']=='permanent' for seam in payload['seams'].values()) and not permanent_continuity:
            raise StudioError('Permanent source sewing cannot be qualified without actual mapped pairs')
        if quality_error:raise quality_error
        if maximum_displacement<recipe["limits"]["min_movement_cm"]:
            raise StudioError("No measured cloth response; a successful API call is not a simulation")
        if penetration>recipe["limits"]["max_penetration_cm"]:raise StudioError("Final cloth penetrates its declared collider")
        final_gap=history[-1]["max_seam_gap_cm"]
        if pairs and final_gap>recipe["limits"]["max_seam_gap_cm"]:raise StudioError("Seams did not settle within the declared tolerance")
        if pairs and initial_gap>recipe["limits"]["max_seam_gap_cm"] and final_gap>=initial_gap*.95:
            raise StudioError("No measured sewing improvement")
        return coords,{"simulation":"PASS","phase":phase,"mass":mass,"executed":expected,"frames":history,"final_quality":final_quality,"final_checks":final_checks,
            'execution_control':monitor.report() if monitor else {'mode':'FIXED_FRAME_BUDGET','convergence':'NOT_QUALIFIED'},
            'validation_contract':evidence,'final_contact':final_contact,
            "max_penetration_cm":penetration,"initial_gap_cm":initial_gap,"final_gap_cm":final_gap,
            "centroid_start_cm":[sum(p[k] for p in start)/len(start) for k in range(3)],
            "centroid_end_cm":[sum(p[k] for p in coords)/len(coords) for k in range(3)],
            "visual_validation":"NOT_EXECUTED"}
    except BaseException as exc:
        if save_diagnostic:
            try:
                from a3d.sewing_diagnostics import failure_geometry
                from mathutils import Vector
                penetrations=[]
                source=payload.get('source_vertex_indices', list(range(len(start))))
                for i,point in enumerate(coords):
                    if any(not math.isfinite(x) for x in point):continue
                    p=Vector([x/100 for x in point])
                    for ti,tree in enumerate(trees):
                        hit,normal,_,_=tree.find_nearest(p)
                        depth=-(p-hit).dot(normal)*100 if hit is not None else 0.
                        if depth>recipe['limits']['max_penetration_cm']:
                            penetrations.append({'index':i,'source_index':source[i] if i<len(source) else None,
                                'collider':colliders[ti].name,'depth_cm':depth})
                try:observed=physical_snapshot(obj)
                except Exception as snapshot_error:observed={'unavailable':repr(snapshot_error)}
                geometry=failure_geometry(payload,coords,start,recipe,penetrations)
                geometry['motion']=motion_metrics(payload,coords,start,evaluated_frame,previous,previous_frame,
                    recipe['limits']['max_displacement_cm'])
                save_diagnostic({'error':str(exc),'frame':evaluated_frame,'requested_frame':frame,'expected_execution':expected,'executed':observed,'frames':history,'final_quality':final_quality,'final_checks':final_checks,
                    'simulation_outcome':getattr(exc,'simulation_outcome','FAIL'),
                    'execution_control':monitor.report() if monitor else {'mode':'FIXED_FRAME_BUDGET','convergence':'NOT_QUALIFIED'},
                    'contact':getattr(exc,'contact_report',contact),
                    'geometry':geometry})
            except Exception as diagnostic_error:
                exc.add_note('Failure diagnostic unavailable: '+repr(diagnostic_error))
        raise
    finally:
        # No stale cache can qualify a subsequent run. The caller stores evaluated
        # coordinates as a new state, preserving the independent flat rest key.
        if cloth in list(obj.modifiers):obj.modifiers.remove(cloth)
        if collection.name in bpy.data.collections:bpy.data.collections.remove(collection)


def commit_positions(obj,coords):
    for i,p in enumerate(coords):
        value=[x/100 for x in p];obj.data.vertices[i].co=value
        obj.data.shape_keys.key_blocks[0].data[i].co=value
    obj.data.update()


def grid_probe(spacing, two=False, height=6.):
    """Synthetic square coupons, independent of any user geometry."""
    rest=[];placed=[];faces=[];pins={};seams={}
    n=max(2,math.ceil(10/spacing));w=10/n
    for panel in range(2 if two else 1):
        off=len(rest)
        for y in range(n+1):
            for x in range(n+1):
                rest.append([x*w,y*w,panel*1000.])
                placed.append([x*w+panel*11,y*w,height])
                if two and ((panel==0 and x==0) or (panel==1 and x==n)):pins[str(len(rest)-1)]=1.
        for y in range(n):
            for x in range(n):
                a=off+y*(n+1)+x
                faces.extend([[a,a+1,a+n+2],[a,a+n+2,a+n+1]])
    if two:
        seams['coupon']={'kind':'permanent','pairs':[[y*(n+1)+n,(n+1)**2+y*(n+1)] for y in range(n+1)]}
    panels={'synthetic-'+str(index):{'indices':list(range(index*(n+1)**2,(index+1)*(n+1)**2)),
        'edges':{},'boundary':[]} for index in range(2 if two else 1)}
    return {'rest_cm':rest,'placed_cm':placed,'faces':faces,'pins':pins,'seams':seams,'panels':panels,'full_rest_area_cm2':100*(2 if two else 1)}


def backend_probes(recipe,phase,output_dir,proof_callback=None,failure_callback=None):
    """Three tiny physical tests in a separate scene; zero user-scene mutations."""
    import bpy
    from mathutils.bvhtree import BVHTree
    from mathutils import Vector
    output_dir=Path(output_dir);output_dir.mkdir(parents=True,exist_ok=True)
    original=bpy.context.window.scene
    scene=bpy.data.scenes.new('A3D.BackendProbes.'+uuid.uuid4().hex[:8])
    bpy.context.window.scene=scene;scene.unit_settings.system='METRIC';scene.unit_settings.scale_length=1.
    results={}
    try:
        for case in ('gravity','sewing','contact'):
            local=copy.deepcopy(recipe)
            # Mechanism probes isolate forces; the subsequent project-local trial
            # uses the unmodified material, gravity and collision recipe.
            profile=local['phases'][phase]
            profile['gravity_m_s2']=[0,0,0] if case=='sewing' else [0,0,-9.81]
            profile['self_collision']=False
            profile['frames']=24 if case=='sewing' else 12
            local['limits']['max_displacement_cm']=100
            local['limits']['max_seam_gap_cm']=.5
            # Start contact close enough that the measured free-fall control
            # would cross the support within the same twelve evaluated frames.
            payload=grid_probe(local['mesh']['spacing_cm'],case=='sewing',height=2. if case=='contact' else 6.)
            obj=make_object(payload,'A3D.Probe.'+case)
            colliders=[];trees=[]
            if case=='contact':
                bpy.ops.mesh.primitive_cube_add(size=1,location=(.05,.05,-.05))
                body=bpy.context.object;body.name='A3D.ProbeSupport';body.scale=(.6,.6,.1)
                bpy.ops.object.transform_apply(location=False,rotation=False,scale=True)
                body.modifiers.new('Collision','COLLISION');body.collision.thickness_outer=.001
                v,f=object_mesh(body)
                trees=[BVHTree.FromPolygons([Vector(p) for p in v],f)];colliders=[body]
            if proof_callback:proof_callback(case,'before',obj)
            saved=False;coords=payload['placed_cm'];report=None
            def preserve(data):
                nonlocal saved
                from a3d.sewing_diagnostics import store_probe_failure
                data['geometry']['mapping_domain']='synthetic_coupon'
                data.update(component_id='synthetic.probe.'+case,phase=phase,scope='backend-probe',
                    schema_version=1,simulation='FAIL',accepted=False,synthetic=True,visual_validation='NOT_EXECUTED',
                    execution_stage='backend_probe',backend_probe_simulation='FAIL',garment_simulation='NOT_EXECUTED',
                    probe={'case':case,'requested_phase_frames':recipe['phases'][phase]['frames'],
                        'configured_frames':profile['frames'],'profile':copy.deepcopy(profile),
                        'mass_input':local['mass'],'mesh_limits':local['mesh'],'limits':local['limits'],
                        'colliders':[collider_info(c) for c in colliders],
                        'supports':[{'index':int(i),'weight':w,'position_cm':payload['placed_cm'][int(i)]}
                            for i,w in payload['pins'].items()],
                        'completed_cases':list(results)})
                ref=store_probe_failure(output_dir,data);saved=True
                if failure_callback:failure_callback(data,ref)
            try:
                coords,report=simulate_object(obj,payload,local,phase,colliders,trees,save_diagnostic=preserve)
                if case=='gravity' and sum(p[2] for p in coords)/len(coords)>=5.:
                    raise StudioError('Gravity probe did not fall at least 1 cm')
                if case=='contact' and (min(p[2] for p in coords)<-.1 or max(p[2] for p in coords)>2.):
                    raise StudioError('Contact probe did not settle above its support')
                if case=='contact':
                    free_fall=results['gravity']['centroid_end_cm'][2]-results['gravity']['centroid_start_cm'][2]
                    if 2.+free_fall>=-.1:
                        raise StudioError('Contact probe never challenged the support; free-fall control did not reach it')
                    report['unopposed_contact_centroid_z_cm']=2.+free_fall
            except BaseException as exc:
                if not saved:
                    from a3d.sewing_diagnostics import failure_geometry
                    try:observed=physical_snapshot(obj)
                    except Exception as error:observed={'unavailable':repr(error)}
                    preserve({'error':str(exc),'frame':report['frames'][-1]['frame'] if report else 0,
                        'frames':report['frames'] if report else [],
                        'expected_execution':report['executed'] if report else None,
                        'executed':report['executed'] if report else observed,'final_quality':report['final_quality'] if report else None,
                        'geometry':failure_geometry(payload,coords,payload['placed_cm'],local)})
                raise
            commit_positions(obj,coords)
            if proof_callback:proof_callback(case,'after',obj)
            report['case']=case;report['synthetic']=True;results[case]=report
            atomic_json(output_dir/(case+'.json'),report)
            for o in list(scene.objects):bpy.data.objects.remove(o,do_unlink=True)
        return {'blender_version':bpy.app.version_string,'checks':results,'simulation':'PASS','visual_validation':'NOT_EXECUTED'}
    finally:
        for o in list(scene.objects):bpy.data.objects.remove(o,do_unlink=True)
        bpy.context.window.scene=original
        bpy.data.scenes.remove(scene)


def managed_inputs(project,component_id,recipe_path,check_placement=True):
    import bpy
    state,component=project.ready(component_id)
    if component['stage']=='RECONSTRUCTED':raise StudioError('Accepted sewing geometry is immutable')
    objects=[o for o in bpy.data.objects if o.type=='MESH' and o.get('a3d_component_id')==component_id and o.get('a3d_role')=='simulation']
    if len(objects)!=1:raise StudioError('Prepare exactly one native derived simulation mesh with garment(recipe_path=...)')
    obj=objects[0]
    meta=inside(project.root,obj['a3d_sewing_mesh'])
    if sha(meta)!=obj['a3d_sewing_mesh_sha256']:raise StudioError('Derived boundary map changed')
    payload=read_json(meta)
    if payload['package_sha256']!=component['package']['sha256'] or obj.get('a3d_package_sha256')!=component['package']['sha256']:
        raise StudioError('Simulation mesh package changed')
    source=inside(project.root,payload['source_garment'])
    data=read_json(source)
    if digest(data)!=payload['source_garment_sha256']:raise StudioError('Extracted source contours changed')
    recipe=read_json(inside(project.root,recipe_path));validate_recipe(data,recipe)
    if check_placement:preflight(obj,payload,recipe)
    return obj,payload,recipe


def trial_binding(obj,payload,recipe,phase,context):
    import bpy
    binding={'recipe':recipe,'phase':phase,'mesh':mesh_digest(obj),'map':obj['a3d_sewing_mesh_sha256'],
        'blender':bpy.app.version_string,'colliders':context['colliders'],'fit_binding':context.get('fit_binding')}
    if payload.get('construction_id'):
        if obj.get('a3d_construction_id')!=payload['construction_id']:raise StudioError('Clean construction identity changed')
        binding['construction_id']=payload['construction_id']
    return digest(binding)


def simulate_sewn(project_root,component_id,recipe_path,phase,scope,purpose='fitting'):
    import bpy
    from blender.operations import working
    project,session=working(project_root)
    obj,payload,recipe=managed_inputs(project,component_id,recipe_path)
    from a3d.physics_admission import require_recipe_fit_intent
    require_recipe_fit_intent(project, recipe)
    context,colliders,trees=preflight(obj,payload,recipe)
    from blender.physics_admission import require_native_recipe_fit_intent
    fit_admission = require_native_recipe_fit_intent(project, recipe, colliders, payload)
    from blender.piece_inventory import require_live
    require_live(project, component_id)
    from blender.fitting import recipe_fit
    fitting=recipe_fit(project,obj,payload,recipe)
    if fitting:context['fit_binding']=fitting['fit_binding']
    if scope=='full' and fitting and fitting['fit_status']=='INCOMPATIBLE':
        raise StudioError('Measured fitting deficit blocks full; propose a reviewed pattern variant before retrying')
    # Bind the trial to current geometry, rest, support weights, body pose and
    # physical recipe. Parameter tuning invalidates a TECHNICAL trial, not the
    # human approval of unmodified patterns.
    binding=trial_binding(obj,payload,recipe,phase,context)
    directory=project.data/'blender/sewing';directory.mkdir(parents=True,exist_ok=True)
    local_path=directory/(component_id+'-local.json')
    if scope=='full':
        if purpose!='assembly' and not any(c['role']=='mannequin' for c in recipe['colliders']):
            raise StudioError('Full garment trial needs the identified, measured auxiliary mannequin')
        from a3d.sewn_continuity import local_status
        latest=local_status(read_json(local_path) if local_path.is_file() else None,binding)
        current_local=latest=='PASS'
        current_failed=latest=='FAIL'
        if purpose=='assembly' and not current_local and not current_failed:
            from blender.sewn_stages import assembly_resume
            current_local=assembly_resume(project,obj,payload,recipe,phase)
        if not current_local:
            raise StudioError('Run the current local sleeve/armhole trial before a full toile')
    attempt_dir=directory/('attempt-'+uuid.uuid4().hex);attempt_dir.mkdir()
    # Record the measured mounting context before the first Cloth frame. It
    # survives a failed run, but cannot grant a local PASS or revise the cut.
    from blender.placement import placement_report
    placement_path=attempt_dir/'placement.json'
    atomic_json(placement_path,placement_report(obj,payload,recipe,context,trees,project.root))
    placement_ref={'path':placement_path.relative_to(project.root).as_posix(),'sha256':sha(placement_path)}
    progress_path=attempt_dir/'progress.json'
    counter_path=directory/(component_id+'-attempts.json')
    counters=read_json(counter_path) if counter_path.exists() else {'full_failures':0}
    if scope=='full' and counters['full_failures']>=2:
        raise StudioError('Two full attempts failed: diagnose and pass the local trial before another full run')
    target=obj
    diagnostic_ref=None
    execution_stage='backend_probe' if scope=='local' else 'garment'
    def save_diagnostic(data):
        nonlocal diagnostic_ref
        data.setdefault('execution_stage','garment')
        data.setdefault('garment_simulation','FAIL')
        data.setdefault('backend_probe_simulation','PASS' if scope=='local' else 'NOT_EXECUTED')
        data.update(schema_version=1,simulation='FAIL',accepted=False,visual_validation='NOT_EXECUTED',
            component_id=component_id,phase=phase,scope=scope,binding=binding,context=context,
            package_sha256=payload['package_sha256'],recipe_sha256=digest(recipe),recipe=recipe,
            boundary_map_sha256=obj['a3d_sewing_mesh_sha256'],source_garment_sha256=payload['source_garment_sha256'],placement=placement_ref,
            checkpoint=project.state().get('pending_blender_operation',{}).get('checkpoint'),fitting=fitting)
        path=attempt_dir/'diagnostic.json'
        from a3d.sewing_diagnostics import preview_svg
        preview=preview_svg(data)
        if preview:
            preview_path=attempt_dir/'diagnostic.svg'
            preview_path.write_text(preview,encoding='utf-8')
            data['preview']={'path':preview_path.relative_to(project.root).as_posix(),'sha256':sha(preview_path)}
        atomic_json(path,data)
        diagnostic_ref={'path':path.relative_to(project.root).as_posix(),'sha256':sha(path)}
    def save_probe_diagnostic(data,ref):
        data['probe_diagnostic']={'path':Path(ref['path']).relative_to(project.root).as_posix(),'sha256':ref['sha256']}
        save_diagnostic(data)
    original_scene_settings=(bpy.context.scene.frame_current,bpy.context.scene.frame_start,bpy.context.scene.frame_end,
        bpy.context.scene.render.fps,bpy.context.scene.render.fps_base,list(bpy.context.scene.gravity),bpy.context.scene.use_gravity)
    try:
        if scope=='local':
            probe_recipe=copy.deepcopy(recipe)
            # Backend coupons have no source panel IDs. They qualify uniform
            # integration only; the actual local garment executes regional groups.
            for profile in probe_recipe['phases'].values():profile.pop('regional_stiffness',None)
            if recipe['mass']['basis']=='total_kg':probe_recipe['mass']={'basis':'areal_density_kg_m2','value':recipe['mass']['value']/(payload['full_rest_area_cm2']/10000)}
            probes=backend_probes(probe_recipe,phase,attempt_dir/'backend-probes',failure_callback=save_probe_diagnostic)
            execution_stage='garment'
            local_payload=copy.deepcopy(payload)
            local_payload['placed_cm']=[[x*100 for x in p] for p in object_mesh(obj)[0]]
            local_payload=subset_mesh(local_payload,recipe['trial_pieces'])
            local_payload=fitting_tack_payload(local_payload,recipe,phase)
            # Disable original cloth collision: only the explicit collision
            # collection is used; the project mesh is preserved and not simulated.
            target=make_object(local_payload,'A3D.LocalTrial.'+uuid.uuid4().hex[:8])
            payload_for_run=local_payload
        else:payload_for_run=payload
        coords,report=simulate_object(target,payload_for_run,recipe,phase,colliders,trees,
            lambda rows:atomic_json(progress_path,{'frames':rows}),save_diagnostic)
        if context_colliders(recipe)[2]!=context['colliders']:
            raise StudioError('Auxiliary mannequin pose changed during simulation')
        report.update(fit_intent_admission=fit_admission,binding=binding,scope=scope,component_id=component_id,recipe_path=recipe_path,recipe_sha256=digest(recipe),
            context=context,package_sha256=payload['package_sha256'],trial_pieces=recipe['trial_pieces'],placement=placement_ref,
            fitting=fitting,fitting_tacks=payload_for_run.get('fitting_tacks',[]),
            qualification='CONSTRUCTION_FITTING_ONLY' if payload_for_run.get('fitting_tacks') else 'PHYSICS_ONLY')
        report.update(purpose=purpose,units='cm',boundary_map_sha256=obj['a3d_sewing_mesh_sha256'],
            source_vertex_indices=payload_for_run.get('source_vertex_indices',list(range(len(payload['rest_cm'])))),
            source_garment_sha256=payload['source_garment_sha256'])
        if scope=='local':
            report['backend_probes']=probes
            report['local_result_cm']=coords
            atomic_json(local_path,report)
            counters['full_failures']=0
        else:
            commit_positions(obj,coords)
            report['result_mesh_sha256']=mesh_digest(obj)
            report['result_cm']=coords
            if purpose=='assembly':report['qualification']='ASSEMBLY_PHYSICS_ONLY'
            report['boundary_map_sha256']=obj['a3d_sewing_mesh_sha256']
            atomic_json(directory/(component_id+'-full.json'),report)
        atomic_json(counter_path,counters);atomic_json(attempt_dir/'result.json',report)
        if scope=='full':
            obj['a3d_sewn_stage_result']=(attempt_dir/'result.json').relative_to(project.root).as_posix()
            obj['a3d_sewn_stage_result_sha256']=sha(attempt_dir/'result.json')
        if scope=='full':bpy.ops.wm.save_as_mainfile(filepath=session['working'],check_existing=False)
        return {'simulation':'PASS','scope':scope,'phase':phase,'report':(attempt_dir/'result.json').relative_to(project.root).as_posix(),
            'mass':report['mass'],'final_gap_cm':report['final_gap_cm'],'visual_validation':'NOT_EXECUTED'}
    except BaseException as exc:
        if scope=='full':counters['full_failures']+=1;atomic_json(counter_path,counters)
        outcome=getattr(exc,'simulation_outcome','FAIL')
        atomic_json(attempt_dir/'failure.json',{'error':str(exc),'scope':scope,'binding':binding,'simulation':outcome,
            'execution_stage':execution_stage,'backend_probe_simulation':outcome if execution_stage=='backend_probe' else 'PASS' if scope=='local' else 'NOT_EXECUTED',
            'garment_simulation':'NOT_EXECUTED' if execution_stage=='backend_probe' else outcome,
            'diagnostic':diagnostic_ref,'placement':placement_ref,'notes':getattr(exc,'__notes__',[])})
        if scope=='local':
            # Latest qualification is a projection; immutable prior attempt
            # results remain on disk, but a newer failed local cannot admit full.
            atomic_json(local_path,{'binding':binding,'simulation':outcome,'execution_stage':execution_stage,
                'diagnostic':diagnostic_ref,'garment_simulation':'NOT_EXECUTED' if execution_stage=='backend_probe' else outcome})
        raise
    finally:
        if scope=='local':
            if target!=obj and target.name in bpy.data.objects:bpy.data.objects.remove(target,do_unlink=True)
            sc=bpy.context.scene;frame,sc.frame_start,sc.frame_end,sc.render.fps,sc.render.fps_base,gravity,sc.use_gravity=original_scene_settings
            sc.gravity=gravity;sc.frame_set(frame)


def freeze_sewn(project_root,component_id,recipe_path):
    import bpy
    from blender.operations import working
    project,session=working(project_root)
    obj,payload,recipe=managed_inputs(project,component_id,recipe_path)
    if recipe.get('physics_purpose') == 'TEST_ONLY':
        raise StudioError('TEST_ONLY physics cannot become a production frozen fitting result')
    from a3d.physics_admission import require_recipe_fit_intent
    require_recipe_fit_intent(project, recipe)
    from blender.physics_admission import require_native_recipe_fit_intent
    colliders, _, _ = context_colliders(recipe)
    fit_admission = require_native_recipe_fit_intent(project, recipe, colliders, payload)
    if payload.get('rest_mode')=='assembled_3d':
        from blender.pattern_assembly import freeze_continuous
        return freeze_continuous(project,session,obj,payload,recipe)
    report_path=project.data/'blender/sewing'/(component_id+'-full.json')
    if not report_path.exists():raise StudioError('No completed full toile to freeze')
    report=read_json(report_path)
    if report.get('purpose')=='assembly':raise StudioError('Free assembly is not a fitting qualification; fit before freeze')
    from blender.fitting import recipe_fit
    fitting=recipe_fit(project,obj,payload,recipe)
    if fitting and (fitting['fit_status']=='INCOMPATIBLE' or (report.get('fitting') or {}).get('fit_binding')!=fitting['fit_binding']):
        raise StudioError('Fitting evidence changed or is incompatible; requalify before freeze')
    if report.get('simulation')!='PASS' or report.get('result_mesh_sha256')!=mesh_digest(obj) or report['recipe_sha256']!=digest(recipe) or report.get('boundary_map_sha256')!=obj['a3d_sewing_mesh_sha256']:
        raise StudioError('Full simulation evidence is stale')
    coords,faces=object_mesh(obj)
    vertices,new_faces,mapping,count=weld_permanent(coords,faces,payload['seams'],recipe['limits']['weld_gap_cm']/100)
    mesh=bpy.data.meshes.new('A3D.SewnSurface');mesh.from_pydata(vertices,[],new_faces);mesh.update()
    result=bpy.data.objects.new('A3D.Sewn.'+component_id,mesh);bpy.context.scene.collection.objects.link(result)
    result['a3d_component_id']=component_id;result['a3d_package_sha256']=payload['package_sha256'];result['a3d_role']='render'
    result['a3d_source_simulation']=obj.name
    from blender.piece_inventory import bind_frozen_map
    bind_frozen_map(project, result, payload, new_faces, vertices, mapping)
    obj['a3d_source_component_id']=component_id;del obj['a3d_component_id'];obj['a3d_role']='archived-simulation'
    obj.hide_set(True);obj.hide_render=True
    receipt={'operation':'freeze_sewn','component_id':component_id,'object':result.name,'vertices_before':len(coords),
        'vertices_after':len(vertices),'explicit_unions':count,'mapping':mapping,
        'preserved_links':[sid for sid,s in payload['seams'].items() if s['kind']!='permanent'],
        'source_simulation_report':report_path.relative_to(project.root).as_posix(),'source_simulation_sha256':sha(report_path),
        'fit_intent_admission':fit_admission,'visual_validation':'NOT_EXECUTED'}
    atomic_json(project.data/'blender/sewing'/(component_id+'-frozen.json'),receipt)
    bpy.ops.wm.save_as_mainfile(filepath=session['working'],check_existing=False)
    return {k:v for k,v in receipt.items() if k!='mapping'}
