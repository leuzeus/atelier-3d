"""Bounded directional surface envelopes for source-bound material cages.

The operation is a geometric proposal, not drape or contact admission. Explicit
source face regions prevent a torso panel from snapping to a neighbouring arm.
The declared direction decides which exterior sheet is relevant; several
distinct sheets or missing coverage remain unresolved instead of guessed.
"""
import copy
import math
import time
from collections import defaultdict

from .anatomy_profile import unit
from .contact_geometry import TriangleBVH, cross, dot, sub
from .core import StudioError, digest


def _positive(value, name, maximum):
    if type(value) not in (int, float) or not math.isfinite(value) or not 0 < value <= maximum:
        raise StudioError('Regional surface envelope needs bounded '+name)
    return value


def _line_box(point, direction, box, bound):
    lo, hi = -bound, bound
    for k in range(3):
        if abs(direction[k]) <= 1e-14:
            if not box[0][k]-1e-9 <= point[k] <= box[1][k]+1e-9:
                return False
        else:
            a, b = sorted(((box[0][k]-point[k])/direction[k], (box[1][k]-point[k])/direction[k]))
            lo, hi = max(lo, a), min(hi, b)
            if hi+1e-9 < lo:
                return False
    return True


def _outward_hit(point, direction, triangle, bound):
    a, b, c = triangle
    e1, e2 = sub(b, a), sub(c, a)
    normal = cross(e1, e2)
    # Outward winding and transversality are required. A grazing triangle does
    # not provide an exterior envelope along the declared material direction.
    normal_size = math.sqrt(dot(normal, normal))
    if normal_size <= 1e-12 or dot(normal, direction) <= 1e-9*normal_size:
        return None
    h = cross(direction, e2); determinant = dot(e1, h)
    delta = sub(point, a); u = dot(delta, h)/determinant
    q = cross(delta, e1); v = dot(direction, q)/determinant
    distance = dot(e2, q)/determinant
    if min(u, v, 1-u-v) >= -1e-9 and -bound <= distance <= bound:
        return distance, dot(normal, direction)/normal_size
    return None


def _hits(point, direction, triangles, tree, bound, tick):
    pending = [tree.root] if tree.root is not None else []; values = []
    while pending:
        tick()
        node = pending.pop()
        if not _line_box(point, direction, node[0], bound):
            continue
        if node[1] is None:
            pending.extend((node[2], node[3])); continue
        for index in node[1]:
            tick(ray=True)
            hit = _outward_hit(point, direction, triangles[index], bound)
            if hit is not None:
                values.append((hit[0], index, hit[1]))
    groups = []
    for distance, index, cosine in sorted(values):
        if not groups or abs(distance-groups[-1][0]) > 1e-7:
            groups.append([distance, [index], cosine])
        else:
            groups[-1][1].append(index)
            groups[-1][2] = min(groups[-1][2], cosine)
    return groups


def apply_regional_surface_envelopes(data, panels, profile, anatomical_geometry, policies, *, clock=time.monotonic):
    """Return new guide cages and complete/partial envelope diagnostics.

    Policies are independent of piece names or garment families. Each specifies
    source_region_ids, direction_body, reserve_cm, max_displacement_cm and an
    optional source_v_range_cm. UV, connectivity, approved body and source
    patterns remain byte-for-byte inputs; material distortion remains visible.
    """
    from .dressing_derivation import _triangles
    from .garment_guides import _source_limb_mesh, _vector
    from .pattern_assembly import _compile_cage
    from .source_seam_coupling import _evaluator, _Budget
    if (not isinstance(anatomical_geometry, dict) or not isinstance(policies, dict) or
            not policies or not set(policies) <= set(panels)):
        raise StudioError('Regional surface envelope requires exact body geometry, native triangles and prepared pieces')
    geometry = anatomical_geometry.get('geometry', {}); indexed = anatomical_geometry.get('triangles', [])
    _triangles(profile, geometry, indexed)
    before = digest([data, panels, profile, anatomical_geometry, policies])
    labels = geometry.get('face_sets')
    if (not isinstance(labels, list) or len(labels) != len(geometry['faces']) or
            any(type(label) is not int for label in labels)):
        raise StudioError('Regional surface envelope requires actual source face-region identities')
    memberships = defaultdict(set)
    for fid, face in enumerate(geometry['faces']):
        for vertex in face:
            memberships[vertex].add(fid)
    owners = []
    for triangle in indexed:
        common = set.intersection(*(memberships[index] for index in triangle))
        if len(common) != 1:
            raise StudioError('Regional envelope triangle has ambiguous source face ownership')
        owners.append(next(iter(common)))
    result = copy.deepcopy(panels); reports = []; diagnostics = []
    for pid, policy in sorted(policies.items()):
        if not isinstance(policy, dict) or policy.get('method') != 'REGIONAL_SURFACE_ENVELOPE_V1':
            raise StudioError('Regional surface envelope requires its explicit V1 method')
        region_ids = policy.get('source_region_ids')
        if (not isinstance(region_ids, list) or not region_ids or len(region_ids) > 128 or
                any(type(value) is not int for value in region_ids) or len(set(region_ids)) != len(region_ids) or
                not set(region_ids) <= set(labels)):
            raise StudioError('Regional surface envelope requires existing distinct source regions: '+pid)
        direction_body = unit(_vector(policy.get('direction_body'), 'regional exterior direction'))
        direction = [math.fsum(direction_body[j]*profile['frame'][name][k]
                    for j, name in enumerate(('right', 'forward', 'up'))) for k in range(3)]
        reserve = _positive(policy.get('reserve_cm'), 'reserve_cm', 20.)
        maximum = _positive(policy.get('max_displacement_cm'), 'max_displacement_cm', 100.)
        if reserve > maximum:
            raise StudioError('Regional envelope reserve exceeds its correction budget')
        interval = policy.get('source_v_range_cm')
        if interval is not None and (not isinstance(interval, list) or len(interval) != 2 or
                any(type(x) not in (int, float) or not math.isfinite(x) for x in interval) or interval[0] > interval[1]):
            raise StudioError('Regional envelope material V scope must be an explicit finite interval')
        seconds = _positive(policy.get('max_seconds', 30.), 'max_seconds', 120.)
        cap = policy.get('max_controls', 20000); ray_cap = policy.get('max_ray_tests', 2000000)
        if (type(cap) is not int or not 1 <= cap <= 100000 or type(ray_cap) is not int or not 1 <= ray_cap <= 20000000):
            raise StudioError('Regional surface envelope requires finite control/ray budgets')
        started = clock(); ray_tests = 0

        def tick(ray=False):
            nonlocal ray_tests
            if ray:
                ray_tests += 1
            if ray_tests > ray_cap or clock()-started > seconds:
                raise TimeoutError('REGIONAL_ENVELOPE_BUDGET_EXHAUSTED')

        selected = [i for i, owner in enumerate(owners) if labels[owner] in region_ids]
        triangles = [[geometry['vertices_cm'][j] for j in indexed[i]] for i in selected]
        tree = TriangleBVH(triangles)
        frame = result[pid]
        if 'uv_cm' not in frame:
            budget = _Budget(None, clock)
            evaluate = _evaluator(frame, pid, budget)
            uv, faces = _source_limb_mesh(data['pieces'][pid], 8)
            frame = result[pid] = {'source_ref': frame['source_ref'], 'uv_cm': uv,
                'target_cm': [evaluate(p) for p in uv], 'triangles': faces}
        _compile_cage(frame, pid)
        if len(frame['uv_cm']) > cap:
            raise StudioError('Regional surface envelope source cage control budget exhausted: '+pid)
        moved = 0; covered = 0; outside_scope = 0; unresolved = []; maximum_used = 0.; stopped = False
        old_targets = copy.deepcopy(frame['target_cm'])
        for index, (uv, point) in enumerate(zip(frame['uv_cm'], old_targets)):
            if interval is not None and not interval[0] <= uv[1] <= interval[1]:
                outside_scope += 1; continue
            if stopped:
                unresolved.append((index, 'BUDGET_NOT_EVALUATED')); continue
            try:
                hits = _hits(point, direction, triangles, tree, maximum, tick)
            except TimeoutError:
                stopped = True; unresolved.append((index, 'BUDGET_NOT_EVALUATED')); continue
            if len(hits) != 1:
                unresolved.append((index, 'SURFACE_COVERAGE_MISSING' if not hits else 'MULTIPLE_EXTERIOR_SHEETS')); continue
            distance = max(0., hits[0][0]+reserve/hits[0][2])
            if distance > maximum:
                unresolved.append((index, 'DISPLACEMENT_BUDGET_EXCEEDED')); continue
            covered += 1
            if distance > 1e-10:
                frame['target_cm'][index] = [point[k]+distance*direction[k] for k in range(3)]
                maximum_used = max(maximum_used, distance); moved += 1
        frame['source_ref'] += '; regional-surface-envelope:'+digest(policy)
        record = {'piece': pid, 'method': 'REGIONAL_SURFACE_ENVELOPE_V1',
            'source_region_ids': list(region_ids), 'direction_body': direction_body,
            'geometry_sha256': profile['geometry_sha256'], 'native_triangles_sha256': digest(indexed),
            'source_face_sets_sha256': digest(labels), 'selected_triangle_count': len(selected),
            'reserve_cm': reserve, 'max_displacement_cm': maximum_used,
            'controls': len(old_targets), 'covered_controls': covered, 'moved_controls': moved,
            'outside_declared_scope_controls': outside_scope, 'unresolved_controls': len(unresolved),
            'unresolved_samples': [{'index': i, 'reason': reason} for i, reason in unresolved[:32]],
            'ray_triangle_tests': ray_tests,
            'status': 'PARTIAL_SURFACE_ENVELOPE' if unresolved else 'SURFACE_ENVELOPE_PREPARED',
            'material_metric_preserved': 'NOT_ASSUMED_REQUIRES_SOLVER',
            'source_uv_scaled': False, 'source_topology_changed': False, 'body_mutated': False,
            'final_triangle_contacts': 'REQUIRED', 'qualification': 'NONE'}
        reports.append(record)
        if unresolved:
            diagnostics.append({'piece': pid, 'code': 'REGIONAL_SURFACE_COVERAGE_INCOMPLETE',
                'unresolved_controls': len(unresolved), 'samples': record['unresolved_samples'],
                'message': 'The declared region/direction does not provide a unique bounded exterior for all requested controls'})
    if digest([data, panels, profile, anatomical_geometry, policies]) != before:
        raise StudioError('Regional surface envelopes changed immutable input')
    return result, {'version': 1, 'pieces': reports, 'diagnostics': diagnostics,
        'status': 'PARTIAL_SURFACE_ENVELOPES' if diagnostics else 'SURFACE_ENVELOPES_PREPARED',
        'source_mutated': False, 'body_mutated': False, 'metric_admission': 'REQUIRED',
        'contact_admission': 'REQUIRED', 'simulation': 'NOT_EXECUTED', 'qualification': 'NONE'}
