"""Portable permanent-reference contracts; these tests do not qualify Cloth."""
import copy
import math
import unittest
from unittest import mock

from a3d.core import StudioError, digest
from a3d.cloth_metrics import triangle_metrics
from a3d.mesh_refinement import improve_interior


class SharedReferenceRefinement(unittest.TestCase):
    def setUp(self):
        self.vertices=[[0.,0.],[2.,0.],[2.,2.],[0.,2.],[.2,.2]]
        self.faces=[[0,1,4],[1,2,4],[2,3,4],[3,0,4]]
        self.settings={'target_angle':25.,'min_edge':.1,'max_displacement':.5}

    def run_shared(self,vertices=None,reference=None,faces=None,fixed=(),**settings):
        return improve_interior(self.vertices if vertices is None else vertices,
            self.faces if faces is None else faces,fixed,**{**self.settings,**settings},
            displacement_reference=self.vertices if reference is None else reference)

    def test_second_call_spends_the_same_permanent_budget(self):
        first,_=improve_interior(self.vertices,self.faces,[],**self.settings)
        legacy,legacy_report=improve_interior(first,self.faces,[],**self.settings)
        shared,report=self.run_shared(vertices=first)
        self.assertGreater(math.dist(legacy[4],self.vertices[4]),.5)
        self.assertTrue(legacy_report['target_reached'])
        self.assertEqual(shared,first)
        self.assertFalse(report['target_reached'])
        self.assertEqual(report['accepted_vertex_moves'],0)
        binding=report['displacement_reference']
        self.assertEqual(binding['maximum_entry_displacement_cm'],math.dist(first[4],self.vertices[4]))
        self.assertEqual(binding['maximum_cumulative_displacement_cm'],binding['maximum_entry_displacement_cm'])
        self.assertEqual(report['maximum_displacement_cm'],0.)

    def test_same_reference_as_entry_preserves_legacy_points_and_receipt_fields(self):
        legacy,receipt=improve_interior(self.vertices,self.faces,[],**self.settings)
        shared,report=self.run_shared()
        self.assertEqual(shared,legacy)
        self.assertEqual({k:v for k,v in report.items() if k!='displacement_reference'},receipt)
        self.assertEqual(report['displacement_reference']['reference_sha256'],digest(self.vertices))

    def test_explicit_none_preserves_exact_legacy_receipt(self):
        expected=improve_interior(self.vertices,self.faces,[],**self.settings)
        actual=improve_interior(self.vertices,self.faces,[],**self.settings,displacement_reference=None)
        self.assertEqual(actual,expected)
        self.assertNotIn('displacement_reference',actual[1])

    def test_entry_outside_permanent_budget_refuses_before_metric_or_optimization(self):
        reference=copy.deepcopy(self.vertices);reference[4]=[-.2,-.2]
        before=copy.deepcopy((self.vertices,self.faces,reference))
        with mock.patch('a3d.mesh_refinement.triangle_metrics') as metrics:
            with self.assertRaisesRegex(StudioError,'entry exceeds'):
                self.run_shared(reference=reference)
            metrics.assert_not_called()
        self.assertEqual((self.vertices,self.faces,reference),before)

    def test_reference_count_and_shape_are_explicit(self):
        cases=[[],self.vertices[:-1],self.vertices+[[0.,0.]],{},iter(self.vertices),
            [[0.,0.,0.]]*5,[[0.]]*5,[None]*5,['ab']*5]
        for reference in cases:
            with self.subTest(reference_type=type(reference).__name__),self.assertRaises(StudioError):
                self.run_shared(reference=reference)

    def test_reference_nonfinite_bool_and_nonnative_numeric_types_refuse(self):
        class IntSubtype(int):pass
        class FloatSubtype(float):pass
        for value in (math.nan,math.inf,-math.inf,True,False,'0',IntSubtype(0),FloatSubtype(0.),10**400):
            reference=copy.deepcopy(self.vertices);reference[0][0]=value
            with self.subTest(value_type=type(value).__name__),self.assertRaises(StudioError):
                self.run_shared(reference=reference)

    def test_tuple_reference_native_ints_and_floats_is_accepted(self):
        reference=tuple(tuple(int(x) if x.is_integer() else x for x in p) for p in self.vertices)
        result,report=self.run_shared(reference=reference)
        self.assertEqual(result[:4],self.vertices[:4])
        self.assertEqual(report['displacement_reference']['reference_sha256'],digest(reference))

    def test_zero_budget_returns_exact_entry_without_moves(self):
        result,report=self.run_shared(max_displacement=0.)
        self.assertEqual(result,self.vertices)
        self.assertEqual(report['accepted_vertex_moves'],0)
        self.assertEqual(report['displacement_reference']['maximum_cumulative_displacement_cm'],0.)

    def test_zero_budget_refuses_nonzero_entry_displacement(self):
        reference=copy.deepcopy(self.vertices);reference[0][0]=math.nextafter(0.,1.)
        with self.assertRaisesRegex(StudioError,'entry exceeds'):
            self.run_shared(reference=reference,max_displacement=0.)

    def test_exact_entry_bound_accepts_but_nextafter_outside_refuses(self):
        reference=copy.deepcopy(self.vertices);reference[0]=[-.5,0.]
        result,report=self.run_shared(reference=reference,passes=0)
        self.assertEqual(result,self.vertices)
        self.assertEqual(report['displacement_reference']['maximum_entry_displacement_cm'],.5)
        reference[0]=[-math.nextafter(.5,math.inf),0.]
        with self.assertRaisesRegex(StudioError,'entry exceeds'):
            self.run_shared(reference=reference,passes=0)

    def test_actual_trial_distance_uses_strict_bound_without_epsilon(self):
        first,_=improve_interior(self.vertices,self.faces,[],**self.settings,passes=1)
        exact=math.dist(first[4],self.vertices[4])
        admitted,_=self.run_shared(max_displacement=exact,passes=1)
        lower=math.nextafter(exact,0.)
        bounded,_=self.run_shared(max_displacement=lower,passes=1)
        self.assertEqual(admitted,first)
        self.assertNotEqual(bounded[4],first[4])
        self.assertLessEqual(math.dist(bounded[4],self.vertices[4]),lower)

    def test_reference_does_not_replace_fixed_entry_anchor_contract(self):
        reference=copy.deepcopy(self.vertices);reference[0]=[-.4,0.];reference[4]=[.1,.1]
        result,report=self.run_shared(reference=reference,fixed={4})
        self.assertEqual(result,self.vertices)
        self.assertEqual(report['fixed_vertex_count'],5)
        self.assertEqual(report['displacement_reference']['fixed_anchor_policy'],'UNCHANGED_FROM_CALL_ENTRY')

    def test_automatic_boundary_and_both_windings_remain_preserved(self):
        clockwise=[list(reversed(f)) for f in self.faces]
        for faces in (self.faces,clockwise):
            before=copy.deepcopy(faces)
            result,report=self.run_shared(faces=faces)
            self.assertEqual(result[:4],self.vertices[:4])
            self.assertEqual(report['boundary_vertex_count'],4)
            self.assertEqual(faces,before)
            for face in faces:
                def sign(points):
                    a,b,c=[points[i] for i in face]
                    return (b[0]-a[0])*(c[1]-a[1])-(b[1]-a[1])*(c[0]-a[0])
                self.assertGreater(sign(self.vertices)*sign(result),0.)

    def test_inputs_and_return_have_no_mutable_alias(self):
        reference=copy.deepcopy(self.vertices);before=copy.deepcopy((self.vertices,self.faces,reference))
        result,report=self.run_shared(reference=reference)
        self.assertEqual((self.vertices,self.faces,reference),before)
        result[0][0]=100.
        self.assertEqual((self.vertices,self.faces,reference),before)
        reference[4][0]=200.
        self.assertNotEqual(result[4][0],200.)
        self.assertEqual(report['displacement_reference']['reference_sha256'],digest(before[2]))

    def test_reference_is_frozen_before_hostile_external_mutation(self):
        reference=copy.deepcopy(self.vertices);expected=self.run_shared(reference=reference)
        changed=False
        def metric(points):
            nonlocal changed
            if not changed:reference[4]=[100.,100.];changed=True
            return triangle_metrics(points)
        with mock.patch('a3d.mesh_refinement.triangle_metrics',side_effect=metric):
            actual=self.run_shared(reference=reference)
        self.assertEqual(actual,expected)

    def test_final_actual_coordinates_are_rechecked_after_metrics(self):
        calls=0
        def metric(points):
            nonlocal calls
            calls+=1
            if calls==5:points[2][0]=100.
            return triangle_metrics(points)
        with mock.patch('a3d.mesh_refinement.triangle_metrics',side_effect=metric):
            with self.assertRaisesRegex(StudioError,'result exceeds'):
                self.run_shared(passes=0)
        self.assertEqual(self.vertices[4],[.2,.2])

    def test_final_fixed_anchor_changes_refuse_even_inside_displacement_ball(self):
        calls=0
        def metric(points):
            nonlocal calls
            calls+=1
            if calls==5:points[0][0]=.1
            return triangle_metrics(points)
        with mock.patch('a3d.mesh_refinement.triangle_metrics',side_effect=metric):
            with self.assertRaisesRegex(StudioError,'fixed entry anchor'):
                self.run_shared(passes=0)
        self.assertEqual(self.vertices[0],[0.,0.])


if __name__=='__main__':unittest.main()
