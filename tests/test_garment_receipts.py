from types import SimpleNamespace
from unittest.mock import patch

from a3d.core import read_json, sha
from a3d.garment_receipts import write_receipt
from a3d.store import Project
from tests.support import asset
from tests.test_core import Case


class GarmentReceiptTests(Case):
    def test_components_and_repeated_operations_keep_separate_immutable_receipts(self):
        project = Project.create(self.root, asset(True))
        historical = project.data / 'blender/garment-receipt.json'
        historical.write_bytes(b'original legacy evidence')
        refs = [write_receipt(project, cid, fingerprint, {'object': 'A3D.' + cid})
                for cid, fingerprint in (('garment.coat', 'a' * 64), ('garment.belt', 'b' * 64),
                                         ('garment.coat', 'c' * 64))]
        self.assertEqual(len({ref['path'] for ref in refs}), 3)
        for ref, cid, package in zip(refs, ('garment.coat', 'garment.belt', 'garment.coat'),
                                      ('a' * 64, 'b' * 64, 'c' * 64), strict=True):
            path = project.root / ref['path']
            self.assertEqual(sha(path), ref['sha256'])
            record = read_json(path)
            self.assertEqual(record['component_id'], cid)
            self.assertEqual(record['package_sha256'], package)
            self.assertEqual(record['operation'], 'garment')
            self.assertEqual(record['result']['object'], 'A3D.' + cid)
        self.assertEqual(historical.read_bytes(), b'original legacy evidence')

    def test_uuid_collision_never_overwrites_an_existing_receipt(self):
        project = Project.create(self.root, asset(True))
        with patch('a3d.garment_receipts.uuid.uuid4', return_value=SimpleNamespace(hex='fixed')):
            ref = write_receipt(project, 'garment.coat', 'a' * 64, {'object': 'original'})
            with self.assertRaises(FileExistsError):
                write_receipt(project, 'garment.coat', 'b' * 64, {'object': 'replacement'})
        self.assertEqual(sha(project.root / ref['path']), ref['sha256'])

    def test_component_path_cannot_escape_receipt_storage(self):
        project = Project.create(self.root, asset(True))
        from a3d.core import StudioError
        with self.assertRaises(StudioError):
            write_receipt(project, '../outside', 'a' * 64, {})
