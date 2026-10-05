"""Portable source-bound fixtures; no CDT, Blender, physical or product gate."""
import copy
import json
import math
import struct
import unittest
from unittest.mock import patch

from a3d import boundary_gradation as g
from a3d.core import StudioError, digest
from a3d.meshing_envelope import MeshingEnvelope
from a3d.pattern_preparation import prepare_regular_boundaries, _bind_source_notch
from a3d.sewing import prepare_boundaries
from tests.test_sewing import sources


def binary32(point):
    return [struct.unpack('f',struct.pack('f',x))[0] for x in point]


def fixture(reverse=False):
    _, recipe = sources()
    polygon = [[0.,0.],[.1,0.],[1.5,0.],[3.,0.],[3.,1.],[0.,1.]]
    piece = {'vertices':polygon,'faces':[[0,1,5],[1,2,5],[2,3,4],[2,4,5]],
        'edges':{'bottom':[0,1,2,3],'short':[0,1],'middle':[1,2],'long':[2,3],
                 'rest':[3,4,5,0]}}
    data = {'component_id':'garment.coat','units':'cm','pieces':{
        'left':copy.deepcopy(piece),'right':copy.deepcopy(piece)},'seams':[{
        'id':'join','piece_a':'left','piece_b':'right','edge_a':'bottom','edge_b':'bottom',
        'orientation':'reverse' if reverse else 'forward','kind':'permanent'}]}
    placement = copy.deepcopy(recipe['placements']['front'])
    recipe.update(component_id=data['component_id'],seams={'join':{
        'kind':'permanent','ease_b_over_a':0.,'tolerance_relative':.01}},
        placements={p:copy.deepcopy(placement) for p in data['pieces']},
        trial_pieces=list(data['pieces']),pins=[],colliders=[],no_collision_reason='Portable fixture')
    recipe['mesh'].update(spacing_cm=1.,max_vertices=1000,min_edge_cm=.001,
        max_boundary_error_cm=.01,quality_refinement={
            'max_passes':8,'max_added_vertices':4000,'target_min_angle_degrees':15.})
    regular = {'spacing_cm':2.,'min_spacing_cm':1.,'refinement_distance_cm':1.,
               'max_vertices':1000,'target_min_angle_degrees':15.}
    parts,seams,_ = prepare_regular_boundaries(data,recipe,regular)
    return data,recipe,regular,parts,seams


def envelope(data, overrides=None, clock=None, max_seconds=90.):
    limits = {'capture_nodes':500000,'capture_bytes':8*1024*1024,
              'output_nodes':500000,'output_bytes':8*1024*1024,
              'work_steps':100000000,'sampling_calls':20,'sampling_point_slots':20000,
              'fraction_requests':4000,'attempted_insertions':4000}
    limits.update(overrides or {})
    return MeshingEnvelope(data['component_id'],limits,clock=clock or (lambda:0.),max_seconds=max_seconds)


def call(items, env=None, transport=binary32):
    return g.grade_shared_boundaries(*items,transport_2d=transport,
        envelope=env or envelope(items[0]))


class BoundaryGradationTests(unittest.TestCase):
    def test_fixpoint_complete_inventory_old_samples_exact_and_no_admission(self):
        items=fixture();before=copy.deepcopy(items);env=envelope(items[0]);parts,seams,r=call(items,env)
        self.assertEqual(set(parts),set(items[3]));self.assertEqual(set(seams),set(items[4]))
        self.assertEqual(r['post_union_cascade']['iterations'][-1]['violations'],[])
        self.assertGreater(r['total_initial_charged_boundary_insertions'],0)
        self.assertEqual(r['total_initial_charged_boundary_insertions'],sum(env.material_controls.values()))
        self.assertEqual(r['qualification'],'NONE');self.assertEqual(r['native'],'NOT_EXECUTED')
        self.assertNotIn('READY',json.dumps(r));self.assertEqual(before,items)
        for pid,old in items[3].items():
            lookup=dict(zip(parts[pid]['keys'],parts[pid]['polygon']))
            self.assertTrue(all(lookup[key]==point for key,point in zip(old['keys'],old['polygon'])))
        self.assertTrue(set(items[4]['join']['parameters'])<=set(seams['join']['parameters']))

    def test_shared_envelope_replay_charges_calls_not_identical_controls(self):
        items=fixture();env=envelope(items[0]);a=call(items,env);count=env.snapshot()['work']
        b=call(items,env);later=env.snapshot()['work']
        self.assertEqual(a[:2],b[:2]);self.assertEqual(later['attempted_insertions'],count['attempted_insertions'])
        self.assertGreater(later['sampling_calls'],count['sampling_calls'])
        self.assertGreater(later['sampling_point_slots'],count['sampling_point_slots'])
        self.assertGreater(later['work_steps'],count['work_steps'])

    def test_reorder_has_same_geometry_and_journal(self):
        items=fixture();a=call(items);other=copy.deepcopy(items)
        other[3].update({})
        other=list(other);other[3]=dict(reversed(list(other[3].items())))
        b=call(other)
        self.assertEqual(a[:2],b[:2])
        self.assertEqual(a[2]['post_union_cascade']['journal'],b[2]['post_union_cascade']['journal'])

    def test_source_reorder_with_inconsistent_old_flip_gauge_refuses(self):
        items=list(fixture());items[0]['pieces']=dict(reversed(list(items[0]['pieces'].items())))
        with self.assertRaises(g.GradedBoundaryRefusal) as error:call(items)
        self.assertEqual(error.exception.reason,'AUTHORED_SOURCE_PROPERTY_CHANGED')

    def test_idempotence_on_the_new_prepared_boundaries(self):
        items=fixture();parts,seams,_=call(items)
        new=(*items[:3],parts,seams)
        second=call(new)
        self.assertEqual((parts,seams),second[:2])
        self.assertEqual(second[2]['total_initial_charged_boundary_insertions'],0)

    def test_reversed_partner_preserves_oriented_material_samples(self):
        items=fixture(True);parts,seams,r=call(items)
        self.assertEqual(r['qualification'],'NONE');row=seams['join']
        self.assertEqual(len(row['a']),len(row['b']))
        for a,b in zip(row['a'],row['b']):
            self.assertAlmostEqual(parts['left']['polygon'][a][0]+parts['right']['polygon'][b][0],3.)

    def test_partial_source_overlap_propagates_without_new_relation(self):
        items=list(fixture())
        data,recipe,regular=items[:3]
        # A partial overlap with exact integer stops exercises transitive
        # sampling without inventing a second owner for a graded small edge.
        piece={'vertices':[[0.,0.],[2.,0.],[4.,0.],[4.,2.],[0.,2.]],
            'faces':[[0,1,4],[1,2,3],[1,3,4]],
            'edges':{'bottom':[0,1,2],'middle':[1,2],'rest':[2,3,4,0]}}
        data['pieces']={p:copy.deepcopy(piece) for p in ('left','right')}
        data['pieces']['third']=copy.deepcopy(data['pieces']['left'])
        recipe['placements']['third']=copy.deepcopy(recipe['placements']['left'])
        data['seams'].append({'id':'partial','piece_a':'right','piece_b':'third',
            'edge_a':'middle','edge_b':'middle','orientation':'reverse','kind':'detachable'})
        recipe['seams']['partial']={'kind':'detachable','ease_b_over_a':0.,'tolerance_relative':.01}
        parts,seams,_=prepare_regular_boundaries(data,recipe,regular)
        before=digest(data)
        output=call((data,recipe,regular,parts,seams))
        self.assertEqual(set(output[1]),{'join','partial'});self.assertEqual(digest(data),before)
        self.assertEqual(output[1]['partial']['kind'],'detachable')

    def test_source_notch_material_uv_remains_exact_after_rebind(self):
        items=fixture();mark={'seam_id':'join','notch_id':'near-half','piece':'left','side':'a',
            'source_local_parameter':math.nextafter(.5,1.),'symbol':'triangle','source_mark':{
                'id':'near-half','seam_id':'join','position':math.nextafter(.5,1.),'symbol':'triangle'}}
        old=_bind_source_notch(items[0],items[3],items[4],mark)
        parts,seams,r=call(items);new=_bind_source_notch(items[0],parts,seams,mark)
        self.assertEqual(new['source_uv_cm'],old['source_uv_cm'])
        self.assertEqual(new['common_parameter'],old['common_parameter'])
        self.assertEqual(r['source_notch_rebind'],'CALLER_REQUIRED_ON_NEW_BOUNDARIES')

    def test_nearby_fractions_are_not_merged(self):
        items=fixture();seeds={'join':[.5,.50000001]}
        before=copy.deepcopy(seeds)
        with self.assertRaises(StudioError):
            prepare_boundaries(items[0],items[1],seam_parameters=seeds,regular_boundary_spacing_cm=1.)
        # The existing sampler refuses this tiny physical interval. Preserve
        # that localized refusal and the two requests instead of coalescing.
        self.assertEqual(before,seeds);self.assertEqual(len(set(seeds['join'])),2)
        env=envelope(items[0]);values=[.5,math.nextafter(.5,1.)]
        identities={'left':[{'source_sha256':'a'*64,'source_perimeter_key_cm':v} for v in values]}
        env.observe_material_controls(items[0]['component_id'],identities)
        self.assertEqual(env._counts['attempted_insertions'],2)

    def test_distinct_source_controls_alias_after_transport_refuses(self):
        with self.assertRaises(g.GradedBoundaryRefusal) as error:
            call(fixture(),transport=lambda p:[0.,0.])
        self.assertEqual(error.exception.reason,'DISTINCT_SOURCE_CONTROLS_ALIAS_AFTER_TRANSPORT')

    def test_transport_input_mutation_and_bad_outputs_refuse(self):
        def mutating(p):p[0]+=1;return p
        for transport in (mutating,lambda p:[math.nan,0.],lambda p:[True,0.],lambda p:[0.]):
            with self.subTest(transport=transport),self.assertRaises(g.GradedBoundaryRefusal):
                call(fixture(),transport=transport)

    def test_foreign_baseline_source_or_sample_or_seam_refuses(self):
        for action in ('source','point','seam','key'):
            items=list(fixture())
            if action=='source':items[3]['left']['source_sha256']='0'*64
            elif action=='point':items[3]['left']['polygon'][0][0]=.001
            elif action=='seam':items[4]['join']['kind']='closure'
            else:items[3]['left']['keys'][1]=items[3]['left']['keys'][0]
            with self.subTest(action=action),self.assertRaises(g.GradedBoundaryRefusal):call(items)

    def test_missing_mandatory_stop_refuses_before_new_sampling(self):
        items=list(fixture());row=items[3]['left'];index=row['polygon'].index([.1,0.])
        for key in ('polygon','keys','sample_provenance'):row[key].pop(index)
        with self.assertRaises(g.GradedBoundaryRefusal) as error:call(items)
        self.assertEqual(error.exception.reason,'MANDATORY_SOURCE_CORNER_OR_STOP_LOST')

    def test_malformed_shape_refuses_as_contract_not_raw_keyerror(self):
        items=list(fixture());del items[2]['min_spacing_cm']
        with self.assertRaises(g.GradedBoundaryRefusal) as error:call(items)
        self.assertEqual(error.exception.reason,'SOURCE_BOUNDARY_CONTRACT_REFUSED')

    def test_ambiguous_owner_refuses_without_relation_creation(self):
        items=list(fixture())
        data,recipe,regular=items[:3]
        data['seams'].append({**data['seams'][0],'id':'other','kind':'detachable'})
        recipe['seams']['other']={**recipe['seams']['join'],'kind':'detachable'}
        parts,seams,_=prepare_regular_boundaries(data,recipe,regular)
        with self.assertRaises(g.GradedBoundaryRefusal) as caught:
            call((data,recipe,regular,parts,seams))
        self.assertIn(caught.exception.reason,('AMBIGUOUS_SOURCE_SEAM_PARAMETER_OWNER',
            'MISSING_OR_AMBIGUOUS_DECLARED_SOURCE_OWNER'))

    def test_missing_partner_refuses_before_sampler(self):
        items=list(fixture());items[0]['seams'][0]['piece_b']='missing';items[4]['join']['piece_b']='missing'
        with self.assertRaises(g.GradedBoundaryRefusal) as caught:call(items)
        self.assertEqual(caught.exception.reason,'MISSING_DECLARED_SOURCE_PARTNER')

    def test_component_insertion_limit_does_not_multiply_by_piece(self):
        items=fixture();env=envelope(items[0],{'attempted_insertions':1})
        with self.assertRaises(StudioError):call(items,env)
        self.assertLessEqual(env._counts['attempted_insertions'],1)
        self.assertGreater(env._counts['work_steps'],0)
        self.assertGreater(env._counts['sampling_calls'],0)

    def test_sampling_reservations_precede_api_and_failed_work_is_not_refunded(self):
        items=fixture();env=envelope(items[0]);observed=[]
        def refused(*args,**kwargs):
            observed.append(copy.deepcopy(env._counts));raise StudioError('fixture sampler refused')
        with patch.object(g,'prepare_boundaries',refused),self.assertRaises(g.GradedBoundaryRefusal):call(items,env)
        self.assertGreater(observed[0]['sampling_calls'],0)
        self.assertGreater(observed[0]['sampling_point_slots'],0)
        self.assertGreater(env._counts['work_steps'],0)

    def test_material_debit_precedes_validation_and_survives_late_refusal(self):
        items=fixture();env=envelope(items[0]);original=g.prepare_boundaries
        calls=[0]
        def corrupt(*args,**kwargs):
            result=original(*args,**kwargs);calls[0]+=1
            if calls[0]==2:result[0]['left']['polygon'][0][0]=.001
            return result
        with patch.object(g,'prepare_boundaries',corrupt),self.assertRaises(g.GradedBoundaryRefusal):call(items,env)
        self.assertGreater(env._counts['attempted_insertions'],0)
        self.assertGreater(sum(env.material_controls.values()),0)

    def test_stagnation_is_refused_without_favorable_gate(self):
        items=fixture();env=envelope(items[0]);parameters={k:v['parameters'][:] for k,v in items[4].items()}
        with patch.object(g,'partition_distances',return_value=([1.4],{'qualification':'NONE'})),self.assertRaises(g.GradedBoundaryRefusal) as error:
            g.synchronized_parameters(items[0],items[1],items[2],items[3],items[4],parameters,
                lambda:env.check('fixture'),env)
        self.assertEqual(error.exception.reason,'POST_UNION_GRADATION_STAGNATION')

    def test_zero_caps_refuse_before_sampler_or_copy_consumption(self):
        for kind in ('capture_nodes','capture_bytes','work_steps','sampling_calls','sampling_point_slots','fraction_requests'):
            items=fixture();env=envelope(items[0],{kind:0})
            with self.subTest(kind=kind),self.assertRaises(StudioError),patch.object(g,'prepare_boundaries') as sampler:
                call(items,env)
            if kind!='fraction_requests':self.assertFalse(sampler.called)

    def test_whole_output_nodes_exact_and_minus_one(self):
        items=fixture();env=envelope(items[0]);parts,seams,r=call(items,env)
        nodes,size=g._shape({'boundaries':parts,'seams':seams,'report':r},lambda:None)
        self.assertEqual(env._counts['output_nodes'],nodes);self.assertEqual(env._counts['output_bytes'],size)
        self.assertEqual(size,len(json.dumps({'boundaries':parts,'seams':seams,'report':r},
            ensure_ascii=False,sort_keys=True,separators=(',',':'),allow_nan=False).encode('utf-8')))
        exact=envelope(items[0],{'output_nodes':nodes});call(items,exact)
        with self.assertRaises(StudioError):call(items,envelope(items[0],{'output_nodes':nodes-1}))

    def test_whole_output_utf8_byte_cap_fixed_point_and_minus_one(self):
        items=fixture();bound=8*1024*1024
        for _ in range(4):
            env=envelope(items[0],{'output_bytes':bound});call(items,env);measured=env._counts['output_bytes']
            if measured==bound:break
            bound=measured
        self.assertEqual(measured,bound)
        with self.assertRaises(StudioError):call(items,envelope(items[0],{'output_bytes':bound-1}))

    def test_expired_or_stopped_envelope_before_capture_refuses(self):
        items=fixture();time=[0.];env=envelope(items[0],clock=lambda:time[0],max_seconds=1.)
        time[0]=1.
        with self.assertRaises(StudioError) as error:call(items,env)
        self.assertEqual(error.exception.reason,'DEADLINE_EXHAUSTED');self.assertEqual(env._counts['capture_nodes'],0)
        env=envelope(items[0]);env.stop_requested=lambda:True
        with self.assertRaises(StudioError) as error:call(items,env)
        self.assertEqual(error.exception.reason,'STOP_REQUESTED')

    def test_expiry_in_sampler_preserves_attempted_work_and_cannot_return_success(self):
        items=fixture();time=[0.];env=envelope(items[0],clock=lambda:time[0],max_seconds=1.);original=g.prepare_boundaries
        calls=[0]
        def delayed(*args,**kwargs):
            result=original(*args,**kwargs);calls[0]+=1
            if calls[0]==2:time[0]=1.
            return result
        with patch.object(g,'prepare_boundaries',delayed),self.assertRaises(StudioError) as error:call(items,env)
        self.assertIn(error.exception.reason,('DEADLINE_EXHAUSTED','CALLER_STOP_OR_DEADLINE'))
        self.assertEqual(error.exception.status,'INCOMPLETE')
        self.assertGreater(env._counts['sampling_calls'],0);self.assertGreater(env._counts['fraction_requests'],0)

    def test_expiry_during_final_preservation_hash_refuses(self):
        items=fixture();time=[0.];env=envelope(items[0],clock=lambda:time[0],max_seconds=1.)
        original=g._preservation_hash;calls=[0]
        def late(value,check):
            result=original(value,check);calls[0]+=1
            if calls[0]==3:time[0]=1.
            return result
        with patch.object(g,'_preservation_hash',late),self.assertRaises(StudioError) as error:call(items,env)
        self.assertEqual(error.exception.reason,'DEADLINE_EXHAUSTED');self.assertGreater(env._counts['output_nodes'],0)

    def test_original_mutation_from_callback_refuses_and_return_has_no_alias(self):
        items=fixture();count=[0]
        def evil(point):
            count[0]+=1
            if count[0]==1:items[0]['units']='mm'
            return binary32(point)
        with self.assertRaises(g.GradedBoundaryRefusal) as error:call(items,transport=evil)
        self.assertEqual(error.exception.reason,'SOURCE_INPUT_MUTATION')
        items=fixture();before=copy.deepcopy(items);parts,seams,r=call(items)
        parts['left']['polygon'][0][0]=100;seams['join']['a'][0]=100;r['pieces'].clear()
        self.assertEqual(items,before)

    def test_structured_capture_refuses_cycles_nonfinite_subclasses_and_key_aliases(self):
        for extra in (math.inf,object(),{1:'number','1':'text'}):
            items=list(fixture());items[1]['extra']=extra
            with self.subTest(extra=type(extra)),self.assertRaises(g.GradedBoundaryRefusal):call(items)
        items=list(fixture());items[1]['loop']=items[1]
        with self.assertRaises(g.GradedBoundaryRefusal) as error:call(items)
        self.assertEqual(error.exception.reason,'CYCLIC_SOURCE_INPUT')

    def test_content_hash_is_bound_to_entire_geometry_and_report(self):
        parts,seams,r=call(fixture());claimed=r.pop('content_sha256')
        self.assertEqual(claimed,digest({'boundaries':parts,'seams':seams,'report':r}))
        parts['left']['polygon'][0][0]=.001
        self.assertNotEqual(claimed,digest({'boundaries':parts,'seams':seams,'report':r}))

    def test_no_local_clock_default_ledger_or_native_import(self):
        import ast
        from pathlib import Path
        tree=ast.parse(Path(g.__file__).read_text(encoding='utf-8'))
        modules=[n.module or '' for n in ast.walk(tree) if isinstance(n,ast.ImportFrom)]
        modules.extend(a.name for n in ast.walk(tree) if isinstance(n,ast.Import) for a in n.names)
        self.assertFalse(any(m.startswith(('bpy','mathutils','sqlite3','time','importlib')) for m in modules))


class SourceVertexSeamBindingTests(unittest.TestCase):
    """The source vertex's exact UV and existing key outrank re-interpolation.

    These synthetic bindings exercise only the baseline identity check; they
    do not resample the real garment or execute boundary grading/native code.
    """
    def identity(self, items, check=lambda:None):
        return g._source_identity(items[0],items[3],items[4],items[1],check)

    def neighbour(self, reverse=False, vertex=2, steps=2, direction=0.):
        items=fixture(reverse);row=items[3]['left'];relation=items[4]['join']
        index=next(i for i,p in enumerate(row['sample_provenance'])
                   if p.get('source_vertex')==vertex)
        ordinal=relation['a'].index(index);original=relation['parameters'][ordinal]
        for _ in range(steps):
            relation['parameters'][ordinal]=math.nextafter(relation['parameters'][ordinal],direction)
        return items,ordinal,original

    def test_structured_two_ulp_reinterpolation_preserves_source_vertex_exactly(self):
        items,ordinal,_=self.neighbour();before=copy.deepcopy(items)
        relation=items[4]['join'];row=items[3]['left'];index=relation['a'][ordinal]
        expected=g.sample_chain(items[0]['pieces']['left']['vertices'][:4],
                                relation['parameters'][ordinal])
        self.assertEqual(row['polygon'][index][0]-expected[0],2*math.ulp(1.5))
        self.assertEqual(row['sample_provenance'][index]['kind'],'SOURCE_VERTEX')
        self.identity(items);self.assertEqual(items,before)

    def test_reversed_partner_keeps_its_own_source_vertex_and_key(self):
        items,ordinal,_=self.neighbour(True);before=copy.deepcopy(items)
        self.identity(items);self.assertEqual(items,before)
        relation=items[4]['join']
        for side,pid in (('a','left'),('b','right')):
            index=relation[side][ordinal];row=items[3][pid]
            self.assertEqual(row['sample_provenance'][index]['source_vertex'],2)
            self.assertEqual(row['keys'][index],1.5)

    def test_two_ulp_arc_interpolation_does_not_acquire_vertex_fallback(self):
        items,ordinal,original=self.neighbour();row=items[3]['left']
        index=items[4]['join']['a'][ordinal];identity=row['sample_provenance'][index]
        identity.pop('source_vertex');identity.update(kind='SOURCE_ARC_INTERPOLATION',
            source_chain=[0,1,2,3],source_parameter=original)
        # Its own UV is valid; the differing common fraction must still refuse.
        with self.assertRaises(g.GradedBoundaryRefusal) as caught:self.identity(items)
        self.assertEqual(caught.exception.reason,'SOURCE_SEAM_SAMPLE_CHANGED')

    def test_one_ulp_neighbour_without_source_vertex_provenance_refuses(self):
        items,ordinal,original=self.neighbour(steps=1,direction=1.);row=items[3]['left']
        index=items[4]['join']['a'][ordinal];identity=row['sample_provenance'][index]
        expected=g.sample_chain(items[0]['pieces']['left']['vertices'][:4],
                                items[4]['join']['parameters'][ordinal])
        self.assertEqual(expected[0]-row['polygon'][index][0],math.ulp(1.5))
        identity.pop('source_vertex');identity.update(kind='SOURCE_ARC_INTERPOLATION',
            source_chain=[0,1,2,3],source_parameter=original)
        with self.assertRaises(g.GradedBoundaryRefusal) as caught:self.identity(items)
        self.assertEqual(caught.exception.reason,'SOURCE_SEAM_SAMPLE_CHANGED')

    def test_exact_normal_equality_for_arc_provenance_is_unchanged(self):
        items=fixture();row=items[3]['left'];relation=items[4]['join']
        index=next(i for i,p in enumerate(row['sample_provenance'])
                   if p.get('source_vertex')==2)
        identity=row['sample_provenance'][index];identity.pop('source_vertex')
        identity.update(kind='SOURCE_ARC_INTERPOLATION',source_chain=[0,1,2,3],
                        source_parameter=relation['parameters'][relation['a'].index(index)])
        self.identity(items)

    def test_mutated_vertex_uv_provenance_and_key_are_not_tolerated(self):
        for mutation in ('uv','vertex','key','local_index'):
            items,ordinal,_=self.neighbour();row=items[3]['left']
            index=items[4]['join']['a'][ordinal];identity=row['sample_provenance'][index]
            if mutation=='uv':row['polygon'][index][0]=math.nextafter(1.5,1.)
            elif mutation=='vertex':identity['source_vertex']=3
            elif mutation=='key':identity['source_perimeter_key_cm']=math.nextafter(row['keys'][index],1.)
            else:identity['derived_boundary_vertex']=index+1
            before=copy.deepcopy(items)
            with self.subTest(mutation=mutation),self.assertRaises(g.GradedBoundaryRefusal):self.identity(items)
            self.assertEqual(items,before)

    def test_other_source_vertex_in_or_outside_chain_cannot_replace_binding(self):
        for vertex in (3,4):
            items,ordinal,_=self.neighbour();row=items[3]['left'];relation=items[4]['join']
            other=next(i for i,p in enumerate(row['sample_provenance'])
                       if p.get('source_vertex')==vertex)
            current=relation['a'][ordinal]
            if other in relation['a']:
                other_ordinal=relation['a'].index(other);relation['a'][other_ordinal]=current
            relation['a'][ordinal]=other
            with self.subTest(vertex=vertex),self.assertRaises(g.GradedBoundaryRefusal) as caught:self.identity(items)
            self.assertEqual(caught.exception.reason,'SOURCE_SEAM_SAMPLE_CHANGED')

    def test_common_route_to_another_key_refuses_even_for_exact_vertex(self):
        items,ordinal,_=self.neighbour();items[4]['join']['parameters'][ordinal]=.500001
        with self.assertRaises(g.GradedBoundaryRefusal) as caught:self.identity(items)
        self.assertEqual(caught.exception.reason,'SOURCE_SEAM_SAMPLE_CHANGED')

    def test_cyclic_perimeter_origin_keeps_existing_modulo_key_policy(self):
        items=list(fixture());items[0]['seams'][0].update(edge_a='rest',edge_b='rest')
        items[3],items[4],_=prepare_regular_boundaries(*items[:3])
        relation=items[4]['join'];relation['parameters'][-1]=math.nextafter(1.,0.)
        for side,pid in (('a','left'),('b','right')):
            index=relation[side][-1];self.assertEqual(items[3][pid]['keys'][index],0.)
            self.assertEqual(items[3][pid]['sample_provenance'][index]['source_vertex'],0)
        self.identity(items)

    def test_fallback_remains_cooperative_and_preserves_source_on_refusal(self):
        items,ordinal,_=self.neighbour();before=copy.deepcopy(items);calls=[]
        original=g._existing_source_perimeter_key
        def stopped(*args):
            calls.append(True)
            def refuse():raise StudioError('fixture deadline exhausted')
            return original(*args[:-1],refuse)
        with patch.object(g,'_existing_source_perimeter_key',stopped),self.assertRaises(StudioError):self.identity(items)
        self.assertEqual(calls,[True]);self.assertEqual(items,before)


class SourceInterpolationSeamBindingTests(unittest.TestCase):
    """A checked sampler key alias preserves the last writer's exact UV."""
    def alias(self, reverse=False):
        items=fixture(reverse);relation=items[4]['join'];row=items[3]['left']
        ordinal=next(j for j,index in enumerate(relation['a'])
            if row['sample_provenance'][index]['kind']=='SOURCE_ARC_INTERPOLATION'
            and 0.1 < relation['parameters'][j] < 0.5)
        original=relation['parameters'][ordinal]
        relation['parameters'][ordinal]=math.nextafter(math.nextafter(original,1.),1.)
        index=relation['a'][ordinal]
        return items,ordinal,index

    def identity(self, items):
        return g._source_identity(items[0],items[3],items[4],items[1],lambda:None)

    def test_existing_interpolation_storage_alias_preserves_exact_uv(self):
        for reverse in (False,True):
            items,ordinal,index=self.alias(reverse);before=copy.deepcopy(items)
            row=items[3]['left'];identity=row['sample_provenance'][index]
            chain=identity['source_chain'];common=items[4]['join']['parameters'][ordinal]
            self.assertNotEqual(row['polygon'][index],
                g.sample_chain([row['source'][j] for j in chain],common))
            self.assertEqual(row['keys'][index],g._existing_source_perimeter_key(
                row['source'],chain,common,row['perimeter'],lambda:None))
            self.identity(items);self.assertEqual(items,before)

    def test_changed_uv_provenance_or_route_refuses_without_mutation(self):
        for mutation in ('uv','parameter','chain','key','local_index','common_route'):
            items,ordinal,index=self.alias();row=items[3]['left']
            identity=row['sample_provenance'][index]
            if mutation=='uv':row['polygon'][index][0]=math.nextafter(row['polygon'][index][0],math.inf)
            elif mutation=='parameter':identity['source_parameter']+=0.01
            elif mutation=='chain':identity['source_chain']=[3,4,5,0]
            elif mutation=='key':identity['source_perimeter_key_cm']=math.nextafter(row['keys'][index],math.inf)
            elif mutation=='local_index':identity['derived_boundary_vertex']=index+1
            else:items[4]['join']['parameters'][ordinal]+=0.000001
            before=copy.deepcopy(items)
            with self.subTest(mutation=mutation),self.assertRaises(g.GradedBoundaryRefusal):self.identity(items)
            self.assertEqual(items,before)

    def test_valid_uv_from_foreign_storage_route_cannot_replace_sample(self):
        items,_,index=self.alias();row=items[3]['left'];identity=row['sample_provenance'][index]
        identity['source_parameter']+=0.01
        row['polygon'][index]=g.sample_chain([row['source'][j] for j in identity['source_chain']],
            identity['source_parameter'])
        with self.assertRaises(g.GradedBoundaryRefusal) as caught:self.identity(items)
        self.assertEqual(caught.exception.reason,'SOURCE_MATERIAL_UV_CHANGED')

    def test_alias_is_produced_by_unchanged_source_sampler(self):
        items=list(fixture());original=1/3
        trailing=math.nextafter(math.nextafter(original,1.),1.)
        items[3],items[4],_=prepare_boundaries(items[0],items[1],
            seam_parameters={'join':[original,trailing]},regular_boundary_spacing_cm=1.)
        row=items[3]['left'];relation=items[4]['join']
        index=relation['a'][relation['parameters'].index(original)]
        self.assertEqual(row['sample_provenance'][index]['source_parameter'],trailing)
        self.assertNotEqual(row['polygon'][index],g.sample_chain(row['source'][:4],original))
        before=copy.deepcopy(items);self.identity(items);self.assertEqual(items,before)

    def test_backtracking_chain_cannot_fabricate_valid_uv_and_storage_key(self):
        items,_,index=self.alias();row=items[3]['left'];identity=row['sample_provenance'][index]
        chain=[0,1,0,1,2,3];parameter=1.2/3.2
        identity.update(source_chain=chain,source_parameter=parameter)
        row['polygon'][index]=g.sample_chain([row['source'][j] for j in chain],parameter)
        with self.assertRaises(g.GradedBoundaryRefusal) as caught:self.identity(items)
        self.assertEqual(caught.exception.reason,'INVALID_SOURCE_ARC_IDENTITY')

    def test_public_gradation_refuses_fabricated_writer_and_exact_modified_uv(self):
        # The local identity check proves route/UV self-consistency. Public
        # grading additionally compares against a canonical source resample;
        # an invented last-writer fraction cannot qualify by matching a key.
        for steps in (4,100):
            items,_,index=self.alias();row=items[3]['left'];identity=row['sample_provenance'][index]
            for _ in range(steps):
                identity['source_parameter']=math.nextafter(identity['source_parameter'],math.inf)
            row['polygon'][index]=g.sample_chain([row['source'][j] for j in identity['source_chain']],
                identity['source_parameter'])
            before=copy.deepcopy(items)
            with self.subTest(steps=steps),self.assertRaises(g.GradedBoundaryRefusal) as caught:call(items)
            self.assertEqual(caught.exception.reason,'OLD_PREPARED_COORDINATE_OR_IDENTITY_CHANGED')
            self.assertEqual(items,before)


if __name__=='__main__':unittest.main()
