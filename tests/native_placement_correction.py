"""Measured native contact/metric gates for a disposable sewing coupon."""
import copy
import math
from pathlib import Path
import sys
import bpy
ROOT = Path(__file__).resolve().parents[1]; sys.path.insert(0, str(ROOT))
from a3d.core import StudioError, atomic_json, digest
from a3d.cloth_metrics import validate_metrics
from a3d.placement_correction import correct_placement
from blender.cloth_contacts import build_contact_context, check_contacts
from tests.native_cloth_contacts import box
from tests.test_placement_correction import fixture, motion


def run(output):
    output = Path(output); output.mkdir(parents=True, exist_ok=True)
    payload, coordinates, budgets, seam_measurement = fixture(); source_sha = digest(payload)
    budgets['max_displacement_cm'] = 20.
    criteria = {'quality': {'min_angle_degrees': 10., 'min_edge_cm': .05,
                            'min_stretch': .99, 'max_stretch': 1.01},
                'clearance_cm': .05, 'budgets': budgets, 'qualification': 'NATIVE_COUPON_ONLY'}
    atomic_json(output/'criteria.json', criteria)
    body = box(); body.location.x = -.05; body.location.y = .01
    bpy.context.view_layer.update()
    context = build_contact_context(payload, [body], clearance_cm=.05)
    def evaluate(source, points):
        try: metrics = validate_metrics(source, points, criteria['quality'])
        except StudioError as error:
            if not hasattr(error, 'quality_metrics'): raise
            metrics = error.quality_metrics
        contacts = check_contacts(context, points)
        return dict(seam_measurement(source, points), hard_valid=not metrics['violations'] and contacts['ok'],
                    quality=metrics, contacts=contacts)
    def propose(source, points, report):
        # First trial intersects the measured body; second follows the actual
        # seam partner vector by a bounded rigid translation.
        yield motion(-10.)
        gaps = [[points[b][i]-points[a][i] for i in range(3)] for a, b in source['seams']['join']['pairs']]
        translation = [-sum(row[i] for row in gaps)/len(gaps) for i in range(3)]
        size = math.sqrt(sum(x*x for x in translation))
        if size:
            proposal = motion(0.); proposal['translation_cm'] = [x*min(1., .5/size) for x in translation]
            yield proposal
    result = correct_placement(payload, coordinates, evaluate, propose, budgets)
    assert result['stop_reason'] == 'TARGET_REACHED'
    assert not result['measurement']['quality']['violations'] and result['measurement']['contacts']['ok']
    assert any(row['reason'] == 'HARD_GATE_OR_NO_IMPROVEMENT' and not row['measurement']['contacts']['ok'] for row in result['history'])
    assert digest(payload) == source_sha
    atomic_json(output/'correction.json', result)
    atomic_json(output/'receipt.json', {'status': 'NATIVE_COUPON_CORRECTION_PASS',
        'source_unchanged': True, 'metric_and_contact_gates': 'PASS', 'unsafe_trial_rejected': True,
        'blender_version': bpy.app.version_string, 'qualification': 'NATIVE_COUPON_ONLY',
        'full_garment': 'NOT_EXECUTED', 'production_connection': False})


if __name__ == '__main__': run(sys.argv[sys.argv.index('--')+1])
