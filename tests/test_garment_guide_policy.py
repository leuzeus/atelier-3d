import copy
import ast
import json
import zipfile
from types import SimpleNamespace
from unittest.mock import patch

from a3d.core import ROOT,StudioError,atomic_json,digest,sha
from a3d.garment_guide_policy import (prepare_guide_policy,reconstruct_guide_policy,verify_guide_policy,
    prepare_project_guide_policy,verify_project_guides,CODE_SOURCES,guide_generator_identity)
from tests.test_core import Case
from tests.test_garment_guides import fixture as garment_fixture
from tests.test_shoulder_surface import fixture as shoulder_fixture


def fixture():
    data,semantics,profile=garment_fixture();_,geometry,_=shoulder_fixture()
    data['component_id']='garment.test';ref={'path':'source.garmentpkg','sha256':'a'*64}
    body_ref={'path':'body.json','sha256':'b'*64};geometry_ref={'path':'geometry.json','sha256':'c'*64}
    compiled={'version':1,'status':'READY_TO_PLAN','source_ref':{'path':'dossier.json','sha256':'d'*64},
        'specification_source_ref':{'path':'production.json','sha256':'e'*64},'assembly_spec':{'body_ref':body_ref},
        'components':[{'id':'garment.test','pipeline':'PATTERN_SEWN','package_source_ref':ref},
                      {'id':'prop.rigid','pipeline':'MULTIVIEW_PART','package_source_ref':ref}],
        'textiles':{pid:{'component_id':'garment.test','source_geometry':copy.deepcopy(piece),'semantics':semantics[pid]}
                    for pid,piece in data['pieces'].items()}}
    parameters={'garment.test':{'upper_blend':1.,'surface_sections':True,'skin_section_heights_cm':[]}}
    return compiled,profile,geometry,geometry_ref,{'garment.test':data},parameters


def coupled_fixture():
    c,p,g,ref,data,params=fixture();source=data['garment.test'];source['units']='cm'
    for pid,piece in source['pieces'].items():
        piece['faces']=[[0,1,2],[0,2,3]]
        c['textiles'][pid]['source_geometry']=copy.deepcopy(piece)
    source['seams']=[{'id':'front-to-collar','kind':'permanent','piece_a':'single-front',
        'edge_a':'attachment','piece_b':'collar','edge_b':'attachment','orientation':'reverse'}]
    recipe={'component_id':'garment.test','seams':{'front-to-collar':{'kind':'permanent',
        'ease_b_over_a':0.,'tolerance_relative':0.02}}}
    params['garment.test']['source_seam_coupling']={'pieces':['single-front','collar'],
        'subdivisions':2,'budgets':{'max_source_points':20000,'max_source_triangles':20000,
            'max_controls':70000,'max_triangles':131072,'max_seconds':60.},
        'recipe_ref':{'path':'recipe.json','sha256':'f'*64}}
    return c,p,g,ref,data,params,{'garment.test':recipe}


class GuidePolicy(Case):
    def test_generator_identity_covers_imported_coordinate_dependencies_including_upper_shoulders(self):
        # Include late imports in the upper_blend branch even when the current
        # source has only specialized panels and would produce the same points.
        coordinate_modules=('garment_guides','semantic_placement','torso_sections','guide_cage_sampling','source_seam_coupling','shoulder_guides',
            'preform_volume','anatomy_profile','shoulder_surface','head_surface','contact_geometry')
        dependencies=set()
        for module in coordinate_modules:
            tree=ast.parse((ROOT/('a3d/'+module+'.py')).read_text(encoding='utf-8'))
            for node in ast.walk(tree):
                if isinstance(node,ast.ImportFrom)and node.module:
                    if node.level==1:dependencies.add(node.module.split('.')[0])
                    elif node.module.startswith('a3d.'):dependencies.add(node.module.split('.')[1])
        self.assertIn('shoulder_guides',dependencies);self.assertLessEqual(dependencies,set(CODE_SOURCES))
        c,p,g,ref,data,params=fixture();policy=prepare_guide_policy(c,p,g,ref,params)
        guides,_=reconstruct_guide_policy(c,p,g,ref,data,policy);identity=guide_generator_identity()
        self.assertEqual(identity['shoulder_guides'],sha(ROOT/'a3d/shoulder_guides.py'))
        with patch('a3d.garment_guide_policy.sha',side_effect=lambda path:
                'f'*64 if path.name=='shoulder_guides.py'else sha(path)):
            with self.assertRaisesRegex(StudioError,'generator code is stale'):
                verify_guide_policy(c,p,g,ref,data,policy,guides)

    def test_cage_helper_code_change_invalidates_existing_guide_policy(self):
        c,p,g,ref,data,params=fixture();policy=prepare_guide_policy(c,p,g,ref,params)
        guides,_=reconstruct_guide_policy(c,p,g,ref,data,policy)
        self.assertEqual(policy['generator_code_sha256']['guide_cage_sampling'],sha(ROOT/'a3d/guide_cage_sampling.py'))
        with patch('a3d.garment_guide_policy.sha',side_effect=lambda path:
                'f'*64 if path.name=='guide_cage_sampling.py'else sha(path)):
            with self.assertRaisesRegex(StudioError,'generator code is stale'):
                verify_guide_policy(c,p,g,ref,data,policy,guides)

    def test_reconstruction_uses_existing_generator_and_exact_sources_without_granting_fit(self):
        c,p,g,ref,data,params=fixture();before=digest([c,p,g,ref,data,params])
        policy=prepare_guide_policy(c,p,g,ref,params)
        guides,evidence=reconstruct_guide_policy(c,p,g,ref,data,policy)
        self.assertEqual(set(guides),{'garment.test'})
        self.assertEqual(len(guides['garment.test']['panels']),5)
        verified=verify_guide_policy(c,p,g,ref,data,policy,guides)
        self.assertEqual(verified['comparison'],'FULL_UNROUNDED_GUIDE_REPORT_IDENTICAL')
        self.assertFalse(verified['admissible_for_fit']);self.assertEqual(verified['qualification'],'NONE')
        self.assertEqual(verified['acceptance'],'NOT_GRANTED');self.assertEqual(digest([c,p,g,ref,data,params]),before)
        self.assertEqual(reconstruct_guide_policy(c,p,g,ref,data,policy)[0],guides)

    def test_coordinate_policy_code_skin_body_source_or_inventory_changes_are_refused(self):
        c,p,g,ref,data,params=fixture();policy=prepare_guide_policy(c,p,g,ref,params)
        guides,_=reconstruct_guide_policy(c,p,g,ref,data,policy)
        for change in ('coordinate','report','code','missing-code','compiled','body-ref','geometry-ref','geometry','pose','package','material','inventory','unexpected-skin','override'):
            cc,pp,gg,rr,dd,pol,provided=copy.deepcopy([c,p,g,ref,data,policy,guides])
            if change=='coordinate':provided['garment.test']['panels']['collar']['arc_sections'][0]['curve_cm'][0][0]+=1e-12
            elif change=='report':provided['garment.test']['simulation']='COMPLETED'
            elif change=='code':pol['generator_code_sha256']['garment_guides']='f'*64
            elif change=='missing-code':pol['generator_code_sha256'].pop('torso_sections')
            elif change=='compiled':pol['compiled_sha256']='f'*64
            elif change=='body-ref':pol['body_ref']['sha256']='f'*64
            elif change=='geometry-ref':pol['geometry_ref']['sha256']='f'*64
            elif change=='geometry':gg['vertices_cm'][0][0]+=1.
            elif change=='pose':gg['pose_sha256']='f'*64
            elif change=='package':pol['components']['garment.test']['package_source_ref']['sha256']='f'*64
            elif change=='material':dd['garment.test']['pieces']['collar']['vertices'][0][0]-=1.
            elif change=='inventory':pol['components']['prop.rigid']=copy.deepcopy(pol['components']['garment.test'])
            elif change=='unexpected-skin':pol['components']['garment.test']['skin_sections_sha256']='f'*64
            else:pol['components']['garment.test']['manual_coordinates']=[[0.,0.,0.]]
            with self.subTest(change=change),self.assertRaises(StudioError):verify_guide_policy(cc,pp,gg,rr,dd,pol,provided)

    def test_measured_skin_is_recomputed_and_stale_evidence_or_missing_surface_declaration_refused(self):
        c,p,g,ref,data,params=fixture();data['garment.test']['pieces']={'single-front':data['garment.test']['pieces']['single-front']}
        c['textiles']={'single-front':c['textiles']['single-front']}
        p['sections']=[{'height_cm':50.,'seed_xy_cm':[0.,0.]}]
        params['garment.test']['skin_section_heights_cm']=[50.]
        policy=prepare_guide_policy(c,p,g,ref,params);guides,evidence=reconstruct_guide_policy(c,p,g,ref,data,policy)
        self.assertEqual(evidence['skin_sections']['garment.test']['qualification'],'OBSTACLE_GUIDE_CONTOURS_ONLY')
        self.assertFalse(evidence['skin_sections']['garment.test']['anatomical_girths_replaced'])
        for change in ('height','skin-hash','surface','missing-hash'):
            pol=copy.deepcopy(policy);row=pol['components']['garment.test']
            if change=='height':row['skin_section_heights_cm']=[51.]
            elif change=='skin-hash':row['skin_sections_sha256']='f'*64
            elif change=='surface':row['surface_sections']=False
            else:row.pop('skin_sections_sha256')
            with self.subTest(change=change),self.assertRaises(StudioError):verify_guide_policy(c,p,g,ref,data,pol,guides)

    def test_parameters_require_all_textile_owners_explicit_values_and_no_overrides(self):
        c,p,g,ref,data,params=fixture()
        for change in ('missing','unknown-owner','missing-value','out-of-range'):
            values=copy.deepcopy(params)
            if change=='missing':values={}
            elif change=='unknown-owner':values['prop.rigid']=values['garment.test']
            elif change=='missing-value':values['garment.test'].pop('surface_sections')
            else:values['garment.test']['upper_blend']=2.
            with self.subTest(change=change),self.assertRaises(StudioError):prepare_guide_policy(c,p,g,ref,values)
        params['garment.test'].update(surface_sections=False,skin_section_heights_cm=[50.])
        with patch('a3d.garment_guide_policy.measured_native_skin_sections')as measure:
            with self.assertRaisesRegex(StudioError,'explicitly enabled surfaces'):
                prepare_guide_policy(c,p,g,ref,params)
            measure.assert_not_called()

    def test_project_wrapper_binds_canonical_body_geometry_and_hashed_packages_read_only(self):
        c,p,g,ref,data,params=fixture()
        def stored(name,value):
            atomic_json(self.root/name,value);return {'path':name,'sha256':sha(self.root/name)}
        body_ref=stored('body.json',p);ref=stored('geometry.json',g);c['assembly_spec']['body_ref']=body_ref
        with zipfile.ZipFile(self.root/'source.garmentpkg','w')as archive:archive.writestr('garment.json',json.dumps(data['garment.test']))
        c['components'][0]['package_source_ref']={'path':'source.garmentpkg','sha256':sha(self.root/'source.garmentpkg')}
        project=SimpleNamespace(root=self.root)
        native={'operation':'prepare_body_target','files':[body_ref,ref],
            'result':{'profile_cache_key':p['cache_key'],'artifacts':{'profile':body_ref,'geometry':ref}}}
        with patch('a3d.production_dossier.compile_project_dossier',return_value=c),\
                patch('a3d.native_evidence.native_origin',return_value=(native,{'qualification':'SOURCE_BODY_ONLY'})):
            policy,origin=prepare_project_guide_policy(project,c,params)
            guides,_=reconstruct_guide_policy(c,p,g,ref,data,policy)
            stored('policy.json',policy);before={path.name:sha(path)for path in self.root.iterdir()}
            evidence=verify_project_guides(project,c,guides,'policy.json')
            self.assertEqual(evidence['policy_ref']['sha256'],sha(self.root/'policy.json'))
            self.assertEqual(evidence['native_body_origin'],origin['native_body_origin'])
            self.assertFalse(evidence['admissible_for_fit'])
            self.assertEqual(before,{path.name:sha(path)for path in self.root.iterdir()})
            from a3d.garment_guide_policy import verify_guide_policy as real_verify
            def replace_during_reconstruction(*args,**kwargs):
                result=real_verify(*args,**kwargs);stored('policy.json',{'corrupted':'different policy bytes'})
                return result
            with patch('a3d.garment_guide_policy.verify_guide_policy',side_effect=replace_during_reconstruction):
                with self.assertRaisesRegex(StudioError,'policy artifact changed'):
                    verify_project_guides(project,c,guides,'policy.json')
            stored('policy.json',policy)
            native['files'].remove(ref)
            with self.assertRaisesRegex(StudioError,'canonical completed native body'):verify_project_guides(project,c,guides,'policy.json')

    def test_declared_source_coupling_is_reproducible_and_does_not_admit_coverage_or_fitting(self):
        c,p,g,ref,data,params,recipes=coupled_fixture();before=digest([c,p,g,ref,data,params,recipes])
        policy=prepare_guide_policy(c,p,g,ref,params,source_seam_recipes=recipes)
        guides,evidence=reconstruct_guide_policy(c,p,g,ref,data,policy,source_seam_recipes=recipes)
        coupling=guides['garment.test']['source_seam_coupling']
        self.assertEqual(coupling['qualification'],'NONE');self.assertEqual(coupling['front_coverage'],'NOT_REVIEWED')
        self.assertEqual(coupling['contact_assessment'],'REQUIRED')
        self.assertEqual(coupling['relations'][0]['max_common_control_gap_cm'],0.)
        verified=verify_guide_policy(c,p,g,ref,data,policy,guides,source_seam_recipes=recipes)
        self.assertEqual(verified['comparison'],'FULL_UNROUNDED_GUIDE_REPORT_IDENTICAL')
        self.assertEqual(before,digest([c,p,g,ref,data,params,recipes]));self.assertFalse(evidence['admissible_for_fit'])

    def test_source_coupling_missing_changed_unrequested_recipe_and_panel_overrides_are_refused(self):
        c,p,g,ref,data,params,recipes=coupled_fixture()
        policy=prepare_guide_policy(c,p,g,ref,params,source_seam_recipes=recipes)
        for change in ('missing','changed','extra','hash','missing-hash','piece','unexpected-hash'):
            pol,rr=copy.deepcopy([policy,recipes])
            if change=='missing':rr={}
            elif change=='changed':rr['garment.test']['seams']['front-to-collar']['ease_b_over_a']=.1
            elif change=='extra':rr['unrequested']=rr['garment.test']
            elif change=='hash':pol['components']['garment.test']['source_seam_recipe_sha256']='a'*64
            elif change=='missing-hash':pol['components']['garment.test'].pop('source_seam_recipe_sha256')
            elif change=='piece':pol['components']['garment.test']['source_seam_coupling']['pieces']=['single-front','absent']
            else:
                pol['components']['garment.test'].pop('source_seam_coupling');rr={}
            with self.subTest(change=change),self.assertRaises(StudioError):
                reconstruct_guide_policy(c,p,g,ref,data,pol,source_seam_recipes=rr)

    def test_project_recipe_ref_checks_exact_file_bytes_before_and_after_reconstruction(self):
        c,p,g,ref,data,params,recipes=coupled_fixture();project=SimpleNamespace(root=self.root)
        atomic_json(self.root/'recipe.json',recipes['garment.test'])
        recipe_ref={'path':'recipe.json','sha256':sha(self.root/'recipe.json')}
        params['garment.test']['source_seam_coupling']['recipe_ref']=recipe_ref
        with patch('a3d.garment_guide_policy._project_inputs',return_value=(p,g,ref,data,{'native':True})):
            policy,_=prepare_project_guide_policy(project,c,params)
            guides,_=reconstruct_guide_policy(c,p,g,ref,data,policy,source_seam_recipes=recipes)
            atomic_json(self.root/'policy.json',policy)
            verify_project_guides(project,c,guides,'policy.json')
            original=(self.root/'recipe.json').read_bytes()
            (self.root/'recipe.json').write_bytes(original+b' ')
            with self.assertRaisesRegex(StudioError,'recipe artifact changed'):
                verify_project_guides(project,c,guides,'policy.json')
            (self.root/'recipe.json').write_bytes(original)
            from a3d.garment_guide_policy import verify_guide_policy as real_verify
            def replace_recipe(*args,**kwargs):
                result=real_verify(*args,**kwargs)
                (self.root/'recipe.json').write_bytes(original+b' ')
                return result
            with patch('a3d.garment_guide_policy.verify_guide_policy',side_effect=replace_recipe):
                with self.assertRaisesRegex(StudioError,'recipe artifact changed'):
                    verify_project_guides(project,c,guides,'policy.json')
