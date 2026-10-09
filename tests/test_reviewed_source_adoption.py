"""Synthetic canonical adoption only; no Blender or product qualification."""
import copy
import json
from unittest.mock import patch

from a3d.core import StudioError, atomic_json, canonical, digest, read_json, sha
from a3d.planning import admission, package_records, require_board
from a3d.reviewed_pattern_revisions import prepare_project_reviewed_pattern_revision
from a3d.reviewed_source_adoption import adopt_reviewed_source_revision, KEY
from tests.test_core import Case
import tests.test_reviewed_pattern_revisions as revision_fixture


class ReviewedSourceAdoption(Case):
    def fixture(self):
        helper = revision_fixture.ReviewedPatternRevisions(); helper.root = self.root
        fixture = helper.fixture(); project, gate_name, roles, _ = fixture
        prepared = prepare_project_reviewed_pattern_revision(project, gate_name, roles, 'preparation/adoption-input')
        return project, gate_name, roles, prepared

    def adopt(self, fixture, request_key='fixture.adoption', expected=None):
        project, _, _, prepared = fixture
        return adopt_reviewed_source_revision(project, prepared['manifest_ref']['path'],
            expected if expected is not None else prepared['parent_source_epoch'], request_key)

    def test_adoption_is_current_canonical_replay_and_exact_idempotence(self):
        fixture = self.fixture(); project, _, _, prepared = fixture
        parent = copy.deepcopy(project.state())
        from a3d import reviewed_pattern_admission, pattern_variant_composition
        historical_producers = {module.__file__: sha(module.__file__) for module in (reviewed_pattern_admission, pattern_variant_composition)}
        before_files = {key: sha(project.root/row['path']) for key, row in parent['evidence'].items()}
        result = self.adopt(fixture)
        self.assertEqual(result['status'], 'REVIEWED_SOURCE_INPUTS_ADOPTED')
        current = project.state()
        self.assertEqual(current['source_epoch'], prepared['source_epoch'])
        self.assertNotEqual(current['components']['garment.coat']['package'], parent['components']['garment.coat']['package'])
        view = require_board(project, current)
        self.assertEqual(view['status'], 'REVIEWED_SOURCE_ADOPTION_VERIFIED')
        self.assertEqual(view['source_epoch'], prepared['source_epoch'])
        self.assertTrue(admission(project)['admitted'])
        self.assertEqual(result['qualification'], 'NONE')
        self.assertEqual(result['permission'], 'NOT_GRANTED')
        self.assertEqual(result['fitting'], 'NOT_GRANTED')
        for key, identity in before_files.items(): self.assertEqual(sha(project.root/parent['evidence'][key]['path']), identity)
        for path, identity in historical_producers.items(): self.assertEqual(sha(path), identity)
        before_retry = sha(project.db)
        self.assertEqual(result, self.adopt(fixture))
        self.assertEqual(sha(project.db), before_retry)
        with self.assertRaisesRegex(StudioError, 'different exact arguments'):
            self.adopt(fixture, expected='0'*64)

    def test_wrong_parent_epoch_refuses_without_canonical_changes(self):
        fixture = self.fixture(); before = sha(fixture[0].db)
        with self.assertRaisesRegex(StudioError, 'parent epoch'): self.adopt(fixture, expected='0'*64)
        self.assertEqual(before, sha(fixture[0].db))
        self.assertNotIn(KEY, fixture[0].state()['evidence'])

    def test_gate_revocation_and_effective_package_tamper_refuse_admission_replay(self):
        for failure in ['gate', 'package']:
            fixture = self.fixture(); project, gate, roles, _ = fixture
            self.adopt(fixture)
            if failure == 'gate': project.gate(gate, False, 'SYNTHETIC rejected later', list(roles.values()), 'test:revoke')
            else:
                package = project.root/project.state()['components']['garment.coat']['package']['path']
                package.write_bytes(package.read_bytes()+b'tampered')
            with self.subTest(failure=failure), self.assertRaises(StudioError): require_board(project, project.state())

    def test_parent_source_ancestor_revocation_refuses_replay(self):
        fixture = self.fixture(); project = fixture[0]; self.adopt(fixture)
        proof = read_json(project.root/project.state()['evidence']['reviewed-pattern-composition']['path'])
        from a3d.store import Project
        ancestor = Project(proof['origin']['source_project'])
        name = proof['request']['gate_name']; gate = ancestor.state()['gates'][name]
        ancestor.gate(name, False, 'SYNTHETIC revoked ancestor', list(gate['evidence']), 'test:ancestor-revoke')
        with self.assertRaises(StudioError): require_board(project, project.state())

    def test_active_work_and_pending_operation_refuse(self):
        for failure in ['pending', 'job', 'run']:
            fixture = self.fixture(); project = fixture[0]
            with project.transaction() as db:
                state = project.state(db)
                if failure == 'pending':
                    state['pending_blender_operation'] = {'operation': 'synthetic'}
                    project.save(db, state, 'synthetic_pending', {'test': True})
                elif failure == 'job':
                    db.execute('INSERT INTO jobs VALUES (?,?,?)', ('synthetic', 'synthetic', canonical({'status': 'running'}).decode()))
                else:
                    db.execute('CREATE TABLE runs (id TEXT PRIMARY KEY, request_key TEXT UNIQUE,doc TEXT NOT NULL)')
                    db.execute('INSERT INTO runs VALUES (?,?,?)', ('run.synthetic', 'synthetic', canonical({'run_id': 'run.synthetic', 'status': 'AWAITING_CONFIRMATION', 'units': []}).decode()))
            before = sha(project.db)
            with self.subTest(failure=failure), self.assertRaises(StudioError): self.adopt(fixture)
            self.assertEqual(before, sha(project.db))
            self.assertNotIn(KEY, project.state()['evidence'])

    def test_artifact_interruption_keeps_parent_active_and_retry_is_safe(self):
        fixture = self.fixture(); project = fixture[0]; parent = copy.deepcopy(project.state())
        original = atomic_json
        def interrupt(path, value):
            original(path, value)
            if str(path).endswith('manifest.json'): raise OSError('SYNTHETIC interruption before admission event')
        with patch('a3d.reviewed_source_adoption.atomic_json', interrupt):
            with self.assertRaises(OSError): self.adopt(fixture)
        self.assertEqual(parent, project.state())
        self.assertNotIn(KEY, project.state()['evidence'])
        self.assertEqual(require_board(project, project.state())['kind'], 'CALCULATED_SOURCE_COMPOSITION')
        result = self.adopt(fixture)
        self.assertEqual(result['status'], 'REVIEWED_SOURCE_INPUTS_ADOPTED')
        manifests = list((project.data/'evidence').glob('reviewed-source-adoption-*/manifest.json'))
        self.assertEqual(len(manifests), 2)

    def test_atomic_rollback_preserves_source_bindings_on_save_failure(self):
        fixture = self.fixture(); project = fixture[0]; parent = copy.deepcopy(project.state())
        original = project.save
        def save(db, state, kind, detail):
            original(db, state, kind, detail)
            if kind == 'reviewed_source_revision_adopted': raise RuntimeError('SYNTHETIC failure after event write')
        with patch.object(project, 'save', side_effect=save):
            with self.assertRaises(RuntimeError): self.adopt(fixture)
        self.assertEqual(parent, project.state())
        with project.transaction() as db:
            self.assertIsNone(db.execute("SELECT 1 FROM events WHERE kind='reviewed_source_revision_adopted'").fetchone())
        self.assertEqual(self.adopt(fixture)['status'], 'REVIEWED_SOURCE_INPUTS_ADOPTED')

    def test_dependent_evidence_and_runs_invalidate_while_body_history_stays(self):
        fixture = self.fixture(); project, _, _, prepared = fixture
        old_package = project.state()['components']['garment.coat']['package']
        evidence_file = project.root/'preparation/old-placement.json'
        atomic_json(evidence_file, {'package_sha256': old_package['sha256'], 'status': 'SYNTHETIC'})
        project.evidence('placement-result', 'preparation/old-placement.json')
        project.evidence('body.intrinsic', 'preparation/inputs/body.json')
        with project.transaction() as db:
            db.execute('CREATE TABLE runs (id TEXT PRIMARY KEY,request_key TEXT UNIQUE,doc TEXT NOT NULL)')
            run = {'run_id': 'run.old', 'request_key': 'synthetic', 'revision': 0, 'status': 'COMPLETED',
                   'units': [], 'inputs': [{'path': old_package['path'], 'sha256': old_package['sha256']}], 'qualification': 'NOT_GRANTED'}
            db.execute('INSERT INTO runs VALUES (?,?,?)', (run['run_id'], run['request_key'], canonical(run).decode()))
        result = self.adopt(fixture)
        self.assertEqual(result['invalidated_evidence_keys'], ['placement-result'])
        self.assertEqual(result['invalidated_run_ids'], ['run.old'])
        self.assertIn('body.intrinsic', project.state()['evidence'])
        self.assertTrue(evidence_file.exists())
        with project.transaction() as db:
            run = json.loads(db.execute("SELECT doc FROM runs WHERE id='run.old'").fetchone()[0])
            self.assertEqual(run['status'], 'COMPLETED')
            self.assertEqual(run['source_invalidation']['source_epoch'], prepared['source_epoch'])

    def test_transitive_two_level_json_dependency_invalidates_comfy_but_preserves_independent(self):
        fixture = self.fixture(); project = fixture[0]
        old_package = project.state()['components']['garment.coat']['package']
        b = project.root/'preparation/B.json'; atomic_json(b, {'source_ref': {'path': old_package['path'], 'sha256': old_package['sha256']}})
        a = project.root/'preparation/A.json'; atomic_json(a, {'input_ref': {'path': 'preparation/B.json', 'sha256': sha(b)}})
        independent = project.root/'preparation/independent.json'; atomic_json(independent, {'meaning': 'SYNTHETIC independent'})
        project.evidence('transitive-result', 'preparation/A.json')
        project.evidence('independent-result', 'preparation/independent.json')
        with project.transaction() as db:
            db.execute('CREATE TABLE runs (id TEXT PRIMARY KEY,request_key TEXT UNIQUE,doc TEXT NOT NULL)')
            for name, path in [('dependent', a), ('independent', independent)]:
                run = {'run_id': 'run.'+name, 'request_key': name, 'kind': 'comfy', 'revision': 0, 'status': 'COMPLETED',
                       'units': [{'status': 'COMPLETED', 'attempts': [], 'inputs': [
                           {'path': path.relative_to(project.root).as_posix(), 'sha256': sha(path)}]}], 'inputs': []}
                db.execute('INSERT INTO runs VALUES (?,?,?)', (run['run_id'], run['request_key'], canonical(run).decode()))
        result = self.adopt(fixture)
        self.assertEqual(result['invalidated_evidence_keys'], ['transitive-result'])
        self.assertEqual(result['invalidated_run_ids'], ['run.dependent'])
        self.assertIn('independent-result', project.state()['evidence'])
        with project.transaction() as db:
            independent_run = json.loads(db.execute("SELECT doc FROM runs WHERE id='run.independent'").fetchone()[0])
            self.assertNotIn('source_invalidation', independent_run)

    def test_invalidation_cycle_with_contradictory_hash_refuses_without_mutation(self):
        fixture = self.fixture(); project = fixture[0]
        a = project.root/'preparation/cycle.json'
        # A cryptographic self-reference cannot be authenticated by filling an
        # invented hash. Refuse the contradiction rather than looping or using
        # it to decide independence.
        atomic_json(a, {'input_ref': {'path': 'preparation/cycle.json', 'sha256': '0'*64}})
        project.evidence('cyclic-result', 'preparation/cycle.json')
        parent = copy.deepcopy(project.state())
        with self.assertRaisesRegex(StudioError, 'contradictory identity'): self.adopt(fixture)
        self.assertEqual(parent, project.state())
