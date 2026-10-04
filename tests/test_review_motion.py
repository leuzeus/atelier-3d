import copy
import math
from unittest.mock import patch
from types import SimpleNamespace

from a3d.core import StudioError, atomic_json, contract, digest, sha
from a3d.review_motion import (_expected_actions, camera_plan, render_schedule,
                                review_motion_descriptor, validate_movie_metadata)
from tests.test_asset_export import profile as export_profile
from tests.test_core import Case
from tests.support import ready_project


def profile(export_ref):
    return {'version': 1, 'export_profile_ref': export_ref, 'object_names': ['cloth'],
            'clip_ids': ['walk'], 'fps': 24, 'views': ['front', 'threequarter'],
            'resolution': [128, 192], 'display': 'NEUTRAL',
            'budgets': {'max_render_frames': 24, 'max_seconds': 60.}}


def measured_receipt(value):
    # Explicit portable verifier output fixture; never written as canonical
    # native evidence. The real descriptor calls export_descriptor first.
    clip = value['clips'][0]
    return {'candidate': value['source_ref'], 'status': 'CLIPS_EXECUTED', 'scope': 'EXACT_CANDIDATE_ANIMATION',
            'fps': value['fps'], 'temporal_coverage': 'COMPLETE', 'native_dispatch_verified': True,
            'clip_measurements_verified': [clip['id']], 'clip_measured_meshes': {clip['id']: ['cloth']},
            'clips': [dict(clip, action_sha256='a'*64, status='EXECUTED_FULL_CLIP', executed_times=[1, 2, 3, 4, 5, 6])]}


class MotionReviewTests(Case):
    def inputs(self):
        project = ready_project(self.root); source = self.root/'source.blend'; source.write_bytes(b'portable-not-native')
        export = export_profile({'path': source.name, 'sha256': sha(source)})
        atomic_json(self.root/'export.json', export)
        review = profile({'path': 'export.json', 'sha256': sha(self.root/'export.json')})
        return project, export, review

    def test_schedule_covers_all_integer_frames_and_encoder_budget(self):
        _, export, review = self.inputs(); before = digest([export, review])
        schedule = render_schedule(review, export)
        self.assertEqual(schedule['clips'][0]['frames'], [1, 2, 3, 4, 5, 6])
        self.assertEqual(schedule['still_frames'], 12); self.assertEqual(schedule['total_render_frames'], 24)
        self.assertEqual(before, digest([export, review]))
        review['budgets']['max_render_frames'] = 23
        with self.assertRaisesRegex(StudioError, 'budget'): render_schedule(review, export)

    def test_source_clip_names_objects_fps_order_and_odd_h264_size_refused(self):
        _, export, value = self.inputs()
        for field, replacement in [('clip_ids', ['invented']), ('clip_ids', []), ('object_names', ['other']),
                                    ('fps', 30), ('resolution', [127, 192])]:
            bad = copy.deepcopy(value); bad[field] = replacement
            with self.subTest(field=field), self.assertRaises(StudioError): render_schedule(bad, export)

    def test_descriptor_rejects_changed_source_profile_before_native_loading(self):
        project, export, review = self.inputs(); atomic_json(self.root/'review.json', review)
        export['fps'] = 30; atomic_json(self.root/'export.json', export)
        with patch('a3d.review_motion.export_descriptor') as native, self.assertRaisesRegex(StudioError, 'changed'):
            review_motion_descriptor(project, 'review.json')
        native.assert_not_called()

    def test_descriptor_requires_canonical_complete_motion_not_a_client_pass(self):
        project, export, review = self.inputs(); atomic_json(self.root/'review.json', review)
        with self.assertRaisesRegex(StudioError, 'canonical'): review_motion_descriptor(project, 'review.json')
        receipt = measured_receipt(export)
        for change in ('unverified', 'incomplete', 'missing_integer', 'different_candidate', 'ambiguous'):
            bad = copy.deepcopy(receipt)
            if change == 'unverified': bad['native_dispatch_verified'] = False
            if change == 'incomplete': bad['temporal_coverage'] = 'INCOMPLETE'
            if change == 'missing_integer': bad['clips'][0]['executed_times'].remove(3)
            if change == 'different_candidate': bad['candidate']['sha256'] = 'b'*64
            rows = [bad, copy.deepcopy(bad)] if change == 'ambiguous' else [bad]
            with self.subTest(change=change), self.assertRaises(StudioError): _expected_actions(export, rows)

    def test_simultaneous_object_and_key_tracks_keep_all_action_content(self):
        _, export, _ = self.inputs()
        export['clips'][0]['tracks'] = [{'object_name': 'cloth', 'action_name': 'cloth-key',
                                        'slot_identifier': 'KEcloth', 'animation_target': 'SHAPE_KEYS'}]
        export['action_names'].append('cloth-key')
        receipt = measured_receipt(export); receipt['clips'][0]['tracks'][0]['action_sha256'] = 'b'*64
        self.assertEqual(_expected_actions(export, [receipt]), {'walk': 'a'*64, 'cloth-key': 'b'*64})
        del receipt['clips'][0]['tracks'][0]['action_sha256']
        with self.assertRaisesRegex(StudioError, 'Action digests'): _expected_actions(export, [receipt])

    def test_camera_bounds_all_frames_and_oblique_projection(self):
        points = [[x, y, z] for x in (-50., 50.) for y in (-10., 30.) for z in (0., 200.)]
        points.append([130., 0., 120.])  # Moving endpoint outside rest bounds.
        for view in ('front', 'side', 'back', 'threequarter'):
            camera = camera_plan(points, view, [128, 192]); self.assertEqual(camera['bounds_cm'][1][0], 130.)
            self.assertGreater(camera['ortho_scale_cm'], max(camera['projected_extents_cm'][:2]))
            self.assertAlmostEqual(sum(x*x for x in camera['right']), 1.)
            self.assertAlmostEqual(sum(a*b for a, b in zip(camera['right'], camera['up'])), 0.)
        for points in ([], [[True, 0., 0.]], [[math.nan, 0., 0.]], [[math.inf, 0., 0.]]):
            with self.assertRaises(StudioError): camera_plan(points, 'front', [128, 192])

    def test_movie_native_duration_size_and_fps_required(self):
        report = validate_movie_metadata(6, [128, 192], 6, [128, 192], 24., 24)
        self.assertEqual(report['status'], 'MOVIE_RELOADED_METADATA_MATCHES')
        for count, size, fps in [(5, [128, 192], 24.), (6, [192, 128], 24.), (True, [128, 192], 24.),
                                 (6, [128, 192], 30.), (6, [128, 192], math.nan)]:
            with self.subTest(count=count, size=size, fps=fps), self.assertRaises(StudioError):
                validate_movie_metadata(count, size, 6, [128, 192], fps, 24)

    def test_blender_video_domain_is_selected_before_dynamic_format(self):
        from blender.review_motion import _configure_movie_output, ReviewStopped
        class ImageSettings:
            def __init__(self): self.media_type = 'IMAGE'; self._format = 'PNG'
            @property
            def file_format(self): return self._format
            @file_format.setter
            def file_format(self, value):
                if value == 'FFMPEG' and self.media_type != 'VIDEO':
                    raise TypeError('FFMPEG is outside the IMAGE domain')
                self._format = value
        render = SimpleNamespace(image_settings=ImageSettings(), ffmpeg=SimpleNamespace())
        _configure_movie_output(render, True)
        self.assertEqual(render.image_settings.media_type, 'VIDEO')
        self.assertEqual(render.image_settings.file_format, 'FFMPEG')
        self.assertEqual(render.ffmpeg.codec, 'H264')
        self.assertEqual(render.ffmpeg.audio_codec, 'NONE')
        unavailable = SimpleNamespace(image_settings=ImageSettings(), ffmpeg=SimpleNamespace())
        with self.assertRaisesRegex(ReviewStopped, 'MOVIE_CODEC_UNAVAILABLE'):
            _configure_movie_output(unavailable, False)
        self.assertEqual(unavailable.image_settings.media_type, 'IMAGE')
        missing_settings = SimpleNamespace(image_settings=ImageSettings(), ffmpeg=None)
        with self.assertRaisesRegex(ReviewStopped, 'MOVIE_CODEC_UNAVAILABLE'):
            _configure_movie_output(missing_settings, True)
        legacy = SimpleNamespace(image_settings=SimpleNamespace(file_format='PNG'), ffmpeg=SimpleNamespace())
        _configure_movie_output(legacy, True)
        self.assertEqual(legacy.image_settings.file_format, 'FFMPEG')

    def test_profile_does_not_accept_claimed_qualification_or_unbounded_values(self):
        _, _, review = self.inputs(); contract('review-motion', review)
        for field, replacement in [('display', 'ARTISTIC_PASS'), ('fps', True), ('resolution', [128, 99999])]:
            bad = copy.deepcopy(review); bad[field] = replacement
            with self.subTest(field=field), self.assertRaises(StudioError): contract('review-motion', bad)
        review['qualified'] = True
        with self.assertRaises(StudioError): contract('review-motion', review)

    def test_descriptor_preserves_sources_and_returns_only_pixel_scope_inputs(self):
        project, export, review = self.inputs(); atomic_json(self.root/'review.json', review)
        protected = {name: sha(self.root/name) for name in ('source.blend', 'export.json', 'review.json')}
        verified = {'profile': export, 'source': self.root/'source.blend', 'receipts': [measured_receipt(export)],
                    'evidence': [review['export_profile_ref'], export['source_ref']]}
        with patch('a3d.review_motion.export_descriptor', return_value=verified):
            descriptor = review_motion_descriptor(project, 'review.json')
        self.assertEqual(descriptor['expected_actions'], {'walk': 'a'*64})
        self.assertEqual(descriptor['max_sample_vertex_frames'], 10000000)
        self.assertEqual(protected, {name: sha(self.root/name) for name in protected})
