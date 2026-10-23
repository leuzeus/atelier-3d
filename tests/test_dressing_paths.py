import copy
import json
import unittest
import zipfile
from unittest.mock import patch

from a3d.core import StudioError,atomic_json,digest,sha
from a3d.dressing_derivation import derive_dressing_contract,dressing_derivation_descriptor
from a3d.dressing_paths import generate_dressing_paths,dressing_paths_descriptor
from tests.test_core import Case
from tests.support import ready_project
from tests.test_dressing_derivation import fixture,hood_yoke_fixture


class DressingPaths(unittest.TestCase):
    def test_controls_reuse_original_uv_edges_and_measured_sections_without_entry_translation(self):
        source=derive_dressing_contract(*fixture());before=digest(source)
        result=generate_dressing_paths(source)
        self.assertEqual(digest(source),before);self.assertEqual(result,generate_dressing_paths(source))
        self.assertEqual(result['status'],'NEEDS_DATA');self.assertFalse(result['executable'])
        self.assertEqual(result['simulation'],'NOT_EXECUTED');self.assertFalse(result['accepted'])
        self.assertEqual(len(result['controls']),3)
        for control in result['controls']:
            self.assertIsNone(control['trajectory']);self.assertEqual(control['entry_configuration'],'MISSING')
            for rim in control['source_rims']:
                self.assertGreaterEqual(len(rim['samples']),4)
                for sample in rim['samples']:
                    self.assertAlmostEqual(sum(sample['source_weights']),1.)
                    self.assertEqual(sample['guide_point_cm'],[*sample['uv_cm'],50.])
        wrap=next(row for row in result['controls'] if row['method']=='OPEN_WRAP')
        self.assertEqual({row['edge'] for row in wrap['source_rims']},{'left','right'})

    def test_point_budget_refuses_entire_mapping_before_allocation(self):
        source=derive_dressing_contract(*fixture())
        with patch('a3d.dressing_paths._sample_edge') as sampler:
            result=generate_dressing_paths(source,2)
        sampler.assert_not_called();self.assertEqual(result['status'],'INCOMPLETE');self.assertEqual(result['controls'],[])
        self.assertEqual(result['diagnostics'][-1]['category'],'BUDGET_INCOMPLETE')
        for limit in (True,1,501):
            with self.assertRaises(StudioError):generate_dressing_paths(source,limit)

    def test_declared_arc_deficit_is_impossible_and_never_clamped_or_resized(self):
        values=list(fixture())
        for container in (values[5]['source.belt']['panels'],values[6]['components']['source.belt']['plan_fields']['preform']['panels']):
            container['belt']['arc_sections'][0]['curve_cm'][-1][0]=5.
        source=derive_dressing_contract(*values);result=generate_dressing_paths(source)
        diagnostic=next(row for row in result['diagnostics'] if row['reason']=='SOURCE_RIM_OUTSIDE_DECLARED_GUIDE')
        self.assertEqual(diagnostic['category'],'IMPOSSIBLE_SOURCE_GEOMETRY')
        self.assertFalse(result['executable']);self.assertFalse(result['accepted'])

    def test_unsupported_guide_and_changed_derivation_do_not_fake_paths(self):
        source=derive_dressing_contract(*fixture());bad=copy.deepcopy(source);bad['methods'][0]['clearance_cm']+=1.
        with self.assertRaisesRegex(StudioError,'exact source derivation'):generate_dressing_paths(bad)
        values=list(fixture())
        for container in (values[5]['source.belt']['panels'],values[6]['components']['source.belt']['plan_fields']['preform']['panels']):
            container['belt'].pop('arc_sections')
        result=generate_dressing_paths(derive_dressing_contract(*values))
        self.assertIn('SOURCE_GUIDE_PARAMETERIZATION_UNSUPPORTED',{row['reason'] for row in result['diagnostics']})


    def test_hood_control_rims_and_permanent_neck_anchors_are_distinct_source_geometry(self):
        source=derive_dressing_contract(*hood_yoke_fixture(True));before=digest(source);result=generate_dressing_paths(source)
        self.assertEqual(digest(source),before);hood=next(row for row in result['controls'] if row['method']=='OPEN_HOOD_YOKE')
        self.assertEqual({(row['piece'],row['edge']) for row in hood['source_rims']},{
            ('hood-left','face-free'),('hood-right','face-free'),('yoke-upper','front-left'),('yoke-upper','front-right')})
        self.assertEqual({(row['piece'],row['edge'],row['source_link_id']) for row in hood['source_anchor_rims']},{
            ('hood-left','neck-base','neck-left'),('hood-right','neck-base','neck-right')})
        self.assertEqual(hood['configuration']['mode'],'RAISED_OPEN_HOOD');self.assertIsNone(hood['trajectory'])
        self.assertFalse(hood['executable']);self.assertEqual(hood['passage'],'NOT_QUALIFIED')
        for rim in hood['source_anchor_rims']:
            for point in rim['samples']:
                self.assertEqual(point['guide_point_cm'],[*point['uv_cm'],80.])
        expected=sum(len(row['body_axis_controls'])+sum(len(rim['samples']) for rim in row['source_rims']+row['source_anchor_rims'])
                     for row in result['controls'])
        self.assertEqual(result['point_budget']['required_points'],expected)


class DressingPathsDescriptor(Case):
    def test_mode_declaration_must_match_its_exact_source_document_after_resigning_policy(self):
        project=ready_project(self.root);values=hood_yoke_fixture(True)
        compiled,sources,profile,geometry,triangles,guides,templates,policy=values
        def save(name,value):
            atomic_json(self.root/name,value);return {'path':name,'sha256':sha(self.root/name)}
        packages=[]
        for cid,source in sources.items():
            name=cid+'.garmentpkg'
            with zipfile.ZipFile(self.root/name,'w') as archive:archive.writestr('garment.json',json.dumps(source['data']))
            source['source_ref']={'path':name,'sha256':sha(self.root/name)}
            templates['components'][cid]['source_ref']=copy.deepcopy(source['source_ref'])
            packages.append({'component_id':cid,'source_ref':copy.deepcopy(source['source_ref'])})
        assembly={'PORTABLE_RECONSTRUCTION_FIXTURE_ONLY':True}
        inputs={'dossier_ref':save('dossier.json',{}),'production_spec_ref':save('production.json',{'packages':packages}),
                'assembly_plan_ref':save('assembly.json',assembly),'guides_ref':save('guides.json',guides),
                'standard_recipe_ref':save('recipe.json',{})}
        templates['compiler_inputs']=inputs;templates['body_ref']=save('body-profile.json',profile)
        policy['bindings']={'templates_ref':save('templates.json',templates),'body_geometry_ref':save('geometry.json',geometry),
                            'body_triangles_ref':save('triangles.json',triangles)}
        for configuration in policy['method_configurations']:
            document={key:value for key,value in configuration.items() if key!='source_ref'}
            configuration['source_ref']=save(configuration['source_ref']['path'],document)
        save('derivation-policy.json',policy);before=sha(project.db)
        with patch('a3d.production_dossier.compile_project_dossier',return_value=compiled),\
                patch('a3d.garment_planner.plan_assembly',return_value=assembly),\
                patch('a3d.textile_executor.prepare_component_templates',return_value=templates):
            descriptor=dressing_derivation_descriptor(project,'derivation-policy.json')
            method=next(row for row in descriptor['derivation']['methods'] if row['method']=='OPEN_HOOD_YOKE')
            self.assertEqual(method['configuration']['mode'],'RAISED_OPEN_HOOD')
            self.assertIn(policy['method_configurations'][0]['source_ref'],descriptor['evidence'])
            changed={key:value for key,value in policy['method_configurations'][0].items() if key!='source_ref'}
            changed['mode']='LOWERED_OPEN_HOOD'
            policy['method_configurations'][0]['source_ref']=save('hood-configuration.json',changed)
            save('derivation-policy.json',policy)
            with self.assertRaisesRegex(StudioError,'exact source decision document'):
                dressing_derivation_descriptor(project,'derivation-policy.json')
        self.assertEqual(sha(project.db),before)

    def test_wrapper_reconstructs_source_derivation_instead_of_trusting_resigned_result(self):
        project=ready_project(self.root);source=derive_dressing_contract(*fixture())
        atomic_json(self.root/'derive-spec.json',fixture()[-1]);atomic_json(self.root/'derived.json',source)
        request={'version':1,'bindings':{key:{'path':name,'sha256':sha(self.root/name)}
                 for key,name in [('derivation_spec_ref','derive-spec.json'),('derivation_ref','derived.json')]},'max_path_points':500}
        atomic_json(self.root/'request.json',request)
        reconstructed={'derivation':source,'evidence':[]}
        with patch('a3d.dressing_paths.dressing_derivation_descriptor',return_value=reconstructed):
            self.assertEqual(dressing_paths_descriptor(project,'request.json')['paths']['status'],'NEEDS_DATA')
        changed=copy.deepcopy(source);changed['methods'][0]['clearance_cm']+=1.
        changed.pop('derivation_sha256');changed['derivation_sha256']=digest(changed)
        atomic_json(self.root/'derived.json',changed);request['bindings']['derivation_ref']['sha256']=sha(self.root/'derived.json')
        atomic_json(self.root/'request.json',request)
        with patch('a3d.dressing_paths.dressing_derivation_descriptor',return_value=reconstructed),self.assertRaisesRegex(StudioError,'reconstruction'):
            dressing_paths_descriptor(project,'request.json')
