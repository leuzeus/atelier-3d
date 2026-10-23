"""Metric regressions independent of Blender and of any physical approval."""
import copy
import math
import unittest

from a3d.core import StudioError,digest
from a3d.cloth_metrics import (METRIC_VERSION,VALIDATOR_VERSION,evaluate_metrics,face_sources,
    principal_stretches,validate_linear_motion,validate_metrics)
from a3d.pattern_assembly import (bounded_close,consolidate,continuous_quality,map_digest,
    migrate_legacy_receipt,preform_coordinates)
from a3d.pattern_preparation import preparation_statistics
from a3d.sewing import mesh_quality
from tests.test_pattern_assembly import example


def triangle():
    return {'rest_cm':[[0.,0.,0.],[1.,0.,0.],[0.,1.,0.]],'faces':[[0,1,2]],
            'panels':{'coupon':{'indices':[0,1,2]}},'seams':{}}


LIMITS={'min_angle_degrees':5.,'min_edge_cm':.01,'min_stretch':.9,'max_stretch':1.05}


class ClothMetrics(unittest.TestCase):
    def test_shear_hidden_from_edge_ratios_is_refused_by_shared_gate(self):
        payload=triangle();coords=[[0.,0.,0.],[1.,0.,0.],[.2,1.,0.]]
        old=mesh_quality(payload['rest_cm'],coords,payload['faces'],LIMITS)
        self.assertLess(old['max_stretch'],LIMITS['max_stretch'])
        self.assertGreater(old['min_stretch'],LIMITS['min_stretch'])
        before=digest(payload)
        with self.assertRaises(StudioError) as caught:validate_metrics(payload,coords,LIMITS)
        self.assertEqual(caught.exception.quality_violations,['principal_stretch'])
        report=caught.exception.quality_metrics
        self.assertAlmostEqual(report['min_principal_stretch'],.904987562112089)
        self.assertAlmostEqual(report['max_principal_stretch'],1.104987562112089)
        self.assertEqual(report['extrema']['max_principal_stretch']['face'],0)
        self.assertEqual(report['extrema']['max_principal_stretch']['piece'],'coupon')
        self.assertEqual(report['metric_version'],METRIC_VERSION)
        self.assertEqual(report['validator_version'],VALIDATOR_VERSION)
        self.assertEqual(before,digest(payload))
        admitted=validate_metrics(payload,coords,{**LIMITS,'min_stretch':.8,'max_stretch':1.25})
        self.assertEqual(admitted['violations'],[])

    def test_every_pure_stage_uses_principal_gate_before_closing_or_welding(self):
        payload,plan=example();placed,_=preform_coordinates(payload,plan)
        plan['quality']=dict(LIMITS)
        sheared=[[x+.2*y,y,z] for x,y,z in placed]
        with self.assertRaisesRegex(StudioError,'principal_stretch'):continuous_quality(payload,sheared,plan['quality'])
        unchanged,report=bounded_close(payload,sheared,plan)
        self.assertEqual(report['status'],'REFUSED')
        self.assertEqual(report['reason'],'initial_geometry_rejected')
        self.assertEqual(report['accepted_steps'],0)
        self.assertEqual(unchanged,sheared)
        self.assertIn('principal_stretch',report['quality']['violations'])
        with self.assertRaisesRegex(StudioError,'principal_stretch'):consolidate(payload,sheared,plan)

    def test_developable_extrusion_has_bending_and_unit_in_plane_metric(self):
        count=12;step=math.pi/12;radius=.5/math.sin(step/2)
        rest=[[float(i),float(j),0.] for j in (0,1) for i in range(count+1)]
        coords=[[radius*math.sin(i*step),float(j),radius*(1-math.cos(i*step))]
                for j in (0,1) for i in range(count+1)]
        faces=[]
        for i in range(count):faces.extend([[i,i+1,count+i+2],[i,count+i+2,count+i+1]])
        payload={'rest_cm':rest,'faces':faces,'panels':{'bent':{'indices':list(range(len(rest)))}},'seams':{}}
        report=validate_metrics(payload,coords,LIMITS,include_faces=True)
        self.assertAlmostEqual(report['min_principal_stretch'],1.,places=12)
        self.assertAlmostEqual(report['max_principal_stretch'],1.,places=12)
        self.assertAlmostEqual(report['bending']['placed_dihedral_degrees']['max'],15.)
        self.assertEqual(report['bending']['source_dihedral_degrees']['max'],0.)
        self.assertTrue(all(abs(m['area_ratio']-1)<1e-12 for m in report['face_metrics']))
        prepared=preparation_statistics(payload,coords)
        self.assertEqual(prepared['bending'],report['bending'])
        self.assertEqual([m['principal_stretch'] for m in prepared['face_metrics']],
                         [m['principal_stretch'] for m in report['face_metrics']])

    def test_rigid_rotations_and_normal_reversal_are_not_material_inversion_evidence(self):
        payload=triangle()
        for coords in ([[3+x,7-y,9-z] for x,y,z in payload['rest_cm']],
                       [[3+z,7+x,9+y] for x,y,z in payload['rest_cm']]):
            report=validate_metrics(payload,coords,LIMITS)
            self.assertEqual(report['min_principal_stretch'],1.)
            self.assertEqual(report['max_principal_stretch'],1.)
            self.assertEqual(report['orientation']['material_side_inversion'],'NOT_DETERMINABLE_FROM_POSITIONS_ONLY')
            self.assertFalse(report['orientation']['normal_world_sign_is_inversion'])

    def test_collapsed_geometry_and_demonstrated_source_winding_change_are_refused(self):
        payload=triangle();collapsed=[[0.,0.,0.],[1.,0.,0.],[2.,0.,0.]]
        with self.assertRaises(StudioError) as caught:validate_metrics(payload,collapsed,LIMITS)
        self.assertIn('degenerate_or_sliver',caught.exception.quality_violations)
        payload.update({k:v for k,v in face_sources(payload).items() if k.startswith('source_')})
        payload['faces'][0].reverse()
        with self.assertRaises(StudioError) as caught:validate_metrics(payload,payload['rest_cm'],LIMITS)
        self.assertIn('source_orientation_or_topology',caught.exception.quality_violations)
        self.assertEqual(caught.exception.quality_metrics['orientation']['source_binding_issues'][0]['code'],
                         'SOURCE_FACE_WINDING_OR_BINDING_CHANGED')

    def test_linear_operation_detects_midstep_collapse_without_a_world_normal_gate(self):
        payload=triangle();before=payload['rest_cm']
        after=[[x,-y,z] for x,y,z in before]
        # Endpoint is a valid rigid 180-degree pose. The specified straight-line
        # vertex operation is a different path and collapses halfway through.
        validate_metrics(payload,after,LIMITS)
        with self.assertRaises(StudioError) as caught:validate_linear_motion(payload,before,after)
        self.assertAlmostEqual(caught.exception.quality_metrics['worst']['fraction'],.5)
        quarter=[[x,0.,y] for x,y,z in before]
        self.assertGreater(validate_linear_motion(payload,before,quarter)['minimum_area_cm2'],0.)

    def test_continuous_faces_keep_distinct_uv_islands_piece_ids_and_mass(self):
        payload,plan=example()
        # Move the right source UV island without changing its physical shape.
        for index in payload['panels']['right']['indices']:
            payload['rest_cm'][index][0]+=100.;payload['rest_cm'][index][1]+=200.
        plan['mapping_sha256']=map_digest(payload)
        plan['preform']['panels']['right']['offset_uv_cm']=[100.,200.]
        placed,_=preform_coordinates(payload,plan);closed,report=bounded_close(payload,placed,plan)
        self.assertEqual(report['status'],'GEOMETRY_READY')
        continuous,_=consolidate(payload,closed,plan)
        self.assertEqual(continuous['source_face_pieces'],['left','left','right','right'])
        self.assertEqual(continuous['source_rest_triangles_cm'][2][0],[100.,200.])
        before=digest(continuous)
        metrics=validate_metrics(continuous,continuous['placed_cm'],plan['quality'],include_faces=True)
        stats=preparation_statistics(continuous,mass={'basis':'areal_density_kg_m2','value':.3})
        self.assertEqual([m['piece'] for m in metrics['face_metrics']],continuous['source_face_pieces'])
        self.assertEqual(stats['per_piece']['right']['source_bbox_cm'],[[100.,200.],[102.,202.]])
        self.assertAlmostEqual(stats['mass']['total_mass_kg'],8./10000*.3)
        self.assertEqual(digest(continuous),before)
        # Cyclic vertex rotations preserve winding and align the same UV data.
        rotated=copy.deepcopy(continuous);rotated['faces'][2]=rotated['faces'][2][1:]+rotated['faces'][2][:1]
        rotated_report=validate_metrics(rotated,rotated['placed_cm'],plan['quality'])
        self.assertAlmostEqual(rotated_report['max_principal_stretch'],metrics['max_principal_stretch'])

    def test_small_singular_value_does_not_disappear_through_subtraction(self):
        values=principal_stretches([[0.,0.],[1.,0.],[0.,1.]],[[0.,0.,0.],[1.,0.,0.],[0.,1e-9,0.]])
        self.assertAlmostEqual(values[0],1e-9,places=18)
        self.assertEqual(values[1],1.)

    def test_historical_pass_is_preserved_without_metric_qualification_transfer(self):
        receipt={'status':'PASS','quality':{'min_stretch':.91,'max_stretch':1.02}}
        before=copy.deepcopy(receipt);migration=migrate_legacy_receipt(receipt)
        self.assertEqual(migration['historical_result'],'PASS')
        self.assertFalse(migration['metric_evidence']['historical_pass_transferred'])
        self.assertFalse(migration['metric_evidence']['current_metrics_executed'])
        self.assertEqual(migration['legacy_receipt'],before)
        self.assertEqual(receipt,before)


if __name__=='__main__':unittest.main()
