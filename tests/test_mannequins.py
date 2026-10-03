import copy
import shutil
from pathlib import Path
from types import SimpleNamespace
from unittest.mock import patch

from a3d.core import ROOT, StudioError, atomic_json, read_json, sha
from a3d.mannequins import catalog, distribution_files, select_catalog_body
from scripts.package_plugin import DIRS, ROOT_FILES, inventory
from tests.test_core import Case


class Mannequins(Case):
    def fixture(self):
        for name in ROOT_FILES:
            (self.root/name).write_text('fixture', encoding='utf-8')
        for name in DIRS:
            (self.root/name).mkdir(exist_ok=True)
        shutil.copytree(ROOT/'assets/mannequins', self.root/'assets/mannequins')
        return self.root/'assets/mannequins/catalog.json'

    def test_catalog_has_real_sources_dimensions_readiness_and_no_sex_inference(self):
        result = catalog()
        self.assertEqual({e['label'] for e in result['entries']}, {'Homme', 'Femme'})
        self.assertEqual(len(distribution_files()), 2)
        for entry in result['entries']:
            self.assertEqual(entry['license'], 'CC0-1.0')
            self.assertGreater(entry['stature_cm'], 150.)
            self.assertLess(entry['stature_cm'], 200.)
            self.assertIn('blender.org', entry['source_url'])
            self.assertIn('pipeline_ready', entry)

    def test_package_only_includes_two_allowed_blends(self):
        self.fixture()
        (self.root/'personal.blend').write_bytes(b'private scene')
        (self.root/'assets/mannequins/personal.blend').write_bytes(b'private scene')
        (self.root/'tests/private.blend').write_bytes(b'private scene')
        (self.root/'config.local.json').write_text('private config')
        included = inventory(self.root)
        blends = [p for p in included if p.suffix == '.blend']
        self.assertEqual(set(blends), set(distribution_files(self.root)))
        self.assertEqual(len(blends), 2)
        self.assertFalse(any(p.name == 'config.local.json' for p in included))

    def test_byte_mutation_notice_mutation_license_and_personal_scene_are_refused(self):
        path = self.fixture(); original = read_json(path)
        for failure in ['bytes', 'notice', 'license', 'path', 'adapter', 'unqualified_ready']:
            data = copy.deepcopy(original)
            target = None; before = None
            if failure == 'bytes': target = path.parent/data['entries'][0]['file']
            if failure == 'notice': target = path.parent/'NOTICE-CC0.md'
            if failure == 'adapter': target = path.parent/data['entries'][0]['anatomy_adapter']
            if target:
                before = target.read_bytes(); target.write_bytes(before+b'changed')
            if failure == 'license': data['entries'][0]['license'] = 'unknown'
            if failure == 'path': data['entries'][0]['file'] = '../personal.blend'
            if failure == 'unqualified_ready': data['entries'][0]['pipeline_ready'] = True
            atomic_json(path, data)
            try:
                with self.subTest(failure=failure), self.assertRaises(StudioError):
                    catalog(self.root)
            finally:
                if target: target.write_bytes(before)
                atomic_json(path, original)

    def test_project_copy_preserves_source_previous_selections_and_native_descriptor(self):
        entry = catalog()['entries'][0]; source = ROOT/'assets/mannequins'/entry['file']
        before = sha(source); project = SimpleNamespace(root=self.root)
        first = select_catalog_body(project, entry['id']); second = select_catalog_body(project, entry['id'])
        self.assertNotEqual(first['selection']['path'], second['selection']['path'])
        self.assertEqual(sha(source), before)
        descriptor = read_json(self.root/first['selection']['path'])
        self.assertEqual(sha(self.root/descriptor['source_blend']), before)
        self.assertEqual(descriptor['meshes'], entry['meshes'])
        adapter = read_json(self.root/first['anatomy_adapter']['path'])
        self.assertEqual(adapter['source_ref'], first['source'])
        self.assertEqual(sha(self.root/first['anatomy_adapter']['path']), first['anatomy_adapter']['sha256'])
        self.assertEqual(first['qualification'], 'NONE')
        self.assertEqual(first['status'], 'BODY_SELECTED_NOT_EVALUATED')

    def test_missing_catalog_does_not_invent_bases_or_hide_import_options(self):
        result = catalog(self.root)
        self.assertEqual(result['status'], 'UNAVAILABLE')
        self.assertEqual(len(result['additional_choices']), 2)
        self.assertEqual(distribution_files(self.root), [])
