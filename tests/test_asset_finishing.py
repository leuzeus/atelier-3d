import copy
import math

from a3d.asset_finishing import assess_lod, finishing_descriptor, source_uv_identity, validate_finishing_profile
from a3d.core import StudioError, atomic_json, sha
from tests.test_core import Case
from tests.support import ready_project


def profile(source_ref, uv_sha):
    return {'version': 1, 'source_ref': source_ref, 'object_names': ['cloth', 'buckle'],
            'dependency_names': [], 'action_names': [], 'embedded_image_names': [], 'resources': [],
            'unit_scale_m': 1., 'fps': 24, 'reference_frame': 1,
            'operations': [{'object_name': 'cloth', 'role': 'PATTERN_SEWN',
                            'uv': {'method': 'PRESERVE_SOURCE', 'layer_name': 'SourcePattern', 'source_uv_sha256': uv_sha}, 'lods': []},
                           {'object_name': 'buckle', 'role': 'RIGID',
                            'uv': {'method': 'SMART_PROJECT', 'layer_name': 'RigidUV', 'angle_limit_degrees': 66., 'island_margin': .02},
                            'lods': [{'id': 'buckle-lod1', 'ratio': .5, 'max_faces': 10, 'max_geometry_error_cm': .1}]}],
            'budgets': {'max_seconds': 60., 'max_lod_clones': 1, 'max_error_samples': 1000}}


class AssetFinishingTests(Case):
    def test_sewn_uv_remap_lod_and_wrong_object_refused(self):
        value = profile({'path': 'candidate.blend', 'sha256': 'a'*64}, 'b'*64)
        self.assertEqual(validate_finishing_profile(value), value)
        for change in ('sewn_uv', 'sewn_lod', 'unknown_object', 'duplicate_operation', 'budget'):
            bad = copy.deepcopy(value)
            if change == 'sewn_uv': bad['operations'][0]['uv'] = copy.deepcopy(bad['operations'][1]['uv'])
            if change == 'sewn_lod': bad['operations'][0]['lods'] = copy.deepcopy(bad['operations'][1]['lods'])
            if change == 'unknown_object': bad['operations'][0]['object_name'] = 'unknown'
            if change == 'duplicate_operation': bad['operations'].append(copy.deepcopy(bad['operations'][0]))
            if change == 'budget': bad['budgets']['max_lod_clones'] = 0
            with self.subTest(change=change), self.assertRaises(StudioError): validate_finishing_profile(bad)

    def test_source_uv_winding_corner_count_and_nonfinite_values_are_bound(self):
        faces = [[0, 1, 2]]; values = [[0., 0.], [1., 0.], [0., 1.]]
        self.assertNotEqual(source_uv_identity(faces, values), source_uv_identity([[0, 2, 1]], values))
        self.assertNotEqual(source_uv_identity(faces, values), source_uv_identity(faces, list(reversed(values))))
        with self.assertRaises(StudioError): source_uv_identity(faces, values[:2])
        with self.assertRaises(StudioError): source_uv_identity(faces, [[math.nan, 0.], *values[1:]])

    def test_changed_native_candidate_refuses_finishing(self):
        project = ready_project(self.root); source = self.root/'candidate.blend'; source.write_bytes(b'native-fixture')
        value = profile({'path': source.name, 'sha256': sha(source)}, 'b'*64)
        atomic_json(self.root/'finish.json', value)
        self.assertEqual(finishing_descriptor(project, 'finish.json')['profile'], value)
        source.write_bytes(b'changed')
        with self.assertRaisesRegex(StudioError, 'exact'): finishing_descriptor(project, 'finish.json')

    def test_lod_qualifies_only_actual_declared_surface_samples_and_budgets(self):
        request = {'id': 'buckle-lod1', 'ratio': .5, 'max_faces': 10, 'max_geometry_error_cm': .1}
        measured = {'source_faces': 20, 'source_triangles': 40, 'lod_faces': 9, 'lod_triangles': 18,
                    'expected_samples': 100, 'executed_samples': 100, 'max_surface_error_cm': .03}
        result = assess_lod(request, measured)
        self.assertEqual(result['status'], 'LOD_GEOMETRY_WITHIN_BUDGET')
        self.assertEqual(result['observed_triangle_ratio'], .45)
        self.assertEqual(result['engine_qualification'], 'NOT_QUALIFIED')
        for field, value, expected in [('lod_faces', 11, 'NEEDS_CORRECTION'), ('max_surface_error_cm', .2, 'NEEDS_CORRECTION'),
                                       ('executed_samples', 99, 'INCOMPLETE'), ('max_surface_error_cm', None, 'INCOMPLETE')]:
            with self.subTest(field=field):
                self.assertEqual(assess_lod(request, dict(measured, **{field: value}))['status'], expected)
        with self.assertRaises(StudioError): assess_lod(request, dict(measured, max_surface_error_cm=math.nan))
