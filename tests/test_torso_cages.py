import copy
import json
import math
import unittest

from a3d.core import StudioError, digest
from a3d.pattern_assembly import _cage_point, _compile_cage, _compile_arc_sections, _section_point
from a3d.sewing import edge_chain, sample_chain, mesh_quality
from a3d.torso_sections import source_bound_torso_cages


def fixture():
    front = {'vertices':[[1.,0.],[4.,0.],[5.,6.],[6.,12.],[1.,12.]],
        'faces':[[0,1,2],[0,2,3],[0,3,4]],
        'edges':{'side':[1,2,3], 'shoulder':[3,4], 'free':[4,0]}}
    back = {'vertices':[[0.,0.],[-4.,0.],[-5.,6.],[-6.,12.],[0.,12.]],
        'faces':[[0,1,2],[0,2,3],[0,3,4]],
        'edges':{'side':[3,2,1], 'shoulder':[3,4], 'center':[0,4]}}
    data = {'pieces':{'front':front, 'back':back}, 'seams':[{'id':'actual-side',
        'piece_a':'front', 'piece_b':'back', 'edge_a':'side', 'edge_b':'side',
        'orientation':'reverse', 'kind':'permanent'}]}
    frames = {pid:{'source_ref':'fixture:measured-skin-current-guide', 'u_direction':direction,
        'arc_sections':[{'v_cm':v, 'arc_offset_cm':0.,
            'curve_cm':[[0.,offset+v/12 if pid=='back' else 0.,v],
                        [15.,offset+v/12 if pid=='back' else 0.,v]]} for v in (0.,12.)]}
        for pid,direction,offset in (('front',1,0.),('back',-1,2.))}
    return data, frames


class SourceBoundTorsoCages(unittest.TestCase):
    def test_json_roundtrip_preserves_full_report_and_exact_reconstruction(self):
        data,frames = fixture(); before = digest([data,frames])
        cages,report = source_bound_torso_cages(data,frames)
        serialized = json.dumps({'panels':cages,'report':report},allow_nan=False)
        restored = json.loads(serialized)
        self.assertEqual(restored,{'panels':cages,'report':report})
        source,guide = json.loads(json.dumps([data,frames],allow_nan=False))
        reconstructed,receipt = source_bound_torso_cages(source,guide)
        self.assertEqual(restored,{'panels':reconstructed,'report':receipt})
        self.assertEqual(digest([data,frames]),before)

    def test_shared_source_boundary_is_exact_between_knots_and_input_is_immutable(self):
        data, old = fixture(); before = digest([data,old])
        cages, report = source_bound_torso_cages(data,old)
        compiled = {pid:_compile_cage(frame,pid) for pid,frame in cages.items()}
        self.assertGreater(report['relations'][0]['max_initial_guide_gap_cm'],2.9)
        for fraction in (0.,.013,.16134918981837518,.499,.51,.842076250287768,1.):
            points = [sample_chain(edge_chain(data['pieces'][pid],'side')[1],t)
                      for pid,t in (('front',fraction),('back',1-fraction))]
            targets = [_cage_point(cages[pid],compiled[pid],uv,pid)[0]
                       for pid,uv in zip(('front','back'),points)]
            self.assertLess(math.dist(*targets),1e-10)
        self.assertEqual(digest([data,old]),before)
        self.assertEqual(report['relations'][0]['max_common_control_gap_cm'],0.)
        self.assertAlmostEqual(report['max_target_correction_cm']['front'],1.5)
        self.assertAlmostEqual(report['max_target_correction_cm']['back'],1.5)
        self.assertEqual(report['qualification'],'NONE')
        self.assertEqual(report['front_coverage'],'NOT_REVIEWED')
        self.assertEqual(report['metric_assessment'],'REQUIRED')
        self.assertEqual(report['contact_assessment'],'REQUIRED')
        self.assertTrue(all('arc_sections' not in frame for frame in cages.values()))

    def test_common_targets_are_existing_proposals_mean_and_unsewn_controls_are_retained(self):
        data,old = fixture(); cages,report = source_bound_torso_cages(data,old,subdivisions=3)
        original_compiled = {pid:_compile_arc_sections(frame,pid) for pid,frame in old.items()}
        touched = {tuple(key) for pair in report['relations'][0]['paired_cage_controls'] for key in pair}
        for a,b in report['relations'][0]['paired_cage_controls']:
            original = [_section_point(old[pid],original_compiled[pid],cages[pid]['uv_cm'][index],pid)[0]
                        for pid,index in (a,b)]
            expected = [math.fsum(point[k] for point in original)/2 for k in range(3)]
            self.assertEqual(cages[a[0]]['target_cm'][a[1]],expected)
        for pid,frame in cages.items():
            for index,uv in enumerate(frame['uv_cm']):
                if (pid,index) not in touched:
                    self.assertEqual(frame['target_cm'][index],
                        _section_point(old[pid],original_compiled[pid],uv,pid)[0])
        # Both source face triangulations cover precisely the original area.
        for pid,frame in cages.items():
            area = sum(abs((b[0]-a[0])*(c[1]-a[1])-(b[1]-a[1])*(c[0]-a[0]))/2
                for triangle in frame['triangles'] for a,b,c in [[frame['uv_cm'][i] for i in triangle]])
            source = data['pieces'][pid]['vertices']
            expected = abs(sum(a[0]*b[1]-b[0]*a[1] for a,b in zip(source,source[1:]+source[:1]))/2)
            self.assertAlmostEqual(area,expected)

    def test_incompatible_corner_partitions_cannot_be_silently_resampled(self):
        data,frames = fixture()
        piece = data['pieces']['back'];piece['vertices'][2] = [-4.5,3.]
        # The seam is the same straight geometric edge, with the same length,
        # but its actual source corner is at a different normalized fraction.
        before = digest([data,frames])
        with self.assertRaisesRegex(StudioError,'corner partitions') as caught:
            source_bound_torso_cages(data,frames)
        self.assertEqual(caught.exception.guide_diagnostic['source_seam_id'],'actual-side')
        self.assertEqual(caught.exception.guide_diagnostic['garment_impossibility'],'NOT_ESTABLISHED')
        self.assertEqual(digest([data,frames]),before)

    def test_unequal_source_lengths_and_undeclared_orientation_are_refused(self):
        for variant in ('length','orientation','missing'):
            data,frames = fixture()
            if variant == 'length':
                data['pieces']['back']['vertices'][2][0] -= 1.
            elif variant == 'orientation':
                del data['seams'][0]['orientation']
            else:
                data['seams'] = []
            with self.subTest(variant=variant),self.assertRaises(StudioError):
                source_bound_torso_cages(data,frames)

    def test_bounded_native_source_only_no_new_material_or_hybrid_frame(self):
        for variant in ('faces','winding','nonfinite','hybrid','budget','boolean'):
            data,frames = fixture();kwargs = {}
            if variant == 'faces':
                del data['pieces']['front']['faces']
            elif variant == 'winding':
                data['pieces']['front']['faces'][0].reverse()
            elif variant == 'nonfinite':
                data['pieces']['front']['vertices'][0][0] = math.nan
            elif variant == 'hybrid':
                frames['front']['uv_cm'] = [[1.,0.]]
            elif variant == 'budget':
                kwargs['subdivisions'] = 17
            else:
                kwargs['subdivisions'] = True
            with self.subTest(variant=variant),self.assertRaises(StudioError):
                source_bound_torso_cages(data,frames,**kwargs)

    def test_internal_seams_and_external_relations_have_separate_scope(self):
        data,frames = fixture()
        data['pieces']['sleeve'] = copy.deepcopy(data['pieces']['front'])
        data['seams'].append({'id':'external-armhole', 'piece_a':'front', 'piece_b':'sleeve',
            'edge_a':'shoulder', 'edge_b':'side', 'orientation':'forward', 'kind':'permanent'})
        cages,report = source_bound_torso_cages(data,frames)
        self.assertEqual(set(cages),{'front','back'})
        self.assertEqual(report['unprocessed_external_relations'],['external-armhole'])
        self.assertEqual([row['source_seam_id'] for row in report['relations']],['actual-side'])
        self.assertEqual(digest(cages),report['cage_sha256'])

    def test_three_panel_source_corner_is_transitive_and_relation_order_independent(self):
        data,frames = fixture()
        # A source junction of three explicit pieces. The mirrored boundary
        # starts at the same side/shoulder corner without an easing mismatch.
        data['pieces']['back']['vertices'] = [[-u,v] for u,v in data['pieces']['front']['vertices']]
        data['pieces']['third'] = copy.deepcopy(data['pieces']['front'])
        frames['third'] = copy.deepcopy(frames['front'])
        for row in frames['third']['arc_sections']:
            for point in row['curve_cm']:
                point[1] = 6.
        data['seams'].append({'id':'actual-junction-shoulder', 'piece_a':'back', 'piece_b':'third',
            'edge_a':'shoulder', 'edge_b':'shoulder', 'orientation':'forward', 'kind':'permanent'})
        cages,report = source_bound_torso_cages(data,frames)
        # Three original proposals at the junction: y=0, y=3, y=6.
        for pid,uv in (('front',[6.,12.]),('back',[-6.,12.]),('third',[6.,12.])):
            index = cages[pid]['uv_cm'].index(uv)
            self.assertEqual(cages[pid]['target_cm'][index],[6.,3.,12.])
        reordered = copy.deepcopy(data);reordered['seams'].reverse()
        again,another = source_bound_torso_cages(reordered,frames)
        # Source identity records order; actual correspondence does not.
        for pid in cages:
            self.assertEqual(again[pid]['target_cm'],cages[pid]['target_cm'])
        self.assertEqual(another['max_target_correction_cm'],report['max_target_correction_cm'])

    def test_metric_gate_still_rejects_stretched_corrected_cage(self):
        data,frames = fixture(); cages,report = source_bound_torso_cages(data,frames)
        frame = cages['front']; limits = {'min_angle_degrees':0., 'min_edge_cm':.001,
            'min_stretch':.999999, 'max_stretch':1.000001}
        with self.assertRaisesRegex(StudioError,'distorted') as caught:
            mesh_quality([uv+[0.] for uv in frame['uv_cm']],frame['target_cm'],frame['triangles'],limits)
        self.assertIn('stretch',caught.exception.quality_violations)
        self.assertGreater(caught.exception.quality_metrics['max_stretch'],limits['max_stretch'])
        self.assertEqual(report['qualification'],'NONE')

    def test_rotated_measured_guide_frame_has_the_same_source_correspondence(self):
        data,frames = fixture(); cages,_ = source_bound_torso_cages(data,frames)
        moved = copy.deepcopy(frames)
        transform = lambda p:[12.-p[1],7.+p[2],-3.+p[0]]
        for frame in moved.values():
            for row in frame['arc_sections']:
                row['curve_cm'] = [transform(p) for p in row['curve_cm']]
        rotated,_ = source_bound_torso_cages(data,moved)
        for pid in cages:
            self.assertEqual(rotated[pid]['uv_cm'],cages[pid]['uv_cm'])
            self.assertEqual(rotated[pid]['triangles'],cages[pid]['triangles'])
            self.assertTrue(all(math.dist(transform(a),b) < 1e-10
                for a,b in zip(cages[pid]['target_cm'],rotated[pid]['target_cm'])))

    def test_semantic_surface_path_returns_only_source_cages_with_current_parameters(self):
        from a3d.semantic_placement import torso_volume_frames
        from tests.test_semantic_placement import fixture as semantic_fixture
        from tests.test_torso_sections import section
        source,_,profile = semantic_fixture()
        data = {'pieces':{pid:source['pieces'][pid] for pid in ('front','back')},
            'seams':[{'id':'actual-side','piece_a':'front','piece_b':'back',
                'edge_a':'side','edge_b':'side','orientation':'forward','kind':'permanent'}]}
        for piece in data['pieces'].values():
            piece['faces'] = [[0,1,2],[0,2,3]]
        for point in data['pieces']['back']['vertices']:
            point[0] *= -1
        semantics = {pid:{'role':pid,'side':'right','layer':'outer'} for pid in data['pieces']}
        profile['sections'] = [section(v) for v in (130.,135.,140.)]
        before = digest([data,semantics,profile])
        report = torso_volume_frames(data,semantics,profile,surface_sections=True,upper_blend=0.)
        self.assertEqual(report['source_boundary_cage']['method'],'SOURCE_PERMANENT_BOUNDARY_COMMON_TARGET_CAGE')
        self.assertEqual(report['qualification'],'NONE')
        self.assertEqual(report['fitting'],'NOT_EXECUTED')
        self.assertTrue(all(set(frame) == {'source_ref','uv_cm','target_cm','triangles'} for frame in report['panels'].values()))
        self.assertEqual(digest([data,semantics,profile]),before)


if __name__ == '__main__':
    unittest.main()
