"""Synthetic review epochs only; no production or native acceptance."""
import copy
import math
from unittest.mock import patch
import zipfile

from a3d.core import StudioError, atomic_json, digest, read_json, sha
from a3d.planning import require_board
from a3d.production_dossier import compile_project_dossier
from a3d.pattern_ease_variant import _candidate, _material_notches, _parameters, _seams, _svg
from a3d.reviewed_pattern_revisions import prepare_project_reviewed_pattern_revision
from tests.test_core import Case
import tests.test_reviewed_pattern_admission as admission_fixture
from tests.test_garment_planner import example as planner_example
from tests.support import png
import tests.support as support


class ReviewedPatternRevisions(Case):
    def fixture(self):
        old_source = support.garment_source
        old_dossier = support.construction_dossier
        def source(directory):
            data = old_source(directory)
            for seam in data['seams']: seam['kind'] = 'permanent'
            for pid in ('panel.one', 'panel.two', 'panel.three'):
                data['pieces'][pid] = copy.deepcopy(data['pieces']['front'])
            atomic_json(directory/'garment.json', data)
            (directory/'pattern.svg').write_bytes(_svg(data))
            return data
        def dossier(project, garment):
            value = old_dossier(project, garment)
            rows = value['components']['garment.coat']['pieces']
            for i, pid in enumerate(('panel.one', 'panel.two', 'panel.three')):
                row = copy.deepcopy(rows[0]); row['id'] = pid
                row['pattern']['folds'] = []; row['pattern']['assembly_marks'] = []
                rows.append(row)
                value['exploded']['annotations'].append({'component_id': 'garment.coat', 'piece_id': pid,
                    'anchor_px': [15+i*12, 50], 'label_position_px': [3, 80+i*12]})
            return value
        helper = admission_fixture.ReviewedPatternAdmissionTests(); helper.root = self.root
        old_record = helper.record_decision
        def record_old_review(parent, decision, request, **kwargs):
            # The historical V1 reader hashes this artifact as opaque evidence.
            # Unused generated clones/producer inputs were never imported and
            # cannot become mandatory dependencies of the new preparation.
            path = parent.root/decision['proposal_ref']['path']
            value = read_json(path)
            value.update(packages={'unused.clone': {'path': 'variants/not-copied/unused.garmentpkg', 'sha256': '0'*64}},
                         input_refs=[{'path': 'preparation/not-copied/old-compiled.json', 'sha256': '0'*64}])
            value['proposal_sha256'] = digest(value)
            atomic_json(path, value); decision['proposal_ref']['sha256'] = sha(path)
            return old_record(parent, decision, request, **kwargs)
        helper.record_decision = record_old_review
        with patch('tests.support.garment_source', source), patch('tests.support.construction_dossier', dossier):
            _, _, _, project = helper.imported(name='source'+str(len(list(self.root.iterdir()))))
        board = require_board(project, project.state())
        base = read_json(project.root/board['dossier_path'])
        root = project.root/'preparation/inputs'; root.mkdir(parents=True)
        ref = lambda path: {'path': path, 'sha256': sha(project.root/path)}
        body = root/'body.json'; atomic_json(body, {'status': 'SYNTHETIC_NO_FITTING'})
        old = planner_example()
        cid = 'garment.coat'; package = project.state()['components'][cid]['package']
        with zipfile.ZipFile(project.root/package['path']) as z: data = read_json_from_bytes(z.read('garment.json'))
        source_ref = ref(board['dossier_path']); body_ref = ref('preparation/inputs/body.json')
        spec = {'version': 1, 'source_ref': source_ref, 'body_ref': body_ref,
            'packages': [{'component_id': cid, 'source_ref': ref(package['path'])}],
            'piece_semantics': {pid: {'role': 'lining', 'side': 'center', 'layer': 'cloth', 'longitudinal_uv_axis': 'v'} for pid in data['pieces']},
            'layers': {'version': 1, 'source_ref': source_ref, 'mode': 'ordered', 'interaction': 'one_way_declared',
                'nodes': [{'id': 'body', 'kind': 'body', 'panels': [], 'colliders': ['body'], 'source_ref': body_ref},
                          {'id': 'cloth', 'kind': 'garment', 'panels': list(data['pieces']), 'colliders': [], 'source_ref': source_ref}],
                'inside_to_outside': [['body', 'cloth']]}, 'budgets': old['budgets']}
        atomic_json(root/'spec.json', spec)
        compiled = compile_project_dossier(project, source_ref['path'], 'preparation/inputs/spec.json')
        atomic_json(root/'compiled.json', compiled)
        numeric_proposal = root/'numeric.json'; atomic_json(numeric_proposal, {'scope': 'SYNTHETIC'})
        numeric_review = root/'numeric-review.json'; atomic_json(numeric_review, {'scope': 'SYNTHETIC'})
        decision = {'status': 'NUMERIC_EASE_DESIGN_INTENT_APPROVED', 'approved': True, 'component_ids': [cid],
            'dossier_ref': source_ref, 'body_ref': body_ref, 'proposal_ref': ref('preparation/inputs/numeric.json'),
            'review_ref': ref('preparation/inputs/numeric-review.json'), 'source_ref': 'test:explicit-intent', 'statement': 'SYNTHETIC intent'}
        atomic_json(root/'decision.json', decision)
        decision_ref = ref('preparation/inputs/decision.json')
        keys = []
        for i, reference in enumerate([decision_ref, source_ref, body_ref, decision['proposal_ref'], decision['review_ref']]):
            key = 'synthetic.numeric.'+str(i); project.evidence(key, reference['path']); keys.append(key)
        numeric_gate = project.gate('ease-design.'+cid, True, decision['statement'], keys, decision['source_ref'])
        selected = ['front', 'back', 'panel.one', 'panel.two', 'panel.three']
        fixed = lambda v: {'minimum': v, 'initial': v, 'maximum': v}
        policy = {'version': 1, 'compiled_sha256': digest(compiled), 'design_decision_ref': decision_ref,
            'dossier_ref': source_ref, 'body_ref': body_ref, 'unlisted_pieces': 'PRESERVE_EXACT',
            'families': [{'id': pid, 'pieces': [pid], 'mode': 'AFFINE_SOURCE_UV', 'anchor_vertices': {pid: 0},
                          'scale_x': fixed(1.1), 'scale_y': fixed(1.)} for pid in selected],
            'nominal_paths': [{'id': 'test.span', 'body_landmark': 'test.reference', 'component_id': cid, 'layer': 'cloth',
                'path_kind': 'open_material_span', 'segments': [{'piece': 'front', 'from': {'edge': 'left', 'fraction': .5},
                                                             'to': {'edge': 'right', 'fraction': .5}}],
                'joins': [], 'engaged_links': [], 'takeup': [], 'objective': 'TARGET', 'path_parameterization': 'NORMALIZED_ARC_PATH_VARIANT'}],
            'constraints': {'seam_length_absolute_cm': .00001, 'seam_length_relative': .0000001,
                'target_absolute_cm': .00001, 'target_weight': 1., 'seam_weight': 100.},
            'budgets': {'max_iterations': 2, 'max_evaluations': 100, 'max_seconds': 10., 'finite_difference_step': .0001,
                       'damping': .00001, 'minimum_step': .0001, 'stagnation_iterations': 1}, 'notch_policy': 'PRESERVE_MATERIAL_POINTS'}
        atomic_json(root/'policy.json', policy)
        local = copy.deepcopy(policy); local['_decision_components'] = [cid]
        owners, families, _, parameters = _parameters(compiled, local)
        candidates, annotations = _candidate(compiled, {cid: data}, owners, families, parameters)
        holder = {'candidate_garments': candidates, 'piece_annotations': annotations}
        marks, _, valid = _material_notches(compiled, compiled, holder, 'PRESERVE_MATERIAL_POINTS')
        self.assertTrue(valid)
        candidate = copy.deepcopy(base)
        candidate['components'][cid]['pieces'] = [annotations[row['id']] for row in candidate['components'][cid]['pieces']]
        variants = project.root/'variants/new'; variants.mkdir(parents=True)
        atomic_json(variants/'candidate.json', candidate)
        package_source = variants/'package-source'; package_source.mkdir()
        variant_ref = helper.write_package(project, package_source, candidates[cid], 'package.garmentpkg')
        from a3d.packages import inspect_package
        variant_record = {**variant_ref, 'manifest': inspect_package(project.root/variant_ref['path'])}
        (variants/'review.png').write_bytes(png())
        diffs = [{'piece': pid, 'component_id': cid, 'source_geometry_sha256': digest(row['source_geometry']),
                  'variant_geometry_sha256': digest(candidates[cid]['pieces'][pid])} for pid, row in compiled['textiles'].items()]
        proposal = {'version': 1, 'status': 'PROPOSAL_READY_FOR_REVIEW', 'packages_allowed_for_review': True,
            'source_compilation_sha256': digest(compiled), 'policy_sha256': digest(policy), 'design_decision_ref': decision_ref,
            'dossier_ref': source_ref, 'body_ref': body_ref, 'production_binding': 'NOT_CHANGED', 'source_mutated': False,
            'body_rescaled': False, 'topology_changed': False, 'piece_diff': diffs, 'candidate_garments': candidates,
            'piece_annotations': annotations, 'material_notches': marks, 'seam_constraints': _seams(compiled, candidates, policy['constraints']),
            'solver': {'parameters': parameters}, 'packages': {cid: variant_record},
            'input_refs': [ref('preparation/inputs/compiled.json'), ref('preparation/inputs/policy.json'), decision_ref,
                           source_ref, body_ref, ref('preparation/inputs/spec.json'), ref(package['path'])],
            'canonical_design_reviews': [{'gate': 'ease-design.'+cid, 'decision_id': numeric_gate['decision_id'], 'source_ref': decision['source_ref']}]}
        atomic_json(variants/'proposal.json', {**proposal, 'proposal_sha256': digest(proposal)})
        roles = {'proposal': 'new.proposal', 'review': 'new.review', 'candidate_dossier': 'new.dossier', 'variant_package': 'new.package'}
        paths = ['variants/new/proposal.json', 'variants/new/review.png', 'variants/new/candidate.json', variant_ref['path']]
        for key, path in zip(roles.values(), paths): project.evidence(key, path)
        gate_name = 'pattern-variant.new-shapes'
        project.gate(gate_name, True, 'SYNTHETIC: approve five shapes only', list(roles.values()), 'test:new-cutting-approval')
        return project, gate_name, roles, selected

    def prepare(self, fixture, name='preparation/revision'):
        project, gate, roles, _ = fixture
        return prepare_project_reviewed_pattern_revision(project, gate, roles, name)

    def rewrite_proposal(self, fixture, mutate):
        project, gate, roles, _ = fixture
        path = project.root/project.state()['evidence'][roles['proposal']]['path']
        value = read_json(path); mutate(value)
        value['proposal_sha256'] = digest({k: v for k, v in value.items() if k != 'proposal_sha256'})
        atomic_json(path, value); project.evidence(roles['proposal'], path.relative_to(project.root).as_posix())
        old = project.state()['gates'][gate]
        project.gate(gate, True, old['statement'], list(roles.values()), old['source_ref'])

    def test_five_latest_pieces_preserve_two_previously_reviewed_sleeves_and_canonical_state(self):
        fixture = self.fixture(); project, _, _, selected = fixture
        before = sha(project.db), copy.deepcopy(project.state()), require_board(project, project.state())
        result = self.prepare(fixture)
        self.assertEqual(result['reviewed_piece_ids'], sorted(selected))
        self.assertEqual(result['status'], 'DESIGN_SOURCE_REVISION_PREPARED')
        self.assertEqual(result['production_binding'], 'NOT_CHANGED')
        self.assertEqual(result['execution'], 'NOT_AUTHORIZED')
        self.assertEqual(result['source_revision'], 'ADOPTION_REQUIRED')
        self.assertEqual(result['fitting'], 'NOT_QUALIFIED')
        effective = read_json(project.root/result['outputs']['effective-dossier.json']['path'])
        parent = read_json(project.root/before[2]['dossier_path'])
        rows = lambda d: {row['id']: row for row in d['components']['garment.coat']['pieces']}
        for pid in ['sleeve-left', 'sleeve-right']:
            self.assertEqual(rows(effective)[pid], rows(parent)[pid])
        self.assertEqual((sha(project.db), project.state(), require_board(project, project.state())), before)
        second = self.prepare(fixture, 'preparation/revision-two')
        self.assertEqual(result['source_epoch'], second['source_epoch'])

    def test_calculation_of_authenticated_archived_baseline_writes_no_outputs(self):
        from a3d.reviewed_pattern_revisions import calculate_reviewed_pattern_revision
        from a3d.planning import package_records
        fixture = self.fixture(); project, gate, roles, _ = fixture
        state = project.state()
        baseline = {'board': require_board(project, state), 'packages': package_records(project, state)}
        database = sha(project.db)
        files = {file.relative_to(project.root).as_posix(): sha(file)
                 for file in project.root.rglob('*') if file.is_file()}
        calculated = calculate_reviewed_pattern_revision(project, gate, roles, baseline=baseline)
        self.assertEqual(calculated['result']['status'], 'DESIGN_SOURCE_REVISION_PREPARED')
        self.assertNotIn('outputs', calculated['result'])
        self.assertEqual(sha(project.db), database)
        self.assertEqual({file.relative_to(project.root).as_posix(): sha(file)
                          for file in project.root.rglob('*') if file.is_file()}, files)

    def test_scope_is_parent_relative_not_cumulative(self):
        fixture = self.fixture(); result = self.prepare(fixture)
        self.assertEqual(len(result['reviewed_piece_ids']), 5)
        self.assertIn('sleeve-left', result['package_comparison']['preserved_piece_ids'])
        self.assertIn('sleeve-right', result['package_comparison']['preserved_piece_ids'])

    def test_duplicate_roles_and_role_artifact_aliases_refused(self):
        fixture = self.fixture(); project, gate, roles, _ = fixture
        duplicate = {**roles, 'review': roles['proposal']}
        with self.assertRaisesRegex(StudioError, 'distinct'): prepare_project_reviewed_pattern_revision(project, gate, duplicate, 'preparation/out')
        record = project.state()['evidence'][roles['review']]
        project.evidence('review.alias', record['path'])
        old = project.state()['gates'][gate]
        project.gate(gate, True, old['statement'], [*roles.values(), 'review.alias'], old['source_ref'])
        with self.assertRaisesRegex(StudioError, 'duplicate evidence aliases'): self.prepare(fixture)

    def test_revoked_gate_stale_role_and_bad_proposal_seal_refused(self):
        for failure in ['revoke', 'stale', 'seal']:
            with self.subTest(failure=failure):
                fixture = self.fixture(); project, gate, roles, _ = fixture
                if failure == 'revoke':
                    old = project.state()['gates'][gate]; project.gate(gate, False, 'reject', list(roles.values()), old['source_ref'])
                elif failure == 'stale':
                    project.evidence(roles['review'], project.state()['evidence'][roles['review']]['path'])
                else:
                    path = project.root/project.state()['evidence'][roles['proposal']]['path']
                    value = read_json(path); value['proposal_sha256'] = '0'*64; atomic_json(path, value)
                    project.evidence(roles['proposal'], path.relative_to(project.root).as_posix())
                    old = project.state()['gates'][gate]; project.gate(gate, True, old['statement'], list(roles.values()), old['source_ref'])
                with self.assertRaises(StudioError): self.prepare(fixture)
                self.assertFalse((project.root/'preparation/revision').exists())

    def test_forged_notches_closure_and_outside_scope_ulp_are_refused(self):
        for failure in ['notch', 'closure', 'ulp', 'scope']:
            fixture = self.fixture()
            def mutate(value):
                if failure == 'notch': value['piece_annotations']['front']['pattern']['assembly_marks'][0]['position'] = .9
                elif failure == 'closure': value['candidate_garments']['garment.coat']['seams'][0]['kind'] = 'closure'
                elif failure == 'ulp':
                    point = value['candidate_garments']['garment.coat']['pieces']['sleeve-left']['vertices'][0]
                    point[0] = math.nextafter(point[0], 1.)
                else: value['piece_diff'][0]['source_geometry_sha256'] = '0'*64
            self.rewrite_proposal(fixture, mutate)
            with self.subTest(failure=failure), self.assertRaises(StudioError): self.prepare(fixture)

    def test_policy_baseline_and_compilation_changes_refused(self):
        for key in ['policy_sha256', 'source_compilation_sha256', 'dossier_ref']:
            fixture = self.fixture()
            self.rewrite_proposal(fixture, lambda value: value.update({key: {'path': 'different.json', 'sha256': '0'*64} if key == 'dossier_ref' else '0'*64}))
            with self.subTest(key=key), self.assertRaises(StudioError): self.prepare(fixture)

    def test_parent_stale_rejected_and_historical_modules_unchanged(self):
        fixture = self.fixture(); project = fixture[0]
        from a3d import reviewed_pattern_admission, pattern_variant_composition
        before = [sha(module.__file__) for module in [reviewed_pattern_admission, pattern_variant_composition]]
        proof = project.state()['evidence']['reviewed-pattern-composition']; (project.root/proof['path']).write_text('{}', encoding='utf-8')
        with self.assertRaises(StudioError): self.prepare(fixture)
        self.assertEqual(before, [sha(module.__file__) for module in [reviewed_pattern_admission, pattern_variant_composition]])

    def test_fresh_output_path_and_time_and_input_budgets_are_enforced(self):
        fixture = self.fixture(); project = fixture[0]
        self.prepare(fixture)
        with self.assertRaisesRegex(StudioError, 'already exists'): self.prepare(fixture)
        for name in ['variants/forbidden', 'preparation/../escape', 'preparation/Revision']:
            with self.subTest(name=name), self.assertRaises(StudioError): self.prepare(fixture, name)
        with patch('a3d.reviewed_pattern_revisions.MAX_SECONDS', -1):
            with self.assertRaisesRegex(StudioError, 'time budget'): self.prepare(fixture, 'preparation/timeout')
        with patch('a3d.reviewed_pattern_revisions.MAX_INPUT_BYTES', 1):
            with self.assertRaisesRegex(StudioError, 'budget'): self.prepare(fixture, 'preparation/input-limit')
        self.assertFalse((project.root/'preparation/timeout').exists())

    def test_canonical_mutation_during_output_is_detected_without_binding_candidate(self):
        fixture = self.fixture(); project, gate, roles, _ = fixture
        before_package = copy.deepcopy(project.state()['components']['garment.coat']['package'])
        original = atomic_json
        mutated = False
        def write(path, value):
            nonlocal mutated
            original(path, value)
            if not mutated and str(path).endswith('effective-dossier.json'):
                mutated = True
                project.gate(gate, False, 'SYNTHETIC revoked concurrently', list(roles.values()), 'test:revoke')
        with patch('a3d.reviewed_pattern_revisions.atomic_json', write):
            with self.assertRaisesRegex(StudioError, 'changed during preparation'): self.prepare(fixture)
        self.assertEqual(before_package, project.state()['components']['garment.coat']['package'])
        self.assertTrue((project.root/'preparation/revision/failure.json').exists())

    def compressed_fixture_package(self, fixture, members):
        project, gate, roles, _ = fixture
        path = project.root/'variants/new/expanded-budget.garmentpkg'
        with zipfile.ZipFile(path, 'w', compression=zipfile.ZIP_DEFLATED) as archive:
            for name, amount in members: archive.writestr(name, b'0'*amount)
        project.evidence(roles['variant_package'], path.relative_to(project.root).as_posix())
        old = project.state()['gates'][gate]
        project.gate(gate, True, old['statement'], list(roles.values()), old['source_ref'])
        return path

    def test_expanded_garment_member_refused_before_any_historical_validator(self):
        fixture = self.fixture()
        path = self.compressed_fixture_package(fixture, [('garment.json', 8192)])
        self.assertLess(path.stat().st_size, 4096)
        with patch('a3d.reviewed_pattern_revisions.MAX_FILE_BYTES', 4096), \
             patch('a3d.planning.require_board', side_effect=AssertionError('Historical admission must not run')), \
             patch('a3d.production_dossier.compile_project_dossier', side_effect=AssertionError('Compiler must not run')), \
             patch('a3d.packages.inspect_package', side_effect=AssertionError('Package inspector must not run')):
            with self.assertRaisesRegex(StudioError, 'expanded archive member'): self.prepare(fixture)

    def test_expanded_sum_of_archive_members_refused_before_validation(self):
        fixture = self.fixture()
        path = self.compressed_fixture_package(fixture, [('garment.json', 3000), ('pattern.svg', 3000)])
        self.assertLess(path.stat().st_size, 4096)
        with patch('a3d.reviewed_pattern_revisions.MAX_INPUT_BYTES', 4096), \
             patch('a3d.planning.require_board', side_effect=AssertionError('Historical admission must not run')):
            with self.assertRaisesRegex(StudioError, 'expanded archive total'): self.prepare(fixture)

    def test_preflight_covers_parent_package_and_ignores_unrelated_native_evidence(self):
        fixture = self.fixture(); project = fixture[0]
        # A non-admitted inventory fixture tests the preflight alone. The
        # canonical production state remains unchanged and is never rewritten.
        path = project.root/'variants/parent-budget.garmentpkg'
        with zipfile.ZipFile(path, 'w', compression=zipfile.ZIP_DEFLATED) as archive:
            archive.writestr('garment.json', b'0'*8192)
        state = copy.deepcopy(project.state())
        state['components']['garment.coat']['package'] = {'path': path.relative_to(project.root).as_posix(), 'sha256': sha(path)}
        state['gates'] = {}; state['evidence'] = {'unrelated-native': {'path': 'does-not-exist.blend', 'sha256': '0'*64}}
        from a3d.reviewed_pattern_revisions import _preflight_dependencies
        before = sha(project.db)
        with patch('a3d.reviewed_pattern_revisions.MAX_FILE_BYTES', 4096):
            with self.assertRaisesRegex(StudioError, 'expanded archive member'):
                _preflight_dependencies(project, state, 'pattern-variant.fixture', {}, lambda: None)
        self.assertEqual(sha(project.db), before)

    def test_preflight_also_bounds_generic_3dpkg_and_packages_nested_in_specification(self):
        fixture = self.fixture(); project = fixture[0]
        package = project.root/'preparation/hidden.3dpkg'
        with zipfile.ZipFile(package, 'w', compression=zipfile.ZIP_DEFLATED) as archive:
            archive.writestr('garment.json', b'0'*8192)
        specification = project.root/'preparation/hidden-spec.json'
        atomic_json(specification, {'packages': [{'component_id': 'garment.synthetic', 'source_ref': {
            'path': package.relative_to(project.root).as_posix(), 'sha256': sha(package)}}]})
        state = copy.deepcopy(project.state())
        state['components'] = {}; state['gates'] = {}
        state['evidence'] = {'construction-board': {'path': specification.relative_to(project.root).as_posix(), 'sha256': sha(specification)}}
        from a3d.reviewed_pattern_revisions import _preflight_dependencies
        with patch('a3d.reviewed_pattern_revisions.MAX_FILE_BYTES', 4096):
            with self.assertRaisesRegex(StudioError, 'expanded archive member'):
                _preflight_dependencies(project, state, 'pattern-variant.fixture', {}, lambda: None)

    def test_current_proposal_missing_consumed_input_is_still_refused_before_validation(self):
        fixture = self.fixture()
        self.rewrite_proposal(fixture, lambda value: value['input_refs'].append({
            'path': 'preparation/missing-current-input.json', 'sha256': '0'*64}))
        with patch('a3d.planning.require_board', side_effect=AssertionError('Historical admission must not run')):
            with self.assertRaises(StudioError): self.prepare(fixture)


def read_json_from_bytes(raw):
    import json
    return json.loads(raw)
