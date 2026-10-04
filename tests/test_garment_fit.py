import copy
import unittest

from a3d.core import StudioError, digest
from a3d.garment_fit import assess_source_fit
from tests.test_fitting import fitting_sources


def fixture():
    data, _, old = fitting_sources()
    ref = {'path': 'dossier.json', 'sha256': 'a'*64}
    body_ref = {'path': 'body.json', 'sha256': 'b'*64}
    compiled = {'status': 'READY_TO_PLAN', 'source_ref': copy.deepcopy(ref), 'assembly_spec': {'body_ref': copy.deepcopy(body_ref)},
        'components': [{'id': data['component_id'], 'pipeline': 'PATTERN_SEWN'}],
        'textiles': {pid: {'component_id': data['component_id'], 'source_geometry': p,
                          'semantics': {'layer': 'outer'}, 'package_source_ref': ref} for pid, p in data['pieces'].items()},
        'links': [{**s, 'kind': s.get('kind', 'permanent'), 'id': data['component_id']+'::'+s['id']} for s in data['seams']]}
    body = {'status': 'PROFILE_MEASURED', **{key: 'c'*64 for key in
        ('source_sha256', 'pose_sha256', 'geometry_sha256', 'options_sha256', 'rig_landmarks_sha256')},
        'landmarks': {'chest': {'girth_cm': 36., 'section': {'status': 'MEASURED', 'height_cm': 20.,
                      'girth_cm': 36., 'curve_cm': [[-4.5,-4.5,20.],[4.5,-4.5,20.],[4.5,4.5,20.],[-4.5,4.5,20.]]}}}}
    body['cache_key'] = digest({key: body[key] for key in
        ('source_sha256', 'pose_sha256', 'geometry_sha256', 'options_sha256', 'rig_landmarks_sha256')})
    measurement = {'id': 'coat.chest', 'component_id': data['component_id'], 'layer': 'outer', 'body_landmark': 'chest',
        'homology_source_ref': ref, 'path_kind': 'closed_girth',
        'segments': [{'piece': s['piece'], **{side: {'edge': s[side]['edge'], 'fraction': s[side]['t']} for side in ('from','to')}}
                     for s in old['measurements'][0]['pattern_path']],
        'joins': [data['component_id']+'::'+sid for sid in old['measurements'][0]['joins']],
        'engaged_links': [data['component_id']+'::opening'], 'takeup': [],
        'ease': {'minimum_cm': 3., 'target_cm': 4., 'maximum_cm': 8., 'movement_cm': 2.,
                 'underlayers_cm': 1., 'style_cm': 1., 'source_ref': ref}}
    spec = {'version': 1, 'source_ref': ref, 'dossier_ref': ref, 'body_ref': body_ref,
        'component_ids': [data['component_id']], 'classification': {'category': 'coat', 'silhouette_intent': 'regular',
             'wearing_configuration': 'closed', 'layer_role': 'outer'},
        'required_measurements': [{key: measurement[key] for key in ('id','component_id','layer','body_landmark')}],
        'measurements': [measurement]}
    return compiled, body, spec


class GarmentFit(unittest.TestCase):
    def test_nominal_capacity_ease_breakdown_and_sources_without_acceptance(self):
        compiled, body, spec = fixture(); before = digest([compiled, body, spec])
        report = assess_source_fit(compiled, body, spec); row = report['checks'][0]
        self.assertEqual(report['status'], 'SOURCE_EASE_COMPARED')
        self.assertEqual(row['source_material_length_cm'], 40.)
        self.assertEqual(row['ease_cm'], 4.)
        self.assertEqual(row['closure_state'], 'DECLARED_NOMINAL_NOT_OBSERVED')
        self.assertEqual(report['fitting'], 'NOT_EXECUTED')
        self.assertEqual(report['acceptance'], 'NOT_GRANTED')
        self.assertEqual(report['intent_review'], 'REQUIRES_CANONICAL_HUMAN_DECISION')
        self.assertEqual(before, digest([compiled, body, spec]))

    def test_category_does_not_invent_ease_and_missing_required_path_is_visible(self):
        compiled, body, spec = fixture(); spec['classification']['silhouette_intent'] = 'unspecified'
        spec['measurements'] = []
        report = assess_source_fit(compiled, body, spec)
        self.assertEqual(report['status'], 'FIT_PREFLIGHT_INCOMPLETE')
        self.assertEqual({row['code'] for row in report['diagnostics']}, {'FIT_CLASSIFICATION_REQUIRED','FIT_MEASUREMENT_PATH_REQUIRED'})
        self.assertEqual(report['checks'], [])
        for category in ('coat', 'shirt', 'accessory'):
            compiled, body, spec = fixture(); spec['classification']['category'] = category
            self.assertEqual(assess_source_fit(compiled, body, spec)['checks'][0]['ease_cm'], 4.)

    def test_takeup_changes_nominal_capacity_but_cut_allowance_does_not(self):
        compiled, body, spec = fixture()
        for row in compiled['textiles'].values(): row['source_geometry']['cut_allowance_cm'] = 50.
        self.assertEqual(assess_source_fit(compiled, body, spec)['checks'][0]['ease_cm'], 4.)
        spec['measurements'][0]['takeup'] = [{'amount_cm': 2., 'reason': 'explicit nominal overlap', 'source_ref': spec['source_ref']}]
        result = assess_source_fit(compiled, body, spec)
        self.assertEqual(result['status'], 'SOURCE_EASE_MISMATCH')
        self.assertEqual(result['checks'][0]['ease_cm'], 2.)

    def test_open_front_never_becomes_closed_girth_from_material_sum(self):
        compiled, body, spec = fixture(); row = spec['measurements'][0]
        row['path_kind'] = 'open_material_span'; row['joins'].pop(); row['engaged_links'] = []
        spec['classification']['wearing_configuration'] = 'open_front'
        result = assess_source_fit(compiled, body, spec)
        self.assertEqual(result['checks'][0]['status'], 'OPEN_SPATIAL_COVERAGE_REQUIRED')
        self.assertIsNone(result['checks'][0]['ease_cm'])
        self.assertEqual(result['checks'][0]['spatial_overlap'], 'NOT_MEASURED')
        self.assertIn('OPEN_FRONT_OVERLAP_INTENT_REQUIRED', [item['code'] for item in result['diagnostics']])

    def test_same_body_section_can_serve_distinct_owned_layer_measurements(self):
        compiled, body, spec = fixture()
        second = copy.deepcopy(spec['measurements'][0]); second['id'] = 'coat.secondary-chest'
        spec['measurements'].append(second)
        spec['required_measurements'].append({key: second[key] for key in ('id','component_id','layer','body_landmark')})
        self.assertEqual(len(assess_source_fit(compiled, body, spec)['checks']), 2)
        self.assertEqual(assess_source_fit(compiled, body, spec)['checks'][1]['ease_cm'], 4.)

    def test_bounds_breakdown_owner_wrong_join_or_detachable_cannot_qualify(self):
        for mutation in ('bounds','breakdown','layer','component','join','orientation','detachable','engagement','doublejoin'):
            compiled, body, spec = fixture(); row = spec['measurements'][0]
            if mutation == 'bounds': row['ease']['minimum_cm'] = 10
            if mutation == 'breakdown': row['ease']['movement_cm'] = 3
            if mutation == 'layer': compiled['textiles']['back']['semantics']['layer'] = 'inner'
            if mutation == 'component': row['component_id'] = 'another'
            if mutation == 'join': row['joins'][0] = 'invented'
            if mutation == 'orientation': row['segments'][1]['from']['fraction'] = .4
            if mutation == 'detachable': compiled['links'][1]['kind'] = 'detachable'
            if mutation == 'engagement': row['engaged_links'] = []
            if mutation == 'doublejoin': row['joins'] = [row['joins'][0]]*2
            with self.subTest(mutation=mutation), self.assertRaises(StudioError): assess_source_fit(compiled, body, spec)

    def test_invalid_body_section_and_changed_pose_cache_are_not_measurements(self):
        compiled, body, spec = fixture(); body['landmarks']['chest']['section']['status'] = 'NOT_QUALIFIED'
        result = assess_source_fit(compiled, body, spec)
        self.assertEqual(result['checks'][0]['status'], 'MISSING_BODY_MEASUREMENT')
        self.assertEqual(result['status'], 'FIT_PREFLIGHT_INCOMPLETE')
        for mutation in ('girth','curve','pose','cache','reference'):
            compiled, body, spec = fixture()
            if mutation == 'girth': body['landmarks']['chest']['section']['girth_cm'] = 1000
            if mutation == 'curve': body['landmarks']['chest']['section']['curve_cm'][0][2] = 21
            if mutation == 'pose': body['pose_sha256'] = 'd'*64
            if mutation == 'cache': body['cache_key'] = 'arbitrary'
            if mutation == 'reference': spec['body_ref']['sha256'] = 'd'*64
            with self.subTest(mutation=mutation), self.assertRaises(StudioError): assess_source_fit(compiled, body, spec)

    def test_concave_source_gap_cannot_be_missed_by_sampling(self):
        compiled, body, spec = fixture()
        compiled['textiles']['front']['source_geometry'] = {
            'vertices': [[0,0],[10,0],[10,10],[5.001,10],[5.001,4],[5,4],[5,10],[0,10]],
            'edges': {'left': [7,0], 'right': [1,2]}, 'faces': []}
        with self.assertRaisesRegex(StudioError, 'empty space'): assess_source_fit(compiled, body, spec)

    def test_belt_96cm_cannot_become_192cm_by_crossing_source_spans_and_repeating_closure(self):
        from a3d.garment_fit import _path
        compiled,_,_=fixture();cid=compiled['components'][0]['id']
        compiled['textiles']={'belt':{'component_id':cid,'semantics':{'layer':'outer'},
            'package_source_ref':compiled['source_ref'],'source_geometry':{
                'vertices':[[0.,0.],[96.,0.],[96.,6.],[0.,6.]],
                'edges':{'end-left':[3,0],'end-right':[1,2]}}}}
        compiled['links']=[{'id':name,'kind':'closure','piece_a':'belt','edge_a':'end-right',
                            'piece_b':'belt','edge_b':'end-left','orientation':'reverse'}
                           for name in ('closure-a','closure-b')]
        row={'component_id':cid,'layer':'outer','path_kind':'closed_girth','takeup':[],
             'segments':[{'piece':'belt','from':{'edge':'end-left','fraction':f},
                          'to':{'edge':'end-right','fraction':f}} for f in (.25,.75)],
             'joins':['closure-a','closure-a'],'engaged_links':['closure-a']}
        with self.assertRaisesRegex(StudioError,'simple cycle'):_path(compiled,row,{cid})
        # Even two distinct approved connection IDs cannot turn the crossing
        # diagonals into a simple homologous material circumference.
        row['joins']=['closure-a','closure-b'];row['engaged_links']=row['joins'][:]
        with self.assertRaisesRegex(StudioError,'self-intersects'):_path(compiled,row,{cid})

    def test_same_takeup_cannot_be_deducted_twice_with_reordered_keys_or_numeric_representation(self):
        compiled,body,spec=fixture()
        first={'amount_cm':1,'reason':'same declared overlap','source_ref':spec['source_ref']}
        second={'source_ref':copy.deepcopy(spec['source_ref']),'reason':'same declared overlap','amount_cm':1.0}
        spec['measurements'][0]['takeup']=[first,second]
        with self.assertRaises(StudioError):assess_source_fit(compiled,body,spec)

    def test_signed_client_body_wrapper_without_native_journal_does_not_admit_project_assessment(self):
        import tempfile
        from pathlib import Path
        from unittest.mock import patch
        from a3d.core import ROOT,atomic_json,sha
        from a3d.garment_fit import assess_project_fit
        from tests.support import ready_project
        (ROOT/'work/test-runs').mkdir(parents=True,exist_ok=True)
        with tempfile.TemporaryDirectory(dir=ROOT/'work/test-runs') as directory:
            project=ready_project(Path(directory),True)
            compiled,body,spec=fixture()
            atomic_json(project.root/'dossier.json',{'purpose':'PORTABLE_TEST_ONLY'})
            atomic_json(project.root/'metadata.json',{'purpose':'PORTABLE_TEST_ONLY'})
            atomic_json(project.root/'body.json',body)
            dref={'path':'dossier.json','sha256':sha(project.root/'dossier.json')}
            bref={'path':'body.json','sha256':sha(project.root/'body.json')}
            compiled['source_ref']=dref;compiled['assembly_spec']['body_ref']=bref
            compiled['specification_source_ref']={'path':'metadata.json','sha256':sha(project.root/'metadata.json')}
            spec.update(source_ref=dref,dossier_ref=dref,body_ref=bref)
            for row in spec['measurements']:
                row['homology_source_ref']=dref;row['ease']['source_ref']=dref
            client={'operation':'prepare_body_target','origin':'NATIVE_DISPATCH','execution':'RETURNED',
                    'scope':'PORTABLE_NEGATIVE_TEST_NO_NATIVE_CALLBACK',
                    'result':{'status':'NATIVE_BODY_TARGET_MEASURED','artifacts':{'profile':bref},
                              'profile_cache_key':body['cache_key']},'files':[bref]}
            client['cache_key']=digest(client)
            atomic_json(project.root/'client-wrapper.json',client)
            # Ordinary evidence registration is not a native run completion.
            project.evidence('client.body-wrapper','client-wrapper.json')
            atomic_json(project.root/'compiled.json',compiled);atomic_json(project.root/'fit.json',spec)
            database_sha=sha(project.db)
            with patch('a3d.production_dossier.compile_project_dossier',return_value=compiled):
                with self.assertRaisesRegex(StudioError,'canonical native run origin'):
                    assess_project_fit(project,'compiled.json','fit.json')
            self.assertEqual(sha(project.db),database_sha)


if __name__ == '__main__':
    unittest.main()
