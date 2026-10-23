"""Reuse exact approved design inputs without transferring execution results."""
import copy
import shutil
import sqlite3
from contextlib import ExitStack
from .core import StudioError, atomic_json, digest, inside, read_json, sha
from .planning import require_board


def import_approved_design(project, source, *, pattern_variant=None):
    # Discover authenticated parents without mutation, then reserve every
    # canonical source until all target admissions finish. SQLite readers remain
    # usable; a concurrent human/evidence writer must wait until this unit ends.
    composition = None
    roots = {source.root}
    if pattern_variant is not None:
        from .reviewed_pattern_admission import prepare_reviewed_pattern_composition
        composition = prepare_reviewed_pattern_composition(source, pattern_variant)
        template = composition['manifest_template']
        origins = [template['pattern_decision_origin'], *template['base_decision_origins'].values()]
        generation = template['generation_origin']
        from .store import Project
        roots.update(Project(row['project']).root for row in origins)
        roots.update(Project(row['project']).root for origin in origins for row in origin['import_lineage'])
        roots.add(Project(generation['source_project']).root)
        roots.update(Project(row['project']).root for row in generation['import_lineage'])
    if project.root in roots:
        raise StudioError('Approved design import requires a distinct target outside its source lineage')
    from .store import Project
    with ExitStack() as reservations:
        for root in sorted(roots, key=lambda path: str(path).casefold()):
            try:
                reservations.enter_context(Project(root).transaction())
            except sqlite3.OperationalError as error:
                raise StudioError('Canonical design source is busy; retry the import after its writer finishes') from error
        if composition is not None:
            replay = prepare_reviewed_pattern_composition(source, pattern_variant)
            observed, repeated = (copy.deepcopy(item['manifest_template']) for item in (composition, replay))
            observed.pop('source_revision_observed'); repeated.pop('source_revision_observed')
            if digest(observed) != digest(repeated):
                raise StudioError('Reviewed source context changed before its atomic import reservation')
            composition = replay
        return _import_reserved_design(project, source, pattern_variant=pattern_variant, composition=composition)


def _import_reserved_design(project, source, *, pattern_variant, composition):
    source_state, current = source.state(), project.state()
    if source.root == project.root or current['stage'] != 'INIT':
        raise StudioError('Approved design import requires a distinct new INIT project')
    if digest(source_state['asset']) != digest(current['asset']):
        raise StudioError('A changed asset needs a separate human design review')
    if 'reviewed-pattern-composition' in source_state['evidence']:
        raise StudioError('Nested reviewed pattern composition is not supported in V1; preserve the original parent')
    require_board(source, source_state)
    dossier_path = '.a3d/evidence/reviewed-pattern-composition-dossier.json'
    proof_path = '.a3d/evidence/reviewed-pattern-composition.json'
    import_path = '.a3d/evidence/approved-design-import.json'
    if inside(project.root, import_path, False).exists():
        raise StudioError('Design import outputs require a fresh project')
    if pattern_variant is not None:
        if inside(project.root, dossier_path, False).exists() or inside(project.root, proof_path, False).exists():
            raise StudioError('Scoped composition outputs require a fresh project')
    names = ['references', 'construction']+['route.'+cid for cid in current['components']]
    gates = {}
    evidence = {}
    files = {}
    def add(path, identity):
        if any(name.casefold() == path.casefold() and value != identity for name, value in files.items()):
            raise StudioError('Contradictory design source identities')
        files[path] = identity
    for name in names:
        source.require_gate(source_state, name)
        gate = source_state['gates'][name]
        if gate.get('source') != 'human':
            raise StudioError('Only actual human design decisions may be preserved')
        gates[name] = copy.deepcopy(gate)
        for key, record in gate['evidence'].items():
            evidence[key] = copy.deepcopy(source.verify_evidence(source_state, key))
            add(record['path'], record['sha256'])
    board = read_json(inside(source.root, evidence['construction-board']['path']))
    for path, identity in board['dependencies'].items(): add(path, identity)
    for key, row in board['source_references'].items():
        evidence[key] = copy.deepcopy(source.verify_evidence(source_state, key))
        add(evidence[key]['path'], evidence[key]['sha256'])
    packages = {}
    for cid, component in source_state['components'].items():
        packages[cid] = copy.deepcopy(component['package'])
        add(component['package']['path'], component['package']['sha256'])
    for key in ('brief', 'analysis', 'exploded-image-generation'):
        if key in source_state['evidence']:
            evidence[key] = copy.deepcopy(source.verify_evidence(source_state, key))
            add(evidence[key]['path'], evidence[key]['sha256'])
    if composition is not None:
        for name, gate in composition['extra_gates'].items():
            if name in gates and gates[name] != gate:
                raise StudioError('Contradictory scoped pattern decision: '+name)
            gates[name] = copy.deepcopy(gate)
        for key, record in composition['extra_evidence'].items():
            if key in evidence and evidence[key] != record:
                raise StudioError('Contradictory scoped pattern evidence: '+key)
            evidence[key] = copy.deepcopy(record)
        for path, identity in composition['files'].items(): add(path, identity)
        if set(composition['package_overrides'])-set(packages):
            raise StudioError('Scoped composition cannot add a component')
        packages.update(copy.deepcopy(composition['package_overrides']))
    forbidden = ('.a3d/blender/', '.a3d/checkpoints/', '.a3d/runs/', '.a3d/reconstruction/')
    copies = []
    for path, identity in sorted(files.items()):
        folded = path.casefold()
        if folded.startswith(forbidden) or folded.startswith('.a3d/state.sqlite3') or folded == '.a3d/project.json':
            raise StudioError('Design context cannot include candidate or execution state')
        src, dst = inside(source.root, path), inside(project.root, path, False)
        if sha(src) != identity or dst.exists() and sha(dst) != identity:
            raise StudioError('Design file is changed or collides: '+path)
        if folded == import_path or composition is not None and folded in (dossier_path, proof_path):
            raise StudioError('Reviewed source collides with a reserved composition output')
        copies.append((path, identity, src, dst))
    with project.transaction() as db:
        state = project.state(db)
        if state['stage'] != 'INIT' or digest(state['asset']) != digest(current['asset']):
            raise StudioError('New project changed before design copying')
        if db.execute("SELECT 1 FROM events WHERE kind='approved_design_import_started' LIMIT 1").fetchone():
            raise StudioError('Partial design import cannot resume in V1; preserve it and create a fresh project')
        if set(state['gates']) & set(gates) or set(state['evidence']) & set(evidence):
            raise StudioError('Design import would replace an existing decision or evidence')
        project.save(db, state, 'approved_design_import_started',
            {'source_project': str(source.root), 'source_asset_sha256': digest(source_state['asset']),
                'pattern_variant': copy.deepcopy(pattern_variant), 'input_files': copy.deepcopy(files),
                'qualification': 'NONE', 'candidate_receipts': 'NOT_TRANSFERRED'})
    for path, identity, src, dst in copies:
        if not dst.exists():
            dst.parent.mkdir(parents=True, exist_ok=True)
            shutil.copyfile(src, dst)
        if sha(src) != identity or sha(dst) != identity:
            raise StudioError('Design input changed while copying: '+path)
    current_source = source.state()
    if digest(current_source['asset']) != digest(source_state['asset']) or any(
            current_source['gates'].get(name) != gate for name, gate in gates.items()):
        raise StudioError('Reviewed source decisions changed during design import')
    for name in gates: source.require_gate(current_source, name)
    if any(source.verify_evidence(current_source, key) != record for key, record in evidence.items()):
        raise StudioError('Reviewed source evidence changed during design import')
    if any(sha(inside(source.root, path)) != identity or sha(inside(project.root, path)) != identity
            for path, identity in files.items()):
        raise StudioError('Reviewed source files changed during design import')
    manifest = {'version': 1, 'status': 'EXACT_APPROVED_DESIGN_IMPORTED',
        'source_project': str(source.root), 'source_revision': source_state['revision'],
        'asset_sha256': digest(current['asset']), 'files': files,
        'human_decision_ids': {name: gate['decision_id'] for name, gate in gates.items()},
        'construction': 'NOT_EXECUTED', 'fitting': 'NOT_EXECUTED', 'animation': 'NOT_EXECUTED',
        'candidate_receipts': 'NOT_TRANSFERRED', 'canonical_database': 'NOT_TRANSFERRED'}
    if composition is not None:
        dossier_file, proof_file = inside(project.root, dossier_path, False), inside(project.root, proof_path, False)
        if dossier_file.exists() or proof_file.exists():
            raise StudioError('Scoped composition outputs require a fresh project')
        atomic_json(dossier_file, composition['composed_dossier'])
        proof = copy.deepcopy(composition['manifest_template'])
        proof['output'] = {'dossier_ref': {'path': dossier_path, 'sha256': sha(dossier_file)},
            'packages': copy.deepcopy(packages)}
        atomic_json(proof_file, proof)
        manifest['status'] = 'APPROVED_DESIGN_WITH_SCOPED_PATTERN_COMPOSITION_IMPORTED'
        manifest['calculated_source_composition'] = {'path': proof_path, 'sha256': sha(proof_file),
            'origin': 'calculated', 'qualification': 'NONE'}
    path = project.data/'evidence/approved-design-import.json'; atomic_json(path, manifest)
    with project.transaction() as db:
        state = project.state(db)
        if state['stage'] != 'INIT' or digest(state['asset']) != digest(current['asset']):
            raise StudioError('New project changed during design import')
        if set(state['gates']) & set(gates) or set(state['evidence']) & set(evidence):
            raise StudioError('Design import would replace an existing decision or evidence')
        state['gates'].update(gates); state['evidence'].update(evidence)
        state['stage'] = 'ANALYZED'
        project.save(db, state, 'approved_design_context_imported', manifest)
    # Use ordinary canonical admissions for routes, packages and reconstruction.
    for cid, component in source_state['components'].items():
        project.resolve_route(cid, component['route']['selected'])
    evidence_key = 'approved-design-import'
    project.evidence(evidence_key, path.relative_to(project.root).as_posix())
    if composition is not None:
        project.evidence('reviewed-pattern-composition', proof_path)
    project.transition('ROUTED', evidence_key)
    for cid, package in packages.items(): project.bind_package(cid, package['path'])
    project.transition('PACKAGED', evidence_key)
    require_board(project, project.state())
    project.transition('RECONSTRUCTING', evidence_key)
    return manifest
