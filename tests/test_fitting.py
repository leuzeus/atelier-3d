import copy
import unittest
from a3d.core import StudioError, digest, contract, atomic_json, sha, ROOT
from a3d.fitting import section_loop, pattern_capacity, compare_fit, propose_adjustments, path_inside
from a3d.sewing import validate_recipe, fitting_tack_payload, active_sewing_pairs
from a3d.guard import admit_operation
from tests.test_core import Case
from tests.test_sewing import sources
from tests.support import ready_project


def fitting_sources():
    data,recipe=sources()
    data['seams']=[data['seams'][0],{'id':'opening','piece_a':'back','edge_a':'right','piece_b':'front','edge_b':'left','orientation':'forward','kind':'closure'}]
    recipe['seams']={s['id']:{'kind':s.get('kind','permanent'),'ease_b_over_a':0,'tolerance_relative':.005} for s in data['seams']}
    recipe['trial_pieces']=['front','back']
    anchor=lambda edge:{'edge':edge,'t':.5}
    row={'id':'chest','landmark_status':'validated','source_ref':'synthetic homologous chest markers','target_kind':'minimum_required','uncertainty_cm':.2,
        'body_section':{'height_cm':20,'seed_xy_cm':[0,0]},'envelope_section':{'height_cm':20,'seed_xy_cm':[0,0]},
        'pattern_path':[{'piece':p,'from':anchor('left'),'to':anchor('right')} for p in ('front','back')],
        'joins':['torso-right','opening'],'ease_cm':8,'envelope_clearance_girth_cm':1,
        'adjustment_sites':[{'piece':p,'edge':e,'share':.25,'max_capacity_increment_cm':2,'source_ref':'synthetic alteration site'} for p in ('front','back') for e in ('left','right')]}
    plan={'version':1,'component_id':'garment.coat','body':{'object':'BODY','geometry_sha256':'a'*64,'role':'target'},'measurements':[row]}
    return data,recipe,plan


class FittingTests(unittest.TestCase):
    def test_missing_landmarks_or_closed_path_never_grant_fit_or_patch(self):
        data,_,plan=fitting_sources();plan['measurements'][0]['landmark_status']='assumed'
        report=compare_fit(data,plan,{},{});self.assertEqual(report['fit_status'],'NOT_QUALIFIED')
        self.assertEqual(propose_adjustments(data,plan,report)['proposals'],[])
        row=plan['measurements'][0];row['joins'].pop()
        self.assertEqual(pattern_capacity(data,row)['status'],'NOT_QUALIFIED')

    def test_seam_line_capacity_ignores_cutting_allowance_and_counts_takeup(self):
        data,_,plan=fitting_sources();row=plan['measurements'][0]
        before=digest(data);self.assertEqual(pattern_capacity(data,row)['capacity_cm'],40)
        for piece in data['pieces'].values():piece['cut_allowance_cm']=50
        self.assertEqual(pattern_capacity(data,row)['capacity_cm'],40)
        row['takeup']=[{'amount_cm':2,'reason':'explicit overlap','source_ref':'synthetic fold marker'}]
        self.assertEqual(pattern_capacity(data,row)['capacity_cm'],38)
        self.assertNotEqual(digest(data),before)

    def test_measured_deficit_allocation_is_bounded_readonly_and_has_dependencies(self):
        data,_,plan=fitting_sources();before=(digest(data),digest(plan))
        body={'chest':{'status':'MEASURED','circumference_cm':36}}
        report=compare_fit(data,plan,body,body);self.assertEqual(report['fit_status'],'INCOMPATIBLE')
        proposal=propose_adjustments(data,plan,report)['proposals'][0]
        self.assertEqual(proposal['required_capacity_increment_cm'],4)
        self.assertTrue(all(s['capacity_increment_cm']==1 and s['dependent_seams'] for s in proposal['sites']))
        self.assertEqual(proposal['status'],'PROPOSED_NOT_APPLIED');self.assertEqual(before,(digest(data),digest(plan)))
        plan['measurements'][0]['adjustment_sites'][0]['max_capacity_increment_cm']=.5
        self.assertEqual(propose_adjustments(data,plan,report)['proposals'][0]['status'],'OUTSIDE_DECLARED_LIMITS')
        plan['measurements'][0]['target_kind']='style_only'
        self.assertEqual(compare_fit(data,plan,body,body)['fit_status'],'NOT_QUALIFIED')
        plan['body']['role']='proxy';self.assertEqual(compare_fit(data,plan,body,body)['fit_status'],'NOT_QUALIFIED')

    def test_wrong_homologous_join_or_detachable_path_refused(self):
        data,_,plan=fitting_sources();row=plan['measurements'][0];row['pattern_path'][1]['from']['t']=.4
        with self.assertRaisesRegex(StudioError,'orientation'):pattern_capacity(data,row)
        row['pattern_path'][1]['from']['t']=.5;data['seams'][1]['kind']='detachable'
        with self.assertRaisesRegex(StudioError,'Detachable'):pattern_capacity(data,row)

    def test_narrow_concave_cutout_cannot_be_skipped_by_sampling(self):
        polygon=[[0,0],[10,0],[10,10],[5.001,10],[5.001,4],[5,4],[5,10],[0,10]]
        self.assertFalse(path_inside([0,5],[10,5],polygon));self.assertTrue(path_inside([0,2],[10,2],polygon))

    def test_closed_torso_section_excludes_disconnected_arms_and_ambiguity(self):
        vertices=[];faces=[]
        for centre in (0,10,-10):
            off=len(vertices);vertices.extend([[centre+x,y,z] for z in (-1,1) for x,y in ((-1,-1),(1,-1),(1,1),(-1,1))])
            faces.extend([[off+i,off+(i+1)%4,off+(i+1)%4+4,off+i+4] for i in range(4)])
        result=section_loop(vertices,faces,{'height_cm':0,'seed_xy_cm':[0,0]})
        self.assertEqual(result['status'],'MEASURED');self.assertEqual(result['circumference_cm'],8);self.assertEqual(len(result['loops']),3)
        self.assertEqual(section_loop(vertices,faces,{'height_cm':0,'seed_xy_cm':[5,0]})['status'],'NOT_QUALIFIED')
        self.assertEqual(section_loop(vertices,faces[:-1],{'height_cm':0,'seed_xy_cm':[-10,0]})['status'],'NOT_QUALIFIED')

    def test_tacks_type_duration_force_and_trial_dependencies(self):
        data,recipe,_=fitting_sources();recipe['fitting_tacks']=[{'id':'baste','seam_id':'opening','phase':'mount','source_ref':'synthetic closure support','force_mode':'shared_native_sewing','sewing_force_per_kg':recipe['phases']['mount']['sewing_force_per_kg'],'frame_start':1,'frame_end':recipe['phases']['mount']['frames']}]
        validate_recipe(data,recipe)
        for key,value in (('seam_id','torso-right'),('frame_end',2),('sewing_force_per_kg',1)):
            bad=copy.deepcopy(recipe);bad['fitting_tacks'][0][key]=value
            with self.subTest(key=key),self.assertRaises(StudioError):validate_recipe(data,bad)
        payload={'seams':{'opening':{'kind':'closure','pairs':[[0,3]]},'s':{'kind':'permanent','pairs':[[1,2]]}}}
        before=digest(payload);local=fitting_tack_payload(payload,recipe,'mount')
        self.assertEqual(active_sewing_pairs(local),[[1,2],[0,3]]);self.assertEqual(local['seams']['opening']['kind'],'closure');self.assertEqual(digest(payload),before)


class FittingAdmissionTests(Case):
    def test_readonly_fitting_admission_and_plan_hash_changes(self):
        project=ready_project(self.root,True);_,recipe,plan=fitting_sources()
        atomic_json(project.root/'recipe.json',recipe);atomic_json(project.root/'fit.json',plan)
        args={'component_id':'garment.coat','recipe_path':'recipe.json','fit_path':'fit.json'};before=sha(project.db)
        for operation in ('inspect_garment_fit','propose_pattern_adjustment'):admit_operation(project,operation,args)
        self.assertEqual(sha(project.db),before)
        recipe['fitting_plan']={'path':'fit.json','sha256':sha(project.root/'fit.json')};atomic_json(project.root/'recipe.json',recipe)
        plan['measurements'][0]['ease_cm']=10;atomic_json(project.root/'fit.json',plan)
        with self.assertRaisesRegex(StudioError,'fitting plan changed'):admit_operation(project,'inspect_garment_fit',args)

    def test_tacked_trial_cannot_admit_full_or_freeze(self):
        project=ready_project(self.root,True);_,recipe,_=fitting_sources();recipe['fitting_tacks']=[{'id':'baste','seam_id':'opening','phase':'mount','source_ref':'test','force_mode':'shared_native_sewing','sewing_force_per_kg':20000,'frame_start':1,'frame_end':recipe['phases']['mount']['frames']}]
        atomic_json(project.root/'recipe.json',recipe)
        for operation,args in [('simulate_sewn',{'phase':'mount','scope':'full'}),('freeze_sewn',{})]:
            with self.subTest(operation=operation),self.assertRaisesRegex(StudioError,'construction trial only'):
                admit_operation(project,operation,{'component_id':'garment.coat','recipe_path':'recipe.json',**args})
