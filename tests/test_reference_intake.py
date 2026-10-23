from a3d.core import StudioError, sha
from a3d.reference_intake import import_references
from tests.test_core import Case
from tests.support import ready_project


class ReferenceIntakeTests(Case):
    def test_reordered_sources_are_deterministic_and_immutable(self):
        project = ready_project(self.root)
        path = '.a3d/source/package/front.clean.png'
        rows = [{'id': name, 'path': path, 'sha256': sha(self.root/path), 'provenance': 'Synthetic test image'} for name in ('front', 'profile')]
        database = sha(project.db)
        first = import_references(project, self.root, rows)
        self.assertEqual(first, import_references(project, self.root, list(reversed(rows))))
        self.assertEqual(first['visual_review'], 'NOT_EXECUTED')
        self.assertEqual(database, sha(project.db))
        rows[0]['sha256'] = 'a'*64
        with self.assertRaises(StudioError): import_references(project, self.root, rows)

    def test_escape_and_duplicate_rejected(self):
        project = ready_project(self.root)
        row = {'id': 'front', 'path': '../outside.png', 'sha256': 'a'*64, 'provenance': 'Explicit'}
        with self.assertRaises(StudioError): import_references(project, self.root, [row])
