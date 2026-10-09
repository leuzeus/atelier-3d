"""Bounded observations of guide-cage interpolation, never mesh admission.

Each stage is compared with the same immutable material UV triangles. Cage
triangles may be slivers: their angles describe interpolation conditioning,
not the quality of a future regular REST mesh or a physical Cloth result.
"""
from __future__ import annotations

import math

from . import cloth_metrics
from .core import StudioError, digest, sha


STAGES = ('original_guide', 'role_rigid_seed', 'seam_cohort_mean')
DEGENERATE_WITNESS_LIMIT = 32


def _vector(point, size):
    return (isinstance(point, (list, tuple)) and len(point) == size
            and all(type(x) in (int, float) and math.isfinite(x) for x in point))


def _finite_tree(value):
    if isinstance(value, dict):
        return all(_finite_tree(v) for v in value.values())
    if isinstance(value, (list, tuple)):
        return all(_finite_tree(v) for v in value)
    return not isinstance(value, float) or math.isfinite(value)


def observe_guide_stages(states, coordinates, budget, *, provenance):
    """Observe three complete cage stages within the caller's coupling budget.

    ``states`` binds UV, indexed triangles and original source-face indices.
    Coordinates contain exactly ``STAGES``, with complete per-piece controls.
    Existing reserved controls/triangles are checked, not reserved again. The
    three passes have a fixed multiplier and share the same monotonic deadline.
    No coordinate, UV, topology, budget reservation or admission is changed.
    """
    budget.check()
    if (not isinstance(states, dict) or not 1 <= len(states) <= 16
            or any(not isinstance(pid, str) or not pid for pid in states)
            or not isinstance(coordinates, dict) or set(coordinates) != set(STAGES)
            or not isinstance(provenance, dict)):
        raise StudioError('Guide stage observations require complete explicit cage stages and provenance')
    controls = triangles = 0
    bindings = {}
    for pid, state in sorted(states.items()):
        budget.check()
        if (not isinstance(state, dict) or not isinstance(state.get('uv'), list)
                or not isinstance(state.get('triangles'), list)
                or not isinstance(state.get('triangle_source_faces'), list)
                or len(state['uv']) < 3 or not state['triangles']
                or len(state['triangles']) != len(state['triangle_source_faces'])):
            raise StudioError('Guide stage observations require complete source cage topology: '+pid)
        controls += len(state['uv']); triangles += len(state['triangles'])
        if controls > budget.limits['max_controls'] or triangles > budget.limits['max_triangles']:
            raise StudioError('Guide stage observations exceed the source coupling control or triangle budget')
        for point in state['uv']:
            budget.check()
            if not _vector(point, 2):
                raise StudioError('Guide stage source UV must be finite material coordinates: '+pid)
        for face, source_face in zip(state['triangles'], state['triangle_source_faces'], strict=True):
            budget.check()
            if (not isinstance(face, (list, tuple)) or len(face) != 3
                    or any(type(i) is not int or not 0 <= i < len(state['uv']) for i in face)
                    or len(set(face)) != 3
                    or type(source_face) is not int or source_face < 0):
                raise StudioError('Guide stage source triangle binding is invalid: '+pid)
        bindings[pid] = {key: state[key] for key in ('uv', 'triangles', 'triangle_source_faces')}
    for stage in STAGES:
        budget.check()
        pieces = coordinates[stage]
        if not isinstance(pieces, dict) or set(pieces) != set(states):
            raise StudioError('Guide stage coordinates must cover every source piece: '+stage)
        for pid, points in sorted(pieces.items()):
            budget.check()
            if not isinstance(points, list) or len(points) != len(states[pid]['uv']):
                raise StudioError('Guide stage coordinates must cover every cage control: '+stage+'; '+pid)
            for point in points:
                budget.check()
                if not _vector(point, 3):
                    raise StudioError('Guide stage coordinates must be finite: '+stage+'; '+pid)
    try:
        binding_sha = digest(bindings)
        stage_shas = {}
        for stage in STAGES:
            budget.check()
            stage_shas[stage] = {pid: digest(points) for pid, points in sorted(coordinates[stage].items())}
        provenance_sha = digest(provenance)
    except (TypeError, ValueError, OverflowError) as error:
        raise StudioError('Guide stage provenance must be finite JSON evidence') from error
    budget.check()
    pieces = {}
    for pid, state in sorted(states.items()):
        budget.check()
        stages = {}
        for stage in STAGES:
            budget.check()
            extrema = {}; degeneracies = []; degenerate_count = 0
            source_degenerate_count = placed_degenerate_count = source_singular_count = 0

            def extreme(name, value, record, lower=False):
                if value is None:
                    return
                if name not in extrema or (value < extrema[name]['value'] if lower else value > extrema[name]['value']):
                    extrema[name] = {'value': value, 'piece': pid,
                        'cage_triangle_index': record['cage_triangle_index'],
                        'cage_control_indices': record['cage_control_indices'],
                        'source_face_index': record['source_face_index'], 'source_uv_cm': record['source_uv_cm'],
                        'placed_triangle_cm': record['placed_triangle_cm']}

            for index, face in enumerate(state['triangles']):
                budget.check()
                uv = [state['uv'][i] for i in face]
                placed = [coordinates[stage][pid][i] for i in face]
                try:
                    source = cloth_metrics.triangle_metrics(uv)
                    target = cloth_metrics.triangle_metrics(placed)
                    stretches = cloth_metrics.principal_stretches(uv, placed)
                    strains = [value-1. for value in stretches] if stretches is not None else None
                    record = {'cage_triangle_index': index, 'cage_control_indices': list(face),
                        'source_face_index': state['triangle_source_faces'][index],
                        'source_uv_cm': [list(point) for point in uv],
                        'placed_triangle_cm': [list(point) for point in placed],
                        'source_area_cm2': source['area_cm2'], 'placed_area_cm2': target['area_cm2'],
                        'source_min_angle_degrees': source['min_angle_degrees'],
                        'placed_min_angle_degrees': target['min_angle_degrees'],
                        'principal_stretch': stretches, 'principal_engineering_strain': strains,
                        'source_degenerate': source['area_cm2'] < 1e-8,
                        'placed_degenerate': target['area_cm2'] < 1e-8,
                        'principal_measurement': 'SOURCE_SINGULAR' if stretches is None else 'MEASURED'}
                except (ArithmeticError, ValueError) as error:
                    raise StudioError('Guide stage triangle metric arithmetic is not finite: '+stage+'; '+pid) from error
                if not _finite_tree(record):
                    raise StudioError('Guide stage triangle metric arithmetic is not finite: '+stage+'; '+pid)
                if record['source_degenerate'] or record['placed_degenerate'] or stretches is None:
                    degenerate_count += 1
                    if len(degeneracies) < DEGENERATE_WITNESS_LIMIT:
                        degeneracies.append(record)
                source_degenerate_count += record['source_degenerate']
                placed_degenerate_count += record['placed_degenerate']
                source_singular_count += stretches is None
                extreme('min_source_angle_degrees', source['min_angle_degrees'], record, True)
                extreme('min_placed_angle_degrees', target['min_angle_degrees'], record, True)
                if stretches is not None:
                    extreme('min_principal_stretch', stretches[0], record, True)
                    extreme('max_principal_stretch', stretches[1], record)
                    extreme('min_principal_engineering_strain', strains[0], record, True)
                    extreme('max_principal_engineering_strain', strains[1], record)
            stages[stage] = {'coordinate_sha256': stage_shas[stage][pid], 'extrema': extrema,
                'evaluated_triangle_count': len(state['triangles']),
                'principal_measurement_count': len(state['triangles'])-source_singular_count,
                'source_singular_triangle_count': source_singular_count,
                'source_degenerate_triangle_count': source_degenerate_count,
                'placed_degenerate_triangle_count': placed_degenerate_count,
                'degenerate_triangle_count': degenerate_count, 'degenerate_triangle_witnesses': degeneracies,
                'degenerate_witnesses_truncated': degenerate_count > len(degeneracies),
                'qualification': 'NONE'}
        pieces[pid] = {'controls': len(state['uv']), 'triangles': len(state['triangles']), 'stages': stages}
    budget.check()
    result = {'method': 'IMMUTABLE_SOURCE_UV_GUIDE_CAGE_STAGE_OBSERVATIONS', 'version': 1,
        'scope': 'GUIDE_CAGE_INTERPOLATION_DIAGNOSTIC_ONLY',
        'stage_order': list(STAGES), 'per_piece': pieces,
        'source_uv_triangle_binding_sha256': binding_sha, 'provenance': provenance,
        'provenance_sha256': provenance_sha, 'kernel_code_sha256': sha(cloth_metrics.__file__),
        'observer_code_sha256': sha(__file__), 'metric_version': cloth_metrics.METRIC_VERSION,
        'validator_version': cloth_metrics.VALIDATOR_VERSION,
        'principal_strain_definition': 'ENGINEERING_STRAIN_EQUALS_PRINCIPAL_STRETCH_MINUS_ONE',
        'output_policy': 'EXTREMA_AND_COUNTS_ALL_TRIANGLES_FIRST_32_DEGENERATE_WITNESSES_PER_PIECE_STAGE',
        'degenerate_witness_limit_per_piece_stage': DEGENERATE_WITNESS_LIMIT,
        'degenerate_area_policy': 'SHARED_CLOTH_METRIC_DIAGNOSTIC_AREA_LT_1E_MINUS_8_CM2',
        'source_angle_scope': 'CAGE_CONDITIONING_NOT_PHYSICAL_REST_MESH_ADMISSION',
        'source_mutated': False, 'qualification': 'NONE', 'regular_mesh_assessment': 'NOT_EXECUTED',
        'simulation': 'NOT_EXECUTED', 'fitting': 'NOT_EXECUTED'}
    budget.check()
    return result
