"""Bounded crossing witnesses for linearly interpolated moving surfaces.

Actual animated bodies are separately reevaluated at every discrete check time.
This helper detects vertex/face and edge/edge crossing roots on the endpoint
linear geometric approximation. It does not claim exhaustive nonlinear CCD or
exact intermediate Cloth cache states. Pure Python, metric coordinates in cm.
"""
import math
from a3d.core import StudioError
from a3d.contact_geometry import TriangleBVH, closest_point_triangle, closest_segments, cross, dot, sub


def interpolate(before, after, fraction):
    if len(before) != len(after) or not 0 <= fraction <= 1:
        raise StudioError('Interpolation requires fixed vertex correspondence and fraction in [0,1]')
    return [[a[k]+fraction*(b[k]-a[k]) for k in range(3)] for a,b in zip(before,after)]


def _value(coefficients, time):
    value = 0.
    for coefficient in reversed(coefficients): value = value*time+coefficient
    return value


def _roots(coefficients):
    scale = max((abs(v) for v in coefficients), default=0.)
    if scale == 0: return None
    coefficients = [v/scale for v in coefficients]
    while len(coefficients) > 1 and abs(coefficients[-1]) < 1e-14: coefficients.pop()
    if len(coefficients) == 1: return []
    if len(coefficients) == 2:
        root = -coefficients[0]/coefficients[1]
        return [root] if 0 <= root <= 1 else []
    critical = _roots([i*coefficients[i] for i in range(1,len(coefficients))]) or []
    times = sorted(set([0.,1.]+critical)); roots = []
    for time in times:
        if abs(_value(coefficients,time)) <= 1e-12: roots.append(time)
    for left,right in zip(times,times[1:]):
        a,b = _value(coefficients,left), _value(coefficients,right)
        if a*b >= 0: continue
        for _ in range(60):
            middle = (left+right)/2; value = _value(coefficients,middle)
            if a*value <= 0: right = middle
            else: left = middle; a = value
        roots.append((left+right)/2)
    unique = []
    for root in sorted(roots):
        if not unique or abs(root-unique[-1]) > 1e-9: unique.append(root)
    return unique


def _determinant_polynomial(before, after):
    # det(B-A,C-A,D-A) with every source point linear in interval fraction.
    base = [sub(before[i],before[0]) for i in (1,2,3)]
    change = [sub(sub(after[i],after[0]),base[j]) for j,i in enumerate((1,2,3))]
    coefficients = [0.]*4
    for i in (0,1):
        for j in (0,1):
            for k in (0,1):
                coefficients[i+j+k] += dot((base[0],change[0])[i],
                    cross((base[1],change[1])[j],(base[2],change[2])[k]))
    return coefficients


def _crossing_roots(before, after):
    coefficients = _determinant_polynomial(before,after); roots = _roots(coefficients)
    if roots is None:
        velocity = sub(after[0],before[0])
        moving = any(math.dist(sub(b,a),velocity) > 1e-10 for a,b in zip(before,after))
        return [], moving
    crossings = []
    for time in roots:
        # A root exactly on a discrete sample boundary cannot silently vanish
        # from both neighbouring segments. Preserve its directional witness;
        # the caller treats it as incomplete unless an interior crossing was
        # independently witnessed. Shared stationary tangency still has no
        # sign-changing determinant and is not promoted to a crossing.
        delta = min(1e-5,time/2 if time>1e-9 else 1e-5,(1-time)/2 if time<1-1e-9 else 1e-5)
        if _value(coefficients,time-delta)*_value(coefficients,time+delta) < 0:
            crossings.append(time)
    return crossings, False


def _point_at(before, after, fraction):
    return [before[k]+fraction*(after[k]-before[k]) for k in range(3)]


def swept_crossing(garment_before, garment_after, garment_faces, body_before, body_after,
                   body_triangles, *, max_pairs, expired=lambda:False):
    """Report crossing or incomplete coverage, never move either source."""
    for before,after in ((garment_before,garment_after),(body_before,body_after)):
        if len(before) != len(after) or not before or any(len(p)!=3 or any(type(v) not in (int,float) or not math.isfinite(v)
                for v in p) for p in before+after):
            raise StudioError('Swept contacts require finite immutable vertex correspondence')
    if type(max_pairs) is not int or max_pairs < 1: raise StudioError('Swept contact budget must be positive')
    for faces,coords in ((garment_faces,garment_before),(body_triangles,body_before)):
        if not faces or any(len(f)!=3 or len(set(f))!=3 or any(type(i) is not int or not 0<=i<len(coords) for i in f) for f in faces):
            raise StudioError('Swept contacts require valid source triangles')
    cloth = TriangleBVH([[garment_before[i] for i in f]+[garment_after[i] for i in f] for f in garment_faces])
    body = TriangleBVH([[body_before[i] for i in f]+[body_after[i] for i in f] for f in body_triangles])
    tested = 0; ambiguous = 0
    for face_id,triangle_id in cloth.pairs(body):
        tested += 1
        if tested > max_pairs or expired():
            return {'ok':False,'status':'INCOMPLETE','reason':'MOVING_CONTACT_PAIR_OR_TIME_BUDGET','tested_pairs':tested-1}
        face,triangle = garment_faces[face_id],body_triangles[triangle_id]
        ga,gb = [[garment_before[i] for i in face],[garment_after[i] for i in face]]
        ba,bb = [[body_before[i] for i in triangle],[body_after[i] for i in triangle]]
        epsilon = max(1e-8,max(math.dist(p,q) for points in (ga,gb,ba,bb) for p in points for q in points)*1e-9)
        candidates = []
        for point_id in range(3):
            for origin_a,origin_b,target_a,target_b,label in ((ga,gb,ba,bb,'GARMENT_VERTEX_MOVING_BODY_FACE'),
                                                           (ba,bb,ga,gb,'BODY_VERTEX_MOVING_GARMENT_FACE')):
                roots,unresolved = _crossing_roots([target_a[0],target_a[1],target_a[2],origin_a[point_id]],
                                                 [target_b[0],target_b[1],target_b[2],origin_b[point_id]])
                ambiguous += int(unresolved)
                for fraction in roots:
                    point = _point_at(origin_a[point_id],origin_b[point_id],fraction)
                    target = [_point_at(a,b,fraction) for a,b in zip(target_a,target_b)]
                    if math.dist(point,closest_point_triangle(point,target)) <= epsilon:
                        candidates.append({'fraction':fraction,'feature':label,'vertex_local':point_id})
        for a0,a1 in ((0,1),(1,2),(2,0)):
            for b0,b1 in ((0,1),(1,2),(2,0)):
                roots,unresolved = _crossing_roots([ga[a0],ga[a1],ba[b0],ba[b1]], [gb[a0],gb[a1],bb[b0],bb[b1]])
                ambiguous += int(unresolved)
                for fraction in roots:
                    points = [_point_at(a,b,fraction) for a,b in zip([ga[a0],ga[a1],ba[b0],ba[b1]],
                                                                   [gb[a0],gb[a1],bb[b0],bb[b1]])]
                    left,right = closest_segments(*points)
                    if math.dist(left,right) <= epsilon:
                        candidates.append({'fraction':fraction,'feature':'MOVING_EDGE_EDGE'})
        if candidates:
            interior=any(1e-9<row['fraction']<1-1e-9 for row in candidates)
            return {'ok':False,'status':'REFUSED' if interior else 'INCOMPLETE',
                    'reason':'RELATIVE_SWEPT_SURFACE_CROSSING' if interior else 'MOVING_CONTACT_ENDPOINT_DIRECTION_UNRESOLVED',
                    'garment_face':face_id,'body_triangle':triangle_id,'tested_pairs':tested,
                    'witnesses':sorted(candidates,key=lambda row:row['fraction'])[:12],
                    'scope':'LINEAR_ENDPOINT_SURFACES_NOT_EXHAUSTIVE_NONLINEAR_CCD'}
    if ambiguous:
        return {'ok':False,'status':'INCOMPLETE','reason':'PERSISTENT_COPLANAR_MOVING_FEATURE_UNRESOLVED',
                'tested_pairs':tested,'unresolved_features':ambiguous}
    return {'ok':True,'status':'LINEAR_SWEPT_FEATURES_CLEAR','tested_pairs':tested,
            'scope':'LINEAR_ENDPOINT_SURFACES_NOT_EXHAUSTIVE_NONLINEAR_CCD'}
