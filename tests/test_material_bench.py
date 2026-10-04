import copy
import tempfile
import unittest
from pathlib import Path

from a3d.core import ROOT, StudioError, atomic_json, digest, read_json, sha
from a3d.material_bench import (compile_material_bench, case_recipe, coupon, comparison_report,
    _load_compiled, laboratory_conditions, SUPPORTED_SEEDS, observation_summary, coupon_response)
from a3d.store import Project
from tests.support import asset


def bench_fixture(project):
    recipe=read_json(ROOT/'templates/sewing-recipe.json')
    bindings={}
    for name,value in [('candidate',{'fixture':'CANDIDATE_NOT_QUALIFIED'}), ('source',{'fixture':'APPROVED_TEST_ONLY'}),
                       ('body',{'fixture':'BODY_REFERENCE_ONLY'}), ('pose',{'fixture':'POSE_REFERENCE_ONLY'}), ('recipe',recipe)]:
        path=project.root/(name+'.json'); atomic_json(path,value)
        bindings[name]={'path':path.name,'sha256':sha(path)}
    return {'version':1,'id':'material-test','component_id':'garment.coat','phase':'drape','bindings':bindings,
        'programs':['cantilever','sewing'], 'factor':{'parameter':'bending_stiffness','values':[.003,.3]},
        'execution':{'fps':24,'max_frames':32,'max_seconds':2.,'min_frames':8,'window_frames':3,'velocity_tolerance_cm_s':.01}}


class MaterialBench(unittest.TestCase):
    def setUp(self):
        folder=ROOT/'work/test-material-bench'; folder.mkdir(parents=True,exist_ok=True)
        self.temp=tempfile.TemporaryDirectory(dir=folder); self.root=Path(self.temp.name)
        self.project=Project.create(self.root,asset(True)); self.spec=bench_fixture(self.project)
        atomic_json(self.root/'spec.json',self.spec)
    def tearDown(self): self.temp.cleanup()
    def test_compile_preserves_sources_and_prepares_dag_without_physics_or_gate(self):
        before=self.project.state(); identities={ref['path']:ref['sha256'] for ref in self.spec['bindings'].values()}
        prepared=compile_material_bench(self.project,'spec.json','compiled')
        self.assertEqual(prepared['case_count'],4); self.assertFalse(prepared['executed'])
        self.assertEqual(self.project.state(),before)
        for path,identity in identities.items(): self.assertEqual(sha(self.root/path),identity)
        run=read_json(self.root/prepared['run_specification']['path'])
        self.assertEqual(run['units'][0]['operation'],'run_material_bench')
        self.assertEqual(run['budgets']['max_seconds'],8.)
        with self.assertRaises(StudioError): compile_material_bench(self.project,'spec.json','compiled')
    def test_only_factor_changes_and_all_source_physics_remains_identical(self):
        recipe=read_json(self.root/'recipe.json'); before=digest(recipe)
        soft=case_recipe(recipe,self.spec,.003); stiff=case_recipe(recipe,self.spec,.3)
        stiff['phases']['drape']['bending_stiffness']=.003
        self.assertEqual(soft,stiff); self.assertEqual(digest(recipe),before)
        self.assertEqual(soft['phases']['drape']['execution_control']['max_seconds'],2.)
    def test_stale_body_pose_and_recomputed_forged_case_inventory_are_refused(self):
        prepared=compile_material_bench(self.project,'spec.json','compiled'); path=self.root/prepared['bench']['path']
        doc=read_json(path); doc['cases']*=2; doc.pop('fingerprint'); doc['fingerprint']=digest(doc); atomic_json(path,doc)
        with self.assertRaises(StudioError): _load_compiled(self.project,prepared['bench']['path'])
        (self.root/'body.json').write_text('{}')
        with self.assertRaises(StudioError): compile_material_bench(self.project,'spec.json','other')
    def test_nan_boolean_missing_controls_and_hidden_regional_recipe_are_refused(self):
        for failure in ('bool','nan','window','fps','regional','spacing'):
            spec=copy.deepcopy(self.spec); recipe=read_json(ROOT/'templates/sewing-recipe.json')
            if failure=='bool':spec['factor']['values'][0]=True
            if failure=='nan':spec['factor']['values'][0]=float('nan')
            if failure=='window':spec['execution']['window_frames']=32
            if failure=='fps':spec['execution']['fps']=30
            if failure=='regional':recipe['phases']['drape']['regional_stiffness']={}
            if failure=='spacing':recipe['mesh']['spacing_cm']=.1
            atomic_json(self.root/'recipe.json',recipe); spec['bindings']['recipe']['sha256']=sha(self.root/'recipe.json')
            if failure=='nan':
                with self.assertRaises(ValueError): atomic_json(self.root/'bad.json',spec)
                continue
            atomic_json(self.root/'bad.json',spec)
            with self.subTest(failure=failure),self.assertRaises(StudioError):
                compile_material_bench(self.project,'bad.json','bad-output')
    def test_fixed_coupon_clamp_topology_and_case_comparison_cannot_select_material_or_fit(self):
        first=coupon('cantilever',2.); second=coupon('cantilever',2.)
        self.assertEqual(first,second); self.assertEqual(len(first['rest_cm']),66)
        self.assertTrue(first['pins']); self.assertEqual(first['seams'],{})
        for invalid in (True,float('nan'),.01):
            with self.assertRaises(StudioError): coupon('cantilever',invalid)
        report=comparison_report({'factor':self.spec['factor']},[
            {'case_id':'a','status':'PASS'},{'case_id':'b','status':'INCOMPLETE'}])
        self.assertFalse(report['automatic_selection']); self.assertFalse(report['accepted'])
        self.assertEqual(report['fitting'],'NOT_EXECUTED'); self.assertEqual(report['qualification'],'COUPON_ONLY')
    def test_supported_seeds_have_fixed_distinct_geometry_and_admitted_narrow_seam(self):
        conditions=laboratory_conditions(SUPPORTED_SEEDS)
        beam=coupon('cantilever',2.,SUPPORTED_SEEDS)
        self.assertEqual(len(beam['rest_cm']),36)
        self.assertEqual(beam['full_rest_area_cm2'],100.)
        self.assertEqual(max(point[1] for point in beam['rest_cm']),10.)
        seam=coupon('sewing',2.,SUPPORTED_SEEDS)
        import math
        gaps=[math.dist(seam['placed_cm'][a],seam['placed_cm'][b]) for a,b in seam['seams']['coupon']['pairs']]
        self.assertTrue(all(abs(gap-.1)<1e-12 for gap in gaps))
        self.assertTrue(all(a!=b for a,b in seam['seams']['coupon']['pairs']))
        self.assertEqual(len(seam['rest_cm']),72)
        self.assertIn('NOT_WIDE_GAP_CLOSURE',conditions['sewing']['scope'])
        contact=coupon('contact',2.,SUPPORTED_SEEDS)
        self.assertEqual(len(contact['pins']),6)
        self.assertLess(len(contact['pins']),len(contact['rest_cm']))
        self.assertTrue(all(contact['placed_cm'][int(index)][1]==0. for index in contact['pins']))
        self.assertTrue(all(point[2]==.6 for point in contact['placed_cm']))
        self.assertEqual(conditions['contact']['support_thickness_outer_cm'],.1)
        from blender.cloth_contacts import precise_self_contacts
        for program in ('cantilever','sewing','contact'):
            source=coupon(program,2.,SUPPORTED_SEEDS)
            measured=precise_self_contacts(source,source['placed_cm'],.15,.3)
            self.assertTrue(measured['ok'])
            self.assertEqual(measured['contact_count'],0)
            self.assertEqual(measured['settled_direct_permanent_pairs'],6 if program=='sewing' else 0)
            self.assertEqual(measured['declared_seam_adjacency_tolerance_cm'],.15)
            self.assertEqual(measured['required_clearance_cm'],.3)
        with self.assertRaises(StudioError):laboratory_conditions('unknown')
    def test_supported_damping_cases_bind_equal_seeds_and_one_physical_factor(self):
        self.spec['laboratory']={'seed_set':SUPPORTED_SEEDS}
        self.spec['factor']={'parameter':'structural_damping','values':[1.,20.]}
        self.spec['programs']=['cantilever','sewing','contact']
        atomic_json(self.root/'spec.json',self.spec)
        prepared=compile_material_bench(self.project,'spec.json','supported')
        doc=_load_compiled(self.project,prepared['bench']['path'])
        self.assertEqual(doc['laboratory_conditions'],laboratory_conditions(SUPPORTED_SEEDS))
        for program in self.spec['programs']:
            a,b=[case for case in doc['cases'] if case['program']==program]
            self.assertEqual(a['coupon_sha256'],b['coupon_sha256'])
            self.assertEqual(a['source_conditions_sha256'],b['source_conditions_sha256'])
            first=copy.deepcopy(a['recipe']); second=copy.deepcopy(b['recipe'])
            second['phases']['drape']['structural_damping']=1.
            self.assertEqual(first,second)
            self.assertEqual(first['limits'],read_json(self.root/'recipe.json')['limits'])
        doc['laboratory_conditions']['sewing']['initial_gap_cm']=.001
        doc.pop('fingerprint');doc['fingerprint']=digest(doc)
        atomic_json(self.root/prepared['bench']['path'],doc)
        with self.assertRaises(StudioError):_load_compiled(self.project,prepared['bench']['path'])
    def test_supported_geometry_incompatible_source_gates_are_refused_before_native(self):
        self.spec['laboratory']={'seed_set':SUPPORTED_SEEDS}
        self.spec['programs']=['cantilever','sewing','contact']
        for gate,value in [('max_displacement_cm',10.),('weld_gap_cm',.05),('max_seam_gap_cm',.05),('collision_distance_cm',.6)]:
            recipe=read_json(ROOT/'templates/sewing-recipe.json')
            if gate=='collision_distance_cm':recipe['phases']['drape'][gate]=value
            else:recipe['limits'][gate]=value
            atomic_json(self.root/'recipe.json',recipe)
            spec=copy.deepcopy(self.spec);spec['bindings']['recipe']['sha256']=sha(self.root/'recipe.json')
            atomic_json(self.root/'bad.json',spec)
            with self.subTest(gate=gate),self.assertRaises(StudioError):
                compile_material_bench(self.project,'bad.json','refused')
    def test_observation_keeps_failed_frame_and_unqualified_budget_terminal_motion(self):
        frames=[{'frame':frame,'max_movement_cm':frame*.01,'max_seam_gap_cm':.1,
            'motion':{'max_increment':{'distance_cm':.001}},
            'quality':{'status':'PASS','metrics':{'min_principal_stretch':.999,'max_principal_stretch':1.001}},
            'contact':{'ok':frame<3,'status':'CONTACTS_CLEAR_DISCRETE' if frame<3 else 'REFUSED',
                'reason':None if frame<3 else 'INTERPOLATED_CONTACT','fraction':.8}}
            for frame in (1,2,3)]
        control={'stop_reason':'FRAME_BUDGET','evaluated_frames':2,'control':{'window_frames':2,'velocity_tolerance_cm_s':.01}}
        result=observation_summary(frames,24,control)
        self.assertEqual(result['evaluated_frame_count'],3)
        self.assertIsNone(result['samples'][0]['max_velocity_cm_s'])
        self.assertEqual(result['samples'][-1]['max_velocity_cm_s'],.024)
        self.assertFalse(result['terminal_window']['hard_gates_clear'])
        self.assertEqual(result['convergence'],'NOT_QUALIFIED')
        self.assertEqual(result['samples'][-1]['contact_fraction'],.8)
        self.assertIsNone(observation_summary([],24,control)['terminal_window']['hard_gates_clear'])
        with self.assertRaises(StudioError):observation_summary([frames[1]],24,control)
        payload=coupon('cantilever',2.,SUPPORTED_SEEDS)
        coords=[[x,y,z-.1] for x,y,z in payload['placed_cm']]
        response=coupon_response(payload,coords)
        self.assertAlmostEqual(response['max_displacement_cm'],.1)
        self.assertEqual(response['status'],'OBSERVED_NOT_QUALIFIED')
        self.assertEqual(coupon_response(payload,[])['status'],'UNAVAILABLE_NONFINITE_OR_CHANGED_TOPOLOGY')


if __name__=='__main__': unittest.main()
