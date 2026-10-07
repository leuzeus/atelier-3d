"""Review-only lengths of actual interfaces between declared source regions.

No anatomical landmark is invented. A source joint identifies a pair of face
regions, not an automatically accepted tailoring measure. This module never
writes a Project, a gate, Blender state, a body profile or a fitting intention.
"""
import copy
import hashlib
import html
import json
import math
import os
import sqlite3
import stat
import time
from collections import Counter, defaultdict
from contextlib import closing
from pathlib import Path

from .core import ROOT, StudioError, canonical, digest, ident, inside, relative, sha


CODE_SOURCES = ('body_source_paths', 'body_path_openings', 'core', 'native_evidence', 'run_projection_archive',
                'body_context', 'body_target', 'body_source', 'body_region_sections',
                'catalog_anatomy', 'shoulder_surface', 'head_surface', 'anatomy_profile',
                'contact_geometry')
LIMITS = {'max_read_bytes': (1, 256*1024*1024), 'max_vertices': (4, 250000),
          'max_faces': (2, 250000), 'max_face_edges': (4, 1500000),
          'max_paths': (1, 32), 'max_boundary_edges': (3, 50000),
          'max_evidence_files': (1, 256), 'max_native_receipts': (1, 128),
          'max_output_bytes': (1, 32*1024*1024)}
MAX_SPEC_BYTES = 65536
MAX_JSON_BYTES = 32*1024*1024


def validate_specification(specification):
    if (not isinstance(specification, dict) or set(specification)-{'version', 'paths', 'budgets', 'display', 'opening_exploration'}
            or specification.get('version') != 1 or type(specification.get('version')) is not int):
        raise StudioError('Body source paths require an explicit version 1 specification')
    budgets = specification.get('budgets')
    if not isinstance(budgets, dict) or set(budgets) != set(LIMITS)|{'max_seconds'}:
        raise StudioError('Body source paths require all explicit reading, geometry, time and storage budgets')
    for key, (minimum, maximum) in LIMITS.items():
        if type(budgets[key]) is not int or not minimum <= budgets[key] <= maximum:
            raise StudioError('Unsupported body source path budget: '+key)
    seconds = budgets['max_seconds']
    if type(seconds) not in (int, float) or not math.isfinite(seconds) or not 0 < seconds <= 60:
        raise StudioError('Body source path max_seconds must be finite, positive and at most 60')
    paths = specification.get('paths')
    if not isinstance(paths, list) or not 1 <= len(paths) <= budgets['max_paths']:
        raise StudioError('Body source paths exceed the declared path budget or are absent')
    ids, joints = set(), set()
    for row in paths:
        if not isinstance(row, dict) or set(row)-{'id', 'source_joint', 'display_name'}:
            raise StudioError('A body source path declares only its ID, source joint and optional display name')
        ident(row.get('id')); joint = row.get('source_joint')
        if not isinstance(joint, str) or not joint or len(joint) > 200:
            raise StudioError('A body source path requires an exact declared adapter joint name')
        if row['id'] in ids or joint in joints:
            raise StudioError('Body source path IDs and source joints must be unique')
        ids.add(row['id']); joints.add(joint)
        if 'display_name' in row and (not isinstance(row['display_name'], str) or not row['display_name']
                                      or len(row['display_name']) > 200):
            raise StudioError('Body source path display name is invalid')
    if 'display' in specification:
        display = specification['display']
        if (not isinstance(display, dict) or set(display) != {'max_faces', 'width_px', 'height_px'} or
                any(type(display[key]) is not int for key in display) or
                not 1 <= display['max_faces'] <= 15000 or not 600 <= display['width_px'] <= 2400 or
                not 600 <= display['height_px'] <= 2400):
            raise StudioError('Body source path display requires explicit bounded face and pixel budgets')
    if 'opening_exploration' in specification:
        from .body_path_openings import validate_opening_options
        options = validate_opening_options(specification['opening_exploration'])
        if options['path_id'] not in ids:
            raise StudioError('Body opening exploration must select one declared source path')
        if options['max_output_bytes'] > budgets['max_output_bytes'] or options['max_seconds'] > seconds:
            raise StudioError('Body opening exploration cannot exceed the parent storage or time budgets')
    return specification


class _Budget:
    def __init__(self, specification):
        self.limits = validate_specification(specification)['budgets']
        self.started = self.last = time.monotonic()
        self.read_bytes = 0
        self.face_edges = 0
        self.boundary_edges = 0

    def check(self):
        current = time.monotonic()
        if not math.isfinite(current) or current < self.last or current-self.started > self.limits['max_seconds']:
            raise StudioError('Body source path time budget exceeded or clock moved backwards')
        self.last = current

    def charge(self, count):
        self.check()
        self.read_bytes += count
        if self.read_bytes > self.limits['max_read_bytes']:
            raise StudioError('Body source path reading budget exceeded')


def _point(value):
    return isinstance(value, (list, tuple)) and len(value) == 3 and all(
        type(x) in (int, float) and math.isfinite(x) for x in value)


def _mesh(geometry, budget):
    if not isinstance(geometry, dict):
        raise StudioError('Body source path needs an exact evaluated geometry')
    vertices, faces, labels = (geometry.get(key) for key in ('vertices_cm', 'faces', 'face_sets'))
    if (not isinstance(vertices, list) or not 4 <= len(vertices) <= budget.limits['max_vertices'] or
            not isinstance(faces, list) or not 2 <= len(faces) <= budget.limits['max_faces'] or
            not isinstance(labels, list) or len(labels) != len(faces)):
        raise StudioError('Body source path mesh counts or face regions exceed their explicit budget')
    for index, point in enumerate(vertices):
        if index % 256 == 0: budget.check()
        if not _point(point): raise StudioError('Body source path vertices must be finite world centimetres')
    for face, label in zip(faces, labels):
        budget.check()
        if (not isinstance(face, list) or len(face) < 3 or
                any(type(i) is not int or not 0 <= i < len(vertices) for i in face) or
                len(set(face)) != len(face) or type(label) is not int):
            raise StudioError('Body source path face, winding or source region identity is invalid')
        budget.face_edges += len(face)
        if budget.face_edges > budget.limits['max_face_edges']:
            raise StudioError('Body source path face-edge budget exceeded')
    return vertices, faces, labels


def _frame(profile):
    basis = profile.get('frame', {})
    if set(basis) != {'origin_cm', 'right', 'forward', 'up'} or any(not _point(p) for p in basis.values()):
        raise StudioError('Body source paths need the exact finite body frame')
    axes = [basis[key] for key in ('right', 'forward', 'up')]
    if any(abs(math.fsum(x*y for x, y in zip(a, b))-float(i == j)) > 1e-7
           for i, a in enumerate(axes) for j, b in enumerate(axes)):
        raise StudioError('Body source path frame is not orthonormal')
    return basis


def measure_source_body_paths(profile, geometry, source_geometry, adapter, specification, *, _budget=None):
    """Pure source topology measurement; native origin is established by the facade."""
    budget = _budget or _Budget(specification)
    validate_specification(specification)
    try: before = digest([profile, geometry, source_geometry, adapter, specification])
    except (ValueError, TypeError, RecursionError) as error:
        raise StudioError('Body source paths require finite canonical source inputs') from error
    vertices, faces, labels = _mesh(geometry, budget)
    # Source and evaluated arrays both count against the edge-processing budget.
    source_vertices, source_faces, source_labels = _mesh(source_geometry, budget)
    for body in (geometry, source_geometry):
        for key in ('source_sha256', 'pose_sha256'):
            value = body.get(key)
            if (not isinstance(value, str) or len(value) != 64 or
                    any(x not in '0123456789abcdef' for x in value)):
                raise StudioError('Body source path source and pose require exact SHA-256 identities')
    if (len(vertices) != len(source_vertices) or faces != source_faces or labels != source_labels or
            profile.get('geometry_sha256') != digest([vertices, faces]) or
            any(profile.get(key) != geometry.get(key) for key in ('source_sha256', 'pose_sha256')) or
            profile.get('rig_landmarks_sha256') != digest(geometry.get('rig_landmarks', {}))):
        raise StudioError('Body source path profile, pose, geometry or preserved source topology changed')
    from .body_region_sections import _base_identity
    _base_identity(profile)
    basis = _frame(profile)
    if (not isinstance(adapter, dict) or adapter.get('source_geometry_sha256') !=
            digest([source_vertices, source_faces, source_labels]) or
            source_geometry.get('source_sha256') != geometry.get('source_sha256') or
            not isinstance(adapter.get('source_ref'), dict) or
            adapter['source_ref'].get('sha256') != geometry.get('source_sha256')):
        raise StudioError('Body source path adapter differs from the exact original source geometry')
    declarations = adapter.get('joints', {})
    if not isinstance(declarations, dict): raise StudioError('Body source adapter joint declarations are absent')
    requested = []
    for row in specification['paths']:
        pair = declarations.get(row['source_joint'])
        if (not isinstance(pair, list) or len(pair) != 2 or any(type(x) is not int for x in pair) or
                pair[0] == pair[1] or not set(pair).issubset(set(labels))):
            raise StudioError('Body source joint lacks two distinct actual declared regions: '+row['source_joint'])
        requested.append((row, set(pair)))
    owners = defaultdict(list)
    for face_id, (face, label) in enumerate(zip(faces, labels)):
        budget.check()
        for a, b in zip(face, face[1:]+face[:1]): owners[tuple(sorted((a, b)))].append((face_id, label, a, b))
    results = []
    for row, regions in requested:
        adjacency = defaultdict(list); boundary = {}
        for edge, incident in owners.items():
            budget.check()
            if not regions.issubset({item[1] for item in incident}): continue
            if len(incident) != 2 or incident[0][2:] != tuple(reversed(incident[1][2:])):
                raise StudioError('Body source interface has nonmanifold or inconsistent source winding: '+row['id'])
            a, b = edge
            if math.dist(vertices[a], vertices[b]) == 0:
                raise StudioError('Body source interface contains a collapsed actual edge: '+row['id'])
            boundary[edge] = sorted(item[0] for item in incident)
            adjacency[a].append(b); adjacency[b].append(a)
            budget.boundary_edges += 1
            if budget.boundary_edges > budget.limits['max_boundary_edges']:
                raise StudioError('Body source boundary-edge budget exceeded')
        if not adjacency or any(len(neighbors) != 2 for neighbors in adjacency.values()):
            raise StudioError('Body source interface must be a closed loop without open ends or branches: '+row['id'])
        start = min(adjacency); ordered = [start]; seen = {start}; previous = None; current = start
        while True:
            budget.check()
            following = min(adjacency[current]) if previous is None else next(
                vertex for vertex in adjacency[current] if vertex != previous)
            if following == start: break
            if following in seen: raise StudioError('Body source interface repeats a boundary vertex')
            ordered.append(following); seen.add(following); previous, current = current, following
        if len(seen) != len(adjacency):
            raise StudioError('Body source interface has several closed loops; no anatomical choice is inferred: '+row['id'])
        edges = list(zip(ordered, ordered[1:]+ordered[:1]))
        points = [copy.deepcopy(vertices[index]) for index in ordered]
        heights = [math.fsum((point[k]-basis['origin_cm'][k])*basis['up'][k] for k in range(3)) for point in points]
        results.append({'id': row['id'], 'source_joint': row['source_joint'],
            'display_name': row.get('display_name', row['source_joint']),
            'measurement_kind': 'SOURCE_REGION_BOUNDARY_LENGTH', 'source_regions': sorted(regions),
            'vertex_ids': ordered, 'edge_vertex_ids': [list(edge) for edge in edges],
            'edge_source_face_ids': [boundary[tuple(sorted(edge))] for edge in edges],
            'curve_world_cm': points, 'closed': True, 'length_cm': math.fsum(math.dist(vertices[a], vertices[b]) for a, b in edges),
            'body_frame_height_range_cm': [min(heights), max(heights)],
            'height_variation_cm': max(heights)-min(heights),
            'topology': 'ONE_EXACT_DECLARED_REGION_INTERFACE_CYCLE',
            'tailoring_homology': 'REVIEW_REQUIRED', 'body_girth_replaced': False,
            'ease_transferred': False, 'anatomical_gate': 'NOT_GRANTED',
            'discretization_scope': 'ACTUAL_SOURCE_MESH_EDGE_POLYLINE_NO_SURFACE_SMOOTHING',
            'mesh_approximation_error_cm': None})
    result = {'version': 1, 'status': 'BODY_SOURCE_PATHS_MEASURED_FOR_REVIEW', 'paths': results,
        'identity': {'profile_sha256': digest(profile), 'profile_cache_key': profile['cache_key'],
                     'geometry_sha256': digest([vertices, faces]), 'face_sets_sha256': digest(labels),
                     'source_geometry_sha256': digest(source_geometry), 'adapter_sha256': digest(adapter),
                     'source_sha256': geometry['source_sha256'], 'pose_sha256': geometry['pose_sha256']},
        'specification_sha256': digest(specification), 'frame': copy.deepcopy(basis),
        'source_mutated': False, 'body_profile_changed': False, 'body_girths_replaced': False,
        'ease_transferred': False, 'qualification': 'NONE', 'tailoring_homology': 'REVIEW_REQUIRED',
        'native_body_origin': 'NOT_CHECKED_BY_PORTABLE_KERNEL', 'fitting': 'NOT_EXECUTED',
        'Blender': 'NOT_EXECUTED', 'acceptance': 'NOT_GRANTED'}
    if digest([profile, geometry, source_geometry, adapter, specification]) != before:
        raise StudioError('Body source path measurement mutated immutable inputs')
    budget.check()
    return result


class _Reader:
    def __init__(self, project, budget):
        self.project = project; self.budget = budget; self.refs = {}; self.documents = {}

    def _path(self, name):
        try: path = inside(self.project.root, name)
        except (FileNotFoundError, NotADirectoryError) as error:
            raise StudioError('Body source path referenced file is missing: '+str(name)) from error
        if name.startswith('.a3d/runs/native/projections/'):
            from .run_projection_archive import _archive_io_path
            path = _archive_io_path(path)
        return path

    def read(self, name, expected=None, document=True):
        path = self._path(name)
        if name in self.refs:
            if expected is not None and self.refs[name]['sha256'] != expected:
                raise StudioError('Body source path referenced SHA differs: '+name)
            if not document: return path
            if name in self.documents: return copy.deepcopy(self.documents[name])
            # A binary preflight may have hashed a JSON artifact. Load it only
            # against that same SHA; never silently replace its old identity.
            expected = self.refs[name]['sha256']
        elif len(self.refs) >= self.budget.limits['max_evidence_files']:
            raise StudioError('Body source path evidence-file budget exceeded')
        size = path.stat().st_size
        if (document and size > MAX_JSON_BYTES) or self.budget.read_bytes+size > self.budget.limits['max_read_bytes']:
            raise StudioError('Body source path input file exceeds its reading budget: '+name)
        chunks = []; hasher = hashlib.sha256(); document_bytes = 0
        with path.open('rb') as stream:
            while True:
                # A changed/stat-misreported file cannot bypass the actual
                # JSON limit. Binary artifacts retain only the global limit.
                amount = min(65536, MAX_JSON_BYTES-document_bytes+1) if document else 65536
                data = stream.read(amount)
                if not data: break
                self.budget.charge(len(data))
                if document:
                    document_bytes += len(data)
                    if document_bytes > MAX_JSON_BYTES:
                        raise StudioError('Body source path actual JSON bytes exceed the document reading limit: '+name)
                hasher.update(data)
                if document: chunks.append(data)
        actual = hasher.hexdigest()
        if expected is not None and actual != expected:
            raise StudioError('Body source path referenced artifact changed: '+name)
        self.refs[name] = {'path': name, 'sha256': actual}
        if document:
            try: self.documents[name] = json.loads(b''.join(chunks).decode('utf-8-sig'))
            except (UnicodeError, ValueError, RecursionError) as error:
                raise StudioError('Body source path source JSON is invalid: '+name) from error
            return copy.deepcopy(self.documents[name])
        return path

    def reference(self, reference, document=True):
        if (not isinstance(reference, dict) or set(reference) != {'path', 'sha256'} or
                not isinstance(reference['sha256'], str) or len(reference['sha256']) != 64 or
                any(x not in '0123456789abcdef' for x in reference['sha256'])):
            raise StudioError('Body source path requires exact path and SHA-256 references')
        return self.read(reference['path'], reference['sha256'], document)

    def preserve(self):
        for name, reference in self.refs.items():
            self.budget.check()
            # Stream again; account for the actual verification bytes too.
            hasher = hashlib.sha256()
            with self._path(name).open('rb') as stream:
                while True:
                    data = stream.read(65536)
                    if not data: break
                    self.budget.charge(len(data)); hasher.update(data)
            if hasher.hexdigest() != reference['sha256']:
                raise StudioError('Body source path input changed during preparation: '+name)


def _references(value, depth=0):
    if depth > 40: raise StudioError('Body source path evidence nesting is unsupported')
    if isinstance(value, dict):
        if set(value) == {'path', 'sha256'}: yield value
        else:
            for child in value.values(): yield from _references(child, depth+1)
    elif isinstance(value, list):
        for child in value: yield from _references(child, depth+1)


def _matches_native(document, profile_ref):
    result = document.get('result', {})
    return ((document.get('operation') == 'prepare_body_target' and
             result.get('artifacts', {}).get('profile') == profile_ref) or
            (document.get('operation') == 'introduce_body_target' and result.get('profile_ref') == profile_ref))


def _authenticated_target(project, profile_ref, reader):
    """Bound the canonical search before using the shared exact origin verifier."""
    from .native_evidence import canonical_receipt_operation
    operations = ('prepare_body_target', 'introduce_body_target')
    budget = reader.budget; selected = None
    try:
        with closing(sqlite3.connect(project.db.as_uri()+'?mode=ro', uri=True)) as database:
            database.set_progress_handler(lambda: _sql_progress(budget), 1000)
            rows = database.execute("SELECT length(CAST(doc AS BLOB)),CASE WHEN length(CAST(doc AS BLOB))<=? THEN doc ELSE NULL END "
                "FROM events WHERE kind='run_native_receipt' ORDER BY id DESC LIMIT ?",
                (MAX_JSON_BYTES, budget.limits['max_native_receipts']))
            for size, raw in rows:
                budget.charge(size)
                if raw is None: raise StudioError('Body source path canonical receipt document exceeds the JSON budget')
                event = json.loads(raw)
                run_size = database.execute('SELECT length(CAST(doc AS BLOB)) FROM runs WHERE id=?', (event['run_id'],)).fetchone()
                if not run_size or run_size[0] > MAX_JSON_BYTES:
                    raise StudioError('Body source path native run is absent or exceeds the JSON budget')
                budget.charge(run_size[0])
                if canonical_receipt_operation(database, event) not in operations: continue
                document = reader.reference(event['receipt'])
                if not _matches_native(document, profile_ref): continue
                selected = document; break
    except (sqlite3.Error, KeyError, ValueError) as error:
        if isinstance(error, StudioError): raise
        raise StudioError('Body source paths require a bounded canonical native body origin') from error
    if selected is None: raise StudioError('Body profile has no exact canonical native body origin within the receipt budget')
    for reference in selected.get('files', []): reader.reference(reference, False)
    for row in selected.get('project_projections', []): reader.reference(row['archive_ref'], False)
    if selected['operation'] == 'introduce_body_target':
        context = reader.read(selected['arguments']['context_path'])
        receipt = reader.reference(context['body_target_receipt'])
    else: receipt = selected['result']
    for reference in _references(receipt):
        reader.reference(reference, reference['path'].endswith('.json'))
    selection = reader.reference(receipt['evidence']['selection'])
    reader.read(selection['source_blend'], selection['source_sha256'], False)
    adapter = reader.reference(receipt['evidence']['adapter'])
    reader.reference(adapter['source_ref'], False)
    # Reserve a conservative byte bound for repeated shared-verifier reads.
    # The inventory above includes all artifacts it will verify. This reserve
    # is explicit and separate from bytes streamed by this module itself.
    verifier_reserve = 8*sum(reader._path(name).stat().st_size for name in reader.refs)
    budget.charge(verifier_reserve)
    from .native_evidence import native_origin
    native, origin = native_origin(project, lambda document: document == selected,
                                  operation_filter=operations)
    budget.check()
    if native['operation'] == 'introduce_body_target':
        from .body_context import body_context_descriptor
        descriptor = body_context_descriptor(project, native['arguments']['context_path'])
        result = native['result']; actual = descriptor['receipt']
        if (result.get('status') != 'BODY_TARGET_INTRODUCED' or result.get('binding_sha256') != descriptor['binding_sha256'] or
                result.get('context') != descriptor['context_ref'] or result.get('body_target_receipt') != context['body_target_receipt'] or
                result.get('source_artifact') != actual['artifact'] or result.get('geometry_ref') != actual['artifacts']['geometry'] or
                result.get('profile_cache_key') != descriptor['profile']['cache_key'] or
                result.get('actual_geometry_sha256') != digest({key: descriptor['geometry'][key]
                                                               for key in ('vertices_cm', 'faces', 'face_sets')})):
            raise StudioError('Body source path introduction differs from its exact native source context')
        receipt = actual
    else:
        from .body_target import target_descriptor
        source = target_descriptor(project, receipt['evidence']['selection']['path'], receipt['evidence']['target']['path'])
        if source['evidence'] != receipt['evidence']:
            raise StudioError('Body source path original selection, target or adapter changed')
    if (receipt.get('status') != 'NATIVE_BODY_TARGET_MEASURED' or receipt.get('native_reopened') is not True or
            receipt.get('cache_key') != digest({k: v for k, v in receipt.items() if k != 'cache_key'}) or
            receipt.get('artifacts', {}).get('profile') != profile_ref or
            receipt.get('source_face_ids_preserved') is not True or receipt.get('topology_preserved') is not True or
            receipt.get('adapter_rebound_to_variant') is not False):
        raise StudioError('Body source paths require an exact reopened native body with preserved source identities')
    budget.check()
    return receipt, origin, verifier_reserve


def _sql_progress(budget):
    try: budget.check(); return 0
    except StudioError: return 1


def _code_sources():
    return {name: sha(ROOT/('a3d/'+name+'.py')) for name in CODE_SOURCES}


def _remove_fresh_marker(project, output_dir, marker_path, identity, marker):
    """Retire only this publication's exact fresh file after terminal refusal.

    Reports survive. A replaced marker or changed/linking path is someone
    else's file and must not be removed by this failed attempt.
    """
    try:
        checked = inside(project.root, output_dir+'/review-receipt.json')
        if checked != marker_path: return
        current = marker_path.lstat()
        if not stat.S_ISREG(current.st_mode) or (current.st_dev, current.st_ino) != identity: return
        with marker_path.open('rb') as stream:
            opened = os.fstat(stream.fileno())
            if (opened.st_dev, opened.st_ino) != identity: return
            observed = stream.read(len(marker)+1)
        if observed != marker: return
        current = marker_path.lstat()
        if (current.st_dev, current.st_ino) == identity:
            marker_path.unlink()
    except (FileNotFoundError, NotADirectoryError, StudioError):
        return


def _projection_board(profile, geometry, result, display, budget):
    """Bounded orthographic source projections, not a Blender/occlusion render."""
    basis = _frame(profile); vertices = geometry['vertices_cm']; faces = geometry['faces']
    local = [[math.fsum((p[k]-basis['origin_cm'][k])*basis[axis][k] for k in range(3))
              for axis in ('right', 'forward', 'up')] for p in vertices]
    stride = max(1, math.ceil(len(faces)/display['max_faces'])); displayed = list(range(0, len(faces), stride))
    width, height = display['width_px'], display['height_px']; parts = []; encoded = 0
    def append(text):
        nonlocal encoded
        encoded += len(text.encode('utf-8'))
        if encoded > budget.limits['max_output_bytes']: raise StudioError('Body source projection storage budget exceeded')
        parts.append(text)
    append('<svg xmlns="http://www.w3.org/2000/svg" width="'+str(width)+'" height="'+str(height)+'" viewBox="0 0 '+str(width)+' '+str(height)+'">')
    append('<rect width="100%" height="100%" fill="white"/><g font-family="sans-serif" font-size="13">')
    views = [('Face', 1., 0.), ('Profil', 0., 1.), ('Dos', -1., 0.), ('Trois-quarts', 2**-.5, 2**-.5)]
    for view, (name, a, b) in enumerate(views):
        budget.check(); projected = [[a*p[0]+b*p[1], p[2]] for p in local]
        lo = [min(p[k] for p in projected) for k in (0, 1)]; hi = [max(p[k] for p in projected) for k in (0, 1)]
        legend_height = 64+20*len(result['paths'])
        cell_w, cell_h = width/2, (height-legend_height)/2; x0, y0 = (view%2)*cell_w, (view//2)*cell_h
        if cell_h < 100: raise StudioError('Body source path display has too many legends for its pixel budget')
        scale = min((cell_w-70)/max(hi[0]-lo[0], 1e-10), (cell_h-65)/max(hi[1]-lo[1], 1e-10))
        def pixels(index):
            x, y = projected[index]
            return f'{x0+cell_w/2+(x-(lo[0]+hi[0])/2)*scale:.3f},{y0+35+(hi[1]-y)*scale:.3f}'
        append(f'<text x="{x0+18:.3f}" y="{y0+20:.3f}">{name}</text>')
        depth = lambda index: math.fsum(-b*local[i][0]+a*local[i][1] for i in faces[index])/len(faces[index])
        for index in sorted(displayed, key=lambda index: (depth(index), index)):
            budget.check()
            append('<polygon points="'+' '.join(pixels(i) for i in faces[index])+'" fill="#e7ebee" stroke="#bbc3c9" stroke-width=".3"/>')
        for path in result['paths']:
            append('<polyline points="'+' '.join(pixels(i) for i in path['vertex_ids']+[path['vertex_ids'][0]])+
                   '" fill="none" stroke="#d12435" stroke-width="2"/>')
    for index, path in enumerate(result['paths']):
        append('<text x="18" y="'+str(height-legend_height+28+index*20)+'">'+html.escape(path['display_name'])+
               ' — frontière source ; homologie anatomique à revoir</text>')
    append('<text x="18" y="'+str(height-20)+'">Projections source, sans contrôle d’occlusion ; arrondis SVG uniquement, mesures non arrondies.</text></g></svg>')
    budget.check()
    return ''.join(parts).encode('utf-8'), {'scope': 'SOURCE_ORTHOGRAPHIC_PROJECTIONS_ONLY',
        'display_face_ids': displayed, 'all_measurement_edges_displayed': True,
        'face_sampling_stride': stride, 'source_mesh_changed': False, 'occlusion': 'NOT_QUALIFIED',
        'display_coordinate_decimal_places': 3, 'measurement_rounding': 'NONE'}


def prepare_project_body_path_review(project, body_profile_path, specification_path, output_dir):
    """Publish a fresh review bundle; canonical native origin is read-only."""
    relative(output_dir)
    if not output_dir.startswith('preparation/') or output_dir == 'preparation/':
        raise StudioError('Body source path review needs a fresh directory under preparation/')
    output = inside(project.root, output_dir, False)
    if output.exists(): raise StudioError('Body source path review output exists; preserve prior reports')
    specification_file = inside(project.root, specification_path)
    if specification_file.stat().st_size > MAX_SPEC_BYTES:
        raise StudioError('Body source path specification exceeds its fixed bootstrap reading limit')
    with specification_file.open('rb') as stream:
        raw_specification = stream.read(MAX_SPEC_BYTES+1)
    if len(raw_specification) > MAX_SPEC_BYTES:
        raise StudioError('Body source path specification exceeds its fixed bootstrap reading limit')
    try: specification = json.loads(raw_specification.decode('utf-8-sig'))
    except (UnicodeError, ValueError, RecursionError) as error:
        raise StudioError('Body source path specification JSON is invalid') from error
    budget = _Budget(specification); budget.charge(len(raw_specification))
    reader = _Reader(project, budget); reader.read(specification_path)
    if reader.refs[specification_path]['sha256'] != hashlib.sha256(raw_specification).hexdigest():
        raise StudioError('Body source path specification changed during bootstrap')
    code = _code_sources(); profile = reader.read(body_profile_path); profile_ref = reader.refs[body_profile_path]
    receipt, origin, verifier_reserve = _authenticated_target(project, profile_ref, reader)
    refs = receipt['artifacts']; geometry = reader.reference(refs['geometry'])
    original = reader.reference(refs['source-geometry']); adapter = reader.reference(receipt['evidence']['adapter'])
    options = reader.reference(refs['options']); derivation = reader.reference(refs['derivation'])
    stature = derivation.get('stature_derivation') if isinstance(derivation, dict) else None
    reader.reference(refs['triangles'], False)
    if (receipt.get('profile_cache_key') != profile.get('cache_key') or
            any(receipt.get(key) != profile.get(key) for key in ('geometry_sha256', 'pose_sha256')) or
            profile.get('options_sha256') != digest(options) or receipt.get('anatomy_adapter_sha256') != digest(adapter) or
            not isinstance(stature, dict) or stature != receipt['stature_derivation'] or
            geometry.get('dimension_derivation', {}).get('source_geometry_sha256') != stature.get('source_geometry_sha256') or
            geometry.get('dimension_derivation', {}).get('source_sha256') != original.get('source_sha256') or
            geometry.get('dimension_derivation', {}).get('source_pose_sha256') != original.get('pose_sha256') or
            stature.get('source_geometry_sha256') != digest([original['vertices_cm'], original['faces']])):
        raise StudioError('Body source path evaluated pose, adapter or stature derivation differs from its native origin')
    result = measure_source_body_paths(profile, geometry, original, adapter, specification, _budget=budget)
    result.update(native_body_origin=origin, input_refs=sorted(reader.refs.values(), key=lambda row: row['path']),
                  measurement_code_sha256=code, budgets=copy.deepcopy(specification['budgets']),
                  shared_verifier_reserved_read_bytes=verifier_reserve,
                  source_preservation='VERIFIED_BEFORE_PUBLICATION')
    artifacts = {}
    if 'opening_exploration' in specification:
        from .body_path_openings import prepare_opening_candidates, render_opening_candidates
        options = specification['opening_exploration']
        path = next(row for row in result['paths'] if row['id'] == options['path_id'])
        opening_started = time.monotonic(); opening_last = [opening_started]
        def opening_check():
            budget.check()
            current = time.monotonic()
            if (not math.isfinite(current) or current < opening_last[0] or
                    current-opening_started > options['max_seconds']):
                raise StudioError('Body opening exploration cumulative time budget exceeded or clock moved backwards')
            opening_last[0] = current
        opening_check()
        exploration = prepare_opening_candidates(profile, geometry, path, options, budget_check=opening_check)
        artifacts['opening-options.svg'] = render_opening_candidates(
            profile, geometry, exploration, options, budget_check=opening_check)
        opening_check()
        if len(canonical(exploration))+len(artifacts['opening-options.svg']) > options['max_output_bytes']:
            raise StudioError('Body opening exploration report and diagram exceed their combined storage budget')
        result['opening_exploration'] = exploration
    if 'display' in specification:
        board, display = _projection_board(profile, geometry, result, specification['display'], budget)
        result['display'] = display; artifacts['projections.svg'] = board
    rows = ['# Frontières corporelles source à revoir', '',
            'Mesures des vraies arêtes 3D du corps natif. Homologie anatomique à revoir ; aucune mensuration, aisance ou gate remplacée.', '',
            '| Source | Régions | Longueur 3D (cm, non arrondie) | Hauteur min/max dans le cadre du corps (cm) |',
            '| --- | --- | --- | --- |']
    for path in result['paths']:
        rows.append('| '+path['source_joint'].replace('|', '\\|')+' | '+str(path['source_regions'])+' | '+
                    repr(path['length_cm'])+' | '+repr(path['body_frame_height_range_cm'])+' |')
    if 'display' in specification: rows += ['', '![Projections du mesh et des frontières source](projections.svg)',
        '', 'Affichage sans contrôle d’occlusion. Les faces affichées peuvent être échantillonnées ; tous les segments mesurés sont surlignés.']
    if 'opening_exploration' in specification:
        rows += ['', '## Hypothèses d’ouverture à examiner', '',
                 '![Arcs omis et arcs corporels restants](opening-options.svg)', '',
                 'Les extrémités sont calculées dans l’ordre topologique de la vraie boucle, depuis son intersection sagittale frontale.',
                 'Aucune ouverture, aisance ou correspondance au patron n’est choisie. Ces hypothèses requièrent leur propre revue.']
    rows += ['', 'La frontière entre régions source n’est pas automatiquement une mesure de tailleur. Le corps, la pose et le profil sont conservés.',
             'Fitting, Cloth et Blender : non exécutés. Acceptation : non accordée.', '', 'Références exactes :', '']
    rows += ['- '+ref['path']+' — `'+ref['sha256']+'`' for ref in result['input_refs']]
    rows += ['', 'Identités du code :', '']+['- '+name+' : `'+value+'`' for name, value in sorted(code.items())]
    artifacts['report.md'] = ('\n'.join(rows)+'\n').encode('utf-8')
    artifacts['report.json'] = canonical(result)
    if sum(map(len, artifacts.values())) > budget.limits['max_output_bytes']:
        raise StudioError('Body source path report storage budget exceeded')
    reader.preserve()
    if _code_sources() != code: raise StudioError('Body source path code changed during preparation')
    budget.check(); output.mkdir(parents=True, exist_ok=False)
    for name, blob in artifacts.items():
        budget.check()
        with (output/name).open('xb') as stream: stream.write(blob)
    # This final marker distinguishes complete bundles from files left by an
    # interrupted write. It is not a canonical/native/product receipt.
    reader.preserve()
    if _code_sources() != code: raise StudioError('Body source path code changed during publication')
    completed = {'version': 1, 'status': 'BODY_SOURCE_PATH_REVIEW_PREPARED', 'qualification': 'NONE',
        'artifacts': {name: {'path': output_dir+'/'+name, 'sha256': sha(output/name)} for name in artifacts},
        'input_files_preserved': True, 'measurement_code_preserved': True, 'database': 'READ_ONLY_NATIVE_ORIGIN',
        'body_profile_changed': False, 'body_girths_replaced': False, 'ease_transferred': False,
        'tailoring_homology': 'REVIEW_REQUIRED', 'fitting': 'NOT_EXECUTED', 'Blender': 'NOT_EXECUTED',
        'acceptance': 'NOT_GRANTED', 'report': result}
    marker = canonical({key: value for key, value in completed.items() if key != 'report'})
    if sum(map(len, artifacts.values()))+len(marker) > budget.limits['max_output_bytes']:
        raise StudioError('Body source path final marker exceeds its storage budget; incomplete bundle preserved')
    budget.check()
    marker_path = output/'review-receipt.json'; identity = None
    try:
        with marker_path.open('xb') as stream:
            created = os.fstat(stream.fileno()); identity = (created.st_dev, created.st_ino)
            stream.write(marker)
        completed['review_receipt'] = {'path': output_dir+'/review-receipt.json', 'sha256': sha(marker_path)}
        budget.check()
    except BaseException:
        if identity is not None: _remove_fresh_marker(project, output_dir, marker_path, identity, marker)
        raise
    return completed
