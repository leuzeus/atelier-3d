"""Inspect provider geometry against exact rigid-part source dimensions."""
import json
import math
import struct

from .core import StudioError, contract, inside, read_json, sha


def embedded_glb(path, max_bytes, budgets=None):
    if path.stat().st_size > max_bytes:
        raise StudioError('Reconstructed part exceeds its declared file budget')
    data = path.read_bytes()
    if len(data) < 20 or data[:4] != b'glTF':
        raise StudioError('Rigid inspection requires a binary glTF source')
    version, length = struct.unpack_from('<II', data, 4)
    if version != 2 or length != len(data):
        raise StudioError('Malformed binary glTF header')
    offset = 12; document = None; binary_lengths = []
    while offset < len(data):
        if offset+8 > len(data): raise StudioError('Truncated binary glTF chunk')
        size, kind = struct.unpack_from('<II', data, offset); offset += 8
        if size % 4 or offset+size > len(data): raise StudioError('Invalid binary glTF chunk length')
        if kind == 0x4e4f534a:
            if document is not None: raise StudioError('Duplicate binary glTF JSON chunk')
            document = json.loads(data[offset:offset+size])
        elif kind == 0x004e4942:
            binary_lengths.append(size)
        offset += size
    if not document or document.get('asset', {}).get('version') != '2.0':
        raise StudioError('Missing binary glTF scene document')
    for row in [*document.get('buffers', []), *document.get('images', [])]:
        if row.get('uri') and not row['uri'].startswith('data:'):
            raise StudioError('Rigid source must embed its resource dependencies')
    if document.get('animations') or document.get('skins'):
        raise StudioError('Static rigid inspection does not import animation or skinning')
    if budgets is not None:
        glb_topology_budget(document, binary_lengths, budgets)
    return document


def glb_topology_budget(document, binary_lengths, budgets):
    """Bound native allocation from declared accessors before invoking import."""
    compression = {'EXT_meshopt_compression', 'KHR_draco_mesh_compression'}
    if compression.intersection([*document.get('extensionsRequired', []), *document.get('extensionsUsed', [])]):
        raise StudioError('Rigid preflight supports uncompressed source buffers only')
    buffers = document.get('buffers', []); views = document.get('bufferViews', [])
    accessors = document.get('accessors', []); meshes = document.get('meshes', [])
    for row in buffers:
        length = row.get('byteLength')
        if type(length) is not int or length < 0: raise StudioError('Invalid rigid buffer length')
        if not row.get('uri') and (len(binary_lengths) != 1 or not length <= binary_lengths[0] <= length+3):
            raise StudioError('Rigid binary buffer length differs from its embedded chunk')
    for row in views:
        if row.get('extensions'):
            raise StudioError('Rigid buffer view extensions are outside the bounded uncompressed import')
        index = row.get('buffer'); offset = row.get('byteOffset', 0); length = row.get('byteLength')
        if (type(index) is not int or not 0 <= index < len(buffers) or type(offset) is not int or offset < 0 or
                type(length) is not int or length < 0 or offset+length > buffers[index]['byteLength']):
            raise StudioError('Rigid buffer view exceeds its embedded source')
    widths = {'SCALAR': 1, 'VEC2': 2, 'VEC3': 3, 'VEC4': 4, 'MAT2': 4, 'MAT3': 9, 'MAT4': 16}
    sizes = {5120: 1, 5121: 1, 5122: 2, 5123: 2, 5125: 4, 5126: 4}
    for row in accessors:
        count = row.get('count'); index = row.get('bufferView'); offset = row.get('byteOffset', 0)
        width = widths.get(row.get('type'), 0)*sizes.get(row.get('componentType'), 0)
        if (row.get('sparse') or type(count) is not int or count < 1 or type(index) is not int or
                not 0 <= index < len(views) or type(offset) is not int or offset < 0 or not width):
            raise StudioError('Rigid accessors require supported bounded embedded buffers')
        stride = views[index].get('byteStride', width)
        if type(stride) is not int or stride < width or offset+(count-1)*stride+width > views[index]['byteLength']:
            raise StudioError('Rigid accessor count exceeds its embedded view')
    totals = []
    for mesh in meshes:
        if mesh.get('weights'):
            raise StudioError('Static rigid inspection does not import morph weights')
        vertices = faces = 0
        for primitive in mesh.get('primitives', []):
            if primitive.get('targets'):
                raise StudioError('Static rigid inspection does not import morph targets')
            if primitive.get('mode', 4) != 4 or primitive.get('extensions'):
                raise StudioError('Rigid preflight supports explicit uncompressed source triangles')
            index = primitive.get('attributes', {}).get('POSITION')
            if type(index) is not int or not 0 <= index < len(accessors) or accessors[index]['type'] != 'VEC3':
                raise StudioError('Rigid primitive position accessor is missing')
            count = accessors[index]['count']; vertices += count
            indices = primitive.get('indices')
            if indices is not None:
                if type(indices) is not int or not 0 <= indices < len(accessors) or accessors[indices]['type'] != 'SCALAR':
                    raise StudioError('Rigid triangle index accessor is invalid')
                count = accessors[indices]['count']
            if count % 3: raise StudioError('Rigid primitive has an incomplete triangle')
            faces += count//3
        totals.append((vertices, faces))
    vertices = faces = 0
    for node in document.get('nodes', []):
        if node.get('weights'):
            raise StudioError('Static rigid inspection does not import morph weights')
        if 'mesh' not in node: continue
        index = node['mesh']
        if type(index) is not int or not 0 <= index < len(totals):
            raise StudioError('Rigid node refers to an absent mesh')
        vertices += totals[index][0]; faces += totals[index][1]
    if not vertices or not faces or vertices > budgets['max_vertices'] or faces > budgets['max_faces']:
        raise StudioError('Rigid declared topology exceeds its native import budget')
    return {'vertices': vertices, 'faces': faces}


def part_descriptor(project, profile_path, normalize=False):
    profile = contract('part-preparation', read_json(inside(project.root, profile_path)))
    if ('normalization' in profile) != normalize:
        raise StudioError('Rigid dimension calibration requires its exact preparation operation')
    _, component = project.ready(profile['component_id'])
    if component['route']['selected'] != 'MULTIVIEW_PART':
        raise StudioError('Rigid preparation requires the approved multiview route')
    if profile['package_ref'] != {key: component['package'][key] for key in ('path', 'sha256')}:
        raise StudioError('Rigid preparation targets another approved package')
    from .planning import require_board
    board = require_board(project, project.state())
    expected_dossier = {'path': board['dossier_path'], 'sha256': board['dependencies'][board['dossier_path']]}
    if profile['dossier_ref'] != expected_dossier:
        raise StudioError('Rigid target dimensions must come from the exact approved construction board')
    for key in ('source_ref', 'dossier_ref'):
        reference = profile[key]
        if sha(inside(project.root, reference['path'])) != reference['sha256']:
            raise StudioError('Rigid preparation source changed: '+key)
    job = project.job(profile['job_id'])
    if job['component_id'] != profile['component_id'] or job['status'] != 'completed':
        raise StudioError('Rigid candidate needs its completed owned provider job')
    if not any({key: row[key] for key in ('path', 'sha256')} == profile['source_ref']
               for row in job.get('outputs', [])):
        raise StudioError('Rigid source is not a verified output of the declared provider job')
    dossier = read_json(inside(project.root, profile['dossier_ref']['path']))
    if dossier['asset_id'] != project.state()['asset']['id'] or dossier['units'] != 'cm':
        raise StudioError('Rigid dimension dossier identity or units differ')
    pieces = dossier['components'][profile['component_id']]['pieces']
    matches = [row for row in pieces if row['id'] == profile['piece_id']]
    if len(matches) != 1: raise StudioError('Rigid dimensions require one exact source piece')
    dimensions = matches[0]['dimensions_cm']
    if len(dimensions) != 3 or any(type(value) not in (int, float) or not math.isfinite(value) or value <= 0 for value in dimensions):
        raise StudioError('Rigid source dimension triplet is incomplete')
    source = inside(project.root, profile['source_ref']['path'])
    document = embedded_glb(source, profile['budgets']['max_file_bytes'], profile['budgets'])
    return {'profile': profile, 'source': source, 'dimensions_cm': dimensions,
            'dimension_basis': matches[0].get('basis', 'UNSPECIFIED'), 'glb_document': document}


def dimension_proposal(measured, target):
    if any(value <= 0 or not math.isfinite(value) for value in measured):
        raise StudioError('Rigid geometry has a degenerate extent')
    ratios = [goal/current for current, goal in zip(measured, target, strict=True)]
    factor = sorted(ratios)[1]
    scaled = [value*factor for value in measured]
    return {'mode': 'UNIFORM_SCALE_PROPOSAL_ONLY', 'factor': factor,
            'axis_order': ['width_x', 'height_z', 'depth_y'],
            'target_dimensions_cm': target, 'predicted_dimensions_cm': scaled,
            'residuals_cm': [actual-goal for actual, goal in zip(scaled, target, strict=True)],
            'orientation': 'PROVIDER_NATIVE_UNREVIEWED', 'applied': False}


def calibrate_geometry(geometry, target, max_axis_ratio_change):
    """Source dimension calibration on a copy; no garment/body fitting changes."""
    import copy
    points = [point for row in geometry.values() for point in row['vertices_cm']]
    low = [min(p[axis] for p in points) for axis in range(3)]
    high = [max(p[axis] for p in points) for axis in range(3)]
    measured = [high[axis]-low[axis] for axis in (0, 2, 1)]
    uniform = dimension_proposal(measured, target)['factor']
    scales = [target[0]/measured[0], target[2]/measured[2], target[1]/measured[1]]
    ratio_change = max(abs(value/uniform-1.) for value in scales)
    if ratio_change > max_axis_ratio_change:
        raise StudioError('Rigid source aspect correction exceeds its declared calibration budget')
    center = [(a+b)/2 for a, b in zip(low, high, strict=True)]
    result = copy.deepcopy(geometry)
    for row in result.values():
        row['vertices_cm'] = [[(point[axis]-center[axis])*scales[axis] for axis in range(3)]
                             for point in row['vertices_cm']]
    return result, {'mode': 'EXACT_APPROVED_RIGID_DIMENSIONS_ON_COPY', 'source_center_cm': center,
                    'source_dimensions_cm': measured, 'target_dimensions_cm': target,
                    'scales_xyz': scales, 'uniform_reference_scale': uniform,
                    'max_axis_ratio_change': ratio_change, 'declared_ratio_budget': max_axis_ratio_change,
                    'source_topology_preserved': True, 'orientation': 'PROVIDER_NATIVE_UNREVIEWED',
                    'garment_patterns_changed': False, 'body_changed': False}
