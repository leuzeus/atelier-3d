"""Read-only native inspection of the current, unsimulated pattern placement."""
from a3d.core import StudioError, digest, inside, read_json
from a3d.sewing_placement import placement_geometry


def placement_report(obj, payload, recipe, context, trees, project_root):
    import bpy
    from mathutils import Vector
    from blender.sewing import mesh_digest, object_mesh
    coords = [[x*100 for x in p] for p in object_mesh(obj)[0]]

    def nearest(point):
        p = Vector([x/100 for x in point]); rows = []
        for tree, collider in zip(trees, context['colliders'], strict=True):
            hit, normal, face, dist = tree.find_nearest(p)
            if hit is not None:
                rows.append({'object': collider['object'], 'face': face, 'point_cm': [x*100 for x in hit],
                    'normal': list(normal), 'distance_cm': dist*100, 'signed_offset_cm': (p-hit).dot(normal)*100})
        return rows

    def crossings(a, b):
        start, end = (Vector([x/100 for x in p]) for p in (a, b)); delta = end-start
        length = delta.length; epsilon = 1e-6  # meters; ignore coincident seam endpoints
        if length <= 2*epsilon:
            return []
        direction = delta/length; rows = []
        for tree, collider in zip(trees, context['colliders'], strict=True):
            hit, normal, face, dist = tree.ray_cast(start+direction*epsilon, direction, length-2*epsilon)
            if hit is not None:
                rows.append({'object': collider['object'], 'face': face, 'first_hit_cm': [x*100 for x in hit],
                    'normal': list(normal), 'distance_from_a_cm': (dist+epsilon)*100})
        return rows

    # Existing derived maps preserve paired samples but may omit the original
    # named-edge fields. Read them from the already verified source garment;
    # never rewrite an old mapping to add diagnostic metadata.
    data = read_json(inside(project_root, payload['source_garment']))
    source_seams = {s['id']: s for s in data['seams']}
    mapped = {**payload, 'seams': {sid: {**seam, 'edge_a': source_seams[sid]['edge_a'],
        'edge_b': source_seams[sid]['edge_b']} for sid, seam in payload['seams'].items()}}
    report = placement_geometry(mapped, coords, recipe, nearest, crossings)
    from a3d.garment_rejections import seam_directions
    report['directions']=seam_directions(payload,coords,data)
    report.update(schema_version=1, component_id=recipe['component_id'], blender_version=bpy.app.version_string,
        object=obj.name, package_sha256=payload['package_sha256'], recipe_sha256=digest(recipe),
        boundary_map_sha256=obj['a3d_sewing_mesh_sha256'], source_garment_sha256=payload['source_garment_sha256'],
        mesh_sha256=mesh_digest(obj), preflight=context)
    return report


def measurement_context(obj,payload,recipe):
    """Strict structure/context identity, independent geometric measurements."""
    from blender.sewing import structural_inputs, context_colliders, penetration_cm
    from a3d.sewing import mesh_quality
    from a3d.garment_rejections import seam_directions
    if any(m.type == 'CLOTH' for m in obj.modifiers):
        raise StudioError('Inspect initial placement before Cloth; restore the checkpoint after a failed simulation')
    coords,faces=structural_inputs(obj,payload,recipe)
    _,trees,snapshots=context_colliders(recipe)
    errors=[]
    try:quality=mesh_quality(payload['rest_cm'],coords,faces,recipe['mesh'])
    except StudioError as exc:
        quality=getattr(exc,'quality_metrics',None);errors.append(str(exc))
    directions=seam_directions(payload,coords)
    if directions['violations']:errors.append('Opposed/undefined permanent seam tangents')
    penetration=penetration_cm(coords,trees)
    if penetration>recipe['limits']['max_penetration_cm']:errors.append('Initial penetration exceeds the unchanged limit')
    context={'quality':quality,'colliders':snapshots,'max_penetration_cm':penetration,
        'status':'REJECTED' if errors else 'PASS','errors':errors,
        'qualification':'MEASUREMENTS_ONLY','accepted':False}
    return context,trees


def inspect_sewing_placement(project_root, component_id, recipe_path):
    from blender.operations import working
    from blender.sewing import managed_inputs
    project,_=working(project_root)
    obj,payload,recipe=managed_inputs(project,component_id,recipe_path,check_placement=False)
    context,trees=measurement_context(obj,payload,recipe)
    return placement_report(obj,payload,recipe,context,trees,project.root)
