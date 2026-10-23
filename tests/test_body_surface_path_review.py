"""Existing native-origin review operation with bounded OPEN exploration."""
import copy
import json
from pathlib import Path
import tempfile
import unittest
from unittest.mock import patch
import xml.etree.ElementTree as ET

from a3d import body_source_paths as module
from a3d import body_surface_paths as kernel
from a3d.core import ROOT, StudioError, atomic_json, canonical, digest, read_json, sha
from tests.test_body_source_paths import native_project, specification


def options():
    return {'version': 1, 'paths': [{'id': 'open.source-proposal', 'domain_region_ids': [41],
        'start': {'kind': 'source_vertex', 'vertex_id': 0}, 'end': {'kind': 'source_vertex', 'vertex_id': 1}}],
        'budgets': {'max_vertices': 10000, 'max_faces': 10000, 'max_edges': 100000,
            'max_visited': 1000, 'max_seconds': 1., 'max_paths': 4}, 'max_output_bytes': 512000}


def prepare(root, mutate=None):
    project, _ = native_project(root)
    spec = read_json(root/'specification.json'); spec['surface_exploration'] = options()
    if mutate is not None: mutate(spec)
    atomic_json(root/'specification.json', spec)
    return project, spec


class BodySurfacePathReview(unittest.TestCase):
    def test_native_operation_binds_its_own_source_report_and_blue_open_segments(self):
        with tempfile.TemporaryDirectory(dir=ROOT) as directory:
            root = Path(directory); project, spec = prepare(root)
            before = {p.name: sha(p) for p in root.iterdir() if p.is_file()}
            result = module.prepare_project_body_path_review(project, 'profile.json', 'specification.json', 'preparation/surface')
            self.assertEqual({name: sha(root/name) for name in before}, before)
            surface = result['report']['surface_exploration']
            source_ref = result['artifacts']['source-paths.json']
            self.assertEqual(surface['source_report_ref'], source_ref)
            self.assertEqual(surface['source_path_report_sha256'], {'source': source_ref['sha256']})
            self.assertEqual(source_ref['sha256'], digest(read_json(root/source_ref['path'])))
            self.assertEqual(surface['operation_native_body_origin']['event_id'], 1)
            self.assertEqual(surface['frame'], read_json(root/'profile.json')['frame'])
            self.assertEqual(surface, read_json(root/result['artifacts']['surface-paths.json']['path']))
            self.assertEqual(surface['shared_face_edge_incidences'], 72)
            self.assertEqual(surface['qualification'], 'NONE')
            self.assertEqual(surface['paths'][0]['tailoring_homology'], 'REVIEW_REQUIRED')
            self.assertEqual(surface['paths'][0]['vertex_ids'], [0, 1])
            self.assertEqual(surface['paths'][0]['smooth_geodesic_error_bound'], 'NOT_ESTABLISHED')
            board = ET.fromstring((root/result['artifacts']['surface-paths.svg']['path']).read_bytes())
            lines = board.findall('.//{http://www.w3.org/2000/svg}polyline')
            self.assertEqual(len(lines), 4)
            for line in lines:
                self.assertEqual(line.attrib['stroke'], '#0969da')
                self.assertEqual(line.attrib['data-closed'], 'false')
                self.assertEqual(len(line.attrib['points'].split()), 2)
            closed = (root/'preparation/surface/projections.svg').read_text()
            self.assertIn('stroke="#d12435"', closed)
            self.assertNotIn('data-closed="false"', closed)
            for ref in result['artifacts'].values(): self.assertEqual(sha(root/ref['path']), ref['sha256'])
            self.assertTrue((root/'preparation/surface/review-receipt.json').is_file())

    def test_old_no_option_keeps_its_artifact_inventory_and_report_shape(self):
        with tempfile.TemporaryDirectory(dir=ROOT) as directory:
            root = Path(directory); project, _ = native_project(root)
            result = module.prepare_project_body_path_review(project, 'profile.json', 'specification.json', 'preparation/old')
            self.assertEqual(set(result['artifacts']), {'report.json', 'report.md', 'projections.svg'})
            self.assertNotIn('surface_exploration', result['report'])
            self.assertNotIn('body_surface_paths', result['report']['measurement_code_sha256'])
            self.assertEqual(result['report']['paths'][0]['vertex_ids'], [0, 1, 2, 3])
            self.assertEqual(result['report']['paths'][0]['closed'], True)

    def test_options_require_operation_cycles_alias_source_all_budgets_and_display(self):
        base = specification(display=True); base['surface_exploration'] = options()
        selectors = [
            {'kind': 'boundary_extreme', 'report_id': 'other', 'path_id': 'source.neck-boundary', 'axis': 'up', 'extreme': 'max'},
            {'kind': 'boundary_extreme', 'report_id': 'source', 'path_id': 'missing', 'axis': 'up', 'extreme': 'max'},
            {'kind': 'world_point', 'point_world_cm': [1., 2., 3.]}]
        for selector in selectors:
            spec = copy.deepcopy(base); spec['surface_exploration']['paths'][0]['start'] = selector
            with self.subTest(selector=selector), self.assertRaises(StudioError): module.validate_specification(spec)
        for variant in ('cycles', 'display', 'budgets', 'seconds', 'output', 'path_budget', 'frame'):
            spec = copy.deepcopy(base)
            if variant == 'cycles': spec['paths'] = []
            elif variant == 'display': del spec['display']
            elif variant == 'budgets': del spec['surface_exploration']['budgets']['max_visited']
            elif variant == 'seconds': spec['surface_exploration']['budgets']['max_seconds'] = 16.
            elif variant == 'output': spec['surface_exploration']['max_output_bytes'] = 5*1024*1024
            elif variant == 'path_budget': spec['budgets']['max_paths'] = 1
            else: spec['surface_exploration']['frame'] = {'origin_cm': [1., 2., 3.]}
            with self.subTest(variant=variant), self.assertRaises(StudioError): module.validate_specification(spec)

    def test_absent_domain_uncycled_vertices_and_ambiguous_selector_refuse_before_publication(self):
        for variant in ('domain', 'vertex', 'selector'):
            def mutate(spec):
                path = spec['surface_exploration']['paths'][0]
                if variant == 'domain': path['domain_region_ids'] = [99]
                elif variant == 'vertex': path['end']['vertex_id'] = 4
                else: path['start'] = {'kind': 'boundary_extreme', 'report_id': 'source',
                    'path_id': 'source.neck-boundary', 'axis': 'up', 'extreme': 'max'}
            with tempfile.TemporaryDirectory(dir=ROOT) as directory:
                root = Path(directory); project, _ = prepare(root, mutate)
                before = sha(project.db)
                with self.subTest(variant=variant), self.assertRaises(StudioError):
                    module.prepare_project_body_path_review(project, 'profile.json', 'specification.json', 'preparation/refused')
                self.assertFalse((root/'preparation/refused').exists())
                self.assertEqual(sha(project.db), before)

    def test_stale_pose_or_profile_refuses_before_solver_and_preserves_native_journal(self):
        for name in ('geometry.json', 'profile.json'):
            with tempfile.TemporaryDirectory(dir=ROOT) as directory:
                root = Path(directory); project, _ = prepare(root)
                document = read_json(root/name); document['pose_sha256'] = 'f'*64; atomic_json(root/name, document)
                before = sha(project.db)
                with patch.object(kernel, 'propose_body_surface_paths') as solve, self.assertRaises(StudioError):
                    module.prepare_project_body_path_review(project, 'profile.json', 'specification.json', 'preparation/stale')
                solve.assert_not_called()
                self.assertFalse((root/'preparation/stale').exists())
                self.assertEqual(sha(project.db), before)

    def test_solver_and_diagram_share_one_surface_deadline(self):
        with tempfile.TemporaryDirectory(dir=ROOT) as directory:
            root = Path(directory); project, _ = prepare(root)
            now = [0.]; solve = kernel.propose_body_surface_paths; render = module._projection_board
            def computation(*args, **kwargs):
                result = solve(*args, **kwargs); now[0] = .6; return result
            def diagram(*args, **kwargs):
                result = render(*args, **kwargs)
                if kwargs.get('open_paths'): now[0] = 1.1
                return result
            with patch.object(module.time, 'monotonic', side_effect=lambda: now[0]), \
                    patch.object(kernel, 'propose_body_surface_paths', side_effect=computation), \
                    patch.object(module, '_projection_board', side_effect=diagram), self.assertRaisesRegex(StudioError, 'cumulative'):
                module.prepare_project_body_path_review(project, 'profile.json', 'specification.json', 'preparation/expired')
            self.assertFalse((root/'preparation/expired').exists())

    def test_source_snapshot_serialization_is_inside_surface_deadline_before_solver_or_publication(self):
        with tempfile.TemporaryDirectory(dir=ROOT) as directory:
            root = Path(directory); project, _ = prepare(root)
            now = [0.]; encode = module.canonical
            def snapshot_serialization(value):
                result = encode(value)
                if isinstance(value, dict) and value.get('status') == 'BODY_SOURCE_PATHS_MEASURED_FOR_REVIEW':
                    now[0] = 1.1
                return result
            with patch.object(module.time, 'monotonic', side_effect=lambda: now[0]), \
                    patch.object(module, 'canonical', side_effect=snapshot_serialization), \
                    patch.object(kernel, 'propose_body_surface_paths') as solve, self.assertRaisesRegex(StudioError, 'cumulative'):
                module.prepare_project_body_path_review(project, 'profile.json', 'specification.json', 'preparation/snapshot-expired')
            solve.assert_not_called()
            self.assertFalse((root/'preparation/snapshot-expired').exists())

    def test_parent_read_and_source_measurement_time_is_not_reset_by_surface_solver(self):
        with tempfile.TemporaryDirectory(dir=ROOT) as directory:
            root = Path(directory); project, spec = prepare(root)
            spec['budgets']['max_seconds'] = 1.; atomic_json(root/'specification.json', spec)
            now = [0.]; measure = module.measure_source_body_paths
            def source_measurement(*args, **kwargs):
                result = measure(*args, **kwargs); now[0] = 1.1; return result
            with patch.object(module.time, 'monotonic', side_effect=lambda: now[0]), \
                    patch.object(module, 'measure_source_body_paths', side_effect=source_measurement), \
                    patch.object(kernel, 'propose_body_surface_paths') as solve, self.assertRaisesRegex(StudioError, 'time budget'):
                module.prepare_project_body_path_review(project, 'profile.json', 'specification.json', 'preparation/expired')
            solve.assert_not_called()
            self.assertFalse((root/'preparation/expired').exists())

    def test_added_graph_scan_charges_shared_geometry_budget_and_output_cap_covers_bundle(self):
        for variant in ('edges', 'output'):
            def mutate(spec):
                if variant == 'edges':
                    spec['budgets']['max_face_edges'] = 60
                    spec['surface_exploration']['budgets']['max_edges'] = 60
                else: spec['surface_exploration']['max_output_bytes'] = 1
            with tempfile.TemporaryDirectory(dir=ROOT) as directory:
                root = Path(directory); project, _ = prepare(root, mutate)
                with self.subTest(variant=variant), self.assertRaisesRegex(StudioError, 'budget'):
                    module.prepare_project_body_path_review(project, 'profile.json', 'specification.json', 'preparation/bounded')
                self.assertFalse((root/'preparation/bounded').exists())

    def test_final_marker_storage_or_surface_deadline_failure_preserves_reports_without_complete_marker(self):
        for variant in ('storage', 'after_hash', 'publication'):
            with tempfile.TemporaryDirectory(dir=ROOT) as directory:
                root = Path(directory); project, spec = prepare(root)
                marker = root/'preparation/interrupted/review-receipt.json'; now = [0.]
                real_sha = module.sha; real_canonical = module.canonical; real_preserve = module._Reader.preserve; checks = [0]
                def late_hash(path):
                    result = real_sha(path)
                    if variant == 'after_hash' and Path(path) == marker: now[0] = 1.1
                    return result
                def marker_storage(value):
                    result = real_canonical(value)
                    if variant == 'storage' and isinstance(value, dict) and value.get('status') == 'BODY_SOURCE_PATH_REVIEW_PREPARED':
                        return result+b' '*spec['surface_exploration']['max_output_bytes']
                    return result
                def publication(reader):
                    result = real_preserve(reader); checks[0] += 1
                    if variant == 'publication' and checks[0] == 2: now[0] = 1.1
                    return result
                with patch.object(module.time, 'monotonic', side_effect=lambda: now[0]), \
                        patch.object(module, 'sha', side_effect=late_hash), \
                        patch.object(module, 'canonical', side_effect=marker_storage), \
                        patch.object(module._Reader, 'preserve', publication), self.subTest(variant=variant), self.assertRaises(StudioError):
                    module.prepare_project_body_path_review(project, 'profile.json', 'specification.json', 'preparation/interrupted')
                self.assertFalse(marker.exists())
                for name in ('source-paths.json', 'surface-paths.json', 'surface-paths.svg', 'report.json'):
                    self.assertTrue((marker.parent/name).is_file())

    def test_opening_and_surface_explorations_keep_independent_options_and_provenance(self):
        with tempfile.TemporaryDirectory(dir=ROOT) as directory:
            root = Path(directory); project, _ = prepare(root, lambda spec: spec.update(opening_exploration={
                'path_id': 'source.neck-boundary', 'reference_plane': 'BODY_SAGITTAL',
                'front_anchor': 'UNIQUE_FRONTMOST_INTERSECTION', 'max_pairs': 1, 'max_seconds': 2., 'max_output_bytes': 512000}))
            result = module.prepare_project_body_path_review(project, 'profile.json', 'specification.json', 'preparation/both')
            self.assertIn('opening-options.svg', result['artifacts'])
            self.assertIn('surface-paths.svg', result['artifacts'])
            self.assertEqual(result['report']['surface_exploration']['source_path_report_sha256']['source'],
                             result['artifacts']['source-paths.json']['sha256'])


if __name__ == '__main__':
    unittest.main()
