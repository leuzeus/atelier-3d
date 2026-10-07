"""Code-backed tailoring comparisons; never pattern adoption or fitting admission."""
import copy
import hashlib
import json

from .core import ROOT, StudioError, atomic_json, contract, digest, inside, sha
from .garment_fit import assess_source_fit, assess_compiled_fit, _girth, _region_girth, _finite


def _targets(decision, specification):
    if decision is None:
        return {}
    if (decision.get('approved') is not True or
            decision.get('status') != 'NUMERIC_EASE_DESIGN_INTENT_APPROVED' or
            decision.get('body_ref') != specification['body_ref'] or
            decision.get('classification') != specification['classification'] or
            set(decision.get('component_ids', [])) != set(specification['component_ids'])):
        raise StudioError('Patronage needs the exact body, classification and reviewed design scope')
    result = {}
    required = specification['required_measurements']
    for row in decision.get('targets', []):
        name = row['body_landmark']; ease = row['ease_cm']
        matches = [item for item in required if item['body_landmark'] == name and
                   ('measurement_id' not in row or item['id'] == row['measurement_id'])]
        if len(matches) != 1:
            raise StudioError('Patronage target requires an unambiguous measurement_id for its owner and layer')
        key = matches[0]['id']
        if key in result:
            raise StudioError('Patronage design target is duplicated or outside the required scope')
        values = [ease[key] for key in ('minimum', 'target', 'maximum', 'movement', 'underlayers', 'style')]
        if (not all(_finite(value) for value in values) or
                not ease['minimum'] <= ease['target'] <= ease['maximum'] or
                abs(ease['movement']+ease['underlayers']+ease['style']-ease['target']) > 1e-8 or
                not _finite(row['body_girth_cm']) or row['body_girth_cm'] <= 0 or
                not _finite(row['body_plus_target_cm']) or
                abs(row['body_plus_target_cm']-row['body_girth_cm']-ease['target']) > 1e-7):
            raise StudioError('Patronage numerical design target is inconsistent')
        result[key] = row
    return result


def compare_patronage(compiled, body, specification, decision=None, body_regions=None):
    """Use existing exact section/material-path code, including its declared limits."""
    before = digest([compiled, body, specification, decision, body_regions])
    assessment = assess_source_fit(compiled, body, specification, body_regions)
    targets = _targets(decision, specification)
    checks = {row['id']: row for row in assessment['checks']}; rows = []
    for required in sorted(specification['required_measurements'], key=lambda row: row['id']):
        name = required['body_landmark']; check = checks.get(required['id'])
        measured = _girth(body['landmarks'].get(name, {}))
        if measured is None:
            measured = _region_girth(body, specification, body_regions, name)
        target = targets.get(required['id']); ease = copy.deepcopy(check['ease_intent']) if check else None
        if target:
            if measured is not None and abs(measured-target['body_girth_cm']) > 1e-7:
                raise StudioError('Patronage design body measurement differs from its measured section')
            declared = {key+'_cm': value for key, value in target['ease_cm'].items()}
            if ease and any(abs(ease[key]-declared[key]) > 1e-8 for key in declared):
                raise StudioError('Patronage source fit and reviewed numerical ease disagree')
            if ease is None:
                ease = declared
        path_kind = check['path_kind'] if check else None
        closed = path_kind == 'closed_girth'
        material = check['source_material_length_cm'] if check else None
        desired = measured+ease['target_cm'] if measured is not None and ease else None
        # An open material span must never be subtracted from a body girth.
        delta = desired-material if closed and desired is not None and material is not None else None
        status = (check['status'] if check else 'MEASUREMENT_PATH_REQUIRED')
        if ease is None:
            status = 'EASE_TARGET_REQUIRED'
        if measured is None:
            status = 'BODY_MEASUREMENT_REQUIRED'
        rows.append({**copy.deepcopy(required), 'status': status,
            'body_girth_cm': measured, 'ease_intent': ease,
            'body_plus_target_reference_cm': desired,
            'reference_interpretation': ('CLOSED_NOMINAL_TARGET' if closed else
                'REFERENCE_ENVELOPE_REQUIRES_PATH_AND_CONFIGURATION'),
            'source_material_length_cm': material, 'path_kind': path_kind,
            'measured_source_ease_cm': check['ease_cm'] if check else None,
            'target_minus_source_cm': delta,
            'adjustment_interpretation': ('NOMINAL_TOTAL_LENGTH_DELTA_NOT_PIECE_ALLOCATION' if delta is not None else
                'NOT_COMPUTABLE_WITHOUT_HOMOLOGOUS_CLOSED_PATH'),
            'spatial_coverage': 'NOT_MEASURED', 'fitting': 'NOT_EXECUTED'})
    incomplete = bool(assessment['diagnostics']) or any(row['status'] not in
        ('WITHIN_DECLARED_SOURCE_EASE', 'BELOW_DECLARED_EASE', 'ABOVE_DECLARED_EASE') for row in rows)
    status = ('PATRONAGE_DATA_INCOMPLETE' if incomplete else
              'PATTERN_ADJUSTMENT_PROPOSAL_REQUIRED' if assessment['status'] == 'SOURCE_EASE_MISMATCH' else
              'SOURCE_DIMENSIONS_COMPARED_SPATIAL_FIT_PENDING')
    result = {'version': 1, 'status': status, 'classification': copy.deepcopy(specification['classification']),
        'component_ids': copy.deepcopy(specification['component_ids']), 'rows': rows,
        'fit_preflight': assessment, 'qualification': 'DIAGNOSTIC_ONLY',
        'source_mutated': False, 'body_rescaled': False, 'patterns_modified': False,
        'native_execution': False, 'canonical_database_changed': False,
        'fitting': 'NOT_EXECUTED', 'acceptance': 'NOT_GRANTED',
        'next': ('Prepare missing measurement paths/body sections or numeric intentions; review their correspondence'
                 if incomplete else 'Review measured deltas and prepare a separate bounded pattern variant when needed; verify spatial coverage')}
    result['design_scope_matches'] = decision is None or decision.get('dossier_ref') == specification['dossier_ref']
    if not result['design_scope_matches']:
        # Arithmetic can show a proposed intention, but cannot claim it was
        # reviewed for another dossier, even with identical body/classification.
        result['design_intent_review'] = 'REQUIRES_DESIGN_SCOPE_RECONCILIATION'
        result['canonical_numeric_review_required'] = True
        if result['status'] != 'PATRONAGE_DATA_INCOMPLETE': result['status'] = 'PATRONAGE_REVIEW_REQUIRED'
        result['next'] += '; reconcile the numerical design scope with the exact current dossier'
    if digest([compiled, body, specification, decision, body_regions]) != before:
        raise StudioError('Patronage calculation changed its inputs')
    return result


def _markdown(report):
    def label(value): return str(value).replace('|', '\\|').replace('\n', ' ').replace('\r', ' ')
    def number(value): return '—' if value is None else format(value, '.2f')
    lines = ['# Revue de patronage calculée', '', 'Statut : '+report['status'], '',
        'Revue de l’intention numérique : '+str(report.get('design_intent_review', 'NON_DÉDUITE')), '',
        'Diagnostic dimensionnel uniquement. Aucun patron modifié, aucun fitting ou avis artistique accepté.', '',
        '| Mesure | Corps cm | Corps + aisance cible cm | Matière source cm | Cible − source cm | État |',
        '| --- | ---: | ---: | ---: | ---: | --- |']
    for row in report['rows']:
        lines.append('| '+' | '.join([label(row['id']), number(row['body_girth_cm']),
            number(row['body_plus_target_reference_cm']), number(row['source_material_length_cm']),
            number(row['target_minus_source_cm']), label(row['status'])])+' |')
    lines += ['', 'Une valeur corps + aisance est une référence spatiale tant que le trajet fermé correspondant '
              'n’est pas établi. Un devant ouvert ne produit aucun déficit de tour fermé.', '',
              'Le delta nominal d’un trajet fermé ne répartit pas automatiquement les modifications entre pièces. '
              'Raccords, emmanchures, crans, couches et revue des variantes restent à contrôler.', '',
              'Prochaine action : '+report['next'], '', 'Mesures, preuves et limites : [report.json](report.json).', '']
    return '\n'.join(lines)


def prepare_project_patronage_review(project, dossier_path, specification_path,
                                     fit_profile_path, output_dir, design_decision_path=None,
                                     refresh_body_regions=False):
    """Authenticate existing services, write fresh review files; no new canonical gate."""
    from .body_region_sections import body_region_descriptor, measure_project_body_regions
    from .pattern_ease_variant import _review
    from .production_dossier import compile_project_dossier
    from .garment_fit import _fit_reviews
    if not output_dir.startswith('preparation/') or output_dir == 'preparation/':
        raise StudioError('Patronage review needs a fresh directory under preparation/')
    output = inside(project.root, output_dir, must_exist=False)
    if output.exists():
        raise StudioError('Patronage review output already exists; preserve previous reviews')
    if type(refresh_body_regions) is not bool:
        raise StudioError('Patronage region refresh requires an explicit boolean')
    implementation_sha256 = sha(__file__)
    def code_sources():
        return {path.relative_to(ROOT).as_posix(): sha(path)
                for directory, pattern in (('a3d', '*.py'), ('schemas', '*.json'))
                for path in sorted((ROOT/directory).rglob(pattern))}
    implementation_sources = code_sources()
    refs = []
    def snapshot(path):
        file = inside(project.root, path); raw = file.read_bytes()
        value = json.loads(raw.decode('utf-8-sig'))
        refs.append({'path': path, 'sha256': hashlib.sha256(raw).hexdigest()})
        return value
    snapshot(dossier_path); snapshot(specification_path)
    compiled = compile_project_dossier(project, dossier_path, specification_path)
    specification = snapshot(fit_profile_path)
    contract('garment-fit', specification)
    original_fit_ref = copy.deepcopy(refs[-1]); actual_fit_path = fit_profile_path
    refresh = {'requested': refresh_body_regions, 'status': 'NOT_REQUIRED',
               'source_fit_profile_ref': original_fit_ref, 'human_approval_inherited': False}
    output_created = False
    if refresh_body_regions and specification.get('body_regions'):
        entry = specification['body_regions']
        old_supplement = snapshot(entry['supplement_ref']['path'])
        if refs[-1] != entry['supplement_ref']:
            raise StudioError('Patronage cannot refresh a modified source supplement')
        expected = measure_project_body_regions(project, entry['specification_ref']['path'])
        if old_supplement != expected:
            # This prepares new derived inputs only. The original specification,
            # supplement, body and human decisions remain untouched. The normal
            # source-fit service authenticates the new inputs and review state.
            output.mkdir(parents=True, exist_ok=False); output_created = True
            atomic_json(output/'body-region-supplement.json', expected)
            supplement_ref = {'path': output_dir+'/body-region-supplement.json',
                              'sha256': sha(output/'body-region-supplement.json')}
            specification = copy.deepcopy(specification)
            specification['body_regions']['supplement_ref'] = supplement_ref
            actual_fit_path = output_dir+'/fit-profile.json'
            atomic_json(output/'fit-profile.json', specification)
            refs += [supplement_ref, {'path': actual_fit_path, 'sha256': sha(output/'fit-profile.json')}]
            refresh.update(status='DERIVED_INPUTS_REMEASURED_FOR_REVIEW',
                previous_supplement_ref=copy.deepcopy(entry['supplement_ref']),
                supplement_ref=supplement_ref, fit_profile_ref=copy.deepcopy(refs[-1]),
                old_supplement_digest=digest(old_supplement), new_supplement_digest=digest(expected))
    authenticated = assess_compiled_fit(project, compiled, actual_fit_path)
    current_fit_ref = {'path': actual_fit_path, 'sha256': sha(inside(project.root, actual_fit_path))}
    fit_reviews = _fit_reviews(project, specification, current_fit_ref)
    if authenticated.get('human_reviews', fit_reviews) != fit_reviews:
        raise StudioError('Patronage fitting reviews changed after authentication')
    body = snapshot(specification['body_ref']['path'])
    if refs[-1] != specification['body_ref']:
        raise StudioError('Patronage body file changed')
    regions = None
    if specification.get('body_regions'):
        entry = specification['body_regions']
        regions = body_region_descriptor(project, entry['specification_ref']['path'], entry['supplement_ref'])
    decision = snapshot(design_decision_path) if design_decision_path else None
    decision_ref = copy.deepcopy(refs[-1]) if decision is not None else None
    def review_state():
        if decision is None: return None
        try:
            return {'status': ('REVIEWED_EXACT_NUMERIC_INTENT'
                    if decision.get('dossier_ref') == specification['dossier_ref']
                    else 'REQUIRES_DESIGN_SCOPE_RECONCILIATION'),
                    'decision_dossier_ref': decision.get('dossier_ref'),
                    'current_dossier_ref': specification['dossier_ref'],
                    'reviews': _review(project, decision, decision_ref)}
        except StudioError as error:
            # Diagnostic arithmetic may expose an unrecorded/revoked intention;
            # it cannot revive it or authorize a pattern variant. Preserve the
            # exact relevant gate state so concurrent changes still stop output.
            gates = project.state()['gates']
            return {'status': 'REQUIRES_CANONICAL_HUMAN_DECISION', 'reason': str(error),
                'gates': {name: copy.deepcopy(gates.get(name)) for name in
                          ('ease-design.'+cid for cid in decision['component_ids'])}}
    reviews = review_state()
    def collect(value):
        if isinstance(value, dict):
            if set(value) == {'path', 'sha256'}:
                if value not in refs: refs.append(copy.deepcopy(value))
            else:
                for item in value.values(): collect(item)
        elif isinstance(value, list):
            for item in value: collect(item)
    for value in (compiled, specification, decision, authenticated, regions): collect(value)
    def verify():
        if sha(__file__) != implementation_sha256:
            raise StudioError('Patronage implementation changed during calculation')
        if code_sources() != implementation_sources:
            raise StudioError('Patronage service code or schemas changed during calculation')
        for ref in refs:
            if sha(inside(project.root, ref['path'])) != ref['sha256']:
                raise StudioError('Patronage source or evidence changed: '+ref['path'])
        if review_state() != reviews:
            raise StudioError('Patronage canonical numerical review changed')
        if _fit_reviews(project, specification, current_fit_ref) != fit_reviews:
            raise StudioError('Patronage canonical fitting review changed')
    verify()
    report = compare_patronage(compiled, body, specification, decision, regions)
    for key in ('status', 'checks', 'diagnostics', 'compiled_dossier_sha256', 'body_profile_sha256', 'specification_sha256'):
        if report['fit_preflight'][key] != authenticated[key]:
            raise StudioError('Patronage differs from authenticated source remeasurement')
    report['fit_preflight'] = authenticated
    report['input_refs'] = copy.deepcopy(refs)
    report['design_reviews'] = reviews
    report['design_intent_review'] = reviews['status'] if reviews is not None else authenticated['intent_review']
    if report['design_intent_review'] != 'REVIEWED_EXACT_NUMERIC_INTENT':
        report['canonical_numeric_review_required'] = True
        if report['status'] != 'PATRONAGE_DATA_INCOMPLETE':
            report['status'] = 'PATRONAGE_REVIEW_REQUIRED'
        report['next'] += '; reconcile the exact existing human numerical decision before adopting any pattern variant'
    report['body_region_refresh'] = refresh
    report['code_sha256'] = implementation_sha256
    report['service_code_sources'] = implementation_sources
    report['service_code_sha256'] = digest(implementation_sources)
    verify()
    if not output_created:
        output.mkdir(parents=True, exist_ok=False)
    if (output/'report.json').exists() or (output/'report.md').exists():
        raise StudioError('Patronage result files already exist; preserve them')
    atomic_json(output/'report.json', report)
    (output/'report.md').write_text(_markdown(report), encoding='utf-8', newline='\n')
    verify()
    report['artifacts'] = {name: {'path': output_dir+'/'+name,
        'sha256': sha(output/name)} for name in ('report.json', 'report.md')}
    return report
