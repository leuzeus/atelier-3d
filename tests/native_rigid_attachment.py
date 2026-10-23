"""Rigid attachment kernel fixture on an actual canonical TEST_ONLY Cloth clip.

Run isolated Blender --background --factory-startup --offline-mode
--python-exit-code 1. The synthetic cuboid has no provider/job/calibration
provenance. This deliberately exercises only the native transform/reimport
kernel, never the public admission API or the production garment.
"""
import argparse
import copy
from pathlib import Path
import sys
import time

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))


def arguments(argv):
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--output', required=True)
    parser.add_argument('--source-project', required=True)
    parser.add_argument('--source-receipt', required=True)
    parser.add_argument('--validate-only', action='store_true')
    args = parser.parse_args(argv)
    output, project, receipt = map(Path, (args.output, args.source_project, args.source_receipt))
    if (not all(path.is_absolute() and path.drive.lower() == 'g:' for path in (output, project, receipt)) or
            output.exists() or not (project/'.a3d/state.sqlite3').is_file() or not receipt.is_file() or
            not receipt.resolve().is_relative_to(project.resolve())):
        parser.error('Require a new G: output, an existing exact project and its canonical TEST_ONLY receipt')
    args.output, args.source_project, args.source_receipt = output.resolve(), project.resolve(), receipt.resolve()
    return args


def _ref(project, path):
    from a3d.core import sha
    return {'path': path.relative_to(project.root).as_posix(), 'sha256': sha(path)}


def _synthetic_source(project, directory, campaign):
    import bpy
    from a3d.core import atomic_json, digest
    name = 'A3D.Fixture.RigidCuboid.'+campaign
    # Width, depth, height in metres, matching measured dimensions W/H/D.
    points = [[x*.036, y*.0035, z*.034] for x, y, z in
              ((-1,-1,-1),(1,-1,-1),(1,1,-1),(-1,1,-1),
               (-1,-1,1),(1,-1,1),(1,1,1),(-1,1,1))]
    faces = [[0,3,2,1],[4,5,6,7],[0,1,5,4],[1,2,6,5],[2,3,7,6],[3,0,4,7]]
    mesh = bpy.data.meshes.new(name); mesh.from_pydata(points, [], faces); mesh.update()
    obj = bpy.data.objects.new(name, mesh)
    artifact = directory/'synthetic-cuboid.blend'
    # Static source needs only its object/data. Writing a newly created,
    # unevaluated scene enters Blender 5.2's view-layer copy path before its
    # collection caches exist (native access violation in BKE_view_layer_copy).
    # No scene state is a dependency of this synthetic static cuboid.
    bpy.data.libraries.write(str(artifact), {obj, mesh}, fake_user=True)
    geometry = {obj.name: {'vertices_cm': [[float(v)*100 for v in row.co] for row in obj.data.vertices],
                           'faces': [list(row.vertices) for row in obj.data.polygons]}}
    geometry_path = directory/'synthetic-geometry.json'; atomic_json(geometry_path, geometry)
    declaration = directory/'synthetic-source.json'
    atomic_json(declaration, {'version': 1, 'scope': 'SYNTHETIC_FUNCTION_FIXTURE_ONLY',
                              'provider': 'NOT_CLAIMED', 'job': 'NOT_CLAIMED',
                              'canonical_calibration': 'NOT_EXECUTED',
                              'measured_dimensions_cm': [7.2,6.8,.7]})
    typed = _ref(project, declaration)
    source = {'artifact': _ref(project, artifact), 'geometry': _ref(project, geometry_path),
              'geometry_sha256': digest(geometry), 'measured_dimensions_cm': [7.2,6.8,.7],
              'candidate': typed, 'profile': typed, 'package': typed, 'dossier': typed}
    bpy.data.batch_remove(ids={obj,mesh})
    return name, source, geometry, typed


def run(output, source_project, source_receipt):
    import bpy
    from a3d.core import StudioError, atomic_json, digest, read_json, sha
    from a3d.store import Project
    from a3d.garment_motion import canonical_garment_clip
    from a3d.cloth_metrics import face_sources
    from a3d.rigid_attachment import attachment_frames, bind_selectors, source_axes
    from a3d.animated_delivery import rigid_leaf
    from blender.rigid_attachment import _run_attachment
    from blender.body_source import data_ids, live_geometry
    assert bpy.app.background and not bpy.data.filepath and bpy.context.mode == 'OBJECT'
    project = Project(source_project); database_sha = sha(project.db)
    reference = _ref(project, source_receipt); target, target_origin = canonical_garment_clip(project, reference)
    if target['purpose'] != 'TEST_ONLY':
        raise StudioError('Synthetic rigid fixture refuses all production source clips')
    output.mkdir(parents=True, exist_ok=False); campaign = digest(str(output))[:12]
    directory = project.data/('native-rigid-kernel-'+campaign); directory.mkdir(parents=True, exist_ok=False)
    protected = {}
    def collect(value):
        if isinstance(value, dict):
            if set(value) == {'path','sha256'}: protected[value['path']] = value['sha256']
            else:
                for child in value.values(): collect(child)
        elif isinstance(value, list):
            for child in value: collect(child)
    collect(reference); collect(target); collect(target_origin)
    obj_name, source, geometry, declaration = _synthetic_source(project, directory, campaign)
    print('RIGID_KERNEL_STATIC_SOURCE_WRITTEN',flush=True)
    candidate = read_json(project.root/target['bindings']['candidate']['path'])
    observations = read_json(project.root/target['observations_artifact']['path'])
    recipe = read_json(project.root/target['bindings']['recipe']['path'])
    sources = face_sources(candidate)
    if sources['binding_issues']: raise StudioError('Canonical fixture source UV mapping is invalid')
    triangle = sources['source_rest_triangles_cm'][0]; piece_id = sources['source_face_pieces'][0]
    def uv(weights):
        return [sum(weight*point[axis] for weight,point in zip(weights,triangle)) for axis in range(2)]
    mapping = {'piece_id': piece_id, 'scope': 'SYNTHETIC_FUNCTION_FIXTURE_ONLY',
               'origin': {'kind':'UV','uv_cm':uv([1/3,1/3,1/3])},
               'right': {'kind':'UV','uv_cm':uv([.2,.6,.2])},
               'up': {'kind':'UV','uv_cm':uv([.2,.2,.6])}}
    mapping_path = directory/'synthetic-anchor-map.json'; atomic_json(mapping_path, mapping)
    bindings = bind_selectors(candidate, mapping, {})
    reserve = recipe['phases']['drape']['collision_distance_cm']; offset = .7/2+reserve
    frames = attachment_frames(candidate, observations['frames'], bindings,
                               source_axes({'axis':[0,-1,0],'up':[0,0,1]}),
                               [0.,0.,0.], offset, 90., None, .001)
    profile = {'component_id':'fixture.buckle','piece_id':'fixture.buckle','purpose':'TEST_ONLY',
               'object_name':obj_name,'source_receipt':declaration,'anchor_map_ref':_ref(project,mapping_path),
               'geometry_tolerance_cm':.001,'budgets':{'max_seconds':900.,'max_samples':len(frames)+1,
                                                      'max_normal_turn_degrees':90.}}
    inputs = {'profile':profile,'source':source,'geometry':geometry,
              'clips':[{'declaration':{'id':'fixture-attachment','target_receipt':reference},
                        'target':target,'target_origin':target_origin,'candidate':candidate,
                        'observations':observations,'bindings':bindings,'frames':frames,
                        'offset':{'mode':'PART_HALF_DEPTH_PLUS_RECIPE_COLLISION_DISTANCE',
                                  'part_depth_cm':.7,'recipe_ref':target['bindings']['recipe'],
                                  'reserve_cm':reserve,'offset_cm':offset}}]}
    baseline, live = data_ids(), live_geometry()
    before_state = digest(project.state())
    try:
        print('RIGID_KERNEL_ATTACHMENT_AND_REIMPORT_BEGIN',flush=True)
        result = _run_attachment(project, inputs, directory, time.monotonic()+900.)
        result.update(version=1,purpose='TEST_ONLY',component_id='fixture.buckle',piece_id='fixture.buckle',
                      scope='SYNTHETIC_FUNCTION_FIXTURE_ONLY',public_admission='NOT_EXECUTED',
                      provider_calibration='NOT_CLAIMED')
        assert result['status']=='RIGID_PART_PREPARED_UNACCEPTED' and result['parent_created'] is False
        assert result['intrinsic_dimensions_cm']==[7.2,6.8,.7]
        assert result['native_reimport_comparison']['sample_count']==len(frames)+1
        assert result['clips'][0]['executed_times']==[row['frame'] for row in frames]
        assert result['clips'][0]['animation_target']=='OBJECT'
        assert {row['animation_target'] for row in result['clips'][0]['tracks']}=={'OBJECT','SHAPE_KEYS'}
        fixture_receipt = directory/'kernel-result.json'; atomic_json(fixture_receipt,result)
        # No journal callback is manufactured. The public compositor must reject
        # this kernel-only proof even for TEST_ONLY admission.
        try:
            rigid_leaf(project,{'component_id':'fixture.buckle',
                                'source_receipt':_ref(project,fixture_receipt),'object_name':result['object_names'][0]},False)
        except StudioError: pass
        else: raise AssertionError('Unregistered kernel fixture was admitted as a canonical native rigid leaf')
    finally:
        bpy.data.batch_remove(ids=data_ids()-baseline)
        assert data_ids()==baseline and live_geometry()==live
        assert sha(project.db)==database_sha and digest(project.state())==before_state
        for path,identity in protected.items(): assert sha(project.root/path)==identity
    receipt = {'version':1,'status':'NATIVE_RIGID_ATTACHMENT_KERNEL_PASS',
               'scope':'SYNTHETIC_FUNCTION_FIXTURE_ONLY','source_project':str(source_project),
               'source_clip':reference,'result':result,'public_admission':'NOT_EXECUTED',
               'provider_calibration':'NOT_CLAIMED','source_database_preserved':True,
               'source_files_preserved':True,'production_qualification':'NOT_GRANTED',
               'fitting':'NOT_QUALIFIED','placement_review':'HUMAN_REVIEW_REQUIRED'}
    atomic_json(output/'receipt.json',receipt)
    print('NATIVE_RIGID_ATTACHMENT_KERNEL_PASS: '+str(output/'receipt.json'))


if __name__=='__main__':
    argv=sys.argv[sys.argv.index('--')+1:] if '--' in sys.argv else sys.argv[1:]
    args=arguments(argv)
    if args.validate_only: print('ARGUMENTS_VALIDATED: no native operation executed')
    else: run(args.output,args.source_project,args.source_receipt)
