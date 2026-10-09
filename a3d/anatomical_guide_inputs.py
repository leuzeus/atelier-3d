"""Load immutable anatomical guide inputs without accepting a body or a fit.

The public preparation path resolves portable file references. Pure geometry
consumers receive the same source-bound reports, never caller-invented native
origins or an implicit anatomical decision.
"""
import copy
import hashlib
import json

from .core import StudioError, digest, inside


MAX_DOCUMENT_BYTES = 4 * 1024 * 1024
MAX_REPORT_BYTES = 8 * 1024 * 1024
MAX_TOTAL_REPORT_BYTES = 32 * 1024 * 1024


def _read_reference(project, reference, maximum):
    if (not isinstance(reference, dict) or set(reference) != {'path', 'sha256'}
            or not isinstance(reference['sha256'], str) or len(reference['sha256']) != 64):
        raise StudioError('Anatomical guide input requires an exact portable file reference')
    path = inside(project.root, reference['path'])
    if path.stat().st_size > maximum:
        raise StudioError('Anatomical guide artifact exceeds its byte budget')
    with path.open('rb') as stream:
        content = stream.read(maximum + 1)
    if len(content) > maximum or hashlib.sha256(content).hexdigest() != reference['sha256']:
        raise StudioError('Anatomical guide artifact changed or exceeds its byte budget')
    try:
        value = json.loads(content.decode('utf-8-sig'))
    except (UnicodeError, ValueError) as error:
        raise StudioError('Anatomical guide artifact must contain valid UTF-8 JSON') from error
    return value, len(content)


def project_anatomical_references(project, components):
    """Resolve the exact declared components, deduplicating shared reports.

    Report geometry and profile identities are checked by the numerical
    consumer against its authenticated body. Loading a report does not change
    its anatomical review status.
    """
    documents = {}
    cache = {}
    total = 0
    for cid, row in sorted(components.items()):
        if 'anatomical_references_ref' not in row:
            continue
        document, size = _read_reference(project, row['anatomical_references_ref'], MAX_DOCUMENT_BYTES)
        total += size
        if (not isinstance(document, dict) or set(document)-{'triangles_ref'} != {'version', 'profile_sha256', 'paths', 'pieces'}
                or type(document['version']) is not int or document['version'] != 1
                or not isinstance(document['paths'], dict) or len(document['paths']) > 256
                or not isinstance(document['pieces'], dict) or len(document['pieces']) > 256):
            raise StudioError('Anatomical guide specification needs bounded paths and piece policies')
        resolved = copy.deepcopy(document)
        if 'triangles_ref' in resolved:
            triangles, size = _read_reference(project, resolved.pop('triangles_ref'), MAX_REPORT_BYTES)
            total += size
            if (not isinstance(triangles, list) or len(triangles) > 200000
                    or any(not isinstance(row, list) or len(row) != 3
                           or any(type(index) is not int or index < 0 for index in row) for row in triangles)):
                raise StudioError('Anatomical surface input needs bounded native triangle indices')
            resolved['triangles'] = triangles
        for name, item in sorted(document['paths'].items()):
            if (not isinstance(item, dict)
                    or set(item) != {'report_ref', 'path_id', 'region'}):
                raise StudioError('Anatomical path specification needs a report reference, path ID and region')
            key = digest(item['report_ref'])
            if key not in cache:
                report, size = _read_reference(project, item['report_ref'], MAX_REPORT_BYTES)
                total += size
                cache[key] = report
            if total > MAX_TOTAL_REPORT_BYTES:
                raise StudioError('Anatomical guide references exceed their shared byte budget')
            report = cache[key]
            resolved['paths'][name] = {'report': copy.deepcopy(report),
                'report_sha256': digest(report), 'path_id': item['path_id'], 'region': item['region']}
        if total > MAX_TOTAL_REPORT_BYTES:
            raise StudioError('Anatomical guide references exceed their shared byte budget')
        documents[cid] = resolved
    return documents


def check_anatomical_inputs(components, documents):
    expected = {cid for cid, row in components.items() if 'anatomical_references_ref' in row}
    if not isinstance(documents, dict) or set(documents) != expected:
        raise StudioError('Anatomical guide inputs must exactly cover their declared components')
    return expected
