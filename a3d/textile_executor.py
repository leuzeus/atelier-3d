"""Source-piece/group adapters for the existing native textile kernels.

Group meshes are disposable derived maps, never canonical asset components or
replacement packages. Every face retains component, piece, original face and
source UV. Only actual approved permanent pairs may consolidate. Closures and
detachable links remain separate. Native execution is prepared separately.
"""
import copy
import json
import math
import zipfile

from .cloth_metrics import face_sources
from .core import StudioError, contract, digest, inside, read_json, sha
from .dressing import _reference, sewing_graph_digest
from .pattern_assembly import (map_digest, validate_plan, consolidate, continuous_quality,
                               _vertex_manifold)
from .cloth_metrics import validate_linear_motion
from .piece_inventory import face_piece_ids


STAGES = ('preposition', 'mount', 'close', 'consolidate', 'relax', 'drape')
TEMPLATE_NUMERIC_POLICY={'version':1,'derived_decimal_places':8,
    'scope':'COMPUTED_RIGID_SEED_AND_AUDIT_OBSERVATIONS_ONLY',
    'source_coordinates':'EXACT_UNCHANGED','source_guides':'EXACT_UNCHANGED',
    'body_receipts':'EXACT_UNCHANGED','gate_evaluation':'UNROUNDED_UNCHANGED'}


def _template_audit_observations(report):
    """Canonicalise computed observations after the unchanged source audit.

    CPython 3.12 changed float summation. These derived display quantities and
    seed instructions use a declared sub-nanometre decimal grid; copied source
    stops, contours, grain, policy values and all hashes retain exact values.
    The audit's decisions are computed before this serialization step.
    """
    result=copy.deepcopy(report)
    for panel in result['panels'].values():
        for key in ('area_cm2','signed_area_cm2','perimeter_cm','source_segment_min_cm','source_segment_max_cm'):
            panel[key]=round(panel[key],TEMPLATE_NUMERIC_POLICY['derived_decimal_places'])
        panel['source_dimensions_cm']=[round(value,TEMPLATE_NUMERIC_POLICY['derived_decimal_places'])
            for value in panel['source_dimensions_cm']]
        for edge in panel['named_edges'].values():
            edge['length_cm']=round(edge['length_cm'],TEMPLATE_NUMERIC_POLICY['derived_decimal_places'])
    for seam in result['seams']:
        for key in ('length_a_cm','length_b_cm','residual_relative'):
            seam[key]=round(seam[key],TEMPLATE_NUMERIC_POLICY['derived_decimal_places'])
    return result


def _guide_seed_placement(piece, frame, piece_id):
    """A rigid source plane derived from the target guide; no fitted UV scale."""
    from .anatomy_profile import unit
    from .contact_geometry import cross, dot
    from .pattern_assembly import _compile_arc_sections, _section_point, _compile_cage, _cage_point
    vertices = piece['vertices']
    # A real source vertex, plus local derivatives within the sourced UV domain.
    pivot = min(vertices, key=lambda p: (p[1], p[0]))
    if 'arc_sections' in frame:
        compiled = _compile_arc_sections(frame, piece_id)
        def at(uv): return _section_point(frame, compiled, uv, piece_id)[0]
        target = at(pivot); directions = []
        for axis in (0, 1):
            derivative = None
            for sign in (1, -1):
                trial = list(pivot); trial[axis] += sign*.001
                try:
                    point = at(trial)
                    derivative = unit([(point[k]-target[k])*sign for k in range(3)]); break
                except StudioError: pass
            if derivative is None:
                raise StudioError('Source guide lacks a finite tangent seed: '+piece_id)
            directions.append(derivative)
        u = directions[0]
        v = unit([directions[1][k]-dot(directions[1],u)*u[k] for k in range(3)])
    elif 'uv_cm' in frame:
        compiled = _compile_cage(frame, piece_id)
        target, binding = _cage_point(frame, compiled, pivot, piece_id)
        # Differentiate the actual containing source triangle. Sampling along
        # U/V outside a beveled source corner would invent a guide extension.
        _, indices, a, b, c, denominator = compiled[binding['cage_triangle']]
        ta, tb, tc = [frame['target_cm'][index] for index in indices]
        du = [((tb[k]-ta[k])*(c[1]-a[1])-(tc[k]-ta[k])*(b[1]-a[1]))/denominator for k in range(3)]
        dv = [(-(tb[k]-ta[k])*(c[0]-a[0])+(tc[k]-ta[k])*(b[0]-a[0]))/denominator for k in range(3)]
        u = unit(du)
        v = unit([dv[k]-dot(dv,u)*u[k] for k in range(3)])
    elif 'origin_cm' in frame:
        u = unit(frame['u_axis']); v = unit(frame['v_axis'])
        offset = frame.get('offset_uv_cm', [0.,0.])
        target = [frame['origin_cm'][k]+(pivot[0]-offset[0])*u[k]+(pivot[1]-offset[1])*v[k] for k in range(3)]
    else:
        raise StudioError('Source guide requires an explicit supported tangent seed: '+piece_id)
    normal = unit(cross(u,v))
    # Blender XYZ Euler rotation, columns are the orthonormal material axes.
    ry = math.asin(max(-1.,min(1.,-u[2])))
    if abs(math.cos(ry)) > 1e-8:
        rx = math.atan2(v[2],normal[2]); rz = math.atan2(u[1],u[0])
    else:
        rx = math.atan2(-normal[1],v[1]); rz = 0.
    return {'mode':'flat', 'position_cm':[round(target[k]-pivot[0]*u[k]-pivot[1]*v[k],
                TEMPLATE_NUMERIC_POLICY['derived_decimal_places']) for k in range(3)],
            'rotation_degrees':[round(math.degrees(value),TEMPLATE_NUMERIC_POLICY['derived_decimal_places']) for value in (rx,ry,rz)],
            'radius_cm':1., 'origin_2d_cm':[0.,0.]}


def _project_component_layers(source,own):
    layers=copy.deepcopy(source);ancestors={node['id']:set() for node in source['nodes']}
    for inner,outer in source['inside_to_outside']:ancestors[outer].add(inner)
    for _ in ancestors:
        for outer in ancestors:
            ancestors[outer].update(set().union(*(ancestors[parent] for parent in list(ancestors[outer]))))
    for node in layers['nodes']:node['panels']=[pid for pid in node['panels'] if pid in own]
    layers['nodes']=[node for node in layers['nodes'] if node['kind']=='body' or node['panels'] or node['colliders']]
    kept={node['id'] for node in layers['nodes']}
    # Preserve already-proven paths through layers absent from this component.
    layers['inside_to_outside']=[[inner,outer] for outer in sorted(kept) for inner in sorted(ancestors[outer]&kept)]
    return layers


def _guide_preform_bound(piece,frame,placement):
    """Conservative flat-seed to declared-guide envelope, before execution."""
    rx,ry,rz=[math.radians(value) for value in placement['rotation_degrees']]
    u=[math.cos(rz)*math.cos(ry),math.sin(rz)*math.cos(ry),-math.sin(ry)]
    v=[math.cos(rz)*math.sin(ry)*math.sin(rx)-math.sin(rz)*math.cos(rx),
        math.sin(rz)*math.sin(ry)*math.sin(rx)+math.cos(rz)*math.cos(rx),math.cos(ry)*math.sin(rx)]
    initial=[[placement['position_cm'][k]+p[0]*u[k]+p[1]*v[k] for k in range(3)] for p in piece['vertices']]
    if 'arc_sections' in frame or 'uv_cm' in frame:
        if 'uv_cm' in frame:
            from .pattern_assembly import _compile_cage
            _compile_cage(frame,'preform-budget');targets=frame['target_cm']
            method='AFFINE_SOURCE_BOUNDARY_AND_CONVEX_BARYCENTRIC_TARGET_ENVELOPE'
        else:
            targets=[point for section in frame['arc_sections'] for point in section['curve_cm']]
            method='AFFINE_SOURCE_BOUNDARY_AND_CONVEX_ARC_SECTION_ENVELOPE'
        extent=[max(abs(max(p[k] for p in initial)-min(p[k] for p in targets)),
                    abs(max(p[k] for p in targets)-min(p[k] for p in initial))) for k in range(3)]
        bound=math.sqrt(math.fsum(value*value for value in extent))
    elif 'origin_cm' in frame:
        offset=frame.get('offset_uv_cm',[0.,0.])
        targets=[[frame['origin_cm'][k]+(p[0]-offset[0])*frame['u_axis'][k]+(p[1]-offset[1])*frame['v_axis'][k]
            for k in range(3)] for p in piece['vertices']]
        bound=max(math.dist(a,b) for a,b in zip(initial,targets));method='CORRESPONDING_AFFINE_SOURCE_BOUNDARY_EXTREMA'
    else:raise StudioError('Preform displacement bound needs the exact declared guide domain')
    scale=max(abs(value) for point in initial+targets for value in point);guard=max(.0001,scale*2e-6)
    return {'bound_cm':round(math.ceil((bound+guard)/.01)*.01,8),'method':method,'guide_sha256':digest(frame),
        'source_contour_sha256':digest(piece['vertices']),'native_float32_guard_cm':round(guard,8),
        'budget_rounding_cm':.01,'gate_thresholds_changed':False}


def source_preform_budget(data,frames,placements):
    """A recomputable staging bound, distinct from all physical budgets."""
    if set(frames)!=set(data['pieces']) or set(placements)!=set(data['pieces']):
        raise StudioError('Source preform budget must cover every exact source piece')
    if any(placement.get('mode')!='flat' or placement.get('origin_2d_cm')!=[0.,0.] for placement in placements.values()):
        raise StudioError('Source preform budget supports only explicit flat source tangent seeds')
    panels={pid:_guide_preform_bound(piece,frames[pid],placements[pid]) for pid,piece in sorted(data['pieces'].items())}
    return {'version':1,'basis':'SOURCE_FLAT_SEED_TO_DECLARED_GUIDE_BEFORE_EXECUTION',
        'source_garment_sha256':digest(data),'guides_sha256':digest(frames),'placements_sha256':digest(placements),
        'max_displacement_cm':max(panel['bound_cm'] for panel in panels.values()),'panels':panels,
        'physical_budgets_changed':False}


def verify_source_preform_budget(data,frames,placements,declared):
    expected=source_preform_budget(data,frames,placements)
    if declared!=expected:
        raise StudioError('Source preform budget differs from the exact source, guide or seed reconstruction')
    return expected


def mount_release_batches(payload,plan,releases,frames):
    """Coalesce physically equivalent supports while retaining every frame."""
    from .pattern_assembly import support_weights
    batches=[]
    for index,release in enumerate(releases):
        pins,support=support_weights(payload,plan,'assembly',release)
        key=digest([pins,support['temporary_supports_active']]);count=frames//len(releases)+(index<frames%len(releases))
        if batches and batches[-1]['physical_support_identity']==key:
            batches[-1]['releases'].append(release);batches[-1]['frames']+=count;batches[-1]['support']=support
        else:batches.append({'physical_support_identity':key,'releases':[release],'frames':count,'pins':pins,'support':support})
    return batches


def _source_metric_recovery(data, semantics, guide, preform_budget, budgets):
    """Declare recovery ownership from source relations and actual guide stops.

    A coupled guide adds its entire explicit source cohort. Its binary32
    alignment allowance derives from the existing per-panel conversion guards;
    it neither admits a placement nor changes any final seam/quality gate.
    """
    coupling=guide.get('source_seam_coupling')
    recoverable=sorted(pid for pid,row in semantics.items()if row.get('role')in('front','back'))
    seams=[]
    if coupling is not None:
        if (not isinstance(coupling,dict)or coupling.get('method')!='SOURCE_PERMANENT_NORMALIZED_PARTITION_UNION_CAGE'
                or coupling.get('component_id')!=data['component_id']or coupling.get('source_sha256')!=digest(data)
                or not isinstance(coupling.get('refinements'),dict)):
            raise StudioError('Metric recovery requires its exact source-bound guide coupling report')
        recoverable=sorted(coupling['refinements'])
        if not recoverable or not set(recoverable)<=set(semantics):
            raise StudioError('Coupled metric recovery has missing actual source pieces')
        if coupling.get('cage_sha256')!=digest({pid:guide['panels'][pid]for pid in recoverable}):
            raise StudioError('Coupled metric recovery guide cages changed after source coupling')
        expected={row['id']:row for row in data['seams']if row['kind']=='permanent'
                  and row['piece_a']in recoverable and row['piece_b']in recoverable}
        rows=coupling.get('relations')
        if (not isinstance(rows,list)or not expected or len(rows)!=len(expected)
                or any(not isinstance(row,dict)or row.get('source_seam_id')not in expected
                       or row.get('source_relation')!=expected[row['source_seam_id']]for row in rows)
                or len({row['source_seam_id']for row in rows})!=len(expected)):
            raise StudioError('Coupled metric recovery requires every exact internal permanent source relation')
        seams=sorted(expected)
    if not recoverable:return None
    stops=[]
    for pid in recoverable:
        row=semantics[pid];edges=row.get('guide_edges',{})
        names=([edges.get('shoulder')]if row.get('role')in('front','back')else
               [edges.get('anchor')]+([edges['anchor_end']]if 'anchor_end'in edges else []))
        if any(not name or name not in data['pieces'][pid]['edges']for name in names):
            raise StudioError('Source metric recovery requires each selected piece\'s explicit actual guide stop: '+pid)
        stops.extend({'piece':pid,'edge':name}for name in dict.fromkeys(names))
    result={'version':1,'piece_ids':recoverable,'protected_edges':stops,
        'budgets':{'max_iterations':min(100,budgets['max_iterations']),
            'max_seconds':min(300,budgets['max_seconds']),
            'max_displacement_cm':budgets['max_displacement_cm'],'max_step_cm':.5,
            'cg_iterations':60,'cg_tolerance':1e-5,'stagnation_iterations':5},'strain_weight':100.}
    if seams:
        guards=[preform_budget['panels'][pid]['native_float32_guard_cm']for pid in recoverable]
        if any(type(value)not in(int,float)or not math.isfinite(value)or not 0<value<=1 for value in guards):
            raise StudioError('Coupled metric alignment requires the actual finite native conversion guards')
        result.update(seam_ids=seams,max_initial_seam_gap_cm=2*max(guards))
    return result


def prepare_component_templates(assembly_plan, sources, guides, standard_recipe, dossier, dossier_ref, compiler_inputs=None):
    """Prepare portable native inputs without claiming a native mesh identity.

    `sources` contains exact source_ref/data pairs, as used by the dossier
    compiler. Collider snapshots and native triangulation maps deliberately
    remain unresolved. The native binder verifies them before preparation.
    """
    from .pattern_preparation import audit_source
    from .sewing import validate_recipe
    _reference(dossier_ref); contract('sewing-recipe',standard_recipe)
    before = digest([assembly_plan,sources,guides,standard_recipe,dossier,dossier_ref])
    expected = digest({k:v for k,v in assembly_plan.items() if k!='plan_sha256'})
    if assembly_plan.get('plan_sha256') != expected or assembly_plan.get('qualification')!='NONE':
        raise StudioError('Component preparation needs the exact unqualified source assembly plan')
    prepared = {}; diagnostic = []
    for cid, source in sorted(sources.items()):
        _reference(source['source_ref']); data = source['data']
        if data['component_id'] != cid: raise StudioError('Source preparation component differs')
        guide = guides.get(cid,{})
        if guide.get('status')!='GARMENT_GUIDES_PREPARED' or set(guide.get('panels',{}))!=set(data['pieces']):
            raise StudioError('Source preparation requires complete measured guides: '+cid)
        semantics={pid:{k:v for k,v in assembly_plan['piece_semantics'][pid].items()
                       if k not in ('id','component_id','edges','source_ref')} for pid in data['pieces']}
        if guide.get('source_sha256')!=digest(data) or guide.get('semantics_sha256')!=digest(semantics):
            raise StudioError('Source guides belong to another source geometry or semantic declaration: '+cid)
        if not guide.get('profile_sha256') or not guide.get('profile_cache_key'):
            raise StudioError('Source guides lack their exact measured body identity: '+cid)
        recipe = copy.deepcopy(standard_recipe); recipe['component_id'] = cid
        recipe['placements'] = {pid:_guide_seed_placement(piece,guide['panels'][pid],pid) for pid,piece in sorted(data['pieces'].items())}
        recipe['seams'] = {s['id']:{'kind':s['kind'],'ease_b_over_a':0.,'tolerance_relative':.02} for s in data['seams']}
        recipe['pins']=[]; recipe['trial_pieces']=sorted(data['pieces']); recipe['colliders']=[]
        recipe['no_collision_reason']='NATIVE_BODY_BINDING_REQUIRED_BEFORE_EXECUTION'
        recipe['collision_collection']='A3D.Colliders'
        permanent = any(s['kind']=='permanent' for s in data['seams'])
        if not permanent: recipe['trial_mode']='single_panel' if len(data['pieces'])==1 else 'seam_free'
        else: recipe.pop('trial_mode',None)
        # Self contacts are measured from the first physical frame, including
        # the experimental coupled-layer source group.
        recipe['phases']['mount']['self_collision']=True
        validate_recipe(data,recipe)
        own = set(data['pieces']); layers=_project_component_layers(assembly_plan['spatial_graph'],own)
        preform_budget=source_preform_budget(data,guide['panels'],recipe['placements'])
        fields={'version':1,'component_id':cid,
            'source_refs':[dossier_ref['path']+'#sha256='+dossier_ref['sha256'],
                           source['source_ref']['path']+'#sha256='+source['source_ref']['sha256']],
            'preform':{'panels':copy.deepcopy(guide['panels'])},
            'assembly':{'max_initial_gap_cm':recipe['limits']['max_seam_gap_cm'],
                        'max_displacement_cm':recipe['limits']['max_displacement_cm'],
                        'max_step_cm':.05,'iterations':300,'neighborhood_rings':2,'closure_support_release':1.},
            'consolidation':{'weld_gap_cm':recipe['limits']['weld_gap_cm']},
            'quality':{key:recipe['mesh'][key] for key in ('min_angle_degrees','min_edge_cm','min_stretch','max_stretch')},
            'cloth':{'mount_release_steps':[0.,.5,1.]},
            'supports':{'temporary':[],'drape':[],'functional':[]},
            'collision':{'required':True,'clearance_cm':recipe['phases']['drape']['collision_distance_cm'],
                         'source_ref':'approved-measured-body:'+digest(assembly_plan['body_ref'])},
            'layers':layers}
        spec={'version':1,'component_id':cid,'source_ref':dossier_ref['path']+'#sha256='+dossier_ref['sha256'],
            'construction_dossier':copy.deepcopy(dossier_ref),
            'source_preform_budget':preform_budget,
            'regular_mesh':{'spacing_cm':recipe['mesh']['spacing_cm'],'min_spacing_cm':max(.2,recipe['mesh']['spacing_cm']/2),
                'refinement_distance_cm':4.,'max_vertices':recipe['mesh']['max_vertices'],'target_min_angle_degrees':15.},
            'mass_policy':'native_uniform_vertex',
            'material_profiles':[{'id':'standard-unqualified','source_ref':'standard-recipe:'+digest(standard_recipe),
                'pieces':sorted(data['pieces']),'areal_density_kg_m2':recipe['mass']['value'],'cloth_profile':'phase_base'}]
            if recipe['mass']['basis']=='areal_density_kg_m2' else []}
        budgets=next(g['budgets'] for g in assembly_plan['groups'] if own.intersection(g['pieces']))
        correction_quality=copy.deepcopy(fields['quality'])
        correction_quality['min_stretch']=max(correction_quality['min_stretch'],1-budgets['max_strain_relative'])
        correction_quality['max_stretch']=min(correction_quality['max_stretch'],1+budgets['max_strain_relative'])
        spec['placement_correction']={'version':1,'kernels':['rigid','relaxation'],'quality':correction_quality,
            'budgets':{'max_iterations':min(300,budgets['max_iterations']),'max_seconds':min(300,budgets['max_seconds']),
                'max_proposals_per_iteration':8,'max_displacement_cm':budgets['max_displacement_cm'],
                'max_step_cm':.05,'stagnation_iterations':3,'min_improvement':1e-6,'target_score':1e-6}}
        recovery=_source_metric_recovery(data,semantics,guide,preform_budget,budgets)
        if recovery:spec['metric_recovery']=recovery
        contract('pattern-preparation',spec)
        prepared[cid]={'source_ref':copy.deepcopy(source['source_ref']),'source_garment_sha256':digest(data),
            'recipe_template':recipe,'plan_fields':fields,'preparation_template':spec,
            'guide_identity':{k:guide[k] for k in ('source_sha256','semantics_sha256','profile_sha256','profile_cache_key')},
            'source_audit':_template_audit_observations(audit_source(data,recipe,dossier)),
            'recipe_provenance':{'standard_recipe_sha256':digest(standard_recipe),'calibration':'NOT_QUALIFIED',
                'placements':'RIGID_TANGENT_PLANES_OF_MEASURED_SOURCE_GUIDES','supports':'NONE_DECLARED',
                'seam_ease':'ZERO_DECLARED_AND_SOURCE_LENGTH_CHECKED','permanent_links_changed':False},
            'native_bindings_required':['BODY_COLLIDER_SNAPSHOT','NATIVE_REGULAR_MESH_MAP','COLLISION_ENVELOPE_REVIEW'],
            'simulation':'NOT_EXECUTED','qualification':'NONE'}
        prepared[cid]['recipe_provenance']['preform_displacement_budget']={'panels':preform_budget['panels'],
            'declared_cm':preform_budget['max_displacement_cm'],'assembly_limit_cm':fields['assembly']['max_displacement_cm'],
            'cloth_limit_cm':recipe['limits']['max_displacement_cm'],
            'correction_limit_cm':spec['placement_correction']['budgets']['max_displacement_cm'],
            'basis':'SOURCE_FLAT_SEED_TO_DECLARED_GUIDE_BEFORE_EXECUTION'}
        if prepared[cid]['source_audit']['status']!='SOURCE_AUDITED':
            diagnostic.append({'component_id':cid,'category':'source_audit','assessment':prepared[cid]['source_audit']['status']})
    if digest([assembly_plan,sources,guides,standard_recipe,dossier,dossier_ref])!=before:
        raise StudioError('Source preparation templates mutated immutable input')
    result={'version':1,'status':'SOURCE_PREPARATION_TEMPLATES_READY','components':prepared,
        'body_ref':copy.deepcopy(assembly_plan['body_ref']),'diagnostics':diagnostic,'qualification':'NONE',
        'simulation':'NOT_EXECUTED','source_mutated':False,'native_mesh_identity':'NOT_YET_DERIVED',
        'compiler_numeric_policy':copy.deepcopy(TEMPLATE_NUMERIC_POLICY)}
    if compiler_inputs is not None:
        required={'assembly_plan_ref','guides_ref','production_spec_ref','standard_recipe_ref','dossier_ref'}
        if set(compiler_inputs)!=required:raise StudioError('Component template compiler inputs are incomplete')
        for ref in compiler_inputs.values():_reference(ref)
        result['compiler_inputs']=copy.deepcopy(compiler_inputs)
        result['input_refs']=[copy.deepcopy(compiler_inputs[key]) for key in sorted(compiler_inputs)]
    result['prepared_sha256']=digest(result)
    return result


def merge_group_payloads(group, piece_semantics, payloads):
    """Join source maps by offsets, retaining complete per-face provenance."""
    selected = set(group['pieces'])
    component_ids = sorted({piece_semantics[pid]['component_id'] for pid in selected})
    result = {'version': 2, 'component_id': group['id'], 'rest_cm': [], 'placed_cm': [],
              'faces': [], 'panels': {}, 'seams': {}, 'pins': {},
              'source_rest_triangles_cm': [], 'source_face_pieces': [], 'source_face_vertex_ids': [],
              'source_vertex_map': {}, 'source_face_origins': [], 'source_components': {},
              'source_group': copy.deepcopy(group), 'qualification': 'NONE'}
    source_refs = {}; before = digest([group, piece_semantics, payloads])
    for cid in component_ids:
        if cid not in payloads:
            raise StudioError('Source group lacks its actual derived component map: '+cid)
        source = payloads[cid]
        if source['component_id'] != cid or not source.get('source_garment_sha256') or not source.get('package_sha256'):
            raise StudioError('Textile group needs exact approved component/package provenance')
        labels = face_piece_ids(source, source['faces'], len(source['rest_cm']))
        bindings = face_sources(source)
        if bindings['binding_issues']:
            raise StudioError('Group source face UV or winding correspondence changed')
        owned = {pid for pid in source['panels'] if pid in selected}
        if not owned or any(piece_semantics[pid]['component_id'] != cid for pid in owned):
            raise StudioError('Textile group component/piece ownership differs from assembly plan')
        ids = sorted({i for pid in owned for i in source['panels'][pid]['indices']})
        remap = {index: len(result['rest_cm'])+number for number, index in enumerate(ids)}
        result['rest_cm'].extend(copy.deepcopy(source['rest_cm'][i]) for i in ids)
        result['placed_cm'].extend(copy.deepcopy(source.get('placed_cm', source['rest_cm'])[i]) for i in ids)
        for pid in sorted(owned):
            if pid in result['panels']:
                raise StudioError('Several source components own the same textile piece')
            panel = copy.deepcopy(source['panels'][pid])
            for field in ('indices', 'boundary'):
                if field in panel: panel[field] = [remap[i] for i in panel[field]]
            if 'edges' in panel:
                panel['edges'] = {name: [remap[i] for i in edge] for name, edge in panel['edges'].items()}
            result['panels'][pid] = panel
        for source_face, (face, pid) in enumerate(zip(source['faces'], labels)):
            if pid not in owned: continue
            if any(i not in remap for i in face):
                raise StudioError('Group face crosses undeclared source-piece ownership')
            result['faces'].append([remap[i] for i in face])
            uv = bindings['source_rest_triangles_cm'][source_face]
            original_ids = bindings['source_face_vertex_ids'][source_face]
            composite_ids = [remap[coordinate] for coordinate in face]
            for index in composite_ids:
                result['source_vertex_map'][str(index)] = index
            result['source_rest_triangles_cm'].append(copy.deepcopy(uv))
            result['source_face_pieces'].append(pid)
            result['source_face_vertex_ids'].append(composite_ids)
            result['source_face_origins'].append({'component_id': cid, 'piece': pid, 'source_face': source_face,
                'source_vertex_ids': copy.deepcopy(original_ids), 'source_uv_cm': copy.deepcopy(uv)})
        for sid, seam in sorted(source['seams'].items()):
            touched = {seam['piece_a'], seam['piece_b']} & owned
            if not touched: continue
            if {seam['piece_a'], seam['piece_b']}-owned:
                if seam['kind'] == 'permanent':
                    raise StudioError('Group slicing would discard an approved permanent seam')
                continue
            merged = copy.deepcopy(seam)
            merged['pairs'] = [[remap[a], remap[b]] for a, b in seam['pairs']]
            result['seams'][cid+'::'+sid] = merged
        for index, weight in source.get('pins', {}).items():
            if int(index) in remap: result['pins'][str(remap[int(index)])] = weight
        result['source_components'][cid] = {'package_sha256': source['package_sha256'],
            'source_garment_sha256': source['source_garment_sha256'], 'source_map_sha256': digest(source),
            'pieces': sorted(owned), 'source_coordinate_map': {str(old): new for old, new in remap.items()}}
        source_refs[cid] = result['source_components'][cid]
    if set(result['panels']) != selected or not result['faces']:
        raise StudioError('Textile group source mapping is incomplete')
    result['package_sha256'] = digest({cid: row['package_sha256'] for cid, row in source_refs.items()})
    result['source_garment_sha256'] = digest({cid: row['source_garment_sha256'] for cid, row in source_refs.items()})
    if len(result['panels']) == 1 and not any(s['kind'] == 'permanent' for s in result['seams'].values()):
        result['trial_mode'] = 'single_panel'
        result['single_panel_source'] = {'component_id': group['id'],
            'source_garment_sha256': result['source_garment_sha256'],
            'piece_ids': sorted(result['panels']), 'trial_pieces': sorted(result['panels']),
            'seam_kinds': {sid: row['kind'] for sid, row in result['seams'].items()}}
    if digest([group, piece_semantics, payloads]) != before:
        raise StudioError('Group adapter mutated a source component')
    return result


def split_group_payload(group_payload, component_id):
    """Restore a component's source-piece map after geometric consolidation."""
    info = group_payload['source_components'].get(component_id)
    if not info: raise StudioError('Group has no source component: '+component_id)
    pieces = set(info['pieces'])
    face_ids = [i for i, row in enumerate(group_payload['source_face_origins']) if row['component_id'] == component_id]
    if len(group_payload['source_face_origins']) != len(group_payload['faces']):
        raise StudioError('Consolidation lost the original per-face component identities')
    indices = sorted({index for fi in face_ids for index in group_payload['faces'][fi]})
    remap = {index: number for number, index in enumerate(indices)}
    result = {'version': 2, 'component_id': component_id,
        'source_garment_sha256': info['source_garment_sha256'], 'package_sha256': info['package_sha256'],
        'rest_cm': [copy.deepcopy(group_payload['rest_cm'][i]) for i in indices],
        'placed_cm': [copy.deepcopy(group_payload['placed_cm'][i]) for i in indices],
        'faces': [[remap[i] for i in group_payload['faces'][fi]] for fi in face_ids],
        'source_rest_triangles_cm': [copy.deepcopy(group_payload['source_rest_triangles_cm'][fi]) for fi in face_ids],
        'source_face_pieces': [group_payload['source_face_pieces'][fi] for fi in face_ids],
        'source_face_vertex_ids': [copy.deepcopy(group_payload['source_face_origins'][fi]['source_vertex_ids']) for fi in face_ids],
        'source_face_origins': [copy.deepcopy(group_payload['source_face_origins'][fi]) for fi in face_ids],
        'source_vertex_map': {},
        'pins': {str(remap[int(i)]): w for i, w in group_payload['pins'].items() if int(i) in remap},
        'panels': {}, 'seams': {}, 'rest_mode': group_payload.get('rest_mode', 'flat_2d'),
        'group_source_sha256': digest(group_payload)}
    for fi in face_ids:
        for source_index, current in zip(group_payload['source_face_origins'][fi]['source_vertex_ids'], group_payload['faces'][fi], strict=True):
            key = str(source_index); new = remap[current]
            if key in result['source_vertex_map'] and result['source_vertex_map'][key] != new:
                raise StudioError('One source vertex has contradictory fragment coordinates')
            result['source_vertex_map'][key] = new
    for pid in sorted(pieces):
        panel = copy.deepcopy(group_payload['panels'][pid])
        for field in ('indices', 'boundary'):
            if field in panel: panel[field] = [remap[i] for i in panel[field] if i in remap]
        panel['edges'] = {key: [remap[i] for i in ids if i in remap] for key, ids in panel.get('edges', {}).items()}
        result['panels'][pid] = panel
    for sid, seam in group_payload['seams'].items():
        if seam['piece_a'] in pieces and seam['piece_b'] in pieces:
            row = copy.deepcopy(seam); row['pairs'] = [[remap[a], remap[b]] for a, b in seam['pairs']]
            result['seams'][sid.split('::', 1)[-1]] = row
    face_piece_ids(result, result['faces'], len(result['rest_cm']))
    return result


def assemble_component_fragments(source, fragments):
    """Collect completed groups into one source component without new welding."""
    pieces = set(source['panels']); owners = [pid for part in fragments for pid in part['panels']]
    if set(owners) != pieces or len(owners) != len(pieces):
        raise StudioError('Completed component fragments must cover each approved source piece exactly once')
    result = {'version': 2, 'component_id': source['component_id'],
        'package_sha256': source['package_sha256'], 'source_garment_sha256': source['source_garment_sha256'],
        'rest_mode': 'assembled_3d', 'rest_cm': [], 'placed_cm': [], 'faces': [], 'panels': {},
        'seams': {}, 'pins': {}, 'source_vertex_map': {}, 'source_rest_triangles_cm': [],
        'source_face_pieces': [], 'source_face_vertex_ids': [], 'source_face_origins': [],
        'regional_source': {key: copy.deepcopy(source.get(key)) for key in ('rest_cm', 'panels', 'source_garment_sha256')}}
    faces = {}; originals = face_sources(source)
    for part in fragments:
        if part['component_id'] != source['component_id'] or part['package_sha256'] != source['package_sha256'] or part['source_garment_sha256'] != source['source_garment_sha256']:
            raise StudioError('Completed component fragment changed approved source provenance')
        offset = len(result['rest_cm'])
        result['rest_cm'].extend(copy.deepcopy(part['rest_cm'])); result['placed_cm'].extend(copy.deepcopy(part['placed_cm']))
        for key, index in part['source_vertex_map'].items():
            if key in result['source_vertex_map']: raise StudioError('Completed source fragments overlap vertex ownership')
            result['source_vertex_map'][key] = offset+index
        for pid, panel in part['panels'].items():
            row = copy.deepcopy(panel)
            for key in ('indices', 'boundary'): row[key] = [offset+i for i in row[key]]
            row['edges'] = {name: [offset+i for i in ids] for name, ids in row['edges'].items()}
            result['panels'][pid] = row
        result['pins'].update({str(offset+int(i)): weight for i, weight in part['pins'].items()})
        for face, origin in zip(part['faces'], part['source_face_origins'], strict=True):
            index = origin['source_face']
            if index in faces or origin['component_id'] != source['component_id']:
                raise StudioError('Completed fragments duplicate or reassign an approved source face')
            if (origin['source_uv_cm'] != originals['source_rest_triangles_cm'][index] or
                    origin['source_vertex_ids'] != originals['source_face_vertex_ids'][index]):
                raise StudioError('Completed fragment changed an approved source face UV or winding')
            faces[index] = ([offset+i for i in face], copy.deepcopy(origin))
    if set(faces) != set(range(len(source['faces']))):
        raise StudioError('Completed component lacks approved source faces')
    for index in sorted(faces):
        face, origin = faces[index]; result['faces'].append(face); result['source_face_origins'].append(origin)
        result['source_rest_triangles_cm'].append(origin['source_uv_cm'])
        result['source_face_pieces'].append(origin['piece']); result['source_face_vertex_ids'].append(origin['source_vertex_ids'])
    for sid, seam in source['seams'].items():
        row = copy.deepcopy(seam)
        row['pairs'] = [[result['source_vertex_map'][str(a)], result['source_vertex_map'][str(b)]] for a, b in row['pairs']]
        if row['kind'] == 'permanent':
            if any(a != b for a, b in row['pairs']): raise StudioError('Completed fragments did not consolidate the approved permanent partners')
            row['consolidated'] = True
        elif any(a!=b and result['source_vertex_map'][str(a)]==result['source_vertex_map'][str(b)] for a,b in seam['pairs']):
            raise StudioError('Completed fragments collapsed an approved closure or detachable relation')
        result['seams'][sid] = row
    result['source_vertex_cohorts']={str(index):[] for index in range(len(result['rest_cm']))}
    for old,new in result['source_vertex_map'].items():result['source_vertex_cohorts'][str(new)].append(int(old))
    result['source_vertex_indices']=[min(result['source_vertex_cohorts'][str(index)]) for index in range(len(result['rest_cm']))]
    result['source_vertex_index_semantics']='representative_only_see_source_vertex_cohorts'
    if face_sources(result)['binding_issues']: raise StudioError('Completed component lost source face correspondence')
    return result


def _component_continuity_map(payload):
    return digest([map_digest(payload),payload.get('source_vertex_map'),payload.get('source_vertex_cohorts'),
        payload.get('source_face_origins'),payload.get('source_rest_triangles_cm'),payload.get('source_face_pieces'),
        payload.get('source_face_vertex_ids')])


def component_continuity_proof(source,source_ref,result,groups,program_ref,package_ref,weld_limit_cm):
    """Compose exact group geometry roots; never manufacture a Cloth receipt.

    The native caller must resolve every group to its connected completed drape
    receipt before movement admission. This portable result verifies only the
    complete source inventory, material faces, permanent unions and remapping.
    """
    from .pattern_assembly import verify_permanent_continuity
    from .sewing import permanent_support_groups
    for ref in (source_ref,program_ref,package_ref):_reference(ref)
    cid=source['component_id'];fragments=[];roots=[];identities=set()
    for item in groups:
        gid=item['group_id'];ref=item['derived_mesh_ref'];group=item['payload'];_reference(ref)
        if gid in identities:raise StudioError('Component continuity repeats a source group')
        identities.add(gid)
        info=group.get('source_components',{}).get(cid)
        if (not info or group['component_id']!=gid or group.get('rest_mode')!='assembled_3d'
                or info['source_map_sha256']!=digest(source) or info['package_sha256']!=package_ref['sha256']
                or source['package_sha256']!=package_ref['sha256']):
            raise StudioError('Component continuity group does not belong to the exact canonical source mesh')
        permanent=verify_permanent_continuity(group,weld_limit_cm)
        fragment=split_group_payload(group,cid);fragments.append(fragment)
        roots.append({'group_id':gid,'derived_mesh_ref':copy.deepcopy(ref),'group_payload_sha256':digest(group),
            'source_pieces':sorted(fragment['panels']),
            'source_face_indices':[origin['source_face'] for origin in fragment['source_face_origins']],
            'source_vertex_map':copy.deepcopy(fragment['source_vertex_map']),
            'permanent_consolidation_proof_sha256':permanent['proof_sha256'] if permanent else None})
    expected=assemble_component_fragments(source,fragments)
    cohorts=permanent_support_groups(source);joined={index for group in cohorts for index in group}
    allowed={frozenset(group) for group in cohorts}|{frozenset((index,)) for index in range(len(source['rest_cm'])) if index not in joined}
    actual={frozenset(group) for group in expected['source_vertex_cohorts'].values()}
    if actual!=allowed:
        raise StudioError('Component continuity contains unions outside its approved permanent source cohorts')
    if _component_continuity_map(expected)!=_component_continuity_map(result):
        raise StudioError('Complete component mapping differs from its exact source group reconstruction')
    proof={'version':1,'scope':'COMPLETE_COMPONENT_FROM_SOURCE_GROUP_GEOMETRY','component_id':cid,
        'source_ref':copy.deepcopy(source_ref),'source_mapping_sha256':map_digest(source),
        'source_payload_sha256':digest(source),'package_ref':copy.deepcopy(package_ref),
        'program_ref':copy.deepcopy(program_ref),'result_mapping_sha256':_component_continuity_map(result),
        'groups':roots,'qualification':'GEOMETRY_ONLY','native_drape_receipts_required':True,
        'cloth_evidence_created':False}
    proof['proof_sha256']=digest(proof)
    return proof


def verify_component_continuity(source,result,groups,weld_limit_cm):
    declared=result.get('component_continuity')
    if not isinstance(declared,dict):raise StudioError('Complete component lacks its source group continuity proof')
    expected=component_continuity_proof(source,declared['source_ref'],result,groups,
        declared['program_ref'],declared['package_ref'],weld_limit_cm)
    if declared!=expected:raise StudioError('Complete component continuity proof differs from its verified group/source reconstruction')
    return {'status':'COMPONENT_CONTINUITY_VERIFIED','component_id':source['component_id'],
        'proof_sha256':declared['proof_sha256'],'source_ref':declared['source_ref'],
        'package_ref':declared['package_ref'],'program_ref':declared['program_ref'],
        'verified_groups':copy.deepcopy(declared['groups']),
        'global_source_vertex_map':copy.deepcopy(result['source_vertex_map']),
        'global_source_face_indices':[origin['source_face'] for origin in result['source_face_origins']],
        'permanent_source_pair_count':sum(len(seam['pairs']) for seam in source['seams'].values() if seam['kind']=='permanent'),
        'result_mapping_sha256':declared['result_mapping_sha256'],'qualification':'GEOMETRY_ONLY',
        'native_drape_receipts_required':True,'cloth_evidence_created':False}


def consolidate_group(payload, coordinates, plan):
    """Use permanent sewing when declared, otherwise retain independent panels.

    A group of complete continuous panels with no permanent links needs no
    geometric union. This is distinct from pretending the group is one source
    panel, and never qualifies its closures or detachable relationships.
    """
    if any(row['kind'] == 'permanent' for row in payload['seams'].values()) or payload.get('trial_mode') == 'single_panel':
        return consolidate(payload, coordinates, plan)
    validate_plan(payload, plan)
    if not payload.get('source_components') or not payload.get('source_face_origins'):
        raise StudioError('Independent-panel group requires complete source-component and face provenance')
    continuous_quality(payload, coordinates, plan['quality'])
    _vertex_manifold(payload['faces'])
    sources = face_sources(payload)
    if sources['binding_issues']:
        raise StudioError('Independent-panel consolidation lost immutable source UV correspondence')
    result = copy.deepcopy(payload)
    result.update(version=2, rest_mode='assembled_3d', rest_cm=copy.deepcopy(coordinates),
        placed_cm=copy.deepcopy(coordinates), source_mapping_sha256=map_digest(payload),
        regional_source={key: copy.deepcopy(payload.get(key)) for key in ('rest_cm', 'panels', 'source_garment_sha256')})
    result['source_vertex_cohorts'] = {str(index): [index] for index in range(len(coordinates))}
    result['source_vertex_indices'] = list(range(len(coordinates)))
    result['source_vertex_index_semantics'] = 'representative_only_see_source_vertex_cohorts'
    result['quality'] = continuous_quality(result, coordinates, plan['quality'])
    result['full_rest_area_cm2'] = result['quality']['rest_area_cm2']
    result.pop('fitting_tacks', None)
    return result, {'status': 'GEOMETRY_CONSOLIDATED', 'qualification': 'NONE',
        'operation': 'INDEPENDENT_SOURCE_PANELS_NO_UNION', 'explicit_unions': 0,
        'sewing_executed': False, 'welding_executed': False, 'closure_behavior': 'NOT_QUALIFIED',
        'source_mapping_sha256': map_digest(payload), 'result_mapping_sha256': map_digest(result),
        'vertices_before': len(coordinates), 'vertices_after': len(coordinates),
        'verified_weld_gap_cm': None, 'source_rest_mode': 'immutable_source_uv_per_face',
        'simulation_rest_mode': 'assembled_3d',
        'linear_union_motion': validate_linear_motion(payload, coordinates, coordinates),
        'quality': result['quality'], 'preserved_links': sorted(payload['seams']),
        'requires': ['continuous_cloth_relaxation', 'body_fitting', 'behaviour_qualification', 'artistic_review']}


def _same(values, name):
    first = values[0]
    if any(value != first for value in values[1:]):
        raise StudioError('Group needs one reviewed common '+name+' policy; source policies differ')
    return copy.deepcopy(first)


def group_recipe(group, payload, recipes):
    selected = sorted(payload['source_components']); values = [recipes[cid] for cid in selected]
    result = {'version': 1, 'component_id': group['id'],
              'collision_collection': 'A3D.TextileCollision.'+group['id'],
              'trial_pieces': sorted(payload['panels']), 'no_collision_reason': '; '.join(sorted({r['no_collision_reason'] for r in values})),
              'placements': {}, 'seams': {}, 'pins': [], 'colliders': []}
    for field in ('mass', 'mesh', 'phases', 'limits'):
        result[field] = _same([r[field] for r in values], field)
    strain = group['budgets']['max_strain_relative']
    result['mesh']['min_stretch'] = max(result['mesh']['min_stretch'], 1-strain)
    result['mesh']['max_stretch'] = min(result['mesh']['max_stretch'], 1+strain)
    result['limits']['max_displacement_cm'] = min(result['limits']['max_displacement_cm'], group['budgets']['max_displacement_cm'])
    if payload.get('trial_mode') == 'single_panel':
        result['trial_mode'] = 'single_panel'
    if len(payload['rest_cm']) > result['mesh']['max_vertices']:
        raise StudioError('Combined textile group exceeds the reviewed mesh vertex budget')
    if len(selected) == 1 and set(values[0]['trial_pieces']) == set(payload['panels']):
        for field in ('fitting_plan', 'fitting_pose'):
            if field in values[0]: result[field] = copy.deepcopy(values[0][field])
    colliders = {}
    for cid in selected:
        recipe = recipes[cid]; owned = set(payload['source_components'][cid]['pieces'])
        result['placements'].update({pid: copy.deepcopy(row) for pid, row in recipe['placements'].items() if pid in owned})
        result['seams'].update({cid+'::'+sid: copy.deepcopy(row) for sid, row in recipe['seams'].items() if cid+'::'+sid in payload['seams']})
        result['pins'].extend(copy.deepcopy(row) for row in recipe['pins'] if row['piece'] in owned)
        for row in recipe['colliders']:
            if row['object'] in colliders and colliders[row['object']] != row:
                raise StudioError('Group recipes disagree on actual collider geometry')
            colliders[row['object']] = copy.deepcopy(row)
    result['colliders'] = [colliders[key] for key in sorted(colliders)]
    contract('sewing-recipe', result)
    return result


def group_plan(group, payload, plans, assembly_ref):
    selected = sorted(payload['source_components']); values = [plans[cid] for cid in selected]
    result = {'version': 1, 'component_id': group['id'], 'mapping_sha256': map_digest(payload),
              'source_refs': sorted({ref for plan in values for ref in plan['source_refs']}),
              'preform': {'panels': {}}, 'supports': {'temporary': [], 'drape': [], 'functional': []}}
    for field in ('assembly', 'consolidation', 'quality'):
        result[field] = _same([p[field] for p in values], field)
    result['assembly']['iterations'] = min(result['assembly']['iterations'], group['budgets']['max_iterations'])
    result['assembly']['max_displacement_cm'] = min(result['assembly']['max_displacement_cm'], group['budgets']['max_displacement_cm'])
    strain = group['budgets']['max_strain_relative']
    result['quality']['min_stretch'] = max(result['quality']['min_stretch'], 1-strain)
    result['quality']['max_stretch'] = min(result['quality']['max_stretch'], 1+strain)
    collision = _same([{k: v for k, v in p['collision'].items() if k != 'source_ref'} for p in values], 'collision reserve')
    result['collision'] = {**collision, 'source_ref': 'group-source:'+digest(assembly_ref)}
    cloths = [p.get('cloth', {}) for p in values]
    if any(cloths): result['cloth'] = _same(cloths, 'support release/Cloth phase')
    for cid in selected:
        plan = plans[cid]; owned = set(payload['source_components'][cid]['pieces'])
        result['preform']['panels'].update({pid: copy.deepcopy(frame) for pid, frame in plan['preform']['panels'].items() if pid in owned})
        for role, supports in plan['supports'].items():
            result['supports'][role].extend({**copy.deepcopy(row), 'id': cid+'::'+row['id']} for row in supports if row['piece'] in owned)
    if len(selected) == 1:
        original = values[0]
        if set(original['preform']['panels']) == set(payload['panels']):
            for field in ('dressing', 'layers'):
                if field in original: result[field] = copy.deepcopy(original[field])
            if original.get('layer_execution'):
                result['layer_execution'] = copy.deepcopy(original['layer_execution'])
                result['layer_execution']['source_mapping_sha256'] = map_digest(payload)
                result['layer_execution']['sewing_graph_sha256'] = sewing_graph_digest(payload)
    elif any(p.get('dressing', {}).get('required') for p in values):
        raise StudioError('Multicomponent group requires an explicitly reviewed group dressing contract; component passage choreography cannot be discarded')
    validate_plan(payload, result)
    return result


def compile_textile_program(assembly_plan, specification, payloads, recipes, plans):
    """Compile an exact native stage DAG, retaining source component ownership."""
    contract('textile-program', specification)
    if assembly_plan.get('qualification') != 'NONE' or assembly_plan.get('simulation') != 'NOT_EXECUTED':
        raise StudioError('Textile compiler requires an unexecuted source assembly plan')
    expected = digest({k: v for k, v in assembly_plan.items() if k != 'plan_sha256'})
    if assembly_plan.get('plan_sha256') != expected:
        raise StudioError('Source assembly plan identity changed')
    groups = []; units = []; last_units = {}; diagnostics = []
    if specification['purpose']=='TEST_ONLY' and specification.get('fit_context'):
        raise StudioError('TEST_ONLY textile programs cannot carry a production fit context')
    if specification['purpose']=='GARMENT_CANDIDATE' and not specification.get('fit_context'):
        diagnostics.append({'code':'PRODUCTION_FIT_CONTEXT_REQUIRED','category':'missing_metadata',
            'remedy':'Provide exact source dossier and component fit profiles with reviewed numeric intent'})
    fit_inputs=[]
    if specification.get('fit_context'):
        fit_inputs=[specification['fit_context']['compiled_dossier_ref']]+specification['fit_context']['fit_profiles_refs']
    bindings = {row['component_id']: row for row in specification['components']}
    if len(bindings) != len(specification['components']):
        raise StudioError('Textile program has duplicate component bindings')
    for group in assembly_plan['groups']:
        payload = merge_group_payloads(group, assembly_plan['piece_semantics'], payloads)
        expected_links = {row['id']: row for row in assembly_plan['link_graph'] if row['id'] in group['links']}
        for sid, link in expected_links.items():
            if link['kind'] != 'permanent': continue
            actual = payload['seams'].get(sid)
            if (actual is None or any(actual.get(key) != link[key] for key in ('kind', 'piece_a', 'piece_b')) or
                    any(not {pair[number] for pair in actual['pairs']} <= set(payload['panels'][link['piece_'+side]]['edges'][link['edge_'+side]])
                        for number, side in enumerate(('a', 'b')))):
                raise StudioError('Group permanent link is absent from its approved source mapping: '+sid)
        payload['source_link_graph'] = copy.deepcopy([expected_links[sid] for sid in sorted(expected_links)])
        recipe = group_recipe(group, payload, recipes)
        plan = group_plan(group, payload, plans, specification['assembly_plan_ref'])
        if len(group['layers']) > 1 and not specification.get('experimental_coupled_multilayer', False):
            diagnostics.append({'code': 'COUPLED_MULTILAYER_NATIVE_TRIAL_REQUIRED', 'group': group['id'],
                                'category': 'capability_not_qualified'})
        inputs = [specification['assembly_plan_ref']]+copy.deepcopy(fit_inputs)
        for cid in sorted(payload['source_components']):
            if cid not in bindings: raise StudioError('Textile program component binding missing: '+cid)
            inputs.extend(bindings[cid][name] for name in ('package_ref', 'derived_mesh_ref', 'recipe_ref', 'plan_ref'))
        groups.append({'group': copy.deepcopy(group), 'payload': payload, 'recipe': recipe, 'plan': plan,
                       'inputs': copy.deepcopy(inputs), 'qualification': 'EXPERIMENTAL_NOT_QUALIFIED'})
        prior = sorted(last_units[gid] for gid in group['dependencies'])
        for stage in STAGES:
            prepare_uid = group['id']+'.prepare.'+stage
            units.append({'id': prepare_uid, 'dependencies': prior, 'executor': 'blender',
                          'operation': 'advance_textile_program', 'arguments': {'program_path': specification['program_path']},
                          'inputs': copy.deepcopy(inputs), 'success_statuses': ['NEXT_OPERATION_PREPARED']})
            uid = group['id']+'.'+stage
            units.append({'id': uid, 'dependencies': [prepare_uid], 'executor': 'blender',
                          'operation': 'transition_textile_group',
                          'arguments': {'program_path': specification['program_path'], 'group_id': group['id'], 'stage': stage},
                          'inputs': copy.deepcopy(inputs), 'success_statuses': ['GROUP_STAGE_COMPLETED']})
            prior = [uid]
        last_units[group['id']] = prior[0]
    run = {'version': 1, 'id': specification['id'], 'asset_id': specification['asset_id'], 'kind': 'garment',
           'inputs': [specification['assembly_plan_ref']]+copy.deepcopy(fit_inputs), 'budgets': copy.deepcopy(specification['run_budgets']), 'units': units}
    contract('run', run)
    missing_fit=any(row['code']=='PRODUCTION_FIT_CONTEXT_REQUIRED' for row in diagnostics)
    result = {'version': 1, 'status': 'NEEDS_DATA' if missing_fit else 'NATIVE_TRIAL_REQUIRED' if diagnostics else 'TEXTILE_PROGRAM_PREPARED',
              'purpose':specification['purpose'],
              'production_qualification':'NOT_GRANTED',
              'fit_intent_admission':'TEST_ONLY_NO_PRODUCT_ADMISSION' if specification['purpose']=='TEST_ONLY' else 'CANONICAL_REVIEW_REQUIRED_BEFORE_EXECUTION',
              'groups': groups, 'run_spec': run, 'diagnostics': diagnostics, 'qualification': 'NONE',
              'simulation': 'NOT_EXECUTED', 'fitting': 'NOT_EXECUTED', 'source_mutated': False,
              'checkpoint_recovery': 'RESTORE_ENTRY_AND_REPLAY_INTERRUPTED_STAGE',
              'continuous_velocity_resume': 'NOT_CLAIMED'}
    result['compiled_sha256'] = digest(result)
    return result


def require_textile_program_admission(project,specification,assembly_plan=None):
    """Read-only prerequisite for every native textile entry, before effects.

    A portable plan or a profile's component_ids is insufficient. Production
    needs current source recompilation, the exact target, actual owned checks
    and canonical human numeric-intent decisions for every executing component.
    """
    contract('textile-program',specification);purpose=specification['purpose']
    if specification['asset_id']!=project.state()['asset']['id']:
        raise StudioError('Textile admission targets another canonical asset')
    components={row['component_id'] for row in specification['components']}
    if len(components)!=len(specification['components']):raise StudioError('Textile admission rejects duplicate component bindings')
    if purpose=='TEST_ONLY':
        if specification.get('fit_context'):raise StudioError('TEST_ONLY cannot substitute a production fit context')
        return {'purpose':purpose,'admission':'TEST_ONLY_EXPERIMENT','covered_components':sorted(components),
            'fit_assessments':[],'production_qualification':'NOT_GRANTED','qualification':'NONE','accepted':False}
    context=specification.get('fit_context')
    if not context:raise StudioError('GARMENT_CANDIDATE textile execution needs exact source fit context and reviewed numeric intent')
    from .production_dossier import compile_project_dossier
    from .garment_planner import plan_assembly
    from .garment_fit import require_fit_intent
    def load(ref):
        _reference(ref);path=inside(project.root,ref['path'])
        if sha(path)!=ref['sha256']:raise StudioError('Production textile fit reference changed: '+ref['path'])
        return read_json(path)
    source_assembly=load(specification['assembly_plan_ref'])
    if assembly_plan is not None and source_assembly!=assembly_plan:
        raise StudioError('Production textile admission received a substituted source assembly')
    compiled=load(context['compiled_dossier_ref'])
    compiled_source=compiled.get('source_ref',{});compiled_spec=compiled.get('specification_source_ref',{})
    if not compiled_source or not compiled_spec:raise StudioError('Production textile fit compilation lacks reconstructable source references')
    load(compiled_source);load(compiled_spec)
    rebuilt=compile_project_dossier(project,compiled_source['path'],compiled_spec['path'])
    if rebuilt!=compiled or compiled.get('status')!='READY_TO_PLAN':
        raise StudioError('Production textile fit compilation differs from exact approved source reconstruction')
    if plan_assembly(compiled['assembly_spec'],capabilities=['coupled_multilayer'])!=source_assembly:
        raise StudioError('Production textile fit intent belongs to another source assembly or exact body target')
    packages={row['id']:row['package_source_ref'] for row in compiled['components'] if row['pipeline']=='PATTERN_SEWN'}
    for binding in specification['components']:
        if packages.get(binding['component_id'])!=binding['package_ref']:
            raise StudioError('Production textile fit context does not own its actual executing source package')
    body_ref=source_assembly['body_ref'];body=load(body_ref);covered=set();assessments=[]
    for ref in context['fit_profiles_refs']:
        profile=load(ref)
        if profile['body_ref']!=body_ref or profile['dossier_ref']!=source_assembly['source_ref']:
            raise StudioError('Production textile fit profile belongs to another exact body or approved source dossier')
        report=require_fit_intent(project,context['compiled_dossier_ref']['path'],ref['path'])
        checks=report.get('checks',[]);actual={row['component_id'] for row in checks}
        declared=set(profile['component_ids']);relevant=components&declared
        if not relevant or not relevant<=actual:
            raise StudioError('Every executing production textile component needs actual owned fit checks, not declared IDs alone')
        if covered&relevant:raise StudioError('Several production fit profiles ambiguously own the same executing component')
        if (report.get('admission')!='EXPLORATORY_PHYSICS_ONLY' or
                report.get('body_profile_sha256')!=digest(body) or report.get('body_profile_cache_key')!=body['cache_key'] or
                any(row.get('status')not in ('WITHIN_DECLARED_SOURCE_EASE','OPEN_SPATIAL_COVERAGE_REQUIRED') for row in checks) or
                any(row.get('measurement_scope')!='NOMINAL_SOURCE_CAPACITY' for row in checks)):
            raise StudioError('Production textile fit checks are incomplete, stale, incompatible or outside their actual source scope')
        reviews={row['component_id']:row for row in report.get('human_reviews',[])}
        if any(reviews.get(cid,{}).get('numeric_ease',{}).get('status')!='REVIEWED' for cid in relevant):
            raise StudioError('Production textile numeric fit intent has no exact canonical human review for every component')
        covered.update(relevant);assessments.append({'profile_ref':copy.deepcopy(ref),'components':sorted(relevant),
            'assessment_sha256':report['assessment_sha256'],'admission':report['admission'],
            'human_reviews':copy.deepcopy(report['human_reviews'])})
    if covered!=components:raise StudioError('Production textile fit profiles do not cover every actual executing component')
    return {'purpose':purpose,'admission':'EXPLORATORY_PHYSICS_ONLY','covered_components':sorted(covered),
        'fit_context':copy.deepcopy(context),'body_ref':copy.deepcopy(body_ref),'fit_assessments':assessments,
        'production_qualification':'NOT_GRANTED','qualification':'NONE','accepted':False}


def load_textile_program(project, program_path):
    """Verify on-disk sources and compile; reads never mutate project state."""
    from .packages import inspect_package
    path = inside(project.root, program_path); spec = contract('textile-program', read_json(path))
    if spec['program_path'] != program_path:
        raise StudioError('Textile program path differs from the exact declared source')

    def load(ref):
        _reference(ref); file = inside(project.root, ref['path'])
        if sha(file) != ref['sha256']: raise StudioError('Textile source reference changed: '+ref['path'])
        return read_json(file)
    assembly = load(spec['assembly_plan_ref']); meshes = {}; recipes = {}; plans = {}
    state = project.state()
    if spec['asset_id'] != state['asset']['id']:
        raise StudioError('Textile program targets another asset')
    for binding in spec['components']:
        cid = binding['component_id']; package_ref = binding['package_ref']
        _reference(package_ref); package = inside(project.root, package_ref['path'])
        canonical_package = state['components'][cid]['package']
        if sha(package) != package_ref['sha256'] or {key: canonical_package[key] for key in ('path', 'sha256')} != package_ref:
            raise StudioError('Textile source package differs from canonical component binding')
        inspected = inspect_package(package)
        if inspected != canonical_package['manifest']:
            raise StudioError('Textile package manifest differs from the canonical component binding')
        with zipfile.ZipFile(package) as archive:
            source = json.loads(archive.read('garment.json'))
        meshes[cid] = load(binding['derived_mesh_ref']); recipes[cid] = load(binding['recipe_ref']); plans[cid] = load(binding['plan_ref'])
        if meshes[cid]['package_sha256'] != package_ref['sha256'] or meshes[cid]['source_garment_sha256'] != digest(source):
            raise StudioError('Derived textile source/package provenance changed')
        if set(meshes[cid]['panels']) != set(source['pieces']):
            raise StudioError('Native textile program needs complete source component coverage')
    admission=require_textile_program_admission(project,spec,assembly)
    compiled=compile_textile_program(assembly,spec,meshes,recipes,plans);compiled['execution_admission']=admission
    compiled['compiled_sha256']=digest({key:value for key,value in compiled.items() if key!='compiled_sha256'})
    return spec,compiled
