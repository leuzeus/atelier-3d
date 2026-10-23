import copy

from a3d.core import ROOT, StudioError, read_json, sha
from a3d.guard import admit_operation
from a3d.sewing_placement import placement_geometry
from tests.test_core import Case
from tests.test_sewing_diagnostics import payload
from tests.support import ready_project


class PlacementTests(Case):
    def test_measures_samples_supports_closures_and_orientation_without_acceptance(self):
        data = payload()
        for p in data['panels'].values():
            p.update(boundary_source_arclength_cm=[0, 2, 4], source_contour_sha256='c'*64)
        data['seams']['armhole'].update(edge_a='edge', edge_b='edge')
        data['seams']['opening'] = {**data['seams']['armhole'], 'kind': 'closure'}
        recipe = read_json(ROOT/'templates/sewing-recipe.json')
        recipe['placements'] = {pid: {'mode': 'flat'} for pid in data['panels']}
        original = copy.deepcopy((data, recipe))
        def nearest(p):
            return [{'object': 'Arm', 'face': 7, 'point_cm': [p[0], p[1], -1],
                'normal': [0, 0, -1], 'distance_cm': 1, 'signed_offset_cm': -1}]
        report = placement_geometry(data, data['placed_cm'], recipe, nearest,
            lambda a, b: [{'object': 'Arm', 'first_hit_cm': [5, 0, 0]}])
        self.assertEqual(report['seams']['armhole']['max_gap_cm'], 10)
        self.assertEqual(report['seams']['armhole']['pairs'][0]['a']['boundary_source_arclength_cm'], 2)
        self.assertEqual(report['panels']['sleeve']['supports'][0]['pin_weight'], .5)
        self.assertEqual(report['panels']['body']['collider_regions']['Arm']['inward_faces'], 1)
        self.assertEqual(report['warnings']['permanent_seams_above_final_tolerance'], ['armhole'])
        self.assertIsNone(report['seams']['opening']['above_final_seam_tolerance'])
        self.assertFalse(report['accepted']); self.assertEqual(report['simulation'], 'NOT_EXECUTED')
        self.assertEqual((data, recipe), original)

    def test_admission_preserves_pending_and_requires_packaged_pattern_route(self):
        project = ready_project(self.root, True)
        with project.transaction() as db:
            state = project.state(db); state['pending_blender_operation'] = {'status': 'failed'}
            project.save(db, state, 'synthetic_failure', {})
        # Reuse a valid fixture recipe with the expected component identity.
        from a3d.core import atomic_json
        atomic_json(project.root/'recipe.json', read_json(ROOT/'templates/sewing-recipe.json'))
        before = sha(project.db)
        args = {'component_id': 'garment.coat', 'recipe_path': 'recipe.json'}
        admit_operation(project, 'inspect_sewing_placement', args)
        self.assertEqual(sha(project.db), before)
        with self.assertRaises(StudioError):
            admit_operation(project, 'inspect_sewing_placement', {**args, 'recipe_path': '../outside.json'})
        with self.assertRaises(StudioError):
            admit_operation(project, 'inspect_sewing_placement', {**args, 'component_id': 'unknown'})
        with self.assertRaisesRegex(StudioError, 'Unexpected'):
            admit_operation(project, 'inspect_sewing_placement', {**args, 'approve': True})
