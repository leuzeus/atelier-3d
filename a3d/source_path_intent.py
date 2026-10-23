"""Authenticate reviewed source-body path targets for pattern proposals only.

A nonplanar source boundary remains a length, never a replacement girth.
This reader neither grants a gate nor changes a body, pattern or project.
"""
import copy
import math
import time

from .core import StudioError, digest, ident
from .body_source_paths import (_Reader, _authenticated_target,
                                measure_source_body_paths, validate_specification)


class _IntentBudget:
    """Fixed admission caps, including delegated native-verifier read reserve."""
    def __init__(self):
        self.limits = {'max_read_bytes': 512*1024*1024,
                       'max_evidence_files': 256, 'max_native_receipts': 128,
                       'max_seconds': 60.}
        self.read_bytes = 0
        self.started = self.last = time.monotonic()

    def check(self):
        current = time.monotonic()
        if not math.isfinite(current) or current < self.last or current-self.started > self.limits['max_seconds']:
            raise StudioError('Source path intent time budget exceeded or clock moved backwards')
        self.last = current

    def charge(self, count):
        self.check(); self.read_bytes += count
        if self.read_bytes > self.limits['max_read_bytes']:
            raise StudioError('Source path intent reading budget exceeded')


def _finite(value, label, positive=False):
    if (type(value) not in (int, float) or not math.isfinite(value) or
            (value <= 0 if positive else value < 0)):
        raise StudioError('Source path intent requires a finite '+label)
    return value


def _refs(value, depth=0):
    if depth > 40: raise StudioError('Source path intent source nesting exceeds its budget')
    if isinstance(value, dict):
        if set(value) == {'path', 'sha256'}: yield value
        else:
            for item in value.values(): yield from _refs(item, depth+1)
    elif isinstance(value, list):
        for item in value: yield from _refs(item, depth+1)


def _verify_sources(reader, value):
    for reference in _refs(value): reader.reference(reference, False)


def _gate(project, state, reader, name, required, snapshots, expected=None):
    ident(name); gate = state.get('gates', {}).get(name, {})
    if gate.get('source') != 'human' or gate.get('approved') is not True:
        raise StudioError('Source path intent requires its exact canonical human gate: '+name)
    if not gate.get('decision_id') or not gate.get('source_ref') or not gate.get('statement'):
        raise StudioError('Source path intent human gate lacks its original decision identity')
    if expected is not None and gate != expected:
        raise StudioError('Source path intent comparison differs from its canonical body-path review')
    evidence = gate.get('evidence')
    if not isinstance(evidence, dict) or not evidence or len(evidence) > 256:
        raise StudioError('Source path intent gate evidence is absent or exceeds its budget')
    references = []
    for item in evidence.values():
        if not isinstance(item, dict) or not {'path', 'sha256'}.issubset(item):
            raise StudioError('Source path intent gate evidence lacks an exact reference')
        reference = {key: item[key] for key in ('path', 'sha256')}
        reader.reference(reference, False); references.append(reference)
    if any(reference not in references for reference in required):
        raise StudioError('Source path intent gate did not review these exact source files')
    project.require_gate(state, name); reader.budget.check()
    snapshots[name] = copy.deepcopy(gate)
    return {'gate': name, 'decision_id': gate['decision_id'], 'source_ref': gate['source_ref']}


def _body_report(project, state, reader, comparison, body_ref, snapshots):
    reviewed = comparison.get('body_reference_review', {})
    names = [name for name, gate in state.get('gates', {}).items()
             if gate.get('decision_id') == reviewed.get('decision_id')]
    if len(names) != 1:
        raise StudioError('Source path intent has no unique canonical body-path review')
    candidates = []
    for item in reviewed.get('evidence', {}).values():
        reference = {key: item[key] for key in ('path', 'sha256')}
        if reference['path'].lower().endswith('.json'):
            document = reader.reference(reference)
            if isinstance(document, dict) and document.get('status') == 'BODY_SOURCE_PATHS_MEASURED_FOR_REVIEW':
                candidates.append((reference, document))
    if len(candidates) != 1:
        raise StudioError('Source path intent needs one exact reviewed source-body path report')
    report_ref, report = candidates[0]
    _gate(project, state, reader, names[0], [report_ref], snapshots, expected=reviewed)
    inputs = report.get('input_refs')
    if not isinstance(inputs, list) or not inputs or len(inputs) > 256 or body_ref not in inputs:
        raise StudioError('Source path intent body report belongs to another exact body')
    specifications = []
    for reference in inputs:
        document = reader.reference(reference, reference['path'].lower().endswith('.json'))
        if isinstance(document, dict) and {'version', 'paths', 'budgets'}.issubset(document):
            if digest(document) == report.get('specification_sha256'):
                specifications.append(document)
    if len(specifications) != 1:
        raise StudioError('Source path intent needs its exact source-body path specification')
    specification = validate_specification(specifications[0])
    profile = reader.reference(body_ref)
    receipt, origin, _ = _authenticated_target(project, body_ref, reader)
    artifacts = receipt['artifacts']
    geometry = reader.reference(artifacts['geometry'])
    original = reader.reference(artifacts['source-geometry'])
    adapter = reader.reference(receipt['evidence']['adapter'])
    options = reader.reference(artifacts['options'])
    derivation = reader.reference(artifacts['derivation'])
    stature = derivation.get('stature_derivation') if isinstance(derivation, dict) else None
    if (receipt.get('profile_cache_key') != profile.get('cache_key') or
            any(receipt.get(key) != profile.get(key) for key in ('geometry_sha256', 'pose_sha256')) or
            profile.get('options_sha256') != digest(options) or receipt.get('anatomy_adapter_sha256') != digest(adapter) or
            not isinstance(stature, dict) or stature != receipt.get('stature_derivation') or
            geometry.get('dimension_derivation', {}).get('source_geometry_sha256') != stature.get('source_geometry_sha256') or
            geometry.get('dimension_derivation', {}).get('source_sha256') != original.get('source_sha256') or
            geometry.get('dimension_derivation', {}).get('source_pose_sha256') != original.get('pose_sha256') or
            stature.get('source_geometry_sha256') != digest([original['vertices_cm'], original['faces']])):
        raise StudioError('Source path intent body pose, adapter or derivation differs from its native origin')
    measured = measure_source_body_paths(profile, geometry, original, adapter, specification)
    reader.budget.check()
    if (report.get('identity') != measured['identity'] or report.get('frame') != measured['frame'] or
            report.get('paths') != measured['paths'] or report.get('native_body_origin') != origin):
        raise StudioError('Source path intent report differs from exact native source remeasurement')
    path_id = comparison.get('body_path_id')
    paths = [row for row in measured['paths'] if row['id'] == path_id]
    if (len(paths) != 1 or paths[0].get('closed') is not True or
            paths[0].get('measurement_kind') != 'SOURCE_REGION_BOUNDARY_LENGTH' or
            paths[0]['length_cm'] != comparison.get('body_reference_length_cm')):
        raise StudioError('Source path intent comparison does not measure this exact closed source boundary')
    if report_ref not in comparison.get('input_refs', []) or body_ref not in comparison.get('input_refs', []):
        raise StudioError('Source path intent comparison lacks its exact body and report references')
    return report_ref


def _material(compiled, target, comparison):
    from .garment_fit import _path
    from .garment_measurements import _assembled_row_topology, _collar_neckline_row
    reference = target.get('material_reference')
    required = {'domain', 'component_id', 'piece', 'source_geometry_sha256', 'source_v_cm', 'segments'}
    optional = {'source_material_length_cm', 'topology', 'attachment'}
    if (not isinstance(reference, dict) or not required.issubset(reference) or
            set(reference)-required-optional or reference['domain'] != 'PERMANENT_ENDPOINT_CYCLE'):
        raise StudioError('Source path intent requires an explicit permanent source material cycle')
    cid, pid = reference['component_id'], reference['piece']; ident(cid); ident(pid)
    row = compiled['textiles'].get(pid)
    if (row is None or row['component_id'] != cid or row['semantics']['role'] != 'collar' or
            row['semantics'].get('longitudinal_uv_axis') != 'u' or
            digest(row['source_geometry']) != reference['source_geometry_sha256']):
        raise StudioError('Source path intent material reference belongs to another owned source piece')
    if type(reference['source_v_cm']) not in (int, float) or not math.isfinite(reference['source_v_cm']):
        raise StudioError('Source path intent needs a finite declared material row V')
    segments = reference['segments']
    if not isinstance(segments, list) or len(segments) != 1 or segments[0].get('piece') != pid:
        raise StudioError('Source path intent V1 requires one exact owned source-band row')
    if set(segments[0]) != {'piece', 'from', 'to'}:
        raise StudioError('Source path intent V1 requires exact named-edge endpoint selectors')
    measurement = {'component_id': cid, 'layer': row['semantics']['layer'],
                   'path_kind': 'open_material_span', 'segments': segments,
                   'joins': [], 'engaged_links': [], 'takeup': []}
    length, spans = _path(compiled, measurement, [cid])
    ends = [spans[0]['from_uv_cm'], spans[0]['to_uv_cm']]
    if any(point[1] != reference['source_v_cm'] for point in ends):
        raise StudioError('Source path intent selectors do not lie on their declared exact material row')
    topology = _assembled_row_topology(compiled, segments[0])
    attachment = _collar_neckline_row(compiled, pid, reference['source_v_cm'], ends)
    if (topology.get('status') != 'CLOSED_PERMANENT_ENDPOINT_CYCLE' or
            topology != comparison.get('assembled_row_topology') or
            attachment != comparison.get('source_neckline_attachment') or
            length != comparison.get('source_material_length_cm') or
            topology.get('component_id') != cid or
            any(link.get('component_id') != cid for link in attachment['permanent_source_attachments'])):
        raise StudioError('Source path intent differs from the actual full attached permanent source cycle')
    for key, actual in (('source_material_length_cm', length), ('topology', topology), ('attachment', attachment)):
        if key in reference and reference[key] != actual:
            raise StudioError('Source path intent additional material proof differs from exact remeasurement')
    # Identity uses the actual row and source corners, independently of optional
    # proof duplication, JSON int/float encoding or the direction of traversal.
    # No geometric proximity or a new rounding tolerance is used.
    endpoints = sorted((item['piece'], item['source_vertex_id']) for item in topology['endpoints'])
    semantic = {'component_id': cid, 'piece': pid,
                'source_geometry_sha256': digest(row['source_geometry']),
                'source_v_cm': 0.0 if reference['source_v_cm'] == 0 else float(reference['source_v_cm']),
                'source_vertex_endpoints': [list(item) for item in endpoints]}
    return cid, semantic


def review_source_path_intent(project, decision, decision_ref):
    """Return canonical human review identities; admission is proposal-only.

    ``source_path_ref`` names a reviewed comparison. ``material_reference``
    names a V1 collar band row with exact source-corner selectors; its UV-open
    span and permanent endpoint equivalence are independently remeasured.
    A production specification reference permits exact package recompilation.
    Fixed caps: 32 targets, 256 files, 512 MiB reads/reserves, 60 seconds.
    """
    try:
        return _review_source_path_intent(project, decision, decision_ref)
    except StudioError:
        raise
    except (KeyError, TypeError, IndexError, ValueError, RecursionError) as error:
        raise StudioError('Source path intent has an invalid or incomplete explicit contract') from error


def _review_source_path_intent(project, decision, decision_ref):
    before = digest(decision); reader = _Reader(project, _IntentBudget())
    if reader.reference(decision_ref) != decision:
        raise StudioError('Source path intent decision differs from its persisted exact file')
    if (decision.get('status') != 'SOURCE_PATH_DESIGN_INTENT_APPROVED' or decision.get('approved') is not True or
            'assembled_source_path_design_targets' not in decision.get('approved_scope', [])):
        raise StudioError('Source path intent lacks its explicit approved pattern-design scope')
    components = decision.get('component_ids'); targets = decision.get('targets')
    if (not isinstance(components, list) or not 1 <= len(components) <= 32 or len(set(components)) != len(components) or
            not isinstance(targets, list) or not 1 <= len(targets) <= 32):
        raise StudioError('Source path intent components or targets are absent or exceed their budget')
    for cid in components: ident(cid)
    for key in ('dossier_ref', 'body_ref', 'production_specification_ref'): reader.reference(decision[key], False)
    spec = reader.reference(decision['production_specification_ref'])
    if spec.get('source_ref') != decision['dossier_ref'] or spec.get('body_ref') != decision['body_ref']:
        raise StudioError('Source path intent production compilation belongs to another body or source dossier')
    _verify_sources(reader, spec)
    from .production_dossier import compile_project_dossier
    compiled = compile_project_dossier(project, decision['dossier_ref']['path'], decision['production_specification_ref']['path'])
    reader.budget.check()
    state = project.state(); reviews = []; seen = set(); covered = set(); gate_snapshots = {}
    for target in targets:
        reader.budget.check()
        comparison_ref = target['source_path_ref']; comparison = reader.reference(comparison_ref)
        intent_ref = target['human_intent_ref']; intent = reader.reference(intent_ref)
        _verify_sources(reader, comparison.get('input_refs', []))
        contexts = [reader.reference(reference) for reference in comparison.get('input_refs', [])
                    if reference['path'].lower().endswith('.json')]
        if not any(isinstance(context, dict) and context.get('dossier_ref') == decision['dossier_ref'] and
                   context.get('body_ref') == decision['body_ref'] for context in contexts):
            raise StudioError('Source path intent comparison lacks its exact source dossier and body context')
        if (comparison.get('status') != 'COLLAR_BODY_REFERENCE_COMPARISON_PREPARED' or
                comparison.get('scope') != 'HOMOLOGY_AND_NEW_METRIC_INTENT_PROPOSAL_ONLY' or
                comparison.get('body_changed') is not False or comparison.get('patterns_changed') is not False or
                comparison.get('admissible_for_fit') is not False or comparison.get('qualification') != 'NONE'):
            raise StudioError('Source path intent requires an unchanged review-only source comparison')
        body_report_ref = _body_report(project, state, reader, comparison, decision['body_ref'], gate_snapshots)
        cid, semantic = _material(compiled, target, comparison)
        if cid not in components: raise StudioError('Source path intent target belongs to an undeclared component')
        covered.add(cid)
        identity = digest([decision['body_ref'], comparison['body_path_id'], semantic])
        if identity in seen: raise StudioError('Source path intent cannot count the same source path twice')
        seen.add(identity)
        body = _finite(target['body_reference_length_cm'], 'source body length', True)
        ease = _finite(target['ease_total_cm'], 'total source path ease')
        total = _finite(target['target_material_length_cm'], 'target material length', True)
        if (intent.get('scope') != 'VARIANT_PREPARATION_TARGET_ONLY' or
                intent.get('body_reference') != comparison_ref or intent.get('body_path_id') != comparison['body_path_id'] or
                intent.get('body_reference_length_cm') != body or body != comparison['body_reference_length_cm'] or
                intent.get('ease_cm') != ease or intent.get('target_material_length_cm') != total or
                total != math.fsum((body, ease)) or intent.get('source_material_length_cm') != comparison['source_material_length_cm'] or
                intent.get('ease_decomposition') != 'NOT_DECLARED' or intent.get('body_changed') is not False or
                intent.get('pattern_adoption') != 'NOT_GRANTED' or intent.get('fitting') != 'NOT_EXECUTED'):
            raise StudioError('Source path intent numeric target differs from the actual reviewed length and total ease')
        gate_name = target['human_review_gate']
        gate = state.get('gates', {}).get(gate_name, {})
        if (gate.get('source_ref') != decision.get('source_ref') or gate.get('statement') != decision.get('statement') or
                intent.get('user_statement') != decision.get('statement')):
            raise StudioError('Source path intent must retain the actual human statement and message reference')
        review = _gate(project, state, reader, gate_name, [intent_ref, comparison_ref, body_report_ref], gate_snapshots)
        if review not in reviews: reviews.append(review)
    if covered != set(components): raise StudioError('Every source path intent component needs its own exact target')
    reader.preserve(); reader.budget.check()
    if digest(decision) != before: raise StudioError('Source path intent verification mutated its decision')
    # Reads and native remeasurement can outlive a concurrent human revocation.
    # Recheck precisely the used body and numeric gates, not unrelated gates.
    current = project.state()
    for name, original in sorted(gate_snapshots.items()):
        reader.budget.check()
        if current.get('gates', {}).get(name) != original:
            raise StudioError('Source path intent canonical human review changed during verification: '+name)
        project.require_gate(current, name)
    reader.budget.check()
    return reviews
