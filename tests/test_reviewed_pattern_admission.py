"""Synthetic canonical projects only; no real garment or image acceptance."""
import copy
import json
import math
import sqlite3
import zipfile
from contextlib import closing
from unittest.mock import patch

from a3d.approved_inputs import import_approved_design
from a3d.core import StudioError, atomic_json, read_json, sha
from a3d.packages import build_package
from a3d.planning import require_board
from a3d.reviewed_pattern_admission import KEY, KIND, prepare_reviewed_pattern_composition
from a3d.store import Project
from tests.support import PROVENANCE, png, ready_project
from tests.test_core import Case


class ReviewedPatternAdmissionTests(Case):
    def fixture(self, *, name='source', source=None, generic=False):
        source = source or ready_project(self.root/name, True)
        state = source.state()
        directory = source.root/'variants/scoped'
        directory.mkdir(parents=True)
        package_source = directory/'source'
        # Exact source input fixture, never native state or production evidence.
        with zipfile.ZipFile(source.root/state['components']['garment.coat']['package']['path']) as archive:
            package_source.mkdir()
            for filename in ('garment.json', 'pattern.svg'):
                (package_source/filename).write_bytes(archive.read(filename))
        variant = read_json(package_source/'garment.json')
        for pid in ('sleeve-left', 'sleeve-right'):
            for vertex in variant['pieces'][pid]['vertices']:
                vertex[0] *= 1.1
        self.write_package(source, package_source, variant, 'package.garmentpkg')
        board = read_json(source.root/state['evidence']['construction-board']['path'])
        original = read_json(source.root/board['dossier_path'])
        candidate = copy.deepcopy(original)
        rows = {p['id']: p for p in candidate['components']['garment.coat']['pieces']}
        for pid in ('sleeve-left', 'sleeve-right'):
            rows[pid]['dimensions_cm'] = [22, 40]
            rows[pid]['pattern']['cut_outline_cm'] = [[-1, -1], [23, -1], [23, 41], [-1, 41]]
        # One ULP on an unreviewed front notch MUST be excluded, not tolerated.
        rows['front']['pattern']['assembly_marks'][0]['position'] = math.nextafter(.3, 1)
        atomic_json(directory/'candidate-dossier.json', candidate)
        atomic_json(directory/'proposal.json', {'scope': 'SYNTHETIC_TWO_SLEEVES_ONLY'})
        (directory/'review.png').write_bytes(png())
        atomic_json(directory/'numeric-intent.json', {'scope': 'TEST_ONLY_NUMERIC_INTENT'})
        atomic_json(directory/'body.json', {'scope': 'TEST_ONLY_BODY_REFERENCE_NO_FITTING'})
        ref = lambda path: {'path': path, 'sha256': sha(source.root/path)}
        decision = {
            'version': 1, 'component_id': 'garment.coat', 'piece_ids': ['sleeve-left', 'sleeve-right'],
            'approved': True,
            'status': 'SCOPED_PATTERN_VARIANT_APPROVED' if generic else 'TWO_SLEEVE_PATTERN_VARIANT_APPROVED',
            'approved_scope': ['pattern_shapes' if generic else 'two_sleeve_pattern_shapes'],
            'statement': 'SYNTHETIC TEST ONLY: reviewed the two exact sleeve fixture shapes',
            'source_ref': 'test:scoped-pattern-review-not-a-production-approval',
            'proposal_ref': ref('variants/scoped/proposal.json'),
            'review_ref': ref('variants/scoped/review.png'),
            'candidate_dossier_ref': ref('variants/scoped/candidate-dossier.json'),
            'variant_package_ref': ref('variants/scoped/package.garmentpkg'),
            'numeric_design_decision_ref': ref('variants/scoped/numeric-intent.json'),
            'body_ref': ref('variants/scoped/body.json'),
            'original_dossier_ref': ref(board['dossier_path']),
        }
        request = {'gate_name': 'pattern-variant.fixture.garment.coat', 'decision_evidence_key': 'scoped.decision'}
        self.record_decision(source, decision, request)
        return source, request, decision

    def write_package(self, source, directory, garment, filename):
        atomic_json(directory/'garment.json', garment)
        polygons = ''.join('<polygon id="'+pid+'" points="'+' '.join(','.join(map(str, p)) for p in piece['vertices'])+'"/>'
                           for pid, piece in garment['pieces'].items())
        (directory/'pattern.svg').write_text('<svg xmlns="http://www.w3.org/2000/svg">'+polygons+'</svg>', encoding='utf-8')
        destination = directory.parent/filename
        build_package(directory, destination, source.state()['asset']['id'], 'garment.coat', 'PATTERN_SEWN', PROVENANCE)
        return {'path': destination.relative_to(source.root).as_posix(), 'sha256': sha(destination)}

    def record_decision(self, source, decision, request, *, aliases=()):
        path = 'variants/scoped/decision.json'
        atomic_json(source.root/path, decision)
        source.evidence(request['decision_evidence_key'], path)
        keys = [request['decision_evidence_key']]
        for role in ('proposal_ref', 'review_ref', 'candidate_dossier_ref', 'variant_package_ref'):
            key = 'scoped.'+role.removesuffix('_ref').replace('_', '-')
            source.evidence(key, decision[role]['path']); keys.append(key)
        for alias in aliases:
            source.evidence(alias, path); keys.append(alias)
        source.gate(request['gate_name'], True, decision['statement'], keys, decision['source_ref'])

    def imported(self, name='source'):
        source, request, decision = self.fixture(name=name)
        target = Project.create(self.root/(name+'-target'), source.state()['asset'])
        import_approved_design(target, source, pattern_variant=request)
        return source, request, decision, target

    def inherited(self, name='inherited'):
        parent = ready_project(self.root/(name+'-parent'), True)
        source = Project.create(self.root/name, parent.state()['asset'])
        import_approved_design(source, parent)
        source, request, decision = self.fixture(source=source)
        return parent, source, request, decision

    def change_proof(self, target, change):
        ref = target.state()['evidence'][KEY]
        proof = read_json(target.root/ref['path'])
        change(proof)
        atomic_json(target.root/ref['path'], proof)
        target.evidence(KEY, ref['path'])

    def test_preparation_is_read_only_and_reports_ulp_exclusion(self):
        source, request, decision = self.fixture()
        before = {p.relative_to(source.root).as_posix(): sha(p) for p in source.root.rglob('*') if p.is_file()}
        with patch.object(source, 'transaction', side_effect=AssertionError('Read-only service wrote state')):
            result = prepare_reviewed_pattern_composition(source, request)
        after = {p.relative_to(source.root).as_posix(): sha(p) for p in source.root.rglob('*') if p.is_file()}
        self.assertEqual(before, after)
        self.assertEqual(result['status'], 'COMPOSED_INPUTS_ONLY')
        for field in ('construction', 'fitting', 'permission', 'human_review'):
            self.assertEqual(result[field], 'NOT_GRANTED')
        self.assertEqual(result['qualification'], 'NONE')
        template = result['manifest_template']
        self.assertEqual(template['origin']['kind'], 'calculated')
        self.assertEqual(template['reviewed_piece_ids'], decision['piece_ids'])
        self.assertEqual(set(result['extra_gates']), {request['gate_name']})
        self.assertEqual(result['extra_evidence'], source.state()['gates'][request['gate_name']]['evidence'])
        excluded = template['dossier_comparison']['excluded_unreviewed_differences']
        self.assertEqual(excluded[0]['piece_id'], 'front')
        difference = excluded[0]['differences'][0]
        self.assertEqual(difference['approved_value'], .3)
        self.assertEqual(difference['variant_value'], math.nextafter(.3, 1))
        self.assertNotEqual(difference['approved_value'], difference['variant_value'])
        original = read_json(source.root/decision['original_dossier_ref']['path'])
        self.assertEqual(result['composed_dossier']['components']['garment.coat']['pieces'][0],
                         original['components']['garment.coat']['pieces'][0])

    def test_registered_import_uses_composed_dossier_preserves_original_gate(self):
        source, request, _, target = self.imported()
        before = sha(source.db)
        view = require_board(target, target.state())
        self.assertEqual(sha(source.db), before)
        self.assertEqual(view['kind'], KIND)
        self.assertEqual(view['qualification'], 'NONE')
        self.assertEqual(view['permission'], 'NOT_GRANTED')
        self.assertEqual(view['image_scope'], 'BASE_DESIGN_ONLY_SCOPED_REVIEW_SEPARATE')
        self.assertEqual(view['dossier_path'], '.a3d/evidence/reviewed-pattern-composition-dossier.json')
        self.assertEqual(target.state()['gates']['construction'], source.state()['gates']['construction'])
        self.assertEqual(target.state()['gates'][request['gate_name']], source.state()['gates'][request['gate_name']])
        self.assertNotIn('fitting', target.state()['gates'])
        self.assertNotIn('final', target.state()['gates'])
        self.assertIn(view['dossier_path'], view['dependencies'])
        self.assertIn(target.state()['evidence'][KEY]['path'], view['dependencies'])

    def test_generic_v1_document_is_supported_without_human_grants(self):
        source, request, _ = self.fixture(generic=True)
        self.assertEqual(prepare_reviewed_pattern_composition(source, request)['qualification'], 'NONE')

    def test_changed_package_or_body_or_missing_review_refuses(self):
        for role in ('variant_package_ref', 'body_ref', 'review_ref'):
            with self.subTest(role=role):
                source, request, decision = self.fixture(name=role)
                file = source.root/decision[role]['path']
                file.unlink() if role == 'review_ref' else file.write_bytes(file.read_bytes()+b'changed')
                with self.assertRaises((StudioError, OSError)):
                    prepare_reviewed_pattern_composition(source, request)

    def test_revoked_human_gate_refuses_replay(self):
        source, request, decision, target = self.imported()
        source.gate(request['gate_name'], False, 'SYNTHETIC approval revoked',
                    [request['decision_evidence_key']], decision['source_ref'])
        with self.assertRaises(StudioError): require_board(target, target.state())

    def test_matching_gate_flags_without_human_event_are_rejected(self):
        source, request, _ = self.fixture()
        with source.transaction() as db:
            state = source.state(db)
            state['gates'][request['gate_name']]['decision_id'] = 'synthetic-unrecorded-event'
            source.save(db, state, 'test_fixture_invalid_gate', {'scope': 'TEST_ONLY'})
        with self.assertRaisesRegex(StudioError, 'direct canonical human event'):
            prepare_reviewed_pattern_composition(source, request)

    def test_gate_statement_and_document_source_must_agree(self):
        source, request, decision = self.fixture()
        source.gate(request['gate_name'], True, 'SYNTHETIC another statement',
                    list(source.state()['gates'][request['gate_name']]['evidence']), decision['source_ref'])
        with self.assertRaisesRegex(StudioError, 'statement or conversation source'):
            prepare_reviewed_pattern_composition(source, request)

    def test_invalid_explicit_scopes_refuse_even_with_a_recorded_fixture_gate(self):
        cases = [([], ['sleeve-left', 'sleeve-right']),
                 (['two_sleeve_pattern_shapes'], []),
                 (['two_sleeve_pattern_shapes'], ['sleeve-left', 'sleeve-left']),
                 (['two_sleeve_pattern_shapes'], ['sleeve-left', 'missing']),
                 (['physical_fitting'], ['sleeve-left', 'sleeve-right'])]
        for i, (scope, ids) in enumerate(cases):
            with self.subTest(i=i):
                source, request, decision = self.fixture(name='scope-'+str(i))
                decision['approved_scope'], decision['piece_ids'] = scope, ids
                self.record_decision(source, decision, request)
                with self.assertRaises(StudioError): prepare_reviewed_pattern_composition(source, request)

    def test_duplicate_role_and_duplicate_gate_binding_are_rejected(self):
        source, request, decision = self.fixture(name='duplicate-role')
        decision['review_ref'] = copy.deepcopy(decision['proposal_ref'])
        self.record_decision(source, decision, request)
        with self.assertRaisesRegex(StudioError, 'duplicate reference bindings'):
            prepare_reviewed_pattern_composition(source, request)
        source, request, decision = self.fixture(name='duplicate-key')
        self.record_decision(source, decision, request, aliases=('scoped.duplicate-decision',))
        with self.assertRaisesRegex(StudioError, 'bind one exact artifact'):
            prepare_reviewed_pattern_composition(source, request)

    def test_case_aliases_cannot_assign_the_same_file_to_two_review_roles(self):
        source, request, decision = self.fixture()
        decision['review_ref'] = copy.deepcopy(decision['proposal_ref'])
        decision['review_ref']['path'] = decision['review_ref']['path'].upper()
        atomic_json(source.root/'variants/scoped/decision.json', decision)
        source.evidence(request['decision_evidence_key'], 'variants/scoped/decision.json')
        source.gate(request['gate_name'], True, decision['statement'],
                    list(source.state()['gates'][request['gate_name']]['evidence']), decision['source_ref'])
        with self.assertRaisesRegex(StudioError, 'duplicate reference bindings'):
            prepare_reviewed_pattern_composition(source, request)

    def test_actual_final_or_fitting_gate_cannot_be_copied_as_pattern_review(self):
        source, request, decision = self.fixture()
        for name in ('final', 'fitting', 'generation'):
            scoped = dict(request, gate_name=name)
            self.record_decision(source, decision, scoped)
            with self.subTest(name=name), self.assertRaisesRegex(StudioError, 'only a scoped pattern-variant'):
                prepare_reviewed_pattern_composition(source, scoped)

    def test_gate_must_bind_all_four_reviewed_artifacts(self):
        source, request, decision = self.fixture()
        keys = list(source.state()['gates'][request['gate_name']]['evidence'])
        keys.remove('scoped.review')
        source.gate(request['gate_name'], True, decision['statement'], keys, decision['source_ref'])
        with self.assertRaisesRegex(StudioError, 'review_ref must bind'):
            prepare_reviewed_pattern_composition(source, request)

    def test_unreviewed_package_piece_or_material_change_is_rejected(self):
        for mode in ('front', 'material'):
            with self.subTest(mode=mode):
                source, request, decision = self.fixture(name='package-'+mode)
                directory = source.root/'variants/scoped/source'
                garment = read_json(directory/'garment.json')
                if mode == 'front': garment['pieces']['front']['position_cm'][0] += .01
                else: garment['material']['mass_kg'] += .01
                decision['variant_package_ref'] = self.write_package(source, directory, garment, 'invalid.garmentpkg')
                self.record_decision(source, decision, request)
                with self.assertRaises(StudioError): prepare_reviewed_pattern_composition(source, request)

    def test_manufacturing_dimensions_grain_and_cut_containment_are_enforced(self):
        for mode in ('dimensions', 'grain', 'cut'):
            with self.subTest(mode=mode):
                source, request, decision = self.fixture(name='manufacture-'+mode)
                path = source.root/decision['candidate_dossier_ref']['path']
                dossier = read_json(path); piece = dossier['components']['garment.coat']['pieces'][2]
                if mode == 'dimensions': piece['dimensions_cm'] = [21, 40]
                elif mode == 'grain': piece['grain_direction'] = [0, 0]
                else: piece['pattern']['cut_outline_cm'] = [[0, 0], [20, 0], [20, 40], [0, 40]]
                atomic_json(path, dossier); decision['candidate_dossier_ref']['sha256'] = sha(path)
                self.record_decision(source, decision, request)
                with self.assertRaises(StudioError): prepare_reviewed_pattern_composition(source, request)

    def test_copied_dependency_and_copied_human_gate_are_current(self):
        source, request, _, target = self.imported(name='copy-source')
        path = target.root/'variants/scoped/body.json'
        atomic_json(path, {'scope': 'CHANGED_NO_ADMISSION'})
        with self.assertRaisesRegex(StudioError, 'source file changed'):
            require_board(target, target.state())
        source, request, _, target = self.imported(name='copy-gate')
        with target.transaction() as db:
            state = target.state(db)
            state['gates'][request['gate_name']]['statement'] += ' changed'
            target.save(db, state, 'test_fixture_invalid_gate', {'scope': 'TEST_ONLY'})
        with self.assertRaisesRegex(StudioError, 'Copied pattern human gate differs'):
            require_board(target, target.state())

    def test_rehashed_output_dossier_still_must_equal_the_replayed_composition(self):
        _, _, _, target = self.imported()
        def corrupt(proof):
            path = target.root/proof['output']['dossier_ref']['path']
            dossier = read_json(path)
            dossier['components']['garment.coat']['pieces'][0]['pattern']['assembly_marks'][0]['position'] = math.nextafter(.3, 1)
            atomic_json(path, dossier)
            proof['output']['dossier_ref']['sha256'] = sha(path)
        self.change_proof(target, corrupt)
        with self.assertRaisesRegex(StudioError, 'output dossier differs'):
            require_board(target, target.state())

    def test_manifest_scope_codes_origin_and_package_inventory_are_not_trusted_flags(self):
        changes = {
            'scope': lambda p: p['reviewed_piece_ids'].append('front'),
            'codes': lambda p: p['code_producers'].update({'a3d/reviewed_pattern_admission.py': '0'*64}),
            'flags': lambda p: p.update(qualification='PASS', permission='GRANTED'),
            'origin': lambda p: p['origin'].update(kind='human'),
            'packages': lambda p: p['output']['packages']['garment.coat'].update(path='elsewhere.garmentpkg'),
        }
        for name, change in changes.items():
            with self.subTest(name=name):
                _, _, _, target = self.imported(name='proof-'+name)
                self.change_proof(target, change)
                with self.assertRaises(StudioError): require_board(target, target.state())

    def test_unregistered_or_malformed_proof_cannot_create_calculated_admission(self):
        for i, value in enumerate((None, [], {'kind': KIND, 'version': 1, 'origin': []},
                                   {'kind': KIND, 'version': True, 'origin': {'kind': 'calculated'}})):
            with self.subTest(i=i):
                _, _, _, target = self.imported(name='malformed-'+str(i))
                ref = target.state()['evidence'][KEY]
                atomic_json(target.root/ref['path'], value)
                target.evidence(KEY, ref['path'])
                with self.assertRaises(StudioError): require_board(target, target.state())

    def test_unrelated_revision_is_observed_only_but_evidence_reregistration_is_stale(self):
        source, request, _, target = self.imported()
        proof_before = sha(target.root/target.state()['evidence'][KEY]['path'])
        source.evidence('unrelated-note', '.a3d/evidence/brief.json')
        self.assertEqual(require_board(target, target.state())['kind'], KIND)
        self.assertEqual(sha(target.root/target.state()['evidence'][KEY]['path']), proof_before)
        source.evidence(request['decision_evidence_key'], 'variants/scoped/decision.json')
        with self.assertRaisesRegex(StudioError, 'Human review stale'):
            require_board(target, target.state())

    def test_nesting_is_refused_before_source_composition(self):
        _, request, _, target = self.imported()
        with self.assertRaisesRegex(StudioError, 'nesting is unsupported'):
            prepare_reviewed_pattern_composition(target, request)

    def test_duplicate_json_object_keys_are_not_silently_overwritten(self):
        source, request, decision = self.fixture()
        path = source.root/'variants/scoped/decision.json'
        raw = path.read_text(encoding='utf-8')
        path.write_text(raw.replace('"version": 1', '"version": 1, "version": 1'), encoding='utf-8')
        source.evidence(request['decision_evidence_key'], 'variants/scoped/decision.json')
        source.gate(request['gate_name'], True, decision['statement'],
                    list(source.state()['gates'][request['gate_name']]['evidence']), decision['source_ref'])
        with self.assertRaisesRegex(StudioError, 'finite unambiguous JSON'):
            prepare_reviewed_pattern_composition(source, request)

    def test_original_import_lineage_authenticates_generation_without_new_evidence_slot(self):
        parent, source, request, _ = self.inherited()
        before = sha(parent.db), sha(source.db)
        self.assertNotIn('exploded-image-request', source.state()['evidence'])
        result = prepare_reviewed_pattern_composition(source, request)
        origin = result['manifest_template']['generation_origin']
        self.assertEqual(origin['source_project'], str(parent.root))
        self.assertEqual(origin['request'], parent.state()['evidence']['exploded-image-request'])
        self.assertEqual(origin['receipt'], parent.state()['evidence']['exploded-image-generation'])
        self.assertEqual(origin['import_lineage'][0]['project'], str(source.root))
        self.assertEqual((sha(parent.db), sha(source.db)), before)
        target = Project.create(self.root/'inherited-target', source.state()['asset'])
        import_approved_design(target, source, pattern_variant=request)
        self.assertNotIn('exploded-image-request', target.state()['evidence'])
        self.assertEqual(require_board(target, target.state())['provenance']['generation_origin'], origin)
        self.assertEqual((sha(parent.db), sha(source.db)), before)

    def test_multi_import_human_lineage_lists_every_authenticated_database(self):
        parent = ready_project(self.root/'human-parent', True)
        middle = Project.create(self.root/'human-middle', parent.state()['asset'])
        import_approved_design(middle, parent)
        source = Project.create(self.root/'human-leaf', parent.state()['asset'])
        import_approved_design(source, middle)
        source, request, _ = self.fixture(source=source)
        before = [sha(project.db) for project in (source, middle, parent)]
        result = prepare_reviewed_pattern_composition(source, request)
        names = ('references', 'construction', 'route.garment.coat')
        for name in names:
            with self.subTest(name=name):
                origin = result['manifest_template']['base_decision_origins'][name]
                self.assertEqual(origin['project'], str(parent.root))
                self.assertEqual(origin['decision_id'], parent.state()['gates'][name]['decision_id'])
                self.assertEqual([row['project'] for row in origin['import_lineage']],
                                 [str(source.root), str(middle.root)])
                for project, row in zip((source, middle), origin['import_lineage']):
                    ref = project.state()['evidence']['approved-design-import']
                    self.assertEqual(row['import_ref'], {k: ref[k] for k in ('path', 'sha256')})
                    self.assertEqual(row['project_id'], project.state()['project_id'])
                    with closing(sqlite3.connect(project.db.as_uri()+'?mode=ro', uri=True)) as db:
                        kind, raw = db.execute('SELECT kind,doc FROM events WHERE id=?', (row['event_id'],)).fetchone()
                    self.assertEqual(kind, 'approved_design_context_imported')
                    self.assertEqual(json.loads(raw), read_json(project.root/ref['path']))
        self.assertEqual(result['manifest_template']['pattern_decision_origin']['import_lineage'], [])
        self.assertEqual([sha(project.db) for project in (source, middle, parent)], before)
        # A current intermediary approval change invalidates the whole replay.
        middle.gate('construction', False, 'SYNTHETIC intermediary revoked',
                    ['construction-board'], 'test:intermediary-revoked')
        with self.assertRaises(StudioError): prepare_reviewed_pattern_composition(source, request)

    def test_generation_parent_revoked_reregistered_or_missing_is_rejected(self):
        for mode in ('revoked', 'reregistered', 'missing'):
            with self.subTest(mode=mode):
                parent, source, request, _ = self.inherited(name='generation-'+mode)
                target = Project.create(self.root/('generation-'+mode+'-target'), source.state()['asset'])
                import_approved_design(target, source, pattern_variant=request)
                if mode == 'revoked':
                    parent.gate('construction', False, 'SYNTHETIC parent approval revoked',
                                ['construction-board'], 'test:parent-revoked')
                else:
                    ref = parent.state()['evidence']['exploded-image-request']
                    if mode == 'reregistered':
                        with patch('a3d.store.now', return_value='2099-01-01T00:00:00+00:00'):
                            parent.evidence('exploded-image-request', ref['path'])
                    else: (parent.root/ref['path']).unlink()
                with self.assertRaises((StudioError, OSError)):
                    require_board(target, target.state())

    def test_unrelated_parent_revision_does_not_stale_generation(self):
        parent, source, request, _ = self.inherited()
        target = Project.create(self.root/'inherited-target', source.state()['asset'])
        import_approved_design(target, source, pattern_variant=request)
        parent.evidence('unrelated-note', '.a3d/evidence/brief.json')
        self.assertEqual(require_board(target, target.state())['kind'], KIND)

    def test_fabricated_import_manifest_without_its_actual_event_is_rejected(self):
        _, source, request, _ = self.inherited()
        ref = source.state()['evidence']['approved-design-import']
        manifest = read_json(source.root/ref['path'])
        manifest['source_revision'] += 1
        atomic_json(source.root/ref['path'], manifest)
        source.evidence('approved-design-import', ref['path'])
        with self.assertRaisesRegex(StudioError, 'exact canonical design import'):
            prepare_reviewed_pattern_composition(source, request)

    def test_revocation_during_final_structure_validation_is_detected(self):
        source, request, decision, target = self.imported()
        from a3d.planning import _validate_dossier_structure
        changed = []
        def revoke_once(project, state, dossier, packages):
            result = _validate_dossier_structure(project, state, dossier, packages)
            if project.root == target.root and not changed:
                source.gate(request['gate_name'], False, 'SYNTHETIC revoked during replay',
                            [request['decision_evidence_key']], decision['source_ref'])
                changed.append(True)
            return result
        with patch('a3d.planning._validate_dossier_structure', side_effect=revoke_once):
            with self.assertRaises(StudioError): require_board(target, target.state())

    def test_unregistered_proof_and_producer_changes_do_not_get_legacy_fallback(self):
        _, _, _, target = self.imported()
        proof = target.state()['evidence'][KEY]
        with target.transaction() as db:
            state = target.state(db); state['evidence'].pop(KEY)
            target.save(db, state, 'test_fixture_unregistered_proof', {'scope': 'TEST_ONLY'})
        # Without the typed slot, the original board still binds old packages.
        with self.assertRaisesRegex(StudioError, 'no longer matches routes/packages'):
            require_board(target, target.state())
        target.evidence(KEY, proof['path'])
        from a3d.reviewed_pattern_admission import _codes
        changed = _codes(); changed['a3d/pattern_variant_composition.py'] = '0'*64
        with patch('a3d.reviewed_pattern_admission._codes', return_value=changed):
            with self.assertRaisesRegex(StudioError, 'authenticated replay'):
                require_board(target, target.state())
