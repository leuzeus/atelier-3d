"""Portable tests for bounded regular seeds; no Blender qualification."""
import copy
import json
import unittest
from a3d.core import StudioError,digest
from a3d.pattern_preparation import regular_interior_points

class Envelope:
    material_controls={"panel":0}
    def __init__(self,limit=1000000,stop_phase=None,mutate=None):
        self.limit=limit;self.stop_phase=stop_phase;self.mutate=mutate
        self.phases=[];self.work=0;self.owners=[]
    def check(self,phase):
        self.phases.append(phase)
        if self.mutate is not None:self.mutate(phase)
        if phase==self.stop_phase:
            raise StudioError("Cooperative deadline")
    def reserve(self,kind,count,*,owner):
        if kind!="work_steps" or owner!="panel":raise AssertionError("Wrong ledger")
        self.owners.append(owner)
        self.work+=count
        if self.work>self.limit:raise StudioError("Work budget")

class BoundedRegularGrid(unittest.TestCase):
    config={"spacing_cm":2.,"min_spacing_cm":.5,"refinement_distance_cm":.5,"max_vertices":4000}
    boundary={"piece_id":"panel","polygon":[[0,0],[12,0],[12,8],[0,8]]}
    def test_same_exact_points_report_and_source_as_legacy(self):
        for polygon in (self.boundary["polygon"],
                [[-6,-4],[6,-4],[6,1],[0,1],[0,4],[-6,4]],
                [[0,0],[2,0],[5,0],[9,0],[12,0],[12,4],[12,8],[6,8],[0,8],[0,4]]):
            boundary={"piece_id":"panel","polygon":copy.deepcopy(polygon)}
            before=digest([boundary,self.config]);env=Envelope()
            expected,old=regular_interior_points(boundary,self.config)
            points,report=regular_interior_points(boundary,self.config,meshing_envelope=env)
            self.assertEqual(points,expected)
            self.assertEqual({k:v for k,v in report.items() if k not in ("query_work","query_policy")},old)
            self.assertEqual(before,digest([boundary,self.config]))
            self.assertGreater(env.work,0);self.assertEqual(set(env.owners),{"panel"})
            self.assertEqual(report["qualification"],"NONE")
    def test_stop_during_queries_refuses_before_return(self):
        env=Envelope(stop_phase="regular_grid:source_query")
        with self.assertRaisesRegex(StudioError,"Cooperative deadline"):
            regular_interior_points(copy.deepcopy(self.boundary),self.config,meshing_envelope=env)
        self.assertNotIn("regular_grid:final_return",env.phases)
    def test_stop_at_final_return_is_not_success(self):
        env=Envelope(stop_phase="regular_grid:final_return")
        with self.assertRaisesRegex(StudioError,"Cooperative deadline"):
            regular_interior_points(copy.deepcopy(self.boundary),self.config,meshing_envelope=env)

    def test_stop_during_source_validation_is_not_deferred_to_queries(self):
        env=Envelope(stop_phase='regular_grid:source_validation')
        with self.assertRaisesRegex(StudioError,'Cooperative deadline'):
            regular_interior_points(copy.deepcopy(self.boundary),self.config,meshing_envelope=env)
        self.assertNotIn('regular_grid:source_query',env.phases)

    def test_simple_polygon_optional_work_keeps_predicates_and_debits_rows(self):
        from a3d.board_contract import simple_polygon
        for polygon in (self.boundary['polygon'],[[0,0],[8,8],[0,8],[8,0]]):
            costs=[]
            self.assertEqual(simple_polygon(polygon),simple_polygon(polygon,work=costs.append))
            self.assertEqual(costs[0],len(polygon))
        costs=[]
        simple_polygon(self.boundary['polygon'],work=costs.append)
        self.assertEqual(costs,[4,3,2,1,0])
    def test_work_budget_is_not_refunded(self):
        env=Envelope(limit=0)
        with self.assertRaisesRegex(StudioError,"Work budget"):
            regular_interior_points(copy.deepcopy(self.boundary),self.config,meshing_envelope=env)
        self.assertGreater(env.work,0)
    def test_source_mutation_at_last_clock_check_refused(self):
        boundary=copy.deepcopy(self.boundary)
        env=Envelope(mutate=lambda phase:boundary["polygon"][0].__setitem__(0,-1)
                     if phase=="regular_grid:final_return" else None)
        with self.assertRaisesRegex(StudioError,"immutable source"):
            regular_interior_points(boundary,self.config,meshing_envelope=env)
    def test_reserved_owner_required(self):
        with self.assertRaisesRegex(StudioError,"reserved source owner"):
            regular_interior_points({"polygon":self.boundary["polygon"]},self.config,meshing_envelope=Envelope())
    def test_non_simple_contour_not_repaired(self):
        boundary={"piece_id":"panel","polygon":[[0,0],[8,8],[0,8],[8,0]]}
        with self.assertRaisesRegex(StudioError,"non-simple"):
            regular_interior_points(boundary,self.config,meshing_envelope=Envelope())
    def test_no_implicit_bounded_option_or_extra_receipt_fields(self):
        points,report=regular_interior_points(copy.deepcopy(self.boundary),self.config)
        self.assertTrue(points)
        self.assertNotIn("query_work",report)
        self.assertNotIn("query_policy",report)

    def test_failure_observation_excludes_native_candidate_objects(self):
        from blender.pattern_preparation import meshing_partial_diagnostic
        error=StudioError('Expired')
        error.bounded_meshing_partial={'qualification':'NONE','admission':'NONE',
            'active_piece':'panel','interior_grid':{'qualification':'NONE'},
            'best_safe_candidate':{'native_vector':object()},
            'last_completed_work_snapshot':{'cdt_calls':2},
            'snapshot_scope':'LAST_COMPLETED_CHECKPOINT_NOT_FINAL_WORK_LEDGER',
            'costs_refunded':False}
        result=meshing_partial_diagnostic(error)
        self.assertTrue(result['best_safe_candidate_recorded_in_exception'])
        self.assertNotIn('best_safe_candidate',result)
        self.assertFalse(result['candidate_admitted'])
        self.assertEqual(result['active_piece'],'panel')
        json.dumps(result,allow_nan=False)

if __name__=="__main__":unittest.main()
