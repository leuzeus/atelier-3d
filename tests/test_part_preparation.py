import json
import struct
from types import SimpleNamespace
from unittest.mock import patch

from a3d.core import StudioError, atomic_json
from a3d.part_preparation import embedded_glb, dimension_proposal, glb_topology_budget, part_descriptor, calibrate_geometry
from tests.test_core import Case


def glb(document):
    data = json.dumps(document).encode(); data += b' '*((-len(data)) % 4)
    return b'glTF'+struct.pack('<II', 2, 20+len(data))+struct.pack('<II', len(data), 0x4e4f534a)+data


class PartPreparationTests(Case):
    def test_dimension_calibration_preserves_source_topology_and_refuses_large_aspect_change(self):
        geometry = {'mesh': {'vertices_cm': [[-100, -12, -100], [100, 12, 100], [-100, 12, 100]], 'faces': [[0, 1, 2]]}}
        transformed, record = calibrate_geometry(geometry, [7.2, 6.8, .7], .2)
        self.assertEqual(transformed['mesh']['faces'], geometry['mesh']['faces'])
        self.assertEqual(geometry['mesh']['vertices_cm'][0], [-100, -12, -100])
        self.assertFalse(record['body_changed'])
        for observed, expected in zip(transformed['mesh']['vertices_cm'][0], [-3.6, -.35, -3.4], strict=True):
            self.assertAlmostEqual(observed, expected, places=10)
        with self.assertRaises(StudioError): calibrate_geometry(geometry, [7.2, 6.8, .1], .2)
    def test_embedded_static_source_and_dimension_proposal_preserve_shape(self):
        path = self.root/'source.glb'; path.write_bytes(glb({'asset': {'version': '2.0'}, 'buffers': [{'byteLength': 0}]}))
        self.assertEqual(embedded_glb(path, 1000)['asset']['version'], '2.0')
        proposal = dimension_proposal([72, 68, 7], [7.2, 6.8, .7])
        self.assertAlmostEqual(proposal['factor'], .1)
        self.assertFalse(proposal['applied'])

    def test_external_resource_and_skinning_are_refused_before_import(self):
        path = self.root/'source.glb'
        for extras in ({'images': [{'uri': '../private.png'}]}, {'skins': [{}]}, {'animations': [{}]}):
            path.write_bytes(glb({'asset': {'version': '2.0'}, **extras}))
            with self.assertRaises(StudioError): embedded_glb(path, 1000)

    def test_file_budget_and_degenerate_extent_are_refused(self):
        path = self.root/'source.glb'; path.write_bytes(glb({'asset': {'version': '2.0'}}))
        with self.assertRaises(StudioError): embedded_glb(path, 20)
        with self.assertRaises(StudioError): dimension_proposal([1, 0, 1], [1, 1, 1])

    def test_import_budget_counts_instances_and_rejects_excess_before_import(self):
        document = {'buffers': [{'byteLength': 60}],
                    'bufferViews': [{'buffer': 0, 'byteLength': 48}, {'buffer': 0, 'byteOffset': 48, 'byteLength': 12}],
                    'accessors': [{'bufferView': 0, 'componentType': 5126, 'count': 4, 'type': 'VEC3'},
                                  {'bufferView': 1, 'componentType': 5123, 'count': 6, 'type': 'SCALAR'}],
                    'meshes': [{'primitives': [{'attributes': {'POSITION': 0}, 'indices': 1}]}], 'nodes': [{'mesh': 0}]}
        budgets = {'max_vertices': 4, 'max_faces': 2}
        self.assertEqual(glb_topology_budget(document, [60], budgets), {'vertices': 4, 'faces': 2})
        document['nodes'].append({'mesh': 0})
        with self.assertRaises(StudioError): glb_topology_budget(document, [60], budgets)
        document['nodes'].pop(); document['accessors'][0]['count'] = 1000000
        with self.assertRaises(StudioError): glb_topology_budget(document, [60], budgets)

    def test_same_asset_alternate_dossier_cannot_replace_approved_dimensions(self):
        package = {'path': 'rigid.partpkg', 'sha256': 'a'*64}
        profile = {'version': 1, 'component_id': 'rigid', 'piece_id': 'piece', 'job_id': 'owned',
                   'package_ref': package, 'source_ref': {'path': 'source.glb', 'sha256': 'b'*64},
                   'dossier_ref': {'path': 'alternative.json', 'sha256': 'c'*64},
                   'budgets': {'max_file_bytes': 1000, 'max_vertices': 100, 'max_faces': 100, 'max_seconds': 10}}
        atomic_json(self.root/'profile.json', profile)
        project = SimpleNamespace(root=self.root, state=lambda: {'asset': {'id': 'same-asset'}},
            ready=lambda _: ({}, {'route': {'selected': 'MULTIVIEW_PART'}, 'package': package}))
        with patch('a3d.planning.require_board', return_value={
                'dossier_path': 'approved.json', 'dependencies': {'approved.json': 'd'*64}}):
            with self.assertRaisesRegex(StudioError, 'exact approved construction board'):
                part_descriptor(project, 'profile.json')
