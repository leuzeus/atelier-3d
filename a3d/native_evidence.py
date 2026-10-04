"""Authenticate native results against their persistent dispatch attempt.

This establishes the origin of an observed result. It grants no product gate
and does not decide whether an older physical implementation is still valid.
"""
import copy
import json
import sqlite3
from contextlib import closing

from .core import StudioError, inside, read_json, sha


def checked_reference(project, ref):
    if not isinstance(ref, dict) or set(ref) != {'path', 'sha256'}:
        raise StudioError('Native evidence requires exact portable path and SHA-256 references')
    path = inside(project.root, ref['path'])
    if not path.is_file() or sha(path) != ref['sha256']:
        raise StudioError('Native evidence reference changed: '+ref['path'])
    return copy.deepcopy(ref)


def native_origin(project, predicate):
    """Read a genuine dispatch receipt registered to its exact run attempt."""
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
                    attempt.get('receipt') != event['receipt'] or unit['status'] != 'COMPLETED' or
                    attempt.get('status') != 'COMPLETED' or receipt.get('origin') != 'NATIVE_DISPATCH' or
                    receipt.get('execution') != 'RETURNED' or receipt.get('operation') != attempt['operation'] or
                    receipt.get('arguments') != attempt['arguments'] or
                    any(receipt.get(key) != event[key] for key in ('run_id','unit_id','attempt_id','binding_sha256')) or
                    receipt.get('binding_sha256') != attempt['binding_sha256']):
                raise StudioError('Native input receipt differs from its canonical completed attempt')
            for ref in receipt['files']: checked_reference(project, ref)
            return receipt, {'event_id':event_id, 'receipt':event['receipt'],
                             'run_id':event['run_id'], 'unit_id':event['unit_id'], 'attempt_id':event['attempt_id']}
    raise StudioError('Input file alone is not a canonically registered native result')
