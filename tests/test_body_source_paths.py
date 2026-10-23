"""Portable source-interface probes; no anatomical or native acceptance."""
import copy
import json
import math
import sqlite3
import tempfile
import unittest
from contextlib import closing
from pathlib import Path
from types import SimpleNamespace
from unittest.mock import patch

from a3d.body_source_paths import (measure_source_body_paths,
    prepare_project_body_path_review, validate_specification)
from a3d.core import ROOT, StudioError, atomic_json, digest, read_json, sha


def specification(display=False):
    result = {'version': 1, 'paths': [{'id': 'source.neck-boundary', 'source_joint': 'neck.base',
                                     'display_name': 'Frontière source cou/torse'}],
              'budgets': {'max_read_bytes': 64*1024*1024, 'max_vertices': 10000,
                  'max_faces': 10000, 'max_face_edges': 100000, 'max_paths': 4,
                  'max_boundary_edges': 1000, 'max_evidence_files': 64,
                  'max_native_receipts': 64, 'max_output_bytes': 4*1024*1024,
                  'max_seconds': 15.}}
    if display: result['display'] = {'max_faces': 100, 'width_px': 1000, 'height_px': 1000}
    return result


def fixture():
    # A nonplanar ring between regions 41 and 67; deliberately no fixed 1/17.
    vertices = [[-10., -10., 80.], [10., -10., 82.], [10., 10., 80.],
                [-10., 10., 82.], [0., 0., 0.], [0., 0., 180.]]
    faces = [[4, (i+1)%4, i] for i in range(4)]+[[5, i, (i+1)%4] for i in range(4)]
    geometry = {'vertices_cm': vertices, 'faces': faces, 'face_sets': [41]*4+[67]*4,
                'source_sha256': 'a'*64, 'pose_sha256': 'b'*64, 'rig_landmarks': {}}
    original = copy.deepcopy(geometry)
    basis = {'origin_cm': [0., 0., 0.], 'right': [1., 0., 0.],
             'forward': [0., 1., 0.], 'up': [0., 0., 1.]}
    profile = {'source_sha256': geometry['source_sha256'], 'pose_sha256': geometry['pose_sha256'],
        'geometry_sha256': digest([vertices, faces]), 'options_sha256': digest(basis),
        'rig_landmarks_sha256': digest({}), 'frame': basis,
        'landmarks': {'neck': {'girth_cm': 80., 'section': {'status': 'MEASURED', 'height_cm': 90.}}}}
    profile['cache_key'] = digest({key: profile[key] for key in
        ('source_sha256', 'pose_sha256', 'geometry_sha256', 'options_sha256', 'rig_landmarks_sha256')})
    adapter = {'source_ref': {'path': 'source.blend', 'sha256': 'a'*64},
        'source_geometry_sha256': digest([vertices, faces, geometry['face_sets']]),
        'joints': {'neck.base': [41, 67]}, 'torso_regions': [41]}
    return profile, geometry, original, adapter, specification()


def rebind(values):
    profile, geometry, original, adapter, _ = values
    original['faces'] = copy.deepcopy(geometry['faces']); original['face_sets'] = copy.deepcopy(geometry['face_sets'])
    original['vertices_cm'] = copy.deepcopy(geometry['vertices_cm'])
    profile['geometry_sha256'] = digest([geometry['vertices_cm'], geometry['faces']])
    profile['cache_key'] = digest({key: profile[key] for key in
        ('source_sha256', 'pose_sha256', 'geometry_sha256', 'options_sha256', 'rig_landmarks_sha256')})
    adapter['source_geometry_sha256'] = digest([original['vertices_cm'], original['faces'], original['face_sets']])


def native_project(root):
    """Synthetic canonical journal fixture, never proof of a real Blender run."""
    from tests.test_body_target import target_fixture
    values = list(fixture()); profile, geometry, original, adapter, spec = values
    source = root/'source.blend'; source.write_bytes(b'SYNTHETIC_BODY_SOURCE_ONLY')
    for body in (geometry, original): body['source_sha256'] = sha(source)
    profile['source_sha256'] = sha(source); adapter['source_ref']['sha256'] = sha(source)
    rebind(values)
    selected = {'version': 1, 'source_blend': 'source.blend', 'source_sha256': sha(source),
                'source_ref': 'EXPLICIT_SYNTHETIC_IDENTITY_FIXTURE', 'frame': 1, 'unit_scale_m': 1.,
                'meshes': ['source'], 'dependencies': [], 'reference_object': 'source'}
    atomic_json(root/'selection.json', selected); atomic_json(root/'anatomy.json', adapter)
    atomic_json(root/'target.json', target_fixture(sha(root/'selection.json'), sha(root/'anatomy.json')))
    derivation = {'source_geometry_sha256': digest([original['vertices_cm'], original['faces']]),
                  'source_sha256': geometry['source_sha256'], 'source_pose_sha256': original['pose_sha256']}
    geometry['dimension_derivation'] = copy.deepcopy(derivation)
    artifact = root/'body.blend'; artifact.write_bytes(b'SYNTHETIC_NOT_NATIVE_GEOMETRY')
    artifacts = {}
    for name, value in [('profile', profile), ('geometry', geometry), ('source-geometry', original),
                        ('options', profile['frame']),
                        ('derivation', {'version': 1, 'status': 'BODY_TARGET_MEASURED', 'stature_derivation': derivation}),
                        ('triangles', geometry['faces'])]:
        atomic_json(root/(name+'.json'), value)
        artifacts[name] = {'path': name+'.json', 'sha256': sha(root/(name+'.json'))}
    receipt = {'status': 'NATIVE_BODY_TARGET_MEASURED', 'native_reopened': True,
        'source_face_ids_preserved': True, 'topology_preserved': True, 'adapter_rebound_to_variant': False,
        'geometry_sha256': profile['geometry_sha256'], 'pose_sha256': profile['pose_sha256'],
        'profile_cache_key': profile['cache_key'], 'stature_derivation': derivation,
        'anatomy_adapter_sha256': digest(adapter), 'artifacts': artifacts,
        'artifact': {'path': 'body.blend', 'sha256': sha(artifact)},
        'evidence': {'selection': {'path': 'selection.json', 'sha256': sha(root/'selection.json')},
                     'target': {'path': 'target.json', 'sha256': sha(root/'target.json')},
                     'adapter': {'path': 'anatomy.json', 'sha256': sha(root/'anatomy.json')}}}
    receipt['cache_key'] = digest(receipt)
    atomic_json(root/'specification.json', dict(spec, display={'max_faces': 100, 'width_px': 1000, 'height_px': 1000}))
    files = [*artifacts.values(), receipt['artifact'], *receipt['evidence'].values()]
    arguments = {'project_root': str(root), 'selection_path': 'selection.json', 'target_path': 'target.json'}
    native = {'operation': 'prepare_body_target', 'arguments': arguments, 'result': receipt,
        'origin': 'NATIVE_DISPATCH', 'execution': 'RETURNED', 'run_id': 'run.body', 'unit_id': 'body',
        'attempt_id': 'attempt.body', 'binding_sha256': 'e'*64, 'files': files}
    atomic_json(root/'native.json', native)
    ref = {'path': 'native.json', 'sha256': sha(root/'native.json')}
    event = {'receipt': ref, 'run_id': 'run.body', 'unit_id': 'body', 'attempt_id': 'attempt.body', 'binding_sha256': 'e'*64}
    run = {'units': [{'id': 'body', 'status': 'COMPLETED', 'attempts': [{'id': 'attempt.body',
        'status': 'COMPLETED', 'operation': 'prepare_body_target', 'arguments': arguments,
        'receipt_event_id': 1, 'receipt': ref, 'binding_sha256': 'e'*64}]}]}
    database = root/'state.sqlite'
    with closing(sqlite3.connect(database)) as db, db:
        db.execute('CREATE TABLE events(id INTEGER PRIMARY KEY,kind TEXT,doc TEXT)')
        db.execute('CREATE TABLE runs(id TEXT PRIMARY KEY,doc TEXT)')
        db.execute('INSERT INTO events VALUES(1,?,?)', ('run_native_receipt', json.dumps(event)))
        db.execute('INSERT INTO runs VALUES(?,?)', ('run.body', json.dumps(run)))
    return SimpleNamespace(root=root, db=database), receipt


class BodySourcePaths(unittest.TestCase):
    def test_nonplanar_source_ring_is_measured_without_replacing_a_horizontal_girth(self):
        values = fixture(); before = digest(values); result = measure_source_body_paths(*values)
        path = result['paths'][0]
        self.assertEqual(path['source_regions'], [41, 67]); self.assertEqual(path['vertex_ids'], [0, 1, 2, 3])
        self.assertEqual(path['length_cm'], 4*math.sqrt(404.))
        self.assertEqual(path['body_frame_height_range_cm'], [80., 82.])
        self.assertNotEqual(path['length_cm'], values[0]['landmarks']['neck']['girth_cm'])
        self.assertEqual(digest(values), before); self.assertEqual(result, measure_source_body_paths(*values))
        self.assertEqual(result['tailoring_homology'], 'REVIEW_REQUIRED'); self.assertEqual(result['qualification'], 'NONE')
        self.assertFalse(result['body_girths_replaced']); self.assertFalse(result['ease_transferred'])

    def test_open_interface_branches_and_multiple_loops_are_refused(self):
        for mode in ('open', 'branch', 'two-loops'):
            values = list(copy.deepcopy(fixture())); geometry = values[1]
            if mode == 'open': geometry['face_sets'][-1] = 99
            else:
                old_points = geometry['vertices_cm']; offset = len(old_points)
                if mode == 'two-loops':
                    geometry['vertices_cm'] += [[x+40, y, z] for x, y, z in old_points]
                    geometry['faces'] += [[i+offset for i in face] for face in geometry['faces']]
                else:
                    # A second cycle shares source vertex 0, forming degree 4.
                    geometry['vertices_cm'] += [[x+40, y, z] for x, y, z in old_points[1:]]
                    remap = lambda i: 0 if i == 0 else offset+i-1
                    geometry['faces'] += [[remap(i) for i in face] for face in geometry['faces']]
                geometry['face_sets'] *= 2
            rebind(values)
            with self.subTest(mode=mode), self.assertRaises(StudioError): measure_source_body_paths(*values)

    def test_order_and_body_frame_transform_preserve_actual_length_and_height(self):
        plain = measure_source_body_paths(*fixture()); values = list(copy.deepcopy(fixture()))
        for body in (values[1], values[2]):
            body['vertices_cm'] = [[-z+7., x-8., y+9.] for x, y, z in body['vertices_cm']]
        values[0]['frame'] = {'origin_cm': [7., -8., 9.], 'right': [0., 1., 0.],
                             'forward': [0., 0., 1.], 'up': [-1., 0., 0.]}
        values[1]['faces'].reverse(); values[1]['face_sets'].reverse(); rebind(values)
        transformed = measure_source_body_paths(*values)['paths'][0]
        self.assertEqual(transformed['length_cm'], plain['paths'][0]['length_cm'])
        self.assertEqual(transformed['body_frame_height_range_cm'], [80., 82.])
        self.assertEqual(transformed['vertex_ids'], [0, 1, 2, 3])

    def test_profile_source_pose_adapter_labels_and_original_topology_mismatch_refused(self):
        for mode in ('source', 'pose', 'adapter', 'labels', 'topology', 'profile', 'cache'):
            values = list(copy.deepcopy(fixture()))
            if mode == 'source': values[1]['source_sha256'] = 'c'*64
            if mode == 'pose': values[1]['pose_sha256'] = 'c'*64
            if mode == 'adapter': values[3]['source_geometry_sha256'] = 'c'*64
            if mode == 'labels': values[1]['face_sets'][0] = 99
            if mode == 'topology': values[2]['faces'][0].reverse()
            if mode == 'profile': values[0]['geometry_sha256'] = 'c'*64
            if mode == 'cache': values[0]['cache_key'] = 'c'*64
            with self.subTest(mode=mode), self.assertRaises(StudioError): measure_source_body_paths(*values)

    def test_nan_bool_missing_joint_bad_winding_and_collapsed_source_edges_refused(self):
        for mode in ('nan', 'bool', 'joint', 'winding', 'collapsed'):
            values = list(copy.deepcopy(fixture()))
            if mode == 'nan': values[1]['vertices_cm'][0][0] = float('nan')
            if mode == 'bool': values[1]['faces'][0][0] = True
            if mode == 'joint': values[4]['paths'][0]['source_joint'] = 'absent'
            if mode == 'winding': values[1]['faces'][0].reverse(); rebind(values)
            if mode == 'collapsed': values[1]['vertices_cm'][1] = list(values[1]['vertices_cm'][0]); rebind(values)
            with self.subTest(mode=mode), self.assertRaises(StudioError): measure_source_body_paths(*values)

    def test_explicit_budgets_refuse_excess_and_late_or_reversed_clocks(self):
        for key, value in [('max_vertices', 4), ('max_faces', 2), ('max_face_edges', 4), ('max_boundary_edges', 3)]:
            values = list(copy.deepcopy(fixture())); values[-1]['budgets'][key] = value
            with self.subTest(key=key), self.assertRaisesRegex(StudioError, 'budget'): measure_source_body_paths(*values)
        for clock in ([0., 2.], [2., 1.]):
            values = list(fixture()); values[-1]['budgets']['max_seconds'] = 1.
            with patch('a3d.body_source_paths.time.monotonic', side_effect=clock), self.assertRaisesRegex(StudioError, 'clock'):
                measure_source_body_paths(*values)
        bad = specification(); bad['budgets']['max_seconds'] = float('nan')
        with self.assertRaises(StudioError): validate_specification(bad)

    def test_facade_reads_canonical_origin_and_preserves_files_database_and_profiles(self):
        with tempfile.TemporaryDirectory(dir=ROOT) as directory:
            root = Path(directory); project, _ = native_project(root)
            before = {p.name: sha(p) for p in root.iterdir() if p.is_file()}
            result = prepare_project_body_path_review(project, 'profile.json', 'specification.json', 'preparation/review')
            self.assertEqual(result['status'], 'BODY_SOURCE_PATH_REVIEW_PREPARED')
            self.assertEqual({name: sha(root/name) for name in before}, before)
            self.assertEqual(result['report']['native_body_origin']['event_id'], 1)
            for ref in result['artifacts'].values(): self.assertEqual(sha(root/ref['path']), ref['sha256'])
            svg = (root/'preparation/review/projections.svg').read_text(encoding='utf-8')
            self.assertIn('homologie anatomique', svg); self.assertIn('sans contrôle d’occlusion', svg)
            self.assertEqual(svg.count('<polyline'), 4)
            self.assertTrue((root/'preparation/review/review-receipt.json').is_file())
            with self.assertRaisesRegex(StudioError, 'exists'):
                prepare_project_body_path_review(project, 'profile.json', 'specification.json', 'preparation/review')

    def test_optional_openings_have_separate_unselected_artifacts_and_preserve_the_body(self):
        with tempfile.TemporaryDirectory(dir=ROOT) as directory:
            root = Path(directory); project, _ = native_project(root)
            spec = read_json(root/'specification.json')
            spec['opening_exploration'] = {'path_id':'source.neck-boundary',
                'reference_plane':'BODY_SAGITTAL','front_anchor':'UNIQUE_FRONTMOST_INTERSECTION',
                'max_pairs':1,'max_seconds':2.,'max_output_bytes':512000}
            atomic_json(root/'specification.json', spec)
            before = {p.name:sha(p) for p in root.iterdir() if p.is_file()}
            result = prepare_project_body_path_review(project, 'profile.json', 'specification.json', 'preparation/openings')
            self.assertEqual({name:sha(root/name) for name in before}, before)
            self.assertEqual(result['qualification'], 'NONE')
            self.assertIn('opening_exploration',result['report'])
            self.assertIn('opening-options.svg',result['artifacts'])
            self.assertIn('projections.svg',result['artifacts'])
            self.assertEqual(result['report']['paths'][0]['tailoring_homology'],'REVIEW_REQUIRED')
            for ref in result['artifacts'].values(): self.assertEqual(sha(root/ref['path']),ref['sha256'])

    def test_opening_exploration_cannot_select_another_path_or_exceed_parent_budgets(self):
        base = specification()
        base['opening_exploration'] = {'path_id':'source.neck-boundary',
            'reference_plane':'BODY_SAGITTAL','front_anchor':'UNIQUE_FRONTMOST_INTERSECTION',
            'max_pairs':1,'max_seconds':2.,'max_output_bytes':512000}
        for field,value in (('path_id','other.path'),('max_seconds',16.),('max_output_bytes',5*1024*1024)):
            spec = copy.deepcopy(base); spec['opening_exploration'][field] = value
            with self.subTest(field=field), self.assertRaises(StudioError): validate_specification(spec)

    def test_opening_computation_and_renderer_share_one_cumulative_time_budget(self):
        from a3d import body_path_openings
        original_prepare = body_path_openings.prepare_opening_candidates
        original_render = body_path_openings.render_opening_candidates
        with tempfile.TemporaryDirectory(dir=ROOT) as directory:
            root = Path(directory); project, _ = native_project(root)
            spec = read_json(root/'specification.json')
            spec['opening_exploration'] = {'path_id':'source.neck-boundary',
                'reference_plane':'BODY_SAGITTAL','front_anchor':'UNIQUE_FRONTMOST_INTERSECTION',
                'max_pairs':1,'max_seconds':1.,'max_output_bytes':512000}
            atomic_json(root/'specification.json',spec)
            elapsed = [0.]
            def prepare(*args, **kwargs):
                result = original_prepare(*args, **kwargs); elapsed[0] = .6; return result
            def render(*args, **kwargs):
                result = original_render(*args, **kwargs); elapsed[0] = 1.1; return result
            with patch('a3d.body_source_paths.time.monotonic',side_effect=lambda:elapsed[0]), \
                    patch.object(body_path_openings,'prepare_opening_candidates',side_effect=prepare), \
                    patch.object(body_path_openings,'render_opening_candidates',side_effect=render), \
                    self.assertRaisesRegex(StudioError,'cumulative'):
                prepare_project_body_path_review(project,'profile.json','specification.json','preparation/expired')
            self.assertFalse((root/'preparation/expired').exists())

    def test_file_only_and_failed_or_forged_native_attempt_cannot_qualify_a_profile(self):
        for mode in ('no-event', 'failed', 'forged-binding'):
            with tempfile.TemporaryDirectory(dir=ROOT) as directory:
                root = Path(directory); project, _ = native_project(root)
                with closing(sqlite3.connect(project.db)) as database, database:
                    if mode == 'no-event': database.execute('DELETE FROM events')
                    else:
                        run = json.loads(database.execute('SELECT doc FROM runs').fetchone()[0])
                        if mode == 'failed': run['units'][0]['status'] = 'FAILED'
                        else: run['units'][0]['attempts'][0]['binding_sha256'] = 'f'*64
                        database.execute('UPDATE runs SET doc=?', (json.dumps(run),))
                before = sha(project.db)
                with self.subTest(mode=mode), self.assertRaises(StudioError):
                    prepare_project_body_path_review(project, 'profile.json', 'specification.json', 'preparation/refused')
                self.assertEqual(sha(project.db), before); self.assertFalse((root/'preparation/refused').exists())

    def test_stale_native_artifacts_and_tiny_read_or_output_budgets_refuse_before_write(self):
        for mode in ('adapter', 'source', 'pose', 'read-budget', 'storage-budget'):
            with tempfile.TemporaryDirectory(dir=ROOT) as directory:
                root = Path(directory); project, _ = native_project(root)
                if mode == 'adapter': (root/'anatomy.json').write_text('{}')
                if mode == 'source': (root/'source.blend').write_bytes(b'changed')
                if mode == 'pose':
                    geometry = read_json(root/'geometry.json'); geometry['pose_sha256'] = 'f'*64; atomic_json(root/'geometry.json', geometry)
                if mode in ('read-budget', 'storage-budget'):
                    spec = read_json(root/'specification.json')
                    spec['budgets']['max_read_bytes' if mode == 'read-budget' else 'max_output_bytes'] = 1
                    atomic_json(root/'specification.json', spec)
                with self.subTest(mode=mode), self.assertRaises(StudioError):
                    prepare_project_body_path_review(project, 'profile.json', 'specification.json', 'preparation/refused')
                self.assertFalse((root/'preparation/refused').exists())

    def test_source_change_during_publication_leaves_no_completed_review_marker(self):
        with tempfile.TemporaryDirectory(dir=ROOT) as directory:
            root = Path(directory); project, _ = native_project(root)
            from a3d.body_source_paths import _Reader
            original = _Reader.preserve; count = [0]
            def preserve(reader):
                count[0] += 1
                if count[0] == 2: (root/'profile.json').write_text('{}')
                return original(reader)
            with patch.object(_Reader, 'preserve', preserve), self.assertRaisesRegex(StudioError, 'changed'):
                prepare_project_body_path_review(project, 'profile.json', 'specification.json', 'preparation/interrupted')
            self.assertFalse((root/'preparation/interrupted/review-receipt.json').exists())

    def test_terminal_budget_expiry_retires_only_the_fresh_marker_and_keeps_reports(self):
        import a3d.body_source_paths as module
        for phase in ('after-write', 'after-hash'):
            with tempfile.TemporaryDirectory(dir=ROOT) as directory:
                root = Path(directory); project, _ = native_project(root)
                spec = read_json(root/'specification.json'); spec['budgets']['max_seconds'] = 1.
                atomic_json(root/'specification.json', spec)
                marker = root/'preparation/interrupted/review-receipt.json'; clock = [0.]; real_sha = module.sha
                def observe_sha(path):
                    result = real_sha(path)
                    if phase == 'after-hash' and Path(path) == marker: clock[0] = 2.
                    return result
                now = lambda: 2. if phase == 'after-write' and marker.exists() else clock[0]
                with patch.object(module.time, 'monotonic', side_effect=now), patch.object(module, 'sha', side_effect=observe_sha):
                    with self.subTest(phase=phase), self.assertRaisesRegex(StudioError, 'time budget'):
                        prepare_project_body_path_review(project, 'profile.json', 'specification.json', 'preparation/interrupted')
                self.assertFalse(marker.exists())
                for name in ('report.json', 'report.md', 'projections.svg'):
                    self.assertTrue((root/'preparation/interrupted'/name).is_file())

    def test_terminal_refusal_preserves_a_foreign_replacement_marker(self):
        import a3d.body_source_paths as module
        with tempfile.TemporaryDirectory(dir=ROOT) as directory:
            root = Path(directory); project, _ = native_project(root)
            spec = read_json(root/'specification.json'); spec['budgets']['max_seconds'] = 1.
            atomic_json(root/'specification.json', spec)
            marker = root/'preparation/interrupted/review-receipt.json'; clock = [0.]; real_sha = module.sha
            foreign = b'{"status":"FOREIGN_DIAGNOSTIC_RECORD"}'
            def replace_marker(path):
                if Path(path) == marker:
                    replacement = marker.with_name('foreign.json'); replacement.write_bytes(foreign)
                    replacement.replace(marker); clock[0] = 2.
                return real_sha(path)
            with patch.object(module.time, 'monotonic', side_effect=lambda: clock[0]), patch.object(module, 'sha', side_effect=replace_marker):
                with self.assertRaisesRegex(StudioError, 'time budget'):
                    prepare_project_body_path_review(project, 'profile.json', 'specification.json', 'preparation/interrupted')
            self.assertEqual(marker.read_bytes(), foreign)
            self.assertTrue((root/'preparation/interrupted/report.json').is_file())

    def test_actual_bootstrap_bytes_are_bounded_when_stat_understates_the_file(self):
        import a3d.body_source_paths as module
        with tempfile.TemporaryDirectory(dir=ROOT) as directory:
            root = Path(directory); project, _ = native_project(root)
            file = root/'specification.json'; file.write_bytes(file.read_bytes()+b' '*module.MAX_SPEC_BYTES)
            real_stat = Path.stat
            def understated(path, *args, **kwargs):
                result = real_stat(path, *args, **kwargs)
                return SimpleNamespace(st_size=1) if path == file and kwargs.get('follow_symlinks', True) else result
            with patch.object(Path, 'stat', understated), self.assertRaisesRegex(StudioError, 'bootstrap reading limit'):
                prepare_project_body_path_review(project, 'profile.json', 'specification.json', 'preparation/refused')
            self.assertFalse((root/'preparation/refused').exists())

    def test_streaming_json_limit_uses_actual_bytes_without_capping_binary_blobs(self):
        import a3d.body_source_paths as module
        with tempfile.TemporaryDirectory(dir=ROOT) as directory:
            root = Path(directory); file = root/'growing.json'; file.write_bytes(b'{"value":"'+b'x'*1000+b'"}')
            project = SimpleNamespace(root=root); real_stat = Path.stat
            def understated(path, *args, **kwargs):
                result = real_stat(path, *args, **kwargs)
                return SimpleNamespace(st_size=1) if path == file and kwargs.get('follow_symlinks', True) else result
            with patch.object(Path, 'stat', understated), patch.object(module, 'MAX_JSON_BYTES', 32):
                budget = module._Budget(specification()); reader = module._Reader(project, budget)
                with self.assertRaisesRegex(StudioError, 'actual JSON bytes'): reader.read(file.name)
                self.assertEqual(budget.read_bytes, 33); self.assertNotIn(file.name, reader.documents)
                binary = module._Reader(project, module._Budget(specification()))
                self.assertEqual(binary.read(file.name, document=False), file)
                self.assertEqual(binary.budget.read_bytes, file.stat().st_size if file.stat().st_size != 1 else len(file.read_bytes()))

    def test_unrelated_native_receipt_is_filtered_before_any_artifact_read(self):
        with tempfile.TemporaryDirectory(dir=ROOT) as directory:
            root = Path(directory); project, _ = native_project(root)
            (root/'unrelated.json').write_bytes(b'UNRELATED_INVALID_JSON_MUST_NEVER_BE_READ')
            ref = {'path': 'unrelated.json', 'sha256': sha(root/'unrelated.json')}
            event = {'receipt': ref, 'run_id': 'run.unrelated', 'unit_id': 'unrelated',
                     'attempt_id': 'attempt.unrelated', 'binding_sha256': 'c'*64}
            run = {'units': [{'id': 'unrelated', 'status': 'COMPLETED', 'attempts': [
                {'id': 'attempt.unrelated', 'operation': 'bind_component_preparations'}]}]}
            with closing(sqlite3.connect(project.db)) as database, database:
                database.execute('INSERT INTO runs VALUES(?,?)', ('run.unrelated', json.dumps(run)))
                database.execute('INSERT INTO events VALUES(2,?,?)', ('run_native_receipt', json.dumps(event)))
            before = sha(project.db)
            result = prepare_project_body_path_review(project, 'profile.json', 'specification.json', 'preparation/review')
            self.assertEqual(result['report']['native_body_origin']['event_id'], 1)
            self.assertNotIn('unrelated.json', [ref['path'] for ref in result['report']['input_refs']])
            self.assertEqual(sha(project.db), before)

    def test_introduced_body_requires_exact_context_binding_and_real_canonical_attempt(self):
        # The context loader is independently tested in test_body_context. This
        # fixture isolates its native introduction binding, without inventing
        # an anatomical/Blender result for the portable bipyramid.
        for forged in (False, True):
            with tempfile.TemporaryDirectory(dir=ROOT) as directory:
                root = Path(directory); project, receipt = native_project(root)
                atomic_json(root/'body-receipt.json', receipt)
                receipt_ref = {'path': 'body-receipt.json', 'sha256': sha(root/'body-receipt.json')}
                context = {'body_target_receipt': receipt_ref}; atomic_json(root/'context.json', context)
                context_ref = {'path': 'context.json', 'sha256': sha(root/'context.json')}
                profile = read_json(root/'profile.json'); geometry = read_json(root/'geometry.json')
                descriptor = {'context': context, 'context_ref': context_ref, 'receipt': receipt,
                    'profile': profile, 'geometry': geometry, 'binding_sha256': 'c'*64}
                native = read_json(root/'native.json'); native['operation'] = 'introduce_body_target'
                native['arguments'] = {'project_root': str(root), 'context_path': 'context.json'}
                native['result'] = {'status': 'BODY_TARGET_INTRODUCED', 'profile_ref': receipt['artifacts']['profile'],
                    'geometry_ref': receipt['artifacts']['geometry'], 'context': context_ref,
                    'body_target_receipt': receipt_ref, 'source_artifact': receipt['artifact'],
                    'profile_cache_key': profile['cache_key'], 'binding_sha256': 'f'*64 if forged else 'c'*64,
                    'actual_geometry_sha256': digest({key: geometry[key] for key in ('vertices_cm', 'faces', 'face_sets')})}
                native['files'] += [context_ref, receipt_ref]; atomic_json(root/'native.json', native)
                with closing(sqlite3.connect(project.db)) as database, database:
                    event = json.loads(database.execute('SELECT doc FROM events').fetchone()[0])
                    event['receipt']['sha256'] = sha(root/'native.json')
                    run = json.loads(database.execute('SELECT doc FROM runs').fetchone()[0])
                    attempt = run['units'][0]['attempts'][0]
                    attempt.update(operation=native['operation'], arguments=native['arguments'], receipt=event['receipt'])
                    database.execute('UPDATE events SET doc=?', (json.dumps(event),))
                    database.execute('UPDATE runs SET doc=?', (json.dumps(run),))
                before = sha(project.db)
                with patch('a3d.body_context.body_context_descriptor', return_value=descriptor):
                    if forged:
                        with self.assertRaisesRegex(StudioError, 'introduction differs'):
                            prepare_project_body_path_review(project, 'profile.json', 'specification.json', 'preparation/refused')
                        self.assertFalse((root/'preparation/refused').exists())
                    else:
                        result = prepare_project_body_path_review(project, 'profile.json', 'specification.json', 'preparation/review')
                        self.assertEqual(result['report']['native_body_origin']['event_id'], 1)
                self.assertEqual(sha(project.db), before)


if __name__ == '__main__': unittest.main()
