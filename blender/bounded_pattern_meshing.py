"""Opt-in bounded pattern triangulation; caller owns work, clock and admission.

Safeguards and numeric arithmetic derive from frozen native V4. No production
caller is switched by importing this module. Only a supplied envelope can run it.
"""
import copy
import hashlib
import json
import math
from a3d.core import StudioError
from a3d.sewing import distance, point_inside, segment_distance, signed_area
from a3d.mesh_refinement import improve_interior

DISCRIMINANT = "BOUNDED_PATTERN_MESHING_V1"
FROZEN_KERNEL_SHA256 = "815922eb0fe5173653fe5e0aa2ecdbbd93ac64b6f7f37c41605acc5af6232f70"

class ConditionedPointRefusal(ValueError):
    def __init__(self, reason, **diagnostic):
        self.reason = reason
        self.diagnostic = diagnostic
        super().__init__(reason)


def _pool_digest(value):
    return hashlib.sha256(json.dumps(value, sort_keys=True, allow_nan=False,
        separators=(',', ':')).encode('utf-8')).hexdigest()


def exact_input_association(origins, input_count, output_count):
    if output_count != len(origins):
        raise ConditionedPointRefusal('INCOMPLETE_INPUT_IDENTITY')
    association = {}
    for output_id, input_ids in enumerate(origins):
        if not isinstance(input_ids, (list, tuple)) or len(input_ids) != 1:
            raise ConditionedPointRefusal('AMBIGUOUS_INPUT_IDENTITY', output_id=output_id,
                alias_count=len(input_ids) if isinstance(input_ids, (list, tuple)) else None)
        input_id = input_ids[0]
        if (isinstance(input_id, bool) or not isinstance(input_id, int)
                or input_id < 0 or input_id >= input_count or input_id in association):
            raise ConditionedPointRefusal('INVALID_OR_DUPLICATE_INPUT_IDENTITY', output_id=output_id)
        association[input_id] = output_id
    if len(association) != input_count or set(association) != set(range(input_count)):
        raise ConditionedPointRefusal('MISSING_INPUT_IDENTITY')
    return association


def validate_conditioned_pool(points, births, coordinates, origins, faces, polygon,
                              vector, inside_polygon, area, max_displacement, check=None):
    """Associate by exact input IDs, then validate actual transported geometry.

    No coordinate search, alias resolution, projection, threshold relaxation or
    admission takes place here. Births are permanent, including after remesh.
    """
    if check is not None:check("bounded_meshing:transport_before_capture")
    count, protected = len(points), len(polygon)
    if len(births) != count:
        raise ConditionedPointRefusal('INCOMPLETE_INPUT_IDENTITY')
    if not math.isfinite(max_displacement) or max_displacement < 0:
        raise ConditionedPointRefusal('INVALID_DISPLACEMENT_BUDGET')
    association = exact_input_association(origins, count, len(coordinates))
    carried = [None] * count
    carried_output = [None] * len(coordinates)
    maximum = 0.
    for input_id in range(count):
        if check is not None:check("bounded_meshing:transport_input")
        output_id = association[input_id]
        coordinate = coordinates[output_id]
        if (len(coordinate) != 2 or len(births[input_id]) != 2
                or any(not math.isfinite(v) for v in coordinate)
                or any(not math.isfinite(v) for v in births[input_id])):
            raise ConditionedPointRefusal('NONFINITE_OR_INVALID_COORDINATE', input_id=input_id)
        if input_id < protected:
            if list(coordinate) != list(polygon[input_id]):
                raise ConditionedPointRefusal('CHANGED_PROTECTED_SOURCE', input_id=input_id)
            value = vector(points[input_id])
            if list(value) != list(vector(polygon[input_id])):
                raise ConditionedPointRefusal('CHANGED_PROTECTED_CARRIER', input_id=input_id)
        else:
            value = vector(coordinate)
            actual = list(value)
            if any(not math.isfinite(v) for v in actual):
                raise ConditionedPointRefusal('NONFINITE_VECTOR_TRANSPORT', input_id=input_id)
            if not inside_polygon(actual, polygon):
                raise ConditionedPointRefusal('TRANSPORTED_INTERIOR_OUTSIDE_SOURCE', input_id=input_id)
            displacement = max(math.dist(coordinate, births[input_id]),
                               math.dist(actual, births[input_id]))
            if displacement > max_displacement:
                raise ConditionedPointRefusal('CUMULATIVE_DISPLACEMENT_BUDGET_EXCEEDED',
                    input_id=input_id, displacement_cm=displacement,
                    max_displacement_cm=max_displacement)
            maximum = max(maximum, displacement)
        carried[input_id] = value
        carried_output[output_id] = list(value)
    if len({tuple(v) for v in carried_output}) != len(carried_output):
        raise ConditionedPointRefusal('TRANSPORT_COLLAPSED_INPUTS')
    for face_id, face in enumerate(faces):
        if check is not None:check("bounded_meshing:transport_face")
        if (len(face) != 3 or len(set(face)) != 3
                or any(isinstance(i, bool) or not isinstance(i, int)
                       or i < 0 or i >= len(coordinates) for i in face)):
            raise ConditionedPointRefusal('INVALID_DERIVED_TRIANGLE', face_id=face_id)
        exact_area = area([coordinates[i] for i in face])
        carried_area = area([carried_output[i] for i in face])
        if (not math.isfinite(exact_area) or not math.isfinite(carried_area)
                or exact_area * carried_area <= 0):
            raise ConditionedPointRefusal('TRANSPORT_INVERTED_OR_COLLAPSED_TRIANGLE', face_id=face_id)
    if not faces:
        raise ConditionedPointRefusal('NO_DERIVED_TRIANGLES')
    if check is not None:check("bounded_meshing:transport_before_hashes")
    return carried, {'input_count':count, 'protected_input_count':protected,
        'interior_count':count-protected, 'maximum_cumulative_displacement_cm':maximum,
        'max_displacement_cm':max_displacement, 'identity_policy':'ONE_OUTPUT_PER_EXACT_INPUT_ID',
        'input_to_output':association,
        'pool_sha256':_pool_digest([list(v) for v in carried]),
        'births_sha256':_pool_digest(births), 'coordinates_sha256':_pool_digest(coordinates),
        'origins_sha256':_pool_digest(origins)}


def snapshot_candidate(verts, edges, faces, origins, coordinates, mapping, smoothing,
                       points, births, added, passes, angle, edge):
    return copy.deepcopy({'triangulation':(verts, edges, faces, origins),
        'coordinates':coordinates, 'mapping':mapping, 'smoothing':smoothing,
        'points':points, 'births':births, 'added_vertices':added, 'passes':passes,
        'min_angle_degrees':angle, 'min_edge_cm':edge})


def restore_candidate(snapshot):
    """Return a complete independent state; never return global work counters."""
    return copy.deepcopy(snapshot)


def separated_from_transported(value, transported, insertions, separation, distance):
    return all(distance(value, p) >= separation for p in transported + insertions)


def final_quality_reached(faces, angle, edge, target_angle, min_edge, transport_refusal):
    return bool(faces) and not transport_refusal and angle >= target_angle and edge >= min_edge


class _EnvelopePointWork:
    """Local safety/statistics only; all attempted work belongs to the caller."""
    def __init__(self,envelope,owner,max_remesh,max_inserted,max_points,initial_charge):
        self.envelope,self.owner=envelope,owner
        self.max_remesh,self.max_inserted,self.max_points=max_remesh,max_inserted,max_points
        self.cdt_calls=self.remesh_attempts=0
        self.attempted_insertions=initial_charge
        self.last_cdt_input_sha256=None

    def before_cdt(self,points,ids):
        self.envelope.check('bounded_meshing:before_cdt_reservation')
        if len(points)>self.max_points:raise ConditionedPointRefusal('POINT_BUDGET_EXHAUSTED')
        key=_pool_digest({'points':[list(p) for p in points],'constraints':ids})
        self.envelope.check('bounded_meshing:after_cdt_input_hash')
        if key==self.last_cdt_input_sha256:raise ConditionedPointRefusal('UNCHANGED_CDT_INPUT_REFUSED')
        if self.cdt_calls>=self.max_remesh+1:raise ConditionedPointRefusal('CDT_CALL_BUDGET_EXHAUSTED')
        self.envelope.reserve('native_point_slots',len(points),owner=self.owner)
        self.envelope.reserve('native_cdt_calls',1,owner=self.owner)
        self.cdt_calls+=1
        self.last_cdt_input_sha256=key

    def can_reserve(self,existing_count,proposed_count):
        self.envelope.check('bounded_meshing:insertion_preflight')
        state=self.envelope.snapshot()
        return (self.remesh_attempts<self.max_remesh
            and self.attempted_insertions+proposed_count<=self.max_inserted
            and existing_count+proposed_count<=self.max_points
            and state['work'].get('attempted_insertions',0)+proposed_count<=state['limits']['attempted_insertions'])

    def reserve_remesh(self,existing_count,proposed_count):
        if proposed_count<=0:raise ConditionedPointRefusal('EMPTY_REMESH_REFUSED')
        if not self.can_reserve(existing_count,proposed_count):
            raise ConditionedPointRefusal('ATTEMPTED_REFINEMENT_BUDGET_EXHAUSTED')
        self.envelope.reserve('attempted_insertions',proposed_count,owner=self.owner)
        self.envelope.reserve('native_remesh_attempts',1,owner=self.owner)
        self.remesh_attempts+=1
        self.attempted_insertions+=proposed_count

    def report(self):
        return {'cdt_calls':self.cdt_calls,'remesh_attempts':self.remesh_attempts,
            'attempted_insertions':self.attempted_insertions,
            'max_cdt_calls':self.max_remesh+1,'max_remesh_attempts':self.max_remesh,
            'max_attempted_insertions':self.max_inserted,'max_points':self.max_points,
            'last_cdt_input_sha256':self.last_cdt_input_sha256,
            'rollback_refunds_attempted_work':False}


def _triangulate(boundary, recipe, regular_mesh, *, envelope, _state):
    if not all(callable(getattr(envelope,name,None)) for name in ('check','reserve','snapshot')):
        raise ConditionedPointRefusal('INVALID_ENVELOPE_PROTOCOL')
    check=envelope.check
    check('bounded_meshing:before_capture')
    if type(boundary) is not dict or type(recipe) is not dict:
        raise ConditionedPointRefusal('INVALID_BOUNDARY_OR_RECIPE')
    owner=boundary.get('piece_id')
    if type(owner) is not str or not owner:
        raise ConditionedPointRefusal('EXPLICIT_PIECE_OWNER_REQUIRED')
    controls=envelope.material_controls
    if owner not in controls or type(controls[owner]) is not int:
        raise ConditionedPointRefusal('INITIAL_MATERIAL_CONTROLS_NOT_RESERVED')
    initial_charge=controls[owner]
    if (type(boundary.get('polygon')) is not list or not 3<=len(boundary['polygon'])<=30000
        or type(boundary.get('source')) is not list or len(boundary['source'])<3):
        raise ConditionedPointRefusal('INVALID_SOURCE_CONTOUR')
    for point in boundary['polygon']+boundary['source']:
        check('bounded_meshing:source_coordinate')
        if (type(point) not in (list,tuple) or len(point)!=2
            or any(type(v) not in (int,float) or not math.isfinite(v) for v in point)):
            raise ConditionedPointRefusal('INVALID_SOURCE_CONTOUR')
    refinement_input=recipe['mesh'].get('quality_refinement')
    if (type(regular_mesh) is not dict or not regular_mesh or type(refinement_input) is not dict
        or type(refinement_input.get('max_passes')) is not int or not 0<=refinement_input['max_passes']<=8
        or type(refinement_input.get('max_added_vertices')) is not int or not 0<=refinement_input['max_added_vertices']<=4000
        or type(recipe['mesh'].get('max_vertices')) is not int or not 0<recipe['mesh']['max_vertices']<=30000
        or type(regular_mesh.get('max_vertices')) is not int or not 0<regular_mesh['max_vertices']<=30000
        or type(regular_mesh.get('min_spacing_cm')) not in (int,float)
        or not math.isfinite(regular_mesh['min_spacing_cm']) or not 0<regular_mesh['min_spacing_cm']<=1
        or not 0<=initial_charge<=refinement_input['max_added_vertices']
        or initial_charge>len(boundary['polygon'])):
        raise ConditionedPointRefusal('INVALID_HISTORICAL_MESHING_CAPS')
    entry=envelope.snapshot()
    prior=entry['owner_work'].get(owner,{})
    if (entry.get('material_controls',{}).get(owner)!=initial_charge
        or prior.get('attempted_insertions',0)<initial_charge
        or entry['work'].get('attempted_insertions',0)<sum(controls.values())
        or not all(type(entry['limits'].get(kind)) is int and entry['limits'][kind]>=0
            for kind in ('attempted_insertions','native_cdt_calls','native_remesh_attempts','native_point_slots'))):
        raise ConditionedPointRefusal('INITIAL_MATERIAL_CONTROL_LEDGER_CONTRADICTION')
    if any(prior.get(kind,0) for kind in ('native_cdt_calls','native_remesh_attempts','native_point_slots')):
        raise ConditionedPointRefusal('PIECE_WORK_ALREADY_STARTED_NO_BIRTH_RESET')
    input_identity=_pool_digest({k:v for k,v in boundary.items() if k!='preparation_refinement'})
    recipe_identity=_pool_digest(recipe)
    regular_identity=_pool_digest(regular_mesh)
    check('bounded_meshing:after_capture_hashes')
    from mathutils import Vector
    from mathutils.geometry import delaunay_2d_cdt
    polygon=boundary["polygon"]
    check("bounded_meshing:before_pool_capture")
    spacing=recipe["mesh"]["spacing_cm"]
    points=[Vector(p) for p in polygon]
    xmin,xmax=min(p[0] for p in polygon),max(p[0] for p in polygon)
    ymin,ymax=min(p[1] for p in polygon),max(p[1] for p in polygon)
    nx,ny=math.ceil((xmax-xmin)/spacing),math.ceil((ymax-ymin)/spacing)
    if nx*ny>recipe["mesh"]["max_vertices"]*4:
        raise StudioError("Interior grid exceeds the declared mesh budget")
    if regular_mesh:
        from a3d.pattern_preparation import regular_interior_points
        check("bounded_meshing:before_interior_grid")
        interior,_=regular_interior_points(boundary,regular_mesh)
        check("bounded_meshing:after_interior_grid")
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
    births=[list(p) for p in points]
    vertex_budget=min(recipe['mesh']['max_vertices'],regular_mesh['max_vertices'] if regular_mesh else recipe['mesh']['max_vertices'])
    work=_EnvelopePointWork(envelope,owner,refinement["max_passes"],
        refinement["max_added_vertices"],vertex_budget,initial_charge)
    trace_history=[]
    def _trace_conditioned(phase, points, births, coordinates=None, origins=None,
                           faces=None, mapping=None, **scalar):
        _state['last_completed_work_snapshot']=scalar.get('work',_state.get('last_completed_work_snapshot'))
        check('bounded_meshing:trace:'+phase)
        trace_history.append({'phase':phase,'input_count':len(points),
            'pool_sha256':_pool_digest([list(v) for v in points]),
            'births_sha256':_pool_digest(births),'scalar':copy.deepcopy(scalar)})
        check('bounded_meshing:trace_after_hash:'+phase)
    _trace_conditioned('DERIVED_BOUNDARY_INITIAL_LEDGER',points,births,
        initial_derived_boundary_insertions=initial_charge,work=work.report())
    transport_refusal=None;transport_history=[];final_transport=None
    def angle(face,points_override=None):
        values=verts if points_override is None else points_override
        lengths=[distance(values[a],values[b]) for a,b in zip(face,face[1:]+face[:1])]
        if min(lengths)<1e-10:return 0.
        return min(math.degrees(math.acos(max(-1.,min(1.,(x*x+y*y-z*z)/(2*x*y)))))
            for x,y,z in ((lengths[0],lengths[1],lengths[2]),(lengths[1],lengths[2],lengths[0]),(lengths[2],lengths[0],lengths[1])))
    def exact_source_coordinates(vertices,triangles,origins):
        check("bounded_meshing:exact_source_restoration")
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
    def restore_best():
        state=restore_candidate(best)
        return (state['triangulation'],state['coordinates'],state['mapping'],state['smoothing'],
            state['points'],state['births'],state['added_vertices'],state['passes'])

    while True:
        check("bounded_meshing:before_cdt")
        work.before_cdt(points,ids)
        _trace_conditioned('CDT_INPUT',points,births,work=work.report())
        verts,edges,faces,orig,_,_=delaunay_2d_cdt(points,[],[ids],1,1e-6,True)
        check("bounded_meshing:after_cdt")
        if not refinement:break
        candidate_pool=points
        if regular_mesh:
            # Resolve every input identity before smoothing or exact restoration;
            # missing/aliased protected IDs must also preserve the complete best.
            try:
                exact_input_association(orig,len(points),len(verts))
            except ConditionedPointRefusal as error:
                transport_refusal={'reason':error.reason,**error.diagnostic}
                _trace_conditioned('CDT_IDENTITY_REFUSED',points,births,[list(v) for v in verts],orig,faces,
                    refusal=transport_refusal,work=work.report())
                if best is None:raise
                (verts,edges,faces,orig),coordinates,mapping,smoothing,points,births,added,passes=restore_best()
                refusal=error.reason;break
            raw_angle=min((angle(f) for f in faces),default=0.)
            anchors={i for i,inputs in enumerate(orig) if any(j<len(polygon) for j in inputs)}
            # The existing per-call conditioner and its budgets are unchanged.
            improved,smoothing=improve_interior([list(v) for v in verts],faces,anchors,
                target_angle=refinement['target_min_angle_degrees'],min_edge=recipe['mesh']['min_edge_cm'],
                max_displacement=regular_mesh['min_spacing_cm']*.5,
                displacement_reference=[births[input_ids[0]] for input_ids in orig],check=envelope.check)
            check("bounded_meshing:after_conditioner")
            verts=[Vector(p) for p in improved]
            coordinates,mapping=exact_source_coordinates(verts,faces,orig)
            try:
                candidate_pool,transport=validate_conditioned_pool(points,births,coordinates,orig,faces,polygon,
                    Vector,point_inside,signed_area,regular_mesh['min_spacing_cm']*.5,check=envelope.check)
            except ConditionedPointRefusal as error:
                transport_refusal={'reason':error.reason,**error.diagnostic}
                _trace_conditioned('CANDIDATE_REFUSED',points,births,coordinates,orig,faces,mapping,
                    refusal=transport_refusal,work=work.report())
                if best is None:raise
                (verts,edges,faces,orig),coordinates,mapping,smoothing,points,births,added,passes=restore_best()
                refusal=error.reason;break
            transport_history.append(transport)
            _trace_conditioned('CANDIDATE_VALIDATED',candidate_pool,births,coordinates,orig,faces,mapping,
                transport=transport,work=work.report())
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
                (verts,edges,faces,orig),coordinates,mapping,smoothing,points,births,added,passes=restore_best()
                refusal='NON_MONOTONIC_REFINEMENT_ROLLED_BACK';break
            conditioning['decision']='BEST_CONDITIONED_CANDIDATE_PRESERVED'
            best=snapshot_candidate(verts,edges,faces,orig,coordinates,mapping,smoothing,
                candidate_pool,births,added,passes,measured_angle,measured_edge)
            _state["best_safe_candidate"]=best
            _trace_conditioned('BEST_CANDIDATE_PRESERVED',candidate_pool,births,coordinates,orig,faces,mapping,
                smoothing=smoothing,conditioning=conditioning,work=work.report())
        bad=[f for f in faces if angle(f,coordinates if regular_mesh else None)<refinement['target_min_angle_degrees']]
        if not bad:break
        if work.remesh_attempts>=refinement['max_passes']:
            if regular_mesh:
                refusal='PASS_BUDGET_EXHAUSTED';break
            error=StudioError('Derived mesh refinement did not reach the declared angle target within its pass budget')
            error.refinement_metrics={'min_angle_degrees':min(angle(f) for f in faces),'bad_faces':len(bad),
                'added_vertices':added,'source_polygon':boundary['source'],
                'examples':[[list(verts[i]) for i in f] for f in bad[:5]]}
            raise error
        existing={(round(v.x,6),round(v.y,6)) for v in candidate_pool};insert=[];insertion_checks=[];budget_exhausted=False
        for face in bad:
            check("bounded_meshing:insertion_candidate")
            a,b=min(((verts[a],verts[b]) for a,b in zip(face,face[1:]+face[:1])),key=lambda p:distance(*p))
            d=b-a;mid=(a+b)*.5;normal=Vector((-d.y,d.x))
            opposite=next(verts[i] for i in face if verts[i]!=a and verts[i]!=b)
            if normal.dot(opposite-mid)<0:normal=-normal
            value=mid+normal*math.sqrt(3)/2
            tri=[verts[i] for i in face]
            x,y,z=tri
            # Exact frozen stable-centre arithmetic and transport are retained.
            ux,uy=float(y.x)-float(x.x),float(y.y)-float(x.y)
            vx,vy=float(z.x)-float(x.x),float(z.y)-float(x.y)
            det=2*(ux*vy-uy*vx)
            if abs(det)>1e-12:
                uu,vv=ux*ux+uy*uy,vx*vx+vy*vy
                center=Vector((float(x.x)+(uu*vy-vv*uy)/det,
                    float(x.y)+(ux*vv-vx*uu)/det))
                if point_inside(center,polygon):value=center
            inside_face=all((v.x-u.x)*(value.y-u.y)-(v.y-u.y)*(value.x-u.x)>=-1e-9
                for u,v in zip(tri,tri[1:]+tri[:1]))
            if not inside_face and not point_inside(value,polygon):value=sum(tri,Vector((0.,0.)))/3
            key=(round(value.x,6),round(value.y,6))
            if key not in existing and point_inside(value,polygon):
                separation=None
                if regular_mesh:
                    separation=max(recipe['mesh']['min_edge_cm'],distance(a,b)*.2)
                    if not separated_from_transported(value,candidate_pool,insert,separation,distance):continue
                    if min(segment_distance(value,u,v) for u,v in zip(polygon,polygon[1:]+polygon[:1]))<separation:continue
                if not work.can_reserve(len(candidate_pool),len(insert)+1):
                    budget_exhausted=True;break
                existing.add(key);insert.append(value)
                insertion_checks.append({'input_id':len(candidate_pool)+len(insert)-1,
                    'separation_cm':separation,'point_cm':list(value)})
        if budget_exhausted:
            refusal='VERTEX_BUDGET_EXHAUSTED';break
        if not insert:
            if regular_mesh:
                refusal='REFINEMENT_STALLED';break
            raise StudioError('Derived refinement stalled; source boundary anchors remain unchanged')
        work.reserve_remesh(len(candidate_pool),len(insert))
        # Transport only at an existing, admitted insertion/remesh boundary.
        points=[Vector(v) for v in candidate_pool]
        points.extend(insert);births.extend(list(v) for v in insert)
        added+=len(insert);passes+=1
        _trace_conditioned('REMESH_RESERVED',points,births,coordinates,orig,faces,mapping,
            inserted=insertion_checks,work=work.report())
    coordinates,mapping=exact_source_coordinates(verts,faces,orig)
    if regular_mesh:
        # Revalidate the exact final returned candidate, including cumulative
        # displacement after Vector transport. No last-call exemption exists.
        final_pool,final_transport=validate_conditioned_pool(points,births,coordinates,orig,faces,polygon,
            Vector,point_inside,signed_area,regular_mesh['min_spacing_cm']*.5,check=envelope.check)
        _trace_conditioned('FINAL_CANDIDATE',final_pool,births,coordinates,orig,faces,mapping,
            transport=final_transport,transport_refusal=transport_refusal,work=work.report())
        final_angle=min((angle(f,coordinates) for f in faces),default=0.)
        final_edge=min((distance(coordinates[a],coordinates[b]) for f in faces for a,b in zip(f,f[1:]+f[:1])),default=0.)
        check("bounded_meshing:before_final_quality")
        if final_quality_reached(faces,final_angle,final_edge,refinement['target_min_angle_degrees'],
                recipe['mesh']['min_edge_cm'],transport_refusal):refusal=None
        elif refusal is None:refusal='INTERIOR_QUALITY_TARGET_NOT_REACHED'
        report={'status':'NEEDS_CORRECTION' if refusal else 'TARGET_REACHED',
            'refusal':refusal,'target_min_angle_degrees':refinement['target_min_angle_degrees'],
            'min_angle_degrees':final_angle,'min_edge_cm':final_edge,'passes':passes,'added_vertices':added,
            'max_passes':refinement['max_passes'],'max_added_vertices':refinement['max_added_vertices'],
            'source_anchors_changed':False,'rejected_candidate':rejected_candidate,
            'interior_smoothing':smoothing,
            'conditioning_policy':'BOUNDED_CUMULATIVE_INPUT_ID_TRANSPORT_AT_EXISTING_REMESH_BOUNDARIES',
            'conditioning_history':conditioning_history,'best_safe_candidate_preserved':True,
            'conditioned_point_transport':{'qualification':'NONE','work':work.report(),
                'refusal':transport_refusal,'history':transport_history,'final':final_transport},
            'bad_faces':[list(f) for f in faces if angle(f,coordinates)<refinement['target_min_angle_degrees']]}
    if bool(boundary["flip"]) ^ (signed_area(boundary["source"])<0):
        faces=[list(reversed(f)) for f in faces]
    check('bounded_meshing:before_final_source_preservation')
    if (_pool_digest({k:v for k,v in boundary.items() if k!='preparation_refinement'})!=input_identity
        or _pool_digest(recipe)!=recipe_identity or _pool_digest(regular_mesh)!=regular_identity
        or envelope.material_controls.get(owner)!=initial_charge):
        raise ConditionedPointRefusal('SOURCE_OR_RECIPE_MUTATED')
    check('bounded_meshing:after_final_source_hashes')
    report.update(discriminant=DISCRIMINANT,purpose='NUMERICAL_PREPARATION',qualification='NONE',
        admission='NONE',physical_mesh_qualified=False,piece_id=owner,
        source_input_sha256=input_identity,recipe_sha256=recipe_identity,
        regular_mesh_sha256=regular_identity,frozen_kernel_sha256=FROZEN_KERNEL_SHA256,
        initial_material_controls_already_reserved=initial_charge,
        envelope=envelope.snapshot(),trace_history=trace_history,
        component_live_vertices_checked_by='CALLER_BUILD_MESH',costs_refunded=False)
    check('bounded_meshing:final_return')
    boundary['preparation_refinement']=report
    return coordinates,faces,mapping


def triangulate(boundary, recipe, regular_mesh, *, envelope):
    """Return a numerical candidate; all admission remains with the caller.

    An interrupted/refused operation retains its last already-snapshotted safe
    candidate on the exception, without copying/rechecking after its deadline.
    That diagnostic is NONE and does not turn an expired operation into success.
    """
    state={}
    try:
        return _triangulate(boundary,recipe,regular_mesh,envelope=envelope,_state=state)
    except Exception as error:
        try:
            error.bounded_meshing_partial={'qualification':'NONE','admission':'NONE',
                'best_safe_candidate':state.get('best_safe_candidate'),
                'last_completed_work_snapshot':state.get('last_completed_work_snapshot'),
                'snapshot_scope':'LAST_COMPLETED_CHECKPOINT_NOT_FINAL_WORK_LEDGER',
                'costs_refunded':False}
        except (AttributeError,TypeError):
            pass
        raise
