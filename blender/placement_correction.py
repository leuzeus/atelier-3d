"""Native measured-contact adapter for the bounded source-preserving solver.

Exploratory corrections may still intersect the body. Only the unchanged final
preparation validator decides READY; this adapter never approves a garment.
"""
import copy
import math

from a3d.core import StudioError,contract,digest
from a3d.placement_solver import solve_placement
from a3d.cloth_metrics import validate_metrics
from a3d.guide_metric_solver import recover_guide_metric
from a3d.contact_geometry import cross,dot,norm,sub


def effective_quality(recipe,plan,preparation,specification):
    requested=specification['quality'];declared=plan['quality'];source=recipe['mesh']
    limits={key:max(source[key],declared[key],requested[key]) for key in ('min_angle_degrees','min_edge_cm','min_stretch')}
    limits['min_angle_degrees']=max(limits['min_angle_degrees'],preparation['regular_mesh'].get('target_min_angle_degrees',15.))
    limits['max_stretch']=min(source['max_stretch'],declared['max_stretch'],requested['max_stretch'])
    return limits


def native_measurement(payload,coordinates,context,limits,plan):
    """Exact static gates, plus measured surface-normal proposals for search."""
    from mathutils import Vector
    from blender.cloth_contacts import check_contacts
    from blender.pattern_assembly import collision_check
    contact=check_contacts(context,coordinates)
    if contact.get('reason') in ('CONTACT_PAIR_BUDGET','COLLIDER_GEOMETRY_CHANGED','COLLIDER_VOLUME_ORIENTATION','COLLIDER_UNAVAILABLE'):
        error=StudioError('Native placement contact coverage is incomplete: '+contact['reason'])
        error.contact_report=contact;error.reason_category='contact_context';raise error
    proposals=[];deficits={};clearance=context['clearance_cm']
    for body in context['bodies']:
        for index,point in enumerate(coordinates):
            hit,normal,face,_=body['tree'].find_nearest(Vector([v/100 for v in point]))
            if hit is None:continue
            signed=collision_check([point],[body['tree']],[body['snapshot']],clearance,
                surface_triangles=[body['triangles']]) if body['closed'] else None
            if signed and signed['ambiguous_sign_count']:continue
            distance=signed['minimum_signed_offset_cm'] if signed else math.dist(point,[v*100 for v in hit])
            # This is collision_check's existing numerical decision margin,
            # not an added contact reserve or a changed acceptance threshold.
            deficit=max(0.,clearance-distance-1e-6)
            if deficit:
                proposals.append({'vertex':index,'normal':list(normal.normalized()),'signed_offset_cm':distance,
                    'clearance_cm':clearance,'collider':body['name'],'collider_triangle':face,
                    'proposal_measurement':'MEASURED_NEAREST_SURFACE_NORMAL'})
                deficits[index]=max(deficits.get(index,0.),deficit)
    # A face may intersect a body while its vertices are exterior. Preserve
    # the precise face witness and calculate an exploratory face-plane move.
    for row in contact.get('contacts',[]):
        body=next(b for b in context['bodies'] if b['name']==row['collider'])
        triangle=body['triangles'][row['collider_triangle']]
        normal=cross(sub(triangle[1],triangle[0]),sub(triangle[2],triangle[0]));length=norm(normal)
        if not length:continue
        normal=[v/length for v in normal]
        witness=row['point_b_cm']
        for index in row['vertices']:
            offset=dot(sub(coordinates[index],witness),normal)
            if offset<clearance:
                proposals.append({'vertex':index,'normal':normal,'signed_offset_cm':offset,'clearance_cm':clearance,
                    'collider':body['name'],'collider_triangle':row['collider_triangle'],
                    'proposal_measurement':'PRECISE_CONTACT_TRIANGLE_PLANE_WITNESS_EXPLORATORY'})
                # Several collider triangles can witness the same source
                # vertex. Count its largest measured deficit once: a change
                # in broadphase pair count must not create a score barrier
                # while the actual penetration is continuously decreasing.
                deficits[index]=max(deficits.get(index,0.),clearance-offset)
    metrics_ok=True;violations=[]
    try:validate_metrics(payload,coordinates,limits,include_faces=False,include_bending=False)
    except StudioError as error:metrics_ok=False;violations=getattr(error,'quality_violations',[str(error)])
    pairs=[pair for seam in payload['seams'].values() if seam['kind']=='permanent' for pair in seam['pairs']]
    gap=max((math.dist(coordinates[a],coordinates[b]) for a,b in pairs),default=0.)
    gap_deficit=max(0.,gap-plan['assembly']['max_initial_gap_cm'])
    self_count=contact.get('self_contact',{}).get('contact_count',0)
    score=sum(deficits.values())+gap_deficit+self_count*max(clearance,.001)
    return {'candidate_sha256':digest(coordinates),'hard_valid':contact['ok'] and metrics_ok and gap_deficit<=1e-8,
            'score':score,'contacts':proposals,'static_contact':contact,'metric_violations':violations,
            'permanent_max_gap_cm':gap,'sewing_qualification':'NOT_EXECUTED',
            'score_vertex_deficits_cm':{str(index):deficits[index] for index in sorted(deficits)},
            'proposal_scope':'MEASURED_NORMAL_SEARCH_ONLY_FINAL_STATIC_CONTACT_GATES_UNCHANGED'}


def correct_preparation(payload,recipe,plan,preparation,colliders):
    """Return a disposable candidate and exact observations; do not mutate inputs."""
    from blender.cloth_contacts import build_contact_context
    declared=preparation.get('placement_correction')
    if declared is None:return None
    contract('placement-correction',declared)
    before=digest([payload,recipe,plan,preparation])
    specification=copy.deepcopy(declared)
    specification['quality']=effective_quality(recipe,plan,preparation,declared)
    specification['budgets']['max_displacement_cm']=min(declared['budgets']['max_displacement_cm'],plan['assembly']['max_displacement_cm'])
    specification['budgets']['max_step_cm']=min(declared['budgets']['max_step_cm'],plan['assembly']['max_step_cm'])
    specification['budgets']['max_iterations']=min(declared['budgets']['max_iterations'],plan['assembly']['iterations'])
    context=build_contact_context(payload,colliders,clearance_cm=plan['collision']['clearance_cm'],
        seam_tolerance_cm=plan['consolidation']['weld_gap_cm'],check_self=True)
    source_guide=copy.deepcopy(payload['placed_cm']);candidate=copy.deepcopy(payload);metric_recovery=None
    recovery=preparation.get('metric_recovery')
    if recovery:
        contract('pattern-preparation',preparation)
        budgets=copy.deepcopy(recovery['budgets'])
        budgets['max_displacement_cm']=min(budgets['max_displacement_cm'],specification['budgets']['max_displacement_cm'])
        # Both numerical recovery and contact correction spend the same eight
        # centimetres (or stricter declared limit) from the original guide.
        metric_recovery=recover_guide_metric(candidate,source_guide,specification['quality'],
            recovery['piece_ids'],recovery['protected_edges'],strain_weight=recovery['strain_weight'],
            protected_indices=specification.get('protected_indices',[]),
            **({key:copy.deepcopy(recovery[key])for key in ('seam_ids','max_initial_seam_gap_cm')}
               if 'seam_ids'in recovery else {}),**budgets)
        candidate['placed_cm']=copy.deepcopy(metric_recovery['coordinates_cm'])
        source_stops=[]
        for stop in recovery['protected_edges']:
            ids=candidate['panels'][stop['piece']]['edges'][stop['edge']];source_stops.extend((ids[0],ids[-1]))
        specification['protected_indices']=sorted(set(specification.get('protected_indices',[]))|set(source_stops))
        prep_limits={key:max(recipe['mesh'][key],plan['quality'][key])
            for key in ('min_angle_degrees','min_edge_cm','min_stretch')}
        prep_limits['max_stretch']=min(recipe['mesh']['max_stretch'],plan['quality']['max_stretch'])
        prep_limits['min_angle_degrees']=max(prep_limits['min_angle_degrees'],preparation['regular_mesh'].get('target_min_angle_degrees',15.))
        try:
            prep_metric=validate_metrics(candidate,candidate['placed_cm'],prep_limits,include_faces=False,include_bending=False)
            prep_valid=True
        except StudioError as error:prep_metric=error.quality_metrics;prep_valid=False
        metric_recovery['source_preparation_metric']={'valid':prep_valid,'quality':prep_limits,'metric':prep_metric}
        metric_recovery['contact_search_metric']={'valid':metric_recovery['status']=='SOURCE_METRIC_RECOVERED',
            'quality':copy.deepcopy(specification['quality'])}
        metric_recovery['shared_displacement_reference_sha256']=digest(source_guide)
    if metric_recovery and metric_recovery['status']!='SOURCE_METRIC_RECOVERED':
        measured=native_measurement(candidate,candidate['placed_cm'],context,specification['quality'],plan)
        result={'version':1,'status':'NEEDS_CORRECTION','stop_reason':'METRIC_RECOVERY_'+metric_recovery['stop_reason'],
            'coordinates_cm':copy.deepcopy(candidate['placed_cm']),'measurement':measured,'history':[],
            'contact_search':'NOT_STARTED_INVALID_SOURCE_METRIC','iterations':0,'metric_recovery':metric_recovery,
            'candidate_sha256':digest(candidate['placed_cm']),'source_sha256':digest(payload),
            'max_displacement_cm':metric_recovery['max_displacement_cm'],
            'source_mutated':False,'qualification':'NONE','simulation':'NOT_EXECUTED','fitting':'NOT_EXECUTED'}
    else:
        result=solve_placement(candidate,candidate['placed_cm'],
            lambda source,coords:native_measurement(source,coords,context,specification['quality'],plan),specification,
            displacement_reference=source_guide)
        if metric_recovery:result['metric_recovery']=metric_recovery
    if digest([payload,recipe,plan,preparation])!=before:
        raise StudioError('Native placement correction mutated an immutable source or policy')
    result.update(origin='NATIVE_MEASURED_CONTACT_CORRECTION',source_package_sha256=payload['package_sha256'],
        declared_specification_sha256=digest(declared),effective_specification=specification,
        colliders=[{'object':body['name'],'evaluated_surface_sha256':body['sha256']} for body in context['bodies']],
        candidate_not_automatically_admitted=True,final_readiness='UNCHANGED_PREPARATION_VALIDATOR_REQUIRED')
    return result
