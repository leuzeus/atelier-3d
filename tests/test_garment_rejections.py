import copy

from a3d.core import ROOT, StudioError, read_json, sha
from a3d.garment_rejections import inspect_rejection, save_rejection, seam_directions
from a3d.guard import admit_operation
from blender.operations import dispatch
from tests.test_core import Case
from tests.support import ready_project


def curved_payload():
    return {'rest_cm': [[0,0,0],[1,1,0],[2,0,0],[0,0,1000],[1,1,1000],[2,0,1000]],
        'placed_cm': [[0,0,0],[1,1,0],[2,0,0],[0,0,1],[-2,-4,1],[2,0,1]],
        'faces': [[0,1,2],[3,4,5]], 'pins': {},
        'panels': {'front': {'indices': [0,1,2]}, 'back': {'indices': [3,4,5]}},
        'seams': {'curve': {'kind':'permanent','piece_a':'front','piece_b':'back','pairs':[[0,3],[1,4],[2,5]]}}}


class RejectionTests(Case):
    def test_local_curve_tangent_and_global_chord_remain_distinct(self):
        payload=curved_payload(); before=copy.deepcopy(payload)
        source={'seams':[{'id':'curve','edge_a':'cap','edge_b':'armhole'}]}
        report=seam_directions(payload,payload['placed_cm'],source)
        self.assertEqual(report['seams']['curve']['opposition_extent'],'some_local_segments')
        self.assertEqual(report['seams']['curve']['endpoint_chord_cosine'],1)
        bad=report['violations'][0]
        self.assertEqual((bad['seam_id'],bad['edge_a'],bad['edge_b']),('curve','cap','armhole'))
        self.assertLess(bad['cosine'],-.5); self.assertEqual(bad['threshold'],-.5)
        self.assertEqual(bad['previous_pair'][0]['rest_uv_cm'],[0,0])
        self.assertEqual(bad['next_pair'][1]['position_cm'],[-2,-4,1])
        self.assertEqual(payload,before)
        coords=copy.deepcopy(payload['placed_cm']);coords[3:]=[[2,0,1],[1,-1,1],[0,0,1]]
        reverse=seam_directions(payload,coords,source)
        self.assertEqual(reverse['seams']['curve']['endpoint_chord_cosine'],-1)
        self.assertEqual(reverse['seams']['curve']['opposition_extent'],'all_local_segments')
        coords[0]=coords[1]
        self.assertIsNone(seam_directions(payload,coords,source)['violations'][0]['cosine'])

    def test_historical_inspection_preserves_failure_and_refuses_tamper_scope(self):
        project=ready_project(self.root,True); recipe=read_json(ROOT/'templates/sewing-recipe.json')
        error=StudioError('Rejected initial contact')
        error.initial_contacts=[{'piece':'front','index':4,'collider':'Arm','depth_cm':1.8128}]
        data={'component_id':'garment.coat','seams':[]}
        ref=save_rejection(project,data,recipe,None,error,{'path':'synthetic.blend','sha256':'a'*64})
        directory=(project.root/ref['path']).parent
        with project.transaction() as db:
            state=project.state(db);state['pending_blender_operation']={'status':'failed','diagnostic':ref}
            project.save(db,state,'synthetic_failure',{})
        before=sha(project.db)
        args={'component_id':'garment.coat','attempt_dir':directory.relative_to(project.root).as_posix()}
        admit_operation(project,'inspect_garment_failure',args)
        result=dispatch(str(project.root),'inspect_garment_failure',args)
        self.assertEqual(result['initial_contacts'],error.initial_contacts)
        self.assertEqual(result['simulation'],'NOT_EXECUTED'); self.assertFalse(result['accepted'])
        self.assertEqual(sha(project.db),before)
        self.assertTrue(project.state()['pending_blender_operation'])
        with self.assertRaises(StudioError):inspect_rejection(project,'foreign',args['attempt_dir'])
        with self.assertRaises(StudioError):inspect_rejection(project,'garment.coat','.a3d/evidence')
        (project.root/ref['path']).write_text('{}')
        with self.assertRaisesRegex(StudioError,'changed'):admit_operation(project,'inspect_garment_failure',args)
