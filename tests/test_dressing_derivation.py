"""Portable source topology and exact body sections; no native dressing proof."""
import copy
import math
import unittest
from unittest.mock import patch

from a3d.core import StudioError, contract, digest
from a3d.dressing_derivation import (_triangles, derive_dressing_contract, mount_orders,
                                    source_boundary_graph, world_point)
from a3d.shoulder_surface import measured_surface_shoulders
from tests.test_shoulder_surface import fixture as body_fixture


def panel(width=10.,height=10.):
    return {'vertices':[[0.,0.],[width,0.],[width,height],[0.,height]],
            'faces':[[0,1,2],[0,2,3]],'edges':{'bottom':[0,1],'right':[1,2],'top':[2,3],'left':[0,3]},
            'position_cm':[0.,0.,0.],'rotation_degrees':[0.,0.,0.]}


def link(ident,a,ea,b,eb,kind='permanent',orientation='forward'):
    return {'id':ident,'piece_a':a,'edge_a':ea,'piece_b':b,'edge_b':eb,'kind':kind,'orientation':orientation}


def garment(cid,pieces,seams):
    return {'component_id':cid,'units':'cm','pieces':pieces,'seams':seams,
            'material':{'mass_kg':.1,'tension_stiffness':1.,'compression_stiffness':1.,
                        'shear_stiffness':1.,'bending_stiffness':1.}}


def fixture():
    profile,geometry,triangles=body_fixture()
    profile.update(status='PROFILE_MEASURED',segmentation='EXPLICIT_SOURCE')
    for name,point in [('wrist.left',[0.,0.,20.]),('elbow.left',[0.,0.,40.]),
                       ('waist',[0.,0.,50.]),('hip',[0.,0.,20.]),('neck',[0.,0.,90.])]:
        profile['landmarks'][name]={'point_cm':point}
    profile=measured_surface_shoulders(profile,geometry,triangles)
    belt=garment('source.belt',{'belt':panel(10.,3.)},[link('closure','belt','left','belt','right','closure')])
    cuff=garment('source.arm',{'cuff':panel(10.,3.),'sleeve':panel()},
        [link('cuff-side','cuff','left','cuff','right'),link('sleeve-side','sleeve','left','sleeve','right'),
         link('attach','cuff','top','sleeve','bottom')])
    front=garment('source.coat',{'front-left':panel(),'front-right':panel()},
        [link('detachable','front-left','top','front-right','top','detachable')])
    sources={cid:{'data':data,'source_ref':{'path':cid+'.garmentpkg','sha256':digest(data)}}
             for cid,data in ((row['component_id'],row) for row in (belt,cuff,front))}
    semantics={'belt':{'role':'belt','side':'center','layer':'outer'},
               'cuff':{'role':'cuff','side':'left','layer':'inner'},
               'sleeve':{'role':'sleeve','side':'left','layer':'inner'},
               'front-left':{'role':'front','side':'left','layer':'coat','guide_edges':{'opening':'left'}},
               'front-right':{'role':'front','side':'right','layer':'coat','guide_edges':{'opening':'right'}}}
    compiled={'textiles':{pid:{'semantics':semantics[pid],'source_geometry':copy.deepcopy(piece)}
                          for source in sources.values() for pid,piece in source['data']['pieces'].items()},
              'assembly_spec':{'layers':{'inside_to_outside':[['inner','coat'],['coat','outer']]}}}
    guides={};templates={'components':{}}
    for cid,source in sources.items():
        panels={pid:{'source_ref':'synthetic:explicit-guide','arc_sections':
                     [{'v_cm':v,'arc_offset_cm':0.,'curve_cm':[[0.,v,50.],[10.,v,50.]]} for v in (0.,10.)]}
                for pid in source['data']['pieces']}
        guides[cid]={'source_sha256':digest(source['data']),'profile_sha256':digest(profile),
                     'profile_cache_key':profile['cache_key'],'panels':panels}
        templates['components'][cid]={'source_ref':source['source_ref'],'plan_fields':
            {'preform':{'panels':copy.deepcopy(panels)},'collision':{'clearance_cm':.05},
             'assembly':{'max_displacement_cm':.8}}}
    policy={'version':1,'bindings':{key:{'path':key+'.json','sha256':'a'*64}
             for key in ('templates_ref','body_geometry_ref','body_triangles_ref')},
             'section_parameters':[0.,.5,1.],'source_edge_spacing_cm':1.,
             'budgets':{'max_boundary_edges':100,'max_body_triangles':100,'max_methods':8,
                        'max_sections':24,'max_candidate_orders':4,'max_path_points':500}}
    return compiled,sources,profile,geometry,triangles,guides,templates,policy


def hood_yoke_fixture(configure=False,head_height=97.):
    """Synthetic cut with real boundary indices and declared, unwelded openings."""
    values=list(fixture());compiled,sources,profile,geometry,triangles,guides,templates,policy=values
    base=copy.deepcopy(profile);surface=base.pop('surface_landmarks_source');base['cache_key']=surface['previous_cache_key']
    for side in ('left','right'):del base['landmarks']['shoulder.surface.'+side]
    base['landmarks']['head.center']={'point_cm':[0.,0.,head_height]};base['landmarks']['chest']={'point_cm':[0.,0.,70.]}
    profile=measured_surface_shoulders(base,geometry,triangles);values[2]=profile
    hood=panel();hood['edges']={'neck-base':[0,1],'face-free':[1,2],'crown-back':[2,3,0]}
    points=[[0.,0.],[4.,0.],[8.,0.],[8.,4.],[8.,8.],[4.,8.],[0.,8.],[0.,4.]]
    yoke={'vertices':points+[[4.,4.]],'faces':[[8,i,(i+1)%8] for i in range(8)],
          'edges':{'outer-free':[0,1,2,3],'front-left':[3,4],'neck-left':[4,5],'neck-right':[5,6],
                   'front-right':[6,7],'attach-left':[0,1],'attach-right':[1,2]},
          'position_cm':[0.,0.,0.],'rotation_degrees':[0.,0.,0.]}
    pieces={'hood-left':copy.deepcopy(hood),'hood-right':copy.deepcopy(hood),'yoke-upper':copy.deepcopy(yoke),'yoke-lower':copy.deepcopy(yoke)}
    links=[link('crown','hood-left','crown-back','hood-right','crown-back'),
           link('neck-left','hood-left','neck-base','yoke-upper','neck-left'),
           link('neck-right','hood-right','neck-base','yoke-upper','neck-right'),
           link('front-upper','yoke-upper','front-left','yoke-upper','front-right','closure'),
           link('front-lower','yoke-lower','front-left','yoke-lower','front-right','closure'),
           link('attach-left','yoke-upper','attach-left','yoke-lower','attach-left','detachable'),
           link('attach-right','yoke-upper','attach-right','yoke-lower','attach-right','detachable')]
    data=garment('source.hood-yoke',pieces,links);ref={'path':'source.hood-yoke.garmentpkg','sha256':digest(data)}
    sources[data['component_id']]={'data':data,'source_ref':ref}
    for pid,piece in pieces.items():
        is_hood=pid.startswith('hood-');side=pid.rsplit('-',1)[-1] if is_hood else 'center'
        compiled['textiles'][pid]={'source_geometry':copy.deepcopy(piece),'semantics':{
            'role':'hood' if is_hood else 'yoke','side':side,'layer':'hood-upper' if pid!='yoke-lower' else 'hood-lower',
            'guide_edges':{'anchor':'neck-base'} if is_hood else {'anchor':'neck-left','anchor_end':'neck-right'}}}
    compiled['assembly_spec']['layers']['inside_to_outside'] += [['coat','hood-lower'],['hood-lower','hood-upper'],['hood-upper','outer']]
    panels={pid:{'source_ref':'synthetic:source-bound-hood-yoke','arc_sections':[
        {'v_cm':v,'arc_offset_cm':0.,'curve_cm':[[0.,v,80.],[10.,v,80.]]} for v in (0.,10.)]} for pid in pieces}
    guides[data['component_id']]={'source_sha256':digest(data),'profile_sha256':digest(profile),'profile_cache_key':profile['cache_key'],'panels':panels}
    templates['components'][data['component_id']]={'source_ref':ref,'plan_fields':{'preform':{'panels':copy.deepcopy(panels)},
        'collision':{'clearance_cm':.05},'assembly':{'max_displacement_cm':.8}}}
    for guide in guides.values():guide.update(profile_sha256=digest(profile),profile_cache_key=profile['cache_key'])
    if configure:
        policy['method_configurations']=[{
            'method_id':'source.hood-yoke.hood-yoke','mode':'RAISED_OPEN_HOOD',
            'source_ref':{'path':'hood-configuration.json','sha256':'b'*64},
            'source_link_states':[{'source_link_id':name,'state':'OPEN'} for name in ('front-upper','attach-left','attach-right')]},
            {'method_id':'source.hood-yoke.yoke.yoke-lower','mode':'OPEN_SHOULDER_YOKE',
             'source_ref':{'path':'yoke-configuration.json','sha256':'c'*64},
             'source_link_states':[{'source_link_id':name,'state':'OPEN'} for name in ('front-lower','attach-left','attach-right')]}]
    return values


class DressingDerivation(unittest.TestCase):
    def test_free_aliases_closure_links_and_cut_are_preserved_without_proximity_union(self):
        values=fixture();data=values[1]['source.belt']['data'];data['pieces']['belt']['edges']['free-alias']=[0,1]
        before=digest(data);result=source_boundary_graph(data)
        self.assertEqual(digest(data),before);self.assertEqual(result['permanent_atoms_consumed'],0)
        self.assertEqual(result['source_boundary_atoms'],4);self.assertEqual(len(result['components']),1)
        self.assertTrue(result['components'][0]['closed_graph'])
        self.assertEqual(result['closure_links_preserved'],data['seams'])
        self.assertEqual(result['components'][0]['passage'],'NOT_ASSESSED')
        coincident=copy.deepcopy(data);coincident['pieces']['second']=copy.deepcopy(data['pieces']['belt'])
        self.assertEqual(len(source_boundary_graph(coincident)['components']),2)

    def test_only_permanent_source_links_connect_cuff_and_sleeve_free_boundaries(self):
        source=fixture()[1]['source.arm']['data'];report=source_boundary_graph(source)
        cuff=[row for row in report['components'] if row['pieces']==['cuff']]
        self.assertEqual(len(cuff),1);self.assertTrue(cuff[0]['closed_graph'])
        self.assertEqual(cuff[0]['source_edges'],[{'piece':'cuff','edge':'bottom'}])
        self.assertEqual(len(report['permanent_bridges']),3)
        self.assertEqual(report['qualification'],'SOURCE_TOPOLOGY_ONLY')

    def test_duplicate_permanent_consumption_invalid_faces_and_budget_refused(self):
        source=fixture()[1]['source.arm']['data']
        self.assertEqual(source_boundary_graph(source,1)['status'],'INCOMPLETE')
        for failure in ('duplicate','interior','face','nan','bool'):
            bad=copy.deepcopy(source)
            if failure=='duplicate':bad['seams'].append(dict(bad['seams'][0],id='duplicate'))
            if failure=='interior':bad['pieces']['cuff']['edges']['diagonal']=[0,2]
            if failure=='face':bad['pieces']['cuff']['faces'][0]=[0,1,999]
            if failure=='nan':bad['pieces']['cuff']['vertices'][0][0]=math.nan
            if failure=='bool':bad['pieces']['cuff']['vertices'][0][0]=True
            with self.subTest(failure=failure),self.assertRaises(StudioError):source_boundary_graph(bad)

    def test_measured_regions_closed_cuff_open_front_and_wrap_are_distinct(self):
        values=fixture();before=digest(values);result=derive_dressing_contract(*values)
        self.assertEqual(digest(values),before);self.assertEqual(result,derive_dressing_contract(*values))
        self.assertEqual({row['method'] for row in result['methods']},{'CLOSED_CUFF','OPEN_WRAP','OPEN_FRONT'})
        self.assertTrue(all(row['status']=='MEASURED_SECTIONS' for row in result['regions']))
        self.assertEqual(result['mount_dag']['selected_order'],['source.arm.cuff.left','source.coat.open-front','source.belt.wrap'])
        reasons={row['reason'] for row in result['diagnostics']}
        self.assertIn('MEASURED_HAND_ENTRY_DOMAIN_REQUIRED',reasons)
        self.assertIn('NATIVE_ENTRY_CONFIGURATION_AND_SOURCE_GRIPS_REQUIRED',reasons)
        self.assertEqual(result['status'],'NEEDS_DATA');self.assertFalse(result['accepted'])
        self.assertEqual(result['simulation'],'NOT_EXECUTED')
        wrap=next(row for row in result['methods'] if row['method']=='OPEN_WRAP')
        self.assertEqual(wrap['opening_interpretation'],'OPEN_BAND_NEVER_CLOSED_PASSAGE_FROM_FLAT_PERIMETER')

    def test_changed_pose_geometry_frame_and_native_triangulation_refused(self):
        values=fixture()
        for failure in ('pose','geometry','triangles','frame','cache'):
            _,_,profile,geometry,triangles,*_=copy.deepcopy(values)
            if failure=='pose':geometry['pose_sha256']='b'*64
            if failure=='geometry':geometry['vertices_cm'][0][0]+=1.
            if failure=='triangles':triangles[0].reverse()
            if failure=='frame':profile['frame']['origin_cm'][0]+=1.
            if failure=='cache':profile['cache_key']='invented'
            with self.subTest(failure=failure),self.assertRaises(StudioError):_triangles(profile,geometry,triangles)
        self.assertEqual(world_point(values[2],[2.,3.,4.]),[-2.,-3.,4.])

    def test_layer_dag_ties_and_budget_never_select_a_lexical_approval(self):
        methods=[{'id':name,'layers':['outer']} for name in ('left','right')]
        layers={'inside_to_outside':[]}
        result=mount_orders(methods,layers,2);self.assertEqual(result['status'],'AMBIGUOUS_ORDER')
        self.assertIsNone(result['selected_order'])
        self.assertEqual(mount_orders(methods,layers,1)['status'],'INCOMPLETE')
        self.assertEqual(mount_orders(methods,layers,2,['right','left'])['selected_order'],['right','left'])
        constrained=[{'id':'inside','layers':['inner']},{'id':'outside','layers':['outer']}]
        with self.assertRaises(StudioError):mount_orders(constrained,{'inside_to_outside':[['inner','outer']]},2,['outside','inside'])

    def test_triangle_budget_checked_before_measuring_and_policy_numeric_refusals(self):
        values=list(fixture());values[-1]['budgets']['max_body_triangles']=4
        with patch('a3d.dressing_derivation._triangles') as measure,self.assertRaisesRegex(StudioError,'triangle budget'):
            derive_dressing_contract(*values)
        measure.assert_not_called()
        values=list(fixture());values[-1]['section_parameters']=[.5,0.,1.]
        with self.assertRaisesRegex(StudioError,'increasing'):derive_dressing_contract(*values)
        for failure in ('bool','nan','claim'):
            policy=fixture()[-1]
            if failure=='bool':policy['budgets']['max_path_points']=True
            if failure=='nan':policy['source_edge_spacing_cm']=math.nan
            if failure=='claim':policy['passage']='PASS'
            with self.subTest(failure=failure),self.assertRaises(StudioError):contract('dressing-derivation',policy)

    def test_wrong_guide_source_and_template_policies_refused(self):
        for failure in ('guide','template','source'):
            values=list(fixture())
            if failure=='guide':values[5]['source.belt']['profile_cache_key']='old'
            if failure=='template':values[6]['components']['source.belt']['plan_fields']['preform']['panels']['belt']['arc_sections'][0]['v_cm']+=1
            if failure=='source':values[1]['source.belt']['data']['pieces']['belt']['vertices'][0][0]+=.1
            with self.subTest(failure=failure),self.assertRaisesRegex(StudioError,'exact compiled sources'):
                derive_dressing_contract(*values)

    def test_hood_yoke_methods_partition_permanent_units_and_preserve_detachable_relations(self):
        values=hood_yoke_fixture();before=digest(values);result=derive_dressing_contract(*values)
        self.assertEqual(digest(values),before);self.assertEqual(result,derive_dressing_contract(*values))
        hood=next(row for row in result['methods'] if row['method']=='OPEN_HOOD_YOKE')
        yoke=next(row for row in result['methods'] if row['method']=='OPEN_DETACHABLE_YOKE')
        self.assertEqual(hood['pieces'],['hood-left','hood-right','yoke-upper']);self.assertEqual(yoke['pieces'],['yoke-lower'])
        self.assertEqual(hood['mode_proposals'],['RAISED_OPEN_HOOD','LOWERED_OPEN_HOOD']);self.assertIsNone(hood['configuration'])
        self.assertEqual({row['source_link_id'] for row in hood['source_anchor_edges']},{'neck-left','neck-right'})
        self.assertEqual({row['id'] for row in hood['source_open_links']},{'front-upper','attach-left','attach-right'})
        self.assertEqual(hood['full_head_passage'],'NOT_QUALIFIED')
        self.assertEqual(result['mount_dag']['dependencies'][hood['id']],['source.arm.cuff.left','source.coat.open-front',yoke['id']])
        self.assertIn('HOOD_YOKE_SOURCE_MODE_AND_OPEN_LINK_STATES_REQUIRED',{row['reason'] for row in result['diagnostics']})
        self.assertNotIn('HOOD_YOKE_DRESSING_METHOD_NOT_IMPLEMENTED',{row['reason'] for row in result['diagnostics']})

    def test_explicit_raised_or_lowered_modes_remain_open_and_nonphysical(self):
        for mode in ('RAISED_OPEN_HOOD','LOWERED_OPEN_HOOD'):
            values=hood_yoke_fixture(True);values[-1]['method_configurations'][0]['mode']=mode
            result=derive_dressing_contract(*values);hood=next(row for row in result['methods'] if row['method']=='OPEN_HOOD_YOKE')
            self.assertEqual(hood['configuration']['mode'],mode);self.assertEqual(hood['closure_behavior'],'NOT_EXECUTED')
            region=next(row for row in result['regions'] if row['id']==hood['body_region'])
            self.assertEqual(region['domain'],'NECK_TO_HEAD_CENTER_ONLY');self.assertEqual(region['full_head_passage'],'NOT_QUALIFIED')
            self.assertTrue(all(row['state']=='OPEN' for row in hood['configuration']['source_link_states']))
            self.assertNotIn('HOOD_YOKE_SOURCE_MODE_AND_OPEN_LINK_STATES_REQUIRED',{row['reason'] for row in result['diagnostics']})
            self.assertEqual(result['status'],'NEEDS_DATA');self.assertEqual(result['simulation'],'NOT_EXECUTED')

    def test_configurations_refuse_wrong_mode_unknown_missing_duplicate_or_closed_links(self):
        for failure in ('mode','unknown','missing','duplicate','closed','boolean','duplicate-method'):
            values=hood_yoke_fixture(True);rows=values[-1]['method_configurations'];configuration=rows[0]
            if failure=='mode':configuration['mode']='OPEN_SHOULDER_YOKE'
            if failure=='unknown':configuration['source_link_states'][0]['source_link_id']='invented-closure'
            if failure=='missing':configuration['source_link_states'].pop()
            if failure=='duplicate':configuration['source_link_states'][0]=copy.deepcopy(configuration['source_link_states'][1])
            if failure=='closed':configuration['source_link_states'][0]['state']='CLOSED'
            if failure=='boolean':configuration['source_link_states'][0]['state']=True
            if failure=='duplicate-method':rows.append(copy.deepcopy(rows[0]))
            with self.subTest(failure=failure),self.assertRaises(StudioError):derive_dressing_contract(*values)

    def test_missing_free_face_is_needs_data_and_permanent_detachable_change_never_keeps_old_configuration(self):
        values=hood_yoke_fixture();data=values[1]['source.hood-yoke']['data'];data['pieces']['hood-left']['edges'].pop('face-free')
        values[0]['textiles']['hood-left']['source_geometry']=copy.deepcopy(data['pieces']['hood-left'])
        values[5]['source.hood-yoke']['source_sha256']=digest(data)
        result=derive_dressing_contract(*values)
        self.assertIn('HOOD_EXPLICIT_FREE_FACE_AND_PERMANENT_NECK_BINDINGS_REQUIRED',{row['reason'] for row in result['diagnostics']})
        self.assertFalse(any(row['method']=='OPEN_HOOD_YOKE' for row in result['methods']))
        values=hood_yoke_fixture(True);data=values[1]['source.hood-yoke']['data'];data['seams'][-2]['kind']='permanent'
        values[5]['source.hood-yoke']['source_sha256']=digest(data)
        with self.assertRaisesRegex(StudioError,'absent or unresolved'):derive_dressing_contract(*values)
