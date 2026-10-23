import copy
import math
import unittest
from a3d.core import StudioError
from a3d.sewn_continuity import transfer_coordinates,local_status
from a3d.core import atomic_json,sha
from unittest.mock import patch
from types import SimpleNamespace
from tests.test_core import Case


class SewingTransfer(unittest.TestCase):
    def test_latest_local_failure_is_not_absent_or_historical_success(self):
        self.assertEqual(local_status({'binding':'current','simulation':'FAIL'},'current'),'FAIL')
        self.assertEqual(local_status({'binding':'current','simulation':'PASS'},'current'),'PASS')
        self.assertIsNone(local_status({'binding':'old','simulation':'PASS'},'current'))
        self.assertIsNone(local_status(None,'current'))

    def fixture(self):
        points=[[0,0,0],[1,0,0],[0,1,0],[3,0,0],[4,0,0],[3,1,0]]
        payload={'rest_cm':copy.deepcopy(points),'placed_cm':copy.deepcopy(points),'faces':[[0,1,2],[3,4,5]],
            'panels':{'left':{'indices':[0,1,2]},'right':{'indices':[3,4,5]}}}
        recipe={'trial_pieces':['left'],'mesh':{'min_angle_degrees':2,'min_edge_cm':.001,'min_stretch':.8,'max_stretch':1.25}}
        report={'simulation':'PASS','scope':'local','qualification':'PHYSICS_ONLY','trial_pieces':['left'],
            'local_result_cm':[[x,y,z+.2] for x,y,z in points[:3]],'context':{'colliders':[]}}
        return payload,recipe,report

    def test_exact_transfer_keeps_other_vertices_and_rest(self):
        p,r,s=self.fixture();before=copy.deepcopy(p)
        result,ids=transfer_coordinates(p,r,s)
        self.assertEqual(ids,[0,1,2]);self.assertEqual(result[:3],s['local_result_cm'])
        self.assertEqual(result[3:],p['placed_cm'][3:]);self.assertEqual(p,before)

    def test_indices_units_counts_and_nonfinite_are_refused(self):
        for key,value in [('source_vertex_indices',[1,0,2]),('units','m'),('local_result_cm',[[0,0,0]]),
                ('local_result_cm',[[0,0,math.nan],[1,0,0],[0,1,0]])]:
            p,r,s=self.fixture();s[key]=value
            with self.subTest(key=key),self.assertRaises(StudioError):transfer_coordinates(p,r,s)

    def test_fitting_tacks_colliders_and_partial_success_cannot_transfer(self):
        for key,value in [('simulation','FAIL'),('qualification','CONSTRUCTION_FITTING_ONLY'),
                ('fitting_tacks',[{'id':'closure'}]),('context',{'colliders':[{'object':'body'}]})]:
            p,r,s=self.fixture();s[key]=value
            with self.subTest(key=key),self.assertRaises(StudioError):transfer_coordinates(p,r,s)


class StageBindings(Case):
    def test_completed_stage_requires_exact_recipe_geometry_and_map(self):
        from blender.sewn_stages import stage_receipt
        project=SimpleNamespace(root=self.root)
        payload={'component_id':'coat','package_sha256':'package'}
        receipt={'component_id':'coat','package_sha256':'package','mesh_sha256':'before',
            'map_sha256':'map','recipe_sha256':'recipe'}
        result={'simulation':'PASS','scope':'full','recipe_sha256':'recipe',
            'result_mesh_sha256':'after','boundary_map_sha256':'map'}
        atomic_json(self.root/'stage.json',receipt);atomic_json(self.root/'full.json',result)
        obj={'a3d_sewn_stage_receipt':'stage.json','a3d_sewn_stage_receipt_sha256':sha(self.root/'stage.json'),
            'a3d_sewing_mesh_sha256':'map','a3d_sewn_stage_result':'full.json',
            'a3d_sewn_stage_result_sha256':sha(self.root/'full.json')}
        with patch('blender.sewn_stages.mesh_digest',return_value='after'):
            stage_receipt(project,obj,payload,allow_completed=True)
            with self.assertRaises(StudioError):stage_receipt(project,obj,payload)
            for key in ('recipe_sha256','boundary_map_sha256','result_mesh_sha256'):
                changed=copy.deepcopy(result);changed[key]='stale';atomic_json(self.root/'full.json',changed)
                obj['a3d_sewn_stage_result_sha256']=sha(self.root/'full.json')
                with self.subTest(key=key),self.assertRaises(StudioError):
                    stage_receipt(project,obj,payload,allow_completed=True)

    def test_receipt_file_mutation_is_refused_before_reuse(self):
        from blender.sewn_stages import stage_receipt
        atomic_json(self.root/'stage.json',{'mesh_sha256':'before'})
        obj={'a3d_sewn_stage_receipt':'stage.json','a3d_sewn_stage_receipt_sha256':sha(self.root/'stage.json')}
        atomic_json(self.root/'stage.json',{'mesh_sha256':'after'})
        with self.assertRaisesRegex(StudioError,'changed sewn stage receipt'):
            stage_receipt(SimpleNamespace(root=self.root),obj,{})
