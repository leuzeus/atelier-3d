from unittest.mock import patch

from a3d.core import StudioError, sha
from a3d.guard import admit_operation, code_for
from blender.operations import dispatch
from tests.support import ready_project
from tests import test_pipeline_guards as hook_tests
from tests.test_core import Case


class ViewportAdmission(Case):
    def setUp(self):
        super().setUp()
        self.project = ready_project(self.root, True)
        self.args = {'component_id': 'garment.coat', 'object_name': 'A3D.garment.coat.001'}

    def test_framing_does_not_require_or_fabricate_acceptance(self):
        before = sha(self.project.db)
        admit_operation(self.project, 'frame_view', self.args)
        self.assertEqual(sha(self.project.db), before)
        with patch('blender.viewport.frame_view', return_value={'operation': 'frame_view'}) as frame:
            self.assertEqual(dispatch(str(self.root), 'frame_view', self.args), {'operation': 'frame_view'})
            frame.assert_called_once_with(str(self.root), **self.args)
        self.assertEqual(sha(self.project.db), before)
        self.assertFalse((self.project.data / 'blender/last-checkpoint.json').exists())

    def test_diagnostic_framing_during_failure_and_complete(self):
        with self.project.transaction() as db:
            state = self.project.state(db)
            state['pending_blender_operation'] = {'status': 'failed'}
            state['gates'].pop('construction')
            self.project.save(db, state, 'synthetic_failure', {})
        for stage in ('RECONSTRUCTING', 'COMPLETE', 'FAILED', 'BLOCKED'):
            with self.project.transaction() as db:
                state = self.project.state(db); state['stage'] = stage
                self.project.save(db, state, 'synthetic_stage', {})
            before = sha(self.project.db)
            admit_operation(self.project, 'frame_view', self.args)
            self.assertEqual(sha(self.project.db), before)
            with self.assertRaises(StudioError):
                admit_operation(self.project, 'resume', {})

    def test_unknown_targets_edit_flags_outputs_and_invalid_names_refused(self):
        for args in ({**self.args, 'component_id': 'foreign.mesh'},
                     {**self.args, 'object_name': ''}, {**self.args, 'object_name': '\n'},
                     {**self.args, 'object_name': 42}, {**self.args, 'object_name': 'a' * 256},
                     {**self.args, 'allow_edits': False}, {**self.args, 'output': 'image.png'},
                     {'component_id': 'garment.coat'}):
            with self.subTest(args=args), self.assertRaises(StudioError):
                admit_operation(self.project, 'frame_view', args)
        with self.project.transaction() as db:
            state = self.project.state(db); state['stage'] = 'PACKAGED'
            self.project.save(db, state, 'synthetic_unbuilt', {})
        with self.assertRaises(StudioError):
            admit_operation(self.project, 'frame_view', self.args)

    def test_failure_creates_no_pending_mutation(self):
        before = sha(self.project.db)
        with patch('blender.viewport.frame_view', side_effect=StudioError('foreign scene')):
            with self.assertRaisesRegex(StudioError, 'foreign scene'):
                dispatch(str(self.root), 'frame_view', self.args)
        self.assertEqual(sha(self.project.db), before)


class ViewportHooks(Case):
    def setUp(self):
        super().setUp()
        import importlib.util
        from a3d.core import ROOT
        spec = importlib.util.spec_from_file_location('viewport_hook', ROOT / 'hooks/handler.py')
        self.hook = importlib.util.module_from_spec(spec); spec.loader.exec_module(self.hook)
    event = hook_tests.HookGuards.event
    def test_guarded_frame_code_admitted_direct_navigation_and_edit_denied(self):
        ready_project(self.root, True)
        args = {'component_id': 'garment.coat', 'object_name': 'A3D.garment.coat.001'}
        code = code_for(str(self.root), 'frame_view', args)
        result = self.hook.handle(self.event('mcp__blender_lab__execute_blender_code', {'code': code}))
        self.assertNotIn('permissionDecision', result['hookSpecificOutput'])
        for edits in (False, True):
            result = self.hook.handle(self.event('mcp__blender_lab__jump_to_view3d_object_by_name',
                                      {'name': args['object_name'], 'allow_edits': edits}))
            self.assertEqual(result['hookSpecificOutput']['permissionDecision'], 'deny')
            self.assertIn('frame_view', result['hookSpecificOutput']['permissionDecisionReason'])
        for name, args in (('set_object_transform', {'name': 'A3D.garment.coat.001'}),
                           ('execute_blender_code', {'code': 'import bpy'})):
            result = self.hook.handle(self.event('mcp__blender_lab__' + name, args))
            self.assertEqual(result['hookSpecificOutput']['permissionDecision'], 'deny')
        result = self.hook.handle(self.event('mcp__blender_lab__get_screenshot_of_area_as_image', {'area_ui_type': 'VIEW_3D'}))
        self.assertNotIn('permissionDecision', result['hookSpecificOutput'])
