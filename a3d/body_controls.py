"""Source-bound radial torso controls and bounded deterministic fitting of girths.

The cage is derived from an explicitly sourced torso segmentation. It changes
only the declared body copy, never a pattern or a fitting acceptance threshold.
Joint boundaries, feet and vertices outside the torso remain fixed. Shoulder and
limb-length controls require separate qualified cages and are refused here.
"""
import copy
import math

from .anatomy_profile import profile_mesh, surface_section
from .body_dimensions import _validate
from .contact_geometry import dot, sub
from .core import StudioError, digest

GIRTH_CONTROLS = ('hip', 'waist', 'chest')
WIDTH_DEPTH_RELATIVE_TOLERANCE = .0001


def _finite(value):
    return type(value) in (int, float) and math.isfinite(value)


def _hat(height, knots, index):
    low, center, high = knots[index:index+3]
    if height <= low or height >= high:
        return 0.
    return ((height-low)/(center-low) if height <= center else
            (high-height)/(high-center))


def cage_from_segmentation(geometry, options):
    """Build a cage from exact current geometry and source face IDs.

    Input torso_faces must already have been admitted against the original
    source adapter. A stature derivation may retain these face identities; its
    metric must never be rebound to the original adapter's geometry identity.
    """
    _validate(geometry, options, 180.)
    if 'torso_faces' not in options or not options.get('segmentation_source_ref'):
        raise StudioError('Body controls require explicitly sourced torso face segmentation')
    profile = profile_mesh(geometry, options)
    if any(name not in profile['landmarks'] for name in GIRTH_CONTROLS):
        raise StudioError('Body controls require measured hip, waist and chest sections')
    frame = profile['frame']; nodes = []
    for name in GIRTH_CONTROLS:
        landmark = profile['landmarks'][name]
        nodes.append({'name': name, 'height_cm': landmark['section_height_cm'],
                      'center_xy_cm': landmark['point_cm'][:2]})
    heights = [node['height_cm'] for node in nodes]
    if any(b-a < .005*profile['stature_cm'] for a, b in zip(heights, heights[1:])):
        raise StudioError('Body control section heights overlap or have unsupported order')
    knots = [max(profile['floor_cm'], heights[0]-.1*profile['stature_cm']),
             *heights, min(profile['floor_cm']+profile['stature_cm'],
                           heights[-1]+.1*profile['stature_cm'])]
    torso = set(options['torso_faces']); eligible = set(); excluded = set()
    for index, face in enumerate(geometry['faces']):
        (eligible if index in torso else excluded).update(face)
    # Shared limb/head boundaries are protected, including shared vertex IDs.
    controlled = eligible-excluded
    weights = []
    for index in sorted(controlled):
        point = geometry['vertices_cm'][index]
        height = dot(sub(point, frame['origin_cm']), frame['up'])
        row = [_hat(height, knots, i) for i in range(3)]
        if any(row):
            weights.append({'vertex': index, 'weights': row})
    if any(not any(row['weights'][i] > 1e-8 for row in weights) for i in range(3)):
        raise StudioError('Torso mesh has insufficient interior vertices for all requested controls')
    protected = sorted(set(range(len(geometry['vertices_cm'])))-{row['vertex'] for row in weights})
    result = {'version': 1, 'method': 'SOURCE_TORSO_RADIAL_SECTION_CAGE',
              'geometry_sha256': digest([geometry['vertices_cm'], geometry['faces']]),
              'source_sha256': geometry['source_sha256'], 'pose_sha256': geometry['pose_sha256'],
              'options_sha256': digest(options), 'source_ref': copy.deepcopy(options['segmentation_source_ref']),
              'frame': frame, 'nodes': nodes, 'knots_cm': knots, 'weights': weights,
              'protected_vertex_ids': protected, 'topology_sha256': digest(geometry['faces']),
              'width_depth_policy': 'PRESERVE_MEASURED_SOURCE_SECTION_RATIO_WITH_PROTECTED_BOUNDARIES',
              'qualification': 'TORSO_GIRTH_CONTROLS_REQUIRE_ANATOMICAL_REVIEW',
              'unsupported_controls': ['shoulder_width', 'arm_length', 'leg_length']}
    result['cache_key'] = digest(result)
    return result


def _validate_cage(geometry, options, cage):
    _validate(geometry, options, 180.)
    expected = {'geometry_sha256': digest([geometry['vertices_cm'], geometry['faces']]),
                'source_sha256': geometry['source_sha256'], 'pose_sha256': geometry['pose_sha256'],
                'options_sha256': digest(options), 'topology_sha256': digest(geometry['faces'])}
    if not isinstance(cage, dict) or any(cage.get(k) != v for k, v in expected.items()):
        raise StudioError('Body control cage is stale for the geometry, pose or measurement options')
    payload = {key: value for key, value in cage.items() if key != 'cache_key'}
    if cage.get('cache_key') != digest(payload):
        raise StudioError('Body control cage contents changed')
    # Rebuild once to reject a fabricated source-bound but semantically different cage.
    if cage != cage_from_segmentation(geometry, options):
        raise StudioError('Body cage differs from its declared source segmentation')


def _center(height, nodes):
    if height <= nodes[0]['height_cm']:
        return nodes[0]['center_xy_cm']
    for left, right in zip(nodes, nodes[1:]):
        if height <= right['height_cm']:
            factor = (height-left['height_cm'])/(right['height_cm']-left['height_cm'])
            return [a+factor*(b-a) for a, b in zip(left['center_xy_cm'], right['center_xy_cm'])]
    return nodes[-1]['center_xy_cm']


def _deform(geometry, cage, parameters):
    output = copy.deepcopy(geometry); frame = cage['frame']
    for row in cage['weights']:
        index = row['vertex']; original = geometry['vertices_cm'][index]
        local = [dot(sub(original, frame['origin_cm']), frame[key])
                 for key in ('right', 'forward', 'up')]
        center = _center(local[2], cage['nodes'])
        factors = [math.exp(sum(weight*parameters[2*region+axis] for region, weight in enumerate(row['weights'])))
                   for axis in range(2)]
        delta = [(local[i]-center[i])*(factors[i]-1.) for i in range(2)]
        output['vertices_cm'][index] = [original[i]+delta[0]*frame['right'][i]+delta[1]*frame['forward'][i]
                                       for i in range(3)]
    # Joint guides remain attached to protected joint boundaries. This is a
    # mesh-copy operation and does not manufacture an animated or accepted rig.
    output['pose_sha256'] = digest({'source_pose_sha256': geometry['pose_sha256'],
                                   'cage': cage['cache_key'], 'parameters': parameters})
    return output


def section_dimensions(geometry, options, source_profile, names=GIRTH_CONTROLS):
    """Measure actual cut planes, including interpolation across protected seams.

Equal factors at a mobile vertex do not preserve a section when a cut edge's
other endpoint is protected. The final contour must therefore be measured.
No geometry or anatomical landmark is replaced to satisfy this constraint.
"""
    basis = source_profile['frame']
    local = [[dot(sub(point, basis['origin_cm']), basis[key]) for key in ('right', 'forward', 'up')]
             for point in geometry['vertices_cm']]
    faces = [geometry['faces'][index] for index in options['torso_faces']]
    result = {}
    for name in names:
        landmark = source_profile['landmarks'][name]
        section = surface_section(local, faces, landmark['section_height_cm'], landmark['point_cm'][:2])
        if section['status'] != 'MEASURED':
            raise StudioError('Body correction lost its source width/depth cut plane: ' + name)
        low, high = section['bounds_xy_cm']; width, depth = high[0]-low[0], high[1]-low[1]
        if width <= 0. or depth <= 0.:
            raise StudioError('Body width/depth section is collapsed: ' + name)
        result[name] = {'width_cm': width, 'depth_cm': depth, 'width_depth_ratio': width/depth,
                        'section_height_cm': landmark['section_height_cm']}
    return result


def _linear_solve(matrix, vector):
    rows = [list(row)+[value] for row, value in zip(matrix, vector)]
    n = len(vector)
    for column in range(n):
        pivot = max(range(column, n), key=lambda i: abs(rows[i][column]))
        if abs(rows[pivot][column]) < 1e-14:
            raise StudioError('Body control Jacobian is singular')
        rows[column], rows[pivot] = rows[pivot], rows[column]
        divisor = rows[column][column]
        rows[column] = [x/divisor for x in rows[column]]
        for i in range(n):
            if i == column:
                continue
            factor = rows[i][column]
            rows[i] = [a-factor*b for a, b in zip(rows[i], rows[column])]
    return [row[-1] for row in rows]


def solve_girths(geometry, options, cage, targets_cm, tolerance_cm, budgets):
    """Fit measured profile girths within an explicit bounded radial domain.

    On stagnation or budget exhaustion return the best nonqualified candidate,
    with residuals. Missing or unsupported controls are refused before mutation.
    """
    _validate_cage(geometry, options, cage)
    if not isinstance(targets_cm, dict) or not targets_cm:
        raise StudioError('Body controls need explicit girth targets')
    if set(targets_cm)-set(GIRTH_CONTROLS):
        raise StudioError('Unsupported body control; shoulder or limb controls require a qualified cage')
    if any(not _finite(value) or not 10 <= value <= 400 for value in targets_cm.values()):
        raise StudioError('Body girth targets must be finite within 10 to 400 cm')
    if not _finite(tolerance_cm) or not .00001 <= tolerance_cm <= 2.:
        raise StudioError('Body girth tolerance must be declared within .00001 to 2 cm')
    keys = {'max_iterations', 'max_evaluations', 'finite_difference_step', 'damping',
            'line_search_steps', 'min_scale', 'max_scale'}
    if not isinstance(budgets, dict) or set(budgets) != keys:
        raise StudioError('Body control solver requires all explicit budgets')
    for key, lo, hi in [('max_iterations', 1, 100), ('max_evaluations', 1, 2000), ('line_search_steps', 1, 20)]:
        if type(budgets[key]) is not int or not lo <= budgets[key] <= hi:
            raise StudioError('Invalid body solver budget: '+key)
    for key, lo, hi in [('finite_difference_step', .00001, .05), ('damping', 1e-12, 100.),
                        ('min_scale', .5, 1.), ('max_scale', 1., 1.5)]:
        if not _finite(budgets[key]) or not lo <= budgets[key] <= hi:
            raise StudioError('Invalid body solver domain: '+key)
    if budgets['min_scale'] >= budgets['max_scale']:
        raise StudioError('Body solver scale domain is empty')
    before = digest([geometry, options, cage, targets_cm, budgets])
    regions = [i for i, name in enumerate(GIRTH_CONTROLS) if name in targets_cm]
    names = [GIRTH_CONTROLS[i] for i in regions]; evaluations = 0; history = []
    source_profile = profile_mesh(geometry, options)
    source_dimensions = section_dimensions(geometry, options, source_profile, names)

    def evaluate(parameters):
        nonlocal evaluations
        if evaluations >= budgets['max_evaluations']:
            return None
        evaluations += 1
        variant = _deform(geometry, cage, parameters)
        profile = profile_mesh(variant, options)
        if any(name not in profile['landmarks'] for name in names):
            raise StudioError('Body correction lost a qualified source torso section')
        residuals = [profile['landmarks'][name]['girth_cm']-targets_cm[name] for name in names]
        dimensions = section_dimensions(variant, options, source_profile, names)
        ratios = [dimensions[name]['width_depth_ratio']/source_dimensions[name]['width_depth_ratio'] for name in names]
        # Convert the dimensionless shape constraints to source-girth units so
        # the damped least-squares system has comparable measured residuals.
        shape_residuals = [source_profile['landmarks'][name]['girth_cm']*math.log(ratio)
                           for name, ratio in zip(names, ratios, strict=True)]
        vector = [*residuals, *shape_residuals]
        return (sum(value*value for value in vector), residuals, variant, profile, dimensions, vector)

    def admitted(candidate):
        return (max(abs(value) for value in candidate[1]) <= tolerance_cm and
                all(abs(candidate[4][name]['width_depth_ratio']/source_dimensions[name]['width_depth_ratio']-1.)
                    <= WIDTH_DEPTH_RELATIVE_TOLERANCE for name in names))

    parameters = [0.] * 6; best = evaluate(parameters)
    # Prefer exact equal-axis radial controls. Add shape-compensation degrees
    # of freedom only when actual protected-boundary section measurements show
    # that this simple transform no longer conserves the source ratio.
    compensate = False
    status = 'BUDGET_EXHAUSTED'; iterations = 0
    low, high = math.log(budgets['min_scale']), math.log(budgets['max_scale'])
    for iteration in range(budgets['max_iterations']):
        iterations = iteration+1
        history.append({'iteration': iteration, 'evaluations': evaluations,
                        'residuals_cm': dict(zip(names, best[1])), 'squared_error': best[0],
                        'width_depth_relative_errors': {name: best[4][name]['width_depth_ratio']/source_dimensions[name]['width_depth_ratio']-1.
                                                       for name in names}})
        if admitted(best):
            status = 'TARGETS_MEASURED'; break
        if any(abs(best[4][name]['width_depth_ratio']/source_dimensions[name]['width_depth_ratio']-1.)
               > WIDTH_DEPTH_RELATIVE_TOLERANCE for name in names):
            compensate = True
        active = ([[2*region+axis] for region in regions for axis in range(2)] if compensate else
                  [[2*region, 2*region+1] for region in regions])
        columns = []
        for indices in active:
            perturbation = budgets['finite_difference_step']
            if any(parameters[index]+perturbation > high for index in indices):
                perturbation = -perturbation
            perturbation = max(low-min(parameters[index] for index in indices),
                               min(high-max(parameters[index] for index in indices), perturbation))
            shifted = list(parameters)
            for index in indices:
                shifted[index] += perturbation
            candidate = evaluate(shifted)
            if candidate is None:
                break
            columns.append([(after-before)/perturbation for before, after in zip(best[5], candidate[5])])
        if len(columns) != len(active):
            break
        normal = [[sum(a*b for a, b in zip(columns[i], columns[j]))+
                   (budgets['damping'] if i == j else 0.) for j in range(len(active))]
                  for i in range(len(active))]
        vector = [-sum(a*b for a, b in zip(column, best[5])) for column in columns]
        step = _linear_solve(normal, vector); improved = False
        for attempt in range(budgets['line_search_steps']):
            factor = .5**attempt; trial = list(parameters)
            for indices, delta in zip(active, step):
                change = max(low-min(parameters[index] for index in indices),
                             min(high-max(parameters[index] for index in indices), factor*delta))
                for index in indices:
                    trial[index] += change
            candidate = evaluate(trial)
            if candidate is None:
                break
            if candidate[0] < best[0]-1e-12:
                best, parameters, improved = candidate, trial, True
                break
        if not improved:
            status = 'BUDGET_EXHAUSTED' if evaluations >= budgets['max_evaluations'] else 'STAGNATED'
            break
    if admitted(best):
        status = 'TARGETS_MEASURED'
    variant, profile = best[2:4]
    protected = all(variant['vertices_cm'][i] == geometry['vertices_cm'][i] for i in cage['protected_vertex_ids'])
    if (not protected or variant['faces'] != geometry['faces'] or
            abs(profile['floor_cm']-source_profile['floor_cm']) > 1e-9 or
            abs(profile['stature_cm']-source_profile['stature_cm']) > 1e-9):
        raise StudioError('Body control changed protected regions, topology, stature or foot plane')
    if digest([geometry, options, cage, targets_cm, budgets]) != before:
        raise StudioError('Body control solver mutated source inputs')
    receipt = {'version': 1, 'status': status, 'qualification': 'TORSO_GIRTHS_ONLY',
               'cage_sha256': cage['cache_key'],
               'parameters_log_scale': {name: {'right': parameters[2*i], 'forward': parameters[2*i+1]}
                                        for i, name in enumerate(GIRTH_CONTROLS)},
               'targets_cm': copy.deepcopy(targets_cm), 'tolerance_cm': tolerance_cm,
               'measured_girths_cm': {name: row['girth_cm'] for name, row in profile['landmarks'].items() if 'girth_cm' in row},
               'residuals_cm': dict(zip(names, best[1])), 'iterations': iterations,
               'evaluations': evaluations, 'budgets': copy.deepcopy(budgets), 'history': history,
               'protected_vertices_preserved': protected, 'topology_preserved': True,
               'source_mutated': False, 'source_input_sha256': before,
               'width_depth_policy': cage['width_depth_policy'],
               'source_section_dimensions': source_dimensions, 'variant_section_dimensions': best[4],
               'width_depth_relative_errors': {name: best[4][name]['width_depth_ratio']/source_dimensions[name]['width_depth_ratio']-1.
                                              for name in names},
               'width_depth_relative_tolerance': WIDTH_DEPTH_RELATIVE_TOLERANCE,
               'width_depth_preserved': all(abs(best[4][name]['width_depth_ratio']/source_dimensions[name]['width_depth_ratio']-1.)
                                            <= WIDTH_DEPTH_RELATIVE_TOLERANCE for name in names),
               'protected_boundary_shape_compensation_used': compensate,
               'variant_geometry_sha256': profile['geometry_sha256'], 'variant_profile_cache_key': profile['cache_key'],
               'mensurations_review': 'REQUIRED_BEFORE_FITTING', 'rig_qualification': 'NOT_EXECUTED',
               'simulation': 'NOT_EXECUTED', 'fitting': 'NOT_EXECUTED'}
    receipt['cache_key'] = digest(receipt)
    return {'geometry': variant, 'options': copy.deepcopy(options), 'profile': profile, 'receipt': receipt}
