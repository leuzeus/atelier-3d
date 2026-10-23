"""Call-local exact evaluated-body guard for anchor observations only.

The initial contact capture is authenticated by the legacy adapter. Subsequent
checks stream every evaluated coordinate and topology identity, without hashing
a second JSON surface or rebuilding world triangles. No geometry is cached in
place of native evaluation, and no collision query or BVH is replaced.
"""
from dataclasses import dataclass
import math

from a3d.core import StudioError


def _immutable(value):
    if type(value) is dict:
        return (dict,tuple((key,_immutable(child)) for key,child in sorted(value.items())))
    if type(value) in (list,tuple):return (type(value),tuple(_immutable(child) for child in value))
    if type(value) not in (str,int,float,bool,type(None)):
        raise StudioError('Contact body identity requires finite structured data')
    if type(value) is float and not math.isfinite(value):
        raise StudioError('Contact body identity requires finite structured data')
    return (type(value),value)


def _equal(value,expected):
    kind,data=expected
    if type(value) is not kind:return False
    if kind is dict:
        return len(value)==len(data) and all(key in value and _equal(value[key],child) for key,child in data)
    if kind in (list,tuple):
        return len(value)==len(data) and all(_equal(a,b) for a,b in zip(value,data))
    return value==data


def _rows(value):return tuple(tuple(row) for row in value)


def _same_rows(value,expected):
    return len(value)==len(expected) and all(tuple(row)==target for row,target in zip(value,expected))


@dataclass(frozen=True,slots=True)
class _ContactBodyIdentity:
    expected:tuple
    seal:tuple
    handles:tuple
    handles_seal:tuple
    collision:tuple
    collision_seal:tuple


def create_contact_body_identity(context,binding,plan,authenticate):
    """Initialize only inside the observation wrapper and its budget clock.

    Tests or older objects lacking the complete native evaluated-mesh API retain
    the unchanged legacy path. A real native authentication failure propagates
    to the observation wrapper; it is never treated as an API fallback.
    """
    bodies=authenticate(context,binding)
    if any(not callable(getattr(body['object'],'evaluated_get',None)) for body in bodies):return None
    expected=[];handles=[]
    for body in bodies:
        geometry=binding['canonical_geometry']
        expected_view={'object':body['name'],'dimensions_cm':[
            max(p[k] for p in geometry['vertices_cm'])-min(p[k] for p in geometry['vertices_cm']) for k in range(3)]}
        if body['snapshot']!=expected_view:
            raise StudioError('Anchor reserve contact dimensions differ from the authenticated body')
        expected.append((body['name'],body['sha256'],_rows(geometry['vertices_cm']),
            _rows(geometry['faces']),tuple(geometry['face_sets']),_rows(body['faces']),tuple(body['polygons']),
            tuple(tuple(tuple(point) for point in triangle) for triangle in body['triangles']),
            _immutable(body['snapshot']),_immutable(body['closed']),_immutable(body['orientation_issues']),
            binding['profile_cache_key']))
        handles.append((body['object'],body['tree']))
    snapshot=tuple(expected)
    # Independent immutable structure detects field replacement even if frozen
    # dataclass attributes are deliberately bypassed. Its leaves are immutable.
    seal=tuple((name,sha,_rows(points),_rows(polygons),tuple(v for v in labels),_rows(triangles),
        tuple(v for v in owners),tuple(tuple(tuple(v for v in point) for point in tri) for tri in world),
        _copy_immutable(view),_copy_immutable(closed),_copy_immutable(issues),cache)
        for name,sha,points,polygons,labels,triangles,owners,world,view,closed,issues,cache in snapshot)
    collision=_immutable(plan['collision'])
    return _ContactBodyIdentity(snapshot,seal,tuple(handles),tuple((obj,tree) for obj,tree in handles),
                                collision,_copy_immutable(collision))


def _copy_immutable(value):
    return tuple(_copy_immutable(v) for v in value) if type(value) is tuple else value


def verify_contact_body_identity(context,binding,plan,guard,*,expected_guard=None):
    """Check the actual query buffers and every evaluated source identity."""
    if (type(guard) is not _ContactBodyIdentity or
            (expected_guard is not None and guard is not expected_guard) or
            guard.expected!=guard.seal or guard.collision!=guard.collision_seal or
            len(guard.handles)!=len(guard.handles_seal) or
            any(a is not c or b is not d for (a,b),(c,d) in zip(guard.handles,guard.handles_seal)) or
            not _equal(plan['collision'],guard.collision)):
        raise StudioError('Anchor reserve private contact identity or collision plan changed')
    bodies=context['bodies']
    if len(bodies)!=len(guard.expected) or len(guard.handles)!=len(bodies):
        raise StudioError('Anchor reserve contact body inventory changed')
    import bpy
    for body,expected,handles in zip(bodies,guard.expected,guard.handles):
        name,sha,points,polygons,labels,triangles,owners,world,view,closed,issues,cache=expected
        obj,tree=handles
        if (body['object'] is not obj or body['tree'] is not tree or body['name']!=name or body['sha256']!=sha or
                not _same_rows(body['coords'],points) or not _same_rows(body['faces'],triangles) or
                tuple(body['polygons'])!=owners or len(body['triangles'])!=len(world) or
                any(not _same_rows(tri,target) for tri,target in zip(body['triangles'],world)) or
                not _equal(body['snapshot'],view) or not _equal(body['closed'],closed) or
                not _equal(body['orientation_issues'],issues) or
                obj.type!='MESH' or obj.name!=name or name not in binding['collider_names'] or
                bpy.data.objects.get(name) is not obj or
                obj.get('a3d_profile_cache_key')!=cache or cache!=binding['profile_cache_key']):
            raise StudioError('Anchor reserve captured contact buffers or collider identity changed')
        evaluated=obj.evaluated_get(bpy.context.evaluated_depsgraph_get())
        try:
            mesh=evaluated.to_mesh()
            source_labels=mesh.attributes.get('.sculpt_face_set')
            if (not source_labels or source_labels.domain!='FACE' or source_labels.data_type!='INT' or
                    len(mesh.vertices)!=len(points) or len(mesh.polygons)!=len(polygons) or
                    len(source_labels.data)!=len(labels)):
                raise StudioError('Anchor reserve evaluated source topology or regions changed')
            for vertex,expected_point in zip(mesh.vertices,points):
                point=tuple(float(x)*100 for x in evaluated.matrix_world@vertex.co)
                if not all(math.isfinite(x) for x in point) or point!=expected_point:
                    raise StudioError('Anchor reserve actual evaluated body coordinates changed')
            if (any(tuple(face.vertices)!=target for face,target in zip(mesh.polygons,polygons)) or
                    any(value.value!=target for value,target in zip(source_labels.data,labels))):
                raise StudioError('Anchor reserve actual evaluated body faces or regions changed')
            mesh.calc_loop_triangles()
            if len(mesh.loop_triangles)!=len(triangles):
                raise StudioError('Anchor reserve evaluated contact triangulation changed')
            if any(tuple(tri.vertices)!=target or tri.polygon_index!=owner
                   for tri,target,owner in zip(mesh.loop_triangles,triangles,owners)):
                raise StudioError('Anchor reserve evaluated triangle ordering, winding or ownership changed')
        finally:evaluated.to_mesh_clear()
    return bodies
