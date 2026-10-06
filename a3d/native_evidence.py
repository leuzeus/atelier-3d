"""Authenticate native results against their persistent dispatch attempt.

This establishes the origin of an observed result. It grants no product gate
and does not decide whether an older physical implementation is still valid.
"""
import copy
import json
import re
import sqlite3
from contextlib import closing

from .core import StudioError, inside, read_json, sha


def checked_reference(project, ref):
    if not isinstance(ref, dict) or set(ref) != {'path', 'sha256'}:
        raise StudioError('Native evidence requires exact portable path and SHA-256 references')
    if isinstance(ref['path'],str) and ref['path'].startswith('.a3d/runs/native/projections/'):
        from .run_projection_archive import _archive_io_path
        path = _archive_io_path(inside(project.root, ref['path'], False))
    else:
        path = inside(project.root, ref['path'])
    if not path.is_file() or sha(path) != ref['sha256']:
        raise StudioError('Native evidence reference changed: '+ref['path'])
    return copy.deepcopy(ref)


def native_origin(project, predicate):
    """Read a genuine dispatch receipt registered to its exact run attempt."""
    return _native_origin(project, predicate, completed_only=True)


def native_observation_origin(project, predicate, observed_artifact_ref=None):
    """Authenticate returned diagnostic data, including a refused candidate.

    This establishes what was observed, never admission of the result. Body,
    fitting and motion prerequisites must keep using completed native_origin.
    """
    return _native_origin(project, predicate, completed_only=False, observed_artifact_ref=observed_artifact_ref)


def _native_origin(project, predicate, completed_only, observed_artifact_ref=None):
    outcomes = {'COMPLETED'} if completed_only else {'COMPLETED', 'NEEDS_CORRECTION', 'INCOMPLETE'}
    with closing(sqlite3.connect(project.db.as_uri()+'?mode=ro', uri=True)) as db:
        if not db.execute("SELECT 1 FROM sqlite_master WHERE name='runs'").fetchone():
            raise StudioError('Input has no canonical native run origin')
        for event_id, document in db.execute("SELECT id,doc FROM events WHERE kind='run_native_receipt' ORDER BY id DESC"):
            event = json.loads(document)
            try:
                checked_reference(project, event['receipt'])
                receipt = read_json(inside(project.root, event['receipt']['path']))
            except (StudioError, FileNotFoundError):
                continue
            if not predicate(receipt): continue
            run_row = db.execute('SELECT doc FROM runs WHERE id=?', (event['run_id'],)).fetchone()
            if not run_row: raise StudioError('Native input run is absent from this project')
            run = json.loads(run_row[0])
            unit = next((row for row in run['units'] if row['id'] == event['unit_id']), None)
            attempt = next((row for row in unit['attempts'] if row['id'] == event['attempt_id']), None) if unit else None
            if (unit is None or attempt is None or attempt.get('receipt_event_id') != event_id or
                    attempt.get('receipt') != event['receipt'] or unit['status'] not in outcomes or
                    attempt.get('status') not in outcomes or receipt.get('origin') != 'NATIVE_DISPATCH' or
                    receipt.get('execution') != 'RETURNED' or receipt.get('operation') != attempt['operation'] or
                    receipt.get('arguments') != attempt['arguments'] or
                    any(receipt.get(key) != event[key] for key in ('run_id','unit_id','attempt_id','binding_sha256')) or
                    receipt.get('binding_sha256') != attempt['binding_sha256']):
                raise StudioError('Native input receipt differs from its canonical completed attempt')
            from .run_projection_archive import verify_projection_archives
            archived_projections = verify_projection_archives(project, receipt)
            stale_projections = []
            if observed_artifact_ref is not None:
                if observed_artifact_ref not in receipt['files']:
                    raise StudioError('Observed artifact is not bound by the exact native dispatch receipt')
                checked_reference(project, observed_artifact_ref)
            for ref in receipt['files']:
                try:
                    checked_reference(project, ref)
                except StudioError:
                    projection = (ref['path'] == '.a3d/blender/piece-candidates.json' or
                                  re.fullmatch(r'\.a3d/blender/working-[0-9a-f]+\.blend', ref['path']) is not None)
                    if (completed_only or observed_artifact_ref is None or not projection or
                            ref == observed_artifact_ref):
                        raise
                    path = inside(project.root, ref['path'])
                    if not path.is_file(): raise
                    stale_projections.append({'historical_ref': copy.deepcopy(ref),
                        'current_ref': {'path': ref['path'], 'sha256': sha(path)},
                        'role': 'MUTABLE_PROJECT_PROJECTION_NOT_ARTIFACT', 'status': 'STALE'})
            origin = {'event_id':event_id, 'receipt':event['receipt'],
                      'run_id':event['run_id'], 'unit_id':event['unit_id'], 'attempt_id':event['attempt_id']}
            if archived_projections:
                origin['archived_project_projections'] = archived_projections
            if not completed_only:
                origin.update(scope='OBSERVATION_ONLY', qualification='NONE',
                              unit_status=unit['status'], attempt_status=attempt['status'],
                              fitting='NOT_QUALIFIED', product_acceptance='NOT_GRANTED', accepted=False)
                if observed_artifact_ref is not None:
                    origin.update(observed_artifact_ref=copy.deepcopy(observed_artifact_ref),
                                  stale_project_projections=stale_projections,
                                  receipt_scope='EXACT_ARTIFACT_OBSERVATION_WITH_IMMUTABLE_REFERENCES')
            return receipt, origin
    raise StudioError('Input file alone is not a canonically registered native result')
