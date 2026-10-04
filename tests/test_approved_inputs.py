import shutil
import sqlite3
from contextlib import closing
from unittest.mock import patch
from a3d.approved_inputs import import_approved_design
from a3d.core import StudioError, atomic_json, read_json, sha
from a3d.planning import require_board
from a3d.store import Project
from a3d.tools import call, TOOLS
from tests.test_core import Case
from tests.support import ready_project


class ApprovedDesignTests(Case):
    def variant_fixture(self):
        from tests.test_reviewed_pattern_admission import ReviewedPatternAdmissionTests
        fixture = ReviewedPatternAdmissionTests()
        fixture.root = self.root
        return fixture.fixture()

    def test_public_scoped_import_keeps_original_decisions_and_uses_derived_inputs(self):
        source, request, decision = self.variant_fixture()
        before = sha(source.db)
        target = Project.create(self.root/'new', source.state()['asset'])
        result = call('studio_import_approved_design', {'project_root': str(target.root),
            'source_project_root': str(source.root), 'pattern_variant': request})
        self.assertEqual(result['status'], 'APPROVED_DESIGN_WITH_SCOPED_PATTERN_COMPOSITION_IMPORTED')
        self.assertEqual(sha(source.db), before)
        state = target.state()
        self.assertEqual(state['stage'], 'RECONSTRUCTING')
        for name in ('construction', request['gate_name']):
            self.assertEqual(state['gates'][name], source.state()['gates'][name])
        view = require_board(target, state)
        self.assertEqual(view['qualification'], 'NONE')
        self.assertEqual(view['permission'], 'NOT_GRANTED')
        self.assertEqual(view['image_scope'], 'BASE_DESIGN_ONLY_SCOPED_REVIEW_SEPARATE')
        self.assertNotEqual(view['dossier_path'], decision['original_dossier_ref']['path'])
        self.assertEqual(state['components']['garment.coat']['package']['sha256'],
                         decision['variant_package_ref']['sha256'])
        self.assertFalse(set(state['gates']) & {'final', 'fitting', 'artistic'})
        proof = read_json(target.root/state['evidence']['reviewed-pattern-composition']['path'])
        self.assertEqual(proof['origin']['kind'], 'calculated')
        self.assertEqual(proof['reviewed_piece_ids'], decision['piece_ids'])

    def test_reserved_composition_output_collision_is_refused_before_any_copy(self):
        source, request, _ = self.variant_fixture()
        target = Project.create(self.root/'new', source.state()['asset'])
        atomic_json(target.data/'evidence/reviewed-pattern-composition.json', {'existing': True})
        before = sha(target.db)
        with patch('a3d.approved_inputs.shutil.copyfile', side_effect=AssertionError('Unexpected copy')):
            with self.assertRaisesRegex(StudioError, 'fresh project'):
                import_approved_design(target, source, pattern_variant=request)
        self.assertEqual(target.state()['stage'], 'INIT')
        self.assertEqual(sha(target.db), before)

    def test_already_composed_source_is_refused_even_for_default_import_before_copy(self):
        source, request, _ = self.variant_fixture()
        composed = Project.create(self.root/'composed', source.state()['asset'])
        import_approved_design(composed, source, pattern_variant=request)
        target = Project.create(self.root/'new', source.state()['asset'])
        before = sha(target.db)
        with patch('a3d.approved_inputs.shutil.copyfile', side_effect=AssertionError('Unexpected copy')):
            with self.assertRaisesRegex(StudioError, 'Nested reviewed pattern composition'):
                import_approved_design(target, composed)
        self.assertEqual(sha(target.db), before)
        self.assertEqual(target.state()['stage'], 'INIT')

    def test_interrupted_copy_is_retained_and_cannot_be_blindly_resumed(self):
        source = ready_project(self.root/'source', True)
        target = Project.create(self.root/'new', source.state()['asset'])
        with patch('a3d.approved_inputs.shutil.copyfile', side_effect=OSError('SYNTHETIC copy interruption')):
            with self.assertRaises(OSError): import_approved_design(target, source)
        self.assertEqual(target.state()['stage'], 'INIT')
        self.assertFalse(target.state()['gates'])
        with patch('a3d.approved_inputs.shutil.copyfile', side_effect=AssertionError('Unexpected resume copy')):
            with self.assertRaisesRegex(StudioError, 'Partial design import cannot resume'):
                import_approved_design(target, source)

    def test_windows_case_alias_of_execution_dependency_is_refused_before_copy(self):
        source = ready_project(self.root/'source', True)
        target = Project.create(self.root/'new', source.state()['asset'])
        alias = '.A3D/BLENDER/historical-execution.json'
        atomic_json(source.root/alias, {'scope': 'SYNTHETIC_HISTORICAL_EXECUTION'})
        board_path = source.state()['evidence']['construction-board']['path']
        board = read_json(source.root/board_path)
        board['dependencies'][alias] = sha(source.root/alias)
        atomic_json(source.root/board_path, board)
        source.evidence('construction-board', board_path)
        source.gate('construction', True, 'SYNTHETIC reviewed board dependency',
                    ['construction-board'], 'test:case-alias-no-execution-transfer')
        with patch('a3d.approved_inputs.shutil.copyfile', side_effect=AssertionError('Unexpected copy')):
            with self.assertRaisesRegex(StudioError, 'candidate or execution state'):
                import_approved_design(target, source)
        self.assertEqual(target.state()['stage'], 'INIT')

    def test_public_import_tool_mutates_only_the_new_execution_context(self):
        source = ready_project(self.root/'source', True)
        target = Project.create(self.root/'new', source.state()['asset'])
        before = sha(source.db)
        result = call('studio_import_approved_design', {'project_root': str(target.root),
            'source_project_root': str(source.root)})
        self.assertEqual(result['status'], 'EXACT_APPROVED_DESIGN_IMPORTED')
        self.assertEqual(target.state()['stage'], 'RECONSTRUCTING')
        self.assertEqual(sha(source.db), before)
        self.assertFalse(TOOLS['studio_import_approved_design']['descriptor']['annotations']['readOnlyHint'])

    def test_import_tool_rejects_unbounded_variant_fields_before_project_access(self):
        with self.assertRaises(StudioError):
            call('studio_import_approved_design', {'project_root': 'absent', 'source_project_root': 'absent',
                'pattern_variant': {'gate_name': 'pattern-variant.test', 'decision_evidence_key': 'review',
                    'grant_fitting': True}})

    def test_only_exact_design_approval_survives_new_execution_context(self):
        source = ready_project(self.root/'source', True)
        source.evidence('old-fitting', '.a3d/evidence/brief.json')
        source.gate('final', True, 'SYNTHETIC historical acceptance', ['old-fitting'], 'test:old-final')
        before = sha(source.db)
        target = Project.create(self.root/'new', source.state()['asset'])
        manifest = import_approved_design(target, source)
        state = target.state()
        self.assertEqual(state['stage'], 'RECONSTRUCTING')
        self.assertEqual(state['gates']['construction'], source.state()['gates']['construction'])
        self.assertNotIn('final', state['gates']); self.assertNotIn('old-fitting', state['evidence'])
        self.assertEqual(manifest['candidate_receipts'], 'NOT_TRANSFERRED')
        self.assertEqual(sha(source.db), before)
        self.assertTrue(all('reconstruction' not in component for component in state['components'].values()))

    def test_changed_asset_or_source_file_never_grants_admission(self):
        source = ready_project(self.root/'source', True)
        asset = source.state()['asset']; asset['height_cm'] = 170
        target = Project.create(self.root/'changed', asset)
        with self.assertRaises(StudioError): import_approved_design(target, source)
        target = Project.create(self.root/'stale', source.state()['asset'])
        board = source.state()['evidence']['construction-board']['path']
        atomic_json(source.root/board, {'changed': True})
        with self.assertRaises(StudioError): import_approved_design(target, source)
        self.assertEqual(target.state()['stage'], 'INIT')

    def test_source_writer_cannot_revoke_approval_during_copy_or_admission(self):
        source = ready_project(self.root/'source', True)
        target = Project.create(self.root/'new', source.state()['asset'])
        before = sha(source.db)
        copyfile = shutil.copyfile; observed = []
        def inspect_reservation(src, dst):
            result = copyfile(src, dst)
            if not observed:
                with closing(sqlite3.connect(source.db, timeout=0)) as writer:
                    with self.assertRaisesRegex(sqlite3.OperationalError, 'locked'):
                        writer.execute('BEGIN IMMEDIATE')
                observed.append(True)
            return result
        with patch('a3d.approved_inputs.shutil.copyfile', side_effect=inspect_reservation):
            import_approved_design(target, source)
        self.assertTrue(observed)
        self.assertEqual(target.state()['stage'], 'RECONSTRUCTING')
        self.assertEqual(sha(source.db), before)
        with source.transaction(): pass  # Reservation released after the unit.

    def test_unrelated_source_revision_after_import_does_not_invalidate_design(self):
        source = ready_project(self.root/'source', True)
        target = Project.create(self.root/'new', source.state()['asset'])
        expected = source.state()['gates']['construction']
        import_approved_design(target, source)
        source.evidence('unrelated-note', '.a3d/evidence/brief.json')
        self.assertEqual(target.state()['stage'], 'RECONSTRUCTING')
        self.assertEqual(target.state()['gates']['construction'], expected)
        self.assertNotIn('unrelated-note', target.state()['evidence'])

    def test_re_registered_source_proof_before_import_makes_approval_stale(self):
        source = ready_project(self.root/'source', True)
        target = Project.create(self.root/'new', source.state()['asset'])
        record = source.state()['evidence']['construction-board']
        with patch('a3d.store.now', return_value='2099-01-01T00:00:00+00:00'):
            source.evidence('construction-board', record['path'])
        with patch('a3d.approved_inputs.shutil.copyfile', side_effect=AssertionError('Unexpected copy')):
            with self.assertRaisesRegex(StudioError, 'Human review stale'):
                import_approved_design(target, source)
        self.assertEqual(target.state()['stage'], 'INIT')
        self.assertFalse(target.state()['gates'])
        self.assertEqual(sha(source.root/record['path']), record['sha256'])
