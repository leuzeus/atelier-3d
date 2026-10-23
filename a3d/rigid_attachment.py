"""Source-bound rigid attachment to observed textile UV; no placement acceptance."""
import copy
import math
import zipfile
import json

from .core import StudioError, contract, digest, inside, read_json, sha
from .garment_motion import _native_origin, canonical_garment_clip, checked_reference
from .contact_geometry import cross, dot, norm, sub


def unit(value):
    if len(value) != 3 or any(type(x) not in (int, float) or not math.isfinite(x) for x in value) or norm(value)<1e-10:
        raise StudioError('Rigid attachment has a degenerate or nonfinite direction')
    return [x/norm(value) for x in value]


def source_axes(camera):
    front, up = unit(camera['axis']), unit(camera['up'])
    if abs(dot(front, up)) > 1e-6: raise StudioError('Rigid source front and up are not orthogonal')
    return {'right': unit(cross(up, front)), 'up': up, 'front': front}


def selector_uv(selector, piece):
    if selector['kind'] == 'UV': return list(selector['uv_cm'])
    if selector['kind'] == 'MARK':
        marks = [row for row in piece.get('assembly_marks', []) if row.get('id') == selector['mark_id']]
        if len(marks) != 1 or 'edge_id' not in marks[0] or 'position' not in marks[0]:
            raise StudioError('Rigid source notch lacks a reliable named edge and fractional location')
        selector = {'kind': 'EDGE', 'edge_id': marks[0]['edge_id'], 'fraction': marks[0]['position']}
    edge = piece['edges'].get(selector['edge_id'])
    if not edge or len(edge)<2: raise StudioError('Rigid attachment references an absent source edge')
    points = [piece['vertices'][index] for index in edge]
    lengths = [math.dist(a, b) for a, b in zip(points, points[1:])]; total = sum(lengths)
    if total < 1e-9: raise StudioError('Rigid attachment source edge is degenerate')
    remaining = selector['fraction']*total
    for a, b, length in zip(points, points[1:], lengths):
        if length and remaining <= length+1e-10:
            return [x+(y-x)*min(1., remaining/length) for x, y in zip(a, b)]
        remaining -= length
    return list(points[-1])


def barycentric(uv, triangle):
    a, b, c = triangle; x, y = uv
    denominator = (b[1]-c[1])*(a[0]-c[0])+(c[0]-b[0])*(a[1]-c[1])
    if abs(denominator)<1e-12: return None
    u = ((b[1]-c[1])*(x-c[0])+(c[0]-b[0])*(y-c[1]))/denominator
    v = ((c[1]-a[1])*(x-c[0])+(a[0]-c[0])*(y-c[1]))/denominator
    weights = [u, v, 1-u-v]
    return weights if min(weights)>=-1e-8 and max(weights)<=1+1e-8 else None


def bind_selectors(candidate, mapping, piece):
    from .cloth_metrics import face_sources
    sources = face_sources(candidate)
    if sources['binding_issues']: raise StudioError('Rigid target lost immutable source face/UV bindings')
    result = {}
    for name in ('origin', 'right', 'up'):
        uv = selector_uv(mapping[name], piece); matches = []
        for index, (triangle, owner) in enumerate(zip(sources['source_rest_triangles_cm'], sources['source_face_pieces'])):
            if owner != mapping['piece_id']: continue
            weights = barycentric(uv, triangle)
            if weights is not None: matches.append({'face': index, 'weights': weights})
        if not matches: raise StudioError('Rigid target selector is outside the exact source panel: '+name)
        result[name] = {'uv_cm': uv, 'witnesses': matches}
    if abs((result['right']['uv_cm'][0]-result['origin']['uv_cm'][0])*(result['up']['uv_cm'][1]-result['origin']['uv_cm'][1])-
           (result['right']['uv_cm'][1]-result['origin']['uv_cm'][1])*(result['up']['uv_cm'][0]-result['origin']['uv_cm'][0])) < 1e-9:
        raise StudioError('Rigid source UV attachment frame is degenerate')
    return result


def mapped_point(binding, vertices, faces, tolerance):
    points = [[sum(weight*vertices[index][axis] for weight, index in zip(row['weights'], faces[row['face']])) for axis in range(3)]
              for row in binding['witnesses']]
    if any(math.dist(points[0], point)>tolerance for point in points[1:]):
        raise StudioError('Rigid target UV has ambiguous physical witnesses after source consolidation')
    return points[0]


def attachment_frames(candidate, frames, bindings, axes, source_anchor, offset_cm, max_turn_degrees, reference_normal, tolerance):
    faces = candidate['faces']; expected = list(range(frames[0]['frame'], frames[-1]['frame']+1))
    if [row['frame'] for row in frames] != expected: raise StudioError('Rigid attachment must cover every consecutive observed frame')
    output = []; previous = None
    for sample in frames:
        points = sample['vertices_cm']
        if len(points) != len(candidate['placed_cm']) or any(len(row)!=3 or any(not math.isfinite(v) for v in row) for row in points):
            raise StudioError('Rigid attachment observed target vertex correspondence changed')
        origin, right_point, up_point = [mapped_point(bindings[name], points, faces, tolerance) for name in ('origin', 'right', 'up')]
        right = unit(sub(right_point, origin)); up_vector = sub(up_point, origin)
        up = unit([v-dot(up_vector, right)*r for v,r in zip(up_vector,right)])
        front = unit(cross(right, up))
        if previous is None and reference_normal is not None and dot(front, unit(reference_normal))<=0:
            raise StudioError('Rigid attachment normal opposes its sourced body-front reference')
        if previous is not None and dot(front, previous)<math.cos(math.radians(max_turn_degrees)):
            raise StudioError('Rigid attachment frame changes normal beyond its declared temporal budget')
        previous = front
        target_axes = (right, up, front); source = (axes['right'], axes['up'], axes['front'])
        rotation = [[sum(target_axes[k][i]*source[k][j] for k in range(3)) for j in range(3)] for i in range(3)]
        position = [origin[i]+offset_cm*front[i] for i in range(3)]
        translation = [position[i]-sum(rotation[i][j]*source_anchor[j] for j in range(3)) for i in range(3)]
        output.append({'frame': sample['frame'], 'rotation': rotation, 'translation_cm': translation,
                       'target_origin_cm': origin, 'target_axes': {'right': right, 'up': up, 'front': front},
                       'target_geometry_sha256': digest([points, faces]), 'body_geometry_sha256': sample['body_geometry_sha256']})
    return output


def canonical_calibrated_part(project, reference):
    checked_reference(project, reference)
    native, origin = _native_origin(project, lambda row: row.get('operation')=='prepare_reconstructed_part' and row.get('result',{}).get('receipt')==reference)
    result = read_json(inside(project.root, reference['path']))
    if (result.get('status')!='RIGID_DIMENSION_CALIBRATED_UNACCEPTED' or result.get('dimensions_status')!='PASS' or
            any(native['result'].get(key)!=value for key,value in result.items())):
        raise StudioError('Rigid attachment requires exact native source dimension calibration')
    for name in ('artifact','geometry','profile','candidate','package','dossier'):
        checked_reference(project,result[name])
        if result[name] not in native['files']: raise StudioError('Rigid calibration dependency is not canonically registered')
    from .part_preparation import part_descriptor
    current = part_descriptor(project, result['profile']['path'], normalize=True)
    if (current['profile']['source_ref']!=result['candidate'] or current['profile']['package_ref']!=result['package'] or
            current['profile']['dossier_ref']!=result['dossier'] or current['profile']['component_id']!=result['component_id'] or
            current['profile']['piece_id']!=result['piece_id']):
        raise StudioError('Rigid calibration no longer matches source provider/job/package/dossier')
    geometry=read_json(inside(project.root,result['geometry']['path']))
    if digest(geometry)!=result['geometry_sha256']: raise StudioError('Rigid calibrated geometry record changed')
    return result, origin, geometry


def rigid_attachment_descriptor(project, profile_path):
    profile_path_obj=inside(project.root,profile_path); profile=contract('rigid-attachment',read_json(profile_path_obj))
    mapping=contract('rigid-anchor-map',read_json(inside(project.root,checked_reference(project,profile['anchor_map_ref'])['path'])))
    source,origin,geometry=canonical_calibrated_part(project,profile['source_receipt'])
    if (source['component_id']!=profile['component_id'] or source['piece_id']!=profile['piece_id'] or
            source['object_names']!=[profile['object_name']] or set(geometry)!=set(source['object_names'])):
        raise StudioError('Rigid attachment V1 requires one exact native mesh for the complete source part')
    with zipfile.ZipFile(inside(project.root,source['package']['path'])) as archive: part=json.loads(archive.read('part.json'))
    if profile['anchor_name'] not in part['anchors'] or profile['front_view'] not in part['views']:
        raise StudioError('Rigid attachment lacks a reliable declared source anchor or front/up view')
    relations=[row for row in part['relationships'] if row['a']==profile['component_id'] and row['b']==mapping['target_component_id']]
    if len(relations)!=1 or relations[0]['type']!='attached' or relations[0]['must_remain_separate'] is not True or relations[0]['may_merge'] is not False:
        raise StudioError('Rigid attachment must preserve its exact approved separate attachment relation')
    package_ref=checked_reference(project,mapping['source_ref']); checked_reference(project,mapping['provenance_ref'])
    component=project.state()['components'][mapping['target_component_id']]
    if package_ref!={key:component['package'][key] for key in ('path','sha256')}:
        raise StudioError('Rigid target selectors use another immutable source package')
    with zipfile.ZipFile(inside(project.root,package_ref['path'])) as archive: garment=json.loads(archive.read('garment.json'))
    if mapping['piece_id'] not in garment['pieces']: raise StudioError('Rigid target panel is absent from its exact source cut')
    if profile['purpose']=='GARMENT_CANDIDATE':
        from .planning import require_board
        board=require_board(project,project.state()); ref=mapping['provenance_ref']
        if board['dependencies'].get(ref['path'])!=ref['sha256']:
            raise StudioError('Production anchor mapping must cite the exact approved construction evidence')
    clips=[]; times=0
    if len({row['id'] for row in profile['clips']})!=len(profile['clips']) or any(row['id']=='reference' for row in profile['clips']):
        raise StudioError('Rigid attachment clip identities are ambiguous')
    for declaration in profile['clips']:
        target,target_origin=canonical_garment_clip(project,declaration['target_receipt'])
        if profile['purpose']=='GARMENT_CANDIDATE' and target['purpose']!='GARMENT_CANDIDATE':
            raise StudioError('TEST_ONLY cloth cannot qualify a production rigid attachment')
        inventory=target['object_inventory']['garment']
        if inventory['component_id']!=mapping['target_component_id'] or inventory['package_sha256']!=package_ref['sha256'] or mapping['piece_id'] not in inventory['source_pieces']:
            raise StudioError('Rigid target clip does not preserve its declared source panel/package')
        candidate_ref=checked_reference(project,target['bindings']['candidate']); candidate=read_json(inside(project.root,candidate_ref['path']))
        bindings=bind_selectors(candidate,mapping,garment['pieces'][mapping['piece_id']])
        observation_ref=checked_reference(project,target['observations_artifact']); observations=read_json(inside(project.root,observation_ref['path']))
        if [row['frame'] for row in observations['frames']]!=list(range(target['clip']['frame_start'],target['clip']['frame_end']+1)):
            raise StudioError('Rigid target clip coverage is incomplete')
        recipe_ref=checked_reference(project,target['bindings']['recipe']); recipe=contract('sewing-recipe',read_json(inside(project.root,recipe_ref['path'])))
        clearance=recipe['phases']['drape']['collision_distance_cm']; depth=source['measured_dimensions_cm'][2]
        if clearance<0 or depth<=0: raise StudioError('Rigid attachment depth/reserve is unsupported')
        normal=None
        if profile['purpose']=='GARMENT_CANDIDATE':
            motion=read_json(inside(project.root,target['bindings']['body_motion_receipt']['path']))
            body_target=read_json(inside(project.root,motion['body_target_receipt']['path']))
            body_profile=read_json(inside(project.root,body_target['artifacts']['profile']['path']))
            normal=body_profile['frame']['forward']
        computed=attachment_frames(candidate,observations['frames'],bindings,source_axes(part['views'][profile['front_view']]['camera']),
            part['anchors'][profile['anchor_name']],depth/2+clearance,profile['budgets']['max_normal_turn_degrees'],normal,profile['geometry_tolerance_cm'])
        clips.append({'declaration':copy.deepcopy(declaration),'target':target,'target_origin':target_origin,'candidate':candidate,
                      'observations':observations,'bindings':bindings,'frames':computed,'offset':{'mode':'PART_HALF_DEPTH_PLUS_RECIPE_COLLISION_DISTANCE',
                      'part_depth_cm':depth,'recipe_ref':recipe_ref,'phase':'drape','field':'collision_distance_cm','reserve_cm':clearance,'offset_cm':depth/2+clearance}})
        times+=len(computed)
    if len({row['target']['clip']['fps'] for row in clips})!=1 or times+1>profile['budgets']['max_samples']:
        raise StudioError('Rigid attachment clip timing or sample budget is incompatible')
    return {'profile':profile,'profile_ref':{'path':profile_path,'sha256':sha(profile_path_obj)},'mapping':mapping,'source':source,
            'source_origin':origin,'geometry':geometry,'clips':clips,'binding_sha256':digest([profile,mapping,origin,[row['target_origin'] for row in clips]])}
