import copy
from unittest.mock import patch

from a3d.core import StudioError, atomic_json, sha
from a3d.animated_delivery import animated_delivery_descriptor, compare_inventory, rigid_leaf, source_inventory
from tests.test_core import Case
from tests.support import ready_project


def profile(refs, inventory):
    return {'version': 1, 'purpose': 'TEST_ONLY', 'expected_inventory': inventory,
            'clips': [{'id': 'walk', 'source_receipts': refs}], 'rigid_parts': [], 'source_resources': [],
            'geometry_tolerance_cm': .0001, 'budgets': {'max_seconds': 60., 'max_samples': 30, 'max_cache_vertex_frames': 100000}}


class AnimatedDeliveryTests(Case):
    def inputs(self, count=2):
        project = ready_project(self.root); leaves = {}; refs = []; expected = []
        for i in range(count):
            cid = 'cloth'+str(i)
            observation = self.root/(cid+'.observations.json'); atomic_json(observation, {'frames': [{'frame': value} for value in (1, 2, 3)]})
            result = {'purpose': 'TEST_ONLY', 'clip': {'frame_start': 1, 'frame_end': 3, 'fps': 24},
                      'object_inventory': {'garment': {'component_id': cid, 'object_name': cid, 'source_pieces': [cid+'.piece'],
                                                      'package_sha256': 'a'*64, 'source_face_provenance_sha256': 'b'*64},
                                           'body': {'object_name': 'body', 'motion_binding': {'body': 'source', 'action': 'walk'},
                                                    'body_action': {'object_name': 'rig', 'action_name': 'walk'}}},
                      'observations_artifact': {'path': observation.name, 'sha256': sha(observation)}}
            file = self.root/(cid+'.receipt.json'); atomic_json(file, result)
            reference = {'path': file.name, 'sha256': sha(file)}; refs.append(reference)
            leaves[file.name] = result
            expected.append({'component_id': cid, 'kind': 'TEXTILE', 'source_pieces': [cid+'.piece'], 'package_sha256': 'a'*64})
        return project, profile(refs, expected), leaves

    def compile(self, project, value, leaves):
        file = self.root/'composition.json'; atomic_json(file, value)
        with patch('a3d.garment_motion.canonical_garment_clip', side_effect=lambda project, ref: (leaves[ref['path']], {'receipt': ref})):
            return animated_delivery_descriptor(project, file.name)

    def test_inventory_cannot_duplicate_omit_merge_change_cut_or_package(self):
        _, value, _ = self.inputs(); expected = value['expected_inventory']
        self.assertEqual(compare_inventory(expected, copy.deepcopy(expected))['textile_piece_count'], 2)
        for change in ('duplicate', 'missing', 'merged', 'cut', 'package'):
            actual = copy.deepcopy(expected)
            if change == 'duplicate': actual.append(copy.deepcopy(actual[0]))
            if change == 'missing': actual.pop()
            if change == 'merged': actual[0]['source_pieces'].extend(actual.pop()['source_pieces'])
            if change == 'cut': actual[0]['source_pieces'] = ['invented']
            if change == 'package': actual[0]['package_sha256'] = 'c'*64
            with self.subTest(change=change), self.assertRaises(StudioError): compare_inventory(expected, actual)

    def test_production_inventory_is_derived_from_board_packages_and_exact_compiled_connections(self):
        import json
        import zipfile
        from types import SimpleNamespace
        from tests.test_production_dossier import fixture
        from a3d.production_dossier import compile_production_dossier
        dossier, packages, spec = fixture()
        dossier_path = self.root/'dossier.json'; atomic_json(dossier_path, dossier)
        dossier_ref = {'path': dossier_path.name, 'sha256': sha(dossier_path)}
        package_path = self.root/'coat.garmentpkg'
        with zipfile.ZipFile(package_path, 'w') as archive:
            archive.writestr('garment.json', json.dumps(packages['garment.coat']['data']))
        coat_ref = {'path': package_path.name, 'sha256': sha(package_path)}
        packages['garment.coat']['source_ref'] = coat_ref
        spec['packages'][0]['source_ref'] = coat_ref; spec['source_ref'] = dossier_ref
        assembly = compile_production_dossier(dossier, packages, spec)['assembly_spec']
        assembly_path = self.root/'assembly.json'; atomic_json(assembly_path, assembly)
        rigid = self.root/'buckle.partpkg'; rigid.write_bytes(b'fixture-standin-only')
        state = {'components': {'garment.coat': {'route': {'selected': 'PATTERN_SEWN'}, 'package': coat_ref},
                                'rigid.component': {'route': {'selected': 'MULTIVIEW_PART'}, 'package': {'path': rigid.name, 'sha256': sha(rigid)}}}}
        project = SimpleNamespace(root=self.root, state=lambda: state)
        board = {'dossier_path': dossier_path.name, 'dependencies': {dossier_path.name: sha(dossier_path)}}
        value = {'purpose': 'GARMENT_CANDIDATE', 'dossier_ref': dossier_ref,
                 'assembly_plan_ref': {'path': assembly_path.name, 'sha256': sha(assembly_path)}}
        with patch('a3d.planning.require_board', return_value=board):
            expected, actual_assembly = source_inventory(project, value)
            self.assertEqual(len(expected), 2); self.assertEqual(actual_assembly, assembly)
            self.assertEqual(compare_inventory(expected, expected)['textile_piece_count'], 4)
            self.assertNotIn('source_mutated', assembly)
            changed = copy.deepcopy(assembly); changed['links'][0]['kind'] = 'closure'
            atomic_json(assembly_path, changed); value['assembly_plan_ref']['sha256'] = sha(assembly_path)
            with self.assertRaisesRegex(StudioError, 'approved source connection'): source_inventory(project, value)
            atomic_json(assembly_path, assembly); value['assembly_plan_ref']['sha256'] = sha(assembly_path)
            value['expected_inventory'] = [expected[0]]
            with self.assertRaisesRegex(StudioError, 'Client inventory'): source_inventory(project, value)

    def test_whole_clip_body_binding_full_coverage_and_reference_budget_required(self):
        project, value, leaves = self.inputs(); compiled = self.compile(project, value, leaves)
        self.assertEqual(compiled['sample_count'], 3)
        self.assertEqual(compiled['clips'][0]['inventory']['status'], 'TEST_INVENTORY_ONLY')
        for change in ('body', 'bounds', 'fps', 'missing_terminal', 'duplicate_component', 'cut', 'budget', 'reserved'):
            candidate = copy.deepcopy(value); source = copy.deepcopy(leaves); second = source['cloth1.receipt.json']
            if change == 'body': second['object_inventory']['body']['motion_binding']['body'] = 'changed'
            if change == 'bounds': second['clip']['frame_end'] = 2
            if change == 'fps': second['clip']['fps'] = 30
            if change == 'missing_terminal':
                ref = second['observations_artifact']; atomic_json(self.root/ref['path'], {'frames': [{'frame': 1}, {'frame': 2}]})
                ref['sha256'] = sha(self.root/ref['path'])
            if change == 'duplicate_component': second['object_inventory']['garment']['component_id'] = 'cloth0'
            if change == 'cut': second['object_inventory']['garment']['source_pieces'] = ['imaginary']
            if change == 'budget': candidate['budgets']['max_samples'] = 3
            if change == 'reserved': candidate['clips'][0]['id'] = 'reference'
            with self.subTest(change=change), self.assertRaises(StudioError): self.compile(project, candidate, source)
            # Reset the source observation changed by this negative case.
            ref = leaves['cloth1.receipt.json']['observations_artifact']
            atomic_json(self.root/ref['path'], {'frames': [{'frame': n} for n in (1, 2, 3)]})

    def test_test_only_native_leaf_cannot_be_promoted_by_client_production_purpose(self):
        project, value, leaves = self.inputs(); value['purpose'] = 'GARMENT_CANDIDATE'
        value['dossier_ref'] = value['assembly_plan_ref'] = value['clips'][0]['source_receipts'][0]
        with patch('a3d.animated_delivery.source_inventory', return_value=(value['expected_inventory'], {})):
            with self.assertRaisesRegex(StudioError, 'TEST_ONLY'): self.compile(project, value, leaves)

    def test_inspected_rigid_has_no_production_placement_or_invented_animated_attachment(self):
        project, value, _ = self.inputs(1); artifact = self.root/'rigid.blend'; artifact.write_bytes(b'fixture')
        result = {'status': 'RIGID_GEOMETRY_INSPECTED', 'component_id': 'buckle', 'piece_id': 'buckle-source',
                  'artifact': {'path': artifact.name, 'sha256': sha(artifact)},
                  'object_names': ['buckle'], 'accepted': False}
        file = self.root/'rigid.json'; atomic_json(file, result); ref = {'path': file.name, 'sha256': sha(file)}
        native = {'operation': 'inspect_reconstructed_part', 'result': dict(result, receipt=ref), 'files': [ref, result['artifact']]}
        row = {'component_id': 'buckle', 'source_receipt': ref, 'object_name': 'buckle'}
        with patch('a3d.garment_motion._native_origin', return_value=(native, {'receipt': ref})):
            self.assertEqual(rigid_leaf(project, row, False)['result']['status'], 'RIGID_GEOMETRY_INSPECTED')
            with self.assertRaisesRegex(StudioError, 'sourced rigid'): rigid_leaf(project, row, True)
            native['files'] = [ref]
            with self.assertRaisesRegex(StudioError, 'callback'): rigid_leaf(project, row, False)

    def test_calibrated_rigid_is_readable_only_as_test_fixture_without_placement_review(self):
        project,_,_=self.inputs(1);file=self.root/'calibrated.blend';file.write_bytes(b'fixture')
        result={'status':'RIGID_DIMENSION_CALIBRATED_UNACCEPTED','component_id':'buckle','piece_id':'buckle-source',
                'artifact':{'path':file.name,'sha256':sha(file)},'object_names':['buckle']}
        path=self.root/'calibrated.json';atomic_json(path,result);ref={'path':path.name,'sha256':sha(path)}
        native={'operation':'prepare_reconstructed_part','result':dict(result,receipt=ref),'files':[ref,result['artifact']]}
        row={'component_id':'buckle','source_receipt':ref,'object_name':'buckle'}
        with patch('a3d.garment_motion._native_origin',return_value=(native,{})):
            self.assertEqual(rigid_leaf(project,row,False)['result']['status'],'RIGID_DIMENSION_CALIBRATED_UNACCEPTED')
            with self.assertRaisesRegex(StudioError,'sourced rigid'):rigid_leaf(project,row,True)

    def test_production_rigid_review_requires_exact_canonical_human_gate_and_candidate_artifacts(self):
        project,_,_=self.inputs(1)
        artifact=self.root/'placed.blend';artifact.write_bytes(b'fixture')
        geometry=self.root/'placed.geometry.json';atomic_json(geometry,{'fixture':True})
        artifact_ref={'path':artifact.name,'sha256':sha(artifact)}
        geometry_ref={'path':geometry.name,'sha256':sha(geometry)}
        result={'status':'RIGID_PART_PREPARED_UNACCEPTED','purpose':'GARMENT_CANDIDATE',
                'component_id':'buckle','piece_id':'buckle-source','artifact':artifact_ref,'geometry':geometry_ref,
                'object_names':['buckle'],'placement_review':'REVIEWED',
                'placement_binding':{'status':'SOURCE_BOUND','source_refs':[geometry_ref],
                                     'target_refs':[geometry_ref],'orientation_source_ref':geometry_ref,
                                     'anchors_mapping_ref':geometry_ref}}
        path=self.root/'placed.json';atomic_json(path,result);ref={'path':path.name,'sha256':sha(path)}
        native={'operation':'attach_reconstructed_part','result':dict(result,receipt=ref),'files':[ref,artifact_ref]}
        row={'component_id':'buckle','source_receipt':ref,'object_name':'buckle'}
        review=self.root/'placement.review.json';atomic_json(review,{'fixture':'portable admission test only'})
        with patch('a3d.garment_motion._native_origin',return_value=(native,{})),patch('a3d.lifecycle.visual_review') as visual:
            with self.assertRaisesRegex(StudioError,'exact source-bound review'):rigid_leaf(project,row,True)
            row['placement_review_ref']={'path':review.name,'sha256':sha(review)}
            with self.assertRaisesRegex(StudioError,'canonical evidence'):rigid_leaf(project,row,True)
            project.evidence('rigid.review',review.name)
            with self.assertRaisesRegex(StudioError,'Human review pending'):rigid_leaf(project,row,True)
            # This is a portable test decision in a synthetic temporary project.
            project.gate('rigid-placement.buckle',True,'Fixture decision',['rigid.review'],'fixture:test')
            self.assertEqual(rigid_leaf(project,row,True)['result'],result)
            self.assertEqual(visual.call_args.kwargs['expected_artifacts'],[artifact_ref,geometry_ref])
            atomic_json(review,{'fixture':'changed evidence'})
            with self.assertRaisesRegex(StudioError,'input changed'):rigid_leaf(project,row,True)

    def test_observed_rigid_requires_registered_measurements_every_integer_frame_and_native_reopen(self):
        project,_,_=self.inputs(1);artifact=self.root/'animated-rigid.blend';artifact.write_bytes(b'fixture')
        result={'status':'RIGID_PART_PREPARED_UNACCEPTED','purpose':'TEST_ONLY',
                'component_id':'buckle','artifact':{'path':artifact.name,'sha256':sha(artifact)},
                'object_names':['buckle'],'placement_binding':{'mode':'OBSERVED_TEXTILE_FRAME_ACTIONS'},
                'temporal_coverage':'COMPLETE','native_reopened':True,
                'clips':[{'id':'walk','status':'EXECUTED_FULL_CLIP','frame_start':1,'frame_end':3,'executed_times':[1,2,3]}]}
        path=self.root/'animated-rigid.json'
        row={'component_id':'buckle','object_name':'buckle'}
        def read_current(value,measurements):
            atomic_json(path,value);ref={'path':path.name,'sha256':sha(path)};row['source_receipt']=ref
            native={'operation':'attach_reconstructed_part','result':dict(value,receipt=ref),'files':[ref,value['artifact']]}
            with patch('a3d.garment_motion._native_origin',return_value=(native,{})),patch('a3d.export_profiles._measured_clips',return_value=(measurements,{})):
                return rigid_leaf(project,row,False)
        self.assertEqual(read_current(result,['walk'])['result'],result)
        for change in ('missing_middle','not_reopened','incomplete','unregistered','duplicate_clip'):
            value=copy.deepcopy(result);measured=['walk']
            if change=='missing_middle':value['clips'][0]['executed_times']=[1,3]
            if change=='not_reopened':value['native_reopened']=False
            if change=='incomplete':value['temporal_coverage']='INCOMPLETE'
            if change=='unregistered':measured=[]
            if change=='duplicate_clip':value['clips'].append(copy.deepcopy(value['clips'][0]))
            with self.subTest(change=change),self.assertRaisesRegex(StudioError,'full reopened clips'):read_current(value,measured)

    def test_native_composition_budget_and_rest_contract_is_importable_without_blender(self):
        from blender.animated_delivery import _garment_rest
        from types import SimpleNamespace
        bad = SimpleNamespace(type='MESH', parent=None, constraints=[], modifiers=['CLOTH'], animation_data=None)
        with self.assertRaisesRegex(StudioError, 'unmodified observed'): _garment_rest(bad)
