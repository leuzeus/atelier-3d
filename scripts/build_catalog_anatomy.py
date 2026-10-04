"""Reproduce topology adapters for the exact Blender CC0 realistic bases.

This declares source face-region correspondence, not per-garment coordinates.
Different imported bodies use the evaluated rig/custom landmark adapter.
"""
import argparse
from pathlib import Path
import sys

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))
from a3d.core import atomic_json, digest, read_json, sha
from a3d.catalog_anatomy import region_guides
from a3d.anatomy_profile import profile_mesh


def build(geometry_directory):
    directory = Path(geometry_directory)
    catalog_path = ROOT/'assets/mannequins/catalog.json'
    catalog = read_json(catalog_path)
    for entry in catalog['entries']:
        geometry = read_json(directory/(entry['id']+'.geometry.json'))
        adapter = {'version': 1,
            'source_geometry_sha256': digest([geometry['vertices_cm'], geometry['faces'], geometry['face_sets']]),
            'source_ref': {'path': 'assets/mannequins/'+entry['file'], 'sha256': entry['sha256']},
            'torso_regions': [1, 17, 18, 19],
            'joints': {'shoulder.right': [1, 20], 'shoulder.left': [1, 21],
                       'elbow.right': [20, 11], 'elbow.left': [21, 12],
                       'wrist.right': [11, 10], 'wrist.left': [12, 9],
                       'hip.right': [18, 23], 'hip.left': [18, 24],
                       'knee.right': [23, 16], 'knee.left': [24, 15],
                       'ankle.right': [16, 13], 'ankle.left': [15, 14], 'neck.base': [1, 17]},
            'joint_ring_vertex_counts': {'neck.base': 54},
            'centers': {'head.center': [17], 'hand.left': [9], 'hand.right': [10],
                        'foot.left': [14], 'foot.right': [13], 'pelvis.center': [18]},
            'region_to_bone': {'1': 'spine.upper', '17': 'head', '18': 'pelvis', '19': 'spine.lower',
                '20': 'upper_arm.right', '21': 'upper_arm.left', '11': 'forearm.right', '12': 'forearm.left',
                '9': 'hand.left', '10': 'hand.right', '23': 'thigh.right', '24': 'thigh.left',
                '15': 'shin.left', '16': 'shin.right', '13': 'foot.right', '14': 'foot.left'},
            'anatomical_review': 'REQUIRED',
            'source_region_review': 'Exact shared rings inspected; extra four-vertex neck annotations excluded by explicit 54-vertex ring identity'}
        # Source regions for facial details, toes and fingers were inspected by
        # their shared topology and bounds. V1 keeps fingers/toes with the hand/
        # foot; this is not a detailed digit rig or inferred nearest-bone map.
        for labels, bone in [([2, 3, 4, 5, 7, 8, 22], 'head'),
                             (range(26, 46), 'foot.right'),
                             ([25, *range(46, 64)], 'foot.left'),
                             (range(64, 84), 'hand.left'),
                             (range(84, 104), 'hand.right')]:
            adapter['region_to_bone'].update({str(label): bone for label in labels})
        guides = region_guides(geometry, adapter)
        geometry['rig_landmarks'] = guides['rig_landmarks']
        options = dict(entry['orientation'], section_count=80, torso_faces=guides['torso_faces'],
                       segmentation_source_ref=guides['segmentation_source_ref'])
        profile = profile_mesh(geometry, options)
        if profile['status'] != 'PROFILE_MEASURED':
            raise ValueError('Catalog profile is incomplete: '+entry['id'])
        atomic_json(directory/(entry['id']+'.review-profile.json'), profile)
        atomic_json(directory/(entry['id']+'.joint-guides.json'), guides)
        adapter_name = entry['id']+'.anatomy.json'
        atomic_json(ROOT/'assets/mannequins'/adapter_name, adapter)
        entry.update(measured_girths_cm={k: round(v['girth_cm'], 3) for k, v in profile['landmarks'].items() if 'girth_cm' in v},
                     profile_status=profile['status'], missing_landmarks=profile['missing_landmarks'],
                     anatomical_review='REQUIRED', anatomy_adapter=adapter_name,
                     anatomy_adapter_sha256=sha(ROOT/'assets/mannequins'/adapter_name))
    atomic_json(catalog_path, catalog)
    return {'status': 'GEOMETRY_GUIDES_MEASURED', 'qualification': 'NOT_PHYSICAL',
            'entries': [entry['id'] for entry in catalog['entries']]}


if __name__ == '__main__':
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--geometry-directory', required=True)
    print(build(parser.parse_args().geometry_directory))
