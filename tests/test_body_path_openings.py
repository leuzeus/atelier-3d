"""Synthetic source-cycle exploration, never acceptance of an opening."""
import copy
import math
import unittest
import xml.etree.ElementTree as ET
from unittest.mock import patch

from a3d.body_path_openings import (prepare_opening_candidates, render_opening_candidates,
                                   validate_opening_options)
from a3d.core import StudioError, digest


def fixture(vertex_crossing=True):
    ring = ([[10.,0.,80.],[9.,3.,81.],[6.,5.,82.],[0.,6.,83.],[-6.,5.,82.],[-9.,3.,81.],
             [-10.,0.,80.],[-9.,-3.,79.],[-6.,-5.,78.],[0.,-6.,77.],[6.,-5.,78.],[9.,-3.,79.]]
            if vertex_crossing else
            [[10.,0.,80.],[6.,5.,82.],[-6.,5.,82.],[-10.,0.,80.],[-6.,-5.,78.],[6.,-5.,78.]])
    n = len(ring); vertices = ring+[[0.,0.,0.],[0.,0.,180.]]
    faces = [[n,(i+1)%n,i] for i in range(n)]+[[n+1,i,(i+1)%n] for i in range(n)]
    geometry = {'vertices_cm':vertices,'faces':faces,'face_sets':[2]*n+[7]*n,
                'source_sha256':'a'*64,'pose_sha256':digest(vertices)}
    profile = {'frame':{'origin_cm':[0.,0.,0.],'right':[1.,0.,0.],
                        'forward':[0.,1.,0.],'up':[0.,0.,1.]},
               'source_sha256':geometry['source_sha256'],'pose_sha256':geometry['pose_sha256'],
               'geometry_sha256':digest([vertices,faces])}
    path = make_path(geometry,list(range(n)))
    options = {'path_id':path['id'],'reference_plane':'BODY_SAGITTAL',
               'front_anchor':'UNIQUE_FRONTMOST_INTERSECTION','max_pairs':3,
               'max_seconds':10.,'max_output_bytes':2*1024*1024}
    return profile,geometry,path,options


def make_path(geometry,ids):
    edges = list(zip(ids,ids[1:]+ids[:1])); owners={}
    for face_id,face in enumerate(geometry['faces']):
        for a,b in zip(face,face[1:]+face[:1]):owners.setdefault(tuple(sorted((a,b))),[]).append(face_id)
    return {'id':'neck.source-boundary','measurement_kind':'SOURCE_REGION_BOUNDARY_LENGTH',
        'source_joint':'declared.test-interface','source_regions':[2,7],'closed':True,
        'vertex_ids':ids,'edge_vertex_ids':[list(edge)for edge in edges],
        'edge_source_face_ids':[sorted(owners[tuple(sorted(edge))])for edge in edges],
        'curve_world_cm':[copy.deepcopy(geometry['vertices_cm'][i])for i in ids],
        'length_cm':math.fsum(math.dist(geometry['vertices_cm'][a],geometry['vertices_cm'][b])for a,b in edges),
        'tailoring_homology':'REVIEW_REQUIRED'}


def with_ring(points):
    profile,geometry,_,options=fixture();n=len(points)
    geometry['vertices_cm']=copy.deepcopy(points)+[[0.,0.,0.],[0.,0.,180.]]
    geometry['faces']=[[n,(i+1)%n,i]for i in range(n)]+[[n+1,i,(i+1)%n]for i in range(n)]
    geometry['face_sets']=[2]*n+[7]*n;geometry['pose_sha256']=digest(points)
    profile.update(pose_sha256=geometry['pose_sha256'],geometry_sha256=digest([geometry['vertices_cm'],geometry['faces']]))
    return profile,geometry,make_path(geometry,list(range(n))),options


class BodyPathOpenings(unittest.TestCase):
    def test_vertex_front_proposals_follow_topological_order_and_preserve_every_input(self):
        values=fixture();before=digest(values);result=prepare_opening_candidates(*values)
        self.assertEqual(before,digest(values));self.assertEqual(result,prepare_opening_candidates(*values))
        self.assertEqual(result['front_anchor']['selector'],{'kind':'SOURCE_VERTEX','vertex_id':3})
        self.assertEqual(result['produced_pairs'],3)
        self.assertEqual(result['stop_reason'],'PAIR_BUDGET_REACHED')
        first=result['candidates'][0]
        self.assertEqual([p['selector']['vertex_id']for p in first['endpoints']],[2,4])
        self.assertEqual(first['front_omitted_arc']['vertex_ids'],[2,3,4])
        self.assertEqual(first['remaining_arc']['vertex_ids'],[4,5,6,7,8,9,10,11,0,1,2])
        for proposal in result['candidates']:
            self.assertAlmostEqual(proposal['front_omitted_arc']['length_cm']+proposal['remaining_arc']['length_cm'],values[2]['length_cm'],places=12)
            self.assertEqual(proposal['selection'],'NONE');self.assertIsNone(proposal['ease_cm'])
        self.assertFalse(result['body_reference_review_transferred']);self.assertEqual(result['acceptance'],'NONE')

    def test_intersection_inside_a_real_edge_has_exact_fraction_provenance(self):
        values=fixture(False);result=prepare_opening_candidates(*values)
        selector=result['front_anchor']['selector']
        self.assertEqual(selector,{'kind':'SOURCE_EDGE_FRACTION','edge_vertex_ids':[1,2],'fraction':.5,'fraction_exact':[1,2]})
        self.assertEqual(result['front_anchor']['world_cm'],[0.,5.,82.])
        self.assertEqual([p['selector']['vertex_id']for p in result['candidates'][0]['endpoints']],[1,2])

    def test_cycle_rotation_and_reversal_keep_candidates_and_front_provenance_identical(self):
        values=fixture();baseline=prepare_opening_candidates(*values)
        ids=values[2]['vertex_ids']
        for order in (ids[5:]+ids[:5],list(reversed(ids)),list(reversed(ids[5:]+ids[:5]))):
            changed=list(copy.deepcopy(values));changed[2]=make_path(changed[1],order)
            result=prepare_opening_candidates(*changed)
            self.assertEqual(result['candidates'],baseline['candidates'])
            self.assertEqual(result['front_anchor'],baseline['front_anchor'])
            self.assertEqual(result['canonical_source_vertex_ids'],baseline['canonical_source_vertex_ids'])

    def test_rotated_translated_frame_keeps_source_endpoint_ids_and_material_lengths(self):
        values=list(fixture());baseline=prepare_opening_candidates(*values)
        # Exact signed permutation preserves vertex-on-plane cases exactly.
        transform=lambda p:[p[2]+17.,-p[0]-9.,p[1]+2.]
        values[1]['vertices_cm']=list(map(transform,values[1]['vertices_cm']))
        values[0]['frame']={'origin_cm':[17.,-9.,2.],'right':[0.,-1.,0.],
                            'forward':[0.,0.,1.],'up':[1.,0.,0.]}
        values[1]['pose_sha256']=digest(values[1]['vertices_cm'])
        values[0].update(pose_sha256=values[1]['pose_sha256'],geometry_sha256=digest([values[1]['vertices_cm'],values[1]['faces']]))
        values[2]=make_path(values[1],values[2]['vertex_ids']);result=prepare_opening_candidates(*values)
        self.assertEqual(result['front_anchor']['selector'],baseline['front_anchor']['selector'])
        for a,b in zip(result['candidates'],baseline['candidates']):
            self.assertEqual([p['selector']for p in a['endpoints']],[p['selector']for p in b['endpoints']])
            self.assertEqual(a['front_omitted_arc']['length_cm'],b['front_omitted_arc']['length_cm'])

    def test_general_rotated_frame_preserves_interior_crossing_and_neighbours(self):
        values=list(fixture(False));baseline=prepare_opening_candidates(*values);a,b=.37,.61
        def rotate(p):
            q=[math.cos(a)*p[0]-math.sin(a)*p[1],math.sin(a)*p[0]+math.cos(a)*p[1],p[2]]
            return [q[0],math.cos(b)*q[1]-math.sin(b)*q[2],math.sin(b)*q[1]+math.cos(b)*q[2]]
        offset=[17.,-9.,2.]
        values[1]['vertices_cm']=[[x+y for x,y in zip(rotate(p),offset)]for p in values[1]['vertices_cm']]
        values[0]['frame']={'origin_cm':offset,**{name:rotate(axis)for name,axis in
            [('right',[1.,0.,0.]),('forward',[0.,1.,0.]),('up',[0.,0.,1.])]}}
        values[1]['pose_sha256']=digest(values[1]['vertices_cm'])
        values[0].update(pose_sha256=values[1]['pose_sha256'],geometry_sha256=digest([values[1]['vertices_cm'],values[1]['faces']]))
        values[2]=make_path(values[1],values[2]['vertex_ids']);result=prepare_opening_candidates(*values)
        self.assertEqual(result['front_anchor']['selector']['edge_vertex_ids'],[1,2])
        for actual,expected in zip(result['candidates'],baseline['candidates']):
            self.assertEqual([p['selector']for p in actual['endpoints']],[p['selector']for p in expected['endpoints']])
            self.assertAlmostEqual(actual['remaining_arc']['length_cm'],expected['remaining_arc']['length_cm'],places=10)

    def test_nonplanar_arcs_use_real_three_dimensional_lengths_not_horizontal_chords(self):
        values=fixture();result=prepare_opening_candidates(*values);arc=result['candidates'][0]['front_omitted_arc']
        points=[values[1]['vertices_cm'][i]for i in arc['vertex_ids']]
        projected=math.fsum(math.dist(a[:2],b[:2])for a,b in zip(points,points[1:]))
        self.assertGreater(arc['length_cm'],projected)
        self.assertGreater(arc['length_cm'],math.dist(points[0],points[-1]))

    def test_ambiguous_sagittal_plane_coincidence_tangency_multiple_hits_and_front_tie_refused(self):
        rings=[[[0.,4.,80.],[0.,2.,81.],[-4.,-3.,80.],[4.,-3.,80.]],
               [[0.,5.,80.],[4.,0.,81.],[3.,-3.,80.]],
               [[-3.,5.,80.],[3.,5.,80.],[-3.,-5.,80.],[3.,-5.,80.]],
               [[-3.,2.,80.],[3.,2.,81.],[3.,2.,82.],[-3.,2.,83.]]]
        for ring in rings:
            with self.subTest(ring=ring),self.assertRaises(StudioError):prepare_opening_candidates(*with_ring(ring))

    def test_source_pose_points_edges_faces_length_and_path_owner_mismatch_refused(self):
        for mode in ('pose','point','edge','face','length','owner','id','closed'):
            values=list(copy.deepcopy(fixture()))
            if mode=='pose':values[1]['pose_sha256']='c'*64
            if mode=='point':values[2]['curve_world_cm'][0][0]+=.1
            if mode=='edge':values[2]['edge_vertex_ids'][0][1]=2
            if mode=='face':values[2]['edge_source_face_ids'][0]=[0,1]
            if mode=='length':values[2]['length_cm']+=.1
            if mode=='owner':values[2]['source_regions']=[2,9]
            if mode=='id':values[3]['path_id']='another.path'
            if mode=='closed':values[2]['closed']=False
            with self.subTest(mode=mode),self.assertRaises(StudioError):prepare_opening_candidates(*values)

    def test_pair_output_clock_and_parent_budgets_are_explicit_and_enforced(self):
        for key,value in [('max_pairs',True),('max_pairs',33),('max_seconds',float('nan')),('max_output_bytes',False)]:
            options=fixture()[-1];options[key]=value
            with self.subTest(key=key,value=value),self.assertRaises(StudioError):validate_opening_options(options)
        values=list(fixture());values[-1]['max_output_bytes']=1
        with self.assertRaisesRegex(StudioError,'byte budget'):prepare_opening_candidates(*values)
        for times in ([0.,11.],[2.,1.],[float('nan')]):
            with patch('a3d.body_path_openings.time.monotonic',side_effect=times),self.assertRaisesRegex(StudioError,'clock'):
                prepare_opening_candidates(*fixture())
        def parent_refusal():raise StudioError('parent budget exhausted')
        with self.assertRaisesRegex(StudioError,'parent budget'):prepare_opening_candidates(*fixture(),budget_check=parent_refusal)

    def test_requested_pair_cap_never_wraps_the_cycle_or_chooses_a_rear_opening(self):
        values=list(fixture());values[-1]['max_pairs']=32;report=prepare_opening_candidates(*values)
        self.assertEqual(report['produced_pairs'],5)
        self.assertEqual(report['stop_reason'],'SOURCE_CYCLE_CAPACITY_REACHED')
        rear=report['rear_intersection']['selector']['vertex_id']
        for candidate in report['candidates']:
            self.assertNotIn(rear,candidate['front_omitted_arc']['vertex_ids'])
            self.assertNotEqual(candidate['endpoints'][0]['selector'],candidate['endpoints'][1]['selector'])
            omitted=candidate['front_omitted_arc']['vertex_ids'];remaining=candidate['remaining_arc']['vertex_ids']
            self.assertEqual(set(omitted)&set(remaining),{omitted[0],omitted[-1]})
            self.assertEqual(set(omitted)|set(remaining),set(values[2]['vertex_ids']))

    def test_four_projection_svg_uses_all_exact_arc_vertices_and_refuses_forged_report(self):
        values=fixture();before=digest(values);report=prepare_opening_candidates(*values)
        svg=render_opening_candidates(values[0],values[1],report,values[-1]);tree=ET.fromstring(svg)
        self.assertEqual(digest(values),before)
        lines=tree.findall('.//{http://www.w3.org/2000/svg}polyline')
        self.assertEqual(len(lines),report['produced_pairs']*8)
        self.assertIn('non sélectionnées',svg.decode());self.assertIn('aucune aisance',svg.decode())
        changed=copy.deepcopy(report);changed['candidates'][0]['remaining_arc']['length_cm']+=1.
        with self.assertRaisesRegex(StudioError,'source reconstruction'):
            render_opening_candidates(values[0],values[1],changed,values[-1])
        bounded=dict(values[-1],max_output_bytes=len(svg))
        with self.assertRaisesRegex(StudioError,'byte budget'):
            render_opening_candidates(values[0],values[1],report,bounded)


if __name__=='__main__':unittest.main()
