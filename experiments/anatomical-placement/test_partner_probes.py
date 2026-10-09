import copy
import unittest
import numpy as np
from propose_partner_rigid import rows_for_piece
from prepare_sewn_band import prepare
from sparse_metric_factor import SparseMetricFactor
from solve_piece_contact import MetricFactor,Budget


def fixture():
    cage={'uv_cm':[[0.,0.],[1.,0.],[0.,1.],[1.,1.]],'triangles':[[0,1,2],[1,3,2]],
        'target_cm':[[0.,0.,0.],[1.,0.,0.],[0.,1.,0.],[1.,1.2,.3]]}
    return cage


def binding(i,point, fraction):
    support={'control_indices':[0,1,2],'weights':[float(j==i) for j in range(3)],'evaluated_world_cm':point}
    return {'binding_id':str(i),'source_seam_id':'source-seam',
        'partner':{'piece':'panel','existing_control_indices':[i],'source_uv_cm':point[:2],
            'common_fraction':fraction,'source_edge_length_cm':3.,'support':copy.deepcopy(support)},
        'driver':{'piece':'driver','support':copy.deepcopy(support)}}


class PartnerProbes(unittest.TestCase):
    def test_uneven_partition_uses_source_length_not_density(self):
        cage=fixture();frames={'panel':cage,'driver':copy.deepcopy(cage)}
        bindings=[binding(i,cage['target_cm'][i],f) for i,f in enumerate((0.,.1,1.))]
        before=copy.deepcopy((frames,bindings));rows=rows_for_piece(bindings,frames,'panel')
        np.testing.assert_allclose([r['weight'] for r in rows],[.15,1.5,1.35],rtol=0.,atol=1e-15)
        self.assertAlmostEqual(sum(r['weight'] for r in rows),3.)
        self.assertEqual((frames,bindings),before)

    def test_stale_evaluated_support_is_refused(self):
        cage=fixture();frames={'panel':cage,'driver':cage}
        bindings=[binding(i,cage['target_cm'][i],f) for i,f in enumerate((0.,.1,1.))]
        bindings[1]['driver']['support']['evaluated_world_cm']=[9.,0.,0.]
        with self.assertRaisesRegex(ValueError,'STALE_SUPPORT_VALUE'):rows_for_piece(bindings,frames,'panel')

    def test_frozen_halo_conflict_is_only_a_subproblem_refusal(self):
        cage=fixture();driver=copy.deepcopy(cage);driver['target_cm'][0]=[10.,0.,0.]
        frames={'panel':cage,'driver':driver};row=binding(0,cage['target_cm'][0],0.)
        block={'free_control_indices':[0,1],'halo_control_indices':[2,3],'material_edge_band_cm':2.}
        before=copy.deepcopy(frames);result=prepare(frames,[row],'panel',block)
        self.assertEqual(result['status'],'FROZEN_BLOCK_NECESSARY_PATH_CONFLICT')
        self.assertEqual(result['qualification'],'NONE');self.assertEqual(frames,before)
        self.assertGreater(result['necessary_path_conflicts'][0]['necessary_upper_bound_excess_cm'],8.)

    def test_nonunit_support_is_not_snapped_to_existing_hint(self):
        cage=fixture();frames={'panel':cage,'driver':cage};a=binding(0,cage['target_cm'][0],0.)
        b=binding(1,cage['target_cm'][1],1.);b['partner']['support']['weights']=[.2,.8,0.]
        block={'free_control_indices':[0,1],'halo_control_indices':[2,3],'material_edge_band_cm':2.}
        result=prepare(frames,[a,b],'panel',block)
        self.assertEqual(set(result['temporary_sewing_targets']),{0})
        self.assertEqual(result['nonunit_sewing_supports_not_frozen'],['1'])

    def test_sparse_step_matches_qr_on_well_conditioned_case(self):
        cage=fixture();settings={'max_seconds':5.,'position_penalty':1e-6,'max_controls':20,
            'max_gradient_rows':20,'lsmr_tolerance':1e-13,'max_condition_estimate':1e12,'max_linear_iterations':100}
        budget=Budget(settings);dense=MetricFactor(cage,[0,1],settings,budget);sparse=SparseMetricFactor(cage,[0,1],settings,budget)
        world=np.asarray(cage['target_cm']);a=dense.step(world);b=sparse.step(world)
        np.testing.assert_allclose(a,b,atol=1e-10,rtol=0.)
        np.testing.assert_array_equal(b[[0,1]],world[[0,1]])

    def test_sparse_iteration_exhaustion_is_refused(self):
        cage=fixture();settings={'max_seconds':5.,'position_penalty':1e-6,'max_controls':20,
            'max_gradient_rows':20,'lsmr_tolerance':1e-14,'max_condition_estimate':1e12,'max_linear_iterations':1}
        factor=SparseMetricFactor(cage,[0],settings,Budget(settings))
        with self.assertRaisesRegex(ValueError,'SPARSE_LEAST_SQUARES_INCOMPLETE'):factor.step(np.asarray(cage['target_cm']))

    def test_sparse_dimensions_refused_before_build(self):
        settings={'max_seconds':5.,'max_controls':2,'max_gradient_rows':2}
        with self.assertRaisesRegex(ValueError,'SPARSE_DIMENSION_BUDGET'):SparseMetricFactor(fixture(),[0],settings,Budget(settings))


if __name__=='__main__':unittest.main()
