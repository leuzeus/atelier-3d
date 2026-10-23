"""Exact source-double and legacy binary32 writer replay; no native execution."""
import copy
import json
import math
import unittest

from a3d.core import ROOT,StudioError,digest,read_json
from a3d.garment_measurements import reconcile_source_boundary_uv
from a3d.pattern_preparation import prepare_regular_boundaries
from a3d.source_uv_witnesses import replay_source_boundary_storage,source_boundary_seam_witnesses
from tests.test_source_uv_witnesses import f32


def fixture(binary32=False,vertex_alias=False,multiple=False):
    vertices=([[0.,0.],[12.800328,0.],[25.600655,0.],[25.600655,10.],[0.,10.]]if vertex_alias else
              [[0.,0.],[37.01308077488563,0.],[37.01308077488563,10.],[0.,10.]])
    edges=({'join':[0,1,2],'first':[0,1],'last':[1,2]}if vertex_alias else{'join':[1,2]})
    piece={'vertices':vertices,'faces':[[0,1,2],[0,2,3]],'edges':edges}
    data={'component_id':'garment.coat','units':'cm','pieces':{'front':copy.deepcopy(piece),'back':copy.deepcopy(piece)},
        'seams':[{'id':'join','piece_a':'front','piece_b':'back','edge_a':'join','edge_b':'join','orientation':'forward'}]}
    if vertex_alias:data['pieces']['back']['vertices'][1][0]=math.nextafter(vertices[1][0],-math.inf)
    if multiple:
        data['seams']=[{**data['seams'][0],'id':name,'edge_a':name,'edge_b':name}for name in ('first','last')]
    recipe=read_json(ROOT/'templates/sewing-recipe.json');recipe['component_id']='garment.coat'
    recipe['seams']={'join':{'kind':'permanent','ease_b_over_a':0.,'tolerance_relative':.02}}
    if multiple:recipe['seams']={name:copy.deepcopy(recipe['seams']['join'])for name in ('first','last')}
    recipe['placements']={pid:recipe['placements'][pid]for pid in data['pieces']}
    recipe['trial_pieces']=list(data['pieces'])
    recipe['pins']=[];recipe['mesh']['spacing_cm']=1.
    regular={'spacing_cm':2.,'min_spacing_cm':1.,'refinement_distance_cm':4.,'max_vertices':3000,'target_min_angle_degrees':15.}
    parts,seams,_=prepare_regular_boundaries(data,recipe,regular)
    native={'component_id':data['component_id'],'source_garment_sha256':digest(data),
        'recipe_mesh_sha256':digest({key:recipe[key]for key in ('component_id','mesh','placements','seams','pins')}),
        'regular_preparation_mesh':regular,'rest_cm':[],'panels':{},'seams':{}}
    offsets={}
    for pid,row in parts.items():
        offset=len(native['rest_cm']);offsets[pid]=offset
        native['rest_cm'].extend((f32(point)if binary32 else copy.deepcopy(point))+[0.]for point in row['polygon'])
        indices=list(range(offset,len(native['rest_cm'])))
        native['panels'][pid]={'indices':indices,'boundary':indices,'boundary_source_arclength_cm':row['keys'],
            'source_contour_sha256':row['source_sha256'],'edges':{key:[offset+i for i in ids]for key,ids in row['edges'].items()}}
    for sid,row in seams.items():
        native['seams'][sid]={key:copy.deepcopy(row[key])for key in ('piece_a','piece_b','kind','parameters')}
        native['seams'][sid]['pairs']=[[offsets[row['piece_a']]+a,offsets[row['piece_b']]+b]for a,b in zip(row['a'],row['b'])]
    links=[{**row,'id':'garment.coat::'+row['id'],'source_link_id':row['id'],'component_id':'garment.coat','kind':'permanent'}for row in data['seams']]
    return data,recipe,native,regular,links


class SourceUVStorage(unittest.TestCase):
    def test_explicit_absent_profile_keeps_historical_replay_identical(self):
        data,recipe,native,regular,_=fixture()
        original=replay_source_boundary_storage(data,recipe,native,regular)
        explicit=replay_source_boundary_storage(data,recipe,native,regular,
            meshing_profile=None,meshing_observation=None)
        self.assertEqual(original,explicit)
        self.assertNotIn('meshing_profile',original)
        self.assertNotIn('native_meshing_observation_sha256',original)

    def test_exact_double_and_binary32_replay_preserves_inputs_and_full_boundary(self):
        for binary32 in (False,True):
            data,recipe,native,regular,links=fixture(binary32)
            before=digest([data,recipe,native,regular,links])
            storage=replay_source_boundary_storage(data,recipe,native,regular)
            self.assertEqual(storage['storage_mode'],'BINARY32'if binary32 else'SOURCE_DOUBLE')
            for pid,piece in data['pieces'].items():
                witnesses=source_boundary_seam_witnesses(piece,pid,data['component_id'],native,links,canonical_storage=storage)
                restored,proof=reconcile_source_boundary_uv(piece,native['panels'][pid],native['rest_cm'],
                    seam_witnesses=witnesses,canonical_storage=storage,native_observation=native,piece_id=pid)
                self.assertEqual(set(restored),set(native['panels'][pid]['boundary']))
                self.assertEqual(proof['storage_mode'],storage['storage_mode'])
                self.assertEqual(proof['qualification'],'NONE');self.assertFalse(proof['native_mesh_changed'])
                self.assertTrue(all(row['storage_round_trip']=='EXACT'for row in proof['boundary_vertex_bindings']))
            self.assertEqual(digest([data,recipe,native,regular,links]),before)
            # The trusted ephemeral replay remains JSON-portable.
            copy_storage=json.loads(json.dumps(storage))
            source_boundary_seam_witnesses(data['pieces']['front'],'front',data['component_id'],native,links,
                canonical_storage=copy_storage)

    def test_replay_refuses_changed_uv_parameters_keys_order_and_ownership(self):
        for change in ('uv','parameter','key','boundary-order','pair-order','edge-order','ownership','recipe','source','profile'):
            data,recipe,native,regular,_=fixture()
            if change=='uv':native['rest_cm'][native['panels']['front']['boundary'][1]][0]+=1e-9
            elif change=='parameter':native['seams']['join']['parameters'][1]=math.nextafter(native['seams']['join']['parameters'][1],math.inf)
            elif change=='key':native['panels']['front']['boundary_source_arclength_cm'][1]+=.01
            elif change=='boundary-order':native['panels']['front']['boundary'].reverse()
            elif change=='pair-order':native['seams']['join']['pairs'].reverse()
            elif change=='edge-order':native['panels']['front']['edges']['join'].reverse()
            elif change=='ownership':native['panels']['back']['indices'].append(native['panels']['front']['indices'][0])
            elif change=='recipe':recipe['mesh']['spacing_cm']+=.01
            elif change=='source':data['pieces']['front']['vertices'][1][0]+=1e-9
            else:native['meshing_profile']={'mode':'SYNCHRONIZED_GRADED_V1'}
            before=digest([data,recipe,native,regular])
            with self.subTest(change=change),self.assertRaises(StudioError):replay_source_boundary_storage(data,recipe,native,regular)
            self.assertEqual(digest([data,recipe,native,regular]),before)

    def test_storage_refuses_observation_changed_after_replay(self):
        data,recipe,native,regular,links=fixture();storage=replay_source_boundary_storage(data,recipe,native,regular)
        native['rest_cm'][0][0]=math.nextafter(native['rest_cm'][0][0],math.inf)
        with self.assertRaises(StudioError):source_boundary_seam_witnesses(data['pieces']['front'],'front',
            data['component_id'],native,links,canonical_storage=storage)
        with self.assertRaises(StudioError):reconcile_source_boundary_uv(data['pieces']['front'],native['panels']['front'],
            native['rest_cm'],canonical_storage=storage,native_observation=native,piece_id='front')

    def test_missing_replay_context_does_not_silently_accept_source_double(self):
        data,_,native,_,links=fixture()
        with self.assertRaisesRegex(StudioError,'binary32'):source_boundary_seam_witnesses(
            data['pieces']['front'],'front',data['component_id'],native,links)
        with self.assertRaisesRegex(StudioError,'binary32'):reconcile_source_boundary_uv(
            data['pieces']['front'],native['panels']['front'],native['rest_cm'])

    def test_authored_vertex_storage_alias_uses_canonical_put_not_reinterpolation(self):
        from a3d.sewing import edge_chain,sample_chain
        data,recipe,native,regular,links=fixture(vertex_alias=True)
        storage=replay_source_boundary_storage(data,recipe,native,regular);aliases=[]
        for side,column in (('a',0),('b',1)):
            pid=native['seams']['join']['piece_'+side]
            points=edge_chain(data['pieces'][pid],'join')[1]
            for t,pair in zip(native['seams']['join']['parameters'],native['seams']['join']['pairs']):
                index=pair[column]
                if sample_chain(points,t)!=native['rest_cm'][index][:2]:aliases.append((pid,index))
            result=source_boundary_seam_witnesses(data['pieces'][pid],pid,data['component_id'],native,links,canonical_storage=storage)
            self.assertTrue(all(row['evidence']['storage_round_trip']=='EXACT'for row in result.values()))
        self.assertTrue(aliases)
        for pid,index in aliases:self.assertEqual(storage['boundaries'][pid]['bindings'][str(index)]['source_provenance']['kind'],'SOURCE_VERTEX')

    def test_shared_endpoint_keeps_both_declared_witnesses_and_refuses_parameter_forgery(self):
        data,recipe,native,regular,links=fixture(vertex_alias=True,multiple=True)
        storage=replay_source_boundary_storage(data,recipe,native,regular)
        result=source_boundary_seam_witnesses(data['pieces']['front'],'front',data['component_id'],native,links,
            canonical_storage=storage)
        multiple=[row for row in result.values()if len(row['evidence']['witnesses'])==2]
        self.assertEqual(len(multiple),1)
        self.assertEqual({row['source_link_id']for row in multiple[0]['evidence']['witnesses']},{'first','last'})
        native['seams']['first']['parameters'][1]=math.nextafter(native['seams']['first']['parameters'][1],math.inf)
        with self.assertRaises(StudioError):replay_source_boundary_storage(data,recipe,native,regular)
        with self.assertRaises(StudioError):source_boundary_seam_witnesses(data['pieces']['front'],'front',
            data['component_id'],native,links,canonical_storage=storage)
