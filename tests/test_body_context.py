import copy

from a3d.body_context import body_context_descriptor
from a3d.core import StudioError, atomic_json, digest, read_json, sha
from tests.test_core import Case
from tests.test_body_target import target_fixture
from tests.support import ready_project


def context_profile(receipt_ref, object_name='A3D.BodyTarget.Test180'):
    return {'version': 1, 'body_target_receipt': receipt_ref, 'object_name': object_name,
            'collision': {'outer_thickness_cm': .1, 'inner_thickness_cm': .1},
            'provenance': {'source_ref': 'EXPLICIT_SYNTHETIC_TEST_ONLY_BODY_CONTEXT',
                           'purpose': 'EXACT_MEASURED_BODY_FOR_GARMENT_PREPARATION'}}


def body_inputs(project):
    """Portable identity fixture only; no claim of actual native execution."""
    from a3d.anatomy_profile import profile_mesh
    from a3d.head_surface import measured_head_surface
    from a3d.shoulder_surface import measured_surface_shoulders
    from tests.test_anatomy_profile import fixture
    root = project.root; source = root/'source-body.blend'; source.write_bytes(b'synthetic-portable-source')
    selected = {'version': 1, 'source_blend': source.name, 'source_sha256': sha(source),
                'source_ref': 'explicit portable fixture only', 'frame': 1, 'unit_scale_m': 1.,
                'meshes': ['source-body'], 'dependencies': [], 'reference_object': 'REFERENCE'}
    atomic_json(root/'selection.json', selected)
    adapter = {'source_ref': {'path': source.name, 'sha256': sha(source)}, 'source_geometry_sha256': 'c'*64}
    atomic_json(root/'anatomy.json', adapter)
    atomic_json(root/'target.json', target_fixture(sha(root/'selection.json'), sha(root/'anatomy.json')))
    geometry, options = fixture(); geometry['source_sha256'] = sha(source); geometry['face_sets'] = [1]*len(geometry['faces'])
    points = {'shoulder.left': [-10., 0., 175.], 'shoulder.right': [10., 0., 175.],
              'elbow.left': [-12., 0., 120.], 'elbow.right': [12., 0., 120.],
              'wrist.left': [-14., 0., 85.], 'wrist.right': [14., 0., 85.], 'head.center': [0., 0., 165.]}
    geometry['rig_landmarks'] = {name: {'point_cm': value, 'source_ref': 'explicit synthetic fixture'} for name, value in points.items()}
    options.update(torso_faces=list(range(len(geometry['faces']))), segmentation_source_ref='explicit test segmentation')
    triangles = []
    for face in geometry['faces']:
        triangles += [[face[0], face[i], face[i+1]] for i in range(1, len(face)-1)]
    profile = measured_head_surface(profile_mesh(geometry, options), geometry, options['torso_faces'], adapter['source_ref'])
    profile = measured_surface_shoulders(profile, geometry, triangles)
    artifact = root/'target-body.blend'; artifact.write_bytes(b'portable-native-artifact-identity-fixture-only')
    artifacts = {}
    for name, value in [('geometry', geometry), ('source-geometry', geometry), ('profile', profile), ('options', options)]:
        path = root/(name+'.json'); atomic_json(path, value); artifacts[name] = {'path': path.name, 'sha256': sha(path)}
    receipt = {'version': 1, 'status': 'NATIVE_BODY_TARGET_MEASURED', 'native_reopened': True,
               'source_face_ids_preserved': True, 'geometry_sha256': profile['geometry_sha256'], 'pose_sha256': profile['pose_sha256'],
               'profile_cache_key': profile['cache_key'], 'artifact': {'path': artifact.name, 'sha256': sha(artifact)}, 'artifacts': artifacts,
               'evidence': {name: {'path': name+'.json', 'sha256': sha(root/(name+'.json'))} for name in ('selection', 'target', 'anatomy')}}
    receipt['evidence']['adapter'] = receipt['evidence'].pop('anatomy')
    receipt['cache_key'] = digest(receipt); path = root/'body-receipt.json'; atomic_json(path, receipt)
    context = context_profile({'path': path.name, 'sha256': sha(path)})
    atomic_json(root/'context.json', context)
    return context, receipt


class BodyContextTests(Case):
    def test_descriptor_is_read_only_and_preserves_exact_source_profile_regions(self):
        project = ready_project(self.root, True); context, _ = body_inputs(project); database = sha(project.db)
        result = body_context_descriptor(project, 'context.json')
        self.assertEqual(result['context'], context); self.assertEqual(sha(project.db), database)
        self.assertEqual(result['profile']['geometry_sha256'], digest([result['geometry']['vertices_cm'], result['geometry']['faces']]))
        changed = copy.deepcopy(context); changed['collision']['outer_thickness_cm'] = .2
        atomic_json(project.root/'other-context.json', changed)
        self.assertNotEqual(result['binding_sha256'], body_context_descriptor(project, 'other-context.json')['binding_sha256'])

    def test_missing_or_changed_body_inputs_and_impossible_collision_parameters_refused(self):
        project = ready_project(self.root, True); context, receipt = body_inputs(project)
        for change in ('artifact', 'receipt', 'source', 'parameters', 'escape', 'incomplete'):
            with self.subTest(change=change):
                original = {p: p.read_bytes() for p in project.root.glob('*.json')}; body_bytes = (project.root/'target-body.blend').read_bytes()
                source_bytes = (project.root/'source-body.blend').read_bytes(); value = copy.deepcopy(context)
                if change == 'artifact': (project.root/'target-body.blend').write_bytes(b'changed')
                if change == 'receipt': atomic_json(project.root/'body-receipt.json', dict(receipt, native_reopened=False))
                if change == 'source': (project.root/'source-body.blend').write_bytes(b'changed')
                if change == 'parameters': value['collision']['outer_thickness_cm'] = .00001
                if change == 'escape': value['body_target_receipt']['path'] = '../outside.json'
                if change == 'incomplete':
                    bad = copy.deepcopy(receipt); bad['status'] = 'NATIVE_BODY_TARGET_INCOMPLETE'
                    bad['cache_key'] = digest({k: v for k, v in bad.items() if k != 'cache_key'})
                    atomic_json(project.root/'body-receipt.json', bad); value['body_target_receipt']['sha256'] = sha(project.root/'body-receipt.json')
                atomic_json(project.root/'context.json', value)
                with self.assertRaises((StudioError, FileNotFoundError)): body_context_descriptor(project, 'context.json')
                for path, data in original.items(): path.write_bytes(data)
                (project.root/'target-body.blend').write_bytes(body_bytes); (project.root/'source-body.blend').write_bytes(source_bytes)

    def test_rehashed_source_regions_pose_and_profile_frame_still_require_correspondence(self):
        project = ready_project(self.root, True)
        for change in ('regions', 'pose', 'frame'):
            context, receipt = body_inputs(project)
            name = 'profile' if change == 'frame' else 'geometry'; path = project.root/receipt['artifacts'][name]['path']
            value = read_json(path)
            if change == 'regions': value['face_sets'][0] += 1
            if change == 'pose': value['pose_sha256'] = 'd'*64
            if change == 'frame': value['frame']['origin_cm'][2] += 1.
            atomic_json(path, value); receipt['artifacts'][name]['sha256'] = sha(path)
            receipt['cache_key'] = digest({k: v for k, v in receipt.items() if k != 'cache_key'})
            atomic_json(project.root/'body-receipt.json', receipt); context['body_target_receipt']['sha256'] = sha(project.root/'body-receipt.json')
            atomic_json(project.root/'context.json', context)
            with self.subTest(change=change), self.assertRaises(StudioError): body_context_descriptor(project, 'context.json')
