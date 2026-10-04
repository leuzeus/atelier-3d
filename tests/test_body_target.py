import copy
import math

from a3d.body_target import measurement_compatibility, stature_target, target_descriptor, validate_target
from a3d.core import StudioError, atomic_json, digest, sha
from tests.test_core import Case
from tests.support import ready_project


def target_fixture(selection_sha='a'*64, adapter_sha='b'*64):
    return {'version': 1, 'selection_sha256': selection_sha,
            'anatomy_adapter': {'path': 'anatomy.json', 'sha256': adapter_sha},
            'orientation': {'up_axis': [0., 0., 1.], 'forward_axis': [0., -1., 0.], 'origin_cm': [0., 0., 0.]},
            'target_stature_cm': 180.,
            'provenance': {'source_ref': 'explicit approved test target', 'measurements_status': 'DECLARED_FOR_REVIEW'},
            'tolerances': {'stature_cm': .0001, 'floor_cm': .0001, 'roundtrip_cm': .0001, 'girth_cm': .1},
            'budgets': {'max_iterations': 15, 'max_evaluations': 150, 'finite_difference_step': .001,
                        'damping': .001, 'line_search_steps': 8, 'min_scale': .85, 'max_scale': 1.15}}


class BodyTargetTests(Case):
    def test_height_only_target_has_declared_provenance_and_independent_policies(self):
        selected = {'selection': {'path': 'selection.json', 'sha256': 'a'*64},
                    'anatomy_adapter': {'path': 'anatomy.json', 'sha256': 'b'*64}}
        orientation = {'up_axis': [0., 0., 1.], 'forward_axis': [0., -1., 0.]}
        target = stature_target(selected, orientation, 180., 'human explicitly requests 180 cm')
        self.assertNotIn('target_girths_cm', target)
        self.assertEqual(target['provenance']['measurements_status'], 'DECLARED_FOR_REVIEW')
        self.assertEqual(target['orientation']['origin_cm'], [0., 0., 0.])
        target['budgets']['max_iterations'] = 2
        self.assertEqual(stature_target(selected, orientation, 180., 'another declaration')['budgets']['max_iterations'], 15)
        self.assertNotIn('origin_cm', orientation)

    def test_head_section_is_measured_and_bound_to_exact_base_profile(self):
        from a3d.anatomy_profile import profile_mesh
        from a3d.head_surface import head_surface_section, measured_head_surface
        from tests.test_anatomy_profile import fixture
        geometry, options = fixture()
        geometry['rig_landmarks'] = {'head.center': {'point_cm': [0., 0., 165.], 'source_ref': 'synthetic-source-head-center'}}
        profile = profile_mesh(geometry, options); before = digest([profile, geometry])
        result = measured_head_surface(profile, geometry, list(range(len(geometry['faces']))), 'synthetic-head-only-region')
        section = head_surface_section(result)
        self.assertEqual(section['status'], 'MEASURED')
        self.assertGreater(section['girth_cm'], 90.)
        self.assertEqual(section['full_head_envelope'], 'NOT_QUALIFIED')
        self.assertEqual(before, digest([profile, geometry]))
        for change in ('curve', 'pose', 'head_center', 'frame', 'cache'):
            bad = copy.deepcopy(result)
            if change == 'curve': bad['surface_sections']['head']['curve_cm'][0][0] += .01
            if change == 'pose': bad['pose_sha256'] = 'c'*64
            if change == 'head_center': bad['landmarks']['head.center']['point_cm'][2] += .01
            if change == 'frame': bad['frame']['origin_cm'][2] += 1.
            if change == 'cache': bad['cache_key'] = 'changed'
            with self.subTest(change=change), self.assertRaises(StudioError): head_surface_section(bad)
        open_section = measured_head_surface(profile, geometry, list(range(1, len(geometry['faces']))), 'open-synthetic-head-region')
        self.assertEqual(head_surface_section(open_section)['status'], 'NOT_QUALIFIED')

    def test_target_bound_to_exact_selection_adapter_source_and_project(self):
        project = ready_project(self.root, True)
        source = project.root/'body.blend'; source.write_bytes(b'explicit source fixture')
        selected = {'version': 1, 'source_blend': 'body.blend', 'source_sha256': sha(source),
                    'source_ref': 'reviewed source fixture', 'frame': 1, 'unit_scale_m': 1.,
                    'meshes': ['body'], 'dependencies': [], 'reference_object': 'REFERENCE'}
        selection_path = project.root/'selection.json'; atomic_json(selection_path, selected)
        adapter = {'source_ref': {'path': 'body.blend', 'sha256': sha(source)}, 'source_geometry_sha256': 'c'*64}
        adapter_path = project.root/'anatomy.json'; atomic_json(adapter_path, adapter)
        target = target_fixture(sha(selection_path), sha(adapter_path)); atomic_json(project.root/'target.json', target)
        db = sha(project.db)
        result = target_descriptor(project, 'selection.json', 'target.json')
        self.assertEqual(result['evidence']['selection']['sha256'], sha(selection_path))
        self.assertEqual(result['target']['target_stature_cm'], 180.)
        self.assertEqual(sha(project.db), db)
        for change in ('selection', 'adapter', 'source', 'adapter_source', 'escape'):
            changed_target = copy.deepcopy(target)
            atomic_json(selection_path, selected); atomic_json(adapter_path, adapter); source.write_bytes(b'explicit source fixture')
            if change == 'selection': atomic_json(selection_path, dict(selected, frame=2))
            if change == 'adapter': atomic_json(adapter_path, dict(adapter, altered=True))
            if change == 'source': source.write_bytes(b'changed source')
            if change == 'adapter_source':
                atomic_json(adapter_path, dict(adapter, source_ref={'path': 'other.blend', 'sha256': 'f'*64}))
                changed_target['anatomy_adapter']['sha256'] = sha(adapter_path)
            if change == 'escape': changed_target['anatomy_adapter']['path'] = '../outside.json'
            atomic_json(project.root/'target.json', changed_target)
            with self.subTest(change=change), self.assertRaises(StudioError):
                target_descriptor(project, 'selection.json', 'target.json')

    def test_target_requires_explicit_finite_inputs_and_supported_controls(self):
        target = target_fixture(); self.assertEqual(validate_target(target), target)
        failures = [('target_stature_cm', True), ('target_stature_cm', math.nan),
                    ('target_stature_cm', 401.), ('target_girths_cm', {'shoulder_width': 40.}),
                    ('provenance', {'source_ref': 'inferred'}), ('extra', 'unapproved')]
        for key, value in failures:
            bad = copy.deepcopy(target); bad[key] = value
            with self.subTest(key=key), self.assertRaises(StudioError): validate_target(bad)
        bad = copy.deepcopy(target); bad['orientation']['forward_axis'] = [0., 0., 1.]
        with self.assertRaises(StudioError): validate_target(bad)
        bad = copy.deepcopy(target); bad['budgets']['min_scale'] = bad['budgets']['max_scale'] = 1.
        with self.assertRaises(StudioError): validate_target(bad)

    def test_capacity_checks_do_not_infer_ease_or_accept_fitting(self):
        profile = {'cache_key': 'exact-profile', 'stature_cm': 180., 'landmarks': {'chest': {'girth_cm': 100.}}}
        capacities = [{'measurement': 'chest', 'minimum_cm': 95., 'maximum_cm': 102., 'source_ref': 'approved-source-section'},
                      {'measurement': 'waist', 'minimum_cm': 70., 'maximum_cm': 80., 'source_ref': 'approved-waist-section'},
                      {'measurement': 'stature', 'minimum_cm': 170., 'maximum_cm': 179., 'source_ref': 'approved-length'}]
        result = measurement_compatibility(profile, capacities)
        self.assertEqual({row['measurement']: row['status'] for row in result['checks']},
                         {'chest': 'WITHIN_DECLARED_CAPACITY', 'waist': 'MISSING_BODY_MEASUREMENT',
                          'stature': 'OUTSIDE_DECLARED_CAPACITY'})
        self.assertEqual(result['acceptance'], 'NOT_GRANTED')
        self.assertEqual(result['fitting'], 'NOT_EXECUTED')
        self.assertEqual(measurement_compatibility(profile, [])['status'], 'NO_CAPACITIES_PROVIDED')
        for invalid in ([dict(capacities[0], maximum_cm=math.nan)], [dict(capacities[0], source_ref='')],
                        [dict(capacities[0], minimum_cm=103.)]):
            with self.assertRaises(StudioError): measurement_compatibility(profile, invalid)
