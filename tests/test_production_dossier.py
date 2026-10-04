import copy
import tempfile
import unittest
from pathlib import Path

from a3d.core import StudioError, digest, read_json
from a3d.production_dossier import compile_production_dossier, compile_project_dossier
from tests.test_garment_planner import example as planner_example


def fixture():
    data = read_json(Path(__file__).parent/'fixtures/garment-coat/package/garment.json')
    for seam in data['seams']:
        seam['kind'] = 'permanent'
    ref = {'path': 'packages/coat.garmentpkg', 'sha256': 'a'*64}
    dossier = {'units': 'cm', 'components': {data['component_id']: {'pipeline': 'PATTERN_SEWN',
        'pieces': [{'id': pid, 'label': 'free prose never interpreted', 'grain_direction': [0, 1],
                    'pattern': {'cut_quantity': 1, 'assembly_marks': []}} for pid in data['pieces']]},
        'rigid.component': {'pipeline': 'MULTIVIEW_PART', 'pieces': [{'id': 'rigid-buckle'}]}}}
    packages = {data['component_id']: {'source_ref': ref, 'data': data}}
    old = planner_example(); source = old['source_ref']
    nodes = [{'id': 'body', 'kind': 'body', 'panels': [], 'colliders': ['body'], 'source_ref': source},
             {'id': 'cloth', 'kind': 'garment', 'panels': list(data['pieces']), 'colliders': [], 'source_ref': source}]
    spec = {'version': 1, 'source_ref': source, 'body_ref': old['body_ref'],
        'packages': [{'component_id': data['component_id'], 'source_ref': ref}],
        'piece_semantics': {pid: {'role': 'lining', 'side': 'center', 'layer': 'cloth'} for pid in data['pieces']},
        'layers': {'version': 1, 'source_ref': source, 'mode': 'ordered', 'interaction': 'one_way_declared',
                   'nodes': nodes, 'inside_to_outside': [['body', 'cloth']]},
        'budgets': old['budgets'],
        'measurement_paths': [{'id': 'source-edge-length', 'piece': 'front', 'edges': ['right'], 'purpose': 'source width'}]}
    return dossier, packages, spec


class ProductionDossier(unittest.TestCase):
    def test_complete_explicit_compilation_preserves_inventory_rigid_links_and_sources(self):
        dossier, packages, spec = fixture(); before = digest([dossier, packages, spec])
        report = compile_production_dossier(dossier, packages, spec)
        self.assertEqual(report['status'], 'READY_TO_PLAN')
        self.assertEqual(report['textile_count'], 4)
        self.assertEqual(report['rigid_count'], 1)
        self.assertNotIn('rigid-buckle', {p['id'] for p in report['assembly_spec']['pieces']})
        self.assertEqual(report['textiles']['front']['grain_direction'], [0, 1])
        self.assertTrue(all(link['kind'] == 'permanent' for link in report['links']))
        self.assertEqual(digest([dossier, packages, spec]), before)
        self.assertEqual(report['simulation'], 'NOT_EXECUTED')
        self.assertEqual(report['qualification'], 'NONE')

    def test_permuting_sets_keeps_identical_compiled_data(self):
        dossier, packages, spec = fixture()
        expected = compile_production_dossier(dossier, packages, spec)
        dossier['components']['garment.coat']['pieces'].reverse()
        packages['garment.coat']['data']['seams'].reverse()
        spec['layers']['nodes'].reverse()
        spec['layers']['nodes'][0]['panels'].reverse()
        self.assertEqual(compile_production_dossier(dossier, packages, spec), expected)

    def test_missing_semantics_never_inferred_from_front_or_buckle_names(self):
        dossier, packages, spec = fixture(); del spec['piece_semantics']['front']
        report = compile_production_dossier(dossier, packages, spec)
        self.assertEqual(report['status'], 'NEEDS_CLARIFICATION')
        self.assertIsNone(report['assembly_spec'])
        codes = {d['code'] for d in report['diagnostics'] if d.get('piece') == 'front'}
        self.assertEqual(codes, {'PIECE_ROLE_MISSING', 'PIECE_SIDE_MISSING', 'PIECE_LAYER_MISSING'})
        self.assertEqual(compile_production_dossier(dossier, packages)['textile_count'], 4)

    def test_bad_edges_mark_and_duplicate_permanent_seams_refused(self):
        for failure in ('edge', 'measurement', 'mark', 'duplicate', 'package', 'piece'):
            dossier, packages, spec = fixture()
            if failure == 'edge': spec['piece_semantics']['front']['guide_edges'] = {'anchor': 'invented'}
            if failure == 'measurement': spec['measurement_paths'][0]['edges'] = ['invented']
            if failure == 'mark': dossier['components']['garment.coat']['pieces'][0]['pattern']['assembly_marks'] = [{'id': 'x', 'seam_id': 'unknown', 'position': .5}]
            if failure == 'duplicate':
                seam = copy.deepcopy(packages['garment.coat']['data']['seams'][0]); seam['id'] = 'duplicate-owner'
                packages['garment.coat']['data']['seams'].append(seam)
            if failure == 'package': spec['packages'][0]['source_ref'] = {**spec['packages'][0]['source_ref'], 'sha256': 'b'*64}
            if failure == 'piece': dossier['components']['rigid.component']['pieces'][0]['id'] = 'front'
            with self.subTest(failure=failure), self.assertRaises(StudioError):
                compile_production_dossier(dossier, packages, spec)

    def test_center_inner_front_stays_exactly_one_piece_and_closure_is_preserved(self):
        dossier, packages, spec = fixture()
        spec['piece_semantics']['front']['role'] = 'inner_front'
        packages['garment.coat']['data']['seams'][0]['kind'] = 'closure'
        report = compile_production_dossier(dossier, packages, spec)
        self.assertEqual(len([p for p in report['assembly_spec']['pieces'] if p['role'] == 'inner_front']), 1)
        self.assertEqual(report['links'][2]['kind'], 'closure')
        self.assertEqual(report['textile_count'], 4)

    def test_project_wrapper_refuses_path_escape_or_changed_dossier_before_loading_packages(self):
        from a3d.core import atomic_json
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory)
            dossier, _, spec = fixture(); atomic_json(root/'dossier.json', dossier)
            atomic_json(root/'spec.json', spec)
            project = type('ProjectStub', (), {'root': root})()
            with self.assertRaisesRegex(StudioError, 'exact dossier'):
                compile_project_dossier(project, 'dossier.json', 'spec.json')
            with self.assertRaises(StudioError): compile_project_dossier(project, '../dossier.json', 'spec.json')


if __name__ == '__main__':
    unittest.main()
