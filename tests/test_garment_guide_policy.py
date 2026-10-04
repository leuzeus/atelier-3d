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


class GuidePolicy(Case):
    def test_generator_identity_covers_imported_coordinate_dependencies_including_upper_shoulders(self):
        # Include late imports in the upper_blend branch even when the current
        # source has only specialized panels and would produce the same points.
        coordinate_modules=('garment_guides','semantic_placement','torso_sections','shoulder_guides',
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
            def replace_during_reconstruction(*args):
                result=real_verify(*args);stored('policy.json',{'corrupted':'different policy bytes'})
                return result
            with patch('a3d.garment_guide_policy.verify_guide_policy',side_effect=replace_during_reconstruction):
                with self.assertRaisesRegex(StudioError,'policy artifact changed'):
                    verify_project_guides(project,c,guides,'policy.json')
            stored('policy.json',policy)
            native['files'].remove(ref)
            with self.assertRaisesRegex(StudioError,'canonical completed native body'):verify_project_guides(project,c,guides,'policy.json')
