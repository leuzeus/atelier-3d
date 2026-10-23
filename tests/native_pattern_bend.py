"""Isolated native Simple Deform coupons; geometry and rest contracts, no Cloth run."""
import copy
import json
import math
import os
from pathlib import Path
import sys

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))
import bpy
from a3d.core import StudioError, atomic_json, digest, read_json, sha
from a3d.pattern_assembly import map_digest
from a3d.pattern_preparation import preparation_statistics

OUT = Path(os.environ['A3D_VALIDATION_OUTPUT'])


def coupon(step=.5):
    nx, ny = round(10/step), round(20/step)
    rest = [[i*step, j*step, 0.] for j in range(ny+1) for i in range(nx+1)]
    faces = []
    for j in range(ny):
        for i in range(nx):
            a = j*(nx+1)+i
            faces.extend([[a,a+1,a+nx+2], [a,a+nx+2,a+nx+1]])
    bottom = list(range(nx+1))
    right = [j*(nx+1)+nx for j in range(ny+1)]
    top = [ny*(nx+1)+i for i in range(nx,-1,-1)]
    left = [j*(nx+1) for j in range(ny,-1,-1)]
    boundary = bottom[:-1]+right[:-1]+top[:-1]+left[:-1]
    payload = {'version':1, 'component_id':'coupon', 'source_garment_sha256':'synthetic:10x20cm',
        'rest_cm':rest, 'placed_cm':copy.deepcopy(rest), 'faces':faces, 'pins':{}, 'seams':{},
        'full_rest_area_cm2':200., 'panels':{'sheet':{'indices':list(range(len(rest))),
            'boundary':boundary, 'edges':{'bottom':bottom,'right':right,'top':top,'left':left}}}}
    plan = {'version':1, 'component_id':'coupon', 'source_refs':['synthetic:immutable-metric-coupon'],
        'mapping_sha256':map_digest(payload), 'preform':{'panels':{'sheet':{
            'source_ref':'synthetic:quarter-cylinder-axis-coupon', 'origin_cm':[0.,0.,0.],
            'u_axis':[1.,0.,0.], 'v_axis':[0.,1.,0.], 'native_bend':{
                'angle_degrees':90., 'deform_axis':'Z', 'origin_cm':[5.,0.,0.],
                'rotation_degrees':[-90.,0.,0.]}}}},
        'assembly':{'max_initial_gap_cm':1., 'max_displacement_cm':30.,
            'max_step_cm':.03, 'iterations':10, 'neighborhood_rings':2, 'closure_support_release':1.},
        'consolidation':{'weld_gap_cm':.01},
        'quality':{'min_angle_degrees':40., 'min_edge_cm':.1, 'min_stretch':.99, 'max_stretch':1.01},
        'supports':{'temporary':[], 'drape':[], 'functional':[]},
        'collision':{'required':False, 'clearance_cm':0., 'source_ref':'synthetic:free-axis-coupon'}}
    return payload, plan


def inventory():
    return {'objects':sorted(o.name for o in bpy.data.objects),
        'meshes':sorted(m.name for m in bpy.data.meshes),
        'collections':sorted(c.name for c in bpy.data.collections),
        'shape_keys':sorted(k.name for k in bpy.data.shape_keys),
        'selected':sorted(o.name for o in bpy.context.selected_objects),
        'active':bpy.context.view_layer.objects.active.name if bpy.context.view_layer.objects.active else None,
        'frame':bpy.context.scene.frame_current}


def raw_bend(payload, spec):
    """Use the native modifier directly only to establish observable axes/signs."""
    before = inventory()
    mesh = bpy.data.meshes.new('TEST.BendAxis.Mesh')
    mesh.from_pydata([[x/100 for x in p] for p in payload['rest_cm']], [], payload['faces'])
    obj = bpy.data.objects.new('TEST.BendAxis',mesh)
    origin = bpy.data.objects.new('TEST.BendAxis.Origin',None)
    bpy.context.scene.collection.objects.link(obj)
    bpy.context.scene.collection.objects.link(origin)
    evaluated = None
    try:
        origin.location = [x/100 for x in spec['origin_cm']]
        origin.rotation_euler = [math.radians(x) for x in spec['rotation_degrees']]
        modifier = obj.modifiers.new('NativeBend','SIMPLE_DEFORM')
        modifier.deform_method = 'BEND'
        modifier.deform_axis = spec['deform_axis']
        modifier.angle = math.radians(spec['angle_degrees'])
        modifier.origin = origin
        modifier.limits = (0.,1.)
        bpy.context.view_layer.update()
        evaluated = obj.evaluated_get(bpy.context.evaluated_depsgraph_get())
        result = evaluated.to_mesh()
        assert [list(p.vertices) for p in result.polygons] == payload['faces']
        assert len(result.vertices) == len(payload['rest_cm'])
        coords = [[x*100 for x in v.co] for v in result.vertices]
    finally:
        if evaluated is not None:
            evaluated.to_mesh_clear()
        bpy.data.objects.remove(obj,do_unlink=True)
        bpy.data.objects.remove(origin,do_unlink=True)
        bpy.data.meshes.remove(mesh)
    assert inventory() == before, 'Native axis probe leaked data or changed context'
    return coords


def coordinate_samples(payload, coords):
    wanted = {(0.,0.),(10.,0.),(0.,20.),(10.,20.),(5.,0.),(5.,20.),(0.,10.),(10.,10.),(5.,10.),
              (0.,5.),(0.,15.)}
    return [{'source_uv_cm':p[:2], 'target_cm':coords[i]}
        for i,p in enumerate(payload['rest_cm']) if tuple(p[:2]) in wanted]


def raw_axis_probes(payload):
    results = {}
    for axis, angle, rotation in [('Z',90.,-90.),('Z',90.,90.),('X',360.,-90.),('X',360.,90.),
                                  ('Y',360.,-90.),('Y',360.,90.),('Y',360.,0.)]:
        key = f'{axis}_{angle:g}_rotationX_{rotation:g}'
        spec = {'deform_axis':axis, 'angle_degrees':angle, 'origin_cm':[0.,0.,0.],
                'rotation_degrees':[rotation,0.,0.]}
        coords = raw_bend(payload,spec)
        stats = preparation_statistics(payload,coords=coords)
        results[key] = {'parameters':spec, 'samples':coordinate_samples(payload,coords),
            'min_principal_stretch':stats['extrema']['min_principal_stretch']['value'],
            'max_principal_stretch':stats['extrema']['max_principal_stretch']['value']}
    atomic_json(OUT/'native-axis-probes.json',results)
    return results


def checked_preform(payload, plan):
    from blender.preform import preform_coordinates
    before = inventory()
    payload_before = digest(payload)
    # The nonfinite-input witness must reach admission rather than fail inside
    # this test's snapshot helper. This string is not a production receipt.
    plan_before = json.dumps(plan,sort_keys=True,allow_nan=True)
    try:
        return preform_coordinates(payload, plan)
    finally:
        assert digest(payload) == payload_before, 'Native preform changed its source map'
        assert json.dumps(plan,sort_keys=True,allow_nan=True) == plan_before, 'Native preform changed its input plan'
        assert inventory() == before, 'Native preform leaked data or changed selection/context'


def expect_refusal(payload, plan, label):
    try:
        checked_preform(payload,plan)
    except StudioError as error:
        return {'status':'EXPECTED_REFUSAL', 'message':str(error),
                'reason_category':getattr(error,'reason_category',None)}
    raise AssertionError('Native Bend admitted '+label)


def verify_rest_persistence(payload, coords, plan):
    from blender.sewing import make_object, apply_physics, rest_key_name
    recipe = read_json(ROOT/'templates/sewing-recipe.json')
    recipe.update(component_id='coupon',seams={},placements={},pins=[],colliders=[])
    recipe['mesh'].update(plan['quality'])
    expected = {}
    for continuous in (False,True):
        candidate = copy.deepcopy(payload)
        candidate['placed_cm'] = copy.deepcopy(coords)
        if continuous:
            # A single already-continuous coupon verifies the post-consolidation
            # rest contract; it does not stand in for a sewn garment or a weld.
            candidate['rest_mode'] = 'assembled_3d'
            candidate['source_rest_triangles_cm'] = [[payload['rest_cm'][i][:2] for i in f]
                                                    for f in payload['faces']]
            candidate['rest_cm'] = copy.deepcopy(coords)
        name = 'TEST.ContinuousRest' if continuous else 'TEST.SourceFlatRest'
        obj = make_object(candidate,name)
        cloth, _, _ = apply_physics(obj,candidate,recipe,'mount',[])
        assert cloth.settings.rest_shape_key.name == rest_key_name(candidate)
        assert cloth.settings.use_dynamic_mesh is False
        assert cloth.settings.use_sewing_springs is False
        expected[name] = {'key':rest_key_name(candidate), 'rest_cm':candidate['rest_cm'],
                          'placement_cm':coords}
    path = OUT/'native-bend-rest-contract.blend'
    bpy.ops.wm.save_as_mainfile(filepath=str(path))
    bpy.ops.wm.open_mainfile(filepath=str(path),load_ui=False)
    for name, record in expected.items():
        obj = bpy.data.objects[name]
        cloth = next(m for m in obj.modifiers if m.type == 'CLOTH')
        assert cloth.settings.rest_shape_key.name == record['key']
        assert cloth.settings.use_dynamic_mesh is False
        assert cloth.settings.use_sewing_springs is False
        key = obj.data.shape_keys.key_blocks[record['key']]
        assert max(math.dist([x*100 for x in v.co],p)
                   for v,p in zip(key.data,record['rest_cm'],strict=True)) < 3e-6
        placement = obj.data.shape_keys.key_blocks['Placement']
        assert max(math.dist([x*100 for x in v.co],p)
                   for v,p in zip(placement.data,record['placement_cm'],strict=True)) < 3e-6
    return {'status':'PASS_CONFIGURATION_AND_REOPEN', 'path':str(path),
        'rest_keys':[record['key'] for record in expected.values()],
        'dynamic_mesh':False, 'simulation':'NOT_EXECUTED', 'qualification':'NONE'}


def backend_contracts(payload, plan):
    coords, report = checked_preform(payload,plan)
    assert report['qualification'] == 'NONE'
    backend = report['native_backends']['sheet']
    assert backend['backend'] == 'BLENDER_SIMPLE_DEFORM_BEND'
    assert backend['connectivity_preserved'] is True
    assert backend['temporary_data_cleaned'] is True
    assert backend['vertex_count'] == len(payload['rest_cm'])
    assert backend['face_count'] == len(payload['faces'])
    assert len(report['correspondence']) == len(payload['rest_cm'])
    for item in report['correspondence']:
        index = item['derived_vertex']
        assert item['source_uv_cm'] == payload['rest_cm'][index][:2]
        assert math.dist(item['target_cm'],coords[index]) < 1e-10
    stats = preparation_statistics(payload,coords=coords)
    low = stats['extrema']['min_principal_stretch']['value']
    high = stats['extrema']['max_principal_stretch']['value']
    assert .9997 < low < 1., (low,high)
    assert 1.-5e-6 < high < 1.+5e-6, (low,high)
    assert max(p[2] for p in coords)-min(p[2] for p in coords) > 1.8
    lookup = {tuple(p[:2]):i for i,p in enumerate(payload['rest_cm'])}
    longitudinal = [math.dist(coords[lookup[(i*.5,0.)]],coords[lookup[(i*.5,20.)]]) for i in range(21)]
    assert max(abs(length-20.) for length in longitudinal) < 3e-6
    for label, key, value in [('angle-sign','angle_degrees',-90.),
                              ('origin-orientation-sign','rotation_degrees',[90.,0.,0.])]:
        mirrored = copy.deepcopy(plan)
        mirrored['preform']['panels']['sheet']['native_bend'][key] = value
        opposite, _ = checked_preform(payload,mirrored)
        assert max(math.dist([p[0],p[1],-p[2]],q) for p,q in zip(coords,opposite,strict=True)) < 3e-6, label
    posed = copy.deepcopy(plan)
    posed['preform']['panels']['sheet'].update(origin_cm=[3.,-2.,1.],
                                               u_axis=[0.,1.,0.],v_axis=[-1.,0.,0.])
    posed_coords, _ = checked_preform(payload,posed)
    assert max(math.dist([3.-p[1],-2.+p[0],1.+p[2]],q)
               for p,q in zip(coords,posed_coords,strict=True)) < 3e-6
    # Re-evaluate the declarative modifier from source UV at another resolution;
    # no old vertex index is used to build the new preform.
    refined, refined_plan = coupon(.25)
    refined_coords, refined_report = checked_preform(refined,refined_plan)
    refined_lookup = {tuple(p[:2]):i for i,p in enumerate(refined['rest_cm'])}
    shared_error = max(math.dist(coords[i],refined_coords[refined_lookup[tuple(p[:2])]])
                       for i,p in enumerate(payload['rest_cm']))
    assert shared_error < 3e-6
    assert refined_plan['mapping_sha256'] != plan['mapping_sha256']
    refined_stats = preparation_statistics(refined,coords=refined_coords)
    assert refined_stats['extrema']['min_principal_stretch']['value'] > low
    # Reindex independently as well: source UV, not historical mesh indices,
    # is the durable location of a panel point.
    shuffled = copy.deepcopy(payload)
    count = len(shuffled['rest_cm'])
    shuffled['rest_cm'].reverse()
    shuffled['placed_cm'].reverse()
    shuffled['faces'] = [[count-1-i for i in face] for face in shuffled['faces']]
    panel = shuffled['panels']['sheet']
    panel['indices'] = [count-1-i for i in panel['indices']]
    panel['boundary'] = [count-1-i for i in panel['boundary']]
    panel['edges'] = {edge:[count-1-i for i in ids] for edge,ids in panel['edges'].items()}
    shuffled_plan = copy.deepcopy(plan)
    shuffled_plan['mapping_sha256'] = map_digest(shuffled)
    shuffled_coords, _ = checked_preform(shuffled,shuffled_plan)
    assert max(math.dist(p,q) for p,q in zip(coords,reversed(shuffled_coords),strict=True)) < 3e-6
    refusals = {}
    for label in ('wrong-radial-axis','wrong-flat-axis','nan-origin','zero-scale-frame','stale-map'):
        invalid = copy.deepcopy(plan)
        frame = invalid['preform']['panels']['sheet']
        if label == 'wrong-radial-axis':
            frame['native_bend'].update(deform_axis='Y',angle_degrees=360.)
        elif label == 'wrong-flat-axis':
            frame['native_bend']['rotation_degrees'] = [0.,0.,0.]
        elif label == 'nan-origin':
            frame['native_bend']['origin_cm'][0] = math.nan
        elif label == 'zero-scale-frame':
            frame['u_axis'] = [0.,0.,0.]
        else:
            invalid['mapping_sha256'] = '0'*64
        refusals[label] = expect_refusal(payload,invalid,label)
    from a3d.pattern_assembly import preform_coordinates as pure_preform
    try:
        pure_preform(payload,plan)
    except StudioError as error:
        refusals['missing-native-backend'] = {'status':'EXPECTED_REFUSAL','message':str(error)}
    else:
        raise AssertionError('Pure preform silently ignored native Bend')
    atomic_json(OUT/'native-bend-map.json',payload)
    atomic_json(OUT/'native-bend-plan.json',plan)
    atomic_json(OUT/'native-bend-preform.json',report)
    persistence = verify_rest_persistence(payload,coords,plan)
    return {'status':'PASS', 'source_vertices':len(payload['rest_cm']), 'source_faces':len(payload['faces']),
        'principal_stretch':[low,high], 'longitudinal_length_cm':[min(longitudinal),max(longitudinal)],
        'bending':stats['bending'], 'source_map_unchanged':True, 'native_temporary_data_cleaned':True,
        'remesh':{'vertices':len(refined['rest_cm']), 'shared_position_max_error_cm':shared_error,
                  'principal_stretch_min':refined_stats['extrema']['min_principal_stretch']['value']},
        'reindexed_source_uv_positions_preserved':True, 'refusals':refusals,
        'rest_persistence':persistence, 'simulation':'NOT_EXECUTED', 'qualification':'NONE'}


def contact_contracts(map_path):
    """Replay one immutable derived fixture; no rendering, mesh edits or Cloth."""
    from blender.pattern_assembly import self_contact_report, require_prepared_native_preform
    source = Path(map_path).resolve(strict=True)
    assert source.drive.upper() == 'G:'
    original_hash = sha(source)
    payload = read_json(source)
    old = read_json(source.with_name('receipt.json'))['collision']['self_contact']
    assert old['nonadjacent_overlap_count'] == 2
    report = self_contact_report(payload,payload['placed_cm'],.15)
    assert report['ok'] and report['nonadjacent_overlap_count'] == 0,report
    nonpartners = copy.deepcopy(payload)
    for seam in nonpartners['seams'].values():
        if seam['piece_a']==seam['piece_b']:
            seam['kind']='closure'
    open_report = self_contact_report(nonpartners,nonpartners['placed_cm'],.15)
    assert not open_report['ok'] and open_report['nonadjacent_overlap_count'] >= 2,open_report
    assert all(pair in open_report['nonadjacent_face_overlaps'] for pair in old['nonadjacent_face_overlaps'])
    # Intersecting noncoplanar triangles exercise the exclusion policy without
    # depending on BVH's incomplete handling of exactly coplanar triangles.
    coords = [[0.,0.,0.],[2.,0.,0.],[0.,2.,0.],
              [0.,0.,0.],[2.,2.,1.],[2.,2.,-1.],[0.,0.,0.]]
    fixture = {'faces':[[0,1,2],[3,4,5]],'seams':{}}
    refusals = {}
    for label,kind,pairs in [('no-partner','permanent',[]),
                            ('partner-too-far','permanent',[[0,4]]),
                            ('closure-open','closure',[[0,3]]),
                            ('detachable-open','detachable',[[0,3]]),
                            ('transitive-only','permanent',[[0,6],[6,3]])]:
        fixture['seams']={'test':{'kind':kind,'pairs':pairs}}
        overlap = self_contact_report(fixture,coords,.15)
        assert overlap['nonadjacent_overlap_count'] == 1,(label,overlap)
        refusals[label]={'status':'EXPECTED_REFUSAL','nonadjacent_overlap_count':1}
    fixture['seams']={'test':{'kind':'permanent','pairs':[[0,3]]}}
    assert self_contact_report(fixture,coords,.15)['nonadjacent_overlap_count'] == 0
    _, plan = coupon()
    for readiness in (None,'NEEDS_CORRECTION','NEEDS_CLARIFICATION'):
        preparation = ({'readiness':readiness},{}) if readiness else None
        try:
            require_prepared_native_preform(plan,preparation)
        except StudioError:
            pass
        else:
            raise AssertionError('Bend admitted without READY preparation: '+str(readiness))
    require_prepared_native_preform(plan,({'readiness':'READY'},{}))
    flat_plan=copy.deepcopy(plan)
    del flat_plan['preform']['panels']['sheet']['native_bend']
    require_prepared_native_preform(flat_plan,None)
    assert sha(source)==original_hash
    result={'status':'PASS','source':str(source),'source_sha256':original_hash,
        'source_unchanged':True,'previous_recorded_self_contact':old,'current_self_contact':report,
        'same_fixture_undeclared_or_open_partners':open_report,'synthetic_refusals':refusals,
        'native_bend_requires_ready_preparation':'PASS_ADMISSION_ONLY',
        'simulation':'NOT_EXECUTED','qualification':'NONE'}
    atomic_json(OUT/'contact-result.json',result)
    print('NATIVE_BEND_CONTACT_PASS '+str(OUT/'contact-result.json'),flush=True)


def main():
    assert OUT.drive.upper() == 'G:'
    bpy.context.preferences.filepaths.temporary_directory = str(OUT/'tmp')
    if '--contact-map' in sys.argv:
        contact_contracts(sys.argv[sys.argv.index('--contact-map')+1])
        return
    payload, plan = coupon()
    axes = raw_axis_probes(payload)
    print('NATIVE_BEND_AXES '+str(OUT/'native-axis-probes.json'),flush=True)
    if '--raw-only' in sys.argv:
        return
    result = backend_contracts(payload,plan)
    result['blender_version'] = bpy.app.version_string
    result['blender_build_hash'] = bpy.app.build_hash.decode()
    atomic_json(OUT/'result.json',result)
    print('NATIVE_BEND_PASS '+str(OUT/'result.json'),flush=True)


if __name__ == '__main__':
    main()
