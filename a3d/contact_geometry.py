"""Float64 triangle distances and conservative AABB broad phase in centimetres.

These geometric predicates do not move vertices or qualify physical behaviour.
Numerical epsilon classifies coincidence; it is not a collision reserve.
"""
import math
from .core import StudioError


def sub(a,b):return tuple(x-y for x,y in zip(a,b))
def add(a,b):return tuple(x+y for x,y in zip(a,b))
def mul(a,s):return tuple(x*s for x in a)
def dot(a,b):return sum(x*y for x,y in zip(a,b))
def cross(a,b):return (a[1]*b[2]-a[2]*b[1],a[2]*b[0]-a[0]*b[2],a[0]*b[1]-a[1]*b[0])
def norm(a):return math.sqrt(dot(a,a))


def closest_point_triangle(p,t):
    """Closest point in the closed triangle, including edges and vertices."""
    a,b,c=t;ab,ac,ap=sub(b,a),sub(c,a),sub(p,a)
    d1,d2=dot(ab,ap),dot(ac,ap)
    if d1<=0 and d2<=0:return tuple(a)
    bp=sub(p,b);d3,d4=dot(ab,bp),dot(ac,bp)
    if d3>=0 and d4<=d3:return tuple(b)
    vc=d1*d4-d3*d2
    if vc<=0 and d1>=0 and d3<=0:return add(a,mul(ab,d1/(d1-d3)))
    cp=sub(p,c);d5,d6=dot(ab,cp),dot(ac,cp)
    if d6>=0 and d5<=d6:return tuple(c)
    vb=d5*d2-d1*d6
    if vb<=0 and d2>=0 and d6<=0:return add(a,mul(ac,d2/(d2-d6)))
    va=d3*d6-d5*d4
    if va<=0 and d4-d3>=0 and d5-d6>=0:
        return add(b,mul(sub(c,b),(d4-d3)/((d4-d3)+(d5-d6))))
    total=va+vb+vc
    if total<=0:raise StudioError('Degenerate contact triangle')
    return add(a,add(mul(ab,vb/total),mul(ac,vc/total)))


def closest_segments(p1,q1,p2,q2):
    d1,d2,r=sub(q1,p1),sub(q2,p2),sub(p1,p2)
    a,e=dot(d1,d1),dot(d2,d2)
    if a<=0 or e<=0:raise StudioError('Degenerate contact edge')
    b,c,f=dot(d1,d2),dot(d1,r),dot(d2,r)
    denominator=a*e-b*b
    s=max(0.,min(1.,(b*f-c*e)/denominator)) if denominator>1e-15*a*e else 0.
    t=(b*s+f)/e
    if t<0:t=0.;s=max(0.,min(1.,-c/a))
    elif t>1:t=1.;s=max(0.,min(1.,(b-c)/a))
    return add(p1,mul(d1,s)),add(p2,mul(d2,t))


def _segment_triangle(p,q,t,normal,epsilon):
    a,b=dot(sub(p,t[0]),normal),dot(sub(q,t[0]),normal)
    if (a>epsilon and b>epsilon) or (a < -epsilon and b < -epsilon):return None
    if abs(a-b)<=epsilon:return None  # coplanar case handled by distances
    fraction=a/(a-b)
    if not 0<=fraction<=1:return None
    point=add(p,mul(sub(q,p),fraction))
    return point if math.dist(point,closest_point_triangle(point,t))<=epsilon else None


def _coplanar_area(a,b,normal):
    axis=max(range(3),key=lambda i:abs(normal[i]))
    project=lambda p:tuple(p[i] for i in range(3) if i!=axis)
    polygon=[project(p) for p in a];clip=[project(p) for p in b]
    orient=lambda p,q,r:(q[0]-p[0])*(r[1]-p[1])-(q[1]-p[1])*(r[0]-p[0])
    direction=1 if orient(*clip)>0 else -1
    for start,end in zip(clip,clip[1:]+clip[:1]):
        previous=polygon[-1] if polygon else None;output=[]
        for point in polygon:
            dp,dq=direction*orient(start,end,previous),direction*orient(start,end,point)
            if (dq>=0)!=(dp>=0):
                fraction=dp/(dp-dq)
                output.append(tuple(previous[k]+fraction*(point[k]-previous[k]) for k in range(2)))
            if dq>=0:output.append(point)
            previous=point
        polygon=output
    return abs(sum(p[0]*q[1]-p[1]*q[0] for p,q in zip(polygon,polygon[1:]+polygon[:1])))/2 if polygon else 0.


def triangle_contact(a,b):
    """Distance, nearest witnesses and transverse/coplanar/touch classification."""
    if any(len(t)!=3 or any(len(p)!=3 or any(not math.isfinite(v) for v in p) for p in t) for t in (a,b)):
        raise StudioError('Contact triangles must contain finite 3D coordinates')
    normals=[cross(sub(t[1],t[0]),sub(t[2],t[0])) for t in (a,b)]
    lengths=[math.dist(t[i],t[(i+1)%3]) for t in (a,b) for i in range(3)]
    epsilon=max(1e-10,max(lengths)*1e-10)
    if any(norm(n)<=epsilon*max(lengths) for n in normals):raise StudioError('Degenerate contact triangle')
    na,nb=[mul(n,1/norm(n)) for n in normals]
    best=(float('inf'),None,None)
    def consider(p,q):
        nonlocal best
        distance=math.dist(p,q)
        if distance<best[0]:best=(distance,tuple(p),tuple(q))
    for p in a:consider(p,closest_point_triangle(p,b))
    for p in b:consider(closest_point_triangle(p,a),p)
    for i in range(3):
        p=_segment_triangle(a[i],a[(i+1)%3],b,nb,epsilon)
        if p is not None:consider(p,p)
        p=_segment_triangle(b[i],b[(i+1)%3],a,na,epsilon)
        if p is not None:consider(p,p)
        for j in range(3):consider(*closest_segments(a[i],a[(i+1)%3],b[j],b[(j+1)%3]))
    da=[dot(sub(p,b[0]),nb) for p in a];db=[dot(sub(p,a[0]),na) for p in b]
    coplanar=norm(cross(na,nb))<=1e-10 and max(abs(v) for v in da+db)<=epsilon
    kind='SEPARATED'
    if best[0]<=epsilon:
        if coplanar and _coplanar_area(a,b,na)>epsilon*epsilon:kind='COPLANAR_OVERLAP'
        elif min(da)<-epsilon and max(da)>epsilon and min(db)<-epsilon and max(db)>epsilon:kind='TRANSVERSE_INTERSECTION'
        else:kind='TOUCHING'
    return {'distance_cm':best[0],'kind':kind,'point_a_cm':list(best[1]),'point_b_cm':list(best[2]),
            'numerical_epsilon_cm':epsilon}


def triangle_bounds(triangle):
    return tuple(min(p[k] for p in triangle) for k in range(3)),tuple(max(p[k] for p in triangle) for k in range(3))


def separated_projection(a,b,margin):
    """A separating projection proves distance exceeds margin; never the reverse.

    Coplanar in-plane edge normals avoid expensive closest-feature evaluation
    for neighbouring grid boxes whose actual triangles remain disjoint.
    """
    edges_a=[sub(a[(i+1)%3],a[i]) for i in range(3)]
    edges_b=[sub(b[(i+1)%3],b[i]) for i in range(3)]
    na,nb=cross(edges_a[0],edges_a[1]),cross(edges_b[0],edges_b[1])
    def separates(axis):
        length=norm(axis)
        if length==0:return False
        pa=[dot(p,axis) for p in a];pb=[dot(p,axis) for p in b]
        return max(min(pa)-max(pb),min(pb)-max(pa))>margin*length
    if separates(na) or separates(nb):return True
    if norm(cross(na,nb))<=1e-10*norm(na)*norm(nb):
        return any(separates(cross(edge,na)) for edge in edges_a+edges_b)
    return any(separates(cross(e,f)) for e in edges_a for f in edges_b)


def bounds_distance_sq(a,b):
    return sum(max(a[0][k]-b[1][k],b[0][k]-a[1][k],0.)**2 for k in range(3))


class TriangleBVH:
    """Balanced AABB BVH; unlike native triangle overlap, includes coplanar cases."""
    def __init__(self,triangles):
        self.bounds=[triangle_bounds(t) for t in triangles]
        def build(ids):
            box=(tuple(min(self.bounds[i][0][k] for i in ids) for k in range(3)),
                 tuple(max(self.bounds[i][1][k] for i in ids) for k in range(3)))
            if len(ids)<=8:return (box,ids,None,None)
            axis=max(range(3),key=lambda k:box[1][k]-box[0][k])
            ids=sorted(ids,key=lambda i:self.bounds[i][0][axis]+self.bounds[i][1][axis]);half=len(ids)//2
            return (box,None,build(ids[:half]),build(ids[half:]))
        self.root=build(list(range(len(triangles)))) if triangles else None

    def pairs(self,other,margin=0.,same=False):
        if self.root is None or other.root is None:return
        threshold=margin*margin;stack=[(self.root,other.root)]
        while stack:
            a,b=stack.pop()
            if bounds_distance_sq(a[0],b[0])>threshold:continue
            if a[1] is not None and b[1] is not None:
                for i in a[1]:
                    for j in b[1]:
                        if same and a is b and i>=j:continue
                        if bounds_distance_sq(self.bounds[i],other.bounds[j])<=threshold:
                            yield (min(i,j),max(i,j)) if same else (i,j)
            elif same and a is b:
                stack.extend(((a[2],a[2]),(a[2],a[3]),(a[3],a[3])))
            elif a[1] is None and (b[1] is not None or
                    sum(a[0][1][k]-a[0][0][k] for k in range(3))>=sum(b[0][1][k]-b[0][0][k] for k in range(3))):
                stack.extend(((a[2],b),(a[3],b)))
            else:stack.extend(((a,b[2]),(a,b[3])))
