"""Fixed native textile coupons, with exact source bindings and bounded runs.

Comparisons describe the response of synthetic coupons using a cited recipe.
They never qualify the garment, its measured body, dressing or final fitting.
Compilation is pure preparation. Only run_material_bench enters Blender and
it uses the existing evaluated-frame Cloth runtime, with measured convergence.
"""
import copy
import math
import time
import uuid
from pathlib import Path

from .core import ROOT, StudioError, atomic_json, contract, digest, ident, inside, read_json, sha

PARAMETERS = {'tension_stiffness', 'compression_stiffness', 'shear_stiffness',
              'bending_stiffness', 'structural_damping', 'air_damping'}
PROGRAMS = ('cantilever', 'sewing', 'contact')
PROGRAM_VERSION = 'fixed-textile-coupons-v2'
LEGACY_SEEDS = 'legacy-v1'
SUPPORTED_SEEDS = 'supported-v2'


def laboratory_conditions(seed_set=LEGACY_SEEDS):
    """Declared apparatus and initial geometry, fixed before factor comparison.

    V2 is a separate experiment. Its sewing seed tests an already admitted
    narrow seam, not the closure of separated panels. No contact exemption,
    metric threshold or physical recipe parameter is changed by this seed.
    """
    if seed_set not in (LEGACY_SEEDS, SUPPORTED_SEEDS):
        raise StudioError('Unknown fixed laboratory source seed set')
    supported = seed_set == SUPPORTED_SEEDS
    return {'seed_set': seed_set, 'units': 'cm',
        'cantilever': {'width_cm': 10., 'free_length_cm': 10. if supported else 20.,
            'height_cm': 20., 'clamp': 'SOURCE_FIRST_ROW',
            'scope': 'HORIZONTAL_GRAVITY_BENDING_WITH_FIXED_LABORATORY_CLAMP'},
        'sewing': {'panel_size_cm': 10., 'height_cm': 6.,
            'initial_gap_cm': .1 if supported else 1., 'clamp': 'TWO_OUTER_SOURCE_ROWS',
            'scope': 'NARROW_ADMITTED_SEAM_RESPONSE_NOT_WIDE_GAP_CLOSURE' if supported
                     else 'SEPARATED_PANEL_CLOSURE'},
        'contact': {'panel_size_cm': 10., 'height_cm': .6 if supported else 2.,
            'clamp': 'SOURCE_FIRST_ROW' if supported else 'NONE',
            'support_vertices_cm': [[x,y,z] for z in (-10.,0.) for y in (-25.,35.) for x in (-25.,35.)],
            'support_faces': [[0,2,3,1],[4,5,7,6],[0,1,5,4],[1,3,7,5],[3,2,6,7],[2,0,4,6]],
            'support_thickness_outer_cm': .1, 'support_thickness_inner_cm': .1,
            'scope': 'TETHERED_DROP_ON_CLOSED_SUPPORT' if supported else 'FREE_DROP_ON_CLOSED_SUPPORT'}}


def _conditions(spec):
    return laboratory_conditions(spec.get('laboratory', {}).get('seed_set', LEGACY_SEEDS))


def checked_bindings(project, bindings):
    """Resolve source bytes, not a caller-supplied PASS or verification flag."""
    result = {}
    for key, ref in bindings.items():
        if not isinstance(ref, dict) or set(ref) != {'path', 'sha256'}:
            raise StudioError('Benchmark/dressing bindings require exact path and SHA-256')
        path = inside(project.root, ref['path'])
        if not path.is_file() or sha(path) != ref['sha256']:
            raise StudioError('Benchmark/dressing binding is stale: '+key)
        result[key] = copy.deepcopy(ref)
    if len({ref['path'] for ref in result.values()}) != len(result):
        raise StudioError('Candidate, source, body, pose and recipe bindings must identify distinct records')
    return result


def _descriptor(project, specification_path):
    spec = contract('material-bench', read_json(inside(project.root, specification_path)))
    ident(spec['id']); ident(spec['component_id'])
    state=project.state()
    component = next((item for item in state['asset']['components'] if item['id']==spec['component_id']),None)
    if component is None or component['type'] != 'garment':
        raise StudioError('Material benchmark requires the identified garment component')
    bindings = checked_bindings(project, spec['bindings'])
    recipe = contract('sewing-recipe', read_json(inside(project.root, bindings['recipe']['path'])))
    if recipe['component_id'] != spec['component_id']:
        raise StudioError('Material benchmark recipe identifies another garment')
    profile = recipe['phases'][spec['phase']]
    if 'regional_stiffness' in profile:
        raise StudioError('Fixed coupons require an explicitly reviewed uniform recipe; regional mappings cannot be inferred')
    if spec['factor']['parameter'] not in PARAMETERS:
        raise StudioError('Unsupported textile benchmark factor')
    values = spec['factor']['values']
    if len(set(values)) != len(values):
        raise StudioError('Textile comparison factor values must be distinct')
    if profile['fps'] != spec['execution']['fps']:
        raise StudioError('Benchmark frame rate must match its cited source recipe')
    if not .5 <= recipe['mesh']['spacing_cm'] <= 5.:
        raise StudioError('Fixed coupon spacing must stay within its bounded 0.5 to 5 cm inventory')
    if spec['execution']['window_frames'] >= spec['execution']['max_frames']:
        raise StudioError('Convergence window requires a subsequent evaluated frame')
    if spec['execution']['min_frames'] > spec['execution']['max_frames']:
        raise StudioError('Minimum observation exceeds the frame budget')
    conditions = _conditions(spec)
    if conditions['seed_set'] == SUPPORTED_SEEDS:
        if 'cantilever' in spec['programs'] and 2*conditions['cantilever']['free_length_cm']*recipe['mesh']['max_stretch'] > recipe['limits']['max_displacement_cm']:
            raise StudioError('Laboratory free length cannot fit the cited displacement budget at allowed stretch')
        gap = conditions['sewing']['initial_gap_cm']
        if 'sewing' in spec['programs'] and gap > min(recipe['limits']['weld_gap_cm'],recipe['limits']['max_seam_gap_cm']):
            raise StudioError('Supported sewing seed must be inside the unchanged direct seam tolerance')
        if 'contact' in spec['programs'] and conditions['contact']['height_cm'] <= profile['collision_distance_cm']+conditions['contact']['support_thickness_outer_cm']:
            raise StudioError('Supported contact seed must start outside the cited collision envelope')
    return spec, bindings, recipe


def case_recipe(recipe, spec, value):
    """Exactly one physical factor changes between coupons of the same program."""
    result = copy.deepcopy(recipe)
    profile = result['phases'][spec['phase']]
    profile[spec['factor']['parameter']] = value
    execution = spec['execution']
    profile['frames'] = execution['max_frames']
    profile['execution_control'] = {key: execution[key] for key in
        ('max_seconds', 'min_frames', 'window_frames', 'velocity_tolerance_cm_s')}
    contract('sewing-recipe', result)
    return result


def _code_sources():
    paths = ['a3d/material_bench.py', 'a3d/simulation_control.py', 'a3d/cloth_metrics.py',
             'a3d/contact_geometry.py', 'a3d/sewing_diagnostics.py', 'blender/pattern_assembly.py',
             'a3d/sewing.py', 'blender/sewing.py', 'blender/cloth_contacts.py',
             'schemas/material-bench.schema.json', 'schemas/sewing-recipe.schema.json']
    return {path: sha(ROOT/path) for path in paths}


def compile_material_bench(project, specification_path, output_dir):
    """Write immutable recipes and one native execution unit; execute nothing."""
    if project.state().get('pending_blender_operation') or project.state()['stage'] == 'COMPLETE':
        raise StudioError('Pending or completed project prevents benchmark preparation')
    spec, bindings, recipe = _descriptor(project, specification_path)
    output = inside(project.root, output_dir, False)
    if output.exists():
        raise StudioError('Benchmark output must be a new project directory')
    cases = []
    conditions = _conditions(spec)
    for program in spec['programs']:
        for index, value in enumerate(spec['factor']['values']):
            local = case_recipe(recipe, spec, value)
            payload = coupon(program, recipe['mesh']['spacing_cm'], conditions['seed_set'])
            if len(payload['rest_cm']) > recipe['mesh']['max_vertices']:
                raise StudioError('Laboratory coupon exceeds the source mesh vertex budget')
            cases.append({'id': program+'.'+str(index), 'program': program, 'factor_value': value,
                          'recipe_sha256': digest(local), 'recipe': local,
                          'coupon_sha256': digest(payload), 'source_conditions_sha256': digest(conditions[program])})
    codes = _code_sources()
    document = {'version': 1, 'id': spec['id'], 'component_id': spec['component_id'],
        'program_version': PROGRAM_VERSION, 'specification': {'path': specification_path,
        'sha256': sha(inside(project.root, specification_path))}, 'bindings': bindings,
        'factor': copy.deepcopy(spec['factor']), 'phase': spec['phase'],
        'execution': copy.deepcopy(spec['execution']), 'laboratory_conditions': conditions,
        'cases': cases, 'code_sources': codes,
        'qualification': 'NOT_EXECUTED', 'accepted': False,
        'body_scope': 'REFERENCE_BOUND_BODY_AND_POSE_NOT_TESTED_BY_SYNTHETIC_COUPONS'}
    document['fingerprint'] = digest(document)
    output.mkdir(parents=True)
    path = output/'bench.json'; atomic_json(path, document)
    ref = {'path': path.relative_to(project.root).as_posix(), 'sha256': sha(path)}
    native_output = (output/'native').relative_to(project.root).as_posix()
    run = {'version': 1, 'id': spec['id'], 'asset_id': project.state()['asset']['id'],
        'kind': 'material_bench', 'inputs': list(bindings.values())+[ref],
        'budgets': {'max_attempts': 1, 'max_seconds': min(3600., len(cases)*spec['execution']['max_seconds'])},
        'units': [{'id': 'coupons', 'dependencies': [], 'executor': 'blender',
            'operation': 'run_material_bench', 'arguments': {'bench_path': ref['path'], 'output_dir': native_output},
            'inputs': list(bindings.values())+[ref], 'code_paths': list(codes), 'success_statuses': ['PASS']}]}
    contract('run', run); run_path = output/'run.json'; atomic_json(run_path, run)
    return {'status': 'PREPARED', 'bench': ref,
            'run_specification': {'path': run_path.relative_to(project.root).as_posix(), 'sha256': sha(run_path)},
            'case_count': len(cases), 'executed': False, 'qualification': 'NOT_EXECUTED', 'accepted': False}


def _load_compiled(project, bench_path):
    doc = read_json(inside(project.root, bench_path))
    expected = doc.get('fingerprint'); bound = dict(doc); bound.pop('fingerprint', None)
    if expected != digest(bound) or doc['program_version'] != PROGRAM_VERSION or doc['code_sources'] != _code_sources():
        raise StudioError('Compiled benchmark or native runtime changed; prepare a new benchmark')
    source = doc['specification']
    if sha(inside(project.root, source['path'])) != source['sha256']:
        raise StudioError('Benchmark specification changed')
    spec, bindings, recipe = _descriptor(project, source['path'])
    if bindings != doc['bindings']:
        raise StudioError('Compiled benchmark source bindings changed')
    expected_cases = []
    conditions = _conditions(spec)
    for program in spec['programs']:
        for index,value in enumerate(spec['factor']['values']):
            expected_recipe=case_recipe(recipe,spec,value)
            expected_cases.append({'id':program+'.'+str(index),'program':program,'factor_value':value,
                'recipe_sha256':digest(expected_recipe),'recipe':expected_recipe,
                'coupon_sha256':digest(coupon(program,recipe['mesh']['spacing_cm'],conditions['seed_set'])),
                'source_conditions_sha256':digest(conditions[program])})
    if doc['cases']!=expected_cases or doc['phase']!=spec['phase'] or doc['execution']!=spec['execution'] or doc['factor']!=spec['factor'] or doc.get('laboratory_conditions')!=conditions:
        raise StudioError('Compiled coupon changes more than the declared factor or bounded case inventory')
    return doc


def coupon(program, spacing_cm, seed_set=LEGACY_SEEDS):
    """Fixed metric coupons. Laboratory clamps are functional supports."""
    if program not in PROGRAMS:
        raise StudioError('Unknown fixed textile coupon program')
    if type(spacing_cm) not in (int, float) or not math.isfinite(spacing_cm) or not .5 <= spacing_cm <= 5.:
        raise StudioError('Coupon spacing must be finite and within 0.5 to 5 cm')
    conditions = laboratory_conditions(seed_set)[program]
    from blender.sewing import grid_probe
    if program in ('contact', 'sewing'):
        payload = grid_probe(spacing_cm, two=program == 'sewing', height=conditions['height_cm'])
        if program == 'sewing':
            for index in payload['panels']['synthetic-1']['indices']:
                payload['placed_cm'][index][0] += conditions['initial_gap_cm']-1.
        elif conditions['clamp'] == 'SOURCE_FIRST_ROW':
            payload['pins'] = {str(index): 1. for index,point in enumerate(payload['rest_cm']) if point[1] == 0.}
    else:
        width,length = conditions['width_cm'],conditions['free_length_cm']
        nx, ny = math.ceil(width/spacing_cm), math.ceil(length/spacing_cm)
        points = [[i*width/nx, j*length/ny, 0.] for j in range(ny+1) for i in range(nx+1)]
        faces = []
        for j in range(ny):
            for i in range(nx):
                index = j*(nx+1)+i
                faces.extend([[index,index+1,index+nx+2], [index,index+nx+2,index+nx+1]])
        bottom = list(range(nx+1)); top = [ny*(nx+1)+i for i in range(nx+1)]
        payload = {'rest_cm': points, 'placed_cm': [[x,y,conditions['height_cm']] for x,y,_ in points], 'faces': faces,
            'seams': {}, 'pins': {str(index): 1. for index in bottom}, 'full_rest_area_cm2': width*length,
            'panels': {'synthetic-0': {'indices': list(range(len(points))), 'boundary': [],
                                      'edges': {'clamp': bottom, 'free': top}}}}
    payload.update(component_id='synthetic.coupon.'+program, synthetic=True,
        source_garment_sha256='synthetic:'+PROGRAM_VERSION,
        laboratory_source={'seed_set': seed_set, 'conditions': conditions, 'sha256': digest(conditions)},
        pattern_assembly={'contact_policy': {'clearance_cm': 0.}, 'temporary_supports_active': False})
    return payload


def observation_summary(frames, fps, control=None):
    """Compact actual-frame measurements for successful and refused cases alike.

    Velocity is the largest observed vertex increment times FPS, not a solver
    substep velocity. Contact remains the native check's declared coverage.
    The failed last frame is retained even when the convergence monitor has
    not admitted that frame; missing measurements never become zero or PASS.
    """
    samples = []
    for index, item in enumerate(frames):
        if item.get('frame') != index+1:
            raise StudioError('Coupon observation must retain every consecutive evaluated frame')
        motion = item.get('motion', {})
        quality = item.get('quality', {})
        metrics = quality.get('metrics') or {}
        contact = item.get('contact') or {}
        surface = contact.get('worst_sample') or contact.get('contact') or contact
        increment = motion.get('max_increment', {}).get('distance_cm')
        velocity = increment*fps if index and increment is not None else None
        samples.append({'frame': item['frame'], 'max_excursion_cm': item.get('max_movement_cm'),
            'max_increment_cm': increment, 'max_velocity_cm_s': velocity,
            'max_seam_gap_cm': item.get('max_seam_gap_cm'), 'quality_status': quality.get('status'),
            'min_principal_stretch': metrics.get('min_principal_stretch'),
            'max_principal_stretch': metrics.get('max_principal_stretch'),
            'contact_status': contact.get('status'), 'contact_ok': contact.get('ok'),
            'minimum_signed_offset_cm': surface.get('minimum_signed_offset_cm'),
            'contact_reason': contact.get('reason'), 'contact_fraction': contact.get('fraction'),
            'contact_coverage': contact.get('coverage'),
            'solver_max_iterations': item.get('solver_max_iterations')})
    settings = (control or {}).get('control') or {}
    window = settings.get('window_frames')
    tail = samples[-window:] if window else samples
    speeds = [sample['max_velocity_cm_s'] for sample in tail if sample['max_velocity_cm_s'] is not None]
    return {'scope': 'ACTUAL_INTEGER_FRAME_OBSERVATIONS_NOT_SOLVER_SUBSTEP_VELOCITY',
        'evaluated_frame_count': len(samples), 'samples': samples,
        'terminal_window': {'requested_intervals': window,
            'observed_velocity_intervals': len(speeds),
            'minimum_velocity_cm_s': min(speeds) if speeds else None,
            'maximum_velocity_cm_s': max(speeds) if speeds else None,
            'tolerance_cm_s': settings.get('velocity_tolerance_cm_s'),
            'hard_gates_clear': all(sample['quality_status']=='PASS' and sample['contact_ok'] is True for sample in tail) if tail else None},
        'convergence': 'MEASURED' if (control or {}).get('stop_reason')=='MEASURED_CONVERGENCE' else 'NOT_QUALIFIED'}


def coupon_response(payload, coordinates):
    """An observed end state, including unsuccessful runs; never acceptance."""
    if len(coordinates) != len(payload['placed_cm']) or any(len(point)!=3 or
            any(type(value) not in (int,float) or not math.isfinite(value) for value in point) for point in coordinates):
        return {'status': 'UNAVAILABLE_NONFINITE_OR_CHANGED_TOPOLOGY'}
    distances = [math.dist(a,b) for a,b in zip(payload['placed_cm'], coordinates)]
    pairs = [pair for seam in payload['seams'].values() for pair in seam['pairs']]
    return {'status': 'OBSERVED_NOT_QUALIFIED',
        'rms_displacement_cm': math.sqrt(sum(value*value for value in distances)/len(distances)),
        'max_displacement_cm': max(distances),
        'centroid_final_cm': [sum(point[k] for point in coordinates)/len(coordinates) for k in range(3)],
        'initial_seam_gap_cm': max((math.dist(payload['placed_cm'][a],payload['placed_cm'][b]) for a,b in pairs),default=0.),
        'final_seam_gap_cm': max((math.dist(coordinates[a],coordinates[b]) for a,b in pairs),default=0.)}


def comparison_report(document, rows):
    """An observed response table, never an automatic textile selection."""
    return {'factor': copy.deepcopy(document['factor']), 'program_version': PROGRAM_VERSION,
        'laboratory_conditions': copy.deepcopy(document.get('laboratory_conditions')),
        'comparison_scope': 'SAME_SOURCE_GEOMETRY_CLAMPS_SUPPORT_RECIPE_BUDGETS_ONE_PHYSICAL_FACTOR_PER_PROGRAM',
        'rows': [{key: copy.deepcopy(row.get(key)) for key in
                  ('case_id', 'program', 'factor_value', 'status', 'error', 'response', 'execution_control',
                   'observations', 'initial_contact', 'refusal_contact',
                   'source_conditions_sha256', 'coupon_sha256', 'receipt')} for row in rows],
        'automatic_selection': False, 'qualification': 'COUPON_ONLY',
        'garment_simulation': 'NOT_EXECUTED', 'fitting': 'NOT_EXECUTED', 'accepted': False}


def run_material_bench(project_root, bench_path, output_dir):
    """Native dispatcher target. Each coupon has a fresh scene and fresh cache."""
    import bpy
    from mathutils import Vector
    from mathutils.bvhtree import BVHTree
    from .store import Project
    from blender.sewing import make_object, simulate_object, object_mesh
    from blender.cloth_contacts import build_contact_context, check_contacts
    project = Project(project_root); document = _load_compiled(project, bench_path)
    output = inside(project.root, output_dir, False)
    if output.exists(): raise StudioError('Native benchmark output must be new')
    output.mkdir(parents=True)
    original_scene = bpy.context.window.scene; original_frame = original_scene.frame_current
    original_objects = {obj.name: digest({'matrix': [list(row) for row in obj.matrix_world],
        'vertices': [list(vertex.co) for vertex in obj.data.vertices] if obj.type == 'MESH' else None}) for obj in original_scene.objects}
    rows = []
    try:
        for case in document['cases']:
            existing_collections=set(collection.name for collection in bpy.data.collections)
            scene = bpy.data.scenes.new('A3D.MaterialBench.'+uuid.uuid4().hex[:8])
            bpy.context.window.scene = scene
            scene.unit_settings.system='METRIC'; scene.unit_settings.scale_length=1.
            conditions = document['laboratory_conditions'][case['program']]
            payload = coupon(case['program'], case['recipe']['mesh']['spacing_cm'],document['laboratory_conditions']['seed_set'])
            if digest(payload)!=case['coupon_sha256'] or digest(conditions)!=case['source_conditions_sha256']:
                raise StudioError('Native coupon source differs from the prepared source geometry')
            local = copy.deepcopy(case['recipe']); obj = make_object(payload, 'A3D.Coupon.'+case['id'])
            created_meshes = [obj.data]; colliders = []; trees = []; diagnostics = []
            row = {'case_id': case['id'], 'program': case['program'], 'factor_value': case['factor_value'],
                'status': 'INCOMPLETE', 'bindings': copy.deepcopy(document['bindings']),
                'source_recipe_sha256': case['recipe_sha256'], 'coupon_sha256': digest(payload),
                'source_conditions_sha256': case['source_conditions_sha256'],
                'laboratory_conditions': copy.deepcopy(conditions),
                'recipe': local, 'qualification': 'COUPON_ONLY', 'accepted': False,
                'blender_version': bpy.app.version_string, 'blender_build_hash': bpy.app.build_hash.decode()}
            started = time.monotonic()
            try:
                if case['program'] == 'contact':
                    mesh = bpy.data.meshes.new('A3D.LaboratorySupport.Mesh')
                    vertices = [[coordinate/100 for coordinate in point] for point in conditions['support_vertices_cm']]
                    faces = conditions['support_faces']
                    mesh.from_pydata(vertices, [], faces); mesh.update(); created_meshes.append(mesh)
                    body = bpy.data.objects.new('A3D.LaboratorySupport', mesh); scene.collection.objects.link(body)
                    body.modifiers.new('Collision', 'COLLISION')
                    body.collision.thickness_outer=conditions['support_thickness_outer_cm']/100
                    body.collision.thickness_inner=conditions['support_thickness_inner_cm']/100; colliders=[body]
                    coords, topology = object_mesh(body, True)
                    trees=[BVHTree.FromPolygons([Vector(point) for point in coords], topology)]
                profile=local['phases'][document['phase']]
                contact_context=build_contact_context(payload,colliders,
                    clearance_cm=payload['pattern_assembly']['contact_policy']['clearance_cm'],
                    self_clearance_cm=profile['self_distance_cm'] if profile['self_collision'] else 0.,
                    seam_tolerance_cm=local['limits']['weld_gap_cm'],
                    max_penetration_cm=local['limits']['max_penetration_cm'])
                initial_cm=[[coordinate*100 for coordinate in point] for point in object_mesh(obj,True)[0]]
                row['initial_contact']=check_contacts(contact_context,initial_cm,frame=0)
                coords, measured = simulate_object(obj, payload, local, document['phase'], colliders, trees,
                                                   save_diagnostic=lambda data: diagnostics.append(copy.deepcopy(data)))
                control = measured.get('execution_control', {})
                if control.get('stop_reason') != 'MEASURED_CONVERGENCE':
                    raise StudioError('Coupon returned without measured convergence')
                row.update(status='PASS', native=measured, execution_control=control,
                    response=coupon_response(payload,coords),
                    observations=observation_summary(measured['frames'],local['phases'][document['phase']]['fps'],control))
            except StudioError as error:
                row.update(status=getattr(error, 'simulation_outcome', 'FAIL'), error=str(error), diagnostics=diagnostics)
                if diagnostics:
                    last = diagnostics[-1]
                    row['execution_control'] = last.get('execution_control')
                    row['observations'] = observation_summary(last.get('frames',[]),local['phases'][document['phase']]['fps'],row['execution_control'])
                    row['response'] = coupon_response(payload,last.get('geometry',{}).get('evaluated_cm',[]))
                    row['refusal_contact'] = last.get('contact')
            finally:
                row['elapsed_seconds'] = time.monotonic()-started
                for item in list(scene.objects): bpy.data.objects.remove(item, do_unlink=True)
                bpy.context.window.scene = original_scene; bpy.data.scenes.remove(scene)
                for mesh in created_meshes:
                    if mesh.users == 0: bpy.data.meshes.remove(mesh)
                for collection in list(bpy.data.collections):
                    if collection.name not in existing_collections and collection.users==0:
                        bpy.data.collections.remove(collection)
            path = output/(case['id']+'.json'); atomic_json(path, row)
            row['receipt'] = {'path': path.relative_to(project.root).as_posix(), 'sha256': sha(path)}
            rows.append(row)
    finally:
        bpy.context.window.scene = original_scene
        if original_scene.frame_current != original_frame: original_scene.frame_set(original_frame)
    after = {obj.name: digest({'matrix': [list(row) for row in obj.matrix_world],
        'vertices': [list(vertex.co) for vertex in obj.data.vertices] if obj.type == 'MESH' else None}) for obj in original_scene.objects}
    if after != original_objects:
        raise StudioError('Native coupon changed the original scene')
    report = comparison_report(document, rows)
    report.update(status='PASS' if all(row['status']=='PASS' for row in rows)
                  else 'FAIL' if any(row['status']=='FAIL' for row in rows) else 'INCOMPLETE',
                  bindings=copy.deepcopy(document['bindings']), bench_sha256=sha(inside(project.root, bench_path)),
                  original_scene_unchanged=True, source_patterns_changed=False)
    path = output/'comparison.json'; atomic_json(path, report)
    return {'status': report['status'], 'qualification': 'COUPON_ONLY', 'accepted': False,
            'report': {'path': path.relative_to(project.root).as_posix(), 'sha256': sha(path)},
            'cases': [row['receipt'] for row in rows], 'garment_simulation': 'NOT_EXECUTED', 'fitting': 'NOT_EXECUTED'}
