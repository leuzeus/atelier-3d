import copy
import math
import zipfile
from types import SimpleNamespace
from unittest.mock import patch

from a3d.core import StudioError,atomic_json,digest,sha
from a3d.garment_measurements import (source_edge_at_v,propose_measurement_paths,
    propose_project_measurement_paths,propose_compiled_measurement_paths,intersect_guide_material_plane,reconcile_source_boundary_uv)
from tests.test_core import Case


def fixture():
    ref={'path':'source.garmentpkg','sha256':'a'*64}
    frame={'origin_cm':[10.,20.,30.],'right':[0.,1.,0.],'forward':[-1.,0.,0.],'up':[0.,0.,1.]}
    body={'status':'PROFILE_MEASURED','segmentation':'EXPLICIT_SOURCE','cache_key':'b'*64,'frame':frame,
        'landmarks':{name:{'girth_cm':14.,'section':{'status':'MEASURED','height_cm':height,'girth_cm':14.}}
                     for name,height in (('chest',4.),('neck',9.))}}
    def world(p):return [frame['origin_cm'][k]+sum(p[i]*frame[axis][k]
        for i,axis in enumerate(('right','forward','up'))) for k in range(3)]
    textiles={};panels={}
    for pid,role,side in [('front.left','front','left'),('back.left','back','left'),
            ('back.right','back','right'),('front.right','front','right'),('single-inner','inner_front','center')]:
        geometry={'vertices':[[0.,0.],[4.,0.],[4.,10.],[0.,10.]],
            'edges':{'left':[0,3],'right':[1,2],'bottom':[0,1],'top':[3,2]}}
        semantics={'role':role,'side':side,'layer':'inner' if role=='inner_front' else 'outer',
            'guide_edges':{'opening':'left','side':'right'} if role=='front' else {'side':'left','center':'right'}}
        textiles[pid]={'component_id':'garment.coat','source_geometry':geometry,'semantics':semantics,'package_source_ref':ref}
        panels[pid]={'arc_sections':[{'v_cm':v,'arc_offset_cm':0.,'curve_cm':[world([0.,0.,v]),world([4.,0.,v])]}
                                        for v in (0.,10.)]}
    links=[{'id':sid,'piece_a':a,'edge_a':ea,'piece_b':b,'edge_b':eb,'kind':'permanent','orientation':'forward'}
        for sid,a,ea,b,eb in [('left-side','front.left','right','back.left','left'),
            ('back-center','back.left','right','back.right','right'),
            ('right-side','back.right','left','front.right','right')]]
    compiled={'status':'READY_TO_PLAN','assembly_spec':{'body_ref':ref},'source_ref':ref,
        'textiles':textiles,'links':links,'components':[{'id':'garment.coat','pipeline':'PATTERN_SEWN','package_source_ref':ref}]}
    guide={'panels':panels,'profile_sha256':digest(body),'profile_cache_key':body['cache_key'],
        'semantics_sha256':digest({pid:row['semantics'] for pid,row in textiles.items()})}
    request={'id':'coat.chest','component_id':'garment.coat','layer':'outer','body_landmark':'chest'}
    return compiled,body,{'garment.coat':guide},[request],world


def limb_fixture():
    compiled,body,guides,_,world=fixture()
    body['landmarks']['wrist.left']={'point_cm':[15.,0.,0.],'source_ref':{'path':'native.json','sha256':'c'*64}}
    guides['garment.coat']['profile_sha256']=digest(body)
    for pid,role in [('sleeve.left','sleeve'),('cuff.left','cuff')]:
        source={'vertices':[[0.,0.],[4.,0.],[4.,10.],[0.,10.]],
            'edges':{'seam-a':[0,3],'seam-b':[2,1],'distal':[0,1],'proximal':[3,2]}}
        compiled['textiles'][pid]={'component_id':'garment.coat','source_geometry':source,
            'semantics':{'role':role,'side':'left','layer':'outer','guide_edges':{'distal':'distal','proximal':'proximal'}},
            'package_source_ref':compiled['source_ref']}
        guides['garment.coat']['panels'][pid]={'arc_sections':[{'v_cm':v,'arc_offset_cm':0.,
            'curve_cm':[world(p) for p in [[14.,-1.,v],[16.,-1.,v],[16.,1.,v],[14.,1.,v],[14.,-1.,v]]]}
            for v in (0.,10.)]}
        compiled['links'].append({'id':pid+'.seam','piece_a':pid,'edge_a':'seam-a','piece_b':pid,
            'edge_b':'seam-b','kind':'permanent','orientation':'reverse'})
    guides['garment.coat']['semantics_sha256']=digest({pid:row['semantics'] for pid,row in compiled['textiles'].items()})
    descriptor={'identity':{'profile_sha256':digest(body),'profile_cache_key':body['cache_key']},'sections':{}}
    requests=[];mapping=[]
    for landmark,role,v in [('upper-arm.left','sleeve',5.),('wrist.left','cuff',0.)]:
        sid=role+'.section.0';descriptor['sections'][sid]={'region':{'side':'left','domain':
            'SHOULDER_TO_ELBOW_ONLY' if role=='sleeve' else 'WRIST_TO_ELBOW_ONLY',
            'axis_start_cm':world([15.,0.,0.]),'axis_end_cm':world([15.,0.,10.])},
            'section':{'id':sid,'status':'MEASURED','ok':True,'girth_cm':3.,'center_cm':world([15.,0.,v]),
                       'parameter':.5 if role=='sleeve'else 0.,'plane':{'normal_world':[0.,.6,.8]}}}
        requests.append({'id':'coat.'+landmark,'component_id':'garment.coat','layer':'outer','body_landmark':landmark})
        mapping.append({'body_landmark':landmark,'section_id':sid})
    return compiled,body,guides,requests,descriptor,mapping


class GarmentMeasurements(Case):
    def oblique_fixture(self):
        source={'vertices':[[0.,0.],[8.,0.],[8.,10.],[0.,10.]],'edges':{'left':[0,3],'right':[2,1]}}
        frame={'arc_sections':[{'v_cm':z,'arc_offset_cm':0.,
            'curve_cm':[[x,y,z]for x,y in [(-1.,-1.),(1.,-1.),(1.,1.),(-1.,1.),(-1.,-1.)]]}for z in (0.,10.)]}
        triangles=[]
        for u in range(8):triangles.extend([[[float(u),0.],[u+1.,0.],[u+1.,10.]],[[float(u),0.],[u+1.,10.],[float(u),10.]]])
        section={'center_cm':[0.,0.,5.],'plane':{'normal_world':[0.,.6,.8]}}
        return source,frame,triangles,section

    def test_oblique_body_plane_inverse_uv_curve_has_measured_material_length_and_exact_source_parameters(self):
        source,frame,triangles,section=self.oblique_fixture();before=digest([source,frame,triangles,section])
        curve=intersect_guide_material_plane(source,frame,triangles,section,['left','right'])
        self.assertAlmostEqual(curve['source_material_length_cm'],9.)
        self.assertEqual(curve['from']['edge'],'left');self.assertEqual(curve['to']['edge'],'right')
        self.assertAlmostEqual(curve['from']['fraction'],.575);self.assertAlmostEqual(curve['to']['fraction'],.425)
        self.assertLess(curve['maximum_plane_residual_cm'],1e-12)
        for point,binding in zip(curve['source_uv_polyline_cm'],curve['source_triangle_bindings']):
            for item in binding:
                weights=item['barycentric_weights'];triangle=triangles[item['source_triangle']]
                self.assertAlmostEqual(sum(weights),1.)
                for k in (0,1):self.assertAlmostEqual(point[k],sum(w*uv[k]for w,uv in zip(weights,triangle)))
        self.assertEqual(curve['surface_discretization_error'],'NOT_ESTIMATED')
        self.assertEqual(curve['homology'],'REVIEW_REQUIRED');self.assertEqual(curve['qualification'],'NONE')
        self.assertEqual(digest([source,frame,triangles,section]),before)

    def test_oblique_material_intersection_refuses_budget_coplanar_missing_or_invalid_source_domains(self):
        for change in ('face-budget','time-budget','missing','coplanar','source-void','duplicate-face'):
            source,frame,triangles,section=self.oblique_fixture();kwargs={}
            if change=='face-budget':kwargs={'max_faces':1}
            elif change=='time-budget':kwargs={'clock':__import__('unittest').mock.Mock(side_effect=[0.,1.]),'max_seconds':.5}
            elif change=='missing':section['center_cm'][2]=20.
            elif change=='coplanar':section={'center_cm':[1.,0.,0.],'plane':{'normal_world':[1.,0.,0.]}}
            elif change=='source-void':source['vertices']=[[0.,0.],[8.,0.],[8.,10.],[5.,10.],[5.,2.],[3.,2.],[3.,10.],[0.,10.]]
            else:triangles.append(copy.deepcopy(triangles[0]))
            with self.subTest(change=change),self.assertRaises(StudioError):
                intersect_guide_material_plane(source,frame,triangles,section,['left','right'],**kwargs)

    def test_native_derived_boundary_can_approximate_an_irrelevant_cap_but_measured_curve_must_remain_in_original_cut(self):
        source,frame,triangles,section=self.oblique_fixture();boundary=copy.deepcopy(source['vertices'])
        source['vertices']=[[0.,0.],[8.,0.],[8.,10.],[5.,10.],[4.,9.98],[3.,10.],[0.,10.]]
        source['edges']={'left':[6,0],'right':[1,2]}
        with self.assertRaises(StudioError):intersect_guide_material_plane(source,frame,triangles,section,['left','right'])
        curve=intersect_guide_material_plane(source,frame,triangles,section,['left','right'],triangulated_boundary_uv=boundary)
        self.assertEqual(curve['triangulation_domain'],'CANONICAL_NATIVE_DERIVED_SOURCE_UV_BOUNDARY')
        self.assertEqual(curve['material_curve_domain'],'ORIGINAL_IMMUTABLE_SOURCE_POLYGON')
        self.assertAlmostEqual(curve['source_material_length_cm'],9.);self.assertEqual(curve['qualification'],'NONE')
        source['vertices']=[[0.,0.],[8.,0.],[8.,10.],[5.,10.],[5.,2.],[3.,2.],[3.,10.],[0.,10.]]
        source['edges']['left']=[7,0]
        with self.assertRaisesRegex(StudioError,'empty source material'):
            intersect_guide_material_plane(source,frame,triangles,section,['left','right'],triangulated_boundary_uv=boundary)

    def test_duplicate_half_domain_or_overlap_cannot_compensate_a_missing_material_domain(self):
        for reverse in (False,True):
            source,frame,_,_=self.oblique_fixture();triangle=[[0.,0.],[8.,0.],[8.,10.]]
            duplicated=[triangle,list(reversed(triangle))if reverse else copy.deepcopy(triangle)]
            section={'center_cm':[0.,0.,0.],'plane':{'normal_world':[0.,0.,1.]}}
            with self.subTest(reverse=reverse),self.assertRaisesRegex(StudioError,'duplicate UV face'):
                intersect_guide_material_plane(source,frame,duplicated,section,['left','right'])
        source,frame,_,section=self.oblique_fixture();overlapping=[]
        for a,b in ((0.,4.),(2.,6.)):
            overlapping.extend([[[a,0.],[b,0.],[b,10.]],[[a,0.],[b,10.],[a,10.]]])
        with self.assertRaisesRegex(StudioError,'boundary'):
            intersect_guide_material_plane(source,frame,overlapping,section,['left','right'])

    def test_time_budget_expiring_during_endpoint_processing_refuses_the_candidate(self):
        source,frame,triangles,section=self.oblique_fixture();elapsed=[0.]
        from a3d.garment_measurements import _source_selector_at_point
        def expensive_selector(*args):
            result=_source_selector_at_point(*args);elapsed[0]+=.06;return result
        with patch('a3d.garment_measurements._source_selector_at_point',side_effect=expensive_selector),\
                self.assertRaisesRegex(StudioError,'time budget exhausted'):
            intersect_guide_material_plane(source,frame,triangles,section,['left','right'],clock=lambda:elapsed[0],max_seconds=.05)

    def test_source_endpoint_rounding_error_is_preserved_as_a_refusal_with_actual_curve_diagnostics(self):
        source,frame,triangles,section=self.oblique_fixture();boundary=copy.deepcopy(source['vertices'])
        for point in boundary:
            if point[0]==0.:point[0]=1e-6
        for triangle in triangles:
            for point in triangle:
                if point[0]==0.:point[0]=1e-6
        with self.assertRaisesRegex(StudioError,'outside its declared source boundary')as caught:
            intersect_guide_material_plane(source,frame,triangles,section,['left','right'],triangulated_boundary_uv=boundary)
        diagnostic=caught.exception.guide_plane_diagnostic
        self.assertAlmostEqual(diagnostic['source_edge_distances_cm']['left'],1e-6)
        self.assertEqual(diagnostic['numerical_tolerance_cm'],1e-7);self.assertFalse(diagnostic['admissible_for_fit'])
        self.assertGreater(diagnostic['source_material_length_cm'],8.);self.assertEqual(diagnostic['qualification'],'NONE')

    def test_native_binary32_boundary_reconstruction_requires_exact_contour_keys_and_round_trip(self):
        import struct
        from a3d.sewing import chain_lengths
        piece={'vertices':[[.1234567,0.],[8.1234567,0.],[8.1234567,10.],[.1234567,10.]],'edges':{}}
        native=[[struct.unpack('f',struct.pack('f',value))[0]for value in point]+[0.]for point in piece['vertices']]
        panel={'boundary':list(range(4)),'boundary_source_arclength_cm':
            [round(value,8)for value in chain_lengths(piece['vertices']+[piece['vertices'][0]])[:-1]],
            'source_contour_sha256':digest(piece['vertices'])}
        before=digest([piece,panel,native]);restored,evidence=reconcile_source_boundary_uv(piece,panel,native)
        self.assertEqual([restored[index]for index in range(4)],piece['vertices'])
        self.assertGreater(evidence['maximum_native_to_source_delta_cm'],1e-7)
        self.assertEqual(evidence['perimeter_key_uncertainty_cm'],.5e-8)
        self.assertFalse(evidence['native_mesh_changed']);self.assertFalse(evidence['admissible_for_fit'])
        self.assertTrue(all(row['binary32_round_trip']=='EXACT'for row in evidence['boundary_vertex_bindings']))
        self.assertEqual(digest([piece,panel,native]),before)
        for change in ('contour','arclength','native-moved','duplicate-index','missing-key'):
            p,r=copy.deepcopy(panel),copy.deepcopy(native)
            if change=='contour':p['source_contour_sha256']='f'*64
            elif change=='arclength':p['boundary_source_arclength_cm'][1]+=.01
            elif change=='native-moved':r[1][0]+=.00001
            elif change=='duplicate-index':p['boundary'][1]=p['boundary'][0]
            else:p['boundary_source_arclength_cm'].pop()
            with self.subTest(change=change),self.assertRaises(StudioError):reconcile_source_boundary_uv(piece,p,r)

    def test_open_torso_uses_actual_source_cohort_and_rotated_body_plane(self):
        compiled,body,guides,requests,_=fixture();before=digest([compiled,body,guides,requests])
        report=propose_measurement_paths(compiled,body,guides,requests);row=report['proposals'][0]
        self.assertEqual(row['path_kind'],'open_material_span');self.assertEqual(row['joins'],['left-side','back-center','right-side'])
        self.assertEqual(len(row['segments']),4);self.assertNotIn('single-inner',[p['piece'] for p in row['segments']])
        self.assertEqual(row['source_material_length_cm'],16.);self.assertEqual(row['body_girth_cm'],14.)
        self.assertEqual({span['source_v_cm'] for span in row['source_spans']},{4.})
        self.assertFalse(row['admissible_for_fit']);self.assertIsNone(row['ease_cm'])
        self.assertEqual(row['open_front_overlap'],'NOT_MEASURED');self.assertEqual(row['takeup'],'EXPLICIT_DECLARATION_REQUIRED')
        self.assertEqual(report['numeric_intent'],'NOT_INFERRED_FROM_CLASSIFICATION')
        self.assertEqual(digest([compiled,body,guides,requests]),before)
        guides['garment.coat']['panels']=dict(reversed(list(guides['garment.coat']['panels'].items())))
        self.assertEqual(propose_measurement_paths(compiled,body,guides,requests),report)

    def torso_cage_fixture(self):
        compiled,body,guides,requests,world=fixture();payload={'rest_cm':[],'faces':[],'panels':{}}
        # A bent guide changes source V within one measured body plane. The
        # source mesh explicitly contains the same material subdivisions.
        uv=[[0.,0.],[4.,0.],[4.,10.],[0.,10.],[2.,0.],[2.,10.]]
        triangles=[[0,4,5],[0,5,3],[4,1,2],[4,2,5]]
        boundary=[0,4,1,2,5,3];arcs=[0.,2.,4.,14.,16.,18.]
        for pid,row in compiled['textiles'].items():
            offset=len(payload['rest_cm'])
            payload['rest_cm'].extend([point+[0.]for point in uv])
            payload['faces'].extend([[offset+i for i in face]for face in triangles])
            payload['panels'][pid]={'indices':list(range(offset,offset+6)),
                'boundary':[offset+i for i in boundary],'boundary_source_arclength_cm':arcs,
                'source_contour_sha256':digest(row['source_geometry']['vertices'])}
            guides['garment.coat']['panels'][pid]={'uv_cm':copy.deepcopy(uv),'triangles':triangles,
                'target_cm':[world([u,0.,v+(1. if u==2. else 0.)])for u,v in uv]}
        return compiled,body,guides,requests,{'garment.coat':payload}

    def test_torso_cage_measures_bent_material_curve_in_rotated_body_frame_without_nominal_v(self):
        compiled,body,guides,requests,meshes=self.torso_cage_fixture()
        before=digest([compiled,body,guides,requests,meshes])
        result=propose_measurement_paths(compiled,body,guides,requests,source_meshes=meshes)
        self.assertEqual(result['diagnostics'],[]);row=result['proposals'][0]
        self.assertEqual(row['path_kind'],'open_material_span')
        self.assertEqual(row['joins'],['left-side','back-center','right-side'])
        self.assertAlmostEqual(row['source_material_length_cm'],8.*math.sqrt(5.))
        for span,homology in zip(row['source_spans'],row['homology']):
            self.assertNotIn('source_v_cm',span);self.assertFalse(homology['source_v_inferred'])
            self.assertEqual(homology['anatomical_homology'],'REVIEW_REQUIRED')
            curve=span['guide_plane_material_curve']
            self.assertLess(curve['maximum_plane_residual_cm'],1e-12)
            self.assertTrue(any(abs(point[1]-3.)<1e-10 for point in curve['source_uv_polyline_cm']))
            self.assertEqual(curve['source_uv_precision_reconciliation']['native_mesh_changed'],False)
        self.assertTrue(all('source_uv_polyline_cm'in segment for segment in row['segments']))
        self.assertFalse(row['admissible_for_fit']);self.assertIsNone(row['ease_cm'])
        self.assertEqual(digest([compiled,body,guides,requests,meshes]),before)

    def test_torso_cage_without_actual_source_mesh_or_with_wrong_partner_is_localized_and_not_admitted(self):
        for change in ('missing-mesh','missing-panel','missing-boundary','wrong-partner','outside-plane'):
            compiled,body,guides,requests,meshes=self.torso_cage_fixture()
            if change=='missing-mesh':meshes=None
            elif change=='missing-panel':del meshes['garment.coat']['panels']['front.left']
            elif change=='missing-boundary':del meshes['garment.coat']['panels']['front.left']['boundary']
            elif change=='wrong-partner':compiled['links'][0]['orientation']='reverse'
            else:
                body['landmarks']['chest']['section']['height_cm']=20.
                guides['garment.coat']['profile_sha256']=digest(body)
            with self.subTest(change=change):
                result=propose_measurement_paths(compiled,body,guides,requests,source_meshes=meshes)
                self.assertEqual(result['proposals'],[]);self.assertEqual(len(result['diagnostics']),1)
                if change=='missing-mesh':self.assertIn('actual source triangulation',result['diagnostics'][0]['message'])

    def test_closed_limbs_use_actual_unary_seams_and_explicit_distal_source_stop(self):
        compiled,body,guides,requests,descriptor,mapping=limb_fixture()
        before=digest([compiled,body,guides,requests,descriptor,mapping])
        report=propose_measurement_paths(compiled,body,guides,requests,descriptor,mapping)
        self.assertEqual(report['diagnostics'],[])
        rows={row['body_landmark']:row for row in report['proposals']}
        for row in rows.values():
            self.assertEqual(row['path_kind'],'closed_girth');self.assertEqual(row['source_material_length_cm'],4.)
            self.assertEqual(len(row['joins']),1);self.assertFalse(row['admissible_for_fit']);self.assertIsNone(row['ease_cm'])
        upper=rows['upper-arm.left']['homology'][0]
        self.assertAlmostEqual(upper['source_v_cm'],5.);self.assertAlmostEqual(upper['axis_lateral_offset_cm'],0.)
        self.assertAlmostEqual(upper['body_plane_to_guide_ring_angle_degrees'],math.degrees(math.acos(.8)))
        self.assertEqual(upper['oblique_plane_material_curve'],'NOT_DERIVED')
        cuff=rows['wrist.left']['homology'][0]
        self.assertEqual(cuff['source_v_cm'],0.);self.assertEqual(cuff['distal_edge'],'distal')
        self.assertEqual(digest([compiled,body,guides,requests,descriptor,mapping]),before)

    def test_missing_collar_configuration_limb_sections_and_source_homology_are_localized(self):
        compiled,body,guides,requests,_=fixture()
        requests += [{'id':'coat.neck','component_id':'garment.coat','layer':'outer','body_landmark':'neck'},
                     {'id':'coat.wrist','component_id':'garment.coat','layer':'outer','body_landmark':'wrist.left'}]
        report=propose_measurement_paths(compiled,body,guides,requests)
        self.assertEqual([r['id'] for r in report['proposals']],['coat.chest'])
        diagnostics={r['id']:r for r in report['diagnostics']}
        self.assertIn('collar configuration',diagnostics['coat.neck']['message'])
        self.assertIn('measured anatomical limb section is missing',diagnostics['coat.wrist']['message'])
        compiled['links'][0]['orientation']='reverse'
        report=propose_measurement_paths(compiled,body,guides,requests[:1])
        self.assertEqual(report['proposals'],[])
        self.assertEqual(report['diagnostics'][0]['source_join']['link'],'left-side')
        self.assertAlmostEqual(report['diagnostics'][0]['source_join']['actual_fraction_b'],.4)
        self.assertAlmostEqual(report['diagnostics'][0]['source_join']['expected_fraction_b'],.6)

    def test_collar_open_options_measure_source_extreme_rows_without_choosing_or_engaging_closure(self):
        compiled,body,guides,requests,world=fixture()
        compiled['textiles']['collar']={'component_id':'garment.coat','source_geometry':{
            'vertices':[[0.,0.],[12.,0.],[11.,7.],[1.,7.]],'edges':{'left':[3,0],'right':[1,2],'top':[2,3]}},
            'semantics':{'role':'collar','side':'center','layer':'outer','longitudinal_uv_axis':'u'},
            'package_source_ref':compiled['source_ref']}
        guides['garment.coat']['panels']['collar']={'arc_sections':[{'v_cm':v,'arc_offset_cm':0.,
            'curve_cm':[world([0.,0.,9.+v]),world([12.,0.,9.+v])]}for v in (0.,7.)]}
        guides['garment.coat']['semantics_sha256']=digest({pid:row['semantics']for pid,row in compiled['textiles'].items()})
        compiled['links'].append({'id':'collar-closure','piece_a':'collar','edge_a':'left','piece_b':'collar',
            'edge_b':'right','kind':'closure','orientation':'reverse'})
        request={'id':'coat.neck','component_id':'garment.coat','layer':'outer','body_landmark':'neck'}
        before=digest([compiled,body,guides,request])
        report=propose_measurement_paths(compiled,body,guides,[request]);options=report['diagnostics'][0]['source_open_collar_options']
        self.assertEqual(report['proposals'],[]);self.assertEqual(len(options),2)
        self.assertEqual([option['source_material_length_cm']for option in options],[12.,10.])
        self.assertEqual([option['body_girth_cm']for option in options],[14.,None])
        for option in options:
            self.assertEqual(option['path_kind'],'open_material_span');self.assertEqual(option['engaged_links'],[])
            self.assertEqual(option['configuration_choice'],'HUMAN_REVIEW_REQUIRED');self.assertFalse(option['admissible_for_fit'])
            self.assertEqual(option['source_closure_state'],'NOT_ENGAGED_PROPOSAL');self.assertIsNone(option['ease_cm'])
        self.assertEqual(digest([compiled,body,guides,request]),before)
        compiled['links'][-1]['kind']='permanent'
        missing=propose_measurement_paths(compiled,body,guides,[request])['diagnostics'][0]
        self.assertNotIn('source_open_collar_options',missing)
        self.assertIn('explicit unary closure',missing['source_open_collar_options_missing'])

    def test_open_front_collar_selects_only_the_attached_measured_neckline_and_preserves_other_controls(self):
        compiled,body,guides,_,world=fixture()
        for pid,role,geometry,semantics in (
            ('collar','collar',{'vertices':[[0.,0.],[12.,0.],[11.,7.],[1.,7.]],
                'edges':{'left':[3,0],'right':[1,2],'neck-base':[0,1],'top':[2,3]}},
                {'longitudinal_uv_axis':'u'}),
            ('neck-part','front',{'vertices':[[0.,0.],[12.,0.],[12.,2.],[0.,2.]],'edges':{'actual-neck':[0,1]}},
                {'guide_edges':{'neck':'actual-neck'}})):
            compiled['textiles'][pid]={'component_id':'garment.coat','source_geometry':geometry,
                'semantics':{'role':role,'side':'center','layer':'outer',**semantics},'package_source_ref':compiled['source_ref']}
            guides['garment.coat']['panels'][pid]={'arc_sections':[{'v_cm':v,'arc_offset_cm':0.,
                'curve_cm':[world([0.,0.,9.+v]),world([12.,0.,9.+v])]}for v in (0.,7.)]}
        compiled['links'] += [
            {'id':'collar-closure','piece_a':'collar','edge_a':'left','piece_b':'collar','edge_b':'right','kind':'closure','orientation':'reverse'},
            {'id':'real-neck-attachment','piece_a':'collar','edge_a':'neck-base','piece_b':'neck-part',
                'edge_b':'actual-neck','kind':'permanent','orientation':'forward'}]
        guides['garment.coat']['semantics_sha256']=digest({pid:row['semantics']for pid,row in compiled['textiles'].items()})
        request={'id':'coat.neck','component_id':'garment.coat','layer':'outer','body_landmark':'neck'}
        configuration={'wearing_configuration':'open_front'};before=digest([compiled,body,guides,configuration])
        result=propose_measurement_paths(compiled,body,guides,[request],configuration=configuration)
        self.assertEqual(result['diagnostics'],[]);row=result['proposals'][0]
        self.assertEqual(row['source_material_length_cm'],12.);self.assertEqual(row['body_girth_cm'],14.)
        self.assertEqual(row['path_kind'],'open_material_span');self.assertEqual(row['joins'],[]);self.assertEqual(row['engaged_links'],[])
        self.assertEqual(row['source_closure_state'],'NOT_ENGAGED_PROPOSAL');self.assertFalse(row['admissible_for_fit'])
        proof=row['homology'][0]['source_neckline_attachment'];self.assertEqual(proof['coverage'],'FULL_SOURCE_ROW_ONCE')
        self.assertEqual(proof['permanent_source_attachments'][0]['id'],'real-neck-attachment')
        self.assertEqual(row['source_open_collar_options'][1]['body_girth_cm'],None)
        self.assertEqual(digest([compiled,body,guides,configuration]),before)
        for change in ('undeclared-neck','missing-attachment','duplicate-attachment','not-open','nonplanar'):
            c,p,g=copy.deepcopy(compiled),copy.deepcopy(body),copy.deepcopy(guides);config=copy.deepcopy(configuration)
            if change=='undeclared-neck':
                c['textiles']['neck-part']['semantics']['guide_edges']={}
                g['garment.coat']['semantics_sha256']=digest({pid:entry['semantics']for pid,entry in c['textiles'].items()})
            elif change=='missing-attachment':c['links'].pop()
            elif change=='duplicate-attachment':c['links'].append({**c['links'][-1],'id':'duplicate'})
            elif change=='not-open':config['wearing_configuration']='closed'
            else:g['garment.coat']['panels']['collar']['arc_sections'][0]['curve_cm'].insert(1,world([6.,0.,10.]))
            with self.subTest(change=change):
                refused=propose_measurement_paths(c,p,g,[request],configuration=config)
                self.assertEqual(refused['proposals'],[]);self.assertEqual(len(refused['diagnostics']),1)

    def test_missing_seam_disconnected_path_branch_or_extrapolated_plane_never_invents_a_join(self):
        for change in ('missing','closure','branch','extrapolate','nonplanar'):
            compiled,body,guides,requests,_=fixture()
            if change=='missing':compiled['links'].pop(1)
            elif change=='closure':compiled['links'][1]['kind']='closure'
            elif change=='branch':compiled['links'].append({**compiled['links'][0],'id':'duplicate-permanent'})
            elif change=='extrapolate':
                body['landmarks']['chest']['section']['height_cm']=20.;guides['garment.coat']['profile_sha256']=digest(body)
            else:guides['garment.coat']['panels']['front.left']['arc_sections'][0]['curve_cm'][0][2]+=1.
            with self.subTest(change=change):
                report=propose_measurement_paths(compiled,body,guides,requests)
                self.assertFalse(report['proposals']);self.assertEqual(len(report['diagnostics']),1)
                self.assertEqual(report['diagnostics'][0]['code'],'HOMOLOGOUS_SOURCE_PATH_NEEDS_DATA')

    def test_path_cannot_cross_a_source_void_or_an_ambiguous_edge(self):
        compiled,body,guides,requests,_=fixture()
        piece=compiled['textiles']['front.left']['source_geometry']
        piece['vertices']=[[0.,0.],[6.,0.],[6.,6.],[4.,6.],[4.,2.],[2.,2.],[2.,6.],[0.,6.]]
        piece['edges']={'left':[7,0],'right':[1,2]}
        report=propose_measurement_paths(compiled,body,guides,requests)
        self.assertIn('empty source space',report['diagnostics'][0]['message']);self.assertEqual(report['proposals'],[])
        with self.assertRaisesRegex(StudioError,'coincident'):source_edge_at_v({'vertices':[[0.,0.],[1.,0.]],'edges':{'flat':[0,1]}},'flat',0.)
        with self.assertRaisesRegex(StudioError,'unambiguous'):source_edge_at_v(
            {'vertices':[[0.,0.],[1.,10.],[2.,0.]],'edges':{'folded':[0,1,2]}},'folded',4.)

    def test_unqualified_wrong_body_wrong_side_or_stale_guides_cannot_supply_limb_homology(self):
        for change in ('body','not_measured','side','distal','missing_seam','open_ring','asymmetric_ring','outside','semantics'):
            compiled,body,guides,requests,descriptor,mapping=limb_fixture()
            if change=='body':descriptor['identity']['profile_cache_key']='e'*64
            elif change=='not_measured':descriptor['sections']['sleeve.section.0']['section']['ok']=False
            elif change=='side':descriptor['sections']['sleeve.section.0']['region']['side']='right'
            elif change=='distal':compiled['textiles']['cuff.left']['semantics']['guide_edges'].pop('distal')
            elif change=='missing_seam':compiled['links']=[link for link in compiled['links']if link['piece_a']!='sleeve.left']
            elif change=='open_ring':guides['garment.coat']['panels']['sleeve.left']['arc_sections'][0]['curve_cm'].pop()
            elif change=='asymmetric_ring':guides['garment.coat']['panels']['sleeve.left']['arc_sections'][0]['curve_cm'][1][0]-=.5
            elif change=='outside':descriptor['sections']['sleeve.section.0']['section']['center_cm'][2]+=20.
            else:guides['garment.coat']['semantics_sha256']='e'*64
            if change=='distal':guides['garment.coat']['semantics_sha256']=digest({pid:row['semantics']for pid,row in compiled['textiles'].items()})
            with self.subTest(change=change):
                if change in ('body','semantics'):
                    with self.assertRaises(StudioError):propose_measurement_paths(compiled,body,guides,requests,descriptor,mapping)
                else:
                    report=propose_measurement_paths(compiled,body,guides,requests,descriptor,mapping)
                    self.assertTrue(report['diagnostics']);self.assertLess(len(report['proposals']),2)

    def test_limb_mapping_cannot_relabel_arm_as_wrist_or_left_as_right_or_shift_sourced_wrist_endpoint(self):
        for change in ('wrist-to-arm','right-to-left','wrist-interior','wrong-wrist-point','unsourced-wrist'):
            compiled,body,guides,requests,descriptor,mapping=limb_fixture()
            if change=='wrist-to-arm':mapping[1]['section_id']='sleeve.section.0';requests=requests[1:]
            elif change=='right-to-left':
                mapping[0]['body_landmark']='upper-arm.right';requests[0]['body_landmark']='upper-arm.right';requests=requests[:1]
            else:
                requests=requests[1:]
                if change=='wrist-interior':descriptor['sections']['cuff.section.0']['section']['parameter']=.5
                elif change=='wrong-wrist-point':body['landmarks']['wrist.left']['point_cm'][2]=1.
                else:body['landmarks']['wrist.left'].pop('source_ref')
                guides['garment.coat']['profile_sha256']=digest(body);descriptor['identity']['profile_sha256']=digest(body)
            with self.subTest(change=change):
                result=propose_measurement_paths(compiled,body,guides,requests,descriptor,mapping)
                self.assertEqual(result['proposals'],[]);self.assertEqual(len(result['diagnostics']),1)
                self.assertNotIn('guide_plane_material_candidate',result['diagnostics'][0])

    def project_fixture(self):
        compiled,body,guides,required,_=fixture()
        def stored(name,value):
            atomic_json(self.root/name,value);return {'path':name,'sha256':sha(self.root/name)}
        geometry={'vertices_cm':[[0.,0.,0.],[1.,0.,0.],[0.,1.,0.]],'faces':[[0,1,2]],'face_sets':[0]}
        body['geometry_sha256']=digest([geometry['vertices_cm'],geometry['faces']])
        body_ref=stored('body.json',body);geometry_ref=stored('geometry.json',geometry)
        dossier_ref=stored('dossier.json',{'approved':'data'});spec_ref=stored('production.json',{'metadata':'data'})
        compiled.update(source_ref=dossier_ref,specification_source_ref=spec_ref)
        compiled['assembly_spec']['body_ref']=body_ref
        data={'component_id':'garment.coat','pieces':{pid:row['source_geometry']for pid,row in compiled['textiles'].items()},'seams':compiled['links']}
        with zipfile.ZipFile(self.root/'source.garmentpkg','w')as archive:archive.writestr('garment.json',__import__('json').dumps(data))
        package_ref={'path':'source.garmentpkg','sha256':sha(self.root/'source.garmentpkg')}
        compiled['components'][0]['package_source_ref']=package_ref
        for row in compiled['textiles'].values():row['package_source_ref']=package_ref
        guides['garment.coat'].update(profile_sha256=digest(body),source_sha256=digest(data))
        fit={'version':1,'source_ref':stored('original-fit.json',{'intent':'still to review'}),'dossier_ref':dossier_ref,
            'body_ref':body_ref,'component_ids':['garment.coat'],
            'classification':{'category':'coat','silhouette_intent':'relaxed','wearing_configuration':'open_front','layer_role':'outer'},
            'required_measurements':required,'measurements':[]}
        stored('compiled.json',compiled);stored('guides.json',guides);stored('fit.json',fit)
        native={'operation':'prepare_body_target','files':[body_ref,geometry_ref],
            'result':{'profile_cache_key':body['cache_key'],'artifacts':{'profile':body_ref,'geometry':geometry_ref}}}
        return SimpleNamespace(root=self.root),compiled,fit,native,stored

    def test_project_wrapper_reads_real_hashed_packages_and_canonical_body_without_changing_files(self):
        project,compiled,fit,native,stored=self.project_fixture()
        before={path.name:sha(path)for path in self.root.iterdir()}
        with patch('a3d.production_dossier.compile_project_dossier',return_value=copy.deepcopy(compiled)),\
                patch('a3d.native_evidence.native_origin',return_value=(native,{'receipt':'canonical-body'})):
            result=propose_project_measurement_paths(project,'compiled.json','guides.json','fit.json')
        self.assertEqual(result['native_body_origin'],{'receipt':'canonical-body'})
        self.assertEqual(len(result['proposals']),1);self.assertEqual(result['acceptance'],'NOT_GRANTED')
        self.assertEqual(result['guide_reconstruction']['diagnostics'][0]['code'],'GUIDE_POLICY_MISSING')
        self.assertFalse(result['guide_reconstruction']['admissible_for_fit'])
        self.assertEqual(before,{path.name:sha(path)for path in self.root.iterdir()})
        self.assertEqual(result['proposal_sha256'],digest({k:v for k,v in result.items()if k!='proposal_sha256'}))
        with patch('a3d.production_dossier.compile_project_dossier',return_value=copy.deepcopy(compiled)),\
                patch('a3d.native_evidence.native_origin',return_value=(native,{'receipt':'canonical-body'})):
            memory=propose_compiled_measurement_paths(project,compiled,'guides.json','fit.json')
        self.assertEqual(memory['proposals'],result['proposals'])
        self.assertNotIn('compiled.json',[ref['path']for ref in memory['input_refs']])
        self.assertEqual(before,{path.name:sha(path)for path in self.root.iterdir()})

    def test_provided_guide_policy_is_forwarded_to_reconstruction_and_a_divergence_refuses_measurements(self):
        project,compiled,fit,native,stored=self.project_fixture();ref=stored('policy.json',{'explicit':'source policy'})
        evidence={'status':'GUIDE_HYPOTHESES_RECONSTRUCTED','qualification':'NONE','admissible_for_fit':False}
        with patch('a3d.production_dossier.compile_project_dossier',return_value=copy.deepcopy(compiled)),\
                patch('a3d.native_evidence.native_origin',return_value=(native,{})),\
                patch('a3d.garment_guide_policy.verify_guide_policy',return_value=evidence)as verifier:
            result=propose_compiled_measurement_paths(project,compiled,'guides.json','fit.json',guide_policy_path='policy.json')
            verifier.assert_called_once();self.assertEqual(verifier.call_args.args[3],native['result']['artifacts']['geometry'])
            self.assertIn(ref,result['input_refs']);self.assertEqual(result['guide_reconstruction']['policy_ref'],ref)
            self.assertFalse(result['proposals'][0]['admissible_for_fit'])
            verifier.side_effect=StudioError('Guide coordinates differ from reconstruction')
            with self.assertRaisesRegex(StudioError,'differ from reconstruction'):
                propose_compiled_measurement_paths(project,compiled,'guides.json','fit.json',guide_policy_path='policy.json')

    def test_guide_policy_substitution_during_reconstruction_or_measurement_is_refused(self):
        from a3d.garment_measurements import propose_measurement_paths as real_propose
        project,compiled,fit,native,stored=self.project_fixture()
        for boundary in ('reconstruction','measurement'):
            stored('policy.json',{'explicit':'original policy bytes'})
            evidence={'status':'GUIDE_HYPOTHESES_RECONSTRUCTED','qualification':'NONE','admissible_for_fit':False}
            def reconstruct(*args):
                if boundary=='reconstruction':stored('policy.json',{'corrupted':'substituted policy bytes'})
                return copy.deepcopy(evidence)
            def propose(*args):
                result=real_propose(*args)
                if boundary=='measurement':stored('policy.json',{'corrupted':'substituted policy bytes'})
                return result
            with self.subTest(boundary=boundary),patch('a3d.production_dossier.compile_project_dossier',return_value=copy.deepcopy(compiled)),\
                    patch('a3d.native_evidence.native_origin',return_value=(native,{})),\
                    patch('a3d.garment_guide_policy.verify_guide_policy',side_effect=reconstruct),\
                    patch('a3d.garment_measurements.propose_measurement_paths',side_effect=propose):
                with self.assertRaisesRegex(StudioError,'policy artifact changed'):
                    propose_compiled_measurement_paths(project,compiled,'guides.json','fit.json',guide_policy_path='policy.json')

    def test_coupled_guide_recipe_is_forwarded_and_file_substitution_refuses_measurements(self):
        project,compiled,fit,native,stored=self.project_fixture()
        recipe={'component_id':'garment.coat','seams':{'source-seam':{'kind':'permanent'}}}
        recipe_ref=stored('recipe.json',recipe)
        policy={'components':{'garment.coat':{'source_seam_coupling':{'recipe_ref':recipe_ref}}}}
        stored('policy.json',policy)
        evidence={'status':'GUIDE_HYPOTHESES_RECONSTRUCTED','qualification':'NONE','admissible_for_fit':False}
        with patch('a3d.production_dossier.compile_project_dossier',return_value=copy.deepcopy(compiled)),\
                patch('a3d.native_evidence.native_origin',return_value=(native,{})),\
                patch('a3d.garment_guide_policy.verify_guide_policy',return_value=copy.deepcopy(evidence))as verifier:
            result=propose_compiled_measurement_paths(project,compiled,'guides.json','fit.json',guide_policy_path='policy.json')
            self.assertEqual(verifier.call_args.kwargs['source_seam_recipes'],{'garment.coat':recipe})
            self.assertIn(recipe_ref,result['input_refs']);self.assertFalse(result['proposals'][0]['admissible_for_fit'])
        from a3d.garment_measurements import propose_measurement_paths as real_propose
        def mutate_recipe(*args):
            result=real_propose(*args)
            (self.root/'recipe.json').write_bytes((self.root/'recipe.json').read_bytes()+b' ')
            return result
        with patch('a3d.production_dossier.compile_project_dossier',return_value=copy.deepcopy(compiled)),\
                patch('a3d.native_evidence.native_origin',return_value=(native,{})),\
                patch('a3d.garment_guide_policy.verify_guide_policy',return_value=copy.deepcopy(evidence)),\
                patch('a3d.garment_measurements.propose_measurement_paths',side_effect=mutate_recipe):
            with self.assertRaisesRegex(StudioError,'recipe artifact changed'):
                propose_compiled_measurement_paths(project,compiled,'guides.json','fit.json',guide_policy_path='policy.json')

    def test_project_wrapper_rejects_other_target_changed_package_or_forged_guide_source(self):
        project,compiled,fit,native,stored=self.project_fixture()
        for change in ('target','package','guide','origin','geometry'):
            current=copy.deepcopy(fit);current_native=copy.deepcopy(native)
            if change=='target':current['body_ref']={'path':'other-body.json','sha256':'e'*64}
            elif change=='package':
                with zipfile.ZipFile(self.root/'source.garmentpkg','a')as archive:archive.writestr('changed.txt','changed')
            elif change=='guide':
                from a3d.core import read_json
                guides=read_json(self.root/'guides.json');guides['garment.coat']['source_sha256']='e'*64;stored('guides.json',guides)
            elif change=='origin':current_native['result']['profile_cache_key']='e'*64
            else:
                from a3d.core import read_json
                body=read_json(self.root/'body.json');body['geometry_sha256']='e'*64
                current['body_ref']=stored('body.json',body)
            stored('fit.json',current)
            with self.subTest(change=change),patch('a3d.production_dossier.compile_project_dossier',return_value=copy.deepcopy(compiled)),\
                    patch('a3d.native_evidence.native_origin',return_value=(current_native,{})),self.assertRaises(StudioError):
                propose_project_measurement_paths(project,'compiled.json','guides.json','fit.json')
            project,compiled,fit,native,stored=self.project_fixture()

    def test_source_uv_mesh_requires_observation_origin_and_exact_source_but_never_inherits_readiness(self):
        project,compiled,fit,native,stored=self.project_fixture()
        with zipfile.ZipFile(self.root/'source.garmentpkg')as archive:data=__import__('json').loads(archive.read('garment.json'))
        stored('source.json',data)
        payload={'component_id':'garment.coat','source_garment':'source.json','source_garment_sha256':digest(data),
                 'package_sha256':compiled['components'][0]['package_source_ref']['sha256']}
        ref=stored('mesh.json',payload)
        rejected={'operation':'prepare_pattern_assembly','files':[ref],
                  'result':{'derived_mesh':ref,'component_id':'garment.coat','readiness':'NEEDS_CORRECTION'}}
        with patch('a3d.production_dossier.compile_project_dossier',return_value=copy.deepcopy(compiled)),\
                patch('a3d.native_evidence.native_origin',return_value=(native,{}))as body_origin,\
                patch('a3d.native_evidence.native_observation_origin',return_value=(rejected,{'qualification':'NONE'}))as observer:
            report=propose_compiled_measurement_paths(project,compiled,'guides.json','fit.json',derived_mesh_refs={'garment.coat':ref})
            body_origin.assert_called_once();observer.assert_called_once()
            self.assertEqual(observer.call_args.kwargs['observed_artifact_ref'],ref)
            trace=report['source_uv_triangulations']['garment.coat']
            self.assertEqual(trace['placement_readiness'],'NEEDS_CORRECTION');self.assertEqual(trace['placement_qualification'],'NOT_TRANSFERRED')
            self.assertFalse(report['proposals'][0]['admissible_for_fit'])
            stored('source.json',{'different':'cut'})
            with self.assertRaisesRegex(StudioError,'immutable exact source'):propose_compiled_measurement_paths(
                project,compiled,'guides.json','fit.json',derived_mesh_refs={'garment.coat':ref})
