import copy
import sys
from types import SimpleNamespace
from unittest.mock import patch

from a3d.core import StudioError, atomic_json, digest, read_json, sha
from a3d.piece_inventory import (current_proof, expected_inventory, mapped_pieces,
                                 reconcile, require_complete, write_review)
from blender.piece_inventory import collect, remember_candidate, save_report, bind_frozen_map
from tests.test_core import Case
from tests.support import ready_project, png


def fixture_inventory():
    specs = {'garment.coat': [f'coat-{i}' for i in range(10)],
             'garment.hood-yoke': ['hood-left', 'hood-right', 'yoke-upper', 'yoke-lower'],
             'garment.belt': ['belt']}
    components = {cid: {'kind': 'textile', 'pieces': ids, 'package': {'sha256': cid},
                        'source_sha256': cid} for cid, ids in specs.items()}
    components['prop.buckle'] = {'kind': 'rigid', 'pieces': [], 'package': {'sha256': 'buckle'}}
    return {'components': components}


def observation(expected, cid, pieces=None, **extra):
    info = expected['components'][cid]
    return {'component_id': cid, 'object': cid, 'pieces': pieces or info['pieces'],
            'package_sha256': info['package']['sha256'], 'source_sha256': info['source_sha256'],
            'visible': True, **extra}


class PieceInventoryTests(Case):
    def test_reported_case_local_ten_global_fifteen_and_exact_missing_ids(self):
        expected = fixture_inventory()
        report = reconcile(expected, [observation(expected, 'garment.coat')], 'garment.coat')
        self.assertEqual(report['components']['garment.coat']['status'], 'COMPLETE')
        self.assertEqual((report['global']['present'], report['global']['expected']), (10, 15))
        self.assertEqual(len(report['global']['missing']), 5)
        self.assertIn(['garment.belt', 'belt'], report['global']['missing'])
        self.assertEqual(report['rigid_components'], ['prop.buckle'])
        require_complete(report, 'garment.coat')
        with self.assertRaises(StudioError): require_complete(report)

    def test_equal_total_count_with_duplicate_does_not_replace_missing_identity(self):
        expected = fixture_inventory()
        rows = [observation(expected, cid) for cid in expected['components'] if cid != 'prop.buckle']
        rows = rows[:2]+[observation(expected, 'garment.coat', ['coat-0'])]
        report = reconcile(expected, rows)
        self.assertEqual(report['global']['present'], 14)
        self.assertEqual(report['global']['duplicates'][0]['count'], 2)
        self.assertEqual(report['global']['missing'], [['garment.belt', 'belt']])

    def test_hidden_piece_is_present_without_visual_or_technical_approval(self):
        expected = fixture_inventory()
        report = reconcile(expected, [observation(expected, 'garment.coat', visible=False)])
        self.assertEqual(report['global']['present'], 10)
        self.assertEqual(report['global']['visible_in_view_layer'], 0)
        self.assertEqual(report['global']['capture_visibility'], 'NOT_VERIFIED')
        self.assertEqual(report['global']['technical_acceptance'], 'NOT_INFERRED')

    def test_missing_mapping_or_old_package_is_non_verifiable(self):
        expected = fixture_inventory()
        for extra in ({'error': 'mapping unavailable'}, {'package_sha256': 'previous'}):
            report = reconcile(expected, [observation(expected, 'garment.coat', **extra)])
            self.assertEqual(report['global']['status'], 'NON_VERIFIABLE')
            self.assertEqual(report['global']['present'], 0)

    def test_connected_mesh_keeps_face_piece_identity(self):
        payload = {'faces': [[0,1,2], [1,2,3]], 'rest_cm': [[0,0,0]]*4,
                   'panels': {'left': {}, 'right': {}}, 'source_face_pieces': ['left', 'right']}
        self.assertEqual(mapped_pieces(payload, payload['faces'], 4), ['left', 'right'])
        with self.assertRaises(StudioError): mapped_pieces(payload, payload['faces'][:1], 4)
        del payload['source_face_pieces']
        payload['panels'] = {'left': {'indices': [0,1,2,3]}, 'right': {'indices': [0,1,2,3]}}
        with self.assertRaises(StudioError): mapped_pieces(payload, payload['faces'], 4)

    def native_fixture(self):
        project = ready_project(self.root, True)
        expected = expected_inventory(project)
        cid = 'garment.coat'; info = expected['components'][cid]
        faces = [[3*i, 3*i+1, 3*i+2] for i in range(len(info['pieces']))]
        payload = {'component_id': cid, 'package_sha256': info['package']['sha256'],
                   'source_garment_sha256': info['source_sha256'], 'faces': faces,
                   'rest_cm': [[0,0,0]]*(len(faces)*3), 'placed_cm': [[0,0,0]]*(len(faces)*3),
                   'source_face_pieces': info['pieces'],
                   'panels': {pid: {'indices': f} for pid,f in zip(info['pieces'], faces)}}
        path = project.data/'blender/map.json'; atomic_json(path, payload)
        working = project.data/'blender/working.blend'; working.write_bytes(b'synthetic saved scene')
        atomic_json(project.data/'blender/session.json', {'working': str(working), 'construction_id': 'current'})
        class Obj(dict):
            type = 'MESH'
            hide_render = False
            def visible_get(self): return True
        obj = Obj(a3d_component_id=cid, a3d_package_sha256=info['package']['sha256'],
                  a3d_role='simulation', a3d_sewing_mesh=path.relative_to(project.root).as_posix(),
                  a3d_sewing_mesh_sha256=sha(path), a3d_construction_id='current')
        obj.name = 'single mesh with all panels'
        obj.data = SimpleNamespace(vertices=list(range(len(payload['rest_cm']))),
                                   polygons=[SimpleNamespace(vertices=f) for f in faces])
        bpy = SimpleNamespace(context=SimpleNamespace(scene=SimpleNamespace(objects=[obj])),
                              data=SimpleNamespace(is_dirty=False))
        return project, obj, payload, bpy

    def test_native_adapter_one_object_all_panels_and_duplicate_geometry(self):
        project, obj, payload, bpy = self.native_fixture()
        with patch.dict(sys.modules, {'bpy': bpy}), patch('blender.sewing.mesh_digest', return_value='geometry'):
            report = collect(project)
            self.assertEqual(report['global']['status'], 'COMPLETE')
            self.assertEqual(report['global']['present'], len(payload['panels']))
            bpy.context.scene.objects.append(obj)
            report = collect(project)
            self.assertEqual(len(report['global']['duplicates']), len(payload['panels']))
            with self.assertRaises(StudioError): require_complete(report)

    def test_archived_auxiliary_and_other_construction_cannot_satisfy_inventory(self):
        project, obj, _, bpy = self.native_fixture()
        with patch.dict(sys.modules, {'bpy': bpy}), patch('blender.sewing.mesh_digest', return_value='geometry'):
            for role in ('archived-simulation', 'auxiliary_collider'):
                obj['a3d_role'] = role
                self.assertEqual(collect(project)['global']['present'], 0)
            obj['a3d_role'] = 'simulation'; obj['a3d_construction_id'] = 'old'
            self.assertEqual(collect(project)['global']['status'], 'NON_VERIFIABLE')

    def test_preparation_candidate_is_preview_only_and_new_rejection_clears_it(self):
        project, obj, _, bpy = self.native_fixture()
        cid = obj['a3d_component_id']; obj['a3d_source_component_id'] = obj.pop('a3d_component_id')
        obj['a3d_role'] = 'preparation-candidate'
        with patch.dict(sys.modules, {'bpy': bpy}), patch('blender.sewing.mesh_digest', return_value='geometry'):
            # Migration: the loaded 0.6.7 candidate has no new inventory registry yet.
            self.assertEqual(collect(project, previews=True)['global']['status'], 'COMPLETE')
            remember_candidate(project, cid, obj)
            self.assertEqual(collect(project)['global']['present'], 0)
            report = collect(project, cid, previews=True)
            self.assertEqual(report['global']['status'], 'COMPLETE')
            save_report(project, report)
            with self.assertRaises(StudioError): current_proof(project, require_global=True)
            remember_candidate(project, cid, None)
            self.assertEqual(collect(project, previews=True)['global']['present'], 0)

    def test_saved_proof_invalidates_on_scene_map_session_package_or_dirty_changes(self):
        project, obj, _, bpy = self.native_fixture()
        with patch.dict(sys.modules, {'bpy': bpy}), patch('blender.sewing.mesh_digest', return_value='geometry'):
            report = save_report(project, collect(project))
            self.assertEqual(current_proof(project, require_global=True)['global']['status'], 'COMPLETE')
            working = self.root/report['artifact']['path']; old = working.read_bytes()
            working.write_bytes(b'new scene')
            with self.assertRaises(StudioError): current_proof(project, require_global=True)
            working.write_bytes(old)
            map_path = self.root/obj['a3d_sewing_mesh']; old_map = map_path.read_bytes()
            map_path.write_bytes(b'changed mapping')
            with self.assertRaises(StudioError): current_proof(project, require_global=True)
            map_path.write_bytes(old_map)
            bpy.data.is_dirty = True
            save_report(project, collect(project))
            with self.assertRaises(StudioError): current_proof(project, require_global=True)
            bpy.data.is_dirty = False
            save_report(project, collect(project))
            package = self.root/project.state()['components']['garment.coat']['package']['path']
            with package.open('ab') as f: f.write(b'package changed')
            with self.assertRaises(StudioError): current_proof(project, require_global=True)

    def test_review_places_missing_coverage_next_to_original_image(self):
        expected = fixture_inventory()
        report = reconcile(expected, [observation(expected, 'garment.coat')], 'garment.coat')
        project = ready_project(self.root, True)
        image = project.data/'blender/front.png'; image.parent.mkdir(exist_ok=True); image.write_bytes(png())
        path = project.data/'blender/review.html'
        write_review(project, report, path, [{'path': image.relative_to(self.root).as_posix(), 'sha256': sha(image)}])
        html = path.read_text(encoding='utf-8')
        self.assertIn('10/15', html); self.assertIn('garment.belt/belt', html)
        self.assertIn('<figcaption>', html); self.assertIn('front.png', html)

    def test_frozen_surface_keeps_source_identity_after_explicit_remap(self):
        project, obj, payload, bpy = self.native_fixture()
        coords = [[0,0,0]]*len(payload['rest_cm'])
        bind_frozen_map(project, obj, payload, payload['faces'], coords,
                        {i:i for i in range(len(coords))})
        frozen = read_json(self.root/obj['a3d_sewing_mesh'])
        self.assertEqual(mapped_pieces(frozen, payload['faces'], len(coords)), sorted(payload['panels']))

    def test_global_lifecycle_and_native_gate_refuse_missing_or_preview_only_proof(self):
        from a3d.lifecycle import assembly_result, final_validation
        from blender.piece_inventory import require_live
        project, obj, _, bpy = self.native_fixture()
        for gate in (assembly_result, final_validation):
            with self.assertRaisesRegex(StudioError, 'completeness'):
                gate(project, project.state())
        with patch.dict(sys.modules, {'bpy': bpy}), patch('blender.sewing.mesh_digest', return_value='geometry'):
            save_report(project, collect(project, previews=True))
            with self.assertRaises(StudioError): current_proof(project, require_global=True)
            bpy.context.scene.objects.clear()
            with self.assertRaisesRegex(StudioError, 'completeness blocks'):
                require_live(project, 'garment.coat')
            save_report(project, collect(project))
            for gate in (assembly_result, final_validation):
                with self.assertRaisesRegex(StudioError, 'completeness'):
                    gate(project, project.state())

    def test_inspection_before_reviewed_inventory_reports_unknown_without_inventing_counts(self):
        project, _, _, bpy = self.native_fixture()
        with patch.dict(sys.modules, {'bpy': bpy}), patch('blender.piece_inventory.expected_inventory', side_effect=StudioError('board absent')):
            report = collect(project)
            self.assertEqual(report['global']['status'], 'NON_VERIFIABLE')
            self.assertIsNone(report['global']['expected'])
            with self.assertRaises(StudioError): require_complete(report)

    def test_inspect_includes_non_ready_source_component_candidate(self):
        from blender.operations import inspect
        project, obj, payload, bpy = self.native_fixture()
        obj['a3d_source_component_id'] = obj.pop('a3d_component_id')
        obj['a3d_role'] = 'preparation-candidate'
        obj['a3d_pattern_preparation_readiness'] = 'NEEDS_CLARIFICATION'
        obj.data.materials = []; obj.data.uv_layers = []
        obj.dimensions = [1,1,1]; obj.modifiers = []
        bpy.data.objects = [obj]; bpy.app = SimpleNamespace(version_string='synthetic fixture')
        bm = SimpleNamespace(from_mesh=lambda _: None, edges=[], faces=[], free=lambda: None)
        with patch.dict(sys.modules, {'bpy': bpy, 'bmesh': SimpleNamespace(new=lambda: bm)}), patch('blender.sewing.mesh_digest', return_value='geometry'), patch('blender.operations.working', return_value=(project, read_json(project.data/'blender/session.json'))):
            report = inspect(str(project.root))
        self.assertEqual(report['objects'][0]['component_id'], 'garment.coat')
        self.assertEqual(report['piece_completeness']['global']['present'], len(payload['panels']))
        self.assertEqual(report['active_piece_completeness']['global']['present'], 0)
        self.assertFalse('PASS' in report['piece_completeness']['qualification'])
