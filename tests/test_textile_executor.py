import copy
import unittest
from types import SimpleNamespace
from unittest.mock import Mock,patch

from a3d.core import ROOT, StudioError, digest, read_json,atomic_json,sha,contract
from a3d.cloth_metrics import face_sources
from a3d.garment_planner import plan_assembly
from a3d.pattern_assembly import consolidate, map_digest
from a3d.textile_executor import (compile_textile_program, consolidate_group, group_plan, merge_group_payloads,
                                  split_group_payload, assemble_component_fragments, prepare_component_templates,
                                  _guide_seed_placement, STAGES)
from a3d.textile_executor import (_template_audit_observations,TEMPLATE_NUMERIC_POLICY,_project_component_layers,
    _guide_preform_bound,mount_release_batches,source_preform_budget,verify_source_preform_budget,
    component_continuity_proof,verify_component_continuity)
from tests.test_pattern_assembly import example
from tests.test_core import Case
from a3d.textile_executor import require_textile_program_admission


def fixture(two_layers=False):
    original, original_plan = example(); template = read_json(ROOT/'templates/sewing-recipe.json')
    ref = {'path': 'approved/assembly.json', 'sha256': 'a'*64}; payloads = {}; recipes = {}; plans = {}; bindings = []; pieces = []
    for cid, pid, x, layer in [('source.a', 'panel.a', 0., 'inner' if two_layers else 'cloth'),
                              ('source.b', 'panel.b', 3., 'outer' if two_layers else 'cloth')]:
        points = [[0., 0., 0.], [2., 0., 0.], [2., 2., 0.], [0., 2., 0.]]
        payload = {'version': 2, 'component_id': cid, 'package_sha256': digest(cid), 'source_garment_sha256': digest(pid),
            'rest_cm': points, 'placed_cm': [[p[0]+x, p[1], p[2]] for p in points],
            'faces': [[3, 0, 1], [1, 2, 3]], 'pins': {}, 'seams': {},
            'panels': {pid: {'indices': [0, 1, 2, 3], 'boundary': [0, 1, 2, 3],
                            'edges': {'left': [0, 3], 'right': [1, 2], 'top': [2, 3], 'bottom': [0, 1]}}}}
        payloads[cid] = payload
        plan = copy.deepcopy(original_plan)
        plan.update(component_id=cid, mapping_sha256=map_digest(payload))
        plan['preform']['panels'] = {pid: {'source_ref': 'fixture:source-plane', 'origin_cm': [x, 0., 0.],
                                          'u_axis': [1., 0., 0.], 'v_axis': [0., 1., 0.]}}
        plans[cid] = plan
        recipe = copy.deepcopy(template); recipe['component_id'] = cid
        recipe['placements'] = {pid: recipe['placements']['front']}; recipe['seams'] = {}; recipe['pins'] = []
        recipe['trial_pieces'] = [pid]; recipe['colliders'] = []; recipe['no_collision_reason'] = 'fixture:free coupons'
        recipes[cid] = recipe
        pieces.append({'id': pid, 'component_id': cid, 'role': 'lining', 'side': 'center', 'layer': layer,
                       'edges': ['left', 'right', 'top', 'bottom'], 'source_ref': ref})
        bindings.append({'component_id': cid, **{key: {'path': cid+'/'+key+'.json', 'sha256': 'a'*64}
                                               for key in ('package_ref', 'derived_mesh_ref', 'recipe_ref', 'plan_ref')}})
    nodes = [{'id': layer, 'kind': 'garment', 'panels': [p['id'] for p in pieces if p['layer'] == layer],
              'colliders': [], 'source_ref': ref} for layer in sorted({p['layer'] for p in pieces})]
    assembly = plan_assembly({'version': 1, 'source_ref': ref, 'body_ref': ref, 'pieces': pieces, 'links': [],
        'layers': {'version': 1, 'source_ref': ref, 'mode': 'ordered', 'interaction': 'one_way_declared',
                   'nodes': nodes, 'inside_to_outside': [['inner', 'outer']] if two_layers else []},
        'budgets': {'max_frames': 120, 'max_iterations': 20, 'max_seconds': 10.,
                    'max_displacement_cm': 3., 'max_strain_relative': .1}})
    specification = {'version': 1, 'purpose':'TEST_ONLY', 'id': 'synthetic-textile-program', 'asset_id': 'test-character',
                     'program_path': 'production/program.json', 'assembly_plan_ref': ref,
                     'components': bindings, 'run_budgets': {'max_attempts': 2, 'max_seconds': 30.}}
    return assembly, specification, payloads, recipes, plans


class TextileFitAdmission(Case):
    """Admission-only fixtures; no native/physical or garment proof is created."""
    def stored(self,name,value):
        atomic_json(self.root/name,value)
        return {'path':name,'sha256':sha(self.root/name)}

    def production(self):
        assembly,spec,payloads,recipes,plans=fixture()
        spec['purpose']='GARMENT_CANDIDATE'
        dossier_ref=self.stored('dossier.json',{'approved':'source'})
        source_spec_ref=self.stored('source-spec.json',{'explicit':'metadata'})
        body={'cache_key':'b'*64,'geometry_sha256':'c'*64}
        body_ref=self.stored('body.json',body)
        assembly['body_ref']=body_ref;assembly['source_ref']=dossier_ref
        spec['assembly_plan_ref']=self.stored('assembly.json',assembly)
        compiled={'status':'READY_TO_PLAN','source_ref':dossier_ref,'specification_source_ref':source_spec_ref,
            'assembly_spec':{},'components':[{'id':row['component_id'],'pipeline':'PATTERN_SEWN',
                'package_source_ref':row['package_ref']} for row in spec['components']]}
        compiled_ref=self.stored('compiled.json',compiled)
        profile={'body_ref':body_ref,'dossier_ref':dossier_ref,'component_ids':['source.a','source.b']}
        profile_ref=self.stored('fit.json',profile)
        spec['fit_context']={'compiled_dossier_ref':compiled_ref,'fit_profiles_refs':[profile_ref]}
        report={'admission':'EXPLORATORY_PHYSICS_ONLY','body_profile_sha256':digest(body),
            'body_profile_cache_key':body['cache_key'],'assessment_sha256':'d'*64,
            'checks':[{'component_id':cid,'status':'WITHIN_DECLARED_SOURCE_EASE',
                       'measurement_scope':'NOMINAL_SOURCE_CAPACITY'} for cid in profile['component_ids']],
            'human_reviews':[{'component_id':cid,'numeric_ease':{'status':'REVIEWED'}} for cid in profile['component_ids']]}
        project=SimpleNamespace(root=self.root,state=Mock(return_value={'asset':{'id':spec['asset_id']}}))
        return project,spec,assembly,compiled,profile,report

    def admitted(self,project,spec,assembly,compiled,report):
        with patch('a3d.production_dossier.compile_project_dossier',return_value=copy.deepcopy(compiled)),\
                patch('a3d.garment_planner.plan_assembly',return_value=copy.deepcopy(assembly)),\
                patch('a3d.garment_fit.require_fit_intent',return_value=copy.deepcopy(report)) as canonical:
            result=require_textile_program_admission(project,spec,assembly)
            self.assertEqual(canonical.call_count,len(spec['fit_context']['fit_profiles_refs']))
            return result

    def test_test_only_is_explicit_and_never_grants_product_acceptance(self):
        assembly,spec,payloads,recipes,plans=fixture();before=digest([assembly,spec,payloads,recipes,plans])
        project=SimpleNamespace(root=self.root,state=lambda:{'asset':{'id':spec['asset_id']}})
        admission=require_textile_program_admission(project,spec)
        self.assertEqual(admission['admission'],'TEST_ONLY_EXPERIMENT')
        self.assertEqual(admission['production_qualification'],'NOT_GRANTED');self.assertFalse(admission['accepted'])
        compiled=compile_textile_program(assembly,spec,payloads,recipes,plans)
        self.assertEqual(compiled['fit_intent_admission'],'TEST_ONLY_NO_PRODUCT_ADMISSION')
        self.assertEqual(digest([assembly,spec,payloads,recipes,plans]),before)
        spec.pop('purpose')
        with self.assertRaises(StudioError):contract('textile-program',spec)

    def test_missing_production_intent_is_data_missing_and_cannot_enter_native_effects(self):
        assembly,spec,payloads,recipes,plans=fixture();spec['purpose']='GARMENT_CANDIDATE'
        compiled=compile_textile_program(assembly,spec,payloads,recipes,plans)
        self.assertEqual(compiled['status'],'NEEDS_DATA')
        project=SimpleNamespace(root=self.root,state=lambda:{'asset':{'id':spec['asset_id']}})
        with self.assertRaisesRegex(StudioError,'reviewed numeric intent'):require_textile_program_admission(project,spec)
        bpy=SimpleNamespace(ops=SimpleNamespace(wm=SimpleNamespace(save_as_mainfile=Mock())))
        with patch.dict('sys.modules',{'bpy':bpy}),\
                patch('blender.operations.working',return_value=(project,{'working':'unused.blend'})),\
                patch('blender.textile_executor.load_textile_program',return_value=(spec,compiled)),\
                patch('blender.textile_executor.program_directory') as directory,\
                patch('blender.textile_executor.prepare_group_bundle') as bundle:
            from blender.textile_executor import advance_textile_program
            with self.assertRaisesRegex(StudioError,'reviewed numeric intent'):advance_textile_program(str(self.root),'program.json')
            directory.assert_not_called();bundle.assert_not_called();bpy.ops.wm.save_as_mainfile.assert_not_called()
        with patch('blender.operations.working',return_value=(project,{})),\
                patch('blender.textile_executor.load_textile_program',return_value=(spec,compiled)),\
                patch('blender.textile_executor.verified',return_value=assembly),\
                patch('blender.textile_executor._inner_colliders') as colliders:
            from blender.textile_executor import prepare_group_bundle
            with self.assertRaisesRegex(StudioError,'reviewed numeric intent'):prepare_group_bundle(project,'program.json','unknown')
            colliders.assert_not_called()
        with patch.dict('sys.modules',{'bpy':bpy}),\
                patch('blender.operations.working',return_value=(project,{})),\
                patch('blender.textile_group.load_textile_program',return_value=(spec,compiled)),\
                patch('blender.sewing.make_object') as make:
            from blender.textile_group import transition_textile_group
            with self.assertRaisesRegex(StudioError,'reviewed numeric intent'):
                transition_textile_group(str(self.root),'program.json','unknown','mount')
            make.assert_not_called()

    def test_all_actual_component_checks_exact_body_and_human_intent_are_required(self):
        project,spec,assembly,compiled,profile,report=self.production();before=digest([spec,assembly,compiled,profile,report])
        result=self.admitted(project,spec,assembly,compiled,report)
        self.assertEqual(result['covered_components'],['source.a','source.b'])
        self.assertEqual(result['admission'],'EXPLORATORY_PHYSICS_ONLY');self.assertFalse(result['accepted'])
        self.assertEqual(result['body_ref'],assembly['body_ref']);self.assertEqual(result['qualification'],'NONE')
        self.assertEqual(digest([spec,assembly,compiled,profile,report]),before)
        for change in ('declared_only','stale_body','wrong_scope','incompatible','unreviewed'):
            altered=copy.deepcopy(report)
            if change=='declared_only':altered['checks']=altered['checks'][:1]
            elif change=='stale_body':altered['body_profile_cache_key']='e'*64
            elif change=='wrong_scope':altered['checks'][1]['measurement_scope']='BOUNDING_BOX'
            elif change=='incompatible':altered['checks'][1]['status']='OUTSIDE_DECLARED_SOURCE_EASE'
            else:altered['human_reviews'][1]['numeric_ease']['status']='PENDING'
            with self.subTest(change=change),self.assertRaises(StudioError):self.admitted(project,spec,assembly,compiled,altered)

    def test_profiles_cannot_omit_owners_overlap_or_substitute_sources(self):
        project,spec,assembly,compiled,profile,report=self.production()
        for change in ('missing_component','wrong_body','stale_hash','package','overlap','recompiled','asset'):
            incoming=copy.deepcopy(spec);source=copy.deepcopy(compiled);fit=copy.deepcopy(profile)
            altered=copy.deepcopy(report)
            if change=='missing_component':
                fit['component_ids']=['source.a'];incoming['fit_context']['fit_profiles_refs']=[self.stored('one.json',fit)]
                altered['checks']=altered['checks'][:1];altered['human_reviews']=altered['human_reviews'][:1]
            elif change=='wrong_body':
                fit['body_ref']={'path':'other.json','sha256':'e'*64}
                incoming['fit_context']['fit_profiles_refs']=[self.stored('other-fit.json',fit)]
            elif change=='stale_hash':incoming['fit_context']['fit_profiles_refs'][0]['sha256']='e'*64
            elif change=='package':incoming['components'][0]['package_ref']['sha256']='e'*64
            elif change=='overlap':incoming['fit_context']['fit_profiles_refs'].append(self.stored('duplicate-fit.json',fit))
            elif change=='recompiled':source['components'][0]['package_source_ref']['sha256']='e'*64
            else:incoming['asset_id']='another-asset'
            with self.subTest(change=change),self.assertRaises(StudioError):self.admitted(project,incoming,assembly,source,altered)
        test_only=copy.deepcopy(spec);test_only['purpose']='TEST_ONLY'
        with self.assertRaisesRegex(StudioError,'TEST_ONLY'):require_textile_program_admission(project,test_only)


class TextileExecutor(unittest.TestCase):
    def sewn_component_continuity_fixture(self):
        from a3d.pattern_assembly import preform_coordinates,bounded_close
        source,plan=example();source['package_sha256']='a'*64
        group={'id':'source-group','pieces':sorted(source['panels'])}
        semantics={pid:{'component_id':source['component_id']} for pid in source['panels']}
        merged=merge_group_payloads(group,semantics,{source['component_id']:source})
        plan.update(component_id=group['id'],mapping_sha256=map_digest(merged))
        coords,_=preform_coordinates(merged,plan);coords,_=bounded_close(merged,coords,plan)
        continuous,_=consolidate_group(merged,coords,plan)
        fragment=split_group_payload(continuous,source['component_id'])
        component=assemble_component_fragments(source,[fragment]);ref={'path':'source.json','sha256':'b'*64}
        groups=[{'group_id':group['id'],'derived_mesh_ref':{'path':'group.json','sha256':'c'*64},'payload':continuous}]
        component['component_continuity']=component_continuity_proof(source,ref,component,groups,
            {'path':'program.json','sha256':'d'*64},{'path':'source.garmentpkg','sha256':'a'*64},.01)
        return source,component,groups

    def test_complete_component_composes_permanent_source_groups_without_cloth_claims(self):
        source,component,groups=self.sewn_component_continuity_fixture();before=digest([source,component,groups])
        result=verify_component_continuity(source,component,groups,.01)
        self.assertEqual(result['status'],'COMPONENT_CONTINUITY_VERIFIED')
        self.assertEqual(result['permanent_source_pair_count'],2)
        self.assertTrue(result['native_drape_receipts_required']);self.assertFalse(result['cloth_evidence_created'])
        self.assertEqual(result['global_source_vertex_map'],component['source_vertex_map'])
        self.assertEqual(result['global_source_face_indices'],list(range(len(source['faces']))))
        self.assertEqual(result['verified_groups'][0]['permanent_consolidation_proof_sha256'],
            groups[0]['payload']['permanent_consolidation']['proof_sha256'])
        self.assertEqual(digest([source,component,groups]),before)
        component['placed_cm'][0][2]+=.2
        self.assertEqual(verify_component_continuity(source,component,groups,.01)['status'],'COMPONENT_CONTINUITY_VERIFIED')

    def test_component_continuity_refuses_missing_root_changed_uv_maps_relations_and_source(self):
        source,component,groups=self.sewn_component_continuity_fixture()
        for change in ('missing','duplicate','source','group-proof','group-ref','source-face','global-map','extra-seam'):
            incoming=copy.deepcopy(source);candidate=copy.deepcopy(component);roots=copy.deepcopy(groups)
            if change=='missing':roots=[]
            elif change=='duplicate':roots*=2
            elif change=='source':incoming['source_garment_sha256']='another-source'
            elif change=='group-proof':roots[0]['payload'].pop('permanent_consolidation')
            elif change=='group-ref':roots[0]['derived_mesh_ref']['sha256']='e'*64
            elif change=='source-face':candidate['source_face_origins'][0]['source_uv_cm'][0][0]+=.1
            elif change=='global-map':candidate['source_vertex_map']['0']=1
            else:candidate['seams']['invented-detachable']={**copy.deepcopy(candidate['seams']['join']),'kind':'detachable'}
            with self.subTest(change=change),self.assertRaises(StudioError):
                verify_component_continuity(incoming,candidate,roots,.01)

    def test_component_layer_projection_preserves_only_proven_transitive_order(self):
        ref={'path':'source.json','sha256':'a'*64}
        layers={'version':1,'source_ref':ref,'mode':'ordered','interaction':'one_way_declared','nodes':[
            {'id':'body','kind':'body','panels':[],'colliders':['native.body'],'source_ref':ref},
            {'id':'inner','kind':'garment','panels':['inner-piece'],'colliders':[],'source_ref':ref},
            {'id':'outer','kind':'garment','panels':['outer-piece'],'colliders':[],'source_ref':ref},
            {'id':'belt','kind':'garment','panels':['belt-piece'],'colliders':[],'source_ref':ref}],
            'inside_to_outside':[['body','inner'],['inner','outer'],['outer','belt']]}
        before=digest(layers);projected=_project_component_layers(layers,{'belt-piece'})
        self.assertEqual(projected['inside_to_outside'],[['body','belt']])
        self.assertEqual({node['id'] for node in projected['nodes']},{'body','belt'})
        self.assertEqual(digest(layers),before)

    def test_long_curved_source_guide_has_a_budget_derived_before_execution(self):
        import math
        curve=[[15.*math.cos(i*math.pi/16),15.*math.sin(i*math.pi/16),100.] for i in range(33)]
        width=sum(math.dist(a,b) for a,b in zip(curve,curve[1:]))
        piece={'vertices':[[0.,0.],[width,0.],[width,8.],[0.,8.]]}
        frame={'arc_sections':[{'v_cm':v,'arc_offset_cm':0.,'curve_cm':[[x,y,z+v] for x,y,z in curve]} for v in (0.,8.)]}
        placement=_guide_seed_placement(piece,frame,'band');before=digest([piece,frame,placement])
        bound=_guide_preform_bound(piece,frame,placement)
        self.assertGreater(bound['bound_cm'],90.)
        self.assertEqual(bound['source_contour_sha256'],digest(piece['vertices']))
        self.assertEqual(bound['guide_sha256'],digest(frame));self.assertFalse(bound['gate_thresholds_changed'])
        self.assertEqual(digest([piece,frame,placement]),before)

    def test_equivalent_support_releases_keep_all_frames_and_changed_supports_remain_separate(self):
        payload={'panels':{'panel':{'indices':[0,1,2,3],'edges':{'top':[2,3],'bottom':[0,1]}}}}
        plan={'supports':{'temporary':[],'functional':[],'drape':[{'id':'top','piece':'panel','edge':'top',
            'weight':.7,'source_ref':'synthetic:fixed-support'}]}}
        before=digest([payload,plan]);batches=mount_release_batches(payload,plan,[0.,.5,1.],12)
        self.assertEqual(len(batches),1);self.assertEqual(batches[0]['frames'],12)
        self.assertEqual(batches[0]['releases'],[0.,.5,1.]);self.assertEqual(digest([payload,plan]),before)
        plan['supports']['temporary']=[{'id':'bottom','piece':'panel','edge':'bottom','weight':.7,'source_ref':'synthetic:released-support'}]
        batches=mount_release_batches(payload,plan,[0.,.5,1.],12)
        self.assertEqual(len(batches),3);self.assertEqual(sum(row['frames'] for row in batches),12)
        self.assertNotEqual(batches[0]['pins'],batches[-1]['pins'])

    def test_source_staging_budget_refuses_modified_bound_source_guide_or_seed(self):
        data={'pieces':{'long-strip':{'vertices':[[0.,0.],[180.,0.],[180.,8.],[0.,8.]]}}}
        frames={'long-strip':{'origin_cm':[0.,0.,0.],'u_axis':[1.,0.,0.],'v_axis':[0.,1.,0.]}}
        placements={'long-strip':{'mode':'flat','position_cm':[150.,0.,0.],
            'rotation_degrees':[0.,0.,0.],'origin_2d_cm':[0.,0.]}}
        before=digest([data,frames,placements]);budget=source_preform_budget(data,frames,placements)
        self.assertGreater(budget['max_displacement_cm'],100.)
        self.assertEqual(verify_source_preform_budget(data,frames,placements,budget),budget)
        changes=[(data,frames,placements,{**budget,'max_displacement_cm':200.}),
            ({'pieces':{'long-strip':{'vertices':[[0.,0.],[181.,0.],[180.,8.],[0.,8.]]}}},frames,placements,budget),
            (data,{'long-strip':{**frames['long-strip'],'origin_cm':[1.,0.,0.]}},placements,budget),
            (data,frames,{'long-strip':{**placements['long-strip'],'position_cm':[151.,0.,0.]}},budget)]
        for inputs in changes:
            with self.subTest(inputs=digest(inputs)),self.assertRaisesRegex(StudioError,'exact source'):
                verify_source_preform_budget(*inputs)
        self.assertEqual(digest([data,frames,placements]),before)

    def test_barycentric_source_seed_is_rigid_and_bound_covers_the_entire_declared_cage(self):
        import math
        from a3d.pattern_assembly import _compile_cage,_cage_point
        from tests.test_barycentric_guide_measurements import fixture
        piece,frame,_,_=fixture();before=digest([piece,frame])
        placement=_guide_seed_placement(piece,frame,'closed-coupon')
        bound=_guide_preform_bound(piece,frame,placement)
        self.assertEqual(bound['method'],'AFFINE_SOURCE_BOUNDARY_AND_CONVEX_BARYCENTRIC_TARGET_ENVELOPE')
        rx,ry,rz=[math.radians(value)for value in placement['rotation_degrees']]
        u=[math.cos(rz)*math.cos(ry),math.sin(rz)*math.cos(ry),-math.sin(ry)]
        v=[math.cos(rz)*math.sin(ry)*math.sin(rx)-math.sin(rz)*math.cos(rx),
            math.sin(rz)*math.sin(ry)*math.sin(rx)+math.cos(rz)*math.cos(rx),math.cos(ry)*math.sin(rx)]
        def seeded(uv):return[placement['position_cm'][k]+uv[0]*u[k]+uv[1]*v[k]for k in range(3)]
        self.assertAlmostEqual(math.dist(seeded([0.,0.]),seeded([8.,0.])),8.)
        self.assertAlmostEqual(math.dist(seeded([0.,0.]),seeded([0.,10.])),10.)
        compiled=_compile_cage(frame,'fixture')
        for source_u in (0.,.35,2.5,7.1,8.):
            for source_v in (0.,.14,5.5,10.):
                target,_=_cage_point(frame,compiled,[source_u,source_v],'fixture')
                self.assertLessEqual(math.dist(seeded([source_u,source_v]),target),bound['bound_cm'])
        self.assertEqual(digest([piece,frame]),before)

    def test_barycentric_seed_uses_source_triangle_at_beveled_corner_and_refuses_collapsed_world_tangent(self):
        piece={'vertices':[[2.,0.],[8.,6.],[0.,6.]]}
        frame={'uv_cm':copy.deepcopy(piece['vertices']),
            'target_cm':[[10.,20.,30.],[10.,26.,36.],[10.,18.,36.]],'triangles':[[0,1,2]]}
        placement=_guide_seed_placement(piece,frame,'beveled-coupon')
        self.assertEqual(placement['position_cm'],[10.,18.,30.])
        frame['target_cm']=[[0.,0.,0.],[1.,0.,0.],[2.,0.,0.]]
        with self.assertRaises(StudioError):_guide_seed_placement(piece,frame,'collapsed-coupon')

    def test_derived_template_observations_are_portable_without_rounding_source_metadata(self):
        source=1.2345678901234567
        panel={'area_cm2':4233.221955302751,'signed_area_cm2':4233.221955302751,
            'perimeter_cm':328.4962386473745,'source_segment_min_cm':1.,'source_segment_max_cm':2.,
            'source_dimensions_cm':[2.,3.],'grain_direction':[source,1.],
            'named_edges':{'edge':{'length_cm':122.00049338140757,'geometric_stops_uv_cm':[[source,0.],[2.,3.]]}}}
        report={'panels':{'panel':panel},'seams':[{'length_a_cm':2.,'length_b_cm':2.,'residual_relative':0.,
            'stops_a_uv_cm':[[source,0.],[2.,3.]],'notches':[{'a':source,'b':source}]}],'status':'SOURCE_AUDITED'}
        other=copy.deepcopy(report)
        other['panels']['panel'].update(area_cm2=4233.22195530275,signed_area_cm2=4233.22195530275,
            perimeter_cm=328.4962386473746)
        other['panels']['panel']['named_edges']['edge']['length_cm']=122.00049338140755
        report['panels']['halfway']=copy.deepcopy(panel)
        other['panels']['halfway']=copy.deepcopy(panel)
        report['panels']['halfway'].update(area_cm2=779.1148749375,signed_area_cm2=-779.1148749375001)
        other['panels']['halfway'].update(area_cm2=779.1148749375001,signed_area_cm2=-779.1148749375)
        before=digest(report);normalized=_template_audit_observations(report)
        self.assertEqual(normalized,_template_audit_observations(other))
        self.assertEqual(normalized['panels']['panel']['grain_direction'],[source,1.])
        self.assertEqual(normalized['panels']['panel']['named_edges']['edge']['geometric_stops_uv_cm'][0][0],source)
        self.assertEqual(normalized['seams'][0]['notches'][0]['a'],source)
        self.assertEqual(TEMPLATE_NUMERIC_POLICY['gate_evaluation'],'UNROUNDED_UNCHANGED')
        self.assertEqual(digest(report),before)

    def test_seed_plane_is_computed_from_source_guide_without_material_scaling(self):
        placement=_guide_seed_placement({'vertices':[[3.,4.],[6.,4.],[6.,9.]]},
            {'source_ref':'fixture:measured-plane','origin_cm':[10.,20.,30.],
             'u_axis':[0.,1.,0.],'v_axis':[0.,0.,1.],'offset_uv_cm':[2.,3.]},'coupon')
        import math
        rx,ry,rz=[math.radians(a) for a in placement['rotation_degrees']]
        u=[math.cos(rz)*math.cos(ry),math.sin(rz)*math.cos(ry),-math.sin(ry)]
        v=[math.cos(rz)*math.sin(ry)*math.sin(rx)-math.sin(rz)*math.cos(rx),
           math.sin(rz)*math.sin(ry)*math.sin(rx)+math.cos(rz)*math.cos(rx),math.cos(ry)*math.sin(rx)]
        for uv in ([3.,4.],[6.,9.]):
            actual=[placement['position_cm'][k]+uv[0]*u[k]+uv[1]*v[k] for k in range(3)]
            expected=[10.,20.+uv[0]-2.,30.+uv[1]-3.]
            for a,b in zip(actual,expected):self.assertAlmostEqual(a,b)

    def test_portable_component_templates_keep_native_bindings_unresolved(self):
        from tests.test_sewing import sources
        data,recipe=sources();ref={'path':'approved/source.garmentpkg','sha256':'a'*64}
        pieces=[{'id':pid,'component_id':data['component_id'],'role':'lining','side':'center','layer':'cloth',
            'edges':sorted(panel['edges']),'source_ref':ref} for pid,panel in data['pieces'].items()]
        links=[{key:seam[key] for key in ('piece_a','piece_b','edge_a','edge_b')}|
               {'id':data['component_id']+'::'+seam['id'],'kind':'permanent','source_ref':ref} for seam in data['seams']]
        assembly=plan_assembly({'version':1,'source_ref':ref,'body_ref':ref,'pieces':pieces,'links':links,
            'layers':{'version':1,'source_ref':ref,'mode':'single','interaction':'one_way_declared',
                'nodes':[{'id':'cloth','kind':'garment','panels':sorted(data['pieces']),'colliders':[],'source_ref':ref}],
                'inside_to_outside':[]},'budgets':{'max_frames':100,'max_iterations':300,'max_seconds':100,
                    'max_displacement_cm':8,'max_strain_relative':.1}})
        for seam in data['seams']:seam['kind']='permanent'
        semantics={p['id']:{k:v for k,v in p.items() if k not in ('id','component_id','edges','source_ref')} for p in pieces}
        guides={data['component_id']:{'status':'GARMENT_GUIDES_PREPARED','source_sha256':digest(data),
            'semantics_sha256':digest(semantics),'profile_sha256':'b'*64,'profile_cache_key':'c'*64,'panels':{pid:{'source_ref':'fixture:measured',
            'origin_cm':[0.,0.,0.],'u_axis':[1.,0.,0.],'v_axis':[0.,1.,0.]} for pid in data['pieces']}}}
        inputs=[assembly,data,guides,recipe];before=digest(inputs)
        result=prepare_component_templates(assembly,{data['component_id']:{'source_ref':ref,'data':data}},guides,recipe,{'units':'cm'},ref)
        template=result['components'][data['component_id']]
        self.assertEqual(template['plan_fields']['assembly']['max_displacement_cm'],recipe['limits']['max_displacement_cm'])
        self.assertEqual(template['recipe_template']['limits'],recipe['limits'])
        self.assertEqual(template['preparation_template']['placement_correction']['budgets']['max_displacement_cm'],8.)
        self.assertFalse(template['preparation_template']['source_preform_budget']['physical_budgets_changed'])
        self.assertNotIn('mapping_sha256',template['plan_fields'])
        self.assertEqual(template['recipe_template']['trial_pieces'],sorted(data['pieces']))
        self.assertEqual(template['native_bindings_required'],['BODY_COLLIDER_SNAPSHOT','NATIVE_REGULAR_MESH_MAP','COLLISION_ENVELOPE_REVIEW'])
        self.assertEqual(digest(inputs),before)
        for pid,panel in data['pieces'].items():
            guides[data['component_id']]['panels'][pid]={'source_ref':'fixture:explicit-source-cage',
                'uv_cm':copy.deepcopy(panel['vertices']),'target_cm':[uv+[0.]for uv in panel['vertices']],
                'triangles':copy.deepcopy(panel['faces'])}
        before=digest(inputs)
        caged=prepare_component_templates(assembly,{data['component_id']:{'source_ref':ref,'data':data}},guides,recipe,{'units':'cm'},ref)
        cage_template=caged['components'][data['component_id']]['preparation_template']
        contract('pattern-preparation',cage_template)
        self.assertTrue(all(row['method']=='AFFINE_SOURCE_BOUNDARY_AND_CONVEX_BARYCENTRIC_TARGET_ENVELOPE'
            for row in cage_template['source_preform_budget']['panels'].values()))
        self.assertEqual(caged['qualification'],'NONE');self.assertEqual(digest(inputs),before)

    def test_ordered_fragments_of_one_source_restore_detachable_link_and_exact_face_coverage(self):
        assembly,spec,payloads,recipes,plans=fixture(True)
        source=copy.deepcopy(payloads['source.a']); other=payloads['source.b']; offset=len(source['rest_cm'])
        source['rest_cm'].extend(copy.deepcopy(other['rest_cm']));source['placed_cm'].extend(copy.deepcopy(other['placed_cm']))
        source['faces'].extend([[i+offset for i in face] for face in other['faces']])
        source['panels']['panel.b']={key:([i+offset for i in value] if key in ('indices','boundary') else
            {name:[i+offset for i in indices] for name,indices in value.items()}) for key,value in other['panels']['panel.b'].items()}
        source['seams']={'detachable':{'kind':'detachable','piece_a':'panel.a','piece_b':'panel.b',
            'parameters':[0.,1.],'pairs':[[1,4],[2,7]]}}
        semantics=copy.deepcopy(assembly['piece_semantics'])
        for row in semantics.values():row['component_id']='source.a'
        fragments=[]
        for group in assembly['groups']:
            merged=merge_group_payloads(group,semantics,{'source.a':source})
            merged['rest_mode']='assembled_3d'
            fragments.append(split_group_payload(merged,'source.a'))
        result=assemble_component_fragments(source,fragments)
        self.assertEqual(result['faces'],source['faces'])
        self.assertEqual(result['seams']['detachable']['pairs'],source['seams']['detachable']['pairs'])
        self.assertEqual(result['source_face_pieces'],['panel.a']*2+['panel.b']*2)
        self.assertEqual(face_sources(result)['binding_issues'],[])
        with self.assertRaises(StudioError):assemble_component_fragments(source,fragments+fragments[:1])
    def test_multicomponent_group_preserves_source_uv_face_and_piece_ownership(self):
        assembly, spec, payloads, recipes, plans = fixture(); before = digest([assembly, spec, payloads, recipes, plans])
        compiled = compile_textile_program(assembly, spec, payloads, recipes, plans)
        self.assertEqual(compiled['status'], 'TEXTILE_PROGRAM_PREPARED')
        self.assertEqual(len(compiled['groups']), 1)
        merged = compiled['groups'][0]['payload']
        self.assertEqual(set(merged['source_components']), {'source.a', 'source.b'})
        self.assertEqual(set(merged['panels']), {'panel.a', 'panel.b'})
        self.assertEqual(len(merged['source_face_origins']), 4)
        self.assertEqual(face_sources(merged)['binding_issues'], [])
        self.assertEqual(merged['faces'][0], [3, 0, 1])
        self.assertEqual(merged['source_face_vertex_ids'][0], [3, 0, 1])
        self.assertEqual(digest([assembly, spec, payloads, recipes, plans]), before)

    def test_consolidation_and_split_restore_components_with_source_face_uv(self):
        assembly, spec, payloads, recipes, plans = fixture()
        entry = compile_textile_program(assembly, spec, payloads, recipes, plans)['groups'][0]
        merged, report = consolidate_group(entry['payload'], entry['payload']['placed_cm'], entry['plan'])
        self.assertEqual(report['operation'], 'INDEPENDENT_SOURCE_PANELS_NO_UNION')
        self.assertEqual(report['explicit_unions'], 0)
        for cid, source in payloads.items():
            part = split_group_payload(merged, cid)
            self.assertEqual(part['source_garment_sha256'], source['source_garment_sha256'])
            self.assertEqual(part['source_face_pieces'], list(source['panels'])*2)
            self.assertEqual(face_sources(part)['binding_issues'], [])
            self.assertEqual(face_sources(part)['source_rest_triangles_cm'], face_sources(source)['source_rest_triangles_cm'])

    def test_native_program_orders_preparation_stage_and_frozen_inner_dependencies(self):
        assembly, spec, payloads, recipes, plans = fixture(True)
        compiled = compile_textile_program(assembly, spec, payloads, recipes, plans)
        units = compiled['run_spec']['units']; self.assertEqual(len(units), 24)
        inner, outer = assembly['groups']
        self.assertEqual(units[12]['dependencies'], [inner['id']+'.drape'])
        self.assertEqual(units[13]['dependencies'], [outer['id']+'.prepare.preposition'])
        self.assertEqual([u['arguments']['stage'] for u in units[:12] if u['operation'] == 'transition_textile_group'], list(STAGES))
        self.assertEqual(compiled['continuous_velocity_resume'], 'NOT_CLAIMED')
        self.assertTrue(all(u['success_statuses']==['GROUP_STAGE_COMPLETED'] for u in units if u['operation']=='transition_textile_group'))

    def test_missing_source_mapping_or_differing_physical_policy_refused(self):
        for failure in ('mapping', 'physical', 'identity', 'ownership'):
            assembly, spec, payloads, recipes, plans = fixture()
            if failure == 'mapping': del payloads['source.b']
            if failure == 'physical': recipes['source.b']['phases']['drape']['bending_stiffness'] += .1
            if failure == 'identity': assembly['groups'][0]['pieces'].pop()
            if failure == 'ownership': payloads['source.b']['component_id'] = 'other'
            with self.subTest(failure=failure), self.assertRaises(StudioError):
                compile_textile_program(assembly, spec, payloads, recipes, plans)

    def test_single_belt_consolidation_keeps_its_closure_and_never_welds_ends(self):
        assembly, spec, payloads, recipes, plans = fixture(True)
        group = assembly['groups'][0]; source = payloads['source.a']; pid = 'panel.a'
        source['seams'] = {'ends': {'kind': 'closure', 'piece_a': pid, 'piece_b': pid,
            'edge_a': 'left', 'edge_b': 'right', 'parameters': [0., 1.], 'pairs': [[0, 1], [3, 2]]}}
        merged = merge_group_payloads(group, assembly['piece_semantics'], payloads)
        plan = group_plan(group, merged, plans, spec['assembly_plan_ref'])
        result, report = consolidate(merged, merged['placed_cm'], plan)
        self.assertEqual(report['explicit_unions'], 0)
        self.assertEqual(result['seams']['source.a::ends']['kind'], 'closure')
        self.assertEqual(len(result['rest_cm']), 4)
        self.assertEqual(result['seams']['source.a::ends']['pairs'], [[0, 1], [3, 2]])


if __name__ == '__main__':
    unittest.main()
