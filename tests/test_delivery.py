from a3d.core import StudioError, atomic_json, sha
from a3d.delivery import delivery_profile, verify_delivery_manifest
from tests.test_core import Case
from tests.support import ready_project


class DeliveryTests(Case):
    def test_missing_reimport_and_missing_resource_cannot_qualify_delivery(self):
        project = ready_project(self.root)
        with self.assertRaises(StudioError): verify_delivery_manifest(project, {'destination':'blender_animation','reimport':'NOT_EXECUTED'})
        with self.assertRaises((StudioError,FileNotFoundError)):
            verify_delivery_manifest(project, {'destination':'blender_animation','reimport':'EXECUTED','clips_executed':['walk'],
                                               'artifacts':[{'path':'missing.blend','sha256':'a'*64}]})

    def test_changed_candidate_invalidates_review_profile(self):
        project = ready_project(self.root); source = self.root/'body.blend'; source.write_bytes(b'fixture')
        profile = {'version':1,'source_ref':{'path':'body.blend','sha256':sha(source)},'object_names':['body'],
                   'frame':1,'resolution':[256,256],'views':['front','back'],'max_seconds':30.}
        atomic_json(self.root/'review.json',profile)
        self.assertEqual(delivery_profile(project,'review.json')[0],profile)
        source.write_bytes(b'changed')
        with self.assertRaises(StudioError): delivery_profile(project,'review.json')

    def test_client_reimport_and_clip_flags_cannot_establish_delivery(self):
        project = ready_project(self.root)
        source = self.root/'export.blend'; source.write_bytes(b'client fixture')
        with self.assertRaises(StudioError):
            verify_delivery_manifest(project, {
                'destination': 'blender_animation', 'reimport': 'EXECUTED',
                'clips_executed': ['walk'], 'animation_qualification': 'PASS',
                'artifacts': [{'path': source.name, 'sha256': sha(source)}]})
