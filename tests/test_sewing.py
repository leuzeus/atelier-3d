import copy
import math
import unittest
from a3d.core import ROOT, StudioError, read_json, atomic_json, digest
from a3d.guard import admit_operation
from a3d.sewing import (prepare_boundaries, resample_parameters, mesh_quality,
    mass_settings, seam_report, validate_recipe, weld_permanent)
from tests.test_core import Case
from tests.support import ready_project


def sources():
    return (read_json(ROOT/'tests/fixtures/garment-coat/package/garment.json'),
        read_json(ROOT/'templates/sewing-recipe.json'))


class BoundaryTests(unittest.TestCase):
    def test_mirror_u_preserves_source_boundaries_and_changes_recipe_identity(self):
        from blender.sewing import mesh_recipe_digest
        data,recipe=sources();original=digest(data)
        recipe['placements']['front']['mode']='cylinder'
        before=prepare_boundaries(data,recipe);before_hash=mesh_recipe_digest(recipe)
        recipe['placements']['front']['mirror_u']=True
        self.assertEqual(prepare_boundaries(data,recipe),before)
        self.assertEqual(digest(data),original)
        self.assertNotEqual(mesh_recipe_digest(recipe),before_hash)

    def test_mirror_u_must_be_boolean_and_cylindrical(self):
        data,recipe=sources()
        recipe['placements']['front']['mirror_u']=True
        with self.assertRaisesRegex(StudioError,'cylindrical'):validate_recipe(data,recipe)
        recipe['placements']['front']['mode']='cylinder'
        recipe['placements']['front']['mirror_u']='true'
        with self.assertRaises(StudioError):validate_recipe(data,recipe)

    def test_dense_collinear_contours_are_not_simulation_resolution(self):
        points=[[0,i/100] for i in range(4001)]
        values=resample_parameters([points],2,.02)
        self.assertEqual(len(values),21)
        self.assertEqual(points[0],[0,0]);self.assertEqual(points[-1],[0,40])

    def test_curve_error_inserts_shared_parameters_on_both_sides(self):
        a=[[0,0],[1,2],[2,0]];b=[[0,0],[1,0],[2,0]]
        t=resample_parameters([a,b],10,.01)
        self.assertIn(.5,t)
        self.assertEqual(t,[0.,.5,1.])

    def test_boundaries_preserve_source_and_exact_named_seam_mapping(self):
        data,recipe=sources();before=digest(data)
        boundaries,seams,_=prepare_boundaries(data,recipe)
        self.assertEqual(digest(data),before)
        for sid,seam in seams.items():
            self.assertEqual(len(seam['a']),len(seam['b']))
            original=next(s for s in data['seams'] if s['id']==sid)
            edge=data['pieces'][seam['piece_b']]['edges'][original['edge_b']]
            target=edge[-1] if original['orientation']=='reverse' else edge[0]
            self.assertEqual(boundaries[seam['piece_b']]['polygon'][seam['b'][0]],data['pieces'][seam['piece_b']]['vertices'][target])
        self.assertGreater(len(boundaries['front']['polygon']),4)

    def test_declared_ease_is_checked_per_seam(self):
        data,recipe=sources()
        for p in data['pieces']['sleeve-left']['vertices']:p[1]*=1.04
        with self.assertRaisesRegex(StudioError,'ease'):seam_report(data,recipe)
        recipe['seams']['sleeve-left']['ease_b_over_a']=.04
        reports,_=seam_report(data,recipe)
        self.assertLess(next(r for r in reports if r['id']=='sleeve-left')['residual'],1e-10)

    def test_different_source_counts_share_simulation_samples(self):
        data,recipe=sources()
        p=data['pieces']['front']
        # Insert one collinear point into right edge and update only its indices.
        p['vertices'].insert(2,[20,20])
        p['edges']={'right':[1,2,3],'left':[0,4],'top':[4,3]}
        boundaries,seams,_=prepare_boundaries(data,recipe)
        for s in seams.values():self.assertEqual(len(s['a']),len(s['b']))
        self.assertEqual(data['pieces']['front']['vertices'][2],[20,20])

    def test_single_panel_self_seam_keeps_two_distinct_edges(self):
        data,recipe=sources()
        data['seams']=[{'id':'self','piece_a':'front','edge_a':'left',
            'piece_b':'front','edge_b':'right','orientation':'forward'},data['seams'][2]]
        recipe['seams']={s['id']:{'kind':'permanent','ease_b_over_a':0,'tolerance_relative':.005} for s in data['seams']}
        recipe['trial_pieces']=['back','sleeve-right']
        _,seams,_=prepare_boundaries(data,recipe)
        self.assertFalse(set(seams['self']['a']) & set(seams['self']['b']))

    def test_seam_chain_cannot_jump_through_panel(self):
        data,recipe=sources();data['pieces']['front']['edges']['right']=[0,2]
        with self.assertRaisesRegex(StudioError,'contiguous'):seam_report(data,recipe)

    def test_untyped_or_changed_declared_seam_is_rejected(self):
        data,recipe=sources();recipe['seams'].pop('torso-right')
        with self.assertRaisesRegex(StudioError,'type every'):validate_recipe(data,recipe)
        data,recipe=sources();data['seams'][0]['kind']='closure'
        with self.assertRaisesRegex(StudioError,'cannot change'):validate_recipe(data,recipe)

    def test_local_trial_and_collision_absence_are_explicit(self):
        data,recipe=sources();recipe['trial_pieces']=['front','sleeve-right']
        with self.assertRaisesRegex(StudioError,'permanent seam'):validate_recipe(data,recipe)
        data,recipe=sources();recipe['no_collision_reason']=''
        with self.assertRaisesRegex(StudioError,'Missing mannequin'):validate_recipe(data,recipe)


class PhysicsTests(unittest.TestCase):
    def test_contact_recovery_and_reference_mode_remain_bounded(self):
        from a3d.core import contract
        data,recipe=sources()
        recipe['contact_recovery']={'source_ref':'test:contact','clearance_cm':.1,
            'max_displacement_cm':.5,'max_passes':2}
        validate_recipe(data,recipe)
        recipe['contact_recovery']['max_displacement_cm']=recipe['limits']['max_displacement_cm']+1
        with self.assertRaisesRegex(StudioError,'existing displacement budget'):validate_recipe(data,recipe)
        recipe.pop('contact_recovery')
        recipe['experimental_prefit']={'experimental':True,'source_ref':'test:fixed-reference',
            'seam_ids':['torso-right'],'reference_pieces':['front'],'fixed_edges':[],
            'iterations':5,'clearance_cm':0,'max_displacement_cm':1,'min_fraction':.125,
            'max_backtracks':3,'preserve_reference_positions':True}
        validate_recipe(data,recipe)
        recipe['experimental_prefit']['preserve_reference_positions']='true'
        with self.assertRaises(StudioError):contract('sewing-recipe',recipe)

    def test_experimental_prefit_is_opt_in_bound_and_permanent_only(self):
        from blender.sewing import mesh_recipe_digest
        data,recipe=sources();baseline=mesh_recipe_digest(recipe)
        options={'experimental':True,'source_ref':'test:bounded-placement','seam_ids':['torso-right'],
            'reference_pieces':['front'],'fixed_edges':[],'iterations':5,'clearance_cm':0,
            'max_displacement_cm':1,'min_fraction':.125,'max_backtracks':3}
        recipe['experimental_prefit']=options
        validate_recipe(data,recipe)
        self.assertNotEqual(mesh_recipe_digest(recipe),baseline)
        options['max_displacement_cm']=recipe['limits']['max_displacement_cm']+1
        with self.assertRaisesRegex(StudioError,'budget'):validate_recipe(data,recipe)
        options['max_displacement_cm']=1;recipe['seams']['torso-right']['kind']='closure'
        with self.assertRaisesRegex(StudioError,'permanent'):validate_recipe(data,recipe)
        recipe['seams']['torso-right']['kind']='permanent';options['reference_pieces']=['sleeve-left']
        with self.assertRaisesRegex(StudioError,'reference'):validate_recipe(data,recipe)
        options['reference_pieces']=['front'];options['fixed_edges']=[{'piece':'front','edge':'missing','exclude_joined_vertices':True}]
        with self.assertRaisesRegex(StudioError,'fixed edge'):validate_recipe(data,recipe)

    def test_area_mass_is_constant_across_resolution(self):
        coarse=mass_settings({'basis':'areal_density_kg_m2','value':.4},20000,1000,20000)
        fine=mass_settings({'basis':'areal_density_kg_m2','value':.4},20000,4000,20000)
        self.assertAlmostEqual(coarse['total_mass_kg'],.8)
        self.assertAlmostEqual(coarse['mass_per_vertex_kg'],4*fine['mass_per_vertex_kg'])
        self.assertAlmostEqual(coarse['sewing_force_max'],4*fine['sewing_force_max'])

    def test_explicit_total_mass_is_not_assigned_to_each_vertex(self):
        p=mass_settings({'basis':'total_kg','value':.3},10000,3000,20000)
        self.assertAlmostEqual(p['mass_per_vertex_kg'],.0001)
        self.assertAlmostEqual(p['sewing_force_max'],2)

    def test_regular_rest_does_not_certify_distorted_placement(self):
        _,r=sources();points=[[0,0,0],[1,0,0],[0,1,0]]
        for placed in ([[0,0,0],[0,0,0],[0,1,0]],[[0,0,0],[41.6,0,0],[0,1,0]]):
            with self.subTest(placed=placed),self.assertRaises(StudioError):mesh_quality(points,placed,[[0,1,2]],r['mesh'])

    def test_sliver_and_nonfinite_faces_are_refused(self):
        _,r=sources()
        for pts in ([[0,0,0],[1,0,0],[2,.0001,0]],[[0,0,0],[1,0,0],[0,math.nan,0]]):
            with self.subTest(points=pts),self.assertRaises(StudioError):mesh_quality(pts,pts,[[0,1,2]],r['mesh'])

    def test_quality_refusal_retains_all_measurable_violations(self):
        _,r=sources();rest=[[0,0,0],[1,0,0],[0,1,0]]
        placed=[[0,0,0],[4,0,0],[2,.01,0]]
        with self.assertRaises(StudioError) as raised:mesh_quality(rest,placed,[[0,1,2]],r['mesh'])
        error=raised.exception
        self.assertIn('degenerate_or_sliver',error.quality_violations)
        self.assertIn('stretch',error.quality_violations)
        self.assertLess(error.quality_metrics['min_angle_degrees'],r['mesh']['min_angle_degrees'])
        self.assertGreater(error.quality_metrics['max_stretch'],r['mesh']['max_stretch'])

    def test_refinement_cannot_lower_the_angle_gate_or_exceed_contract_budgets(self):
        data,recipe=sources()
        recipe['mesh']['quality_refinement']={'target_min_angle_degrees':3,'max_passes':16,'max_added_vertices':2000}
        validate_recipe(data,recipe)
        recipe['mesh']['min_angle_degrees']=4
        with self.assertRaisesRegex(StudioError,'exceed'):validate_recipe(data,recipe)
        recipe['mesh']['min_angle_degrees']=2;recipe['mesh']['quality_refinement']['max_passes']=100
        with self.assertRaises(StudioError):validate_recipe(data,recipe)


class FreezeTests(unittest.TestCase):
    def test_only_explicit_permanent_pairs_weld_even_when_others_coincide(self):
        vertices=[[0,0,0],[1,0,0],[0,1,0],[0,0,0],[-1,0,0],[0,1,0],
            [3,0,0],[4,0,0],[3,1,0],[3,0,0],[4,0,0],[3,1,0]]
        faces=[[0,1,2],[3,5,4],[6,7,8],[9,10,11]]
        seams={'fixed':{'kind':'permanent','pairs':[[0,3],[2,5]]},
            'opening':{'kind':'closure','pairs':[[6,9]]},'removable':{'kind':'detachable','pairs':[[7,10]]}}
        coords,fs,mapping,count=weld_permanent(vertices,faces,seams,.001)
        self.assertEqual(count,2);self.assertEqual(mapping[0],mapping[3])
        self.assertNotEqual(mapping[6],mapping[9]);self.assertNotEqual(mapping[7],mapping[10])
        self.assertEqual(len(coords),10)

    def test_large_gap_is_not_forced_closed(self):
        with self.assertRaisesRegex(StudioError,'not settled'):
            weld_permanent([[0,0,0],[1,0,0],[0,1,0],[2,0,0]],[[0,1,2]],{'s':{'kind':'permanent','pairs':[[0,3]]}},.01)

    def test_welding_cannot_collapse_a_face(self):
        with self.assertRaisesRegex(StudioError,'collapse'):
            weld_permanent([[0,0,0],[.001,0,0],[0,1,0]],[[0,1,2]],{'s':{'kind':'permanent','pairs':[[0,1]]}},.01)

    def test_welding_cannot_flatten_three_distinct_indices(self):
        with self.assertRaisesRegex(StudioError,'zero-area'):
            weld_permanent([[0,0,0],[1,0,0],[0,.001,0],[0,-.001,0]],[[0,1,2]],
                {'s':{'kind':'permanent','pairs':[[2,3]]}},.01)


class SewingAdmissionTests(Case):
    def test_free_assembly_is_explicit_and_does_not_allow_colliders(self):
        p=ready_project(self.root,True);_,r=sources();atomic_json(p.root/'recipe.json',r)
        before=p.state()
        args={'component_id':'garment.coat','recipe_path':'recipe.json','phase':'mount','scope':'full','purpose':'assembly'}
        admit_operation(p,'simulate_sewn',args)
        admit_operation(p,'prepare_sewn_stage',{'component_id':'garment.coat','recipe_path':'recipe.json','stage':'assembly'})
        r['no_collision_reason']='';atomic_json(p.root/'recipe.json',r)
        with self.assertRaisesRegex(StudioError,'explicit collider-free'):admit_operation(p,'simulate_sewn',args)
        r['no_collision_reason']='test';r['colliders']=[{'object':'body','role':'mannequin',
            'geometry_sha256':'0'*64,'dimensions_cm':[20,20,180],'tolerance_cm':.1,
            'outer_thickness_cm':.1,'inner_thickness_cm':.1}]
        atomic_json(p.root/'recipe.json',r)
        with self.assertRaisesRegex(StudioError,'explicit collider-free'):admit_operation(p,'simulate_sewn',args)
        self.assertEqual(p.state(),before)

    def test_new_stages_cannot_bypass_board_or_unknown_purpose(self):
        p=ready_project(self.root,True,False);_,r=sources();atomic_json(p.root/'recipe.json',r)
        with self.assertRaisesRegex(StudioError,'construction'):
            admit_operation(p,'prepare_sewn_stage',{'component_id':'garment.coat','recipe_path':'recipe.json','stage':'assembly'})
        with self.assertRaisesRegex(StudioError,'purpose'):
            admit_operation(p,'simulate_sewn',{'component_id':'garment.coat','recipe_path':'recipe.json',
                'phase':'mount','scope':'local','purpose':'unknown'})

    def test_rebuild_cannot_replace_accepted_component(self):
        from a3d.packages import extract_package
        p=ready_project(self.root,True);_,r=sources();atomic_json(p.root/'recipe.json',r)
        state=p.state();component=state['components']['garment.coat']
        extract_package(p.root/component['package']['path'],p.root/'extracted')
        with p.transaction() as db:
            state=p.state(db);state['components']['garment.coat']['stage']='RECONSTRUCTED'
            p.save(db,state,'synthetic_acceptance',{})
        with self.assertRaisesRegex(StudioError,'immutable'):
            admit_operation(p,'garment',{'package_dir':'extracted','recipe_path':'recipe.json','rebuild':True})

    def test_technical_recipe_keeps_existing_human_board_decision(self):
        p=ready_project(self.root,True);_,r=sources()
        path='recipe.json';atomic_json(p.root/path,r);state=p.state()
        args={'component_id':'garment.coat','recipe_path':path,'phase':'mount','scope':'local'}
        admit_operation(p,'simulate_sewn',args)
        r['phases']['mount']['quality']=12;atomic_json(p.root/path,r)
        admit_operation(p,'simulate_sewn',args)
        self.assertEqual(p.state(),state)

    def test_native_operations_do_not_bypass_board(self):
        p=ready_project(self.root,True,False);_,r=sources();atomic_json(p.root/'recipe.json',r)
        with self.assertRaisesRegex(StudioError,'construction'):
            admit_operation(p,'simulate_sewn',{'component_id':'garment.coat','recipe_path':'recipe.json','phase':'mount','scope':'full'})

    def test_unknown_scope_does_not_run(self):
        p=ready_project(self.root,True);_,r=sources();atomic_json(p.root/'recipe.json',r)
        with self.assertRaisesRegex(StudioError,'scope'):
            admit_operation(p,'simulate_sewn',{'component_id':'garment.coat','recipe_path':'recipe.json','phase':'mount','scope':'unbounded'})

    def test_old_simulation_plan_is_not_a_physical_admission(self):
        from a3d.lifecycle import simulation_plan
        p=ready_project(self.root,True)
        atomic_json(p.root/'old.json',{'component_id':'garment.coat','type':'cloth','frame_start':1,'frame_end':24,
            'quality':5,'collision_components':[],'baked':False,'max_frames':24})
        with self.assertRaisesRegex(StudioError,'Legacy simulation'):
            simulation_plan(p,p.state(),'old.json',['garment.coat'])
