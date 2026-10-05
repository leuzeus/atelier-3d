"""Portable Vector/CDT fixtures. No Blender process or real garment replay."""
import ast
import copy
import hashlib
import json
import math
from pathlib import Path
import struct
import sys
import types
import unittest
from unittest.mock import patch
from a3d.core import StudioError
from a3d.meshing_envelope import MeshingEnvelope
from blender import bounded_pattern_meshing as mesh


def frozen_kernel_text():
    value=json.loads((Path(__file__).parent/'data/native-shared-reference-v4.json').read_bytes())
    raw=value['source_utf8'].encode('utf-8')
    if hashlib.sha256(raw).hexdigest()!=mesh.FROZEN_KERNEL_SHA256:
        raise AssertionError('Historical kernel fixture must retain its exact frozen bytes')
    return raw.decode('utf-8')


class Vector32:
    def __init__(self, values):
        self.v=tuple(struct.unpack('!f',struct.pack('!f',float(x)))[0] for x in values)
    def __iter__(self):return iter(self.v)
    def __len__(self):return len(self.v)
    def __getitem__(self,i):return self.v[i]
    @property
    def x(self):return self.v[0]
    @property
    def y(self):return self.v[1]
    def __add__(self,x):return Vector32(a+b for a,b in zip(self,x))
    def __radd__(self,x):return self if x==0 else self+x
    def __sub__(self,x):return Vector32(a-b for a,b in zip(self,x))
    def __mul__(self,x):return Vector32(a*x for a in self)
    def __truediv__(self,x):return Vector32(a/x for a in self)
    def __neg__(self):return Vector32(-a for a in self)
    def __eq__(self,x):return isinstance(x,Vector32)and self.v==x.v
    def dot(self,x):return sum(a*b for a,b in zip(self,x))


def inputs(target=15.,charge=0,piece='generic-panel'):
    polygon=[[0.,0.],[4.,0.],[4.,2.],[0.,2.]]
    boundary={'piece_id':piece,'polygon':polygon,'source':copy.deepcopy(polygon),'flip':False,
              'source_sha256':'explicit-fixture-only','sample_provenance':[]}
    recipe={'mesh':{'spacing_cm':1.,'max_vertices':30000,'min_edge_cm':.001,
                   'min_angle_degrees':15.,'quality_refinement':{'max_passes':8,'max_added_vertices':4000}}}
    regular={'min_spacing_cm':1.,'max_vertices':30000,'target_min_angle_degrees':target}
    env=MeshingEnvelope('generic-component',{'attempted_insertions':4000,'native_cdt_calls':90,
       'native_remesh_attempts':80,'native_point_slots':2700000},
       owner_limits={'attempted_insertions':4000,'native_cdt_calls':9,'native_remesh_attempts':8},clock=lambda:0.)
    env.observe_material_controls('generic-component',{piece:[['explicit-material',i]for i in range(charge)]})
    return boundary,recipe,regular,env


class Backend:
    def __init__(self,provider=None):self.inputs=[];self.provider=provider
    def __call__(self,points,edges,faces,kind,epsilon,need_ids):
        self.inputs.append([list(p)for p in points])
        coords=[list(p)for p in points];origins=[[i]for i in range(len(points))]
        triangles=[[0,1,2],[0,2,3]]
        if self.provider:coords,triangles,origins=self.provider(coords,len(self.inputs))
        return [Vector32(p)for p in coords],[],triangles,origins,[],[]


class SuppliedNativeFixtures:
    def __init__(self,backend):self.backend=backend
    def __enter__(self):
        mathutils=types.ModuleType('mathutils');mathutils.Vector=Vector32
        geometry=types.ModuleType('mathutils.geometry');geometry.delaunay_2d_cdt=self.backend
        mathutils.geometry=geometry
        self.mods=patch.dict(sys.modules,{'mathutils':mathutils,'mathutils.geometry':geometry})
        self.grid=patch('a3d.pattern_preparation.regular_interior_points',return_value=([],{}))
        self.mods.__enter__();self.grid.__enter__();return self.backend
    def __exit__(self,*args):self.grid.__exit__(*args);self.mods.__exit__(*args)


def unchanged_conditioner(vertices,faces,anchors,**kwargs):
    if 'check'in kwargs:kwargs['check']('fixture_conditioner')
    return copy.deepcopy(vertices),{'target_reached':False,'fixture':True}


class BoundedMeshing(unittest.TestCase):
    def test_simple_target_is_numerical_only_and_source_immutable(self):
        boundary,recipe,regular,env=inputs(charge=2)
        before=copy.deepcopy((boundary,recipe,regular))
        backend=Backend()
        with SuppliedNativeFixtures(backend):coords,faces,mapping=mesh.triangulate(boundary,recipe,regular,envelope=env)
        report=boundary.pop('preparation_refinement')
        self.assertEqual((boundary,recipe,regular),before)
        self.assertEqual(coords,boundary['polygon']);self.assertEqual(mapping,{i:i for i in range(4)})
        self.assertEqual(report['status'],'TARGET_REACHED');self.assertEqual(report['qualification'],'NONE')
        self.assertEqual(report['admission'],'NONE');self.assertFalse(report['physical_mesh_qualified'])
        self.assertEqual(env.snapshot()['work']['attempted_insertions'],2)
        self.assertEqual(env.snapshot()['work']['native_cdt_calls'],1)
        self.assertEqual(env.snapshot()['work']['native_point_slots'],4)
        self.assertEqual(report['conditioned_point_transport']['work']['attempted_insertions'],2)

    def test_rollback_restores_every_table_but_not_work(self):
        boundary,recipe,regular,env=inputs(target=45.)
        def provider(points,call):
            if call==1:return points,[[0,1,2],[0,2,3]],[[i]for i in range(4)]
            points[4]=[points[4][0]+.3,points[4][1]]
            return points,[[0,1,4],[1,2,4],[2,3,4],[3,0,4]],[[i]for i in range(5)]
        backend=Backend(provider)
        with SuppliedNativeFixtures(backend),patch.object(mesh,'improve_interior',unchanged_conditioner):
            coords,faces,mapping=mesh.triangulate(boundary,recipe,regular,envelope=env)
        report=boundary['preparation_refinement'];work=env.snapshot()['work']
        self.assertEqual(coords,boundary['polygon']);self.assertEqual(faces,[[0,1,2],[0,2,3]])
        self.assertEqual(mapping,{i:i for i in range(4)})
        self.assertEqual(report['refusal'],'NON_MONOTONIC_REFINEMENT_ROLLED_BACK')
        self.assertEqual(report['added_vertices'],0);self.assertEqual(report['passes'],0)
        self.assertEqual(report['conditioned_point_transport']['final']['input_count'],4)
        self.assertEqual(report['conditioned_point_transport']['final']['births_sha256'],mesh._pool_digest(backend.inputs[0]))
        self.assertEqual(work['native_cdt_calls'],2);self.assertEqual(work['native_remesh_attempts'],1)
        self.assertEqual(work['attempted_insertions'],1);self.assertEqual(work['native_point_slots'],9)
        self.assertFalse(report['costs_refunded'])
        self.assertEqual(report['conditioned_point_transport']['work']['attempted_insertions'],1)

    def test_alias_after_remesh_restores_best_without_extra_cdt(self):
        boundary,recipe,regular,env=inputs(target=45.)
        def provider(points,call):
            origins=[[i]for i in range(len(points))]
            if call==2:origins[0]=[0,4]
            return points,[[0,1,2],[0,2,3]],origins
        backend=Backend(provider)
        with SuppliedNativeFixtures(backend),patch.object(mesh,'improve_interior',unchanged_conditioner):
            coords,faces,mapping=mesh.triangulate(boundary,recipe,regular,envelope=env)
        self.assertEqual(coords,boundary['polygon']);self.assertEqual(len(backend.inputs),2)
        report=boundary['preparation_refinement']
        self.assertEqual(report['refusal'],'AMBIGUOUS_INPUT_IDENTITY')
        self.assertEqual(report['conditioned_point_transport']['final']['input_count'],4)
        self.assertEqual(env.snapshot()['work']['attempted_insertions'],1)

    def test_first_alias_is_refused_before_conditioner(self):
        boundary,recipe,regular,env=inputs()
        def provider(p,c):return p,[[0,1,2],[0,2,3]],[[0,1],[1],[2],[3]]
        with SuppliedNativeFixtures(Backend(provider)),patch.object(mesh,'improve_interior')as conditioner:
            with self.assertRaises(mesh.ConditionedPointRefusal)as caught:mesh.triangulate(boundary,recipe,regular,envelope=env)
        self.assertEqual(caught.exception.reason,'AMBIGUOUS_INPUT_IDENTITY')
        self.assertFalse(conditioner.called)
        self.assertIsNone(caught.exception.bounded_meshing_partial['best_safe_candidate'])
        self.assertNotIn('preparation_refinement',boundary)

    def test_source_restore_refuses_shift_beyond_existing_bound(self):
        boundary,recipe,regular,env=inputs()
        def provider(p,c):p[0]=[.01,0];return p,[[0,1,2],[0,2,3]],[[i]for i in range(4)]
        with SuppliedNativeFixtures(Backend(provider)),patch.object(mesh,'improve_interior',unchanged_conditioner):
            with self.assertRaises(StudioError):mesh.triangulate(boundary,recipe,regular,envelope=env)

    def test_exact_protected_anchor_restored_after_binary32(self):
        b,r,g,e=inputs();b['polygon'][0]=[.10000000000000003,0.];b['source']=copy.deepcopy(b['polygon'])
        with SuppliedNativeFixtures(Backend()):coords,_,_=mesh.triangulate(b,r,g,envelope=e)
        self.assertEqual(coords[0],b['polygon'][0])
        self.assertNotEqual(list(Vector32(b['polygon'][0])),b['polygon'][0])

    def test_winding_flip_matches_existing_rule(self):
        b,r,g,e=inputs();b['flip']=True
        with SuppliedNativeFixtures(Backend()):_,faces,_=mesh.triangulate(b,r,g,envelope=e)
        self.assertEqual(faces,[[2,1,0],[3,2,0]])

    def test_owner_must_be_explicit_and_precharged(self):
        for mode in('missing_id','missing_charge'):
            b,r,g,e=inputs()
            if mode=='missing_id':b.pop('piece_id')
            else:b['piece_id']='unobserved'
            with self.assertRaises(mesh.ConditionedPointRefusal):mesh.triangulate(b,r,g,envelope=e)
            self.assertEqual(e.snapshot()['work']['native_cdt_calls'],0)

    def test_same_owner_cannot_reset_births_or_work_in_envelope(self):
        b,r,g,e=inputs()
        with SuppliedNativeFixtures(Backend()):mesh.triangulate(b,r,g,envelope=e)
        old=copy.deepcopy(e.snapshot()['work'])
        with self.assertRaises(mesh.ConditionedPointRefusal)as caught:mesh.triangulate(b,r,g,envelope=e)
        self.assertEqual(caught.exception.reason,'PIECE_WORK_ALREADY_STARTED_NO_BIRTH_RESET')
        self.assertEqual(e.snapshot()['work'],old)

    def test_no_local_clock_and_no_external_alias_or_hardcoded_component(self):
        text=Path(mesh.__file__).read_text(encoding='utf8');tree=ast.parse(text)
        self.assertNotIn('_shared_birth_refiner',text)
        self.assertNotIn('sys.modules',text)
        self.assertNotIn('garment.coat',text)
        self.assertNotIn('time.monotonic',text)
        self.assertNotIn('perf_counter',text)
        self.assertFalse(any(isinstance(n,ast.Call)and isinstance(n.func,ast.Name)and n.func.id=='MeshingEnvelope'for n in ast.walk(tree)))

    def test_historical_piece_caps_may_not_be_relaxed(self):
        for field,value in(('max_passes',9),('max_added_vertices',4001)):
            b,r,g,e=inputs();r['mesh']['quality_refinement'][field]=value
            with self.assertRaises(mesh.ConditionedPointRefusal):mesh.triangulate(b,r,g,envelope=e)
        b,r,g,e=inputs();g['min_spacing_cm']=2.
        with self.assertRaises(mesh.ConditionedPointRefusal):mesh.triangulate(b,r,g,envelope=e)

    def test_stall_does_not_resubmit_unchanged_pool(self):
        b,r,g,e=inputs(target=45.);r['mesh']['quality_refinement']['max_added_vertices']=0
        with SuppliedNativeFixtures(Backend())as backend,patch.object(mesh,'improve_interior',unchanged_conditioner):
            mesh.triangulate(b,r,g,envelope=e)
        self.assertEqual(len(backend.inputs),1)
        self.assertEqual(e.snapshot()['work']['native_remesh_attempts'],0)
        self.assertEqual(b['preparation_refinement']['status'],'NEEDS_CORRECTION')

    def test_component_insertions_do_not_multiply_per_piece(self):
        b,r,g,e=inputs(target=45.,charge=2)
        e.limits=types.MappingProxyType({**e.limits,'attempted_insertions':2})
        with SuppliedNativeFixtures(Backend())as backend,patch.object(mesh,'improve_interior',unchanged_conditioner):
            mesh.triangulate(b,r,g,envelope=e)
        self.assertEqual(e.snapshot()['work']['attempted_insertions'],2)
        self.assertEqual(e.snapshot()['work']['native_cdt_calls'],1)
        self.assertEqual(b['preparation_refinement']['status'],'NEEDS_CORRECTION')

    def test_point_slot_component_refusal_before_cdt_preserves_other_debits(self):
        b,r,g,e=inputs(charge=2)
        e.limits=types.MappingProxyType({**e.limits,'native_point_slots':3})
        with SuppliedNativeFixtures(Backend())as backend:
            with self.assertRaises(StudioError):mesh.triangulate(b,r,g,envelope=e)
        self.assertEqual(backend.inputs,[])
        self.assertEqual(e.snapshot()['work']['attempted_insertions'],2)

    def test_expiration_after_reservation_keeps_debit_no_cdt(self):
        b,r,g,e=inputs();e.stop_requested=lambda:e.phase=='after_reserve:native_cdt_calls'
        with SuppliedNativeFixtures(Backend())as backend:
            with self.assertRaises(StudioError):mesh.triangulate(b,r,g,envelope=e)
        e.stop_requested=None
        self.assertEqual(backend.inputs,[])
        self.assertEqual(e.snapshot()['work']['native_cdt_calls'],1)
        self.assertEqual(e.snapshot()['work']['native_point_slots'],4)

    def test_conditioner_cooperative_stop_has_no_success_report(self):
        b,r,g,e=inputs();e.stop_requested=lambda:e.phase.startswith('interior_refinement:')
        with SuppliedNativeFixtures(Backend()):
            with self.assertRaises(StudioError):mesh.triangulate(b,r,g,envelope=e)
        self.assertNotIn('preparation_refinement',b)

    def test_stop_after_best_preserves_complete_snapshot_on_exception(self):
        b,r,g,e=inputs(target=45.)
        e.stop_requested=lambda:e.phase=='bounded_meshing:insertion_candidate'
        with SuppliedNativeFixtures(Backend()),patch.object(mesh,'improve_interior',unchanged_conditioner):
            with self.assertRaises(StudioError)as caught:mesh.triangulate(b,r,g,envelope=e)
        partial=caught.exception.bounded_meshing_partial
        self.assertEqual(partial['qualification'],'NONE')
        self.assertEqual(partial['best_safe_candidate']['coordinates'],b['polygon'])
        self.assertEqual(partial['best_safe_candidate']['births'],b['polygon'])
        self.assertIn('triangulation',partial['best_safe_candidate'])
        self.assertEqual(partial['snapshot_scope'],'LAST_COMPLETED_CHECKPOINT_NOT_FINAL_WORK_LEDGER')

    def test_stop_at_final_return_cannot_publish_target_report(self):
        b,r,g,e=inputs();e.stop_requested=lambda:e.phase=='bounded_meshing:final_return'
        with SuppliedNativeFixtures(Backend()):
            with self.assertRaises(StudioError):mesh.triangulate(b,r,g,envelope=e)
        self.assertNotIn('preparation_refinement',b)

    def test_mutated_recipe_refuses_even_after_target_geometry(self):
        b,r,g,e=inputs()
        def conditioner(v,f,a,**kwargs):r['mesh']['min_edge_cm']=.002;return unchanged_conditioner(v,f,a,**kwargs)
        with SuppliedNativeFixtures(Backend()),patch.object(mesh,'improve_interior',conditioner):
            with self.assertRaises(mesh.ConditionedPointRefusal)as caught:mesh.triangulate(b,r,g,envelope=e)
        self.assertEqual(caught.exception.reason,'SOURCE_OR_RECIPE_MUTATED')

    def test_actual_deadline_before_capture_does_not_start_native(self):
        b,r,g,e=inputs();e.clock=lambda:90.
        with SuppliedNativeFixtures(Backend())as backend:
            with self.assertRaises(StudioError)as caught:mesh.triangulate(b,r,g,envelope=e)
        self.assertEqual(caught.exception.reason,'DEADLINE_EXHAUSTED')
        self.assertEqual(backend.inputs,[])
        self.assertNotIn('preparation_refinement',b)

    def test_actual_deadline_after_cdt_has_no_conditioner_or_report(self):
        b,r,g,e=inputs()
        e.clock=lambda:90. if e.phase=='bounded_meshing:after_cdt'else 0.
        with SuppliedNativeFixtures(Backend())as backend,patch.object(mesh,'improve_interior')as conditioner:
            with self.assertRaises(StudioError)as caught:mesh.triangulate(b,r,g,envelope=e)
        self.assertEqual(caught.exception.reason,'DEADLINE_EXHAUSTED')
        self.assertEqual(len(backend.inputs),1)
        self.assertFalse(conditioner.called)
        self.assertEqual(e._counts['native_cdt_calls'],1)
        self.assertNotIn('preparation_refinement',b)

    def test_actual_deadline_at_final_return_has_no_target_publication(self):
        b,r,g,e=inputs();e.clock=lambda:90. if e.phase=='bounded_meshing:final_return'else 0.
        with SuppliedNativeFixtures(Backend()):
            with self.assertRaises(StudioError)as caught:mesh.triangulate(b,r,g,envelope=e)
        self.assertEqual(caught.exception.reason,'DEADLINE_EXHAUSTED')
        self.assertNotIn('preparation_refinement',b)

    def test_work_caps_slots_calls_and_remesh_no_refund(self):
        b,r,g,e=inputs()
        work=mesh._EnvelopePointWork(e,b['piece_id'],1,2,5,0)
        pool=[Vector32(p)for p in b['polygon']]
        work.before_cdt(pool,[0,1,2,3])
        with self.assertRaises(mesh.ConditionedPointRefusal)as caught:work.before_cdt(pool,[0,1,2,3])
        self.assertEqual(caught.exception.reason,'UNCHANGED_CDT_INPUT_REFUSED')
        work.reserve_remesh(4,1)
        with self.assertRaises(mesh.ConditionedPointRefusal):work.reserve_remesh(5,1)
        pool.append(Vector32([2,1]));work.before_cdt(pool,[0,1,2,3])
        with self.assertRaises(mesh.ConditionedPointRefusal):work.before_cdt(pool+[Vector32([2,1.1])],[0,1,2,3])
        stats=e.snapshot()['work']
        self.assertEqual(stats['native_cdt_calls'],2)
        self.assertEqual(stats['native_point_slots'],9)
        self.assertEqual(stats['native_remesh_attempts'],1)
        self.assertEqual(stats['attempted_insertions'],1)

    def test_material_control_mapping_must_concord_with_paid_ledger(self):
        b,r,g,e=inputs(charge=2)
        e._owner_counts[b['piece_id']]['attempted_insertions']=0
        with self.assertRaises(mesh.ConditionedPointRefusal)as caught:mesh.triangulate(b,r,g,envelope=e)
        self.assertEqual(caught.exception.reason,'INITIAL_MATERIAL_CONTROL_LEDGER_CONTRADICTION')

    def test_frozen_v4_fixture_outputs_and_core_reports_remain_exact(self):
        tree=ast.parse(frozen_kernel_text())
        names={'ConditionedPointRefusal','_pool_digest','exact_input_association','validate_conditioned_pool',
               'PointWorkBudget','snapshot_candidate','restore_candidate','separated_from_transported',
               'final_quality_reached','_trace_conditioned','triangulate'}
        selected=[copy.deepcopy(n)for n in tree.body if getattr(n,'name',None)in names]
        class StaticReferenceImport(ast.NodeTransformer):
            def visit_ImportFrom(self,node):
                return None if node.module=='a3d._shared_birth_refiner'else node
        selected=[StaticReferenceImport().visit(n)for n in selected]
        namespace={'copy':copy,'math':math,'json':__import__('json'),'hashlib':hashlib,
                   'StudioError':StudioError,'distance':mesh.distance,'point_inside':mesh.point_inside,
                   'signed_area':mesh.signed_area,'segment_distance':mesh.segment_distance,
                   'improve_interior':mesh.improve_interior,'_CONDITIONED_POINT_TRACE':None}
        exec(compile(ast.fix_missing_locations(ast.Module(body=selected,type_ignores=[])),'frozen-kernel-fixture','exec'),namespace)
        for scenario in('target','rollback','alias'):
            with self.subTest(scenario=scenario):
                target=15. if scenario=='target'else 45.
                old,r,g,_=inputs(target=target,charge=2)
                new,_,_,e=inputs(target=target,charge=2)
                def provider(points,call):
                    if call==1:return points,[[0,1,2],[0,2,3]],[[i]for i in range(4)]
                    points[4]=[points[4][0]+.3,points[4][1]]
                    origins=[[i]for i in range(5)]
                    if scenario=='alias':origins[0]=[0,4]
                    return points,[[0,1,4],[1,2,4],[2,3,4],[3,0,4]],origins
                conditioner=mesh.improve_interior if scenario=='target'else unchanged_conditioner
                namespace['improve_interior']=conditioner
                with SuppliedNativeFixtures(Backend(provider)):
                    reference=namespace['triangulate'](old,r,g,_initial_derived_boundary_insertions=2)
                with SuppliedNativeFixtures(Backend(provider)),patch.object(mesh,'improve_interior',conditioner):
                    current=mesh.triangulate(new,r,g,envelope=e)
                self.assertEqual(reference,current)
                original_report=old['preparation_refinement']
                candidate_report={key:new['preparation_refinement'][key]for key in original_report}
                self.assertEqual(original_report,candidate_report)


class Safeguards(unittest.TestCase):
    def test_singleton_input_ids_and_permutation(self):
        self.assertEqual(mesh.exact_input_association([[2],[0],[1]],3,3),{2:0,0:1,1:2})
        for origins in ([[0,1],[1]],[[0],[0]],[[True],[1]],[[0],[3]],[[0]]):
            with self.assertRaises(mesh.ConditionedPointRefusal):mesh.exact_input_association(origins,2,len(origins))

    def test_binary32_transport_not_nominal_coordinates_alone(self):
        polygon=[[0,0],[1,0],[1,1],[0,1]];points=polygon+[[.25,.25]]
        coords=polygon+[[.74999999,.2501]]
        self.assertLessEqual(math.dist(coords[4],points[4]),.5)
        self.assertGreater(math.dist(list(Vector32(coords[4])),points[4]),.5)
        with self.assertRaises(mesh.ConditionedPointRefusal)as caught:
            mesh.validate_conditioned_pool([Vector32(p)for p in points],points,coords,[[i]for i in range(5)],
                [[0,1,4],[1,2,4],[2,3,4],[3,0,4]],polygon,Vector32,mesh.point_inside,mesh.signed_area,.5)
        self.assertEqual(caught.exception.reason,'CUMULATIVE_DISPLACEMENT_BUDGET_EXCEEDED')

    def test_protected_anchor_and_transported_collapse_refused(self):
        p=[[0,0],[1,0],[1,1],[0,1]];coords=copy.deepcopy(p);coords[0]=[.001,0]
        with self.assertRaises(mesh.ConditionedPointRefusal):
            mesh.validate_conditioned_pool([Vector32(v)for v in p],p,coords,[[i]for i in range(4)],
                [[0,1,2],[0,2,3]],p,Vector32,mesh.point_inside,mesh.signed_area,.5)

    def test_snapshot_is_complete_independent_without_counters(self):
        state=mesh.snapshot_candidate([[0,0]],[],[[0,1,2]],[[0]],[[0,0]],{0:0},{'a':1},[[0,0]],[[0,0]],2,1,10.,.1)
        copy1=mesh.restore_candidate(state);copy1['points'][0][0]=5
        self.assertEqual(state['points'],[[0,0]])
        self.assertNotIn('work',state)
        self.assertEqual(set(state),{'triangulation','coordinates','mapping','smoothing','points','births','added_vertices','passes','min_angle_degrees','min_edge_cm'})

    def test_stable_separation_uses_transported_pool(self):
        self.assertFalse(mesh.separated_from_transported([0,0],[[.01,0]],[],.02,math.dist))
        self.assertTrue(mesh.separated_from_transported([0,0],[[.02,0]],[],.02,math.dist))

    def test_no_target_promotion_after_transport_refusal(self):
        self.assertFalse(mesh.final_quality_reached([[0,1,2]],20.,.1,15.,.001,{'reason':'x'}))

    def test_frozen_numeric_helpers_ast_exact_except_checkpoints(self):
        old={n.name:n for n in ast.parse(frozen_kernel_text()).body if isinstance(n,(ast.FunctionDef,ast.ClassDef))}
        current={n.name:n for n in ast.parse(Path(mesh.__file__).read_text(encoding='utf8')).body if isinstance(n,(ast.FunctionDef,ast.ClassDef))}
        for name in ('ConditionedPointRefusal','_pool_digest','exact_input_association','snapshot_candidate','restore_candidate','separated_from_transported','final_quality_reached'):
            self.assertEqual(ast.dump(old[name],include_attributes=False),ast.dump(current[name],include_attributes=False),name)
        class StripCheck(ast.NodeTransformer):
            def visit_If(self,node):
                if isinstance(node.test,ast.Compare)and isinstance(node.test.left,ast.Name)and node.test.left.id=='check':return None
                return self.generic_visit(node)
        candidate=StripCheck().visit(copy.deepcopy(current['validate_conditioned_pool']))
        candidate.args.args.pop();candidate.args.defaults.pop()
        self.assertEqual(ast.dump(old['validate_conditioned_pool'],include_attributes=False),ast.dump(candidate,include_attributes=False))


if __name__=='__main__':unittest.main()
