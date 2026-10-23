"""Source inventories and canonical leaves for simultaneous native clip composition."""
import copy
import json
import zipfile

from .core import StudioError, contract, digest, inside, read_json, sha


def checked(project, reference):
    if not isinstance(reference, dict) or set(reference) != {'path', 'sha256'}:
        raise StudioError('Animated delivery requires exact portable source references')
    path = inside(project.root, reference['path'])
    if sha(path) != reference['sha256']:
        raise StudioError('Animated delivery input changed: '+reference['path'])
    return path


def compare_inventory(expected, actual, production=True):
    """Require source-piece coverage once per component, without merging components."""
    want = {row['component_id']: row for row in expected}
    if len(want) != len(expected) or len({row['component_id'] for row in actual}) != len(actual):
        raise StudioError('Animated delivery cannot duplicate a component or its source pieces')
    if set(want) != {row['component_id'] for row in actual}:
        raise StudioError('Animated delivery source component inventory is incomplete')
    for row in actual:
        source = want[row['component_id']]
        pieces = row['source_pieces']
        if (len(set(pieces)) != len(pieces) or set(pieces) != set(source['source_pieces']) or
                row['kind'] != source['kind'] or production and row.get('package_sha256') != source.get('package_sha256')):
            raise StudioError('Animated delivery changed the exact source cut, package or piece inventory')
    return {'status': 'SOURCE_INVENTORY_COMPLETE' if production else 'TEST_INVENTORY_ONLY',
            'textile_piece_count': sum(len(row['source_pieces']) for row in expected if row['kind'] == 'TEXTILE'),
            'rigid_piece_count': sum(len(row['source_pieces']) for row in expected if row['kind'] == 'RIGID')}


def source_inventory(project, profile):
    if profile['purpose'] == 'TEST_ONLY':
        return copy.deepcopy(profile['expected_inventory']), None
    from .planning import require_board
    state = project.state(); board = require_board(project, state)
    dossier_ref = profile['dossier_ref']; checked(project, dossier_ref)
    if board['dossier_path'] != dossier_ref['path'] or board['dependencies'].get(dossier_ref['path']) != dossier_ref['sha256']:
        raise StudioError('Animated delivery dossier differs from its human-approved source board')
    dossier = read_json(inside(project.root, dossier_ref['path']))
    assembly = read_json(checked(project, profile['assembly_plan_ref']))
    if assembly.get('source_ref') != dossier_ref:
        raise StudioError('Animated delivery assembly does not preserve its approved source dossier')
    from .garment_planner import plan_assembly
    plan_assembly(assembly, capabilities=('coupled_multilayer',))
    expected = []; expected_links = []
    for cid, entry in sorted(dossier['components'].items()):
        pipeline = entry['pipeline']; component = state['components'].get(cid)
        if not component or component.get('route', {}).get('selected') != pipeline:
            raise StudioError('Animated delivery source route or component changed: '+cid)
        package = component['package']; checked(project, {k: package[k] for k in ('path', 'sha256')})
        pieces = sorted(row['id'] for row in entry['pieces'])
        if pipeline == 'PATTERN_SEWN':
            with zipfile.ZipFile(inside(project.root, package['path'])) as archive:
                data = json.loads(archive.read('garment.json'))
            if set(data['pieces']) != set(pieces):
                raise StudioError('Animated delivery dossier cut differs from its immutable source package')
            expected_links.extend({**{key: seam[key] for key in ('kind', 'piece_a', 'edge_a', 'piece_b', 'edge_b')},
                                   'id': cid+'::'+seam['id'], 'source_ref': {key: package[key] for key in ('path', 'sha256')}}
                                  for seam in data['seams'])
        expected.append({'component_id': cid, 'kind': 'TEXTILE' if pipeline == 'PATTERN_SEWN' else 'RIGID',
                         'source_pieces': pieces, 'package_sha256': package['sha256']})
    textile_pieces = {pid: row['component_id'] for row in expected if row['kind'] == 'TEXTILE' for pid in row['source_pieces']}
    if (len(assembly['pieces']) != len(textile_pieces) or
            {row['id']: row['component_id'] for row in assembly['pieces']} != textile_pieces):
        raise StudioError('Composition assembly inventory differs from its approved source cut')
    for row in assembly['pieces']:
        component = state['components'][row['component_id']]
        if row['source_ref'] != {key: component['package'][key] for key in ('path', 'sha256')}:
            raise StudioError('Composition assembly piece is bound to a different source package')
    if sorted(assembly['links'], key=digest) != sorted(expected_links, key=digest):
        raise StudioError('Composition assembly changed an approved source connection')
    if profile.get('expected_inventory') and profile['expected_inventory'] != expected:
        raise StudioError('Client inventory cannot replace the canonical approved production cut')
    return expected, assembly


def rigid_leaf(project, row, production):
    from .garment_motion import _native_origin
    reference = row['source_receipt']; checked(project, reference)
    native, origin = _native_origin(project, lambda document: document.get('result', {}).get('receipt') == reference and
                                    document.get('result', {}).get('status') in ('RIGID_GEOMETRY_INSPECTED', 'RIGID_DIMENSION_CALIBRATED_UNACCEPTED', 'RIGID_PART_PREPARED_UNACCEPTED'))
    result = read_json(inside(project.root, reference['path']))
    if (native.get('operation') not in ('inspect_reconstructed_part', 'prepare_reconstructed_part', 'attach_reconstructed_part') or
            any(native['result'].get(key) != value for key, value in result.items())):
        raise StudioError('Rigid source differs from its actual native result')
    artifact = result.get('artifact'); checked(project, artifact)
    if artifact not in native['files'] or reference not in native['files']:
        raise StudioError('Rigid composition input is absent from its canonical native callback')
    names = result.get('object_names', [])
    if row['object_name'] not in names or result.get('component_id') != row['component_id']:
        raise StudioError('Rigid source object is absent from its exact native inventory')
    if production:
        binding = result.get('placement_binding', {})
        if (result.get('status') != 'RIGID_PART_PREPARED_UNACCEPTED' or binding.get('status') != 'SOURCE_BOUND' or
                not binding.get('source_refs') or not binding.get('target_refs') or
                not binding.get('orientation_source_ref') or not binding.get('anchors_mapping_ref')):
            raise StudioError('Production composition requires actual sourced rigid orientation, anchors and placement')
        for ref in [*binding['source_refs'], *binding['target_refs'], binding['orientation_source_ref'], binding['anchors_mapping_ref']]:
            checked(project, ref)
        if result.get('purpose')=='TEST_ONLY':raise StudioError('TEST_ONLY rigid attachment cannot qualify production composition')
        review_ref = row.get('placement_review_ref')
        if not review_ref:
            raise StudioError('Production rigid placement needs its exact source-bound review')
        checked(project,review_ref);state=project.state();keys=[key for key,rec in state['evidence'].items() if {k:rec[k] for k in ('path','sha256')}==review_ref]
        if len(keys)!=1:raise StudioError('Rigid review is not exact current canonical evidence')
        key=keys[0];gate_name='rigid-placement.'+row['component_id'];project.require_gate(state,gate_name);gate=state['gates'][gate_name]
        if gate.get('source')!='human' or not gate.get('statement','').strip() or not gate.get('source_ref','').strip() or gate['evidence'].get(key)!=state['evidence'][key]:
            raise StudioError('Rigid placement needs an exact actual human decision')
        from .lifecycle import visual_review
        visual_review(project,state,key,'reconstruction',expected_artifacts=[artifact,result['geometry']])
    if result.get('placement_binding',{}).get('mode')=='OBSERVED_TEXTILE_FRAME_ACTIONS':
        from .export_profiles import _measured_clips
        measured,_=_measured_clips(project,native)
        clips=result.get('clips',[])
        if (set(measured)!={clip['id'] for clip in clips} or len(set(measured))!=len(clips) or not measured or
                result.get('native_reopened') is not True or result.get('temporal_coverage')!='COMPLETE' or
                any(clip.get('status')!='EXECUTED_FULL_CLIP' or
                    clip.get('executed_times')!=list(range(clip['frame_start'],clip['frame_end']+1)) for clip in clips)):
            raise StudioError('Rigid attachment lacks exact measured native Actions and full reopened clips')
    return {'result': result, 'origin': origin, 'native':native,'request': copy.deepcopy(row), 'artifact': artifact}


def animated_delivery_descriptor(project, profile_path):
    from .garment_motion import canonical_garment_clip
    path = inside(project.root, profile_path); profile = contract('animated-delivery', read_json(path))
    expected, assembly = source_inventory(project, profile); production = profile['purpose'] == 'GARMENT_CANDIDATE'
    if len({row['id'] for row in profile['clips']}) != len(profile['clips']) or any(row['id'] == 'reference' for row in profile['clips']):
        raise StudioError('Animated delivery global clip identities must be unique')
    rigid = [rigid_leaf(project, row, production) for row in profile['rigid_parts']]
    rigid_inventory = []
    for item in rigid:
        row, result = item['request'], item['result']
        matching = next((entry for entry in expected if entry['component_id'] == row['component_id']), None)
        if not matching or matching['kind'] != 'RIGID':
            raise StudioError('Rigid delivery component does not belong to the explicit source inventory')
        if not result.get('piece_id') or matching['source_pieces'] != [result['piece_id']]:
            raise StudioError('Rigid delivery inventory differs from its exact native source piece')
        package_sha = result.get('package_sha256') or result.get('package', result.get('package_ref', {})).get('sha256')
        rigid_inventory.append(dict(matching, package_sha256=package_sha))
    clips = []; frames = 0
    for declaration in profile['clips']:
        leaves = []; inventories = []; body_binding = None; bounds = None
        for reference in declaration['source_receipts']:
            checked(project, reference); result, origin = canonical_garment_clip(project, reference)
            if production and result.get('purpose') != 'GARMENT_CANDIDATE':
                raise StudioError('TEST_ONLY physics cannot qualify a whole production delivery')
            inventory = result.get('object_inventory', {}); garment = inventory.get('garment', {}); body = inventory.get('body', {})
            if not garment.get('source_pieces') or not body.get('body_action') or not garment.get('source_face_provenance_sha256'):
                raise StudioError('Composition leaf lacks actual garment provenance and body Action inventory')
            clip = result['clip']; current_bounds = (clip['frame_start'], clip['frame_end'], clip['fps'])
            if clip['frame_end'] < clip['frame_start'] or bounds is not None and current_bounds != bounds:
                raise StudioError('Global composition requires matching full clip bounds and frame rates')
            if body_binding is not None and body['motion_binding'] != body_binding:
                raise StudioError('Global composition cannot combine different body geometries, poses, weights or Actions')
            if production:
                body_motion = read_json(checked(project, result['bindings']['body_motion_receipt']))
                target = read_json(checked(project, body_motion['body_target_receipt']))
                if target['artifacts']['profile'] != assembly['body_ref']:
                    raise StudioError('Composition body differs from the exact source assembly target')
            observations = read_json(checked(project, result['observations_artifact']))
            observed = [entry['frame'] for entry in observations['frames']]
            if observed != list(range(clip['frame_start'], clip['frame_end']+1)):
                raise StudioError('Composition requires every observed source frame including terminal samples')
            bounds, body_binding = current_bounds, body['motion_binding']
            inventories.append(dict(garment, kind='TEXTILE'))
            leaves.append({'result': result, 'origin': origin, 'source_receipt': reference, 'observations': observations})
        if not leaves:
            raise StudioError('Composition needs an actually executed garment source for every global clip')
        inventory_status = compare_inventory(expected, [*inventories, *rigid_inventory], production)
        frames += bounds[1]-bounds[0]+1
        clips.append({'declaration': copy.deepcopy(declaration), 'leaves': leaves, 'bounds': bounds,
                      'common_motion_binding': body_binding, 'inventory': inventory_status})
    if len({row['bounds'][2] for row in clips}) != 1 or frames+1 > profile['budgets']['max_samples']:
        raise StudioError('Composition frame rate or whole-clip sample budget is incompatible')
    for row in profile['source_resources']:
        checked(project, row['source_artifact']); checked(project, row['file_ref'])
    return {'profile': profile, 'profile_ref': {'path': profile_path, 'sha256': sha(path)}, 'expected_inventory': expected,
            'clips': clips, 'rigid_parts': rigid, 'sample_count': frames, 'assembly': assembly,
            'binding_sha256': digest([profile, [leaf['origin'] for clip in clips for leaf in clip['leaves']],
                                     [item['origin'] for item in rigid]])}


def prepare_composed_export_profile(project, composition_receipt, output_path):
    """Create a new profile after registration; never rewrite composition proof files."""
    from .garment_motion import _native_origin
    from .core import atomic_json
    checked(project, composition_receipt)
    native, origin = _native_origin(project, lambda row: row.get('operation') == 'compose_animated_delivery' and
                               row.get('result', {}).get('receipt') == composition_receipt)
    result = read_json(checked(project, composition_receipt)); payload = dict(result); key = payload.pop('cache_key', None)
    if (key != digest(payload) or any(native['result'].get(name) != value for name, value in result.items()) or
            result.get('status') != 'CLIPS_EXECUTED' or result.get('scope') != 'EXACT_CANDIDATE_ANIMATION' or
            result.get('temporal_coverage') != 'COMPLETE' or result.get('native_reopened') is not True):
        raise StudioError('Composition has no complete exact native animation evidence')
    from .export_profiles import _measured_clips
    measured, unused = _measured_clips(project, native)
    if set(measured) != {clip['id'] for clip in result['clips']}:
        raise StudioError('Composition has no exact complete registered clip measurements')
    template = read_json(checked(project, result['export_profile_template']))
    if result['export_profile_template'] not in native['files'] or template['source_ref'] != result['candidate']:
        raise StudioError('Composition export template does not identify its registered native candidate')
    native_ref = copy.deepcopy(origin['receipt']); checked(project, native_ref)
    from .export_profiles import validate_export_profile
    template['motion_receipts'] = [native_ref]
    validate_export_profile(template); output = inside(project.root, output_path, False)
    if output.exists():
        raise StudioError('Composed export profile must be a new file')
    atomic_json(output, template)
    return {'path': output.relative_to(project.root).as_posix(), 'sha256': sha(output)}
