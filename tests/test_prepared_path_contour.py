"""Prepared constants versus the unchanged historical path predicate oracle."""
import copy
from dataclasses import FrozenInstanceError
import math
import random
import unittest
from unittest.mock import patch

from a3d.core import StudioError,digest
from a3d.fitting import path_inside,prepare_path_contour
from a3d.sewing import point_inside,segment_distance
from a3d.garment_measurements import intersect_guide_material_plane
from tests.test_guide_plane_linear_preparation import curve_inputs


def historical_path_inside(a,b,polygon):
    # Frozen pre-refactor oracle: ordering, lazy norm and all thresholds intact.
    cross=lambda u,v:u[0]*v[1]-u[1]*v[0]
    d=[b[k]-a[k]for k in range(2)];cuts={0.,1.}
    for x,y in zip(polygon,polygon[1:]+polygon[:1]):
        e=[y[k]-x[k]for k in range(2)];v=[x[k]-a[k]for k in range(2)];den=cross(d,e)
        if abs(den)>1e-12:
            t,u=cross(v,e)/den,cross(v,d)/den
            if 0<=t<=1 and 0<=u<=1:cuts.add(t)
        elif abs(cross(v,d))<1e-10:
            norm=sum(z*z for z in d)
            if norm>1e-20:
                cuts.update(max(0.,min(1.,sum((p[k]-a[k])*d[k]for k in range(2))/norm))for p in (x,y))
    values=sorted(cuts)
    for lo,hi in zip(values,values[1:]):
        p=[a[k]+(lo+hi)/2*d[k]for k in range(2)]
        if not point_inside(p,polygon)and min(segment_distance(p,x,y)for x,y in zip(polygon,polygon[1:]+polygon[:1]))>1e-7:return False
    return True


def outcome(function,*args):
    try:return ('RETURNED',function(*args))
    except Exception as error:return ('REFUSED',type(error).__name__,str(error))


class PreparedPathContourTests(unittest.TestCase):
    def compare(self,polygon,queries):
        before=repr(polygon);prepared=prepare_path_contour(polygon)
        for a,b in queries:
            expected=outcome(historical_path_inside,a,b,polygon)
            with self.subTest(a=a,b=b):
                self.assertEqual(outcome(path_inside,a,b,polygon),expected)
                self.assertEqual(outcome(prepared.path_inside,a,b),expected)
        self.assertEqual(before,repr(polygon))

    def test_concavities_slits_hole_bridge_boundary_and_direction_match_frozen_oracle(self):
        polygons=[[[0.,0.],[8.,0.],[8.,8.],[0.,8.]],
            [[0,0],[10,0],[10,10],[5.001,10],[5.001,4],[5,4],[5,10],[0,10]],
            [[0.,0.],[8.,0.],[8.,8.],[0.,8.],[0.,0.],[2.,2.],[2.,6.],[6.,6.],[6.,2.],[2.,2.],[0.,0.]]]
        rng=random.Random(1047)
        queries=[([0.,0.],[8.,0.]),([0.,4.],[8.,4.]),([1.,1.],[7.,7.]),([4.,4.],[4.,4.]),
            ([-1e-7,0.],[8.,0.]),([math.nextafter(-1e-7,-math.inf),0.],[8.,0.]),([0.,-0.],[8.,0.])]
        queries+=[([rng.uniform(-1.,11.),rng.uniform(-1.,11.)],
                   [rng.uniform(-1.,11.),rng.uniform(-1.,11.)])for _ in range(180)]
        queries+=[(b,a)for a,b in list(queries)]
        for polygon in polygons:self.compare(polygon,queries)

    def test_large_mixed_numbers_nonfinite_and_malformed_coordinates_preserve_errors(self):
        for polygon in ([],[[0.,0.]],[[0,0],[1.,0],[1,1.],[0.,1]],
                        [[10**400,0],[0.,1.],[1.,2.]],[[0.,0.],[float('inf'),0.],[1.,1.]],
                        [[0.,0.],[float('nan'),1.],[1.,1.]],[[0],[1],[2]],[[0,0,3],[1,0,3],[1,1,3]]):
            queries=[([0.,0.],[1.,1.]),([0,-0.],[10**308,1.]),([float('inf'),0.],[1.,1.]),
                ([float('nan'),0.],[1.,1.]),(None,[1.,1.]),([0.],[1.,1.])]
            self.compare(polygon,queries)
        for origin,span in ((1e16,64.),(1e100,1e90),(0.,1e308)):
            polygon=[[origin,0.],[origin+span,0.],[origin+span,span],[origin,span]]
            self.compare(polygon,[(polygon[0],polygon[2]),([origin+span/2,span/2],[origin+span/2,span])])

    def test_query_direction_norm_is_lazy_and_constant_overflow_remains_lazy(self):
        a=[0,0];b=[10**308,1.]
        noncollinear=[[0,-.5],[1,-.5],[1,.5],[0,.5]]
        self.assertEqual(outcome(historical_path_inside,a,b,noncollinear),('RETURNED',False))
        self.compare(noncollinear,[(a,b)])
        collinear=[[0,0],[10**308,1.],[10**308,2.],[0,1.]]
        self.assertEqual(outcome(historical_path_inside,a,b,collinear)[1],'OverflowError')
        self.compare(collinear,[(a,b)])
        polygon=[[10**400,0],[0.,1.],[1.,2.]]
        prepared=prepare_path_contour(polygon)
        self.assertFalse(prepared.complete)
        self.assertEqual(outcome(prepared.path_inside,[0,0],[1,1]),outcome(historical_path_inside,[0,0],[1,1],polygon))

    def test_snapshot_is_local_immutable_and_never_reuses_other_contours(self):
        polygon=[[0.,0.],[8.,0.],[8.,8.],[0.,8.]];before=digest(polygon)
        prepared=prepare_path_contour(polygon,max_edges=4)
        self.assertTrue(prepared.path_inside([1.,1.],[7.,7.]))
        self.assertEqual(before,digest(polygon))
        with self.assertRaises(FrozenInstanceError):prepared.polygon=()
        with self.assertRaises(TypeError):prepared.polygon[0][0]=10.
        for point in polygon:point[0]+=100.
        other=prepare_path_contour(polygon)
        self.assertTrue(prepared.path_inside([1.,1.],[7.,7.]))
        self.assertFalse(other.path_inside([1.,1.],[7.,7.]))

    def test_preparation_storage_cap_and_deadline_are_checked_before_copy_and_each_edge(self):
        polygon=[[0.,0.],[8.,0.],[8.,8.],[0.,8.]]
        for maximum in (3,-1,True):
            with self.subTest(maximum=maximum),self.assertRaisesRegex(StudioError,'edge budget'):
                prepare_path_contour(polygon,max_edges=maximum)
        calls=[0]
        def stopped():
            calls[0]+=1
            if calls[0]>5:raise StudioError('deadline')
        with self.assertRaisesRegex(StudioError,'deadline'):prepare_path_contour(polygon,max_edges=4,check_time=stopped)
        self.assertEqual(calls[0],6)

    def test_measurement_report_matches_uncached_oracle_and_does_not_modify_inputs(self):
        source,frame,triangles,section=curve_inputs();before=digest([source,frame,triangles,section])
        class Oracle:
            def __init__(self,polygon):self.polygon=copy.deepcopy(polygon)
            def path_inside(self,a,b):return historical_path_inside(a,b,self.polygon)
        with patch('a3d.fitting.prepare_path_contour',side_effect=lambda polygon,**kwargs:Oracle(polygon)):
            expected=intersect_guide_material_plane(source,frame,triangles,section,['left','right'])
        actual=intersect_guide_material_plane(source,frame,triangles,section,['left','right'])
        self.assertEqual(actual,expected);self.assertEqual(before,digest([source,frame,triangles,section]))

    def test_measurement_checks_deadline_after_predicate_and_rejects_mutated_contour(self):
        original=prepare_path_contour
        source,frame,triangles,section=curve_inputs();elapsed=[0.]
        class Expensive:
            def __init__(self,contour):self.contour=contour
            def path_inside(self,a,b):
                result=self.contour.path_inside(a,b);elapsed[0]+=.06;return result
        with patch('a3d.fitting.prepare_path_contour',side_effect=lambda polygon,**kwargs:Expensive(original(polygon,**kwargs))),\
                self.assertRaisesRegex(StudioError,'time budget exhausted'):
            intersect_guide_material_plane(source,frame,triangles,section,['left','right'],clock=lambda:elapsed[0],max_seconds=.05)
        source,frame,triangles,section=curve_inputs()
        def mutated(polygon,**kwargs):
            contour=original(polygon,**kwargs);polygon[0][0]+=.01;return contour
        with patch('a3d.fitting.prepare_path_contour',side_effect=mutated),self.assertRaises(StudioError):
            intersect_guide_material_plane(source,frame,triangles,section,['left','right'])
