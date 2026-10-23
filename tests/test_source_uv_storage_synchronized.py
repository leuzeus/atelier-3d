"""Portable replay of the sourced synchronized boundary writer; no Blender."""
import copy
import json
import math
import unittest
import zipfile
from unittest.mock import patch

from a3d.core import StudioError,digest,read_json,sha
from a3d.garment_measurements import propose_compiled_measurement_paths,reconcile_source_boundary_uv
from a3d.meshing_profile import create_envelope,profile_binding
from a3d.pattern_preparation import prepare_regular_boundaries
from a3d.source_uv_witnesses import replay_source_boundary_storage,source_boundary_seam_witnesses,_binary32
from tests.test_boundary_gradation import fixture as graded_inputs,binary32
from tests.test_core import Case
import tests.test_garment_measurements as measurement_tests
from tests.test_meshing_profile import profile as profile_for


def fixture(reverse=False):
    data,recipe,regular,*_=graded_inputs(reverse)
    profile=profile_for(data['pieces'])
    envelope=create_envelope(profile,data['component_id'],recipe,regular,clock=lambda:0.)
    parts,seams,sampling=prepare_regular_boundaries(data,recipe,regular,
        meshing_envelope=envelope,transport_2d=binary32)
    native={'component_id':data['component_id'],'source_garment_sha256':digest(data),
        'recipe_mesh_sha256':digest({key:recipe[key]for key in ('component_id','mesh','placements','seams','pins')}),
        'regular_preparation_mesh':copy.deepcopy(regular),'regular_preparation_sampling':sampling,
        'rest_cm':[],'panels':{},'seams':{},'meshing_profile':profile_binding(profile)}
    offsets={}
    for pid,row in parts.items():
        offset=len(native['rest_cm']);offsets[pid]=offset
        # bounded_pattern_meshing.exact_source_coordinates restores these source doubles.
        native['rest_cm'].extend(copy.deepcopy(point)+[0.]for point in row['polygon'])
        indices=list(range(offset,len(native['rest_cm'])))
        native['panels'][pid]={'indices':indices,'boundary':indices,'boundary_source_arclength_cm':row['keys'],
            'source_contour_sha256':row['source_sha256'],'edges':{key:[offset+i for i in ids]for key,ids in row['edges'].items()}}
    for sid,row in seams.items():
        native['seams'][sid]={key:copy.deepcopy(row[key])for key in ('piece_a','piece_b','kind','parameters')}
        native['seams'][sid]['pairs']=[[offsets[row['piece_a']]+a,offsets[row['piece_b']]+b]for a,b in zip(row['a'],row['b'])]
    native['meshing_work']=envelope.snapshot()
    observation={'status':'COMPLETED_MESH_BUILD_ONLY','qualification':'NONE',
        'profile':copy.deepcopy(native['meshing_profile']),'work':copy.deepcopy(native['meshing_work'])}
    links=[{**row,'id':'garment.coat::'+row['id'],'source_link_id':row['id'],'component_id':'garment.coat'}for row in data['seams']]
    return data,recipe,native,regular,profile,observation,links


def replay(items):
    data,recipe,native,regular,profile,observation,*_=items
    return replay_source_boundary_storage(data,recipe,native,regular,
        meshing_profile=profile,meshing_observation=observation)


def rebind_profile(items):
    data,recipe,native,regular,profile,observation,*_=items
    envelope=create_envelope(profile,data['component_id'],recipe,regular,clock=lambda:0.)
    native['meshing_profile']=profile_binding(profile)
    native['meshing_work']['limits']=dict(envelope.limits)
    native['meshing_work']['owner_limits']=dict(envelope.owner_limits)
    observation.update(profile=copy.deepcopy(native['meshing_profile']),work=copy.deepcopy(native['meshing_work']))


class SynchronizedSourceUVStorage(unittest.TestCase):
    def test_real_shared_sampler_replays_added_controls_and_reversed_seams_exactly(self):
        for reverse in (False,True):
            items=fixture(reverse);data,recipe,native,regular,profile,observation,links=items
            self.assertGreater(native['regular_preparation_sampling']['source_boundary_gradation']['boundary_count_after'],
                native['regular_preparation_sampling']['source_boundary_gradation']['boundary_count_before'])
            before=digest(items);storage=replay(items)
            self.assertEqual(storage['storage_mode'],'SOURCE_DOUBLE')
            self.assertEqual(storage['meshing_profile'],profile_binding(profile))
            self.assertEqual(storage['native_meshing_observation_sha256'],digest(observation))
            for pid,piece in data['pieces'].items():
                witnesses=source_boundary_seam_witnesses(piece,pid,data['component_id'],native,links,canonical_storage=storage)
                restored,proof=reconcile_source_boundary_uv(piece,native['panels'][pid],native['rest_cm'],
                    seam_witnesses=witnesses,canonical_storage=storage,native_observation=native,piece_id=pid)
                self.assertEqual(set(restored),set(native['panels'][pid]['boundary']))
                self.assertEqual(proof['qualification'],'NONE');self.assertFalse(proof['native_mesh_changed'])
            self.assertEqual(before,digest(items))
            self.assertEqual(storage,json.loads(json.dumps(storage)))

    def test_exact_binary32_transport_is_portable_and_not_a_storage_tolerance(self):
        points=([.1,-.1],[math.nextafter(1.,math.inf),-0.],[2**-149,2**-150],[37.01308077488563,1.0000000596046448])
        for point in points:self.assertEqual(_binary32(point),binary32(point))
        with self.assertRaises(StudioError):_binary32([1e300,0.])
        items=fixture();native=items[2]
        for point in native['rest_cm']:point[:2]=_binary32(point[:2])
        with self.assertRaisesRegex(StudioError,'exact restored source-double'):replay(items)

    def test_missing_different_partial_or_refused_profile_and_observation_stay_refused(self):
        for change in ('argument','payload','observation','mode','hash','ids','qualification','scope','extra',
                       'declared-budget','incomplete','refused','observation-profile','observation-work'):
            items=list(fixture());native,profile,observation=items[2],items[4],items[5]
            if change=='argument':items[4]=None
            elif change=='payload':native.pop('meshing_profile')
            elif change=='observation':items[5]=None
            elif change=='mode':native['meshing_profile']['mode']='OTHER'
            elif change=='hash':native['meshing_profile']['profile_sha256']='e'*64
            elif change=='ids':native['meshing_profile']['source_ids']=['left']
            elif change=='qualification':native['meshing_profile']['qualification']='PASS'
            elif change=='scope':native['meshing_profile']['clock_scope']='OTHER'
            elif change=='extra':native['meshing_profile']['ignored']=True
            elif change=='declared-budget':profile['budgets']['max_seconds']+=1.
            elif change=='incomplete':observation['status']='REFUSED_OR_INCOMPLETE_MESH_BUILD'
            elif change=='refused':profile['mode']='UNSUPPORTED'
            elif change=='observation-profile':observation['profile']['source_ids'].reverse()
            else:observation['work']['work']['sampling_calls']+=1
            before=digest(items)
            with self.subTest(change=change),self.assertRaises(StudioError):replay(items)
            self.assertEqual(before,digest(items))

    def test_mutated_source_recipe_uv_seam_parameters_order_and_ownership_remain_refused(self):
        for change in ('source','recipe','uv','binary32-alias','parameter','key','boundary-order','pair-order','edge-order','ownership'):
            items=list(fixture());data,recipe,native=items[:3];panel=native['panels']['left']
            if change=='source':data['pieces']['left']['vertices'][1][0]=math.nextafter(.1,math.inf)
            elif change=='recipe':recipe['mesh']['spacing_cm']+=.01
            elif change=='uv':native['rest_cm'][panel['boundary'][1]][0]+=1e-9
            elif change=='binary32-alias':native['rest_cm'][panel['boundary'][1]][0]=math.nextafter(native['rest_cm'][panel['boundary'][1]][0],math.inf)
            elif change=='parameter':native['seams']['join']['parameters'][1]=math.nextafter(native['seams']['join']['parameters'][1],math.inf)
            elif change=='key':panel['boundary_source_arclength_cm'][1]+=.01
            elif change=='boundary-order':panel['boundary'].reverse()
            elif change=='pair-order':native['seams']['join']['pairs'].reverse()
            elif change=='edge-order':panel['edges']['bottom'].reverse()
            else:native['panels']['right']['indices'].append(panel['indices'][0])
            before=digest(items)
            with self.subTest(change=change),self.assertRaises(StudioError):replay(items)
            self.assertEqual(before,digest(items))

    def test_writer_work_over_budget_invalid_clock_or_refunded_costs_are_refused(self):
        for change in ('counter','limits','owners','refund','nan','deadline','duration','component','admission',
                       'missing-owner-work','owner-budget','owner-global','unknown-owner','missing-controls',
                       'control-count','unknown-control','phase','extra'):
            items=list(fixture());work=items[2]['meshing_work']
            if change=='counter':work['work']['sampling_calls']=work['limits']['sampling_calls']+1
            elif change=='limits':work['limits']['work_steps']+=1
            elif change=='owners':work['owner_limits']['native_cdt_calls']+=1
            elif change=='refund':work['costs_refunded']=True
            elif change=='nan':work['last_checkpoint']=float('nan')
            elif change=='deadline':work['last_checkpoint']=work['absolute_deadline']
            elif change=='duration':work['absolute_deadline']+=1.
            elif change=='component':work['component_id']='other'
            elif change=='admission':work['admission']='PASS'
            elif change=='missing-owner-work':work.pop('owner_work')
            elif change=='owner-budget':work['owner_work']['left']['native_cdt_calls']=work['owner_limits']['native_cdt_calls']+1
            elif change=='owner-global':work['owner_work']['left']['sampling_calls']=1+work['work']['sampling_calls']
            elif change=='unknown-owner':work['owner_work']['unsourced']={}
            elif change=='missing-controls':work.pop('material_controls')
            elif change=='control-count':work['material_controls']['left']=work['work']['attempted_insertions']+1
            elif change=='unknown-control':work['material_controls']['unsourced']=0
            elif change=='phase':work['last_phase']='before_capture'
            else:work['unrecognized']=True
            items[5]['work']=copy.deepcopy(work)
            with self.subTest(change=change),self.assertRaises(StudioError):replay(items)

    def test_replay_has_fresh_bounded_clock_and_stops_on_work_budget(self):
        items=list(fixture());profile=items[4];profile['budgets']['max_work_steps']=1
        for key in items[2]['meshing_work']['work']:items[2]['meshing_work']['work'][key]=0
        items[2]['meshing_work']['owner_work']={}
        items[2]['meshing_work']['material_controls']={pid:0 for pid in items[0]['pieces']}
        rebind_profile(items);before=digest(items)
        with self.assertRaises(StudioError)as caught:replay(items)
        self.assertEqual(caught.exception.reason,'BUDGET_EXHAUSTED')
        self.assertEqual(before,digest(items))
        items=fixture();clock=[1000.];envelope=None
        def local_envelope(*args,**kwargs):
            nonlocal envelope
            envelope=create_envelope(*args,**kwargs,clock=lambda:clock[0]);return envelope
        def expired(*args,**kwargs):
            clock[0]+=90.;return prepare_regular_boundaries(*args,**kwargs)
        with patch('a3d.meshing_profile.create_envelope',side_effect=local_envelope),\
                patch('a3d.pattern_preparation.prepare_regular_boundaries',side_effect=expired),self.assertRaises(StudioError)as caught:
            replay(items)
        self.assertEqual(envelope.start,1000.)
        self.assertEqual(items[2]['meshing_work']['start'],0.)
        self.assertEqual(caught.exception.reason,'DEADLINE_EXHAUSTED')

    def test_additional_replay_output_cannot_exceed_shared_storage_budget(self):
        items=list(fixture());items[4]['budgets']['max_output_nodes']=items[2]['meshing_work']['work']['output_nodes']
        rebind_profile(items)
        with self.assertRaises(StudioError)as caught:replay(items)
        self.assertEqual(caught.exception.reason,'BUDGET_EXHAUSTED')

    def test_storage_cannot_survive_mutation_of_profile_or_writer_work(self):
        for change in ('profile','work'):
            items=fixture();storage=replay(items);data,_,native,_,_,_,links=items
            if change=='profile':native['meshing_profile']['source_ids'].reverse()
            else:native['meshing_work']['work']['sampling_calls']+=1
            with self.subTest(change=change),self.assertRaises(StudioError):source_boundary_seam_witnesses(
                data['pieces']['left'],'left',data['component_id'],native,links,canonical_storage=storage)


class SynchronizedMeasurementReplayWiring(Case):
    def test_wrapper_forwards_authenticated_profile_and_observation_and_retains_refs(self):
        project,compiled,fit,body_origin,stored=measurement_tests.GarmentMeasurements.project_fixture(self)
        data,recipe,payload,regular,profile,observation,_=fixture()
        with zipfile.ZipFile(self.root/'source.garmentpkg','w')as archive:archive.writestr('garment.json',json.dumps(data))
        package_ref={'path':'source.garmentpkg','sha256':sha(self.root/'source.garmentpkg')}
        compiled['components'][0]['package_source_ref']=package_ref
        guides=read_json(self.root/'guides.json');guides['garment.coat']['source_sha256']=digest(data);stored('guides.json',guides)
        stored('source.json',data);payload.update(source_garment='source.json',package_sha256=package_ref['sha256'])
        mesh_ref=stored('mesh.json',payload)
        spec={'version':1,'component_id':data['component_id'],'source_ref':'fixture:source',
              'regular_mesh':regular,'meshing_profile':profile}
        refs=[stored('recipe.json',recipe),stored('preparation.json',spec),compiled['source_ref']]
        native={'operation':'prepare_pattern_assembly','files':[mesh_ref,*refs],
            'result':dict(zip(('recipe','preparation_spec','construction_dossier'),refs))}
        native['result'].update(derived_mesh=mesh_ref,component_id=data['component_id'],
            readiness='NEEDS_CORRECTION',meshing_observation=observation)
        before={file.name:sha(file)for file in self.root.iterdir()}
        with patch('a3d.production_dossier.compile_project_dossier',return_value=copy.deepcopy(compiled)),\
                patch('a3d.native_evidence.native_origin',return_value=(body_origin,{})),\
                patch('a3d.native_evidence.native_observation_origin',return_value=(native,{})),\
                patch('a3d.garment_measurements.propose_measurement_paths',return_value={'proposals':[], 'qualification':'NONE'})as propose:
            result=propose_compiled_measurement_paths(project,compiled,'guides.json','fit.json',
                derived_mesh_refs={data['component_id']:mesh_ref})
        actual_mesh=propose.call_args.args[6][data['component_id']]
        self.assertEqual(actual_mesh['_canonical_source_uv_storage']['meshing_profile'],profile_binding(profile))
        self.assertNotIn('_source_uv_storage_error',actual_mesh)
        self.assertTrue(all(ref in result['input_refs']for ref in refs))
        trace=result['source_uv_triangulations'][data['component_id']]
        self.assertEqual(trace['placement_readiness'],'NEEDS_CORRECTION')
        self.assertEqual(trace['placement_qualification'],'NOT_TRANSFERRED')
        self.assertEqual(trace['source_uv_storage']['storage_mode'],'SOURCE_DOUBLE')
        self.assertEqual(before,{file.name:sha(file)for file in self.root.iterdir()})
