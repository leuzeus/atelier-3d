"""Exact oracle for local invariant preparation; no spatial cage lookup."""
import copy
import math
import random
import unittest
from unittest.mock import patch

from a3d.core import StudioError,digest
from a3d.garment_measurements import _prepare_linear_cage_evaluator,intersect_guide_material_plane
from a3d.pattern_assembly import _compile_cage,_cage_point


def frame_grid(size=6):
    uv=[[float(x),float(y)]for y in range(size+1)for x in range(size+1)]
    triangles=[]
    for y in range(size):
        for x in range(size):
            a=y*(size+1)+x;b=a+1;c=a+size+1;d=c+1
            triangles.extend(([a,b,d],[a,d,c]))
    return {'uv_cm':uv,'target_cm':[[x*.71+y*.07,y*.93-x*.04,y]for x,y in uv],'triangles':triangles}


def outcome(function,uv):
    try:return ('RETURNED',function(uv))
    except Exception as error:return ('REFUSED',type(error).__name__,str(error),getattr(error,'reason_category',None))


def curve_inputs():
    frame=frame_grid()
    source={'vertices':[[0.,0.],[6.,0.],[6.,6.],[0.,6.]],'edges':{'left':[0,3],'right':[2,1]}}
    triangles=[[copy.deepcopy(frame['uv_cm'][index])for index in triangle]for triangle in frame['triangles']]
    section={'center_cm':[0.,0.,3.25],'plane':{'normal_world':[0.,0.,1.]}}
    return source,frame,triangles,section


class LinearCagePreparation(unittest.TestCase):
    def compare(self,frame,points):
        before=digest(frame);compiled=_compile_cage(frame,'measurement')
        prepared=_prepare_linear_cage_evaluator(frame,compiled,lambda:None)
        reference=lambda uv:_cage_point(frame,compiled,uv,'measurement')
        for uv in points:
            with self.subTest(uv=uv):self.assertEqual(outcome(prepared,uv),outcome(reference,uv))
        self.assertEqual(before,digest(frame))

    def test_shared_edges_vertices_outside_tolerance_neighbors_and_random_points_match_exactly(self):
        frame=frame_grid();rng=random.Random(2410)
        points=copy.deepcopy(frame['uv_cm'])+[[.5,.5],[1.,.5],[-1e-8,0.],[-1e-7,0.],[6.+1e-8,0.]]
        points+=[[rng.uniform(-.1,6.1),rng.uniform(-.1,6.1)]for _ in range(200)]
        for value in (0.,1.,6.):
            points.extend([[math.nextafter(value,-math.inf),2.],[math.nextafter(value,math.inf),2.]])
        self.compare(frame,points)

    def test_reversed_cells_ill_conditioned_large_origins_signed_zero_and_nonfinite_queries_match(self):
        cases=[]
        reversed_frame=frame_grid(2);reversed_frame['triangles']=[list(reversed(row))for row in reversed_frame['triangles']]
        cases.append((reversed_frame,[[.25,.5],[1.,1.],[0.,-0.],[float('nan'),0.],[float('inf'),0.],[True,0.]]))
        for origin,span in ((1e16,64.),(1e100,1e90),(0.,1e150),(0.,1e308)):
            uv=[[origin,0.],[origin+span,0.],[origin+span,span],[origin,span]]
            frame={'uv_cm':uv,'target_cm':[[0.,0.,0.],[1.,0.,0.],[1.,1.,0.],[0.,1.,0.]],'triangles':[[0,1,2],[0,2,3]]}
            cases.append((frame,[uv[0],uv[2],[origin+span/2,span/2],[origin-span,span/2]]))
        narrow={'uv_cm':[[0.,0.],[1e8,0.],[1e8,1e-8]],'target_cm':[[0.,0.,0.],[1.,0.,0.],[1.,1.,0.]],'triangles':[[0,1,2]]}
        cases.append((narrow,[[5e7,5e-9],[1e8,1e-8],[1e8,math.nextafter(1e-8,math.inf)]]))
        for frame,points in cases:self.compare(frame,points)

    def test_all_overlaps_and_first_candidate_order_are_preserved(self):
        base={'uv_cm':[[0.,0.],[1.,0.],[0.,1.]],'target_cm':[[0.,0.,0.],[1.,0.,0.],[0.,1.,0.]],'triangles':[[0,1,2]]}
        for conflict in (False,True):
            frame=copy.deepcopy(base);frame['uv_cm']*=2;frame['target_cm']*=2
            frame['triangles'].append([3,4,5])
            if conflict:frame['target_cm'][3]=[0.,0.,1.]
            self.compare(frame,[[.25,.25],[0.,0.],[1.,0.]])
        frame=frame_grid(2);frame['triangles'].reverse();self.compare(frame,[[1.,1.],[.5,.5]])

    def test_necessary_weight_short_circuit_keeps_exact_tolerance_and_numeric_errors(self):
        frame={'uv_cm':[[0.,0.],[1.,0.],[0.,1.]],'target_cm':[[0.,0.,0.],[1.,0.,0.],[0.,1.,0.]],
               'triangles':[[0,1,2]]}
        points=[[value,0.]for value in (-1e-8,math.nextafter(-1e-8,-math.inf),math.nextafter(-1e-8,math.inf),
            1+1e-8,math.nextafter(1+1e-8,math.inf),math.nextafter(1+1e-8,-math.inf))]
        points.extend(([2.,1e308],[1e308,2.],[-1e308,1e308]))
        self.compare(frame,points)
        # Beta is already outside, but the historical mixed-number gamma
        # calculation still raises OverflowError. It must not be masked.
        mixed={'uv_cm':[[0,0],[2,0],[0,.5]],'target_cm':frame['target_cm'],'triangles':[[0,1,2]]}
        uv=[4,10**308];compiled=_compile_cage(mixed,'measurement')
        self.assertEqual(outcome(lambda p:_cage_point(mixed,compiled,p,'measurement'),uv)[1],'OverflowError')
        self.compare(mixed,[uv,[4,1],[0,0]])

    def test_prepared_evaluator_is_per_call_and_cannot_mix_equal_uvs_across_frames(self):
        a=frame_grid(2);b=copy.deepcopy(a)
        for point in b['target_cm']:point[2]+=7.
        eval_a=_prepare_linear_cage_evaluator(a,_compile_cage(a,'measurement'),lambda:None)
        eval_b=_prepare_linear_cage_evaluator(b,_compile_cage(b,'measurement'),lambda:None)
        self.assertNotEqual(eval_a([.25,.5]),eval_b([.25,.5]))
        self.assertEqual(eval_a([.25,.5]),_cage_point(a,_compile_cage(a,'measurement'),[.25,.5],'measurement'))

    def test_full_curve_report_is_identical_to_historical_evaluator(self):
        source,frame,triangles,section=curve_inputs();before=digest([source,frame,triangles,section])
        def oracle(frame,compiled,check):return lambda uv:_cage_point(frame,compiled,uv,'measurement',check)
        with patch('a3d.garment_measurements._prepare_linear_cage_evaluator',side_effect=oracle):
            reference=intersect_guide_material_plane(source,frame,triangles,section,['left','right'])
        actual=intersect_guide_material_plane(source,frame,triangles,section,['left','right'])
        self.assertEqual(actual,reference)
        self.assertEqual(actual['guide_evaluation_backend'],'LINEAR_CAGE')
        self.assertEqual(actual['budgets'],{'max_faces':50000,'max_points':20000,'max_seconds':15.})
        self.assertEqual(before,digest([source,frame,triangles,section]))

    def test_preparation_and_evaluation_check_deadline_for_every_cell(self):
        frame=frame_grid(2);compiled=_compile_cage(frame,'measurement');calls=[0]
        def stopped():
            calls[0]+=1
            if calls[0]>2:raise StudioError('Guide-plane material computation time budget exhausted')
        with self.assertRaisesRegex(StudioError,'time budget exhausted'):
            _prepare_linear_cage_evaluator(frame,compiled,stopped)
        # Use a fresh hook to stop evaluation, after successful preparation.
        stop=[False]
        def check():
            if stop[0]:raise StudioError('Guide-plane material computation time budget exhausted')
        prepared=_prepare_linear_cage_evaluator(frame,compiled,check);stop[0]=True
        with self.assertRaisesRegex(StudioError,'time budget exhausted'):prepared([.25,.5])

    def test_unchanged_face_point_and_deadline_budgets_reject_instead_of_increasing(self):
        source,frame,triangles,section=curve_inputs()
        for kwargs in ({'max_faces':1},{'max_points':2},{'max_seconds':.1,'clock':iter([0.,1.]).__next__}):
            with self.subTest(kwargs=list(kwargs)),self.assertRaises(StudioError):
                intersect_guide_material_plane(source,frame,triangles,section,['left','right'],**kwargs)

    def test_mutation_after_local_preparation_cannot_return_a_measurement(self):
        source,frame,triangles,section=curve_inputs();original=_prepare_linear_cage_evaluator
        def changed(frame,compiled,check):
            evaluator=original(frame,compiled,check);frame['target_cm'][0][0]+=.01;return evaluator
        with patch('a3d.garment_measurements._prepare_linear_cage_evaluator',side_effect=changed),\
                self.assertRaisesRegex(StudioError,'changed its exact source inputs'):
            intersect_guide_material_plane(source,frame,triangles,section,['left','right'])
