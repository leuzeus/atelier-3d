"""One bounded real Comfy cycle, including an explicitly injected lost receipt."""
import argparse
import json
import os
from pathlib import Path
import shutil
import sys
import time
from unittest.mock import patch

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--output', required=True)
    parser.add_argument('--source-project', required=True)
    parser.add_argument('--source-image', required=True)
    parser.add_argument('--config', required=True)
    args = parser.parse_args()
    output = Path(args.output).resolve()
    if output.drive.upper() != 'G:' or output.exists():
        raise ValueError('Use a fresh native validation directory on G:')
    os.environ['A3D_CONFIG'] = str(Path(args.config).resolve(strict=True))
    from a3d.comfy import Comfy
    from a3d.config import load_config
    from a3d.core import atomic_json, digest, inside, sha
    from a3d.official_mcp import OfficialMCP
    from a3d.runs import create_run, next_run_step, run_status
    from a3d.store import Project
    from a3d.workflow_variants import prepare_variant
    source = Project(args.source_project)
    original = inside(source.root, args.source_image)
    source_sha = sha(original)
    output.mkdir(parents=True)
    project = Project.create(output/'project', source.state()['asset'])
    image = project.root/'reference.png'; shutil.copyfile(original, image)
    assert sha(image) == sha(original) == source_sha
    project.evidence('reference.original', 'reference.png')
    atomic_json(project.root/'brief.json', {'purpose': 'REAL_PROVIDER_PIPELINE_TEST_ONLY', 'source_sha256': source_sha})
    project.evidence('brief', 'brief.json'); project.transition('SPECIFIED', 'brief')
    config = load_config(args.config)
    native = {'submissions': 0, 'lost_receipt': None}
    class LostReceipt(OfficialMCP):
        def call(self, name, arguments=None):
            result = super().call(name, arguments)
            if name == 'run_workflow':
                native['submissions'] += 1
                native['lost_receipt'] = result
                raise TimeoutError('TEST INJECTION: receipt lost after actual provider acceptance')
            return result
    client = Comfy(config, factory=LostReceipt)
    upload = client.upload(str(project.root), 'reference.png', 'source')
    parameters = {'source': upload['input_name'],
                  'prompt': 'dark blue garment, full garment reference, plain neutral background',
                  'steps': 4, 'megapixels': .1, 'denoise': .1, 'seed': 4242}
    invalid = prepare_variant(project, client, 'reference-sd15-bounded', 'missing-model',
                              dict(parameters, checkpoint='not-installed-test-model.safetensors'))
    assert invalid['status'] == 'INCOMPATIBLE' and native['submissions'] == 0
    variant = prepare_variant(project, client, 'reference-sd15-bounded', 'native-bounded-reference', parameters)
    assert variant['status'] == 'COMPATIBLE', variant['compatibility']
    cid = next(iter(project.state()['components']))
    specification = {'version': 1, 'id': 'native.comfy.lost-receipt', 'kind': 'comfy',
        'asset_id': project.state()['asset']['id'],
        'inputs': [{'path': 'reference.png', 'sha256': source_sha}, variant['graph']],
        'budgets': {'max_attempts': 1, 'max_seconds': 600.},
        'units': [{'id': 'reference', 'dependencies': [], 'executor': 'comfy',
            'operation': 'submit_workflow', 'arguments': {'component_id': cid,
                'workflow_id': variant['variant_id'], 'parameters': {}},
            'inputs': [variant['graph']], 'code_paths': ['a3d/workflow_compatibility.py',
                'a3d/workflow_variants.py', 'workflows/comfy/reference-sd15-bounded.api.json'],
            'success_statuses': ['COMPLETED']}]}
    atomic_json(project.root/'run.json', specification)
    run = create_run(project, 'comfy', 'run.json')
    observations = []
    started = time.monotonic()
    with patch('a3d.comfy.Comfy', return_value=client):
        while time.monotonic()-started < 600.:
            result = next_run_step(project, run['run_id'])
            observations.append({'elapsed_seconds': time.monotonic()-started, 'result': result})
            state = run_status(project, run['run_id'])
            if state['status'] in ('COMPLETED', 'FAILED', 'INCOMPLETE', 'NEEDS_CORRECTION'):
                break
            time.sleep(3.)
    state = run_status(project, run['run_id'])
    jobs = project.jobs()
    report = {'version': 1, 'status': 'PASS' if state['status'] == 'COMPLETED' else 'FAIL',
        'scope': 'REAL_COMFY_PROVIDER_CYCLE_WITH_FAULT_INJECTION',
        'endpoint': client.base, 'elapsed_seconds': time.monotonic()-started,
        'lost_receipt': native['lost_receipt'], 'provider_submission_count': native['submissions'],
        'run_id': run['run_id'], 'run': state, 'jobs': jobs, 'observations': observations,
        'variant': variant, 'incompatible_variant': invalid, 'source_sha256': source_sha,
        'generated_reference_review': 'NOT_EXECUTED', 'geometry': 'NOT_EXECUTED',
        'fitting': 'NOT_EXECUTED', 'garment_acceptance': 'NOT_GRANTED'}
    atomic_json(output/'receipt.json', report)
    assert native['submissions'] == 1 and len(jobs) == 1, report
    assert state['status'] == 'COMPLETED', {'run': state, 'jobs': jobs}
    assert jobs[0].get('reconciliation') and jobs[0]['outputs']
    assert all(sha(project.root/ref['path']) == ref['sha256'] for ref in jobs[0]['outputs'])
    print(json.dumps({'status': report['status'], 'receipt': str(output/'receipt.json'),
                      'provider_submissions': native['submissions'], 'outputs': len(jobs[0]['outputs'])}))


if __name__ == '__main__': main()
