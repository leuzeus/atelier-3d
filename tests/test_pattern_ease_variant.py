import copy
import json
import math
import zipfile
from types import SimpleNamespace
from unittest.mock import patch

from a3d.core import StudioError,atomic_json,digest,sha
from a3d.packages import build_package,inspect_package
from a3d.production_dossier import compile_production_dossier
from a3d.pattern_ease_variant import (prepare_pattern_ease_variant,prepare_project_pattern_ease_variant,_svg,_seams,
    _weighted_transport,_review,_source_reference_path)
from tests.test_core import Case
from tests.test_garment_planner import example as planner_example


def fixture(mode='WIDTH_BY_V_STATIONS'):
    polygons={'sleeve':[[2.,0.],[5.,0.],[8.,0.],[9.,5.],[10.,10.],[5.,12.],[0.,10.],[1.,5.]],
        'cuff':[[2.5,0.],[5.,0.],[7.5,0.],[7.75,4.],[8.,8.],[5.,8.],[2.,8.],[2.25,4.]],
        'coat-front':[[0.,0.],[5.,2.],[10.,0.]]}
    edges={'sleeve':{'cuff':[0,1,2],'back':[2,3,4],'cap-back':[4,5],'cap-front':[5,6],'front':[6,7,0]},
        'cuff':{'wrist':[0,1,2],'back':[2,3,4],'join':[4,5,6],'front':[6,7,0]},
        'coat-front':{'arm-front':[0,1],'arm-back':[1,2],'hem':[2,0]}}
    data={'component_id':'garment.test','units':'cm','pieces':{pid:{'vertices':points,'faces':[list(range(len(points)))],
        'edges':edges[pid],'position_cm':[0.,0.,0.],'rotation_degrees':[0.,0.,0.]}for pid,points in polygons.items()},
        'seams':[{'id':name,'piece_a':a,'edge_a':ea,'piece_b':b,'edge_b':eb,'orientation':orientation,'kind':'permanent'}
            for name,a,ea,b,eb,orientation in [('sleeve-underarm','sleeve','front','sleeve','back','reverse'),
                ('cuff-join','sleeve','cuff','cuff','join','reverse'),('cuff-underarm','cuff','front','cuff','back','reverse'),
                ('arm-front','sleeve','cap-front','coat-front','arm-front','forward'),
                ('arm-back','sleeve','cap-back','coat-front','arm-back','forward')]],
        'material':{'mass_kg':.1,'tension_stiffness':20.,'compression_stiffness':20.,'shear_stiffness':10.,'bending_stiffness':.3}}
    data['pieces']['sleeve']['faces']=[[5,6,7],[5,7,0],[5,0,1],[5,1,2],[5,2,3],[5,3,4]]
    data['pieces']['cuff']['faces']=[[3,4,5],[3,5,6],[3,6,7],[3,7,0],[3,0,1],[3,1,2]]
    annotations=[]
    for pid,piece in data['pieces'].items():
        marks=[{'id':seam['id']+'-mid','seam_id':seam['id'],'position':.5,'symbol':'notch'}for seam in data['seams']if pid in(seam['piece_a'],seam['piece_b'])]
        annotations.append({'id':pid,'grain_direction':[0,1],'dimensions_cm':[max(p[0]for p in piece['vertices'])-min(p[0]for p in piece['vertices']),max(p[1]for p in piece['vertices'])],
            'seam_allowance_cm':0.,'pattern':{'cut_quantity':1,'cut_outline_cm':copy.deepcopy(piece['vertices']),
                'folds':[],'assembly_marks':marks}})
    dossier={'asset_id':'variant.test','units':'cm','components':{'garment.test':{'pipeline':'PATTERN_SEWN','pieces':annotations},
        'prop.buckle':{'pipeline':'MULTIVIEW_PART','pieces':[{'id':'buckle'}]}}}
    old=planner_example();ref={'path':'source.garmentpkg','sha256':'a'*64};source={'path':'dossier.json','sha256':'b'*64}
    semantics={pid:{'role':role,'side':'left','layer':'cloth','longitudinal_uv_axis':'v'}for pid,role in(('sleeve','sleeve'),('cuff','cuff'),('coat-front','front'))}
    spec={'version':1,'source_ref':source,'body_ref':old['body_ref'],'packages':[{'component_id':'garment.test','source_ref':ref}],
        'piece_semantics':semantics,'layers':{'version':1,'source_ref':source,'mode':'ordered','interaction':'one_way_declared',
            'nodes':[{'id':'body','kind':'body','panels':[],'colliders':['body'],'source_ref':source},
                {'id':'cloth','kind':'garment','panels':list(data['pieces']),'colliders':[],'source_ref':source}],
            'inside_to_outside':[['body','cloth']]},'budgets':old['budgets']}
    compiled=compile_production_dossier(dossier,{'garment.test':{'source_ref':ref,'data':data}},spec)
    targets=[]
    for landmark,body,ease in(('upper-arm.left',7.,5.),('wrist.left',4.,1.)):
        targets.append({'body_landmark':landmark,'body_girth_cm':body,'ease_cm':{'minimum':ease-.01,'target':ease,'maximum':ease+.01,
            'movement':ease,'underlayers':0.,'style':0.},'body_plus_target_cm':body+ease,
            'body_plus_target_interpretation':'CLOSED_LIMB_NOMINAL_REFERENCE_REQUIRES_HOMOLOGY'})
    decision={'status':'NUMERIC_EASE_DESIGN_INTENT_APPROVED','approved':True,'component_ids':['garment.test'],
        'dossier_ref':source,'body_ref':spec['body_ref'],'approved_scope':['numeric_ease_design_targets','underlayer_intent'],
        'targets':targets,'underlayer':'LIGHT_TOP','source_ref':'fixture:user','statement':'approve explicit design only',
        'proposal_ref':{'path':'numeric.json','sha256':'d'*64},'review_ref':{'path':'review.json','sha256':'e'*64}}
    fixed=lambda x:{'minimum':x,'initial':x,'maximum':x}
    free=lambda x,lo,hi:{'minimum':lo,'initial':x,'maximum':hi}
    if mode=='WIDTH_BY_V_STATIONS':
        families=[{'id':'sleeve','pieces':['sleeve'],'mode':mode,'width_center':'SOURCE_BOUNDS_CENTER',
            'stations':[{'v_cm':v,'scale_x':value}for v,value in((0.,fixed(1.)),(5.,free(1.,1.,2.)),(10.,fixed(1.)),(12.,fixed(1.)))]}]
    else:
        families=[{'id':pid,'pieces':[pid],'mode':mode,'anchor_vertices':{pid:1},'scale_x':free(1.,.8,2.),'scale_y':fixed(1.)}for pid in('sleeve','cuff')]
    paths=[{'id':'design.'+pid,'body_landmark':name,'component_id':'garment.test','layer':'cloth','path_kind':'closed_girth',
        'objective':'TARGET'if pid=='sleeve'else'BOUNDS','path_parameterization':'SOURCE_V_CM','source_v_cm':5. if pid=='sleeve'else 0.,
        'segments':[{'piece':pid,'from':{'edge':'front','fraction':fraction},'to':{'edge':'back','fraction':1-fraction}}],
        'joins':['garment.test::'+pid+'-underarm'],'engaged_links':[],'takeup':[]}
        for pid,name,fraction in(('sleeve','upper-arm.left',.5),('cuff','wrist.left',1.))]
    policy={'version':1,'compiled_sha256':digest(compiled),'design_decision_ref':{'path':'decision.json','sha256':'c'*64},
        'body_ref':spec['body_ref'],'dossier_ref':source,'unlisted_pieces':'PRESERVE_EXACT','families':families,'nominal_paths':paths,
        'constraints':{'seam_length_absolute_cm':.00001,'seam_length_relative':.0000001,'target_absolute_cm':.00001,'target_weight':1.,'seam_weight':100.},
        'budgets':{'max_iterations':50,'max_evaluations':1000,'max_seconds':10.,'finite_difference_step':.0001,'damping':.00001,'minimum_step':.0001,'stagnation_iterations':3}}
    return compiled,{'garment.test':data},decision,policy,dossier,spec


def source_reference_fixture():
    from tests.test_garment_measurements import collar_cycle_fixture
    c,_,_,_=collar_cycle_fixture();cid='textile.unusual';pid='band.named'
    data={'component_id':cid,'units':'cm','pieces':{p:copy.deepcopy(r['source_geometry'])for p,r in c['textiles'].items()},
        'seams':[{k:link[k]for k in('piece_a','piece_b','edge_a','edge_b','orientation','kind')}|{'id':link['source_link_id']}for link in c['links']],
        'material':{'mass_kg':.1,'tension_stiffness':20.,'compression_stiffness':20.,'shear_stiffness':10.,'bending_stiffness':.3}}
    data['pieces']['insert.named']['vertices']=[[-math.sqrt(3),1.],[0.,2.],[math.sqrt(3),1.]]
    annotations=[]
    for p,piece in data['pieces'].items():
        piece.update(position_cm=[0.,0.,0.],rotation_degrees=[0.,0.,0.])
        marks=[{'id':s['id']+'-mid','seam_id':s['id'],'position':.5,'symbol':'notch'}for s in data['seams']if p in(s['piece_a'],s['piece_b'])]
        annotations.append({'id':p,'grain_direction':[0,1],
            'dimensions_cm':[max(v[k]for v in piece['vertices'])-min(v[k]for v in piece['vertices'])for k in(0,1)],
            'seam_allowance_cm':0.,'pattern':{'cut_quantity':1,'cut_outline_cm':copy.deepcopy(piece['vertices']),'folds':[],'assembly_marks':marks}})
    dossier={'asset_id':'variant.source.reference','units':'cm','components':{cid:{'pipeline':'PATTERN_SEWN','pieces':annotations}}}
    _,_,_,policy,_,spec=fixture();spec=copy.deepcopy(spec);ref=spec['packages'][0]['source_ref']
    spec['packages']=[{'component_id':cid,'source_ref':ref}]
    spec['piece_semantics']={p:{**r['semantics'],'layer':'cloth','longitudinal_uv_axis':'u'if p==pid else'v'}for p,r in c['textiles'].items()}
    spec['layers']['nodes'][1]['panels']=list(data['pieces'])
    compiled=compile_production_dossier(dossier,{cid:{'source_ref':ref,'data':data}},spec)
    segment={'piece':pid,'from':{'edge':'stop.a','fraction':1.},'to':{'edge':'stop.b','fraction':0.}}
    target={'body_landmark':'neck','body_reference_length_cm':12.,'ease_total_cm':2.,'target_material_length_cm':14.,
        'body_plus_target_interpretation':'ASSEMBLED_SOURCE_PATH_TARGET_ONLY','source_path_ref':{'path':'comparison.json','sha256':'d'*64},
        'material_reference':{'domain':'PERMANENT_ENDPOINT_CYCLE','component_id':cid,'piece':pid,'source_geometry_sha256':digest(data['pieces'][pid]),
            'source_v_cm':0.,'segments':[segment],'source_material_length_cm':12.}}
    decision={'status':'SOURCE_PATH_DESIGN_INTENT_APPROVED','approved':True,'component_ids':[cid],
        'approved_scope':['assembled_source_path_design_targets'],'body_ref':spec['body_ref'],'dossier_ref':spec['source_ref'],
        'targets':[target],'proposal_ref':target['source_path_ref'],'review_ref':{'path':'intent.json','sha256':'e'*64}}
    fixed={'minimum':1.,'initial':1.,'maximum':1.};free={'minimum':1.,'initial':1.,'maximum':1.5}
    weights=[(max(0.,min(u-2.,8.))/u if u else 0.)for u,v in data['pieces'][pid]['vertices']]
    policy.update(compiled_sha256=digest(compiled),body_ref=spec['body_ref'],dossier_ref=spec['source_ref'],
        families=[{'id':'local.band','pieces':[pid],'mode':'WEIGHTED_SOURCE_UV','anchor_vertices':{pid:0},
                   'weights_by_piece':{pid:weights},'protected_edges_by_piece':{pid:[]},'scale_x':free,'scale_y':fixed},
                  {'id':'local.partner','pieces':['neck.named'],'mode':'AFFINE_SOURCE_UV','anchor_vertices':{'neck.named':0},
                   'scale_x':copy.deepcopy(free),'scale_y':copy.deepcopy(fixed)}],
        nominal_paths=[{'id':'design.source.neck','body_landmark':'neck','component_id':cid,'layer':'cloth','path_kind':'open_material_span',
            'objective':'TARGET','path_parameterization':'SOURCE_V_CM','source_v_cm':0.,'segments':[segment],
            'joins':[],'engaged_links':[],'takeup':[]}])
    return compiled,{cid:data},decision,policy,dossier,spec


class PatternEaseVariant(Case):
    def test_assembled_source_reference_reaches_a_separate_coupled_variant_without_girth_promotion(self):
        c,data,d,p,_,_=source_reference_fixture();before=digest([c,data,d,p])
        result=prepare_pattern_ease_variant(c,data,d,p)
        self.assertEqual(result['status'],'PROPOSAL_READY_FOR_REVIEW');self.assertTrue(result['packages_allowed_for_review'])
        check=result['target_checks'][0]
        self.assertAlmostEqual(check['material_length_cm'],14.,places=5)
        self.assertEqual(check['assembled_row_topology']['status'],'CLOSED_PERMANENT_ENDPOINT_CYCLE')
        self.assertEqual(check['assembled_row_topology']['source_neckline_attachment']['coverage'],'FULL_SOURCE_ROW_ONCE')
        self.assertEqual(check['path_kind'],'open_material_span');self.assertEqual(check['body_reference_length_cm'],12.)
        self.assertEqual(check['ease_total_cm'],2.);self.assertNotIn('body_girth_cm',check)
        self.assertEqual(check['qualification'],'SOURCE_REFERENCE_TARGET_ONLY');self.assertFalse(check['admissible_for_fit'])
        candidate=result['candidate_garments']['textile.unusual']
        self.assertEqual(candidate['seams'],data['textile.unusual']['seams'])
        self.assertEqual(candidate['pieces']['insert.named'],data['textile.unusual']['pieces']['insert.named'])
        self.assertTrue(all(row['status']=='COMPATIBLE'for row in result['seam_constraints']))
        self.assertTrue(all(mark['status']=='MATERIAL_POINT_PRESERVED'for mark in result['material_notches']))
        self.assertTrue(all(row['faces_preserved']and row['edges_preserved']for row in result['piece_diff']))
        self.assertEqual(result['qualification'],'PATTERN_PROPOSAL_ONLY');self.assertEqual(result['acceptance'],'NOT_GRANTED')
        self.assertEqual(digest([c,data,d,p]),before)

    def test_assembled_source_target_rejects_false_homology_reference_or_closure_contract(self):
        for change in('scalar','breakdown','legacy-status','source-ref','domain','geometry','material-length','material-segment','v',
                      'path-kind','join','engaged','distinct-endpoints','normalized-notches','weighted-y'):
            c,data,d,p,_,_=source_reference_fixture();target=d['targets'][0];path=p['nominal_paths'][0]
            if change=='scalar':target['target_material_length_cm']+=.1
            elif change=='breakdown':target['ease_cm']={'target':2.}
            elif change=='legacy-status':d['status']='NUMERIC_EASE_DESIGN_INTENT_APPROVED';d['approved_scope']=['numeric_ease_design_targets','underlayer_intent']
            elif change=='source-ref':target['source_path_ref']['sha256']='wrong'
            elif change=='domain':target['material_reference']['domain']='UNSUPPORTED'
            elif change=='geometry':target['material_reference']['source_geometry_sha256']='f'*64
            elif change=='material-length':target['material_reference']['source_material_length_cm']+=.1
            elif change=='material-segment':target['material_reference']['segments'][0]['from']['fraction']=.5
            elif change=='v':target['material_reference']['source_v_cm']=1.
            elif change=='path-kind':path['path_kind']='closed_girth'
            elif change=='join':path['joins']=['textile.unusual::band.fastener']
            elif change=='engaged':path['engaged_links']=['textile.unusual::band.fastener']
            elif change=='distinct-endpoints':
                c['links'][0]['kind']='closure';data['textile.unusual']['seams'][0]['kind']='closure';p['compiled_sha256']=digest(c)
            elif change=='normalized-notches':p['notch_policy']='NORMALIZED_ARC_FRACTIONS'
            else:p['families'][0]['scale_y']['maximum']=1.1
            with self.subTest(change=change),self.assertRaises(StudioError):prepare_pattern_ease_variant(c,data,d,p)

    def test_weighted_local_uv_keeps_protected_cap_cuff_and_source_notches(self):
        c,data,d,p,_,_=fixture();pid='sleeve'
        p['families']=[{'id':pid,'pieces':[pid],'mode':'WEIGHTED_SOURCE_UV','anchor_vertices':{pid:1},
            'weights_by_piece':{pid:[0.,0.,0.,1.,0.,0.,0.,1.]},
            'protected_edges_by_piece':{pid:['cuff','cap-back','cap-front']},
            'scale_x':{'minimum':1.,'initial':1.,'maximum':2.},'scale_y':{'minimum':1.,'initial':1.,'maximum':1.}}]
        before=digest([c,data,d,p]);r=prepare_pattern_ease_variant(c,data,d,p)
        self.assertTrue(r['packages_allowed_for_review'])
        check=next(row for row in r['target_checks']if row['body_landmark']=='upper-arm.left')
        self.assertAlmostEqual(check['material_length_cm'],12.,places=5)
        piece=r['candidate_garments']['garment.test']['pieces'][pid]
        for index in(0,1,2,4,5,6):self.assertEqual(piece['vertices'][index],data['garment.test']['pieces'][pid]['vertices'][index])
        self.assertEqual(r['candidate_garments']['garment.test']['pieces']['cuff'],data['garment.test']['pieces']['cuff'])
        self.assertTrue(all(m['status']=='MATERIAL_POINT_PRESERVED'for m in r['material_notches']))
        self.assertEqual(digest([c,data,d,p]),before)

    def test_weighted_policy_protection_weights_anchors_and_source_domain_are_strict(self):
        for change in('protected-weight','missing-weights','bool-weight','anchor','missing-edge','nontriangular','cut','allowance'):
            c,data,d,p,_,_=source_reference_fixture();family=p['families'][0];pid='band.named';owner=c['textiles'][pid]
            if change=='protected-weight':family['protected_edges_by_piece'][pid]=['middle']
            elif change=='missing-weights':family['weights_by_piece'][pid].pop()
            elif change=='bool-weight':family['weights_by_piece'][pid][0]=True
            elif change=='anchor':family['anchor_vertices'][pid]=1000
            elif change=='missing-edge':family['protected_edges_by_piece'][pid]=['invented']
            elif change=='nontriangular':
                data['textile.unusual']['pieces'][pid]['faces']=[[0,1,2,3,4,5,6]]
                owner['source_geometry']=copy.deepcopy(data['textile.unusual']['pieces'][pid])
            elif change=='cut':owner['source']['pattern']['cut_outline_cm'][0][0]-=.1
            else:owner['source']['seam_allowance_cm']=.1
            p['compiled_sha256']=digest(c)
            with self.subTest(change=change),self.assertRaises(StudioError):prepare_pattern_ease_variant(c,data,d,p)

    def test_weighted_pl_fold_crossings_match_exact_source_triangle_oracle(self):
        source={'vertices':[[0.,0.],[4.,0.],[4.,4.],[0.,4.]],'faces':[[0,1,2],[0,2,3]],'edges':{'fixed':[0,1]}}
        family={'id':'local','_piece':'arbitrary','anchor_vertices':{'arbitrary':0},'weights_by_piece':{'arbitrary':[0.,0.,1.,0.]}}
        before=digest([source,family]);targets,point,line=_weighted_transport(source,family,{'local:x':1.5,'local:y':1.},lambda:None)
        self.assertEqual(targets,[[0.,0.],[4.,0.],[6.,4.],[0.,4.]])
        self.assertEqual(point([.5,3.5]),[.75,3.5])
        self.assertEqual(line([[.5,3.5],[3.5,.5]]),[[.75,3.5],[3.,2.],[3.75,.5]])
        with self.assertRaises(StudioError):point([-1.,2.])
        with self.assertRaises(StudioError):line([[-1.,2.],[2.,2.]])
        with self.assertRaises(StudioError):line([[.5,.5]]*41)
        with self.assertRaises(StudioError):line([[float('nan'),1.],[1.,1.]])
        self.assertEqual(digest([source,family]),before)
        _,_,identity=_weighted_transport(source,family,{'local:x':1.,'local:y':1.},lambda:None)
        original=[[.5,3.5],[3.5,.5]];self.assertEqual(identity(original),original)

    def test_material_notch_pair_objective_detects_equal_length_but_shifted_material_midpoint(self):
        from a3d.pattern_ease_variant import _paired_material_notch_residuals
        c,data,_,p,_,_=source_reference_fixture();candidate=copy.deepcopy(data)
        candidate['textile.unusual']['pieces']['band.named']['vertices'][2][0]=6.5
        seams=_seams(c,candidate,p['constraints']);self.assertTrue(all(row['status']=='COMPATIBLE'for row in seams))
        annotations={pid:copy.deepcopy(row['source'])for pid,row in c['textiles'].items()}
        residual=_paired_material_notch_residuals(c,c,candidate,annotations,seams)
        self.assertTrue(any(abs(value)>.49 for value in residual))

    def test_source_reference_budget_impossible_protection_and_input_mutation_do_not_admit(self):
        c,data,d,p,_,_=source_reference_fixture();before=digest([c,data,d,p]);p['budgets']['max_evaluations']=1
        result=prepare_pattern_ease_variant(c,data,d,p)
        self.assertEqual(result['status'],'INCOMPLETE_BUDGET');self.assertFalse(result['packages_allowed_for_review'])
        self.assertEqual(result['candidate_garments'],data)
        c,data,d,p,_,_=source_reference_fixture();p['families'][0]['weights_by_piece']['band.named']=[0.]*7
        result=prepare_pattern_ease_variant(c,data,d,p)
        self.assertEqual(result['status'],'REFUSED_CONSTRAINTS');self.assertFalse(result['packages_allowed_for_review'])
        c,data,d,p,_,_=source_reference_fixture();ticks=iter([0.,11.])
        with self.assertRaisesRegex(StudioError,'initial computation time budget'):
            prepare_pattern_ease_variant(c,data,d,p,clock=lambda:next(ticks))
        c,data,d,p,_,_=source_reference_fixture()
        from a3d.pattern_ease_variant import _candidate
        def changed(*args,**kwargs):
            result=_candidate(*args,**kwargs);d['targets'][0]['source_path_ref']['path']='changed.json';return result
        with patch('a3d.pattern_ease_variant._candidate',side_effect=changed),self.assertRaisesRegex(StudioError,'immutable'):
            prepare_pattern_ease_variant(c,data,d,p)

    def test_source_reference_review_delegates_to_specific_canonical_intent(self):
        _,_,decision,_,_,_=source_reference_fixture();project=SimpleNamespace();ref={'path':'decision.json','sha256':'a'*64}
        with patch('a3d.source_path_intent.review_source_path_intent',return_value=[{'gate':'specific-source-intent'}])as method:
            self.assertEqual(_review(project,decision,ref),[{'gate':'specific-source-intent'}])
        method.assert_called_once_with(project,decision,ref)

    def test_attached_source_reference_rechecks_full_candidate_coverage_and_refuses_nonmonotone_row(self):
        from a3d.garment_measurements import _collar_neckline_row
        c,data,d,p,_,_=source_reference_fixture();target=d['targets'][0];row=p['nominal_paths'][0]
        target['material_reference']['attachment']=_collar_neckline_row(c,'band.named',0.,[[0.,0.],[12.,0.]])
        result=prepare_pattern_ease_variant(c,data,d,p)
        self.assertTrue(result['packages_allowed_for_review'])
        proof=result['target_checks'][0]['assembled_row_topology']['source_neckline_attachment']
        self.assertEqual(proof['coverage'],'FULL_SOURCE_ROW_ONCE')
        modified=copy.deepcopy(c);modified['textiles']['band.named']['source_geometry']['vertices'][2][0]=1.5
        with self.assertRaisesRegex(StudioError,'folded or collapsed'):
            _source_reference_path(modified,row,target,d['component_ids'])
        del target['material_reference']['attachment']
        with self.assertRaisesRegex(StudioError,'folded or collapsed'):
            _source_reference_path(modified,row,target,d['component_ids'])

    def dense_policy(self,policy):
        policy=copy.deepcopy(policy)
        policy['nominal_paths'][0]['source_v_cm']=7.
        fixed={'minimum':1.,'initial':1.,'maximum':1.}
        policy['families'][0]['stations'].insert(2,{'v_cm':7.,'scale_x':{'minimum':1.,'initial':1.,'maximum':2.}})
        policy['families'][0]['stations'][1]['scale_x']=copy.deepcopy(fixed)
        policy['families'][0]['densification']={'mode':'SOURCE_BOUNDARY_V_STATIONS',
            'edges_by_piece':{'sleeve':['front','back']},'minimum_segment_length_cm':.00001,
            'max_inserted_vertices_per_piece':4,'face_policy':'SOURCE_TRIANGLE_BOUNDARY_SUBDIVISION'}
        return policy

    def test_densification_reaches_real_exported_station_and_preserves_source_vertices_caps_and_seams(self):
        c,data,d,p,_,_=fixture();before=digest([c,data,d,p]);dense=self.dense_policy(p)
        result=prepare_pattern_ease_variant(c,data,d,dense)
        self.assertEqual(result['status'],'PROPOSAL_READY_FOR_REVIEW');self.assertTrue(result['topology_changed'])
        self.assertEqual(digest([c,data,d,p]),before)
        mapping=result['topology_mappings']['sleeve'];source=data['garment.test']['pieces']['sleeve']
        piece=result['candidate_garments']['garment.test']['pieces']['sleeve']
        self.assertEqual(len(mapping['inserted_vertices']),2);self.assertEqual(len(piece['vertices']),10)
        for i,point in enumerate(source['vertices']):
            self.assertEqual(piece['vertices'][mapping['old_to_new_vertex_indices'][str(i)]],point)
        inserted=[piece['vertices'][row['new_vertex_index']]for row in mapping['inserted_vertices']]
        self.assertTrue(all(point[1]==7. for point in inserted));self.assertAlmostEqual(math.dist(*inserted),12.,places=5)
        self.assertEqual(len(piece['faces']),8);self.assertTrue(all(len(face)==3 for face in piece['faces']))
        self.assertEqual(set(piece['edges']),set(source['edges']))
        self.assertEqual(result['candidate_garments']['garment.test']['seams'],data['garment.test']['seams'])
        self.assertTrue(all(row['status']=='COMPATIBLE'for row in result['seam_constraints']))
        self.assertEqual(result['piece_annotations']['sleeve']['pattern']['cut_outline_cm'],piece['vertices'])
        self.assertEqual([row['id']for row in result['piece_annotations']['sleeve']['pattern']['assembly_marks']],
            [row['id']for row in c['textiles']['sleeve']['source']['pattern']['assembly_marks']])
        self.assertEqual(result['piece_diff'][-1]['source_vertex_max_displacement_cm'],0.)
        sparse=copy.deepcopy(p);sparse['nominal_paths'][0]['source_v_cm']=7.
        sparse_result=prepare_pattern_ease_variant(c,data,d,sparse)
        self.assertEqual(sparse_result['status'],'PROPOSAL_READY_FOR_REVIEW')
        self.assertGreater(sparse_result['candidate_garments']['garment.test']['pieces']['sleeve']['vertices'][3][0],max(point[0]for point in piece['vertices']))

    def test_density_is_explicit_bounded_and_requires_exact_supported_source_cut_and_partner_edges(self):
        for change in('missing-option','wrong-edges','one-vertex-budget','allowance','cut','segment-budget','duplicate-station'):
            c,data,d,p,_,_=fixture();p=self.dense_policy(p)
            if change=='missing-option':p['families'][0].pop('densification')
            elif change=='wrong-edges':p['families'][0]['densification']['edges_by_piece']['sleeve']=['cap-front','cap-back']
            elif change=='one-vertex-budget':p['families'][0]['densification']['max_inserted_vertices_per_piece']=1
            elif change=='allowance':c['textiles']['sleeve']['source']['seam_allowance_cm']=1.;p['compiled_sha256']=digest(c)
            elif change=='cut':c['textiles']['sleeve']['source']['pattern']['cut_outline_cm'][0][0]+=.1;p['compiled_sha256']=digest(c)
            elif change=='segment-budget':p['families'][0]['stations'][2]['v_cm']=5.000001;p['families'][0]['densification']['minimum_segment_length_cm']=.01
            else:p['families'][0]['stations'].insert(2,copy.deepcopy(p['families'][0]['stations'][2]))
            with self.subTest(change=change),self.assertRaises(StudioError):prepare_pattern_ease_variant(c,data,d,p)

    def test_density_minimum_segment_checks_adjacent_insertions_not_only_original_endpoints(self):
        c,data,d,p,_,_=fixture();p=self.dense_policy(p);before=digest([c,data,d,p])
        p['families'][0]['densification']['minimum_segment_length_cm']=.01
        fixed={'minimum':1.,'initial':1.,'maximum':1.}
        p['families'][0]['stations'].extend([{'v_cm':6.,'scale_x':copy.deepcopy(fixed)},{'v_cm':6.0001,'scale_x':copy.deepcopy(fixed)}])
        p['families'][0]['stations'].sort(key=lambda row:row['v_cm'])
        p['families'][0]['densification']['max_inserted_vertices_per_piece']=6
        after_edit=digest([c,data,d,p])
        with self.assertRaisesRegex(StudioError,'breakpoints create a segment'):
            prepare_pattern_ease_variant(c,data,d,p)
        self.assertEqual(digest([c,data,d,p]),after_edit);self.assertNotEqual(before,after_edit)

    def test_density_records_explicit_source_face_region_replacement_including_all_inserted_vertices(self):
        c,data,d,p,_,_=fixture();piece=data['garment.test']['pieces']['sleeve']
        result=prepare_pattern_ease_variant(c,data,d,self.dense_policy(p));mapping=result['topology_mappings']['sleeve']
        self.assertEqual(result['status'],'PROPOSAL_READY_FOR_REVIEW')
        self.assertFalse(mapping['face_count_preserved']);self.assertEqual(mapping['source_face_count'],6)
        self.assertEqual(mapping['variant_face_count'],8)
        self.assertEqual(sorted(i for cohort in mapping['old_to_new_face_regions'].values()for i in cohort),list(range(8)))
        faces=result['candidate_garments']['garment.test']['pieces']['sleeve']['faces']
        self.assertTrue(all(any(row['new_vertex_index']in face for face in faces)for row in mapping['inserted_vertices']))
        piece['faces']=[[5,6,7],[5,7,0],[5,0,2],[5,2,3],[5,3,4]]
        c['textiles']['sleeve']['source_geometry']=copy.deepcopy(piece);p['compiled_sha256']=digest(c)
        with self.assertRaisesRegex(StudioError,'cover the actual material boundary'):
            prepare_pattern_ease_variant(c,data,d,self.dense_policy(p))

    def test_station_variant_changes_actual_polygon_and_keeps_caps_distal_lengths_ids_grain_and_pairs(self):
        c,data,d,p,_,_=fixture();before=digest([c,data,d,p]);result=prepare_pattern_ease_variant(c,data,d,p)
        self.assertEqual(result['status'],'PROPOSAL_READY_FOR_REVIEW');self.assertTrue(result['packages_allowed_for_review'])
        self.assertEqual(digest([c,data,d,p]),before);check=next(row for row in result['target_checks']if row['body_landmark']=='upper-arm.left')
        self.assertAlmostEqual(check['material_length_cm'],12.,places=5)
        variant=result['candidate_garments']['garment.test'];source=data['garment.test']
        self.assertEqual(variant['pieces']['cuff'],source['pieces']['cuff']);self.assertEqual(variant['pieces']['coat-front'],source['pieces']['coat-front'])
        self.assertEqual(variant['seams'],source['seams']);self.assertEqual(variant['pieces']['sleeve']['vertices'][3][1],5.)
        self.assertAlmostEqual(variant['pieces']['sleeve']['vertices'][3][0]-variant['pieces']['sleeve']['vertices'][7][0],12.,places=5)
        for i in(0,1,2,4,5,6):self.assertEqual(variant['pieces']['sleeve']['vertices'][i],source['pieces']['sleeve']['vertices'][i])
        self.assertTrue(all(row['status']=='COMPATIBLE'for row in result['seam_constraints']))
        self.assertTrue(all(row.get('self_seam_parameterization','COMPATIBLE')=='COMPATIBLE'for row in result['seam_constraints']))
        self.assertTrue(all(row['faces_preserved']and row['edges_preserved']and row['assembly_mark_identifiers_preserved']and row['material_notch_points_preserved']for row in result['piece_diff']))
        self.assertEqual(result['rigid_parts'],c['rigid_parts']);self.assertEqual(result['qualification'],'PATTERN_PROPOSAL_ONLY')
        self.assertEqual(result['homology'],'PENDING');self.assertEqual(result['acceptance'],'NOT_GRANTED')

    def test_affine_conflict_preserves_best_candidate_and_refuses_incompatible_permanent_arcs(self):
        c,data,d,p,_,_=fixture('AFFINE_SOURCE_UV');result=prepare_pattern_ease_variant(c,data,d,p)
        self.assertEqual(result['status'],'REFUSED_CONSTRAINTS');self.assertFalse(result['packages_allowed_for_review'])
        self.assertLess(result['solver']['best_score'],result['solver']['initial_score']);self.assertIn('candidate_garments',result)
        self.assertTrue(any(row['code']=='PERMANENT_ARC_CONSTRAINT_INCOMPATIBLE'for row in result['diagnostics']))
        self.assertEqual(result['candidate_garments']['garment.test']['seams'],data['garment.test']['seams'])

    def test_source_inventory_decision_anatomy_and_non_vertex_stations_cannot_be_substituted(self):
        for change in('compiled','body','source','kind','decision','wrong-side','station','propagate-owner','override'):
            c,data,d,p,_,_=fixture()
            if change=='compiled':p['compiled_sha256']='f'*64
            elif change=='body':d['body_ref']={'path':'wrong.json','sha256':'f'*64}
            elif change=='source':data['garment.test']['pieces']['sleeve']['vertices'][3][0]+=1.
            elif change=='kind':data['garment.test']['seams'][0]['kind']='closure'
            elif change=='decision':d['approved']=False
            elif change=='wrong-side':p['nominal_paths'][0]['body_landmark']='upper-arm.right'
            elif change=='station':p['families'][0]['stations'][1]['v_cm']=4.
            elif change=='propagate-owner':p['families'][0]['pieces'].append('buckle')
            else:p['families'][0]['manual_uv']=[[1.,2.]]
            with self.subTest(change=change),self.assertRaises(StudioError):prepare_pattern_ease_variant(c,data,d,p)

    def test_open_torso_targets_remain_unresolved_and_cannot_supply_a_closed_scale(self):
        c,data,d,p,_,_=fixture();d['targets'].append({'body_landmark':'chest','body_girth_cm':100.,
            'ease_cm':{'minimum':16.,'target':20.,'maximum':24.,'movement':6.,'underlayers':2.,'style':12.},
            'body_plus_target_cm':120.,'body_plus_target_interpretation':'SPATIAL_REFERENCE_ENVELOPE_NOT_CLOSED_MATERIAL_GIRTH'})
        result=prepare_pattern_ease_variant(c,data,d,p)
        self.assertEqual(result['status'],'NEEDS_DATA');self.assertEqual(result['diagnostics'][0]['code'],'OPEN_COVERAGE_OVERLAP_REQUIRED')
        p['nominal_paths'][0]['body_landmark']='chest'
        with self.assertRaisesRegex(StudioError,'open torso/collar'):prepare_pattern_ease_variant(c,data,d,p)

    def test_solver_budget_stops_and_retains_source_bound_best_candidate(self):
        c,data,d,p,_,_=fixture();p['budgets']['max_evaluations']=1
        result=prepare_pattern_ease_variant(c,data,d,p)
        self.assertEqual(result['solver']['stop_reason'],'TIME_OR_EVALUATION_BUDGET');self.assertEqual(result['solver']['evaluations'],1)
        self.assertEqual(result['candidate_garments'],data);self.assertFalse(result['packages_allowed_for_review'])
        ticks=iter(i*.01 for i in range(100));p['budgets']['max_seconds']=.001
        result=prepare_pattern_ease_variant(c,data,d,p,clock=lambda:next(ticks))
        self.assertEqual(result['status'],'INCOMPLETE_BUDGET');self.assertEqual(result['candidate_garments'],data)
        self.assertFalse(result['packages_allowed_for_review'])

    def test_deadline_expiring_during_diff_cannot_return_ready_or_publish_archives(self):
        from a3d.pattern_ease_variant import _bounds
        from a3d.board_contract import validate_patterns
        elapsed=[0.];validated=[False]
        def validation(*args):
            result=validate_patterns(*args);validated[0]=True;return result
        def delayed_bounds(*args):
            result=_bounds(*args)
            if validated[0]:elapsed[0]=11.
            return result
        c,data,d,p,_,_=fixture();before=digest([c,data,d,p])
        with patch('a3d.pattern_ease_variant.validate_patterns',side_effect=validation), \
                patch('a3d.pattern_ease_variant._bounds',side_effect=delayed_bounds):
            result=prepare_pattern_ease_variant(c,data,d,p,clock=lambda:elapsed[0])
        self.assertEqual(result['status'],'INCOMPLETE_BUDGET');self.assertFalse(result['packages_allowed_for_review'])
        self.assertEqual(result['solver']['stop_reason'],'TIME_BUDGET_POSTPROCESSING')
        self.assertEqual(result['solver']['seconds_elapsed'],11.)
        self.assertTrue(result['piece_diff']);self.assertTrue(result['candidate_garments'])
        self.assertEqual(result['proposal_sha256'],digest({key:value for key,value in result.items()if key!='proposal_sha256'}))
        self.assertEqual(digest([c,data,d,p]),before)
        project,_,_,_=self.project_fixture();elapsed[0]=0.;validated[0]=False
        original=prepare_pattern_ease_variant
        def bounded(*args):return original(*args,clock=lambda:elapsed[0])
        with patch('a3d.pattern_ease_variant.prepare_pattern_ease_variant',side_effect=bounded), \
                patch('a3d.pattern_ease_variant.validate_patterns',side_effect=validation), \
                patch('a3d.pattern_ease_variant._bounds',side_effect=delayed_bounds):
            published=prepare_project_pattern_ease_variant(project,'compiled.json','decision.json','policy.json','variants/late-budget')
        self.assertEqual(published['status'],'INCOMPLETE_BUDGET');self.assertEqual(published['packages'],{})
        self.assertTrue((self.root/'variants/late-budget/candidate-garments.json').is_file())
        self.assertFalse((self.root/'variants/late-budget/packages').exists())

    def test_minimal_source_target_derives_only_its_nominal_identifier_type_and_optional_original_length(self):
        c,data,d,p,_,_=source_reference_fixture();target=d['targets'][0]
        for key in('body_landmark','body_plus_target_interpretation'):target.pop(key)
        target['material_reference'].pop('source_material_length_cm')
        for key in('proposal_ref','review_ref'):d.pop(key)
        p['nominal_paths'][0]['body_landmark']='source-boundary.band.named'
        before=digest([c,data,d,p]);result=prepare_pattern_ease_variant(c,data,d,p)
        self.assertEqual(result['status'],'PROPOSAL_READY_FOR_REVIEW')
        self.assertEqual(result['target_checks'][0]['body_landmark'],'source-boundary.band.named')
        self.assertEqual(result['target_checks'][0]['target_interpretation'],'ASSEMBLED_SOURCE_PATH_TARGET_ONLY')
        self.assertNotIn('body_girth_cm',result['target_checks'][0]);self.assertEqual(digest([c,data,d,p]),before)

    def test_project_source_decision_has_no_legacy_proposal_or_review_reference_requirement(self):
        c,data,d,p,dossier,spec=source_reference_fixture();cid='textile.unusual'
        def stored(name,value):
            atomic_json(self.root/name,value);return {'path':name,'sha256':sha(self.root/name)}
        body_ref=stored('source-body.json',{'scope':'SYNTHETIC_FACADE_ADAPTER_ONLY'})
        dossier_ref=stored('source-dossier.json',dossier)
        source=self.root/'source-band';source.mkdir();atomic_json(source/'garment.json',data[cid])
        (source/'pattern.svg').write_bytes(_svg(data[cid]))
        package=build_package(source,self.root/'source-band.garmentpkg',dossier['asset_id'],cid,'PATTERN_SEWN',
            {'source':'test','created_by':'unit adapter fixture','notes':'TEST_ONLY'})
        package_ref={'path':'source-band.garmentpkg','sha256':package['sha256']}
        spec.update(source_ref=dossier_ref,body_ref=body_ref);spec['packages'][0]['source_ref']=package_ref
        spec['layers']['source_ref']=dossier_ref
        for node in spec['layers']['nodes']:node['source_ref']=dossier_ref
        spec_ref=stored('source-specification.json',spec)
        c=compile_production_dossier(dossier,{cid:{'source_ref':package_ref,'data':data[cid]}},spec)
        c['specification_source_ref']=spec_ref;c['compiled_sha256']=digest({key:value for key,value in c.items()if key!='compiled_sha256'})
        d.update(body_ref=body_ref,dossier_ref=dossier_ref,production_specification_ref=spec_ref)
        for key in('proposal_ref','review_ref'):d.pop(key)
        target=d['targets'][0]
        target['source_path_ref']=stored('source-comparison.json',{'scope':'SYNTHETIC_ADAPTER_ONLY'})
        target['human_intent_ref']=stored('source-intent.json',{'scope':'SYNTHETIC_ADAPTER_ONLY'})
        target['human_review_gate']='source.target';target['material_reference'].pop('source_material_length_cm')
        target['material_reference']['source_geometry_sha256']=digest(c['textiles']['band.named']['source_geometry'])
        decision_ref=stored('source-decision.json',d)
        p.update(compiled_sha256=digest(c),body_ref=body_ref,dossier_ref=dossier_ref,design_decision_ref=decision_ref)
        stored('source-compiled.json',c);stored('source-policy.json',p)
        project=SimpleNamespace(root=self.root)
        # Canonical admission is tested independently in test_source_path_intent.
        # This adapter probe verifies its callback and the exact file inventory.
        with patch('a3d.source_path_intent.review_source_path_intent',return_value=[{'gate':'source.target'}])as reviewed:
            result=prepare_project_pattern_ease_variant(project,'source-compiled.json','source-decision.json','source-policy.json','variants/source-adapter')
        self.assertEqual(result['status'],'PROPOSAL_READY_FOR_REVIEW');self.assertEqual(reviewed.call_count,3)
        artifact=json.loads((self.root/'variants/source-adapter/proposal.json').read_bytes())
        self.assertIn(spec_ref,artifact['input_refs']);self.assertIn(target['source_path_ref'],artifact['input_refs'])
        self.assertIn(target['human_intent_ref'],artifact['input_refs']);self.assertTrue(result['packages'])

    @staticmethod
    def narrow_weighted_source(initial=1.):
        c,data,d,p,_,_=source_reference_fixture();pid='band.named';cid='textile.unusual'
        source=data[cid]['pieces'][pid];source['vertices'][6][0]=10.9
        c['textiles'][pid]['source_geometry']=copy.deepcopy(source)
        c['textiles'][pid]['source']['pattern']['cut_outline_cm']=copy.deepcopy(source['vertices'])
        d['targets'][0]['material_reference']['source_geometry_sha256']=digest(source)
        p['families'][0]['weights_by_piece'][pid][6]=1.
        p['families'][0]['scale_x']['initial']=initial
        p['families'][1]['scale_x']['initial']=initial
        p['compiled_sha256']=digest(c)
        return c,data,d,p

    def test_actual_weighted_face_barrier_preserves_valid_best_when_target_would_invert_a_source_face(self):
        c,data,d,p=self.narrow_weighted_source();before=digest([c,data,d,p])
        result=prepare_pattern_ease_variant(c,data,d,p);domain=result['solver']['geometry_domain']
        self.assertTrue(domain['enabled']);self.assertTrue(domain['best_valid'])
        self.assertGreater(domain['rejected_evaluations'],0)
        self.assertTrue(any(w['code']=='VARIANT_FACE_ORIENTATION_INVALID'for row in domain['rejections']for w in row['witnesses']))
        self.assertEqual(result['status'],'REFUSED_CONSTRAINTS');self.assertFalse(result['packages_allowed_for_review'])
        self.assertFalse(any(row['code']=='VARIANT_FACE_ORIENTATION_INVALID'for row in result['diagnostics']))
        for diff in result['piece_diff']:self.assertTrue(diff['faces_preserved']);self.assertTrue(diff['edges_preserved'])
        self.assertEqual(digest([c,data,d,p]),before)

    def test_finite_difference_uses_valid_opposite_side_and_invalid_initial_configuration_is_refused(self):
        c,data,d,p=self.narrow_weighted_source(1.03447)
        result=prepare_pattern_ease_variant(c,data,d,p);domain=result['solver']['geometry_domain']
        self.assertTrue(domain['best_valid'])
        self.assertTrue(any(row['phase']=='FINITE_DIFFERENCE'for row in domain['rejections']))
        c,data,d,p=self.narrow_weighted_source(1.05)
        result=prepare_pattern_ease_variant(c,data,d,p)
        self.assertEqual(result['solver']['stop_reason'],'INITIAL_GEOMETRY_INVALID')
        self.assertFalse(result['solver']['geometry_domain']['best_valid']);self.assertFalse(result['packages_allowed_for_review'])
        self.assertEqual(result['status'],'REFUSED_CONSTRAINTS')

    def test_solver_uses_representable_actual_step_for_very_narrow_legal_intervals_at_both_endpoints(self):
        for endpoint in(1.,1.+1e-13):
            c,data,d,p,_,_=fixture();p['families'][0]['stations'][1]['scale_x']={'minimum':1.,'initial':endpoint,'maximum':1.+1e-13}
            result=prepare_pattern_ease_variant(c,data,d,p)
            self.assertEqual(result['status'],'REFUSED_CONSTRAINTS');self.assertFalse(result['packages_allowed_for_review'])
            self.assertTrue(1.<=result['solver']['parameters']['sleeve:station:1']<=1.+1e-13)

    def test_fixed_v_is_recomputed_after_arc_changes_and_bounds_objective_preserves_wrist_in_range(self):
        c,data,d,p,_,_=fixture();piece=data['garment.test']['pieces']['sleeve']
        for i in(3,7):piece['vertices'][i][1]=3.
        c['textiles']['sleeve']['source_geometry']=copy.deepcopy(piece)
        c['textiles']['sleeve']['source']['pattern']['cut_outline_cm']=copy.deepcopy(piece['vertices'])
        p['compiled_sha256']=digest(c);p['families'][0]['stations'][1]['v_cm']=3.
        wrist=d['targets'][1];wrist['ease_cm'].update(minimum=.5,target=2.,maximum=3.,movement=2.)
        wrist['body_plus_target_cm']=6.
        result=prepare_pattern_ease_variant(c,data,d,p)
        self.assertEqual(result['status'],'PROPOSAL_READY_FOR_REVIEW')
        sleeve=next(row for row in result['target_checks']if row['body_landmark']=='upper-arm.left')
        self.assertAlmostEqual(sleeve['material_length_cm'],12.,places=5)
        self.assertNotAlmostEqual(sleeve['actual_segments'][0]['from']['fraction'],.5,places=3)
        for row in sleeve['actual_source_spans']:
            self.assertAlmostEqual(row['from_uv_cm'][1],5.,places=9);self.assertAlmostEqual(row['to_uv_cm'][1],5.,places=9)
        self.assertEqual(result['candidate_garments']['garment.test']['pieces']['cuff'],data['garment.test']['pieces']['cuff'])
        self.assertEqual(next(row for row in result['target_checks']if row['body_landmark']=='wrist.left')['target_residual_cm'],-1.)

    def test_equal_self_seam_totals_cannot_hide_nonhomologous_arc_station_increments(self):
        c,data,d,p,_,_=fixture();candidate=copy.deepcopy(data);piece=candidate['garment.test']['pieces']['cuff']
        for i,point in{0:[2.,0.],2:[8.,0.],3:[8.,3.],4:[8.,8.],6:[2.,8.],7:[2.,5.]}.items():piece['vertices'][i]=point
        seam=next(row for row in _seams(c,candidate,p['constraints'])if row['id']=='garment.test::cuff-underarm')
        self.assertEqual(seam['mismatch_cm'],0.);self.assertEqual(seam['status'],'INCOMPATIBLE')
        self.assertEqual(seam['self_seam_parameterization'],'INCOMPATIBLE')

    def test_default_strict_notches_preserve_unary_material_points_using_explicit_partner_fractions_and_normalized_mode_reports_change(self):
        c,data,d,p,_,_=fixture();before=digest([c,data,d,p])
        strict=prepare_pattern_ease_variant(c,data,d,p)
        self.assertEqual(strict['notch_policy'],'PRESERVE_MATERIAL_POINTS');self.assertEqual(strict['status'],'PROPOSAL_READY_FOR_REVIEW')
        self.assertTrue(strict['packages_allowed_for_review']);self.assertEqual(digest([c,data,d,p]),before)
        failed=next(row for row in strict['material_notches']if row['mark_id']=='sleeve-underarm-mid')
        self.assertEqual(failed['piece'],'sleeve');self.assertEqual(failed['mark_id'],'sleeve-underarm-mid')
        a,b=failed['bindings'];self.assertAlmostEqual(a['mapped_fraction']+b['mapped_fraction'],1.,places=12)
        self.assertNotAlmostEqual(a['mapped_fraction'],b['mapped_fraction'],places=3)
        self.assertTrue(all(row['source_residual_cm']<=1e-7 for row in failed['bindings']))
        actual=next(row for row in strict['piece_annotations']['sleeve']['pattern']['assembly_marks']if row['id']=='sleeve-underarm-mid')
        self.assertEqual(actual['seam_side_positions'],{'a':a['mapped_fraction'],'b':b['mapped_fraction']})
        p['notch_policy']='NORMALIZED_ARC_FRACTIONS';normal=prepare_pattern_ease_variant(c,data,d,p)
        self.assertEqual(normal['status'],'NEEDS_DATA');self.assertTrue(normal['packages_allowed_for_review'])
        self.assertTrue(any(row['code']=='NORMALIZED_ARC_NOTCH_REPOSITIONING_PROPOSED'for row in normal['diagnostics']))
        self.assertFalse(next(row for row in normal['piece_diff']if row['piece']=='sleeve')['material_notch_points_preserved'])

    def test_default_strict_notches_recompute_representable_fraction_from_exported_material_point_and_ignore_absent_marks(self):
        c,data,d,p,_,_=fixture('AFFINE_SOURCE_UV')
        for family in p['families']:family['scale_x']={'minimum':1.,'initial':1.,'maximum':1.}
        d['targets'][0]['body_girth_cm']=3.;d['targets'][0]['body_plus_target_cm']=8.
        result=prepare_pattern_ease_variant(c,data,d,p)
        self.assertTrue(result['packages_allowed_for_review']);self.assertTrue(all(row['status']=='MATERIAL_POINT_PRESERVED'for row in result['material_notches']))
        for owner in c['textiles'].values():owner['source']['pattern']['assembly_marks']=[]
        p['compiled_sha256']=digest(c);unmarked=prepare_pattern_ease_variant(c,data,d,p)
        self.assertEqual(unmarked['material_notches'],[])
        self.assertFalse(any(row['code'].startswith('UNREPRESENTABLE')for row in unmarked['diagnostics']))

    def test_input_set_permutation_keeps_exact_candidate_and_residuals(self):
        c,data,d,p,_,_=fixture();expected=prepare_pattern_ease_variant(c,data,d,p)
        data['garment.test']['pieces']=dict(reversed(list(data['garment.test']['pieces'].items())))
        data['garment.test']['seams'].reverse();d['targets'].reverse();p['nominal_paths'].reverse();c['links'].reverse()
        p['compiled_sha256']=digest(c);actual=prepare_pattern_ease_variant(c,data,d,p)
        self.assertEqual(actual['candidate_garments']['garment.test']['pieces'],expected['candidate_garments']['garment.test']['pieces'])
        self.assertEqual(actual['target_checks'],expected['target_checks']);self.assertEqual(actual['solver']['parameters'],expected['solver']['parameters'])

    def project_fixture(self):
        c,data,d,p,dossier,spec=fixture()
        def stored(name,value):
            atomic_json(self.root/name,value);return {'path':name,'sha256':sha(self.root/name)}
        body_ref=stored('body.json',{'exact':'unchanged measured source'});dossier_ref=stored('dossier.json',dossier)
        source=self.root/'package-source';source.mkdir();atomic_json(source/'garment.json',data['garment.test']);(source/'pattern.svg').write_bytes(_svg(data['garment.test']))
        package=build_package(source,self.root/'source.garmentpkg',dossier['asset_id'],'garment.test','PATTERN_SEWN',{'source':'test','created_by':'unit fixture','notes':'TEST_ONLY'})
        package_ref={'path':'source.garmentpkg','sha256':package['sha256']}
        spec.update(source_ref=dossier_ref,body_ref=body_ref);spec['packages'][0]['source_ref']=package_ref;spec['layers']['source_ref']=dossier_ref
        for node in spec['layers']['nodes']:node['source_ref']=dossier_ref
        spec_ref=stored('specification.json',spec);c=compile_production_dossier(dossier,{'garment.test':{'source_ref':package_ref,'data':data['garment.test']}},spec)
        c['specification_source_ref']=spec_ref;c['compiled_sha256']=digest({key:v for key,v in c.items()if key!='compiled_sha256'})
        d.update(body_ref=body_ref,dossier_ref=dossier_ref,proposal_ref=stored('numeric.json',{'target':'numeric design'}),review_ref=stored('review.json',{'review':'exact'}))
        decision_ref=stored('decision.json',d);p.update(compiled_sha256=digest(c),body_ref=body_ref,dossier_ref=dossier_ref,design_decision_ref=decision_ref)
        stored('compiled.json',c);stored('policy.json',p)
        gate={'approved':True,'source':'human','source_ref':d['source_ref'],'statement':d['statement'],'decision_id':'test-only-decision',
            'evidence':{str(i):row for i,row in enumerate([decision_ref,body_ref,dossier_ref,d['proposal_ref'],d['review_ref']])}}
        state={'gates':{'ease-design.garment.test':gate}}
        project=SimpleNamespace(root=self.root,state=lambda:copy.deepcopy(state),require_gate=lambda state,key:None)
        return project,state,dossier,data

    def test_project_wrapper_builds_new_packages_only_after_exact_human_review_without_binding_sources(self):
        project,state,dossier,data=self.project_fixture();before={str(path.relative_to(self.root)):sha(path)for path in self.root.rglob('*')if path.is_file()}
        result=prepare_project_pattern_ease_variant(project,'compiled.json','decision.json','policy.json','variants/review-one')
        self.assertEqual(result['status'],'PROPOSAL_READY_FOR_REVIEW');self.assertEqual(result['production_binding'],'NOT_CHANGED')
        self.assertEqual(set(result['packages']),{'garment.test'});self.assertEqual(result['acceptance'],'NOT_GRANTED')
        for name,value in before.items():self.assertEqual(sha(self.root/name),value)
        for row in result['packages'].values():inspect_package(self.root/row['path'])
        with zipfile.ZipFile(self.root/result['packages']['garment.test']['path'])as archive:variant=json.loads(archive.read('garment.json'))
        self.assertEqual(set(variant['pieces']),set(data['garment.test']['pieces']));self.assertEqual(variant['seams'],data['garment.test']['seams'])
        with self.assertRaisesRegex(StudioError,'must not exist'):prepare_project_pattern_ease_variant(project,'compiled.json','decision.json','policy.json','variants/review-one')
        state['gates']['ease-design.garment.test']['source']='agent'
        with self.assertRaisesRegex(StudioError,'canonical human'):prepare_project_pattern_ease_variant(project,'compiled.json','decision.json','policy.json','variants/refused')
        self.assertFalse((self.root/'variants/refused').exists())

    def test_densified_package_exports_exact_new_polygon_and_mirrored_source_preserves_winding(self):
        c,data,d,p,_,_=fixture()
        for vertex in data['garment.test']['pieces']['sleeve']['vertices']:vertex[0]=-vertex[0]
        c['textiles']['sleeve']['source_geometry']=copy.deepcopy(data['garment.test']['pieces']['sleeve'])
        c['textiles']['sleeve']['source']['pattern']['cut_outline_cm']=copy.deepcopy(data['garment.test']['pieces']['sleeve']['vertices'])
        p['compiled_sha256']=digest(c);mirrored=prepare_pattern_ease_variant(c,data,d,self.dense_policy(p))
        self.assertEqual(mirrored['status'],'PROPOSAL_READY_FOR_REVIEW')
        project,_,_,_=self.project_fixture();policy=self.dense_policy(json.loads((self.root/'policy.json').read_bytes()))
        basis={'input_refs':[policy['design_decision_ref']],'selection':'EXPLICIT_NOMINAL_V_NOT_ACCEPTED_ANATOMICAL_HOMOLOGY'}
        atomic_json(self.root/'basis.json',basis);policy['nominal_basis_ref']={'path':'basis.json','sha256':sha(self.root/'basis.json')}
        atomic_json(self.root/'policy-dense.json',policy)
        result=prepare_project_pattern_ease_variant(project,'compiled.json','decision.json','policy-dense.json','variants/dense-export')
        with zipfile.ZipFile(self.root/result['packages']['garment.test']['path'])as archive:
            garment=json.loads(archive.read('garment.json'));svg=archive.read('pattern.svg').decode()
        piece=garment['pieces']['sleeve'];self.assertEqual(len(piece['vertices']),10)
        self.assertIn(' '.join(str(p[0])+','+str(p[1])for p in piece['vertices']),svg)
        self.assertEqual(len(piece['faces']),8);self.assertEqual(len(piece['edges']['front']),4)
        proposal=json.loads((self.root/'variants/dense-export/proposal.json').read_bytes())
        self.assertIn(policy['nominal_basis_ref'],proposal['input_refs']);self.assertTrue(proposal['topology_changed'])
        self.assertEqual(proposal['acceptance'],'NOT_GRANTED');self.assertEqual(result['production_binding'],'NOT_CHANGED')
        atomic_json(self.root/'basis.json',{'changed':True})
        with self.assertRaisesRegex(StudioError,'station basis'):
            prepare_project_pattern_ease_variant(project,'compiled.json','decision.json','policy-dense.json','variants/stale-basis')
        self.assertFalse((self.root/'variants/stale-basis').exists())

    def test_densified_candidate_is_consumed_by_existing_source_limb_cages_with_exact_paired_boundaries(self):
        from a3d.garment_guides import limb_volume_frames
        from a3d.pattern_assembly import _compile_cage,_cage_point
        from tests.test_garment_guides import limb_fixture
        c,data,d,p,_,_=fixture();result=prepare_pattern_ease_variant(c,data,d,self.dense_policy(p))
        candidate=result['candidate_garments']['garment.test'];semantics={pid:copy.deepcopy(row['semantics'])for pid,row in c['textiles'].items()}
        semantics['cuff']['guide_edges']={'distal':'wrist','proximal':'join'}
        profile=limb_fixture(side='left')[2];before=digest([candidate,semantics,profile])
        report=limb_volume_frames(candidate,semantics,profile)
        frame=report['panels']['sleeve'];cage=_compile_cage(frame,'sleeve')
        inserts=result['topology_mappings']['sleeve']['inserted_vertices']
        pair=[candidate['pieces']['sleeve']['vertices'][row['new_vertex_index']]for row in inserts]
        targets=[_cage_point(frame,cage,point,'sleeve')[0]for point in pair]
        self.assertLess(math.dist(*targets),1e-8);self.assertEqual(digest([candidate,semantics,profile]),before)
        self.assertEqual(report['qualification'],'NONE');self.assertEqual(report['fitting'],'NOT_EXECUTED')
        self.assertEqual(next(row for row in report['evidence']if row['piece']=='sleeve')['cage_refinement']['source_faces'],8)

    def test_refused_affine_proposal_has_a_reviewable_candidate_without_a_package(self):
        project,state,dossier,data=self.project_fixture()
        policy=json.loads((self.root/'policy.json').read_bytes());policy['families']=fixture('AFFINE_SOURCE_UV')[3]['families']
        atomic_json(self.root/'policy-affine.json',policy)
        result=prepare_project_pattern_ease_variant(project,'compiled.json','decision.json','policy-affine.json','variants/affine-refused')
        self.assertEqual(result['status'],'REFUSED_CONSTRAINTS');self.assertEqual(result['packages'],{})
        self.assertTrue((self.root/'variants/affine-refused/candidate-garments.json').is_file())
        self.assertTrue((self.root/'variants/affine-refused/review-patterns.svg').is_file())
        self.assertFalse((self.root/'variants/affine-refused/packages').exists())

    def test_missing_reviewed_ref_or_artifact_substitution_cannot_publish_false_provenance(self):
        project,state,_,_=self.project_fixture();gate=state['gates']['ease-design.garment.test']
        omitted=gate['evidence'].pop('0')
        with self.assertRaisesRegex(StudioError,'exact decision/body/dossier'):
            prepare_project_pattern_ease_variant(project,'compiled.json','decision.json','policy.json','variants/missing-ref')
        self.assertFalse((self.root/'variants/missing-ref').exists());gate['evidence']['0']=omitted
        original=build_package
        def change_policy(*args):
            result=original(*args);atomic_json(self.root/'policy.json',{'substituted':'different bytes'});return result
        with patch('a3d.packages.build_package',side_effect=change_policy):
            with self.assertRaisesRegex(StudioError,'changed during artifact preparation'):
                prepare_project_pattern_ease_variant(project,'compiled.json','decision.json','policy.json','variants/stale-source')
        self.assertTrue((self.root/'variants/stale-source/candidate-garments.json').is_file())
        self.assertTrue((self.root/'variants/stale-source/failure.json').is_file())
        self.assertFalse((self.root/'variants/stale-source/proposal.json').exists())
