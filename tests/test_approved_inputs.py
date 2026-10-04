from a3d.approved_inputs import import_approved_design
from a3d.core import StudioError, atomic_json, sha
from a3d.store import Project
from tests.test_core import Case
from tests.support import ready_project


class ApprovedDesignTests(Case):
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
