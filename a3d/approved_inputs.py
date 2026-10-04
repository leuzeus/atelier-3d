"""Reuse exact approved design inputs without transferring execution results."""
import copy
import shutil
from .core import StudioError, atomic_json, digest, inside, read_json, sha
from .planning import require_board


def import_approved_design(project, source):
    source_state, current = source.state(), project.state()
    if source.root == project.root or current['stage'] != 'INIT':
        raise StudioError('Approved design import requires a distinct new INIT project')
    if digest(source_state['asset']) != digest(current['asset']):
        raise StudioError('A changed asset needs a separate human design review')
    require_board(source, source_state)
    names = ['references', 'construction']+['route.'+cid for cid in current['components']]
    gates = {}
    evidence = {}
    files = {}
    def add(path, identity):
        if path in files and files[path] != identity:
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
    forbidden = ('.a3d/blender/', '.a3d/checkpoints/', '.a3d/runs/', '.a3d/reconstruction/')
    for path, identity in sorted(files.items()):
        if path.startswith(forbidden) or path in ('.a3d/state.sqlite3', '.a3d/project.json'):
            raise StudioError('Design context cannot include candidate or execution state')
        src, dst = inside(source.root, path), inside(project.root, path, False)
        if sha(src) != identity or dst.exists() and sha(dst) != identity:
            raise StudioError('Design file is changed or collides: '+path)
        if not dst.exists():
            dst.parent.mkdir(parents=True, exist_ok=True)
            shutil.copyfile(src, dst)
        if sha(src) != identity or sha(dst) != identity:
            raise StudioError('Design input changed while copying: '+path)
    manifest = {'version': 1, 'status': 'EXACT_APPROVED_DESIGN_IMPORTED',
        'source_project': str(source.root), 'source_revision': source_state['revision'],
        'asset_sha256': digest(current['asset']), 'files': files,
        'human_decision_ids': {name: gate['decision_id'] for name, gate in gates.items()},
        'construction': 'NOT_EXECUTED', 'fitting': 'NOT_EXECUTED', 'animation': 'NOT_EXECUTED',
        'candidate_receipts': 'NOT_TRANSFERRED', 'canonical_database': 'NOT_TRANSFERRED'}
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
    project.transition('ROUTED', evidence_key)
    for cid, package in packages.items(): project.bind_package(cid, package['path'])
    project.transition('PACKAGED', evidence_key)
    require_board(project, project.state())
    project.transition('RECONSTRUCTING', evidence_key)
    return manifest
