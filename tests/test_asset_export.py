import copy
from types import SimpleNamespace
from unittest.mock import patch

from a3d.core import StudioError, atomic_json, digest, sha
from a3d.export_profiles import (compare_native_samples, export_descriptor, export_sample_times,
                                 clip_tracks, motion_qualification, validate_export_profile, verify_export_manifest)
from tests.test_core import Case
from tests.support import ready_project


def profile(source_ref):
    return {'version': 1, 'destination': 'blender_animation', 'source_ref': source_ref,
            'object_names': ['cloth'], 'dependency_names': ['rig'], 'action_names': ['walk'], 'embedded_image_names': [],
            'unit_scale_m': 1., 'fps': 24, 'reference_frame': 1, 'resources': [], 'motion_receipts': [],
            'clips': [{'id': 'walk', 'object_name': 'rig', 'action_name': 'walk', 'slot_identifier': 'OBrig',
                       'frame_start': 1, 'frame_end': 6, 'sample_step': 4}],
            'pack_resources': True, 'geometry_tolerance_cm': .0001, 'budgets': {'max_seconds': 60., 'max_samples': 20}}


def clip_receipt(export_profile, action_sha):
    clip = export_profile['clips'][0]
    receipt = {'version': 1, 'candidate': export_profile['source_ref'], 'status': 'CLIPS_EXECUTED',
               'scope': 'EXACT_CANDIDATE_ANIMATION', 'temporal_coverage': 'COMPLETE', 'fps': export_profile['fps'],
               'clips': [dict(clip, status='EXECUTED_FULL_CLIP', action_sha256=action_sha,
                              executed_times=list(range(clip['frame_start'], clip['frame_end']+1)))]}
    receipt['cache_key'] = digest(receipt)
    return receipt


class AssetExportTests(Case):
    def inputs(self):
        project = ready_project(self.root); source = self.root/'candidate.blend'; source.write_bytes(b'native-fixture-only')
        return project, profile({'path': source.name, 'sha256': sha(source)})

    def test_endpoints_required_and_insufficient_sampling_budget_refused(self):
        _, value = self.inputs()
        self.assertEqual(export_sample_times(value['clips'][0]), [1, 5, 6])
        bad = copy.deepcopy(value); bad['budgets']['max_samples'] = 3
        with self.assertRaisesRegex(StudioError, 'budget'): validate_export_profile(bad)
        for change in ('undeclared_action', 'same_dependency', 'backwards_clip', 'duplicate_clip', 'wrong_destination'):
            bad = copy.deepcopy(value)
            if change == 'undeclared_action': bad['clips'][0]['action_name'] = 'unknown'
            if change == 'same_dependency': bad['dependency_names'].append('cloth')
            if change == 'backwards_clip': bad['clips'][0]['frame_end'] = 0
            if change == 'duplicate_clip': bad['clips'].append(copy.deepcopy(bad['clips'][0]))
            if change == 'wrong_destination': bad['destination'] = 'unreal'
            with self.subTest(change=change), self.assertRaises(StudioError): validate_export_profile(bad)

    def test_native_library_replacing_assigned_lists_preserves_logical_names_and_profile(self):
        from blender.asset_export import load_candidate
        _, value = self.inputs(); value['embedded_image_names'] = ['texture']; before = digest(value)
        class NativeID:
            library = None
            animation_data = None
        Object = type('Object', (NativeID,), {'type': 'MESH', 'modifiers': []})
        Action = type('Action', (NativeID,), {})
        Image = type('Image', (NativeID,), {})
        objects = {'cloth': Object(), 'rig': Object()}; actions = {'walk': Action()}; images = {'texture': Image()}
        class Load:
            def __enter__(self):
                self.loaded = SimpleNamespace()
                return SimpleNamespace(objects=list(objects), actions=list(actions), images=list(images)), self.loaded
            def __exit__(self, *args):
                for key, table in (('objects', objects), ('actions', actions), ('images', images)):
                    values = getattr(self.loaded, key)
                    values[:] = [table[name] for name in values]
        scene = SimpleNamespace(unit_settings=SimpleNamespace(), render=SimpleNamespace(),
                                collection=SimpleNamespace(objects=SimpleNamespace(link=lambda obj: None)))
        native_types = SimpleNamespace(Object=Object, Action=Action, Image=Image,
                                      **{name: type(name, (NativeID,), {}) for name in ('CacheFile', 'Sound', 'MovieClip', 'Volume', 'VectorFont')})
        fake = SimpleNamespace(types=native_types, data=SimpleNamespace(libraries=SimpleNamespace(load=lambda *args, **kw: Load()),
                                                                     scenes=SimpleNamespace(new=lambda name: scene)))
        with patch.dict('sys.modules', {'bpy': fake}), patch('blender.body_source.data_ids', side_effect=[set(), {*objects.values(), *actions.values(), *images.values()}]):
            loaded = load_candidate(self.root/'candidate.blend', value, 'Test')
        self.assertEqual(set(loaded['objects']), {'cloth', 'rig'})
        self.assertEqual(set(loaded['actions']), {'walk'}); self.assertEqual(set(loaded['images']), {'texture'})
        self.assertEqual(before, digest(value))

    def test_changed_source_resource_and_unauthenticated_receipt_refused(self):
        project, value = self.inputs(); image = self.root/'texture.png'; image.write_bytes(b'image-fixture')
        value['resources'] = [{'kind': 'IMAGE', 'datablock_name': 'texture', 'file_ref': {'path': image.name, 'sha256': sha(image)}}]
        atomic_json(self.root/'export.json', value)
        self.assertEqual(export_descriptor(project, 'export.json')['profile'], value)
        image.write_bytes(b'changed')
        with self.assertRaisesRegex(StudioError, 'resource'): export_descriptor(project, 'export.json')
        value['resources'] = []; receipt = clip_receipt(value, 'a'*64); receipt['clips'][0]['frame_end'] = 5
        atomic_json(self.root/'motion.json', receipt); value['motion_receipts'] = [{'path': 'motion.json', 'sha256': sha(self.root/'motion.json')}]
        atomic_json(self.root/'export.json', value)
        with self.assertRaisesRegex(StudioError, 'authenticated'): export_descriptor(project, 'export.json')
        value['motion_receipts'] = []; atomic_json(self.root/'export.json', value)
        (self.root/'candidate.blend').write_bytes(b'changed')
        with self.assertRaisesRegex(StudioError, 'exact'): export_descriptor(project, 'export.json')

    def test_shape_key_actions_are_explicit_dependencies_and_use_key_target_slots(self):
        from blender.asset_export import assign_clip, candidate_action_names
        slot = SimpleNamespace(identifier='KEcloth', target_id_type='KEY')
        shape_action = SimpleNamespace(name='observed', slots=[slot])
        rig_action = SimpleNamespace(name='walk', slots=[SimpleNamespace(identifier='OBrig', target_id_type='OBJECT')])
        keys = SimpleNamespace(animation_data=SimpleNamespace(action=shape_action, action_slot=slot),
                               animation_data_create=lambda: None)
        cloth = SimpleNamespace(name='cloth', data=SimpleNamespace(shape_keys=keys), animation_data=None)
        rig = SimpleNamespace(name='rig', data=None, animation_data=SimpleNamespace(action=rig_action))
        self.assertEqual(candidate_action_names([cloth, rig]), ['observed', 'walk'])
        candidate = {'objects': {'cloth': cloth, 'rig': rig}, 'actions': {'observed': shape_action, 'walk': rig_action}}
        clip = {'object_name': 'cloth', 'action_name': 'observed', 'slot_identifier': 'KEcloth', 'animation_target': 'SHAPE_KEYS'}
        assign_clip(candidate, clip)
        self.assertIs(keys.animation_data.action, shape_action); self.assertIs(keys.animation_data.action_slot, slot)
        for change in ('wrong_target', 'missing_key_owner', 'wrong_slot'):
            bad = copy.deepcopy(clip)
            if change == 'wrong_target': bad['animation_target'] = 'OBJECT'
            if change == 'missing_key_owner': bad['object_name'] = 'rig'
            if change == 'wrong_slot': bad['slot_identifier'] = 'KEanother'
            with self.subTest(change=change), self.assertRaises(StudioError): assign_clip(candidate, bad)

    def test_global_clips_bind_body_and_shape_actions_atomically_and_qualify_exact_tracks(self):
        from blender.asset_export import assign_clip
        key_slot = SimpleNamespace(identifier='KEcloth', target_id_type='KEY')
        body_slot = SimpleNamespace(identifier='OBrig', target_id_type='OBJECT')
        key_action = SimpleNamespace(name='observed', slots=[key_slot]); body_action = SimpleNamespace(name='walk', slots=[body_slot])
        key_owner = SimpleNamespace(animation_data=SimpleNamespace(action=None, action_slot=None), animation_data_create=lambda: None)
        cloth = SimpleNamespace(data=SimpleNamespace(shape_keys=key_owner), animation_data=None)
        rig = SimpleNamespace(data=None, animation_data=SimpleNamespace(action=None, action_slot=None), animation_data_create=lambda: None)
        _, value = self.inputs(); value['action_names'].append('observed')
        value['clips'][0]['tracks'] = [{'object_name': 'cloth', 'action_name': 'observed', 'slot_identifier': 'KEcloth', 'animation_target': 'SHAPE_KEYS'}]
        validate_export_profile(value)
        candidate = {'objects': {'cloth': cloth, 'rig': rig}, 'actions': {'walk': body_action, 'observed': key_action}}
        bad = copy.deepcopy(value['clips'][0]); bad['tracks'][0]['slot_identifier'] = 'KEunknown'
        with self.assertRaises(StudioError): assign_clip(candidate, bad)
        self.assertIsNone(rig.animation_data.action); self.assertIsNone(key_owner.animation_data.action)
        assign_clip(candidate, value['clips'][0])
        self.assertIs(rig.animation_data.action, body_action); self.assertIs(key_owner.animation_data.action, key_action)
        hashes = {'walk': 'a'*64, 'observed': 'b'*64}
        receipt = clip_receipt(value, hashes['walk']); receipt['clips'][0]['tracks'][0]['action_sha256'] = hashes['observed']
        receipt.update(native_dispatch_verified=True, clip_measurements_verified=['walk'])
        self.assertEqual(motion_qualification(value, [receipt], hashes)['status'], 'EXACT_CANDIDATE_CLIPS_VERIFIED')
        for change in ('action', 'target', 'slot', 'missing'):
            forged = copy.deepcopy(receipt)
            if change == 'action': forged['clips'][0]['tracks'][0]['action_sha256'] = 'c'*64
            if change == 'target': forged['clips'][0]['tracks'][0]['animation_target'] = 'OBJECT'
            if change == 'slot': forged['clips'][0]['tracks'][0]['slot_identifier'] = 'KEother'
            if change == 'missing': forged['clips'][0].pop('tracks')
            with self.subTest(change=change):
                self.assertEqual(motion_qualification(value, [forged], hashes)['status'], 'NOT_QUALIFIED')
        duplicate = copy.deepcopy(value['clips'][0]); duplicate['tracks'].append(copy.deepcopy(duplicate['tracks'][0]))
        with self.assertRaises(StudioError): clip_tracks(duplicate)

    def test_old_action_candidate_body_scope_and_incomplete_execution_cannot_qualify(self):
        _, value = self.inputs(); valid = dict(clip_receipt(value, 'a'*64), native_dispatch_verified=True, clip_measurements_verified=['walk'])
        self.assertEqual(motion_qualification(value, [valid], {'walk': 'a'*64})['status'], 'EXACT_CANDIDATE_CLIPS_VERIFIED')
        self.assertEqual(motion_qualification(value, [], {'walk': 'a'*64})['status'], 'NOT_QUALIFIED')
        for change in ('candidate', 'action', 'scope', 'last_frame', 'between_frames', 'slot', 'target', 'fps', 'unregistered', 'unmeasured'):
            receipt = copy.deepcopy(valid)
            if change == 'candidate': receipt['candidate']['sha256'] = 'b'*64
            if change == 'action': receipt['clips'][0]['action_sha256'] = 'b'*64
            if change == 'scope': receipt['scope'] = 'EVALUATED_BODY_MOTION_SAMPLES_ONLY'
            if change == 'last_frame': receipt['clips'][0]['executed_times'] = [1, 2, 3, 4, 5]
            if change == 'between_frames': receipt['clips'][0]['executed_times'] = [1, 6]
            if change == 'slot': receipt['clips'][0]['slot_identifier'] = 'OBother'
            if change == 'target': receipt['clips'][0]['animation_target'] = 'SHAPE_KEYS'
            if change == 'fps': receipt['fps'] = 30
            if change == 'unregistered': receipt['native_dispatch_verified'] = False
            if change == 'unmeasured': receipt['clip_measurements_verified'] = []
            with self.subTest(change=change):
                self.assertEqual(motion_qualification(value, [receipt], {'walk': 'a'*64})['status'], 'NOT_QUALIFIED')
        self.assertEqual(motion_qualification(value, [valid, valid], {'walk': 'a'*64})['status'], 'NOT_QUALIFIED')

    def test_manual_motion_claim_cannot_supply_its_own_native_flags(self):
        project, value = self.inputs()
        receipt = clip_receipt(value, 'a'*64); receipt['native_dispatch_verified'] = True
        receipt['clip_measurements_verified'] = ['walk']; receipt['cache_key'] = digest({k: v for k, v in receipt.items() if k != 'cache_key'})
        atomic_json(self.root/'manual-motion.json', receipt)
        value['motion_receipts'] = [{'path': 'manual-motion.json', 'sha256': sha(self.root/'manual-motion.json')}]
        atomic_json(self.root/'export.json', value)
        records = export_descriptor(project, 'export.json')['receipts']
        self.assertFalse(records[0]['native_dispatch_verified'])
        self.assertEqual(motion_qualification(value, records, {'walk': 'a'*64})['status'], 'NOT_QUALIFIED')

    def test_reimport_requires_exact_coverage_topology_and_finite_geometry(self):
        sample = [{'clip_id': 'walk', 'time': 1, 'meshes': {'cloth': {'vertices_cm': [[0., 0., 0.], [1., 0., 0.], [0., 1., 0.]], 'faces': [[0, 1, 2]]}}}]
        self.assertEqual(compare_native_samples(sample, copy.deepcopy(sample), .0001)['status'], 'NATIVE_SAMPLES_MATCH')
        for change in ('missing_sample', 'changed_topology', 'vertex_shift', 'wrong_clip'):
            after = copy.deepcopy(sample)
            if change == 'missing_sample': after = []
            if change == 'changed_topology': after[0]['meshes']['cloth']['faces'] = [[0, 2, 1]]
            if change == 'vertex_shift': after[0]['meshes']['cloth']['vertices_cm'][0][0] += .01
            if change == 'wrong_clip': after[0]['clip_id'] = 'old'
            with self.subTest(change=change), self.assertRaises(StudioError): compare_native_samples(sample, after, .0001)

    def test_client_transport_claim_and_unmeasured_comparison_cannot_create_native_proof(self):
        project, value = self.inputs(); output = self.root/'output.blend'; output.write_bytes(b'copy')
        atomic_json(self.root/'export.json', value); atomic_json(self.root/'snapshots.json', {'fixture': True})
        manifest = {'version': 1, 'status': 'BLENDER_EXPORT_REOPENED', 'destination': 'blender_animation',
                    'reimport': 'EXECUTED', 'candidate': value['source_ref'],
                    'profile': {'path': 'export.json', 'sha256': sha(self.root/'export.json')},
                    'artifact': {'path': 'output.blend', 'sha256': sha(output)},
                    'snapshots_artifact': {'path': 'snapshots.json', 'sha256': sha(self.root/'snapshots.json')},
                    'resources': [], 'animation_qualification': 'NOT_QUALIFIED'}
        manifest['cache_key'] = digest(manifest)
        with self.assertRaisesRegex(StudioError, 'registered'): verify_export_manifest(project, manifest)
        fake_native = {'files': [manifest[k] for k in ('candidate', 'profile', 'artifact', 'snapshots_artifact')]}
        with patch('a3d.export_profiles.registered_export_manifest', return_value=fake_native), self.assertRaisesRegex(StudioError, 'comparison'):
            verify_export_manifest(project, manifest)
        bad = dict(manifest, reimport='NOT_EXECUTED'); bad['cache_key'] = digest({k: v for k, v in bad.items() if k != 'cache_key'})
        with self.assertRaises(StudioError): verify_export_manifest(project, bad)
        output.unlink()
        with self.assertRaises(FileNotFoundError): verify_export_manifest(project, manifest)
