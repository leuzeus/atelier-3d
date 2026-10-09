"""Exact closed-triangle reserve evidence is separate from anatomical adoption."""
import copy
from fractions import Fraction
import math
import unittest

from a3d.attachment_clearance import (AttachmentClearanceRefused, check_attachment_clearance,
                                     check_attachment_clearances, propose_attachment_clearance)


def plane(z=0.):
    return [[-2., -2., z], [2., -2., z], [0., 2., z]], [[0, 1, 2]]


def exact(record):
    return Fraction(int(record['numerator']), int(record['denominator']))


def check(point, vertices=None, triangles=None, **kwargs):
    default_vertices, default_triangles = plane()
    return check_attachment_clearance(default_vertices if vertices is None else vertices,
                                     default_triangles if triangles is None else triangles,
                                     point, clearance_cm=kwargs.pop('clearance_cm', .3),
                                     clock=lambda: 0., **kwargs)


def propose(vertices=None, triangles=None, **kwargs):
    default_vertices, default_triangles = plane()
    return propose_attachment_clearance(default_vertices if vertices is None else vertices,
        default_triangles if triangles is None else triangles,
        kwargs.pop('anchor', [0., 0., 0.]), kwargs.pop('offset', [0., 0., .1]),
        clearance_cm=kwargs.pop('clearance_cm', .3), safety_margin_cm=kwargs.pop('safety_margin_cm', .001),
        max_added_displacement_cm=kwargs.pop('max_added_displacement_cm', .5),
        search_step_cm=kwargs.pop('search_step_cm', .01), clock=lambda: 0., **kwargs)


class ExactAttachmentClearance(unittest.TestCase):
    def test_reserve_boundary_and_exact_shortfall_witness(self):
        equal = check([0., 0., .3])
        self.assertEqual(equal['status'], 'CLEARANCE_VERIFIED')
        self.assertTrue(equal['certificate']['coverage_complete'])
        low = check([0., 0., math.nextafter(.3, 0.)])
        self.assertEqual(low['status'], 'FIXED_TARGET_CLEARANCE_CONFLICT')
        certificate = low['certificate']
        self.assertTrue(certificate['necessary_conflict_proved'])
        self.assertLess(exact(certificate['witness']['distance_squared_cm2']), Fraction(.3)**2)
        weights = [exact(x) for x in certificate['witness']['barycentric']]
        self.assertEqual(sum(weights), 1)
        self.assertGreaterEqual(min(weights), 0)

    def test_exact_sum_of_declared_margin_is_not_rounded_down(self):
        target = float(Fraction(.3)+Fraction(.001))
        report = check([0., 0., target], safety_margin_cm=.001)
        threshold = exact(report['certificate']['threshold_cm'])
        self.assertEqual(threshold, Fraction(.3)+Fraction(.001))
        self.assertEqual(report['certificate']['clearance_satisfied'], Fraction(target) >= threshold)
        self.assertEqual(check([0., 0., math.nextafter(target, math.inf)], safety_margin_cm=.001)['status'], 'CLEARANCE_VERIFIED')

    def test_edge_vertex_and_degenerate_closed_triangle(self):
        vertices = [[0.,0.,0.],[2.,0.,0.],[0.,2.,0.]]
        edge = check([1., -.1, 0.], vertices, [[0,1,2]], clearance_cm=.2)['certificate']['witness']
        self.assertEqual(exact(edge['distance_squared_cm2']), Fraction(.1)**2)
        self.assertEqual(exact(edge['barycentric'][2]), 0)
        corner = check([-.1, -.1, 0.], vertices, [[0,1,2]], clearance_cm=.2)['certificate']['witness']
        self.assertEqual([exact(x) for x in corner['barycentric']], [1,0,0])
        degenerate = check([1., .1, 0.], [[0.,0.,0.],[1.,0.,0.],[2.,0.,0.]], [[0,1,2]], clearance_cm=.2)
        self.assertEqual(degenerate['status'], 'FIXED_TARGET_CLEARANCE_CONFLICT')

    def test_whole_body_checks_triangle_with_distant_centroid(self):
        vertices = [[0.,0.,0.],[1000.,0.,0.],[0.,1000.,0.],[-10.,-10.,10.],[10.,-10.,10.],[0.,10.,10.]]
        report = check([.01,.01,.1], vertices, [[3,4,5],[0,1,2]])
        self.assertEqual(report['certificate']['witness']['body_triangle'], 1)
        self.assertEqual(report['certificate']['visited_triangles'], 2)
        self.assertEqual(report['certificate']['exact_aabb_exclusions'], 1)

    def test_proof_includes_all_closed_triangles_not_only_nearest_guess(self):
        vertices, triangles = plane()
        upper, _ = plane(.31)
        vertices += upper
        report = check([0.,0.,.6], vertices, triangles+[[3,4,5]])
        self.assertEqual(report['status'], 'FIXED_TARGET_CLEARANCE_CONFLICT')
        self.assertEqual(report['certificate']['witness']['body_triangle'], 1)
        safe = check([0.,0.,1.], vertices, triangles+[[3,4,5]])
        self.assertTrue(safe['certificate']['coverage_complete'])
        self.assertEqual(safe['certificate']['visited_triangles'], 2)
        self.assertEqual(safe['qualification'], 'NONE')
        self.assertEqual(safe['signed_inside_outside'], 'NOT_ASSESSED')

    def test_batch_prepares_once_counts_conflicts_and_preserves_order(self):
        vertices, triangles = plane()
        points = [[0.,0.,.1],[0.,0.,.5],[0.,0.,.3]]
        report = check_attachment_clearances(vertices, triangles, points, clearance_cm=.3, clock=lambda:0.)
        self.assertEqual(report['status'], 'FIXED_TARGET_CLEARANCE_CONFLICTS')
        self.assertEqual((report['conflict_count'],report['verified_count'],report['checked_count']), (1,2,3))
        self.assertEqual([r['index'] for r in report['checks']], [0,1,2])
        self.assertEqual(report['work']['prepared_triangles'], 1)
        self.assertEqual(report['work']['prepared_vertices'], 3)
        self.assertEqual(report['work']['candidates'], 3)
        safe = check_attachment_clearances(vertices, triangles, points[1:], clearance_cm=.3, clock=lambda:0.)
        self.assertEqual(safe['status'], 'ALL_TARGET_CLEARANCES_VERIFIED')

    def test_deterministic_declared_ray_no_input_mutation_or_adoption(self):
        vertices, triangles = plane(); provenance={'path_sha256':'accepted-path','fraction':.4,'source_uv_cm':[2,3]}
        source=copy.deepcopy((vertices,triangles,provenance))
        first = propose(vertices,triangles,provenance=provenance)
        again = propose(vertices,triangles,provenance=provenance)
        self.assertEqual(first,again)
        self.assertEqual((vertices,triangles,provenance),source)
        self.assertEqual(first['status'],'CLEARANCE_VARIANT_PROPOSED')
        self.assertEqual(first['target_world_cm'][:2],[0.,0.])
        self.assertGreater(first['target_world_cm'][2],.301)
        self.assertLessEqual(first['added_displacement_cm'],.5)
        self.assertTrue(first['certificate']['coverage_complete'])
        self.assertEqual(first['initial_check']['necessary_conflict_proved'],True)
        self.assertEqual(first['minimality'],'NOT_CLAIMED')
        self.assertFalse(first['canonical_mutation'])
        self.assertEqual(first['qualification'],'NONE')

    def test_ray_search_does_not_assume_monotonic_clearance(self):
        vertices,triangles=plane(); upper,_=plane(.4);vertices+=upper;triangles+=[[3,4,5]]
        report=propose(vertices,triangles,clearance_cm=.16,safety_margin_cm=0.,search_step_cm=.15,max_added_displacement_cm=.6)
        self.assertEqual(len(report['trials']),4)
        self.assertEqual([r['status'] for r in report['trials']],['CLEARANCE_REFUSED']*3+['CLEARANCE_VERIFIED'])
        self.assertAlmostEqual(report['target_world_cm'][2],.7)
        self.assertEqual(report['clearance_monotonicity'],'NOT_ASSUMED')

    def test_already_valid_target_is_preserved(self):
        report=propose(offset=[0.,0.,.5])
        self.assertEqual(report['status'],'UNCHANGED_TARGET_CLEARANCE_VERIFIED')
        self.assertEqual(report['target_world_cm'],[0.,0.,.5])
        self.assertEqual(report['work']['candidates'],1)

    def test_rotation_translation_and_negative_ray(self):
        vertices,triangles=plane()
        original=propose(vertices,triangles,offset=[0.,0.,-.1])
        transform=lambda p:[p[2]+7.,p[0]-4.,p[1]+2.]
        turn=lambda p:[p[2],p[0],p[1]]
        rotated=propose([transform(p) for p in vertices],triangles,anchor=transform([0.,0.,0.]),offset=turn([0.,0.,-.1]))
        self.assertEqual(rotated['status'],original['status'])
        self.assertLess(math.dist(rotated['target_world_cm'],transform(original['target_world_cm'])),1e-13)
        self.assertEqual(rotated['path_anchor_world_cm'],[7.,-4.,2.])
        self.assertEqual(rotated['offset_world_cm'],[-.1,0.,0.])

    def test_rounding_cannot_bypass_actual_displacement_cap(self):
        vertices=[[1e16,-2.,-2.],[1e16,2.,-2.],[1e16,0.,2.]]
        with self.assertRaises(AttachmentClearanceRefused) as caught:
            propose(vertices,[[0,1,2]],anchor=[1e16,0.,0.],offset=[1.,0.,0.],max_added_displacement_cm=1.,search_step_cm=1.)
        diagnostic=caught.exception.diagnostic
        self.assertEqual(diagnostic['reason'],'NO_CANDIDATE_ON_DECLARED_RAY_GRID')
        self.assertEqual(diagnostic['trials'][0]['status'],'ROUNDED_DISPLACEMENT_CAP_REFUSED')

    def test_exhausted_grid_is_not_global_impossibility(self):
        with self.assertRaises(AttachmentClearanceRefused) as caught:
            propose(max_added_displacement_cm=.01)
        self.assertEqual(caught.exception.diagnostic['reason'],'NO_CANDIDATE_ON_DECLARED_RAY_GRID')
        self.assertFalse(caught.exception.diagnostic['geometric_impossibility_proved'])
        self.assertTrue(caught.exception.diagnostic['initial_check']['necessary_conflict_proved'])

    def test_candidate_budget_prevents_unbounded_tiny_step_allocation(self):
        with self.assertRaises(AttachmentClearanceRefused) as caught:
            propose(search_step_cm=1e-300,budgets={'max_candidates':2})
        self.assertEqual(caught.exception.diagnostic['reason'],'CANDIDATES_BUDGET')
        self.assertEqual(caught.exception.diagnostic['work']['candidates'],2)
        self.assertTrue(caught.exception.diagnostic['initial_check']['necessary_conflict_proved'])

    def test_triangle_budget_never_returns_partial_clearance_success(self):
        vertices,triangles=plane()
        with self.assertRaises(AttachmentClearanceRefused) as caught:
            check([0.,0.,10.],vertices,triangles*2,budgets={'max_triangle_visits':1})
        self.assertEqual(caught.exception.diagnostic['reason'],'TRIANGLE_VISITS_BUDGET')
        self.assertEqual(caught.exception.diagnostic['work']['triangle_visits'],1)
        self.assertEqual(caught.exception.diagnostic['qualification'],'NONE')

    def test_injected_time_interrupts_preparation_or_query_safely(self):
        vertices,triangles=plane(); ticks=iter([0.,0.,0.,0.,0.,1.])
        with self.assertRaises(AttachmentClearanceRefused) as caught:
            check_attachment_clearance(vertices,triangles,[0.,0.,.4],clearance_cm=.3,clock=lambda:next(ticks),budgets={'max_seconds':.5})
        self.assertEqual(caught.exception.diagnostic['reason'],'TIME_BUDGET')
        self.assertEqual(caught.exception.diagnostic['qualification'],'NONE')

    def test_external_interrupt_is_not_wrapped_or_swallowed(self):
        class Stop(Exception):pass
        error=Stop('shared solver deadline')
        def callback():raise error
        with self.assertRaises(Stop) as caught:
            propose(check_time=callback)
        self.assertIs(caught.exception,error)

    def test_invalid_values_geometry_budgets_and_provenance(self):
        cases=[lambda:check([0.,float('nan'),0.]),lambda:check([True,0.,0.]),
               lambda:check([0.,0.,1.],clearance_cm=float('inf')),
               lambda:propose(offset=[0.,0.,0.]),lambda:propose(search_step_cm=0.),
               lambda:check([0.,0.,1.],[[0.,0.,0.]],[[0,1,0]]),
               lambda:check([0.,0.,1.],[[0.,0.,0.]],[[0,False,0]]),
               lambda:check([0.,0.,1.],[],[]),
               lambda:check([0.,0.,1.],budgets={'max_triangle_visits':1.5}),
               lambda:check([0.,0.,1.],budgets={'max_candidates':True}),
               lambda:check([0.,0.,1.],budgets={'max_seconds':float('inf')}),
               lambda:check([0.,0.,1.],budgets={'unexpected':3}),
               lambda:check([0.,0.,1.],provenance={'bad':float('nan')})]
        for index,call in enumerate(cases):
            with self.subTest(case=index), self.assertRaises(AttachmentClearanceRefused):call()

    def test_batch_budget_retains_completed_evidence(self):
        vertices,triangles=plane()
        with self.assertRaises(AttachmentClearanceRefused) as caught:
            check_attachment_clearances(vertices,triangles,[[0.,0.,.1],[0.,0.,.5]],clearance_cm=.3,
                                        budgets={'max_triangle_visits':1},clock=lambda:0.)
        d=caught.exception.diagnostic
        self.assertEqual(d['checked_count'],1)
        self.assertEqual(d['conflict_count'],1)
        self.assertEqual(d['completed_checks'][0]['status'],'FIXED_TARGET_CLEARANCE_CONFLICT')

    def test_identity_covers_body_target_and_provenance(self):
        original=check([0.,0.,.5],provenance={'path':'A'})
        moved=check([0.,0.,.6],provenance={'path':'A'})
        source=check([0.,0.,.5],provenance={'path':'B'})
        self.assertNotEqual(original['inputs_sha256'],moved['inputs_sha256'])
        self.assertNotEqual(original['provenance_sha256'],source['provenance_sha256'])
        self.assertEqual(original['body_geometry_sha256'],moved['body_geometry_sha256'])

    def test_nonrepresentable_integer_plane_cannot_create_false_clearance(self):
        # The declared distance is exactly 1, not the 2 produced by rounding a.
        a=2**53+1
        vertices=[[a,-2,0],[a,2,0],[a,0,2]]; target=[a+1,0,1]
        before=copy.deepcopy((vertices,target))
        with self.assertRaises(AttachmentClearanceRefused) as caught:
            check(target,vertices,[[0,1,2]],clearance_cm=1.5)
        self.assertEqual(caught.exception.diagnostic['reason'],'INTEGER_NOT_EXACT_BINARY64')
        self.assertEqual(caught.exception.diagnostic['field'],'body_vertex')
        self.assertEqual((vertices,target),before)

    def test_nonrepresentable_integer_coordinates_and_scalars_are_refused(self):
        bad=2**53+1
        cases=[('target_world_cm',lambda:check([bad,0,1])),
               ('path_anchor_world_cm',lambda:propose(anchor=[bad,0,0])),
               ('offset_world_cm',lambda:propose(offset=[0,0,bad])),
               ('clearance_cm',lambda:check([0,0,1],clearance_cm=bad)),
               ('safety_margin_cm',lambda:check([0,0,1],safety_margin_cm=bad)),
               ('max_added_displacement_cm',lambda:propose(max_added_displacement_cm=bad)),
               ('search_step_cm',lambda:propose(search_step_cm=bad))]
        for name,call in cases:
            with self.subTest(field=name),self.assertRaises(AttachmentClearanceRefused) as caught:
                call()
            self.assertEqual(caught.exception.diagnostic['reason'],'INTEGER_NOT_EXACT_BINARY64')
            self.assertEqual(caught.exception.diagnostic['field'],name)

    def test_exactly_representable_large_integers_and_binary64_body_are_supported(self):
        a=2**53
        vertices=[[a,-2,0],[a,2,0],[a,0,2]]
        integer=check([a+2,0,1],vertices,[[0,1,2]],clearance_cm=1.5)
        binary64=check([float(a+2),0.,1.],[[float(x) for x in p] for p in vertices],[[0,1,2]],clearance_cm=1.5)
        self.assertEqual(integer['status'],'CLEARANCE_VERIFIED')
        self.assertEqual(integer['certificate'],binary64['certificate'])
        # Ordinary body coordinates continue through the same exact distance path.
        self.assertEqual(check([.1,.2,.4])['status'],'CLEARANCE_VERIFIED')


if __name__=='__main__':
    unittest.main()
