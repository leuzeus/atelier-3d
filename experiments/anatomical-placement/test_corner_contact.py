import copy,json
from pathlib import Path
import unittest
import numpy as np
from solve_corner_contact import VariableEqualities,MetricFactor,ScalarProjection,Budget,verified_sewing_equalities
from solve_piece_metric import metric

def fixture():
    cage={'uv_cm':[[0.,0.],[1.,0.],[0.,1.],[5.,0.],[6.,0.],[5.,1.]],
        'triangles':[[0,1,2],[3,4,5]],'target_cm':[[0.,0.,0.],[1.,0.,0.],[0.,1.,0.],[0.,0.,0.],[1.2,0.,0.],[0.,1.,0.]]}
    return cage,[0,2,3,5],[[1,4]],{'max_seconds':5.,'position_penalty':1e-6}

class CornerTests(unittest.TestCase):
    def test_qr_eliminates_coordinate_equality_without_welding_source(self):
        cage,fixed,pairs,settings=fixture();initial=copy.deepcopy(cage);factor=MetricFactor(cage,fixed,settings,Budget(settings),pairs)
        xyz=np.array(cage['target_cm']);self.assertEqual(len(factor.free),1)
        for _ in range(200):
            xyz=factor.step(xyz);self.assertTrue(np.array_equal(xyz[1],xyz[4]))
        self.assertEqual(cage,initial);self.assertTrue(np.array_equal(xyz[fixed],np.array(initial['target_cm'])[fixed]))
        self.assertEqual(metric(cage,xyz)['outside_triangles'],0)
        self.assertEqual(len(cage['uv_cm']),6);self.assertEqual(cage['triangles'],[[0,1,2],[3,4,5]])

    def test_differing_fixed_coordinates_refuse_before_qr(self):
        cage,fixed,pairs,settings=fixture();cage['target_cm'][3]=[.2,0.,0.]
        with self.assertRaisesRegex(ValueError,'EQUALITY_CONTRADICTS_FIXED_ANATOMY'):
            MetricFactor(cage,fixed,settings,Budget(settings),[[0,3]])

    def test_scalar_contact_rows_are_combined_in_equality_variable_space(self):
        cage,fixed,pairs,settings=fixture();budget=Budget(settings);factor=MetricFactor(cage,fixed,settings,budget,pairs)
        xyz=factor.step(np.array(cage['target_cm']));rows=np.zeros((2,6,3));rows[0,1,2]=1.;rows[1,4,2]=1.
        solver=ScalarProjection(factor,rows,np.array([.3,.3]),budget);result,residual=solver.project(xyz,20)
        self.assertTrue(np.array_equal(result[1],result[4]));self.assertAlmostEqual(result[1,2],.3,places=12)
        self.assertLess(residual,1e-10);self.assertTrue(np.array_equal(result[fixed],np.array(cage['target_cm'])[fixed]))

    def test_source_corner_relation_authenticates_existing_unit_supports(self):
        cage,fixed,pairs,settings=fixture();rows=[]
        for name,i in [('s-a',1),('s-b',4)]:
            rows.append({'binding_id':name,'source_seam_id':name,'driver':{'piece':'driver','existing_control_indices':[i],
                'source_uv_cm':cage['uv_cm'][i],'support':{'control_indices':[i],'weights':[1.],
                'evaluated_world_cm':cage['target_cm'][i]}},'partner':{'piece':'partner','source_uv_cm':[2.,3.],'source_corner_vertex_ids':[7]}})
        bindings={'binding_set_sha256':'exact-binding-set','driver_piece':'driver','bindings':rows}
        document={'method':'SHARED_PARTNER_SOURCE_CORNER_EQUALITY_V1','source_boundary_binding_set_sha256':'exact-binding-set',
            'driver_piece':'driver','constraints':[{'source_binding_ids':['s-a','s-b'],'source_seam_ids':['s-a','s-b'],'driver_control_indices':[1,4]}]}
        recipe={'seams':{'s-a':{'kind':'permanent'},'s-b':{'kind':'permanent'}}}
        self.assertEqual(verified_sewing_equalities(document,bindings,cage,'driver',recipe),[[1,4]])
        forged=copy.deepcopy(bindings);forged['bindings'][1]['partner']['source_uv_cm']=[2.1,3.]
        with self.assertRaisesRegex(ValueError,'PARTNER_SOURCE_POINT_NOT_IDENTICAL'):
            verified_sewing_equalities(document,forged,cage,'driver',recipe)
        forged=copy.deepcopy(bindings);forged['bindings'][1]['driver']['support']['weights']=[.999]
        with self.assertRaisesRegex(ValueError,'EXACT_UNIT_CAGE_SUPPORT_REQUIRED'):
            verified_sewing_equalities(document,forged,cage,'driver',recipe)

if __name__=='__main__':
    result=unittest.TextTestRunner(verbosity=2).run(unittest.defaultTestLoader.loadTestsFromTestCase(CornerTests))
    Path('corner-test-report.json').write_text(json.dumps({'tests':result.testsRun,'failures':len(result.failures),'errors':len(result.errors),
        'passed':result.wasSuccessful(),'qualification':'NONE','scope':'PORTABLE_EQUALITY_ELIMINATION_ONLY'},indent=2),encoding='utf-8')
    raise SystemExit(0 if result.wasSuccessful() else 1)
