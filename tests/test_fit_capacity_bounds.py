"""Nominal source path bounds, never a physical garment acceptance fixture."""
import copy
import json
import math
import unittest

from a3d.core import StudioError,digest
from a3d.fit_capacity_bounds import compare_body_section,transverse_capacity_bound


def fixture():
    ref={'path':'synthetic.garmentpkg','sha256':'a'*64}
    piece={'vertices':[[2.,0.],[27.,0.],[29.,20.],[0.,20.]],
           'faces':[[0,1,2],[0,2,3]],'edges':{'underarm-front':[3,0],'underarm-back':[1,2]}}
    seam={'id':'source::underarm','component_id':'source','piece_a':'cuff','piece_b':'cuff',
          'edge_a':'underarm-front','edge_b':'underarm-back','kind':'permanent','orientation':'reverse','source_ref':ref}
    return {'textiles':{'cuff':{'component_id':'source','semantics':{'role':'cuff','side':'left','layer':'outer'},
                              'package_source_ref':ref,'source_geometry':piece}},'links':[seam]}


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
        for mutation in ('closure','orientation','second','other_piece','shared_atom','wrong_ref'):
            compiled=copy.deepcopy(fixture());seam=compiled['links'][0]
            if mutation=='closure':seam['kind']='closure'
            if mutation=='orientation':seam['orientation']='forward'
            if mutation=='second':compiled['links'].append(dict(seam,id='second'))
            if mutation=='other_piece':seam['piece_b']='invented'
            if mutation=='shared_atom':compiled['textiles']['cuff']['source_geometry']['edges']['underarm-back']=[3,0]
            if mutation=='wrong_ref':seam['source_ref']={'path':'other.garmentpkg','sha256':'b'*64}
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


if __name__=='__main__':unittest.main()
