"""Prepare scoped, reviewed design data without replacing production inputs.

An epoch describes calculated source data. It is neither a package admission,
an execution permission nor a transfer of any ancestor's physical results.
Historical composition producers intentionally remain unchanged.
"""
import copy
import hashlib
import json
import math
from pathlib import Path
import time
import zipfile

from .core import StudioError, atomic_json, canonical, contract, digest, ident, inside, relative, sha
from .pattern_variant_composition import compose_pattern_variant_dossier, verify_pattern_variant_scope
from .reviewed_pattern_admission import _human, _parse, _reference, _ref, _state

ROLES = {'proposal', 'review', 'candidate_dossier', 'variant_package'}
MAX_SECONDS = 120.0
MAX_INPUT_BYTES = 128 * 1024 * 1024
MAX_FILE_BYTES = 64 * 1024 * 1024
MAX_OUTPUT_BYTES = 16 * 1024 * 1024
MAX_REFERENCES = 512
MAX_PARENT_PROJECTS = 8
PACKAGE_SUFFIXES = {'.garmentpkg', '.partpkg', '.3dpkg'}


def _codes():
    directory = Path(__file__).resolve().parent
    names = ('reviewed_pattern_revisions.py', 'pattern_ease_variant.py',
             'production_dossier.py', 'board_contract.py', 'sewing.py',
             'pattern_variant_composition.py', 'reviewed_pattern_admission.py',
             'core.py', 'planning.py', 'packages.py', 'garment_guides.py',
             'garment_fit.py', 'source_path_intent.py')
    result = {'a3d/'+name: sha(directory/name) for name in names}
    for name in ('pattern-ease-variant', 'production-dossier', 'construction', 'garment', 'package'):
        file = directory.parent/'schemas'/(name+'.schema.json')
        if file.exists(): result['schemas/'+file.name] = sha(file)
    return result


def _preflight_dependencies(project, state, gate_name, roles, check):
    """Bound expanded packages before any historical admission validator.

    Only current design-admission dependencies and their authenticated-parent
    candidates are inspected. Unrelated run, scene and checkpoint evidence is
    outside this data preparation. Authentication still follows this inventory.
    """
    from .store import Project
    projects = {}; pending = []; files = {}; aliases = {}; expanded = 0
    parsed_files = set()
    observed_refs = set()
    def reference(owner, value, follow=False):
        value = _reference(value); token = (str(owner.root), value['path'], value['sha256'], follow)
        if token not in observed_refs:
            if len(observed_refs) >= MAX_REFERENCES:
                raise StudioError('Reviewed source revision preflight reference budget exhausted')
            observed_refs.add(token); pending.append((owner, value, follow))
    def visit_project(owner, current=None, pattern_gate=None, decision_key=None):
        check(); key = str(owner.root).casefold()
        if key not in projects:
            if len(projects) >= MAX_PARENT_PROJECTS:
                raise StudioError('Reviewed source revision parent project budget exhausted')
            current = current if current is not None else _state(owner)
            projects[key] = (owner, current)
            for component in current['components'].values():
                if component.get('package'): reference(owner, component['package'])
            for name in ('construction-board', 'reviewed-pattern-composition', 'approved-design-import'):
                if name in current['evidence']: reference(owner, current['evidence'][name], True)
            names = ['references', 'construction']+['route.'+cid for cid in current['components']]
            for name in names:
                for row in current['gates'].get(name, {}).get('evidence', {}).values(): reference(owner, row)
        owner, current = projects[key]
        if pattern_gate:
            for row in current['gates'].get(pattern_gate, {}).get('evidence', {}).values(): reference(owner, row)
        if decision_key and decision_key in current['evidence']:
            reference(owner, current['evidence'][decision_key], True)
    visit_project(project, state, gate_name)
    for evidence_key in roles.values():
        if evidence_key not in state['evidence']:
            raise StudioError('Reviewed source revision preflight role evidence is missing')
        reference(project, state['evidence'][evidence_key], evidence_key == roles.get('proposal'))
    while pending:
        # Inventory already known archives first, before parsing large metadata
        # that would otherwise consume the allowance and hide expansion errors.
        archive_indices = [i for i, (_, ref, _) in enumerate(pending) if Path(ref['path']).suffix.lower() in PACKAGE_SUFFIXES]
        check(); owner, ref, follow = pending.pop(archive_indices[-1] if archive_indices else -1)
        file = inside(owner.root, ref['path'])
        raw_path = owner.root.joinpath(*ref['path'].split('/'))
        for part in (raw_path, *raw_path.parents):
            if part == owner.root: break
            metadata = part.lstat()
            if part.is_symlink() or getattr(metadata, 'st_file_attributes', 0) & 0x400:
                raise StudioError('Reviewed source revision preflight refuses symlink/junction dependencies')
        key = str(file).casefold()
        if key in aliases and aliases[key] != str(raw_path):
            raise StudioError('Reviewed source revision preflight has a Windows case alias')
        aliases[key] = str(raw_path)
        if key in files:
            if files[key]['sha256'] != ref['sha256']:
                raise StudioError('Reviewed source revision preflight binds contradictory identities')
            if not follow or key in parsed_files: continue
            # A file may first be hashed as opaque reviewed evidence, then be
            # encountered as an actual metadata input. Count it only once.
            size = files[key]['file_bytes']; identity = files[key]['sha256']
            row = files[key]
        else:
            size = file.stat().st_size
            if size > MAX_FILE_BYTES:
                raise StudioError('Reviewed source revision preflight file budget exhausted')
            identity = sha(file); check()
            if identity != ref['sha256']:
                raise StudioError('Reviewed source revision preflight input changed')
            row = {'path': str(file), 'sha256': identity, 'file_bytes': size}
        if key not in files and file.suffix.lower() in PACKAGE_SUFFIXES:
            with zipfile.ZipFile(file) as archive:
                infos = archive.infolist()
                if len(infos) > MAX_REFERENCES:
                    raise StudioError('Reviewed source revision preflight archive member budget exhausted')
                names = set(); amount = 0
                for info in infos:
                    check(); relative(info.filename)
                    if info.filename.casefold() in names or info.file_size > MAX_FILE_BYTES:
                        raise StudioError('Reviewed source revision expanded archive member budget/alias violated')
                    names.add(info.filename.casefold()); amount += info.file_size
                    if expanded+max(size, amount) > MAX_INPUT_BYTES:
                        raise StudioError('Reviewed source revision expanded archive total budget exhausted')
            row.update(expanded_bytes=amount, kind='PACKAGE_INVENTORY_ONLY')
            expanded += max(size, amount)
        elif key not in files:
            expanded += size; row.update(expanded_bytes=size, kind='ORDINARY_FILE')
        if expanded > MAX_INPUT_BYTES:
            raise StudioError('Reviewed source revision preflight total input budget exhausted')
        files[key] = row
        if not follow or file.suffix.lower() != '.json': continue
        parsed_files.add(key)
        raw = file.read_bytes(); check()
        if len(raw) != size or hashlib.sha256(raw).hexdigest() != identity:
            raise StudioError('Reviewed source revision preflight metadata changed')
        value = _parse(raw)
        if not isinstance(value, dict): continue
        for name in ('dependencies', 'input_files', 'files'):
            for path, identity in value.get(name, {}).items() if isinstance(value.get(name), dict) else ():
                reference(owner, {'path': path, 'sha256': identity})
        for item in value.get('input_refs', []): reference(owner, item, True)
        historical_decision = value.get('status') in ('SCOPED_PATTERN_VARIANT_APPROVED', 'TWO_SLEEVE_PATTERN_VARIANT_APPROVED')
        for name in ('proposal_ref', 'review_ref', 'candidate_dossier_ref', 'variant_package_ref',
                     'numeric_design_decision_ref', 'body_ref', 'original_dossier_ref',
                     'design_decision_ref', 'dossier_ref', 'pipeline_proposal', 'source_ref',
                     'specification_source_ref', 'production_specification_ref', 'base_board_ref', 'decision_ref'):
            item = value.get(name)
            if isinstance(item, dict) and {'path', 'sha256'} <= item.keys(): reference(owner, item, not historical_decision)
        # Proposal package maps are generated outputs. Only the explicitly
        # reviewed affected archive is consumed; untouched output clones may
        # legitimately never have been copied into an approved-input import.
        for package in value.get('packages', {}).values() if isinstance(value.get('packages'), dict) and 'proposal_sha256' not in value else ():
            if isinstance(package, dict) and {'path', 'sha256'} <= package.keys(): reference(owner, package)
        if isinstance(value.get('packages'), list):
            # The production compiler verifies every exact reference nested in
            # its specification, including package list entries and layers.
            stack = [value]
            while stack:
                check(); child = stack.pop()
                if isinstance(child, dict):
                    if set(child) == {'path', 'sha256'}: reference(owner, child)
                    else: stack.extend(child.values())
                elif isinstance(child, list): stack.extend(child)
        output = value.get('output', {})
        if isinstance(output, dict):
            if isinstance(output.get('dossier_ref'), dict): reference(owner, output['dossier_ref'])
            for package in output.get('packages', {}).values() if isinstance(output.get('packages'), dict) else ():
                reference(owner, package)
        origins = [value.get('origin', {}), value.get('generation_origin', {})]
        source_parent = value.get('source_project')
        if isinstance(source_parent, str): visit_project(Project(source_parent))
        for origin in origins:
            if not isinstance(origin, dict): continue
            source_parent = origin.get('source_project')
            if isinstance(source_parent, str):
                request = value.get('request', {})
                visit_project(Project(source_parent), pattern_gate=request.get('gate_name') if isinstance(request, dict) else None,
                              decision_key=request.get('decision_evidence_key') if isinstance(request, dict) else None)
            for ancestor in origin.get('import_lineage', []):
                visit_project(Project(ancestor['project']))
    check()
    return {'scope': 'CURRENT_DESIGN_ADMISSION_LINEAGE_FILES_AND_EXPANDED_PACKAGES',
            'expanded_input_bytes': expanded, 'parent_project_count': len(projects),
            'max_parent_projects': MAX_PARENT_PROJECTS, 'files': sorted(files.values(), key=lambda row: row['path'])}


def calculate_reviewed_pattern_revision(project, gate_name, roles, baseline=None):
    """Authenticate and replay design data without writing outputs.

    Role values are evidence keys in the actual direct human decision. This
    bounded V1 preparation supports unchanged topology and an existing grading
    policy; its retained parameters are replayed, never optimized again.
    """
    from .planning import require_board, package_records, _validate_dossier_structure
    from .packages import inspect_package
    from .production_dossier import compile_project_dossier
    from .pattern_ease_variant import (_parameters, _candidate, _material_notches,
                                      _seams, _candidate_geometry_domain, _review)

    started = time.monotonic()
    def check():
        if time.monotonic()-started > MAX_SECONDS:
            raise StudioError('Reviewed source revision preparation exhausted its time budget')
    ident(gate_name)
    if not gate_name.startswith('pattern-variant.'):
        raise StudioError('Reviewed source revision requires a scoped pattern-variant gate')
    if (not isinstance(roles, dict) or set(roles) != ROLES or
            any(not isinstance(value, str) for value in roles.values()) or
            len(set(roles.values())) != len(ROLES)):
        raise StudioError('Reviewed source revision requires four distinct exact evidence roles')
    for value in roles.values(): ident(value)
    before_codes = _codes()
    state = _state(project)
    try:
        preflight = _preflight_dependencies(project, state, gate_name, roles, check)
    except OSError as error:
        raise StudioError('Reviewed source revision preflight dependency is missing or unreadable') from error
    if baseline is None:
        board = require_board(project, state)
        packages = package_records(project, state)
    else:
        # Internal replay context supplied by the admission verifier after
        # authenticating an archived parent. It grants no admission itself.
        if not isinstance(baseline, dict) or set(baseline) != {'board', 'packages'}:
            raise StudioError('Reviewed source revision baseline must be an exact verified parent context')
        board = copy.deepcopy(baseline['board'])
        packages = copy.deepcopy(baseline['packages'])
    origin, gate = _human(project, state, gate_name)
    refs = {}; raw_cache = {}; total_bytes = 0

    def read(reference, *, json_value=True):
        nonlocal total_bytes
        check(); reference = _ref(reference); name = reference['path']
        relative(name)
        aliases = [key for key in refs if key.casefold() == name.casefold()]
        if aliases and aliases[0] != name:
            raise StudioError('Reviewed source revision has a Windows case alias: '+name)
        if name in refs and refs[name] != reference['sha256']:
            raise StudioError('Reviewed source revision binds contradictory file identities')
        file = inside(project.root, name)
        if name not in raw_cache:
            size = file.stat().st_size
            if size > MAX_FILE_BYTES or total_bytes+size > MAX_INPUT_BYTES or len(refs) >= MAX_REFERENCES:
                raise StudioError('Reviewed source revision input budget exhausted')
            raw = file.read_bytes(); total_bytes += len(raw)
            if len(raw) > MAX_FILE_BYTES or total_bytes > MAX_INPUT_BYTES:
                raise StudioError('Reviewed source revision input grew beyond its budget')
            raw_cache[name] = raw
        raw = raw_cache[name]
        if hashlib.sha256(raw).hexdigest() != reference['sha256']:
            raise StudioError('Reviewed source revision file changed: '+name)
        refs[name] = reference['sha256']
        return _parse(raw) if json_value else file

    role_refs = {}
    for role, key in roles.items():
        record = project.verify_evidence(state, key)
        if canonical(gate['evidence'].get(key)) != canonical(record):
            raise StudioError('Reviewed source revision role is outside the exact human gate: '+role)
        reference = _reference(record)
        aliases = [row for row in gate['evidence'].values()
                   if row['path'].casefold() == reference['path'].casefold()]
        if len(aliases) != 1:
            raise StudioError('Reviewed source revision role has duplicate evidence aliases')
        role_refs[role] = reference
    if len({ref['path'].casefold() for ref in role_refs.values()}) != len(ROLES):
        raise StudioError('Reviewed source revision roles reuse the same artifact')
    proposal = read(role_refs['proposal']); read(role_refs['review'], json_value=False)
    candidate_dossier = read(role_refs['candidate_dossier'])
    variant_file = read(role_refs['variant_package'], json_value=False)
    parent_dossier_ref = {'path': board['dossier_path'], 'sha256': board['dependencies'][board['dossier_path']]}
    parent_dossier = read(parent_dossier_ref)
    for path, identity in board['dependencies'].items(): read({'path': path, 'sha256': identity}, json_value=False)
    for row in packages.values(): read(_reference(row), json_value=False)
    if (proposal.get('proposal_sha256') != digest({key: value for key, value in proposal.items() if key != 'proposal_sha256'}) or
            proposal.get('status') != 'PROPOSAL_READY_FOR_REVIEW' or
            proposal.get('packages_allowed_for_review') is not True or
            proposal.get('production_binding') != 'NOT_CHANGED' or
            proposal.get('source_mutated') is not False or proposal.get('body_rescaled') is not False or
            proposal.get('topology_changed') is not False or proposal.get('dossier_ref') != parent_dossier_ref):
        raise StudioError('Reviewed source revision needs a sealed source-bound proposal with unchanged topology')
    inputs = proposal.get('input_refs')
    if not isinstance(inputs, list) or len(inputs) > MAX_REFERENCES:
        raise StudioError('Reviewed source revision proposal needs bounded exact input references')
    values = []
    for ref in inputs:
        file = read(ref, json_value=False)
        if file.suffix.lower() == '.json': values.append((_ref(ref), read(ref)))
    # Repeated identical refs in the original producer are harmless; role
    # aliases, contradictory refs and ambiguous semantic producers are not.
    def unique_input(predicate, label):
        found = {row['path']: (row, value) for row, value in values if predicate(value)}
        if len(found) != 1:
            raise StudioError('Reviewed source revision needs one authenticated '+label)
        return next(iter(found.values()))
    compiled_ref, compiled = unique_input(lambda value: isinstance(value, dict) and digest(value) == proposal.get('source_compilation_sha256'), 'source compilation')
    policy_ref, policy = unique_input(lambda value: isinstance(value, dict) and digest(value) == proposal.get('policy_sha256'), 'grading policy')
    contract('pattern-ease-variant', policy)
    if (policy['compiled_sha256'] != digest(compiled) or policy['dossier_ref'] != parent_dossier_ref or
            policy['body_ref'] != proposal.get('body_ref') or policy['design_decision_ref'] != proposal.get('design_decision_ref') or
            compiled['source_ref'] != parent_dossier_ref or
            policy.get('notch_policy', 'PRESERVE_MATERIAL_POINTS') != 'PRESERVE_MATERIAL_POINTS'):
        raise StudioError('Reviewed source revision policy differs from the exact parent/control baseline')
    if compile_project_dossier(project, compiled['source_ref']['path'], compiled['specification_source_ref']['path']) != compiled:
        raise StudioError('Reviewed source revision compilation is stale against its actual parent inputs')
    decision = read(policy['design_decision_ref'])
    design_reviews = _review(project, decision, policy['design_decision_ref'])
    if design_reviews != proposal.get('canonical_design_reviews'):
        raise StudioError('Reviewed source revision numerical design reviews changed')
    source_data = {}
    for row in compiled['components']:
        if row['pipeline'] != 'PATTERN_SEWN': continue
        cid = row['id']; source_ref = row['package_source_ref']
        if cid not in packages or source_ref != _reference(packages[cid]):
            raise StudioError('Reviewed source revision compilation uses another bound source package')
        with zipfile.ZipFile(read(source_ref, json_value=False)) as archive:
            if archive.getinfo('garment.json').file_size > MAX_FILE_BYTES:
                raise StudioError('Reviewed source revision garment archive exceeds its input budget')
            source_data[cid] = _parse(archive.read('garment.json'))
    local_policy = copy.deepcopy(policy); local_policy['_decision_components'] = decision['component_ids']
    owners, families, variables, fixed = _parameters(compiled, local_policy)
    parameters = proposal.get('solver', {}).get('parameters')
    expected_names = set(fixed) | {key for key, _ in variables}
    if (not isinstance(parameters, dict) or set(parameters) != expected_names or
            any(type(v) not in (int, float) or not math.isfinite(v) for v in parameters.values()) or
            any(parameters[key] != value for key, value in fixed.items()) or
            any(not bounds['minimum'] <= parameters[key] <= bounds['maximum'] for key, bounds in variables)):
        raise StudioError('Reviewed source revision retained parameters violate the original policy bounds')
    replay_garments, replay_annotations = _candidate(compiled, source_data, owners, families, parameters, check)
    holder = {'candidate_garments': replay_garments, 'piece_annotations': replay_annotations}
    marks, diagnostics, marks_valid = _material_notches(compiled, compiled, holder, 'PRESERVE_MATERIAL_POINTS')
    if (not marks_valid or diagnostics or canonical(marks) != canonical(proposal.get('material_notches')) or
            canonical(replay_garments) != canonical(proposal.get('candidate_garments')) or
            canonical(replay_annotations) != canonical(proposal.get('piece_annotations'))):
        raise StudioError('Reviewed source revision geometry or material notches differ from policy replay')
    if not _candidate_geometry_domain(compiled, replay_garments, replay_annotations, check)['valid']:
        raise StudioError('Reviewed source revision violates original geometry controls')
    seams = _seams(compiled, replay_garments, policy['constraints'])
    if canonical(seams) != canonical(proposal.get('seam_constraints')) or any(row['status'] != 'COMPATIBLE' for row in seams):
        raise StudioError('Reviewed source revision sewing constraints do not match the replay')
    diffs = proposal.get('piece_diff')
    if not isinstance(diffs, list) or len(diffs) != len(compiled['textiles']):
        raise StudioError('Reviewed source revision needs complete unique source piece differences')
    observed = set(); changed = []
    for row in diffs:
        pid = row.get('piece')
        if pid in observed or pid not in compiled['textiles']:
            raise StudioError('Reviewed source revision piece difference has duplicate/unknown IDs')
        observed.add(pid); source = compiled['textiles'][pid]; cid = source['component_id']
        piece = replay_garments[cid]['pieces'][pid]
        if (row.get('component_id') != cid or row.get('source_geometry_sha256') != digest(source['source_geometry']) or
                row.get('variant_geometry_sha256') != digest(piece)):
            raise StudioError('Reviewed source revision piece difference contradicts exact geometry identities')
        if row['source_geometry_sha256'] != row['variant_geometry_sha256']: changed.append(pid)
    manifest = inspect_package(variant_file); cid = manifest['component_id']
    if (manifest['asset_id'] != state['asset']['id'] or manifest['pipeline'] != 'PATTERN_SEWN' or
            cid not in source_data or not changed or any(compiled['textiles'][pid]['component_id'] != cid for pid in changed)):
        raise StudioError('Reviewed source revision requires one exact affected sewn component')
    expected_variant = proposal.get('packages', {}).get(cid)
    if not isinstance(expected_variant, dict) or _reference(expected_variant) != role_refs['variant_package'] or expected_variant.get('manifest') != manifest:
        raise StudioError('Reviewed source revision package differs from the exact reviewed proposal')
    with zipfile.ZipFile(variant_file) as archive:
        if archive.getinfo('garment.json').file_size > MAX_FILE_BYTES:
            raise StudioError('Reviewed source revision variant archive exceeds its input budget')
        variant = _parse(archive.read('garment.json'))
    if canonical(variant) != canonical(replay_garments[cid]):
        raise StudioError('Reviewed source revision package contains another candidate geometry')
    comparison = verify_pattern_variant_scope(source_data[cid], variant, changed)
    if set(comparison['changed_piece_ids']) != set(changed):
        raise StudioError('Reviewed source revision exact package diff differs from the latest review scope')
    composition = compose_pattern_variant_dossier(parent_dossier, candidate_dossier, changed)
    for component in candidate_dossier['components'].values():
        for row in component['pieces']:
            if row['id'] in replay_annotations and canonical(row) != canonical(replay_annotations[row['id']]):
                raise StudioError('Reviewed source revision dossier annotations differ from the replay')
    effective_packages = copy.deepcopy(packages)
    effective_packages[cid] = {**role_refs['variant_package'], 'manifest': manifest}
    _validate_dossier_structure(project, state, composition['dossier'], effective_packages)
    parent_identity = {'dossier_ref': parent_dossier_ref,
                       'packages': {key: _reference(value) for key, value in sorted(packages.items())}}
    epoch_basis = {'version': 1, 'parent': parent_identity, 'gate_name': gate_name,
                   'decision_id': gate['decision_id'], 'roles': role_refs, 'component_id': cid,
                   'piece_ids': sorted(changed), 'effective_dossier_sha256': digest(composition['dossier']),
                   'effective_packages': {key: _reference(value) for key, value in sorted(effective_packages.items())}}
    result = {'version': 1, 'status': 'DESIGN_SOURCE_REVISION_PREPARED',
              'source_epoch': digest(epoch_basis), 'epoch_basis': epoch_basis,
              'parent_source_epoch': digest(parent_identity), 'source_revision': 'ADOPTION_REQUIRED',
              'production_binding': 'NOT_CHANGED', 'execution': 'NOT_AUTHORIZED',
              'qualification': 'DESIGN_DATA_ONLY', 'fitting': 'NOT_QUALIFIED',
              'human_decision_origin': origin, 'human_gate_record': copy.deepcopy(gate),
              'reviewed_piece_ids': sorted(changed), 'component_id': cid,
              'package_comparison': comparison,
              'dossier_comparison': {key: value for key, value in composition.items() if key != 'dossier'},
              'input_files': refs, 'code_producers': before_codes,
              'input_preflight': preflight,
              'budgets': {'max_seconds': MAX_SECONDS, 'max_input_bytes': MAX_INPUT_BYTES,
                          'max_file_bytes': MAX_FILE_BYTES, 'max_output_bytes': MAX_OUTPUT_BYTES,
                          'max_references': MAX_REFERENCES},
              'next': 'Use these scoped design data for preparation; production adoption and native execution remain separate operations.'}

    def recheck():
        check(); latest = _state(project)
        if (canonical(latest) != canonical(state) or _codes() != before_codes or
                baseline is None and canonical(require_board(project, latest)) != canonical(board) or
                canonical(_human(project, latest, gate_name)[1]) != canonical(gate) or
                _review(project, decision, policy['design_decision_ref']) != design_reviews):
            raise StudioError('Reviewed source revision canonical parent/review/code changed during preparation')
        for name, identity in refs.items():
            check()
            if sha(inside(project.root, name)) != identity:
                raise StudioError('Reviewed source revision input changed during preparation: '+name)
    recheck()
    return {'result': result, 'dossier': composition['dossier'], 'packages': effective_packages,
            'recheck': recheck, 'check_budget': check}


def prepare_project_reviewed_pattern_revision(project, gate_name, roles, output_dir):
    """Write fresh non-admitted design data from an authenticated calculation."""
    relative(output_dir)
    if not output_dir.startswith('preparation/') or output_dir == 'preparation/':
        raise StudioError('Reviewed source revision output must be fresh under preparation/')
    output = inside(project.root, output_dir, False)
    if output.exists():
        raise StudioError('Reviewed source revision output already exists; preserve it')
    parent = output.parent
    if parent.exists() and any(child.name.casefold() == output.name.casefold() for child in parent.iterdir()):
        raise StudioError('Reviewed source revision output has a Windows case alias')
    calculated = calculate_reviewed_pattern_revision(project, gate_name, roles)
    result = calculated['result']; recheck = calculated['recheck']; check = calculated['check_budget']
    files = {'effective-dossier.json': calculated['dossier'], 'effective-packages.json': calculated['packages']}
    result['outputs'] = {name: {'path': output_dir+'/'+name, 'sha256': hashlib.sha256(json.dumps(value, ensure_ascii=False, indent=2, allow_nan=False).encode('utf-8')+b'\n').hexdigest()} for name, value in files.items()}
    files['revision.json'] = result
    if sum(len(canonical(value)) for value in files.values()) > MAX_OUTPUT_BYTES:
        raise StudioError('Reviewed source revision output budget exhausted')
    output.mkdir(parents=True, exist_ok=False)
    try:
        for name, value in files.items(): atomic_json(output/name, value)
        if sum(file.stat().st_size for file in output.iterdir()) > MAX_OUTPUT_BYTES:
            raise StudioError('Reviewed source revision serialized output budget exhausted')
        recheck()
        for name, record in result['outputs'].items():
            if sha(output/name) != record['sha256']:
                raise StudioError('Reviewed source revision output changed during preparation')
        manifest_sha256 = sha(output/'revision.json'); check()
    except BaseException as error:
        atomic_json(output/'failure.json', {'status': 'PREPARATION_REFUSED', 'error': str(error),
                    'production_binding': 'NOT_CHANGED', 'execution': 'NOT_AUTHORIZED'})
        raise
    return {**result, 'manifest_ref': {'path': output_dir+'/revision.json', 'sha256': manifest_sha256}}
