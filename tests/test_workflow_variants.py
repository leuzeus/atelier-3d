from pathlib import Path
from a3d.comfy import Comfy
from a3d.core import StudioError, atomic_json, read_json
from a3d.workflow_variants import load_variant, prepare_variant
from tests.test_core import Case
from tests.support import FakeNative, ready_project


class WorkflowVariantTests(Case):
    def setUp(self):
        super().setUp()
        self.project = ready_project(self.root)
        self.native = FakeNative()
        self.client = Comfy(factory=self.native)
        self.params = {'front': 'front.png', 'left': 'left.png', 'steps': 12}

    def test_immutable_variant_retains_diff_validation_and_parameters(self):
        report = prepare_variant(self.project, self.client, 'hunyuan-multiview', 'test-variant', self.params)
        self.assertEqual(report['status'], 'COMPATIBLE')
        self.assertTrue(any(r['input'] == 'steps' and r['after'] == 12 for r in report['diff']))
        spec, graph = self.client.template('test-variant', {}, self.project)
        self.assertEqual(graph['5']['inputs']['steps'], 12)
        self.assertEqual(prepare_variant(self.project, self.client, 'hunyuan-multiview', 'test-variant', self.params), report)
        self.assertEqual(sum(n == 'validate_workflow' for n, _ in self.native.calls), 1)
        with self.assertRaises(StudioError):
            prepare_variant(self.project, self.client, 'hunyuan-multiview', 'test-variant', {**self.params, 'steps': 13})
        with self.assertRaises(StudioError):
            self.client.template('test-variant', {'steps': 13}, self.project)

    def test_incompatible_and_modified_graph_never_submitted(self):
        self.native.valid = False
        report = prepare_variant(self.project, self.client, 'hunyuan-multiview', 'test-variant', self.params)
        with self.assertRaises(StudioError): self.client.template('test-variant', {}, self.project)
        path = self.root/report['graph']['path']
        data = read_json(path); data['5']['inputs']['steps'] = 14; atomic_json(path, data)
        with self.assertRaises(StudioError): load_variant(self.project, 'test-variant')
        self.assertFalse(any(n == 'run_workflow' for n, _ in self.native.calls))

    def test_unknown_parameter_refused_before_provider_call(self):
        with self.assertRaises(StudioError):
            prepare_variant(self.project, self.client, 'hunyuan-multiview', 'test-variant', {**self.params, 'random': 1})
        self.assertFalse(self.native.calls)


class ReconciliationTests(Case):
    def setUp(self):
        super().setUp()
        self.project = ready_project(self.root)
        self.native = FakeNative(); self.client = Comfy(factory=self.native)
        params = {}
        for view in ('front', 'left'):
            params[view] = self.client.upload(self.root, f'.a3d/source/package/{view}.clean.png')['input_name']
        self.native.fail_submit = True
        self.job = self.client.submit(self.root, 'body.skull', 'hunyuan-multiview', params, 'uncertain-1')
        self.path = str(self.root/self.job['workflow_path'])

    def provider(self, rows=None, **changes):
        original = self.native.call
        self.native.queue = rows if rows is not None else [{'prompt_id': 'lost-1', 'status': 'completed', 'workflow_path': self.path}]
        def call(name, args=None):
            if name == 'job' and args.get('action') == 'status':
                self.native.calls.append((name, args))
                return {'prompt_id': 'lost-1', 'status': 'completed', 'workflow': self.path,
                        'submitted_at': self.job['created_at'], **changes}
            return original(name, args)
        self.native.call = call

    def test_unique_provider_receipts_recover_without_resubmission(self):
        self.provider()
        result = self.client.reconcile(self.root, self.job['job_id'])
        self.assertEqual(result['prompt_id'], 'lost-1')
        self.assertEqual(result['status'], 'completed')
        self.assertTrue((self.root/result['reconciliation']['path']).is_file())
        self.assertEqual(sum(n == 'run_workflow' for n, _ in self.native.calls), 1)
        self.assertEqual(self.project.state()['components']['body.skull']['stage'], 'RECONSTRUCTING')

    def test_absent_ambiguous_contradictory_provider_evidence_never_guessed(self):
        self.provider([])
        self.assertEqual(self.client.reconcile(self.root, self.job['job_id'])['reconciliation'], 'INSUFFICIENT_PROVIDER_EVIDENCE')
        self.native.queue = [{'prompt_id': p, 'status': 'completed', 'workflow_path': self.path} for p in ('p1', 'p2')]
        self.assertEqual(self.client.reconcile(self.root, self.job['job_id'])['reconciliation'], 'AMBIGUOUS')
        self.native.queue = [{'prompt_id': 'lost-1', 'status': 'completed', 'workflow_path': self.path}]
        self.provider(submitted_at='2000-01-01T00:00:00+00:00')
        with self.assertRaises(StudioError): self.client.reconcile(self.root, self.job['job_id'])
        self.assertIsNone(self.project.job(self.job['job_id'])['prompt_id'])

    def test_changed_local_graph_invalidates_reconciliation(self):
        self.provider()
        data = read_json(self.path); data['5']['inputs']['seed'] = 999; atomic_json(self.path, data)
        with self.assertRaises(StudioError): self.client.reconcile(self.root, self.job['job_id'])

    def test_empty_provider_prompt_never_becomes_owned_completed_job(self):
        self.provider([{'prompt_id': '', 'status': 'completed', 'workflow_path': self.path}], prompt_id='')
        with self.assertRaises(StudioError): self.client.reconcile(self.root, self.job['job_id'])
        self.assertIsNone(self.project.job(self.job['job_id'])['prompt_id'])

    def test_local_status_without_workflow_uses_two_queue_and_exact_output_namespace(self):
        from urllib.parse import urlencode
        graph = read_json(self.path); prefix = graph['8']['inputs']['filename_prefix']
        folder, filename = prefix.rsplit('/', 1)
        output = self.client.base+'/view?'+urlencode({'type': 'output', 'subfolder': folder,
                                                     'filename': filename+'_00001_.glb'})
        row = {'prompt_id': 'lost-1', 'status': 'completed', 'workflow_path': self.path,
               'updated_at': self.job['created_at']}
        self.provider([row], workflow=None, submitted_at=None, outputs=[output])
        result = self.client.reconcile(self.root, self.job['job_id'])
        self.assertEqual(result['status'], 'completed')
        self.assertEqual(sum(name == 'job' and args.get('action') == 'queue' for name, args in self.native.calls), 3)

    def test_local_output_from_another_namespace_never_recovers_ownership(self):
        row = {'prompt_id': 'lost-1', 'status': 'completed', 'workflow_path': self.path,
               'updated_at': self.job['created_at']}
        self.provider([row], workflow=None, submitted_at=None,
                      outputs=[self.client.base+'/view?type=output&filename=other_00001_.png&subfolder=other'])
        with self.assertRaises(StudioError): self.client.reconcile(self.root, self.job['job_id'])
        self.assertIsNone(self.project.job(self.job['job_id'])['prompt_id'])
