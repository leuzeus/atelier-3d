"""Homologous seam-line measurements and bounded proposals; never edit patterns."""
import math
import copy
from dataclasses import dataclass
from .core import StudioError, contract, digest
from .sewing import edge_chain, sample_chain, chain_lengths, point_inside, segment_distance


def _path_inside_engine(a,b,polygon,intersection_edges,edge_pairs):
    cross=lambda u,v:u[0]*v[1]-u[1]*v[0]
    d=[b[k]-a[k] for k in range(2)];cuts={0.,1.}
    for x,y,e in intersection_edges():
        v=[x[k]-a[k] for k in range(2)];den=cross(d,e)
        if abs(den)>1e-12:
            t,u=cross(v,e)/den,cross(v,d)/den
            if 0<=t<=1 and 0<=u<=1:cuts.add(t)
        elif abs(cross(v,d))<1e-10:
            norm=sum(z*z for z in d)
            if norm>1e-20:
                cuts.update(max(0.,min(1.,sum((p[k]-a[k])*d[k] for k in range(2))/norm)) for p in (x,y))
    values=sorted(cuts)
    for lo,hi in zip(values,values[1:]):
        p=[a[k]+(lo+hi)/2*d[k] for k in range(2)]
        if not point_inside(p,polygon) and min(segment_distance(p,x,y) for x,y in edge_pairs())>1e-7:return False
    return True


def path_inside(a,b,polygon):
    """Split at every boundary intersection; check each open interval."""
    pairs=lambda:zip(polygon,polygon[1:]+polygon[:1])
    intersections=lambda:((x,y,[y[k]-x[k]for k in range(2)])for x,y in pairs())
    return _path_inside_engine(a,b,polygon,intersections,pairs)


@dataclass(frozen=True)
class _PreparedPathContour:
    polygon:tuple
    pairs:tuple
    intersections:tuple
    complete:bool

    def path_inside(self,a,b):
        if self.complete:
            intersections=lambda:iter(self.intersections)
        else:
            # Unsupported or overflowing constant arithmetic remains lazy, so
            # the query raises the same error at the same stage as path_inside.
            intersections=lambda:((x,y,e if e is not None else[y[k]-x[k]for k in range(2)])
                                  for x,y,e in self.intersections)
        return _path_inside_engine(a,b,self.polygon,intersections,lambda:iter(self.pairs))


def prepare_path_contour(polygon,*,max_edges=None,check_time=None):
    """Copy one local contour; reuse only query-independent edge differences.

    The source points are not coerced or rounded. Query direction, its lazy
    norm, cuts, point_inside and segment_distance retain the historical engine.
    This is not a query cache, spatial index or geometry/fit admission.
    """
    if max_edges is not None and(type(max_edges)is not int or max_edges<0 or len(polygon)>max_edges):
        raise StudioError('Prepared material contour edge budget exhausted or invalid')
    def check():
        if check_time is not None:check_time()
    check();snapshot=[]
    for point in polygon:
        check()
        copied=copy.deepcopy(point)
        # Retain malformed sequence types for their original lazy error text;
        # measurement contours are validated two-coordinate numeric points.
        snapshot.append(tuple(copied)if isinstance(copied,(list,tuple))and len(copied)>=2 else copied)
    snapshot=tuple(snapshot);pairs=tuple(zip(snapshot,snapshot[1:]+snapshot[:1]));rows=[]
    for x,y in pairs:
        check();difference=None
        try:
            if all(type(point[k])in(int,float,bool)for point in (x,y)for k in range(2)):
                difference=tuple(y[k]-x[k]for k in range(2))
        except (IndexError,KeyError,TypeError,ValueError,OverflowError):
            pass
        rows.append((x,y,difference))
    check()
    return _PreparedPathContour(snapshot,pairs,tuple(rows),all(row[2]is not None for row in rows))


def section_loop(vertices, faces, section):
    """Horizontal section, choose one closed loop by a declared interior seed."""
    height=section['height_cm'];segments=set();ambiguous=False
    for face in faces:
        points=[]
        for a,b in zip(face,face[1:]+face[:1]):
            pa,pb=vertices[a],vertices[b];da,db=pa[2]-height,pb[2]-height
            if abs(da)<1e-8 and abs(db)<1e-8:ambiguous=True;continue
            if (da<=0<db) or (db<=0<da):
                t=da/(da-db);points.append(tuple(round(pa[k]+t*(pb[k]-pa[k]),5) for k in (0,1)))
        points=list(dict.fromkeys(points))
        if len(points)==2:segments.add(tuple(sorted(points)))
        elif points:ambiguous=True
    graph={}
    for a,b in segments:graph.setdefault(a,set()).add(b);graph.setdefault(b,set()).add(a)
    unseen=set(graph);loops=[]
    while unseen:
        seed=min(unseen);stack=[seed];component=set()
        while stack:
            p=stack.pop()
            if p in component:continue
            component.add(p);stack.extend(graph[p]-component)
        unseen-=component;closed=all(len(graph[p])==2 for p in component);polygon=[]
        if closed:
            previous=None;current=seed
            while current not in polygon:
                polygon.append(current);following=min(n for n in graph[current] if n!=previous)
                previous,current=current,following
            closed=current==seed and len(polygon)==len(component)
        loops.append({'closed':closed,'contains_seed':closed and point_inside(section['seed_xy_cm'],polygon),
            'circumference_cm':sum(math.dist(a,b) for a,b in segments if a in component and b in component) if closed else None,
            'points':len(component),'x_range_cm':[min(p[0] for p in component),max(p[0] for p in component)]})
    selected=[l for l in loops if l['closed'] and l['contains_seed']]
    valid=len(selected)==1 and not ambiguous
    return {'status':'MEASURED' if valid else 'NOT_QUALIFIED','loops':loops,
        'circumference_cm':selected[0]['circumference_cm'] if valid else None,'coplanar_or_ambiguous':ambiguous,
        'numerical_error_bound_cm':math.sqrt(2)*.00001*selected[0]['points'] if valid else None,
        'section':section,'method':'closed surface loop containing declared seed; other loops excluded'}


def pattern_capacity(data, measurement):
    path=measurement.get('pattern_path',[]);joins=measurement.get('joins',[])
    if not path or len(path)!=len(joins):return {'status':'NOT_QUALIFIED','missing':['closed homologous pattern path and joins']}
    seam_by_id={s['id']:s for s in data['seams']};anchors=[];lengths=[];seen=set()
    for segment in path:
        pid=segment['piece'];piece=data['pieces'].get(pid)
        if piece is None:raise StudioError('Unknown fitting pattern piece')
        start,end=segment['from'],segment['to']
        key=(pid,start['edge'],start['t'],end['edge'],end['t'])
        if key in seen:raise StudioError('Duplicate fitting path segment; symmetry would be counted twice')
        seen.add(key)
        ends=[sample_chain(edge_chain(piece,a['edge'])[1],a['t']) for a in (start,end)]
        points=[ends[0],*segment.get('via_cm',[]),ends[1]]
        # Explicit seam-line paths inside the source polygon, including concave
        # crossings. Endpoints may lie on its boundary, margins are never read.
        polygon=piece['vertices']
        for a,b in zip(points,points[1:]):
            if not path_inside(a,b,polygon):raise StudioError('Fitting measurement path leaves the seam-line polygon')
        lengths.append(chain_lengths(points)[-1]);anchors.append((start,end))
    for i,sid in enumerate(joins):
        seam=seam_by_id.get(sid)
        if seam is None:raise StudioError('Unknown fitting path seam')
        if seam.get('kind','permanent')=='detachable':raise StudioError('Detachable link cannot certify a closed fitting path')
        left,right=path[i],path[(i+1)%len(path)];a,b=anchors[i][1],anchors[(i+1)%len(path)][0]
        if (left['piece'],a['edge'],right['piece'],b['edge'])==(seam['piece_a'],seam['edge_a'],seam['piece_b'],seam['edge_b']):ta,tb=a['t'],b['t']
        elif (left['piece'],a['edge'],right['piece'],b['edge'])==(seam['piece_b'],seam['edge_b'],seam['piece_a'],seam['edge_a']):ta,tb=b['t'],a['t']
        else:raise StudioError('Fitting path does not join homologous seam anchors')
        expected=1-ta if seam['orientation']=='reverse' else ta
        if abs(tb-expected)>1e-6:raise StudioError('Fitting path anchor orientation mismatch')
    takeup=sum(item['amount_cm'] for item in measurement.get('takeup',[]));capacity=sum(lengths)-takeup
    if capacity<=0:raise StudioError('Fitting take-up consumes the entire capacity')
    return {'status':'MEASURED','capacity_cm':capacity,'segment_lengths_cm':lengths,'takeup_cm':takeup,
        'basis':'source seam-line paths, not cutting allowances','path_sha256':digest({'path':path,'joins':joins,'takeup':measurement.get('takeup',[])})}


def compare_fit(data, plan, body_sections, envelope_sections):
    contract('fitting-plan',plan);rows=[]
    if len({m['id'] for m in plan['measurements']})!=len(plan['measurements']):raise StudioError('Duplicate fitting measurement')
    for m in plan['measurements']:
        missing=[];body=body_sections.get(m['id']);envelope=envelope_sections.get(m['id']);capacity=pattern_capacity(data,m)
        if m['landmark_status']!='validated':missing.append('validated homologous landmarks')
        if plan.get('body',{}).get('role')!='target':missing.append('identified target body, not a proxy')
        if not body or body['status']!='MEASURED':missing.append('unambiguous body section')
        if not envelope or envelope['status']!='MEASURED':missing.append('unambiguous collision envelope section')
        if capacity['status']!='MEASURED':missing+=capacity['missing']
        if 'ease_cm' not in m:missing.append('declared ease')
        if 'envelope_clearance_girth_cm' not in m:missing.append('declared envelope/tissue clearance in girth units')
        target=None;delta=None;status='NOT_QUALIFIED';uncertainty=m['uncertainty_cm']
        if not missing:
            target=max(body['circumference_cm']+m['ease_cm'],envelope['circumference_cm']+m['envelope_clearance_girth_cm'])
            delta=target-capacity['capacity_cm'];uncertainty=m['uncertainty_cm']+max(body.get('numerical_error_bound_cm',0),envelope.get('numerical_error_bound_cm',0))
            if m['target_kind']=='style_only':status='STYLE_DELTA'
            elif delta>uncertainty:status='DEFICIT_MEASURED'
            elif delta>=-uncertainty:status='INDETERMINATE'
            else:status='CAPACITY_SUFFICIENT'
        rows.append({'id':m['id'],'status':status,'missing':missing,'body':body,'envelope':envelope,
            'pattern':capacity,'required_cm':target,'deficit_cm':delta,'uncertainty_cm':m['uncertainty_cm'],
            'effective_uncertainty_cm':uncertainty,
            'ease_cm':m.get('ease_cm'),'envelope_clearance_girth_cm':m.get('envelope_clearance_girth_cm'),
            'target_kind':m['target_kind'],'source_ref':m['source_ref']})
    status='INCOMPATIBLE' if any(r['status']=='DEFICIT_MEASURED' for r in rows) else 'CAPACITY_SUFFICIENT' if rows and all(r['status']=='CAPACITY_SUFFICIENT' for r in rows) else 'NOT_QUALIFIED'
    return {'fit_status':status,'rows':rows,'accepted':False,'simulation':'NOT_EXECUTED','visual_validation':'NOT_EXECUTED',
        'note':'Capacity comparison only; does not certify worn fitting, dynamics or artistic acceptance. Seam allowances are not ease.'}


def propose_adjustments(data, plan, report):
    proposals=[];unproposed=[]
    for row in report['rows']:
        if row['status']!='DEFICIT_MEASURED':continue
        measurement=next(m for m in plan['measurements'] if m['id']==row['id']);sites=measurement.get('adjustment_sites',[])
        if not sites or abs(sum(s['share'] for s in sites)-1)>1e-6:
            unproposed.append({'measurement':row['id'],'reason':'MISSING_OR_UNBALANCED_ADJUSTMENT_SITES'});continue
        keys=[(s['piece'],s['edge']) for s in sites]
        if len(set(keys))!=len(keys):raise StudioError('Duplicate adjustment site; no implicit symmetry multiplication')
        changes=[]
        for site in sites:
            edge_chain(data['pieces'][site['piece']],site['edge'])
            delta=row['deficit_cm']*site['share']
            dependencies=[s for s in data['seams'] if (site['piece'],site['edge']) in ((s['piece_a'],s['edge_a']),(s['piece_b'],s['edge_b']))]
            changes.append({**site,'capacity_increment_cm':delta,'within_declared_limit':delta<=site['max_capacity_increment_cm'],
                'dependent_seams':dependencies})
        proposals.append({'measurement':row['id'],'required_capacity_increment_cm':row['deficit_cm'],'sites':changes,
            'status':'PROPOSED_NOT_APPLIED' if all(c['within_declared_limit'] for c in changes) else 'OUTSIDE_DECLARED_LIMITS',
            'requirements':['derive a separate source-pattern variant','preserve smooth curves, grain and paired seam ease',
                'remeasure capacity and validate all dependent seams','review exact changed board before production'],
            'note':'Capacity allocation in cm, not an automatic seam offset. No pattern or rest shape was edited.'})
    return {'proposals':proposals,'unproposed':unproposed,'source_garment_sha256':digest(data),'plan_sha256':digest(plan),'accepted':False,'applied':False}
