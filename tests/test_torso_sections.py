import copy
import math
import unittest

from a3d.core import StudioError, digest
from a3d.torso_sections import half_section, apply_measured_sections
from a3d.preform_volume import paired_volume_frames
from tests.test_preform_volume import source_fixture


def section(height=20.):
    return {'status':'MEASURED','height_cm':height,'bounds_xy_cm':[[-2.,-1.],[2.,1.]],
            'curve_cm':[[-2.,-1.,height],[2.,-1.,height],[2.,1.,height],[-2.,1.,height]]}


class MeasuredTorsoContours(unittest.TestCase):
    def test_front_to_back_halves_preserve_both_sides_without_a_hull(self):
        data=section();before=digest(data)
        for side in (-1,1):
            curve,length=half_section(data,side)
            self.assertEqual(length,6.)
            self.assertEqual(curve[0],[0.,-1.,20.])
            self.assertEqual(curve[-1],[0.,1.,20.])
            self.assertTrue(all(side*p[0]>=0 for p in curve))
        self.assertEqual(digest(data),before)

    def test_surface_guide_retains_source_girth_at_actual_measured_heights(self):
        source,_,body=source_fixture()
        source={'pieces':{p:source['pieces'][p] for p in ('front','back')}}
        group={'front':'front','back':'back','side_sign':1,'uv_origin_cm':[0.,0.],
               'source_edges':{'front':{'hem':'hem','side':'side'},
                               'back':{'hem':'hem','side':'side','center':'center'}}}
        panels,report=paired_volume_frames(source,group,body)
        profile={'landmarks':{'chest':{'section':{'height_cm':20.}}},
                 'sections':[section(height) for height in (17.,20.,22.,27.)]}
        before=digest([source,profile])
        panels,report=apply_measured_sections(panels,report,group,profile)
        for row in panels['front']['arc_sections']:
            length=sum(math.dist(a,b) for a,b in zip(row['curve_cm'],row['curve_cm'][1:]))
            self.assertAlmostEqual(length,10.) # 8 cm sourced half plus explicit 2 cm tangent.
        self.assertEqual(report['measured_sections'][-1]['guide_height_cm'],27.)
        self.assertTrue(all(row['body_surface_extrapolated'] is False for row in report['measured_sections']))
        self.assertEqual(report['body_projection'],'NOT_EXECUTED')
        self.assertEqual(digest([source,profile]),before)
        incomplete=copy.deepcopy(profile);incomplete['sections']=[section()]
        with self.assertRaisesRegex(StudioError,'measured'):
            apply_measured_sections(panels,report,group,incomplete)

    def test_capacity_deficit_and_unmeasured_section_are_explicit_refusals(self):
        bad=section();bad['status']='NOT_QUALIFIED'
        with self.assertRaises(StudioError):half_section(bad,1)
        data=section();data['curve_cm']=[[x*10,y*10,z] for x,y,z in data['curve_cm']]
        data['bounds_xy_cm']=[[-20.,-10.],[20.,10.]]
        source,_,body=source_fixture()
        source={'pieces':{p:source['pieces'][p] for p in ('front','back')}}
        group={'front':'front','back':'back','side_sign':1,'uv_origin_cm':[0.,0.],
               'source_edges':{'front':{'hem':'hem','side':'side'},'back':{'hem':'hem','side':'side','center':'center'}}}
        panels,report=paired_volume_frames(source,group,body)
        sections=[]
        for height in (17.,22.,27.):
            row=copy.deepcopy(data);row['height_cm']=height
            row['curve_cm']=[[x,y,height] for x,y,_ in row['curve_cm']];sections.append(row)
        with self.assertRaisesRegex(StudioError,'capacity deficit'):
            apply_measured_sections(panels,report,group,{'landmarks':{'chest':{'section':{'height_cm':20.}}},'sections':sections})

    def test_zero_blend_shoulder_base_keeps_material_continuity_without_arm_girth(self):
        source,_,body=source_fixture();source={'pieces':{p:source['pieces'][p] for p in ('front','back')}}
        group={'front':'front','back':'back','side_sign':1,'uv_origin_cm':[0.,0.],
            'source_edges':{'front':{'hem':'hem','side':'side'},'back':{'hem':'hem','side':'side','center':'center'}},
            'measured_shoulder_transition':{'source_start_v_cm':5.,'source_edges':{},'upper_blend':1.}}
        panels,report=paired_volume_frames(source,group,body)
        profile={'sections':[section(height) for height in (17.,20.,22.,27.)]}
        base=next(row for row in panels['front']['arc_sections'] if row['v_cm']==5.)
        ellipse=copy.deepcopy(base['curve_cm']);before=digest([source,profile])
        panels,report=apply_measured_sections(panels,report,group,profile)
        base=next(row for row in panels['front']['arc_sections'] if row['v_cm']==5.)
        self.assertNotEqual(base['curve_cm'],ellipse)
        evidence=next(row for row in report['measured_sections'] if row['source_v_cm']==5.)
        self.assertEqual(evidence['surface_guide'],'MEASURED_SKIN_SHOULDER_MATERIAL_PLANE_TRANSITION')
        self.assertEqual(evidence['measurement_at_requested_height'],'NOT_USED')
        self.assertFalse(evidence['circumference_of_connected_arms_used'])
        lower=next(row for row in panels['front']['arc_sections'] if row['v_cm']==evidence['material_continuity_base_v_cm'])
        delta=5.-lower['v_cm']
        self.assertEqual(base['curve_cm'],[[p[0],p[1],p[2]+delta] for p in lower['curve_cm']])
        self.assertEqual(base['arc_offset_cm'],lower['arc_offset_cm'])
        self.assertEqual(digest([source,profile]),before)
        self.assertTrue(all(row['surface_guide']=='MEASURED_SKIN_SHOULDER_MATERIAL_PLANE_TRANSITION'
            for row in report['measured_sections'] if row['source_v_cm']>5.))


if __name__=='__main__':unittest.main()
