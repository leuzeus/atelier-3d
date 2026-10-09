"""Constructive, exact UV reference partitions; no 3D field or production caller."""
from collections import defaultdict
from fractions import Fraction as F
from pathlib import Path
import hashlib
import math
import time

from .core import StudioError
from . import material_sample_carrier as uv
from . import material_surface_field as accounting


DISCRIMINANT = 'MATERIAL_REFERENCE_PARTITION_V1'
# This new global construction format deliberately differs from field V1's
# local 4k/8k mesh limits. Its source/cage envelope comes from seam coupling.
_DEFAULTS = {'max_source_points': 20000, 'max_source_triangles': 20000,
    'max_controls': 70000, 'max_triangles': 131072, 'max_sections': 10000,
    'max_samples': 10000, 'max_pair_checks': 250000,
    'max_fraction_operations': 300000, 'max_fraction_bits': 4096,
    'max_input_nodes': 500000, 'max_input_bytes': 8388608,
    'max_output_nodes': 500000, 'max_output_bytes': 8388608, 'max_seconds': 60.}
_HARD = {**_DEFAULTS, 'max_pair_checks': 2000000,
         'max_fraction_operations': 5000000}


def _refuse(reason, detail):
    error = StudioError('Material reference partition: '+detail)
    error.reason = reason; error.qualification = 'NONE'
    error.status = 'INCOMPLETE' if reason in ('BUDGET_EXHAUSTED','DEADLINE_EXHAUSTED') else 'REFUSED'
    raise error


class _Budget(accounting._Budget):
    def __init__(self, values, deadline, clock):
        if not callable(clock): _refuse('INVALID_CLOCK','monotone clock required')
        if deadline is not None and not accounting._finite(deadline):
            _refuse('INVALID_DEADLINE','finite absolute deadline required')
        self.clock=clock; self.counts={}; self.declared_deadline=deadline
        self.start=self.now()
        self.deadline=min(self.start+60.,deadline) if deadline is not None else self.start+60.
        self.check('before_budget_capture')
        if values is None: values={}
        if type(values) is not dict or set(values)-set(_DEFAULTS):
            _refuse('INVALID_BUDGET','unknown construction budget')
        self.limits={**_DEFAULTS,**values}
        for key,value in self.limits.items():
            self.check('budget_capture')
            valid=type(value) in (int,float) if key=='max_seconds' else type(value) is int
            if not valid or not accounting._finite(value) or not 0<value<=_HARD[key]:
                _refuse('INVALID_BUDGET','invalid explicit cap: '+key)
        self.deadline=min(self.start+self.limits['max_seconds'],deadline) if deadline is not None else self.start+self.limits['max_seconds']
        self.check('before_capture')


def _q(value,b): return b.q(value)
def _num(value,b): return _q(uv._number(value,b),b)
def _add(a,c,b): return _q(a+c,b)
def _sub(a,c,b): return _q(a-c,b)
def _mul(a,c,b): return _q(a*c,b)
def _div(a,c,b):
    if not c: _refuse('DEGENERATE','zero rational divisor')
    return _q(a/c,b)


def _sum(values,b):
    total=F(0)
    for value in values:total=_add(total,value,b)
    return total


def _cross(a,c,d,b):
    return _sub(_mul(_sub(c[0],a[0],b),_sub(d[1],a[1],b),b),
                _mul(_sub(c[1],a[1],b),_sub(d[0],a[0],b),b),b)


def _signed_area(poly,b):
    total=F(0)
    for a,c in zip(poly,poly[1:]+poly[:1]):
        total=_add(total,_sub(_mul(a[0],c[1],b),_mul(a[1],c[0],b),b),b)
    return _div(total,F(2),b)


def _bary(point,tri,b):
    det=_cross(*tri,b)
    return tuple(_div(_cross(point,tri[1],tri[2],b),det,b) if i==0 else
                 _div(_cross(tri[0],point,tri[2],b),det,b) if i==1 else
                 _div(_cross(tri[0],tri[1],point,b),det,b) for i in range(3))


def _on(point,a,c,b):
    return _cross(a,c,point,b)==0 and all(min(a[k],c[k])<=point[k]<=max(a[k],c[k]) for k in (0,1))


def _unique(poly):
    out=[]
    for p in poly:
        if not out or p!=out[-1]: out.append(p)
    if len(out)>1 and out[0]==out[-1]: out.pop()
    return out


def _intersection(poly,tri,b):
    if _cross(*tri,b)<0: tri=list(reversed(tri))
    for a,c in zip(tri,tri[1:]+tri[:1]):
        b.check('source_exhaustive_clipping')
        if not poly: break
        out=[]
        for p,q in zip(poly,poly[1:]+poly[:1]):
            cp,cq=_cross(a,c,p,b),_cross(a,c,q,b)
            if cp>=0: out.append(p)
            if (cp<0<=cq) or (cq<0<=cp):
                t=_div(cp,_sub(cp,cq,b),b)
                out.append(tuple(_add(p[k],_mul(t,_sub(q[k],p[k],b),b),b) for k in (0,1)))
        poly=_unique(out)
    return poly


def _topology(faces,point_count,b):
    owners=defaultdict(list); stars=defaultdict(list); seen=set()
    for fid,f in enumerate(faces):
        b.check('source_topology')
        key=tuple(sorted(f))
        if key in seen: _refuse('OVERLAP','duplicate source face')
        seen.add(key)
        for v in f: stars[v].append(fid)
        for a,c in zip(f,f[1:]+f[:1]): owners[tuple(sorted((a,c)))].append((fid,a,c))
    if len(stars)!=point_count: _refuse('INVALID_SOURCE','unused source vertex')
    adjacency=defaultdict(set);boundary=[]
    for edge,uses in owners.items():
        b.check('source_edge_ownership')
        if len(uses)==1: boundary.append(edge)
        elif len(uses)==2 and uses[0][1:]==tuple(reversed(uses[1][1:])):
            adjacency[uses[0][0]].add(uses[1][0]);adjacency[uses[1][0]].add(uses[0][0])
        else: _refuse('NONMANIFOLD','invalid source edge ownership')
    visited=set();todo=[0]
    while todo:
        b.check('source_connectivity'); i=todo.pop()
        if i not in visited: visited.add(i);todo.extend(adjacency[i]-visited)
    degree=defaultdict(int)
    for a,c in boundary: degree[a]+=1;degree[c]+=1
    if len(visited)!=len(faces) or point_count-len(owners)+len(faces)!=1 or not degree or any(v!=2 for v in degree.values()):
        _refuse('NONMANIFOLD','source must be one complete material disk')
    # Check links as well as Euler/edges. These flags do not replace pairs.
    for v,fs in stars.items():
        b.check('source_vertex_links');link=defaultdict(set)
        for fid in fs:
            a,c=[i for i in faces[fid] if i!=v];link[a].add(c);link[c].add(a)
        visited=set();todo=[next(iter(link))]
        while todo:
            i=todo.pop()
            if i not in visited:visited.add(i);todo.extend(link[i]-visited)
        ds=sorted(len(ns) for ns in link.values())
        want=[1,1]+[2]*(len(ds)-2) if v in degree else [2]*len(ds)
        if len(visited)!=len(link) or ds!=want: _refuse('NONMANIFOLD','source vertex link is not a disk/cycle')
    return owners,boundary


def _source(raw,b):
    uv._fields(raw,('id','uv_cm','triangles','vertex_ids','face_ids'),('edges',))
    uv._identity(raw['id'])
    for k in ('uv_cm','triangles','vertex_ids','face_ids'):
        if type(raw[k]) is not list: _refuse('INVALID_SOURCE','source arrays required')
    n,nf=len(raw['uv_cm']),len(raw['triangles'])
    if n<3 or nf<1 or n!=len(raw['vertex_ids']) or nf!=len(raw['face_ids']):
        _refuse('INVALID_SOURCE','source counts/identities differ')
    b.available('pair_checks',nf*(nf-1)//2)
    b.take('source_points',n);b.take('source_triangles',nf)
    vids=[uv._identity(v) for v in raw['vertex_ids']]; fids=[uv._identity(v) for v in raw['face_ids']]
    if len(set(vids))!=n or len(set(fids))!=nf: _refuse('IDENTITY_COLLISION','duplicate source identity')
    points=[]
    for p in raw['uv_cm']:
        if type(p) is not list or len(p)!=2: _refuse('INVALID_SOURCE','source UV requires two coordinates')
        points.append(tuple(_num(x,b) for x in p))
    if len(set(points))!=n: _refuse('AMBIGUOUS_SOURCE','distinct source nodes coincide exactly')
    faces=[];orientation=None
    for f in raw['triangles']:
        if type(f) is not list or len(f)!=3 or any(type(i)is not int or not 0<=i<n for i in f) or len(set(f))!=3:
            _refuse('INVALID_SOURCE','invalid actual source triangle')
        det=_cross(*(points[i] for i in f),b)
        if not det: _refuse('DEGENERATE','zero source triangle')
        sign=1 if det>0 else -1
        if orientation is not None and sign!=orientation: _refuse('WINDING','source faces disagree')
        orientation=sign;faces.append(f)
    owners,boundary=_topology(faces,n,b)
    for i,fa in enumerate(faces):
        for j in range(i+1,nf):
            b.take('pair_checks');fb=faces[j]
            poly=_intersection([points[k] for k in fa],[points[k] for k in fb],b)
            if len(poly)>=3 and _signed_area(poly,b): _refuse('OVERLAP','source triangles overlap')
            shared=set(fa)&set(fb)
            if poly and (not shared or any(not _on(p,points[min(shared)],points[max(shared)],b) for p in poly)):
                _refuse('AMBIGUOUS_SOURCE','nonconforming source contact')
    edges=raw.get('edges',{})
    if type(edges)is not dict: _refuse('INVALID_SOURCE','named edges must be explicit')
    lookup={v:i for i,v in enumerate(vids)}
    for name,chain in edges.items():
        uv._identity(name)
        if type(chain)is not list or len(chain)<2 or any(type(v)is not str or v not in lookup for v in chain) or len(set(chain))!=len(chain):
            _refuse('INVALID_SOURCE','invalid source boundary chain')
        if any(tuple(sorted((lookup[a],lookup[c])))not in boundary for a,c in zip(chain,chain[1:])):
            _refuse('INVALID_SOURCE','named boundary is not an actual source edge')
    # Stable identities, never input-array order, determine the canonical route.
    order=sorted(range(n),key=lambda i:vids[i]);inverse={old:new for new,old in enumerate(order)}
    canonical_faces=[]
    for fid,f in sorted(zip(fids,faces)):
        k=min(range(3),key=lambda j:vids[f[j]])
        canonical_faces.append((fid,[inverse[i] for i in f[k:]+f[:k]]))
    normalized={'id':raw['id'],'uv_cm':[raw['uv_cm'][i] for i in order],
        'vertex_ids':[vids[i] for i in order],'triangles':[f for _,f in canonical_faces],
        'face_ids':[fid for fid,_ in canonical_faces],'edges':{k:edges[k] for k in sorted(edges)}}
    return {'raw':normalized,'points':[points[i] for i in order],
        'faces':normalized['triangles'],'ids':normalized['vertex_ids'],
        'face_lookup':{fid:i for i,fid in enumerate(normalized['face_ids'])},
        'vertex_lookup':{v:i for i,v in enumerate(normalized['vertex_ids'])},
        'edges':{tuple(sorted((inverse[a],inverse[c]))) for a,c in owners},'orientation':orientation}


def _clip_v(poly,cut,below,b):
    out=[]
    for p,q in zip(poly,poly[1:]+poly[:1]):
        b.check('rational_section_clipping')
        dp,dq=_sub(p[1],cut,b),_sub(q[1],cut,b)
        ip,iq=(dp<=0,dq<=0) if below else (dp>=0,dq>=0)
        if ip: out.append(p)
        if ip!=iq:
            t=_div(dp,_sub(dp,dq,b),b)
            out.append(tuple(_add(p[k],_mul(t,_sub(q[k],p[k],b),b),b) for k in (0,1)))
    return _unique(out)


def _cells(tri,cuts,b):
    remainder=list(tri);out=[]
    for cut in cuts:
        b.take('fraction_operations');b.check('section_order')
        low,high=min(p[1] for p in remainder),max(p[1] for p in remainder)
        if cut<=low:continue
        if cut>=high:break
        lower=_clip_v(remainder,cut,True,b)
        if len(lower)>=3:out.append(lower)
        remainder=_clip_v(remainder,cut,False,b)
    out.append(remainder)
    if _sum((_signed_area(p,b) for p in out),b)!=_signed_area(list(tri),b):
        _refuse('CERTIFICATE_INVALID','section children do not cover parent exactly')
    return out


def _ears(poly,b):
    left=list(poly);out=[]
    while len(left)>3:
        b.check('constructive_ear');total=abs(_mul(_signed_area(left,b),F(2),b))
        candidates=[(abs(_cross(left[i-1],p,left[(i+1)%len(left)],b)),i) for i,p in enumerate(left)]
        candidates=[row for row in candidates if 0<row[0]<total]
        if not candidates:_refuse('CERTIFICATE_INVALID','convex cell cannot retain boundary nodes')
        _,i=max(candidates,key=lambda row:(row[0],-row[1]))
        out.append([left[i-1],left[i],left[(i+1)%len(left)]]);left.pop(i)
    if len(left)!=3 or not _cross(*left,b):_refuse('CERTIFICATE_INVALID','zero child triangle')
    out.append(left)
    if _sum((_signed_area(p,b) for p in out),b)!=_signed_area(poly,b):
        _refuse('CERTIFICATE_INVALID','triangles do not cover material cell')
    return out


def _code_sources(b):
    out={}
    for module in (__file__,uv.__file__,accounting.__file__):
        b.check('code_before_capture');path=Path(module)
        if path.stat().st_size>1048576:_refuse('BUDGET_EXHAUSTED','code source size exceeds fixed1MiB')
        out[path.name]=hashlib.sha256(path.read_bytes()).hexdigest();b.check('code_after_hash')
    return out


def _binding(raw,b,code):
    uv._fields(raw,('candidate_id','run_id','predecessor_candidate_id','predecessor_run_id',
        'source_sha256','recipe_sha256','body_sha256','code_sha256'))
    for k in ('candidate_id','run_id'):uv._identity(raw[k])
    for k in ('predecessor_candidate_id','predecessor_run_id'):
        if raw[k] is not None:uv._identity(raw[k])
    if raw['candidate_id']==raw['predecessor_candidate_id'] or raw['run_id']==raw['predecessor_run_id']:
        _refuse('INVALIDATION_REQUIRED','new candidate/run identity must differ from predecessor')
    for k in ('source_sha256','recipe_sha256','body_sha256','code_sha256'):
        s=raw[k]
        if type(s)is not str or len(s)!=64 or any(c not in '0123456789abcdef'for c in s):
            _refuse('INVALID_BINDING','explicit SHA256 identity required')
    if raw['code_sha256']!=code[Path(__file__).name]:
        _refuse('INVALIDATION_REQUIRED','code identity changed; new preparation binding required')
    b.check('binding');return raw


def _sample(row,source,b):
    uv._fields(row,('id','domain_id','role','support'),('relation_ref','metadata'))
    uv._identity(row['id'])
    if row['role']not in ('material_sample','notch','reference_node'):
        _refuse('INVALID_SAMPLE','explicit material/sample/reference-node role required')
    if 'relation_ref'in row:
        uv._fields(row['relation_ref'],('id','kind','orientation'))
        uv._identity(row['relation_ref']['id'])
        if row['relation_ref']['kind']not in ('permanent','closure','detachable') or row['relation_ref']['orientation']not in ('forward','reverse'):
            _refuse('INVALID_SAMPLE','relation remains an explicit unexecuted source reference')
    s=row['support'];points=source['points'];vlookup=source['vertex_lookup']
    if type(s)is not dict:_refuse('INVALID_SUPPORT','source support required')
    kind=s.get('kind')
    if kind=='source_vertex':
        uv._fields(s,('kind','vertex_id'))
        if type(s['vertex_id'])is not str or s['vertex_id']not in vlookup:_refuse('INVALID_SUPPORT','unknown original vertex')
        point=points[vlookup[s['vertex_id']]]
    elif kind=='source_segment':
        uv._fields(s,('kind','vertex_ids','fraction'))
        vs=s['vertex_ids']
        if type(vs)is not list or len(vs)!=2 or any(type(v)is not str or v not in vlookup for v in vs) or len(set(vs))!=2:
            _refuse('INVALID_SUPPORT','actual source segment IDs required')
        ids=[vlookup[v]for v in vs]
        if tuple(sorted(ids))not in source['edges']:_refuse('INVALID_SUPPORT','segment is not an actual source edge')
        t=_num(s['fraction'],b)
        if not 0<=t<=1:_refuse('INVALID_SUPPORT','local material fraction outside segment')
        p,q=[points[i]for i in ids]
        point=tuple(_add(p[k],_mul(t,_sub(q[k],p[k],b),b),b)for k in (0,1))
    elif kind=='source_face':
        uv._fields(s,('kind','face_id','weights'))
        if type(s['face_id'])is not str or s['face_id']not in source['face_lookup'] or type(s['weights'])is not list:
            _refuse('INVALID_SUPPORT','actual source face and weights required')
        f=source['faces'][source['face_lookup'][s['face_id']]];allowed={source['ids'][i]for i in f};weights={}
        for pair in s['weights']:
            if type(pair)is not list or len(pair)!=2 or type(pair[0])is not str or pair[0]not in allowed or pair[0]in weights:
                _refuse('INVALID_SUPPORT','weights must bind distinct actual face vertices')
            weights[pair[0]]=_num(pair[1],b)
        if any(v<0 for v in weights.values()) or _sum(weights.values(),b)!=1:
            _refuse('INVALID_SUPPORT','exact nonnegative weights must sum to1')
        point=tuple(_sum((_mul(w,points[vlookup[v]][k],b)for v,w in weights.items()),b) for k in (0,1))
    else:_refuse('INVALID_SUPPORT','rounded UV is not an original material support')
    return point


def _build(data,b):
    uv._fields(data,('sources','sections','subdivisions','material_samples','binding'))
    for k in ('sources','sections','material_samples'):
        if type(data[k])is not list:_refuse('INVALID_CONTRACT','explicit source/section/sample lists required')
    n=data['subdivisions']
    if type(n)is not int or not 2<=n<=16:_refuse('INVALID_CONTRACT','integer subdivisions2..16 required')
    code=_code_sources(b);binding=_binding(data['binding'],b,code)
    if binding['source_sha256']!=accounting._hash(data['sources'],b,'actual_source_binding'):
        _refuse('INVALID_BINDING','source SHA does not bind the actual supplied source meshes')
    sources={}
    for raw in sorted(data['sources'],key=lambda v:str(v.get('id',''))if type(v)is dict else ''):
        s=_source(raw,b);pid=s['raw']['id']
        if pid in sources:_refuse('IDENTITY_COLLISION','source domain identity repeated')
        sources[pid]=s
    if not sources:_refuse('INVALID_SOURCE','at least one actual source required')
    b.take('sections',len(data['sections']));sectionids=set();cuts=defaultdict(set);sectionrows=[]
    for r in data['sections']:
        uv._fields(r,('id','domain_id','v_cm'));uv._identity(r['id']);pid=uv._identity(r['domain_id'])
        if r['id']in sectionids or pid not in sources:_refuse('INVALID_SECTION','duplicate section or unknown domain')
        sectionids.add(r['id']);v=_num(r['v_cm'],b);ys=[p[1]for p in sources[pid]['points']]
        if not min(ys)<=v<=max(ys):_refuse('INVALID_SECTION','section outside actual source V domain')
        cuts[pid].add(v);sectionrows.append({'id':r['id'],'domain_id':pid,'v_cm':v})
    sectionrows.sort(key=lambda r:(r['domain_id'],r['v_cm'],r['id']))
    b.take('samples',len(data['material_samples']));sampleids=set();samples=[]
    for r in sorted(data['material_samples'],key=lambda v:str(v.get('id',''))if type(v)is dict else ''):
        if type(r)is not dict or type(r.get('domain_id'))is not str or r.get('domain_id')not in sources:_refuse('INVALID_SAMPLE','unknown material domain')
        point=_sample(r,sources[r['domain_id']],b)
        if r['id']in sampleids:_refuse('IDENTITY_COLLISION','distinct sample IDs required')
        sampleids.add(r['id']);samples.append({'definition':r,'point':point})
    b.available('triangles',sum(len(s['faces'])*n*n for s in sources.values()))
    nodes={};parents=[];cells=[];active=[];insertions=[]

    def node(pid,point,source_face,seed=False):
        s=sources[pid];fi=s['face_lookup'][source_face];f=s['faces'][fi]
        weights=_bary(point,[s['points'][i]for i in f],b)
        if min(weights)<0 or _sum(weights,b)!=1:_refuse('CERTIFICATE_INVALID','node outside its exact original source face')
        support=tuple(sorted((s['ids'][i],w)for i,w in zip(f,weights)if w))
        key=(pid,point)
        if key not in nodes:
            b.take('controls');nodes[key]={'domain_id':pid,'uv_cm':point,'source_weights':support,'is_seed':seed}
        elif nodes[key]['source_weights']!=support:
            _refuse('AMBIGUOUS_SOURCE','coincident UV has different actual material support')
        elif seed:nodes[key]['is_seed']=True
        return key

    def add_triangle(pid,source_face,points,parent):
        s=sources[pid];d=_cross(*points,b)
        if not d or (1 if d>0 else -1)!=s['orientation']:_refuse('CERTIFICATE_INVALID','child triangle winding/area invalid')
        b.take('triangles');row={'id':'mrp:t'+str(len(active)),'domain_id':pid,'source_face_id':source_face,
            'nodes':[node(pid,p,source_face)for p in points],'parent':parent,'active':True}
        active.append(row);return row['id']

    for pid,s in sources.items():
        for fid,f in zip(s['raw']['face_ids'],s['faces']):
            grid={}
            for i in range(n+1):
                for j in range(n+1-i):
                    w=(n-i-j,i,j)
                    point=tuple(_div(_sum((_mul(s['points'][v][k],F(weight),b)for v,weight in zip(f,w)),b),F(n),b)for k in (0,1))
                    grid[i,j]=point;node(pid,point,fid,True)
            seeds=[]
            for i in range(n):
                for j in range(n-i):
                    seeds.append((i,j,0,[grid[i,j],grid[i+1,j],grid[i,j+1]]))
                    if j<n-i-1:seeds.append((i,j,1,[grid[i+1,j],grid[i+1,j+1],grid[i,j+1]]))
            for i,j,which,points in seeds:
                b.take('triangles');parentid='mrp:p'+str(len(parents));childids=[]
                polys=_cells(points,sorted(cuts[pid]),b)
                for poly in polys:
                    cid='mrp:c'+str(len(cells));faces=[]
                    for tri in _ears(poly,b):faces.append(add_triangle(pid,fid,tri,cid))
                    cells.append({'id':cid,'domain_id':pid,'source_face_id':fid,'parent_seed_id':parentid,
                        'polygon_nodes':[node(pid,p,fid)for p in poly],'triangle_ids':faces})
                    childids.append(cid)
                parents.append({'id':parentid,'domain_id':pid,'source_face_id':fid,
                    'integer_lattice':[i,j,which],'subdivisions':n,'nodes':[node(pid,p,fid,True)for p in points],
                    'child_cell_ids':childids})
    # Insertions never infer supports from a rounded UV or introduce seams.
    for sample in samples:
        r=sample['definition'];pid=r['domain_id'];point=sample['point']
        if r['role']!='reference_node':continue
        if (pid,point)in nodes:
            sample['node_key']=(pid,point);continue
        hits=[]
        for t in active:
            if not t['active']or t['domain_id']!=pid:continue
            b.take('pair_checks');pts=[nodes[k]['uv_cm']for k in t['nodes']];weights=_bary(point,pts,b)
            if min(weights)>=0:hits.append((t,pts,weights))
        if not hits:_refuse('CERTIFICATE_INVALID','reference insertion not covered by actual material triangles')
        children=[];parentrows=[]
        for t,pts,weights in hits:
            t['active']=False;parentrows.append({'id':t['id'],'nodes':t['nodes'],'parent':t['parent'],'source_face_id':t['source_face_id']})
            before_area=_signed_area(pts,b);made=[]
            for slot in range(3):
                a,c=pts[slot],pts[(slot+1)%3]
                if _cross(a,c,point,b):
                    tid=add_triangle(pid,t['source_face_id'],[a,c,point],r['id']);children.append(tid);made.append([a,c,point])
            if _sum((_signed_area(tr,b)for tr in made),b)!=before_area:
                _refuse('CERTIFICATE_INVALID','inserted children do not cover actual parent')
        sample['node_key']=(pid,point)
        insertions.append({'sample_id':r['id'],'domain_id':pid,'parent_triangles':parentrows,'child_triangle_ids':children})
    ordered=sorted(nodes);node_indices={key:i for i,key in enumerate(ordered)}
    outnodes=[{'id':'mrp:n'+str(i),**nodes[key]}for i,key in enumerate(ordered)]
    def indices(keys):return [node_indices[k]for k in keys]
    for p in parents:p['nodes']=indices(p['nodes'])
    for c in cells:c['polygon_nodes']=indices(c['polygon_nodes'])
    for insertion in insertions:
        for p in insertion['parent_triangles']:p['nodes']=indices(p['nodes'])
    final=[]
    for t in active:
        if t['active']:final.append({k:indices(v)if k=='nodes'else v for k,v in t.items()if k!='active'})
    views=defaultdict(list)
    for i,t in enumerate(final):views[(t['domain_id'],t['source_face_id'])].append(i)
    outviews=[{'domain_id':pid,'source_face_id':fid,'triangle_indices':ids,
        'node_indices':sorted({v for i in ids for v in final[i]['nodes']})}for (pid,fid),ids in sorted(views.items())]
    outsamples=[{'id':s['definition']['id'],'definition':s['definition'],'exact_uv_cm':s['point'],
        'reference_node_index':node_indices[s['node_key']]if 'node_key'in s else None}for s in samples]
    normalized={'sources':data['sources'],'sections':sectionrows,
        'subdivisions':n,'material_samples':[s['definition']for s in samples],'binding':binding}
    return {'discriminant':DISCRIMINANT,'version':1,'status':'UV_REFERENCE_PREPARED_TEST_ONLY',
        'purpose':'TEST_ONLY','qualification':'NONE','uv_certificate':'EXACT_CONSTRUCTIVE_SOURCE_REFINEMENT',
        'input_payload':normalized,'source_tables':[s['raw']for s in sources.values()],
        'code_sources':code,'global_nodes':outnodes,'seed_parents':parents,
        'section_cells':cells,'insertion_steps':insertions,'global_triangles':final,'work_views':outviews,
        'triangle_archive':[{k:indices(v)if k=='nodes'else v for k,v in t.items()}for t in active],
        'material_samples':outsamples,'pins':[],'generated_seams':[],
        'fresh_reference':'NOT_CREATED','surface_3d':'NOT_IMPLEMENTED','seam_coupling':'NOT_IMPLEMENTED',
        'metric':'NOT_ASSESSED','fitting':'NOT_EXECUTED','physical_mesh':False,'is_installable':False,
        'receipt_elapsed_scope':'SNAPSHOT_BEFORE_COMPLETE_OUTPUT_SERIALIZATION_TERMINAL_DEADLINE_STILL_CHECKED',
        'reference_policy':'NEW_CANDIDATE_AND_RUN_ONLY_NO_EXISTING_S_FRESH_REPLACEMENT_OR_BUDGET_RESET',
        'external_recipe_body_binding_scope':'DECLARED_IDENTITIES_ONLY_NO_FILE_OR_3D_VALIDATION',
        'budget_contract':'ONE_GLOBAL_LEDGER_CONSTRUCTION_AND_VERIFICATION_NO_PER_VIEW_RESET'}


def _capture(originals,budgets,deadline,clock):
    b=_Budget(budgets,deadline,clock);copied=accounting._snapshot(originals,b)
    before=accounting._hash(copied,b,'snapshot')
    if accounting._hash(originals,b,'original')!=before:_refuse('REFERENCE_MUTATION','inputs changed during capture')
    return copied,before,b


def _equal(actual,expected,b):
    # Count the revalidation traversal explicitly, without a second output.
    b.take('input_nodes')
    if isinstance(expected,F):return type(actual)is str and actual==str(_q(expected,b))
    if type(expected)is dict:
        return type(actual)is dict and set(actual)==set(expected) and all(_equal(actual[k],v,b)for k,v in expected.items())
    if type(expected)in(list,tuple):
        return type(actual)is list and len(actual)==len(expected) and all(_equal(a,c,b)for a,c in zip(actual,expected))
    return type(actual)is type(expected) and actual==expected


def prepare_material_reference_partition(sources,sections,subdivisions,binding,*,material_samples=None,
        budgets=None,deadline=None,clock=time.monotonic):
    """Prepare exact UV only, with a complete replayable construction record."""
    data={'sources':sources,'sections':sections,'subdivisions':subdivisions,
        'material_samples':[]if material_samples is None else material_samples,'binding':binding}
    originals=[data,budgets,deadline]
    try:
        copied,before,b=_capture(originals,budgets,deadline,clock);result=_build(copied[0],b)
        if _code_sources(b)!=result['code_sources']:_refuse('INVALIDATION_REQUIRED','dependency code changed during preparation')
        return accounting._finish(result,originals,before,b,{'actual_normalized_source_meshes':accounting._hash(result['input_payload']['sources'],b,'source_meshes'),'code_sources':accounting._hash(result['code_sources'],b,'code_sources')})
    except StudioError as error:raise accounting._normalize_error(error)


def verify_material_reference_partition(compiled,*,budgets=None,deadline=None,clock=time.monotonic):
    """Replay every source/parent/cell/insertion; cached flags never suffice."""
    originals=[compiled,budgets,deadline]
    try:
        copied,before,b=_capture(originals,budgets,deadline,clock);actual=copied[0]
        if type(actual)is not dict or actual.get('discriminant')!=DISCRIMINANT or 'input_payload'not in actual:
            _refuse('INVALID_CERTIFICATE','typed complete reference certificate required')
        expected=_build(actual['input_payload'],b)
        body={k:v for k,v in actual.items()if k!='receipt'}
        if not _equal(body,expected,b):_refuse('CERTIFICATE_INVALID','source/parent/children/tables differ from exact reconstruction')
        if _code_sources(b)!=expected['code_sources']:_refuse('INVALIDATION_REQUIRED','dependency code changed during verification')
        expected['status']='CERTIFICATE_VERIFIED_TEST_ONLY'
        return accounting._finish(expected,originals,before,b,{'certificate':accounting._hash(body,b,'certificate')})
    except StudioError as error:raise accounting._normalize_error(error)
