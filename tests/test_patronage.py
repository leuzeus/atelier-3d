import copy
from unittest.mock import patch

from a3d.core import StudioError, atomic_json, digest, read_json, sha
from a3d.garment_fit import assess_source_fit
from a3d.patronage import compare_patronage, prepare_project_patronage_review
from tests.test_core import Case
from tests.test_garment_fit import fixture


def design(spec, measured=36., target=4.):
    return {'status': 'NUMERIC_EASE_DESIGN_INTENT_APPROVED', 'approved': True,
        'body_ref': copy.deepcopy(spec['body_ref']), 'component_ids': copy.deepcopy(spec['component_ids']),
        'classification': copy.deepcopy(spec['classification']),
        'targets': [{'body_landmark': 'chest', 'body_girth_cm': measured,
            'body_plus_target_cm': measured+target,
            'ease_cm': {'minimum': 3., 'target': target, 'maximum': 8.,
                        'movement': 2., 'underlayers': 1., 'style': target-3.}}]}


class Patronage(Case):
    def test_closed_path_reuses_measured_source_and_retains_inputs(self):
        compiled, body, spec = fixture(); before = digest([compiled, body, spec])
        report = compare_patronage(compiled, body, spec)
        row = report['rows'][0]
        self.assertEqual(row['body_girth_cm'], 36.)
        self.assertEqual(row['source_material_length_cm'], 40.)
        self.assertEqual(row['body_plus_target_reference_cm'], 40.)
        self.assertEqual(row['target_minus_source_cm'], 0.)
        self.assertEqual(report['status'], 'SOURCE_DIMENSIONS_COMPARED_SPATIAL_FIT_PENDING')
        self.assertEqual(report['acceptance'], 'NOT_GRANTED')
        self.assertEqual(report['fitting'], 'NOT_EXECUTED')
        self.assertEqual(digest([compiled, body, spec]), before)

    def test_nominal_target_delta_does_not_allocate_or_change_pieces(self):
        compiled, body, spec = fixture()
        spec['measurements'][0]['ease'].update(minimum_cm=8., target_cm=10., maximum_cm=12., style_cm=7.)
        report = compare_patronage(compiled, body, spec)
        self.assertEqual(report['status'], 'PATTERN_ADJUSTMENT_PROPOSAL_REQUIRED')
        self.assertEqual(report['rows'][0]['target_minus_source_cm'], 6.)
        self.assertEqual(report['rows'][0]['adjustment_interpretation'],
                         'NOMINAL_TOTAL_LENGTH_DELTA_NOT_PIECE_ALLOCATION')
        self.assertFalse(report['patterns_modified'])

    def test_missing_path_uses_reviewed_target_without_inventing_capacity(self):
        compiled, body, spec = fixture(); spec['measurements'] = []
        decision = design(spec); before = digest([compiled, body, spec, decision])
        report = compare_patronage(compiled, body, spec, decision)
        self.assertEqual(report['status'], 'PATRONAGE_DATA_INCOMPLETE')
        row = report['rows'][0]
        self.assertEqual(row['body_plus_target_reference_cm'], 40.)
        self.assertIsNone(row['source_material_length_cm'])
        self.assertIsNone(row['target_minus_source_cm'])
        self.assertEqual(row['status'], 'MEASUREMENT_PATH_REQUIRED')
        self.assertEqual(digest([compiled, body, spec, decision]), before)

    def test_missing_numeric_intent_stays_incomplete(self):
        compiled, body, spec = fixture(); spec['measurements'] = []
        report = compare_patronage(compiled, body, spec)
        self.assertEqual(report['rows'][0]['status'], 'EASE_TARGET_REQUIRED')
        self.assertIsNone(report['rows'][0]['body_plus_target_reference_cm'])

    def test_open_span_never_yields_closed_girth_delta(self):
        compiled, body, spec = fixture()
        spec['classification']['wearing_configuration'] = 'open_front'
        spec['measurements'][0]['path_kind'] = 'open_material_span'
        spec['measurements'][0]['joins'].pop()
        spec['measurements'][0]['engaged_links'] = []
        report = compare_patronage(compiled, body, spec)
        self.assertEqual(report['status'], 'PATRONAGE_DATA_INCOMPLETE')
        self.assertIsNone(report['rows'][0]['target_minus_source_cm'])
        self.assertIsNone(report['rows'][0]['measured_source_ease_cm'])
        self.assertEqual(report['rows'][0]['source_material_length_cm'], 40.)

    def test_source_material_polyline_is_remeasured_by_existing_code(self):
        compiled, body, spec = fixture()
        spec['measurements'][0]['segments'][0]['source_uv_polyline_cm'] = [[0.,20.],[10.,21.],[20.,20.]]
        report = compare_patronage(compiled, body, spec)
        self.assertGreater(report['rows'][0]['source_material_length_cm'], 40.)
        self.assertLess(report['rows'][0]['target_minus_source_cm'], 0.)

    def test_reviewed_decision_cannot_relabel_body_scope_or_override_ease(self):
        for mutation in ('body', 'category', 'component', 'unapproved', 'duplicate', 'body_value', 'target'):
            compiled, body, spec = fixture(); decision = design(spec)
            if mutation == 'body': decision['body_ref']['sha256'] = 'f'*64
            if mutation == 'category': decision['classification']['category'] = 'shirt'
            if mutation == 'component': decision['component_ids'] = ['other']
            if mutation == 'unapproved': decision['approved'] = False
            if mutation == 'duplicate': decision['targets'].append(copy.deepcopy(decision['targets'][0]))
            if mutation == 'body_value': decision = design(spec, measured=37.)
            if mutation == 'target': decision = design(spec, target=5.)
            with self.subTest(mutation=mutation), self.assertRaises(StudioError):
                compare_patronage(compiled, body, spec, decision)

    def test_shared_body_section_needs_explicit_measurement_owner_for_design_targets(self):
        compiled, body, spec = fixture()
        second = copy.deepcopy(spec['required_measurements'][0])
        second.update(id='secondary.chest', layer='other-layer')
        spec['required_measurements'].append(second)
        decision = design(spec)
        with self.assertRaisesRegex(StudioError, 'unambiguous measurement_id'):
            compare_patronage(compiled, body, spec, decision)
        decision['targets'][0]['measurement_id'] = spec['required_measurements'][0]['id']
        other = copy.deepcopy(decision['targets'][0]); other['measurement_id'] = second['id']
        other['ease_cm'].update(target=5., style=2.); other['body_plus_target_cm'] = 41.
        decision['targets'].append(other)
        report = compare_patronage(compiled, body, spec, decision)
        rows = {row['id']: row for row in report['rows']}
        self.assertEqual(rows[second['id']]['body_plus_target_reference_cm'], 41.)
        self.assertEqual(rows[spec['required_measurements'][0]['id']]['body_plus_target_reference_cm'], 40.)

    def _project_inputs(self, with_decision=False):
        from types import SimpleNamespace
        compiled, body, spec = fixture()
        atomic_json(self.root/'source.json', {})
        atomic_json(self.root/'compile-spec.json', {})
        atomic_json(self.root/'body.json', body)
        source = {'path': 'source.json', 'sha256': sha(self.root/'source.json')}
        body_ref = {'path': 'body.json', 'sha256': sha(self.root/'body.json')}
        compiled['source_ref'] = source
        compiled['specification_source_ref'] = {'path': 'compile-spec.json', 'sha256': sha(self.root/'compile-spec.json')}
        compiled['assembly_spec']['body_ref'] = body_ref
        for piece in compiled['textiles'].values(): piece['package_source_ref'] = source
        spec.update(source_ref=source, dossier_ref=source, body_ref=body_ref)
        for row in spec['measurements']:
            row['homology_source_ref'] = source; row['ease']['source_ref'] = source
        atomic_json(self.root/'fit.json', spec)
        if with_decision: atomic_json(self.root/'decision.json', design(spec))
        return SimpleNamespace(root=self.root), compiled, body, spec

    def _run(self, project, decision=None, output='preparation/review-v1', refresh=False):
        return prepare_project_patronage_review(project, 'source.json', 'compile-spec.json',
                                                'fit.json', output, decision, refresh)

    def test_project_writes_exact_report_after_authenticated_service(self):
        project, compiled, body, spec = self._project_inputs()
        authenticated = assess_source_fit(compiled, body, spec)
        with (patch('a3d.production_dossier.compile_project_dossier', return_value=compiled) as compiler,
              patch('a3d.patronage.assess_compiled_fit', return_value=authenticated) as authority):
            report = self._run(project)
        compiler.assert_called_once_with(project, 'source.json', 'compile-spec.json')
        authority.assert_called_once_with(project, compiled, 'fit.json')
        artifact = report['artifacts']['report.json']
        self.assertEqual(sha(self.root/artifact['path']), artifact['sha256'])
        saved = read_json(self.root/artifact['path'])
        self.assertEqual(saved['rows'], report['rows'])
        self.assertFalse(saved['canonical_database_changed'])
        self.assertIn('40.00', (self.root/'preparation/review-v1/report.md').read_text(encoding='utf-8'))

    def test_failed_authentication_and_changed_source_write_no_review(self):
        for mode in ('refused', 'changed'):
            project, compiled, body, spec = self._project_inputs()
            def authority(*args):
                if mode == 'refused': raise StudioError('native origin refused')
                atomic_json(self.root/'source.json', {'changed': True})
                return assess_source_fit(compiled, body, spec)
            with (patch('a3d.production_dossier.compile_project_dossier', return_value=compiled),
                  patch('a3d.patronage.assess_compiled_fit', side_effect=authority),
                  self.subTest(mode=mode), self.assertRaises(StudioError)):
                self._run(project)
            self.assertFalse((self.root/'preparation/review-v1').exists())

    def test_existing_or_escaping_output_is_refused_before_calculation(self):
        project, _, _, _ = self._project_inputs()
        (self.root/'preparation/old').mkdir(parents=True)
        witness = self.root/'preparation/old/witness.txt'; witness.write_text('preserve')
        for output in ('preparation/old', 'variants/new', 'preparation/../escape', 'preparation/'):
            with self.subTest(output=output), self.assertRaises(StudioError):
                self._run(project, output=output)
        self.assertEqual(witness.read_text(), 'preserve')

    def test_canonical_design_revocation_stops_before_artifact_creation(self):
        project, compiled, body, spec = self._project_inputs(with_decision=True)
        with (patch('a3d.production_dossier.compile_project_dossier', return_value=compiled),
              patch('a3d.patronage.assess_compiled_fit', return_value=assess_source_fit(compiled, body, spec)),
              patch('a3d.pattern_ease_variant._review', side_effect=[[{'decision_id':1}], [{'decision_id':2}]]),
              self.assertRaisesRegex(StudioError, 'canonical numerical review changed')):
            self._run(project, decision='decision.json')
        self.assertFalse((self.root/'preparation/review-v1').exists())

    def test_public_tool_contract_matches_code_and_declares_artifact_writes(self):
        from a3d.tools import TOOLS
        descriptor = TOOLS['studio_prepare_patronage_review']['descriptor']
        self.assertFalse(descriptor['annotations']['readOnlyHint'])
        self.assertIn('fit_profile_path', descriptor['inputSchema']['required'])
        self.assertNotIn('design_decision_path', descriptor['inputSchema']['required'])

    def _region_inputs(self):
        project, compiled, body, spec = self._project_inputs()
        atomic_json(self.root/'region-policy.json', {})
        atomic_json(self.root/'old-supplement.json', {'code': 'old'})
        spec['body_regions'] = {
            'specification_ref': {'path':'region-policy.json', 'sha256':sha(self.root/'region-policy.json')},
            'supplement_ref': {'path':'old-supplement.json', 'sha256':sha(self.root/'old-supplement.json')},
            'landmark_sections': [{'body_landmark':'upper-arm.left','section_id':'source-upper-left'}]}
        atomic_json(self.root/'fit.json', spec)
        return project, compiled, body, spec

    def test_refresh_derives_new_inputs_without_overwriting_or_approving_old_ones(self):
        project, compiled, body, spec = self._region_inputs()
        old_fit = (self.root/'fit.json').read_bytes(); old_supplement = (self.root/'old-supplement.json').read_bytes()
        def authority(project, compiled, path):
            return assess_source_fit(compiled, body, read_json(self.root/path))
        with (patch('a3d.production_dossier.compile_project_dossier', return_value=compiled),
              patch('a3d.patronage.assess_compiled_fit', side_effect=authority),
              patch('a3d.body_region_sections.measure_project_body_regions', return_value={'code':'current'}),
              patch('a3d.body_region_sections.body_region_descriptor', return_value={})): 
            report = self._run(project, refresh=True)
        self.assertEqual(report['body_region_refresh']['status'], 'DERIVED_INPUTS_REMEASURED_FOR_REVIEW')
        self.assertFalse(report['body_region_refresh']['human_approval_inherited'])
        self.assertEqual((self.root/'fit.json').read_bytes(), old_fit)
        self.assertEqual((self.root/'old-supplement.json').read_bytes(), old_supplement)
        new_fit = read_json(self.root/'preparation/review-v1/fit-profile.json')
        self.assertEqual(new_fit['body_ref'], spec['body_ref'])
        self.assertEqual(new_fit['measurements'], spec['measurements'])
        self.assertNotEqual(new_fit['body_regions']['supplement_ref'], spec['body_regions']['supplement_ref'])
        self.assertEqual(report['acceptance'], 'NOT_GRANTED')

    def test_refresh_refuses_damaged_old_reference_before_remeasurement(self):
        project, compiled, body, spec = self._region_inputs()
        atomic_json(self.root/'old-supplement.json', {'damaged': True})
        with (patch('a3d.production_dossier.compile_project_dossier', return_value=compiled),
              patch('a3d.body_region_sections.measure_project_body_regions') as measure,
              self.assertRaisesRegex(StudioError, 'modified source supplement')):
            self._run(project, refresh=True)
        measure.assert_not_called()
        self.assertFalse((self.root/'preparation/review-v1').exists())

    def test_unrecorded_design_can_be_diagnosed_but_not_adopted(self):
        project, compiled, body, spec = self._project_inputs(with_decision=True)
        project.state = lambda: {'gates': {}}
        with (patch('a3d.production_dossier.compile_project_dossier', return_value=compiled),
              patch('a3d.patronage.assess_compiled_fit', return_value=assess_source_fit(compiled, body, spec)),
              patch('a3d.pattern_ease_variant._review', side_effect=StudioError('canonical review absent'))):
            report = self._run(project, decision='decision.json')
        self.assertEqual(report['design_intent_review'], 'REQUIRES_CANONICAL_HUMAN_DECISION')
        self.assertEqual(report['status'], 'PATRONAGE_REVIEW_REQUIRED')
        self.assertTrue(report['canonical_numeric_review_required'])
        self.assertEqual(report['acceptance'], 'NOT_GRANTED')
