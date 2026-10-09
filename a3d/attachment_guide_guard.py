"""Check immutable guide targets before trying to satisfy sewing constraints.

This guard uses the exact body collider's declared physical reserve. A failed
necessary condition blocks coupling; a passed point-distance check does not
qualify panels, surface contacts, donning, or fitting. It never moves a target.
"""
import copy
import math
import time

from .core import StudioError, digest


METHOD = 'FIXED_SOURCE_TARGET_BODY_RESERVE_V1'
LIMITS = {'max_seconds': 60., 'max_triangle_visits': 10000000,
          'max_candidates': 1024, 'max_body_vertices': 200000,
          'max_body_triangles': 200000}


def validate_attachment_guard_policy(policy):
    if (not isinstance(policy, dict) or set(policy) != {'method', 'collider_object', 'budgets'}
            or policy['method'] != METHOD or not isinstance(policy['collider_object'], str)
            or not 1 <= len(policy['collider_object']) <= 256
            or policy['collider_object'].strip() != policy['collider_object']
            or not isinstance(policy['budgets'], dict)
            or 'max_seconds' not in policy['budgets'] or set(policy['budgets'])-set(LIMITS)):
        raise StudioError('Attachment guard requires an explicit collider and bounded policy')
    for name, value in policy['budgets'].items():
        try:
            valid = (type(value) in ((int, float) if name == 'max_seconds' else (int,))
                     and math.isfinite(value) and 0 < value <= LIMITS[name])
        except OverflowError:
            valid = False
        if not valid:
            raise StudioError('Attachment guard has an invalid '+name+' budget')
    return policy


def inspect_fixed_attachment_reserve(data, controls, profile, anatomical_geometry,
                                     recipe, policy, *, clock=time.monotonic):
    """Bind the caller's fixed source points to one exact native body collider."""
    validate_attachment_guard_policy(policy)
    started = clock()
    def check_time():
        if clock()-started >= policy['budgets']['max_seconds']:
            raise StudioError('Attachment guard common time budget exhausted')
    if (not isinstance(controls, list) or not 1 <= len(controls) <= 1024
            or not isinstance(anatomical_geometry, dict) or not isinstance(recipe, dict)
            or recipe.get('component_id') != data.get('component_id')):
        raise StudioError('Attachment guard requires fixed source controls and the exact component recipe')
    geometry = anatomical_geometry.get('geometry')
    triangles = anatomical_geometry.get('triangles')
    if not isinstance(geometry, dict) or not isinstance(triangles, list):
        raise StudioError('Attachment guard requires measured native geometry and triangles')
    colliders = recipe.get('colliders')
    if not isinstance(colliders, list):
        raise StudioError('Attachment guard requires the actual declared recipe collider')
    matches = [row for row in colliders if isinstance(row, dict)
               and row.get('object') == policy['collider_object']]
    if len(matches) != 1:
        raise StudioError('Attachment guard collider is ambiguous or belongs to another measured body')
    collider = matches[0]; reserve = collider.get('outer_thickness_cm')
    if type(reserve) not in (int, float) or not math.isfinite(reserve) or reserve <= 0:
        raise StudioError('Attachment guard needs the actual positive collider outer thickness')
    from .dressing_derivation import _triangles
    from .attachment_clearance import check_attachment_clearances
    _triangles(profile, geometry, triangles)
    check_time()
    # Blender sewing.mesh_digest hashes world meters rounded to seven places.
    # This recipe compatibility identity is distinct from the unrounded body
    # profile identity already verified above, and does not replace that proof.
    collider_sha256 = digest({'vertices_m': [[round(x/100., 7) for x in point]
        for point in geometry['vertices_cm']], 'faces': geometry['faces']})
    if collider.get('geometry_sha256') != collider_sha256:
        raise StudioError('Attachment guard collider belongs to another measured body snapshot')
    for row in controls:
        if (not isinstance(row, dict) or row.get('piece') not in data['pieces']
                or not isinstance(row.get('source_ref'), str) or not row['source_ref']
                or not isinstance(row.get('source_uv_cm'), (list, tuple)) or len(row['source_uv_cm']) != 2
                or any(type(x) not in (int, float) or not math.isfinite(x) for x in row['source_uv_cm'])):
            raise StudioError('Attachment guard requires the actual bound source-UV controls')
    identity = {'source_sha256': digest(data), 'constraints_sha256': digest(controls),
        'profile_sha256': digest(profile), 'geometry_sha256': profile['geometry_sha256'],
        'triangles_sha256': digest(triangles), 'recipe_sha256': digest(recipe),
        'native_collider_sha256': collider_sha256,
        'native_collider_digest_scheme': 'WORLD_METERS_ROUNDED_7_AND_NATIVE_POLYGONS',
        'policy_sha256': digest(policy)}
    receipt = check_attachment_clearances(geometry['vertices_cm'], triangles,
        [row['target_world_cm'] for row in controls], clearance_cm=reserve,
        safety_margin_cm=0., budgets=policy['budgets'], provenance=identity,
        clock=clock, check_time=check_time)
    # Wall time belongs to the run observation, not a deterministic replay.
    receipt.pop('elapsed_seconds', None)
    check_time()
    return {'method': METHOD, 'status': receipt['status'], 'identities': identity,
        'fixed_controls': copy.deepcopy(controls), 'collider_object': collider['object'],
        'physical_reserve_cm': reserve, 'numerical_margin_cm': 0., 'clearance': receipt,
        'candidate_adjusted': False, 'qualification': 'NECESSARY_FIXED_POINT_CONDITION_ONLY',
        'panel_contacts': 'NOT_ASSESSED', 'global_inside_outside': 'NOT_ASSESSED',
        'admissible_for_fit': False}
