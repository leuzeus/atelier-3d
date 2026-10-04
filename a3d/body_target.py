"""Prepare measured body copies from explicit targets, never garment admission."""
import copy

from .anatomy_profile import frame, profile_mesh
from .body_dimensions import variant_by_stature
from .body_source import selection
from .catalog_anatomy import region_guides
from .core import StudioError, contract, digest, inside, read_json, sha
from .shoulder_surface import measured_surface_shoulders
from .head_surface import head_face_ids, measured_head_surface

STATURE_TARGET_TOLERANCES = {'stature_cm': .0001, 'floor_cm': .0001, 'roundtrip_cm': .0001, 'girth_cm': .1}
STATURE_TARGET_BUDGETS = {'max_iterations': 15, 'max_evaluations': 150, 'finite_difference_step': .001,
                         'damping': .001, 'line_search_steps': 8, 'min_scale': .85, 'max_scale': 1.15}


def stature_target(selected, orientation, stature_cm, provenance):
    """Construct a height-only declaration with named V1 numerical policies.

    Numeric stature and provenance must come from the caller. Other mensurations
    are omitted and are measured after preparation. The default frame origin is
    the world coordinate origin of the catalog's explicitly baked source mesh.
    """
    if isinstance(provenance, str):
        provenance = {'source_ref': provenance, 'measurements_status': 'DECLARED_FOR_REVIEW'}
    if not isinstance(selected, dict) or not isinstance(orientation, dict):
        raise StudioError('Stature target requires an exact selected source and declared orientation')
    try:
        target = {'version': 1, 'selection_sha256': selected['selection']['sha256'],
                  'anatomy_adapter': copy.deepcopy(selected['anatomy_adapter']),
                  'orientation': dict(copy.deepcopy(orientation), origin_cm=orientation.get('origin_cm', [0., 0., 0.])),
                  'target_stature_cm': stature_cm, 'provenance': copy.deepcopy(provenance),
                  'tolerances': copy.deepcopy(STATURE_TARGET_TOLERANCES),
                  'budgets': copy.deepcopy(STATURE_TARGET_BUDGETS)}
    except KeyError as error:
        raise StudioError('Stature target requires exact selection and adapter identities') from error
    return validate_target(target)


def validate_target(target):
    contract('body-target', target)
    frame(target['orientation'])
    if target['budgets']['min_scale'] >= target['budgets']['max_scale']:
        raise StudioError('Body target control scale domain is empty')
    return target


def target_descriptor(project, selection_path, target_path):
    """Read a source-bound target without writing project or Blender state."""
    data, source, selection_sha = selection(project, selection_path)
    path = inside(project.root, target_path)
    target = validate_target(read_json(path))
    if target['selection_sha256'] != selection_sha:
        raise StudioError('Body target selection identity changed')
    adapter_ref = target['anatomy_adapter']
    adapter_path = inside(project.root, adapter_ref['path'])
    if sha(adapter_path) != adapter_ref['sha256']:
        raise StudioError('Body target anatomical adapter identity changed')
    adapter = read_json(adapter_path)
    if adapter.get('source_ref') != {'path': data['source_blend'], 'sha256': data['source_sha256']}:
        raise StudioError('Body target adapter refers to a different selected source')
    return {'selection': data, 'source': source, 'target': target, 'adapter': adapter,
            'evidence': {'selection': {'path': selection_path, 'sha256': selection_sha},
                         'target': {'path': target_path, 'sha256': sha(path)},
                         'adapter': copy.deepcopy(adapter_ref)}}


def prepare_target_geometry(geometry, triangles, target, adapter):
    """Measure source and target with native triangulation and source adapter.

    Returned arrays are independent of the source. Anatomical joint regions are
    admitted only against the original mesh, before uniform stature scaling.
    Face labels retain their original identities without rebinding the adapter.
    """
    validate_target(target)
    original = digest([geometry, triangles, target, adapter])
    guides = region_guides(geometry, adapter)
    source = copy.deepcopy(geometry)
    source['rig_landmarks'] = copy.deepcopy(guides['rig_landmarks'])
    options = dict(copy.deepcopy(target['orientation']), torso_faces=guides['torso_faces'],
                   segmentation_source_ref=guides['segmentation_source_ref'],
                   section_count=target.get('section_count', 80))
    required = ('shoulder.left', 'shoulder.right')
    if any(name not in guides['rig_landmarks'] for name in required):
        raise StudioError('Body target preparation needs explicit source shoulder joint regions')
    head_faces = head_face_ids(source, adapter)
    source_profile = measured_head_surface(profile_mesh(source, options), source, head_faces, adapter['source_ref'])
    source_profile = measured_surface_shoulders(source_profile, source, triangles)
    result = variant_by_stature(source, options, target['target_stature_cm'])
    # These are immutable face-region identities, not a metric-valid adapter.
    result['geometry']['face_sets'] = copy.deepcopy(geometry['face_sets'])
    controls = None
    if target.get('target_girths_cm'):
        from .body_controls import cage_from_segmentation, solve_girths
        cage = cage_from_segmentation(result['geometry'], result['options'])
        controls = solve_girths(result['geometry'], result['options'], cage,
                               target['target_girths_cm'], target['tolerances']['girth_cm'], target['budgets'])
        result['geometry'], result['options'] = controls['geometry'], controls['options']
    profile = measured_head_surface(profile_mesh(result['geometry'], result['options']),
                                    result['geometry'], head_faces, adapter['source_ref'])
    profile = measured_surface_shoulders(profile, result['geometry'], triangles)
    if abs(profile['stature_cm']-target['target_stature_cm']) > target['tolerances']['stature_cm']:
        raise StudioError('Prepared body did not attain the declared target stature tolerance')
    if abs(profile['floor_cm']-source_profile['floor_cm']) > target['tolerances']['floor_cm']:
        raise StudioError('Prepared body did not preserve the source foot plane')
    if digest([geometry, triangles, target, adapter]) != original:
        raise StudioError('Body target preparation changed its source inputs')
    status = 'BODY_TARGET_MEASURED'
    if controls and controls['receipt']['status'] != 'TARGETS_MEASURED':
        status = 'BODY_TARGET_INCOMPLETE'
    receipt = {'version': 1, 'status': status,
               'qualification': 'MEASURED_BODY_COPY_REQUIRES_REVIEW',
               'source_input_sha256': original, 'target_sha256': digest(target),
               'source_profile_cache_key': source_profile['cache_key'],
               'profile_cache_key': profile['cache_key'], 'source_sha256': geometry['source_sha256'],
               'source_pose_sha256': geometry['pose_sha256'], 'variant_pose_sha256': result['geometry']['pose_sha256'],
               'variant_geometry_sha256': profile['geometry_sha256'],
               'source_stature_cm': source_profile['stature_cm'],
               'target_stature_cm': target['target_stature_cm'], 'measured_stature_cm': profile['stature_cm'],
               'source_floor_cm': source_profile['floor_cm'], 'measured_floor_cm': profile['floor_cm'],
               'measured_girths_cm': {name: row['girth_cm'] for name, row in profile['landmarks'].items() if 'girth_cm' in row},
               'target_girths_cm': copy.deepcopy(target.get('target_girths_cm', {})),
               'stature_derivation': result['receipt'],
               'regional_controls': controls['receipt'] if controls else {'status': 'NOT_REQUESTED'},
               'anatomy_adapter_sha256': digest(adapter), 'adapter_rebound_to_variant': False,
               'source_face_ids_preserved': True, 'topology_preserved': True, 'source_mutated': False,
               'target_provenance': copy.deepcopy(target['provenance']),
               'mensurations_review': 'REQUIRED_BEFORE_FITTING',
               'missing_landmarks': copy.deepcopy(profile['missing_landmarks']),
               'pattern_compatibility': 'NOT_QUALIFIED', 'rig_qualification': 'NOT_EXECUTED',
               'collision_envelope': 'NOT_CREATED', 'simulation': 'NOT_EXECUTED', 'fitting': 'NOT_EXECUTED',
               'artistic_review': 'NOT_EXECUTED',
               'prior_evidence_invalidated': result['receipt']['prior_evidence_invalidated']}
    receipt['cache_key'] = digest(receipt)
    return {'geometry': result['geometry'], 'triangles': copy.deepcopy(triangles),
            'options': result['options'], 'profile': profile, 'source_profile': source_profile, 'receipt': receipt}


def measurement_compatibility(profile, capacities):
    """Check explicitly supplied capacities; this cannot admit garment fitting.

    Each capacity needs a sourced homologous body measurement name and explicit
    min/max accepted measurements. No ease or hidden garment dimensions inferred.
    """
    if not isinstance(capacities, list):
        raise StudioError('Body compatibility capacities must be explicitly listed')
    if any(not isinstance(item, dict) or not isinstance(item.get('measurement'), str) for item in capacities):
        raise StudioError('Pattern capacities need declared measurement names')
    if len({item['measurement'] for item in capacities}) != len(capacities):
        raise StudioError('Pattern capacities cannot duplicate a measurement')
    rows = []
    for capacity in sorted(capacities, key=lambda item: item['measurement']):
        if (not isinstance(capacity, dict) or set(capacity) != {'measurement', 'minimum_cm', 'maximum_cm', 'source_ref'}
                or not capacity.get('source_ref')):
            raise StudioError('Pattern capacity needs exact measurement limits and source provenance')
        name = capacity['measurement']
        import math
        low, high = capacity['minimum_cm'], capacity['maximum_cm']
        if any(type(value) not in (int, float) or not math.isfinite(value) for value in (low, high)) or not 0 <= low <= high:
            raise StudioError('Pattern capacity measurement domain is invalid')
        measured = (profile['stature_cm'] if name == 'stature' else
                    profile['landmarks'].get(name, {}).get('girth_cm'))
        rows.append(dict(capacity, measured_cm=measured,
                         status='MISSING_BODY_MEASUREMENT' if measured is None else
                         'WITHIN_DECLARED_CAPACITY' if low <= measured <= high else 'OUTSIDE_DECLARED_CAPACITY'))
    return {'status': 'CAPACITIES_CHECKED' if capacities else 'NO_CAPACITIES_PROVIDED',
            'profile_cache_key': profile['cache_key'], 'checks': rows,
            'fitting': 'NOT_EXECUTED', 'dressing': 'NOT_EXECUTED', 'acceptance': 'NOT_GRANTED'}
