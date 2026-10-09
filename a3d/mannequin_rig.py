"""Source-bound rig preparation from mesh regions; no borrowed rig code.

This creates an inspectable rest skeleton and bounded smoothing of regional
weights. It does not qualify deformations, mensuration controls or fitting.
"""
import math

from .core import StudioError, digest
from .catalog_anatomy import region_guides
from .anatomy_profile import profile_mesh


def prepare_rig(geometry, adapter, orientation, smoothing_passes=4):
    if type(smoothing_passes) is not int or not 0 <= smoothing_passes <= 12:
        raise StudioError('Regional rig smoothing must stay within zero to twelve passes')
    guides = region_guides(geometry, adapter)
    evaluated = dict(geometry, rig_landmarks=guides['rig_landmarks'])
    profile = profile_mesh(evaluated, dict(orientation, torso_faces=guides['torso_faces'],
                                          segmentation_source_ref=guides['segmentation_source_ref']))
    if profile['status'] != 'PROFILE_MEASURED':
        raise StudioError('A complete source-bound profile is required before rig preparation')
    points = {name: row['point_cm'] for name, row in guides['rig_landmarks'].items()}
    basis = profile['frame']

    def world(point):
        return [basis['origin_cm'][i]+sum(point[j]*basis[key][i]
                for j, key in enumerate(('right', 'forward', 'up'))) for i in range(3)]

    points['waist.center'] = world(profile['landmarks']['waist']['point_cm'])
    points['chest.center'] = world(profile['landmarks']['chest']['point_cm'])
    head = profile['landmarks']['head.center']['point_cm']
    points['head.top'] = world([head[0], head[1], profile['bounds_cm'][1][2]])
    bones = []

    def bone(name, start, end, parent=None):
        if start not in points or end not in points:
            raise StudioError('Rig preparation needs source anatomical guides: '+start+' / '+end)
        a, b = points[start], points[end]
        if math.dist(a, b) < .5 or not all(math.isfinite(x) for p in (a, b) for x in p):
            raise StudioError('Rig preparation produced a collapsed or invalid bone: '+name)
        bones.append({'name': name, 'head_cm': a, 'tail_cm': b, 'parent': parent})

    bone('pelvis', 'pelvis.center', 'waist.center')
    bone('spine.lower', 'waist.center', 'chest.center', 'pelvis')
    bone('spine.upper', 'chest.center', 'neck.base', 'spine.lower')
    bone('neck', 'neck.base', 'head.center', 'spine.upper')
    bone('head', 'head.center', 'head.top', 'neck')
    for side in ('left', 'right'):
        bone('upper_arm.'+side, 'shoulder.'+side, 'elbow.'+side, 'spine.upper')
        bone('forearm.'+side, 'elbow.'+side, 'wrist.'+side, 'upper_arm.'+side)
        bone('hand.'+side, 'wrist.'+side, 'hand.'+side, 'forearm.'+side)
        bone('thigh.'+side, 'hip.'+side, 'knee.'+side, 'pelvis')
        bone('shin.'+side, 'knee.'+side, 'ankle.'+side, 'thigh.'+side)
        bone('foot.'+side, 'ankle.'+side, 'foot.'+side, 'shin.'+side)
    names = {row['name'] for row in bones}
    vertices, faces = geometry['vertices_cm'], geometry['faces']
    neighbors = [set() for _ in vertices]; weights = [{} for _ in vertices]
    mapping = adapter.get('region_to_bone', {})
    for face, label in zip(faces, geometry['face_sets']):
        target = mapping.get(str(label))
        if target not in names:
            raise StudioError('Every source region needs a declared prepared bone: '+str(label))
        for i in face:
            weights[i][target] = weights[i].get(target, 0.)+1.
        for a, b in zip(face, face[1:]+face[:1]):
            neighbors[a].add(b); neighbors[b].add(a)
    for row in weights:
        total = sum(row.values())
        if not total:
            raise StudioError('Rig source contains a vertex without an anatomical region')
        for name in row: row[name] /= total
    for _ in range(smoothing_passes):
        following = []
        for i, row in enumerate(weights):
            combined = {name: .65*value for name, value in row.items()}
            for j in neighbors[i]:
                for name, value in weights[j].items():
                    combined[name] = combined.get(name, 0.)+.35*value/len(neighbors[i])
            total = sum(combined.values())
            following.append({name: value/total for name, value in sorted(combined.items())})
        weights = following
    result = {'version': 1, 'status': 'RIG_PREPARED_NOT_QUALIFIED', 'bones': bones,
              'weights': weights, 'smoothing_passes': smoothing_passes,
              'source_sha256': geometry['source_sha256'],
              'geometry_sha256': digest([vertices, faces, geometry['face_sets']]),
              'adapter_sha256': digest(adapter), 'profile_cache_key': profile['cache_key'],
              'source_mutated': False, 'deformation': 'NOT_EXECUTED',
              'mensuration_controls': 'NOT_CREATED', 'fitting': 'NOT_EXECUTED'}
    result['cache_key'] = digest(result)
    return result
