"""Small native preparation replies with exact links to full stored evidence."""
import copy


def compact_preparation_reply(result):
    reference = result.get('receipt')
    if not isinstance(reference, dict) or set(reference) != {'path', 'sha256'}:
        return result
    keys = ('schema_version', 'operation', 'component_id', 'stage', 'status', 'readiness',
            'problems', 'qualification', 'simulation', 'fitting', 'behavior', 'accepted', 'visual_validation',
            'export_eligible', 'object', 'receipt', 'garment_receipt', 'master', 'checkpoint',
            'summary', 'next_operation', 'next_piece_review', 'derived_mesh', 'package_sha256',
            'source_garment_sha256', 'recipe_sha256', 'plan', 'mesh_sha256', 'technical_views',
            'piece_completeness', 'validation_contract', 'error', 'reason_category')
    summary = {key: copy.deepcopy(result[key]) for key in keys if key in result}
    quality = result.get('quality')
    if isinstance(quality, dict):
        summary['quality'] = {key: copy.deepcopy(quality[key]) for key in
            ('faces', 'vertices', 'rest_area_cm2', 'min_area_cm2', 'min_angle_degrees',
             'min_edge_cm', 'min_stretch', 'max_stretch', 'min_principal_stretch',
             'max_principal_stretch', 'violations', 'limits') if key in quality}
    runs = []
    for run in result.get('cloth_runs', []):
        entry = {key: copy.deepcopy(run[key]) for key in
            ('simulation', 'phase', 'initial_gap_cm', 'final_gap_cm', 'max_penetration_cm',
             'execution_control', 'support_transition', 'temporary_release', 'validation_contract') if key in run}
        entry['evaluated_frames'] = len(run.get('frames', []))
        entry['sewing_springs'] = run.get('executed', {}).get('settings', {}).get('use_sewing_springs')
        runs.append(entry)
    if 'cloth_runs' in result: summary['cloth_runs'] = runs
    summary['transport'] = {'mode': 'COMPACT_RECEIPT_SUMMARY', 'full_evidence': copy.deepcopy(reference),
                            'full_evidence_preserved': True}
    return summary
