"""Replay one declared source band on exact saved body evidence, without Blender.

Input JSON contains profile_ref, geometry_ref, package_ref, component_id,
piece_id and anatomical_references_ref. No garment name or coordinates are
embedded in this executable. Results are exploratory numerical observations.
"""
import argparse
import json
import math
import sys
import zipfile
from pathlib import Path
from types import SimpleNamespace

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))
from a3d.anatomical_guide_inputs import project_anatomical_references
from a3d.anatomical_placement import validate_anatomical_references
from a3d.core import StudioError, atomic_json, digest, inside, read_json, sha
from a3d.garment_guides import anatomical_band_frame


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--project', required=True)
    parser.add_argument('--inputs', required=True)
    parser.add_argument('--output', required=True)
    args = parser.parse_args()
    project = SimpleNamespace(root=Path(args.project).resolve())
    request_path = inside(project.root, args.inputs)
    request = read_json(request_path)
    output = Path(args.output).resolve()
    if output.exists():
        raise StudioError('Preserve the previous replay; select a fresh output directory')
    references = []

    def verified(reference):
        path = inside(project.root, reference['path'])
        if sha(path) != reference['sha256']:
            raise StudioError('Diagnostic source changed: '+reference['path'])
        references.append(reference)
        return path

    profile = read_json(verified(request['profile_ref']))
    geometry = read_json(verified(request['geometry_ref']))
    with zipfile.ZipFile(verified(request['package_ref'])) as archive:
        data = json.loads(archive.read('garment.json'))
    cid, pid = request['component_id'], request['piece_id']
    if data['component_id'] != cid or pid not in data['pieces']:
        raise StudioError('Diagnostic source component or piece differs')
    documents = project_anatomical_references(project, {cid: {
        'anatomical_references_ref': request['anatomical_references_ref']}})
    before = digest([profile, geometry, data, documents])
    normalized = validate_anatomical_references(profile, documents[cid], geometry=geometry)
    policy = normalized['pieces'][pid]
    cage, report = anatomical_band_frame(data['pieces'][pid], policy, profile, normalized, pid)
    axis = 0 if policy['material_axis'] == 'u' else 1
    fibres = {}
    for uv, point in zip(cage['uv_cm'], cage['target_cm']):
        fibres.setdefault(round(uv[axis], 9), []).append((uv[1-axis], point))
    errors = []
    for row in fibres.values():
        row.sort()
        if len(row) > 1:
            rest = row[-1][0]-row[0][0]
            errors.append(abs(math.dist(row[0][1], row[-1][1])-rest))
    if not errors or digest([profile, geometry, data, documents]) != before:
        raise StudioError('Diagnostic fibre coverage missing or source mutated')
    for reference in references:
        if sha(inside(project.root, reference['path'])) != reference['sha256']:
            raise StudioError('Diagnostic source changed during replay')
    if project_anatomical_references(project, {cid: {
            'anatomical_references_ref': request['anatomical_references_ref']}}) != documents:
        raise StudioError('Diagnostic anatomical inputs changed during replay')
    output.mkdir(parents=True)
    atomic_json(output/'cage.json', cage)
    result = {'status': 'PORTABLE_BAND_REPLAY_ONLY', 'input_sha256': sha(request_path),
        'inputs': request, 'guide': report, 'tested_fibres': len(errors),
        'max_fibre_length_error_cm': max(errors), 'source_mutated': False,
        'cage_sha256': sha(output/'cage.json'), 'qualification': 'NONE',
        'attachment_correspondence_review': 'NOT_GRANTED_BY_THIS_DIAGNOSTIC',
        'whole_garment_placement': 'NOT_EXECUTED', 'simulation': 'NOT_EXECUTED', 'fitting': 'NOT_EXECUTED'}
    atomic_json(output/'report.json', result)
    print(json.dumps({k: result[k] for k in ('status', 'tested_fibres', 'max_fibre_length_error_cm', 'qualification')}))


if __name__ == '__main__':
    main()
