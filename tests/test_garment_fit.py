import copy
import math
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
    def test_source_polyline_remeasures_each_material_span_instead_of_its_chord(self):
        compiled, body, spec = fixture(); row = spec['measurements'][0]
        points = [[0., 20.], [10., 21.], [20., 20.]]
        row['segments'][0]['source_uv_polyline_cm'] = points
        before = digest([compiled, body, spec]); result = assess_source_fit(compiled, body, spec)
        span = result['checks'][0]['source_spans'][0]
        self.assertAlmostEqual(span['material_length_cm'], 2*math.sqrt(101.))
        self.assertEqual(span['straight_chord_length_cm'], 20.)
        self.assertGreater(span['material_length_cm'], span['straight_chord_length_cm'])
        self.assertAlmostEqual(result['checks'][0]['source_material_length_cm'], 20+2*math.sqrt(101.))
        self.assertEqual(span['source_uv_polyline_cm'], points)
        self.assertEqual(span['source_path_sha256'], digest(points))
        self.assertEqual(span['source_anchor_residual_cm'], [0., 0.])
        self.assertEqual(span['package_ref'], compiled['textiles']['front']['package_source_ref'])
        self.assertEqual(result['intent_review'], 'REQUIRES_CANONICAL_HUMAN_DECISION')
        self.assertEqual(result['acceptance'], 'NOT_GRANTED'); self.assertEqual(result['fitting'], 'NOT_EXECUTED')
        self.assertEqual(digest([compiled, body, spec]), before)
        row['segments'][0]['source_uv_polyline_cm'] = [[0., 20.], [10., 20.], [20., 20.]]
        straight = assess_source_fit(compiled, body, spec)
        self.assertEqual(straight['checks'][0]['source_material_length_cm'], 40.)
        del row['segments'][0]['source_uv_polyline_cm']
        legacy = assess_source_fit(compiled, body, spec)
        self.assertEqual(legacy['checks'][0]['source_material_length_cm'], 40.)
        self.assertNotIn('source_uv_polyline_cm', legacy['checks'][0]['source_spans'][0])

    def test_polyline_each_leg_respects_narrow_concavity_and_may_follow_real_material_around_it(self):
        compiled, body, spec = fixture()
        compiled['textiles']['front']['source_geometry'] = {
            'vertices': [[0.,0.],[20.,0.],[20.,40.],[10.001,40.],[10.001,15.],[10.,15.],[10.,40.],[0.,40.]],
            'edges': {'left': [7,0], 'right': [1,2]}, 'faces': []}
        segment = spec['measurements'][0]['segments'][0]
        segment['source_uv_polyline_cm'] = [[0.,20.],[9.5,20.],[10.5,20.],[20.,20.]]
        with self.assertRaisesRegex(StudioError, 'empty space'):
            assess_source_fit(compiled, body, spec)
        segment['source_uv_polyline_cm'] = [[0.,20.],[9.5,14.],[10.5,14.],[20.,20.]]
        result = assess_source_fit(compiled, body, spec)
        self.assertGreater(result['checks'][0]['source_spans'][0]['material_length_cm'], 20.)
        self.assertEqual(result['fitting'], 'NOT_EXECUTED')

    def test_polyline_internal_crossing_repeated_endpoint_or_retraced_material_refused(self):
        cases = {
            'cross': [[0.,20.],[15.,30.],[5.,30.],[15.,10.],[20.,20.]],
            'retrace': [[0.,20.],[12.,20.],[5.,20.],[20.,20.]],
            'endpoint': [[0.,20.],[10.,25.],[10.,15.],[10.,25.],[20.,20.]],
            't_contact': [[0.,20.],[15.,20.],[10.,30.],[10.,20.],[20.,25.],[20.,20.]]}
        for name, points in cases.items():
            compiled, body, spec = fixture()
            spec['measurements'][0]['segments'][0]['source_uv_polyline_cm'] = points
            with self.subTest(name=name), self.assertRaisesRegex(StudioError, 'self-intersects|same material span twice'):
                assess_source_fit(compiled, body, spec)

    def test_polyline_conflicts_with_another_declared_material_segment_in_same_piece(self):
        from a3d.garment_fit import _path
        compiled, _, spec = fixture(); row = spec['measurements'][0]
        first = {'piece': 'front', 'from': {'edge': 'left', 'fraction': .25},
                 'to': {'edge': 'right', 'fraction': .25},
                 'source_uv_polyline_cm': [[0.,10.],[10.,35.],[20.,10.]]}
        second = {'piece': 'front', 'from': {'edge': 'left', 'fraction': .75},
                  'to': {'edge': 'right', 'fraction': .75}}
        row.update(path_kind='open_material_span', segments=[first, second], joins=row['joins'][:1], engaged_links=[])
        with self.assertRaisesRegex(StudioError, 'self-intersects'):
            _path(compiled, row, set(spec['component_ids']))

    def test_polyline_finite_points_exact_source_anchors_and_noncollapsed_spans_required(self):
        for points in ([], [[0.,20.]], [[.001,20.],[20.,20.]], [[20.,20.],[0.,20.]],
                       [[0.,20.],[10.,20.],[10.,20.],[20.,20.]],
                       [[0.,20.],[True,20.],[20.,20.]], [[0.,20.],[float('nan'),20.],[20.,20.]]):
            compiled, body, spec = fixture(); spec['measurements'][0]['segments'][0]['source_uv_polyline_cm'] = points
            with self.subTest(points=points), self.assertRaises((StudioError, ValueError)):
                assess_source_fit(compiled, body, spec)

    def test_polyline_budgets_refuse_without_truncating_simplifying_or_changing_sources(self):
        from a3d.garment_fit import _path
        for name, budget in [('points', {'max_points': 3}), ('checks', {'max_span_checks': 1}),
                             ('time', {'max_seconds': .001}), ('invalid', {'max_points': True}),
                             ('nan_time', {'max_seconds': float('nan')})]:
            compiled, _, spec = fixture(); row = spec['measurements'][0]
            row['segments'][0]['source_uv_polyline_cm'] = [[0.,20.],[6.,21.],[13.,21.],[20.,20.]]
            row['path_budget'] = budget
            before = copy.deepcopy([compiled, row])
            ticks = iter([0., .002] if name == 'time' else [0.]*1000)
            with self.subTest(name=name), self.assertRaisesRegex(StudioError, 'budget'):
                _path(compiled, row, set(spec['component_ids']), clock=lambda: next(ticks))
            if name != 'nan_time': self.assertEqual([compiled, row], before)
        compiled, body, spec = fixture()
        spec['measurements'][0]['segments'][0]['source_uv_polyline_cm'] = [[0.,20.],[10.,21.],[20.,20.]]
        spec['measurements'][0]['path_budget'] = {'max_points': 5, 'max_span_checks': 1, 'max_seconds': 15.}
        self.assertGreater(assess_source_fit(compiled, body, spec)['checks'][0]['source_material_length_cm'], 40.)

    def test_second_declared_component_without_its_measurement_is_not_admitted(self):
        from unittest.mock import patch
        from a3d.garment_fit import require_fit_intent
        compiled, body, spec = fixture()
        compiled['components'].append({'id': 'garment.hood', 'pipeline': 'PATTERN_SEWN'})
        spec['component_ids'].append('garment.hood')
        report = assess_source_fit(compiled, body, spec)
        self.assertEqual(report['status'], 'FIT_PREFLIGHT_INCOMPLETE')
        self.assertIn({'code': 'FIT_COMPONENT_MEASUREMENTS_REQUIRED', 'component_id': 'garment.hood'}, report['diagnostics'])
        report['human_reviews'] = [{'component_id': cid, 'numeric_ease': {'status': 'REVIEWED'}}
                                  for cid in spec['component_ids']]
        with patch('a3d.garment_fit.assess_project_fit', return_value=report), self.assertRaises(StudioError):
            require_fit_intent(None, 'compiled.json', 'fit.json')
        # Even a malformed preflight that drops the missing-owner diagnostic
        # must not let a second component inherit another component's checks.
        report['diagnostics'] = []
        with patch('a3d.garment_fit.assess_project_fit', return_value=report), self.assertRaisesRegex(StudioError, 'its own measured source path'):
            require_fit_intent(None, 'compiled.json', 'fit.json')
        undeclared = copy.deepcopy(spec)
        undeclared['required_measurements'].append({'id': 'foreign', 'component_id': 'garment.foreign',
                                                   'layer': 'outer', 'body_landmark': 'chest'})
        with self.assertRaisesRegex(StudioError, 'undeclared components'):
            assess_source_fit(compiled, body, undeclared)

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

    def test_silhouette_review_does_not_review_numeric_ease_and_stale_sources_refuse(self):
        import tempfile
        from pathlib import Path
        from a3d.core import ROOT, atomic_json, sha
        from a3d.garment_fit import _fit_reviews
        from tests.support import ready_project
        (ROOT/'work/test-runs').mkdir(parents=True, exist_ok=True)
        with tempfile.TemporaryDirectory(dir=ROOT/'work/test-runs') as directory:
            project = ready_project(Path(directory), True)
            _, _, spec = fixture(); cid = spec['component_ids'][0]
            refs = {}
            for name in ('dossier', 'body'):
                atomic_json(project.root/(name+'.json'), {'purpose': 'PORTABLE_TEST_ONLY', 'id': name})
                refs[name] = {'path': name+'.json', 'sha256': sha(project.root/(name+'.json'))}
                project.evidence('fit.'+name, refs[name]['path'])
            spec.update(dossier_ref=refs['dossier'], body_ref=refs['body'])
            decision = {'component_ids': [cid], 'dossier_ref': refs['dossier'], 'body_ref': refs['body'],
                'category': spec['classification']['category'],
                'silhouette_intent': spec['classification']['silhouette_intent'],
                'approved_scope': ['category', 'silhouette_intent'], 'purpose': 'SYNTHETIC_DECISION_TEST_ONLY'}
            atomic_json(project.root/'decision.json', decision)
            spec['source_ref'] = {'path': 'decision.json', 'sha256': sha(project.root/'decision.json')}
            project.evidence('fit.silhouette', 'decision.json')
            project.gate('fit-silhouette.'+cid, True, 'SYNTHETIC_TEST_ONLY', ['fit.silhouette'], 'portable:test')
            atomic_json(project.root/'fit.json', spec)
            spec_ref = {'path': 'fit.json', 'sha256': sha(project.root/'fit.json')}
            rows = _fit_reviews(project, spec, spec_ref)
            self.assertEqual(rows[0]['silhouette']['status'], 'REVIEWED')
            self.assertEqual(rows[0]['numeric_ease']['status'], 'PENDING')
            # Approving the same silhouette under the numeric gate name still
            # cannot approve a fit specification, dossier and exact body.
            project.gate('fit-intent.'+cid, True, 'SYNTHETIC_TEST_ONLY', ['fit.silhouette'], 'portable:test')
            self.assertEqual(_fit_reviews(project, spec, spec_ref)[0]['numeric_ease']['status'], 'PENDING_EXACT_REFERENCES')
            project.evidence('fit.numeric', 'fit.json')
            project.gate('fit-intent.'+cid, True, 'SYNTHETIC_TEST_ONLY',
                ['fit.numeric', 'fit.dossier', 'fit.body'], 'portable:test')
            self.assertEqual(_fit_reviews(project, spec, spec_ref)[0]['numeric_ease']['status'], 'REVIEWED')
            atomic_json(project.root/'body.json', {'purpose': 'CHANGED_SOURCE_TEST_ONLY'})
            with self.assertRaises(StudioError): _fit_reviews(project, spec, spec_ref)

    def test_production_intent_admission_keeps_open_coverage_unqualified(self):
        from unittest.mock import patch
        from a3d.garment_fit import require_fit_intent
        compiled, body, spec = fixture()
        report = assess_source_fit(compiled, body, spec)
        report['human_reviews'] = [{'numeric_ease': {'status': 'PENDING'},
                                    'numeric_design_intent': {'status': 'REVIEWED'}}]
        with patch('a3d.garment_fit.assess_project_fit', return_value=report):
            with self.assertRaisesRegex(StudioError, 'exact human review'):
                require_fit_intent(None, 'compiled.json', 'fit.json')

        report['human_reviews'][0]['numeric_ease']['status'] = 'REVIEWED'
        report['checks'][0]['status'] = 'OPEN_SPATIAL_COVERAGE_REQUIRED'
        with patch('a3d.garment_fit.assess_project_fit', return_value=report):
            result = require_fit_intent(None, 'compiled.json', 'fit.json')
        self.assertEqual(result['admission'], 'EXPLORATORY_PHYSICS_ONLY')
        self.assertEqual(result['acceptance'], 'NOT_GRANTED')
        self.assertEqual(result['spatial_coverage'], 'NOT_MEASURED')
        for mutation in ('missing_path', 'missing_body', 'deficit'):
            changed = copy.deepcopy(report)
            if mutation == 'missing_path': changed['diagnostics'] = [{'code': 'FIT_MEASUREMENT_PATH_REQUIRED'}]
            if mutation == 'missing_body': changed['checks'][0]['status'] = 'MISSING_BODY_MEASUREMENT'
            if mutation == 'deficit': changed['checks'][0]['status'] = 'BELOW_DECLARED_EASE'
            with patch('a3d.garment_fit.assess_project_fit', return_value=changed), self.assertRaises(StudioError):
                require_fit_intent(None, 'compiled.json', 'fit.json')

    def test_numeric_design_gate_does_not_review_an_unseen_fit_profile(self):
        import tempfile
        from pathlib import Path
        from a3d.core import ROOT,atomic_json,sha
        from a3d.garment_fit import _fit_reviews
        from tests.support import ready_project
        (ROOT/'work/test-runs').mkdir(parents=True,exist_ok=True)
        with tempfile.TemporaryDirectory(dir=ROOT/'work/test-runs')as directory:
            project=ready_project(Path(directory),True);_,_,spec=fixture();cid=spec['component_ids'][0]
            atomic_json(project.root/'body.json',{'scope':'PORTABLE_FIXTURE_ONLY'})
            atomic_json(project.root/'dossier.json',{'scope':'PORTABLE_FIXTURE_ONLY'})
            spec['body_ref']={'path':'body.json','sha256':sha(project.root/'body.json')}
            spec['dossier_ref']={'path':'dossier.json','sha256':sha(project.root/'dossier.json')}
            decision={'status':'NUMERIC_EASE_DESIGN_INTENT_APPROVED','approved':True,'component_ids':[cid],
                'approved_scope':['numeric_ease_design_targets'],
                'body_ref':spec['body_ref'],'dossier_ref':spec['dossier_ref']}
            atomic_json(project.root/'decision.json',decision)
            spec['source_ref']={'path':'decision.json','sha256':sha(project.root/'decision.json')}
            atomic_json(project.root/'fit.json',spec);fit_ref={'path':'fit.json','sha256':sha(project.root/'fit.json')}
            for key,path in [('design','decision.json'),('dossier','dossier.json'),('body','body.json')]:project.evidence(key,path)
            project.gate('ease-design.'+cid,True,'PORTABLE_TEST_ONLY',['design','dossier','body'],'portable:test')
            review=_fit_reviews(project,spec,fit_ref)[0]
            self.assertEqual(review['numeric_design_intent']['status'],'REVIEWED')
            self.assertEqual(review['numeric_ease']['status'],'PENDING')
            project.gate('fit-intent.'+cid,True,'PORTABLE_TEST_ONLY',['design','dossier','body'],'portable:test')
            self.assertEqual(_fit_reviews(project,spec,fit_ref)[0]['numeric_ease']['status'],'PENDING_EXACT_REFERENCES')

    def test_legacy_markdown_fit_source_remains_readable_without_any_numeric_gate(self):
        import tempfile
        from pathlib import Path
        from a3d.core import ROOT, atomic_json, sha
        from a3d.garment_fit import _fit_reviews
        from tests.support import ready_project
        (ROOT/'work/test-runs').mkdir(parents=True, exist_ok=True)
        with tempfile.TemporaryDirectory(dir=ROOT/'work/test-runs') as directory:
            project = ready_project(Path(directory), True); _, _, spec = fixture()
            source_path = project.root/'legacy-intent.md'
            source_path.write_text('# Intention source\nValeurs encore à revoir.\n', encoding='utf-8')
            spec['source_ref'] = {'path': 'legacy-intent.md', 'sha256': sha(source_path)}
            atomic_json(project.root/'fit.json', spec)
            ref = {'path': 'fit.json', 'sha256': sha(project.root/'fit.json')}
            review = _fit_reviews(project, spec, ref)[0]
            self.assertEqual(review['numeric_ease']['status'], 'PENDING')
            self.assertEqual(review['numeric_design_intent']['status'], 'NOT_SEPARATELY_REVIEWED')
            source_path.write_text('Texte changé après la référence.\n', encoding='utf-8')
            with self.assertRaisesRegex(StudioError, 'source reference changed'):
                _fit_reviews(project, spec, ref)

    def test_declared_json_numeric_decision_is_not_skipped_when_invalid(self):
        import tempfile
        from pathlib import Path
        from a3d.core import ROOT, atomic_json, sha
        from a3d.garment_fit import _fit_reviews
        from tests.support import ready_project
        (ROOT/'work/test-runs').mkdir(parents=True, exist_ok=True)
        with tempfile.TemporaryDirectory(dir=ROOT/'work/test-runs') as directory:
            project = ready_project(Path(directory), True); _, _, spec = fixture()
            for content in ('not valid JSON', '[]'):
                path = project.root/'declared-decision.JSON'
                path.write_text(content, encoding='utf-8')
                spec['source_ref'] = {'path': path.name, 'sha256': sha(path)}
                with self.subTest(content=content), self.assertRaises(ValueError):
                    _fit_reviews(project, spec, {'path': 'fit.json', 'sha256': 'a'*64})
            decision = {'status': 'NUMERIC_EASE_DESIGN_INTENT_APPROVED', 'approved': False,
                'component_ids': spec['component_ids'], 'approved_scope': ['numeric_ease_design_targets'],
                'body_ref': spec['body_ref'], 'dossier_ref': spec['dossier_ref']}
            atomic_json(project.root/'declared-decision.JSON', decision)
            spec['source_ref'] = {'path': 'declared-decision.JSON', 'sha256': sha(project.root/'declared-decision.JSON')}
            with self.assertRaisesRegex(StudioError, 'approved design scope'):
                _fit_reviews(project, spec, {'path': 'fit.json', 'sha256': 'a'*64})

    def test_oblique_skin_section_is_separate_and_cannot_be_relabelled_as_a_hand_hull(self):
        import math
        compiled, body, spec = fixture()
        landmark = 'wrist.left'; section_id = 'forearm.left.section.0'
        body['frame'] = {'origin_cm': [0.,0.,0.], 'right': [1.,0.,0.],
                         'forward': [0.,1.,0.], 'up': [0.,0.,1.]}
        body['landmarks'][landmark] = {'point_cm': [0.,0.,0.], 'source_ref': 'PORTABLE_TEST_ONLY'}
        for row in (spec['measurements'][0], spec['required_measurements'][0]): row['body_landmark'] = landmark
        refs = {'specification_ref': {'path': 'region-policy.json', 'sha256': 'd'*64},
                'supplement_ref': {'path': 'region-supplement.json', 'sha256': 'e'*64}}
        spec['body_regions'] = {**refs, 'landmark_sections': [{'body_landmark': landmark, 'section_id': section_id}]}
        h = math.sqrt(.5)
        curve = [[x, y*h, -y*h] for x, y in ((-4.5,-4.5),(4.5,-4.5),(4.5,4.5),(-4.5,4.5))]
        section = {'status': 'MEASURED', 'ok': True, 'parameter': 0, 'center_cm': [0.,0.,0.],
                   'plane': {'normal_world': [0.,h,h]}, 'curve_cm': curve, 'girth_cm': 36.}
        descriptor = {**refs, 'identity': {'profile_sha256': digest(body), 'profile_cache_key': body['cache_key']},
            'sections': {section_id: {'region': {'side': 'left', 'domain': 'WRIST_TO_ELBOW_ONLY',
                                                'axis_start_cm': [0.,0.,0.]}, 'section': section}}}
        before = digest(body)
        result = assess_source_fit(compiled, body, spec, descriptor)
        self.assertEqual(result['checks'][0]['body_girth_cm'], 36.)
        self.assertEqual(result['checks'][0]['ease_cm'], 4.)
        self.assertEqual(digest(body), before)
        for mutation in ('other_body', 'other_side', 'other_domain', 'other_parameter', 'elbow_as_wrist', 'off_plane', 'hull', 'unmeasured'):
            altered = copy.deepcopy(descriptor); entry = altered['sections'][section_id]
            if mutation == 'other_body': altered['identity']['profile_sha256'] = 'f'*64
            if mutation == 'other_side': entry['region']['side'] = 'right'
            if mutation == 'other_domain': entry['region']['domain'] = 'SHOULDER_TO_ELBOW_ONLY'
            if mutation == 'other_parameter': entry['section']['parameter'] = .5
            if mutation == 'elbow_as_wrist':
                entry['region']['axis_start_cm'] = [0.,10.,0.]
                entry['section']['center_cm'] = [0.,10.,0.]
                entry['section']['curve_cm'] = [[p[0],p[1]+10,p[2]] for p in curve]
            if mutation == 'off_plane': entry['section']['curve_cm'][0][2] += 1
            if mutation == 'hull': altered['sections'] = {}; altered['hand_envelopes'] = {section_id: section}
            if mutation == 'unmeasured':
                entry['section']['ok'] = False; entry['section']['status'] = 'NEEDS_DATA'
                self.assertEqual(assess_source_fit(compiled, body, spec, altered)['checks'][0]['status'], 'MISSING_BODY_MEASUREMENT')
                continue
            with self.subTest(mutation=mutation), self.assertRaises(StudioError):
                assess_source_fit(compiled, body, spec, altered)



if __name__ == '__main__':
    unittest.main()
