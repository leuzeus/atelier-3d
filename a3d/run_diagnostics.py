"""Read-only explanations of a run journal; execution is not qualification."""
import copy


def diagnose_run(run):
    issues = []
    for unit in run['units']:
        status = unit['status']
        if status in ('AWAITING_CONFIRMATION', 'WAITING_RESULT', 'INCOMPLETE', 'NEEDS_CORRECTION', 'SUBMISSION_UNKNOWN', 'UNKNOWN_COMPLETION'):
            issues.append({'unit': unit['id'], 'status': status,
                           'reason': unit.get('reason', status),
                           'attempts': len(unit['attempts'])})
    return {'execution_status': run['status'], 'issues': issues,
            'qualifications': {unit['id']: copy.deepcopy(unit.get('qualification', 'NOT_GRANTED'))
                               for unit in run['units']},
            'accepted': False,
            'resume_boundary': 'RESTORE_ENTRY_CHECKPOINT_THEN_REPLAY_UNIT',
            'continuous_physics_resume': False,
            'limits': ['Blender code is prepared only; explicit execution permission is required.',
                       'Only canonically registered native receipts can complete a Blender unit.',
                       'Execution duration is supplied by native dispatch; permission waiting is excluded. Budgets are checked after return and cannot preempt Blender.',
                       'Unknown Comfy submissions are reconciled with their original request key, never resubmitted.',
                       'Execution completion grants no physical, fitting or artistic acceptance.']}
