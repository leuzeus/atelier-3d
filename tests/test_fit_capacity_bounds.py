"""Nominal source path bounds, never a physical garment acceptance fixture."""
import copy
import json
import math
import tempfile
import unittest
from pathlib import Path
from types import SimpleNamespace
from unittest.mock import patch

from a3d.core import StudioError,digest,sha
from a3d.fit_capacity_bounds import _middle_upper_arm_section,compare_body_section,project_capacity_bounds,transverse_capacity_bound


def fixture():
    ref={'path':'synthetic.garmentpkg','sha256':'a'*64}
    piece={'vertices':[[2.,0.],[27.,0.],[29.,20.],[0.,20.]],
           'faces':[[0,1,2],[0,2,3]],'edges':{'underarm-front':[3,0],'underarm-back':[1,2]}}
    seam={'id':'source::underarm','component_id':'source','piece_a':'cuff','piece_b':'cuff',
          'edge_a':'underarm-front','edge_b':'underarm-back','kind':'permanent','orientation':'reverse','source_ref':ref}
    return {'textiles':{'cuff':{'component_id':'source','semantics':{'role':'cuff','side':'left','layer':'outer'},
                              'package_source_ref':ref,'source_geometry':piece}},'links':[seam]}


def region_descriptor():
    curve=[[-5.,-5.,0.],[5.,-5.,0.],[5.,5.,0.],[-5.,5.,0.]]
    regions=[]
    for side in ('left','right'):
        sections=[{'id':side+'-measurement-'+str(index),'parameter':parameter,'ok':True,'status':'MEASURED',
                   'curve_cm':copy.deepcopy(curve),'girth_cm':40.}
                  for index,parameter in enumerate((0.,.25,.5,.75,1.))]
        regions.append({'id':'source-domain-'+side,'side':side,'domain':'SHOULDER_TO_ELBOW_ONLY','sections':sections})
    return {'supplement':{'regions':regions},'sections':{s['id']:{'region':r,'section':s} for r in regions for s in r['sections']},
            'identity':{'fixture':'exact-native-origin-not-exercised'},'specification_ref':{'path':'policy.json','sha256':'b'*64},
            'supplement_ref':{'path':'supplement.json','sha256':'c'*64},'native_body_origin':{'fixture':True}}


def reindex(descriptor):
    descriptor['sections']={s['id']:{'region':r,'section':s} for r in descriptor['supplement']['regions'] for s in r['sections']}


class FitCapacityBounds(unittest.TestCase):
    def test_exact_trapezoid_family_without_cut_allowance_or_bounding_box(self):
        compiled=fixture();before=digest(compiled);result=transverse_capacity_bound(compiled,'cuff')
        self.assertEqual(result['minimum_capacity_cm'],25.);self.assertEqual(result['maximum_capacity_cm'],29.)
        self.assertEqual(result['minimum']['fraction_a'],1.);self.assertEqual(result['maximum']['fraction_a'],0.)
        self.assertEqual(result['assumed_material_strain'],0.)
        self.assertFalse(result['bounding_box_used']);self.assertFalse(result['layers_summed'])
        self.assertEqual(result['acceptance'],'NOT_GRANTED');self.assertEqual(result['fitting'],'NOT_EXECUTED')
        self.assertEqual(before,digest(compiled));self.assertEqual(json.loads(json.dumps(result)),result)
        compiled['textiles']['cuff']['source_geometry']['cut_allowance_cm']=50.
        self.assertEqual(transverse_capacity_bound(compiled,'cuff')['maximum_capacity_cm'],29.)

    def test_rotated_metric_source_bounds_do_not_depend_on_u_width(self):
        compiled=fixture();a=.57
        piece=compiled['textiles']['cuff']['source_geometry']
        piece['vertices']=[[13.+math.cos(a)*x-math.sin(a)*y,-8.+math.sin(a)*x+math.cos(a)*y] for x,y in piece['vertices']]
        result=transverse_capacity_bound(compiled,'cuff')
        self.assertAlmostEqual(result['minimum_capacity_cm'],25.,places=8)
        self.assertAlmostEqual(result['maximum_capacity_cm'],29.,places=8)

    def test_renamed_segmented_and_reindexed_source_contour_uses_declared_seam(self):
        compiled=fixture();piece=compiled['textiles']['cuff']['source_geometry'];seam=compiled['links'][0]
        piece.update(vertices=[[2.,0.],[27.,0.],[28.,10.],[29.,20.],[0.,20.],[1.,10.]],
                     faces=[[0,1,2],[0,2,3],[0,3,4],[0,4,5]],edges={'join-alpha':[4,5,0],'join-omega':[1,2,3]})
        seam.update(edge_a='join-alpha',edge_b='join-omega')
        # Change the outline's starting index as well as its planar frame.
        n=len(piece['vertices']);offset=2;angle=.57
        piece['vertices']=piece['vertices'][offset:]+piece['vertices'][:offset]
        piece['faces']=[[(i-offset)%n for i in face] for face in piece['faces']]
        piece['edges']={name:[(i-offset)%n for i in ids] for name,ids in piece['edges'].items()}
        piece['vertices']=[[13.+math.cos(angle)*x-math.sin(angle)*y,-8.+math.sin(angle)*x+math.cos(angle)*y] for x,y in piece['vertices']]
        before=digest(compiled);result=transverse_capacity_bound(compiled,'cuff')
        self.assertAlmostEqual(result['minimum_capacity_cm'],25.,places=8)
        self.assertAlmostEqual(result['maximum_capacity_cm'],29.,places=8)
        self.assertGreater(len(result['cells']),1)
        self.assertEqual(result['source_seam'],seam);self.assertEqual(before,digest(compiled))
        self.assertTrue(all(c['inside_material']['proof']=='BOUNDARY_VERTEX_CONTACT_PARTITION_AND_EVERY_OPEN_INTERVAL' for c in result['cells']))
        self.assertEqual(result['acceptance'],'NOT_GRANTED');self.assertEqual(result['full_body_path_homology'],'NOT_QUALIFIED')

    def test_edge_rename_alone_preserves_the_full_numerical_family(self):
        compiled=fixture();baseline=transverse_capacity_bound(compiled,'cuff');seam=compiled['links'][0]
        piece=compiled['textiles']['cuff']['source_geometry']
        piece['edges']={'source-chain-17':piece['edges']['underarm-front'],'source-chain-42':piece['edges']['underarm-back']}
        seam.update(edge_a='source-chain-17',edge_b='source-chain-42')
        renamed=transverse_capacity_bound(compiled,'cuff')
        for key in ('minimum','maximum','cells','breakpoints','source_seam_edge_arclengths_cm','bound_proof','minimum_proof'):
            self.assertEqual(renamed[key],baseline[key],key)

    def test_declared_chains_require_real_unique_contiguous_source_vertex_ids(self):
        for ids in (None,[],[3],[3,-4],[3,4],[3,False],[3,0,3],[3,1],[3,0.0]):
            compiled=fixture();compiled['textiles']['cuff']['source_geometry']['edges']['underarm-front']=ids
            with self.subTest(ids=ids),self.assertRaises(StudioError):transverse_capacity_bound(compiled,'cuff')
        compiled=fixture();compiled['links'][0]['edge_a']='undeclared-edge'
        with self.assertRaises(StudioError):transverse_capacity_bound(compiled,'cuff')

    def test_all_normalized_edge_breakpoints_are_used_and_maximum_can_be_internal(self):
        compiled=fixture();piece=compiled['textiles']['cuff']['source_geometry']
        piece.update(vertices=[[0.,0.],[10.,0.],[14.,5.],[10.,10.],[0.,10.]],
                     edges={'underarm-front':[4,0],'underarm-back':[1,2,3]})
        result=transverse_capacity_bound(compiled,'cuff')
        self.assertEqual(result['breakpoints'],[0.,.5,1.])
        self.assertEqual(result['maximum_capacity_cm'],14.)
        self.assertEqual(result['maximum']['fraction_a'],.5)
        self.assertEqual(result['minimum_capacity_cm'],10.)

    def test_analytical_minimum_of_affine_difference_can_be_inside_a_cell(self):
        compiled=fixture();piece=compiled['textiles']['cuff']['source_geometry']
        piece['vertices']=[[0.,0.],[2.,1.],[2.,1.5],[0.,2.]]
        result=transverse_capacity_bound(compiled,'cuff')
        self.assertAlmostEqual(result['minimum_capacity_cm'],2.,places=8)
        self.assertAlmostEqual(result['minimum']['fraction_a'],1/3,places=8)
        self.assertAlmostEqual(result['maximum_capacity_cm'],math.sqrt(5),places=8)
        self.assertEqual(result['native_seam_alignment'],'NOT_OBSERVED')

    def test_non_simple_or_outside_material_path_cannot_grant_a_capacity_bound(self):
        compiled=fixture();piece=compiled['textiles']['cuff']['source_geometry']
        piece.update(vertices=[[0.,0.],[10.,0.],[10.,10.],[5.001,10.],[5.001,4.],[5.,4.],[5.,10.],[0.,10.]],
                     edges={'underarm-front':[7,0],'underarm-back':[1,2]})
        with self.assertRaisesRegex(StudioError,'leaves material'):transverse_capacity_bound(compiled,'cuff')
        piece['vertices']=[[0.,0.],[10.,10.],[0.,10.],[10.,0.]]
        with self.assertRaisesRegex(StudioError,'simple source'):transverse_capacity_bound(compiled,'cuff')

    def test_canonical_loop_requires_one_permanent_unary_source_join(self):
        for mutation in ('closure','orientation','second','other_piece','shared_atom','wrong_ref','wrong_component'):
            compiled=copy.deepcopy(fixture());seam=compiled['links'][0]
            if mutation=='closure':seam['kind']='closure'
            if mutation=='orientation':seam['orientation']='forward'
            if mutation=='second':compiled['links'].append(dict(seam,id='second'))
            if mutation=='other_piece':seam['piece_b']='invented'
            if mutation=='shared_atom':compiled['textiles']['cuff']['source_geometry']['edges']['underarm-back']=[3,0]
            if mutation=='wrong_ref':seam['source_ref']={'path':'other.garmentpkg','sha256':'b'*64}
            if mutation=='wrong_component':seam['component_id']='other-source'
            with self.subTest(mutation=mutation),self.assertRaises(StudioError):transverse_capacity_bound(compiled,'cuff')

    def test_capacity_signal_does_not_define_ease_or_physical_impossibility(self):
        bound=transverse_capacity_bound(fixture(),'cuff')
        curve=[[-5.,-5.,0.],[5.,-5.,0.],[5.,5.,0.],[-5.,5.,0.]]
        section={'id':'source-skin.section','ok':True,'status':'MEASURED','curve_cm':curve,'girth_cm':40.}
        result=compare_body_section(bound,section)
        self.assertEqual(result['nominal_maximum_minus_body_cm'],-11.)
        self.assertEqual(result['signal'],'BODY_SECTION_EXCEEDS_NOMINAL_TRANSVERSE_MAXIMUM')
        self.assertEqual(result['physical_impossibility'],'NOT_ESTABLISHED')
        self.assertEqual(result['numeric_ease_target'],'NOT_DEFINED')
        with self.assertRaises(StudioError):compare_body_section(bound,{'status':'CONSERVATIVE_SKIN_PROJECTION_MEASURED'})


class DeclaredBodySectionSelection(unittest.TestCase):
    def test_arbitrary_region_and_section_ids_are_selected_by_actual_declared_domain(self):
        descriptor=region_descriptor();before=digest(descriptor)
        left=_middle_upper_arm_section(descriptor,'left');right=_middle_upper_arm_section(descriptor,'right')
        self.assertEqual(left['id'],'left-measurement-2');self.assertEqual(right['id'],'right-measurement-2')
        self.assertEqual(left['parameter'],.5);self.assertEqual(before,digest(descriptor))
        descriptor['supplement']['regions'].reverse()
        for region in descriptor['supplement']['regions']:region['sections'].reverse()
        reindex(descriptor)
        self.assertEqual(_middle_upper_arm_section(descriptor,'left'),left)

    def test_a_familiar_id_does_not_relabel_a_forearm_or_other_side(self):
        descriptor=region_descriptor();forearm=copy.deepcopy(descriptor['supplement']['regions'][0])
        forearm.update(id='forearm-domain',domain='WRIST_TO_ELBOW_ONLY')
        forearm['sections']=[dict(forearm['sections'][2],id='upper.left.section.1')]
        descriptor['supplement']['regions'].append(forearm);reindex(descriptor)
        self.assertEqual(_middle_upper_arm_section(descriptor,'left')['id'],'left-measurement-2')

    def test_missing_wrong_domain_side_or_parameter_cannot_select_a_body_section(self):
        for mutation in ('absent','wrong_domain','wrong_side','wrong_parameter'):
            descriptor=region_descriptor();region=descriptor['supplement']['regions'][0]
            if mutation=='absent':region['sections'].pop(2)
            if mutation=='wrong_domain':region['domain']='WRIST_TO_ELBOW_ONLY'
            if mutation=='wrong_side':region['side']='right'
            if mutation=='wrong_parameter':region['sections'][2]['parameter']=.5+1e-9
            reindex(descriptor)
            with self.subTest(mutation=mutation),self.assertRaisesRegex(StudioError,'one unique declared'):
                _middle_upper_arm_section(descriptor,'left')

    def test_duplicate_middle_section_or_domain_is_ambiguous_even_if_one_is_incomplete(self):
        for mutation in ('same_region','other_region','incomplete_duplicate'):
            descriptor=region_descriptor();region=descriptor['supplement']['regions'][0]
            section=dict(region['sections'][2],id='second-middle')
            if mutation=='incomplete_duplicate':section.update(ok=False,status='INCOMPLETE')
            if mutation=='other_region':descriptor['supplement']['regions'].append(dict(copy.deepcopy(region),id='second-domain',sections=[section]))
            else:region['sections'].append(section)
            reindex(descriptor)
            with self.subTest(mutation=mutation),self.assertRaisesRegex(StudioError,'one unique declared'):
                _middle_upper_arm_section(descriptor,'left')

    def test_section_must_be_measured_and_agree_with_its_declared_region(self):
        for mutation in ('not_ok','incomplete','hull','missing_index','wrong_index_key','different_region','different_section'):
            descriptor=region_descriptor();region=descriptor['supplement']['regions'][0];section=region['sections'][2]
            if mutation=='not_ok':section['ok']=False
            if mutation=='incomplete':section['status']='INCOMPLETE'
            if mutation=='hull':section['status']='CONSERVATIVE_SKIN_PROJECTION_MEASURED'
            if mutation=='missing_index':descriptor['sections'].pop(section['id'])
            if mutation=='wrong_index_key':descriptor['sections']['upper.left.section.1']=descriptor['sections'].pop(section['id'])
            if mutation=='different_region':descriptor['sections'][section['id']]['region']=dict(region,side='right')
            if mutation=='different_section':descriptor['sections'][section['id']]['section']=dict(section,parameter=.25)
            with self.subTest(mutation=mutation),self.assertRaises(StudioError):_middle_upper_arm_section(descriptor,'left')


class CapacityProjectWrapper(unittest.TestCase):
    def setUp(self):
        self.directory=tempfile.TemporaryDirectory(prefix='a3d-capacity-wrapper-')
        self.addCleanup(self.directory.cleanup);self.root=Path(self.directory.name);self.project=SimpleNamespace(root=self.root)
        self.compiled=fixture();sleeve=copy.deepcopy(self.compiled['textiles']['cuff']);sleeve['semantics']['role']='sleeve'
        self.compiled['textiles']['sleeve']=sleeve
        self.compiled['links'].append(dict(self.compiled['links'][0],id='source::sleeve',piece_a='sleeve',piece_b='sleeve'))
        for key,path in (('source_ref','dossier.json'),('specification_source_ref','metadata.json')):
            file=self.root/path;file.write_text('{}',encoding='utf-8');self.compiled[key]={'path':path,'sha256':sha(file)}
        (self.root/'compiled.json').write_text(json.dumps(self.compiled),encoding='utf-8')

    def test_wrapper_consumes_authenticated_descriptor_without_named_section_shortcut(self):
        descriptor=region_descriptor();before=digest([self.compiled,descriptor])
        with patch('a3d.production_dossier.compile_project_dossier',return_value=self.compiled) as compile_source,patch(
                'a3d.body_region_sections.body_region_descriptor',return_value=descriptor) as authenticate:
            result=project_capacity_bounds(self.project,'compiled.json','policy.json',descriptor['supplement_ref'])
        compile_source.assert_called_once_with(self.project,'dossier.json','metadata.json')
        authenticate.assert_called_once_with(self.project,'policy.json',descriptor['supplement_ref'])
        self.assertEqual(len(result['bounds']),2);self.assertEqual(len(result['signals']),1)
        self.assertEqual(result['signals'][0]['piece_id'],'sleeve')
        self.assertEqual(result['signals'][0]['body_section_id'],'left-measurement-2')
        self.assertEqual(result['signals'][0]['nominal_maximum_minus_body_cm'],-11.)
        self.assertEqual(result['acceptance'],'NOT_GRANTED');self.assertFalse(result['patterns_changed'])
        self.assertEqual(before,digest([self.compiled,descriptor]))

    def test_wrapper_preserves_source_and_native_authentication_refusals(self):
        with patch('a3d.production_dossier.compile_project_dossier',return_value=self.compiled),patch(
                'a3d.body_region_sections.body_region_descriptor',side_effect=StudioError('Unauthenticated body supplement')):
            with self.assertRaisesRegex(StudioError,'Unauthenticated'):
                project_capacity_bounds(self.project,'compiled.json','policy.json',{'path':'supplement.json','sha256':'c'*64})
        with patch('a3d.production_dossier.compile_project_dossier',return_value=dict(self.compiled,unexpected='changed')):
            with self.assertRaisesRegex(StudioError,'exact current recompiled'):
                project_capacity_bounds(self.project,'compiled.json')


if __name__=='__main__':unittest.main()
