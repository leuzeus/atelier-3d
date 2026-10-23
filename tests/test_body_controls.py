import copy
import math
import unittest

from a3d.anatomy_profile import profile_mesh
from a3d.body_controls import WIDTH_DEPTH_RELATIVE_TOLERANCE, cage_from_segmentation, section_dimensions, solve_girths
from a3d.core import StudioError, digest


def fixture():
    count = 16
    heights = list(range(0, 181, 5))
    # Sourced mesh fixture with local girth extrema at the declared body bands.
    def radius(z):
        return 10.+4.*math.exp(-((z-90.)/13.)**2)+5.*math.exp(-((z-133.)/9.)**2)
    points = [[radius(z)*math.cos(i*math.tau/count), .8*radius(z)*math.sin(i*math.tau/count), float(z)]
              for z in heights for i in range(count)]
    faces = [[ring*count+i, ring*count+(i+1)%count,
              (ring+1)*count+(i+1)%count, (ring+1)*count+i]
             for ring in range(len(heights)-1) for i in range(count)]
    faces += [list(reversed(range(count))), list(range((len(heights)-1)*count, len(heights)*count))]
    geometry = {'vertices_cm': points, 'faces': faces, 'source_sha256': 'a'*64, 'pose_sha256': 'b'*64}
    options = {'up_axis': [0., 0., 1.], 'forward_axis': [0., 1., 0.], 'origin_cm': [0., 0., 0.],
               'section_count': 24, 'torso_faces': list(range(len(faces))),
               'segmentation_source_ref': 'synthetic-reviewed-torso-face-ids', 'torso_seed_xy_cm': [0., 0.]}
    budgets = {'max_iterations': 15, 'max_evaluations': 150, 'finite_difference_step': .001,
               'damping': .001, 'line_search_steps': 8, 'min_scale': .85, 'max_scale': 1.15}
    return geometry, options, budgets


class BodyControls(unittest.TestCase):
    def test_measured_girth_targets_protected_regions_and_source_immutability(self):
        geometry, options, budgets = fixture(); cage = cage_from_segmentation(geometry, options)
        before = digest([geometry, options, cage, budgets])
        profile = profile_mesh(geometry, options)
        targets = {name: profile['landmarks'][name]['girth_cm']*factor
                   for name, factor in [('hip', 1.02), ('waist', .99), ('chest', 1.03)]}
        result = solve_girths(geometry, options, cage, targets, .03, budgets)
        self.assertEqual(result['receipt']['status'], 'TARGETS_MEASURED', result['receipt']['residuals_cm'])
        self.assertTrue(all(abs(value) <= .03 for value in result['receipt']['residuals_cm'].values()))
        for index in cage['protected_vertex_ids']:
            self.assertEqual(result['geometry']['vertices_cm'][index], geometry['vertices_cm'][index])
        self.assertEqual(result['geometry']['faces'], geometry['faces'])
        self.assertEqual(result['profile']['stature_cm'], 180.)
        self.assertEqual(result['receipt']['fitting'], 'NOT_EXECUTED')
        self.assertEqual(before, digest([geometry, options, cage, budgets]))
        # Each unprotected ring receives one radial scale, conserving its
        # source ellipse's width/depth ratio instead of flattening it.
        for z in (85., 110., 130.):
            source_ring = [point for point in geometry['vertices_cm'] if point[2] == z]
            actual_ring = [point for point in result['geometry']['vertices_cm'] if point[2] == z]
            ratio = lambda ring: ((max(p[0] for p in ring)-min(p[0] for p in ring))/
                                  (max(p[1] for p in ring)-min(p[1] for p in ring)))
            self.assertAlmostEqual(ratio(actual_ring), ratio(source_ring), places=10)

    def test_deterministic_rotated_frame_and_stale_cage_refusal(self):
        geometry, options, budgets = fixture()
        rotate = lambda p: [p[0], -p[2], p[1]]
        geometry['vertices_cm'] = [rotate(point) for point in geometry['vertices_cm']]
        options.update(up_axis=[0., -1., 0.], forward_axis=[0., 0., 1.])
        cage = cage_from_segmentation(geometry, options)
        targets = {'chest': profile_mesh(geometry, options)['landmarks']['chest']['girth_cm']*1.02}
        first = solve_girths(geometry, options, cage, targets, .03, budgets)
        self.assertEqual(first, solve_girths(geometry, options, cage, targets, .03, budgets))
        self.assertEqual(first['receipt']['status'], 'TARGETS_MEASURED')
        for change in ('geometry', 'pose', 'options', 'cage'):
            source, config, controls = copy.deepcopy(geometry), copy.deepcopy(options), copy.deepcopy(cage)
            if change == 'geometry': source['vertices_cm'][0][0] += .01
            if change == 'pose': source['pose_sha256'] = 'c'*64
            if change == 'options': config['section_count'] = 25
            if change == 'cage': controls['weights'][0]['weights'][0] += .001
            with self.subTest(change=change), self.assertRaises(StudioError):
                solve_girths(source, config, controls, targets, .03, budgets)

    def test_protected_cut_edge_endpoints_require_measured_shape_compensation(self):
        geometry, options, budgets = fixture()
        # Three source seam vertices at z=90 also belong to a protected region.
        # The measured hip plane crosses edges with one protected endpoint.
        geometry['faces'].append([18*16, 18*16+1, 18*16+2])
        source = profile_mesh(geometry, options)
        cage = cage_from_segmentation(geometry, options)
        targets = {name: source['landmarks'][name]['girth_cm']*factor
                   for name, factor in [('hip', 1.03), ('waist', .97), ('chest', 1.03)]}
        result = solve_girths(geometry, options, cage, targets, .03, budgets)
        self.assertEqual(result['receipt']['status'], 'TARGETS_MEASURED', result['receipt'])
        self.assertTrue(result['receipt']['protected_boundary_shape_compensation_used'])
        before = section_dimensions(geometry, options, source)
        after = section_dimensions(result['geometry'], options, source)
        for name in targets:
            error = abs(after[name]['width_depth_ratio']/before[name]['width_depth_ratio']-1.)
            self.assertLessEqual(error, WIDTH_DEPTH_RELATIVE_TOLERANCE)
            self.assertAlmostEqual(after[name]['section_height_cm'], before[name]['section_height_cm'])
        for index in cage['protected_vertex_ids']:
            self.assertEqual(geometry['vertices_cm'][index], result['geometry']['vertices_cm'][index])

    def test_budget_exhaustion_and_impossible_target_never_claim_success(self):
        geometry, options, budgets = fixture(); cage = cage_from_segmentation(geometry, options)
        budgets['max_evaluations'] = 1
        limited = solve_girths(geometry, options, cage, {'chest': 300.}, .01, budgets)
        self.assertEqual(limited['receipt']['status'], 'BUDGET_EXHAUSTED')
        self.assertEqual(limited['receipt']['evaluations'], 1)
        self.assertEqual(limited['geometry']['vertices_cm'], geometry['vertices_cm'])
        budgets['max_evaluations'] = 150
        impossible = solve_girths(geometry, options, cage, {'chest': 300.}, .01, budgets)
        self.assertNotEqual(impossible['receipt']['status'], 'TARGETS_MEASURED')
        self.assertGreater(abs(impossible['receipt']['residuals_cm']['chest']), .01)
        with self.assertRaisesRegex(StudioError, 'Unsupported body control'):
            solve_girths(geometry, options, cage, {'shoulder_width': 40.}, .1, budgets)

    def test_unsourced_segmentation_and_invalid_domains_refused(self):
        geometry, options, budgets = fixture()
        config = copy.deepcopy(options); del config['segmentation_source_ref']
        with self.assertRaises(StudioError): cage_from_segmentation(geometry, config)
        cage = cage_from_segmentation(geometry, options)
        for key, value in [('max_iterations', True), ('max_evaluations', 0), ('min_scale', .4), ('damping', 0), ('finite_difference_step', math.nan)]:
            bad = dict(budgets, **{key: value})
            with self.subTest(key=key), self.assertRaises(StudioError):
                solve_girths(geometry, options, cage, {'chest': 80.}, .1, bad)


if __name__ == '__main__':
    unittest.main()
