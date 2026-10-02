import copy
from pathlib import Path

from a3d.core import ROOT, StudioError, atomic_json, read_json, sha
from a3d.guard import admit_operation
from a3d.sewing_diagnostics import failure_geometry, inspect_failure, store_probe_failure, motion_metrics
from blender.operations import dispatch
from blender.sewing import subset_mesh
from tests.test_core import Case
from tests.support import ready_project


def payload():
    return {'rest_cm':[[0,0,0],[2,0,0],[0,2,0],[10,0,1000],[12,0,1000],[10,2,1000]],
        'placed_cm':[[0,0,0],[2,0,0],[0,2,0],[10,0,0],[12,0,0],[10,2,0]],
        'faces':[[0,1,2],[3,4,5]], 'pins':{'4':0.5},
        'panels':{p:{'indices':[o,o+1,o+2],'boundary':[o,o+1,o+2],'edges':{'edge':[o,o+1]}}
            for p,o in (('body',0),('sleeve',3))},
        'seams':{'armhole':{'kind':'permanent','piece_a':'body','piece_b':'sleeve','pairs':[[1,3],[2,5]]}}}


class DiagnosticTests(Case):
    def setUp(self):
        super().setUp()
        self.recipe = read_json(ROOT / 'templates/sewing-recipe.json')

    def test_motion_tracks_source_and_distinct_increment_maxima_without_mutation(self):
        data=subset_mesh(payload(),['sleeve']);before=copy.deepcopy(data)
        start=data['placed_cm'];previous=copy.deepcopy(start);coords=copy.deepcopy(start)
        previous[0][0]+=9;coords[0][0]+=10;coords[1][1]+=4
        report=motion_metrics(data,coords,start,2,previous,1,budget_cm=9)
        self.assertEqual(report['max_excursion']['source_vertex_index'],3)
        self.assertEqual(report['max_excursion']['piece'],'sleeve')
        self.assertEqual(report['max_excursion']['distance_cm'],10)
        self.assertEqual(report['max_increment']['source_vertex_index'],4)
        self.assertEqual(report['max_increment']['distance_cm'],4)
        self.assertEqual(report['max_increment']['pin_weight'],.5)
        self.assertEqual(report['max_increment']['delta_cm'],[0,4,0])
        self.assertEqual(report['pieces']['sleeve']['max_increment'],report['max_increment'])
        self.assertTrue(report['budget_exceeded']);self.assertEqual(data,before)

    def test_historical_motion_never_invents_increment_and_bad_geometry_is_unavailable(self):
        data=payload();start=data['placed_cm'];coords=copy.deepcopy(start);coords[1][0]+=5
        report=motion_metrics(data,coords,start,24,budget_cm=5)
        self.assertEqual(report['increment_status'],'NOT_RECORDED')
        self.assertIsNone(report['max_increment']);self.assertFalse(report['budget_exceeded'])
        self.assertEqual(report['max_excursion']['named_edges'],['edge'])
        self.assertEqual(motion_metrics(data,coords,start,1,start,1)['increment_status'],'NOT_RECORDED')
        coords[0][0]=None
        self.assertEqual(motion_metrics(data,coords,start,2)['excursion_status'],'UNAVAILABLE')
        self.assertIsNone(motion_metrics(data,coords[:-1],start,2)['budget_exceeded'])

    def test_localizes_compression_stretch_faces_seams_and_sources(self):
        data=payload(); before=copy.deepcopy(data)
        coords=copy.deepcopy(data['placed_cm']);coords[1]=[0.01,0,0];coords[4]=[14,0,0]
        report=failure_geometry(data,coords,data['placed_cm'],self.recipe,[{'index':4,'depth_cm':0.2}])
        self.assertTrue(report['finite_matching_topology'])
        self.assertIn('compression',report['outlier_edges'][0]['reasons'])
        self.assertTrue(any('stretch' in e['reasons'] for e in report['outlier_edges']))
        self.assertTrue(report['outlier_faces'])
        self.assertEqual(report['seam_gaps']['armhole']['outside_tolerance'],2)
        self.assertEqual(report['penetrations'][0]['index'],4)
        self.assertEqual(data,before)

    def test_subset_preserves_global_identity_and_remaps_every_boundary(self):
        data=payload();sub=subset_mesh(data,['sleeve'])
        self.assertEqual(sub['source_vertex_indices'],[3,4,5])
        self.assertEqual(sub['source_face_indices'],[1])
        self.assertEqual(sub['panels']['sleeve']['boundary'],[0,1,2])
        self.assertEqual(sub['panels']['sleeve']['edges']['edge'],[0,1])
        self.assertEqual(sub['pins'],{'1':0.5})
        self.assertEqual(sub['omitted_seams'],['armhole'])
        coords=copy.deepcopy(sub['placed_cm']);coords[1]=coords[0]
        report=failure_geometry(sub,coords,sub['placed_cm'],self.recipe)
        self.assertEqual(report['outlier_edges'][0]['source_indices'],[3,4])
        self.assertEqual(report['outlier_faces'][0]['source_face'],1)
        self.assertEqual(report['subset_kind'],'whole-pattern-pieces')

    def test_nonfinite_geometry_retained_as_null_and_not_accepted(self):
        data=payload();coords=copy.deepcopy(data['placed_cm']);coords[0][0]=float('nan')
        report=failure_geometry(data,coords,data['placed_cm'],self.recipe)
        self.assertFalse(report['finite_matching_topology'])
        self.assertIsNone(report['evaluated_cm'][0][0])
        self.assertEqual(report['outlier_edges'],[])

    def test_probe_status_native_integrity_and_preview_are_distinct_from_garment(self):
        project=ready_project(self.root,True)
        directory=project.data/'blender/sewing/attempt-probe';directory.mkdir(parents=True)
        output=directory/'backend-probes';output.mkdir()
        data={'component_id':'synthetic.probe.sewing','simulation':'FAIL','frame':24,'error':'open coupon',
            'scope':'backend-probe','phase':'mount','execution_stage':'backend_probe','garment_simulation':'NOT_EXECUTED',
            'backend_probe_simulation':'FAIL','probe':{'case':'sewing','configured_frames':24,'requested_phase_frames':48},
            'geometry':failure_geometry(payload(),payload()['placed_cm'],payload()['placed_cm'],self.recipe)}
        native_ref=store_probe_failure(output,data)
        data.update(component_id='garment.coat',scope='local',binding='d'*64,package_sha256='a'*64,
            recipe_sha256='b'*64,boundary_map_sha256='c'*64,
            probe_diagnostic={'path':Path(native_ref['path']).relative_to(project.root).as_posix(),'sha256':native_ref['sha256']})
        diagnostic=directory/'diagnostic.json';atomic_json(diagnostic,data)
        atomic_json(directory/'failure.json',{'simulation':'FAIL','binding':'d'*64,'scope':'local',
            'diagnostic':{'path':diagnostic.relative_to(project.root).as_posix(),'sha256':sha(diagnostic)}})
        report=inspect_failure(project,'garment.coat',directory.relative_to(project.root).as_posix())
        self.assertEqual(report['garment_simulation'],'NOT_EXECUTED')
        self.assertEqual(report['backend_probe_simulation'],'FAIL')
        image=Path(native_ref['path']).with_suffix('.svg')
        self.assertIn('vêtement NON EXÉCUTÉ',image.read_text(encoding='utf-8'))
        image.write_text('changed')
        with self.assertRaisesRegex(StudioError,'probe preview changed'):
            inspect_failure(project,'garment.coat',directory.relative_to(project.root).as_posix())

    def test_failure_inspection_preserves_pending_gates_and_refuses_tamper(self):
        project=ready_project(self.root,True)
        directory=project.data/'blender/sewing/attempt-synthetic';directory.mkdir(parents=True)
        geometry=failure_geometry(payload(),payload()['placed_cm'],payload()['placed_cm'],self.recipe)
        data={'component_id':'garment.coat','simulation':'FAIL','frame':24,'error':'measured compression',
            'scope':'local','phase':'mount','package_sha256':'a'*64,'recipe_sha256':'b'*64,
            'boundary_map_sha256':'c'*64,'binding':'d'*64,'geometry':geometry}
        diagnostic=directory/'diagnostic.json';atomic_json(diagnostic,data)
        ref={'path':diagnostic.relative_to(project.root).as_posix(),'sha256':sha(diagnostic)}
        atomic_json(directory/'failure.json',{'simulation':'FAIL','diagnostic':ref,'binding':'d'*64,'scope':'local'})
        with project.transaction() as db:
            state=project.state(db);state['pending_blender_operation']={'status':'failed'}
            project.save(db,state,'synthetic_failure',{})
        before=sha(project.db)
        args={'component_id':'garment.coat','attempt_dir':directory.relative_to(project.root).as_posix()}
        admit_operation(project,'inspect_sewing_failure',args)
        result=dispatch(str(project.root),'inspect_sewing_failure',args)
        self.assertEqual(result['simulation'],'FAIL');self.assertFalse(result['accepted'])
        self.assertEqual(result['motion']['excursion_status'],'MEASURED')
        self.assertEqual(result['motion']['increment_status'],'NOT_RECORDED')
        self.assertEqual(sha(project.db),before)
        with self.assertRaises(StudioError):inspect_failure(project,'foreign.mesh',args['attempt_dir'])
        with self.assertRaises(StudioError):inspect_failure(project,'garment.coat','.a3d/evidence')
        atomic_json(diagnostic,{**data,'frame':25})
        with self.assertRaisesRegex(StudioError,'changed'):admit_operation(project,'inspect_sewing_failure',args)
        initial=directory/'placement.json'
        atomic_json(initial,{k:data[k] for k in ('component_id','package_sha256','recipe_sha256','boundary_map_sha256')})
        data['placement']={'path':initial.relative_to(project.root).as_posix(),'sha256':sha(initial)}
        atomic_json(diagnostic,data)
        ref['sha256']=sha(diagnostic)
        atomic_json(directory/'failure.json',{'simulation':'FAIL','diagnostic':ref,'binding':'d'*64,'scope':'local'})
        self.assertEqual(inspect_failure(project,'garment.coat',args['attempt_dir'])['placement'],data['placement'])
        atomic_json(initial,{'component_id':'foreign'})
        with self.assertRaisesRegex(StudioError,'placement diagnostic changed'):
            inspect_failure(project,'garment.coat',args['attempt_dir'])
