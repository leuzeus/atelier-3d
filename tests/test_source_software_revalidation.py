"""Software changes never transfer design or physics acceptance implicitly."""
import copy
from unittest.mock import patch

from a3d.core import StudioError, sha
from a3d.planning import require_board
from a3d import reviewed_pattern_revisions as revisions
from a3d import reviewed_source_adoption as adoption
from tests.test_core import Case
import tests.test_reviewed_source_adoption as adoption_fixture


class SourceSoftwareRevalidation(Case):
    def fixture(self):
        helper = adoption_fixture.ReviewedSourceAdoption(); helper.root = self.root
        fixture = helper.fixture()
        helper.adopt(fixture)
        return fixture

    def upgraded(self):
        checker = adoption._codes(); checker[next(iter(checker))] = 'a'*64
        producer = revisions._codes(); producer['a3d/garment_guides.py'] = 'b'*64
        return checker, producer

    def test_changed_software_requires_fresh_attestation_and_exact_replay(self):
        project, _, _, _ = self.fixture()
        before = copy.deepcopy(project.state())
        checker, producer = self.upgraded()
        with patch.object(adoption, '_codes', return_value=checker), patch.object(revisions, '_codes', return_value=producer):
            with self.assertRaisesRegex(StudioError, 'studio_revalidate_source_adoption'):
                require_board(project, project.state())
            receipt = adoption.revalidate_source_adoption(project, 'preparation/software-v2')
            current = project.state()
            view = require_board(project, current)
            self.assertEqual(view['status'], 'REVIEWED_SOURCE_ADOPTION_VERIFIED')
            self.assertEqual(receipt['production_evidence'], 'NOT_REVALIDATED')
            self.assertEqual(receipt['permission'], 'NOT_GRANTED')
            self.assertEqual(receipt['revision_producers']['changed_paths'], ['a3d/garment_guides.py'])
            self.assertEqual(current['source_epoch'], before['source_epoch'])
            self.assertEqual(current['source_adoption'], before['source_adoption'])
            self.assertEqual(current['components'], before['components'])
            self.assertEqual(current['gates'], before['gates'])
            self.assertEqual({k:v for k,v in current['evidence'].items() if k != adoption.REVALIDATION_KEY}, before['evidence'])
            self.assertIn('software_revalidation_ref', view['provenance'])
            original = sha(project.root / before['evidence'][adoption.KEY]['path'])
            self.assertEqual(original, before['evidence'][adoption.KEY]['sha256'])
            newer = {**producer, 'a3d/garment_guides.py': 'c'*64}
            with patch.object(revisions, '_codes', return_value=newer):
                with self.assertRaisesRegex(StudioError, 'revalidation is stale'):
                    require_board(project, project.state())

    def test_recomputed_design_delta_is_not_a_software_only_change(self):
        project, _, _, _ = self.fixture()
        before = sha(project.db)
        original = revisions.calculate_reviewed_pattern_revision
        def changed(*args, **kwargs):
            result = original(*args, **kwargs)
            result['result']['reviewed_piece_ids'] = ['another-piece']
            return result
        with patch.object(revisions, 'calculate_reviewed_pattern_revision', side_effect=changed):
            with self.assertRaisesRegex(StudioError, 'differs from current authenticated replay'):
                adoption.revalidate_source_adoption(project, 'preparation/not-software')
        self.assertEqual(before, sha(project.db))
        self.assertFalse((project.root/'preparation/not-software').exists())

    def test_changed_effective_output_refuses_even_with_same_result_identity(self):
        project, _, _, _ = self.fixture()
        original = revisions.calculate_reviewed_pattern_revision
        def changed(*args, **kwargs):
            result = original(*args, **kwargs)
            result['dossier'] = {**result['dossier'], 'injected': True}
            return result
        with patch.object(revisions, 'calculate_reviewed_pattern_revision', side_effect=changed):
            with self.assertRaisesRegex(StudioError, 'prepared output differs'):
                adoption.revalidate_source_adoption(project, 'preparation/wrong-output')

    def test_removed_or_invalid_producer_is_not_silently_ignored(self):
        project, _, _, _ = self.fixture()
        current = revisions._codes()
        for value in (dict(list(current.items())[1:]), {**current, 'a3d/garment_guides.py': 'not-a-sha'}):
            with patch.object(revisions, '_codes', return_value=value):
                with self.assertRaisesRegex(StudioError, 'same valid producer inventory'):
                    adoption.revalidate_source_adoption(project, 'preparation/wrong-producer')

    def test_revoked_gate_still_refuses_after_attestation(self):
        project, gate, roles, _ = self.fixture()
        checker, producer = self.upgraded()
        with patch.object(adoption, '_codes', return_value=checker), patch.object(revisions, '_codes', return_value=producer):
            adoption.revalidate_source_adoption(project, 'preparation/software-v2')
            project.gate(gate, False, 'SYNTHETIC later revocation', list(roles.values()), 'test:revoke')
            with self.assertRaises(StudioError):
                require_board(project, project.state())

    def test_pending_operation_prevents_registration(self):
        project, _, _, _ = self.fixture()
        with project.transaction() as db:
            state = project.state(db); state['pending_blender_operation'] = {'operation': 'SYNTHETIC'}
            project.save(db, state, 'synthetic_pending', {})
        before = sha(project.db)
        with self.assertRaisesRegex(StudioError, 'pending Blender operation'):
            adoption.revalidate_source_adoption(project, 'preparation/active')
        self.assertEqual(before, sha(project.db))
        self.assertFalse((project.root/'preparation/active').exists())

    def test_interruption_preserves_orphan_but_no_admission(self):
        project, _, _, _ = self.fixture()
        checker, producer = self.upgraded()
        before = copy.deepcopy(project.state())
        with patch.object(adoption, '_codes', return_value=checker), patch.object(revisions, '_codes', return_value=producer):
            with patch.object(project, 'save', side_effect=OSError('SYNTHETIC registration failure')):
                with self.assertRaises(OSError):
                    adoption.revalidate_source_adoption(project, 'preparation/orphan')
            self.assertTrue((project.root/'preparation/orphan/revalidation.json').exists())
            self.assertEqual(before, project.state())
            with self.assertRaisesRegex(StudioError, 'studio_revalidate_source_adoption'):
                require_board(project, project.state())
            with self.assertRaisesRegex(StudioError, 'Preserve'):
                adoption.revalidate_source_adoption(project, 'preparation/orphan')
            adoption.revalidate_source_adoption(project, 'preparation/retry')
            self.assertEqual(require_board(project, project.state())['status'], 'REVIEWED_SOURCE_ADOPTION_VERIFIED')

    def test_unregistered_receipt_is_not_accepted_as_canonical_attestation(self):
        project, _, _, _ = self.fixture()
        checker, producer = self.upgraded()
        with patch.object(adoption, '_codes', return_value=checker), patch.object(revisions, '_codes', return_value=producer):
            adoption.revalidate_source_adoption(project, 'preparation/software-v2')
            with project.transaction() as db:
                db.execute("DELETE FROM events WHERE kind='reviewed_source_adoption_revalidated'")
            with self.assertRaisesRegex(StudioError, 'canonical event'):
                require_board(project, project.state())

    def test_public_tool_is_explicit_and_does_not_request_blender(self):
        from a3d.tools import TOOLS, call
        descriptor = TOOLS['studio_revalidate_source_adoption']['descriptor']
        self.assertFalse(descriptor['annotations']['readOnlyHint'])
        with patch('a3d.tools.Project', return_value='project'), patch.object(adoption, 'revalidate_source_adoption', return_value={'status': 'TEST_ONLY'}) as service:
            self.assertEqual(call('studio_revalidate_source_adoption', {'project_root': 'selected', 'output_dir': 'preparation/new'})['status'], 'TEST_ONLY')
            service.assert_called_once_with('project', 'preparation/new')

    def test_dependency_change_during_write_refuses_registration(self):
        project, _, _, _ = self.fixture()
        before = copy.deepcopy(project.state())
        original = adoption.atomic_json
        package = project.root / before['components']['garment.coat']['package']['path']
        def change_after_write(path, value):
            original(path, value)
            package.write_bytes(package.read_bytes() + b'SYNTHETIC change during write')
        with patch.object(adoption, 'atomic_json', side_effect=change_after_write):
            with self.assertRaises(StudioError):
                adoption.revalidate_source_adoption(project, 'preparation/racing-source')
        self.assertEqual(before, project.state())
        self.assertFalse(adoption._events(project, 'reviewed_source_adoption_revalidated'))
        self.assertTrue((project.root/'preparation/racing-source/revalidation.json').exists())

    def test_ancestor_is_reserved_while_attestation_is_written(self):
        import sqlite3
        project, _, _, _ = self.fixture()
        state = project.state()
        manifest = adoption._read(project, adoption._reference(state['evidence'][adoption.KEY]))
        snapshot = adoption._read(project, manifest['parent_snapshot_ref'])
        _, proof = adoption._parent_baseline(project, snapshot)
        ancestors = adoption._ancestor_roots(project, proof)
        self.assertTrue(ancestors)
        original = adoption.atomic_json
        def probe_reservations(path, value):
            for root in ancestors:
                with sqlite3.connect(root/'.a3d/state.sqlite3', timeout=0) as connection:
                    with self.assertRaisesRegex(sqlite3.OperationalError, 'locked'):
                        connection.execute('BEGIN IMMEDIATE')
            original(path, value)
        with patch.object(adoption, 'atomic_json', side_effect=probe_reservations):
            adoption.revalidate_source_adoption(project, 'preparation/reserved')
